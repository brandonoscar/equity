"""Harris County, TX Justice Courts: civil judgments entered (public data extract).

The JP courts' Public Data Extract (jpwebsite.harriscountytx.gov/PublicExtracts) serves the
"Judgments Entered" civil extract as CSV with no login: case, type, claim, parties and their
addresses, judgment text and date, in favor of / against, amount, fees, costs and interest.
No license or terms are published (used on the project owner's decision, 2026-11-23).

Each judgment with an amount is a COURT_ORDER instrument (a justice-court money judgment; it
becomes a lien only once abstracted, which this extract does not show). The party in
"Judgment Against" is the debtor, with the defendant's address when that party is the
defendant or second defendant; "Judgment In Favor Of" is the creditor.

Partitions are 14-day windows of judgment date (the extract allows 90 days for all courts and
case types, but a 30-day window already takes about as long as Cloudflare waits) from 2010.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

BASE = "https://jpwebsite.harriscountytx.gov/PublicExtracts/GetExtractData"
COUNTY = "48201"
# Every civil case type, as the extract page sends for "all types".
CASE_TYPES = ("64033,56068,8462,56073,64007,56072,8463,56074,56075,8464,56076,56079,56080,"
              "58183,8465,8466,56081,56083,51413,51414,56084,56085")  # fmt: skip
FIRST = date(2010, 1, 1)
WINDOW_DAYS = 14  # 30 days took 111 s, at the Cloudflare 100 s origin timeout (HTTP 524)
EXTRACT_LIMIT_DAYS = 90  # the most the extract serves for all courts and case types


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


def _money(v: Any) -> Decimal | None:
    s = str(v or "").replace("$", "").replace(",", "").strip()
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() and d > 0 else None


def _date(v: Any) -> date | None:
    """MM/DD/YYYY or YYYY-MM-DD (a calendar date; no time zone)."""
    s = str(v or "").strip()[:10]
    try:
        if len(s) == 10 and s[2] == "/" and s[5] == "/":
            return date(int(s[6:]), int(s[:2]), int(s[3:5]))
        return date.fromisoformat(s)
    except ValueError:
        return None


def _field(row: Mapping[str, Any], name: str) -> str | None:
    """Column names carry trailing spaces in places; match them trimmed."""
    for k, v in row.items():
        if k.strip() == name:
            return _text(v)
    return None


def _addr(row: Mapping[str, Any], who: str) -> dict[str, Any] | None:
    line = " ".join(x for x in (_field(row, f"{who} Addr Line 1"),
                                _field(row, f"{who} Addr Line 2")) if x) or None  # fmt: skip
    z = (_field(row, f"{who} Addr Zip") or "")[:5]
    return normalized_address(line, _field(row, f"{who} Addr City"),
                              _field(row, f"{who} Addr State"),
                              z if z.isdigit() and len(z) == 5 else None)  # fmt: skip


class HarrisJPJudgments(Adapter):
    source_id: ClassVar[str] = "tx.harris.jp.judgments"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = (
        *(
            f"{w} {f}"
            for w in ("Defendant", "Second Defendant", "Plaintiff", "Second Plaintiff")
            for f in ("Name", "Addr Line 1 ", "Addr Line 2 ", "Addr Line 1", "Addr Line 2")
        ),
        "Judgment Against ",
        "Judgment In Favor Of ",
        "Style Of Case ",
    )

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=600.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "court",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": BASE,
            "terms_url": "https://jpwebsite.harriscountytx.gov/PublicExtracts/search.jsp",
            "terms_summary": (
                "Harris County Justice Courts Public Data Extract, civil 'Judgments Entered'; "
                "free, no login; no license or terms published (robots.txt has no Disallow). "
                "Used on the project owner's decision (2026-11-23)."
            ),
            "terms_checked_on": "2026-11-23",
            "robots_checked_on": "2026-11-23",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        today = datetime.now(UTC).date()
        lo = FIRST
        while lo <= today:
            hi = min(lo + timedelta(days=WINDOW_DAYS - 1), today)
            yield {"from": lo.isoformat(), "to": hi.isoformat()}
            lo = hi + timedelta(days=1)

    def fetch(self, request: FetchRequest) -> Fetched:
        lo = date.fromisoformat(request.params["from"])  # parsed dates only reach the URL
        hi = date.fromisoformat(request.params["to"])
        if (hi - lo).days >= EXTRACT_LIMIT_DAYS or hi < lo:
            raise ValueError("window must be 1 to 90 days")
        params = {"extractCaseType": "CV", "extract": "3", "court": "300",
                  "casetype": CASE_TYPES, "format": "csv",
                  "fdate": lo.strftime("%m/%d/%Y"), "tdate": hi.strftime("%m/%d/%Y")}  # fmt: skip
        resp = self.client.get(BASE, params)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status}")
        text = resp.content.decode("utf-8-sig", errors="replace")
        rows = list(csv.DictReader(io.StringIO(text)))
        limit = request.params.get("limit")
        if limit:
            rows = rows[: int(limit)]
        return Fetched(self.source_id, f"{BASE}?from={lo}&to={hi}", resp.retrieved_at, 200,
                       canonical_json({"rows": rows}), "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        seen: set[str] = set()
        for r in sorted(json.loads(fetched.content).get("rows") or [], key=canonical_json):
            case = _field(r, "Case Number")
            against, favor = _field(r, "Judgment Against"), _field(r, "Judgment In Favor Of")
            amount = _money(_field(r, "Judgment Amount"))
            when = _date(_field(r, "Judgment Date"))
            if not (case and against and amount and when):
                continue
            key = f"{case}|{when.isoformat()}|{clean(against)}"
            if key in seen:
                continue
            seen.add(key)
            ctx = RecordContext(fetched, COUNTY, key, "jp_judgment", r)
            uid = stable_id(self.source_id, "judgment", key)
            yield ctx.source_record()
            case_type = _field(r, "Case Type") or "Civil"
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=case, book_type=None,
                book=None, page=None, doc_type_raw=f"Justice court judgment: {case_type}",
                doc_type="COURT_ORDER", recorded_on=when, recorded_seq=None, executed_on=None,
                consideration=None, principal_amount=amount, max_secured_amount=None,
                maturity_date=None, amount_source="index",
                legal_desc_raw=_field(r, "Judgment Text"),
            )  # fmt: skip
            addr = None
            for who in ("Defendant", "Second Defendant"):
                if clean(_field(r, f"{who} Name") or "") == clean(against):
                    addr = _addr(r, who)
                    break
            parties = [("debtor", against, addr)]
            if favor:
                plaintiff = clean(_field(r, "Plaintiff Name") or "") == clean(favor)
                parties.append(("creditor", favor, _addr(r, "Plaintiff") if plaintiff else None))
            for seq, (role, name, a) in enumerate(parties, start=1):
                if a is not None:
                    yield NormalizedRow("address", a)
                nc = classify(name)
                party_id = stable_id(self.source_id, key, role, clean(name))
                yield ctx.fact("party", party_id=party_id, raw_name=name,
                               party_kind=nc.party_kind, org_form=nc.org_form,
                               org_name_norm=nc.org_name_norm,
                               address_id=a["address_id"] if a else None)  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=party_id,
                               role=role, seq=seq)  # fmt: skip

    def health(self) -> HealthReport:
        today = datetime.now(UTC).date()
        f = self.fetch(FetchRequest({"from": (today - timedelta(days=7)).isoformat(),
                                     "to": today.isoformat()}))  # fmt: skip
        n = len(json.loads(f.content)["rows"])
        return HealthReport(self.source_id, n > 0, datetime.now(UTC), f"{n} rows last 7 days")
