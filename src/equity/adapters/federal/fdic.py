"""FDIC BankFind Suite: every FDIC-insured institution (active and inactive, ~28k, back to
1934) and every office location (main offices and branches, ~78k), from the public BankFind
API (api.fdic.gov/banks; no key, no login).

Two sources, one partition per state (STALP, from one aggregate query), each read in pages
of PAGE rows sorted by the record key:

- us.fdic.institutions: business, sos_id FDIC:<CERT> (the FDIC certificate number), the
  institution's name, status active / inactive, formed_on = the establishment date,
  status_date = the end date of an inactive institution, principal address = the main office
  address, valid from the establishment date; the bank holding company (NAMEHCR) is a
  holder (role 'other', title BANK HOLDING COMPANY). Prior names (PRIORNAME1-10) are parties (role
  former_name) on the same record. Charter class, regulator, successor certificate (NEWCERT),
  RSSD id and the rest stay in the hashed raw record.
- us.fdic.locations: one source record per office (UNINUM, record_type bank_office): a party
  naming the institution (role 'office', an org) at the office's street address; the office
  name, service type, main-office flag and dates stay in the raw record.

Source: https://api.fdic.gov/banks/docs/ (FDIC BankFind Suite API documentation). U.S.
government data, free, no API key, no login; api.fdic.gov serves no robots.txt (404 on
2026-11-25: no restrictions). No personal data: names are institutions'.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import Holder, address, emit_business, emit_party, text
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.geo import county_by_fips, state_fips

API = "https://api.fdic.gov/banks"
DOCS = "https://api.fdic.gov/banks/docs/"
CHECKED_ON = "2026-11-25"
PAGE = 10_000  # the API's largest page
PRIOR = tuple(f"PRIORNAME{i}" for i in range(1, 11))
_STATE = re.compile(r"^[A-Z]{2}$")
_MDY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def mdy(value: Any) -> date | None:
    """MM/DD/YYYY (the API's date format), else None."""
    m = _MDY.match(text(value) or "")
    if m is None:
        return None
    try:
        return date(int(m[3]), int(m[1]), int(m[2]))
    except ValueError:
        return None


def county_jurisdiction(r: Mapping[str, Any]) -> str:
    """The county FIPS (STCNTY), else the state FIPS, else US."""
    st = text(r.get("STALP")) or ""
    fips = text(r.get("STCNTY")) or ""
    if fips.isdigit() and len(fips) == 5:
        try:
            return county_by_fips(st, fips[2:]).fips5
        except KeyError:
            pass
    try:
        return state_fips(st) if len(st) == 2 else "US"
    except KeyError:
        return "US"


class _BankFind(Adapter):
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = ()
    endpoint: ClassVar[str]
    key: ClassVar[str]
    fields: ClassVar[tuple[str, ...]]
    title: ClassVar[str]

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a federal registry of institutions
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": f"{API}/{self.endpoint}",
            "terms_url": DOCS,
            "terms_summary": (
                f"FDIC BankFind Suite API, {self.title}; U.S. government data, free, no API "
                "key, no login. api.fdic.gov serves no robots.txt (404)."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def _get(self, params: Mapping[str, str]) -> dict[str, Any]:
        url = f"{API}/{self.endpoint}"
        resp = self.client.get(url, params)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {resp.url}: {resp.content[:200]!r}")
        data: dict[str, Any] = json.loads(resp.content)
        return data

    def state_counts(self) -> dict[str, int]:
        data = self._get({"limit": "1", "agg_by": "STALP", "agg_limit": "1000"})
        out = {}
        for d in data.get("data") or []:
            st = text((d.get("data") or {}).get("STALP"))
            if st and _STATE.match(st):
                out[st] = int((d.get("data") or {}).get("count") or 0)
        return dict(sorted(out.items()))

    def partitions(self) -> Iterator[dict[str, str]]:
        for st in self.state_counts():
            yield {"state": st}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: state (STALP, two letters); limit (fixtures: the first rows)."""
        p = request.params
        st = p["state"].upper()
        if not _STATE.match(st):
            raise ValueError(f"bad state {st!r}")
        limit = int(p["limit"]) if "limit" in p else None
        rows: list[dict[str, Any]] = []
        at: datetime | None = None
        while True:
            data = self._get({"filters": f'STALP:"{st}"', "fields": ",".join(self.fields),
                              "limit": str(limit or PAGE), "offset": str(len(rows)),
                              "sort_by": self.key, "sort_order": "ASC"})  # fmt: skip
            at = at or datetime.now(UTC)
            page = [{k: v for k in self.fields if (v := (d.get("data") or {}).get(k))
                     not in (None, "")} for d in data.get("data") or []]  # fmt: skip
            rows += page
            total = int((data.get("meta") or {}).get("total") or 0)
            if limit is not None or not page or len(rows) >= total:
                break
        url = f"{API}/{self.endpoint}?filters=STALP:{st}"
        return Fetched(self.source_id, url, at, 200,
                       canonical_json({"state": st, "rows": rows}), "application/json")  # fmt: skip

    def records(self, fetched: Fetched) -> Iterator[tuple[str, dict[str, Any]]]:
        seen: set[str] = set()
        for r in sorted(json.loads(fetched.content).get("rows") or [], key=canonical_json):
            k = text(r.get(self.key))
            if k and k not in seen and text(r.get("NAME")):
                seen.add(k)
                yield k, r

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            data = self._get({"limit": "1"})
        except (OSError, RuntimeError, ValueError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        n = int((data.get("meta") or {}).get("total") or 0)
        rows = data.get("data") or []
        shape = tuple(sorted(rows[0].get("data") or {})) if rows else ()
        ok = n > 0 and {self.key, "NAME"} <= set(shape)
        return HealthReport(self.source_id, ok, now, f"rows={n}", shape, rows=n)


class FDICInstitutions(_BankFind):
    source_id: ClassVar[str] = "us.fdic.institutions"
    endpoint: ClassVar[str] = "institutions"
    key: ClassVar[str] = "CERT"
    title: ClassVar[str] = "institutions (every insured institution since 1934)"
    fields: ClassVar[tuple[str, ...]] = (
        "CERT", "NAME", "ADDRESS", "ADDRESS2", "CITY", "STALP", "ZIP", "COUNTY", "STCNTY",
        "ACTIVE", "INACTIVE", "ESTYMD", "INSDATE", "ENDEFYMD", "EFFDATE", "PROCDATE",
        "DATEUPDT", "CHANGEC1", "NEWCERT", "FED_RSSD", "RSSDHCR", "NAMEHCR", "UNINUM",
        "BKCLASS", "CHRTAGNT", "REGAGNT", "FDICREGN", "INSAGNT1", "CHARTER", "STCHRTR",
        "FEDCHRTR", "WEBADDR", "ULTCERT", "OFFDOM", "ASSET", "CITYHCR", "STALPHCR", *PRIOR,
    )  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        observed = fetched.retrieved_at.astimezone(UTC).date()
        for cert, r in self.records(fetched):
            ctx = RecordContext(fetched, county_jurisdiction(r), cert, "insured_institution", r)
            yield ctx.source_record()
            est = mdy(r.get("ESTYMD"))
            est = est if est is not None and est <= observed else None
            active = str(r.get("ACTIVE")) == "1"
            ended = None if active else mdy(r.get("ENDEFYMD"))
            ended = ended if ended is not None and ended <= observed else None
            street = text(" ".join(p for p in (text(r.get("ADDRESS")), text(r.get("ADDRESS2")))
                                   if p))  # fmt: skip
            addr = address(street, r.get("CITY"), r.get("STALP"), r.get("ZIP"))
            name = str(text(r.get("NAME")))
            holders = []
            if hc := text(r.get("NAMEHCR")):
                holders.append(
                    Holder(
                        "other",
                        "BANK HOLDING COMPANY",
                        hc,
                        address(None, r.get("CITYHCR"), r.get("STALPHCR"), None),
                    )
                )
            yield from emit_business(
                ctx, source_id=self.source_id, sos_id=f"FDIC:{cert}", name=name,
                valid_from=est or observed, status="active" if active else "inactive",
                formed_on=est, status_date=ended, principal=addr, holders=holders,
            )  # fmt: skip
            for old in dict.fromkeys(n for k in PRIOR if (n := text(r.get(k))) and n != name):
                yield from emit_party(ctx, self.source_id, "former_name", old)


class FDICLocations(_BankFind):
    source_id: ClassVar[str] = "us.fdic.locations"
    endpoint: ClassVar[str] = "locations"
    key: ClassVar[str] = "UNINUM"
    title: ClassVar[str] = "office locations (main offices and branches)"
    fields: ClassVar[tuple[str, ...]] = (
        "UNINUM", "CERT", "FI_UNINUM", "NAME", "OFFNAME", "OFFNUM", "MAINOFF", "ADDRESS",
        "ADDRESS2", "CITY", "STALP", "ZIP", "COUNTY", "STCNTY", "SERVTYPE", "SERVTYPE_DESC",
        "ESTYMD", "ACQDATE", "RUNDATE", "BKCLASS", "LATITUDE", "LONGITUDE",
    )  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        for uninum, r in self.records(fetched):
            ctx = RecordContext(fetched, county_jurisdiction(r), uninum, "bank_office", r)
            yield ctx.source_record()
            street = text(" ".join(p for p in (text(r.get("ADDRESS")), text(r.get("ADDRESS2")))
                                   if p))  # fmt: skip
            addr = address(street, r.get("CITY"), r.get("STALP"), r.get("ZIP"))
            yield from emit_party(ctx, self.source_id, "office", str(text(r.get("NAME"))), addr)
