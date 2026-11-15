from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.wv.delinquent import WVDelinquentProperties

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures/adapters/wv.statewide.delinquent/county_number-31_limit-20.json"
)
AT = datetime(2026, 11, 15, 12, tzinfo=UTC)


def rows(content: bytes) -> list[tuple[str, dict[str, Any]]]:
    f = Fetched("wv.statewide.delinquent", "fixture://d", AT, 200, content, "application/json")
    return [(r.table, dict(r.row)) for r in WVDelinquentProperties().normalize(f)]


def test_fixture() -> None:
    out = rows(FIXTURE.read_bytes())
    snaps = [r for t, r in out if t == "tax_delinquency_snapshot"]
    assert Counter(t for t, _ in out)["source_record"] == len(snaps) == 20
    first = next(r for r in snaps if r["certificate_no"] == "305911")
    assert first["parcel_uid"] == "54061-010004003300000000"
    assert first["status_raw"] == "Redeemed"
    assert first["observed_on"] == date(2026, 11, 15)
    assert {r["status_raw"] for r in snaps} <= {
        "Redeemed", "No Bid", "Deed", "Dismissed", "Sold - Did Not Follow Through"
    }  # fmt: skip


def _a(**kw: Any) -> dict[str, Any]:
    base = {"OBJECTID": 1, "CleanParcelID": "31010004003300000000", "CountyID": "31",
            "status": "No Bid", "certno": 7, "MAX_certno": 7, "FREQUENCY": 2,
            "deed_book": "NULL", "page_number": " 56 ", "description": "  Pt  Lot 45 ",
            "district": "X", "map_1": "4", "parcel_1": "33"}  # fmt: skip
    base.update(kw)
    return base


def test_nulls_whitespace_duplicates_and_skips() -> None:
    body = json.dumps({"layer": "x", "where": "y", "attributes": [
        _a(OBJECTID=9, status="Deed"), _a(OBJECTID=3), _a(status="NULL", certno=8),
        _a(CleanParcelID=None, certno=9), _a(certno=10, FREQUENCY=None),
    ]}).encode()  # fmt: skip
    snaps = {r["certificate_no"]: r for t, r in rows(body) if t == "tax_delinquency_snapshot"}
    assert sorted(snaps) == ["10", "7"]
    assert snaps["7"]["status_raw"] == "No Bid"  # lowest OBJECTID wins
    assert snaps["7"]["deed_book"] is None
    assert snaps["7"]["deed_page"] == "56"
    assert snaps["7"]["legal_desc_raw"] == "Pt Lot 45"
    assert snaps["10"]["times_listed"] is None


def test_where() -> None:
    assert WVDelinquentProperties().where(FetchRequest({"county_number": "31"})) == "CountyID='31'"
    with pytest.raises(ValueError, match="1-55"):
        WVDelinquentProperties().where(FetchRequest({"county_number": "0"}))


def test_partitions_cover_all_55_counties() -> None:
    assert len(list(WVDelinquentProperties().partitions())) == 55
