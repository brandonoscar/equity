"""Statewide voter registration files: Ohio (Secretary of State) and North Carolina (State
Board of Elections). One adapter class per state; one partition per county file, so the lake
builds county by county. Both states publish the file free with no use restriction in state law
(research_notes/Voter file access by state/midwest.md, southeast.md); Brandon approved them.

What is emitted, from existing tables only:

- source_record: one per registration. Its raw (hashed) record is the registration columns
  this module keeps: voter ids, name, residential and mailing address, status, party,
  registration date and date of birth (Ohio) or birth year (NC). Voting history, phone, race,
  gender and district columns are never kept.
- party: the voter, party_kind 'person', raw_name "LAST FIRST MIDDLE SUFFIX" (the order
  assessor rolls use), with the name parts, and address_id = the residential address.
- address: the residential address, and the mailing address as its own row when it
  normalizes to a different address.

Records a state marks confidential (NC confidential_ind = Y) are skipped entirely, and a name
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
import json
import re
import urllib.parse
import zipfile
from collections.abc import Iterator, Mapping
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


def iter_rows(content: bytes, delimiter: str) -> Iterator[Mapping[str, Any]]:
    """Rows of either fetched shape: a JSON sample ({"rows": [...]}) or the raw file."""
    if content[:1] == b"{":
        yield from json.loads(content)["rows"]
    else:
        yield from iter_raw_rows(content, delimiter)


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
            rows: list[dict[str, str]] = []
            for r in iter_raw_rows(content, self.delimiter):
                if len(rows) >= int(p["limit"]):
                    break
                rows.append({k: r[k] for k in self.keep if k in r})
            content = canonical_json({"url": url, "rows": rows})
            ctype = "application/json"
        return Fetched(self.source_id, url, at, status, content, ctype)

    # -- normalize ------------------------------------------------------------------------
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
        for row in iter_rows(fetched.content, self.delimiter):
            r = {k: row[k] for k in self.keep if k in row}
            key = self.record_key(r)
            if key is None or key in seen or self.skip(r):
                continue
            seen.add(key)
            try:
                n = county_number(str(r.get(self.county_column) or ""), self.counties)
                jurisdiction = county_fips(self.state_fips, n)
            except ValueError:
                jurisdiction = self.state_fips
            ctx = RecordContext(fetched, jurisdiction, key, "voter_registration", r)
            yield ctx.source_record()
            res = self._address(r, self.res_columns)
            mail = self._address(r, self.mail_columns)
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
