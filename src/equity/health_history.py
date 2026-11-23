"""Day-by-day source health: row counts and field names, with alerts on what changed.

    uv run python -m equity.adapters.health > health.json
    uv run python -m equity.health_history --health health.json      # exit 1 on any alert

Each run writes data/health/<day>.json: per source, whether it answered, its live row count
(where the API counts) and its field names, plus the alerts raised against the previous
day on file. Alerts:
  went_down       answered yesterday, not today
  row_drop        live row count fell by more than the threshold (default 10%)
  fields_changed  fields were added or removed (a renamed column breaks a config silently)
  refresh_drop    a lake refresh in the last day stored more than the threshold fewer rows
                  in a table than the build it replaced (from _refreshed.json, equity.refresh)
Small tables are not compared on counts (MIN_ROWS): a drop from 9 rows to 8 is noise.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

HISTORY = Path("data") / "health"
LAKE = Path("data") / "lake"
DROP = 0.10
MIN_ROWS = 50
RECENT = timedelta(hours=26)  # a refresh newer than this is checked by tonight's run


def snapshot(results: list[dict[str, Any]], day: date) -> dict[str, Any]:
    return {
        "day": day.isoformat(),
        "sources": {
            r["source_id"]: {"ok": bool(r.get("ok")), "detail": r.get("detail", ""),
                             "rows": r.get("rows"), "fields": sorted(r.get("fields") or [])}
            for r in results
        },
    }  # fmt: skip


def _dropped(before: int | None, after: int | None, drop: float) -> bool:
    return bool(before and before >= MIN_ROWS and after is not None and after < before * (1 - drop))


def compare(prev: dict[str, Any], cur: dict[str, Any], drop: float = DROP) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for sid, c in sorted(cur["sources"].items()):
        p = prev["sources"].get(sid)
        if p is None:
            continue
        if p["ok"] and not c["ok"]:
            alerts.append({"source_id": sid, "alert": "went_down", "detail": c["detail"]})
        if _dropped(p.get("rows"), c.get("rows"), drop):
            alerts.append({"source_id": sid, "alert": "row_drop",
                           "detail": f"{p['rows']:,} -> {c['rows']:,} rows"})  # fmt: skip
        pf, cf = set(p.get("fields") or []), set(c.get("fields") or [])
        if pf and cf and pf != cf:
            detail = f"added {sorted(cf - pf)}, removed {sorted(pf - cf)}"
            alerts.append({"source_id": sid, "alert": "fields_changed", "detail": detail})
    return alerts


def refresh_alerts(lake: Path, now: datetime, drop: float = DROP) -> list[dict[str, Any]]:
    """Tables a recent refresh stored with fewer rows than the build it replaced."""
    alerts: list[dict[str, Any]] = []
    for f in sorted(lake.glob("*/_refreshed.json")):
        rec = json.loads(f.read_text())
        if now - datetime.fromisoformat(rec["at"]) > RECENT or "previous" not in rec:
            continue
        before = rec["previous"].get("counts") or {}
        for table, n in sorted(before.items()):
            after = rec["counts"].get(table, 0)
            if _dropped(n, after, drop):
                alerts.append({"source_id": f.parent.name, "alert": "refresh_drop",
                               "detail": f"{table}: {n:,} -> {after:,} rows"})  # fmt: skip
    return alerts


def previous_day(history: Path, day: date) -> dict[str, Any] | None:
    days = sorted(p for p in history.glob("*.json") if p.stem < day.isoformat())
    return json.loads(days[-1].read_text()) if days else None


def check(
    results: list[dict[str, Any]], history: Path, lake: Path, now: datetime, drop: float = DROP
) -> dict[str, Any]:
    day = now.astimezone(UTC).date()
    cur = snapshot(results, day)
    prev = previous_day(history, day)
    cur["compared_with"] = prev["day"] if prev else None
    cur["alerts"] = (compare(prev, cur, drop) if prev else []) + refresh_alerts(lake, now, drop)
    history.mkdir(parents=True, exist_ok=True)
    (history / f"{day.isoformat()}.json").write_text(json.dumps(cur, indent=1, sort_keys=True))
    return cur


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.health_history")
    ap.add_argument("--health", type=Path, required=True, help="equity.adapters.health output")
    ap.add_argument("--history", type=Path, default=HISTORY)
    ap.add_argument("--lake", type=Path, default=LAKE)
    ap.add_argument("--drop", type=float, default=DROP, help="alert on a larger fall (0.10)")
    ap.add_argument("--now", type=datetime.fromisoformat, default=None)
    args = ap.parse_args(argv)
    now = args.now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    results = json.loads(args.health.read_text())["results"]
    out = check(results, args.history, args.lake, now, args.drop)
    json.dump({"day": out["day"], "compared_with": out["compared_with"],
               "alerts": out["alerts"]}, sys.stdout, indent=2)  # fmt: skip
    sys.stdout.write("\n")
    return 1 if out["alerts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
