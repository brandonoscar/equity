"""Deterministic debtor -> property-owner matching over the lake (no fuzzy scores, no AI).

    uv run python -m equity.matching.resolve --state NY

Debtors are the debtor parties of lien and judgment instruments (warrants, docketed
judgments, lien filings). Owners are the owner parties of parcel snapshots. Both sides get the
same keys, computed in SQL so every match can be re-derived:

  name_key   the set of name words (upper case, letters and digits only, suffixes and
             filler words dropped, sorted): "SMITH JOHN A" and "JOHN A SMITH" -> "A JOHN SMITH".
             A person key needs at least two words; a last name alone never matches.
             A different middle name or initial gives a different key, so it never matches.
  suffix_key generational suffixes (JR, SR, II, III, ...). name_key drops them, so a person
             match is refused when both names carry a suffix and the suffixes differ
             (father and son at one address).
             "Person" rules cover every name not classified as an org at load (most
             loaders leave people as party_kind 'unknown').
  org_name   the organization name as normalized at load (equity.matching.orgs).
  addr_key   street line + ZIP 5 of a normalized address. The street line is compared with
             suffix and direction words spelled one way (USPS: STREET=ST, NORTH=N, ...) and
             punctuation dropped (review.street_norm; approved by the project owner
             2026-11-22), so "12 Main Street" and "12 MAIN ST." are one address.
  town_key   street line + city, for states whose parcel data carries no owner ZIP (CT).

Rules, strongest first (a debtor-owner pair keeps its strongest rule):
  person_name_address   same person name_key, and the debtor's address equals the owner's
                        mailing address or the parcel's property address       -> auto
  org_name_address      same org_name and address                              -> auto
  org_name_zip          same org_name and ZIP                                  -> auto
  person_name_zip       same person name_key and ZIP                           -> review
  person_name_initial_address  same address, and the names are the same except that one side
                        has one extra single-letter middle initial ("JOHN SMITH" / "SMITH JOHN
                        A"); a parent and child can share both, so -> review (approved by the
                        project owner 2026-11-22)
With parcel_on_lien (liens recorded against a parcel id, e.g. Allegheny PINs), first; a lien
that names a parcel but no debtor gets the stand-in debtor "owner-of:<parcel_uid>":
  lien_names_parcel         the lien itself names the parcel (instrument_parcel, or the one
                            parcel at its CITED PROPERTY address, see LOTS_SQL), and
                            that parcel is in the owner source; no name match needed -> auto
Any debtor whose lien or judgment names a county (and every run uses this rule):
  org_name_county           same org_name, and the debtor's county is the parcel's county
                            -> review (no address to confirm it is the same business)
With court_sources (court judgments: case_party debtors of a judgment, e.g. the federal IDB,
whose parties carry a county but no address, and whose people are surnames only), their
debtor parties join the debtors.
With writ_sources (e.g. Hillsborough garnishment), defendants of cases whose docket shows an
enforcement writ join the debtors as judgment debtors (amount unpublished).
With street_town (CT only, approved by the project owner 2026-11-22), also:
  person_name_street_town   same person name_key, street line and town         -> auto
  org_name_street_town      same org_name, street line and town                -> auto

Output (Parquet under data/derived/<state>/, which is git-ignored: it names people):
  matches.parquet   debtor party, its instrument, owner party, parcel, rule, decision, keys
  debtor_summary.parquet   per matched debtor: liens, open amount, parcels, total parcel value,
                    and with recorder sources open mortgages and equity_est (see .equity)
  people.parquet    one row per debtor person or business (parties merged across liens and
                    sources, see PEOPLE_SQL): open judgments, open amount, matched parcels
  mortgage_status.parquet  each mortgage on a matched lot: open or which rule marked it paid
  review_queue.parquet     evidence and labels for review-only matches (see .review)
and a summary with counts only, printed and written to summary.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import duckdb
import yaml

from equity.config import CONFIG_DIR

LAKE = Path("data/lake")
DERIVED = Path("data/derived")
TEMP_LIMIT = "30GB"


def memory_limit() -> str | None:
    """EQUITY_MEMORY_LIMIT ('6GB', '512MB'), validated; None leaves DuckDB's default."""
    raw = os.environ.get("EQUITY_MEMORY_LIMIT", "").strip().upper()
    if not raw:
        return None
    if not re.fullmatch(r"[0-9]+(\.[0-9]+)?\s*(KB|MB|GB|TB)", raw):
        raise ValueError(f"EQUITY_MEMORY_LIMIT must look like '6GB', not {raw!r}")
    return raw.replace(" ", "")


DEBT_KINDS = CONFIG_DIR / "debt_kinds.yaml"


def debt_kinds() -> dict[str, str]:
    """source_id -> kind of debt (court_judgment, tax_lien, ...), from config/debt_kinds.yaml."""
    data = yaml.safe_load(DEBT_KINDS.read_text())
    allowed = set(data["kinds"])
    out = {str(k): str(v) for k, v in data["sources"].items()}
    bad = sorted(k for k, v in out.items() if v not in allowed)
    if bad:
        raise ValueError(f"debt_kinds.yaml: unknown kind for {bad}")
    return out


# Words that never identify a person: suffixes, conjunctions, "et al", trustee markers.
STOP = ("JR", "SR", "II", "III", "IV", "AND", "OR", "ETAL", "ET", "AL", "TR", "TRUSTEE",
        "TTEE", "MR", "MRS", "MS", "DR", "THE", "OF", "C/O", "CO", "ATTN")  # fmt: skip
RULES = (
    ("lien_names_parcel", "auto", 0),
    ("person_name_address", "auto", 1),
    ("org_name_address", "auto", 2),
    ("org_name_zip", "auto", 3),
    ("person_name_zip", "review", 4),
    ("person_name_street_town", "auto", 5),
    ("org_name_street_town", "auto", 6),
    ("org_name_county", "review", 7),
    ("person_name_initial_address", "review", 8),
)


def _glob(lake: Path, sources: list[str], table: str) -> str | None:
    paths = [str(p) for s in sources for p in sorted((lake / s / table).glob("*.parquet"))]
    if not paths:
        return None
    return "[" + ", ".join("'" + p.replace("'", "''") + "'" for p in paths) + "]"


V = "VARCHAR"
COLUMNS: dict[str, dict[str, str]] = {
    "address": {"address_id": V, "line1": V, "city": V, "state": V, "zip5": V},
    "party": {"party_id": V, "raw_name": V, "party_kind": V, "org_name_norm": V,
              "address_id": V},
    "instrument_party": {"instrument_uid": V, "party_id": V, "role": V},
    "instrument": {"instrument_uid": V, "source_id": V, "doc_type": V, "doc_type_raw": V,
                   "recorded_on": "DATE",
                   "principal_amount": "DOUBLE", "consideration": "DOUBLE", "jurisdiction": V},
    "instrument_ref": {"from_uid": V, "to_uid": V, "ref_type": V},
    "instrument_parcel": {"instrument_uid": V, "parcel_uid": V},
    "parcel_link": {"from_parcel_uid": V, "to_parcel_uid": V, "link_type": V},
    "business": {"sos_id": V, "name": V, "status": V},
    "business_role": {"sos_id": V, "party_id": V, "role": V, "title": V},
    "owner_snapshot": {"parcel_uid": V, "party_id": V},
    "parcel": {"parcel_uid": V, "situs_address_id": V},
    "case_party": {"case_uid": V, "party_id": V, "role": V},
    "judgment": {"judgment_uid": V, "case_uid": V, "source_id": V, "entered_on": "DATE",
                 "principal": "DOUBLE", "jurisdiction": V, "judgment_type": V},
    "judgment_event": {"judgment_uid": V, "event": V},
    "docket_entry": {"case_uid": V, "entry_date": "DATE", "source_id": V, "jurisdiction": V},
    "parcel_assessment": {"parcel_uid": V, "tax_year": "INTEGER", "appraised_total": "DOUBLE",
                          "assessed_value": "DOUBLE"},
}  # fmt: skip


