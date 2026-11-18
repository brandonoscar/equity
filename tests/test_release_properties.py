"""Property tests for encumbrance termination (Hypothesis).

Invariants:
- a release removes exactly the instrument it references, and nothing else;
- load order never changes the as-of result;
- only releases recorded on/before the as-of date count.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from equity.config import doc_types
from equity.schema.clock import fixed_clock
from equity.schema.load import load_rows
from equity.schema.migrate import connect, migrate
from equity.schema.temporal import open_encumbrances_as_of

CFG = doc_types()
PARCEL = "99001-09-09-0001"
EPOCH = date(2000, 1, 1)
CLOCK = fixed_clock(datetime(2026, 1, 1, tzinfo=UTC))
KNOWN = datetime(2026, 1, 2, tzinfo=UTC)


def _prov(key: str) -> dict[str, Any]:
    return {
        "source_record_id": f"sr-{key}", "source_id": "prop", "jurisdiction": "99001",
        "record_key": key, "source_uri": f"mem://{key}",
        "retrieved_at": "2025-12-31T00:00:00+00:00", "content_sha256": "b" * 64,
    }  # fmt: skip


def _rows(liens: list[int], releases: list[tuple[int, int]]) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for i, day in enumerate(liens):
        uid = f"L{i}"
        out.append(("instrument", {
            "instrument_uid": uid, "instrument_number": uid, "doc_type_raw": "DOT",
            "doc_type": "DEED_OF_TRUST", "recorded_on": (EPOCH + timedelta(day)).isoformat(),
            "recorded_seq": 1, **_prov(uid),
        }))  # fmt: skip
        out.append(("instrument_parcel", {
            "instrument_uid": uid, "parcel_uid": PARCEL, "method": "manual",
            "evidence": {"p": 1}, **_prov(uid),
        }))  # fmt: skip
    for j, (target, delay) in enumerate(releases):
        uid = f"R{j}"
        day = liens[target] + delay
        out.append(("instrument", {
            "instrument_uid": uid, "instrument_number": uid, "doc_type_raw": "REL",
            "doc_type": "RELEASE", "recorded_on": (EPOCH + timedelta(day)).isoformat(),
            "recorded_seq": 2, **_prov(uid),
        }))  # fmt: skip
        out.append(("instrument_ref", {
            "from_uid": uid, "to_uid": f"L{target}", "ref_type": "releases",
            "method": "index_xref", **_prov(uid),
        }))  # fmt: skip
    return out


def _open(rows: list[tuple[str, dict[str, Any]]], on_day: int) -> list[str]:
    con = connect()
    migrate(con, CLOCK)
    for table, row in rows:
        load_rows(con, table, [row], CLOCK)
    got = open_encumbrances_as_of(con, PARCEL, EPOCH + timedelta(on_day), KNOWN, CFG)
    con.close()
    return [e.instrument_uid for e in got]


def _expected(liens: list[int], releases: list[tuple[int, int]], on_day: int) -> set[str]:
    released = {t for t, d in releases if liens[t] + d <= on_day}
    return {f"L{i}" for i, day in enumerate(liens) if day <= on_day and i not in released}


scenario = st.lists(st.integers(0, 3000), min_size=1, max_size=5).flatmap(
    lambda liens: st.tuples(
        st.just(liens),
        st.lists(st.tuples(st.integers(0, len(liens) - 1), st.integers(0, 2000)), max_size=4),
        st.integers(0, 6000),
    )
)


@settings(max_examples=40, deadline=None)
@given(scenario)
def test_open_set_matches_definition(case: tuple[list[int], list[tuple[int, int]], int]) -> None:
    liens, releases, on_day = case
    assert set(_open(_rows(liens, releases), on_day)) == _expected(liens, releases, on_day)


@settings(max_examples=25, deadline=None)
@given(scenario, st.randoms(use_true_random=False))
def test_load_order_does_not_matter(case, rnd) -> None:  # type: ignore[no-untyped-def]
    liens, releases, on_day = case
    rows = _rows(liens, releases)
    shuffled = list(rows)
    rnd.shuffle(shuffled)
    assert _open(rows, on_day) == _open(shuffled, on_day)


@settings(max_examples=25, deadline=None)
@given(scenario)
def test_each_release_removes_exactly_its_target(case) -> None:  # type: ignore[no-untyped-def]
    liens, releases, _ = case
    if not releases:
        return
    on_day = 10_000  # after everything
    with_all = set(_open(_rows(liens, releases), on_day))
    target = releases[-1][0]
    without_last = set(_open(_rows(liens, releases[:-1]), on_day))
    other_releases_of_target = any(t == target for t, _ in releases[:-1])
    expected_diff = set() if other_releases_of_target else {f"L{target}"}
    assert without_last - with_all == expected_diff
    assert with_all <= without_last
