"""Providence tax roll: owners, addresses and assessed value keyed to the statewide PlatLot."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from equity.adapters.base import Fetched
from equity.adapters.ri_providence import ProvidenceTaxRoll


def test_roll_rows() -> None:
    body = {"rows": [
        {"tax_map": "041-0029-0000", "class": "01", "short_desc": "SINGLE FAMILY",
         "civic": "12", "street": "TEST", "suffix": "ST", "city": "PROVIDENCE",
         "zip_postal": "02906", "first_name": "ANN", "last_name": "LEE",
         "company": "LEE FAMILY TRUST", "civic_1": "9", "street_1": "MAIL", "s_suffix": "AVE",
         "city_1": "BOSTON", "state": "MA", "zip_postal_1": "02101-1234",
         "total_assmt": "350000"},
        {"tax_map": "041-0029-0000", "last_name": "DUPLICATE"},
        {"tax_map": "BAD", "last_name": "SKIPPED"},
        {"tax_map": "005-0379-0000", "company": "TEST LLC", "total_assmt": "-1"},
    ]}  # fmt: skip
    f = Fetched("ri.providence.parcels", "x", datetime(2026, 11, 23, tzinfo=UTC), 200,
                json.dumps(body).encode(), "application/json")  # fmt: skip
    rows = list(ProvidenceTaxRoll().normalize(f))
    by = lambda t: [r.row for r in rows if r.table == t]  # noqa: E731
    assert [p["parcel_uid"] for p in by("parcel")] == ["44007-PR005-0379-0000",
                                                       "44007-PR041-0029-0000"]  # fmt: skip
    people = {p["raw_name"]: p for p in by("party")}
    assert set(people) == {"ANN LEE", "LEE FAMILY TRUST", "TEST LLC"}
    assert (people["ANN LEE"]["first_name"], people["ANN LEE"]["last_name"]) == ("ANN", "LEE")
    assert people["ANN LEE"]["party_kind"] == "person"
    mail = {a["address_id"]: a for a in by("address")}[people["ANN LEE"]["address_id"]]
    assert (mail["city"], mail["state"], mail["zip5"]) == ("BOSTON", "MA", "02101")
    (v,) = by("parcel_assessment")  # the negative assessment is dropped
    assert (v["parcel_uid"], v["assessed_value"], v["tax_year"]) == (
        "44007-PR041-0029-0000", Decimal("350000"), 2024)  # fmt: skip
