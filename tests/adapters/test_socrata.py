"""Socrata paging: stable order, short-page stop, transient retries, errors. Offline."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from equity.adapters.http import Response
from equity.adapters.socrata import SocrataError, SocrataQuery, fetch_all, parse_rows, quote

Q = SocrataQuery("https://p.test", "abcd-1234", "x > 1", ("document_id", ":id"), page_size=2)
AT = datetime(2026, 1, 1, tzinfo=UTC)


class Client:
    retries = 3
    backoff_s = 2.0

    def __init__(self, bodies: list[bytes], status: int = 200) -> None:
        self.bodies = bodies
        self.status = status
        self.params: list[dict[str, str]] = []
        self.slept: list[float] = []

    def sleep(self, s: float) -> None:
        self.slept.append(s)

    def get(self, url: str, params: dict[str, str]) -> Response:
        assert url == "https://p.test/resource/abcd-1234.json"
        body = self.bodies[min(len(self.params), len(self.bodies) - 1)]
        self.params.append(params)
        return Response(url, self.status, body, "application/json", AT)


def _rows(*ids: int) -> bytes:
    return json.dumps([{"id": i} for i in ids]).encode()


def test_params_are_explicit() -> None:
    assert Q.params(4) == {"$where": "x > 1", "$order": "document_id,:id", "$limit": "2",
                           "$offset": "4"}  # fmt: skip
    q = SocrataQuery("https://p.test", "abcd-1234", "1=1", select=("a", "b"))
    assert q.params(0)["$select"] == "a,b" and q.params(0)["$order"] == ":id"


def test_pages_until_a_short_page() -> None:
    c = Client([_rows(1, 2), _rows(3, 4), _rows(5)])
    rows, resps = fetch_all(c, Q)  # type: ignore[arg-type]
    assert [r["id"] for r in rows] == [1, 2, 3, 4, 5]
    assert [p["$offset"] for p in c.params] == ["0", "2", "4"]
    assert len(resps) == 3


def test_exact_multiple_ends_with_an_empty_page() -> None:
    c = Client([_rows(1, 2), _rows()])
    rows, _ = fetch_all(c, Q)  # type: ignore[arg-type]
    assert len(rows) == 2 and len(c.params) == 2


def test_sample_and_cap() -> None:
    rows, _ = fetch_all(Client([_rows(1, 2)]), Q, max_pages=1, sample=True)  # type: ignore[arg-type]
    assert len(rows) == 2
    with pytest.raises(SocrataError, match="stopped after 1"):
        fetch_all(Client([_rows(1, 2)]), Q, max_pages=1)  # type: ignore[arg-type]


def test_cut_off_bodies_are_retried_then_surface() -> None:
    c = Client([b"", b"[{", _rows(9)])
    rows, _ = fetch_all(c, Q)  # type: ignore[arg-type]
    assert [r["id"] for r in rows] == [9] and c.slept == [2.0, 4.0]
    bad = Client([b""])
    with pytest.raises(json.JSONDecodeError):
        fetch_all(bad, Q)  # type: ignore[arg-type]
    assert len(bad.params) == 4


def test_errors_surface() -> None:
    with pytest.raises(SocrataError, match="HTTP 400"):
        fetch_all(Client([b'{"message": "no such column"}'], status=400), Q)  # type: ignore[arg-type]
    with pytest.raises(SocrataError, match="no such column"):
        parse_rows(b'{"error": true, "message": "no such column"}')
    with pytest.raises(SocrataError, match="not a JSON array"):
        parse_rows(b'{"rows": []}')


def test_quote_escapes_single_quotes() -> None:
    assert quote("O'Brien") == "'O''Brien'"
