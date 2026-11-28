"""Business registries in matching: the people behind owner companies, and the companies (and
their property) behind debtors. Exact joins only, no scores.

Runs after equity.matching.resolve has built `debtors` and `owners` on the same connection.
Registry sources give `business` (entity id, name, status), `business_role` (entity id, party,
role, title) and the role holders' `party` and `address` rows.

  org key     a registry name normalized exactly as the loader normalizes organization names
              (equity.matching.orgs.classify: upper case, no punctuation, trailing entity
              form such as LLC/INC/CORP dropped). Corporate names are unique within a state's
              registry, so an owner organization joins the registry entity with the same key
              in that state. A key shared by more than one entity id (a dissolved entity and a
              newer one of the same name) is kept for every id and flagged `ambiguous`.
              Every name an entity has carried keys it (name-history sources such as
              ny.sos.name_history add former and assumed names), so an old name still
              reaches the entity; the current name is what the outputs show.

Registries a run reads: its state's SOS registry (STATES "registries"), plus, optionally,
the national lists that name the people behind businesses (FMCSA carrier officers, NPI
authorized officials, IRS 990 officers, SEC Form D related persons, insiders and adviser
owners, MSHA mine controllers, FCC licensees, lobbying registrants) and the state's license
boards (resolve.optional_registries). All are filtered to businesses whose jurisdiction is in
the run's state: an organization name is unique only within one state.

Outputs (Parquet in the state's derived folder, git-ignored: they name people):
  owner_companies   owner organization -> registry entity, per parcel
  company_people    registry entity -> role holders (role, title, name, address)
  debtor_companies  debtor -> registry entity:
                      org_name_registry      organization debtor, same org key        auto
                      org_name_registry_loose  the same once AND / & / THE, spaces and
                                             punctuation are dropped                  auto
                      person_officer_address person debtor, same name_key and address
                                             as a role holder                        auto
                      person_officer_zip     same name_key and ZIP                     review
                      person_officer_nickname / person_officer_typo  at the officer's
                                             address, a nickname or one-letter typo of the
                                             officer's name                            review
                    (an address also counts as its building without the unit)
                    (the same evidence levels as the debtor-owner rules)
  debtor_company_parcels  parcels owned by a debtor's registry entities
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from equity.matching.orgs import _FORMS


def org_key_macro(con: duckdb.DuckDBPyConnection) -> None:
    """org_key(name): the loader's org_name_norm for a name that ends in an entity form, else
    the cleaned name. Built from orgs._FORMS in order, so both sides normalize identically."""
    clean = ("trim(regexp_replace(regexp_replace(replace(upper(coalesce(n, '')), '.', ''), "
             "'[^A-Z0-9& ]+', ' ', 'g'), '\\s+', ' ', 'g'))")  # fmt: skip
    cases = []
    for phrase, _form in _FORMS:
        p = phrase.replace("'", "''")
        cases.append(f"WHEN c <> '{p}' AND ends_with(c, ' {p}') "
                     f"THEN trim(left(c, length(c) - {len(phrase) + 1}))")  # fmt: skip
    con.execute(f"""
        CREATE OR REPLACE MACRO org_key_clean(c) AS
            CASE {" ".join(cases)} ELSE c END;
        CREATE OR REPLACE MACRO org_key(n) AS org_key_clean({clean});
    """)


def attach(
    con: duckdb.DuckDBPyConnection, lake: Path, sources: list[str], state_fips: str | None = None
) -> None:
    """Registry views. With state_fips, only businesses of that state (jurisdiction is the
    state's FIPS or one of its counties'): national lists (FMCSA carriers, NPI providers, IRS
    990 filers, SEC filers) and other states' license boards carry the same names elsewhere,
    and an organization name is only unique within one state's registry."""
    from equity.matching.resolve import _view

    _view(con, "r_business_all", lake, sources, "business")
    keep = (f"jurisdiction IS NULL OR left(jurisdiction, 2) = '{state_fips}'"
            if state_fips else "true")  # fmt: skip
    con.execute(f"CREATE TEMP VIEW r_business AS SELECT * FROM r_business_all WHERE {keep}")  # noqa: S608
    _view(con, "r_role", lake, sources, "business_role")
    _view(con, "r_party", lake, sources, "party")
    _view(con, "r_addr", lake, sources, "address")


