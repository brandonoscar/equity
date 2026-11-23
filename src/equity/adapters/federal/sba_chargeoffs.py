"""SBA 7(a) and 504 loans the lender charged off, from SBA's quarterly FOIA loan files.

Each row of the FOIA files is one SBA-guaranteed loan, with the borrower's name and street
address, the lender (or 504 Certified Development Company), approval date and amount, and
the loan status. Rows with LoanStatus CHGOFF are kept: a business that defaulted on a
federally guaranteed loan, with the charge-off date and gross amount. A charge-off is not a
judgment or a lien; it enters as its own debt kind (charged_off_loan) so a debtor's other
debts can be weighed against it.

One partition per file (the 7(a) files by fiscal-year range, the two 504 files). File names
carry their as-of date, so each fetch finds the current link on the dataset page. Files are
streamed and only CHGOFF rows are kept, so a 190 MB file never sits in memory as rows.

Source: https://data.sba.gov/dataset/7a-504-foia (U.S. government data, released under FOIA;
robots.txt disallows only Drupal admin and search paths). Each instrument is OTHER, dated by
the charge-off, with the gross charge-off amount; the borrower is the debtor and the lender or
CDC the creditor. County: the project county (ProjectCounty, ProjectState) when it names one.
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.geo import county_by_name
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PAGE = "https://data.sba.gov/dataset/7a-504-foia"
FILES = {
    "7a_1991": r"FOIA_7a_FY1991_FY1999_asof_\d+\.csv",
    "7a_2000": r"FOIA_7a_FY2000_FY2009_asof_\d+\.csv",
    "7a_2010": r"FOIA_7a_FY2010_FY2019_asof_\d+\.csv",
    "7a_2020": r"FOIA_7a_FY2020_Present_asof_\d+\.csv",
    "504_1991": r"FOIA_504_FY1991_FY2009_asof_\d+\.csv",
    "504_2010": r"FOIA_504_FY2010_Present_asof_\d+\.csv",
}
KEEP = ("AsOfDate", "Program", "LocationID", "BorrName", "BorrStreet", "BorrCity", "BorrState",
        "BorrZip", "BankName", "BankFDICNumber", "BankNCUANumber", "CDC_Name",
        "ThirdPartyLender_Name", "GrossApproval", "ApprovalDate", "ApprovalFY", "ProjectCounty",
        "ProjectState", "BusinessType", "LoanStatus", "ChargeOffDate", "GrossChargeOffAmount",
        "CollateralInd")  # fmt: skip


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


def _day(v: Any) -> date | None:
    s = str(v or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC).date()
        except ValueError:
            continue
    return None


def _money(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v or "").replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() and d > 0 else None


def chargeoffs(content: bytes) -> list[dict[str, Any]]:
    """The CHGOFF rows of one FOIA CSV, only the KEEP columns, read row by row."""
    text = io.TextIOWrapper(io.BytesIO(content), encoding="utf-8-sig", errors="replace",
                            newline="")  # fmt: skip
    out: list[dict[str, Any]] = []
    for row in csv.DictReader(text):
        if (row.get("LoanStatus") or "").strip().upper() == "CHGOFF":
            out.append({k: (row.get(k) or "").strip() or None for k in KEEP if k in row})
    return out


class SBAChargeOffs(Adapter):
    source_id: ClassVar[str] = "us.sba.chargeoffs"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("BorrName", "BorrStreet")

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=900.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "federal_loan",
            "jurisdiction": "US",
            "access_method": "bulk",
            "base_url": PAGE,
            "terms_url": PAGE,
            "terms_summary": (
                "SBA 7(a) and 504 FOIA loan files, quarterly CSV, free, no login; U.S. "
                "government data released under FOIA. robots.txt disallows only admin/search."
            ),
            "terms_checked_on": "2026-11-23",
            "robots_checked_on": "2026-11-23",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        for name in FILES:
            yield {"file": name}

    def file_url(self, name: str) -> str:
        page = self.client.get(PAGE)
        if page.status != 200:
            raise RuntimeError(f"HTTP {page.status} from {PAGE}")
        text = page.content.decode("utf-8", errors="replace")
        for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", text):
            if re.search(FILES[name], str(href)):
                return str(urllib.parse.urljoin(PAGE, str(href)))
        raise RuntimeError(f"no {name} file linked on {PAGE}")

    def fetch(self, request: FetchRequest) -> Fetched:
        name = request.params["file"]
        if name not in FILES:
            raise ValueError(f"unknown file {name!r}")
        url = self.file_url(name)
        resp = self.client.get(url)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        rows = chargeoffs(resp.content)
        if "limit" in request.params:
            rows = rows[: int(request.params["limit"])]
        body = {"file": name, "url": url, "rows": rows}
        return Fetched(self.source_id, url, resp.retrieved_at, 200, canonical_json(body),
                       "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        today = fetched.retrieved_at.astimezone(UTC).date()
        seen: dict[str, int] = {}
        for a in sorted(data.get("rows") or [], key=canonical_json):
            name = _text(a.get("BorrName"))
            charged = _day(a.get("ChargeOffDate"))
            if name is None or charged is None or charged > today:
                continue
            program = _text(a.get("Program")) or ("504" if "CDC_Name" in a else "7A")
            # The borrower name is part of the identity, but only the hash carries it.
            fields = (
                "Program",
                "LocationID",
                "BorrName",
                "ApprovalDate",
                "GrossApproval",
                "BankName",
                "CDC_Name",
                "ChargeOffDate",
                "GrossChargeOffAmount",
            )
            key = "|".join(str(a.get(k) or "") for k in fields)
            # Loans the file does not tell apart: numbered in (sorted) file order.
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                key = f"{key}~{seen[key]}"
            number = "-".join(str(a.get(k) or "") for k in ("Program", "LocationID",
                                                           "ApprovalDate")).strip("-")  # fmt: skip
            st = _text(a.get("ProjectState")) or _text(a.get("BorrState"))
            juris = st or "US"
            county = _text(a.get("ProjectCounty"))
            if st and county:
                try:
                    juris = county_by_name(st, county).fips5
                except KeyError:
                    juris = st
            ctx = RecordContext(fetched, juris, stable_id(self.source_id, key), "sba_chargeoff", a)
            yield ctx.source_record()
            uid = stable_id(self.source_id, key)
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=number or uid, book_type=None,
                book=None, page=None, doc_type_raw=f"SBA {program} loan charged off",
                doc_type="OTHER", recorded_on=charged, recorded_seq=None,
                executed_on=_day(a.get("ApprovalDate")), consideration=None,
                principal_amount=_money(a.get("GrossChargeOffAmount")),
                max_secured_amount=_money(a.get("GrossApproval")), maturity_date=None,
                amount_source="index", legal_desc_raw=None,
            )  # fmt: skip
            z = str(a.get("BorrZip") or "").strip()[:5]
            addr = normalized_address(_text(a.get("BorrStreet")), _text(a.get("BorrCity")),
                                      _text(a.get("BorrState")),
                                      z if len(z) == 5 and z.isdigit() else None)  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            lender = _text(a.get("BankName")) or _text(a.get("CDC_Name"))
            for role, who, address_id in (("debtor", name, addr["address_id"] if addr else None),
                                          ("creditor", lender, None)):  # fmt: skip
                if who is None:
                    continue
                nc = classify(who)
                pid = stable_id(self.source_id, key, role, clean(who))
                yield ctx.fact("party", party_id=pid, raw_name=who, party_kind=nc.party_kind,
                               org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                               address_id=address_id)  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid, role=role,
                               seq=1)  # fmt: skip

    def health(self) -> HealthReport:
        try:
            url = self.file_url("504_2010")
        except (RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        return HealthReport(self.source_id, True, datetime.now(UTC), url.rsplit("/", 1)[-1])
