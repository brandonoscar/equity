from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.html_table import tables
from equity.adapters.http import PoliteClient
from equity.adapters.rows import canonical_json
from equity.adapters.wv.parcelweb import (
    HEADER,
    MonongaliaParcelWeb,
    ParcelWebError,
    _money,
    ias_parid,
    results_table,
)

FIXTURE = next(
    (Path(__file__).parents[1] / "fixtures/adapters/wv.monongalia.assessor.parcelweb").glob(
        "*.json"
    )
)
AT = datetime(2026, 11, 15, 12, tzinfo=UTC)


def rows(content: bytes) -> list[tuple[str, dict[str, Any]]]:
    f = Fetched(MonongaliaParcelWeb.source_id, "fixture://pw", AT, 200, content, "application/json")
    return [(r.table, dict(r.row)) for r in MonongaliaParcelWeb().normalize(f)]


def test_fixture_rows() -> None:
    out = rows(FIXTURE.read_bytes())
    counts = Counter(t for t, _ in out)
    assert counts["party"] == counts["source_record"] == 40
    # 14 rows in this sample end before they start (a clerical pattern on one deed).
    assert counts["data_issue"] == 14
    assert counts["ownership_period"] == 26
    periods = [r for t, r in out if t == "ownership_period"]
    assert all(date(2025, 3, 1) <= r["valid_from"] <= date(2025, 3, 31) for r in periods)
    assert all(r["parcel_uid"].startswith("54061-") for r in periods)
    assert all(len(r["parcel_uid"]) == len("54061-") + 18 for r in periods)
    assert any(r["sale_price"] not in (None, "0.00") for r in periods)
    parties = [r for t, r in out if t == "party"]
    assert all(r["raw_name"].startswith("TESTOWNER") for r in parties)  # scrubbed fixture


def test_joint_owners_get_sequential_slots() -> None:
    periods = [r for t, r in rows(FIXTURE.read_bytes()) if t == "ownership_period"]
    slots = Counter((r["parcel_uid"], r["valid_from"]) for r in periods)
    multi = [k for k, n in slots.items() if n > 1]
    assert multi, "fixture should include a parcel with more than one owner row"
    seqs = sorted(r["owner_seq"] for r in periods if (r["parcel_uid"], r["valid_from"]) == multi[0])
    assert seqs == list(range(1, len(seqs) + 1))


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((1, "13", "20"), "010013002000000000"),
        ((4, "08", "1.12"), "040008000100120000"),
        ((3, "12A", "3"), "03012A000300000000"),
        ((5, "07B", "31.3"), "05007B003100030000"),
    ],
)
def test_ias_parid(args: tuple[int, str, str], expected: str) -> None:
    assert ias_parid(*args) == expected


@pytest.mark.parametrize(
    ("map_", "parcel"), [("13", "2x"), ("13", "1.a"), ("", "1"), ("12345", "1")]
)
def test_ias_parid_rejects(map_: str, parcel: str) -> None:
    with pytest.raises(ValueError, match="unexpected"):
        ias_parid(1, map_, parcel)


@pytest.mark.parametrize(
    ("text", "out"),
    [
        ("$100,000.00", "100000.00"),
        ("$0.00", "0.00"),
        ("1500", "1500.00"),
        ("", None),
        ("n/a", None),
    ],
)
def test_money(text: str, out: str | None) -> None:
    assert _money(text) == out


def _page(total: int, body_rows: list[list[str]]) -> str:
    head = "".join(f"<th>{h}</th>" for h in HEADER)
    trs = "".join(
        "<tr>" + f"<td>{r[0]}</td>" + f"<td><a href='maps/{r[1]}.tif'>{r[1]}</a></td>"
        + (f'<td><a href="detailview.aspx?district=1&amp;map=13&amp;parcel={r[2]}">{r[2]}</a></td>'
           if len(r) > 2 else "")
        + "".join(f"<td>{c}</td>" for c in r[3:]) + "</tr>"
        for r in body_rows
    )  # fmt: skip
    return (f'<input name="__VIEWSTATE" value="abc"/><table><caption>{total} Rows</caption>'
            f"<tr>{head}</tr>{trs}</table>")  # fmt: skip


ROW = ["Battelle", "13", "20", "Smith, Pat , ", "100", "1", "$5.00", "03/02/2025", "", "", "1.0"]


