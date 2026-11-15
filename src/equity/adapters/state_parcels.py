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

from equity.adapters.arcgis_adapter import ArcGISCountyAdapter
from equity.adapters.base import Fetched, FetchRequest, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext
from equity.config import CONFIG_DIR
from equity.geo import County, counties_in, county_by_fips, county_by_name, state_fips
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

STATES_DIR = CONFIG_DIR / "states"
CANONICAL = (
    "parcel_id", "owner1", "owner2", "mail_line1", "mail_line2", "mail_city", "mail_state",
    "mail_zip", "land_value", "bldg_value", "total_value", "assessed_value", "tax_year",
    "deed_book", "deed_page",
)  # fmt: skip
PII_CANONICAL = ("owner1", "owner2", "mail_line1", "mail_line2")
_ZIP = re.compile(r"^\s*(\d{5})")
_NULLS = {"", "NULL", "NONE", "N/A", "<NULL>"}


class StateConfigError(ValueError):
    pass


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
        names |= {str(v["year_of"]) for v in self.fields.values()
                  if isinstance(v, dict) and "year_of" in v}  # fmt: skip
        if "field" in self.county:
            names.add(str(self.county["field"]))
        return tuple(sorted(names))

    @property
    def pii_fields(self) -> tuple[str, ...]:
        mapped = [self.source_field(c) for c in PII_CANONICAL]
        return tuple(sorted({m for m in mapped if m} | set(self.extra_pii)))


def load_config(path: Path) -> StateConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise StateConfigError(f"{path.name}: expected a mapping")
    required = ("source_id", "state", "layer_url", "order_by", "county", "fields", "terms",
                "value_basis")  # fmt: skip
    missing = [k for k in required if k not in data]
    if missing:
        raise StateConfigError(f"{path.name}: missing {missing}")
    unknown = set(data["fields"]) - set(CANONICAL)
    if unknown:
        raise StateConfigError(f"{path.name}: unknown canonical fields {sorted(unknown)}")
    if "parcel_id" not in data["fields"]:
        raise StateConfigError(f"{path.name}: fields.parcel_id is required")
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
        layer_url=str(data["layer_url"]).rstrip("/"),
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
    def county_of(self, attrs: Mapping[str, Any]) -> County:
        spec = self.config.county
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
        """params: county_fips (3 digits) | oid_min + oid_max | sample=1 (fixtures)."""
        p = request.params
        spec = self.config.county
        if "county_fips" in p:
            county = county_by_fips(self.config.state, p["county_fips"])
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
            return " OR ".join(f"{fld}='{c}'" for c in codes) or "1=0"
        if "oid_min" in p and "oid_max" in p:
            lo, hi = int(p["oid_min"]), int(p["oid_max"])
            return f"{self.config.order_by}>={lo} AND {self.config.order_by}<{hi}"
        if p.get("sample"):
            return "1=1"
        raise StateConfigError("need county_fips, oid_min/oid_max, or sample")

    def partitions(self, window: int = 50_000) -> Iterator[dict[str, str]]:
        """Fetch plan for the whole state: one request per county when the layer has a
        county code we can filter on, otherwise object-id windows (one live stats query)."""
        spec = self.config.county
        if "constant" in spec or spec.get("format") in ("fips3", "fips5", "int", "code_map"):
            for c in counties_in(self.config.state):
                yield {"county_fips": c.county_fips}
            return
        oid = self.config.order_by
        stats = json.dumps([
            {"statisticType": "min", "onStatisticField": oid, "outStatisticFieldName": "lo"},
            {"statisticType": "max", "onStatisticField": oid, "outStatisticFieldName": "hi"},
        ])  # fmt: skip
        resp = self.client.get(self.layer_url + "/query",
                               {"where": "1=1", "outStatistics": stats, "f": "json"})  # fmt: skip
        attrs = json.loads(resp.content)["features"][0]["attributes"]
        lo, hi = int(attrs["lo"]), int(attrs["hi"])
        for start in range(lo, hi + 1, window):
            yield {"oid_min": str(start), "oid_max": str(start + window)}

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
        return None

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = self.config
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
                county = self.county_of(a)
            except KeyError:
                continue  # no county, no stable key: skip rather than guess
            uid = f"{county.fips5}-{local_id}"
            ctx = RecordContext(fetched, county.fips5, local_id, "parcel", dict(a))
            yield ctx.source_record()
            yield ctx.fact("parcel", parcel_uid=uid, parid_raw=local_id)
            addr = self._address(a)
            if addr is not None:
                yield NormalizedRow("address", addr)
            owners = [n for n in (_text(self._get(a, "owner1")), _text(self._get(a, "owner2")))
                      if n]  # fmt: skip
            for seq, name in enumerate(owners, start=1):
                nc = classify(name)
                party_id = stable_id(self.source_id, local_id, "owner", str(seq), clean(name))
                yield ctx.fact("party", party_id=party_id, raw_name=name,
                               party_kind=nc.party_kind, org_form=nc.org_form,
                               org_name_norm=nc.org_name_norm,
                               address_id=None if addr is None else addr["address_id"])  # fmt: skip
                yield ctx.fact("owner_snapshot", parcel_uid=uid, owner_seq=seq,
                               party_id=party_id, deed_book=_text(self._get(a, "deed_book")),
                               deed_page=_text(self._get(a, "deed_page")),
                               observed_on=observed)  # fmt: skip
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
                                   **values)  # fmt: skip

    def _address(self, a: Mapping[str, Any]) -> dict[str, Any] | None:
        lines = [x for x in (_text(self._get(a, "mail_line1")), _text(self._get(a, "mail_line2")))
                 if x]  # fmt: skip
        city, st = _text(self._get(a, "mail_city")), _text(self._get(a, "mail_state"))
        m = _ZIP.match(str(self._get(a, "mail_zip") or ""))
        zip5 = m.group(1) if m else None
        if not (lines or city or zip5):
            return None
        norm_key = "|".join(clean(x or "") for x in (" ".join(lines), city, st, zip5))
        return {"address_id": stable_id("address", norm_key), "line1": lines[0] if lines else None,
                "line2": " ".join(lines[1:]) or None, "city": city, "state": st, "zip5": zip5,
                "norm_key": norm_key}  # fmt: skip


def adapter_for(cfg: StateConfig) -> type[StateParcelAdapter]:
    name = "StateParcels_" + cfg.state
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


def all_state_adapters(states_dir: Path = STATES_DIR) -> list[type[StateParcelAdapter]]:
    return [adapter_for(load_config(p)) for p in sorted(states_dir.glob("*.yaml"))]
