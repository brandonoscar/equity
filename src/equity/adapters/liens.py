"""Judgments, warrants and liens published as open datasets (Socrata, CKAN, ArcGIS layers or a
plain .xlsx download), one YAML per source in config/liens/. Each row becomes a recorded
instrument (the lien), its parties (debtor and creditor, with addresses) and, where the row
names a lot or parcel, an instrument_parcel link, so the matcher treats these exactly like
recorder documents. A satisfaction date
becomes a RELEASE instrument that `releases` the lien.

Config keys:
  source_id, state, portal, dataset, where (optional base filter), order_by (default :id)
  api                 socrata (default), ckan (+ resource_id), arcgis (+ layer_url, no portal or
                      dataset) or xlsx (+ url: one workbook, read whole; sheet = 0-based index)
  excel_dates         xlsx: fields holding Excel serial day numbers, turned into ISO dates
  address_split       xlsx: {field, prefix}: "line1, city, ST 12345" into <prefix>line1/city/
                      state/zip (the whole text stays line1 when it does not split that way)
  select              optional field list: fetch only these (keeps free text out)
  date_field          the lien date (docketed / filed); rows without it are skipped
  partition           year (default) or month windows on date_field, from first_year
  uid                 field (or list of fields joined with '-') unique within the dataset
  doc_type            instrument doc_type (JUDGMENT_LIEN, TAX_LIEN_STATE, ...), or
                      {field, map: {VALUE: DOC_TYPE}, default} to map a row's value
  doc_type_raw        constant label, or {field: name}
  amount              field holding the amount owed (principal_amount), or a list summed
  released_on         optional field: satisfaction date -> RELEASE + instrument_ref
  satisfied_flag      optional field: a value in satisfied_values (default true/1/yes/y) marks
                      the lien satisfied when no satisfaction date is published
  parties             list of {role, name: field|[fields] | const: text,
                               address: {line1: field|[fields], city, state, zip}}
  parcel              {kind: nyc_bbl, borough, block, lot} | {kind: nyc_bbl10, field}
                      | {kind: pin, field, county_fips}
  county_fips         jurisdiction when no parcel names a county (5 digits)
  county_name_field   optional field holding the county name (mapped to FIPS in `state`)
  skip_names          name values that are separators, not parties (e.g. AND/OR)
  extra_pii           more fields pseudonymized in recorded fixtures (e.g. an apartment address)
  terms               {url, summary, checked_on, cost_model}
"""

from __future__ import annotations

import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path
from typing import Any, ClassVar

import yaml

from equity.adapters.arcgis import ArcGISQuery
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
REQUIRED = ("source_id", "state", "date_field", "uid", "doc_type", "doc_type_raw", "parties",
            "terms")  # fmt: skip
API_KEYS = {"socrata": ("portal", "dataset"), "ckan": ("portal", "resource_id"),
            "arcgis": ("layer_url",), "xlsx": ("url",)}  # fmt: skip
SATISFIED = ("true", "1", "yes", "y")
XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
EXCEL_EPOCH = date(1899, 12, 30)
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
    if api not in API_KEYS:
        raise LienConfigError(f"{path.name}: unknown api {api!r}")
    need = [*REQUIRED, *API_KEYS[api]]
    missing = [k for k in need if k not in data]
    if missing:
        raise LienConfigError(f"{path.name}: missing {missing}")
    if data.get("partition", "year") not in ("year", "month"):
        raise LienConfigError(f"{path.name}: partition must be year or month")
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


