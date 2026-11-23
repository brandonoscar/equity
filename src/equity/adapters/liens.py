"""Judgments, warrants and liens published as Socrata datasets, one YAML per source in
config/liens/. Each row becomes a recorded instrument (the lien), its parties (debtor and
creditor, with addresses) and, where the row names a lot or parcel, an instrument_parcel
link, so the matcher treats these exactly like recorder documents. A satisfaction date
becomes a RELEASE instrument that `releases` the lien.

Config keys:
  source_id, state, portal, dataset, where (optional base filter), order_by (default :id)
  api                 socrata (default) | ckan (resource_id) | arcgis (layer_urls: one or
                      more ArcGIS REST layer URLs, one partition each; order_by OBJECTID)
  select              optional field list: fetch only these (keeps free text out)
  date_field          the lien date (docketed / filed); rows without it are skipped
  partition           year (default) or month windows on date_field, from first_year, or
                      none (one request; arcgis layers are always one partition per layer)
                      date_field values may be ISO dates, ArcGIS epoch milliseconds or a
                      bare year (taken as January 1 of that year)
  uid                 field (or list of fields joined with '-') unique within the dataset
  doc_type            instrument doc_type (JUDGMENT_LIEN, TAX_LIEN_STATE, ...), or
                      {field, map: {VALUE: DOC_TYPE}, default} to map a row's value
  doc_type_raw        constant label, or {field: name}
  amount              field holding the amount owed (principal_amount)
  released_on         optional field: satisfaction date -> RELEASE + instrument_ref
  parties             list of {role, name: field|[fields] | const: text,
                               address: {line1: field|[fields], city, state, zip}
                                        or csz: one field holding "CITY ST 12345"}
  parcel              {kind: nyc_bbl, borough, block, lot} | {kind: nyc_bbl10, field}
                      | {kind: pin, field, county_fips, strip: characters removed}
  county_fips         jurisdiction when no parcel names a county (5 digits)
  county_name_field   optional field holding the county name (mapped to FIPS in `state`)
  skip_names          name values that are separators, not parties (e.g. AND/OR)
  extra_pii           more fields pseudonymized in recorded fixtures (e.g. an apartment address)
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

from equity.adapters.arcgis import ArcGISQuery, get_json
from equity.adapters.arcgis import fetch_all as arcgis_fetch_all
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
        return tuple(sorted(out | set(self.data.get("extra_pii") or ())))


def _fields(spec: Any) -> list[str]:
    if spec is None or isinstance(spec, dict):
        return []
    return [spec] if isinstance(spec, str) else [str(s) for s in spec]


def load_lien_config(path: Path) -> LienConfig:
    data = yaml.safe_load(path.read_text())
    api = data.get("api", "socrata")
    need = [k for k in REQUIRED if not (k == "dataset" and api in ("ckan", "arcgis"))
            and not (k == "portal" and api == "arcgis")]  # fmt: skip
    if api == "ckan":
        need.append("resource_id")
    if api == "arcgis":
        need.append("layer_urls")
    if api not in ("socrata", "ckan", "arcgis"):
        raise LienConfigError(f"{path.name}: unknown api {api!r}")
    missing = [k for k in need if k not in data]
    if missing:
        raise LienConfigError(f"{path.name}: missing {missing}")
    if data.get("partition", "year") not in ("year", "month", "none"):
        raise LienConfigError(f"{path.name}: partition must be year, month or none")
    kind = (data.get("parcel") or {}).get("kind")
    if kind not in (None, "nyc_bbl", "nyc_bbl10", "pin"):
        raise LienConfigError(f"{path.name}: unknown parcel kind {kind!r}")
    if not data.get("parcel") and not data.get("county_fips"):
        raise LienConfigError(f"{path.name}: needs parcel or county_fips")
    return LienConfig(data)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    s = " ".join(str(value).split())
    return s or None


def _csz(value: Any) -> tuple[str, str, str] | None:
    """'BATAVIA OH 45103' or 'BATAVIA, OH 45103-1234' -> (city, state, zip5)."""
    m = re.fullmatch(r"(.+?),?\s+([A-Z]{2})\s+([0-9]{5})(?:-?[0-9]{4})?", _text(value) or "")
    return (m.group(1), m.group(2), m.group(3)) if m else None


def _join(row: Mapping[str, Any], spec: Any) -> str | None:
    parts = [_text(row.get(f)) for f in _fields(spec)]
    return " ".join(p for p in parts if p) or None


def _date(value: Any) -> date | None:
    """ISO date text, ArcGIS epoch milliseconds, or a bare year (-> January 1)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        v = int(value)
        if 1800 <= v <= 2200:
            return date(v, 1, 1)
        if v > 10**11:
            try:
                return datetime.fromtimestamp(v / 1000, tz=UTC).date()
            except (OverflowError, OSError, ValueError):
                return None
        return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    if len(s) == 4 and s.isdigit() and 1800 <= int(s) <= 2200:
        return date(int(s), 1, 1)
    if len(s) < 10:
        return None
    if re.fullmatch(r"[0-9]{2}[-/][0-9]{2}[-/][0-9]{4}", s[:10]):  # MM-DD-YYYY, MM/DD/YYYY
        try:
            return date(int(s[6:10]), int(s[:2]), int(s[3:5]))
        except ValueError:
            return None
    try:
        return date.fromisoformat(s[:10])
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
            "base_url": (
                self.config["layer_urls"][0]
                if self.arcgis
                else f"{self.config['portal']}/datastore/{self.config['resource_id']}"
                if self.ckan
                else f"{self.config['portal']}/resource/{self.config['dataset']}.json"
            ),
            "terms_url": t.get("url"),
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t.get("robots_checked_on", t["checked_on"]),
            "cost_model": t["cost_model"],
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        if self.arcgis:
            for i in range(len(self.config["layer_urls"])):
                yield {"layer": str(i)}
            return
        if self.config.get("partition") == "none":
            yield {}
            return
        first = int(self.config.get("first_year", 1990))
        last = datetime.now(UTC).year
        for y in range(first, last + 1):
            if self.config.get("partition", "year") == "month":
                for m in range(1, 13):
                    yield {"from": f"{y}-{m:02d}-01",
                           "to": f"{y + (m == 12)}-{m % 12 + 1:02d}-01"}  # fmt: skip
            else:
                yield {"from": f"{y}-01-01", "to": f"{y + 1}-01-01"}

    @property
    def ckan(self) -> bool:
        return bool(self.config.get("api") == "ckan")

    @property
    def arcgis(self) -> bool:
        return bool(self.config.get("api") == "arcgis")

    def where(self, params: Mapping[str, str]) -> str:
        clauses = [f"({self.config['where']})"] if self.config.get("where") else []
        f = self.config["date_field"]
        t = "" if self.ckan else "T00:00:00"  # CKAN SQL compares plain dates
        if "from" in params:
            clauses.append(f"{f} >= '{params['from']}{t}' AND {f} < '{params['to']}{t}'")
        return " AND ".join(clauses) or "1=1"

    def _ckan_rows(self, where: str, limit: int | None) -> tuple[list[dict[str, Any]], datetime]:
        """CKAN DataStore SQL, paged in _id order (WPRDC and other CKAN portals)."""
        url = f"{self.config['portal']}/api/3/action/datastore_search_sql"
        page = limit or 10_000
        rows: list[dict[str, Any]] = []
        res = self.config["resource_id"]
        while True:
            # resource_id and the date window come from repo config, never from fetched data.
            n = len(rows)
            sql = f'SELECT * FROM "{res}" WHERE {where} ORDER BY _id LIMIT {page} OFFSET {n}'  # noqa: S608
            resp = self.client.get(url, {"sql": sql})
            body = json.loads(resp.content)
            if resp.status != 200 or not body.get("success"):
                raise LienConfigError(f"{self.source_id}: CKAN query failed: {body.get('error')}")
            got = body["result"]["records"]
            rows += got
            if limit or len(got) < page:
                return rows, resp.retrieved_at

    def _arcgis_fetch(self, request: FetchRequest) -> Fetched:
        urls = self.config["layer_urls"]
        index = int(request.params.get("layer", "0"))
        if not 0 <= index < len(urls):
            raise LienConfigError(f"{self.source_id}: no layer {index}")
        limit = request.params.get("limit")
        q = ArcGISQuery(urls[index], self.config.get("where") or "1=1",
                        tuple(self.config.get("select") or ("*",)),
                        tuple(self.config.get("order_by", ["OBJECTID"])),
                        int(limit) if limit else 1000)  # fmt: skip
        feats, resp = arcgis_fetch_all(self.client, q, max_pages=1 if limit else 10_000,
                                       sample=bool(limit))  # fmt: skip
        body = canonical_json({"layer": urls[index], "rows": [f["attributes"] for f in feats]})
        return Fetched(self.source_id, f"{urls[index]}/query", resp[-1].retrieved_at, 200, body,
                       "application/json")  # fmt: skip

    def fetch(self, request: FetchRequest) -> Fetched:
        if self.arcgis:
            return self._arcgis_fetch(request)
        limit = request.params.get("limit")
        where = self.where(request.params)
        if self.ckan:
            rows_c, at_c = self._ckan_rows(where, int(limit) if limit else None)
            res = self.config["resource_id"]
            body_c = canonical_json({"resource": res, "where": where, "rows": rows_c})
            return Fetched(self.source_id, f"{self.config['portal']}/datastore/{res}?where={where}",
                           at_c, 200, body_c, "application/json")  # fmt: skip
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

    def _doc_type(self, row: Mapping[str, Any]) -> str:
        """A constant, or {field, map, default}: the row's value looked up in map."""
        spec = self.config["doc_type"]
        if isinstance(spec, str):
            return spec
        value = str(row.get(spec["field"]) or "").strip().upper()
        return str(spec["map"].get(value, spec["default"]))

    def _parcel(self, row: Mapping[str, Any]) -> tuple[str | None, str | None]:
        """(parcel_uid, county fips) for the row's lot, or (None, None)."""
        spec = self.config.get("parcel") or {}
        if spec.get("kind") == "nyc_bbl":
            b = nyc_bbl(row.get(spec["borough"]), row.get(spec["block"]), row.get(spec["lot"]))
            if b is None:
                return None, None
            county, swis = BOROUGHS[b[0]]
            return f"{county}-{swis}{b}", county
        if spec.get("kind") == "nyc_bbl10":
            raw = str(row.get(spec["field"]) or "").strip().split(".")[0]
            b = nyc_bbl(raw[:1], raw[1:6], raw[6:]) if len(raw) == 10 and raw.isdigit() else None
            if b is None:
                return None, None
            county, swis = BOROUGHS[b[0]]
            return f"{county}-{swis}{b}", county
        if spec.get("kind") == "pin":
            pin = _text(row.get(spec["field"]))
            for ch in spec.get("strip") or "":
                pin = pin.replace(ch, "") if pin else pin
            if not pin:
                return None, None
            return f"{spec['county_fips']}-{norm_parcel_id(pin)}", spec["county_fips"]
        return None, None

    def _county(self, row: Mapping[str, Any]) -> str:
        spec = self.config.get("parcel") or {}
        if spec.get("kind") == "nyc_bbl":
            hit = BOROUGHS.get(str(row.get(spec["borough"]) or "").strip().upper())
            if hit:
                return hit[0]
        if spec.get("kind") == "nyc_bbl10":
            hit = BOROUGHS.get(str(row.get(spec["field"]) or "")[:1])
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

    def _uid(self, row: Mapping[str, Any]) -> str | None:
        spec = self.config["uid"]
        if isinstance(spec, list):
            parts = [_text(row.get(f)) for f in spec]
            return None if not any(parts) else "-".join(p or "" for p in parts)
        return _join(row, spec)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        """Rows sharing a uid are one lien: status versions (NY warrants), one row per debtor
        (CT), or one per docket entry or lot (foreclosures, evictions). They are merged: all
        parties and lots, the first amount and doc type in content order, any release date."""
        cfg = self.config
        groups: dict[str, list[Mapping[str, Any]]] = {}
        for row in json.loads(fetched.content).get("rows") or []:
            uid_raw = self._uid(row)
            if uid_raw and _date(row.get(cfg["date_field"])) is not None:
                groups.setdefault(uid_raw, []).append(row)  # no key or no date: skipped
        for uid_raw in sorted(groups):
            rows = sorted(groups[uid_raw], key=canonical_json)
            first = rows[0]
            recorded = min(d for d in (_date(r.get(cfg["date_field"])) for r in rows) if d)
            lots = sorted({lot for lot in (self._parcel(r) for r in rows) if lot[0]})
            county = lots[0][1] if lots else None
            ctx = RecordContext(fetched, county or self._county(first), uid_raw, "lien",
                                rows[0] if len(rows) == 1 else {"rows": rows})  # fmt: skip
            uid = stable_id(self.source_id, "lien", uid_raw)
            raw_type = cfg["doc_type_raw"]
            doc_raw = (_text(first.get(raw_type["field"])) if isinstance(raw_type, dict)
                       else str(raw_type)) or self._doc_type(first)  # fmt: skip
            flag = cfg.get("satisfied_flag")
            if flag and any(str(r.get(flag)).strip().lower() in ("true", "1", "yes", "y")
                            for r in rows):  # fmt: skip
                doc_raw += " (satisfied)"  # no satisfaction date is published: marked only
            amounts = [a for a in (_amount(r.get(cfg["amount"])) for r in rows) if a is not None] \
                if cfg.get("amount") else []  # fmt: skip
            amount = amounts[0] if amounts else None
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=uid_raw, book_type=None,
                book=None, page=None, doc_type_raw=doc_raw, doc_type=self._doc_type(first),
                recorded_on=recorded, recorded_seq=None, executed_on=None, consideration=None,
                principal_amount=amount, max_secured_amount=None, maturity_date=None,
                amount_source="index" if amount is not None else None, legal_desc_raw=None,
            )  # fmt: skip
            for parcel_uid, _county in lots:
                yield ctx.fact("instrument_parcel", instrument_uid=uid, parcel_uid=parcel_uid,
                               method="index_parcel_id",
                               evidence={"source_fields": cfg["parcel"]})  # fmt: skip
            yield from self._parties(ctx, uid, rows)
            rel_field = cfg.get("released_on")
            rel_dates = [d for d in (_date(r.get(rel_field)) for r in rows)
                         if d is not None and d >= recorded] if rel_field else []  # fmt: skip
            if rel_dates:
                rel_uid = stable_id(self.source_id, "release", uid_raw)
                yield ctx.fact(
                    "instrument", instrument_uid=rel_uid, instrument_number=f"{uid_raw}-SAT",
                    book_type=None, book=None, page=None, doc_type_raw=f"{doc_raw} satisfied",
                    doc_type="RELEASE", recorded_on=min(rel_dates), recorded_seq=None,
                    executed_on=None, consideration=None, principal_amount=None,
                    max_secured_amount=None, maturity_date=None, amount_source=None,
                    legal_desc_raw=None,
                )  # fmt: skip
                yield ctx.fact("instrument_ref", from_uid=rel_uid, to_uid=uid,
                               ref_type="releases", scope_parcel_uid=None,
                               method="index_xref")  # fmt: skip

    def _parties(
        self, ctx: RecordContext, uid: str, rows: list[Mapping[str, Any]]
    ) -> Iterator[NormalizedRow]:
        skip = {s.upper() for s in self.config.get("skip_names", [])}
        found: dict[str, dict[str, dict[str, Any] | None]] = {}
        for row in rows:
            for p in self.config["parties"]:
                name = _text(p["const"]) if "const" in p else _join(row, p.get("name"))
                if not name or name.upper() in skip:
                    continue
                a = p.get("address") or {}
                csz = _csz(row.get(a["csz"])) if a.get("csz") else None
                if csz is not None:
                    a = {**a, "state_const": csz[1]}
                zipc = csz[2] if csz else _text(row.get(a["zip"])) if a.get("zip") else None
                zip5 = zipc[:5] if zipc and re.fullmatch(r"[0-9]{5}", zipc[:5]) else None
                state = (_text(row.get(a["state"])) if a.get("state") and a["state"] in row
                         else _text(a.get("state_const")))  # fmt: skip
                city = csz[0] if csz else _text(row.get(a["city"])) if a.get("city") else None
                addr = normalized_address(_join(row, a.get("line1")), city,
                                          state, zip5) if a else None  # fmt: skip
                by_name = found.setdefault(p["role"], {})
                if name not in by_name or (by_name[name] is None and addr is not None):
                    by_name[name] = addr
        for role in sorted(found):
            for seq, name in enumerate(sorted(found[role]), start=1):
                addr = found[role][name]
                if addr is not None:
                    yield NormalizedRow("address", addr)
                nc = classify(name)
                party_id = stable_id(self.source_id, ctx.record_key, role, str(seq), clean(name))
                yield ctx.fact("party", party_id=party_id, raw_name=name,
                               party_kind=nc.party_kind, org_form=nc.org_form,
                               org_name_norm=nc.org_name_norm,
                               address_id=None if addr is None else addr["address_id"])  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=party_id,
                               role=role, seq=seq)  # fmt: skip

    def health(self) -> HealthReport:
        if self.arcgis:
            body = get_json(self.client, self.config["layer_urls"][0] + "/query",
                            {"where": self.config.get("where") or "1=1",
                             "returnCountOnly": "true", "f": "json"})  # fmt: skip
            n = int(body.get("count") or 0)
            return HealthReport(self.source_id, n > 0, datetime.now(UTC), f"{n} rows")
        if self.ckan:
            rows_h, _ = self._ckan_rows("1=1", 1)
            return HealthReport(self.source_id, bool(rows_h), datetime.now(UTC),
                                "ok" if rows_h else "no rows")  # fmt: skip
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
