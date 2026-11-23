"""Detroit blight judgments: owed by the named owner, on the parcel, satisfied when paid."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

from equity.adapters.base import Fetched
from equity.adapters.mi_detroit_blight import DetroitBlightJudgments


def test_judged_tickets() -> None:
    base = {"disposition": "Responsible by Default", "judgment_date": "2005-03-22",
            "parcel_id": "01004105.", "property_owner_name": "TEST OWNER LLC",
            "property_owner_address": "1 TEST ST", "property_owner_city": "DETROIT",
            "property_owner_state": "MI", "property_owner_zip_code": "48226"}  # fmt: skip
    rows = [
        {**base, "ticket_number": "T1", "amt_judgment": 305, "amt_balance_due": 305},
        {**base, "ticket_number": "T2", "amt_judgment": 305, "amt_balance_due": 0},
        {**base, "ticket_number": "T3", "amt_judgment": 0, "amt_balance_due": 0},
        {**base, "ticket_number": "T4", "amt_judgment": 50, "judgment_date": None},
    ]
    f = Fetched("mi.detroit.blight_judgments", "x", datetime(2026, 11, 23, tzinfo=UTC), 200,
                json.dumps({"rows": rows}).encode(), "application/json")  # fmt: skip
    out = list(DetroitBlightJudgments().normalize(f))
    inst = {r.row["instrument_number"]: r.row for r in out if r.table == "instrument"}
    assert set(inst) == {"T1", "T2"}
    assert inst["T1"]["principal_amount"] == Decimal("305")
    assert inst["T1"]["recorded_on"] == date(2005, 3, 22)
    assert inst["T2"]["doc_type_raw"].endswith("(satisfied)")
    assert {r.row["parcel_uid"] for r in out if r.table == "instrument_parcel"} == {
        "26163-01004105."
    }
    (party,) = {r.row["raw_name"] for r in out if r.table == "party"}
    assert party == "TEST OWNER LLC"
