"""HHS OIG List of Excluded Individuals/Entities (LEIE): every person and company the Office
of Inspector General has excluded from Medicare, Medicaid and all other federal health care
programs (fraud, patient abuse, licensing actions, defaulted health education loans...).

One CSV, UPDATED.csv (~10 MB, ~83k rows), rewritten monthly with the whole current list
(reinstated parties drop off; the monthly supplement files are not read). Columns: LASTNAME,
FIRSTNAME, MIDNAME, BUSNAME, GENERAL (provider category), SPECIALTY, UPIN, NPI (0 when none),
DOB, ADDRESS, CITY, STATE, ZIP, EXCLTYPE (the authority, e.g. 1128a1), EXCLDATE, REINDATE,
WAIVERDATE, WVRSTATE. Every column is kept in the hashed raw record (the date of birth too:
it is published to tell people with the same name apart).

What is emitted, from existing tables only (one source record per row, record_type
exclusion; the file has no row id, so the key is a hash of the row's identifying columns,
numbered when two rows agree on all of them):

- an excluded company (BUSNAME): business, sos_id NPI:<npi> when the row carries an NPI (the
  key CMS NPPES uses, so the exclusion lands on the provider's record), else LEIE:<key>;
  status 'excluded' with status_date = the exclusion date, valid from the exclusion date,
  principal address = the row's address; a person named on the same row (an owner) is a
  holder (role 'other', title EXCLUDED INDIVIDUAL).
- an excluded individual: party (a person, name in parts) at the row's address.
- address: the normalized U.S. address.

Source: https://oig.hhs.gov/exclusions/exclusions_list.asp (download page:
https://oig.hhs.gov/exclusions/leie-database-supplement-downloads/). U.S. government data,
free, no login; oig.hhs.gov serves no robots.txt (404 on 2026-11-25: no restrictions). The
file ignores Range requests, so it is read whole (one GET).
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import (
    Holder,
    address,
    emit_business,
    emit_party,
    jurisdiction,
    scrub_json,
    text,
)
from equity.adapters.federal.cms_nppes import pseudo_digits
from equity.adapters.federal.fmcsa import parse_day
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.schema.ids import stable_id

PAGE = "https://oig.hhs.gov/exclusions/exclusions_list.asp"
URL = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"
CHECKED_ON = "2026-11-25"
COLUMNS = ("LASTNAME", "FIRSTNAME", "MIDNAME", "BUSNAME", "GENERAL", "SPECIALTY", "UPIN", "NPI",
           "DOB", "ADDRESS", "CITY", "STATE", "ZIP", "EXCLTYPE", "EXCLDATE", "REINDATE",
           "WAIVERDATE", "WVRSTATE")  # fmt: skip
NAMES = ("LASTNAME", "FIRSTNAME", "MIDNAME", "BUSNAME")
IDENTITY = ("LASTNAME", "FIRSTNAME", "MIDNAME", "BUSNAME", "NPI", "DOB", "ADDRESS", "EXCLTYPE",
            "EXCLDATE")  # fmt: skip


def read_rows(content: bytes, limit: int | None = None, step: int = 1) -> list[dict[str, str]]:
    """The LEIE columns of UPDATED.csv, empty cells dropped; every `step`-th row."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace"),
                                        newline=""))  # fmt: skip
    if reader.fieldnames is None or "EXCLTYPE" not in reader.fieldnames:
        raise RuntimeError("not an LEIE file: no EXCLTYPE column")
    out: list[dict[str, str]] = []
    for i, row in enumerate(reader):
        if limit is not None and len(out) >= limit:
            break
        if i % step:
            continue
        out.append({k: v for k in COLUMNS if (v := text(row.get(k))) is not None})
    return out


def npi(value: Any) -> str | None:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits if len(digits) == 10 and int(digits) > 0 else None


