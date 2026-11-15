"""Generic statewide parcel adapter: config validation, county handling, normalization, and a
check of every config in config/states/ against its recorded fixture."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.state_parcels import (
    STATES_DIR,
    StateConfigError,
    adapter_for,
    all_state_adapters,
    load_config,
    norm_parcel_id,
)
from equity.geo import state_fips

FIX = Path(__file__).parents[1] / "fixtures" / "adapters"
AT = datetime(2026, 11, 15, 12, tzinfo=UTC)


def _cfg(tmp_path: Path, **over: Any) -> Path:
    base: dict[str, Any] = {
        "source_id": "zz.test.parcels", "state": "WV", "layer_url": "https://x.test/FeatureServer/0/",
        "order_by": "OID", "page_size": 2, "county": {"field": "CO", "format": "fips3"},
        "fields": {"parcel_id": "PID", "owner1": "OWN", "owner2": "OWN2", "mail_line1": "M1",
                   "mail_city": "MC", "mail_state": "MS", "mail_zip": "MZ", "total_value": "TV",
                   "tax_year": {"const": 2025}},
        "value_basis": "test", "terms": {"summary": "s", "checked_on": "2026-11-15",
                                         "cost_model": "free"},
    }  # fmt: skip
    base.update(over)
    path = tmp_path / "zz.yaml"
    path.write_text(yaml.safe_dump(base))
    return path


def _rows(cls, attrs: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:  # type: ignore[no-untyped-def]
    body = json.dumps({"layer": "x", "where": "1=1", "attributes": attrs}).encode()
    f = Fetched(cls.source_id, "fixture://zz", AT, 200, body, "application/json")
    return [(r.table, dict(r.row)) for r in cls().normalize(f)]


def test_normalize_maps_fields(tmp_path: Path) -> None:
    cls = adapter_for(load_config(_cfg(tmp_path)))
    out = _rows(cls, [
        {"OID": 2, "PID": "01 23-4", "CO": "061", "OWN": "ACME LLC", "OWN2": "", "M1": "1 Main",
         "MC": "Morgantown", "MS": "WV", "MZ": "26505", "TV": "1,500"},
        {"OID": 1, "PID": "0123-4", "CO": "061", "OWN": "First Row Wins", "TV": 9},
        {"OID": 3, "PID": "77", "CO": "999", "OWN": "Bad County"},
        {"OID": 4, "PID": None, "CO": "061"},
    ])  # fmt: skip
    c = Counter(t for t, _ in out)
    assert c["parcel"] == 1  # duplicate ids collapse; bad county and missing id skipped
    (parcel,) = [r for t, r in out if t == "parcel"]
    assert parcel["parcel_uid"] == "54061-0123-4"
    (party,) = [r for t, r in out if t == "party"]
    assert party["raw_name"] == "First Row Wins"  # lowest order_by value
    (a,) = [r for t, r in out if t == "parcel_assessment"]
    assert (a["tax_year"], a["appraised_total"], a["valid_from"]) == (
        2025,
        "9.00",
        date(2025, 1, 1),
    )


def test_address_and_org(tmp_path: Path) -> None:
    cls = adapter_for(load_config(_cfg(tmp_path)))
    out = _rows(cls, [{"OID": 1, "PID": "9", "CO": "61", "OWN": "ACME LLC", "M1": "1 Main",
                       "MC": "Morgantown", "MS": "WV", "MZ": "26505-1111",
                       "TV": "-5"}])  # fmt: skip
    (addr,) = [r for t, r in out if t == "address"]
    assert addr["zip5"] == "26505"
    (party,) = [r for t, r in out if t == "party"]
    assert party["org_form"] == "LLC"
    assert party["address_id"] == addr["address_id"]
    assert not [r for t, r in out if t == "parcel_assessment"]  # negative value dropped


@pytest.mark.parametrize(
    ("county", "value", "where", "fips5"),
    [
        ({"field": "C", "format": "fips3"}, "061", "C='061'", "54061"),
        ({"field": "C", "format": "fips5"}, "54061", "C='54061'", "54061"),
        ({"field": "C", "format": "int"}, 61, "C=61", "54061"),
        ({"field": "C", "format": "code_map", "code_map": {"31": "061"}}, "31", "C='31'", "54061"),
        ({"constant": "061"}, None, "1=1", "54061"),
    ],
)
def test_county_formats(tmp_path: Path, county: dict[str, Any], value: Any, where: str,
                        fips5: str) -> None:  # fmt: skip
    cls = adapter_for(load_config(_cfg(tmp_path, county=county)))
    a = cls()
    assert a.where(FetchRequest({"county_fips": "061"})) == where
    assert a.county_of({"C": value}).fips5 == fips5


def test_name_format_and_other_partitions(tmp_path: Path) -> None:
    cls = adapter_for(load_config(_cfg(tmp_path, county={"field": "C", "format": "name"})))
    a = cls()
    assert a.county_of({"C": "monongalia"}).fips5 == "54061"
    with pytest.raises(StateConfigError, match="oid range"):
        a.where(FetchRequest({"county_fips": "061"}))
    assert a.where(FetchRequest({"oid_min": "1", "oid_max": "5"})) == "OID>=1 AND OID<5"
    assert a.where(FetchRequest({"sample": "1"})) == "1=1"
    with pytest.raises(StateConfigError, match="need"):
        a.where(FetchRequest({}))
    with pytest.raises(KeyError):
        a.county_of({"C": ""})


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"fields": {"owner1": "X"}}, "parcel_id"),
        ({"fields": {"parcel_id": "P", "bogus": "X"}}, "unknown canonical"),
        ({"county": {"field": "C"}}, "county needs"),
        ({"county": {"field": "C", "format": "code_map"}}, "code_map"),
        ({"terms": {"summary": "s"}}, "terms.checked_on"),
        ({"state": "XX"}, "unknown state"),
    ],
)
def test_config_validation(tmp_path: Path, over: dict[str, Any], message: str) -> None:
    with pytest.raises((StateConfigError, KeyError), match=message):
        load_config(_cfg(tmp_path, **over))


def test_config_requires_keys(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("source_id: x\n")
    with pytest.raises(StateConfigError, match="missing"):
        load_config(p)
    p.write_text("- 1\n")
    with pytest.raises(StateConfigError, match="mapping"):
        load_config(p)


def test_norm_parcel_id() -> None:
    assert norm_parcel_id(" 01 23-4a ") == "0123-4A"


def test_year_of_and_pii(tmp_path: Path) -> None:
    fields = {"parcel_id": "PID", "owner1": "OWN", "mail_line1": "M1", "total_value": "TV",
              "tax_year": {"year_of": "D"}}  # fmt: skip
    cls = adapter_for(load_config(_cfg(tmp_path, fields=fields, extra_pii=["SITUS"])))
    assert cls.pii_fields == ("M1", "OWN", "SITUS")
    assert "D" in cls.fields
    out = _rows(cls, [{"OID": 1, "PID": "1", "CO": "061", "TV": 5, "D": 1767225600000},
                      {"OID": 2, "PID": "2", "CO": "061", "TV": 5, "D": None}])  # fmt: skip
    years = sorted(r["tax_year"] for t, r in out if t == "parcel_assessment")
    assert years == [2026]


# --- every real state config ------------------------------------------------------------

CONFIGS = sorted(STATES_DIR.glob("*.yaml"))


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.stem)
def test_state_config_against_fixture(path: Path) -> None:
    cfg = load_config(path)
    fixtures = sorted((FIX / cfg.source_id).glob("*.json"))
    assert fixtures, f"{cfg.source_id}: record a fixture with equity.adapters.record"
    cls = adapter_for(cfg)
    out: list[tuple[str, dict[str, Any]]] = []
    for fx in fixtures:
        out += [
            (r.table, dict(r.row))
            for r in cls().normalize(
                Fetched(cls.source_id, "fixture://s", AT, 200, fx.read_bytes(), "application/json")
            )
        ]
    parcels = [r for t, r in out if t == "parcel"]
    assert len(parcels) >= 5, "fixture should yield at least 5 parcels"
    assert all(r["parcel_uid"].startswith(state_fips(cfg.state)) for r in parcels)
    assert any(t == "owner_snapshot" for t, _ in out) or "owner1" not in cfg.fields


def test_all_configs_load() -> None:
    adapters = all_state_adapters()
    assert len(adapters) == len(CONFIGS)
    assert len({a.source_id for a in adapters}) == len(adapters)


def test_partitions_by_county_and_by_oid_window(tmp_path: Path) -> None:
    cls = adapter_for(load_config(_cfg(tmp_path)))
    plan = list(cls().partitions())
    assert len(plan) == 55
    assert plan[30] == {"county_fips": "061"}

    from collections.abc import Mapping as _M

    from equity.adapters.http import PoliteClient

    def transport(url: str, headers: _M[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        body = {"features": [{"attributes": {"lo": 1, "hi": 120000}}]}
        return 200, json.dumps(body).encode(), "application/json"

    named = adapter_for(load_config(_cfg(tmp_path, county={"field": "C", "format": "name"})))
    client = PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None)
    windows = list(named(client).partitions(window=50_000))
    assert windows == [{"oid_min": "1", "oid_max": "50001"},
                       {"oid_min": "50001", "oid_max": "100001"},
                       {"oid_min": "100001", "oid_max": "150001"}]  # fmt: skip
