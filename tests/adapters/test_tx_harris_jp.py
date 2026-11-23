"""Harris County JP judgments: the party judged against is the debtor, with their address."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.tx_harris_jp import HarrisJPJudgments


def _row(**kw: str) -> dict[str, str]:
    base = {"Case Number": "CV1", "Case Type": "Debt Claim", "Judgment Date": "11/03/2026",
            "Judgment Amount": "1,234.50", "Judgment Against ": "ANN LEE",
            "Judgment In Favor Of ": "TEST BANK NA", "Plaintiff Name": "TEST BANK NA",
            "Defendant Name": "ANN LEE", "Defendant Addr Line 1 ": "1 TEST ST",
            "Defendant Addr City ": "HOUSTON", "Defendant Addr State": "TX",
            "Defendant Addr Zip": "77002-1234"}  # fmt: skip
    return {**base, **kw}


def test_judgments() -> None:
    rows = [_row(), _row(), _row(**{"Case Number": "CV2", "Judgment Amount": "0"}),
            _row(**{"Case Number": "CV3", "Judgment Against ": "BO RAY",
                    "Second Defendant Name": "BO RAY",
                    "Second Defendant Addr Line 1 ": "9 TEST RD"})]  # fmt: skip
    f = Fetched("tx.harris.jp.judgments", "x", datetime(2026, 11, 23, tzinfo=UTC), 200,
                json.dumps({"rows": rows}).encode(), "application/json")  # fmt: skip
    out = list(HarrisJPJudgments().normalize(f))
    inst = {r.row["instrument_number"]: r.row for r in out if r.table == "instrument"}
    assert set(inst) == {"CV1", "CV3"}  # duplicate row once; zero amount dropped
    assert (inst["CV1"]["principal_amount"], inst["CV1"]["recorded_on"]) == (
        Decimal("1234.50"), date(2026, 11, 3))  # fmt: skip
    roles = {(r.row["role"]) for r in out if r.table == "instrument_party"}
    assert roles == {"debtor", "creditor"}
    addrs = [r.row for r in out if r.table == "address"]
    assert {(a["line1"], a["zip5"]) for a in addrs} >= {("1 TEST ST", "77002")}
    assert any(a["line1"] == "9 TEST RD" for a in addrs)  # second defendant's address


def test_partitions_and_window_guard() -> None:
    parts = list(HarrisJPJudgments().partitions())
    assert parts[:2] == [{"from": "2010-01-01", "to": "2010-01-14"},
                         {"from": "2010-01-15", "to": "2010-01-28"}]  # fmt: skip
    with pytest.raises(ValueError, match="90 days"):
        HarrisJPJudgments().fetch(FetchRequest({"from": "2026-01-01", "to": "2026-06-01"}))
