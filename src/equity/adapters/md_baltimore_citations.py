"""Baltimore City Environmental Control Board citations that are liens on the property.

Open Baltimore 'Environmental Citations' (ArcGIS, CC BY 3.0): one row per citation with
block and lot, fine, current balance, status and a lien code. Citations with lien code L are
liened against the parcel, so their debtor is the parcel's owner: no violator name is
published. Each liened citation becomes a STATUTORY_LIEN instrument on parcel
24510-<block><lot> (the key of md.baltimore_city.parcels); its amount is the current balance.
Paid (P), voided (V) and abated (A) citations are marked "(satisfied)" so they are never open.
Unliened citations (code N) are not loaded.
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
from equity.adapters.state_parcels import norm_parcel_id
from equity.schema.ids import stable_id

LAYER = "https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services/ECB_OB/FeatureServer/0"
COUNTY = "24510"
WINDOW = 25_000
FIELDS = ("ObjectID", "CitationNo", "LienCode", "ViolationDate", "FineAmount", "Balance",
          "CitationStatus", "Description", "Agency", "Block", "Lot",
          "ViolationLocation")  # fmt: skip
SATISFIED = {"P": "paid", "V": "voided", "A": "abated"}


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


def _money(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() and d >= 0 else None


def _epoch(v: Any) -> date | None:
    try:
        return datetime.fromtimestamp(int(v) / 1000, tz=UTC).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parcel_uid(block: Any, lot: Any) -> str | None:
    b, lt = _text(block), _text(lot)
    return f"{COUNTY}-{norm_parcel_id(b + lt)}" if b and lt else None


class BaltimoreCitationLiens(Adapter):
    source_id: ClassVar[str] = "md.baltimore_city.citation_liens"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "arcgis"
    pii_fields: ClassVar[tuple[str, ...]] = ()

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "tax",
            "jurisdiction": COUNTY,
            "access_method": "arcgis",
            "base_url": LAYER,
            "terms_url": "https://www.arcgis.com/home/item.html?id=87f2524498a64caca3cc7e37a3a355f7",
            "terms_summary": (
                "Baltimore City 'Environmental Citations' (Open Baltimore); licenseInfo: "
                "Creative Commons Attribution 3.0 Unported (credit Baltimore City)."
            ),
            "terms_checked_on": "2026-11-23",
            "robots_checked_on": "2026-11-23",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        stats = json.dumps([{"statisticType": "max", "onStatisticField": "ObjectID",
                             "outStatisticFieldName": "hi"}])  # fmt: skip
        body = get_json(self.client, LAYER + "/query",
                        {"where": "1=1", "outStatistics": stats, "f": "json"})  # fmt: skip
        hi = int((body.get("features") or [{}])[0].get("attributes", {}).get("hi") or 0)
        for lo in range(0, hi + 1, WINDOW):
            yield {"lo": str(lo), "hi": str(lo + WINDOW)}

    def fetch(self, request: FetchRequest) -> Fetched:
        lo, hi = int(request.params["lo"]), int(request.params["hi"])  # ints only reach SQL
        limit = request.params.get("limit")
        where = f"LienCode = 'L' AND ObjectID >= {lo} AND ObjectID < {hi}"
        q = ArcGISQuery(LAYER, where, FIELDS, ("ObjectID",), int(limit) if limit else 2000)
        feats, resp = fetch_all(self.client, q, max_pages=1 if limit else 10_000,
                                sample=limit is not None)  # fmt: skip
        return Fetched(self.source_id, f"{LAYER}/query?lo={lo}&hi={hi}", resp[-1].retrieved_at,
                       200, canonical_json({"rows": [f["attributes"] for f in feats]}),
                       "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        for a in sorted(json.loads(fetched.content).get("rows") or [],
                        key=lambda r: str(r.get("CitationNo"))):  # fmt: skip
            cit, uid = _text(a.get("CitationNo")), parcel_uid(a.get("Block"), a.get("Lot"))
            recorded = _epoch(a.get("ViolationDate"))
            if cit is None or uid is None or recorded is None or _text(a.get("LienCode")) != "L":
                continue
            status = (_text(a.get("CitationStatus")) or "").upper()
            raw = "Environmental citation lien"
            if status in SATISFIED:
                raw += f" ({SATISFIED[status]}) (satisfied)"
            ctx = RecordContext(fetched, COUNTY, cit, "citation", a)
            iuid = stable_id(self.source_id, "citation", cit)
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=iuid, instrument_number=cit, book_type=None,
                book=None, page=None, doc_type_raw=raw, doc_type="STATUTORY_LIEN",
                recorded_on=recorded, recorded_seq=None, executed_on=None, consideration=None,
                principal_amount=_money(a.get("Balance")), max_secured_amount=None,
                maturity_date=None, amount_source="index",
                legal_desc_raw=_text(a.get("Description")),
            )  # fmt: skip
            yield ctx.fact("instrument_parcel", instrument_uid=iuid, parcel_uid=uid,
                           method="index_parcel_id",
                           evidence={"block": _text(a.get("Block")),
                                     "lot": _text(a.get("Lot"))})  # fmt: skip

    def health(self) -> HealthReport:
        params = {"where": "LienCode = 'L'", "returnCountOnly": "true", "f": "json"}
        body = get_json(self.client, LAYER + "/query", params)
        n = int(body.get("count") or 0)
        return HealthReport(self.source_id, n > 10_000, datetime.now(UTC), f"{n} liened citations")
