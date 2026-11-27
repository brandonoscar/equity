"""Transfers after a debt: a debtor conveying property away once the judgment or lien exists,
and the company that received it when the debtor runs it (a nominee LLC).

Runs after equity.matching.resolve has built `debtors` and `matches` (and, when the run has
registries, after equity.matching.entities has built `company_people` and `biz_by_key`).
Deed sources are the state's recorder or sales files with DEED instruments and their
grantor/grantee parties (ACRIS, Philadelphia RTT, Florida official records, Illinois PTAX-203,
the Cook Assessor sales, Maryland SDAT transfers).

A deed's party strings are split first ("JOHN DOE AND JANE DOE", "JOHN DOE TRUSTEE", "DBA"),
each name a party of the deed. A deed is flagged when one of its grantors is an open debt's debtor (same person name_key of
two or more words, or same organization name) and it was recorded after the debt:

  on_matched_parcel  the deed's parcel is one the debtor is auto-matched to           -> auto
  same_county        the parcel is in the debt's county (no parcel match)              -> review
  nominal            consideration missing or at most rules.yaml
                     transfer_flags.nominal_consideration_max (a gift, a quitclaim, or a price
                     kept off the record); NULL while that threshold is not set (Brandon's
                     decision: code never substitutes a default)
  grantee_org        a grantee is an organization
  grantee_same_name  a grantee has the debtor's own name (to a trust or a new entity form)
  nominee_llc        a grantee organization's registry lists a role holder with the debtor's
                     name (member, manager, officer, agent): the debtor still controls it

These are leads for a fraudulent-transfer review (e.g. the Uniform Voidable Transactions
Act's badges of fraud), not findings: names alone are matched, and a sale may be genuine.

Outputs (Parquet in the state's derived folder, git-ignored: they name people):
  transfer_flags  debtor, debt (instrument, date), deed (instrument, date, source, price),
                  parcel, grantees, the flags above, rule and decision
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from equity.config import _load
from equity.matching.resolve import _view, name_variant_table


def nominal_max(config_dir: Path | None = None) -> float | None:
    """rules.yaml transfer_flags.nominal_consideration_max, or None while it is unset."""
    value = (_load("rules.yaml", config_dir).get("transfer_flags") or {}).get(
        "nominal_consideration_max"
    )
    return None if value is None else float(value)


SQL = """
CREATE TEMP TABLE deed_inst AS
SELECT DISTINCT instrument_uid, source_id, recorded_on, consideration
FROM t_inst WHERE doc_type = 'DEED' AND recorded_on IS NOT NULL;
CREATE TEMP TABLE deed_party AS
SELECT DISTINCT ip.instrument_uid, ip.role, p.raw_name, p.party_kind, p.org_name_norm,
       name_key(p.raw_name) AS name_key
FROM t_ip ip JOIN t_party p USING (party_id)
WHERE ip.instrument_uid IN (SELECT instrument_uid FROM deed_inst)
  AND ip.role IN ('grantor', 'grantee');
CREATE TEMP TABLE deed_lot AS
SELECT DISTINCT instrument_uid, parcel_uid FROM t_lot
WHERE instrument_uid IN (SELECT instrument_uid FROM deed_inst);
CREATE TEMP TABLE open_debt AS
SELECT DISTINCT party_id, instrument_uid AS debt_uid, recorded_on AS debt_on, name_key,
       party_kind, org_name_norm, county
FROM debtors
WHERE NOT released AND doc_type <> 'LIS_PENDENS' AND recorded_on IS NOT NULL
  AND NOT starts_with(party_id, 'owner-of:');
CREATE TEMP TABLE transfer_hits AS
SELECT DISTINCT o.party_id, o.debt_uid, o.debt_on, o.name_key, o.county,
       g.instrument_uid AS deed_uid
FROM open_debt o JOIN deed_party g ON g.role = 'grantor'
 AND ((o.party_kind <> 'org' AND coalesce(g.party_kind, '') <> 'org'
       AND name_words(o.name_key) >= 2 AND g.name_key = o.name_key)
      OR (o.party_kind = 'org' AND g.party_kind = 'org'
          AND coalesce(o.org_name_norm, '') <> '' AND g.org_name_norm = o.org_name_norm));
CREATE TEMP TABLE grantee_summary AS
SELECT instrument_uid, list(DISTINCT raw_name ORDER BY raw_name) AS grantees,
       bool_or(party_kind = 'org') AS grantee_org,
       list(DISTINCT org_name_norm) FILTER (WHERE party_kind = 'org'
                                            AND coalesce(org_name_norm, '') <> '') AS orgs,
       list(DISTINCT name_key) AS name_keys
