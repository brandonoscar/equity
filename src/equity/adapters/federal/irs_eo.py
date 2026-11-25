"""IRS Exempt Organizations Business Master File Extract (EO BMF): every organization the IRS
recognizes as tax-exempt, with its EIN, name, "in care of" name, street address, subsection
(501(c)(3), (c)(4)...), ruling date and exemption status.

What is emitted, from existing tables only:

- business: one per EIN, sos_id "EIN:<9 digits>" (the same key the Form 990 officer source
  uses, so a return's officers attach to the organization), name, the mailing address as the
  principal address, status from the exemption status code, status_date = the ruling date
  (the month the exemption was recognized). Valid from the ruling date (else the snapshot
  date): the file is a monthly snapshot and the ruling date is stable from month to month.
- business_role + party: the "in care of" name (ICO), role 'other', title 'in care of', at
  the organization's address. A leading '%' or 'C/O' is dropped. Most ICO names are a
  person (an officer, a trustee, an accountant) or a bank trust department.
- source_record: the whole row (subsection, classification, foundation, NTEE, asset and
  income amounts stay there, hashed).

One partition per state file (eo_al.csv ... eo_wy.csv, eo_dc.csv, eo_pr.csv, and eo_xx.csv
for international addresses), linked from the EO BMF page; the regional eo1-eo4 files hold the
same rows. The files are rewritten monthly. fetch() parses the CSV row by row and keeps only
the KEEP columns; `limit` keeps the first `limit` rows (fixtures).

Source: https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf
(U.S. government data, free, no login; www.irs.gov robots.txt disallows only search, admin
and a few legal-document paths, not /pub/irs-soi/). Layout: the "eo_info.pdf" record layout
on the same page.
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
from equity.adapters.federal.bulk_files import (
    BulkClient,
    Holder,
    address,
    emit_business,
    jurisdiction,
    scrub_json,
    text,
)
from equity.adapters.rows import RecordContext, canonical_json

PAGE = "https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf"
FILE = re.compile(r"/pub/irs-soi/eo_([a-z]{2})\.csv$", re.I)
CHECKED_ON = "2026-11-25"
KEEP = ("EIN", "NAME", "ICO", "STREET", "CITY", "STATE", "ZIP", "GROUP", "SUBSECTION",
        "AFFILIATION", "CLASSIFICATION", "RULING", "DEDUCTIBILITY", "FOUNDATION", "ACTIVITY",
        "ORGANIZATION", "STATUS", "TAX_PERIOD", "ASSET_CD", "INCOME_CD", "FILING_REQ_CD",
        "PF_FILING_REQ_CD", "ACCT_PD", "ASSET_AMT", "INCOME_AMT", "REVENUE_AMT", "NTEE_CD",
        "SORT_NAME")  # fmt: skip
# EO BMF exemption status codes (eo_info.pdf).
STATUS = {"01": "unconditional exemption", "02": "conditional exemption",
          "12": "trust described in section 4947(a)(2)",
          "25": "organization terminating its private foundation status"}  # fmt: skip
_CARE_OF = re.compile(r"^\s*(?:%|C/O\b|C\\O\b|CARE OF\b|ATTN:?)\s*", re.I)


def care_of(value: Any) -> str | None:
    """The ICO name without its '%' / 'C/O' prefix."""
    s = text(value)
    if s is None:
        return None
    return text(_CARE_OF.sub("", s))


def ruling_date(value: Any) -> date | None:
    """RULING is YYYYMM (000000 when none)."""
    s = (text(value) or "").strip()
    if len(s) != 6 or not s.isdigit() or s == "000000":
        return None
    try:
        return date(int(s[:4]), int(s[4:]), 1)
    except ValueError:
        return None


def read_rows(content: bytes, limit: int | None = None) -> list[dict[str, Any]]:
    """The KEEP columns of an EO BMF CSV, row by row."""
    text_io = io.TextIOWrapper(io.BytesIO(content), encoding="utf-8-sig", errors="replace",
                               newline="")  # fmt: skip
    out: list[dict[str, Any]] = []
    for row in csv.DictReader(text_io):
        if limit is not None and len(out) >= limit:
            break
        out.append({k: (row.get(k) or "").strip() or None for k in KEEP if k in row})
    return out


class IRSExemptOrgs(Adapter):
    source_id: ClassVar[str] = "us.irs.eo_bmf"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("ICO", "STREET")

    def __init__(self, client: BulkClient | None = None) -> None:
        self.client = client or BulkClient(min_interval_s=2.0, timeout_s=900.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a registry of organizations
            "jurisdiction": "US",
            "access_method": "bulk",
            "base_url": PAGE,
            "terms_url": PAGE,
            "terms_summary": (
                "IRS Exempt Organizations Business Master File Extract, CSV per state, "
                "rewritten monthly; U.S. government data, free, no login. robots.txt allows "
                "/pub/irs-soi/."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def state_files(self) -> dict[str, str]:
        resp = self.client.get(PAGE)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {PAGE}")
        page = resp.content.decode("utf-8", errors="replace")
        out: dict[str, str] = {}
        for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", page):
            m = FILE.search(href)
            if m:
                out[m.group(1).lower()] = urllib.parse.urljoin(PAGE, href)
        return dict(sorted(out.items()))

    def partitions(self) -> Iterator[dict[str, str]]:
        for st in self.state_files():
            yield {"state": st}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: state (two letters, or xx for international); limit (fixtures)."""
        p = request.params
        st = p["state"].lower()
        if not re.fullmatch(r"[a-z]{2}", st):
            raise ValueError(f"bad state {st!r}")
        url = f"https://www.irs.gov/pub/irs-soi/eo_{st}.csv"
        resp = self.client.get(url)
        if resp.status != 200 or not resp.content.lstrip(b"\xef\xbb\xbf").startswith(b"EIN,"):
            raise RuntimeError(f"{url}: HTTP {resp.status} ({resp.content_type}), not an EO file")
        rows = read_rows(resp.content, int(p["limit"]) if "limit" in p else None)
        body = {"state": st, "url": url, "rows": rows}
        return Fetched(self.source_id, url, resp.retrieved_at, 200, canonical_json(body),
                       "application/json")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, ("ICO",), ("STREET",))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for r in sorted(data.get("rows") or [], key=canonical_json):
            ein = "".join(ch for ch in str(r.get("EIN") or "") if ch.isdigit())
            name = text(r.get("NAME"))
            if len(ein) != 9 or name is None or ein in seen:
                continue
            seen.add(ein)
            ctx = RecordContext(fetched, jurisdiction(text(r.get("STATE"))), ein,
                                "exempt_organization", r)  # fmt: skip
            yield ctx.source_record()
            ruled = ruling_date(r.get("RULING"))
            if ruled is not None and ruled > observed:
                ruled = None
            addr = address(r.get("STREET"), r.get("CITY"), r.get("STATE"), r.get("ZIP"))
            holders = []
            ico = care_of(r.get("ICO"))
            if ico:
                holders.append(Holder("other", "in care of", ico, addr))
            code = text(r.get("STATUS"))
            yield from emit_business(
                ctx, source_id=self.source_id, sos_id=f"EIN:{ein}", name=name,
                valid_from=ruled or observed, status=STATUS.get(code or "", code),
                status_date=ruled, principal=addr, holders=holders,
            )  # fmt: skip

    def health(self) -> HealthReport:
        try:
            files = self.state_files()
        except (RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        ok = len(files) >= 50
        return HealthReport(self.source_id, ok, datetime.now(UTC), f"{len(files)} state files",
                            rows=None)  # fmt: skip
