"""Harris County (TX) District Clerk: civil debt judgments from the CaseSummaryMods datasets.

The District Clerk's Public Datasets page (config/courts_state/tx.harris.district.
civil_judgments.yaml) offers tab-delimited case summary extracts: one file per five years of
filing (CaseSummaryMods_Historical-2020-2024.txt) and one of cases changed since the last of
those (CaseSummaryMods_HistoricalCurrent-2025-<yymmdd>.txt). Each row is a case and one of
its judgments: filing date, court, status, case type, the first plaintiff and defendant
(names only) and the judgment's date and text. There are no amounts and no addresses.

Kept: civil debt cases (configured case types). Each becomes one court_case with its two
parties; each configured judgment text on the case's own judgment row (no pj_num) becomes a
judgment with no principal. Those texts are judgments for the plaintiff, so a case with one
names the plaintiff 'creditor' and the defendant 'debtor'; other cases keep 'plaintiff' and
'defendant'.

Files are fetched through the page's Download button (an ASP.NET form post), and only kept
rows are stored. A case can be in a historical file and again in the current one, so all
files load into one store in order (single_store), the newer row superseding the older.
"""

from __future__ import annotations

import csv
import html
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

CONFIG = "courts_state/tx.harris.district.civil_judgments.yaml"
COUNTY = "48201"
HISTORICAL = re.compile(r"CaseSummaryMods_Historical-(\d{4})-(\d{4})\.txt")
CURRENT = re.compile(r"CaseSummaryMods_HistoricalCurrent-(\d{4})-(\d{6})\.txt")
COLUMNS = ("region", "casenbr", "file_crt", "curr_crt", "file_dt", "cst", "cs_typ", "toac",
           "plaintiff", "defendant", "pj_num", "judgment_dt", "judgment", "lastmoddt")  # fmt: skip
