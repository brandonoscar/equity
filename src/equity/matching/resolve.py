"""Deterministic debtor -> property-owner matching over the lake (no fuzzy scores, no AI).

    uv run python -m equity.matching.resolve --state NY

Debtors are the debtor parties of lien and judgment instruments (warrants, docketed
judgments, lien filings). Owners are the owner parties of parcel snapshots. Both sides get the
same keys, computed in SQL so every match can be re-derived:

  name_key   the set of name words (upper case, letters and digits only, suffixes and
             filler words dropped, sorted): "SMITH JOHN A" and "JOHN A SMITH" -> "A JOHN SMITH".
             A person key needs at least two words; a last name alone never matches.
             "Person" rules cover every name not classified as an org at load (most
             loaders leave people as party_kind 'unknown').
  org_name   the organization name as normalized at load (equity.matching.orgs).
  addr_key   street line + ZIP 5 of a normalized address.
  town_key   street line + city, for states whose parcel data carries no owner ZIP (CT).

Rules, strongest first (a debtor-owner pair keeps its strongest rule):
  person_name_address   same person name_key, and the debtor's address equals the owner's
                        mailing address or the parcel's property address       -> auto
  org_name_address      same org_name and address                              -> auto
  org_name_zip          same org_name and ZIP                                  -> auto
  person_name_zip       same person name_key and ZIP                           -> review
With parcel_on_lien (liens recorded against a parcel id, e.g. Allegheny PINs), first; a lien
that names a parcel but no debtor gets the stand-in debtor "owner-of:<parcel_uid>":
  lien_names_parcel         the lien itself names the parcel (instrument_parcel), and that
                            parcel is in the owner source; no name match needed   -> auto
With court_sources (court judgments: case_party debtors of a judgment, e.g. the federal IDB,
whose parties carry a county but no address, and whose people are surnames only), also:
  org_name_county           same org_name, and the judgment's county is the parcel's county
                            -> review (no address to confirm it is the same business)
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
and a summary with counts only, printed and written to summary.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb

LAKE = Path("data/lake")
DERIVED = Path("data/derived")
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
)


def _glob(lake: Path, sources: list[str], table: str) -> str | None:
    paths = [str(p) for s in sources for p in sorted((lake / s / table).glob("*.parquet"))]
    if not paths:
        return None
    return "[" + ", ".join("'" + p.replace("'", "''") + "'" for p in paths) + "]"


V = "VARCHAR"
COLUMNS: dict[str, dict[str, str]] = {
    "address": {"address_id": V, "line1": V, "city": V, "zip5": V},
    "party": {"party_id": V, "raw_name": V, "party_kind": V, "org_name_norm": V,
              "address_id": V},
    "instrument_party": {"instrument_uid": V, "party_id": V, "role": V},
    "instrument": {"instrument_uid": V, "source_id": V, "doc_type": V, "doc_type_raw": V,
                   "recorded_on": "DATE",
                   "principal_amount": "DOUBLE"},
    "instrument_ref": {"from_uid": V, "to_uid": V, "ref_type": V},
    "instrument_parcel": {"instrument_uid": V, "parcel_uid": V},
    "parcel_link": {"from_parcel_uid": V, "to_parcel_uid": V, "link_type": V},
    "owner_snapshot": {"parcel_uid": V, "party_id": V},
    "parcel": {"parcel_uid": V, "situs_address_id": V},
    "case_party": {"case_uid": V, "party_id": V, "role": V},
    "judgment": {"judgment_uid": V, "case_uid": V, "source_id": V, "entered_on": "DATE",
                 "principal": "DOUBLE", "jurisdiction": V},
    "judgment_event": {"judgment_uid": V, "event": V},
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


def connect(
    lake: Path,
    debtor_sources: list[str],
    owner_sources: list[str],
    parcel_on_lien: bool = False,
    court_sources: list[str] | None = None,
) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    stop = ", ".join(f"'{w}'" for w in STOP)
    con.execute(f"""
        CREATE MACRO name_key(n) AS array_to_string(list_sort(list_distinct(list_filter(
            string_split(trim(regexp_replace(upper(coalesce(n, '')), '[^A-Z0-9]+', ' ', 'g')), ' '),
            lambda w: length(w) >= 1 AND w NOT IN ({stop})))), ' ');
        CREATE MACRO name_words(k) AS CASE WHEN k = '' THEN 0 ELSE len(string_split(k, ' ')) END;
    """)
    both = sorted(set(debtor_sources) | set(owner_sources))
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
    con.execute("""
        CREATE TEMP TABLE addr AS
        SELECT DISTINCT address_id,
               CASE WHEN line1 IS NOT NULL AND zip5 IS NOT NULL
                    THEN upper(line1) || '|' || zip5 END AS addr_key,
               CASE WHEN line1 IS NOT NULL AND city IS NOT NULL
                    THEN upper(line1) || '|' || upper(trim(city)) END AS town_key,
               zip5
        FROM addr_all;
        CREATE TEMP TABLE debtors AS
        SELECT DISTINCT p.party_id, p.raw_name, p.party_kind, p.org_name_norm,
               ip.instrument_uid, i.source_id, i.doc_type, i.recorded_on, i.principal_amount,
               EXISTS (SELECT 1 FROM d_ref r WHERE r.to_uid = i.instrument_uid
                       AND r.ref_type = 'releases')
                   OR coalesce(i.doc_type_raw, '') LIKE '%(satisfied)' AS released,
               name_key(p.raw_name) AS name_key, a.addr_key, a.town_key, a.zip5
        FROM d_ip ip
        JOIN d_party p ON p.party_id = ip.party_id
        JOIN d_inst i ON i.instrument_uid = ip.instrument_uid
        LEFT JOIN addr a ON a.address_id = p.address_id
        WHERE ip.role = 'debtor';
        ALTER TABLE debtors ADD COLUMN county VARCHAR;
        CREATE TEMP TABLE owners AS
        SELECT DISTINCT p.party_id, p.raw_name, p.party_kind, p.org_name_norm, s.parcel_uid,
               name_key(p.raw_name) AS name_key, ma.addr_key AS mail_key, ma.zip5 AS mail_zip,
               sa.addr_key AS situs_key, sa.zip5 AS situs_zip,
               ma.town_key AS mail_town, sa.town_key AS situs_town
        FROM o_snap s
        JOIN o_party p ON p.party_id = s.party_id
        LEFT JOIN o_parcel pc ON pc.parcel_uid = s.parcel_uid
        LEFT JOIN addr ma ON ma.address_id = p.address_id
        LEFT JOIN addr sa ON sa.address_id = pc.situs_address_id;
    """)
    if court_sources:
        _court_debtors(con, lake, court_sources)
    if parcel_on_lien:
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
                   '', NULL, NULL, NULL, NULL
            FROM d_inst i JOIN d_lot l ON l.instrument_uid = i.instrument_uid
            WHERE i.doc_type <> 'RELEASE' AND NOT EXISTS (
                SELECT 1 FROM d_ip ip WHERE ip.instrument_uid = i.instrument_uid
                  AND ip.role = 'debtor');
        """)
    return con


