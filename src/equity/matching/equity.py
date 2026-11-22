"""Open mortgages on matched parcels, and estimated equity per debtor (exact rules, no AI).

Runs after equity.matching.resolve has built `matches`, `parcel_value` and `debtor_summary`
on the same connection. Recorder sources (ACRIS) give mortgages, satisfactions and deeds with
their lots and parties. Few satisfactions cite the mortgage they pay off (about 3% in ACRIS),
so a mortgage on a lot is treated as paid when any of these holds, checked in this order:

  paid_ref      a release instrument cites it (instrument_ref 'releases')
  paid_payoff   a release recorded on the same lot on or after it names one of its borrowers
                (same name_key; a key needs at least two words)
  paid_sale     a deed recorded on the same lot after it conveys the lot to grantees none of
                whom is one of its borrowers (a sale to someone else pays it off at closing)

Otherwise it is open. Mortgage amounts are the amounts secured when recorded, not today's
balance, so open debt is an upper bound and equity a lower bound. A mortgage spanning several
lots counts once per debtor, at its full amount. Partial releases do not close a mortgage.

Rules chosen by the project owner (2026-11-22): same-lot payoff and sale closes older loans.

Condominium units: recorders index a unit's documents by unit lot, the assessment roll
carries the condominium as one billing lot. With a parcel_link source (condo_unit_of), a unit
lot's documents join to the billing lot; the paid rules still run on the unit lot itself. A
billing lot stands for the whole building, so an open mortgage on a unit counts against a
debtor only when one of its borrowers has the debtor's name_key.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

PAID_RULES = ("paid_ref", "paid_payoff", "paid_sale")


def attach(
    con: duckdb.DuckDBPyConnection, lake: Path, sources: list[str], link_sources: list[str]
) -> None:
    from equity.matching.resolve import _view

    _view(con, "m_link", lake, link_sources, "parcel_link")
    _view(con, "m_inst", lake, sources, "instrument")
    _view(con, "m_lot", lake, sources, "instrument_parcel")
    _view(con, "m_ip", lake, sources, "instrument_party")
    _view(con, "m_party", lake, sources, "party")
    _view(con, "m_ref", lake, sources, "instrument_ref")


SQL = """
CREATE TEMP TABLE unit_of AS
SELECT from_parcel_uid, any_value(to_parcel_uid) AS to_parcel_uid
FROM m_link WHERE link_type = 'condo_unit_of' GROUP BY from_parcel_uid;
CREATE TEMP TABLE m_docs AS
SELECT * FROM (
    SELECT DISTINCT l.instrument_uid, l.parcel_uid AS lot_uid,
           coalesce(u.to_parcel_uid, l.parcel_uid) AS parcel_uid,
           u.to_parcel_uid IS NOT NULL AS via_unit,
           i.doc_type, i.recorded_on, i.principal_amount
    FROM m_lot l JOIN m_inst i ON i.instrument_uid = l.instrument_uid
    LEFT JOIN unit_of u ON u.from_parcel_uid = l.parcel_uid
    WHERE i.doc_type IN ('MORTGAGE', 'RELEASE', 'DEED'))
WHERE parcel_uid IN (SELECT parcel_uid FROM matches);
CREATE TEMP TABLE m_names AS
SELECT DISTINCT ip.instrument_uid, ip.role, name_key(p.raw_name) AS k
FROM m_ip ip JOIN m_party p ON p.party_id = ip.party_id
WHERE ip.role IN ('borrower', 'grantee')
  AND ip.instrument_uid IN (SELECT instrument_uid FROM m_docs)
  AND name_words(name_key(p.raw_name)) >= 2;
CREATE TEMP TABLE mortgage_status AS
SELECT m.instrument_uid, m.lot_uid, m.parcel_uid, m.via_unit, m.recorded_on, m.principal_amount,
    CASE
    WHEN EXISTS (SELECT 1 FROM m_ref r
                 WHERE r.to_uid = m.instrument_uid AND r.ref_type = 'releases') THEN 'paid_ref'
    WHEN EXISTS (
        SELECT 1 FROM m_docs s
        JOIN m_names sn ON sn.instrument_uid = s.instrument_uid AND sn.role = 'borrower'
        JOIN m_names mn ON mn.instrument_uid = m.instrument_uid AND mn.role = 'borrower'
                        AND mn.k = sn.k
        WHERE s.lot_uid = m.lot_uid AND s.doc_type = 'RELEASE'
          AND s.recorded_on >= m.recorded_on) THEN 'paid_payoff'
    WHEN EXISTS (
        SELECT 1 FROM m_docs d
        WHERE d.lot_uid = m.lot_uid AND d.doc_type = 'DEED'
          AND d.recorded_on > m.recorded_on
          AND NOT EXISTS (
              SELECT 1 FROM m_names g
              JOIN m_names b ON b.instrument_uid = m.instrument_uid AND b.role = 'borrower'
                             AND b.k = g.k
              WHERE g.instrument_uid = d.instrument_uid AND g.role = 'grantee')) THEN 'paid_sale'
    ELSE 'open' END AS status
FROM m_docs m WHERE m.doc_type = 'MORTGAGE';
CREATE TEMP TABLE debtor_mortgages AS
SELECT x.debtor_party_id, count(*) AS open_mortgages,
       sum(x.principal_amount) AS open_mortgage_amount,
       count(*) FILTER (WHERE x.principal_amount IS NULL) AS open_mortgages_no_amount
FROM (SELECT DISTINCT mp.debtor_party_id, s.instrument_uid, s.principal_amount
      FROM (SELECT DISTINCT debtor_party_id, parcel_uid FROM matches) mp
      JOIN mortgage_status s ON s.parcel_uid = mp.parcel_uid
      WHERE s.status = 'open'
        AND (NOT s.via_unit OR EXISTS (
            SELECT 1 FROM m_names b JOIN debtors d ON d.name_key = b.k
            WHERE b.instrument_uid = s.instrument_uid AND b.role = 'borrower'
              AND d.party_id = mp.debtor_party_id))) x
GROUP BY x.debtor_party_id;
CREATE OR REPLACE TEMP TABLE debtor_summary AS
SELECT d.*, coalesce(m.open_mortgages, 0) AS open_mortgages,
       coalesce(m.open_mortgage_amount, 0) AS open_mortgage_amount,
       coalesce(m.open_mortgages_no_amount, 0) AS open_mortgages_no_amount,
       d.parcel_value - coalesce(m.open_mortgage_amount, 0) AS equity_est
FROM debtor_summary d LEFT JOIN debtor_mortgages m USING (debtor_party_id);
"""


def compute(
    con: duckdb.DuckDBPyConnection, lake: Path, sources: list[str], link_sources: list[str]
) -> None:
    attach(con, lake, sources, link_sources)
    con.execute(SQL)


def summary(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    sql = "SELECT status, count(*) FROM mortgage_status GROUP BY 1 ORDER BY 1"
    by_status = dict(con.execute(sql).fetchall())
    row = con.execute(
        "SELECT count(*) FILTER (WHERE equity_est > 0), round(sum(equity_est) FILTER ("
        "WHERE equity_est > 0), 2) FROM debtor_summary WHERE has_auto"
    ).fetchone()
    return {
        "mortgage_lots_by_status": by_status,
        "debtors_auto_with_positive_equity": row[0] if row else 0,
        "equity_est_auto_positive": row[1] if row else None,
    }
