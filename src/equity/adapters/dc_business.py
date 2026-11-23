"""District of Columbia business registrations and beneficial owners (DLCP, CC BY 4.0).

Two tables on DC GIS (Business_Licensing_and_Grants MapServer):
  layer 0  Corporate Registration: file number, name, type, status, business address,
           registered agent and address, effective date (about 507K entities)
  layer 2  Beneficial Owners: owner name and one-line address per entity (INITIALFILENUMBER =
           layer 0 FILE_NUMBER), about 495K rows: the people behind DC LLCs and corporations

Partitions are windows of each layer's (sparse) OBJECTIDs. An owner row is tied to its entity
by the file number, so the two layers need not be read together. Owners are business_role
"other" titled BENEFICIAL OWNER, dated from the table's last-modified date (no start date is
published).
Credit: District of Columbia, Department of Licensing and Consumer Protection (DLCP).
"""

from __future__ import annotations

import json
import re
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

BASE = ("https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/"
        "Business_Licensing_and_Grants_WebMercator/MapServer")  # fmt: skip
REGISTRATIONS, OWNERS = "0", "2"
WINDOW = 25_000
_ZIP = re.compile(r"^[0-9]{5}(?:-?[0-9]{4})?$")
_STATE = re.compile(r"^[A-Z]{2}$")


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


def _epoch_date(v: Any) -> date | None:
    try:
        return datetime.fromtimestamp(int(v) / 1000, tz=UTC).date()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def one_line_address(text: str | None) -> dict[str, Any] | None:
    """'street[, unit], city, ST, ZIP[, country]' -> normalized address; unparsed text keeps
    its street only."""
    parts = [p.strip() for p in (text or "").split(",") if p.strip()]
    if parts and not _ZIP.match(parts[-1]) and len(parts[-1]) <= 3 and parts[-1].isalpha():
        parts = parts[:-1]  # country code
    if len(parts) >= 4 and _ZIP.match(parts[-1]) and _STATE.match(parts[-2].upper()):
        return normalized_address(" ".join(parts[:-3]), parts[-3], parts[-2].upper(),
                                  parts[-1][:5])  # fmt: skip
    return normalized_address(" ".join(parts) or None, None, None, None)


def _addr(a: Mapping[str, Any], lines: tuple[str, ...], city: str, st: str, z: str) -> Any:
    street = " ".join(x for x in (_text(a.get(f)) for f in lines) if x) or None
    zip_raw = str(a.get(z) or "").strip()
    zip5 = zip_raw[:5] if _ZIP.match(zip_raw) else None
    return normalized_address(street, _text(a.get(city)), _text(a.get(st)), zip5)


