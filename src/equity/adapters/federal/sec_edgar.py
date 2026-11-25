"""SEC EDGAR structured data sets naming companies and the people tied to them.

Two sources, one partition per calendar quarter (e.g. quarter=2026q3), each a zip of
tab-separated files linked from its data set page:

- us.sec.form_d: Form D notices of exempt (private) offerings. The issuer (CIK, name, street
  address, entity type, jurisdiction and year of incorporation) and its related persons
  (executive officers, directors, promoters) with their addresses. Data set page:
  https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets
- us.sec.insiders: Forms 3, 4 and 5 (insider ownership). The issuer (CIK, name, ticker) and
  each reporting owner (CIK, name, relationship, officer title, address). Data set page:
  https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets

What is emitted, from existing tables only (one source record per filing, the accession
number):

- business: the issuer, sos_id "CIK:<10 digits>" (both sources share the key), valid from the
  filing date (Form D) or the period of report (Forms 3/4/5). Form D gives the issuer's
  address; the insider data sets give none.
- business_role + party per related person / reporting owner: 'officer' (executive officer,
  officer), 'director', else 'other' (promoter, ten percent owner, other); the title is the
  officer title or the filer's clarification. Form D names come in parts (first, middle,
  last); insider names are as EDGAR prints them ("LAST FIRST MIDDLE"). Offering amounts and
  the submission fields stay in the source record.
- address: issuer and person addresses (U.S. five-digit ZIPs; foreign ones keep no ZIP).

A quarter's zip (4-100 MB) is streamed to data/work/ and read member by member with the csv
module, then deleted. `limit` keeps the first `limit` live filings (fixtures).

Terms: SEC data is public (U.S. government, no copyright); EDGAR fair-access policy allows
automated access at under 10 requests per second with a User-Agent that identifies the client.
This client sends the project's generic User-Agent (no personal contact address); sec.gov
accepted it on 2026-11-25. robots.txt allows /files/ and the data set pages.
"""

from __future__ import annotations

import csv
import io
import json
import re
import tempfile
import urllib.parse
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Mapping
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
    scrub_json,
    text,
)
from equity.adapters.rows import RecordContext, canonical_json

CHECKED_ON = "2026-11-25"
SEC = "https://www.sec.gov"
FORM_D_PAGE = f"{SEC}/data-research/sec-markets-data/form-d-data-sets"
INSIDER_PAGE = f"{SEC}/data-research/sec-markets-data/insider-transactions-data-sets"

D_SUBMISSION = ("ACCESSIONNUMBER", "FILE_NUM", "FILING_DATE", "SIC_CODE", "SUBMISSIONTYPE",
                "TESTORLIVE")  # fmt: skip
D_ISSUER = ("ACCESSIONNUMBER", "IS_PRIMARYISSUER_FLAG", "ISSUER_SEQ_KEY", "CIK", "ENTITYNAME",
            "STREET1", "STREET2", "CITY", "STATEORCOUNTRY", "STATEORCOUNTRYDESCRIPTION",
            "ZIPCODE", "JURISDICTIONOFINC", "ISSUER_PREVIOUSNAME_1", "ISSUER_PREVIOUSNAME_2",
            "ISSUER_PREVIOUSNAME_3", "EDGAR_PREVIOUSNAME_1", "EDGAR_PREVIOUSNAME_2",
            "EDGAR_PREVIOUSNAME_3", "ENTITYTYPE", "ENTITYTYPEOTHERDESC",
            "YEAROFINC_TIMESPAN_CHOICE", "YEAROFINC_VALUE_ENTERED")  # fmt: skip
D_PERSON = ("ACCESSIONNUMBER", "RELATEDPERSON_SEQ_KEY", "FIRSTNAME", "MIDDLENAME", "LASTNAME",
            "STREET1", "STREET2", "CITY", "STATEORCOUNTRY", "STATEORCOUNTRYDESCRIPTION",
            "ZIPCODE", "RELATIONSHIP_1", "RELATIONSHIP_2", "RELATIONSHIP_3",
            "RELATIONSHIPCLARIFICATION")  # fmt: skip
