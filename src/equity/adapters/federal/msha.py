"""MSHA Open Government Data: every mine (and mill, plant, contractor-served pit) the Mine
Safety and Health Administration has assigned an ID, its operators and controllers (a
company or a person) since 1970s, the operator's address of record, and the civil
penalties MSHA assessed for violations, from the pipe-delimited zips on the open data page.

Two sources:

- us.dol.msha_mines: Mines.zip (mine name, status and date, current operator and controller,
  state and county, commodity, company type), AddressofRecord.zip (the operator's business
  name and mailing address for the mine) and ControllerOperatorHistory.zip (every
  controller and operator period at each mine, with start and end dates and whether the
  controller is a PERSON or a COMPANY). One source record per mine (record_type mine):
  business, sos_id MSHA:<mine id>, the mine's name, status as published (Active,
  Abandoned...), status_date = the status date, principal address = the address of record,
  valid from the earliest operator period (else the status date); holders (role 'other'):
  every operator (title OPERATOR) and controller (title CONTROLLER; a person when MSHA says
  PERSON) with the end date of their latest period, and the address of record's business
  name as an operator at that address. Partitions: one per state of
  the mine (Mines.txt STATE); the three zips (~15 MB) are fetched once per adapter instance
  and kept in memory.

- us.dol.msha_assessed_penalties: AssessedViolations.zip (~110 MB; 1.3 GB of text, ~3M
  assessed violations since 2000). A debt: an assessment case's violations that are past
  their delinquent date (DELINQUENT_DT, set with the final order) with penalty principal
  unpaid (CURRENT_ASSESSMENT_AMT - PAID_PROPOSED_PENALTY_AMT > 0). One instrument per
  (assessment case number, violator id): doc_type OTHER, dated by the final order date,
  principal_amount = the unpaid penalty principal summed over the case's violations (the
  Mine Act and late-payment interest, which MSHA accrues on the account, stay in the raw
  record), the violator (operator or contractor, as named at assessment) the debtor and
  MSHA the creditor. Jurisdiction: the mine's county (from Mines.zip). The zip is streamed
  to data/work/ and read row by row, then deleted; with `limit` (fixtures) the member is
  read over HTTP Range requests only as far as the first `limit` unpaid cases.

Source: https://arlweb.msha.gov/OpenGovernmentData/OGIMSHA.asp (definition files linked
there). U.S. government data, free, no login; arlweb.msha.gov serves no robots.txt (404 on
2026-11-25: no restrictions). The files are rebuilt weekly.
"""

from __future__ import annotations

import csv
import io
import json
import re
import tempfile
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import IO, Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import (
    BulkClient,
    Holder,
    address,
    emit_business,
    jurisdiction,
    remote_zip,
    scrub_json,
    text,
)
from equity.adapters.rows import RecordContext, canonical_json
from equity.geo import county_by_fips
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PAGE = "https://arlweb.msha.gov/OpenGovernmentData/OGIMSHA.asp"
DATASETS = "https://arlweb.msha.gov/OpenGovernmentData/DataSets"
CHECKED_ON = "2026-11-25"
MSHA = "MINE SAFETY AND HEALTH ADMINISTRATION"
MINE_KEEP = ("MINE_ID", "CURRENT_MINE_NAME", "COAL_METAL_IND", "CURRENT_MINE_TYPE",
             "CURRENT_MINE_STATUS", "CURRENT_STATUS_DT", "CURRENT_CONTROLLER_ID",
             "CURRENT_CONTROLLER_NAME", "CURRENT_OPERATOR_ID", "CURRENT_OPERATOR_NAME", "STATE",
             "BOM_STATE_CD", "FIPS_CNTY_CD", "FIPS_CNTY_NM", "COMPANY_TYPE",
             "CURRENT_CONTROLLER_BEGIN_DT", "DISTRICT", "OFFICE_CD", "PRIMARY_SIC",
             "SECONDARY_SIC", "PRIMARY_CANVASS", "NO_EMPLOYEES", "LATITUDE", "LONGITUDE",
             "NEAREST_TOWN")  # fmt: skip
