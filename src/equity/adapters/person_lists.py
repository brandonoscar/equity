"""Government-published lists that name people with an address: state unclaimed-property owner
files, city uncashed-check lists, rental and building registries. One YAML per list in
config/person_lists/<st>.<publisher>.<name>.yaml; one adapter class per file, generated at
import.

These are the locate sources for states whose voter files may not be used commercially. Each
row becomes, with existing tables only:

  source_record  the list row (record_type from config, e.g. unclaimed_property)
  party          each name on the row as printed, with the row's address
  address        the normalized last-known (or registered) address

Four access methods (`api`):

  socrata      a Socrata dataset, planned as windows of PAGE rows over :id order
  csv_ranges   one very large CSV file served with HTTP byte ranges (e.g. Oklahoma's 470 MB
               unclaimed-property file). The file's current name is found on `csv.page` (or in
               the page's `csv.script`, for a single-page app); partitions are byte windows of
               `csv.chunk_bytes`, found by 1-byte probes, never by downloading the file. A
               window holds the lines that start inside it. `csv.whole: true`: a small file
               fetched in one GET (for servers that mangle ranges), one window.
  html_table   one HTML page per partition value (`html.url` with {value}); the values are
               the link texts of the anchors whose id starts with `html.link_id_prefix` on
               `html.index` (e.g. Missouri's 115 county lists). Rows are the <tr> elements of
               the first table (or those whose id contains `html.row_id`); `html.columns`
               names the cells.
  arcgis       an ArcGIS FeatureServer/MapServer layer (`arcgis.layer`), planned as windows of
               `arcgis.window` object ids (`arcgis.id_field`) between the layer's min and max
               id, each paged `arcgis.page` features at a time (e.g. Orange County's 7M-row
               extract of the California Controller's unclaimed-property file).
  delivered    a file obtained by request, purchase or hand download (it is not fetchable by
               a script), dropped into data/manual/<source_id>/ or named by a `path=` param:
               CSV / delimited / fixed-width text, .xlsx, or a .zip of those. Text is planned
               as byte windows of `file.chunk_bytes` per file (or zip member), like
               csv_ranges; an .xlsx as windows of `file.rows_per_part` rows. Headers are
               canonicalized ('Owner Name' -> OWNER_NAME) unless `file.canon: false`;
               headerless layouts name `file.columns` (delimited) or `file.fixed` ([[name,
               width], ...]). `file.request_url` is the form or page that says how to ask.
  pdf_table    one PDF per partition value (`pdf.url` with {value}, resolved against
               `pdf.index`); the values are group 1 of the `pdf.link` regex on `pdf.index`
               and/or `pdf.values` (e.g. New Jersey's and Ohio's per-county notices of
               owners). Lines are cut into `pdf.columns` at the x positions `pdf.cuts`, below
               each page's `pdf.header` line; `pdf.wrap` names a column whose long values
               continue on a line of their own; `pdf.require` ({column: regex}) keeps a row.

Config keys: source_id, state, jurisdiction (FIPS), kind (source kind), record_type, api,
  portal + dataset (socrata) | csv (csv_ranges) | html (html_table) | arcgis (arcgis) | file
  (delivered) | pdf (pdf_table); key (field or fields that
  identify a row; else a hash of the row); parties: list of {role, name: field | [fields]
  (first non-empty), parts: {first, middle, last, suffix} (used when name is empty), format:
  as_is | first_last ('THOMAS J MANN') | last_first ('MANN THOMAS J') | last_comma_first |
  last_first_comma (either of the last two),
  split (separator for a column holding several names), address: {street: field | [fields],
  city, state | state_const, zip, city_state_zip, line}}; key_prefix; skip_names; extra_pii;
  terms: {url, summary, checked_on, cost_model, robots_checked_on (default checked_on),
  use_restrictions (tags as in the parcel configs, shown as RESTRICTED[...] in the source
  row)}.

Names in a person list are mostly people, but holders report companies too: classify() decides
org vs unknown (as everywhere), and only a non-org name gets first/middle/last parts.
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
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, ClassVar

import yaml

from equity.adapters.arcgis import ArcGISError, ArcGISQuery, fetch_all, get_json
from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import OVERLAP, RangeClient, Response, window_lines
from equity.adapters.licenses import AddressSpec
from equity.adapters.licenses import address_of as license_address_of
from equity.adapters.pdf_lists import pdf_rows
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataError, SocrataQuery, parse_rows
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

LISTS_DIR = CONFIG_DIR / "person_lists"
PAGE = 50_000
APIS = {"socrata": ("portal", "dataset"), "csv_ranges": ("csv",), "html_table": ("html",),
        "arcgis": ("arcgis",), "delivered": ("file",), "pdf_table": ("pdf",)}  # fmt: skip
ACCESS = {"socrata": "api", "csv_ranges": "bulk", "html_table": "html", "arcgis": "arcgis",
          "delivered": "manual", "pdf_table": "bulk"}  # fmt: skip
KINDS = frozenset({"sos", "tax", "court", "vessel", "government_sale"})
FORMATS = frozenset({"as_is", "first_last", "last_first", "last_comma_first", "last_first_comma"})
REQUIRED = ("source_id", "state", "jurisdiction", "kind", "record_type", "parties", "terms")
PART_KEYS = ("first", "middle", "last", "suffix")
SUFFIXES = frozenset({"JR", "SR", "II", "III", "IV"})
PLACEHOLDERS = frozenset({"UNKNOWN", "UNK", "NONE", "NO ADDRESS", "ADDRESS UNKNOWN", "NA", "N A"})


class PersonListConfigError(ValueError):
    pass


def _fields(spec: Any) -> list[str]:
    if spec is None:
        return []
    return [spec] if isinstance(spec, str) else [str(s) for s in spec]


@dataclass(frozen=True)
class PartySpec:
    role: str
    name: tuple[str, ...]
    parts: Mapping[str, str]
    format: str
    split: str | None
    address: AddressSpec | None
    person_names: bool  # False: the name column holds only companies (not pseudonymized)

    @staticmethod
    def parse(data: Mapping[str, Any]) -> PartySpec:
        fmt = str(data.get("format", "as_is"))
        if fmt not in FORMATS:
            raise PersonListConfigError(f"unknown name format {fmt!r}")
        parts = dict(data.get("parts") or {})
        if set(parts) - set(PART_KEYS):
            raise PersonListConfigError(f"unknown name parts {sorted(set(parts) - set(PART_KEYS))}")
        if not data.get("name") and not parts:
            raise PersonListConfigError("a party needs name or parts")
        addr = dict(data.get("address") or {})
        state_const = addr.pop("state_const", None)
        spec = AddressSpec.parse(addr) if addr else None
        return PartySpec(
            role=str(data.get("role", "named")), name=tuple(_fields(data.get("name"))),
            parts=parts, format=fmt, split=data.get("split"),
            address=_with_state(spec, state_const),
            person_names=bool(data.get("person_names", True)),
        )  # fmt: skip


def _with_state(spec: AddressSpec | None, state_const: str | None) -> AddressSpec | None:
    if spec is None or state_const is None:
        return spec
    # A constant state rides in a synthetic column the row never has; address_of() below fills it.
    return AddressSpec(spec.street, spec.city, f"={state_const}", spec.zip, spec.city_state_zip,
                       spec.line)  # fmt: skip


@dataclass(frozen=True)
class PersonListConfig:
    data: Mapping[str, Any]
    parties: tuple[PartySpec, ...]

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    @property
    def source_id(self) -> str:
        return str(self.data["source_id"])

    @property
    def api(self) -> str:
        return str(self.data.get("api", "socrata"))

    @property
    def pii_fields(self) -> tuple[str, ...]:
        out: set[str] = set()
        for p in self.parties:
            if p.person_names:
                out |= set(p.name) | set(p.parts.values())
            if p.address is not None:
                out |= set(p.address.street)
                if p.address.line:
                    out.add(p.address.line)
        return tuple(sorted(out | set(self.data.get("extra_pii") or ())))


def load_person_list(path: Path) -> PersonListConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    api = data.get("api", "socrata")
    if api not in APIS:
        raise PersonListConfigError(f"{path.name}: unknown api {api!r}")
    missing = [k for k in (*REQUIRED, *APIS[api]) if k not in data]
    if missing:
        raise PersonListConfigError(f"{path.name}: missing {missing}")
    if data["kind"] not in KINDS:
        raise PersonListConfigError(f"{path.name}: kind must be one of {sorted(KINDS)}")
    if path.stem != data["source_id"]:
        raise PersonListConfigError(f"{path.name}: file name must be the source_id")
    if api == "csv_ranges" and not {"url", "page"} & set(data["csv"]):
        raise PersonListConfigError(f"{path.name}: csv needs url or page")
    if api == "html_table" and "url" not in data["html"]:
        raise PersonListConfigError(f"{path.name}: html needs url")
    if api == "arcgis" and "layer" not in data["arcgis"]:
        raise PersonListConfigError(f"{path.name}: arcgis needs layer")
    if api == "pdf_table" and not {"url", "columns", "cuts"} <= set(data["pdf"]):
        raise PersonListConfigError(f"{path.name}: pdf needs url, columns and cuts")
    if api == "delivered" and "request_url" not in data["file"]:
        raise PersonListConfigError(f"{path.name}: file needs request_url")
    terms = data["terms"]
    for k in ("url", "summary", "checked_on"):
        if k not in terms:
            raise PersonListConfigError(f"{path.name}: terms missing {k}")
    try:
        parties = tuple(PartySpec.parse(p) for p in data["parties"])
    except PersonListConfigError as err:
        raise PersonListConfigError(f"{path.name}: {err}") from err
    return PersonListConfig(data, parties)


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    s = " ".join(str(value).split())
    return s or None


def address_of(row: Mapping[str, Any], spec: AddressSpec | None) -> dict[str, Any] | None:
    if spec is None:
        return None
    # Holders report 'UNKNOWN' for a missing street or city: such a part is no address.
    cols = [*spec.street, spec.city, spec.state, spec.zip, spec.city_state_zip, spec.line]
    blank: dict[str, str | None] = {
        c: None for c in cols if c and clean(_text(row.get(c)) or "") in PLACEHOLDERS
    }
    if spec.state and spec.state.startswith("="):
        blank[spec.state] = spec.state[1:]
    if spec.line and (line := _text(row.get(spec.line))) and (m := _ST_COMMA_ZIP.search(line)):
        # '1 MAIN ST, RALEIGH, NC, 27606-4999': no comma between state and ZIP.
        blank[spec.line] = f"{line[: m.start()]}, {m['st']} {m['zip']}"
    return license_address_of({**row, **blank} if blank else row, spec)


_ST_COMMA_ZIP = re.compile(r",\s*(?P<st>[A-Za-z]{2}),\s*(?P<zip>\d{5}(?:-?\d{4})?)\s*$")


def split_name(name: str, fmt: str) -> dict[str, str | None]:
    """first/middle/last/suffix of a person's name printed in `fmt`; all None for as_is."""
    out: dict[str, str | None] = dict.fromkeys(PART_KEYS)
    if fmt == "last_first_comma":  # 'LAST, FIRST M' or 'LAST FIRST M' in one list
        fmt = "last_comma_first" if "," in name else "last_first"
    if fmt == "last_comma_first" and "," in name:
        last, _, rest = name.partition(",")
        words = rest.split()
        out["last"] = _text(last)
    elif fmt == "last_first":
        tokens = name.split()
        if len(tokens) < 2:
            return out
        out["last"], words = tokens[0], tokens[1:]
    elif fmt == "first_last":
        words = name.split()
        if words and words[-1].upper().rstrip(".") in SUFFIXES:
            out["suffix"] = words.pop()
        if len(words) < 2:
            return dict.fromkeys(PART_KEYS)
        out["first"], out["last"] = words[0], words[-1]
        out["middle"] = " ".join(words[1:-1]) or None
        return out
    else:
        return out
    if words and words[-1].upper().rstrip(".") in SUFFIXES:
        out["suffix"] = words.pop()
    if words:
        out["first"] = words[0]
        out["middle"] = " ".join(words[1:]) or None
    return out


