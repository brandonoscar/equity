"""Socrata judgment and lien sources: config checks, partitions, instrument rows."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.liens import (
    LienConfigError,
    all_lien_adapters,
    lien_adapter_for,
    load_lien_config,
    nyc_bbl,
)

AT = datetime(2026, 11, 21, tzinfo=UTC)


def _cfg(tmp_path: Path, **over: Any) -> Path:
    base: dict[str, Any] = {
        "source_id": "zz.test.liens", "state": "NY", "portal": "https://p.test",
        "dataset": "abcd-1234", "date_field": "docketed", "uid": "ticket",
        "doc_type": "JUDGMENT_LIEN", "doc_type_raw": "test judgment", "amount": "due",
        "released_on": "satisfied",
        "parties": [
            {"role": "debtor", "name": ["first", "last"],
             "address": {"line1": ["house", "street"], "city": "city", "state_const": "NY",
                         "zip": "zip"}},
            {"role": "creditor", "const": "NYC DOF"},
        ],
        "parcel": {"kind": "nyc_bbl", "borough": "boro", "block": "block", "lot": "lot"},
        "terms": {"summary": "s", "checked_on": "2026-11-21", "cost_model": "free"},
    }  # fmt: skip
    base.update(over)
    path = tmp_path / "z.yaml"
    path.write_text(yaml.safe_dump(base))
    return path


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"partition": "week"}, "partition"),
        ({"parcel": {"kind": "gps"}}, "unknown parcel kind"),
        ({"parcel": None}, "needs parcel or county_fips"),
    ],
)
def test_config_validation(tmp_path: Path, over: dict[str, Any], message: str) -> None:
    with pytest.raises(LienConfigError, match=message):
        load_lien_config(_cfg(tmp_path, **over))
    bad = tmp_path / "bad.yaml"
    bad.write_text("source_id: x\n")
    with pytest.raises(LienConfigError, match="missing"):
        load_lien_config(bad)


def test_nyc_bbl() -> None:
    assert nyc_bbl("QUEENS", "01737", "0039") == "4017370039"
    assert nyc_bbl("1", 12, 3) == "1000120003"
    assert nyc_bbl("JERSEY", 1, 1) is None
    assert nyc_bbl("BRONX", "", "3") is None
    assert nyc_bbl("BRONX", 0, 3) is None


def test_partitions_and_where(tmp_path: Path) -> None:
    a = lien_adapter_for(load_lien_config(_cfg(tmp_path, first_year=2025, partition="month")))()
    plan = list(a.partitions())
    assert plan[0] == {"from": "2025-01-01", "to": "2025-02-01"}
    assert {"from": "2025-12-01", "to": "2026-01-01"} in plan
    yearly = lien_adapter_for(load_lien_config(_cfg(tmp_path, first_year=2025, where="x>0")))()
    assert next(iter(yearly.partitions())) == {"from": "2025-01-01", "to": "2026-01-01"}
    window = "docketed >= '2025-01-01T00:00:00' AND docketed < '2026-01-01T00:00:00'"
    assert yearly.where({"from": "2025-01-01", "to": "2026-01-01"}) == f"(x>0) AND {window}"
    assert yearly.where({}) == "(x>0)"


def test_rows_become_instruments_parties_parcels_and_releases(tmp_path: Path) -> None:
    cls = lien_adapter_for(load_lien_config(_cfg(tmp_path)))
    assert cls.pii_fields == ("first", "house", "last", "street")
    rows = [
        {"ticket": "T1", "docketed": "2026-01-05T00:00:00.000", "due": "1,250.50",
         "satisfied": "2026-03-01T00:00:00.000", "first": "ANN", "last": "LEE",
         "house": "12", "street": "MAIN ST", "city": "Bronx", "zip": "10451-1234",
         "boro": "BRONX", "block": "2345", "lot": "17"},
        {"ticket": "T2", "docketed": "2026-02-01T00:00:00.000", "due": "x", "last": "ACME LLC",
         "boro": "", "block": "", "lot": ""},
        {"ticket": "T3", "docketed": None, "last": "NO DATE"},
        {"ticket": "", "docketed": "2026-02-01T00:00:00.000", "last": "NO KEY"},
    ]  # fmt: skip
    body = json.dumps({"dataset": "abcd-1234", "where": "1=1", "rows": rows}).encode()
    out = [(r.table, dict(r.row)) for r in cls().normalize(Fetched(cls.source_id, "x", AT, 200,
                                                                   body, ""))]  # fmt: skip
    inst = {r["instrument_number"]: r for t, r in out if t == "instrument"}
    assert set(inst) == {"T1", "T1-SAT", "T2"}  # T3 has no date, the fourth no key
    assert inst["T1"]["principal_amount"] == pytest.approx(1250.50)
    assert inst["T1"]["doc_type"] == "JUDGMENT_LIEN" and inst["T1"]["jurisdiction"] == "36005"
    assert inst["T2"]["principal_amount"] is None and inst["T2"]["jurisdiction"] == "NY"
    assert inst["T1-SAT"]["doc_type"] == "RELEASE"
    refs = [r for t, r in out if t == "instrument_ref"]
    assert [(r["from_uid"], r["to_uid"], r["ref_type"]) for r in refs] == [
        (inst["T1-SAT"]["instrument_uid"], inst["T1"]["instrument_uid"], "releases")]  # fmt: skip
    parcels = [r["parcel_uid"] for t, r in out if t == "instrument_parcel"]
    assert parcels == ["36005-6001002023450017"]
    roles = sorted((r["instrument_uid"] == inst["T1"]["instrument_uid"], r["role"])
                   for t, r in out if t == "instrument_party")  # fmt: skip
    assert roles == [(False, "creditor"), (False, "debtor"), (True, "creditor"), (True, "debtor")]
    names = {r["raw_name"] for t, r in out if t == "party"}
    assert names == {"ANN LEE", "ACME LLC", "NYC DOF"}
    addr = next(r for t, r in out if t == "address")
    assert (addr["line1"], addr["state"], addr["zip5"]) == ("12 MAIN ST", "NY", "10451")


def test_pin_parcels_use_the_county(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, parcel={"kind": "pin", "field": "pin", "county_fips": "42003"},
               released_on=None)  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    body = json.dumps({"rows": [{"ticket": "L1", "docketed": "2024-05-01T00:00:00",
                                 "pin": "0001-A-00100", "last": "X"}]}).encode()  # fmt: skip
    out = [(r.table, dict(r.row)) for r in cls().normalize(Fetched(cls.source_id, "x", AT, 200,
                                                                   body, ""))]  # fmt: skip
    (puid,) = [r["parcel_uid"] for t, r in out if t == "instrument_parcel"]
    assert puid.startswith("42003-")
    assert not [r for t, r in out if t == "instrument_ref"]


def test_real_lien_configs_load() -> None:
    ids = {a.source_id for a in all_lien_adapters()}
    assert "ny.nyc.oath.judgments" in ids


def test_zip_must_be_five_ascii_digits(tmp_path: Path) -> None:
    cls = lien_adapter_for(load_lien_config(_cfg(tmp_path)))
    rows = [
        {
            "ticket": "Z",
            "docketed": "2026-01-05T00:00:00",
            "last": "X",
            "house": "1",
            "street": "A ST",
            "zip": "\uff11\uff10\uff14\uff15\uff11",  # fullwidth "10451"
        }
    ]  # fullwidth digits pass str.isdigit()
    body = json.dumps({"rows": rows}).encode()
    out = [r.row for r in cls().normalize(Fetched(cls.source_id, "x", AT, 200, body, ""))
           if r.table == "address"]  # fmt: skip
    assert [a["zip5"] for a in out] == [None]


def test_separators_are_skipped_and_county_comes_from_its_name(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, parcel=None, county_fips="36001", county_name_field="county",
               skip_names=["AND/OR"],
               parties=[{"role": "debtor", "name": "n1"}, {"role": "debtor", "name": "n2"},
                        {"role": "debtor", "name": "n3"}])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    rows = [
        {
            "ticket": "W1",
            "docketed": "2026-01-05T00:00:00",
            "n1": "ANN LEE",
            "n2": "AND/OR",
            "n3": "BOB LEE",
            "county": "PUTNAM",
        },
        {"ticket": "W2", "docketed": "2026-01-05T00:00:00", "n1": "C", "county": "NOWHERE"},
    ]
    body = json.dumps({"rows": rows}).encode()
    out = [
        (r.table, r.row) for r in cls().normalize(Fetched(cls.source_id, "x", AT, 200, body, ""))
    ]
    names = sorted(r["raw_name"] for t, r in out if t == "party")
    assert names == ["ANN LEE", "BOB LEE", "C"]
    seqs = sorted(r["seq"] for t, r in out if t == "instrument_party")
    assert seqs == [1, 1, 2]
    juris = {r["instrument_number"]: r["jurisdiction"] for t, r in out if t == "instrument"}
    assert juris == {"W1": "36079", "W2": "36001"}  # Putnam; unknown name -> fallback


def test_ckan_sources_page_by_sql_and_mark_satisfied(tmp_path: Path) -> None:
    from collections.abc import Mapping as _M

    from equity.adapters.http import PoliteClient

    calls: list[str] = []

    def transport(url: str, headers: _M[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        calls.append(url)
        recs = [{"_id": 1, "dtd": "DTD-1", "filing_date": "2020-02-03", "amount": 10.5,
                 "pin": "0001A00100000000", "satisfied": True, "assignee": "TAX CO"}]  # fmt: skip
        page = recs if len(calls) == 1 else []
        return 200, json.dumps({"success": True, "result": {"records": page}}).encode(), ""

    cfg = _cfg(tmp_path, api="ckan", resource_id="res-1", portal="https://c.test",
               date_field="filing_date", uid="dtd", amount="amount", released_on=None,
               satisfied_flag="satisfied", parcel={"kind": "pin", "field": "pin",
                                                   "county_fips": "42003"},
               parties=[{"role": "creditor", "name": "assignee"}])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    client = PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None)
    a = cls(client)
    assert a.where({"from": "2020-01-01", "to": "2021-01-01"}) == (
        "filing_date >= '2020-01-01' AND filing_date < '2021-01-01'")  # fmt: skip
    f = a.fetch(FetchRequest({"from": "2020-01-01", "to": "2021-01-01"}))
    assert len(calls) == 1  # a short page ends the paging
    assert "datastore_search_sql" in calls[0] and "res-1" in calls[0]
    (inst,) = [r.row for r in a.normalize(f) if r.table == "instrument"]
    assert inst["doc_type_raw"].endswith("(satisfied)")
    assert a.source_row()["base_url"] == "https://c.test/datastore/res-1"
    bad = tmp_path / "ck.yaml"
    data = yaml.safe_load(cfg.read_text())
    del data["resource_id"]
    bad.write_text(yaml.safe_dump(data))
    with pytest.raises(LienConfigError, match="resource_id"):
        load_lien_config(bad)


def test_doc_type_can_be_mapped_from_a_field(tmp_path: Path) -> None:
    dt = {"field": "kind", "map": {"IRS": "TAX_LIEN_FEDERAL"}, "default": "OTHER"}
    cls = lien_adapter_for(load_lien_config(_cfg(tmp_path, doc_type=dt,
                                                  doc_type_raw={"field": "kind"})))  # fmt: skip
    rows = [{"ticket": "A", "docketed": "2026-01-05T00:00:00", "kind": "irs", "last": "X"},
            {"ticket": "B", "docketed": "2026-01-05T00:00:00", "kind": "ODD", "last": "Y"},
            {"ticket": "C", "docketed": "2026-01-05T00:00:00", "last": "Z"}]  # fmt: skip
    body = json.dumps({"rows": rows}).encode()
    inst = {r.row["instrument_number"]: r.row for r in cls().normalize(
        Fetched(cls.source_id, "x", AT, 200, body, "")) if r.table == "instrument"}  # fmt: skip
    assert {k: v["doc_type"] for k, v in inst.items()} == {
        "A": "TAX_LIEN_FEDERAL", "B": "OTHER", "C": "OTHER"}  # fmt: skip
    assert inst["C"]["doc_type_raw"] == "OTHER"  # no raw value: falls back to the mapped type


def test_ten_digit_bbl_and_extra_pii(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, parcel={"kind": "nyc_bbl10", "field": "bbl"}, parties=[],
               extra_pii=["apt"])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    assert cls.pii_fields == ("apt",)
    rows = [{"ticket": "E1", "docketed": "2025-03-01T00:00:00", "bbl": "2042840001"},
            {"ticket": "E2", "docketed": "2025-03-01T00:00:00", "bbl": "204284"}]  # fmt: skip
    body = json.dumps({"rows": rows}).encode()
    out = [
        (r.table, r.row) for r in cls().normalize(Fetched(cls.source_id, "x", AT, 200, body, ""))
    ]
    assert [r["parcel_uid"] for t, r in out if t == "instrument_parcel"] == [
        "36005-6001002042840001"]  # fmt: skip
    juris = {r["instrument_number"]: r["jurisdiction"] for t, r in out if t == "instrument"}
    # A short bbl names no lot, but its first digit still names the borough (2 = Bronx).
    assert juris == {"E1": "36005", "E2": "36005"}


def test_rows_sharing_a_uid_are_one_lien(tmp_path: Path) -> None:
    """NY warrants repeat per status change; CT repeats per debtor; foreclosures per lot."""
    cfg = _cfg(tmp_path, parcel={"kind": "pin", "field": "pin", "county_fips": "42003"},
               parties=[{"role": "debtor", "name": "last",
                         "address": {"line1": "street", "zip": "zip"}}])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    rows = [
        {"ticket": "W1", "docketed": "2026-01-05T00:00:00", "due": "50", "last": "ANN LEE",
         "pin": "1", "satisfied": None},
        {"ticket": "W1", "docketed": "2026-01-05T00:00:00", "due": "50", "last": "ANN LEE",
         "street": "1 MAIN ST", "zip": "10001", "pin": "2",
         "satisfied": "2026-04-01T00:00:00"},
        {"ticket": "W1", "docketed": "2026-01-05T00:00:00", "last": "BOB LEE", "pin": "2"},
    ]  # fmt: skip
    body = json.dumps({"rows": rows}).encode()
    out = [
        (r.table, r.row) for r in cls().normalize(Fetched(cls.source_id, "x", AT, 200, body, ""))
    ]
    inst = [r for t, r in out if t == "instrument"]
    assert sorted(r["doc_type"] for r in inst) == ["JUDGMENT_LIEN", "RELEASE"]
    assert len([1 for t, _ in out if t == "source_record"]) == 1
    assert len([r for t, r in out if t == "instrument_parcel"]) == 2
    parties = {r["raw_name"]: r["address_id"] for t, r in out if t == "party"}
    assert set(parties) == {"ANN LEE", "BOB LEE"}
    assert parties["ANN LEE"] is not None  # the row with an address wins
    again = [
        (r.table, r.row)
        for r in cls().normalize(
            Fetched(cls.source_id, "x", AT, 200, json.dumps({"rows": rows[::-1]}).encode(), "")
        )
    ]
    assert again == out  # row order does not matter


def _xlsx(rows: list[list[str]]) -> bytes:
    """A minimal workbook: shared strings for text, plain numbers for digits."""
    import io
    import zipfile
    from xml.sax.saxutils import escape

    strings: list[str] = []
    body = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, val in enumerate(row):
            ref = f"{chr(65 + c)}{r}"
            if val.replace(".", "", 1).isdigit():
                cells.append(f'<c r="{ref}"><v>{val}</v></c>')
            elif val:
                strings.append(val)
                cells.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
        body.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    sst = "".join(f"<si><t>{escape(s)}</t></si>" for s in strings)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>{sst}</sst>")
        z.writestr(
            "xl/worksheets/sheet1.xml",
            f"<worksheet {ns}><sheetData>{''.join(body)}</sheetData></worksheet>",
        )
    return buf.getvalue()


def test_xlsx_helpers() -> None:
    from equity.adapters.liens import excel_date, split_address, xlsx_rows

    book = _xlsx([["Name of Employer/DBA", "Date Posted", "Owed"],
                  ["Acme LLC", "45478", "12.5"], ["", "", ""], ["Bee Inc", "", "3"]])  # fmt: skip
    assert xlsx_rows(book) == [
        {"name_of_employer_dba": "Acme LLC", "date_posted": "45478", "owed": "12.5"},
        {"name_of_employer_dba": "Bee Inc", "date_posted": "", "owed": "3"}]  # fmt: skip
    assert excel_date("45478") == "2024-07-05"
    assert excel_date("") is None and excel_date("0") is None
    assert split_address("259 Drum Point Road,  Brick, NJ 08723") == {
        "line1": "259 Drum Point Road",
        "city": "Brick",
        "state": "NJ",
        "zip": "08723",
    }
    assert split_address("199 Main St., Suite 202, Woodbridge, NJ 07095-1234")["line1"] == (
        "199 Main St., Suite 202")  # fmt: skip
    assert split_address("PO Box 5, Trenton") == {
        "line1": "PO Box 5, Trenton", "city": None, "state": None, "zip": None}  # fmt: skip


def _client(responses: dict[str, bytes]):  # type: ignore[no-untyped-def]
    from collections.abc import Mapping as _M

    from equity.adapters.http import PoliteClient

    def transport(url: str, headers: _M[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        for key, body in responses.items():
            if key in url:
                return 200, body, ""
        return 404, b"", ""

    return PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None)


def test_xlsx_source_reads_one_workbook(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, api="xlsx", url="https://x.test/list.xlsx", portal=None, dataset=None,
               parcel=None, county_fips="34", released_on=None, date_field="posted",
               excel_dates=["posted"], uid=["employer", "posted"],
               address_split={"field": "address", "prefix": "a_"},
               amount=["wages", "penalty"], satisfied_flag="status",
               satisfied_values=["Wages Paid in Full"],
               parties=[{"role": "debtor", "name": "employer",
                         "address": {"line1": "a_line1", "city": "a_city", "state": "a_state",
                                     "zip": "a_zip"}}])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    book = _xlsx([["Employer", "Address", "Posted", "Wages", "Penalty", "Status"],
                  ["Acme LLC", "1 Main St, Newark, NJ 07102", "45478", "100.105", "20",
                   "Wages Paid in Full"],
                  ["Bee Inc", "", "45479", "7", "", "Wages Still Owed"]])  # fmt: skip
    a = cls(_client({"list.xlsx": book}))
    assert list(a.partitions()) == [{"file": "all"}]
    assert a.source_row()["access_method"] == "bulk"
    out = [(r.table, dict(r.row)) for r in a.normalize(a.fetch(FetchRequest({"file": "all"})))]
    inst = {r["instrument_number"]: r for t, r in out if t == "instrument"}
    acme, bee = inst["Acme LLC-2024-07-05"], inst["Bee Inc-2024-07-06"]
    assert str(acme["principal_amount"]) == "120.10" and acme["doc_type_raw"].endswith(
        "(satisfied)"
    )
    assert str(bee["principal_amount"]) == "7.00" and "satisfied" not in bee["doc_type_raw"]
    addr = next(r for t, r in out if t == "address")
    assert (addr["state"], addr["zip5"]) == ("NJ", "07102")


def test_arcgis_source_windows_by_date(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, api="arcgis", layer_url="https://g.test/FeatureServer/0", portal=None,
               dataset=None, where="disposition LIKE 'Responsible%'", released_on=None,
               date_field="judgment_date", uid="ticket", order_by=["OBJECTID"],
               parcel={"kind": "pin", "field": "pin", "county_fips": "26163"},
               satisfied_flag="pay", satisfied_values=["PAID IN FULL"])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    feats = {"features": [{"attributes": {"ticket": "T9", "judgment_date": "2025-09-23",
                                          "due": 305, "pay": "PAID IN FULL",
                                          "pin": "13006747.", "last": "X"}}]}  # fmt: skip
    a = cls(_client({"FeatureServer/0/query": json.dumps(feats).encode()}))
    where = a.where({"from": "2025-01-01", "to": "2026-01-01"})
    assert where == ("(disposition LIKE 'Responsible%') AND judgment_date >= DATE '2025-01-01' "
                     "AND judgment_date < DATE '2026-01-01'")  # fmt: skip
    f = a.fetch(FetchRequest({"from": "2025-01-01", "to": "2026-01-01"}))
    out = [(r.table, dict(r.row)) for r in a.normalize(f)]
    (inst,) = [r for t, r in out if t == "instrument" and r["instrument_number"] == "T9"]
    assert inst["doc_type_raw"].endswith("(satisfied)")
    assert [r["parcel_uid"] for t, r in out if t == "instrument_parcel"] == ["26163-13006747."]
    assert a.source_row()["access_method"] == "arcgis"


def test_unknown_api_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(LienConfigError, match="unknown api"):
        load_lien_config(_cfg(tmp_path, api="ftp"))


def test_arcgis_text_dates_compare_as_strings(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, api="arcgis", layer_url="https://g.test/FeatureServer/1", portal=None,
               dataset=None, date_field="jd", date_is_text=True)  # fmt: skip
    a = lien_adapter_for(load_lien_config(cfg))()
    assert a.where({"from": "2025-01-01", "to": "2026-01-01"}) == (
        "jd >= '2025-01-01' AND jd < '2026-01-01'")  # fmt: skip


def test_captions_split_and_pin_lists_give_every_lot(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, caption_field="title", released_on=None,
               parcel={"kind": "pin", "county_fips": "42125", "field": ["p1", "p2"]},
               parties=[{"role": "creditor", "name": "caption_plaintiff"},
                        {"role": "debtor", "name": "caption_defendant"}])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    rows = [
        {
            "ticket": "S1",
            "docketed": "2024-05-01T00:00:00",
            "title": "BANK NA\r\nvs\r\nANN LEE",
            "p1": "010-022",
            "p2": "010-023",
        },
        {"ticket": "S2", "docketed": "2024-05-01T00:00:00", "title": "no caption", "p1": ""},
    ]
    body = json.dumps({"rows": rows}).encode()
    out = [(r.table, dict(r.row)) for r in cls().normalize(Fetched(cls.source_id, "x", AT, 200,
                                                                   body, ""))]  # fmt: skip
    roles = {(r["raw_name"]) for t, r in out if t == "party"}
    assert roles == {"BANK NA", "ANN LEE"}
    assert sorted(r["parcel_uid"] for t, r in out if t == "instrument_parcel") == [
        "42125-010-022", "42125-010-023"]  # fmt: skip


def test_arcgis_epoch_dates() -> None:
    from equity.adapters.liens import _date

    assert str(_date(1648771200000)) == "2022-04-01"
    assert _date(True) is None and _date(1e30) is None


def _rows_of(cls: Any, responses: dict[str, bytes]) -> list[tuple[str, dict[str, Any]]]:
    a = cls(_client(responses))
    return [(r.table, dict(r.row)) for r in a.normalize(a.fetch(FetchRequest({"file": "all"})))]


def test_xlsx_banner_date_header_row_and_county_alias(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, api="xlsx", url="https://x.test/w.xlsx", portal=None, dataset=None,
               parcel=None, county_fips="12", state="FL", released_on=None,
               header_row=1, as_of={"field": "listed", "after": "as of"},
               date_field="listed", uid="warrant", amount="owed",
               county_name_field="county", county_aliases={"Dade": "MIAMI-DADE"},
               address_split={"field": "where", "prefix": "a_", "form": "slash"},
               parties=[{"role": "debtor", "name": "owner",
                         "address": {"line1": "a_line1", "city": "a_city", "state": "a_state",
                                     "zip": "a_zip"}}])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    book = _xlsx([["Delinquent Taxpayers as of 11/20/2026"],
                  ["Owner", "Where", "County", "Warrant", "Owed"],
                  ["ACME LLC", "1 MAIN ST / OPA LOCKA FL 33054-64", "DADE", "W1", "5"],
                  ["BEE INC", "2 ELM ST MIAMI, FL. 33101", "NOWHERE", "W2", "6"]])  # fmt: skip
    out = _rows_of(cls, {"w.xlsx": book})
    inst = {r["instrument_number"]: r for t, r in out if t == "instrument"}
    assert {str(r["recorded_on"]) for r in inst.values()} == {"2026-11-20"}
    assert (inst["W1"]["jurisdiction"], inst["W2"]["jurisdiction"]) == ("12086", "12")
    addrs = {r["line1"]: r for t, r in out if t == "address"}
    assert (addrs["1 MAIN ST"]["city"], addrs["1 MAIN ST"]["zip5"]) == ("OPA LOCKA", "33054")
    assert addrs["2 ELM ST MIAMI"]["city"] is None and addrs["2 ELM ST MIAMI"]["zip5"] == "33101"


def test_csv_source_with_us_dates_and_city_only_addresses(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, api="csv", url="https://f.test/list.txt", delimiter="\t",
               portal=None, dataset=None, parcel=None, county_fips="06", state="CA",
               released_on=None, us_dates=["lien"], date_field="lien", uid=["name", "lien"],
               amount="total", user_agent="equity-records/0.1 (test)",
               address_split={"field": "address", "prefix": "a_", "form": "city_state_zip"},
               parties=[{"role": "debtor", "name": "name",
                         "address": {"city": "a_city", "state": "a_state",
                                     "zip": "a_zip"}}])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    assert cls().client.user_agent == "equity-records/0.1 (test)"
    text = ("﻿Child?\tName\tAddress\tTotal\tLien\n"
            "-\tTotal\t-\t$9.00\t-\n"
            "\tAnn Lee\tActon, MA 01720\t$1,000.50\t08/20/2025\n"
            "Y\t\t\t\t\n"
            "\tBo Ray\tnowhere\t$2\t13/45/2025\n")  # fmt: skip
    out = _rows_of(cls, {"list.txt": text.encode()})
    (inst,) = [r for t, r in out if t == "instrument"]
    assert (str(inst["recorded_on"]), str(inst["principal_amount"])) == ("2025-08-20", "1000.50")
    (addr,) = [r for t, r in out if t == "address"]
    assert (addr["line1"], addr["city"], addr["state"], addr["zip5"]) == (
        None, "ACTON", "MA", "01720")  # fmt: skip
    assert cls().source_row()["access_method"] == "bulk"


HTML_PAGE = b"""<html><head><script>var x = "<table><tr><td>zqx</td></tr></table>";</script>
<style>td {}</style></head><body><p>Delinquent Taxpayers (Updated November 16, 2026)</p>
<table><tr><td>layout</td></tr></table>
<table><thead><tr><th><strong>Name</strong></th><th>Last Known Address</th><th>County</th>
<th>Balance</th></tr></thead><tbody>
<tr><td><div>LEE, ANN &amp; BO</div></td><td>1 A<br>ST</td><td>DOUGLAS</td>
<td>$20,252.64</td></tr>
<tr><td>RAY, BO</td><td>2 B ST</td><td>OUT OF STATE</td><td>$1.00</td></tr>
</tbody></table></body></html>"""


def test_html_table_source_takes_the_page_date(tmp_path: Path) -> None:
    from equity.adapters.liens import html_tables

    tables, text = html_tables(HTML_PAGE)
    assert len(tables) == 2 and "zqx" not in text and tables[1][1][1] == "1 A ST"
    cfg = _cfg(tmp_path, api="html", url="https://n.test/list", table=1, portal=None,
               dataset=None, parcel=None, county_fips="31", state="NE", released_on=None,
               as_of={"field": "listed", "after": "Updated"}, date_field="listed",
               uid=["name", "county"], amount="balance", county_name_field="county",
               parties=[{"role": "debtor", "name": "name",
                         "address": {"line1": "last_known_address"}}])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    out = _rows_of(cls, {"n.test/list": HTML_PAGE})
    inst = sorted((r for t, r in out if t == "instrument"), key=lambda r: r["instrument_number"])
    assert [(r["jurisdiction"], str(r["recorded_on"])) for r in inst] == [
        ("31055", "2026-11-16"), ("31", "2026-11-16")]  # fmt: skip
    assert {r["raw_name"] for t, r in out if t == "party"} == {"LEE, ANN & BO", "RAY, BO"}
    assert cls().source_row()["access_method"] == "html"
    missing = _cfg(tmp_path, api="html", url="https://n.test/list", table=5, portal=None,
                   dataset=None, parcel=None, county_fips="31", date_field="d",
                   released_on=None)  # fmt: skip
    assert _rows_of(lien_adapter_for(load_lien_config(missing)), {"n.test/list": HTML_PAGE}) == []


def test_text_dates() -> None:
    from equity.adapters.liens import split_address, text_date, us_date

    assert text_date("List is current as of Wednesday, October 7, 2026", "as of") == "2026-10-07"
    assert text_date("as of 05/05/2026 (was June 1, 2020)", "AS OF") == "2026-05-05"
    assert text_date("June 1, 2020 then 05/05/2026") == "2020-06-01"
    assert text_date("no marker here", "as of") is None
    assert text_date("as of soon", "as of") is None
    assert text_date("as of 02/30/2026", "as of") is None
    assert text_date(None) is None
    assert us_date("8/2/2025") == "2025-08-02" and us_date("-") is None and us_date(None) is None
    assert split_address("1 A ST / NOWHERE", "slash")["line1"] == "1 A ST / NOWHERE"
    assert split_address(", MA 01720", "city_state_zip")["line1"] == ", MA 01720"
    assert split_address("Acton MA 01720", "city_state_zip")["city"] is None


def test_link_from_finds_the_current_file(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, api="csv", url="https://d.test/old.csv", portal=None, dataset=None,
               parcel=None, county_fips="10", released_on=None, date_field="d", uid="n",
               link_from={"page": "https://d.test/list/", "pattern": r"List_\w+\.csv$"},
               parties=[{"role": "debtor", "name": "n"}])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    page = b"<a href=\"/x.pdf\">x</a> <A HREF='files/List_Oct_2026.csv'>now</A>"
    a = cls(_client({"List_Oct_2026.csv": b"n,d\nAcme,2026-09-30\n", "d.test/list/": page}))
    assert a.file_url() == "https://d.test/list/files/List_Oct_2026.csv"
    f = a.fetch(FetchRequest({"file": "all"}))
    assert f.request.endswith("List_Oct_2026.csv") and json.loads(f.content)["rows"][0]["n"] == (
        "Acme")  # fmt: skip
    with pytest.raises(LienConfigError, match="no link"):
        cls(_client({"d.test/list/": b"<a href='a.pdf'>"})).file_url()
    with pytest.raises(LienConfigError, match="HTTP 404"):
        cls(_client({})).file_url()


def _pdf(lines: list[tuple[float, float, str]], objstm: bool = False) -> bytes:
    """A one-page PDF: a font with a ToUnicode CMap (code 0x01 -> 'Z'), a deflated content
    stream placing each (x, y, text) with Tm, and optionally the font inside an /ObjStm."""
    import zlib

    ops = ["BT /F1 1 Tf"]
    for x, y, text in lines:
        ops.append(f"10 0 0 10 {x} {y} Tm [({text}) -20 ()] TJ")
    ops.append("ET")
    content = zlib.compress("\n".join(ops).encode("latin-1"))
    cmap = (b"begincmap 1 beginbfchar <01> <005A> endbfchar 1 beginbfrange <02> <03> <0061>"
            b" endbfrange endcmap")  # fmt: skip
    font = b"<</Type/Font/Subtype/TrueType/ToUnicode 5 0 R>>"
    objs = [
        b"1 0 obj <</Type/Catalog/Pages 2 0 R>> endobj",
        b"2 0 obj <</Type/Pages/Kids[3 0 R]/Count 1>> endobj",
        b"3 0 obj <</Type/Page/Resources<</Font<</F1 4 0 R>>>>/Contents[6 0 R]>> endobj",
        b"5 0 obj <</Length %d>>stream\n%s\nendstream endobj" % (len(cmap), cmap),
        b"6 0 obj <</Filter/FlateDecode/Length %d>>stream\n%s\nendstream endobj"
        % (len(content), content),
    ]
    if objstm:
        packed = zlib.compress(b"4 0 " + font)
        objs.append(
            b"7 0 obj <</Type/ObjStm/N 1/First 4/Filter/FlateDecode>>stream\n%s\nendstream endobj"
            % packed
        )
    else:
        objs.append(b"4 0 obj " + font + b" endobj")
    return b"%PDF-1.6\n" + b"\n".join(objs) + b"\n%%EOF"


def test_pdf_table_reader() -> None:
    from equity.adapters.pdf_table import _literal, _tokens, pdf_table, pdf_text

    lines = [(300, 700, "Balance as of 09/30/2026"),
             (36, 680, "Taxpayer Name"), (200, 680, "Address"), (400, 680, "Liability"),
             (36, 668, "ACME \\(DE\\) LLC \\001"), (200, 668.5, "1 MAIN ST"),
             (410, 668, "$1,000.00"), (36, 656, "BEE INC"), (420, 656, "$5.00"),
             (36, 644, "Taxpayer Name"), (200, 644, "Address"),
             (400, 644, "Liability")]  # fmt: skip
    for packed in (False, True):
        pdf = _pdf(lines, objstm=packed)
        assert pdf_table(pdf, "Taxpayer Name") == [
            ["Taxpayer Name", "Address", "Liability"],
            ["ACME (DE) LLC Z", "1 MAIN ST", "$1,000.00"],
            ["BEE INC", "", "$5.00"]]  # fmt: skip
    assert pdf_text(_pdf(lines)).startswith("Balance as of 09/30/2026 Taxpayer Name")
    assert pdf_table(_pdf(lines), "Nobody") == [] and pdf_table(b"not a pdf", "X") == []
    assert _literal(b"a\\nb\\\\(c)) tail", 0) == (b"a\nb\\(c)", 10)
    assert _literal(b"line\\\ncont)", 0)[0] == b"linecont"
    toks = _tokens(b"<4142> <4> <zz> [(x) 1] /N 2 Td T* (y) ' 3 TL << >>")
    assert ("str", b"AB") in toks and ("str", b"@") in toks and ("op", "Td") in toks


def test_pdf_text_ops_move_the_line() -> None:
    import zlib

    from equity.adapters.pdf_table import page_texts

    stream = zlib.compress(b"BT /F9 1 Tf 12 TL 1 0 0 1 10 100 Tm (a) Tj T* (b) Tj 5 -12 TD (c) Tj"
                           b" (d) ' 2 3 Td <65> Tj ET")  # fmt: skip
    head = b"%PDF-1.4\n1 0 obj <</Type/Page/Contents 2 0 R>> endobj\n"
    pdf = head + b"2 0 obj <</Filter/FlateDecode>>stream\n" + stream + b"\nendstream endobj\n"
    got = [(t.x, t.y, t.text) for t in page_texts(pdf)]
    assert got == [(10, 100, "a"), (10, 88, "b"), (15, 76, "c"), (15, 64, "d"), (17, 67, "e")]


def test_pdf_source(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, api="pdf", url="https://d.test/list.pdf", header="Taxpayer Name",
               portal=None, dataset=None, parcel=None, county_fips="10", state="DE",
               released_on=None, as_of={"field": "as_of", "after": "Balance as of"},
               date_field="as_of", uid="taxpayer_name", amount="liability",
               parties=[{"role": "debtor", "name": "taxpayer_name",
                         "address": {"line1": "address"}}])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    pdf = _pdf([(300, 700, "Balance as of 09/30/2026"), (36, 680, "Taxpayer Name"),
                (200, 680, "Address"), (400, 680, "Liability"), (36, 668, "ACME LLC"),
                (200, 668, "1 MAIN ST"), (410, 668, "$1,000.00")])  # fmt: skip
    out = _rows_of(cls, {"list.pdf": pdf})
    (inst,) = [r for t, r in out if t == "instrument"]
    assert (str(inst["recorded_on"]), str(inst["principal_amount"])) == ("2026-09-30", "1000.00")
    with pytest.raises(LienConfigError, match="missing"):
        load_lien_config(_cfg(tmp_path, api="pdf", url="https://d.test/x.pdf"))
