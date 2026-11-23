"""Health history: day-to-day row counts and fields, alerts on drops and changes. Offline."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from equity import health_history as hh

NOW = datetime(2026, 11, 23, 9, tzinfo=UTC)


def _r(sid: str, ok: bool = True, rows: int | None = 1000, fields: tuple[str, ...] = ("a", "b"),
       detail: str = "ok") -> dict[str, object]:  # fmt: skip
    return {"source_id": sid, "ok": ok, "rows": rows, "fields": list(fields), "detail": detail}


def test_first_day_records_history_without_alerts(tmp_path: Path) -> None:
    out = hh.check([_r("s1")], tmp_path / "h", tmp_path / "lake", NOW)
    assert out["alerts"] == [] and out["compared_with"] is None
    saved = json.loads((tmp_path / "h" / "2026-11-23.json").read_text())
    assert saved["sources"]["s1"] == {"ok": True, "detail": "ok", "rows": 1000,
                                      "fields": ["a", "b"]}  # fmt: skip


def test_alerts_against_the_previous_day(tmp_path: Path) -> None:
    hist = tmp_path / "h"
    yesterday = [_r("drop"), _r("small", rows=40), _r("down"), _r("fields"), _r("fine"),
                 _r("nocount", rows=None)]  # fmt: skip
    hh.check(yesterday, hist, tmp_path / "lake", NOW - timedelta(days=1))
    today = [_r("drop", rows=899), _r("small", rows=1), _r("down", ok=False, detail="HTTP 503"),
             _r("fields", fields=("a", "c")), _r("fine", rows=950), _r("nocount", rows=None),
             _r("new")]  # fmt: skip
    out = hh.check(today, hist, tmp_path / "lake", NOW)
    assert out["compared_with"] == "2026-11-22"
    assert [(a["source_id"], a["alert"]) for a in out["alerts"]] == [
        ("down", "went_down"),
        ("drop", "row_drop"),
        ("fields", "fields_changed"),
    ]
    fields = next(a for a in out["alerts"] if a["alert"] == "fields_changed")
    assert fields["detail"] == "added ['c'], removed ['b']"


def test_a_recent_refresh_that_lost_rows_is_flagged(tmp_path: Path) -> None:
    lake = tmp_path / "lake"

    def refreshed(sid: str, at: datetime, before: dict[str, int], after: dict[str, int]) -> None:
        (lake / sid).mkdir(parents=True)
        rec = {"at": at.isoformat(), "counts": after, "previous": {"counts": before}}
        (lake / sid / "_refreshed.json").write_text(json.dumps(rec))

    refreshed("a.list", NOW - timedelta(hours=3), {"instrument": 500, "party": 20},
              {"instrument": 400, "party": 1})  # fmt: skip
    refreshed("b.list", NOW - timedelta(days=3), {"instrument": 500}, {"instrument": 1})  # old
    refreshed("c.list", NOW - timedelta(hours=1), {"instrument": 500}, {"instrument": 460})
    (lake / "d.list").mkdir()
    (lake / "d.list" / "_refreshed.json").write_text(
        json.dumps({"at": NOW.isoformat(), "counts": {"instrument": 1}})
    )  # first refresh: nothing before
    assert hh.refresh_alerts(lake, NOW) == [
        {"source_id": "a.list", "alert": "refresh_drop", "detail": "instrument: 500 -> 400 rows"}
    ]


def test_main_exits_nonzero_on_alerts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    health = tmp_path / "health.json"
    args = ["--health", str(health), "--history", str(tmp_path / "h"),
            "--lake", str(tmp_path / "lake")]  # fmt: skip
    health.write_text(json.dumps({"results": [_r("s")]}))
    assert hh.main([*args, "--now", "2026-11-22T09:00:00"]) == 0
    health.write_text(json.dumps({"results": [_r("s", rows=10)]}))
    assert hh.main([*args, "--now", "2026-11-23T09:00:00+00:00"]) == 1
    assert '"row_drop"' in capsys.readouterr().out
