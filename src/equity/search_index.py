"""Search index: one local DuckDB file that indexes the lake for search and ad-hoc SQL.

(Not equity.lake's catalog, data/catalog.duckdb, which holds read_parquet views of the lake.)

The lake is ~450 sources of Parquet parts (local `data/lake/` or the object-storage bucket).
Searching it directly means opening thousands of files per query. The catalog copies only
the columns queries need into a few tables, one source at a time, and remembers each
source's version so a rebuild re-indexes only sources that changed:

    uv run python -m equity.search_index build                 # every built source in data/lake
    uv run python -m equity.search_index build --remote   # read Parquet from object storage
    uv run python -m equity.search_index build --remote --states OH NY --workers 8
    uv run python -m equity.search_index compact          # sort the lookup tables
    uv run python -m equity.search_index status

Tables (every row keeps its source_id; full rows stay in the lake under the same ids):
  sources          source_id, state, version (what was indexed), indexed_at, rows per table
  names            party names: party_id, raw_name, party_kind, name_key, address_id
  name_words       inverted index: word -> name_key, per source (search candidates)
  word_sounds      every indexed word with its Soundex code (typo-tolerant candidates)
  owners           party_id -> parcel_uid (owner_snapshot)
  parcels          parcel_uid, situs_address_id, land use, zoning
  parcel_values    latest assessment per parcel and source
  addresses        address_id -> line1, city, state, zip5, street_key (content-addressed)
  instruments      recorded documents and debt-list items (doc_type, date, amount)
  instrument_parcels  which parcel a document is recorded against (deed, mortgage, lien)
  instrument_parties, cases, case_parties, judgments, businesses, business_roles
  debtor_owner_candidates  v_debtor_owner_candidates stored by compact (fast to filter)

name_key is the matcher's key (equity.matching.resolve): upper-case name words, letters and
digits only, without JR/SR/AND/TR/..., de-duplicated and sorted. street_key is the matcher's
street_norm (USPS Publication 28 words). No models: every key is a fixed rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from equity.matching.resolve import STOP
from equity.matching.review import WORDS

DEFAULT_DB = Path("data/search_index.duckdb")
STORAGE_VERSION = "v1.5.0"
# Part of every source's version: bump it when the index layout changes, so the next build
# re-indexes every source into the new layout.
INDEX_VERSION = "4"
LAKE = Path("data/lake")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    source_id VARCHAR PRIMARY KEY, state VARCHAR, version VARCHAR NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL, rows VARCHAR);
CREATE TABLE IF NOT EXISTS names (
    source_id VARCHAR, party_id VARCHAR, raw_name VARCHAR, party_kind VARCHAR,
    org_form VARCHAR, name_key VARCHAR, jurisdiction VARCHAR, address_id VARCHAR,
    name_flag VARCHAR);
CREATE TABLE IF NOT EXISTS name_words (word VARCHAR, name_key VARCHAR, source_id VARCHAR);
CREATE TABLE IF NOT EXISTS word_sounds (word VARCHAR PRIMARY KEY, sound VARCHAR);
CREATE TABLE IF NOT EXISTS owners (
    source_id VARCHAR, party_id VARCHAR, parcel_uid VARCHAR, observed_on DATE);
CREATE TABLE IF NOT EXISTS owner_history (
    source_id VARCHAR, party_id VARCHAR, parcel_uid VARCHAR, observed_on DATE,
    superseded_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS parcels (
    source_id VARCHAR, parcel_uid VARCHAR, jurisdiction VARCHAR, parid_raw VARCHAR,
    situs_address_id VARCHAR, land_use_desc VARCHAR, zoning VARCHAR);
CREATE TABLE IF NOT EXISTS parcel_values (
    source_id VARCHAR, parcel_uid VARCHAR, tax_year INTEGER, appraised_total DOUBLE,
    assessed_value DOUBLE, homestead BOOLEAN);
CREATE TABLE IF NOT EXISTS value_history (
    source_id VARCHAR, parcel_uid VARCHAR, tax_year INTEGER, appraised_total DOUBLE,
    assessed_value DOUBLE, valid_from DATE);
CREATE TABLE IF NOT EXISTS addresses (
    address_id VARCHAR, line1 VARCHAR, city VARCHAR, state VARCHAR, zip5 VARCHAR,
    street_key VARCHAR);
CREATE TABLE IF NOT EXISTS instruments (
    source_id VARCHAR, instrument_uid VARCHAR, doc_type VARCHAR, doc_type_raw VARCHAR,
    recorded_on DATE, amount DOUBLE, consideration DOUBLE);
CREATE TABLE IF NOT EXISTS instrument_parcels (
    source_id VARCHAR, instrument_uid VARCHAR, parcel_uid VARCHAR, method VARCHAR);
CREATE TABLE IF NOT EXISTS instrument_refs (
    source_id VARCHAR, from_uid VARCHAR, to_uid VARCHAR, ref_type VARCHAR);
CREATE TABLE IF NOT EXISTS instrument_parties (
    source_id VARCHAR, instrument_uid VARCHAR, party_id VARCHAR, role VARCHAR);
CREATE TABLE IF NOT EXISTS cases (
    source_id VARCHAR, case_uid VARCHAR, court_id VARCHAR, case_number VARCHAR,
    case_type VARCHAR, nature_of_suit VARCHAR, filed_on DATE, closed_on DATE, status VARCHAR);
CREATE TABLE IF NOT EXISTS case_parties (
    source_id VARCHAR, case_uid VARCHAR, party_id VARCHAR, role VARCHAR);
CREATE TABLE IF NOT EXISTS judgments (
    source_id VARCHAR, case_uid VARCHAR, entered_on DATE, principal DOUBLE,
    judgment_type VARCHAR);
CREATE TABLE IF NOT EXISTS businesses (
    source_id VARCHAR, sos_id VARCHAR, name VARCHAR, name_key VARCHAR, org_form VARCHAR,
    status VARCHAR, formed_on DATE);
CREATE TABLE IF NOT EXISTS business_roles (
    source_id VARCHAR, sos_id VARCHAR, party_id VARCHAR, role VARCHAR, title VARCHAR);
-- The matcher's output per state (equity.matching.resolve, data/derived/<state>/). These core
-- columns are the ones search reads; a state's files may carry more (added on load).
CREATE TABLE IF NOT EXISTS matcher_runs (state VARCHAR PRIMARY KEY, version VARCHAR,
    indexed_at TIMESTAMPTZ, files VARCHAR);
CREATE TABLE IF NOT EXISTS m_matches (state VARCHAR, debtor_party_id VARCHAR,
    instrument_uid VARCHAR, owner_party_id VARCHAR, parcel_uid VARCHAR, rule_id VARCHAR,
    decision VARCHAR, key VARCHAR);
CREATE TABLE IF NOT EXISTS m_debtor_summary (state VARCHAR, debtor_party_id VARCHAR,
    debtor_name VARCHAR, liens BIGINT, open_amount DOUBLE, parcels BIGINT,
    parcel_value DOUBLE, has_auto BOOLEAN);
CREATE TABLE IF NOT EXISTS m_people (state VARCHAR, person_id VARCHAR, name VARCHAR,
    open_amount DOUBLE, parcels BIGINT, parcel_value DOUBLE);
CREATE TABLE IF NOT EXISTS m_person_of (state VARCHAR, party_id VARCHAR, person_id VARCHAR);
CREATE TABLE IF NOT EXISTS m_bankruptcy_flags (state VARCHAR, person_id VARCHAR,
    debtor_party_id VARCHAR, case_uid VARCHAR, court_id VARCHAR, chapter VARCHAR,
    status VARCHAR, decision VARCHAR);
CREATE TABLE IF NOT EXISTS m_transfer_flags (state VARCHAR);
CREATE TABLE IF NOT EXISTS m_mortgage_status (state VARCHAR);
CREATE TABLE IF NOT EXISTS nicknames (word VARCHAR, alt VARCHAR);
"""

