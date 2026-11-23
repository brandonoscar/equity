"""docs/gaps.md generator: layers per state from source ids, configs, debt kinds and runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from equity import gaps
from equity.gaps import build, render


def test_layers_are_read_from_source_ids_configs_kinds_and_runs(tmp_path: Path) -> None:
    local = tmp_path / "local.json"
    local.write_text(json.dumps({"layers": [{"state_fips": "54"}, {"state_fips": "54"}]}))
    ids = ["wv.statewide.parcels", "us.wvnb.rss", "fl.hillsborough.or",
           "fl.hillsborough.civil.cases", "fl.dor.tax_warrants", "fl.lee.nuisance_liens",
           "ny.sos.business", "nj.dca.code_links", "ri.statewide.zoning",
           "ks.douglas.parcels"]  # fmt: skip
    kinds = {"fl.hillsborough.civil.cases": "court_judgment", "fl.dor.tax_warrants": "tax_warrant",
             "fl.hillsborough.or": "recorded_judgment_or_lien",
             "fl.lee.nuisance_liens": "code_enforcement_lien"}  # fmt: skip
    rows = {r.state: r for r in build(ids, local, kinds, ["WV", "FL", "NY-NYC-LIENSALE", "NY"])}
    wv = rows["WV"]
    assert (wv.parcels, wv.bankruptcy, wv.zoning, wv.runs) == (
        "statewide", ("us.wvnb.rss",), "2 local layers", ("WV",))  # fmt: skip
    assert "owner" in wv.fields
    assert rows["FL"].instruments == ("fl.hillsborough.or",)
    assert rows["FL"].debts == (("code_enforcement_lien", 1), ("court_judgment", 1),
                                ("recorded_judgment_or_lien", 1), ("tax_warrant", 1))  # fmt: skip
    assert rows["NY"].runs == ("NY", "NY-NYC-LIENSALE") and rows["NY"].debts == ()
    assert rows["NY"].entities == ("ny.sos.business",)
    assert rows["NJ"].ordinances == ("nj.dca.code_links",)
    assert rows["RI"].zoning == "statewide"
    assert rows["KS"].parcels == "1 of 105 counties"
    assert "owner" in rows["KS"].fields  # from config/counties/ks.douglas
    assert rows["MT"].parcels == "none" and rows["MT"].zoning == "none"
    text = render(list(rows.values()))
    assert text.startswith("# Data gaps by state")
    assert "| Court judgments | 1 | |" in text
    assert "court_judgment (1)<br>recorded_judgment_or_lien (1)" in text


def test_docs_gaps_is_up_to_date(capsys: pytest.CaptureFixture[str]) -> None:
    gaps.main()
    committed = (Path(__file__).parents[1] / "docs" / "gaps.md").read_text()
    assert capsys.readouterr().out == committed, "run: uv run python -m equity.gaps > docs/gaps.md"
