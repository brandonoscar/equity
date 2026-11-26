"""Search the query catalog (equity.search_index) by name or address, with every hit explained.

    uv run python -m equity.search "JOHN A SMITH" --state OH
    uv run python -m equity.search "ACME HOLDINGS LLC" --kind org --json
    uv run python -m equity.search --address "123 MAIN ST" --zip 43215
    uv run python -m equity.search --show ia.scott.parcels:<party_id>

Name hits are ranked by fixed rules, best first. A query's name_key is built exactly as the
matcher builds it (upper-case words, punctuation and JR/SR/AND/TR/... dropped, de-duplicated,
sorted), so word order and punctuation never matter:

  exact        same name_key                                          score 1.00
  all_words    every query word is in the name, plus 1-2 more words   0.95 / 0.90
  initial      all query words but one are in the name, and that one   0.85
               is an initial of a name word (or the name has its initial);
               every full name word is in the query or expands a query initial
  sounds_like  every query word is in the name or has the same        0.82
               Soundex code as a name word (3+ letters); word counts within 1
  similar      each query word's best Jaro-Winkler similarity to a    0.80 x similarity
               name word, averaged, >= 0.90 (word counts within 1), among
               names sharing one of the query's two rarest words

Registered businesses (Secretary of State records) are searched too; their refs read
source_id:business:<sos_id>, and --show lists their officers, agents and members.
--network walks a party's links outward (parcels, co-owners, documents, cases, businesses,
same address, same name elsewhere) as nodes and edges.

Each hit carries what the catalog links to it: parcels owned (with the latest value), debts
and recorded documents it is a party to, court cases, and businesses it holds a role in.
Address search standardizes the street with the matcher's street_norm (USPS Publication 28
words) and finds parcels at that situs and parties mailed there.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from equity.search_index import DEFAULT_DB, connect

# Doc types that are debts or liens against the party (not deeds or mortgages they hold).
# (The schema's doc_type vocabulary: equity/schema/migrations/V0004__instruments.sql.)
DEBT_TYPES = (
    "JUDGMENT_LIEN", "ABSTRACT_OF_JUDGMENT", "EXECUTION", "LIS_PENDENS", "MECHANICS_LIEN",
    "STATUTORY_LIEN", "TAX_LIEN_STATE", "TAX_LIEN_FEDERAL", "COURT_ORDER",
)  # fmt: skip
SIMILAR_MIN = 0.90
MAX_CANDIDATES = 20000  # name_keys per candidate branch that are scored
MAX_KEYS = 500  # best-scored name_keys whose parties are fetched


@dataclass
class Hit:
    source_id: str
    party_id: str
    raw_name: str
    party_kind: str | None
    rule: str
    score: float
    state: str | None
    address: str | None = None
    parcels: int = 0
    parcel_value: float | None = None
    debts: int = 0
    debt_amount: float | None = None
    documents: int = 0
    cases: int = 0
    businesses: int = 0  # business roles this party holds
    officers: int = 0  # for a business hit: officer, agent and member rows

    @property
    def ref(self) -> str:
        return f"{self.source_id}:{self.party_id}"


@dataclass
class Entity:
    ref: str
    raw_name: str
    party_kind: str | None
    address: str | None
    parcels: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    cases: list[dict[str, Any]] = field(default_factory=list)
    businesses: list[dict[str, Any]] = field(default_factory=list)
    same_name: list[dict[str, Any]] = field(default_factory=list)


def query_key(con: duckdb.DuckDBPyConnection, name: str) -> str:
    row = con.execute("SELECT name_key(?)", [name]).fetchone()
    return str(row[0]) if row and row[0] else ""


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def _in(values: Iterable[str]) -> str:
    """A literal SQL list. Literal lists (not joins) let DuckDB prune row groups by their
    min/max on the sorted catalog tables, so a lookup reads a few blocks, not the table."""
    vals = sorted({v for v in values if v is not None})
    if not vals:
        return "(NULL)"
    return "(" + ", ".join("'" + v.replace("'", "''") + "'" for v in vals) + ")"


RULES_SQL = f"""
WITH k AS (SELECT DISTINCT unnest($keys::VARCHAR[]) AS name_key),
w AS (SELECT name_key, string_split(name_key, ' ') AS w FROM k WHERE name_key <> ''),
scored AS (
    SELECT *,
      -- each query word against its closest name word, averaged
      list_avg(list_transform($words::VARCHAR[], lambda q: list_max(list_transform(w,
          lambda x: jaro_winkler_similarity(q, x))))) AS sim,
      list_transform(w, lambda x: soundex(x)) AS ws
    FROM w
), ruled AS (
    SELECT *, CASE
      WHEN name_key = $key THEN 'exact'
      WHEN list_has_all(w, $words::VARCHAR[]) AND len(w) - $n BETWEEN 1 AND 2 THEN 'all_words'
      -- every query word but one is in the name; that one is an initial of a name word (or
      -- the name has its initial); word counts within 1; no full name word unexplained
      WHEN len(list_filter($words::VARCHAR[], lambda q: list_contains(w, q))) = $n - 1
           AND len(list_filter($words::VARCHAR[], lambda q: NOT list_contains(w, q)
             AND ((length(q) = 1 AND len(list_filter(w, lambda x: x[1] = q)) > 0)
               OR len(list_filter(w, lambda x: length(x) = 1 AND q[1] = x)) > 0))) = 1
           AND len(list_filter(w, lambda x: length(x) >= 2
               AND NOT list_contains($words::VARCHAR[], x)
               AND NOT list_contains($words::VARCHAR[], x[1]))) = 0
           AND abs(len(w) - $n) <= 1 THEN 'initial'
      -- every query word is in the name or sounds like a name word (Soundex, 3+ letters)
      WHEN len(list_filter($words::VARCHAR[], lambda q: list_contains(w, q)
             OR (length(q) >= 3 AND list_contains(ws, soundex(q))))) = $n
           AND abs(len(w) - $n) <= 1 THEN 'sounds_like'
      WHEN sim >= {SIMILAR_MIN} AND abs(len(w) - $n) <= 1 THEN 'similar'
    END AS rule
    FROM scored
)
SELECT name_key, rule,
       CASE rule WHEN 'exact' THEN 1.0
                 WHEN 'all_words' THEN 1.0 - 0.05 * (len(w) - $n)
                 WHEN 'initial' THEN 0.85
                 WHEN 'sounds_like' THEN 0.82
                 ELSE round(0.8 * sim, 4) END AS score
