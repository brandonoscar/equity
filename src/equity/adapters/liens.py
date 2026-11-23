"""Judgments, warrants and liens published as open datasets (Socrata, CKAN, ArcGIS layers, or
a plain .xlsx, .csv/.txt or HTML-table download), one YAML per source in config/liens/. Each
row becomes a recorded instrument (the lien), its parties (debtor and creditor, with
addresses) and, where the row names a lot or parcel, an instrument_parcel link, so the matcher
treats these exactly like recorder documents. A satisfaction date
becomes a RELEASE instrument that `releases` the lien.

Config keys:
  source_id, state, portal, dataset, where (optional base filter), order_by (default :id)
  api                 socrata (default), ckan (+ resource_id), arcgis (+ layer_url, no portal or
                      dataset) or xlsx (+ url: one workbook, read whole; sheet = 0-based index;
                      header_row = 0-based row holding the column titles, default 0),
                      csv (+ url: one delimited text file; delimiter, default ',') or html
                      (+ url: one page; table = 0-based index of its <table>, default 0) or
                      pdf (+ url, header: a text-based PDF list; the table starts at the line
                      whose first cell begins with `header`, columns split at its x positions)
  caption_field       a 'Plaintiff vs Defendant' caption, split into the derived fields
                      caption_plaintiff and caption_defendant for use in parties
  enrich              arcgis: {carto: SQL API url, table, key, field, columns}: add columns
                      from a Carto table, looked up by the row's field (e.g. owner by case)
  date_is_text        arcgis: date_field is ISO text, so windows compare strings, not DATEs
  excel_dates         xlsx: fields holding Excel serial day numbers, turned into ISO dates
  us_dates            file apis: fields holding M/D/YYYY dates, turned into ISO dates
  year_dates          fields holding a year (levy / tax year), read as Jan 1 of that year
  listed_on           a field name: set to the fetch date on every row (a current list with no
                      per-row date); use it as date_field
  single_partition    true: one fetch of the whole (filtered) dataset, no date windows
  address_split       {field, prefix, form}: form comma (default) splits
                      "line1, city, ST 12345", slash "line1 / CITY ST 12345", city_state_zip
                      "City, ST 12345", city_st_zip "CITY ST 12345" (no street), into
                      <prefix>line1/city/state/zip (the whole text stays line1 when it does
                      not split that way)
  as_of               xlsx/html/pdf: {field, after}: a list with no per-row date. The first
                      date after the text `after` in the title rows above header_row (xlsx) or
                      in the page or document text (html, pdf) is put in `field` on every row
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
  parties             list of {role, name: field|[fields] | const: text, split (optional
                               separator: one field holding several names, e.g. ' | '),
                               address: {line1: field|[fields], city | city_const, state |
                               state_const, zip}}
  parcel              {kind: nyc_bbl, borough, block, lot} | {kind: nyc_bbl10, field}
                      | {kind: pin, field (or a list of fields, one lot each), county_fips}
  county_fips         jurisdiction when no parcel names a county (5 digits)
  county_name_field   optional field holding the county name (mapped to FIPS in `state`)
  county_aliases      optional {name in the data: county name}, e.g. {DADE: MIAMI-DADE}
  skip_names          name values that are separators, not parties (e.g. AND/OR)
  extra_pii           more fields pseudonymized in recorded fixtures (e.g. an apartment address)
  link_from           file apis: {page, pattern}: the file's address changes with each issue
                      (a quarter in its name), so it is the first link on `page` whose href
                      matches the regex `pattern`; `url` is the fallback and the base_url
  user_agent          optional identifying User-Agent for a host whose firewall refuses the
                      default one (it still names this project; robots.txt is still obeyed)
  terms               {url, summary, checked_on, cost_model}
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, ClassVar

import yaml

from equity.adapters.arcgis import ArcGISQuery
from equity.adapters.arcgis import fetch_all as arcgis_fetch_all
from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import USER_AGENT, PoliteClient
from equity.adapters.pdf_table import pdf_table, pdf_text
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
            "arcgis": ("layer_url",), "xlsx": ("url",), "csv": ("url",),
            "html": ("url",), "pdf": ("url", "header")}  # fmt: skip
FILE_APIS = ("xlsx", "csv", "html", "pdf")
ACCESS = {"arcgis": "arcgis", "xlsx": "bulk", "csv": "bulk", "html": "html", "pdf": "bulk"}
MONTHS = {m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"), start=1)}  # fmt: skip
US_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
LONG_DATE = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE)
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
    if isinstance(value, int | float) and not isinstance(value, bool):
        try:  # ArcGIS esriFieldTypeDate: milliseconds since the epoch, UTC
            return datetime.fromtimestamp(value / 1000, UTC).date()
        except (OverflowError, OSError, ValueError):
            return None
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


def xlsx_table(content: bytes, sheet: int = 0) -> list[list[str]]:
    """One worksheet as a list of rows of cell text, read with the standard library: the
    workbook is a zip of XML parts."""
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
    return table


def xlsx_rows(content: bytes, sheet: int = 0, header_row: int = 0) -> list[dict[str, str]]:
    """Rows of one worksheet as {column field name: cell text}; row header_row (0-based) is
    the header and rows above it (a title banner) are dropped."""
    return table_rows(xlsx_table(content, sheet)[header_row:])


def table_rows(table: list[list[str]]) -> list[dict[str, str]]:
    """A header row and data rows as {column field name: cell text}; blank rows dropped."""
    if not table:
        return []
    head = [_header(h) for h in table[0]]
    out = []
    for r in table[1:]:
        rec = {h: (r[i].strip() if i < len(r) else "") for i, h in enumerate(head) if h}
        if any(rec.values()):
            out.append(rec)
    return out


def csv_table(content: bytes, delimiter: str = ",") -> list[list[str]]:
    """A delimited text file as rows of cell text (a UTF-8 byte-order mark is dropped)."""
    text = content.decode("utf-8-sig", errors="replace")
    return [list(r) for r in csv.reader(io.StringIO(text), delimiter=delimiter)]


class _TableParser(HTMLParser):
    """Every <table> on a page as rows of cell text (th and td), plus the page's text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.text: list[str] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self.text.append(data)
        if self._cell is not None:
            self._cell.append(data)


