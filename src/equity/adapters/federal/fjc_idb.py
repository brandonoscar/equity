"""Federal civil money judgments from the FJC Integrated Database (IDB), via CourtListener.

The Federal Judicial Center's IDB has one record per civil case termination reported by the
district courts: court, office, docket number, filing and termination dates, nature of suit,
the first-listed plaintiff and defendant (names cut at about 30 characters), who judgment
was for, the nature of the judgment and the amount received. CourtListener republishes it
as one bz2 CSV per snapshot on a public S3 bucket (config/courts_federal/...yaml).

Kept: judgments for the plaintiff that are monetary awards with an amount, and a parseable
termination date (the filter in `kept`). The plaintiff is the judgment creditor and the
defendant the debtor. Each kept IDB record becomes one court_case, its two parties and one
money judgment entered on the termination date.

The FJC publishes the same IDB itself (fjc_idb_direct.py, us.fjc.idb.direct.civil_judgments),
with judgments terminated after CourtListener's copy stops. That source wins: a kept row whose
district + office + docket + filing date is among the FJC file's kept rows is dropped here, so
each judgment loads once. The FJC keys come from its manual file (FJCDirectCivilJudgments.
kept_keys), and the file's name is stored with every partition.

Partitions are years of date_terminated. The snapshot is downloaded once into data/work, and
one streaming pass writes the kept rows, split by year, into a small local extract; the bz2
is then deleted. Each partition reads its year from the extract (the stored raw bytes are that
year's kept rows), and the extract is deleted after the last year.
"""

from __future__ import annotations

import bz2
import csv
import json
import re
import shutil
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import IO, Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

CONFIG = "courts_federal/us.fjc.idb.civil_judgments.yaml"
SNAPSHOT = re.compile(r"fjc-integrated-database-(\d{4})-(\d{2})-(\d{2})\.csv\.bz2$")
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
# "SMITH, ET AL" / "ACME CO ETAL" / "DOE, ET. AL." / "ROE, ET ALS", and the same marker cut
# short by the ~30-character name limit when a comma leads it ("..., ET" / "..., ET A").
_ET_AL = re.compile(
    r"(?:(?:,\s*|\s+)ET\.?\s*ALS?\.?|,\s*ET(?:\s+A)?|\s+ET\s+A)[\s.,\\]*$", re.IGNORECASE
)


@dataclass(frozen=True)
class IDBConfig:
    source_id: str
    bucket: str
    prefix: str
    first_year: int
    for_plaintiff: frozenset[str]
    money: frozenset[str]
    amount_unit: int
    amount_floor_code: str
    terms: Mapping[str, Any]


@cache
def load_config() -> IDBConfig:
    import yaml

    d = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    return IDBConfig(
        source_id=d["source_id"],
        bucket=d["bucket"],
        prefix=d["prefix"],
        first_year=int(d["first_year"]),
        for_plaintiff=frozenset(str(c) for c in d["for_plaintiff"]),
        money=frozenset(str(c) for c in d["money"]),
        amount_unit=int(d["amount_unit"]),
        amount_floor_code=str(d["amount_floor_code"]),
        terms=dict(d["terms"]),
    )


@cache
def _state_codes() -> frozenset[str]:
    from equity.geo import counties

    return frozenset(c.state_fips for c in counties())


def iso_date(value: str | None) -> date | None:
    """'1987-08-14' -> date; anything else (blank, '9100103', '1987-02-30') -> None."""
    m = _ISO.fullmatch((value or "").strip())
    if m is None:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def strip_et_al(name: str) -> str:
    """'USA, ET AL' -> 'USA'. The raw name is kept as given; this is for matching only."""
    return _ET_AL.sub("", " ".join(name.split())).strip(" ,")


def county_fips(code: str | None) -> str | None:
    """IDB county code -> 5-digit FIPS, or None for unknown/foreign codes (88888, 99999, 0)."""
    text = (code or "").strip()
    if not text.isdigit() or len(text) > 5:
        return None
    fips = text.zfill(5)
    if fips[:2] not in _state_codes() or fips[2:] == "000":
        return None
    return fips


def kept(row: Mapping[str, str], cfg: IDBConfig) -> tuple[date, int] | None:
    """(termination date, amount in thousands) for a money judgment for the plaintiff."""
    if (row.get("judgment") or "").strip() not in cfg.for_plaintiff:
        return None
    if (row.get("nature_of_judgement") or "").strip() not in cfg.money:
        return None
    amount = (row.get("amount_received") or "").strip()
    if not amount.isdigit() or int(amount) <= 0:
        return None
    closed = iso_date(row.get("date_terminated"))
    if closed is None:
        return None
    return closed, int(amount)


def principal(amount: int, cfg: IDBConfig) -> Decimal | None:
    """Thousands -> dollars. The floor code ('$9,999,000 or more') has no amount: None."""
    if str(amount) == cfg.amount_floor_code:
        return None
    return Decimal(amount * cfg.amount_unit)


