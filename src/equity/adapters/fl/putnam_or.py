"""Putnam County (FL) Clerk: Official Records Index from the county's Open Data downloads.

The county's Open Data page (config/recorders/fl.putnam.or.yaml) offers the Clerk's whole
Official Records Index as free zip files: a history file (October 1983 to the end of last
year) and a current-year file (to last Sunday). Each holds one pipe-delimited text file:

    book|page|file date (MM-DD-YYYY)|from party|to party|instrument|code|description

One row per party (a row names either the from party or the to party). Codes are the same
as Hillsborough's index. A judgment's or lien's description usually starts with its amount
("$1,622.55 ET AL"), kept as principal_amount.

Partitions: one per file-date year of the history file (first_history_year on), then the
current-year file. The history zip (~46 MB) is downloaded once per adapter instance and
cut by year in memory.

Source: https://apps.putnam-fl.com/bocc/putsubs/main.php (robots.txt 404: no restrictions;
checked 2026-11-23).
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date
from decimal import Decimal, InvalidOperation
from functools import cache
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

BASE = "https://apps.putnam-fl.com/bocc/putsubs/subscriptions/coc/"
FILES = {"history": "orimaster.zip", "year": "oriyear.zip"}
CONFIG = "recorders/fl.putnam.or.yaml"
COUNTY = "12107"
FIELDS = ("book", "page", "date", "from", "to", "instrument", "code", "description")
PII_FIELDS: tuple[str, ...] = ("from", "to")
_AMOUNT = re.compile(r"^\s*\$\s*([\d,]+(?:\.\d{1,2})?)")


@dataclass(frozen=True)
class OrCode:
    doc_type: str
    frm: str
    to: str


@dataclass(frozen=True)
class PutnamConfig:
    codes: Mapping[str, OrCode]
    first_history_year: int
    amount_doc_types: frozenset[str]
    exclude_codes: frozenset[str]
    exclude_description_patterns: tuple[re.Pattern[str], ...]
    terms: Mapping[str, Any]


@cache
def load_config() -> PutnamConfig:
    import yaml

    d = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    return PutnamConfig(
        codes={
            str(k): OrCode(str(v["doc_type"]), str(v["frm"]), str(v["to"]))
            for k, v in d["codes"].items()
        },
        first_history_year=int(d["first_history_year"]),
        amount_doc_types=frozenset(d["amount_doc_types"]),
        exclude_codes=frozenset(d["exclude_codes"]),
        exclude_description_patterns=tuple(
            re.compile(p) for p in d["exclude_description_patterns"]
        ),
        terms=dict(d["terms"]),
    )


def file_date(value: str) -> date | None:
    """'10-03-2007' -> date (a calendar date: no time zone involved)."""
    parts = value.strip().split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    try:
        return date(int(parts[2]), int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def amount(description: str) -> Decimal | None:
    """'$1,622.55 ET AL' -> Decimal('1622.55'); no leading amount or zero -> None."""
    m = _AMOUNT.match(description)
    if m is None:
        return None
    try:
        value = Decimal(m.group(1).replace(",", "")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return value if value > 0 else None


def parse_lines(text: str, year: int | None = None) -> list[dict[str, str]]:
    """Pipe-delimited rows -> dicts (blank fields dropped), optionally one file-date year."""
    out = []
    suffix = None if year is None else f"-{year}"
    for line in text.splitlines():
        cells = line.split("|")
        if len(cells) < len(FIELDS):
            continue
        if suffix is not None and not cells[2].strip().endswith(suffix):
            continue
        row = {f: " ".join(cells[i].split()) for i, f in enumerate(FIELDS)}
        out.append({k: v for k, v in row.items() if v})
    return out


def zip_text(content: bytes) -> str:
    """The index text file inside a download zip (the help file is skipped)."""
    z = zipfile.ZipFile(io.BytesIO(content))
    names = [n for n in z.namelist() if n.lower().startswith("rec_")]
    if not names:
        raise RuntimeError(f"no Rec_*.txt in zip: {z.namelist()}")
    return z.read(names[0]).decode("latin-1")


class PutnamOfficialRecords(Adapter):
    source_id: ClassVar[str] = "fl.putnam.or"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = PII_FIELDS

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.config = load_config()
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=900.0)
        self._texts: dict[str, str] = {}

    def source_row(self) -> Mapping[str, Any]:
        t = self.config.terms
        return {
            "source_id": self.source_id,
            "kind": "recorder",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": BASE,
            "terms_url": t["url"],
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t["robots_checked_on"],
            "cost_model": t["cost_model"],
        }

    def _text(self, kind: str) -> str:
        if kind not in self._texts:
            url = BASE + FILES[kind]
            resp = self.client.get(url)
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status} from {url}")
            self._texts = {kind: zip_text(resp.content)}  # keep one file in memory at a time
        return self._texts[kind]

    def partitions(self) -> Iterator[dict[str, str]]:
        """History years oldest first, then the current year's file."""
        this_year = self.client.now().astimezone(UTC).year
        for y in range(self.config.first_history_year, this_year):
            yield {"file": "history", "year": str(y)}
        yield {"file": "year"}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: file (history | year); year (history only); limit (fixtures): the first N
        instruments' rows."""
        p = request.params
        kind = p["file"]
        if kind not in FILES:
            raise ValueError(f"file must be one of {sorted(FILES)}: {kind!r}")
        year = int(p["year"]) if kind == "history" else None
        rows = parse_lines(self._text(kind), year)
        if "limit" in p:
            keep: dict[str, None] = {}
            for r in rows:
                keep.setdefault(r.get("instrument", ""), None)
            first = set(list(keep)[: int(p["limit"])])
            rows = [r for r in rows if r.get("instrument", "") in first]
        url = BASE + FILES[kind] + ("" if year is None else f"#year={year}")
        body = canonical_json({"file": kind, "year": year, "rows": rows})
        return Fetched(self.source_id, url, self.client.now(), 200, body, "application/json")

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        """Party names become pseudonyms; descriptions are kept only when they are an amount,
        an OR book/page reference or a case number (a legal description can locate a home)."""
        from equity.adapters.record import pseudonym  # the recorder imports the registry

        data = json.loads(content)
        keep = re.compile(r"^(\$[\d,.]+( ET AL)?|OR \d+ PG \d+|[\d-]+[A-Z]{2}[\d-]*)$")
        for row in data["rows"]:
            for col in PII_FIELDS:
                if row.get(col):
                    row[col] = pseudonym(col, row[col])
            if row.get("description") and not keep.match(row["description"]):
                row["description"] = "LT 1 BLK 1 TEST SUBDIVISION"
        return canonical_json(data)

    def health(self) -> HealthReport:
        now = self.client.now()
        try:
            resp = self.client.get(BASE + "oriweekly.zip")
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            rows = parse_lines(zip_text(resp.content))
        except (RuntimeError, OSError, zipfile.BadZipFile) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        ok = bool(rows) and all(file_date(r.get("date", "")) for r in rows[:50])
        return HealthReport(self.source_id, ok, now,
                            f"{len(rows)} weekly rows" if ok else "unexpected layout",
                            FIELDS)  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = self.config
        data = json.loads(fetched.content)
        today = fetched.retrieved_at.astimezone(UTC).date()
        by_inst: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in data["rows"]:
            if r.get("instrument"):
                by_inst[r["instrument"]].append(r)
        for inst in sorted(by_inst):
            group = sorted(by_inst[inst], key=canonical_json)
            code = group[0].get("code", "")
            descs = {r.get("description", "") for r in group}
            if code in cfg.exclude_codes or any(
                p.search(d) for p in cfg.exclude_description_patterns for d in descs
            ):
                continue  # never loaded, parties included
            yield from self._document(fetched, today, inst, group)

    def _document(
        self, fetched: Fetched, today: date, inst: str, group: list[dict[str, str]]
    ) -> Iterator[NormalizedRow]:
        cfg = self.config
        first = group[0]
        ctx = RecordContext(fetched, COUNTY, inst, "or_document", group)
        yield ctx.source_record()

        def issue(code: str, /, **detail: Any) -> NormalizedRow:
            return ctx.fact("data_issue", issue_code=code, target_table="instrument",
                            detail={"instrument": inst, **detail})  # fmt: skip

        code = first.get("code", "")
        recorded_on = file_date(first.get("date", ""))
        if not code or recorded_on is None:
            yield issue("missing_doc_type_or_recorded_date", code=code, date=first.get("date"))
            return
        if recorded_on > today:
            yield issue("recorded_after_retrieval", recorded=str(recorded_on))
            return
        spec = cfg.codes.get(code)
        if spec is None:
            yield issue("unknown_doc_code", code=code)
            spec = OrCode("OTHER", "other", "other")
        descs = sorted({r["description"] for r in group if r.get("description")})
        principal = None
        if spec.doc_type in cfg.amount_doc_types:
            principal = next((a for a in (amount(d) for d in descs) if a is not None), None)
        uid = f"{self.source_id}:{inst}"
        yield ctx.fact(
            "instrument",
            instrument_uid=uid,
            instrument_number=inst,
            book_type="OR" if first.get("book") else None,
            book=first.get("book"),
            page=first.get("page"),
            doc_type_raw=code,
            doc_type=spec.doc_type,
            recorded_on=recorded_on,
            recorded_seq=int(inst) if inst.isdigit() else None,
            executed_on=None,
            consideration=None,
            principal_amount=principal,
            max_secured_amount=None,
            maturity_date=None,
            amount_source="index" if principal is not None else None,
            legal_desc_raw=" | ".join(descs) or None,
        )
        for col, role in (("from", spec.frm), ("to", spec.to)):
            names = sorted({r[col] for r in group if r.get(col)})
            for seq, name in enumerate(names, start=1):
                nc = classify(name)
                party_id = stable_id(self.source_id, inst, col, clean(name))
                yield ctx.fact(
                    "party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
                    org_form=nc.org_form, org_name_norm=nc.org_name_norm, address_id=None,
                )  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=party_id,
                               role=role, seq=seq)  # fmt: skip
