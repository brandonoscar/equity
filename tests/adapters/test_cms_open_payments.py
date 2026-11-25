"""CMS Open Payments general payments (equity.adapters.federal.cms_open_payments)."""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.cms_open_payments import (
    META,
    THIRD_PARTY,
    WINDOW,
    CMSOpenPayments,
    query_params,
)
from equity.adapters.http import PoliteClient
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters" / CMSOpenPayments.source_id
DATASET = "fb0b1734-1410-429d-92f6-3f4b35218e5e"
PHYSICIAN = {
    "record_id": "1157436416", "program_year": "2025",
    "covered_recipient_type": "Covered Recipient Physician",
    "covered_recipient_npi": "1023877453", "covered_recipient_profile_id": "11599044",
    "covered_recipient_first_name": "JANE", "covered_recipient_middle_name": "Q",
    "covered_recipient_last_name": "DOE", "covered_recipient_name_suffix": "",
    "recipient_primary_business_street_address_line1": "214 E 23RD ST",
    "recipient_primary_business_street_address_line2": "STE 2", "recipient_city": "CHEYENNE",
    "recipient_state": "WY", "recipient_zip_code": "82001-1234",
    "recipient_country": "United States",
    "applicable_manufacturer_or_applicable_gpo_making_payment_id": "100000010740",
    "applicable_manufacturer_or_applicable_gpo_making_payment_name": "ABIOMED INC",
    "total_amount_of_payment_usdollars": "22.42", "date_of_payment": "08/06/2025",
    "nature_of_payment_or_transfer_of_value": "Food and Beverage",
    THIRD_PARTY: "ACME CONSULTING LLC", "contextual_information": "free text",
}  # fmt: skip
HOSPITAL = {
    "record_id": "1157436417", "program_year": "2025",
    "covered_recipient_type": "Covered Recipient Teaching Hospital",
    "teaching_hospital_ccn": "530014", "teaching_hospital_name": "WYOMING MEDICAL CENTER",
    "recipient_primary_business_street_address_line1": "1233 E 2ND ST",
    "recipient_city": "CASPER", "recipient_state": "WY", "recipient_zip_code": "82601",
    "recipient_country": "United States",
    "applicable_manufacturer_or_applicable_gpo_making_payment_id": "100000010740",
    "applicable_manufacturer_or_applicable_gpo_making_payment_name": "ABIOMED INC",
    "total_amount_of_payment_usdollars": "1000", "date_of_payment": "12/31/2026",
}  # fmt: skip


def _fetched(rows: list[dict[str, Any]]) -> Fetched:
    return Fetched(CMSOpenPayments.source_id, "https://openpaymentsdata.cms.gov/q#WY", AT, 200,
                   canonical_json({"year": "2025", "rows": rows}), "application/json")  # fmt: skip


def test_payments_link_recipients_to_the_paying_manufacturer() -> None:
    out = [(r.table, dict(r.row)) for r in CMSOpenPayments().normalize(
        _fetched([PHYSICIAN, HOSPITAL, {"record_id": "9", "program_year": "2025"}]))]  # fmt: skip
    records = {r["record_key"] for t, r in out if t == "source_record"}
    assert records == {"1157436416", "1157436417"}  # the nameless record is skipped
    (biz,) = {r["sos_id"]: r for t, r in out if t == "business"}.values()
    assert (biz["sos_id"], biz["name"], biz["valid_from"]) == (
        "OPMFR:100000010740",
        "ABIOMED INC",
        date(2025, 1, 1),
    )
    parties = {r["raw_name"]: r for t, r in out if t == "party"}
    jane = parties["JANE Q DOE"]
    assert (jane["party_kind"], jane["first_name"], jane["last_name"]) == ("person", "JANE", "DOE")
    assert jane["jurisdiction"] == "56"
    addrs = {r["address_id"]: r for t, r in out if t == "address"}
    assert addrs[jane["address_id"]]["line1"] == "214 E 23RD ST STE 2"
    assert addrs[jane["address_id"]]["zip5"] == "82001"
    hosp = parties["WYOMING MEDICAL CENTER"]
    assert hosp["party_kind"] == "org" and hosp["last_name"] is None
    assert parties["ACME CONSULTING LLC"]["org_form"] == "LLC"
    roles = {(r["party_id"], r["title"], r["valid_from"]) for t, r in out
             if t == "business_role"}  # fmt: skip
    assert roles == {
        (jane["party_id"], "PAYMENT RECIPIENT", date(2025, 8, 6)),
        (parties["ACME CONSULTING LLC"]["party_id"], "THIRD PARTY PAYMENT RECIPIENT",
         date(2025, 8, 6)),
        (hosp["party_id"], "PAYMENT RECIPIENT", date(2025, 1, 1)),  # a future date: year start
    }  # fmt: skip


def test_a_foreign_recipient_keeps_its_address_raw() -> None:
    row = {**PHYSICIAN, "recipient_country": "Canada", "recipient_state": ""}
    out = [(r.table, dict(r.row)) for r in CMSOpenPayments().normalize(_fetched([row]))]
    assert not [r for t, r in out if t == "address"]
    assert {r["jurisdiction"] for t, r in out if t == "party"} == {"US"}


