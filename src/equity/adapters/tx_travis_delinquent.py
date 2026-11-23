"""Travis County, TX Tax Office delinquent property tax file (one CSV, refreshed weekly).

tax-office.traviscountytx.gov publishes TaxDelqOpenData.csv with no login: one row per account
with the owner's name and mailing address, the delinquent and total amounts due, the first
delinquent year and, once the county has sued, the tax-suit cause number and judgment date.
No license or terms are published (used on the project owner's decision, 2026-11-23).

Each account with a delinquent total is one instrument owed by the named owner:
  with a cause number and judgment date   COURT_ORDER (a tax-suit judgment), dated the judgment
  otherwise                               TAX_LIEN_STATE (Texas property tax is a lien on the
                                          property), dated January 1 of the first delinquent
                                          year
The amount is the delinquent total. The account number is the tax office's geographic id, not
the appraisal district PROP_ID that the statewide parcels carry, so no parcel link is made and
owners are matched by name and mailing address.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

URL = "https://tax-office.traviscountytx.gov/voterdata/TaxDelqOpenData.csv"
COUNTY = "48453"


def _field(row: Mapping[str, Any], name: str) -> str | None:
    """Column names carry trailing spaces in places; match them trimmed."""
    for k, v in row.items():
        if k.strip() == name:
            s = " ".join(str(v or "").split())
            return s or None
    return None


def _money(v: str | None) -> Decimal | None:
    try:
        d = Decimal((v or "").replace("$", "").replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() and d > 0 else None


def _date(v: str | None) -> date | None:
    """MM/DD/YYYY (time ignored) or YYYY-MM-DD."""
    s = (v or "").strip().split(" ")[0]
    try:
        if len(s) >= 8 and s.count("/") == 2:
            m, d, y = (int(x) for x in s.split("/"))
            return date(y, m, d)
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _year(v: str | None) -> int | None:
    s = (v or "").strip()
    return int(s) if s.isdigit() and 1900 <= int(s) <= 2200 else None


class TravisTaxDelinquent(Adapter):
    source_id: ClassVar[str] = "tx.travis.tax_delinquent"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("Owner Name", "Address 1", "Address 2", "Address 3",
                                             "Street Number", "Street Name",
                                             "Legal Description")  # fmt: skip

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "tax",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": URL,
            "terms_url": "https://tax-office.traviscountytx.gov/pages/DelinquentFileLayout.php",
            "terms_summary": (
                "Travis County Tax Office delinquent tax open data file; free, no login; no "
                "license or terms published. Used on the project owner's decision (2026-11-23)."
            ),
            "terms_checked_on": "2026-11-23",
            "robots_checked_on": "2026-11-23",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {}

    def fetch(self, request: FetchRequest) -> Fetched:
        resp = self.client.get(URL, {})
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status}")
        rows = list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig", "replace"))))
        limit = request.params.get("limit")
        if limit:
            rows = rows[: int(limit)]
        return Fetched(self.source_id, URL, resp.retrieved_at, 200,
                       canonical_json({"rows": rows}), "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        seen: set[str] = set()
        for r in sorted(json.loads(fetched.content).get("rows") or [], key=canonical_json):
            account, owner = _field(r, "Account #"), _field(r, "Owner Name")
            amount = _money(_field(r, "Delinquent Total"))
            cause, judged = _field(r, "Cause #"), _date(_field(r, "Judgement Date"))
            first = _year(_field(r, "1st Year Delinquent"))
            when = judged if cause and judged else date(first, 1, 1) if first else None
            if not (account and owner and amount and when) or account in seen:
                continue
            seen.add(account)
            ctx = RecordContext(fetched, COUNTY, account, "tax_account", r)
            uid = stable_id(self.source_id, "account", account)
            suit = bool(cause and judged)
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=uid,
                instrument_number=cause if suit else account, book_type=None, book=None,
                page=None,
                doc_type_raw="Tax suit judgment" if suit else "Delinquent property tax",
                doc_type="COURT_ORDER" if suit else "TAX_LIEN_STATE", recorded_on=when,
                recorded_seq=None, executed_on=None, consideration=None,
                principal_amount=amount, max_secured_amount=None, maturity_date=None,
                amount_source="index", legal_desc_raw=None,
            )  # fmt: skip
            line = " ".join(x for x in (_field(r, "Address 1"), _field(r, "Address 2"),
                                        _field(r, "Address 3")) if x) or None  # fmt: skip
            z = (_field(r, "Zip Code") or "")[:5]
            addr = normalized_address(line, _field(r, "City"), _field(r, "State"),
                                      z if z.isdigit() and len(z) == 5 else None)  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            nc = classify(owner)
            party_id = stable_id(self.source_id, account, "debtor", clean(owner))
            yield ctx.fact("party", party_id=party_id, raw_name=owner, party_kind=nc.party_kind,
                           org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                           address_id=addr["address_id"] if addr else None)  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=party_id,
                           role="debtor", seq=1)  # fmt: skip

    def health(self) -> HealthReport:
        n = len(json.loads(self.fetch(FetchRequest({})).content)["rows"])
        return HealthReport(self.source_id, n > 1000, datetime.now(UTC), f"{n} accounts")
