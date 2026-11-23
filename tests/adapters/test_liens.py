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


def test_arcgis_layers_are_partitions_and_dates_may_be_epochs_or_years(tmp_path: Path) -> None:
    from collections.abc import Mapping as _M

    from equity.adapters.http import PoliteClient

    calls: list[str] = []

    def transport(url: str, headers: _M[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        calls.append(url)
        if "returnCountOnly" in url:
            return 200, b'{"count": 2}', ""
        feats = [{"attributes": {"OBJECTID": 1, "bill": "B1", "due": 1472601600000,
                                 "pin": "9608-10-8745-00000", "owner": "ANN LEE",
                                 "line": "1 MAIN ST", "csz": "ASHEVILLE, NC 28805-1234",
                                 "total": "12.50"}},
                 {"attributes": {"OBJECTID": 2, "bill": "B2", "due": 2019, "pin": "",
                                 "owner": "BOB RAY", "line": "2 OAK AVE", "csz": "nowhere",
                                 "total": "3"}}]  # fmt: skip
        return 200, json.dumps({"features": feats if "layer1" in url else []}).encode(), ""

    cfg = _cfg(tmp_path, api="arcgis", portal=None, dataset=None, date_field="due", uid="bill",
               amount="total", released_on=None,
               layer_urls=["https://g.test/layer0/FeatureServer/0",
                           "https://g.test/layer1/FeatureServer/0"],
               parcel={"kind": "pin", "field": "pin", "county_fips": "37021", "strip": "-"},
               parties=[{"role": "debtor", "name": "owner",
                         "address": {"line1": "line", "csz": "csz"}}])  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    a = cls(PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None))
    assert list(a.partitions()) == [{"layer": "0"}, {"layer": "1"}]
    assert a.source_row()["base_url"] == "https://g.test/layer0/FeatureServer/0"
    assert a.health().ok
    f = a.fetch(FetchRequest({"layer": "1"}))
    assert any("layer1" in c and "query" in c for c in calls)
    out = [(r.table, dict(r.row)) for r in a.normalize(f)]
    inst = {r["instrument_number"]: r for t, r in out if t == "instrument"}
    assert str(inst["B1"]["recorded_on"]) == "2016-08-31"  # epoch milliseconds
    assert str(inst["B2"]["recorded_on"]) == "2019-01-01"  # bare year
    assert [r["parcel_uid"] for t, r in out if t == "instrument_parcel"] == [
        "37021-960810874500000"]  # dashes stripped; the empty PIN links nothing  # fmt: skip
    addrs = [r for t, r in out if t == "address"]
    assert [(r["line1"], r["city"], r["state"], r["zip5"]) for r in addrs] == [
        ("1 MAIN ST", "ASHEVILLE", "NC", "28805"),
        ("2 OAK AVE", None, None, None),  # an unparsable city line keeps only the street
    ]
    with pytest.raises(LienConfigError, match="no layer"):
        a.fetch(FetchRequest({"layer": "5"}))
    data = yaml.safe_load(cfg.read_text())
    del data["layer_urls"]
    (tmp_path / "ag.yaml").write_text(yaml.safe_dump(data))
    with pytest.raises(LienConfigError, match="layer_urls"):
        load_lien_config(tmp_path / "ag.yaml")
    data["api"] = "ftp"
    (tmp_path / "ag.yaml").write_text(yaml.safe_dump(data))
    with pytest.raises(LienConfigError, match="unknown api"):
        load_lien_config(tmp_path / "ag.yaml")


def test_single_partition_and_us_dates(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, partition="none", released_on=None, county_fips="37119",
               parcel=None)  # fmt: skip
    cls = lien_adapter_for(load_lien_config(cfg))
    a = cls()
    assert list(a.partitions()) == [{}]
    assert a.where({}) == "1=1"
    rows_in = [{"ticket": "T1", "docketed": "09-13-2004", "last": "X"},
               {"ticket": "T2", "docketed": "13/45/2004", "last": "Y"},
               {"ticket": "T3", "docketed": "1700", "last": "Z"}]  # fmt: skip
    body = json.dumps({"rows": rows_in}).encode()
    rows = [r.row for r in a.normalize(Fetched(cls.source_id, "x", AT, 200, body, ""))
            if r.table == "instrument"]  # fmt: skip
    assert [(r["instrument_number"], str(r["recorded_on"])) for r in rows] == [
        ("T1", "2004-09-13")]  # a bad month and an out-of-range year are not dates  # fmt: skip
