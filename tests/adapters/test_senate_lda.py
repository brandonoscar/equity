"""LDA.gov registrants, clients and lobbyists (equity.adapters.federal.senate_lda)."""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.senate_lda import (
    API,
    PAGES_PER_PART,
    LDAClients,
    LDALobbyists,
    LDARegistrants,
    keep,
)
from equity.adapters.http import PoliteClient
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
ROOT = Path(__file__).parents[1] / "fixtures" / "adapters"
REG = {
    "id": 8453, "name": "BRIDGE PUBLIC AFFAIRS, LLC", "address_1": "801 Pennsylvania Avenue, NW",
    "address_2": "Suite 430", "city": "Washington", "state": "DC", "zip": "20004",
    "country": "US", "contact_name": "MR. PETER ROE", "contact_telephone": "+1 202-555-0100",
    "state_display": "District of Columbia", "url": "https://lda.gov/api/v1/registrants/8453/",
}  # fmt: skip
CLIENT = {"id": 44400, "name": "BLUECROSS BLUESHIELD OF TENNESSEE, INC.", "state": "TN",
          "country": "US", "effective_date": "2022-02-09", "registrant": REG}  # fmt: skip
LOBBYIST = {"id": 2, "first_name": "TOBIN", "middle_name": "L", "last_name": "SMITH",
            "suffix": "JR", "registrant": REG}  # fmt: skip


def _fetched(cls: Any, rows: list[dict[str, Any]]) -> Fetched:
    body = canonical_json({"rows": [keep(r) for r in rows]})
    return Fetched(cls.source_id, f"{API}/x/", AT, 200, body, "application/json")


def _out(cls: Any, rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return [(r.table, dict(r.row)) for r in cls().normalize(_fetched(cls, rows))]


def test_keep_drops_phones_urls_and_labels() -> None:
    k = keep(CLIENT)
    assert "contact_telephone" not in k["registrant"] and "url" not in k["registrant"]
    assert "state_display" not in k["registrant"] and k["registrant"]["zip"] == "20004"


def test_registrants_become_businesses_with_their_contact() -> None:
    out = _out(LDARegistrants, [REG, {"id": 9}])
    (biz,) = [r for t, r in out if t == "business"]
    assert (biz["sos_id"], biz["jurisdiction"], biz["valid_from"]) == ("LDA-REG:8453", "11",
                                                                      AT.date())  # fmt: skip
    addrs = {r["address_id"]: r for t, r in out if t == "address"}
    assert addrs[biz["principal_address_id"]]["line1"].startswith("801 PENNSYLVANIA")
    (contact,) = [r for t, r in out if t == "party"]
    assert (contact["raw_name"], contact["party_kind"]) == ("PETER ROE", "person")


def test_clients_name_their_registrant() -> None:
    out = _out(LDAClients, [CLIENT])
    (biz,) = [r for t, r in out if t == "business"]
    assert (biz["sos_id"], biz["valid_from"], biz["jurisdiction"], biz["principal_address_id"]
            ) == ("LDA-CLIENT:44400", date(2022, 2, 9), "47", None)  # fmt: skip
    (role,) = [r for t, r in out if t == "business_role"]
    (party,) = [r for t, r in out if t == "party"]
    assert role["title"] == "LOBBYING REGISTRANT" and party["raw_name"] == REG["name"]
    assert party["address_id"] is not None


def test_lobbyists_are_people_at_the_registrant() -> None:
    out = _out(LDALobbyists, [LOBBYIST, {"id": 3, "first_name": "ONLY"}])
    parties = {r["raw_name"]: r for t, r in out if t == "party"}
    smith = parties["TOBIN L SMITH JR"]
    assert (smith["party_kind"], smith["first_name"], smith["middle"], smith["last_name"],
            smith["suffix"]) == ("person", "TOBIN", "L", "SMITH", "JR")  # fmt: skip
    assert parties[REG["name"]]["address_id"] == smith["address_id"] is not None
    assert len([t for t, _ in out if t == "source_record"]) == 1


class _API:
    def __init__(self, n: int) -> None:
        self.n, self.queries = n, []  # type: ignore[var-annotated]

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                 ) -> tuple[int, bytes, str]:  # fmt: skip
        base, _, qs = url.partition("?")
        if base.endswith("/robots.txt"):
            return 200, b"User-agent: *\nAllow: /api/v1/\nCrawl-delay: 4\n", "text/plain"
        q = dict(urllib.parse.parse_qsl(qs))
        self.queries.append(q)
        size, page = int(q["page_size"]), int(q["page"])
        ids = list(range(1, self.n + 1))[(page - 1) * size : page * size]
        if not ids:
            return 404, b'{"detail":"Invalid page."}', "application/json"
        body = {"count": self.n, "next": "x" if page * size < self.n else None,
                "results": [{**REG, "id": i} for i in ids]}  # fmt: skip
        return 200, json.dumps(body).encode(), "application/json"


def test_partitions_and_paged_fetch() -> None:
    api = _API(25 * PAGES_PER_PART + 3)
    slept: list[float] = []
    adapter = LDARegistrants(PoliteClient(transport=api, sleep=slept.append, now=lambda: AT))
    parts = list(adapter.partitions())
    assert parts == [{"page_from": "1", "page_to": str(1 + PAGES_PER_PART)},
                     {"page_from": str(1 + PAGES_PER_PART),
                      "page_to": str(1 + 2 * PAGES_PER_PART)}]  # fmt: skip
    body = json.loads(adapter.fetch(FetchRequest(parts[1])).content)
    assert [r["id"] for r in body["rows"]] == [25 * PAGES_PER_PART + i for i in (1, 2, 3)]
    assert all(q["ordering"] == "id" for q in api.queries)
    assert slept and min(slept) > 0  # robots.txt Crawl-delay spacing
    body = json.loads(adapter.fetch(FetchRequest({"page_from": "2", "limit": "2"})).content)
    assert [r["id"] for r in body["rows"]] == [3, 4]
    with pytest.raises(ValueError, match="bad page window"):
        adapter.fetch(FetchRequest({"page_from": "0"}))


@pytest.mark.parametrize("cls", [LDARegistrants, LDAClients, LDALobbyists])
def test_recorded_fixtures_are_pseudonymized(cls: Any) -> None:
    paths = sorted((ROOT / cls.source_id).glob("*.json"))
    assert paths

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            assert "contact_telephone" not in obj
            for k, v in obj.items():
                if k in cls.pii_fields and isinstance(v, str):
                    assert v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for path in paths:
        walk(json.loads(path.read_text()))


@pytest.mark.parametrize("cls", [LDARegistrants, LDAClients, LDALobbyists])
def test_recorded_fixtures_pass_the_adapter_contract(cls: type, empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(cls, sorted((ROOT / cls.source_id).glob("*.json")), empty_db)  # type: ignore[attr-defined]
