"""Keep the parcel lake in object storage (a Supabase Storage bucket), so a build can stop on one
machine and continue on another.

    uv run python -m equity.lake_sync push                  # upload new or changed lake files
    uv run python -m equity.lake_sync push --prune-finished # ...then drop local Parquet of
                                                            #    finished sources once stored
    uv run python -m equity.lake_sync push --watch 300      # keep pushing every 5 minutes
    uv run python -m equity.lake_sync pull-state            # fetch plans and part markers only

`pull-state` is all a fresh machine needs to resume: a source's plan and its finished-part
markers say what is left to build. Parquet parts stay in storage until something reads them.

Credentials: the bucket's secret key comes from SUPABASE_SECRET_KEY. When it is unset, requests
go out without one (a proxy that injects the key, as in the cloud session, still works).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_URL = "https://xxdygfwpeijrrpggqpbi.supabase.co/storage/v1"
BUCKET = "lake"
# Supabase's default per-object limit is 50 MB; larger files are reported, not sent.
MAX_BYTES = 45_000_000
# Small files that describe a source's build state; push also bundles them, with every
# finished-part marker, into one _state.json per source so a fresh machine needs one download.
STATE_FILES = ("_plan.json", "_counts.json", "_offloaded", "_refreshed.json")
BUNDLE = "_state.json"
OFFLOADED_NOTE = "parquet parts are in object storage under this source id\n"

Transport = Callable[[str, str, bytes | None, dict[str, str]], bytes]


def urllib_transport(method: str, url: str, data: bytes | None, headers: dict[str, str]) -> bytes:
    req = urllib.request.Request(url, data=data, method=method, headers=headers)  # noqa: S310
    with urllib.request.urlopen(req, timeout=600) as resp:  # noqa: S310
        body: bytes = resp.read()
        return body


@dataclass
class Store:
    base_url: str = DEFAULT_URL
    bucket: str = BUCKET
    key: str | None = None
    transport: Transport = urllib_transport
    retries: int = 5
    sleep: Callable[[float], None] = time.sleep
    log: Callable[[str], None] = field(default=print)

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = dict(extra or {})
        if self.key:
            h["apikey"] = self.key
            h["Authorization"] = f"Bearer {self.key}"
        return h

    def _call(self, method: str, url: str, data: bytes | None, headers: dict[str, str]) -> bytes:
        for attempt in range(self.retries + 1):
            try:
                return self.transport(method, url, data, self._headers(headers))
            except (OSError, urllib.error.HTTPError) as exc:
                if attempt == self.retries:
                    raise
                self.log(f"retry {method} {url}: {exc}")
                self.sleep(2**attempt)
        raise AssertionError("unreachable")  # pragma: no cover

    def list_dir(self, prefix: str) -> tuple[dict[str, int], list[str]]:
        """({file name: size}, [sub-folder names]) directly under prefix."""
        files: dict[str, int] = {}
        dirs: list[str] = []
        offset = 0
        while True:
            body = json.dumps({"prefix": prefix, "limit": 1000, "offset": offset}).encode()
            rows = json.loads(self._call("POST", f"{self.base_url}/object/list/{self.bucket}",
                                         body, {"Content-Type": "application/json"}))  # fmt: skip
            for r in rows:
                meta = r.get("metadata")
                if meta:
                    files[r["name"]] = int(meta.get("size") or 0)
                else:
                    dirs.append(r["name"])
            if len(rows) < 1000:
                return files, dirs
            offset += 1000

    def upload(self, key: str, data: bytes) -> None:
        self._call("POST", f"{self.base_url}/object/{self.bucket}/{key}", data,
                   {"Content-Type": "application/octet-stream", "x-upsert": "true"})  # fmt: skip

    def download(self, key: str) -> bytes:
        return self._call("GET", f"{self.base_url}/object/{self.bucket}/{key}", None, {})

    def delete(self, keys: list[str]) -> None:
        for i in range(0, len(keys), 1000):
            body = json.dumps({"prefixes": keys[i : i + 1000]}).encode()
            self._call("DELETE", f"{self.base_url}/object/{self.bucket}", body,
                       {"Content-Type": "application/json"})  # fmt: skip


@dataclass
class PushReport:
    uploaded: int = 0
    unchanged: int = 0
    deleted: list[str] = field(default_factory=list)
    too_big: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)


def _local_dirs(lake: Path, only: frozenset[str] | None = None) -> Iterator[Path]:
    seen = sorted({p.parent for p in lake.rglob("*") if p.is_file()})
    for d in seen:
        if only is None or d.relative_to(lake).parts[0] in only:
            yield d


def oversized_parts(src: Path) -> set[str]:
    """Part numbers with a Parquet file storage will not take (built before parts were split
    on export). Their markers stay out of the bundle, so another machine rebuilds them."""
    return {p.name.split(".")[0].split("_")[0]
            for p in src.glob("*/*.parquet") if p.stat().st_size > MAX_BYTES}  # fmt: skip


def write_bundle(src: Path) -> None:
    """Write src/_state.json: every state file and _parts marker, by relative path. A part
    with a file too big for storage is left out, as if unfinished."""
    files = {n: (src / n).read_text() for n in STATE_FILES if (src / n).exists()}
    skip = oversized_parts(src)
    files |= {f"_parts/{m.name}": m.read_text() for m in sorted((src / "_parts").glob("*.json"))
              if m.stem not in skip}  # fmt: skip
    if files:
        (src / BUNDLE).write_text(json.dumps(files, sort_keys=True))


def push(
    store: Store,
    lake: Path,
    prune_finished: bool = False,
    only: frozenset[str] | None = None,
    mirror: bool = False,
) -> PushReport:
    """Upload every lake file that storage lacks or holds at a different size. With
    prune_finished, a finished source (has _counts.json) whose Parquet parts are all stored
    loses its local Parquet and gets an _offloaded marker. `only` limits the push to those
    sources, so parallel loaders never upload another loader's (stale) state. With mirror
    (needs `only`), a finished source's stored table Parquet that is not in the local lake is
    deleted: for a source rebuilt whole here (equity.refresh), so storage holds no part the
    new build did not make."""
    if mirror and only is None:
        raise ValueError("mirror needs `only`: it deletes stored parts missing locally")
    report = PushReport()
    sources = [d for d in sorted(lake.iterdir()) if d.is_dir() and (only is None or d.name in only)]
    for src in sources:
        write_bundle(src)
    remote: dict[Path, dict[str, int]] = {}
    for folder in _local_dirs(lake, only):
        rel = folder.relative_to(lake).as_posix()
        have, _ = store.list_dir(rel + "/")
        remote[folder] = have
        for p in sorted(folder.iterdir()):
            if not p.is_file() or p.suffix in (".tmp", ".part"):
                continue
            size = p.stat().st_size
            if have.get(p.name) == size:
                report.unchanged += 1
                continue
            if size > MAX_BYTES:
                report.too_big.append(f"{rel}/{p.name}")
                continue
            store.upload(f"{rel}/{p.name}", p.read_bytes())
            have[p.name] = size
            report.uploaded += 1
    if mirror:
        # Offloaded or Parquet-less local copies are not a full build: never mirror those.
        full = [d for d in sources if (d / "_counts.json").exists()
                and not (d / "_offloaded").exists() and any(d.glob("*/*.parquet"))]  # fmt: skip
        for src in full:
            _, folders = store.list_dir(f"{src.name}/")
            stale = [
                f"{src.name}/{table}/{name}"
                for table in sorted(folders) if not table.startswith("_")
                for name in sorted(store.list_dir(f"{src.name}/{table}/")[0])
                if name.endswith(".parquet") and not (src / table / name).exists()
            ]  # fmt: skip
            if stale:
                store.delete(stale)
                report.deleted.extend(stale)
    if prune_finished:
        for src in (d for d in sources if (d / "_counts.json").exists()):
            parts = list(src.glob("*/*.parquet"))
            if parts and all(remote.get(p.parent, {}).get(p.name) == p.stat().st_size
                             for p in parts):  # fmt: skip
                for p in parts:
                    p.unlink()
                (src / "_offloaded").write_text(OFFLOADED_NOTE)
                store.upload(f"{src.name}/_offloaded", OFFLOADED_NOTE.encode())
                report.pruned.append(src.name)
    return report


def pull_state(store: Store, lake: Path, only: frozenset[str] | None = None) -> int:
    """Unpack each stored source's _state.json (plan, counts, finished-part markers) into the
    local lake. Returns the number of files written. Never overwrites a local file."""
    written = 0
    _, sources = store.list_dir("")
    for src in sorted(s for s in sources if only is None or s in only):
        files, _ = store.list_dir(f"{src}/")
        if BUNDLE not in files:
            continue
        bundle: dict[str, str] = json.loads(store.download(f"{src}/{BUNDLE}"))
        for rel, text in bundle.items():
            dest = lake / src / rel
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text)
            written += 1
    return written


def pull_parts(
    store: Store, lake: Path, sources: list[str], tables: list[str] | None = None
) -> int:
    """Download a source's stored Parquet parts that are missing locally (or differ in size),
    for analysis on a machine that did not build them. Returns files written."""
    written = 0
    for src in sources:
        _, folders = store.list_dir(f"{src}/")
        for table in sorted(folders):
            if table.startswith("_") or (tables and table not in tables):
                continue
            remote, _ = store.list_dir(f"{src}/{table}/")
            for name, size in sorted(remote.items()):
                dest = lake / src / table / name
                if not name.endswith(".parquet") or (dest.exists() and dest.stat().st_size == size):
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(".parquet.tmp")
                tmp.write_bytes(store.download(f"{src}/{table}/{name}"))
                tmp.replace(dest)
                written += 1
    return written


def pull_snapshots(store: Store, lake: Path, sources: list[str]) -> int:
    """Download a source's stored _snapshots (daily counts, listing copies) missing locally,
    so a fresh machine can build the listing history (equity.refresh). Returns files written."""
    written = 0

    def fetch(prefix: str, folder: Path) -> int:
        n = 0
        files, dirs = store.list_dir(prefix)
        for name, size in sorted(files.items()):
            dest = folder / name
            if dest.exists() and dest.stat().st_size == size:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(store.download(prefix + name))
            n += 1
        for d in sorted(dirs):
            n += fetch(f"{prefix}{d}/", folder / d)
        return n

    for src in sources:
        written += fetch(f"{src}/_snapshots/", lake / src / "_snapshots")
    return written


def push_dir(store: Store, local: Path, prefix: str) -> int:
    """Upload every file under `local` to <prefix>/<relative path> (match results for a state,
    built on a machine that keeps nothing). Returns files uploaded."""
    if not re.fullmatch(r"[a-z0-9_]+(/[a-z0-9_-]+)*", prefix):
        raise ValueError(f"bad storage prefix {prefix!r}")
    n = 0
    for path in sorted(p for p in local.rglob("*") if p.is_file()):
        store.upload(f"{prefix}/{path.relative_to(local).as_posix()}", path.read_bytes())
        n += 1
    return n


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="equity.lake_sync")
    ap.add_argument("--lake", default="data/lake")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("push")
    p.add_argument("--prune-finished", action="store_true")
    p.add_argument("--watch", type=int, default=0, help="repeat every N seconds")
    p.add_argument("--only", nargs="*", help="limit to these source ids")
    p.add_argument(
        "--mirror",
        action="store_true",
        help="delete stored parts of these (rebuilt) sources that are not local",
    )
    pp = sub.add_parser("pull-parts", help="download stored Parquet parts for analysis")
    pp.add_argument("sources", nargs="+")
    pp.add_argument("--tables", nargs="*", help="only these tables")
    sn = sub.add_parser("pull-snapshots", help="download stored dated snapshots")
    sn.add_argument("sources", nargs="+")
    pd = sub.add_parser("push-dir", help="upload a folder (e.g. a state's match results)")
    pd.add_argument("local")
    pd.add_argument("prefix", help="storage prefix, e.g. derived/tx-travis")
    ps = sub.add_parser("pull-state")
    ps.add_argument("--only", nargs="*", help="limit to these source ids")
    args = ap.parse_args(argv)
    only = frozenset(args.only) if getattr(args, "only", None) else None
    store = Store(base_url=os.environ.get("SUPABASE_STORAGE_URL", DEFAULT_URL),
                  key=os.environ.get("SUPABASE_SECRET_KEY") or None)  # fmt: skip
    lake = Path(args.lake)
    if args.cmd == "pull-parts":
        print(f"pulled {pull_parts(store, lake, args.sources, args.tables)} parquet files")
        return 0
    if args.cmd == "pull-snapshots":
        print(f"pulled {pull_snapshots(store, lake, args.sources)} snapshot files")
        return 0
    if args.cmd == "push-dir":
        print(f"uploaded {push_dir(store, Path(args.local), args.prefix)} files")
        return 0
    if args.cmd == "pull-state":
        print(f"pulled {pull_state(store, lake, only)} state files")
        return 0
    while True:
        r = push(store, lake, args.prune_finished, only, args.mirror)
        print(f"uploaded {r.uploaded}, unchanged {r.unchanged}, too big {len(r.too_big)}, "
              f"pruned {r.pruned}, deleted {len(r.deleted)}", flush=True)  # fmt: skip
        for name in r.too_big:
            print(f"too big for storage: {name}", flush=True)
        if not args.watch:
            return 0
        time.sleep(args.watch)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
