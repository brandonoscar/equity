"""Review-queue pairs with both addresses run through the Census geocoder: is it the same house?

The review queue holds debtor/owner pairs with the same name whose addresses did not agree as
typed (person_name_zip and the middle-initial rule). Here both sides are standardized by the
U.S. Census Bureau batch geocoder (equity.geocode; only street and ZIP are sent, never a name),
and each pair is labelled. Nothing here accepts a match or changes a rule.

  same_segment   the debtor's standardized house number and street equal the owner's mailing
                 or property address, on the same TIGER street segment and side. The ZIP may
                 differ: one segment can carry two ZIPs or a vanity city.
  same_zip       as same_segment, and the standardized ZIPs agree too (the stricter count).
  multi_unit     either raw address names a unit (APT, UNIT, STE, #, FL, RM, PH ...), or more
                 than one owner parcel in the queue sits at the debtor's standardized address.
                 The geocoder drops units, so these need a human even when same_segment.

Geocoder answers are cached by address (upper-cased street and ZIP) in
data/derived/geocode_cache.parquet and never requested twice.

Outputs, in the state's derived folder (git-ignored: they name people):
  review_geo.parquet         one row per review pair with the labels above
  review_geo_sample.csv      up to 25 same_segment single-unit pairs and 10 multi-unit ones
  review_geo_summary.json    counts only

    uv run python -m equity.matching.review_geo --state NY --max-batches 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from equity.adapters.http import PoliteClient
from equity.geocode import BATCH, Geocoded, batches, geocode_batch
from equity.matching.resolve import DERIVED

CACHE = "geocode_cache.parquet"
UNIT = r"(^|\s)(APT|APARTMENT|UNIT|STE|SUITE|FL|FLOOR|RM|ROOM|PH|BSMT|#)\s*[0-9A-Z]"


def addr_key(line1: Any, zip5: Any) -> str:
    raw = f"{' '.join(str(line1 or '').upper().split())}|{str(zip5 or '').strip()[:5]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _queue_addresses(queue: Path) -> list[tuple[str, str, str]]:
    """Distinct (key, line1, zip5) across the debtor, mailing and property sides."""
    con = duckdb.connect()
    rows = con.execute(
        "SELECT line1, zip FROM ("  # noqa: S608 (a path only)
        f"SELECT debtor_line1 AS line1, debtor_zip AS zip FROM '{queue.as_posix()}' UNION "
        f"SELECT mail_line1, mail_zip FROM '{queue.as_posix()}' UNION "
        f"SELECT situs_line1, situs_zip FROM '{queue.as_posix()}') "
        "WHERE coalesce(trim(line1), '') <> '' AND coalesce(zip, '') <> ''"
    ).fetchall()
    found = {addr_key(a, z): (a, z) for a, z in rows}
    return sorted((k, a, z) for k, (a, z) in found.items())


def _cached(derived: Path) -> set[str]:
    path = derived / CACHE
    if not path.exists():
        return set()
    con = duckdb.connect()
    return {r[0] for r in con.execute(f"SELECT key FROM '{path.as_posix()}'").fetchall()}  # noqa: S608


def _append_cache(derived: Path, results: Sequence[Geocoded]) -> None:
    path = derived / CACHE
    derived.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE g (key VARCHAR, match VARCHAR, match_type VARCHAR, line1 VARCHAR, "
        "city VARCHAR, state VARCHAR, zip5 VARCHAR, lon DOUBLE, lat DOUBLE, "
        "tiger_line_id VARCHAR, side VARCHAR, geocoded_on DATE)"
    )
    if path.exists():
        con.execute(f"INSERT INTO g SELECT * FROM '{path.as_posix()}'")  # noqa: S608
    today = datetime.now(UTC).date()
    con.executemany("INSERT INTO g VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(*vars(r).values(), today) for r in results])  # fmt: skip
    tmp = path.with_suffix(".tmp.parquet")
    con.execute(f"COPY (SELECT * FROM g ORDER BY key) TO '{tmp.as_posix()}' (FORMAT parquet)")  # noqa: S608
    tmp.replace(path)


def geocode_queue(derived: Path, state: str, max_batches: int,
                  client: PoliteClient | None = None) -> dict[str, int]:  # fmt: skip
    """Geocode the state's review-queue addresses not yet in the cache (up to max_batches)."""
    queue = derived / state / "review_queue.parquet"
    if not queue.exists():
        raise FileNotFoundError(f"no review queue for {state}: run equity.matching.resolve")
    done = _cached(derived)
    todo = [(k, a, z) for k, a, z in _queue_addresses(queue) if k not in done]
    client = client or PoliteClient(min_interval_s=5.0, timeout_s=900.0)
    sent = 0
    for chunk in list(batches(todo, BATCH))[:max_batches]:
        _append_cache(derived, geocode_batch(client, [(k, a, "", "", z) for k, a, z in chunk]))
        sent += len(chunk)
    return {"to_geocode": len(todo), "sent": sent, "left": len(todo) - sent}


