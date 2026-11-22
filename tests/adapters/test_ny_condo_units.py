"""NYC condo unit lot -> billing lot links."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from equity.adapters.base import Fetched
from equity.adapters.ny.condo_units import NycCondoUnits


def test_units_link_to_their_condo_billing_lot() -> None:
    body = {
        "units": [
            {"unit_bbl": "1000041002", "condo_key": "100835", "unit_designation": "2A"},
            {"unit_bbl": "1000041001", "condo_key": "100835"},
            {"unit_bbl": "1000041001", "condo_key": "100835"},  # repeated unit: kept once
            {"unit_bbl": "3023101001", "condo_key": "999999"},  # condo without a billing lot
            {"unit_bbl": "12345", "condo_key": "100835"},  # malformed lot
            {"unit_bbl": "1000047501", "condo_key": "100835"},  # the billing lot itself
        ],
        "condos": [{"condo_key": "100835", "condo_billing_bbl": "1000047501"},
                   {"condo_key": "999999", "condo_billing_bbl": None}],
    }  # fmt: skip
    f = Fetched("ny.nyc.dof.condo_units", "x", datetime(2026, 11, 22, tzinfo=UTC), 200,
                json.dumps(body).encode(), "application/json")  # fmt: skip
    rows = [r.row for r in NycCondoUnits().normalize(f) if r.table == "parcel_link"]
    assert [(r["from_parcel_uid"], r["to_parcel_uid"], r["detail"]) for r in rows] == [
        ("36061-6201001000041001", "36061-6201001000047501", None),
        ("36061-6201001000041002", "36061-6201001000047501", "2A"),
    ]
    assert {r["link_type"] for r in rows} == {"condo_unit_of"}
    assert {r["jurisdiction"] for r in rows} == {"36061"}
