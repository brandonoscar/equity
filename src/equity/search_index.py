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

name_key is the matcher's key (equity.matching.resolve): upper-case name words, letters and
digits only, without JR/SR/AND/TR/..., de-duplicated and sorted. street_key is the matcher's
street_norm (USPS Publication 28 words). No models: every key is a fixed rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
INDEX_VERSION = "3"
LAKE = Path("data/lake")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    source_id VARCHAR PRIMARY KEY, state VARCHAR, version VARCHAR NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL, rows VARCHAR);
CREATE TABLE IF NOT EXISTS names (
    source_id VARCHAR, party_id VARCHAR, raw_name VARCHAR, party_kind VARCHAR,
    org_form VARCHAR, name_key VARCHAR, jurisdiction VARCHAR, address_id VARCHAR);
CREATE TABLE IF NOT EXISTS name_words (word VARCHAR, name_key VARCHAR, source_id VARCHAR);
CREATE TABLE IF NOT EXISTS word_sounds (word VARCHAR PRIMARY KEY, sound VARCHAR);
CREATE TABLE IF NOT EXISTS owners (
    source_id VARCHAR, party_id VARCHAR, parcel_uid VARCHAR, observed_on DATE);
CREATE TABLE IF NOT EXISTS parcels (
    source_id VARCHAR, parcel_uid VARCHAR, jurisdiction VARCHAR, parid_raw VARCHAR,
    situs_address_id VARCHAR, land_use_desc VARCHAR, zoning VARCHAR);
CREATE TABLE IF NOT EXISTS parcel_values (
    source_id VARCHAR, parcel_uid VARCHAR, tax_year INTEGER, appraised_total DOUBLE,
    assessed_value DOUBLE, homestead BOOLEAN);
CREATE TABLE IF NOT EXISTS addresses (
    address_id VARCHAR, line1 VARCHAR, city VARCHAR, state VARCHAR, zip5 VARCHAR,
    street_key VARCHAR);
CREATE TABLE IF NOT EXISTS instruments (
    source_id VARCHAR, instrument_uid VARCHAR, doc_type VARCHAR, doc_type_raw VARCHAR,
    recorded_on DATE, amount DOUBLE, consideration DOUBLE);
CREATE TABLE IF NOT EXISTS instrument_parcels (
    source_id VARCHAR, instrument_uid VARCHAR, parcel_uid VARCHAR, method VARCHAR);
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
-- Parties named on a debt (lien, judgment, lis pendens...) whose exact name_key also owns a
-- parcel in the same state. Name-only: review before relying on it.
CREATE OR REPLACE VIEW v_debtor_owner_candidates AS
SELECT d.ref AS debtor_ref, d.raw_name AS debtor_name, d.doc_type, d.recorded_on, d.amount,
       o.ref AS owner_ref, o.raw_name AS owner_name, o.parcel_uid, o.appraised_total,
       o.assessed_value, ds.state
FROM v_party_documents d
JOIN names dn ON dn.source_id = d.source_id AND dn.party_id = d.party_id
JOIN sources ds ON ds.source_id = d.source_id
JOIN names onm ON onm.name_key = dn.name_key AND onm.name_key <> ''
JOIN sources os ON os.source_id = onm.source_id AND os.state = ds.state
JOIN v_owner_parcels o ON o.source_id = onm.source_id AND o.party_id = onm.party_id
WHERE d.doc_type IN ('JUDGMENT_LIEN', 'ABSTRACT_OF_JUDGMENT', 'EXECUTION', 'LIS_PENDENS',
                     'MECHANICS_LIEN', 'STATUTORY_LIEN', 'TAX_LIEN_STATE', 'TAX_LIEN_FEDERAL',
                     'COURT_ORDER')
  AND len(string_split(dn.name_key, ' ')) >= 2;
