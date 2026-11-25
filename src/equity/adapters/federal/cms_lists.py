"""CMS Medicare provider lists from data.cms.gov that name practitioners and suppliers:

- us.cms.opt_out_affidavits: "Opt Out Affidavits" (~60k rows, monthly): practitioners who
  opted out of Medicare (they contract privately with Medicare patients), with NPI,
  specialty, opt-out effective and end dates and the practice street address. Each row is a
  source record (record_type medicare_opt_out, key NPI + effective date): a party (a
  person, name in parts) at the address (role 'opted_out').
- us.cms.revoked_providers: "Revoked Medicare Providers and Suppliers" (~9k rows, monthly):
  enrollments CMS revoked, with NPI, enrollment id, name (a person's parts or an
  organization's name), state, provider type, the regulation cited, the effective date and
  the end of the re-enrollment bar. Each row is a source record (record_type
  medicare_revocation, key = the enrollment id): an organization is a business (sos_id
  NPI:<npi>, the CMS NPPES key, status 'revoked', status_date and valid from = the
  revocation's effective date); a person is a party with name parts (role 'revoked'). The
  file gives a state, no street address.

Both are read through the data.cms.gov data API (`/data-api/v1/dataset/<id>/data`, pages of
PAGE rows by offset) at the dataset's "latest" distribution as listed in
https://data.cms.gov/data.json (checked 2026-11-25), so each fetch reads the current month.
One partition per source.

Source: https://data.cms.gov/ (CMS; U.S. government data, free, no login, no key).
data.cms.gov robots.txt (read 2026-11-25) allows /data-api/.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import (
    address,
    emit_business,
    emit_party,
    jurisdiction,
    scrub_json,
    text,
)
from equity.adapters.federal.cms_nppes import pseudo_digits
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json

API = "https://data.cms.gov/data-api/v1/dataset"
CHECKED_ON = "2026-11-25"
PAGE = 5000


def iso_day(value: Any) -> date | None:
    try:
        return date.fromisoformat((text(value) or "")[:10])
    except ValueError:
        return None


class _CMSList(Adapter):
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    dataset: ClassVar[str]  # the "latest" distribution's dataset id in data.json
    page_url: ClassVar[str]
    title: ClassVar[str]
    npi_field: ClassVar[str] = "NPI"

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    @property
    def url(self) -> str:
        return f"{API}/{self.dataset}/data"

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a federal list of named providers
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": self.url,
            "terms_url": self.page_url,
            "terms_summary": (
                f"CMS {self.title}, data.cms.gov data API (latest monthly release); U.S. "
                "government data, free, no login, no key. robots.txt allows /data-api/."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def _page(self, offset: int, size: int) -> list[dict[str, Any]]:
        resp = self.client.get(self.url, {"offset": str(offset), "size": str(size)})
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {resp.url}: {resp.content[:200]!r}")
        rows = json.loads(resp.content)
        if not isinstance(rows, list):
            raise RuntimeError(f"{resp.url}: not a list of rows")
        return rows

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {"release": "latest"}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: release ('latest', the only partition); limit (fixtures: the first rows,
        `offset` rows in)."""
        p = request.params
        if p.get("release", "latest") != "latest":
            raise ValueError(f"bad release {p['release']!r}")
        at = datetime.now(UTC)
        if "limit" in p:
            rows = self._page(int(p.get("offset", "0")), int(p["limit"]))
        else:
            rows = []
            while page := self._page(len(rows), PAGE):
                rows += page
                if len(page) < PAGE:
                    break
        kept = [{k: v for k, v in r.items() if text(v) is not None} for r in rows]
        body = canonical_json({"url": self.url, "rows": kept})
        return Fetched(self.source_id, self.url, at, 200, body, "application/json")

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        """Names and streets pseudonymized; NPIs and enrollment ids replaced too."""
        data = json.loads(scrub_json(content, cls.names, cls.streets))
        for r in data.get("rows") or []:
            if r.get(cls.npi_field):
                r[cls.npi_field] = pseudo_digits("NPI", r[cls.npi_field], 10)
            if r.get("ENRLMT_ID"):
                r["ENRLMT_ID"] = "TEST" + pseudo_digits("ENRLMT", r["ENRLMT_ID"], 11)
        return canonical_json(data)

    names: ClassVar[tuple[str, ...]]
    streets: ClassVar[tuple[str, ...]] = ()

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            rows = self._page(0, 1)
        except (OSError, RuntimeError, ValueError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        shape = tuple(sorted(rows[0])) if rows else ()
        return HealthReport(self.source_id, self.npi_field in shape, now, "ok", shape)


class CMSOptOutAffidavits(_CMSList):
    source_id: ClassVar[str] = "us.cms.opt_out_affidavits"
    dataset: ClassVar[str] = "9887a515-7552-4693-bf58-735c77af46d7"
    page_url: ClassVar[str] = (
        "https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment/"
        "opt-out-affidavits"
    )
    title: ClassVar[str] = "Opt Out Affidavits"
    names: ClassVar[tuple[str, ...]] = ("First Name", "Last Name")
    streets: ClassVar[tuple[str, ...]] = ("First Line Street Address",
                                          "Second Line Street Address")  # fmt: skip
    pii_fields: ClassVar[tuple[str, ...]] = (*names, *streets)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        seen: set[str] = set()
        for r in sorted(json.loads(fetched.content).get("rows") or [], key=canonical_json):
            npi, last = text(r.get("NPI")), text(r.get("Last Name"))
            if npi is None or last is None:
                continue
            key = f"{npi}|{text(r.get('Optout Effective Date')) or ''}"
            if key in seen:
                continue
            seen.add(key)
            st = text(r.get("State Code"))
            ctx = RecordContext(fetched, jurisdiction(st), key, "medicare_opt_out", r)
            yield ctx.source_record()
            street = text(" ".join(p for k in self.streets if (p := text(r.get(k)))))
            addr = address(street, r.get("City Name"), st, r.get("Zip Code"))
            first = text(r.get("First Name"))
            parts = {"first_name": first, "middle": None, "last_name": last, "suffix": None}
            who = " ".join(v for v in (first, last) if v)
            yield from emit_party(ctx, self.source_id, "opted_out", who, addr, person=True,
                                  parts=parts)  # fmt: skip


class CMSRevokedProviders(_CMSList):
    source_id: ClassVar[str] = "us.cms.revoked_providers"
    dataset: ClassVar[str] = "66acd4b6-e9ca-47bb-a7d6-fbd7c2f56e93"
    page_url: ClassVar[str] = (
        "https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment/"
        "revoked-medicare-providers-and-suppliers"
    )
    title: ClassVar[str] = "Revoked Medicare Providers and Suppliers"
    names: ClassVar[tuple[str, ...]] = ("FIRST_NAME", "MDL_NAME", "LAST_NAME", "ORG_NAME")
    pii_fields: ClassVar[tuple[str, ...]] = names

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for r in sorted(json.loads(fetched.content).get("rows") or [], key=canonical_json):
            key = text(r.get("ENRLMT_ID")) or text(r.get("NPI"))
            org, last = text(r.get("ORG_NAME")), text(r.get("LAST_NAME"))
            if key is None or key in seen or not (org or last):
                continue
            seen.add(key)
            ctx = RecordContext(fetched, jurisdiction(text(r.get("STATE_CD"))), key,
                                "medicare_revocation", r)  # fmt: skip
            yield ctx.source_record()
            on = iso_day(r.get("REVOCATION_EFCTV_DT"))
            on = on if on is not None and on <= observed else None
            npi = text(r.get("NPI"))
            if org is not None:
                yield from emit_business(
                    ctx, source_id=self.source_id, sos_id=f"NPI:{npi}" if npi else f"PECOS:{key}",
                    name=org, valid_from=on or observed, status="revoked", status_date=on,
                )  # fmt: skip
                continue
            parts = {"first_name": text(r.get("FIRST_NAME")), "middle": text(r.get("MDL_NAME")),
                     "last_name": last, "suffix": None}  # fmt: skip
            who = " ".join(v for v in (parts["first_name"], parts["middle"], last) if v)
            yield from emit_party(ctx, self.source_id, "revoked", who, person=True, parts=parts)
