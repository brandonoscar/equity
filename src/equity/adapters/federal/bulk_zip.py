"""Shared plumbing for federal bulk files published as one large zip (FAA aircraft registry,
FCC ULS): stream the zip to disk once, then stream members line by line from it.

Nothing here holds a whole file in memory. A download is written to `<dest>.part` in 1 MB
chunks and renamed when complete, under the same robots.txt, spacing and retry rules as every
other request (PoliteClient). Adapters partition the work (by registrant state) and re-read
the cached zip for each partition, so a lake build runs partition by partition without
fetching the file again.

Where to read the zip from, in order: an explicit `path=` parameter (a file saved by hand);
the manual path data/manual/<source_id>/<file> when present; a cached download in
data/work/<source_id>/ younger than `max_age_s`; else a fresh download into that cache.
"""

from __future__ import annotations

import io
import os
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from equity.adapters.http import PoliteClient, Response

CHUNK = 1 << 20
MANUAL_DIR = Path("data") / "manual"
WORK_DIR = Path("data") / "work"

# (url, headers, timeout, dest) -> (status, content_type); writes the body to dest.
StreamTransport = Callable[[str, Mapping[str, str], float, Path], tuple[int, str]]


def urllib_stream(url: str, headers: Mapping[str, str], timeout: float, dest: Path
                  ) -> tuple[int, str]:  # fmt: skip
    req = urllib.request.Request(url, headers=dict(headers))  # noqa: S310 - https only
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as out:  # noqa: S310
            while chunk := resp.read(CHUNK):
                out.write(chunk)
            return int(resp.status), str(resp.headers.get("Content-Type", ""))
    except urllib.error.HTTPError as err:
        return int(err.code), str(err.headers.get("Content-Type", ""))


@dataclass
class DownloadClient(PoliteClient):
    """PoliteClient plus download(): the body goes to a file, never into memory."""

    stream: StreamTransport = field(default=urllib_stream)

    def download(self, url: str, dest: Path) -> Response:
        """Stream `url` to `dest` (via dest.part, renamed on HTTP 200). The Response carries
        no content; on any other status dest is left untouched."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")

        def call(hdrs: Mapping[str, str]) -> tuple[int, bytes, str]:
            status, ctype = self.stream(url, hdrs, self.timeout_s, part)
            return status, b"", ctype

        try:
            resp = self._send(url, call)
            if resp.status == 200 and part.exists():
                part.replace(dest)
            return resp
        finally:
            part.unlink(missing_ok=True)


def is_zip(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(2) == b"PK"
    except OSError:
        return False


def locate_zip(
    client: DownloadClient,
    source_id: str,
    url: str,
    params: Mapping[str, str],
    max_age_s: float,
    clock: Callable[[], float] = time.time,
) -> tuple[Path, str, int | None]:
    """-> (local zip, provenance URL, HTTP status or None when read from disk)."""
    name = url.rsplit("/", 1)[-1]
    if params.get("path"):
        path = Path(params["path"])
        if not is_zip(path):
            raise RuntimeError(f"{path}: not a zip file")
        return path, url, None
    manual = MANUAL_DIR / source_id / name
    if is_zip(manual):
        return manual, url, None
    cached = WORK_DIR / source_id / name
    if is_zip(cached) and clock() - cached.stat().st_mtime < max_age_s:
        return cached, url, 200
    resp = client.download(url, cached)
    if resp.status != 200 or not is_zip(cached):
        raise RuntimeError(
            f"{url}: HTTP {resp.status} ({resp.content_type}); not the zip. Save it by hand "
            f"to {manual} (or pass path=<file>) and run again."
        )
    return cached, url, resp.status


def file_time(path: Path) -> datetime:
    """When a local zip was saved or downloaded (its mtime, whole seconds): its retrieval
    time, the same for every partition read from it."""
    return datetime.fromtimestamp(int(os.stat(path).st_mtime), UTC)


def member_name(zf: zipfile.ZipFile, wanted: str) -> str | None:
    """The member called `wanted`, matched case-insensitively and ignoring folders."""
    for info in zf.infolist():
        if info.filename.rsplit("/", 1)[-1].upper() == wanted.upper():
            return info.filename
    return None


def member_lines(zip_path: Path, member: str, encoding: str = "utf-8-sig") -> Iterator[str]:
    """Stream one member's lines as text (line ends kept, undecodable bytes replaced)."""
    with zipfile.ZipFile(zip_path) as zf:
        name = member_name(zf, member)
        if name is None:
            raise KeyError(f"{zip_path.name}: no member {member}")
        with zf.open(name) as raw:
            yield from io.TextIOWrapper(raw, encoding=encoding, errors="replace", newline="")
