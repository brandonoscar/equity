"""Douglas County, NE (Omaha) property tax liens from the County Treasurer, via DOGIS.

Two hosted ArcGIS layers (no license published; used on the project owner's decision,
2026-11-23):
  auction  'DC_Tax_Lien_Auction (View)': the tax sale list, one row per certificate with the
           taxpayer, mailing address, PIN, certificate/principal/interest amounts and sale
           year. The county shows it only around the annual tax sale, so it is snapshotted
           while it is up.
  county   'DC_Tax_Liens_view': county-held tax liens with PIN, year and amount (no name: owed
           by the parcel's owner).

Each row is a STATUTORY_LIEN instrument on parcel 31055-<PIN> (the ne.douglas.parcels key),
dated January 1 of its tax year (no filing date is published). Joint taxpayers ("A*B") are
separate debtors.
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

BASE = "https://dcgis.org/server/rest/services/Hosted"
LAYERS = {"auction": f"{BASE}/DC_Tax_Lien_Auction_(View)/FeatureServer/0",
          "county": f"{BASE}/DC_Tax_Liens_view/FeatureServer/0"}  # fmt: skip
COUNTY = "31055"


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


def _money(v: Any) -> Decimal | None:
    s = str(v if v is not None else "").replace("$", "").replace(",", "").strip()
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() and d > 0 else None


def _year(v: Any) -> int | None:
    s = str(v or "").strip().split(".")[0]
    return int(s) if s.isdigit() and 1900 <= int(s) <= 2200 else None


class DouglasTaxLiens(Adapter):
    source_id: ClassVar[str] = "ne.douglas.tax_liens"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "arcgis"
    pii_fields: ClassVar[tuple[str, ...]] = ("taxpayer", "mail_address1", "mail_address2",
                                             "prop_address", "address")  # fmt: skip

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "tax",
            "jurisdiction": COUNTY,
            "access_method": "arcgis",
            "base_url": BASE,
            "terms_url": "https://www.arcgis.com/home/item.html?id=045e450e8cdb428b934ca1d4e79940b5",
            "terms_summary": (
                "Douglas County, NE Treasurer tax lien auction list and county-held tax liens "
                "(DOGIS hosted layers); no license published. Used on the project owner's "
                "decision (2026-11-23)."
            ),
            "terms_checked_on": "2026-11-23",
            "robots_checked_on": "2026-11-23",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        for layer in LAYERS:
            yield {"layer": layer}

    def fetch(self, request: FetchRequest) -> Fetched:
        layer = request.params["layer"]
        if layer not in LAYERS:
            raise ValueError(f"unknown layer {layer!r}")
        limit = request.params.get("limit")
        q = ArcGISQuery(LAYERS[layer], "1=1", ("*",), ("objectid",), int(limit) if limit else 1000)
        feats, resp = fetch_all(self.client, q, max_pages=1 if limit else 1000,
                                sample=limit is not None)  # fmt: skip
        body = {"layer": layer, "rows": [f["attributes"] for f in feats]}
        return Fetched(self.source_id, f"{LAYERS[layer]}/query", resp[-1].retrieved_at, 200,
                       canonical_json(body), "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        layer = data.get("layer")
        for a in sorted(data.get("rows") or [], key=canonical_json):
            pin = _text(a.get("pin"))
            if layer == "auction":
                year, amount = _year(a.get("tax_sale_year")), _money(a.get("cert_amt"))
                key = f"auction-{_text(a.get('tax_sale_year'))}-{_text(a.get('item_num'))}-{pin}"
            else:
                year, amount = _year(a.get("year")), _money(a.get("amt"))
                key = f"county-{_text(a.get('year'))}-{pin}-{_text(a.get('objectid'))}"
            if pin is None or year is None:
                continue
            ctx = RecordContext(fetched, COUNTY, key, "tax_lien", a)
            uid = stable_id(self.source_id, "lien", key)
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=key, book_type=None,
                book=None, page=None,
                doc_type_raw="Tax sale certificate" if layer == "auction" else "County tax lien",
                doc_type="STATUTORY_LIEN", recorded_on=date(year, 1, 1), recorded_seq=None,
                executed_on=None, consideration=None, principal_amount=amount,
                max_secured_amount=None, maturity_date=None, amount_source="index",
                legal_desc_raw=None,
            )  # fmt: skip
            yield ctx.fact("instrument_parcel", instrument_uid=uid,
                           parcel_uid=f"{COUNTY}-{norm_parcel_id(pin)}",
                           method="index_parcel_id", evidence={"pin": pin})  # fmt: skip
            if layer != "auction":
                continue
            street = " ".join(x for x in (_text(a.get("mail_address1")),
                                          _text(a.get("mail_address2"))) if x) or None  # fmt: skip
            z = str(a.get("zip") or "").strip()[:5]
            addr = normalized_address(street, _text(a.get("city")), _text(a.get("state")),
                                      z if len(z) == 5 and z.isdigit() else None)  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            names = [n.strip() for n in str(a.get("taxpayer") or "").split("*") if n.strip()]
            for seq, name in enumerate(names, start=1):
                nc = classify(name)
                party_id = stable_id(self.source_id, key, "debtor", clean(name))
                yield ctx.fact("party", party_id=party_id, raw_name=name,
                               party_kind=nc.party_kind, org_form=nc.org_form,
                               org_name_norm=nc.org_name_norm,
                               address_id=addr["address_id"] if addr else None)  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=party_id,
                               role="debtor", seq=seq)  # fmt: skip

    def health(self) -> HealthReport:
        params = {"where": "1=1", "returnCountOnly": "true", "f": "json"}
        n = int(get_json(self.client, LAYERS["county"] + "/query", params).get("count") or 0)
        return HealthReport(self.source_id, n > 0, datetime.now(UTC), f"{n} county-held liens")
