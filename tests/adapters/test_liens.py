"""Socrata judgment and lien sources: config checks, partitions, instrument rows."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from equity.adapters.base import Fetched
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
