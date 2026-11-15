"""Check 11: data invariants hold on fixtures, and each invariant actually fires."""

from __future__ import annotations

import duckdb
import pytest

from equity.quality.gates import invariant_violations


def test_fixture_database_passes(fixture_db, doc_types_cfg) -> None:  # type: ignore[no-untyped-def]
    violations = invariant_violations(fixture_db, doc_types_cfg)
    assert violations == [], "\n".join(map(str, violations))


def _checks(con, cfg) -> set[tuple[str, str]]:  # type: ignore[no-untyped-def]
    return {(v.check, v.table) for v in invariant_violations(con, cfg)}


def test_future_recording_date(scratch_db, doc_types_cfg) -> None:  # type: ignore[no-untyped-def]
    scratch_db.execute(
        "UPDATE instrument SET recorded_on = DATE '2030-01-01' "
        "WHERE instrument_uid = '99001:2022-000110'"
    )
    assert ("future_date", "instrument") in _checks(scratch_db, doc_types_cfg)


def test_lien_without_parcel(scratch_db, doc_types_cfg) -> None:  # type: ignore[no-untyped-def]
    scratch_db.execute("DELETE FROM instrument_parcel WHERE instrument_uid = '99001:2020-000202'")
    assert ("lien_without_parcel", "instrument") in _checks(scratch_db, doc_types_cfg)


def test_general_lien_without_parcel_is_allowed(fixture_db, doc_types_cfg) -> None:  # type: ignore[no-untyped-def]
    # The judgment lien in the fixture has no parcel row; it reaches parcels via the debtor.
    n = fixture_db.execute(
        "SELECT count(*) FROM instrument_parcel WHERE instrument_uid = '99001:2019-000120'"
    ).fetchone()
    assert n == (0,)
    assert ("lien_without_parcel", "instrument") not in _checks(fixture_db, doc_types_cfg)


def test_negative_amounts_blocked_by_schema(scratch_db) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(duckdb.ConstraintException):
        scratch_db.execute(
            "UPDATE instrument SET principal_amount = -1 WHERE instrument_uid = '99001:2020-000202'"
        )


def test_negative_amount_gate(scratch_db, doc_types_cfg) -> None:  # type: ignore[no-untyped-def]
    # Simulate a fact table that lost its CHECK (e.g. rebuilt from Parquet).
    scratch_db.execute("CREATE TABLE tmp AS SELECT * FROM judgment")
    scratch_db.execute("DROP TABLE judgment")
    scratch_db.execute("CREATE TABLE judgment AS SELECT * FROM tmp")
    scratch_db.execute("UPDATE judgment SET principal = -5")
    assert ("negative_amount", "judgment") in _checks(scratch_db, doc_types_cfg)


def _entity(con, link_id: str, signals: str = '{"same_address": true}') -> None:  # type: ignore[no-untyped-def]
    con.execute(
        "INSERT INTO entity_link VALUES (?, 'fx-r-a-1', 'e1', 'name_exact', '1', 100, ?, 'auto', "
        "TIMESTAMPTZ '2026-02-01 00:00:00+00', 'rule', NULL)",
        [link_id, signals],
    )


def test_entity_without_link(scratch_db, doc_types_cfg) -> None:  # type: ignore[no-untyped-def]
    scratch_db.execute(
        "INSERT INTO entity VALUES "
        "('e1', 'person', 'X', 'no-such-link', TIMESTAMPTZ '2026-02-01 00:00:00+00')"
    )
    assert ("entity_without_link", "entity") in _checks(scratch_db, doc_types_cfg)


def test_link_without_evidence(scratch_db, doc_types_cfg) -> None:  # type: ignore[no-untyped-def]
    scratch_db.execute(
        "INSERT INTO entity VALUES "
        "('e1', 'person', 'X', 'l1', TIMESTAMPTZ '2026-02-01 00:00:00+00')"
    )
    _entity(scratch_db, "l1", "{}")
    found = _checks(scratch_db, doc_types_cfg)
    assert ("link_without_evidence", "entity_link") in found
    assert ("entity_without_link", "entity") not in found


def test_dangling_link(scratch_db, doc_types_cfg) -> None:  # type: ignore[no-untyped-def]
    _entity(scratch_db, "l2")
    assert ("dangling_link", "entity_link") in _checks(scratch_db, doc_types_cfg)


def test_dangling_reference(scratch_db, doc_types_cfg) -> None:  # type: ignore[no-untyped-def]
    scratch_db.execute("DELETE FROM party WHERE party_id = 'fx-r-c-1'")
    assert ("dangling_reference", "instrument_party") in _checks(scratch_db, doc_types_cfg)


def test_duplicate_current_rows(scratch_db, doc_types_cfg) -> None:  # type: ignore[no-untyped-def]
    scratch_db.execute("UPDATE parcel_assessment SET superseded_at = NULL")
    assert ("duplicate_current", "parcel_assessment") in _checks(scratch_db, doc_types_cfg)
