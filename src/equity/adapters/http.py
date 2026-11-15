"""Polite HTTP for adapters: robots.txt honored, per-host minimum interval, no auth, a fixed
identifying User-Agent. Standard library only. Transport and clocks are injectable so the
politeness rules are tested offline.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

USER_AGENT = "equity-records/0.1 (public records research; respects robots.txt)"

# (url, headers, timeout) -> (status, body, content_type)
Transport = Callable[[str, Mapping[str, str], float], tuple[int, bytes, str]]


class AccessDenied(RuntimeError):
    """robots.txt disallows the URL, or robots.txt was unreachable (RFC 9309: disallow)."""


@dataclass(frozen=True)
class Response:
    url: str
    status: int
    content: bytes
    content_type: str
    retrieved_at: datetime


def urllib_transport(
    url: str, headers: Mapping[str, str], timeout: float
) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, headers=dict(headers))  # noqa: S310 - https URLs only
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return int(resp.status), resp.read(), str(resp.headers.get("Content-Type", ""))
    except urllib.error.HTTPError as err:
        return int(err.code), err.read(), str(err.headers.get("Content-Type", ""))


@dataclass
class PoliteClient:
    min_interval_s: float = 1.0
    timeout_s: float = 60.0
    user_agent: str = USER_AGENT
    transport: Transport = urllib_transport
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    _last: dict[str, float] = field(default_factory=dict)
    _robots: dict[str, urllib.robotparser.RobotFileParser] = field(default_factory=dict)

    def _wait_turn(self, host: str) -> None:
        wait = self._last.get(host, float("-inf")) + self.min_interval_s - self.monotonic()
        if wait > 0:
            self.sleep(wait)

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            rp = urllib.robotparser.RobotFileParser(origin + "/robots.txt")
            self._wait_turn(parts.netloc)
            try:
                status, body, _ = self.transport(
                    origin + "/robots.txt", {"User-Agent": self.user_agent}, self.timeout_s
                )
            except OSError:
                status, body = 599, b""
            self._last[parts.netloc] = self.monotonic()
            # RFC 9309 (Robots Exclusion Protocol), section 2.3.1:
            #   2xx: obey the file;  4xx "unavailable" (incl. 401/403): no restrictions;
            #   5xx or network error "unreachable": assume complete disallow.
            if 200 <= status < 300:
                rp.parse(body.decode("utf-8", errors="replace").splitlines())
            elif 400 <= status < 500:
                rp.parse([])
            else:
                rp.disallow_all = True
            self._robots[origin] = rp
        return self._robots[origin]

    def get(self, url: str, params: Mapping[str, str] | None = None) -> Response:
        full = url + ("?" + urllib.parse.urlencode(sorted(params.items())) if params else "")
        if not self._robots_for(full).can_fetch(self.user_agent, full):
            raise AccessDenied(f"robots.txt disallows {full}")
        host = urllib.parse.urlsplit(full).netloc
        self._wait_turn(host)
        status, body, ctype = self.transport(full, {"User-Agent": self.user_agent}, self.timeout_s)
        self._last[host] = self.monotonic()
        return Response(full, status, body, ctype, self.now())