# Ready-made joins for SQL clients. Name-only links between sources are candidates, not
# matches: the matcher (equity.matching.resolve) decides links with address and ZIP rules.
VIEWS = """
CREATE OR REPLACE VIEW v_party AS
SELECT n.source_id, n.party_id, n.source_id || ':' || n.party_id AS ref, n.raw_name,
       n.party_kind, n.name_key, s.state, a.line1, a.city, a.state AS addr_state, a.zip5
FROM names n JOIN sources s USING (source_id) LEFT JOIN addresses a USING (address_id);
CREATE OR REPLACE VIEW v_owner_parcels AS
SELECT o.source_id, o.party_id, o.source_id || ':' || o.party_id AS ref, n.raw_name,
       o.parcel_uid, o.observed_on, v.tax_year, v.appraised_total, v.assessed_value,
       v.homestead, p.land_use_desc, a.line1 AS situs_line1, a.city AS situs_city,
       a.zip5 AS situs_zip
FROM owners o JOIN names n USING (source_id, party_id)
LEFT JOIN parcels p USING (source_id, parcel_uid)
LEFT JOIN parcel_values v USING (source_id, parcel_uid)
LEFT JOIN addresses a ON a.address_id = p.situs_address_id;
CREATE OR REPLACE VIEW v_party_documents AS
SELECT ip.source_id, ip.party_id, ip.source_id || ':' || ip.party_id AS ref, n.raw_name,
       ip.role, i.instrument_uid, i.doc_type, i.doc_type_raw, i.recorded_on, i.amount
FROM instrument_parties ip JOIN instruments i USING (source_id, instrument_uid)
JOIN names n USING (source_id, party_id);
CREATE OR REPLACE VIEW v_party_cases AS
SELECT cp.source_id, cp.party_id, cp.source_id || ':' || cp.party_id AS ref, n.raw_name,
       cp.role, c.court_id, c.case_number, c.nature_of_suit, c.filed_on, c.closed_on,
       j.entered_on AS judgment_on, j.principal AS judgment_principal
FROM case_parties cp JOIN cases c USING (source_id, case_uid)
JOIN names n USING (source_id, party_id) LEFT JOIN judgments j USING (source_id, case_uid);
-- One row per name and state: a name on a debt (lien, judgment, lis pendens...) that also
-- owns parcels in the same state, with the debts and parcels behind it. Each side is
-- aggregated before the join, so a common name cannot multiply rows. Name-only: these are
-- leads to check against address and ZIP, not matches.
CREATE OR REPLACE VIEW v_debtor_owner_candidates AS
WITH debt AS (
    SELECT n.name_key, s.state, any_value(n.raw_name) AS debtor_name,
           count(*) AS debts, sum(i.amount) AS debt_amount,
           min(i.recorded_on) AS first_debt_on, max(i.recorded_on) AS last_debt_on,
           list(DISTINCT i.doc_type ORDER BY i.doc_type) AS doc_types,
           list(DISTINCT ip.source_id || ':' || ip.party_id)[1:20] AS debtor_refs,
           count(DISTINCT m.debtor_party_id) AS matcher_auto_debtors,
           list(DISTINCT m.rule_id) FILTER (WHERE m.rule_id IS NOT NULL) AS matcher_rules
    FROM instrument_parties ip
    JOIN instruments i USING (source_id, instrument_uid)
    JOIN names n USING (source_id, party_id)
    JOIN sources s USING (source_id)
    LEFT JOIN m_matches m ON m.debtor_party_id = ip.party_id AND m.decision = 'auto'
    WHERE i.doc_type IN ('JUDGMENT_LIEN', 'ABSTRACT_OF_JUDGMENT', 'EXECUTION', 'LIS_PENDENS',
                         'MECHANICS_LIEN', 'STATUTORY_LIEN', 'TAX_LIEN_STATE',
                         'TAX_LIEN_FEDERAL', 'COURT_ORDER')
      AND ip.role IN ('debtor', 'borrower', 'grantor')  -- the party that owes, not the creditor
      AND len(string_split(n.name_key, ' ')) >= 2 AND n.name_flag IS NULL
    GROUP BY n.name_key, s.state
), own AS (
    SELECT n.name_key, s.state, count(DISTINCT o.parcel_uid) AS parcels,
           sum(coalesce(v.appraised_total, v.assessed_value)) AS parcel_value,
           list(DISTINCT o.parcel_uid ORDER BY o.parcel_uid)[1:20] AS parcel_uids,
           list(DISTINCT o.source_id || ':' || o.party_id)[1:20] AS owner_refs
    FROM debt d
    JOIN names n ON n.name_key = d.name_key
    JOIN sources s ON s.source_id = n.source_id AND s.state = d.state
    JOIN owners o ON o.source_id = n.source_id AND o.party_id = n.party_id
    LEFT JOIN parcel_values v ON v.source_id = o.source_id AND v.parcel_uid = o.parcel_uid
    WHERE n.name_flag IS NULL
    GROUP BY n.name_key, s.state
)
SELECT d.state, d.debtor_name, d.name_key, d.debts, d.debt_amount, d.doc_types,
       d.first_debt_on, d.last_debt_on, o.parcels, o.parcel_value, d.debtor_refs,
       o.owner_refs, o.parcel_uids, d.matcher_auto_debtors, d.matcher_rules
FROM debt d JOIN own o USING (name_key, state);
-- Net equity per parcel where recorder data exists: the latest value minus mortgages and
-- deeds of trust recorded against the parcel that no recorded release points at. Only
-- counties with recorded mortgages or releases in the index get a row: elsewhere senior
-- debt is unknown, not zero.
CREATE OR REPLACE VIEW v_parcel_equity AS
WITH covered AS (
    SELECT DISTINCT left(x.parcel_uid, 5) AS fips
    FROM instrument_parcels x JOIN instruments i USING (source_id, instrument_uid)
    WHERE i.doc_type IN ('MORTGAGE', 'DEED_OF_TRUST', 'RELEASE')
), mort AS (
    SELECT x.parcel_uid, i.source_id, i.instrument_uid, i.amount, i.recorded_on
    FROM instrument_parcels x JOIN instruments i USING (source_id, instrument_uid)
    WHERE i.doc_type IN ('MORTGAGE', 'DEED_OF_TRUST')
), released AS (
    SELECT DISTINCT source_id, to_uid FROM instrument_refs
    WHERE ref_type IN ('releases', 'satisfies_judgment')
), open AS (
    SELECT m.* FROM mort m
    ANTI JOIN released r ON r.source_id = m.source_id AND r.to_uid = m.instrument_uid
), val AS (
    SELECT parcel_uid, max(coalesce(appraised_total, assessed_value)) AS value,
           max(tax_year) AS tax_year
    FROM parcel_values GROUP BY parcel_uid
), mstat AS (
    SELECT m.parcel_uid, count(*) AS mortgages,
           count(*) FILTER (WHERE o.instrument_uid IS NOT NULL) AS open_mortgages,
           sum(o.amount) AS open_principal,
           count(*) FILTER (WHERE o.instrument_uid IS NOT NULL AND o.amount IS NULL)
             AS open_without_amount,
           min(o.recorded_on) AS oldest_open_on
    FROM mort m LEFT JOIN open o USING (source_id, instrument_uid)
    GROUP BY m.parcel_uid
)
SELECT v.parcel_uid, v.value, v.tax_year, coalesce(s.mortgages, 0) AS mortgages,
       coalesce(s.open_mortgages, 0) AS open_mortgages, coalesce(s.open_principal, 0)
         AS open_principal, s.oldest_open_on,
       CASE WHEN coalesce(s.open_without_amount, 0) = 0
            THEN v.value - coalesce(s.open_principal, 0) END AS equity_est,
       coalesce(s.open_without_amount, 0) > 0 AS principal_unknown
FROM val v JOIN covered c ON c.fips = left(v.parcel_uid, 5)
LEFT JOIN mstat s USING (parcel_uid);
"""