def names_of(
    row: Mapping[str, Any], spec: PartySpec, skip: frozenset[str]
) -> list[tuple[str, dict[str, str | None]]]:
    """(name as printed, parts) for each name the spec finds on the row."""
    raw = next((t for t in (_text(row.get(c)) for c in spec.name) if t), None)
    if raw is None and spec.parts:
        vals = {k: _text(row.get(col)) for k, col in spec.parts.items()}
        if not vals.get("last"):
            return []
        name = " ".join(v for k in PART_KEYS if (v := vals.get(k)))
        parts = {k: vals.get(k) for k in PART_KEYS}
        return [] if name.upper() in skip else [(name, parts)]
    if raw is None:
        return []
    out = []
    for one in raw.split(spec.split) if spec.split else [raw]:
        found = _text(one)
        if not found or found.upper() in skip:
            continue
        name = found
        org = classify(name).party_kind == "org"
        parts = dict.fromkeys(PART_KEYS) if org else split_name(name, spec.format)
        out.append((name, parts))
    return out


def row_key(row: Mapping[str, Any], key: list[str], prefix: str = "") -> str:
    vals = [_text(row.get(k)) for k in key]
    if key and all(vals):
        return prefix + "-".join(v for v in vals if v)
    return prefix + "h" + stable_id("row", canonical_json(row).decode())[:20]


