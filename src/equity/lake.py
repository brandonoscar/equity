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
from datetime import datetime
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


# Object storage takes files up to lake_sync.MAX_BYTES (45 MB). A table file bigger than
# SPLIT_BYTES is rewritten as several files of about CHUNK_BYTES: <part>.parquet,
# <part>_1.parquet, ... Readers glob */<table>/*.parquet, so the split is invisible to them.
SPLIT_BYTES = 40_000_000
CHUNK_BYTES = 30_000_000


def _part_files(table_dir: Path, part: str) -> list[Path]:
    return sorted(table_dir.glob(f"{part}.parquet")) + sorted(table_dir.glob(f"{part}_*.parquet"))


class QualityError(RuntimeError):
    """A built part broke a provenance rule; it is not exported or marked finished."""


def check_part(con: duckdb.DuckDBPyConnection, out_dir: Path, part: str) -> None:
    """Run the quality gates on a scratch DB before its part is exported. Provenance
    violations (a fact row that does not trace to its source record, fetch and source) fail
    the part. Invariant violations are written to out_dir/_quality/<part>.json and logged,
    so real data that breaks one is visible without stopping every build."""
    from equity.config import doc_types
    from equity.quality.gates import invariant_violations, provenance_violations

    present = [
        t for t in sorted(FACT_TABLES)
        if (row := con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [t]
        ).fetchone()) and row[0]
        and (n := con.execute(f"SELECT count(*) FROM {t}").fetchone()) and n[0]  # noqa: S608
    ]  # fmt: skip
    hard = provenance_violations(con, present)
    soft = invariant_violations(con, doc_types())
    if soft or hard:
        qdir = out_dir / "_quality"
        qdir.mkdir(parents=True, exist_ok=True)
        (qdir / f"{part}.json").write_text(json.dumps(
            {"provenance": [str(v) for v in hard], "invariants": [str(v) for v in soft]},
            indent=1))  # fmt: skip
        for v in soft:
            print(f"quality warning {out_dir.name} {part}: {v}", flush=True)
    if hard:
        raise QualityError(f"{out_dir.name} {part}: " + "; ".join(str(v) for v in hard))