def html_tables(content: bytes) -> tuple[list[list[list[str]]], str]:
    """(tables, page text) of an HTML page, read with the standard library parser."""
    p = _TableParser()
    p.feed(content.decode("utf-8", errors="replace"))
    p.close()
    return p.tables, " ".join(" ".join(p.text).split())


def text_date(text: str | None, after: str = "") -> str | None:
    """The first M/D/YYYY or 'Month D, YYYY' date in text after the marker `after` (case
    ignored), as an ISO date; None when there is none or it is not a real date."""
    s = text or ""
    at = s.lower().find(after.lower()) if after else 0
    if at < 0:
        return None
    s = s[at + len(after) :]
    us, long = US_DATE.search(s), LONG_DATE.search(s)
    try:
        if us and (long is None or us.start() < long.start()):
            return date(int(us[3]), int(us[1]), int(us[2])).isoformat()
        if long:
            return date(int(long[3]), MONTHS[long[1].lower()], int(long[2])).isoformat()
    except ValueError:
        return None
    return None


def us_date(value: Any) -> str | None:
    """'08/20/2025' -> '2025-08-20'; text that is not one such date -> None."""
    s = _text(value) or ""
    return text_date(s) if US_DATE.fullmatch(s) else None


def excel_date(value: Any) -> str | None:
    """An Excel serial day number (45478) as an ISO date; other text unchanged or None."""
    try:
        n = float(str(value))
    except ValueError:
        return _text(value)
    if not 1 <= n < 2_958_466:  # 1900-01-01 .. 9999-12-31
        return None
    return (EXCEL_EPOCH + timedelta(days=int(n))).isoformat()


