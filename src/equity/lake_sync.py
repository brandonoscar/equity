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
STATE_FILES = ("_plan.json", "_counts.json", "_offloaded")
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


@dataclass
class PushReport:
    uploaded: int = 0
    unchanged: int = 0
    too_big: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)


def _local_dirs(lake: Path, only: frozenset[str] | None = None) -> Iterator[Path]:
    seen = sorted({p.parent for p in lake.rglob("*") if p.is_file()})
    for d in seen:
        if only is None or d.relative_to(lake).parts[0] in only:
            yield d


def write_bundle(src: Path) -> None:
    """Write src/_state.json: every state file and _parts marker, by relative path."""
    files = {n: (src / n).read_text() for n in STATE_FILES if (src / n).exists()}
    files |= {f"_parts/{m.name}": m.read_text() for m in sorted((src / "_parts").glob("*.json"))}
    if files:
        (src / BUNDLE).write_text(json.dumps(files, sort_keys=True))


def push(
    store: Store, lake: Path, prune_finished: bool = False, only: frozenset[str] | None = None
) -> PushReport:
    """Upload every lake file that storage lacks or holds at a different size. With
    prune_finished, a finished source (has _counts.json) whose Parquet parts are all stored
    loses its local Parquet and gets an _offloaded marker. `only` limits the push to those
    sources, so parallel loaders never upload another loader's (stale) state."""
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


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="equity.lake_sync")
    ap.add_argument("--lake", default="data/lake")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("push")
    p.add_argument("--prune-finished", action="store_true")
    p.add_argument("--watch", type=int, default=0, help="repeat every N seconds")
    p.add_argument("--only", nargs="*", help="limit to these source ids")
    ps = sub.add_parser("pull-state")
    ps.add_argument("--only", nargs="*", help="limit to these source ids")
    args = ap.parse_args(argv)
    only = frozenset(args.only) if args.only else None
    store = Store(base_url=os.environ.get("SUPABASE_STORAGE_URL", DEFAULT_URL),
                  key=os.environ.get("SUPABASE_SECRET_KEY") or None)  # fmt: skip
    lake = Path(args.lake)
    if args.cmd == "pull-state":
        print(f"pulled {pull_state(store, lake, only)} state files")
        return 0
    while True:
        r = push(store, lake, args.prune_finished, only)
        print(f"uploaded {r.uploaded}, unchanged {r.unchanged}, too big {len(r.too_big)}, "
              f"pruned {r.pruned}", flush=True)  # fmt: skip
        for name in r.too_big:
            print(f"too big for storage: {name}", flush=True)
        if not args.watch:
            return 0
        time.sleep(args.watch)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
