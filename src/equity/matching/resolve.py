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
             2026-11-22), so "12 Main Street" and "12 MAIN ST." are one address; a numbered
             street's ordinal is dropped too, "88TH ST" = "88 ST" (approved 2026-11-27).
  town_key   street line + city, for states whose parcel data carries no owner ZIP (CT).

Rules, strongest first (a debtor-owner pair keeps its strongest rule):
  person_name_address   same person name_key, and the debtor's address equals the owner's
                        mailing address or the parcel's property address       -> auto
  org_name_address      same org_name and address                              -> auto
  person_name_address_unit / org_name_address_unit  the same, where one address is the
                        other without its unit ("12 MAIN ST APT 3" / "12 MAIN ST"; two
                        different units never pair)                            -> auto
  org_name_zip          same org_name and ZIP                                  -> auto
  person_name_zip       same person name_key and ZIP                           -> review
  person_name_initial_address  same address, and the names are the same except that one side
                        has one extra single-letter middle initial ("JOHN SMITH" / "SMITH JOHN
                        A"); a parent and child can share both, so -> review (approved by the
                        project owner 2026-11-22)
  person_nickname_address  same address, and the names are the same once each common
                        nickname is read as its formal name ("BOB SMITH" / "ROBERT SMITH",
                        equity.matching.nicknames; ambiguous nicknames left out) -> review
  person_name_typo_address  same address, and the names differ in one word by one letter
                        (added, dropped, changed or two swapped: SMITH / SMIHT), unless both
                        words are real first names (JOHN / JOAN: two people; 1990 Census
                        first-name lists)                                       -> review
  person_middle_name_address  same address, and one name is the other plus a full middle
                        name or second surname ("JOHN SMITH" / "JOHN MICHAEL SMITH", "MARIA
                        GARCIA" / "MARIA GARCIA LOPEZ"), or a middle initial on one side
                        and that middle name on the other ("JOHN A SMITH" / "JOHN ALAN
                        SMITH")                                                  -> review
  person_name_spacing_address  same address, and the same letters once spaces and
                        punctuation are dropped ("O'BRIEN" / "OBRIEN", "DE LA CRUZ" /
                        "DELACRUZ", "MC DONALD" / "MCDONALD")                  -> review
  person_loose_name_address  same address, and the names agree once nicknames are read as
                        formal names, middle initials are dropped and spaces ignored, all at
                        once ("BOB A SMITH" / "ROBERT SMITH", "BILL O BRIEN" / "WILLIAM
                        OBRIEN"); two different middle initials never agree      -> review
  person_at_owner_occupied_property  a lot no source names an owner for (California rolls)
                        whose property address is the debtor's own address, and the roll's
                        latest homeowner exemption says an owner lives there       -> review
  person_at_property    the same without the exemption (owner or tenant: unknown)   -> review
                        (an address shared by several nameless lots gives no lead)
  person_at_org_owner_mailing  a company (LLC, corp) that owns a lot has its tax bill sent
                        to the debtor's own address: the debtor likely runs the company, which
                        the registries often do not say (an LLC need list no members) -> review.
                        Not when that address takes bills for more than MAIL_SHARED_MAX owner
                        names (a manager, lawyer or bank), or is the company's own property
                        (a tenant there shares the address).
Company names that differ only in AND / & / THE, spaces or punctuation ("SMITH AND SONS",
"SMITH & SONS", "THE SMITH SONS"; org_loose):
  org_name_loose_address    same address (or its building)                   -> auto
  org_name_loose_zip        same ZIP                                         -> review
A debtor who has moved: a record that puts the debtor's name at the lien's address and at
another one (a deed's seller at the house sold and at their mailing address, a buyer, a
mortgage's borrower, the same owner name mailed at two addresses across roll years) links
the two (addr_history); an owner of that name at the other address is a lead:
  person_name_former_address  same name, the lien's address is a known former or later
                            address of an owner at another address               -> review
An address with no ZIP (on the lien or on the roll) is compared by street and city:
  person_name_street_city / org_name_street_city   same name, street line and city -> review
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

Out-of-state owners: property in another state whose tax bill is mailed into this one
(equity.matching.crossstate builds the national index; owner_basis 'out_of_state'). They
are owners like any other, so every address rule meets them.

With record_owners (and every run's deeds): owner names for parcels whose roll publishes none
(California counties, Indiana's statewide layer), from records that name a lot's owner: the
grantee of a DEED, the borrower of a MORTGAGE, or the 'owner' party of a permit,
registration or code case. Per parcel the
latest such record counts, only where the roll has no owner, matched to the roll parcel by
county and parcel number letters and digits (punctuation ignored). Matches through them carry
owner_basis ('deed:<source>' / 'record:<source>', 'roll' otherwise) and owner_seen_on; a
'record:' owner older than RECORD_OWNER_AUTO_DAYS reaches review only.

Owner strings that print several people or a trust ("SMITH JOHN A & JANE B", "JOHN A SMITH
REVOCABLE TRUST") are split into the people they name (equity.matching.names): each is an
extra owner name of the same party and parcel, so every rule above can meet it. Matches record
owner_name_variant ('joint', 'trust' or 'alias': a DBA/AKA/FKA name of the same owner); a
trust's settlor only reaches review.
Debtor strings are split the same way, plus aliases ("JOHN SMITH DBA SMITH PLUMBING", AKA,
FKA, T/A): each name is an extra debtor name of the same party and instrument, a business
alias with its org name. Matches record debtor_name_variant ('alias', 'joint' or 'trust').

Output (Parquet under data/derived/<state>/, which is git-ignored: it names people):
  matches.parquet   debtor party, its instrument, owner party, parcel, rule, decision, keys
  debtor_summary.parquet   per matched debtor: liens, open amount, parcels, total parcel value,
                    and with recorder sources open mortgages and equity_est (see .equity)
  people.parquet    one row per debtor person or business (parties merged across liens and
                    sources, see PEOPLE_SQL): open judgments, open amount, matched parcels.
                    A lien naming several people ("JOHN & MARY DOE") is in each one's row.
  person_of.parquet debtor party -> person (several rows for a party that names several people)
  mortgage_status.parquet  each mortgage on a matched lot: open or which rule marked it paid
  review_queue.parquet     evidence and labels for review-only matches (see .review)
  graph_edges / graph_nodes / person_reach.parquet  every link as one graph, its connected
                    sets and the parcels each person reaches through chains (see .graph)
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
from equity.geo import state_fips

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
    ("person_name_address_unit", "auto", 3),
    ("org_name_address_unit", "auto", 4),
    ("org_name_zip", "auto", 5),
    ("person_name_zip", "review", 6),
    ("person_name_street_town", "auto", 7),
    ("org_name_street_town", "auto", 8),
    ("org_name_county", "review", 9),
    ("person_name_initial_address", "review", 10),
    ("person_nickname_address", "review", 11),
    ("person_name_typo_address", "review", 12),
    ("person_middle_name_address", "review", 13),
    ("person_name_spacing_address", "review", 14),
    ("person_at_owner_occupied_property", "review", 15),
    ("person_at_property", "review", 16),
    ("person_at_org_owner_mailing", "review", 17),
    ("org_name_loose_address", "auto", 18),
    ("org_name_loose_zip", "review", 19),
    ("person_name_street_city", "review", 20),
    ("org_name_street_city", "review", 21),
    ("person_name_former_address", "review", 22),
    ("person_loose_name_address", "review", 23),
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
    "business": {"sos_id": V, "name": V, "status": V, "jurisdiction": V},
    "business_role": {"sos_id": V, "party_id": V, "role": V, "title": V},
    "owner_snapshot": {"parcel_uid": V, "party_id": V},
    "parcel": {"parcel_uid": V, "situs_address_id": V},
    "case_party": {"case_uid": V, "party_id": V, "role": V},
    "judgment": {"judgment_uid": V, "case_uid": V, "source_id": V, "entered_on": "DATE",
                 "principal": "DOUBLE", "jurisdiction": V, "judgment_type": V},
    "judgment_event": {"judgment_uid": V, "event": V},
    "docket_entry": {"case_uid": V, "entry_date": "DATE", "source_id": V, "jurisdiction": V},
    "parcel_assessment": {"parcel_uid": V, "tax_year": "INTEGER", "appraised_total": "DOUBLE",
                          "assessed_value": "DOUBLE", "homestead": "BOOLEAN"},
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


# A unit designator and its number at the end of a street line.
UNIT_MACRO = r"""
CREATE OR REPLACE MACRO unit_strip(s) AS regexp_replace(upper(coalesce(s, '')),
    '\s*(#\s*[A-Z0-9-]+|\b(APT|APARTMENT|UNIT|STE|SUITE|FL|FLOOR|RM|ROOM|SPC|SPACE|TRLR|LOT)'
    '\b\.?\s*#?\s*([A-Z]?-?[0-9][A-Z0-9-]*|[A-Z]))\s*$', '');
"""


def connect(
    lake: Path,
    debtor_sources: list[str],
    owner_sources: list[str],
    parcel_on_lien: bool = False,
    court_sources: list[str] | None = None,
    writ_sources: list[str] | None = None,
    debtor_doc_types: list[str] | dict[str, list[str]] | None = None,
    record_owner_sources: list[str] | None = None,
    out_of_state: tuple[Path, str] | None = None,
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
                  | set(writ_sources or []) | set(record_owner_sources or []))  # fmt: skip
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
    con.execute(UNIT_MACRO)
    con.execute(f"""
        CREATE TEMP TABLE addr AS
        SELECT DISTINCT address_id,
               CASE WHEN street_norm(line1) <> '' AND zip5 IS NOT NULL
                    THEN street_norm(line1) || '|' || zip5 END AS addr_key,
               CASE WHEN street_norm(line1) <> '' AND city IS NOT NULL
                    THEN street_norm(line1) || '|' || upper(trim(city)) END AS town_key,
               zip5,
               -- The building's address: the street line without a trailing unit
               -- ("12 MAIN ST APT 3B", "12 MAIN ST #3", "... STE 200", "... LOT 14").
               CASE WHEN len(string_split(street_norm(unit_strip(line1)), ' ')) >= 2
                         AND zip5 IS NOT NULL
                    THEN street_norm(unit_strip(line1)) || '|' || zip5 END AS base_key
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
        ALTER TABLE owners ADD COLUMN owner_basis VARCHAR DEFAULT 'roll';
        ALTER TABLE owners ADD COLUMN owner_seen_on DATE;
        ALTER TABLE owners ADD COLUMN name_variant VARCHAR;
    """)  # noqa: S608 - doc types come from STATES (repo config), quoted
    if record_owner_sources:
        _record_owners(con, lake, record_owner_sources)
    if out_of_state and out_of_state[0].exists():
        # Parcels in other states whose tax bill is mailed into this one (crossstate.INDEX).
        from equity.matching import crossstate

        crossstate.load(con, out_of_state[0], out_of_state[1])
    _owner_name_variants(con)
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
    _debtor_name_variants(con)
    return con


# Owner names from records that are not owner rolls, for parcels whose roll publishes none
# (California counties, Indiana's statewide layer): a deed's grantee, and the 'owner' party of
# a permit, landlord or rental registration or code case, and the borrower of a mortgage (who
# owned the lot when it was recorded). Per parcel only the latest dated
# record counts (all its owner names), and only where no roll owner is known, so a roll owner
# is never displaced. owner_basis says where the name came from: 'deed:<source>',
# 'mortgage:<source>' or 'record:<source>'; owner_seen_on is that record's date.
RECORD_OWNERS_SQL = """
-- Records and rolls often print one parcel number differently ('49-02-19-107-055.000-800'
-- in the roll, '490219107055000800' on a sales form): a record's lot is the roll parcel with
-- the same county and the same letters and digits.
CREATE MACRO parcel_key(u) AS split_part(u, '-', 1) || '-'
    || upper(regexp_replace(substr(u, strpos(u, '-') + 1), '[^0-9A-Za-z]', '', 'g'));
CREATE TEMP TABLE roll_lot AS
SELECT parcel_key(parcel_uid) AS k, min(parcel_uid) AS parcel_uid
FROM o_parcel GROUP BY 1 HAVING count(DISTINCT parcel_uid) = 1;
INSERT INTO owners
WITH named AS (
    SELECT rl.parcel_uid, ip.party_id, i.recorded_on, i.source_id,
           CASE WHEN ip.role = 'grantee' THEN 'deed:'
                WHEN ip.role = 'borrower' THEN 'mortgage:' ELSE 'record:' END || i.source_id
               AS basis
    FROM ro_ip ip
    JOIN ro_inst i ON i.instrument_uid = ip.instrument_uid
    JOIN ro_lot l ON l.instrument_uid = ip.instrument_uid
    JOIN roll_lot rl ON rl.k = parcel_key(l.parcel_uid)
    WHERE (ip.role = 'owner' OR (ip.role = 'grantee' AND i.doc_type = 'DEED')
           -- a mortgage's borrower owned the lot when it was recorded
           OR (ip.role = 'borrower' AND i.doc_type = 'MORTGAGE'))
      AND i.recorded_on IS NOT NULL
      AND rl.parcel_uid NOT IN (SELECT parcel_uid FROM o_snap)
), latest AS (
    SELECT * FROM named
    QUALIFY recorded_on = max(recorded_on) OVER (PARTITION BY parcel_uid)
)
SELECT DISTINCT p.party_id, p.raw_name, p.party_kind, p.org_name_norm, n.parcel_uid,
       name_key(p.raw_name), suffix_key(p.raw_name),
       ma.addr_key, ma.zip5, sa.addr_key, sa.zip5, ma.town_key, sa.town_key,
       n.basis, n.recorded_on, NULL
FROM latest n
JOIN ro_party p ON p.party_id = n.party_id
LEFT JOIN o_parcel pc ON pc.parcel_uid = n.parcel_uid
LEFT JOIN addr ma ON ma.address_id = p.address_id
LEFT JOIN addr sa ON sa.address_id = pc.situs_address_id;
"""
# A 'record:' or 'mortgage:' owner is who owned the lot on the record's date (a permit, a
# registration, a mortgage); the lot may have been sold since. Its matches stay 'review'
# unless the record is recent.
# TODO(Brandon): confirm the two-year window (deeds are not capped: the latest recorded
# grantee is the owner of record).
RECORD_OWNER_AUTO_DAYS = 730


def _record_owners(con: duckdb.DuckDBPyConnection, lake: Path, sources: list[str]) -> None:
    _view(con, "ro_party", lake, sources, "party")
    _view(con, "ro_ip", lake, sources, "instrument_party")
    _view(con, "ro_inst", lake, sources, "instrument")
    _view(con, "ro_lot", lake, sources, "instrument_parcel")
    con.execute(RECORD_OWNERS_SQL)


# Owner strings that print several people or a trust ("SMITH JOHN A & JANE B", "JOHN A
# SMITH REVOCABLE TRUST"): each person they name joins the owners as an extra name of the
# same owner party and parcel (equity.matching.names). raw_name stays the printed string;
# name_key is the person's. A joint owner's name is matched like any owner name; a trust's
# settlor or trustee (name_variant 'trust') only reaches review.
VARIANT_MARK = r"&|\bAND\b|/|;|\bTR\b|\bTRS\b|TRUST|\bTTEES?\b|\bET ?UX\b|\bET ?VIR\b"
# Alias markers ("JOHN SMITH DBA SMITH PLUMBING", AKA, FKA, NKA, T/A), read after periods
# are dropped (D.B.A. -> DBA).
ALIAS_MARK = (r"\bD ?/? ?B ?/? ?A\b|\b[AFN] ?/? ?K ?/? ?A\b|\bT ?/ ?A\b"
              r"|KNOWN AS|BUSINESS AS|TRADING AS")  # fmt: skip
NAME_MARK = VARIANT_MARK + "|" + ALIAS_MARK


def name_variant_table(con: duckdb.DuckDBPyConnection, table: str, names_sql: str) -> None:
    """CREATE TEMP TABLE <table> (raw_name, variant, kind, party_kind, org_name_norm): every
    name inside each string names_sql returns that carries a joint, trust or alias marker
    (equity.matching.names.debtor_name_variants), split in Python and loaded back through a
    temporary CSV. A business alias keeps its org name (orgs.classify); other names are
    people. Used for owners, debtors, bankruptcy filers, deed parties and company officers."""
    import csv
    import tempfile

    from equity.matching.names import debtor_name_variants
    from equity.matching.orgs import classify

    names = [r[0] for r in con.execute(
        f"SELECT DISTINCT raw FROM ({names_sql}) t(raw) "  # noqa: S608 - internal SQL
        "WHERE regexp_matches(upper(replace(coalesce(raw, ''), '.', '')), ?) ORDER BY 1",
        [NAME_MARK]).fetchall()]  # fmt: skip
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "variants.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["raw_name", "variant", "kind", "party_kind", "org_name_norm"])
            for raw in names:
                for variant, kind in debtor_name_variants(raw):
                    c = classify(variant) if kind == "alias" else None
                    org = c is not None and c.party_kind == "org" and bool(c.org_name_norm)
                    w.writerow([raw, variant, kind, "org" if org else "person",
                                c.org_name_norm if org and c else ""])  # fmt: skip
        cols = ("{'raw_name': 'VARCHAR', 'variant': 'VARCHAR', 'kind': 'VARCHAR', "
                "'party_kind': 'VARCHAR', 'org_name_norm': 'VARCHAR'}")  # fmt: skip
        sql = (f"CREATE OR REPLACE TEMP TABLE {table} AS SELECT raw_name, variant, kind, "  # noqa: S608
               "party_kind, nullif(org_name_norm, '') AS org_name_norm "
               f"FROM read_csv(?, header=true, columns={cols})")  # fmt: skip
        con.execute(sql, [str(path)])


VARIANT_INSERT_SQL = """
INSERT INTO owners
SELECT DISTINCT o.party_id, o.raw_name, v.party_kind, v.org_name_norm, o.parcel_uid,
       name_key(v.variant), suffix_key(v.variant), o.mail_key, o.mail_zip, o.situs_key,
       o.situs_zip, o.mail_town, o.situs_town, o.owner_basis, o.owner_seen_on, v.kind
FROM owners o JOIN owner_name_variant v ON v.raw_name = o.raw_name
WHERE o.name_variant IS NULL
  AND (v.party_kind = 'org' OR name_words(name_key(v.variant)) >= 2);
"""


def _owner_name_variants(con: duckdb.DuckDBPyConnection) -> None:
    """Owner strings that print several people, a trust or an alias: each name is an extra
    owner row of the same party and parcel."""
    name_variant_table(con, "owner_name_variant",
                       "SELECT raw_name FROM owners WHERE name_variant IS NULL")  # fmt: skip
    con.execute(VARIANT_INSERT_SQL)


# Debtor strings that print aliases or several people ("JOHN SMITH DBA SMITH PLUMBING",
# "JOHN SMITH AKA JACK SMITH", "JOHN & JANE SMITH"): each name joins the debtors as an extra
# row of the same party and instrument (equity.matching.names.debtor_name_variants), so a
# sole proprietor's trade-name lien reaches the person's house and the business's lots. A
# business alias keeps its org name (orgs.classify), so the org rules can meet it.
DEBTOR_VARIANT_INSERT_SQL = """
INSERT INTO debtors (party_id, raw_name, party_kind, org_name_norm, instrument_uid, source_id,
                     doc_type, recorded_on, principal_amount, released, name_key, suffix_key,
                     addr_key, town_key, zip5, county, name_variant, variant_name)
SELECT DISTINCT d.party_id, d.raw_name, v.party_kind, v.org_name_norm, d.instrument_uid,
       d.source_id, d.doc_type, d.recorded_on, d.principal_amount, d.released,
       name_key(v.variant), suffix_key(v.variant), d.addr_key, d.town_key, d.zip5, d.county,
       v.kind, v.variant
FROM debtors d JOIN debtor_name_variant v ON v.raw_name = d.raw_name
WHERE d.name_variant IS NULL
  AND (v.party_kind = 'org' OR name_words(name_key(v.variant)) >= 2);
"""


def _debtor_name_variants(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        "ALTER TABLE debtors ADD COLUMN name_variant VARCHAR;"
        "ALTER TABLE debtors ADD COLUMN variant_name VARCHAR"
    )
    name_variant_table(con, "debtor_name_variant", "SELECT raw_name FROM debtors")
    con.execute(DEBTOR_VARIANT_INSERT_SQL)


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
-- Who a people row is. A debtor party is one subject, except a lien that names several
-- people in one string ("JOHN & MARY DOE"): each of them is a subject of their own, and the
-- lien counts in each one's row (each is liable for it).
CREATE TEMP TABLE subjects AS
WITH split AS (SELECT DISTINCT party_id FROM debtors WHERE name_variant = 'joint')
SELECT DISTINCT party_id || '#' || name_key AS subject, party_id, name_key,
       variant_name AS name
FROM debtors WHERE name_variant = 'joint'
UNION ALL
SELECT DISTINCT party_id, party_id, NULL, NULL FROM debtors
WHERE party_id NOT IN (SELECT party_id FROM split);
CREATE TEMP TABLE debtor_identity AS
SELECT DISTINCT s.subject,
       CASE WHEN starts_with(d.party_id, 'owner-of:') THEN d.party_id
            WHEN d.party_kind = 'org' AND coalesce(d.org_name_norm, '') <> ''
            THEN 'org:' || d.org_name_norm || '|' || coalesce(d.addr_key, d.zip5, '')
            WHEN name_words(d.name_key) >= 2
            THEN 'person:' || d.name_key || '|' || coalesce(d.addr_key, d.zip5, '')
            ELSE 'party:' || d.party_id END AS identity
FROM debtors d JOIN subjects s ON s.party_id = d.party_id
-- A party's own name and its aliases name it; each joint name names its own subject; a
-- trust's settlor is someone else and merges nothing.
WHERE (s.name_key IS NULL AND coalesce(d.name_variant, 'alias') = 'alias')
   OR (s.name_key = d.name_key AND d.name_variant = 'joint');
-- A person's liens at "12 MAIN ST APT 3" and at "12 MAIN ST" (same name) are one person:
-- the unit row also takes the building row's identity, when there is one.
INSERT INTO debtor_identity
SELECT DISTINCT s.subject, 'person:' || d.name_key || '|' || b.base_key
FROM debtors d JOIN subjects s ON s.party_id = d.party_id
JOIN addr_base b ON b.addr_key = d.addr_key AND b.base_key <> d.addr_key
WHERE d.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND ((s.name_key IS NULL AND coalesce(d.name_variant, 'alias') = 'alias')
       OR (s.name_key = d.name_key AND d.name_variant = 'joint'))
  AND 'person:' || d.name_key || '|' || b.base_key IN (SELECT identity FROM debtor_identity);
-- The subject a match belongs to: one joint name's match is that person's; any other match
-- of a split party (the whole string, an address) belongs to every name on it.
CREATE TEMP TABLE match_subject AS
SELECT DISTINCT s.subject, m.debtor_party_id, m.instrument_uid, m.owner_party_id,
       m.parcel_uid, m.decision, m.owner_name_variant, m.debtor_name_variant
FROM matches m JOIN subjects s ON s.party_id = m.debtor_party_id
WHERE s.name_key IS NULL OR m.debtor_name_variant IS DISTINCT FROM 'joint'
   OR s.name_key = m.key;
-- Each group (an identity key, or an auto-matched owner party) is a star around its smallest
-- subject, both ways, so the edges grow with the subjects, not with the square of a group.
CREATE TEMP TABLE person_groups AS
SELECT subject, identity AS grp FROM debtor_identity
UNION
SELECT DISTINCT subject, 'owner:' || owner_party_id FROM match_subject
WHERE decision = 'auto' AND owner_party_id IS NOT NULL
  -- Two people who matched one joint owner string ("SMITH JOHN & JANE") are two people,
  -- and a split party's whole-string match is every name's, so it merges no one.
  AND coalesce(owner_name_variant, 'alias') = 'alias'
  AND coalesce(debtor_name_variant, 'alias') IN ('alias', 'joint')
  AND (debtor_name_variant = 'joint'
       OR debtor_party_id NOT IN (SELECT party_id FROM subjects WHERE name_key IS NOT NULL));
CREATE TEMP TABLE person_edges AS
WITH hub AS (SELECT grp, min(subject) AS h FROM person_groups GROUP BY grp)
SELECT DISTINCT * FROM (
    SELECT g.subject AS x, hub.h AS y FROM person_groups g JOIN hub USING (grp)
    UNION ALL
    SELECT hub.h, g.subject FROM person_groups g JOIN hub USING (grp)
    UNION ALL
    SELECT subject, subject FROM person_groups);
CREATE TEMP TABLE subject_of AS
SELECT x AS subject, min(y) AS person_id FROM person_edges GROUP BY x;
"""
PEOPLE_MERGE_STEP_SQL = """
CREATE OR REPLACE TEMP TABLE subject_of AS
SELECT e.x AS subject, min(p.person_id) AS person_id
FROM person_edges e JOIN subject_of p ON p.subject = e.y GROUP BY e.x;
"""
PEOPLE_SUMMARY_SQL = """
-- party -> person (a split party maps to each of its people).
CREATE TEMP TABLE person_of AS
SELECT DISTINCT s.party_id, so.person_id
FROM subject_of so JOIN subjects s USING (subject);
CREATE TEMP TABLE people AS
WITH j AS (
    SELECT so.person_id, d.instrument_uid, any_value(d.source_id) AS source_id,
           any_value(d.doc_type) AS doc_type, bool_or(d.released) AS released,
           any_value(d.principal_amount) AS amount,
           any_value(coalesce(s.name, d.raw_name)) AS raw_name
    FROM debtors d JOIN subjects s ON s.party_id = d.party_id
    JOIN subject_of so ON so.subject = s.subject
    GROUP BY so.person_id, d.instrument_uid
), lots AS (
    SELECT DISTINCT so.person_id, m.parcel_uid
    FROM match_subject m JOIN subject_of so ON so.subject = m.subject
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
# Every address and the addresses it counts as: itself, and, for a unit, its building
# without the unit ("12 MAIN ST APT 3" <-> "12 MAIN ST"; two different units never pair).
# Every address rule below joins through addr_alias, so a unit never hides a match.
ADDR_ALIAS_SQL = """
CREATE TEMP TABLE addr_base AS
SELECT addr_key, min(base_key) AS base_key FROM addr
WHERE addr_key IS NOT NULL AND base_key IS NOT NULL GROUP BY addr_key;
CREATE TEMP TABLE unit_pair AS
WITH u AS (SELECT addr_key, base_key FROM addr_base WHERE base_key <> addr_key)
SELECT addr_key AS a, base_key AS b FROM u UNION SELECT base_key, addr_key FROM u;
CREATE TEMP TABLE addr_alias AS
SELECT DISTINCT addr_key AS k, addr_key AS k2 FROM addr WHERE addr_key IS NOT NULL
UNION SELECT a, b FROM unit_pair;
"""
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
FROM debtors d JOIN addr_alias aa ON aa.k = d.addr_key JOIN o_by_addr o ON o.k = aa.k2
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
# Same name, and one address is the other without its unit ("12 MAIN ST APT 3" on the lien,
# "12 MAIN ST" on the roll, or the reverse). Two different units of one building never pair.
UNIT_SQL = """
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid,
       'person_name_address_unit', d.name_key
FROM debtors d JOIN unit_pair u ON u.a = d.addr_key
JOIN owners o ON o.name_key = d.name_key AND u.b IN (o.mail_key, o.situs_key)
WHERE d.party_kind <> 'org' AND o.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND NOT suffix_conflict(d.suffix_key, o.suffix_key)
UNION ALL
SELECT DISTINCT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid,
       'org_name_address_unit', d.org_name_norm
FROM debtors d JOIN unit_pair u ON u.a = d.addr_key
JOIN owners o ON o.org_name_norm = d.org_name_norm AND u.b IN (o.mail_key, o.situs_key)
WHERE d.party_kind = 'org' AND o.party_kind = 'org' AND d.org_name_norm <> '';
"""
# Same address, and the same name once nicknames are read as formal names (o_by_addr is
# INITIAL_SQL's owners-by-address table).
NICK_SQL = """
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid,
       'person_nickname_address', d.name_key
FROM debtors d JOIN addr_alias aa ON aa.k = d.addr_key JOIN o_by_addr o ON o.k = aa.k2
WHERE d.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND d.name_key <> o.name_key AND NOT suffix_conflict(d.suffix_key, o.suffix_key)
  AND nick_key(d.name_key) = nick_key(o.name_key);
"""

# Same address, the same number of name words, and exactly one word on each side differs
# from the other by one edit. Both words at least 3 letters, the words they share include a
# full word (not only initials), and not two real first names (first_names table).
TYPO_SQL = """
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid,
       'person_name_typo_address', d.name_key
FROM debtors d JOIN addr_alias aa ON aa.k = d.addr_key JOIN o_by_addr o ON o.k = aa.k2
WHERE d.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND NOT suffix_conflict(d.suffix_key, o.suffix_key)
  AND name_typo(d.name_key, o.name_key)
  AND NOT two_first_names(name_only(d.name_key, o.name_key)[1],
                          name_only(o.name_key, d.name_key)[1]);
"""
# Same address; one name is the other plus one full word (a middle name, a second surname),
# or the two differ only in a middle initial against a middle name that starts with it.
MIDDLE_SQL = """
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid,
       'person_middle_name_address', d.name_key
FROM debtors d JOIN addr_alias aa ON aa.k = d.addr_key JOIN o_by_addr o ON o.k = aa.k2
WHERE d.party_kind <> 'org' AND name_words(d.name_key) >= 2 AND name_words(o.name_key) >= 2
  AND d.name_key <> o.name_key AND NOT suffix_conflict(d.suffix_key, o.suffix_key)
  AND (
    -- one extra full word on one side, every other word shared
    (abs(name_words(d.name_key) - name_words(o.name_key)) = 1
     AND least(name_words(d.name_key), name_words(o.name_key)) >= 2
     AND ((len(name_only(d.name_key, o.name_key)) = 0
           AND len(name_only(o.name_key, d.name_key)) = 1
           AND length(name_only(o.name_key, d.name_key)[1]) >= 2)
          OR (len(name_only(o.name_key, d.name_key)) = 0
              AND len(name_only(d.name_key, o.name_key)) = 1
              AND length(name_only(d.name_key, o.name_key)[1]) >= 2)))
    -- an initial against a full word that starts with it
    OR (name_words(d.name_key) = name_words(o.name_key)
        AND len(name_only(d.name_key, o.name_key)) = 1
        AND len(name_only(o.name_key, d.name_key)) = 1
        AND least(length(name_only(d.name_key, o.name_key)[1]),
                  length(name_only(o.name_key, d.name_key)[1])) = 1
        AND greatest(length(name_only(d.name_key, o.name_key)[1]),
                     length(name_only(o.name_key, d.name_key)[1])) >= 2
        AND left(name_only(d.name_key, o.name_key)[1], 1)
            = left(name_only(o.name_key, d.name_key)[1], 1)));
"""
# Same address and the same letters once spaces are dropped (name keys keep apostrophes as
# word breaks: O'BRIEN is "O BRIEN"; a source that prints OBRIEN, DELACRUZ or MCDONALD is
# the same name).
SPACING_SQL = """
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid,
       'person_name_spacing_address', d.name_key
FROM debtors d JOIN addr_alias aa ON aa.k = d.addr_key JOIN o_by_addr o ON o.k = aa.k2
WHERE d.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND d.name_key <> o.name_key AND name_words(d.name_key) <> name_words(o.name_key)
  AND NOT suffix_conflict(d.suffix_key, o.suffix_key)
  AND list_sort(string_split(replace(d.name_key, ' ', ''), ''))
      = list_sort(string_split(replace(o.name_key, ' ', ''), ''));
"""


# Every name rule at once: loose_letters(k) is the sorted letters of a name key's full words
# (2+ letters) with nicknames read as formal names, loose_letters_all(k) the same with every
# word (an O of O BRIEN is a letter of the surname, not an initial); initials(k) its
# single-letter words.
LOOSE_SQL = """
CREATE OR REPLACE MACRO initials(k) AS list_sort(list_filter(string_split(k, ' '),
    lambda w: length(w) = 1));
CREATE OR REPLACE MACRO loose_letters(k) AS array_to_string(list_sort(string_split(
    array_to_string(list_filter(string_split(nick_key(k), ' '), lambda w: length(w) >= 2), ''),
    '')), '');
CREATE OR REPLACE MACRO loose_letters_all(k) AS array_to_string(list_sort(string_split(
    replace(nick_key(k), ' ', ''), '')), '');
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid,
       'person_loose_name_address', d.name_key
FROM debtors d JOIN addr_alias aa ON aa.k = d.addr_key JOIN o_by_addr o ON o.k = aa.k2
WHERE d.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND d.name_key <> o.name_key AND NOT suffix_conflict(d.suffix_key, o.suffix_key)
  AND len(list_filter(string_split(d.name_key, ' '), lambda w: length(w) >= 2)) >= 2
  AND len(list_filter(string_split(o.name_key, ' '), lambda w: length(w) >= 2)) >= 2
  AND (loose_letters(d.name_key) = loose_letters(o.name_key)
       OR loose_letters_all(d.name_key) = loose_letters_all(o.name_key))
  AND (len(initials(d.name_key)) = 0 OR len(initials(o.name_key)) = 0
       OR initials(d.name_key) = initials(o.name_key));
"""


def first_names(con: duckdb.DuckDBPyConnection) -> None:
    """first_names(name): every first name in the 1990 Census lists (data/first_names_1990.txt)."""
    path = Path(__file__).parent / "data" / "first_names_1990.txt"
    con.execute(
        "CREATE OR REPLACE TEMP TABLE first_names AS SELECT DISTINCT name FROM read_csv(?, "
        "header=false, comment='#', columns={'name': 'VARCHAR'})",
        [str(path)],
    )
    # name_only(a, b): the words of name key a that are not in b. name_typo(a, b): the same
    # number of words, exactly one differing word on each side, those two words at least 3
    # letters and one edit apart (added, dropped, changed or two swapped), and a shared word
    # of at least 2 letters (not only initials). The caller rules out two real first names.
    from equity.matching.nicknames import SAME_NAME_PAIRS

    con.execute("CREATE OR REPLACE TEMP TABLE same_name_pairs (a VARCHAR, b VARCHAR)")
    con.executemany("INSERT INTO same_name_pairs VALUES (?, ?)",
                    [p for a, b in SAME_NAME_PAIRS for p in ((a, b), (b, a))])  # fmt: skip
    # two_first_names(x, y): both words are real first names and not two spellings of one
    # (JOHN / JOAN: two people; JOHN / JON: one name).
    con.execute("""
        CREATE OR REPLACE MACRO two_first_names(x, y) AS
            x IN (SELECT name FROM first_names) AND y IN (SELECT name FROM first_names)
            AND (x, y) NOT IN (SELECT (a, b) FROM same_name_pairs);
    """)
    con.execute("""
        CREATE OR REPLACE MACRO name_only(a, b) AS list_filter(string_split(a, ' '),
            lambda x: NOT list_contains(string_split(b, ' '), x));
        CREATE OR REPLACE MACRO name_typo(a, b) AS
            a <> b AND name_words(a) = name_words(b)
            AND len(name_only(a, b)) = 1 AND len(name_only(b, a)) = 1
            AND length(name_only(a, b)[1]) >= 3 AND length(name_only(b, a)[1]) >= 3
            AND damerau_levenshtein(name_only(a, b)[1], name_only(b, a)[1]) = 1
            AND len(list_filter(string_split(a, ' '),
                    lambda y: list_contains(string_split(b, ' '), y) AND length(y) >= 2)) >= 1;
    """)


def nick_macro(con: duckdb.DuckDBPyConnection) -> None:
    """nick_key(k): a name key with each nickname replaced by its formal name, re-sorted."""
    from equity.matching.nicknames import nickname_map

    pairs = ", ".join(f"'{k}': '{v}'" for k, v in sorted(nickname_map().items()))
    con.execute(f"""
        CREATE OR REPLACE MACRO nick_key(k) AS array_to_string(list_sort(list_distinct(
            list_transform(string_split(k, ' '), lambda w: coalesce(MAP {{{pairs}}}[w], w)))),
            ' ');
    """)


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

# Company names one way: AND / & / THE, spaces and punctuation dropped.
ORG_LOOSE_MACRO = r"""
CREATE OR REPLACE MACRO org_loose(n) AS regexp_replace(regexp_replace(
    ' ' || upper(coalesce(n, '')) || ' ', '\b(AND|THE)\b|&', ' ', 'g'), '[^A-Z0-9]+', '', 'g');
"""
ORG_LOOSE_SQL = """
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid,
       CASE WHEN aa.k2 IN (o.mail_key, o.situs_key) THEN 'org_name_loose_address'
            ELSE 'org_name_loose_zip' END, d.org_name_norm
FROM debtors d JOIN owners o ON org_loose(o.org_name_norm) = org_loose(d.org_name_norm)
LEFT JOIN addr_alias aa ON aa.k = d.addr_key AND aa.k2 IN (o.mail_key, o.situs_key)
WHERE d.party_kind = 'org' AND o.party_kind = 'org' AND d.org_name_norm <> o.org_name_norm
  AND org_loose(d.org_name_norm) <> ''
  AND (aa.k2 IS NOT NULL OR (d.zip5 IS NOT NULL AND d.zip5 IN (o.mail_zip, o.situs_zip)));
"""
# A debtor or owner address with no ZIP has no address key: compare street line and city.
CITY_SQL = """
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid,
       'person_name_street_city', d.name_key
FROM debtors d JOIN owners o ON o.name_key = d.name_key
WHERE d.party_kind <> 'org' AND o.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND NOT suffix_conflict(d.suffix_key, o.suffix_key) AND d.town_key IS NOT NULL
  AND ((d.town_key = o.mail_town AND (d.addr_key IS NULL OR o.mail_key IS NULL))
       OR (d.town_key = o.situs_town AND (d.addr_key IS NULL OR o.situs_key IS NULL)))
UNION ALL
SELECT DISTINCT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid,
       'org_name_street_city', d.org_name_norm
FROM debtors d JOIN owners o ON o.org_name_norm = d.org_name_norm
WHERE d.party_kind = 'org' AND o.party_kind = 'org' AND d.org_name_norm <> ''
  AND d.town_key IS NOT NULL
  AND ((d.town_key = o.mail_town AND (d.addr_key IS NULL OR o.mail_key IS NULL))
       OR (d.town_key = o.situs_town AND (d.addr_key IS NULL OR o.situs_key IS NULL)));
"""

# Two addresses one name is known at: a deed, mortgage or owner-role record's party at the
# parcel's property address and at their own address; and one owner name at two mailing
# addresses for one parcel (across roll years). Both directions are kept.
HISTORY_FROM_RECORDS_SQL = """
INSERT INTO addr_history
SELECT DISTINCT name_key(p.raw_name), sa.addr_key, pa.addr_key
FROM ro_ip ip JOIN ro_party p ON p.party_id = ip.party_id
JOIN ro_lot l ON l.instrument_uid = ip.instrument_uid
JOIN roll_lot rl ON rl.k = parcel_key(l.parcel_uid)
JOIN o_parcel pc ON pc.parcel_uid = rl.parcel_uid
JOIN addr sa ON sa.address_id = pc.situs_address_id
JOIN addr pa ON pa.address_id = p.address_id
WHERE ip.role IN ('grantor', 'grantee', 'borrower', 'owner')
  AND coalesce(p.party_kind, '') <> 'org' AND name_words(name_key(p.raw_name)) >= 2
  AND sa.addr_key IS NOT NULL AND pa.addr_key IS NOT NULL AND sa.addr_key <> pa.addr_key;
"""
FORMER_SQL = """
INSERT INTO addr_history
SELECT DISTINCT o1.name_key, o1.mail_key, o2.mail_key
FROM owners o1 JOIN owners o2 ON o2.parcel_uid = o1.parcel_uid AND o2.name_key = o1.name_key
WHERE o1.party_kind <> 'org' AND name_words(o1.name_key) >= 2
  AND coalesce(o1.name_variant, 'alias') = 'alias'
  AND o1.mail_key IS NOT NULL AND o2.mail_key IS NOT NULL AND o1.mail_key <> o2.mail_key;
CREATE OR REPLACE TEMP TABLE addr_hist AS
SELECT name_key, a, b FROM addr_history UNION SELECT name_key, b, a FROM addr_history;
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, o.party_id, o.parcel_uid,
       'person_name_former_address', d.name_key
FROM debtors d JOIN addr_alias aa ON aa.k = d.addr_key
JOIN addr_hist h ON h.name_key = d.name_key AND h.a = aa.k2
JOIN owners o ON o.name_key = d.name_key AND h.b IN (o.mail_key, o.situs_key)
WHERE d.party_kind <> 'org' AND o.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND NOT suffix_conflict(d.suffix_key, o.suffix_key) AND h.b <> d.addr_key;
"""

# Parcels no source names an owner for (California rolls publish none): a debtor whose own
# address is the lot's property address may own it or may rent it, so these are review only.
# The roll's homeowner (owner-occupied) exemption for the latest year says an owner lives
# there, which ranks the lead above a plain address match. No name is compared: there is none.
NAMELESS_SQL = """
CREATE TEMP TABLE nameless_lots AS
WITH occ AS (
    SELECT parcel_uid, arg_max(homestead, tax_year) AS homestead FROM o_assess
    WHERE homestead IS NOT NULL GROUP BY parcel_uid
)
SELECT DISTINCT pc.parcel_uid, a.addr_key, coalesce(occ.homestead, false) AS owner_occupied
FROM o_parcel pc JOIN addr a ON a.address_id = pc.situs_address_id
LEFT JOIN occ ON occ.parcel_uid = pc.parcel_uid
WHERE a.addr_key IS NOT NULL
  AND pc.parcel_uid NOT IN (SELECT parcel_uid FROM owners);
-- One address can be many lots (condo units, a building split into parcels): only an
-- address that is one nameless lot is a lead.
CREATE TEMP TABLE nameless_one AS
SELECT addr_key, min(parcel_uid) AS parcel_uid, bool_or(owner_occupied) AS owner_occupied
FROM nameless_lots GROUP BY addr_key HAVING count(DISTINCT parcel_uid) = 1;
-- Through addr_alias, a debtor in a unit reaches its building's lot and the reverse; an
-- address that reaches more than one nameless lot that way (a condo building's units) is
-- no lead, and a unit's homeowner exemption says nothing about its neighbour: a lot reached
-- through its unit pair is person_at_property.
INSERT INTO candidates
WITH hits AS (
    SELECT DISTINCT d.party_id, d.instrument_uid, d.addr_key, n.parcel_uid,
           n.owner_occupied AND aa.k = aa.k2 AS occupied
    FROM debtors d JOIN addr_alias aa ON aa.k = d.addr_key
    JOIN nameless_one n ON n.addr_key = aa.k2
    WHERE d.party_kind <> 'org' AND name_words(d.name_key) >= 2
), one AS (
    SELECT addr_key FROM hits GROUP BY addr_key HAVING count(DISTINCT parcel_uid) = 1
)
SELECT DISTINCT party_id, instrument_uid, NULL, parcel_uid,
       CASE WHEN occupied THEN 'person_at_owner_occupied_property'
            ELSE 'person_at_property' END, addr_key
FROM hits WHERE addr_key IN (SELECT addr_key FROM one);
"""

# A company owner whose tax bill goes to a person debtor's own address. An address that takes
# bills for more owner names than this is an office (a property manager, a law firm, a bank's
# escrow desk), not someone's home. TODO(Brandon): confirm 10.
MAIL_SHARED_MAX = 10
ORG_MAILING_SQL = f"""
CREATE TEMP TABLE org_mail AS
WITH busy AS (
    SELECT mail_key FROM owners WHERE mail_key IS NOT NULL
    GROUP BY mail_key
    HAVING count(DISTINCT coalesce(nullif(org_name_norm, ''), name_key)) > {MAIL_SHARED_MAX}
    -- An office building's suites each take few bills; the building takes many.
    UNION
    SELECT o.mail_key FROM owners o JOIN addr_base b ON b.addr_key = o.mail_key
    WHERE b.base_key IN (
        SELECT b2.base_key FROM owners o2 JOIN addr_base b2 ON b2.addr_key = o2.mail_key
        GROUP BY b2.base_key
        HAVING count(DISTINCT coalesce(nullif(o2.org_name_norm, ''), o2.name_key))
               > {MAIL_SHARED_MAX})
), own_lot AS (  -- the company's own property: its tenants share the address
    SELECT DISTINCT org_name_norm, situs_key FROM owners
    WHERE party_kind = 'org' AND situs_key IS NOT NULL
)
SELECT DISTINCT o.party_id, o.parcel_uid, o.mail_key FROM owners o
WHERE o.party_kind = 'org' AND coalesce(o.org_name_norm, '') <> '' AND o.mail_key IS NOT NULL
  AND o.mail_key NOT IN (SELECT mail_key FROM busy)
  AND NOT EXISTS (SELECT 1 FROM own_lot l
                  WHERE l.org_name_norm = o.org_name_norm AND l.situs_key = o.mail_key);
INSERT INTO candidates
SELECT DISTINCT d.party_id, d.instrument_uid, m.party_id, m.parcel_uid,
       'person_at_org_owner_mailing', d.addr_key
FROM debtors d JOIN addr_alias aa ON aa.k = d.addr_key JOIN org_mail m ON m.mail_key = aa.k2
WHERE d.party_kind <> 'org' AND name_words(d.name_key) >= 2;
"""  # noqa: S608 - the cap is a constant


def _table_exists(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    row = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
    ).fetchone()
    return bool(row and row[0])


def match(
    con: duckdb.DuckDBPyConnection,
    street_town: bool = False,
    parcel_on_lien: bool = False,
    courts: bool = False,
) -> None:
    con.execute(ADDR_ALIAS_SQL)
    con.execute(MATCH_SQL)
    con.execute(COURT_COUNTY_SQL)
    con.execute(INITIAL_SQL)
    nick_macro(con)
    con.execute(NICK_SQL)
    first_names(con)
    con.execute(TYPO_SQL)
    con.execute(MIDDLE_SQL)
    con.execute(SPACING_SQL)
    con.execute(ORG_LOOSE_MACRO)
    con.execute(ORG_LOOSE_SQL)
    con.execute(CITY_SQL)
    con.execute("CREATE OR REPLACE TEMP TABLE addr_history (name_key VARCHAR, a VARCHAR, "
                "b VARCHAR)")  # fmt: skip
    if _table_exists(con, "roll_lot"):
        con.execute(HISTORY_FROM_RECORDS_SQL)
    con.execute(FORMER_SQL)
    con.execute(LOOSE_SQL)
    con.execute(UNIT_SQL)
    if parcel_on_lien:
        con.execute(PARCEL_ON_LIEN_SQL)
    if street_town:
        con.execute(STREET_TOWN_SQL)
    con.execute(NAMELESS_SQL)
    con.execute(ORG_MAILING_SQL)
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
        ALTER TABLE matches ADD COLUMN owner_basis VARCHAR;
        ALTER TABLE matches ADD COLUMN owner_seen_on DATE;
        UPDATE matches SET owner_basis = o.owner_basis, owner_seen_on = o.owner_seen_on
        FROM (SELECT party_id, parcel_uid, min(owner_basis) AS owner_basis,
                     max(owner_seen_on) AS owner_seen_on
              FROM owners GROUP BY party_id, parcel_uid) o
        WHERE o.party_id = matches.owner_party_id AND o.parcel_uid = matches.parcel_uid;
        UPDATE matches SET decision = 'review'
        WHERE decision = 'auto'
          AND (starts_with(coalesce(owner_basis, ''), 'record:')
               OR starts_with(coalesce(owner_basis, ''), 'mortgage:'))
          AND owner_seen_on < current_date - INTERVAL {RECORD_OWNER_AUTO_DAYS} DAY;
        -- Which name of the owner string the match used: NULL (the whole string), 'joint'
        -- (one of several owners printed together) or 'trust' (a trust's settlor/trustee).
        ALTER TABLE matches ADD COLUMN owner_name_variant VARCHAR;
        UPDATE matches SET owner_name_variant = v.variant
        FROM (SELECT party_id, parcel_uid, name_key,
                     CASE WHEN bool_or(name_variant IS NULL) THEN NULL
                          ELSE min(name_variant) END AS variant
              FROM owners GROUP BY party_id, parcel_uid, name_key) v
        WHERE v.party_id = matches.owner_party_id AND v.parcel_uid = matches.parcel_uid
          AND v.name_key = matches.key;
        UPDATE matches SET decision = 'review'
        WHERE decision = 'auto' AND owner_name_variant = 'trust';
        -- The same for the debtor's name: NULL, 'alias' (a DBA/AKA name of the same debtor),
        -- 'joint' or 'trust'. A trust's debt is not its settlor's own: review only.
        ALTER TABLE matches ADD COLUMN debtor_name_variant VARCHAR;
        UPDATE matches SET debtor_name_variant = v.variant
        FROM (SELECT party_id, instrument_uid, k,
                     CASE WHEN bool_or(name_variant IS NULL) THEN NULL
                          ELSE min(name_variant) END AS variant
              FROM (SELECT party_id, instrument_uid, name_key AS k, name_variant FROM debtors
                    UNION ALL
                    SELECT party_id, instrument_uid, org_name_norm, name_variant FROM debtors
                    WHERE org_name_norm IS NOT NULL)
              GROUP BY party_id, instrument_uid, k) v
        WHERE v.party_id = matches.debtor_party_id AND v.instrument_uid = matches.instrument_uid
          AND v.k = matches.key;
        UPDATE matches SET decision = 'review'
        WHERE decision = 'auto' AND debtor_name_variant = 'trust';
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


# A debt list that links more than this share of a run's owner parcels (and at least
# OUTLIER_FLOOR of them) is almost always a list that is not what it says: Gwinnett's weekly
# "delinquent" file carried the whole current tax roll and linked ~16% of Georgia's parcels.
OUTLIER_SHARE = 0.10
OUTLIER_FLOOR = 1000


def outliers(con: duckdb.DuckDBPyConnection) -> list[dict[str, object]]:
    """Debt sources whose automatic links cover an implausible share of the owner parcels."""
    rows = con.execute(
        "WITH tot AS (SELECT count(DISTINCT parcel_uid) AS n FROM owners),"
        " per AS (SELECT d.source_id, count(DISTINCT m.parcel_uid) AS n FROM matches m"
        " JOIN (SELECT DISTINCT instrument_uid, source_id FROM debtors) d"
        " USING (instrument_uid) WHERE m.decision = 'auto' AND m.parcel_uid IS NOT NULL"
        " GROUP BY 1)"
        " SELECT per.source_id, per.n, tot.n FROM per, tot"
        " WHERE per.n >= ? AND per.n > ? * tot.n ORDER BY per.n DESC, per.source_id",
        [OUTLIER_FLOOR, OUTLIER_SHARE],
    ).fetchall()
    return [{"source_id": sid, "parcels_linked": n, "owner_parcels": total,
             "share": round(n / total, 3)} for sid, n, total in rows]  # fmt: skip


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
        "outlier_sources": outliers(con),
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
    record_owner_sources: list[str] | None = None,
    state_fips: str | None = None,
    out_of_state: tuple[Path, str] | None = None,
) -> dict[str, object]:
    from equity.matching import bankruptcy, entities, equity, graph, review, transfers

    con = connect(lake, debtor_sources, owner_sources, parcel_on_lien, court_sources,
                  writ_sources, debtor_doc_types, record_owner_sources,
                  out_of_state)  # fmt: skip
    match(con, street_town, parcel_on_lien, bool(court_sources))
    review.build(con)
    tables = ["matches", "debtor_summary", "people", "person_of", "review_queue"]
    if registry_sources:
        entities.compute(con, lake, registry_sources, state_fips)
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
    graph.compute(con)  # last: it reads every step's links
    tables.extend(graph.TABLES)
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
    result["graph"] = graph.summary(con)
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
        "debtors": ["ny.dtf.child_support_warrants", "ny.dtf.tax_warrants", "ny.nyc.acris.real",
                    "ny.nyc.hpd_litigation", "ny.nyc.oath.judgments",
                    "ny.tompkins.foreclosure_parcels"],
        "owners": ["ny.local_rolls.parcels", "ny.statewide.parcels", "ny.nyc.parcels"],
        "mortgages": ["ny.nyc.acris.real"],
        "links": ["ny.nyc.dof.condo_units"],
        "courts": FEDERAL_COURTS,
        "registries": ["ny.sos.business", "ny.sos.name_history"],
        "deeds": ["ny.nyc.acris.real"],
        "record_owners": ["ny.nyc.dob_permits", "ny.nyc.dob_job_filings",
                          "ny.nyc.dob_legacy_permits", "ny.nyc.dob_electrical_permits",
                          "ny.nyc.lpc_permits", "ny.nyc.tax_commission_actions"],
    },
    # CT parcel data has no owner ZIP (Mailing_Zip is empty statewide): street + town instead.
    # Allegheny's parcel layer has no owner names, but its liens name the parcel (PIN).
    "PA-ALLEGHENY": {"debtors": ["pa.allegheny.delinquent_real_estate_taxes",
                                 "pa.allegheny.foreclosures", "pa.allegheny.tax_liens",
                                 "pa.pittsburgh.tax_delinquency", "pa.pittsburgh.treasury_sales"],
                     "owners": ["pa.allegheny.parcels", "pa.allegheny.assessments"],
                     "registries": ["pa.dos.business"], "parcel_on_lien": True,
                     "courts": FEDERAL_COURTS,
                     "record_owners": ["pa.pittsburgh.pli_permits",
                                       "pa.pittsburgh.condemned_properties"]},
    "CT": {"debtors": ["ct.sots.liens"], "owners": ["ct.statewide.parcels"], "street_town": True,
           "registries": ["ct.sos.business"], "courts": FEDERAL_COURTS,
           "deeds": ["ct.cama.sales"]},
    # Baltimore City: environmental citation liens name the parcel (block/lot), not a person.
    "MD-BALTIMORE": {"debtors": ["md.baltimore_city.citation_liens",
                                 "md.baltimore_city.in_rem_candidates",
                                 "md.baltimore_city.tax_lien_certificate_sale",
                                 "md.baltimore_city.tax_sale_2026"],
                     "owners": ["md.baltimore_city.parcels"], "parcel_on_lien": True,
                     "deeds": ["md.sdat.transfers_1", "md.sdat.transfers_2",
                               "md.sdat.transfers_3"],
                     "courts": FEDERAL_COURTS},
    # Travis: delinquent property tax accounts and tax-suit judgments, by owner name.
    # Dallas County Tax Office TRW roll: delinquent accounts by Dallas CAD account, the key of
    # the city's copy of the certified roll (Dallas and a one-mile buffer).
    "TX-DALLAS": {"debtors": ["tx.dallas.tax_roll_delinquent"],
                  "owners": ["tx.dallas_city.parcels"], "parcel_on_lien": True,
                  "courts": FEDERAL_COURTS},
    # Tarrant County Tax Office roll: delinquent accounts with owners and mailing addresses
    # (no parcel id in the statewide form), matched by name and address, as for Travis.
    "TX-TARRANT": {"debtors": ["tx.tarrant.tax_roll_delinquent"],
                   "owners": ["tx.statewide.parcels"], "courts": FEDERAL_COURTS},
    "TX-TRAVIS": {"debtors": ["tx.travis.tax_delinquent"], "owners": ["tx.statewide.parcels"],
                  "courts": FEDERAL_COURTS},
    # Omaha: tax sale certificates (named taxpayers) and county-held liens (PIN only).
    # Plus Nebraska's statewide delinquent-taxpayer list (named, with address) and Sarpy's
    # owners (the Omaha suburbs).
    # Nebraska's statewide layer has no owner names: the statewide delinquent-taxpayer list
    # and delinquent real-property lists against the
    # Lancaster, Cass, Douglas and Sarpy owner layers.
    "NE-COUNTIES": {"debtors": ["ne.dor.delinquent_real_property", "ne.dor.delinquent_taxpayers"],
                    "courts": FEDERAL_COURTS, "parcel_on_lien": True,
                    "owners": ["ne.cass.parcels", "ne.douglas.parcels", "ne.hall.parcels",
                               "ne.lancaster.parcels", "ne.sarpy.parcels"]},
    "NE-DOUGLAS": {"debtors": ["ne.douglas.tax_liens", "ne.dor.delinquent_taxpayers"],
                   "owners": ["ne.douglas.parcels", "ne.sarpy.parcels"],
                   "parcel_on_lien": True, "courts": FEDERAL_COURTS},
    # Colorado: federal tax and statutory (hospital, other) liens from the SOS UCC system;
    # UCC financing statements name debtors too but are not debts owed on a judgment or lien.
    # Lake County's tax lien sale list names the owner and the parcel.
    "CO": {"debtors": ["co.douglas.tax_lien_sale", "co.lake.tax_lien_sale",
                       "co.saguache.tax_lien_sale", "co.sos.ucc"],
           "debtor_doc_types": {"co.sos.ucc": ["TAX_LIEN_FEDERAL", "STATUTORY_LIEN"]},
           "owners": ["co.statewide.parcels"], "registries": ["co.sos.business"],
           "parcel_on_lien": True, "courts": FEDERAL_COURTS,
           "deeds": ["co.adams.property_sales", "co.denver.property_sales",
                     "co.douglas.property_sales"]},
    # Detroit blight judgments name both the owner and the ticketed parcel (same parcel_id as
    # the Detroit assessor layer); Harris tax-suit judgments name the HCAD account; Washington
    # County sheriff sales list every parcel sold.
    "MI-DETROIT": {"debtors": ["mi.detroit.blight_judgments"], "owners": ["mi.wayne.parcels"],
                   "parcel_on_lien": True, "courts": FEDERAL_COURTS,
                   "deeds": ["mi.detroit.property_sales"],
                   "record_owners": ["mi.detroit.demolition_permits",
                                     "mi.detroit.trades_permits",
                                     "mi.detroit.vacant_property_registrations"]},
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
           "deeds": ["fl.hillsborough.or", "fl.hernando.or", "fl.putnam.or"],
           "record_owners": ["fl.cape_coral.building_permits", "fl.miami_dade.building_permits",
                             "fl.orlando.permit_applications"]},
    # PA L&I lists name employers statewide; county parcel layers with owner names.
    "PA": {"debtors": ["pa.berks.upset_sale_unsold", "pa.cumberland.tax_sales",
                       "pa.dli.bllc_noncompliance", "pa.dli.bwc_noncompliance",
                       "pa.dli.uc_liens", "pa.montgomery.judicial_sale",
                       "pa.montgomery.upset_sale", "pa.philadelphia.li_fines",
                       "pa.philadelphia.tax_delinquencies", "pa.washington.judicial_sales",
                       "pa.washington.repository_sales", "pa.washington.sheriff_sales",
                       "pa.washington.upset_sales", "pa.west_chester.upset_sale"],
           "owners": ["pa.berks.parcels", "pa.bucks.parcels", "pa.chester.parcels",
                      "pa.erie.parcels", "pa.franklin.parcels", "pa.lancaster.parcels",
                      "pa.mercer.parcels", "pa.montgomery.parcels", "pa.philadelphia.parcels",
                      "pa.washington.parcels", "pa.york.parcels", "pa.cumberland.parcels",
                      "pa.luzerne.parcels"],
           "parcel_on_lien": True, "courts": FEDERAL_COURTS, "street_town": True,
           # Philadelphia RTT: mortgages and satisfactions on OPA lots (42101-<opa>), netted
           # by the owner-approved paid rules in equity.py; also the deed source for transfers.
           "deeds": ["pa.philadelphia.rtt"], "mortgages": ["pa.philadelphia.rtt"],
           "record_owners": ["pa.philadelphia.permits", "pa.philadelphia.violations",
                             "pa.philadelphia.appeals", "pa.philadelphia.clean_seal",
                             "pa.philadelphia.demolitions"]},
    # The PA and VT lists publish street and town but no ZIP: street + town rules, as in CT.
    "VT": {"debtors": ["vt.tax.top100_individuals", "vt.tax.top100_businesses"],
           "owners": ["vt.statewide.parcels"], "courts": FEDERAL_COURTS,
           "street_town": True,
           "deeds": ["vt.tax.property_transfers", "vt.tax.property_transfers_archive"]},
    # Chicago DOAH cites the property's street address with no ZIP: street + town rules.
    "IL-COOK": {"debtors": ["il.chicago.doah_judgments", "il.chicago.doe_judgments",
                            "il.chicago.vacant_building_judgments"], "owners": ["il.cook.parcels"],
                "deeds": ["il.cook.sales", "il.ptax.transfers"],
                "courts": FEDERAL_COURTS, "street_town": True},
    # New Orleans code judgments name the parcel (GeoPIN), not the owner.
    "LA-NOLA": {"debtors": ["la.nola.code_hearing_judgments"], "owners": ["la.orleans.parcels"],
                "courts": FEDERAL_COURTS, "parcel_on_lien": True,
                "record_owners": ["la.nola.permits"]},
    # Cincinnati lot abatement cites the property's address only: its parcel is found by
    # situs address (LOTS_SQL) and the charge is owed by that parcel's owner.
    "OH": {"debtors": ["oh.cincinnati.lot_abatement", "oh.clermont.tax_delinquent",
                       "oh.hamilton.delinquent_taxes", "oh.lucas.forfeited_land_sale",
                       "oh.mahoning.delinquent_taxes", "oh.medina.delinquent_taxes"],
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
                       "nc.charlotte.municipal_liens", "nc.pitt.delinquent_taxes"],
                    "owners": ["nc.statewide.parcels"], "parcel_on_lien": True,
                    "courts": FEDERAL_COURTS,
           "record_owners": ["nc.raleigh.building_permits"]},
    "AZ-COCHISE": {"debtors": ["az.cochise.tax_liens", "az.cochise.tax_deed_auction"],
                   "owners": ["az.cochise.parcels"],
                   "parcel_on_lien": True, "courts": FEDERAL_COURTS},
    "MS-HARRISON": {"debtors": ["ms.harrison.tax_sale_2026", "ms.harrison.tax_sale_parcels"],
                    "owners": ["ms.statewide.parcels"],
                    "parcel_on_lien": True, "courts": FEDERAL_COURTS},
    "AZ-PIMA": {"debtors": ["az.tucson.code_liens"], "owners": ["az.pima.parcels"],
                "courts": FEDERAL_COURTS},
    "PA-WASHINGTON": {"debtors": ["pa.washington.sheriff_sales"],
                      "owners": ["pa.washington.parcels"], "parcel_on_lien": True},
    # NYC lien sale notices and DOF past-due charges name no one: each is owed by the lot's
    # owner. A run of its own, so the NY run's ACRIS instruments do not take on parcel_on_lien.
    "NY-NYC-LIENSALE": {"debtors": ["ny.nyc.tax_lien_sale", "ny.nyc.dof.past_due_charges"],
                        "owners": ["ny.statewide.parcels", "ny.nyc.parcels"],
                        "parcel_on_lien": True},
    # St. Joseph IN tax sale: named owners and state parcel numbers. Indiana's statewide layer
    # has parcels but no owner names, so debtors link to the parcels their liens name.
    "IN-STJOSEPH": {"debtors": ["in.st_joseph.tax_sale"], "owners": ["in.statewide.parcels"],
                    "parcel_on_lien": True, "courts": FEDERAL_COURTS,
                    "deeds": ["in.st_joseph.transfer_history"]},
    # West Virginia, the pilot state: Bluefield's tax-delinquent list (names and addresses), plus
    # federal court judgments and the national debt lists against WV owners.
    "WV": {"debtors": ["wv.bluefield.tax_delinquent"], "owners": ["wv.statewide.parcels"],
           "courts": FEDERAL_COURTS},
    # States and counties whose parcel layers carry owner names and that have no county debt
    # list yet: federal court judgments and the national debt lists (SBA) against their owners.
    "MT": {"debtors": [], "owners": ["mt.statewide.parcels"], "courts": FEDERAL_COURTS},
    "ID": {"debtors": [], "owners": ["id.statewide.parcels"], "courts": FEDERAL_COURTS},
    # Pulaski adds the owner mailing addresses the statewide layer lacks.
    "AR": {"debtors": [], "owners": ["ar.statewide.parcels", "ar.pulaski.parcels"],
           "courts": FEDERAL_COURTS},
    "ND": {"debtors": [], "owners": ["nd.statewide.parcels"], "courts": FEDERAL_COURTS},
    "WY": {"debtors": [], "owners": ["wy.statewide.parcels"], "courts": FEDERAL_COURTS},
    "ME": {"debtors": [], "owners": ["me.statewide.parcels"], "courts": FEDERAL_COURTS},
    "MN": {"debtors": ["mn.carlton.tax_forfeited_land_sale", "mn.dakota.sheriff_sales",
                       "mn.mille_lacs.tax_forfeited_land", "mn.wright.tax_forfeited_land"],
           "owners": ["mn.statewide.parcels", "mn.metro.parcels"],
           "courts": FEDERAL_COURTS, "parcel_on_lien": True,
           "deeds": ["mn.grant.parcel_sales", "mn.isanti.parcel_sales", "mn.polk.parcel_sales"]},
    "MA": {"debtors": [], "owners": ["ma.statewide.parcels"], "courts": FEDERAL_COURTS},
    "NV-WASHOE": {"debtors": [], "owners": ["nv.washoe.parcels"], "courts": FEDERAL_COURTS},
    # Clark: the City of Las Vegas copy of the assessor roll (Las Vegas Valley only).
    "NV-COUNTIES": {"debtors": [], "courts": FEDERAL_COURTS,
                    "owners": ["nv.clark.parcels", "nv.lyon.parcels"],
                    "record_owners": ["nv.las_vegas.abandoned_property_registry"]},
    # County parcel layers with owner names in states (or counties) with no county debt list
    # yet: federal court judgments, the national debt lists (SBA 7(a)/504 and PPP charge-offs)
    # and the state's bankruptcy feeds against those owners.
    "AK": {"debtors": ["ak.fairbanks_north_star.tax_foreclosures"], "courts": FEDERAL_COURTS,
           "parcel_on_lien": True,
           "owners": ["ak.anchorage.parcels", "ak.fairbanks_north_star.parcels",
                      "ak.juneau.parcels", "ak.kenai_peninsula.parcels",
                      "ak.matanuska_susitna.parcels"]},
    "AL": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["al.blount.parcels", "al.cullman.parcels", "al.dekalb.parcels",
                      "al.houston.parcels", "al.jefferson.parcels", "al.lauderdale.parcels",
                      "al.madison.parcels", "al.marshall.parcels", "al.mobile.parcels",
                      "al.montgomery.parcels", "al.morgan.parcels", "al.talladega.parcels",
                      "al.tuscaloosa.parcels", "al.baldwin.parcels", "al.elmore.parcels",
                      "al.etowah.parcels"],
           "deeds": ["al.houston.last_deed", "al.lauderdale.last_deed"]},
    "AZ-COUNTIES": {"debtors": ["az.coconino.tax_liens", "az.navajo.back_tax_auction",
                                "az.yavapai.tax_sale"],
                    "courts": FEDERAL_COURTS,
                    "parcel_on_lien": True,
                    "owners": ["az.coconino.parcels", "az.mohave.parcels", "az.pinal.parcels",
                               "az.yavapai.parcels", "az.yuma.parcels", "az.apache.parcels",
                               "az.gila.parcels", "az.graham.parcels", "az.greenlee.parcels",
                               "az.la_paz.parcels", "az.navajo.parcels",
                               "az.santa_cruz.parcels"]},
    "GA": {"debtors": ["ga.albany.delinquent_taxes", "ga.gwinnett.delinquent_taxes",
                       "ga.dekalb.delinquent_taxes", "ga.richmond.delinquent_taxes"],
           "courts": FEDERAL_COURTS,
           "parcel_on_lien": True,
           "owners": ["ga.chatham.parcels", "ga.clayton.parcels", "ga.cobb.parcels",
                      "ga.dekalb.parcels", "ga.dougherty.parcels", "ga.fulton.parcels",
                      "ga.gwinnett.parcels", "ga.forsyth.parcels", "ga.cherokee.parcels",
                      "ga.clarke.parcels", "ga.bibb.parcels", "ga.richmond.parcels",
                      "ga.bartow.parcels", "ga.lowndes.parcels"]},
    "IA": {"debtors": [], "courts": FEDERAL_COURTS, "registries": ["ia.sos.business"],
           "owners": ["ia.blackhawk.parcels", "ia.dubuque.parcels", "ia.johnson.parcels",
                      "ia.linn.parcels", "ia.pottawattamie.parcels", "ia.scott.parcels",
                      "ia.story.parcels", "ia.woodbury.parcels"]},
    "IL-COLLAR": {"debtors": [], "courts": FEDERAL_COURTS,
                  "owners": ["il.dupage.parcels", "il.kane.parcels", "il.lake.parcels",
                             "il.mchenry.parcels"]},
    "IL-COUNTIES": {"debtors": [], "courts": FEDERAL_COURTS,
                    "owners": ["il.adams.parcels", "il.madison.parcels", "il.peoria.parcels",
                               "il.whiteside.parcels", "il.winnebago.parcels"]},
    "KS": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["ks.butler.parcels", "ks.douglas.parcels", "ks.shawnee.parcels",
                      "ks.wyandotte.parcels"]},
    "KY": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["ky.boone.parcels", "ky.campbell.parcels", "ky.kenton.parcels",
                      "ky.pendleton.parcels"]},
    "LA-EBR": {"debtors": [], "courts": FEDERAL_COURTS, "owners": ["la.eastbatonrouge.parcels"]},
    "LA-LAFAYETTE": {"debtors": [], "courts": FEDERAL_COURTS, "owners": ["la.lafayette.parcels"]},
    "LA-COUNTIES": {"debtors": [], "courts": FEDERAL_COURTS,
                    "owners": ["la.ascension.parcels", "la.livingston.parcels",
                               "la.st_bernard.parcels", "la.tangipahoa.parcels"]},
    # California: the state's top-500 delinquent taxpayer lists (FTB personal and corporate,
    # CDTFA) against the San Jose owner table, the only California owner source so far.
    # The four county rolls publish no owner names: their lots are found by property address
    # (nameless-lot review leads) and by the LA lists that name the parcel.
    "CA": {"debtors": ["ca.cdtfa.top500", "ca.ftb.top500_corporate", "ca.ftb.top500_personal",
                       "ca.los_angeles.defaulted_tax", "ca.los_angeles.registered_foreclosures"],
           "owners": ["ca.san_jose.parcels", "ca.losangeles.parcels", "ca.riverside.parcels",
                      "ca.sanbernardino.parcels", "ca.sandiego.parcels"],
           "courts": FEDERAL_COURTS, "parcel_on_lien": True,
           "record_owners": ["ca.san_jose.building_permits_active",
                             "ca.san_jose.building_permits_expired",
                             "ca.san_jose.building_permits_under_inspection"]},
    "MI-COUNTIES": {"debtors": ["mi.eaton.tax_foreclosure_sale", "mi.kalamazoo.delinquent_2024",
                                "mi.kalamazoo.delinquent_taxes", "mi.kalamazoo.foreclosed_2022",
                                "mi.kalamazoo.forfeited_2018", "mi.kalamazoo.forfeited_2020",
                                "mi.kalamazoo.forfeited_2023", "mi.kalamazoo.forfeited_2024",
                                "mi.kalamazoo.forfeited_parcels", "mi.lenawee.tax_sale"],
                    "courts": FEDERAL_COURTS,
                    "parcel_on_lien": True,
                    "owners": ["mi.barry.parcels", "mi.eaton.parcels", "mi.genesee.parcels",
                               "mi.ingham.parcels", "mi.kalamazoo.parcels", "mi.lenawee.parcels",
                               "mi.macomb.parcels", "mi.ottawa.parcels", "mi.allegan.parcels",
                               "mi.grand_traverse.parcels"]},
    "MO": {"debtors": ["mo.st_louis_county.post_third_sale"], "courts": FEDERAL_COURTS,
           "parcel_on_lien": True,
           "owners": ["mo.greene.parcels", "mo.jackson.parcels", "mo.st_louis_county.parcels",
                      "mo.jefferson.parcels", "mo.st_charles.parcels"]},
    "NH": {"debtors": [], "courts": FEDERAL_COURTS, "owners": ["nh.nrpc.parcels"]},
    "NM": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["nm.bernalillo.parcels", "nm.chaves.parcels", "nm.dona_ana.parcels",
                      "nm.grant.parcels", "nm.sandoval.parcels"]},
    "OK": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["ok.canadian.parcels", "ok.oklahoma.parcels", "ok.tulsa.parcels"]},
    "OR": {"debtors": [], "courts": FEDERAL_COURTS, "registries": ["or.sos.business"],
           "owners": ["or.deschutes.parcels", "or.jackson.parcels", "or.lane.parcels",
                      "or.multnomah.parcels", "or.josephine.parcels", "or.yamhill.parcels",
                      "or.klamath.parcels", "or.umatilla.parcels"]},
    "SC": {"debtors": ["sc.horry.delinquent_tax_sale", "sc.york.tax_sale",
                       "sc.beaufort.delinquent_taxes"],
           "courts": FEDERAL_COURTS,
           "parcel_on_lien": True,
           "owners": ["sc.charleston.parcels", "sc.georgetown.parcels", "sc.greenville.parcels",
                      "sc.horry.parcels", "sc.lancaster.parcels", "sc.lexington.parcels",
                      "sc.spartanburg.parcels", "sc.york.parcels", "sc.beaufort.parcels",
                      "sc.berkeley.parcels", "sc.dorchester.parcels", "sc.pickens.parcels",
                      "sc.sumter.parcels"]},
    # South Dakota's business-tax delinquents (a lien filed on each) against county owners.
    "SD": {"debtors": ["sd.dor.top_delinquent_business"], "courts": FEDERAL_COURTS,
           "owners": ["sd.beadle.parcels", "sd.codington.parcels", "sd.lincoln.parcels",
                      "sd.miner.parcels", "sd.minnehaha.parcels", "sd.pennington.parcels"]},
    "TN": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["tn.davidson.parcels", "tn.hamilton.parcels", "tn.rutherford.parcels",
                      "tn.washington.parcels", "tn.williamson.parcels", "tn.owners.parcels"],
           "deeds": ["tn.rutherford.last_sale"]},
    "UT": {"debtors": ["ut.box_elder.tax_sale"], "courts": FEDERAL_COURTS, "parcel_on_lien": True,
           "owners": ["ut.salt_lake.parcels", "ut.utah.parcels"]},
    "WA": {"debtors": [], "courts": FEDERAL_COURTS,
           "owners": ["wa.snohomish.parcels", "wa.spokane.parcels", "wa.thurston.parcels",
                      "wa.whatcom.parcels", "wa.grant.parcels", "wa.island.parcels",
                      "wa.kitsap.parcels"]},
    "VA-COUNTIES": {"debtors": ["va.fauquier.delinquent_taxes"], "courts": FEDERAL_COURTS,
                    "parcel_on_lien": True,
                    "owners": ["va.albemarle.parcels", "va.alexandria_city.parcels",
                               "va.chesapeake_city.parcels", "va.chesterfield.parcels",
                               "va.fauquier.parcels", "va.franklin_city.parcels",
                               "va.gloucester.parcels", "va.isle_of_wight.parcels",
                               "va.james_city.parcels", "va.loudoun.parcels",
                               "va.lynchburg_city.parcels", "va.newport_news_city.parcels",
                               "va.norfolk_city.parcels", "va.portsmouth_city.parcels",
                               "va.prince_william.parcels", "va.spotsylvania.parcels",
                               "va.suffolk_city.parcels", "va.virginia_beach_city.parcels",
                               "va.williamsburg_city.parcels", "va.york.parcels",
                               "va.roanoke_county.parcels"],
                    "deeds": ["va.norfolk.property_transfers"],
                    "record_owners": ["va.lynchburg.building_permits",
                                      "va.lynchburg.code_violations"]},
    # Ohio's statewide Name field is a placeholder: county layers carry the owner names.
    "OH-COUNTIES": {"debtors": ["oh.cuyahoga.delinquent_taxes", "oh.cuyahoga.forfeited_land_sale",
                                "oh.franklin.tax_lien_sale", "oh.franklin.delinquent_taxes",
                                "oh.greene.delinquent_taxes",
                                "oh.lorain.delinquent_taxes", "oh.lorain.forfeited_land_sale",
                                "oh.stark.delinquent_taxes", "oh.stark.foreclosures",
                                "oh.stark.civil_sales"],
                    "courts": FEDERAL_COURTS,
                    "parcel_on_lien": True,
                    "owners": ["oh.clermont.parcels", "oh.cuyahoga.parcels",
                               "oh.fairfield.parcels", "oh.franklin.parcels", "oh.greene.parcels",
                               "oh.holmes.parcels", "oh.lake.parcels", "oh.licking.parcels",
                               "oh.lorain.parcels", "oh.lucas.parcels", "oh.mahoning.parcels",
                               "oh.pickaway.parcels", "oh.stark.parcels", "oh.summit.parcels",
                               "oh.tuscarawas.parcels", "oh.wayne.parcels", "oh.delaware.parcels",
                               "oh.union.parcels"],
                    "deeds": ["oh.cuyahoga.last_transfer"],
                    "record_owners": ["oh.franklin.rental_contacts"]},
    "TX-COUNTIES": {"debtors": ["tx.tabc.credit_law_delinquent"], "courts": FEDERAL_COURTS,
                    "owners": ["tx.collin.parcels", "tx.dallas_city.parcels",
                               "tx.montgomery.parcels", "tx.williamson.parcels",
                               "tx.travis.parcels"],
                    "record_owners": ["tx.collin.cad_building_permits"]},
    "MD-COUNTIES": {"debtors": ["md.st_marys.tax_sale"], "courts": FEDERAL_COURTS,
                    "owners": ["md.anne_arundel.parcels", "md.baltimore_county.parcels",
                               "md.charles.parcels", "md.montgomery.parcels", "md.st_marys.parcels",
                               "md.washington.parcels", "md.wicomico.parcels"],
                   "parcel_on_lien": True},
    # NJ wage-theft lists name employers; Monmouth's parcel layer names owners (SR-1A is blank).
    "NJ-MONMOUTH": {"debtors": ["nj.dol.wage_watchlist", "nj.dol.wall"], "courts": FEDERAL_COURTS,
                    "owners": ["nj.monmouth.parcels"]},
    # Prince George's County MD owners (the county's property file; MD's statewide layer has no
    # owner names) against the national lists and the MD bankruptcy feeds.
    # Its Foreclosed Property Registry names no one: each filing links to the parcel's owner.
    "MD-PRINCE-GEORGES": {"debtors": ["md.prince_georges.foreclosures"],
                          "owners": ["md.prince_georges.parcels"],
                          "courts": FEDERAL_COURTS, "parcel_on_lien": True},
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
    "IN": {"debtors": ["in.delaware.tax_sale", "in.delaware.tax_sale_results",
                       "in.st_joseph.tax_sale"],
           "owners": ["in.statewide.parcels", "in.marion.parcels", "in.vanderburgh.parcels",
                      "in.lake.parcels"],
           "parcel_on_lien": True,
           "courts": FEDERAL_COURTS,
           "deeds": ["in.st_joseph.transfer_history"],
           "record_owners": ["in.dlgf.sales_disclosures"]},
    # DC: prior-year real property tax owed by the lot's owner (OTR extract, keyed by SSL).
    "DC": {"debtors": ["dc.otr.delinquent_taxes"], "owners": ["dc.statewide.parcels"],
           "parcel_on_lien": True, "registries": ["dc.dlcp.business"], "courts": FEDERAL_COURTS,
           "record_owners": ["dc.dob.building_permits", "dc.otr.vacant_blighted"]},
}  # fmt: skip


