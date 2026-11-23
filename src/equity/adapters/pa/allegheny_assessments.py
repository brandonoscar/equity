"""Allegheny County property assessments (WPRDC), for parcel values.

The county parcel layer carries no values and no owner names; WPRDC's "Property Assessments
Parcel Data" (CC0, one row per parcel, current tax year) has fair market and county assessed
values and the homestead flag. Only those columns are read: the dataset has no owner name, and
its owner mailing address columns are not taken (no name to attach them to).

Partitions are the first two digits of the PIN (block number), because the DataStore's _id
changes when WPRDC reloads the table.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import norm_parcel_id

PORTAL = "https://data.wprdc.org"
RESOURCE = "65855e14-549e-4992-b5be-d629afc676fa"  # Property Assessments Parcel Data (API)
COUNTY = "42003"
COLUMNS = ("PARID", "TAXYEAR", "CLASSDESC", "HOMESTEADFLAG", "COUNTYTOTAL", "FAIRMARKETLAND",
           "FAIRMARKETBUILDING", "FAIRMARKETTOTAL")  # fmt: skip


def _money(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() and d >= 0 else None


class AlleghenyAssessments(Adapter):
    source_id: ClassVar[str] = "pa.allegheny.assessments"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = ()
    page_size: ClassVar[int] = 10_000

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "assessor",
            "jurisdiction": COUNTY,
            "access_method": "api",
            "base_url": f"{PORTAL}/api/3/action/datastore_search_sql",
            "terms_url": "https://data.wprdc.org/dataset/property-assessments",
            "terms_summary": (
                "WPRDC (University of Pittsburgh) for the Allegheny County Office of Property "
                "Assessments, CC0. CKAN DataStore API; robots.txt grants scripts use of /api/ "
                "(see equity.adapters.http SCRIPT_PERMISSIONS)."
            ),
            "terms_checked_on": "2026-11-22",
            "robots_checked_on": "2026-11-22",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        for i in range(100):
            yield {"prefix": f"{i:02d}"}

    def _sql(self, prefix: str, limit: int, offset: int) -> str:
        if not (len(prefix) == 2 and prefix.isdigit()):
            raise ValueError(f"bad PIN prefix {prefix!r}")
        cols = ", ".join(f'"{c}"' for c in COLUMNS)
        return (f'SELECT {cols} FROM "{RESOURCE}" WHERE "PARID" LIKE \'{prefix}%\' '  # noqa: S608
                f'ORDER BY "PARID" LIMIT {limit} OFFSET {offset}')  # fmt: skip

    def fetch(self, request: FetchRequest) -> Fetched:
        prefix = request.params["prefix"]
        limit = request.params.get("limit")
        page = int(limit) if limit else self.page_size
        url = f"{PORTAL}/api/3/action/datastore_search_sql"
        rows: list[dict[str, Any]] = []
        while True:
            resp = self.client.get(url, {"sql": self._sql(prefix, page, len(rows))})
            body = json.loads(resp.content)
            if resp.status != 200 or not body.get("success"):
                raise RuntimeError(f"{self.source_id}: CKAN query failed: {body.get('error')}")
            got = body["result"]["records"]
            rows += got
            if limit or len(got) < page:
                break
        return Fetched(self.source_id, f"{url}?prefix={prefix}", resp.retrieved_at, 200,
                       canonical_json({"records": rows}), "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        for r in json.loads(fetched.content).get("records") or []:
            pin = str(r.get("PARID") or "").strip()
            year = r.get("TAXYEAR")
            if not pin or year is None:
                continue
            tax_year = int(float(year))
            if not 1800 <= tax_year <= 2200:
                continue
            ctx = RecordContext(fetched, COUNTY, pin, "assessment", r)
            yield ctx.source_record()
            yield ctx.fact(
                "parcel_assessment",
                parcel_uid=f"{COUNTY}-{norm_parcel_id(pin)}",
                tax_year=tax_year,
                appraised_land=_money(r.get("FAIRMARKETLAND")),
                appraised_bldg=_money(r.get("FAIRMARKETBUILDING")),
                appraised_total=_money(r.get("FAIRMARKETTOTAL")),
                assessed_value=_money(r.get("COUNTYTOTAL")),
                tax_class=str(r.get("CLASSDESC") or "").strip() or None,
                valid_from=date(tax_year, 1, 1),
                valid_to=None,
                homestead=str(r.get("HOMESTEADFLAG") or "").strip().upper() == "HOM",
            )

    def health(self) -> HealthReport:
        url = f"{PORTAL}/api/3/action/datastore_search_sql"
        resp = self.client.get(url, {"sql": self._sql("01", 1, 0)})
        ok = resp.status == 200 and bool(json.loads(resp.content).get("success"))
        return HealthReport(self.source_id, ok, datetime.now(UTC), f"status={resp.status}")
