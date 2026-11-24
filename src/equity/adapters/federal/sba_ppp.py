"""Paycheck Protection Program loans SBA charged off, from SBA's PPP FOIA files.

Each row of the PPP FOIA files is one PPP loan, with the borrower's name and street address,
the servicing lender, approval amount, forgiveness amount and the loan status. Rows with
LoanStatus "Charged Off" are kept: a borrower whose federally guaranteed loan was neither
repaid nor forgiven. The owed balance is the current approval amount less the amount forgiven
(both published per loan); the file gives no separate charge-off amount. Like the 7(a) and 504
charge-offs (equity.adapters.federal.sba_chargeoffs) this is its own debt kind
(charged_off_loan), not a judgment or lien. Borrower names SBA withheld under FOIA Exemption 6
(individuals and sole proprietors) are not loaded.

One partition per file: the loans over $150,000 and twelve files of smaller loans. File names
carry their as-of date, so each fetch finds the current link on the dataset page. Only charged
off rows are kept, so a 450 MB file never sits in memory as rows.

Source: https://data.sba.gov/dataset/ppp-foia (U.S. government data, released under FOIA;
robots.txt disallows only Drupal admin and search paths). Each instrument is OTHER, dated by
the loan status date, with the unforgiven balance; the borrower is the debtor and the
servicing lender the creditor. County: the project county when it names one.
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.sba_chargeoffs import _day, _money, _text
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.geo import county_by_name
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PAGE = "https://data.sba.gov/dataset/ppp-foia"
SMALL = {f"up_to_150k_{n}": rf"public_up_to_150k_{n}_\d+\.csv" for n in range(1, 13)}
FILES = {"150k_plus": r"public_150k_plus_\d+\.csv", **SMALL}
KEEP = ("LoanNumber", "DateApproved", "BorrowerName", "BorrowerAddress", "BorrowerCity",
        "BorrowerState", "BorrowerZip", "LoanStatusDate", "LoanStatus", "CurrentApprovalAmount",
        "ForgivenessAmount", "ServicingLenderName", "ProjectCountyName", "ProjectState",
        "BusinessType", "ProcessingMethod")  # fmt: skip
WITHHELD = ("EXEMPTION 6", "NOT AVAILABLE", "N/A", "NA")


def charged_off(content: bytes) -> list[dict[str, Any]]:
    """The Charged Off rows of one PPP FOIA CSV, only the KEEP columns, read row by row."""
    text = io.TextIOWrapper(io.BytesIO(content), encoding="utf-8-sig", errors="replace",
                            newline="")  # fmt: skip
    out: list[dict[str, Any]] = []
    for row in csv.DictReader(text):
        if (row.get("LoanStatus") or "").strip().upper() == "CHARGED OFF":
            out.append({k: (row.get(k) or "").strip() or None for k in KEEP if k in row})
    return out


def unforgiven(row: Mapping[str, Any]) -> Decimal | None:
    """Current approval amount less the amount forgiven, or None when nothing is left."""
    approved = _money(row.get("CurrentApprovalAmount"))
    if approved is None:
        return None
    left = approved - (_money(row.get("ForgivenessAmount")) or Decimal(0))
    return left if left > 0 else None


class SBAPPPChargeOffs(Adapter):
    source_id: ClassVar[str] = "us.sba.ppp_chargeoffs"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("BorrowerName", "BorrowerAddress")

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=1800.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "federal_loan",
            "jurisdiction": "US",
            "access_method": "bulk",
            "base_url": PAGE,
            "terms_url": PAGE,
            "terms_summary": (
                "SBA Paycheck Protection Program FOIA loan files, CSV, free, no login; U.S. "
                "government data released under FOIA. robots.txt disallows only admin/search."
            ),
            "terms_checked_on": "2026-11-24",
            "robots_checked_on": "2026-11-24",
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
        rows = charged_off(resp.content)
        if "limit" in request.params:
            rows = rows[: int(request.params["limit"])]
        body = {"file": name, "url": url, "rows": rows}
        return Fetched(self.source_id, url, resp.retrieved_at, 200, canonical_json(body),
                       "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        today = fetched.retrieved_at.astimezone(UTC).date()
        for a in sorted(data.get("rows") or [], key=canonical_json):
            name = _text(a.get("BorrowerName"))
            loan = _text(a.get("LoanNumber"))
            status_on = _day(a.get("LoanStatusDate"))
            if (name is None or name.upper() in WITHHELD or loan is None or status_on is None
                    or status_on > today):  # fmt: skip
                continue
            st = _text(a.get("ProjectState")) or _text(a.get("BorrowerState"))
            juris = st or "US"
            county = _text(a.get("ProjectCountyName"))
            if st and county:
                try:
                    juris = county_by_name(st, county).fips5
                except KeyError:
                    juris = st
            ctx = RecordContext(fetched, juris, stable_id(self.source_id, loan), "ppp_chargeoff", a)
            yield ctx.source_record()
            uid = stable_id(self.source_id, loan)
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=loan, book_type=None,
                book=None, page=None, doc_type_raw="SBA PPP loan charged off", doc_type="OTHER",
                recorded_on=status_on, recorded_seq=None, executed_on=_day(a.get("DateApproved")),
                consideration=None, principal_amount=unforgiven(a),
                max_secured_amount=_money(a.get("CurrentApprovalAmount")), maturity_date=None,
                amount_source="index", legal_desc_raw=None,
            )  # fmt: skip
            z = str(a.get("BorrowerZip") or "").strip()[:5]
            addr = normalized_address(_text(a.get("BorrowerAddress")), _text(a.get("BorrowerCity")),
                                      _text(a.get("BorrowerState")),
                                      z if len(z) == 5 and z.isdigit() else None)  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            lender = _text(a.get("ServicingLenderName"))
            for role, who, address_id in (("debtor", name, addr["address_id"] if addr else None),
                                          ("creditor", lender, None)):  # fmt: skip
                if who is None:
                    continue
                nc = classify(who)
                pid = stable_id(self.source_id, loan, role, clean(who))
                yield ctx.fact("party", party_id=pid, raw_name=who, party_kind=nc.party_kind,
                               org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                               address_id=address_id)  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid, role=role,
                               seq=1)  # fmt: skip

    def health(self) -> HealthReport:
        try:
            url = self.file_url("150k_plus")
        except (RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        return HealthReport(self.source_id, True, datetime.now(UTC), url.rsplit("/", 1)[-1])
