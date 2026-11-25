"""FMCSA Company Census File (equity.adapters.federal.fmcsa)."""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.fmcsa import (
    WINDOW,
    FMCSACarrierCensus,
    parse_day,
    person_parts,
    window_where,
)
from equity.adapters.http import PoliteClient
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters" / FMCSACarrierCensus.source_id
CORP = {
    "dot_number": "9241", "legal_name": "GREEN MOUNTAIN HAULING INC",
    "dba_name": "GMH", "company_officer_1": "JOHN A SMITH JR",
    "company_officer_2": "DOE, JANE", "status_code": "A", "add_date": "19740601",
    "mcs150_date": "20181211", "business_org_id": "3", "phy_street": "1 MAIN ST",
    "phy_city": "PITTSFORD", "phy_state": "VT", "phy_zip": "05763", "phy_cnty": "021",
    "phy_country": "US", "carrier_mailing_street": "PO BOX 9",
    "carrier_mailing_city": "RUTLAND", "carrier_mailing_state": "VT",
    "carrier_mailing_zip": "05701-0009", "carrier_mailing_country": "US",
    "power_units": "3", "docket1prefix": "MC", "docket1": "200649",
}  # fmt: skip
SOLE = {
    "dot_number": "9254", "legal_name": "MARY K JONES", "company_officer_1": "MARY K JONES",
    "status_code": "I", "add_date": "20991231", "business_org_id": "1", "phy_street": "2 ELM ST",
    "phy_city": "BARRE", "phy_state": "VT", "phy_zip": "05641", "phy_country": "US",
}  # fmt: skip
CANADA = {
    "dot_number": "77", "legal_name": "MAPLE FREIGHT LTD", "phy_street": "3 KING ST",
    "phy_city": "TORONTO", "phy_state": "ON", "phy_country": "CA", "status_code": "A",
}  # fmt: skip


def _fetched(rows: list[dict[str, Any]]) -> Fetched:
    return Fetched(FMCSACarrierCensus.source_id, "https://data.transportation.gov/r#VT", AT,
                   200, canonical_json({"rows": rows}), "application/json")  # fmt: skip


def test_carriers_become_businesses_with_officers() -> None:
    out = [(r.table, dict(r.row)) for r in FMCSACarrierCensus().normalize(
        _fetched([CORP, SOLE, CANADA, {"dot_number": "5"}]))]  # fmt: skip
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    assert set(biz) == {"USDOT:9241", "USDOT:9254", "USDOT:77"}
    corp = biz["USDOT:9241"]
    assert (corp["status"], corp["org_form"], corp["valid_from"]) == (
        "active",
        "INC",
        date(1974, 6, 1),
    )
    assert corp["jurisdiction"] == "50021"  # Rutland County, VT
    addrs = {r["address_id"]: r for t, r in out if t == "address"}
    assert addrs[corp["principal_address_id"]]["line1"] == "1 MAIN ST"
    assert addrs[corp["mailing_address_id"]]["zip5"] == "05701"
    assert biz["USDOT:9254"]["valid_from"] == AT.date()  # a future add date
    assert biz["USDOT:9254"]["status"] == "inactive"
    assert biz["USDOT:77"]["principal_address_id"] is None
    assert biz["USDOT:77"]["jurisdiction"] == "US"
    parties = {r["party_id"]: r for t, r in out if t == "party"}
    roles = sorted((r["sos_id"], r["role"], r["title"], parties[r["party_id"]]["raw_name"])
                   for t, r in out if t == "business_role")  # fmt: skip
    assert roles == [
        ("USDOT:9241", "officer", "COMPANY OFFICER", "DOE, JANE"),
        ("USDOT:9241", "officer", "COMPANY OFFICER", "JOHN A SMITH JR"),
        ("USDOT:9254", "officer", "COMPANY OFFICER", "MARY K JONES"),
        ("USDOT:9254", "other", "SOLE PROPRIETOR", "MARY K JONES"),
    ]
    smith = next(p for p in parties.values() if p["raw_name"] == "JOHN A SMITH JR")
    assert (smith["party_kind"], smith["first_name"], smith["middle"], smith["last_name"],
            smith["suffix"]) == ("person", "JOHN", "A", "SMITH", "JR")  # fmt: skip
    doe = next(p for p in parties.values() if p["raw_name"] == "DOE, JANE")
    assert (doe["first_name"], doe["last_name"]) == ("JANE", "DOE")