# Catalog table -> (lake table, {catalog column: SQL over the lake row}, current): current=True
# keeps rows not superseded, False keeps only superseded ones (history).
# Columns a source's Parquet lacks (older builds) become NULL.
INDEXED: dict[str, tuple[str, dict[str, str], bool]] = {
    "names": (
        "party",
        {
            "source_id": "source_id",
            "party_id": "party_id",
            "raw_name": "raw_name",
            "party_kind": "party_kind",
            "org_form": "org_form",
            "name_key": "name_key(raw_name)",
            "jurisdiction": "jurisdiction",
            "address_id": "address_id",
            "name_flag": "name_flag(raw_name)",
        },
        True,
    ),
    "owner_history": (
        "owner_snapshot",
        {
            "source_id": "source_id",
            "party_id": "party_id",
            "parcel_uid": "parcel_uid",
            "observed_on": "observed_on",
            "superseded_at": "superseded_at",
        },
        False,  # superseded rows only: who the snapshots used to list
    ),
    "value_history": (
        "parcel_assessment",
        {
            "source_id": "source_id",
            "parcel_uid": "parcel_uid",
            "tax_year": "tax_year",
            "appraised_total": "appraised_total",
            "assessed_value": "assessed_value",
            "valid_from": "valid_from",
        },
        True,
    ),
    "instrument_refs": (
        "instrument_ref",
        {
            "source_id": "source_id",
            "from_uid": "from_uid",
            "to_uid": "to_uid",
            "ref_type": "ref_type",
        },
        True,
    ),
    "owners": (
        "owner_snapshot",
        {
            "source_id": "source_id",
            "party_id": "party_id",
            "parcel_uid": "parcel_uid",
            "observed_on": "observed_on",
        },
        True,
    ),
    "parcels": (
        "parcel",
        {
            "source_id": "source_id",
            "parcel_uid": "parcel_uid",
            "jurisdiction": "jurisdiction",
            "parid_raw": "parid_raw",
            "situs_address_id": "situs_address_id",
            "land_use_desc": "coalesce(land_use_desc, land_use_code)",
            "zoning": "zoning",
        },
        True,
    ),
    "instruments": (
        "instrument",
        {
            "source_id": "source_id",
            "instrument_uid": "instrument_uid",
            "doc_type": "doc_type",
            "doc_type_raw": "doc_type_raw",
            "recorded_on": "recorded_on",
            "amount": "coalesce(principal_amount, max_secured_amount)",
            "consideration": "consideration",
        },
        True,
    ),
    "instrument_parcels": (
        "instrument_parcel",
        {
            "source_id": "source_id",
            "instrument_uid": "instrument_uid",
            "parcel_uid": "parcel_uid",
            "method": "method",
        },
        True,
    ),
    "instrument_parties": (
        "instrument_party",
        {
            "source_id": "source_id",
            "instrument_uid": "instrument_uid",
            "party_id": "party_id",
            "role": "role",
        },
        True,
    ),
    "cases": (
        "court_case",
        {
            "source_id": "source_id",
            "case_uid": "case_uid",
            "court_id": "court_id",
            "case_number": "case_number_raw",
            "case_type": "case_type",
            "nature_of_suit": "nature_of_suit",
            "filed_on": "filed_on",
            "closed_on": "closed_on",
            "status": "status",
        },
        True,
    ),
    "case_parties": (
        "case_party",
        {"source_id": "source_id", "case_uid": "case_uid", "party_id": "party_id", "role": "role"},
        True,
    ),
    "judgments": (
        "judgment",
        {
            "source_id": "source_id",
            "case_uid": "case_uid",
            "entered_on": "entered_on",
            "principal": "principal",
            "judgment_type": "judgment_type",
        },
        True,
    ),
    "businesses": (
        "business",
        {
            "source_id": "source_id",
            "sos_id": "sos_id",
            "name": "name",
            "name_key": "name_key(name)",
            "org_form": "org_form",
            "status": "status",
            "formed_on": "formed_on",
        },
        True,
    ),
    "business_roles": (
        "business_role",
        {
            "source_id": "source_id",
            "sos_id": "sos_id",
            "party_id": "party_id",
            "role": "role",
            "title": "title",
        },
        True,
    ),
}
PER_SOURCE = (*INDEXED, "name_words", "parcel_values")
# compact() sorts each lookup table by the key search filters on, so DuckDB's per-row-group
# min/max (zone maps) skips nearly every block for a short list of keys.
SORT_KEYS = (("names", "name_key"), ("name_words", "word"), ("owners", "party_id"),
             ("instrument_parties", "party_id"), ("case_parties", "party_id"),
             ("business_roles", "party_id"), ("businesses", "name_key"),
             ("parcels", "parcel_uid"), ("parcel_values", "parcel_uid"),
             ("instruments", "instrument_uid"),
    ("instrument_parcels", "parcel_uid"),
    ("instrument_refs", "to_uid"),
    ("owner_history", "parcel_uid"),
    ("value_history", "parcel_uid"), ("cases", "case_uid"),
             ("judgments", "case_uid"), ("addresses", "address_id"))  # fmt: skip
