"""Politeness rules: robots.txt honored, per-host spacing, status passthrough. Offline."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from equity.adapters.http import AccessDenied, PoliteClient


class FakeNet:
    def __init__(self, routes: Mapping[str, tuple[int, bytes]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(
        self, url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes, str]:
        self.calls.append(url)
        assert headers["User-Agent"].startswith("equity-records/")
        for prefix, (status, body) in self.routes.items():
            if url.startswith(prefix):
                return status, body, "text/plain"
        raise OSError("unreachable")


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


def client(net: FakeNet, clock: FakeClock, interval: float = 2.0) -> PoliteClient:
    return PoliteClient(
        min_interval_s=interval, transport=net, sleep=clock.sleep, monotonic=clock.monotonic,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
    )  # fmt: skip


def test_robots_disallow_blocks_request() -> None:
    net = FakeNet({"https://a.test/robots.txt": (200, b"User-agent: *\nDisallow: /private\n"),
                   "https://a.test/": (200, b"ok")})  # fmt: skip
    c = client(net, FakeClock())
    assert c.get("https://a.test/public").content == b"ok"
    with pytest.raises(AccessDenied):
        c.get("https://a.test/private/x")
    assert net.calls.count("https://a.test/robots.txt") == 1  # cached per origin


@pytest.mark.parametrize(("status", "allowed"), [(404, True), (500, True), (403, False)])
def test_robots_status_conventions(status: int, allowed: bool) -> None:
    net = FakeNet({"https://b.test/robots.txt": (status, b""), "https://b.test/": (200, b"ok")})
    c = client(net, FakeClock())
    if allowed:
        assert c.get("https://b.test/x").status == 200
    else:
        with pytest.raises(AccessDenied):
            c.get("https://b.test/x")


def test_unreachable_robots_means_no_rules() -> None:
    net = FakeNet({"https://c.test/x": (200, b"ok")})
    assert client(net, FakeClock()).get("https://c.test/x").status == 200


def test_requests_to_one_host_are_spaced() -> None:
    net = FakeNet({"https://d.test/robots.txt": (404, b""), "https://d.test/": (200, b"ok")})
    clock = FakeClock()
    c = client(net, clock, interval=2.0)
    c.get("https://d.test/1")
    c.get("https://d.test/2", {"b": "2", "a": "1"})
    assert clock.slept == [2.0, 2.0]  # robots then page 1, then page 2
    assert net.calls[-1] == "https://d.test/2?a=1&b=2"  # params sorted: stable request strings
