from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.ecf_rss import (
    NDWVBankruptcyRSS,
    NDWVDistrictRSS,
    caption_parties,
    parse_case,
)
from equity.adapters.http import PoliteClient

FIX = Path(__file__).parents[1] / "fixtures/adapters"
AT = datetime(2026, 11, 15, 20, tzinfo=UTC)


def rows(cls, content: bytes) -> list[tuple[str, dict[str, Any]]]:  # type: ignore[no-untyped-def]
    f = Fetched(cls.source_id, "fixture://rss", AT, 200, content, "text/xml")
    return [(r.table, dict(r.row)) for r in cls().normalize(f)]


def test_bankruptcy_fixture() -> None:
    content = (FIX / "us.wvnb.rss/feed.xml").read_bytes()
    out = rows(NDWVBankruptcyRSS, content)
    counts = Counter(t for t, _ in out)
    assert counts["docket_entry"] == counts["source_record"] == content.count(b"<item>")
    cases = [r for t, r in out if t == "court_case"]
    assert all(r["court_id"] == "wvnb" for r in cases)
    assert {r["case_type"] for r in cases} <= {"bk", "ap"}  # cases and adversary proceedings
    assert any(r["nature_of_suit"] == "chapter 7" for r in cases)
    roles = Counter(r["role"] for t, r in out if t == "case_party")
    assert roles["trustee"] >= 1
    assert roles["debtor"] >= 1
    entry = next(r for t, r in out if t == "docket_entry")
    assert entry["entry_date"] == date(2026, 11, 15)
    assert entry["text"].startswith("[")


def test_district_fixture() -> None:
    out = rows(NDWVDistrictRSS, (FIX / "us.wvnd.rss/feed.xml").read_bytes())
    cases = {r["case_uid"] for t, r in out if t == "court_case"}
    assert cases == {"wvnd:1:26-cv-00066", "wvnd:1:25-cv-00052"}
    entries = [r for t, r in out if t == "docket_entry"]
    assert sorted(r["entry_no"] for r in entries) == [34, 90, 91]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("1:25-bk-00040 Doe, Jane", ("1", "25", "bk", "40", "Doe, Jane")),
        ("5:26-cv-00725-JPB Acme LLC v. Roe", ("5", "26", "cv", "725", "Acme LLC v. Roe")),
        ("1:26-ap-00001", ("1", "26", "ap", "1", "")),
        ("26-31038- Doe, Jane", ("0", "26", "bk", "31038", "Doe, Jane")),
        ("26-55830-pwb Roe LLC", ("0", "26", "bk", "55830", "Roe LLC")),
        ("26-05199-pwb Lincoln v. Roe", ("0", "26", "ap", "5199", "Lincoln v. Roe")),
        ("26-35279-mvl7 Doe", ("0", "26", "bk", "35279", "Doe")),
        ("26-23147 Doe", ("0", "26", "bk", "23147", "Doe")),
        ("not a case", None),
    ],
)
def test_parse_case(title: str, expected: tuple[str, ...] | None) -> None:
    assert parse_case(title, bankruptcy_court=True) == expected


def test_untyped_numbers_outside_bankruptcy_are_civil() -> None:
    assert parse_case("26-00012 Acme v. Roe") == ("0", "26", "cv", "12", "Acme v. Roe")


@pytest.mark.parametrize(
    ("ctype", "caption", "expected"),
    [
        ("bk", "Doe, Jane and Doe, John", [("Doe, Jane", "debtor"), ("Doe, John", "debtor")]),
        ("cv", "Acme LLC v. Roe", [("Acme LLC", "plaintiff"), ("Roe", "defendant")]),
        ("cv", "In re Something", [("In re Something", "other")]),
        ("cv", "", []),
    ],
)
def test_caption_parties(ctype: str, caption: str, expected: list[tuple[str, str]]) -> None:
    assert caption_parties(ctype, caption) == expected


