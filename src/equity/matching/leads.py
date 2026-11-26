"""Commercial lead list: owners of commercial, mixed-use or industrial property with open debt.

A judgment or lien whose debtor was matched to a parcel owner by an `auto` rule links the owner
to that parcel. This keeps the parcels whose land use is commercial, mixed residential and
commercial, or industrial, and lists one row per owner (owner name as the roll carries it)
with those parcels, their property addresses, and the debts linked to the owner. Nothing is
matched or scored here: rows are sorted by open amount, then parcel count, then name.

Land use is classified by fixed code tables, then by words in the roll's description:
  NY state property class (3 digits): 4xx commercial, 7xx industrial
  NYC land use (2 digits): 04 mixed residential + commercial, 05 commercial and office,
                           06 industrial and manufacturing
  descriptions: COMMERCIAL / RETAIL / OFFICE / STORE / HOTEL / RESTAURANT -> commercial,
                INDUSTRIAL / WAREHOUSE / MANUFACTUR -> industrial, MIXED -> mixed

Outputs, in the state's derived folder (git-ignored: they name people):
  commercial_leads.parquet / commercial_leads.csv

    uv run python -m equity.matching.leads --state NY
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import duckdb

from equity.matching.resolve import DERIVED, LAKE, STATES

KIND_SQL = r"""
CREATE MACRO land_kind(code, descr) AS CASE
  WHEN regexp_matches(coalesce(code, ''), '^4[0-9]{2}$') THEN 'commercial'
  WHEN regexp_matches(coalesce(code, ''), '^7[0-9]{2}$') THEN 'industrial'
  WHEN code = '05' THEN 'commercial'
  WHEN code = '04' THEN 'mixed'
  WHEN code = '06' THEN 'industrial'
  WHEN regexp_matches(upper(coalesce(descr, '')), 'MIXED') THEN 'mixed'
  WHEN regexp_matches(upper(coalesce(descr, '')),
       'COMMERCIAL|RETAIL|OFFICE|STORE|HOTEL|MOTEL|RESTAURANT|SHOPPING') THEN 'commercial'
  WHEN regexp_matches(upper(coalesce(descr, '')),
       'INDUSTRIAL|WAREHOUSE|MANUFACTUR') THEN 'industrial'
  ELSE NULL END;
"""

LEADS_SQL = """
CREATE TABLE land AS
SELECT parcel_uid, any_value(land_use_code) AS code, any_value(land_use_desc) AS descr,
       any_value(situs_address_id) AS situs_address_id
FROM read_parquet({parcels}, union_by_name=true) GROUP BY 1;
CREATE TABLE hits AS
SELECT DISTINCT m.debtor_party_id, m.owner_party_id, m.parcel_uid,
       land_kind(l.code, l.descr) AS kind, l.situs_address_id
FROM read_parquet('{matches}') m JOIN land l USING (parcel_uid)
WHERE m.decision = 'auto' AND land_kind(l.code, l.descr) IS NOT NULL;
CREATE TABLE owner_name AS
SELECT party_id, any_value(raw_name) AS owner_name FROM read_parquet({parties}, union_by_name=true)
WHERE party_id IN (SELECT owner_party_id FROM hits) GROUP BY 1;
CREATE TABLE situs AS
SELECT address_id, any_value(concat_ws(', ', line1, city, state, zip5)) AS address
FROM read_parquet({addresses}, union_by_name=true)
WHERE address_id IN (SELECT situs_address_id FROM hits) GROUP BY 1;
CREATE TABLE commercial_leads AS
WITH per_owner AS (
    SELECT coalesce(o.owner_name, h.owner_party_id) AS owner_name,
           list(DISTINCT h.parcel_uid ORDER BY h.parcel_uid) AS parcels,
           list(DISTINCT h.kind ORDER BY h.kind) AS kinds,
           list(DISTINCT s.address ORDER BY s.address) FILTER (WHERE s.address IS NOT NULL)
               AS property_addresses,
           list(DISTINCT h.debtor_party_id) AS debtor_party_ids
    FROM hits h LEFT JOIN owner_name o ON o.party_id = h.owner_party_id
    LEFT JOIN situs s ON s.address_id = h.situs_address_id
    GROUP BY 1
), debts AS (
    SELECT p.owner_name, count(DISTINCT ds.debtor_party_id) AS debts_linked,
           sum(ds.liens) AS liens, round(sum(ds.open_amount), 2) AS open_amount,
           any_value(ds.debtor_name) AS a_debtor_name
    FROM per_owner p, unnest(p.debtor_party_ids) AS u(debtor_party_id)
    JOIN read_parquet('{summary}') ds ON ds.debtor_party_id = u.debtor_party_id
    GROUP BY 1
)
SELECT p.owner_name, len(p.parcels) AS parcel_count, p.kinds, p.property_addresses,
       p.parcels, coalesce(d.debts_linked, 0) AS debts_linked, coalesce(d.liens, 0) AS liens,
       d.open_amount, d.a_debtor_name AS example_debtor_name
