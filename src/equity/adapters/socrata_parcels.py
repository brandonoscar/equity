"""Config-driven parcel-owner adapters for open-data JSON APIs: Socrata (SODA 2.x) and CKAN
datastore. One YAML file per source in config/socrata_parcels/<st>.<county>.parcels.yaml.

Some counties and cities publish owner names only as an open-data table, not as an ArcGIS
layer. The config vocabulary is the ArcGIS one (config/states/README.md, read by
state_parcels.load_config): the same `fields` canonical names (parcel_id, owner1, owner2,
mail_*, situs_*, values, tax_year...), `county`, `terms`, `value_basis`, `use_restrictions`,
`filter`. Rows come out exactly as from the ArcGIS path (source_record, parcel, address,
party, owner_snapshot, parcel_assessment when a tax year exists): normalization is
StateParcelAdapter's, and pii_fields are derived the same way. Only fetching differs.

Extra keys:
  api: socrata (default) | ckan
  layer_url: socrata  https://<portal>/resource/<4x4>.json
             ckan     https://<portal>/api/3/action/datastore_search   (plus resource_id: <uuid>)
  order_by: a key column; the API's own row id (:id / _id) is appended as tie-breaker, so
            offset paging runs in a total order.
  row_window: rows per partition (default 100000) when the county is a constant.
  filter: a fixed SoQL $where (socrata only).

Partitions: one per county when `county` is a field (fips3/fips5/int/code_map); otherwise
offset windows {row_min, row_max} cut from one count query. Offsets are stable only while the
table does not change, which holds within one refresh run (these tables update monthly or
less often). `sample=1` (with `limit`, optional `row_min`) records a fixture.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlsplit

import yaml

from equity.adapters.base import Fetched, FetchRequest, HealthReport
from equity.adapters.http import PoliteClient, Response
from equity.adapters.rows import canonical_json
from equity.adapters.socrata import SocrataError, SocrataQuery, get_page, parse_rows
from equity.adapters.state_parcels import (
    StateConfig,
    StateConfigError,
    StateParcelAdapter,
    load_config,
)
from equity.config import CONFIG_DIR
from equity.geo import counties_in

API_DIR = CONFIG_DIR / "socrata_parcels"
APIS = ("socrata", "ckan")
_SODA = re.compile(
    r"^(?P<portal>https://[^/]+)/resource/(?P<dataset>[a-z0-9]{4}-[a-z0-9]{4})\.json$"
)
_CKAN = re.compile(r"^https://[^/]+(/[^?#]*)?/api/3/action/datastore_search$")
_YEAR = re.compile(r"^\s*(\d{4})")
_ROW_ID = {"socrata": ":id", "ckan": "_id"}


@dataclass(frozen=True)
class ApiParcelConfig:
    base: StateConfig
    api: str
    resource_id: str | None
    row_window: int

    @property
    def portal(self) -> str:
        parts = urlsplit(self.base.layer_url)
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def dataset(self) -> str:
        m = _SODA.match(self.base.layer_url)
        return m.group("dataset") if m else str(self.resource_id)

    @property
    def order(self) -> tuple[str, ...]:
        return (self.base.order_by, _ROW_ID[self.api])


def load_api_config(path: Path) -> ApiParcelConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise StateConfigError(f"{path.name}: expected a mapping")
    api = str(data.get("api", "socrata"))
    if api not in APIS:
        raise StateConfigError(f"{path.name}: api must be one of {APIS}")
    base = load_config(path)
    if base.layers:
        raise StateConfigError(f"{path.name}: one table per config (no layers)")
    url = base.layer_url
    if api == "socrata" and not _SODA.match(url):
        raise StateConfigError(
            f"{path.name}: layer_url must be https://<portal>/resource/<4x4>.json"
        )
    if api == "ckan":
        if not _CKAN.match(url) or not data.get("resource_id"):
            raise StateConfigError(
                f"{path.name}: ckan needs layer_url .../datastore_search and resource_id"
            )
        if base.base_filter or "field" in base.county:
            raise StateConfigError(f"{path.name}: ckan supports a constant county and no filter")
    if base.county.get("format") == "name":
        raise StateConfigError(f"{path.name}: county name format is not supported; use code_map")
    return ApiParcelConfig(
        base=base,
        api=api,
        resource_id=str(data["resource_id"]) if data.get("resource_id") else None,
        row_window=int(data.get("row_window", 100_000)),
    )


class ApiParcelAdapter(StateParcelAdapter):
    """StateParcelAdapter's normalization over a Socrata or CKAN table."""

    api_config: ClassVar[ApiParcelConfig]
    access_method: ClassVar[str] = "api"

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.params = {"page_size": self.config.page_size}
        self.client = client or PoliteClient(
            min_interval_s=self.config.min_interval_s, timeout_s=300.0
        )

    def source_row(self) -> Mapping[str, Any]:
        row = dict(super().source_row())
        row["access_method"] = "api"
        if self.api_config.resource_id:
            row["base_url"] = f"{self.config.layer_url}?resource_id={self.api_config.resource_id}"
        return row

    # -- partitioning -------------------------------------------------------------------
    def _partition_where(self, request: FetchRequest) -> str:
        p = request.params
        if "county_fips" in p:
            return self._county_clause(p["county_fips"], 0)
        return "1=1"

    def partitions(self, window: int = 0) -> Iterator[dict[str, str]]:
        """Row windows of at most row_window rows (one count query each), per county when
        rows carry a county code (only the code_map's counties), else over the whole table.
        A county with no rows has no partition."""
        size = window or self.api_config.row_window
        spec = self.config.county
        fmt = spec.get("format")
        if fmt == "code_map":
            scopes: list[str | None] = [*sorted({str(v) for v in spec["code_map"].values()})]
        elif fmt in ("fips3", "fips5", "int"):
            scopes = [c.county_fips for c in counties_in(self.config.state)]
        else:
            scopes = [None]
        for fips in scopes:
            base = {} if fips is None else {"county_fips": fips}
            total = self.count(fips)
            for lo in range(0, total, size):
                yield {**base, "row_min": str(lo), "row_max": str(min(lo + size, total))}

    def count(self, county_fips: str | None = None) -> int:
        """Rows in the table (or one county), after the config's fixed filter."""
        if self.api_config.api == "ckan":
            body, _ = self._ckan(0, 0)
            return int(body["result"]["total"])
        where = self.where(FetchRequest({"county_fips": county_fips} if county_fips else {}))
        url = f"{self.api_config.portal}/resource/{self.api_config.dataset}.json"
        resp = self.client.get(url, {"$select": "count(*) AS n", "$where": where})
        if resp.status != 200:
            raise SocrataError(f"HTTP {resp.status} from {resp.url}: {resp.content[:200]!r}")
        return int(parse_rows(resp.content)[0]["n"])

    # -- fetching -----------------------------------------------------------------------
    def _ckan(self, offset: int, limit: int) -> tuple[dict[str, Any], Response]:
        params = {
            "resource_id": str(self.api_config.resource_id),
            "limit": str(limit),
            "offset": str(offset),
            "sort": ",".join(self.api_config.order),
            "fields": ",".join(self.fields),
        }
        resp = self.client.get(self.config.layer_url, params)
        try:
            body = json.loads(resp.content)
        except ValueError as exc:
            raise SocrataError(f"HTTP {resp.status} from {resp.url}: not JSON") from exc
        if resp.status != 200 or not body.get("success"):
            raise SocrataError(f"HTTP {resp.status} from {resp.url}: {str(body)[:200]}")
        return dict(body), resp

    def _page(self, where: str, offset: int, limit: int) -> tuple[list[dict[str, Any]], Response]:
        if self.api_config.api == "ckan":
            body, resp = self._ckan(offset, limit)
            return list(body["result"]["records"]), resp
        q = SocrataQuery(self.api_config.portal, self.api_config.dataset, where,
                         self.api_config.order, limit, self.fields)  # fmt: skip
        resp = get_page(self.client, q, offset)
        if resp.status != 200:
            raise SocrataError(f"HTTP {resp.status} from {resp.url}: {resp.content[:200]!r}")
        return parse_rows(resp.content), resp

    def fetch(self, request: FetchRequest) -> Fetched:
        """Rows [row_min, row_max) of the partition, paged in the config's total order.
        `limit` = one page of that size (fixtures)."""
        p = request.params
        where = self.where(request)
        limit = p.get("limit")
        page = int(limit) if limit is not None else self.config.page_size
        lo = int(p.get("row_min", "0"))
        hi = int(p["row_max"]) if "row_max" in p else None
        rows: list[dict[str, Any]] = []
        last: Response | None = None
        offset = lo
        for _ in range(100_000):
            n = page if hi is None else min(page, hi - offset)
            if n <= 0:
                break
            got, last = self._page(where, offset, n)
            rows.extend(got)
            if len(got) < n or limit is not None:
                break
            offset += len(got)
        else:
            raise SocrataError("too many pages; narrow the partition")
        if last is None:
            raise SocrataError(f"empty row window {lo}..{hi}")
        window = f"&row_min={lo}" + (f"&row_max={hi}" if hi is not None else "")
        body = canonical_json({"layer": self.config.layer_url, "where": where,
                               "row_min": lo, "attributes": rows})  # fmt: skip
        return Fetched(self.source_id, f"{self.config.layer_url}?where={where}{window}",
                       last.retrieved_at, 200, body, "application/json")  # fmt: skip

    def health(self) -> HealthReport:
        """Live: one row with every mapped column selected (an unknown column is an error)."""
        try:
            rows, resp = self._page(self.where(FetchRequest()), 0, 1)
        except (SocrataError, ValueError, OSError) as exc:
            return HealthReport(self.source_id, False, self.client.now(), repr(exc))
        ok = resp.status == 200 and len(rows) == 1
        shape = tuple(sorted(self.fields))
        detail = "ok" if ok else f"status={resp.status} rows={len(rows)}"
        return HealthReport(self.source_id, ok, self.client.now(), detail, shape)

    def layer_of(self, fetched: Fetched) -> int:
        return 0

    # -- normalization ------------------------------------------------------------------
    def _get(self, attrs: Mapping[str, Any], canonical: str) -> Any:
        spec = self.config.fields.get(canonical)
        if isinstance(spec, dict) and "year_of" in spec:
            # Socrata and CKAN dates are ISO text ('2024-07-01T00:00:00.000'), not epoch ms.
            raw = attrs.get(str(spec["year_of"]))
            if isinstance(raw, int | float):
                return datetime.fromtimestamp(int(raw) / 1000, tz=UTC).year
            m = _YEAR.match(str(raw or ""))
            return int(m.group(1)) if m else None
        return super()._get(attrs, canonical)


def api_adapter_for(cfg: ApiParcelConfig) -> type[ApiParcelAdapter]:
    base = cfg.base
    name = "ApiParcels_" + base.source_id.replace(".", "_")
    return type(
        name,
        (ApiParcelAdapter,),
        {
            "config": base,
            "api_config": cfg,
            "source_id": base.source_id,
            "layer_url": base.layer_url,
            # The API's row id is not selectable as a column; order_by is.
            "fields": base.source_fields,
            "order_by": cfg.order,
            "pii_fields": base.pii_fields,
            "health_where": "1=1",
            "__module__": __name__,
        },
    )


def api_config_paths(*dirs: Path) -> list[Path]:
    return [p for d in (dirs or (API_DIR,)) for p in sorted(d.glob("*.yaml"))]


def all_api_parcel_adapters(*dirs: Path) -> list[type[ApiParcelAdapter]]:
    return [api_adapter_for(load_api_config(p)) for p in api_config_paths(*dirs)]
