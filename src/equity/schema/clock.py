"""Injected clocks. Pipeline code never calls datetime.now() directly."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(UTC)


def fixed_clock(at: datetime) -> Clock:
    if at.tzinfo is None:
        raise ValueError("fixed_clock needs a timezone-aware datetime")

    def _clock() -> datetime:
        return at

    return _clock
