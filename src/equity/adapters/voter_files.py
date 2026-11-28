"""Statewide voter registration files. One adapter class per state; one partition per county,
so the lake builds county by county.

- Downloads: Ohio (Secretary of State) and North Carolina (State Board of Elections) publish
  the file free, one file per county, with no use restriction in state law
  (research_notes/Voter file access by state/midwest.md, southeast.md); Brandon approved them.
- Hand-delivered (DeliveredVoterFile, below): Alaska, Arkansas, Colorado, the District of
  Columbia, Florida, Michigan, Mississippi and Wisconsin, the other jurisdictions where the
  research found no use restriction ("reports/Voter file access by state.md"). None offers a
  public download; each file is requested (docs/voter_file_requests.md), dropped into
  data/manual/<source_id>/ and read there in the state's published layout.

What is emitted, from existing tables only:

- source_record: one per registration. Its raw (hashed) record is the registration columns
  this module keeps: voter ids, name, residential and mailing address, status, party,
  registration date and date of birth (Ohio, Florida, Arkansas) or birth year (NC, Michigan,
  Colorado). Voting history, phone, e-mail, race, gender and district columns are never kept.
- party: the voter, party_kind 'person', raw_name "LAST FIRST MIDDLE SUFFIX" (the order
  assessor rolls use), with the name parts, and address_id = the residential address.
- address: the residential address, and the mailing address as its own row when it
  normalizes to a different address.

Records a state marks confidential (NC confidential_ind = Y, a Florida public-records
exemption = Y) are skipped entirely, and a name
the county has masked ('#', under review) gives no party. Ohio leaves confidential (ACP)
voters out of the file itself (ORC 3503.13(A)(2), SB 293, effective 2026-03-20).

Parsing streams: the csv module reads the zip member (NC) or the gzip stream (Ohio) through a
text wrapper, so a county file is never held as a list of rows. fetch() with `limit` (fixtures)
keeps the first `limit` registrations as JSON {"url", "rows": [{column: value}]}, the shape
equity.adapters.record pseudonymizes; normalize() reads either shape.

Ohio's sites (www.ohiosos.gov, www6.ohiosos.gov) answered every request from this project's
network with a Cloudflare "suspicious activity" block page (HTTP 403) on 2026-11-25, robots.txt
included, and third parties report that the SoS blocks scripted downloads (403/CAPTCHA). The
adapter never works around a block: when the download fails, save the county file by hand from
the Voter Files Download page and pass `path=<file>`.
"""

from __future__ import annotations

import csv
import gzip
import html
import io
import itertools
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Generator, Iterable, Iterator, Mapping
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient, Response
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.matching.orgs import clean
from equity.schema.ids import stable_id

CHECKED_ON = "2026-11-25"
NAME_PARTS = ("last_name", "first_name", "middle", "suffix")

# Ohio's 88 counties, in the order of the file's COUNTY_NUMBER (01-88, alphabetical).
OH_COUNTIES = (
    "ADAMS", "ALLEN", "ASHLAND", "ASHTABULA", "ATHENS", "AUGLAIZE", "BELMONT", "BROWN",
    "BUTLER", "CARROLL", "CHAMPAIGN", "CLARK", "CLERMONT", "CLINTON", "COLUMBIANA", "COSHOCTON",
    "CRAWFORD", "CUYAHOGA", "DARKE", "DEFIANCE", "DELAWARE", "ERIE", "FAIRFIELD", "FAYETTE",
    "FRANKLIN", "FULTON", "GALLIA", "GEAUGA", "GREENE", "GUERNSEY", "HAMILTON", "HANCOCK",
    "HARDIN", "HARRISON", "HENRY", "HIGHLAND", "HOCKING", "HOLMES", "HURON", "JACKSON",
    "JEFFERSON", "KNOX", "LAKE", "LAWRENCE", "LICKING", "LOGAN", "LORAIN", "LUCAS", "MADISON",
    "MAHONING", "MARION", "MEDINA", "MEIGS", "MERCER", "MIAMI", "MONROE", "MONTGOMERY",
    "MORGAN", "MORROW", "MUSKINGUM", "NOBLE", "OTTAWA", "PAULDING", "PERRY", "PICKAWAY", "PIKE",
    "PORTAGE", "PREBLE", "PUTNAM", "RICHLAND", "ROSS", "SANDUSKY", "SCIOTO", "SENECA", "SHELBY",
    "STARK", "SUMMIT", "TRUMBULL", "TUSCARAWAS", "UNION", "VAN WERT", "VINTON", "WARREN",
    "WASHINGTON", "WAYNE", "WILLIAMS", "WOOD", "WYANDOT",
)  # fmt: skip

# North Carolina's 100 counties in county_id order (1-100, alphabetical; layout_ncvoter.txt).
NC_COUNTIES = (
    "ALAMANCE", "ALEXANDER", "ALLEGHANY", "ANSON", "ASHE", "AVERY", "BEAUFORT", "BERTIE",
    "BLADEN", "BRUNSWICK", "BUNCOMBE", "BURKE", "CABARRUS", "CALDWELL", "CAMDEN", "CARTERET",
    "CASWELL", "CATAWBA", "CHATHAM", "CHEROKEE", "CHOWAN", "CLAY", "CLEVELAND", "COLUMBUS",
    "CRAVEN", "CUMBERLAND", "CURRITUCK", "DARE", "DAVIDSON", "DAVIE", "DUPLIN", "DURHAM",
    "EDGECOMBE", "FORSYTH", "FRANKLIN", "GASTON", "GATES", "GRAHAM", "GRANVILLE", "GREENE",
    "GUILFORD", "HALIFAX", "HARNETT", "HAYWOOD", "HENDERSON", "HERTFORD", "HOKE", "HYDE",
    "IREDELL", "JACKSON", "JOHNSTON", "JONES", "LEE", "LENOIR", "LINCOLN", "MACON", "MADISON",
    "MARTIN", "MCDOWELL", "MECKLENBURG", "MITCHELL", "MONTGOMERY", "MOORE", "NASH",
    "NEW HANOVER", "NORTHAMPTON", "ONSLOW", "ORANGE", "PAMLICO", "PASQUOTANK", "PENDER",
    "PERQUIMANS", "PERSON", "PITT", "POLK", "RANDOLPH", "RICHMOND", "ROBESON", "ROCKINGHAM",
    "ROWAN", "RUTHERFORD", "SAMPSON", "SCOTLAND", "STANLY", "STOKES", "SURRY", "SWAIN",
    "TRANSYLVANIA", "TYRRELL", "UNION", "VANCE", "WAKE", "WARREN", "WASHINGTON", "WATAUGA",
    "WAYNE", "WILKES", "WILSON", "YADKIN", "YANCEY",
)  # fmt: skip


def _text(value: Any) -> str | None:
    s = " ".join(str(value).split()) if value is not None else ""
    return s or None


def _zip5(value: Any) -> str | None:
    z = str(value or "").strip()
    return z[:5] if len(z) >= 5 and z[:5].isdigit() else None


def _squash(name: str) -> str:
    """'Van Wert County' -> 'VANWERT': letters only, the word COUNTY dropped."""
    return re.sub(r"[^A-Z]", "", name.upper().replace("COUNTY", ""))


def county_number(value: str, counties: tuple[str, ...]) -> int:
    """'89', '089' or 'Tyrrell' -> 89 (1-based position in `counties`)."""
    v = value.strip()
    if v.isdigit() and 1 <= int(v) <= len(counties):
        return int(v)
    by_name = {_squash(c): i for i, c in enumerate(counties, start=1)}
    if _squash(v) in by_name:
        return by_name[_squash(v)]
    raise ValueError(f"unknown county {value!r}")


def county_fips(state_fips: str, number: int) -> str:
    """Both states number counties alphabetically, as FIPS does with odd codes: n -> 2n-1."""
    return f"{state_fips}{2 * number - 1:03d}"


def _open_text(content: bytes) -> IO[str]:
    """A text stream over the file inside `content`: a zip's largest member, a gzip stream,
    or plain text. Nothing is decompressed ahead of the reader."""
    raw: IO[bytes] | gzip.GzipFile
    if content[:2] == b"PK":
        zf = zipfile.ZipFile(io.BytesIO(content))
        member = max(zf.infolist(), key=lambda i: (i.file_size, i.filename))
        raw = zf.open(member)
    elif content[:2] == b"\x1f\x8b":
        raw = gzip.GzipFile(fileobj=io.BytesIO(content))
    else:
        raw = io.BytesIO(content)
    return io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")


def iter_raw_rows(content: bytes, delimiter: str) -> Iterator[dict[str, str]]:
    """Stream the rows of a voter file (zip, gzip or text) as {column: value}."""
    with _open_text(content) as text:
        reader = csv.reader(text, delimiter=delimiter)
        header = [h.strip() for h in next(reader, [])]
        for cells in reader:
            if cells:
                yield dict(zip(header, cells, strict=False))


_ANCHOR = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.S | re.I)
_ROW = re.compile(r"<tr\b.*?</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def _plain(fragment: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", fragment)).split())


def _is_download(href: str) -> bool:
    h = href.upper()
    return ("DOWNLOAD" in h or "PRODUCT_NUMBER" in h
            or h.split("?")[0].endswith((".GZ", ".ZIP", ".TXT", ".CSV")))  # fmt: skip


def county_links(page: str, base_url: str, counties: tuple[str, ...]) -> dict[int, str]:
    """County number -> download URL, from an index page that links one file per county.

    A link belongs to a county when its text, the first cell of its table row, or its file
    name is the county's name ('Adams', 'ADAMS COUNTY', '.../ADAMS.txt.gz'). Links to the
    statewide or district files name no single county and are ignored. The first link wins.
    """
    names = {_squash(c): i for i, c in enumerate(counties, start=1)}
    found: dict[int, str] = {}

    def take(href: str, candidates: list[str]) -> None:
        href = html.unescape(href).strip()
        if not _is_download(href):
            return
        stem = urllib.parse.urlsplit(href).path.rsplit("/", 1)[-1].split(".")[0]
        for cand in [*candidates, stem]:
            n = names.get(_squash(cand))
            if n is not None:
                found.setdefault(n, urllib.parse.urljoin(base_url, href))
                return

    for row in _ROW.findall(page):
        cells = _CELL.findall(row)
        first = _plain(cells[0]) if cells else ""
        for href, label in _ANCHOR.findall(row):
            take(href, [_plain(label), first])
    for href, label in _ANCHOR.findall(page):
        take(href, [_plain(label)])
    return dict(sorted(found.items()))


