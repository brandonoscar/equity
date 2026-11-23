"""PACER spending guard: pricing, the quarterly ceiling, the ledger (equity.pacer)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from equity import pacer


def _budget(tmp_path: Path, ceiling: str | None = "28.00",
            when: datetime = datetime(2026, 11, 23, tzinfo=UTC)) -> pacer.Budget:  # fmt: skip
    fees = replace(pacer.Fees.load(), ceiling=None if ceiling is None else Decimal(ceiling))
    return pacer.Budget(tmp_path / "ledger.jsonl", fees, now=lambda: when)


def test_prices_follow_the_fee_schedule() -> None:
    fees = pacer.Fees.load()
    assert pacer.price(fees, "document", 7) == Decimal("0.70")
    assert pacer.price(fees, "document", 250) == Decimal("3.00")  # capped per document
    assert pacer.price(fees, "docket_report", 45) == Decimal("3.00")
    assert pacer.price(fees, "search", 45) == Decimal("4.50")  # search results are uncapped
    assert pacer.price(fees, "document", 0) == Decimal("0.00")
    with pytest.raises(ValueError, match="pages"):
        pacer.price(fees, "document", -1)
    assert pacer.quarter_of(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-Q1"
    assert pacer.quarter_of(datetime(2026, 12, 31, tzinfo=UTC)) == "2026-Q4"


def test_every_request_is_refused_until_the_ceiling_is_set(tmp_path: Path) -> None:
    assert pacer.Fees.load().ceiling is None  # config/pacer.yaml: Brandon's decision
    with pytest.raises(pacer.BudgetExceeded, match="quarterly_ceiling is not set"):
        _budget(tmp_path, None).authorize("document", 3, "flmb", "8:26-bk-00001")
    assert not (tmp_path / "ledger.jsonl").exists()


def test_the_ceiling_holds_and_the_ledger_records_each_charge(tmp_path: Path) -> None:
    b = _budget(tmp_path, "10.00")
    first = b.authorize("document", 30, "flmb", "8:26-bk-00001", "Schedule A/B")
    assert first["cost"] == "3.00" and first["alert"] is False
    b.authorize("document", 30, "flmb", "8:26-bk-00001", "Schedule D")
    third = b.authorize("search", 22, "flmb", "", "case search")  # 2.20, total 8.20
    assert third["quarter_total"] == "8.20" and third["alert"] is True  # >= 80% of 10
    with pytest.raises(pacer.BudgetExceeded, match="exceed the ceiling"):
        b.authorize("document", 30, "flmb", "8:26-bk-00002")  # 11.20 > 10
    assert len(b.entries()) == 3 and b.spent() == Decimal("8.20")
    status = b.status()
    assert status == {"quarter": "2026-Q4", "spent": "8.20", "ceiling": "10.00",
                      "remaining": "1.80", "waived_if_quarter_ends_now": True,
                      "requests": 3}  # fmt: skip
    nextq = pacer.Budget(b.ledger, b.fees, now=lambda: datetime(2027, 1, 2, tzinfo=UTC))
    assert nextq.spent() == Decimal("0")  # a new quarter starts from zero
    assert nextq.status()["remaining"] == "10.00"


def test_status_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert pacer.main(["status", "--ledger", str(tmp_path / "none.jsonl")]) == 0
    out = capsys.readouterr().out
    assert '"ceiling": null' in out and '"requests": 0' in out
