"""Forensic asset tracing over the search index: the evidence a judgment-recovery investigator
assembles, gathered by fixed rules. It lists facts and named signs; it never concludes that a
transfer was fraudulent or that two records are one person. Those are a lawyer's and a
court's calls, made on the documents.

    uv run python -m equity.forensic --stack <parcel_uid> [--lien <instrument_uid>]
    uv run python -m equity.forensic --badges <source_id:party_id>
    uv run python -m equity.forensic --ring <source_id:party_id>
    uv run python -m equity.forensic --timeline <source_id:party_id>
    uv run python -m equity.forensic --household <source_id:party_id>
    uv run python -m equity.forensic --portfolios OH [--min-leads 3]

stack       every encumbrance recorded against a parcel by recording date, released or open,
            and for a given lien: what is senior to it (recorded earlier), what is junior,
            and the equity behind it net of only the senior debt
badges      deeds out by the debtor's name in the state, from 180 days before the first
            debt on, each with the UVTA-style badges the records show (badges below)
ring        businesses the debtor's name holds a role in, their parcels, whether they were
            formed after the debt, and deeds from the debtor into them
timeline    one dated list of the debtor's documents, cases, judgments, bankruptcy events,
            business formations and deeds on parcels the name owns
household   other owners at the debtor's mailing address, and the same name owning in other
            states with the same mailing ZIP: labelled leads, not identity
portfolios  creditors holding open judgments against graded (A/B) leads with equity: who
            holds the paper worth buying

Badges on a deed (a sign is a reason to look, not a finding):
  same_name_grantee   a grantee has the debtor's exact name_key (to a trust, a new form)
  shares_name_word    a grantee person shares a 3+ letter name word with the debtor (a
                      relative, maybe; common surnames make this weak)
  grantee_org         a grantee is an organization
  grantee_run_by_debtor  a grantee organization's registry lists a role holder with the
                      debtor's name_key (member, manager, officer, agent)
  grantee_at_debtor_address  a grantee's address is the debtor's address
  no_consideration    no consideration recorded
  nominal             consideration at or below rules.yaml nominal_consideration_max (only
                      when Brandon has set it; otherwise this badge is never given)
  quitclaim           the raw document type reads as a quitclaim
  debtor_still_listed the debtor's name is still a listed owner of the parcel in a snapshot
                      observed after the deed (possession or tax mailing kept)
  shortly_before_debt recorded within 180 days before the first debt
  within_year_of_debt recorded within 365 days after the first debt
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb

from equity.config import _load
from equity.search import DEBT_TYPES, _in, _rows
from equity.search_index import DEFAULT_DB, connect

ENCUMBRANCES = ("MORTGAGE", "DEED_OF_TRUST", *DEBT_TYPES)
MORTGAGES = ("MORTGAGE", "DEED_OF_TRUST")
# Senior whatever their recording date (property and state tax liens, by statute). A federal
# tax lien ranks by its filing date against an earlier judgment lien (26 U.S.C. 6323(a)).
TAX_LIENS = ("TAX_LIEN_STATE",)
QUITCLAIM_WORDS = ("QUIT", "QCD", "Q/C", "Q C D")
BEFORE_DAYS = 180
AFTER_DAYS = 365


def nominal_max(config_dir: Path | None = None) -> float | None:
    """rules.yaml transfer_flags.nominal_consideration_max (Brandon's), or None if unset."""
    value = (_load("rules.yaml", config_dir).get("transfer_flags") or {}).get(
        "nominal_consideration_max")  # fmt: skip
    return None if value is None else float(value)


def _split(ref: str) -> tuple[str, str]:
    src, _, pid = ref.partition(":")
    return src, pid


def _party(con: duckdb.DuckDBPyConnection, ref: str) -> dict[str, Any] | None:
    src, pid = _split(ref)
    rows = _rows(con, """
        SELECT n.source_id, n.party_id, n.raw_name, n.name_key, n.party_kind, n.address_id,
               s.state, a.line1, a.city, a.zip5, street_norm(a.line1) AS street
        FROM names n JOIN sources s USING (source_id)
        LEFT JOIN addresses a ON a.address_id = n.address_id
        WHERE n.source_id = ? AND n.party_id = ?""", [src, pid])  # fmt: skip
    return rows[0] if rows else None


def _same_name(con: duckdb.DuckDBPyConnection, key: str, state: str) -> list[tuple[str, str]]:
    """Every record with this exact name_key in the state (source_id, party_id)."""
    rows = con.execute("""
        SELECT n.source_id, n.party_id FROM names n JOIN sources s USING (source_id)
        WHERE n.name_key = ? AND s.state = ?""", [key, state]).fetchall()  # fmt: skip
    return [(str(a), str(b)) for a, b in rows]


def _first_debt(con: duckdb.DuckDBPyConnection, records: list[tuple[str, str]]) -> date | None:
    ids = {p for _s, p in records}
    if not ids:
        return None
    rows = con.execute(f"""
        SELECT ip.source_id, ip.party_id, min(i.recorded_on)
        FROM instrument_parties ip JOIN instruments i USING (source_id, instrument_uid)
        WHERE ip.party_id IN {_in(ids)} AND i.doc_type IN {_in(DEBT_TYPES)}
          AND ip.role IN ('debtor', 'borrower', 'grantor')
        GROUP BY 1, 2""").fetchall()  # noqa: S608  # fmt: skip
    mine = set(records)
    dates = [d for s, p, d in rows if (str(s), str(p)) in mine and d is not None]
    return min(dates) if dates else None


def org_records(
    con: duckdb.DuckDBPyConnection, org_name: str, state: str
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Party records and registered businesses in the state whose name is this organization
    by org_key (punctuation and legal form ignored): ([(source_id, party_id)],
    [(source_id, sos_id)]). Candidates come from name_words (every org_key word present)."""
    row = con.execute("SELECT org_key(?)", [org_name]).fetchone()
    target = str(row[0]) if row and row[0] else ""
    words = [w for w in target.split(" ") if len(w) >= 2]
    if not words:
        return [], []
    keys = [str(r[0]) for r in con.execute(f"""
        SELECT name_key FROM name_words WHERE word IN {_in(words)}
        GROUP BY name_key HAVING count(DISTINCT word) = {len(words)}""").fetchall()]  # noqa: S608  # fmt: skip
    if not keys:
        return [], []
    parties = con.execute(f"""
        SELECT n.source_id, n.party_id FROM names n JOIN sources s USING (source_id)
        WHERE n.name_key IN {_in(keys)} AND s.state = ? AND org_key(n.raw_name) = ?
    """, [state, target]).fetchall()  # noqa: S608  # fmt: skip
    firms = con.execute(f"""
        SELECT b.source_id, b.sos_id FROM businesses b JOIN sources s USING (source_id)
        WHERE b.name_key IN {_in(keys)} AND s.state = ? AND org_key(b.name) = ?
    """, [state, target]).fetchall()  # noqa: S608  # fmt: skip
    return ([(str(a), str(b)) for a, b in parties], [(str(a), str(b)) for a, b in firms])


# -- (1) lien priority stack ------------------------------------------------------------------


def priority_stack(
    con: duckdb.DuckDBPyConnection, parcel: str, lien: str | None = None
) -> dict[str, Any]:
    """Every encumbrance recorded against a parcel, oldest first, with whether a recorded
    release points at it; with `lien` (an instrument_uid on the parcel), its position."""
    docs = _rows(con, f"""
        SELECT i.source_id, i.instrument_uid, i.doc_type, i.doc_type_raw, i.recorded_on,
               i.amount,
               EXISTS (SELECT 1 FROM instrument_refs r WHERE r.source_id = i.source_id
                       AND r.to_uid = i.instrument_uid
                       AND r.ref_type IN ('releases', 'satisfies_judgment')) AS released,
               (SELECT list(n.raw_name || ' (' || ip.role || ')' ORDER BY ip.role, n.raw_name)
                  FROM instrument_parties ip JOIN names n USING (source_id, party_id)
                 WHERE ip.source_id = i.source_id AND ip.instrument_uid = i.instrument_uid)
                 AS parties
        FROM instrument_parcels x JOIN instruments i USING (source_id, instrument_uid)
        WHERE x.parcel_uid = ? AND i.doc_type IN {_in(ENCUMBRANCES)}
        ORDER BY i.recorded_on NULLS LAST, i.instrument_uid
    """, [parcel])  # noqa: S608  # fmt: skip
    value = con.execute("""
        SELECT max(coalesce(appraised_total, assessed_value)), max(tax_year)
        FROM parcel_values WHERE parcel_uid = ?""", [parcel]).fetchone()  # fmt: skip
    out: dict[str, Any] = {
        "parcel_uid": parcel, "value": value[0] if value else None,
        "value_tax_year": value[1] if value else None, "encumbrances": docs,
        "note": "priority here is recording order; state and property tax liens count as "
                "senior whatever their date, federal tax liens by their filing date (26 U.S.C. "
                "6323(a)), same-day recordings as senior (their order is unknown), and a "
                "purchase-money mortgage can outrank an earlier judgment lien: confirm the "
                "order with a title search",
    }  # fmt: skip
    if lien is None:
        return out
    mine = next((d for d in docs if d["instrument_uid"] == lien), None)
    if mine is None:
        out["position"] = {"error": f"{lien} is not recorded against {parcel}"}
        return out
    when = mine["recorded_on"]
    open_docs = [d for d in docs if not d["released"] and d["instrument_uid"] != lien]
    # Same-day recordings: their order is unknown, so they count as senior (conservative).
    senior = [d for d in open_docs if d["doc_type"] in TAX_LIENS
              or (when and d["recorded_on"] and d["recorded_on"] <= when)]  # fmt: skip
    same_day = [d["instrument_uid"] for d in senior if d["recorded_on"] == when]
    junior = [d for d in open_docs if d not in senior]
    senior_known = sum(float(d["amount"]) for d in senior if d["amount"] is not None)
    unknown = [d["instrument_uid"] for d in senior if d["amount"] is None]
    equity = None
    if out["value"] is not None and not unknown:
        equity = round(float(out["value"]) - senior_known, 2)
    out["position"] = {
        "lien": lien, "recorded_on": when, "rank": 1 + len(senior),
        "senior": [d["instrument_uid"] for d in senior],
        "junior": [d["instrument_uid"] for d in junior],
        "senior_amount_known": senior_known, "senior_amount_unknown": unknown,
        "same_day_as_lien": same_day,
        "equity_behind_lien": equity,
        "junior_mortgages_after_lien": [d["instrument_uid"] for d in junior
                                        if d["doc_type"] in MORTGAGES],
    }  # fmt: skip
    return out


# -- (2) badges on deeds out -------------------------------------------------------------------


def transfer_badges(
    con: duckdb.DuckDBPyConnection, ref: str, config_dir: Path | None = None
) -> dict[str, Any]:
    """Deeds out by the debtor's name in the state from BEFORE_DAYS before the first debt, each
    with the badges the records show (module doc)."""
    p = _party(con, ref)
    if p is None:
        return {"error": f"no party {ref}"}
    records = _same_name(con, p["name_key"], p["state"])
    first = _first_debt(con, records)
    if first is None:
        return {"debtor": ref, "first_debt_on": None, "deeds": [],
                "note": "no debt document under this name in the state"}  # fmt: skip
    since = first - timedelta(days=BEFORE_DAYS)
    ids = {pid for _s, pid in records}
    mine = set(records)
    out_deeds = [r for r in _rows(con, f"""
        SELECT ip.source_id, ip.party_id, i.instrument_uid, i.doc_type_raw, i.recorded_on,
               i.consideration
        FROM instrument_parties ip JOIN instruments i USING (source_id, instrument_uid)
        WHERE ip.party_id IN {_in(ids)} AND ip.role = 'grantor' AND i.doc_type = 'DEED'
          AND i.recorded_on >= ?
        ORDER BY i.recorded_on""", [since]) if (r["source_id"], r["party_id"]) in mine]  # noqa: S608  # fmt: skip
    nominal = nominal_max(config_dir)
    words = {w for w in p["name_key"].split(" ") if len(w) >= 3}
    deeds = []
    for d in out_deeds:
        grantees = _rows(con, """
            SELECT n.raw_name, n.name_key, n.party_kind, n.address_id, a.zip5,
                   street_norm(a.line1) AS street
            FROM instrument_parties ip JOIN names n USING (source_id, party_id)
            LEFT JOIN addresses a ON a.address_id = n.address_id
            WHERE ip.source_id = ? AND ip.instrument_uid = ? AND ip.role = 'grantee'
        """, [d["source_id"], d["instrument_uid"]])  # fmt: skip
        parcels = [str(r[0]) for r in con.execute(
            "SELECT parcel_uid FROM instrument_parcels WHERE source_id = ? AND instrument_uid = ?",
            [d["source_id"], d["instrument_uid"]]).fetchall()]  # fmt: skip
        badges: list[str] = []
        evidence: list[str] = []
        for g in grantees:
            if g["name_key"] == p["name_key"]:
                badges.append("same_name_grantee")
            elif g["party_kind"] != "org" and words & set(str(g["name_key"]).split(" ")):
                badges.append("shares_name_word")
                shared = sorted(words & set(str(g["name_key"]).split(" ")))
                evidence.append(f"grantee {g['raw_name']} shares {shared}")
            if g["party_kind"] == "org":
                badges.append("grantee_org")
                _parties, firms = org_records(con, str(g["raw_name"]), p["state"])
                run = con.execute(f"""
                    SELECT b.name, r.role FROM businesses b
                    JOIN business_roles r USING (source_id, sos_id)
                    JOIN names n ON n.source_id = r.source_id AND n.party_id = r.party_id
                    WHERE b.sos_id IN {_in(f for _s, f in firms)} AND n.name_key = ?
                    LIMIT 3""", [p["name_key"]]).fetchall() if firms else []  # noqa: S608  # fmt: skip
                if run:
                    badges.append("grantee_run_by_debtor")
                    evidence += [f"{n} lists {p['raw_name']} as {r}" for n, r in run]
            same_addr = (g["address_id"] and g["address_id"] == p["address_id"]) or (
                g["street"] and g["street"] == p["street"] and g["zip5"] == p["zip5"]
            )
            if same_addr:
                badges.append("grantee_at_debtor_address")
        if d["consideration"] is None:
            badges.append("no_consideration")
        elif nominal is not None and float(d["consideration"]) <= nominal:
            badges.append("nominal")
        raw = str(d["doc_type_raw"] or "").upper()
        if any(w in raw for w in QUITCLAIM_WORDS):
            badges.append("quitclaim")
        if parcels:
            still = con.execute(f"""
                SELECT count(*) FROM owners o JOIN names n USING (source_id, party_id)
                WHERE o.parcel_uid IN {_in(parcels)} AND n.name_key = ? AND o.observed_on > ?
            """, [p["name_key"], d["recorded_on"]]).fetchone()  # noqa: S608  # fmt: skip
            if still and still[0]:
                badges.append("debtor_still_listed")
        days = (d["recorded_on"] - first).days
        if days < 0:
            badges.append("shortly_before_debt")
        elif days <= AFTER_DAYS:
            badges.append("within_year_of_debt")
        deeds.append({
            "deed": f"{d['source_id']}:{d['instrument_uid']}", "recorded_on": d["recorded_on"],
            "days_after_first_debt": days, "doc_type_raw": d["doc_type_raw"],
            "consideration": d["consideration"], "parcels": parcels,
            "grantees": [g["raw_name"] for g in grantees],
            "badges": sorted(set(badges)), "evidence": evidence,
        })  # fmt: skip
    return {
        "debtor": ref, "name_key": p["name_key"], "state": p["state"], "first_debt_on": first,
        "nominal_threshold": nominal,
        "note": "badges are reasons to review a transfer (UVTA badges of fraud), not findings; "
                "deeds are matched by exact name in the state, so a namesake's deed can appear"
                + ("" if nominal is not None else "; rules.yaml nominal_consideration_max is "
                   "unset, so no deed is marked nominal"),
        "deeds": deeds,
    }  # fmt: skip


# -- (3) entity and nominee rings ------------------------------------------------------------


def entity_ring(con: duckdb.DuckDBPyConnection, ref: str) -> dict[str, Any]:
    """Businesses the debtor's name holds a role in (in the state), with their parcels,
    formation date against the first debt, and deeds from the debtor's name into them."""
    p = _party(con, ref)
    if p is None:
        return {"error": f"no party {ref}"}
    first = _first_debt(con, _same_name(con, p["name_key"], p["state"]))
    firms = _rows(con, """
        SELECT DISTINCT b.source_id, b.sos_id, b.name, b.name_key, b.org_form, b.status,
               b.formed_on, r.role, r.title
        FROM names n JOIN sources s USING (source_id)
        JOIN business_roles r ON r.source_id = n.source_id AND r.party_id = n.party_id
        JOIN businesses b ON b.source_id = r.source_id AND b.sos_id = r.sos_id
        WHERE n.name_key = ? AND s.state = ?
        ORDER BY b.formed_on NULLS LAST, b.name""", [p["name_key"], p["state"]])  # fmt: skip
    ring = []
    for f in firms:
        records, _firms = org_records(con, str(f["name"]), p["state"])
        ids, mine = {pid for _s, pid in records}, set(records)
        owned_sql = f"""
            SELECT DISTINCT o.source_id, o.party_id, o.parcel_uid,
                   o.source_id || ':' || o.party_id AS owner_ref,
                   v.appraised_total, v.assessed_value, v.tax_year
            FROM owners o
            LEFT JOIN parcel_values v ON v.source_id = o.source_id AND v.parcel_uid = o.parcel_uid
            WHERE o.party_id IN {_in(ids)}"""  # noqa: S608
        parcels = [r for r in _rows(con, owned_sql, [])
                   if (r["source_id"], r["party_id"]) in mine] if ids else []  # fmt: skip
        for r in parcels:
            del r["source_id"], r["party_id"]
        into_sql = f"""
            SELECT DISTINCT ge.source_id AS g_src, ge.party_id AS g_pid,
                   i.source_id || ':' || i.instrument_uid AS deed, i.recorded_on, i.consideration
            FROM instrument_parties ge
            JOIN instruments i
              ON i.source_id = ge.source_id AND i.instrument_uid = ge.instrument_uid
            JOIN instrument_parties gr ON gr.source_id = ge.source_id
                 AND gr.instrument_uid = ge.instrument_uid AND gr.role = 'grantor'
            JOIN names gn ON gn.source_id = gr.source_id AND gn.party_id = gr.party_id
            WHERE ge.role = 'grantee' AND ge.party_id IN {_in(ids)} AND gn.name_key = ?
              AND i.doc_type = 'DEED'"""  # noqa: S608
        into = [r for r in _rows(con, into_sql, [p["name_key"]])
                if (r["g_src"], r["g_pid"]) in mine] if ids else []  # fmt: skip
        for r in into:
            del r["g_src"], r["g_pid"]
        at_home = con.execute("""
            SELECT a.line1, a.zip5 FROM business_addresses ba
            JOIN addresses a ON a.address_id IN (ba.principal_address_id, ba.mailing_address_id)
            WHERE ba.source_id = ? AND ba.sos_id = ?
              AND (a.address_id = ? OR (a.zip5 = ? AND street_norm(a.line1) = ?))
            LIMIT 1""", [f["source_id"], f["sos_id"], p["address_id"], p["zip5"],
                         p["street"]]).fetchone()  # fmt: skip
        ring.append({
            "business": f"{f['source_id']}:business:{f['sos_id']}", "name": f["name"],
            "org_form": f["org_form"], "status": f["status"], "formed_on": f["formed_on"],
            "debtor_role": f["role"], "title": f["title"],
            "formed_after_first_debt": bool(first and f["formed_on"] and f["formed_on"] > first),
            "registered_at_debtor_address": at_home is not None,
            "parcels": parcels, "deeds_from_debtor": into,
        })  # fmt: skip
    return {"debtor": ref, "name_key": p["name_key"], "state": p["state"],
            "first_debt_on": first, "businesses": ring,
            "note": "roles are matched on the exact name in the state's registry: a namesake "
                    "can appear"}  # fmt: skip


# -- (5) timeline ------------------------------------------------------------------------------


def timeline(con: duckdb.DuckDBPyConnection, ref: str) -> dict[str, Any]:
    """One dated list for the debtor's name in the state: documents (with role), cases,
    judgments, bankruptcy events, business formations, and deeds on parcels it owns."""
    p = _party(con, ref)
    if p is None:
        return {"error": f"no party {ref}"}
    records = _same_name(con, p["name_key"], p["state"])
    ids, mine = {pid for _s, pid in records}, set(records)
    events: list[dict[str, Any]] = []
    for r in _rows(con, f"""
        SELECT ip.source_id, ip.party_id, ip.role, i.instrument_uid, i.doc_type, i.recorded_on,
               i.amount, i.consideration
        FROM instrument_parties ip JOIN instruments i USING (source_id, instrument_uid)
        WHERE ip.party_id IN {_in(ids)}""", []) if ids else []:  # noqa: S608  # fmt: skip
        if (r["source_id"], r["party_id"]) in mine:
            events.append({"on": r["recorded_on"], "kind": r["doc_type"], "role": r["role"],
                           "ref": f"{r['source_id']}:{r['instrument_uid']}",
                           "amount": r["amount"] or r["consideration"],
                           "record": f"{r['source_id']}:{r['party_id']}"})  # fmt: skip
    for r in _rows(con, f"""
        SELECT cp.source_id, cp.party_id, cp.role, c.case_uid, c.case_number, c.filed_on,
               c.closed_on, j.entered_on, j.principal, b.chapter, b.petition_on, b.discharge_on,
               b.dismissed_on
        FROM case_parties cp JOIN cases c USING (source_id, case_uid)
        LEFT JOIN judgments j USING (source_id, case_uid)
        LEFT JOIN bankruptcies b USING (source_id, case_uid)
        WHERE cp.party_id IN {_in(ids)}""", []) if ids else []:  # noqa: S608  # fmt: skip
        if (r["source_id"], r["party_id"]) not in mine:
            continue
        case = f"{r['source_id']}:{r['case_uid']}"
        events.append({"on": r["filed_on"], "kind": "CASE_FILED", "role": r["role"],
                       "ref": case, "detail": r["case_number"]})  # fmt: skip
        for when, kind in ((r["entered_on"], "JUDGMENT_ENTERED"), (r["closed_on"], "CASE_CLOSED"),
                           (r["discharge_on"], "BANKRUPTCY_DISCHARGE"),
                           (r["dismissed_on"], "BANKRUPTCY_DISMISSED")):  # fmt: skip
            if when:
                amount = r["principal"] if kind == "JUDGMENT_ENTERED" else None
                events.append({"on": when, "kind": kind, "ref": case, "amount": amount})
        if r["chapter"]:
            events.append({"on": r["petition_on"], "kind": f"BANKRUPTCY_CH{r['chapter']}",
                           "ref": case})  # fmt: skip
    for f in entity_ring(con, ref)["businesses"]:
        events.append({"on": f["formed_on"], "kind": "BUSINESS_FORMED", "ref": f["business"],
                       "detail": f"{f['name']} ({f['debtor_role']})"})  # fmt: skip
    sql = f"SELECT DISTINCT parcel_uid FROM owners WHERE party_id IN {_in(ids)}"  # noqa: S608
    owned = [str(r[0]) for r in con.execute(sql).fetchall()] if ids else []
    seen = {e["ref"] for e in events}
    for r in _rows(con, f"""
        SELECT i.source_id, i.instrument_uid, i.doc_type, i.recorded_on, i.amount,
               i.consideration, x.parcel_uid
        FROM instrument_parcels x JOIN instruments i USING (source_id, instrument_uid)
        WHERE x.parcel_uid IN {_in(owned)} AND i.doc_type IN ('DEED', 'MORTGAGE',
              'DEED_OF_TRUST', 'RELEASE')""", []) if owned else []:  # noqa: S608  # fmt: skip
        key = f"{r['source_id']}:{r['instrument_uid']}"
        if key not in seen:
            events.append({"on": r["recorded_on"], "kind": f"{r['doc_type']}_ON_OWNED_PARCEL",
                           "ref": key, "parcel_uid": r["parcel_uid"],
                           "amount": r["amount"] or r["consideration"]})  # fmt: skip
    events.sort(key=lambda e: (e["on"] is None, e["on"] or date.min, e["kind"], e["ref"]))
    return {"debtor": ref, "name": p["raw_name"], "state": p["state"],
            "records_under_name": len(records), "events": events,
            "note": "events are gathered by exact name in the state: a namesake's records can "
                    "appear; check each ref"}  # fmt: skip


# -- (6) household and cross-state -------------------------------------------------------------


def household(con: duckdb.DuckDBPyConnection, ref: str, limit: int = 100) -> dict[str, Any]:
    """Leads around the debtor's address: other owner records mailed at it, parcels whose
    property address it is, and the same name owning in other states with the same mailing
    ZIP. Every row is a lead to check, never an identity."""
    p = _party(con, ref)
    if p is None:
        return {"error": f"no party {ref}"}
    out: dict[str, Any] = {"debtor": ref, "address": " ".join(
        str(x) for x in (p["line1"], p["city"], p["zip5"]) if x), "leads": []}  # fmt: skip
    if p["street"] and p["zip5"]:
        out["leads"] += [dict(r, link="owner_mailed_at_debtor_address") for r in _rows(con, f"""
            SELECT DISTINCT n.source_id || ':' || n.party_id AS ref, n.raw_name, o.parcel_uid
            FROM addresses a JOIN names n ON n.address_id = a.address_id
            JOIN owners o ON o.source_id = n.source_id AND o.party_id = n.party_id
            WHERE a.zip5 = ? AND street_norm(a.line1) = ? AND n.name_key <> ?
            LIMIT {int(limit)}""", [p["zip5"], p["street"], p["name_key"]])]  # noqa: S608  # fmt: skip
        out["leads"] += [dict(r, link="parcel_at_debtor_address") for r in _rows(con, f"""
            SELECT DISTINCT p.parcel_uid, p.source_id, n.raw_name AS owner
            FROM addresses a JOIN parcels p ON p.situs_address_id = a.address_id
            LEFT JOIN owners o ON o.source_id = p.source_id AND o.parcel_uid = p.parcel_uid
            LEFT JOIN names n ON n.source_id = o.source_id AND n.party_id = o.party_id
            WHERE a.zip5 = ? AND street_norm(a.line1) = ?
            LIMIT {int(limit)}""", [p["zip5"], p["street"]])]  # noqa: S608  # fmt: skip
    if p["zip5"]:
        out["leads"] += [dict(r, link="same_name_other_state_same_mailing_zip") for r in _rows(
            con, f"""
            SELECT DISTINCT n.source_id || ':' || n.party_id AS ref, n.raw_name, s.state,
                   o.parcel_uid
            FROM names n JOIN sources s USING (source_id)
            JOIN owners o ON o.source_id = n.source_id AND o.party_id = n.party_id
            JOIN addresses a ON a.address_id = n.address_id
            WHERE n.name_key = ? AND s.state <> ? AND a.zip5 = ?
            LIMIT {int(limit)}""", [p["name_key"], p["state"], p["zip5"]])]  # noqa: S608  # fmt: skip
    out["note"] = (
        "leads only: a shared address can be a relative, a tenant, a landlord or a "
        "mail drop; a same name elsewhere needs the matcher's evidence"
    )
    return out


# -- (4) creditor portfolios -------------------------------------------------------------------


def creditor_portfolios(
    con: duckdb.DuckDBPyConnection, state: str, min_leads: int = 3, limit: int = 100
) -> list[dict[str, Any]]:
    """Creditors on open judgment documents against A/B-graded leads in the state, with how
    many leads, the debt they hold, and the leads' known net equity: who to ask about buying
    the paper. Government creditors are kept and marked (name_flag)."""
    return _rows(con, f"""
        WITH lead_debtors AS (
            SELECT l.lead_id, l.grade, l.net_equity_known, l.parcel_value,
                   split_part(r, ':', 1) AS src, r[length(split_part(r, ':', 1)) + 2:] AS pid
            FROM leads l, unnest(l.debtor_refs) t(r)
            WHERE l.state = ? AND l.grade IN ('A', 'B')
        ), debts AS (
            SELECT DISTINCT d.lead_id, d.grade, d.net_equity_known, d.parcel_value,
                   i.source_id, i.instrument_uid, i.amount
            FROM lead_debtors d
            JOIN instrument_parties ip ON ip.source_id = d.src AND ip.party_id = d.pid
            JOIN instruments i
              ON i.source_id = ip.source_id AND i.instrument_uid = ip.instrument_uid
            WHERE i.doc_type IN ('JUDGMENT_LIEN', 'ABSTRACT_OF_JUDGMENT', 'EXECUTION')
              AND NOT EXISTS (SELECT 1 FROM instrument_refs r WHERE r.source_id = i.source_id
                              AND r.to_uid = i.instrument_uid
                              AND r.ref_type IN ('releases', 'satisfies_judgment'))
        ), creditors AS (
            SELECT d.*, n.name_key AS creditor_key, n.raw_name AS creditor, n.name_flag
            FROM debts d
            JOIN instrument_parties c ON c.source_id = d.source_id
                 AND c.instrument_uid = d.instrument_uid
                 AND c.role IN ('creditor', 'plaintiff', 'grantee', 'lienholder')
            JOIN names n ON n.source_id = c.source_id AND n.party_id = c.party_id
        )
        SELECT creditor_key, any_value(creditor) AS creditor, any_value(name_flag) AS name_flag,
               count(DISTINCT lead_id) AS leads,
               count(DISTINCT lead_id) FILTER (WHERE grade = 'A') AS grade_a_leads,
               count(DISTINCT instrument_uid) AS judgments, sum(amount) AS judgment_amount,
               sum(DISTINCT net_equity_known) AS leads_net_equity_known,
               list(DISTINCT lead_id ORDER BY lead_id)[1:50] AS lead_ids
        FROM creditors GROUP BY creditor_key
        HAVING count(DISTINCT lead_id) >= ?
        ORDER BY grade_a_leads DESC, leads DESC, judgment_amount DESC NULLS LAST
        LIMIT {int(limit)}
    """, [state.upper(), min_leads])  # noqa: S608  # fmt: skip


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--stack", metavar="PARCEL_UID")
    g.add_argument("--badges", metavar="REF")
    g.add_argument("--ring", metavar="REF")
    g.add_argument("--timeline", metavar="REF")
    g.add_argument("--household", metavar="REF")
    g.add_argument("--portfolios", metavar="STATE")
    ap.add_argument("--lien", help="with --stack: the lien's instrument_uid")
    ap.add_argument("--min-leads", type=int, default=3)
    args = ap.parse_args(argv)
    con = connect(args.db, read_only=True)
    out: Any
    if args.stack:
        out = priority_stack(con, args.stack, args.lien)
    elif args.badges:
        out = transfer_badges(con, args.badges)
    elif args.ring:
        out = entity_ring(con, args.ring)
    elif args.timeline:
        out = timeline(con, args.timeline)
    elif args.household:
        out = household(con, args.household)
    else:
        out = creditor_portfolios(con, args.portfolios, args.min_leads)
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
