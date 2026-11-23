"""Allegheny County assessments: values per PIN, no owner data."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from equity.adapters.base import Fetched
from equity.adapters.pa.allegheny_assessments import AlleghenyAssessments


def test_values_and_homestead_per_pin() -> None:
    body = {"records": [
        {"PARID": "0001D00128000000", "TAXYEAR": 2026.0, "CLASSDESC": "RESIDENTIAL",
         "HOMESTEADFLAG": "HOM", "COUNTYTOTAL": 90000.0, "FAIRMARKETLAND": 20000.0,
         "FAIRMARKETBUILDING": 80000.0, "FAIRMARKETTOTAL": 100000.0},
        {"PARID": "0001D00132000000", "TAXYEAR": 2026.0, "HOMESTEADFLAG": None,
         "FAIRMARKETTOTAL": -5},  # a negative value is not a value
        {"PARID": "", "TAXYEAR": 2026.0},
        {"PARID": "0001D00133000000", "TAXYEAR": None},
    ]}  # fmt: skip
    f = Fetched("pa.allegheny.assessments", "x", datetime(2026, 11, 22, tzinfo=UTC), 200,
                json.dumps(body).encode(), "application/json")  # fmt: skip
    rows = [r.row for r in AlleghenyAssessments().normalize(f) if r.table == "parcel_assessment"]
    assert [r["parcel_uid"] for r in rows] == ["42003-0001D00128000000", "42003-0001D00132000000"]
    first, second = rows
    assert (first["appraised_total"], first["assessed_value"], first["homestead"]) == (
        Decimal("100000.0"), Decimal("90000.0"), True)  # fmt: skip
    assert first["valid_from"] == date(2026, 1, 1) and first["tax_class"] == "RESIDENTIAL"
    assert second["appraised_total"] is None and second["homestead"] is False


def test_partitions_are_pin_prefixes_and_only_digits_reach_sql() -> None:
    a = AlleghenyAssessments()
    parts = list(a.partitions())
    assert len(parts) == 100 and parts[0] == {"prefix": "00"} and parts[-1] == {"prefix": "99"}
    assert "LIKE '07%'" in a._sql("07", 10, 0)
    with pytest.raises(ValueError, match="bad PIN prefix"):
        a._sql("0'; DROP", 10, 0)
