"""WV statewide parcel attributes (WVGISTC `WV_Parcels` MapServer, table 11 `ParcelSummary`).

Source: WV GIS Technical Center, built annually from county assessor GIS + the State Tax
Department's IAS. Free (SB 588, 2017). Robots: no restrictions (checked 2026-11-15). One fetch
pulls a whole county, ordered by ID, so normalize() sees every row for a parcel together.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from datetime import UTC, date
from typing import Any, ClassVar

from equity.adapters.arcgis_adapter import ArcGISCountyAdapter
from equity.adapters.base import Fetched, FetchRequest, NormalizedRow
from equity.adapters.rows import RecordContext
from equity.adapters.wv.parcel_ids import county_fips, normalize_parid, parcel_uid_from_clean
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

LAYER = (
    "https://services.wvgis.wvu.edu/arcgis/rest/services/Planning_Cadastre/WV_Parcels/MapServer/11"
)
FIELDS: tuple[str, ...] = (
    "ID", "CleanParcelID", "CountyCode", "ParcelID", "DistrictCode", "Map", "ParcelNumber",
    "Suffix", "Cards", "TaxYear", "TaxClass", "DeedBook", "DeedPage",
    "Owner1", "Owner2", "CareOf", "OwnerAddress1", "OwnerAddress2", "OwnerAddress3",
    "OwnerCity", "OwnerStateCode", "OwnerZipCode",
    "LandAppraisal", "BuildingAppraisal", "TotalAppraisal",
)  # fmt: skip
# Fields replaced with pseudonyms when recording fixtures for this public repo.
PII_FIELDS: tuple[str, ...] = (
    "Owner1", "Owner2", "CareOf", "OwnerAddress1", "OwnerAddress2", "OwnerAddress3",
)  # fmt: skip
_ZIP = re.compile(r"^\s*(\d{5})")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _money(value: Any) -> str | None:
    if value is None:
        return None
    return f"{float(value):.2f}"


def valid_from_for(tax_year: int, rule: str) -> date:
    if rule == "tax_year_jan1":
        return date(tax_year, 1, 1)
    if rule == "prior_july1":
        return date(tax_year - 1, 7, 1)
    raise ValueError(f"unknown assessment_valid_from rule {rule!r}")


def choose_row(rows: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Pick one ParcelSummary row per CleanParcelID.

    Some parcels appear twice under two ParcelID spellings, one a zero-value stub with
    Cards = 0. Rule: prefer a row with Cards > 0, then the lowest ID.
    """
    return min(rows, key=lambda a: (0 if (a.get("Cards") or 0) > 0 else 1, int(a["ID"])))


def address_row(a: Mapping[str, Any]) -> dict[str, Any] | None:
    parts = [_text(a.get(k)) for k in ("OwnerAddress1", "OwnerAddress2", "OwnerAddress3")]
    lines = [p for p in parts if p]
    city, state = _text(a.get("OwnerCity")), _text(a.get("OwnerStateCode"))
    zip_match = _ZIP.match(str(a.get("OwnerZipCode") or ""))
    zip5 = zip_match.group(1) if zip_match else None
    if not (lines or city or zip5):
        return None
    norm_key = "|".join(clean(x or "") for x in (" ".join(lines), city, state, zip5))
    return {
        "address_id": stable_id("address", norm_key),
        "line1": lines[0] if lines else None,
        "line2": " ".join(lines[1:]) or None,
        "city": city,
        "state": state,
        "zip5": zip5,
        "norm_key": norm_key,
    }


class WVStatewideParcels(ArcGISCountyAdapter):
    source_id: ClassVar[str] = "wv.statewide.parcels"
    adapter_version: ClassVar[str] = "1"
    layer_url: ClassVar[str] = LAYER
    fields: ClassVar[tuple[str, ...]] = FIELDS
    order_by: ClassVar[tuple[str, ...]] = ("ID",)
    pii_fields: ClassVar[tuple[str, ...]] = PII_FIELDS
    health_where: ClassVar[str] = "CountyCode=31"

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "parcel_statewide",
            "jurisdiction": "54",
            "access_method": "arcgis",
            "base_url": LAYER,
            "terms_url": "https://data.wvgis.wvu.edu/",
            "terms_summary": (
                "Free download under SB 588 (2017); as-is disclaimer; no license text found; "
                "commercial reuse not yet confirmed in writing"
            ),
            "terms_checked_on": date(2026, 11, 15),
            "robots_checked_on": date(2026, 11, 15),
            "cost_model": "free",
        }

    def where(self, request: FetchRequest) -> str:
        """params: county_number (1-55)."""
        county = int(request.params["county_number"])
        county_fips(county)  # validates the range
        return f"CountyCode={county}"

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        groups: dict[str, list[Mapping[str, Any]]] = {}
        for attrs in self.attributes(fetched):
            key = _text(attrs.get("CleanParcelID"))
            if key is not None:
                groups.setdefault(key, []).append(attrs)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        rule = str(self.params["assessment_valid_from"])
        for clean_id in sorted(groups):
            a = choose_row(groups[clean_id])
            county = int(a["CountyCode"])
            ctx = RecordContext(fetched, county_fips(county), clean_id, "parcel_summary", dict(a))
            yield ctx.source_record()
            uid = parcel_uid_from_clean(clean_id)
            parid = _text(a.get("ParcelID"))
            yield ctx.fact(
                "parcel",
                parcel_uid=uid,
                district=None if a.get("DistrictCode") is None else f"{int(a['DistrictCode']):02d}",
                map=_text(a.get("Map")),
                parcel_no=_text(a.get("ParcelNumber")),
                subparcel=_text(a.get("Suffix")),
                parid_raw=normalize_parid(parid) if parid else clean_id[2:],
            )
            addr = address_row(a)
            if addr is not None:
                yield NormalizedRow("address", addr)
            owners = [n for n in (_text(a.get("Owner1")), _text(a.get("Owner2"))) if n]
            for seq, name in enumerate(owners, start=1):
                nc = classify(name)
                party_id = stable_id(self.source_id, clean_id, "owner", str(seq), clean(name))
                yield ctx.fact(
                    "party",
                    party_id=party_id,
                    raw_name=name,
                    party_kind=nc.party_kind,
                    org_form=nc.org_form,
                    org_name_norm=nc.org_name_norm,
                    address_id=None if addr is None else addr["address_id"],
                )
                yield ctx.fact(
                    "owner_snapshot",
                    parcel_uid=uid,
                    owner_seq=seq,
                    party_id=party_id,
                    deed_book=_text(a.get("DeedBook")),
                    deed_page=_text(a.get("DeedPage")),
                    observed_on=observed,
                )
            if a.get("TaxYear"):
                year = int(a["TaxYear"])
                yield ctx.fact(
                    "parcel_assessment",
                    parcel_uid=uid,
                    tax_year=year,
                    appraised_land=_money(a.get("LandAppraisal")),
                    appraised_bldg=_money(a.get("BuildingAppraisal")),
                    appraised_total=_money(a.get("TotalAppraisal")),
                    tax_class=_text(a.get("TaxClass")),
                    valid_from=valid_from_for(year, rule),
                )
