"""SEC EDGAR bulk submissions: one JSON per EDGAR filer (companies, funds, trusts, and every
person who has filed, e.g. an insider filing Forms 3/4/5), from the nightly submissions.zip
(~1.6 GB, ~1M members CIK##########.json; the -submissions-NNN.json members hold only older
filings and are skipped).

Kept from each filer (the KEEP keys; the phone number and the filing history are not kept,
only the latest filing date): CIK, name, former names with their date ranges, entity type
(operating, investment, other, individual...), SIC code and description, EIN, LEI, tickers
and exchanges, category, fiscal year end, state of incorporation, business and mailing
addresses, the insider-transaction flags and the date of the latest filing.

What is emitted, from existing tables only (one source record per CIK, record_type
edgar_filer):

- a company (an operating or investment entity, or one with an SIC code, EIN or ticker, or
  whose name reads as an organization): business, sos_id CIK:<10 digits> (the key the SEC
  Form D and insider sources use, so their officers and owners attach), status None, valid
  from the retrieval date (the file is a snapshot), principal address = the business
  address, mailing address = the mailing address; each former name is a party (role
  former_name) on the same record.
- any other filer (an individual filer: an insider, a Schedule 13D/G holder): party at the
  mailing address (and the business address when it differs); a person, name parts read
  LAST FIRST MIDDLE as EDGAR prints them, when EDGAR files the CIK as an individual or as an
  insider-transaction owner.
- address: U.S. addresses (a two-letter state; foreign ones stay in the raw record).

Partitions: byte windows of WINDOW bytes over the zip's data (before the central directory,
whose offset the zip's last 64 KB give). A window holds the members whose local header
starts inside it: fetch() finds the first local header at or after `lo` (a PK\\3\\4
signature followed by a CIK member name) and walks the headers from there, reading ranges
of CHUNK bytes, so the 88 MB central directory is never read and the 1.6 GB file is read
once across all partitions in ~200 Range requests. `limit` (fixtures) keeps the first
filers of the window.

Terms: SEC data is public (U.S. government, no copyright); EDGAR fair-access policy allows
automated access at under 10 requests per second with a User-Agent that identifies the
client. This client sends the project's generic User-Agent (as the other SEC sources do) at
one request every 0.5 s. robots.txt (read 2026-11-25) allows /Archives/edgar/.
"""

from __future__ import annotations

import json
import re
import struct
import zlib
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import (
    BulkClient,
    address,
    emit_business,
    emit_party,
    jurisdiction,
    scrub_json,
    text,
    zip_size,
)
from equity.adapters.federal.sec_edgar import cik10
from equity.adapters.person_lists import split_name
from equity.adapters.rows import RecordContext, canonical_json
from equity.matching.orgs import classify
from equity.schema.ids import stable_id

URL = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
PAGE = "https://www.sec.gov/search-filings/edgar-application-programming-interfaces"
TERMS = "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data"
CHECKED_ON = "2026-11-25"
WINDOW = 32 << 20  # ~20k filers per partition
CHUNK = 8 << 20  # bytes per Range request
TAIL = 1 << 16
KEEP = ("cik", "name", "formerNames", "entityType", "sic", "sicDescription", "ein", "lei",
        "tickers", "exchanges", "category", "fiscalYearEnd", "stateOfIncorporation",
        "stateOfIncorporationDescription", "ownerOrg", "addresses",
        "insiderTransactionForOwnerExists", "insiderTransactionForIssuerExists",
        "website")  # fmt: skip
ADDRESS_KEYS = ("street1", "street2", "city", "stateOrCountry", "zipCode",
                "stateOrCountryDescription", "isForeignLocation", "country")  # fmt: skip
COMPANY_TYPES = frozenset({"operating", "investment"})
PERSON_TYPES = frozenset({"individual"})
_MEMBER = re.compile(rb"^CIK\d{10}(?:-submissions-\d{3})?\.json$")
_SIG = b"PK\x03\x04"
_HEADER = struct.Struct("<4sHHHHHIIIHH")


def data_end(tail: bytes) -> int:
    """Where the members end: the central directory's offset, from the zip's last bytes."""
    at = tail.rfind(b"PK\x05\x06")
    if at < 0:
        raise ValueError("no end-of-central-directory record in the zip tail")
    offset = struct.unpack("<I", tail[at + 16 : at + 20])[0]
    if offset == 0xFFFFFFFF:
        z = tail.rfind(b"PK\x06\x06", 0, at)
        if z < 0:
            raise ValueError("zip64 end record not in the zip tail")
        offset = struct.unpack("<Q", tail[z + 48 : z + 56])[0]
    return int(offset)


