"""Hillsborough County (FL) Clerk: Circuit and County Civil public data files.

Three CSV series, each its own source because they overlap in what they describe:

- fl.hillsborough.civil.cases       monthly "Bulk Data Case File": cases filed that month, with
                                     status and the latest judgment code (kept one year)
- fl.hillsborough.civil.filings     daily "CivilFiling": every party of each new case, with
                                     address and attorney (kept about a month)
- fl.hillsborough.garnishment       weekly "Return Of Service And Garnishment Data": judgment
                                     creditor, debtor (with address), garnishee, and the dates
                                     writs of garnishment were filed and issued

All three use case_uid fl.hillsborough:<case number>, the same number the Official Records
index carries in its legal column, so a recorded judgment can be tied to its case.

Source: https://publicrec.hillsclerk.com/Civil/ (robots.txt 404: no restrictions; checked
2026-11-16). No terms found on the folders.
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import cache
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address, parse_full_address
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

BASE = "https://publicrec.hillsclerk.com/Civil/"
CONFIG = "courts_state/fl.hillsborough.civil.yaml"
COUNTY = "12057"
COURT_ID = "fl.13th_circuit.hillsborough.civil"
_VS = re.compile(r"\s+vs\.?\s+", re.IGNORECASE)
_ET_AL = re.compile(r",?\s+et\s+al\.?$", re.IGNORECASE)


@dataclass(frozen=True)
class CivilConfig:
    judgment_codes: Mapping[str, str]
    garnishment_events: Mapping[str, str]
    filing_party_roles: Mapping[str, str]


@cache
def load_config() -> CivilConfig:
    import yaml

    d = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    return CivilConfig(
        judgment_codes=dict(d["judgment_codes"]),
        garnishment_events=dict(d["garnishment_events"]),
        filing_party_roles=dict(d["filing_party_roles"]),
    )


def case_norm(raw: str) -> str:
    return re.sub(r"\s+", "", raw.upper())


def case_uid(raw: str) -> str:
    return f"fl.hillsborough:{case_norm(raw)}"


def us_date(value: str | None) -> date | None:
    """'10/01/2026' or '11/28/2006 12:00:00 AM' -> date."""
    if not value:
        return None
    head = value.strip().split(" ")[0]
    parts = head.split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    try:
        return date(int(parts[2]), int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def split_style(style: str) -> tuple[str | None, str | None]:
    """'Smith, Ann vs Acme LLC et al' -> ('Smith, Ann', 'Acme LLC')."""
    sides = _VS.split(" ".join(style.split()), maxsplit=1)
    if len(sides) != 2:
        return None, None
    left, right = (_ET_AL.sub("", s).strip() or None for s in sides)
    return left, right


def read_csv(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]


def write_csv(rows: list[dict[str, str]], fields: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


class _CivilFiles(Adapter):
    """One CSV per partition, from one folder; subclasses say which and how to read it."""

    access_method: ClassVar[str] = "bulk"
    adapter_version: ClassVar[str] = "1"
    folder: ClassVar[str]
    file_pattern: ClassVar[re.Pattern[str]]
    pii_columns: ClassVar[tuple[str, ...]]
    style_columns: ClassVar[tuple[str, ...]] = ()

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    @property
    def folder_url(self) -> str:
        return BASE + urllib.parse.quote(self.folder) + "/"

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "court",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": self.folder_url,
            "terms_url": "https://www.hillsclerk.com/records-and-reports/public-data-files",
            "terms_summary": "Public data files, no login; no terms of use found on the folder.",
            "terms_checked_on": date(2026, 11, 16),
            "robots_checked_on": date(2026, 11, 16),
            "cost_model": "free",
        }

    def _get(self, url: str) -> str:
        resp = self.client.get(url)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        return resp.content.decode("utf-8", errors="replace")

    def files(self) -> list[str]:
        names = set(self.file_pattern.findall(self._get(self.folder_url)))
        return sorted(names, key=lambda n: (self.file_date(n), n))

    def file_date(self, name: str) -> date:
        raise NotImplementedError

    def partitions(self) -> Iterator[dict[str, str]]:
        for name in self.files():
            yield {"file": name}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: file (a name from the folder listing); limit (fixtures): first N rows."""
        name = request.params["file"]
        if not self.file_pattern.fullmatch(name):
            raise ValueError(f"not a {self.source_id} file name: {name!r}")
        url = self.folder_url + urllib.parse.quote(name)
        text = self._get(url)
        if "limit" in request.params:
            rows = read_csv(text)
            fields = list(rows[0]) if rows else []
            text = write_csv(rows[: int(request.params["limit"])], fields)
        return Fetched(
            source_id=self.source_id,
            request=url,
            retrieved_at=datetime.now(UTC),
            http_status=200,
            content=canonical_json({"file": name, "csv": text}),
            content_type="application/json",
        )

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        from equity.adapters.record import pseudonym  # the recorder imports the registry

        data = json.loads(content)
        rows = read_csv(data["csv"])
        for row in rows:
            for col in cls.pii_columns:
                if row.get(col):
                    row[col] = pseudonym("ADDRESS" if "addr" in col.lower() else col, row[col])
            for col in cls.style_columns:
                left, right = split_style(row.get(col, ""))
                if left or right:
                    row[col] = " vs ".join(pseudonym(col, s or "-") for s in (left, right))
        data["csv"] = write_csv(rows, list(rows[0]) if rows else [])
        return canonical_json(data)

    def rows(self, fetched: Fetched) -> tuple[str, list[dict[str, str]]]:
        data = json.loads(fetched.content)
        return str(data["file"]), read_csv(data["csv"])

    def _party(
        self, ctx: RecordContext, uid: str, role: str, name: str, address: dict[str, Any] | None
    ) -> Iterator[NormalizedRow]:
        if address is not None:
            yield NormalizedRow("address", address)
        nc = classify(name)
        party_id = stable_id(self.source_id, uid, role, clean(name))
        yield ctx.fact(
            "party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
            org_form=nc.org_form, org_name_norm=nc.org_name_norm,
            address_id=None if address is None else address["address_id"],
        )  # fmt: skip
        yield ctx.fact("case_party", case_uid=uid, party_id=party_id, role=role)

    def health(self) -> HealthReport:
        try:
            names = self.files()
        except (RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        ok = bool(names)
        return HealthReport(self.source_id, ok, datetime.now(UTC),
                            "ok" if ok else "no files listed", tuple(names[-1:]))  # fmt: skip


class HillsboroughCivilCases(_CivilFiles):
    source_id: ClassVar[str] = "fl.hillsborough.civil.cases"
    folder: ClassVar[str] = "bulkdata"
    file_pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"Bulk Data Case File_ \d{2}-\d{2}-\d{4}\.csv"
    )
    pii_columns: ClassVar[tuple[str, ...]] = ()
    style_columns: ClassVar[tuple[str, ...]] = ("Style",)

    def file_date(self, name: str) -> date:
        m = re.search(r"(\d{2})-(\d{2})-(\d{4})", name)
        assert m is not None
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = load_config()
        _, rows = self.rows(fetched)
        today = fetched.retrieved_at.astimezone(UTC).date()
        by_case: dict[str, dict[str, str]] = {}
        for r in rows:
            if r.get("CaseNbr"):
                by_case.setdefault(case_norm(r["CaseNbr"]), r)
        for norm in sorted(by_case):
            r = by_case[norm]
            uid = case_uid(norm)
            ctx = RecordContext(fetched, COUNTY, norm, "civil_case", r)
            yield ctx.source_record()
            filed = us_date(r.get("DtFile"))
            yield ctx.fact(
                "court_case", case_uid=uid, court_id=COURT_ID, case_number_raw=r["CaseNbr"],
                case_number_norm=norm, case_type=r.get("CaseType") or None,
                nature_of_suit=r.get("CauseDescription") or None,
                filed_on=filed if filed is not None and filed <= today else None,
                closed_on=None, status=r.get("CaseStatus") or None,
            )  # fmt: skip
            plaintiff, defendant = split_style(r.get("Style", ""))
            for role, name in (("plaintiff", plaintiff), ("defendant", defendant)):
                if name:
                    yield from self._party(ctx, uid, role, name, None)
            code = r.get("JudgmentCode", "")
            entered = us_date(r.get("JudgmentDate"))
            if code in cfg.judgment_codes and entered is not None and entered <= today:
                yield ctx.fact(
                    "judgment", judgment_uid=f"{uid}:{code}:{entered.isoformat()}",
                    case_uid=uid, entered_on=entered, principal=None, interest=None, costs=None,
                    rate=None, judgment_type=cfg.judgment_codes[code], lien_instrument_uid=None,
                )  # fmt: skip


