from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from equity.adapters.arcgis import ArcGISError, ArcGISQuery, fetch_all, parse_page
from equity.adapters.http import Response

Q = ArcGISQuery("https://x.test/MapServer/1", "A=1", ("A", "B"), ("ID",), page_size=2)


class PagedClient:
    def __init__(self, pages: list[dict[str, object]], status: int = 200) -> None:
        self.pages = pages
        self.status = status
        self.offsets: list[str] = []

    def get(self, url: str, params: dict[str, str]) -> Response:
        self.offsets.append(params["resultOffset"])
        page = self.pages[len(self.offsets) - 1]
        return Response(url, self.status, json.dumps(page).encode(), "application/json",
                        datetime(2026, 1, 1, tzinfo=UTC))  # fmt: skip


def _page(ids: list[int], more: bool) -> dict[str, object]:
    return {"features": [{"attributes": {"ID": i}} for i in ids], "exceededTransferLimit": more}


def test_params_are_explicit_and_stable() -> None:
    p = Q.params(4)
    assert p["orderByFields"] == "ID"
    assert p["resultOffset"] == "4"
    assert p["returnGeometry"] == "false"


def test_pages_until_exhausted() -> None:
    c = PagedClient([_page([1, 2], True), _page([3], False)])
    feats, resps = fetch_all(c, Q)  # type: ignore[arg-type]
    assert [f["attributes"]["ID"] for f in feats] == [1, 2, 3]
    assert c.offsets == ["0", "2"]
    assert len(resps) == 2


def test_sample_stops_early_and_cap_raises() -> None:
    feats, _ = fetch_all(PagedClient([_page([1, 2], True)]), Q, max_pages=1, sample=True)  # type: ignore[arg-type]
    assert len(feats) == 2
    with pytest.raises(ArcGISError, match="stopped after 1"):
        fetch_all(PagedClient([_page([1, 2], True)]), Q, max_pages=1)  # type: ignore[arg-type]


def test_errors_surface() -> None:
    with pytest.raises(ArcGISError, match="HTTP 500"):
        fetch_all(PagedClient([_page([], False)], status=500), Q)  # type: ignore[arg-type]
    with pytest.raises(ArcGISError, match="Unable"):
        parse_page(b'{"error": {"code": 400, "message": "Unable"}}')
    with pytest.raises(ArcGISError, match="no features"):
        parse_page(b"{}")