LAKE_TABLES = ("party", "owner_snapshot", "parcel", "parcel_assessment", "address", "instrument",
               "instrument_party",
    "instrument_parcel",
    "instrument_ref", "court_case", "case_party", "judgment", "business",
               "business_role")  # fmt: skip


def connect(db: Path | str = DEFAULT_DB, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the catalog with the name and street macros the tables are keyed by."""
    if not read_only and isinstance(db, Path):
        db.parent.mkdir(parents=True, exist_ok=True)
        if not db.exists():
            # Written in an older storage format so readers on an older DuckDB (the MCP
            # server pins its own) can open it; DuckDB keeps a file's format on later writes.
            new = duckdb.connect()
            new.execute(f"ATTACH '{db}' AS cat (STORAGE_VERSION '{STORAGE_VERSION}')")
            new.close()
    con = duckdb.connect(str(db), read_only=read_only)
    # Saved in the file when writable, so SQL clients (the MCP server) can call them too.
    kind = "TEMP MACRO" if read_only else "MACRO"
    stop = ", ".join(f"'{w}'" for w in STOP)
    con.execute(f"""
        CREATE OR REPLACE {kind} name_key(n) AS array_to_string(list_sort(list_distinct(
            list_filter(string_split(trim(regexp_replace(upper(coalesce(n, '')),
                '[^A-Z0-9]+', ' ', 'g')), ' '),
            lambda w: length(w) >= 1 AND w NOT IN ({stop})))), ' ');
    """)
    # The matcher's street_norm (equity.matching.review.street_macro), as a TEMP macro so a
    # read-only catalog can use it too.
    pairs = ", ".join(f"'{k}': '{v}'" for k, v in sorted(WORDS.items()))
    con.execute(f"""
        CREATE OR REPLACE {kind} street_norm(s) AS array_to_string(list_transform(
            list_filter(string_split(trim(regexp_replace(upper(coalesce(s, '')),
                '[^A-Z0-9 ]+', ' ', 'g')), ' '), lambda w: w <> ''),
            lambda w: coalesce(MAP {{{pairs}}}[w], w)), ' ');
    """)
    con.execute(f"""
        -- American Soundex (first letter + 3 digits; H and W do not separate equal codes).
        CREATE OR REPLACE {kind} sx_codes(sx_w) AS list_transform(string_split(sx_w, ''),
            lambda sx_ch: CASE WHEN sx_ch IN ('B', 'F', 'P', 'V') THEN '1'
                WHEN sx_ch IN ('C', 'G', 'J', 'K', 'Q', 'S', 'X', 'Z') THEN '2'
                WHEN sx_ch IN ('D', 'T') THEN '3' WHEN sx_ch = 'L' THEN '4'
                WHEN sx_ch IN ('M', 'N') THEN '5' WHEN sx_ch = 'R' THEN '6'
                WHEN sx_ch IN ('H', 'W') THEN 'h' ELSE '0' END);
        -- Lambda variables are named sx_* so the macros can be used inside other lambdas.
        CREATE OR REPLACE {kind} sx_noh(sx_c) AS
            list_filter(sx_c, lambda sx_a, sx_i: sx_i = 1 OR sx_a <> 'h');
        CREATE OR REPLACE {kind} sx_collapse(sx_c) AS
            list_filter(sx_c, lambda sx_b, sx_j: sx_j = 1 OR sx_b <> sx_c[sx_j - 1]);
        CREATE OR REPLACE {kind} soundex(sx_w) AS
            CASE WHEN regexp_full_match(coalesce(sx_w, ''), '[A-Z]+')
            THEN sx_w[1] || left(rpad(array_to_string(list_filter(
                sx_collapse(sx_noh(sx_codes(sx_w)))[2:], lambda sx_d: sx_d NOT IN ('0', 'h')),
                ''), 3, '0'), 3)
            ELSE sx_w END;
    """)
    con.execute(f"""
        -- Why a printed name cannot be a lead (NULL when it can): see NAME_FLAGS.
        CREATE OR REPLACE {kind} name_flag(nf_n) AS CASE
            WHEN NOT regexp_matches(name_key(nf_n), '[A-Z]{{2}}') THEN 'placeholder'
            WHEN regexp_matches(upper(nf_n), '{WITHHELD}') THEN 'withheld'
            WHEN regexp_matches(upper(nf_n), '{CONTINUED}') THEN 'continued'
            WHEN regexp_matches(upper(nf_n), '{GOVERNMENT}') THEN 'government'
            WHEN len(string_split(name_key(nf_n), ' ')) = 1 THEN 'one_word'
        END;
    """)
    if not read_only:
        _migrate(con)
        con.execute(SCHEMA)
        con.execute("ALTER TABLE names ADD COLUMN IF NOT EXISTS name_flag VARCHAR")
        _load_nicknames(con)
        con.execute(VIEWS)
    return con


# Name flags (fixed patterns on the printed name, upper-cased). A flagged name stays in the
# index and in search results (ranked after clean names) but is never a lead.
#   placeholder  no two-letter word ("39005 | A01-001-0-0001-00": Ohio's statewide view)
#   withheld     the source withholds or lacks the owner ("Name withheld by request.")
#   continued    a name split across records ("... INC (CONT'D #1 OF #4)")
#   government   a public body: usually the creditor, or tax-exempt property
#   one_word     a single word: a surname alone is never a match
WITHHELD = ("WITHHELD|CONFIDENTIAL|REDACTED|NOT AVAILABLE|UNKNOWN OWNER|OWNER UNKNOWN|"
            "CURRENT OWNER|\\bOCCUPANT\\b|NAME NOT|NO NAME")  # fmt: skip
CONTINUED = "CONT''?D\\b|\\bCONTINUED\\b|#\\s*[0-9]+\\s+OF\\s+#?\\s*[0-9]+"
GOVERNMENT = (
    "^(THE )?(CITY|COUNTY|STATE|VILLAGE|TOWN|TOWNSHIP|PARISH|BOROUGH|COMMONWEALTH) OF\\b|"
    "\\bTREASURER\\b|\\bUNITED STATES\\b|\\bHOUSING AUTHORITY\\b|\\bLAND BANK\\b|"
    "\\bBOARD OF (EDUCATION|COMMISSIONERS|TRUSTEES)\\b|\\bSCHOOL DISTRICT\\b|"
    "\\bDEPARTMENT OF\\b|\\bREDEVELOPMENT AUTHORITY\\b|\\bPORT AUTHORITY\\b"
)  # fmt: skip


def _load_nicknames(con: duckdb.DuckDBPyConnection) -> None:
    """Fill the nicknames table once from equity/data/nicknames.csv (see equity/data/README):
    every pair of given names that share a canonical name, both ways (BOB <-> ROBERT, and
    BOB <-> ROB through ROBERT), upper case."""
    if con.execute("SELECT count(*) FROM nicknames").fetchone() != (0,):
        return
    from importlib import resources

    path = resources.files("equity.data").joinpath("nicknames.csv")
    with resources.as_file(path) as csv:
        con.execute("""
            INSERT INTO nicknames
            WITH t AS (SELECT upper(name1) AS canon, upper(name2) AS nick
                       FROM read_csv(?, header = true) WHERE relationship = 'has_nickname'),
            groups AS (SELECT canon, canon AS word FROM t UNION SELECT canon, nick FROM t)
            SELECT DISTINCT a.word, b.word FROM groups a JOIN groups b USING (canon)
            WHERE a.word <> b.word AND regexp_full_match(a.word, '[A-Z]+')
              AND regexp_full_match(b.word, '[A-Z]+')
        """, [str(csv)])  # fmt: skip


def _migrate(con: duckdb.DuckDBPyConnection) -> None:
    """Catalogs built before name_words held name_keys: rebuild it (and word_sounds) from
    the indexed names, so a catalog never needs a full re-index for a layout change."""
    cols = {r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'name_words'"
    ).fetchall()}  # fmt: skip
    if "party_id" not in cols:
        return
    con.execute("""
        CREATE OR REPLACE TABLE name_words AS
        SELECT DISTINCT unnest(string_split(name_key, ' ')) AS word, name_key, source_id
        FROM names WHERE name_key <> ''
        UNION
        SELECT DISTINCT unnest(string_split(name_key, ' ')), name_key, source_id
        FROM businesses WHERE name_key <> ''
    """)
    con.execute("CREATE TABLE IF NOT EXISTS word_sounds (word VARCHAR PRIMARY KEY, sound VARCHAR)")
    con.execute("INSERT OR IGNORE INTO word_sounds "
                "SELECT DISTINCT word, soundex(word) FROM name_words")  # fmt: skip


class FileSource:
    """Parquet parts of a local lake directory (data/lake/<source>/<table>/*.parquet)."""

    def __init__(self, lake: Path = LAKE) -> None:
        self.lake = lake

    def sources(self, only: Iterable[str] | None = None) -> list[str]:
        ids = sorted(p.parent.name for p in self.lake.glob("*/_counts.json"))
        return ids if only is None else [s for s in ids if s in set(only)]

    def version(self, source_id: str) -> str:
        src = self.lake / source_id
        h = hashlib.sha256(INDEX_VERSION.encode() + (src / "_counts.json").read_bytes())
        for m in sorted((src / "_parts").glob("*.json")):
            h.update(m.name.encode() + m.read_bytes())
        return h.hexdigest()[:16]

    def files(self, source_id: str, table: str) -> list[str]:
        return sorted(str(p) for p in (self.lake / source_id / table).glob("*.parquet"))

    # The matcher's output lives beside the lake: data/derived/<state>/<file>.parquet.
    def derived(self) -> dict[str, dict[str, str]]:
        """{state: {file stem: path}} for every state with matcher output."""
        root = self.lake.parent / "derived"
        out: dict[str, dict[str, str]] = {}
        for d in sorted(p for p in root.glob("*") if p.is_dir() and len(p.name) <= 3):
            files = {f.stem: str(f) for f in sorted(d.glob("*.parquet")) if f.stem in MATCHER}
            if files:
                out[d.name.upper()] = files
        return out

    def derived_version(self, state: str, files: dict[str, str]) -> str:
        h = hashlib.sha256(INDEX_VERSION.encode())
        for stem, path in sorted(files.items()):
            st = Path(path).stat()
            h.update(f"{stem}:{st.st_size}:{st.st_mtime_ns}".encode())
        return h.hexdigest()[:16]


class RemoteSource:
    """Parquet parts in the object-storage bucket, read over HTTPS (equity.lake_sync.Store)."""

    def __init__(self, store: Any) -> None:
        self.store = store
        self._bundles: dict[str, str] = {}

    def sources(self, only: Iterable[str] | None = None) -> list[str]:
        """Built sources (a bundle with _counts.json). Bundles are probed in parallel with a
        single retry: a folder without one (unfinished, or not a source) is skipped."""
        from concurrent.futures import ThreadPoolExecutor
        from dataclasses import replace

        if only is None:
            _, dirs = self.store.list_dir("")
        else:
            dirs = list(only)
        probe = replace(self.store, retries=1, log=lambda _m: None)

        def one(sid: str) -> tuple[str, str | None]:
            try:
                return sid, probe.download(f"{sid}/_state.json").decode()
            except Exception:
                return sid, None

        with ThreadPoolExecutor(16) as ex:
            found = dict(ex.map(one, sorted(set(dirs))))
        out = []
        for sid, text in sorted(found.items()):
            if text is not None and "_counts.json" in json.loads(text):
                self._bundles[sid] = text
                out.append(sid)
        return out

    def version(self, source_id: str) -> str:
        text = self._bundles.get(source_id)
        if text is None:
            text = self.store.download(f"{source_id}/_state.json").decode()
        return hashlib.sha256(INDEX_VERSION.encode() + text.encode()).hexdigest()[:16]

    def files(self, source_id: str, table: str) -> list[str]:
        files, _ = self.store.list_dir(f"{source_id}/{table}/")
        base = f"{self.store.base_url}/object/{self.store.bucket}/{source_id}/{table}"
        return [f"{base}/{n}" for n in sorted(files) if n.endswith(".parquet")]

    def derived(self) -> dict[str, dict[str, str]]:
        """{state: {file stem: url}} for every state whose matcher output is in the bucket."""
        _, states = self.store.list_dir("derived/")
        out: dict[str, dict[str, str]] = {}
        self._derived_sizes: dict[str, dict[str, int]] = {}
        for st in sorted(x for x in states if len(x) <= 3):
            listed, _ = self.store.list_dir(f"derived/{st}/")
            base = f"{self.store.base_url}/object/{self.store.bucket}/derived/{st}"
            files = {n[: -len(".parquet")]: f"{base}/{n}" for n in sorted(listed)
                     if n.endswith(".parquet") and n[: -len(".parquet")] in MATCHER}  # fmt: skip
            if files:
                out[st.upper()] = files
                self._derived_sizes[st.upper()] = {n: int(v) for n, v in listed.items()}
        return out

    def derived_version(self, state: str, files: dict[str, str]) -> str:
        sizes = getattr(self, "_derived_sizes", {}).get(state, {})
        text = INDEX_VERSION + json.dumps(sorted(sizes.items()))
        return hashlib.sha256(text.encode()).hexdigest()[:16]


# Matcher output files loaded per state as m_<stem> tables (equity.matching.resolve,
# .bankruptcy, .transfers, .equity). Columns beyond the core ones in SCHEMA are added on load.
MATCHER = ("matches", "debtor_summary", "people", "person_of", "bankruptcy_flags",
           "transfer_flags", "mortgage_status")  # fmt: skip


def index_matcher(
    con: duckdb.DuckDBPyConnection, source: Any, force: bool = False, log: Any = print
) -> list[str]:
    """Load each state's matcher output into m_* tables (replacing that state's rows) when
    its files changed. Returns the states loaded."""
    known = dict(con.execute("SELECT state, version FROM matcher_runs").fetchall())
    done = []
    for state, files in source.derived().items():
        version = source.derived_version(state, files)
        if not force and known.get(state) == version:
            continue
        con.execute("BEGIN TRANSACTION")
        try:
            counts = {}
            for stem in MATCHER:
                table = f"m_{stem}"
                con.execute(f"DELETE FROM {table} WHERE state = ?", [state])  # noqa: S608
                if stem not in files:
                    continue
                have = {r[0] for r in con.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                    [table]).fetchall()}  # fmt: skip
                desc = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [files[stem]]
                                   ).fetchall()  # fmt: skip
                for name, typ, *_ in desc:
                    if name not in have:
                        con.execute(f'ALTER TABLE {table} ADD COLUMN "{name}" {typ}')
                con.execute(f"INSERT INTO {table} BY NAME SELECT ? AS state, * "  # noqa: S608
                            "FROM read_parquet(?)", [state, files[stem]])  # fmt: skip
                counts[stem] = int(con.execute(
                    f"SELECT count(*) FROM {table} WHERE state = ?", [state]  # noqa: S608
                ).fetchone()[0])  # type: ignore[index]  # fmt: skip
            con.execute("DELETE FROM matcher_runs WHERE state = ?", [state])
            con.execute("INSERT INTO matcher_runs VALUES (?, ?, ?, ?)",
                        [state, version, datetime.now(UTC), json.dumps(counts)])  # fmt: skip
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        done.append(state)
        log(f"matcher {state}: " + ", ".join(f"{k} {v:,}" for k, v in counts.items()))
    return done


