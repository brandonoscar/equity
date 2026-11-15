from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from equity.pipeline import read_jsonl, run, run_manifest
from equity.schema.clock import fixed_clock, system_clock
from equity.schema.load import LoadError

from .conftest import SYNTHETIC_MANIFEST


def test_run_loads_files_in_order(tmp_path: Path) -> None:
    files = sorted(SYNTHETIC_MANIFEST.parent.glob("*.jsonl"))
    con = run(str(tmp_path / "x.duckdb"), files, fixed_clock(datetime(2026, 4, 1, tzinfo=UTC)))
    assert con.execute("SELECT count(*) FROM judgment").fetchone() == (1,)


def test_jsonl_shape_is_enforced(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text('\n{"table": "source"}\n')
    with pytest.raises(LoadError, match=r"bad\.jsonl:2"):
        list(read_jsonl(bad))


def test_manifest_needs_batches(tmp_path: Path) -> None:
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps({"batches": []}))
    with pytest.raises(LoadError, match="no batches"):
        run_manifest(":memory:", m)


def test_clocks() -> None:
    now = system_clock()
    assert now.tzinfo is not None
    assert abs(datetime.now(UTC) - now) < timedelta(seconds=5)
    with pytest.raises(ValueError, match="timezone-aware"):
        fixed_clock(datetime(2026, 1, 1))  # noqa: DTZ001 - deliberately naive
