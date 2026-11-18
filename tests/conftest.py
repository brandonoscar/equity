from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from equity.config import DocTypes, doc_types
from equity.pipeline import run_manifest
from equity.schema.clock import fixed_clock
from equity.schema.migrate import connect, migrate

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC_MANIFEST = FIXTURES / "synthetic" / "manifest.json"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(scope="session")
def doc_types_cfg() -> DocTypes:
    return doc_types()


@pytest.fixture(scope="session")
def fixture_db() -> Iterator[duckdb.DuckDBPyConnection]:
    """The synthetic county, loaded once. Tests must not mutate it."""
    con = run_manifest(":memory:", SYNTHETIC_MANIFEST)
    yield con
    con.close()


@pytest.fixture
def empty_db() -> Iterator[duckdb.DuckDBPyConnection]:
    con = connect(":memory:")
    migrate(con, fixed_clock(T0))
    yield con
    con.close()


@pytest.fixture
def scratch_db() -> Iterator[duckdb.DuckDBPyConnection]:
    """A fresh copy of the synthetic county that a test may mutate."""
    con = run_manifest(":memory:", SYNTHETIC_MANIFEST)
    yield con
    con.close()
