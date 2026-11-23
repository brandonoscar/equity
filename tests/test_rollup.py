"""The cross-state rollup: counts by state and one review queue, nothing matched here."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import duckdb
import pytest

from equity.matching.rollup import main, markdown, rollup, states

Row = tuple[str, str, str, str, int]


def _state(derived: Path, name: str, summary: dict[str, object], queue: list[Row]) -> None:
    d = derived / name
    d.mkdir(parents=True)
    (d / "summary.json").write_text(json.dumps(summary))
    if queue:
        con = duckdb.connect()
        con.execute(
            "CREATE TABLE q (debtor_party_id VARCHAR, debtor_name VARCHAR, owner_party_id "
            "VARCHAR, category VARCHAR, owners_with_name_in_zip BIGINT)"
        )
        con.executemany("INSERT INTO q VALUES (?, ?, ?, ?, ?)", queue)
        con.execute(f"COPY q TO '{(d / 'review_queue.parquet').as_posix()}' (FORMAT parquet)")


def test_rollup_counts_and_queue(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _state(tmp_path, "ny", {"debtor_parties": 10, "debtors_matched_auto": 4,
                            "debtors_matched_review_only": 2, "open_amount_auto": 1500.0,
                            "review": {"debtors_by_category": {"po_box": 1, "different": 1}}},
           [("d2", "ZED", "o1", "po_box", 1), ("d1", "AMY", "o2", "different", 2)])  # fmt: skip
    _state(tmp_path, "ct", {"debtor_parties": 3, "debtors_matched_auto": 1}, [])
    (tmp_path / "Bad Name").mkdir()
    (tmp_path / "Bad Name" / "summary.json").write_text("{}")
    assert states(tmp_path) == ["ct", "ny"]  # only safe folder names
    rows = rollup(tmp_path)
    assert [r["state"] for r in rows] == ["ct", "ny"]
    ny = rows[1]
    assert (ny["debtors_review_only"], ny["review_po_box"], ny["review_different"],
            ny["review_spelling_only"]) == (2, 1, 1, 0)  # fmt: skip
    assert json.loads((tmp_path / "summary_by_state.json").read_text()) == rows
    everything = (tmp_path / "review_queue_all.parquet").as_posix()
    got = duckdb.connect().execute(f"SELECT state, debtor_party_id FROM '{everything}'").fetchall()
    assert got == [("ny", "d1"), ("ny", "d2")]  # category order: different before po_box
    csv = (tmp_path / "ny" / "review_queue.csv").read_text().splitlines()
    assert csv[0].startswith("debtor_party_id") and len(csv) == 3
    assert not (tmp_path / "ct" / "review_queue.csv").exists()
    table = markdown(rows)
    assert "| ny | 10 | 4 | 2 | 0 | 0 | 1 | 1 | $1,500 |  |" in table
    assert main(["--derived", str(tmp_path)]) == 0
    assert "| ct | 3 | 1 |" in capsys.readouterr().out


def test_rollup_with_no_queues(tmp_path: Path) -> None:
    _state(tmp_path, "co", {"debtor_parties": 1}, [])
    assert rollup(tmp_path)[0]["debtor_parties"] == 1
    assert not (tmp_path / "review_queue_all.parquet").exists()


def test_runs_as_a_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                          capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    _state(tmp_path, "pa", {"debtor_parties": 2}, [])
    monkeypatch.setattr(sys, "argv", ["rollup", "--derived", str(tmp_path)])
    monkeypatch.delitem(sys.modules, "equity.matching.rollup", raising=False)
    with pytest.raises(SystemExit) as done:
        runpy.run_module("equity.matching.rollup", run_name="__main__")
    assert done.value.code == 0
    assert "| pa | 2 |" in capsys.readouterr().out
