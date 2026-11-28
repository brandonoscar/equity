"""Recurring refreshes: rules, due, start/finish, polled feeds and the sale-listing history."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import duckdb
import pytest

from equity import lake, refresh
from equity.adapters.registry import REGISTRY

NOW = datetime(2026, 11, 23, 12, tzinfo=UTC)


def _rule(mode: str = "rebuild", hours: float = 24, table: str | None = None) -> refresh.Rule:
    return refresh.Rule(("*",), (), timedelta(hours=hours), mode, table)


def _built(src: Path, refreshed: datetime | None = None) -> None:
    (src / "_parts").mkdir(parents=True, exist_ok=True)
    (src / "_counts.json").write_text('{"instrument": 1}')
    (src / "_plan.json").write_text("[{}]")
    if refreshed:
        (src / refresh.REFRESHED).write_text(json.dumps({"at": refreshed.isoformat()}))


def test_config_rules_cover_the_intended_sources() -> None:
    rules = refresh.rules()
    mode = {s: (r.mode if (r := refresh.rule_for(s, rules)) else None) for s in (
        "us.flmb.rss", "pa.washington.sheriff_sales", "wv.statewide.delinquent",
        "ny.dtf.tax_warrants", "il.chicago.doah_judgments", "wv.statewide.parcels",
        "ny.nyc.acris.real", "pa.dos.business", "us.fjc.idb.civil_judgments")}  # fmt: skip
    assert mode == {"us.flmb.rss": "append", "pa.washington.sheriff_sales": "listing",
                    "wv.statewide.delinquent": "listing", "ny.dtf.tax_warrants": "rebuild",
                    "il.chicago.doah_judgments": "rebuild", "wv.statewide.parcels": None,
                    "ny.nyc.acris.real": None, "pa.dos.business": None,
                    "us.fjc.idb.civil_judgments": None}  # fmt: skip


def test_append_rules_name_polled_feeds_only() -> None:
    """An append rule keeps every poll, so its adapter must drop rows already stored
    (append_polls): the court RSS feeds and Oregon's rolling month of UCC filings."""
    rules = refresh.rules()
    appended = [c for c in REGISTRY
                if (r := refresh.rule_for(c.source_id, rules)) and r.mode == "append"]  # fmt: skip
    assert [c.source_id for c in appended if not getattr(c, "append_polls", False)] == []
    assert "or.sos.ucc" in {c.source_id for c in appended}


# Debtor sources a match run reads that are loaded once on purpose: recorder indexes (big,
# refreshed by hand) and closed lists of past years that no longer change.
LOADED_ONCE = ("fl.hernando.or", "fl.hillsborough.or", "fl.putnam.or", "ny.nyc.acris.real",
               "mi.kalamazoo.foreclosed_*", "mi.kalamazoo.forfeited_20*")  # fmt: skip


def test_every_match_run_debtor_is_refreshed_or_loaded_once_on_purpose() -> None:
    """The weekly sync: a debt list wired into a match run is fetched again on a schedule, so
    a new source cannot sit at its first download unnoticed."""
    import fnmatch

    from equity.matching.resolve import STATES

    rules = refresh.rules()
    debtors = sorted({s for spec in STATES.values() for s in spec.get("debtors") or []})
    stale = [s for s in debtors if refresh.rule_for(s, rules) is None
             and not any(fnmatch.fnmatch(s, p) for p in LOADED_ONCE)]  # fmt: skip
    assert stale == []


def test_the_hosted_loader_builds_every_match_run_source() -> None:
    """A source wired into a match run gets its first build from the lake workflow without
    being listed by hand (court RSS feeds are polled by the refresh workflow instead)."""
    from equity import lake
    from equity.matching.resolve import STATES, state_sources

    ids = {c.source_id for c in REGISTRY}
    built = set(lake.parcel_sources())
    wanted = {s for state in STATES for s in state_sources(state)
              if s in ids and not s.endswith(".rss")}  # fmt: skip
    assert sorted(wanted - built) == []
    assert {"tx.dallas.tax_roll_delinquent", "tn.hamilton.delinquent_taxes"} <= built


def test_every_source_named_in_refresh_yaml_is_registered() -> None:
    ids = {c.source_id for c in REGISTRY}
    named = {p for r in refresh.rules() for p in r.match if not any(ch in p for ch in "*?[")}
    assert named <= ids