def _view(con: duckdb.DuckDBPyConnection, name: str, lake: Path, sources: list[str],
          table: str) -> None:  # fmt: skip
    """A view with exactly COLUMNS[table]; columns a source lacks read as NULL."""
    cols = COLUMNS[table]
    files = _glob(lake, sources, table)
    if files is None:
        sel = ", ".join(f"NULL::{t} AS {c}" for c, t in cols.items())
        con.execute(f"CREATE TEMP VIEW {name} AS SELECT {sel} FROM (SELECT 1) WHERE false")  # noqa: S608
        return
    src = f"read_parquet({files}, union_by_name=true)"
    have = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()}  # noqa: S608
    sel = ", ".join(
        f"TRY_CAST({c} AS {t}) AS {c}" if c in have else f"NULL::{t} AS {c}"
        for c, t in cols.items()
    )
    con.execute(f"CREATE TEMP VIEW {name} AS SELECT {sel} FROM {src}")  # noqa: S608


def _q(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


def doc_type_filter(spec: list[str] | dict[str, list[str]] | None) -> str:
    """SQL limiting which instruments count as debts. A list applies to every source of the
    run; a {source: [doc types]} mapping only to the sources it names (e.g. Colorado's UCC
    system, where financing statements are not debts, beside a county tax lien list). The
    national debt lists (FEDERAL_DEBTS) always count."""
    if not spec:
        return ""
    fed = ", ".join(_q(s) for s in FEDERAL_DEBTS)
    if isinstance(spec, dict):
        named = ", ".join(_q(s) for s in sorted(spec))
        per = " OR ".join(
            f"(i.source_id = {_q(src)} AND i.doc_type IN ({', '.join(_q(t) for t in types)}))"
            for src, types in sorted(spec.items())
        )
        return f"AND (i.source_id NOT IN ({named}) OR {per})"
    types = ", ".join(_q(t) for t in spec)
    return f"AND (i.doc_type IN ({types}) OR i.source_id IN ({fed}))"


def connect(
    lake: Path,
    debtor_sources: list[str],
    owner_sources: list[str],
    parcel_on_lien: bool = False,
    court_sources: list[str] | None = None,
    writ_sources: list[str] | None = None,
    debtor_doc_types: list[str] | dict[str, list[str]] | None = None,
) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    # Large runs (NY: ~5M debtors x ~5M owners) spill to disk; cap it so a run fails cleanly
    # instead of filling the machine's disk.
    con.execute(f"SET max_temp_directory_size = '{TEMP_LIMIT}'")
    # DuckDB takes 80% of the machine's memory by default; a container shared with other jobs
    # is killed by the kernel first. EQUITY_MEMORY_LIMIT (e.g. '6GB') caps it so it spills.
    limit = memory_limit()
    if limit:
        con.execute(f"SET memory_limit = '{limit}'")
    # Only these instrument types count as debts (e.g. liens but not UCC financing statements).
    doc_filter = doc_type_filter(debtor_doc_types)
    stop = ", ".join(f"'{w}'" for w in STOP)
    con.execute(f"""
        CREATE MACRO name_key(n) AS array_to_string(list_sort(list_distinct(list_filter(
            string_split(trim(regexp_replace(upper(coalesce(n, '')), '[^A-Z0-9]+', ' ', 'g')), ' '),
            lambda w: length(w) >= 1 AND w NOT IN ({stop})))), ' ');
        CREATE MACRO name_words(k) AS CASE WHEN k = '' THEN 0 ELSE len(string_split(k, ' ')) END;
        -- Generational suffixes in a name (JR, SR, II, III, IV, V), sorted; '' when none.
        CREATE MACRO suffix_key(n) AS array_to_string(list_sort(list_distinct(list_filter(
            string_split(trim(regexp_replace(upper(coalesce(n, '')), '[^A-Z0-9]+', ' ', 'g')), ' '),
            lambda w: w IN ('JR', 'SR', 'II', 'III', 'IV', 'V', '2ND', '3RD')))), ' ');
        -- Both names carry a suffix and they differ (JOHN SMITH JR vs JOHN SMITH SR).
        CREATE MACRO suffix_conflict(a, b) AS a <> '' AND b <> '' AND a <> b;
    """)
    both = sorted(set(debtor_sources) | set(owner_sources) | set(court_sources or [])
                  | set(writ_sources or []))  # fmt: skip
    _view(con, "addr_all", lake, both, "address")
    _view(con, "d_party", lake, debtor_sources, "party")
    _view(con, "d_ip", lake, debtor_sources, "instrument_party")
    _view(con, "d_inst", lake, debtor_sources, "instrument")
    _view(con, "d_ref", lake, debtor_sources, "instrument_ref")
    _view(con, "d_lot", lake, debtor_sources, "instrument_parcel")
    _view(con, "o_party", lake, owner_sources, "party")
    _view(con, "o_snap", lake, owner_sources, "owner_snapshot")
    _view(con, "o_parcel", lake, owner_sources, "parcel")
    _view(con, "o_assess", lake, owner_sources, "parcel_assessment")
    from equity.matching.review import street_macro

    street_macro(con)
    con.execute(f"""
        CREATE TEMP TABLE addr AS
        SELECT DISTINCT address_id,
               CASE WHEN street_norm(line1) <> '' AND zip5 IS NOT NULL
                    THEN street_norm(line1) || '|' || zip5 END AS addr_key,
               CASE WHEN street_norm(line1) <> '' AND city IS NOT NULL
                    THEN street_norm(line1) || '|' || upper(trim(city)) END AS town_key,
               zip5
        FROM addr_all;
        CREATE TEMP TABLE debtors AS
        SELECT DISTINCT p.party_id, p.raw_name, p.party_kind, p.org_name_norm,
               ip.instrument_uid, i.source_id, i.doc_type, i.recorded_on, i.principal_amount,
               EXISTS (SELECT 1 FROM d_ref r WHERE r.to_uid = i.instrument_uid
                       AND r.ref_type = 'releases')
                   OR coalesce(i.doc_type_raw, '') LIKE '%(satisfied)' AS released,
               name_key(p.raw_name) AS name_key, suffix_key(p.raw_name) AS suffix_key,
               a.addr_key, a.town_key, a.zip5
        FROM d_ip ip
        JOIN d_party p ON p.party_id = ip.party_id
        JOIN d_inst i ON i.instrument_uid = ip.instrument_uid
        LEFT JOIN addr a ON a.address_id = p.address_id
        WHERE ip.role = 'debtor' {doc_filter};
        ALTER TABLE debtors ADD COLUMN county VARCHAR;
        -- A lien's county (its jurisdiction, when that is a 5-digit county FIPS).
        UPDATE debtors SET county = i.jurisdiction FROM d_inst i
        WHERE i.instrument_uid = debtors.instrument_uid
          AND regexp_full_match(coalesce(i.jurisdiction, ''), '[0-9]{{5}}');
        CREATE TEMP TABLE owners AS
        SELECT DISTINCT p.party_id, p.raw_name, p.party_kind, p.org_name_norm, s.parcel_uid,
               name_key(p.raw_name) AS name_key, suffix_key(p.raw_name) AS suffix_key,
               ma.addr_key AS mail_key, ma.zip5 AS mail_zip,
               sa.addr_key AS situs_key, sa.zip5 AS situs_zip,
               ma.town_key AS mail_town, sa.town_key AS situs_town
        FROM o_snap s
        JOIN o_party p ON p.party_id = s.party_id
        LEFT JOIN o_parcel pc ON pc.parcel_uid = s.parcel_uid
        LEFT JOIN addr ma ON ma.address_id = p.address_id
        LEFT JOIN addr sa ON sa.address_id = pc.situs_address_id;
    """)  # noqa: S608 - doc types come from STATES (repo config), quoted
    if court_sources:
        _court_debtors(con, lake, court_sources)
    if writ_sources:
        _writ_debtors(con, lake, writ_sources)
    if parcel_on_lien:
        con.execute(LOTS_SQL)
        # A lien that names a parcel but no debtor (Allegheny tax liens, foreclosures) is owed
        # by whoever owns that parcel: one stand-in debtor per parcel, "owner-of:<parcel_uid>".
        con.execute("""
            INSERT INTO debtors
            SELECT DISTINCT 'owner-of:' || l.parcel_uid, NULL, 'unknown', NULL,
                   i.instrument_uid, i.source_id, i.doc_type, i.recorded_on,
                   i.principal_amount,
                   EXISTS (SELECT 1 FROM d_ref r WHERE r.to_uid = i.instrument_uid
                           AND r.ref_type = 'releases')
                       OR coalesce(i.doc_type_raw, '') LIKE '%(satisfied)',
                   '', '', NULL, NULL, NULL, NULL
            FROM d_inst i JOIN lots l ON l.instrument_uid = i.instrument_uid
            WHERE i.doc_type <> 'RELEASE' AND NOT EXISTS (
                SELECT 1 FROM d_ip ip WHERE ip.instrument_uid = i.instrument_uid
                  AND ip.role = 'debtor');
        """)
    return con


def _court_debtors(con: duckdb.DuckDBPyConnection, lake: Path, sources: list[str]) -> None:
    """Debtor parties of court judgments in the owners' counties or states (the judgment's
    jurisdiction is a county FIPS when the court record names one, else a state FIPS, as in
    EPA ICIS; state-level debtors can match only by address, never by org_name_county).
    A 'satisfied' judgment event releases it."""
    _view(con, "c_party", lake, sources, "party")
    _view(con, "c_cp", lake, sources, "case_party")
    _view(con, "c_judg", lake, sources, "judgment")
    _view(con, "c_event", lake, sources, "judgment_event")
    con.execute("""
        INSERT INTO debtors
        SELECT DISTINCT p.party_id, p.raw_name, p.party_kind, p.org_name_norm,
               j.judgment_uid, j.source_id, 'COURT_JUDGMENT', j.entered_on, j.principal,
               EXISTS (SELECT 1 FROM c_event e WHERE e.judgment_uid = j.judgment_uid
                       AND e.event = 'satisfied'),
               name_key(p.raw_name), suffix_key(p.raw_name), a.addr_key, a.town_key, a.zip5,
               j.jurisdiction
        FROM c_judg j
        JOIN c_cp cp ON cp.case_uid = j.case_uid
         AND (cp.role = 'debtor'
              -- A court that records only plaintiff/defendant: for a judgment that runs
              -- against the defendant by its type, the defendants are the debtors.
              OR (cp.role = 'defendant'
                  AND j.judgment_type IN ('default', 'money', 'deficiency', 'consent')
                  AND NOT EXISTS (SELECT 1 FROM c_cp x WHERE x.case_uid = j.case_uid
                                  AND x.role IN ('debtor', 'creditor'))))
        JOIN c_party p ON p.party_id = cp.party_id
        LEFT JOIN addr a ON a.address_id = p.address_id
        WHERE j.jurisdiction IN (SELECT DISTINCT left(parcel_uid, 5) FROM o_parcel)
           OR j.jurisdiction IN (SELECT DISTINCT left(parcel_uid, 2) FROM o_parcel);
    """)


def _writ_debtors(con: duckdb.DuckDBPyConnection, lake: Path, sources: list[str]) -> None:
    """Defendants in cases with an enforcement writ (garnishment) on the docket: a writ issues
    only on a judgment, so each such case is one judgment owed by its defendants. Its amount
    is not published (NULL) and its date is the first writ entry."""
    _view(con, "w_party", lake, sources, "party")
    _view(con, "w_cp", lake, sources, "case_party")
    _view(con, "w_entry", lake, sources, "docket_entry")
    con.execute("""
        INSERT INTO debtors
        SELECT DISTINCT p.party_id, p.raw_name, p.party_kind, p.org_name_norm,
               'writ:' || e.case_uid, e.source_id, 'COURT_JUDGMENT', e.first_on, NULL, false,
               name_key(p.raw_name), suffix_key(p.raw_name), a.addr_key, a.town_key, a.zip5,
               e.jurisdiction
        FROM (SELECT case_uid, any_value(source_id) AS source_id,
                     any_value(jurisdiction) AS jurisdiction, min(entry_date) AS first_on
              FROM w_entry GROUP BY case_uid) e
        JOIN w_cp cp ON cp.case_uid = e.case_uid AND cp.role IN ('defendant', 'debtor')
        JOIN w_party p ON p.party_id = cp.party_id
        LEFT JOIN addr a ON a.address_id = p.address_id;
    """)


# The parcels a lien names: its instrument_parcel rows, plus, for a lien whose 'CITED
# PROPERTY' party (role 'other') carries the cited property's address (code charges that
# give an address but no parcel id), the one owner parcel whose situs address has the same
# street line and ZIP, or street line and town. An address shared by several parcels
# (condos, multi-lot sites) is ambiguous and names none.
LOTS_SQL = """
CREATE TEMP TABLE lots AS
SELECT DISTINCT instrument_uid, parcel_uid FROM d_lot
UNION
SELECT instrument_uid, any_value(parcel_uid) FROM (
    SELECT DISTINCT ip.instrument_uid, pc.parcel_uid
    FROM d_ip ip
    JOIN d_party p ON p.party_id = ip.party_id
    JOIN addr a ON a.address_id = p.address_id
    JOIN addr sa ON (a.addr_key IS NOT NULL AND sa.addr_key = a.addr_key)
                 OR (a.town_key IS NOT NULL AND sa.town_key = a.town_key)
    JOIN o_parcel pc ON pc.situs_address_id = sa.address_id
    WHERE ip.role = 'other' AND p.raw_name = 'CITED PROPERTY')
GROUP BY instrument_uid HAVING count(*) = 1;
"""
COURT_COUNTY_SQL = """
INSERT INTO candidates
SELECT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid, 'org_name_county',
       d.org_name_norm
FROM debtors d JOIN owners o ON o.org_name_norm = d.org_name_norm
WHERE d.county IS NOT NULL AND d.party_kind = 'org' AND o.party_kind = 'org'
  AND d.org_name_norm <> '' AND left(o.parcel_uid, 5) = d.county;
"""
MATCH_SQL = """
CREATE TEMP TABLE candidates AS
SELECT d.party_id AS debtor_party_id, d.instrument_uid, o.party_id AS owner_party_id,
       o.parcel_uid, 'person_name_address' AS rule_id, d.name_key AS key
FROM debtors d JOIN owners o ON o.name_key = d.name_key
WHERE d.party_kind <> 'org' AND o.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND NOT suffix_conflict(d.suffix_key, o.suffix_key)
  AND d.addr_key IS NOT NULL AND d.addr_key IN (o.mail_key, o.situs_key)
UNION ALL
SELECT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid, 'org_name_address', d.org_name_norm
FROM debtors d JOIN owners o ON o.org_name_norm = d.org_name_norm
WHERE d.party_kind = 'org' AND o.party_kind = 'org' AND d.org_name_norm <> ''
  AND d.addr_key IS NOT NULL AND d.addr_key IN (o.mail_key, o.situs_key)
UNION ALL
SELECT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid, 'org_name_zip', d.org_name_norm
FROM debtors d JOIN owners o ON o.org_name_norm = d.org_name_norm
WHERE d.party_kind = 'org' AND o.party_kind = 'org' AND d.org_name_norm <> ''
  AND d.zip5 IS NOT NULL AND d.zip5 IN (o.mail_zip, o.situs_zip)
UNION ALL
SELECT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid, 'person_name_zip', d.name_key
FROM debtors d JOIN owners o ON o.name_key = d.name_key
WHERE d.party_kind <> 'org' AND o.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND NOT suffix_conflict(d.suffix_key, o.suffix_key)
  AND d.zip5 IS NOT NULL AND d.zip5 IN (o.mail_zip, o.situs_zip);
"""
# One row per person or business behind the debtor parties: every source loads one party per
# lien, so the same debtor appears once per ticket, warrant or judgment. Parties are the same
# debtor when they share the identity key (org name, or person name_key, plus address key or
# ZIP when known) or are matched by an auto rule to the same parcel-owner party. Connected
# groups are merged with a fixed number of label-propagation passes (min party id wins),
# which is deterministic. Parcel value is counted once per distinct parcel.
PEOPLE_SQL = """
CREATE TEMP TABLE debtor_identity AS
SELECT DISTINCT party_id,
       CASE WHEN starts_with(party_id, 'owner-of:') THEN party_id
            WHEN party_kind = 'org' AND coalesce(org_name_norm, '') <> ''
            THEN 'org:' || org_name_norm || '|' || coalesce(addr_key, zip5, '')
            WHEN name_words(name_key) >= 2
            THEN 'person:' || name_key || '|' || coalesce(addr_key, zip5, '')
            ELSE 'party:' || party_id END AS identity
FROM debtors;
-- Each group (an identity key, or an auto-matched owner party) is a star around its smallest
-- party id, both ways, so the edges grow with the parties, not with the square of a group.
CREATE TEMP TABLE person_groups AS
SELECT party_id, identity AS grp FROM debtor_identity
UNION
SELECT DISTINCT debtor_party_id, 'owner:' || owner_party_id FROM matches
WHERE decision = 'auto' AND owner_party_id IS NOT NULL;
CREATE TEMP TABLE person_edges AS
WITH hub AS (SELECT grp, min(party_id) AS h FROM person_groups GROUP BY grp)
SELECT DISTINCT * FROM (
    SELECT g.party_id AS x, hub.h AS y FROM person_groups g JOIN hub USING (grp)
    UNION ALL
    SELECT hub.h, g.party_id FROM person_groups g JOIN hub USING (grp)
    UNION ALL
    SELECT party_id, party_id FROM person_groups);
CREATE TEMP TABLE person_of AS
SELECT x AS party_id, min(y) AS person_id FROM person_edges GROUP BY x;
"""
PEOPLE_MERGE_STEP_SQL = """
CREATE OR REPLACE TEMP TABLE person_of AS
SELECT e.x AS party_id, min(p.person_id) AS person_id
FROM person_edges e JOIN person_of p ON p.party_id = e.y GROUP BY e.x;
"""
PEOPLE_SUMMARY_SQL = """
CREATE TEMP TABLE people AS
WITH j AS (
    SELECT po.person_id, d.instrument_uid, any_value(d.source_id) AS source_id,
           any_value(d.doc_type) AS doc_type, bool_or(d.released) AS released,
           any_value(d.principal_amount) AS amount, any_value(d.raw_name) AS raw_name
    FROM debtors d JOIN person_of po ON po.party_id = d.party_id
    GROUP BY po.person_id, d.instrument_uid
), lots AS (
    SELECT DISTINCT po.person_id, m.parcel_uid
    FROM matches m JOIN person_of po ON po.party_id = m.debtor_party_id
    WHERE m.decision = 'auto'
)
SELECT j.person_id, mode(j.raw_name) AS name,
       count(*) FILTER (WHERE j.doc_type <> 'LIS_PENDENS') AS judgments_and_liens,
       count(*) FILTER (WHERE j.doc_type <> 'LIS_PENDENS' AND NOT j.released) AS open_count,
       sum(CASE WHEN NOT j.released AND j.doc_type <> 'LIS_PENDENS' THEN j.amount END)
           AS open_amount,
       count(*) FILTER (WHERE j.doc_type = 'LIS_PENDENS') AS foreclosure_filings,
       list_sort(list_distinct(list(j.source_id))) AS sources,
       list_sort(list_distinct(list(coalesce(k.kind, 'unlabeled')))) AS debt_kinds,
       (SELECT count(*) FROM lots l WHERE l.person_id = j.person_id) AS parcels,
       (SELECT sum(v.value) FROM lots l JOIN parcel_value v ON v.parcel_uid = l.parcel_uid
        WHERE l.person_id = j.person_id) AS parcel_value
FROM j LEFT JOIN debt_kind k ON k.source_id = j.source_id GROUP BY j.person_id;
"""
PEOPLE_PASSES = 12  # star edges: two hops per group
PARCEL_ON_LIEN_SQL = """
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, NULL, l.parcel_uid, 'lien_names_parcel',
       l.parcel_uid
FROM debtors d JOIN lots l ON l.instrument_uid = d.instrument_uid
WHERE l.parcel_uid IN (SELECT parcel_uid FROM o_parcel)
  AND (NOT starts_with(d.party_id, 'owner-of:') OR d.party_id = 'owner-of:' || l.parcel_uid);
"""
# One name key is the other plus exactly one single-letter word (a middle initial).
INITIAL_SQL = """
CREATE TEMP TABLE o_by_addr AS
SELECT party_id, parcel_uid, name_key, suffix_key, mail_key AS k FROM owners
WHERE party_kind <> 'org' AND mail_key IS NOT NULL AND name_words(name_key) >= 2
UNION
SELECT party_id, parcel_uid, name_key, suffix_key, situs_key FROM owners
WHERE party_kind <> 'org' AND situs_key IS NOT NULL AND name_words(name_key) >= 2;
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid,
       'person_name_initial_address', d.name_key
FROM debtors d JOIN o_by_addr o ON o.k = d.addr_key
WHERE d.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND NOT suffix_conflict(d.suffix_key, o.suffix_key)
  AND d.name_key <> o.name_key
  AND abs(name_words(d.name_key) - name_words(o.name_key)) = 1
  AND (list_has_all(string_split(o.name_key, ' '), string_split(d.name_key, ' '))
       OR list_has_all(string_split(d.name_key, ' '), string_split(o.name_key, ' ')))
  AND length(list_filter(
        string_split(CASE WHEN name_words(o.name_key) > name_words(d.name_key)
                          THEN o.name_key ELSE d.name_key END, ' '),
        lambda w: NOT list_contains(string_split(CASE WHEN name_words(o.name_key) >
            name_words(d.name_key) THEN d.name_key ELSE o.name_key END, ' '), w))[1]) = 1;
"""
STREET_TOWN_SQL = """
INSERT INTO candidates
SELECT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid, 'person_name_street_town',
       d.name_key
FROM debtors d JOIN owners o ON o.name_key = d.name_key
WHERE d.party_kind <> 'org' AND o.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND NOT suffix_conflict(d.suffix_key, o.suffix_key)
  AND d.town_key IS NOT NULL AND d.town_key IN (o.mail_town, o.situs_town)
UNION ALL
SELECT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid, 'org_name_street_town',
       d.org_name_norm
FROM debtors d JOIN owners o ON o.org_name_norm = d.org_name_norm
WHERE d.party_kind = 'org' AND o.party_kind = 'org' AND d.org_name_norm <> ''
  AND d.town_key IS NOT NULL AND d.town_key IN (o.mail_town, o.situs_town);
"""


def match(
    con: duckdb.DuckDBPyConnection,
    street_town: bool = False,
    parcel_on_lien: bool = False,
    courts: bool = False,
) -> None:
    con.execute(MATCH_SQL)
    con.execute(COURT_COUNTY_SQL)
    con.execute(INITIAL_SQL)
    if parcel_on_lien:
        con.execute(PARCEL_ON_LIEN_SQL)
    if street_town:
        con.execute(STREET_TOWN_SQL)
    ranks = " ".join(f"WHEN '{r}' THEN {n}" for r, _, n in RULES)
    decisions = " ".join(f"WHEN '{r}' THEN '{d}'" for r, d, _ in RULES)
    con.execute(f"""
        CREATE TEMP TABLE matches AS
        SELECT debtor_party_id, instrument_uid, owner_party_id, parcel_uid, rule_id,
               CASE rule_id {decisions} END AS decision, key
        FROM candidates
        QUALIFY row_number() OVER (
            PARTITION BY debtor_party_id, instrument_uid, owner_party_id, parcel_uid
            ORDER BY CASE rule_id {ranks} END) = 1;
        CREATE TEMP TABLE parcel_value AS
        SELECT parcel_uid, arg_max(coalesce(appraised_total, assessed_value), tax_year) AS value
        FROM o_assess GROUP BY parcel_uid;
        CREATE TEMP TABLE debtor_summary AS
        WITH liens AS (
            SELECT party_id, any_value(raw_name) AS debtor_name,
                   count(*) FILTER (WHERE doc_type <> 'LIS_PENDENS') AS liens,
                   -- A foreclosure filing claims mortgage debt, not a lien to buy, and its
                   -- outcome is not published: counted, never added to open_amount.
                   sum(CASE WHEN NOT released AND doc_type <> 'LIS_PENDENS'
                            THEN principal_amount END) AS open_amount,
                   count(*) FILTER (WHERE doc_type = 'LIS_PENDENS') AS foreclosure_filings,
                   max(recorded_on) FILTER (WHERE doc_type = 'LIS_PENDENS') AS last_foreclosure_on
            FROM (SELECT DISTINCT party_id, raw_name, instrument_uid, doc_type, recorded_on,
                         released, principal_amount
                  FROM debtors) GROUP BY party_id
        ), props AS (
            SELECT mp.debtor_party_id, count(*) AS parcels, sum(v.value) AS parcel_value
            FROM (SELECT DISTINCT debtor_party_id, parcel_uid FROM matches) mp
            LEFT JOIN parcel_value v ON v.parcel_uid = mp.parcel_uid
            GROUP BY mp.debtor_party_id
        ), rules AS (
            SELECT debtor_party_id, min(CASE rule_id {ranks} END) AS best_rank,
                   bool_or(decision = 'auto') AS has_auto
            FROM matches GROUP BY debtor_party_id
        )
        SELECT r.debtor_party_id, l.debtor_name, l.liens, l.open_amount, p.parcels,
               p.parcel_value, r.best_rank, r.has_auto, l.foreclosure_filings,
               l.last_foreclosure_on
        FROM rules r
        JOIN liens l ON l.party_id = r.debtor_party_id
        JOIN props p ON p.debtor_party_id = r.debtor_party_id;
    """)  # noqa: S608 - rule names are constants
    con.execute(PEOPLE_SQL)
    for _ in range(PEOPLE_PASSES):
        con.execute(PEOPLE_MERGE_STEP_SQL)
    con.execute("CREATE OR REPLACE TEMP TABLE debt_kind (source_id VARCHAR, kind VARCHAR)")
    kinds = sorted(debt_kinds().items())
    if kinds:
        con.executemany("INSERT INTO debt_kind VALUES (?, ?)", kinds)
    con.execute(PEOPLE_SUMMARY_SQL)


def summary(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    def one(sql: str) -> object:
        row = con.execute(sql).fetchone()
        return None if row is None else row[0]

    by_rule = dict(
        con.execute("SELECT rule_id, count(*) FROM matches GROUP BY 1 ORDER BY 1").fetchall()
    )
    auto = "FROM debtor_summary WHERE has_auto"
    return {
        "debtor_parties": one("SELECT count(DISTINCT party_id) FROM debtors"),
        "owner_parties": one("SELECT count(DISTINCT party_id) FROM owners"),
        "matches_by_rule": by_rule,
        "debtors_matched_auto": one(f"SELECT count(*) {auto}"),
        "debtor_names_matched_auto": one(f"SELECT count(DISTINCT debtor_name) {auto}"),
        "debtors_matched_review_only": one(
            "SELECT count(*) FROM debtor_summary WHERE NOT has_auto"
        ),
        "open_amount_auto": one(f"SELECT round(sum(open_amount), 2) {auto}"),
        "parcel_value_auto": one(f"SELECT round(sum(parcel_value), 2) {auto}"),
        # Each judgment once, however many debtors it names (people totals count a joint
        # judgment once per debtor, since each is liable for it).
        "open_judgments_linked": one(
            "SELECT count(DISTINCT d.instrument_uid) FROM debtors d JOIN matches m"
            " ON m.instrument_uid = d.instrument_uid AND m.decision = 'auto'"
            " WHERE NOT d.released AND d.doc_type <> 'LIS_PENDENS'"
        ),
        "open_amount_linked_once": one(
            "SELECT round(sum(a), 2) FROM (SELECT any_value(d.principal_amount) AS a"
            " FROM debtors d JOIN matches m ON m.instrument_uid = d.instrument_uid"
            " AND m.decision = 'auto' WHERE NOT d.released AND d.doc_type <> 'LIS_PENDENS'"
            " GROUP BY d.instrument_uid)"
        ),
        # Open judgments and liens linked to an owner, and their amount, by kind of debt.
        "open_linked_by_kind": {
            k: {"count": n, "amount": a}
            for k, n, a in con.execute(
                "SELECT coalesce(k.kind, 'unlabeled'), count(*), round(sum(amount), 2) FROM ("
                " SELECT d.instrument_uid, any_value(d.source_id) AS source_id,"
                " any_value(d.principal_amount) AS amount FROM debtors d JOIN matches m"
                " ON m.instrument_uid = d.instrument_uid AND m.decision = 'auto'"
                " WHERE NOT d.released AND d.doc_type <> 'LIS_PENDENS' GROUP BY 1) x"
                " LEFT JOIN debt_kind k USING (source_id) GROUP BY 1 ORDER BY 1"
            ).fetchall()
        },
        "people": one("SELECT count(*) FROM people"),
        "people_with_parcels": one("SELECT count(*) FROM people WHERE parcels > 0"),
        "people_open_amount_with_parcels": one(
            "SELECT round(sum(open_amount), 2) FROM people WHERE parcels > 0"
        ),
        "people_parcel_value": one(
            "SELECT round(sum(parcel_value), 2) FROM people WHERE parcels > 0"
        ),
    }


def run(
    lake: Path,
    out: Path,
    debtor_sources: list[str],
    owner_sources: list[str],
    mortgage_sources: list[str] | None = None,
    link_sources: list[str] | None = None,
    street_town: bool = False,
    parcel_on_lien: bool = False,
    court_sources: list[str] | None = None,
    writ_sources: list[str] | None = None,
    registry_sources: list[str] | None = None,
    debtor_doc_types: list[str] | dict[str, list[str]] | None = None,
    bankruptcy_sources: list[str] | None = None,
    deed_sources: list[str] | None = None,
) -> dict[str, object]:
    from equity.matching import bankruptcy, entities, equity, review, transfers

    con = connect(lake, debtor_sources, owner_sources, parcel_on_lien, court_sources,
                  writ_sources, debtor_doc_types)  # fmt: skip
    match(con, street_town, parcel_on_lien, bool(court_sources))
    review.build(con)
    tables = ["matches", "debtor_summary", "people", "person_of", "review_queue"]
    if registry_sources:
        entities.compute(con, lake, registry_sources)
        tables.extend(entities.TABLES)
    if bankruptcy_sources:
        bankruptcy.compute(con, lake, bankruptcy_sources)
        tables.extend(bankruptcy.TABLES)
    if deed_sources:  # after entities: the nominee check reads company_people
        transfers.compute(con, lake, deed_sources)
        tables.extend(transfers.TABLES)
    if mortgage_sources:
        equity.compute(con, lake, mortgage_sources, link_sources or [])
        tables.append("mortgage_status")
    out.mkdir(parents=True, exist_ok=True)
    for table in tables:
        con.execute(f"COPY {table} TO '{(out / (table + '.parquet')).as_posix()}' "
                    "(FORMAT PARQUET, COMPRESSION ZSTD)")  # fmt: skip
    result = summary(con)
    result["review"] = review.summary(con)
    if registry_sources:
        result["registries"] = entities.summary(con)
    if bankruptcy_sources:
        result["bankruptcy"] = bankruptcy.summary(con)
    if deed_sources:
        result["transfers"] = transfers.summary(con)
    if mortgage_sources:
        result |= equity.summary(con)
    (out / "summary.json").write_text(json.dumps(result, indent=2, default=str))
    return result


# Federal court money judgments (FJC IDB, its CourtListener copy, EPA judicial cases): every
# run matches the ones in its owners' counties.
FEDERAL_COURTS = ["us.fjc.idb.civil_judgments", "us.fjc.idb.direct.civil_judgments",
                  "us.epa.echo.judicial_cases"]  # fmt: skip
# National debt lists every run reads as debtors (they link only where a debtor matches one
# of the run's owners): SBA 7(a)/504 and PPP loans charged off.
FEDERAL_DEBTS = ["us.sba.chargeoffs", "us.sba.ppp_chargeoffs"]
STATES: dict[str, dict[str, Any]] = {
    "NY": {
        "debtors": ["ny.dtf.tax_warrants", "ny.dtf.child_support_warrants",
                    "ny.nyc.oath.judgments", "ny.nyc.hpd_litigation", "ny.nyc.acris.real"],
        "owners": ["ny.statewide.parcels"],
        "mortgages": ["ny.nyc.acris.real"],
        "links": ["ny.nyc.dof.condo_units"],
        "courts": FEDERAL_COURTS,
        "registries": ["ny.sos.business", "ny.sos.name_history"],
        "deeds": ["ny.nyc.acris.real"],
    },
    # CT parcel data has no owner ZIP (Mailing_Zip is empty statewide): street + town instead.
    # Allegheny's parcel layer has no owner names, but its liens name the parcel (PIN).
    "PA-ALLEGHENY": {"debtors": ["pa.allegheny.tax_liens", "pa.allegheny.foreclosures"],
                     "owners": ["pa.allegheny.parcels", "pa.allegheny.assessments"],
                     "registries": ["pa.dos.business"], "parcel_on_lien": True,
                     "courts": FEDERAL_COURTS},
    "CT": {"debtors": ["ct.sots.liens"], "owners": ["ct.statewide.parcels"], "street_town": True,
           "registries": ["ct.sos.business"], "courts": FEDERAL_COURTS},
    # Baltimore City: environmental citation liens name the parcel (block/lot), not a person.
    "MD-BALTIMORE": {"debtors": ["md.baltimore_city.citation_liens"],
                     "owners": ["md.baltimore_city.parcels"], "parcel_on_lien": True,
                     "deeds": ["md.sdat.transfers_1", "md.sdat.transfers_2",
                               "md.sdat.transfers_3"],
                     "courts": FEDERAL_COURTS},
    # Travis: delinquent property tax accounts and tax-suit judgments, by owner name.
    "TX-TRAVIS": {"debtors": ["tx.travis.tax_delinquent"], "owners": ["tx.statewide.parcels"],
                  "courts": FEDERAL_COURTS},
    # Omaha: tax sale certificates (named taxpayers) and county-held liens (PIN only).
    # Plus Nebraska's statewide delinquent-taxpayer list (named, with address) and Sarpy's
    # owners (the Omaha suburbs).
    # Nebraska's statewide layer has no owner names: the statewide delinquent-taxpayer list
    # against the Lancaster (Lincoln) and Cass county owner layers.
    "NE-COUNTIES": {"debtors": ["ne.dor.delinquent_taxpayers"], "courts": FEDERAL_COURTS,
                    "owners": ["ne.cass.parcels", "ne.lancaster.parcels"]},
    "NE-DOUGLAS": {"debtors": ["ne.douglas.tax_liens", "ne.dor.delinquent_taxpayers"],
                   "owners": ["ne.douglas.parcels", "ne.sarpy.parcels"],
                   "parcel_on_lien": True, "courts": FEDERAL_COURTS},
    # Colorado: federal tax and statutory (hospital, other) liens from the SOS UCC system;
    # UCC financing statements name debtors too but are not debts owed on a judgment or lien.
    # Lake County's tax lien sale list names the owner and the parcel.
    "CO": {"debtors": ["co.sos.ucc", "co.lake.tax_lien_sale"],
           "debtor_doc_types": {"co.sos.ucc": ["TAX_LIEN_FEDERAL", "STATUTORY_LIEN"]},
           "owners": ["co.statewide.parcels"], "registries": ["co.sos.business"],
           "parcel_on_lien": True, "courts": FEDERAL_COURTS},
    # Detroit blight judgments name both the owner and the ticketed parcel (same parcel_id as
    # the Detroit assessor layer); Harris tax-suit judgments name the HCAD account; Washington
    # County sheriff sales list every parcel sold.
    "MI-DETROIT": {"debtors": ["mi.detroit.blight_judgments"], "owners": ["mi.wayne.parcels"],
                   "parcel_on_lien": True, "courts": FEDERAL_COURTS},
    "TX-HARRIS": {"debtors": ["tx.harris.tax_judgments", "tx.tceq.civil_judgments",
                              "tx.tceq.administrative_orders", "tx.harris.delinquent_taxes"],
                  "owners": ["tx.statewide.parcels"], "parcel_on_lien": True,
                  "courts": ["tx.harris.jp.civil_judgments", "tx.harris.district.civil_judgments",
                             *FEDERAL_COURTS]},
    # Hillsborough: recorded judgments and liens (Official Records index), civil judgments,
    # and judgment debtors under a writ of garnishment (with their address).
    "FL": {"debtors": ["fl.hillsborough.or", "fl.dor.tax_warrants", "fl.hernando.or",
                       "fl.putnam.or", "fl.broward.tax_certificates", "fl.lee.nuisance_liens",
                       "fl.miami_dade.code_liens", "fl.miami_dade.code_collections",
                       "fl.miami_dade.waste_judgments", "fl.miami_dade.building_liens"],
           "owners": ["fl.statewide.parcels"],
           "courts": ["fl.hillsborough.civil.cases", "fl.citrus.civil", *FEDERAL_COURTS],
           "writs": ["fl.hillsborough.garnishment"], "parcel_on_lien": True,
           "deeds": ["fl.hillsborough.or", "fl.hernando.or", "fl.putnam.or"]},
    # PA L&I lists name employers statewide; county parcel layers with owner names.
    "PA": {"debtors": ["pa.dli.uc_liens", "pa.dli.bwc_noncompliance", "pa.dli.bllc_noncompliance",
                       "pa.washington.sheriff_sales", "pa.philadelphia.li_fines"],
           "owners": ["pa.berks.parcels", "pa.bucks.parcels", "pa.chester.parcels",
                      "pa.erie.parcels", "pa.franklin.parcels", "pa.lancaster.parcels",
                      "pa.mercer.parcels", "pa.montgomery.parcels", "pa.philadelphia.parcels",
                      "pa.washington.parcels", "pa.york.parcels", "pa.cumberland.parcels"],
           "parcel_on_lien": True, "courts": FEDERAL_COURTS, "street_town": True,
           "deeds": ["pa.philadelphia.rtt"]},
    # The PA and VT lists publish street and town but no ZIP: street + town rules, as in CT.
    "VT": {"debtors": ["vt.tax.top100_individuals", "vt.tax.top100_businesses"],
           "owners": ["vt.statewide.parcels"], "courts": FEDERAL_COURTS,
           "street_town": True},
    # Chicago DOAH cites the property's street address with no ZIP: street + town rules.
    "IL-COOK": {"debtors": ["il.chicago.doah_judgments", "il.chicago.doe_judgments",
                            "il.chicago.vacant_building_judgments"], "owners": ["il.cook.parcels"],
                "deeds": ["il.cook.sales", "il.ptax.transfers"],
                "courts": FEDERAL_COURTS, "street_town": True},
    # New Orleans code judgments name the parcel (GeoPIN), not the owner.
    "LA-NOLA": {"debtors": ["la.nola.code_hearing_judgments"], "owners": ["la.orleans.parcels"],
                "courts": FEDERAL_COURTS, "parcel_on_lien": True},
    # Cincinnati lot abatement cites the property's address only: its parcel is found by
    # situs address (LOTS_SQL) and the charge is owed by that parcel's owner.
    "OH": {"debtors": ["oh.cincinnati.lot_abatement", "oh.hamilton.delinquent_taxes",
                       "oh.clermont.tax_delinquent", "oh.mahoning.delinquent_taxes",
                       "oh.lucas.forfeited_land_sale"],
           "owners": ["oh.clermont.parcels", "oh.lucas.parcels", "oh.mahoning.parcels",
                      "oh.statewide.parcels"],
           "parcel_on_lien": True, "courts": FEDERAL_COURTS},
    # Milwaukee delinquent taxes name the owner, mailing address and tax key (= WI PARCELID).
    "WI-MILWAUKEE": {"debtors": ["wi.milwaukee.delinquent_taxes",
                                 "wi.milwaukee.foreclosure_sales"],
                     "owners": ["wi.statewide.parcels"], "parcel_on_lien": True,
                     "courts": FEDERAL_COURTS},
    "VA-RICHMOND": {"debtors": ["va.richmond.tax_delinquent"],
                    "owners": ["va.richmond_city.parcels"], "parcel_on_lien": True,
                    "courts": FEDERAL_COURTS},
    # North Carolina: Guilford and Buncombe unpaid property taxes, Charlotte municipal liens.
    "NC": {"debtors": ["nc.guilford.tax_delinquent", "nc.buncombe.unpaid_bills",
                       "nc.charlotte.municipal_liens"],
                    "owners": ["nc.statewide.parcels"], "parcel_on_lien": True,
                    "courts": FEDERAL_COURTS},
    "AZ-COCHISE": {"debtors": ["az.cochise.tax_liens", "az.cochise.tax_deed_auction"],
                   "owners": ["az.cochise.parcels"],
                   "parcel_on_lien": True, "courts": FEDERAL_COURTS},
    "MS-HARRISON": {"debtors": ["ms.harrison.tax_sale_parcels"], "owners": ["ms.statewide.parcels"],
                    "parcel_on_lien": True, "courts": FEDERAL_COURTS},
    "AZ-PIMA": {"debtors": ["az.tucson.code_liens"], "owners": ["az.pima.parcels"],
                "courts": FEDERAL_COURTS},
    "PA-WASHINGTON": {"debtors": ["pa.washington.sheriff_sales"],
                      "owners": ["pa.washington.parcels"], "parcel_on_lien": True},
    # NYC lien sale notices name no one: each is owed by the noticed parcel's owner. A run
    # of its own, so the NY run's ACRIS instruments do not take on parcel_on_lien.
    "NY-NYC-LIENSALE": {"debtors": ["ny.nyc.tax_lien_sale"], "owners": ["ny.statewide.parcels"],
                        "parcel_on_lien": True},
    # St. Joseph IN tax sale: named owners and state parcel numbers. Indiana's statewide layer
    # has parcels but no owner names, so debtors link to the parcels their liens name.
    "IN-STJOSEPH": {"debtors": ["in.st_joseph.tax_sale"], "owners": ["in.statewide.parcels"],
                    "parcel_on_lien": True, "courts": FEDERAL_COURTS},
    # West Virginia, the pilot state: no county lien list in instrument form yet (the
    # delinquent-lands list is a snapshot table), so federal court judgments and the national
    # debt lists against WV owners.
    "WV": {"debtors": [], "owners": ["wv.statewide.parcels"], "courts": FEDERAL_COURTS},
    # States and counties whose parcel layers carry owner names and that have no county debt
    # list yet: federal court judgments and the national debt lists (SBA) against their owners.
    "MT": {"debtors": [], "owners": ["mt.statewide.parcels"], "courts": FEDERAL_COURTS},
    "ID": {"debtors": [], "owners": ["id.statewide.parcels"], "courts": FEDERAL_COURTS},
    "AR": {"debtors": [], "owners": ["ar.statewide.parcels"], "courts": FEDERAL_COURTS},
    "ND": {"debtors": [], "owners": ["nd.statewide.parcels"], "courts": FEDERAL_COURTS},
    "WY": {"debtors": [], "owners": ["wy.statewide.parcels"], "courts": FEDERAL_COURTS},
    "ME": {"debtors": [], "owners": ["me.statewide.parcels"], "courts": FEDERAL_COURTS},
    "MN": {"debtors": [], "owners": ["mn.statewide.parcels", "mn.metro.parcels"],
           "courts": FEDERAL_COURTS},
    "MA": {"debtors": [], "owners": ["ma.statewide.parcels"], "courts": FEDERAL_COURTS},
    "NV-WASHOE": {"debtors": [], "owners": ["nv.washoe.parcels"], "courts": FEDERAL_COURTS},
    # County parcel layers with owner names in states (or counties) with no county debt list
    # yet: federal court judgments, the national debt lists (SBA 7(a)/504 and PPP charge-offs)
    # and the state's bankruptcy feeds against those owners.
    "AK": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["ak.anchorage.parcels", "ak.fairbanks_north_star.parcels",
                      "ak.kenai_peninsula.parcels"]},
    "AL": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["al.blount.parcels", "al.cullman.parcels", "al.dekalb.parcels",
                      "al.houston.parcels", "al.jefferson.parcels", "al.lauderdale.parcels",
                      "al.madison.parcels", "al.marshall.parcels", "al.mobile.parcels",
                      "al.montgomery.parcels", "al.morgan.parcels", "al.talladega.parcels",
                      "al.tuscaloosa.parcels"]},
    "AZ-COUNTIES": {"debtors": [], "courts": FEDERAL_COURTS,
                    "owners": ["az.coconino.parcels", "az.mohave.parcels", "az.pinal.parcels",
                               "az.yavapai.parcels", "az.yuma.parcels", "az.apache.parcels",
                               "az.gila.parcels", "az.graham.parcels", "az.greenlee.parcels",
                               "az.la_paz.parcels", "az.navajo.parcels",
                               "az.santa_cruz.parcels"]},
    "GA": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["ga.chatham.parcels", "ga.clayton.parcels", "ga.cobb.parcels",
                      "ga.dekalb.parcels", "ga.dougherty.parcels", "ga.fulton.parcels",
                      "ga.gwinnett.parcels"]},
    "IA": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["ia.blackhawk.parcels", "ia.johnson.parcels", "ia.linn.parcels",
                      "ia.scott.parcels", "ia.story.parcels", "ia.woodbury.parcels"]},
    "IL-COLLAR": {"debtors": [], "courts": FEDERAL_COURTS,
                  "owners": ["il.dupage.parcels", "il.kane.parcels", "il.lake.parcels",
                             "il.mchenry.parcels"]},
    "IL-COUNTIES": {"debtors": [], "courts": FEDERAL_COURTS,
                    "owners": ["il.adams.parcels", "il.madison.parcels", "il.whiteside.parcels"]},
    "KS": {"debtors": [], "courts": FEDERAL_COURTS, "owners": ["ks.douglas.parcels"]},
    "KY": {"debtors": [], "courts": FEDERAL_COURTS, "owners": ["ky.boone.parcels"]},
    "LA-EBR": {"debtors": [], "courts": FEDERAL_COURTS, "owners": ["la.eastbatonrouge.parcels"]},
    "MI-COUNTIES": {"debtors": [], "courts": FEDERAL_COURTS,
                    "owners": ["mi.barry.parcels", "mi.eaton.parcels", "mi.genesee.parcels",
                               "mi.ingham.parcels", "mi.kalamazoo.parcels", "mi.lenawee.parcels",
                               "mi.macomb.parcels", "mi.ottawa.parcels"]},
    "MO": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["mo.jackson.parcels", "mo.st_louis_county.parcels",
                      "mo.jefferson.parcels", "mo.st_charles.parcels"]},
    "NH": {"debtors": [], "courts": FEDERAL_COURTS, "owners": ["nh.nrpc.parcels"]},
    "NM": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["nm.dona_ana.parcels", "nm.sandoval.parcels", "nm.grant.parcels"]},
    "OK": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["ok.canadian.parcels", "ok.oklahoma.parcels", "ok.tulsa.parcels"]},
    "OR": {"debtors": [], "courts": FEDERAL_COURTS, "registries": ["or.sos.business"],
           "owners": ["or.deschutes.parcels", "or.jackson.parcels", "or.lane.parcels",
                      "or.multnomah.parcels"]},
    "SC": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["sc.charleston.parcels", "sc.georgetown.parcels", "sc.greenville.parcels",
                      "sc.horry.parcels", "sc.lancaster.parcels", "sc.spartanburg.parcels",
                      "sc.york.parcels"]},
    "SD": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["sd.lincoln.parcels", "sd.minnehaha.parcels", "sd.pennington.parcels"]},
    "TN": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["tn.davidson.parcels", "tn.hamilton.parcels", "tn.rutherford.parcels",
                      "tn.washington.parcels"]},
    "UT": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["ut.salt_lake.parcels", "ut.utah.parcels"]},
    "WA": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["wa.snohomish.parcels", "wa.spokane.parcels", "wa.thurston.parcels",
                      "wa.whatcom.parcels"]},
    "VA-COUNTIES": {"debtors": [], "courts": FEDERAL_COURTS,
                    "owners": ["va.albemarle.parcels", "va.alexandria_city.parcels",
                               "va.chesapeake_city.parcels", "va.chesterfield.parcels",
                               "va.fauquier.parcels", "va.franklin_city.parcels",
                               "va.gloucester.parcels", "va.isle_of_wight.parcels",
                               "va.james_city.parcels", "va.loudoun.parcels",
                               "va.lynchburg_city.parcels", "va.newport_news_city.parcels",
                               "va.norfolk_city.parcels", "va.portsmouth_city.parcels",
                               "va.prince_william.parcels", "va.spotsylvania.parcels",
                               "va.suffolk_city.parcels", "va.virginia_beach_city.parcels",
                               "va.williamsburg_city.parcels", "va.york.parcels"]},
    # Ohio's statewide Name field is a placeholder: county layers carry the owner names.
    "OH-COUNTIES": {"debtors": [], "courts": FEDERAL_COURTS,
                    "owners": ["oh.clermont.parcels", "oh.cuyahoga.parcels", "oh.fairfield.parcels",
                               "oh.franklin.parcels", "oh.greene.parcels", "oh.holmes.parcels",
                               "oh.lake.parcels", "oh.licking.parcels", "oh.lorain.parcels",
                               "oh.lucas.parcels", "oh.mahoning.parcels", "oh.pickaway.parcels",
                               "oh.stark.parcels", "oh.summit.parcels", "oh.tuscarawas.parcels",
                               "oh.wayne.parcels"]},
    "TX-COUNTIES": {"debtors": [], "courts": FEDERAL_COURTS,
                    "owners": ["tx.montgomery.parcels", "tx.williamson.parcels"]},
    "MD-COUNTIES": {"debtors": [], "courts": FEDERAL_COURTS,
                    "owners": ["md.anne_arundel.parcels", "md.baltimore_county.parcels",
                               "md.charles.parcels", "md.montgomery.parcels", "md.st_marys.parcels",
                               "md.washington.parcels", "md.wicomico.parcels"]},
    # NJ wage-theft lists name employers; Monmouth's parcel layer names owners (SR-1A is blank).
    "NJ-MONMOUTH": {"debtors": ["nj.dol.wage_watchlist", "nj.dol.wall"], "courts": FEDERAL_COURTS,
                    "owners": ["nj.monmouth.parcels"]},
    # Prince George's County MD owners (the county's property file; MD's statewide layer has no
    # owner names) against the national lists and the MD bankruptcy feeds.
    "MD-PRINCE-GEORGES": {"debtors": [], "owners": ["md.prince_georges.parcels"],
                          "courts": FEDERAL_COURTS},
    # Kent County DE owners against Delaware's top delinquent taxpayer lists.
    "DE": {"debtors": ["de.revenue.top_delinquent_personal",
                       "de.revenue.top_delinquent_business"],
           "owners": ["de.kent.parcels", "de.newcastle.parcels", "de.sussex.parcels"],
           "courts": FEDERAL_COURTS},
    # Maricopa: tax liens the annual sale did not sell (State-held), owed by the APN's owner.
    "AZ-MARICOPA": {"debtors": ["az.maricopa.unsold_tax_liens"],
                    "owners": ["az.maricopa.parcels"], "parcel_on_lien": True,
                    "courts": FEDERAL_COURTS},
    # Indiana statewide owners plus Marion County's (Indianapolis) mailing addresses.
    "IN": {"debtors": ["in.st_joseph.tax_sale"],
           "owners": ["in.statewide.parcels", "in.marion.parcels", "in.vanderburgh.parcels",
                      "in.lake.parcels"],
           "parcel_on_lien": True,
           "courts": FEDERAL_COURTS},
    # DC: prior-year real property tax owed by the lot's owner (OTR extract, keyed by SSL).
    "DC": {"debtors": ["dc.otr.delinquent_taxes"], "owners": ["dc.statewide.parcels"],
           "parcel_on_lien": True, "registries": ["dc.dlcp.business"], "courts": FEDERAL_COURTS},
}  # fmt: skip


