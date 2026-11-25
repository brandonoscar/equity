"""USPTO trademark owners and patent assignments, from the USPTO daily bulk XML files.

- us.uspto.trademark_owners: Trademark Full Text XML, daily applications (ODP product
  TRTDXFAP, files apcYYMMDD.zip). Each <case-file> is one application or registration
  (serial number, filing date, status, mark text) with its owners (<case-file-owner>: party
  type, legal entity type, name, address, dba/aka, composed-of statement).
- us.uspto.patent_assignments: Patent Assignment XML, daily (ODP product PASDL, files
  adYYYYMMDD.zip). Each <patent-assignment> is one recorded conveyance (reel/frame, recorded
  date, conveyance text) with its assignors (name, execution date), assignees (name,
  address) and the patents and applications it covers.

What is emitted, from existing tables only:

Trademarks (source record = serial number): an owner that is an organization becomes a
business, sos_id "USPTO-TM:<serial>:<party type>-<entry>", with its address; an individual
owner (legal entity type 01) is a party (person) with its address, and when the record gives a
dba/aka name that name becomes the business with the individual as role 'other' ("trademark
owner (individual)"). Mark text, status, party type and entity codes stay in the source record.

Patent assignments (source record = reel/frame): each organization assignee becomes a
business, sos_id "USPTO-PA:<reel>-<frame>:<n>", with its address. When the conveyance is an
assignment of the assignor's interest (inventors to their employer, one company to another)
each assignor is tied to every organization assignee by business_role 'other', title "patent
assignor"; for other conveyances (security interests, releases, mergers, name changes) the
assignors are parties of the record but get no role, since the assignee is not their
company. Assignors carry no address in the data; "LAST, FIRST" names are split into parts.

Access (checked 2026-11-25): bulkdata.uspto.gov, the old bulk host, no longer resolves; its
files moved to the Open Data Portal (data.uspto.gov), whose download links answer scripts
with an AWS WAF challenge page and whose API (api.uspto.gov) requires an API key tied to a
USPTO.gov account login. This project does neither, so these adapters read files saved by
hand: download the daily zips from https://data.uspto.gov/bulkdata/datasets/TRTDXFAP and
.../PASDL in a browser and drop them in data/manual/<source_id>/ (or pass path=<file>).
One partition per file. The XML is parsed with iterparse, one record at a time.

Terms: USPTO bulk data is U.S. government work, free; the ODP terms ask users not to overload
the service. Layouts: the Trademark Case Files Dataset variable tables (which name each XML
element) and the Patent Assignment Dataset schema, both on www.uspto.gov.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator, Mapping
from contextlib import ExitStack
from datetime import UTC, date, datetime
from pathlib import Path
from typing import IO, Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import (
    Holder,
    address,
    emit_business,
    holder_party,
    jurisdiction,
    scrub_json,
    text,
)
from equity.adapters.rows import RecordContext, canonical_json
from equity.matching.orgs import classify

CHECKED_ON = "2026-11-25"
MANUAL_DIR = Path("data") / "manual"
ODP = "https://data.uspto.gov/bulkdata/datasets"
INDIVIDUAL = "01"  # legal-entity-type-code of a natural person
ASSIGNOR_INTEREST = re.compile(r"ASSIGNMENT OF (THE )?ASSIGNOR", re.I)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _kids(el: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in el if _local(c.tag) == name]


def _val(el: ET.Element | None, *path: str) -> str | None:
    for name in path:
        if el is None:
            return None
        el = next((c for c in el if _local(c.tag) == name), None)
    return None if el is None else text("".join(el.itertext()))


def _day(value: Any) -> date | None:
    s = re.sub(r"\D", "", text(value) or "")
    if len(s) != 8 or s == "00000000":
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:]))
    except ValueError:
        return None


def iter_elements(stream: IO[bytes], tag: str) -> Iterator[ET.Element]:
    """Each complete <tag> element of an XML stream; cleared once the caller moves on."""
    for _, el in ET.iterparse(stream, events=("end",)):  # noqa: S314 - USPTO bulk XML
        if _local(el.tag) == tag:
            yield el
            el.clear()


def xml_streams(source: Path, stack: ExitStack) -> Iterator[IO[bytes]]:
    """The XML members of a zip (or the file itself), opened in turn."""
    if zipfile.is_zipfile(source):
        zf = stack.enter_context(zipfile.ZipFile(source))
        for info in zf.infolist():
            if info.filename.lower().endswith(".xml"):
                yield stack.enter_context(zf.open(info))
    else:
        yield stack.enter_context(source.open("rb"))


# --- trademark case files --------------------------------------------------------------------

TM_OWNER = {"entry-number": "entry_number", "party-type": "party_type",
            "legal-entity-type-code": "legal_entity_type", "entity-statement": "entity_statement",
            "party-name": "owner_name", "address-1": "owner_address_1",
            "address-2": "owner_address_2", "city": "city", "state": "state",
            "country": "country", "postcode": "postcode", "dba-aka-text": "dba_aka",
            "composed-of-statement": "composed_of"}  # fmt: skip


def trademark_case(el: ET.Element) -> dict[str, Any] | None:
    serial = _val(el, "serial-number")
    if serial is None:
        return None
    owners = []
    for group in _kids(el, "case-file-owners"):
        for o in _kids(group, "case-file-owner"):
            row = {k: _val(o, tag) for tag, k in TM_OWNER.items()}
            row["nationality_state"] = _val(o, "nationality", "state")
            row["nationality_country"] = _val(o, "nationality", "country")
            if row["owner_name"]:
                owners.append({k: v for k, v in row.items() if v is not None})
    return {
        "serial_number": serial, "registration_number": _val(el, "registration-number"),
        "transaction_date": _val(el, "transaction-date"),
        "filing_date": _val(el, "case-file-header", "filing-date"),
        "status_code": _val(el, "case-file-header", "status-code"),
        "status_date": _val(el, "case-file-header", "status-date"),
        "mark": _val(el, "case-file-header", "mark-identification"), "owners": owners,
    }  # fmt: skip


def trademark_cases(source: Path, limit: int | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with ExitStack() as stack:
        for stream in xml_streams(source, stack):
            for el in iter_elements(stream, "case-file"):
                case = trademark_case(el)
                if case is not None and case["owners"]:
                    out.append(case)
                    if limit is not None and len(out) >= limit:
                        return out
    return out


# --- patent assignments ----------------------------------------------------------------------


def patent_assignment(el: ET.Element) -> dict[str, Any] | None:
    rec = next(iter(_kids(el, "assignment-record")), None)
    reel, frame = _val(rec, "reel-no"), _val(rec, "frame-no")
    if rec is None or reel is None or frame is None:
        return None
    assignors = []
    for group in _kids(el, "patent-assignors"):
        for a in _kids(group, "patent-assignor"):
            if (name := _val(a, "name")) is not None:
                assignors.append(
                    {
                        "name": name,
                        "execution_date": _val(a, "execution-date", "date"),
                        "date_acknowledged": _val(a, "date-acknowledged", "date"),
                    }
                )
    assignees = []
    for group in _kids(el, "patent-assignees"):
        for a in _kids(group, "patent-assignee"):
            if (name := _val(a, "name")) is not None:
                assignees.append({"name": name, "address_1": _val(a, "address-1"),
                                  "address_2": _val(a, "address-2"), "city": _val(a, "city"),
                                  "state": _val(a, "state"),
                                  "country": _val(a, "country-name") or _val(a, "country"),
                                  "postcode": _val(a, "postcode")})  # fmt: skip
    props = []
    for group in _kids(el, "patent-properties"):
        for p in _kids(group, "patent-property"):
            docs = [{"country": _val(d, "country"), "doc_number": _val(d, "doc-number"),
                     "kind": _val(d, "kind"), "date": _val(d, "date")}
                    for d in _kids(p, "document-id")]  # fmt: skip
            props.append({"documents": docs, "title": _val(p, "invention-title")})
    return {
        "reel_no": reel, "frame_no": frame, "recorded_date": _val(rec, "recorded-date", "date"),
        "last_update_date": _val(rec, "last-update-date", "date"),
        "purge_indicator": _val(rec, "purge-indicator"), "page_count": _val(rec, "page-count"),
        "conveyance_text": _val(rec, "conveyance-text"), "assignors": assignors,
        "assignees": assignees, "properties": props,
    }  # fmt: skip


def patent_assignments(source: Path, limit: int | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with ExitStack() as stack:
        for stream in xml_streams(source, stack):
            for el in iter_elements(stream, "patent-assignment"):
                rec = patent_assignment(el)
                if rec is not None:
                    out.append(rec)
                    if limit is not None and len(out) >= limit:
                        return out
    return out


def split_last_first(name: str) -> dict[str, str | None]:
    """'DOE, JOHN Q.' -> parts; {} for anything else (an organization, one word)."""
    if name.count(",") != 1 or classify(name).party_kind == "org":
        return {}
    last, rest = (text(p) for p in name.split(","))
    given = (rest or "").split()
    if not last or not given:
        return {}
    return {"first_name": given[0], "middle": " ".join(given[1:]) or None, "last_name": last,
            "suffix": None}  # fmt: skip


# --- the adapters ----------------------------------------------------------------------------


class _USPTODaily(Adapter):
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "manual"
    product: ClassVar[str]
    file_re: ClassVar[re.Pattern[str]]
    summary: ClassVar[str]

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a registry of names, owners and addresses
            "jurisdiction": "US",
            "access_method": "manual",
            "base_url": f"{ODP}/{self.product}",
            "terms_url": "https://data.uspto.gov/home",
            "terms_summary": self.summary,
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": None,  # files are saved by hand; nothing is fetched
            "cost_model": "free",
        }

    @classmethod
    def drop_dir(cls) -> Path:
        return MANUAL_DIR / cls.source_id

    def files(self) -> dict[str, Path]:
        drop = self.drop_dir()
        found = [f for f in drop.iterdir() if self.file_re.fullmatch(f.name)] if drop.is_dir() \
            else []  # fmt: skip
        return {f.name: f for f in sorted(found)}

    def partitions(self) -> Iterator[dict[str, str]]:
        files = self.files()
        if not files:
            raise RuntimeError(self.missing())
        for name in files:
            yield {"file": name}

    def missing(self) -> str:
        return (
            f"{self.drop_dir()}: no {self.product} files. USPTO serves them only to a browser "
            f"(AWS WAF) or with an ODP API key (account login): save the daily zips from "
            f"{ODP}/{self.product} by hand into this folder, or pass path=<file>."
        )

    def source_file(self, p: Mapping[str, str]) -> Path:
        if p.get("path"):
            return Path(p["path"])
        name = p.get("file", "")
        path = self.files().get(name)
        if path is None:
            raise RuntimeError(f"{name!r}: " + self.missing())
        return path

    def read(self, source: Path, limit: int | None) -> list[dict[str, Any]]:
        raise NotImplementedError

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: file (a name in the drop folder) or path; limit (fixtures)."""
        p = request.params
        source = self.source_file(p)
        records = self.read(source, int(p["limit"]) if "limit" in p else None)
        url = f"{ODP}/{self.product}#file={source.name}"
        at = datetime.fromtimestamp(int(source.stat().st_mtime), UTC)
        body = {"file": source.name, "url": url, "records": records}
        return Fetched(self.source_id, url, at, None, canonical_json(body), "application/json")

    def health(self) -> HealthReport:
        """No network: whether a file is on hand to load."""
        files = self.files()
        detail = f"{len(files)} files on hand" if files else self.missing()
        return HealthReport(self.source_id, bool(files), datetime.now(UTC), detail)

    def records(self, fetched: Fetched) -> list[dict[str, Any]]:
        return sorted(json.loads(fetched.content).get("records") or [], key=canonical_json)


