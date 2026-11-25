"""CMS Open Payments: General Payment Data (detailed), one dataset per program year.

Drug and device manufacturers and group purchasing organizations report every payment or
other transfer of value to physicians, non-physician practitioners and teaching hospitals
(42 CFR Part 403 Subpart I). CMS publishes each program year (2019 onward on the current
site; ~15-16M general payments a year) in the DKAN datastore at openpaymentsdata.cms.gov,
re-published each June with corrections and refreshed again in January.

Read through the datastore query API (GET /api/1/datastore/query/<dataset>/0): conditions
on recipient_state, sorted by record_id, 500 rows a page (the API's maximum); only the KEEP
columns are kept. Free text (contextual_information) and the product columns past the first
are not.

What is emitted, from existing tables only:

- source_record: one per payment (record_key = record_id, record_type
  open_payments_general_payment). Amount, date, number of payments, form and nature of the
  payment, travel, product and dispute fields stay in the hashed raw record.
- business: the paying manufacturer or GPO (sos_id OPMFR:<its Open Payments id>, name as
  printed, valid from 1 January of the program year: every payment of the year emits the
  same row, so it loads once).
- party: the covered recipient, a person with name parts (physician or non-physician
  practitioner; NPI and profile id in the raw record) or a teaching hospital (an
  organization), at the recipient's business address; and a third party that received the
  payment on the recipient's behalf, when named.
- business_role: recipient -> payer, role 'other', title PAYMENT RECIPIENT (third party:
  THIRD PARTY PAYMENT RECIPIENT), valid from the payment date.
- address: the recipient's U.S. business address (a foreign one stays raw).

Partitions: program year x recipient state (the states the year's data holds, from one
grouped count per year; '' -> 'other') x offset window of WINDOW payments in record_id
order. The datasets do not change between publications, so offsets are stable within one.
openpaymentsdata.cms.gov robots.txt allows everything with Crawl-delay: 5 (PoliteClient
waits 5 s between requests); one page takes ~20-30 s to serve, so a year is ~32k requests:
a full load is a multi-day job, run partition by partition. `limit` (fixtures) reads only
the first `limit` rows of a window.

Source: https://openpaymentsdata.cms.gov (CMS; datasets licensed as U.S. government works,
https://www.usa.gov/government-works; free, no login, no API key).
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import address, jurisdiction, scrub_json, text
from equity.adapters.federal.cms_nppes import parse_day, pseudo_digits
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

SITE = "https://openpaymentsdata.cms.gov"
META = f"{SITE}/api/1/metastore/schemas/dataset/items"
QUERY = SITE + "/api/1/datastore/query/{dataset}/0"
TITLE = re.compile(r"^\s*(\d{4}) General Payment Data\s*$")
CHECKED_ON = "2026-11-25"
PAGE_SIZE = 500  # the datastore's maximum
WINDOW = 10_000  # payments per partition: 20 pages
OTHER = "other"  # recipient_state blank (foreign recipients)
KEEP = (
    "record_id", "program_year", "change_type", "covered_recipient_type",
    "teaching_hospital_ccn", "teaching_hospital_id", "teaching_hospital_name",
    "covered_recipient_profile_id", "covered_recipient_npi", "covered_recipient_first_name",
    "covered_recipient_middle_name", "covered_recipient_last_name",
    "covered_recipient_name_suffix", "recipient_primary_business_street_address_line1",
    "recipient_primary_business_street_address_line2", "recipient_city", "recipient_state",
    "recipient_zip_code", "recipient_country", "recipient_province", "recipient_postal_code",
    "covered_recipient_primary_type_1", "covered_recipient_specialty_1",
    "covered_recipient_license_state_code1",
    "submitting_applicable_manufacturer_or_applicable_gpo_name",
    "applicable_manufacturer_or_applicable_gpo_making_payment_id",
    "applicable_manufacturer_or_applicable_gpo_making_payment_name",
    "applicable_manufacturer_or_applicable_gpo_making_payment_state",
    "applicable_manufacturer_or_applicable_gpo_making_payment_country",
    "total_amount_of_payment_usdollars", "date_of_payment",
    "number_of_payments_included_in_total_amount", "form_of_payment_or_transfer_of_value",
    "nature_of_payment_or_transfer_of_value", "city_of_travel", "state_of_travel",
    "country_of_travel", "physician_ownership_indicator",
    "third_party_payment_recipient_indicator",
    "name_of_third_party_entity_receiving_payment_or_transfer_of_ccfc", "charity_indicator",
    "third_party_equals_covered_recipient_indicator", "delay_in_publication_indicator",
    "dispute_status_for_publication", "related_product_indicator",
    "indicate_drug_or_biological_or_device_or_medical_supply_1",
    "product_category_or_therapeutic_area_1",
    "name_of_drug_or_biological_or_device_or_medical_supply_1", "payment_publication_date",
)  # fmt: skip
THIRD_PARTY = "name_of_third_party_entity_receiving_payment_or_transfer_of_ccfc"
PAYER_ID = "applicable_manufacturer_or_applicable_gpo_making_payment_id"
PAYER_NAME = "applicable_manufacturer_or_applicable_gpo_making_payment_name"
NAMES = ("covered_recipient_first_name", "covered_recipient_middle_name",
         "covered_recipient_last_name", THIRD_PARTY)  # fmt: skip
STREETS = ("recipient_primary_business_street_address_line1",
           "recipient_primary_business_street_address_line2")  # fmt: skip
US = frozenset({"", "UNITED STATES", "US", "USA"})


class OpenPaymentsError(RuntimeError):
    pass


def query_params(state: str, offset: int, limit: int) -> dict[str, str]:
    """One datastore page: recipient_state = state ('' for 'other'), record_id order."""
    p = {
        "limit": str(limit), "offset": str(offset), "count": "false", "schema": "false",
        "results": "true", "keys": "true",
        "conditions[0][property]": "recipient_state",
        "conditions[0][value]": "" if state == OTHER else state,
        "conditions[0][operator]": "=",
        "sorts[0][property]": "record_id", "sorts[0][order]": "asc",
    }  # fmt: skip
    # No `properties` column list: the server refuses a request line over ~2850 characters,
    # and KEEP spelled out is that long. Rows come whole; fetch() keeps the KEEP columns.
    return p


def is_hospital(r: Mapping[str, Any]) -> bool:
    return "TEACHING HOSPITAL" in (text(r.get("covered_recipient_type")) or "").upper()


def recipient(r: Mapping[str, Any]) -> tuple[str, str, dict[str, str | None]] | None:
    """(raw name, party kind, name parts) of the covered recipient."""
    if is_hospital(r):
        name = text(r.get("teaching_hospital_name"))
        return None if name is None else (name, "org", {})
    last = text(r.get("covered_recipient_last_name"))
    if last is None:
        return None
    first = text(r.get("covered_recipient_first_name"))
    middle = text(r.get("covered_recipient_middle_name"))
    suffix = text(r.get("covered_recipient_name_suffix"))
    raw = " ".join(p for p in (first, middle, last, suffix) if p)
    return raw, "person", {"first_name": first, "middle": middle, "last_name": last,
                           "suffix": suffix}  # fmt: skip


class CMSOpenPayments(Adapter):
    source_id: ClassVar[str] = "us.cms.open_payments"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = (*NAMES, *STREETS)

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=5.0, timeout_s=600.0)
        self._datasets: dict[str, str] | None = None

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a federal registry of payers and recipients
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": SITE,
            "terms_url": "https://www.usa.gov/government-works",
            "terms_summary": (
                "CMS Open Payments general payment data by program year, DKAN datastore API, "
                "free, no login or key; datasets licensed as U.S. government works. "
                "robots.txt allows all paths, Crawl-delay 5."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def datasets(self) -> dict[str, str]:
        """Program year -> datastore dataset id, from the metastore."""
        if self._datasets is None:
            resp = self.client.get(META, {"show-reference-ids": "false"})
            if resp.status != 200:
                raise OpenPaymentsError(f"HTTP {resp.status} from {META}")
            out: dict[str, str] = {}
            for d in json.loads(resp.content):
                m = TITLE.match(str(d.get("title") or ""))
                if m and d.get("identifier"):
                    out[m.group(1)] = str(d["identifier"])
            self._datasets = dict(sorted(out.items()))
        return self._datasets

    def _get(self, dataset: str, params: Mapping[str, str]) -> list[dict[str, Any]]:
        # In order, not sorted (as PoliteClient.get sorts params): DKAN reads indexed
        # parameters (properties[0], properties[1], ... properties[10]) as a list only in
        # index order.
        url = QUERY.format(dataset=dataset)
        resp = self.client.get(url + "?" + urllib.parse.urlencode(list(params.items())))
        if resp.status != 200:
            raise OpenPaymentsError(f"HTTP {resp.status} from {url}: {resp.content[:200]!r}")
        body = json.loads(resp.content)
        results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(results, list):
            raise OpenPaymentsError(f"{url}: no results array")
        return results

    def state_counts(self, dataset: str) -> dict[str, int]:
        """Payments per recipient state ('other' for blank) in one grouped query."""
        rows = self._get(dataset, {
            "limit": "500", "count": "false", "schema": "false", "results": "true",
            "groupings[0]": "recipient_state", "properties[0]": "recipient_state",
            "properties[1][expression][operator]": "count",
            "properties[1][expression][operands][0]": "record_id", "properties[1][alias]": "n",
        })  # fmt: skip
        out: dict[str, int] = {}
        for r in rows:
            st = text(r.get("recipient_state")) or OTHER
            out[st] = out.get(st, 0) + int(r.get("n") or 0)
        return dict(sorted(out.items()))

    def partitions(self) -> Iterator[dict[str, str]]:
        for year, dataset in self.datasets().items():
            for st, n in self.state_counts(dataset).items():
                for lo in range(0, n, WINDOW):
                    yield {"year": year, "state": st, "offset": str(lo)}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: year (program year); state (recipient state, or 'other'); offset (the
        window's first payment, default 0); limit (fixtures: the window's first rows)."""
        p = request.params
        year, state = p["year"], p["state"]
        if not re.fullmatch(r"\d{4}", year):
            raise ValueError(f"bad program year {year!r}")
        if state != OTHER and not re.fullmatch(r"[A-Z]{2}", state):
            raise ValueError(f"bad state {state!r}")
        dataset = self.datasets().get(year)
        if dataset is None:
            raise OpenPaymentsError(f"no {year} General Payment Data dataset")
        offset = int(p.get("offset", "0"))
        want = min(int(p["limit"]), WINDOW) if "limit" in p else WINDOW
        rows: list[dict[str, Any]] = []
        at = self.client.now()
        while len(rows) < want:
            n = min(PAGE_SIZE, want - len(rows))
            page = self._get(dataset, query_params(state, offset + len(rows), n))
            rows.extend({k: v for k in KEEP if (v := page_value(r, k)) is not None}
                        for r in page)  # fmt: skip
            if len(page) < n:
                break
        body = {"year": year, "dataset": dataset, "state": state, "offset": offset,
                "rows": rows}  # fmt: skip
        url = QUERY.format(dataset=dataset)
        return Fetched(self.source_id, f"{url}#state={state}&offset={offset}", at, 200,
                       canonical_json(body), "application/json")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        """Names and streets pseudonymized; a person's NPI, profile id and the record id too
        (each is a public lookup key that would undo the name pseudonym)."""
        data = json.loads(scrub_json(content, NAMES, STREETS))
        for r in data.get("rows") or []:
            if is_hospital(r):
                continue
            for k, n in (("covered_recipient_npi", 10), ("covered_recipient_profile_id", 8),
                         ("record_id", 10)):  # fmt: skip
                if r.get(k):
                    r[k] = pseudo_digits(k, r[k], n)
        return canonical_json(data)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for r in sorted(data.get("rows") or [], key=canonical_json):
            rid = text(r.get("record_id"))
            who = recipient(r)
            if rid is None or who is None or rid in seen:
                continue
            seen.add(rid)
            yield from self._payment(fetched, r, rid, who, data.get("year"), observed)

    def _payment(
        self,
        fetched: Fetched,
        r: Mapping[str, Any],
        rid: str,
        who: tuple[str, str, dict[str, str | None]],
        year: Any,
        observed: date,
    ) -> Iterator[NormalizedRow]:
        state = text(r.get("recipient_state"))
        ctx = RecordContext(fetched, jurisdiction(state), rid, "open_payments_general_payment",
                            r)  # fmt: skip
        yield ctx.source_record()
        addr = None
        if (text(r.get("recipient_country")) or "").upper() in US:
            street = " ".join(s for k in STREETS if (s := text(r.get(k)))) or None
            addr = address(street, r.get("recipient_city"), state, r.get("recipient_zip_code"))
        if addr is not None:
            yield NormalizedRow("address", addr)
        py = str(r.get("program_year") or year or "")
        year_start = date(int(py), 1, 1) if py.isdigit() else observed
        year_start = min(year_start, observed)
        paid = parse_day(r.get("date_of_payment"))
        paid_on = paid if paid is not None and paid <= observed else year_start
        payer = text(r.get(PAYER_NAME))
        sos_id = None
        if payer is not None:
            pid = text(r.get(PAYER_ID)) or stable_id("payer", clean(payer))
            sos_id = f"OPMFR:{pid}"
            yield ctx.fact(
                "business", sos_id=sos_id, name=payer, org_form=classify(payer).org_form,
                status=None, formed_on=None, status_date=None, principal_address_id=None,
                mailing_address_id=None, valid_from=year_start, valid_to=None,
            )  # fmt: skip
        raw, kind, parts = who
        parties = [("recipient", "PAYMENT RECIPIENT", raw, kind, parts, addr)]
        if (third := text(r.get(THIRD_PARTY))) and clean(third) != clean(raw):
            parties.append(("third_party", "THIRD PARTY PAYMENT RECIPIENT", third,
                            classify(third).party_kind, {}, None))  # fmt: skip
        for role_key, title, name, pkind, pparts, paddr in parties:
            party_id = stable_id(self.source_id, rid, role_key, clean(name))
            nc = classify(name)
            org = pkind == "org"
            yield ctx.fact(
                "party", party_id=party_id, raw_name=name, party_kind=pkind,
                org_form=nc.org_form if org else None,
                org_name_norm=(nc.org_name_norm or clean(name)) if org else None,
                address_id=None if paddr is None else paddr["address_id"],
                first_name=pparts.get("first_name"), middle=pparts.get("middle"),
                last_name=pparts.get("last_name"), suffix=pparts.get("suffix"),
            )  # fmt: skip
            if sos_id is not None:
                yield ctx.fact("business_role", sos_id=sos_id, party_id=party_id, role="other",
                               title=title, valid_from=paid_on, valid_to=None)  # fmt: skip

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            years = self.datasets()
            latest = years[max(years)]
            rows = self._get(latest, query_params("WY", 0, 1))
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        shape = tuple(sorted(rows[0])) if rows else ()
        ok = bool(rows) and {"record_id", "covered_recipient_last_name"} <= set(shape)
        return HealthReport(self.source_id, ok, now, f"years={','.join(years)}", shape)


def page_value(row: Mapping[str, Any], key: str) -> str | None:
    """A datastore value as kept: stripped text, empty strings dropped."""
    v = row.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s or None
