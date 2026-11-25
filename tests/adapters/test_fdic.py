"""FDIC BankFind institutions and locations (equity.adapters.federal.fdic)."""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.fdic import FDICInstitutions, FDICLocations, county_jurisdiction, mdy
from equity.adapters.http import PoliteClient
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
ROOT = Path(__file__).parents[1] / "fixtures" / "adapters"
BANK = {
    "CERT": 6209, "NAME": "Connecticut River Bank, National Association",
    "ADDRESS": "242 River Street", "CITY": "Springfield", "STALP": "VT", "ZIP": "05156",
    "STCNTY": "50027", "ACTIVE": 0, "ESTYMD": "01/01/1864", "ENDEFYMD": "08/16/2014",
    "NAMEHCR": "CONNECTICUT RIVER BCORP INC", "CITYHCR": "CHARLESTOWN", "STALPHCR": "NH",
    "PRIORNAME1": "The Connecticut River National Bank", "PRIORNAME2": "Connecticut River Bank",
}  # fmt: skip
OPEN = {"CERT": 1, "NAME": "New Bank", "STALP": "VT", "ACTIVE": 1, "ESTYMD": "01/01/2099",
        "ENDEFYMD": "12/31/9999"}  # fmt: skip
OFFICE = {"UNINUM": 45, "CERT": 6209, "NAME": "Santander Bank, N.A.", "OFFNAME": "GLOUCESTER",
          "ADDRESS": "102 Rogers St", "CITY": "Gloucester", "STALP": "MA", "ZIP": "01930",
          "STCNTY": "25009"}  # fmt: skip


def _fetched(cls: type, rows: list[dict[str, Any]]) -> Fetched:
    return Fetched(cls.source_id, "https://api.fdic.gov/banks/x", AT, 200,  # type: ignore[attr-defined]
                   canonical_json({"rows": rows}), "application/json")  # fmt: skip


def test_institutions_become_businesses_with_holding_company_and_prior_names() -> None:
    out = [(r.table, dict(r.row)) for r in FDICInstitutions().normalize(
        _fetched(FDICInstitutions, [BANK, OPEN, {"CERT": 9}]))]  # fmt: skip
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    assert set(biz) == {"FDIC:6209", "FDIC:1"}
    b = biz["FDIC:6209"]
    assert (b["status"], b["formed_on"], b["status_date"], b["valid_from"], b["jurisdiction"]) == (
        "inactive",
        date(1864, 1, 1),
        date(2014, 8, 16),
        date(1864, 1, 1),
        "50027",
    )
    assert biz["FDIC:1"]["status"] == "active" and biz["FDIC:1"]["valid_from"] == AT.date()
    assert biz["FDIC:1"]["status_date"] is None and biz["FDIC:1"]["formed_on"] is None
    roles = [r for t, r in out if t == "business_role"]
    assert [(r["title"], r["sos_id"]) for r in roles] == [("BANK HOLDING COMPANY", "FDIC:6209")]
    names = sorted(r["raw_name"] for t, r in out if t == "party")
    assert names == ["CONNECTICUT RIVER BCORP INC", "Connecticut River Bank",
                     "The Connecticut River National Bank"]  # fmt: skip
    addrs = {r["address_id"]: r for t, r in out if t == "address"}
    assert addrs[b["principal_address_id"]]["line1"] == "242 RIVER STREET"


def test_locations_name_the_institution_at_each_office() -> None:
    out = [(r.table, dict(r.row)) for r in FDICLocations().normalize(
        _fetched(FDICLocations, [OFFICE]))]  # fmt: skip
    (party,) = [r for t, r in out if t == "party"]
    assert (party["raw_name"], party["party_kind"], party["jurisdiction"]) == (
        "Santander Bank, N.A.",
        "org",
        "25009",
    )
    (addr,) = [r for t, r in out if t == "address"]
    assert addr["address_id"] == party["address_id"] and addr["zip5"] == "01930"


def test_helpers() -> None:
    assert mdy("08/16/2014") == date(2014, 8, 16) and mdy("2014-08-16") is None
    assert county_jurisdiction({"STALP": "VT", "STCNTY": "50999"}) == "50"
    assert county_jurisdiction({"STALP": "XX"}) == "US"


class _API:
    def __init__(self) -> None:
        self.queries: list[dict[str, str]] = []

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                 ) -> tuple[int, bytes, str]:  # fmt: skip
        base, _, qs = url.partition("?")
        if base.endswith("/robots.txt"):
            return 404, b"", "text/plain"
        q = dict(urllib.parse.parse_qsl(qs))
        self.queries.append(q)
        if "agg_by" in q:
            body: dict[str, Any] = {"data": [{"data": {"STALP": "VT", "count": 3}},
                                             {"data": {"STALP": "", "count": 1}}]}  # fmt: skip
        else:
            rows = [BANK, OPEN, {**BANK, "CERT": 7}]
            off, lim = int(q["offset"]), int(q["limit"])
            body = {"meta": {"total": len(rows)},
                    "data": [{"data": r} for r in rows[off : off + min(lim, 2)]]}  # fmt: skip
        return 200, json.dumps(body).encode(), "application/json"


def test_partitions_by_state_and_paged_fetch() -> None:
    api = _API()
    adapter = FDICInstitutions(PoliteClient(transport=api, sleep=lambda s: None, now=lambda: AT))
    assert list(adapter.partitions()) == [{"state": "VT"}]
    body = json.loads(adapter.fetch(FetchRequest({"state": "vt"})).content)
    assert [r["CERT"] for r in body["rows"]] == [6209, 1, 7]
    assert api.queries[-1]["filters"] == 'STALP:"VT"' and api.queries[-1]["sort_by"] == "CERT"
    body = json.loads(adapter.fetch(FetchRequest({"state": "VT", "limit": "1"})).content)
    assert len(body["rows"]) == 1
    with pytest.raises(ValueError, match="bad state"):
        adapter.fetch(FetchRequest({"state": 'V"T'}))


@pytest.mark.parametrize("cls", [FDICInstitutions, FDICLocations])
def test_recorded_fixtures_pass_the_adapter_contract(cls: type, empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(cls, sorted((ROOT / cls.source_id).glob("*.json")), empty_db)  # type: ignore[attr-defined]
