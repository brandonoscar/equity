"""Travis County delinquent tax accounts: a tax lien, or a tax-suit judgment once sued."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import PoliteClient
from equity.adapters.tx_travis_delinquent import TravisTaxDelinquent

AT = datetime(2026, 11, 23, tzinfo=UTC)


def _row(**kw: str) -> dict[str, str]:
    base = {"Account #": "0100", "Last Tax Roll Year ": "2026", "Delinquent Total": "25",
            "1st Year Delinquent": "2024", "Cause #": "", "Judgement Date": "",
            "Owner Name": "ANN LEE", "Address 1": "", "Address 2": "1 TEST ST",
            "Address 3": "", "City": "AUSTIN", "State": "TX", "Zip Code": "787041234"}  # fmt: skip
    return {**base, **kw}


def _out(rows: list[dict[str, str]]) -> list[tuple[str, dict[str, object]]]:
    f = Fetched("tx.travis.tax_delinquent", "x", AT, 200, json.dumps({"rows": rows}).encode(),
                "application/json")  # fmt: skip
    return [(r.table, dict(r.row)) for r in TravisTaxDelinquent().normalize(f)]


def test_liens_and_tax_suit_judgments() -> None:
    rows = [_row(), _row(),  # the same account twice is one instrument
            _row(**{"Account #": "0200", "Cause #": "GN21006856",
                    "Judgement Date": "4/27/2026 0:00", "Delinquent Total": "12,996.01"}),
            _row(**{"Account #": "0300", "Delinquent Total": "0"}),
            _row(**{"Account #": "0400", "1st Year Delinquent": ""}),
            _row(**{"Account #": "0500", "Cause #": "GN1", "Judgement Date": "bad",
                    "1st Year Delinquent": "2019"})]  # fmt: skip
    out = _out(rows)
    inst = {r["instrument_number"]: r for t, r in out if t == "instrument"}
    assert set(inst) == {"0100", "GN21006856", "0500"}  # no amount / no date: skipped
    assert (inst["0100"]["doc_type"], inst["0100"]["recorded_on"]) == (
        "TAX_LIEN_STATE", date(2024, 1, 1))  # fmt: skip
    sued = inst["GN21006856"]
    assert (sued["doc_type"], sued["recorded_on"], sued["principal_amount"]) == (
        "COURT_ORDER", date(2026, 4, 27), Decimal("12996.01"))  # fmt: skip
    assert inst["0500"]["doc_type"] == "TAX_LIEN_STATE"  # an unreadable judgment date
    addrs = [r for t, r in out if t == "address"]
    assert {(a["line1"], a["city"], a["zip5"]) for a in addrs} == {("1 TEST ST", "AUSTIN", "78704")}
    assert {r["role"] for t, r in out if t == "instrument_party"} == {"debtor"}
    assert not [r for t, r in out if t == "instrument_parcel"]


def test_fetch_and_health() -> None:
    body = "﻿Account #,Owner Name,Delinquent Total\n01,A B,5\n02,C D,6\n".encode()

    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        return 200, body, "text/csv"

    a = TravisTaxDelinquent(PoliteClient(min_interval_s=0, transport=transport,
                                         sleep=lambda s: None))  # fmt: skip
    assert list(a.partitions()) == [{}]
    assert a.source_row()["jurisdiction"] == "48453"
    rows = json.loads(a.fetch(FetchRequest({"limit": "1"})).content)["rows"]
    assert rows == [{"Account #": "01", "Owner Name": "A B", "Delinquent Total": "5"}]
    h = a.health()
    assert not h.ok and "2 accounts" in h.detail


def test_http_error() -> None:
    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        return (404, b"", "") if url.endswith("robots.txt") else (503, b"", "")

    a = TravisTaxDelinquent(PoliteClient(min_interval_s=0, transport=transport, retries=0,
                                         sleep=lambda s: None))  # fmt: skip
    with pytest.raises(RuntimeError, match="HTTP 503"):
        a.fetch(FetchRequest({}))