D_OFFERING = ("ACCESSIONNUMBER", "INDUSTRYGROUPTYPE", "INVESTMENTFUNDTYPE",
              "FEDERALEXEMPTIONS_ITEMS_LIST", "ISAMENDMENT", "PREVIOUSACCESSIONNUMBER",
              "SALE_DATE", "TOTALOFFERINGAMOUNT", "TOTALAMOUNTSOLD", "TOTALREMAINING",
              "TOTALNUMBERALREADYINVESTED")  # fmt: skip
I_SUBMISSION = ("ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT", "DATE_OF_ORIG_SUB",
                "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL")  # fmt: skip
I_OWNER = ("ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME", "RPTOWNER_RELATIONSHIP",
           "RPTOWNER_TITLE", "RPTOWNER_TXT", "RPTOWNER_STREET1", "RPTOWNER_STREET2",
           "RPTOWNER_CITY", "RPTOWNER_STATE", "RPTOWNER_ZIPCODE",
           "RPTOWNER_STATE_DESC")  # fmt: skip

D_ROLES = {"EXECUTIVE OFFICER": "officer", "DIRECTOR": "director", "PROMOTER": "other"}
I_ROLES = {"OFFICER": ("officer", None), "DIRECTOR": ("director", None),
           "TENPERCENTOWNER": ("other", "10% owner"), "OTHER": ("other", None)}  # fmt: skip


def sec_date(value: Any) -> date | None:
    """30-SEP-2026 or 2026-09-30."""
    s = text(value) or ""
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC).date()
        except ValueError:
            continue
    return None


def cik10(value: Any) -> str | None:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits.zfill(10) if digits and int(digits) > 0 else None


def tsv_rows(stream: IO[bytes], keep: tuple[str, ...]) -> Iterator[dict[str, str | None]]:
    """The `keep` columns of one SEC data set TSV, streamed."""
    text_io = io.TextIOWrapper(stream, encoding="utf-8-sig", errors="replace", newline="")
    for row in csv.DictReader(text_io, delimiter="\t", quoting=csv.QUOTE_NONE):
        yield {k: text(row.get(k)) for k in keep if k in row}


def _member(zf: zipfile.ZipFile, name: str) -> str:
    for info in zf.infolist():
        if Path(info.filename).name.upper() == name.upper():
            return info.filename
    raise KeyError(f"{name} not in {zf.filename}")


def form_d_filings(zf: zipfile.ZipFile, limit: int | None = None) -> list[dict[str, Any]]:
    """One dict per live Form D filing: submission, issuers, related persons, offering."""
    subs: dict[str, dict[str, Any]] = {}
    with zf.open(_member(zf, "FORMDSUBMISSION.tsv")) as f:
        for r in tsv_rows(f, D_SUBMISSION):
            acc = r.get("ACCESSIONNUMBER")
            if acc and (r.get("TESTORLIVE") or "LIVE").upper() == "LIVE":
                if limit is not None and len(subs) >= limit:
                    break
                subs[acc] = {"accession": acc, "submission": r, "issuers": [],
                             "related_persons": [], "offering": None}  # fmt: skip
    for member, keep, slot in (("ISSUERS.tsv", D_ISSUER, "issuers"),
                               ("RELATEDPERSONS.tsv", D_PERSON, "related_persons"),
                               ("OFFERING.tsv", D_OFFERING, "offering")):  # fmt: skip
        with zf.open(_member(zf, member)) as f:
            for r in tsv_rows(f, keep):
                sub = subs.get(r.get("ACCESSIONNUMBER") or "")
                if sub is None:
                    continue
                if slot == "offering":
                    sub["offering"] = r
                else:
                    sub[slot].append(r)
    return list(subs.values())