def _state_of(source_id: str) -> str:
    head = source_id.split(".")
    if head[0] == "us" and len(head) > 2 and head[2] == "rss":
        return head[1][:2].upper()
    return head[0].upper()


def _columns(con: duckdb.DuckDBPyConnection, files: list[str]) -> set[str]:
    rows = con.execute(
        "SELECT name FROM parquet_schema(?) WHERE name <> 'duckdb_schema'", [files]
    ).fetchall()
    return {str(r[0]) for r in rows}


def _expr(sql: str, have: set[str]) -> str:
    """The column SQL for this source's Parquet: a plain column or name_key(column) becomes
    NULL when the column is missing; coalesce(a, b) keeps the columns that exist."""
    if sql.startswith("coalesce("):
        args = [a.strip() for a in sql[len("coalesce(") : -1].split(",")]
        kept = [a for a in args if a in have]
        return f"coalesce({', '.join(kept)})" if kept else "NULL"
    m = re.fullmatch(r"(name_key|name_flag)\((\w+)\)", sql)
    col = m.group(2) if m else sql
    return sql if col in have else "NULL"


def index_source(con: duckdb.DuckDBPyConnection, source: Any, source_id: str) -> dict[str, int]:
    """Replace one source's rows in every catalog table. Returns rows written per table."""
    for t in PER_SOURCE:
        con.execute(f"DELETE FROM {t} WHERE source_id = ?", [source_id])  # noqa: S608
    counts: dict[str, int] = {}
    for table, (lake_table, cols, current) in INDEXED.items():
        files = source.files(source_id, lake_table)
        if not files:
            continue
        have = _columns(con, files)
        select = ", ".join(_expr(sql, have) for sql in cols.values())
        if "superseded_at" not in have:
            if not current:
                continue  # no history kept by this source
            where = ""
        else:
            where = f" WHERE superseded_at IS {'' if current else 'NOT '}NULL"
        con.execute(f"INSERT INTO {table} ({', '.join(cols)}) SELECT {select} "  # noqa: S608
                    f"FROM read_parquet(?, union_by_name = true){where}", [files])  # fmt: skip
        counts[table] = int(con.execute(
            f"SELECT count(*) FROM {table} WHERE source_id = ?", [source_id]  # noqa: S608
        ).fetchone()[0])  # type: ignore[index]  # fmt: skip
    files = source.files(source_id, "parcel_assessment")
    if files:
        have = _columns(con, files)
        home = "homestead" if "homestead" in have else "NULL"
        where = "WHERE superseded_at IS NULL" if "superseded_at" in have else ""
        con.execute(f"""
            INSERT INTO parcel_values
            SELECT source_id, parcel_uid, tax_year, appraised_total, assessed_value, {home}
            FROM read_parquet(?, union_by_name = true) {where}
            QUALIFY row_number() OVER (PARTITION BY parcel_uid
                                       ORDER BY tax_year DESC, valid_from DESC) = 1
        """, [files])  # noqa: S608  # fmt: skip
        counts["parcel_values"] = int(con.execute(
            "SELECT count(*) FROM parcel_values WHERE source_id = ?", [source_id]
        ).fetchone()[0])  # type: ignore[index]  # fmt: skip
    files = source.files(source_id, "address")
    if files:
        con.execute("""
            INSERT INTO addresses
            SELECT r.address_id, any_value(r.line1), any_value(r.city), any_value(r.state),
                   any_value(r.zip5), any_value(street_norm(r.line1))
            FROM read_parquet(?, union_by_name = true) r
            ANTI JOIN addresses x ON x.address_id = r.address_id
            GROUP BY r.address_id
        """, [files])  # fmt: skip
    con.execute("""
        INSERT INTO name_words
        SELECT DISTINCT word, name_key, source_id FROM (
            SELECT unnest(string_split(name_key, ' ')) AS word, name_key, source_id
            FROM (SELECT name_key, source_id FROM names WHERE source_id = ? AND name_key <> ''
                  UNION
                  SELECT name_key, source_id FROM businesses
                  WHERE source_id = ? AND name_key <> ''))
        -- Initials find nothing useful on their own; a name with no 2-letter word is a
        -- placeholder (Ohio's statewide view: "39005 | A01-001-0-0001-00"), not a name.
        WHERE length(word) >= 2 AND regexp_matches(name_key, '[A-Z]{2}')
          AND name_key NOT IN (SELECT name_key FROM names WHERE source_id = ?
                               AND name_flag IN ('placeholder', 'withheld'))
    """, [source_id, source_id, source_id])  # fmt: skip
    con.execute("""
        INSERT OR IGNORE INTO word_sounds
        SELECT DISTINCT word, soundex(word) FROM name_words WHERE source_id = ?
    """, [source_id])  # fmt: skip
    return counts


