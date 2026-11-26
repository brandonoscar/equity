"""Sale watch: matched debtors' parcels that appear on a sale list or in a foreclosure filing.

A tax sale, sheriff sale, forfeited-land sale or foreclosure on a debtor's parcel is time
sensitive: the sale can wipe out the equity behind a judgment, or leave surplus proceeds a
judgment creditor can claim. This joins a state's auto-matched parcels (equity.matching.resolve)
to every event source it can find in the lake:

  listing sources   refresh.yaml rules in `listing` mode (tax sale, sheriff sale, forfeited
                    land, HUD REO ...): their instrument + instrument_parcel rows, or
                    tax_delinquency_snapshot rows
  foreclosures      sources whose kind in config/debt_kinds.yaml is `foreclosure`

When `equity.refresh listings` has written sale_listing_history (data/derived/sale_listings),
each hit also gets first_seen / last_seen / on_latest from it. Nothing is matched here: only
parcel ids already matched by an `auto` rule are used.

Outputs, in the state's derived folder (git-ignored: they name people):
  sale_watch.parquet / sale_watch.csv   one row per (parcel, event), newest event first

    uv run python -m equity.matching.sale_watch --state PA-ALLEGHENY
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import duckdb

from equity.config import CONFIG_DIR
from equity.matching.resolve import DERIVED, LAKE
from equity.refresh import rule_for, rules

HISTORY = DERIVED / "sale_listings" / "sale_listing_history.parquet"


def _files(lake: Path, source: str, table: str) -> list[str]:
    return [p.as_posix() for p in sorted((lake / source / table).glob("*.parquet"))]


def event_sources(lake: Path, config_dir: Path | None = None) -> dict[str, str]:
    """{source_id: 'listing' | 'foreclosure'} for event sources present in the lake."""
    import yaml

    cfg = config_dir or CONFIG_DIR
    kinds = (yaml.safe_load((cfg / "debt_kinds.yaml").read_text()) or {}).get("sources") or {}
    out: dict[str, str] = {}
    rule_list = rules(config_dir)
    for src in sorted(p.name for p in lake.iterdir() if p.is_dir()) if lake.exists() else []:
        rule = rule_for(src, rule_list)
        if rule is not None and rule.mode == "listing":
            out[src] = "listing"
        elif kinds.get(src) == "foreclosure":
            out[src] = "foreclosure"
    return out


def _event_select(lake: Path, source: str, kind: str) -> str | None:
    inst, lots = _files(lake, source, "instrument"), _files(lake, source, "instrument_parcel")
    snap = _files(lake, source, "tax_delinquency_snapshot")
    if inst and lots:
        return (f"SELECT '{source}' AS source_id, '{kind}' AS event_kind, "  # noqa: S608
                "i.instrument_uid AS listing_key, p.parcel_uid, i.recorded_on AS event_date, "
                "CAST(i.principal_amount AS DOUBLE) AS amount, i.doc_type_raw AS status "
                f"FROM read_parquet({inst}, union_by_name=true) i "
                f"JOIN read_parquet({lots}, union_by_name=true) p USING (instrument_uid) "
                "WHERE i.superseded_at IS NULL")  # fmt: skip
    if snap:
        return (f"SELECT '{source}' AS source_id, '{kind}' AS event_kind, "  # noqa: S608
                "parcel_uid || '|' || certificate_no AS listing_key, parcel_uid, "
                "observed_on AS event_date, CAST(NULL AS DOUBLE) AS amount, "
                f"status_raw AS status FROM read_parquet({snap}, union_by_name=true) "
                "WHERE superseded_at IS NULL")  # fmt: skip
    return None


def build(lake: Path, derived: Path, state: str, history: Path = HISTORY,
          config_dir: Path | None = None) -> dict[str, Any]:  # fmt: skip
    key = state.upper()
    out = derived / state.lower()
    matches, summary = out / "matches.parquet", out / "debtor_summary.parquet"
    if not matches.exists():
        raise FileNotFoundError(f"{key}: run equity.matching.resolve first")
    sources = event_sources(lake, config_dir)
    selects = [s for s in (_event_select(lake, src, k) for src, k in sources.items()) if s]
    con = duckdb.connect()
    if selects:
        con.execute("CREATE TABLE events AS " + " UNION ALL BY NAME ".join(selects))
    else:
        con.execute("CREATE TABLE events (source_id VARCHAR, event_kind VARCHAR, "
                    "listing_key VARCHAR, parcel_uid VARCHAR, event_date DATE, "
                    "amount DOUBLE, status VARCHAR)")  # fmt: skip
    if history.exists():
        con.execute(f"CREATE TABLE hist AS SELECT source_id, listing_key, first_seen, last_seen, "  # noqa: S608
                    f"on_latest FROM '{history.as_posix()}'")  # fmt: skip
    else:
        con.execute("CREATE TABLE hist (source_id VARCHAR, listing_key VARCHAR, "
                    "first_seen DATE, last_seen DATE, on_latest BOOLEAN)")  # fmt: skip
    con.execute(f"""
        CREATE TABLE sale_watch AS
        WITH m AS (
            SELECT parcel_uid, list(DISTINCT debtor_party_id) AS debtor_party_ids
            FROM read_parquet('{matches.as_posix()}') WHERE decision = 'auto' GROUP BY 1
        ), money AS (
            SELECT m.parcel_uid, round(sum(s.open_amount), 2) AS open_amount,
                   any_value(s.debtor_name) AS example_debtor_name
            FROM m, unnest(m.debtor_party_ids) AS u(debtor_party_id)
            JOIN read_parquet('{summary.as_posix()}') s USING (debtor_party_id)
            GROUP BY 1
        )
        SELECT e.parcel_uid, e.source_id, e.event_kind, e.event_date, e.amount AS event_amount,
               e.status, e.listing_key, len(m.debtor_party_ids) AS debts_linked,
               money.open_amount AS debtor_open_amount, money.example_debtor_name,
               h.first_seen, h.last_seen, h.on_latest
        FROM events e JOIN m USING (parcel_uid)
        LEFT JOIN money USING (parcel_uid)
        LEFT JOIN hist h ON h.source_id = e.source_id AND h.listing_key = e.listing_key
        ORDER BY e.event_date DESC NULLS LAST, e.parcel_uid, e.source_id, e.listing_key
    """)  # noqa: S608
    con.execute(f"COPY sale_watch TO '{(out / 'sale_watch.parquet').as_posix()}' "
                "(FORMAT parquet)")  # fmt: skip
    con.execute(f"COPY (SELECT * EXCLUDE (listing_key) FROM sale_watch) TO "  # noqa: S608
                f"'{(out / 'sale_watch.csv').as_posix()}' (HEADER)")  # fmt: skip

    def one(sql: str) -> Any:
        row = con.execute(sql).fetchone()
        return row[0] if row else None

    return {
        "state": key,
        "event_sources_in_lake": len(sources),
        "parcels_hit": one("SELECT count(DISTINCT parcel_uid) FROM sale_watch"),
        "events": one("SELECT count(*) FROM sale_watch"),
        "parcels_hit_last_365_days": one(
            "SELECT count(DISTINCT parcel_uid) FROM sale_watch "
            "WHERE event_date >= current_date - INTERVAL 365 DAY"),
        "by_source": dict(con.execute(
            "SELECT source_id, count(DISTINCT parcel_uid) FROM sale_watch GROUP BY 1 ORDER BY 1"
        ).fetchall()),
        "debtor_open_amount": one(
            "SELECT round(sum(debtor_open_amount), 2) FROM "
            "(SELECT DISTINCT parcel_uid, debtor_open_amount FROM sale_watch)"),
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.matching.sale_watch")
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
