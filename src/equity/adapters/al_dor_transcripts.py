"""Alabama Department of Revenue: tax-delinquent land held by the State (county transcripts).

When no one bids at a county's tax sale, the parcel is bid in to the State and the Department
of Revenue holds the certificate of sale (Code of Alabama 40-10-21). The Property Tax Division
posts, per county, a "Transcript of Tax Delinquent Land Available for Sale" (revenue.alabama.gov,
Property Tax > Tax Delinquent Property and Land Sales; "The transcripts are updated weekly"):
one PDF per DOR county code (01 Jefferson-Birmingham ... 67 Winston, 68 Jefferson-Bessemer).
Each record is the name the property was assessed in when it sold for taxes, the county code,
the year it sold to the State, the certificate of sale number, the assessment class, the city
code, the assessor's parcel id, the legal description and, on the second line, the amount due
at the time of the tax sale ("How To Read The Transcript", same page; blank on parcels sold to
the State this year until the Department posts it). The owner can redeem until the State sells
or assigns the certificate. On the 2026-11-06 transcripts: 15,992 parcels in 40 counties,
$7.84M bid at tax sale, sold to the State from 1983 to 2026 (Jefferson-Birmingham 8,977,
Jefferson-Bessemer 2,518, Montgomery 1,143).

Each record is one TAX_LIEN_STATE instrument (the State's certificate of sale) owed by the
assessed owner, dated January 1 of the year it sold to the State (the transcript gives only the
year), for the amount bid at the tax sale (none when blank). The parcel id is the DOR county
code followed by the county's own parcel number, zero-padded: the 16 characters after the code
are the parcel key of the county layers (al.jefferson.parcels PARCELID, al.montgomery.parcels
PID, ...), punctuated for Mobile ('2906130002184.000') and Baldwin and Madison
('05-66-03-08-2-000-084.001', '14-07-35-2-002-055.000') as their layers print them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.pdf_table import Text, page_texts
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import norm_parcel_id
from equity.geo import county_by_name
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PAGE = "https://www.revenue.alabama.gov/property-tax/tax-delinquent-property-and-land-sales/"
URL = ("https://www.revenue.alabama.gov/wp-content/uploads/property-tax-transcripts/"
       "WWW_TRANS_{code}.PDF")  # fmt: skip
CREDITOR = "State of Alabama Department of Revenue"
# DOR county codes, in the transcript page's order: 01-03 the three largest, then alphabetical
# (Jefferson's Bessemer Division has its own code, 68).
COUNTIES = ("Jefferson", "Mobile", "Montgomery", "Autauga", "Baldwin", "Barbour", "Bibb",
            "Blount", "Bullock", "Butler", "Calhoun", "Chambers", "Cherokee", "Chilton",
            "Choctaw", "Clarke", "Clay", "Cleburne", "Coffee", "Colbert", "Conecuh", "Coosa",
            "Covington", "Crenshaw", "Cullman", "Dale", "Dallas", "DeKalb", "Elmore", "Escambia",
            "Etowah", "Fayette", "Franklin", "Geneva", "Greene", "Hale", "Henry", "Houston",
            "Jackson", "Lamar", "Lauderdale", "Lawrence", "Lee", "Limestone", "Lowndes", "Macon",
            "Madison", "Marengo", "Marion", "Marshall", "Monroe", "Morgan", "Perry", "Pickens",
            "Pike", "Randolph", "Russell", "Shelby", "St. Clair", "Sumter", "Talladega",
            "Tallapoosa", "Tuscaloosa", "Walker", "Washington", "Wilcox", "Winston",
            "Jefferson")  # fmt: skip
COLUMNS = ("Name", "Amt Bid", "CO.", "YR.", "C/S#", "CLASS", "CODE", "PARCEL ID", "DESCRIPTION")
KEYS = ("name", "amount", "co", "yr", "cs", "class", "code", "parcel", "legal")
MONEY = re.compile(r"^[0-9][0-9,]*(?:\.[0-9]{1,2})?$")
CUT = re.compile(r"\s*(?:%|\bC/O\b).*$")


def county_parcel(code: str, parcel: str) -> str | None:
    """The county layer's parcel key for a transcript parcel id: the 16 characters after the
    two-digit county code, punctuated as Mobile, Baldwin and Madison print theirs."""
    if not (parcel.startswith(code) and len(parcel) >= 15):
        return None
    core = parcel[2:18]
    if code == "02":  # Mobile: '2906130002184.000'
        return core[:13] + "." + (core[13:] or "000")
    if code in ("05", "47") and len(core) == 16:  # Baldwin, Madison
        dashed = (f"{core[0:2]}-{core[2:4]}-{core[4:6]}-{core[6]}-{core[7:10]}-"
                  f"{core[10:13]}.{core[13:16]}")  # fmt: skip
        return ("05-" + dashed) if code == "05" else dashed
    return core


def owner_name(raw: str) -> str:
    """'RICK LEON WAYNE & MARY BETH % KENDAL POWELL' -> 'RICK LEON WAYNE & MARY BETH';
    'HOLMES BESSIE LEE &' -> 'HOLMES BESSIE LEE' (a name cut off at the column edge)."""
    name = " ".join(CUT.sub("", raw.upper()).split())
    return re.sub(r"(?:\s*(?:&|,|\bOR\b|\bAND\b))+$", "", name).strip()


def transcript_rows(texts: Iterable[Text]) -> list[dict[str, str]]:
    """Records of one transcript, in page order: each line with a certificate number is a
    record; the first dollar amount left of the CO. column after it is its amount bid."""
    lines: dict[tuple[int, float], list[Text]] = {}
    for t in texts:
        key = next((k for k in lines if k[0] == t.page and abs(k[1] - t.y) <= 2.0), None)
        lines.setdefault(key or (t.page, t.y), []).append(t)
    starts: list[float] | None = None
    out: list[dict[str, str]] = []
    pending: dict[str, str] | None = None
    for _, line in sorted(lines.items(), key=lambda kv: (kv[0][0], -kv[0][1])):
        line = sorted(line, key=lambda t: t.x)
        words = [t.text.strip() for t in line]
        if words and words[0] == "Name" and any(w.startswith("Amt Bid") for w in words):
            pos = [next((t.x for t in line if t.text.strip().startswith(c)), None)
                   for c in COLUMNS]  # fmt: skip
            starts = [float(x) for x in pos if x is not None]
            starts = starts if len(starts) == len(COLUMNS) else None
            continue
        if starts is None:
            continue
        cells = [""] * len(starts)
        for t in line:
            col = max((i for i, s in enumerate(starts) if s <= t.x + 2.0), default=0)
            cells[col] = (cells[col] + " " + t.text.strip()).strip()
        r = dict(zip(KEYS, cells, strict=True))
        if re.fullmatch(r"\d{8}", r["cs"]) and re.fullmatch(r"\d\d", r["co"]):
            pending = {k: r[k] for k in KEYS if k != "amount"}
            out.append(pending)
            continue
        money = next((t.text.strip() for t in line if t.x < starts[2] - 1.0
                      and MONEY.match(t.text.strip())), None)  # fmt: skip
        if pending is not None and money and "amount" not in pending:
            pending["amount"] = money.replace(",", "")
    return out


class AlabamaStateHeldTaxLand(Adapter):
    source_id: ClassVar[str] = "al.dor.state_held_tax_land"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("name",)

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=600.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "tax",
            "jurisdiction": "01",
            "access_method": "bulk",
            "base_url": PAGE,
            "terms_url": PAGE,
            "terms_summary": (
                "Alabama Department of Revenue 'Transcripts of Delinquent Property' (Property "
                "Tax > Tax Delinquent Property and Land Sales), one free PDF per county, "
                "updated weekly, no login; no license or use restriction stated. "
                "revenue.alabama.gov/robots.txt disallows only /wp-admin/."
            ),
            "terms_checked_on": "2026-11-28",
            "robots_checked_on": "2026-11-28",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        for i in range(1, len(COUNTIES) + 1):
            yield {"code": f"{i:02d}"}

    def fetch(self, request: FetchRequest) -> Fetched:
        code = str(request.params.get("code") or "01")
        url = URL.format(code=code)
        resp = self.client.get(url)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status} for {url}")
        texts = page_texts(resp.content)
        if not texts:
            raise RuntimeError(f"{self.source_id}: no text in {url}")
        stamp = re.search(r"\d{2}/\d{2}/\d{4}", " ".join(t.text for t in texts[:12]))
        rows = transcript_rows(texts)
        limit = request.params.get("limit")
        if limit:
            rows = rows[: int(limit)]
        return Fetched(self.source_id, url, resp.retrieved_at, 200,
                       canonical_json({"code": code, "as_of": stamp[0] if stamp else None,
                                       "rows": rows}),
                       "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        code = str(data.get("code") or "")
        if not (code.isdigit() and 1 <= int(code) <= len(COUNTIES)):
            return
        county = county_by_name("AL", COUNTIES[int(code) - 1])
        century = fetched.retrieved_at.year % 100
        for r in data.get("rows") or []:
            name, cs = owner_name(str(r.get("name") or "")), str(r.get("cs") or "")
            yr, amount = str(r.get("yr") or ""), str(r.get("amount") or "")
            if not (
                name
                and re.fullmatch(r"\d{8}", cs)
                and re.fullmatch(r"\d\d", yr)
                and str(r.get("co")) == code
                and (not amount or MONEY.match(amount))
            ):
                continue  # fmt: skip
            year = (1900 if int(yr) > century else 2000) + int(yr)
            ctx = RecordContext(fetched, county.fips5, cs, "state_held_tax_parcel", r)
            uid = stable_id(self.source_id, "certificate", cs)
            yield ctx.source_record()
            legal = " ".join(str(r.get("legal") or "").split()) or None
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=cs, book_type=None,
                book=None, page=None,
                doc_type_raw=(f"Alabama certificate of sale held by the State (sold to the "
                              f"State {year}), {county.name}"),
                doc_type="TAX_LIEN_STATE", recorded_on=date(year, 1, 1), recorded_seq=None,
                executed_on=None, consideration=None,
                principal_amount=Decimal(amount) if amount else None, max_secured_amount=None,
                maturity_date=None, amount_source="index", legal_desc_raw=legal,
            )  # fmt: skip
            parcel = str(r.get("parcel") or "")
            key = county_parcel(code, parcel)
            if key:
                yield ctx.fact("instrument_parcel", instrument_uid=uid,
                               parcel_uid=f"{county.fips5}-{norm_parcel_id(key)}",
                               method="index_parcel_id",
                               evidence={"code": code, "parcel": parcel})  # fmt: skip
            nc = classify(name)
            pid = stable_id(self.source_id, cs, "debtor", clean(name))
            yield ctx.fact("party", party_id=pid, raw_name=name, party_kind=nc.party_kind,
                           org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                           address_id=None)  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid,
                           role="debtor", seq=1)  # fmt: skip
            cr = classify(CREDITOR)
            cid = stable_id(self.source_id, "creditor", clean(CREDITOR))
            yield ctx.fact("party", party_id=cid, raw_name=CREDITOR, party_kind=cr.party_kind,
                           org_form=cr.org_form, org_name_norm=cr.org_name_norm,
                           address_id=None)  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=cid,
                           role="creditor", seq=1)  # fmt: skip

    def health(self) -> HealthReport:
        resp = self.client.get(PAGE)
        ok = resp.status == 200 and b"WWW_TRANS_01" in resp.content
        return HealthReport(self.source_id, ok, datetime.now(UTC),
                            f"status={resp.status}; transcript links "
                            f"{'found' if ok else 'missing'}")  # fmt: skip
