"""Check 10: as-of queries return the right owner, encumbrances and values on known dates."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from equity.schema.temporal import assessment_as_of, open_encumbrances_as_of, owners_as_of

P1, P2 = "99001-01-01-0001", "99001-01-01-0002"
NOW = datetime(2026, 6, 1, tzinfo=UTC)
ALPHA, BRAVO = "TESTPERSON ALPHA Q", "BRAVO TESTHOLDINGS LLC"


@pytest.mark.parametrize(
    ("parcel", "on", "expected"),
    [
        (P1, date(2010, 2, 28), []),
        (P1, date(2010, 3, 1), [ALPHA]),
        (P1, date(2021, 6, 14), [ALPHA]),
        (P1, date(2021, 6, 15), [BRAVO]),  # valid_to is exclusive
        (P1, date(2026, 1, 1), [BRAVO]),
        (P2, date(2012, 9, 8), []),
        (P2, date(2026, 1, 1), [ALPHA]),
    ],
)
def test_owner_as_of(fixture_db, parcel: str, on: date, expected: list[str]) -> None:  # type: ignore[no-untyped-def]
    assert [o.raw_name for o in owners_as_of(fixture_db, parcel, on, NOW)] == expected


DOT1, DOT2, DOT3 = "99001:2010-000102", "99001:2015-000502", "99001:2013-000300"
MECH, LISP = "99001:2020-000202", "99001:2022-000110"


@pytest.mark.parametrize(
    ("parcel", "on", "expected"),
    [
        (P1, date(2010, 2, 28), []),
        (P1, date(2010, 3, 1), [DOT1]),
        (P1, date(2013, 4, 1), [DOT1, DOT3]),
        (P1, date(2015, 5, 4), [DOT1, DOT3]),
        (P1, date(2015, 5, 5), [DOT3, DOT2]),  # release of DOT1 recorded same day as DOT2
        (P1, date(2018, 8, 8), [DOT2]),  # partial release frees P1 from blanket DOT3
        (P1, date(2020, 2, 2), [DOT2, MECH]),
        (P1, date(2022, 1, 10), [DOT2, MECH, LISP]),
        (P2, date(2013, 4, 1), [DOT3]),
        (P2, date(2019, 1, 1), [DOT3]),  # partial release was scoped to P1 only
    ],
)
def test_open_encumbrances_as_of(fixture_db, doc_types_cfg, parcel, on, expected) -> None:  # type: ignore[no-untyped-def]
    got = open_encumbrances_as_of(fixture_db, parcel, on, NOW, doc_types_cfg)
    assert [e.instrument_uid for e in got] == expected


def test_encumbrance_carries_amount_and_row(fixture_db, doc_types_cfg) -> None:  # type: ignore[no-untyped-def]
    (dot,) = open_encumbrances_as_of(fixture_db, P1, date(2019, 1, 1), NOW, doc_types_cfg)
    assert dot.principal_amount == Decimal("100000.00")
    assert dot.recorded_seq == 2 and len(dot.row_id) == 32


def test_nothing_known_before_ingest(fixture_db, doc_types_cfg) -> None:  # type: ignore[no-untyped-def]
    before = datetime(2026, 1, 31, tzinfo=UTC)
    assert owners_as_of(fixture_db, P1, date(2020, 1, 1), before) == []
    assert open_encumbrances_as_of(fixture_db, P1, date(2020, 3, 1), before, doc_types_cfg) == []


@pytest.mark.parametrize(
    ("on", "known", "expected"),
    [
        (date(2020, 6, 30), NOW, None),
        (date(2020, 7, 1), NOW, (2020, Decimal("150000.00"))),
        (date(2025, 6, 30), NOW, (2020, Decimal("150000.00"))),
        # Before the correction was ingested we knew 200,000; after, 210,000.
        (date(2026, 1, 1), datetime(2026, 2, 15, tzinfo=UTC), (2025, Decimal("200000.00"))),
        (date(2026, 1, 1), NOW, (2025, Decimal("210000.00"))),
    ],
)
def test_assessment_as_of(fixture_db, on, known, expected) -> None:  # type: ignore[no-untyped-def]
    got = assessment_as_of(fixture_db, P1, on, known)
    assert (None if got is None else (got.tax_year, got.appraised_total)) == expected
