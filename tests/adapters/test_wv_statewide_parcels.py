"""WV statewide parcel adapter on its recorded (pseudonymized) fixture, plus edge cases."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.wv.statewide_parcels import (
    FIELDS,
    WVStatewideParcels,
    address_row,
    choose_row,
    valid_from_for,
)

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures/adapters/wv.statewide.parcels/county_number-31_limit-25.json"
)
AT = datetime(2026, 11, 15, 12, tzinfo=UTC)


def fetched(content: bytes) -> Fetched:
    return Fetched("wv.statewide.parcels", "fixture://wv", AT, 200, content, "application/json")


def rows(content: bytes) -> list[tuple[str, dict[str, Any]]]:
    return [(r.table, dict(r.row)) for r in WVStatewideParcels().normalize(fetched(content))]


def test_fixture_normalizes_to_expected_tables() -> None:
    out = rows(FIXTURE.read_bytes())
    counts = Counter(t for t, _ in out)
    assert counts["source_record"] == counts["parcel"] == 25
    assert counts["parcel_assessment"] == 25
    assert counts["owner_snapshot"] == counts["party"] >= 25
    parcels = {r["parcel_uid"] for t, r in out if t == "parcel"}
    assert "54061-140024000400010000" in parcels
    assert all(p.startswith("54061-") for p in parcels)


def test_fixture_values_and_rules() -> None:
    out = rows(FIXTURE.read_bytes())
    a = next(r for t, r in out if t == "parcel_assessment"
             and r["parcel_uid"] == "54061-140024000400010000")  # fmt: skip
    assert a["appraised_total"] == "176200.00"
    assert a["tax_year"] == 2026
    assert a["valid_from"] == date(2026, 1, 1)  # config: tax_year_jan1
    snap = next(r for t, r in out if t == "owner_snapshot")
    assert snap["observed_on"] == date(2026, 11, 15)
    orgs = [r for t, r in out if t == "party" and r["party_kind"] == "org"]
    assert any(r["org_form"] == "LLC" for r in orgs)
    assert all(r["raw_name"].startswith("TESTOWNER") for t, r in out if t == "party")


def test_party_ids_are_stable_across_fetches() -> None:
    first = {r["party_id"] for t, r in rows(FIXTURE.read_bytes()) if t == "party"}
    later_fetch = Fetched("wv.statewide.parcels", "fixture://wv2", datetime(2027, 1, 1, tzinfo=UTC),
                          200, FIXTURE.read_bytes(), "application/json")  # fmt: skip
    later = list(WVStatewideParcels().normalize(later_fetch))
    assert first == {r.row["party_id"] for r in later if r.table == "party"}


def _attrs(**kw: Any) -> dict[str, Any]:
    base = {f: None for f in FIELDS}
    base.update({"ID": 1, "CleanParcelID": "3101000012", "CountyCode": 31, "ParcelID": "01000012",
                 "DistrictCode": 1, "Map": "0000", "ParcelNumber": "12", "Suffix": "", "Cards": 1,
                 "TaxYear": 2026})  # fmt: skip
    base.update(kw)
    return base


def test_duplicate_parcel_rows_pick_the_carded_row_deterministically() -> None:
    stub = _attrs(ID=5, Cards=0, TotalAppraisal=0, ParcelID="010000000012")
    real = _attrs(ID=9, Cards=1, TotalAppraisal=5000)
    assert choose_row([stub, real])["ID"] == 9
    assert choose_row([real, stub])["ID"] == 9
    assert choose_row([_attrs(ID=7, Cards=0), _attrs(ID=3, Cards=0)])["ID"] == 3
    body = json.dumps({"layer": "x", "where": "y", "attributes": [stub, real]}).encode()
    totals = [r["appraised_total"] for t, r in rows(body) if t == "parcel_assessment"]
    assert totals == ["5000.00"]


def test_rows_without_owner_tax_year_or_parcel_id() -> None:
    body = json.dumps({"layer": "x", "where": "y", "attributes": [
        _attrs(TaxYear=None, ParcelID=None), _attrs(CleanParcelID=None)]}).encode()  # fmt: skip
    out = rows(body)
    assert Counter(t for t, _ in out) == Counter({"source_record": 1, "parcel": 1})
    assert next(r for t, r in out if t == "parcel")["parid_raw"] == "01000012"


def test_address_rows() -> None:
    assert address_row(_attrs()) is None
    a = address_row(_attrs(OwnerAddress1="PO Box 12", OwnerAddress2="Apt. 3",
                           OwnerCity="Morgantown", OwnerStateCode="WV",
                           OwnerZipCode="26505-1234"))  # fmt: skip
    assert a is not None
    assert (a["line1"], a["line2"], a["zip5"]) == ("PO Box 12", "Apt. 3", "26505")
    assert a["norm_key"] == "PO BOX 12 APT 3|MORGANTOWN|WV|26505"


def test_valid_from_rules() -> None:
    assert valid_from_for(2026, "tax_year_jan1") == date(2026, 1, 1)
    assert valid_from_for(2026, "prior_july1") == date(2025, 7, 1)
    with pytest.raises(ValueError, match="unknown"):
        valid_from_for(2026, "guess")


def test_where_rejects_bad_county() -> None:
    assert WVStatewideParcels().where(FetchRequest({"county_number": "31"})) == "CountyCode=31"
    with pytest.raises(ValueError, match="1-55"):
        WVStatewideParcels().where(FetchRequest({"county_number": "56"}))


def test_partitions_cover_all_55_counties() -> None:
    plan = list(WVStatewideParcels().partitions())
    assert len(plan) == 55
    assert plan[30] == {"county_number": "31"}