def test_pii_fields_cover_names_and_streets_and_the_scrub_hides_person_ids() -> None:
    assert {"covered_recipient_first_name", "covered_recipient_last_name", THIRD_PARTY,
            "recipient_primary_business_street_address_line1"} <= set(
        CMSOpenPayments.pii_fields)  # fmt: skip
    body = canonical_json({"rows": [PHYSICIAN, HOSPITAL]})
    jane, hosp = json.loads(CMSOpenPayments.scrub_fixture(body))["rows"]
    assert jane["covered_recipient_last_name"].startswith("TESTOWNER")
    assert jane["recipient_primary_business_street_address_line1"].endswith(" TEST ST")
    assert jane[THIRD_PARTY].startswith("TESTOWNER") and jane[THIRD_PARTY].endswith(" LLC")
    assert jane["covered_recipient_npi"].startswith("0") and jane["record_id"].startswith("0")
    assert jane["covered_recipient_npi"] != PHYSICIAN["covered_recipient_npi"]
    assert hosp["record_id"] == "1157436417" and hosp["teaching_hospital_name"].startswith("WY")


def test_recorded_fixture_is_pseudonymized() -> None:
    paths = sorted(FIXTURES.glob("*.json"))
    assert paths
    for path in paths:
        for r in json.loads(path.read_text())["rows"]:
            for k in CMSOpenPayments.pii_fields:
                v = r.get(k)
                assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k
            assert "contextual_information" not in r


class _Api:
    """A fake datastore: the metastore list, a grouped count, and paged results."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.queries: list[dict[str, str]] = []

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                 ) -> tuple[int, bytes, str]:  # fmt: skip
        base, _, qs = url.partition("?")
        if base.endswith("/robots.txt"):
            return 200, b"User-agent: *\nCrawl-delay: 5\nAllow: /\n", "text/plain"
        if base == META:
            return 200, json.dumps([
                {"title": "2025 General Payment Data", "identifier": DATASET},
                {"title": "2025 Research Payment Data", "identifier": "r"},
                {"title": "2024 General Payment Data", "identifier": "d24"},
            ]).encode(), "application/json"  # fmt: skip
        q = dict(urllib.parse.parse_qsl(qs, keep_blank_values=True))
        self.queries.append(q)
        if "groupings[0]" in q:
            body = [{"recipient_state": "WY", "n": str(WINDOW + 1)},
                    {"recipient_state": "", "n": "3"}]  # fmt: skip
            return 200, json.dumps({"results": body}).encode(), "application/json"
        if int(q["limit"]) > 500:
            return 400, b'{"message":"limit"}', "application/json"
        state = q["conditions[0][value]"]
        hits = [r for r in self.rows if r["recipient_state"] == state]
        lo = int(q["offset"])
        page = hits[lo : lo + int(q["limit"])]
        return 200, json.dumps({"results": page}).encode(), "application/json"


def _adapter(api: _Api) -> CMSOpenPayments:
    client = PoliteClient(transport=api, sleep=lambda s: None, now=lambda: AT)
    return CMSOpenPayments(client)


def test_partitions_are_year_state_and_offset_windows() -> None:
    parts = list(_adapter(_Api([])).partitions())
    assert parts == [
        {"year": "2024", "state": "WY", "offset": "0"},
        {"year": "2024", "state": "WY", "offset": str(WINDOW)},
        {"year": "2024", "state": "other", "offset": "0"},
        {"year": "2025", "state": "WY", "offset": "0"},
        {"year": "2025", "state": "WY", "offset": str(WINDOW)},
        {"year": "2025", "state": "other", "offset": "0"},
    ]


def test_fetch_pages_in_record_order_keeps_kept_columns_and_honors_limit() -> None:
    rows = [{**PHYSICIAN, "record_id": f"{i:010d}"} for i in range(3)]
    api = _Api(rows)
    fetched = _adapter(api).fetch(FetchRequest({"year": "2025", "state": "WY", "limit": "2"}))
    body = json.loads(fetched.content)
    assert [r["record_id"] for r in body["rows"]] == ["0000000000", "0000000001"]
    assert "contextual_information" not in body["rows"][0]
    assert "covered_recipient_name_suffix" not in body["rows"][0]  # empty values dropped
    q = api.queries[-1]
    assert (q["limit"], q["sorts[0][property]"], q["conditions[0][value]"]) == ("2", "record_id",
                                                                                "WY")  # fmt: skip
    assert fetched.request.endswith("#state=WY&offset=0")
    assert query_params("other", 0, 1)["conditions[0][value]"] == ""
    with pytest.raises(ValueError, match="bad state"):
        _adapter(api).fetch(FetchRequest({"year": "2025", "state": "wy"}))


def test_recorded_fixture_passes_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(CMSOpenPayments, sorted(FIXTURES.glob("*.json")), empty_db)
