"""Bankruptcy screen: debtors who appear as the debtor in a bankruptcy case in their state.

A debtor in bankruptcy is protected by the automatic stay (11 U.S.C. 362): collection on a
judgment stops, and a discharge can wipe it out. So a match here is a "do not act before
checking" flag, not a hard exclusion. Runs after equity.matching.resolve has built `debtors`,
`person_of` and `people` on the same connection.

Source: the free CM/ECF RSS feeds of the state's bankruptcy courts (config/courts.yaml, ids
ending in 'b'), polled every 2 hours (equity.refresh) since each feed holds about a day.
The feeds give the case number, chapter and the caption (debtor names), never an address,
so matching is on the name alone, within the state:

  person_name   person debtor, same name_key (two or more words) as a bankruptcy debtor
  org_name      organization debtor, same org_name_norm as a bankruptcy debtor

Every flag is `review`: a common name in a large state is not proof. Status comes from the
docket text seen so far: 'dismissed' (an order dismissing the case; a motion to dismiss is
not enough), else 'discharged' (an order of discharge of the debtor; discharging a trustee is
not one), else 'open'. A case first seen mid-way shows only the entries since polling began.

Outputs (Parquet in the state's derived folder, git-ignored: they name people):
  bankruptcy_flags   person, debtor party, bankruptcy case, court, chapter, first/last entry
                     seen, status, match rule
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import yaml

from equity.config import CONFIG_DIR
from equity.matching.resolve import _glob

SQL = """
CREATE TEMP TABLE bk_case AS
SELECT case_uid, any_value(court_id) AS court_id,
       any_value(regexp_extract(coalesce(nature_of_suit, ''), 'chapter (\\d+)', 1)) AS chapter
FROM bk_court_case WHERE case_type = 'bk' GROUP BY case_uid;
CREATE TEMP TABLE bk_status AS
SELECT case_uid, min(entry_date) AS first_entry, max(entry_date) AS last_entry,
       bool_or(regexp_matches(text, '(?i)order dismissing|dismissing case|order to dismiss case'))
           AS dismissed,
       bool_or(regexp_matches(text,
               '(?i)order of discharge|discharging debtor|discharge of debtor')) AS discharged
FROM bk_docket GROUP BY case_uid;
CREATE TEMP TABLE bk_debtor AS
SELECT DISTINCT cp.case_uid, p.party_id AS bk_party_id, p.raw_name, p.party_kind,
       p.org_name_norm, name_key(p.raw_name) AS name_key
FROM bk_case_party cp JOIN bk_party p USING (party_id)
WHERE cp.role = 'debtor' AND cp.case_uid IN (SELECT case_uid FROM bk_case);
CREATE TEMP TABLE bankruptcy_flags AS
WITH hits AS (
    SELECT DISTINCT d.party_id, b.case_uid, 'person_name' AS rule_id
    FROM debtors d JOIN bk_debtor b ON b.name_key = d.name_key
    WHERE d.party_kind <> 'org' AND coalesce(b.party_kind, '') <> 'org'
      AND name_words(d.name_key) >= 2
    UNION
    SELECT DISTINCT d.party_id, b.case_uid, 'org_name'
    FROM debtors d JOIN bk_debtor b ON b.org_name_norm = d.org_name_norm
    WHERE d.party_kind = 'org' AND b.party_kind = 'org' AND coalesce(d.org_name_norm, '') <> ''
)
SELECT po.person_id, pe.name AS person_name, h.party_id AS debtor_party_id, h.case_uid,
       c.court_id, nullif(c.chapter, '') AS chapter, s.first_entry, s.last_entry,
       CASE WHEN s.dismissed THEN 'dismissed' WHEN s.discharged THEN 'discharged'
            ELSE 'open' END AS status,
       h.rule_id, 'review' AS decision
FROM hits h JOIN bk_case c USING (case_uid)
LEFT JOIN bk_status s USING (case_uid)
JOIN person_of po ON po.party_id = h.party_id
JOIN people pe ON pe.person_id = po.person_id;
"""

COLS = {
    "court_case": "case_uid, court_id, case_type, nature_of_suit",
    "case_party": "case_uid, party_id, role",
    "party": "party_id, raw_name, party_kind, org_name_norm",
    "docket_entry": "case_uid, entry_date, text",
}
EMPTY = {
    "court_case": "NULL::VARCHAR AS case_uid, NULL::VARCHAR AS court_id, "
    "NULL::VARCHAR AS case_type, NULL::VARCHAR AS nature_of_suit",
    "case_party": "NULL::VARCHAR AS case_uid, NULL::VARCHAR AS party_id, NULL::VARCHAR AS role",
    "party": "NULL::VARCHAR AS party_id, NULL::VARCHAR AS raw_name, "
    "NULL::VARCHAR AS party_kind, NULL::VARCHAR AS org_name_norm",
    "docket_entry": "NULL::VARCHAR AS case_uid, NULL::DATE AS entry_date, NULL::VARCHAR AS text",
}
VIEWS = {"court_case": "bk_court_case", "case_party": "bk_case_party", "party": "bk_party",
         "docket_entry": "bk_docket"}  # fmt: skip


def sources_for(state: str, config_dir: Path | None = None) -> list[str]:
    """The RSS sources of the state's enabled bankruptcy courts (config/courts.yaml)."""
    data = yaml.safe_load(((config_dir or CONFIG_DIR) / "courts.yaml").read_text())
    enabled = set(data.get("enabled") or [])
    courts = (data.get("courts") or {}).get(state.upper()) or []
    return [f"us.{c}.rss" for c in courts if c.endswith("b") and c in enabled]


def compute(con: duckdb.DuckDBPyConnection, lake: Path, sources: list[str]) -> None:
    for table, view in VIEWS.items():
        files = _glob(lake, sources, table)
        if files is None:
            con.execute(f"CREATE TEMP VIEW {view} AS SELECT {EMPTY[table]} WHERE false")
        else:
            con.execute(f"CREATE TEMP VIEW {view} AS SELECT {COLS[table]} "  # noqa: S608
                        f"FROM read_parquet({files}, union_by_name=true)")  # fmt: skip
    con.execute(SQL)


TABLES = ("bankruptcy_flags",)


def summary(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    def one(sql: str) -> object:
        row = con.execute(sql).fetchone()
        return None if row is None else row[0]

    return {
        "bankruptcy_cases_seen": one("SELECT count(*) FROM bk_case"),
        "people_flagged": one("SELECT count(DISTINCT person_id) FROM bankruptcy_flags"),
        "people_flagged_by_status": dict(con.execute(
            "SELECT status, count(DISTINCT person_id) FROM bankruptcy_flags GROUP BY 1 ORDER BY 1"
        ).fetchall()),
        "people_with_parcels_flagged": one(
            "SELECT count(DISTINCT f.person_id) FROM bankruptcy_flags f "
            "JOIN people p USING (person_id) WHERE p.parcels > 0"
        ),
    }  # fmt: skip
