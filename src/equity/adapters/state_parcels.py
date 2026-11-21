"""Config-driven statewide parcel adapters: one YAML file per state in config/states/.

Every free statewide parcel layer differs only in where it lives and what it calls things, so
each state is data, not code. A config names the ArcGIS layer, how to split it into counties,
and which source field holds each canonical attribute. The adapter class for each config is
built at import time and registered like any hand-written adapter.

Config keys (see config/states/README.md):
  source_id, state, layer_url, order_by, page_size, min_interval_s, terms{...},
  county: {field, format: fips3|fips5|int|name|code_map, code_map: {...}} | {constant: fips3}
  fields: {parcel_id, owner1, owner2, mail_line1, mail_line2, mail_city, mail_state, mail_zip,
           land_value, bldg_value, total_value, assessed_value, tax_year, deed_book, deed_page}
           each value a source field name, or {const: value}
  value_basis: what the source's value fields mean (free text, recorded in source terms)
  assessment_valid_from: tax_year_jan1 | prior_july1
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, ClassVar

import yaml

from equity.adapters.arcgis import ArcGISQuery, fetch_all, get_json
from equity.adapters.arcgis_adapter import ArcGISCountyAdapter
from equity.adapters.base import Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.config import CONFIG_DIR
from equity.geo import County, counties_in, county_by_fips, county_by_name, state_fips
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

STATES_DIR = CONFIG_DIR / "states"
# Same format, one file per county, for states without a free statewide layer.
COUNTIES_DIR = CONFIG_DIR / "counties"
CANONICAL = (
    "parcel_id", "owner1", "owner2", "mail_line1", "mail_line2", "mail_full",
    "mail_city_state_zip", "mail_city", "mail_state", "mail_zip", "land_value", "bldg_value",
    "total_value", "assessed_value", "tax_year", "deed_book", "deed_page", "deed_ref",
    "situs_line1", "situs_full", "situs_city", "situs_state", "situs_zip",
    "owner_type", "homestead", "land_use_code", "land_use_desc", "zoning",
)  # fmt: skip
# Situs addresses are often the owner's home: pseudonymized in fixtures like mailing addresses.
PII_CANONICAL = ("owner1", "owner2", "mail_line1", "mail_line2", "mail_full",
                 "situs_line1", "situs_full")  # fmt: skip
_TRUE = {"Y", "YES", "T", "TRUE", "H", "HX", "HOMESTEAD", "ENROLLED"}
_FALSE = {"N", "NO", "F", "FALSE", "NOT ENROLLED", "NON-HOMESTEAD", "NON HOMESTEAD", "NONHOMESTEAD"}


def parse_homestead(value: Any) -> bool | None:
    """Homestead flag from a roll field: a positive amount (e.g. Florida's homestead just
    value) or a yes/no code is True/False; anything else is unknown (None), never guessed."""
    text = _text(value)
    if text is None:
        return None
    up = text.upper()
    if up in _TRUE:
        return True
    if up in _FALSE:
        return False
    try:
        return float(up.replace(",", "").replace("$", "")) > 0
    except ValueError:
        return None


# One-string postal address: "LINE , CITY, ST 12345[-6789]". Without the comma layout the
# whole string stays as the street line: we never guess where a street ends and a city begins.
_FULL = re.compile(
    r"^(?P<line>.+?)\s*,\s*(?P<city>[^,]+?)\s*,\s*"
    r"(?P<st>[A-Za-z]{2})\s+(?P<zip>\d{5})(?:-?\d{4})?\s*$"
)


_CSZ = re.compile(r"^(?P<city>.+?)[,\s]+(?P<st>[A-Za-z]{2})\s+(?P<zip>\d{5})(?:-?\d{4})?\s*$")


def parse_city_state_zip(text: str) -> tuple[str | None, str | None, str | None]:
    """'WASHINGTON DC 20001-1234' / 'Austin, TX 78701' -> (city, state, zip5). The field holds
    only city/state/ZIP, so everything before the 2-letter state is the city."""
    m = _CSZ.match(text.strip())
    if m is None:
        return None, None, None
    return " ".join(m.group("city").split()).rstrip(","), m.group("st").upper(), m.group("zip")


def normalized_address(
    street: str | None, city: str | None, state: str | None, zip5: str | None
) -> dict[str, Any] | None:
    """An address row holds only normalized parts, so one norm_key always means one content.
    The raw text stays in the source record."""
    parts = [clean(x or "") or None for x in (street, city, state)]
    if not (parts[0] or parts[1] or zip5):
        return None
    norm_key = "|".join(p or "" for p in (*parts, zip5))
    return {"address_id": stable_id("address", norm_key), "line1": parts[0], "line2": None,
            "city": parts[1], "state": parts[2], "zip5": zip5, "norm_key": norm_key}  # fmt: skip


def parse_full_address(text: str) -> tuple[str, str | None, str | None, str | None]:
    """-> (line, city, state, zip5)."""
    m = _FULL.match(text)
    if m is None:
        return " ".join(text.split()), None, None, None
    return (" ".join(m.group("line").split()), " ".join(m.group("city").split()),
            m.group("st").upper(), m.group("zip"))  # fmt: skip


_ZIP = re.compile(r"^\s*(\d{5})")
_NULLS = {"", "NULL", "NONE", "N/A", "<NULL>"}


class StateConfigError(ValueError):
    pass


@dataclass(frozen=True)
class LayerSpec:
    url: str
    # Per-layer county rule (e.g. one layer per county: {constant: "001"}); None = config's.
    county: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class StateConfig:
    path: Path
    source_id: str
    state: str
    layer_url: str
    order_by: str
    page_size: int
    min_interval_s: float
    county: Mapping[str, Any]
    fields: Mapping[str, Any]
    terms: Mapping[str, Any]
    value_basis: str
    assessment_valid_from: str = "tax_year_jan1"
    extra_pii: tuple[str, ...] = field(default_factory=tuple)
    # Published limits on use (e.g. no_mailing_list, no_resale). Recorded in source terms so
    # exports that would violate them can be blocked.
    use_restrictions: tuple[str, ...] = field(default_factory=tuple)
    layers: tuple[LayerSpec, ...] = ()
    paginate: bool = True
    # Fixed where clause ANDed into every query (e.g. "ROLL_YEAR = 2026" for layers that keep
    # one row per parcel per year).
    base_filter: str | None = None
    # Regex with named groups `book` and `page` for a combined deed reference ("282 - 520").
    deed_ref_pattern: str | None = None
    # Split the layer into object-id windows of this many ids instead of one request per
    # county, for layers whose counties are too big to fetch in one go (Florida). The county
    # still comes from each row's county field.
    partition_window: int | None = None
    # Split each county into object-id windows of this many ids (one stats query per county
    # at plan time), so a big county is many small fetches instead of one long one.
    county_window: int | None = None

    def layer(self, index: int) -> LayerSpec:
        return self.layers[index] if self.layers else LayerSpec(self.layer_url)

    @property
    def layer_count(self) -> int:
        return len(self.layers) or 1

    def county_spec(self, index: int) -> Mapping[str, Any]:
        return self.layer(index).county or self.county

    @property
    def state_fips(self) -> str:
        return state_fips(self.state)

    def source_field(self, canonical: str) -> str | None:
        spec = self.fields.get(canonical)
        return spec if isinstance(spec, str) else None

    @property
    def source_fields(self) -> tuple[str, ...]:
        names = {self.order_by}
        names |= {v for v in self.fields.values() if isinstance(v, str)}
        names |= {str(x) for v in self.fields.values() if isinstance(v, list) for x in v}
        names |= {str(v["year_of"]) for v in self.fields.values()
                  if isinstance(v, dict) and "year_of" in v}  # fmt: skip
        for i in range(self.layer_count):
            spec = self.county_spec(i)
            if "field" in spec:
                names.add(str(spec["field"]))
        return tuple(sorted(names))

    @property
    def pii_fields(self) -> tuple[str, ...]:
        mapped = [self.source_field(c) for c in PII_CANONICAL]
        return tuple(sorted({m for m in mapped if m} | set(self.extra_pii)))


def load_config(path: Path) -> StateConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise StateConfigError(f"{path.name}: expected a mapping")
    required = ("source_id", "state", "order_by", "county", "fields", "terms", "value_basis")
    missing = [k for k in required if k not in data]
    if "layer_url" not in data and "layers" not in data:
        missing.append("layer_url or layers")
    if missing:
        raise StateConfigError(f"{path.name}: missing {missing}")
    layers: list[LayerSpec] = []
    for item in data.get("layers") or []:
        if isinstance(item, str):
            layers.append(LayerSpec(item.rstrip("/")))
        elif isinstance(item, dict) and "url" in item:
            layers.append(LayerSpec(str(item["url"]).rstrip("/"), item.get("county")))
        else:
            raise StateConfigError(f"{path.name}: each layer is a URL or {{url, county}}")
    unknown = set(data["fields"]) - set(CANONICAL)
    if unknown:
        raise StateConfigError(f"{path.name}: unknown canonical fields {sorted(unknown)}")
    if "parcel_id" not in data["fields"]:
        raise StateConfigError(f"{path.name}: fields.parcel_id is required")
    pattern = data.get("deed_ref_pattern")
    if "deed_ref" in data["fields"]:
        if not pattern:
            raise StateConfigError(f"{path.name}: fields.deed_ref needs deed_ref_pattern")
        if not {"book", "page"} <= set(re.compile(pattern).groupindex):
            raise StateConfigError(f"{path.name}: deed_ref_pattern needs named groups book, page")
    county = data["county"]
    if not ("constant" in county or ("field" in county and "format" in county)):
        raise StateConfigError(f"{path.name}: county needs constant, or field + format")
    if county.get("format") == "code_map" and not isinstance(county.get("code_map"), dict):
        raise StateConfigError(f"{path.name}: county.format code_map needs county.code_map")
    for key in ("summary", "checked_on", "cost_model"):
        if key not in data["terms"]:
            raise StateConfigError(f"{path.name}: terms.{key} is required")
    state_fips(data["state"])  # validates the state code
    return StateConfig(
        path=path,
        source_id=str(data["source_id"]),
        state=str(data["state"]).upper(),
        layer_url=str(data.get("layer_url") or layers[0].url).rstrip("/"),
        order_by=str(data["order_by"]),
        page_size=int(data.get("page_size", 1000)),
        min_interval_s=float(data.get("min_interval_s", 1.0)),
        county=county,
        fields=data["fields"],
        terms=data["terms"],
        value_basis=str(data["value_basis"]),
        assessment_valid_from=str(data.get("assessment_valid_from", "tax_year_jan1")),
        extra_pii=tuple(data.get("extra_pii", ())),
        use_restrictions=tuple(sorted(data.get("use_restrictions", ()))),
        layers=tuple(layers),
        paginate=bool(data.get("paginate", True)),
        base_filter=data.get("filter"),
        deed_ref_pattern=data.get("deed_ref_pattern"),
        partition_window=int(data["partition_window"]) if "partition_window" in data else None,
        county_window=int(data["county_window"]) if "county_window" in data else None,
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    s = " ".join(str(value).split())
    return None if s.upper() in _NULLS else s


def _money(value: Any) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        amount = float(str(value).replace(",", "").replace("$", ""))
    except ValueError:
        return None
    return None if amount < 0 else f"{amount:.2f}"


def norm_parcel_id(raw: str) -> str:
    """Uppercase, whitespace removed; punctuation kept (it is meaningful in many states)."""
    return re.sub(r"\s+", "", raw.upper())


def _valid_from(tax_year: int, rule: str) -> date:
    if rule == "tax_year_jan1":
        return date(tax_year, 1, 1)
    if rule == "prior_july1":
        return date(tax_year - 1, 7, 1)
    raise StateConfigError(f"unknown assessment_valid_from {rule!r}")


class StateParcelAdapter(ArcGISCountyAdapter):
    config: ClassVar[StateConfig]
    adapter_version: ClassVar[str] = "1"

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.params = {"page_size": self.config.page_size}
        self.client = client or PoliteClient(min_interval_s=self.config.min_interval_s)

    def source_row(self) -> Mapping[str, Any]:
        t = self.config.terms
        return {
            "source_id": self.source_id,
            "kind": "parcel_statewide",
            "jurisdiction": self.config.state_fips,
            "access_method": "arcgis",
            "base_url": self.config.layer_url,
            "terms_url": t.get("url"),
            "terms_summary": (
                (
                    f"RESTRICTED[{','.join(self.config.use_restrictions)}] "
                    if self.config.use_restrictions
                    else ""
                )
                + f"{t['summary']} | values: {self.config.value_basis}"
            ),
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t.get("robots_checked_on", t["checked_on"]),
            "cost_model": t["cost_model"],
        }

    # -- partitioning -------------------------------------------------------------------
    def county_of(self, attrs: Mapping[str, Any], layer: int = 0) -> County:
        spec = self.config.county_spec(layer)
        st = self.config.state
        if "constant" in spec:
            return county_by_fips(st, str(spec["constant"]))
        raw = attrs.get(str(spec["field"]))
        text = _text(raw)
        if text is None:
            raise KeyError("county field is empty")
        fmt = spec["format"]
        if fmt in ("fips3", "fips5", "int"):
            return county_by_fips(st, text.split(".")[0])
        if fmt == "name":
            return county_by_name(st, text)
        if fmt == "code_map":
            code_map = {str(k): str(v) for k, v in spec["code_map"].items()}
            if text not in code_map:
                raise KeyError(f"county code {text!r} not in code_map")
            return county_by_fips(st, code_map[text])
        raise StateConfigError(f"unknown county format {fmt!r}")

    def where(self, request: FetchRequest) -> str:
        """Partition clause, ANDed with the config's fixed filter when there is one."""
        clause = self._partition_where(request)
        if self.config.base_filter:
            return f"({self.config.base_filter}) AND ({clause})"
        return clause

    def _partition_where(self, request: FetchRequest) -> str:
        """params: county_fips (3 digits) and/or oid_min + oid_max | sample=1 (fixtures)."""
        p = request.params
        clauses = []
        if "county_fips" in p:
            clauses.append(self._county_clause(p["county_fips"], int(p.get("layer", "0"))))
        if "oid_min" in p and "oid_max" in p:
            lo, hi = int(p["oid_min"]), int(p["oid_max"])
            clauses.append(f"{self.config.order_by}>={lo} AND {self.config.order_by}<{hi}")
        if len(clauses) == 2 and clauses[0] == "1=1":
            clauses = clauses[1:]
        if clauses:
            return " AND ".join(f"({c})" for c in clauses) if len(clauses) > 1 else clauses[0]
        if p.get("sample"):
            return "1=1"
        raise StateConfigError("need county_fips, oid_min/oid_max, or sample")

    def _county_clause(self, county_fips: str, layer: int) -> str:
        spec = self.config.county_spec(layer)
        county = county_by_fips(self.config.state, county_fips)
        if "constant" in spec:
            return "1=1"
        fld, fmt = str(spec["field"]), spec["format"]
        if fmt == "fips3":
            return f"{fld}='{county.county_fips}'"
        if fmt == "fips5":
            return f"{fld}='{county.fips5}'"
        if fmt == "int":
            return f"{fld}={int(county.county_fips)}"
        if fmt == "name":
            raise StateConfigError("name-partitioned layers are fetched by oid range")
        codes = [k for k, v in spec["code_map"].items() if str(v) == county.county_fips]
        q = "" if spec.get("numeric") else "'"  # integer code fields reject quoted literals
        return " OR ".join(f"{fld}={q}{c}{q}" for c in codes) or "1=0"

    def split_partition(self, params: Mapping[str, str]) -> list[dict[str, str]]:
        """A county partition cut into windows of county_window records each, from the
        county's actual object-id list (one returnIdsOnly query), so no window is empty even
        when ids are scattered. Anything else, or a config without county_window, comes back
        unchanged."""
        size = self.config.county_window
        if not size or "county_fips" not in params or "oid_min" in params:
            return [dict(params)]
        layer = int(params.get("layer", "0"))
        where = self._county_clause(params["county_fips"], layer)
        if self.config.base_filter:
            where = f"({self.config.base_filter}) AND ({where})"
        q = {"where": where, "returnIdsOnly": "true", "f": "json"}
        body = get_json(self.client, self.config.layer(layer).url + "/query", q)
        if "error" in body:
            raise StateConfigError(f"id list for county {params['county_fips']}: {body['error']}")
        ids = sorted(int(i) for i in body.get("objectIds") or [])
        out: list[dict[str, str]] = []
        for i in range(0, len(ids), size):
            chunk = ids[i : i + size]
            out.append({**params, "oid_min": str(chunk[0]), "oid_max": str(chunk[-1] + 1)})
        return out

    def partitions(self, window: int = 50_000) -> Iterator[dict[str, str]]:
        """Fetch plan for the whole state, per layer: one request per county when the layer
        has a county code to filter on, otherwise object-id windows (one stats query each).
        Without server paging, windows are capped at page_size."""
        if self.config.partition_window:
            window = self.config.partition_window
        if not self.config.paginate:
            window = min(window, self.config.page_size)
        for i in range(self.config.layer_count):
            spec = self.config.county_spec(i)
            base = {"layer": str(i)} if self.config.layers else {}
            by_county = spec.get("format") in ("fips3", "fips5", "int", "code_map")
            if by_county and self.config.paginate and not self.config.partition_window:
                for c in counties_in(self.config.state):
                    yield from self.split_partition({**base, "county_fips": c.county_fips})
                continue
            oid = self.config.order_by
            stats = json.dumps([
                {"statisticType": "min", "onStatisticField": oid, "outStatisticFieldName": "lo"},
                {"statisticType": "max", "onStatisticField": oid, "outStatisticFieldName": "hi"},
            ])  # fmt: skip
            url = self.config.layer(i).url
            params = {
                "where": self.config.base_filter or "1=1",
                "outStatistics": stats,
                "f": "json",
            }
            body = get_json(self.client, url + "/query", params)
            if "features" not in body:
                # Some servers (e.g. MARIS for Mississippi) refuse statistics queries but answer
                # returnIdsOnly. Cut windows from the id list instead; fail only if both refuse.
                ids = self._id_list(url)
                if ids is None:
                    raise StateConfigError(
                        f"id range for {url}: {body.get('error', body)}; id list refused too"
                    )
                yield from ({**base, **w} for w in _id_windows(ids, window))
                continue
            raw_attrs = body["features"][0]["attributes"]
            attrs = {str(k).lower(): v for k, v in raw_attrs.items()}  # some servers upper-case
            lo, hi = int(attrs["lo"]), int(attrs["hi"])
            count = self._count(url)
            if count and (hi - lo + 1) > 4 * count:
                # Sparse ids: fixed-width windows would be mostly empty. Cut windows from the
                # actual id list instead (one returnIdsOnly request).
                yield from ({**base, **w} for w in self._dense_windows(url, window))
                continue
            for start in range(lo, hi + 1, window):
                yield {**base, "oid_min": str(start), "oid_max": str(start + window)}

    def _count(self, url: str) -> int:
        params = {"where": self.config.base_filter or "1=1", "returnCountOnly": "true", "f": "json"}
        resp = self.client.get(url + "/query", params)
        return int(json.loads(resp.content).get("count") or 0)

    def _id_list(self, url: str) -> list[int] | None:
        """Every object id in the layer (one returnIdsOnly request), or None if refused."""
        params = {"where": self.config.base_filter or "1=1", "returnIdsOnly": "true", "f": "json"}
        body = get_json(self.client, url + "/query", params)
        if "error" in body:
            return None
        return sorted(int(i) for i in body.get("objectIds") or [])

    def _dense_windows(self, url: str, window: int) -> Iterator[dict[str, str]]:
        ids = self._id_list(url)
        if ids is None:
            raise StateConfigError(f"id list for {url} refused")
        yield from _id_windows(ids, window)

    def fetch(self, request: FetchRequest) -> Fetched:
        """Like the base fetch, but on the requested layer and honoring `paginate`."""
        index = int(request.params.get("layer", "0"))
        url = self.config.layer(index).url
        limit = request.params.get("limit")
        page = int(limit) if limit is not None else self.config.page_size
        q = ArcGISQuery(url, self.where(request), self.fields, self.order_by, page,
                        paginate=self.config.paginate)  # fmt: skip
        features, responses = fetch_all(
            self.client, q, max_pages=1 if limit else 10_000, sample=limit is not None
        )
        body = canonical_json({"layer": url, "where": q.where,
                               "attributes": [f["attributes"] for f in features]})  # fmt: skip
        return Fetched(self.source_id, f"{url}/query?where={q.where}",
                       responses[-1].retrieved_at, 200, body, "application/json")  # fmt: skip

    def health(self) -> HealthReport:
        """Live: the first layer answers a tiny query with every mapped field present."""
        oid = self.config.order_by
        where = "1=1" if self.config.paginate else f"{oid} IN (0, 1, 2)"
        q = ArcGISQuery(self.config.layer(0).url, where, self.fields, self.order_by, 1,
                        paginate=self.config.paginate)  # fmt: skip
        try:
            resp = self.client.get(q.layer_url + "/query", q.params(0))
            feats = json.loads(resp.content).get("features") or []
        except (ValueError, OSError) as exc:
            return HealthReport(self.source_id, False, self.client.now(), repr(exc))
        shape = tuple(sorted(feats[0]["attributes"])) if feats else ()
        ok = resp.status == 200 and shape == tuple(sorted(self.fields))
        detail = "ok" if ok else f"status={resp.status} fields={list(shape)}"
        return HealthReport(self.source_id, ok, self.client.now(), detail, shape)

    def layer_of(self, fetched: Fetched) -> int:
        matches = [i for i in range(self.config.layer_count)
                   if fetched.request.startswith(self.config.layer(i).url + "/")]  # fmt: skip
        return matches[0] if matches else 0

    # -- normalization ------------------------------------------------------------------
    def _get(self, attrs: Mapping[str, Any], canonical: str) -> Any:
        spec = self.config.fields.get(canonical)
        if isinstance(spec, dict) and "const" in spec:
            return spec["const"]
        if isinstance(spec, dict) and "year_of" in spec:
            # Year of an ArcGIS date field (epoch milliseconds, UTC).
            ms = attrs.get(str(spec["year_of"]))
            if ms is None:
                return None
            return datetime.fromtimestamp(int(ms) / 1000, tz=UTC).year
        if isinstance(spec, str):
            return attrs.get(spec)
        if isinstance(spec, list):
            # Composite key, e.g. [TOWN_ID, PROP_ID]: all parts required, joined with '-'.
            parts = [_text(attrs.get(str(f))) for f in spec]
            return None if any(p is None for p in parts) else "-".join(str(p) for p in parts)
        return None

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = self.config
        layer = self.layer_of(fetched)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        groups: dict[str, list[Mapping[str, Any]]] = {}
        for attrs in self.attributes(fetched):
            pid = _text(self._get(attrs, "parcel_id"))
            if pid is not None:
                groups.setdefault(norm_parcel_id(pid), []).append(attrs)
        for local_id in sorted(groups):
            # Multipart/duplicate rows: the lowest order_by value wins, deterministically.
            a = min(
                groups[local_id],
                key=lambda x: (x.get(cfg.order_by) is None, str(x.get(cfg.order_by)).zfill(20)),
            )
            try:
                county = self.county_of(a, layer)
            except KeyError:
                continue  # no county, no stable key: skip rather than guess
            uid = f"{county.fips5}-{local_id}"
            ctx = RecordContext(fetched, county.fips5, local_id, "parcel", dict(a))
            yield ctx.source_record()
            situs = self._situs(a)
            if situs is not None:
                yield NormalizedRow("address", situs)
            situs_id = None if situs is None else situs["address_id"]
            yield ctx.fact("parcel", parcel_uid=uid, parid_raw=local_id, situs_address_id=situs_id,
                           land_use_code=_text(self._get(a, "land_use_code")),
                           land_use_desc=_text(self._get(a, "land_use_desc")),
                           zoning=_text(self._get(a, "zoning")))  # fmt: skip
            addr = self._address(a)
            if addr is not None:
                yield NormalizedRow("address", addr)
            owners = [n for n in (_text(self._get(a, "owner1")), _text(self._get(a, "owner2")))
                      if n]  # fmt: skip
            owner_type = _text(self._get(a, "owner_type"))
            for seq, name in enumerate(owners, start=1):
                nc = classify(name)
                party_id = stable_id(self.source_id, local_id, "owner", str(seq), clean(name))
                yield ctx.fact("party", party_id=party_id, raw_name=name,
                               party_kind=nc.party_kind, org_form=nc.org_form,
                               org_name_norm=nc.org_name_norm,
                               address_id=None if addr is None else addr["address_id"])  # fmt: skip
                book, page = self._deed(a)
                yield ctx.fact("owner_snapshot", parcel_uid=uid, owner_seq=seq,
                               party_id=party_id, deed_book=book, deed_page=page,
                               owner_type=owner_type, observed_on=observed)  # fmt: skip
            year_raw = _text(self._get(a, "tax_year"))
            values = {
                "appraised_land": _money(self._get(a, "land_value")),
                "appraised_bldg": _money(self._get(a, "bldg_value")),
                "appraised_total": _money(self._get(a, "total_value")),
                "assessed_value": _money(self._get(a, "assessed_value")),
            }
            if year_raw and year_raw.split(".")[0].isdigit() and any(values.values()):
                year = int(year_raw.split(".")[0])
                if 1800 <= year <= 2200:
                    yield ctx.fact("parcel_assessment", parcel_uid=uid, tax_year=year,
                                   valid_from=_valid_from(year, cfg.assessment_valid_from),
                                   homestead=parse_homestead(self._get(a, "homestead")),
                                   **values)  # fmt: skip

    def _deed(self, a: Mapping[str, Any]) -> tuple[str | None, str | None]:
        book, page = _text(self._get(a, "deed_book")), _text(self._get(a, "deed_page"))
        ref = _text(self._get(a, "deed_ref"))
        if ref and self.config.deed_ref_pattern and not (book or page):
            m = re.search(self.config.deed_ref_pattern, ref)
            if m:  # no match: leave both empty rather than guess
                book, page = m.group("book"), m.group("page")
        return book, page

    def _situs(self, a: Mapping[str, Any]) -> dict[str, Any] | None:
        """The property's own address. A one-string situs is split only when it carries the
        'LINE, CITY, ST ZIP' layout; otherwise it is kept whole as the street line."""
        spec = self.config.fields.get("situs_line1")
        if isinstance(spec, list):  # house number, prefix, street, suffix: joined, gaps skipped
            line = _text(" ".join(p for p in (_text(a.get(str(f))) for f in spec) if p))
        else:
            line = _text(self._get(a, "situs_line1"))
        city, st = _text(self._get(a, "situs_city")), _text(self._get(a, "situs_state"))
        m = _ZIP.match(str(self._get(a, "situs_zip") or ""))
        zip5 = m.group(1) if m else None
        full = _text(self._get(a, "situs_full"))
        if full and not (line or city or zip5):
            line, city, st, zip5 = parse_full_address(full)
        if not (line or city or zip5):
            return None
        return normalized_address(line, city, st or self.config.state, zip5)

    def _address(self, a: Mapping[str, Any]) -> dict[str, Any] | None:
        lines = [x for x in (_text(self._get(a, "mail_line1")), _text(self._get(a, "mail_line2")))
                 if x]  # fmt: skip
        city, st = _text(self._get(a, "mail_city")), _text(self._get(a, "mail_state"))
        m = _ZIP.match(str(self._get(a, "mail_zip") or ""))
        zip5 = m.group(1) if m else None
        csz = _text(self._get(a, "mail_city_state_zip"))
        if csz and not (city or zip5):
            city, st, zip5 = parse_city_state_zip(csz)
        full = _text(self._get(a, "mail_full"))
        if full and not (lines or city or zip5):
            line, city, st, zip5 = parse_full_address(full)
            lines = [line]
        if not (lines or city or zip5):
            return None
        return normalized_address(" ".join(lines), city, st, zip5)


def adapter_for(cfg: StateConfig) -> type[StateParcelAdapter]:
    name = "Parcels_" + cfg.source_id.replace(".", "_")
    return type(
        name,
        (StateParcelAdapter,),
        {
            "config": cfg,
            "source_id": cfg.source_id,
            "layer_url": cfg.layer_url,
            "fields": cfg.source_fields,
            "order_by": (cfg.order_by,),
            "pii_fields": cfg.pii_fields,
            "health_where": "1=1",
            "__module__": __name__,
        },
    )


def config_paths(*dirs: Path) -> list[Path]:
    return [p for d in (dirs or (STATES_DIR, COUNTIES_DIR)) for p in sorted(d.glob("*.yaml"))]


def all_state_adapters(*dirs: Path) -> list[type[StateParcelAdapter]]:
    return [adapter_for(load_config(p)) for p in config_paths(*dirs)]


def _id_windows(ids: list[int], window: int) -> Iterator[dict[str, str]]:
    """Half-open oid windows holding at most `window` actual ids each."""
    for i in range(0, len(ids), window):
        chunk = ids[i : i + window]
        yield {"oid_min": str(chunk[0]), "oid_max": str(chunk[-1] + 1)}
