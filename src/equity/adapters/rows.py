"""Builders for normalized rows, so every adapter emits provenance the same way."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from equity.adapters.base import Fetched, NormalizedRow
from equity.schema.ids import sha256_hex, stable_id


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def fetch_id(fetched: Fetched) -> str:
    return stable_id(fetched.source_id, fetched.request, fetched.retrieved_at.isoformat())


def fetch_log_row(fetched: Fetched, adapter: str, version: str, raw_path: str) -> NormalizedRow:
    return NormalizedRow(
        "fetch_log",
        {
            "fetch_id": fetch_id(fetched),
            "source_id": fetched.source_id,
            "adapter": adapter,
            "adapter_version": version,
            "request": fetched.request,
            "retrieved_at": fetched.retrieved_at,
            "http_status": fetched.http_status,
            "content_sha256": sha256_hex(fetched.content),
            "raw_path": raw_path,
            "bytes": len(fetched.content),
        },
    )


class RecordContext:
    """Provenance for one source record (a feature, a row, a docket line)."""

    def __init__(
        self,
        fetched: Fetched,
        jurisdiction: str,
        record_key: str,
        record_type: str,
        raw: Any,
    ) -> None:
        self.raw_sha256 = sha256_hex(canonical_json(raw))
        self.source_record_id = stable_id(fetch_id(fetched), record_type, record_key)
        self.fetched = fetched
        self.jurisdiction = jurisdiction
        self.record_key = record_key
        self.record_type = record_type

    def source_record(self) -> NormalizedRow:
        at: datetime = self.fetched.retrieved_at
        return NormalizedRow(
            "source_record",
            {
                "source_record_id": self.source_record_id,
                "fetch_id": fetch_id(self.fetched),
                "source_id": self.fetched.source_id,
                "record_key": self.record_key,
                "record_type": self.record_type,
                "raw_sha256": self.raw_sha256,
                "first_seen_at": at,
                "last_seen_at": at,
            },
        )

    def fact(self, table: str, **row: Any) -> NormalizedRow:
        return NormalizedRow(
            table,
            {
                **row,
                "source_record_id": self.source_record_id,
                "source_id": self.fetched.source_id,
                "jurisdiction": self.jurisdiction,
                "record_key": self.record_key,
                "source_uri": f"{self.fetched.request}#{self.record_key}",
                "retrieved_at": self.fetched.retrieved_at,
                "content_sha256": self.raw_sha256,
            },
        )
