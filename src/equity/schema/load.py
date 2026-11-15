"""Append-only loader with bitemporal supersession.

Fact rows are never updated in place. When a source re-publishes a fact with the same domain
key but different content, the current row gets `superseded_at` and a new row is inserted.
Re-loading identical content is a no-op, so loads are idempotent.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import duckdb

from equity.schema.catalog import (
    FACT_TABLES,
    LOADER_COLUMNS,
    OTHER_TABLES,
    PROVENANCE_COLUMNS,
    PROVENANCE_TABLES,
)
from equity.schema.clock import Clock
from equity.schema.ids import stable_id


class LoadError(ValueError):
    pass


@dataclass
class LoadStats:
    inserted: int = 0
    unchanged: int = 0
    superseded: int = 0
    by_table: dict[str, int] = field(default_factory=dict)


def column_types(con: duckdb.DuckDBPyConnection, table: str) -> dict[str, str]:
    rows = con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [table],
    ).fetchall()
    if not rows:
        raise LoadError(f"unknown table {table!r}")
    return {str(name): str(dtype).upper() for name, dtype in rows}


def _convert(value: Any, dtype: str, column: str) -> Any:
    """Turn a JSON-ish value into the Python type DuckDB expects for `dtype`."""
    if value is None:
        return None
    if dtype == "DATE":
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    if dtype.startswith("TIMESTAMP"):
        ts = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if ts.tzinfo is None:
            raise LoadError(f"{column}: timestamps must carry a timezone, got {value!r}")
        return ts.astimezone(UTC)
    if dtype.startswith("DECIMAL"):
        if isinstance(value, float):
            raise LoadError(f"{column}: pass money as a string, not a float ({value!r})")
        return Decimal(str(value))
    if dtype == "JSON":
        return json.dumps(
            value if not isinstance(value, str) else json.loads(value),
            sort_keys=True,
            separators=(",", ":"),
        )
    if dtype == "BLOB":
        return value if isinstance(value, bytes) else bytes.fromhex(str(value))
    if dtype == "BOOLEAN":
        if not isinstance(value, bool):
            raise LoadError(f"{column}: expected a boolean, got {value!r}")
        return value
    if dtype in {"INTEGER", "BIGINT"}:
        return int(value)
    if dtype == "DOUBLE":
        return float(value)
    return str(value)


def canonical(value: Any) -> str:
    """A stable text form used for hashing and change detection."""
    if value is None:
        return "\x00null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _fact_columns(types: Mapping[str, str]) -> list[str]:
    skip = {*LOADER_COLUMNS, *PROVENANCE_COLUMNS}
    return [c for c in types if c not in skip]


def _content_hash(table: str, row: Mapping[str, Any], columns: Iterable[str]) -> str:
    cols = sorted(columns)
    return stable_id(table, *[f"{c}={canonical(row.get(c))}" for c in cols])


def load_rows(
    con: duckdb.DuckDBPyConnection,
    table: str,
    rows: Iterable[Mapping[str, Any]],
    clock: Clock,
    stats: LoadStats | None = None,
) -> LoadStats:
    stats = stats or LoadStats()
    types = column_types(con, table)
    for raw in rows:
        unknown = set(raw) - set(types)
        if unknown:
            raise LoadError(f"{table}: unknown columns {sorted(unknown)}")
        owned = set(raw) & set(LOADER_COLUMNS) if table in FACT_TABLES else set()
        if owned:
            raise LoadError(f"{table}: loader-owned columns must not be passed: {sorted(owned)}")
        row = {c: _convert(raw.get(c), types[c], c) for c in raw}
        if table in FACT_TABLES:
            _load_fact(con, table, row, types, clock, stats)
        else:
            _load_plain(con, table, row, stats)
        stats.by_table[table] = stats.by_table.get(table, 0) + 1
    return stats


def _load_plain(
    con: duckdb.DuckDBPyConnection, table: str, row: dict[str, Any], stats: LoadStats
) -> None:
    pk = PROVENANCE_TABLES.get(table) or OTHER_TABLES.get(table)
    if pk is None:
        raise LoadError(f"{table}: not a loadable table")
    if row.get(pk) in (None, ""):
        raise LoadError(f"{table}: missing primary key {pk}")
    existing = con.execute(f"SELECT * FROM {table} WHERE {pk} = ?", [row[pk]]).fetchone()  # noqa: S608
    if existing is not None:
        names = [d[0] for d in con.description or []]
        current = dict(zip(names, existing, strict=True))
        if all(canonical(current.get(c)) == canonical(v) for c, v in row.items()):
            stats.unchanged += 1
            return
        raise LoadError(f"{table}: {pk}={row[pk]!r} already exists with different content")
    _insert(con, table, row)
    stats.inserted += 1


def _load_fact(
    con: duckdb.DuckDBPyConnection,
    table: str,
    row: dict[str, Any],
    types: Mapping[str, str],
    clock: Clock,
    stats: LoadStats,
) -> None:
    spec = FACT_TABLES[table]
    missing = [c for c in PROVENANCE_COLUMNS if row.get(c) in (None, "")]
    if missing:
        raise LoadError(f"{table}: missing provenance {missing}")
    key_cols = ("source_id", *spec.domain_key)
    for c in key_cols:
        if c not in row:
            raise LoadError(f"{table}: missing domain-key column {c}")
    fact_cols = [c for c in _fact_columns(types) if c not in spec.unhashed]
    new_hash = _content_hash(table, row, fact_cols)

    where = " AND ".join(f"{c} IS NULL" if row[c] is None else f"{c} = ?" for c in key_cols)
    params = [row[c] for c in key_cols if row[c] is not None]
    current = con.execute(
        f"SELECT * FROM {table} WHERE superseded_at IS NULL AND {where}",  # noqa: S608
        params,
    ).fetchall()
    names = [d[0] for d in con.description or []]
    now = clock()
    if len(current) > 1:
        raise LoadError(f"{table}: more than one current row for key {params}")
    if current:
        cur = dict(zip(names, current[0], strict=True))
        if _content_hash(table, cur, fact_cols) == new_hash:
            stats.unchanged += 1
            return
        con.execute(
            f"UPDATE {table} SET superseded_at = ? WHERE row_id = ?",  # noqa: S608
            [now, cur["row_id"]],
        )
        stats.superseded += 1

    full = dict(row)
    full["row_id"] = stable_id(table, new_hash, canonical(row["retrieved_at"]))
    full["ingested_at"] = now
    full["superseded_at"] = None
    _insert(con, table, full)
    stats.inserted += 1


def _insert(con: duckdb.DuckDBPyConnection, table: str, row: Mapping[str, Any]) -> None:
    cols = list(row)
    placeholders = ", ".join("?" for _ in cols)
    con.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",  # noqa: S608
        [row[c] for c in cols],
    )
