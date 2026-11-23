"""Debtor scoring: factors per person from a state's match output, and a score and tier
only when every weight in config/scoring.yaml is set (Brandon's decisions).

    uv run python -m equity.rules.score --state OH

Reads data/derived/<state>/: people (open amount, parcels, value, debt kinds),
bankruptcy_flags and transfer_flags when present. Statute time comes from config/sol.yaml
(judgment_enforceable_years for the run's state); a null there leaves sol_years_left null.

Writes data/derived/<state>/scores.parquet (one row per person: the factors, and score and
tier when scoring is complete) and score_report.json (which parameters are missing).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import duckdb

from equity.config import _load

DERIVED = Path("data") / "derived"
TAX_KINDS = ("tax_lien", "tax_warrant", "tax_delinquency")


def weights(config_dir: Path | None = None) -> tuple[dict[str, float | None], list[dict[str, Any]]]:
    data = _load("scoring.yaml", config_dir)
    factors = {str(k): (None if v is None else float(v)) for k, v in data["factors"].items()}
    return factors, list(data.get("tiers") or [])


def enforceable_years(state: str, config_dir: Path | None = None) -> float | None:
    entry = (_load("sol.yaml", config_dir).get("states") or {}).get(state.upper()) or {}
    years = entry.get("judgment_enforceable_years")
    return None if years is None else float(years)


def _view(con: duckdb.DuckDBPyConnection, name: str, path: Path, empty: str | None) -> None:
    """A view over one derived Parquet file, or an empty stand-in with `empty`'s columns."""
    if path.exists():
        body = f"SELECT * FROM read_parquet('{path.as_posix()}')"  # noqa: S608
    elif empty is not None:
        body = f"SELECT {empty} WHERE false"
    else:
        raise FileNotFoundError(path)
    con.execute(f"CREATE VIEW {name} AS {body}")


FACTORS_SQL = """
CREATE TEMP TABLE factors AS
SELECT p.person_id, p.name,
       coalesce(p.open_amount, 0)::DOUBLE AS open_amount,
       coalesce(p.parcel_value, 0)::DOUBLE AS parcel_value,
       coalesce(p.parcels, 0)::DOUBLE AS parcels,
       list_contains(p.debt_kinds, 'court_judgment')::INT AS court_judgment,
       list_contains(p.debt_kinds, 'charged_off_loan')::INT AS charged_off_loan,
       (list_has_any(p.debt_kinds, {tax_kinds}))::INT AS tax_debt,
       coalesce(b.open_case, 0) AS bankruptcy_open,
       coalesce(b.discharged, 0) AS bankruptcy_discharged,
       coalesce(t.transfers, 0)::DOUBLE AS transfers_after_debt,
       coalesce(t.nominee, 0) AS nominee_transfer,
       {sol_years} AS sol_years_left
FROM people p
LEFT JOIN (SELECT person_id, max((status = 'open')::INT) AS open_case,
                  max((status = 'discharged')::INT) AS discharged
           FROM bk GROUP BY 1) b USING (person_id)
LEFT JOIN (SELECT po.person_id, count(DISTINCT f.deed_uid) FILTER (WHERE f.decision = 'auto')
                      AS transfers,
                  max(f.nominee_llc::INT) AS nominee
           FROM tf f JOIN person_of po ON po.party_id = f.debtor_party_id GROUP BY 1) t
       USING (person_id);
"""


def score_state(
    state: str, derived: Path = DERIVED, config_dir: Path | None = None
) -> dict[str, Any]:
    folder = derived / state.lower()
    people = folder / "people.parquet"
    if not people.exists():
        raise FileNotFoundError(f"{people}: run the {state} match first")
    w, tiers = weights(config_dir)
    years = enforceable_years(state.split("-", 1)[0], config_dir)
    con = duckdb.connect()
    # Paths are the run's own derived files; weights and tier names come from repo config.
    _view(con, "people", folder / "people.parquet", None)
    _view(con, "bk", folder / "bankruptcy_flags.parquet",
          "NULL::VARCHAR AS person_id, NULL::VARCHAR AS status")  # fmt: skip
    _view(con, "tf", folder / "transfer_flags.parquet",
          "NULL::VARCHAR AS debtor_party_id, NULL::VARCHAR AS deed_uid, "
          "NULL::VARCHAR AS decision, NULL::BOOLEAN AS nominee_llc")  # fmt: skip
    _view(con, "person_of", folder / "person_of.parquet",
          "NULL::VARCHAR AS party_id, NULL::VARCHAR AS person_id")  # fmt: skip
    # Years left needs the oldest open debt date, which people does not carry yet: until it
    # does, the factor is the period itself (or NULL when sol.yaml has no value).
    sol = "NULL::DOUBLE" if years is None else f"{years!r}::DOUBLE"
    kinds = "[" + ", ".join(f"'{k}'" for k in TAX_KINDS) + "]"
    con.execute(FACTORS_SQL.format(tax_kinds=kinds, sol_years=sol))
    missing = sorted(k for k, v in w.items() if v is None)
    if years is None:
        missing.append(f"sol.yaml {state.split('-', 1)[0].upper()}.judgment_enforceable_years")
    if not tiers:
        missing.append("scoring.yaml tiers")
    complete = not missing
    score, tier = "NULL::DOUBLE", "NULL::VARCHAR"
    if complete:
        score = " + ".join(f"{v!r} * coalesce({k}, 0)" for k, v in sorted(w.items()))
        ranked = sorted(tiers, key=lambda t: -float(t["min_score"]))
        tier = (
            "CASE "
            + " ".join(
                f"WHEN ({score}) >= {float(t['min_score'])!r} THEN '{t['name']}'" for t in ranked
            )
            + " END"
        )
    out = (folder / "scores.parquet").as_posix()
    sql = (
        f"COPY (SELECT *, {score} AS score, {tier} AS tier FROM factors "  # noqa: S608
        f"ORDER BY score DESC NULLS LAST, open_amount DESC, person_id) TO '{out}' (FORMAT PARQUET)"
    )
    con.execute(sql)
    row = con.execute("SELECT count(*) FROM factors").fetchone()
    report = {"state": state, "people": row[0] if row else 0, "scored": complete,
              "missing_parameters": missing}  # fmt: skip
    (folder / "score_report.json").write_text(json.dumps(report, indent=1))
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.rules.score")
    ap.add_argument("--state", required=True)
    ap.add_argument("--derived", type=Path, default=DERIVED)
    args = ap.parse_args(argv)
    json.dump(score_state(args.state, args.derived), sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
