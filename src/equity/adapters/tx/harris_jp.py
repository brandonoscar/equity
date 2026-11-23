"""Harris County (TX) Justice Courts: civil judgments from the "Judgments Entered" extract.

The JP Public Data Extract Service (config/courts_state/tx.harris.jp.civil_judgments.yaml)
returns, for a judgment-date window, one CSV row per judgment entered in any of the 16 JP
courts: case number, court, case type, filing date, the first two plaintiffs and defendants
with their addresses, and the judgment's text, date, in favor of, against, amount, attorney
fees, court costs and post-judgment rate.

Kept: rows of the configured case types (debt claims, small claims, evictions...). Each
case in a window becomes one court_case and its parties (with addresses); each listed
judgment text that awards money becomes a judgment row.

Who won is read from "Judgment In Favor Of" / "Judgment Against" (names such as
"Doe, Ann and others"): their words are compared with the plaintiffs' and defendants' names.
When every money judgment of the case went the same way, the winning side's parties get
role 'creditor' and the losing side's 'debtor' (normally plaintiff -> creditor, defendant ->
debtor; a counterclaim won by the defendant flips them). When it cannot be told, or the
case's judgments went both ways (the extract then repeats the case once per pairing), the
parties keep 'plaintiff'/'defendant' and no debtor is named.

Money: principal is the judgment amount; costs are court costs plus attorney's fees; rate is
the post-judgment rate as a fraction (6.75 -> 0.0675). The pre-judgment column is left out:
it sometimes holds dollar amounts, not rates.

Partitions are half months of judgment date, newest first (the form allows up to 90 days
per request, but a whole month can outlast the server's 100 s gateway timeout).
A case with judgments in two months appears in both months' parts.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, timedelta
from decimal import Decimal, InvalidOperation
from functools import cache
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

CONFIG = "courts_state/tx.harris.jp.civil_judgments.yaml"
COUNTY = "48201"
HEADER = "Case Number"
# (role, name column, address column prefix) for the four parties the layout carries.
SIDES: dict[str, tuple[tuple[str, str], ...]] = {
    "plaintiff": (("Plaintiff Name", "Plaintiff Addr"),
                  ("Second Plaintiff Name", "Second Plaintiff Addr")),
    "defendant": (("Defendant Name", "Defendant Addr"),
                  ("Second Defendant Name", "Second Defendant Addr")),
}  # fmt: skip
NAME_COLUMNS = tuple(c for side in SIDES.values() for c, _ in side)
# Columns with names or street lines: pseudonymized in fixtures (the repo is public).
PII_FIELDS: tuple[str, ...] = (
    *NAME_COLUMNS, "Style Of Case", "Judgment In Favor Of", "Judgment Against",
    *(f"{p} Line {n}" for _, p in (s for side in SIDES.values() for s in side) for n in (1, 2)),
    *(f"{w}Atty Name" for w in ("Plaintiff ", "Defendant ", "Second Plaintiff ",
                                 "Second Defendant ")),
    *(f"{w}Atty Addr {n}" for w in ("Plaintiff ", "Defendant ", "Second Plaintiff ",
                                    "Second Defendant ") for n in (1, 2)),
)  # fmt: skip
_COURT = re.compile(r"Precinct\s+(\d+),\s*Place\s+(\d+)", re.IGNORECASE)
_WORD = re.compile(r"[A-Z0-9]+")
# Words that say nothing about which side a name is on.
_FILLER = frozenset({"AND", "OTHERS", "OTHER", "ALL", "OCCUPANTS", "OCCUPANT", "CURRENT", "THE",
                     "OF", "LLC", "INC", "LP", "LTD", "CO", "CORP", "DBA", "D", "B", "A",
                     "AKA", "JR", "SR", "II", "III"})  # fmt: skip
# "John Doe and all other occupants" / "Jane Roe & All Occupants": the tenant is the party.
_OCCUPANTS = re.compile(
    r"[\s,]*(?:and|&)\s+(?:all\s+)?(?:other\s+|current\s+)?occupants?\.?\s*$", re.IGNORECASE
)
# Rewritten by scrub_fixture from the scrubbed party names.
_DERIVED = frozenset({"Judgment In Favor Of", "Judgment Against", "Style Of Case"})
_NO_ADDRESS = frozenset({"", "UNKNOWN", "NONE", "N/A", "NA"})


@dataclass(frozen=True)
class JPConfig:
    source_id: str
    base_url: str
    extract: str
    court: str
    case_type_codes: str
    first_month: date
    case_types: frozenset[str]
    judgment_types: Mapping[str, str]
    costs_only_counts: bool
    terms: Mapping[str, Any]


@cache
def load_config() -> JPConfig:
    import yaml

    d = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    y, m = (int(x) for x in str(d["first_month"]).split("-")[:2])
    return JPConfig(
        source_id=d["source_id"],
        base_url=d["base_url"],
        extract=str(d["extract"]),
        court=str(d["court"]),
        case_type_codes=str(d["case_type_codes"]),
        first_month=date(y, m, 1),
        case_types=frozenset(d["case_types"]),
        judgment_types=dict(d["judgment_types"]),
        costs_only_counts=bool(d["costs_only_counts"]),
        terms=dict(d["terms"]),
    )


# -- parsing helpers -----------------------------------------------------------------------
def us_date(value: str | None) -> date | None:
    """'10/05/2026' -> date; blank or malformed -> None."""
    parts = (value or "").strip().split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    try:
        return date(int(parts[2]), int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def money(value: str | None) -> Decimal | None:
    """'1118.2900' -> Decimal('1118.29'); blank, malformed or negative -> None."""
    text = (value or "").strip().replace(",", "").replace("$", "")
    if not text:
        return None
    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return amount if amount >= 0 else None


def rate(value: str | None) -> Decimal | None:
    """Post-judgment rate in percent -> fraction ('6.7500' -> 0.0675); 0 or blank -> None."""
    pct = money(value)
    if pct is None or pct == 0 or pct >= 100:
        return None
    return (pct / 100).quantize(Decimal("0.000001"))


def court_id(raw: str) -> str:
    """'Precinct 5, Place 1' -> 'tx.harris.jp.5-1'."""
    m = _COURT.search(raw or "")
    if m is None:
        return "tx.harris.jp." + (clean(raw).lower().replace(" ", "_") or "unknown")
    return f"tx.harris.jp.{int(m.group(1))}-{int(m.group(2))}"


def case_norm(raw: str) -> str:
    return re.sub(r"\s+", "", raw.upper())


def case_uid(raw: str) -> str:
    """Case numbers identify a case across all JP courts (the file layout says so)."""
    return f"tx.harris.jp:{case_norm(raw)}"


def party_name(raw: str) -> str:
    """'Ann Doe and All Other Occupants' -> 'Ann Doe'; spaces collapsed."""
    text = " ".join((raw or "").split())
    return _OCCUPANTS.sub("", text).strip(" ,") or text


def name_words(text: str) -> frozenset[str]:
    return frozenset(_WORD.findall(clean(text or ""))) - _FILLER


def winner(row: Mapping[str, str]) -> str | None:
    """'plaintiff' or 'defendant': the side named in favor of (and not against), by words."""
    pl = frozenset[str]().union(*(name_words(row.get(c, "")) for c, _ in SIDES["plaintiff"]))
    df = frozenset[str]().union(*(name_words(row.get(c, "")) for c, _ in SIDES["defendant"]))
    favor = name_words(row.get("Judgment In Favor Of", ""))
    against = name_words(row.get("Judgment Against", ""))
    for_pl = len(favor & pl - df) + len(against & df - pl)
    for_df = len(favor & df - pl) + len(against & pl - df)
    if for_pl > for_df:
        return "plaintiff"
    if for_df > for_pl:
        return "defendant"
    return None


def address(row: Mapping[str, str], prefix: str) -> dict[str, Any] | None:
    lines = [" ".join(row.get(f"{prefix} Line {n}", "").split()) for n in (1, 2)]
    street = " ".join(x for x in lines if x.upper() not in _NO_ADDRESS) or None
    city = " ".join(row.get(f"{prefix} City", "").split())
    state = row.get(f"{prefix} State", "").strip()
    zip5 = row.get(f"{prefix} Zip", "").strip()[:5]
    return normalized_address(
        street,
        None if city.upper() in _NO_ADDRESS else city,
        state or None,
        zip5 if zip5.isdigit() and len(zip5) == 5 and zip5 != "00000" else None,
    )


def read_rows(text: str) -> list[dict[str, str]]:
    """The extract's CSV as dicts keyed by the stripped header names."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿"), newline=""))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        return []
    if not header or header[0] != HEADER:
        raise ValueError(f"not a JP extract (first column {header[:1]!r})")
    return [dict(zip(header, rec, strict=False)) for rec in reader if any(rec)]


