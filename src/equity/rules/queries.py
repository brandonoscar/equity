"""Saved criteria queries over the match output, with what is new since the last run.

    uv run python -m equity.rules.queries                   # every config/private/queries/*.yaml
    uv run python -m equity.rules.queries --file q.yaml     # one query file

A query (see config/queries.example.yaml) names match runs, filters over the scorer's
factors (equity.rules.score: open amount, parcel value, debt kinds, bankruptcy and transfer
flags), an order and a limit. Each run writes data/derived/queries/<name>/<date>.parquet and
new_since_last.parquet: the people not in the previous dated result. Person ids are stable
party ids, so "new" means a person newly meeting the criteria, not a re-run.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import yaml

from equity.config import CONFIG_DIR
from equity.rules.score import DERIVED, score_state

QUERY_DIR = CONFIG_DIR / "private" / "queries"
ORDERABLE = ("open_amount", "parcel_value", "parcels", "transfers_after_debt", "score")
KNOWN = {"min_open_amount", "min_parcel_value", "debt_kinds_any", "exclude_bankruptcy",
         "require_parcels", "max_transfers_after_debt"}  # fmt: skip


def _num(v: Any, key: str) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise ValueError(f"{key} must be a number")
    return float(v)


def where_sql(where: dict[str, Any]) -> str:
    unknown = set(where) - KNOWN
    if unknown:
        raise ValueError(f"unknown filters {sorted(unknown)}")
    clauses: list[str] = []
    if where.get("min_open_amount") is not None:
        clauses.append(f"open_amount >= {_num(where['min_open_amount'], 'min_open_amount')!r}")
    if where.get("min_parcel_value") is not None:
        clauses.append(f"parcel_value >= {_num(where['min_parcel_value'], 'min_parcel_value')!r}")
    kinds = where.get("debt_kinds_any")
    if kinds:
        if not all(isinstance(k, str) and k.replace("_", "").isalnum() for k in kinds):
            raise ValueError("debt_kinds_any must be debt kind names")
        clauses.append("list_has_any(debt_kinds, [" + ", ".join(f"'{k}'" for k in kinds) + "])")
    if where.get("exclude_bankruptcy"):
        clauses.append("bankruptcy_open = 0 AND bankruptcy_discharged = 0")
    if where.get("require_parcels"):
        clauses.append("parcels > 0")
    if where.get("max_transfers_after_debt") is not None:
        n = _num(where["max_transfers_after_debt"], "max_transfers_after_debt")
        clauses.append(f"transfers_after_debt <= {n!r}")
    return " AND ".join(clauses) or "true"


def run_query(
    spec: dict[str, Any], derived: Path = DERIVED, today: str | None = None
) -> dict[str, Any]:
    name = str(spec["name"])
    if not name.replace("_", "").replace("-", "").isalnum():
        raise ValueError(f"query name {name!r}: letters, digits, - and _ only")
    order = str(spec.get("order_by") or "open_amount")
    if order not in ORDERABLE:
        raise ValueError(f"order_by must be one of {ORDERABLE}")
    limit = int(spec.get("limit") or 1000)
    where = where_sql(dict(spec.get("where") or {}))
    con = duckdb.connect()
    parts = []
    for run in spec["states"]:
        folder = derived / str(run).lower()
        scores = folder / "scores.parquet"
        if not scores.exists():
            score_state(str(run), derived)
        people = folder / "people.parquet"
        parts.append(
            f"SELECT '{str(run).upper()}' AS run, s.*, p.debt_kinds "  # noqa: S608
            f"FROM read_parquet('{scores.as_posix()}') s "
            f"JOIN read_parquet('{people.as_posix()}') p USING (person_id)"
        )
    con.execute("CREATE TABLE allp AS " + " UNION ALL BY NAME ".join(parts))
    con.execute(f"CREATE TABLE result AS SELECT * FROM allp WHERE {where} "  # noqa: S608
                f"ORDER BY {order} DESC NULLS LAST, person_id LIMIT {limit}")  # fmt: skip
    folder = derived / "queries" / name
    folder.mkdir(parents=True, exist_ok=True)
    day = today or datetime.now(UTC).date().isoformat()
    earlier = sorted(p for p in folder.glob("????-??-??.parquet") if p.stem < day)
    con.execute(f"COPY result TO '{(folder / day).as_posix()}.parquet' (FORMAT PARQUET)")
    if earlier:
        prev = earlier[-1].as_posix()
        seen = f"SELECT 1 FROM read_parquet('{prev}') p"  # noqa: S608
        new_sql = (f"SELECT * FROM result r WHERE NOT EXISTS ({seen} "  # noqa: S608
                   "WHERE p.run = r.run AND p.person_id = r.person_id)")  # fmt: skip
    else:
        new_sql = "SELECT * FROM result"
    con.execute(f"COPY ({new_sql}) TO '{(folder / 'new_since_last').as_posix()}.parquet' "
                "(FORMAT PARQUET)")  # fmt: skip
    total = con.execute("SELECT count(*) FROM result").fetchone()
    new = con.execute(f"SELECT count(*) FROM ({new_sql})").fetchone()  # noqa: S608
    summary = {"query": name, "day": day, "matched": total[0] if total else 0,
               "new_since_last": new[0] if new else 0,
               "compared_with": earlier[-1].stem if earlier else None}  # fmt: skip
    (folder / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.rules.queries")
    ap.add_argument("--file", type=Path, help="one query file (default: every private query)")
    ap.add_argument("--derived", type=Path, default=DERIVED)
    args = ap.parse_args(argv)
    files = [args.file] if args.file else sorted(QUERY_DIR.glob("*.yaml"))
    if not files:
        print(f"no queries in {QUERY_DIR} (see config/queries.example.yaml)", file=sys.stderr)
        return 0
    for f in files:
        print(json.dumps(run_query(yaml.safe_load(f.read_text()), args.derived)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