class VoterFileAdapter(Adapter):
    """Shared fetch/normalize for one state's county voter files. Subclasses name the
    columns; nothing here is state-specific."""

    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    state: ClassVar[str]
    state_fips: ClassVar[str]
    counties: ClassVar[tuple[str, ...]]
    delimiter: ClassVar[str]
    index_url: ClassVar[str]
    keep: ClassVar[tuple[str, ...]]  # registration columns kept in the source record
    pii_fields: ClassVar[tuple[str, ...]] = ()
    # Placeholder values that name nobody (equity.adapters.record and the fixture privacy
    # test read `config["skip_names"]` and leave these unscrubbed).
    config: ClassVar[Mapping[str, Any]] = {"skip_names": ()}
    placeholders: ClassVar[frozenset[str]] = frozenset()

    # -- per-state columns ----------------------------------------------------------------
    id_column: ClassVar[str]
    county_column: ClassVar[str]
    name_columns: ClassVar[tuple[str, str, str, str]]  # last, first, middle, suffix
    res_columns: ClassVar[tuple[tuple[str, ...], str, str, str]]  # street parts, city, st, zip
    mail_columns: ClassVar[tuple[tuple[str, ...], str, str, str]]

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=600.0)

    def file_url(self, county: int) -> str:
        raise NotImplementedError

    def county_param(self, params: Mapping[str, str]) -> int:
        return county_number(params["county"], self.counties)

    def partitions(self) -> Iterator[dict[str, str]]:
        """One partition per county file linked from the state's index page."""
        resp = self.client.get(self.index_url)
        if resp.status != 200:
            raise RuntimeError(f"{self.index_url}: HTTP {resp.status}")
        links = county_links(resp.content.decode("utf-8", "replace"), self.index_url,
                             self.counties)  # fmt: skip
        if not links:
            raise RuntimeError(f"{self.index_url}: no county files linked")
        for n in links:
            yield {"county": f"{n:02d}"}

    # -- fetch ----------------------------------------------------------------------------
    def _download(self, county: int) -> Response:
        url = self.file_url(county)
        resp = self.client.get(url)
        head = resp.content[:2]
        if resp.status != 200 or (head not in (b"PK", b"\x1f\x8b") and b"<" in resp.content[:64]):
            raise RuntimeError(
                f"{url}: HTTP {resp.status} ({resp.content_type}); not a voter file. Save the "
                f"county file by hand from {self.index_url} and pass path=<file>."
            )
        return resp

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: county (number or name); path (a county file saved by hand, read instead
        of downloading); limit (fixtures: keep the first `limit` registrations as JSON)."""
        p = request.params
        county = self.county_param(p)
        if p.get("path"):
            path = Path(p["path"])
            content = path.read_bytes()
            url = self.file_url(county) if not p.get("url") else p["url"]
            at = datetime.fromtimestamp(int(path.stat().st_mtime), UTC)
            status, ctype = None, "application/octet-stream"
        else:
            resp = self._download(county)
            content, url, at = resp.content, resp.url, resp.retrieved_at
            status, ctype = resp.status, resp.content_type or "application/octet-stream"
        if "limit" in p:
            content = self.sample(url, self.raw_rows(content), int(p["limit"]))
            ctype = "application/json"
        return Fetched(self.source_id, url, at, status, content, ctype)

    def sample(self, url: str, rows: Iterator[Mapping[str, Any]], limit: int) -> bytes:
        """The first `limit` registrations, kept columns only, as the JSON fixture shape."""
        kept: list[dict[str, Any]] = []
        for r in rows:
            if len(kept) >= limit:
                break
            kept.append(self.kept(r))
        return canonical_json({"url": url, "rows": kept})

    # -- normalize ------------------------------------------------------------------------
    def raw_rows(self, content: bytes) -> Iterator[Mapping[str, Any]]:
        """The rows of a fetched file, streamed."""
        return iter_raw_rows(content, self.delimiter)

    def rows(self, content: bytes) -> Iterator[Mapping[str, Any]]:
        """Rows of either fetched shape: a JSON sample or the file itself."""
        if content[:1] == b"{":
            yield from json.loads(content)["rows"]
        else:
            yield from self.raw_rows(content)

    def kept(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """The registration columns this module keeps (the hashed raw record)."""
        return {k: row[k] for k in self.keep if k in row}

    def jurisdiction(self, r: Mapping[str, Any]) -> str:
        try:
            n = county_number(str(r.get(self.county_column) or ""), self.counties)
        except ValueError:
            return self.state_fips
        return county_fips(self.state_fips, n)

    def residence(self, r: Mapping[str, Any]) -> dict[str, Any] | None:
        return self._address(r, self.res_columns)

    def mailing(self, r: Mapping[str, Any]) -> dict[str, Any] | None:
        return self._address(r, self.mail_columns)

    def record_key(self, r: Mapping[str, Any]) -> str | None:
        return _text(r.get(self.id_column))

    def skip(self, r: Mapping[str, Any]) -> bool:
        """A record the state marks confidential: nothing of it is emitted."""
        return False

    def _address(
        self, r: Mapping[str, Any], cols: tuple[tuple[str, ...], str, str, str]
    ) -> dict[str, Any] | None:
        street_cols, city, st, z = cols
        parts = [_text(r.get(c)) for c in street_cols]
        street = " ".join(p for p in parts if p and p.upper() not in self.placeholders) or None
        return normalized_address(street, _text(r.get(city)), _text(r.get(st)), _zip5(r.get(z)))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        seen: set[str] = set()
        addresses: set[str] = set()
        for row in self.rows(fetched.content):
            r = self.kept(row)
            key = self.record_key(r)
            if key is None or key in seen or self.skip(r):
                continue
            seen.add(key)
            ctx = RecordContext(fetched, self.jurisdiction(r), key, "voter_registration", r)
            yield ctx.source_record()
            res = self.residence(r)
            mail = self.mailing(r)
            for addr in (res, mail):
                if addr is not None and addr["address_id"] not in addresses:
                    addresses.add(addr["address_id"])
                    yield NormalizedRow("address", addr)
            parts = dict(zip(NAME_PARTS, (_text(r.get(c)) for c in self.name_columns),
                             strict=True))  # fmt: skip
            masked = any("#" in (v or "") for v in parts.values())
            if not parts["last_name"] or masked:
                continue
            raw_name = " ".join(v for v in (parts[k] for k in NAME_PARTS) if v)
            yield ctx.fact(
                "party", party_id=stable_id(self.source_id, key, "voter", clean(raw_name)),
                raw_name=raw_name, party_kind="person", org_form=None, org_name_norm=None,
                address_id=res["address_id"] if res else None, **parts,
            )  # fmt: skip

    def source_row_base(self) -> dict[str, Any]:
        return {"source_id": self.source_id, "kind": "sos",  # nearest kind: a state registry
                "jurisdiction": self.state_fips, "access_method": self.access_method,
                "cost_model": "free", "robots_checked_on": CHECKED_ON}  # fmt: skip


class OhioVoterFile(VoterFileAdapter):
    """Ohio Statewide Voter File (SWVF), one comma-delimited, gzip-compressed file per county,
    refreshed weekly. Layout per the SoS record layout (as quoted by third parties; the SoS
    page itself was unreachable from here): SOS_VOTERID, COUNTY_NUMBER, COUNTY_ID, LAST_NAME,
    FIRST_NAME, MIDDLE_NAME, SUFFIX, DATE_OF_BIRTH, REGISTRATION_DATE (YYYY-MM-DD),
    VOTER_STATUS, PARTY_AFFILIATION, RESIDENTIAL_* and MAILING_* address groups, district
    columns, then one column per election (voting history, never kept)."""

    source_id: ClassVar[str] = "oh.sos.voter_file"
    state: ClassVar[str] = "OH"
    state_fips: ClassVar[str] = "39"
    counties: ClassVar[tuple[str, ...]] = OH_COUNTIES
    delimiter: ClassVar[str] = ","
    index_url: ClassVar[str] = "https://www6.ohiosos.gov/ords/f?p=VOTERFTP:HOME"
    download_page: ClassVar[str] = "https://www.ohiosos.gov/elections/voters/voter-files-download/"
    keep: ClassVar[tuple[str, ...]] = (
        "SOS_VOTERID", "COUNTY_NUMBER", "COUNTY_ID", "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME",
        "SUFFIX", "DATE_OF_BIRTH", "REGISTRATION_DATE", "VOTER_STATUS", "PARTY_AFFILIATION",
        "RESIDENTIAL_ADDRESS1", "RESIDENTIAL_SECONDARY_ADDR", "RESIDENTIAL_CITY",
        "RESIDENTIAL_STATE", "RESIDENTIAL_ZIP", "RESIDENTIAL_ZIP_PLUS4", "RESIDENTIAL_COUNTRY",
        "RESIDENTIAL_POSTALCODE", "MAILING_ADDRESS1", "MAILING_SECONDARY_ADDRESS",
        "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP", "MAILING_ZIP_PLUS4", "MAILING_COUNTRY",
        "MAILING_POSTAL_CODE",
    )  # fmt: skip
    pii_fields: ClassVar[tuple[str, ...]] = (
        "SOS_VOTERID", "COUNTY_ID", "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "SUFFIX",
        "DATE_OF_BIRTH", "REGISTRATION_DATE", "RESIDENTIAL_ADDRESS1",
        "RESIDENTIAL_SECONDARY_ADDR", "MAILING_ADDRESS1", "MAILING_SECONDARY_ADDRESS",
    )  # fmt: skip
    id_column: ClassVar[str] = "SOS_VOTERID"
    county_column: ClassVar[str] = "COUNTY_NUMBER"
    name_columns: ClassVar[tuple[str, str, str, str]] = (
        "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "SUFFIX")  # fmt: skip
    res_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("RESIDENTIAL_ADDRESS1", "RESIDENTIAL_SECONDARY_ADDR"), "RESIDENTIAL_CITY",
        "RESIDENTIAL_STATE", "RESIDENTIAL_ZIP")  # fmt: skip
    mail_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("MAILING_ADDRESS1", "MAILING_SECONDARY_ADDRESS"), "MAILING_CITY", "MAILING_STATE",
        "MAILING_ZIP")  # fmt: skip

    def file_url(self, county: int) -> str:
        resp = self.client.get(self.index_url)
        links = county_links(resp.content.decode("utf-8", "replace"), self.index_url,
                             self.counties) if resp.status == 200 else {}  # fmt: skip
        if county not in links:
            raise RuntimeError(
                f"{self.index_url}: HTTP {resp.status}, no link for county {county:02d} "
                f"({self.counties[county - 1]}). Save the county file by hand from "
                f"{self.download_page} and pass path=<file>."
            )
        return links[county]

    def fetch(self, request: FetchRequest) -> Fetched:
        if request.params.get("path") and not request.params.get("url"):
            # A hand-saved file: its provenance is the download page, not a resolved link.
            n = self.county_param(request.params)
            url = f"{self.download_page}#county={n:02d}"
            return super().fetch(FetchRequest({**request.params, "url": url}))
        return super().fetch(request)

    def source_row(self) -> Mapping[str, Any]:
        return {
            **self.source_row_base(),
            "base_url": self.index_url,
            "terms_url": self.download_page,
            "terms_summary": (
                "Ohio SoS Voter Files Download: the statewide voter registration database, "
                "free, one file per county, updated weekly. A public record under ORC "
                "3503.13(A)(1); SB 293 (eff. 2026-03-20) withholds SSN, DL/ID number, phone, "
                "email, confidential (Safe at Home) records, redacted public-service-worker "
                "addresses and proof of citizenship. No use restriction in statute (research "
                "2026-11-25). On 2026-11-25 www.ohiosos.gov and www6.ohiosos.gov, robots.txt "
                "included, answered this client with a Cloudflare 403 block page, so neither "
                "robots.txt nor the page's terms could be read; scripted access stops at a "
                "block (no CAPTCHA solving) and a hand-saved county file is read via path=."
            ),
            "terms_checked_on": None,
        }

    def health(self) -> HealthReport:
        resp = self.client.get(self.index_url)
        links = county_links(resp.content.decode("utf-8", "replace"), self.index_url,
                             self.counties) if resp.status == 200 else {}  # fmt: skip
        ok = len(links) == len(self.counties)
        return HealthReport(self.source_id, ok, datetime.now(UTC),
                            f"status={resp.status} county_links={len(links)}")  # fmt: skip


NC_DATA = "https://s3.amazonaws.com/dl.ncsbe.gov/data"
_LAYOUT_COL = re.compile(r"^([a-z][a-z0-9_]*)\s+\S")


def layout_columns(text: str) -> tuple[str, ...]:
    """Column names of the current layout (the first table) in layout_ncvoter.txt."""
    cols: list[str] = []
    started = False
    for line in text.splitlines():
        if not started:
            started = line.startswith("name ") and "data type" in line
            continue
        if line.startswith("----"):
            if cols:
                break
            continue
        m = _LAYOUT_COL.match(line)
        if m:
            cols.append(m.group(1))
    return tuple(cols)


class NorthCarolinaVoterFile(VoterFileAdapter):
    """NC State Board of Elections voter registration file (ncvoter), one tab-delimited,
    quoted text file per county in data/ncvoter<county_id>.zip, a weekly snapshot (Sunday
    evening). Layout from data/layout_ncvoter.txt (current layout from 2026-02-01): ids
    (voter_reg_num, unique in the county; ncid, statewide), name, status and reason, residential
    address (res_street_address, res_city_desc, state_cd, zip_code), mailing address
    (mail_addr1-4, mail_city, mail_state, mail_zipcode), phone, confidential_ind, registr_dt
    (MM/DD/YYYY), race, ethnicity, party_cd, gender, birth_year, age, birth_state, ID flags and
    districts. No date of birth, SSN or DL number (confidential by law). Removed voters whose
    last vote is over 10 years old are dropped; removed and confidential records carry
    'REMOVED' / 'CONFIDENTIAL' in place of the street."""

    source_id: ClassVar[str] = "nc.sbe.voter_file"
    state: ClassVar[str] = "NC"
    state_fips: ClassVar[str] = "37"
    counties: ClassVar[tuple[str, ...]] = NC_COUNTIES
    delimiter: ClassVar[str] = "\t"
    index_url: ClassVar[str] = "https://www.ncsbe.gov/results-data/voter-registration-data"
    keep: ClassVar[tuple[str, ...]] = (
        "county_id", "county_desc", "voter_reg_num", "ncid", "last_name", "first_name",
        "middle_name", "name_suffix_lbl", "status_cd", "voter_status_desc", "reason_cd",
        "voter_status_reason_desc", "res_street_address", "res_city_desc", "state_cd",
        "zip_code", "mail_addr1", "mail_addr2", "mail_addr3", "mail_addr4", "mail_city",
        "mail_state", "mail_zipcode", "confidential_ind", "registr_dt", "party_cd", "birth_year",
    )  # fmt: skip
    pii_fields: ClassVar[tuple[str, ...]] = (
        "voter_reg_num", "ncid", "last_name", "first_name", "middle_name", "name_suffix_lbl",
        "res_street_address", "mail_addr1", "mail_addr2", "mail_addr3", "mail_addr4",
        "registr_dt", "birth_year",
    )  # fmt: skip
    placeholders: ClassVar[frozenset[str]] = frozenset({"REMOVED", "CONFIDENTIAL"})
    config: ClassVar[Mapping[str, Any]] = {"skip_names": ("REMOVED", "CONFIDENTIAL")}
    id_column: ClassVar[str] = "ncid"
    county_column: ClassVar[str] = "county_id"
    name_columns: ClassVar[tuple[str, str, str, str]] = (
        "last_name", "first_name", "middle_name", "name_suffix_lbl")  # fmt: skip
    res_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("res_street_address",), "res_city_desc", "state_cd", "zip_code")  # fmt: skip
    mail_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("mail_addr1", "mail_addr2", "mail_addr3", "mail_addr4"), "mail_city", "mail_state",
        "mail_zipcode")  # fmt: skip

    def file_url(self, county: int) -> str:
        return f"{NC_DATA}/ncvoter{county}.zip"

    def record_key(self, r: Mapping[str, Any]) -> str | None:
        """The NCID; a record without one is known by county and registration number."""
        ncid = _text(r.get("ncid"))
        if ncid:
            return ncid
        reg, cty = _text(r.get("voter_reg_num")), _text(r.get("county_id"))
        return f"{cty}-{reg}" if reg and cty else None

    def skip(self, r: Mapping[str, Any]) -> bool:
        return (_text(r.get("confidential_ind")) or "").upper() == "Y"

    def partitions(self) -> Iterator[dict[str, str]]:
        """The county zips linked from the NCSBE Voter Registration Data page (never the
        statewide zip)."""
        resp = self.client.get(self.index_url)
        if resp.status != 200:
            raise RuntimeError(f"{self.index_url}: HTTP {resp.status}")
        page = resp.content.decode("utf-8", "replace")
        ids = sorted({int(n) for n in re.findall(r"/ncvoter(\d+)\.zip", page)
                      if 1 <= int(n) <= len(self.counties)})  # fmt: skip
        if not ids:
            raise RuntimeError(f"{self.index_url}: no county files linked")
        for n in ids:
            yield {"county": str(n)}

    def source_row(self) -> Mapping[str, Any]:
        return {
            **self.source_row_base(),
            "base_url": f"{NC_DATA}/",
            "terms_url": self.index_url,
            "terms_checked_on": CHECKED_ON,
            "terms_summary": (
                "NC State Board of Elections public voter registration files: free, no login, "
                "weekly snapshot (Sunday evening), statewide and one zip per county. Public "
                "records under G.S. 132-1 and 163-82.10 (data/ReadMe_PUBLIC_DATA.txt); birth "
                "date, SSN and DL number are confidential and excluded. No license or use "
                "restriction on the Voter Registration Data page (read 2026-11-25); its footer "
                "links only the generic nc.gov Disclaimer & Terms of Use. robots.txt: "
                "www.ncsbe.gov disallows only Drupal admin/user/search paths; dl.ncsbe.gov "
                "(404) and s3.amazonaws.com (403) publish none, so no restriction (RFC 9309)."
            ),
        }

    def health(self) -> HealthReport:
        resp = self.client.get(f"{NC_DATA}/layout_ncvoter.txt")
        cols = layout_columns(resp.content.decode("utf-8", "replace")) if resp.status == 200 else ()
        missing = sorted(set(self.keep) - set(cols))
        ok = resp.status == 200 and not missing
        detail = "ok" if ok else f"status={resp.status} missing={missing}"
        return HealthReport(self.source_id, ok, datetime.now(UTC), detail, tuple(sorted(cols)))


# =========================================================================================
# Hand-delivered statewide files: AK, AR, CO, DC, FL, MI, MS, WI.
#
# None of these states publishes its voter file for download: each is requested (a form,
# an email, a public-records request or a paid account) and arrives by disk, flash drive,
# secure link or e-mail link. docs/voter_file_requests.md says how to ask for each. The file
# (or the folder of county files, or the zip exactly as delivered) is dropped into
# data/manual/<source_id>/ and read from there; nothing here downloads anything.
#
# Columns are read by name. Headers are canonicalized ('Voter Reg Number' -> VOTER_REG_NUMBER,
# 'LastName' -> LASTNAME, 'PRE-DIRECTION' -> PRE_DIRECTION) and a state's known alternate
# headers are mapped onto the published ones (`aliases`), so a re-labeled column does not
# silently drop. Headerless layouts (Florida's tab-delimited extract, Michigan's fixed-width
# .lst) name their columns from the official layout. A statewide file is split once, in one
# streaming pass, into per-county extracts of the kept columns under data/work/<source_id>/,
# and each county is then one partition, as for NC and OH.
# =========================================================================================

MANUAL_DIR = Path("data") / "manual"
WORK_DIR = Path("data") / "work"
EXTRACT_MAGIC = "#equity-voter-extract"
_DATA_FILE = re.compile(r"\.(csv|txt|tsv|lst|xlsx)$", re.I)
_CSZ_LINE = re.compile(
    r"^(?P<city>.*?[A-Z].*?)[,\s]+(?P<st>[A-Z]{2})[,\s]+(?P<zip>\d{5})(?:-?\d{4})?$", re.I
)
_XLSX = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
ByteStream = IO[bytes] | gzip.GzipFile
Members = Generator[tuple[str, ByteStream], None, None]


def canon(header: str) -> str:
    """'Voter Reg Number' -> 'VOTER_REG_NUMBER'; 'PRE-DIRECTION' -> 'PRE_DIRECTION'."""
    return re.sub(r"[^A-Z0-9]+", "_", header.strip().lstrip("﻿").upper()).strip("_")


def fips_table(
    state_fips: str,
    ordered: tuple[str, ...],
    extra: Mapping[str, str] | None = None,
    numbered: bool = False,
) -> dict[str, str]:
    """County lookup -> 5-digit FIPS. `ordered` lists the counties in FIPS order, where the
    n-th has code 2n-1; `extra` gives the codes that break that pattern (Broomfield 014,
    Menominee 078, Miami-Dade 086). With `numbered`, the 1-based position is also a key (the
    state numbers its counties alphabetically, as Michigan's QVF COUNTY_CODE does)."""
    table: dict[str, str] = {}
    for i, name in enumerate(ordered, start=1):
        table[_squash(name)] = f"{state_fips}{2 * i - 1:03d}"
        if numbered:
            table[str(i)] = table[_squash(name)]
    for name, code in (extra or {}).items():
        table[_squash(name)] = f"{state_fips}{code}"
    return table


def split_city_line(lines: list[str | None], zip_fallback: Any = None) -> dict[str, Any] | None:
    """Address lines whose last line is 'CITY ST 12345' (or 'CITY, ST 12345-6789'), as in
    Michigan's MAILING_ADDRESS_LINE_* and Wisconsin's Address1/Address2: the city line is
    parsed off and the lines before it are the street. A last line without a ZIP is kept as
    street text (too easily confused with '12 OAK CT')."""
    parts = [" ".join(x.split()) for x in lines if x and x.strip()]
    city = st = None
    z = _zip5(zip_fallback)
    if parts:
        m = _CSZ_LINE.match(parts[-1])
        if m:
            city, st, z = m.group("city").strip(" ,"), m.group("st").upper(), m.group("zip")
            parts = parts[:-1]
    return normalized_address(" ".join(parts) or None, city, st, z)


def _member_ok(name: str, include: re.Pattern[str], exclude: re.Pattern[str] | None) -> bool:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    if base.startswith((".", "~", "__MACOSX")) or "__MACOSX/" in name:
        return False
    return bool(include.search(base)) and not (exclude and exclude.search(base))


def iter_members(
    source: Path, include: re.Pattern[str], exclude: re.Pattern[str] | None = None
) -> Members:
    """(name, byte stream) of every data file in `source`: a folder (recursively), a zip
    (and zips inside it), a .gz, an .xlsx or a plain file. Inside a folder or zip, only names
    matching `include` and not `exclude` count (voting-history and code-table files are
    skipped); a plain file named directly is always read."""
    if source.is_dir():
        for child in sorted(source.rglob("*")):
            if child.is_file() and (child.suffix.lower() in (".zip", ".gz")
                                    or _member_ok(child.name, include, exclude)):  # fmt: skip
                yield from iter_members(child, include, exclude)
        return
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            yield from _zip_members(zf, include, exclude)
        return
    if source.suffix.lower() == ".gz":
        with gzip.open(source, "rb") as gz:
            yield source.name[:-3], gz
        return
    with source.open("rb") as fh:
        yield source.name, fh


def _zip_members(
    zf: zipfile.ZipFile, include: re.Pattern[str], exclude: re.Pattern[str] | None
) -> Members:
    for info in sorted(zf.infolist(), key=lambda i: i.filename):
        if info.is_dir():
            continue
        if info.filename.lower().endswith(".zip"):
            with zf.open(info) as inner, zipfile.ZipFile(inner) as nested:
                yield from _zip_members(nested, include, exclude)
        elif _member_ok(info.filename, include, exclude):
            with zf.open(info) as fh:
                yield info.filename.rsplit("/", 1)[-1], fh


def _text_stream(raw: ByteStream) -> IO[str]:
    return io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")


def iter_header_rows(
    lines: Iterable[str], delimiter: str | None = None
) -> Iterator[dict[str, str]]:
    """Rows of a delimited file with a header line, headers canonicalized. The delimiter is
    the one of ',', '|' and tab that the header uses most, unless given."""
    it = iter(lines)
    first = next(it, "")
    delim = delimiter or max(",|\t", key=first.count)
    header = [canon(h) for h in next(csv.reader([first], delimiter=delim), [])]
    for cells in csv.reader(it, delimiter=delim):
        if any(c.strip() for c in cells):
            yield dict(zip(header, cells, strict=False))


def iter_headerless_rows(
    text: IO[str], columns: tuple[str, ...], delimiter: str
) -> Iterator[dict[str, str]]:
    for cells in csv.reader(text, delimiter=delimiter, quoting=csv.QUOTE_NONE):
        if any(c.strip() for c in cells):
            yield dict(zip(columns, cells, strict=False))


def iter_fixed_rows(
    lines: Iterable[str], spec: tuple[tuple[str, int, int], ...]
) -> Iterator[dict[str, str]]:
    """Fixed-width lines: spec = (column, start, end), 0-based, end exclusive."""
    for line in lines:
        line = line.rstrip("\r\n")
        if line.strip():
            yield {name: line[a:b].strip() for name, a, b in spec}


def _xlsx_col(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + ord(ch.upper()) - 64
    return n - 1


def iter_xlsx_rows(raw: ByteStream) -> Iterator[dict[str, str]]:
    """Rows of the largest worksheet of an .xlsx (first row = header), streamed with the
    standard library: shared strings, inline strings and raw cell values (a date stays the
    serial number Excel stores)."""
    data = raw.read() if not raw.seekable() else None
    with zipfile.ZipFile(io.BytesIO(data) if data is not None else raw) as zf:
        names = zf.namelist()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            # An official agency delivery; Python's expat refuses entity-expansion bombs.
            for _, el in ET.iterparse(zf.open("xl/sharedStrings.xml")):  # noqa: S314
                if el.tag == f"{_XLSX}si":
                    shared.append("".join(t.text or "" for t in el.iter(f"{_XLSX}t")))
                    el.clear()
        sheets = [n for n in names if n.startswith("xl/worksheets/") and n.endswith(".xml")]
        if not sheets:
            return
        sheet = max(sheets, key=lambda n: (zf.getinfo(n).file_size, n))
        header: list[str] | None = None
        for _, el in ET.iterparse(zf.open(sheet)):  # noqa: S314
            if el.tag != f"{_XLSX}row":
                continue
            cells: dict[int, str] = {}
            for pos, c in enumerate(el.iter(f"{_XLSX}c")):
                col = _xlsx_col(c.get("r", "")) if c.get("r") else pos
                v = c.find(f"{_XLSX}v")
                if c.get("t") == "s" and v is not None and v.text:
                    cells[col] = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    cells[col] = "".join(t.text or "" for t in c.iter(f"{_XLSX}t"))
                else:
                    cells[col] = (v.text or "") if v is not None else ""
            el.clear()
            row = [cells.get(i, "") for i in range(max(cells) + 1)] if cells else []
            if header is None:
                header = [canon(h) for h in row]
            elif any(x.strip() for x in row):
                yield dict(zip(header, row, strict=False))


class DeliveredVoterFile(VoterFileAdapter):
    """A statewide file obtained by request and read from data/manual/<source_id>/.

    partitions(): one per county. A state that delivers one file per county (Florida) is
    partitioned by its files; any other statewide file is split once into per-county
    extracts (data/work/<source_id>/<file-size-mtime>/<fips>.tsv.gz, kept columns only). A
    state with no county column (Alaska, DC) is one partition.

    fetch() params: county (5-digit FIPS, county name or the state's county code); path (read
    this file or folder instead of the newest one in the drop folder); limit (JSON sample).
    """

    access_method: ClassVar[str] = "manual"
    delimiter: ClassVar[str] = ","
    index_url: ClassVar[str] = ""
    counties: ClassVar[tuple[str, ...]] = ()
    request_url: ClassVar[str]  # the request page or form (fetch provenance)
    layout_url: ClassVar[str]  # the published record layout this class follows
    terms_summary: ClassVar[str]
    cost_model: ClassVar[str] = "free"
    include: ClassVar[re.Pattern[str]] = _DATA_FILE
    exclude: ClassVar[re.Pattern[str] | None] = re.compile(r"hist|layout|readme|code", re.I)
    columns: ClassVar[tuple[str, ...]] = ()  # set for headerless layouts
    aliases: ClassVar[Mapping[str, str]] = {}  # alternate canonical header -> kept column
    fips: ClassVar[Mapping[str, str]] = {}  # squashed county name / code -> FIPS
    per_county_files: ClassVar[bool] = False
    county_column: ClassVar[str] = ""  # '' = the whole file is one partition
    optional: ClassVar[tuple[str, ...]] = ()  # kept when present; not in every delivery

    # -- where the delivery lives -----------------------------------------------------------
    @classmethod
    def drop_dir(cls) -> Path:
        return MANUAL_DIR / cls.source_id

    @classmethod
    def work_dir(cls) -> Path:
        return WORK_DIR / cls.source_id.replace(".", "_")

    def delivered(self, params: Mapping[str, str] | None = None) -> Path:
        """The file (or, for per-county deliveries, the folder) to read."""
        if params and params.get("path"):
            return Path(params["path"])
        drop = self.drop_dir()
        files = [f for f in drop.glob("*") if not f.name.startswith(".")
                 and f.name.upper() != "README.MD"] if drop.is_dir() else []  # fmt: skip
        if not files:
            raise RuntimeError(
                f"{drop}: no {self.state} voter file delivered yet. It is not downloadable: "
                f"request it ({self.request_url}; docs/voter_file_requests.md) and drop the "
                f"delivery here, or pass path=<file>."
            )
        if self.per_county_files:
            return drop
        return max(files, key=lambda f: (f.stat().st_mtime, f.name))

    # -- reading ----------------------------------------------------------------------------
    def read_member(self, name: str, raw: ByteStream) -> Iterator[dict[str, str]]:
        """Canonical-header rows of one delivered data file."""
        if name.lower().endswith(".xlsx"):
            yield from iter_xlsx_rows(raw)
            return
        with _text_stream(raw) as text:
            if self.columns:
                yield from iter_headerless_rows(text, self.columns, self.delimiter)
            else:
                yield from iter_header_rows(text)

    def canonical(self, row: Mapping[str, Any]) -> dict[str, Any]:
        out = dict(row)
        for alt, col in self.aliases.items():
            if col not in out and alt in out:
                out[col] = out[alt]
        return out

    def kept(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """Every kept column, '' when the file lacks it, so a row hashes the same whether it
        came straight from the delivery, from a county extract or from a JSON sample."""
        r = self.canonical(row)
        return {k: (r.get(k) if r.get(k) is not None else "") for k in self.keep}

    def iter_delivered(self, source: Path) -> Iterator[dict[str, str]]:
        for name, raw in iter_members(source, self.include, self.exclude):
            yield from self.read_member(name, raw)

    def member_bytes(self, source: Path, member: str) -> bytes:
        members = iter_members(source, self.include, self.exclude)
        try:
            for name, raw in members:
                if name == member:
                    return raw.read()
        finally:
            members.close()
        raise RuntimeError(f"{source}: no member {member}")

    def raw_rows(self, content: bytes) -> Iterator[Mapping[str, Any]]:
        """Fetched content: a county extract (gzip, magic first line), a zip as delivered,
        an .xlsx, a gzip or one plain data file."""
        if content[:2] == b"\x1f\x8b":
            with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz:
                head = gz.read(len(EXTRACT_MAGIC))
                gz.seek(0)
                if head == EXTRACT_MAGIC.encode():
                    with _text_stream(gz) as text:
                        text.readline()
                        yield from iter_header_rows(text, "\t")
                else:
                    yield from self.read_member("", gz)
            return
        if content[:2] == b"PK":
            zf = zipfile.ZipFile(io.BytesIO(content))
            if "xl/workbook.xml" in zf.namelist():
                yield from iter_xlsx_rows(io.BytesIO(content))
                return
            with zf:
                for name, raw in _zip_members(zf, self.include, self.exclude):
                    yield from self.read_member(name, raw)
            return
        yield from self.read_member("", io.BytesIO(content))

    # -- counties ---------------------------------------------------------------------------
    def jurisdiction(self, r: Mapping[str, Any]) -> str:
        value = _text(r.get(self.county_column)) if self.county_column else None
        if not value:
            return self.state_fips
        return self.fips.get(_squash(value)) or self.fips.get(value.lstrip("0")) \
            or self.state_fips  # fmt: skip

    def county_key(self, value: str) -> str:
        """A county param (FIPS, name or state code) -> its FIPS partition key."""
        v = value.strip()
        if re.fullmatch(rf"{self.state_fips}(\d{{3}})?", v):
            return v
        key = self.fips.get(_squash(v)) or self.fips.get(v.lstrip("0"))
        if key is None:
            raise ValueError(f"unknown {self.state} county {value!r}")
        return key

    def county_files(self, source: Path) -> dict[str, str]:
        """Per-county deliveries: FIPS -> member name (the newest file per county)."""
        found: dict[str, str] = {}
        for name, _ in iter_members(source, self.include, self.exclude):
            key = self.fips.get(_squash(name.split("_")[0]))
            if key and name > found.get(key, ""):
                found[key] = name
        return dict(sorted(found.items()))

    def _extract_dir(self, source: Path) -> Path:
        st = source.stat()
        tag = re.sub(r"[^A-Za-z0-9._-]", "_", f"{source.name}-{st.st_size}-{int(st.st_mtime)}")
        return self.work_dir() / tag

    def split(self, source: Path) -> dict[str, int]:
        """One streaming pass: the statewide file -> one gzip extract per county (kept
        columns, tab-delimited, header line). Reused while the delivered file is unchanged."""
        out = self._extract_dir(source)
        manifest = out / "_manifest.json"
        if manifest.exists():
            parts: dict[str, int] = json.loads(manifest.read_text())["parts"]
            return parts
        out.mkdir(parents=True, exist_ok=True)
        writers: dict[str, Any] = {}
        counts: dict[str, int] = {}
        with ExitStack() as stack:
            for row in self.iter_delivered(source):
                r = self.kept(row)
                key = self.jurisdiction(r)
                if key not in writers:
                    gz = stack.enter_context(gzip.open(out / f"{key}.tsv.gz", "wt",
                                                       encoding="utf-8", newline=""))  # fmt: skip
                    gz.write(EXTRACT_MAGIC + "\n")
                    writers[key] = csv.writer(gz, delimiter="\t", lineterminator="\n")
                    writers[key].writerow(self.keep)
                writers[key].writerow([r[k] for k in self.keep])
                counts[key] = counts.get(key, 0) + 1
        manifest.write_text(json.dumps({"source": str(source), "parts": dict(sorted(
            counts.items()))}, indent=1))  # fmt: skip
        return counts

    def partitions(self) -> Iterator[dict[str, str]]:
        source = self.delivered()
        if self.per_county_files:
            keys = list(self.county_files(source))
        elif self.county_column:
            keys = sorted(self.split(source))
        else:
            keys = [self.whole_key()]
        if not keys:
            raise RuntimeError(f"{source}: no {self.state} voter registration file found")
        for k in keys:
            yield {"county": k}

    def whole_key(self) -> str:
        return self.state_fips

    # -- fetch ------------------------------------------------------------------------------
    def file_url(self, county: int) -> str:
        return self.request_url

    def fetch(self, request: FetchRequest) -> Fetched:
        p = request.params
        source = self.delivered(p)
        county = self.county_key(p["county"]) if p.get("county") else None
        at = datetime.fromtimestamp(int(source.stat().st_mtime), UTC)
        url = f"{self.request_url}#file={source.name}" + (f"&county={county}" if county else "")
        if "limit" in p:
            rows: Iterator[Mapping[str, Any]] = self.iter_delivered(source)
            if county and county != self.whole_key():
                rows = (r for r in rows if self.jurisdiction(self.kept(r)) == county)
            content = self.sample(url, rows, int(p["limit"]))
            return Fetched(self.source_id, url, at, None, content, "application/json")
        if self.per_county_files:
            if county is None:
                raise ValueError(f"{self.source_id}: county= is required (see partitions())")
            member = self.county_files(source).get(county)
            if member is None:
                raise RuntimeError(f"{source}: no file for county {county}")
            return Fetched(self.source_id, f"{url}&member={member}", at, None,
                           self.member_bytes(source, member), "text/plain")  # fmt: skip
        if self.county_column and county and county != self.whole_key():
            if county not in self.split(source):
                raise RuntimeError(f"{source}: no registrations in county {county}")
            body = (self._extract_dir(source) / f"{county}.tsv.gz").read_bytes()
            return Fetched(self.source_id, url, at, None, body, "application/gzip")
        if self.county_column:
            raise ValueError(f"{self.source_id}: county= is required (see partitions())")
        if source.is_dir():
            members = [n for n, _ in iter_members(source, self.include, self.exclude)]
            if len(members) != 1:
                raise RuntimeError(f"{source}: expected one voter file, found {members}")
            source = next(f for f in source.rglob("*") if f.name == members[0])
        return Fetched(self.source_id, url, at, None, source.read_bytes(),
                       "application/octet-stream")  # fmt: skip

    # -- provenance -------------------------------------------------------------------------
    def source_row(self) -> Mapping[str, Any]:
        return {
            **self.source_row_base(),
            "cost_model": self.cost_model,
            "robots_checked_on": None,  # nothing is fetched from the state's site
            "base_url": self.request_url,
            "terms_url": self.request_url,
            "terms_checked_on": CHECKED_ON,
            "terms_summary": self.terms_summary,
        }

    def health(self) -> HealthReport:
        """No network: whether a delivery is on hand and its header carries the kept
        columns (a layout change shows up as missing columns)."""
        now = datetime.now(UTC)
        try:
            source = self.delivered()
        except RuntimeError as e:
            return HealthReport(self.source_id, False, now, f"awaiting delivery: {e}")
        first = next(iter(self.iter_delivered(source)), None)
        cols = set(self.canonical(first)) if first else set()
        missing = sorted(set(self.keep) - cols - set(self.optional))
        ok = first is not None and not missing
        detail = "ok" if ok else f"file={source.name} missing={missing}"
        return HealthReport(self.source_id, ok, now, detail, tuple(sorted(cols)))


# -- county tables (FIPS order; see fips_table) -------------------------------------------
AR_COUNTIES = (
    "Arkansas", "Ashley", "Baxter", "Benton", "Boone", "Bradley", "Calhoun", "Carroll",
    "Chicot", "Clark", "Clay", "Cleburne", "Cleveland", "Columbia", "Conway", "Craighead",
    "Crawford", "Crittenden", "Cross", "Dallas", "Desha", "Drew", "Faulkner", "Franklin",
    "Fulton", "Garland", "Grant", "Greene", "Hempstead", "Hot Spring", "Howard",
    "Independence", "Izard", "Jackson", "Jefferson", "Johnson", "Lafayette", "Lawrence", "Lee",
    "Lincoln", "Little River", "Logan", "Lonoke", "Madison", "Marion", "Miller", "Mississippi",
    "Monroe", "Montgomery", "Nevada", "Newton", "Ouachita", "Perry", "Phillips", "Pike",
    "Poinsett", "Polk", "Pope", "Prairie", "Pulaski", "Randolph", "St. Francis", "Saline",
    "Scott", "Searcy", "Sebastian", "Sevier", "Sharp", "Stone", "Union", "Van Buren",
    "Washington", "White", "Woodruff", "Yell",
)  # fmt: skip
CO_COUNTIES = (  # Broomfield (08014, created 2001) is the one code outside the 2n-1 run
    "Adams", "Alamosa", "Arapahoe", "Archuleta", "Baca", "Bent", "Boulder", "Chaffee",
    "Cheyenne", "Clear Creek", "Conejos", "Costilla", "Crowley", "Custer", "Delta", "Denver",
    "Dolores", "Douglas", "Eagle", "Elbert", "El Paso", "Fremont", "Garfield", "Gilpin",
    "Grand", "Gunnison", "Hinsdale", "Huerfano", "Jackson", "Jefferson", "Kiowa", "Kit Carson",
    "Lake", "La Plata", "Larimer", "Las Animas", "Lincoln", "Logan", "Mesa", "Mineral",
    "Moffat", "Montezuma", "Montrose", "Morgan", "Otero", "Ouray", "Park", "Phillips", "Pitkin",
    "Prowers", "Pueblo", "Rio Blanco", "Rio Grande", "Routt", "Saguache", "San Juan",
    "San Miguel", "Sedgwick", "Summit", "Teller", "Washington", "Weld", "Yuma",
)  # fmt: skip
# Florida: (extract county code, name) in FIPS order. Miami-Dade (code DAD) is 12086, not
# the 12025 its alphabetical slot as 'Dade' would give.
FL_COUNTIES = (
    ("ALA", "Alachua"), ("BAK", "Baker"), ("BAY", "Bay"), ("BRA", "Bradford"),
    ("BRE", "Brevard"), ("BRO", "Broward"), ("CAL", "Calhoun"), ("CHA", "Charlotte"),
    ("CIT", "Citrus"), ("CLA", "Clay"), ("CLL", "Collier"), ("CLM", "Columbia"),
    ("DAD", "Miami-Dade"), ("DES", "DeSoto"), ("DIX", "Dixie"), ("DUV", "Duval"),
    ("ESC", "Escambia"), ("FLA", "Flagler"), ("FRA", "Franklin"), ("GAD", "Gadsden"),
    ("GIL", "Gilchrist"), ("GLA", "Glades"), ("GUL", "Gulf"), ("HAM", "Hamilton"),
    ("HAR", "Hardee"), ("HEN", "Hendry"), ("HER", "Hernando"), ("HIG", "Highlands"),
    ("HIL", "Hillsborough"), ("HOL", "Holmes"), ("IND", "Indian River"), ("JAC", "Jackson"),
    ("JEF", "Jefferson"), ("LAF", "Lafayette"), ("LAK", "Lake"), ("LEE", "Lee"),
    ("LEO", "Leon"), ("LEV", "Levy"), ("LIB", "Liberty"), ("MAD", "Madison"),
    ("MAN", "Manatee"), ("MRN", "Marion"), ("MRT", "Martin"), ("MON", "Monroe"),
    ("NAS", "Nassau"), ("OKA", "Okaloosa"), ("OKE", "Okeechobee"), ("ORA", "Orange"),
    ("OSC", "Osceola"), ("PAL", "Palm Beach"), ("PAS", "Pasco"), ("PIN", "Pinellas"),
    ("POL", "Polk"), ("PUT", "Putnam"), ("STJ", "St. Johns"), ("STL", "St. Lucie"),
    ("SAN", "Santa Rosa"), ("SAR", "Sarasota"), ("SEM", "Seminole"), ("SUM", "Sumter"),
    ("SUW", "Suwannee"), ("TAY", "Taylor"), ("UNI", "Union"), ("VOL", "Volusia"),
    ("WAK", "Wakulla"), ("WAL", "Walton"), ("WAS", "Washington"),
)  # fmt: skip
MI_COUNTIES = (  # also QVF COUNTY_CODE order (01 Alcona ... 82 Wayne, 83 Wexford)
    "Alcona", "Alger", "Allegan", "Alpena", "Antrim", "Arenac", "Baraga", "Barry", "Bay",
    "Benzie", "Berrien", "Branch", "Calhoun", "Cass", "Charlevoix", "Cheboygan", "Chippewa",
    "Clare", "Clinton", "Crawford", "Delta", "Dickinson", "Eaton", "Emmet", "Genesee",
    "Gladwin", "Gogebic", "Grand Traverse", "Gratiot", "Hillsdale", "Houghton", "Huron",
    "Ingham", "Ionia", "Iosco", "Iron", "Isabella", "Jackson", "Kalamazoo", "Kalkaska", "Kent",
    "Keweenaw", "Lake", "Lapeer", "Leelanau", "Lenawee", "Livingston", "Luce", "Mackinac",
    "Macomb", "Manistee", "Marquette", "Mason", "Mecosta", "Menominee", "Midland", "Missaukee",
    "Monroe", "Montcalm", "Montmorency", "Muskegon", "Newaygo", "Oakland", "Oceana", "Ogemaw",
    "Ontonagon", "Osceola", "Oscoda", "Otsego", "Ottawa", "Presque Isle", "Roscommon",
    "Saginaw", "St. Clair", "St. Joseph", "Sanilac", "Schoolcraft", "Shiawassee", "Tuscola",
    "Van Buren", "Washtenaw", "Wayne", "Wexford",
)  # fmt: skip
MS_COUNTIES = (
    "Adams", "Alcorn", "Amite", "Attala", "Benton", "Bolivar", "Calhoun", "Carroll",
    "Chickasaw", "Choctaw", "Claiborne", "Clarke", "Clay", "Coahoma", "Copiah", "Covington",
    "DeSoto", "Forrest", "Franklin", "George", "Greene", "Grenada", "Hancock", "Harrison",
    "Hinds", "Holmes", "Humphreys", "Issaquena", "Itawamba", "Jackson", "Jasper", "Jefferson",
    "Jefferson Davis", "Jones", "Kemper", "Lafayette", "Lamar", "Lauderdale", "Lawrence",
    "Leake", "Lee", "Leflore", "Lincoln", "Lowndes", "Madison", "Marion", "Marshall", "Monroe",
    "Montgomery", "Neshoba", "Newton", "Noxubee", "Oktibbeha", "Panola", "Pearl River",
    "Perry", "Pike", "Pontotoc", "Prentiss", "Quitman", "Rankin", "Scott", "Sharkey",
    "Simpson", "Smith", "Stone", "Sunflower", "Tallahatchie", "Tate", "Tippah", "Tishomingo",
    "Tunica", "Union", "Walthall", "Warren", "Washington", "Wayne", "Webster", "Wilkinson",
    "Winston", "Yalobusha", "Yazoo",
)  # fmt: skip
WI_COUNTIES = (  # Menominee (55078, created 1961) is the one code outside the 2n-1 run
    "Adams", "Ashland", "Barron", "Bayfield", "Brown", "Buffalo", "Burnett", "Calumet",
    "Chippewa", "Clark", "Columbia", "Crawford", "Dane", "Dodge", "Door", "Douglas", "Dunn",
    "Eau Claire", "Florence", "Fond du Lac", "Forest", "Grant", "Green", "Green Lake", "Iowa",
    "Iron", "Jackson", "Jefferson", "Juneau", "Kenosha", "Kewaunee", "La Crosse", "Lafayette",
    "Langlade", "Lincoln", "Manitowoc", "Marathon", "Marinette", "Marquette", "Milwaukee",
    "Monroe", "Oconto", "Oneida", "Outagamie", "Ozaukee", "Pepin", "Pierce", "Polk", "Portage",
    "Price", "Racine", "Richland", "Rock", "Rusk", "St. Croix", "Sauk", "Sawyer", "Shawano",
    "Sheboygan", "Taylor", "Trempealeau", "Vernon", "Vilas", "Walworth", "Washburn",
    "Washington", "Waukesha", "Waupaca", "Waushara", "Winnebago", "Wood",
)  # fmt: skip


def _fl_fips() -> dict[str, str]:
    table = fips_table("12", tuple(name for _, name in FL_COUNTIES), {"Miami-Dade": "086"})
    for code, name in FL_COUNTIES:
        table[code] = table[_squash(name)]
    table["DADE"] = table["MIAMIDADE"]
    return table


class FloridaVoterFile(DeliveredVoterFile):
    """Florida Division of Elections monthly Voter Extract (disk by mail; free, one request a
    year covers every monthly disk). Layout: 'Voter Extract Disk File Layout' rev. 2025-05-16
    (https://files.floridados.gov/media/708728/final-voter-extract-disk-file-layout-rev-20250516.pdf):
    67 county registration files CCC_YYYYMMDD.txt plus 67 history files CCC_H_YYYYMMDD.txt,
    tab-delimited ASCII, no header, 38 fields in this order. Confidential and exempt data is
    not in the extract (ss. 119.071, 97.0585); a voter who requested a public-records
    exemption (field 7 = Y) is skipped outright. Kept: ids, name, exemption flag, residence and
    mailing address, birth date (MM/DD/YYYY), registration date, party, status. Gender, race,
    districts, phone and e-mail are never kept; the history files are never read."""

    source_id: ClassVar[str] = "fl.dos.voter_file"
    state: ClassVar[str] = "FL"
    state_fips: ClassVar[str] = "12"
    delimiter: ClassVar[str] = "\t"
    per_county_files: ClassVar[bool] = True
    include: ClassVar[re.Pattern[str]] = re.compile(r"^[A-Z]{3}_\d{8}\.txt$", re.I)
    exclude: ClassVar[re.Pattern[str] | None] = None
    request_url: ClassVar[str] = (
        "https://dos.fl.gov/elections/data-statistics/voter-registration-statistics/"
        "voter-extract-request/"
    )
    layout_url: ClassVar[str] = (
        "https://files.floridados.gov/media/708728/"
        "final-voter-extract-disk-file-layout-rev-20250516.pdf"
    )
    columns: ClassVar[tuple[str, ...]] = (
        "COUNTY_CODE", "VOTER_ID", "NAME_LAST", "NAME_SUFFIX", "NAME_FIRST", "NAME_MIDDLE",
        "REQUESTED_PUBLIC_RECORDS_EXEMPTION", "RESIDENCE_ADDRESS_LINE_1",
        "RESIDENCE_ADDRESS_LINE_2", "RESIDENCE_CITY", "RESIDENCE_STATE", "RESIDENCE_ZIPCODE",
        "MAILING_ADDRESS_LINE_1", "MAILING_ADDRESS_LINE_2", "MAILING_ADDRESS_LINE_3",
        "MAILING_CITY", "MAILING_STATE", "MAILING_ZIPCODE", "MAILING_COUNTRY", "GENDER", "RACE",
        "BIRTH_DATE", "REGISTRATION_DATE", "PARTY_AFFILIATION", "PRECINCT", "PRECINCT_GROUP",
        "PRECINCT_SPLIT", "PRECINCT_SUFFIX", "VOTER_STATUS", "CONGRESSIONAL_DISTRICT",
        "HOUSE_DISTRICT", "SENATE_DISTRICT", "COUNTY_COMMISSION_DISTRICT",
        "SCHOOL_BOARD_DISTRICT", "DAYTIME_AREA_CODE", "DAYTIME_PHONE_NUMBER",
        "DAYTIME_PHONE_EXTENSION", "EMAIL_ADDRESS",
    )  # fmt: skip
    keep: ClassVar[tuple[str, ...]] = (
        "COUNTY_CODE", "VOTER_ID", "NAME_LAST", "NAME_SUFFIX", "NAME_FIRST", "NAME_MIDDLE",
        "REQUESTED_PUBLIC_RECORDS_EXEMPTION", "RESIDENCE_ADDRESS_LINE_1",
        "RESIDENCE_ADDRESS_LINE_2", "RESIDENCE_CITY", "RESIDENCE_STATE", "RESIDENCE_ZIPCODE",
        "MAILING_ADDRESS_LINE_1", "MAILING_ADDRESS_LINE_2", "MAILING_ADDRESS_LINE_3",
        "MAILING_CITY", "MAILING_STATE", "MAILING_ZIPCODE", "MAILING_COUNTRY", "BIRTH_DATE",
        "REGISTRATION_DATE", "PARTY_AFFILIATION", "VOTER_STATUS",
    )  # fmt: skip
    pii_fields: ClassVar[tuple[str, ...]] = (
        "VOTER_ID", "NAME_LAST", "NAME_SUFFIX", "NAME_FIRST", "NAME_MIDDLE",
        "RESIDENCE_ADDRESS_LINE_1", "RESIDENCE_ADDRESS_LINE_2", "MAILING_ADDRESS_LINE_1",
        "MAILING_ADDRESS_LINE_2", "MAILING_ADDRESS_LINE_3", "BIRTH_DATE", "REGISTRATION_DATE",
    )  # fmt: skip
    placeholders: ClassVar[frozenset[str]] = frozenset({"*"})
    config: ClassVar[Mapping[str, Any]] = {"skip_names": ("*",)}
    fips: ClassVar[Mapping[str, str]] = _fl_fips()
    id_column: ClassVar[str] = "VOTER_ID"
    county_column: ClassVar[str] = "COUNTY_CODE"
    name_columns: ClassVar[tuple[str, str, str, str]] = (
        "NAME_LAST", "NAME_FIRST", "NAME_MIDDLE", "NAME_SUFFIX")  # fmt: skip
    res_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("RESIDENCE_ADDRESS_LINE_1", "RESIDENCE_ADDRESS_LINE_2"), "RESIDENCE_CITY",
        "RESIDENCE_STATE", "RESIDENCE_ZIPCODE")  # fmt: skip
    mail_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("MAILING_ADDRESS_LINE_1", "MAILING_ADDRESS_LINE_2", "MAILING_ADDRESS_LINE_3"),
        "MAILING_CITY", "MAILING_STATE", "MAILING_ZIPCODE")  # fmt: skip
    terms_summary: ClassVar[str] = (
        "Florida DOS monthly voter extract: public record (ch. 97-98 Fla. Stat.); free, by "
        "e-mail or mail request, delivered on disk by mail or pickup, 'NOT available by email "
        "or online'; one request a year covers all monthly disks. The 2004 s. 98.095 oath and "
        "use limit is absent from every compilation 2005-2026; no use restriction (research "
        "2026-11-25). Exempt (s. 119.071) and confidential (s. 97.0585, ACP) data excluded."
    )

    def skip(self, r: Mapping[str, Any]) -> bool:
        return (_text(r.get("REQUESTED_PUBLIC_RECORDS_EXEMPTION")) or "").upper() == "Y"

    def residence(self, r: Mapping[str, Any]) -> dict[str, Any] | None:
        return self._address({**r, "RESIDENCE_STATE": _text(r.get("RESIDENCE_STATE")) or "FL"},
                             self.res_columns)  # fmt: skip


MI_FIXED = (  # QVF 'Voter File Layout' (.lst, fixed-length ASCII), 0-based [start, end)
    ("LAST_NAME", 0, 35), ("FIRST_NAME", 35, 55), ("MIDDLE_NAME", 55, 75),
    ("NAME_SUFFIX", 75, 78), ("YEAR_OF_BIRTH", 78, 82), ("GENDER", 82, 83),
    ("REGISTRATION_DATE", 83, 91), ("STREET_NUMBER_PREFIX", 91, 92), ("STREET_NUMBER", 92, 99),
    ("STREET_NUMBER_SUFFIX", 99, 103), ("DIRECTION_PREFIX", 103, 105),
    ("STREET_NAME", 105, 135), ("STREET_TYPE", 135, 141), ("DIRECTION_SUFFIX", 141, 143),
    ("EXTENSION", 143, 156), ("CITY", 156, 191), ("STATE", 191, 193), ("ZIP_CODE", 193, 198),
    ("MAILING_ADDRESS_LINE_ONE", 198, 248), ("MAILING_ADDRESS_LINE_TWO", 248, 298),
    ("MAILING_ADDRESS_LINE_THREE", 298, 348), ("MAILING_ADDRESS_LINE_FOUR", 348, 398),
    ("MAILING_ADDRESS_LINE_FIVE", 398, 448), ("VOTER_IDENTIFICATION_NUMBER", 448, 461),
    ("COUNTY_CODE", 461, 463), ("JURISDICTION_CODE", 463, 468), ("WARD_PRECINCT", 468, 474),
    ("SCHOOL_DISTRICT_CODE", 474, 479), ("STATE_HOUSE_DISTRICT_CODE", 479, 484),
    ("STATE_SENATE_DISTRICT_CODE", 484, 489), ("US_CONGRESS_DISTRICT_CODE", 489, 494),
    ("COUNTY_COMMISSIONER_DISTRICT_CODE", 494, 499), ("VILLAGE_DISTRICT_CODE", 499, 504),
    ("VILLAGE_PRECINCT", 504, 510), ("SCHOOL_PRECINCT", 510, 516),
    ("IS_PERMANENT_ABSENTEE_VOTER", 516, 517), ("VOTER_STATUS_TYPE_CODE", 517, 519),
)  # fmt: skip
MI_MAIL = tuple(f"MAILING_ADDRESS_LINE_{n}" for n in ("ONE", "TWO", "THREE", "FOUR", "FIVE"))
MI_STREET = ("STREET_NUMBER_PREFIX", "STREET_NUMBER", "STREET_NUMBER_SUFFIX",
             "DIRECTION_PREFIX", "STREET_NAME", "STREET_TYPE", "DIRECTION_SUFFIX",
             "EXTENSION")  # fmt: skip


class MichiganVoterFile(DeliveredVoterFile):
    """Michigan Qualified Voter File (Bureau of Elections, by FOIA request on the QVF Data
    Request Form, rev. 03/26: https://www.michigan.gov/-/media/Project/Websites/sos/02lehman/FOIA_FORM.pdf).
    Delivered on an encrypted flash drive, by FTP or for pickup, with the state's own file
    layout, county/jurisdiction code lists and a separate voter-history file. The form names
    both CSV and fixed-length ASCII; both are read: the CSV by its header (EntireStateVoters
    style: LAST_NAME ... VOTER_IDENTIFICATION_NUMBER, COUNTY_CODE, COUNTY_NAME ...), the .lst
    by the fixed positions in MI_FIXED. MDOS does not publish the layout online (it ships with
    the file); column names and positions follow the delivered files as documented by the
    Voteshield 'reggie' Michigan config and preprocessor
    (https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/michigan.yaml),
    to be checked against the layout on the drive. Each record: complete name, residential
    and mailing address, year of birth, registration date (MMDDYYYY), status, voter ID.
    Month/day of birth, phone, e-mail, DL number, SSN digits and signature are FOIA-exempt
    (MCL 168.509gg) and never in the file. Gender, districts and history are never kept."""

    source_id: ClassVar[str] = "mi.sos.voter_file"
    state: ClassVar[str] = "MI"
    state_fips: ClassVar[str] = "26"
    exclude: ClassVar[re.Pattern[str] | None] = re.compile(
        r"hist|layout|readme|code|cd\.lst$|list_of", re.I)  # fmt: skip
    request_url: ClassVar[str] = (
        "https://www.michigan.gov/-/media/Project/Websites/sos/02lehman/FOIA_FORM.pdf"
    )
    layout_url: ClassVar[str] = (
        "https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/michigan.yaml"
    )
    keep: ClassVar[tuple[str, ...]] = (
        "VOTER_IDENTIFICATION_NUMBER", "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "NAME_SUFFIX",
        "YEAR_OF_BIRTH", "REGISTRATION_DATE", *MI_STREET, "CITY", "STATE", "ZIP_CODE",
        *MI_MAIL, "COUNTY_CODE", "COUNTY_NAME", "JURISDICTION_CODE", "JURISDICTION_NAME",
        "VOTER_STATUS_TYPE_CODE",
    )  # fmt: skip
    pii_fields: ClassVar[tuple[str, ...]] = (
        "VOTER_IDENTIFICATION_NUMBER", "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "NAME_SUFFIX",
        "YEAR_OF_BIRTH", "REGISTRATION_DATE", *MI_STREET, *MI_MAIL,
    )  # fmt: skip
    optional: ClassVar[tuple[str, ...]] = ("COUNTY_NAME", "JURISDICTION_NAME")  # CSV only
    aliases: ClassVar[Mapping[str, str]] = {"STATE_ADDR": "STATE"}
    fips: ClassVar[Mapping[str, str]] = fips_table("26", MI_COUNTIES, numbered=True)
    id_column: ClassVar[str] = "VOTER_IDENTIFICATION_NUMBER"
    county_column: ClassVar[str] = "COUNTY_CODE"
    name_columns: ClassVar[tuple[str, str, str, str]] = (
        "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "NAME_SUFFIX")  # fmt: skip
    res_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        MI_STREET, "CITY", "STATE", "ZIP_CODE")  # fmt: skip
    mail_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (MI_MAIL, "", "", "")
    cost_model: ClassVar[str] = "fee"
    terms_summary: ClassVar[str] = (
        "Michigan QVF by FOIA (MCL 15.231 et seq.) to the Bureau of Elections on the QVF Data "
        "Request Form (rev. 03/26): any requester, no purpose or use certification; FOIA "
        "processing fee (EAC lists about $23, unverified). MCL 168.509gg exempts fields only "
        "(DL/ID no., month and day of birth, phone, e-mail, signature, SSN digits) and places "
        "no limit on use (research 2026-11-25)."
    )

    def read_member(self, name: str, raw: ByteStream) -> Iterator[dict[str, str]]:
        with _text_stream(raw) as text:
            first = text.readline()
            lines = itertools.chain([first], text)
            if "LAST_NAME" in first.upper() and not name.lower().endswith(".lst"):
                yield from iter_header_rows(lines)
            else:
                yield from iter_fixed_rows(lines, MI_FIXED)

    def jurisdiction(self, r: Mapping[str, Any]) -> str:
        """COUNTY_CODE (01-83, alphabetical) first; COUNTY_NAME when the code is blank."""
        for col in ("COUNTY_CODE", "COUNTY_NAME"):
            value = _text(r.get(col))
            if value and (value.lstrip("0") in self.fips or _squash(value) in self.fips):
                return self.fips.get(value.lstrip("0")) or self.fips[_squash(value)]
        return self.state_fips

    def mailing(self, r: Mapping[str, Any]) -> dict[str, Any] | None:
        return split_city_line([_text(r.get(c)) for c in MI_MAIL])


class ColoradoVoterFile(DeliveredVoterFile):
    """Colorado Secretary of State Statewide Registered Voter List (EX-003), bought on the
    Elections Data Request Form (rev. Nov 2024,
    https://www.coloradosos.gov/pubs/elections/forms/dataRequests.pdf): $50 a report on disc
    (returned by first-class mail within 72 hours) or the $1,000 2025-2026 election-cycle
    subscription (download, updated weekly). One statewide file, delimited text with a header,
    from SCORE; the SoS publishes no layout. Columns follow the EX-003 headers documented by
    the Voteshield 'reggie' Colorado config
    (https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/colorado.yaml) and
    the SCORE field list counties publish (Douglas County EX-002 fields:
    https://www.douglas.co.us/documents/fields-for-master-voter-history-list-with-details.pdf);
    the short SCORE export names (RES_ADDRESS, MAIL_ADDR1, YOB, COUNTY_REGN_DATE...) that
    county exports such as Boulder's VR-011B use are aliases, so either reads. Public fields
    per the SoS FAQ: name, residential address, party and affiliation date, phone and gender
    if provided, birth year, history. Confidential (C.R.S. 24-72-204(3.5)) and ACP voters
    are not in the file. Phone, gender and districts are never kept."""

    source_id: ClassVar[str] = "co.sos.voter_file"
    state: ClassVar[str] = "CO"
    state_fips: ClassVar[str] = "08"
    exclude: ClassVar[re.Pattern[str] | None] = re.compile(
        r"hist|EX-002|layout|readme|code|split_district", re.I)  # fmt: skip
    request_url: ClassVar[str] = "https://www.coloradosos.gov/pubs/elections/forms/dataRequests.pdf"
    layout_url: ClassVar[str] = (
        "https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/colorado.yaml"
    )
    keep: ClassVar[tuple[str, ...]] = (
        "VOTER_ID", "COUNTY_CODE", "COUNTY", "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME",
        "NAME_SUFFIX", "RESIDENTIAL_ADDRESS", "RESIDENTIAL_CITY", "RESIDENTIAL_STATE",
        "RESIDENTIAL_ZIP_CODE", "RESIDENTIAL_ZIP_PLUS", "MAILING_ADDRESS_1", "MAILING_ADDRESS_2",
        "MAILING_ADDRESS_3", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP_CODE",
        "MAILING_ZIP_PLUS", "MAILING_COUNTRY", "REGISTRATION_DATE", "EFFECTIVE_DATE", "STATUS",
        "STATUS_REASON", "BIRTH_YEAR", "PARTY", "PARTY_AFFILIATION_DATE",
    )  # fmt: skip
    pii_fields: ClassVar[tuple[str, ...]] = (
        "VOTER_ID", "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "NAME_SUFFIX",
        "RESIDENTIAL_ADDRESS", "MAILING_ADDRESS_1", "MAILING_ADDRESS_2", "MAILING_ADDRESS_3",
        "REGISTRATION_DATE", "EFFECTIVE_DATE", "BIRTH_YEAR",
    )  # fmt: skip
    optional: ClassVar[tuple[str, ...]] = ("COUNTY_CODE", "PARTY_AFFILIATION_DATE")
    aliases: ClassVar[Mapping[str, str]] = {
        "RES_ADDRESS": "RESIDENTIAL_ADDRESS", "RES_CITY": "RESIDENTIAL_CITY",
        "RES_STATE": "RESIDENTIAL_STATE", "RES_ZIP_CODE": "RESIDENTIAL_ZIP_CODE",
        "RES_ZIP_PLUS": "RESIDENTIAL_ZIP_PLUS", "MAIL_ADDR1": "MAILING_ADDRESS_1",
        "MAIL_ADDR2": "MAILING_ADDRESS_2", "MAIL_ADDR3": "MAILING_ADDRESS_3",
        "MAILING_ZIP": "MAILING_ZIP_CODE", "YOB": "BIRTH_YEAR",
        "COUNTY_REGN_DATE": "REGISTRATION_DATE", "EFF_DATE": "EFFECTIVE_DATE",
        "POLPARTY_AFF_DATE": "PARTY_AFFILIATION_DATE", "VOTER_STATUS": "STATUS",
    }  # fmt: skip
    fips: ClassVar[Mapping[str, str]] = fips_table("08", CO_COUNTIES, {"Broomfield": "014"})
    id_column: ClassVar[str] = "VOTER_ID"
    county_column: ClassVar[str] = "COUNTY"
    name_columns: ClassVar[tuple[str, str, str, str]] = (
        "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "NAME_SUFFIX")  # fmt: skip
    res_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("RESIDENTIAL_ADDRESS",), "RESIDENTIAL_CITY", "RESIDENTIAL_STATE",
        "RESIDENTIAL_ZIP_CODE")  # fmt: skip
    mail_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("MAILING_ADDRESS_1", "MAILING_ADDRESS_2", "MAILING_ADDRESS_3"), "MAILING_CITY",
        "MAILING_STATE", "MAILING_ZIP_CODE")  # fmt: skip
    cost_model: ClassVar[str] = "paid"
    terms_summary: ClassVar[str] = (
        "Colorado SoS Statewide Registered Voter List (EX-003): any person, Elections Data "
        "Request Form (rev. Nov 2024) with no purpose or use certification; $50 per report "
        "on disc or $1,000 per election-cycle subscription. SoS FAQ: public voter data is "
        "provided 'without regard to how these people might use the information'. C.R.S. "
        "1-2-227, 24-72-204(8): no use restriction (research 2026-11-25)."
    )


