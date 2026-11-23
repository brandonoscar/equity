"""Omaha tax liens: certificates owed by named (joint) taxpayers; county liens by the PIN."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.ne_douglas_tax_liens import DouglasTaxLiens


def _norm(layer: str, rows: list[dict[str, object]]) -> list[tuple[str, dict[str, object]]]:
    body = json.dumps({"layer": layer, "rows": rows}).encode()
    f = Fetched("ne.douglas.tax_liens", "x", datetime(2026, 11, 23, tzinfo=UTC), 200, body,
                "application/json")  # fmt: skip
    return [(r.table, dict(r.row)) for r in DouglasTaxLiens().normalize(f)]


def test_auction_certificates_name_joint_taxpayers() -> None:
    out = _norm("auction", [{"pin": "0104720004", "tax_sale_year": "2026", "item_num": "7",
                             "cert_amt": "$1,234.56", "taxpayer": "ANN LEE*BO LEE",
                             "mail_address1": "1 TEST ST", "city": "OMAHA", "state": "NE",
                             "zip": "68102"}])  # fmt: skip
    (inst,) = [r for t, r in out if t == "instrument"]
    assert (inst["principal_amount"], inst["recorded_on"]) == (Decimal("1234.56"),
                                                               date(2026, 1, 1))  # fmt: skip
    assert [r["parcel_uid"] for t, r in out if t == "instrument_parcel"] == ["31055-0104720004"]
    assert sorted(r["raw_name"] for t, r in out if t == "party") == ["ANN LEE", "BO LEE"]


def test_county_liens_have_no_named_debtor() -> None:
    out = _norm("county", [{"pin": "0104720004", "year": 2024, "amt": 162, "objectid": 1},
                           {"pin": None, "year": 2024, "amt": 5, "objectid": 2}])  # fmt: skip
    assert len([1 for t, _ in out if t == "instrument"]) == 1
    assert not [1 for t, _ in out if t == "party"]


def test_unknown_layer_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown layer"):
        DouglasTaxLiens().fetch(FetchRequest({"layer": "x"}))
