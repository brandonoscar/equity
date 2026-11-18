"""Ingest runner: raw bytes kept, provenance loaded first, partitions planned. Offline."""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import pytest

from equity import ingest
from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.rows import RecordContext
from equity.quality.gates import provenance_violations
from equity.schema.clock import fixed_clock
from equity.schema.migrate import connect

AT = datetime(2026, 11, 15, tzinfo=UTC)


class Tiny(Adapter):
    source_id: ClassVar[str] = "test.tiny"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"

    def source_row(self) -> Mapping[str, Any]:
        return {"source_id": self.source_id, "kind": "fixture", "jurisdiction": "99001",
                "access_method": "fixture", "base_url": "mem://", "terms_summary": "t",
                "cost_model": "free"}  # fmt: skip

    def fetch(self, request: FetchRequest) -> Fetched:
        body = json.dumps({"ids": request.params.get("ids", "1,2").split(",")}).encode()
        return Fetched(self.source_id, f"mem://tiny?{request.params}", AT, 200, body, "json")

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        for pid in json.loads(fetched.content)["ids"]:
            ctx = RecordContext(fetched, "99001", pid, "row", {"id": pid})
            yield ctx.fact("parcel", parcel_uid=f"99001-{pid}", parid_raw=pid)
            yield ctx.source_record()  # deliberately after the fact: loader must reorder

    def health(self) -> HealthReport:  # pragma: no cover - not exercised offline
        return HealthReport(self.source_id, True, AT, "ok")


class Planned(Tiny):
    def partitions(self) -> Iterator[dict[str, str]]:
        yield {"ids": "1"}
        yield {"ids": "2,3"}


def test_run_stores_raw_and_loads(tmp_path: Path) -> None:
    lines: list[str] = []
    db = str(tmp_path / "x.duckdb")
    stats = ingest.run(Tiny(), db, tmp_path / "raw", [{"ids": "1,2"}], fixed_clock(AT),
                       log=lines.append)  # fmt: skip
    assert stats.by_table["parcel"] == 2
    assert lines and "+" in lines[0]
    raws = list((tmp_path / "raw" / "test.tiny").glob("*.gz"))
    assert len(raws) == 1
    with gzip.open(raws[0]) as fh:
        assert json.loads(fh.read())["ids"] == ["1", "2"]
    con = connect(db)
    assert provenance_violations(con, ["parcel"]) == []
    assert con.execute("SELECT raw_path FROM fetch_log").fetchone()[0].endswith(".gz")  # type: ignore[index]


def test_partitions_default_and_planned() -> None:
    assert list(ingest.partitions(Tiny())) == [{}]
    assert list(ingest.partitions(Planned())) == [{"ids": "1"}, {"ids": "2,3"}]


def test_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("equity.adapters.registry.by_source_id", lambda sid: Planned)
    db = tmp_path / "sub" / "x.duckdb"
    assert ingest.main(["test.tiny", "--db", str(db), "--raw", str(tmp_path / "r"), "--all"]) == 0
    out = capsys.readouterr().out
    assert '"parcel": 3' in out
    assert ingest.main(["test.tiny", "--db", str(db), "--raw", str(tmp_path / "r"),
                        "--partition", "ids=1"]) == 0  # fmt: skip
    second = json.loads(capsys.readouterr().out.split("\n", 1)[1])
    # Same request at the same (fixed) instant = the same fetch: everything is a no-op.
    assert second["inserted"] == 0
    assert second["unchanged"] == 4  # source, fetch_log, source_record, parcel