class BoulderCountyVoterFile(ColoradoVoterFile):
    """Boulder County (CO) Clerk and Recorder 'Registered Voter Data (VR-011B)': active and
    inactive registered voters of one county (confidential voters left out), one pipe-delimited
    SCORE export in a zip, posted free with no login on the county's data-access page and
    updated once a month (page text read 2026-11-25). Same columns as ColoradoVoterFile reads
    through its SCORE aliases (YOB, RES_ADDRESS, MAIL_ADDR1, COUNTY_REGN_DATE...); phone,
    gender and ballot address are dropped the same way. Downloaded directly: robots.txt of the
    file host (election.boco.solutions) is absent (404) and bouldercounty.gov allows every
    path (checked 2026-11-25). One partition: the county. path= reads a saved copy instead."""

    source_id: ClassVar[str] = "co.boulder.voter_file"
    access_method: ClassVar[str] = "bulk"
    cost_model: ClassVar[str] = "free"
    request_url: ClassVar[str] = "https://bouldercounty.gov/elections/maps-and-data/data-access/"
    download_url: ClassVar[str] = (
        "https://election.boco.solutions/ElectionDataPublicFiles/CE-VR011B_EXTERNAL.zip"
    )
    county_fips: ClassVar[str] = "08013"
    terms_summary: ClassVar[str] = (
        "Boulder County Clerk and Recorder, Registered Voter Data (VR-011B): free download, no "
        "login, form or use certification (county data-access page, read 2026-11-25). "
        "Colorado voter registration records are public (C.R.S. 1-2-227) and the SoS provides "
        "them 'without regard to how these people might use the information': no use "
        "restriction found (reports/Voter file access by state.md). Internal use only, not "
        "redistributed."
    )

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {"county": self.county_fips}

    def fetch(self, request: FetchRequest) -> Fetched:
        """The county zip as published (or a JSON sample with limit=); path= reads a copy
        saved by hand, as the statewide Colorado adapter does."""
        p = request.params
        if p.get("path"):
            return super().fetch(request)
        resp = self.client.get(self.download_url)
        if resp.status != 200 or resp.content[:2] != b"PK":
            raise RuntimeError(
                f"{self.download_url}: HTTP {resp.status} ({resp.content_type}); not the voter "
                f"file zip. Save it by hand from {self.request_url} and pass path=<file>."
            )
        content, ctype = resp.content, resp.content_type or "application/zip"
        if "limit" in p:
            content = self.sample(resp.url, self.raw_rows(resp.content), int(p["limit"]))
            ctype = "application/json"
        return Fetched(self.source_id, resp.url, resp.retrieved_at, resp.status, content, ctype)

    def source_row(self) -> Mapping[str, Any]:
        return {**super().source_row(), "jurisdiction": self.county_fips,
                "base_url": self.download_url, "robots_checked_on": CHECKED_ON}  # fmt: skip

    def health(self) -> HealthReport:
        """The data-access page answers and still links the VR-011B zip (no 16 MB download)."""
        now = datetime.now(UTC)
        try:
            resp = self.client.get(self.request_url)
        except OSError as e:
            return HealthReport(self.source_id, False, now, repr(e))
        ok = resp.status == 200 and self.download_url.encode() in resp.content
        detail = "ok" if ok else f"status={resp.status}; VR-011B link not found"
        return HealthReport(self.source_id, ok, now, detail)


