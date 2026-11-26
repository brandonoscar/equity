"""FHFA ZIP5 house price index: the stdlib .xlsx reader, header lookup, rows and facts."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.fhfa_hpi import (
    FhfaHpiZip5,
    XlsxError,
    _col,
    parse_zip5,
    xlsx_rows,
)
from equity.adapters.http import PoliteClient

FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "us.fhfa.hpi_zip5" / "limit-40.json"
NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def _xlsx(rows: list[list[tuple[str, str]]], strings: list[str]) -> bytes:
    """A minimal workbook: rows of (cell ref, value) where a value 's:N' is shared string N."""
    sheet = [f"<worksheet {NS}><sheetData>"]
    for i, row in enumerate(rows, start=1):
        cells = []
        for ref, v in row:
            if v.startswith("s:"):
                cells.append(f'<c r="{ref}{i}" t="s"><v>{v[2:]}</v></c>')
            elif v.startswith("i:"):
                cells.append(f'<c r="{ref}{i}" t="inlineStr"><is><t>{v[2:]}</t></is></c>')
            elif v == "":
                cells.append(f'<c r="{ref}{i}"/>')
            else:
                cells.append(f'<c r="{ref}{i}"><v>{v}</v></c>')
        sheet.append(f'<row r="{i}">{"".join(cells)}</row>')
    sheet.append("</sheetData></worksheet>")
    sst = f"<sst {NS}>" + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", "".join(sheet))
        z.writestr("xl/sharedStrings.xml", sst)
    return buf.getvalue()


HEAD = ["Five-Digit ZIP Code", "Year", "Annual Change (%)", "HPI", "HPI with 1990 base",
        "HPI with 2000 base", "Title"]  # fmt: skip


def _book() -> bytes:
    return _xlsx([
        [("A", "s:6")],                                         # title row
        [],                                                     # empty row
        [("A", "s:0"), ("B", "s:1"), ("C", "s:2"), ("D", "s:3"), ("E", "s:4"), ("F", "s:5")],
        [("A", "1001"), ("B", "1984"), ("C", "i:."), ("D", "100"), ("E", "52.3"),
         ("F", "51.39")],
        [("A", "i:99901"), ("B", "2025"), ("C", "-6.25"), ("D", "382.33"), ("F", "251.67")],
        [("A", "i:note"), ("B", "")],                           # a footnote: skipped
    ], HEAD)  # fmt: skip


def test_col_and_reader() -> None:
    assert (_col("A1"), _col("C12"), _col("AA3")) == (0, 2, 26)
    rows = list(xlsx_rows(_book()))
    assert rows[0] == ["Title"] and rows[1] == []
    assert rows[3][:2] == ["1001", "1984"] and rows[3][2] == "."


def test_parse_zip5_finds_columns_by_header() -> None:
    got = list(parse_zip5(_book()))
    assert got == [
        {"zip5": "01001", "year": 1984, "annual_change_pct": None, "index_value": 100.0,
         "index_1990_base": 52.3, "index_2000_base": 51.39},
        {"zip5": "99901", "year": 2025, "annual_change_pct": -6.25, "index_value": 382.33,
         "index_1990_base": None, "index_2000_base": 251.67},
    ]  # fmt: skip
    with pytest.raises(XlsxError, match="no header row"):
        list(parse_zip5(_xlsx([[("A", "s:0")]], HEAD)))


def test_fixture_rows_become_index_facts() -> None:
    f = Fetched("us.fhfa.hpi_zip5", "x", datetime(2026, 11, 25, tzinfo=UTC), 200,
                FIX.read_bytes(), "application/json")  # fmt: skip
    out = [(r.table, dict(r.row)) for r in FhfaHpiZip5().normalize(f)]
    facts = [r for t, r in out if t == "house_price_index"]
    assert len(facts) == 40 and {r["geo_level"] for r in facts} == {"zip5"}
    assert all(r["period"] == 0 and len(r["geo_id"]) == 5 for r in facts)
    body = json.dumps({"rows": [{"zip5": "01001", "year": 2000, "index_value": 1.0},
                                {"zip5": "01001", "year": 2000, "index_value": 2.0},
                                {"zip5": "1001", "year": 2000},
                                {"zip5": "01001", "year": "2000"}]}).encode()  # fmt: skip
    dup = [r for r in FhfaHpiZip5().normalize(Fetched("x", "x", f.retrieved_at, 200, body, ""))
           if r.table == "house_price_index"]  # fmt: skip
    assert len(dup) == 1 and dup[0].row["index_value"] == 1.0


def test_fetch_limit_health_and_errors() -> None:
    book = _book()
    status = [200]

    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        return status[0], book, "application/vnd.openxmlformats-officedocument.spreadsheetml"

    a = FhfaHpiZip5(PoliteClient(min_interval_s=0, retries=0, transport=transport,
                                 sleep=lambda s: None))  # fmt: skip
    assert list(a.partitions()) == [{}]
    assert a.source_row()["kind"] == "price_index"
    assert len(json.loads(a.fetch(FetchRequest({"limit": "1"})).content)["rows"]) == 1
    h = a.health()
    assert not h.ok and h.detail == "2 ZIP-years"
    status[0] = 503
    with pytest.raises(RuntimeError, match="HTTP 503"):
        a.fetch(FetchRequest({}))
