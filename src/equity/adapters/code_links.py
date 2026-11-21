"""Links to each municipality's zoning ordinance, zoning map and website.

New Jersey: the Department of Community Affairs' "Municipal Zoning" layer (NJOGIS), one
polygon per municipality with links to its ordinance (mostly eCode360), zoning map and site.
Only the links are stored; the ordinance text stays with its publisher, whose terms bar bulk
copying (docs/sources/zoning-sources.md). The layer asks for credit to NJDCA and NJOGIS.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

from equity.adapters.arcgis import ArcGISQuery, fetch_all, get_json
from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json

PUBLISHERS = (
    ("municode.com", "municode"),
    ("ecode360.com", "ecode360"),
    ("amlegal.com", "amlegal"),
    ("codepublishing.com", "codepublishing"),
)


def publisher_of(url: str | None) -> str | None:
    if not url:
        return None
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    for suffix, name in PUBLISHERS:
        if host == suffix or host.endswith("." + suffix):
            return name
    return "government"


def _url(value: Any) -> str | None:
    s = str(value or "").strip()
    return s if s.lower().startswith(("http://", "https://")) else None


class NJMunicipalCodeLinks(Adapter):
    source_id: ClassVar[str] = "nj.dca.code_links"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "arcgis"
    pii_fields: ClassVar[tuple[str, ...]] = ()
    layer_url: ClassVar[str] = (
        "https://services.arcgis.com/Aur8tCo478N3VovT/arcgis/rest/services/"
        "Municipal_Zoning/FeatureServer/0"
    )
    fields: ClassVar[tuple[str, ...]] = ("OBJECTID_1", "Muni", "Municipali", "County_1", "Map",
                                         "Ordinance", "Website")  # fmt: skip

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "zoning",
            "jurisdiction": "34",
            "access_method": "arcgis",
            "base_url": self.layer_url,
            "terms_url": "https://njogis-newjersey.opendata.arcgis.com/",
            "terms_summary": (
                "NJ DCA 'Municipal Zoning' (NJOGIS): links to each municipality's zoning "
                "ordinance, map and website. Credit NJDCA and NJOGIS. Links only are stored."
            ),
            "terms_checked_on": "2026-11-20",
            "robots_checked_on": "2026-11-20",
            "cost_model": "free",
        }

    def fetch(self, request: FetchRequest) -> Fetched:
        limit = request.params.get("limit")
        q = ArcGISQuery(self.layer_url, "1=1", self.fields, ("OBJECTID_1",), int(limit or 1000))
        features, responses = fetch_all(self.client, q, max_pages=1 if limit else 100,
                                        sample=limit is not None)  # fmt: skip
        body = canonical_json({"attributes": [f["attributes"] for f in features]})
        return Fetched(self.source_id, f"{self.layer_url}/query?where=1=1",
                       responses[-1].retrieved_at, 200, body, "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        for a in json.loads(fetched.content).get("attributes") or []:
            muni = str(a.get("Muni") or "").strip()
            if not muni:
                continue  # no municipal code, no stable key
            ctx = RecordContext(fetched, "34", muni, "code_link", a)
            ordinance = _url(a.get("Ordinance"))
            yield ctx.source_record()
            yield ctx.fact(
                "code_link",
                jurisdiction_uid=f"NJ-{muni}",
                jurisdiction_name=str(a.get("Municipali") or "").strip() or None,
                county_name=str(a.get("County_1") or "").strip() or None,
                ordinance_url=ordinance,
                zoning_map_url=_url(a.get("Map")),
                website_url=_url(a.get("Website")),
                publisher=publisher_of(ordinance),
            )

    def health(self) -> HealthReport:
        body = get_json(self.client, self.layer_url + "/query",
                        {"where": "1=1", "returnCountOnly": "true", "f": "json"})  # fmt: skip
        n = int(body.get("count") or 0)
        return HealthReport(self.source_id, n > 500, datetime.now(UTC), f"{n} municipalities")
