"""Shared plumbing for the federal organization sources (IRS, SEC, USPTO bulk files).

- BulkClient: PoliteClient (robots.txt, per-host spacing, retries) plus a GET with a Range
  header, a suffix Range ("the last n bytes") and a download streamed to a file on disk, so a
  multi-hundred-megabyte zip never sits in memory.
- remote_zip(): a zipfile.ZipFile over HTTP Range requests: the central directory and the
  members actually read are fetched, nothing else (fixtures from a 70 MB 990 batch cost a few
  hundred kilobytes).
- emit_business(): the business / business_role / party / address rows for one organization
  and the people tied to it, the same way equity.adapters.business_registry emits them.
- scrub_json(): fixture pseudonyms (names -> TESTOWNER ..., street lines -> ... TEST ST).
"""

from __future__ import annotations

import io
import json
import struct
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from equity.adapters.base import NormalizedRow
from equity.adapters.http import Response
from equity.adapters.person_lists import RangeClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.geo import state_fips
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

ROLES = frozenset({"member", "manager", "officer", "director", "organizer", "incorporator",
                   "registered_agent", "other"})  # fmt: skip
CHUNK = 1 << 20

# (url, headers, timeout, destination file) -> (status, content_type); the body goes to the file.
StreamTransport = Callable[[str, Mapping[str, str], float, Path], tuple[int, str]]


def urllib_stream_transport(
    url: str, headers: Mapping[str, str], timeout: float, dest: Path
) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=dict(headers))  # noqa: S310 - https only
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as out:  # noqa: S310
            while chunk := resp.read(CHUNK):
                out.write(chunk)
            return int(resp.status), str(resp.headers.get("Content-Type", ""))
    except urllib.error.HTTPError as err:
        dest.write_bytes(err.read()[:65536])
        return int(err.code), str(err.headers.get("Content-Type", ""))