class _Window:
    """Bytes of the remote zip from some offset on, fetched CHUNK bytes at a time."""

    def __init__(self, client: BulkClient, url: str, end: int, chunk: int) -> None:
        self.client, self.url, self.end, self.chunk = client, url, end, chunk
        self.at, self.buf = 0, b""

    def get(self, off: int, n: int) -> bytes:
        """`n` bytes at `off` (fewer at the end of the data)."""
        if off < self.at or off > self.at + len(self.buf):
            self.at, self.buf = off, b""
        else:
            self.buf, self.at = self.buf[off - self.at :], off
        while len(self.buf) < n and self.at + len(self.buf) < self.end:
            first = self.at + len(self.buf)
            last = min(self.end, first + max(self.chunk, n - len(self.buf))) - 1
            resp = self.client.get_range(self.url, first, last)
            if resp.status != 206:
                raise RuntimeError(f"{self.url}: HTTP {resp.status} to a Range request")
            self.buf += resp.content[: last - first + 1]
        return self.buf[:n]


def parse_header(head: bytes) -> tuple[str, int, int, int] | None:
    """(member name, method, compressed size, data offset from the header) of a local file
    header, or None when the bytes are not one of this zip's members."""
    if len(head) < _HEADER.size or head[:4] != _SIG:
        return None
    _, _, flag, method, _, _, _, csize, _, nlen, elen = _HEADER.unpack(head[: _HEADER.size])
    name = head[_HEADER.size : _HEADER.size + nlen]
    if flag & 0x08 or method not in (0, 8) or not _MEMBER.match(name):
        return None
    return name.decode(), method, csize, _HEADER.size + nlen + elen


def members(window: _Window, lo: int, hi: int) -> Iterator[tuple[str, bytes]]:
    """(name, uncompressed bytes) of each member whose local header starts in [lo, hi)."""
    pos = lo
    if lo > 0:  # find the first header at or after lo
        found = None
        while found is None and pos < min(hi, window.end):
            blob = window.get(pos, window.chunk)
            at = blob.find(_SIG)
            while at >= 0 and found is None:
                if parse_header(window.get(pos + at, 512)) is not None:
                    found = pos + at
                else:
                    at = blob.find(_SIG, at + 1)
            if found is None:
                pos += max(len(blob) - 3, 1)
        if found is None:
            return
        pos = found
    while pos < min(hi, window.end):
        got = parse_header(window.get(pos, 512))
        if got is None:
            raise RuntimeError(f"{window.url}: no zip member header at byte {pos}")
        name, method, csize, skip = got
        raw = window.get(pos + skip, csize)
        yield name, zlib.decompressobj(-15).decompress(raw) if method == 8 else raw
        pos += skip + csize


def filer(doc: Mapping[str, Any]) -> dict[str, Any]:
    """The KEEP keys of one submissions JSON, with the latest filing date."""
    out = {k: doc[k] for k in KEEP if doc.get(k) not in (None, "", [], {})}
    addrs = out.get("addresses") or {}
    out["addresses"] = {kind: {k: v for k in ADDRESS_KEYS if (v := a.get(k)) not in (None, "")}
                        for kind, a in sorted(addrs.items()) if isinstance(a, dict)}  # fmt: skip
    recent = ((doc.get("filings") or {}).get("recent") or {}).get("filingDate") or []
    if recent:
        out["lastFiled"] = max(recent)
    return out


