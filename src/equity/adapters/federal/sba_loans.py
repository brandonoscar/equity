"""Every SBA loan as a borrower record: all PPP loans, and all 7(a) and 504 loans, from SBA's
FOIA loan files.

The charge-off sources (equity.adapters.federal.sba_ppp, sba_chargeoffs) keep only the loans
that went bad, as debts. These sources keep every loan, whatever its status (approved,
disbursed, paid in full, forgiven, cancelled, charged off), because a loan names a borrower at
a street address on a stated day, with its lender. A loan here is not a debt to us: no
instrument row is written; the amounts, status and loan terms stay in the raw record.

Rows, with existing tables only:

  source_record  the loan row (record_type ppp_loan | sba_7a_loan | sba_504_loan), with its
                 amounts (approval, forgiveness, guaranty, charge-off), status, NAICS code,
                 jobs and lender ids, exactly as the file prints them
  business       the borrower as a business on this loan: sos_id SBA-PPP-<LoanNumber> or
                 SBA-7A-/SBA-504-<record key>, status = the loan status, status_date = the
                 status (or paid-in-full / charge-off) date, principal address = the borrower's
                 street address, valid from the approval date
  party          the borrower (with its address) and each lender as printed (servicing and
                 originating lender for PPP; the bank for 7(a); the Certified Development
                 Company and the third-party lender for 504), each with the lender's address
                 where the file gives one
  business_role  borrower and lenders -> the loan's business row: role 'other', title
                 BORROWER, SERVICING LENDER, ORIGINATING LENDER, LENDER, CDC or THIRD PARTY
                 LENDER
  address        normalized borrower and lender addresses

Borrower names SBA withheld under FOIA Exemption 6 (individuals and sole proprietors) are not
loaded, as in the charge-off sources. Demographic columns (race, ethnicity, gender, veteran)
are not kept.

Partitions: one per file and byte window. The files are large (PPP: 13 files, ~3.7 GB and
~11M rows; 7(a)/504: 6 files, ~1 GB), so they are never downloaded whole: each partition is a
window of WINDOW bytes read with an HTTP Range request, holding the CSV lines that start
inside it (equity.adapters.http.window_lines), the header read from the first bytes.
Windows are found with 1-byte probes. A line the csv module splits into the wrong number of
fields (a quoted newline cut by a window edge) is dropped and counted in `bad_lines`.

Sources: https://data.sba.gov/dataset/ppp-foia and https://data.sba.gov/dataset/7a-504-foia
(U.S. government data released under FOIA, free, no login; robots.txt disallows only Drupal
admin, user and search paths). PPP files are final (as of 2024-09-30, re-published 2026-06);
the 7(a)/504 files are refreshed quarterly.
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal import sba_chargeoffs, sba_ppp
from equity.adapters.federal.sba_chargeoffs import _day, _text
from equity.adapters.http import OVERLAP, RangeClient, window_lines
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.geo import county_by_name
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

WINDOW = 16_000_000  # bytes per partition: ~25k PPP rows, ~35k 7(a) rows
HEAD_BYTES = 16_383

PPP_KEEP = (
    "LoanNumber", "DateApproved", "SBAOfficeCode", "ProcessingMethod", "BorrowerName",
    "BorrowerAddress", "BorrowerCity", "BorrowerState", "BorrowerZip", "LoanStatusDate",
    "LoanStatus", "Term", "SBAGuarantyPercentage", "InitialApprovalAmount",
    "CurrentApprovalAmount", "UndisbursedAmount", "FranchiseName", "ServicingLenderLocationID",
    "ServicingLenderName", "ServicingLenderAddress", "ServicingLenderCity",
    "ServicingLenderState", "ServicingLenderZip", "BusinessAgeDescription", "ProjectCity",
    "ProjectCountyName", "ProjectState", "ProjectZip", "CD", "JobsReported", "NAICSCode",
    "BusinessType", "OriginatingLenderLocationID", "OriginatingLender", "OriginatingLenderCity",
    "OriginatingLenderState", "NonProfit", "ForgivenessAmount", "ForgivenessDate",
)  # fmt: skip
SBA_KEEP = (
    "AsOfDate", "Program", "LocationID", "BorrName", "BorrStreet", "BorrCity", "BorrState",
    "BorrZip", "BankName", "BankFDICNumber", "BankNCUANumber", "BankStreet", "BankCity",
    "BankState", "BankZip", "CDC_Name", "CDC_Street", "CDC_City", "CDC_State", "CDC_Zip",
    "ThirdPartyLender_Name", "ThirdPartyLender_City", "ThirdPartyLender_State",
    "ThirdPartyDollars", "GrossApproval", "SBAGuaranteedApproval", "ApprovalDate", "ApprovalFY",
    "FirstDisbursementDate", "ProcessingMethod", "InitialInterestRate",
    "FixedorVariableInterestInd", "TermInMonths", "NaicsCode", "NaicsDescription",
    "FranchiseCode", "FranchiseName", "ProjectCounty", "ProjectState", "SBADistrictOffice",
    "CongressionalDistrict", "BusinessType", "BusinessAge", "LoanStatus", "PaidInFullDate",
    "ChargeOffDate", "GrossChargeOffAmount", "RevolverStatus", "JobsSupported", "CollateralInd",
    "SoldSecMrktInd",
)  # fmt: skip


def _zip5(v: Any) -> str | None:
    z = str(v or "").strip()[:5]
    return z if len(z) == 5 and z.isdigit() else None


def _addr(street: Any, city: Any, state: Any, zip_: Any) -> dict[str, Any] | None:
    return normalized_address(_text(street), _text(city), _text(state), _zip5(zip_))


def _jurisdiction(state: str | None, county: str | None) -> str:
    if state and county:
        try:
            return county_by_name(state, county).fips5
        except KeyError:
            return state
    return state or "US"


def parse_window(
    head: bytes, data: bytes, lo: int, hi: int, start: int, at_eof: bool, keep: tuple[str, ...]
) -> tuple[list[str], list[dict[str, Any]], int]:
    """(header, the KEEP columns of every row starting in [lo, hi), lines dropped) for the
    bytes `data` read from file offset `start`, the file's first bytes being `head`."""
    header = next(csv.reader([head.split(b"\n", 1)[0].decode("utf-8-sig", errors="replace")]))
    header = [h.strip() for h in header]
    lines = window_lines(data, lo, hi, start, at_eof)
    if lo == 0 and lines:
        lines = lines[1:]  # the header
    text = b"".join(lines).decode("utf-8", errors="replace")
    rows: list[dict[str, Any]] = []
    bad = 0
    for cells in csv.reader(io.StringIO(text)):
        if not cells:
            continue
        if len(cells) != len(header):
            bad += 1
            continue
        row = dict(zip(header, cells, strict=True))
        rows.append({k: (row.get(k) or "").strip() or None for k in keep if k in row})
    return header, rows, bad


