"""Base class for adapters backed by one ArcGIS REST layer, fetched one county at a time."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

from equity.adapters.arcgis import ArcGISQuery, fetch_all
from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import canonical_json
from equity.config import source_params


class ArcGISCountyAdapter(Adapter):
    access_method: ClassVar[str] = "arcgis"
    layer_url: ClassVar[str]
    fields: ClassVar[tuple[str, ...]]
    order_by: ClassVar[tuple[str, ...]] = ("OBJECTID",)
    # Fields replaced with pseudonyms when recording fixtures (the repo is public).
    pii_fields: ClassVar[tuple[str, ...]] = ()
    health_where: ClassVar[str]

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.params = source_params(self.source_id)
        self.client = client or PoliteClient(min_interval_s=float(self.params["min_interval_s"]))

    def where(self, request: FetchRequest) -> str:
        raise NotImplementedError

    def fetch(self, request: FetchRequest) -> Fetched:
        """Whole county in one Fetched. Optional `limit` = one page of that size (fixtures)."""
        limit = request.params.get("limit")
        page = int(limit) if limit is not None else int(self.params["page_size"])
        q = ArcGISQuery(self.layer_url, self.where(request), self.fields, self.order_by, page)
        features, responses = fetch_all(
            self.client, q, max_pages=1 if limit else 10_000, sample=limit is not None
        )
        body = canonical_json(
            {"layer": self.layer_url, "where": q.where,
             "attributes": [f["attributes"] for f in features]}
        )  # fmt: skip
        return Fetched(
            source_id=self.source_id,
            request=f"{self.layer_url}/query?where={q.where}",
            retrieved_at=responses[-1].retrieved_at,
            http_status=200,
            content=body,
            content_type="application/json",
        )

    @staticmethod
    def attributes(fetched: Fetched) -> list[Mapping[str, Any]]:
        data = json.loads(fetched.content)
        attrs = data["attributes"]
        if not isinstance(attrs, list):
            raise ValueError("fetched content has no attributes list")
        return attrs

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        raise NotImplementedError

    def health(self) -> HealthReport:
        q = ArcGISQuery(self.layer_url, self.health_where, self.fields, self.order_by, 1)
        resp = self.client.get(self.layer_url + "/query", q.params(0))
        try:
            feats = json.loads(resp.content).get("features") or []
        except ValueError:
            feats = []
        shape = tuple(sorted(feats[0]["attributes"])) if feats else ()
        ok = resp.status == 200 and shape == tuple(sorted(self.fields))
        detail = "ok" if ok else f"status={resp.status} fields={list(shape)}"
        return HealthReport(self.source_id, ok, datetime.now(UTC), detail, shape)
