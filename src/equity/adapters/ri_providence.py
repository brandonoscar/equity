"""City of Providence 2024 Property Tax Roll (data.providenceri.gov xvti-7dtw, ODC-BY).

The Rhode Island statewide parcel layer has boundaries only. Providence's tax roll gives the
owner (first and last name, or a company), the owner's mailing address, the property address
and the total assessment for each plat-lot-unit. tax_map ("041-0029-0000") keys to the
statewide parcel: PlatLot "PR 041-0029-0000" -> parcel_uid "44007-PR041-0029-0000".

The 2024 roll is used because it carries an explicit license (Open Data Commons Attribution:
credit the City of Providence); the 2025 roll lists none.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataQuery, fetch_all, get_page, parse_rows
from equity.adapters.state_parcels import normalized_address
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PORTAL = "https://data.providenceri.gov"
DATASET = "xvti-7dtw"
COUNTY = "44007"
TAX_YEAR = 2024
_TAX_MAP = re.compile(r"^[0-9]{3}-[0-9]{4}-[0-9]{4}$")


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


def _money(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() and d >= 0 else None


def _street(*parts: Any) -> str | None:
    return " ".join(p for p in (_text(x) for x in parts) if p) or None


def _zip5(v: Any) -> str | None:
    z = str(v or "").strip()
    return z[:5] if len(z) >= 5 and z[:5].isdigit() else None


class ProvidenceTaxRoll(Adapter):
    source_id: ClassVar[str] = "ri.providence.parcels"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = ("first_name", "last_name", "company",
                                             "free_line_2", "street_1", "civic_1")  # fmt: skip

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "assessor",
            "jurisdiction": COUNTY,
            "access_method": "api",
            "base_url": f"{PORTAL}/resource/{DATASET}.json",
            "terms_url": "https://data.providenceri.gov/Finance/2024-Property-Tax-Roll/xvti-7dtw",
            "terms_summary": (
                "City of Providence 2024 Property Tax Roll; license Open Data Commons "
                "Attribution (credit the City of Providence)."
            ),
            "terms_checked_on": "2026-11-23",
            "robots_checked_on": "2026-11-23",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {}

    def fetch(self, request: FetchRequest) -> Fetched:
        limit = request.params.get("limit")
        q = SocrataQuery(PORTAL, DATASET, "tax_map IS NOT NULL", ("tax_map", ":id"),
                         int(limit) if limit else 50_000)  # fmt: skip
        rows, resp = fetch_all(self.client, q, max_pages=1 if limit else 100,
                               sample=limit is not None)  # fmt: skip
        return Fetched(self.source_id, q.url, resp[-1].retrieved_at, 200,
                       canonical_json({"rows": rows}), "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for r in sorted(json.loads(fetched.content).get("rows") or [],
                        key=lambda x: (str(x.get("tax_map")), canonical_json(x))):  # fmt: skip
            tax_map = _text(r.get("tax_map"))
            if tax_map is None or not _TAX_MAP.match(tax_map) or tax_map in seen:
                continue
            seen.add(tax_map)
            local = f"PR{tax_map}"
            uid = f"{COUNTY}-{local}"
            ctx = RecordContext(fetched, COUNTY, local, "parcel", r)
            yield ctx.source_record()
            street = _street(r.get("civic"), r.get("street"), r.get("suffix"))
            situs = normalized_address(street, _text(r.get("city")), "RI",
                                       _zip5(r.get("zip_postal")))  # fmt: skip
            if situs is not None:
                yield NormalizedRow("address", situs)
            yield ctx.fact("parcel", parcel_uid=uid, parid_raw=local,
                           situs_address_id=situs["address_id"] if situs else None,
                           land_use_code=_text(r.get("class")),
                           land_use_desc=_text(r.get("short_desc")), zoning=None)  # fmt: skip
            mail = normalized_address(
                _street(r.get("civic_1"), r.get("street_1"), r.get("s_suffix"), r.get("unit_1")),
                _text(r.get("city_1")),
                _text(r.get("state")),
                _zip5(r.get("zip_postal_1")),
            )
            if mail is not None:
                yield NormalizedRow("address", mail)
            first, last, company = (_text(r.get("first_name")), _text(r.get("last_name")),
                                    _text(r.get("company")))  # fmt: skip
            names: list[tuple[str, dict[str, str | None]]] = []
            if last:
                names.append((" ".join(p for p in (first, last) if p),
                              {"first_name": first, "middle": None, "last_name": last,
                               "suffix": None}))  # fmt: skip
            if company:
                names.append((company, dict.fromkeys(("first_name", "middle", "last_name",
                                                      "suffix"))))  # fmt: skip
            for seq, (name, parts) in enumerate(names, start=1):
                nc = classify(name)
                party_id = stable_id(self.source_id, local, "owner", str(seq), clean(name))
                yield ctx.fact("party", party_id=party_id, raw_name=name,
                               party_kind="person" if parts["last_name"] else nc.party_kind,
                               org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                               address_id=mail["address_id"] if mail else None,
                               **parts)  # fmt: skip
                yield ctx.fact("owner_snapshot", parcel_uid=uid, owner_seq=seq,
                               party_id=party_id, deed_book=None, deed_page=None,
                               owner_type=None, observed_on=observed)  # fmt: skip
            total = _money(r.get("total_assmt"))
            if total is not None:
                yield ctx.fact("parcel_assessment", parcel_uid=uid, tax_year=TAX_YEAR,
                               appraised_land=None, appraised_bldg=None, appraised_total=None,
                               assessed_value=total, tax_class=_text(r.get("class")),
                               valid_from=date(TAX_YEAR, 1, 1), valid_to=None,
                               homestead=None)  # fmt: skip

    def health(self) -> HealthReport:
        q = SocrataQuery(PORTAL, DATASET, "tax_map IS NOT NULL", (":id",), 1)
        resp = get_page(self.client, q, 0)
        ok = resp.status == 200 and len(parse_rows(resp.content)) == 1
        return HealthReport(self.source_id, ok, datetime.now(UTC), f"status={resp.status}")
