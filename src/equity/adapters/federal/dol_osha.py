"""OSHA inspections that ended in citation penalties: the establishment owes the penalty.

Two DOL enforcement tables, joined on activity_nr (one inspection):

- inspection: activity_nr, reporting_id (the OSHA federal or state-plan office), estab_name,
  site_address, site_city, site_state, site_zip, mail_street / mail_city / mail_state /
  mail_zip, owner_type, naics_code, insp_type, open_date, close_case_date.
- violation: activity_nr, citation_id, delete_flag (X = deleted), standard, viol_type (S
  serious, W willful, R repeat, O other...), issuance_date, initial_penalty, current_penalty
  (after informal settlement or contest), contest_date, final_order_date, fta_penalty.

Access (checked 2026-11-25): enforcedata.dol.gov and its bulk host enfxfr.dol.gov redirect to
the DOL Open Data Portal (data.dol.gov), whose rows come only from the v4 API
(apiprod.dol.gov/v4/get/OSHA/inspection|violation/...) with an X-API-KEY issued to a
signed-in account; www.osha.gov (the establishment search and its downloads) answered every
client from this network with a CloudFront 403, robots.txt included. So this adapter reads
files saved by hand into data/manual/us.dol.osha_penalties/ (or path=, a file or a folder):
the portal's CSV downloads of both tables, the legacy osha_inspection*.csv /
osha_violation*.csv bulk files, zips of them, or saved API JSON. Each file's rows are told
apart by their columns (estab_name: inspection; citation_id + current_penalty: violation).
It is not registered until a keyless route exists or a key is approved.

Kept: inspections whose non-deleted violations carry a current penalty above zero. Each is
one instrument (doc_type OTHER: a citation penalty, not a lien): principal_amount = the sum of
current_penalty, recorded_on = the earliest issuance_date of a penalized citation,
doc_type_raw "OSHA citation penalties, N violations (S 2, O 1)", debtor = the establishment at
the inspection site address, creditor = the Occupational Safety and Health Administration.
TODO(Brandon): penalties from state-plan inspections (reporting_id names a state-plan office)
are owed to that state's agency, not federal OSHA; confirm the office mapping before the
creditor is split. The amounts are assessed, not balances (payment is not published).

Joining two multi-gigabyte tables in memory is not possible, so the first fetch makes one
streaming pass over the saved files into an SQLite file under data/work/ (penalized
violations, then the inspections they belong to, keyed by site state) and every partition
reads its state from it. Partitions: site_state, plus OTHER for blank or unknown codes; the
work file is deleted after the OTHER partition (the last). `limit` keeps the first `limit`
inspections by activity_nr.

Terms: U.S. government data, public domain (catalog.data.gov "DOL Enforcement Data -
Inspection"); data.dol.gov robots.txt disallows only /static/.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import closing
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import address, jurisdiction, scrub_json, text
from equity.adapters.federal.dol_whd import (
    case_key,
    day,
    files_stem,
    files_time,
    manual_files,
    money,
    records,
)
from equity.adapters.federal.fcc_uls import OTHER, state_partition, us_states
from equity.adapters.rows import RecordContext, canonical_json
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

CHECKED_ON = "2026-11-25"
METADATA_URL = "https://apiprod.dol.gov/v4/datasets/10334"
API_URL = "https://apiprod.dol.gov/v4/get/OSHA/inspection/json"
TERMS_URL = "https://catalog.data.gov/dataset/dol-enforcement-data-inspection"
CREDITOR = "Occupational Safety and Health Administration"
INSPECTION = ("activity_nr", "reporting_id", "estab_name", "site_address", "site_city",
              "site_state", "site_zip", "mail_street", "mail_city", "mail_state", "mail_zip",
              "owner_type", "naics_code", "sic_code", "insp_type", "insp_scope", "open_date",
              "close_conf_date", "close_case_date")  # fmt: skip
VIOLATION = ("activity_nr", "citation_id", "delete_flag", "standard", "viol_type",
             "issuance_date", "initial_penalty", "current_penalty", "contest_date",
             "final_order_date", "fta_penalty")  # fmt: skip


def kind_of(row: Mapping[str, Any]) -> str | None:
    if "estab_name" in row and "activity_nr" in row:
        return "inspection"
    if "citation_id" in row and "current_penalty" in row and "activity_nr" in row:
        return "violation"
    return None


def penalized(v: Mapping[str, Any]) -> bool:
    deleted = (text(v.get("delete_flag")) or "").upper() == "X"
    return not deleted and money(v.get("current_penalty")) is not None


def _project(row: Mapping[str, Any], cols: tuple[str, ...]) -> dict[str, Any]:
    out = {k: row.get(k) for k in cols if row.get(k) not in (None, "")}
    out["activity_nr"] = case_key(row.get("activity_nr"))
    return out


def build_index(files: list[Path], db: Path) -> None:
    """One streaming pass: penalized violations, then their inspections (by site state)."""
    part = db.with_name(db.name + ".part")
    part.unlink(missing_ok=True)
    part.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(part)) as con:
        con.execute("CREATE TABLE viol (activity_nr TEXT NOT NULL, row TEXT NOT NULL)")
        con.execute("CREATE TABLE insp (activity_nr TEXT PRIMARY KEY, state TEXT NOT NULL, "
                    "row TEXT NOT NULL)")  # fmt: skip
        for f in files:
            batch = []
            for r in records(f):
                if kind_of(r) == "violation" and penalized(r) and case_key(r.get("activity_nr")):
                    v = _project(r, VIOLATION)
                    batch.append((v["activity_nr"], canonical_json(v).decode()))
                    if len(batch) >= 10_000:
                        con.executemany("INSERT INTO viol VALUES (?, ?)", batch)
                        batch = []
            con.executemany("INSERT INTO viol VALUES (?, ?)", batch)
        con.execute("CREATE INDEX viol_nr ON viol (activity_nr)")
        for f in files:
            for r in records(f):
                nr = case_key(r.get("activity_nr"))
                if kind_of(r) != "inspection" or nr is None:
                    continue
                if con.execute("SELECT 1 FROM viol WHERE activity_nr = ? LIMIT 1",
                               (nr,)).fetchone() is None:  # fmt: skip
                    continue
                i = _project(r, INSPECTION)
                con.execute("INSERT OR IGNORE INTO insp VALUES (?, ?, ?)",
                            (nr, state_partition(text(r.get("site_state"))),
                             canonical_json(i).decode()))  # fmt: skip
        con.execute("CREATE INDEX insp_state ON insp (state)")
        con.commit()
    part.replace(db)


def read_state(db: Path, state: str | None, limit: int | None) -> list[dict[str, Any]]:
    """The inspections of one state (None: all), each with its penalized violations."""
    with closing(sqlite3.connect(db)) as con:
        where, args = ("WHERE state = ?", [state]) if state is not None else ("", [])
        sql = f"SELECT activity_nr, row FROM insp {where} ORDER BY length(activity_nr), activity_nr"  # noqa: S608 - fixed text
        rows = con.execute(sql, args).fetchall()
        if limit is not None:
            rows = rows[:limit]
        out = []
        for nr, raw in rows:
            viols = [json.loads(v) for (v,) in con.execute(
                "SELECT row FROM viol WHERE activity_nr = ? ORDER BY row", (nr,))]  # fmt: skip
            out.append({**json.loads(raw), "violations": viols})
    return out


class DOLOSHAPenalties(Adapter):
    source_id: ClassVar[str] = "us.dol.osha_penalties"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "manual"
    pii_fields: ClassVar[tuple[str, ...]] = ("estab_name", "site_address", "mail_street")
    cache_dir: ClassVar[Path] = Path("data") / "work" / "us_dol_osha_penalties"

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "recorder",  # nearest kind: an index of debts, as the config/liens sources
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": METADATA_URL,
            "terms_url": TERMS_URL,
            "terms_summary": (
                "OSHA inspection and violation tables (DOL enforcement data), U.S. government "
                "data, public domain. Rows only via the DOL v4 API (key from a signed-in "
                "data.dol.gov account); osha.gov refused this network (CloudFront 403). Read "
                "from files saved by hand (data/manual/us.dol.osha_penalties/)."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        for st in (*us_states(), OTHER):
            yield {"state": st}

    def index(self, files: list[Path]) -> Path:
        db = self.cache_dir / f"{files_stem(files)}.sqlite"
        if not db.exists():
            build_index(files, db)
        return db

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: state (a partition; absent = every state); limit (the first `limit`
        inspections by activity_nr); path (saved files instead of data/manual/<source_id>/)."""
        p = request.params
        state = p.get("state")
        if state is not None and state != OTHER and state not in us_states():
            raise ValueError(f"unknown state partition {state!r}")
        files = manual_files(self.source_id, p.get("path"))
        db = self.index(files)
        rows = read_state(db, state, int(p["limit"]) if "limit" in p else None)
        if state in (OTHER, None) and "limit" not in p:
            db.unlink(missing_ok=True)  # the last partition (or a whole read): free the disk
        stem = files_stem(files)
        saved = [{"name": f.name, "bytes": f.stat().st_size} for f in files]
        body = {"files": saved, "state": state, "inspections": rows}
        req = f"{API_URL}#{stem}" + (f":site_state={state}" if state else "")
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
        return scrub_json(content, ("estab_name",), ("site_address", "mail_street"))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        today = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        data = json.loads(fetched.content).get("inspections") or []
        for i in sorted(data, key=canonical_json):
            nr = case_key(i.get("activity_nr"))
            name = text(i.get("estab_name"))
            viols = [v for v in i.get("violations") or [] if penalized(v)
                     and case_key(v.get("activity_nr")) == nr]  # fmt: skip
            amounts = [m for v in viols if (m := money(v.get("current_penalty"))) is not None]
            issued = [d for v in viols if (d := day(v.get("issuance_date"))) is not None]
            if nr is None or nr in seen or name is None or not clean(name) or not amounts:
                continue
            on: date | None = min(issued) if issued else None
            if on is None or on > today:
                continue
            seen.add(nr)
            st = text(i.get("site_state"))
            us = state_partition(st) != OTHER
            ctx = RecordContext(fetched, jurisdiction(st if us else None), nr, "osha_inspection",
                                i)  # fmt: skip
            yield ctx.source_record()
            addr = address(i.get("site_address"), i.get("site_city"), st if us else None,
                           i.get("site_zip") if us else None)  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            types = Counter((text(v.get("viol_type")) or "?").upper() for v in viols)
            label = (f"OSHA citation penalties, {len(viols)} violation"
                     f"{'s' if len(viols) != 1 else ''} ("
                     + ", ".join(f"{t} {n}" for t, n in sorted(types.items())) + ")")  # fmt: skip
            rid = text(i.get("reporting_id"))
            if rid:
                label += f"; office {rid}"
            uid = stable_id(self.source_id, "inspection", nr)
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=nr, book_type=None,
                book=None, page=None, doc_type_raw=label, doc_type="OTHER", recorded_on=on,
                recorded_seq=None, executed_on=None, consideration=None,
                principal_amount=sum(amounts, Decimal(0)), max_secured_amount=None,
                maturity_date=None, amount_source="index", legal_desc_raw=None,
            )  # fmt: skip
            for role, who, a in (("debtor", name, addr), ("creditor", CREDITOR, None)):
                nc = classify(who)
                pid = stable_id(self.source_id, nr, role, clean(who))
                yield ctx.fact("party", party_id=pid, raw_name=who, party_kind=nc.party_kind,
                               org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                               address_id=None if a is None else a["address_id"])  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid, role=role,
                               seq=1)  # fmt: skip
