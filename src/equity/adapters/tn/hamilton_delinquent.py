"""Hamilton County, TN Trustee delinquent tax file: unpaid real property tax bills.

The county publishes the Trustee's delinquent file free on hamiltontn.gov (Property Records >
Delinquent Tax Download): "a current list of all records that are considered delinquent in the
Trustee's Office", rebuilt monthly (CTRUDELQ.TXT, 810-byte fixed-width records, layout in
CTRUDELQ.PDF on the same page; the CSV twin breaks about 460 records across lines, so the text
file is read). Each record is one tax bill: map, group and parcel, the owner names and mailing
lines on the bill, the bill year and number, the property address, and the county, municipal
and stormwater amounts still owed. Map 'PER' is business personal property (about 40,000 of
52,477 records on the 2026-11-01 file); only real property bills are read here.

Each bill is one TAX_LIEN_STATE instrument (Tennessee property tax is a lien on the property
from January 1 of the tax year, T.C.A. 67-5-2101) owed by the owner named on that bill, dated
January 1 of the bill year, with the county + municipal + stormwater amount owed. Bills more
than a year past due are suits in Chancery Court; the back-tax indicator is kept in the raw
type. The parcel is the GISLINK of tn.hamilton.parcels: '033' (the state's county number) +
map + group + parcel as five digits ('137A', 'T', '016' -> '033137AT01600'); a condominium
unit suffix ('002   C037') names no GISLINK, so no parcel link is made for it.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.liens import split_address
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PAGE = "https://hamiltontn.gov/DownloadRecords.aspx"
URL = "https://www.hamiltontn.gov/_downloadsTrusteeDelinquent/CTRUDELQ.zip"
COUNTY = "47065"
STATE_COUNTY_NO = "033"
CREDITOR = "Hamilton County Trustee"
RECORD = 810
# (name, start, length): 1-based start columns from the Trustee's layout
FIELDS = (("map", 9, 5), ("group", 14, 3), ("parcel", 17, 10), ("owner1", 27, 35),
          ("year", 62, 4), ("bill", 66, 6), ("owner2", 80, 35), ("mail1", 115, 35),
          ("mail2", 150, 35), ("mail3", 185, 35), ("situs", 340, 30), ("back_tax", 572, 2),
          ("county_owed", 593, 9), ("mun_owed", 602, 9), ("stw_owed", 611, 9))  # fmt: skip
PARCEL = re.compile(r"^(\d{1,3})(?:\.(\d{1,2}))?$")
CSZ = re.compile(r"\b[A-Z]{2}\s+\d{5}(?:-?\d{4})?$")


def parse_record(line: str) -> dict[str, str]:
    return {name: line[a - 1 : a - 1 + n].strip() for name, a, n in FIELDS}


def _cents(v: str) -> int:
    return int(v) if v.isdigit() else 0


def gislink(map_: str, group: str, parcel: str) -> str | None:
    """'137A', 'T', '016' -> '033137AT01600' (tn.hamilton.parcels parcel_id, spaces removed);
    None for personal property, a condominium-unit suffix or an unreadable parcel number."""
    m = PARCEL.match(parcel)
    if map_ in ("", "PER") or not m or not re.fullmatch(r"[0-9A-Z]{2,5}", map_):
        return None
    return STATE_COUNTY_NO + map_ + group + m.group(1).zfill(3) + (m.group(2) or "").ljust(2, "0")


def delinquent_bills(lines: Iterable[str]) -> list[dict[str, Any]]:
    """Real property bills with an amount owed, one row each, in file order."""
    out = []
    for line in lines:
        if len(line) < RECORD - 1:
            continue
        r = parse_record(line)
        cents = sum(_cents(r[k]) for k in ("county_owed", "mun_owed", "stw_owed"))
        if r["map"] == "PER" or not r["map"] or cents <= 0 or not r["year"].isdigit():
            continue
        out.append({**{k: r[k] for k in ("map", "group", "parcel", "owner1", "owner2", "year",
                                         "bill", "mail1", "mail2", "mail3", "situs",
                                         "back_tax")}, "cents": cents})  # fmt: skip
    return out


def mailing(r: Mapping[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    """The bill's mailing lines as (street, city, state, zip): the last line ending 'ST 12345'
    is the city line, the lines above it the street ('2430   CAMPBELL   ST' / 'CHATT TN
    37416,'; the trailing commas are dropped, and 'CHATT, TN 37416' splits at its comma)."""
    lines = [" ".join(str(r.get(k) or "").split()).strip(" ,")
             for k in ("mail1", "mail2", "mail3")]  # fmt: skip
    lines = [x for x in lines if x]
    for i in range(len(lines) - 1, -1, -1):
        if CSZ.search(lines[i]):
            parts = split_address(lines[i], "city_state_zip" if "," in lines[i] else "city_st_zip")
            street = " ".join(lines[:i]) or None
            return street, parts.get("city"), parts.get("state"), parts.get("zip")
    return (" ".join(lines) or None), None, None, None


class HamiltonTNDelinquentTaxes(Adapter):
    source_id: ClassVar[str] = "tn.hamilton.delinquent_taxes"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("owner1", "owner2", "mail1", "mail2", "mail3",
                                             "situs")  # fmt: skip

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=1800.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "tax",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": URL,
            "terms_url": PAGE,
            "terms_summary": (
                "Hamilton County, TN Trustee delinquent tax file, a free download on the "
                "county's Download Property Records page, no login; no license or use "
                "restriction stated. hamiltontn.gov robots.txt allows all but a few "
                "directories (not this one)."
            ),
            "terms_checked_on": "2026-11-27",
            "robots_checked_on": "2026-11-27",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {}

    def fetch(self, request: FetchRequest) -> Fetched:
        resp = self.client.get(URL)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status} for {URL}")
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        names = [n for n in z.namelist() if n.lower().endswith(".txt")]
        if not names:
            raise RuntimeError(f"{self.source_id}: no .TXT file in {URL}")
        text = z.read(names[0]).decode("latin-1")
        rows = delinquent_bills(text.replace("\r\n", "\n").split("\n"))
        limit = request.params.get("limit")
        if limit:
            rows = rows[: int(limit)]
        return Fetched(self.source_id, URL, resp.retrieved_at, 200,
                       canonical_json({"file": names[0], "rows": rows}),
                       "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        seen: set[str] = set()
        for r in json.loads(fetched.content).get("rows") or []:
            names = [n for n in (" ".join(str(r.get(k) or "").split())
                                 for k in ("owner1", "owner2")) if n]  # fmt: skip
            year, cents = str(r.get("year") or ""), int(r.get("cents") or 0)
            parcel_txt = " ".join(str(r.get(k) or "") for k in ("map", "group", "parcel"))
            key = f"{' '.join(parcel_txt.split())}-{year}-{r.get('bill') or ''}"
            if not (names and year.isdigit() and cents > 0) or key in seen:
                continue
            seen.add(key)
            ctx = RecordContext(fetched, COUNTY, key, "tax_bill", r)
            uid = stable_id(self.source_id, "bill", key)
            back = " (back tax)" if str(r.get("back_tax") or "") == "Y" else ""
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=key, book_type=None,
                book=None, page=None,
                doc_type_raw=f"Hamilton County delinquent property tax, bill year {year}{back}",
                doc_type="TAX_LIEN_STATE", recorded_on=date(int(year), 1, 1),
                recorded_seq=None, executed_on=None, consideration=None,
                principal_amount=Decimal(cents) / 100, max_secured_amount=None,
                maturity_date=None, amount_source="index", legal_desc_raw=None,
            )  # fmt: skip
            link = gislink(str(r.get("map") or ""), str(r.get("group") or ""),
                           str(r.get("parcel") or ""))  # fmt: skip
            if link:
                yield ctx.fact("instrument_parcel", instrument_uid=uid,
                               parcel_uid=f"{COUNTY}-{link}", method="index_parcel_id",
                               evidence={"map": r.get("map"), "group": r.get("group"),
                                         "parcel": r.get("parcel")})  # fmt: skip
            street, city, state, zip5 = mailing(r)
            addr = normalized_address(street, city, state, zip5)
            if addr is not None:
                yield NormalizedRow("address", addr)
            for seq, name in enumerate(names, start=1):
                nc = classify(name)
                pid = stable_id(self.source_id, key, "debtor", clean(name))
                yield ctx.fact("party", party_id=pid, raw_name=name, party_kind=nc.party_kind,
                               org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                               address_id=addr["address_id"] if addr else None)  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid,
                               role="debtor", seq=seq)  # fmt: skip
            cr = classify(CREDITOR)
            cid = stable_id(self.source_id, "creditor", clean(CREDITOR))
            yield ctx.fact("party", party_id=cid, raw_name=CREDITOR, party_kind=cr.party_kind,
                           org_form=cr.org_form, org_name_norm=cr.org_name_norm,
                           address_id=None)  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=cid,
                           role="creditor", seq=1)  # fmt: skip

    def health(self) -> HealthReport:
        resp = self.client.get(PAGE)
        ok = resp.status == 200 and b"CTRUDELQ.zip" in resp.content
        return HealthReport(self.source_id, ok, datetime.now(UTC),
                            f"status={resp.status}; delinquent file link "
                            f"{'found' if ok else 'missing'}")  # fmt: skip
