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
    # Some servers reject resultOffset/resultRecordCount/orderByFields. Then each query must
    # be a window small enough to come back whole (e.g. an object-id range <= maxRecordCount).
    paginate: bool = True

    def params(self, offset: int) -> dict[str, str]:
        p = {
            "where": self.where,
            "outFields": ",".join(self.out_fields),
            "returnGeometry": "true" if self.return_geometry else "false",
            "outSR": "4326",
            "f": "json",
        }
        if self.paginate:
            p["orderByFields"] = ",".join(self.order_by)
            p["resultOffset"] = str(offset)
            p["resultRecordCount"] = str(self.page_size)
        return p


def parse_page(body: bytes) -> tuple[list[dict[str, Any]], bool]:
    data = json.loads(body)
    if "error" in data:
        raise ArcGISError(str(data["error"]))
    feats = data.get("features")
    if not isinstance(feats, list):
        raise ArcGISError("response has no features list")
    return feats, bool(data.get("exceededTransferLimit"))


TRANSIENT_ERROR_CODES = frozenset({500, 502, 503, 504})


# ArcGIS Online answers some queries under load with this generic 400, and the same query
# succeeds moments later (seen on the Florida cadastral layer at resultOffset 100000,
# 2026-11-16). Specific 400s ("Invalid field ...") are real errors and are not retried.
TRANSIENT_400_PREFIX = "Cannot perform query"


def _is_transient(body: bytes) -> bool:
    """An empty or cut-off body, a 5xx error object, or ArcGIS Online's generic busy-400."""
    try:
        data = json.loads(body)
    except ValueError:
        return True
    err = data.get("error") if isinstance(data, dict) else None
    if not isinstance(err, dict):
        return False
    if err.get("code") in TRANSIENT_ERROR_CODES:
        return True
    return err.get("code") == 400 and str(err.get("message", "")).startswith(TRANSIENT_400_PREFIX)


def get_page(client: PoliteClient, query: ArcGISQuery, offset: int) -> Response:
    """One query page. A 200 whose body is empty, truncated or a 5xx error object is retried
    with the client's backoff, like an HTTP 5xx; the last response surfaces if it persists."""
    attempt = 0
    while True:
        resp = client.get(query.layer_url + "/query", query.params(offset))
        if resp.status != 200 or not _is_transient(resp.content) or attempt >= client.retries:
            return resp
        client.sleep(client.backoff_s * (2**attempt))
        attempt += 1


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
        resp = get_page(client, query, offset)
        if resp.status != 200:
            raise ArcGISError(f"HTTP {resp.status} from {resp.url}")
        page, more = parse_page(resp.content)
        features.extend(page)
        responses.append(resp)
        if not query.paginate:
            if more:
                raise ArcGISError("window exceeds the server's record limit; use smaller windows")
            return features, responses
        if not more or not page or (sample and len(responses) >= max_pages):
            return features, responses
        offset += len(page)
    raise ArcGISError(f"stopped after {max_pages} pages; refine the query")
