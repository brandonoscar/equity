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
  lien_names_parcel         the lien itself names the parcel (instrument_parcel), and that
                            parcel is in the owner source; no name match needed   -> auto
With street_town (CT only, approved by the project owner 2026-11-22), also:
  person_name_street_town   same person name_key, street line and town         -> auto
  org_name_street_town      same org_name, street line and town                -> auto

Output (Parquet under data/derived/<state>/, which is git-ignored: it names people):
  matches.parquet   debtor party, its instrument, owner party, parcel, rule, decision, keys
  debtor_summary.parquet   per matched debtor: liens, open amount, parcels, total parcel value,
                    and with recorder sources open mortgages and equity_est (see .equity)
  mortgage_status.parquet  each mortgage on a matched lot: open or which rule marked it paid
  review_queue.parquet     evidence and labels for review-only matches (see .review)
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
    ("person_name_initial_address", "review", 7),
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
                   "principal_amount": "DOUBLE"},
    "instrument_ref": {"from_uid": V, "to_uid": V, "ref_type": V},
    "instrument_parcel": {"instrument_uid": V, "parcel_uid": V},
    "parcel_link": {"from_parcel_uid": V, "to_parcel_uid": V, "link_type": V},
    "business": {"sos_id": V, "name": V, "status": V},
    "business_role": {"sos_id": V, "party_id": V, "role": V, "title": V},
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
    lake: Path,
    debtor_sources: list[str],
    owner_sources: list[str],
    parcel_on_lien: bool = False,
    debtor_doc_types: list[str] | None = None,
) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    # Only these instrument types count as debts (e.g. liens but not UCC financing statements).
    doc_filter = ""
    if debtor_doc_types:
        types = ", ".join("'" + t.replace("'", "''") + "'" for t in debtor_doc_types)
        doc_filter = f"AND i.doc_type IN ({types})"
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
                   '', '', NULL, NULL, NULL
            FROM d_inst i JOIN d_lot l ON l.instrument_uid = i.instrument_uid
            WHERE i.doc_type <> 'RELEASE' AND NOT EXISTS (
                SELECT 1 FROM d_ip ip WHERE ip.instrument_uid = i.instrument_uid
                  AND ip.role = 'debtor');
        """)
    return con


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
PARCEL_ON_LIEN_SQL = """
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, NULL, l.parcel_uid, 'lien_names_parcel',
       l.parcel_uid
FROM debtors d JOIN d_lot l ON l.instrument_uid = d.instrument_uid
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
    con: duckdb.DuckDBPyConnection, street_town: bool = False, parcel_on_lien: bool = False
) -> None:
    con.execute(MATCH_SQL)
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
    link_sources: list[str] | None = None,
    street_town: bool = False,
    parcel_on_lien: bool = False,
    registry_sources: list[str] | None = None,
    debtor_doc_types: list[str] | None = None,
) -> dict[str, object]:
    from equity.matching import entities, equity, review

    con = connect(lake, debtor_sources, owner_sources, parcel_on_lien, debtor_doc_types)
    match(con, street_town, parcel_on_lien)
    review.build(con)
    tables = ["matches", "debtor_summary", "review_queue"]
    if registry_sources:
        entities.compute(con, lake, registry_sources)
        tables.extend(entities.TABLES)
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
        "registries": ["ny.sos.business"],
    },
    # CT parcel data has no owner ZIP (Mailing_Zip is empty statewide): street + town instead.
    # Allegheny's parcel layer has no owner names, but its liens name the parcel (PIN).
    "PA-ALLEGHENY": {"debtors": ["pa.allegheny.tax_liens", "pa.allegheny.foreclosures"],
                     "owners": ["pa.allegheny.parcels", "pa.allegheny.assessments"],
                     "registries": ["pa.dos.business"],
                     "parcel_on_lien": True},
    # Baltimore City: environmental citation liens name the parcel (block/lot), not a person.
    "MD-BALTIMORE": {"debtors": ["md.baltimore_city.citation_liens"],
                     "owners": ["md.baltimore_city.parcels"], "parcel_on_lien": True},
    # Harris County, TX: justice-court civil judgments against Texas parcel owners.
    "TX-HARRIS": {"debtors": ["tx.harris.jp.judgments"], "owners": ["tx.statewide.parcels"]},
    # Travis: delinquent property tax accounts and tax-suit judgments, by owner name.
    "TX-TRAVIS": {"debtors": ["tx.travis.tax_delinquent"], "owners": ["tx.statewide.parcels"]},
    # Detroit: blight judgments name the owner and the parcel; both are matched.
    "MI-WAYNE": {"debtors": ["mi.detroit.blight_judgments"], "owners": ["mi.wayne.parcels"],
                 "parcel_on_lien": True},
    # Omaha: tax sale certificates (named taxpayers) and county-held liens (PIN only).
    "NE-DOUGLAS": {"debtors": ["ne.douglas.tax_liens"], "owners": ["ne.douglas.parcels"],
                   "parcel_on_lien": True},
    # Colorado: federal tax and statutory (hospital, other) liens from the SOS UCC system;
    # UCC financing statements name debtors too but are not debts owed on a judgment or lien.
    "CO": {"debtors": ["co.sos.ucc"], "debtor_doc_types": ["TAX_LIEN_FEDERAL", "STATUTORY_LIEN"],
           "owners": ["co.statewide.parcels"], "registries": ["co.sos.business"]},
    "CT": {"debtors": ["ct.sots.liens"], "owners": ["ct.statewide.parcels"], "street_town": True,
           "registries": ["ct.sos.business"]},
    # North Carolina: Guilford and Buncombe unpaid property taxes, Charlotte municipal liens.
    "NC": {"debtors": ["nc.guilford.tax_delinquent", "nc.buncombe.unpaid_bills",
                       "nc.charlotte.municipal_liens"],
           "owners": ["nc.statewide.parcels"], "parcel_on_lien": True},
    "AZ-COCHISE": {"debtors": ["az.cochise.tax_liens"], "owners": ["az.cochise.parcels"],
                   "parcel_on_lien": True},
    "OH-CLERMONT": {"debtors": ["oh.clermont.tax_delinquent"], "owners": ["oh.statewide.parcels"],
                    "parcel_on_lien": True},
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
                 spec.get("registries"), spec.get("debtor_doc_types"))  # fmt: skip
    json.dump(result, sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
