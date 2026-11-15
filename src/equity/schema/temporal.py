"""As-of queries: what a parcel looked like on a date, as known at a point in time.

Two clocks:
- `on` (valid time): the date in the world we ask about (recorded / effective dates).
- `known_as_of` (transaction time): what our database had ingested by then. Rows superseded
  before that instant are excluded; rows ingested after it are invisible.

Ordering in these results is only a stable listing order, not lien priority. Priority is a
Phase 4 rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import duckdb

from equity.config import DocTypes


def _known(alias: str) -> str:
    return (
        f"{alias}.ingested_at <= $known AND "
        f"({alias}.superseded_at IS NULL OR {alias}.superseded_at > $known)"
    )


@dataclass(frozen=True)
class OwnerAsOf:
    parcel_uid: str
    party_id: str
    raw_name: str
    owner_seq: int
    valid_from: date
    valid_to: date | None
    row_id: str


def owners_as_of(
    con: duckdb.DuckDBPyConnection, parcel_uid: str, on: date, known_as_of: datetime
) -> list[OwnerAsOf]:
    sql = f"""
        SELECT o.parcel_uid, o.party_id, p.raw_name, o.owner_seq, o.valid_from, o.valid_to,
               o.row_id
        FROM ownership_period o
        JOIN party p ON p.party_id = o.party_id AND {_known("p")}
        WHERE o.parcel_uid = $parcel
          AND o.valid_from <= $on
          AND (o.valid_to IS NULL OR o.valid_to > $on)
          AND {_known("o")}
        ORDER BY o.owner_seq, o.party_id, o.row_id
    """  # noqa: S608 - only fixed aliases are interpolated
    rows = con.execute(sql, {"parcel": parcel_uid, "on": on, "known": known_as_of}).fetchall()
    return [
        OwnerAsOf(str(r[0]), str(r[1]), str(r[2]), int(r[3]), r[4], r[5], str(r[6])) for r in rows
    ]


@dataclass(frozen=True)
class EncumbranceAsOf:
    instrument_uid: str
    doc_type: str
    recorded_on: date
    recorded_seq: int | None
    principal_amount: Decimal | None
    row_id: str


def open_encumbrances_as_of(
    con: duckdb.DuckDBPyConnection,
    parcel_uid: str,
    on: date,
    known_as_of: datetime,
    doc_types: DocTypes,
) -> list[EncumbranceAsOf]:
    """Parcel-linked liens and notices recorded on/before `on` and not terminated by then.

    A terminating reference (e.g. a release) ends exactly the instrument it points to, and only
    if the terminating instrument was itself recorded on/before `on`. A parcel-scoped
    reference (partial release) ends it for its scope parcel only.
    """
    sql = f"""
        SELECT i.instrument_uid, i.doc_type, i.recorded_on, i.recorded_seq,
               i.principal_amount, i.row_id
        FROM instrument i
        JOIN instrument_parcel ip
          ON ip.instrument_uid = i.instrument_uid AND {_known("ip")}
        WHERE ip.parcel_uid = $parcel
          AND i.doc_type IN (SELECT unnest($enc))
          AND i.recorded_on <= $on
          AND {_known("i")}
          AND NOT EXISTS (
              SELECT 1
              FROM instrument_ref r
              JOIN instrument t ON t.instrument_uid = r.from_uid AND {_known("t")}
              WHERE r.to_uid = i.instrument_uid
                AND {_known("r")}
                AND t.recorded_on <= $on
                AND (
                    r.ref_type IN (SELECT unnest($term))
                    OR (r.ref_type IN (SELECT unnest($scoped))
                        AND r.scope_parcel_uid = $parcel)
                )
          )
        ORDER BY i.recorded_on, i.recorded_seq NULLS LAST, i.instrument_uid
    """  # noqa: S608 - only fixed aliases are interpolated
    params = {
        "parcel": parcel_uid,
        "on": on,
        "known": known_as_of,
        "enc": list(doc_types.encumbrances),
        "term": list(doc_types.terminating_refs),
        "scoped": list(doc_types.parcel_scoped_terminating_refs),
    }
    rows = con.execute(sql, params).fetchall()
    return [
        EncumbranceAsOf(
            str(r[0]), str(r[1]), r[2], None if r[3] is None else int(r[3]), r[4], str(r[5])
        )
        for r in rows
    ]


@dataclass(frozen=True)
class AssessmentAsOf:
    parcel_uid: str
    tax_year: int
    appraised_total: Decimal | None
    assessed_value: Decimal | None
    row_id: str


def assessment_as_of(
    con: duckdb.DuckDBPyConnection, parcel_uid: str, on: date, known_as_of: datetime
) -> AssessmentAsOf | None:
    """Latest tax-year assessment in effect on `on`, as known at `known_as_of`."""
    sql = f"""
        SELECT a.parcel_uid, a.tax_year, a.appraised_total, a.assessed_value, a.row_id
        FROM parcel_assessment a
        WHERE a.parcel_uid = $parcel
          AND a.valid_from <= $on
          AND (a.valid_to IS NULL OR a.valid_to > $on)
          AND {_known("a")}
        ORDER BY a.tax_year DESC, a.source_id, a.row_id
        LIMIT 1
    """  # noqa: S608 - only fixed aliases are interpolated
    row = con.execute(sql, {"parcel": parcel_uid, "on": on, "known": known_as_of}).fetchone()
    if row is None:
        return None
    return AssessmentAsOf(str(row[0]), int(row[1]), row[2], row[3], str(row[4]))


@dataclass(frozen=True)
class SnapshotOwner:
    parcel_uid: str
    owner_seq: int
    party_id: str
    raw_name: str
    source_id: str
    observed_on: date
    row_id: str


def snapshot_owners(
    con: duckdb.DuckDBPyConnection, parcel_uid: str, known_as_of: datetime
) -> list[SnapshotOwner]:
    """Owners listed by snapshot sources, as our database knew them at `known_as_of`."""
    sql = f"""
        SELECT s.parcel_uid, s.owner_seq, s.party_id, p.raw_name, s.source_id, s.observed_on,
               s.row_id
        FROM owner_snapshot s
        JOIN party p ON p.party_id = s.party_id AND {_known("p")}
        WHERE s.parcel_uid = $parcel AND {_known("s")}
        ORDER BY s.source_id, s.owner_seq, s.row_id
    """  # noqa: S608 - only fixed aliases are interpolated
    rows = con.execute(sql, {"parcel": parcel_uid, "known": known_as_of}).fetchall()
    return [
        SnapshotOwner(str(r[0]), int(r[1]), str(r[2]), str(r[3]), str(r[4]), r[5], str(r[6]))
        for r in rows
    ]
