"""Dallas County, TX Tax Office Tax Roll (TRW) file: delinquent real property tax by account.

The Tax Office publishes the TRW file free on dallascounty.org (Departments > Tax > Tax Roll),
rebuilt weekly after Friday close: a zip holding one fixed-width ASCII file (534 characters a
record, layout in trwfile_layout.txt) with the current year's roll, paid and unpaid, and every
prior year's unpaid balance, one record per account, year and taxing jurisdiction (about five
jurisdictions an account). Each record carries the owner's name and up to three mailing lines,
the appraisal-district account number, the total amount due, the due date, the date paid, and
flags for a pending tax suit (with cause number), a bankruptcy on file (with case number) and a
payment agreement. The zip's file name changes each week, so the current link is taken from the
tax-roll page.

Read here: real property records (roll codes R, real, and C, commercial; the TRW FAQ lists
P personal, R real, M mobile home, N mineral, C commercial) with an amount due and a due date
before the fetch date, summed per appraisal-district account across years and jurisdictions.
Each account is one TAX_LIEN_STATE instrument (Texas property tax is a lien on the property,
Tax Code 32.01) owed by the named owner, dated January 1 of the earliest unpaid year, with the
total due as its amount. The suit, bankruptcy and payment-agreement flags and numbers are kept
in the raw type: the layout does not define the suit codes (A, J, L), so a suit is not read as
a judgment.
The appraisal-district account is the Dallas CAD account of tx.dallas_city.parcels.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PAGE = "https://www.dallascounty.org/departments/tax/tax-roll.php"
LINK = re.compile(r'href="\s*([^"]*?/trw/trwfile\.\d+\.zip)\s*"', re.I)
COUNTY = "48113"
CREDITOR = "Dallas County Tax Assessor-Collector"
RECORD = 534
REAL_ROLLS = ("R", "C")  # real and commercial real property (TRW FAQ roll codes)
# (name, start, end): 1-based inclusive positions from trwfile_layout.txt
FIELDS = (("account", 1, 34), ("year", 35, 38), ("jurisdiction", 39, 42),
          ("cad_account", 43, 76), ("date_paid", 93, 100), ("due_date", 101, 108),
          ("suit", 122, 122), ("cause", 123, 162), ("bankrupt", 163, 163),
          ("bankrupt_no", 164, 203), ("owner", 226, 265), ("addr2", 266, 305),
          ("addr3", 306, 345), ("addr4", 346, 385), ("city", 386, 425), ("state", 426, 427),
          ("zip", 428, 439), ("roll", 440, 440), ("agreement", 489, 489),
          ("total_due", 490, 500))  # fmt: skip


def parse_record(line: str) -> dict[str, str]:
    return {name: line[a - 1 : b].strip() for name, a, b in FIELDS}


def _ymd(v: str) -> date | None:
    s = v.strip()
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8])) if len(s) == 8 and s.isdigit() else None
    except ValueError:
        return None


def _cents(v: str) -> int:
    s = v.strip().lstrip("0") or "0"
    return int(s) if s.isdigit() else 0


def delinquent_accounts(lines: Iterator[str], today: date,
                        rolls: tuple[str, ...] = REAL_ROLLS) -> list[dict[str, Any]]:  # fmt: skip
    """Records of the given roll codes past due with an amount due, summed per CAD account."""
    acc: dict[str, dict[str, Any]] = {}
    for line in lines:
        if len(line) < RECORD - 1:
            continue
        r = parse_record(line)
        due, cents = _ymd(r["due_date"]), _cents(r["total_due"])
        if r["roll"] not in rolls or cents <= 0 or due is None or due >= today or r["date_paid"]:
            continue
        key = r["cad_account"] or r["account"]
        if not key:
            continue
        a = acc.setdefault(key, {"cad_account": key, "owner": r["owner"], "addr2": r["addr2"],
                                 "addr3": r["addr3"], "addr4": r["addr4"], "city": r["city"],
                                 "state": r["state"], "zip": r["zip"], "cents": 0,
                                 "years": set(), "suits": set(), "bankruptcies": set(),
                                 "agreement": False})  # fmt: skip
        a["cents"] += cents
        if r["year"].isdigit():
            a["years"].add(int(r["year"]))
        if r["suit"]:
            a["suits"].add(f"{r['suit']}:{r['cause']}" if r["cause"] else r["suit"])
        if r["bankrupt"]:
            a["bankruptcies"].add(r["bankrupt_no"] or r["bankrupt"])
        a["agreement"] = a["agreement"] or r["agreement"] == "Y"
    out = []
    for key in sorted(acc):
        a = acc[key]
        out.append({**a, "years": sorted(a["years"]), "suits": sorted(a["suits"]),
                    "bankruptcies": sorted(a["bankruptcies"])})  # fmt: skip
    return out


class DallasTaxRollDelinquent(Adapter):
    source_id: ClassVar[str] = "tx.dallas.tax_roll_delinquent"
    adapter_version: ClassVar[str] = "2"  # 2: commercial real property (roll C) included
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("owner", "addr2", "addr3", "addr4")
    rolls: ClassVar[tuple[str, ...]] = REAL_ROLLS
    tax_label: ClassVar[str] = "property tax"
    link_parcel: ClassVar[bool] = True  # the CAD account of a real property record is its parcel

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=1800.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "tax",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": PAGE,
            "terms_url": PAGE,
            "terms_summary": (
                "Dallas County Tax Office Tax Roll (TRW) file: 'accessible on the Dallas County "
                "Tax Office website for no additional charge', rebuilt weekly; no login. No "
                "license or use restriction stated; dallascounty.org robots.txt allows all."
            ),
            "terms_checked_on": "2026-11-27",
            "robots_checked_on": "2026-11-27",
            "cost_model": "free",
        }

    def file_url(self) -> str:
        resp = self.client.get(PAGE)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status} for the tax-roll page")
        m = LINK.search(resp.content.decode("utf-8", "replace"))
        if m is None:
            raise RuntimeError(f"{self.source_id}: no TRW zip link on {PAGE}")
        href = m.group(1)
        return href if href.startswith("http") else "https://www.dallascounty.org" + href

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {}

    def fetch(self, request: FetchRequest) -> Fetched:
        url = self.file_url()
        resp = self.client.get(url)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status} for {url}")
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        names = [n for n in z.namelist() if "/flat404." in n or n.startswith("flat404.")]
        if not names:
            raise RuntimeError(f"{self.source_id}: no flat404 data file in {url}")
        with z.open(names[0]) as raw:
            lines = (b.decode("latin-1").rstrip("\r\n") for b in raw)
            rows = delinquent_accounts(lines, resp.retrieved_at.date(), self.rolls)
        limit = request.params.get("limit")
        if limit:
            rows = rows[: int(limit)]
        return Fetched(self.source_id, url, resp.retrieved_at, 200,
                       canonical_json({"file": names[0].rsplit("/", 1)[-1], "rows": rows}),
                       "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        for r in json.loads(fetched.content).get("rows") or []:
            key, owner = (
                str(r.get("cad_account") or ""),
                " ".join(str(r.get("owner") or "").split()),
            )
            years = [int(y) for y in r.get("years") or []]
            cents = int(r.get("cents") or 0)
            if not (key and owner and years and cents > 0):
                continue
            ctx = RecordContext(fetched, COUNTY, key, "tax_account", r)
            uid = stable_id(self.source_id, "account", key)
            notes = [f"years {years[0]}-{years[-1]}" if len(years) > 1 else f"year {years[0]}"]
            if r.get("suits"):
                notes.append("tax suit " + ", ".join(r["suits"]))
            if r.get("bankruptcies"):
                notes.append("bankruptcy on file " + ", ".join(r["bankruptcies"]))
            if r.get("agreement"):
                notes.append("payment agreement")
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=key, book_type=None,
                book=None, page=None,
                doc_type_raw=(f"Dallas County delinquent {self.tax_label} ("
                              + "; ".join(notes) + ")"),
                doc_type="TAX_LIEN_STATE", recorded_on=date(years[0], 1, 1), recorded_seq=None,
                executed_on=None, consideration=None,
                principal_amount=Decimal(cents) / 100, max_secured_amount=None,
                maturity_date=None, amount_source="index", legal_desc_raw=None,
            )  # fmt: skip
            if self.link_parcel:
                yield ctx.fact("instrument_parcel", instrument_uid=uid,
                               parcel_uid=f"{COUNTY}-{key}", method="index_parcel_id",
                               evidence={"cad_account": key})  # fmt: skip
            line = " ".join(x for x in (r.get("addr2"), r.get("addr3"), r.get("addr4")) if x)
            z = str(r.get("zip") or "")[:5]
            addr = normalized_address(line or None, r.get("city") or None, r.get("state") or None,
                                      z if z.isdigit() and len(z) == 5 else None)  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            nc = classify(owner)
            pid = stable_id(self.source_id, key, "debtor", clean(owner))
            yield ctx.fact("party", party_id=pid, raw_name=owner, party_kind=nc.party_kind,
                           org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                           address_id=addr["address_id"] if addr else None)  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid, role="debtor",
                           seq=1)  # fmt: skip
            cr = classify(CREDITOR)
            cid = stable_id(self.source_id, "creditor", clean(CREDITOR))
            yield ctx.fact("party", party_id=cid, raw_name=CREDITOR, party_kind=cr.party_kind,
                           org_form=cr.org_form, org_name_norm=cr.org_name_norm,
                           address_id=None)  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=cid,
                           role="creditor", seq=1)  # fmt: skip

    def health(self) -> HealthReport:
        try:
            url = self.file_url()
        except RuntimeError as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        return HealthReport(self.source_id, True, datetime.now(UTC), f"TRW file {url}")


class DallasPersonalPropertyDelinquent(DallasTaxRollDelinquent):
    """The TRW file's business personal property records (roll code P: the equipment,
    furniture and inventory of businesses, assessed to the business). Texas personal property
    tax is a lien on that property (Tax Code 32.01); each account is a TAX_LIEN_STATE
    instrument owed by the business, with no parcel (a personal property account is not a
    lot)."""

    source_id: ClassVar[str] = "tx.dallas.personal_property_delinquent"
    adapter_version: ClassVar[str] = "1"
    rolls: ClassVar[tuple[str, ...]] = ("P",)
    tax_label: ClassVar[str] = "business personal property tax"
    link_parcel: ClassVar[bool] = False
