"""Recurring refreshes of loaded sources, with a dated snapshot of each refresh.

    uv run python -m equity.refresh due --limit 8        # sources whose refresh is due
    uv run python -m equity.refresh start <ids...>       # reset them so `lake run` rebuilds
    uv run python -m equity.lake run --only <ids...>
    uv run python -m equity.refresh finish <ids...>      # record the refresh and snapshot
    uv run python -m equity.refresh listings             # sale-listing history from snapshots

Cadence and mode per source come from config/refresh.yaml. `start` prepares a source:
  rebuild / listing  the partition plan is made again from the adapter (keeping any extra
                     parameters every old partition shared, e.g. a doc-code filter) and every
                     finished part is cleared;
  append             a new poll partition is added to the plan; finished parts stay, and the
                     build drops rows already stored (equity.lake.drop_known).
`finish` writes, for a source whose build completed:
  _refreshed.json              when and how it was last refreshed, with the counts before
                               ("previous"); synced with the state, read by health_history
  _snapshots/<date>.json       row counts per table that day: the source's history
  _snapshots/<date>/<t>.parquet  listing mode only: the listing table as it stood that day
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from equity.config import _load

LAKE = Path("data") / "lake"
DERIVED = Path("data") / "derived"
MODES = ("rebuild", "listing", "append")
REFRESHED = "_refreshed.json"
BEFORE = "_before_refresh.json"  # counts as they stood when the refresh started
SNAPSHOTS = "_snapshots"


@dataclass(frozen=True)
class Rule:
    match: tuple[str, ...]
    exclude: tuple[str, ...]
    every: timedelta
    mode: str
    listing_table: str | None = None

    def covers(self, source_id: str) -> bool:
        return any(fnmatch.fnmatchcase(source_id, p) for p in self.match) and not any(
            fnmatch.fnmatchcase(source_id, p) for p in self.exclude
        )


def rules(config_dir: Path | None = None) -> list[Rule]:
    out: list[Rule] = []
    for i, r in enumerate(_load("refresh.yaml", config_dir)["rules"]):
        mode = r.get("mode", "rebuild")
        if mode not in MODES:
            raise ValueError(f"refresh.yaml rule {i}: mode must be one of {MODES}")
        if mode == "listing" and not r.get("listing_table"):
            raise ValueError(f"refresh.yaml rule {i}: listing mode needs listing_table")
        hours = float(r["every_hours"])
        if hours <= 0:
            raise ValueError(f"refresh.yaml rule {i}: every_hours must be positive")
        out.append(Rule(tuple(r["match"]), tuple(r.get("exclude") or ()),
                        timedelta(hours=hours), mode, r.get("listing_table")))  # fmt: skip
    return out


def rule_for(source_id: str, rule_list: list[Rule]) -> Rule | None:
    return next((r for r in rule_list if r.covers(source_id)), None)


def registered() -> list[str]:
    from equity.adapters.registry import REGISTRY

    return sorted({c.source_id for c in REGISTRY})


def last_refresh(src: Path) -> datetime | None:
    f = src / REFRESHED
    if not f.exists():
        return None
    return datetime.fromisoformat(json.loads(f.read_text())["at"])


def due(
    lake: Path, now: datetime, rule_list: list[Rule], source_ids: list[str] | None = None
) -> list[str]:
    """Sources whose refresh is due, never-refreshed first, then oldest refresh first.
    A rebuild/listing source that has not finished its first load is left to `lake run`;
    a polled feed is due from the start (its first poll is its first load)."""
    found: list[tuple[datetime, str]] = []
    floor = datetime.min.replace(tzinfo=UTC)
    for sid in source_ids if source_ids is not None else registered():
        rule = rule_for(sid, rule_list)
        if rule is None:
            continue
        src = lake / sid
        built = (src / "_counts.json").exists()
        if rule.mode != "append" and not built:
            continue
        last = last_refresh(src)
        if last is None or now - last >= rule.every or (rule.mode == "append" and not built):
            found.append((last or floor, sid))
    return [sid for _, sid in sorted(found)]


def _clear_parts(src: Path) -> None:
    for marker in (src / "_parts").glob("*.json"):
        marker.unlink()
    for table_dir in src.iterdir():
        if table_dir.is_dir() and not table_dir.name.startswith("_"):
            shutil.rmtree(table_dir)
    for name in ("_counts.json", "_offloaded"):
        (src / name).unlink(missing_ok=True)


def shared_extra(old: list[dict[str, str]], fresh: list[dict[str, str]]) -> dict[str, str]:
    """Parameters every old partition carried that the adapter's own plan never sets: a
    subset filter written by `lake plan --set`, kept across a re-plan."""
    if not old:
        return {}
    own = {k for p in fresh for k in p}
    common = {k: v for k, v in old[0].items() if k not in own}
    return {k: v for k, v in common.items() if all(p.get(k) == v for p in old[1:])}


def start(source_id: str, lake: Path, now: datetime, rule: Rule) -> str:
    """Prepare one source for its refresh build. Returns what was done."""
    src = lake / source_id
    plan_path = src / "_plan.json"
    built = (src / "_counts.json").exists()
    if built and not (src / BEFORE).exists():  # what finish() compares the new counts with
        last = last_refresh(src)
        (src / BEFORE).write_text(json.dumps({
            "at": last.isoformat() if last else None,
            "counts": json.loads((src / "_counts.json").read_text())}, sort_keys=True))  # fmt: skip
    if rule.mode == "append":
        if not plan_path.exists():
            return "first poll"  # build writes the adapter's plan
        if not built:
            return "poll pending"
        if (src / "_offloaded").exists() or (
            any((src / "_parts").glob("*.json")) and not any(src.glob("*/*.parquet"))
        ):
            raise RuntimeError(
                f"{source_id}: stored parts are not local; pull them first "
                "(lake_sync pull-parts) so the new poll can drop rows already kept"
            )
        plan = json.loads(plan_path.read_text())
        plan.append({"poll": now.astimezone(UTC).isoformat(timespec="seconds")})
        plan_path.write_text(json.dumps(plan, indent=1))
        (src / "_counts.json").unlink()
        return f"poll {len(plan) - 1} added"
    if not built:
        return "not built yet"
    from equity.adapters.registry import by_source_id
    from equity.ingest import partitions

    old = json.loads(plan_path.read_text()) if plan_path.exists() else []
    fresh = list(partitions(by_source_id(source_id)()))
    extra = shared_extra(old, fresh)
    _clear_parts(src)
    plan_path.write_text(json.dumps([{**p, **extra} for p in fresh], indent=1))
    return f"re-planned {len(fresh)} partitions"


def finish(source_id: str, lake: Path, now: datetime, rule: Rule) -> dict[str, Any] | None:
    """Record a completed refresh build (None when the build has not finished)."""
    src = lake / source_id
    counts_path = src / "_counts.json"
    if not counts_path.exists():
        return None
    counts = json.loads(counts_path.read_text())
    day = now.astimezone(UTC).date().isoformat()
    record: dict[str, Any] = {
        "at": now.astimezone(UTC).isoformat(timespec="seconds"), "mode": rule.mode,
        "parts": len(list((src / "_parts").glob("*.json"))), "counts": counts}  # fmt: skip
    if (src / BEFORE).exists():
        record["previous"] = json.loads((src / BEFORE).read_text())
    elif (src / REFRESHED).exists():
        old = json.loads((src / REFRESHED).read_text())
        record["previous"] = {"at": old.get("at"), "counts": old.get("counts", {})}
    snaps = src / SNAPSHOTS
    snaps.mkdir(parents=True, exist_ok=True)
    (snaps / f"{day}.json").write_text(json.dumps(record, indent=1, sort_keys=True))
    if rule.mode == "listing" and rule.listing_table:
        tables = [rule.listing_table]
        if rule.listing_table == "instrument":
            tables.append("instrument_parcel")
        for table in tables:
            files = sorted((src / table).glob("*.parquet"))
            dest = snaps / day / f"{table}.parquet"
            dest.parent.mkdir(parents=True, exist_ok=True)
            paths = ", ".join(f"'{p.as_posix()}'" for p in files)
            # A listing with no parcel links still gets an (empty) instrument_parcel file.
            query = (f"SELECT * FROM read_parquet([{paths}], union_by_name = true)" if files  # noqa: S608
                     else "SELECT NULL::VARCHAR AS instrument_uid, NULL::VARCHAR AS parcel_uid "
                     "WHERE false")  # fmt: skip
            duckdb.connect().execute(
                f"COPY ({query}) TO '{dest.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
    (src / REFRESHED).write_text(json.dumps(record, indent=1, sort_keys=True))
    (src / BEFORE).unlink(missing_ok=True)
    return record


# One row per listing per snapshot day, whatever table the source lists in.
LISTING_SELECT = {
    "instrument": """
        SELECT i.source_id, i.instrument_uid AS listing_key, min(p.parcel_uid) AS parcel_uid,
               i.recorded_on AS listed_date, i.principal_amount AS amount,
               i.doc_type_raw AS status
        FROM read_parquet('{dir}/instrument.parquet') i
        LEFT JOIN read_parquet('{dir}/instrument_parcel.parquet') p USING (instrument_uid)
        WHERE i.superseded_at IS NULL GROUP BY ALL""",
    "tax_delinquency_snapshot": """
        SELECT source_id, parcel_uid || '|' || certificate_no AS listing_key, parcel_uid,
               observed_on AS listed_date, CAST(NULL AS DECIMAL(14,2)) AS amount,
               status_raw AS status
        FROM read_parquet('{dir}/tax_delinquency_snapshot.parquet')
        WHERE superseded_at IS NULL""",
}

HISTORY_SQL = """
WITH s AS (SELECT * FROM sale_listing_snapshot),
latest AS (SELECT source_id, max(snapshot_date) AS d FROM s GROUP BY 1)
SELECT s.source_id, s.listing_key, any_value(s.parcel_uid) AS parcel_uid,
       min(s.snapshot_date) AS first_seen, max(s.snapshot_date) AS last_seen,
       count(*) AS days_seen, max(s.snapshot_date) = any_value(l.d) AS on_latest,
       arg_max(s.amount, s.snapshot_date) AS latest_amount,
       arg_max(s.status, s.snapshot_date) AS latest_status,
       count(DISTINCT coalesce(CAST(s.amount AS VARCHAR), '') || '|'
             || coalesce(s.status, '')) - 1 AS changes
