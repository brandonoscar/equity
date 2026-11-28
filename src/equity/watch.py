"""Watchlists: after each index build, what is new on the names, records and parcels you watch.

    uv run python -m equity.watch                  # check config/private/watchlist.yaml
    uv run python -m equity.watch --list FILE.yaml

A watchlist (git-ignored: it names people; template docs/watchlist-template.yaml) holds
entries of three kinds:

    - name: "JOHN A SMITH"     # every record with this exact name_key in the state
      state: OH
    - ref: oh.cuyahoga.liens:<party_id>
    - parcel: 39049-010-001234

For each entry the check collects what the index now holds (documents and their type and
date, court cases and judgments, bankruptcy cases, and for a parcel its owners and the
documents recorded against it), compares it with the snapshot from the last check
(data/derived/watch/state.json) and reports what is new. The first check of an entry records
a baseline and reports nothing. Alerts are written to data/derived/watch/alerts-<date>.md.
Deterministic: set differences, no scoring.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import yaml

from equity.search import _in, _rows
from equity.search_index import DEFAULT_DB, connect

WATCHLIST = Path("config") / "private" / "watchlist.yaml"
OUT = Path("data") / "derived" / "watch"
MAX_NAME_RECORDS = 200  # a name held by more records than this is too common to watch


def load(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text()) or []
    entries = data.get("watch", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError(f"{path}: expected a list of entries (or watch: [...])")
    return [e for e in entries if isinstance(e, dict)]


def entry_key(e: dict[str, Any]) -> str:
    if e.get("parcel"):
        return f"parcel:{e['parcel']}"
    if e.get("ref"):
        return f"ref:{e['ref']}"
    return f"name:{str(e.get('state', '')).upper()}:{e.get('name', '')}"


def _parties(
    con: duckdb.DuckDBPyConnection, e: dict[str, Any]
) -> tuple[list[tuple[str, str]], str]:
    if e.get("ref"):
        src, _, pid = str(e["ref"]).partition(":")
        return [(src, pid)], ""
    state = str(e.get("state", "")).upper()
    rows = con.execute("""
        SELECT n.source_id, n.party_id FROM names n JOIN sources s USING (source_id)
        WHERE n.name_key = name_key(?) AND s.state = ?
    """, [str(e.get("name", "")), state]).fetchall()  # fmt: skip
    if len(rows) > MAX_NAME_RECORDS:
        return [], f"{len(rows)} records hold this name in {state}: too common to watch"
    return [(str(a), str(b)) for a, b in rows], ""


def observe(con: duckdb.DuckDBPyConnection, e: dict[str, Any]) -> dict[str, Any]:
    """What the index holds now for one entry: {item id: description}, plus a note."""
    items: dict[str, str] = {}
    if e.get("parcel"):
        uid = str(e["parcel"])
        for r in _rows(con, """
            SELECT i.source_id, i.instrument_uid, i.doc_type, i.recorded_on, i.amount
            FROM instrument_parcels x JOIN instruments i USING (source_id, instrument_uid)
            WHERE x.parcel_uid = ?""", [uid]):  # fmt: skip
            items[f"doc:{r['source_id']}:{r['instrument_uid']}"] = (
                f"{r['doc_type']} recorded {r['recorded_on']} against {uid}"
                + (f" (${float(r['amount']):,.0f})" if r["amount"] is not None else "")
            )
        for r in _rows(con, """
            SELECT o.source_id, o.party_id, n.raw_name FROM owners o
            JOIN names n USING (source_id, party_id) WHERE o.parcel_uid = ?""", [uid]):  # fmt: skip
            items[f"owner:{r['source_id']}:{r['party_id']}"] = f"owner of {uid}: {r['raw_name']}"
        for r in _rows(con, "SELECT * FROM tax_delinquencies WHERE parcel_uid = ?", [uid]):
            items[f"taxdelinq:{r['source_id']}:{r['certificate_no']}"] = (
                f"tax delinquency listing {r['status_raw']} (observed {r['observed_on']}) on {uid}"
            )
        return {"items": items, "note": ""}
    parties, note = _parties(con, e)
    if not parties:
        return {"items": items, "note": note or "no record found"}
    ids = {p for _s, p in parties}
    mine = set(parties)
    for r in _rows(con, f"""
        SELECT ip.source_id, ip.party_id, ip.role, i.instrument_uid, i.doc_type, i.recorded_on,
               i.amount
        FROM instrument_parties ip JOIN instruments i USING (source_id, instrument_uid)
        WHERE ip.party_id IN {_in(ids)}""", []):  # noqa: S608  # fmt: skip
        if (r["source_id"], r["party_id"]) in mine:
            items[f"doc:{r['source_id']}:{r['instrument_uid']}"] = (
                f"{r['doc_type']} recorded {r['recorded_on']} ({r['role']})"
                + (f" ${float(r['amount']):,.0f}" if r["amount"] is not None else "")
            )
    for r in _rows(con, f"""
        SELECT cp.source_id, cp.party_id, cp.role, c.case_uid, c.case_number, c.filed_on,
               j.entered_on, b.chapter, b.discharge_on, b.dismissed_on
        FROM case_parties cp JOIN cases c USING (source_id, case_uid)
        LEFT JOIN judgments j USING (source_id, case_uid)
        LEFT JOIN bankruptcies b USING (source_id, case_uid)
        WHERE cp.party_id IN {_in(ids)}""", []):  # noqa: S608  # fmt: skip
        if (r["source_id"], r["party_id"]) not in mine:
            continue
        key = f"case:{r['source_id']}:{r['case_uid']}"
        items[key] = f"case {r['case_number']} filed {r['filed_on']} ({r['role']})"
        if r["entered_on"]:
            items[key + ":judgment"] = f"judgment entered {r['entered_on']} in {r['case_number']}"
        if r["chapter"]:
            items[key + ":bk"] = f"bankruptcy chapter {r['chapter']} ({r['case_number']})"
        if r["discharge_on"]:
            items[key + ":discharge"] = f"bankruptcy discharge {r['discharge_on']}"
        if r["dismissed_on"]:
            items[key + ":dismissed"] = f"bankruptcy dismissed {r['dismissed_on']}"
    for r in _rows(con, f"""
        SELECT o.source_id, o.party_id, o.parcel_uid FROM owners o
        WHERE o.party_id IN {_in(ids)}""", []):  # noqa: S608  # fmt: skip
        if (r["source_id"], r["party_id"]) in mine:
            items[f"owns:{r['source_id']}:{r['parcel_uid']}"] = f"listed owner of {r['parcel_uid']}"
    return {"items": items, "note": note}


def check(
    con: duckdb.DuckDBPyConnection, entries: list[dict[str, Any]], state_file: Path
) -> list[dict[str, Any]]:
    """Compare each entry with its last snapshot; save the new snapshot. Returns one result per
    entry: {key, label, baseline, new: [descriptions], gone: [...], note}."""
    previous = json.loads(state_file.read_text()) if state_file.exists() else {}
    current: dict[str, Any] = {}
    results = []
    for e in entries:
        key = entry_key(e)
        seen = observe(con, e)
        before = previous.get(key)
        now = seen["items"]
        current[key] = now
        if before is None:
            results.append({"key": key, "label": e.get("label", ""), "baseline": True,
                            "new": [], "gone": [], "note": seen["note"],
                            "items": len(now)})  # fmt: skip
            continue
        results.append({
            "key": key, "label": e.get("label", ""), "baseline": False,
            "new": [now[k] for k in sorted(set(now) - set(before))],
            "gone": [before[k] for k in sorted(set(before) - set(now))],
            "note": seen["note"], "items": len(now),
        })  # fmt: skip
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(current, indent=1, sort_keys=True))
    return results


def report(results: list[dict[str, Any]], when: datetime) -> str:
    changed = [r for r in results if r["new"] or r["gone"]]
    lines = [f"# Watchlist check {when:%Y-%m-%d %H:%M} UTC", "",
             f"{len(results)} entries, {len(changed)} with changes, "
             f"{sum(r['baseline'] for r in results)} new baselines.", ""]  # fmt: skip
    for r in results:
        if not (r["new"] or r["gone"] or r["note"]):
            continue
        lines.append(f"## {r['label'] or r['key']}")
        lines += [f"- NEW: {x}" for x in r["new"]]
        lines += [f"- gone from the index: {x}" for x in r["gone"]]
        if r["note"]:
            lines.append(f"- note: {r['note']}")
        lines.append("")
    return "\n".join(lines)


def run(
    db: Path,
    watchlist: Path,
    out: Path,
    log: Any = print,
    con: duckdb.DuckDBPyConnection | None = None,
) -> list[dict[str, Any]] | None:
    """Check a watchlist file if there is one (None if not) and write the alerts file. Pass
    `con` to reuse an open connection (build does: one process may not open the file twice)."""
    if not watchlist.exists():
        return None
    own = con is None
    con = con or connect(db, read_only=True)
    try:
        results = check(con, load(watchlist), out / "state.json")
    finally:
        if own:
            con.close()
    now = datetime.now(UTC)
    path = out / f"alerts-{now:%Y-%m-%d}.md"
    path.write_text(report(results, now))
    changed = sum(bool(r["new"] or r["gone"]) for r in results)
    log(f"watchlist: {len(results)} entries, {changed} with changes -> {path}")
    return results


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--list", type=Path, default=WATCHLIST)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    if run(args.db, args.list, args.out) is None:
        print(f"no watchlist at {args.list} (template: docs/watchlist-template.yaml)")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
