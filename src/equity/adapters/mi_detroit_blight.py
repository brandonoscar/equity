"""City of Detroit blight violation tickets with an administrative-hearing judgment.

Department of Administrative Hearings 'Blight Tickets' (ArcGIS, City of Detroit; no license
published, used on the project owner's decision 2026-11-23): one row per ticket with the
property's parcel id, the property owner's name and mailing address, the disposition and
judgment date, and judgment, payment and balance amounts.

Each ticket found responsible with a judgment amount is a COURT_ORDER instrument (an
administrative judgment against the owner) on parcel 26163-<parcel_id> (Wayne County), owed
by the named owner; its amount is the balance due, and a ticket with no balance left is marked
"(satisfied)". Partitions are OBJECTID windows.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from equity.adapters.arcgis import ArcGISQuery, fetch_all, get_json
from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import norm_parcel_id, normalized_address
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

LAYER = ("https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/"
         "blight_tickets/FeatureServer/0")  # fmt: skip
COUNTY = "26163"
WINDOW = 50_000
FIELDS = ("OBJECTID", "ticket_number", "parcel_id", "disposition", "judgment_date",
          "amt_judgment", "amt_balance_due", "payment_status", "ordinance_description",
          "property_owner_name", "property_owner_address", "property_owner_city",
          "property_owner_state", "property_owner_zip_code")  # fmt: skip


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


def _money(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() and d >= 0 else None


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


class DetroitBlightJudgments(Adapter):
    source_id: ClassVar[str] = "mi.detroit.blight_judgments"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "arcgis"
    pii_fields: ClassVar[tuple[str, ...]] = ("property_owner_name", "property_owner_address")

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "court",
            "jurisdiction": COUNTY,
            "access_method": "arcgis",
            "base_url": LAYER,
            "terms_url": "https://www.arcgis.com/home/item.html?id=9ce72b42872844bdbe272c607224e3b3",
            "terms_summary": (
                "City of Detroit Department of Administrative Hearings 'Blight Tickets'; no "
                "licenseInfo (accessInformation 'City of Detroit'). Used on the project "
                "owner's decision (2026-11-23)."
            ),
            "terms_checked_on": "2026-11-23",
            "robots_checked_on": "2026-11-23",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        stats = json.dumps([{"statisticType": "max", "onStatisticField": "OBJECTID",
                             "outStatisticFieldName": "hi"}])  # fmt: skip
        body = get_json(self.client, LAYER + "/query",
                        {"where": "1=1", "outStatistics": stats, "f": "json"})  # fmt: skip
        hi = int((body.get("features") or [{}])[0].get("attributes", {}).get("hi") or 0)
        for lo in range(0, hi + 1, WINDOW):
            yield {"lo": str(lo), "hi": str(lo + WINDOW)}

    def fetch(self, request: FetchRequest) -> Fetched:
        lo, hi = int(request.params["lo"]), int(request.params["hi"])  # ints only reach SQL
        limit = request.params.get("limit")
        where = f"amt_judgment > 0 AND OBJECTID >= {lo} AND OBJECTID < {hi}"
        q = ArcGISQuery(LAYER, where, FIELDS, ("OBJECTID",), int(limit) if limit else 1000)
        feats, resp = fetch_all(self.client, q, max_pages=1 if limit else 10_000,
                                sample=limit is not None)  # fmt: skip
        return Fetched(self.source_id, f"{LAYER}/query?lo={lo}&hi={hi}", resp[-1].retrieved_at,
                       200, canonical_json({"rows": [f["attributes"] for f in feats]}),
                       "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        seen: set[str] = set()
        for a in sorted(json.loads(fetched.content).get("rows") or [],
                        key=lambda r: str(r.get("ticket_number"))):  # fmt: skip
            ticket, when = _text(a.get("ticket_number")), _date(a.get("judgment_date"))
            judged = _money(a.get("amt_judgment"))
            if ticket is None or when is None or not judged or ticket in seen:
                continue
            seen.add(ticket)
            balance = _money(a.get("amt_balance_due"))
            raw = f"Blight judgment: {_text(a.get('disposition')) or 'responsible'}"
            if balance is not None and balance == 0:
                raw += " (satisfied)"
            ctx = RecordContext(fetched, COUNTY, ticket, "blight_ticket", a)
            uid = stable_id(self.source_id, "ticket", ticket)
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=ticket, book_type=None,
                book=None, page=None, doc_type_raw=raw, doc_type="COURT_ORDER",
                recorded_on=when, recorded_seq=None, executed_on=None, consideration=None,
                principal_amount=balance if balance is not None else judged,
                max_secured_amount=None, maturity_date=None, amount_source="index",
                legal_desc_raw=_text(a.get("ordinance_description")),
            )  # fmt: skip
            pid = _text(a.get("parcel_id"))
            if pid:
                yield ctx.fact("instrument_parcel", instrument_uid=uid,
                               parcel_uid=f"{COUNTY}-{norm_parcel_id(pid)}",
                               method="index_parcel_id", evidence={"parcel_id": pid})  # fmt: skip
            owner = _text(a.get("property_owner_name"))
            if owner is None:
                continue
            z = str(a.get("property_owner_zip_code") or "").strip()[:5]
            addr = normalized_address(_text(a.get("property_owner_address")),
                                      _text(a.get("property_owner_city")),
                                      _text(a.get("property_owner_state")),
                                      z if len(z) == 5 and z.isdigit() else None)  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            nc = classify(owner)
            party_id = stable_id(self.source_id, ticket, "debtor", clean(owner))
            yield ctx.fact("party", party_id=party_id, raw_name=owner, party_kind=nc.party_kind,
                           org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                           address_id=addr["address_id"] if addr else None)  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=party_id,
                           role="debtor", seq=1)  # fmt: skip

    def health(self) -> HealthReport:
        params = {"where": "amt_judgment > 0", "returnCountOnly": "true", "f": "json"}
        n = int(get_json(self.client, LAYER + "/query", params).get("count") or 0)
        return HealthReport(self.source_id, n > 100_000, datetime.now(UTC), f"{n} judged tickets")
