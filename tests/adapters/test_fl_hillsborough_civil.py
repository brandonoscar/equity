"""Hillsborough civil files: cases, daily filings, garnishment. Offline."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.fl.hillsborough_civil import (
    HillsboroughCivilCases,
    HillsboroughCivilFilings,
    HillsboroughGarnishment,
    case_uid,
    read_csv,
    split_style,
    us_date,
    write_csv,
)
from equity.adapters.http import Response
from equity.adapters.rows import canonical_json

FIX = Path(__file__).parents[1] / "fixtures" / "adapters"
AT = datetime(2026, 11, 16, tzinfo=UTC)


def _norm(cls: type, rows: list[dict[str, str]]) -> list[tuple[str, dict[str, Any]]]:
    body = canonical_json({"file": "f.csv", "csv": write_csv(rows, list(rows[0]))})
    f = Fetched(cls.source_id, "https://x.test/f.csv", AT, 200, body, "")
    return [(r.table, dict(r.row)) for r in cls().normalize(f)]


def _fixture(cls: type) -> list[tuple[str, dict[str, Any]]]:
    path = next((FIX / cls.source_id).resolve().glob("*.json"))
    f = Fetched(cls.source_id, path.as_uri(), AT, 200, path.read_bytes(), "")
    return [(r.table, dict(r.row)) for r in cls().normalize(f)]


def test_helpers() -> None:
    assert us_date("10/01/2026") == date(2026, 10, 1)
    assert us_date("11/28/2006 12:00:00 AM") == date(2006, 11, 28)
    assert us_date("2006-12-20") is None and us_date("") is None and us_date("13/40/2026") is None
    assert split_style("Smith, Ann vs Acme LLC et al") == ("Smith, Ann", "Acme LLC")
    assert split_style("A VS. B") == ("A", "B")
    assert split_style("In re Estate of X") == (None, None)
    assert case_uid(" 26-ca-010627 ") == "fl.hillsborough:26-CA-010627"
    assert read_csv("﻿A,B\n 1 ,\n") == [{"A": "1", "B": ""}]


def test_cases_fixture_and_judgments() -> None:
    rows = _fixture(HillsboroughCivilCases)
    t = Counter(table for table, _ in rows)
    assert t["court_case"] == t["source_record"] > 0
    assert {r["role"] for tb, r in rows if tb == "case_party"} == {"plaintiff", "defendant"}
    base = {"CaseNbr": "26-CC-1", "Style": "BANK NA vs DOE, JOHN", "CaseType": "SC Debt",
            "Division": "A", "DtFile": "10/01/2026", "Judge": "J", "CauseOfAction": "",
            "CauseDescription": "", "CaseStatus": "Closed"}  # fmt: skip
    out = _norm(HillsboroughCivilCases, [
        {**base, "JudgmentCode": "DJ", "JudgmentDescription": "DEFAULT JUDGMENT",
         "JudgmentDate": "10/20/2026"},
        {**base, "CaseNbr": "26-CC-2", "JudgmentCode": "JFP",
         "JudgmentDescription": "JUDGMENT FOR POSSESSION", "JudgmentDate": "10/20/2026"},
        {**base, "CaseNbr": "26-CC-3", "DtFile": "01/01/2027", "JudgmentCode": "FJ",
         "JudgmentDescription": "FINAL JUDGMENT", "JudgmentDate": "01/02/2027"},
    ])  # fmt: skip
    j = [r for tb, r in out if tb == "judgment"]
    assert [(r["case_uid"], r["judgment_type"]) for r in j] == [
        ("fl.hillsborough:26-CC-1", "default")
    ]
    assert j[0]["judgment_uid"] == "fl.hillsborough:26-CC-1:DJ:2026-10-20"
    future = next(r for tb, r in out if tb == "court_case" and r["case_number_norm"] == "26-CC-3")
    assert future["filed_on"] is None


def test_filings_parties_with_addresses() -> None:
    rows = _fixture(HillsboroughCivilFilings)
    assert Counter(tb for tb, _ in rows)["case_party"] > 0
    base = {"CaseCategory": "CV", "CaseTypeDescription": "Debt", "CaseNumber": "26-CC-9",
            "Title": "A vs B", "FilingDate": "10/19/2026", "MiddleName": "",
            "Attorney": ""}  # fmt: skip
    out = _norm(HillsboroughCivilFilings, [
        {**base, "PartyType": "Plaintiff", "FirstName": "", "LastName/CompanyName": "ACME LLC",
         "PartyAddress": "1 MAIN ST, TAMPA, FL 33602"},
        {**base, "PartyType": "Defendant", "FirstName": "JOHN", "LastName/CompanyName": "DOE",
         "PartyAddress": "2 OAK AVE APT 3, TAMPA, FL 33629"},
        {**base, "PartyType": "Defendant", "FirstName": "JOHN", "LastName/CompanyName": "DOE",
         "PartyAddress": "2 OAK AVE APT 3, TAMPA, FL 33629"},
        {**base, "PartyType": "Interested Party", "FirstName": "X", "LastName/CompanyName": "Y",
         "PartyAddress": ""},
    ])  # fmt: skip
    roles = sorted(r["role"] for tb, r in out if tb == "case_party")
    assert roles == ["defendant", "other", "plaintiff"]
    zips = {r["zip5"] for tb, r in out if tb == "address"}
    assert zips == {"33602", "33629"}
    names = {r["raw_name"] for tb, r in out if tb == "party"}
    assert names == {"ACME LLC", "JOHN DOE", "X Y"}
    assert [r["filed_on"] for tb, r in out if tb == "court_case"] == [date(2026, 10, 19)]


def test_garnishment_parties_and_writ_dates() -> None:
    rows = _fixture(HillsboroughGarnishment)
    roles = Counter(r["role"] for tb, r in rows if tb == "case_party")
    assert roles["defendant"] > 0 and roles["plaintiff"] > 0
    assert any(
        r["text"].startswith("WRIT OF GARNISHMENT") for tb, r in rows if tb == "docket_entry"
    )
    base = {"CaseNbr": "06-CC-032306", "DtFile": "11/28/2006 12:00:00 AM",
            "PlaintiffName": "BANK NA", "DefendantName": "DOE, ANN", "Address1": "3 PINE RD",
            "Address2": "", "Address3": "", "City": "PLANT CITY", "State": "FL", "ZIP": "33565-1",
            "CaseTypeDesc": "Accounts", "CaseStatDesc": "Reopened", "Pre_Trial_Date": "",
            "Service_Return_Date": "", "Return_of_Non_Service_Date": "",
            "Date_Writ_of_Garnishment_filed": "8/20/2026 12:00:00 AM",
            "Date_Writ_of_Garnishment_Issued": "8/25/2026 12:00:00 AM"}  # fmt: skip
    out = _norm(HillsboroughGarnishment, [
        {**base, "GarnisheeName": "EMPLOYER INC"},
        {**base, "GarnisheeName": "CREDIT UNION"},
        {**base, "GarnisheeName": "", "Date_Writ_of_Garnishment_filed": "1/1/2027 12:00:00 AM",
         "Date_Writ_of_Garnishment_Issued": ""},
    ])  # fmt: skip
    t = Counter(tb for tb, _ in out)
    assert t["court_case"] == 1
    roles = sorted((r["role"]) for tb, r in out if tb == "case_party")
    assert roles == ["defendant", "garnishee", "garnishee", "plaintiff"]
    debtor = next(r for tb, r in out if tb == "party" and r["raw_name"] == "DOE, ANN")
    addr = next(r for tb, r in out if tb == "address")
    assert debtor["address_id"] == addr["address_id"] and addr["zip5"] == "33565"
    entries = sorted((r["entry_date"].isoformat(), r["text"]) for tb, r in out
                     if tb == "docket_entry")  # fmt: skip
    assert entries == [
        ("2026-08-20", "WRIT OF GARNISHMENT FILED: CREDIT UNION"),
        ("2026-08-20", "WRIT OF GARNISHMENT FILED: EMPLOYER INC"),
        ("2026-08-25", "WRIT OF GARNISHMENT ISSUED: CREDIT UNION"),
        ("2026-08-25", "WRIT OF GARNISHMENT ISSUED: EMPLOYER INC"),
    ]  # the 2027 date is after retrieval: dropped
    assert HillsboroughGarnishment.single_store and HillsboroughCivilFilings.single_store


class FakeFolder:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        from urllib.parse import unquote

        name = unquote(url.rsplit("/", 1)[-1])
        body = self.files.get(name)
        return Response(url, 200 if body is not None else 404, body or b"", "text/csv", AT)


def test_listing_fetch_limit_scrub_and_health() -> None:
    listing = (b'<a href="/Civil/bulkdata/Bulk%20Data%20Case%20File_%2002-10-2026.csv">'
               b"Bulk Data Case File_ 02-10-2026.csv</a> Bulk Data Case File_ 12-10-2025.csv "
               b"Bulk Data Event File_ 02-10-2026.csv")  # fmt: skip
    csv_text = b"CaseNbr,Style\n26-CA-1,REAL PERSON vs OTHER PERSON\n26-CA-2,A vs B\n"
    fake = FakeFolder({"": listing, "Bulk Data Case File_ 02-10-2026.csv": csv_text})
    a = HillsboroughCivilCases(fake)  # type: ignore[arg-type]
    assert [p["file"] for p in a.partitions()] == [
        "Bulk Data Case File_ 12-10-2025.csv",
        "Bulk Data Case File_ 02-10-2026.csv",
    ]  # oldest first, by the date in the name
    f = a.fetch(FetchRequest({"file": "Bulk Data Case File_ 02-10-2026.csv", "limit": "1"}))
    assert read_csv(json.loads(f.content)["csv"]) == [
        {"CaseNbr": "26-CA-1", "Style": "REAL PERSON vs OTHER PERSON"}
    ]
    scrubbed = json.loads(HillsboroughCivilCases.scrub_fixture(f.content))["csv"]
    assert "REAL PERSON" not in scrubbed and scrubbed.count("TESTOWNER") == 2
    with pytest.raises(ValueError, match="not a"):
        a.fetch(FetchRequest({"file": "../etc/passwd"}))
    with pytest.raises(RuntimeError, match="HTTP 404"):
        a.fetch(FetchRequest({"file": "Bulk Data Case File_ 03-10-2026.csv"}))
    assert a.health().ok
    assert not HillsboroughCivilCases(FakeFolder({"": b"nothing"})).health().ok  # type: ignore[arg-type]
    assert not HillsboroughCivilCases(FakeFolder({})).health().ok  # type: ignore[arg-type]
    assert a.source_row()["kind"] == "court"
