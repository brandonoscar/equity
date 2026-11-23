"""Hernando County (FL) Clerk: Official Records weekly index files.

Florida records certified copies of judgments, liens, lis pendens, satisfactions, deeds and
mortgages in one Official Records series. Hernando's clerk posts one CSV per week on its
subscriber file site, which no longer needs an account (config/recorders/fl.hernando.or.yaml):

    Grantor, Grantee, ClerkFileNumber, Book, PageNumber, DocumentTypeDescription,
    LegalDescription, DateRecorded ("11/06/26 10:44:57 AM")

(no header row; one row per grantor x grantee x legal-description line, so an instrument
spans many rows). Files go back to 2024-08-02. The index carries no party addresses and no
amounts.

Source: https://subscriber.hernandoclerk.com/ (robots.txt 404: no restrictions; checked
2026-11-23).
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date
from functools import cache
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

SITE = "https://subscriber.hernandoclerk.com/"
BASE = SITE + "data_files/official_records/"
CONFIG = "recorders/fl.hernando.or.yaml"
COUNTY = "12053"
FIELDS = ("Grantor", "Grantee", "ClerkFileNumber", "Book", "PageNumber",
          "DocumentTypeDescription", "LegalDescription", "DateRecorded")  # fmt: skip
PII_FIELDS: tuple[str, ...] = ("Grantor", "Grantee")
_FILE = re.compile(r"official_records/(\d{2}-\d{2}-\d{4}\.csv)")
_RECORDED = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b")


@dataclass(frozen=True)
class OrCode:
    doc_type: str
    frm: str
    to: str


@dataclass(frozen=True)
class HernandoConfig:
    descriptions: Mapping[str, OrCode]
    consideration_doc_types: frozenset[str]
    family_suffix: re.Pattern[str]
    variant_suffix: re.Pattern[str]
    exclude_patterns: tuple[re.Pattern[str], ...]
    empty_legal: str
    terms: Mapping[str, Any]


@cache
def load_config() -> HernandoConfig:
    import yaml

    d = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    return HernandoConfig(
        descriptions={
            str(k): OrCode(str(v["doc_type"]), str(v["frm"]), str(v["to"]))
            for k, v in d["descriptions"].items()
        },
        consideration_doc_types=frozenset(d["consideration_doc_types"]),
        family_suffix=re.compile(d["family_suffix"]),
        variant_suffix=re.compile(d["variant_suffix"]),
        exclude_patterns=tuple(re.compile(p) for p in d["exclude_patterns"]),
        empty_legal=" ".join(str(d["empty_legal"]).split()),
        terms=dict(d["terms"]),
    )


def lookup(cfg: HernandoConfig, description: str) -> OrCode | str | None:
    """A description's mapping; 'excluded' when it is never loaded; None when unknown."""
    desc = " ".join(description.upper().split())
    if desc in cfg.descriptions:
        return cfg.descriptions[desc]
    if any(p.search(desc) for p in cfg.exclude_patterns):
        return "excluded"
    base = cfg.family_suffix.sub("", desc)
    if base != desc and cfg.variant_suffix.sub("", base).strip() in cfg.descriptions:
        return "excluded"
    return cfg.descriptions.get(cfg.variant_suffix.sub("", desc).strip())


def recorded_date(value: str) -> date | None:
    """'11/06/26 10:44:57 AM' -> 2026-11-06 (a calendar date: no time zone involved)."""
    m = _RECORDED.match(value.strip())
    if m is None:
        return None
    month, day, year = (int(g) for g in m.groups())
    if year < 100:
        year += 2000 if year < 70 else 1900
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_rows(text: str) -> list[dict[str, str]]:
    """The headerless CSV -> dicts; short rows are skipped, exact repeats dropped."""
    out: dict[bytes, dict[str, str]] = {}
    for rec in csv.reader(io.StringIO(text, newline="")):
        if len(rec) < len(FIELDS):
            continue
        row = {f: " ".join(rec[i].split()) for i, f in enumerate(FIELDS)}
        out.setdefault(canonical_json(row), row)
    return list(out.values())


def weekly_files(listing: str) -> list[str]:
    """Official Records file names on the subscriber page, oldest first."""
    names = set(_FILE.findall(listing))
    return sorted(names, key=lambda n: (n[6:10], n[0:2], n[3:5]))


