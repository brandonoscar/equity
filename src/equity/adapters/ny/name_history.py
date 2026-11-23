"""New York DOS entity name history (data.ny.gov ekwr-p59j, "Corporations and Other Entities:
All Filings - Name Status History", about 7.5M rows): every name a New York entity has filed
under, with the filing date and whether the name is the entity's active one.

Each row becomes a `business` row keyed by the DOS id (the same id as ny.sos.business), so an
entity has one row per name it has carried. Matching (equity.matching.entities) keys
companies by every one of their names: a debt or a deed in an old name ("REIN TEEN TOURS,
INC.") reaches the entity that now trades as something else. It also brings in names of
entities that are no longer active, which ny.sos.business (active entities only) lacks.

  status       'active name' (name_status A) or 'former name' (I)
  valid_from   the filing date of the name

Partitions are filing-year windows. NY Open Data terms: free to use, no warranty.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataQuery, fetch_all
from equity.matching.orgs import classify

PORTAL = "https://data.ny.gov"
DATASET = "ekwr-p59j"
FIRST_YEAR = 1800
STATUS = {"A": "active name", "I": "former name"}


class NYNameHistory(Adapter):
    source_id: ClassVar[str] = "ny.sos.name_history"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = ("corp_name",)  # as for the other registries

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",
            "jurisdiction": "36",
            "access_method": "api",
            "base_url": f"{PORTAL}/resource/{DATASET}.json",
            "terms_url": "https://data.ny.gov/download/77gx-ii52/application%2Fpdf",
            "terms_summary": "NY Open Data terms: free to use; no warranty.",
            "terms_checked_on": "2026-11-23",
            "robots_checked_on": "2026-11-23",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        # Before 1900 the filings are few: one window; then one per decade, then per year.
        yield {"from": f"{FIRST_YEAR}-01-01", "to": "1900-01-01"}
        for y in range(1900, 1990, 10):
            yield {"from": f"{y}-01-01", "to": f"{y + 10}-01-01"}
        for y in range(1990, datetime.now(UTC).year + 1):
            yield {"from": f"{y}-01-01", "to": f"{y + 1}-01-01"}

    def fetch(self, request: FetchRequest) -> Fetched:
        p = request.params
        where = f"date_filed >= '{p['from']}T00:00:00' AND date_filed < '{p['to']}T00:00:00'"
        limit = int(p["limit"]) if "limit" in p else None
        q = SocrataQuery(PORTAL, DATASET, where, ("corpid_num", "date_filed", ":id"),
                         limit or 50_000)  # fmt: skip
        rows, resp = fetch_all(self.client, q, max_pages=1 if limit else 10_000,
                               sample=limit is not None)  # fmt: skip
        body = {"where": where, "rows": rows}
        return Fetched(self.source_id, q.url, resp[-1].retrieved_at, 200, canonical_json(body),
                       "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        today = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[tuple[str, date]] = set()
        for r in sorted(json.loads(fetched.content).get("rows") or [], key=canonical_json):
            sos_id = str(r.get("corpid_num") or "").strip()
            name = " ".join(str(r.get("corp_name") or "").split())
            try:
                filed = date.fromisoformat(str(r.get("date_filed") or "")[:10])
            except ValueError:
                continue
            if not sos_id or not name or filed > today or (sos_id, filed) in seen:
                continue  # one name per entity and day (the business key)
            seen.add((sos_id, filed))
            key = f"{sos_id}@{filed.isoformat()}"
            ctx = RecordContext(fetched, "36", key, "ny_name_filing", r)
            yield ctx.source_record()
            yield ctx.fact(
                "business", sos_id=sos_id, name=name, org_form=classify(name).org_form,
                status=STATUS.get(str(r.get("name_status") or "").strip(), "name"),
                formed_on=None, status_date=filed, principal_address_id=None,
                mailing_address_id=None, valid_from=filed, valid_to=None,
            )  # fmt: skip

    def health(self) -> HealthReport:
        """Fields from the dataset's column list (Socrata drops null fields from rows)."""
        try:
            view = json.loads(self.client.get(f"{PORTAL}/api/views/{DATASET}.json").content)
        except (ValueError, OSError) as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        shape = tuple(sorted(str(c["fieldName"]) for c in view.get("columns") or []
                             if not str(c["fieldName"]).startswith(":")))  # fmt: skip
        ok = {"corpid_num", "corp_name", "date_filed", "name_status"} <= set(shape)
        return HealthReport(self.source_id, ok, datetime.now(UTC), "ok" if ok else "fields",
                            shape)  # fmt: skip
