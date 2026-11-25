"""NCUA credit union call report data: every federally insured credit union (~4.3k) with its
mailing address, charter number and dates, and every office (~23k branches, from the
"Credit Union Branch Information" file), one zip per calendar quarter
(call-report-data-YYYY-MM.zip, ~8 MB, linked from the quarterly data page, back to 1994).

Read from each zip (the financial FS220* schedules are not read): FOICU.txt (charter
number, name, mailing street / city / state / ZIP, county code, "attention of" line, year
opened, charter issue date, insured date, peer group...), Credit Union Branch
Information.txt (each site's name, type, main-office flag, physical and mailing address;
phone numbers and hours are not kept) and TradeNames.txt.

What is emitted, from existing tables only (one source record per credit union, record_type
credit_union, key = the charter number):

- business: sos_id NCUA:<charter number>, the main office's site name (the full name, e.g.
  ... FCU) else the FOICU name, status active (the quarter's file lists open credit unions),
  formed_on = the charter issue date, principal address = the main office's physical
  address, mailing address = the FOICU mailing address, valid from the issue date (else the
  quarter's cycle date). The "attention of" line is a holder (role 'other', title ATTENTION
  OF).
- party: the FOICU short name and each trade name (role 'alias'), and the credit union's
  name at each branch's physical address (role 'office').
- address: normalized U.S. addresses.

Partitions: one per quarter (quarter=YYYY-MM, the cycle month). The zip ignores Range
requests and is read whole into memory (8 MB). `limit` (fixtures) keeps the first credit
unions by charter number.

Source: https://ncua.gov/analysis/credit-union-corporate-call-report-data/quarterly-data
(NCUA; U.S. government data, free, no login). ncua.gov robots.txt (read 2026-11-25) allows
/analysis/ and /files/.
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import (
    Holder,
    address,
    emit_business,
    emit_party,
    jurisdiction,
    scrub_json,
    text,
)
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.geo import county_by_fips

PAGE = "https://ncua.gov/analysis/credit-union-corporate-call-report-data/quarterly-data"
CHECKED_ON = "2026-11-25"
FILE = re.compile(r"/call-report-data-(\d{4}-\d{2})\.zip$", re.I)
FOICU = ("CU_NUMBER", "CYCLE_DATE", "JOIN_NUMBER", "RSSD", "CU_TYPE", "CU_NAME", "CITY", "STATE",
         "CharterState", "STATE_CODE", "ZIP_CODE", "COUNTY_CODE", "CONG_DIST", "SMSA",
         "ATTENTION_OF", "STREET", "REGION", "SE", "DISTRICT", "YEAR_OPENED", "TOM_CODE",
         "LIMITED_INC", "ISSUE_DATE", "Peer_Group", "IsMDI", "INSURED_DATE")  # fmt: skip
BRANCH = ("CU_NUMBER", "SiteId", "CU_NAME", "SiteName", "SiteTypeName", "MainOffice",
          "PhysicalAddressLine1", "PhysicalAddressLine2", "PhysicalAddressCity",
          "PhysicalAddressStateCode", "PhysicalAddressPostalCode", "PhysicalAddressCountyName2",
          "PhysicalAddressCountry", "MailingAddressLine1", "MailingAddressLine2",
          "MailingAddressCity", "MailingAddressStateCode", "MailingAddressPostalCode",
          "MemberServices", "ATM", "DriveThru")  # fmt: skip
TRADE = ("CU_NUMBER", "TradeName")
STREETS = ("STREET", "PhysicalAddressLine1", "PhysicalAddressLine2", "MailingAddressLine1",
           "MailingAddressLine2")  # fmt: skip
_MDY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})")


def mdy(value: Any) -> date | None:
    """'6/30/2026 0:00:00' -> 2026-06-30."""
    m = _MDY.match(text(value) or "")
    if m is None:
        return None
    try:
        return date(int(m[3]), int(m[1]), int(m[2]))
    except ValueError:
        return None


def member_rows(zf: zipfile.ZipFile, name: str, keep: tuple[str, ...]) -> list[dict[str, str]]:
    for info in zf.infolist():
        if Path(info.filename).name.lower() == name.lower():
            raw = zf.read(info).decode("utf-8-sig", errors="replace")
            return [{k: v for k in keep if (v := text(r.get(k))) is not None}
                    for r in csv.DictReader(io.StringIO(raw, newline=""))]  # fmt: skip
    raise KeyError(f"{name} not in the zip")


def credit_unions(zf: zipfile.ZipFile, limit: int | None = None) -> list[dict[str, Any]]:
    """One dict per credit union: the FOICU row, its branches and trade names."""
    cus = member_rows(zf, "FOICU.txt", FOICU)
    cus.sort(key=lambda r: int(r["CU_NUMBER"]) if r.get("CU_NUMBER", "").isdigit() else 0)
    if limit is not None:
        cus = cus[:limit]
    wanted = {r.get("CU_NUMBER") for r in cus}
    extra: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for member, keep, slot in (("Credit Union Branch Information.txt", BRANCH, "branches"),
                               ("TradeNames.txt", TRADE, "trade_names")):  # fmt: skip
        for r in member_rows(zf, member, keep):
            if (k := r.get("CU_NUMBER")) is not None and k in wanted:
                extra[k][slot].append(r)
    return [
        {
            **r,
            "branches": extra[r.get("CU_NUMBER", "")]["branches"],
            "trade_names": extra[r.get("CU_NUMBER", "")]["trade_names"],
        }
        for r in cus
    ]


def cu_jurisdiction(r: Mapping[str, Any]) -> str:
    st = text(r.get("STATE"))
    code = text(r.get("COUNTY_CODE"))
    if st and code and code.isdigit() and int(code) > 0:
        try:
            return county_by_fips(st, code.zfill(3)).fips5
        except KeyError:
            pass
    return jurisdiction(st)


def branch_address(b: Mapping[str, Any]) -> dict[str, Any] | None:
    if (text(b.get("PhysicalAddressCountry")) or "United States") != "United States":
        return None
    street = text(" ".join(p for k in ("PhysicalAddressLine1", "PhysicalAddressLine2")
                           if (p := text(b.get(k)))))  # fmt: skip
    return address(street, b.get("PhysicalAddressCity"), b.get("PhysicalAddressStateCode"),
                   b.get("PhysicalAddressPostalCode"))  # fmt: skip


class NCUACreditUnions(Adapter):
    source_id: ClassVar[str] = "us.ncua.credit_unions"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("ATTENTION_OF", *STREETS)

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=600.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a federal registry of institutions
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": PAGE,
            "terms_url": PAGE,
            "terms_summary": (
                "NCUA quarterly credit union call report data (FOICU, branch and trade-name "
                "files), one zip per quarter; U.S. government data, free, no login. "
                "robots.txt allows /analysis/ and /files/. Phone numbers not kept."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def quarter_urls(self) -> dict[str, str]:
        resp = self.client.get(PAGE)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {PAGE}")
        page = resp.content.decode("utf-8", errors="replace")
        out = {}
        for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", page):
            if m := FILE.search(href):
                out[m.group(1)] = urllib.parse.urljoin(PAGE, href)
        return dict(sorted(out.items()))

    def partitions(self) -> Iterator[dict[str, str]]:
        for q in self.quarter_urls():
            yield {"quarter": q}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: quarter (YYYY-MM, the cycle month); limit (fixtures: the first credit
        unions by charter number)."""
        p = request.params
        q = p["quarter"]
        if not re.fullmatch(r"\d{4}-(03|06|09|12)", q):
            raise ValueError(f"bad quarter {q!r}")
        url = self.quarter_urls().get(q)
        if url is None:
            raise RuntimeError(f"{q}: no call report zip linked on {PAGE}")
        resp = self.client.get(url)
        if resp.status != 200 or not resp.content.startswith(b"PK"):
            raise RuntimeError(f"{url}: HTTP {resp.status} ({resp.content_type}); not a zip")
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            cus = credit_unions(zf, int(p["limit"]) if "limit" in p else None)
        body = {"quarter": q, "url": url, "credit_unions": cus}
        return Fetched(self.source_id, url, resp.retrieved_at, 200, canonical_json(body),
                       "application/json")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, ("ATTENTION_OF",), STREETS)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for r in sorted(data.get("credit_unions") or [], key=canonical_json):
            num = text(r.get("CU_NUMBER"))
            short = text(r.get("CU_NAME"))
            if num is None or short is None or num in seen:
                continue
            seen.add(num)
            ctx = RecordContext(fetched, cu_jurisdiction(r), num, "credit_union", r)
            yield ctx.source_record()
            branches = sorted(r.get("branches") or [], key=canonical_json)
            main = next((b for b in branches if (b.get("MainOffice") or "").lower() == "yes"),
                        None)  # fmt: skip
            name = (text(main.get("SiteName")) if main else None) or short
            cycle = mdy(r.get("CYCLE_DATE"))
            cycle = cycle if cycle is not None and cycle <= observed else observed
            issued = mdy(r.get("ISSUE_DATE"))
            issued = issued if issued is not None and issued <= cycle else None
            mailing = address(r.get("STREET"), r.get("CITY"), r.get("STATE"), r.get("ZIP_CODE"))
            holders = []
            if (att := text(r.get("ATTENTION_OF"))) and any(ch.isalpha() for ch in att):
                holders.append(Holder("other", "ATTENTION OF", att, mailing))
            yield from emit_business(
                ctx, source_id=self.source_id, sos_id=f"NCUA:{num}", name=name,
                valid_from=issued or cycle, status="active", formed_on=issued,
                principal=branch_address(main) if main else None, mailing=mailing,
                holders=holders,
            )  # fmt: skip
            aliases = [short] + [n for t in r.get("trade_names") or []
                                 if (n := text(t.get("TradeName")))]  # fmt: skip
            for alias in dict.fromkeys(a for a in aliases if a.upper() != name.upper()):
                yield from emit_party(ctx, self.source_id, "alias", alias)
            offices = {a["address_id"]: a for b in branches if (a := branch_address(b))}
            for addr in offices.values():
                yield from emit_party(ctx, self.source_id, "office", name, addr)

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            found = self.quarter_urls()
        except (OSError, RuntimeError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        latest = max(found) if found else None
        return HealthReport(self.source_id, bool(found), now,
                            f"{len(found)} quarters; latest {latest}")  # fmt: skip