FROM ruled WHERE rule IS NOT NULL
ORDER BY score DESC, name_key
LIMIT {MAX_KEYS}
"""  # noqa: S608


def candidate_keys(con: duckdb.DuckDBPyConnection, key: str) -> list[str]:
    """name_keys worth scoring: the exact key, names holding one of the query's two rarest
    words (a typo in one still finds the name through the other), and names holding a word
    that sounds like one of the query's two longest words (a typo in every word)."""
    words = key.split(" ")
    counts = con.execute(
        f"SELECT word, count(*) FROM name_words WHERE word IN {_in(words)} GROUP BY word"  # noqa: S608
    ).fetchall()
    present = {str(w): int(n) for w, n in counts}
    rare = sorted(present, key=lambda w: (present[w], -len(w), w))[:2]
    out = {key}
    for word in rare:
        out |= {str(r[0]) for r in con.execute(
            f"SELECT DISTINCT name_key FROM name_words WHERE word = ? LIMIT {MAX_CANDIDATES}",  # noqa: S608
            [word]).fetchall()}  # fmt: skip
    long_words = sorted((w for w in words if len(w) >= 3 and w.isalpha()),
                        key=lambda w: (-len(w), w))[:2]  # fmt: skip
    if long_words:
        sounds = [str(r[0]) for r in con.execute(
            "SELECT DISTINCT soundex(w) FROM unnest(?::VARCHAR[]) t(w)", [long_words]
        ).fetchall()]  # fmt: skip
        alike = [str(r[0]) for r in con.execute(
            f"SELECT word FROM word_sounds WHERE sound IN {_in(sounds)} LIMIT 2000"  # noqa: S608
        ).fetchall()]  # fmt: skip
        if alike:
            out |= {str(r[0]) for r in con.execute(
                f"SELECT DISTINCT name_key FROM name_words WHERE word IN {_in(alike)} "  # noqa: S608
                f"LIMIT {MAX_CANDIDATES}").fetchall()}  # fmt: skip
    return sorted(out)


