"""Zoning district polygons from state and regional zoning layers on ArcGIS.

One YAML file per layer group in config/zoning/. Each file names the layer(s), which
attribute holds the jurisdiction, zone code, description and generalized class, and the
terms as checked. Every attribute the layer publishes is kept in the raw response; the fact
row carries the four common fields plus the polygon (ArcGIS rings, EPSG:4326) and its
bounding box, so parcels can later be placed in a district with a point-in-polygon test.

Sources and licenses are documented in docs/sources/zoning-sources.md.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import yaml

from equity.adapters.arcgis import ArcGISQuery, fetch_all, get_json
from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import _id_windows
from equity.config import CONFIG_DIR
from equity.geo import state_fips

ZONING_DIR = CONFIG_DIR / "zoning"
FIELDS = ("jurisdiction", "zone_code", "zone_desc", "zone_class")
REQUIRED = ("source_id", "state", "layers", "fields", "terms")
DIGITS = 6  # ~0.1 m at the equator: plenty for district boundaries, and keeps rows small


class ZoningConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ZoningConfig:
    source_id: str
    state: str
    layers: tuple[str, ...]
    fields: Mapping[str, str]
    terms: Mapping[str, Any]
    order_by: str = "OBJECTID"
    page_size: int = 1000
    min_interval_s: float = 1.0

    @property
    def state_fips(self) -> str:
        return state_fips(self.state)


def load_zoning_config(path: Path) -> ZoningConfig:
    data = yaml.safe_load(path.read_text())
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ZoningConfigError(f"{path.name}: missing {missing}")
    unknown = set(data["fields"]) - set(FIELDS)
    if unknown:
        raise ZoningConfigError(f"{path.name}: unknown fields {sorted(unknown)}")
    for key in ("summary", "checked_on", "cost_model"):
        if key not in data["terms"]:
            raise ZoningConfigError(f"{path.name}: terms.{key} is required")
    cfg = ZoningConfig(
        source_id=data["source_id"],
        state=data["state"],
        layers=tuple(data["layers"]),
        fields=dict(data["fields"]),
        terms=dict(data["terms"]),
        order_by=data.get("order_by", "OBJECTID"),
        page_size=int(data.get("page_size", 1000)),
        min_interval_s=float(data.get("min_interval_s", 1.0)),
    )
    cfg.state_fips  # noqa: B018 - raises KeyError on an unknown state
    if not cfg.source_id.endswith(".zoning"):
        raise ZoningConfigError(f"{path.name}: source_id must end with .zoning")
    return cfg


def _ring_box(rings: Sequence[Sequence[Sequence[float]]]) -> tuple[float, float, float, float]:
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    return min(xs), min(ys), max(xs), max(ys)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


class ZoningAdapter(Adapter):
    config: ClassVar[ZoningConfig]
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "arcgis"
    pii_fields: ClassVar[tuple[str, ...]] = ()  # district polygons hold no personal data

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=self.config.min_interval_s)

    def source_row(self) -> Mapping[str, Any]:
        t = self.config.terms
        return {
            "source_id": self.source_id,
            "kind": "zoning",
            "jurisdiction": self.config.state_fips,
            "access_method": "arcgis",
            "base_url": self.config.layers[0],
            "terms_url": t.get("url"),
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t.get("robots_checked_on", t["checked_on"]),
            "cost_model": t["cost_model"],
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        """Windows of at most page_size actual object ids per layer (one returnIdsOnly call)."""
        for i, url in enumerate(self.config.layers):
            body = get_json(self.client, url + "/query",
                            {"where": "1=1", "returnIdsOnly": "true", "f": "json"})  # fmt: skip
            if "error" in body:
                raise ZoningConfigError(f"id list for {url}: {body['error']}")
            ids = sorted(int(x) for x in body.get("objectIds") or [])
            for w in _id_windows(ids, self.config.page_size):
                yield {"layer": str(i), **w}

    def where(self, request: FetchRequest) -> str:
        p = request.params
        if "oid_min" in p:
            oid = self.config.order_by
            return f"{oid}>={int(p['oid_min'])} AND {oid}<{int(p['oid_max'])}"
        return "1=1"

    def fetch(self, request: FetchRequest) -> Fetched:
        url = self.config.layers[int(request.params.get("layer", "0"))]
        limit = request.params.get("limit")
        page = int(limit) if limit is not None else self.config.page_size
        q = ArcGISQuery(url, self.where(request), ("*",), (self.config.order_by,), page,
                        return_geometry=True)  # fmt: skip
        features, responses = fetch_all(
            self.client, q, max_pages=1 if limit else 10_000, sample=limit is not None
        )
        body = canonical_json({"layer": url, "where": q.where, "features": features})
        return Fetched(self.source_id, f"{url}/query?where={q.where}",
                       responses[-1].retrieved_at, 200, body, "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        layer = (
            self.config.layers.index(data["layer"]) if data["layer"] in self.config.layers else 0
        )
        f = self.config.fields
        for feat in data.get("features") or []:
            attrs = feat.get("attributes") or {}
            rings = (feat.get("geometry") or {}).get("rings") or []
            rings = [[[round(x, DIGITS), round(y, DIGITS)] for x, y, *_ in r] for r in rings if r]
            oid = attrs.get(self.config.order_by)
            if not rings or oid is None:
                continue  # no shape or no stable key: skip rather than guess
            uid = f"{layer}-{int(oid)}"
            ctx = RecordContext(fetched, self.config.state_fips, uid, "zoning_district", attrs)
            xmin, ymin, xmax, ymax = _ring_box(rings)
            mapped = {k: _text(attrs.get(f[k])) if k in f else None for k in FIELDS}
            yield ctx.source_record()
            yield ctx.fact(
                "zoning_district",
                zone_uid=uid,
                jurisdiction_name=mapped["jurisdiction"],
                zone_code=mapped["zone_code"],
                zone_desc=mapped["zone_desc"],
                zone_class=mapped["zone_class"],
                geom_rings=json.dumps(rings, separators=(",", ":")),
                xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax,
            )  # fmt: skip

    def health(self) -> HealthReport:
        url = self.config.layers[0]
        body = get_json(self.client, url + "/query",
                        {"where": "1=1", "returnCountOnly": "true", "f": "json"})  # fmt: skip
        n = int(body.get("count") or 0)
        return HealthReport(self.source_id, n > 0, datetime.now(UTC), f"{n} districts on layer 0")


def zoning_adapter_for(cfg: ZoningConfig) -> type[ZoningAdapter]:
    name = "Zoning_" + cfg.source_id.replace(".", "_")
    return type(name, (ZoningAdapter,),
                {"config": cfg, "source_id": cfg.source_id, "__module__": __name__})  # fmt: skip


def all_zoning_adapters(directory: Path = ZONING_DIR) -> list[type[ZoningAdapter]]:
    return [zoning_adapter_for(load_zoning_config(p)) for p in sorted(directory.glob("*.yaml"))]
