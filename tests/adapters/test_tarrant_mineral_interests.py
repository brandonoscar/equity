"""Tarrant mineral interests: roll 03 accounts with a value, as owner records."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

from equity.adapters.base import Fetched
from equity.adapters.tx.mineral_interests import TarrantMineralInterests, mineral_accounts

AT = datetime(2025, 12, 31, tzinfo=UTC)


def _master(account: str, roll: str, owner: str, land: int, imp: int) -> str:
    line = [" "] * 781
    for (a, b), v in {
        (1, 30): account,
        (34, 35): roll,
        (36, 155): "OLIVER #1 91210030-000 BRG LONE STAR 0.01228200",
        (327, 376): owner,
        (427, 456): "1 MAIN ST",
        (487, 516): "FORT WORTH",
        (517, 536): "TX",
        (537, 554): "76102",
        (667, 677): str(land).zfill(11),
        (678, 688): str(imp).zfill(11),
    }.items():
        line[a - 1 : b] = list(v.ljust(b - a + 1)[: b - a + 1])
    return "".join(line)


def test_mineral_accounts_with_a_value_become_owner_records() -> None:
    lines = [
        _master("00010335366", "03", "OLIVER CHARLES TR", 0, 1799),
        _master("00010335367", "03", "NO VALUE LLC", 0, 0),  # not producing
        _master("00000000001", "01", "ANN LEE", 5000, 90000),
    ]  # real property
    rows = mineral_accounts(lines)
    assert [r["account"] for r in rows] == ["00010335366"]
    body = json.dumps(
        {"file": "TaxRoll20251125.zip", "roll_date": "2025-11-25", "rows": rows}
    ).encode()
    out = [(t.table, dict(t.row)) for t in TarrantMineralInterests().normalize(
        Fetched("tx.tarrant.mineral_interests", "x", AT, 200, body, ""))]  # fmt: skip
    (parcel,) = [r for t, r in out if t == "parcel"]
    assert parcel["parcel_uid"] == "48439-MIN-00010335366"
    assert parcel["land_use_desc"].startswith("Mineral interest: OLIVER #1")
    (val,) = [r for t, r in out if t == "parcel_assessment"]
    assert (val["tax_year"], val["appraised_total"], val["valid_from"]) == (
        2025, Decimal(1799), date(2025, 1, 1))  # fmt: skip
    (snap,) = [r for t, r in out if t == "owner_snapshot"]
    assert snap["observed_on"] == date(2025, 11, 25)
    assert [r["raw_name"] for t, r in out if t == "party"] == ["OLIVER CHARLES TR"]