# Every lake table a state's match reads (for pulling just these onto a fresh machine).
TABLES_READ = ("address", "party", "instrument", "instrument_party", "instrument_ref",
               "instrument_parcel", "owner_snapshot", "parcel", "parcel_assessment",
               "parcel_link", "business", "business_role", "judgment", "judgment_event",
               "case_party", "court_case", "docket_entry")  # fmt: skip


# Lists that name the people behind businesses nationwide (carrier officers, NPI authorized
# officials, 990 officers, Form D related persons, insiders, adviser owners, mine controllers,
# FCC licensees, lobbying registrants). Every run reads them, plus its own state's license
# boards, as extra registries filtered to the run's state; they are optional: a run never
# fails for want of them (missing_sources leaves them out), and --list-sources names them
# under "optional_sources" so a loader can pull them.
NATIONAL_REGISTRIES = ["us.cms.nppes", "us.dol.msha_mines", "us.fcc.uls_amateur",
                       "us.fcc.uls_gmrs", "us.fcc.uls_land_mobile_broadcast",
                       "us.fcc.uls_land_mobile_commercial", "us.fcc.uls_land_mobile_private",
                       "us.fmcsa.carrier_census", "us.irs.990_officers", "us.sec.form_d",
                       "us.sec.iapd_advisers", "us.sec.insiders",
                       "us.senate.lda_registrants"]  # fmt: skip