AOR_KEEP = ("MINE_ID", "MINE_NAME", "CONTACT_TITLE", "BUSINESS_NAME", "STREET", "PO_BOX", "CITY",
            "STATE_ABBR", "ZIP_CD", "COUNTRY", "PROVINCE", "POSTAL_CD", "MINE_STATUS",
            "MINE_STATUS_DT")  # fmt: skip
HIST_KEEP = ("MINE_ID", "CONTROLLER_ID", "CONTROLLER_NAME", "CONTROLLER_TYPE",
             "CONTROLLER_START_DT", "CONTROLLER_END_DT", "OPERATOR_ID", "OPERATOR_NAME",
             "OPERATOR_START_DT", "OPERATOR_END_DT")  # fmt: skip
VIOL_KEEP = ("EVENT_NBR", "VIOLATION_NO", "MINE_ID", "VIOLATOR_ID", "VIOLATOR_NAME",
             "VIOLATOR_TYPE_CD", "ASSESS_CASE_NO", "ASSESS_CASE_STATUS_CD",
             "ASSESS_CASE_STATUS_DT", "ISSUE_DT", "FINAL_ORDER_DT", "DELINQUENT_DT",
             "PROPOSED_PENALTY_AMT", "CURRENT_ASSESSMENT_AMT", "MINEACT_INTEREST_AMT",
             "EXLATE_INTEREST_AMT", "PAID_PROPOSED_PENALTY_AMT", "PAID_MINEACT_INTEREST_AMT",
             "PAID_EXLATE_INTEREST_AMT", "CITATION_TYPE_CD", "MINE_ACT_SECTION_CD")  # fmt: skip
MINE_NAMES = ("CURRENT_MINE_NAME", "MINE_NAME", "CURRENT_CONTROLLER_NAME", "CURRENT_OPERATOR_NAME",
              "BUSINESS_NAME", "CONTROLLER_NAME", "OPERATOR_NAME")  # fmt: skip
_MDY = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_STATE = re.compile(r"^[A-Z]{2}$")


def mdy(value: Any) -> date | None:
    m = _MDY.match(text(value) or "")
    if m is None:
        return None
    try:
        return date(int(m[3]), int(m[1]), int(m[2]))
    except ValueError:
        return None


def money(value: Any) -> Decimal:
    try:
        return Decimal(text(value) or "0")
    except InvalidOperation:
        return Decimal(0)


def pipe_rows(stream: IO[bytes], keep: tuple[str, ...]) -> Iterator[dict[str, str]]:
    """The `keep` columns of one MSHA pipe-delimited file, streamed (empty cells dropped)."""
    text_io = io.TextIOWrapper(stream, encoding="latin-1", newline="")
    for row in csv.DictReader(text_io, delimiter="|"):
        yield {k: v for k in keep if (v := text(row.get(k))) is not None}