FROM per_owner p LEFT JOIN debts d USING (owner_name)
ORDER BY d.open_amount DESC NULLS LAST, parcel_count DESC, owner_name;
"""


def _files(lake: Path, sources: list[str], table: str) -> list[str]:
    return [p.as_posix() for s in sources for p in sorted((lake / s / table).glob("*.parquet"))]


def build(lake: Path, derived: Path, state: str) -> dict[str, Any]:
    key = state.upper()
    if key not in STATES:
        raise KeyError(f"no match run named {state!r}")
    out = derived / state.lower()
    owners = list(STATES[key]["owners"])
    parcels, parties = _files(lake, owners, "parcel"), _files(lake, owners, "party")
    if not parcels or not parties:
        raise FileNotFoundError(f"{key}: owner parcels or parties are not in {lake}")
    addresses = _files(lake, owners, "address") or ["/nonexistent/none.parquet"]
    con = duckdb.connect()
    con.execute(KIND_SQL)
    if not _files(lake, owners, "address"):
        con.execute("CREATE TABLE no_addr (address_id VARCHAR, line1 VARCHAR, city VARCHAR, "
                    "state VARCHAR, zip5 VARCHAR)")  # fmt: skip
        sql = LEADS_SQL.replace("read_parquet({addresses}, union_by_name=true)", "no_addr")
    else:
        sql = LEADS_SQL
    con.execute(sql.format(parcels=parcels, parties=parties, addresses=addresses,
                           matches=(out / "matches.parquet").as_posix(),
                           summary=(out / "debtor_summary.parquet").as_posix()))  # fmt: skip
    con.execute(f"COPY commercial_leads TO '{(out / 'commercial_leads.parquet').as_posix()}' "
                "(FORMAT parquet)")  # fmt: skip
    con.execute(
        "COPY (SELECT owner_name, parcel_count, array_to_string(kinds, '; ') AS kinds, "  # noqa: S608
        "array_to_string(property_addresses, ' | ') AS property_addresses, debts_linked, liens, "
        "open_amount, example_debtor_name FROM commercial_leads) "
        f"TO '{(out / 'commercial_leads.csv').as_posix()}' (HEADER)"
    )

    def one(sql_: str) -> Any:
        row = con.execute(sql_).fetchone()
        return row[0] if row else None

    return {
        "state": key,
        "owners": one("SELECT count(*) FROM commercial_leads"),
        "owners_with_open_debt": one("SELECT count(*) FROM commercial_leads WHERE open_amount > 0"),
        "parcels": one("SELECT count(DISTINCT parcel_uid) FROM hits"),
        "parcels_by_kind": dict(con.execute(
            "SELECT kind, count(DISTINCT parcel_uid) FROM hits GROUP BY 1 ORDER BY 1").fetchall()),
        "open_amount": one("SELECT round(sum(open_amount), 2) FROM commercial_leads"),
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.matching.leads")
    ap.add_argument("--state", required=True)
    ap.add_argument("--lake", type=Path, default=LAKE)
    ap.add_argument("--derived", type=Path, default=DERIVED)
    args = ap.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9-]+", args.state):
        ap.error("bad state")
    json.dump(build(args.lake, args.derived, args.state), sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