def search(
    con: duckdb.DuckDBPyConnection,
    name: str,
    state: str | None = None,
    kind: str | None = None,
    limit: int = 25,
) -> list[Hit]:
    """Name search over parties and registered businesses, scored by rule (module doc)."""
    key = query_key(con, name)
    if not key:
        return []
    words = key.split(" ")
    ranked = con.execute(RULES_SQL, {"keys": candidate_keys(con, key), "words": words,
                                     "key": key, "n": len(words)}).fetchall()  # fmt: skip
    rule = {str(k): (str(r), float(sc)) for k, r, sc in ranked}
    if not rule:
        return []
    cond = ""
    params: list[Any] = []
    if state:
        cond += " AND s.state = ?"
        params.append(state.upper())
    parties = [] if kind == "business" else _rows(con, f"""
        SELECT n.source_id, n.party_id, n.raw_name, n.party_kind, n.address_id, n.name_key,
               s.state
        FROM names n JOIN sources s USING (source_id)
        WHERE n.name_key IN {_in(rule)} {cond} {"AND n.party_kind = ?" if kind else ""}
    """, params + ([kind] if kind else []))  # noqa: S608  # fmt: skip
    firms = [] if kind not in (None, "org", "business") else _rows(con, f"""
        SELECT b.source_id, 'business:' || b.sos_id AS party_id, b.name AS raw_name,
               'business' AS party_kind, NULL AS address_id, b.name_key, s.state
        FROM businesses b JOIN sources s USING (source_id)
        WHERE b.name_key IN {_in(rule)} {cond}
    """, params)  # noqa: S608  # fmt: skip
    rows = sorted(
        parties + firms,
        key=lambda r: (-rule[r["name_key"]][1], r["raw_name"], r["source_id"], r["party_id"]),
    )[:limit]
    hits = [
        Hit(
            r["source_id"],
            r["party_id"],
            r["raw_name"],
            r["party_kind"],
            rule[r["name_key"]][0],
            rule[r["name_key"]][1],
            r["state"],
        )
        for r in rows
    ]
    _annotate(con, hits, {(r["source_id"], r["party_id"]): r["address_id"] for r in rows})
    return hits


def _annotate(
    con: duckdb.DuckDBPyConnection, hits: list[Hit], addr: dict[tuple[str, str], str | None]
) -> None:
    """Link counts per hit, each a lookup on a sorted table by a literal key list."""
    if not hits:
        return
    ids = {h.party_id for h in hits}
    mine = {(h.source_id, h.party_id) for h in hits}
    owned = [r for r in con.execute(
        f"SELECT source_id, party_id, parcel_uid FROM owners WHERE party_id IN {_in(ids)}"  # noqa: S608
    ).fetchall() if (r[0], r[1]) in mine]  # fmt: skip
    values = {(str(s), str(p)): v for s, p, v in con.execute(
        "SELECT source_id, parcel_uid, coalesce(appraised_total, assessed_value) "  # noqa: S608
        f"FROM parcel_values WHERE parcel_uid IN {_in(str(r[2]) for r in owned)}"
    ).fetchall()}  # fmt: skip
    docs = [r for r in con.execute(
        "SELECT source_id, party_id, instrument_uid FROM instrument_parties "  # noqa: S608
        f"WHERE party_id IN {_in(ids)}").fetchall() if (r[0], r[1]) in mine]  # fmt: skip
    kinds = {(str(s), str(i)): (str(t), a) for s, i, t, a in con.execute(
        "SELECT source_id, instrument_uid, doc_type, amount FROM instruments "  # noqa: S608
        f"WHERE instrument_uid IN {_in(str(r[2]) for r in docs)}").fetchall()}  # fmt: skip
    cases = [r for r in con.execute(
        f"SELECT source_id, party_id FROM case_parties WHERE party_id IN {_in(ids)}"  # noqa: S608
    ).fetchall() if (r[0], r[1]) in mine]  # fmt: skip
    roles = [r for r in con.execute(
        f"SELECT source_id, party_id FROM business_roles WHERE party_id IN {_in(ids)}"  # noqa: S608
    ).fetchall() if (r[0], r[1]) in mine]  # fmt: skip
    firm_ids = {h.party_id.removeprefix("business:") for h in hits
                if h.party_id.startswith("business:")}  # fmt: skip
    officers = con.execute(
        f"SELECT source_id, sos_id, count(*) FROM business_roles WHERE sos_id IN {_in(firm_ids)} "  # noqa: S608
        "GROUP BY ALL").fetchall() if firm_ids else []  # fmt: skip
    staff = {(str(s), "business:" + str(b)): int(n) for s, b, n in officers}
    addr_ids = [a for a in addr.values() if a]
    lines = {r["address_id"]: _addr_text(r) for r in _rows(
        con, f"SELECT * FROM addresses WHERE address_id IN {_in(addr_ids)}", [])  # noqa: S608
    } if addr_ids else {}  # fmt: skip
    for h in hits:
        mine_owned = {str(r[2]) for r in owned if (r[0], r[1]) == (h.source_id, h.party_id)}
        h.parcels = len(mine_owned)
        vals = [values[(h.source_id, p)] for p in mine_owned if values.get((h.source_id, p))]
        h.parcel_value = float(sum(vals)) if vals else None
        my_docs = [kinds.get((h.source_id, str(r[2]))) for r in docs
                   if (r[0], r[1]) == (h.source_id, h.party_id)]  # fmt: skip
        h.documents = len(my_docs)
        debts = [d for d in my_docs if d and d[0] in DEBT_TYPES]
        h.debts = len(debts)
        amounts = [float(d[1]) for d in debts if d[1] is not None]
        h.debt_amount = sum(amounts) if amounts else None
        h.cases = sum(1 for r in cases if (r[0], r[1]) == (h.source_id, h.party_id))
        h.businesses = sum(1 for r in roles if (r[0], r[1]) == (h.source_id, h.party_id))
        h.officers = staff.get((h.source_id, h.party_id), 0)
        a = addr.get((h.source_id, h.party_id))
        h.address = lines.get(a) if a else None


