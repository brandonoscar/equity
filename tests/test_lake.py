"""Lake: export a loaded DB to Parquet, rebuild the catalog of views, gates still pass."""

from __future__ import annotations

import json
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


def test_write_plan_adds_params_and_refuses_after_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    import json

    from .test_ingest import Planned

    monkeypatch.setattr(lake, "LAKE", tmp_path / "lake")
    monkeypatch.setattr(lake, "WORK", tmp_path / "work")
    monkeypatch.setattr("equity.adapters.registry.by_source_id", lambda sid: Planned)
    assert lake.main(["plan", "test.tiny", "--set", "codes=A|B"]) == 0
    assert "2 partitions planned" in capsys.readouterr().out
    plan = json.loads((tmp_path / "lake" / "test.tiny" / "_plan.json").read_text())
    assert all(p["codes"] == "A|B" for p in plan) and len(plan) == 2
    (tmp_path / "lake" / "test.tiny" / "_parts").mkdir()
    (tmp_path / "lake" / "test.tiny" / "_parts" / "00000.json").write_text("{}")
    with pytest.raises(RuntimeError, match="already built"):
        lake.write_plan("test.tiny", {}, tmp_path / "lake")


def test_host_comes_from_the_url_attribute_or_the_source_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class WithUrl:
        layer_url = "https://gis.example.gov/arcgis/rest/services/X/MapServer/0"

    class WithRow:
        def source_row(self) -> dict[str, str]:
            return {"base_url": "https://data.example.gov/resource/abcd-1234.json"}

    class Neither:
        def source_row(self) -> dict[str, str]:
            return {}

    classes = {"a": WithUrl, "b": WithRow, "c": Neither}
    monkeypatch.setattr("equity.adapters.registry.by_source_id", lambda sid: classes[sid])
    assert lake._host("a") == "gis.example.gov"
    assert lake._host("b") == "data.example.gov"  # one host = one build at a time
    assert lake._host("c") == "c"


def test_single_store_sources_load_every_partition_into_one_part(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from .test_ingest import Planned

    class Series(Planned):
        single_store = True

    monkeypatch.setattr(lake, "LAKE", tmp_path / "lake")
    monkeypatch.setattr(lake, "WORK", tmp_path / "work")
    monkeypatch.setattr("equity.adapters.registry.by_source_id", lambda sid: Series)
    out = tmp_path / "lake" / "test.tiny"
    (out / "parcel").mkdir(parents=True)
    (out / "parcel" / "00007.parquet").write_bytes(b"stale")
    counts = lake.build("test.tiny", raw_dir=tmp_path / "raw")
    assert counts["parcel"] == 3
    assert sorted(p.name for p in (out / "parcel").glob("*.parquet")) == ["00000.parquet"]
    assert not list((tmp_path / "work").glob("*.duckdb"))


def test_replan_keeps_finished_parts_and_splits_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lake, "WORK", tmp_path / "work")
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "s-00001.duckdb").write_text("stale")

    class Splitter:
        def split_partition(self, params: dict[str, str]) -> list[dict[str, str]]:
            if params["county_fips"] == "003":
                return []  # empty county
            return [{**params, "oid_min": str(i), "oid_max": str(i + 1)} for i in (1, 2)]

    monkeypatch.setattr("equity.adapters.registry.by_source_id", lambda sid: Splitter)
    out = tmp_path / "lake" / "s"
    (out / "_parts").mkdir(parents=True)
    (out / "parcel").mkdir()
    plan = [{"county_fips": c} for c in ("001", "002", "003", "004")]
    (out / "_plan.json").write_text(json.dumps(plan))
    for i in (1, 3):  # counties 002 and 004 are finished
        (out / "_parts" / f"{i:05d}.json").write_text(json.dumps({"params": plan[i]}))
        (out / "parcel" / f"{i:05d}.parquet").write_text(f"part{i}")
    kept, pending = lake.replan("s", tmp_path / "lake")
    assert (kept, pending) == (2, 2)
    new = json.loads((out / "_plan.json").read_text())
    assert new[:2] == [{"county_fips": "002"}, {"county_fips": "004"}]
    assert new[2:] == [{"county_fips": "001", "oid_min": "1", "oid_max": "2"},
                       {"county_fips": "001", "oid_min": "2", "oid_max": "3"}]  # fmt: skip
    assert (out / "parcel" / "00000.parquet").read_text() == "part1"
    assert (out / "parcel" / "00001.parquet").read_text() == "part3"
    assert sorted(p.name for p in (out / "_parts").iterdir()) == ["00000.json", "00001.json"]
    assert not (tmp_path / "work" / "s-00001.duckdb").exists()
    # Replanning again folds the old windows back into their county and re-cuts it.
    assert lake.replan("s", tmp_path / "lake") == (2, 2)
    assert json.loads((out / "_plan.json").read_text()) == new


