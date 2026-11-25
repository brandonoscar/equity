"""Lobbying Disclosure Act registrations (U.S. Senate Office of Public Records, LDA.gov REST
API, v1): every lobbying registrant (lobbying firms and organizations that lobby for
themselves, ~18k), every client a registrant has registered for (~138k) and every lobbyist
named on a filing (~89k), with the registrant's address. LDA.gov replaced
lda.senate.gov (which answers 503 "under maintenance" and serves no robots.txt).

Three sources, one per endpoint, each read in id order (`ordering=id`, so pages already read
stay put as rows are added) in pages of PAGE_SIZE rows (the API's largest page):

- us.senate.lda_registrants: business, sos_id LDA-REG:<registrant id>, the registrant's
  name and address (address_1-4, city, state, ZIP; U.S. only), valid from the retrieval
  date; the contact name (a person; a leading MR./MS./DR. dropped) is a holder (role
  'other', title CONTACT). Telephone numbers are not kept.
- us.senate.lda_clients: business, sos_id LDA-CLIENT:<client id> (one per registrant-client
  registration), the client's name, valid from the registration's effective date; the
  registrant is a holder (role 'other', title LOBBYING REGISTRANT, at the registrant's
  address). The API gives a client's state and country only, no street address.
- us.senate.lda_lobbyists: party, the lobbyist (a person, name in parts: first / middle /
  last / suffix) at the registrant's address (role 'lobbyist'), and the registrant (role
  'employer') at the same address.

Partitions: windows of PAGES_PER_PART pages (page_from, page_to half-open), counted from one
request's `count`.

Terms: https://lda.gov/api/tos/ (read 2026-11-25): anonymous access allowed without a key,
throttled to 15 requests/minute; secondary use is not restricted ("Data accessed through
LDA.gov do not, and should not, include controls over its end use"); analyses must cite the
retrieval date and say the Senate Office of Public Records cannot vouch for data or analyses
after retrieval; content may not be modified and still cited as LDA.gov. robots.txt
(2026-11-25) allows /api/v1/ with Crawl-delay: 4, which PoliteClient honors (15/minute).
"""

from __future__ import annotations

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
    emit_party,
    jurisdiction,
    scrub_json,
    text,
)
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json

API = "https://lda.gov/api/v1"
TOS = "https://lda.gov/api/tos/"
CHECKED_ON = "2026-11-25"
PAGE_SIZE = 25
PAGES_PER_PART = 100  # 2,500 rows, ~7 minutes at 15 requests/minute
STREETS = ("address_1", "address_2", "address_3", "address_4")
NAMES = ("name", "contact_name", "first_name", "middle_name", "last_name", "nickname")
DROP = frozenset({"contact_telephone", "url"})
_HONORIFIC = re.compile(r"^(?:MR|MRS|MS|DR|HON)\.?\s+", re.I)


