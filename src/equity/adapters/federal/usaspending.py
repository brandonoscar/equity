"""Federal award recipients (contracts, grants, loans, direct payments, other assistance) from
USAspending.gov, with the recipient's name, UEI/DUNS, parent and street address.

USAspending publishes every prime award a federal agency reports under the DATA Act. No
published file lists recipients with their addresses (the recipient API gives an address only
one recipient at a time), so this source asks the official custom award download API
(POST /api/v2/download/awards/, then /api/v2/download/status until the generated zip on
files.usaspending.gov is ready) for prime award summaries, only the COLUMNS it needs, and
groups the award rows by recipient. One recipient within one partition is one record:

  source_record  the recipient's award rows in the partition (record_type
                 federal_award_recipient): award ids, type, obligated / outlayed / face value
                 amounts, dates, awarding agency, NAICS / CFDA, exactly as downloaded
  business       the recipient: sos_id USAS:<record key>, name, principal address = the
                 recipient address on its latest award, valid over the partition's window
  party          the recipient (with its address), its parent recipient (when a different
                 entity), and the highly compensated officers named on its awards
  business_role  recipient -> 'other' RECIPIENT, parent -> 'other' PARENT RECIPIENT,
                 officers -> 'officer' HIGHLY COMPENSATED OFFICER
  address        the normalized recipient address

The record key is FY<fy>/<award type>/<state>[/<month>]/UEI-<uei> (else DUNS-<duns>, else a
hash of the name and address): recipient identifiers are public registration numbers.

Partitions: fiscal year (FY2008 on: the API's search floor) x award type group (contracts,
idvs, grants, direct_payments, loans, other) x recipient state, over the awards that *began*
in the window (time_period date_type new_awards_only), so every award is in one partition
only. The award counts endpoint sizes each partition first; a partition over SPLIT_AT awards
is split into its twelve months. Amounts are each award's lifetime totals as of the download.

Skipped: aggregate records (record_type_code 1: payments to individuals summed by county) and
individual recipients (record_type_code 3: names redacted for privacy), and any recipient
named REDACTED / MULTIPLE RECIPIENTS; recipients outside the U.S. states and territories.

Source: https://api.usaspending.gov (U.S. Treasury, Bureau of the Fiscal Service; public data
under the DATA Act, free, no API key, no login). api.usaspending.gov has no robots.txt (404:
no restrictions) and files.usaspending.gov serves no robots rules.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.sba_chargeoffs import _day, _text
from equity.adapters.http import PoliteClient, PostTransport, Response, _urlopen
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.geo import county_by_fips
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

API = "https://api.usaspending.gov"
DOWNLOAD = f"{API}/api/v2/download/awards/"
STATUS = f"{API}/api/v2/download/status"
COUNT = f"{API}/api/v2/search/spending_by_award_count/"
AWARD_TYPES = f"{API}/api/v2/references/award_types/"
TERMS = "https://www.usaspending.gov/about"

FIRST_FY = 2008
SPLIT_AT = 100_000  # awards per partition before it is split by month
MAX_ROWS = 500_000  # the download API's row limit: a partition that hits it is refused
POLL_S = 15.0
MAX_POLLS = 480  # two hours of polling for one generated file

# /api/v2/references/award_types/, read 2026-11-25. Group names follow the counts endpoint.
GROUPS: dict[str, tuple[str, ...]] = {
    "contracts": ("A", "B", "C", "D"),
    "idvs": ("IDV_A", "IDV_B", "IDV_B_A", "IDV_B_B", "IDV_B_C", "IDV_C", "IDV_D", "IDV_E"),
    "grants": ("02", "03", "04", "05", "F001", "F002"),
    "direct_payments": ("06", "10", "F006", "F007"),
    "loans": ("07", "08", "F003", "F004"),
    "other": ("09", "11", "-1", "F005", "F008", "F009", "F010"),
}
# The 50 states, DC and the inhabited territories (USPS codes, as recipient_state_code).
STATES = (
    "AK", "AL", "AR", "AS", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "GU", "HI", "IA",
    "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MP", "MS", "MT",
    "NC", "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "PR", "RI", "SC",
    "SD", "TN", "TX", "UT", "VA", "VI", "VT", "WA", "WI", "WV", "WY",
)  # fmt: skip
OFFICERS = tuple(f"highly_compensated_officer_{n}_name" for n in range(1, 6))
# Columns asked of the download. A request naming a column its award family's file lacks
# fails ("An error occurred."), so contracts/IDVs and assistance each get their own list
# (column names checked against full downloads, 2026-11-25).
_COMMON = (
    "total_obligated_amount", "total_outlayed_amount", "award_base_action_date",
    "award_latest_action_date", "period_of_performance_start_date",
    "period_of_performance_current_end_date", "awarding_agency_name",
    "awarding_sub_agency_name", "funding_agency_name", "recipient_uei", "recipient_duns",
    "recipient_name", "recipient_name_raw", "recipient_parent_uei", "recipient_parent_duns",
    "recipient_parent_name", "recipient_country_code", "recipient_address_line_1",
    "recipient_address_line_2", "recipient_city_name", "recipient_county_name",
    "prime_award_summary_recipient_county_fips_code", "recipient_state_code",
    *(c for n in range(1, 6) for c in (f"highly_compensated_officer_{n}_name",
                                      f"highly_compensated_officer_{n}_amount")),
)  # fmt: skip
CONTRACT_COLUMNS = (
    "contract_award_unique_key", "award_id_piid", "parent_award_id_piid", "award_type_code",
    "award_type", "current_total_value_of_award", "potential_total_value_of_award",
    "recipient_doing_business_as_name", "cage_code", "recipient_parent_name_raw",
    "recipient_zip_4_code", "naics_code", "naics_description", "product_or_service_code",
    *_COMMON,
)  # fmt: skip
ASSISTANCE_COLUMNS = (
    "assistance_award_unique_key", "award_id_fain", "award_id_uri", "assistance_type_code",
    "assistance_type_description", "total_face_value_of_loan", "total_loan_subsidy_cost",
    "total_non_federal_funding_amount", "recipient_zip_code", "recipient_zip_last_4_code",
    "business_types_code", "business_types_description", "record_type_code",
    "cfda_numbers_and_titles", *_COMMON,
)  # fmt: skip
COLUMNS = tuple(dict.fromkeys((*CONTRACT_COLUMNS, *ASSISTANCE_COLUMNS)))
CONTRACT_GROUPS = frozenset({"contracts", "idvs"})
SKIP_RECORD_TYPES = frozenset({"1", "3"})  # county aggregates; redacted individuals
REDACTED = re.compile(r"REDACTED|MULTIPLE RECIPIENTS|MULTIPLE FOREIGN RECIPIENTS|"
                      r"MISCELLANEOUS FOREIGN AWARDEES|PRIVATE INDIVIDUAL", re.I)  # fmt: skip


def json_post_transport(
    url: str, headers: Mapping[str, str], body: bytes, timeout: float
) -> tuple[int, bytes, str]:
    return _urlopen(url, {**headers, "Content-Type": "application/json"}, body, timeout)


@dataclass
class JsonClient(PoliteClient):
    """PoliteClient plus a JSON POST (same robots.txt, spacing and retry rules)."""

    json_transport: PostTransport = json_post_transport

    def post_json(self, url: str, obj: Any) -> Response:
        body = canonical_json(obj)
        return self._send(url, lambda hdrs: self.json_transport(url, hdrs, body,
                                                                self.timeout_s))  # fmt: skip


def fiscal_year(day: date) -> int:
    return day.year + 1 if day.month >= 10 else day.year


def window(fy: int, month: str | None = None) -> tuple[date, date]:
    """(first, last day) of a fiscal year, or of one month 'YYYY-MM' in it."""
    if month is None:
        return date(fy - 1, 10, 1), date(fy, 9, 30)
    y, m = (int(x) for x in month.split("-"))
    first = date(y, m, 1)
    if fiscal_year(first) != fy:
        raise ValueError(f"{month} is not in FY{fy}")
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def months(fy: int) -> list[str]:
    return [f"{fy - 1 if m >= 10 else fy}-{m:02d}" for m in (*range(10, 13), *range(1, 10))]


def filters(fy: int, group: str, state: str, month: str | None = None) -> dict[str, Any]:
    first, last = window(fy, month)
    return {
        "time_period": [{"start_date": first.isoformat(), "end_date": last.isoformat(),
                         "date_type": "new_awards_only"}],
        "award_type_codes": list(GROUPS[group]),
        "recipient_locations": [{"country": "USA", "state": state}],
    }  # fmt: skip


def columns_for(group: str) -> tuple[str, ...]:
    return CONTRACT_COLUMNS if group in CONTRACT_GROUPS else ASSISTANCE_COLUMNS


def prime_rows(content: bytes, keep: tuple[str, ...] = COLUMNS) -> list[dict[str, Any]]:
    """The prime award summary rows of a generated download zip, only `keep` columns, each
    tagged with its file (contracts | assistance). Sub-award files are ignored."""
    out: list[dict[str, Any]] = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for member in sorted(z.namelist()):
            base = member.rsplit("/", 1)[-1]
            if "PrimeAwardSummaries" not in base or not base.endswith(".csv"):
                continue
            kind = "contracts" if base.startswith("Contracts") else "assistance"
            with z.open(member) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
                for row in csv.DictReader(text):
                    kept = {k: (row.get(k) or "").strip() or None for k in keep if k in row}
                    out.append({"file": kind, **kept})
    return out


def redacted(row: Mapping[str, Any]) -> bool:
    name = _text(row.get("recipient_name")) or _text(row.get("recipient_name_raw"))
    rtype = str(row.get("record_type_code") or "").strip()
    return name is None or rtype in SKIP_RECORD_TYPES or REDACTED.search(name) is not None


def recipient_key(row: Mapping[str, Any], source_id: str) -> str:
    if uei := _text(row.get("recipient_uei")):
        return f"UEI-{uei.upper()}"
    if duns := _text(row.get("recipient_duns")):
        return f"DUNS-{duns}"
    parts = (row.get(k) or "" for k in ("recipient_name", "recipient_address_line_1",
                                        "recipient_city_name", "recipient_zip_code",
                                        "recipient_zip_4_code"))  # fmt: skip
    return "H-" + stable_id(source_id, *(clean(str(p)) for p in parts))[:20]


class USASpendingRecipients(Adapter):
    source_id: ClassVar[str] = "us.usaspending.recipients"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = (
        "recipient_name", "recipient_name_raw", "recipient_doing_business_as_name",
        "recipient_parent_name", "recipient_parent_name_raw", "recipient_address_line_1",
        "recipient_address_line_2", *OFFICERS,
    )  # fmt: skip

    def __init__(self, client: JsonClient | None = None) -> None:
        self.client = client or JsonClient(min_interval_s=2.0, timeout_s=900.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "federal_loan",
            "jurisdiction": "US",
            "access_method": "api",
            "base_url": API,
            "terms_url": TERMS,
            "terms_summary": (
                "USAspending.gov prime award data (contracts, grants, loans, other "
                "assistance), public U.S. government data under the DATA Act; free, no API "
                "key or login. Custom award download API; no robots.txt restrictions."
            ),
            "terms_checked_on": "2026-11-25",
            "robots_checked_on": "2026-11-25",
            "cost_model": "free",
        }

    # planning ----------------------------------------------------------------------------

    def counts(self, fy: int, state: str, month: str | None = None) -> dict[str, int]:
        f = filters(fy, "contracts", state, month)
        del f["award_type_codes"]
        resp = self.client.post_json(COUNT, {"filters": f})
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {COUNT}")
        results = json.loads(resp.content).get("results") or {}
        return {g: int(results.get(g) or 0) for g in GROUPS}

    def partitions(self) -> Iterator[dict[str, str]]:
        last_fy = fiscal_year(datetime.now(UTC).date())
        for fy in range(FIRST_FY, last_fy + 1):
            for state in STATES:
                for group, n in self.counts(fy, state).items():
                    base = {"fy": str(fy), "award_type": group, "state": state}
                    if n == 0:
                        continue
                    if n <= SPLIT_AT:
                        yield base
                    else:
                        for m in months(fy):
                            yield {**base, "month": m}

    # fetching ----------------------------------------------------------------------------

    def _generated(self, body: Mapping[str, Any]) -> tuple[str, Response]:
        """Ask for a download, wait for it, and return (file url, the zip)."""
        resp = self.client.post_json(DOWNLOAD, body)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {DOWNLOAD}: {resp.content[:200]!r}")
        job = json.loads(resp.content)
        name, url = str(job["file_name"]), str(job["file_url"])
        for _ in range(MAX_POLLS):
            st = self.client.get(STATUS, {"file_name": name})
            if st.status != 200:
                raise RuntimeError(f"HTTP {st.status} from {STATUS}")
            info = json.loads(st.content)
            if info.get("status") == "finished":
                url = str(info.get("file_url") or url)
                break
            if info.get("status") == "failed":
                raise RuntimeError(f"download {name} failed: {info.get('message')}")
            self.client.sleep(POLL_S)
        else:
            raise RuntimeError(f"download {name} not ready after {MAX_POLLS} polls")
        got = self.client.get(url)
        if got.status != 200:
            raise RuntimeError(f"HTTP {got.status} from {url}")
        return url, got

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: fy, award_type (a GROUPS key), state, month (YYYY-MM, optional); limit
        (fixtures: the first rows only)."""
        p = request.params
        fy, group, state, month = int(p["fy"]), p["award_type"], p["state"].upper(), p.get("month")
        if group not in GROUPS:
            raise ValueError(f"unknown award_type {group!r}")
        if state not in STATES:
            raise ValueError(f"unknown state {state!r}")
        limit = int(p["limit"]) if "limit" in p else MAX_ROWS
        body = {"filters": filters(fy, group, state, month), "columns": list(columns_for(group)),
                "file_format": "csv", "limit": limit}  # fmt: skip
        url, got = self._generated(body)
        rows = prime_rows(got.content)
        if "limit" not in p and len(rows) >= MAX_ROWS:
            raise RuntimeError(f"FY{fy} {group} {state} {month or ''}: {len(rows)} rows hit the "
                               "download limit; split the partition")  # fmt: skip
        first, last = window(fy, month)
        out = {"fy": fy, "award_type": group, "state": state, "month": month,
               "start_date": first.isoformat(), "end_date": last.isoformat(), "url": url,
               "rows": rows[:limit]}  # fmt: skip
        return Fetched(self.source_id, url, got.retrieved_at, 200, canonical_json(out),
                       "application/json")  # fmt: skip

    # normalizing -------------------------------------------------------------------------

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        today = fetched.retrieved_at.astimezone(UTC).date()
        fy, group, state = int(data["fy"]), str(data["award_type"]), str(data["state"])
        month = data.get("month")
        first, last = window(fy, month)
        valid_from = min(first, today)
        valid_to = last if last <= today else None
        part = f"FY{fy}/{group}/{state}" + (f"/{month}" if month else "")
        by_key: dict[str, list[dict[str, Any]]] = {}
        for r in data.get("rows") or []:
            if not redacted(r):
                by_key.setdefault(recipient_key(r, self.source_id), []).append(r)
        for rkey in sorted(by_key):
            rows = sorted(by_key[rkey], key=canonical_json)
            yield from self._recipient(fetched, f"{part}/{rkey}", rows, state, valid_from,
                                       valid_to)  # fmt: skip

    def _recipient(
        self,
        fetched: Fetched,
        record_key: str,
        rows: list[dict[str, Any]],
        state: str,
        valid_from: date,
        valid_to: date | None,
    ) -> Iterator[NormalizedRow]:
        rep = max(rows, key=lambda r: (str(r.get("award_latest_action_date") or ""),
                                       canonical_json(r)))  # fmt: skip
        name = _text(rep.get("recipient_name")) or _text(rep.get("recipient_name_raw"))
        assert name is not None  # redacted() dropped nameless rows
        st = _text(rep.get("recipient_state_code")) or state
        juris = st
        fips = str(rep.get("prime_award_summary_recipient_county_fips_code") or "").strip()
        if len(fips) == 5 and fips.isdigit():
            try:
                juris = county_by_fips(st, fips).fips5
            except KeyError:
                juris = st
        ctx = RecordContext(fetched, juris, record_key, "federal_award_recipient", rows)
        yield ctx.source_record()
        zip_ = str(rep.get("recipient_zip_code") or rep.get("recipient_zip_4_code") or "")[:5]
        addr = normalized_address(_text(rep.get("recipient_address_line_1")),
                                  _text(rep.get("recipient_city_name")), st,
                                  zip_ if len(zip_) == 5 and zip_.isdigit() else None)  # fmt: skip
        if addr is not None:
            yield NormalizedRow("address", addr)
        sos_id = f"USAS:{record_key}"
        nc = classify(name)
        latest = _day(rep.get("award_latest_action_date"))
        today = fetched.retrieved_at.astimezone(UTC).date()
        yield ctx.fact(
            "business", sos_id=sos_id, name=name, org_form=nc.org_form, status=None,
            formed_on=None,
            status_date=latest if latest is not None and latest <= today else None,
            principal_address_id=None if addr is None else addr["address_id"],
            mailing_address_id=None, valid_from=valid_from, valid_to=valid_to,
        )  # fmt: skip
        holders: list[tuple[str, str, str, dict[str, Any] | None]] = [
            ("recipient", "RECIPIENT", name, addr)
        ]
        parent = _text(rep.get("recipient_parent_name")) or _text(
            rep.get("recipient_parent_name_raw")
        )
        uei, parent_uei = _text(rep.get("recipient_uei")), _text(rep.get("recipient_parent_uei"))
        if parent and not REDACTED.search(parent) and clean(parent) != clean(name) and (
                parent_uei is None or parent_uei != uei):  # fmt: skip
            holders.append(("parent", "PARENT RECIPIENT", parent, None))
        officers = sorted({o for r in rows for c in OFFICERS if (o := _text(r.get(c)))})
        holders += [("officer", "HIGHLY COMPENSATED OFFICER", o, None) for o in officers]
        seen: set[str] = set()
        for kind, title, who, where in holders:
            party_id = stable_id(self.source_id, record_key, kind, clean(who))
            if party_id in seen:
                continue
            seen.add(party_id)
            pc = classify(who)
            yield ctx.fact(
                "party", party_id=party_id, raw_name=who, party_kind=pc.party_kind,
                org_form=pc.org_form, org_name_norm=pc.org_name_norm,
                address_id=None if where is None else where["address_id"],
            )  # fmt: skip
            yield ctx.fact("business_role", sos_id=sos_id, party_id=party_id,
                           role="officer" if kind == "officer" else "other", title=title,
                           valid_from=valid_from, valid_to=valid_to)  # fmt: skip

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            resp = self.client.get(AWARD_TYPES)
            groups = json.loads(resp.content) if resp.status == 200 else {}
        except (OSError, ValueError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        shape = tuple(sorted(groups)) if isinstance(groups, dict) else ()
        ok = {"contracts", "grants", "loans"} <= set(shape)
        return HealthReport(self.source_id, ok, now, "ok" if ok else f"shape={list(shape)}",
                            shape)  # fmt: skip
