"""Federal real-property sale and surplus notices from the Federal Register API (free, no key).

Three searches, each a NOTICE-type document query, one partition per query and year:
  realty      "notice of realty action": BLM (and other agency) sales, exchanges and leases
              of public land, e.g. "Modified Competitive Sale of 20 Parcels ... Clark County"
  homeless    HUD's weekly Title V "Federal Property Suitable as Facilities to Assist the
              Homeless": excess federal buildings and land offered first to homeless providers
  lease_sale  BLM "lease sale": oil, gas and coal lease sale notices

Each notice is one instrument (doc_type OTHER, dated by publication, numbered by the FR
document number), with the publishing agencies as parties and the title in legal_desc_raw.
Notices name land by legal description in their full text; turning that into parcels is a
later step (a PLSS legal-description parser), so no instrument_parcel rows are made here.

API: https://www.federalregister.gov/api/v1/documents.json (robots.txt disallows only the
site's search pages, not /api/). Federal Register content is a U.S. government work.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

API = "https://www.federalregister.gov/api/v1/documents.json"
QUERIES: dict[str, dict[str, str]] = {
    "realty": {"conditions[term]": '"notice of realty action"', "label": "Notice of realty action"},
    "homeless": {"conditions[term]": '"assist the homeless"',
                 "conditions[agencies][]": "housing-and-urban-development-department",
                 "label": "Title V surplus federal property"},
    "lease_sale": {"conditions[term]": '"lease sale"',
                   "conditions[agencies][]": "land-management-bureau",
                   "label": "BLM lease sale"},
}  # fmt: skip
# HUD single-family (vacant / non-vacant), multifamily and healthcare note sales: each notice
# announces a sale of defaulted HUD-held mortgage notes, with the bid date and how to qualify.
LOAN_SALE_QUERIES: dict[str, dict[str, str]] = {
    "hud_loan_sale": {"conditions[term]": '"loan sale"',
                      "conditions[agencies][]": "housing-and-urban-development-department",
                      "label": "HUD loan sale notice"},
}  # fmt: skip
FIELDS = ("document_number", "title", "publication_date", "agencies", "html_url", "type")
FIRST_YEAR = 2000
PER_PAGE = 1000


class FederalRegisterRealty(Adapter):
    source_id: ClassVar[str] = "us.federalregister.realty_notices"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    queries: ClassVar[dict[str, dict[str, str]]] = QUERIES

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=120.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "government_sale",
            "jurisdiction": "US",
            "access_method": "api",
            "base_url": API,
            "terms_url": "https://www.federalregister.gov/reader-aids/developer-resources",
            "terms_summary": (
                "Federal Register API, free, no key; Federal Register documents are U.S. "
                "government works. robots.txt disallows only the site's search pages."
            ),
            "terms_checked_on": "2026-11-23",
            "robots_checked_on": "2026-11-23",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        for q in self.queries:
            for year in range(FIRST_YEAR, datetime.now(UTC).year + 1):
                yield {"query": q, "year": str(year)}

    def _params(self, query: str, year: int, page: int, per_page: int) -> list[tuple[str, str]]:
        spec = [(k, v) for k, v in self.queries[query].items() if k != "label"]
        return [*spec, ("conditions[type][]", "NOTICE"),
                ("conditions[publication_date][gte]", f"{year}-01-01"),
                ("conditions[publication_date][lte]", f"{year}-12-31"),
                ("per_page", str(per_page)), ("page", str(page)), ("order", "oldest"),
                *(("fields[]", f) for f in FIELDS)]  # fmt: skip

    def _get(self, params: list[tuple[str, str]]) -> Any:
        # fields[] repeats, so the query string is built here, not by the client.
        resp = self.client.get(f"{API}?{urllib.parse.urlencode(params)}")
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from the Federal Register API")
        return json.loads(resp.content), resp

    def fetch(self, request: FetchRequest) -> Fetched:
        query, year = request.params["query"], int(request.params["year"])
        if query not in self.queries:
            raise ValueError(f"unknown query {query!r}")
        limit = int(request.params["limit"]) if "limit" in request.params else None
        rows: list[dict[str, Any]] = []
        page, retrieved = 1, datetime.now(UTC)
        while True:
            data, resp = self._get(self._params(query, year, page, limit or PER_PAGE))
            retrieved = resp.retrieved_at
            rows += data.get("results") or []
            if limit or not data.get("next_page_url"):
                break
            page += 1
        body = {"query": query, "year": year, "rows": rows}
        return Fetched(self.source_id, f"{API}?query={query}&year={year}", retrieved, 200,
                       canonical_json(body), "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        label = self.queries.get(data.get("query"), {}).get("label", "Federal Register notice")
        today = fetched.retrieved_at.astimezone(UTC).date()
        for r in sorted(data.get("rows") or [], key=lambda x: str(x.get("document_number"))):
            num = str(r.get("document_number") or "").strip()
            try:
                published = date.fromisoformat(str(r.get("publication_date")))
            except ValueError:
                continue
            if not num or published > today:
                continue
            ctx = RecordContext(fetched, "US", num, "fr_notice", r)
            yield ctx.source_record()
            uid = stable_id(self.source_id, num)
            title = " ".join(str(r.get("title") or "").split())[:2000] or None
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=num, book_type=None,
                book=None, page=None, doc_type_raw=label, doc_type="OTHER",
                recorded_on=published, recorded_seq=None, executed_on=None, consideration=None,
                principal_amount=None, max_secured_amount=None, maturity_date=None,
                amount_source=None, legal_desc_raw=title,
            )  # fmt: skip
            agencies = [a for a in r.get("agencies") or [] if isinstance(a, dict)]
            names = sorted({str(a.get("raw_name") or a.get("name") or "").strip().upper()
                            for a in agencies} - {""})  # fmt: skip
            for seq, name in enumerate(names, start=1):
                nc = classify(name)
                pid = stable_id(self.source_id, "agency", clean(name))
                yield ctx.fact("party", party_id=pid, raw_name=name, party_kind="org",
                               org_form=nc.org_form, org_name_norm=nc.org_name_norm or clean(name),
                               address_id=None)  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid,
                               role="other", seq=seq)  # fmt: skip

    def health(self) -> HealthReport:
        try:
            query = next(iter(self.queries))  # the loan-sale source has no "realty" query
            data, _ = self._get(self._params(query, datetime.now(UTC).year, 1, 1))
        except (RuntimeError, ValueError, OSError) as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        rows = data.get("results") or []
        shape = tuple(sorted(rows[0])) if rows else ()
        n = int(data.get("count") or 0)
        return HealthReport(self.source_id, n > 0, datetime.now(UTC), f"{n} notices this year",
                            shape, n)  # fmt: skip


class FederalRegisterLoanSales(FederalRegisterRealty):
    """HUD loan sale notices: sales of defaulted HUD-held mortgage notes (single-family vacant
    and non-vacant, multifamily, healthcare). Each notice is a deal announcement: the sale
    name (e.g. HVLS 2027-1), bid date and qualification steps are in the notice text. The loan
    files themselves need HUD's confidentiality agreement and qualification statement, which
    is the project owner's decision; nothing here registers or bids."""

    source_id: ClassVar[str] = "us.federalregister.loan_sales"
    queries: ClassVar[dict[str, dict[str, str]]] = LOAN_SALE_QUERIES

    def source_row(self) -> Mapping[str, Any]:
        return {**super().source_row(), "source_id": self.source_id}
