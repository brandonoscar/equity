"""Hernando County (FL) daily Civil Data Index. Offline."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.fl.hernando_civil import (
    HernandoCivilFilings,
    file_key,
    load_config,
    parse_rows,
    us_date,
)
from equity.adapters.http import PoliteClient
from equity.adapters.registry import by_source_id
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 23, tzinfo=UTC)
FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "fl.hernando.civil.filings"
TEXT = (
    "SC|SMALL CLAIMS|26000500SCAXMX|SMALL CLAIMS $500-$2500|11/19/2026|OPEN|Plaintiff|"
    "Acme Funding LLC|1 Main St| |Tampa|FL|33602|JANE LAWYER\n"
    "SC|SMALL CLAIMS|26000500SCAXMX|SMALL CLAIMS $500-$2500|11/19/2026|OPEN|Defendant|"
    "Ann  B Doe|2 Oak Ave|Apt 3|Spring Hill|FL|34608-1234|\n"
    "SC|SMALL CLAIMS|26000500SCAXMX|SMALL CLAIMS $500-$2500|11/19/2026|OPEN|Defendant|"
    "Ann B Doe|2 Oak Ave|Apt 3|Spring Hill|FL|34608|\n"
    "SC|SMALL CLAIMS|26000500SCAXMX|SMALL CLAIMS $500-$2500|11/19/2026|OPEN|Third Party|"
    "Roe Co| | | | | |\n"
    "DR|DOMESTIC|26000600DRAXMX|DISSOLUTION|11/19/2026|OPEN|Petitioner|Pat Private|9 Elm|"
    " |Brooksville|FL|34601|\n"
    "CA|CIR CIVIL|26000700CAAXMX|AUTO NEGLIGENCE|12/19/2026|OPEN|Plaintiff|Sam Driver| | | |"
    " | |\n"
    "too|short\n"
)


def _norm(text: str = TEXT) -> list[tuple[str, dict[str, Any]]]:
    rows = parse_rows(text, load_config().case_type_codes)
    body = canonical_json({"file": "2026-11-20.csv", "rows": rows})
    f = Fetched(HernandoCivilFilings.source_id, "https://x.test/x", AT, 200, body, "")
    return [(r.table, dict(r.row)) for r in HernandoCivilFilings().normalize(f)]


def _of(out: list[tuple[str, dict[str, Any]]], table: str) -> list[dict[str, Any]]:
    return [r for t, r in out if t == table]


def test_helpers() -> None:
    assert us_date("11/19/2026") == date(2026, 11, 19)
    assert us_date("") is None and us_date("2026-11-19") is None and us_date("13/40/2026") is None
    rows = parse_rows(TEXT, load_config().case_type_codes)
    assert len(rows) == 5 and all(r["CaseTypeCode"] != "DR" for r in rows)
    assert "Address2" not in rows[0] and rows[1]["PartyName"] == "Ann B Doe"
    names = ["2026-01-02.csv", "Civil Data 2024-04-01 - 2024-07-11.csv", "2024-01-01.csv"]
    assert sorted(names, key=file_key) == [names[1], names[2], names[0]]


def test_normalize() -> None:
    out = _norm()
    cases = {c["case_uid"]: c for c in _of(out, "court_case")}
    assert set(cases) == {"fl.hernando:26000500SCAXMX", "fl.hernando:26000700CAAXMX"}
    sc = cases["fl.hernando:26000500SCAXMX"]
    assert sc["filed_on"] == date(2026, 11, 19) and sc["status"] == "OPEN"
    assert sc["nature_of_suit"] == "SMALL CLAIMS $500-$2500"
    assert cases["fl.hernando:26000700CAAXMX"]["filed_on"] is None  # after retrieval
    names = {p["party_id"]: p for p in _of(out, "party")}
    roles = sorted((names[c["party_id"]]["raw_name"], c["role"]) for c in _of(out, "case_party"))
    assert roles == [("Acme Funding LLC", "plaintiff"), ("Ann B Doe", "defendant"),
                     ("Roe Co", "other"), ("Sam Driver", "plaintiff")]  # fmt: skip
    doe = next(p for p in names.values() if p["raw_name"] == "Ann B Doe")
    addr = {a["address_id"]: a for a in _of(out, "address")}[doe["address_id"]]
    assert addr["zip5"] == "34608" and "APT 3" in addr["line1"]
    assert next(p for p in names.values() if p["raw_name"] == "Roe Co")["address_id"] is None


class FakeTransport:
    def __init__(self, pages: Mapping[str, tuple[int, str]]) -> None:
        self.pages = pages

    def __call__(
        self, url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes, str]:
        status, text = self.pages.get(url, (404, ""))
        return status, text.encode(), "text/plain"


SITE = "https://subscriber.hernandoclerk.com/"
PAGE = ('<a href="/data_files/civil_data/2026-11-20.csv">'
        '<a href="/data_files/civil_data/Civil Data 2024-04-01 - 2024-07-11.csv">'
        '<a href="/data_files/official_records/11-20-2026.csv">')  # fmt: skip


def _adapter(pages: Mapping[str, tuple[int, str]]) -> HernandoCivilFilings:
    client = PoliteClient(min_interval_s=0, retries=0, transport=FakeTransport(pages),
                          sleep=lambda _s: None, now=lambda: AT)  # fmt: skip
    return HernandoCivilFilings(client=client)


def test_fetch_partitions_health() -> None:
    day = SITE + "data_files/civil_data/2026-11-20.csv"
    a = _adapter({SITE: (200, PAGE), day: (200, TEXT)})
    assert [p["file"] for p in a.partitions()] == [
        "Civil Data 2024-04-01 - 2024-07-11.csv", "2026-11-20.csv"]  # fmt: skip
    f = a.fetch(FetchRequest({"file": "2026-11-20.csv", "limit": "2"}))
    assert len(json.loads(f.content)["rows"]) == 2 and f.request == day
    with pytest.raises(ValueError, match="not a civil data"):
        a.fetch(FetchRequest({"file": "../../etc.csv"}))
    report = a.health()
    assert report.ok and report.detail == "2026-11-20.csv: 5 rows"
    assert not _adapter({SITE: (200, "")}).health().ok
    assert not _adapter({SITE: (503, "")}).health().ok
    back = SITE + "data_files/civil_data/Civil%20Data%202024-04-01%20-%202024-07-11.csv"
    b = _adapter({SITE: (200, PAGE), back: (200, TEXT)})
    assert b.fetch(FetchRequest({"file": "Civil Data 2024-04-01 - 2024-07-11.csv"})).request == back


def test_scrub_and_fixture() -> None:
    body = canonical_json({"file": "x", "rows": parse_rows(TEXT, load_config().case_type_codes)})
    data = json.loads(HernandoCivilFilings.scrub_fixture(body))
    assert all(r["PartyName"].startswith("TESTOWNER") for r in data["rows"])
    assert data["rows"][1]["Address1"].endswith(" TEST ST")
    assert by_source_id("fl.hernando.civil.filings") is HernandoCivilFilings
    paths = sorted(FIX.glob("*.json"))
    assert paths
    for path in paths:
        for r in json.loads(path.read_text())["rows"]:
            assert r["CaseTypeCode"] in {"CA", "CC", "SC"}
            for col in ("PartyName", "Address1", "Address2", "PartyAttorney"):
                v = r.get(col, "")
                assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), col
