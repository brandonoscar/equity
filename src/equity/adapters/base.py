"""The adapter contract: fetch(), normalize(), health().

Source preference (record it in `access_method`): bulk files > official APIs > structured
endpoints (ArcGIS REST etc.) > feeds > HTML scraping as a last resort. Adapters never log in,
never solve CAPTCHAs, honor robots.txt and rate limits, and never call a paid source unless
the source is approved in config.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar


@dataclass(frozen=True)
class FetchRequest:
    """What to get. `params` are source-specific (bbox, date range, page offset, case no...)."""

    params: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Fetched:
    """Raw bytes plus everything provenance needs. Stored before normalize() runs."""

    source_id: str
    request: str  # URL with query, or file path
    retrieved_at: datetime
    http_status: int | None
    content: bytes
    content_type: str


@dataclass(frozen=True)
class NormalizedRow:
    table: str
    row: Mapping[str, Any]


@dataclass(frozen=True)
class HealthReport:
    source_id: str
    ok: bool
    checked_at: datetime
    detail: str
    # Shape fingerprint (e.g. sorted field names) compared against the fixture's.
    shape: tuple[str, ...] = ()


class Adapter(ABC):
    source_id: ClassVar[str]
    adapter_version: ClassVar[str]
    access_method: ClassVar[str]  # bulk | api | arcgis | feed | html | manual

    @abstractmethod
    def source_row(self) -> Mapping[str, Any]:
        """The `source` table row: terms, robots check date, cost model."""

    @abstractmethod
    def fetch(self, request: FetchRequest) -> Fetched:
        """Retrieve raw bytes. The only method allowed to touch the network."""

    @abstractmethod
    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        """Pure function of the fetched bytes: same input, same rows, every time."""

    @abstractmethod
    def health(self) -> HealthReport:
        """Live check (nightly only): reachable, and response shape matches the fixture."""


# Registered adapter classes. Contract tests and the nightly health job iterate this list.
REGISTRY: list[type[Adapter]] = []


def register(cls: type[Adapter]) -> type[Adapter]:
    if cls in REGISTRY:
        raise ValueError(f"{cls.__name__} registered twice")
    REGISTRY.append(cls)
    return cls