def dedupe_key(row: Mapping[str, str]) -> str:
    """us.<district>:<office>:<docket>:<filed>: the key shared with the FJC's own file."""
    return case_uid(row).rsplit("#", 1)[0]


def case_uid(row: Mapping[str, str]) -> str:
    """us.<district>:<office>:<docket>:<filed>#<IDB id>.

    District, office, docket number and filing date do not identify an IDB record on their
    own: a reopened case, or a docket reported on more than one record, comes back with the
    same four (147 of the 412,413 kept rows in the 2026-09-30 snapshot, some with different
    amounts or parties). The CourtListener record id makes each record its own case; the
    docket is still shared through court_id + case_number_norm."""
    district = row["district_id"].strip().lower()
    office = (row.get("office") or "").strip() or "-"
    filed = (row.get("date_filed") or "").strip() or "-"
    return f"us.{district}:{office}:{row['docket_number'].strip()}:{filed}#{row['id'].strip()}"


def read_csv_rows(fh: IO[str]) -> Iterator[dict[str, str] | None]:
    """Rows of the IDB CSV as dicts; None for a row with the wrong number of fields."""
    reader = csv.reader(fh, escapechar="\\", doublequote=False)
    header = next(reader)
    for rec in reader:
        yield dict(zip(header, rec, strict=True)) if len(rec) == len(header) else None


def list_bucket(xml: str) -> list[tuple[str, int]]:
    keys = re.findall(r"<Key>([^<]+)</Key>", xml)
    sizes = [int(s) for s in re.findall(r"<Size>(\d+)</Size>", xml)]
    if len(keys) != len(sizes):
        raise ValueError("S3 listing: keys and sizes do not pair up")
    return list(zip(keys, sizes, strict=True))


def snapshot_date(key: str) -> date:
    m = SNAPSHOT.search(key)
    if m is None:
        raise ValueError(f"not an IDB snapshot key: {key!r}")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _fjc_direct_keys() -> tuple[str, frozenset[str]]:
    from equity.adapters.federal.fjc_idb_direct import FJCDirectCivilJudgments

    stem, keys = FJCDirectCivilJudgments().kept_keys()
    return f"us.fjc.idb.direct.civil_judgments:{stem}", keys


