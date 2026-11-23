"""Federal civil money judgments from the FJC Integrated Database (IDB), straight from the FJC.

The same IDB the CourtListener source (fjc_idb.py) republishes, but the FJC's own "Civil Cases
Cumulative File" (cv88on.zip, config/courts_federal/us.fjc.idb.direct.civil_judgments.yaml):
every civil case terminated since SY 1988, updated quarterly, so it has the judgments
terminated after CourtListener's copy stops (filings through 2022-03-31). One tab-delimited
record per case termination, in the codebook's short column names.

Kept, and modeled, exactly as in fjc_idb.py (the filter thresholds are read from that source's
config): judgments for the plaintiff (JUDGMENT 1) that are monetary awards (NOJ 1 or 2) with
an amount (AMTREC > 0, in thousands; 9999 is a floor and gives a NULL principal) and a
termination date. Each becomes one court_case, the plaintiff as creditor and the defendant as
debtor (ET AL markers stripped for the party identity) and one money judgment entered on the
termination date.

The file has no record id. A record is known by district + office + docket + filing date
(dedupe_key, the same key CourtListener's case_uid starts with), and case_uid adds the
termination date: <key>#<termination date>. Records sharing both (a docket reported twice,
same day) are numbered ~1, ~2 in a fixed order; an exact repeat of a record is dropped.

robots.txt disallows the IDB file paths on fjc.gov, so this is a manual source: the zip is
downloaded by hand to manual_path and read from there. Partitions are years of TERMDATE. One
streaming pass writes the kept rows, split by year, to a local extract, and the sorted list of
kept keys (which the CourtListener adapter uses to drop its copies of these records) to a
keys file beside it; the extract is deleted after the last year.
"""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import IO, Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.fjc_idb import IDBConfig, county_fips, kept, principal, strip_et_al
from equity.adapters.federal.fjc_idb import load_config as load_idb_config
from equity.adapters.rows import RecordContext, canonical_json
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

CONFIG = "courts_federal/us.fjc.idb.direct.civil_judgments.yaml"


@dataclass(frozen=True)
class DirectConfig:
    source_id: str
    download_page: str
    file_url: str
    manual_path: Path
    member: str
    first_year: int
    districts: Mapping[str, str]
    terms: Mapping[str, Any]


@cache
def load_config() -> DirectConfig:
    import yaml

    d = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    return DirectConfig(
        source_id=d["source_id"],
        download_page=d["download_page"],
        file_url=d["file_url"],
        manual_path=Path(d["manual_path"]),
        member=d["member"],
        first_year=int(d["first_year"]),
        districts={str(k): str(v) for k, v in d["districts"].items()},
        terms=dict(d["terms"]),
    )