def _addr_text(r: dict[str, Any]) -> str:
    tail = " ".join(x for x in (r.get("state"), r.get("zip5")) if x)
    return ", ".join(x for x in (r.get("line1"), r.get("city"), tail) if x)


def show(con: duckdb.DuckDBPyConnection, ref: str) -> Entity | None:
    """Everything the catalog links to one party: parcels (with situs and latest value),
    documents and debts, court cases, business roles, and same-name parties elsewhere."""
    source_id, _, party_id = ref.partition(":")
    head = _rows(con, "SELECT * FROM names WHERE source_id = ? AND party_id = ? LIMIT 1",
                 [source_id, party_id])  # fmt: skip
    if not head:
        return None
    n = head[0]
    addr = _rows(con, "SELECT * FROM addresses WHERE address_id = ?", [n["address_id"]])
    e = Entity(ref, n["raw_name"], n["party_kind"], _addr_text(addr[0]) if addr else None)
    e.parcels = _rows(con, """
        SELECT o.parcel_uid, o.observed_on, p.land_use_desc, p.zoning,
               v.tax_year, v.appraised_total, v.assessed_value, v.homestead,
               a.line1 AS situs_line1, a.city AS situs_city, a.zip5 AS situs_zip
        FROM owners o
        LEFT JOIN parcels p ON p.source_id = o.source_id AND p.parcel_uid = o.parcel_uid
        LEFT JOIN parcel_values v ON v.source_id = o.source_id AND v.parcel_uid = o.parcel_uid
        LEFT JOIN addresses a ON a.address_id = p.situs_address_id
        WHERE o.source_id = ? AND o.party_id = ?
        ORDER BY o.parcel_uid
    """, [source_id, party_id])  # fmt: skip
    e.documents = _rows(con, """
        SELECT i.instrument_uid, i.doc_type, i.doc_type_raw, i.recorded_on, i.amount,
               i.consideration, ip.role
        FROM instrument_parties ip JOIN instruments i USING (source_id, instrument_uid)
        WHERE ip.source_id = ? AND ip.party_id = ?
        ORDER BY i.recorded_on DESC NULLS LAST, i.instrument_uid
    """, [source_id, party_id])  # fmt: skip
    e.cases = _rows(con, """
        SELECT c.case_uid, c.court_id, c.case_number, c.nature_of_suit, c.filed_on,
               c.closed_on, c.status, cp.role, j.entered_on AS judgment_on,
               j.principal AS judgment_principal
        FROM case_parties cp JOIN cases c USING (source_id, case_uid)
        LEFT JOIN judgments j USING (source_id, case_uid)
        WHERE cp.source_id = ? AND cp.party_id = ?
        ORDER BY c.filed_on DESC NULLS LAST, c.case_uid
    """, [source_id, party_id])  # fmt: skip
    e.businesses = _rows(con, """
        SELECT b.sos_id, b.name, b.org_form, b.status, r.role, r.title
        FROM business_roles r JOIN businesses b USING (source_id, sos_id)
        WHERE r.source_id = ? AND r.party_id = ?
        ORDER BY b.name
    """, [source_id, party_id])  # fmt: skip
    e.same_name = _rows(con, """
        SELECT n.source_id || ':' || n.party_id AS ref, n.raw_name, s.state
        FROM names n JOIN sources s USING (source_id)
        WHERE n.name_key = ? AND NOT (n.source_id = ? AND n.party_id = ?)
        ORDER BY n.source_id, n.party_id LIMIT 50
    """, [n["name_key"], source_id, party_id])  # fmt: skip
    return e


