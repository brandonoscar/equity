"""Tarrant County, TX Tax Office tax roll export: delinquent real property tax by account.

The Tax Office publishes the full current and delinquent roll free on tarrantcountytx.gov (Tax >
Property Tax > Tarrant County Tax Roll), rebuilt weekly: TaxRollYYYYMMDD.zip with two fixed-width
files (layout: "Tarrant Tax Roll Record Definition", November 2026). Master.DAT has one 781-byte
record per account (owner names, mailing address, appraisal-district property id, roll code);
Rec.DAT has one 267-byte record per account, tax year, tax unit and receivable, with the base
amount due (before penalty, interest and attorney fees), the delinquency date and, once the
county sues, the lawsuit number, filing date and judgment date, plus any bankruptcy number and
installment agreement. The zip's name carries the run date, so the link is read from the page.

Read here: receivables with an amount due whose delinquency date is before the fetch date,
summed per account, for real property accounts (roll code 01). Each is one instrument owed by
the owner(s) named on the master record: COURT_ORDER (a tax-suit judgment) dated the latest
judgment date when the county has one, otherwise TAX_LIEN_STATE (Texas property tax is a lien
on the property, Tax Code 32.01) dated January 1 of the earliest delinquent year. The lawsuit
and bankruptcy numbers and an installment agreement are kept in the raw type. The master's
"appraisal district number" reads like a block and lot ('14437    11    1'), not the PROP_ID
the statewide parcels carry, so no parcel link is made: owners are matched by name and mailing
address, as for Travis (25,143 accounts, $78.6M base tax due on the 2026-11-25 roll).
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PAGE = "https://www.tarrantcountytx.gov/en/tax/property-tax/tarrant-county-tax-roll.html"
HOST = "https://www.tarrantcountytx.gov"
LINK = re.compile(r'href="([^"]*/tax-rolls/\d{4}/TaxRoll\d{8}\.zip)"', re.I)
COUNTY = "48439"
CREDITOR = "Tarrant County Tax Assessor-Collector"
REAL = ("01",)
Spec = tuple[tuple[str, int, int], ...]
MASTER: Spec = (("account", 1, 30), ("roll", 34, 35), ("cad_id", 169, 198), ("owner1", 327, 376),
          ("owner2", 377, 426), ("addr1", 427, 456), ("addr2", 457, 486), ("city", 487, 516),
          ("state", 517, 536), ("zip", 537, 554))  # fmt: skip
REC: Spec = (("account", 1, 30), ("year", 31, 34), ("unit", 35, 37), ("amount_due", 79, 90),
       ("delinquent_on", 91, 100), ("judgment_on", 111, 120), ("lawsuit", 121, 138),
       ("bankruptcy", 149, 166), ("installment", 234, 234))  # fmt: skip


def _slice(line: str, spec: Spec) -> dict[str, str]:
    return {name: line[a - 1 : b].strip() for name, a, b in spec}


def _mdy(v: str) -> date | None:
    s = v.strip()
    if len(s) != 10 or s == "01/01/9999":
        return None
    try:
        return date(int(s[6:]), int(s[:2]), int(s[3:5]))
    except ValueError:
        return None


def _money(v: str) -> Decimal:
    try:
        d = Decimal(v.strip() or "0")
    except InvalidOperation:
        return Decimal(0)
    return d if d.is_finite() and d > 0 else Decimal(0)


def delinquent_receivables(lines: Iterable[str], today: date,
                           spec: Spec = REC) -> dict[str, dict[str, Any]]:  # fmt: skip
    """Per account: past-due amount, years, latest judgment date, lawsuits, bankruptcies."""
    acc: dict[str, dict[str, Any]] = {}
    for line in lines:
        r = _slice(line, spec)
        due, amount = _mdy(r["delinquent_on"]), _money(r["amount_due"])
        if not r["account"] or amount <= 0 or due is None or due >= today:
            continue
        a = acc.setdefault(r["account"], {"amount": Decimal(0), "years": set(), "judged": None,
                                          "lawsuits": set(), "bankruptcies": set(),
                                          "installment": False})  # fmt: skip
        a["amount"] += amount
        if r["year"].isdigit():
            a["years"].add(int(r["year"]))
        judged = _mdy(r["judgment_on"])
        if judged and (a["judged"] is None or judged > a["judged"]):
            a["judged"] = judged
        if r["lawsuit"]:
            a["lawsuits"].add(r["lawsuit"])
        if r["bankruptcy"]:
            a["bankruptcies"].add(r["bankruptcy"])
        a["installment"] = a["installment"] or r["installment"] == "Y"
    return acc


def delinquent_accounts(master: Iterable[str], rec: Iterable[str], today: date,
                        master_spec: Spec = MASTER, rec_spec: Spec = REC,
                        real: tuple[str, ...] = REAL) -> list[dict[str, Any]]:  # fmt: skip
    owed = delinquent_receivables(rec, today, rec_spec)
    out = []
    for line in master:
        m = _slice(line, master_spec)
        a = owed.get(m["account"])
        if a is None or m["roll"] not in real:
            continue
        out.append({**m, "amount": str(a["amount"]), "years": sorted(a["years"]),
                    "judged": a["judged"].isoformat() if a["judged"] else None,
                    "lawsuits": sorted(a["lawsuits"]), "bankruptcies": sorted(a["bankruptcies"]),
                    "installment": a["installment"]})  # fmt: skip
    return sorted(out, key=lambda r: str(r["account"]))


class TarrantTaxRollDelinquent(Adapter):
    source_id: ClassVar[str] = "tx.tarrant.tax_roll_delinquent"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("owner1", "owner2", "addr1", "addr2")
    # The layout, roll codes and files of this county's export; other tax offices on the same
    # collection system publish the same two files with their own positions.
    county: ClassVar[str] = COUNTY
    creditor: ClassVar[str] = CREDITOR
    label: ClassVar[str] = "Tarrant County"
    tax_label: ClassVar[str] = "property tax"  # 'business personal property tax' for those rolls
    master_spec: ClassVar[Spec] = MASTER
    rec_spec: ClassVar[Spec] = REC
    real: ClassVar[tuple[str, ...]] = REAL
    files: ClassVar[tuple[str, str]] = ("master.dat", "rec.dat")
    link_parcel: ClassVar[bool] = False  # the master's CAD number is a block/lot, not PROP_ID

    def __init__(self, client: PoliteClient | None = None) -> None:
        # robots.txt asks Crawl-delay: 30
        self.client = client or PoliteClient(min_interval_s=30.0, timeout_s=1800.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "tax",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": PAGE,
            "terms_url": PAGE,
            "terms_summary": (
                "Tarrant County Tax Office tax roll export: 'There is no charge for the "
                "information when accessed through the website', rebuilt weekly; no login. No "
                "license or use restriction stated; robots.txt disallows only site search and "
                "asks Crawl-delay: 30."
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
            raise RuntimeError(f"{self.source_id}: no TaxRoll zip link on {PAGE}")
        return m.group(1) if m.group(1).startswith("http") else HOST + m.group(1)

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {}

    def fetch(self, request: FetchRequest) -> Fetched:
        url = self.file_url()
        resp = self.client.get(url)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status} for {url}")
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        names = {n.rsplit("/", 1)[-1].lower(): n for n in z.namelist()}
        found = [next((n for k, n in sorted(names.items()) if self._is(k, want)), None)
                 for want in self.files]  # fmt: skip
        master, rec = found
        if master is None or rec is None:
            raise RuntimeError(f"{self.source_id}: {' or '.join(self.files)} missing in {url}")

        def lines(name: str) -> Iterator[str]:
            with z.open(name) as raw:
                for b in raw:
                    yield b.decode("latin-1").rstrip("\r\n")

        rows = delinquent_accounts(lines(master), lines(rec), resp.retrieved_at.date(),
                                   self.master_spec, self.rec_spec, self.real)  # fmt: skip
        limit = request.params.get("limit")
        if limit:
            rows = rows[: int(limit)]
        return Fetched(self.source_id, url, resp.retrieved_at, 200,
                       canonical_json({"file": url.rsplit("/", 1)[-1], "rows": rows}),
                       "application/json")  # fmt: skip

    def parcel_key(self, row: Mapping[str, Any]) -> str | None:
        """The tx.statewide.parcels PROP_ID the account's row names, when link_parcel is set:
        the appraisal-district number as printed (Collin)."""
        cad = str(row.get("cad_id") or "").strip()
        return cad or None if self.link_parcel else None

    @staticmethod
    def _is(name: str, want: str) -> bool:
        """'master.dat' is that file; 'am*.dat' is any file of that prefix and extension."""
        if "*" not in want:
            return name == want
        head, tail = want.split("*", 1)
        return name.startswith(head) and name.endswith(tail)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        for r in json.loads(fetched.content).get("rows") or []:
            account = str(r.get("account") or "")
            names = [n for n in (" ".join(str(r.get(k) or "").split())
                                 for k in ("owner1", "owner2")) if n]  # fmt: skip
            years = [int(y) for y in r.get("years") or []]
            amount = Decimal(str(r.get("amount") or "0"))
            if not (account and names and years and amount > 0):
                continue
            judged = date.fromisoformat(r["judged"]) if r.get("judged") else None
            ctx = RecordContext(fetched, self.county, account, "tax_account", r)
            uid = stable_id(self.source_id, "account", account)
            notes = [f"years {years[0]}-{years[-1]}" if len(years) > 1 else f"year {years[0]}"]
            if r.get("lawsuits"):
                notes.append("lawsuit " + ", ".join(r["lawsuits"]))
            if r.get("bankruptcies"):
                notes.append("bankruptcy " + ", ".join(r["bankruptcies"]))
            if r.get("installment"):
                notes.append("installment agreement")
            kind = "Tax suit judgment" if judged else f"Delinquent {self.tax_label}"
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=account, book_type=None,
                book=None, page=None,
                doc_type_raw=f"{self.label} {kind.lower()} (" + "; ".join(notes) + ")",
                doc_type="COURT_ORDER" if judged else "TAX_LIEN_STATE",
                recorded_on=judged or date(years[0], 1, 1), recorded_seq=None,
                executed_on=None, consideration=None, principal_amount=amount,
                max_secured_amount=None, maturity_date=None, amount_source="index",
                legal_desc_raw=None,
            )  # fmt: skip
            cad = self.parcel_key(r)
            if cad:
                yield ctx.fact("instrument_parcel", instrument_uid=uid,
                               parcel_uid=f"{self.county}-{cad}", method="index_parcel_id",
                               evidence={"cad_id": r.get("cad_id"),
                                         "account": account})  # fmt: skip
            z = str(r.get("zip") or "")[:5]
            line = " ".join(x for x in (r.get("addr1"), r.get("addr2")) if x) or None
            addr = normalized_address(line, r.get("city") or None, r.get("state") or None,
                                      z if z.isdigit() and len(z) == 5 else None)  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            for seq, name in enumerate(names, start=1):
                nc = classify(name)
                pid = stable_id(self.source_id, account, "debtor", clean(name))
                yield ctx.fact("party", party_id=pid, raw_name=name, party_kind=nc.party_kind,
                               org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                               address_id=addr["address_id"] if addr else None)  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid,
                               role="debtor", seq=seq)  # fmt: skip
            cr = classify(self.creditor)
            cid = stable_id(self.source_id, "creditor", clean(self.creditor))
            yield ctx.fact("party", party_id=cid, raw_name=self.creditor, party_kind=cr.party_kind,
                           org_form=cr.org_form, org_name_norm=cr.org_name_norm,
                           address_id=None)  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=cid,
                           role="creditor", seq=1)  # fmt: skip

    def health(self) -> HealthReport:
        try:
            url = self.file_url()
        except RuntimeError as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        return HealthReport(self.source_id, True, datetime.now(UTC), f"tax roll {url}")


class TarrantPersonalPropertyDelinquent(TarrantTaxRollDelinquent):
    """The same roll's business personal property accounts (roll code 02, as in the
    collection system's roll code list: 01 real, 02 personal, 03 mineral). Texas personal
    property tax is a lien on that property (Tax Code 32.01); each account is a TAX_LIEN_STATE
    (or, with a judgment, COURT_ORDER) instrument owed by the business, with no parcel."""

    source_id: ClassVar[str] = "tx.tarrant.personal_property_delinquent"
    adapter_version: ClassVar[str] = "1"
    real: ClassVar[tuple[str, ...]] = ("02",)
    tax_label: ClassVar[str] = "business personal property tax"


class TarrantMineralTaxDelinquent(TarrantTaxRollDelinquent):
    """The same roll's mineral interest accounts (roll code 03) with past-due tax: owners of
    oil and gas interests behind on their tax (243,044 accounts, $17.3M base tax, 466 with a
    tax-suit judgment on the 2026-11-25 roll). The mineral estate is real property in Texas
    and the tax a lien on it (Tax Code 32.01); each account is a TAX_LIEN_STATE (or, with a
    judgment, COURT_ORDER) instrument on the interest's parcel in tx.tarrant.mineral_interests
    ('48439-MIN-<account>'), which lists the interests that have an appraised value."""

    source_id: ClassVar[str] = "tx.tarrant.mineral_tax_delinquent"
    adapter_version: ClassVar[str] = "1"
    real: ClassVar[tuple[str, ...]] = ("03",)
    tax_label: ClassVar[str] = "mineral interest tax"
    link_parcel: ClassVar[bool] = True

    def parcel_key(self, row: Mapping[str, Any]) -> str | None:
        account = str(row.get("account") or "").strip()
        return f"MIN-{account}" if account else None
