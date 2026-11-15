"""Check 5: the full pipeline run twice on fixtures produces byte-identical output."""

from __future__ import annotations

import hashlib
from pathlib import Path

from equity.pipeline import export_snapshot, run_manifest

from .conftest import SYNTHETIC_MANIFEST


def _run(tmp: Path, name: str) -> dict[str, str]:
    con = run_manifest(str(tmp / f"{name}.duckdb"), SYNTHETIC_MANIFEST)
    files = export_snapshot(con, tmp / name)
    con.close()
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}


def test_two_runs_are_byte_identical(tmp_path: Path) -> None:
    first = _run(tmp_path, "a")
    second = _run(tmp_path, "b")
    assert first == second
    assert len(first) >= 29
    # Sanity: the snapshot is not trivially empty.
    assert (tmp_path / "a" / "instrument.csv").read_text().count("\n") == 11
