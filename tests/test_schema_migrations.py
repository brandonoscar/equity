"""Check 8: migrate up from empty, prove idempotence, then load fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from equity.pipeline import ingest
from equity.schema import migrate as mig
from equity.schema.catalog import FACT_TABLES, PROVENANCE_COLUMNS, all_tables, primary_key
from equity.schema.clock import fixed_clock
from equity.schema.migrate import MigrationError, connect, discover, migrate

from .conftest import SYNTHETIC_MANIFEST, T0


def test_migrate_from_empty_then_again_is_noop() -> None:
    con = connect()
    first = migrate(con, fixed_clock(T0))
    assert first == [m.version for m in discover()]
    assert migrate(con, fixed_clock(T0)) == []
    rows = con.execute("SELECT count(*) FROM schema_migrations").fetchone()
    assert rows is not None and rows[0] == len(first)


def test_every_catalog_table_exists(empty_db) -> None:  # type: ignore[no-untyped-def]
    present = {
        r[0]
        for r in empty_db.execute("SELECT table_name FROM information_schema.tables").fetchall()
    }
    assert set(all_tables()) <= present


@pytest.mark.parametrize("table", sorted(FACT_TABLES))
def test_fact_tables_carry_required_provenance(empty_db, table: str) -> None:  # type: ignore[no-untyped-def]
    cols = {
        r[0]: r[1]
        for r in empty_db.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name = ?",
            [table],
        ).fetchall()
    }
    for col in (*PROVENANCE_COLUMNS, "row_id", "ingested_at"):
        assert col in cols, f"{table} lacks {col}"
        assert cols[col] == "NO", f"{table}.{col} must be NOT NULL"
    assert cols["superseded_at"] == "YES"
    for key in FACT_TABLES[table].domain_key:
        assert key in cols, f"{table} domain key column {key} missing"


def test_primary_key_lookup() -> None:
    assert primary_key("instrument") == "row_id"
    assert primary_key("source") == "source_id"
    assert primary_key("entity") == "entity_id"
    with pytest.raises(KeyError):
        primary_key("nope")


def test_edited_migration_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    con = connect()
    migrate(con, fixed_clock(T0))
    original = discover()
    tampered = [mig.Migration(m.version, m.name, m.sql + "\n-- edit") for m in original]
    monkeypatch.setattr(mig, "discover", lambda: tampered)
    with pytest.raises(MigrationError, match="changed after it was applied"):
        migrate(con, fixed_clock(T0))


def test_failed_migration_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    con = connect()
    broken = [mig.Migration(1, "broken", "CREATE TABLE ok_t (a INT); SELECT * FROM nope;")]
    monkeypatch.setattr(mig, "discover", lambda: broken)
    with pytest.raises(Exception, match="nope"):
        migrate(con, fixed_clock(T0))
    tables = {
        r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
    }
    assert "ok_t" not in tables


def test_discover_rejects_gaps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ("V0001__a.sql", "V0003__c.sql", "README.md"):
        (tmp_path / name).write_text("SELECT 1;")

    class _Files:
        def iterdir(self):  # type: ignore[no-untyped-def]
            return iter(sorted(tmp_path.iterdir()))

    monkeypatch.setattr(mig.resources, "files", lambda _pkg: _Files())
    with pytest.raises(MigrationError, match="contiguous"):
        mig.discover()


def test_fixtures_load_into_fresh_schema(empty_db) -> None:  # type: ignore[no-untyped-def]
    files = sorted(SYNTHETIC_MANIFEST.parent.glob("*.jsonl"))
    stats = ingest(empty_db, files, fixed_clock(datetime(2026, 4, 1, tzinfo=UTC)))
    assert stats.inserted > 50
    count = empty_db.execute("SELECT count(*) FROM instrument").fetchone()
    assert count is not None and count[0] == 10