def us_date(value: str | None) -> date | None:
    """'03/31/2025' -> date; blank, '-8' or an impossible date -> None."""
    parts = (value or "").strip().split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts) or len(parts[2]) != 4:
        return None
    try:
        return date(int(parts[2]), int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def _filed_text(row: Mapping[str, str]) -> str:
    raw = (row.get("FILEDATE") or "").strip()
    filed = us_date(raw)
    return filed.isoformat() if filed is not None else (raw or "-")


def court(row: Mapping[str, str], cfg: DirectConfig) -> str | None:
    """DISTRICT code -> PACER court id ('13' -> 'paed'); None for a code not in the table."""
    return cfg.districts.get((row.get("DISTRICT") or "").strip())


def dedupe_key(row: Mapping[str, str], cfg: DirectConfig) -> str | None:
    """us.<district>:<office>:<docket>:<filed>, the prefix of the CourtListener case_uid."""
    district = court(row, cfg)
    docket = (row.get("DOCKET") or "").strip()
    if district is None or not docket:
        return None
    office = (row.get("OFFICE") or "").strip() or "-"
    return f"us.{district}:{office}:{docket}:{_filed_text(row)}"


def kept_direct(row: Mapping[str, str]) -> tuple[date, int] | None:
    """The CourtListener filter (fjc_idb.kept) applied to an FJC record."""
    closed = us_date(row.get("TERMDATE"))
    as_cl = {
        "judgment": row.get("JUDGMENT") or "",
        "nature_of_judgement": row.get("NOJ") or "",
        "amount_received": row.get("AMTREC") or "",
        "date_terminated": closed.isoformat() if closed is not None else "",
    }
    return kept(as_cl, load_idb_config())


def read_rows(fh: IO[str]) -> Iterator[dict[str, str] | None]:
    """Records of the tab-delimited file as dicts; None for a line with the wrong field count."""
    header = fh.readline().rstrip("\r\n").split("\t")
    for line in fh:
        cells = line.rstrip("\r\n").split("\t")
        yield dict(zip(header, cells, strict=True)) if len(cells) == len(header) else None


def file_stem(path: Path, member: str) -> str:
    """cv88on-<member date>-<member size>: names one release of the file."""
    with zipfile.ZipFile(path) as zf:
        info = zf.getinfo(member)
    y, m, d = info.date_time[:3]
    return f"{Path(member).stem}-{y:04d}{m:02d}{d:02d}-{info.file_size}"


class FJCDirectCivilJudgments(Adapter):
    source_id: ClassVar[str] = "us.fjc.idb.direct.civil_judgments"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "manual"
    pii_fields: ClassVar[tuple[str, ...]] = ("PLT", "DEF")
    cache_dir: ClassVar[Path] = Path("data") / "work" / "us_fjc_idb_direct"

    def __init__(self, manual_path: Path | None = None) -> None:
        self.config = load_config()
        self.manual_path = manual_path or self.config.manual_path

    def source_row(self) -> Mapping[str, Any]:
        t = self.config.terms
        return {
            "source_id": self.source_id,
            "kind": "court",
            "jurisdiction": "us",
            "access_method": self.access_method,
            "base_url": self.config.file_url,
            "terms_url": t["url"],
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t["robots_checked_on"],
            "cost_model": t["cost_model"],
        }

    # -- the manual file ------------------------------------------------------------------
    def _zip(self) -> Path:
        if not self.manual_path.exists():
            raise FileNotFoundError(
                f"{self.manual_path}: download the Civil Cases Cumulative File (text) from "
                f"{self.config.download_page} by hand and save it here (robots.txt disallows "
                "scripted downloads)"
            )
        return self.manual_path

    def stem(self) -> str:
        return file_stem(self._zip(), self.config.member)

    def retrieved_at(self) -> datetime:
        """When the manual file was saved (its mtime): the file's retrieval time."""
        return datetime.fromtimestamp(int(self._zip().stat().st_mtime), UTC)

    def partitions(self) -> Iterator[dict[str, str]]:
        stem = self.stem()
        last = int(stem.split("-")[1][:4])
        for year in range(self.config.first_year, last + 1):
            yield {"file": stem, "year": str(year)}

    def keys_path(self, stem: str) -> Path:
        return self.cache_dir / f"{stem}.keys"

    def extract(self) -> Path:
        """One pass over the file: kept rows to <year>.jsonl, kept keys to <stem>.keys."""
        stem = self.stem()
        out = self.cache_dir / stem
        if (out / "_manifest.json").exists() and self.keys_path(stem).exists():
            return out
        tmp = out.with_name(out.name + ".part")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        files: dict[int, IO[str]] = {}
        keys: set[str] = set()
        counts = {"rows": 0, "bad_rows": 0, "kept": 0, "unknown_district": 0}
        try:
            with zipfile.ZipFile(self._zip()) as zf, zf.open(self.config.member) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
                for row in read_rows(text):
                    counts["rows"] += 1
                    if row is None:
                        counts["bad_rows"] += 1
                        continue
                    k = kept_direct(row)
                    if k is None:
                        continue
                    key = dedupe_key(row, self.config)
                    if key is None:
                        counts["unknown_district"] += 1
                        continue
                    keys.add(key)
                    year = k[0].year
                    if year not in files:
                        files[year] = (tmp / f"{year}.jsonl").open("w", encoding="utf-8")
                    files[year].write(canonical_json(row).decode("utf-8") + "\n")
                    counts["kept"] += 1
        finally:
            for f in files.values():
                f.close()
        manifest = {"file": stem, "url": self.config.file_url,
                    "retrieved_at": self.retrieved_at().isoformat(), **counts}  # fmt: skip
        (tmp / "_manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        keys_tmp = self.keys_path(stem).with_suffix(".keys.part")
        keys_tmp.write_text("".join(k + "\n" for k in sorted(keys)), encoding="utf-8")
        shutil.rmtree(out, ignore_errors=True)
        tmp.replace(out)
        keys_tmp.replace(self.keys_path(stem))
        return out

    def kept_keys(self) -> tuple[str, frozenset[str]]:
        """(file stem, dedupe keys of every kept record): what CourtListener rows yield to."""
        stem = self.stem()
        path = self.keys_path(stem)
        if not path.exists():
            self.extract()
        return stem, frozenset(path.read_text(encoding="utf-8").split())

    # -- fetching -------------------------------------------------------------------------
    def fetch(self, request: FetchRequest) -> Fetched:
        """params: year (and file, from partitions: must still be the manual file); limit."""
        p = request.params
        year = int(p["year"])
        stem = self.stem()
        if p.get("file", stem) != stem:
            raise ValueError(f"planned for {p['file']}, but {self.manual_path} is {stem}")
        out = self.extract()
        path = out / f"{year}.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        if "limit" in p:
            lines = lines[: int(p["limit"])]
        rows = [json.loads(line) for line in lines]
        if year >= int(stem.split("-")[1][:4]) and "limit" not in p:
            shutil.rmtree(out, ignore_errors=True)  # the last partition: free the disk
        body = canonical_json({"file": stem, "year": year, "rows": rows})
        url = f"{self.config.file_url}#{stem}:TERMDATE={year}"
        return Fetched(self.source_id, url, self.retrieved_at(), 200, body, "application/json")

    def health(self) -> HealthReport:
        """Manual source: the downloaded file is present and readable (no network)."""
        now = datetime.now(UTC)
        try:
            stem = self.stem()
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        return HealthReport(self.source_id, True, now, stem, (self.config.member,))

    # -- normalizing ----------------------------------------------------------------------
    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg, idb = self.config, load_idb_config()
        rows: list[dict[str, str]] = json.loads(fetched.content)["rows"]
        today = fetched.retrieved_at.astimezone(UTC).date()
        groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in rows:
            k = kept_direct(r)
            key = dedupe_key(r, cfg)
            if k is None or key is None or k[0] > today:
                continue
            groups[f"{key}#{k[0].isoformat()}"].append(r)
        for base in sorted(groups):
            unique = sorted({canonical_json(r): r for r in groups[base]}.items())
            for n, (_, r) in enumerate(unique, start=1):
                uid = base if len(unique) == 1 else f"{base}~{n}"
                yield from self._case(fetched, uid, r, idb)

    def _case(
        self, fetched: Fetched, uid: str, r: Mapping[str, str], idb: IDBConfig
    ) -> Iterator[NormalizedRow]:
        k = kept_direct(r)
        district = court(r, self.config)
        assert k is not None  # normalize() kept only rows that pass the filter
        assert district is not None
        closed, amount = k
        docket = (r.get("DOCKET") or "").strip()
        jurisdiction = county_fips(r.get("COUNTY")) or district
        ctx = RecordContext(fetched, jurisdiction, uid, "idb_civil_case", r)
        yield ctx.source_record()
        filed = us_date(r.get("FILEDATE"))
        office = (r.get("OFFICE") or "").strip() or "-"
        nos = (r.get("NOS") or "").strip()
        yield ctx.fact(
            "court_case", case_uid=uid, court_id=f"us.{district}", case_number_raw=docket,
            case_number_norm=f"{office}:{docket}", case_type="civil",
            nature_of_suit=nos if nos and nos != "-8" else None,
            filed_on=filed if filed is not None and filed <= closed else None,
            closed_on=closed, status=None,
        )  # fmt: skip
        for role, col in (("creditor", "PLT"), ("debtor", "DEF")):
            raw = " ".join((r.get(col) or "").split())
            if raw and raw != "-8":
                yield from self._party(ctx, uid, role, raw)
        yield ctx.fact(
            "judgment", judgment_uid=f"{uid}:judgment", case_uid=uid, entered_on=closed,
            principal=principal(amount, idb), interest=None, costs=None, rate=None,
            judgment_type="money", lien_instrument_uid=None,
        )  # fmt: skip

    def _party(self, ctx: RecordContext, uid: str, role: str, raw: str) -> Iterator[NormalizedRow]:
        name = strip_et_al(raw) or raw
        nc = classify(name)
        party_id = stable_id(self.source_id, uid, role, clean(name))
        yield ctx.fact(
            "party", party_id=party_id, raw_name=raw, party_kind=nc.party_kind,
            org_form=nc.org_form, org_name_norm=nc.org_name_norm, address_id=None,
        )  # fmt: skip
        yield ctx.fact("case_party", case_uid=uid, party_id=party_id, role=role)
