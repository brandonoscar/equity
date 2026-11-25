"""Politeness rules: robots.txt honored, per-host spacing, status passthrough. Offline."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from equity.adapters.http import AccessDenied, PoliteClient, decode_body


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


# RFC 9309 section 2.3.1: 4xx (including 401/403) = unavailable = no restrictions;
# 5xx = unreachable = complete disallow.
@pytest.mark.parametrize(
    ("status", "allowed"), [(404, True), (403, True), (401, True), (500, False), (503, False)]
)
def test_robots_status_conventions(status: int, allowed: bool) -> None:
    net = FakeNet({"https://b.test/robots.txt": (status, b""), "https://b.test/": (200, b"ok")})
    c = client(net, FakeClock())
    if allowed:
        assert c.get("https://b.test/x").status == 200
    else:
        with pytest.raises(AccessDenied):
            c.get("https://b.test/x")


def test_unreachable_robots_means_disallow() -> None:
    net = FakeNet({"https://c.test/x": (200, b"ok")})  # robots.txt raises OSError
    with pytest.raises(AccessDenied):
        client(net, FakeClock()).get("https://c.test/x")
    assert net.calls == ["https://c.test/robots.txt"]  # the page itself was never requested


def test_requests_to_one_host_are_spaced() -> None:
    net = FakeNet({"https://d.test/robots.txt": (404, b""), "https://d.test/": (200, b"ok")})
    clock = FakeClock()
    c = client(net, clock, interval=2.0)
    c.get("https://d.test/1")
    c.get("https://d.test/2", {"b": "2", "a": "1"})
    assert clock.slept == [2.0, 2.0]  # robots then page 1, then page 2
    assert net.calls[-1] == "https://d.test/2?a=1&b=2"  # params sorted: stable request strings


def test_robots_crawl_delay_longer_than_ours_is_honored() -> None:
    robots = b"User-agent: *\nCrawl-delay: 5\nDisallow:\n"
    net = FakeNet({"https://e.test/robots.txt": (200, robots), "https://e.test/": (200, b"ok")})
    clock = FakeClock()
    c = client(net, clock, interval=2.0)
    c.get("https://e.test/1")
    c.get("https://e.test/2")
    # page 1 waits 5 s after the robots fetch, page 2 waits 5 s after page 1
    assert clock.slept == [5.0, 5.0]


def test_crawl_delay_shorter_than_ours_does_not_speed_us_up() -> None:
    robots = b"User-agent: *\nCrawl-delay: 1\n"
    net = FakeNet({"https://f.test/robots.txt": (200, robots), "https://f.test/": (200, b"ok")})
    clock = FakeClock()
    c = client(net, clock, interval=3.0)
    c.get("https://f.test/1")
    assert clock.slept == [3.0]


def test_transient_failures_are_retried_with_backoff() -> None:
    attempts: list[str] = []

    def flaky(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        attempts.append(url)
        if len(attempts) == 1:
            raise ConnectionResetError("reset")
        if len(attempts) == 2:
            return 503, b"busy", "text/plain"
        return 200, b"ok", "text/plain"

    clock = FakeClock()
    c = PoliteClient(min_interval_s=0, transport=flaky, sleep=clock.sleep,
                     monotonic=clock.monotonic)  # fmt: skip
    assert c.get("https://e.test/x").content == b"ok"
    assert len(attempts) == 3
    assert clock.slept == [2.0, 4.0]


def test_retries_give_up() -> None:
    def down(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        raise TimeoutError("timed out")

    clock = FakeClock()
    c = PoliteClient(min_interval_s=0, transport=down, sleep=clock.sleep, retries=2)
    with pytest.raises(TimeoutError):
        c.get("https://f.test/x")
    assert clock.slept == [2.0, 4.0]

    def busy(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        return (404, b"", "") if url.endswith("robots.txt") else (429, b"slow down", "")

    c = PoliteClient(min_interval_s=0, transport=busy, sleep=FakeClock().sleep, retries=1)
    assert c.get("https://g.test/x").status == 429  # surfaced after retries


def test_gzip_bodies_are_decoded_and_others_pass_through() -> None:
    import gzip

    raw = b'{"a": 1}'
    assert decode_body(gzip.compress(raw), "gzip") == raw
    assert decode_body(gzip.compress(raw), " GZIP ") == raw
    assert decode_body(raw, None) == raw
    assert decode_body(raw, "identity") == raw


def test_cut_off_transfers_are_retried() -> None:
    import http.client

    calls: list[str] = []

    def cut(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        calls.append(url)
        if len(calls) == 1:
            raise http.client.IncompleteRead(b"partial", 100)
        return 200, b"whole", "text/plain"

    clock = FakeClock()
    c = PoliteClient(min_interval_s=0.0, transport=cut, sleep=clock.sleep,
                     monotonic=clock.monotonic)  # fmt: skip
    assert c.get("https://g.test/x").content == b"whole"
    assert len(calls) == 2 and clock.slept == [2.0]


WPRDC_ROBOTS = b"""# If you use WPRDC data for your scripts or applications, you are allowed to
# ignore these rules.
User-agent: *
Disallow: /api/
Disallow: /datastore/dump/
Disallow: /private/
"""


def test_written_script_permission_opens_only_its_prefix_while_still_published() -> None:
    net = FakeNet({"https://data.wprdc.org/robots.txt": (200, WPRDC_ROBOTS),
                   "https://data.wprdc.org/": (200, b"ok")})  # fmt: skip
    c = client(net, FakeClock())
    assert c.get("https://data.wprdc.org/api/3/action/datastore_search").content == b"ok"
    assert c.get("https://data.wprdc.org/datastore/dump/abc").content == b"ok"
    with pytest.raises(AccessDenied):  # not a permitted prefix
        c.get("https://data.wprdc.org/private/x")
    withdrawn = FakeNet({"https://data.wprdc.org/robots.txt":
                         (200, b"User-agent: *\nDisallow: /api/\n")})  # fmt: skip
    with pytest.raises(AccessDenied):  # sentence gone: back to the plain rules
        client(withdrawn, FakeClock()).get("https://data.wprdc.org/api/3/action/x")
    other = FakeNet({"https://b.test/robots.txt": (200, WPRDC_ROBOTS)})
    with pytest.raises(AccessDenied):  # the same text on another host grants nothing
        client(other, FakeClock()).get("https://b.test/api/x")


def test_post_form_follows_robots_and_spacing() -> None:
    net = FakeNet({"https://a.test/robots.txt": (200, b"User-agent: *\nDisallow: /private\n")})
    posted: list[tuple[str, bytes, str]] = []

    def post(url: str, headers: Mapping[str, str], body: bytes, timeout: float
             ) -> tuple[int, bytes, str]:  # fmt: skip
        posted.append((url, body, headers["User-Agent"]))
        return 200, b"file", "application/octet-stream"

    clock = FakeClock()
    c = PoliteClient(min_interval_s=2.0, transport=net, post_transport=post, sleep=clock.sleep,
                     monotonic=clock.monotonic)  # fmt: skip
    resp = c.post_form("https://a.test/form.aspx", {"b": "2 3", "a": "x\\y"})
    assert resp.status == 200 and resp.content == b"file"
    assert posted == [("https://a.test/form.aspx", b"b=2+3&a=x%5Cy", posted[0][2])]
    assert posted[0][2].startswith("equity-records/")
    assert clock.slept == [2.0]  # spaced after the robots.txt request
    with pytest.raises(AccessDenied):
        c.post_form("https://a.test/private/form.aspx", {})


def test_urllib_post_transport_sends_a_form(monkeypatch: pytest.MonkeyPatch) -> None:
    from equity.adapters import http

    seen: dict[str, object] = {}

    def fake(url: str, headers: Mapping[str, str], data: bytes | None, timeout: float
             ) -> tuple[int, bytes, str]:  # fmt: skip
        seen.update(url=url, headers=dict(headers), data=data)
        return 200, b"", ""

    monkeypatch.setattr(http, "_urlopen", fake)
    http.urllib_post_transport("https://a.test/f", {"User-Agent": "u"}, b"a=1", 5.0)
    assert seen["data"] == b"a=1"
    assert seen["headers"] == {"User-Agent": "u",
                               "Content-Type": "application/x-www-form-urlencoded"}  # fmt: skip


def test_redirects_drop_an_explicit_https_default_port() -> None:
    from equity.adapters.http import drop_default_port

    assert drop_default_port("https://s3.amazonaws.com:443/b/k?X-Amz=1") == (
        "https://s3.amazonaws.com/b/k?X-Amz=1")  # fmt: skip
    assert drop_default_port("https://h.test:8443/x") == "https://h.test:8443/x"
    assert drop_default_port("http://h.test:443/x") == "http://h.test:443/x"