FROM deed_party WHERE role = 'grantee' GROUP BY instrument_uid;
CREATE TEMP TABLE transfer_flags AS
SELECT h.party_id AS debtor_party_id, h.debt_uid, h.debt_on, h.deed_uid,
       i.recorded_on AS deed_on, i.source_id AS deed_source, i.consideration, l.parcel_uid,
       coalesce(g.grantees, []) AS grantees,
       {nominal} AS nominal,
       coalesce(g.grantee_org, false) AS grantee_org,
       coalesce(list_contains(g.name_keys, h.name_key), false) AS grantee_same_name,
       false AS nominee_llc, NULL::VARCHAR AS nominee_sos_id,
       m.debtor_party_id IS NOT NULL AS on_matched_parcel,
       CASE WHEN m.debtor_party_id IS NOT NULL THEN 'on_matched_parcel'
            ELSE 'same_county' END AS rule_id,
       CASE WHEN m.debtor_party_id IS NOT NULL THEN 'auto' ELSE 'review' END AS decision
FROM transfer_hits h
JOIN deed_inst i ON i.instrument_uid = h.deed_uid AND i.recorded_on > h.debt_on
JOIN deed_lot l ON l.instrument_uid = h.deed_uid
LEFT JOIN grantee_summary g ON g.instrument_uid = h.deed_uid
LEFT JOIN (SELECT DISTINCT debtor_party_id, parcel_uid FROM matches WHERE decision = 'auto') m
       ON m.debtor_party_id = h.party_id AND m.parcel_uid = l.parcel_uid
WHERE m.debtor_party_id IS NOT NULL
   OR (h.county IS NOT NULL AND left(l.parcel_uid, 5) = h.county);
"""

DEED_VARIANT_SQL = """
INSERT INTO deed_party
SELECT DISTINCT g.instrument_uid, g.role, g.raw_name, v.party_kind, v.org_name_norm,
       name_key(v.variant)
FROM deed_party g JOIN deed_name_variant v ON v.raw_name = g.raw_name
WHERE v.party_kind = 'org' OR name_words(name_key(v.variant)) >= 2;
"""

# A grantee company whose registry entry lists the debtor's name as a role holder.
NOMINEE_SQL = """
CREATE TEMP TABLE nominee AS
SELECT DISTINCT f.debtor_party_id, f.deed_uid, b.sos_id
FROM transfer_flags f
JOIN debtors d ON d.party_id = f.debtor_party_id
JOIN grantee_summary g ON g.instrument_uid = f.deed_uid
JOIN biz_by_key k ON list_contains(g.orgs, k.org_key)
JOIN biz b ON list_contains(k.ids, b.sos_id)
JOIN company_people c ON c.sos_id = b.sos_id AND c.name_key = d.name_key
WHERE d.party_kind <> 'org' AND name_words(d.name_key) >= 2;
UPDATE transfer_flags SET nominee_llc = true, nominee_sos_id = n.sos_id
FROM (SELECT debtor_party_id, deed_uid, min(sos_id) AS sos_id FROM nominee GROUP BY ALL) n
WHERE n.debtor_party_id = transfer_flags.debtor_party_id
  AND n.deed_uid = transfer_flags.deed_uid;
"""


def _has(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    row = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()
    return bool(row and row[0])


def compute(con: duckdb.DuckDBPyConnection, lake: Path, sources: list[str]) -> None:
    _view(con, "t_inst", lake, sources, "instrument")
    _view(con, "t_ip", lake, sources, "instrument_party")
    _view(con, "t_party", lake, sources, "party")
    _view(con, "t_lot", lake, sources, "instrument_parcel")
    limit = nominal_max()
    nominal = "NULL::BOOLEAN" if limit is None else f"coalesce(i.consideration, 0) <= {limit!r}"
    sql = SQL.format(nominal=nominal)
    parties, rest = sql.split("CREATE TEMP TABLE deed_lot", 1)
    con.execute(parties)
    # Deeds print several grantors or grantees, trusts and aliases in one string ("JOHN DOE
    # AND JANE DOE", "JOHN DOE TRUSTEE"): each name is a party of the deed.
    name_variant_table(con, "deed_name_variant", "SELECT raw_name FROM deed_party")
    con.execute(DEED_VARIANT_SQL)
    con.execute("CREATE TEMP TABLE deed_lot" + rest)
    if _has(con, "company_people") and _has(con, "biz_by_key"):
        con.execute(NOMINEE_SQL)


TABLES = ("transfer_flags",)


def summary(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    def one(sql: str) -> object:
        row = con.execute(sql).fetchone()
        return None if row is None else row[0]

    return {
        "deeds": one("SELECT count(*) FROM deed_inst"),
        "debtors_with_transfers_auto": one(
            "SELECT count(DISTINCT debtor_party_id) FROM transfer_flags WHERE decision = 'auto'"
        ),
        "debtors_with_transfers_review": one(
            "SELECT count(DISTINCT debtor_party_id) FROM transfer_flags WHERE decision = 'review'"
        ),
        "nominal_transfers": one("SELECT count(*) FROM transfer_flags WHERE nominal"),
        "nominal_threshold_set": nominal_max() is not None,
        "to_organizations": one("SELECT count(*) FROM transfer_flags WHERE grantee_org"),
        "nominee_llc": one("SELECT count(*) FROM transfer_flags WHERE nominee_llc"),
    }
