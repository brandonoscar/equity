"""Socrata (SODA 2.x) query paging, shared by every Socrata-backed adapter.

Rules (checked on data.cityofnewyork.us, data.ny.gov, data.ct.gov, data.colorado.gov and
data.oregon.gov, 2026-11-16): robots.txt allows /resource/ with Crawl-delay: 1, which
PoliteClient honors. No app token: we stay anonymous. Socrata leaves null fields out of JSON
rows, so field lists come from /api/views/<id>/columns.json, never from a sample row.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from equity.adapters.http import PoliteClient, Response


class SocrataError(RuntimeError):
    pass


@dataclass(frozen=True)
class SocrataQuery:
    portal: str  # https://data.cityofnewyork.us
    dataset: str  # 4x4 id, e.g. bnx9-e6tj
    where: str
    # Total order for stable paging. ":id" (Socrata's row id) breaks ties.
    order_by: Sequence[str] = (":id",)
    page_size: int = 50_000
    select: Sequence[str] = ()

    @property
    def url(self) -> str:
        return f"{self.portal}/resource/{self.dataset}.json"

    def params(self, offset: int) -> dict[str, str]:
        p = {
            "$where": self.where,
            "$order": ",".join(self.order_by),
            "$limit": str(self.page_size),
            "$offset": str(offset),
        }
        if self.select:
            p["$select"] = ",".join(self.select)
        return p


def parse_rows(body: bytes) -> list[dict[str, Any]]:
    data = json.loads(body)
    if isinstance(data, dict) and data.get("error"):
        raise SocrataError(str(data.get("message") or data))
    if not isinstance(data, list):
        raise SocrataError("response is not a JSON array of rows")
    return data


def _is_transient(body: bytes) -> bool:
    try:
        json.loads(body)
    except ValueError:
        return True
    return False


def get_page(client: PoliteClient, query: SocrataQuery, offset: int) -> Response:
    """One page; an empty or cut-off 200 body is retried with the client's backoff."""
    attempt = 0
    while True:
        resp = client.get(query.url, query.params(offset))
        if resp.status != 200 or not _is_transient(resp.content) or attempt >= client.retries:
            return resp
        client.sleep(client.backoff_s * (2**attempt))
        attempt += 1


def fetch_all(
    client: PoliteClient, query: SocrataQuery, max_pages: int = 10_000, sample: bool = False
) -> tuple[list[dict[str, Any]], list[Response]]:
    """Page with $limit/$offset in a total order until a short page. sample=True stops after
    max_pages (fixtures); otherwise hitting max_pages is an error."""
    rows: list[dict[str, Any]] = []
    responses: list[Response] = []
    offset = 0
    for _ in range(max_pages):
        resp = get_page(client, query, offset)
        if resp.status != 200:
            raise SocrataError(f"HTTP {resp.status} from {resp.url}: {resp.content[:200]!r}")
        page = parse_rows(resp.content)
        rows.extend(page)
        responses.append(resp)
        if len(page) < query.page_size or (sample and len(responses) >= max_pages):
            return rows, responses
        offset += len(page)
    raise SocrataError(f"stopped after {max_pages} pages; narrow the query")


def quote(value: str) -> str:
    """A SoQL string literal."""
    return "'" + value.replace("'", "''") + "'"
