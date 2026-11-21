"""Run an adapter for real: fetch, keep the raw bytes, normalize, bulk-load.

    uv run python -m equity.ingest ar.statewide.parcels --partition county_fips=013
    uv run python -m equity.ingest ar.statewide.parcels --all     # whole state

(--db defaults to data/equity.duckdb, --raw to data/raw.)

Raw responses are written to data/raw/<source_id>/<fetch_id>.gz before normalization, so any
fact can be re-derived from the exact bytes it came from. data/ is git-ignored.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import duckdb

from equity.adapters.base import Adapter, Fetched, FetchRequest
from equity.adapters.rows import fetch_id, fetch_log_row
from equity.schema.bulk import load_bulk
from equity.schema.clock import Clock, system_clock
from equity.schema.load import LoadStats, load_rows
from equity.schema.migrate import connect, migrate

# Provenance first so every fact's references exist when it lands.
LOAD_ORDER = ("source", "fetch_log", "source_record", "address")


def store_raw(fetched: Fetched, raw_dir: Path) -> Path:
    folder = raw_dir / fetched.source_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{fetch_id(fetched)}.gz"
    with gzip.open(path, "wb") as fh:
        fh.write(fetched.content)
    meta = {"request": fetched.request, "retrieved_at": fetched.retrieved_at.isoformat(),
            "http_status": fetched.http_status, "content_type": fetched.content_type}  # fmt: skip
    (folder / f"{fetch_id(fetched)}.json").write_text(json.dumps(meta, sort_keys=True))
    return path


def load_fetched(
    con: duckdb.DuckDBPyConnection, adapter: Adapter, fetched: Fetched, raw_path: Path, clock: Clock
) -> LoadStats:
    stats = LoadStats()
    load_rows(con, "source", [dict(adapter.source_row())], clock, stats)
    log = fetch_log_row(fetched, type(adapter).__name__, adapter.adapter_version, str(raw_path))
    load_rows(con, "fetch_log", [dict(log.row)], clock, stats)
    by_table: dict[str, list[dict[str, Any]]] = {}
    for item in adapter.normalize(fetched):
        by_table.setdefault(item.table, []).append(dict(item.row))
    ordered = [t for t in LOAD_ORDER if t in by_table] + sorted(
        t for t in by_table if t not in LOAD_ORDER
    )
    for table in ordered:
        load_bulk(con, table, by_table[table], clock, stats)
    return stats


def partitions(adapter: Adapter) -> Iterator[dict[str, str]]:
    plan: Callable[[], Iterator[dict[str, str]]] | None = getattr(adapter, "partitions", None)
    if plan is None:
        yield {}
        return
    yield from plan()


def run(
    adapter: Adapter,
    db_path: str,
    raw_dir: Path,
    requests: list[dict[str, str]],
    clock: Clock = system_clock,
    log: Callable[[str], None] = print,
) -> LoadStats:
    con = connect(db_path)
    migrate(con, clock)
    total = LoadStats()
    for params in requests:
        fetched = adapter.fetch(FetchRequest(params))
        raw = store_raw(fetched, raw_dir)
        stats = load_fetched(con, adapter, fetched, raw, clock)
        total.inserted += stats.inserted
        total.unchanged += stats.unchanged
        total.superseded += stats.superseded
        for t, n in stats.by_table.items():
            total.by_table[t] = total.by_table.get(t, 0) + n
        log(f"{adapter.source_id} {params}: +{stats.inserted} new, {stats.unchanged} unchanged, "
            f"{stats.superseded} superseded")  # fmt: skip
    con.close()
    return total


def main(argv: list[str]) -> int:
    from equity.adapters.registry import by_source_id

    ap = argparse.ArgumentParser(prog="equity.ingest")
    ap.add_argument("source_id")
    ap.add_argument("--db", default="data/equity.duckdb")
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--partition", action="append", default=[],
                    help="key=value request params (repeatable), e.g. county_fips=013")  # fmt: skip
    ap.add_argument("--all", action="store_true", help="every partition the adapter plans")
    args = ap.parse_args(argv)
    adapter = by_source_id(args.source_id)()
    if args.all:
        requests = list(partitions(adapter))
    else:
        requests = [dict(p.split("=", 1) for p in args.partition)]
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    stats = run(adapter, args.db, Path(args.raw), requests)
    print(json.dumps({"inserted": stats.inserted, "unchanged": stats.unchanged,
                      "superseded": stats.superseded, "rows_by_table": stats.by_table},
                     indent=2, sort_keys=True))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
