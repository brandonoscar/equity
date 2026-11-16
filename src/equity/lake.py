"""The parcel lake: one Parquet folder per source, one DuckDB catalog of views over all of it.

    uv run python -m equity.lake build wv.statewide.parcels      # ingest + export one source
    uv run python -m equity.lake run --max-parallel 6            # every source, by priority
    uv run python -m equity.lake catalog                         # (re)build catalog views
    uv run python -m equity.lake status                          # rows per source
    uv run python -m equity.lake plan ny.nyc.acris.real --set codes='JUDG|TLS'   # subset plan

Each source is ingested into a scratch DuckDB, exported to zstd Parquet under
data/lake/<source_id>/<table>.parquet, and the scratch file is deleted. Raw responses stay
gzipped under data/raw/. The catalog (data/catalog.duckdb) holds only views, so it is rebuilt
in seconds and every query sees all loaded sources.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb

from equity.schema.catalog import FACT_TABLES, all_tables
from equity.schema.clock import system_clock
from equity.schema.migrate import connect, migrate

DATA = Path("data")
LAKE = DATA / "lake"
WORK = DATA / "work"
CATALOG = DATA / "catalog.duckdb"
# Highest value first: pilot state, then states where judgments are enforced, then the rest.
PRIORITY = ("wv.", "fl.", "nc.", "oh.", "pa.", "ga.", "al.", "la.", "sc.", "mi.", "il.", "ny.",
            "in.", "tx.", "ca.", "nj.")  # fmt: skip


def export_part(work_db: Path, out_dir: Path, part: str) -> dict[str, int]:
    """Copy every non-empty table of a scratch DB to out_dir/<table>/<part>.parquet (zstd)."""
    con = duckdb.connect(str(work_db), read_only=True)
    counts: dict[str, int] = {}
    try:
        for table in all_tables():
            row = con.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
            n = 0 if row is None else int(row[0])
            if n == 0:
                continue
            target = out_dir / table / f"{part}.parquet"
            target.parent.mkdir(parents=True, exist_ok=True)
            con.execute(
                f"COPY (SELECT * FROM {table}) TO '{target.as_posix()}' "  # noqa: S608
                "(FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            counts[table] = n
    finally:
        con.close()
    return counts


def export_source(work_db: Path, out_dir: Path) -> dict[str, int]:
    """Export a whole scratch DB as one part and write the source's _counts.json."""
    counts = export_part(work_db, out_dir, "00000")
    (out_dir / "_counts.json").write_text(json.dumps(counts, indent=2, sort_keys=True))
    return counts


def build(source_id: str, raw_dir: Path = DATA / "raw") -> dict[str, int]:
    """Ingest one source partition by partition. Each partition gets a small scratch DB,
    is exported to its own Parquet part and marked done, so disk stays bounded and an
    interrupted build resumes where it stopped. (First-load semantics: partitions of one
    source never share domain keys, so per-partition loading equals a whole-source load.)"""
    from equity.adapters.registry import by_source_id
    from equity.ingest import partitions, run

    WORK.mkdir(parents=True, exist_ok=True)
    out = LAKE / source_id
    done_dir = out / "_parts"
    done_dir.mkdir(parents=True, exist_ok=True)
    adapter = by_source_id(source_id)()  # type: ignore[abstract]
    plan_path = out / "_plan.json"
    if plan_path.exists():
        requests = json.loads(plan_path.read_text())
    else:
        requests = list(partitions(adapter))
        plan_path.write_text(json.dumps(requests, indent=1))
    if getattr(adapter, "single_store", False):
        return _build_single_store(source_id, adapter, requests, out, raw_dir)
    for i, params in enumerate(requests):
        part = f"{i:05d}"
        marker = done_dir / f"{part}.json"
        if marker.exists():
            continue
        work_db = WORK / f"{source_id}-{part}.duckdb"
        work_db.unlink(missing_ok=True)
        run(adapter, str(work_db), raw_dir, [params])
        counts = export_part(work_db, out, part)
        marker.write_text(json.dumps({"params": params, "counts": counts}, sort_keys=True))
        work_db.unlink(missing_ok=True)
        Path(str(work_db) + ".wal").unlink(missing_ok=True)
    total: dict[str, int] = defaultdict(int)
    for m in done_dir.glob("*.json"):
        for t, n in json.loads(m.read_text())["counts"].items():
            total[t] += n
    (out / "_counts.json").write_text(json.dumps(dict(total), indent=2, sort_keys=True))
    return dict(total)


def _build_single_store(
    source_id: str, adapter: Any, requests: list[dict[str, str]], out: Path, raw_dir: Path
) -> dict[str, int]:
    """Snapshot series (weekly lists, daily files with corrections): one key can come back in
    a later partition, so every partition is loaded in order into ONE store, where the loader
    supersedes or keeps rows, and exported as one part. Rebuilt whole each time."""
    from equity.ingest import run

    work_db = WORK / f"{source_id}-all.duckdb"
    work_db.unlink(missing_ok=True)
    run(adapter, str(work_db), raw_dir, requests)
    for old in out.glob("*/*.parquet"):
        old.unlink()
    counts = export_part(work_db, out, "00000")
    work_db.unlink(missing_ok=True)
    Path(str(work_db) + ".wal").unlink(missing_ok=True)
    (out / "_counts.json").write_text(json.dumps(counts, indent=2, sort_keys=True))
    return counts