def zip_rows(content: bytes, keep: tuple[str, ...]) -> Iterator[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        member = next(i for i in zf.infolist() if i.filename.lower().endswith(".txt"))
        with zf.open(member) as f:
            yield from pipe_rows(f, keep)


def mine_place(m: Mapping[str, Any] | None) -> str:
    """The mine's county FIPS, else its state FIPS, else US."""
    if not m:
        return "US"
    st = text(m.get("STATE"))
    cnty = text(m.get("FIPS_CNTY_CD"))
    if st and cnty and cnty.isdigit():
        try:
            return county_by_fips(st, cnty.zfill(3)).fips5
        except KeyError:
            pass
    return jurisdiction(st)


class _MSHA(Adapter):
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    title: ClassVar[str]

    def __init__(self, client: BulkClient | None = None) -> None:
        self.client = client or BulkClient(min_interval_s=2.0, timeout_s=1800.0)
        self._zips: dict[str, tuple[bytes, datetime]] = {}

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a federal registry of mines and their operators
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": PAGE,
            "terms_url": PAGE,
            "terms_summary": (
                f"MSHA Open Government Data ({self.title}), pipe-delimited zips rebuilt "
                "weekly; U.S. government data, free, no login. arlweb.msha.gov serves no "
                "robots.txt (404)."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def small_zip(self, name: str) -> tuple[bytes, datetime]:
        """A small data set zip, fetched once per adapter instance."""
        if name not in self._zips:
            url = f"{DATASETS}/{name}"
            resp = self.client.get(url)
            if resp.status != 200 or not resp.content.startswith(b"PK"):
                raise RuntimeError(f"{url}: HTTP {resp.status} ({resp.content_type}); not a zip")
            self._zips[name] = (resp.content, resp.retrieved_at)
        return self._zips[name]

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            resp = self.client.get(PAGE)
        except (OSError, RuntimeError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        page = resp.content.decode("latin-1")
        ok = resp.status == 200 and "Mines.zip" in page and "AssessedViolations.zip" in page
        return HealthReport(self.source_id, ok, now, f"HTTP {resp.status}")


class MSHAMines(_MSHA):
    source_id: ClassVar[str] = "us.dol.msha_mines"
    title: ClassVar[str] = "mines, addresses of record, controller and operator history"
    pii_fields: ClassVar[tuple[str, ...]] = (*MINE_NAMES, "STREET", "PO_BOX")

    def mines(self) -> list[dict[str, str]]:
        return list(zip_rows(self.small_zip("Mines.zip")[0], MINE_KEEP))

    def partitions(self) -> Iterator[dict[str, str]]:
        states = sorted({m["STATE"] for m in self.mines() if _STATE.match(m.get("STATE", ""))})
        for st in states:
            yield {"state": st}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: state (the mine's state, two letters); limit (fixtures: the first mines by
        mine id)."""
        p = request.params
        st = p["state"].upper()
        if not _STATE.match(st):
            raise ValueError(f"bad state {st!r}")
        at = self.small_zip("Mines.zip")[1]
        mines = sorted((m for m in self.mines() if m.get("STATE") == st),
                       key=lambda m: m.get("MINE_ID", ""))  # fmt: skip
        if "limit" in p:
            mines = mines[: int(p["limit"])]
        ids = {m.get("MINE_ID") for m in mines}
        aor = {r["MINE_ID"]: r for r in zip_rows(self.small_zip("AddressofRecord.zip")[0], AOR_KEEP)
               if r.get("MINE_ID") in ids}  # fmt: skip
        hist: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in zip_rows(self.small_zip("ControllerOperatorHistory.zip")[0], HIST_KEEP):
            if r.get("MINE_ID") in ids:
                hist[r["MINE_ID"]].append(r)
        body = {"state": st, "mines": [{**m, "address_of_record": aor.get(m["MINE_ID"]),
                                        "history": hist.get(m["MINE_ID"], [])}
                                       for m in mines if m.get("MINE_ID")]}  # fmt: skip
        return Fetched(self.source_id, f"{DATASETS}/Mines.zip#STATE={st}", at, 200,
                       canonical_json(body), "application/json")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, MINE_NAMES, ("STREET", "PO_BOX"))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for m in sorted(data.get("mines") or [], key=canonical_json):
            mid = text(m.get("MINE_ID"))
            if mid is None or mid in seen:
                continue
            seen.add(mid)
            aor = m.get("address_of_record") or {}
            name = text(m.get("CURRENT_MINE_NAME")) or text(aor.get("MINE_NAME"))
            if name is None:
                continue
            ctx = RecordContext(fetched, mine_place(m), mid, "mine", m)
            yield ctx.source_record()
            addr = None
            if (text(aor.get("COUNTRY")) or "USA").upper() in {"USA", "US", "UNITED STATES"}:
                addr = address(
                    text(aor.get("STREET")) or text(aor.get("PO_BOX")),
                    aor.get("CITY"),
                    aor.get("STATE_ABBR"),
                    aor.get("ZIP_CD"),
                )
            history = sorted(m.get("history") or [], key=canonical_json)
            holders = []
            if biz := text(aor.get("BUSINESS_NAME")):
                holders.append(Holder("other", "OPERATOR", biz, addr))
            starts: list[date] = []
            for h in history:
                for who, title, start, end, person in (
                    ("OPERATOR_NAME", "OPERATOR", "OPERATOR_START_DT", "OPERATOR_END_DT", False),
                    ("CONTROLLER_NAME", "CONTROLLER", "CONTROLLER_START_DT", "CONTROLLER_END_DT",
                     (h.get("CONTROLLER_TYPE") or "").upper() == "PERSON"),
                ):  # fmt: skip
                    if (n := text(h.get(who))) is None:
                        continue
                    if (s := mdy(h.get(start))) is not None and s <= observed:
                        starts.append(s)
                    e = mdy(h.get(end))
                    holders.append(
                        Holder(
                            "other",
                            title,
                            n,
                            person=person,
                            valid_to=e if e and e <= observed else None,
                        )
                    )
            for who, title in (("CURRENT_OPERATOR_NAME", "OPERATOR"),
                               ("CURRENT_CONTROLLER_NAME", "CONTROLLER")):  # fmt: skip
                if (n := text(m.get(who))) and not any(h.name == n for h in holders):
                    holders.append(Holder("other", title, n))
            status_on = mdy(m.get("CURRENT_STATUS_DT"))
            status_on = status_on if status_on is not None and status_on <= observed else None
            valid_from = min(starts) if starts else (status_on or observed)
            yield from emit_business(
                ctx, source_id=self.source_id, sos_id=f"MSHA:{mid}", name=name,
                valid_from=valid_from, status=text(m.get("CURRENT_MINE_STATUS")),
                status_date=status_on, principal=addr, holders=_ended_last(holders),
            )  # fmt: skip


def _ended_last(holders: list[Holder]) -> list[Holder]:
    """One holder per (title, name): the open period if any, else the latest end."""
    best: dict[tuple[str, str], Holder] = {}
    for h in holders:
        k = (h.title or "", clean(h.name))
        cur = best.get(k)
        if cur is None or (
            cur.valid_to is not None and (h.valid_to is None or h.valid_to > cur.valid_to)
        ):
            best[k] = Holder(
                h.role,
                h.title,
                h.name,
                h.address or (cur.address if cur else None),
                h.person or bool(cur and cur.person),
                h.parts,
                h.valid_to,
            )
    return list(best.values())


class MSHAAssessedPenalties(_MSHA):
    source_id: ClassVar[str] = "us.dol.msha_assessed_penalties"
    title: ClassVar[str] = "assessed violations: unpaid civil penalties past their delinquent date"
    pii_fields: ClassVar[tuple[str, ...]] = ("VIOLATOR_NAME",)
    cache_dir: ClassVar[Path] = Path("data") / "work" / "us_dol_msha_assessed_penalties"
    URL: ClassVar[str] = f"{DATASETS}/AssessedViolations.zip"

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {"file": "all"}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: file ('all', the only partition); limit (fixtures: the first unpaid cases,
        read over HTTP Range requests)."""
        p = request.params
        if p.get("file", "all") != "all":
            raise ValueError(f"bad file {p['file']!r}")
        limit = int(p["limit"]) if "limit" in p else None
        places = {m["MINE_ID"]: {k: m[k] for k in ("STATE", "FIPS_CNTY_CD") if k in m}
                  for m in zip_rows(self.small_zip("Mines.zip")[0], MINE_KEEP)
                  if m.get("MINE_ID")}  # fmt: skip
        at = datetime.now(UTC)
        if limit is not None:
            zf = remote_zip(self.client, self.URL)
            cases = self._cases(zf, at.date(), limit)
        else:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=self.cache_dir) as tmp:
                dest = Path(tmp) / "AssessedViolations.zip"
                resp = self.client.download(self.URL, dest)
                if resp.status != 200 or not zipfile.is_zipfile(dest):
                    raise RuntimeError(f"{self.URL}: HTTP {resp.status}; not a zip")
                at = resp.retrieved_at
                with zipfile.ZipFile(dest) as zf:
                    cases = self._cases(zf, at.date(), None)
        for c in cases:
            c["mine"] = places.get(c["violations"][0].get("MINE_ID", ""))
        body = {"url": self.URL, "cases": cases}
        return Fetched(self.source_id, self.URL, at, 200, canonical_json(body),
                       "application/json")  # fmt: skip

    @staticmethod
    def _cases(zf: zipfile.ZipFile, today: date, limit: int | None) -> list[dict[str, Any]]:
        """Violations past their delinquent date with penalty principal unpaid, grouped by
        (assessment case, violator)."""
        member = next(i for i in zf.infolist() if i.filename.lower().endswith(".txt"))
        cases: dict[tuple[str, str], list[dict[str, str]]] = {}
        with zf.open(member) as f:
            for r in pipe_rows(f, VIOL_KEEP):
                due = mdy(r.get("DELINQUENT_DT"))
                unpaid = money(r.get("CURRENT_ASSESSMENT_AMT")) - money(
                    r.get("PAID_PROPOSED_PENALTY_AMT")
                )
                if due is None or due > today or unpaid <= 0:
                    continue
                key = (r.get("ASSESS_CASE_NO", ""), r.get("VIOLATOR_ID", ""))
                if not all(key):
                    continue
                if key not in cases and limit is not None and len(cases) >= limit:
                    break
                cases.setdefault(key, []).append(r)
        return [{"assess_case_no": k[0], "violator_id": k[1], "violations": v}
                for k, v in cases.items()]  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, ("VIOLATOR_NAME",), ())

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        seen: set[str] = set()
        for c in sorted(data.get("cases") or [], key=canonical_json):
            viols = sorted(c.get("violations") or [], key=canonical_json)
            case, violator = text(c.get("assess_case_no")), text(c.get("violator_id"))
            name = next((n for v in viols if (n := text(v.get("VIOLATOR_NAME")))), None)
            if not (case and violator and name and viols):
                continue
            key = f"{case}|{violator}"
            if key in seen:
                continue
            seen.add(key)
            unpaid = sum((money(v.get("CURRENT_ASSESSMENT_AMT"))
                          - money(v.get("PAID_PROPOSED_PENALTY_AMT")) for v in viols),
                         Decimal(0))  # fmt: skip
            if unpaid <= 0:
                continue
            final = min((d for v in viols if (d := mdy(v.get("FINAL_ORDER_DT")))), default=None)
            due = min((d for v in viols if (d := mdy(v.get("DELINQUENT_DT")))), default=None)
            issued = min((d for v in viols if (d := mdy(v.get("ISSUE_DT")))), default=None)
            if final is None and due is None:
                continue
            ctx = RecordContext(fetched, mine_place(c.get("mine")), key, "msha_penalty", c)
            yield ctx.source_record()
            uid = stable_id(self.source_id, key)
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=case, book_type=None,
                book=None, page=None, doc_type_raw="MSHA civil penalty assessment, unpaid",
                doc_type="OTHER", recorded_on=final or due, recorded_seq=None,
                executed_on=issued, consideration=None, principal_amount=unpaid.quantize(
                    Decimal("0.01")), max_secured_amount=None, maturity_date=due,
                amount_source="index", legal_desc_raw=None,
            )  # fmt: skip
            for role, who in (("debtor", name), ("creditor", MSHA)):
                nc = classify(who)
                pid = stable_id(self.source_id, key, role, clean(who))
                yield ctx.fact("party", party_id=pid, raw_name=who, party_kind=nc.party_kind,
                               org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                               address_id=None)  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=pid, role=role,
                               seq=1)  # fmt: skip
