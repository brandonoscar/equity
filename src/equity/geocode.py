"""Standardize debtor addresses with the U.S. Census Bureau batch geocoder (free, no key).

Debtor addresses come from many clerks and agencies, each spelling streets its own way, and an
address that does not line up with the owner roll costs a match. The Census geocoder returns
each address as the Census Bureau's standard spelling (TIGER/Line), with coordinates, the
TIGER line id and side, and whether the match was exact.

Only the address goes out (street, city, state, ZIP), keyed by our address_id; no name or
other field is ever sent. Requests are 10,000 addresses at most (the service's limit), spaced
by the polite client. Nothing here changes a match: the output is a lake table that a later,
approved rule may use.

Output: data/lake/us.census.geocoder/address_geocode/<NNNNN>.parquet, one row per address
sent: address_id, match (Match / No_Match / Tie), match_type (Exact / Non_Exact), the
standardized line1, city, state and zip5, lon, lat, tiger_line_id, side, geocoded_on. An
address already in that table is never sent again.

    uv run python -m equity.geocode --sources ny.dtf.tax_warrants --max-batches 1
    uv run python -m equity.geocode --all-debtors --max-batches 5
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from equity.adapters.http import PoliteClient

URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
BENCHMARK = "Public_AR_Current"
BATCH = 10_000  # the service's per-file limit
SOURCE_DIR = "us.census.geocoder"
TABLE = "address_geocode"
LAKE = Path("data/lake")


@dataclass(frozen=True)
class Geocoded:
    address_id: str
    match: str
    match_type: str | None
    line1: str | None
    city: str | None
    state: str | None
    zip5: str | None
    lon: float | None
    lat: float | None
    tiger_line_id: str | None
    side: str | None


def _clean(v: Any) -> str:
    """One line, no commas or quotes (the request file is CSV with fixed columns)."""
    return " ".join(str(v or "").replace(",", " ").replace('"', " ").split())


def request_file(rows: Iterable[Sequence[Any]]) -> bytes:
    """(address_id, line1, city, state, zip5) rows -> the service's 5-column CSV."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    for address_id, line1, city, state, zip5 in rows:
        w.writerow([_clean(address_id), _clean(line1), _clean(city), _clean(state),
                    _clean(zip5)])  # fmt: skip
    return out.getvalue().encode()


def _matched(addr: str) -> tuple[str | None, str | None, str | None, str | None]:
    """'4600 SILVER HILL RD, WASHINGTON, DC, 20233' -> (line1, city, state, zip5)."""
    parts = [p.strip() for p in addr.split(",")]
    if len(parts) < 4:
        return None, None, None, None
    line1, city, state, z = ", ".join(parts[:-3]), parts[-3], parts[-2], parts[-1]
    return line1 or None, city or None, state or None, (z[:5] if z[:5].isdigit() else None)


def parse_response(content: bytes) -> list[Geocoded]:
    """The service's CSV answer: id, input, match[, type, matched address, "lon,lat",
    tiger line id, side]. Rows come back in any order; ids are ours."""
    out: list[Geocoded] = []
    for row in csv.reader(io.StringIO(content.decode("utf-8", "replace"))):
        if len(row) < 3 or not row[0].strip():
            continue
        aid, match = row[0].strip(), row[2].strip()
        mtype = row[3].strip() if len(row) > 3 and row[3].strip() else None
        line1 = city = state = zip5 = None
        lon = lat = None
        if match == "Match" and len(row) >= 6:
            line1, city, state, zip5 = _matched(row[4])
            try:
                lon_s, lat_s = row[5].split(",")
                lon, lat = float(lon_s), float(lat_s)
            except ValueError:
                lon = lat = None
        tiger = row[6].strip() if len(row) > 6 and row[6].strip() else None
        side = row[7].strip() if len(row) > 7 and row[7].strip() else None
        out.append(Geocoded(aid, match, mtype, line1, city, state, zip5, lon, lat, tiger, side))
    return out