SQL = """
CREATE TEMP TABLE biz AS
SELECT sos_id,
       -- The registry's current name; a name-history row only when nothing else names it.
       arg_max(name, CASE WHEN status IN ('former name', 'active name') THEN 0 ELSE 1 END)
           AS business_name,
       arg_max(status, CASE WHEN status IN ('former name', 'active name') THEN 0 ELSE 1 END)
           AS status,
       org_key(arg_max(name, CASE WHEN status IN ('former name', 'active name') THEN 0
                                  ELSE 1 END)) AS org_key
FROM r_business WHERE sos_id IS NOT NULL AND name IS NOT NULL GROUP BY sos_id;
-- Every name an entity has carried (current, former, assumed) keys it, so a deed or a debt in
-- an old name reaches the entity under its new one.
CREATE TEMP TABLE biz_by_key AS
SELECT org_key, list(DISTINCT sos_id ORDER BY sos_id) AS ids FROM (
    SELECT sos_id, org_key(name) AS org_key FROM r_business
    WHERE sos_id IS NOT NULL AND name IS NOT NULL)
WHERE org_key <> '' GROUP BY org_key;
-- The same with AND / & / THE, spaces and punctuation dropped (resolve.org_loose): "SMITH AND
-- SONS LLC" on the roll reaches the registry's "SMITH & SONS, LLC".
CREATE TEMP TABLE biz_by_loose AS
SELECT org_loose(org_key) AS loose, list(DISTINCT sos_id ORDER BY sos_id) AS ids FROM (
    SELECT sos_id, org_key(name) AS org_key FROM r_business
    WHERE sos_id IS NOT NULL AND name IS NOT NULL)
WHERE org_loose(org_key) <> '' GROUP BY 1;
CREATE TEMP TABLE company_people AS
SELECT DISTINCT r.sos_id, b.business_name, r.role, r.title, p.party_id, p.raw_name AS name,
       p.party_kind, name_key(p.raw_name) AS name_key, suffix_key(p.raw_name) AS suffix_key,
       CASE WHEN street_norm(a.line1) <> '' AND a.zip5 IS NOT NULL
            THEN street_norm(a.line1) || '|' || a.zip5 END AS addr_key,
       -- The building without a unit (resolve.UNIT_MACRO), so "12 MAIN ST STE 4" on a filing
       -- meets a debtor at "12 MAIN ST".
       CASE WHEN len(string_split(street_norm(unit_strip(a.line1)), ' ')) >= 2
                 AND a.zip5 IS NOT NULL
            THEN street_norm(unit_strip(a.line1)) || '|' || a.zip5 END AS base_key,
       a.zip5, a.line1, a.city, a.state
FROM r_role r JOIN biz b ON b.sos_id = r.sos_id
JOIN r_party p ON p.party_id = r.party_id
LEFT JOIN r_addr a ON a.address_id = p.address_id;
-- A role holder printed as several people or with an alias ("JOHN & JANE DOE", "JOHN DOE
-- AKA JACK DOE"): each name is a role holder (rows added by compute, see OFFICER_VARIANT_SQL).
CREATE TEMP TABLE owner_companies AS
SELECT DISTINCT o.parcel_uid, o.party_id AS owner_party_id, o.raw_name AS owner_name,
       b.sos_id, b.business_name, b.status, len(k.ids) > 1 AS ambiguous
FROM owners o JOIN biz_by_key k ON k.org_key = o.org_name_norm
JOIN biz b ON list_contains(k.ids, b.sos_id)
WHERE o.party_kind = 'org' AND coalesce(o.org_name_norm, '') <> '';
INSERT INTO owner_companies
SELECT DISTINCT o.parcel_uid, o.party_id, o.raw_name, b.sos_id, b.business_name, b.status,
       len(k.ids) > 1
FROM owners o JOIN biz_by_loose k ON k.loose = org_loose(o.org_name_norm)
JOIN biz b ON list_contains(k.ids, b.sos_id)
WHERE o.party_kind = 'org' AND coalesce(o.org_name_norm, '') <> ''
  AND (o.party_id, o.parcel_uid) NOT IN (SELECT (owner_party_id, parcel_uid) FROM owner_companies);
CREATE TEMP TABLE debtor_companies AS
SELECT DISTINCT d.party_id AS debtor_party_id, d.raw_name AS debtor_name, b.sos_id,
       b.business_name, 'org_name_registry' AS rule_id, 'auto' AS decision,
       len(k.ids) > 1 AS ambiguous
FROM debtors d JOIN biz_by_key k ON k.org_key = d.org_name_norm
JOIN biz b ON list_contains(k.ids, b.sos_id)
WHERE d.party_kind = 'org' AND coalesce(d.org_name_norm, '') <> ''
UNION
SELECT DISTINCT d.party_id, d.raw_name, b.sos_id, b.business_name, 'org_name_registry_loose',
       'auto', len(k.ids) > 1
FROM debtors d JOIN biz_by_loose k ON k.loose = org_loose(d.org_name_norm)
JOIN biz b ON list_contains(k.ids, b.sos_id)
WHERE d.party_kind = 'org' AND coalesce(d.org_name_norm, '') <> ''
  AND d.org_name_norm NOT IN (SELECT org_key FROM biz_by_key)
UNION
SELECT DISTINCT party_id, raw_name, sos_id, business_name,
       CASE WHEN same_place THEN 'person_officer_address' ELSE 'person_officer_zip' END,
       CASE WHEN same_place THEN 'auto' ELSE 'review' END,
       false
FROM (
    SELECT d.party_id, d.raw_name, c.sos_id, c.business_name, d.zip5 AS d_zip, c.zip5 AS c_zip,
           -- One address, or one of them is the other's building without the unit.
           coalesce((d.addr_key IS NOT NULL AND d.addr_key = c.addr_key)
                    OR (db.base_key IS NOT NULL AND db.base_key = c.base_key
                        AND (d.addr_key = db.base_key OR c.addr_key = c.base_key)),
                    false) AS same_place
    FROM debtors d JOIN company_people c ON c.name_key = d.name_key
    LEFT JOIN addr_base db ON db.addr_key = d.addr_key
    WHERE d.party_kind <> 'org' AND c.party_kind <> 'org' AND name_words(d.name_key) >= 2
      AND NOT suffix_conflict(d.suffix_key, c.suffix_key)
)
WHERE same_place OR (d_zip IS NOT NULL AND d_zip = c_zip)
UNION
-- At the officer's own address: a nickname ("BOB SMITH" / "ROBERT SMITH") or a one-letter
-- typo of the officer's name (not two real first names) -> review.
SELECT DISTINCT d.party_id, d.raw_name, c.sos_id, c.business_name,
       CASE WHEN nick_key(d.name_key) = nick_key(c.name_key) THEN 'person_officer_nickname'
            ELSE 'person_officer_typo' END,
       'review', false
FROM debtors d JOIN addr_alias aa ON aa.k = d.addr_key
JOIN company_people c ON c.addr_key = aa.k2 OR c.base_key = aa.k2
WHERE d.party_kind <> 'org' AND c.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND d.name_key <> c.name_key AND NOT suffix_conflict(d.suffix_key, c.suffix_key)
  AND (nick_key(d.name_key) = nick_key(c.name_key)
       OR (name_typo(d.name_key, c.name_key)
           AND NOT two_first_names(name_only(d.name_key, c.name_key)[1],
                                   name_only(c.name_key, d.name_key)[1])));
CREATE TEMP TABLE debtor_company_parcels AS
SELECT DISTINCT dc.debtor_party_id, dc.debtor_name, dc.sos_id, dc.business_name, dc.rule_id,
       dc.decision, oc.parcel_uid, oc.owner_name, v.value AS parcel_value
FROM debtor_companies dc JOIN owner_companies oc ON oc.sos_id = dc.sos_id
LEFT JOIN parcel_value v ON v.parcel_uid = oc.parcel_uid;
"""