_DOC = re.compile(r"DownloadDoc\('([^']+)'\)")
_HIDDEN = re.compile(r"<input[^>]*type=\"hidden\"[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r'(name|value)="([^"]*)"')
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


@dataclass(frozen=True)
class DistrictConfig:
    source_id: str
    page_url: str
    download_field: str
    download_button: str
    folder: str
    first_year: int
    case_types: Mapping[str, str]
    judgment_types: Mapping[str, str]
    terms: Mapping[str, Any]


def _text(value: str) -> str:
    return " ".join(value.upper().split())


@cache
def load_config() -> DistrictConfig:
    import yaml

    d = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    return DistrictConfig(
        source_id=d["source_id"],
        page_url=d["page_url"],
        download_field=d["download_field"],
        download_button=d["download_button"],
        folder=d["folder"],
        first_year=int(d["first_year"]),
        case_types={str(k): str(v) for k, v in d["case_types"].items()},
        judgment_types={_text(k): str(v) for k, v in d["judgment_types"].items()},
        terms=dict(d["terms"]),
    )


def iso_date(value: str | None) -> date | None:
    """'2025-10-22 00:00:00' or '2025-10-22' -> date; blank or malformed -> None."""
    m = _ISO.match((value or "").strip())
    if m is None:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def case_uid(raw: str) -> str:
    return f"tx.harris.district:{raw.strip().upper()}"


def court_id(raw: str) -> str:
    """'061' -> 'tx.harris.district.61' (the district court number)."""
    text = raw.strip()
    return f"tx.harris.district.{int(text) if text.isdigit() else (text.lower() or 'unknown')}"


def listed_files(page: str, folder: str) -> list[str]:
    """File names the datasets page offers in one folder ('Civil\\\\x.txt' -> 'x.txt')."""
    names = set()
    for ref in _DOC.findall(page):
        head, _, name = html.unescape(ref).replace("\\\\", "\\").partition("\\")
        if head == folder and name:
            names.add(name)
    return sorted(names)


def hidden_fields(page: str) -> dict[str, str]:
    """The ASP.NET state fields (__VIEWSTATE...) a postback must send back."""
    out: dict[str, str] = {}
    for tag in _HIDDEN.findall(page):
        attrs = dict(_ATTR.findall(tag))
        if attrs.get("name", "").startswith("__"):
            out[attrs["name"]] = html.unescape(attrs.get("value", ""))
    return out


def read_rows(text: str) -> list[dict[str, str]]:
    """The tab-delimited extract as dicts (no quoting: quotes are part of names)."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")), delimiter="\t", quoting=csv.QUOTE_NONE)
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        return []
    if "casenbr" not in header or "judgment" not in header:
        raise ValueError(f"not a CaseSummaryMods extract (header {header[:3]!r})")
    return [dict(zip(header, (v.strip() for v in rec), strict=False)) for rec in reader if rec]


def kept(row: Mapping[str, str], cfg: DistrictConfig) -> bool:
    return (row.get("region", "").upper() == "CIV" and bool(row.get("casenbr"))
            and row.get("cs_typ", "") in cfg.case_types)  # fmt: skip


class HarrisDistrictCivilJudgments(Adapter):
    source_id: ClassVar[str] = "tx.harris.district.civil_judgments"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("plaintiff", "defendant")
    # A case filed in 2023 and changed in 2025 is in both the 2020-2024 and the current file.
    single_store: ClassVar[bool] = True

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.config = load_config()
        self.client = client or PoliteClient(min_interval_s=5.0, timeout_s=900.0)

    def source_row(self) -> Mapping[str, Any]:
        t = self.config.terms
        return {
            "source_id": self.source_id,
            "kind": "court",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": self.config.page_url,
            "terms_url": t["url"],
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t["robots_checked_on"],
            "cost_model": t["cost_model"],
        }

    # -- the page -----------------------------------------------------------------------
    def _page(self) -> str:
        resp = self.client.get(self.config.page_url)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {self.config.page_url}")
        return resp.content.decode("utf-8", errors="replace")

    def files(self, page: str | None = None) -> list[str]:
        """Historical files from first_year on (oldest first), then the current file."""
        names = listed_files(page if page is not None else self._page(), self.config.folder)
        hist = sorted((m.group(1), n) for n in names if (m := HISTORICAL.fullmatch(n))
                      and int(m.group(2)) >= self.config.first_year)  # fmt: skip
        current = sorted(n for n in names if CURRENT.fullmatch(n))
        return [n for _, n in hist] + current[-1:]

    def partitions(self) -> Iterator[dict[str, str]]:
        for name in self.files():
            yield {"file": name}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: file (a CaseSummaryMods name from the page); limit (fixtures): first N kept."""
        name = request.params["file"]
        if not (HISTORICAL.fullmatch(name) or CURRENT.fullmatch(name)):
            raise ValueError(f"not a CaseSummaryMods file name: {name!r}")
        cfg = self.config
        page = self._page()
        if name not in listed_files(page, cfg.folder):
            raise ValueError(f"{name} is not offered on the datasets page")
        form = {**hidden_fields(page), cfg.download_field: f"{cfg.folder}\\{name}",
                cfg.download_button: ""}  # fmt: skip
        resp = self.client.post_form(cfg.page_url, form)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} posting for {name}")
        rows = [{k: r[k] for k in COLUMNS if r.get(k)}
                for r in read_rows(resp.content.decode("latin-1")) if kept(r, cfg)]  # fmt: skip
        if "limit" in request.params:
            rows = rows[: int(request.params["limit"])]
        body = canonical_json({"file": name, "rows": rows})
        url = f"{cfg.page_url}#{cfg.folder}/{name}"
        return Fetched(self.source_id, url, resp.retrieved_at, 200, body, "application/json")

    def health(self) -> HealthReport:
        """Live: the page still offers a current CaseSummaryMods file."""
        try:
            names = self.files()
        except (RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, self.client.now(), repr(exc))
        ok = any(CURRENT.fullmatch(n) for n in names)
        return HealthReport(self.source_id, ok, self.client.now(),
                            "ok" if ok else "no current CaseSummaryMods file",
                            tuple(names[-1:]))  # fmt: skip

    # -- normalizing --------------------------------------------------------------------
    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = self.config
        rows: list[dict[str, str]] = json.loads(fetched.content)["rows"]
        today = fetched.retrieved_at.astimezone(UTC).date()
        by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in rows:
            if kept(r, cfg):
                by_case[r["casenbr"].strip().upper()].append(r)
        for norm in sorted(by_case):
            group = sorted(by_case[norm], key=canonical_json)
            first = group[0]
            uid = case_uid(norm)
            ctx = RecordContext(fetched, COUNTY, norm, "district_civil_case", group)
            yield ctx.source_record()
            filed = iso_date(first.get("file_dt"))
            yield ctx.fact(
                "court_case", case_uid=uid, court_id=court_id(first.get("curr_crt", "")),
                case_number_raw=first["casenbr"], case_number_norm=norm,
                case_type=cfg.case_types[first["cs_typ"]], nature_of_suit=first.get("toac"),
                filed_on=filed if filed is not None and filed <= today else None,
                closed_on=None, status=first.get("cst") or None,
            )  # fmt: skip
            judgments: dict[tuple[date, str], str] = {}
            for r in group:
                jtype = cfg.judgment_types.get(_text(r.get("judgment", "")))
                entered = iso_date(r.get("judgment_dt"))
                if r.get("pj_num") or jtype is None or entered is None or entered > today:
                    continue
                judgments[(entered, _text(r["judgment"]))] = jtype
            won = bool(judgments)
            for role, col in (("creditor" if won else "plaintiff", "plaintiff"),
                              ("debtor" if won else "defendant", "defendant")):  # fmt: skip
                name = " ".join(first.get(col, "").split())
                if name:
                    yield from self._party(ctx, uid, role, name)
            for (entered, text), jtype in sorted(judgments.items()):
                tag = stable_id("tx.harris.district", text)[:8]
                yield ctx.fact(
                    "judgment", judgment_uid=f"{uid}:{entered.isoformat()}:{tag}",
                    case_uid=uid, entered_on=entered, principal=None, interest=None,
                    costs=None, rate=None, judgment_type=jtype, lien_instrument_uid=None,
                )  # fmt: skip

    def _party(self, ctx: RecordContext, uid: str, role: str, name: str) -> Iterator[NormalizedRow]:
        nc = classify(name)
        party_id = stable_id(self.source_id, uid, role, clean(name))
        yield ctx.fact(
            "party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
            org_form=nc.org_form, org_name_norm=nc.org_name_norm, address_id=None,
        )  # fmt: skip
        yield ctx.fact("case_party", case_uid=uid, party_id=party_id, role=role)