def geocode_batch(client: PoliteClient, rows: Sequence[Sequence[Any]]) -> list[Geocoded]:
    if not 0 < len(rows) <= BATCH:
        raise ValueError(f"a batch holds 1 to {BATCH} addresses, not {len(rows)}")
    upload = {"addressFile": ("addresses.csv", request_file(rows))}
    resp = client.post_multipart(URL, {"benchmark": BENCHMARK}, upload)
    if resp.status != 200:
        raise RuntimeError(f"Census geocoder: HTTP {resp.status}")
    return parse_response(resp.content)


def _glob(lake: Path, sources: Sequence[str]) -> list[str]:
    return [p.as_posix() for s in sources for p in sorted((lake / s / "address").glob("*.parquet"))]


def pending(lake: Path, sources: Sequence[str], limit: int) -> list[tuple[Any, ...]]:
    """Addresses of these sources with a street and a state or ZIP, not yet geocoded,
    in address_id order (deterministic)."""
    files = _glob(lake, sources)
    if not files:
        return []
    con = duckdb.connect()
    con.execute(f"CREATE VIEW a AS SELECT * FROM read_parquet({files}, union_by_name=true)")  # noqa: S608
    done = sorted((lake / SOURCE_DIR / TABLE).glob("*.parquet"))
    paths = [p.as_posix() for p in done]
    seen = f"AND address_id NOT IN (SELECT address_id FROM read_parquet({paths}))" if done else ""  # noqa: S608
    return con.execute(
        "SELECT DISTINCT address_id, line1, city, state, zip5 FROM a "  # noqa: S608
        "WHERE coalesce(trim(line1), '') <> '' "
        "AND (coalesce(zip5, '') <> '' OR coalesce(state, '') <> '') "
        f"{seen} ORDER BY address_id LIMIT ?",
        [limit],
    ).fetchall()


def write_part(lake: Path, results: Sequence[Geocoded], on: date) -> Path:
    out = lake / SOURCE_DIR / TABLE
    out.mkdir(parents=True, exist_ok=True)
    n = len(list(out.glob("*.parquet")))
    path = out / f"{n:05d}.parquet"
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE g (address_id VARCHAR, match VARCHAR, match_type VARCHAR, line1 VARCHAR, "
        "city VARCHAR, state VARCHAR, zip5 VARCHAR, lon DOUBLE, lat DOUBLE, "
        "tiger_line_id VARCHAR, side VARCHAR, geocoded_on DATE)"
    )
    ordered = sorted(results, key=lambda r: r.address_id)
    con.executemany("INSERT INTO g VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(*vars(r).values(), on) for r in ordered])  # fmt: skip
    con.execute(f"COPY (SELECT * FROM g ORDER BY address_id) TO '{path.as_posix()}' "  # noqa: S608
                "(FORMAT parquet)")  # fmt: skip
    return path


def batches(rows: Sequence[tuple[Any, ...]], size: int = BATCH) -> Iterator[Sequence[Any]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def run(lake: Path, sources: Sequence[str], max_batches: int,
        client: PoliteClient | None = None) -> dict[str, Any]:  # fmt: skip
    client = client or PoliteClient(min_interval_s=5.0, timeout_s=900.0)
    todo = pending(lake, sources, max_batches * BATCH)
    counts: dict[str, int] = {}
    parts = 0
    for chunk in batches(todo):
        results = geocode_batch(client, chunk)
        write_part(lake, results, datetime.now(UTC).date())
        parts += 1
        for r in results:
            key = f"{r.match}/{r.match_type}" if r.match_type else r.match
            counts[key] = counts.get(key, 0) + 1
    return {"sent": len(todo), "parts_written": parts, "by_match": dict(sorted(counts.items()))}


def debtor_sources() -> list[str]:
    from equity.matching.resolve import STATES

    return sorted({s for spec in STATES.values() for s in spec.get("debtors") or []})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.geocode")
    ap.add_argument("--lake", type=Path, default=LAKE)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--sources", nargs="+")
    group.add_argument("--all-debtors", action="store_true",
                       help="every debtor source of every match run")  # fmt: skip
    ap.add_argument("--max-batches", type=int, default=1)
    args = ap.parse_args(argv)
    sources = debtor_sources() if args.all_debtors else args.sources
    json.dump(run(args.lake, sources, args.max_batches), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