def show_business(con: duckdb.DuckDBPyConnection, ref: str) -> dict[str, Any] | None:
    """A registered business (ref source_id:business:<sos_id>): its record, its officers,
    agents and members, and what each of them owns or owes in the catalog."""
    source_id, _, rest = ref.partition(":")
    sos_id = rest.removeprefix("business:")
    head = _rows(con, "SELECT * FROM businesses WHERE source_id = ? AND sos_id = ? LIMIT 1",
                 [source_id, sos_id])  # fmt: skip
    if not head:
        return None
    people = _rows(con, """
        SELECT r.role, r.title, n.source_id || ':' || n.party_id AS ref, n.raw_name,
               n.party_kind, n.name_key
        FROM business_roles r JOIN names n
          ON n.source_id = r.source_id AND n.party_id = r.party_id
        WHERE r.source_id = ? AND r.sos_id = ?
        ORDER BY r.role, n.raw_name
    """, [source_id, sos_id])  # fmt: skip
    keys = {p["name_key"] for p in people if p["name_key"]}
    owners = _rows(con, f"""
        SELECT n.name_key, count(DISTINCT o.parcel_uid) AS parcels
        FROM names n JOIN owners o USING (source_id, party_id)
        WHERE n.name_key IN {_in(keys)} GROUP BY n.name_key
    """, []) if keys else []  # noqa: S608  # fmt: skip
    owned = {r["name_key"]: int(r["parcels"]) for r in owners}
    for p in people:
        p["parcels_under_same_name"] = owned.get(p.pop("name_key"), 0)
    return {"ref": ref, **head[0], "people": people}


