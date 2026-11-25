"""Deed and sales sources in config/deeds/: date formats, id rewrites, windows, fixtures."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from equity.adapters.base import Fetched
from equity.adapters.deeds import (
    all_deed_adapters,
    deed_adapter_for,
    load_deed_config,
    mdy_date,
    ymd_date,
)
from equity.adapters.liens import LienConfigError

from ..test_adapter_contract import check_contract

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters"


def _cfg(tmp_path: Path, **over: Any) -> Path:
    base: dict[str, Any] = {
        "source_id": "zz.test.deeds", "state": "VT", "api": "arcgis",
        "layer_url": "https://l.test/FeatureServer/0", "date_field": "rec", "uid": "doc",
        "doc_type": "DEED", "doc_type_raw": "test deed", "consideration": "price",
        "date_format": {"rec": "ymd"},
        "rewrite": {"span": {"pattern": r"^(\d{3})(\d{3})(\d{5})$", "replace": r"\1-\2-\3"}},
        "parties": [{"role": "grantor", "name": "seller"}, {"role": "grantee", "name": "buyer"}],
        "parcel": {"kind": "pin", "field": "span", "county_fips": "50027"},
        "terms": {"summary": "s", "checked_on": "2026-11-25", "cost_model": "free"},
    }  # fmt: skip
    base.update(over)
    path = tmp_path / "z.yaml"
    path.write_text(yaml.safe_dump(base))
    return path


def _facts(cls: type, rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    body = json.dumps({"rows": rows}).encode()
    return [(r.table, dict(r.row)) for r in cls().normalize(Fetched(cls.source_id, "x", AT, 200,
                                                                    body, ""))]  # fmt: skip


def test_date_formats() -> None:
    assert ymd_date(20150121) == ymd_date("20150121") == ymd_date(20150121.0) == "2015-01-21"
    assert ymd_date("00000000") is None and ymd_date("99999999") is None
    assert ymd_date(None) is None and ymd_date(True) is None and ymd_date("2015-01-21") is None
    assert mdy_date("7/2/2012 12:00:00 AM") == mdy_date("07/02/2012") == "2012-07-02"
    assert mdy_date("2012-07-02") is None and mdy_date(None) is None


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"date_format": {"rec": "dmy"}}, "date_format"),
        ({"date_format": {"rec": "mdy"}}, "mdy date windows"),
        ({"rewrite": {"span": {"pattern": "x"}}}, "pattern and replace"),
    ],
)
def test_config_validation(tmp_path: Path, over: dict[str, Any], message: str) -> None:
    with pytest.raises(LienConfigError, match=message):
        load_deed_config(_cfg(tmp_path, **over))


def test_windows_query_the_raw_date(tmp_path: Path) -> None:
    window = {"from": "2015-01-01", "to": "2016-01-01"}
    cls = deed_adapter_for(load_deed_config(_cfg(tmp_path, where="x = 1")))
    assert cls().where(window) == "(x = 1) AND rec >= 20150101 AND rec < 20160101"
    text = deed_adapter_for(load_deed_config(_cfg(tmp_path, date_is_text=True)))
    assert text().where(window) == "rec >= '20150101' AND rec < '20160101'"
    mdy = deed_adapter_for(load_deed_config(_cfg(
        tmp_path, api="socrata", portal="https://p.test", dataset="abcd-1234",
        date_format={"rec": "mdy"})))  # fmt: skip
    assert mdy().where(window) == "(rec LIKE '%/2015 %' OR rec LIKE '%/2015')"
    plain = deed_adapter_for(load_deed_config(_cfg(tmp_path, date_format={})))
    assert plain().where(window) == "rec >= DATE '2015-01-01' AND rec < DATE '2016-01-01'"


def test_rows_get_iso_dates_and_rewritten_parcel_ids(tmp_path: Path) -> None:
    cls = deed_adapter_for(load_deed_config(_cfg(tmp_path)))
    rows = [
        {"doc": "D1", "rec": 20250107, "span": "78625010932", "seller": "A", "buyer": "B",
         "price": 250000},
        {"doc": "D2", "rec": "00000000", "span": "78625010932", "seller": "C", "buyer": "D"},
    ]  # fmt: skip
    out = _facts(cls, rows)
    (inst,) = [r for t, r in out if t == "instrument"]  # D2 has no date: skipped
    assert inst["recorded_on"] == date(2025, 1, 7) and inst["doc_type"] == "DEED"
    assert str(inst["consideration"]) == "250000"
    (link,) = [r for t, r in out if t == "instrument_parcel"]
    assert link["parcel_uid"] == "50027-786-250-10932"
    assert sorted(r["role"] for t, r in out if t == "instrument_party") == ["grantee", "grantor"]


def test_real_deed_configs_load() -> None:
    ids = {a.source_id for a in all_deed_adapters()}
    assert {"ct.cama.sales", "vt.tax.property_transfers", "co.denver.property_sales"} <= ids


def _walk(obj: object, fields: tuple[str, ...]) -> list[str]:
    if isinstance(obj, dict):
        bad = []
        for k, v in obj.items():
            if k in fields and isinstance(v, str) and v.strip():
                if not (v.startswith("TESTOWNER") or v.endswith(" TEST ST")):
                    bad.append(f"{k}={v[:3]}...")
            else:
                bad += _walk(v, fields)
        return bad
    if isinstance(obj, list):
        return [b for v in obj for b in _walk(v, fields)]
    return []


def test_deed_fixtures_are_pseudonymized_and_order_free() -> None:
    checked = 0
    for cls in all_deed_adapters():
        for path in sorted((FIXTURES / cls.source_id).glob("*.json")):
            data = json.loads(path.read_text())
            assert _walk(data, cls.pii_fields) == [], path
            rows = data["rows"]
            fwd = sorted(json.dumps(r, sort_keys=True, default=str) for r in _facts(cls, rows))
            back = sorted(json.dumps(r, sort_keys=True, default=str)
                          for r in _facts(cls, rows[::-1]))  # fmt: skip
            assert fwd == back, cls.source_id
            assert any(t == "instrument_parcel" for t, _ in _facts(cls, rows)), cls.source_id
            checked += 1
    assert checked == len(all_deed_adapters())


def test_deed_adapters_meet_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    for cls in all_deed_adapters():
        check_contract(cls, sorted((FIXTURES / cls.source_id).glob("*.json")), empty_db)