class WisconsinVoterFile(DeliveredVoterFile):
    """Wisconsin Elections Commission WisVote voter list, bought through Badger Voters
    (https://badgervoters.wi.gov; My Wisconsin ID account with MFA since 2025-12-22; $25 +
    $5 per 1,000 records, capped at $12,500), downloaded as CSV (zipped when large) from the
    account. Layout: WEC 'Standard Data Elements in a Voter Data File Request'
    (https://badgervoters.wi.gov/img/Voter%20Data%20Request%20Data%20Elements.pdf) and its
    example CSV: Voter Reg Number (an encrypted customer number), LastName, FirstName,
    MiddleName, Suffix, PhoneNumber, EmailAddress, Address1 (street and unit), Address2
    (city, state and ZIP), MailingAddress1/2, MailingCityStateZip, sort fields, Jurisdiction,
    districts, County ('Milwaukee County'), Voter Status, Voter Status Reason,
    RegistrationDate, ApplicationSource, IsPermanentAbsentee, Voter Type, then one column per
    election (history, never kept). No date of birth, age, party, DL or SSN; confidential
    (s. 6.47) and protected judicial voters are not in the file. Phone and e-mail are never
    kept."""

    source_id: ClassVar[str] = "wi.wec.voter_file"
    state: ClassVar[str] = "WI"
    state_fips: ClassVar[str] = "55"
    request_url: ClassVar[str] = "https://badgervoters.wi.gov/faq"
    layout_url: ClassVar[str] = (
        "https://badgervoters.wi.gov/img/Voter%20Data%20Request%20Data%20Elements.pdf"
    )
    exclude: ClassVar[re.Pattern[str] | None] = re.compile(r"absentee|readme|layout", re.I)
    keep: ClassVar[tuple[str, ...]] = (
        "VOTER_REG_NUMBER", "LASTNAME", "FIRSTNAME", "MIDDLENAME", "SUFFIX", "ADDRESS1",
        "ADDRESS2", "MAILINGADDRESS1", "MAILINGADDRESS2", "MAILINGCITYSTATEZIP", "HOUSENUMBER",
        "STREETNAME", "UNITTYPE", "UNITNUMBER", "ZIPCODE", "JURISDICTION", "COUNTY",
        "MUNICIPALITY", "VOTER_STATUS", "VOTER_STATUS_REASON", "REGISTRATIONDATE", "VOTER_TYPE",
    )  # fmt: skip
    pii_fields: ClassVar[tuple[str, ...]] = (
        "VOTER_REG_NUMBER", "LASTNAME", "FIRSTNAME", "MIDDLENAME", "SUFFIX", "ADDRESS1",
        "ADDRESS2", "MAILINGADDRESS1", "MAILINGADDRESS2", "MAILINGCITYSTATEZIP", "HOUSENUMBER",
        "STREETNAME", "UNITNUMBER", "REGISTRATIONDATE",
    )  # fmt: skip
    aliases: ClassVar[Mapping[str, str]] = {"APPLICATIONDATE": "REGISTRATIONDATE"}
    fips: ClassVar[Mapping[str, str]] = fips_table("55", WI_COUNTIES, {"Menominee": "078"})
    id_column: ClassVar[str] = "VOTER_REG_NUMBER"
    county_column: ClassVar[str] = "COUNTY"
    name_columns: ClassVar[tuple[str, str, str, str]] = (
        "LASTNAME", "FIRSTNAME", "MIDDLENAME", "SUFFIX")  # fmt: skip
    res_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("ADDRESS1", "ADDRESS2"), "", "", "ZIPCODE")  # fmt: skip
    mail_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("MAILINGADDRESS1", "MAILINGADDRESS2", "MAILINGCITYSTATEZIP"), "", "", "")  # fmt: skip
    cost_model: ClassVar[str] = "paid"
    terms_summary: ClassVar[str] = (
        "Wisconsin Elections Commission voter list via Badger Voters: any account holder "
        "(My Wisconsin ID with MFA); $25 base + $5 per 1,000 records, capped at $12,500. "
        "Badger Voters FAQ: 'Wisconsin law does not place any restrictions on the use of data "
        "obtained through this website.' No DOB, age, DL or SSN; confidential (s. 6.47) and "
        "protected voters excluded (research 2026-11-25)."
    )

    def residence(self, r: Mapping[str, Any]) -> dict[str, Any] | None:
        return split_city_line([_text(r.get("ADDRESS1")), _text(r.get("ADDRESS2"))],
                               r.get("ZIPCODE"))  # fmt: skip

    def mailing(self, r: Mapping[str, Any]) -> dict[str, Any] | None:
        return split_city_line([_text(r.get(c)) for c in self.mail_columns[0]])


