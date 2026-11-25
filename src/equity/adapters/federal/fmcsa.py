"""FMCSA Company Census File: every motor carrier, broker, freight forwarder, shipper and
cargo-tank facility with a USDOT number, from the Motor Carrier Management Information System
(MCMIS), as published by the Federal Motor Carrier Safety Administration on DOT's Socrata
portal (data.transportation.gov dataset az4n-8mr2, ~4.5M rows, refreshed daily).

Kept from each row (the KEEP columns; telephone, fax, cell phone, e-mail and the Dun &
Bradstreet number are not kept): USDOT number, legal and DBA names, the company officers
(COMPANY_OFFICER_1 and _2), physical and mailing addresses with county codes, entity status
(A active, I inactive, P pending), the date added to MCMIS and the last MCS-150 filing date,
carrier operation (A interstate, B intrastate hazmat, C intrastate non-hazmat), business
organization type (1 individual, 2 partnership, 3 corporation), fleet size and power units,
truck and bus units, drivers and CDL drivers, docket (MC/MX/FF) numbers and their status,
hazmat flag, carrier/shipper classification, safety rating and its date, mileage.

What is emitted, from existing tables only:

- source_record: one per USDOT number (record_type motor_carrier); docket numbers, fleet
  counts, ratings and dates stay in the hashed raw record.
- business: sos_id USDOT:<number>, the legal name, status active / inactive / pending,
  principal address = the physical address, mailing address = the mailing address (U.S.
  only), valid from the date the carrier was added to MCMIS (else the retrieval date).
- business_role + party: each company officer (role 'officer', title COMPANY OFFICER; a
  person, name split FIRST [MIDDLE] LAST as FMCSA prints it), and for an individual carrier
  (business organization 1) its legal name as the person behind it (role 'other', title
  SOLE PROPRIETOR).
- address: the U.S. physical and mailing addresses.

Partitions: the physical state as published (every distinct PHY_STATE: U.S. states and
territories, Canadian provinces, Mexican states; 'other' when blank), from one grouped count;
a state with more than WINDOW carriers is cut into USDOT-number ranges of ~WINDOW carriers
(boundaries found with one $offset probe each), so every partition is a stable keyset window
(phy_state = X AND dot_number in [from, to)). `limit` (fixtures) keeps the first rows.

Source: https://data.transportation.gov/Trucking-and-Motorcoaches/Company-Census-File/az4n-8mr2
(U.S. DOT open data, public domain U.S. government data, free, no login, anonymous SODA API).
robots.txt (read 2026-11-25) allows /resource/ with Crawl-delay: 1, which PoliteClient
honors.
"""

from __future__ import annotations

import itertools
import json
import re
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
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
from equity.adapters.federal.cms_nppes import pseudo_digits
from equity.adapters.federal.fcc_uls import MILITARY, us_states
from equity.adapters.http import PoliteClient
from equity.adapters.person_lists import split_name
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataError, SocrataQuery, fetch_all, parse_rows, quote
from equity.geo import county_by_fips
from equity.matching.orgs import classify

PORTAL = "https://data.transportation.gov"
DATASET = "az4n-8mr2"
PAGE = f"{PORTAL}/Trucking-and-Motorcoaches/Company-Census-File/{DATASET}"
CHECKED_ON = "2026-11-25"
WINDOW = 50_000  # carriers per partition (one SODA page)
OTHER = "other"
KEEP = (
    "dot_number", "legal_name", "dba_name", "company_officer_1", "company_officer_2",
    "status_code", "add_date", "mcs150_date", "mcs150_update_code_id", "carrier_operation",
    "business_org_id", "business_org_desc", "phy_street", "phy_city", "phy_state", "phy_zip",
    "phy_cnty", "phy_country", "phy_nationality_indicator", "carrier_mailing_street",
    "carrier_mailing_city", "carrier_mailing_state", "carrier_mailing_zip",
    "carrier_mailing_cnty", "carrier_mailing_country", "carrier_mailing_und_date",
    "undeliv_phy", "fleetsize", "power_units", "truck_units", "bus_units", "total_cars",
    "total_drivers", "total_cdl", "total_intrastate_drivers", "driver_inter_total",
    "docket1prefix", "docket1", "docket1_status_code", "docket2prefix", "docket2",
    "docket2_status_code", "docket3prefix", "docket3", "docket3_status_code", "hm_ind",
    "carship", "classdef", "safety_rating", "safety_rating_date", "review_type", "review_date",
    "mcs150_mileage", "mcs150_mileage_year", "prior_revoke_flag", "prior_revoke_dot_number",
    "phy_omc_region", "safety_inv_terr",
)  # fmt: skip
OFFICERS = ("company_officer_1", "company_officer_2")
NAMES = ("legal_name", "dba_name", *OFFICERS)
STREETS = ("phy_street", "carrier_mailing_street")
STATUS = {"A": "active", "I": "inactive", "P": "pending"}
_YMD = re.compile(r"^(\d{4})-?(\d{2})-?(\d{2})")
_STATE = re.compile(r"^[A-Z0-9]{1,3}$")


