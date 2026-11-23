"""Debtor scoring scaffold and saved queries (equity.rules.score, equity.rules.queries)."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest
import yaml

from equity.matching.resolve import run
from equity.rules import queries, score

from .test_resolve import lake  # noqa: F401 (the pytest fixture)


def _derived(lake_dir: Path, tmp_path: Path) -> Path:
    derived = tmp_path / "derived"
    run(lake_dir, derived / "zz", ["zz.debts"], ["zz.parcels"])
    return derived


def _cfg(tmp_path: Path, weights: dict[str, float | None], tiers: list[dict[str, object]],
         years: float | None) -> Path:  # fmt: skip
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    base = yaml.safe_load((Path(score.__file__).parents[3] / "config" / "scoring.yaml").read_text())
    base["factors"] = {k: weights.get(k) for k in base["factors"]}
    base["tiers"] = tiers
    (cfg / "scoring.yaml").write_text(yaml.safe_dump(base))
    (cfg / "sol.yaml").write_text(yaml.safe_dump(
        {"states": {"ZZ": {"judgment_enforceable_years": years}}}))  # fmt: skip
    return cfg


def test_factors_only_while_weights_are_unset(
    lake: Path,  # noqa: F811
    tmp_path: Path,
) -> None:
    derived = _derived(lake, tmp_path)
    report = score.score_state("ZZ", derived, _cfg(tmp_path, {}, [], None))
    assert report["scored"] is False
    assert "open_amount" in report["missing_parameters"]
    assert "sol.yaml ZZ.judgment_enforceable_years" in report["missing_parameters"]
    rows = (
        duckdb.connect()
        .execute(f"SELECT score, tier, open_amount, parcels FROM '{derived}/zz/scores.parquet'")
        .fetchall()
    )
    assert rows and all(r[0] is None and r[1] is None for r in rows)
    assert json.loads((derived / "zz" / "score_report.json").read_text())["scored"] is False


def test_scores_and_tiers_once_every_weight_is_set(
    lake: Path,  # noqa: F811
    tmp_path: Path,
) -> None:
    derived = _derived(lake, tmp_path)
    factors = yaml.safe_load(
        (Path(score.__file__).parents[3] / "config" / "scoring.yaml").read_text()
    )["factors"]
    w = dict.fromkeys(factors, 0.0) | {"open_amount": 1.0, "parcels": 100.0}
    tiers = [{"name": "B", "min_score": 150}, {"name": "A", "min_score": 300}]
    report = score.score_state("ZZ", derived, _cfg(tmp_path, w, tiers, 10))
    assert report == {"state": "ZZ", "people": report["people"], "scored": True,
                      "missing_parameters": []}  # fmt: skip
    got = {r[0]: r[1:] for r in duckdb.connect().execute(
        f"SELECT name, score, tier, sol_years_left FROM '{derived}/zz/scores.parquet'"
    ).fetchall()}  # fmt: skip
    # JOHN A SMITH: open 100 + 1 parcel x 100 = 200 -> B; PAT KIM: 500 + 100 = 600 -> A
    assert got["JOHN A SMITH"] == (200.0, "B", 10.0)
    assert got["PAT KIM"] == (600.0, "A", 10.0)


def test_saved_query_and_new_since_last_run(
    lake: Path,  # noqa: F811
    tmp_path: Path,
) -> None:
    derived = _derived(lake, tmp_path)
    spec = {"name": "test-q", "states": ["ZZ"], "where": {"require_parcels": True,
            "min_open_amount": 150}, "order_by": "open_amount", "limit": 10}  # fmt: skip
    first = queries.run_query(spec, derived, today="2026-11-22")
    assert first["matched"] >= 1 and first["new_since_last"] == first["matched"]
    second = queries.run_query(spec, derived, today="2026-11-23")
    assert second["new_since_last"] == 0 and second["compared_with"] == "2026-11-22"
    wider = {**spec, "where": {"require_parcels": True}}
    third = queries.run_query(wider, derived, today="2026-11-24")
    assert third["new_since_last"] == third["matched"] - first["matched"] > 0
    with pytest.raises(ValueError, match="unknown filters"):
        queries.where_sql({"min_age": 3})
    with pytest.raises(ValueError, match="order_by"):
        queries.run_query({**spec, "order_by": "name; DROP"}, derived)
    assert queries.where_sql({}) == "true"


def test_query_filters_validation_and_cli(
    lake: Path,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    where = {"min_parcel_value": 1, "debt_kinds_any": ["tax_lien"],
             "exclude_bankruptcy": True, "max_transfers_after_debt": 0}  # fmt: skip
    sql = queries.where_sql(where)
    assert "parcel_value >= 1.0" in sql
    assert "list_has_any(debt_kinds, ['tax_lien'])" in sql
    assert "bankruptcy_open = 0" in sql and "transfers_after_debt <= 0.0" in sql
    for bad, msg in (({"min_open_amount": "10"}, "must be a number"),
                     ({"min_open_amount": True}, "must be a number"),
                     ({"debt_kinds_any": ["x'; --"]}, "debt kind names")):  # fmt: skip
        with pytest.raises(ValueError, match=msg):
            queries.where_sql(bad)
    with pytest.raises(ValueError, match="query name"):
        queries.run_query({"name": "../x", "states": ["ZZ"]}, tmp_path)
    derived = _derived(lake, tmp_path)
    qfile = tmp_path / "q.yaml"
    qfile.write_text(yaml.safe_dump({"name": "cli", "states": ["ZZ"], "where": {}}))
    assert queries.main(["--file", str(qfile), "--derived", str(derived)]) == 0
    assert '"query": "cli"' in capsys.readouterr().out
    monkeypatch.setattr(queries, "QUERY_DIR", tmp_path / "none")
    assert queries.main(["--derived", str(derived)]) == 0
    assert "no queries" in capsys.readouterr().err


def test_score_cli_and_missing_run(
    lake: Path,  # noqa: F811
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(FileNotFoundError, match="run the ZZ match first"):
        score.score_state("ZZ", tmp_path / "nothing")
    derived = _derived(lake, tmp_path)
    assert score.main(["--state", "ZZ", "--derived", str(derived)]) == 0
    assert '"scored": false' in capsys.readouterr().out
    assert score.enforceable_years("WV") is None  # sol.yaml is Brandon's: all null
    con = duckdb.connect()
    with pytest.raises(FileNotFoundError):
        score._view(con, "x", tmp_path / "missing.parquet", None)