def network(
    con: duckdb.DuckDBPyConnection, ref: str, hops: int = 2, max_nodes: int = 200
) -> dict[str, list[dict[str, Any]]]:
    """Walk the catalog's links outward from one party, breadth first, up to `hops` steps.

    Edges: owns (party-parcel), party_to (party-document), in_case (party-case),
    role (party-business), same_address (parties with one address_id) and same_name
    (parties in other sources with the same name_key). same_name and same_address are
    name- or address-only: leads to check, not established identity."""
    source_id, _, party_id = ref.partition(":")
    nodes: dict[str, dict[str, Any]] = {}
    edges: set[tuple[str, str, str]] = set()
    frontier = {(source_id, party_id)}
    seen: set[tuple[str, str]] = set()
    for _hop in range(hops):
        frontier -= seen
        if not frontier or len(nodes) >= max_nodes:
            break
        seen |= frontier
        pids = {p for _s, p in frontier}
        me = [r for r in _rows(con, f"""
            SELECT source_id, party_id, raw_name, party_kind, name_key, address_id
            FROM names WHERE party_id IN {_in(pids)}""", [])  # noqa: S608
            if (r["source_id"], r["party_id"]) in frontier]  # fmt: skip
        nxt: set[tuple[str, str]] = set()
        for r in me:
            nodes[f"party:{r['source_id']}:{r['party_id']}"] = {
                "kind": "party",
                "label": r["raw_name"],
                "party_kind": r["party_kind"],
            }
        pnode = {(r["source_id"], r["party_id"]): f"party:{r['source_id']}:{r['party_id']}"
                 for r in me}  # fmt: skip
        # parcels, and their other owners
        own = [r for r in _rows(con, "SELECT source_id, party_id, parcel_uid FROM owners "  # noqa: S608
                                f"WHERE party_id IN {_in(pids)}", [])
               if (r["source_id"], r["party_id"]) in pnode]  # fmt: skip
        for r in own:
            n = f"parcel:{r['parcel_uid']}"
            nodes.setdefault(n, {"kind": "parcel", "label": r["parcel_uid"]})
            edges.add((pnode[(r["source_id"], r["party_id"])], n, "owns"))
        uids = {r["parcel_uid"] for r in own}
        for r in _rows(con, "SELECT source_id, party_id, parcel_uid FROM owners "  # noqa: S608
                            f"WHERE parcel_uid IN {_in(uids)}", []) if uids else []:  # fmt: skip
            nxt.add((r["source_id"], r["party_id"]))
            edges.add((f"party:{r['source_id']}:{r['party_id']}", f"parcel:{r['parcel_uid']}",
                       "owns"))  # fmt: skip
        # documents and cases, and their other parties
        for table, key, kind, label in (
            ("instrument_parties", "instrument_uid", "party_to", "doc"),
            ("case_parties", "case_uid", "in_case", "case"),
            ("business_roles", "sos_id", "role", "business"),
        ):
            mine = [r for r in _rows(con, f"SELECT source_id, party_id, {key} AS k, role "  # noqa: S608
                                          f"FROM {table} WHERE party_id IN {_in(pids)}", [])
                    if (r["source_id"], r["party_id"]) in pnode]  # fmt: skip
            for r in mine:
                n = f"{label}:{r['source_id']}:{r['k']}"
                nodes.setdefault(n, {"kind": label, "label": r["k"]})
                edges.add((pnode[(r["source_id"], r["party_id"])], n, f"{kind}:{r['role']}"))
            ks = {r["k"] for r in mine}
            for r in _rows(con, f"SELECT source_id, party_id, {key} AS k, role FROM {table} "  # noqa: S608
                                f"WHERE {key} IN {_in(ks)}", []) if ks else []:  # fmt: skip
                nxt.add((r["source_id"], r["party_id"]))
                edges.add((f"party:{r['source_id']}:{r['party_id']}",
                           f"{label}:{r['source_id']}:{r['k']}",
                           f"{kind}:{r['role']}"))  # fmt: skip
        # same name elsewhere, same address
        keys = {r["name_key"] for r in me if r["name_key"] and " " in r["name_key"]}
        addrs = {r["address_id"] for r in me if r["address_id"]}
        # Every value in the SQL text is quoted by _in().
        near = f"""
            SELECT source_id, party_id, name_key, address_id FROM names
            WHERE name_key IN {_in(keys)} OR address_id IN {_in(addrs)}"""  # noqa: S608
        for r in _rows(con, near, []):
            other = (r["source_id"], r["party_id"])
            for m in me:
                if other == (m["source_id"], m["party_id"]):
                    continue
                a, b = pnode[(m["source_id"], m["party_id"])], f"party:{other[0]}:{other[1]}"
                if r["name_key"] == m["name_key"] and r["source_id"] != m["source_id"]:
                    edges.add((a, b, "same_name"))
                    nxt.add(other)
                if r["address_id"] and r["address_id"] == m["address_id"]:
                    edges.add((a, b, "same_address"))
                    nxt.add(other)
        frontier = nxt
    # label the last ring of parties
    tail = {n.split(":", 2)[2] for a, b, _k in edges for n in (a, b)
            if n.startswith("party:") and n not in nodes}  # fmt: skip
    for r in _rows(con, "SELECT source_id, party_id, raw_name, party_kind FROM names "  # noqa: S608
                        f"WHERE party_id IN {_in(tail)}", []) if tail else []:  # fmt: skip
        nodes.setdefault(f"party:{r['source_id']}:{r['party_id']}",
                         {"kind": "party", "label": r["raw_name"],
                          "party_kind": r["party_kind"]})  # fmt: skip
    ids = sorted(nodes)[:max_nodes]
    keep = set(ids)
    return {"nodes": [{"id": i, **nodes[i]} for i in ids],
            "edges": [{"from": a, "to": b, "kind": k} for a, b, k in sorted(edges)
                      if a in keep and b in keep]}  # fmt: skip


