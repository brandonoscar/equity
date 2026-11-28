"""Out-of-state owners: property in one state whose tax bill is mailed to another.

A state's run reads that state's owner rolls, so a New York debtor's Florida rental, its bill
mailed to the debtor's New York home, was never seen. `build` reads every run's owner
sources (resolve.STATES) and keeps each owner record whose mailing address is in a different
state from its parcel (the parcel's state is its parcel_uid's first two digits, a state
FIPS; the mailing state is the address's two-letter state). A state's run then adds the
records mailed into it to its owners (owner_basis 'out_of_state'), so every address rule
can meet them: a debtor at the mailing address reaches the parcel in the other state.

    uv run python -m equity.matching.crossstate          # writes INDEX

Output (git-ignored, it names people): data/derived/_national/out_of_state_owners.parquet
  party_id, raw_name, party_kind, org_name_norm, parcel_uid, parcel_state, line1, city,
  mail_state, zip5, source_id
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from equity.geo import counties

INDEX = Path("data/derived/_national/out_of_state_owners.parquet")


def owner_sources() -> list[str]:
    from equity.matching.resolve import STATES

    return sorted({s for spec in STATES.values() for s in spec["owners"]})


SQL = """
COPY (
    SELECT DISTINCT p.party_id, p.raw_name, p.party_kind, p.org_name_norm, s.parcel_uid,
           st.abbr AS parcel_state, a.line1, a.city, upper(trim(a.state)) AS mail_state,
           a.zip5, s.source_id
    FROM x_snap s JOIN x_party p USING (party_id)
    JOIN x_addr a ON a.address_id = p.address_id
    JOIN x_state st ON st.fips = left(s.parcel_uid, 2)
    WHERE length(trim(coalesce(a.state, ''))) = 2 AND upper(trim(a.state)) <> st.abbr
      AND upper(trim(a.state)) IN (SELECT abbr FROM x_state)
    ORDER BY ALL
) TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)
"""


def build(lake: Path, out: Path = INDEX, sources: list[str] | None = None) -> int:
    """Write the out-of-state owner index; returns its row count."""
    from equity.matching.resolve import _glob, _view

    sources = sources if sources is not None else owner_sources()
    con = duckdb.connect()
    _view(con, "x_party", lake, sources, "party")
    _view(con, "x_addr", lake, sources, "address")
    files = _glob(lake, sources, "owner_snapshot")
    if files is None:
        con.execute(
            "CREATE TEMP VIEW x_snap AS SELECT NULL::VARCHAR AS parcel_uid, "
            "NULL::VARCHAR AS party_id, NULL::VARCHAR AS source_id WHERE false"
        )
    else:
        # The source of each snapshot row: its lake folder (data/lake/<source>/...).
        con.execute(
            f"CREATE TEMP VIEW x_snap AS SELECT TRY_CAST(parcel_uid AS VARCHAR) AS parcel_uid, "  # noqa: S608
            "TRY_CAST(party_id AS VARCHAR) AS party_id, "
            "regexp_extract(filename, '([^/\\\\]+)[/\\\\]owner_snapshot[/\\\\]', 1) AS source_id "
            f"FROM read_parquet({files}, union_by_name=true, filename=true)"
        )
    con.execute("CREATE TEMP TABLE x_state (abbr VARCHAR, fips VARCHAR)")
    con.executemany("INSERT INTO x_state VALUES (?, ?)",
                    sorted({(c.state, c.state_fips) for c in counties()}))  # fmt: skip
    out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(SQL.format(out=out.as_posix()))
    row = con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()  # noqa: S608
    return int(row[0]) if row else 0


# Owner rows for a run: the index records mailed into the run's state, keyed like owners.
ROWS_SQL = (
    "CREATE OR REPLACE TEMP TABLE xs_rows AS SELECT * FROM read_parquet(?) WHERE mail_state = ?"
)
LOAD_SQL = """
INSERT INTO addr
SELECT DISTINCT 'xs:' || party_id,
       CASE WHEN street_norm(line1) <> '' AND zip5 IS NOT NULL
            THEN street_norm(line1) || '|' || zip5 END,
       CASE WHEN street_norm(line1) <> '' AND city IS NOT NULL
            THEN street_norm(line1) || '|' || upper(trim(city)) END,
       zip5,
       CASE WHEN len(string_split(street_norm(unit_strip(line1)), ' ')) >= 2
                 AND zip5 IS NOT NULL
            THEN street_norm(unit_strip(line1)) || '|' || zip5 END
FROM xs_rows;
INSERT INTO owners
SELECT DISTINCT x.party_id, x.raw_name, x.party_kind, x.org_name_norm, x.parcel_uid,
       name_key(x.raw_name), suffix_key(x.raw_name), a.addr_key, a.zip5, NULL, NULL,
       a.town_key, NULL, 'out_of_state', NULL::DATE, NULL
FROM xs_rows x JOIN addr a ON a.address_id = 'xs:' || x.party_id
WHERE (x.party_id, x.parcel_uid) NOT IN (SELECT (party_id, parcel_uid) FROM owners);
"""


def load(con: duckdb.DuckDBPyConnection, index: Path, state: str) -> None:
    """Add the index's records mailed into `state` (two letters) to the run's owners."""
    con.execute(ROWS_SQL, [index.as_posix(), state.upper()])
    con.execute(LOAD_SQL)


def main(argv: list[str] | None = None) -> int:
    from equity.matching.resolve import LAKE

    ap = argparse.ArgumentParser(prog="equity.matching.crossstate")
    ap.add_argument("--lake", type=Path, default=LAKE)
    ap.add_argument("--out", type=Path, default=INDEX)
    args = ap.parse_args(argv)
    n = build(args.lake, args.out)
    print(f"{n} out-of-state owner records -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