class HillsboroughCivilFilings(_CivilFiles):
    source_id: ClassVar[str] = "fl.hillsborough.civil.filings"
    folder: ClassVar[str] = "dailyfilings"
    file_pattern: ClassVar[re.Pattern[str]] = re.compile(r"CivilFiling_\d{8}\.csv")
    pii_columns: ClassVar[tuple[str, ...]] = (
        "FirstName", "MiddleName", "LastName/CompanyName", "PartyAddress", "Attorney",
    )  # fmt: skip
    style_columns: ClassVar[tuple[str, ...]] = ("Title",)
    # A case refiled or amended can come back in a later day's file.
    single_store: ClassVar[bool] = True

    def file_date(self, name: str) -> date:
        d = re.search(r"(\d{8})", name)
        assert d is not None
        s = d.group(1)
        return date(int(s[:4]), int(s[4:6]), int(s[6:]))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = load_config()
        _, rows = self.rows(fetched)
        today = fetched.retrieved_at.astimezone(UTC).date()
        by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in rows:
            if r.get("CaseNumber"):
                by_case[case_norm(r["CaseNumber"])].append(r)
        for norm in sorted(by_case):
            group = sorted(by_case[norm], key=canonical_json)
            first = group[0]
            uid = case_uid(norm)
            ctx = RecordContext(fetched, COUNTY, norm, "civil_filing", group)
            yield ctx.source_record()
            filed = us_date(first.get("FilingDate"))
            yield ctx.fact(
                "court_case", case_uid=uid, court_id=COURT_ID,
                case_number_raw=first["CaseNumber"], case_number_norm=norm,
                case_type=first.get("CaseTypeDescription") or None, nature_of_suit=None,
                filed_on=filed if filed is not None and filed <= today else None,
                closed_on=None, status=None,
            )  # fmt: skip
            seen: set[tuple[str, str]] = set()
            for r in group:
                parts = (r.get("FirstName"), r.get("MiddleName"), r.get("LastName/CompanyName"))
                name = " ".join(p for p in parts if p)
                role = cfg.filing_party_roles.get(r.get("PartyType", ""), "other")
                if not name or (role, clean(name)) in seen:
                    continue
                seen.add((role, clean(name)))
                address = None
                if r.get("PartyAddress"):
                    line, city, st, zip5 = parse_full_address(r["PartyAddress"])
                    address = normalized_address(line, city, st, zip5)
                yield from self._party(ctx, uid, role, name, address)


