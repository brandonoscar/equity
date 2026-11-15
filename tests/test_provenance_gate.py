"""Check 9: the build fails if any fact row lacks source, record key or retrieval time."""

from __future__ import annotations

from equity.quality.gates import Violation, provenance_violations


def test_fixture_database_passes(fixture_db) -> None:  # type: ignore[no-untyped-def]
    violations = provenance_violations(fixture_db)
    assert violations == [], "\n".join(map(str, violations))


def test_gate_catches_null_and_empty_provenance(scratch_db) -> None:  # type: ignore[no-untyped-def]
    # Constraints already block this in real tables; the gate must still catch it in any table
    # that lacks them (e.g. a Parquet-backed view in later phases).
    scratch_db.execute("CREATE TABLE loose AS SELECT * FROM party")
    scratch_db.execute("UPDATE loose SET record_key = '' WHERE party_id = 'fx-r-a-1'")
    scratch_db.execute("UPDATE loose SET retrieved_at = NULL WHERE party_id = 'fx-r-a-2'")
    found = {(v.table, v.detail) for v in provenance_violations(scratch_db, ["loose"])}
    assert ("loose", "have null/empty record_key") in found
    assert ("loose", "have null/empty retrieved_at") in found


def test_gate_catches_orphans_and_mismatches(scratch_db) -> None:  # type: ignore[no-untyped-def]
    scratch_db.execute("DELETE FROM source_record WHERE source_record_id LIKE 'sr-f-court%'")
    scratch_db.execute("DELETE FROM fetch_log WHERE fetch_id = 'f-assessor-2026-03'")
    scratch_db.execute("DELETE FROM source WHERE source_id = 'fixture.recorder'")
    found = {(v.table, v.detail) for v in provenance_violations(scratch_db)}
    assert ("court_case", "point at a missing source_record") in found
    assert ("source_record", "point at a missing fetch") in found
    assert ("fetch_log", "point at a missing source") in found


def test_gate_catches_source_mismatch_and_time_travel(scratch_db) -> None:  # type: ignore[no-untyped-def]
    scratch_db.execute("CREATE TABLE loose AS SELECT * FROM judgment")
    scratch_db.execute("UPDATE loose SET source_id = 'fixture.recorder'")
    scratch_db.execute("UPDATE loose SET retrieved_at = ingested_at + INTERVAL 1 DAY")
    details = {v.detail for v in provenance_violations(scratch_db, ["loose"])}
    assert "disagree with their source_record on source_id" in details
    assert "were ingested before they were retrieved" in details


def test_gate_reports_missing_table(empty_db) -> None:  # type: ignore[no-untyped-def]
    assert provenance_violations(empty_db, ["not_a_table"]) == [
        Violation("provenance", "not_a_table", 1, "table is missing")
    ]
    assert str(Violation("provenance", "t", 2, "x")) == "[provenance] t: 2 row(s) x"