# Every lake table a state's match reads (for pulling just these onto a fresh machine).
TABLES_READ = ("address", "party", "instrument", "instrument_party", "instrument_ref",
               "instrument_parcel", "owner_snapshot", "parcel", "parcel_assessment",
               "parcel_link", "business", "business_role", "judgment", "judgment_event",
               "case_party", "court_case", "docket_entry")  # fmt: skip


def bankruptcy_sources(state: str) -> list[str]:
    """The enabled bankruptcy-court RSS feeds of a run's state ('OH', 'WI-MILWAUKEE' -> WI)."""
    from equity.matching.bankruptcy import sources_for

    return sources_for(state.split("-", 1)[0])


def state_sources(state: str) -> list[str]:
    """Every source a state's match reads: debtors, owners, mortgages, links, registries."""
    spec = STATES[state]
    keys = ("debtors", "owners", "mortgages", "links", "registries", "deeds")
    return sorted({s for k in keys for s in spec.get(k) or []} | set(bankruptcy_sources(state))
                  | set(FEDERAL_DEBTS))  # fmt: skip


def missing_sources(state: str, lake: Path = LAKE) -> list[str]:
    """The sources a state's run reads that have no Parquet in the lake, or whose build has not
    finished (Parquet but no _counts.json, as a killed build leaves it). A run reads a missing
    source as empty or partial, so its counts drop without an error; the summary names them."""
    spec = STATES[state]
    wanted = sorted(set(state_sources(state)) | set(spec.get("courts") or [])
                    | set(spec.get("writs") or []))  # fmt: skip
    return [s for s in wanted if not any((lake / s).glob("*/*.parquet"))
            or not (lake / s / "_counts.json").exists()]  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.matching.resolve")
    ap.add_argument("--state", required=True, choices=sorted(STATES))
    ap.add_argument("--list-sources", action="store_true",
                    help="print the sources and tables this state reads, then stop")  # fmt: skip
    ap.add_argument("--lake", type=Path, default=LAKE)
    ap.add_argument("--out", type=Path, default=DERIVED, help="writes <out>/<state>/")
    ap.add_argument(
        "--require-all",
        action="store_true",
        help="refuse to run if a source the state reads is not in the lake",
    )
    args = ap.parse_args(argv)
    if args.list_sources:
        print(json.dumps({"sources": state_sources(args.state), "tables": list(TABLES_READ)}))
        return 0
    missing = missing_sources(args.state, args.lake)
    if missing:
        print(f"{args.state}: not in the lake, read as empty: {', '.join(missing)}",
              file=sys.stderr)  # fmt: skip
        if args.require_all:
            return 2
    spec = STATES[args.state]
    result = run(args.lake, args.out / args.state.lower(), [*spec["debtors"], *FEDERAL_DEBTS],
                 spec["owners"],
                 spec.get("mortgages"), spec.get("links"),
                 bool(spec.get("street_town")), bool(spec.get("parcel_on_lien")),
                 spec.get("courts"), spec.get("writs"), spec.get("registries"),
                 spec.get("debtor_doc_types"), bankruptcy_sources(args.state),
                 spec.get("deeds"))  # fmt: skip
    result["missing_sources"] = missing
    summary = args.out / args.state.lower() / "summary.json"
    summary.write_text(json.dumps(result, indent=2, default=str))
    json.dump(result, sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
