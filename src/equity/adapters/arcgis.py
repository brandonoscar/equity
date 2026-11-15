"""ArcGIS REST query paging, shared by every ArcGIS-backed adapter."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from equity.adapters.http import PoliteClient, Response


class ArcGISError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArcGISQuery:
    layer_url: str  # .../MapServer/<n> or .../FeatureServer/<n>
    where: str
    out_fields: Sequence[str]
    order_by: Sequence[str]
    page_size: int
    return_geometry: bool = False

    def params(self, offset: int) -> dict[str, str]:
        return {
            "where": self.where,
            "outFields": ",".join(self.out_fields),
            "orderByFields": ",".join(self.order_by),
            "resultOffset": str(offset),
            "resultRecordCount": str(self.page_size),
            "returnGeometry": "true" if self.return_geometry else "false",
            "outSR": "4326",
            "f": "json",
        }


def parse_page(body: bytes) -> tuple[list[dict[str, Any]], bool]:
    data = json.loads(body)
    if "error" in data:
        raise ArcGISError(str(data["error"]))
    feats = data.get("features")
    if not isinstance(feats, list):
        raise ArcGISError("response has no features list")
    return feats, bool(data.get("exceededTransferLimit"))


def fetch_all(
    client: PoliteClient, query: ArcGISQuery, max_pages: int = 10_000, sample: bool = False
) -> tuple[list[dict[str, Any]], list[Response]]:
    """Page through a query in stable order. Returns features and every raw response.

    sample=True returns after max_pages even if more exist (used to record fixtures).
    """
    features: list[dict[str, Any]] = []
    responses: list[Response] = []
    offset = 0
    for _ in range(max_pages):
        resp = client.get(query.layer_url + "/query", query.params(offset))
        if resp.status != 200:
            raise ArcGISError(f"HTTP {resp.status} from {resp.url}")
        page, more = parse_page(resp.content)
        features.extend(page)
        responses.append(resp)
        if not more or not page or (sample and len(responses) >= max_pages):
            return features, responses
        offset += len(page)
    raise ArcGISError(f"stopped after {max_pages} pages; refine the query")