AR_STREET = ("TEXT_REGISTRANT_ADDRESS_NBR", "TEXT_RES_ADDRESS_NBR_SUFFIX",
             "CDE_STREET_DIR_PREFIX", "TEXT_STREET_NAME", "DESC_STREET_TYPE",
             "CDE_STREET_DIR_SUFFIX", "DESC_UNIT_TYPE", "TEXT_RES_UNIT_NUBR")  # fmt: skip
AR_MAIL = ("TEXT_MAIL_ADDRESS1", "TEXT_MAIL_ADDRESS2", "TEXT_MAIL_ADDRESS3",
           "TEXT_MAIL_ADDRESS4")  # fmt: skip


class ArkansasVoterFile(DeliveredVoterFile):
    """Arkansas Secretary of State statewide voter registration file (VR; VH is the separate
    history file, VRVH the two combined), requested from the Elections Division (the SoS Data
    Request Form, sections A and B; the last published copy,
    https://www.sos.arkansas.gov/uploads/Data_Request_Form_Updated.pdf, returned 404 on
    2026-11-25, so ask voterservices@sos.arkansas.gov for the current form). Reported as no
    cost, delivered by Dropbox link. The SoS publishes no layout online; VR.csv is a CSV with
    a header, columns as documented by the Voteshield 'reggie' Arkansas config
    (https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/arkansas.yaml):
    County, VoterID, status and reason codes, date_of_birth, date_of_registration, name parts
    (TEXT_NAME_LAST...), residential street parts, city, state and ZIP, mailing lines 1-4 and
    ZIP, precinct, CDE_PARTY, phone parts, districts, DateLastVoted. Secure (§ 7-5-412)
    voters' addresses are withheld by the state. Phone, districts and the last-voted date are
    never kept; the VH file is never read."""

    source_id: ClassVar[str] = "ar.sos.voter_file"
    state: ClassVar[str] = "AR"
    state_fips: ClassVar[str] = "05"
    exclude: ClassVar[re.Pattern[str] | None] = re.compile(r"^vh|hist|layout|readme", re.I)
    request_url: ClassVar[str] = "https://www.sos.arkansas.gov/frequently-asked-questions/35"
    layout_url: ClassVar[str] = (
        "https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/arkansas.yaml"
    )
    keep: ClassVar[tuple[str, ...]] = (
        "COUNTY", "VOTER_ID", "CDE_REGISTRANT_STATUS", "CDE_REGISTRANT_REASON",
        "DATE_OF_BIRTH", "DATE_OF_REGISTRATION", "TEXT_NAME_LAST", "TEXT_NAME_FIRST",
        "TEXT_NAME_MIDDLE", "CDE_NAME_SUFFIX", *AR_STREET, "TEXT_RES_CITY", "CDE_RES_STATE",
        "TEXT_RES_ZIP5", "TEXT_RES_ZIP4", *AR_MAIL, "TEXT_MAIL_ZIP5", "TEXT_MAIL_ZIP4",
        "CDE_PARTY", "DATE_OF_PARTY_AFFILIATION",
    )  # fmt: skip
    pii_fields: ClassVar[tuple[str, ...]] = (
        "VOTER_ID", "DATE_OF_BIRTH", "DATE_OF_REGISTRATION", "TEXT_NAME_LAST",
        "TEXT_NAME_FIRST", "TEXT_NAME_MIDDLE", "CDE_NAME_SUFFIX", *AR_STREET, *AR_MAIL,
    )  # fmt: skip
    optional: ClassVar[tuple[str, ...]] = ("DATE_OF_PARTY_AFFILIATION", "CDE_REGISTRANT_REASON")
    aliases: ClassVar[Mapping[str, str]] = {"VOTERID": "VOTER_ID"}
    fips: ClassVar[Mapping[str, str]] = fips_table("05", AR_COUNTIES)
    id_column: ClassVar[str] = "VOTER_ID"
    county_column: ClassVar[str] = "COUNTY"
    name_columns: ClassVar[tuple[str, str, str, str]] = (
        "TEXT_NAME_LAST", "TEXT_NAME_FIRST", "TEXT_NAME_MIDDLE", "CDE_NAME_SUFFIX")  # fmt: skip
    res_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        AR_STREET, "TEXT_RES_CITY", "CDE_RES_STATE", "TEXT_RES_ZIP5")  # fmt: skip
    mail_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        AR_MAIL, "", "", "TEXT_MAIL_ZIP5")  # fmt: skip
    terms_summary: ClassVar[str] = (
        "Arkansas SoS statewide voter registration file: requested from the Elections "
        "Division (Data Request Form; reportedly no cost, Dropbox delivery). SoS: 'there are "
        "currently no state laws restricting use of the data that the SOS releases' (form "
        "and FAQ 35, via search snippet; form URL 404 on 2026-11-25). A.C.A. § 7-5-109 not "
        "read from primary text; confirm the current form before relying on it."
    )

    def mailing(self, r: Mapping[str, Any]) -> dict[str, Any] | None:
        return split_city_line([_text(r.get(c)) for c in AR_MAIL], r.get("TEXT_MAIL_ZIP5"))


