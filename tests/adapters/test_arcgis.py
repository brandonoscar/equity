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


class RawClient:
    """Returns the given bodies in order (HTTP 200), recording backoff sleeps."""

    retries = 3
    backoff_s = 2.0

    def __init__(self, bodies: list[bytes]) -> None:
        self.bodies = bodies
        self.calls = 0
        self.slept: list[float] = []

    def sleep(self, s: float) -> None:
        self.slept.append(s)

    def get(self, url: str, params: dict[str, str]) -> Response:
        body = self.bodies[min(self.calls, len(self.bodies) - 1)]
        self.calls += 1
        return Response(url, 200, body, "application/json", datetime(2026, 1, 1, tzinfo=UTC))


def test_empty_or_cut_off_bodies_are_retried_with_backoff() -> None:
    good = json.dumps(_page([1], False)).encode()
    c = RawClient([b"", b'{"features": [', good])
    feats, resps = fetch_all(c, Q)  # type: ignore[arg-type]
    assert [f["attributes"]["ID"] for f in feats] == [1]
    assert c.calls == 3 and c.slept == [2.0, 4.0]
    assert len(resps) == 1  # only the good response is kept as provenance


def test_server_5xx_error_object_is_retried_but_specific_4xx_is_not() -> None:
    good = json.dumps(_page([7], False)).encode()
    c = RawClient([b'{"error": {"code": 503, "message": "busy"}}', good])
    feats, _ = fetch_all(c, Q)  # type: ignore[arg-type]
    assert [f["attributes"]["ID"] for f in feats] == [7] and c.slept == [2.0]
    bad = RawClient([b'{"error": {"code": 400, "message": "Invalid field: FOO"}}'])
    with pytest.raises(ArcGISError, match="Invalid field"):
        fetch_all(bad, Q)  # type: ignore[arg-type]
    assert bad.calls == 1


def test_arcgis_online_generic_400_is_retried() -> None:
    busy = b'{"error": {"code": 400, "message": "Cannot perform query. Invalid query parameters."}}'
    c = RawClient([busy, json.dumps(_page([3], False)).encode()])
    feats, _ = fetch_all(c, Q)  # type: ignore[arg-type]
    assert [f["attributes"]["ID"] for f in feats] == [3] and c.calls == 2
    stuck = RawClient([busy])
    with pytest.raises(ArcGISError, match="Cannot perform query"):
        fetch_all(stuck, Q)  # type: ignore[arg-type]
    assert stuck.calls == 4


def test_persistent_empty_body_surfaces_after_retries() -> None:
    c = RawClient([b""])
    with pytest.raises(json.JSONDecodeError):
        fetch_all(c, Q)  # type: ignore[arg-type]
    assert c.calls == 4 and c.slept == [2.0, 4.0, 8.0]


def test_get_json_retries_busy_answers() -> None:
    from equity.adapters.arcgis import get_json

    busy = b'{"error":{"code":400,"message":"","details":["Unable to perform query. x"]}}'
    real = b'{"error":{"code":400,"message":"","details":["Invalid field: X"]}}'

    class Seq:
        retries = 2
        backoff_s = 0.0

        def __init__(self, bodies: list[bytes]) -> None:
            self.bodies = bodies

        def sleep(self, s: float) -> None:
            pass

        def get(self, url: str, params: object = None) -> object:
            from datetime import UTC, datetime

            from equity.adapters.http import Response

            return Response(url, 200, self.bodies.pop(0), "application/json", datetime.now(UTC))

    assert get_json(Seq([busy, b"", b'{"count": 3}']), "u", {}) == {"count": 3}  # type: ignore[arg-type]
    assert "error" in get_json(Seq([real]), "u", {})  # type: ignore[arg-type]
    assert "error" in get_json(Seq([busy, busy, busy]), "u", {})  # type: ignore[arg-type]