class HillsboroughGarnishment(_CivilFiles):
    source_id: ClassVar[str] = "fl.hillsborough.garnishment"
    folder: ClassVar[str] = "Circuit and County Civil with Return of Service and Garnishment Data"
    file_pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"ReturnOfServiceAndGarnishmentData_\d{4}-\d{2}-\d{2}\.csv"
    )
    pii_columns: ClassVar[tuple[str, ...]] = (
        "PlaintiffName", "GarnisheeName", "DefendantName", "Address1", "Address2", "Address3",
        "Service_Return_Date",
    )  # fmt: skip
    # Weekly lists overlap: load every week into one store so repeats are kept, not doubled.
    single_store: ClassVar[bool] = True

    def file_date(self, name: str) -> date:
        d = re.search(r"(\d{4})-(\d{2})-(\d{2})", name)
        assert d is not None
        return date(int(d.group(1)), int(d.group(2)), int(d.group(3)))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = load_config()
        _, rows = self.rows(fetched)
        today = fetched.retrieved_at.astimezone(UTC).date()
        by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in rows:
            if r.get("CaseNbr"):
                by_case[case_norm(r["CaseNbr"])].append(r)
        for norm in sorted(by_case):
            group = sorted(by_case[norm], key=canonical_json)
            first = group[0]
            uid = case_uid(norm)
            ctx = RecordContext(fetched, COUNTY, norm, "garnishment_case", group)
            yield ctx.source_record()
            filed = us_date(first.get("DtFile"))
            yield ctx.fact(
                "court_case", case_uid=uid, court_id=COURT_ID, case_number_raw=first["CaseNbr"],
                case_number_norm=norm, case_type=first.get("CaseTypeDesc") or None,
                nature_of_suit=None,
                filed_on=filed if filed is not None and filed <= today else None,
                closed_on=None, status=first.get("CaseStatDesc") or None,
            )  # fmt: skip
            parties: dict[tuple[str, str], dict[str, Any] | None] = {}
            entries: set[tuple[date, str]] = set()
            for r in group:
                street = " ".join(p for p in (r.get("Address1"), r.get("Address2"),
                                              r.get("Address3")) if p) or None  # fmt: skip
                zip5 = r.get("ZIP", "")[:5]
                debtor_addr = normalized_address(street, r.get("City") or None,
                                                 r.get("State") or None,
                                                 zip5 if zip5.isdigit() and len(zip5) == 5
                                                 else None)  # fmt: skip
                for role, col, addr in (("plaintiff", "PlaintiffName", None),
                                        ("defendant", "DefendantName", debtor_addr),
                                        ("garnishee", "GarnisheeName", None)):  # fmt: skip
                    name = " ".join(r.get(col, "").split())
                    if name:
                        parties.setdefault((role, name), addr)
                for col, text in cfg.garnishment_events.items():
                    when = us_date(r.get(col))
                    if when is not None and when <= today:
                        garnishee = " ".join(r.get("GarnisheeName", "").split())
                        entries.add((when, f"{text}: {garnishee}" if garnishee else text))
            for (role, name), addr in sorted(parties.items(), key=lambda kv: kv[0]):
                yield from self._party(ctx, uid, role, name, addr)
            for when, text in sorted(entries):
                yield ctx.fact("docket_entry", case_uid=uid, entry_no=None, entry_date=when,
                               text=text)  # fmt: skip
