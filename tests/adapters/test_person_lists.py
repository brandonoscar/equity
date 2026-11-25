"""Person lists (config/person_lists/*.yaml): config checks, names, addresses, byte windows,
HTML tables, planning, fetch and normalize. Offline (fake transports)."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from equity.adapters.base import REGISTRY, Fetched, FetchRequest, register
from equity.adapters.licenses import AddressSpec
from equity.adapters.person_lists import (
    LISTS_DIR,
    PartySpec,
    PersonListAdapter,
    PersonListConfig,
    PersonListConfigError,
    RangeClient,
    address_of,
    all_person_list_adapters,
    link_values,
    load_person_list,
    names_of,
    split_name,
    table_rows,
    window_lines,
)

from ..test_adapter_contract import check_contract

# Until equity.adapters.registry lists the person-list adapters, register them here so the
# contract, privacy and fixture-directory tests in this session see them.
for _cls in all_person_list_adapters():
    if _cls not in REGISTRY:
        register(_cls)

FIX = Path(__file__).parents[1] / "fixtures" / "adapters"
AT = datetime(2026, 11, 25, tzinfo=UTC)
CSV = (
    b"PropertyID,OwnerName,OwnerAddress1,OwnerCity,OwnerState,OwnerZipCode\n"
    b'"1"," MANN THOMAS J","12 OAK ST","TULSA","OK","741057306"\n'
    b'"2"," ACME PLUMBING LLC","UNKNOWN","UNKNOWN","OK","00000"\n'
    b'"3"," LEE ANN","5 ELM AVE","NORMAN","OK","73069"\n'
    b'"4"," RAY BO","9 PINE RD","ENID","OK","73701"\n'
)


def by_id(source_id: str) -> type[PersonListAdapter]:
    return next(c for c in all_person_list_adapters() if c.source_id == source_id)


def fetched(source_id: str, body: Any) -> Fetched:
    content = body if isinstance(body, bytes) else json.dumps(body).encode()
    return Fetched(source_id, "file:///x", AT, 200, content, "application/json")


def rows_of(adapter: PersonListAdapter, f: Fetched) -> dict[str, list[Mapping[str, Any]]]:
    out: dict[str, list[Mapping[str, Any]]] = {}
    for item in adapter.normalize(f):
        out.setdefault(item.table, []).append(item.row)
    return out


class FakeTransport:
    """robots.txt is a 404 (no restrictions); `pages` maps a URL prefix to a body; a Range
    header is served from `files`."""

    def __init__(self, pages: Mapping[str, bytes] | None = None,
                 files: Mapping[str, bytes] | None = None) -> None:  # fmt: skip
        self.pages = dict(pages or {})
        self.files = dict(files or {})
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                 ) -> tuple[int, bytes, str]:  # fmt: skip
        rng = headers.get("Range")
        self.calls.append((url, rng))
        if url.endswith("/robots.txt"):
            return 404, b"", "text/plain"
        if rng and url in self.files:
            data = self.files[url]
            first, last = (int(x) for x in rng.removeprefix("bytes=").split("-"))
            if first >= len(data):
                return 416, b"", "text/plain"
            return 206, data[first : last + 1], "binary/octet-stream"
        for prefix, body in self.pages.items():
            if url.startswith(prefix):
                return 200, body, "text/html"
        return 404, b"", "text/plain"


def client(t: FakeTransport) -> RangeClient:
    return RangeClient(min_interval_s=0, transport=t, sleep=lambda s: None)


# --- config -----------------------------------------------------------------------------


def test_every_config_loads_with_pii_covering_names_and_streets() -> None:
    paths = sorted(LISTS_DIR.glob("*.yaml"))
    assert paths
    for path in paths:
        cfg = load_person_list(path)
        assert cfg.pii_fields, path.name
        for p in cfg.parties:
            if p.person_names:
                assert set(p.name) | set(p.parts.values()) <= set(cfg.pii_fields)
            if p.address is not None:
                assert set(p.address.street) <= set(cfg.pii_fields)
        assert cfg["terms"]["summary"].strip(), path.name


def test_every_list_has_fixtures_with_only_pseudonyms() -> None:
    for cls in all_person_list_adapters():
        files = sorted((FIX / cls.source_id).glob("*.json"))
        assert files, cls.source_id
        for f in files:
            for row in json.loads(f.read_text())["rows"]:
                for k in cls.pii_fields:
                    v = row.get(k)
                    if isinstance(v, str) and v.strip():
                        assert v.startswith("TESTOWNER") or v.endswith(" TEST ST"), (f.name, k)


def _write(tmp_path: Path, **over: Any) -> Path:
    data: dict[str, Any] = {
        "source_id": "zz.test.list", "state": "ZZ", "jurisdiction": "99", "kind": "tax",
        "record_type": "unclaimed_property", "api": "socrata", "portal": "https://x.test",
        "dataset": "aaaa-1111", "parties": [{"name": "owner", "address": {"street": "st"}}],
        "terms": {"url": "https://x.test", "summary": "test", "checked_on": "2026-11-25"},
    }  # fmt: skip
    data.update(over)
    path = tmp_path / f"{data['source_id']}.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


@pytest.mark.parametrize(
    ("over", "match"),
    [
        ({"api": "ftp"}, "unknown api"),
        ({"kind": "voter"}, "kind must be"),
        ({"api": "csv_ranges"}, "missing"),
        ({"api": "csv_ranges", "csv": {"chunk_bytes": 1}}, "csv needs url or page"),
        ({"parties": [{"role": "x"}]}, "needs name or parts"),
        ({"parties": [{"name": "n", "format": "backwards"}]}, "unknown name format"),
        ({"parties": [{"parts": {"surname": "s"}}]}, "unknown name parts"),
        ({"terms": {"url": "u", "summary": "s"}}, "terms missing checked_on"),
    ],
)
def test_config_errors(tmp_path: Path, over: dict[str, Any], match: str) -> None:
    with pytest.raises(PersonListConfigError, match=match):
        load_person_list(_write(tmp_path, **over))


def test_config_file_must_be_named_for_its_source(tmp_path: Path) -> None:
    path = _write(tmp_path)
    other = path.with_name("zz.other.yaml")
    path.rename(other)
    with pytest.raises(PersonListConfigError, match="file name"):
        load_person_list(other)


# --- names and addresses ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "fmt", "want"),
    [
        ("MANN THOMAS J", "last_first", ("THOMAS", "J", "MANN", None)),
        ("MANN THOMAS", "last_first", ("THOMAS", None, "MANN", None)),
        ("SMITH JOHN A JR", "last_first", ("JOHN", "A", "SMITH", "JR")),
        ("MANN", "last_first", (None, None, None, None)),
        ("Jones, Charles Weldon", "last_comma_first", ("Charles", "Weldon", "Jones", None)),
        ("Tasha Ann McQuay", "first_last", ("Tasha", "Ann", "McQuay", None)),
        ("ROBERT KING III", "first_last", ("ROBERT", None, "KING", "III")),
        ("Cher", "first_last", (None, None, None, None)),
        ("ANY NAME", "as_is", (None, None, None, None)),
    ],
)
def test_split_name(name: str, fmt: str, want: tuple[str | None, ...]) -> None:
    p = split_name(name, fmt)
    assert (p["first"], p["middle"], p["last"], p["suffix"]) == want


def test_names_of_skips_orgs_parts_and_placeholders() -> None:
    spec = PartySpec.parse({"name": "n", "format": "last_first"})
    assert names_of({"n": " ACME PLUMBING LLC"}, spec, frozenset())[0][1]["last"] is None
    assert names_of({"n": " LEE ANN"}, spec, frozenset())[0][1]["last"] == "LEE"
    assert names_of({"n": "UNKNOWN"}, spec, frozenset({"UNKNOWN"})) == []
    both = PartySpec.parse({"name": "n", "split": " & "})
    assert [n for n, _ in names_of({"n": "ANN LEE & BO RAY"}, both, frozenset())] == [
        "ANN LEE", "BO RAY"]  # fmt: skip
    parts = PartySpec.parse({"parts": {"first": "f", "middle": "m", "last": "l"}})
    ((name, p),) = names_of({"f": "LIANA", "m": "Q", "l": "MACMAHON"}, parts, frozenset())
    assert name == "LIANA Q MACMAHON" and p["last"] == "MACMAHON"
    assert names_of({"f": "LIANA"}, parts, frozenset()) == []  # no last name: nobody


def test_address_placeholders_and_constant_state() -> None:
    spec = AddressSpec(("a1", "a2"), "city", "st", "zip")
    nowhere = {"a1": "UNKNOWN", "city": "UNKNOWN", "st": "OK", "zip": "00000"}
    assert address_of(nowhere, spec) is None  # a state alone is no address
    unknown = address_of({**nowhere, "city": "NOWATA", "zip": "74048"}, spec)
    assert unknown is not None
    assert (unknown["line1"], unknown["city"], unknown["state"], unknown["zip5"]) == (
        None, "NOWATA", "OK", "74048")  # fmt: skip
    full = address_of({"a1": "12 OAK ST", "a2": "APT 2", "city": "TULSA", "st": "OK",
                       "zip": "741057306"}, spec)  # fmt: skip
    assert full is not None and full["line1"] == "12 OAK ST APT 2" and full["zip5"] == "74105"
    mo = PartySpec.parse(
        {"name": "n", "address": {"street": "a", "city": "c", "state_const": "MO"}}
    )
    addr = address_of({"a": "416 N CENTENNIAL ST", "c": "KIRKSVILLE"}, mo.address)
    assert addr is not None and addr["state"] == "MO" and addr["city"] == "KIRKSVILLE"
    csz = AddressSpec(("s",), city_state_zip="t")
    fram = address_of({"s": "6 COPELAND RD", "t": "FRAMINGHAM, MA 01701"}, csz)
    assert fram is not None and (fram["city"], fram["state"], fram["zip5"]) == (
        "FRAMINGHAM", "MA", "01701")  # fmt: skip


# --- byte windows -----------------------------------------------------------------------


def test_window_lines_cover_the_file_once() -> None:
    data = CSV
    for chunk in (1, 7, 40, 64, 1000):
        got: list[bytes] = []
        for lo in range(0, len(data), chunk):
            start = max(lo - 1, 0)
            part = data[start : lo + chunk + 200]  # lines are shorter than 200 bytes
            got += window_lines(part, lo, lo + chunk, start, start + len(part) >= len(data))
        assert b"".join(got) == data, chunk


def test_window_lines_without_a_newline_in_range() -> None:
    assert window_lines(b"abcdef", 3, 6, 2, False) == []
    assert window_lines(b"abc", 0, 10, 0, True) == [b"abc"]
    assert window_lines(b"abc", 0, 10, 0, False) == []  # cut off, not the end of the file


def test_csv_fetch_windows_and_partitions() -> None:
    url = "https://up.test/files/Finder_20261029.csv"
    page = b'<html><script src="main.abc123.js"></script></html>'
    js = b'x="/files/Finder_20261029.csv";'
    t = FakeTransport({"https://up.test/app/portal": page, "https://up.test/main.abc123.js": js},
                      {url: CSV})  # fmt: skip
    cls = by_id("ok.treasurer.unclaimed_property")
    spec = {**cls.config["csv"], "page": "https://up.test/app/portal",
            "file": r"/files/Finder_\d{8}\.csv", "chunk_bytes": 100}  # fmt: skip
    cfg = PersonListConfig({**cls.config.data, "csv": spec}, cls.config.parties)
    adapter = type("T", (cls,), {"config": cfg})(client(t))
    assert adapter.current_csv_url() == url
    parts = list(adapter.partitions())
    assert [p["lo"] for p in parts] == ["0", "100", "200"]  # 3 probes then a 416
    seen: list[str] = []
    for p in parts:
        body = json.loads(adapter.fetch(FetchRequest(p)).content)
        assert body["columns"][0] == "PropertyID"
        seen += [r["PropertyID"] for r in body["rows"]]
    assert seen == ["1", "2", "3", "4"]


def test_csv_fixture_normalizes_names_and_addresses() -> None:
    cls = by_id("ok.treasurer.unclaimed_property")
    f = fetched(cls.source_id, json.loads(CSV_BODY))
    out = rows_of(cls(), f)
    parties = {p["raw_name"]: p for p in out["party"]}
    assert parties["MANN THOMAS J"]["last_name"] == "MANN"
    assert parties["MANN THOMAS J"]["first_name"] == "THOMAS"
    acme = parties["ACME PLUMBING LLC"]
    assert acme["party_kind"] == "org" and acme["last_name"] is None
    addr = {a["address_id"]: a for a in out["address"]}
    assert addr[acme["address_id"]]["line1"] is None  # 'UNKNOWN' street dropped
    assert len(out["source_record"]) == 3  # two rows share PropertyID 1 (joint owners)
    assert {r["record_key"] for r in out["source_record"]} == {"OK-UP:1", "OK-UP:2", "OK-UP:3"}
    assert Counter(p["record_key"] for p in out["party"])["OK-UP:1"] == 2


CSV_BODY = json.dumps({"url": "u", "lo": 0, "hi": 9, "columns": [], "rows": [
    {"PropertyID": "1", "OwnerName": " MANN THOMAS J", "OwnerAddress1": "12 OAK ST",
     "OwnerCity": "TULSA", "OwnerState": "OK", "OwnerZipCode": "741057306"},
    {"PropertyID": "1", "OwnerName": " MANN SUE", "OwnerAddress1": "12 OAK ST",
     "OwnerCity": "TULSA", "OwnerState": "OK", "OwnerZipCode": "741057306"},
    {"PropertyID": "2", "OwnerName": " ACME PLUMBING LLC", "OwnerAddress1": "UNKNOWN",
     "OwnerCity": "OKC", "OwnerState": "OK", "OwnerZipCode": "00000"},
    {"PropertyID": "3", "OwnerName": " LEE ANN", "OwnerAddress1": "5 ELM AVE",
     "OwnerCity": "NORMAN", "OwnerState": "OK", "OwnerZipCode": "73069"},
]})  # fmt: skip


# --- html tables ------------------------------------------------------------------------

INDEX = (
    b'<a id="ctl00_MainContent_lbAdair" href="javascript:__doPostBack()">Adair</a>'
    b'<a id="ctl00_MainContent_lbStLouisCity" href="#">St Louis City</a>'
    b'<a id="other" href="#">Jobs</a><a id="ctl00_MainContent_lbAdair" href="#">Adair</a>'
)
RESULTS = (
    b"<html><table><thead><tr><th>Name</th><th>Last Known Address</th><th>City</th></tr>"
    b'</thead><tbody><tr id="x_ctrl0_trItem"><td>\n AARON DENNIS W\n</td><td> 416 N '
    b"CENTENNIAL ST </td><td>KIRKSVILLE</td></tr>"
    b'<tr id="x_ctrl1_trItem"><td>ADAIR COUNTY UNITED WAY</td><td>304 S FRANKLIN ST</td>'
    b"<td>KIRKSVILLE</td></tr><tr><td>footer</td></tr></tbody></table></html>"
)


def test_link_values_and_table_rows() -> None:
    assert link_values(INDEX.decode(), "ctl00_MainContent_lb") == ["Adair", "St Louis City"]
    rows = table_rows(RESULTS.decode(), ["name", "address", "city"], "_trItem")
    assert rows == [
        {"name": "AARON DENNIS W", "address": "416 N CENTENNIAL ST", "city": "KIRKSVILLE"},
        {"name": "ADAIR COUNTY UNITED WAY", "address": "304 S FRANKLIN ST", "city": "KIRKSVILLE"},
    ]


def test_html_partitions_fetch_and_normalize() -> None:
    cls = by_id("mo.treasurer.unclaimed_owners")
    t = FakeTransport(
        {
            cls.config["html"]["index"]: INDEX,
            "https://treasurer.mo.gov/UCP/Account-Owner-List-Results.aspx": RESULTS,
        }
    )
    adapter = cls(client(t))
    parts = list(adapter.partitions())
    assert parts == [{"value": "Adair"}, {"value": "St Louis City"}]
    f = adapter.fetch(FetchRequest({"value": "St Louis City"}))
    assert f.request.endswith("?Name=St+Louis+City")
    out = rows_of(adapter, f)
    assert len(out["source_record"]) == 2
    people = [p for p in out["party"] if p["party_kind"] != "org"]
    assert [(p["last_name"], p["first_name"], p["middle"]) for p in people] == [
        ("AARON", "DENNIS", "W")]  # fmt: skip
    assert all(a["state"] == "MO" for a in out["address"])
    again = rows_of(adapter, adapter.fetch(FetchRequest({"value": "St Louis City"})))
    assert [r["record_key"] for r in again["source_record"]] == [
        r["record_key"] for r in out["source_record"]]  # fmt: skip  # row-hash keys are stable


# --- socrata ----------------------------------------------------------------------------


def test_socrata_partitions_and_fetch() -> None:
    cls = by_id("ny.nyc.hpd_registration_contacts")
    rows = [{"registrationcontactid": "1", "type": "HeadOfficer", "firstname": "LIANA",
             "lastname": "MACMAHON", "businesshousenumber": "9",
             "businessstreetname": "EAST 38 STREET", "businesscity": "New York",
             "businessstate": "NY", "businesszip": "10016"},
            {"registrationcontactid": "2", "type": "CorporateOwner",
             "corporationname": "RUPPERT HOUSING CO INC", "businesszip": "10016"}]  # fmt: skip
    base = "https://data.cityofnewyork.us/resource/feu5-w2e2.json"

    class T(FakeTransport):
        def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                     ) -> tuple[int, bytes, str]:  # fmt: skip
            if url.startswith(base) and "count" in url:
                return 200, b'[{"n":"120001"}]', "application/json"
            if url.startswith(base):
                return 200, json.dumps(rows).encode(), "application/json"
            return super().__call__(url, headers, timeout)

    adapter = cls(client(T()))
    parts = list(adapter.partitions())
    assert [p["offset"] for p in parts] == ["0", "50000", "100000"]
    out = rows_of(adapter, adapter.fetch(FetchRequest(parts[0])))
    names = {p["raw_name"]: p for p in out["party"]}
    assert names["LIANA MACMAHON"]["last_name"] == "MACMAHON"
    assert names["RUPPERT HOUSING CO INC"]["party_kind"] == "org"
    officer = next(a for a in out["address"] if a["address_id"] == names["LIANA MACMAHON"][
        "address_id"])  # fmt: skip
    assert officer["line1"] == "9 EAST 38 STREET" and officer["zip5"] == "10016"


def test_source_rows() -> None:
    for cls in all_person_list_adapters():
        row = cls().source_row()
        assert row["kind"] in {"tax", "sos", "vessel"} and row["terms_summary"]
        assert row["access_method"] == cls.access_method
    assert by_id("ok.treasurer.unclaimed_property").access_method == "bulk"
    assert by_id("mo.treasurer.unclaimed_owners").access_method == "html"


def test_source_row_carries_use_restrictions_and_robots_date(tmp_path: Path) -> None:
    terms = {"url": "https://x.test", "summary": "test", "checked_on": "2026-11-25",
             "robots_checked_on": "2026-11-24",
             "use_restrictions": ["no_redistribution"]}  # fmt: skip
    cfg = load_person_list(_write(tmp_path, terms=terms))
    cls = type("PL", (PersonListAdapter,), {"source_id": cfg.source_id, "config": cfg})
    row = cls(client=RangeClient()).source_row()
    assert row["terms_summary"] == "RESTRICTED[no_redistribution] test"
    assert row["robots_checked_on"] == "2026-11-24"


def test_every_fixture_normalizes() -> None:
    for cls in all_person_list_adapters():
        for f in sorted((FIX / cls.source_id).glob("*.json")):
            out = rows_of(cls(), fetched(cls.source_id, f.read_bytes()))
            assert out["source_record"] and out["party"], f.name
            with_addr = sum(1 for p in out["party"] if p["address_id"])
            assert with_addr >= 0.75 * len(out["party"]), f.name  # a few rows print none


def test_contract_on_recorded_fixtures(empty_db) -> None:  # type: ignore[no-untyped-def]
    for cls in all_person_list_adapters():
        check_contract(cls, sorted((FIX / cls.source_id).glob("*.json")), empty_db)


# --- arcgis -----------------------------------------------------------------------------


def test_id_windows() -> None:
    from equity.adapters.person_lists import id_windows

    assert id_windows(1, 10, 4) == [(1, 5), (5, 9), (9, 11)]
    assert id_windows(7, 7, 50) == [(7, 8)]


def test_arcgis_partitions_fetch_and_normalize() -> None:
    cls = by_id("ca.orange_county.unclaimed_property")
    layer = cls.config["arcgis"]["layer"]
    feats = [{"attributes": {"OBJECTID": 1, "property_id": 77, "owner_name": "MANN THOMAS J",
                             "owner_address_1": "12 OAK ST", "owner_address_2": None,
                             "owner_city": "IRVINE", "owner_state": "CA",
                             "owner_zip": "92618"}},
             {"attributes": {"OBJECTID": 2, "property_id": 77, "owner_name": "MANN SUE",
                             "owner_address_1": "12 OAK ST", "owner_city": "IRVINE",
                             "owner_state": "CA", "owner_zip": "92618"}},
             {"attributes": {"OBJECTID": 3, "property_id": 78,
                             "owner_name": "ACME PLUMBING LLC", "owner_address_1": "UNKNOWN",
                             "owner_city": "ANAHEIM", "owner_state": "CA"}}]  # fmt: skip
    seen: list[str] = []

    class T(FakeTransport):
        def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                     ) -> tuple[int, bytes, str]:  # fmt: skip
            if url.startswith(layer + "/query"):
                seen.append(url)
                body: dict[str, Any]
                if "outStatistics" in url:
                    body = {"features": [{"attributes": {"MIN": 1, "MAX": 120001}}]}
                else:
                    body = {"features": feats, "exceededTransferLimit": False}
                return 200, json.dumps(body).encode(), "application/json"
            return super().__call__(url, headers, timeout)

    adapter = cls(client(T()))
    parts = list(adapter.partitions())
    assert [(p["lo"], p["hi"]) for p in parts] == [
        ("1", "50001"), ("50001", "100001"), ("100001", "120002")]  # fmt: skip
    f = adapter.fetch(FetchRequest(parts[0]))
    assert "OBJECTID+%3E%3D+1+AND+OBJECTID+%3C+50001" in seen[-1].replace("%20", "+")
    out = rows_of(adapter, f)
    assert {r["record_key"] for r in out["source_record"]} == {"CA-UP:77", "CA-UP:78"}
    people = {p["raw_name"]: p for p in out["party"]}
    assert people["MANN THOMAS J"]["last_name"] == "MANN"
    assert people["ACME PLUMBING LLC"]["party_kind"] == "org"
    addr = {a["address_id"]: a for a in out["address"]}
    assert addr[people["MANN SUE"]["address_id"]]["zip5"] == "92618"
    assert adapter.health().ok


# --- delivered --------------------------------------------------------------------------

DELIVERED_CSV = (
    "PROPERTY_ID,OWNER_NAME,OWNER_STREET_1,OWNER_STREET_2,OWNER_CITY,OWNER_STATE,OWNER_ZIP\n"
    '"1","MANN THOMAS J","12 OAK ST","","FRESNO","CA","93701"\n'
    '"1","MANN SUE","12 OAK ST","","FRESNO","CA","93701"\n'
    '"2","ACME PLUMBING LLC","UNKNOWN","","UNKNOWN","CA",""\n'
    '"3","LEE ANN","5 ELM AVE","APT 2","SAN DIEGO","CA","92101"\n'
)


def _delivered(cls: type[PersonListAdapter], **file_over: Any) -> PersonListAdapter:
    spec = {**cls.config["file"], **file_over}
    cfg = PersonListConfig({**cls.config.data, "file": spec}, cls.config.parties)
    sub: type[PersonListAdapter] = type("T", (cls,), {"config": cfg})
    return sub()


def test_delivered_awaits_a_drop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    adapter = by_id("ca.sco.unclaimed_property")()
    with pytest.raises(RuntimeError, match="nothing delivered yet"):
        list(adapter.partitions())
    report = adapter.health()
    assert not report.ok and "nothing delivered" in report.detail


def test_delivered_zip_windows_cover_every_row_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import zipfile

    monkeypatch.chdir(tmp_path)
    drop = tmp_path / "data" / "manual" / "ca.sco.unclaimed_property"
    drop.mkdir(parents=True)
    with zipfile.ZipFile(drop / "From_10_To_100.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("From_10_To_100.csv", DELIVERED_CSV)
        z.writestr("Record_Layout.csv", "not,data\n")
    (drop / "README.md").write_text("how this got here")
    adapter = _delivered(by_id("ca.sco.unclaimed_property"), chunk_bytes=60)
    parts = list(adapter.partitions())
    assert {p["member"] for p in parts} == {"From_10_To_100.csv"}  # the layout is skipped
    assert [p["lo"] for p in parts] == [str(n) for n in range(0, len(DELIVERED_CSV), 60)]
    names: list[str] = []
    for p in parts:
        body = json.loads(adapter.fetch(FetchRequest(p)).content)
        assert body["columns"][:2] == ["PROPERTY_ID", "OWNER_NAME"]
        names += [r["OWNER_NAME"] for r in body["rows"]]
    assert names == ["MANN THOMAS J", "MANN SUE", "ACME PLUMBING LLC", "LEE ANN"]
    whole = adapter.fetch(FetchRequest({"path": str(drop / "From_10_To_100.zip"),
                                        "member": "From_10_To_100.csv", "lo": "0"}))  # fmt: skip
    out = rows_of(adapter, whole)
    assert {r["record_key"] for r in out["source_record"]} == {"CA-UP:1", "CA-UP:2", "CA-UP:3"}
    lee = next(p for p in out["party"] if p["raw_name"] == "LEE ANN")
    addr = next(a for a in out["address"] if a["address_id"] == lee["address_id"])
    assert (addr["line1"], addr["city"], addr["zip5"]) == ("5 ELM AVE APT 2", "SAN DIEGO", "92101")
    assert adapter.health().ok


def test_delivered_xlsx_and_fixed_width(tmp_path: Path) -> None:
    import zipfile

    from equity.adapters.person_lists import canon, fixed_rows, xlsx_rows

    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    shared = (f'<sst {ns}><si><t>Owner Name</t></si><si><t>Owner Address 1</t></si>'
              f'<si><t>MANN THOMAS J</t></si></sst>')  # fmt: skip
    sheet = (f'<worksheet {ns}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c>'
             '<c r="B1" t="s"><v>1</v></c><c r="C1" t="inlineStr"><is><t>Zip</t></is></c></row>'
             '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="C2"><v>82001</v></c></row>'
             '</sheetData></worksheet>')  # fmt: skip
    path = tmp_path / "finder_list.xlsx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/sharedStrings.xml", shared)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    with path.open("rb") as f:
        assert list(xlsx_rows(f)) == [["Owner Name", "Owner Address 1", "Zip"],
                                      ["MANN THOMAS J", "", "82001"]]  # fmt: skip
    adapter = _delivered(by_id("ca.sco.unclaimed_property"), include=r"\.xlsx$")
    body = json.loads(adapter.fetch(FetchRequest({"path": str(path)})).content)
    assert body["rows"] == [{"OWNER_NAME": "MANN THOMAS J", "OWNER_ADDRESS_1": "", "ZIP": "82001"}]
    assert canon("Former  Owner Address Line 1") == "FORMER_OWNER_ADDRESS_LINE_1"
    assert canon("﻿Zip+4") == "ZIP_4"
    assert fixed_rows(["MANN      12 OAK ST  \n", "   \n"], [("LAST", 10), ("ST", 11)]) == [
        {"LAST": "MANN", "ST": "12 OAK ST"}]  # fmt: skip


@pytest.mark.parametrize(
    ("over", "match"),
    [
        ({"api": "arcgis", "arcgis": {"window": 5}}, "arcgis needs layer"),
        ({"api": "delivered", "file": {"include": "x"}}, "file needs request_url"),
        ({"api": "delivered"}, "missing"),
    ],
)
def test_arcgis_and_delivered_config_errors(tmp_path: Path, over: dict[str, Any],
                                            match: str) -> None:  # fmt: skip
    with pytest.raises(PersonListConfigError, match=match):
        load_person_list(_write(tmp_path, **over))


# --- pdf_table (East: New Jersey, Ohio), csv whole, one-line addresses --------------------


def _list_pdf(lines: list[tuple[float, float, str]]) -> bytes:
    from .test_liens import _pdf

    return _pdf(lines)


# An Ohio-style county list: the title and header, a holder name that wraps onto a second
# line, an address centered left of its header, a repeated header, a row without a city.
OH_LINES: list[tuple[float, float, str]] = [
    (128, 665, "2026 Ashland County Unclaimed Funds List"),
    (135, 634, "NAME"), (282, 634, "ADDRESS"), (451, 634, "CITY"),
    (78, 620, "401K SALARY RETIREMENT"), (275, 620, "600 UNION ST"), (491, 620, "ASHLAND"),
    (78, 607, "SAVINGS PLAN TRUS"),
    (78, 593, "ABEL JESSICA"), (245, 593, "831 TOWNSHIP ROAD 2104"), (464, 593, "BECKETT RIDGE"),
    (135, 578, "NAME"), (282, 578, "ADDRESS"), (451, 578, "CITY"),
    (78, 563, "ABER SHAWN"), (276, 563, "UNKNOWN"), (491, 563, "ASHLAND"),
    (78, 548, "NO CITY ROW"), (276, 548, "1 ELM ST"),
]  # fmt: skip


def test_pdf_rows_cut_columns_wrap_and_require() -> None:
    from equity.adapters.pdf_lists import pdf_rows

    rows = pdf_rows(_list_pdf(OH_LINES), ["name", "address", "city"], [150, 440], "NAME",
                    wrap="name", require={"name": r"\S", "city": r"\S"})  # fmt: skip
    assert rows == [
        {"name": "401K SALARY RETIREMENT SAVINGS PLAN TRUS", "address": "600 UNION ST",
         "city": "ASHLAND"},
        {"name": "ABEL JESSICA", "address": "831 TOWNSHIP ROAD 2104", "city": "BECKETT RIDGE"},
        {"name": "ABER SHAWN", "address": "UNKNOWN", "city": "ASHLAND"},
    ]  # fmt: skip
    with pytest.raises(ValueError, match="one more name"):
        pdf_rows(b"", ["a"], [1.0], "NAME")


NJ_LINES: list[tuple[float, float, str]] = [
    (14, 1274, "2026 Newly Reported Properties (As of August 18, 2026)"),
    (14, 1198, "NAME"), (503, 1198, "ADDRESS"), (706, 1198, "CITY"), (907, 1198, "PROPERTY ID"),
    (14, 1182, "ARCIDIACONO, JOSEPH"), (503, 1182, "254 S BROADWAY"), (706, 1182, "PENNSVILLE"),
    (923, 1182, "47259384"),
    (14, 1167, "ASHER-KELL DAWN M & ECRET TROY"), (503, 1167, "190 E BROADWAY APT B"),
    (706, 1167, "SALEM"), (923, 1167, "47530698"),
    (14, 1152, "ASHBROOK HOME INC"), (503, 1152, "ATTN EARL L WALKER"), (706, 1152, "WOODSTOWN"),
    (923, 1152, "45034723"),
    (168, 1100, "*If your name does not appear on this list, we may still be holding"),
]  # fmt: skip
NJ_INDEX = (b'<a href="pdf/counties/SALEM.pdf">SALEM</a> <a href="pdf/counties/CAPEMAY.pdf">'
            b'CAPE MAY</a> <a href="pdf/counties/SALEM.pdf">again</a>')  # fmt: skip


def test_pdf_table_partitions_fetch_and_normalize() -> None:
    cls = by_id("nj.treasury.unclaimed_owners")
    base = "https://www.nj.gov/treasury/unclaimed-property/"
    t = FakeTransport({cls.config["pdf"]["index"]: NJ_INDEX,
                       base + "pdf/counties/SALEM.pdf": _list_pdf(NJ_LINES)})  # fmt: skip
    adapter = cls(client(t))
    assert list(adapter.partitions()) == [{"value": "SALEM"}, {"value": "CAPEMAY"}]
    f = adapter.fetch(FetchRequest({"value": "SALEM"}))
    assert f.request == base + "pdf/counties/SALEM.pdf"
    body = json.loads(f.content)
    assert [r["property_id"] for r in body["rows"]] == ["47259384", "47530698", "45034723"]
    assert body["rows"][0]["county"] == "SALEM"
    out = rows_of(adapter, f)
    assert {r["record_key"] for r in out["source_record"]} == {
        "NJ-UP:47259384", "NJ-UP:47530698", "NJ-UP:45034723"}  # fmt: skip
    people = {p["raw_name"]: p for p in out["party"]}
    assert (people["ARCIDIACONO, JOSEPH"]["last_name"],
            people["ARCIDIACONO, JOSEPH"]["first_name"]) == ("ARCIDIACONO", "JOSEPH")  # fmt: skip
    assert people["ECRET TROY"]["last_name"] == "ECRET"  # joint owners split on '&'
    assert people["ASHER-KELL DAWN M"]["middle"] == "M"
    assert people["ASHBROOK HOME INC"]["party_kind"] == "org"
    assert {a["state"] for a in out["address"]} == {"NJ"}
    assert {a["city"] for a in out["address"]} == {"PENNSVILLE", "SALEM", "WOODSTOWN"}
    one = json.loads(adapter.fetch(FetchRequest({"value": "SALEM", "limit": "1"})).content)
    assert len(one["rows"]) == 1
    assert adapter.health().ok


def test_pdf_index_unreachable_falls_back_to_values() -> None:
    cls = by_id("oh.commerce.unclaimed_funds_owners")
    url = cls.config["pdf"]["url"].replace("{value}", "7.%20July/Ashland.pdf")
    t = FakeTransport({url: _list_pdf(OH_LINES)})  # the index answers 404
    adapter = cls(client(t))
    parts = list(adapter.partitions())
    assert parts[0] == {"value": "3.%20March/Belmont_County.pdf"}
    assert len(parts) == len(cls.config["pdf"]["values"])
    body = json.loads(adapter.fetch(FetchRequest({"value": "7. July/Ashland.pdf"})).content)
    assert body["url"] == url and body["county_file"] == "Ashland"
    out = rows_of(adapter, fetched(cls.source_id, body))
    abel = next(p for p in out["party"] if p["raw_name"] == "ABEL JESSICA")
    assert (abel["last_name"], abel["first_name"]) == ("ABEL", "JESSICA")
    aber = next(p for p in out["party"] if p["raw_name"] == "ABER SHAWN")
    addr = next(a for a in out["address"] if a["address_id"] == aber["address_id"])
    assert (addr["line1"], addr["city"], addr["state"]) == (None, "ASHLAND", "OH")
    no_values = PersonListConfig({**cls.config.data, "pdf": {**cls.config["pdf"], "values": []}},
                                 cls.config.parties)  # fmt: skip
    with pytest.raises(RuntimeError, match="HTTP 404"):
        list(type("T", (cls,), {"config": no_values})(client(t)).partitions())


def test_pdf_table_config_errors(tmp_path: Path) -> None:
    with pytest.raises(PersonListConfigError, match="pdf needs url, columns and cuts"):
        load_person_list(_write(tmp_path, api="pdf_table", pdf={"url": "x", "columns": ["n"]}))


def test_last_first_comma_reads_either_order() -> None:
    assert split_name("ARCIDIACONO, JOSEPH A", "last_first_comma")["middle"] == "A"
    p = split_name("ARNDT NORA", "last_first_comma")
    assert (p["last"], p["first"]) == ("ARNDT", "NORA")


def test_csv_whole_file_window() -> None:
    cls = by_id("wi.madison.outstanding_checks")
    data = (
        b"Check,Vendor,Name,Amount,Check Date,Address Line 1,Address Line 2,Address Line 3,"
        b"City,State,Zip,Year\n"
        b"1,9,ANN LEE,5.00,01/04/2024,12 OAK ST,APT 2,,MADISON,WI,53703,2024\n"
        b'2,9,"SMITH, BO",8.36,01/26/2024,350 S HAMILTON ST,,,MADISON,WI,53703-0577,2024\n'
    )
    t = FakeTransport({cls.config["csv"]["url"]: data})  # no Range: the server answers 200
    adapter = cls(client(t))
    parts = list(adapter.partitions())
    assert parts == [{"url": cls.config["csv"]["url"], "lo": "0", "hi": "8000000"}]
    body = json.loads(adapter.fetch(FetchRequest(parts[0])).content)
    assert [r["Check"] for r in body["rows"]] == ["1", "2"]
    lo = str(data.index(b"\n2,") + 1)
    second = json.loads(adapter.fetch(FetchRequest({"lo": lo, "hi": "8000000"})).content)
    assert [r["Check"] for r in second["rows"]] == ["2"]  # the line starting in the window
    out = rows_of(adapter, adapter.fetch(FetchRequest(parts[0])))
    ann = next(p for p in out["party"] if p["raw_name"] == "ANN LEE")
    addr = next(a for a in out["address"] if a["address_id"] == ann["address_id"])
    assert (addr["line1"], addr["zip5"]) == ("12 OAK ST APT 2", "53703")
    assert all(rng is None for _, rng in t.calls)
    assert adapter.health().ok


def test_one_line_address_with_comma_before_zip() -> None:
    spec = AddressSpec(line="a")
    addr = address_of({"a": "1110 MCKIMMON VIEW CT, RALEIGH, NC, 27606-4999"}, spec)
    assert addr is not None and (addr["line1"], addr["city"], addr["state"], addr["zip5"]) == (
        "1110 MCKIMMON VIEW CT", "RALEIGH", "NC", "27606")  # fmt: skip
    cls = by_id("nc.raleigh.uncashed_checks")
    body = {"lo": 0, "hi": 9, "rows": [{"FID": 1, "Name1": "JOSHI,JAY",
                                        "Address": "12 OAK ST, RALEIGH, NC, 27606",
                                        "PYMNT_ID_Ref": "0000282622"}]}  # fmt: skip
    out = rows_of(cls(), fetched(cls.source_id, body))
    (p,) = out["party"]
    assert (p["last_name"], p["first_name"]) == ("JOSHI", "JAY")
    assert out["source_record"][0]["record_key"] == "RAL-CHK:0000282622"
    assert out["address"][0]["city"] == "RALEIGH"