class MississippiVoterFile(DeliveredVoterFile):
    """Mississippi Secretary of State statewide voter file: free each week by e-mailed
    ShareFile link to those who sign up for the Statewide Voter File Weekly Distribution
    Program, or by Public Records Act request (PRR form, 'I would like to request a statewide
    voter file', actual cost). One CSV with a header; layout per the SoS program document
    (https://www.sos.ms.gov/content/documents/about_us/2025%20Voter%20File%20Weekly%20Distribution%20Program.pdf):
    Mapping Value, First/Middle/Last Name, Suffix, Residential Address, House Number, Street
    Name, Street Type, Pre-/Post-Direction, Residence City/State/Zip Code, Residential County,
    Precinct Code/Name, Mailing Address, Mailing City/State/Zip Code, Effective Voter
    Registration Date, Voter Status, Date Last Voted, then district columns (header names as
    in the Voteshield 'reggie' Mississippi config). Active and inactive voters. SSN, phone,
    e-mail, date of birth and age are exempt by § 23-15-165(6) and never in the file.
    Precinct, districts and date last voted are never kept; the history file is never read."""

    source_id: ClassVar[str] = "ms.sos.voter_file"
    state: ClassVar[str] = "MS"
    state_fips: ClassVar[str] = "28"
    request_url: ClassVar[str] = (
        "https://www.sos.ms.gov/content/documents/about_us/"
        "2025%20Voter%20File%20Weekly%20Distribution%20Program.pdf"
    )
    layout_url: ClassVar[str] = request_url
    keep: ClassVar[tuple[str, ...]] = (
        "MAPPING_VALUE", "FIRST_NAME", "MIDDLE_NAME", "LAST_NAME", "SUFFIX",
        "RESIDENTIAL_ADDRESS", "HOUSE_NUM", "STREET_NAME", "STREET_TYPE", "PRE_DIRECTION",
        "POST_DIRECTION", "RES_CITY", "RES_STATE", "RES_ZIP_CODE", "RES_COUNTY",
        "MAILING_ADDRESS", "MAIL_CITY", "MAIL_STATE", "MAIL_ZIP_CODE", "EFFECTIVE_REGN_DATE",
        "STATUS",
    )  # fmt: skip
    pii_fields: ClassVar[tuple[str, ...]] = (
        "MAPPING_VALUE", "FIRST_NAME", "MIDDLE_NAME", "LAST_NAME", "SUFFIX",
        "RESIDENTIAL_ADDRESS", "HOUSE_NUM", "STREET_NAME", "MAILING_ADDRESS",
        "EFFECTIVE_REGN_DATE",
    )  # fmt: skip
    aliases: ClassVar[Mapping[str, str]] = {
        "RESIDENCE_CITY": "RES_CITY", "RESIDENCE_STATE": "RES_STATE",
        "RESIDENTIAL_ZIP_CODE": "RES_ZIP_CODE", "RESIDENTIAL_COUNTY": "RES_COUNTY",
        "MAILING_CITY": "MAIL_CITY", "MAILING_STATE": "MAIL_STATE",
        "MAILING_ZIP_CODE": "MAIL_ZIP_CODE", "EFFECTIVE_VOTER_REGISTRATION_DATE":
        "EFFECTIVE_REGN_DATE", "VOTER_STATUS": "STATUS",
    }  # fmt: skip
    fips: ClassVar[Mapping[str, str]] = fips_table("28", MS_COUNTIES)
    id_column: ClassVar[str] = "MAPPING_VALUE"
    county_column: ClassVar[str] = "RES_COUNTY"
    name_columns: ClassVar[tuple[str, str, str, str]] = (
        "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "SUFFIX")  # fmt: skip
    res_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("RESIDENTIAL_ADDRESS",), "RES_CITY", "RES_STATE", "RES_ZIP_CODE")  # fmt: skip
    mail_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("MAILING_ADDRESS",), "MAIL_CITY", "MAIL_STATE", "MAIL_ZIP_CODE")  # fmt: skip
    terms_summary: ClassVar[str] = (
        "Mississippi SoS statewide voter file: free weekly ShareFile link to program "
        "sign-ups, or by Public Records Act request at no more than actual cost. § "
        "23-15-165(6): copies 'shall be provided to any person', excluding SSN, phone, e-mail, "
        "DOB and age; no use restriction in statute or program terms (research 2026-11-25)."
    )