FROM s JOIN latest l USING (source_id)
GROUP BY s.source_id, s.listing_key
ORDER BY s.source_id, s.listing_key
"""


def listings(lake: Path, rule_list: list[Rule], out: Path) -> dict[str, Any]:
    """Union every listing snapshot into sale_listing_snapshot (one row per listing per day)
    and sale_listing_history (first/last seen, on the latest list, changes), and count, per
    source, what appeared and dropped between its last two snapshot days."""
    con = duckdb.connect()
    parts: list[str] = []
    for src in sorted(p for p in lake.iterdir() if (p / SNAPSHOTS).is_dir()):
        rule = rule_for(src.name, rule_list)
        if rule is None or rule.mode != "listing" or rule.listing_table not in LISTING_SELECT:
            continue
        for day_dir in sorted(d for d in (src / SNAPSHOTS).iterdir() if d.is_dir()):
            if not (day_dir / f"{rule.listing_table}.parquet").exists():
                continue
            sql = LISTING_SELECT[rule.listing_table].format(dir=day_dir.as_posix())
            day = day_dir.name  # a YYYY-MM-DD folder written by finish()
            parts.append(f"SELECT DATE '{day}' AS snapshot_date, * FROM ({sql})")  # noqa: S608
    if not parts:
        return {"snapshots": 0}
    con.execute("CREATE TABLE sale_listing_snapshot AS " + " UNION ALL BY NAME ".join(parts))
    con.execute(f"CREATE TABLE sale_listing_history AS {HISTORY_SQL}")
    out.mkdir(parents=True, exist_ok=True)
    for t in ("sale_listing_snapshot", "sale_listing_history"):
        con.execute(f"COPY {t} TO '{(out / t).as_posix()}.parquet' (FORMAT PARQUET)")
    by_source: dict[str, Any] = {}
    rows = con.execute("""
        WITH days AS (SELECT source_id, snapshot_date,
                             dense_rank() OVER (PARTITION BY source_id
                                                ORDER BY snapshot_date DESC) AS r
                      FROM (SELECT DISTINCT source_id, snapshot_date
                            FROM sale_listing_snapshot)),
        cur AS (SELECT s.* FROM sale_listing_snapshot s JOIN days d USING (source_id,
                snapshot_date) WHERE d.r = 1),
        prev AS (SELECT s.* FROM sale_listing_snapshot s JOIN days d USING (source_id,
                 snapshot_date) WHERE d.r = 2)
        SELECT source_id, (SELECT max(snapshot_date) FROM cur c2
                           WHERE c2.source_id = c.source_id) AS latest,
               count(*) AS listed,
               count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM prev p WHERE
                   p.source_id = c.source_id AND p.listing_key = c.listing_key)
                   AND EXISTS (SELECT 1 FROM prev p2 WHERE p2.source_id = c.source_id))
                   AS appeared,
               (SELECT count(*) FROM prev p WHERE p.source_id = c.source_id AND NOT EXISTS
                   (SELECT 1 FROM cur c3 WHERE c3.source_id = p.source_id
                    AND c3.listing_key = p.listing_key)) AS dropped
        FROM cur c GROUP BY source_id ORDER BY source_id""").fetchall()  # fmt: skip
    for sid, latest, listed, appeared, dropped in rows:
        by_source[sid] = {"latest": str(latest), "listed": listed, "appeared": appeared,
                          "dropped": dropped}  # fmt: skip
    row = con.execute("SELECT count(*) FROM sale_listing_snapshot").fetchone()
    summary = {"snapshots": row[0] if row else 0, "sources": by_source}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.refresh")
    ap.add_argument("--lake", type=Path, default=LAKE)
    ap.add_argument("--now", type=datetime.fromisoformat, default=None,
                    help="ISO time to act as now (default: the current UTC time)")  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("due")
    d.add_argument("--limit", type=int, default=0, help="at most this many (0: all)")
    d.add_argument("--mode", choices=MODES, help="only sources refreshed in this mode")
    for name in ("start", "finish"):
        sub.add_parser(name).add_argument("source_ids", nargs="+")
    li = sub.add_parser("listings")
    li.add_argument("--out", type=Path, default=DERIVED / "sale_listings")
    args = ap.parse_args(argv)
    now = args.now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    rule_list = rules()
    if args.cmd == "due":
        ids = due(args.lake, now, rule_list)
        if args.mode:
            ids = [s for s in ids if (r := rule_for(s, rule_list)) and r.mode == args.mode]
        print(" ".join(ids[: args.limit] if args.limit else ids))
        return 0
    if args.cmd == "listings":
        print(json.dumps(listings(args.lake, rule_list, args.out), indent=1, sort_keys=True))
        return 0
    for sid in args.source_ids:
        rule = rule_for(sid, rule_list)
        if rule is None:
            print(f"{sid}: no refresh rule", file=sys.stderr)
            continue
        if args.cmd == "start":
            print(f"{sid}: {start(sid, args.lake, now, rule)}")
        else:
            rec = finish(sid, args.lake, now, rule)
            print(f"{sid}: " + ("build not finished" if rec is None else "refreshed"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
