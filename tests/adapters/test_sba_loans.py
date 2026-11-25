"""Every SBA loan as a borrower record (equity.adapters.federal.sba_loans)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import duckdb

from equity.adapters.base import Fetched, FetchRequest, NormalizedRow
from equity.adapters.federal.sba_loans import (
    PPP_KEEP,
    SBA_KEEP,
    WINDOW,
    SBA7a504Loans,
    SBAPPPLoans,
    parse_window,
)
from equity.adapters.person_lists import RangeClient

from ..test_adapter_contract import ADAPTER_FIXTURES, check_contract
from ..test_fixture_privacy import _walk

AT = datetime(2026, 11, 25, tzinfo=UTC)
PPP_HEAD = (
    "LoanNumber,DateApproved,BorrowerName,BorrowerAddress,BorrowerCity,BorrowerState,"
    "BorrowerZip,LoanStatusDate,LoanStatus,CurrentApprovalAmount,ForgivenessAmount,"
    "ServicingLenderName,ServicingLenderAddress,ServicingLenderCity,ServicingLenderState,"
    "ServicingLenderZip,OriginatingLender,OriginatingLenderCity,OriginatingLenderState,"
    "ProjectCountyName,ProjectState,NAICSCode,JobsReported,Race,Gender\n"
)
PPP_BODY = (
    PPP_HEAD + "1,04/30/2020,ACME LLC,1 MAIN ST,Richmond,VA,23226-1,11/20/2021,Paid in Full,84207,"
    '84207,Celtic Bank,"268 S State St, Ste 300",Salt Lake City,UT,84111,Celtic Bank,'
    "Salt Lake City,UT,HENRICO,VA,713910,40,White,Male Owned\n"
    + "2,05/01/2020,BETA INC,2 MAIN ST,Richmond,VA,23226,,Exemption 4,100,,Truist Bank,,,,,"
    "First Bank,Raleigh,NC,HENRICO,VA,,,,\n"
    + "3,04/30/2020,Exemption 6,,,,,11/20/2021,Charged Off,500,,Lender,,,,,,,,,,,,,\n"
)


def _windows(body: str) -> tuple[list[str], list[dict[str, object]], int]:
    data = body.encode()
    return parse_window(data, data, 0, len(data), 0, True, PPP_KEEP)


def _rows(
    adapter: SBAPPPLoans | SBA7a504Loans, rows: list[dict[str, object]]
) -> list[tuple[str, dict[str, object]]]:
    fetched = Fetched(adapter.source_id, "https://x/f.csv#bytes=0-9", AT, 200,
                      json.dumps({"rows": rows}).encode(), "application/json")  # fmt: skip
    out: list[NormalizedRow] = list(adapter.normalize(fetched))
    return [(r.table, dict(r.row)) for r in out]


def test_every_ppp_loan_is_a_borrower_record_not_a_debt() -> None:
    header, rows, bad = _windows(PPP_BODY)
    assert bad == 0 and header[0] == "LoanNumber"
    assert [r["LoanNumber"] for r in rows] == ["1", "2", "3"]  # every status is kept
    assert "Race" not in rows[0] and "Gender" not in rows[0]  # demographics are not kept
    out = _rows(SBAPPPLoans(), rows)
    tables = {t for t, _ in out}
    assert "instrument" not in tables and "instrument_party" not in tables
    biz = sorted((r for t, r in out if t == "business"), key=lambda r: str(r["sos_id"]))
    assert [b["sos_id"] for b in biz] == ["SBA-PPP-1", "SBA-PPP-2"]  # Exemption 6: skipped
    assert biz[0]["status"] == "Paid in Full" and str(biz[0]["valid_from"]) == "2020-04-30"
    assert str(biz[0]["status_date"]) == "2021-11-20" and biz[1]["status_date"] is None
    assert biz[0]["jurisdiction"] == "51087"  # Henrico County
    roles = sorted((r["sos_id"], r["title"]) for t, r in out if t == "business_role")
    assert roles == [("SBA-PPP-1", "BORROWER"), ("SBA-PPP-1", "SERVICING LENDER"),
                     ("SBA-PPP-2", "BORROWER"), ("SBA-PPP-2", "ORIGINATING LENDER"),
                     ("SBA-PPP-2", "SERVICING LENDER")]  # fmt: skip
    parties = {str(r["raw_name"]): r for t, r in out if t == "party"}
    addrs = {r["address_id"]: r for t, r in out if t == "address"}
    acme = addrs[parties["ACME LLC"]["address_id"]]
    assert (acme["line1"], acme["zip5"]) == ("1 MAIN ST", "23226")
    assert addrs[parties["Celtic Bank"]["address_id"]]["zip5"] == "84111"
    assert addrs[parties["First Bank"]["address_id"]]["city"] == "RALEIGH"
    srs = [r for t, r in out if t == "source_record"]
    assert {r["record_type"] for r in srs} == {"ppp_loan"} and len(srs) == 2


def test_window_takes_lines_starting_inside_it_and_counts_split_lines() -> None:
    data = PPP_BODY.encode()
    second = data.index(b"\n2,") + 1
    third = data.index(b"\n3,") + 1
    _, rows, _ = parse_window(data, data, 0, second, 0, False, PPP_KEEP)
    assert [r["LoanNumber"] for r in rows] == ["1"]
    _, rows, _ = parse_window(data, data[second - 1 :], second, third, second - 1, True,
                              PPP_KEEP)  # fmt: skip
    assert [r["LoanNumber"] for r in rows] == ["2"]
    broken = PPP_HEAD + '1,04/30/2020,"ACME\n'
    _, rows, bad = _windows(broken)
    assert rows == [] and bad == 1


SBA_HEAD = (
    '"Program","LocationID","BorrName","BorrStreet","BorrCity","BorrState","BorrZip",'
    '"BankName","BankStreet","BankCity","BankState","BankZip","CDC_Name","CDC_Street",'
    '"CDC_City","CDC_State","CDC_Zip","ThirdPartyLender_Name","ThirdPartyLender_City",'
    '"ThirdPartyLender_State","GrossApproval","ApprovalDate","ProjectCounty","ProjectState",'
    '"LoanStatus","PaidInFullDate","ChargeOffDate","GrossChargeOffAmount"\n'
)
SBA_BODY = (
    SBA_HEAD + '" 7A","1","Rambler LLC","10 Knoll Cir","LITTLETON","CO","80130","Sunflower Bank",'
    '"8117 Preston Rd","Dallas","TX","75225",,,,,,,,,"1188000.0","2019-10-01","DOUGLAS",'
    '"CO","P I F","2021-08-31",,"0.0"\n'
    + '" 7A","1","Rambler LLC","10 Knoll Cir","LITTLETON","CO","80130","Sunflower Bank",'
    '"8117 Preston Rd","Dallas","TX","75225",,,,,,,,,"1188000.0","2019-10-01","DOUGLAS",'
    '"CO","P I F","2021-08-31",,"0.0"\n'
    + '"504","2","Martin PC","3 E Ramona Ave","Colorado Springs","CO","80905",,,,,,'
    '"Pikes Peak CDC","322 S Cascade Ave","Colorado Springs","CO","80903","JPMorgan Chase",'
    '"Columbus","OH","127000.0","2009-10-02","EL PASO","CO","CHGOFF",,"2015-03-01","9000.0"\n'
)


def test_every_7a_and_504_loan_is_a_borrower_record() -> None:
    data = SBA_BODY.encode()
    _, rows, bad = parse_window(data, data, 0, len(data), 0, True, SBA_KEEP)
    assert bad == 0 and len(rows) == 3
    out = _rows(SBA7a504Loans(), rows)
    assert "instrument" not in {t for t, _ in out}
    biz = [r for t, r in out if t == "business"]
    assert len({b["sos_id"] for b in biz}) == 3  # identical rows are numbered, not merged
    by_prog = {str(b["sos_id"]).split("-")[1]: b for b in biz}
    assert by_prog["504"]["status"] == "CHGOFF" and str(by_prog["504"]["status_date"]) == (
        "2015-03-01")  # fmt: skip
    assert by_prog["504"]["jurisdiction"] == "08041"  # El Paso County, CO
    assert by_prog["7A"]["jurisdiction"] == "08035"  # Douglas County, CO
    assert all("Rambler" not in str(b["record_key"]) for b in biz)  # names only in the hash
    titles = sorted({str(r["title"]) for t, r in out if t == "business_role"})
    assert titles == ["BORROWER", "CDC", "LENDER", "THIRD PARTY LENDER"]
    types = sorted({str(r["record_type"]) for t, r in out if t == "source_record"})
    assert types == ["sba_504_loan", "sba_7a_loan"]


def test_pii_fields_cover_borrower_names_and_street_lines() -> None:
    assert {"BorrowerName", "BorrowerAddress"} <= set(SBAPPPLoans.pii_fields)
    assert {"BorrName", "BorrStreet"} <= set(SBA7a504Loans.pii_fields)
    for cls in (SBAPPPLoans, SBA7a504Loans):
        assert set(cls.pii_fields) <= set(cls.keep)
        paths = sorted((ADAPTER_FIXTURES / cls.source_id).glob("*.json"))
        assert paths, cls.source_id
        for path in paths:
            data = json.loads(path.read_text())
            assert _walk(data, cls.pii_fields) == [], path.name
            assert len(data["rows"]) == 25


class _FakeNet:
    """A dataset page linking one file of `size` bytes, served with byte ranges."""

    def __init__(self, page: str, url: str, body: bytes) -> None:
        self.page, self.url, self.body = page, url, body
        self.ranges: list[str] = []

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                 ) -> tuple[int, bytes, str]:  # fmt: skip
        if url.endswith("/robots.txt"):
            return 404, b"", "text/plain"
        if url == self.page:
            return 200, f'<a href="{self.url}">csv</a>'.encode(), "text/html"
        assert url == self.url
        rng = headers["Range"]
        self.ranges.append(rng)
        lo, hi = (int(x) for x in rng.removeprefix("bytes=").split("-"))
        if lo >= len(self.body):
            return 416, b"", "text/plain"
        return 206, self.body[lo : hi + 1], "text/csv"


def _client(net: _FakeNet) -> RangeClient:
    return RangeClient(min_interval_s=0.0, transport=net, sleep=lambda s: None)


def test_partitions_are_byte_windows_of_each_file_and_fetch_honors_limit() -> None:
    url = "https://data.sba.gov/sites/default/files/x/public_up_to_150k_1_240930.csv"
    body = PPP_BODY.encode()
    net = _FakeNet(SBAPPPLoans.page, url, body)

    class OneFile(SBAPPPLoans):
        files: ClassVar[Mapping[str, str]] = {"up_to_150k_1": SBAPPPLoans.files["up_to_150k_1"]}

    adapter = OneFile(_client(net))
    parts = list(adapter.partitions())
    assert parts == [{"file": "up_to_150k_1", "url": url, "lo": "0", "hi": str(WINDOW)}]
    fetched = adapter.fetch(FetchRequest({**parts[0], "limit": "2"}))
    data = json.loads(fetched.content)
    assert [r["LoanNumber"] for r in data["rows"]] == ["1", "2"]
    assert fetched.request == f"{url}#bytes=0-{WINDOW - 1}"
    assert net.ranges[-1] == f"bytes=0-{WINDOW + 65_536 - 1}"  # never the whole file


def test_recorded_fixtures_load(empty_db: duckdb.DuckDBPyConnection) -> None:
    for cls in (SBAPPPLoans, SBA7a504Loans):
        files: list[Path] = sorted((ADAPTER_FIXTURES / cls.source_id).glob("*.json"))
        check_contract(cls, files, empty_db)