# Lake columns the index reads, per lake table (extract() fetches only these).
NEEDED: dict[str, set[str]] = {
    "party": {"source_id", "party_id", "raw_name", "party_kind", "org_form", "jurisdiction",
              "address_id", "superseded_at"},
    "owner_snapshot": {"source_id", "party_id", "parcel_uid", "observed_on", "superseded_at"},
    "parcel": {"source_id", "parcel_uid", "jurisdiction", "parid_raw", "situs_address_id",
               "land_use_desc", "land_use_code", "zoning", "superseded_at"},
    "parcel_assessment": {"source_id", "parcel_uid", "tax_year", "appraised_total",
                          "assessed_value", "homestead", "valid_from", "superseded_at"},
    "address": {"address_id", "line1", "city", "state", "zip5"},
    "instrument": {"source_id", "instrument_uid", "doc_type", "doc_type_raw", "recorded_on",
                   "principal_amount", "max_secured_amount", "consideration", "superseded_at"},
    "instrument_party": {"source_id", "instrument_uid", "party_id", "role", "superseded_at"},
    "instrument_parcel": {"source_id", "instrument_uid", "parcel_uid", "method", "superseded_at"},
    "instrument_ref": {"source_id", "from_uid", "to_uid", "ref_type", "superseded_at"},
    "court_case": {"source_id", "case_uid", "court_id", "case_number_raw", "case_type",
                   "nature_of_suit", "filed_on", "closed_on", "status", "superseded_at"},
    "case_party": {"source_id", "case_uid", "party_id", "role", "superseded_at"},
    "judgment": {"source_id", "case_uid", "entered_on", "principal", "judgment_type",
                 "superseded_at"},
    "business": {"source_id", "sos_id", "name", "org_form", "status", "formed_on",
                 "superseded_at"},
    "business_role": {"source_id", "sos_id", "party_id", "role", "title", "superseded_at"},
}  # fmt: skip


