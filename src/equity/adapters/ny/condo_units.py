"""NYC condominium unit lots -> the condominium's billing lot (Department of Finance).

ACRIS indexes condo documents by unit lot (1001 and up); the NYS assessment roll carries a
condominium as its billing lot (75xx), with the owner and value. Two Digital Tax Map datasets
on NYC Open Data link them: Condominium Units (eguu-7ie3: unit BBL -> condo key) and
Condominiums (p8u6-a6it: condo key -> billing BBL). Lot numbers only, no personal data.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.ny.acris import load_config, parcel_uid_for
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataQuery, fetch_all, get_page, parse_rows

PORTAL = "https://data.cityofnewyork.us"
UNITS = "eguu-7ie3"
CONDOS = "p8u6-a6it"


def _bbl10(value: Any) -> str | None:
    s = str(value or "").strip()
    return s if len(s) == 10 and s.isascii() and s.isdigit() and s[0] in "12345" else None


class NycCondoUnits(Adapter):
    source_id: ClassVar[str] = "ny.nyc.dof.condo_units"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = ()

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "assessor",
            "jurisdiction": "36",
            "access_method": "api",
            "base_url": f"{PORTAL}/resource/{UNITS}.json",
            "terms_url": "https://www.nyc.gov/html/data/terms.html",
            "terms_summary": (
                "NYC Open Data (DOF Digital Tax Map): no restriction on use found; "
                "informational, no warranty."
            ),
            "terms_checked_on": "2026-11-22",
            "robots_checked_on": "2026-11-22",
            "cost_model": "free",
        }

    def fetch(self, request: FetchRequest) -> Fetched:
        limit = request.params.get("limit")
        size = int(limit) if limit else 50_000
        cols = ("unit_bbl", "condo_key", "unit_designation")
        q = SocrataQuery(PORTAL, UNITS, "unit_bbl IS NOT NULL", ("unit_bbl", ":id"), size, cols)
        units, resp = fetch_all(self.client, q, max_pages=1 if limit else 100,
                                sample=limit is not None)  # fmt: skip
        keys = sorted({str(u.get("condo_key") or "") for u in units} - {""})
        where = "condo_key IS NOT NULL"
        if limit:  # a fixture keeps only the condos its units belong to
            where = "condo_key in (" + ",".join(f"'{k}'" for k in keys if k.isdigit()) + ")"
        cq = SocrataQuery(PORTAL, CONDOS, where, ("condo_key", ":id"), 50_000,
                          ("condo_key", "condo_billing_bbl"))  # fmt: skip
        condos, _ = fetch_all(self.client, cq)
        body = canonical_json({"units": units, "condos": condos})
        return Fetched(self.source_id, f"{PORTAL}/resource/{UNITS}.json", resp[-1].retrieved_at,
                       200, body, "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        billing = {str(c.get("condo_key") or ""): _bbl10(c.get("condo_billing_bbl"))
                   for c in data.get("condos") or []}  # fmt: skip
        cfg = load_config()
        seen: set[str] = set()
        for u in sorted(data.get("units") or [], key=lambda r: str(r.get("unit_bbl"))):
            unit = _bbl10(u.get("unit_bbl"))
            bill = billing.get(str(u.get("condo_key") or ""))
            if unit is None or bill is None or unit == bill or unit in seen:
                continue
            seen.add(unit)
            from_uid, to_uid = parcel_uid_for(unit, cfg), parcel_uid_for(bill, cfg)
            ctx = RecordContext(fetched, from_uid.split("-")[0], unit, "condo_unit", u)
            yield ctx.source_record()
            yield ctx.fact(
                "parcel_link",
                from_parcel_uid=from_uid,
                to_parcel_uid=to_uid,
                link_type="condo_unit_of",
                detail=str(u.get("unit_designation") or "").strip() or None,
            )

    def health(self) -> HealthReport:
        q = SocrataQuery(PORTAL, UNITS, "unit_bbl IS NOT NULL", (":id",), 1)
        resp = get_page(self.client, q, 0)
        ok = resp.status == 200 and len(parse_rows(resp.content)) == 1
        return HealthReport(self.source_id, ok, datetime.now(UTC), f"status={resp.status}")
