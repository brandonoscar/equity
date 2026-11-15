"""Set-based loader for large batches (statewide parcel files, nightly feeds).

Same rows as the row loader, built by set operations instead of one query per row:
  1. convert + hash every row in Python (shared code with the row loader),
  2. stage them in a temp table via DuckDB's NDJSON reader,
  3. one UPDATE supersedes current rows whose key matches and whose content changed,
  4. one INSERT adds rows whose key has no current row.

Semantics within one batch: if the same domain key appears more than once, the LAST row
wins and earlier ones are dropped (the row loader would instead insert and immediately
supersede them). For batches with unique keys the two loaders are equivalent, and
tests/test_bulk_loader.py proves it with Hypothesis.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from equity.schema.catalog import FACT_TABLES, OTHER_TABLES, PROVENANCE_TABLES
from equity.schema.clock import Clock
from equity.schema.load import LoadError, LoadStats, column_types, convert_row, prepare_fact


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return value.hex()
    return value


def _cast(col: str, dtype: str) -> str:
    if dtype == "BLOB":
        return f"from_hex({col})"
    return f"CAST({col} AS {dtype})"


def _stage(
    con: duckdb.DuckDBPyConnection,
    rows: list[dict[str, Any]],
    cols: list[str],
    types: Mapping[str, str],
    workdir: Path,
) -> None:
    path = workdir / "stage.ndjson"
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({c: _jsonable(r.get(c)) for c in cols}) + "\n")
    spec = ", ".join(f"'{c}': 'VARCHAR'" for c in cols)
    select = ", ".join(f"{_cast(c, types[c])} AS {c}" for c in cols)
    con.execute("DROP TABLE IF EXISTS _stage")
    con.execute(
        f"CREATE TEMP TABLE _stage AS SELECT {select} FROM "  # noqa: S608
        f"read_json('{path.as_posix()}', format='newline_delimited', columns={{{spec}}})"
    )


def load_bulk(
    con: duckdb.DuckDBPyConnection,
    table: str,
    rows: Iterable[Mapping[str, Any]],
    clock: Clock,
    stats: LoadStats | None = None,
) -> LoadStats:
    stats = stats or LoadStats()
    types = column_types(con, table)
    with tempfile.TemporaryDirectory(prefix="equity-bulk-") as tmp:
        if table in FACT_TABLES:
            _bulk_fact(con, table, rows, types, clock, stats, Path(tmp))
        elif table in PROVENANCE_TABLES or table in OTHER_TABLES:
            _bulk_plain(con, table, rows, types, stats, Path(tmp))
        else:
            raise LoadError(f"{table}: not a loadable table")
    return stats


def _bulk_fact(
    con: duckdb.DuckDBPyConnection,
    table: str,
    rows: Iterable[Mapping[str, Any]],
    types: Mapping[str, str],
    clock: Clock,
    stats: LoadStats,
    workdir: Path,
) -> None:
    latest: dict[str, dict[str, Any]] = {}
    key_cols: tuple[str, ...] = ()
    seen = 0
    for raw in rows:
        prep = prepare_fact(table, convert_row(table, raw, types), types)
        key_cols = prep.key_cols
        full = dict(prep.row)
        full["row_id"] = prep.row_id
        full["fact_hash"] = prep.fact_hash
        latest.pop(prep.key_text, None)  # re-insert so dict order = last occurrence order
        latest[prep.key_text] = full
        seen += 1
    stats.by_table[table] = stats.by_table.get(table, 0) + seen
    if not latest:
        return
    now = clock()
    staged = list(latest.values())
    cols = [c for c in types if c not in ("ingested_at", "superseded_at")]
    _stage(con, staged, cols, types, workdir)
    on = " AND ".join(f"t.{c} IS NOT DISTINCT FROM s.{c}" for c in key_cols)
    con.execute("BEGIN TRANSACTION")
    try:
        unchanged = con.execute(
            f"SELECT count(*) FROM _stage s JOIN {table} t ON {on} "  # noqa: S608
            "WHERE t.superseded_at IS NULL AND t.fact_hash = s.fact_hash"
        ).fetchone()
        changed = con.execute(
            f"SELECT count(*) FROM {table} t WHERE t.superseded_at IS NULL AND EXISTS "  # noqa: S608
            f"(SELECT 1 FROM _stage s WHERE {on} AND t.fact_hash IS DISTINCT FROM s.fact_hash)"
        ).fetchone()
        con.execute(
            f"UPDATE {table} t SET superseded_at = ? WHERE t.superseded_at IS NULL AND EXISTS "  # noqa: S608
            f"(SELECT 1 FROM _stage s WHERE {on} AND t.fact_hash IS DISTINCT FROM s.fact_hash)",
            [now],
        )
        col_list = ", ".join(cols)
        inserted = con.execute(
            f"INSERT INTO {table} ({col_list}, ingested_at, superseded_at) "  # noqa: S608
            f"SELECT {', '.join('s.' + c for c in cols)}, ?, NULL FROM _stage s "
            f"WHERE NOT EXISTS (SELECT 1 FROM {table} t WHERE {on} AND t.superseded_at IS NULL)",
            [now],
        ).fetchone()
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.execute("DROP TABLE IF EXISTS _stage")
    stats.unchanged += 0 if unchanged is None else int(unchanged[0])
    stats.superseded += 0 if changed is None else int(changed[0])
    stats.inserted += 0 if inserted is None else int(inserted[0])


def _bulk_plain(
    con: duckdb.DuckDBPyConnection,
    table: str,
    rows: Iterable[Mapping[str, Any]],
    types: Mapping[str, str],
    stats: LoadStats,
    workdir: Path,
) -> None:
    pk = PROVENANCE_TABLES.get(table) or OTHER_TABLES[table]
    latest: dict[Any, dict[str, Any]] = {}
    for raw in rows:
        row = convert_row(table, raw, types)
        if row.get(pk) in (None, ""):
            raise LoadError(f"{table}: missing primary key {pk}")
        if row[pk] in latest and latest[row[pk]] != row:
            raise LoadError(f"{table}: {pk}={row[pk]!r} appears twice with different content")
        latest[row[pk]] = row
    stats.by_table[table] = stats.by_table.get(table, 0) + len(latest)
    if not latest:
        return
    cols = sorted({c for r in latest.values() for c in r})
    _stage(con, list(latest.values()), cols, types, workdir)
    differs = " OR ".join(f"t.{c} IS DISTINCT FROM s.{c}" for c in cols)
    try:
        conflict = con.execute(
            f"SELECT count(*) FROM _stage s JOIN {table} t ON t.{pk} = s.{pk} "  # noqa: S608
            f"WHERE {differs}"
        ).fetchone()
        if conflict is not None and int(conflict[0]) > 0:
            raise LoadError(f"{table}: {conflict[0]} row(s) already exist with different content")
        existing = con.execute(
            f"SELECT count(*) FROM _stage s JOIN {table} t ON t.{pk} = s.{pk}"  # noqa: S608
        ).fetchone()
        inserted = con.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM _stage s "  # noqa: S608
            f"WHERE NOT EXISTS (SELECT 1 FROM {table} t WHERE t.{pk} = s.{pk})"
        ).fetchone()
    finally:
        con.execute("DROP TABLE IF EXISTS _stage")
    stats.unchanged += 0 if existing is None else int(existing[0])
    stats.inserted += 0 if inserted is None else int(inserted[0])
