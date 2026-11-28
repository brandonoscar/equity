"""Tarrant County, TX mineral interests on the Tax Office roll: owners of appraised oil and gas
interests, as owner records.

In Texas a mineral interest is real property, appraised and taxed on its own account. The Tax
Office's free weekly roll (TaxRollYYYYMMDD.zip, the same file tx.tarrant.tax_roll_delinquent
reads; "Tax Roll Record Definition", November 2026) carries every mineral account as roll
code 03 in Master.DAT: the owner names and mailing address, the legal description (well,
lease number, operator, field and the owner's decimal interest, e.g. 'OLIVER #1 91210030-000
BRG LONE STAR /NEWARK, EAST (BARNETT 0.01228200'), and the current year's land and improvement
values. On the 2026-11-25 roll: 1,740,541 mineral accounts and 284,323 owners, $1.29B
appraised; 1,490,305 accounts are appraised at $0 (no production) and are not read.

Each account with a value is one parcel row keyed '48439-MIN-<account>' (a mineral interest has
no lot or situs; the prefix keeps it apart from tx.statewide.parcels keys), its owners as
owner_snapshot parties with the mailing address, and a parcel_assessment for the roll's year
with the land and improvement values. A debtor matched to one of these owners holds a
producing mineral interest of that appraised value.
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
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.adapters.tx.tarrant_taxroll import HOST as TARRANT_HOST
from equity.adapters.tx.tarrant_taxroll import LINK, PAGE, Spec, _slice
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

COUNTY = "48439"
MINERAL = "03"
FIELDS: Spec = (("account", 1, 30), ("roll", 34, 35), ("legal", 36, 155), ("cad_id", 169, 198),
                ("owner1", 327, 376), ("owner2", 377, 426), ("addr1", 427, 456),
                ("addr2", 457, 486), ("city", 487, 516), ("state", 517, 536), ("zip", 537, 554),
                ("land", 667, 677), ("improvement", 678, 688))  # fmt: skip
ROLL_DATE = re.compile(r"TaxRoll(\d{4})(\d{2})(\d{2})\.zip$", re.I)


def _dollars(v: str) -> int:
    s = v.strip()
    return int(s) if s.isdigit() else 0


def mineral_accounts(lines: Iterable[str]) -> list[dict[str, Any]]:
    """Mineral (roll 03) master records with an appraised value, in file order."""
    out = []
    for line in lines:
        r = _slice(line, FIELDS)
        land, imp = _dollars(r["land"]), _dollars(r["improvement"])
        if r["roll"] != MINERAL or not r["account"] or land + imp <= 0:
            continue
        out.append({**{k: r[k] for k in ("account", "legal", "cad_id", "owner1", "owner2",
                                         "addr1", "addr2", "city", "state", "zip")},
                    "land": land, "improvement": imp})  # fmt: skip
    return out


class TarrantMineralInterests(Adapter):
    source_id: ClassVar[str] = "tx.tarrant.mineral_interests"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("owner1", "owner2", "addr1", "addr2")

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
                "Tarrant County Tax Office tax roll export (mineral accounts, roll code 03): "
                "'There is no charge for the information when accessed through the website', "
                "rebuilt weekly; no login. No license or use restriction stated; robots.txt "
                "disallows only site search and asks Crawl-delay: 30."
            ),
            "terms_checked_on": "2026-11-28",
            "robots_checked_on": "2026-11-28",
            "cost_model": "free",
        }

    def file_url(self) -> str:
        resp = self.client.get(PAGE)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status} for the tax-roll page")
        m = LINK.search(resp.content.decode("utf-8", "replace"))
        if m is None:
            raise RuntimeError(f"{self.source_id}: no TaxRoll zip link on {PAGE}")
        return m.group(1) if m.group(1).startswith("http") else TARRANT_HOST + m.group(1)

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {}

    def fetch(self, request: FetchRequest) -> Fetched:
        url = self.file_url()
        resp = self.client.get(url)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status} for {url}")
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        names = {n.rsplit("/", 1)[-1].lower(): n for n in z.namelist()}
        if "master.dat" not in names:
            raise RuntimeError(f"{self.source_id}: Master.DAT missing in {url}")
        with z.open(names["master.dat"]) as raw:
            rows = mineral_accounts(b.decode("latin-1").rstrip("\r\n") for b in raw)
        limit = request.params.get("limit")
        if limit:
            rows = rows[: int(limit)]
        m = ROLL_DATE.search(url)
        roll_date = date(int(m[1]), int(m[2]), int(m[3])).isoformat() if m else None
        return Fetched(self.source_id, url, resp.retrieved_at, 200,
                       canonical_json({"file": url.rsplit("/", 1)[-1], "roll_date": roll_date,
                                       "rows": rows}),
                       "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        roll = data.get("roll_date")
        observed = date.fromisoformat(roll) if roll else fetched.retrieved_at.date()
        year = observed.year
        for r in data.get("rows") or []:
            account = str(r.get("account") or "")
            names = [n for n in (" ".join(str(r.get(k) or "").split())
                                 for k in ("owner1", "owner2")) if n]  # fmt: skip
            land, imp = int(r.get("land") or 0), int(r.get("improvement") or 0)
            if not (account and names and land + imp > 0):
                continue
            uid = f"{COUNTY}-MIN-{account}"
            ctx = RecordContext(fetched, COUNTY, account, "mineral_interest", r)
            yield ctx.source_record()
            legal = " ".join(str(r.get("legal") or "").split()) or None
            yield ctx.fact("parcel", parcel_uid=uid, parid_raw=account, situs_address_id=None,
                           land_use_code="MINERAL",
                           land_use_desc=(f"Mineral interest: {legal}" if legal
                                          else "Mineral interest"),
                           zoning=None)  # fmt: skip
            z = str(r.get("zip") or "")[:5]
            line = " ".join(x for x in (r.get("addr1"), r.get("addr2")) if x) or None
            addr = normalized_address(line, r.get("city") or None, r.get("state") or None,
                                      z if z.isdigit() and len(z) == 5 else None)  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            for seq, name in enumerate(names, start=1):
                nc = classify(name)
                pid = stable_id(self.source_id, account, "owner", str(seq), clean(name))
                yield ctx.fact("party", party_id=pid, raw_name=name, party_kind=nc.party_kind,
                               org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                               address_id=addr["address_id"] if addr else None)  # fmt: skip
                yield ctx.fact("owner_snapshot", parcel_uid=uid, owner_seq=seq, party_id=pid,
                               deed_book=None, deed_page=None, owner_type=None,
                               observed_on=observed)  # fmt: skip
            yield ctx.fact("parcel_assessment", parcel_uid=uid, tax_year=year,
                           valid_from=date(year, 1, 1), homestead=None,
                           appraised_land=Decimal(land), appraised_bldg=Decimal(imp),
                           appraised_total=Decimal(land + imp),
                           assessed_value=None)  # fmt: skip

    def health(self) -> HealthReport:
        try:
            url = self.file_url()
        except RuntimeError as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        return HealthReport(self.source_id, True, datetime.now(UTC), f"tax roll {url}")
