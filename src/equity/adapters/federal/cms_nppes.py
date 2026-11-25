"""CMS NPPES: the National Plan and Provider Enumeration System NPI registry, the monthly full
replacement file (NPPES Data Dissemination V.2).

Every health care provider with a National Provider Identifier: individuals (entity type 1:
physicians, nurses, therapists...) and organizations (entity type 2: practices, hospitals,
pharmacies, labs, suppliers). One zip a month (~1.1 GB; npidata_pfile_<from>-<to>.csv inside
is ~12 GB and ~9M rows of 330 columns), linked from the NPI files page; weekly incremental and
monthly deactivation files are linked there too and not read here.

Kept from each row (the KEEP columns; telephone and fax numbers, the EIN column, the parent
organization TIN and the sex code are not kept): NPI, entity type, replacement NPI, the
provider's name (organization legal business name, or last / first / middle / prefix /
suffix / credential), the other name (former or professional name; an organization's other
name), business mailing and practice location addresses, enumeration / last update /
certification dates, deactivation reason and date, reactivation date, the authorized
official of an organization (name, title, credential), sole-proprietor and subpart flags,
the parent organization's legal name, and every taxonomy with its license number and state
(a list, `taxonomies`).

What is emitted, from existing tables only:

- source_record: one per NPI (record_type npi_individual | npi_organization); license
  numbers, taxonomies and dates stay in the hashed raw record.
- business (entity type 2): sos_id NPI:<npi>, the legal business name, status active or
  deactivated (status_date = the deactivation or reactivation date), principal address = the
  practice location, mailing address = the business mailing address, valid from the
  enumeration date (else the file's date).
- business_role + party: the authorized official (role 'officer', title as printed, else
  AUTHORIZED OFFICIAL; a person with name parts) and the parent organization of a subpart
  (role 'other', title PARENT ORGANIZATION).
- party (entity type 1): the provider as a person with name parts at the practice location
  (the mailing address when the practice address is missing or foreign), and the provider's
  other name (a former or professional name) as a second person party at the same address.
- address: the U.S. practice location and mailing addresses (foreign ones stay raw).

Rows with no name (deactivated NPIs: the file blanks every field but the NPI and the dates)
are skipped.

Partitions: the practice location state (us_states(), else 'other') x shard 0-9 (the NPI's
ninth digit, uniform: the tenth is a check digit), so a California shard holds ~100k rows,
not a million. The zip is streamed, never held in memory: a build downloads it once to
data/work/us.cms.nppes/ (or reads path= or data/manual/us.cms.nppes/<file>), splits the CSV
member once into one gzipped JSON-lines file of kept columns per state, and each partition
reads its state's file keeping its shard. With `limit` (fixtures) and no local zip, the
member is read over HTTP Range requests through the zip's central directory, only as far as
the first `limit` rows of the state: a fixture costs a few megabytes, not the 1 GB file.

Source: https://download.cms.gov/nppes/NPI_Files.html (CMS; NPPES data are disclosable under
FOIA and published by CMS for free download, no login; U.S. government data).
download.cms.gov serves no robots.txt (404 on 2026-11-25: no restrictions).
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
import time
import urllib.parse
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import IO, Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import (
    BulkClient,
    Holder,
    address,
    emit_business,
    jurisdiction,
    remote_zip,
    scrub_json,
    text,
)
from equity.adapters.federal.bulk_zip import MANUAL_DIR, WORK_DIR, file_time, is_zip
from equity.adapters.federal.fcc_uls import OTHER, state_partition, us_states
from equity.adapters.rows import RecordContext, canonical_json
from equity.matching.orgs import clean
from equity.schema.ids import stable_id

PAGE = "https://download.cms.gov/nppes/NPI_Files.html"
CHECKED_ON = "2026-11-25"
MONTHLY = re.compile(r"NPPES_Data_Dissemination_([A-Za-z]+)_(\d{4})(?:_V2)?\.zip$", re.I)
MEMBER = re.compile(r"(?:^|/)npidata_pfile_[0-9-]+\.csv$", re.I)  # not the _fileheader file
SHARDS = 10
DONE = "_complete"

# NPPES header -> kept key. Name and street keys are the pii_fields.
KEEP = {
    "NPI": "npi", "Entity Type Code": "entity_type", "Replacement NPI": "replacement_npi",
    "Provider Organization Name (Legal Business Name)": "org_name",
    "Provider Last Name (Legal Name)": "last_name", "Provider First Name": "first_name",
    "Provider Middle Name": "middle_name", "Provider Name Prefix Text": "name_prefix",
    "Provider Name Suffix Text": "name_suffix", "Provider Credential Text": "credential",
    "Provider Other Organization Name": "other_org_name",
    "Provider Other Organization Name Type Code": "other_org_name_type",
    "Provider Other Last Name": "other_last_name", "Provider Other First Name": "other_first_name",
    "Provider Other Middle Name": "other_middle_name",
    "Provider Other Name Suffix Text": "other_name_suffix",
    "Provider Other Last Name Type Code": "other_last_name_type",
    "Provider First Line Business Mailing Address": "mail_line1",
    "Provider Second Line Business Mailing Address": "mail_line2",
    "Provider Business Mailing Address City Name": "mail_city",
    "Provider Business Mailing Address State Name": "mail_state",
    "Provider Business Mailing Address Postal Code": "mail_postal",
    "Provider Business Mailing Address Country Code (If outside U.S.)": "mail_country",
    "Provider First Line Business Practice Location Address": "practice_line1",
    "Provider Second Line Business Practice Location Address": "practice_line2",
    "Provider Business Practice Location Address City Name": "practice_city",
    "Provider Business Practice Location Address State Name": "practice_state",
    "Provider Business Practice Location Address Postal Code": "practice_postal",
    "Provider Business Practice Location Address Country Code (If outside U.S.)":
        "practice_country",
    "Provider Enumeration Date": "enumeration_date", "Last Update Date": "last_update_date",
    "NPI Deactivation Reason Code": "deactivation_reason",
    "NPI Deactivation Date": "deactivation_date", "NPI Reactivation Date": "reactivation_date",
    "Authorized Official Last Name": "ao_last_name",
    "Authorized Official First Name": "ao_first_name",
    "Authorized Official Middle Name": "ao_middle_name",
    "Authorized Official Title or Position": "ao_title",
    "Authorized Official Name Prefix Text": "ao_prefix",
    "Authorized Official Name Suffix Text": "ao_suffix",
    "Authorized Official Credential Text": "ao_credential",
    "Is Sole Proprietor": "sole_proprietor", "Is Organization Subpart": "org_subpart",
    "Parent Organization LBN": "parent_org_name", "Certification Date": "certification_date",
}  # fmt: skip
_TAXONOMY = re.compile(
    r"^(Healthcare Provider Taxonomy Code|Provider License Number|Provider License Number State"
    r" Code|Healthcare Provider Primary Taxonomy Switch)_(\d+)$"
)
_TAX_KEY = {"Healthcare Provider Taxonomy Code": "code", "Provider License Number": "license",
            "Provider License Number State Code": "license_state",
            "Healthcare Provider Primary Taxonomy Switch": "primary"}  # fmt: skip
NAMES = ("last_name", "first_name", "middle_name", "other_last_name", "other_first_name",
         "other_middle_name", "ao_last_name", "ao_first_name", "ao_middle_name")  # fmt: skip
STREETS = ("mail_line1", "mail_line2", "practice_line1", "practice_line2")
_MDY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def pseudo_digits(field: str, value: Any, n: int) -> str:
    """A fixture stand-in for an identifier: `n` digits from a hash, starting with 0 (no NPI,
    USDOT number or payment record id starts with 0, so it never names a real one)."""
    return "0" + str(int(stable_id("scrub", field, str(value))[:15], 16))[-(n - 1) :].zfill(n - 1)


def parse_day(value: Any) -> date | None:
    """NPPES dates are MM/DD/YYYY."""
    m = _MDY.match(text(value) or "")
    if m is None:
        return None
    try:
        return date(int(m[3]), int(m[1]), int(m[2]))
    except ValueError:
        return None


def keep_row(header: list[str], cells: list[str]) -> dict[str, Any]:
    """The KEEP columns of one CSV row (non-empty values only) plus its taxonomies."""
    out: dict[str, Any] = {}
    tax: dict[int, dict[str, str]] = {}
    for h, c in zip(header, cells, strict=False):
        v = c.strip()
        if not v:
            continue
        if (k := KEEP.get(h)) is not None:
            out[k] = v
        elif m := _TAXONOMY.match(h):
            tax.setdefault(int(m[2]), {})[_TAX_KEY[m[1]]] = v
    if tax:
        out["taxonomies"] = [tax[i] for i in sorted(tax)]
    return out


def rows_of(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """Kept rows of an npidata CSV, streamed (header row first)."""
    reader = csv.reader(lines)
    header = [h.strip() for h in next(reader, [])]
    for cells in reader:
        if cells:
            yield keep_row(header, cells)


def is_us(country: Any) -> bool:
    return (text(country) or "US").upper() == "US"


def practice_state(row: Mapping[str, Any]) -> str:
    """The partition of a row: its practice location state, 'other' if foreign or blank."""
    if not is_us(row.get("practice_country")):
        return OTHER
    return state_partition(row.get("practice_state"))


def shard(npi: Any) -> int:
    """0-9: the NPI's ninth digit (the tenth is a Luhn check digit)."""
    s = text(npi) or ""
    return int(s[8]) if len(s) == 10 and s.isdigit() else 0