class DCBusiness(Adapter):
    source_id: ClassVar[str] = "dc.dlcp.business"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "arcgis"
    pii_fields: ClassVar[tuple[str, ...]] = (
        "BUSINESS_NAME", "BUSNIESS_ADDRESS_LINE1", "BUSNIESS_ADDRESS_LINE2",
        "BUSNIESS_ADDRESS_LINE3", "BUSNIESS_ADDRESS_LINE4", "RA_NAME", "RA_ADDRESS1",
        "RA_ADDRESS2", "RA_ADDRESS3", "RA_ADDRESS4", "NAME", "ADDRESS", "BUSINESSNAME",
    )  # fmt: skip

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",
            "jurisdiction": "11",
            "access_method": "arcgis",
            "base_url": BASE,
            "terms_url": "https://opendata.dc.gov/",
            "terms_summary": (
                "DC GIS / DLCP Corporate Registration and Beneficial Owners tables; license "
                "Creative Commons Attribution 4.0 (credit the District of Columbia, DLCP)."
            ),
            "terms_checked_on": "2026-11-22",
            "robots_checked_on": "2026-11-22",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        """OBJECTIDs are sparse 9-digit numbers: read every id (one request per layer) and cut
        the sorted list into windows of WINDOW ids."""
        for layer in (REGISTRATIONS, OWNERS):
            body = get_json(self.client, f"{BASE}/{layer}/query",
                            {"where": "1=1", "returnIdsOnly": "true", "f": "json"})  # fmt: skip
            ids = sorted(int(i) for i in body.get("objectIds") or [])
            for i in range(0, len(ids), WINDOW):
                hi = ids[i + WINDOW] if i + WINDOW < len(ids) else ids[-1] + 1
                yield {"layer": layer, "lo": str(ids[i]), "hi": str(hi)}

    def fetch(self, request: FetchRequest) -> Fetched:
        p = request.params
        layer = p["layer"]
        if layer not in (REGISTRATIONS, OWNERS):
            raise ValueError(f"unknown layer {layer!r}")
        lo, hi = int(p["lo"]), int(p["hi"])  # ints only reach the query
        limit = int(p["limit"]) if "limit" in p else None
        q = ArcGISQuery(f"{BASE}/{layer}", f"OBJECTID >= {lo} AND OBJECTID < {hi}", ("*",),
                        ("OBJECTID",), limit or 2000)  # fmt: skip
        feats, resp = fetch_all(self.client, q, max_pages=1 if limit else 10_000,
                                sample=limit is not None)  # fmt: skip
        body = {"layer": layer, "rows": [f["attributes"] for f in feats]}
        return Fetched(self.source_id, f"{BASE}/{layer}/query?lo={lo}&hi={hi}",
                       resp[-1].retrieved_at, 200, canonical_json(body),
                       "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        rows = sorted(data.get("rows") or [], key=lambda a: int(a.get("OBJECTID") or 0))
        if data.get("layer") == OWNERS:
            yield from self._owners(fetched, observed, rows)
        else:
            yield from self._registrations(fetched, observed, rows)

    def _registrations(
        self, fetched: Fetched, observed: date, rows: list[Mapping[str, Any]]
    ) -> Iterator[NormalizedRow]:
        seen: set[str] = set()
        for a in rows:
            key, name = _text(a.get("FILE_NUMBER")), _text(a.get("BUSINESS_NAME"))
            if key is None or name is None or key in seen:
                continue
            seen.add(key)
            ctx = RecordContext(fetched, "11", key, "business_entity", a)
            yield ctx.source_record()
            formed = _epoch_date(a.get("EFFECTIVE_DATE"))
            formed = formed if formed and formed <= observed else None
            principal = _addr(a, ("BUSNIESS_ADDRESS_LINE1", "BUSNIESS_ADDRESS_LINE2",
                                  "BUSNIESS_ADDRESS_LINE3", "BUSNIESS_ADDRESS_LINE4"),
                              "BUSINESS_CITY", "BUSINESS_STATE", "ZIPCODE")  # fmt: skip
            if principal is not None:
                yield NormalizedRow("address", principal)
            nc = classify(name)
            yield ctx.fact("business", sos_id=key, name=name, org_form=nc.org_form,
                           status=_text(a.get("ENTITY_STATUS")), formed_on=formed,
                           status_date=None,
                           principal_address_id=principal["address_id"] if principal else None,
                           mailing_address_id=None, valid_from=formed or observed,
                           valid_to=None)  # fmt: skip
            agent = _text(a.get("RA_NAME"))
            if agent:
                addr = _addr(a, ("RA_ADDRESS1", "RA_ADDRESS2", "RA_ADDRESS3", "RA_ADDRESS4"),
                             "RA_CITY", "RA_STATE", "RA_ZIPCODE")  # fmt: skip
                yield from self._holder(ctx, key, "registered_agent", "REGISTERED AGENT", agent,
                                        addr, formed or observed)  # fmt: skip

    def _owners(
        self, fetched: Fetched, observed: date, rows: list[Mapping[str, Any]]
    ) -> Iterator[NormalizedRow]:
        for a in rows:
            key, who = _text(a.get("INITIALFILENUMBER")), _text(a.get("NAME"))
            oid = _text(a.get("OBJECTID"))
            if key is None or who is None or oid is None:
                continue
            ctx = RecordContext(fetched, "11", f"owner-{oid}", "beneficial_owner", a)
            yield ctx.source_record()
            since = _epoch_date(a.get("DCS_LAST_MOD_DTTM"))
            since = since if since and since <= observed else observed
            yield from self._holder(ctx, key, "other", "BENEFICIAL OWNER", who,
                                    one_line_address(_text(a.get("ADDRESS"))), since)  # fmt: skip

    def _holder(self, ctx: RecordContext, key: str, role: str, title: str, who: str,
                addr: dict[str, Any] | None, since: date) -> Iterator[NormalizedRow]:  # fmt: skip
        if addr is not None:
            yield NormalizedRow("address", addr)
        pc = classify(who)
        party_id = stable_id(self.source_id, key, role, clean(who))
        yield ctx.fact("party", party_id=party_id, raw_name=who, party_kind=pc.party_kind,
                       org_form=pc.org_form, org_name_norm=pc.org_name_norm,
                       address_id=addr["address_id"] if addr else None)  # fmt: skip
        yield ctx.fact("business_role", sos_id=key, party_id=party_id, role=role, title=title,
                       valid_from=since, valid_to=None)  # fmt: skip

    def health(self) -> HealthReport:
        body = get_json(self.client, f"{BASE}/{OWNERS}/query",
                        {"where": "1=1", "returnCountOnly": "true", "f": "json"})  # fmt: skip
        n = int(body.get("count") or 0)
        return HealthReport(self.source_id, n > 100_000, datetime.now(UTC), f"{n} owner rows")