def extract(source: Any, source_id: str, out: Path, remote: bool = False) -> FileSource:
    """Copy one source's needed lake columns to local Parquet under out/<source_id>/, with
    its own connection, so many sources can be fetched at once while one writer indexes."""
    con = duckdb.connect()
    if remote:
        con.execute("LOAD httpfs")
    dest = out / source_id
    for table in LAKE_TABLES:
        files = source.files(source_id, table)
        if not files:
            continue
        cols = sorted(NEEDED[table] & _columns(con, files))
        (dest / table).mkdir(parents=True, exist_ok=True)
        part = dest / table / "00000.parquet"
        con.execute(f"COPY (SELECT {', '.join(cols)} FROM read_parquet(?, union_by_name = true)) "  # noqa: S608
                    f"TO '{part}' (FORMAT parquet, COMPRESSION zstd)", [files])  # fmt: skip
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "_counts.json").write_text("{}")
    con.close()
    return FileSource(out)


def build(
    con: duckdb.DuckDBPyConnection,
    source: Any,
    only: Iterable[str] | None = None,
    states: Iterable[str] | None = None,
    force: bool = False,
    log: Any = print,
    workers: int = 1,
    scratch: Path | None = None,
    remote: bool = False,
) -> list[str]:
    """Index every source whose version changed since it was last indexed. Sources that no
    longer exist in the lake are dropped. Returns the ids (re)indexed.

    With workers > 1, sources are first fetched in parallel into scratch (local Parquet of
    the needed columns, deleted once indexed) and then indexed one at a time."""
    import shutil
    from concurrent.futures import ThreadPoolExecutor, as_completed

    want_states = {s.upper() for s in states} if states else None
    available = source.sources(only)
    ids = [s for s in available if want_states is None or _state_of(s) in want_states]
    known = dict(con.execute("SELECT source_id, version FROM sources").fetchall())
    if only is None and want_states is None:
        for gone in sorted(set(known) - set(available)):
            for t in PER_SOURCE:
                con.execute(f"DELETE FROM {t} WHERE source_id = ?", [gone])  # noqa: S608
            con.execute("DELETE FROM sources WHERE source_id = ?", [gone])
            log(f"dropped {gone} (no longer in the lake)")
    todo = [(sid, v) for sid in ids
            if (v := source.version(sid)) and (force or known.get(sid) != v)]  # fmt: skip
    done: list[str] = []

    def index(sid: str, version: str, src: Any) -> None:
        con.execute("BEGIN TRANSACTION")
        try:
            counts = index_source(con, src, sid)
            con.execute("DELETE FROM sources WHERE source_id = ?", [sid])
            con.execute("INSERT INTO sources VALUES (?, ?, ?, ?, ?)",
                        [sid, _state_of(sid), version, datetime.now(UTC),
                         json.dumps(counts, sort_keys=True)])  # fmt: skip
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        done.append(sid)
        log(f"indexed {sid}: " + ", ".join(f"{k} {v:,}" for k, v in sorted(counts.items())))

    if workers <= 1 or not todo:
        for sid, version in todo:
            index(sid, version, source)
        return done
    tmp = scratch or Path("data/work/search_index")
    queue = list(todo)
    ahead = 2 * workers  # fetched-but-not-indexed sources kept on disk at most
    with ThreadPoolExecutor(workers) as ex:
        futures: dict[Any, tuple[str, str]] = {}
        while queue or futures:
            while queue and len(futures) < ahead:
                sid, v = queue.pop(0)
                futures[ex.submit(extract, source, sid, tmp, remote)] = (sid, v)
            fut = next(as_completed(futures))
            sid, version = futures.pop(fut)
            index(sid, version, fut.result())
            shutil.rmtree(tmp / sid, ignore_errors=True)
    done.sort()
    return done


def compact(con: duckdb.DuckDBPyConnection, only: Iterable[str] | None = None) -> None:
    """Rewrite the search tables sorted by their lookup keys, so DuckDB's per-block min/max
    skips almost everything on an exact name or word lookup. `only` re-sorts just those
    tables (and skips the rest of the work)."""
    if only is not None:
        keys = dict(SORT_KEYS)
        for table in only:
            con.execute(f"CREATE OR REPLACE TABLE {table} AS "  # noqa: S608
                        f"SELECT * FROM {table} ORDER BY {keys[table]}")  # fmt: skip
            con.execute("CHECKPOINT")
        return
    for table, key in SORT_KEYS:
        con.execute(f"CREATE OR REPLACE TABLE {table} AS "  # noqa: S608
                    f"SELECT * FROM {table} ORDER BY {key}")  # fmt: skip
        # Free the old copy's blocks now, so peak disk is one table, not all of them.
        con.execute("CHECKPOINT")
    # word_sounds keeps its primary key (INSERT OR IGNORE relies on it).
    con.execute("CREATE OR REPLACE TABLE _ws (word VARCHAR PRIMARY KEY, sound VARCHAR)")
    con.execute("INSERT INTO _ws SELECT * FROM word_sounds ORDER BY sound, word")
    con.execute("DROP TABLE word_sounds")
    con.execute("ALTER TABLE _ws RENAME TO word_sounds")
    # The leads view, stored: computing it takes seconds, too slow for an MCP client.
    con.execute("CREATE OR REPLACE TABLE debtor_owner_candidates AS "
                "SELECT * FROM v_debtor_owner_candidates ORDER BY state, name_key")  # fmt: skip
    con.execute("CREATE OR REPLACE TABLE parcel_equity AS "
                "SELECT * FROM v_parcel_equity ORDER BY parcel_uid")  # fmt: skip
    con.execute("CHECKPOINT")