class USPTOTrademarkOwners(_USPTODaily):
    source_id: ClassVar[str] = "us.uspto.trademark_owners"
    product: ClassVar[str] = "TRTDXFAP"
    file_re: ClassVar[re.Pattern[str]] = re.compile(r"apc\d{6}(-\d+)?\.(zip|xml)", re.I)
    pii_fields: ClassVar[tuple[str, ...]] = ("owner_name", "owner_address_1", "owner_address_2",
                                             "dba_aka", "composed_of")  # fmt: skip
    summary: ClassVar[str] = (
        "USPTO Trademark Full Text XML, daily applications (ODP TRTDXFAP); U.S. government "
        "data, free. Downloads need a browser (AWS WAF) or an ODP API key, so files are saved "
        "by hand into data/manual/."
    )

    def read(self, source: Path, limit: int | None) -> list[dict[str, Any]]:
        return trademark_cases(source, limit)

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, ("owner_name", "dba_aka", "composed_of"),
                          ("owner_address_1", "owner_address_2"))  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for case in self.records(fetched):
            serial = text(case.get("serial_number"))
            owners = case.get("owners") or []
            if serial is None or serial in seen or not owners:
                continue
            seen.add(serial)
            st = next((text(o.get("state")) for o in owners if text(o.get("state"))), None)
            ctx = RecordContext(fetched, jurisdiction(st), serial, "trademark_case", case)
            yield ctx.source_record()
            filed = _day(case.get("filing_date"))
            valid_from = filed if filed is not None and filed <= observed else observed
            for o in sorted(owners, key=canonical_json):
                name = text(o.get("owner_name"))
                if name is None:
                    continue
                addr = address(" ".join(p for p in (text(o.get("owner_address_1")),
                                                    text(o.get("owner_address_2"))) if p),
                               o.get("city"), o.get("state"), o.get("postcode"))  # fmt: skip
                ptype = text(o.get("party_type")) or "00"
                entry = text(o.get("entry_number")) or "00"
                sos_id = f"USPTO-TM:{serial}:{ptype}-{entry}"
                individual = text(o.get("legal_entity_type")) == INDIVIDUAL
                if not individual:
                    yield from emit_business(ctx, source_id=self.source_id, sos_id=sos_id,
                                             name=name, valid_from=valid_from,
                                             principal=addr)  # fmt: skip
                    continue
                me = Holder("other", "trademark owner (individual)", name, addr, person=True)
                dba = text(o.get("dba_aka"))
                if dba:
                    dba_name = re.sub(r"^(DBA|D/B/A|AKA|A/K/A|TA|T/A)\b\.?\s*", "", dba,
                                      flags=re.I) or dba  # fmt: skip
                    yield from emit_business(ctx, source_id=self.source_id, sos_id=sos_id,
                                             name=dba_name, valid_from=valid_from,
                                             principal=addr, holders=[me])  # fmt: skip
                    continue
                if addr is not None:
                    yield NormalizedRow("address", addr)
                yield holder_party(ctx, self.source_id, f"{serial}:{ptype}-{entry}", me)[1]


