"""Identity graph: every link a run made, as one edge list, and the chains they form.

Each matching step links two things on its own evidence: a debtor to an owner record
(resolve rules), debtor parties to one person (people), an owner company to a registry entity
and that entity to its role holders (entities), a debtor to a company (entities), a debtor to
a deed (transfers) or a bankruptcy case (bankruptcy). A chain of those (a debtor -> the LLC
whose tax bill goes to their home -> the LLC's registry entity -> its other properties) is
only visible once they are one graph. Runs last, on the same connection, after every step.

Nodes are typed ids: debtor:<party>, person:<person_id>, owner:<party>, parcel:<parcel_uid>,
company:<sos_id>, officer:<party>, case:<case_uid>. Edges carry the link type, the rule that
made it and its decision ('auto' or 'review'), so every chain can be re-derived and shown
with its weakest step.

Components (connected sets) are computed twice: over 'auto' edges only (comp_auto: every
step is evidence a rule accepts on its own) and over all edges (comp_any: leads to review).
A company or officer node with more than HUB_MAX_DEGREE links is a hub (a registered agent
that serves thousands of companies, a bank): its edges are kept in graph_edges, but chains
never pass through it, or one agent would join every company it serves.

Outputs (Parquet in the state's derived folder, git-ignored: they name people):
  graph_edges   src, dst, link, rule_id, decision
  graph_nodes   node, kind, comp_auto, comp_any, hub
  person_reach  person_id, parcel_uid, strength ('auto' when the parcel is in the person's
                comp_auto, else 'review'), direct (the person's own debtor-owner match)
"""

from __future__ import annotations

import duckdb

# Links a company or officer node may have before it is a hub that chains do not cross.
# TODO(Brandon): confirm 50.
HUB_MAX_DEGREE = 50
# Label propagation stops when nothing changes; this caps the passes (a chain longer than
# this is cut, and the summary says the cap was reached).
MAX_PASSES = 200


