"""Committed fixture JSONL must equal what build_synthetic.py generates."""

from __future__ import annotations

from pathlib import Path

from .conftest import SYNTHETIC_MANIFEST
from .fixtures import build_synthetic


def test_committed_fixtures_match_generator(tmp_path: Path) -> None:
    build_synthetic.main(tmp_path)
    committed = SYNTHETIC_MANIFEST.parent
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == sorted(p.name for p in committed.iterdir())
    for name in names:
        assert (tmp_path / name).read_bytes() == (committed / name).read_bytes(), name


def test_fixture_names_are_synthetic() -> None:
    text = "".join(p.read_text() for p in SYNTHETIC_MANIFEST.parent.glob("*.jsonl"))
    assert '"jurisdiction": "99001"' in text
    assert '"jurisdiction": "54' not in text  # no real WV county codes in fixtures