@dataclass
class BulkClient(RangeClient):
    stream_transport: StreamTransport = field(default=urllib_stream_transport)

    def get_suffix(self, url: str, n: int) -> Response:
        """The last `n` bytes of `url` (HTTP 206)."""
        return self._send(url, lambda hdrs: self.transport(url, {**hdrs, "Range": f"bytes=-{n}"},
                                                           self.timeout_s))  # fmt: skip

    def download(self, url: str, dest: Path) -> Response:
        """GET `url` into `dest`, streamed (same robots.txt, spacing and retries as get()).
        The returned Response has an empty body; the bytes are in `dest`."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")

        def call(hdrs: Mapping[str, str]) -> tuple[int, bytes, str]:
            status, ctype = self.stream_transport(url, hdrs, self.timeout_s, part)
            return status, b"", ctype

        resp = self._send(url, call)
        if resp.status == 200:
            part.replace(dest)
        else:
            part.unlink(missing_ok=True)
        return resp


# --- zip over HTTP Range -------------------------------------------------------------------


def zip_size(tail: bytes) -> int:
    """Total size of a zip file from its last bytes (which must hold the end-of-central-
    directory record): the central directory ends where the EOCD (or zip64 EOCD) begins."""
    at = tail.rfind(b"PK\x05\x06")
    if at < 0 or len(tail) - at < 22:
        raise ValueError("no end-of-central-directory record in the zip tail")
    cd_size, cd_offset = struct.unpack("<II", tail[at + 12 : at + 20])
    if cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        z = tail.rfind(b"PK\x06\x06", 0, at)
        if z < 0:
            raise ValueError("zip64 end record not in the zip tail")
        size64, offset64 = struct.unpack("<QQ", tail[z + 40 : z + 56])
        return int(offset64 + size64 + (len(tail) - z))
    return int(cd_offset + cd_size + (len(tail) - at))


class RangeFile(io.RawIOBase):
    """A read-only, seekable file over HTTP Range requests (the last TAIL bytes cached)."""

    TAIL = 1 << 16

    def __init__(self, client: BulkClient, url: str) -> None:
        super().__init__()
        self.client, self.url, self.pos, self.requests = client, url, 0, 0
        resp = client.get_suffix(url, self.TAIL)
        if resp.status != 206:
            raise RuntimeError(f"{url}: HTTP {resp.status} to a Range request")
        self.tail = resp.content
        self.size = zip_size(self.tail)
        self.tail_at = self.size - len(self.tail)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        base = {0: 0, 1: self.pos, 2: self.size}[whence]
        self.pos = max(0, base + offset)
        return self.pos

    def readinto(self, buf: Any) -> int:
        n = min(len(buf), self.size - self.pos)
        if n <= 0:
            return 0
        if self.pos >= self.tail_at:
            data = self.tail[self.pos - self.tail_at : self.pos - self.tail_at + n]
        else:
            resp = self.client.get_range(self.url, self.pos, self.pos + n - 1)
            self.requests += 1
            if resp.status != 206:
                raise RuntimeError(f"{self.url}: HTTP {resp.status} to a Range request")
            data = resp.content[:n]
        buf[: len(data)] = data
        self.pos += len(data)
        return len(data)


def remote_zip(client: BulkClient, url: str) -> zipfile.ZipFile:
    """A ZipFile over `url` that fetches only the bytes it reads."""
    return zipfile.ZipFile(io.BufferedReader(RangeFile(client, url), buffer_size=1 << 18))


# --- small value helpers -------------------------------------------------------------------


def text(value: Any) -> str | None:
    if value is None:
        return None
    s = " ".join(str(value).split())
    return s or None


def zip5(value: Any) -> str | None:
    z = (text(value) or "").replace(" ", "")
    return z[:5] if len(z) >= 5 and z[:5].isdigit() else None


def address(street: Any, city: Any, state: Any, zip_code: Any) -> dict[str, Any] | None:
    return normalized_address(text(street), text(city), text(state), zip5(zip_code))


def jurisdiction(state: str | None) -> str:
    """The state FIPS code of a two-letter U.S. state, else US (foreign or missing)."""
    if state and len(state.strip()) == 2:
        try:
            return state_fips(state.strip())
        except KeyError:
            pass
    return "US"


# --- business rows ------------------------------------------------------------------------


@dataclass(frozen=True)
class Holder:
    """A person or company tied to the business: an officer, a related person, an owner."""

    role: str
    title: str | None
    name: str
    address: dict[str, Any] | None = None
    person: bool = False  # the source says it is a natural person
    parts: Mapping[str, str | None] = field(default_factory=dict)  # first/middle/last/suffix
    valid_to: date | None = None

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"unknown business role {self.role!r}")


NAME_PARTS = ("first_name", "middle", "last_name", "suffix")


def holder_party(
    ctx: RecordContext, source_id: str, key: str, h: Holder
) -> tuple[str, NormalizedRow]:
    nc = classify(h.name)
    kind = nc.party_kind
    if h.person and kind != "org":
        kind = "person"
    parts = {k: h.parts.get(k) for k in NAME_PARTS} if h.parts.get("last_name") else {}
    pid = stable_id(source_id, key, h.role, clean(h.name))
    row = ctx.fact(
        "party", party_id=pid, raw_name=h.name, party_kind=kind, org_form=nc.org_form,
        org_name_norm=nc.org_name_norm,
        address_id=None if h.address is None else h.address["address_id"],
        **({k: parts.get(k) for k in NAME_PARTS} if parts else dict.fromkeys(NAME_PARTS)),
    )  # fmt: skip
    return pid, row


def emit_business(
    ctx: RecordContext,
    *,
    source_id: str,
    sos_id: str,
    name: str,
    valid_from: date,
    status: str | None = None,
    formed_on: date | None = None,
    status_date: date | None = None,
    principal: dict[str, Any] | None = None,
    mailing: dict[str, Any] | None = None,
    holders: list[Holder] | tuple[Holder, ...] = (),
) -> Iterator[NormalizedRow]:
    """address, business, then party + business_role per holder (deduplicated)."""
    for addr in (principal, mailing):
        if addr is not None:
            yield NormalizedRow("address", addr)
    yield ctx.fact(
        "business", sos_id=sos_id, name=name, org_form=classify(name).org_form, status=status,
        formed_on=formed_on, status_date=status_date,
        principal_address_id=None if principal is None else principal["address_id"],
        mailing_address_id=None if mailing is None else mailing["address_id"],
        valid_from=valid_from, valid_to=None,
    )  # fmt: skip
    seen: set[tuple[str, str]] = set()
    for h in sorted(holders, key=lambda h: (h.role, h.name, h.title or "",
                                            canonical_json(dict(h.parts)))):  # fmt: skip
        pid, party = holder_party(ctx, source_id, ctx.record_key, h)
        if (pid, h.role) in seen:
            continue
        seen.add((pid, h.role))
        if h.address is not None:
            yield NormalizedRow("address", h.address)
        yield party
        valid_to = h.valid_to if h.valid_to is None or h.valid_to >= valid_from else None
        yield ctx.fact("business_role", sos_id=sos_id, party_id=pid, role=h.role,
                       title=h.title, valid_from=valid_from, valid_to=valid_to)  # fmt: skip


# --- fixtures -----------------------------------------------------------------------------


def scrub_json(content: bytes, names: tuple[str, ...], streets: tuple[str, ...]) -> bytes:
    """Pseudonymize a fetched JSON body for a committed fixture: every non-empty string under a
    key in `names` becomes TESTOWNER <hash> (entity suffix kept), under `streets` <n> TEST ST."""
    from equity.adapters.record import pseudonym  # imports the registry: only when recording

    def walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if isinstance(v, str) and v.strip() and k in streets:
                    out[k] = pseudonym("ADDRESS", v)
                elif isinstance(v, str) and v.strip() and k in names:
                    out[k] = pseudonym(k, v)
                else:
                    out[k] = walk(v)
            return out
        if isinstance(obj, list):
            return [walk(v) for v in obj]
        return obj

    return canonical_json(walk(json.loads(content)))
