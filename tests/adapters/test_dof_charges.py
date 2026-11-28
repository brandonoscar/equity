"""NYC DOF past-due property charges: one instrument per lot and charge code, on the lot."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import PoliteClient
from equity.adapters.ny.dof_charges import NYCPastDueCharges, lot_uid

AT = datetime(2025, 12, 31, tzinfo=UTC)


def test_lot_uid() -> None:
    assert lot_uid("1000010010") == "36061-6201001000010010"
    assert lot_uid("5034040077") == "36085-6401005034040077"
    assert lot_uid("6000010010") is None and lot_uid("1000000010") is None
    assert lot_uid("10000100") is None


def test_normalize_sums_per_lot_and_code() -> None:
    rows = [
        {"parid": "3000010001", "code": "CHG", "balance": "1200.50", "first_due": "2024-01-01"},
        {"parid": "3000010001", "code": "SAC", "balance": "75", "first_due": "2025-07-01"},
        {"parid": "3000010002", "code": "CHG", "balance": "0", "first_due": "2025-01-01"},  # paid
        {"parid": "bad", "code": "CHG", "balance": "5", "first_due": "2025-01-01"},
    ]  # fmt: skip
    body = json.dumps({"borough": "3", "extract": "2025-11-15", "rows": rows}).encode()
    out = [(r.table, dict(r.row)) for r in NYCPastDueCharges().normalize(
        Fetched("ny.nyc.dof.past_due_charges", "x", AT, 200, body, ""))]  # fmt: skip
    inst = {r["instrument_number"]: r for t, r in out if t == "instrument"}
    assert set(inst) == {"3000010001-CHG", "3000010001-SAC"}
    chg = inst["3000010001-CHG"]
    assert (str(chg["principal_amount"]), chg["recorded_on"], chg["doc_type"]) == (
        "1200.50",
        date(2024, 1, 1),
        "TAX_LIEN_STATE",
    )
    assert "property tax" in chg["doc_type_raw"] and "2025-11-15" in chg["doc_type_raw"]
    lots = {r["parcel_uid"] for t, r in out if t == "instrument_parcel"}
    assert lots == {"36047-6101003000010001"}
    assert {r["role"] for t, r in out if t == "instrument_party"} == {"creditor"}


def test_fetch_reads_only_the_latest_snapshot_past_due() -> None:
    seen: list[str] = []

    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        seen.append(url)
        if "max%28extractdt%29" in url:
            return 200, b'[{"m": "2025-11-15T00:00:00.000"}]', ""
        return 200, b'[{"parid": "5000010010", "code": "CHG", "balance": "9"}]', ""

    a = NYCPastDueCharges(PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None))
    f = a.fetch(FetchRequest({"borough": "5", "limit": "10"}))
    assert json.loads(f.content)["extract"] == "2025-11-15"
    q = seen[-1]
    assert "extractdt+%3D+%272025-11-15" in q and "starts_with%28parid%2C+%275%27%29" in q
    assert "%24group=parid%2C+code" in q
    with pytest.raises(ValueError, match="bad borough"):
        a.where("9", "2025-11-15T00:00:00.000", date(2025, 12, 31))