def _street(row: Mapping[str, Any], prefix: str) -> str | None:
    return " ".join(s for k in ("line1", "line2") if (s := text(row.get(f"{prefix}_{k}"))))


def us_address(row: Mapping[str, Any], prefix: str) -> dict[str, Any] | None:
    """The practice or mailing address of a row, if in the U.S."""
    if not is_us(row.get(f"{prefix}_country")):
        return None
    return address(_street(row, prefix) or None, row.get(f"{prefix}_city"),
                   row.get(f"{prefix}_state"), row.get(f"{prefix}_postal"))  # fmt: skip


def person_name(row: Mapping[str, Any], prefix: str) -> tuple[str, dict[str, str | None]] | None:
    """(raw name, parts) of the provider ('') / other name ('other_') / official ('ao_')."""
    last = text(row.get(f"{prefix}last_name"))
    if last is None:
        return None
    first = text(row.get(f"{prefix}first_name"))
    middle = text(row.get(f"{prefix}middle_name"))
    suffix = text(row.get({"": "name_suffix", "other_": "other_name_suffix",
                           "ao_": "ao_suffix"}[prefix]))  # fmt: skip
    raw = " ".join(p for p in (first, middle, last, suffix) if p)
    return raw, {"first_name": first, "middle": middle, "last_name": last, "suffix": suffix}