class HernandoOfficialRecords(Adapter):
    source_id: ClassVar[str] = "fl.hernando.or"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = PII_FIELDS
    # A corrected or re-indexed record can come back in a later week: one store.
    single_store: ClassVar[bool] = True

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.config = load_config()
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=300.0)

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

    def _text(self, url: str) -> str:
        resp = self.client.get(url)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        return resp.content.decode("utf-8", errors="replace")

    def partitions(self) -> Iterator[dict[str, str]]:
        for name in weekly_files(self._text(SITE)):
            yield {"file": name}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: file (MM-DD-YYYY.csv); limit (fixtures): first N instruments' rows."""
        name = request.params["file"]
        if not re.fullmatch(r"\d{2}-\d{2}-\d{4}\.csv", name):
            raise ValueError(f"not a weekly index file name: {name!r}")
        rows = parse_rows(self._text(BASE + name))
        if "limit" in request.params:
            keep: list[str] = []
            for r in rows:
                if r["ClerkFileNumber"] not in keep:
                    keep.append(r["ClerkFileNumber"])
            first = set(keep[: int(request.params["limit"])])
            rows = [r for r in rows if r["ClerkFileNumber"] in first]
        return Fetched(
            source_id=self.source_id,
            request=BASE + name,
            retrieved_at=self.client.now(),
            http_status=200,
            content=canonical_json({"file": name, "rows": rows}),
            content_type="application/json",
        )

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        """Grantor/grantee become pseudonyms; an indexed legal description becomes a test
        subdivision (the placeholder stays as it is)."""
        from equity.adapters.record import pseudonym  # the recorder imports the registry

        data = json.loads(content)
        empty = load_config().empty_legal
        for row in data["rows"]:
            for col in PII_FIELDS:
                if row.get(col):
                    row[col] = pseudonym(col, row[col])
            if row.get("LegalDescription") and row["LegalDescription"] != empty:
                row["LegalDescription"] = "L1 Blk1 Un1 SubTEST SUBDIVISION S T R"
        return canonical_json(data)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        by_inst: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in data["rows"]:
            if r.get("ClerkFileNumber"):
                by_inst[r["ClerkFileNumber"]].append(r)
        today = fetched.retrieved_at.astimezone(UTC).date()
        for inst in sorted(by_inst):
            group = sorted(by_inst[inst], key=canonical_json)
            spec = lookup(self.config, group[0]["DocumentTypeDescription"])
            if spec == "excluded":
                continue  # never loaded, parties included
            yield from self._document(fetched, today, inst, group,
                                      spec if isinstance(spec, OrCode) else None)  # fmt: skip

    def _document(
        self,
        fetched: Fetched,
        today: date,
        inst: str,
        group: list[dict[str, str]],
        spec: OrCode | None,
    ) -> Iterator[NormalizedRow]:
        cfg = self.config
        first = group[0]
        ctx = RecordContext(fetched, COUNTY, inst, "or_document", group)
        yield ctx.source_record()

        def issue(code: str, /, **detail: Any) -> NormalizedRow:
            return ctx.fact("data_issue", issue_code=code, target_table="instrument",
                            detail={"instrument": inst, **detail})  # fmt: skip

        desc = first["DocumentTypeDescription"]
        recorded_on = recorded_date(first["DateRecorded"])
        if not desc or recorded_on is None:
            yield issue("missing_doc_type_or_recorded_date", description=desc,
                        date=first["DateRecorded"])  # fmt: skip
            return
        if recorded_on > today:
            yield issue("recorded_after_retrieval", recorded=str(recorded_on))
            return
        if spec is None:
            yield issue("unknown_doc_code", description=desc)
            spec = OrCode("OTHER", "other", "other")
        legal = sorted({r["LegalDescription"] for r in group} - {"", cfg.empty_legal})
        uid = f"{self.source_id}:{inst}"
        yield ctx.fact(
            "instrument",
            instrument_uid=uid,
            instrument_number=inst,
            book_type="OR" if first["Book"] else None,
            book=first["Book"] or None,
            page=first["PageNumber"] or None,
            doc_type_raw=desc,
            doc_type=spec.doc_type,
            recorded_on=recorded_on,
            # Clerk file numbers run in recording order (year + sequence).
            recorded_seq=int(inst) if inst.isdigit() else None,
            executed_on=None,
            consideration=None,
            principal_amount=None,
            max_secured_amount=None,
            maturity_date=None,
            amount_source=None,
            legal_desc_raw=" | ".join(legal) or None,
        )
        for col, role in (("Grantor", spec.frm), ("Grantee", spec.to)):
            names = sorted({r[col] for r in group if r[col]})
            for seq, name in enumerate(names, start=1):
                nc = classify(name)
                party_id = stable_id(self.source_id, inst, col, clean(name))
                yield ctx.fact(
                    "party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
                    org_form=nc.org_form, org_name_norm=nc.org_name_norm, address_id=None,
                )  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=party_id,
                               role=role, seq=seq)  # fmt: skip

    def health(self) -> HealthReport:
        now = self.client.now()
        try:
            files = weekly_files(self._text(SITE))
            if not files:
                return HealthReport(self.source_id, False, now, "no weekly files listed")
            rows = parse_rows(self._text(BASE + files[-1]))
        except (RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        sample = rows[:50]
        dated = sum(recorded_date(r["DateRecorded"]) is not None for r in sample)
        ok = bool(sample) and dated * 2 > len(sample)
        return HealthReport(self.source_id, ok, now,
                            f"{files[-1]}: {len(rows)} rows" if ok else "unexpected layout",
                            FIELDS)  # fmt: skip