class AlaskaVoterFile(DeliveredVoterFile):
    """Alaska Division of Elections statewide voter list: 'any person' by applying to the
    director and paying the fee the director sets (AS 15.07.127); 'Voter lists are available
    for purchase. To purchase a list ... contact any divisional office'
    (https://www.elections.alaska.gov/research/). No online form or layout. Delivered as CSV
    with a header; columns as documented by the Voteshield 'reggie' Alaska config
    (https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/alaska.yaml): UN,
    PARTY, house district, PRECINCT, LAST_NAME, FIRST_NAME, MIDDLE_NAME, SUFFIX_NAME,
    ASCENSION (the list's record number), REG_DATE, ORG_REG_DATE, RESIDENCE_ADDRESS/CITY/ZIP,
    MAILING_ADDRESS1-3, MAILING_CITY/STATE/ZIP/COUNTRY, GENDER, STATUS, then history.
    Age/DOB, SSN, DL number, voter ID number, birthplace and signature are confidential (AS
    15.07.195(a)); a voter may keep the residence address private (195(b)). The list has no
    borough column, so the file is one statewide partition. Gender, districts and history are
    never kept."""

    source_id: ClassVar[str] = "ak.doe.voter_file"
    state: ClassVar[str] = "AK"
    state_fips: ClassVar[str] = "02"
    request_url: ClassVar[str] = "https://www.elections.alaska.gov/research/"
    layout_url: ClassVar[str] = (
        "https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/alaska.yaml"
    )
    keep: ClassVar[tuple[str, ...]] = (
        "ASCENSION", "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "SUFFIX_NAME", "PARTY", "STATUS",
        "REG_DATE", "ORG_REG_DATE", "RESIDENCE_ADDRESS", "RESIDENCE_CITY", "RESIDENCE_ZIP",
        "MAILING_ADDRESS1", "MAILING_ADDRESS2", "MAILING_ADDRESS3", "MAILING_CITY",
        "MAILING_STATE", "MAILING_ZIP", "MAILING_COUNTRY",
    )  # fmt: skip
    pii_fields: ClassVar[tuple[str, ...]] = (
        "ASCENSION", "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "SUFFIX_NAME", "REG_DATE",
        "ORG_REG_DATE", "RESIDENCE_ADDRESS", "MAILING_ADDRESS1", "MAILING_ADDRESS2",
        "MAILING_ADDRESS3",
    )  # fmt: skip
    optional: ClassVar[tuple[str, ...]] = ("ORG_REG_DATE", "MAILING_COUNTRY")
    id_column: ClassVar[str] = "ASCENSION"
    name_columns: ClassVar[tuple[str, str, str, str]] = (
        "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME", "SUFFIX_NAME")  # fmt: skip
    res_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("RESIDENCE_ADDRESS",), "RESIDENCE_CITY", "", "RESIDENCE_ZIP")  # fmt: skip
    mail_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        ("MAILING_ADDRESS1", "MAILING_ADDRESS2", "MAILING_ADDRESS3"), "MAILING_CITY",
        "MAILING_STATE", "MAILING_ZIP")  # fmt: skip
    cost_model: ClassVar[str] = "fee"
    terms_summary: ClassVar[str] = (
        "Alaska Division of Elections voter list: 'any person may obtain a copy of the list' "
        "by applying to the director and paying a fee the director sets (AS 15.07.127; EAC "
        "lists about $20, unverified). AS 15.07.195 makes age/DOB, SSN, DL, voter ID number, "
        "birthplace and signature confidential and has no use restriction (research "
        "2026-11-25)."
    )

    def residence(self, r: Mapping[str, Any]) -> dict[str, Any] | None:
        street = _text(r.get("RESIDENCE_ADDRESS"))
        city = _text(r.get("RESIDENCE_CITY"))
        if not (street or city):
            return None
        return normalized_address(street, city, "AK", _zip5(r.get("RESIDENCE_ZIP")))


