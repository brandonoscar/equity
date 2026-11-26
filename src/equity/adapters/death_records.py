"""Cook County Medical Examiner lists that name the dead: a death signal, kept apart from the
address-based person lists and never matched here.

The Medical Examiner publishes, on the Cook County open data portal (Socrata, free, no login):

  il.cook.me_unclaimed_persons     jmub-3h99  decedents whose remains no one has claimed (a
                                              short current list; arrival date, no death date)
  il.cook.me_indigent_cremations   f9wk-2wb9  decedents cremated at county expense
  il.cook.me_burials               hc2f-evny  county burials: cemetery, block, lot, grave
  il.cook.me_heights_crematory     a7ds-fgg3  remains recovered from a closed crematory
                                              (Heights Crematory), with alternate spellings

Each row is one death_record: case number, name, death date, age, sex and the place where
published. None of these lists gives the decedent's address, so a name alone cannot tie a
record to a debtor or an owner: a same-name debtor is a reason to check (probate, an
obituary) before acting, not a finding. Any rule that flags debtors from this table is a
matching rule and waits for the owner's approval; the table only loads the records.
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
from equity.matching.orgs import clean

PORTAL = "https://datacatalog.cookcountyil.gov"
COOK = "17031"


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def _age(v: Any) -> int | None:
    s = str(v or "").strip().split(" ")[0]
    return int(s) if s.isdigit() and int(s) <= 130 else None


def _sex(v: Any) -> str | None:
    s = str(v or "").strip().upper()[:1]
    return s if s in ("F", "M") else None


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


class _CookMEList(Adapter):
    """One Medical Examiner dataset, fetched whole (a few thousand rows at most)."""

    dataset: ClassVar[str]
    title: ClassVar[str]
    record_kind: ClassVar[str]
    license: ClassVar[str]
    case_field: ClassVar[str] = "case"
    name_field: ClassVar[str] = "name"
    death_field: ClassVar[str | None] = "date_of_death"
    listed_field: ClassVar[str | None] = None
    age_field: ClassVar[str] = "age"
    sex_field: ClassVar[str] = "sex"
    place_fields: ClassVar[tuple[str, ...]] = ()
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = (
        "name",
        "decedent",
        "alternate_spellings",
        "place_of_death",
    )

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "vital_record",
            "jurisdiction": COOK,
            "access_method": "api",
            "base_url": f"{PORTAL}/resource/{self.dataset}.json",
            "terms_url": f"{PORTAL}/d/{self.dataset}",
            "terms_summary": (
                f"Cook County Medical Examiner '{self.title}' on the Cook County open data "
                f"portal (Socrata), free, no login; {self.license}. No decedent address is "
                "published. datacatalog.cookcountyil.gov/robots.txt allows /resource/ "
                "(Crawl-delay: 1)."
            ),
            "terms_checked_on": "2026-11-26",
            "robots_checked_on": "2026-11-26",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {}

    def fetch(self, request: FetchRequest) -> Fetched:
        limit = request.params.get("limit")
        q = SocrataQuery(PORTAL, self.dataset, "1=1", (":id",),
                         int(limit) if limit else 50_000)  # fmt: skip
        rows, resp = fetch_all(self.client, q, max_pages=1 if limit else 100, sample=bool(limit))
        return Fetched(self.source_id, q.url, resp[-1].retrieved_at, 200,
                       canonical_json({"rows": rows}), "application/json")  # fmt: skip

    def alternates(self, row: Mapping[str, Any]) -> list[str]:
        return []

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        seen: set[str] = set()
        for row in sorted(json.loads(fetched.content).get("rows") or [], key=canonical_json):
            case, name = _text(row.get(self.case_field)), _text(row.get(self.name_field))
            norm = clean(name) if name else ""
            if not case or not norm or case in seen:
                continue
            seen.add(case)
            place = ", ".join(p for p in (_text(row.get(f)) for f in self.place_fields) if p)
            ctx = RecordContext(fetched, COOK, case, "me_case", row)
            yield ctx.source_record()
            yield ctx.fact(
                "death_record", case_number=case, record_kind=self.record_kind,
                raw_name=name, name_norm=norm, alternate_names=self.alternates(row) or None,
                death_date=_date(row.get(self.death_field)) if self.death_field else None,
                listed_on=_date(row.get(self.listed_field)) if self.listed_field else None,
                age_years=_age(row.get(self.age_field)), sex=_sex(row.get(self.sex_field)),
                county_fips=COOK, place=place or None,
            )  # fmt: skip

    def health(self) -> HealthReport:
        n = len(json.loads(self.fetch(FetchRequest({"limit": "5"})).content)["rows"])
        return HealthReport(self.source_id, n > 0, datetime.now(UTC), f"{n} sample rows")


NO_LICENSE = "no license tag on the dataset (Cook County open data terms: disclaimers only)"


class CookUnclaimedPersons(_CookMEList):
    source_id: ClassVar[str] = "il.cook.me_unclaimed_persons"
    dataset: ClassVar[str] = "jmub-3h99"
    title: ClassVar[str] = "Medical Examiner - Unclaimed Persons"
    record_kind: ClassVar[str] = "unclaimed"
    license: ClassVar[str] = "license Public Domain"
    death_field: ClassVar[str | None] = None
    listed_field: ClassVar[str | None] = "date_of_arrival"
    age_field: ClassVar[str] = "age_sex_race"
    sex_field: ClassVar[str] = "gender"


class CookIndigentCremations(_CookMEList):
    source_id: ClassVar[str] = "il.cook.me_indigent_cremations"
    dataset: ClassVar[str] = "f9wk-2wb9"
    title: ClassVar[str] = "Medical Examiner Indigent Cremations"
    record_kind: ClassVar[str] = "indigent_cremation"
    license: ClassVar[str] = NO_LICENSE
    listed_field: ClassVar[str | None] = "cremation_date"


class CookBurials(_CookMEList):
    source_id: ClassVar[str] = "il.cook.me_burials"
    dataset: ClassVar[str] = "hc2f-evny"
    title: ClassVar[str] = "Medical Examiner - Burial Locations"
    record_kind: ClassVar[str] = "county_burial"
    license: ClassVar[str] = NO_LICENSE
    listed_field: ClassVar[str | None] = "burial_date"
    place_fields: ClassVar[tuple[str, ...]] = ("cemetery", "cemetery_address")


class CookHeightsCrematory(_CookMEList):
    source_id: ClassVar[str] = "il.cook.me_heights_crematory"
    dataset: ClassVar[str] = "a7ds-fgg3"
    title: ClassVar[str] = "Heights Crematory Cremated Remains"
    record_kind: ClassVar[str] = "crematory_remains"
    license: ClassVar[str] = NO_LICENSE
    case_field: ClassVar[str] = "case_number"
    name_field: ClassVar[str] = "decedent"
    place_fields: ClassVar[tuple[str, ...]] = ("place_of_death",)

    def alternates(self, row: Mapping[str, Any]) -> list[str]:
        raw = _text(row.get("alternate_spellings")) or ""
        return sorted({clean(p) for p in raw.replace(";", ",").split(",") if clean(p)})


ADAPTERS = (CookUnclaimedPersons, CookIndigentCremations, CookBurials, CookHeightsCrematory)
