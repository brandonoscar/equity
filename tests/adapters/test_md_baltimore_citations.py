"""Baltimore environmental citation liens: on the block/lot parcel, satisfied when paid."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from equity.adapters.base import Fetched
from equity.adapters.md_baltimore_citations import BaltimoreCitationLiens, parcel_uid


def test_parcel_uid_matches_blocklot() -> None:
    assert parcel_uid("2302 ", "012 ") == "24510-2302012"
    assert parcel_uid("8186 ", "019A") == "24510-8186019A"
    assert parcel_uid(None, "012") is None


def test_liened_citations_only_and_paid_ones_satisfied() -> None:
    day = 1232928000000  # 2009-01-26
    body = {"rows": [
        {"CitationNo": "1", "LienCode": "L", "CitationStatus": "O       ", "Balance": 300,
         "ViolationDate": day, "Block": "2302 ", "Lot": "012 "},
        {"CitationNo": "2", "LienCode": "L", "CitationStatus": "P       ", "Balance": 0,
         "ViolationDate": day, "Block": "2302 ", "Lot": "012 "},
        {"CitationNo": "3", "LienCode": "N", "CitationStatus": "O", "Balance": 50,
         "ViolationDate": day, "Block": "1", "Lot": "1"},  # not a lien
        {"CitationNo": "4", "LienCode": "L", "CitationStatus": "O", "Balance": 10,
         "ViolationDate": day, "Block": "", "Lot": "1"},  # no parcel
    ]}  # fmt: skip
    f = Fetched("md.baltimore_city.citation_liens", "x", datetime(2026, 11, 23, tzinfo=UTC),
                200, json.dumps(body).encode(), "application/json")  # fmt: skip
    rows = list(BaltimoreCitationLiens().normalize(f))
    inst = {r.row["instrument_number"]: r.row for r in rows if r.table == "instrument"}
    assert set(inst) == {"1", "2"}
    assert (
        inst["1"]["principal_amount"] == Decimal("300")
        and "satisfied" not in inst["1"]["doc_type_raw"]
    )
    assert inst["2"]["doc_type_raw"].endswith("(satisfied)")
    lots = {r.row["parcel_uid"] for r in rows if r.table == "instrument_parcel"}
    assert lots == {"24510-2302012"}
