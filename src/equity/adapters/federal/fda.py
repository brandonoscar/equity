"""FDA Drug Establishments Current Registration Site (DECRS): every establishment currently
registered with FDA to make, repack, relabel, analyze or import human and animal drugs
(~10k, about half in the U.S.), from the daily drls_reg.zip (a tab-separated drls_reg.txt
plus the same rows as .xls).

Columns: FEI_NUMBER (FDA Establishment Identifier), DUNS_NUMBER, FIRM_NAME, ADDRESS (one line:
'street, city, State (ST) ZIP, United States (USA)'), EXPIRATION_DATE, OPERATIONS,
ESTABLISHMENT_CONTACT_NAME / _EMAIL, AGENT_DETAILS (the U.S. agent: 'DUNS - name - e-mail -
phone'), REGISTRANT_NAME, REGISTRANT_DUNS, REGISTRANT_CONTACT_NAME / _EMAIL, EXCLUSION_FLAG.
E-mail addresses and the agent's e-mail and phone are not kept; ADDRESS is kept split into
STREET and LOCALITY ('city, State (ST) ZIP, country') where the U.S. form is recognized.

What is emitted, from existing tables only (one source record per FEI number, record_type
drug_establishment):

- business: sos_id FEI:<FEI number>, the firm name, status 'registered', valid from the
  retrieval date (the file lists current registrations; the expiration date stays in the
  raw record), principal address = the establishment's U.S. address.
- business_role + party (role 'other'): the establishment contact (title ESTABLISHMENT
  CONTACT) and the registrant's contact (REGISTRANT CONTACT), people; the registrant
  (REGISTRANT) and the U.S. agent (US AGENT), as named.
- address: the U.S. address (foreign ones stay in the raw record).

Source: https://www.fda.gov/drugs/drug-approvals-and-databases/drug-establishments-current-registration-site
(file https://www.accessdata.fda.gov/cder/drls_reg.zip). U.S. government data, free, no
login; accessdata.fda.gov robots.txt (read 2026-11-25) allows /cder/.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
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
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json

PAGE = (
    "https://www.fda.gov/drugs/drug-approvals-and-databases/"
    "drug-establishments-current-registration-site"
)
URL = "https://www.accessdata.fda.gov/cder/drls_reg.zip"
CHECKED_ON = "2026-11-25"
KEEP = ("FEI_NUMBER", "DUNS_NUMBER", "FIRM_NAME", "ADDRESS", "EXPIRATION_DATE", "OPERATIONS",
        "ESTABLISHMENT_CONTACT_NAME", "AGENT_DETAILS", "REGISTRANT_NAME", "REGISTRANT_DUNS",
        "REGISTRANT_CONTACT_NAME", "EXCLUSION_FLAG")  # fmt: skip
PEOPLE = ("ESTABLISHMENT_CONTACT_NAME", "REGISTRANT_CONTACT_NAME")
_US = re.compile(
    r"^(?P<street>.+?),\s*(?P<city>[^,]+),\s*[^,(]*\((?P<st>[A-Z]{2})\)\s*(?P<zip>\d{5})?"
    r"(?:-?\d{4})?\s*,\s*United States \(USA\)\s*$"
)
_EMAIL = re.compile(r"\S+@\S+")


def split_address(line: Any) -> dict[str, str]:
    """STREET and LOCALITY of a U.S. one-line address; anything else is all STREET."""
    s = text(line)
    if s is None:
        return {}
    m = _US.match(s)
    if m is None:
        return {"STREET": s}
    return {"STREET": m["street"], "LOCALITY": s[m.end("street") :].lstrip(", ")}


def us_address(r: Mapping[str, Any]) -> dict[str, Any] | None:
    """'233 S. Secrest Ave' + 'Monroe, North Carolina (NC) 28112, United States (USA)'."""
    street, locality = text(r.get("STREET")), text(r.get("LOCALITY"))
    m = _US.match(f"{street}, {locality}") if street and locality else None
    if m is None:
        return None
    return address(m["street"], m["city"], m["st"], m["zip"])


def agent_name(details: Any) -> str | None:
    """The name in 'DUNS - name - e-mail - phone' (dashes inside the name are kept)."""
    parts = [p.strip() for p in (text(details) or "").split(" - ")]
    if len(parts) < 2:
        return None
    name = " - ".join(p for p in parts[1:] if not _EMAIL.search(p) and not
                      re.fullmatch(r"[\d\s().+-]+", p))  # fmt: skip
    return text(name)


def read_rows(content: bytes, limit: int | None = None) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        member = next(i for i in zf.infolist() if i.filename.lower().endswith(".txt"))
        raw = zf.read(member).decode("latin-1")
    reader = csv.DictReader(io.StringIO(raw, newline=""), delimiter="\t",
                            quoting=csv.QUOTE_NONE)  # fmt: skip
    if reader.fieldnames is None:
        raise RuntimeError("empty DECRS file")
    reader.fieldnames = [f.strip() for f in reader.fieldnames]
    if "FEI_NUMBER" not in reader.fieldnames:
        raise RuntimeError("not a DECRS file: no FEI_NUMBER column")
    out: list[dict[str, str]] = []
    for row in reader:
        if limit is not None and len(out) >= limit:
            break
        r = {k: v for k in KEEP if (v := text(row.get(k))) is not None}
        r.update(split_address(r.pop("ADDRESS", None)))
        if "AGENT_DETAILS" in r:
            r["AGENT_DETAILS"] = agent_name(r["AGENT_DETAILS"]) or ""
            r = {k: v for k, v in r.items() if v}
        out.append(r)
    return out


class FDADrugEstablishments(Adapter):
    source_id: ClassVar[str] = "us.fda.drug_establishments"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = (*PEOPLE, "AGENT_DETAILS", "STREET")

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a federal registry of establishments
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": URL,
            "terms_url": PAGE,
            "terms_summary": (
                "FDA Drug Establishments Current Registration Site, drls_reg.zip rebuilt "
                "daily; U.S. government data, free, no login. robots.txt allows /cder/. "
                "E-mail addresses and phone numbers not kept."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {"file": "drls_reg"}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: file ('drls_reg', the only partition); limit (fixtures: the first rows,
        U.S. establishments first)."""
        p = request.params
        if p.get("file", "drls_reg") != "drls_reg":
            raise ValueError(f"bad file {p['file']!r}")
        resp = self.client.get(URL)
        if resp.status != 200 or not resp.content.startswith(b"PK"):
            raise RuntimeError(f"{URL}: HTTP {resp.status} ({resp.content_type}); not a zip")
        rows = read_rows(resp.content)
        if "limit" in p:
            rows.sort(key=lambda r: us_address(r) is None)
            rows = rows[: int(p["limit"])]
        return Fetched(self.source_id, URL, resp.retrieved_at, 200,
                       canonical_json({"url": URL, "rows": rows}), "application/json")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        """People's names, the U.S. agent and the street pseudonymized (locality kept)."""
        return scrub_json(content, (*PEOPLE, "AGENT_DETAILS"), ("STREET",))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for r in sorted(data.get("rows") or [], key=canonical_json):
            fei = "".join(ch for ch in str(r.get("FEI_NUMBER") or "") if ch.isdigit())
            name = text(r.get("FIRM_NAME"))
            if not fei or name is None or fei in seen:
                continue
            seen.add(fei)
            addr = us_address(r)
            ctx = RecordContext(fetched, jurisdiction(addr["state"] if addr else None), fei,
                                "drug_establishment", r)  # fmt: skip
            yield ctx.source_record()
            holders = []
            for col, title, person in (
                ("ESTABLISHMENT_CONTACT_NAME", "ESTABLISHMENT CONTACT", True),
                ("REGISTRANT_NAME", "REGISTRANT", False),
                ("REGISTRANT_CONTACT_NAME", "REGISTRANT CONTACT", True),
                ("AGENT_DETAILS", "US AGENT", False),
            ):  # fmt: skip
                if (who := text(r.get(col))) and any(ch.isalpha() for ch in who):
                    holders.append(Holder("other", title, who, person=person))
            yield from emit_business(ctx, source_id=self.source_id, sos_id=f"FEI:{fei}",
                                     name=name, valid_from=observed, status="registered",
                                     principal=addr, holders=holders)  # fmt: skip

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            resp = self.client.get(URL)
            rows = read_rows(resp.content) if resp.status == 200 else []
        except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        return HealthReport(self.source_id, len(rows) > 1000, now, f"rows={len(rows)}", KEEP,
                            rows=len(rows))  # fmt: skip