def export_part(work_db: Path, out_dir: Path, part: str) -> dict[str, int]:
    """Copy every non-empty table of a scratch DB to out_dir/<table>/<part>.parquet (zstd),
    split into <part>_<i>.parquet chunks when one file would exceed SPLIT_BYTES. The quality
    gates run first (check_part)."""
    con = duckdb.connect(str(work_db), read_only=True)
    counts: dict[str, int] = {}
    try:
        check_part(con, out_dir, part)
        for table in all_tables():
            row = con.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
            n = 0 if row is None else int(row[0])
            if n == 0:
                continue
            table_dir = out_dir / table
            table_dir.mkdir(parents=True, exist_ok=True)
            for old in _part_files(table_dir, part):  # an earlier export of this part
                old.unlink()
            # Write under a temporary name and rename when complete, so a build stopped
            # mid-write never leaves a truncated part for the catalog or the storage sync.
            whole = table_dir / f"{part}.parquet.tmp"
            con.execute(
                f"COPY (SELECT * FROM {table}) TO '{whole.as_posix()}' "  # noqa: S608
                "(FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            size = whole.stat().st_size
            if size <= SPLIT_BYTES:
                whole.replace(table_dir / f"{part}.parquet")
            else:
                chunks = -(-size // CHUNK_BYTES)
                step = -(-n // chunks)
                tmps = []
                for i in range(chunks):
                    tmp = table_dir / f"{part}_{i}.parquet.tmp"
                    con.execute(
                        f"COPY (SELECT * FROM {table} ORDER BY rowid LIMIT {step} "  # noqa: S608
                        f"OFFSET {i * step}) TO '{tmp.as_posix()}' "
                        "(FORMAT PARQUET, COMPRESSION ZSTD)"
                    )
                    tmps.append(tmp)
                for i, tmp in enumerate(tmps):
                    tmp.replace(
                        table_dir / (f"{part}.parquet" if i == 0 else f"{part}_{i}.parquet")
                    )
                whole.unlink()
            counts[table] = n
    finally:
        con.close()
    return counts


def drop_known(work_db: Path, out_dir: Path) -> dict[str, int]:
    """For a polled feed (append_polls: each poll is a new part of the same source): delete
    from the new poll's scratch DB every fact row already stored, unchanged, in an earlier
    part (same domain key and fact_hash), then the source records nothing points at any more.
    The fetch_log row stays, so every poll is on record. Returns rows dropped per table."""
    con = duckdb.connect(str(work_db))
    dropped: dict[str, int] = {}
    try:
        kept_records: list[str] = []
        for table, spec in sorted(FACT_TABLES.items()):
            exists = con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
            ).fetchone()
            if not exists or not exists[0]:
                continue
            kept_records.append(f"SELECT source_record_id FROM {table}")  # noqa: S608
            prior = (
                sorted((out_dir / table).glob("*.parquet")) if (out_dir / table).is_dir() else []
            )
            if not prior:
                continue
            cols = ["source_id", *spec.domain_key, "fact_hash"]
            paths = ", ".join(f"'{p.as_posix()}'" for p in prior)
            same = " AND ".join(f"p.{c} IS NOT DISTINCT FROM t.{c}" for c in cols)
            # Catalog table/column names and lake paths only.
            delete = (
                f"DELETE FROM {table} t WHERE EXISTS (SELECT 1 FROM "  # noqa: S608
                f"read_parquet([{paths}], union_by_name = true) p WHERE {same})"
            )
            row = con.execute(delete).fetchone()
            if row and row[0]:
                dropped[table] = int(row[0])
        if kept_records:
            row = con.execute(
                "DELETE FROM source_record WHERE source_record_id NOT IN "  # noqa: S608
                f"({' UNION '.join(kept_records)})"
            ).fetchone()
            if row and row[0]:
                dropped["source_record"] = int(row[0])
    finally:
        con.close()
    return dropped


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
    adapter = by_source_id(source_id)()
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
        if getattr(adapter, "append_polls", False):
            drop_known(work_db, out)
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


def replay(source_id: str, raw_dir: Path = DATA / "raw") -> dict[str, int]:
    """Re-normalize a built source from its stored raw responses, part by part, with the
    current adapter code (after a normalization fix) and without fetching anything. Each
    part's fetch_log names its raw files; a part whose raw files are missing is refused, so
    a replay never half-rebuilds a part. Exports go through the quality gates as in build."""
    import gzip

    from equity.adapters.base import Fetched
    from equity.adapters.registry import by_source_id
    from equity.ingest import load_fetched

    out = LAKE / source_id
    adapter = by_source_id(source_id)()
    parts = sorted(m.stem for m in (out / "_parts").glob("*.json"))
    plans: dict[str, list[Path]] = {}
    for part in parts:
        logs = _part_files(out / "fetch_log", part)
        if not logs:
            raise RuntimeError(f"{source_id} {part}: no fetch_log to replay")
        paths = ", ".join(f"'{p.as_posix()}'" for p in logs)
        q = duckdb.connect()
        sql = f"SELECT raw_path FROM read_parquet([{paths}]) ORDER BY retrieved_at"  # noqa: S608
        raws = [Path(str(r[0])) for r in q.execute(sql).fetchall()]
        q.close()
        missing = [r for r in raws if not r.exists() or not r.with_suffix(".json").exists()]
        if missing:
            raise RuntimeError(f"{source_id} {part}: raw responses missing: {missing[:3]}")
        plans[part] = raws
    WORK.mkdir(parents=True, exist_ok=True)
    for part, raws in plans.items():
        work_db = WORK / f"{source_id}-{part}.duckdb"
        work_db.unlink(missing_ok=True)
        con = connect(str(work_db))
        migrate(con, system_clock)
        for raw in raws:
            meta = json.loads(raw.with_suffix(".json").read_text())
            with gzip.open(raw, "rb") as fh:
                content = fh.read()
            when = datetime.fromisoformat(meta["retrieved_at"])
            fetched = Fetched(source_id, meta["request"], when, int(meta["http_status"]),
                              content, meta.get("content_type") or "")  # fmt: skip
            load_fetched(con, adapter, fetched, raw, system_clock)
        con.close()
        counts = export_part(work_db, out, part)
        marker = out / "_parts" / f"{part}.json"
        params = json.loads(marker.read_text()).get("params", {})
        marker.write_text(json.dumps({"params": params, "counts": counts}, sort_keys=True))
        work_db.unlink(missing_ok=True)
        Path(str(work_db) + ".wal").unlink(missing_ok=True)
        print(f"replayed {source_id} {part}", flush=True)
    total: dict[str, int] = defaultdict(int)
    for m in (out / "_parts").glob("*.json"):
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
    adapter = by_source_id(source_id)()
    requests = [{**params, **extra} for params in partitions(adapter)]
    (out / "_plan.json").write_text(json.dumps(requests, indent=1))
    return len(requests)


def replan(source_id: str, lake: Path | None = None) -> tuple[int, int]:
    """Re-cut the unfinished partitions of a source that is part-way built, keeping every
    finished part. Finished parts are renumbered to the front of the new plan (Parquet files
    and markers renamed to match); each unfinished partition is replaced by the adapter's
    split_partition() pieces. Returns (kept, new partitions)."""
    from equity.adapters.registry import by_source_id

    out = (lake or LAKE) / source_id
    plan = json.loads((out / "_plan.json").read_text())
    done_dir = out / "_parts"
    done = {int(m.stem) for m in done_dir.glob("*.json")}
    adapter = by_source_id(source_id)()
    split = getattr(adapter, "split_partition", None)
    kept = [i for i in range(len(plan)) if i in done]
    # Windows from an earlier replan are folded back into their county first, so replanning
    # again re-cuts them instead of keeping the old cut.
    todo: list[dict[str, str]] = []
    for i, params in enumerate(plan):
        if i in done:
            continue
        base = params
        if split and "county_fips" in params:
            base = {k: v for k, v in params.items() if k not in ("oid_min", "oid_max")}
        if base not in todo:
            todo.append(base)
    pending: list[dict[str, str]] = []
    for params in todo:
        pending.extend(split(params) if split else [params])
    # Two-phase rename so old and new part numbers never collide.
    moves = {old: new for new, old in enumerate(kept)}
    for stage in ("tmp", "final"):
        for old, new in moves.items():
            src_name = f"{old:05d}" if stage == "tmp" else f"tmp{old:05d}"
            dst_name = f"tmp{old:05d}" if stage == "tmp" else f"{new:05d}"
            for f in [*out.glob(f"*/{src_name}.parquet"), *out.glob(f"*/{src_name}_*.parquet")]:
                f.rename(f.with_name(dst_name + f.name[len(src_name) :]))
            (done_dir / f"{src_name}.json").rename(done_dir / f"{dst_name}.json")
    new_plan = [plan[i] for i in kept] + pending
    (out / "_plan.json").write_text(json.dumps(new_plan, indent=1))
    for w in WORK.glob(f"{source_id}-*.duckdb*"):
        w.unlink()
    return len(kept), len(pending)


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
        url = cls().source_row().get("base_url", "")
    return urllib.parse.urlsplit(str(url)).netloc or source_id


def host_groups(lake: Path = LAKE) -> list[dict[str, str]]:
    """Unfinished sources grouped by the host they load from, in priority order: one group
    per parallel loader, so each host still sees one build at a time."""
    groups: dict[str, list[str]] = defaultdict(list)
    for sid in plan(parcel_sources()):
        if not (lake / sid / "_counts.json").exists():
            groups[_host(sid)].append(sid)
    return [{"host": h, "sources": " ".join(s)} for h, s in groups.items()]


def plan(source_ids: list[str]) -> list[str]:
    def rank(sid: str) -> tuple[int, str]:
        for i, prefix in enumerate(PRIORITY):
            if sid.startswith(prefix):
                return i, sid
        return len(PRIORITY), sid

    return sorted(source_ids, key=rank)


# Sources `run` builds besides parcels, zoning and lien configs. ny.nyc.acris.real is loaded
# under a doc-code plan (deeds, mortgages, satisfactions, liens) written by `lake plan --set`;
# the plan is synced with the lake, so the hosted loader resumes it as planned.
EXTRA_SOURCES = ("wv.statewide.delinquent", "ny.nyc.acris.real", "ny.nyc.dof.condo_units",
                 "pa.allegheny.assessments", "hi.honolulu.owners", "co.sos.ucc",
                 "dc.dlcp.business", "pa.dos.business", "ny.sos.business", "ct.sos.business",
                 "co.sos.business", "or.sos.business",
                 "md.baltimore_city.citation_liens", "tx.harris.jp.judgments",
                 "tx.travis.tax_delinquent", "mi.detroit.blight_judgments",
                 "ne.douglas.tax_liens", "us.hud.fha_reo", "us.federalregister.realty_notices",
                 "us.sba.chargeoffs", "ny.sos.name_history")  # fmt: skip


def parcel_sources() -> list[str]:
    """Every registered parcel source (what `run` builds when not given --only)."""
    from equity.adapters.registry import REGISTRY

    return [
        c.source_id for c in REGISTRY
        if c.source_id.endswith((".parcels", ".zoning")) or c.source_id in EXTRA_SOURCES
        or c.__module__ == "equity.adapters.liens"
    ]  # fmt: skip


def run_all(max_parallel: int, min_free_gb: float, only: list[str] | None = None) -> None:
    """Build sources in priority order, at most one per host at a time, stopping new builds
    when free disk drops below min_free_gb."""
    queue = plan(only or parcel_sources())
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
    rpl = sub.add_parser("replay", help="re-normalize a built source from its raw responses")
    rpl.add_argument("source_id")
    rp = sub.add_parser("replan", help="split unfinished partitions, keep finished parts")
    rp.add_argument("source_id")
    sub.add_parser("catalog")
    sub.add_parser("status")
    sub.add_parser("hosts", help="unfinished sources grouped by host, as JSON")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        print(json.dumps(build(args.source_id), indent=2, sort_keys=True))
    elif args.cmd == "run":
        run_all(args.max_parallel, args.min_free_gb, args.only)
    elif args.cmd == "plan":
        extra = dict(kv.split("=", 1) for kv in args.set)
        print(f"{args.source_id}: {write_plan(args.source_id, extra)} partitions planned")
    elif args.cmd == "replay":
        print(json.dumps(replay(args.source_id), indent=2, sort_keys=True))
    elif args.cmd == "replan":
        kept, pending = replan(args.source_id)
        print(f"{args.source_id}: kept {kept} finished parts, {pending} partitions to go")
    elif args.cmd == "catalog":
        print(build_catalog())
    elif args.cmd == "hosts":
        print(json.dumps(host_groups(), separators=(",", ":")))
    else:
        st = status()
        total = sum(v.get("parcel", 0) for v in st.values())
        print(json.dumps({"sources": st, "total_parcels": total}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