# --- html_table -------------------------------------------------------------------------------

_TR = re.compile(r"<tr\b([^>]*)>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")


def table_rows(page: str, columns: list[str], row_id: str | None) -> list[dict[str, str]]:
    start = page.lower().find("<table")
    body = page[start:] if start >= 0 else page
    out = []
    for attrs, inner in _TR.findall(body):
        if row_id and row_id not in attrs:
            continue
        cells = [" ".join(html.unescape(_TAGS.sub(" ", c)).split()) for c in _TD.findall(inner)]
        if len(cells) < len(columns):
            continue
        out.append(dict(zip(columns, cells, strict=False)))
    return out


def link_values(page: str, id_prefix: str) -> list[str]:
    """Texts of the anchors whose id starts with id_prefix, in page order, de-duplicated."""
    pat = re.compile(r'<a\b[^>]*\bid="' + re.escape(id_prefix) + r'[^"]*"[^>]*>(.*?)</a>', re.S)
    seen: dict[str, None] = {}
    for m in pat.finditer(page):
        text = " ".join(html.unescape(_TAGS.sub(" ", m.group(1))).split())
        if text:
            seen.setdefault(text, None)
    return list(seen)


# --- arcgis -----------------------------------------------------------------------------------


def id_windows(lo: int, hi: int, window: int) -> list[tuple[int, int]]:
    """[lo, hi] (inclusive object-id bounds) as half-open windows of `window` ids."""
    return [(a, min(a + window, hi + 1)) for a in range(lo, hi + 1, window)]


# --- delivered --------------------------------------------------------------------------------

MANUAL_DIR = Path("data") / "manual"
DATA_FILE = r"\.(csv|txt|tsv|dat|xlsx)$"
NOT_DATA = r"(?i)layout|readme|record_?desc"
_XL = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def canon(header: str) -> str:
    """'Owner Name' -> 'OWNER_NAME'; 'Zip+4' -> 'ZIP_4'."""
    return re.sub(r"[^A-Z0-9]+", "_", header.strip().lstrip("﻿").upper()).strip("_")