def _court_debtors(con: duckdb.DuckDBPyConnection, lake: Path, sources: list[str]) -> None:
    """Debtor parties of court judgments, in the owners' counties only (the judgment's
    jurisdiction is a county FIPS when the court record names one). A 'satisfied' judgment
    event releases it."""
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
               name_key(p.raw_name), a.addr_key, a.town_key, a.zip5, j.jurisdiction
        FROM c_judg j
        JOIN c_cp cp ON cp.case_uid = j.case_uid AND cp.role = 'debtor'
        JOIN c_party p ON p.party_id = cp.party_id
        LEFT JOIN addr a ON a.address_id = p.address_id
        WHERE j.jurisdiction IN (SELECT DISTINCT left(parcel_uid, 5) FROM o_parcel);
    """)


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
CREATE TEMP TABLE person_edges AS
SELECT a.party_id AS x, b.party_id AS y
FROM debtor_identity a JOIN debtor_identity b ON a.identity = b.identity
UNION
SELECT a.debtor_party_id, b.debtor_party_id
FROM matches a JOIN matches b ON a.owner_party_id = b.owner_party_id
WHERE a.decision = 'auto' AND b.decision = 'auto' AND a.owner_party_id IS NOT NULL;
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
       (SELECT count(*) FROM lots l WHERE l.person_id = j.person_id) AS parcels,
       (SELECT sum(v.value) FROM lots l JOIN parcel_value v ON v.parcel_uid = l.parcel_uid
        WHERE l.person_id = j.person_id) AS parcel_value
FROM j GROUP BY j.person_id;
"""
PEOPLE_PASSES = 6
PARCEL_ON_LIEN_SQL = """
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, NULL, l.parcel_uid, 'lien_names_parcel',
       l.parcel_uid
FROM debtors d JOIN d_lot l ON l.instrument_uid = d.instrument_uid
WHERE l.parcel_uid IN (SELECT parcel_uid FROM o_parcel)
  AND (NOT starts_with(d.party_id, 'owner-of:') OR d.party_id = 'owner-of:' || l.parcel_uid);
"""
STREET_TOWN_SQL = """
INSERT INTO candidates
SELECT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid, 'person_name_street_town',
       d.name_key
FROM debtors d JOIN owners o ON o.name_key = d.name_key
WHERE d.party_kind <> 'org' AND o.party_kind <> 'org' AND name_words(d.name_key) >= 2
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
    if courts:
        con.execute(COURT_COUNTY_SQL)
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
) -> dict[str, object]:
    from equity.matching import equity

    con = connect(lake, debtor_sources, owner_sources, parcel_on_lien, court_sources)
    match(con, street_town, parcel_on_lien, bool(court_sources))
    tables = ["matches", "debtor_summary", "people"]
    if mortgage_sources:
        equity.compute(con, lake, mortgage_sources, link_sources or [])
        tables.append("mortgage_status")
    out.mkdir(parents=True, exist_ok=True)
    for table in tables:
        con.execute(f"COPY {table} TO '{(out / (table + '.parquet')).as_posix()}' "
                    "(FORMAT PARQUET, COMPRESSION ZSTD)")  # fmt: skip
    result = summary(con)
    if mortgage_sources:
        result |= equity.summary(con)
    (out / "summary.json").write_text(json.dumps(result, indent=2, default=str))
    return result


STATES: dict[str, dict[str, Any]] = {
    "NY": {
        "debtors": ["ny.dtf.tax_warrants", "ny.dtf.child_support_warrants",
                    "ny.nyc.oath.judgments", "ny.nyc.hpd_litigation", "ny.nyc.acris.real"],
        "owners": ["ny.statewide.parcels"],
        "mortgages": ["ny.nyc.acris.real"],
        "links": ["ny.nyc.dof.condo_units"],
        "courts": ["us.fjc.idb.civil_judgments"],
    },
    # CT parcel data has no owner ZIP (Mailing_Zip is empty statewide): street + town instead.
    # Allegheny's parcel layer has no owner names, but its liens name the parcel (PIN).
    "PA-ALLEGHENY": {"debtors": ["pa.allegheny.tax_liens", "pa.allegheny.foreclosures"],
                     "owners": ["pa.allegheny.parcels"], "parcel_on_lien": True,
                     "courts": ["us.fjc.idb.civil_judgments"]},
    "CT": {"debtors": ["ct.sots.liens"], "owners": ["ct.statewide.parcels"], "street_town": True,
           "courts": ["us.fjc.idb.civil_judgments"]},
    # Detroit blight judgments name both the owner and the ticketed parcel (same parcel_id as
    # the Detroit assessor layer); Harris tax-suit judgments name the HCAD account; Washington
    # County sheriff sales list every parcel sold.
    "MI-DETROIT": {"debtors": ["mi.detroit.blight_judgments"], "owners": ["mi.wayne.parcels"],
                   "parcel_on_lien": True, "courts": ["us.fjc.idb.civil_judgments"]},
    "TX-HARRIS": {"debtors": ["tx.harris.tax_judgments"], "owners": ["tx.statewide.parcels"],
                  "parcel_on_lien": True, "courts": ["us.fjc.idb.civil_judgments"]},
    "PA-WASHINGTON": {"debtors": ["pa.washington.sheriff_sales"],
                      "owners": ["pa.washington.parcels"], "parcel_on_lien": True},
}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.matching.resolve")
    ap.add_argument("--state", required=True, choices=sorted(STATES))
    ap.add_argument("--lake", type=Path, default=LAKE)
    ap.add_argument("--out", type=Path, default=DERIVED, help="writes <out>/<state>/")
    args = ap.parse_args(argv)
    spec = STATES[args.state]
    result = run(args.lake, args.out / args.state.lower(), spec["debtors"], spec["owners"],
                 spec.get("mortgages"), spec.get("links"),
                 bool(spec.get("street_town")), bool(spec.get("parcel_on_lien")),
                 spec.get("courts"))  # fmt: skip
    json.dump(result, sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
