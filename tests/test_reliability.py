"""Reliability: results do not depend on the order rows arrive in, a match run is repeatable,
and re-running over an unchanged lake changes nothing."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from equity.adapters.base import Fetched
from equity.adapters.registry import REGISTRY
from equity.matching.resolve import run

from .test_resolve import lake  # noqa: F401 (the pytest fixture)

FIXTURES = Path(__file__).parent / "fixtures" / "adapters"
AT = datetime(2025, 12, 31, tzinfo=UTC)


def _facts(cls: type, body: bytes) -> list[str]:
    fetched = Fetched(cls.source_id, "fixture", AT, 200, body, "application/json")
    return sorted(json.dumps(dict(r.row), sort_keys=True, default=str) + r.table
                  for r in cls().normalize(fetched))  # fmt: skip


def test_lien_sources_give_the_same_facts_whatever_the_row_order() -> None:
    checked = 0
    for cls in REGISTRY:
        config = getattr(cls, "config", None)
        if config is None or not hasattr(config, "pii_fields"):
            continue  # only the config-driven lien adapters (config/liens/*.yaml)
        for path in sorted((FIXTURES / cls.source_id).glob("*.json")):
            data = json.loads(path.read_text())
            rows = data.get("rows")
            if not isinstance(rows, list) or len(rows) < 2:
                continue
            forward = _facts(cls, path.read_bytes())
            backward = _facts(cls, json.dumps({**data, "rows": rows[::-1]}).encode())
            assert forward == backward, f"{cls.source_id}: facts depend on row order"
            checked += 1
    assert checked >= 40  # every lien config with a multi-row fixture


def _digest(folder: Path) -> dict[str, str]:
    """Per table: a hash of its rows sorted, so file layout does not matter, content does."""
    con = duckdb.connect()
    out = {}
    for f in sorted(folder.glob("*.parquet")):
        rows = con.execute(f"SELECT * FROM '{f.as_posix()}'").fetchall()
        text = "\n".join(sorted(json.dumps(r, default=str) for r in rows))
        out[f.name] = hashlib.sha256(text.encode()).hexdigest()
    return out


def test_a_match_run_is_repeatable_and_rerunning_changes_nothing(
    lake: Path,  # noqa: F811
    tmp_path: Path,
) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    first = run(lake, a, ["zz.debts"], ["zz.parcels"])
    second = run(lake, b, ["zz.debts"], ["zz.parcels"])
    assert first == second
    assert _digest(a) == _digest(b) and _digest(a)  # same rows in every output table
    again = run(lake, a, ["zz.debts"], ["zz.parcels"])  # over the same folder
    assert again == first and _digest(a) == _digest(b)