def person_name(r: Mapping[str, Any]) -> tuple[str, dict[str, str | None]] | None:
    parts = {"first_name": text(r.get("FIRSTNAME")), "middle": text(r.get("MIDNAME")),
             "last_name": text(r.get("LASTNAME")), "suffix": None}  # fmt: skip
    if parts["last_name"] is None:
        return None
    who = " ".join(v for v in (parts["first_name"], parts["middle"], parts["last_name"]) if v)
    return who, parts


class HHSOIGExclusions(Adapter):
    source_id: ClassVar[str] = "us.hhs_oig.leie"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = (*NAMES, "ADDRESS")

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=600.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a federal registry of named people and companies
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": URL,
            "terms_url": PAGE,
            "terms_summary": (
                "HHS OIG List of Excluded Individuals/Entities, UPDATED.csv rewritten monthly; "
                "U.S. government data, free, no login, no license terms. oig.hhs.gov serves no "
                "robots.txt (404). Dates of birth stay in the raw record only."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {"file": "updated"}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: file ('updated', the only partition); limit, step (fixtures: the first
        `limit` of every `step`-th row, so a sample reaches past the companies listed first)."""
        p = request.params
        if p.get("file", "updated") != "updated":
            raise ValueError(f"bad file {p['file']!r}")
        resp = self.client.get(URL)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {URL}")
        rows = read_rows(
            resp.content, int(p["limit"]) if "limit" in p else None, max(1, int(p.get("step", "1")))
        )
        return Fetched(self.source_id, URL, resp.retrieved_at, 200,
                       canonical_json({"url": URL, "rows": rows}), "application/json")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        """Names and streets pseudonymized; NPI, UPIN and date of birth replaced too (they would
        undo the name pseudonyms)."""
        data = json.loads(scrub_json(content, NAMES, ("ADDRESS",)))
        for r in data.get("rows") or []:
            if npi(r.get("NPI")):
                r["NPI"] = pseudo_digits("NPI", r["NPI"], 10)
            if r.get("UPIN"):
                r["UPIN"] = "TEST" + pseudo_digits("UPIN", r["UPIN"], 2)
            if r.get("DOB"):
                r["DOB"] = "19000101"
        return canonical_json(data)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: dict[str, int] = {}
        for r in sorted(data.get("rows") or [], key=canonical_json):
            business = text(r.get("BUSNAME"))
            who = person_name(r)
            if business is None and who is None:
                continue
            ident = "|".join(str(r.get(k) or "") for k in IDENTITY)
            seen[ident] = seen.get(ident, 0) + 1
            key = stable_id(self.source_id, ident, str(seen[ident]))
            st = text(r.get("STATE"))
            ctx = RecordContext(fetched, jurisdiction(st), key, "exclusion", r)
            yield ctx.source_record()
            addr = address(r.get("ADDRESS"), r.get("CITY"), st, r.get("ZIP"))
            excluded = self._day(r.get("EXCLDATE"), observed)
            if business is None and who is not None:
                yield from emit_party(ctx, self.source_id, "excluded", who[0], addr, person=True,
                                      parts=who[1])  # fmt: skip
                continue
            holders = []
            if who is not None:
                holders.append(Holder("other", "EXCLUDED INDIVIDUAL", who[0], addr, person=True,
                                      parts=who[1]))  # fmt: skip
            n = npi(r.get("NPI"))
            yield from emit_business(
                ctx, source_id=self.source_id, sos_id=f"NPI:{n}" if n else f"LEIE:{key}",
                name=str(business), valid_from=excluded or observed, status="excluded",
                status_date=excluded, principal=addr, holders=holders,
            )  # fmt: skip

    @staticmethod
    def _day(value: Any, observed: date) -> date | None:
        d = parse_day(value)
        return d if d is not None and d <= observed else None

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            resp = self.client.get(URL)
            rows = read_rows(resp.content) if resp.status == 200 else []
        except (OSError, RuntimeError, ValueError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        ok = len(rows) > 10_000
        return HealthReport(self.source_id, ok, now, f"rows={len(rows)}", COLUMNS, rows=len(rows))