"""

# Catalog table -> (lake table, {catalog column: SQL over the lake row}, current-rows filter).
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
    ("instrument_parcels", "parcel_uid"), ("cases", "case_uid"),
             ("judgments", "case_uid"))  # fmt: skip
LAKE_TABLES = ("party", "owner_snapshot", "parcel", "parcel_assessment", "address", "instrument",
               "instrument_party",
    "instrument_parcel", "court_case", "case_party", "judgment", "business",
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
    if not read_only:
        _migrate(con)
        con.execute(SCHEMA)
        con.execute(VIEWS)
    return con


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
    col = sql[len("name_key(") : -1] if sql.startswith("name_key(") else sql
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
        where = " WHERE superseded_at IS NULL" if current and "superseded_at" in have else ""
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
    """, [source_id, source_id])  # fmt: skip
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
    with ThreadPoolExecutor(workers) as ex:
        futures = {ex.submit(extract, source, sid, tmp, remote): (sid, v) for sid, v in todo}
        for fut in as_completed(futures):
            sid, version = futures[fut]
            index(sid, version, fut.result())
            shutil.rmtree(tmp / sid, ignore_errors=True)
    done.sort()
    return done


def compact(con: duckdb.DuckDBPyConnection) -> None:
    """Rewrite the search tables sorted by their lookup keys, so DuckDB's per-block min/max
    skips almost everything on an exact name or word lookup."""
    for table, key in SORT_KEYS:
        con.execute(f"CREATE OR REPLACE TABLE {table} AS "  # noqa: S608
                    f"SELECT * FROM {table} ORDER BY {key}")  # fmt: skip
    # word_sounds keeps its primary key (INSERT OR IGNORE relies on it).
    con.execute("CREATE OR REPLACE TABLE _ws (word VARCHAR PRIMARY KEY, sound VARCHAR)")
    con.execute("INSERT INTO _ws SELECT * FROM word_sounds ORDER BY sound, word")
    con.execute("DROP TABLE word_sounds")
    con.execute("ALTER TABLE _ws RENAME TO word_sounds")
    con.execute("CHECKPOINT")


SHARE_PREFIX = "_search_index"
PART_BYTES = 40_000_000  # object storage takes 50 MB per object; stay well under it
TABLES = ("sources", *PER_SOURCE, "addresses", "word_sounds")


def export(con: duckdb.DuckDBPyConnection, store: Any, work: Path, log: Any = print) -> int:
    """Upload the index to object storage as sorted Parquet parts plus a manifest, so other
    machines can pull it instead of rebuilding. Returns the number of files uploaded."""
    import shutil

    sort = dict(SORT_KEYS) | {"sources": "source_id", "addresses": "address_id",
                              "word_sounds": "sound"}  # fmt: skip
    shutil.rmtree(work, ignore_errors=True)
    manifest: dict[str, Any] = {"exported_at": datetime.now(UTC).isoformat(), "tables": {}}
    sent = 0
    for t in TABLES:
        out = work / t
        out.mkdir(parents=True)
        con.execute(f"COPY (SELECT * FROM {t} ORDER BY {sort[t]}) TO '{out}' "  # noqa: S608
                    f"(FORMAT parquet, COMPRESSION zstd, FILE_SIZE_BYTES {PART_BYTES}, "
                    "ROW_GROUP_SIZE 100000)")  # fmt: skip
        files = sorted(p.name for p in out.glob("*.parquet"))
        for name in files:
            store.upload(f"{SHARE_PREFIX}/{t}/{name}", (out / name).read_bytes())
            sent += 1
        manifest["tables"][t] = files
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
    for t, files in manifest["tables"].items():
        (work / t).mkdir(parents=True)
        for name in files:
            (work / t / name).write_bytes(store.download(f"{SHARE_PREFIX}/{t}/{name}"))
    tmp = db.with_suffix(".pull.duckdb")
    tmp.unlink(missing_ok=True)
    con = connect(tmp)
    for t, files in manifest["tables"].items():
        con.execute(f"DELETE FROM {t}")  # noqa: S608
        if files:
            con.execute(f"INSERT INTO {t} SELECT * FROM read_parquet(?)",  # noqa: S608
                        [[str(work / t / f) for f in files]])  # fmt: skip
        log(f"pulled {t}: {len(files)} parts")
    n = int(con.execute("SELECT count(*) FROM sources").fetchone()[0])  # type: ignore[index]
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
    sub.add_parser("compact")
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
    elif args.cmd == "compact":
        compact(con)
    elif args.cmd == "export":
        print(f"uploaded {export(con, _store(), Path('data/work/search_index_export'))} files")
    print(status(con))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
