"""Build a tiny synthetic lake from a scenario file, then run it through the whole search
pipeline (build, matcher-free supplements, compact, leads) and check its expectations.

A scenario (tests/e2e/scenarios/*.yaml) is:

    name: grade_name_address
    doc: one line on the rule it pins
    sources:
      oh.testcounty.parcels:            # a source id; the first segment is the state
        party: [{party_id: o1, raw_name: TESTOWNER ALPHA, address_id: a1}]
        owner_snapshot: [{party_id: o1, parcel_uid: 39001-1}]
        ...
    then:                               # optional: rows added after a first check (watch)
      oh.testcounty.liens: {instrument: [...]}
    expect:
      - grade: {debtor: <ref>, owner: <ref>, grade: A, rule: name_address}
      - ...

Rows need only the columns that matter; the rest get typed NULLs or defaults (source_id,
superseded_at NULL, a jurisdiction from the parcel's FIPS). Names must be pseudonyms
(TESTOWNER ...) and street lines end in TEST ST (tests/test_fixture_privacy.py's rule).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

# Typed columns per lake table (the columns the index reads, equity.search_index.NEEDED,
# plus the supplements').
COLUMNS: dict[str, dict[str, str]] = {
    "party": {"source_id": "VARCHAR", "party_id": "VARCHAR", "raw_name": "VARCHAR",
              "party_kind": "VARCHAR", "org_form": "VARCHAR", "jurisdiction": "VARCHAR",
              "address_id": "VARCHAR", "superseded_at": "TIMESTAMPTZ"},
    "owner_snapshot": {"source_id": "VARCHAR", "party_id": "VARCHAR", "parcel_uid": "VARCHAR",
                       "observed_on": "DATE", "owner_type": "VARCHAR",
                       "superseded_at": "TIMESTAMPTZ"},
    "parcel": {"source_id": "VARCHAR", "parcel_uid": "VARCHAR", "jurisdiction": "VARCHAR",
               "parid_raw": "VARCHAR", "situs_address_id": "VARCHAR",
               "land_use_desc": "VARCHAR", "land_use_code": "VARCHAR", "zoning": "VARCHAR",
               "superseded_at": "TIMESTAMPTZ"},
    "parcel_assessment": {"source_id": "VARCHAR", "parcel_uid": "VARCHAR",
                          "tax_year": "INTEGER", "appraised_total": "DECIMAL(14,2)",
                          "assessed_value": "DECIMAL(14,2)", "appraised_land": "DECIMAL(14,2)",
                          "appraised_bldg": "DECIMAL(14,2)", "tax_class": "VARCHAR",
                          "homestead": "BOOLEAN", "valid_from": "DATE",
                          "superseded_at": "TIMESTAMPTZ"},
    "address": {"address_id": "VARCHAR", "line1": "VARCHAR", "city": "VARCHAR",
                "state": "VARCHAR", "zip5": "VARCHAR"},
    "instrument": {"source_id": "VARCHAR", "instrument_uid": "VARCHAR", "doc_type": "VARCHAR",
                   "doc_type_raw": "VARCHAR", "recorded_on": "DATE",
                   "principal_amount": "DECIMAL(14,2)", "max_secured_amount": "DECIMAL(14,2)",
                   "consideration": "DECIMAL(14,2)", "superseded_at": "TIMESTAMPTZ"},
    "instrument_party": {"source_id": "VARCHAR", "instrument_uid": "VARCHAR",
                         "party_id": "VARCHAR", "role": "VARCHAR",
                         "superseded_at": "TIMESTAMPTZ"},
    "instrument_parcel": {"source_id": "VARCHAR", "instrument_uid": "VARCHAR",
                          "parcel_uid": "VARCHAR", "method": "VARCHAR",
                          "superseded_at": "TIMESTAMPTZ"},
    "instrument_ref": {"source_id": "VARCHAR", "from_uid": "VARCHAR", "to_uid": "VARCHAR",
                       "ref_type": "VARCHAR", "superseded_at": "TIMESTAMPTZ"},
    "court_case": {"source_id": "VARCHAR", "case_uid": "VARCHAR", "court_id": "VARCHAR",
                   "case_number_raw": "VARCHAR", "case_type": "VARCHAR",
                   "nature_of_suit": "VARCHAR", "filed_on": "DATE", "closed_on": "DATE",
                   "status": "VARCHAR", "superseded_at": "TIMESTAMPTZ"},
    "case_party": {"source_id": "VARCHAR", "case_uid": "VARCHAR", "party_id": "VARCHAR",
                   "role": "VARCHAR", "superseded_at": "TIMESTAMPTZ"},
    "judgment": {"source_id": "VARCHAR", "judgment_uid": "VARCHAR", "case_uid": "VARCHAR",
                 "entered_on": "DATE", "principal": "DECIMAL(14,2)",
                 "interest": "DECIMAL(14,2)", "costs": "DECIMAL(14,2)",
                 "rate": "DECIMAL(9,6)", "judgment_type": "VARCHAR",
                 "lien_instrument_uid": "VARCHAR", "superseded_at": "TIMESTAMPTZ"},
    "business": {"source_id": "VARCHAR", "sos_id": "VARCHAR", "name": "VARCHAR",
                 "org_form": "VARCHAR", "status": "VARCHAR", "formed_on": "DATE",
                 "principal_address_id": "VARCHAR", "mailing_address_id": "VARCHAR",
                 "superseded_at": "TIMESTAMPTZ"},
    "business_role": {"source_id": "VARCHAR", "sos_id": "VARCHAR", "party_id": "VARCHAR",
                      "role": "VARCHAR", "title": "VARCHAR", "superseded_at": "TIMESTAMPTZ"},
    "bankruptcy": {"source_id": "VARCHAR", "case_uid": "VARCHAR", "chapter": "VARCHAR",
                   "petition_on": "DATE", "discharge_on": "DATE", "dismissed_on": "DATE",
                   "converted_on": "DATE", "asset_case": "BOOLEAN",
                   "superseded_at": "TIMESTAMPTZ"},
    "tax_delinquency_snapshot": {"source_id": "VARCHAR", "parcel_uid": "VARCHAR",
                                 "certificate_no": "VARCHAR", "status_raw": "VARCHAR",
                                 "times_listed": "INTEGER", "observed_on": "DATE",
                                 "superseded_at": "TIMESTAMPTZ"},
    "house_price_index": {"source_id": "VARCHAR", "geo_level": "VARCHAR", "geo_id": "VARCHAR",
                          "year": "INTEGER", "period": "INTEGER", "index_value": "DOUBLE",
                          "annual_change_pct": "DOUBLE", "superseded_at": "TIMESTAMPTZ"},
}  # fmt: skip

DEFAULTS: dict[str, dict[str, Any]] = {
    "party": {"party_kind": "unknown"},
    "owner_snapshot": {"observed_on": "2026-11-01"},
    "instrument_parcel": {"method": "index_parcel_id"},
}


def _fill(source_id: str, table: str, row: dict[str, Any]) -> dict[str, Any]:
    cols = COLUMNS[table]
    unknown = set(row) - set(cols)
    if unknown:
        raise ValueError(f"{source_id}.{table}: unknown columns {sorted(unknown)}")
    out = {c: None for c in cols} | DEFAULTS.get(table, {}) | row
    if "source_id" in cols:
        out["source_id"] = source_id
    if table in ("party", "parcel") and out.get("jurisdiction") is None:
        out["jurisdiction"] = "00000"
    if table == "parcel" and out.get("parid_raw") is None:
        out["parid_raw"] = str(out["parcel_uid"]).split("-", 1)[-1]
    if table == "instrument" and out.get("doc_type_raw") is None:
        out["doc_type_raw"] = out["doc_type"]
    return out


def write_sources(lake: Path, sources: dict[str, dict[str, list[dict[str, Any]]]]) -> None:
    """Write (or extend: rows are appended to what a table already has) each source's tables
    as typed Parquet, and its _counts.json."""
    con = duckdb.connect()
    for sid, tables in sources.items():
        counts_path = lake / sid / "_counts.json"
        counts = json.loads(counts_path.read_text()) if counts_path.exists() else {}
        for table, rows in tables.items():
            if table not in COLUMNS:
                raise ValueError(f"{sid}: unknown lake table {table}")
            cols = COLUMNS[table]
            out = lake / sid / table
            out.mkdir(parents=True, exist_ok=True)
            n = len(list(out.glob("*.parquet")))
            filled = [_fill(sid, table, r) for r in rows]
            con.execute("CREATE OR REPLACE TABLE t (" + ", ".join(
                f'"{c}" {t}' for c, t in cols.items()) + ")")  # fmt: skip
            if filled:
                con.executemany(f"INSERT INTO t VALUES ({', '.join('?' for _ in cols)})",
                                [[r[c] for c in cols] for r in filled])  # fmt: skip
            con.execute(f"COPY t TO '{out / f'{n:05d}.parquet'}' (FORMAT parquet)")
            counts[table] = counts.get(table, 0) + len(filled)
        counts_path.parent.mkdir(parents=True, exist_ok=True)
        counts_path.write_text(json.dumps(counts))
    con.close()


def write_derived(lake: Path, derived: dict[str, dict[str, list[dict[str, Any]]]]) -> None:
    """The matcher's output beside the lake (data/derived/<state>/<file>.parquet), e.g.
    {oh: {matches: [{debtor_party_id, owner_party_id, rule_id, decision, ...}]}}."""
    con = duckdb.connect()
    for state, files in derived.items():
        d = lake.parent / "derived" / state.lower()
        d.mkdir(parents=True, exist_ok=True)
        for stem, rows in files.items():
            cols = sorted({k for r in rows for k in r})
            con.execute("CREATE OR REPLACE TABLE t (" + ", ".join(
                f'"{c}" VARCHAR' for c in cols) + ")")  # fmt: skip
            con.executemany(f"INSERT INTO t VALUES ({', '.join('?' for _ in cols)})",
                            [[None if r.get(c) is None else str(r[c]) for c in cols]
                             for r in rows])  # fmt: skip
            con.execute(f"COPY t TO '{d / f'{stem}.parquet'}' (FORMAT parquet)")
    con.close()
