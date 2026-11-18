"""Re-fetching an unchanged snapshot source adds provenance but no new facts; a change
supersedes exactly the changed row."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from equity.adapters.base import Fetched
from equity.adapters.rows import fetch_log_row
from equity.adapters.wv.statewide_parcels import WVStatewideParcels
from equity.quality.gates import provenance_violations
from equity.schema.clock import fixed_clock
from equity.schema.load import LoadStats, load_rows
from equity.schema.temporal import snapshot_owners

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures/adapters/wv.statewide.parcels/county_number-31_limit-25.json"
)
UID = "54061-140024000400010000"


def _load(con, content: bytes, at: datetime) -> LoadStats:  # type: ignore[no-untyped-def]
    adapter = WVStatewideParcels()
    fetched = Fetched(adapter.source_id, "fixture://wv", at, 200, content, "application/json")
    clock = fixed_clock(at)
    stats = LoadStats()
    load_rows(con, "source", [dict(adapter.source_row())], clock, stats)
    row = fetch_log_row(fetched, "WVStatewideParcels", "1", "fixture")
    load_rows(con, "fetch_log", [dict(row.row)], clock, stats)
    for r in adapter.normalize(fetched):
        load_rows(con, r.table, [dict(r.row)], clock, stats)
    return stats


def test_unchanged_refetch_adds_no_facts(empty_db) -> None:  # type: ignore[no-untyped-def]
    content = FIXTURE.read_bytes()
    first = _load(empty_db, content, datetime(2026, 11, 15, tzinfo=UTC))
    second = _load(empty_db, content, datetime(2026, 12, 15, tzinfo=UTC))
    assert second.superseded == 0
    assert second.inserted == second.by_table["source_record"] + 1  # + the new fetch_log row
    assert first.inserted > second.inserted
    (owner,) = [o for o in snapshot_owners(empty_db, UID, datetime(2027, 1, 1, tzinfo=UTC))]
    assert owner.observed_on.isoformat() == "2026-11-15"  # first observation is kept
    assert provenance_violations(empty_db) == []


def test_owner_change_supersedes_only_that_slot(empty_db) -> None:  # type: ignore[no-untyped-def]
    content = FIXTURE.read_bytes()
    _load(empty_db, content, datetime(2026, 11, 15, tzinfo=UTC))
    data = json.loads(content)
    for a in data["attributes"]:
        if a["CleanParcelID"] == "31140024000400010000":
            a["Owner1"] = "TESTOWNER NEWBUYER LLC"
    stats = _load(empty_db, json.dumps(data).encode(), datetime(2026, 12, 15, tzinfo=UTC))
    assert stats.superseded == 1
    before = snapshot_owners(empty_db, UID, datetime(2026, 12, 1, tzinfo=UTC))
    after = snapshot_owners(empty_db, UID, datetime(2026, 12, 16, tzinfo=UTC))
    assert [o.raw_name for o in before] != [o.raw_name for o in after]
    assert after[0].raw_name == "TESTOWNER NEWBUYER LLC"
    assert after[0].observed_on.isoformat() == "2026-12-15"