@pytest.mark.parametrize(
    ("rule", "problem"),
    [({"match": ["a"], "every_hours": 1, "mode": "sometimes"}, "mode must be"),
     ({"match": ["a"], "every_hours": 1, "mode": "listing"}, "listing_table"),
     ({"match": ["a"], "every_hours": 0}, "positive")],
)  # fmt: skip
def test_bad_rules_are_refused(tmp_path: Path, rule: dict[str, object], problem: str) -> None:
    (tmp_path / "refresh.yaml").write_text(json.dumps({"rules": [rule]}))
    with pytest.raises(ValueError, match=problem):
        refresh.rules(tmp_path)


def test_due_orders_never_refreshed_then_oldest(tmp_path: Path) -> None:
    rules = [refresh.Rule(("*.rss",), (), timedelta(hours=2), "append"), _rule(hours=24)]
    _built(tmp_path / "a.list", NOW - timedelta(hours=30))
    _built(tmp_path / "b.list", NOW - timedelta(hours=1))  # refreshed recently: not due
    _built(tmp_path / "c.list")  # built, never refreshed: due first
    (tmp_path / "d.list" / "_parts").mkdir(parents=True)  # still loading: left to lake run
    _built(tmp_path / "e.list", NOW - timedelta(hours=50))
    ids = ["a.list", "b.list", "c.list", "d.list", "e.list", "x.rss"]  # x.rss: never polled
    assert refresh.due(tmp_path, NOW, rules, ids) == ["c.list", "x.rss", "e.list", "a.list"]


def test_shared_extra_keeps_a_subset_filter_only() -> None:
    old = [{"year": "2024", "codes": "JUDG"}, {"year": "2025", "codes": "JUDG"}]
    fresh = [{"year": "2024"}, {"year": "2025"}, {"year": "2026"}]
    assert refresh.shared_extra(old, fresh) == {"codes": "JUDG"}
    assert refresh.shared_extra([{"year": "1", "w": "a"}, {"year": "2", "w": "b"}], fresh) == {}
    assert refresh.shared_extra([], fresh) == {}


def test_start_rebuild_replans_and_clears_parts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from .test_ingest import Planned

    monkeypatch.setattr("equity.adapters.registry.by_source_id", lambda sid: Planned)
    src = tmp_path / "test.tiny"
    assert refresh.start("test.tiny", tmp_path, NOW, _rule()) == "not built yet"
    _built(src)
    (src / "_plan.json").write_text('[{"ids": "1"}]')
    (src / "_parts" / "00000.json").write_text("{}")
    (src / "instrument").mkdir()
    (src / "instrument" / "00000.parquet").write_bytes(b"x")
    (src / "_snapshots").mkdir()
    (src / "_offloaded").write_text("x")
    assert refresh.start("test.tiny", tmp_path, NOW, _rule()) == "re-planned 2 partitions"
    assert json.loads((src / "_plan.json").read_text()) == [{"ids": "1"}, {"ids": "2,3"}]
    assert not (src / "instrument").exists() and not list((src / "_parts").iterdir())
    assert not (src / "_counts.json").exists() and not (src / "_offloaded").exists()
    assert (src / "_snapshots").is_dir()  # history is kept


def test_start_rebuild_keeps_a_doc_code_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from .test_ingest import Planned

    monkeypatch.setattr("equity.adapters.registry.by_source_id", lambda sid: Planned)
    src = tmp_path / "test.tiny"
    _built(src)
    (src / "_plan.json").write_text('[{"ids": "1", "codes": "J"}, {"ids": "2,3", "codes": "J"}]')
    refresh.start("test.tiny", tmp_path, NOW, _rule())
    assert json.loads((src / "_plan.json").read_text()) == [
        {"ids": "1", "codes": "J"}, {"ids": "2,3", "codes": "J"}]  # fmt: skip


