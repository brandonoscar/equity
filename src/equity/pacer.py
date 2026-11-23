"""PACER spending guard: every PACER request is priced, checked against the quarterly ceiling
and written to a ledger before it may be made. No PACER client exists yet; anything that
fetches from PACER must call `Budget.authorize()` first and fetch only if it returns.

    uv run python -m equity.pacer status          # this quarter's spend, ceiling, remaining

Fees (config/pacer.yaml, from the judiciary's schedule): pages x per_page, capped per
document at document_cap except for search results, name reports and transcripts; a quarter
totalling quarterly_waiver or less is waived by PACER, which is why the ceiling sits below it.
The ceiling is Brandon's decision: while it is null every request is refused.

Ledger: data/private/pacer_ledger.jsonl (account data; data/ is git-ignored), one JSON line
per authorized charge: {ts, quarter, kind, court_id, case, document, pages, cost}.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from equity.config import _load

LEDGER = Path("data") / "private" / "pacer_ledger.jsonl"
CENT = Decimal("0.01")


class BudgetExceeded(RuntimeError):
    """The request would take the quarter past the ceiling (or no ceiling is set)."""


def quarter_of(ts: datetime) -> str:
    return f"{ts.year}-Q{(ts.month - 1) // 3 + 1}"


@dataclass(frozen=True)
class Fees:
    per_page: Decimal
    document_cap: Decimal
    uncapped_kinds: frozenset[str]
    quarterly_waiver: Decimal
    ceiling: Decimal | None
    alert_fraction: Decimal

    @staticmethod
    def load(config_dir: Path | None = None) -> Fees:
        data = _load("pacer.yaml", config_dir)
        f = data["fees"]
        ceiling = data.get("quarterly_ceiling")
        return Fees(
            per_page=Decimal(str(f["per_page"])),
            document_cap=Decimal(str(f["document_cap"])),
            uncapped_kinds=frozenset(str(k) for k in f.get("uncapped_kinds") or ()),
            quarterly_waiver=Decimal(str(f["quarterly_waiver"])),
            ceiling=None if ceiling is None else Decimal(str(ceiling)),
            alert_fraction=Decimal(str(data.get("alert_fraction", "0.8"))),
        )


def price(fees: Fees, kind: str, pages: int) -> Decimal:
    """What PACER charges for one request: pages x rate, capped per document unless the kind
    is uncapped (searches, reports, transcripts)."""
    if pages < 0:
        raise ValueError("pages must be >= 0")
    cost = fees.per_page * pages
    if kind not in fees.uncapped_kinds:
        cost = min(cost, fees.document_cap)
    return cost.quantize(CENT, rounding=ROUND_HALF_UP)


class Budget:
    def __init__(self, ledger: Path = LEDGER, fees: Fees | None = None,
                 now: Any = None) -> None:  # fmt: skip
        self.ledger = ledger
        self.fees = fees or Fees.load()
        self._now = now or (lambda: datetime.now(UTC))

    def entries(self) -> list[dict[str, Any]]:
        if not self.ledger.exists():
            return []
        return [json.loads(line) for line in self.ledger.read_text().splitlines() if line.strip()]

    def spent(self, quarter: str | None = None) -> Decimal:
        q = quarter or quarter_of(self._now())
        return sum((Decimal(str(e["cost"])) for e in self.entries() if e["quarter"] == q),
                   Decimal("0"))  # fmt: skip

    def authorize(self, kind: str, pages: int, court_id: str, case: str,
                  document: str = "") -> dict[str, Any]:  # fmt: skip
        """Price the request, refuse it past the ceiling, else record it and return the entry
        (with `alert` true once the quarter reaches alert_fraction of the ceiling)."""
        if self.fees.ceiling is None:
            raise BudgetExceeded("config/pacer.yaml quarterly_ceiling is not set (Brandon)")
        now = self._now()
        q = quarter_of(now)
        cost = price(self.fees, kind, pages)
        total = self.spent(q) + cost
        if total > self.fees.ceiling:
            raise BudgetExceeded(f"{q}: {total} would exceed the ceiling {self.fees.ceiling}")
        entry = {"ts": now.isoformat(timespec="seconds"), "quarter": q, "kind": kind,
                 "court_id": court_id, "case": case, "document": document, "pages": pages,
                 "cost": str(cost)}  # fmt: skip
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return {**entry, "quarter_total": str(total),
                "alert": total >= self.fees.ceiling * self.fees.alert_fraction}  # fmt: skip

    def status(self) -> dict[str, Any]:
        q = quarter_of(self._now())
        spent = self.spent(q)
        ceiling = self.fees.ceiling
        return {"quarter": q, "spent": str(spent),
                "ceiling": None if ceiling is None else str(ceiling),
                "remaining": None if ceiling is None else str(max(ceiling - spent, Decimal(0))),
                "waived_if_quarter_ends_now": spent <= self.fees.quarterly_waiver,
                "requests": sum(1 for e in self.entries() if e["quarter"] == q)}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.pacer")
    ap.add_argument("cmd", choices=["status"])
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    args = ap.parse_args(argv)
    json.dump(Budget(args.ledger).status(), sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
