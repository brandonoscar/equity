"""Published assessment ratios: the share of market value at which a town assesses property.

Many rolls assess at a fraction of market value (a NY town at 45%, a CT town at 70%), so an
assessed value is not a market value. State equalization agencies publish the ratio per
municipality and year; value / (ratio / 100) estimates market value. These sources only load
the ratios (table assessment_ratio). Applying them in equity is a separate step the project
owner approves.

  ny.orpts.residential_assessment_ratios  NYS ORPTS 'Residential Assessment Ratios'
                                          (data.ny.gov bsmp-6um6, from 1982), per SWIS code
  ny.orpts.equalization_rates             NYS ORPTS 'Equalization Rates' (data.ny.gov
                                          e6pv-77bh, from 1954), all property, per SWIS code
  ct.opm.equalized_grand_list             CT OPM 'Equalized Net Grand List by Town' (data.ct.gov
                                          8rr8-a322, Public Domain, 2011 on): the ratio per
                                          property class (residential, apartments, commercial
                                          and industrial, vacant, personal property)
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataQuery, fetch_all


def _pct(v: Any) -> float | None:
    try:
        x = float(str(v))
    except (TypeError, ValueError):
        return None
    return x if 0 < x < 10_000 else None


def _year(v: Any) -> int | None:
    s = str(v or "").strip()[:4]
    return int(s) if s.isdigit() and 1900 <= int(s) <= 2200 else None


class _RatioSource(Adapter):
    """One Socrata dataset of ratios, fetched whole (tens of thousands of rows at most)."""

    portal: ClassVar[str]
    dataset: ClassVar[str]
    jurisdiction: ClassVar[str]
    terms: ClassVar[str]
    access_method: ClassVar[str] = "api"
    adapter_version: ClassVar[str] = "1"

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "assessor",
            "jurisdiction": self.jurisdiction,
            "access_method": "api",
            "base_url": f"{self.portal}/resource/{self.dataset}.json",
            "terms_url": f"{self.portal}/d/{self.dataset}",
            "terms_summary": self.terms,
            "terms_checked_on": "2026-11-26",
            "robots_checked_on": "2026-11-26",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {}

    def fetch(self, request: FetchRequest) -> Fetched:
        limit = request.params.get("limit")
        q = SocrataQuery(self.portal, self.dataset, "1=1", (":id",),
                         int(limit) if limit else 50_000)  # fmt: skip
        rows, resp = fetch_all(self.client, q, max_pages=1 if limit else 1000, sample=bool(limit))
        return Fetched(self.source_id, q.url, resp[-1].retrieved_at, 200,
                       canonical_json({"rows": rows}), "application/json")  # fmt: skip

    def facts(self, row: Mapping[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        seen: set[str] = set()
        for row in sorted(json.loads(fetched.content).get("rows") or [], key=canonical_json):
            out = self.facts(row)
            if not out:
                continue
            key = "|".join(str(out[0][k]) for k in ("geo_id", "year")) + "|" + \
                ",".join(f"{f['property_class']}:{f['ratio_kind']}" for f in out)  # fmt: skip
            if key in seen:
                continue
            seen.add(key)
            ctx = RecordContext(fetched, self.jurisdiction, key, "ratio_row", row)
            yield ctx.source_record()
            for f in out:
                yield ctx.fact("assessment_ratio", **f)

    def health(self) -> HealthReport:
        n = len(json.loads(self.fetch(FetchRequest({"limit": "5"})).content)["rows"])
        return HealthReport(self.source_id, n > 0, datetime.now(UTC), f"{n} sample rows")


NY_TERMS = (
    "NYS Department of Taxation and Finance, Office of Real Property Tax Services, on "
    "data.ny.gov (NY Open Data, free, no login; robots.txt asks Crawl-delay 1)."
)


class _NYRatios(_RatioSource):
    portal: ClassVar[str] = "https://data.ny.gov"
    jurisdiction: ClassVar[str] = "36"
    terms: ClassVar[str] = NY_TERMS
    field: ClassVar[str]
    kind: ClassVar[str]
    property_class: ClassVar[str]

    def facts(self, row: Mapping[str, Any]) -> list[dict[str, Any]]:
        swis, year, pct = str(row.get("swis_code") or "").strip(), _year(row.get("rate_year")), \
            _pct(row.get(self.field))  # fmt: skip
        if not (len(swis) == 6 and swis.isdigit() and year and pct):
            return []
        name = " ".join(x for x in (row.get("municipality_name"), row.get("village_name"))
                        if x) or row.get("county_name")  # fmt: skip
        return [{"geo_level": "ny_swis", "geo_id": swis, "geo_name": name, "year": year,
                 "property_class": self.property_class, "ratio_kind": self.kind,
                 "ratio_pct": pct}]  # fmt: skip


class NYResidentialAssessmentRatios(_NYRatios):
    source_id: ClassVar[str] = "ny.orpts.residential_assessment_ratios"
    dataset: ClassVar[str] = "bsmp-6um6"
    field: ClassVar[str] = "residential_assessment_ratio"
    kind: ClassVar[str] = "residential_assessment_ratio"
    property_class: ClassVar[str] = "residential"


class NYEqualizationRates(_NYRatios):
    source_id: ClassVar[str] = "ny.orpts.equalization_rates"
    dataset: ClassVar[str] = "e6pv-77bh"
    field: ClassVar[str] = "equalization_rate"
    kind: ClassVar[str] = "equalization_rate"
    property_class: ClassVar[str] = "all"


CT_CLASSES = {"residential_ratio": "residential", "apartments_ratio": "apartments",
              "cip_ratio": "commercial_industrial", "vacant_ratio": "vacant",
              "total_personal_property_ratio": "personal"}  # fmt: skip


class CTEqualizedGrandList(_RatioSource):
    source_id: ClassVar[str] = "ct.opm.equalized_grand_list"
    portal: ClassVar[str] = "https://data.ct.gov"
    dataset: ClassVar[str] = "8rr8-a322"
    jurisdiction: ClassVar[str] = "09"
    terms: ClassVar[str] = (
        "CT Office of Policy and Management 'Equalized Net Grand List by Town', data.ct.gov, "
        "license Public Domain; free, no login."
    )

    def facts(self, row: Mapping[str, Any]) -> list[dict[str, Any]]:
        town, year = str(row.get("town_code") or "").strip(), _year(row.get("grand_list_year"))
        if not (town.isdigit() and year):
            return []
        out = []
        for field, cls in CT_CLASSES.items():
            pct = _pct(row.get(field))
            if pct:
                out.append({"geo_level": "ct_town", "geo_id": town.zfill(3),
                            "geo_name": row.get("town_name"), "year": year,
                            "property_class": cls, "ratio_kind": "equalized_ratio",
                            "ratio_pct": pct})  # fmt: skip
        return out


ADAPTERS = (NYResidentialAssessmentRatios, NYEqualizationRates, CTEqualizedGrandList)
