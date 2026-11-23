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

Outputs (Parquet in the state's derived folder, git-ignored: they name people):
  owner_companies   owner organization -> registry entity, per parcel
  company_people    registry entity -> role holders (role, title, name, address)
  debtor_companies  debtor -> registry entity:
                      org_name_registry      organization debtor, same org key        auto
                      person_officer_address person debtor, same name_key and address
                                             as a role holder                        auto
                      person_officer_zip     same name_key and ZIP                     review
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


def attach(con: duckdb.DuckDBPyConnection, lake: Path, sources: list[str]) -> None:
    from equity.matching.resolve import _view

    _view(con, "r_business", lake, sources, "business")
    _view(con, "r_role", lake, sources, "business_role")
    _view(con, "r_party", lake, sources, "party")
    _view(con, "r_addr", lake, sources, "address")


SQL = """
CREATE TEMP TABLE biz AS
SELECT sos_id, any_value(name) AS business_name, any_value(status) AS status,
       org_key(any_value(name)) AS org_key
FROM r_business WHERE sos_id IS NOT NULL AND name IS NOT NULL GROUP BY sos_id;
CREATE TEMP TABLE biz_by_key AS
SELECT org_key, list(sos_id ORDER BY sos_id) AS ids FROM biz WHERE org_key <> '' GROUP BY org_key;
CREATE TEMP TABLE company_people AS
SELECT DISTINCT r.sos_id, b.business_name, r.role, r.title, p.party_id, p.raw_name AS name,
       p.party_kind, name_key(p.raw_name) AS name_key, suffix_key(p.raw_name) AS suffix_key,
       CASE WHEN street_norm(a.line1) <> '' AND a.zip5 IS NOT NULL
            THEN street_norm(a.line1) || '|' || a.zip5 END AS addr_key,
       a.zip5, a.line1, a.city, a.state
FROM r_role r JOIN biz b ON b.sos_id = r.sos_id
JOIN r_party p ON p.party_id = r.party_id
LEFT JOIN r_addr a ON a.address_id = p.address_id;
CREATE TEMP TABLE owner_companies AS
SELECT DISTINCT o.parcel_uid, o.party_id AS owner_party_id, o.raw_name AS owner_name,
       b.sos_id, b.business_name, b.status, len(k.ids) > 1 AS ambiguous
FROM owners o JOIN biz_by_key k ON k.org_key = o.org_name_norm
JOIN biz b ON list_contains(k.ids, b.sos_id)
WHERE o.party_kind = 'org' AND coalesce(o.org_name_norm, '') <> '';
CREATE TEMP TABLE debtor_companies AS
SELECT DISTINCT d.party_id AS debtor_party_id, d.raw_name AS debtor_name, b.sos_id,
       b.business_name, 'org_name_registry' AS rule_id, 'auto' AS decision,
       len(k.ids) > 1 AS ambiguous
FROM debtors d JOIN biz_by_key k ON k.org_key = d.org_name_norm
JOIN biz b ON list_contains(k.ids, b.sos_id)
WHERE d.party_kind = 'org' AND coalesce(d.org_name_norm, '') <> ''
UNION
SELECT DISTINCT d.party_id, d.raw_name, c.sos_id, c.business_name,
       CASE WHEN d.addr_key IS NOT NULL AND d.addr_key = c.addr_key
            THEN 'person_officer_address' ELSE 'person_officer_zip' END,
       CASE WHEN d.addr_key IS NOT NULL AND d.addr_key = c.addr_key
            THEN 'auto' ELSE 'review' END,
       false
FROM debtors d JOIN company_people c ON c.name_key = d.name_key
WHERE d.party_kind <> 'org' AND c.party_kind <> 'org' AND name_words(d.name_key) >= 2
  AND NOT suffix_conflict(d.suffix_key, c.suffix_key)
  AND ((d.addr_key IS NOT NULL AND d.addr_key = c.addr_key)
       OR (d.zip5 IS NOT NULL AND d.zip5 = c.zip5));
CREATE TEMP TABLE debtor_company_parcels AS
SELECT DISTINCT dc.debtor_party_id, dc.debtor_name, dc.sos_id, dc.business_name, dc.rule_id,
       dc.decision, oc.parcel_uid, oc.owner_name, v.value AS parcel_value
FROM debtor_companies dc JOIN owner_companies oc ON oc.sos_id = dc.sos_id
LEFT JOIN parcel_value v ON v.parcel_uid = oc.parcel_uid;
"""


def compute(con: duckdb.DuckDBPyConnection, lake: Path, sources: list[str]) -> None:
    org_key_macro(con)
    attach(con, lake, sources)
    con.execute(SQL)


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