def insider_filings(zf: zipfile.ZipFile, limit: int | None = None) -> list[dict[str, Any]]:
    """One dict per Form 3/4/5 filing: submission and reporting owners."""
    subs: dict[str, dict[str, Any]] = {}
    with zf.open(_member(zf, "SUBMISSION.tsv")) as f:
        for r in tsv_rows(f, I_SUBMISSION):
            acc = r.get("ACCESSION_NUMBER")
            if acc:
                if limit is not None and len(subs) >= limit:
                    break
                subs[acc] = {"accession": acc, "submission": r, "owners": []}
    owners: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with zf.open(_member(zf, "REPORTINGOWNER.tsv")) as f:
        for r in tsv_rows(f, I_OWNER):
            acc = r.get("ACCESSION_NUMBER") or ""
            if acc in subs:
                owners[acc].append(r)
    for acc, rows in owners.items():
        subs[acc]["owners"] = rows
    return list(subs.values())


def _street(r: Mapping[str, Any], a: str, b: str) -> str | None:
    return text(" ".join(p for p in (text(r.get(a)), text(r.get(b))) if p))


def _us_state(r: Mapping[str, Any], col: str) -> str | None:
    """A two-letter U.S. state code; foreign codes (F3, A1...) are not states."""
    st = text(r.get(col))
    return st if st and len(st) == 2 and st.isalpha() else None


def _us_zip(r: Mapping[str, Any], state_col: str, zip_col: str) -> str | None:
    """The ZIP of a U.S. address; a foreign postal code (or SEC's 00000 filler) is not one."""
    return text(r.get(zip_col)) if _us_state(r, state_col) else None


