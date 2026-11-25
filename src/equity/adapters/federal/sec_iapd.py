"""SEC investment advisers and their control persons, from the Form ADV Part 1 data files.

Source: the monthly "Form ADV Part 1 Data Files" published on IAPD (adviserinfo.sec.gov/adv,
the SEC's Investment Adviser Public Disclosure site; sec.gov's Form ADV Data page points there
for filings from January 2025 on). Each month is one zip of CSV tables covering every Form ADV
filing submitted that month by SEC-registered advisers (IA_*) and exempt reporting advisers
(ERA_*). The file list comes from reports_metadata.json, the manifest the IAPD page reads:

  https://reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json
  https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/<year>/<fileName>

Read here (four members, over HTTP Range requests: only their compressed bytes are fetched,
about 1 MB of a 7 MB month):

- IA_ADV_Base_A_*.csv / ERA_ADV_Base_*.csv: one row per filing. FilingID, DateSubmitted,
  1A legal name, 1B1 business name, 1D SEC file number, 1E1 CRD number, 1F1 main office
  (street lines, city, state, country, postal code; 1F1-Private = Y when it is also a
  residence, and then the street is not published), 1G mailing address.
- IA_Schedule_A_B_*.csv / ERA_Schedule_A_B_*.csv: Schedule A (direct owners and executive
  officers) and Schedule B (indirect owners), per FilingID: Full Legal Name (individuals as
  "LAST, FIRST, MIDDLE", a suffix sometimes after LAST), DE/FE/I (domestic entity, foreign
  entity, individual), Title or Status, Status Acquired (MM/YYYY), Ownership Code (NA under
  5%, A 5-10%, B 10-25%, C 25-50%, D 50-75%, E 75%+, F other: general partner, trustee,
  elected manager), Control Person (Y/N), PR (public reporting company) and, on Schedule
  B, Entity in Which the interest is owned. The owner's own CRD number (OwnerID) is not kept.

What is emitted, from existing tables only (no debts):

- business: the adviser, sos_id "CRD:<n>", name = 1A, status "SEC registered" or "exempt
  reporting", principal = main office, mailing = 1G, valid from the filing date. A firm that
  filed more than once in the month (amendments) is emitted once, from its latest filing.
- business_role + party per Schedule A/B row. Schedule A titles map to roles by keyword
  (officer titles -> officer, DIRECTOR -> director, MEMBER -> member, MANAGER -> manager, else
  other: owner, shareholder, general or limited partner, trustee); a title naming several
  (OWNER; PRESIDENT; MEMBER) gives one role each. Schedule B rows are 'other', titled
  "indirect owner via <entity>". The ownership band and control-person flag are added to the
  title. Individuals are persons with name parts.

One partition per monthly file (month=YYYY-MM, from 2025-01). `limit` keeps the first
`limit` firms by CRD (fixtures).

Terms: U.S. government data (SEC), free, no login. adviserinfo.sec.gov robots.txt disallows
only form views, brochures and WebLock paths; reports.adviserinfo.sec.gov serves no robots.txt
(403, read as allow-all). Requests carry the project's generic User-Agent (no personal contact
address) and are spaced well under SEC's fair-access limit of 10 per second.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from typing import Any, ClassVar

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
from equity.adapters.rows import RecordContext, canonical_json

CHECKED_ON = "2026-11-25"
REPORTS = "https://reports.adviserinfo.sec.gov/reports/foia"
META_URL = f"{REPORTS}/reports_metadata.json"
PAGE = "https://adviserinfo.sec.gov/adv"
FILE_RE = re.compile(r"^ADV_Filing_Data_(\d{4})(\d{2})01_\d{8}\.zip$")

BASE_COLS = ("FilingID", "DateSubmitted", "1A", "1B1", "1D", "1E1", "1F1-Street 1",
             "1F1-Street 2", "1F1-City", "1F1-State", "1F1-Country", "1F1-Postal",
             "1F1-Private", "1G-Street 1", "1G-Street 2", "1G-City", "1G-State", "1G-Country",
             "1G-Postal", "1G-Private")  # fmt: skip
SCHED_COLS = ("FilingID", "Schedule", "Full Legal Name", "DE/FE/I", "Entity in Which",
              "Title or Status", "Status Acquired", "Ownership Code", "Control Person",
              "PR")  # fmt: skip
# Members per register: base table, schedule A/B table (file names carry the month's dates).
MEMBERS = {"IA": ("IA_ADV_Base_A_", "IA_Schedule_A_B_"),
           "ERA": ("ERA_ADV_Base_", "ERA_Schedule_A_B_")}  # fmt: skip
STATUS = {"IA": "SEC registered", "ERA": "exempt reporting"}
OWNERSHIP = {"NA": "under 5%", "A": "5-10%", "B": "10-25%", "C": "25-50%", "D": "50-75%",
             "E": "75% or more", "F": "general partner, trustee or elected manager"}  # fmt: skip
SUFFIXES = frozenset({"JR", "SR", "II", "III", "IV", "V"})
US = "UNITED STATES"

_OFFICER = re.compile(
    r"\b(PRESIDENT|CEO|CFO|COO|CCO|CIO|CTO|CHIEF|OFFICER|SECRETARY|TREASURER|VP|"
    r"VICE|MANAGING DIRECTOR|GENERAL COUNSEL|CONTROLLER|COMPTROLLER|EXECUTIVE)\b"
)
_DIRECTOR = re.compile(r"\b(DIRECTOR|BOARD|CHAIRMAN|CHAIR)\b")
_MEMBER = re.compile(r"\bMEMBER\b")
_MANAGER = re.compile(r"\bMANAG(ER|ING PARTNER)\b")


def roles_for(title: str | None) -> list[str]:
    """Business roles a Schedule A title names ('OWNER; PRESIDENT' -> ['officer'])."""
    t = (title or "").upper()
    out = []
    if _OFFICER.search(t):
        out.append("officer")
    if _DIRECTOR.search(t.replace("MANAGING DIRECTOR", " ")):
        out.append("director")
    if _MEMBER.search(t):
        out.append("member")
    if _MANAGER.search(t):
        out.append("manager")
    return out or ["other"]


def person_parts(full: str) -> dict[str, str | None]:
    """'YATES, JR., GENE, A.' -> last YATES, suffix JR., first GENE, middle A."""
    parts = [p.strip() for p in full.split(",") if p.strip()]
    if not parts:
        return {}
    last, rest = parts[0], parts[1:]
    suffix = None
    if rest and rest[0].rstrip(".").upper() in SUFFIXES:
        suffix = rest.pop(0)
    first = rest[0] if rest else None
    middle = " ".join(rest[1:]) or None
    return {"first_name": first, "middle": middle, "last_name": last, "suffix": suffix}


def display_name(parts: Mapping[str, str | None]) -> str | None:
    return text(" ".join(str(parts[k]) for k in ("first_name", "middle", "last_name", "suffix")
                         if parts.get(k)))  # fmt: skip


def adv_date(value: Any) -> date | None:
    """'10/12/2026 11:23:12 AM' (or '10/12/2026') -> 2026-10-12."""
    s = (text(value) or "").split(" ")[0]
    try:
        return datetime.strptime(s, "%m/%d/%Y").replace(tzinfo=UTC).date()
    except ValueError:
        return None


def crd(value: Any) -> str | None:
    digits = (text(value) or "").strip()
    return str(int(digits)) if digits.isdigit() and int(digits) > 0 else None


def _member(zf: zipfile.ZipFile, prefix: str) -> str | None:
    for info in zf.infolist():
        name = info.filename.rsplit("/", 1)[-1]
        if name.upper().startswith(prefix.upper()) and name.lower().endswith(".csv"):
            return info.filename
    return None


def csv_rows(zf: zipfile.ZipFile, member: str, keep: tuple[str, ...]) -> Iterator[dict[str, str]]:
    """The `keep` columns of one member, streamed."""
    with zf.open(member) as raw:
        fh = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
        for row in csv.DictReader(fh):
            yield {k: text(row.get(k)) or "" for k in keep if k in row}


def read_firms(zf: zipfile.ZipFile, limit: int | None = None) -> list[dict[str, Any]]:
    """One dict per adviser (latest filing of the month): register, base row, owners."""
    latest: dict[str, dict[str, Any]] = {}
    for reg, (base_prefix, _) in MEMBERS.items():
        member = _member(zf, base_prefix)
        if member is None:
            continue
        for row in csv_rows(zf, member, BASE_COLS):
            key = crd(row.get("1E1"))
            submitted = adv_date(row.get("DateSubmitted"))
            if key is None or submitted is None or not row.get("1A"):
                continue
            rank = (submitted.isoformat(), int(row.get("FilingID") or 0))
            prev = latest.get(key)
            if prev is None or rank > prev["_rank"]:
                latest[key] = {"_rank": rank, "register": reg, "crd": key, "base": row,
                               "owners": []}  # fmt: skip
    keys = sorted(latest, key=int)
    if limit is not None:
        keys = keys[:limit]
    by_filing = {latest[k]["base"]["FilingID"]: latest[k] for k in keys}
    for _, sched_prefix in MEMBERS.values():
        member = _member(zf, sched_prefix)
        if member is None:
            continue
        for row in csv_rows(zf, member, SCHED_COLS):
            firm = by_filing.get(row.get("FilingID") or "")
            if firm is not None:
                firm["owners"].append(row)
    out = []
    for k in keys:
        firm = {x: v for x, v in latest[k].items() if x != "_rank"}
        firm["owners"] = sorted(firm["owners"], key=canonical_json)
        out.append(firm)
    return out


def _us_state(r: Mapping[str, Any], prefix: str) -> str | None:
    country = (text(r.get(f"{prefix}-Country")) or US).upper()
    st = text(r.get(f"{prefix}-State"))
    return st if country == US and st and len(st) == 2 and st.isalpha() else None


def _address(r: Mapping[str, Any], prefix: str) -> dict[str, Any] | None:
    st = _us_state(r, prefix)
    street = text(" ".join(x for x in (text(r.get(f"{prefix}-Street 1")),
                                       text(r.get(f"{prefix}-Street 2"))) if x))  # fmt: skip
    return address(street, r.get(f"{prefix}-City"), st,
                   r.get(f"{prefix}-Postal") if st else None)  # fmt: skip


def holders(owners: list[Mapping[str, Any]]) -> list[Holder]:
    out: list[Holder] = []
    for o in owners:
        raw = text(o.get("Full Legal Name"))
        if raw is None:
            continue
        person = (text(o.get("DE/FE/I")) or "").upper() == "I"
        parts = person_parts(raw) if person else {}
        name = (display_name(parts) if parts else None) or raw
        title = text(o.get("Title or Status"))
        notes = [OWNERSHIP[c] for c in (text(o.get("Ownership Code")),) if c in OWNERSHIP]
        if (text(o.get("Control Person")) or "").upper() == "Y":
            notes.append("control person")
        if (text(o.get("Schedule")) or "").upper() == "B":
            via = text(o.get("Entity in Which"))
            label = f"indirect owner via {via}" if via else "indirect owner"
            title = f"{label}: {title}" if title else label
            roles = ["other"]
        else:
            roles = roles_for(title)
        full_title = f"{title or 'owner'} ({'; '.join(notes)})" if notes else title
        for role in roles:
            out.append(Holder(role, full_title, name, None, person=person,
                              parts=parts if parts.get("last_name") else {}))  # fmt: skip
    return out


class SECInvestmentAdvisers(Adapter):
    source_id: ClassVar[str] = "us.sec.iapd_advisers"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    # A sole-proprietor adviser's legal and business names are a person's name; a Schedule B
    # entity can be a family trust named for one.
    pii_fields: ClassVar[tuple[str, ...]] = (
        "Full Legal Name", "Entity in Which", "1A", "1B1", "1F1-Street 1", "1F1-Street 2",
        "1G-Street 1", "1G-Street 2",
    )  # fmt: skip

    def __init__(self, client: BulkClient | None = None) -> None:
        # Fair access: well under 10 requests/second.
        self.client = client or BulkClient(min_interval_s=0.5, timeout_s=600.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a registry of firms and their control persons
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": PAGE,
            "terms_url": "https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data",
            "terms_summary": (
                "SEC Form ADV Part 1 data files (investment advisers, Schedules A/B owners and "
                "executive officers), monthly zip of CSV on IAPD; U.S. government data, free, "
                "no login. Generic User-Agent, under 10 requests/s (SEC fair access)."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def month_urls(self) -> dict[str, str]:
        """{'2026-10': url} for every monthly Part 1 file in the IAPD manifest."""
        resp = self.client.get(META_URL)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {META_URL}")
        section = json.loads(resp.content).get("advFilingData") or {}
        out: dict[str, str] = {}
        for year, entry in section.items():
            if not str(year).isdigit() or not isinstance(entry, dict):
                continue
            for f in entry.get("files") or []:
                m = FILE_RE.match(str(f.get("fileName") or ""))
                if m:
                    month = f"{m.group(1)}-{m.group(2)}"
                    out[month] = f"{REPORTS}/advFilingData/{year}/{m.group(0)}"
        return dict(sorted(out.items()))

    def partitions(self) -> Iterator[dict[str, str]]:
        for month in self.month_urls():
            yield {"month": month}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: month (YYYY-MM); limit (fixtures: the first `limit` firms by CRD)."""
        p = request.params
        month = p["month"]
        if not re.fullmatch(r"\d{4}-\d{2}", month):
            raise ValueError(f"bad month {month!r}")
        url = self.month_urls().get(month)
        if url is None:
            raise RuntimeError(f"{month}: no Form ADV Part 1 file in {META_URL}")
        zf = remote_zip(self.client, url)
        at = self.client.now()
        firms = read_firms(zf, int(p["limit"]) if "limit" in p else None)
        body = canonical_json({"month": month, "url": url, "firms": firms})
        return Fetched(self.source_id, url, at, 200, body, "application/json")

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            found = self.month_urls()
        except (RuntimeError, OSError, ValueError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        latest = max(found) if found else None
        return HealthReport(self.source_id, bool(found), now,
                            f"{len(found)} months; latest {latest}")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        names = ("Full Legal Name", "Entity in Which", "1A", "1B1")
        streets = ("1F1-Street 1", "1F1-Street 2", "1G-Street 1", "1G-Street 2")
        return scrub_json(content, names, streets)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        observed = fetched.retrieved_at.astimezone(UTC).date()
        firms = json.loads(fetched.content).get("firms") or []
        seen: set[str] = set()
        for firm in sorted(firms, key=lambda f: (int(f.get("crd") or 0), canonical_json(f))):
            key = crd(firm.get("crd"))
            base = firm.get("base") or {}
            name = text(base.get("1A"))
            submitted = adv_date(base.get("DateSubmitted"))
            if key is None or name is None or submitted is None or key in seen:
                continue
            seen.add(key)
            ctx = RecordContext(fetched, jurisdiction(_us_state(base, "1F1")), f"CRD:{key}",
                                "form_adv", firm)  # fmt: skip
            yield ctx.source_record()
            yield from emit_business(
                ctx, source_id=self.source_id, sos_id=f"CRD:{key}", name=name,
                valid_from=submitted if submitted <= observed else observed,
                status=STATUS.get(str(firm.get("register"))),
                principal=_address(base, "1F1"), mailing=_address(base, "1G"),
                holders=holders(firm.get("owners") or []),
            )  # fmt: skip
