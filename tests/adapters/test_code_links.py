"""Municipal code links: publisher from the ordinance host, links only."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from equity.adapters.base import Fetched
from equity.adapters.code_links import NJMunicipalCodeLinks, publisher_of


def test_publisher_of() -> None:
    assert publisher_of("https://ecode360.com/35938632") == "ecode360"
    assert publisher_of("https://library.municode.com/nj/x") == "municode"
    assert publisher_of("https://codelibrary.amlegal.com/codes/x") == "amlegal"
    assert publisher_of("https://www.townofx.nj.gov/zoning.pdf") == "government"
    assert publisher_of(None) is None
    assert publisher_of("") is None


def test_normalize_keeps_links_and_skips_rows_without_a_code() -> None:
    body = {"attributes": [
        {"Muni": "0503", "Municipali": "Cape May Point Borough", "County_1": "Cape May",
         "Map": "https://ecode360.com/a.pdf", "Ordinance": "https://ecode360.com/1",
         "Website": "not a url"},
        {"Muni": "", "Municipali": "No Code"},
    ]}  # fmt: skip
    f = Fetched("nj.dca.code_links", "x", datetime(2026, 11, 20, tzinfo=UTC), 200,
                json.dumps(body).encode(), "")  # fmt: skip
    rows = [r.row for r in NJMunicipalCodeLinks().normalize(f) if r.table == "code_link"]
    assert len(rows) == 1
    r = rows[0]
    assert (r["jurisdiction_uid"], r["publisher"], r["website_url"], r["jurisdiction"]) == (
        "NJ-0503", "ecode360", None, "34")  # fmt: skip