class USPTOPatentAssignments(_USPTODaily):
    source_id: ClassVar[str] = "us.uspto.patent_assignments"
    product: ClassVar[str] = "PASDL"
    file_re: ClassVar[re.Pattern[str]] = re.compile(r"ad\d{8}(-\d+)?\.(zip|xml)", re.I)
    pii_fields: ClassVar[tuple[str, ...]] = ("name", "address_1", "address_2")
    summary: ClassVar[str] = (
        "USPTO Patent Assignment XML, daily (ODP PASDL); U.S. government data, free. "
        "Downloads need a browser (AWS WAF) or an ODP API key, so files are saved by hand "
        "into data/manual/."
    )

    def read(self, source: Path, limit: int | None) -> list[dict[str, Any]]:
        return patent_assignments(source, limit)

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, ("name",), ("address_1", "address_2"))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for rec in self.records(fetched):
            reel, frame = text(rec.get("reel_no")), text(rec.get("frame_no"))
            if reel is None or frame is None:
                continue
            key = f"{reel.zfill(6)}-{frame.zfill(4)}"
            if key in seen or (text(rec.get("purge_indicator")) or "N").upper() == "Y":
                continue
            seen.add(key)
            assignees = rec.get("assignees") or []
            st = next((text(a.get("state")) for a in assignees if text(a.get("state"))), None)
            ctx = RecordContext(fetched, jurisdiction(st), key, "patent_assignment", rec)
            yield ctx.source_record()
            recorded = _day(rec.get("recorded_date"))
            valid_from = recorded if recorded is not None and recorded <= observed else observed
            conveyance = text(rec.get("conveyance_text")) or ""
            tie = bool(ASSIGNOR_INTEREST.search(conveyance))
            assignors = []
            for a in rec.get("assignors") or []:
                if (name := text(a.get("name"))) is not None:
                    parts = split_last_first(name)
                    assignors.append(Holder("other", "patent assignor", name, None,
                                            person=bool(parts), parts=parts))  # fmt: skip
            orgs = 0
            for n, a in enumerate(assignees, 1):
                name = text(a.get("name"))
                if name is None:
                    continue
                addr = address(" ".join(p for p in (text(a.get("address_1")),
                                                    text(a.get("address_2"))) if p),
                               a.get("city"), a.get("state"), a.get("postcode"))  # fmt: skip
                if classify(name).party_kind == "org":
                    orgs += 1
                    yield from emit_business(ctx, source_id=self.source_id,
                                             sos_id=f"USPTO-PA:{key}:{n}", name=name,
                                             valid_from=valid_from, principal=addr,
                                             holders=assignors if tie else ())  # fmt: skip
                    continue
                parts = split_last_first(name)
                h = Holder("other", "patent assignee", name, addr, person=bool(parts),
                           parts=parts)  # fmt: skip
                if addr is not None:
                    yield NormalizedRow("address", addr)
                yield holder_party(ctx, self.source_id, key, h)[1]
            if not (tie and orgs):
                for h in assignors:
                    yield holder_party(ctx, self.source_id, key, h)[1]
