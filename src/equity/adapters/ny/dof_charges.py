"""NYC Department of Finance "Property Charges Balance": past-due property charges per tax lot.

The dataset (NYC Open Data scjx-j6np) is a quarterly snapshot of every charge on every tax lot
(property tax, sundry and assessment charges), each with its liability, collections and
balance; all snapshots are kept (143M rows). This source reads only the latest snapshot and
only balances more than PAST_DUE_DAYS past their due date, summed on the server per lot
(parid = 10-digit BBL) and charge code: about 122,000 lots and $3.3B past due in the
2026-11-15 snapshot, of which $2.76B is property tax (code CHG).

Each lot and code is one TAX_LIEN_STATE instrument on the lot (NYC property tax and charges
are liens on the property, NYC Admin. Code 11-301), dated by the earliest past-due charge,
with the balance as its amount and the snapshot date in the raw type. The lot's owner is the
debtor (no name is published): the NY-NYC-LIENSALE run links it by parcel. One partition per
borough keeps each query small.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.liens import BOROUGHS
from equity.adapters.rows import RecordContext, canonical_json
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PORTAL = "https://data.cityofnewyork.us"
DATASET = "scjx-j6np"
URL = f"{PORTAL}/resource/{DATASET}.json"
PAST_DUE_DAYS = 60
PAGE = 50_000
CODES = {"CHG": "property tax", "SAC": "sundry charge (SAC)", "SAF": "sundry charge (SAF)",
         "SAT": "sundry charge (SAT)"}  # fmt: skip
CREDITOR = "NYC Department of Finance"


def _money(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() and d > 0 else None


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def lot_uid(parid: Any) -> str | None:
    """'1000010010' -> '36061-6201001000010010' (the NYC parcel key used by the NY runs)."""
    s = str(parid or "").strip()
    if not (len(s) == 10 and s.isdigit() and s[0] in "12345" and int(s[1:6]) and int(s[6:])):
        return None
    county, swis = BOROUGHS[s[0]]
    return f"{county}-{swis}{s}"


class NYCPastDueCharges(Adapter):
    source_id: ClassVar[str] = "ny.nyc.dof.past_due_charges"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=600.0)
        self._extract: str | None = None
        self._retrieved = datetime.now(UTC)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "tax",
            "jurisdiction": "36",
            "access_method": "api",
            "base_url": URL,
            "terms_url": f"{PORTAL}/d/{DATASET}",
            "terms_summary": (
                "NYC Open Data (Socrata), Department of Finance 'Property Charges Balance', NYC "
                "open data terms of use, free, no login. Quarterly snapshot; only the latest "
                "is read, summed per lot and charge code on the server."
            ),
            "terms_checked_on": "2026-11-27",
            "robots_checked_on": "2026-11-27",
            "cost_model": "free",
        }

    def _get(self, params: Mapping[str, str]) -> list[dict[str, Any]]:
        resp = self.client.get(URL, params)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status}")
        self._retrieved = resp.retrieved_at
        rows: list[dict[str, Any]] = json.loads(resp.content)
        return rows

    def latest_extract(self) -> str:
        if self._extract is None:
            rows = self._get({"$select": "max(extractdt) AS m"})
            m = str((rows[0] if rows else {}).get("m") or "")
            if not m:
                raise RuntimeError(f"{self.source_id}: no snapshot date")
            self._extract = m
        return self._extract

    def partitions(self) -> Iterator[dict[str, str]]:
        for b in "12345":
            yield {"borough": b}

    def where(self, borough: str, extract: str, today: date) -> str:
        if borough not in "12345" or len(borough) != 1:
            raise ValueError(f"bad borough {borough!r}")
        cutoff = (today - timedelta(days=PAST_DUE_DAYS)).isoformat()
        return (f"extractdt = '{extract}' AND sum_bal > 0 AND due_date < '{cutoff}' "
                f"AND starts_with(parid, '{borough}')")  # fmt: skip

    def fetch(self, request: FetchRequest) -> Fetched:
        borough = str(request.params["borough"])
        limit = request.params.get("limit")
        extract = self.latest_extract()
        where = self.where(borough, extract, datetime.now(UTC).date())
        rows: list[dict[str, Any]] = []
        offset, page = 0, int(limit) if limit else PAGE
        while True:
            got = self._get({"$select": "parid, code, sum(sum_bal) AS balance, "
                                        "min(due_date) AS first_due, count(*) AS charges",
                             "$where": where, "$group": "parid, code",
                             "$order": "parid, code", "$limit": str(page),
                             "$offset": str(offset)})  # fmt: skip
            rows.extend(got)
            if limit or len(got) < page:
                break
            offset += page
        body = canonical_json({"borough": borough, "extract": extract[:10], "rows": rows})
        return Fetched(self.source_id, f"{URL}?borough={borough}", self._retrieved, 200,
                       body, "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        extract = str(data.get("extract") or "")
        creditor = classify(CREDITOR)
        seen: set[str] = set()
        for r in sorted(data.get("rows") or [], key=canonical_json):
            lot, code = lot_uid(r.get("parid")), str(r.get("code") or "").strip().upper()
            amount, first = _money(r.get("balance")), _date(r.get("first_due"))
            key = f"{r.get('parid')}-{code}"
            if not (lot and code and amount and first) or key in seen:
                continue
            seen.add(key)
            ctx = RecordContext(fetched, lot.split("-")[0], key, "charge_balance", r)
            uid = stable_id(self.source_id, "charge", key)
            label = CODES.get(code, f"charge code {code}")
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=key, book_type=None,
                book=None, page=None,
                doc_type_raw=f"NYC DOF past-due {label} (snapshot {extract})",
                doc_type="TAX_LIEN_STATE", recorded_on=first, recorded_seq=None,
                executed_on=None, consideration=None, principal_amount=amount,
                max_secured_amount=None, maturity_date=None, amount_source="index",
                legal_desc_raw=None,
            )  # fmt: skip
            yield ctx.fact("instrument_parcel", instrument_uid=uid, parcel_uid=lot,
                           method="index_parcel_id",
                           evidence={"parid": r.get("parid")})  # fmt: skip
            pid = stable_id(self.source_id, "creditor", clean(CREDITOR))
            yield ctx.fact("party", party_id=pid, raw_name=CREDITOR,
                           party_kind=creditor.party_kind, org_form=creditor.org_form,
                           org_name_norm=creditor.org_name_norm, address_id=None)  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid,
                           role="creditor", seq=1)  # fmt: skip

    def health(self) -> HealthReport:
        n = len(json.loads(self.fetch(FetchRequest({"borough": "5", "limit": "5"})).content)
                ["rows"])  # fmt: skip
        return HealthReport(self.source_id, n > 0, datetime.now(UTC),
                            f"{n} sample lots; snapshot {self.latest_extract()[:10]}")  # fmt: skip
