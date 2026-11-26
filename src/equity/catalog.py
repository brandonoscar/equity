"""Query catalog: one local DuckDB file that indexes the whole lake for search and ad-hoc SQL.

The lake is ~450 sources of Parquet parts (local `data/lake/` or the object-storage bucket).
Searching it directly means opening thousands of files per query. The catalog copies only
the columns queries need into a few tables, one source at a time, and remembers each
source's version so a rebuild re-indexes only sources that changed:

    uv run python -m equity.catalog build                 # every built source in data/lake
    uv run python -m equity.catalog build --remote        # read Parquet from object storage
    uv run python -m equity.catalog build --only ia.scott.parcels --states OH NY
    uv run python -m equity.catalog compact               # sort the search tables (faster lookups)
    uv run python -m equity.catalog status

Tables (every row keeps its source_id; full rows stay in the lake under the same ids):
  sources          source_id, state, version (what was indexed), indexed_at, rows per table
  names            party names: party_id, raw_name, party_kind, name_key, address_id
  name_words       inverted index: one row per word of a name_key (search candidates)
  owners           party_id -> parcel_uid (owner_snapshot)
  parcels          parcel_uid, situs_address_id, land use, zoning
  parcel_values    latest assessment per parcel and source
  addresses        address_id -> line1, city, state, zip5, street_key (content-addressed)
  instruments      recorded documents and debt-list items (doc_type, date, amount)
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

DEFAULT_DB = Path("data/catalog.duckdb")
STORAGE_VERSION = "v1.5.0"
LAKE = Path("data/lake")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    source_id VARCHAR PRIMARY KEY, state VARCHAR, version VARCHAR NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL, rows VARCHAR);
CREATE TABLE IF NOT EXISTS names (
    source_id VARCHAR, party_id VARCHAR, raw_name VARCHAR, party_kind VARCHAR,
    org_form VARCHAR, name_key VARCHAR, jurisdiction VARCHAR, address_id VARCHAR);
CREATE TABLE IF NOT EXISTS name_words (word VARCHAR, source_id VARCHAR, party_id VARCHAR);
CREATE TABLE IF NOT EXISTS owners (
    source_id VARCHAR, party_id VARCHAR, parcel_uid VARCHAR, observed_on DATE);
CREATE TABLE IF NOT EXISTS parcels (
    source_id VARCHAR, parcel_uid VARCHAR, jurisdiction VARCHAR, parid_raw VARCHAR,
    situs_address_id VARCHAR, land_use_desc VARCHAR, zoning VARCHAR);
CREATE TABLE IF NOT EXISTS parcel_values (
    source_id VARCHAR, parcel_uid VARCHAR, tax_year INTEGER, appraised_total DOUBLE,
    assessed_value DOUBLE, homestead BOOLEAN);
CREATE TABLE IF NOT EXISTS addresses (
    address_id VARCHAR PRIMARY KEY, line1 VARCHAR, city VARCHAR, state VARCHAR, zip5 VARCHAR,
    street_key VARCHAR);
CREATE TABLE IF NOT EXISTS instruments (
    source_id VARCHAR, instrument_uid VARCHAR, doc_type VARCHAR, doc_type_raw VARCHAR,
    recorded_on DATE, amount DOUBLE, consideration DOUBLE);
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
LAKE_TABLES = ("party", "owner_snapshot", "parcel", "parcel_assessment", "address", "instrument",
               "instrument_party", "court_case", "case_party", "judgment", "business",
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
    if not read_only:
        con.execute(SCHEMA)
        con.execute(VIEWS)
    return con


class FileSource:
    """Parquet parts of a local lake directory (data/lake/<source>/<table>/*.parquet)."""

    def __init__(self, lake: Path = LAKE) -> None:
        self.lake = lake

    def sources(self, only: Iterable[str] | None = None) -> list[str]:
        ids = sorted(p.parent.name for p in self.lake.glob("*/_counts.json"))
        return ids if only is None else [s for s in ids if s in set(only)]

    def version(self, source_id: str) -> str:
        src = self.lake / source_id
        h = hashlib.sha256((src / "_counts.json").read_bytes())
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
        return hashlib.sha256(text.encode()).hexdigest()[:16]

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
            SELECT address_id, any_value(line1), any_value(city), any_value(state),
                   any_value(zip5), any_value(street_norm(line1))
            FROM read_parquet(?, union_by_name = true)
            WHERE address_id NOT IN (SELECT address_id FROM addresses)
            GROUP BY address_id
        """, [files])  # fmt: skip
    con.execute("""
        INSERT INTO name_words
        SELECT DISTINCT unnest(string_split(name_key, ' ')) AS word, source_id, party_id
        FROM names WHERE source_id = ? AND name_key <> ''
    """, [source_id])  # fmt: skip
    con.execute("""
        INSERT INTO name_words
        SELECT DISTINCT unnest(string_split(name_key, ' ')), source_id, 'business:' || sos_id
        FROM businesses WHERE source_id = ? AND name_key <> ''
    """, [source_id])  # fmt: skip
    return counts


def build(
    con: duckdb.DuckDBPyConnection,
    source: Any,
    only: Iterable[str] | None = None,
    states: Iterable[str] | None = None,
    force: bool = False,
    log: Any = print,
) -> list[str]:
    """Index every source whose version changed since it was last indexed. Sources that no
    longer exist in the lake are dropped. Returns the ids (re)indexed."""
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
    done = []
    for sid in ids:
        version = source.version(sid)
        if not force and known.get(sid) == version:
            continue
        con.execute("BEGIN TRANSACTION")
        try:
            counts = index_source(con, source, sid)
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
    return done


def compact(con: duckdb.DuckDBPyConnection) -> None:
    """Rewrite the search tables sorted by their lookup keys, so DuckDB's per-block min/max
    skips almost everything on an exact name or word lookup."""
    for table, key in (("names", "name_key"), ("name_words", "word"),
                       ("owners", "party_id"), ("instrument_parties", "party_id"),
                       ("case_parties", "party_id"), ("businesses", "name_key")):  # fmt: skip
        con.execute(f"CREATE OR REPLACE TABLE {table} AS "  # noqa: S608
                    f"SELECT * FROM {table} ORDER BY {key}")  # fmt: skip
    con.execute("CHECKPOINT")


def status(con: duckdb.DuckDBPyConnection) -> str:
    n = con.execute("SELECT count(*), max(indexed_at) FROM sources").fetchone()
    lines = [f"{n[0] if n else 0} sources indexed, last at {n[1] if n else None}"]
    for t in (*PER_SOURCE, "addresses"):
        c = con.execute(f"SELECT count(*) FROM {t}").fetchone()  # noqa: S608
        lines.append(f"  {t:20} {c[0] if c else 0:>14,}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(prog="equity.catalog")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--lake", type=Path, default=LAKE)
    b.add_argument("--remote", action="store_true", help="read Parquet from object storage")
    b.add_argument("--only", nargs="*")
    b.add_argument("--states", nargs="*")
    b.add_argument("--force", action="store_true")
    sub.add_parser("compact")
    sub.add_parser("status")
    args = ap.parse_args(argv)
    con = connect(args.db)
    if args.cmd == "build":
        if args.remote:
            from equity.lake_sync import DEFAULT_URL, Store

            store = Store(base_url=os.environ.get("SUPABASE_STORAGE_URL", DEFAULT_URL),
                          key=os.environ.get("SUPABASE_SECRET_KEY") or None)  # fmt: skip
            con.execute("LOAD httpfs")
            source: Any = RemoteSource(store)
        else:
            source = FileSource(args.lake)
        done = build(con, source, args.only, args.states, args.force)
        print(f"{len(done)} sources (re)indexed")
    elif args.cmd == "compact":
        compact(con)
    print(status(con))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
