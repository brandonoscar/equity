"""Cook County Medical Examiner death lists: one death_record per case, never a party."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from equity.adapters.base import Fetched
from equity.adapters.death_records import (
    CookHeightsCrematory,
    CookIndigentCremations,
    CookUnclaimedPersons,
)

AT = datetime(2025, 12, 31, tzinfo=UTC)


def _rows(cls: type, rows: list[dict[str, object]]) -> list[tuple[str, dict[str, object]]]:
    body = json.dumps({"rows": rows}).encode()
    f = Fetched(cls.source_id, "https://x.test", AT, 200, body, "application/json")
    return [(r.table, dict(r.row)) for r in cls().normalize(f)]


def test_cremation_row_is_a_death_record_and_no_party() -> None:
    out = _rows(CookIndigentCremations, [
        {"case": "ME2024-1", "name": "Ann  O'Lee", "age": "75", "sex": "F",
         "date_of_death": "2024-09-14T00:00:00.000", "cremation_date": "2024-10-28T00:00:00.000"},
        {"case": "ME2024-1", "name": "dup", "age": "99"},  # same case: first in content order
        {"case": "ME2024-2", "name": " ", "age": "40"},         # no name: skipped
    ])  # fmt: skip
    assert [t for t, _ in out] == ["source_record", "death_record"]
    rec = out[1][1]
    assert (
        rec["name_norm"],
        rec["death_date"],
        rec["listed_on"],
        rec["age_years"],
        rec["sex"],
        rec["record_kind"],
    ) == ("ANN O LEE", date(2024, 9, 14), date(2024, 10, 28), 75, "F", "indigent_cremation")


def test_unclaimed_has_arrival_but_no_death_date_and_age_from_combined_field() -> None:
    (_, rec), = [x for x in _rows(CookUnclaimedPersons, [
        {"case": "ME2025-9", "name": "BO RAY", "age_sex_race": "79 F W", "gender": "Female",
         "date_of_arrival": "2025-07-10T00:00:00.000"}]) if x[0] == "death_record"]  # fmt: skip
    assert (rec["death_date"], rec["listed_on"], rec["age_years"], rec["sex"]) == (
        None,
        date(2025, 7, 10),
        79,
        "F",
    )


def test_crematory_keeps_alternate_spellings_and_place() -> None:
    (_, rec), = [x for x in _rows(CookHeightsCrematory, [
        {"case_number": "HC-1", "decedent": "JON DOE", "alternate_spellings": "John Doe; JON DOW",
         "age": "U", "sex": "x", "date_of_death": "2018-07-22T00:00:00.000",
         "place_of_death": "1 MAIN ST"}]) if x[0] == "death_record"]  # fmt: skip
    assert rec["alternate_names"] == ["JOHN DOE", "JON DOW"]
    assert (rec["age_years"], rec["sex"], rec["place"]) == (None, None, "1 MAIN ST")
    assert CookHeightsCrematory().source_row()["kind"] == "vital_record"
