"""Judgments, warrants and liens published as Socrata datasets, one YAML per source in
config/liens/. Each row becomes a recorded instrument (the lien), its parties (debtor and
creditor, with addresses) and, where the row names a lot or parcel, an instrument_parcel
link, so the matcher treats these exactly like recorder documents. A satisfaction date
becomes a RELEASE instrument that `releases` the lien.

Config keys:
  source_id, state, portal, dataset, where (optional base filter), order_by (default :id)
  select              optional field list: fetch only these (keeps free text out)
  date_field          the lien date (docketed / filed); rows without it are skipped
  partition           year (default) or month windows on date_field, from first_year
  uid                 field (or list of fields joined with '-') unique within the dataset
  doc_type            instrument doc_type (JUDGMENT_LIEN, TAX_LIEN_STATE, ...)
  doc_type_raw        constant label, or {field: name}
  amount              field holding the amount owed (principal_amount)
  released_on         optional field: satisfaction date -> RELEASE + instrument_ref
  parties             list of {role, name: field|[fields] | const: text,
                               address: {line1: field|[fields], city, state, zip}}
  parcel              {kind: nyc_bbl, borough, block, lot} | {kind: pin, field, county_fips}
  county_fips         jurisdiction when no parcel names a county (5 digits)
  county_name_field   optional field holding the county name (mapped to FIPS in `state`)
  skip_names          name values that are separators, not parties (e.g. AND/OR)
  terms               {url, summary, checked_on, cost_model}
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path
from typing import Any, ClassVar

import yaml

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataQuery, fetch_all
from equity.adapters.state_parcels import norm_parcel_id, normalized_address
from equity.config import CONFIG_DIR
from equity.geo import counties, norm_county_name
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

LIENS_DIR = CONFIG_DIR / "liens"
REQUIRED = ("source_id", "state", "portal", "dataset", "date_field", "uid", "doc_type",
            "doc_type_raw", "parties", "terms")  # fmt: skip
# NYC borough name or digit -> (county FIPS, NYS SWIS prefix), as in the ACRIS config.
BOROUGHS = {
    "1": ("36061", "620100"), "MANHATTAN": ("36061", "620100"),
    "2": ("36005", "600100"), "BRONX": ("36005", "600100"),
    "3": ("36047", "610100"), "BROOKLYN": ("36047", "610100"),
    "4": ("36081", "630100"), "QUEENS": ("36081", "630100"),
    "5": ("36085", "640100"), "STATEN ISLAND": ("36085", "640100"),
}  # fmt: skip
BOROUGH_DIGIT = {"MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3", "QUEENS": "4",
                 "STATEN ISLAND": "5"}  # fmt: skip


class LienConfigError(ValueError):
    pass


@dataclass(frozen=True)
class LienConfig:
    data: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    @property
    def pii_fields(self) -> tuple[str, ...]:
        out: set[str] = set()
        for p in self.data["parties"]:
            if p.get("person_names", True):
                out |= set(_fields(p.get("name")))
            out |= set(_fields((p.get("address") or {}).get("line1")))
        return tuple(sorted(out))


def _fields(spec: Any) -> list[str]:
    if spec is None or isinstance(spec, dict):
        return []
    return [spec] if isinstance(spec, str) else [str(s) for s in spec]


def load_lien_config(path: Path) -> LienConfig:
    data = yaml.safe_load(path.read_text())
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise LienConfigError(f"{path.name}: missing {missing}")
    if data.get("partition", "year") not in ("year", "month"):
        raise LienConfigError(f"{path.name}: partition must be year or month")
    kind = (data.get("parcel") or {}).get("kind")
    if kind not in (None, "nyc_bbl", "pin"):
        raise LienConfigError(f"{path.name}: unknown parcel kind {kind!r}")
    if not data.get("parcel") and not data.get("county_fips"):
        raise LienConfigError(f"{path.name}: needs parcel or county_fips")
    return LienConfig(data)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    s = " ".join(str(value).split())
    return s or None


def _join(row: Mapping[str, Any], spec: Any) -> str | None:
    parts = [_text(row.get(f)) for f in _fields(spec)]
    return " ".join(p for p in parts if p) or None


def _date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _amount(value: Any) -> Decimal | None:
    try:
        d = Decimal(str(value).replace(",", "").replace("$", ""))
    except (InvalidOperation, ValueError):
        return None
    return d if d >= 0 else None


@cache
def _county_by_name(state: str) -> dict[str, str]:
    return {norm_county_name(c.name): c.fips5 for c in counties() if c.state == state}


def nyc_bbl(borough: Any, block: Any, lot: Any) -> str | None:
    b = BOROUGH_DIGIT.get(str(borough or "").strip().upper(), str(borough or "").strip())
    try:
        blk, lt = int(str(block)), int(str(lot))
    except ValueError:
        return None
    if b not in "12345" or len(b) != 1 or not (0 < blk <= 99999 and 0 < lt <= 9999):
        return None
    return f"{b}{blk:05d}{lt:04d}"


class LienAdapter(Adapter):
    config: ClassVar[LienConfig]
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    page_size: ClassVar[int] = 50_000
    pii_fields: ClassVar[tuple[str, ...]] = ()  # set per source from its config

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0)

    def source_row(self) -> Mapping[str, Any]:
        t = self.config["terms"]
        return {
            "source_id": self.source_id,
            "kind": "recorder",
            "jurisdiction": self.config.get("county_fips") or self.config["state"],
            "access_method": "api",
            "base_url": f"{self.config['portal']}/resource/{self.config['dataset']}.json",
            "terms_url": t.get("url"),
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t.get("robots_checked_on", t["checked_on"]),
            "cost_model": t["cost_model"],
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        first = int(self.config.get("first_year", 1990))
        last = datetime.now(UTC).year
        for y in range(first, last + 1):
            if self.config.get("partition", "year") == "month":
                for m in range(1, 13):
                    yield {"from": f"{y}-{m:02d}-01",
                           "to": f"{y + (m == 12)}-{m % 12 + 1:02d}-01"}  # fmt: skip
            else:
                yield {"from": f"{y}-01-01", "to": f"{y + 1}-01-01"}

    def where(self, params: Mapping[str, str]) -> str:
        clauses = [f"({self.config['where']})"] if self.config.get("where") else []
        f = self.config["date_field"]
        if "from" in params:
            clauses.append(
                f"{f} >= '{params['from']}T00:00:00' AND {f} < '{params['to']}T00:00:00'"
            )
        return " AND ".join(clauses) or "1=1"

    def fetch(self, request: FetchRequest) -> Fetched:
        limit = request.params.get("limit")
        where = self.where(request.params)
        q = SocrataQuery(self.config["portal"], self.config["dataset"], where,
                         tuple(self.config.get("order_by", [":id"])),
                         int(limit) if limit else self.page_size,
                         tuple(self.config.get("select") or ()))  # fmt: skip
        rows, responses = fetch_all(self.client, q, max_pages=1 if limit else 10_000,
                                    sample=bool(limit))  # fmt: skip
        body = canonical_json({"dataset": self.config["dataset"], "where": where, "rows": rows})
        at = responses[-1].retrieved_at if responses else datetime.now(UTC)
        return Fetched(self.source_id, f"{q.url}?$where={where}", at, 200, body,
                       "application/json")  # fmt: skip

    def _parcel(self, row: Mapping[str, Any]) -> tuple[str | None, str | None]:
        """(parcel_uid, county fips) for the row's lot, or (None, None)."""
        spec = self.config.get("parcel") or {}
        if spec.get("kind") == "nyc_bbl":
            b = nyc_bbl(row.get(spec["borough"]), row.get(spec["block"]), row.get(spec["lot"]))
            if b is None:
                return None, None
            county, swis = BOROUGHS[b[0]]
            return f"{county}-{swis}{b}", county
        if spec.get("kind") == "pin":
            raw = _text(row.get(spec["field"]))
            if raw is None:
                return None, None
            return f"{spec['county_fips']}-{norm_parcel_id(raw)}", spec["county_fips"]
        return None, None

    def _county(self, row: Mapping[str, Any]) -> str:
        spec = self.config.get("parcel") or {}
        if spec.get("kind") == "nyc_bbl":
            hit = BOROUGHS.get(str(row.get(spec["borough"]) or "").strip().upper())
            if hit:
                return hit[0]
        field = self.config.get("county_name_field")
        if field:
            fips = _county_by_name(self.config["state"]).get(
                norm_county_name(str(row.get(field) or ""))
            )
            if fips:
                return fips
        return str(self.config.get("county_fips") or self.config["state"])

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = self.config
        for row in json.loads(fetched.content).get("rows") or []:
            uid_raw = _join(row, cfg["uid"]) if not isinstance(cfg["uid"], list) else "-".join(
                _text(row.get(f)) or "" for f in cfg["uid"])  # fmt: skip
            recorded = _date(row.get(cfg["date_field"]))
            if not uid_raw or recorded is None:
                continue  # no stable key or no lien date: skip rather than guess
            parcel_uid, county = self._parcel(row)
            ctx = RecordContext(fetched, county or self._county(row), uid_raw, "lien", dict(row))
            uid = stable_id(self.source_id, "lien", uid_raw)
            raw_type = cfg["doc_type_raw"]
            doc_raw = (_text(row.get(raw_type["field"])) if isinstance(raw_type, dict)
                       else str(raw_type)) or cfg["doc_type"]  # fmt: skip
            amount = _amount(row.get(cfg["amount"])) if cfg.get("amount") else None
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=uid_raw, book_type=None,
                book=None, page=None, doc_type_raw=doc_raw, doc_type=cfg["doc_type"],
                recorded_on=recorded, recorded_seq=None, executed_on=None, consideration=None,
                principal_amount=amount, max_secured_amount=None, maturity_date=None,
                amount_source="index" if amount is not None else None, legal_desc_raw=None,
            )  # fmt: skip
            if parcel_uid is not None:
                yield ctx.fact("instrument_parcel", instrument_uid=uid, parcel_uid=parcel_uid,
                               method="index_parcel_id",
                               evidence={"source_fields": cfg["parcel"]})  # fmt: skip
            yield from self._parties(ctx, uid, row)
            released = _date(row.get(cfg["released_on"])) if cfg.get("released_on") else None
            if released is not None and released >= recorded:
                rel_uid = stable_id(self.source_id, "release", uid_raw)
                yield ctx.fact(
                    "instrument", instrument_uid=rel_uid, instrument_number=f"{uid_raw}-SAT",
                    book_type=None, book=None, page=None, doc_type_raw=f"{doc_raw} satisfied",
                    doc_type="RELEASE", recorded_on=released, recorded_seq=None,
                    executed_on=None, consideration=None, principal_amount=None,
                    max_secured_amount=None, maturity_date=None, amount_source=None,
                    legal_desc_raw=None,
                )  # fmt: skip
                yield ctx.fact("instrument_ref", from_uid=rel_uid, to_uid=uid,
                               ref_type="releases", scope_parcel_uid=None,
                               method="index_xref")  # fmt: skip

    def _parties(
        self, ctx: RecordContext, uid: str, row: Mapping[str, Any]
    ) -> Iterator[NormalizedRow]:
        seqs: dict[str, int] = {}
        skip = {s.upper() for s in self.config.get("skip_names", [])}
        for p in self.config["parties"]:
            name = _text(p["const"]) if "const" in p else _join(row, p.get("name"))
            if not name or name.upper() in skip:
                continue
            role = p["role"]
            seqs[role] = seqs.get(role, 0) + 1
            a = p.get("address") or {}
            zipc = _text(row.get(a["zip"])) if a.get("zip") else None
            zip5 = zipc[:5] if zipc and re.fullmatch(r"[0-9]{5}", zipc[:5]) else None
            state = (_text(row.get(a["state"])) if a.get("state") and a["state"] in row
                     else _text(a.get("state_const")))  # fmt: skip
            addr = normalized_address(_join(row, a.get("line1")),
                                      _text(row.get(a["city"])) if a.get("city") else None,
                                      state, zip5) if a else None  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            nc = classify(name)
            party_id = stable_id(self.source_id, ctx.record_key, role, str(seqs[role]), clean(name))
            yield ctx.fact("party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
                           org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                           address_id=None if addr is None else addr["address_id"])  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=party_id,
                           role=role, seq=seqs[role])  # fmt: skip

    def health(self) -> HealthReport:
        q = SocrataQuery(self.config["portal"], self.config["dataset"], self.where({}),
                         tuple(self.config.get("order_by", [":id"])), 1)  # fmt: skip
        rows, _ = fetch_all(self.client, q, max_pages=1, sample=True)
        return HealthReport(self.source_id, bool(rows), datetime.now(UTC),
                            "ok" if rows else "no rows")  # fmt: skip


def lien_adapter_for(cfg: LienConfig) -> type[LienAdapter]:
    sid = cfg["source_id"]
    return type("Liens_" + sid.replace(".", "_"), (LienAdapter,),
                {"config": cfg, "source_id": sid, "pii_fields": cfg.pii_fields,
                 "__module__": __name__})  # fmt: skip


def all_lien_adapters(directory: Path = LIENS_DIR) -> list[type[LienAdapter]]:
    return [lien_adapter_for(load_lien_config(p)) for p in sorted(directory.glob("*.yaml"))]
