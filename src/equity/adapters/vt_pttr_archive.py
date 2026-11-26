"""Vermont property transfer tax returns, 2010-2018, from the Department of Taxes' public archive.

The Department of Taxes publishes every property transfer tax return (32 V.S.A. 9606) in a
public storage container (taxpttrpublic, listed with no login): monthly XML extracts in a zip
per year. vt.tax.property_transfers loads the VCGI layer, which starts in 2019-01; this source
loads the years before it, keeping only returns that closed before 2019-01-01 so the two never
overlap. Zips whose files are not XML (2006-2009 use an older fixed-width text layout) are
skipped here.

Each return is one DEED instrument on the parcel: grantors are the sellers and grantees the
buyers (every one listed, with mailing address), consideration is the total price paid, and the
financing boxes ticked on the return (bank, owner, none, other) are carried in doc_type_raw, so
an owner-financed or cash sale can be found. The parcel is <county FIPS>-<SPAN as 3-3-5>, the
vt.statewide.parcels key; the return's countyCode numbers Vermont's counties alphabetically
(1 Addison ... 14 Windsor), so FIPS = 50000 + 2 x code - 1.
"""

from __future__ import annotations

import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
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

BASE = "https://taxpttrpublicblob.blob.core.usgovcloudapi.net/taxpttrpublic"
LIST = f"{BASE}?restype=container&comp=list"
ARCHIVE = re.compile(r"^property_transfer_files/Archive/PT(\d{4})/[^/]+\.zip$", re.I)
FIRST_YEAR, LAST_YEAR = 2010, 2018
CUTOFF = date(2019, 1, 1)  # vt.tax.property_transfers covers closings from here on
FINANCING = ("financingBank", "financingOwner", "financingNone", "financingOther")


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def _money(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() and d >= 0 else None


def span_uid(span: Any, county_code: Any) -> str | None:
    s, c = re.sub(r"\D", "", str(span or "")), str(county_code or "").strip()
    if len(s) != 11 or not c.isdigit() or not 1 <= int(c) <= 14:
        return None
    return f"{50000 + 2 * int(c) - 1}-{s[:3]}-{s[3:6]}-{s[6:]}"


def _flat(el: ET.Element) -> dict[str, str]:
    return {c.tag: (c.text or "").strip() for c in el if len(c) == 0}


def parse_extract(content: bytes) -> list[dict[str, Any]]:
    """One XML extract -> returns: the header fields plus seller and buyer lists."""
    out: list[dict[str, Any]] = []
    for form in ET.fromstring(content).iter("formData"):  # noqa: S314 - state tax agency file
        head = form.find("formHeader")
        if head is None:
            continue
        out.append({**_flat(head),
                    "sellers": [_flat(s) for s in form.iter("seller")],
                    "buyers": [_flat(b) for b in form.iter("buyer")]})  # fmt: skip
    return out


def parse_zip(content: bytes) -> list[dict[str, Any]] | None:
    """Every XML extract in a year's zip, or None when the zip holds no XML (older layout)."""
    z = zipfile.ZipFile(io.BytesIO(content))
    xml = sorted(n for n in z.namelist() if n.lower().endswith(".xml"))
    if not xml:
        return None
    return [r for n in xml for r in parse_extract(z.read(n))]


def _name(p: Mapping[str, str]) -> str | None:
    return _text(p.get("entityName") or p.get("businessName")) or _text(
        " ".join(x for x in (p.get("firstName"), p.get("initial"), p.get("lastName")) if x)
    )


class VermontTransferArchive(Adapter):
    source_id: ClassVar[str] = "vt.tax.property_transfers_archive"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("lastName", "firstName", "initial", "street",
                                             "entityName", "businessName",
                                             "propertyLocationStreet")  # fmt: skip

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=600.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "recorder",
            "jurisdiction": "50",
            "access_method": "bulk",
            "base_url": LIST,
            "terms_url": "https://tax.vermont.gov/data-and-statistics/property-transfer-tax-data",
            "terms_summary": (
                "Vermont Department of Taxes property transfer tax return extracts (32 V.S.A. "
                "9606), a public container listed and downloaded with no login; public "
                "information, no license grant or commercial-use restriction stated (same "
                "data as the VCGI layer used by vt.tax.property_transfers)."
            ),
            "terms_checked_on": "2026-11-26",
            "robots_checked_on": "2026-11-26",
            "cost_model": "free",
        }

    def _archives(self) -> list[tuple[int, str]]:
        resp = self.client.get(LIST)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status} listing the container")
        names = re.findall(r"<Name>([^<]+)</Name>", resp.content.decode("utf-8", "replace"))
        found = []
        for n in names:
            m = ARCHIVE.match(n)
            if m and FIRST_YEAR <= int(m.group(1)) <= LAST_YEAR:
                found.append((int(m.group(1)), n))
        return sorted(found)

    def partitions(self) -> Iterator[dict[str, str]]:
        for _year, name in self._archives():
            yield {"blob": name}

    def fetch(self, request: FetchRequest) -> Fetched:
        name = request.params["blob"]
        m = ARCHIVE.match(name)
        if m is None or not FIRST_YEAR <= int(m.group(1)) <= LAST_YEAR:
            raise ValueError(f"not an archive zip in range: {name!r}")
        url = f"{BASE}/{name}"
        resp = self.client.get(url)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status} for {name}")
        rows = parse_zip(resp.content) or []
        limit = request.params.get("limit")
        if limit:
            rows = rows[: int(limit)]
        body = canonical_json({"blob": name, "rows": rows})
        return Fetched(self.source_id, url, resp.retrieved_at, 200, body, "application/json")

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        seen: set[str] = set()
        for r in sorted(json.loads(fetched.content).get("rows") or [],
                        key=lambda x: str(x.get("DLN"))):  # fmt: skip
            dln, closed = _text(r.get("DLN")), _date(r.get("closingDate"))
            if not dln or closed is None or closed >= CUTOFF or dln in seen:
                continue
            seen.add(dln)
            ticked = [f.removeprefix("financing").lower() for f in FINANCING
                      if str(r.get(f) or "").lower() == "true"]  # fmt: skip
            raw = "Vermont property transfer tax return"
            if ticked:
                raw += f" (financing: {', '.join(ticked)})"
            header = {k: v for k, v in r.items() if k not in ("sellers", "buyers")}
            ctx = RecordContext(fetched, "50", dln, "pttr_return", header)
            uid = stable_id(self.source_id, "return", dln)
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=dln, book_type=None,
                book=None, page=None, doc_type_raw=raw, doc_type="DEED", recorded_on=closed,
                recorded_seq=None, executed_on=None, consideration=_money(r.get("totalPricePaid")),
                principal_amount=None, max_secured_amount=None, maturity_date=None,
                amount_source=None, legal_desc_raw=None,
            )  # fmt: skip
            lot = span_uid(r.get("span"), r.get("countyCode"))
            if lot:
                yield ctx.fact("instrument_parcel", instrument_uid=uid, parcel_uid=lot,
                               method="index_parcel_id",
                               evidence={"span": r.get("span"),
                                         "countyCode": r.get("countyCode")})  # fmt: skip
            for role, people in (("grantor", r.get("sellers") or []),
                                 ("grantee", r.get("buyers") or [])):  # fmt: skip
                for seq, p in enumerate(people, start=1):
                    name = _name(p)
                    if name is None:
                        continue
                    z = str(p.get("postal") or "")[:5]
                    zip5 = z if z.isdigit() and len(z) == 5 else None
                    addr = normalized_address(_text(p.get("street")), _text(p.get("city")),
                                              _text(p.get("state")), zip5)  # fmt: skip
                    if addr is not None:
                        yield NormalizedRow("address", addr)
                    nc = classify(name)
                    pid = stable_id(self.source_id, dln, role, str(seq), clean(name))
                    yield ctx.fact("party", party_id=pid, raw_name=name,
                                   party_kind=nc.party_kind, org_form=nc.org_form,
                                   org_name_norm=nc.org_name_norm,
                                   address_id=addr["address_id"] if addr else None)  # fmt: skip
                    yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid,
                                   role=role, seq=seq)  # fmt: skip

    def health(self) -> HealthReport:
        n = len(self._archives())
        return HealthReport(self.source_id, n >= 8, datetime.now(UTC), f"{n} archive zips")
