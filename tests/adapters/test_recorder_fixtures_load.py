"""The recorder adapters' fixture rows load into the real schema (CHECK constraints, enums)
when retrieved after the records were made, and pass the provenance gate."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from equity.adapters.base import Fetched
from equity.adapters.registry import by_source_id
from equity.adapters.rows import fetch_id
from equity.quality.gates import provenance_violations
from equity.schema.clock import fixed_clock
from equity.schema.ids import sha256_hex
from equity.schema.load import load_rows

FIX = Path(__file__).parents[1] / "fixtures" / "adapters"
AT = datetime(2026, 11, 16, 12, tzinfo=UTC)
CLOCK = fixed_clock(datetime(2026, 11, 16, 13, tzinfo=UTC))


@pytest.mark.parametrize(
    "source_id",
    [
        "ny.nyc.acris.real",
        "ny.nyc.acris.personal",
        "pa.philadelphia.rtt",
        "fl.hillsborough.or",
        "ny.sos.business",
        "co.sos.business",
        "ct.sos.business",
        "or.sos.business",
        "ia.sos.business",
        "ri.sos.business",
    ],
)
def test_fixture_rows_load(source_id: str, empty_db: duckdb.DuckDBPyConnection) -> None:
    cls = by_source_id(source_id)
    adapter = cls()  # type: ignore[abstract]
    load_rows(empty_db, "source", [dict(adapter.source_row())], CLOCK)
    path = next((FIX / source_id).resolve().glob("*.json"))
    content = path.read_bytes()
    fetched = Fetched(source_id, path.as_uri(), AT, 200, content, "application/json")
    load_rows(empty_db, "fetch_log", [{
        "fetch_id": fetch_id(fetched), "source_id": source_id, "adapter": cls.__name__,
        "adapter_version": cls.adapter_version, "request": fetched.request,
        "retrieved_at": AT, "http_status": 200, "content_sha256": sha256_hex(content),
        "raw_path": str(path), "bytes": len(content),
    }], CLOCK)  # fmt: skip
    rows = list(adapter.normalize(fetched))
    for item in rows:
        load_rows(empty_db, item.table, [dict(item.row)], CLOCK)
    table = ("business" if ".sos." in source_id
             else "court_case" if "civil" in source_id or "garnish" in source_id
             else "instrument")  # fmt: skip
    n = empty_db.execute(f"SELECT count(*) FROM {table}").fetchone()
    assert n is not None and n[0] > 0
    assert provenance_violations(empty_db) == []
