"""U.S. Department of Labor Wage and Hour Division (WHD) compliance actions: employers that
agreed to pay back wages or were assessed civil money penalties.

The dataset ("WHD Enforcement", formerly the WHISARD bulk file on enforcedata.dol.gov) holds
every concluded WHD compliance action since FY 2005, one row per case: case_id, the employer's
trade name (trade_nm) and legal name (legal_name), street_addr_1_txt, cty_nm, st_cd, zip_cd,
NAICS, findings_start_date / findings_end_date, the case totals bw_atp_amt (back wages agreed
to pay), ee_atp_cnt (employees due them) and cmp_assd (civil money penalties assessed), the
same per law (flsa_*, dbra_*, h2a_*, sca_*, fmla_*...) and flsa_repeat_violator (R, W, RW).

Access (checked 2026-11-25): enforcedata.dol.gov and its bulk host enfxfr.dol.gov now redirect
to the DOL Open Data Portal (data.dol.gov). There the rows come only from the v4 API
(apiprod.dol.gov/v4/get/WHD/enforcement/...), which answers 401 without an X-API-KEY issued to
a signed-in portal account; the keyless metadata endpoint (apiprod.dol.gov/v4/datasets/10362)
gives the column list and a 10-row preview only. This adapter does not sign in or use a key:
it reads files saved by hand into data/manual/us.dol.whd_cases/ (or path=, a file or a
folder): the portal's CSV download, the legacy whd_whisard CSV (same column names), a zip of
either, or saved API JSON ({"data": [...]}). It is not registered until a keyless bulk route
exists or a key is approved.

What is a debt here: a case with back wages agreed to pay > 0 or civil money penalties > 0.
Each becomes up to two instruments (doc_type OTHER, an administrative finding, not a lien):

- <case_id>-BW: principal_amount = bw_atp_amt, doc_type_raw "WHD back wages agreed to pay,
  N employees (FLSA, DBRA...)".
- <case_id>-CMP: principal_amount = cmp_assd, doc_type_raw "WHD civil money penalties
  assessed (FLSA CL...)".

recorded_on is findings_end_date (the end of the period WHD found violations; the case
close date is not published, so this is earlier than the agreement or assessment), else
findings_start_date. Parties: debtor = the employer, its legal name (seq 1) and, when
different, its trade name (seq 2), both at the published address; creditor = the U.S.
Department of Labor, Wage and Hour Division (back wages are paid to the employees through
WHD). The amounts are agreed or assessed, not balances: WHD does not publish whether they
were paid.

Partitions: one per employer state (st_cd), plus OTHER for blank or unknown codes; each
streams the saved files and keeps that state's debt rows. Without `state` every state is
read (fixtures). `limit` keeps the first `limit` cases by case_id.

Terms: U.S. government data, public domain (catalog.data.gov lists the dataset under the U.S.
public domain label); data.dol.gov robots.txt disallows only /static/.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import IO, Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import address, jurisdiction, scrub_json, text
from equity.adapters.federal.fcc_uls import OTHER, state_partition, us_states
from equity.adapters.rows import RecordContext, canonical_json
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

CHECKED_ON = "2026-11-25"
MANUAL_DIR = Path("data") / "manual"
METADATA_URL = "https://apiprod.dol.gov/v4/datasets/10362"
API_URL = "https://apiprod.dol.gov/v4/get/WHD/enforcement/json"
TERMS_URL = "https://catalog.data.gov/dataset/wage-and-hour-division-compliance-action-data"
CREDITOR = "U.S. Department of Labor, Wage and Hour Division"
DATA_SUFFIXES = (".csv", ".zip", ".json")

KEEP = ("case_id", "trade_nm", "legal_name", "street_addr_1_txt", "cty_nm", "st_cd", "zip_cd",
        "naic_cd", "naics_code_description", "case_violtn_cnt", "ee_violtd_cnt", "bw_atp_amt",
        "ee_atp_cnt", "cmp_assd", "findings_start_date", "findings_end_date",
        "flsa_repeat_violator")  # fmt: skip
# Per-law amounts: <law>_bw_atp_amt (or <law>_bw_amt) and <law>_cmp_assd_amt.
LAW_BW = re.compile(r"^([a-z0-9_]+?)_bw(?:_atp)?_amt$")
LAW_CMP = re.compile(r"^([a-z0-9_]+?)_cmp_assd_amt$")
FLSA_PARTS = frozenset({"flsa_mw", "flsa_ot", "flsa_15a3"})  # parts of the FLSA total
REPEAT = {"R": "repeat", "W": "willful", "RW": "repeat and willful"}


# --- reading the saved files ---------------------------------------------------------------


def manual_files(source_id: str, path: str | None = None) -> list[Path]:
    """The data files to read: `path` (a file or a folder), else data/manual/<source_id>/."""
    root = Path(path) if path else MANUAL_DIR / source_id
    if root.is_file():
        return [root]
    files = sorted(p for p in root.glob("*") if p.is_file()
                   and p.name.lower().endswith(DATA_SUFFIXES)) if root.is_dir() else []  # fmt: skip
    if not files:
        raise FileNotFoundError(
            f"{root}: no saved .csv, .zip or .json files. Download the dataset by hand from "
            f"the DOL Open Data Portal (https://data.dol.gov) and save it there, or pass "
            f"path=<file or folder>."
        )
    return files


def files_stem(files: list[Path]) -> str:
    """Names one set of saved files: their names and sizes, hashed."""
    ident = "|".join(f"{p.name}:{p.stat().st_size}" for p in files)
    return hashlib.sha256(ident.encode()).hexdigest()[:12]


def files_time(files: list[Path]) -> datetime:
    """When the files were saved (the newest mtime, whole seconds): their retrieval time."""
    return datetime.fromtimestamp(int(max(p.stat().st_mtime for p in files)), UTC)


def _key(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lstrip("﻿").lower()).strip("_")


def _csv_records(stream: IO[str]) -> Iterator[dict[str, str]]:
    reader = csv.reader(stream)
    head = next(reader, None)
    if head is None:
        return
    keys = [_key(h) for h in head]
    for cells in reader:
        if cells:
            yield {k: v for k, v in zip(keys, cells, strict=False) if k}


def records(path: Path) -> Iterator[dict[str, Any]]:
    """Rows of one saved file, column names lowercased: a CSV, a zip of CSVs (streamed), or
    API JSON ({"data": [...]} or a bare list)."""
    name = path.name.lower()
    if name.endswith(".json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("data") if isinstance(data, dict) else data
        for r in rows or []:
            if isinstance(r, dict):
                yield {_key(str(k)): v for k, v in r.items()}
    elif name.endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            for info in sorted(zf.infolist(), key=lambda i: i.filename):
                if info.filename.lower().endswith(".csv"):
                    with zf.open(info) as raw:
                        yield from _csv_records(io.TextIOWrapper(
                            raw, encoding="utf-8-sig", errors="replace", newline=""))  # fmt: skip
    else:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
            yield from _csv_records(fh)


# --- values ---------------------------------------------------------------------------------


def money(value: Any) -> Decimal | None:
    """'12136.0', '$1,234.50' -> Decimal (cents); blank, unparseable or <= 0 -> None."""
    s = str(value if value is not None else "").replace(",", "").replace("$", "").strip()
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d.quantize(Decimal("0.01")) if d.is_finite() and d > 0 else None


def day(value: Any) -> date | None:
    """'2005-07-19T00:00:00', '2005-07-19', '07/19/2005' -> date."""
    s = (text(value) or "").replace("T", " ").split(" ")[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC).date()
        except ValueError:
            continue
    return None


def case_key(value: Any) -> str | None:
    """case_id as text without a float tail ('1460300.0' -> '1460300')."""
    s = text(value)
    if s is None:
        return None
    return s[:-2] if s.endswith(".0") and s[:-2].isdigit() else s


def laws(row: Mapping[str, Any], pattern: re.Pattern[str]) -> list[str]:
    """Labels of the laws with an amount above zero ('flsa_cl' -> 'FLSA CL')."""
    found = []
    for k in sorted(row):
        m = pattern.match(k)
        if m and m.group(1) not in FLSA_PARTS and money(row.get(k)) is not None:
            found.append(m.group(1).upper().replace("_", " "))
    return found


def is_debt(row: Mapping[str, Any]) -> bool:
    return money(row.get("bw_atp_amt")) is not None or money(row.get("cmp_assd")) is not None


def slim(row: Mapping[str, Any]) -> dict[str, Any]:
    """The KEEP columns and every per-law back wage or penalty amount above zero."""
    out = {k: row.get(k) for k in KEEP if k in row}
    for k, v in row.items():
        if (LAW_BW.match(k) or LAW_CMP.match(k)) and money(v) is not None:
            out[k] = v
    return out


class DOLWageHourCases(Adapter):
    source_id: ClassVar[str] = "us.dol.whd_cases"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "manual"
    pii_fields: ClassVar[tuple[str, ...]] = ("trade_nm", "legal_name", "street_addr_1_txt")

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "recorder",  # nearest kind: an index of debts, as the config/liens sources
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": METADATA_URL,
            "terms_url": TERMS_URL,
            "terms_summary": (
                "DOL Wage and Hour Division compliance actions (FY2005 on), U.S. government "
                "data, public domain. Rows only via the DOL v4 API, which needs a key from a "
                "signed-in data.dol.gov account; read from files saved by hand "
                "(data/manual/us.dol.whd_cases/). data.dol.gov robots.txt disallows /static/."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        for st in (*us_states(), OTHER):
            yield {"state": st}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: state (a partition; absent = every state); limit (the first `limit` cases
        by case_id); path (a saved file or folder instead of data/manual/<source_id>/)."""
        p = request.params
        state = p.get("state")
        if state is not None and state != OTHER and state not in us_states():
            raise ValueError(f"unknown state partition {state!r}")
        files = manual_files(self.source_id, p.get("path"))
        rows: dict[str, dict[str, Any]] = {}
        for f in files:
            for r in records(f):
                key = case_key(r.get("case_id"))
                if key is None or not is_debt(r):
                    continue
                if state is not None and state_partition(text(r.get("st_cd"))) != state:
                    continue
                rows.setdefault(key, slim(r))  # a case in two saved files: the first copy
        keys = sorted(rows, key=lambda k: (len(k), k))
        if "limit" in p:
            keys = keys[: int(p["limit"])]
        stem = files_stem(files)
        saved = [{"name": f.name, "bytes": f.stat().st_size} for f in files]
        body = {"files": saved, "state": state, "rows": [rows[k] for k in keys]}
        req = f"{API_URL}#{stem}" + (f":st_cd={state}" if state else "")
        return Fetched(self.source_id, req, files_time(files), None, canonical_json(body),
                       "application/json")  # fmt: skip

    def health(self) -> HealthReport:
        """Manual source: the saved files are present (no network)."""
        now = datetime.now(UTC)
        try:
            files = manual_files(self.source_id)
        except OSError as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        return HealthReport(self.source_id, True, now, f"{len(files)} files {files_stem(files)}")

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, ("trade_nm", "legal_name"), ("street_addr_1_txt",))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        today = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for r in sorted(json.loads(fetched.content).get("rows") or [], key=canonical_json):
            key = case_key(r.get("case_id"))
            on = day(r.get("findings_end_date")) or day(r.get("findings_start_date"))
            names = [n for n in dict.fromkeys(text(r.get(c)) for c in ("legal_name", "trade_nm"))
                     if n and clean(n)]  # fmt: skip
            if key is None or key in seen or on is None or on > today or not names:
                continue
            if len({clean(n) for n in names}) < len(names):
                names = names[:1]
            seen.add(key)
            st = text(r.get("st_cd"))
            ctx = RecordContext(fetched, jurisdiction(st), key, "whd_case", r)
            yield ctx.source_record()
            addr = address(r.get("street_addr_1_txt"), r.get("cty_nm"),
                           st if state_partition(st) != OTHER else None,
                           r.get("zip_cd"))  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            repeat = REPEAT.get((text(r.get("flsa_repeat_violator")) or "").upper())
            for kind, amount in (("BW", money(r.get("bw_atp_amt"))),
                                 ("CMP", money(r.get("cmp_assd")))):  # fmt: skip
                if amount is None:
                    continue
                if kind == "BW":
                    n = case_key(r.get("ee_atp_cnt"))
                    label = "WHD back wages agreed to pay" + (f", {n} employees" if n and
                                                               n != "0" else "")  # fmt: skip
                    found = laws(r, LAW_BW)
                else:
                    label = "WHD civil money penalties assessed"
                    found = laws(r, LAW_CMP)
                if found:
                    label += f" ({', '.join(found)})"
                if repeat:
                    label += f"; FLSA {repeat} violator"
                uid = stable_id(self.source_id, kind, key)
                yield ctx.fact(
                    "instrument", instrument_uid=uid, instrument_number=f"{key}-{kind}",
                    book_type=None, book=None, page=None, doc_type_raw=label, doc_type="OTHER",
                    recorded_on=on, recorded_seq=None, executed_on=None, consideration=None,
                    principal_amount=amount, max_secured_amount=None, maturity_date=None,
                    amount_source="index", legal_desc_raw=None,
                )  # fmt: skip
                parties = [("debtor", n, addr) for n in names] + [("creditor", CREDITOR, None)]
                seqs: dict[str, int] = {}
                for role, name, a in parties:
                    seqs[role] = seqs.get(role, 0) + 1
                    nc = classify(name)
                    pid = stable_id(self.source_id, key, kind, role, clean(name))
                    yield ctx.fact("party", party_id=pid, raw_name=name,
                                   party_kind=nc.party_kind, org_form=nc.org_form,
                                   org_name_norm=nc.org_name_norm,
                                   address_id=None if a is None else a["address_id"])  # fmt: skip
                    yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid,
                                   role=role, seq=seqs[role])  # fmt: skip
