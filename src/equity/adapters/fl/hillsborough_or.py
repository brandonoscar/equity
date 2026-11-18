"""Hillsborough County (FL) Clerk: Official Records daily index files.

Florida records judgments (certified copies), liens, lis pendens, satisfactions, deeds and
mortgages in one Official Records series. The Clerk posts one pipe-delimited file pair per
business day, kept online for at least two months:

    D<YYYYMMDD><NN>id.29   documents: action|county|instrument|code|description|legal|
                           book type|book|page|filler|pages|date recorded|time|consideration|
    P<YYYYMMDD><NN>id.29   parties:   action|county|instrument|sequence|FRM or TO|name|

(layout: readme.txt in the same folder, dated 2007-01-01). Files are named by recording date,
or by correction date for corrected records; a later file's row for the same instrument
supersedes the earlier one in the store.

Source: https://publicrec.hillsclerk.com/OfficialRecords/DailyIndexes/ (robots.txt 404, so
no restrictions; hillsclerk.com robots allows all; checked 2026-11-16). No terms found.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from functools import cache
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

BASE = "https://publicrec.hillsclerk.com/OfficialRecords/DailyIndexes/"
CONFIG = "recorders/fl.hillsborough.or.yaml"
COUNTY = "12057"
D_FIELDS = ("action", "county", "instrument", "code", "description", "legal", "book_type",
            "book", "page", "filler", "pages", "date", "time", "consideration")  # fmt: skip
P_FIELDS = ("action", "county", "instrument", "seq", "direction", "name")
_FILE = re.compile(r"\bD(\d{8})(\d{2})id\.29\b")
# A Florida uniform case number as typed in the legal column, e.g. 26-CA-006969 or 2025-CC-1.
CASE_NO = re.compile(r"^\d{2,4}-[A-Z]{2,3}-\d{1,7}(?:-[A-Z0-9]+)*$")


@dataclass(frozen=True)
class OrCode:
    doc_type: str
    frm: str
    to: str


@dataclass(frozen=True)
class OrConfig:
    codes: Mapping[str, OrCode]
    consideration_doc_types: frozenset[str]
    exclude_codes: frozenset[str]
    exclude_descriptions: frozenset[str]


@cache
def load_config() -> OrConfig:
    import yaml

    data = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    return OrConfig(
        codes={
            str(k): OrCode(str(v["doc_type"]), str(v["frm"]), str(v["to"]))
            for k, v in data["codes"].items()
        },
        consideration_doc_types=frozenset(data["consideration_doc_types"]),
        exclude_codes=frozenset(data["exclude_codes"]),
        exclude_descriptions=frozenset(data["exclude_descriptions"]),
    )


def parse_lines(text: str, fields: tuple[str, ...]) -> list[dict[str, str]]:
    """Pipe-delimited rows -> dicts. The trailing 'EOF' marker and short lines are skipped."""
    out = []
    for line in text.splitlines():
        cells = line.rstrip("\r\n").split("|")
        if len(cells) < len(fields):
            continue
        out.append({f: cells[i].strip() for i, f in enumerate(fields)})
    return out


def daily_files(listing: str) -> list[tuple[str, str]]:
    """(YYYYMMDD, NN) of every D file in a directory listing, oldest first."""
    return sorted(set(_FILE.findall(listing)))


def _date(value: str) -> date | None:
    """MM/DD/YYYY -> date (a calendar date: no time zone involved)."""
    parts = value.split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    try:
        return date(int(parts[2]), int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def _amount(value: str) -> Decimal | None:
    if not value:
        return None
    try:
        amt = Decimal(value)
    except InvalidOperation:
        return None
    return None if amt <= 0 else amt.quantize(Decimal("0.01"))


class HillsboroughOfficialRecords(Adapter):
    source_id: ClassVar[str] = "fl.hillsborough.or"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    # A corrected record comes back in a later day's file: load all days into one store.
    single_store: ClassVar[bool] = True

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=120.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "recorder",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": BASE,
            "terms_url": "https://www.hillsclerk.com/records-and-reports/public-data-files",
            "terms_summary": "Public data files, no login; no terms of use found on the folder.",
            "terms_checked_on": date(2026, 11, 16),
            "robots_checked_on": date(2026, 11, 16),
            "cost_model": "free",
        }

    def _text(self, url: str) -> str:
        resp = self.client.get(url)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        return resp.content.decode("latin-1")

    def partitions(self) -> Iterator[dict[str, str]]:
        for day, n in daily_files(self._text(BASE)):
            yield {"day": day, "n": n}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: day (YYYYMMDD), n (export counter, normally 01); limit (fixtures): keep the
        first N documents and their parties."""
        day, n = request.params["day"], request.params.get("n", "01")
        if not (day.isdigit() and len(day) == 8 and n.isdigit() and len(n) == 2):
            raise ValueError(f"bad day/n: {day!r} {n!r}")
        d_name, p_name = f"D{day}{n}id.29", f"P{day}{n}id.29"
        d_text, p_text = self._text(BASE + d_name), self._text(BASE + p_name)
        limit = request.params.get("limit")
        if limit is not None:
            d_lines = d_text.splitlines()[: int(limit)]
            keep = {line.split("|")[2] for line in d_lines if line.count("|") > 2}
            p_lines = [ln for ln in p_text.splitlines() if ln.count("|") > 2
                       and ln.split("|")[2] in keep]  # fmt: skip
            d_text, p_text = "\n".join(d_lines) + "\n", "\n".join(p_lines) + "\n"
        body = {"d_file": d_name, "p_file": p_name, "d": d_text, "p": p_text}
        return Fetched(
            source_id=self.source_id,
            request=BASE + d_name,
            retrieved_at=datetime.now(UTC),
            http_status=200,
            content=canonical_json(body),
            content_type="application/json",
        )

    @staticmethod
    def scrub_fixture(content: bytes) -> bytes:
        """Party names become pseudonyms; legal descriptions are kept only when they are a
        case number (a UCC filing's legal column can hold the debtor's address)."""
        from equity.adapters.record import pseudonym  # the recorder imports the registry

        data = json.loads(content)
        p_out = []
        for line in data["p"].splitlines():
            cells = line.split("|")
            if len(cells) > 5 and cells[5].strip():
                cells[5] = pseudonym("name", cells[5].strip())
            p_out.append("|".join(cells))
        d_out = []
        for line in data["d"].splitlines():
            cells = line.split("|")
            if len(cells) > 5 and cells[5].strip() and not CASE_NO.match(cells[5].strip()):
                cells[5] = "L 1 B 1 TEST SUBDIVISION"
            d_out.append("|".join(cells))
        data["p"], data["d"] = "\n".join(p_out) + "\n", "\n".join(d_out) + "\n"
        return canonical_json(data)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = load_config()
        data = json.loads(fetched.content)
        parties: dict[str, list[dict[str, str]]] = defaultdict(list)
        for p in parse_lines(data["p"], P_FIELDS):
            parties[p["instrument"]].append(p)
        docs: dict[str, dict[str, str]] = {}
        for d in parse_lines(data["d"], D_FIELDS):
            if d["instrument"]:
                docs[d["instrument"]] = d  # a repeated row in one file: the last one stands
        today = fetched.retrieved_at.astimezone(UTC).date()
        for inst in sorted(docs):
            d = docs[inst]
            if d["code"] in cfg.exclude_codes or d["description"] in cfg.exclude_descriptions:
                continue  # never loaded, parties included
            yield from self._document(cfg, fetched, today, d, parties.get(inst, []))

    def _document(
        self,
        cfg: OrConfig,
        fetched: Fetched,
        today: date,
        d: Mapping[str, str],
        party_rows: list[dict[str, str]],
    ) -> Iterator[NormalizedRow]:
        inst = d["instrument"]
        raw = {"document": dict(d), "parties": sorted(party_rows, key=canonical_json)}
        ctx = RecordContext(fetched, COUNTY, inst, "or_document", raw)
        yield ctx.source_record()

        def issue(code: str, table: str, /, **detail: Any) -> NormalizedRow:
            return ctx.fact("data_issue", issue_code=code, target_table=table,
                            detail={"instrument": inst, **detail})  # fmt: skip

        if not d["action"].startswith("DDA"):
            # Not an add (a delete or another action): recorded, never applied as a fact.
            yield issue("non_add_action", "instrument", action=d["action"])
            return
        recorded_on = _date(d["date"])
        if not d["code"] or recorded_on is None:
            yield issue("missing_doc_type_or_recorded_date", "instrument",
                        code=d["code"], date=d["date"])  # fmt: skip
            return
        if recorded_on > today:
            yield issue("recorded_after_retrieval", "instrument", recorded=str(recorded_on))
            return
        spec = cfg.codes.get(d["code"])
        if spec is None:
            yield issue("unknown_doc_code", "instrument", code=d["code"],
                        description=d["description"])  # fmt: skip
            spec = OrCode("OTHER", "other", "other")
        is_price = spec.doc_type in cfg.consideration_doc_types
        price = _amount(d["consideration"]) if is_price else None
        uid = f"{self.source_id}:{inst}"
        yield ctx.fact(
            "instrument",
            instrument_uid=uid,
            instrument_number=inst,
            book_type=d["book_type"] or None,
            book=d["book"] or None,
            page=d["page"] or None,
            doc_type_raw=d["code"],
            doc_type=spec.doc_type,
            recorded_on=recorded_on,
            # Instrument numbers run in filing order (year + sequence), so they order a day.
            recorded_seq=int(inst) if inst.isdigit() else None,
            executed_on=None,
            consideration=price,
            principal_amount=None,
            max_secured_amount=None,
            maturity_date=None,
            amount_source="index" if price is not None else None,
            legal_desc_raw=d["legal"] or None,
        )
        seen: dict[str, set[str]] = defaultdict(set)
        ordered = sorted(party_rows, key=lambda p: (p["direction"], int(p["seq"] or 0), p["name"]))
        for p in ordered:
            name = " ".join(p["name"].split())
            role = {"FRM": spec.frm, "TO": spec.to}.get(p["direction"])
            if not name or role is None or name in seen[role]:
                continue
            seen[role].add(name)
            nc = classify(name)
            party_id = stable_id(self.source_id, inst, p["direction"], clean(name))
            yield ctx.fact(
                "party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
                org_form=nc.org_form, org_name_norm=nc.org_name_norm, address_id=None,
            )  # fmt: skip
            yield ctx.fact("instrument_party", instrument_uid=uid, party_id=party_id,
                           role=role, seq=len(seen[role]))  # fmt: skip

    def health(self) -> HealthReport:
        try:
            files = daily_files(self._text(BASE))
        except (RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        if not files:
            return HealthReport(self.source_id, False, datetime.now(UTC), "no daily files")
        day, n = files[-1]
        rows = parse_lines(self._text(f"{BASE}D{day}{n}id.29"), D_FIELDS)
        ok = bool(rows) and all(r["county"] == "29" for r in rows)
        return HealthReport(self.source_id, ok, datetime.now(UTC),
                            "ok" if ok else "unexpected D file layout", D_FIELDS)  # fmt: skip