def registrant_address(r: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not r or (text(r.get("country")) or "US").upper() not in {"US", "USA"}:
        return None
    street = text(" ".join(p for k in STREETS if (p := text(r.get(k)))))
    return address(street, r.get("city"), r.get("state"), r.get("zip"))


def keep(obj: Any) -> Any:
    """The row without telephone numbers, API urls, empty values or *_display labels."""
    if isinstance(obj, dict):
        return {
            k: keep(v)
            for k, v in obj.items()
            if k not in DROP and not k.endswith("_display") and v not in (None, "", [])
        }
    if isinstance(obj, list):
        return [keep(v) for v in obj]
    return obj


def iso_day(value: Any) -> date | None:
    try:
        return date.fromisoformat((text(value) or "")[:10])
    except ValueError:
        return None


class _LDA(Adapter):
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = (*NAMES, *STREETS)
    endpoint: ClassVar[str]
    title: ClassVar[str]

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=4.0, timeout_s=120.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a federal register of organizations and people
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": f"{API}/{self.endpoint}/",
            "terms_url": TOS,
            "terms_summary": (
                f"LDA.gov REST API v1, {self.title}; U.S. Senate Office of Public Records. "
                "Anonymous access allowed (15 requests/minute); end use not restricted; cite "
                "the retrieval date and that the Senate cannot vouch for the data after "
                "retrieval. robots.txt allows /api/v1/ (Crawl-delay 4). Phones not kept."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def _page(self, page: int, size: int = PAGE_SIZE) -> dict[str, Any]:
        url = f"{API}/{self.endpoint}/"
        resp = self.client.get(url, {"ordering": "id", "page": str(page),
                                     "page_size": str(size)})  # fmt: skip
        if resp.status == 404:  # past the last page
            return {"results": []}
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {resp.url}: {resp.content[:200]!r}")
        data: dict[str, Any] = json.loads(resp.content)
        return data

    def partitions(self) -> Iterator[dict[str, str]]:
        n = int(self._page(1, 1).get("count") or 0)
        pages = (n + PAGE_SIZE - 1) // PAGE_SIZE
        for lo in range(1, pages + 1, PAGES_PER_PART):
            yield {"page_from": str(lo), "page_to": str(lo + PAGES_PER_PART)}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: page_from, page_to (a half-open window of PAGE_SIZE-row pages in id
        order); limit (fixtures: page `page_from` of `limit`-row pages, one request)."""
        p = request.params
        lo, hi = int(p["page_from"]), int(p.get("page_to", str(int(p["page_from"]) + 1)))
        if lo < 1 or hi <= lo:
            raise ValueError(f"bad page window {lo}-{hi}")
        at = datetime.now(UTC)
        rows: list[Any] = []
        if "limit" in p:
            rows = self._page(lo, int(p["limit"])).get("results") or []
        else:
            for page in range(lo, hi):
                data = self._page(page)
                rows += data.get("results") or []
                if not data.get("next"):
                    break
        body = {"endpoint": self.endpoint, "page_from": lo, "page_to": hi,
                "rows": [keep(r) for r in rows]}  # fmt: skip
        return Fetched(self.source_id, f"{API}/{self.endpoint}/?ordering=id&page={lo}-{hi - 1}",
                       at, 200, canonical_json(body), "application/json")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, NAMES, STREETS)

    def rows(self, fetched: Fetched) -> Iterator[tuple[str, dict[str, Any]]]:
        seen: set[str] = set()
        for r in sorted(json.loads(fetched.content).get("rows") or [], key=canonical_json):
            k = text(r.get("id"))
            if k and k not in seen:
                seen.add(k)
                yield k, r

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            data = self._page(1, 1)
        except (OSError, RuntimeError, ValueError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        n = int(data.get("count") or 0)
        rows = data.get("results") or []
        shape = tuple(sorted(rows[0])) if rows else ()
        return HealthReport(self.source_id, n > 0 and "id" in shape, now, f"rows={n}", shape,
                            rows=n)  # fmt: skip


class LDARegistrants(_LDA):
    source_id: ClassVar[str] = "us.senate.lda_registrants"
    endpoint: ClassVar[str] = "registrants"
    title: ClassVar[str] = "registrants (lobbying firms and self-filing organizations)"

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        observed = fetched.retrieved_at.astimezone(UTC).date()
        for rid, r in self.rows(fetched):
            name = text(r.get("name"))
            if name is None:
                continue
            addr = registrant_address(r)
            ctx = RecordContext(fetched, jurisdiction(addr["state"] if addr else None), rid,
                                "lda_registrant", r)  # fmt: skip
            yield ctx.source_record()
            holders = []
            if (contact := text(_HONORIFIC.sub("", text(r.get("contact_name")) or ""))) and any(
                ch.isalpha() for ch in contact
            ):
                holders.append(Holder("other", "CONTACT", contact, addr, person=True))
            yield from emit_business(ctx, source_id=self.source_id, sos_id=f"LDA-REG:{rid}",
                                     name=name, valid_from=observed, principal=addr,
                                     holders=holders)  # fmt: skip


class LDAClients(_LDA):
    source_id: ClassVar[str] = "us.senate.lda_clients"
    endpoint: ClassVar[str] = "clients"
    title: ClassVar[str] = "clients registered by each registrant"

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        observed = fetched.retrieved_at.astimezone(UTC).date()
        for cid, r in self.rows(fetched):
            name = text(r.get("name"))
            if name is None:
                continue
            st = text(r.get("state")) if (text(r.get("country")) or "US") == "US" else None
            ctx = RecordContext(fetched, jurisdiction(st), cid, "lda_client", r)
            yield ctx.source_record()
            reg = r.get("registrant") or {}
            holders = []
            if who := text(reg.get("name")):
                holders.append(Holder("other", "LOBBYING REGISTRANT", who,
                                      registrant_address(reg)))  # fmt: skip
            start = iso_day(r.get("effective_date"))
            yield from emit_business(
                ctx, source_id=self.source_id, sos_id=f"LDA-CLIENT:{cid}", name=name,
                valid_from=start if start is not None and start <= observed else observed,
                holders=holders,
            )  # fmt: skip


class LDALobbyists(_LDA):
    source_id: ClassVar[str] = "us.senate.lda_lobbyists"
    endpoint: ClassVar[str] = "lobbyists"
    title: ClassVar[str] = "lobbyists named on registrations and reports"

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        for lid, r in self.rows(fetched):
            parts = {
                "first_name": text(r.get("first_name")),
                "middle": text(r.get("middle_name")),
                "last_name": text(r.get("last_name")),
                "suffix": text(r.get("suffix")),
            }
            who = text(" ".join(v for v in parts.values() if v))
            if who is None or parts["last_name"] is None:
                continue
            reg = r.get("registrant") or {}
            addr = registrant_address(reg)
            ctx = RecordContext(fetched, jurisdiction(addr["state"] if addr else None), lid,
                                "lda_lobbyist", r)  # fmt: skip
            yield ctx.source_record()
            yield from emit_party(ctx, self.source_id, "lobbyist", who, addr, person=True,
                                  parts=parts)  # fmt: skip
            if employer := text(reg.get("name")):
                yield from emit_party(ctx, self.source_id, "employer", employer, addr)
