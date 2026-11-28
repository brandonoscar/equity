"""Assessment ratios: NY RAR and equalization rates per SWIS, CT ratios per town and class."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from equity.adapters.assessment_ratios import (
    ADAPTERS,
    CTEqualizedGrandList,
    NYEqualizationRates,
    NYResidentialAssessmentRatios,
)
from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import PoliteClient

FIX = Path(__file__).parents[1] / "fixtures" / "adapters"
AT = datetime(2026, 11, 26, tzinfo=UTC)


def _facts(cls: type, rows: list[dict[str, str]]) -> list[dict[str, object]]:
    f = Fetched(cls.source_id, "x", AT, 200, json.dumps({"rows": rows}).encode(), "")  # type: ignore[attr-defined]
    return [dict(r.row) for r in cls().normalize(f) if r.table == "assessment_ratio"]


def test_ny_ratios() -> None:
    rows = [{"rate_year": "2021", "swis_code": "010300", "county_name": "Albany",
             "municipality_name": "Cohoes", "residential_assessment_ratio": "45.91"},
            {"rate_year": "2021", "swis_code": "010300", "county_name": "Albany",
             "municipality_name": "Cohoes", "residential_assessment_ratio": "45.91"},
            {"rate_year": "x", "swis_code": "010300", "residential_assessment_ratio": "1"},
            {"rate_year": "2021", "swis_code": "0103", "residential_assessment_ratio": "1"},
            {"rate_year": "2021", "swis_code": "010400",
             "residential_assessment_ratio": "0"}]  # fmt: skip
    (got,) = _facts(NYResidentialAssessmentRatios, rows)  # duplicates and bad rows dropped
    assert {k: got[k] for k in ("geo_level", "geo_id", "geo_name", "year", "property_class",
                                "ratio_kind", "ratio_pct")} == {
        "geo_level": "ny_swis", "geo_id": "010300", "geo_name": "Cohoes", "year": 2021,
        "property_class": "residential", "ratio_kind": "residential_assessment_ratio",
        "ratio_pct": 45.91}  # fmt: skip
    (county,) = _facts(NYEqualizationRates, [{"rate_year": "2020", "swis_code": "010000",
                                              "county_name": "Albany",
                                              "equalization_rate": "79.31"}])  # fmt: skip
    assert (county["geo_name"], county["property_class"], county["ratio_pct"]) == (
        "Albany", "all", 79.31)  # fmt: skip


def test_ct_ratios_by_class() -> None:
    row = {"town_code": "169", "town_name": "Woodstock", "grand_list_year": "2024",
           "residential_ratio": "45.64", "apartments_ratio": "47.37", "cip_ratio": "63.55",
           "vacant_ratio": "72.95", "total_personal_property_ratio": "n/a"}  # fmt: skip
    got = _facts(CTEqualizedGrandList, [row, {"town_code": "x"}])
    assert {(f["property_class"], f["ratio_pct"]) for f in got} == {
        ("residential", 45.64), ("apartments", 47.37), ("commercial_industrial", 63.55),
        ("vacant", 72.95)}  # fmt: skip
    assert {f["geo_id"] for f in got} == {"169"}


def test_fixtures_fetch_and_health() -> None:
    for cls in ADAPTERS:
        path = next((FIX / cls.source_id).glob("*.json"))
        f = Fetched(cls.source_id, "x", AT, 200, path.read_bytes(), "")
        assert any(r.table == "assessment_ratio" for r in cls().normalize(f)), cls.source_id

    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        body = [{"rate_year": "2021", "swis_code": "010300", "equalization_rate": "90"}]
        return 200, json.dumps(body).encode(), "application/json"

    a = NYEqualizationRates(PoliteClient(min_interval_s=0, transport=transport,
                                         sleep=lambda s: None))  # fmt: skip
    assert list(a.partitions()) == [{}]
    assert a.source_row()["kind"] == "assessor"
    assert json.loads(a.fetch(FetchRequest({"limit": "1"})).content)["rows"][0]["swis_code"] == \
        "010300"  # fmt: skip
    assert a.health().ok
    assert len(json.loads(a.fetch(FetchRequest({})).content)["rows"]) == 1