FEED = """<?xml version="1.0"?><rss><channel><title>x</title>
<item><title>1:26-cr-00001 USA v. Someone</title><pubDate>Sun, 15 Nov 2026 10:00:00 GMT</pubDate>
<description>[Indictment] ( 1 )</description></item>
<item><title>garbage</title><pubDate>Sun, 15 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>1:26-bk-00009 Doe, Pat</title><pubDate>Sun, 15 Nov 2026 11:00:00 GMT</pubDate>
<description>Type: bk Office: 1 Chapter: 7 Trustee: Roe, Sam [Voluntary Petition (Chapter 7)]
 &lt;a href="x"&gt;1&lt;/a&gt;</description></item>
<item><title>1:26-bk-00009 Doe, Pat</title><pubDate>Sun, 15 Nov 2026 12:00:00 GMT</pubDate>
<description>Type: bk Office: 1 Chapter: 7 [Meeting of Creditors]</description></item>
<item><title>1:26-bk-00009 Doe, Pat</title><pubDate>Sun, 15 Nov 2026 12:00:00 GMT</pubDate>
<description>Type: bk Office: 1 Chapter: 7 [Meeting of Creditors]</description></item>
</channel></rss>"""


def test_skips_criminal_and_garbage_and_dedupes_cases() -> None:
    out = rows(NDWVBankruptcyRSS, FEED.encode())
    assert [r["case_uid"] for t, r in out if t == "court_case"] == ["wvnb:1:26-bk-00009"]
    entries = [r for t, r in out if t == "docket_entry"]
    assert [(e["entry_no"], e["text"]) for e in entries] == [
        (1, "[Voluntary Petition (Chapter 7)]"),
        (None, "[Meeting of Creditors]"),
        (None, "[Meeting of Creditors]"),
    ]
    keys = [r["record_key"] for t, r in out if t == "source_record"]
    assert len(keys) == len(set(keys)) == 3
    assert "Someone" not in str(out)


def test_rss_without_channel() -> None:
    with pytest.raises(ValueError, match="no channel"):
        rows(NDWVBankruptcyRSS, b"<rss></rss>")


def test_scrub_fixture() -> None:
    scrubbed = NDWVBankruptcyRSS.scrub_fixture(FEED.encode()).decode()
    assert "Doe, Pat" not in scrubbed
    assert "Roe, Sam" not in scrubbed
    assert "1:26-bk-00009 TESTOWNER" in scrubbed


def client(body: bytes, status: int = 200) -> PoliteClient:
    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        return (404, b"", "") if url.endswith("robots.txt") else (status, body, "text/xml")

    return PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None, now=lambda: AT)


def test_fetch_and_health() -> None:
    f = NDWVBankruptcyRSS(client(FEED.encode())).fetch(FetchRequest())
    assert f.content == FEED.encode()
    assert f.request == "https://ecf.wvnb.uscourts.gov/cgi-bin/rss_outside.pl"
    assert NDWVBankruptcyRSS(client(FEED.encode())).health().ok
    assert not NDWVDistrictRSS(client(b"not xml")).health().ok
    down = NDWVDistrictRSS(client(b"<html>Internal Server Error</html>", status=500))
    assert (down.health().ok, down.health().detail) == (False, "status=500")
    with pytest.raises(RuntimeError, match="HTTP 500"):  # an error page is not an empty feed
        down.fetch(FetchRequest())
    assert NDWVDistrictRSS().source_row()["kind"] == "court"
    assert NDWVBankruptcyRSS().source_row()["kind"] == "bankruptcy"


def test_dashed_office_year_number_titles_parse() -> None:
    """Western New York writes '2-26-20862- Name' (office-year-number, no type)."""
    from equity.adapters.federal.ecf_rss import parse_case

    assert parse_case("2-26-20862- Ann T. Lee and Bo L. Lee   ", bankruptcy_court=True) == (
        "2", "26", "bk", "20862", "Ann T. Lee and Bo L. Lee")  # fmt: skip
    assert parse_case("1-26-00055- Acme LLC v. Cy Dee", bankruptcy_court=True)[2:4] == (
        "ap", "55")  # fmt: skip
    assert parse_case("12-26-20862- X", bankruptcy_court=True) is None  # not that form
    assert parse_case("2:26-bk-12345 Foo") == ("2", "26", "bk", "12345", "Foo")  # unchanged