class _SBALoanWindows(Adapter):
    """One SBA FOIA dataset page of CSV files, read in byte windows."""

    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    page: ClassVar[str]
    files: ClassVar[Mapping[str, str]]
    keep: ClassVar[tuple[str, ...]]
    terms: ClassVar[str]

    def __init__(self, client: RangeClient | None = None) -> None:
        self.client = client or RangeClient(min_interval_s=1.0, timeout_s=600.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "federal_loan",
            "jurisdiction": "US",
            "access_method": "bulk",
            "base_url": self.page,
            "terms_url": self.page,
            "terms_summary": self.terms,
            "terms_checked_on": "2026-11-25",
            "robots_checked_on": "2026-11-25",
            "cost_model": "free",
        }

    def file_url(self, name: str) -> str:
        if name not in self.files:
            raise ValueError(f"unknown file {name!r}")
        page = self.client.get(self.page)
        if page.status != 200:
            raise RuntimeError(f"HTTP {page.status} from {self.page}")
        text = page.content.decode("utf-8", errors="replace")
        for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", text):
            if re.search(self.files[name], str(href)):
                return str(urllib.parse.urljoin(self.page, str(href)))
        raise RuntimeError(f"no {name} file linked on {self.page}")

    def partitions(self) -> Iterator[dict[str, str]]:
        """Each file, in WINDOW-byte windows, until a 1-byte probe is past the end."""
        for name in self.files:
            url = self.file_url(name)
            lo = 0
            while True:
                probe = self.client.get_range(url, lo, lo)
                if probe.status != 206:
                    break
                yield {"file": name, "url": url, "lo": str(lo), "hi": str(lo + WINDOW)}
                lo += WINDOW

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: file; url (from partitions, else found on the page); lo, hi (byte window,
        default the first WINDOW bytes); limit (fixtures: the window's first rows only)."""
        p = request.params
        name = p["file"]
        url = p.get("url") or self.file_url(name)
        lo, hi = int(p.get("lo", "0")), int(p.get("hi", str(WINDOW)))
        if hi <= lo:
            raise ValueError("hi must be greater than lo")
        head = self.client.get_range(url, 0, HEAD_BYTES)
        if head.status not in (200, 206):
            raise RuntimeError(f"HTTP {head.status} from {url}")
        start = max(lo - 1, 0)
        want = hi + OVERLAP - 1
        resp = self.client.get_range(url, start, want)
        if resp.status == 416:  # the window starts past the end of the file
            data, at_eof = b"", True
        elif resp.status in (200, 206):
            data = resp.content if resp.status == 206 else resp.content[start : want + 1]
            at_eof = len(data) < want - start + 1
        else:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        header, rows, bad = parse_window(head.content, data, lo, hi, start, at_eof, self.keep)
        if "limit" in p:
            rows = rows[: int(p["limit"])]
        body = {"file": name, "url": url, "lo": lo, "hi": hi, "columns": header,
                "bad_lines": bad, "rows": rows}  # fmt: skip
        return Fetched(self.source_id, f"{url}#bytes={lo}-{hi - 1}", resp.retrieved_at, 200,
                       canonical_json(body), "application/json")  # fmt: skip

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        name = next(iter(self.files))
        try:
            url = self.file_url(name)
            head = self.client.get_range(url, 0, 4095)
        except (RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        line = head.content.split(b"\n", 1)[0].decode("utf-8-sig", errors="replace")
        shape = tuple(sorted(h.strip() for h in next(csv.reader([line])))) if line else ()
        ok = head.status == 206 and bool(set(self.keep[:6]) & set(shape))
        detail = url.rsplit("/", 1)[-1] if ok else f"status={head.status} shape={list(shape)}"
        return HealthReport(self.source_id, ok, now, detail, shape)

    # shared emit ---------------------------------------------------------------------------

    def _emit(
        self,
        ctx: RecordContext,
        sos_id: str,
        borrower: str,
        borrower_addr: dict[str, Any] | None,
        status: str | None,
        status_date: date | None,
        valid_from: date,
        lenders: list[tuple[str, str, dict[str, Any] | None]],
    ) -> Iterator[NormalizedRow]:
        """business + borrower and lender parties and roles. lenders: (title, name, addr)."""
        addrs = [a for a in (borrower_addr, *(x[2] for x in lenders)) if a is not None]
        for a in sorted({a["address_id"]: a for a in addrs}.values(), key=canonical_json):
            yield NormalizedRow("address", a)
        nc = classify(borrower)
        yield ctx.fact(
            "business", sos_id=sos_id, name=borrower, org_form=nc.org_form, status=status,
            formed_on=None, status_date=status_date,
            principal_address_id=None if borrower_addr is None else borrower_addr["address_id"],
            mailing_address_id=None, valid_from=valid_from, valid_to=None,
        )  # fmt: skip
        seen: set[str] = set()
        for title, who, addr in [("BORROWER", borrower, borrower_addr), *lenders]:
            role_key = "borrower" if title == "BORROWER" else "lender"
            party_id = stable_id(self.source_id, ctx.record_key, role_key, clean(who))
            if party_id in seen:  # e.g. the originating lender is the servicing lender
                continue
            seen.add(party_id)
            pc = classify(who)
            yield ctx.fact(
                "party", party_id=party_id, raw_name=who, party_kind=pc.party_kind,
                org_form=pc.org_form, org_name_norm=pc.org_name_norm,
                address_id=None if addr is None else addr["address_id"],
            )  # fmt: skip
            yield ctx.fact("business_role", sos_id=sos_id, party_id=party_id, role="other",
                           title=title, valid_from=valid_from, valid_to=None)  # fmt: skip


class SBAPPPLoans(_SBALoanWindows):
    """Every PPP loan (not only the charged-off ones): borrower, address, lenders."""

    source_id: ClassVar[str] = "us.sba.ppp_loans"
    page: ClassVar[str] = sba_ppp.PAGE
    files: ClassVar[Mapping[str, str]] = sba_ppp.FILES
    keep: ClassVar[tuple[str, ...]] = PPP_KEEP
    pii_fields: ClassVar[tuple[str, ...]] = ("BorrowerName", "BorrowerAddress")
    terms: ClassVar[str] = (
        "SBA Paycheck Protection Program FOIA loan files (all loans), CSV, free, no login; "
        "U.S. government data released under FOIA. robots.txt disallows only admin/search. "
        "Read in HTTP byte ranges."
    )

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        today = fetched.retrieved_at.astimezone(UTC).date()
        for a in sorted(data.get("rows") or [], key=canonical_json):
            name = _text(a.get("BorrowerName"))
            loan = _text(a.get("LoanNumber"))
            if name is None or name.upper() in sba_ppp.WITHHELD or loan is None:
                continue
            approved = _day(a.get("DateApproved"))
            valid_from = approved if approved is not None and approved <= today else today
            status_on = _day(a.get("LoanStatusDate"))
            st = _text(a.get("ProjectState")) or _text(a.get("BorrowerState"))
            juris = _jurisdiction(st, _text(a.get("ProjectCountyName")))
            ctx = RecordContext(fetched, juris, loan, "ppp_loan", a)
            yield ctx.source_record()
            borrower_addr = _addr(a.get("BorrowerAddress"), a.get("BorrowerCity"),
                                  a.get("BorrowerState"), a.get("BorrowerZip"))  # fmt: skip
            lenders: list[tuple[str, str, dict[str, Any] | None]] = []
            if servicing := _text(a.get("ServicingLenderName")):
                lenders.append(("SERVICING LENDER", servicing, _addr(
                    a.get("ServicingLenderAddress"), a.get("ServicingLenderCity"),
                    a.get("ServicingLenderState"), a.get("ServicingLenderZip"))))  # fmt: skip
            if originating := _text(a.get("OriginatingLender")):
                lenders.append(("ORIGINATING LENDER", originating, _addr(
                    None, a.get("OriginatingLenderCity"), a.get("OriginatingLenderState"),
                    None)))  # fmt: skip
            yield from self._emit(
                ctx, f"SBA-PPP-{loan}", name, borrower_addr, _text(a.get("LoanStatus")),
                status_on if status_on is not None and status_on <= today else None,
                valid_from, lenders,
            )  # fmt: skip


# Fields that tell one 7(a)/504 loan from another in the FOIA files (which publish no loan
# number). The borrower name is part of the identity, but only the hash carries it.
SBA_KEY = ("Program", "LocationID", "BorrName", "ApprovalDate", "GrossApproval", "BankName",
           "CDC_Name", "ThirdPartyLender_Name", "TermInMonths")  # fmt: skip


class SBA7a504Loans(_SBALoanWindows):
    """Every SBA 7(a) and 504 loan (not only the charged-off ones): borrower, lender, CDC."""

    source_id: ClassVar[str] = "us.sba.7a_504_loans"
    page: ClassVar[str] = sba_chargeoffs.PAGE
    files: ClassVar[Mapping[str, str]] = sba_chargeoffs.FILES
    keep: ClassVar[tuple[str, ...]] = SBA_KEEP
    pii_fields: ClassVar[tuple[str, ...]] = ("BorrName", "BorrStreet")
    terms: ClassVar[str] = (
        "SBA 7(a) and 504 FOIA loan files (all loans), quarterly CSV, free, no login; U.S. "
        "government data released under FOIA. robots.txt disallows only admin/search. Read "
        "in HTTP byte ranges."
    )

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        today = fetched.retrieved_at.astimezone(UTC).date()
        seen: dict[str, int] = {}
        for a in sorted(data.get("rows") or [], key=canonical_json):
            name = _text(a.get("BorrName"))
            if name is None or name.upper() in sba_ppp.WITHHELD:
                continue
            program = (_text(a.get("Program")) or ("504" if "CDC_Name" in a else "7A")).upper()
            key = "|".join(str(a.get(k) or "").strip() for k in SBA_KEY)
            # Loans the window does not tell apart: numbered in (sorted) order.
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                key = f"{key}~{seen[key]}"
            record_key = stable_id(self.source_id, key)
            approved = _day(a.get("ApprovalDate"))
            valid_from = approved if approved is not None and approved <= today else today
            closed = _day(a.get("ChargeOffDate")) or _day(a.get("PaidInFullDate"))
            st = _text(a.get("ProjectState")) or _text(a.get("BorrState"))
            juris = _jurisdiction(st, _text(a.get("ProjectCounty")))
            rtype = "sba_504_loan" if program == "504" else "sba_7a_loan"
            ctx = RecordContext(fetched, juris, record_key, rtype, a)
            yield ctx.source_record()
            borrower_addr = _addr(a.get("BorrStreet"), a.get("BorrCity"), a.get("BorrState"),
                                  a.get("BorrZip"))  # fmt: skip
            lenders: list[tuple[str, str, dict[str, Any] | None]] = []
            if bank := _text(a.get("BankName")):
                where = _addr(a.get("BankStreet"), a.get("BankCity"), a.get("BankState"),
                              a.get("BankZip"))  # fmt: skip
                lenders.append(("LENDER", bank, where))
            if cdc := _text(a.get("CDC_Name")):
                where = _addr(a.get("CDC_Street"), a.get("CDC_City"), a.get("CDC_State"),
                              a.get("CDC_Zip"))  # fmt: skip
                lenders.append(("CDC", cdc, where))
            if third := _text(a.get("ThirdPartyLender_Name")):
                lenders.append(("THIRD PARTY LENDER", third, _addr(
                    None, a.get("ThirdPartyLender_City"), a.get("ThirdPartyLender_State"),
                    None)))  # fmt: skip
            yield from self._emit(
                ctx, f"SBA-{program}-{record_key}", name, borrower_addr,
                _text(a.get("LoanStatus")),
                closed if closed is not None and closed <= today else None, valid_from, lenders,
            )  # fmt: skip
