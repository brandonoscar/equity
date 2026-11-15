"""WV statewide delinquent properties (WVGISTC `Delinquent_Properties` MapServer, layer 0).

Built weekly from the State Auditor's delinquent and non-entered lands records (per the MapWV
FAQ). It carries a current status per tax-sale certificate but no event dates, so rows load
into tax_delinquency_snapshot. Status strings are stored raw; what each means for
reachability is a rules decision, not an adapter one.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import UTC, date
from typing import Any, ClassVar

from equity.adapters.arcgis_adapter import ArcGISCountyAdapter
from equity.adapters.base import Fetched, FetchRequest, NormalizedRow
from equity.adapters.rows import RecordContext
from equity.adapters.wv.parcel_ids import county_fips, parcel_uid_from_clean

LAYER = (
    "https://services.wvgis.wvu.edu/arcgis/rest/services/Planning_Cadastre/"
    "Delinquent_Properties/MapServer/0"
)
FIELDS: tuple[str, ...] = (
    "OBJECTID", "CleanParcelID", "CountyID", "status", "certno", "MAX_certno", "FREQUENCY",
    "deed_book", "page_number", "description", "district", "map_1", "parcel_1",
)  # fmt: skip
_NULLS = {"", "NULL", "NONE"}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    s = " ".join(str(value).split())
    return None if s.upper() in _NULLS else s


class WVDelinquentProperties(ArcGISCountyAdapter):
    source_id: ClassVar[str] = "wv.statewide.delinquent"
    adapter_version: ClassVar[str] = "1"
    layer_url: ClassVar[str] = LAYER
    fields: ClassVar[tuple[str, ...]] = FIELDS
    order_by: ClassVar[tuple[str, ...]] = ("OBJECTID",)
    health_where: ClassVar[str] = "CountyID='31'"

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "tax",
            "jurisdiction": "54",
            "access_method": "arcgis",
            "base_url": LAYER,
            "terms_url": "https://mapwv.gov/",
            "terms_summary": (
                "Public WVGISTC map service, weekly from WV State Auditor delinquent and "
                "non-entered lands; no license text found"
            ),
            "terms_checked_on": date(2026, 11, 15),
            "robots_checked_on": date(2026, 11, 15),
            "cost_model": "free",
        }

    def where(self, request: FetchRequest) -> str:
        """params: county_number (1-55)."""
        county = int(request.params["county_number"])
        county_fips(county)
        return f"CountyID='{county:02d}'"

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        observed = fetched.retrieved_at.astimezone(UTC).date()
        by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
        for a in self.attributes(fetched):
            clean_id, cert = _text(a.get("CleanParcelID")), _text(a.get("certno"))
            status = _text(a.get("status"))
            if clean_id is None or cert is None or status is None:
                continue
            key = (clean_id, cert)
            # One row per (parcel, certificate); duplicates resolve to the lowest OBJECTID.
            if key not in by_key or int(a["OBJECTID"]) < int(by_key[key]["OBJECTID"]):
                by_key[key] = a
        for (clean_id, cert), a in sorted(by_key.items()):
            county = int(clean_id[:2])
            ctx = RecordContext(
                fetched, county_fips(county), f"{clean_id}/{cert}", "delinquent", dict(a)
            )
            yield ctx.source_record()
            times = a.get("FREQUENCY")
            yield ctx.fact(
                "tax_delinquency_snapshot",
                parcel_uid=parcel_uid_from_clean(clean_id),
                certificate_no=cert,
                status_raw=_text(a.get("status")),
                times_listed=None if times is None else int(times),
                deed_book=_text(a.get("deed_book")),
                deed_page=_text(a.get("page_number")),
                legal_desc_raw=_text(a.get("description")),
                observed_on=observed,
            )
