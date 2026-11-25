"""License datasets (config/licenses/*.yaml): config checks, names, addresses, records, related
holders, planning and fetch ranges. Offline."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from equity.adapters.base import REGISTRY, Fetched, FetchRequest, register
from equity.adapters.http import Response
from equity.adapters.licenses import (
    LICENSE_DIR,
    AddressSpec,
    HolderSpec,
    LicenseAdapter,
    LicenseConfigError,
    adapter_class,
    address_of,
    all_license_adapters,
    holder_of,
    holders_of,
    load_license,
    parse_date,
)
from equity.adapters.rows import canonical_json

# Until equity.adapters.registry lists the license adapters, register them here so the
# contract, privacy and fixture-directory tests in this session see them.
for _cls in all_license_adapters():
    if _cls not in REGISTRY:
        register(_cls)

FIX = Path(__file__).parents[1] / "fixtures" / "adapters"
AT = datetime(2026, 11, 25, tzinfo=UTC)

BASE = {
    "source_id": "zz.test.licenses", "state": "ZZ", "jurisdiction": "99", "portal": "https://x.test",
    "dataset": "aaaa-1111", "key": "num", "id_prefix": "ZZ:", "terms_url": "https://x.test",
    "terms_summary": "test", "checked_on": "2026-11-25",
    "license": {"name": "dba", "type": "kind", "status": "status", "issued_on": "issued",
                "address": {"street": "street", "city": "city", "state": "st", "zip": "zip"}},
    "holders": [{"role": "other", "title": "LICENSEE", "name": "holder", "last_first": True,
                 "address": {"street": "street", "city": "city", "state": "st", "zip": "zip"}}],
    "pii_fields": ["holder", "dba", "street"],
}  # fmt: skip


def _adapter(tmp_path: Path, **over: Any) -> type[LicenseAdapter]:
    data = {**BASE, **over}
    path = tmp_path / f"{data['source_id']}.yaml"
    path.write_text(yaml.safe_dump(data))
    return adapter_class(load_license(path))


def _norm(cls: type[LicenseAdapter], body: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    f = Fetched(cls.source_id, "https://x.test", AT, 200, canonical_json(body), "")
    return [(r.table, dict(r.row)) for r in cls().normalize(f)]


def test_every_config_loads_with_unique_prefixes() -> None:
    adapters = all_license_adapters()
    paths = sorted(LICENSE_DIR.glob("*.yaml"))
    assert len(adapters) == len(paths) >= 30
    prefixes = Counter(c.config.id_prefix for c in adapters)
    assert max(prefixes.values()) == 1
    for cls in adapters:
        assert cls.config.pii_fields, cls.source_id
        assert cls.config.state in cls.source_id.upper().split(".")[0]
        assert sorted((FIX / cls.source_id).glob("*.json")), f"{cls.source_id}: no fixture"


@pytest.mark.parametrize(
    ("change", "problem"),
    [({"id_prefix": ""}, "id_prefix"),
     ({"holders": [{"role": "owner", "name": "x"}]}, "unknown business role"),
     ({"holders": [{"parts": {"first": "f"}}]}, "parts needs 'last'"),
     ({"holders": [{"title": "X"}]}, "needs name or parts"),
     ({"holders": [{"name": "x", "split": ",", "last_first": True}]}, "split"),
     ({"holders": []}, "needs holders or related"),
     ({"license": {"name": "x", "expiry": "y"}}, "unknown license keys"),
     ({"licence": {}}, "unknown keys"),
     ({"related": [{"dataset": "b", "key": "num", "holder": {"name": "n"},
                    "role_map": {"BOSS": "boss"}}]}, "unknown business role"),
     ({"fetch": "ftp"}, "unknown fetch"),
     ({"fetch": "csv"}, "needs urls"),
     ({"fetch": "csv", "urls": ["https://x.test/a.csv"],
       "related": [{"dataset": "b", "key": "num", "holder": {"name": "n"}}]}, "no related"),
     ({"dataset": ""}, "needs portal and dataset"),
     ({"cost_model": "cheap"}, "cost_model")],
)  # fmt: skip
def test_bad_configs_are_refused(tmp_path: Path, change: dict[str, Any], problem: str) -> None:
    with pytest.raises(LicenseConfigError, match=problem):
        _adapter(tmp_path, **change)


def test_file_name_must_match_source_id(tmp_path: Path) -> None:
    (tmp_path / "other.yaml").write_text(yaml.safe_dump(BASE))
    with pytest.raises(LicenseConfigError, match="source_id"):
        load_license(tmp_path / "other.yaml")


def test_dates() -> None:
    assert parse_date("2021-06-21T07:00:00.000") == date(2021, 6, 21)
    assert parse_date("9/2/1996") == date(1996, 9, 2)
    assert parse_date("19271210") == date(1927, 12, 10)
    assert parse_date("20140814.0") == date(2014, 8, 14)
    assert parse_date("13/40/2020") is None
    assert parse_date("17-MAR-00") == date(2000, 3, 17)  # Florida DBPR
    assert parse_date("13-apr-87") == date(1987, 4, 13)
    assert parse_date("01-JAN-2019") == date(2019, 1, 1)
    assert parse_date("31-FOO-20") is None and parse_date("31-FEB-20") is None
    assert parse_date("") is None and parse_date(None) is None and parse_date("soon") is None


def test_addresses() -> None:
    csz = AddressSpec(street=("a1", "a2"), city_state_zip="csz")
    a = address_of({"a1": "1 MAIN ST", "a2": "STE 2", "csz": "SAN ANGELO TX 76903-1004"}, csz)
    assert a is not None and (a["line1"], a["city"], a["state"], a["zip5"]) == (
        "1 MAIN ST STE 2", "SAN ANGELO", "TX", "76903")  # fmt: skip
    line = AddressSpec(line="p", city="c")
    a = address_of({"p": "9-17 NW 6TH AVE PORTLAND OR  97209", "c": "PORTLAND"}, line)
    assert a is not None and (a["line1"], a["city"], a["state"], a["zip5"]) == (
        "9 17 NW 6TH AVE", "PORTLAND", "OR", "97209")  # fmt: skip
    a = address_of({"p": "1 A ST, SALEM, OR 97301"}, AddressSpec(line="p"))
    assert a is not None and (a["city"], a["state"]) == ("SALEM", "OR")
    spec = AddressSpec(street=("s",), city="c", state="st", zip="z")
    a = address_of({"s": "1 B ST", "c": "X", "st": "New York", "z": "80020.0"}, spec)
    assert a is not None and (a["state"], a["zip5"]) == ("NY", "80020")
    a = address_of({"s": "1 B ST", "st": "ST. JAMES", "z": "0000"}, spec)
    assert a is not None and a["state"] is None and a["zip5"] is None
    assert address_of({}, spec) is None and address_of({"s": "x"}, None) is None
    with pytest.raises(LicenseConfigError, match="unknown address keys"):
        AddressSpec.parse({"street": "s", "town": "t"})


def test_holder_names() -> None:
    lf = HolderSpec(name=("n",), last_first=True)
    who, parts = holder_of({"n": "Ochoa, Eric James"}, lf)  # type: ignore[misc]
    assert who == "Ochoa, Eric James"
    assert (parts["first_name"], parts["middle"], parts["last_name"]) == ("Eric", "James", "Ochoa")
    _, parts = holder_of({"n": "ACME, LLC"}, lf)  # type: ignore[misc]
    assert parts["last_name"] is None  # an organization is not split
    ps = HolderSpec(parts={"first": "f", "middle": "m", "last": "l", "suffix": "s"})
    who, parts = holder_of({"f": "ANN", "l": "LEE", "s": "JR", "m": ""}, ps)  # type: ignore[misc]
    assert who == "ANN LEE JR" and parts["suffix"] == "JR" and parts["middle"] is None
    assert holder_of({"f": "ANN"}, ps) == ("ANN", dict.fromkeys(
        ("first_name", "middle", "last_name", "suffix")))  # fmt: skip
    for nobody in ("0", "`", " - ", "N/A", "", None):
        assert holder_of({"n": nobody}, lf) is None
    fallback = HolderSpec(name=("org",), parts={"last": "l"})
    assert holder_of({"org": "0", "l": "LEE"}, fallback) == ("LEE", {
        "first_name": None, "middle": None, "last_name": "LEE", "suffix": None})  # fmt: skip
    split = HolderSpec(name=("o",), split=",")
    assert [h[0] for h in holders_of({"o": "Troy  Binns, Sean Mahoney, , 0"}, split)] == [
        "Troy Binns", "Sean Mahoney"]  # fmt: skip


def test_license_record_business_and_holder(tmp_path: Path) -> None:
    cls = _adapter(tmp_path)
    rows = _norm(cls, {"rows": [
        {"num": "7", "dba": "ACE PLUMBING", "holder": "LEE, ANN Q", "kind": "Plumber",
         "status": "Active", "issued": "2001-02-03", "street": "1 A ST", "city": "AUSTIN",
         "st": "TX", "zip": "78701"},
        {"num": "8", "holder": "BAKER CO INC", "kind": "Plumber", "issued": "2099-01-01"},
        {"num": "9", "dba": "0", "holder": "-"},
        {"dba": "NO KEY", "holder": "X"},
    ]})  # fmt: skip
    t = Counter(table for table, _ in rows)
    assert t["source_record"] == 3 and t["business"] == 2 and t["data_issue"] == 1
    biz = {r["sos_id"]: r for tb, r in rows if tb == "business"}
    ace = biz["ZZ:7"]
    assert (ace["name"], ace["status"], ace["formed_on"]) == ("ACE PLUMBING", "Active",
                                                             date(2001, 2, 3))  # fmt: skip
    assert ace["principal_address_id"] is not None
    baker = biz["ZZ:8"]  # no trade name: the holder names the license; future date dropped
    assert baker["name"] == "BAKER CO INC" and baker["org_form"] == "INC"
    assert baker["formed_on"] is None and baker["valid_from"] == AT.date()
    roles = {r["sos_id"]: r for tb, r in rows if tb == "business_role"}
    assert roles["ZZ:7"]["title"] == "LICENSEE: Plumber" and roles["ZZ:7"]["role"] == "other"
    assert roles["ZZ:7"]["valid_from"] == date(2001, 2, 3)
    ann = next(r for tb, r in rows if tb == "party" and r["raw_name"] == "LEE, ANN Q")
    assert (ann["first_name"], ann["middle"], ann["last_name"]) == ("ANN", "Q", "LEE")
    assert ann["address_id"] == ace["principal_address_id"]
    issue = next(r for tb, r in rows if tb == "data_issue")
    assert issue["issue_code"] == "missing_license_name"


def test_rows_sharing_a_record_key_make_one_license(tmp_path: Path) -> None:
    cls = _adapter(
        tmp_path, record_key=["num", "kind"],
        license={**BASE["license"], "latest_by": "issued"},  # type: ignore[dict-item]
        holders=[{"role": "other", "title": "ASSOCIATE", "title_field": "assoc",
                  "with_type": False, "name": "holder"}],
    )  # fmt: skip
    body = {"rows": [
        {"num": "1", "kind": "A", "dba": "OLD NAME", "holder": "ANN LEE", "assoc": "MGR",
         "issued": "2001-01-01"},
        {"num": "1", "kind": "A", "dba": "NEW NAME", "holder": "BO RAY", "assoc": "OWN",
         "issued": "2010-01-01"},
        {"num": "1", "kind": "B", "dba": "OTHER TYPE", "holder": "ANN LEE"},
    ]}  # fmt: skip
    rows = _norm(cls, body)
    biz = {r["sos_id"]: r["name"] for tb, r in rows if tb == "business"}
    assert biz == {"ZZ:1|A": "NEW NAME", "ZZ:1|B": "OTHER TYPE"}  # latest row wins
    titles = sorted((r["sos_id"], r["title"]) for tb, r in rows if tb == "business_role")
    assert titles == [("ZZ:1|A", "MGR"), ("ZZ:1|A", "OWN"), ("ZZ:1|B", "ASSOCIATE")]
    flipped = _norm(cls, {"rows": body["rows"][::-1]})
    assert sorted(map(repr, rows)) == sorted(map(repr, flipped))


def test_related_holders_roles_and_dates(tmp_path: Path) -> None:
    cls = _adapter(tmp_path, holders=[], related=[{
        "dataset": "bbbb-2222", "key": "num",
        "holder": {"role": "other", "title": "OWNER", "with_type": False, "name": "who",
                   "last_first": True},
        "role_field": "t", "role_map": {"President": "officer"},
        "valid_from": "start", "valid_to": "end"}])  # fmt: skip
    rows = _norm(cls, {"rows": [{"num": "5", "dba": "X LLC"}], "bbbb-2222": [
        {"num": "5", "who": "LEE, ANN", "t": "PRESIDENT", "start": "2005-01-01",
         "end": "2004-01-01"},
        {"num": "5", "who": "RAY, BO", "t": "Partner", "start": "2001-01-01",
         "end": "2003-06-30"},
        {"num": "5", "who": "RAY, BO", "t": "Partner", "start": "2010-01-01"},
        {"num": "6", "who": "NOBODY, HERE"},
    ]})  # fmt: skip
    roles = sorted((r["role"], r["title"], str(r["valid_from"]), str(r["valid_to"]))
                   for tb, r in rows if tb == "business_role")  # fmt: skip
    assert roles == [
        ("officer", "PRESIDENT", "2005-01-01", "None"),  # end before start: dropped
        ("other", "Partner", "2001-01-01", "2003-06-30"),
        ("other", "Partner", "2010-01-01", "None"),  # a second term of the same person
    ]
    parties = [r["raw_name"] for tb, r in rows if tb == "party"]
    assert sorted(parties) == ["LEE, ANN", "RAY, BO"]  # one party row per name and role


class FakeSocrata:
    retries = 0
    backoff_s = 0.0

    def __init__(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self.data = data
        self.queries: list[tuple[str, dict[str, str]]] = []

    def sleep(self, s: float) -> None:
        pass

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        ds = url.rsplit("/", 1)[-1].removesuffix(".json")
        p = dict(params or {})
        self.queries.append((ds, p))
        rows = self.data.get(ds, [])
        if p.get("$select", "").startswith("distinct"):
            w = p["$where"]
            last = w.split("> '")[1].rstrip("'") if "> '" in w else None
            keys = sorted({r["k"] for r in rows})
            rows = [{"k": k} for k in keys if last is None or k > last][: int(p["$limit"])]
        else:
            off, lim = int(p.get("$offset", "0")), int(p.get("$limit", "50000"))
            rows = rows[off : off + lim]
        return Response(url, 200, json.dumps(rows).encode(), "application/json", AT)


def test_partitions_and_numeric_keys_compare_as_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import equity.adapters.licenses as lic

    monkeypatch.setattr(lic, "PLAN_KEYS", 2)
    related = [{"dataset": "bbbb-2222", "key": "acct", "holder": {"name": "who"}}]
    cls = _adapter(tmp_path, key="acct", key_is_number=True, related=related)
    fake = FakeSocrata({"aaaa-1111": [{"k": k} for k in ("10", "11", "12", "20", "21")]})
    parts = list(cls(fake).partitions())  # type: ignore[arg-type]
    assert parts == [{"lo": "10", "hi": "12"}, {"lo": "12", "hi": "21"}, {"lo": "21", "hi": ""}]
    assert fake.queries[0][1]["$where"] == "acct IS NOT NULL"
    assert fake.queries[1][1]["$where"] == "acct::text > '11'"
    fake = FakeSocrata({"aaaa-1111": [{"acct": "10", "dba": "X"}]})
    body = json.loads(cls(fake).fetch(FetchRequest({"lo": "1", "hi": "2"})).content)  # type: ignore[arg-type]
    assert [(ds, q["$where"]) for ds, q in fake.queries] == [
        ("aaaa-1111", "acct::text >= '1' AND acct::text < '2'"),
        ("bbbb-2222", "acct::text >= '1' AND acct::text < '2'")]  # fmt: skip
    assert set(body) == {"portal", "where", "rows", "bbbb-2222"}
    fake = FakeSocrata({"aaaa-1111": [{"acct": "10", "dba": "X"}]})
    cls(fake).fetch(FetchRequest({"lo": "1", "limit": "1"}))  # type: ignore[arg-type]
    assert fake.queries[0][1]["$limit"] == "1"
    assert fake.queries[1][1]["$where"] == "acct::text in ('10')"


def test_health_and_source_row(tmp_path: Path) -> None:
    cls = _adapter(tmp_path)
    assert cls(FakeSocrata({"aaaa-1111": [{"num": "1"}]})).health().ok  # type: ignore[arg-type]
    assert not cls(FakeSocrata({})).health().ok  # type: ignore[arg-type]
    row = cls().source_row()
    assert row["kind"] == "sos" and row["base_url"] == "https://x.test/resource/aaaa-1111.json"


def test_terms_restrictions_and_cost_reach_the_source_row(tmp_path: Path) -> None:
    cls = _adapter(tmp_path, use_restrictions=["no_redistribution", "internal_use_only"],
                   cost_model="fee", robots_checked_on=date(2026, 11, 20))  # fmt: skip
    row = cls().source_row()
    assert row["terms_summary"] == "RESTRICTED[internal_use_only,no_redistribution] test"
    assert row["cost_model"] == "fee" and row["robots_checked_on"] == date(2026, 11, 20)
    assert row["terms_checked_on"] == BASE["checked_on"] and row["access_method"] == "api"
    plain = _adapter(tmp_path, source_id="zz.test.plain")().source_row()
    assert plain["terms_summary"] == "test" and plain["cost_model"] == "free"
    assert plain["robots_checked_on"] == BASE["checked_on"]


class FakeFiles:
    """Files by URL, served whole by get() and by byte range by get_range() (206; 416 past
    the end; the whole file with 200 when `ranges` is off)."""

    retries = 0
    backoff_s = 0.0

    def __init__(self, files: dict[str, bytes], ranges: bool = True) -> None:
        self.files = files
        self.ranges = ranges
        self.calls: list[tuple[str, int, int] | str] = []

    def sleep(self, s: float) -> None:
        pass

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        self.calls.append(url)
        if url not in self.files:
            return Response(url, 404, b"", "text/html", AT)
        return Response(url, 200, self.files[url], "text/csv", AT)

    def get_range(self, url: str, first: int, last: int) -> Response:
        self.calls.append((url, first, last))
        data = self.files.get(url)
        if data is None:
            return Response(url, 404, b"", "text/html", AT)
        if not self.ranges:
            return Response(url, 200, data, "text/csv", AT)
        if first >= len(data):
            return Response(url, 416, b"", "text/plain", AT)
        return Response(url, 206, data[first : last + 1], "text/csv", AT)


CSV_URL = "https://x.test/lic.csv"
HEADERLESS = (
    b'"06","CBC","LEE, ANN Q","ACE BUILDERS LLC","1 A ST","AUSTIN","TX","78701",'
    b'"0001","C","01/02/2003"\n'
    b'"06","CGC","RAY, BO","","2 B ST","DALLAS","TX","75201","0002","C",""\n'
    b'"06","CBC","DOE, JO","","3 C ST","WACO","TX","76701","0003","C","17-MAR-99"\n'
)
COLUMNS = ["board", "occ", "holder", "dba", "street", "city", "st", "zip", "num", "status",
           "issued"]  # fmt: skip


def _csv_adapter(tmp_path: Path, **over: Any) -> type[LicenseAdapter]:
    base = {"fetch": "csv", "urls": [CSV_URL], "columns": COLUMNS, "record_key": ["occ", "num"],
            "license": {**BASE["license"], "name": ["dba", "holder"], "type": "occ"},  # type: ignore[dict-item]
            "encoding": "latin-1"}  # fmt: skip
    return _adapter(tmp_path, **{**base, **over})


def test_csv_source_reads_a_headerless_file(tmp_path: Path) -> None:
    cls = _csv_adapter(tmp_path)
    assert cls.access_method == "bulk"
    fake = FakeFiles({CSV_URL: HEADERLESS})
    a = cls(fake)  # type: ignore[arg-type]
    assert list(a.partitions()) == [{"url": CSV_URL}]
    f = a.fetch(FetchRequest({"url": CSV_URL}))
    assert fake.calls == [CSV_URL] and f.request == CSV_URL
    body = json.loads(f.content)
    assert body["url"] == CSV_URL and [r["num"] for r in body["rows"]] == ["0001", "0002", "0003"]
    rows = _norm(cls, body)
    biz = {r["sos_id"]: r for tb, r in rows if tb == "business"}
    assert set(biz) == {"ZZ:CBC|0001", "ZZ:CGC|0002", "ZZ:CBC|0003"}
    assert biz["ZZ:CBC|0001"]["name"] == "ACE BUILDERS LLC"
    assert biz["ZZ:CBC|0001"]["formed_on"] == date(2003, 1, 2)
    assert biz["ZZ:CBC|0003"]["formed_on"] == date(1999, 3, 17)
    ann = next(r for tb, r in rows if tb == "party" and r["raw_name"] == "LEE, ANN Q")
    assert (ann["first_name"], ann["last_name"]) == ("ANN", "LEE")
    row = cls().source_row()
    assert row["base_url"] == CSV_URL and row["access_method"] == "bulk"


def test_csv_fixture_reads_the_first_bytes_and_drops_a_cut_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import equity.adapters.licenses as lic

    cls = _csv_adapter(tmp_path)
    monkeypatch.setattr(lic, "FIXTURE_BYTES", len(HEADERLESS) - 5)
    fake = FakeFiles({CSV_URL: HEADERLESS})
    body = json.loads(cls(fake).fetch(FetchRequest({"limit": "5"})).content)  # type: ignore[arg-type]
    assert [r["num"] for r in body["rows"]] == ["0001", "0002"]  # the third line was cut off
    assert fake.calls == [(CSV_URL, 0, len(HEADERLESS) - 6)]
    body = json.loads(cls(fake).fetch(FetchRequest({"limit": "1"})).content)  # type: ignore[arg-type]
    assert len(body["rows"]) == 1
    whole = FakeFiles({CSV_URL: HEADERLESS}, ranges=False)  # ranges ignored: the whole file
    body = json.loads(cls(whole).fetch(FetchRequest({"limit": "5"})).content)  # type: ignore[arg-type]
    assert len(body["rows"]) == 3


def test_csv_header_row_names_the_columns(tmp_path: Path) -> None:
    data = b"\xef\xbb\xbfnum,holder ,dba,occ\n7,ANN LEE,,X\n,NO KEY,,X\n\n8,BO RAY,BR CO,Y\n"
    cls = _csv_adapter(tmp_path, columns=None, encoding="utf-8-sig")
    body = json.loads(cls(FakeFiles({CSV_URL: data})).fetch(FetchRequest({})).content)  # type: ignore[arg-type]
    assert body["rows"][0] == {"num": "7", "holder": "ANN LEE", "dba": "", "occ": "X"}
    assert len(body["rows"]) == 3  # the blank line is skipped
    names = {r["name"] for tb, r in _norm(cls, body) if tb == "business"}
    assert names == {"ANN LEE", "BR CO"}  # the row without a key makes no license


def test_csv_byte_windows_cover_the_file_once(tmp_path: Path) -> None:
    data = b"num,holder,occ\n" + b"".join(b"%d,P%d,X\n" % (i, i) for i in range(1, 41))
    cls = _csv_adapter(tmp_path, columns=None, encoding="utf-8", chunk_bytes=50)
    fake = FakeFiles({CSV_URL: data})
    a = cls(fake)  # type: ignore[arg-type]
    parts = list(a.partitions())
    assert [p["lo"] for p in parts] == [str(n) for n in range(0, len(data), 50)]
    got: list[str] = []
    for p in parts:
        f = a.fetch(FetchRequest(p))
        assert f.request == f"{CSV_URL}#bytes={p['lo']}-{int(p['hi']) - 1}"
        got += [r["num"] for r in json.loads(f.content)["rows"]]
    assert got == [str(i) for i in range(1, 41)]
    past = json.loads(a.fetch(FetchRequest({"url": CSV_URL, "lo": "5000", "hi": "5050"})).content)
    assert past["rows"] == []  # 416: the window starts past the end
    flat = cls(FakeFiles({CSV_URL: data}, ranges=False))  # type: ignore[arg-type]
    assert list(flat.partitions()) == [{"url": CSV_URL}]
    whole = flat.fetch(FetchRequest({"url": CSV_URL, "lo": "0", "hi": "60"}))
    assert [r["num"] for r in json.loads(whole.content)["rows"]][:3] == ["1", "2", "3"]
    with pytest.raises(RuntimeError, match="HTTP 404"):
        a.fetch(FetchRequest({"url": "https://x.test/missing.csv", "lo": "0", "hi": "50"}))
    with pytest.raises(LicenseConfigError, match="RangeClient"):
        list(cls(FakeSocrata({})).partitions())  # type: ignore[arg-type]


def test_csv_health(tmp_path: Path) -> None:
    cls = _csv_adapter(tmp_path)
    assert cls(FakeFiles({CSV_URL: HEADERLESS})).health().ok  # type: ignore[arg-type]
    gone = cls(FakeFiles({})).health()  # type: ignore[arg-type]
    assert not gone.ok and "404" in gone.detail
    empty = cls(FakeFiles({CSV_URL: b"\n \n"})).health()  # type: ignore[arg-type]
    assert not empty.ok and empty.detail == "no rows"


def test_fixtures_normalize_to_licenses_with_holders() -> None:
    for cls in all_license_adapters():
        for path in sorted((FIX / cls.source_id).glob("*.json")):
            f = Fetched(cls.source_id, path.as_uri(), AT, 200, path.read_bytes(), "")
            tables = Counter(r.table for r in cls().normalize(f))
            assert tables["business"] > 0, cls.source_id
            assert tables["business_role"] >= tables["business"] * 0.5, cls.source_id
            assert tables["party"] > 0, cls.source_id


def test_chicago_owners_map_to_roles() -> None:
    cls = next(c for c in all_license_adapters() if c.source_id == "il.chicago.business_licenses")
    path = next((FIX / cls.source_id).glob("*.json"))
    f = Fetched(cls.source_id, path.as_uri(), AT, 200, path.read_bytes(), "")
    roles = Counter(r.row["role"] for r in cls().normalize(f) if r.table == "business_role")
    assert roles["officer"] > 0 and roles["other"] > 0
