"""Every state's match results in one place: counts by state, and one review queue.

Reads what `equity.matching.resolve` wrote under data/derived/<state>/ and writes, in the same
git-ignored folder (the queue names people):

  review_queue_all.parquet  every state's review_queue rows with a `state` column, ordered
                            state, category, owners_with_name_in_zip, debtor name
  <state>/review_queue.csv  the same rows for one state, for a spreadsheet
  summary_by_state.json     counts only (no names): debtors, auto matches, review queue by
                            category, open lien amount and parcel value behind auto matches

and prints the counts as a Markdown table. Nothing is matched or accepted here.

    uv run python -m equity.matching.rollup
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import duckdb

from equity.matching.resolve import DERIVED

CATEGORIES = ("spelling_only", "same_number", "po_box", "different")
ORDER = "state, category, owners_with_name_in_zip, debtor_name, debtor_party_id, owner_party_id"


def states(derived: Path) -> list[str]:
    """State folders (lowercase letters, digits and dashes only: they are put into SQL)."""
    names = (p.parent.name for p in derived.glob("*/summary.json"))
    return sorted(n for n in names if re.fullmatch(r"[a-z0-9-]+", n))


def state_row(state: str, summary: dict[str, Any]) -> dict[str, Any]:
    review = summary.get("review") or {}
    cats = review.get("debtors_by_category") or {}
    reg = summary.get("registries") or {}
    return {
        "state": state,
        "debtor_parties": summary.get("debtor_parties") or 0,
        "owner_parties": summary.get("owner_parties") or 0,
        "debtors_matched_auto": summary.get("debtors_matched_auto") or 0,
        "debtor_names_matched_auto": summary.get("debtor_names_matched_auto") or 0,
        "debtors_review_only": summary.get("debtors_matched_review_only") or 0,
        **{f"review_{c}": cats.get(c, 0) for c in CATEGORIES},
        "review_name_unique_in_zip": review.get("debtors_name_unique_in_zip") or 0,
        "debtors_with_company_parcels_auto": reg.get("debtors_with_company_parcels_auto") or 0,
        "open_amount_auto": summary.get("open_amount_auto"),
        "parcel_value_auto": summary.get("parcel_value_auto"),
    }


def _money(v: Any) -> str:
    return "" if v is None else f"${float(v):,.0f}"


def markdown(rows: list[dict[str, Any]]) -> str:
    head = ("| State | Debtors | Auto matched | Review | Spelling | Same no. | PO box | Other "
            "| Open liens (auto) | Parcel value (auto) |")  # fmt: skip
    lines = [head, "|" + "---|" * 10]
    for r in rows:
        lines.append(
            f"| {r['state']} | {r['debtor_parties']:,} | {r['debtors_matched_auto']:,} "
            f"| {r['debtors_review_only']:,} | {r['review_spelling_only']:,} "
            f"| {r['review_same_number']:,} | {r['review_po_box']:,} | {r['review_different']:,} "
            f"| {_money(r['open_amount_auto'])} | {_money(r['parcel_value_auto'])} |"
        )
    return "\n".join(lines)


def rollup(derived: Path) -> list[dict[str, Any]]:
    found = states(derived)
    rows = [state_row(s, json.loads((derived / s / "summary.json").read_text())) for s in found]
    (derived / "summary_by_state.json").write_text(json.dumps(rows, indent=2, default=str))
    queues = [(s, derived / s / "review_queue.parquet") for s in found]
    queues = [(s, p) for s, p in queues if p.exists()]
    if not queues:
        return rows
    con = duckdb.connect()
    parts = " UNION ALL BY NAME ".join(
        f"SELECT '{s}' AS state, * FROM read_parquet('{p.as_posix()}')"  # noqa: S608 (state dir names and paths only)
        for s, p in queues
    )
    con.execute(f"CREATE TABLE q AS {parts}")
    everything = (derived / "review_queue_all.parquet").as_posix()
    con.execute(f"COPY (SELECT * FROM q ORDER BY {ORDER}) TO '{everything}' (FORMAT parquet)")  # noqa: S608
    for s, _ in queues:
        out = (derived / s / "review_queue.csv").as_posix()
        con.execute(f"COPY (SELECT * EXCLUDE (state) FROM q WHERE state = '{s}' ORDER BY {ORDER}) "  # noqa: S608
                    f"TO '{out}' (HEADER)")  # fmt: skip
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.matching.rollup")
    ap.add_argument("--derived", type=Path, default=DERIVED)
    args = ap.parse_args(argv)
    sys.stdout.write(markdown(rollup(args.derived)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
