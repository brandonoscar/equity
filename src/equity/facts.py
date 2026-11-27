"""Fact sheets: everything the index holds that bears on one lead, as one JSON document, for a
scorer (a person, or Claude applying the owner's rubric) to read. Deterministic: it gathers
and labels facts, it does not weigh them. Every fact carries the ref it came from.

    uv run python -m equity.facts 123                 # lead_id from the leads table
    uv run python -m equity.facts --state OH --top 25  # the best-ranked leads, to files

A sheet has the lead row, identity grades for its debtor-owner pairs (grade_pair), the debts
with whether a release points at them, each owned parcel's value, equity, homestead, tax
delinquency, house-price estimate and deeds after the debt, the debtor's cases (judgment
terms, bankruptcy), the state's judgment-lien law (confirmed: config/sol.yaml; proposed and
unverified: config/sol_proposed.yaml, labelled so), the scoring factors named as in
config/scoring.yaml, and `gaps`: what is unknown, so no reader mistakes a gap for a zero.

Sheets name people: files go under data/derived/scores/facts/ (git-ignored).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from equity.config import _load
from equity.search import DEBT_TYPES, _in, _rows, grade_pair, show, show_parcel
from equity.search_index import DEFAULT_DB, connect

OUT = Path("data") / "derived" / "scores" / "facts"
MAX_PAIRS = 5  # debtor and owner refs graded per side
SHEET_VERSION = "1"


def _ref(ref: str) -> tuple[str, str]:
    src, _, pid = ref.partition(":")
    return src, pid


def _law(state: str, config_dir: Path | None = None) -> dict[str, Any]:
    confirmed = (_load("sol.yaml", config_dir).get("states") or {}).get(state) or {}
    try:
        proposed = (_load("sol_proposed.yaml", config_dir).get("states") or {}).get(state) or {}
    except FileNotFoundError:
        proposed = {}
    return {
        "confirmed": {k: v for k, v in confirmed.items() if v is not None},
        "proposed_unverified": proposed,
        "note": "confirmed values come only from config/sol.yaml (owner-filled); proposed "
                "values are research, not confirmed, and must be labelled as such",
    }  # fmt: skip


def lead_row(con: duckdb.DuckDBPyConnection, lead_id: int) -> dict[str, Any] | None:
    rows = _rows(con, "SELECT * FROM leads WHERE lead_id = ?", [lead_id])
    return rows[0] if rows else None


def fact_sheet(
    con: duckdb.DuckDBPyConnection,
    lead_id: int,
    config_dir: Path | None = None,
    as_of: date | None = None,
) -> dict[str, Any] | None:
    """The fact sheet for one lead (module doc), or None if there is no such lead. `as_of`
    (default today, UTC) is the date ages and years left are counted to."""
    as_of = as_of or datetime.now(UTC).date()
    lead = lead_row(con, lead_id)
    if lead is None:
        return None
    gaps: list[str] = []
    debtors = list(lead["debtor_refs"] or [])
    owners = list(lead["owner_refs"] or [])
    pairs = [
        {"debtor_ref": d, "owner_ref": o, **grade_pair(con, d, o)}
        for d in debtors[:MAX_PAIRS] for o in owners[:MAX_PAIRS]
    ]  # fmt: skip
    order = {"A": 0, "B": 1, "C": 2, "reject": 3}
    pairs.sort(key=lambda p: (order.get(p["grade"], 9), p["debtor_ref"], p["owner_ref"]))
    if len(debtors) > MAX_PAIRS or len(owners) > MAX_PAIRS:
        gaps.append(f"identity graded on the first {MAX_PAIRS} records a side of "
                    f"{len(debtors)} debtor and {len(owners)} owner records")  # fmt: skip

    ids = {_ref(r)[1] for r in debtors}
    debts = _rows(con, f"""
        SELECT ip.source_id || ':' || ip.party_id AS debtor_ref, ip.role, i.source_id,
               i.instrument_uid, i.doc_type, i.doc_type_raw, i.recorded_on, i.amount,
               EXISTS (SELECT 1 FROM instrument_refs r WHERE r.source_id = i.source_id
                       AND r.to_uid = i.instrument_uid
                       AND r.ref_type IN ('releases', 'satisfies_judgment')) AS released,
               (SELECT list(x.parcel_uid) FROM instrument_parcels x
                 WHERE x.source_id = i.source_id AND x.instrument_uid = i.instrument_uid)
                 AS recorded_against
        FROM instrument_parties ip JOIN instruments i USING (source_id, instrument_uid)
        WHERE ip.party_id IN {_in(ids)} AND i.doc_type IN {_in(DEBT_TYPES)}
        ORDER BY i.recorded_on, i.instrument_uid
    """, []) if ids else []  # noqa: S608  # fmt: skip
    debts = [d for d in debts if d["debtor_ref"] in set(debtors)]
    open_debts = [d for d in debts if not d["released"]]
    if any(d["amount"] is None for d in open_debts):
        gaps.append(f"{sum(d['amount'] is None for d in open_debts)} open debts have no "
                    "recorded amount")  # fmt: skip

    parcels = []
    first_debt = lead["first_debt_on"]
    for uid in list(lead["parcel_uids"] or [])[:20]:
        for rec in show_parcel(con, uid):
            deeds_after = [
                d for d in rec["documents"] if d["doc_type"] == "DEED" and first_debt
                and d["recorded_on"] and d["recorded_on"] > first_debt]  # fmt: skip
            eq = rec.get("equity")
            parcels.append({
                "parcel_uid": uid, "source_id": rec["source_id"],
                "situs": ", ".join(str(x) for x in (rec["situs_line1"], rec["situs_city"],
                                                     rec["situs_zip"]) if x),
                "tax_year": rec["tax_year"], "appraised_total": rec["appraised_total"],
                "assessed_value": rec["assessed_value"], "homestead": rec["homestead"],
                "equity": eq, "house_price_index": rec["house_price_index"],
                "assessment_ratio": rec["assessment_ratio"],
                "tax_delinquency": rec["tax_delinquency"], "value_parts": rec["value_parts"],
                "owner_types": rec["owner_types"],
                "deeds_after_first_debt": [
                    {"instrument_uid": d["instrument_uid"], "recorded_on": d["recorded_on"],
                     "parties": d["parties"]} for d in deeds_after],
                "open_liens_recorded_against": [
                    d["instrument_uid"] for d in rec["documents"]
                    if d["doc_type"] in DEBT_TYPES and not d["released"]],
            })  # fmt: skip
            if eq is None:
                gaps.append(f"{uid}: no recorder data in the index, senior mortgages unknown")
            elif eq.get("principal_unknown"):
                gaps.append(f"{uid}: an open mortgage has no recorded amount")
            if rec["homestead"] is None:
                gaps.append(f"{uid}: homestead status not in the source")

    cases = []
    for ref in debtors[:MAX_PAIRS]:
        e = show(con, ref)
        if e is not None:
            cases += [{"debtor_ref": ref, **c} for c in e.cases]
    state = str(lead["state"])
    law = _law(state, config_dir)
    if not law["confirmed"].get("judgment_enforceable_years"):
        gaps.append(f"{state}: judgment enforcement period not confirmed in config/sol.yaml")

    sol_years = law["confirmed"].get("judgment_enforceable_years")
    years_left = None
    if sol_years and first_debt:
        years_left = round(float(sol_years) - (as_of - first_debt).days / 365.25, 2)
    factors = {  # named as in config/scoring.yaml; None = unknown here, not zero
        "open_amount": sum(float(d["amount"]) for d in open_debts if d["amount"] is not None),
        "parcel_value": lead["parcel_value"],
        "parcels": lead["owned_parcels"],
        "court_judgment": int(any(d["doc_type"] in ("JUDGMENT_LIEN", "ABSTRACT_OF_JUDGMENT")
                                  for d in open_debts) or any(c.get("judgment_on")
                                                              for c in cases)),
        "charged_off_loan": None,
        "tax_debt": int(any(d["doc_type"].startswith("TAX_LIEN") for d in open_debts)),
        "bankruptcy_open": None if not cases and not lead["matcher_bankruptcy"] else int(any(
            c.get("bankruptcy_chapter") and not (c.get("discharge_on") or c.get("dismissed_on"))
            for c in cases)),
        "bankruptcy_discharged": int(any(c.get("discharge_on") for c in cases)),
        "transfers_after_debt": lead["deeds_after_debt"],
        "nominee_transfer": None,
        "sol_years_left": years_left,
    }  # fmt: skip
    sheet = {
        "sheet_version": SHEET_VERSION,
        "as_of": as_of.isoformat(),
        "lead_id": lead_id,
        "lead": lead,
        "identity": pairs,
        "debts": debts,
        "parcels": parcels,
        "cases": cases,
        "law": law,
        "factors": factors,
        "gaps": sorted(set(gaps)),
    }
    body = json.dumps(sheet, sort_keys=True, default=str)
    sheet["sheet_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    return sheet


def top_leads(con: duckdb.DuckDBPyConnection, state: str, n: int) -> list[int]:
    sql = (
        "SELECT lead_id FROM leads WHERE state = ? AND grade IN ('A', 'B') "
        "ORDER BY grade, net_equity_known DESC NULLS LAST, debt_amount DESC NULLS LAST "
        "LIMIT ?"
    )
    rows = con.execute(sql, [state.upper(), n]).fetchall()
    return [int(r[0]) for r in rows]


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("lead_id", nargs="*", type=int)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--state", help="with --top: the state's best-ranked A/B leads")
    ap.add_argument("--top", type=int, default=0)
    ap.add_argument("--out", type=Path, help="write one <lead_id>.json per sheet here")
    args = ap.parse_args(argv)
    con = connect(args.db, read_only=True)
    ids = list(args.lead_id)
    if args.state and args.top:
        ids += top_leads(con, args.state, args.top)
    if not ids:
        ap.error("give lead ids, or --state and --top")
    out = args.out or (OUT if len(ids) > 1 else None)
    for lid in ids:
        sheet = fact_sheet(con, lid)
        if sheet is None:
            print(f"no lead {lid}", file=sys.stderr)
            continue
        text = json.dumps(sheet, indent=1, default=str)
        if out is None:
            print(text)
        else:
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{lid}.json").write_text(text)
            print(out / f"{lid}.json")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