def address_search(
    con: duckdb.DuckDBPyConnection,
    street: str,
    zip5: str | None = None,
    city: str | None = None,
    limit: int = 50,
) -> dict[str, list[dict[str, Any]]]:
    """Parcels whose situs is this street address, and parties whose address it is."""
    row = con.execute("SELECT street_norm(?)", [street]).fetchone()
    skey = str(row[0]) if row and row[0] else ""
    if not skey:
        return {"parcels": [], "parties": []}
    # Exact street, or an address kept as one unsplit line ("4388 WELLS ST BATON ROUGE LA
    # 70808": no city or ZIP fields) that starts with the street and holds the ZIP.
    cond = ("(a.street_key = ? OR (a.zip5 IS NULL AND a.city IS NULL"
            " AND starts_with(a.street_key, ? || ' ')"
            + (" AND contains(a.street_key, ?)" if zip5 else "") + "))")  # fmt: skip
    params: list[Any] = [skey, skey] + ([zip5] if zip5 else [])
    if zip5:
        cond += " AND (a.zip5 = ? OR a.zip5 IS NULL)"
        params.append(zip5)
    if city:
        cond += " AND (a.city IS NULL OR street_norm(a.city) = street_norm(?))"
        params.append(city)
    parcels = _rows(con, f"""
        SELECT p.source_id, p.parcel_uid, a.line1, a.city, a.zip5, v.tax_year,
               v.appraised_total, v.assessed_value,
               (SELECT list(DISTINCT n.raw_name) FROM owners o JOIN names n
                  ON n.source_id = o.source_id AND n.party_id = o.party_id
                WHERE o.source_id = p.source_id AND o.parcel_uid = p.parcel_uid) AS owners
        FROM addresses a JOIN parcels p ON p.situs_address_id = a.address_id
        LEFT JOIN parcel_values v ON v.source_id = p.source_id AND v.parcel_uid = p.parcel_uid
        WHERE {cond} ORDER BY p.source_id, p.parcel_uid LIMIT ?
    """, [*params, limit])  # noqa: S608  # fmt: skip
    parties = _rows(con, f"""
        SELECT n.source_id || ':' || n.party_id AS ref, n.raw_name, n.party_kind,
               a.line1, a.city, a.zip5
        FROM addresses a JOIN names n ON n.address_id = a.address_id
        WHERE {cond} ORDER BY n.raw_name, ref LIMIT ?
    """, [*params, limit])  # noqa: S608  # fmt: skip
    return {"parcels": parcels, "parties": parties}


def _money(x: float | None) -> str:
    return "" if x is None else f"${x:,.0f}"


def _print_hits(hits: list[Hit]) -> None:
    for h in hits:
        bits = [f"{h.parcels} parcels {_money(h.parcel_value)}".strip() if h.parcels else "",
                f"{h.debts} debts {_money(h.debt_amount)}".strip() if h.debts else "",
                f"{h.cases} cases" if h.cases else "",
                f"{h.businesses} business roles" if h.businesses else "",
                f"{h.officers} officers" if h.officers else ""]  # fmt: skip
        links = "; ".join(b for b in bits if b) or "no links"
        print(f"{h.score:.2f} {h.rule:9} {h.raw_name}  [{h.state}] {h.address or ''}")
        print(f"     {links}  -> --show {h.ref}")


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(prog="equity.search")
    ap.add_argument("name", nargs="?")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--state")
    ap.add_argument("--kind", choices=("person", "org", "unknown", "business"))
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--address")
    ap.add_argument("--zip")
    ap.add_argument("--city")
    ap.add_argument("--show", help="source_id:party_id from a search hit")
    ap.add_argument("--network", help="source_id:party_id: walk its links outward")
    ap.add_argument("--hops", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    con = connect(args.db, read_only=True)
    out: Any
    if args.network:
        out = network(con, args.network, args.hops)
    elif args.show and ":business:" in args.show:
        out = show_business(con, args.show)
        if out is None:
            print(f"no business {args.show}", file=sys.stderr)
            return 1
    elif args.show:
        out = show(con, args.show)
        if out is None:
            print(f"no party {args.show}", file=sys.stderr)
            return 1
        out = asdict(out)
    elif args.address:
        out = address_search(con, args.address, args.zip, args.city, args.limit)
    elif args.name:
        hits = search(con, args.name, args.state, args.kind, args.limit)
        if not args.json:
            _print_hits(hits)
            return 0
        out = [asdict(h) | {"ref": h.ref} for h in hits]
    else:
        ap.error("give a name, --address or --show")
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