def test_polled_feed_keeps_parts_and_drops_rows_already_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from .test_ingest import Tiny

    class Polled(Tiny):
        append_polls: ClassVar[bool] = True

    monkeypatch.setattr(lake, "LAKE", tmp_path)
    monkeypatch.setattr(lake, "WORK", tmp_path / "work")
    monkeypatch.setattr("equity.adapters.registry.by_source_id", lambda sid: Polled)
    rule = _rule("append", hours=2)
    assert refresh.start("test.tiny", tmp_path, NOW, rule) == "first poll"
    assert lake.build("test.tiny", raw_dir=tmp_path / "raw")["parcel"] == 2  # ids 1, 2
    refresh.finish("test.tiny", tmp_path, NOW, rule)
    assert refresh.start("test.tiny", tmp_path, NOW, rule) == "poll 1 added"
    src = tmp_path / "test.tiny"
    plan = json.loads((src / "_plan.json").read_text())
    plan[1]["ids"] = "1,2,3"  # the next poll sees one new item and the two already stored
    (src / "_plan.json").write_text(json.dumps(plan))
    assert refresh.start("test.tiny", tmp_path, NOW, rule) == "poll pending"
    lake.build("test.tiny", raw_dir=tmp_path / "raw")
    new = duckdb.sql(f"SELECT parcel_uid FROM '{src}/parcel/00001.parquet'").fetchall()
    assert new == [("99001-3",)]
    recs = duckdb.sql(f"SELECT count(*) FROM '{src}/source_record/00001.parquet'").fetchall()
    assert recs == [(1,)]
    assert json.loads((src / "_counts.json").read_text())["parcel"] == 3


def test_polled_feed_refuses_to_poll_without_its_stored_parts(tmp_path: Path) -> None:
    src = tmp_path / "us.x.rss"
    _built(src)
    (src / "_parts" / "00000.json").write_text("{}")
    with pytest.raises(RuntimeError, match="pull them first"):
        refresh.start("us.x.rss", tmp_path, NOW, _rule("append"))


def _listing_day(src: Path, rows: list[tuple[str, float]]) -> None:
    """Replace the source's built instrument table with these (uid, amount) rows."""
    for t in ("instrument", "instrument_parcel"):
        (src / t).mkdir(parents=True, exist_ok=True)
    values = ", ".join(f"('{u}', {a})" for u, a in rows)
    duckdb.sql(
        "COPY (SELECT 'zz.sale' AS source_id, u AS instrument_uid, DATE '2026-12-01' AS "
        "recorded_on, CAST(a AS DECIMAL(14,2)) AS principal_amount, 'Sheriff sale' AS "
        f"doc_type_raw, NULL::TIMESTAMPTZ AS superseded_at FROM (VALUES {values}) v(u, a)) "
        f"TO '{src}/instrument/00000.parquet' (FORMAT PARQUET)"
    )
    duckdb.sql(
        f"COPY (SELECT u AS instrument_uid, 'P-' || u AS parcel_uid FROM (VALUES {values}) "
        f"v(u, a)) TO '{src}/instrument_parcel/00000.parquet' (FORMAT PARQUET)"
    )


def test_listing_snapshots_build_a_day_to_day_history(tmp_path: Path) -> None:
    rule = refresh.Rule(("zz.sale",), (), timedelta(hours=24), "listing", "instrument")
    src = tmp_path / "zz.sale"
    _built(src)
    assert refresh.finish("zz.none", tmp_path, NOW, rule) is None  # not built: nothing to do
    _listing_day(src, [("a", 100), ("b", 200)])
    day1 = refresh.finish("zz.sale", tmp_path, NOW - timedelta(days=1), rule)
    assert day1 is not None and day1["mode"] == "listing"
    _listing_day(src, [("b", 250), ("c", 300)])  # a dropped, b changed amount, c is new
    refresh.finish("zz.sale", tmp_path, NOW, rule)
    assert (src / "_snapshots" / "2026-11-22.json").exists()
    assert (src / "_snapshots" / "2026-11-23" / "instrument.parquet").exists()
    assert refresh.last_refresh(src) == NOW
    out = tmp_path / "derived"
    summary = refresh.listings(tmp_path, [rule], out)
    assert summary["snapshots"] == 4
    assert summary["sources"]["zz.sale"] == {"latest": "2026-11-23", "listed": 2,
                                             "appeared": 1, "dropped": 1}  # fmt: skip
    hist = {r[0]: r[1:] for r in duckdb.sql(
        f"SELECT listing_key, parcel_uid, first_seen::VARCHAR, days_seen, on_latest, "
        f"latest_amount::DOUBLE, changes FROM '{out}/sale_listing_history.parquet'"
    ).fetchall()}  # fmt: skip
    assert hist["a"] == ("P-a", "2026-11-22", 1, False, 100.0, 0)
    assert hist["b"] == ("P-b", "2026-11-22", 2, True, 250.0, 1)
    assert hist["c"] == ("P-c", "2026-11-23", 1, True, 300.0, 0)


