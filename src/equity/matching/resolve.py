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

Rules, strongest first (a debtor-owner pair keeps its strongest rule):
  person_name_address   same person name_key, and the debtor's address equals the owner's
                        mailing address or the parcel's property address       -> auto
  org_name_address      same org_name and address                              -> auto
  org_name_zip          same org_name and ZIP                                  -> auto
  person_name_zip       same person name_key and ZIP                           -> review

Output (Parquet under data/derived/<state>/, which is git-ignored: it names people):
  matches.parquet   debtor party, its instrument, owner party, parcel, rule, decision, keys
  debtor_summary.parquet   per matched debtor: liens, open amount, parcels, total parcel value,
                    and with recorder sources open mortgages and equity_est (see .equity)
  mortgage_status.parquet  each mortgage on a matched lot: open or which rule marked it paid
and a summary with counts only, printed and written to summary.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb

LAKE = Path("data/lake")
DERIVED = Path("data/derived")
# Words that never identify a person: suffixes, conjunctions, "et al", trustee markers.
STOP = ("JR", "SR", "II", "III", "IV", "AND", "OR", "ETAL", "ET", "AL", "TR", "TRUSTEE",
        "TTEE", "MR", "MRS", "MS", "DR", "THE", "OF", "C/O", "CO", "ATTN")  # fmt: skip
RULES = (
    ("person_name_address", "auto", 1),
    ("org_name_address", "auto", 2),
    ("org_name_zip", "auto", 3),
    ("person_name_zip", "review", 4),
)


def _glob(lake: Path, sources: list[str], table: str) -> str | None:
    paths = [str(p) for s in sources for p in sorted((lake / s / table).glob("*.parquet"))]
    if not paths:
        return None
    return "[" + ", ".join("'" + p.replace("'", "''") + "'" for p in paths) + "]"


V = "VARCHAR"
COLUMNS: dict[str, dict[str, str]] = {
    "address": {"address_id": V, "line1": V, "zip5": V},
    "party": {"party_id": V, "raw_name": V, "party_kind": V, "org_name_norm": V,
              "address_id": V},
    "instrument_party": {"instrument_uid": V, "party_id": V, "role": V},
    "instrument": {"instrument_uid": V, "source_id": V, "doc_type": V, "recorded_on": "DATE",
                   "principal_amount": "DOUBLE"},
    "instrument_ref": {"from_uid": V, "to_uid": V, "ref_type": V},
    "instrument_parcel": {"instrument_uid": V, "parcel_uid": V},
    "owner_snapshot": {"parcel_uid": V, "party_id": V},
    "parcel": {"parcel_uid": V, "situs_address_id": V},
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
    lake: Path, debtor_sources: list[str], owner_sources: list[str]
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
    _view(con, "o_party", lake, owner_sources, "party")
    _view(con, "o_snap", lake, owner_sources, "owner_snapshot")
    _view(con, "o_parcel", lake, owner_sources, "parcel")
    _view(con, "o_assess", lake, owner_sources, "parcel_assessment")
    con.execute("""
        CREATE TEMP TABLE addr AS
        SELECT DISTINCT address_id,
               CASE WHEN line1 IS NOT NULL AND zip5 IS NOT NULL
                    THEN upper(line1) || '|' || zip5 END AS addr_key,
               zip5
        FROM addr_all;
        CREATE TEMP TABLE debtors AS
        SELECT DISTINCT p.party_id, p.raw_name, p.party_kind, p.org_name_norm,
               ip.instrument_uid, i.source_id, i.doc_type, i.recorded_on, i.principal_amount,
               EXISTS (SELECT 1 FROM d_ref r WHERE r.to_uid = i.instrument_uid
                       AND r.ref_type = 'releases') AS released,
               name_key(p.raw_name) AS name_key, a.addr_key, a.zip5
        FROM d_ip ip
        JOIN d_party p ON p.party_id = ip.party_id
        JOIN d_inst i ON i.instrument_uid = ip.instrument_uid
        LEFT JOIN addr a ON a.address_id = p.address_id
        WHERE ip.role = 'debtor';
        CREATE TEMP TABLE owners AS
        SELECT DISTINCT p.party_id, p.raw_name, p.party_kind, p.org_name_norm, s.parcel_uid,
               name_key(p.raw_name) AS name_key, ma.addr_key AS mail_key, ma.zip5 AS mail_zip,
               sa.addr_key AS situs_key, sa.zip5 AS situs_zip
        FROM o_snap s
        JOIN o_party p ON p.party_id = s.party_id
        LEFT JOIN o_parcel pc ON pc.parcel_uid = s.parcel_uid
        LEFT JOIN addr ma ON ma.address_id = p.address_id
        LEFT JOIN addr sa ON sa.address_id = pc.situs_address_id;
    """)
    return con


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


def match(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(MATCH_SQL)
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
                   count(*) AS liens,
                   sum(CASE WHEN NOT released THEN principal_amount END) AS open_amount
            FROM (SELECT DISTINCT party_id, raw_name, instrument_uid, released, principal_amount
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
               p.parcel_value, r.best_rank, r.has_auto
        FROM rules r
        JOIN liens l ON l.party_id = r.debtor_party_id
        JOIN props p ON p.debtor_party_id = r.debtor_party_id;
    """)  # noqa: S608 - rule names are constants


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
    }


def run(
    lake: Path,
    out: Path,
    debtor_sources: list[str],
    owner_sources: list[str],
    mortgage_sources: list[str] | None = None,
) -> dict[str, object]:
    from equity.matching import equity

    con = connect(lake, debtor_sources, owner_sources)
    match(con)
    tables = ["matches", "debtor_summary"]
    if mortgage_sources:
        equity.compute(con, lake, mortgage_sources)
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


STATES = {
    "NY": {
        "debtors": ["ny.dtf.tax_warrants", "ny.dtf.child_support_warrants",
                    "ny.nyc.oath.judgments", "ny.nyc.hpd_litigation", "ny.nyc.acris.real"],
        "owners": ["ny.statewide.parcels"],
        "mortgages": ["ny.nyc.acris.real"],
    },
}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.matching.resolve")
    ap.add_argument("--state", required=True, choices=sorted(STATES))
    ap.add_argument("--lake", type=Path, default=LAKE)
    ap.add_argument("--out", type=Path, default=DERIVED, help="writes <out>/<state>/")
    args = ap.parse_args(argv)
    spec = STATES[args.state]
    result = run(args.lake, args.out / args.state.lower(), spec["debtors"], spec["owners"],
                 spec.get("mortgages"))  # fmt: skip
    json.dump(result, sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