class _SECQuarterly(Adapter):
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    page: ClassVar[str]
    file_re: ClassVar[re.Pattern[str]]
    record_type: ClassVar[str]
    summary: ClassVar[str]
    cache_dir: ClassVar[Path]

    def __init__(self, client: BulkClient | None = None) -> None:
        # EDGAR fair access: at most 10 requests/second; one every 0.5 s is well under it.
        self.client = client or BulkClient(min_interval_s=0.5, timeout_s=1800.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a registry of companies and their insiders
            "jurisdiction": "US",
            "access_method": "bulk",
            "base_url": self.page,
            "terms_url": "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data",
            "terms_summary": self.summary,
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def quarter_urls(self) -> dict[str, str]:
        resp = self.client.get(self.page)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {self.page}")
        page = resp.content.decode("utf-8", errors="replace")
        out: dict[str, str] = {}
        for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", page):
            m = self.file_re.search(href)
            if m:
                out[m.group(1).lower()] = urllib.parse.urljoin(self.page, href)
        return dict(sorted(out.items()))

    def partitions(self) -> Iterator[dict[str, str]]:
        for q in self.quarter_urls():
            yield {"quarter": q}

    def read(self, zf: zipfile.ZipFile, limit: int | None) -> list[dict[str, Any]]:
        raise NotImplementedError

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: quarter (e.g. 2026q3); limit (fixtures: the first `limit` filings)."""
        p = request.params
        q = p["quarter"].lower()
        if not re.fullmatch(r"\d{4}q[1-4]", q):
            raise ValueError(f"bad quarter {q!r}")
        url = self.quarter_urls().get(q)
        if url is None:
            raise RuntimeError(f"{q}: no data set linked on {self.page}")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.cache_dir) as tmp:
            dest = Path(tmp) / Path(url).name
            resp = self.client.download(url, dest)
            if resp.status != 200 or not zipfile.is_zipfile(dest):
                raise RuntimeError(f"{url}: HTTP {resp.status} ({resp.content_type}); not a zip")
            with zipfile.ZipFile(dest) as zf:
                filings = self.read(zf, int(p["limit"]) if "limit" in p else None)
        body = {"quarter": q, "url": url, "filings": filings}
        return Fetched(self.source_id, url, resp.retrieved_at, 200, canonical_json(body),
                       "application/json")  # fmt: skip

    def health(self) -> HealthReport:
        try:
            found = self.quarter_urls()
        except (RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        latest = max(found) if found else None
        return HealthReport(self.source_id, bool(found), datetime.now(UTC),
                            f"{len(found)} quarters; latest {latest}")  # fmt: skip

    def filings(self, fetched: Fetched) -> Iterator[tuple[str, dict[str, Any]]]:
        data = json.loads(fetched.content)
        seen: set[str] = set()
        for f in sorted(data.get("filings") or [], key=canonical_json):
            acc = text(f.get("accession"))
            if acc and acc not in seen:
                seen.add(acc)
                yield acc, f


class SECFormD(_SECQuarterly):
    source_id: ClassVar[str] = "us.sec.form_d"
    page: ClassVar[str] = FORM_D_PAGE
    file_re: ClassVar[re.Pattern[str]] = re.compile(r"/(\d{4}q[1-4])_d\.zip$", re.I)
    record_type: ClassVar[str] = "form_d"
    # The clarification is free text that often names the person ("Mr. X is a manager...").
    pii_fields: ClassVar[tuple[str, ...]] = ("FIRSTNAME", "MIDDLENAME", "LASTNAME", "STREET1",
                                             "STREET2", "RELATIONSHIPCLARIFICATION")  # fmt: skip
    cache_dir: ClassVar[Path] = Path("data") / "work" / "us_sec_form_d"
    summary: ClassVar[str] = (
        "SEC Form D data sets (exempt offerings: issuers and related persons), quarterly zip "
        "of TSV files; U.S. government data, free, no login. EDGAR fair access: under 10 "
        "requests/s with an identifying User-Agent. robots.txt allows /files/."
    )

    def read(self, zf: zipfile.ZipFile, limit: int | None) -> list[dict[str, Any]]:
        return form_d_filings(zf, limit)

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        names = ("FIRSTNAME", "MIDDLENAME", "LASTNAME", "RELATIONSHIPCLARIFICATION")
        return scrub_json(content, names, ("STREET1", "STREET2"))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        observed = fetched.retrieved_at.astimezone(UTC).date()
        for acc, f in self.filings(fetched):
            issuers = sorted(f.get("issuers") or [], key=lambda r: (
                (r.get("IS_PRIMARYISSUER_FLAG") or "").upper() != "YES",
                int(r.get("ISSUER_SEQ_KEY") or 0) if str(r.get("ISSUER_SEQ_KEY") or "0").isdigit()
                else 0))  # fmt: skip
            primary = next((r for r in issuers if cik10(r.get("CIK"))
                            and text(r.get("ENTITYNAME"))), None)  # fmt: skip
            if primary is None:
                continue
            ctx = RecordContext(fetched, jurisdiction(_us_state(primary, "STATEORCOUNTRY")), acc,
                                self.record_type, f)  # fmt: skip
            yield ctx.source_record()
            filed = sec_date((f.get("submission") or {}).get("FILING_DATE"))
            valid_from = filed if filed is not None and filed <= observed else observed
            holders = []
            for r in f.get("related_persons") or []:
                parts = {"first_name": text(r.get("FIRSTNAME")),
                         "middle": text(r.get("MIDDLENAME")),
                         "last_name": text(r.get("LASTNAME")), "suffix": None}  # fmt: skip
                who = text(" ".join(v for v in (parts["first_name"], parts["middle"],
                                                parts["last_name"]) if v))  # fmt: skip
                if who is None:
                    continue
                addr = address(_street(r, "STREET1", "STREET2"), r.get("CITY"),
                               _us_state(r, "STATEORCOUNTRY"),
                               _us_zip(r, "STATEORCOUNTRY", "ZIPCODE"))  # fmt: skip
                clar = text(r.get("RELATIONSHIPCLARIFICATION"))
                rels = [text(r.get(f"RELATIONSHIP_{i}")) for i in (1, 2, 3)]
                for rel in dict.fromkeys(x for x in rels if x):
                    role = D_ROLES.get(rel.upper(), "other")
                    holders.append(Holder(role, clar or rel.lower(), who, addr,
                                          person=bool(parts["first_name"]),
                                          parts=parts if parts["first_name"] else {}))  # fmt: skip
            principal = address(_street(primary, "STREET1", "STREET2"), primary.get("CITY"),
                                _us_state(primary, "STATEORCOUNTRY"),
                                _us_zip(primary, "STATEORCOUNTRY", "ZIPCODE"))  # fmt: skip
            yield from emit_business(
                ctx, source_id=self.source_id, sos_id=f"CIK:{cik10(primary.get('CIK'))}",
                name=str(text(primary.get("ENTITYNAME"))), valid_from=valid_from,
                principal=principal, holders=holders,
            )  # fmt: skip


class SECInsiders(_SECQuarterly):
    source_id: ClassVar[str] = "us.sec.insiders"
    page: ClassVar[str] = INSIDER_PAGE
    file_re: ClassVar[re.Pattern[str]] = re.compile(r"/(\d{4}q[1-4])_form345\.zip$", re.I)
    record_type: ClassVar[str] = "form_345"
    pii_fields: ClassVar[tuple[str, ...]] = ("RPTOWNERNAME", "RPTOWNER_TXT", "RPTOWNER_STREET1",
                                             "RPTOWNER_STREET2")  # fmt: skip
    cache_dir: ClassVar[Path] = Path("data") / "work" / "us_sec_insiders"
    summary: ClassVar[str] = (
        "SEC Insider Transactions data sets (Forms 3, 4, 5: issuers and reporting owners), "
        "quarterly zip of TSV files; U.S. government data, free, no login. EDGAR fair "
        "access: under 10 requests/s with an identifying User-Agent. robots.txt allows /files/."
    )

    def read(self, zf: zipfile.ZipFile, limit: int | None) -> list[dict[str, Any]]:
        return insider_filings(zf, limit)

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, ("RPTOWNERNAME", "RPTOWNER_TXT"),
                          ("RPTOWNER_STREET1", "RPTOWNER_STREET2"))  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        observed = fetched.retrieved_at.astimezone(UTC).date()
        for acc, f in self.filings(fetched):
            sub = f.get("submission") or {}
            cik = cik10(sub.get("ISSUERCIK"))
            name = text(sub.get("ISSUERNAME"))
            if cik is None or name is None:
                continue
            owners = sorted(f.get("owners") or [], key=canonical_json)
            st = next((s for s in (_us_state(o, "RPTOWNER_STATE") for o in owners) if s), None)
            ctx = RecordContext(fetched, jurisdiction(st), acc, self.record_type, f)
            yield ctx.source_record()
            on = sec_date(sub.get("PERIOD_OF_REPORT")) or sec_date(sub.get("FILING_DATE"))
            valid_from = on if on is not None and on <= observed else observed
            holders = []
            for o in owners:
                who = text(o.get("RPTOWNERNAME"))
                if who is None:
                    continue
                addr = address(_street(o, "RPTOWNER_STREET1", "RPTOWNER_STREET2"),
                               o.get("RPTOWNER_CITY"), _us_state(o, "RPTOWNER_STATE"),
                               _us_zip(o, "RPTOWNER_STATE", "RPTOWNER_ZIPCODE"))  # fmt: skip
                rels = [x.strip() for x in (o.get("RPTOWNER_RELATIONSHIP") or "").split(",")]
                for rel in dict.fromkeys(x for x in rels if x) or ("Other",):
                    role, label = I_ROLES.get(rel.upper(), ("other", None))
                    if role == "officer":
                        title = text(o.get("RPTOWNER_TITLE")) or "officer"
                    elif rel.upper() == "OTHER":
                        title = text(o.get("RPTOWNER_TXT")) or "other"
                    else:
                        title = label or rel.lower()
                    holders.append(Holder(role, title, who, addr))
            yield from emit_business(ctx, source_id=self.source_id, sos_id=f"CIK:{cik}",
                                     name=name, valid_from=valid_from,
                                     holders=holders)  # fmt: skip
