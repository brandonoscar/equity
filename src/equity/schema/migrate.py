"""Forward-only, checksummed SQL migrations for the DuckDB catalog."""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources

import duckdb

from equity.schema.clock import Clock
from equity.schema.ids import sha256_hex

_NAME = re.compile(r"^V(\d{4})__([a-z0-9_]+)\.sql$")

_BOOKKEEPING = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       VARCHAR NOT NULL,
    checksum   VARCHAR NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL
)
"""


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return sha256_hex(self.sql.encode("utf-8"))


def discover() -> list[Migration]:
    """All migration files shipped with the package, in version order."""
    found: list[Migration] = []
    for entry in resources.files("equity.schema.migrations").iterdir():
        match = _NAME.match(entry.name)
        if match is None:
            continue
        found.append(Migration(int(match.group(1)), match.group(2), entry.read_text("utf-8")))
    found.sort(key=lambda m: m.version)
    versions = [m.version for m in found]
    if versions != list(range(1, len(found) + 1)):
        raise MigrationError(f"migration versions must be contiguous from 1, got {versions}")
    return found


def connect(path: str = ":memory:") -> duckdb.DuckDBPyConnection:
    """Open a connection with the session settings every module assumes."""
    con = duckdb.connect(path)
    con.execute("SET TimeZone = 'UTC'")
    return con


def applied(con: duckdb.DuckDBPyConnection) -> dict[int, str]:
    con.execute(_BOOKKEEPING)
    rows = con.execute("SELECT version, checksum FROM schema_migrations").fetchall()
    return {int(v): str(c) for v, c in rows}


def migrate(con: duckdb.DuckDBPyConnection, clock: Clock) -> list[int]:
    """Apply pending migrations. Returns the versions applied by this call.

    Running it twice is a no-op. A migration that was edited after being applied is an
    error: write a new migration instead.
    """
    done = applied(con)
    newly: list[int] = []
    for mig in discover():
        if mig.version in done:
            if done[mig.version] != mig.checksum:
                raise MigrationError(
                    f"V{mig.version:04d}__{mig.name} changed after it was applied; "
                    "add a new migration instead of editing an old one"
                )
            continue
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute(mig.sql)
            con.execute(
                "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                [mig.version, mig.name, mig.checksum, clock()],
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        newly.append(mig.version)
    return newly
