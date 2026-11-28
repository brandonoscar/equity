"""Alabama DOR transcripts of State-held tax-delinquent land: row parsing and parcel keys."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

from equity.adapters.al_dor_transcripts import (
    AlabamaStateHeldTaxLand,
    county_parcel,
    owner_name,
    transcript_rows,
)
from equity.adapters.base import Fetched
from equity.adapters.pdf_table import Text

AT = datetime(2026, 11, 28, tzinfo=UTC)
HEAD = [(18.0, "Name "), (161.8, "Amt Bid at Tax Sale "), (243.0, "CO."), (265.5, "YR."),
        (283.5, "C/S#"), (328.5, "CLASS"), (359.4, "CODE"), (387.0, "PARCEL ID "),
        (477.0, "DESCRIPTION")]  # fmt: skip


def _line(page: int, y: float, runs: list[tuple[float, str]]) -> list[Text]:
    return [Text(x, y, s, page) for x, s in runs]


def _record(page: int, y: float, name: str, yr: str, cs: str, parcel: str) -> list[Text]:
    return _line(page, y, [(18.0, name), (243.0, "05"), (265.5, yr), (283.5, cs),
                           (328.5, "2"), (374.8, "08"), (387.0, parcel),
                           (477.0, "LOT 169 CYPRESS PARK")])  # fmt: skip


def test_rows_take_the_amount_from_the_next_line_even_across_a_page_break() -> None:
    title = "STATE OF ALABAMA-DEPARTMENT OF REVENUE"
    texts = (_line(0, 568.6, [(222.4, title), (697.5, "11/06/2026")])
             + _line(0, 496.6, HEAD)
             + _record(0, 484.2, "HARRIS RICKIE L", "02", "05020231", "0566030820000840010000")
             + _line(0, 475.2, [(189.4, "52.17")])
             + _record(0, 461.6, "SMITH DIANN", "02", "05020527", "0523052200000100050000")
             + _line(0, 453.5, [(477.0, "FOR POB TH RUN S 65', E 65'")])
             + _line(1, 568.6, [(222.4, title)])
             + _line(1, 496.6, HEAD)
             + _line(1, 484.2, [(187.4, "1,148")])
             + _record(1, 470.0, "NEW SALE LLC", "26", "05260001",
                       "0523051610010380000000"))  # fmt: skip
    rows = transcript_rows(texts)
    assert [(r["name"], r.get("amount")) for r in rows] == [
        ("HARRIS RICKIE L", "52.17"), ("SMITH DIANN", "1148"), ("NEW SALE LLC", None)]  # fmt: skip
    assert rows[0]["parcel"] == "0566030820000840010000"


def test_county_parcel_keys() -> None:
    assert county_parcel("01", "0122001410300030000000") == "2200141030003000"  # Jefferson
    assert county_parcel("68", "6829003020250050000000") == "2900302025005000"  # Bessemer
    assert county_parcel("38", "381004183011015003") == "1004183011015003"  # Houston
    assert county_parcel("02", "0229061300021840000000") == "2906130002184.000"  # Mobile
    assert county_parcel("05", "0566030820000840010000") == "05-66-03-08-2-000-084.001"
    assert county_parcel("47", "471702102004042000") == "17-02-10-2-004-042.000"  # Madison
    assert county_parcel("03", "0411") is None
    assert county_parcel("03", "0511062420220070000000") is None  # another county's code


def test_owner_name_cleanup() -> None:
    assert (
        owner_name("RICK LEON WAYNE & MARY BETH % KENDAL POWELL") == "RICK LEON WAYNE & MARY BETH"
    )
    assert owner_name("HOLMES BESSIE LEE &") == "HOLMES BESSIE LEE"
    assert owner_name("JACKSON MILDRED C/O CAV HCS ATTN: DOUGLAS") == "JACKSON MILDRED"
    assert owner_name("EDWARDS ROBERT J OR MARY E %") == "EDWARDS ROBERT J OR MARY E"


def test_normalize_one_state_certificate_per_record() -> None:
    rows = [{"name": "HARRIS RICKIE L", "co": "05", "yr": "02", "cs": "05020231", "class": "2",
             "code": "08", "parcel": "0566030820000840010000", "legal": "LOT 169",
             "amount": "52.17"},
            {"name": "OLD OWNER", "co": "05", "yr": "88", "cs": "05880001", "class": "2",
             "code": "08", "parcel": "0566030820000840020000", "legal": "", "amount": "9"},
            {"name": "NEW SALE LLC", "co": "05", "yr": "26", "cs": "05260001", "class": "2",
             "code": "08", "parcel": "0566030820000840030000", "legal": ""},
            {"name": "WRONG COUNTY", "co": "01", "yr": "02", "cs": "01020001", "class": "2",
             "code": "08", "parcel": "0123", "legal": "", "amount": "1.00"}]  # fmt: skip
    a = AlabamaStateHeldTaxLand()
    fetched = Fetched(a.source_id, "u", AT, 200,
                      json.dumps({"code": "05", "as_of": "11/06/2026", "rows": rows}).encode(),
                      "application/json")  # fmt: skip
    out = [(t.table, dict(t.row)) for t in a.normalize(fetched)]
    inst = {x["instrument_number"]: x for t, x in out if t == "instrument"}
    assert sorted(inst) == ["05020231", "05260001", "05880001"]
    assert (inst["05020231"]["recorded_on"], inst["05020231"]["principal_amount"]) == (
        date(2002, 1, 1), Decimal("52.17"))  # fmt: skip
    assert inst["05880001"]["recorded_on"] == date(1988, 1, 1)
    assert inst["05260001"]["principal_amount"] is None
    assert "Baldwin County" in inst["05020231"]["doc_type_raw"]
    assert {x["parcel_uid"] for t, x in out if t == "instrument_parcel"} >= {
        "01003-05-66-03-08-2-000-084.001"}  # fmt: skip
