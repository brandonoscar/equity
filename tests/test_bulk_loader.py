"""The set-based loader produces exactly what the row loader produces."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from equity.pipeline import export_snapshot, run_manifest
from equity.schema.bulk import load_bulk
from equity.schema.clock import fixed_clock
from equity.schema.load import LoadError, LoadStats, load_rows
from equity.schema.migrate import connect, migrate

from .conftest import SYNTHETIC_MANIFEST


def _snapshot(con, out: Path) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in export_snapshot(con, out)}


def test_bulk_and_row_loaders_give_byte_identical_snapshots(tmp_path: Path) -> None:
    row = run_manifest(str(tmp_path / "row.duckdb"), SYNTHETIC_MANIFEST)
    bulk = run_manifest(str(tmp_path / "bulk.duckdb"), SYNTHETIC_MANIFEST, bulk=True)
    assert _snapshot(row, tmp_path / "r") == _snapshot(bulk, tmp_path / "b")


def _row(key: int, value: int, retrieved: datetime) -> dict[str, Any]:
    return {
        "parcel_uid": f"99001-P{key}", "tax_year": 2025, "appraised_total": f"{value}.00",
        "valid_from": "2025-01-01", "source_record_id": f"sr-{key}", "source_id": "prop",
        "jurisdiction": "99001", "record_key": f"P{key}", "source_uri": f"mem://{key}",
        "retrieved_at": retrieved.isoformat(), "content_sha256": "c" * 64,
    }  # fmt: skip


batches = st.lists(
    st.dictionaries(st.integers(0, 6), st.integers(0, 3), min_size=1, max_size=5),
    min_size=1,
    max_size=4,
)


@settings(max_examples=30, deadline=None)
@given(batches)
def test_equivalent_on_random_refetch_sequences(seq: list[dict[int, int]]) -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    cons = []
    for loader in (load_rows, load_bulk):
        con = connect()
        migrate(con, fixed_clock(t0))
        for i, batch in enumerate(seq):
            at = t0 + timedelta(days=i + 1)
            rows = [_row(k, v, at) for k, v in sorted(batch.items())]
            loader(con, "parcel_assessment", rows, fixed_clock(at))
        cons.append(con)
    q = "SELECT * FROM parcel_assessment ORDER BY row_id"
    assert cons[0].execute(q).fetchall() == cons[1].execute(q).fetchall()


def test_bulk_last_row_wins_within_a_batch(empty_db) -> None:  # type: ignore[no-untyped-def]
    at = datetime(2026, 2, 1, tzinfo=UTC)
    stats = load_bulk(empty_db, "parcel_assessment", [_row(1, 1, at), _row(1, 2, at)],
                      fixed_clock(at))  # fmt: skip
    assert stats.inserted == 1
    assert empty_db.execute("SELECT appraised_total FROM parcel_assessment").fetchall() == [
        (__import__("decimal").Decimal("2.00"),)
    ]
    again = load_bulk(empty_db, "parcel_assessment", [_row(1, 2, at)], fixed_clock(at))
    assert (again.inserted, again.unchanged) == (0, 1)


def _source(summary: str = "x") -> dict[str, Any]:
    return {"source_id": "s1", "kind": "fixture", "jurisdiction": "99001",
            "access_method": "fixture", "base_url": "file://x", "terms_summary": summary,
            "cost_model": "free"}  # fmt: skip


def test_bulk_plain_tables(empty_db) -> None:  # type: ignore[no-untyped-def]
    clock = fixed_clock(datetime(2026, 1, 1, tzinfo=UTC))
    stats = LoadStats()
    load_bulk(empty_db, "source", [_source(), _source()], clock, stats)
    load_bulk(empty_db, "source", [_source()], clock, stats)
    assert (stats.inserted, stats.unchanged) == (1, 1)
    with pytest.raises(LoadError, match="different content"):
        load_bulk(empty_db, "source", [_source("changed")], clock)
    with pytest.raises(LoadError, match="appears twice"):
        load_bulk(empty_db, "source", [_source("a"), _source("b")], clock)
    with pytest.raises(LoadError, match="primary key"):
        load_bulk(empty_db, "source", [{**_source(), "source_id": ""}], clock)
    with pytest.raises(LoadError, match="not a loadable"):
        load_bulk(empty_db, "schema_migrations", [], clock)
    assert load_bulk(empty_db, "parcel", [], clock).inserted == 0
    assert load_bulk(empty_db, "address", [], clock).inserted == 0


def test_bulk_rolls_back_on_failure(empty_db, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    at = datetime(2026, 2, 1, tzinfo=UTC)
    load_bulk(empty_db, "parcel_assessment", [_row(1, 1, at)], fixed_clock(at))

    def boom() -> datetime:
        raise RuntimeError("clock failed")

    with pytest.raises(RuntimeError):
        load_bulk(empty_db, "parcel_assessment", [_row(1, 5, at)], boom)
    assert empty_db.execute("SELECT count(*) FROM parcel_assessment").fetchone() == (1,)