def run_state(state: str) -> str:
    """A run's two-letter state: 'PA-ALLEGHENY' -> 'PA'."""
    return state.split("-", 1)[0]


def optional_registries(state: str) -> list[str]:
    """National people-behind-business lists plus the run's state license boards."""
    from equity.adapters.licenses import all_license_adapters

    prefix = run_state(state).lower() + "."
    boards = {a.source_id for a in all_license_adapters() if a.source_id.startswith(prefix)}
    return sorted(set(NATIONAL_REGISTRIES) | boards)


def bankruptcy_sources(state: str) -> list[str]:
    """The enabled bankruptcy-court RSS feeds of a run's state ('OH', 'WI-MILWAUKEE' -> WI)."""
    from equity.matching.bankruptcy import sources_for

    return sources_for(state.split("-", 1)[0])


def state_sources(state: str) -> list[str]:
    """Every source a state's match reads: debtors, owners, mortgages, links, registries."""
    spec = STATES[state]
    keys = ("debtors", "owners", "mortgages", "links", "registries", "deeds", "record_owners")
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
        print(json.dumps({"sources": state_sources(args.state), "tables": list(TABLES_READ),
                          "optional_sources": optional_registries(args.state)}))  # fmt: skip
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
                 spec.get("courts"), spec.get("writs"),
                 [*(spec.get("registries") or []), *optional_registries(args.state)],
                 spec.get("debtor_doc_types"), bankruptcy_sources(args.state),
                 spec.get("deeds"),
                 [*(spec.get("deeds") or []), *(spec.get("record_owners") or []),
                  *(spec.get("mortgages") or [])],
                 state_fips(run_state(args.state)),
                 (args.out / "_national" / "out_of_state_owners.parquet",
                  run_state(args.state)))  # fmt: skip
    result["missing_sources"] = missing
    summary = args.out / args.state.lower() / "summary.json"
    summary.write_text(json.dumps(result, indent=2, default=str))
    json.dump(result, sys.stdout, indent=2, default=str)
    print()
    flagged = result.get("outlier_sources")
    for o in flagged if isinstance(flagged, list) else []:
        print(f"WARNING: {o['source_id']} links {o['parcels_linked']} of {o['owner_parcels']}"
              f" owner parcels ({o['share']:.0%}); check that the list is debts only",
              file=sys.stderr)  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
