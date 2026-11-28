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

Company networks: one officer across companies, an officer's own property, and companies
whose role holders share an address (see OFFICER_SQL).

Owner records that are one owner (same organization name in the state; same person name
sharing an address; same person name in one ZIP for review) are joined (same_owner, see
CLUSTER_SQL), so a debtor matched to one of a landlord's parcels reaches all of them.

A parcel ends a chain (co-owners of one house are not one owner): sets are built without
parcels, and a person reaches each parcel linked to a node of their set.

Components (connected sets) are computed twice: over 'auto' edges only (comp_auto: every
step is evidence a rule accepts on its own) and over all edges (comp_any: leads to review).
A company or officer node with more than HUB_MAX_DEGREE links is a hub (a registered agent
that serves thousands of companies, a bank): its edges are kept in graph_edges, but chains
never pass through it, or one agent would join every company it serves.

Outputs (Parquet in the state's derived folder, git-ignored: they name people):
  graph_edges   src, dst, link, rule_id, decision
  graph_nodes   node, kind, comp_auto, comp_any, hub
  households    person_id, owner record and parcel of a likely spouse or relative at the
                same address (same surname, another first name): not liable, never a reach
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

# Owner records that are one owner, for every owner already in the graph (owner rolls keep
# one record per parcel, so a landlord's five parcels are five records):
#   owner_org_name      the same organization name in the run's state: a registered name is
#                       unique within a state                                      auto
#   owner_name_address  the same person name (and suffix), sharing a mailing or property
#                       address (or its building without the unit)                 auto
#   owner_name_zip      the same person name and suffix with a mailing address in one ZIP
#                       (a common name in a ZIP is not one person)                 review
# Each group is a star around its smallest record id, so the edges grow with the records.
# A joint or trust variant of an owner string is not its own owner, so it groups nothing.
CLUSTER_SQL = """
CREATE OR REPLACE TEMP TABLE g_seed AS
SELECT DISTINCT CASE WHEN o.party_kind = 'org' THEN 'org:' || o.org_name_norm
                     ELSE 'person:' || o.name_key END AS k
FROM owners o
WHERE 'owner:' || o.party_id IN (SELECT src FROM graph_edges UNION SELECT dst FROM graph_edges)
  AND coalesce(o.name_variant, 'alias') = 'alias'
  AND ((o.party_kind = 'org' AND coalesce(o.org_name_norm, '') <> '')
       OR (o.party_kind <> 'org' AND name_words(o.name_key) >= 2));
CREATE OR REPLACE TEMP TABLE g_group AS
WITH c AS (
    SELECT o.party_id, o.party_kind, o.suffix_key, o.mail_zip,
           CASE WHEN o.party_kind = 'org' THEN 'org:' || o.org_name_norm
                ELSE 'person:' || o.name_key END AS k,
           coalesce(mb.base_key, o.mail_key) AS mail, coalesce(sb.base_key, o.situs_key) AS situs
    FROM owners o
    LEFT JOIN addr_base mb ON mb.addr_key = o.mail_key
    LEFT JOIN addr_base sb ON sb.addr_key = o.situs_key
    WHERE coalesce(o.name_variant, 'alias') = 'alias'
)
SELECT DISTINCT party_id, k AS grp, 'owner_org_name' AS rule_id, 'auto' AS decision
FROM c WHERE party_kind = 'org' AND k IN (SELECT k FROM g_seed)
UNION ALL
SELECT DISTINCT party_id, k || '|' || suffix_key || '|' || a, 'owner_name_address', 'auto'
FROM (SELECT party_id, k, suffix_key, mail AS a FROM c WHERE party_kind <> 'org'
      UNION SELECT party_id, k, suffix_key, situs FROM c WHERE party_kind <> 'org')
WHERE a IS NOT NULL AND k IN (SELECT k FROM g_seed)
UNION ALL
SELECT DISTINCT party_id, k || '|' || suffix_key || '|zip:' || mail_zip, 'owner_name_zip', 'review'
FROM c WHERE party_kind <> 'org' AND mail_zip IS NOT NULL AND k IN (SELECT k FROM g_seed);
INSERT INTO graph_edges
WITH hub AS (SELECT grp, rule_id, min(party_id) AS h FROM g_group GROUP BY grp, rule_id)
SELECT DISTINCT 'owner:' || g.party_id, 'owner:' || hub.h, 'same_owner', g.rule_id, g.decision
FROM g_group g JOIN hub USING (grp, rule_id)
WHERE g.party_id <> hub.h;
"""

# Company networks, from the registries' role holders (company_people):
#   same_officer      one person (same name and suffix, same address or its building) holding
#                     roles in several companies: their officer records are one node (auto)
#   officer_owner     an officer who owns property in their own name at their filing address
#                     (or its building): a company debtor reaches its officers' homes (auto)
#   shared_address    companies whose role holders file from one address (review); an
#                     address many companies use (a registered agent, a law firm) makes its
#                     star centre a hub, which chains do not cross
OFFICER_SQL = """
CREATE OR REPLACE TEMP TABLE g_officer AS
SELECT DISTINCT party_id, sos_id, name_key, suffix_key, party_kind, addr_key,
       coalesce(base_key, addr_key) AS place
FROM company_people WHERE addr_key IS NOT NULL;
INSERT INTO graph_edges
WITH grp AS (
    SELECT party_id, name_key || '|' || suffix_key || '|' || place AS g FROM g_officer
    WHERE party_kind <> 'org' AND name_words(name_key) >= 2
), hub AS (SELECT g, min(party_id) AS h FROM grp GROUP BY g)
SELECT DISTINCT 'officer:' || grp.party_id, 'officer:' || hub.h, 'same_officer',
       'officer_name_address', 'auto'
FROM grp JOIN hub USING (g) WHERE grp.party_id <> hub.h;
INSERT INTO graph_edges
SELECT DISTINCT 'officer:' || c.party_id, 'owner:' || o.party_id, 'officer_owner',
       'officer_name_address', 'auto'
FROM g_officer c JOIN owners o ON o.name_key = c.name_key
JOIN addr_alias aa ON aa.k = c.addr_key AND aa.k2 IN (o.mail_key, o.situs_key)
WHERE c.party_kind <> 'org' AND o.party_kind <> 'org' AND name_words(c.name_key) >= 2
  AND NOT suffix_conflict(c.suffix_key, o.suffix_key)
  AND coalesce(o.name_variant, 'alias') = 'alias';
INSERT INTO graph_edges
WITH hub AS (SELECT place, min(sos_id) AS h FROM g_officer GROUP BY place
             HAVING count(DISTINCT sos_id) > 1)
SELECT DISTINCT 'company:' || c.sos_id, 'company:' || hub.h, 'shared_address',
       'role_holder_address', 'review'
FROM g_officer c JOIN hub USING (place) WHERE c.sos_id <> hub.h;
"""

# Households: a debtor and an owner record at one address (or its building) whose names share
# a full word (the surname) and differ only in a real first name on each side (JOHN SMITH /
# MARY SMITH; first_names). A spouse or relative does not owe the debt and does not own for
# the debtor: these edges have decision 'household' and join no set (comp_auto, comp_any).
HOUSEHOLD_SQL = """
CREATE OR REPLACE TEMP TABLE households AS
SELECT DISTINCT po.person_id, o.party_id AS owner_party_id, o.parcel_uid, d.raw_name AS debtor_name,
       o.name_key AS owner_name_key, aa.k2 AS addr_key,
       list_filter(string_split(d.name_key, ' '),
                   lambda w: list_contains(string_split(o.name_key, ' '), w))[1] AS surname
FROM debtors d JOIN person_of po ON po.party_id = d.party_id
JOIN addr_alias aa ON aa.k = d.addr_key JOIN o_by_addr o ON o.k = aa.k2
WHERE d.party_kind <> 'org' AND name_words(d.name_key) = 2 AND name_words(o.name_key) = 2
  AND len(name_only(d.name_key, o.name_key)) = 1 AND len(name_only(o.name_key, d.name_key)) = 1
  AND length(list_filter(string_split(d.name_key, ' '),
                         lambda w: list_contains(string_split(o.name_key, ' '), w))[1]) >= 2
  AND name_only(d.name_key, o.name_key)[1] IN (SELECT name FROM first_names)
  AND name_only(o.name_key, d.name_key)[1] IN (SELECT name FROM first_names)
  AND nick_key(d.name_key) <> nick_key(o.name_key);
INSERT INTO graph_edges
SELECT DISTINCT 'person:' || person_id, 'owner:' || owner_party_id, 'household',
       'same_surname_address', 'household'
FROM households;
"""

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
    `decisions` and that touch no hub and no parcel. A parcel ends a chain: two co-owners of
    one house are not one owner, so the house joins nothing. Returns the passes taken."""
    allowed = ", ".join(f"'{d}'" for d in decisions)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE g_adj AS
        WITH e AS (
            SELECT src, dst FROM graph_edges
            WHERE decision IN ({allowed})
              AND src NOT IN (SELECT node FROM graph_nodes WHERE hub OR kind = 'parcel')
              AND dst NOT IN (SELECT node FROM graph_nodes WHERE hub OR kind = 'parcel'))
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


# A person reaches every parcel linked to a node of their set: 'auto' when the person's
# automatic set holds a node with an automatic link to it, else 'review'.
REACH_SQL = """
CREATE OR REPLACE TEMP TABLE person_reach AS
WITH p AS (SELECT node, comp_auto, comp_any FROM graph_nodes WHERE kind = 'person'),
lot_edge AS (
    SELECT src AS node, dst AS lot, decision FROM graph_edges WHERE starts_with(dst, 'parcel:')
    UNION ALL
    SELECT dst, src, decision FROM graph_edges WHERE starts_with(src, 'parcel:')
),
direct AS (
    SELECT DISTINCT 'person:' || po.person_id AS node, 'parcel:' || m.parcel_uid AS lot
    FROM matches m JOIN person_of po ON po.party_id = m.debtor_party_id
    WHERE m.decision = 'auto'
)
SELECT substr(p.node, 8) AS person_id, substr(e.lot, 8) AS parcel_uid,
       CASE WHEN bool_or(n.comp_auto = p.comp_auto AND e.decision = 'auto') THEN 'auto'
            ELSE 'review' END AS strength,
       (p.node, e.lot) IN (SELECT (node, lot) FROM direct) AS direct
FROM p JOIN graph_nodes n ON n.comp_any = p.comp_any
JOIN lot_edge e ON e.node = n.node
GROUP BY p.node, e.lot;
"""


def compute(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE OR REPLACE TEMP TABLE graph_edges (src VARCHAR, dst VARCHAR, "
                "link VARCHAR, rule_id VARCHAR, decision VARCHAR)")  # fmt: skip
    for table, select in EDGES.items():
        if _has(con, table):
            con.execute(f"INSERT INTO graph_edges SELECT DISTINCT * FROM ({select})")  # noqa: S608
    if _has(con, "owners") and _has(con, "addr_base"):
        con.execute(CLUSTER_SQL)
    if _has(con, "company_people") and _has(con, "addr_alias"):
        con.execute(OFFICER_SQL)
    if _has(con, "o_by_addr") and _has(con, "first_names"):
        con.execute(HOUSEHOLD_SQL)
    else:
        con.execute("CREATE OR REPLACE TEMP TABLE households (person_id VARCHAR, "
                    "owner_party_id VARCHAR, parcel_uid VARCHAR, debtor_name VARCHAR, "
                    "owner_name_key VARCHAR, addr_key VARCHAR, surname VARCHAR)")  # fmt: skip
    con.execute(OWNS_SQL)
    con.execute(NODES_SQL.format(hub_max=int(HUB_MAX_DEGREE)))
    passes_auto = _components(con, ("auto",), "comp_auto")
    passes_any = _components(con, ("auto", "review"), "comp_any")
    con.execute(REACH_SQL)
    con.execute(
        "CREATE OR REPLACE TEMP TABLE graph_passes AS SELECT ? AS auto_passes, ? AS any_passes",
        [passes_auto, passes_any],
    )


TABLES = ("graph_edges", "graph_nodes", "person_reach", "households")


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
        "household_links": one("SELECT count(*) FROM households"),
        "parcels_reached_review": one(
            "SELECT count(*) FROM person_reach WHERE strength = 'review'"),
        "passes_cap_reached": one(
            "SELECT greatest(auto_passes, any_passes) >= ? FROM graph_passes", MAX_PASSES),
    }  # fmt: skip