def test_helpers() -> None:
    assert parse_day("20181211") == date(2018, 12, 11)
    assert parse_day("2018-12-11T00:00:00.000") == date(2018, 12, 11)
    assert parse_day("20181311") is None and parse_day(None) is None
    assert person_parts("ANN LEE")["last_name"] == "LEE"
    assert window_where("VT", None, "100") == "phy_state = 'VT' AND dot_number < 100"
    assert window_where("other", "5", None) == "phy_state IS NULL AND dot_number >= 5"


def test_pii_fields_cover_names_and_streets_and_the_scrub_hides_ids() -> None:
    assert set(FMCSACarrierCensus.pii_fields) == {"legal_name", "dba_name", "company_officer_1",
                                                 "company_officer_2", "phy_street",
                                                 "carrier_mailing_street"}  # fmt: skip
    (r,) = json.loads(FMCSACarrierCensus.scrub_fixture(canonical_json({"rows": [CORP]})))["rows"]
    assert r["legal_name"].startswith("TESTOWNER") and r["legal_name"].endswith(" INC")
    assert r["company_officer_1"].startswith("TESTOWNER")
    assert r["phy_street"].endswith(" TEST ST")
    assert r["dot_number"].startswith("0") and r["dot_number"] != "9241"
    assert r["docket1"] != "200649" and r["phy_city"] == "PITTSFORD"


def test_recorded_fixture_is_pseudonymized() -> None:
    paths = sorted(FIXTURES.glob("*.json"))
    assert paths
    for path in paths:
        for r in json.loads(path.read_text())["rows"]:
            for k in FMCSACarrierCensus.pii_fields:
                v = r.get(k)
                assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k
            assert r["dot_number"].startswith("0")
            assert not {"phone", "email_address", "cell_phone", "dun_bradstreet_no"} & set(r)


class _Soda:
    """A fake SODA endpoint: grouped counts, $offset probes, windowed pages."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.queries: list[dict[str, str]] = []

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                 ) -> tuple[int, bytes, str]:  # fmt: skip
        base, _, qs = url.partition("?")
        if base.endswith("/robots.txt"):
            return 200, b"User-agent: *\nCrawl-delay: 1\n", "text/plain"
        q = dict(urllib.parse.parse_qsl(qs))
        self.queries.append(q)
        if q.get("$group") == "phy_state":
            body: list[dict[str, Any]] = [{"phy_state": "VT", "n": str(2 * WINDOW + 5)},
                                          {"n": "2"}, {"phy_state": "B@D", "n": "1"}]  # fmt: skip
        elif q.get("$select") == "dot_number":
            body = [{"dot_number": str(int(q["$offset"]) * 10)}]
        else:
            body = self.rows[: int(q["$limit"])]
        return 200, json.dumps(body).encode(), "application/json"


def _adapter(api: _Soda) -> FMCSACarrierCensus:
    return FMCSACarrierCensus(PoliteClient(transport=api, sleep=lambda s: None, now=lambda: AT))


def test_partitions_cut_big_states_into_usdot_ranges() -> None:
    parts = list(_adapter(_Soda([])).partitions())
    assert parts == [
        {"state": "VT", "dot_to": str(WINDOW * 10)},
        {"state": "VT", "dot_from": str(WINDOW * 10), "dot_to": str(2 * WINDOW * 10)},
        {"state": "VT", "dot_from": str(2 * WINDOW * 10)},
        {"state": "other"},
    ]


def test_fetch_selects_kept_columns_in_usdot_order_and_honors_limit() -> None:
    api = _Soda([{**CORP, "phone": "8025551212", "email_address": "x"}, SOLE])
    fetched = _adapter(api).fetch(FetchRequest({"state": "VT", "dot_from": "9000",
                                                "limit": "1"}))  # fmt: skip
    body = json.loads(fetched.content)
    assert [r["dot_number"] for r in body["rows"]] == ["9241"]
    assert "phone" not in body["rows"][0] and "email_address" not in body["rows"][0]
    q = api.queries[-1]
    assert q["$where"] == "phy_state = 'VT' AND dot_number >= 9000"
    assert (q["$order"], q["$limit"]) == ("dot_number", "1") and "legal_name" in q["$select"]
    with pytest.raises(ValueError, match="bad state"):
        _adapter(api).fetch(FetchRequest({"state": "V'T"}))
    with pytest.raises(ValueError, match="USDOT"):
        _adapter(api).fetch(FetchRequest({"state": "VT", "dot_to": "1 OR 1=1"}))


def test_recorded_fixture_passes_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(FMCSACarrierCensus, sorted(FIXTURES.glob("*.json")), empty_db)
