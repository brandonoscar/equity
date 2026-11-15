"""Loader: idempotent, append-only, supersedes on change, rejects bad input loudly."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from equity.schema.clock import fixed_clock
from equity.schema.load import LoadError, LoadStats, canonical, load_rows

T1 = fixed_clock(datetime(2026, 2, 1, tzinfo=UTC))
T2 = fixed_clock(datetime(2026, 3, 1, tzinfo=UTC))
SHA = "a" * 64


def _prov(key: str = "01-01-0009", retrieved: str = "2026-01-10T00:00:00+00:00") -> dict[str, Any]:
    return {
        "source_record_id": "sr-x",
        "source_id": "fixture.assessor",
        "jurisdiction": "99001",
        "record_key": key,
        "source_uri": "file://x#1",
        "retrieved_at": retrieved,
        "content_sha256": SHA,
    }


def _assessment(total: str, retrieved: str = "2026-01-10T00:00:00+00:00") -> dict[str, Any]:
    return {
        "parcel_uid": "99001-01-01-0009",
        "tax_year": 2025,
        "appraised_total": total,
        "valid_from": "2025-07-01",
        **_prov(retrieved=retrieved),
    }


def test_reload_identical_content_is_noop(empty_db) -> None:  # type: ignore[no-untyped-def]
    load_rows(empty_db, "parcel_assessment", [_assessment("100.00")], T1)
    stats = load_rows(empty_db, "parcel_assessment", [_assessment("100")], T2)
    assert (stats.inserted, stats.unchanged, stats.superseded) == (0, 1, 0)


def test_refetch_with_same_facts_but_new_retrieval_is_noop(empty_db) -> None:  # type: ignore[no-untyped-def]
    load_rows(empty_db, "parcel_assessment", [_assessment("100.00")], T1)
    later = _assessment("100.00", retrieved="2026-02-20T00:00:00+00:00")
    stats = load_rows(empty_db, "parcel_assessment", [later], T2)
    assert stats.unchanged == 1


def test_changed_content_supersedes_not_overwrites(empty_db) -> None:  # type: ignore[no-untyped-def]
    load_rows(empty_db, "parcel_assessment", [_assessment("100.00")], T1)
    stats = load_rows(
        empty_db, "parcel_assessment", [_assessment("120.00", "2026-02-20T00:00:00+00:00")], T2
    )
    assert (stats.inserted, stats.superseded) == (1, 1)
    rows = empty_db.execute(
        "SELECT appraised_total, superseded_at FROM parcel_assessment ORDER BY ingested_at"
    ).fetchall()
    assert [str(r[0]) for r in rows] == ["100.00", "120.00"]
    assert rows[0][1] == datetime(2026, 3, 1, tzinfo=UTC)
    assert rows[1][1] is None


def test_value_that_reverts_gets_a_new_row(empty_db) -> None:  # type: ignore[no-untyped-def]
    load_rows(empty_db, "parcel_assessment", [_assessment("100.00")], T1)
    load_rows(
        empty_db, "parcel_assessment", [_assessment("120.00", "2026-02-01T00:00:00+00:00")], T1
    )
    load_rows(
        empty_db, "parcel_assessment", [_assessment("100.00", "2026-02-20T00:00:00+00:00")], T2
    )
    n = empty_db.execute("SELECT count(*), count(superseded_at) FROM parcel_assessment").fetchone()
    assert n == (3, 2)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"row_id": "x"}, "loader-owned"),
        ({"ingested_at": "2026-01-01T00:00:00+00:00"}, "loader-owned"),
        ({"source_uri": ""}, "missing provenance"),
        ({"retrieved_at": None}, "missing provenance"),
        ({"appraised_total": 100.5}, "not a float"),
        ({"retrieved_at": "2026-01-10T00:00:00"}, "timezone"),
        ({"bogus": 1}, "unknown columns"),
    ],
)
def test_bad_rows_are_rejected(empty_db, change: dict[str, Any], message: str) -> None:  # type: ignore[no-untyped-def]
    row = {**_assessment("1.00"), **change}
    with pytest.raises(LoadError, match=message):
        load_rows(empty_db, "parcel_assessment", [row], T1)


def test_missing_domain_key_is_rejected(empty_db) -> None:  # type: ignore[no-untyped-def]
    row = _assessment("1.00")
    del row["tax_year"]
    with pytest.raises(LoadError, match="domain-key"):
        load_rows(empty_db, "parcel_assessment", [row], T1)


def test_unknown_table(empty_db) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(LoadError, match="unknown table"):
        load_rows(empty_db, "nope", [{}], T1)


def _source(summary: str = "x") -> dict[str, Any]:
    return {
        "source_id": "s1", "kind": "fixture", "jurisdiction": "99001", "access_method": "fixture",
        "base_url": "file://x", "terms_summary": summary, "cost_model": "free",
    }  # fmt: skip


def test_provenance_rows_are_insert_once(empty_db) -> None:  # type: ignore[no-untyped-def]
    stats = LoadStats()
    load_rows(empty_db, "source", [_source()], T1, stats)
    load_rows(empty_db, "source", [_source()], T1, stats)
    assert (stats.inserted, stats.unchanged) == (1, 1)
    with pytest.raises(LoadError, match="different content"):
        load_rows(empty_db, "source", [_source("changed")], T1)
    with pytest.raises(LoadError, match="primary key"):
        load_rows(empty_db, "source", [{**_source(), "source_id": ""}], T1)


def test_typed_columns_convert(empty_db) -> None:  # type: ignore[no-untyped-def]
    geometry = {
        "parcel_uid": "99001-01-01-0009", "geom_wkb": "0101000000000000000000f03f000000000000f03f",
        "srid": 4326, "xmin": 1, "ymin": 1, "xmax": 1, "ymax": 1, "acres": "0.5",
        "valid_from": "2025-01-01", **_prov(),
    }  # fmt: skip
    load_rows(empty_db, "parcel_geometry", [geometry], T1)
    blob = empty_db.execute("SELECT geom_wkb, acres FROM parcel_geometry").fetchone()
    assert blob is not None and bytes(blob[0])[:1] == b"\x01" and blob[1] == 0.5
    owner = {
        "parcel_uid": "99001-01-01-0009", "party_id": "p", "owner_seq": 1, "survivorship": True,
        "valid_from": "2020-01-01", **_prov(),
    }  # fmt: skip
    load_rows(empty_db, "ownership_period", [owner], T1)
    with pytest.raises(LoadError, match="boolean"):
        load_rows(empty_db, "ownership_period", [{**owner, "survivorship": "yes"}], T1)


def test_canonical_forms() -> None:
    from datetime import date
    from decimal import Decimal

    assert canonical(None) == "\x00null"
    assert canonical(True) == "true"
    assert canonical(Decimal("120000.00")) == canonical(Decimal("120000")) == "120000"
    assert canonical(date(2020, 1, 2)) == "2020-01-02"
    assert canonical(b"\x01") == "01"
    assert canonical(0.5) == "0.5"


def test_same_content_under_different_keys_gets_distinct_rows(empty_db) -> None:  # type: ignore[no-untyped-def]
    issue = {"issue_code": "x", "target_table": "t", "detail": {"a": 1}}
    load_rows(empty_db, "data_issue", [{**issue, **_prov("K1")}, {**issue, **_prov("K2")}], T1)
    n = empty_db.execute("SELECT count(DISTINCT row_id) FROM data_issue").fetchone()
    assert n == (2,)