LABEL_SQL = r"""
CREATE MACRO akey(l, z) AS substr(sha256(trim(regexp_replace(upper(coalesce(l, '')),
    '\s+', ' ', 'g')) || '|' || left(trim(coalesce(z, '')), 5)), 1, 24);
CREATE TABLE g AS SELECT key, line1, zip5, tiger_line_id, side,
    CASE WHEN match = 'Match' THEN line1 || '|' || tiger_line_id || '|' || side END AS seg
    FROM read_parquet('{cache}');
CREATE TABLE p AS
SELECT q.*, d.line1 AS debtor_std, d.zip5 AS debtor_std_zip, d.seg AS debtor_seg,
       m.seg AS mail_seg, m.zip5 AS mail_std_zip, s.seg AS situs_seg, s.zip5 AS situs_std_zip
FROM read_parquet('{queue}') q
LEFT JOIN g d ON d.key = akey(q.debtor_line1, q.debtor_zip)
LEFT JOIN g m ON m.key = akey(q.mail_line1, q.mail_zip)
LEFT JOIN g s ON s.key = akey(q.situs_line1, q.situs_zip);
CREATE TABLE crowd AS
SELECT debtor_seg, count(DISTINCT parcel_uid) AS parcels FROM p
WHERE debtor_seg IS NOT NULL GROUP BY 1;
CREATE TABLE review_geo AS
SELECT p.*,
       debtor_seg IS NOT NULL AND debtor_seg IN (mail_seg, situs_seg) AS same_segment,
       (debtor_seg IS NOT NULL AND debtor_seg = mail_seg AND debtor_std_zip = mail_std_zip)
         OR (debtor_seg IS NOT NULL AND debtor_seg = situs_seg
             AND debtor_std_zip = situs_std_zip) AS same_zip,
       regexp_matches(upper(coalesce(p.debtor_line1, '')), '{unit}')
         OR regexp_matches(upper(coalesce(p.mail_line1, '')), '{unit}')
         OR regexp_matches(upper(coalesce(p.situs_line1, '')), '{unit}')
         OR coalesce(c.parcels, 0) > 1 AS multi_unit,
       debtor_seg IS NOT NULL AS debtor_geocoded
FROM p LEFT JOIN crowd c USING (debtor_seg);
"""


def label(derived: Path, state: str) -> dict[str, Any]:
    out = derived / state
    con = duckdb.connect()
    con.execute(LABEL_SQL.format(cache=(derived / CACHE).as_posix(),
                                 queue=(out / "review_queue.parquet").as_posix(),
                                 unit=UNIT))  # fmt: skip

    def debtors(where: str) -> int:
        row = con.execute(f"SELECT count(DISTINCT debtor_party_id) FROM review_geo WHERE {where}"  # noqa: S608
                          ).fetchone()  # fmt: skip
        return int(row[0]) if row else 0

    by_cat = dict(con.execute(
        "SELECT category, count(DISTINCT debtor_party_id) FILTER (WHERE same_segment) "
        "FROM review_geo GROUP BY 1 ORDER BY 1").fetchall())  # fmt: skip
    summary = {
        "state": state,
        "review_debtors": debtors("true"),
        "debtor_address_geocoded": debtors("debtor_geocoded"),
        "same_segment": debtors("same_segment"),
        "same_segment_single_unit": debtors("same_segment AND NOT multi_unit"),
        "same_segment_multi_unit": debtors("same_segment AND multi_unit"),
        "same_zip": debtors("same_zip"),
        "same_segment_by_category": by_cat,
    }
    con.execute(f"COPY review_geo TO '{(out / 'review_geo.parquet').as_posix()}' (FORMAT parquet)")
    cols = ("category, debtor_name, debtor_line1, debtor_zip, owner_name, mail_line1, "
            "mail_zip, situs_line1, situs_zip, debtor_std, debtor_std_zip, multi_unit")  # fmt: skip
    con.execute(
        f"COPY (SELECT * FROM (SELECT {cols} FROM review_geo WHERE same_segment AND NOT multi_unit "  # noqa: S608
        "ORDER BY debtor_party_id, owner_party_id LIMIT 25) UNION ALL "
        f"SELECT * FROM (SELECT {cols} FROM review_geo WHERE same_segment AND multi_unit "
        "ORDER BY debtor_party_id, owner_party_id LIMIT 10)) "
        f"TO '{(out / 'review_geo_sample.csv').as_posix()}' (HEADER)"
    )
    (out / "review_geo_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.matching.review_geo")
    ap.add_argument("--state", required=True, help="derived folder name, e.g. NY or MI-WAYNE")
    ap.add_argument("--derived", type=Path, default=DERIVED)
    ap.add_argument("--max-batches", type=int, default=1)
    ap.add_argument("--label-only", action="store_true", help="skip geocoding; relabel")
    args = ap.parse_args(argv)
    state = args.state.lower()
    if not re.fullmatch(r"[a-z0-9-]+", state):
        ap.error("bad state")
    progress = {} if args.label_only else geocode_queue(args.derived, state, args.max_batches)
    json.dump({"geocode": progress, "labels": label(args.derived, state)}, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
