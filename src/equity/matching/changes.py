"""New since last run: what changed in a state's lead list and sale watch.

Each run saves today's commercial_leads.parquet and sale_watch.parquet (whichever exist) under
data/derived/<state>/history/<YYYY-MM-DD>/ (a same-day rerun replaces that day), then compares
them with the latest earlier day:

  new_owner          an owner on today's lead list who was not on the last one
  open_amount_up     an owner whose open amount went up (before -> after)
  new_parcel         an owner listed both times with a parcel not listed before
  new_sale_event     a sale-list or foreclosure event on a matched parcel not seen before

The first run has nothing to compare and reports `first_run`. Nothing is matched here.

Outputs, in the state's derived folder (git-ignored: they name people):
  changes.csv / changes.parquet    one row per change, newest kind first
  changes_summary.json             counts only

    uv run python -m equity.matching.changes --state NY
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from equity.matching.resolve import DERIVED

TRACKED = ("commercial_leads.parquet", "sale_watch.parquet")
KINDS = ("new_owner", "open_amount_up", "new_parcel", "new_sale_event")


def snapshot(out: Path, on: date) -> Path:
    day = out / "history" / on.isoformat()
    day.mkdir(parents=True, exist_ok=True)
    for name in TRACKED:
        if (out / name).exists():
            shutil.copyfile(out / name, day / name)
    return day


def _days(out: Path) -> list[Path]:
    hist = out / "history"
    pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
    return sorted(d for d in hist.iterdir() if d.is_dir() and pattern.fullmatch(d.name)) \
        if hist.exists() else []  # fmt: skip


def _empty_leads(con: duckdb.DuckDBPyConnection, name: str) -> None:
    con.execute(f"CREATE TABLE {name} (owner_name VARCHAR, parcels VARCHAR[], "
                "open_amount DOUBLE)")  # fmt: skip


def _empty_sales(con: duckdb.DuckDBPyConnection, name: str) -> None:
    con.execute(f"CREATE TABLE {name} (parcel_uid VARCHAR, source_id VARCHAR, "
                "listing_key VARCHAR, event_date DATE, status VARCHAR, "
                "example_debtor_name VARCHAR)")  # fmt: skip


def _load(con: duckdb.DuckDBPyConnection, day: Path, tag: str) -> None:
    leads, sales = day / "commercial_leads.parquet", day / "sale_watch.parquet"
    if leads.exists():
        con.execute(f"CREATE TABLE leads_{tag} AS SELECT owner_name, parcels, open_amount "  # noqa: S608
                    f"FROM '{leads.as_posix()}'")  # fmt: skip
    else:
        _empty_leads(con, f"leads_{tag}")
    if sales.exists():
        cols = "parcel_uid, source_id, listing_key, event_date, status, example_debtor_name"
        con.execute(f"CREATE TABLE sales_{tag} AS SELECT {cols} FROM '{sales.as_posix()}'")  # noqa: S608
    else:
        _empty_sales(con, f"sales_{tag}")


DIFF_SQL = """
CREATE TABLE changes AS
SELECT 'new_owner' AS change, c.owner_name AS subject, NULL::VARCHAR AS parcel_uid,
       NULL::DOUBLE AS before, c.open_amount AS after, NULL::VARCHAR AS detail
FROM leads_cur c WHERE c.owner_name NOT IN (SELECT owner_name FROM leads_prev)
UNION ALL
SELECT 'open_amount_up', c.owner_name, NULL, p.open_amount, c.open_amount, NULL
FROM leads_cur c JOIN leads_prev p USING (owner_name)
WHERE coalesce(c.open_amount, 0) > coalesce(p.open_amount, 0)
UNION ALL
SELECT 'new_parcel', c.owner_name, u.parcel_uid, NULL, c.open_amount, NULL
FROM leads_cur c JOIN leads_prev p USING (owner_name), unnest(c.parcels) AS u(parcel_uid)
WHERE NOT list_contains(p.parcels, u.parcel_uid)
UNION ALL
SELECT 'new_sale_event', c.example_debtor_name, c.parcel_uid, NULL, NULL,
       c.source_id || ': ' || coalesce(c.status, '') || ' ' || coalesce(CAST(c.event_date AS
       VARCHAR), '')
FROM sales_cur c WHERE NOT EXISTS (
    SELECT 1 FROM sales_prev p WHERE p.source_id = c.source_id
    AND p.listing_key = c.listing_key AND p.parcel_uid = c.parcel_uid);
"""


def diff(derived: Path, state: str, on: date | None = None) -> dict[str, Any]:
    out = derived / state.lower()
    if not any((out / n).exists() for n in TRACKED):
        raise FileNotFoundError(f"{state}: no commercial_leads or sale_watch to track")
    today = snapshot(out, on or datetime.now(UTC).date())
    earlier = [d for d in _days(out) if d.name < today.name]
    summary: dict[str, Any] = {"state": state.upper(), "today": today.name,
                               "compared_with": earlier[-1].name if earlier else None}  # fmt: skip
    con = duckdb.connect()
    _load(con, today, "cur")
    if earlier:
        _load(con, earlier[-1], "prev")
    else:
        _empty_leads(con, "leads_prev")
        _empty_sales(con, "sales_prev")
    con.execute(DIFF_SQL)
    if not earlier:  # nothing to compare: everything would look new
        con.execute("DELETE FROM changes")
        summary["first_run"] = True
    order = "CASE change " + " ".join(f"WHEN '{k}' THEN {i}" for i, k in enumerate(KINDS)) + " END"
    target = (out / "changes.parquet").as_posix()
    con.execute(f"COPY (SELECT * FROM changes ORDER BY {order}, after DESC NULLS LAST, subject, "  # noqa: S608
                f"parcel_uid) TO '{target}' (FORMAT parquet)")  # fmt: skip
    con.execute(f"COPY (SELECT * FROM '{(out / 'changes.parquet').as_posix()}') TO "  # noqa: S608
                f"'{(out / 'changes.csv').as_posix()}' (HEADER)")  # fmt: skip
    counts = dict(con.execute("SELECT change, count(*) FROM changes GROUP BY 1").fetchall())
    summary["changes"] = {k: counts.get(k, 0) for k in KINDS}
    (out / "changes_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.matching.changes")
    ap.add_argument("--state", required=True)
    ap.add_argument("--derived", type=Path, default=DERIVED)
    args = ap.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.state):
        ap.error("bad state")
    json.dump(diff(args.derived, args.state), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