def test_results_table_and_layout_change() -> None:
    total, body = results_table(_page(3, [ROW]))
    assert total == 3
    assert body[0].cells[3] == "Smith, Pat ,"
    assert results_table("<p>No Records Found</p>") == (0, [])
    with pytest.raises(ParcelWebError, match="layout"):
        results_table("<table><caption>3 Rows</caption><tr><th>Other</th></tr></table>")


def test_inverted_interval_becomes_a_data_issue() -> None:
    inverted = [*ROW[:7], "03/02/2025", "02/01/2025", *ROW[9:]]
    content = canonical_json({"query": {}, "total": 1, "pages": [_page(1, [inverted])]})
    out = rows(content)
    assert [t for t, _ in out if t in ("ownership_period", "data_issue")] == ["data_issue"]
    issue = next(r for t, r in out if t == "data_issue")
    assert issue["issue_code"] == "interval_inverted"
    assert issue["detail"] == {"date_from": "03/02/2025", "date_thru": "02/01/2025"}


def test_normalize_skips_incomplete_rows() -> None:
    bad_date = [*ROW[:7], "", *ROW[8:]]
    no_owner = [*ROW[:3], "", *ROW[4:]]
    short = ROW[:5]
    content = canonical_json({"query": {}, "total": 4,
                              "pages": [_page(4, [ROW, bad_date, no_owner, short])]})  # fmt: skip
    periods = [r for t, r in rows(content) if t == "ownership_period"]
    assert len(periods) == 1
    assert periods[0]["sale_price"] == "5.00"
    assert periods[0]["valid_to"] is None
    names = [r["raw_name"] for t, r in rows(content) if t == "party"]
    assert names == ["Smith, Pat"]


def test_scrub_replaces_names_and_view_state() -> None:
    content = canonical_json({"query": {}, "total": 1, "pages": [_page(1, [ROW])]})
    scrubbed = json.loads(MonongaliaParcelWeb.scrub_fixture(content))["pages"][0]
    assert "Smith, Pat" not in scrubbed
    assert "TESTOWNER" in scrubbed
    assert 'value="SCRUBBED"' in scrubbed


def fake_client(pages: Mapping[int, str], status: int = 200) -> tuple[PoliteClient, list[str]]:
    calls: list[str] = []

    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("/robots.txt"):
            return 404, b"", ""
        calls.append(url)
        n = int(url.rsplit("pageno=", 1)[1].split("&")[0])
        return status, pages.get(n, "").encode(), "text/html"

    client = PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None,
                          now=lambda: AT)  # fmt: skip
    return client, calls


def test_fetch_pages_through_total_and_respects_cap() -> None:
    pages = {1: _page(45, [ROW]), 2: _page(45, [ROW]), 3: _page(45, [ROW])}
    client, calls = fake_client(pages)
    f = MonongaliaParcelWeb(client).fetch(FetchRequest({"date_min": "03/01/2025",
                                                        "date_max": "03/31/2025"}))  # fmt: skip
    assert len(json.loads(f.content)["pages"]) == 3
    assert len(calls) == 3
    client, calls = fake_client(pages)
    MonongaliaParcelWeb(client).fetch(
        FetchRequest({"date_min": "03/01/2025", "date_max": "03/31/2025", "max_pages": "2"})
    )
    assert len(calls) == 2
    client, _ = fake_client(pages, status=500)
    with pytest.raises(ParcelWebError, match="HTTP 500"):
        MonongaliaParcelWeb(client).fetch(FetchRequest({"date_min": "a", "date_max": "b"}))


def test_health() -> None:
    client, _ = fake_client({1: _page(5, [ROW])})
    assert MonongaliaParcelWeb(client).health().ok
    client, _ = fake_client({1: "<table><caption>9 Rows</caption><tr><th>x</th></tr></table>"})
    report = MonongaliaParcelWeb(client).health()
    assert not report.ok
    assert "layout" in report.detail


def test_html_table_parser_ignores_nested_tables() -> None:
    doc = ("<table><caption> 2  Rows </caption><tr><th>A</th></tr>"
           "<tr><td>x <table><tr><td>inner</td></tr></table></td></tr></table>")  # fmt: skip
    ((caption, trs),) = tables(doc)
    assert caption == "2 Rows"
    assert [r.cells for r in trs] == [["A"], ["x"]]
    assert trs[0].header