SHARE_PREFIX = "_search_index"
PART_BYTES = 40_000_000  # object storage takes 50 MB per object; stay well under it
TABLES = ("sources", *PER_SOURCE, "addresses", "word_sounds", "matcher_runs",
          *(f"m_{t}" for t in MATCHER))  # fmt: skip


def export(con: duckdb.DuckDBPyConnection, store: Any, work: Path, log: Any = print) -> int:
    """Upload the index to object storage as sorted Parquet parts plus a manifest, so other
    machines can pull it instead of rebuilding. Returns the number of files uploaded."""
    import shutil

    sort = dict(SORT_KEYS) | {"sources": "source_id", "word_sounds": "sound"}
    shutil.rmtree(work, ignore_errors=True)
    manifest: dict[str, Any] = {"exported_at": datetime.now(UTC).isoformat(), "tables": {}}
    sent = 0
    for t in TABLES:
        out = work / t
        out.mkdir(parents=True)
        order = f" ORDER BY {sort[t]}" if t in sort else ""
        con.execute(f"COPY (SELECT * FROM {t}{order}) TO '{out}' "  # noqa: S608
                    f"(FORMAT parquet, COMPRESSION zstd, FILE_SIZE_BYTES {PART_BYTES}, "
                    "ROW_GROUP_SIZE 100000)")  # fmt: skip
        files = sorted(p.name for p in out.glob("*.parquet"))
        for name in files:
            store.upload(f"{SHARE_PREFIX}/{t}/{name}", (out / name).read_bytes())
            sent += 1
        manifest["tables"][t] = files
        shutil.rmtree(out)  # free each table's copy as soon as it is uploaded
        log(f"exported {t}: {len(files)} parts")
    manifest["sources"] = dict(con.execute("SELECT source_id, version FROM sources").fetchall())
    store.upload(f"{SHARE_PREFIX}/manifest.json",
                 json.dumps(manifest, indent=1, sort_keys=True).encode())  # fmt: skip
    shutil.rmtree(work, ignore_errors=True)
    return sent + 1


def pull(store: Any, db: Path, work: Path, log: Any = print) -> int:
    """Download an exported index and load it into a new local file at db (replacing it).
    Returns the number of sources in it."""
    import shutil

    manifest = json.loads(store.download(f"{SHARE_PREFIX}/manifest.json"))
    shutil.rmtree(work, ignore_errors=True)
    tmp = db.with_suffix(".pull.duckdb")
    tmp.unlink(missing_ok=True)
    con = connect(tmp)
    for t, files in manifest["tables"].items():
        # One table at a time, its download deleted once loaded: peak disk is the index plus
        # one table's Parquet, not twice the index.
        (work / t).mkdir(parents=True)
        for name in files:
            (work / t / name).write_bytes(store.download(f"{SHARE_PREFIX}/{t}/{name}"))
        con.execute(f"DELETE FROM {t}")  # noqa: S608
        if files:
            con.execute(f"INSERT INTO {t} BY NAME SELECT * FROM read_parquet(?)",  # noqa: S608
                        [[str(work / t / f) for f in files]])  # fmt: skip
        shutil.rmtree(work / t)
        log(f"pulled {t}: {len(files)} parts")
    n = int(con.execute("SELECT count(*) FROM sources").fetchone()[0])  # type: ignore[index]
    shutil.rmtree(work, ignore_errors=True)
    for table, view in (("debtor_owner_candidates", "v_debtor_owner_candidates"),
                        ("parcel_equity", "v_parcel_equity")):  # fmt: skip
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM {view}")  # noqa: S608
    con.execute("CHECKPOINT")
    con.close()
    tmp.replace(db)
    shutil.rmtree(work, ignore_errors=True)
    return n


def status(con: duckdb.DuckDBPyConnection) -> str:
    n = con.execute("SELECT count(*), max(indexed_at) FROM sources").fetchone()
    lines = [f"{n[0] if n else 0} sources indexed, last at {n[1] if n else None}"]
    for t in (*PER_SOURCE, "addresses", "word_sounds"):
        c = con.execute(f"SELECT count(*) FROM {t}").fetchone()  # noqa: S608
        lines.append(f"  {t:20} {c[0] if c else 0:>14,}")
    return "\n".join(lines)


def _store() -> Any:  # pragma: no cover - network
    from equity.lake_sync import DEFAULT_URL, Store

    return Store(base_url=os.environ.get("SUPABASE_STORAGE_URL", DEFAULT_URL),
                 key=os.environ.get("SUPABASE_SECRET_KEY") or None)  # fmt: skip


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(prog="equity.search_index")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--lake", type=Path, default=LAKE)
    b.add_argument("--remote", action="store_true", help="read Parquet from object storage")
    b.add_argument("--only", nargs="*")
    b.add_argument("--states", nargs="*")
    b.add_argument("--force", action="store_true")
    b.add_argument("--workers", type=int, default=8, help="sources fetched at once")
    c = sub.add_parser("compact")
    c.add_argument("--only", nargs="*", help="re-sort just these tables")
    sub.add_parser("status")
    sub.add_parser("export", help="upload the index to object storage (for other machines)")
    sub.add_parser("pull", help="replace the local index with the exported one")
    args = ap.parse_args(argv)
    if args.cmd == "pull":
        n = pull(_store(), args.db, Path("data/work/search_index_pull"))
        print(f"pulled {n} sources into {args.db}")
        return 0
    con = connect(args.db, read_only=args.cmd in ("status", "export"))
    if args.cmd == "build":
        if args.remote:
            con.execute("LOAD httpfs")
            source: Any = RemoteSource(_store())
        else:
            source = FileSource(args.lake)
        done = build(con, source, args.only, args.states, args.force,
                     workers=args.workers, remote=args.remote)  # fmt: skip
        print(f"{len(done)} sources (re)indexed")
        print(f"{len(index_matcher(con, source, args.force))} states' matcher output loaded")
    elif args.cmd == "compact":
        compact(con, args.only)
    elif args.cmd == "export":
        print(f"uploaded {export(con, _store(), Path('data/work/search_index_export'))} files")
    print(status(con))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
