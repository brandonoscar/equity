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
