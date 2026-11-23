"""Hernando County (FL) Clerk: daily Civil Data Index (new civil filings, every party with
its street address). Config: config/courts_state/fl.hernando.civil.yaml.

One pipe-delimited file per day on the clerk's open subscriber file site, no header:

    Case Type Code|Case Type Description|Case Number|Filing Type|Case Filed Date|Case Status|
    Party Type|Party Name|Address 1|Address 2|City|State|Zip|Party Attorney

Each case becomes a court_case (fl.hernando:<case number>) with its parties and their
addresses. Domestic-relations (DR) rows are dropped at fetch time and never stored.

Source: https://subscriber.hernandoclerk.com/data_files/civil_data/ (robots.txt 404: no
restrictions; checked 2026-11-23).
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from functools import cache
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

SITE = "https://subscriber.hernandoclerk.com/"
BASE = SITE + "data_files/civil_data/"
CONFIG = "courts_state/fl.hernando.civil.yaml"
COUNTY = "12053"
COURT_ID = "fl.5th_circuit.hernando.civil"
FIELDS = ("CaseTypeCode", "CaseTypeDescription", "CaseNumber", "FilingType", "CaseFiledDate",
          "CaseStatus", "PartyType", "PartyName", "Address1", "Address2", "City", "State",
          "Zip", "PartyAttorney")  # fmt: skip
PII_FIELDS: tuple[str, ...] = ("PartyName", "Address1", "Address2", "PartyAttorney")
_FILE = re.compile(r"civil_data/((?:\d{4}-\d{2}-\d{2}|Civil Data [\d -]+)\.csv)")
_NAME = re.compile(r"(?:\d{4}-\d{2}-\d{2}|Civil Data \d{4}-\d{2}-\d{2} - \d{4}-\d{2}-\d{2})\.csv")


@dataclass(frozen=True)
class CivilConfig:
    case_type_codes: frozenset[str]
    party_roles: Mapping[str, str]
    terms: Mapping[str, Any]


@cache
def load_config() -> CivilConfig:
    import yaml

    d = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    return CivilConfig(frozenset(d["case_type_codes"]), dict(d["party_roles"]), dict(d["terms"]))


def us_date(value: str | None) -> date | None:
    """'11/19/2026' -> date; blank or malformed -> None."""
    parts = (value or "").strip().split(" ")[0].split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    try:
        return date(int(parts[2]), int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def parse_rows(text: str, codes: frozenset[str]) -> list[dict[str, str]]:
    """Pipe-delimited rows -> dicts of the non-blank fields, kept case types only."""
    out = []
    for line in text.splitlines():
        cells = line.split("|")
        if len(cells) < len(FIELDS) - 1 or cells[0].strip() not in codes:
            continue
        row = {f: " ".join(cells[i].split()) for i, f in enumerate(FIELDS) if i < len(cells)}
        out.append({k: v for k, v in row.items() if v})
    return out


def file_key(name: str) -> tuple[str, str]:
    """Sort key: the back-file first, then days in order."""
    return ("0", name) if name.startswith("Civil Data") else ("1", name)


class HernandoCivilFilings(Adapter):
    source_id: ClassVar[str] = "fl.hernando.civil.filings"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = PII_FIELDS
    # The back-file overlaps the daily files of 2024-04..07: one store, repeats kept once.
    single_store: ClassVar[bool] = True

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.config = load_config()
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        t = self.config.terms
        return {
            "source_id": self.source_id,
            "kind": "court",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": BASE,
            "terms_url": t["url"],
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t["robots_checked_on"],
            "cost_model": t["cost_model"],
        }

    def _text(self, url: str) -> str:
        resp = self.client.get(url)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        return resp.content.decode("utf-8", errors="replace")

    def files(self) -> list[str]:
        return sorted(set(_FILE.findall(self._text(SITE))), key=file_key)

    def partitions(self) -> Iterator[dict[str, str]]:
        for name in self.files():
            yield {"file": name}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: file (a name from the listing); limit (fixtures): first N rows."""
        name = request.params["file"]
        if not _NAME.fullmatch(name):
            raise ValueError(f"not a civil data file name: {name!r}")
        url = BASE + urllib.parse.quote(name)
        rows = parse_rows(self._text(url), self.config.case_type_codes)
        if "limit" in request.params:
            rows = rows[: int(request.params["limit"])]
        body = canonical_json({"file": name, "rows": rows})
        return Fetched(self.source_id, url, self.client.now(), 200, body, "application/json")

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        from equity.adapters.record import pseudonym  # the recorder imports the registry

        data = json.loads(content)
        for row in data["rows"]:
            for col in PII_FIELDS:
                if row.get(col):
                    row[col] = pseudonym("ADDRESS" if "Address" in col else col, row[col])
        return canonical_json(data)

    def health(self) -> HealthReport:
        now = self.client.now()
        try:
            names = self.files()
            rows = parse_rows(self._text(BASE + urllib.parse.quote(names[-1])),
                              self.config.case_type_codes) if names else []  # fmt: skip
        except (RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        ok = bool(names) and all(r.get("CaseNumber") for r in rows)
        detail = f"{names[-1]}: {len(rows)} rows" if ok else "no files or bad layout"
        return HealthReport(self.source_id, ok, now, detail, FIELDS)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = self.config
        today = fetched.retrieved_at.date()
        by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in json.loads(fetched.content)["rows"]:
            if r.get("CaseNumber") and r.get("CaseTypeCode") in cfg.case_type_codes:
                by_case[re.sub(r"\s+", "", r["CaseNumber"].upper())].append(r)
        for norm in sorted(by_case):
            group = sorted(by_case[norm], key=canonical_json)
            first = group[0]
            uid = f"fl.hernando:{norm}"
            ctx = RecordContext(fetched, COUNTY, norm, "civil_filing", group)
            yield ctx.source_record()
            filed = us_date(first.get("CaseFiledDate"))
            yield ctx.fact(
                "court_case", case_uid=uid, court_id=COURT_ID,
                case_number_raw=first["CaseNumber"], case_number_norm=norm,
                case_type=first.get("CaseTypeDescription") or None,
                nature_of_suit=first.get("FilingType") or None,
                filed_on=filed if filed is not None and filed <= today else None,
                closed_on=None, status=first.get("CaseStatus") or None,
            )  # fmt: skip
            seen: set[tuple[str, str]] = set()
            for r in group:
                name = r.get("PartyName", "")
                role = cfg.party_roles.get(r.get("PartyType", ""), "other")
                if not name or (role, clean(name)) in seen:
                    continue
                seen.add((role, clean(name)))
                street = " ".join(x for x in (r.get("Address1"), r.get("Address2")) if x) or None
                zip5: str | None = r.get("Zip", "")[:5]
                if not (zip5 and zip5.isdigit() and len(zip5) == 5):
                    zip5 = None
                addr = normalized_address(street, r.get("City"), r.get("State"), zip5)
                if addr is not None:
                    yield NormalizedRow("address", addr)
                nc = classify(name)
                party_id = stable_id(self.source_id, uid, role, clean(name))
                yield ctx.fact(
                    "party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
                    org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                    address_id=None if addr is None else addr["address_id"],
                )  # fmt: skip
                yield ctx.fact("case_party", case_uid=uid, party_id=party_id, role=role)