def test_source_lists_are_complete_in_a_fresh_interpreter() -> None:
    """Regression: an import change once left the runner and the health check with an empty
    adapter list. Inside pytest other tests have already registered every adapter, so each
    entry point is checked in its own clean process, importing only what its CLI imports."""
    import subprocess
    import sys

    def fresh(code: str) -> list[str]:
        run = subprocess.run([sys.executable, "-c", code], check=True,  # noqa: S603
                             capture_output=True, text=True)  # fmt: skip
        return run.stdout.split()

    n, has_tx, has_fl, has_acris = fresh(
        "from equity import lake\n"
        "s = lake.parcel_sources()\n"
        "print(len(s), 'tx.statewide.parcels' in s, 'fl.statewide.parcels' in s,\n"
        "      'ny.nyc.acris.real' in s)\n"
    )
    assert int(n) > 50 and has_tx == "True" and has_fl == "True" and has_acris == "True"
    (adapters,) = fresh("from equity.adapters import health\nprint(len(health.REGISTRY))\n")
    assert int(adapters) > int(n)


def test_host_groups_list_unfinished_sources_by_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hosts = {"fl.a.parcels": "h1", "fl.b.parcels": "h1", "ny.c.parcels": "h2", "zz.d.zoning": "h3"}
    monkeypatch.setattr(lake, "parcel_sources", lambda: list(hosts))
    monkeypatch.setattr(lake, "_host", hosts.__getitem__)
    (tmp_path / "zz.d.zoning").mkdir()
    (tmp_path / "zz.d.zoning" / "_counts.json").write_text("{}")  # finished: left out
    assert lake.host_groups(tmp_path) == [
        {"host": "h1", "sources": "fl.a.parcels fl.b.parcels"},
        {"host": "h2", "sources": "ny.c.parcels"},
    ]


def test_export_splits_tables_too_big_for_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import duckdb

    work = tmp_path / "work.duckdb"
    run_manifest(str(work), SYNTHETIC_MANIFEST).close()
    out = tmp_path / "lake" / "fixture.synthetic"
    whole = lake.export_part(work, out, "00007")
    (out / "instrument" / "00007_9.parquet").write_bytes(b"stale chunk from an older export")
    size = (out / "instrument" / "00007.parquet").stat().st_size
    monkeypatch.setattr(lake, "SPLIT_BYTES", size - 1)  # instrument is just "too big"
    monkeypatch.setattr(lake, "CHUNK_BYTES", size // 2 + 1)
    assert lake.export_part(work, out, "00007") == whole
    files = sorted(p.name for p in (out / "instrument").iterdir())
    assert files == ["00007.parquet", "00007_1.parquet"]  # two chunks, stale one removed
    con = duckdb.connect()
    src = duckdb.connect(str(work), read_only=True)
    got = con.execute(
        f"SELECT count(*), bit_xor(hash(instrument_uid)) "
        f"FROM '{(out / 'instrument').as_posix()}/*.parquet'"
    ).fetchone()
    assert got == src.execute(
        "SELECT count(*), bit_xor(hash(instrument_uid)) FROM instrument").fetchone()  # fmt: skip


def test_replan_renames_split_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lake, "WORK", tmp_path / "work")
    monkeypatch.setattr("equity.adapters.registry.by_source_id", lambda sid: object)
    out = tmp_path / "lake" / "s"
    (out / "_parts").mkdir(parents=True)
    (out / "party").mkdir()
    (out / "_plan.json").write_text(json.dumps([{"a": "0"}, {"a": "1"}]))
    (out / "_parts" / "00001.json").write_text("{}")
    (out / "party" / "00001.parquet").write_text("first")
    (out / "party" / "00001_1.parquet").write_text("second")
    assert lake.replan("s", tmp_path / "lake") == (1, 1)
    assert sorted(p.name for p in (out / "party").iterdir()) == ["00000.parquet",
                                                                 "00000_1.parquet"]  # fmt: skip
    assert (out / "party" / "00000_1.parquet").read_text() == "second"


def test_a_part_whose_facts_lack_provenance_is_not_exported(tmp_path: Path) -> None:
    from equity.lake import QualityError, export_part
    from equity.schema.migrate import connect, migrate
    from tests.conftest import T0, fixed_clock

    db = tmp_path / "w.duckdb"
    con = connect(str(db))
    migrate(con, fixed_clock(T0))
    # A party row whose source_record_id points at nothing: provenance broken.
    con.execute(
        "INSERT INTO party (row_id, party_id, raw_name, party_kind, source_record_id, source_id,"
        " jurisdiction, record_key, source_uri, retrieved_at, content_sha256, ingested_at,"
        " fact_hash) VALUES ('r1', 'p1', 'X', 'unknown', 'missing', 'zz.src', '99001', 'k',"
        " 'file://x', TIMESTAMPTZ '2026-01-01 00:00:00+00', repeat('a', 64),"
        " TIMESTAMPTZ '2026-01-01 00:00:00+00', repeat('b', 64))"
    )
    con.close()
    out = tmp_path / "zz.src"
    with pytest.raises(QualityError, match="provenance"):
        export_part(db, out, "00001")
    assert not (out / "party").exists()  # nothing exported for the failed part
    assert "provenance" in (out / "_quality" / "00001.json").read_text()


def test_a_clean_part_exports_without_a_quality_report(tmp_path: Path) -> None:
    from equity.lake import export_part
    from equity.schema.migrate import connect, migrate
    from tests.conftest import T0, fixed_clock

    db = tmp_path / "w.duckdb"
    con = connect(str(db))
    migrate(con, fixed_clock(T0))
    con.close()
    out = tmp_path / "zz.src"
    counts = export_part(db, out, "00001")
    assert "party" not in counts  # empty tables are not exported
    assert not (out / "_quality").exists()
