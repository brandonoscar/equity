"""HUD FHA single-family REO: homes HUD took back after an FHA-insured mortgage foreclosed and
now offers for sale (HUD's public ArcGIS layer "FHA Single Family REO Properties For Sale",
about 600 homes nationally, refreshed monthly).

Each home is one DEED instrument: title passed to the Secretary of HUD on DATE_ACQUIRED
(the conveyance after foreclosure), with HUD as grantee. For the graph it says the former
owner's equity is gone; for the sale aggregator it is a government listing. The layer has no
parcel number, list price or former owner name: the property address goes in
legal_desc_raw and an address row (for a later address join), the county comes from the
census block (state + county FIPS are its first five digits).

Source: https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/SF_REO/FeatureServer/0
(owner HUD.Official.Content; licenseInfo: no warranty or liability; no use restriction).
HUD Home Store itself (prices, bid deadlines) disallows all robots and is not used.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from equity.adapters.arcgis import ArcGISQuery, fetch_all, get_json
from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

LAYER = "https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/SF_REO/FeatureServer/0"
FIELDS = ("OBJECTID", "CASE_NUM", "STREET_NUM", "DIRECTION_PREFIX", "STREET_NAME", "CITY",
          "STATE_CODE", "DISPLAY_ZIP_CODE", "CENSUS_BLOCK", "FIPS_STATE_CODE", "DATE_ACQUIRED",
          "DATE_CLOSED", "REVITE_NAME")  # fmt: skip
HUD = "SECRETARY OF HOUSING AND URBAN DEVELOPMENT"


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


def _day(ms: Any) -> date | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=UTC).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def jurisdiction(row: Mapping[str, Any]) -> str | None:
    """County FIPS from the census block GEOID, else the state FIPS."""
    block = "".join(ch for ch in str(row.get("CENSUS_BLOCK") or "") if ch.isdigit())
    if len(block) >= 5:
        return block[:5]
    st = "".join(ch for ch in str(row.get("FIPS_STATE_CODE") or "") if ch.isdigit())
    return st.zfill(2) if st else None


class HudFhaReo(Adapter):
    source_id: ClassVar[str] = "us.hud.fha_reo"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "arcgis"
    pii_fields: ClassVar[tuple[str, ...]] = ()  # property addresses of HUD-owned homes only

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "government_sale",
            "jurisdiction": "US",
            "access_method": "arcgis",
            "base_url": LAYER,
            "terms_url": "https://www.arcgis.com/home/item.html?id=a54aff75cc0a42de8456cc36a7335663",
            "terms_summary": (
                "HUD public ArcGIS layer (owner HUD.Official.Content), free, no login. "
                "licenseInfo: no warranty, no liability for use or misuse; no use restriction."
            ),
            "terms_checked_on": "2026-11-23",
            "robots_checked_on": "2026-11-23",
            "cost_model": "free",
        }

    def fetch(self, request: FetchRequest) -> Fetched:
        limit = request.params.get("limit")
        q = ArcGISQuery(LAYER, "1=1", FIELDS, ("OBJECTID",), int(limit) if limit else 2000)
        feats, resp = fetch_all(self.client, q, max_pages=1 if limit else 1000,
                                sample=limit is not None)  # fmt: skip
        body = {"rows": [f["attributes"] for f in feats]}
        return Fetched(self.source_id, f"{LAYER}/query", resp[-1].retrieved_at, 200,
                       canonical_json(body), "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        today = fetched.retrieved_at.astimezone(UTC).date()
        hud = classify(HUD)
        for a in sorted(json.loads(fetched.content).get("rows") or [], key=canonical_json):
            case = _text(a.get("CASE_NUM"))
            acquired = _day(a.get("DATE_ACQUIRED"))
            juris = jurisdiction(a)
            if case is None or acquired is None or acquired > today or juris is None:
                continue
            ctx = RecordContext(fetched, juris, case, "hud_reo_property", a)
            yield ctx.source_record()
            street = " ".join(x for x in (_text(a.get("STREET_NUM")),
                                          _text(a.get("DIRECTION_PREFIX")),
                                          _text(a.get("STREET_NAME"))) if x) or None  # fmt: skip
            z = str(a.get("DISPLAY_ZIP_CODE") or "").strip()[:5]
            addr = normalized_address(street, _text(a.get("CITY")), _text(a.get("STATE_CODE")),
                                      z if len(z) == 5 and z.isdigit() else None)  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            uid = stable_id(self.source_id, case)
            where = ", ".join(x for x in (street, _text(a.get("CITY")),
                                          _text(a.get("STATE_CODE")), z) if x)  # fmt: skip
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=case, book_type=None,
                book=None, page=None, doc_type_raw="HUD FHA REO: acquired by HUD",
                doc_type="DEED", recorded_on=acquired, recorded_seq=None, executed_on=None,
                consideration=None, principal_amount=None, max_secured_amount=None,
                maturity_date=None, amount_source=None, legal_desc_raw=where or None,
            )  # fmt: skip
            party_id = stable_id(self.source_id, "hud")
            yield ctx.fact("party", party_id=party_id, raw_name=HUD, party_kind=hud.party_kind,
                           org_form=hud.org_form, org_name_norm=hud.org_name_norm or clean(HUD),
                           address_id=None)  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=party_id,
                           role="grantee", seq=1)  # fmt: skip

    def health(self) -> HealthReport:
        n = int(get_json(self.client, LAYER + "/query",
                         {"where": "1=1", "returnCountOnly": "true", "f": "json"}).get("count")
                or 0)  # fmt: skip
        meta = get_json(self.client, LAYER, {"f": "json"})
        fields = tuple(sorted(str(f["name"]) for f in meta.get("fields") or []))
        ok = n > 0 and set(FIELDS) <= set(fields)
        return HealthReport(self.source_id, ok, datetime.now(UTC), f"{n} homes", fields, n)
