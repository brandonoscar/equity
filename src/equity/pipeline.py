"""End-to-end load: migrate, ingest normalized JSONL, export deterministic snapshots.

Normalized JSONL is the interchange format between adapters and the database: one object per
line, `{"table": "<name>", "row": {...}}`. Adapters' normalize() produce exactly this.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb

from equity.schema.catalog import all_tables, primary_key
from equity.schema.clock import Clock
from equity.schema.load import LoadError, LoadStats, load_rows
from equity.schema.migrate import connect, migrate


def read_jsonl(path: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict) or set(obj) != {"table", "row"}:
                raise LoadError(f"{path}:{lineno}: expected {{'table', 'row'}}")
            yield str(obj["table"]), dict(obj["row"])


def ingest(con: duckdb.DuckDBPyConnection, inputs: list[Path], clock: Clock) -> LoadStats:
    """Load files in the given order; within a file, line order."""
    stats = LoadStats()
    for path in inputs:
        for table, row in read_jsonl(path):
            load_rows(con, table, [row], clock, stats)
    return stats


def run(db_path: str, inputs: list[Path], clock: Clock) -> duckdb.DuckDBPyConnection:
    con = connect(db_path)
    migrate(con, clock)
    ingest(con, inputs, clock)
    return con


def export_snapshot(con: duckdb.DuckDBPyConnection, out_dir: Path) -> list[Path]:
    """Write every table as CSV ordered by primary key. Byte-stable for identical inputs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for table in all_tables():
        target = out_dir / f"{table}.csv"
        pk = primary_key(table)
        # COPY needs a literal path; table and key names come from the fixed catalog.
        con.execute(
            f"COPY (SELECT * FROM {table} ORDER BY {pk}) "  # noqa: S608
            f"TO '{target.as_posix()}' (HEADER, DELIMITER ',')"
        )
        written.append(target)
    return written


def run_manifest(db_path: str, manifest_path: Path) -> duckdb.DuckDBPyConnection:
    """Run batches listed in a manifest, each ingested at its stated instant.

    Manifest: {"batches": [{"ingested_at": ISO-8601 with tz, "files": [...]}, ...]}.
    Using stated instants instead of the wall clock makes reruns byte-identical.
    """
    from datetime import datetime

    from equity.schema.clock import fixed_clock

    spec = json.loads(manifest_path.read_text(encoding="utf-8"))
    batches = spec["batches"]
    if not batches:
        raise LoadError(f"{manifest_path}: no batches")
    con = connect(db_path)
    first = datetime.fromisoformat(batches[0]["ingested_at"])
    migrate(con, fixed_clock(first))
    for batch in batches:
        clock = fixed_clock(datetime.fromisoformat(batch["ingested_at"]))
        ingest(con, [manifest_path.parent / f for f in batch["files"]], clock)
    return con
