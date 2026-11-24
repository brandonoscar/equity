"""Prince George's County MD property records (data.princegeorgescountymd.gov qzrv-2tnv).

Maryland's statewide parcel layer carries no owner names. Prince George's County publishes its
own monthly property file with the owner of record (owner_name, and ico_name, "in care of"),
the owner's mailing address, the property address, and the SDAT full cash values and current
assessment, keyed by the State tax account number (account, seven digits). The account is the
key the county's Foreclosure Registry (mnie-hrv7) and SDAT use, so parcel_uid is
"24033-<account>".

The last transfer date and price (transfer_date, sales_price) stay in the source record: they
show when the current owner acquired the parcel.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataQuery, fetch_all, get_page, parse_rows
from equity.adapters.state_parcels import normalized_address
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PORTAL = "https://data.princegeorgescountymd.gov"
DATASET = "qzrv-2tnv"
COUNTY = "24033"
_ACCOUNT = re.compile(r"^[0-9]{1,7}$")
SELECT = ("account", "owner_name", "ico_name", "mail_street", "mail_city", "mail_state",
          "mail_zip5", "house_number", "house_suffix", "street_direction", "street_name",
          "street_type", "unit", "city", "zip5", "fcv_land", "fcv_imps", "curr_assess",
          "bpruc", "dwelling_type", "transfer_date", "sales_price", "inactive_date")  # fmt: skip


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


def _money(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() and d >= 0 else None


def _zip5(v: Any) -> str | None:
    z = str(v or "").strip()
    return z[:5] if len(z) >= 5 and z[:5].isdigit() else None


def account_uid(raw: Any) -> str | None:
    """'477067' and '0477067' are the same seven-digit tax account."""
    a = str(raw or "").strip()
    return f"{COUNTY}-{a.zfill(7)}" if _ACCOUNT.match(a) else None


def _street(r: Mapping[str, Any]) -> str | None:
    number = (_text(r.get("house_number")) or "").lstrip("0") or None
    parts = (number, _text(r.get("house_suffix")), _text(r.get("street_direction")),
             _text(r.get("street_name")), _text(r.get("street_type")))  # fmt: skip
    line = " ".join(p for p in parts if p)
    unit = _text(r.get("unit"))
    return (f"{line} UNIT {unit}" if unit else line) or None


class PrinceGeorgesProperty(Adapter):
    source_id: ClassVar[str] = "md.prince_georges.parcels"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = ("owner_name", "ico_name", "mail_street")

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "assessor",
            "jurisdiction": COUNTY,
            "access_method": "api",
            "base_url": f"{PORTAL}/resource/{DATASET}.json",
            "terms_url": f"{PORTAL}/d/{DATASET}",
            "terms_summary": (
                "Prince George's County Open Data (Socrata) 'Property', updated monthly; free, "
                "no login. No license or use restriction stated on the dataset (read "
                "2026-11-24); robots.txt asks a 1 s crawl delay and disallows browse pages only."
            ),
            "terms_checked_on": "2026-11-24",
            "robots_checked_on": "2026-11-24",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {}

    def fetch(self, request: FetchRequest) -> Fetched:
        limit = request.params.get("limit")
        q = SocrataQuery(PORTAL, DATASET, "account IS NOT NULL", ("account", ":id"),
                         int(limit) if limit else 50_000, SELECT)  # fmt: skip
        rows, resp = fetch_all(self.client, q, max_pages=1 if limit else 100,
                               sample=limit is not None)  # fmt: skip
        return Fetched(self.source_id, q.url, resp[-1].retrieved_at, 200,
                       canonical_json({"rows": rows}), "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for r in sorted(json.loads(fetched.content).get("rows") or [],
                        key=lambda x: (str(x.get("account")), canonical_json(x))):  # fmt: skip
            uid = account_uid(r.get("account"))
            if uid is None or uid in seen or _text(r.get("inactive_date")):
                continue
            seen.add(uid)
            local = uid.split("-", 1)[1]
            ctx = RecordContext(fetched, COUNTY, local, "parcel", r)
            yield ctx.source_record()
            situs = normalized_address(_street(r), _text(r.get("city")), "MD",
                                       _zip5(r.get("zip5")))  # fmt: skip
            if situs is not None:
                yield NormalizedRow("address", situs)
            yield ctx.fact("parcel", parcel_uid=uid, parid_raw=local,
                           situs_address_id=situs["address_id"] if situs else None,
                           land_use_code=_text(r.get("bpruc")),
                           land_use_desc=_text(r.get("dwelling_type")), zoning=None)  # fmt: skip
            mail = normalized_address(_text(r.get("mail_street")), _text(r.get("mail_city")),
                                      _text(r.get("mail_state")),
                                      _zip5(r.get("mail_zip5")))  # fmt: skip
            if mail is not None:
                yield NormalizedRow("address", mail)
            names = [n for n in (_text(r.get("owner_name")), _text(r.get("ico_name"))) if n]
            for seq, name in enumerate(dict.fromkeys(names), start=1):
                nc = classify(name)
                party_id = stable_id(self.source_id, local, "owner", str(seq), clean(name))
                yield ctx.fact("party", party_id=party_id, raw_name=name,
                               party_kind=nc.party_kind, org_form=nc.org_form,
                               org_name_norm=nc.org_name_norm,
                               address_id=mail["address_id"] if mail else None)  # fmt: skip
                yield ctx.fact("owner_snapshot", parcel_uid=uid, owner_seq=seq,
                               party_id=party_id, deed_book=None, deed_page=None,
                               owner_type=None, observed_on=observed)  # fmt: skip

    def health(self) -> HealthReport:
        q = SocrataQuery(PORTAL, DATASET, "account IS NOT NULL", (":id",), 1)
        resp = get_page(self.client, q, 0)
        ok = resp.status == 200 and len(parse_rows(resp.content)) == 1
        return HealthReport(self.source_id, ok, datetime.now(UTC), f"status={resp.status}")
