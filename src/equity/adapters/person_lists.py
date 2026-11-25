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
               window holds the lines that start inside it.
  html_table   one HTML page per partition value (`html.url` with {value}); the values are
               the link texts of the anchors whose id starts with `html.link_id_prefix` on
               `html.index` (e.g. Missouri's 115 county lists). Rows are the <tr> elements of
               the first table (or those whose id contains `html.row_id`); `html.columns`
               names the cells.

Config keys: source_id, state, jurisdiction (FIPS), kind (source kind), record_type, api,
  portal + dataset (socrata) | csv (csv_ranges) | html (html_table); key (field or fields that
  identify a row; else a hash of the row); parties: list of {role, name: field | [fields]
  (first non-empty), parts: {first, middle, last, suffix} (used when name is empty), format:
  as_is | first_last ('THOMAS J MANN') | last_first ('MANN THOMAS J') | last_comma_first,
  split (separator for a column holding several names), address: {street: field | [fields],
  city, state | state_const, zip, city_state_zip, line}}; key_prefix; skip_names; extra_pii;
  terms: {url, summary, checked_on, cost_model}.

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
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, ClassVar

import yaml

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient, Response
from equity.adapters.licenses import AddressSpec
from equity.adapters.licenses import address_of as license_address_of
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataError, SocrataQuery, parse_rows
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

LISTS_DIR = CONFIG_DIR / "person_lists"
PAGE = 50_000
APIS = {"socrata": ("portal", "dataset"), "csv_ranges": ("csv",), "html_table": ("html",)}
ACCESS = {"socrata": "api", "csv_ranges": "bulk", "html_table": "html"}
KINDS = frozenset({"sos", "tax", "court", "vessel", "government_sale"})
FORMATS = frozenset({"as_is", "first_last", "last_first", "last_comma_first"})
REQUIRED = ("source_id", "state", "jurisdiction", "kind", "record_type", "parties", "terms")
# Past the end of a byte window: enough for the line that straddles it (lines are ~300 bytes).
OVERLAP = 65_536
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
    return license_address_of({**row, **blank} if blank else row, spec)


def split_name(name: str, fmt: str) -> dict[str, str | None]:
    """first/middle/last/suffix of a person's name printed in `fmt`; all None for as_is."""
    out: dict[str, str | None] = dict.fromkeys(PART_KEYS)
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


# --- csv_ranges -------------------------------------------------------------------------------


def window_lines(data: bytes, lo: int, hi: int, start: int, at_eof: bool) -> list[bytes]:
    """The complete lines of `data` (bytes from file offset `start`, at most lo - 1) that begin
    at an offset in [lo, hi). A line that starts before `lo` belongs to the previous window
    (data starts a byte early so a line beginning exactly at lo is seen); the last line is used
    only when it ends in a newline or at the end of the file."""
    pos = 0
    if lo > 0:
        nl = data.find(b"\n", lo - start - 1)
        if nl == -1:
            return []
        pos = nl + 1
    lines: list[bytes] = []
    while pos < len(data) and start + pos < hi:
        nl = data.find(b"\n", pos)
        if nl == -1:
            if at_eof:
                lines.append(data[pos:])
            break
        lines.append(data[pos : nl + 1])
        pos = nl + 1
    return lines


class RangeClient(PoliteClient):
    """PoliteClient plus GET with a Range header (same robots.txt, spacing and retries)."""

    def get_range(self, url: str, first: int, last: int) -> Response:
        rng = f"bytes={first}-{last}"
        return self._send(url, lambda hdrs: self.transport(url, {**hdrs, "Range": rng},
                                                           self.timeout_s))  # fmt: skip


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
        return str(c["html"].get("index") or c["html"]["url"])

    def source_row(self) -> Mapping[str, Any]:
        c = self.config
        t = c["terms"]
        return {
            "source_id": c.source_id,
            "kind": c["kind"],
            "jurisdiction": str(c["jurisdiction"]),
            "access_method": ACCESS[c.api],
            "base_url": self.base_url,
            "terms_url": t["url"],
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t["checked_on"],
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
            elif c.api == "csv_ranges":
                url = self.current_csv_url()
                head = self.client.get_range(url, 0, 4095)
                line = head.content.split(b"\n", 1)[0].decode("utf-8-sig", errors="replace")
                shape = tuple(sorted(next(csv.reader([line])))) if head.status == 206 else ()
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