def fixed_rows(lines: list[str], fixed: list[tuple[str, int]]) -> list[dict[str, str]]:
    """Fixed-width lines cut by consecutive (name, width) fields."""
    out = []
    for line in lines:
        line = line.rstrip("\r\n")
        if not line.strip():
            continue
        row, pos = {}, 0
        for name, width in fixed:
            row[name] = line[pos : pos + width].strip()
            pos += width
        out.append(row)
    return out


def _xlsx_col(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + ord(ch.upper()) - 64
    return n - 1


def xlsx_rows(raw: Any) -> Iterator[list[str]]:
    """Every row of the largest worksheet of an .xlsx (a binary file object), as cell texts,
    streamed with the standard library (shared and inline strings, raw values)."""
    with zipfile.ZipFile(raw) as zf:
        names = zf.namelist()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            # A government delivery; Python's expat refuses entity-expansion bombs.
            for _, el in ET.iterparse(zf.open("xl/sharedStrings.xml")):  # noqa: S314
                if el.tag == f"{_XL}si":
                    shared.append("".join(t.text or "" for t in el.iter(f"{_XL}t")))
                    el.clear()
        sheets = [n for n in names if n.startswith("xl/worksheets/") and n.endswith(".xml")]
        if not sheets:
            return
        sheet = max(sheets, key=lambda n: (zf.getinfo(n).file_size, n))
        for _, el in ET.iterparse(zf.open(sheet)):  # noqa: S314
            if el.tag != f"{_XL}row":
                continue
            cells: dict[int, str] = {}
            for pos, c in enumerate(el.iter(f"{_XL}c")):
                col = _xlsx_col(c.get("r", "")) if c.get("r") else pos
                v = c.find(f"{_XL}v")
                if c.get("t") == "s" and v is not None and v.text:
                    cells[col] = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    cells[col] = "".join(t.text or "" for t in c.iter(f"{_XL}t"))
                else:
                    cells[col] = (v.text or "") if v is not None else ""
            el.clear()
            yield [cells.get(i, "") for i in range(max(cells) + 1)] if cells else []


@dataclass(frozen=True)
class Member:
    """One data file of a delivery: a plain file, or `name` inside the zip at `path`."""

    path: Path
    name: str  # '' for a plain file
    size: int

    @property
    def label(self) -> str:
        return self.name or self.path.name

    @property
    def is_xlsx(self) -> bool:
        return self.label.lower().endswith(".xlsx")

    def open(self) -> Any:
        if not self.name:
            return self.path.open("rb")
        zf = zipfile.ZipFile(self.path)
        return zf.open(self.name)  # keeps the archive open until the member is closed

    def read_range(self, start: int, stop: int) -> bytes:
        """Bytes [start, stop) (seeking a zip member inflates up to `start`)."""
        with self.open() as f:
            f.seek(start)
            return bytes(f.read(max(stop - start, 0)))


def delivery_members(source: Path, include: str = DATA_FILE, exclude: str = NOT_DATA
                     ) -> list[Member]:  # fmt: skip
    """The data files of a delivery (a file, a zip, or a folder of either), in name order."""
    files = sorted(p for p in source.rglob("*") if p.is_file()) if source.is_dir() else [source]
    inc, exc = re.compile(include, re.I), re.compile(exclude)
    out: list[Member] = []
    for f in files:
        if f.name.startswith(".") or exc.search(f.name):
            continue
        if f.suffix.lower() == ".zip":
            with zipfile.ZipFile(f) as zf:
                out += [Member(f, i.filename, i.file_size) for i in zf.infolist()
                        if not i.is_dir() and inc.search(i.filename)
                        and not exc.search(i.filename)]  # fmt: skip
        elif inc.search(f.name):
            out.append(Member(f, "", f.stat().st_size))
    return out


# --- the adapter ------------------------------------------------------------------------------


class PersonListAdapter(Adapter):
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    config: ClassVar[PersonListConfig]
    pii_fields: ClassVar[tuple[str, ...]] = ()

    def __init__(self, client: RangeClient | None = None) -> None:
        self.client = client or RangeClient(min_interval_s=1.0, timeout_s=300.0)

    @property
    def base_url(self) -> str:
        c = self.config
        if c.api == "socrata":
            return f"{c['portal']}/resource/{c['dataset']}.json"
        if c.api == "csv_ranges":
            return str(c["csv"].get("url") or c["csv"]["page"])
        if c.api == "arcgis":
            return str(c["arcgis"]["layer"])
        if c.api == "delivered":
            return str(c["file"]["request_url"])
        if c.api == "pdf_table":
            return str(c["pdf"].get("index") or c["pdf"]["url"])
        return str(c["html"].get("index") or c["html"]["url"])

    def source_row(self) -> Mapping[str, Any]:
        c = self.config
        t = c["terms"]
        tags = sorted(str(x) for x in t.get("use_restrictions") or ())
        restricted = f"RESTRICTED[{','.join(tags)}] " if tags else ""
        return {
            "source_id": c.source_id,
            "kind": c["kind"],
            "jurisdiction": str(c["jurisdiction"]),
            "access_method": ACCESS[c.api],
            "base_url": self.base_url,
            "terms_url": t["url"],
            "terms_summary": restricted + t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t.get("robots_checked_on", t["checked_on"]),
            "cost_model": t.get("cost_model", "free"),
        }

    # planning ----------------------------------------------------------------------------

    def partitions(self) -> Iterator[dict[str, str]]:
        c = self.config
        if c.api == "socrata":
            url = f"{c['portal']}/resource/{c['dataset']}.json"
            resp = self.client.get(url, {"$select": "count(*) as n",
                                         "$where": c.get("where", "1=1")})  # fmt: skip
            if resp.status != 200:
                raise SocrataError(f"HTTP {resp.status} from {resp.url}")
            rows = parse_rows(resp.content)
            total = int(rows[0]["n"]) if rows else 0
            for off in range(0, total, PAGE):
                yield {"offset": str(off), "limit": str(PAGE)}
        elif c.api == "csv_ranges" and c["csv"].get("whole"):
            yield {"url": self.current_csv_url(), "lo": "0",
                   "hi": str(int(c["csv"].get("chunk_bytes", 8_000_000)))}  # fmt: skip
        elif c.api == "csv_ranges":
            url = self.current_csv_url()
            chunk = int(c["csv"].get("chunk_bytes", 8_000_000))
            lo = 0
            while True:
                probe = self.client.get_range(url, lo, lo)
                if probe.status != 206:
                    break
                yield {"url": url, "lo": str(lo), "hi": str(lo + chunk)}
                lo += chunk
        elif c.api == "arcgis":
            yield from self._arcgis_partitions()
        elif c.api == "delivered":
            yield from self._delivered_partitions()
        elif c.api == "pdf_table":
            yield from self._pdf_partitions()
        else:
            h = c["html"]
            if "index" in h:
                page = self._get(h["index"]).content.decode("utf-8", errors="replace")
                for v in link_values(page, h["link_id_prefix"]):
                    yield {"value": v}
            for v in h.get("values") or ():
                yield {"value": str(v)}

    def current_csv_url(self) -> str:
        """The file named on the download page now (its date changes with each release), else
        the configured url."""
        spec = self.config["csv"]
        if "page" not in spec:
            return str(spec["url"])
        pattern = re.compile(spec["file"])
        page = self._get(spec["page"]).content.decode("utf-8", errors="replace")
        text = page
        if "script" in spec and (m := re.search(spec["script"], page)):
            text = self._get(urllib.parse.urljoin(spec["page"], "/" + m.group(0).lstrip("/"))
                             ).content.decode("utf-8", errors="replace")  # fmt: skip
        found = pattern.search(text)
        if found is None:
            if "url" in spec:
                return str(spec["url"])
            raise RuntimeError(f"{self.source_id}: no file matching {spec['file']!r}")
        return urllib.parse.urljoin(str(spec["page"]), found.group(0))

    def _get(self, url: str, params: Mapping[str, str] | None = None) -> Response:
        resp = self.client.get(url, params)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {resp.url}")
        return resp

    # fetching ----------------------------------------------------------------------------

    def fetch(self, request: FetchRequest) -> Fetched:
        c = self.config
        p = request.params
        if c.api == "socrata":
            body, req = self._fetch_socrata(p)
        elif c.api == "csv_ranges":
            body, req = self._fetch_csv(p)
        elif c.api == "arcgis":
            body, req = self._fetch_arcgis(p)
        elif c.api == "delivered":
            body, req = self._fetch_delivered(p)
        elif c.api == "pdf_table":
            body, req = self._fetch_pdf(p)
        else:
            body, req = self._fetch_html(p)
        return Fetched(c.source_id, req, datetime.now(UTC), 200, canonical_json(body),
                       "application/json")  # fmt: skip

    def _fetch_socrata(self, p: Mapping[str, str]) -> tuple[dict[str, Any], str]:
        """params: offset, limit (a window over :id order)."""
        c = self.config
        offset, limit = int(p.get("offset", "0")), int(p.get("limit", str(PAGE)))
        q = SocrataQuery(c["portal"], c["dataset"], c.get("where", "1=1"), (":id",), limit)
        resp = self.client.get(q.url, q.params(offset))
        if resp.status != 200:
            raise SocrataError(f"HTTP {resp.status} from {resp.url}")
        rows = parse_rows(resp.content)
        return {"offset": offset, "rows": rows}, resp.url

    def _fetch_csv(self, p: Mapping[str, str]) -> tuple[dict[str, Any], str]:
        """params: url (from partitions; else the current file), lo, hi (byte window)."""
        url = p.get("url") or self.current_csv_url()
        lo, hi = int(p["lo"]), int(p["hi"])
        if self.config["csv"].get("whole"):
            return self._fetch_csv_whole(url, lo, hi)
        head = self.client.get_range(url, 0, 16_383)
        if head.status not in (200, 206):
            raise RuntimeError(f"HTTP {head.status} from {url}")
        header = next(csv.reader([head.content.split(b"\n", 1)[0].decode("utf-8-sig")]))
        start = max(lo - 1, 0)
        want = hi + OVERLAP - 1
        resp = self.client.get_range(url, start, want)
        if resp.status == 416:  # the window starts past the end
            data, at_eof = b"", True
        elif resp.status in (200, 206):
            data = resp.content if resp.status == 206 else resp.content[start : want + 1]
            at_eof = len(data) < want - start + 1
        else:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        lines = window_lines(data, lo, hi, start, at_eof)
        if lo == 0 and lines:
            lines = lines[1:]  # the header
        text = b"".join(lines).decode("utf-8", errors="replace")
        rows = [dict(zip(header, r, strict=False)) for r in csv.reader(io.StringIO(text)) if r]
        return {"url": url, "lo": lo, "hi": hi, "columns": header, "rows": rows}, (
            f"{url}#bytes={lo}-{hi - 1}"
        )

    def _fetch_csv_whole(self, url: str, lo: int, hi: int) -> tuple[dict[str, Any], str]:
        """`csv.whole`: a small CSV fetched in one GET, then cut to the lines that start in
        [lo, hi) (for a server that mangles byte ranges, e.g. gzip under a range length)."""
        data = self._get(url).content
        header = next(csv.reader([data.split(b"\n", 1)[0].decode("utf-8-sig")]))
        lines = window_lines(data[max(lo - 1, 0) :], lo, hi, max(lo - 1, 0), True)
        if lo == 0 and lines:
            lines = lines[1:]  # the header
        text = b"".join(lines).decode("utf-8", errors="replace")
        rows = [dict(zip(header, r, strict=False)) for r in csv.reader(io.StringIO(text)) if r]
        return {"url": url, "lo": lo, "hi": hi, "columns": header, "rows": rows}, (
            f"{url}#bytes={lo}-{hi - 1}"
        )

    def _fetch_html(self, p: Mapping[str, str]) -> tuple[dict[str, Any], str]:
        """params: value (partition, e.g. a county); limit (fixtures: first rows only)."""
        h = self.config["html"]
        url = h["url"].replace("{value}", urllib.parse.quote_plus(p["value"]))
        page = self._get(url).content.decode("utf-8", errors="replace")
        rows = table_rows(page, list(h["columns"]), h.get("row_id"))
        if "limit" in p:
            rows = rows[: int(p["limit"])]
        field = h.get("value_field", "partition")
        tagged = [{**r, field: p["value"]} for r in rows]
        return {"url": url, field: p["value"], "rows": tagged}, url

    # arcgis ------------------------------------------------------------------------------

    def _arcgis_query(self, where: str, page: int | None = None) -> ArcGISQuery:
        a = self.config["arcgis"]
        return ArcGISQuery(str(a["layer"]), where, tuple(a.get("fields") or ("*",)),
                           (str(a.get("id_field", "OBJECTID")),),
                           page or int(a.get("page", 2000)))  # fmt: skip

    def _arcgis_partitions(self) -> Iterator[dict[str, str]]:
        """Windows of `arcgis.window` object ids from the layer's min to its max id."""
        a = self.config["arcgis"]
        oid = str(a.get("id_field", "OBJECTID"))
        stats = [{"statisticType": s, "onStatisticField": oid, "outStatisticFieldName": s}
                 for s in ("min", "max")]  # fmt: skip
        data = get_json(self.client, f"{a['layer']}/query", {
            "where": str(a.get("where", "1=1")), "outStatistics": json.dumps(stats),
            "f": "json"})  # fmt: skip
        if "error" in data:
            raise ArcGISError(str(data["error"]))
        feats = data.get("features") or []
        attrs = {k.lower(): v for k, v in (feats[0]["attributes"] if feats else {}).items()}
        if attrs.get("min") is None:
            return
        for lo, hi in id_windows(int(attrs["min"]), int(attrs["max"]),
                                 int(a.get("window", 50_000))):  # fmt: skip
            yield {"lo": str(lo), "hi": str(hi)}

    def _fetch_arcgis(self, p: Mapping[str, str]) -> tuple[dict[str, Any], str]:
        """params: lo, hi (object ids, half-open); limit (fixtures: one page of that many)."""
        a = self.config["arcgis"]
        oid = str(a.get("id_field", "OBJECTID"))
        lo, hi = int(p["lo"]), int(p["hi"])
        where = f"({a.get('where', '1=1')}) AND {oid} >= {lo} AND {oid} < {hi}"
        limit = int(p["limit"]) if "limit" in p else None
        feats, resps = fetch_all(self.client, self._arcgis_query(where, limit), max_pages=1
                                 if limit else 10_000, sample=bool(limit))  # fmt: skip
        rows = [dict(f.get("attributes") or {}) for f in feats][:limit]
        return {"lo": lo, "hi": hi, "rows": rows}, resps[0].url if resps else str(a["layer"])

    # delivered ---------------------------------------------------------------------------

    def drop_dir(self) -> Path:
        return MANUAL_DIR / self.source_id

    def delivery(self, p: Mapping[str, str] | None = None) -> Path:
        """`path` if given, else the drop folder (data/manual/<source_id>/)."""
        if p and p.get("path"):
            return Path(p["path"])
        drop = self.drop_dir()
        if not drop.is_dir() or not any(f.is_file() and f.name.upper() != "README.MD"
                                        for f in drop.rglob("*")):  # fmt: skip
            raise RuntimeError(
                f"{drop}: nothing delivered yet. This list is not downloadable by a script: "
                f"get it as {self.config['file']['request_url']} says "
                f"(docs/unclaimed_property_requests_west.md), drop it here, or pass path=."
            )
        return drop

    def _members(self, source: Path) -> list[Member]:
        f = self.config["file"]
        return delivery_members(source, str(f.get("include", DATA_FILE)),
                                str(f.get("exclude", NOT_DATA)))  # fmt: skip

    def _delivered_partitions(self) -> Iterator[dict[str, str]]:
        f = self.config["file"]
        source = self.delivery()
        members = self._members(source)
        if not members:
            raise RuntimeError(f"{source}: no data file found")
        for m in members:
            base = {"path": str(m.path), **({"member": m.name} if m.name else {})}
            if m.is_xlsx:
                step = int(f.get("rows_per_part", 100_000))
                with m.open() as raw:
                    n = sum(1 for _ in xlsx_rows(raw)) - 1
                bounds = range(0, max(n, 1), step)
            else:
                step = int(f.get("chunk_bytes", 8_000_000))
                bounds = range(0, max(m.size, 1), step)
            for lo in bounds:
                yield {**base, "lo": str(lo), "hi": str(lo + step)}

    def _header_of(self, m: Member) -> list[str]:
        f = self.config["file"]
        if f.get("columns"):
            return [str(c) for c in f["columns"]]
        head = m.read_range(0, 65_536).split(b"\n", 1)[0]
        cols = next(csv.reader([head.decode(str(f.get("encoding", "utf-8-sig")), "replace")],
                               delimiter=str(f.get("delimiter", ","))))  # fmt: skip
        return [canon(c) for c in cols] if f.get("canon", True) else cols

    def _fetch_delivered(self, p: Mapping[str, str]) -> tuple[dict[str, Any], str]:
        """params: path (a file or folder; else the drop folder), member (inside a zip),
        lo, hi (byte window of a text file; row window of an .xlsx); limit (first rows)."""
        f = self.config["file"]
        source = self.delivery(p)
        members = self._members(source)
        want = p.get("member", "")
        m = next((x for x in members if x.name == want), None)
        if m is None:
            raise RuntimeError(f"{source}: no data file {want!r}")
        lo, hi = int(p.get("lo", "0")), int(p.get("hi", str(1 << 62)))
        if m.is_xlsx:
            with m.open() as raw:
                it = xlsx_rows(raw)
                first = next(it, [])
                header = [canon(h) for h in first] if f.get("canon", True) else first
                rows = [dict(zip(header, r, strict=False)) for i, r in enumerate(it)
                        if lo <= i < hi and any(x.strip() for x in r)]  # fmt: skip
        else:
            enc = str(f.get("encoding", "utf-8-sig"))
            start = max(lo - 1, 0)
            stop = min(hi + OVERLAP, m.size)
            data = m.read_range(start, stop)
            lines = window_lines(data, lo, hi, start, start + len(data) >= m.size)
            if lo == 0 and lines and not f.get("columns") and not f.get("fixed"):
                lines = lines[1:]  # the header
            text = b"".join(lines).decode(enc, errors="replace")
            if f.get("fixed"):
                fixed = [(str(n), int(w)) for n, w in f["fixed"]]
                header = [n for n, _ in fixed]
                rows = fixed_rows(text.splitlines(), fixed)
            else:
                header = self._header_of(m)
                reader = csv.reader(io.StringIO(text), delimiter=str(f.get("delimiter", ",")))
                rows = [dict(zip(header, r, strict=False)) for r in reader if any(r)]
        if "limit" in p:
            rows = rows[: int(p["limit"])]
        where = f"{m.path}" + (f"!{m.name}" if m.name else "")
        return {"file": m.label, "lo": lo, "hi": hi, "columns": header, "rows": rows}, (
            f"file://{where}#{'rows' if m.is_xlsx else 'bytes'}={lo}-{hi - 1}"
        )

    def _delivered_shape(self) -> tuple[str, ...]:
        """No network: the columns of the first data file on hand (RuntimeError if none)."""
        source = self.delivery()
        members = self._members(source)
        if not members:
            raise RuntimeError(f"{source}: no data file found")
        body, _ = self._fetch_delivered({"path": str(members[0].path), "member": members[0].name,
                                         "lo": "0", "hi": "65536", "limit": "1"})  # fmt: skip
        return tuple(sorted(body["rows"][0])) if body["rows"] else ()

    # pdf_table ---------------------------------------------------------------------------

    def _pdf_partitions(self) -> Iterator[dict[str, str]]:
        """The `pdf.link` matches (group 1) on `pdf.index`, then `pdf.values`, de-duplicated.
        An index that cannot be read falls back to the values when there are some."""
        spec = self.config["pdf"]
        seen: dict[str, None] = {}
        if "index" in spec:
            try:
                page = self._get(spec["index"]).content.decode("utf-8", errors="replace")
            except (RuntimeError, OSError):
                if not spec.get("values"):
                    raise
            else:
                for m in re.finditer(spec["link"], page):
                    seen.setdefault(html.unescape(m.group(1)), None)
        for v in spec.get("values") or ():
            seen.setdefault(str(v), None)
        for v in seen:
            yield {"value": v}

    def _fetch_pdf(self, p: Mapping[str, str]) -> tuple[dict[str, Any], str]:
        """params: value (partition: a county, or a file path the index links); limit
        (fixtures: first rows only)."""
        spec = self.config["pdf"]
        path = str(spec["url"]).replace("{value}", p["value"].replace(" ", "%20"))
        url = urllib.parse.urljoin(str(spec.get("index") or spec["url"]), path)
        rows = pdf_rows(self._get(url).content, [str(c) for c in spec["columns"]],
                        [float(x) for x in spec["cuts"]], str(spec.get("header", "NAME")),
                        spec.get("wrap"), spec.get("require"))  # fmt: skip
        if "limit" in p:
            rows = rows[: int(p["limit"])]
        field = str(spec.get("value_field", "partition"))
        label = re.sub(str(spec.get("label", r"$^")), "", p["value"])
        return {"url": url, field: label, "rows": [{**r, field: label} for r in rows]}, url

    # normalizing -------------------------------------------------------------------------

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        c = self.config
        data = json.loads(fetched.content)
        key = _fields(c.get("key"))
        prefix = str(c.get("key_prefix", ""))
        skip = frozenset(str(s).strip().upper() for s in c.get("skip_names") or ())
        by_key: dict[str, list[dict[str, Any]]] = {}
        for r in data.get("rows", []):
            by_key.setdefault(row_key(r, key, prefix), []).append(r)
        for k in sorted(by_key):
            rows = sorted(by_key[k], key=canonical_json)
            yield from self._record(fetched, k, rows, skip)

    def _record(
        self, fetched: Fetched, key: str, rows: list[dict[str, Any]], skip: frozenset[str]
    ) -> Iterator[NormalizedRow]:
        c = self.config
        ctx = RecordContext(fetched, str(c["jurisdiction"]), key, c["record_type"],
                            rows[0] if len(rows) == 1 else rows)  # fmt: skip
        yield ctx.source_record()
        seen: set[str] = set()
        for row in rows:
            for spec in c.parties:
                addr = address_of(row, spec.address)
                for name, parts in names_of(row, spec, skip):
                    party_id = stable_id(c.source_id, key, spec.role, clean(name))
                    if party_id in seen:
                        continue
                    seen.add(party_id)
                    if addr is not None:
                        yield NormalizedRow("address", addr)
                    nc = classify(name)
                    yield ctx.fact(
                        "party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
                        org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                        address_id=None if addr is None else addr["address_id"],
                        first_name=parts.get("first"), middle=parts.get("middle"),
                        last_name=parts.get("last"), suffix=parts.get("suffix"),
                    )  # fmt: skip

    # health ------------------------------------------------------------------------------

    def health(self) -> HealthReport:
        c = self.config
        now = datetime.now(UTC)
        try:
            if c.api == "socrata":
                body, _ = self._fetch_socrata({"offset": "0", "limit": "1"})
                shape = tuple(sorted(body["rows"][0])) if body["rows"] else ()
            elif c.api == "csv_ranges" and c["csv"].get("whole"):
                body, _ = self._fetch_csv_whole(self.current_csv_url(), 0, 1)
                shape = tuple(sorted(body["columns"]))
            elif c.api == "csv_ranges":
                url = self.current_csv_url()
                head = self.client.get_range(url, 0, 4095)
                line = head.content.split(b"\n", 1)[0].decode("utf-8-sig", errors="replace")
                shape = tuple(sorted(next(csv.reader([line])))) if head.status == 206 else ()
            elif c.api == "arcgis":
                body, _ = self._fetch_arcgis({"lo": "0", "hi": "2147483647", "limit": "1"})
                shape = tuple(sorted(body["rows"][0])) if body["rows"] else ()
            elif c.api == "delivered":
                shape = self._delivered_shape()
            elif c.api == "pdf_table":
                parts = list(self._pdf_partitions())
                body, _ = self._fetch_pdf({**parts[0], "limit": "1"}) if parts else ({}, "")
                shape = tuple(sorted(body["rows"][0])) if body.get("rows") else ()
            else:
                parts = list(self.partitions())
                body, _ = self._fetch_html({**parts[0], "limit": "1"}) if parts else ({}, "")
                shape = tuple(sorted(body["rows"][0])) if body.get("rows") else ()
        except (RuntimeError, OSError, ValueError, IndexError, KeyError) as err:
            return HealthReport(c.source_id, False, now, f"{type(err).__name__}: {err}")
        wanted = {f for p in c.parties for f in (*p.name, *p.parts.values())}
        ok = bool(shape) and bool(wanted & set(shape))
        return HealthReport(c.source_id, ok, now, "ok" if ok else f"shape={list(shape)}", shape)


@cache
def all_person_list_adapters() -> tuple[type[PersonListAdapter], ...]:
    out = []
    for path in sorted(LISTS_DIR.glob("*.yaml")):
        cfg = load_person_list(path)
        out.append(type(
            f"PersonList_{cfg.source_id.replace('.', '_')}", (PersonListAdapter,),
            {"source_id": cfg.source_id, "config": cfg, "pii_fields": cfg.pii_fields,
             "access_method": ACCESS[cfg.api]},
        ))  # fmt: skip
    return tuple(out)