OFFICER_VARIANT_SQL = """
INSERT INTO company_people
SELECT DISTINCT c.sos_id, c.business_name, c.role, c.title, c.party_id, c.name, 'person',
       name_key(v.variant), suffix_key(v.variant), c.addr_key, c.base_key, c.zip5, c.line1,
       c.city, c.state
FROM company_people c JOIN officer_name_variant v ON v.raw_name = c.name
WHERE v.party_kind <> 'org' AND v.kind NOT IN ('trust', 'estate')
  AND name_words(name_key(v.variant)) >= 2;
"""


def compute(
    con: duckdb.DuckDBPyConnection, lake: Path, sources: list[str], state_fips: str | None = None
) -> None:
    from equity.matching.resolve import name_variant_table

    org_key_macro(con)
    attach(con, lake, sources, state_fips)
    people, rest = SQL.split("CREATE TEMP TABLE owner_companies AS", 1)
    con.execute(people)
    name_variant_table(con, "officer_name_variant", "SELECT name FROM company_people")
    con.execute(OFFICER_VARIANT_SQL)
    con.execute("CREATE TEMP TABLE owner_companies AS" + rest)


TABLES = ("owner_companies", "company_people", "debtor_companies", "debtor_company_parcels")


def summary(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    def one(sql: str) -> object:
        row = con.execute(sql).fetchone()
        return None if row is None else row[0]

    by_rule = dict(
        con.execute(
            "SELECT rule_id, count(DISTINCT debtor_party_id) FROM debtor_companies "
            "GROUP BY 1 ORDER BY 1"
        ).fetchall()
    )
    return {
        "registry_entities": one("SELECT count(*) FROM biz"),
        "owner_orgs_linked": one("SELECT count(DISTINCT owner_party_id) FROM owner_companies"),
        "parcels_with_company_people": one(
            "SELECT count(DISTINCT o.parcel_uid) FROM owner_companies o "
            "JOIN company_people c ON c.sos_id = o.sos_id"
        ),
        "debtors_linked_to_companies_by_rule": by_rule,
        "debtors_with_company_parcels_auto": one(
            "SELECT count(DISTINCT debtor_party_id) FROM debtor_company_parcels "
            "WHERE decision = 'auto'"
        ),
        "company_parcel_value_auto": one(
            "SELECT round(sum(parcel_value), 2) FROM (SELECT DISTINCT parcel_uid, parcel_value "
            "FROM debtor_company_parcels WHERE decision = 'auto')"
        ),
    }
