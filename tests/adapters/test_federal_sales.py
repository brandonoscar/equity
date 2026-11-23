"""HUD FHA REO and Federal Register realty notices: offline, on recorded fixtures."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from equity.adapters.base import Fetched
from equity.adapters.federal.federal_register import QUERIES, FederalRegisterRealty
from equity.adapters.federal.hud_reo import HudFhaReo, jurisdiction

FIX = Path(__file__).parents[1] / "fixtures" / "adapters"
AT = datetime(2026, 11, 23, tzinfo=UTC)


def _rows(cls: type, path: Path) -> list[tuple[str, dict[str, object]]]:
    f = Fetched(cls.source_id, "fixture://x", AT, 200, path.read_bytes(), "application/json")  # type: ignore[attr-defined]
    return [(r.table, dict(r.row)) for r in cls().normalize(f)]


def test_hud_reo_rows_are_deeds_to_hud_in_the_block_county() -> None:
    out = _rows(HudFhaReo, FIX / "us.hud.fha_reo" / "limit-25.json")
    n = Counter(t for t, _ in out)
    assert n["instrument"] == n["instrument_party"] == 25 and n["address"] == 25
    inst = [r for t, r in out if t == "instrument"]
    assert {r["doc_type"] for r in inst} == {"DEED"}
    assert all(r["legal_desc_raw"] for r in inst)
    parties = {r["raw_name"] for t, r in out if t == "party"}
    assert parties == {"SECRETARY OF HOUSING AND URBAN DEVELOPMENT"}
    assert jurisdiction({"CENSUS_BLOCK": "391130015001001"}) == "39113"
    assert jurisdiction({"CENSUS_BLOCK": None, "FIPS_STATE_CODE": 6}) == "06"
    assert jurisdiction({}) is None


def test_hud_reo_skips_rows_without_case_or_acquired_date() -> None:
    body = json.dumps({"rows": [
        {"CASE_NUM": "1", "DATE_ACQUIRED": None, "CENSUS_BLOCK": "391130015001001"},
        {"CASE_NUM": None, "DATE_ACQUIRED": 1700000000000, "CENSUS_BLOCK": "391130015001001"},
        {"CASE_NUM": "2", "DATE_ACQUIRED": 4102444800000, "CENSUS_BLOCK": "391130015001001"},
    ]}).encode()  # fmt: skip
    rows = list(HudFhaReo().normalize(Fetched("us.hud.fha_reo", "x", AT, 200, body, "")))
    assert rows == []  # no date, no case, acquired after retrieval


def test_federal_register_notices_and_partitions() -> None:
    path = next((FIX / "us.federalregister.realty_notices").glob("*.json"))
    out = _rows(FederalRegisterRealty, path)
    inst = [r for t, r in out if t == "instrument"]
    assert inst and {r["doc_type"] for r in inst} == {"OTHER"}
    assert {r["doc_type_raw"] for r in inst} == {QUERIES["realty"]["label"]}
    assert all(str(r["recorded_on"]).startswith("2026") for r in inst)
    assert any(t == "party" and r["party_kind"] == "org" for t, r in out)
    parts = list(FederalRegisterRealty().partitions())
    assert {"query": "homeless", "year": "2000"} in parts
    assert len({p["query"] for p in parts}) == len(QUERIES)
    params = dict(FederalRegisterRealty()._params("lease_sale", 2025, 2, 50))
    assert params["conditions[agencies][]"] == "land-management-bureau"
    assert params["conditions[publication_date][gte]"] == "2025-01-01" and params["page"] == "2"