class FJCCivilJudgments(Adapter):
    source_id: ClassVar[str] = "us.fjc.idb.civil_judgments"
    adapter_version: ClassVar[str] = "2"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("plaintiff", "defendant")
    cache_dir: ClassVar[Path] = Path("data") / "work" / "us_fjc_idb"

    def __init__(
        self,
        client: PoliteClient | None = None,
        preferred: Callable[[], tuple[str, frozenset[str]]] | None = None,
    ) -> None:
        """preferred: (name, keys) of the records another source loads instead (default:
        the FJC's own file, read from its manual path)."""
        self.config = load_config()
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=600.0)
        self.preferred = preferred or _fjc_direct_keys

    def source_row(self) -> Mapping[str, Any]:
        t = self.config.terms
        return {
            "source_id": self.source_id,
            "kind": "court",
            "jurisdiction": "us",
            "access_method": "bulk",
            "base_url": self.config.bucket + self.config.prefix,
            "terms_url": t["url"],
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t["robots_checked_on"],
            "cost_model": t["cost_model"],
        }

    # -- the bucket ---------------------------------------------------------------------
    def snapshots(self) -> list[tuple[str, int]]:
        """(key, size) of every snapshot in the bucket, oldest first."""
        found: list[tuple[str, int]] = []
        token: str | None = None
        while True:
            params = {"list-type": "2", "prefix": self.config.prefix}
            if token:
                params["continuation-token"] = token
            resp = self.client.get(self.config.bucket, params)
            if resp.status != 200:
                raise ValueError(f"S3 listing: HTTP {resp.status}")
            xml = resp.content.decode("utf-8")
            found += [(k, s) for k, s in list_bucket(xml) if SNAPSHOT.search(k)]
            nxt = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", xml)
            if not nxt:
                return sorted(found, key=lambda ks: (snapshot_date(ks[0]), ks[0]))
            token = nxt.group(1)

    def latest(self) -> tuple[str, int]:
        snaps = self.snapshots()
        if not snaps:
            raise ValueError("no IDB snapshot in the bucket")
        return snaps[-1]

    def partitions(self) -> Iterator[dict[str, str]]:
        key, size = self.latest()
        for year in range(self.config.first_year, snapshot_date(key).year + 1):
            yield {"key": key, "size": str(size), "year": str(year)}

    # -- the local cache ----------------------------------------------------------------
    def _extract_dir(self, key: str) -> Path:
        return self.cache_dir / Path(key).name.removesuffix(".csv.bz2")

    def _download(self, key: str, size: int) -> tuple[Path, datetime]:
        cached = self.cache_dir / Path(key).name
        if cached.exists() and cached.stat().st_size == size:
            return cached, self.client.now()
        resp = self.client.get(self.config.bucket + key)
        if resp.status != 200 or len(resp.content) != size:
            raise ValueError(f"{key}: status {resp.status}, {len(resp.content)} of {size} bytes")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_suffix(".part")
        tmp.write_bytes(resp.content)
        tmp.replace(cached)
        return cached, resp.retrieved_at

    def extract(self, key: str, size: int) -> Path:
        """One pass over the snapshot: kept rows to <year>.jsonl files, then drop the bz2."""
        out = self._extract_dir(key)
        if (out / "_manifest.json").exists():
            return out
        src, retrieved_at = self._download(key, size)
        preferred_name, preferred = self.preferred()
        tmp = out.with_name(out.name + ".part")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        files: dict[int, IO[str]] = {}
        counts = {"rows": 0, "bad_rows": 0, "kept": 0, "in_preferred": 0}
        try:
            with bz2.open(src, "rt", encoding="utf-8", errors="replace", newline="") as fh:
                for row in read_csv_rows(fh):
                    counts["rows"] += 1
                    if row is None:
                        counts["bad_rows"] += 1
                        continue
                    k = kept(row, self.config)
                    if k is None:
                        continue
                    if dedupe_key(row) in preferred:
                        counts["in_preferred"] += 1
                        continue
                    year = k[0].year
                    if year not in files:
                        files[year] = (tmp / f"{year}.jsonl").open("w", encoding="utf-8")
                    files[year].write(canonical_json(row).decode("utf-8") + "\n")
                    counts["kept"] += 1
        finally:
            for f in files.values():
                f.close()
        manifest = {"key": key, "size": size, "retrieved_at": retrieved_at.isoformat(),
                    "deduped_against": preferred_name, **counts}  # fmt: skip
        (tmp / "_manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        shutil.rmtree(out, ignore_errors=True)
        tmp.replace(out)
        src.unlink(missing_ok=True)
        return out

    # -- fetching -----------------------------------------------------------------------
    def fetch(self, request: FetchRequest) -> Fetched:
        """params: key and year (from partitions); size (else looked up); limit (fixtures)."""
        p = request.params
        key, year = p["key"], int(p["year"])
        size = int(p["size"]) if "size" in p else dict(self.snapshots())[key]
        out = self.extract(key, size)
        manifest = json.loads((out / "_manifest.json").read_text())
        path = out / f"{year}.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        if "limit" in p:
            lines = lines[: int(p["limit"])]
        rows = [json.loads(line) for line in lines]
        if year >= snapshot_date(key).year and "limit" not in p:
            shutil.rmtree(out, ignore_errors=True)  # the last partition: free the disk
        body = canonical_json({"key": key, "year": year, "rows": rows,
                               "deduped_against": manifest.get("deduped_against")})  # fmt: skip
        url = f"{self.config.bucket}{key}#date_terminated={year}"
        at = datetime.fromisoformat(manifest["retrieved_at"])
        return Fetched(self.source_id, url, at, 200, body, "application/json")

    def health(self) -> HealthReport:
        """Live: the bucket still lists a snapshot."""
        try:
            key, size = self.latest()
        except (ValueError, OSError) as exc:
            return HealthReport(self.source_id, False, self.client.now(), repr(exc))
        return HealthReport(self.source_id, True, self.client.now(), f"{key} ({size} bytes)",
                            (Path(key).name,))  # fmt: skip

    # -- normalizing --------------------------------------------------------------------
    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = self.config
        rows: list[dict[str, str]] = json.loads(fetched.content)["rows"]
        today = fetched.retrieved_at.astimezone(UTC).date()
        for r in sorted(rows, key=lambda r: (len(r.get("id", "")), r.get("id", ""))):
            k = kept(r, cfg)
            ident = (r.get("id") or "").strip()
            district = (r.get("district_id") or "").strip().lower()
            docket = (r.get("docket_number") or "").strip()
            if k is None or not (ident and district and docket) or k[0] > today:
                continue
            closed, amount = k
            uid = case_uid(r)
            jurisdiction = county_fips(r.get("county_of_residence")) or district
            ctx = RecordContext(fetched, jurisdiction, ident, "idb_civil_case", r)
            yield ctx.source_record()
            filed = iso_date(r.get("date_filed"))
            office = (r.get("office") or "").strip() or "-"
            yield ctx.fact(
                "court_case", case_uid=uid, court_id=f"us.{district}", case_number_raw=docket,
                case_number_norm=f"{office}:{docket}", case_type="civil",
                nature_of_suit=(r.get("nature_of_suit") or "").strip() or None,
                filed_on=filed if filed is not None and filed <= closed else None,
                closed_on=closed, status=None,
            )  # fmt: skip
            for role, col in (("creditor", "plaintiff"), ("debtor", "defendant")):
                raw = " ".join((r.get(col) or "").split())
                if raw:
                    yield from self._party(ctx, uid, role, raw)
            yield ctx.fact(
                "judgment", judgment_uid=f"{uid}:judgment", case_uid=uid, entered_on=closed,
                principal=principal(amount, cfg), interest=None, costs=None, rate=None,
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
