"""NYC ACRIS (City Register) from NYC Open Data: recorded documents for Manhattan, the Bronx,
Brooklyn and Queens (Staten Island records live with the Richmond County Clerk).

Two families share one layout: Real Property (deeds, mortgages, assignments, satisfactions,
recorded judgments, NYC tax-lien certificates) and Personal Property (UCC filings and federal
tax liens). Each family is four Socrata datasets joined on document_id: master (one row per
document), legals (lots), parties and references (cross-references to earlier documents).

A fetch covers one document_id range in all four datasets, so normalize() sees every row of a
document together. Ranges are calendar months for modern ids (YYYYMMDD...) and three-character
prefixes for the pre-2003 legacy ids (FT_..., BK_...).

Rules here are classification only, read from config/recorders/ny.nyc.acris.yaml:
doc code -> doc_type, party label -> role, doc code -> reference type.

Parcels: an ACRIS lot is borough-block-lot (BBL). parcel_uid follows the NYS tax parcel layer
(ny.statewide.parcels): <county FIPS>-<SWIS><BBL>, so documents join to those parcels directly.
This source emits no parcel rows of its own (one lot appears in many partitions).

Source: https://data.cityofnewyork.us (robots: /resource/ allowed, Crawl-delay 1, checked
2026-11-16). Terms: NYC Open Data terms of use, no restriction on use found; to be read in full.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from functools import cache
from typing import Any, ClassVar

from equity.adapters.base import (
    Adapter,
    Fetched,
    FetchRequest,
    HealthReport,
    NormalizedRow,
)
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataQuery, fetch_all, quote
from equity.adapters.state_parcels import normalized_address
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PORTAL = "https://data.cityofnewyork.us"
CONFIG = "recorders/ny.nyc.acris.yaml"
# Fields replaced with pseudonyms when recording fixtures (the repo is public).
PII_FIELDS: tuple[str, ...] = ("name", "address_1", "address_2")
# Amount columns: deeds and leases carry a price; everything else a secured or lien amount.
CONSIDERATION_DOC_TYPES = frozenset({"DEED", "LEASE"})
ID_CHUNK = 300  # document ids per "document_id in (...)" query: keeps URLs near 6 KB


@dataclass(frozen=True)
class AcrisCode:
    doc_type: str
    ref_type: str | None
    parties: tuple[str, ...]


@dataclass(frozen=True)
class AcrisConfig:
    codes: Mapping[str, AcrisCode]
    label_roles: Mapping[str, str]
    boroughs: Mapping[str, tuple[str, str]]  # borough -> (county FIPS, SWIS)
    zero_amount_is_unknown: bool
    legacy_prefixes: tuple[str, ...]


@cache
def load_config() -> AcrisConfig:
    import yaml

    data = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    codes = {
        str(code): AcrisCode(
            str(spec["doc_type"]), spec.get("ref_type"), tuple(str(p) for p in spec["parties"])
        )
        for code, spec in data["codes"].items()
    }
    boroughs = {
        str(b): (str(v["county_fips"]), str(v["swis"])) for b, v in data["boroughs"].items()
    }
    return AcrisConfig(
        codes=codes,
        label_roles={str(k): str(v) for k, v in data["label_roles"].items()},
        boroughs=boroughs,
        zero_amount_is_unknown=bool(data["zero_amount_is_unknown"]),
        legacy_prefixes=tuple(str(p) for p in data["legacy_prefixes"]),
    )


@dataclass(frozen=True)
class Family:
    master: str
    legals: str
    parties: str
    references: str
    ref_doc_field: str  # field in `references` holding the referenced document_id


REAL = Family("bnx9-e6tj", "8h5j-fqxa", "636b-3b5g", "pwkr-dpni", "reference_by_doc_id")
PERSONAL = Family("sv7x-dduq", "uqqa-hym2", "nbbg-wtuz", "6y3e-jcrc", "doc_id_ref")


def instrument_uid(document_id: str) -> str:
    return f"ny.nyc.acris:{document_id}"


def _int(value: Any) -> int | None:
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None


def bbl(row: Mapping[str, Any]) -> str | None:
    """10-digit borough-block-lot, or None when a part is missing or out of range."""
    b, blk, lot = _int(row.get("borough")), _int(row.get("block")), _int(row.get("lot"))
    if b is None or blk is None or lot is None:
        return None
    if not (1 <= b <= 5 and 0 <= blk <= 99999 and 0 <= lot <= 9999):
        return None
    return f"{b}{blk:05d}{lot:04d}"


def parcel_uid_for(bbl10: str, cfg: AcrisConfig) -> str:
    county, swis = cfg.boroughs[bbl10[0]]
    return f"{county}-{swis}{bbl10}"


def _date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _amount(value: Any, zero_is_unknown: bool) -> Decimal | None:
    try:
        amt = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if amt < 0 or (zero_is_unknown and amt == 0):
        return None
    return amt.quantize(Decimal("0.01"))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    s = " ".join(str(value).split())
    return s or None


def month_ranges(first: date, last: date) -> Iterator[tuple[str, str]]:
    y, m = first.year, first.month
    while (y, m) <= (last.year, last.month):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        yield f"{y:04d}{m:02d}", f"{ny:04d}{nm:02d}"
        y, m = ny, nm


def prefix_ranges(prefix: str) -> Iterator[tuple[str, str]]:
    """prefix 'FT_1' -> ('FT_100', 'FT_101'), ... ('FT_199', 'FT_19:'): ':' sorts after '9'."""
    for i in range(100):
        lo = f"{prefix}{i:02d}"
        yield lo, lo[:-1] + chr(ord(lo[-1]) + 1)


class AcrisAdapter(Adapter):
    access_method: ClassVar[str] = "api"
    adapter_version: ClassVar[str] = "1"
    family: ClassVar[Family]
    record_type: ClassVar[str]
    pii_fields: ClassVar[tuple[str, ...]] = PII_FIELDS
    first_month: ClassVar[date] = date(2002, 12, 1)
    page_size: ClassVar[int] = 50_000

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "recorder",
            "jurisdiction": "36",
            "access_method": "api",
            "base_url": f"{PORTAL}/resource/{self.family.master}.json",
            "terms_url": "https://www.nyc.gov/html/data/terms.html",
            "terms_summary": (
                "NYC Open Data: no restriction on use found; informational, no warranty; "
                "agency terms also apply. Full terms page not yet read."
            ),
            "terms_checked_on": date(2026, 11, 16),
            "robots_checked_on": date(2026, 11, 16),
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        today = datetime.now(UTC).date()
        for lo, hi in month_ranges(self.first_month, today):
            yield {"lo": lo, "hi": hi}
        for prefix in load_config().legacy_prefixes:
            for lo, hi in prefix_ranges(prefix):
                yield {"lo": lo, "hi": hi}

    @staticmethod
    def where(params: Mapping[str, str]) -> str:
        """params: lo, hi (document_id range, hi exclusive) | ids (comma list, fixtures)."""
        if "ids" in params:
            ids = [i for i in params["ids"].split(",") if i]
            return "document_id in (" + ",".join(quote(i) for i in ids) + ")"
        return f"document_id >= {quote(params['lo'])} AND document_id < {quote(params['hi'])}"

    def _rows(self, dataset: str, where: str, limit: int | None = None) -> list[dict[str, Any]]:
        q = SocrataQuery(PORTAL, dataset, where, ("document_id", ":id"), limit or self.page_size)
        rows, _ = fetch_all(self.client, q, max_pages=1 if limit else 10_000, sample=bool(limit))
        return rows

    def fetch(self, request: FetchRequest) -> Fetched:
        """All four datasets for one document_id range.

        `codes` ('|'-separated doc codes; some codes contain commas) keeps only documents of
        those types: the other three datasets are read for the same id range (a few queries)
        and only the kept documents' rows are stored. `limit` (fixtures) keeps the first N
        master rows and reads the other datasets for exactly those ids, ID_CHUNK per query."""
        params = dict(request.params)
        limit = _int(params.pop("limit", None))
        codes = [c for c in params.pop("codes", "").split("|") if c]
        where = self.where(params)
        if codes:
            where += " AND doc_type in (" + ",".join(quote(c) for c in codes) + ")"
        f = self.family
        master = self._rows(f.master, where, limit)
        ids = {str(r["document_id"]) for r in master}
        if limit:
            ordered = sorted(ids)
            chunks = [ordered[i : i + ID_CHUNK] for i in range(0, len(ordered), ID_CHUNK)]
            related = [self.where({"ids": ",".join(c)}) for c in chunks]
        elif codes and not ids:
            related = []
        else:
            related = [self.where(params)]

        def rows(dataset: str) -> list[dict[str, Any]]:
            got = [r for w in related for r in self._rows(dataset, w)]
            return [r for r in got if str(r.get("document_id")) in ids] if codes else got

        body = {
            "portal": PORTAL,
            "where": where,
            "master": master,
            "legals": rows(f.legals),
            "parties": rows(f.parties),
            "references": rows(f.references),
        }
        return Fetched(
            source_id=self.source_id,
            request=f"{PORTAL}/resource/{f.master}.json?$where={where}",
            retrieved_at=datetime.now(UTC),
            http_status=200,
            content=canonical_json(body),
            content_type="application/json",
        )

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = load_config()
        data = json.loads(fetched.content)
        grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
            lambda: {"legals": [], "parties": [], "references": []}
        )
        for part in ("legals", "parties", "references"):
            for row in data[part]:
                grouped[str(row["document_id"])][part].append(row)
        masters: dict[str, dict[str, Any]] = {}
        for row in data["master"]:
            masters.setdefault(str(row["document_id"]), row)  # repeated rows: keep the first
        today = fetched.retrieved_at.astimezone(UTC).date()
        for doc_id in sorted(masters):
            yield from self._document(cfg, fetched, today, masters[doc_id], grouped[doc_id])

    def _document(
        self,
        cfg: AcrisConfig,
        fetched: Fetched,
        today: date,
        master: Mapping[str, Any],
        rel: Mapping[str, list[dict[str, Any]]],
    ) -> Iterator[NormalizedRow]:
        doc_id = str(master["document_id"])
        legals = sorted(rel["legals"], key=canonical_json)
        bbls = sorted({b for b in (bbl(r) for r in legals) if b is not None})
        borough = bbls[0][0] if bbls else str(_int(master.get("recorded_borough")) or "")
        county = cfg.boroughs.get(borough, ("36", ""))[0]
        raw = {"master": master, **{k: sorted(v, key=canonical_json) for k, v in rel.items()}}
        ctx = RecordContext(fetched, county, doc_id, self.record_type, raw)
        yield ctx.source_record()

        def issue(code: str, table: str, /, **detail: Any) -> NormalizedRow:
            return ctx.fact(
                "data_issue", issue_code=code, target_table=table,
                detail={"document_id": doc_id, **detail},
            )  # fmt: skip

        code_raw = _text(master.get("doc_type"))
        recorded_on = _date(master.get("recorded_datetime"))
        if code_raw is None or recorded_on is None:
            yield issue("missing_doc_type_or_recorded_date", "instrument",
                        doc_type=code_raw, recorded=master.get("recorded_datetime"))  # fmt: skip
            return
        if recorded_on > today:
            yield issue("recorded_after_retrieval", "instrument", recorded=str(recorded_on))
            return
        spec = cfg.codes.get(code_raw, AcrisCode("OTHER", None, ()))
        if code_raw not in cfg.codes:
            yield issue("unknown_doc_code", "instrument", doc_type=code_raw)
        executed_on = _date(master.get("document_date"))
        if executed_on is not None and executed_on > today:
            yield issue("executed_after_retrieval", "instrument", executed=str(executed_on))
            executed_on = None
        amount = _amount(master.get("document_amt"), cfg.zero_amount_is_unknown)
        is_price = spec.doc_type in CONSIDERATION_DOC_TYPES
        reel = _int(master.get("reel_nbr")) or 0
        reel_pg = _int(master.get("reel_pg")) or 0
        uid = instrument_uid(doc_id)
        yield ctx.fact(
            "instrument",
            instrument_uid=uid,
            instrument_number=_text(master.get("crfn")) or doc_id,
            book_type="REEL" if reel else None,
            book=str(reel) if reel else None,
            page=str(reel_pg) if reel and reel_pg else None,
            doc_type_raw=code_raw,
            doc_type=spec.doc_type,
            recorded_on=recorded_on,
            recorded_seq=None,
            executed_on=executed_on,
            consideration=amount if is_price else None,
            principal_amount=None if is_price else amount,
            max_secured_amount=None,
            maturity_date=None,
            amount_source="index" if amount is not None else None,
            legal_desc_raw=None,
        )
        parcel_uids = []
        for b in bbls:
            puid = parcel_uid_for(b, cfg)
            parcel_uids.append(puid)
            evidence = [
                {k: r.get(k) for k in ("borough", "block", "lot", "easement", "partial_lot",
                                       "air_rights", "subterranean_rights", "property_type")}
                for r in legals if bbl(r) == b
            ]  # fmt: skip
            yield ctx.fact(
                "instrument_parcel", instrument_uid=uid, parcel_uid=puid,
                method="index_parcel_id", evidence={"lots": evidence},
            )  # fmt: skip
        dropped = [r for r in legals if bbl(r) is None]
        if dropped:
            yield issue("unparsable_lot", "instrument_parcel", rows=len(dropped))
        yield from self._parties(cfg, ctx, uid, spec, rel["parties"])
        yield from self._references(ctx, uid, spec, rel["references"], parcel_uids, issue)

    def _parties(
        self,
        cfg: AcrisConfig,
        ctx: RecordContext,
        uid: str,
        spec: AcrisCode,
        rows: list[dict[str, Any]],
    ) -> Iterator[NormalizedRow]:
        by_role: dict[str, set[tuple[str, str, str, str, str, str]]] = defaultdict(set)
        for r in rows:
            name = _text(r.get("name"))
            if name is None:
                continue
            n = _int(r.get("party_type"))
            label = spec.parties[n - 1] if n is not None and 1 <= n <= len(spec.parties) else ""
            role = cfg.label_roles.get(label, "other")
            contact = tuple(_text(r.get(k)) or "" for k in ("address_1", "address_2", "city",
                                                              "state", "zip"))  # fmt: skip
            by_role[role].add((name, *contact))  # type: ignore[arg-type]
        for role in sorted(by_role):
            # Server row order is not stable across refreshes: order parties by content.
            for seq, (name, a1, a2, city, state, zipc) in enumerate(sorted(by_role[role]), 1):
                street = " ".join(p for p in (a1, a2) if p) or None
                zip5 = zipc[:5] if len(zipc) >= 5 and zipc[:5].isdigit() else None
                addr = normalized_address(street, city or None, state or None, zip5)
                if addr is not None:
                    yield NormalizedRow("address", addr)
                nc = classify(name)
                party_id = stable_id(ctx.fetched.source_id, ctx.record_key, role, str(seq),
                                     clean(name))  # fmt: skip
                yield ctx.fact(
                    "party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
                    org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                    address_id=None if addr is None else addr["address_id"],
                )  # fmt: skip
                yield ctx.fact(
                    "instrument_party", instrument_uid=uid, party_id=party_id, role=role,
                    seq=seq,
                )  # fmt: skip

    def _references(
        self,
        ctx: RecordContext,
        uid: str,
        spec: AcrisCode,
        rows: list[dict[str, Any]],
        parcel_uids: list[str],
        issue: Any,
    ) -> Iterator[NormalizedRow]:
        """References that name the earlier document_id become instrument_ref rows. Ones that
        cite only a CRFN or a reel/page are kept as an `unresolved_reference` data_issue, for a
        later linking step that joins them to instrument.instrument_number / book / page."""
        if spec.ref_type is None:
            return
        field = self.family.ref_doc_field
        targets = sorted({str(r[field]).strip() for r in rows if _text(r.get(field))})
        crfns, reels = set(), set()
        for r in rows:
            if _text(r.get(field)):
                continue
            crfn = _text(r.get("reference_by_crfn_") or r.get("crfn"))
            reel = tuple(_int(r.get(f"reference_by_reel_{k}")) or 0
                         for k in ("year", "borough", "nbr", "page"))  # fmt: skip
            if crfn:
                crfns.add(crfn)
            elif any(reel):
                reels.add(reel)
        if crfns or reels:
            yield issue(
                "unresolved_reference", "instrument_ref", ref_type=spec.ref_type,
                crfns=sorted(crfns),
                reels=[dict(zip(("year", "borough", "reel", "page"), r, strict=True))
                       for r in sorted(reels)],
            )  # fmt: skip
        for target in targets:
            to_uid = instrument_uid(target)
            if to_uid == uid:
                continue
            scope = None
            if spec.ref_type == "partial_release":
                if len(parcel_uids) != 1:
                    yield issue("partial_release_scope_ambiguous", "instrument_ref",
                                target=target, parcels=len(parcel_uids))  # fmt: skip
                    continue
                scope = parcel_uids[0]
            yield ctx.fact(
                "instrument_ref", from_uid=uid, to_uid=to_uid, ref_type=spec.ref_type,
                scope_parcel_uid=scope, method="index_xref",
            )  # fmt: skip

    def health(self) -> HealthReport:
        q = SocrataQuery(PORTAL, self.family.master, "document_id >= '2025'", ("document_id",), 1)
        resp = self.client.get(q.url, q.params(0))
        try:
            rows = json.loads(resp.content)
        except ValueError:
            rows = []
        ok = resp.status == 200 and bool(rows) and "doc_type" in rows[0]
        shape = tuple(sorted(rows[0])) if rows else ()
        detail = "ok" if ok else f"status={resp.status} keys={list(shape)}"
        return HealthReport(self.source_id, ok, datetime.now(UTC), detail, shape)


class AcrisRealProperty(AcrisAdapter):
    source_id: ClassVar[str] = "ny.nyc.acris.real"
    family: ClassVar[Family] = REAL
    record_type: ClassVar[str] = "acris_real_document"


class AcrisPersonalProperty(AcrisAdapter):
    """UCC filings and federal liens. Federal tax liens attach to the debtor, not a lot."""

    source_id: ClassVar[str] = "ny.nyc.acris.personal"
    family: ClassVar[Family] = PERSONAL
    record_type: ClassVar[str] = "acris_personal_document"
