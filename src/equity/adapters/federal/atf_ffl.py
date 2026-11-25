"""ATF Federal Firearms Licensee (FFL) listing: every active federal firearms license, as the
Bureau of Alcohol, Tobacco, Firearms and Explosives publishes it each month
(https://www.atf.gov/firearms/listing-federal-firearms-licensees: a complete list and lists by
state, as tab-delimited text and Excel, e.g. 1126-ffl-list-complete.txt for November 2026).

Columns (read by header name, canonicalized: 'Lic Regn' -> LIC_REGN): LIC_REGN, LIC_DIST,
LIC_CNTY, LIC_TYPE, LIC_XPRDTE, LIC_SEQN (together the license number, printed
R-DD-CCC-TT-XX-SSSSS), LICENSE_NAME (the licensee: a person or a company), BUSINESS_NAME (the
trade name), PREMISE_STREET / CITY / STATE / ZIP_CODE, MAIL_STREET / CITY / STATE / ZIP_CODE,
VOICE_PHONE (not kept).

What is emitted, from existing tables only:

- source_record: one per license in a month file (record_key = the full license number,
  record_type ffl_license); license type and expiration code stay in the hashed raw record.
- business: sos_id FFL:<region>-<district>-<county>-<type>-<sequence> (the license number
  without its expiration code, which changes at renewal), name = the business name (else the
  licensee's name), principal address = the premises, mailing address = the mailing
  address, valid from the first day of the file's month (a monthly snapshot: no issue date
  is published).
- business_role + party: the licensee, role 'other', title LICENSEE: <license type> (a
  person when the name has no organization marker; 'LAST, FIRST M' split into parts).
- address: the premises and mailing addresses.

Partitions: one per month file. Access: www.atf.gov, robots.txt included, answered this
project's client with an Akamai 403 "Access Denied" on 2026-11-25. The adapter does not work
around it and is not registered: save the month's list from the page by hand to
data/manual/us.atf.ffl/ (any of .txt, .csv, .xlsx; a zip of them too) or pass path=<file>.
U.S. government data, free, no login.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import (
    Holder,
    address,
    emit_business,
    jurisdiction,
    scrub_json,
    text,
)
from equity.adapters.federal.bulk_zip import file_time
from equity.adapters.http import PoliteClient
from equity.adapters.person_lists import (
    MANUAL_DIR,
    Member,
    canon,
    delivery_members,
    split_name,
    xlsx_rows,
)
from equity.adapters.rows import RecordContext, canonical_json
from equity.geo import county_by_fips
from equity.matching.orgs import classify

PAGE = "https://www.atf.gov/firearms/listing-federal-firearms-licensees"
CHECKED_ON = "2026-11-25"
KEEP = ("LIC_REGN", "LIC_DIST", "LIC_CNTY", "LIC_TYPE", "LIC_XPRDTE", "LIC_SEQN",
        "LICENSE_NAME", "BUSINESS_NAME", "PREMISE_STREET", "PREMISE_CITY", "PREMISE_STATE",
        "PREMISE_ZIP_CODE", "MAIL_STREET", "MAIL_CITY", "MAIL_STATE", "MAIL_ZIP_CODE")  # fmt: skip
NAMES = ("LICENSE_NAME", "BUSINESS_NAME")
STREETS = ("PREMISE_STREET", "MAIL_STREET")
# 27 CFR 478.41: license types.
TYPES = {
    "01": "Dealer in firearms other than destructive devices",
    "02": "Pawnbroker in firearms other than destructive devices",
    "03": "Collector of curios and relics",
    "06": "Manufacturer of ammunition for firearms",
    "07": "Manufacturer of firearms other than destructive devices",
    "08": "Importer of firearms other than destructive devices",
    "09": "Dealer in destructive devices",
    "10": "Manufacturer of destructive devices",
    "11": "Importer of destructive devices",
}  # fmt: skip
# 1126-ffl-list... = November 2026 (MMYY).
_MONTH = re.compile(r"(?<!\d)(\d{2})(\d{2})-ffl", re.I)


def file_month(name: str) -> date | None:
    m = _MONTH.search(name)
    if m is None or not 1 <= int(m[1]) <= 12:
        return None
    return date(2000 + int(m[2]), int(m[1]), 1)


def table_rows(lines: Iterable[list[str]], limit: int | None = None) -> list[dict[str, str]]:
    """The KEEP columns of a listing (first row the header), non-empty values only."""
    out: list[dict[str, str]] = []
    header: list[str] | None = None
    for cells in lines:
        if header is None:
            header = [canon(h) for h in cells]
            continue
        if not any(c.strip() for c in cells):
            continue
        row = dict(zip(header, (c.strip() for c in cells), strict=False))
        out.append({k: v for k in KEEP if (v := row.get(k, ""))})
        if limit is not None and len(out) >= limit:
            break
    return out


def member_rows(member: Member, limit: int | None = None) -> list[dict[str, str]]:
    """Rows of one hand-saved file: .xlsx, or text delimited by tabs (else commas or |)."""
    if member.is_xlsx:
        with member.open() as raw:
            return table_rows(xlsx_rows(raw), limit)
    with member.open() as raw:
        text_io = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
        first = text_io.readline()
        delim = "\t" if "\t" in first else "|" if "|" in first else ","
        return table_rows(csv.reader(_chain(first, text_io), delimiter=delim), limit)


def _chain(first: str, rest: Iterable[str]) -> Iterator[str]:
    yield first
    yield from rest


def license_number(r: Mapping[str, Any], with_expiry: bool = True) -> str | None:
    parts = [text(r.get(k)) for k in ("LIC_REGN", "LIC_DIST", "LIC_CNTY", "LIC_TYPE",
                                      "LIC_XPRDTE", "LIC_SEQN")]  # fmt: skip
    if not (parts[0] and parts[1] and parts[5]):
        return None
    if not with_expiry:
        parts = parts[:4] + parts[5:]
    return "-".join(p or "" for p in parts)


def person_parts(name: str) -> dict[str, str | None]:
    p = split_name(name, "last_comma_first") if "," in name else dict.fromkeys(
        ("first", "middle", "last", "suffix"))  # fmt: skip
    return {"first_name": p["first"], "middle": p["middle"], "last_name": p["last"],
            "suffix": p["suffix"]}  # fmt: skip


class ATFFirearmsLicensees(Adapter):
    source_id: ClassVar[str] = "us.atf.ffl"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "manual"
    pii_fields: ClassVar[tuple[str, ...]] = (*NAMES, *STREETS)

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=120.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a federal registry of licensees
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": PAGE,
            "terms_url": PAGE,
            "terms_summary": (
                "ATF Federal Firearms Licensee listing, monthly, complete and by state, text "
                "and Excel; U.S. government data, free, no login. www.atf.gov (robots.txt "
                "included) answered this client with an Akamai 403 on 2026-11-25, so the "
                "adapter reads hand-saved files (path= or data/manual/<source_id>/)."
            ),
            "terms_checked_on": None,
            "robots_checked_on": None,
            "cost_model": "free",
        }

    @property
    def manual_dir(self) -> Path:
        return MANUAL_DIR / self.source_id

    def members(self, path: str | None = None) -> list[Member]:
        source = Path(path) if path else self.manual_dir
        if not source.exists():
            return []
        return delivery_members(source, include=r"\.(txt|csv|tsv|xlsx)$")

    def partitions(self) -> Iterator[dict[str, str]]:
        for m in self.members():
            yield {"file": m.label}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: file (a month file's name, from partitions()); path (a hand-saved file,
        zip or folder, instead of data/manual/us.atf.ffl/); limit (fixtures)."""
        p = request.params
        members = self.members(p.get("path"))
        if p.get("file"):
            members = [m for m in members if m.label == p["file"]]
        if not members:
            raise RuntimeError(
                f"no FFL listing file{' ' + p['file'] if p.get('file') else ''}: save the "
                f"month's list from {PAGE} by hand to {self.manual_dir}/ (or pass path=)"
            )
        if len(members) > 1:
            raise ValueError(f"{len(members)} files; name one with file=")
        member = members[0]
        rows = member_rows(member, int(p["limit"]) if "limit" in p else None)
        month = file_month(member.label)
        body = {"file": member.label, "month": None if month is None else month.isoformat(),
                "rows": rows}  # fmt: skip
        return Fetched(self.source_id, f"{PAGE}#{member.label}", file_time(member.path), None,
                       canonical_json(body), "application/json")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, NAMES, STREETS)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        month = date.fromisoformat(data["month"]) if data.get("month") else None
        valid_from = month if month is not None and month <= observed else observed
        seen: set[str] = set()
        for r in sorted(data.get("rows") or [], key=canonical_json):
            number, base = license_number(r), license_number(r, with_expiry=False)
            licensee = text(r.get("LICENSE_NAME"))
            name = text(r.get("BUSINESS_NAME")) or licensee
            if number is None or base is None or name is None or number in seen:
                continue
            seen.add(number)
            ctx = RecordContext(fetched, self.jurisdiction(r), number, "ffl_license", r)
            yield ctx.source_record()
            premises = address(r.get("PREMISE_STREET"), r.get("PREMISE_CITY"),
                               r.get("PREMISE_STATE"), r.get("PREMISE_ZIP_CODE"))  # fmt: skip
            mailing = address(r.get("MAIL_STREET"), r.get("MAIL_CITY"), r.get("MAIL_STATE"),
                              r.get("MAIL_ZIP_CODE"))  # fmt: skip
            holders: list[Holder] = []
            if licensee:
                kind = text(r.get("LIC_TYPE")) or ""
                title = f"LICENSEE: {TYPES.get(kind.zfill(2), kind)}" if kind else "LICENSEE"
                person = classify(licensee).party_kind != "org"
                holders.append(Holder("other", title, licensee, premises, person=person,
                                      parts=person_parts(licensee) if person else {}))  # fmt: skip
            yield from emit_business(
                ctx, source_id=self.source_id, sos_id=f"FFL:{base}", name=name,
                valid_from=valid_from, status="licensed", principal=premises, mailing=mailing,
                holders=holders,
            )  # fmt: skip

    @staticmethod
    def jurisdiction(r: Mapping[str, Any]) -> str:
        """The premises county (LIC_CNTY read as its FIPS county code), else the state."""
        st = (text(r.get("PREMISE_STATE")) or "").upper()
        county = text(r.get("LIC_CNTY"))
        if st and county and county.isdigit():
            try:
                return county_by_fips(st, county.zfill(3)).fips5
            except KeyError:
                pass
        return jurisdiction(st or None)

    def health(self) -> HealthReport:
        """The listing page answers (it did not, 2026-11-25: Akamai 403)."""
        now = datetime.now(UTC)
        try:
            resp = self.client.get(PAGE)
        except (OSError, RuntimeError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        ok = resp.status == 200 and b"ffl" in resp.content.lower()
        return HealthReport(self.source_id, ok, now, f"status={resp.status}")