def _has(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    row = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()
    return bool(row and row[0])


EDGES: dict[str, str] = {
    # table -> SELECT src, dst, link, rule_id, decision
    "person_of": "SELECT 'debtor:' || party_id, 'person:' || person_id, 'same_person', "
    "'people', 'auto' FROM person_of",
    "matches": "SELECT 'debtor:' || debtor_party_id, "
    "CASE WHEN owner_party_id IS NULL THEN 'parcel:' || parcel_uid "
    "ELSE 'owner:' || owner_party_id END, 'debtor_owner', rule_id, decision FROM matches",
    "owner_companies": "SELECT 'owner:' || owner_party_id, 'company:' || sos_id, "
    "'owner_company', 'org_name_registry', "
    "CASE WHEN ambiguous THEN 'review' ELSE 'auto' END FROM owner_companies",
    "company_people": "SELECT 'company:' || sos_id, 'officer:' || party_id, 'role_holder', "
    "coalesce(role, 'role'), 'auto' FROM company_people",
    "debtor_companies": "SELECT 'debtor:' || debtor_party_id, 'company:' || sos_id, "
    "'debtor_company', rule_id, decision FROM debtor_companies",
    "transfer_flags": "SELECT 'debtor:' || debtor_party_id, 'parcel:' || parcel_uid, "
    "'transfer', rule_id, decision FROM transfer_flags",
    "bankruptcy_flags": "SELECT 'debtor:' || debtor_party_id, 'case:' || case_uid, "
    "'bankruptcy', rule_id, decision FROM bankruptcy_flags",
}

# Every owner record in the graph owns its parcel.
OWNS_SQL = """
INSERT INTO graph_edges
SELECT DISTINCT 'owner:' || o.party_id, 'parcel:' || o.parcel_uid, 'owns', 'owner_roll', 'auto'
FROM owners o
WHERE o.parcel_uid IS NOT NULL
  AND 'owner:' || o.party_id IN (SELECT src FROM graph_edges UNION SELECT dst FROM graph_edges);
"""

NODES_SQL = """
CREATE OR REPLACE TEMP TABLE graph_nodes AS
WITH n AS (SELECT src AS node FROM graph_edges UNION SELECT dst FROM graph_edges),
deg AS (
    SELECT node, count(*) AS degree FROM (
        SELECT src AS node FROM graph_edges UNION ALL SELECT dst FROM graph_edges)
    GROUP BY node
)
SELECT n.node, split_part(n.node, ':', 1) AS kind,
       split_part(n.node, ':', 1) IN ('company', 'officer')
           AND deg.degree > {hub_max} AS hub
FROM n JOIN deg USING (node);
"""


def _components(con: duckdb.DuckDBPyConnection, decisions: tuple[str, ...], col: str) -> int:
    """Label every node with the smallest node id it reaches over edges whose decision is in
    `decisions` and that touch no hub. Returns the passes taken."""
    allowed = ", ".join(f"'{d}'" for d in decisions)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE g_adj AS
        WITH e AS (
            SELECT src, dst FROM graph_edges
            WHERE decision IN ({allowed})
              AND src NOT IN (SELECT node FROM graph_nodes WHERE hub)
              AND dst NOT IN (SELECT node FROM graph_nodes WHERE hub))
        SELECT src AS a, dst AS b FROM e UNION SELECT dst, src FROM e;
        CREATE OR REPLACE TEMP TABLE g_lab AS SELECT node, node AS comp FROM graph_nodes;
    """)  # noqa: S608 - decisions are constants
    passes = 0
    while passes < MAX_PASSES:
        passes += 1
        con.execute("""
            CREATE OR REPLACE TEMP TABLE g_next AS
            SELECT l.node, least(l.comp, coalesce(min(n.comp), l.comp)) AS comp
            FROM g_lab l LEFT JOIN g_adj e ON e.a = l.node LEFT JOIN g_lab n ON n.node = e.b
            GROUP BY l.node, l.comp;
        """)
        row = con.execute(
            "SELECT count(*) FROM g_next x JOIN g_lab l USING (node) WHERE x.comp <> l.comp"
        ).fetchone()
        con.execute("CREATE OR REPLACE TEMP TABLE g_lab AS SELECT * FROM g_next")
        if not row or row[0] == 0:
            break
    con.execute(f"ALTER TABLE graph_nodes ADD COLUMN {col} VARCHAR")
    con.execute(f"UPDATE graph_nodes SET {col} = l.comp FROM g_lab l "  # noqa: S608
                "WHERE l.node = graph_nodes.node")  # fmt: skip
    return passes


REACH_SQL = """
CREATE OR REPLACE TEMP TABLE person_reach AS
WITH p AS (SELECT node, comp_auto, comp_any FROM graph_nodes WHERE kind = 'person'),
lots AS (SELECT node, comp_auto, comp_any FROM graph_nodes WHERE kind = 'parcel'),
direct AS (
    SELECT DISTINCT 'person:' || po.person_id AS node, 'parcel:' || m.parcel_uid AS lot
    FROM matches m JOIN person_of po ON po.party_id = m.debtor_party_id
    WHERE m.decision = 'auto'
)
SELECT DISTINCT substr(p.node, 8) AS person_id, substr(l.node, 8) AS parcel_uid,
       CASE WHEN p.comp_auto = l.comp_auto THEN 'auto' ELSE 'review' END AS strength,
       (p.node, l.node) IN (SELECT (node, lot) FROM direct) AS direct
FROM p JOIN lots l ON l.comp_any = p.comp_any;
"""


def compute(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE OR REPLACE TEMP TABLE graph_edges (src VARCHAR, dst VARCHAR, "
                "link VARCHAR, rule_id VARCHAR, decision VARCHAR)")  # fmt: skip
    for table, select in EDGES.items():
        if _has(con, table):
            con.execute(f"INSERT INTO graph_edges SELECT DISTINCT * FROM ({select})")  # noqa: S608
    con.execute(OWNS_SQL)
    con.execute(NODES_SQL.format(hub_max=int(HUB_MAX_DEGREE)))
    passes_auto = _components(con, ("auto",), "comp_auto")
    passes_any = _components(con, ("auto", "review"), "comp_any")
    con.execute(REACH_SQL)
    con.execute(
        "CREATE OR REPLACE TEMP TABLE graph_passes AS SELECT ? AS auto_passes, ? AS any_passes",
        [passes_auto, passes_any],
    )


TABLES = ("graph_edges", "graph_nodes", "person_reach")


def summary(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    def one(sql: str, *params: object) -> object:
        row = con.execute(sql, list(params)).fetchone()
        return None if row is None else row[0]

    return {
        "edges_by_link": dict(con.execute(
            "SELECT link, count(*) FROM graph_edges GROUP BY 1 ORDER BY 1").fetchall()),
        "nodes": one("SELECT count(*) FROM graph_nodes"),
        "hubs": one("SELECT count(*) FROM graph_nodes WHERE hub"),
        "components_auto": one("SELECT count(DISTINCT comp_auto) FROM graph_nodes"),
        "components_any": one("SELECT count(DISTINCT comp_any) FROM graph_nodes"),
        "largest_component_auto": one(
            "SELECT max(n) FROM (SELECT count(*) AS n FROM graph_nodes GROUP BY comp_auto)"),
        "largest_component_any": one(
            "SELECT max(n) FROM (SELECT count(*) AS n FROM graph_nodes GROUP BY comp_any)"),
        # People who reach a parcel only through a chain (no direct match of their own).
        "people_reaching_parcels_by_chain_auto": one(
            "SELECT count(DISTINCT person_id) FROM person_reach WHERE strength = 'auto' "
            "AND NOT direct AND person_id NOT IN "
            "(SELECT person_id FROM person_reach WHERE direct)"),
        "parcels_reached_by_chain_auto": one(
            "SELECT count(*) FROM person_reach WHERE strength = 'auto' AND NOT direct"),
        "parcels_reached_review": one(
            "SELECT count(*) FROM person_reach WHERE strength = 'review'"),
        "passes_cap_reached": one(
            "SELECT greatest(auto_passes, any_passes) >= ? FROM graph_passes", MAX_PASSES),
    }  # fmt: skip
