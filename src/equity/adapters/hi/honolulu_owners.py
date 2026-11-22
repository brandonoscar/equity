"""Honolulu (Oahu) owners and assessed values from the City & County HOLIS cadastral tables.

The statewide Hawaii TMK layer has boundaries only. Honolulu publishes the Real Property
Assessment Division's tables on ArcGIS Online, refreshed weekly:
  OWNALL  (layer 5)  one row per owner record of each parcel: own1/own2, mailing paddr1..3
  ASMTGIS (layer 9)  land and building values and net taxable value per parcel and tax year
Terms (item licenseInfo): derived from public records, no warranty; no use restriction.

A parcel id (parid) is the 8-digit TMK plus a 4-digit CPR suffix. Suffix 0000 is the lot
itself and keys to the statewide parcel ("15003-1" + TMK). A CPR unit (condominium-style
unit, suffix > 0000) gets its own parcel_uid, "15003-1<TMK>-<suffix>", and a parcel_link
(condo_unit_of) to its lot, as NYC condo units do.

Partitions are the first two TMK digits (zone and section). valid_from is January 1 of the
tax year: the table does not say when Honolulu's tax year starts.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from equity.adapters.arcgis import ArcGISQuery, fetch_all, get_json
from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

BASE = "https://services.arcgis.com/tNJpAOha4mODLkXz/arcgis/rest/services/CadastralTables/FeatureServer"
OWNERS = f"{BASE}/5"
VALUES = f"{BASE}/9"
COUNTY = "15003"
OWNER_FIELDS = ("objectid", "tmk", "suffix", "parid", "taxyr", "own1", "own2", "ownseq",
                "owntble", "ownfld", "owntype1", "paddr1", "paddr2", "paddr3")  # fmt: skip
VALUE_FIELDS = ("objectid", "tmk", "suffix", "parid", "taxyr", "seq", "landvalue",
                "buildingvalue", "tnettaxval")  # fmt: skip
_CITY_ST_ZIP = re.compile(
    r"^\s*(?P<city>.*?)\s+(?P<st>[A-Z]{2})\s+(?P<zip>[0-9]{5})(?:-?[0-9]{4})?\s*$"
)
_NULL = {"", "NULL", "NONE"}


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return None if s.upper() in _NULL else s


def _money(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() and d >= 0 else None


def parcel_uid(tmk: str, suffix: str) -> str:
    lot = f"{COUNTY}-1{tmk}"
    return lot if suffix in ("", "0000") else f"{lot}-{suffix}"


def mailing(a: Mapping[str, Any]) -> dict[str, Any] | None:
    line = " ".join(x for x in (_text(a.get("paddr1")), _text(a.get("paddr2"))) if x) or None
    last = _text(a.get("paddr3")) or ""
    m = _CITY_ST_ZIP.match(last.upper())
    if m:
        return normalized_address(line, m.group("city"), m.group("st"), m.group("zip"))
    return normalized_address(line, last or None, None, None)  # foreign or unparsed


class HonoluluOwners(Adapter):
    source_id: ClassVar[str] = "hi.honolulu.owners"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "arcgis"
    pii_fields: ClassVar[tuple[str, ...]] = ("own1", "own2", "paddr1", "paddr2")
    page_size: ClassVar[int] = 2000

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "assessor",
            "jurisdiction": COUNTY,
            "access_method": "arcgis",
            "base_url": BASE,
            "terms_url": "https://www.arcgis.com/home/item.html?id=fb6c49f86f474b2782e954b339655060",
            "terms_summary": (
                "City & County of Honolulu HOLIS CadastralTables (Real Property Assessment "
                "Division data, weekly). licenseInfo: derived from public records, not legal "
                "representations, no warranty; no use restriction stated."
            ),
            "terms_checked_on": "2026-11-22",
            "robots_checked_on": "2026-11-22",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        for i in range(10, 100):
            yield {"prefix": f"{i:02d}"}

    def fetch(self, request: FetchRequest) -> Fetched:
        prefix = request.params["prefix"]
        if not (len(prefix) == 2 and prefix.isdigit()):
            raise ValueError(f"bad TMK prefix {prefix!r}")
        limit = request.params.get("limit")
        where = f"tmk LIKE '{prefix}%'"
        size = int(limit) if limit else self.page_size
        owners, resp = fetch_all(self.client, ArcGISQuery(OWNERS, where, OWNER_FIELDS,
                                 ("objectid",), size), max_pages=1 if limit else 10_000,
                                 sample=limit is not None)  # fmt: skip
        if limit:  # a fixture keeps the values of the parcels its owners hold
            ids = sorted({str(f["attributes"]["parid"]) for f in owners})
            where = "parid IN (" + ",".join(f"'{p}'" for p in ids if p.isdigit()) + ")"
        values, _ = fetch_all(self.client, ArcGISQuery(VALUES, where, VALUE_FIELDS,
                              ("objectid",), self.page_size))  # fmt: skip
        body = canonical_json({"owners": [f["attributes"] for f in owners],
                               "values": [f["attributes"] for f in values]})  # fmt: skip
        return Fetched(self.source_id, f"{BASE}?prefix={prefix}", resp[-1].retrieved_at, 200,
                       body, "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        import json

        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        by_parcel: dict[str, dict[str, list[Mapping[str, Any]]]] = {}
        for kind in ("owners", "values"):
            for a in data.get(kind) or []:
                tmk, suffix = str(a.get("tmk") or ""), str(a.get("suffix") or "0000")
                if not (len(tmk) == 8 and tmk.isdigit() and len(suffix) == 4 and suffix.isdigit()):
                    continue
                by_parcel.setdefault(f"{tmk}{suffix}", {"owners": [], "values": []})[kind].append(a)
        for parid in sorted(by_parcel):
            tmk, suffix = parid[:8], parid[8:]
            uid = parcel_uid(tmk, suffix)
            rows = by_parcel[parid]
            ctx = RecordContext(fetched, COUNTY, parid, "parcel", rows)
            yield ctx.source_record()
            yield ctx.fact("parcel", parcel_uid=uid, parid_raw=parid, situs_address_id=None,
                           land_use_code=None, land_use_desc=None, zoning=None)  # fmt: skip
            if uid != parcel_uid(tmk, "0000"):
                yield ctx.fact("parcel_link", from_parcel_uid=uid,
                               to_parcel_uid=parcel_uid(tmk, "0000"), link_type="condo_unit_of",
                               detail=f"CPR {suffix}")  # fmt: skip
            ordered = sorted(rows["owners"], key=lambda a: (
                int(a.get("ownseq") or 0), str(a.get("owntble")), str(a.get("ownfld")),
                int(a.get("objectid") or 0)))  # fmt: skip
            seen: set[str] = set()
            seq = 0
            for a in ordered:
                addr = mailing(a)
                if addr is not None:
                    yield NormalizedRow("address", addr)
                for name in (_text(a.get("own1")), _text(a.get("own2"))):
                    if not name or clean(name) in seen:
                        continue
                    seen.add(clean(name))
                    seq += 1
                    nc = classify(name)
                    party_id = stable_id(self.source_id, parid, "owner", str(seq), clean(name))
                    yield ctx.fact(
                        "party",
                        party_id=party_id,
                        raw_name=name,
                        party_kind=nc.party_kind,
                        org_form=nc.org_form,
                        org_name_norm=nc.org_name_norm,
                        address_id=addr["address_id"] if addr else None,
                    )
                    yield ctx.fact(
                        "owner_snapshot",
                        parcel_uid=uid,
                        owner_seq=seq,
                        party_id=party_id,
                        deed_book=None,
                        deed_page=None,
                        owner_type=_text(a.get("owntype1")),
                        observed_on=observed,
                    )
            years: dict[int, Mapping[str, Any]] = {}
            for v in sorted(rows["values"], key=lambda a: int(a.get("seq") or 0)):
                y = v.get("taxyr")
                if isinstance(y, int) and 1800 <= y <= 2200:
                    years[y] = v  # the highest seq of a year wins
            for year in sorted(years):
                v = years[year]
                land, bldg = _money(v.get("landvalue")), _money(v.get("buildingvalue"))
                total = land + bldg if land is not None and bldg is not None else None
                yield ctx.fact(
                    "parcel_assessment",
                    parcel_uid=uid,
                    tax_year=year,
                    appraised_land=land,
                    appraised_bldg=bldg,
                    appraised_total=total,
                    assessed_value=_money(v.get("tnettaxval")),
                    tax_class=None,
                    valid_from=date(year, 1, 1),
                    valid_to=None,
                    homestead=None,
                )

    def health(self) -> HealthReport:
        body = get_json(self.client, OWNERS + "/query",
                        {"where": "1=1", "returnCountOnly": "true", "f": "json"})  # fmt: skip
        n = int(body.get("count") or 0)
        return HealthReport(self.source_id, n > 500_000, datetime.now(UTC), f"{n} owner rows")