def test_listing_without_parcel_links_still_snapshots(tmp_path: Path) -> None:
    rule = refresh.Rule(("zz.sale",), (), timedelta(hours=24), "listing", "instrument")
    src = tmp_path / "zz.sale"
    _built(src)
    _listing_day(src, [("a", 1)])
    for f in (src / "instrument_parcel").iterdir():
        f.unlink()
    refresh.finish("zz.sale", tmp_path, NOW, rule)
    hist = duckdb.sql(f"SELECT listing_key, parcel_uid FROM "
                      f"'{tmp_path}/d/sale_listing_history.parquet'") if refresh.listings(
        tmp_path, [rule], tmp_path / "d")["snapshots"] else None  # fmt: skip
    assert hist is not None and hist.fetchall() == [("a", None)]


def test_tax_delinquency_listings_key_on_parcel_and_certificate(tmp_path: Path) -> None:
    rule = refresh.Rule(("zz.wv",), (), timedelta(hours=24), "listing",
                        "tax_delinquency_snapshot")  # fmt: skip
    src = tmp_path / "zz.wv"
    _built(src)
    (src / "tax_delinquency_snapshot").mkdir()
    duckdb.sql(
        "COPY (SELECT 'zz.wv' AS source_id, 'P1' AS parcel_uid, 'C9' AS certificate_no, "
        "'Certified' AS status_raw, DATE '2026-11-20' AS observed_on, "
        "NULL::TIMESTAMPTZ AS superseded_at) "
        f"TO '{src}/tax_delinquency_snapshot/00000.parquet' (FORMAT PARQUET)"
    )
    refresh.finish("zz.wv", tmp_path, NOW, rule)
    assert refresh.listings(tmp_path, [rule], tmp_path / "d")["sources"]["zz.wv"]["listed"] == 1
    key = duckdb.sql(f"SELECT listing_key FROM '{tmp_path}/d/sale_listing_snapshot.parquet'")
    assert key.fetchall() == [("P1|C9",)]


def test_listings_with_no_snapshots(tmp_path: Path) -> None:
    (tmp_path / "zz.other" / "_snapshots").mkdir(parents=True)
    assert refresh.listings(tmp_path, [_rule()], tmp_path / "d") == {"snapshots": 0}


def test_main_due_start_finish_listings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from .test_ingest import Planned

    monkeypatch.setattr("equity.adapters.registry.by_source_id", lambda sid: Planned)
    _built(tmp_path / "ny.dtf.tax_warrants")
    args = ["--lake", str(tmp_path), "--now", "2026-11-23T12:00:00"]
    assert refresh.main([*args, "due", "--mode", "rebuild", "--limit", "5"]) == 0
    assert capsys.readouterr().out.strip() == "ny.dtf.tax_warrants"
    assert refresh.main([*args, "due", "--mode", "append"]) == 0
    assert "ny.dtf" not in capsys.readouterr().out
    refresh.main([*args, "start", "ny.dtf.tax_warrants", "wv.statewide.parcels"])
    out = capsys.readouterr()
    assert "re-planned 2 partitions" in out.out and "no refresh rule" in out.err
    refresh.main([*args, "finish", "ny.dtf.tax_warrants"])
    assert "build not finished" in capsys.readouterr().out
    assert refresh.main([*args, "listings", "--out", str(tmp_path / "d")]) == 0
    assert '"snapshots": 0' in capsys.readouterr().out


def test_finish_records_the_counts_it_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from .test_ingest import Planned

    monkeypatch.setattr("equity.adapters.registry.by_source_id", lambda sid: Planned)
    src = tmp_path / "test.tiny"
    _built(src, NOW - timedelta(days=8))
    refresh.start("test.tiny", tmp_path, NOW, _rule())
    (src / "_counts.json").write_text('{"instrument": 3}')  # the rebuild finished
    rec = refresh.finish("test.tiny", tmp_path, NOW, _rule())
    assert rec is not None
    assert rec["previous"] == {"at": (NOW - timedelta(days=8)).isoformat(),
                               "counts": {"instrument": 1}}  # fmt: skip
    assert not (src / refresh.BEFORE).exists()
    again = refresh.finish("test.tiny", tmp_path, NOW + timedelta(days=7), _rule())
    assert again is not None and again["previous"]["counts"] == {"instrument": 3}