def _header(text: str) -> str:
    """A spreadsheet column title as a config field name: 'Date Posted on the WALL' ->
    'date_posted_on_the_wall'."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _xml(part: bytes) -> ET.Element:
    """Parse one workbook part. Workbooks never declare a DTD, so one that does is refused
    (no entity expansion from a downloaded file)."""
    if b"<!DOCTYPE" in part or b"<!ENTITY" in part:
        raise LienConfigError("workbook part declares a DTD; refused")
    return ET.fromstring(part)  # noqa: S314 - DTDs refused above; repo-configured gov host


def xlsx_rows(content: bytes, sheet: int = 0) -> list[dict[str, str]]:
    """Rows of one worksheet as {column field name: cell text}; the first row is the header.
    Read with the standard library: the workbook is a zip of XML parts."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in _xml(z.read("xl/sharedStrings.xml")).iter(f"{XLSX_NS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{XLSX_NS}t")))
        sheet_xml = _xml(z.read(f"xl/worksheets/sheet{sheet + 1}.xml"))
    table: list[list[str]] = []
    for row in sheet_xml.iter(f"{XLSX_NS}row"):
        cells: dict[int, str] = {}
        for c in row.iter(f"{XLSX_NS}c"):
            ref = re.match(r"[A-Z]+", c.get("r", ""))
            col = 0
            for ch in ref.group(0) if ref else "":
                col = col * 26 + ord(ch) - 64
            v = c.find(f"{XLSX_NS}v")
            if c.get("t") == "s" and v is not None and v.text:
                text = shared[int(v.text)]
            elif c.get("t") == "inlineStr":
                text = "".join(t.text or "" for t in c.iter(f"{XLSX_NS}t"))
            else:
                text = v.text or "" if v is not None else ""
            cells[col - 1 if col else len(cells)] = text
        table.append([cells.get(i, "") for i in range(max(cells, default=-1) + 1)])
    if not table:
        return []
    head = [_header(h) for h in table[0]]
    out = []
    for r in table[1:]:
        rec = {h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(head) if h}
        if any(rec.values()):
            out.append(rec)
    return out


def excel_date(value: Any) -> str | None:
    """An Excel serial day number (45478) as an ISO date; other text unchanged or None."""
    try:
        n = float(str(value))
    except ValueError:
        return _text(value)
    if not 1 <= n < 2_958_466:  # 1900-01-01 .. 9999-12-31
        return None
    return (EXCEL_EPOCH + timedelta(days=int(n))).isoformat()


ADDRESS_TAIL = re.compile(r"^(?P<state>[A-Z]{2})\.?\s+(?P<zip>[0-9]{5})(?:-[0-9]{4})?$")


def split_address(text: str | None) -> dict[str, str | None]:
    """'259 Drum Point Road, Brick, NJ 08723' -> line1, city, state, zip. Anything else keeps
    the whole text as line1 rather than guessing the parts."""
    full = _text(text)
    parts = [p.strip() for p in (full or "").split(",") if p.strip()]
    tail = ADDRESS_TAIL.match(parts[-1].upper()) if len(parts) >= 3 else None
    if tail is None:
        return {"line1": full, "city": None, "state": None, "zip": None}
    return {"line1": ", ".join(parts[:-2]), "city": parts[-2], "state": tail["state"],
            "zip": tail["zip"]}  # fmt: skip


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
            "access_method": {"arcgis": "arcgis", "xlsx": "bulk"}.get(self.api, "api"),
            "base_url": self.base_url,
            "terms_url": t.get("url"),
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t.get("robots_checked_on", t["checked_on"]),
            "cost_model": t["cost_model"],
        }

    @property
    def api(self) -> str:
        return str(self.config.get("api", "socrata"))

    @property
    def base_url(self) -> str:
        if self.api == "ckan":
            return f"{self.config['portal']}/datastore/{self.config['resource_id']}"
        if self.api == "arcgis":
            return str(self.config["layer_url"])
        if self.api == "xlsx":
            return str(self.config["url"])
        return f"{self.config['portal']}/resource/{self.config['dataset']}.json"

    def partitions(self) -> Iterator[dict[str, str]]:
        if self.api == "xlsx":
            yield {"file": "all"}  # one workbook, replaced in full each month
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
        return self.api == "ckan"

    def where(self, params: Mapping[str, str]) -> str:
        clauses = [f"({self.config['where']})"] if self.config.get("where") else []
        f = self.config["date_field"]
        if "from" in params and self.api == "arcgis":
            clauses.append(f"{f} >= DATE '{params['from']}' AND {f} < DATE '{params['to']}'")
        elif "from" in params:
            t = "" if self.ckan else "T00:00:00"  # CKAN SQL compares plain dates
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

    def _arcgis_query(self, where: str, page: int) -> ArcGISQuery:
        return ArcGISQuery(str(self.config["layer_url"]), where,
                           tuple(self.config.get("select") or ("*",)),
                           tuple(self.config.get("order_by") or ("OBJECTID",)),
                           page)  # fmt: skip

    def _xlsx_rows(self, content: bytes) -> list[dict[str, Any]]:
        """Workbook rows with Excel dates as ISO text and split addresses, so normalize reads
        them like any other source."""
        rows: list[dict[str, Any]] = []
        split = self.config.get("address_split")
        for row in xlsx_rows(content, int(self.config.get("sheet", 0))):
            out: dict[str, Any] = dict(row)
            for f in self.config.get("excel_dates") or ():
                out[f] = excel_date(row.get(f))
            if split:
                for k, v in split_address(row.get(split["field"])).items():
                    out[f"{split['prefix']}{k}"] = v
            rows.append(out)
        return rows

    def fetch(self, request: FetchRequest) -> Fetched:
        limit = request.params.get("limit")
        where = self.where(request.params)
        if self.api == "xlsx":
            resp = self.client.get(str(self.config["url"]))
            if resp.status != 200:
                raise LienConfigError(f"{self.source_id}: HTTP {resp.status} from {resp.url}")
            rows_x = self._xlsx_rows(resp.content)
            rows_x = rows_x[: int(limit)] if limit else rows_x
            body_x = canonical_json({"url": self.config["url"], "rows": rows_x})
            return Fetched(self.source_id, str(self.config["url"]), resp.retrieved_at, 200,
                           body_x, "application/json")  # fmt: skip
        if self.api == "arcgis":
            q_a = self._arcgis_query(where, int(limit) if limit else 1000)
            feats, resps = arcgis_fetch_all(self.client, q_a, max_pages=1 if limit else 10_000,
                                            sample=bool(limit))  # fmt: skip
            rows_a = [f.get("attributes") or {} for f in feats]
            body_a = canonical_json({"layer": q_a.layer_url, "where": where, "rows": rows_a})
            at_a = resps[-1].retrieved_at if resps else datetime.now(UTC)
            return Fetched(self.source_id, f"{q_a.layer_url}/query?where={where}", at_a, 200,
                           body_a, "application/json")  # fmt: skip
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
            if pin is None:
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
            done = tuple(v.lower() for v in cfg.get("satisfied_values") or SATISFIED)
            if flag and any(str(r.get(flag)).strip().lower() in done for r in rows):
                doc_raw += " (satisfied)"  # no satisfaction date is published: marked only
            amounts = [a for a in (self._row_amount(r) for r in rows) if a is not None]
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

    def _row_amount(self, row: Mapping[str, Any]) -> Decimal | None:
        """The row's amount field, or the sum of a list of fields (None if all are blank)."""
        found = [a for a in (_amount(row.get(f)) for f in _fields(self.config.get("amount")))
                 if a is not None]  # fmt: skip
        return sum(found, Decimal(0)).quantize(Decimal("0.01")) if found else None

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
                zipc = _text(row.get(a["zip"])) if a.get("zip") else None
                zip5 = zipc[:5] if zipc and re.fullmatch(r"[0-9]{5}", zipc[:5]) else None
                state = (_text(row.get(a["state"])) if a.get("state") and a["state"] in row
                         else _text(a.get("state_const")))  # fmt: skip
                addr = normalized_address(_join(row, a.get("line1")),
                                          _text(row.get(a["city"])) if a.get("city") else None,
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
        if self.api in ("xlsx", "arcgis"):
            rows_f = json.loads(self.fetch(FetchRequest({"limit": "1"})).content)["rows"]
            return HealthReport(self.source_id, bool(rows_f), datetime.now(UTC),
                                "ok" if rows_f else "no rows")  # fmt: skip
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