def status_of(row: Mapping[str, Any]) -> tuple[str, date | None]:
    off, back = parse_day(row.get("deactivation_date")), parse_day(row.get("reactivation_date"))
    if off is not None and (back is None or back < off):
        return "deactivated", off
    return "active", back


class CMSNPPES(Adapter):
    source_id: ClassVar[str] = "us.cms.nppes"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = (*NAMES, *STREETS)
    max_age_s: ClassVar[float] = 20 * 24 * 3600.0  # a monthly file; one build, one download

    def __init__(self, client: BulkClient | None = None,
                 clock: Callable[[], float] = time.time) -> None:  # fmt: skip
        self.client = client or BulkClient(min_interval_s=2.0, timeout_s=3600.0)
        self.clock = clock

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a registry of providers and organizations
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": PAGE,
            "terms_url": PAGE,
            "terms_summary": (
                "CMS NPPES Data Dissemination: the monthly full replacement NPI file (zip, "
                "CSV), free, no login; NPPES data are FOIA-disclosable U.S. government data "
                "published by CMS. download.cms.gov has no robots.txt (404). Telephone and "
                "fax numbers are not kept."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def monthly_url(self) -> str:
        """The monthly full file linked from the NPI files page."""
        resp = self.client.get(PAGE)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {PAGE}")
        page = resp.content.decode("utf-8", errors="replace")
        for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", page):
            if MONTHLY.search(href):
                return str(urllib.parse.urljoin(PAGE, str(href)))
        raise RuntimeError(f"no monthly NPPES file linked on {PAGE}")

    def partitions(self) -> Iterator[dict[str, str]]:
        for st in (*us_states(), OTHER):
            for i in range(SHARDS):
                yield {"state": st, "shard": str(i)}

    # -- fetch ----------------------------------------------------------------------------
    def fetch(self, request: FetchRequest) -> Fetched:
        """params: state (a partition); shard (0-9, default every shard); limit (fixtures:
        the first `limit` rows); url (the monthly zip, default the one linked on the page);
        path (a hand-saved zip)."""
        p = request.params
        state = p.get("state", "")
        if state != OTHER and state not in us_states():
            raise ValueError(f"unknown state partition {state!r}")
        part = int(p["shard"]) if p.get("shard") else None
        if part is not None and not 0 <= part < SHARDS:
            raise ValueError(f"shard must be 0-{SHARDS - 1}")
        limit = int(p["limit"]) if "limit" in p else None
        if p.get("url"):
            url = p["url"]
        elif p.get("path"):  # provenance: the file's name where CMS publishes it
            url = str(urllib.parse.urljoin(PAGE, Path(p["path"]).name))
        else:
            url = self.monthly_url()
        local = self._local_zip(url, p)
        status: int | None = None
        if local is None and limit is not None:  # a sample: Range requests, no download
            with remote_zip(self.client, url) as zf:
                member = _member(zf)
                rows = self._select(_lines(zf, member), state, part, limit)
            at, status = self.client.now(), 206
        else:
            if local is None:
                local, status = self._download(url), 200
            at = file_time(local)
            with zipfile.ZipFile(local) as zf:
                member = _member(zf)
            if limit is not None:
                with zipfile.ZipFile(local) as zf:
                    rows = self._select(_lines(zf, member), state, part, limit)
            else:
                rows = [r for r in self._split_rows(local, member, state)
                        if part is None or shard(r.get("npi")) == part]  # fmt: skip
        body = {"file": url.rsplit("/", 1)[-1], "member": member, "url": url, "state": state,
                "shard": part, "rows": rows}  # fmt: skip
        frag = f"state={state}" + ("" if part is None else f"&shard={part}")
        return Fetched(self.source_id, f"{url}#{frag}", at, status, canonical_json(body),
                       "application/json")  # fmt: skip

    @staticmethod
    def _select(lines: Iterable[str], state: str, part: int | None, limit: int
                ) -> list[dict[str, Any]]:  # fmt: skip
        out: list[dict[str, Any]] = []
        for row in rows_of(lines):
            if practice_state(row) != state or (part is not None and shard(row.get("npi")) != part):
                continue
            out.append(row)
            if len(out) >= limit:
                break
        return out

    def _local_zip(self, url: str, p: Mapping[str, str]) -> Path | None:
        if p.get("path"):
            path = Path(p["path"])
            if not is_zip(path):
                raise RuntimeError(f"{path}: not a zip file")
            return path
        name = url.rsplit("/", 1)[-1]
        manual = MANUAL_DIR / self.source_id / name
        if is_zip(manual):
            return manual
        cached = WORK_DIR / self.source_id / name
        if is_zip(cached) and self.clock() - cached.stat().st_mtime < self.max_age_s:
            return cached
        return None

    def _download(self, url: str) -> Path:
        dest = WORK_DIR / self.source_id / url.rsplit("/", 1)[-1]
        resp = self.client.download(url, dest)
        if resp.status != 200 or not is_zip(dest):
            raise RuntimeError(f"{url}: HTTP {resp.status} ({resp.content_type}); not the zip. "
                               f"Save it by hand to {MANUAL_DIR / self.source_id} (or pass "
                               "path=<file>) and run again.")  # fmt: skip
        return dest

    @staticmethod
    def split_dir(zip_path: Path) -> Path:
        return WORK_DIR / "us.cms.nppes" / "split" / zip_path.stem

    def _split_rows(self, zip_path: Path, member: str, state: str) -> Iterator[dict[str, Any]]:
        """The kept rows of one practice state, from the per-state split of the zip (made by
        one streaming pass over the member the first time a partition asks)."""
        out = self.split_dir(zip_path)
        if not (out / DONE).exists() or (out / DONE).read_text() != member:
            split(zip_path, member, out)
        path = out / f"{state}.jsonl.gz"
        if not path.exists():
            return
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                yield json.loads(line)

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        """Names and streets pseudonymized; an individual's NPI and license numbers too (a
        public lookup would undo the name pseudonym). Organization NPIs are kept."""
        data = json.loads(scrub_json(content, NAMES, STREETS))
        for r in data.get("rows") or []:
            if str(r.get("entity_type") or "") == "2":
                continue
            for k in ("npi", "replacement_npi"):
                if r.get(k):
                    r[k] = pseudo_digits(k, r[k], 10)
            for t in r.get("taxonomies") or []:
                if t.get("license"):
                    t["license"] = "TEST" + pseudo_digits("license", t["license"], 6)
        return canonical_json(data)

    # -- normalize ------------------------------------------------------------------------
    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for r in sorted(data.get("rows") or [], key=canonical_json):
            npi = text(r.get("npi")) or ""
            if len(npi) != 10 or not npi.isdigit() or npi in seen:
                continue
            org = str(r.get("entity_type") or "").strip() == "2"
            name = text(r.get("org_name")) if org else None
            person = None if org else person_name(r, "")
            if name is None and person is None:  # deactivated: the name is blanked
                continue
            seen.add(npi)
            juris = jurisdiction(text(r.get("practice_state")) if is_us(r.get("practice_country"))
                                 else None)  # fmt: skip
            ctx = RecordContext(fetched, juris, npi,
                                "npi_organization" if org else "npi_individual", r)  # fmt: skip
            yield ctx.source_record()
            practice, mailing = us_address(r, "practice"), us_address(r, "mail")
            enumerated = parse_day(r.get("enumeration_date"))
            valid_from = (
                enumerated if enumerated is not None and enumerated <= observed else observed
            )
            if org and name is not None:
                yield from self._organization(ctx, r, name, practice, mailing, valid_from,
                                              observed)  # fmt: skip
            elif person is not None:
                yield from self._individual(ctx, r, person, practice or mailing)

    def _organization(
        self,
        ctx: RecordContext,
        r: Mapping[str, Any],
        name: str,
        practice: dict[str, Any] | None,
        mailing: dict[str, Any] | None,
        valid_from: date,
        observed: date,
    ) -> Iterator[NormalizedRow]:
        holders: list[Holder] = []
        if official := person_name(r, "ao_"):
            title = text(r.get("ao_title")) or "AUTHORIZED OFFICIAL"
            holders.append(Holder("officer", title, official[0], person=True,
                                  parts=official[1]))  # fmt: skip
        if (parent := text(r.get("parent_org_name"))) and clean(parent) != clean(name):
            holders.append(Holder("other", "PARENT ORGANIZATION", parent))
        status, status_date = status_of(r)
        if status_date is not None and status_date > observed:
            status_date = None
        yield from emit_business(
            ctx, source_id=self.source_id, sos_id=f"NPI:{ctx.record_key}", name=name,
            valid_from=valid_from, status=status, status_date=status_date, principal=practice,
            mailing=mailing, holders=holders,
        )  # fmt: skip

    def _individual(
        self,
        ctx: RecordContext,
        r: Mapping[str, Any],
        person: tuple[str, dict[str, str | None]],
        addr: dict[str, Any] | None,
    ) -> Iterator[NormalizedRow]:
        if addr is not None:
            yield NormalizedRow("address", addr)
        names = [("provider", person)]
        if (other := person_name(r, "other_")) and clean(other[0]) != clean(person[0]):
            names.append(("other_name", other))
        for role, (raw, parts) in names:
            yield ctx.fact(
                "party", party_id=stable_id(self.source_id, ctx.record_key, role, clean(raw)),
                raw_name=raw, party_kind="person", org_form=None, org_name_norm=None,
                address_id=None if addr is None else addr["address_id"], **parts,
            )  # fmt: skip

    def health(self) -> HealthReport:
        """The NPI files page answers and links a monthly file whose zip lists the member."""
        now = datetime.now(UTC)
        try:
            url = self.monthly_url()
            with remote_zip(self.client, url) as zf:
                member = _member(zf)
                header_name = member[:-4] + "_fileheader.csv"
                names = {i.filename for i in zf.infolist()}
                shape: tuple[str, ...] = ()
                if header_name in names:
                    with zf.open(header_name) as raw:
                        line = io.TextIOWrapper(raw, encoding="utf-8-sig").readline()
                    shape = tuple(sorted(h.strip() for h in next(csv.reader([line]))))
        except (OSError, RuntimeError, KeyError, zipfile.BadZipFile) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        ok = set(KEEP) <= set(shape)
        return HealthReport(self.source_id, ok, now, f"{url.rsplit('/', 1)[-1]} {member}",
                            shape)  # fmt: skip


def _member(zf: zipfile.ZipFile) -> str:
    for info in zf.infolist():
        if MEMBER.search(info.filename):
            return info.filename
    raise KeyError("no npidata_pfile CSV in the NPPES zip")


def _lines(zf: zipfile.ZipFile, member: str) -> Iterator[str]:
    with zf.open(member) as raw:
        yield from io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")


def split(zip_path: Path, member: str, out: Path) -> None:
    """Stream the member once into one gzipped JSON-lines file of kept rows per practice
    state (<state>.jsonl.gz), then write the DONE marker naming the member."""
    out.mkdir(parents=True, exist_ok=True)
    (out / DONE).unlink(missing_ok=True)
    files: dict[str, IO[str]] = {}
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for row in rows_of(_lines(zf, member)):
                st = practice_state(row)
                f = files.get(st)
                if f is None:
                    f = files[st] = gzip.open(out / f"{st}.jsonl.gz.part", "wt",  # noqa: SIM115
                                              encoding="utf-8", compresslevel=3)  # fmt: skip
                f.write(canonical_json(row).decode() + "\n")
    finally:
        for f in files.values():
            f.close()
    for st in files:
        (out / f"{st}.jsonl.gz.part").replace(out / f"{st}.jsonl.gz")
    (out / DONE).write_text(member)
