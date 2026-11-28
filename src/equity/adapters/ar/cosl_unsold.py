"""Arkansas Commissioner of State Lands: tax-delinquent parcels on the Unsold-Property Auction.

In Arkansas a county certifies its tax-delinquent real property to the Commissioner of State
Lands, who offers it at a Tax Delinquent Property Auction; a parcel not sold there goes on the
online Unsold-Property Auction (COSL Rules and Regulations, Title 3). Until it sells, the record
owner can still redeem it by paying all delinquent taxes, interest, penalties and costs; the
minimum bid is that amount ("the amount of taxes, interest, penalty and cost", COSL purchasing
guide). auction.cosl.org lists every such parcel with no login: the record owner, county,
parcel number, acreage, the minimum (starting) bid and the date it was added. On 2026-11-28:
2,604 parcels in 48 counties, $3.02M in minimum bids (153 with bids open).

Each parcel is one TAX_LIEN_STATE instrument owed by its record owner (each '%'-separated
name; a 'C/O' addressee is not an owner), dated the day it was listed, for the minimum bid.
The parcel number is the county's, the same parcelid as ar.statewide.parcels, so the parcel
key is the county FIPS + that number.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import norm_parcel_id
from equity.geo import county_by_name
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PAGE = "https://auction.cosl.org/Auctions/ListingsView"
URL = "https://auction.cosl.org/auctions/grid_read"
RULES = "https://coslstorage.blob.core.windows.net/web-resources/rules-and-regs.pdf"
CREDITOR = "Arkansas Commissioner of State Lands"
CARE_OF = re.compile(r"\s+C/O\s+.*$")


def owner_names(raw: str | None) -> list[str]:
    """'RICKY N  NICHOLSON%SUSAN E NICHOLSON' -> ['RICKY N NICHOLSON', 'SUSAN E NICHOLSON'];
    'LOUISE J  MONK C/O BENJAMIN MONK' -> ['LOUISE J MONK'] (the addressee is not an owner)."""
    out = []
    for part in str(raw or "").upper().split("%"):
        name = " ".join(CARE_OF.sub("", " " + part.strip()).split())
        if name and name not in out:
            out.append(name)
    return out


class ArkansasUnsoldTaxParcels(Adapter):
    source_id: ClassVar[str] = "ar.cosl.unsold_tax_parcels"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = ("Owner",)

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=600.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "tax",
            "jurisdiction": "05",
            "access_method": "api",
            "base_url": PAGE,
            "terms_url": RULES,
            "terms_summary": (
                "Arkansas Commissioner of State Lands online auction list (auction.cosl.org, "
                "List View), public with no login; the Rules and Regulations say the list of "
                "unsold parcels 'will be available through the Commissioner's website' and "
                "state no use restriction. auction.cosl.org/robots.txt answers 404 (RFC 9309: "
                "no rules, allowed)."
            ),
            "terms_checked_on": "2026-11-28",
            "robots_checked_on": "2026-11-28",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {}

    def fetch(self, request: FetchRequest) -> Fetched:
        # The List View grid's own data request (Kendo DataSource): every listing, one page.
        resp = self.client.post_form(URL, {"sort": "", "page": "1", "pageSize": "100000",
                                           "group": "", "filter": ""})  # fmt: skip
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status} for {URL}")
        data = json.loads(resp.content)
        rows = list(data.get("Data") or [])
        if data.get("Total") is not None and len(rows) < int(data["Total"]):
            raise RuntimeError(f"{self.source_id}: {len(rows)} of {data['Total']} listings")
        keep = ("Owner", "CoSLCountyName", "CoSLParcelNumber", "Acreage", "StartingBid",
                "CoSLPropertyId", "SaleType", "Added", "Section", "Township", "Range")  # fmt: skip
        rows = sorted(({k: r.get(k) for k in keep} for r in rows),
                      key=lambda r: int(r.get("CoSLPropertyId") or 0))  # fmt: skip
        limit = request.params.get("limit")
        if limit:
            rows = rows[: int(limit)]
        return Fetched(self.source_id, URL, resp.retrieved_at, 200,
                       canonical_json({"rows": rows}), "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        for r in json.loads(fetched.content).get("rows") or []:
            names = owner_names(r.get("Owner"))
            key = str(r.get("CoSLPropertyId") or "")
            parcel = " ".join(str(r.get("CoSLParcelNumber") or "").split())
            bid = Decimal(str(r.get("StartingBid") or 0))
            added = str(r.get("Added") or "")[:10]
            try:
                county = county_by_name("AR", str(r.get("CoSLCountyName") or ""))
            except KeyError:
                continue  # no county, no parcel key: skip rather than guess
            if not (names and key and parcel and bid > 0 and re.match(r"\d{4}-\d\d-\d\d", added)):
                continue
            ctx = RecordContext(fetched, county.fips5, key, "unsold_tax_parcel", r)
            uid = stable_id(self.source_id, "listing", key)
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=key, book_type=None,
                book=None, page=None,
                doc_type_raw=(f"Arkansas Commissioner of State Lands unsold tax-delinquent "
                              f"parcel, {county.name} (minimum bid = taxes, interest, "
                              f"penalty and costs)"),
                doc_type="TAX_LIEN_STATE", recorded_on=date.fromisoformat(added),
                recorded_seq=None, executed_on=None, consideration=None,
                principal_amount=bid, max_secured_amount=None, maturity_date=None,
                amount_source="index", legal_desc_raw=None,
            )  # fmt: skip
            yield ctx.fact("instrument_parcel", instrument_uid=uid,
                           parcel_uid=f"{county.fips5}-{norm_parcel_id(parcel)}",
                           method="index_parcel_id",
                           evidence={"county": r.get("CoSLCountyName"),
                                     "parcel": parcel})  # fmt: skip
            for seq, name in enumerate(names, start=1):
                nc = classify(name)
                pid = stable_id(self.source_id, key, "debtor", clean(name))
                yield ctx.fact("party", party_id=pid, raw_name=name, party_kind=nc.party_kind,
                               org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                               address_id=None)  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid,
                               role="debtor", seq=seq)  # fmt: skip
            cr = classify(CREDITOR)
            cid = stable_id(self.source_id, "creditor", clean(CREDITOR))
            yield ctx.fact("party", party_id=cid, raw_name=CREDITOR, party_kind=cr.party_kind,
                           org_form=cr.org_form, org_name_norm=cr.org_name_norm,
                           address_id=None)  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=cid,
                           role="creditor", seq=1)  # fmt: skip

    def health(self) -> HealthReport:
        resp = self.client.get(PAGE)
        ok = resp.status == 200 and b"grid_read" in resp.content
        return HealthReport(self.source_id, ok, datetime.now(UTC),
                            f"status={resp.status}; listing grid "
                            f"{'found' if ok else 'missing'}")  # fmt: skip
