"""FHFA House Price Index, five-digit ZIP code annual series (public domain, free, no login).

FHFA publishes the developmental annual ZIP5 HPI (all-transactions) at
www.fhfa.gov/hpi/download/annual/hpi_at_zip5.csv. Despite the .csv name it is an Excel
workbook: one sheet, about 690,000 rows of ZIP, year, annual change (%) and the index on its
own base, a 1990 base and a 2000 base. robots.txt restricts only one named crawler.

An index value rolls an old assessed or sale value forward: value_now = value_then x
HPI(zip, latest year) / HPI(zip, year of the value). This adapter only loads the index
(house_price_index, geo_level 'zip5', period 0 = annual); using it in equity estimates is a
separate, owner-approved step.

The workbook is read with the standard library (an .xlsx file is zipped XML): shared strings
plus the first sheet, streamed. Columns are found by their header text, not position, so a
reordered sheet still loads, and a missing column fails loudly.
"""

from __future__ import annotations

import io
import json
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json

URL = "https://www.fhfa.gov/hpi/download/annual/hpi_at_zip5.csv"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
HEADERS = {
    "Five-Digit ZIP Code": "zip5",
    "Year": "year",
    "Annual Change (%)": "annual_change_pct",
    "HPI": "index_value",
    "HPI with 1990 base": "index_1990_base",
    "HPI with 2000 base": "index_2000_base",
}


class XlsxError(ValueError):
    pass


def _col(ref: str) -> int:
    """'C12' -> 2 (zero-based column)."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def xlsx_rows(content: bytes) -> Iterator[list[str]]:
    """Every row of the first sheet as a list of cell strings (gaps filled with '')."""
    z = zipfile.ZipFile(io.BytesIO(content))
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{NS}si"):  # noqa: S314
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    with z.open("xl/worksheets/sheet1.xml") as sheet:
        for _, el in ET.iterparse(sheet):  # noqa: S314 - a federal agency's workbook
            if el.tag != f"{NS}row":
                continue
            cells: dict[int, str] = {}
            for c in el.iter(f"{NS}c"):
                v = c.find(f"{NS}v")
                text = v.text if v is not None and v.text is not None else ""
                if c.get("t") == "s" and text:
                    text = shared[int(text)]
                elif c.get("t") == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter(f"{NS}t"))
                cells[_col(c.get("r") or "A")] = text.strip()
            yield [cells.get(i, "") for i in range(max(cells) + 1)] if cells else []
            el.clear()


def _num(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None


def parse_zip5(content: bytes) -> Iterator[dict[str, Any]]:
    """Data rows as {zip5, year, annual_change_pct, index_value, index_1990_base,
    index_2000_base}, after the header row (the first row naming every HEADERS column)."""
    cols: dict[str, int] | None = None
    for row in xlsx_rows(content):
        if cols is None:
            names = {" ".join(c.split()): i for i, c in enumerate(row)}
            if all(h in names for h in HEADERS):
                cols = {key: names[h] for h, key in HEADERS.items()}
            continue
        get = {k: (row[i] if i < len(row) else "") for k, i in cols.items()}
        z, y = get["zip5"].split(".")[0], get["year"].split(".")[0]
        if not (z.isdigit() and y.isdigit()):
            continue
        yield {"zip5": z.zfill(5), "year": int(y),
               **{k: _num(get[k]) for k in ("annual_change_pct", "index_value",
                                            "index_1990_base", "index_2000_base")}}  # fmt: skip
    if cols is None:
        raise XlsxError(f"no header row with {sorted(HEADERS)}")


class FhfaHpiZip5(Adapter):
    source_id: ClassVar[str] = "us.fhfa.hpi_zip5"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=600.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "price_index",
            "jurisdiction": "US",
            "access_method": "bulk",
            "base_url": URL,
            "terms_url": "https://www.fhfa.gov/data/hpi/datasets",
            "terms_summary": (
                "FHFA House Price Index datasets: a U.S. government work, free, no login. "
                "The annual ZIP5 indexes are labelled developmental. robots.txt restricts only "
                "one named crawler."
            ),
            "terms_checked_on": "2026-11-25",
            "robots_checked_on": "2026-11-25",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {}

    def fetch(self, request: FetchRequest) -> Fetched:
        resp = self.client.get(URL)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status}")
        rows = list(parse_zip5(resp.content))
        limit = request.params.get("limit")
        if limit:
            rows = rows[: int(limit)]
        return Fetched(self.source_id, URL, resp.retrieved_at, 200,
                       canonical_json({"rows": rows}), "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        seen: set[str] = set()
        for r in json.loads(fetched.content).get("rows") or []:
            z, y = str(r.get("zip5") or ""), r.get("year")
            if not (len(z) == 5 and z.isdigit() and isinstance(y, int)):
                continue
            key = f"{z}-{y}"
            if key in seen:
                continue
            seen.add(key)
            ctx = RecordContext(fetched, "US", key, "hpi_row", r)
            yield ctx.source_record()
            yield ctx.fact("house_price_index", geo_level="zip5", geo_id=z, year=y, period=0,
                           index_value=r.get("index_value"),
                           index_1990_base=r.get("index_1990_base"),
                           index_2000_base=r.get("index_2000_base"),
                           annual_change_pct=r.get("annual_change_pct"))  # fmt: skip

    def health(self) -> HealthReport:
        n = len(json.loads(self.fetch(FetchRequest({})).content)["rows"])
        return HealthReport(self.source_id, n > 100_000, datetime.now(UTC), f"{n} ZIP-years")