def parse_day(value: Any) -> date | None:
    """YYYYMMDD (optionally followed by a time) or an ISO date."""
    m = _YMD.match(text(value) or "")
    if m is None:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def person_parts(name: str) -> dict[str, str | None]:
    """'JOHN A SMITH JR' -> first JOHN, middle A, last SMITH, suffix JR (FMCSA prints names
    first-last; 'SMITH, JOHN' is read last-first)."""
    p = split_name(name, "last_comma_first" if "," in name else "first_last")
    return {"first_name": p["first"], "middle": p["middle"], "last_name": p["last"],
            "suffix": p["suffix"]}  # fmt: skip


def is_us(country: Any) -> bool:
    return (text(country) or "US").upper() in {"US", "USA"}


def state_clause(state: str) -> str:
    return "phy_state IS NULL" if state == OTHER else f"phy_state = {quote(state)}"


def window_where(state: str, dot_from: str | None, dot_to: str | None) -> str:
    where = [state_clause(state)]
    if dot_from:
        where.append(f"dot_number >= {int(dot_from)}")
    if dot_to:
        where.append(f"dot_number < {int(dot_to)}")
    return " AND ".join(where)


class FMCSACarrierCensus(Adapter):
    source_id: ClassVar[str] = "us.fmcsa.carrier_census"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = (*NAMES, *STREETS)

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=600.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a federal registry of companies and officers
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": PAGE,
            "terms_url": PAGE,
            "terms_summary": (
                "FMCSA Company Census File (MCMIS), data.transportation.gov Socrata dataset "
                "az4n-8mr2, refreshed daily; U.S. DOT open data (public domain), free, no "
                "login, anonymous SODA API. robots.txt allows /resource/ (Crawl-delay 1). "
                "Phone, fax, e-mail and DUNS numbers are not kept."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    @property
    def url(self) -> str:
        return f"{PORTAL}/resource/{DATASET}.json"

    def _rows(self, params: Mapping[str, str]) -> list[dict[str, Any]]:
        resp = self.client.get(self.url, params)
        if resp.status != 200:
            raise SocrataError(f"HTTP {resp.status} from {resp.url}: {resp.content[:200]!r}")
        return parse_rows(resp.content)

    def state_counts(self) -> dict[str, int]:
        rows = self._rows({"$select": "phy_state, count(*) AS n", "$group": "phy_state",
                           "$order": "phy_state", "$limit": "5000"})  # fmt: skip
        out: dict[str, int] = {}
        for r in rows:
            st = text(r.get("phy_state")) or OTHER
            if st == OTHER or _STATE.match(st):
                out[st] = out.get(st, 0) + int(r.get("n") or 0)
        return dict(sorted(out.items()))

    def partitions(self) -> Iterator[dict[str, str]]:
        for st, n in self.state_counts().items():
            bounds: list[str] = []
            for k in range(1, (n + WINDOW - 1) // WINDOW):
                got = self._rows({"$select": "dot_number", "$where": state_clause(st),
                                  "$order": "dot_number", "$limit": "1",
                                  "$offset": str(k * WINDOW)})  # fmt: skip
                if got and (b := text(got[0].get("dot_number"))) and b not in bounds:
                    bounds.append(b)
            edges: list[str | None] = [None, *bounds, None]
            for lo, hi in itertools.pairwise(edges):
                part = {"state": st}
                if lo:
                    part["dot_from"] = lo
                if hi:
                    part["dot_to"] = hi
                yield part

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: state (a PHY_STATE value, or 'other'); dot_from, dot_to (the window's
        USDOT range, half-open); limit (fixtures: the first rows by USDOT number)."""
        p = request.params
        state = p["state"]
        if state != OTHER and not _STATE.match(state):
            raise ValueError(f"bad state {state!r}")
        for k in ("dot_from", "dot_to"):
            if p.get(k) and not p[k].isdigit():
                raise ValueError(f"{k} must be a USDOT number")
        where = window_where(state, p.get("dot_from"), p.get("dot_to"))
        limit = int(p["limit"]) if "limit" in p else None
        query = SocrataQuery(PORTAL, DATASET, where, order_by=("dot_number",),
                             page_size=limit or WINDOW, select=KEEP)  # fmt: skip
        rows, responses = fetch_all(self.client, query, max_pages=1 if limit else 100,
                                    sample=limit is not None)  # fmt: skip
        kept = [{k: v for k in KEEP if (v := text(r.get(k))) is not None} for r in rows]
        body = {"dataset": DATASET, "where": where, "state": state, "rows": kept}
        return Fetched(self.source_id, f"{query.url}?$where={where}", responses[0].retrieved_at,
                       200, canonical_json(body), "application/json")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        """Names and streets pseudonymized; USDOT and docket numbers too (public lookup keys
        that would undo the name pseudonyms)."""
        data = json.loads(scrub_json(content, NAMES, STREETS))
        for r in data.get("rows") or []:
            for k, n in (("dot_number", 8), ("prior_revoke_dot_number", 8), ("docket1", 7),
                         ("docket2", 7), ("docket3", 7)):  # fmt: skip
                if r.get(k) and str(r[k]).strip("0"):
                    r[k] = pseudo_digits(k, r[k], n)
        return canonical_json(data)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for r in sorted(data.get("rows") or [], key=canonical_json):
            dot = "".join(ch for ch in str(r.get("dot_number") or "") if ch.isdigit())
            name = text(r.get("legal_name"))
            if not dot or name is None or dot in seen:
                continue
            seen.add(dot)
            ctx = RecordContext(fetched, self.jurisdiction(r), dot, "motor_carrier", r)
            yield ctx.source_record()
            physical = mailing = None
            if is_us(r.get("phy_country")):
                physical = address(r.get("phy_street"), r.get("phy_city"), r.get("phy_state"),
                                   r.get("phy_zip"))  # fmt: skip
            if is_us(r.get("carrier_mailing_country")):
                mailing = address(
                    r.get("carrier_mailing_street"), r.get("carrier_mailing_city"),
                    r.get("carrier_mailing_state"), r.get("carrier_mailing_zip"),
                )  # fmt: skip
            added = parse_day(r.get("add_date"))
            valid_from = added if added is not None and added <= observed else observed
            holders: list[Holder] = []
            for k in OFFICERS:
                if (who := text(r.get(k))) and any(ch.isalpha() for ch in who):
                    org = classify(who).party_kind == "org"
                    holders.append(Holder("officer", "COMPANY OFFICER", who, person=not org,
                                          parts={} if org else person_parts(who)))  # fmt: skip
            individual = str(r.get("business_org_id") or "").strip() == "1"
            if individual and classify(name).party_kind != "org":
                holders.append(Holder("other", "SOLE PROPRIETOR", name, person=True,
                                      parts=person_parts(name)))  # fmt: skip
            code = (text(r.get("status_code")) or "").upper()
            yield from emit_business(
                ctx, source_id=self.source_id, sos_id=f"USDOT:{dot}", name=name,
                valid_from=valid_from, status=STATUS.get(code, code or None), principal=physical,
                mailing=mailing, holders=holders,
            )  # fmt: skip

    @staticmethod
    def jurisdiction(r: Mapping[str, Any]) -> str:
        st = (text(r.get("phy_state")) or "").upper()
        if not is_us(r.get("phy_country")) or st not in us_states() or st in MILITARY:
            return "US"
        county = text(r.get("phy_cnty"))
        if county and county.isdigit():
            try:
                return county_by_fips(st, county.zfill(3)).fips5
            except KeyError:
                pass
        return jurisdiction(st)

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            rows = self._rows({"$limit": "1", "$order": "dot_number"})
            count = self._rows({"$select": "count(*) AS n"})
        except (OSError, RuntimeError, ValueError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        shape = tuple(sorted(rows[0])) if rows else ()
        n = int(count[0]["n"]) if count else None
        ok = bool(rows) and {"dot_number", "legal_name"} <= set(shape)
        return HealthReport(self.source_id, ok, now, f"rows={n}", shape, rows=n)