def write_plan(source_id: str, extra: dict[str, str], lake: Path | None = None) -> int:
    """Write a source's partition plan with `extra` params added to every partition (e.g. a
    doc-code filter), so a later `build` loads that subset. Refuses once building started:
    finished parts were made under the old plan."""
    from equity.adapters.registry import by_source_id
    from equity.ingest import partitions

    out = (lake or LAKE) / source_id
    if any((out / "_parts").glob("*.json")):
        raise RuntimeError(f"{source_id}: parts already built; remove {out} to re-plan")
    out.mkdir(parents=True, exist_ok=True)
    adapter = by_source_id(source_id)()  # type: ignore[abstract]
    requests = [{**params, **extra} for params in partitions(adapter)]
    (out / "_plan.json").write_text(json.dumps(requests, indent=1))
    return len(requests)


def build_catalog(lake: Path = LAKE, catalog: Path = CATALOG) -> list[str]:
    """Views named like the schema tables, each reading that table's Parquet parts from every
    source folder. Tables without any Parquet yet stay as empty migrated tables."""
    catalog.unlink(missing_ok=True)
    con = connect(str(catalog))
    migrate(con, system_clock)
    made: list[str] = []
    for table in all_tables():
        files = sorted(lake.glob(f"*/{table}/*.parquet"))
        if not files:
            continue
        paths = ", ".join(f"'{p.as_posix()}'" for p in files)
        # Lookup/provenance rows (source, address, ...) repeat across parts: dedupe them.
        distinct = "" if table in FACT_TABLES else "DISTINCT "
        con.execute(f"DROP TABLE {table}")
        con.execute(
            f"CREATE VIEW {table} AS SELECT {distinct}* FROM "  # noqa: S608
            f"read_parquet([{paths}], union_by_name = true)"
        )
        made.append(table)
    con.close()
    return made


def _host(source_id: str) -> str:
    from equity.adapters.registry import by_source_id

    cls = by_source_id(source_id)
    url = getattr(cls, "layer_url", "") or getattr(cls, "url", "")
    if not url:
        # Adapters without a URL attribute name their endpoint in the source row.
        url = cls().source_row().get("base_url", "")  # type: ignore[abstract]
    return urllib.parse.urlsplit(str(url)).netloc or source_id


def plan(source_ids: list[str]) -> list[str]:
    def rank(sid: str) -> tuple[int, str]:
        for i, prefix in enumerate(PRIORITY):
            if sid.startswith(prefix):
                return i, sid
        return len(PRIORITY), sid

    return sorted(source_ids, key=rank)


def run_all(max_parallel: int, min_free_gb: float, only: list[str] | None = None) -> None:
    """Build sources in priority order, at most one per host at a time, stopping new builds
    when free disk drops below min_free_gb."""
    from equity.adapters.registry import REGISTRY

    wanted = (".parcels",)
    parcel_sources = [
        c.source_id for c in REGISTRY
        if c.source_id.endswith(wanted) or c.source_id == "wv.statewide.delinquent"
    ]  # fmt: skip
    queue = plan(only or parcel_sources)
    queue = [s for s in queue if not (LAKE / s / "_counts.json").exists()]
    running: dict[str, tuple[subprocess.Popen[bytes], str]] = {}
    busy_hosts: set[str] = set()
    hosts = {s: _host(s) for s in queue}
    logs = DATA / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    while queue or running:
        for sid, (proc, host) in list(running.items()):
            if proc.poll() is not None:
                print(f"done {sid} rc={proc.returncode}", flush=True)
                busy_hosts.discard(host)
                del running[sid]
        free_gb = shutil.disk_usage(DATA).free / 1e9
        for sid in list(queue):
            if len(running) >= max_parallel or free_gb < min_free_gb:
                break
            if hosts[sid] in busy_hosts:
                continue
            log = (logs / f"lake_{sid}.log").open("wb")
            proc = subprocess.Popen(  # noqa: S603
                [sys.executable, "-m", "equity.lake", "build", sid], stdout=log, stderr=log
            )
            running[sid] = (proc, hosts[sid])
            busy_hosts.add(hosts[sid])
            queue.remove(sid)
            print(f"start {sid} on {hosts[sid]} (free {free_gb:.1f} GB)", flush=True)
        if free_gb < min_free_gb and not running:
            print(f"stopping: {free_gb:.1f} GB free < {min_free_gb} GB; left: {queue}")
            break
        time.sleep(5)
    build_catalog()


def status(lake: Path = LAKE) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for f in sorted(lake.glob("*/_counts.json")):
        out[f.parent.name] = json.loads(f.read_text())
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="equity.lake")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("source_id")
    r = sub.add_parser("run")
    r.add_argument("--max-parallel", type=int, default=6)
    r.add_argument("--min-free-gb", type=float, default=5.0)
    r.add_argument("--only", nargs="*")
    pl = sub.add_parser("plan")
    pl.add_argument("source_id")
    pl.add_argument("--set", nargs="*", default=[], help="key=value added to every partition")
    sub.add_parser("catalog")
    sub.add_parser("status")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        print(json.dumps(build(args.source_id), indent=2, sort_keys=True))
    elif args.cmd == "run":
        run_all(args.max_parallel, args.min_free_gb, args.only)
    elif args.cmd == "plan":
        extra = dict(kv.split("=", 1) for kv in args.set)
        print(f"{args.source_id}: {write_plan(args.source_id, extra)} partitions planned")
    elif args.cmd == "catalog":
        print(build_catalog())
    else:
        st = status()
        total = sum(v.get("parcel", 0) for v in st.values())
        print(json.dumps({"sources": st, "total_parcels": total}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
