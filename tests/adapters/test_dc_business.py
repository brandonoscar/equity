"""DC registrations and beneficial owners."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.dc_business import DCBusiness, one_line_address


def _fetched(body: dict[str, object]) -> Fetched:
    return Fetched("dc.dlcp.business", "x", datetime(2026, 11, 22, tzinfo=UTC), 200,
                   json.dumps(body).encode(), "application/json")  # fmt: skip


def test_one_line_address() -> None:
    a = one_line_address("100 Test St NW, Apt 2, Washington, DC, 20001, USA")
    assert a is not None and (a["line1"], a["city"], a["state"], a["zip5"]) == (
        "100 TEST ST NW APT 2", "WASHINGTON", "DC", "20001")  # fmt: skip
    b = one_line_address("1 Test Rd, Bethesda, md, 20814-1234")
    assert b is not None and (b["state"], b["zip5"]) == ("MD", "20814")
    c = one_line_address("Somewhere abroad")
    assert c is not None and c["city"] is None and c["zip5"] is None
    assert one_line_address(None) is None


def test_registrations_and_owners() -> None:
    reg = {"layer": "0", "rows": [
        {"OBJECTID": 2, "FILE_NUMBER": "L00000000001", "BUSINESS_NAME": "TEST HOLDINGS LLC",
         "ENTITY_STATUS": "Active", "EFFECTIVE_DATE": 1577836800000,
         "BUSNIESS_ADDRESS_LINE1": "1 TEST ST", "BUSINESS_CITY": "WASHINGTON",
         "BUSINESS_STATE": "DC", "ZIPCODE": "20001", "RA_NAME": "AGENT CO INC",
         "RA_ADDRESS1": "2 TEST ST", "RA_CITY": "WASHINGTON", "RA_STATE": "DC",
         "RA_ZIPCODE": "20002"},
        {"OBJECTID": 3, "FILE_NUMBER": "L00000000001", "BUSINESS_NAME": "DUPLICATE"},
        {"OBJECTID": 4, "FILE_NUMBER": None, "BUSINESS_NAME": "NO KEY"},
    ]}  # fmt: skip
    rows = list(DCBusiness().normalize(_fetched(reg)))
    (biz,) = [r.row for r in rows if r.table == "business"]
    assert (biz["sos_id"], biz["org_form"], biz["formed_on"]) == (
        "L00000000001", "LLC", date(2020, 1, 1))  # fmt: skip
    (agent,) = [r.row for r in rows if r.table == "business_role"]
    assert (agent["role"], agent["valid_from"]) == ("registered_agent", date(2020, 1, 1))
    own = {"layer": "2", "rows": [
        {"OBJECTID": 9, "INITIALFILENUMBER": "L00000000001", "NAME": "ANN TEST",
         "ADDRESS": "3 Test St, Washington, DC, 20003, USA", "DCS_LAST_MOD_DTTM": 1735689600000},
        {"OBJECTID": 10, "INITIALFILENUMBER": None, "NAME": "NO ENTITY"},
    ]}  # fmt: skip
    rows = list(DCBusiness().normalize(_fetched(own)))
    (role,) = [r.row for r in rows if r.table == "business_role"]
    assert (role["sos_id"], role["role"], role["title"], role["valid_from"]) == (
        "L00000000001", "other", "BENEFICIAL OWNER", date(2025, 1, 1))  # fmt: skip
    (party,) = [r.row for r in rows if r.table == "party"]
    assert party["raw_name"] == "ANN TEST" and party["address_id"] is not None


def test_partitions_from_sparse_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    from equity.adapters import dc_business

    monkeypatch.setattr(dc_business, "WINDOW", 2)
    monkeypatch.setattr(dc_business, "get_json",
                        lambda client, url, params: {"objectIds": [500, 100, 300]})  # fmt: skip
    parts = list(DCBusiness().partitions())
    assert parts[:2] == [{"layer": "0", "lo": "100", "hi": "500"},
                         {"layer": "0", "lo": "500", "hi": "501"}]  # fmt: skip
    assert len(parts) == 4


def test_unknown_layer_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown layer"):
        DCBusiness().fetch(FetchRequest({"layer": "1 OR 1=1", "lo": "0", "hi": "1"}))
