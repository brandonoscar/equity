"""Check 7: every registered adapter implements fetch/normalize/health, and normalize() output
on each recorded fixture loads into the schema and passes the provenance gate.

Fixtures live in tests/fixtures/adapters/<source_id>/ as raw files exactly as fetched.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import pytest

from equity.adapters import health
from equity.adapters.base import (
    Adapter,
    Fetched,
    FetchRequest,
    HealthReport,
    NormalizedRow,
    register,
)
from equity.adapters.registry import REGISTRY
from equity.adapters.rows import fetch_id
from equity.quality.gates import provenance_violations
from equity.schema.clock import fixed_clock
from equity.schema.ids import sha256_hex
from equity.schema.load import load_rows

ADAPTER_FIXTURES = Path(__file__).parent / "fixtures" / "adapters"
CLOCK = fixed_clock(datetime(2026, 1, 1, tzinfo=UTC))


def check_contract(cls: type[Adapter], fixture_files: list[Path], con) -> None:  # type: ignore[no-untyped-def]
    for name in ("fetch", "normalize", "health", "source_row"):
        method = getattr(cls, name)
        assert not getattr(method, "__isabstractmethod__", False), f"{cls.__name__}.{name}"
    assert inspect.isclass(cls) and issubclass(cls, Adapter)
    assert cls.access_method in {"bulk", "api", "arcgis", "feed", "html", "manual"}
    assert fixture_files, f"{cls.source_id}: no recorded fixtures"
    adapter = cls()
    load_rows(con, "source", [dict(adapter.source_row())], CLOCK)
    for path in fixture_files:
        content = path.read_bytes()
        fetched = Fetched(
            cls.source_id,
            path.as_uri(),
            datetime(2025, 12, 31, tzinfo=UTC),
            200,
            content,
            "application/octet-stream",
        )
        load_rows(con, "fetch_log", [{
            "fetch_id": fetch_id(fetched), "source_id": cls.source_id,
            "adapter": cls.__name__, "adapter_version": cls.adapter_version,
            "request": fetched.request, "retrieved_at": fetched.retrieved_at,
            "http_status": 200, "content_sha256": sha256_hex(content),
            "raw_path": str(path), "bytes": len(content),
        }], CLOCK)  # fmt: skip
        first = list(adapter.normalize(fetched))
        second = list(adapter.normalize(fetched))
        assert first == second, f"{cls.source_id}: normalize() is not deterministic"
        assert first, f"{path.name}: normalize() produced nothing"
        for item in first:
            load_rows(con, item.table, [dict(item.row)], CLOCK)
    assert provenance_violations(con) == []


def test_registered_adapters(empty_db) -> None:  # type: ignore[no-untyped-def]
    # A loop, not parametrize: with zero adapters this passes instead of reporting a skip.
    for cls in REGISTRY:
        files = sorted((ADAPTER_FIXTURES / cls.source_id).glob("*"))
        check_contract(cls, files, empty_db)


def test_every_fixture_dir_has_an_adapter() -> None:
    registered = {c.source_id for c in REGISTRY}
    dirs = (
        {p.name for p in ADAPTER_FIXTURES.iterdir() if p.is_dir()}
        if ADAPTER_FIXTURES.exists()
        else set()
    )
    assert dirs <= registered, f"fixtures without adapters: {sorted(dirs - registered)}"


# --- The harness itself is tested against a minimal in-test adapter. ---------------------


class _Dummy(Adapter):
    source_id: ClassVar[str] = "test.dummy"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"

    def source_row(self) -> Mapping[str, Any]:
        return {"source_id": self.source_id, "kind": "fixture", "jurisdiction": "99001",
                "access_method": "fixture", "base_url": "file://dummy",
                "terms_summary": "test", "cost_model": "free"}  # fmt: skip

    def fetch(self, request: FetchRequest) -> Fetched:  # pragma: no cover - never called offline
        raise NotImplementedError

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        sha = sha256_hex(fetched.content)
        srid = f"sr-{sha[:16]}"
        yield NormalizedRow("source_record", {
            "source_record_id": srid, "fetch_id": fetch_id(fetched), "source_id": self.source_id,
            "record_key": "K1", "record_type": "row", "raw_sha256": sha,
            "first_seen_at": fetched.retrieved_at, "last_seen_at": fetched.retrieved_at,
        })  # fmt: skip
        yield NormalizedRow("parcel", {
            "parcel_uid": "99001-77-77-0001", "parid_raw": fetched.content.decode().strip(),
            "source_record_id": srid, "source_id": self.source_id, "jurisdiction": "99001",
            "record_key": "K1", "source_uri": fetched.request,
            "retrieved_at": fetched.retrieved_at, "content_sha256": sha,
        })  # fmt: skip

    def health(self) -> HealthReport:
        return HealthReport(self.source_id, True, datetime(2026, 1, 1, tzinfo=UTC), "ok")


def test_harness_accepts_a_conforming_adapter(empty_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    raw = tmp_path / "page1.txt"
    raw.write_text("77-77-0001\n")
    check_contract(_Dummy, [raw], empty_db)


def test_harness_rejects_missing_fixtures(empty_db) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(AssertionError, match="no recorded fixtures"):
        check_contract(_Dummy, [], empty_db)


def test_register_and_health_main(monkeypatch: pytest.MonkeyPatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("equity.adapters.base.REGISTRY", [])
    monkeypatch.setattr(health, "REGISTRY", [])
    assert health.main() == 0
    assert '"adapters": 0' in capsys.readouterr().out

    class _Broken(_Dummy):
        source_id: ClassVar[str] = "test.broken"

        def health(self) -> HealthReport:
            raise RuntimeError("portal changed")

    reg: list[type[Adapter]] = []
    monkeypatch.setattr("equity.adapters.base.REGISTRY", reg)
    register(_Dummy)
    with pytest.raises(ValueError, match="registered twice"):
        register(_Dummy)
    monkeypatch.setattr(health, "REGISTRY", [_Dummy, _Broken])
    assert health.main() == 1
    assert "portal changed" in capsys.readouterr().out
