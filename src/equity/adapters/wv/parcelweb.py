"""Monongalia County Assessor "ParcelWeb": dated ownership history with sale price and deed
book/page (the county's sales-listing database).

Access: public HTML search, no login, no CAPTCHA, robots.txt absent (404, checked
2026-11-15). Results page via GET `SearchResult.aspx?datefromMin=..&datefromMax=..&pageno=N`,
20 rows per page. HTML is a last resort under the source-preference rule. If the Assessor
offers an export, it replaces this adapter. Requests are spaced 3 s apart.

Parcel key: ParcelWeb shows district / map / parcel, where parcel "X.Y" is IAS parcel X, suffix
Y. Map is zero-padded to 4, parcel and suffix to 4, sub-suffix assumed 0000. This convention
was checked against the IAS roll for several parcels. Parcels that exist only as GIS polygons
won't join, which fails safe.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterator, Mapping
from datetime import date, datetime
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlsplit

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.html_table import Row, tables
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.wv.parcel_ids import county_fips
from equity.config import source_params
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

BASE = "https://monongalia.wvassessor.com/parcelweb/SearchResult.aspx"
COUNTY_NUMBER = 31  # Monongalia
HEADER = ["District", "Map", "Parcel", "Owner", "Book", "Page", "Sale Price", "Date From",
          "Date Thru", "Area", "Acreage"]  # fmt: skip
_ROWS = re.compile(r"^(\d+)\s+Rows$")
_MONEY = re.compile(r"^\$?([\d,]+(?:\.\d{2})?)$")
# A results row: three leading cells, then the Owner cell (4th). Cells never nest tables here.
_OWNER_CELL = re.compile(r"(<tr[^>]*>\s*(?:<td[^>]*>.*?</td>\s*){3}<td[^>]*>)(.*?)(</td>)", re.S)
_VIEWSTATE = re.compile(
    r'(name="__(?:VIEWSTATE|EVENTVALIDATION|VIEWSTATEGENERATOR)"[^>]*?)value="[^"]*"'
)


class ParcelWebError(RuntimeError):
    pass


def ias_parid(district: int, map_: str, parcel: str) -> str:
    """'01', '13A', '69.1' -> '01' '013A' '0069' '0001' '0000' (18 chars)."""
    base, _, suffix = parcel.partition(".")
    if not base.isdigit() or (suffix and not suffix.isdigit()):
        raise ValueError(f"unexpected parcel number {parcel!r}")
    m = map_.strip().upper()
    if not m or len(m) > 4 or not m.isalnum():
        raise ValueError(f"unexpected map {map_!r}")
    return f"{district:02d}{m.rjust(4, '0')}{int(base):04d}{int(suffix or 0):04d}0000"


def _mdy(text: str) -> date | None:
    text = text.strip()
    if not text:
        return None
    return datetime.strptime(text, "%m/%d/%Y").date()  # noqa: DTZ007 - a calendar date


def _money(text: str) -> str | None:
    m = _MONEY.match(text.strip())
    return None if m is None else f"{float(m.group(1).replace(',', '')):.2f}"


def owner_text(cell: str) -> str:
    """Owner cell text without the trailing ' ,' separator the page appends."""
    return " ".join(cell.split()).rstrip(" ,")


def results_table(page_html: str) -> tuple[int, list[Row]]:
    for caption, rows in tables(page_html):
        m = _ROWS.match(caption)
        if m and rows and rows[0].cells == HEADER:
            return int(m.group(1)), rows[1:]
    if "No Records" in page_html or "no records" in page_html:
        return 0, []
    raise ParcelWebError("results table not found; the page layout may have changed")


class MonongaliaParcelWeb(Adapter):
    source_id: ClassVar[str] = "wv.monongalia.assessor.parcelweb"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "html"

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.params = source_params(self.source_id)
        self.client = client or PoliteClient(min_interval_s=float(self.params["min_interval_s"]))

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "assessor",
            "jurisdiction": county_fips(COUNTY_NUMBER),
            "access_method": "html",
            "base_url": BASE,
            "terms_url": "https://www.assessor.org/2204/Parcel-Database-Archives",
            "terms_summary": (
                "Public search, no login or CAPTCHA, no terms posted, robots.txt absent"
            ),
            "terms_checked_on": date(2026, 11, 15),
            "robots_checked_on": date(2026, 11, 15),
            "cost_model": "free",
        }

    def _page(self, date_min: str, date_max: str, page: int) -> str:
        resp = self.client.get(
            BASE, {"datefromMin": date_min, "datefromMax": date_max, "pageno": str(page)}
        )
        if resp.status != 200:
            raise ParcelWebError(f"HTTP {resp.status} for {resp.url}")
        return resp.content.decode("utf-8", errors="replace")

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: date_min, date_max (MM/DD/YYYY, ownership 'Date From' window);
        optional max_pages (fixtures)."""
        date_min, date_max = request.params["date_min"], request.params["date_max"]
        cap = int(request.params.get("max_pages", "100000"))
        first = self._page(date_min, date_max, 1)
        total, _ = results_table(first)
        per = int(self.params["rows_per_page"])
        pages = [first]
        n_pages = min(cap, max(1, -(-total // per)))
        for p in range(2, n_pages + 1):
            pages.append(self._page(date_min, date_max, p))
        query = {"datefromMin": date_min, "datefromMax": date_max}
        return Fetched(
            source_id=self.source_id,
            request=f"{BASE}?datefromMin={date_min}&datefromMax={date_max}",
            retrieved_at=self.client.now(),
            http_status=200,
            content=canonical_json({"query": query, "total": total, "pages": pages}),
            content_type="application/json",
        )

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        seen_slots: dict[tuple[str, str], int] = {}
        jurisdiction = county_fips(COUNTY_NUMBER)
        for page_no, page in enumerate(data["pages"], start=1):
            _, rows = results_table(page)
            for i, row in enumerate(rows):
                detail = [h for h in row.hrefs if "detailview.aspx" in h]
                if len(row.cells) != len(HEADER) or not detail:
                    continue
                cell = dict(zip(HEADER, row.cells, strict=True))
                q = parse_qs(urlsplit(html.unescape(detail[0])).query)
                district = int(q["district"][0])
                map_, parcel_txt = q["map"][0], q["parcel"][0]
                valid_from = _mdy(cell["Date From"])
                owner = owner_text(cell["Owner"])
                if valid_from is None or not owner:
                    continue
                parid = ias_parid(district, map_, parcel_txt)
                uid = f"{jurisdiction}-{parid}"
                slot_key = (uid, valid_from.isoformat())
                seq = seen_slots.get(slot_key, 0) + 1
                seen_slots[slot_key] = seq
                key = f"{district:02d}-{map_}-{parcel_txt}@{valid_from.isoformat()}#{seq}"
                ctx = RecordContext(
                    fetched, jurisdiction, key, "transfer",
                    {"page": page_no, "row": i, "cells": row.cells, "href": detail[0]},
                )  # fmt: skip
                yield ctx.source_record()
                yield ctx.fact(
                    "parcel",
                    parcel_uid=uid,
                    district=f"{district:02d}",
                    map=map_,
                    parcel_no=parcel_txt,
                    subparcel=None,
                    parid_raw=parid,
                )
                nc = classify(owner)
                party_id = stable_id(self.source_id, key, "owner", clean(owner))
                yield ctx.fact(
                    "party",
                    party_id=party_id,
                    raw_name=owner,
                    party_kind=nc.party_kind,
                    org_form=nc.org_form,
                    org_name_norm=nc.org_name_norm,
                )
                valid_to = _mdy(cell["Date Thru"])
                if valid_to is not None and valid_to < valid_from:
                    yield ctx.fact(
                        "data_issue",
                        issue_code="interval_inverted",
                        target_table="ownership_period",
                        detail={"date_from": cell["Date From"], "date_thru": cell["Date Thru"]},
                    )
                    continue
                yield ctx.fact(
                    "ownership_period",
                    parcel_uid=uid,
                    party_id=party_id,
                    owner_seq=seq,
                    deed_book=cell["Book"] or None,
                    deed_page=cell["Page"] or None,
                    sale_price=_money(cell["Sale Price"]),
                    valid_from=valid_from,
                    valid_to=valid_to,
                )

    def health(self) -> HealthReport:
        try:
            total, rows = results_table(self._page("01/01/2025", "01/07/2025", 1))
            ok = total > 0 and all(len(r.cells) == len(HEADER) for r in rows)
            detail = f"ok ({total} rows)" if ok else f"unexpected: total={total}"
        except (ParcelWebError, OSError) as exc:
            ok, detail = False, repr(exc)
        return HealthReport(self.source_id, ok, self.client.now(), detail, tuple(HEADER))

    @staticmethod
    def scrub_fixture(content: bytes) -> bytes:
        """Replace every Owner cell in raw HTML with a pseudonym (public repo), and drop
        ASP.NET view state, which can carry the same names in base64."""
        from equity.adapters.record import pseudonym

        def repl(m: re.Match[str]) -> str:
            name = owner_text(html.unescape(m.group(2)))
            return m.group(1) + (pseudonym("Owner", name) if name else "") + m.group(3)

        data = json.loads(content)
        pages = []
        for page in data["pages"]:
            page = _OWNER_CELL.sub(repl, page)
            page = _VIEWSTATE.sub(r'\1value="SCRUBBED"', page)
            pages.append(page)
        data["pages"] = pages
        return canonical_json(data)
