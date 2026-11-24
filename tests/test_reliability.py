"""Reliability: results do not depend on the order rows arrive in, a match run is repeatable,
and re-running over an unchanged lake changes nothing."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

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


def test_a_run_names_the_sources_missing_from_the_lake_and_can_refuse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from equity.matching.resolve import main, missing_sources, state_sources

    empty = tmp_path / "lake"
    empty.mkdir()
    assert set(state_sources("DC")) <= set(missing_sources("DC", empty))
    assert main(["--state", "DC", "--lake", str(empty), "--require-all"]) == 2
    assert "dc.otr.delinquent_taxes" in capsys.readouterr().err
    (empty / "dc.otr.delinquent_taxes" / "instrument").mkdir(parents=True)
    (empty / "dc.otr.delinquent_taxes" / "instrument" / "0.parquet").write_bytes(b"")
    assert "dc.otr.delinquent_taxes" not in missing_sources("DC", empty)


def test_the_memory_limit_comes_from_the_environment(
    lake: Path,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from equity.matching.resolve import memory_limit

    monkeypatch.delenv("EQUITY_MEMORY_LIMIT", raising=False)
    assert memory_limit() is None
    monkeypatch.setenv("EQUITY_MEMORY_LIMIT", "512mb")
    assert memory_limit() == "512MB"
    capped = run(lake, tmp_path / "capped", ["zz.debts"], ["zz.parcels"])
    assert capped == run(lake, tmp_path / "free", ["zz.debts"], ["zz.parcels"])
    monkeypatch.setenv("EQUITY_MEMORY_LIMIT", "lots; DROP")
    with pytest.raises(ValueError, match="EQUITY_MEMORY_LIMIT"):
        memory_limit()