def us_address(a: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not a:
        return None
    st = text(a.get("stateOrCountry"))
    if not st or len(st) != 2 or not st.isalpha() or a.get("isForeignLocation") == 1:
        return None
    street = text(" ".join(p for p in (text(a.get("street1")), text(a.get("street2"))) if p))
    return address(street, a.get("city"), st.upper(), a.get("zipCode"))


def is_company(f: Mapping[str, Any]) -> bool:
    name = text(f.get("name")) or ""
    return bool(
        (f.get("entityType") or "") in COMPANY_TYPES or text(f.get("sic")) or text(f.get("ein"))
        or f.get("tickers") or classify(name).party_kind == "org"
    )  # fmt: skip


class SECSubmissions(Adapter):
    source_id: ClassVar[str] = "us.sec.submissions"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("name", "street1", "street2")

    def __init__(self, client: BulkClient | None = None) -> None:
        # EDGAR fair access: at most 10 requests/second; one every 0.5 s is well under it.
        self.client = client or BulkClient(min_interval_s=0.5, timeout_s=900.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a registry of companies and the people who file
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": URL,
            "terms_url": TERMS,
            "terms_summary": (
                "SEC EDGAR bulk submissions (submissions.zip, rebuilt nightly): every filer's "
                "CIK, names, addresses, SIC and state of incorporation; U.S. government data, "
                "free, no login. EDGAR fair access: under 10 requests/s with an identifying "
                "User-Agent. robots.txt allows /Archives/edgar/. Phone numbers not kept."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def data_end(self) -> int:
        resp = self.client.get_suffix(URL, TAIL)
        if resp.status != 206:
            raise RuntimeError(f"{URL}: HTTP {resp.status} to a Range request")
        zip_size(resp.content)  # raises unless the tail holds the end record
        return data_end(resp.content)

    def partitions(self) -> Iterator[dict[str, str]]:
        end = self.data_end()
        for lo in range(0, end, WINDOW):
            yield {"lo": str(lo), "hi": str(min(lo + WINDOW, end))}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: lo, hi (byte window of the zip's data); limit (fixtures: the first filers
        of the window, read with small Range requests)."""
        p = request.params
        if not (p["lo"].isdigit() and p["hi"].isdigit()) or int(p["lo"]) >= int(p["hi"]):
            raise ValueError(f"bad window {p['lo']!r}-{p['hi']!r}")
        lo, hi = int(p["lo"]), int(p["hi"])
        limit = int(p["limit"]) if "limit" in p else None
        end = self.data_end()
        window = _Window(self.client, URL, end, 1 << 18 if limit else CHUNK)
        filers: list[dict[str, Any]] = []
        for name, raw in members(window, lo, hi):
            if limit is not None and len(filers) >= limit:
                break
            if "-submissions-" not in name:
                filers.append(filer(json.loads(raw)))
        body = {"url": URL, "lo": lo, "hi": hi, "filers": filers}
        return Fetched(self.source_id, f"{URL}#bytes={lo}-{hi - 1}", datetime.now(UTC), 200,
                       canonical_json(body), "application/json")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        """Names (and former names) and streets pseudonymized; CIKs replaced by 99<8 digits>
        (no real CIK is that large) and EINs, LEIs and websites dropped (lookup keys that would
        undo the name pseudonyms)."""
        data = json.loads(scrub_json(content, ("name",), ("street1", "street2")))
        for f in data.get("filers") or []:
            if f.get("cik"):
                f["cik"] = "99" + str(int(stable_id("scrub", "cik", f["cik"])[:12], 16))[-8:]
            for k in ("ein", "lei", "website"):
                f.pop(k, None)
        return canonical_json(data)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for f in sorted(data.get("filers") or [], key=canonical_json):
            cik = cik10(f.get("cik"))
            name = text(f.get("name"))
            if cik is None or name is None or cik in seen:
                continue
            seen.add(cik)
            addrs = f.get("addresses") or {}
            business, mailing = us_address(addrs.get("business")), us_address(addrs.get("mailing"))
            st = next((a["state"] for a in (business, mailing) if a and a.get("state")), None)
            ctx = RecordContext(fetched, jurisdiction(st), cik, "edgar_filer", f)
            yield ctx.source_record()
            if is_company(f):
                yield from emit_business(ctx, source_id=self.source_id, sos_id=f"CIK:{cik}",
                                         name=name, valid_from=observed, principal=business,
                                         mailing=mailing)  # fmt: skip
                for former in sorted(f.get("formerNames") or [], key=canonical_json):
                    if (old := text(former.get("name"))) and old != name:
                        yield from emit_party(ctx, self.source_id, "former_name", old)
                continue
            person = (f.get("entityType") or "") in PERSON_TYPES or bool(
                f.get("insiderTransactionForOwnerExists")
            )
            p = split_name(name, "last_first") if person else {}
            parts = {"first_name": p.get("first"), "middle": p.get("middle"),
                     "last_name": p.get("last"), "suffix": p.get("suffix")}  # fmt: skip
            places: list[dict[str, Any] | None] = [a for a in (mailing, business) if a] or [None]
            done: set[str | None] = set()
            for a in places:
                aid = None if a is None else a["address_id"]
                if aid in done:
                    continue
                done.add(aid)
                yield from emit_party(ctx, self.source_id, "filer", name, a, person=person,
                                      parts=parts)  # fmt: skip

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            end = self.data_end()
            window = _Window(self.client, URL, end, 1 << 16)
            first = next(members(window, 0, end), None)
        except (OSError, RuntimeError, ValueError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        detail = f"data bytes={end}; first member {first[0] if first else None}"
        return HealthReport(self.source_id, first is not None, now, detail)
