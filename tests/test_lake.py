"""Lake: export a loaded DB to Parquet, rebuild the catalog of views, gates still pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from equity import lake
from equity.config import doc_types
from equity.pipeline import run_manifest
from equity.quality.gates import invariant_violations, provenance_violations
from equity.schema.migrate import connect

from .conftest import SYNTHETIC_MANIFEST


def test_export_catalog_and_gates(tmp_path: Path) -> None:
    work = tmp_path / "work.duckdb"
    run_manifest(str(work), SYNTHETIC_MANIFEST).close()
    counts = lake.export_source(work, tmp_path / "lake" / "fixture.synthetic")
    assert counts["instrument"] == 10
    assert "entity" not in counts  # empty tables are not exported
    made = lake.build_catalog(tmp_path / "lake", tmp_path / "catalog.duckdb")
    assert "parcel" in made
    con = connect(str(tmp_path / "catalog.duckdb"))
    assert con.execute("SELECT count(*) FROM instrument").fetchone() == (10,)
    assert provenance_violations(con) == []
    assert invariant_violations(con, doc_types()) == []
    st = lake.status(tmp_path / "lake")
    assert st["fixture.synthetic"]["parcel"] == 2


def test_build_is_partitioned_and_resumable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from .test_ingest import Planned

    monkeypatch.setattr(lake, "LAKE", tmp_path / "lake")
    monkeypatch.setattr(lake, "WORK", tmp_path / "work")
    monkeypatch.setattr("equity.adapters.registry.by_source_id", lambda sid: Planned)
    first = lake.build("test.tiny", raw_dir=tmp_path / "raw")
    assert first["parcel"] == 3
    out = tmp_path / "lake" / "test.tiny"
    assert sorted(p.name for p in (out / "parcel").glob("*.parquet")) == [
        "00000.parquet",
        "00001.parquet",
    ]
    assert not list((tmp_path / "work").glob("*.duckdb"))  # scratch removed
    (out / "_parts" / "00001.json").unlink()  # simulate an interrupted build
    again = lake.build("test.tiny", raw_dir=tmp_path / "raw")
    assert again == first
    made = lake.build_catalog(tmp_path / "lake", tmp_path / "cat.duckdb")
    con = connect(str(tmp_path / "cat.duckdb"))
    assert "source" in made
    assert con.execute("SELECT count(*) FROM source").fetchone() == (1,)  # deduped across parts
    assert con.execute("SELECT count(*) FROM parcel").fetchone() == (3,)


def test_plan_orders_by_priority() -> None:
    order = lake.plan(["zz.x.parcels", "fl.statewide.parcels", "wv.statewide.parcels",
                       "ga.fulton.parcels"])  # fmt: skip
    assert order == ["wv.statewide.parcels", "fl.statewide.parcels", "ga.fulton.parcels",
                     "zz.x.parcels"]  # fmt: skip


def test_main_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(lake, "LAKE", tmp_path)
    monkeypatch.setattr(lake, "status", lambda lake_dir=tmp_path: {"a": {"parcel": 3}})
    assert lake.main(["status"]) == 0
    assert '"total_parcels": 3' in capsys.readouterr().out
