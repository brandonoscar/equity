from __future__ import annotations

from pathlib import Path

from equity import coverage
from equity.adapters.state_parcels import config_paths, load_config


def test_every_state_listed_once_and_built_states_marked() -> None:
    table = coverage.rows([load_config(p) for p in config_paths()], {"XX": "ignored"})
    assert len(coverage.STATES) == 51
    assert [r.state for r in table] == list(coverage.STATES)
    ar = next(r for r in table if r.state == "AR")
    assert ar.sources and ar.owner and ar.values
    text = coverage.render(table)
    assert text.count("\n| ") == 52  # header + 51 rows


def test_docs_coverage_is_up_to_date(capsys) -> None:  # type: ignore[no-untyped-def]
    coverage.main()
    generated = capsys.readouterr().out
    committed = (Path(__file__).parents[1] / "docs" / "coverage.md").read_text()
    assert generated == committed, "run: uv run python -m equity.coverage > docs/coverage.md"
