"""docs/gaps.md generator: layers per state from source ids, configs and lake state."""

from __future__ import annotations

import json
from pathlib import Path

from equity.gaps import build, render


def test_layers_are_read_from_source_ids_configs_and_lake(tmp_path: Path) -> None:
    lake = tmp_path / "lake"
    (lake / "wv.statewide.parcels").mkdir(parents=True)
    (lake / "wv.statewide.parcels" / "_counts.json").write_text(json.dumps({"parcel": 12}))
    local = tmp_path / "local.json"
    local.write_text(json.dumps({"layers": [{"state_fips": "54"}, {"state_fips": "54"}]}))
    ids = ["wv.statewide.parcels", "us.wvnb.rss", "fl.hillsborough.or",
           "fl.hillsborough.civil.cases", "ny.sos.business", "nj.dca.code_links",
           "ri.statewide.zoning", "ks.douglas.parcels"]  # fmt: skip
    rows = {r.state: r for r in build(ids, lake, local)}
    wv = rows["WV"]
    assert (wv.parcels, wv.loaded, wv.bankruptcy, wv.zoning) == (
        "statewide", 12, ("us.wvnb.rss",), "2 local layers")  # fmt: skip
    assert "owner" in wv.fields
    assert rows["FL"].instruments == ("fl.hillsborough.or",)
    assert rows["FL"].judgments == ("fl.hillsborough.civil.cases",)
    assert rows["NY"].entities == ("ny.sos.business",)
    assert rows["NJ"].ordinances == ("nj.dca.code_links",)
    assert rows["RI"].zoning == "statewide"
    assert rows["KS"].parcels == "1 of 105 counties"
    assert "owner" in rows["KS"].fields  # from config/counties/ks.douglas
    assert rows["MT"].parcels == "none" and rows["MT"].zoning == "none"
    text = render(list(rows.values()))
    assert text.startswith("# Data gaps by state")
    assert "| WV | statewide | 12 |" in text