def months(first: date, last: date) -> Iterator[tuple[date, date]]:
    """Calendar-month windows [from, to] covering first..last (last window ends at last)."""
    start = first.replace(day=1)
    while start <= last:
        nxt = (start + timedelta(days=32)).replace(day=1)
        yield start, min(nxt - timedelta(days=1), last)
        start = nxt


class HarrisJPCivilJudgments(Adapter):
    source_id: ClassVar[str] = "tx.harris.jp.civil_judgments"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = PII_FIELDS

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.config = load_config()
        self.client = client or PoliteClient(
            min_interval_s=5.0, timeout_s=900.0, retries=4, backoff_s=15.0
        )

    def source_row(self) -> Mapping[str, Any]:
        t = self.config.terms
        return {
            "source_id": self.source_id,
            "kind": "court",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": self.config.base_url,
            "terms_url": t["url"],
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t["robots_checked_on"],
            "cost_model": t["cost_model"],
        }

    # -- fetching -----------------------------------------------------------------------
    def partitions(self) -> Iterator[dict[str, str]]:
        """Half months, newest first, so a build stopped part-way has the most recent years.
        (A whole month, ~7,300 rows, can take the server longer than the 100 s its Cloudflare
        front waits: HTTP 522.)"""
        yesterday = self.client.now().astimezone(UTC).date() - timedelta(days=1)
        for start, end in reversed(list(months(self.config.first_month, yesterday))):
            yield from self.split_partition({"from": start.isoformat(), "to": end.isoformat()})

    def split_partition(self, params: Mapping[str, str]) -> list[dict[str, str]]:
        """A window cut in two at its middle day, newer half first (lake replan)."""
        start, end = date.fromisoformat(params["from"]), date.fromisoformat(params["to"])
        if start == end:
            return [dict(params)]
        mid = start + (end - start) // 2
        halves = [(mid + timedelta(days=1), end), (start, mid)]
        return [{**params, "from": a.isoformat(), "to": b.isoformat()} for a, b in halves]

    def _params(self, start: date, end: date) -> dict[str, str]:
        c = self.config
        return {"extractCaseType": "CV", "extract": c.extract, "court": c.court,
                "casetype": c.case_type_codes, "format": "csv",
                "fdate": start.strftime("%m/%d/%Y"), "tdate": end.strftime("%m/%d/%Y")}  # fmt: skip

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: from, to (ISO dates, at most 90 days apart); limit (fixtures): first N rows."""
        p = request.params
        start, end = date.fromisoformat(p["from"]), date.fromisoformat(p["to"])
        if not timedelta(0) <= end - start < timedelta(days=90):
            raise ValueError(f"window {start}..{end}: the extract allows 1 to 90 days")
        url = self.config.base_url + "GetExtractData"
        resp = self.client.get(url, self._params(start, end))
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {resp.url}")
        # Blank columns are dropped (about half of the 70 per row): lossless, half the size.
        rows = [{k: v for k, v in r.items() if v.strip()}
                for r in read_rows(resp.content.decode("utf-8", errors="replace"))]  # fmt: skip
        if "limit" in p:
            rows = rows[: int(p["limit"])]
        body = canonical_json({"from": start.isoformat(), "to": end.isoformat(), "rows": rows})
        return Fetched(self.source_id, resp.url, resp.retrieved_at, 200, body, "application/json")

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        """Pseudonyms for every name and street line. In favor of / against are rewritten
        from the pseudonymized parties of the side they named, so tests still see who won."""
        from equity.adapters.record import pseudonym  # the recorder imports the registry

        data = json.loads(content)
        for row in data["rows"]:
            won = winner(row)
            for col in PII_FIELDS:
                if not row.get(col, "").strip() or col in _DERIVED:
                    continue
                row[col] = pseudonym("ADDRESS" if "Addr" in col else col, row[col])
            names = {side: " and ".join(row[c] for c, _ in cols if row.get(c, "").strip())
                     for side, cols in SIDES.items()}  # fmt: skip
            for col in sorted(_DERIVED):
                if not row.get(col, "").strip():
                    continue
                if col == "Style Of Case":
                    row[col] = f"{names['plaintiff'] or 'TESTOWNER'} vs. {names['defendant']}"
                elif won is None:
                    row[col] = pseudonym(col, row[col])
                else:
                    lost = "defendant" if won == "plaintiff" else "plaintiff"
                    side = won if col == "Judgment In Favor Of" else lost
                    row[col] = names[side] or pseudonym(col, row[col])
        return canonical_json(data)

    def health(self) -> HealthReport:
        """Live: yesterday's judgments come back as a JP extract."""
        day = self.client.now().astimezone(UTC).date() - timedelta(days=1)
        try:
            f = self.fetch(FetchRequest({"from": day.isoformat(), "to": day.isoformat()}))
        except (ValueError, RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, self.client.now(), repr(exc))
        rows = json.loads(f.content)["rows"]
        shape = tuple(sorted(rows[0])) if rows else ()
        return HealthReport(self.source_id, True, self.client.now(), f"{len(rows)} rows on {day}",
                            shape)  # fmt: skip

    # -- normalizing --------------------------------------------------------------------
    def judgment_rows(self, rows: list[dict[str, str]], today: date) -> list[dict[str, Any]]:
        """Money judgments of one case: distinct by (date, text, amounts), with who won."""
        cfg = self.config
        found: dict[tuple[Any, ...], dict[str, Any]] = {}
        for r in rows:
            jtype = cfg.judgment_types.get(" ".join(r.get("Judgment Text", "").split()))
            entered = us_date(r.get("Judgment Date"))
            if jtype is None or entered is None or entered > today:
                continue
            amount = money(r.get("Judgment Amount"))
            fees, court_costs = money(r.get("Attorney Fees")), money(r.get("Court Costs"))
            costs = None if fees is None and court_costs is None else (
                (fees or Decimal(0)) + (court_costs or Decimal(0)))  # fmt: skip
            if not (amount or (costs and (cfg.costs_only_counts or fees))):
                continue
            key = (entered, jtype, amount, costs, rate(r.get("Post-Judg Int Rate")))
            j = found.setdefault(key, {"winners": set()})
            j["winners"].add(winner(r))
        return [
            {"entered_on": k[0], "judgment_type": k[1], "principal": k[2], "costs": k[3],
             "rate": k[4], "winners": v["winners"]}
            for k, v in sorted(found.items(), key=lambda kv: canonical_json(
                [str(x) for x in kv[0]]))
        ]  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = self.config
        rows: list[dict[str, str]] = json.loads(fetched.content)["rows"]
        today = fetched.retrieved_at.astimezone(UTC).date()
        by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in rows:
            if r.get(HEADER, "").strip() and r.get("Case Type", "").strip() in cfg.case_types:
                by_case[case_norm(r[HEADER])].append(r)
        for norm in sorted(by_case):
            group = sorted(by_case[norm], key=canonical_json)
            first = group[0]
            uid = case_uid(norm)
            ctx = RecordContext(fetched, COUNTY, norm, "jp_civil_judgment", group)
            yield ctx.source_record()
            filed = us_date(first.get("Case File Date"))
            judgments = self.judgment_rows(group, today)
            yield ctx.fact(
                "court_case", case_uid=uid, court_id=court_id(first.get("JP Court ID", "")),
                case_number_raw=first[HEADER].strip(), case_number_norm=norm,
                case_type=first.get("Case Type") or None,
                nature_of_suit=" ".join(first.get("Cause of Action", "").split()) or None,
                filed_on=filed if filed is not None and filed <= today else None,
                closed_on=None, status=" ".join(first.get("Case Status", "").split()) or None,
            )  # fmt: skip
            winners: set[str | None] = set().union(*(j["winners"] for j in judgments))
            won = next(iter(winners)) if len(winners) == 1 else None
            roles = {"plaintiff": "plaintiff", "defendant": "defendant"}
            if won is not None:
                lost = "defendant" if won == "plaintiff" else "plaintiff"
                roles = {won: "creditor", lost: "debtor"}
            seen: set[tuple[str, str]] = set()
            for side, cols in SIDES.items():
                for name_col, addr_prefix in cols:
                    raw = " ".join(first.get(name_col, "").split())
                    name = party_name(raw)
                    key = (roles[side], clean(name))
                    if not key[1] or key in seen:
                        continue
                    seen.add(key)
                    yield from self._party(ctx, uid, roles[side], name,
                                           address(first, addr_prefix))  # fmt: skip
            for j in judgments:
                suffix = (
                    f"{j['entered_on'].isoformat()}:{j['judgment_type']}:"
                    + stable_id(
                        "tx.harris.jp", str(j["principal"]), str(j["costs"]), str(j["rate"])
                    )[:8]
                )
                yield ctx.fact(
                    "judgment", judgment_uid=f"{uid}:{suffix}", case_uid=uid,
                    entered_on=j["entered_on"], principal=j["principal"], interest=None,
                    costs=j["costs"], rate=j["rate"], judgment_type=j["judgment_type"],
                    lien_instrument_uid=None,
                )  # fmt: skip

    def _party(
        self, ctx: RecordContext, uid: str, role: str, name: str, addr: dict[str, Any] | None
    ) -> Iterator[NormalizedRow]:
        if addr is not None:
            yield NormalizedRow("address", addr)
        nc = classify(name)
        party_id = stable_id(self.source_id, uid, role, clean(name))
        yield ctx.fact(
            "party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
            org_form=nc.org_form, org_name_norm=nc.org_name_norm,
            address_id=None if addr is None else addr["address_id"],
        )  # fmt: skip
        yield ctx.fact("case_party", case_uid=uid, party_id=party_id, role=role)