DC_STREET = ("RES_HOUSE", "RES_FRAC", "RES_STREET", "RES_APT")


class DistrictOfColumbiaVoterFile(DeliveredVoterFile):
    """DC Board of Elections voter registration list: free, requested on the Data Request
    Form (rev. 8/17/26, online at https://vr.dcboe.org/230363516728053 or e-mailed to
    voterservices@dcboe.org); 'the entire voter registration list can only be obtained
    through a secure link', as a Microsoft Excel workbook, with or without history, within
    the D.C. FOIA's 15 business days. DCBOE publishes no layout; the workbook's header row,
    as documented by the Voteshield 'reggie' DC config
    (https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/dc.yaml), is
    REGISTERED, LASTNAME, FIRSTNAME, MIDDLE, SUFFIX, STATUS, PARTY, RES_HOUSE, RES_FRAC,
    RES_APT, RES STREET, RES_CITY, RES_STATE, RES_ZIP, RES_ZIP4, PRECINCT, WARD, ANC, SMD,
    then one column per election (history, never kept). The export carries no voter ID (its
    README lists one); a VOTER_ID column is used when present, else the record key is a hash
    of name, registration date and residence. No mailing address. One partition (11001)."""

    source_id: ClassVar[str] = "dc.boe.voter_file"
    state: ClassVar[str] = "DC"
    state_fips: ClassVar[str] = "11"
    include: ClassVar[re.Pattern[str]] = re.compile(r"\.(xlsx|csv|txt)$", re.I)
    request_url: ClassVar[str] = "https://vr.dcboe.org/230363516728053"
    layout_url: ClassVar[str] = (
        "https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/dc.yaml"
    )
    keep: ClassVar[tuple[str, ...]] = (
        "VOTER_ID", "REGISTERED", "LASTNAME", "FIRSTNAME", "MIDDLE", "SUFFIX", "STATUS",
        "PARTY", *DC_STREET, "RES_CITY", "RES_STATE", "RES_ZIP", "RES_ZIP4", "WARD",
    )  # fmt: skip
    pii_fields: ClassVar[tuple[str, ...]] = (
        "VOTER_ID", "REGISTERED", "LASTNAME", "FIRSTNAME", "MIDDLE", "SUFFIX", *DC_STREET,
    )  # fmt: skip
    optional: ClassVar[tuple[str, ...]] = ("VOTER_ID",)
    id_column: ClassVar[str] = "VOTER_ID"
    name_columns: ClassVar[tuple[str, str, str, str]] = (
        "LASTNAME", "FIRSTNAME", "MIDDLE", "SUFFIX")  # fmt: skip
    res_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = (
        DC_STREET, "RES_CITY", "RES_STATE", "RES_ZIP")  # fmt: skip
    mail_columns: ClassVar[tuple[tuple[str, ...], str, str, str]] = ((), "", "", "")
    terms_summary: ClassVar[str] = (
        "DC Board of Elections voter registration list: anyone, Data Request Form (rev. "
        "8/17/26) with no purpose field or use terms; free, Excel by secure link, up to 15 "
        "business days (D.C. Code § 2-532(c)). D.C. Code §§ 1-1001.05, 1-1001.07: no use "
        "restriction (research 2026-11-25)."
    )

    def whole_key(self) -> str:
        return "11001"

    def jurisdiction(self, r: Mapping[str, Any]) -> str:
        return "11001"

    def record_key(self, r: Mapping[str, Any]) -> str | None:
        vid = _text(r.get("VOTER_ID"))
        if vid:
            return vid
        cols = ("LASTNAME", "FIRSTNAME", "MIDDLE", "SUFFIX", "REGISTERED", *DC_STREET)
        parts = [clean(_text(r.get(c)) or "") for c in cols]
        if not parts[0]:
            return None
        return "h-" + stable_id(self.source_id, *parts)[:20]
