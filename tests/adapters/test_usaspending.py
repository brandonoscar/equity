"""USAspending.gov award recipients (equity.adapters.federal.usaspending)."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

import duckdb
import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal import usaspending as u
from equity.adapters.federal.usaspending import (
    ASSISTANCE_COLUMNS,
    CONTRACT_COLUMNS,
    JsonClient,
    USASpendingRecipients,
)

from ..test_adapter_contract import ADAPTER_FIXTURES, check_contract
from ..test_fixture_privacy import _walk

AT = datetime(2026, 11, 25, tzinfo=UTC)


def award(**kw: Any) -> dict[str, Any]:
    base = {"file": "assistance", "recipient_uei": "AAAABBBBCCC1", "recipient_name": "ACME INC",
            "recipient_address_line_1": "1 MAIN ST", "recipient_city_name": "CASPER",
            "recipient_state_code": "WY", "recipient_zip_code": "82604",
            "prime_award_summary_recipient_county_fips_code": "56025", "record_type_code": "2",
            "total_obligated_amount": "100.00",
            "award_latest_action_date": "2024-01-02"}  # fmt: skip
    return {**base, **kw}


def normalize(rows: list[dict[str, Any]], **head: Any) -> list[tuple[str, dict[str, Any]]]:
    body = {"fy": 2024, "award_type": "grants", "state": "WY", "month": None, "rows": rows,
            **head}  # fmt: skip
    fetched = Fetched(u.USASpendingRecipients.source_id, "https://files.usaspending.gov/x.zip",
                      AT, 200, json.dumps(body).encode(), "application/json")  # fmt: skip
    return [(r.table, dict(r.row)) for r in USASpendingRecipients().normalize(fetched)]


def test_awards_group_into_one_record_per_recipient_and_redacted_rows_are_skipped() -> None:
    rows = [
        award(assistance_award_unique_key="A1"),
        award(assistance_award_unique_key="A2", total_obligated_amount="50.00",
              award_latest_action_date="2024-03-04", recipient_address_line_1="9 NEW ST",
              highly_compensated_officer_1_name="JANE DOE",
              recipient_parent_name="ACME HOLDINGS LLC", recipient_parent_uei="PPPPBBBBCCC1"),
        award(recipient_uei=None, recipient_name="REDACTED DUE TO PII", record_type_code="3"),
        award(recipient_uei=None, recipient_name="MULTIPLE RECIPIENTS", record_type_code="1"),
        award(recipient_uei=None, recipient_name="JOHN ROE", record_type_code="3"),
        award(recipient_uei=None, recipient_duns=None, recipient_name="NO ID LLC"),
    ]  # fmt: skip
    out = normalize(rows)
    srs = [r for t, r in out if t == "source_record"]
    keys = sorted(r["record_key"] for r in srs)
    assert len(keys) == 2 and keys[1] == "FY2024/grants/WY/UEI-AAAABBBBCCC1"
    assert keys[0].startswith("FY2024/grants/WY/H-")
    assert {r["record_type"] for r in srs} == {"federal_award_recipient"}
    names = sorted(r["raw_name"] for t, r in out if t == "party")
    assert names == ["ACME HOLDINGS LLC", "ACME INC", "JANE DOE", "NO ID LLC"]
    (acme,) = [r for t, r in out if t == "business" and r["name"] == "ACME INC"]
    assert acme["sos_id"] == "USAS:FY2024/grants/WY/UEI-AAAABBBBCCC1"
    assert (acme["valid_from"], acme["valid_to"]) == (date(2023, 10, 1), date(2024, 9, 30))
    assert acme["status_date"] == date(2024, 3, 4) and acme["jurisdiction"] == "56025"
    addrs = {r["address_id"]: r for t, r in out if t == "address"}
    assert addrs[acme["principal_address_id"]]["line1"] == "9 NEW ST"  # the latest award's
    roles = sorted((r["role"], r["title"]) for t, r in out if t == "business_role")
    assert roles == [("officer", "HIGHLY COMPENSATED OFFICER"), ("other", "PARENT RECIPIENT"),
                     ("other", "RECIPIENT"), ("other", "RECIPIENT")]  # fmt: skip
    assert not {"instrument", "judgment"} & {t for t, _ in out}


def test_contract_zip_and_same_entity_parent() -> None:
    rows = [award(file="contracts", recipient_zip_code=None, recipient_zip_4_code="820093315",
                  recipient_parent_name="ACME INC.",
                  recipient_parent_uei="AAAABBBBCCC1")]  # fmt: skip
    out = normalize(rows, award_type="contracts", month="2024-02")
    (biz,) = [r for t, r in out if t == "business"]
    assert biz["sos_id"] == "USAS:FY2024/contracts/WY/2024-02/UEI-AAAABBBBCCC1"
    assert (biz["valid_from"], biz["valid_to"]) == (date(2024, 2, 1), date(2024, 2, 29))
    assert [r["zip5"] for t, r in out if t == "address"] == ["82009"]
    assert [r["title"] for t, r in out if t == "business_role"] == ["RECIPIENT"]  # same entity


def test_windows_and_filters() -> None:
    assert u.fiscal_year(date(2026, 11, 25)) == 2027 and u.fiscal_year(date(2026, 9, 30)) == 2026
    assert u.window(2024) == (date(2023, 10, 1), date(2024, 9, 30))
    assert u.window(2024, "2023-12") == (date(2023, 12, 1), date(2023, 12, 31))
    with pytest.raises(ValueError, match="not in FY"):
        u.window(2024, "2024-10")
    assert u.months(2024)[0] == "2023-10" and u.months(2024)[-1] == "2024-09"
    f = u.filters(2024, "loans", "PR", "2024-01")
    assert f["time_period"] == [{"start_date": "2024-01-01", "end_date": "2024-01-31",
                                 "date_type": "new_awards_only"}]  # fmt: skip
    assert f["award_type_codes"] == ["07", "08", "F003", "F004"]
    assert f["recipient_locations"] == [{"country": "USA", "state": "PR"}]
    assert u.columns_for("idvs") == CONTRACT_COLUMNS
    assert u.columns_for("grants") == ASSISTANCE_COLUMNS


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Assistance_PrimeAwardSummaries_2026_1.csv",
                   "recipient_name,recipient_uei,total_obligated_amount,secret_column\n"
                   "ACME INC,AAAABBBBCCC1,10.00,x\nBETA LLC,BBBBBBBBCCC1,20.00,y\n")  # fmt: skip
        z.writestr("Assistance_Subawards_2026.csv", "subawardee_name\nSUB LLC\n")
    return buf.getvalue()


class _FakeApi:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.polls = 0

    def get(self, url: str, headers: Mapping[str, str], timeout: float
            ) -> tuple[int, bytes, str]:  # fmt: skip
        if url.endswith("/robots.txt"):
            return 404, b"", "text/plain"
        if url.startswith(u.STATUS):
            self.polls += 1
            status = "finished" if self.polls > 1 else "running"
            return 200, json.dumps({"status": status, "file_url": "https://f/x.zip"}).encode(), ""
        assert url == "https://f/x.zip"
        return 200, _zip(), "application/zip"

    def post(self, url: str, headers: Mapping[str, str], body: bytes, timeout: float
             ) -> tuple[int, bytes, str]:  # fmt: skip
        obj = json.loads(body)
        self.posts.append((url, obj))
        if url == u.COUNT:
            tp = obj["filters"]["time_period"][0]
            st = obj["filters"]["recipient_locations"][0]["state"]
            n = (5, u.SPLIT_AT + 1) if (tp["end_date"], st) == ("2024-09-30", "WY") else (0, 0)
            return 200, json.dumps({"results": {"grants": n[0], "contracts": n[1]}}).encode(), ""
        assert url == u.DOWNLOAD
        return 200, json.dumps({"file_name": "x.zip", "file_url": "https://f/x.zip"}).encode(), ""


def _adapter(api: _FakeApi, slept: list[float]) -> USASpendingRecipients:
    client = JsonClient(min_interval_s=0.0, transport=api.get, json_transport=api.post,
                        sleep=slept.append)  # fmt: skip
    return USASpendingRecipients(client)


def test_partitions_split_large_ones_by_month() -> None:
    api = _FakeApi()
    parts = list(_adapter(api, []).partitions())
    assert {"fy": "2024", "award_type": "grants", "state": "WY"} in parts
    monthly = [p for p in parts if p["award_type"] == "contracts"]
    assert [p["month"] for p in monthly] == u.months(2024)
    assert len(parts) == 13
    first, last = u.FIRST_FY, u.fiscal_year(datetime.now(UTC).date())
    assert len([p for p in api.posts if p[0] == u.COUNT]) == (last - first + 1) * len(u.STATES)


def test_fetch_waits_for_the_file_and_keeps_prime_award_rows() -> None:
    api = _FakeApi()
    slept: list[float] = []
    fetched = _adapter(api, slept).fetch(
        FetchRequest({"fy": "2024", "award_type": "grants", "state": "wy", "limit": "1"})
    )
    (url, req) = api.posts[-1]
    assert url == u.DOWNLOAD and req["limit"] == 1 and req["columns"] == list(ASSISTANCE_COLUMNS)
    assert slept == [u.POLL_S]  # one poll found it running
    data = json.loads(fetched.content)
    assert data["rows"] == [{"file": "assistance", "recipient_name": "ACME INC",
                             "recipient_uei": "AAAABBBBCCC1",
                             "total_obligated_amount": "10.00"}]  # fmt: skip
    assert fetched.request == "https://f/x.zip" and data["state"] == "WY"
    with pytest.raises(ValueError, match="award_type"):
        _adapter(api, slept).fetch(FetchRequest({"fy": "2024", "award_type": "x", "state": "WY"}))


def test_pii_fields_cover_recipient_names_officers_and_street_lines() -> None:
    pii = set(USASpendingRecipients.pii_fields)
    names = {c for c in u.COLUMNS if c.endswith(("_name", "_name_raw")) and "recipient" in c}
    names -= {"recipient_city_name", "recipient_county_name"}
    assert names <= pii
    assert set(u.OFFICERS) <= pii
    assert {"recipient_address_line_1", "recipient_address_line_2"} <= pii
    paths = sorted((ADAPTER_FIXTURES / USASpendingRecipients.source_id).glob("*.json"))
    assert len(paths) == 2
    for path in paths:
        assert _walk(json.loads(path.read_text()), USASpendingRecipients.pii_fields) == []


def test_recorded_fixtures_load(empty_db: duckdb.DuckDBPyConnection) -> None:
    files = sorted((ADAPTER_FIXTURES / USASpendingRecipients.source_id).glob("*.json"))
    check_contract(USASpendingRecipients, files, empty_db)