CAPTION_VS = re.compile(r"\s+vs?\.?\s+", re.IGNORECASE)
ADDRESS_TAIL = re.compile(r"^(?P<state>[A-Z]{2})\.?\s+(?P<zip>[0-9]{5})(?:-[0-9]{4})?$")
CITY_TAIL = re.compile(
    r"^(?P<city>.*?[^\s,])[\s,]+(?P<state>[A-Z]{2})\.?,?\s*(?P<zip>[0-9]{5})(?:-?[0-9]{1,4})?$"
)


CITY_ST_ZIP = re.compile(
    r"^(?P<city>[A-Z .'-]+?)\s+(?P<state>[A-Z]{2})\s+(?P<zip>[0-9]{5})(?:-?[0-9]{4})?$"
)


def split_address(text: str | None, form: str = "comma") -> dict[str, str | None]:
    """'259 Drum Point Road, Brick, NJ 08723' -> line1, city, state, zip. form slash reads
    '2623 NW 74TH PL / GAINESVILLE FL 32653-1251', city_state_zip 'Acton, MA 01720' (no
    street line). A slash address missing its slash ('974 ALLISON ST JACKSONVILLE FL 32254')
    keeps street and city together as line1, with state and zip split off. Anything else
    keeps the whole text as line1 rather than guessing."""
    full = _text(text)
    if form == "slash" and full:
        line, _, rest = full.rpartition(" / ")
        m = CITY_TAIL.match(rest.upper())
        if m and line.strip():
            return {"line1": line.strip(), "city": rest[: m.end("city")].strip(),
                    "state": m["state"], "zip": m["zip"]}  # fmt: skip
        if m:  # no slash: the city cannot be told from the street
            return {"line1": rest[: m.end("city")].strip(), "city": None,
                    "state": m["state"], "zip": m["zip"]}  # fmt: skip
    if form == "city_st_zip" and full:  # 'BATAVIA OH 45103' (no comma, no street)
        m = CITY_ST_ZIP.match(full.upper())
        if m:
            return {"line1": None, "city": m["city"].strip(), "state": m["state"],
                    "zip": m["zip"]}  # fmt: skip
    if form == "city_state_zip" and full and "," in full:
        city, rest = full.rsplit(",", 1)
        m = ADDRESS_TAIL.match(rest.strip().upper())
        if m and city.strip():
            return {"line1": None, "city": city.strip(), "state": m["state"], "zip": m["zip"]}
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
        ua = str(self.config.get("user_agent") or USER_AGENT)
        self.client = client or PoliteClient(min_interval_s=1.0, user_agent=ua)

    def source_row(self) -> Mapping[str, Any]:
        t = self.config["terms"]
        return {
            "source_id": self.source_id,
            "kind": "recorder",
            "jurisdiction": self.config.get("county_fips") or self.config["state"],
            "access_method": ACCESS.get(self.api, "api"),
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
        if self.api in FILE_APIS:
            return str(self.config["url"])
        return f"{self.config['portal']}/resource/{self.config['dataset']}.json"

    def partitions(self) -> Iterator[dict[str, str]]:
        if self.api in FILE_APIS or self.config.get("single_partition"):
            yield {"file": "all"}  # one file or dataset, replaced in full each update
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
            lo, hi = (
                (f"'{params['from']}'", f"'{params['to']}'")
                if self.config.get("date_is_text")
                else (f"DATE '{params['from']}'", f"DATE '{params['to']}'")
            )
            clauses.append(f"{f} >= {lo} AND {f} < {hi}")
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

    def file_url(self) -> str:
        """The file to download: config url, or the current link found on link_from.page."""
        spec = self.config.get("link_from")
        if not spec:
            return str(self.config["url"])
        page = self.client.get(str(spec["page"]))
        if page.status != 200:
            raise LienConfigError(f"{self.source_id}: HTTP {page.status} from {spec['page']}")
        text = page.content.decode("utf-8", errors="replace")
        for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", text, re.IGNORECASE):
            href = html.unescape(href)
            if re.search(str(spec["pattern"]), href):
                return urllib.parse.urljoin(str(spec["page"]), href)
        raise LienConfigError(f"{self.source_id}: no link matching {spec['pattern']!r}")

    def _enrich(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Config enrich: {carto, table, key, field, columns}: look the row's `field` up as
        `key` in a Carto SQL table and add `columns` (first match in key order wins). Used when
        a source names a case but its owner and parcel live in another public table."""
        spec = self.config.get("enrich")
        if not spec or not rows:
            return rows
        field = str(spec["field"])
        keys = sorted({str(r[field]) for r in rows if r.get(field) not in (None, "")})
        found: dict[str, dict[str, Any]] = {}
        cols = [str(c) for c in spec["columns"]]
        for i in range(0, len(keys), 200):
            # Table and column names come from repo config; keys are quoted with '' doubled.
            quoted = ", ".join("'" + k.replace("'", "''") + "'" for k in keys[i : i + 200])
            sql = (
                f"SELECT {spec['key']}, {', '.join(cols)} FROM {spec['table']} "  # noqa: S608
                f"WHERE {spec['key']} IN ({quoted}) ORDER BY {spec['key']}, {cols[0]}"
            )
            resp = self.client.get(str(spec["carto"]), {"q": sql})
            if resp.status != 200:
                raise LienConfigError(f"{self.source_id}: enrich query HTTP {resp.status}")
            for r in json.loads(resp.content).get("rows") or []:
                found.setdefault(str(r[spec["key"]]), {c: r.get(c) for c in cols})
        empty = dict.fromkeys(cols)
        return [{**r, **found.get(str(r.get(field)), empty)} for r in rows]

    def _file_rows(self, content: bytes) -> list[dict[str, Any]]:
        """Rows of a downloaded workbook, text file or page with Excel and M/D/YYYY dates as
        ISO text, split addresses and the list's as-of date, so normalize reads them like any
        other source."""
        cfg = self.config
        head = int(cfg.get("header_row", 0))
        if self.api == "html":
            tables, banner = html_tables(content)
            idx = int(cfg.get("table", 0))
            table = tables[idx] if idx < len(tables) else []
        elif self.api == "pdf":
            table, banner = pdf_table(content, str(cfg["header"])), pdf_text(content)
        elif self.api == "csv":
            table, banner = csv_table(content, str(cfg.get("delimiter", ","))), ""
        else:
            table = xlsx_table(content, int(cfg.get("sheet", 0)))
            banner = " ".join(c for r in table[:head] for c in r if c)
        table = table[head:]
        as_of = cfg.get("as_of")
        listed = text_date(banner, str(as_of.get("after", ""))) if as_of else None
        rows: list[dict[str, Any]] = []
        split = cfg.get("address_split")
        for row in table_rows(table):
            out: dict[str, Any] = dict(row)
            for f in cfg.get("excel_dates") or ():
                out[f] = excel_date(row.get(f))
            for f in cfg.get("us_dates") or ():
                out[f] = us_date(row.get(f))
            if split:
                parts = split_address(row.get(split["field"]), str(split.get("form", "comma")))
                for k, v in parts.items():
                    out[f"{split['prefix']}{k}"] = v
            if as_of:
                out[as_of["field"]] = listed
            rows.append(out)
        return rows

    def fetch(self, request: FetchRequest) -> Fetched:
        limit = request.params.get("limit")
        where = self.where(request.params)
        if self.api in FILE_APIS:
            url = self.file_url()
            resp = self.client.get(url)
            if resp.status != 200:
                raise LienConfigError(f"{self.source_id}: HTTP {resp.status} from {resp.url}")
            rows_x = self._file_rows(resp.content)
            rows_x = rows_x[: int(limit)] if limit else rows_x
            body_x = canonical_json({"url": url, "rows": rows_x})
            return Fetched(self.source_id, url, resp.retrieved_at, 200, body_x,
                           "application/json")  # fmt: skip
        if self.api == "arcgis":
            q_a = self._arcgis_query(where, int(limit) if limit else 1000)
            feats, resps = arcgis_fetch_all(self.client, q_a, max_pages=1 if limit else 10_000,
                                            sample=bool(limit))  # fmt: skip
            rows_a = self._enrich([f.get("attributes") or {} for f in feats])
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

    def _parcels(self, row: Mapping[str, Any]) -> list[tuple[str | None, str | None]]:
        """Every lot the row names: a pin spec may list several fields (parcels1..parcels15)."""
        spec = self.config.get("parcel") or {}
        if spec.get("kind") == "pin" and isinstance(spec.get("field"), list):
            return [self._parcel({**row, "_pin": row.get(f)}, {**spec, "field": "_pin"})
                    for f in spec["field"]]  # fmt: skip
        return [self._parcel(row)]

    def _parcel(
        self, row: Mapping[str, Any], spec_over: Mapping[str, Any] | None = None
    ) -> tuple[str | None, str | None]:
        """(parcel_uid, county fips) for the row's lot, or (None, None)."""
        spec = spec_over or self.config.get("parcel") or {}
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
            name = str(row.get(field) or "").strip()
            alias = {k.upper(): v for k, v in (self.config.get("county_aliases") or {}).items()}
            name = alias.get(name.upper(), name)
            fips = _county_by_name(self.config["state"]).get(norm_county_name(name))
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
        for raw in json.loads(fetched.content).get("rows") or []:
            row = self._derive(raw)
            if cfg.get("listed_on"):  # a current list with no per-row date: the fetch date
                row = {**row, cfg["listed_on"]: fetched.retrieved_at.date().isoformat()}
            uid_raw = self._uid(row)
            if uid_raw and _date(row.get(cfg["date_field"])) is not None:
                groups.setdefault(uid_raw, []).append(row)  # no key or no date: skipped
        for uid_raw in sorted(groups):
            rows = sorted(groups[uid_raw], key=canonical_json)
            first = rows[0]
            recorded = min(d for d in (_date(r.get(cfg["date_field"])) for r in rows) if d)
            lots = sorted({lot for r in rows for lot in self._parcels(r) if lot[0]})
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

    def _derive(self, row: Mapping[str, Any]) -> Mapping[str, Any]:
        """Fields computed from the raw row: a case caption 'A vs B' split into
        caption_plaintiff and caption_defendant (config caption_field)."""
        split = self.config.get("address_split")
        if split and self.api not in FILE_APIS:  # file apis split at fetch
            addr = split_address(row.get(split["field"]), str(split.get("form", "comma")))
            row = {**row, **{f"{split['prefix']}{k}": v for k, v in addr.items()}}
        years = self.config.get("year_dates") or ()
        if years:
            row = dict(row)
            for f in years:
                y = str(row.get(f) or "").strip()[:4]
                row[f] = f"{y}-01-01" if y.isdigit() and len(y) == 4 else None
        field = self.config.get("caption_field")
        if not field:
            return row
        parts = CAPTION_VS.split(str(row.get(field) or ""), maxsplit=1)
        if len(parts) != 2:
            return row
        return {**row, "caption_plaintiff": _text(parts[0]), "caption_defendant": _text(parts[1])}

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
                raw = _text(p["const"]) if "const" in p else _join(row, p.get("name"))
                sep = str(p.get("split") or "").strip()
                names = [n.strip() for n in raw.split(sep)] if raw and sep else [raw]
                a = p.get("address") or {}
                zipc = _text(row.get(a["zip"])) if a.get("zip") else None
                zip5 = zipc[:5] if zipc and re.fullmatch(r"[0-9]{5}", zipc[:5]) else None
                state = (_text(row.get(a["state"])) if a.get("state") and a["state"] in row
                         else _text(a.get("state_const")))  # fmt: skip
                city = (_text(row.get(a["city"])) if a.get("city")
                        else _text(a.get("city_const")))  # fmt: skip
                addr = normalized_address(_join(row, a.get("line1")), city, state,
                                          zip5) if a else None  # fmt: skip
                by_name = found.setdefault(p["role"], {})
                for name in names:
                    if not name or name.upper() in skip:
                        continue
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
        if self.api in (*FILE_APIS, "arcgis"):
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
