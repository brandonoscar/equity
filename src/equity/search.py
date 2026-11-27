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
--network walks a party's links outward (parcels, co-owners, documents and the parcels they
are recorded against, cases, businesses, same address, same name elsewhere) as nodes and
edges. --parcel shows a parcel's owners, value and recorded documents.

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
from datetime import date
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
# network(): parties in these roles are shown but not walked through (a creditor such as a
# county treasurer is on thousands of documents), nor names shared by more records than this.
HUB_ROLES = frozenset({"creditor", "lender", "plaintiff", "trustee", "assignee"})
MAX_SAME_NAME = 25
MAX_CANDIDATES = 20000  # name_keys per candidate branch that are scored
MAX_KEYS = 500  # best-scored name_keys whose parties are fetched
STRICT_ENOUGH = 50  # strict candidates that make the capped fallback unnecessary
ALIKE = 0.85  # Jaro-Winkler floor for a same-Soundex word to count as a form of a query word


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
    name_key: str = ""
    name_flag: str | None = None  # why this name cannot be a lead (search_index NAME_FLAGS)
    matcher: str | None = None  # the matcher's strongest link for this party: decision rule
    person_id: str | None = None  # the matcher's merged person (people.parquet)
    bankruptcy: bool = False  # the matcher flagged a bankruptcy case for this party

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
    name_flag: str | None = None
    matcher: dict[str, Any] = field(default_factory=dict)


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
      WHEN list_contains($alts::VARCHAR[], name_key) THEN 'nickname'
      WHEN list_has_all(w, $words::VARCHAR[]) AND len(w) - $n BETWEEN 1 AND 2 THEN 'all_words'
      -- every query word but one is in the name; that one is an initial of a name word (or
      -- the name has its initial); word counts within 1; no full name word unexplained
      WHEN len(list_filter($words::VARCHAR[], lambda q: list_contains(w, q))) = $n - 1
           AND len(list_filter($words::VARCHAR[], lambda q: NOT list_contains(w, q)
             AND ((length(q) = 1 AND len(list_filter(w, lambda x: x[1] = q)) > 0)
               OR len(list_filter(w, lambda x: length(x) = 1 AND q[1] = x
                                          AND NOT list_contains($words::VARCHAR[], x))) > 0))) = 1
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
SELECT name_key, rule, sim,
       CASE rule WHEN 'exact' THEN 1.0
                 WHEN 'all_words' THEN 1.0 - 0.05 * (len(w) - $n)
                 WHEN 'nickname' THEN 0.9
                 WHEN 'initial' THEN 0.85
                 WHEN 'sounds_like' THEN 0.82 - 0.03 * greatest(len(w) - $n, 0)
                 ELSE round(0.8 * sim, 4) END AS score
FROM ruled WHERE rule IS NOT NULL
ORDER BY score DESC, sim DESC, name_key
LIMIT {MAX_KEYS}
"""  # noqa: S608


def nickname_keys(con: duckdb.DuckDBPyConnection, key: str, limit: int = 24) -> list[str]:
    """The query's name_key with one word swapped for an equivalent given name (BOB <->
    ROBERT, BILL <-> WILLIAM; equity/data/nicknames.csv), at most `limit` keys."""
    words = key.split(" ")
    alts = con.execute(
        f"SELECT word, alt FROM nicknames WHERE word IN {_in(words)} ORDER BY word, alt"  # noqa: S608
    ).fetchall()
    out: list[str] = []
    for w, alt in alts:
        swapped = sorted({*(x for x in words if x != w), str(alt)})
        k = " ".join(swapped)
        if k != key and k not in out:
            out.append(k)
    return out[:limit]


def word_forms(con: duckdb.DuckDBPyConnection, words: list[str]) -> dict[str, set[str]]:
    """Each query word's accepted forms: itself, its equivalent given names, and indexed words
    with the same Soundex code and Jaro-Winkler similarity >= 0.85 (3+ letters)."""
    forms: dict[str, set[str]] = {w: {w} for w in words}
    for w, alt in con.execute(
        f"SELECT word, alt FROM nicknames WHERE word IN {_in(words)}"  # noqa: S608
    ).fetchall():
        forms[str(w)].add(str(alt))
    long_words = [w for w in words if len(w) >= 3 and w.isalpha()]
    if long_words:
        for w, alike in con.execute(f"""
            SELECT q.w, s.word FROM (SELECT unnest(?::VARCHAR[]) AS w) q
            JOIN word_sounds s ON s.sound = soundex(q.w)
            WHERE s.sound IN {_in(_sounds(con, long_words))}
              AND jaro_winkler_similarity(q.w, s.word) >= {ALIKE}
        """, [long_words]).fetchall():  # noqa: S608  # fmt: skip
            forms[str(w)].add(str(alike))
    return forms


def _sounds(con: duckdb.DuckDBPyConnection, words: list[str]) -> list[str]:
    rows = con.execute("SELECT DISTINCT soundex(w) FROM unnest(?::VARCHAR[]) t(w)", [words])
    return [str(r[0]) for r in rows.fetchall()]


def strict_keys(con: duckdb.DuckDBPyConnection, key: str) -> set[str]:
    """Every name_key holding all the query's full words (2+ letters) in some accepted form
    (word_forms). Not capped, so a common word cannot crowd the right name out."""
    words = [w for w in key.split(" ") if len(w) >= 2]
    if len(words) < 2:
        return set()
    forms = word_forms(con, words)
    pairs = sorted({(f, w) for w, fs in forms.items() for f in fs})
    values = ", ".join(f"('{f}', '{w}')" for f, w in pairs if "'" not in f + w)
    rows = con.execute(f"""
        SELECT nw.name_key FROM name_words nw
        JOIN (VALUES {values}) f(form, q) ON f.form = nw.word
        WHERE nw.word IN {_in(f for f, _ in pairs)}
        GROUP BY nw.name_key HAVING count(DISTINCT f.q) = {len(words)}
    """).fetchall()  # noqa: S608  # fmt: skip
    return {str(r[0]) for r in rows}


def candidate_keys(con: duckdb.DuckDBPyConnection, key: str) -> list[str]:
    """name_keys worth scoring: the exact key and its nickname variants, every name holding all
    the query's words in some form (strict_keys), and, only when that finds few, names holding
    one of the query's two rarest words or a word that sounds like one of its two longest words
    (capped: a typo that changes a word's sound)."""
    strict = strict_keys(con, key)
    if len(strict) >= STRICT_ENOUGH:
        return sorted({key} | strict | set(nickname_keys(con, key)))
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
    return sorted(out | strict | set(nickname_keys(con, key)))


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
                                     "key": key, "n": len(words),
                                     "alts": nickname_keys(con, key)}).fetchall()  # fmt: skip
    rule = {str(k): (str(r), float(sc)) for k, r, _sim, sc in ranked}
    closeness = {str(k): float(sim or 0) for k, _r, sim, _sc in ranked}
    if not rule:
        return []
    cond = ""
    params: list[Any] = []
    if state:
        cond += " AND s.state = ?"
        params.append(state.upper())
    parties = [] if kind == "business" else _rows(con, f"""
        SELECT n.source_id, n.party_id, n.raw_name, n.party_kind, n.address_id, n.name_key,
               s.state, n.name_flag
        FROM names n JOIN sources s USING (source_id)
        WHERE n.name_key IN {_in(rule)} {cond} {"AND n.party_kind = ?" if kind else ""}
    """, params + ([kind] if kind else []))  # noqa: S608  # fmt: skip
    firms = [] if kind not in (None, "org", "business") else _rows(con, f"""
        SELECT b.source_id, 'business:' || b.sos_id AS party_id, b.name AS raw_name,
               'business' AS party_kind, NULL AS address_id, b.name_key, s.state,
               name_flag(b.name) AS name_flag
        FROM businesses b JOIN sources s USING (source_id)
        WHERE b.name_key IN {_in(rule)} {cond}
    """, params)  # noqa: S608  # fmt: skip
    rows = sorted(
        parties + firms,
        key=lambda r: (
            -rule[r["name_key"]][1],
            r["name_flag"] is not None,  # flagged names after clean ones
            -closeness[r["name_key"]],
            r["raw_name"],
            r["source_id"],
            r["party_id"],
        ),
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
            name_key=r["name_key"],
            name_flag=r["name_flag"],
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
    _annotate_matcher(con, hits)


RANK = {"auto": 0, "review": 1}


def _annotate_matcher(con: duckdb.DuckDBPyConnection, hits: list[Hit]) -> None:
    """The matcher's verdict on each hit (m_* tables, empty when no state's output is loaded):
    its strongest link as debtor or owner, its merged person, and any bankruptcy flag."""
    ids = {h.party_id for h in hits}
    links: dict[str, tuple[str, str]] = {}
    for d, o, rule, decision in con.execute(
        "SELECT debtor_party_id, owner_party_id, rule_id, decision FROM m_matches "  # noqa: S608
        f"WHERE debtor_party_id IN {_in(ids)} OR owner_party_id IN {_in(ids)}"
    ).fetchall():
        for pid in (d, o):
            if pid in ids:
                best = links.get(pid)
                if best is None or RANK.get(decision, 9) < RANK.get(best[0], 9):
                    links[pid] = (str(decision), str(rule))
    person = dict(con.execute(
        f"SELECT party_id, person_id FROM m_person_of WHERE party_id IN {_in(ids)}"  # noqa: S608
    ).fetchall())  # fmt: skip
    bk = {str(r[0]) for r in con.execute(
        "SELECT debtor_party_id FROM m_bankruptcy_flags "  # noqa: S608
        f"WHERE debtor_party_id IN {_in(ids)}").fetchall()}  # fmt: skip
    for h in hits:
        if h.party_id in links:
            h.matcher = " ".join(links[h.party_id])
        h.person_id = person.get(h.party_id)
        h.bankruptcy = h.party_id in bk


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
               i.consideration, ip.role,
               (SELECT list(DISTINCT x.parcel_uid ORDER BY x.parcel_uid) FROM instrument_parcels x
                 WHERE x.source_id = i.source_id AND x.instrument_uid = i.instrument_uid)
                 AS parcels
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
    e.name_flag = n.get("name_flag")
    eq = _equity_rows(con, {p["parcel_uid"] for p in e.parcels})
    for p in e.parcels:
        p["equity"] = eq.get(p["parcel_uid"])
    e.matcher = matcher_view(con, party_id)
    return e


def _equity_rows(con: duckdb.DuckDBPyConnection, uids: set[str]) -> dict[str, dict[str, Any]]:
    """Net-equity rows for parcels (parcel_equity, stored by compact; else the view)."""
    if not uids:
        return {}
    have = {str(r[0]) for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    table = "parcel_equity" if "parcel_equity" in have else "v_parcel_equity"
    return {r["parcel_uid"]: r for r in _rows(
        con, f"SELECT * FROM {table} WHERE parcel_uid IN {_in(uids)}", [])}  # noqa: S608  # fmt: skip


def matcher_view(con: duckdb.DuckDBPyConnection, party_id: str) -> dict[str, Any]:
    """What the deterministic matcher concluded about one party: its links as debtor and as
    owner (rule and decision), the debtor summary (open amount, parcels, equity when the
    state's recorder data allows), the merged person, and bankruptcy and transfer flags."""
    out: dict[str, Any] = {}
    out["as_debtor"] = _rows(con, "SELECT state, instrument_uid, owner_party_id, parcel_uid, "
                                  "rule_id, decision FROM m_matches WHERE debtor_party_id = ? "
                                  "ORDER BY decision, rule_id, parcel_uid", [party_id])  # fmt: skip
    out["as_owner"] = _rows(con, "SELECT state, debtor_party_id, instrument_uid, parcel_uid, "
                                 "rule_id, decision FROM m_matches WHERE owner_party_id = ? "
                                 "ORDER BY decision, rule_id, parcel_uid", [party_id])  # fmt: skip
    out["summary"] = _rows(con, "SELECT * FROM m_debtor_summary WHERE debtor_party_id = ?",
                           [party_id])  # fmt: skip
    pid = con.execute("SELECT person_id FROM m_person_of WHERE party_id = ? LIMIT 1",
                      [party_id]).fetchone()  # fmt: skip
    out["person"] = (
        _rows(con, "SELECT * FROM m_people WHERE person_id = ?", [pid[0]]) if pid else []
    )
    out["bankruptcy"] = _rows(con, "SELECT * FROM m_bankruptcy_flags WHERE debtor_party_id = ?",
                              [party_id])  # fmt: skip
    cols = {str(r[0]) for r in con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'm_transfer_flags'"
    ).fetchall()}  # fmt: skip
    key = next((c for c in ("debtor_party_id", "party_id") if c in cols), None)
    out["transfers"] = _rows(con, f"SELECT * FROM m_transfer_flags WHERE {key} = ?",  # noqa: S608
                             [party_id]) if key else []  # fmt: skip
    return {k: v for k, v in out.items() if v}


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
    # Every other name filed under this id, in any registry source (former and assumed names
    # from ny.sos.name_history; the active name from ny.sos.business).
    aka = _rows(con, """
        SELECT source_id, name, status, formed_on FROM businesses
        WHERE sos_id = ? AND NOT (source_id = ? AND name = ?)
          AND split_part(source_id, '.', 1) = split_part(?, '.', 1)
        ORDER BY formed_on NULLS LAST, name
    """, [sos_id, source_id, head[0]["name"], source_id])  # fmt: skip
    return {"ref": ref, **head[0], "aka": aka, "people": people}


def show_parcel(
    con: duckdb.DuckDBPyConnection, parcel: str, as_of: date | None = None
) -> list[dict[str, Any]]:
    """A parcel by parcel_uid ("39049-010-1") or the id as the county prints it: each source's
    record with situs and latest value, its owners, the documents recorded against it with
    their parties and whether a recorded release points at them, the value history, and net
    equity where recorder data exists. With as_of, also who owned it on that date: the
    owner snapshots in force then, and the grantees of the last deed recorded by then."""
    found = _rows(con, """
        SELECT p.source_id, p.parcel_uid, p.parid_raw, p.land_use_desc, p.zoning,
               a.line1 AS situs_line1, a.city AS situs_city, a.zip5 AS situs_zip,
               v.tax_year, v.appraised_total, v.assessed_value, v.homestead
        FROM parcels p
        LEFT JOIN addresses a ON a.address_id = p.situs_address_id
        LEFT JOIN parcel_values v USING (source_id, parcel_uid)
        WHERE p.parcel_uid = ? OR p.parid_raw = ?
        ORDER BY p.parcel_uid, p.source_id
    """, [parcel, parcel])  # fmt: skip
    uids = {r["parcel_uid"] for r in found}
    owners = _rows(con, f"""
        SELECT o.parcel_uid, o.source_id, o.source_id || ':' || o.party_id AS ref, n.raw_name,
               o.observed_on
        FROM owners o JOIN names n USING (source_id, party_id)
        WHERE o.parcel_uid IN {_in(uids)} ORDER BY n.raw_name
    """, []) if uids else []  # noqa: S608  # fmt: skip
    docs = _rows(con, f"""
        SELECT x.parcel_uid, i.source_id, i.instrument_uid, i.doc_type, i.doc_type_raw,
               i.recorded_on, i.amount, i.consideration,
               EXISTS (SELECT 1 FROM instrument_refs r WHERE r.source_id = i.source_id
                       AND r.to_uid = i.instrument_uid
                       AND r.ref_type IN ('releases', 'satisfies_judgment')) AS released,
               (SELECT list(n.raw_name || ' (' || ip.role || ')' ORDER BY ip.role, n.raw_name)
                  FROM instrument_parties ip JOIN names n USING (source_id, party_id)
                 WHERE ip.source_id = i.source_id AND ip.instrument_uid = i.instrument_uid)
                 AS parties
        FROM instrument_parcels x JOIN instruments i USING (source_id, instrument_uid)
        WHERE x.parcel_uid IN {_in(uids)}
        ORDER BY i.recorded_on DESC NULLS LAST, i.instrument_uid
    """, []) if uids else []  # noqa: S608  # fmt: skip
    values = _rows(con, f"""
        SELECT parcel_uid, source_id, tax_year, appraised_total, assessed_value, valid_from
        FROM value_history WHERE parcel_uid IN {_in(uids)} ORDER BY tax_year DESC, source_id
    """, []) if uids else []  # noqa: S608  # fmt: skip
    equity = _equity_rows(con, uids)
    past = owners_as_of(con, uids, as_of) if as_of and uids else {}
    for r in found:
        uid = r["parcel_uid"]
        r["owners"] = [o for o in owners if o["parcel_uid"] == uid]
        r["documents"] = [d for d in docs if d["parcel_uid"] == uid]
        r["value_history"] = [v for v in values if v["parcel_uid"] == uid
                              and v["source_id"] == r["source_id"]]  # fmt: skip
        r["equity"] = equity.get(uid)
        if as_of:
            r["as_of"] = {"date": as_of.isoformat(), **past.get(uid, {})}
    return found


def owners_as_of(
    con: duckdb.DuckDBPyConnection, uids: set[str], when: date
) -> dict[str, dict[str, Any]]:
    """Per parcel, who the data says owned it on `when`: snapshot owners observed on or before
    that date and not superseded by then (owners + owner_history), and the grantees of the
    last DEED recorded on or before it. A snapshot first observed after `when` says nothing
    about that date; when neither applies the answer is empty, not a guess."""
    snaps = _rows(con, f"""
        SELECT o.parcel_uid, o.source_id || ':' || o.party_id AS ref, n.raw_name,
               o.observed_on, NULL::TIMESTAMPTZ AS superseded_at
        FROM owners o JOIN names n USING (source_id, party_id)
        WHERE o.parcel_uid IN {_in(uids)} AND o.observed_on <= ?
        UNION ALL
        SELECT h.parcel_uid, h.source_id || ':' || h.party_id, n.raw_name, h.observed_on,
               h.superseded_at
        FROM owner_history h JOIN names n USING (source_id, party_id)
        WHERE h.parcel_uid IN {_in(uids)} AND h.observed_on <= ? AND h.superseded_at::DATE > ?
        ORDER BY 1, 4 DESC, 3
    """, [when, when, when])  # noqa: S608  # fmt: skip
    deeds = _rows(con, f"""
        SELECT x.parcel_uid, i.instrument_uid, i.recorded_on, i.consideration,
               (SELECT list(n.raw_name ORDER BY n.raw_name) FROM instrument_parties ip
                  JOIN names n USING (source_id, party_id)
                 WHERE ip.source_id = i.source_id AND ip.instrument_uid = i.instrument_uid
                   AND ip.role = 'grantee') AS grantees
        FROM instrument_parcels x JOIN instruments i USING (source_id, instrument_uid)
        WHERE x.parcel_uid IN {_in(uids)} AND i.doc_type = 'DEED' AND i.recorded_on <= ?
        QUALIFY row_number() OVER (PARTITION BY x.parcel_uid
                                   ORDER BY i.recorded_on DESC, i.instrument_uid) = 1
    """, [when])  # noqa: S608  # fmt: skip
    out: dict[str, dict[str, Any]] = {}
    for r in snaps:
        out.setdefault(r.pop("parcel_uid"), {}).setdefault("snapshot_owners", []).append(r)
    for r in deeds:
        out.setdefault(r.pop("parcel_uid"), {})["last_deed"] = r
    return out


def network(
    con: duckdb.DuckDBPyConnection, ref: str, hops: int = 2, max_nodes: int = 200
) -> dict[str, list[dict[str, Any]]]:
    """Walk the catalog's links outward from one party, breadth first, up to `hops` steps.

    Edges: owns (party-parcel), party_to (party-document), in_case (party-case),
    role (party-business), recorded_against (document-parcel), same_address (parties with
    one address_id) and same_name (parties in other sources with the same name_key).
    same_name and same_address are name- or address-only: leads to check, not established
    identity. Creditors, lenders, plaintiffs, trustees and assignees are shown but not walked
    through, and names held by more than MAX_SAME_NAME records are not followed."""
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
                if r["role"] not in HUB_ROLES:  # a county treasurer is on every lien
                    nxt.add((r["source_id"], r["party_id"]))
                edges.add((f"party:{r['source_id']}:{r['party_id']}",
                           f"{label}:{r['source_id']}:{r['k']}",
                           f"{kind}:{r['role']}"))  # fmt: skip
        # documents recorded against a parcel
        docs = {n.split(":", 2)[2] for n in nodes if n.startswith("doc:")}
        q = "SELECT source_id, instrument_uid, parcel_uid FROM instrument_parcels "
        for r in _rows(con, q + f"WHERE instrument_uid IN {_in(docs)}", []) if docs else []:
            n = f"parcel:{r['parcel_uid']}"
            nodes.setdefault(n, {"kind": "parcel", "label": r["parcel_uid"]})
            edges.add((f"doc:{r['source_id']}:{r['instrument_uid']}", n, "recorded_against"))
        # same name elsewhere, same address
        keys = {r["name_key"] for r in me if r["name_key"] and " " in r["name_key"]}
        if keys:  # a name shared by many records (JOHN SMITH) is no lead
            common = con.execute(
                f"SELECT name_key FROM names WHERE name_key IN {_in(keys)} "  # noqa: S608
                f"GROUP BY name_key HAVING count(*) > {MAX_SAME_NAME}").fetchall()  # fmt: skip
            keys -= {str(c[0]) for c in common}
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


def grade_pair(con: duckdb.DuckDBPyConnection, debtor_ref: str, owner_ref: str) -> dict[str, Any]:
    """The identity grade for one debtor record and one owner record, by the matcher's rules
    in order (equity.matching.resolve; CLAUDE.md), with the evidence behind it:

      A lien_names_parcel  a debt document of the debtor is recorded against a parcel the
                           owner record owns
      A matcher_auto       the matcher linked the two automatically
      A name_address       same name_key and the debtor's address is the owner's mailing
                           address or the owned parcel's property address
      B matcher_review     the matcher linked them for review
      B name_zip           same name_key and ZIP
      C name_only          same name_key only
      reject               different names, or either name is flagged (name_flag)"""
    d_src, _, d_pid = debtor_ref.partition(":")
    o_src, _, o_pid = owner_ref.partition(":")
    rows = {(r["source_id"], r["party_id"]): r for r in _rows(con, f"""
        SELECT n.source_id, n.party_id, n.name_key, n.name_flag, n.address_id, a.zip5
        FROM names n LEFT JOIN addresses a USING (address_id)
        WHERE n.party_id IN {_in({d_pid, o_pid})}""", [])}  # noqa: S608  # fmt: skip
    d, o = rows.get((d_src, d_pid)), rows.get((o_src, o_pid))
    if d is None or o is None:
        return {"grade": "reject", "rule": "not_found", "evidence": []}
    owned = {str(r[0]) for r in con.execute(
        "SELECT parcel_uid FROM owners WHERE source_id = ? AND party_id = ?", [o_src, o_pid]
    ).fetchall()}  # fmt: skip
    liened = {str(r[0]): str(r[1]) for r in con.execute(f"""
        SELECT x.parcel_uid, x.instrument_uid FROM instrument_parties ip
        JOIN instrument_parcels x USING (source_id, instrument_uid)
        WHERE ip.source_id = ? AND ip.party_id = ? AND x.parcel_uid IN {_in(owned)}
    """, [d_src, d_pid]).fetchall()} if owned else {}  # noqa: S608  # fmt: skip
    if liened:
        uid = sorted(liened)[0]
        return {"grade": "A", "rule": "lien_names_parcel",
                "evidence": [f"{d_src}:{liened[uid]} is recorded against {uid}, owned by "
                             f"{owner_ref}"]}  # fmt: skip
    links = con.execute(
        "SELECT decision, rule_id FROM m_matches WHERE debtor_party_id = ? AND owner_party_id = ?",
        [d_pid, o_pid]).fetchall()  # fmt: skip
    if any(dec == "auto" for dec, _r in links):
        rule = next(r for dec, r in links if dec == "auto")
        return {"grade": "A", "rule": "matcher_auto", "evidence": [f"matcher rule {rule}"]}
    for r in (d, o):
        if r["name_flag"]:
            return {"grade": "reject", "rule": f"flag_{r['name_flag']}", "evidence": []}
    if d["name_key"] != o["name_key"]:
        if links:
            return {"grade": "B", "rule": "matcher_review", "evidence": [f"matcher {links[0][1]}"]}
        return {"grade": "reject", "rule": "different_names", "evidence": []}
    situs = {str(r[0]) for r in con.execute(f"""
        SELECT situs_address_id FROM parcels WHERE source_id = ? AND parcel_uid IN {_in(owned)}
          AND situs_address_id IS NOT NULL""", [o_src]).fetchall()} if owned else set()  # noqa: S608  # fmt: skip
    if d["address_id"] and (d["address_id"] == o["address_id"] or d["address_id"] in situs):
        where = "mailing" if d["address_id"] == o["address_id"] else "property"
        return {"grade": "A", "rule": "name_address",
                "evidence": [f"same name_key and the debtor's address is the owner's {where} "
                             f"address ({d['address_id']})"]}  # fmt: skip
    if links:
        return {"grade": "B", "rule": "matcher_review", "evidence": [f"matcher {links[0][1]}"]}
    if d["zip5"] and d["zip5"] == o["zip5"]:
        return {
            "grade": "B",
            "rule": "name_zip",
            "evidence": [f"same name_key and ZIP {d['zip5']}"],
        }
    return {"grade": "C", "rule": "name_only", "evidence": [f"same name_key {d['name_key']!r}"]}


def benchmark(
    con: duckdb.DuckDBPyConnection, n: int = 50, seed: int = 7, top: int = 10
) -> dict[str, Any]:
    """Recall and latency on real names. Samples n indexed person-or-unknown names of 2+
    words with letters (repeatably), searches each as written and with one typo (a letter
    dropped from its longest word), and reports how often the sampled name comes back in the
    top results (name_recall) and how often the sampled record itself does (record_recall:
    lower when many records share one name)."""
    import time

    sample = _rows(con, f"""
        SELECT * FROM (
            SELECT source_id, party_id, raw_name, name_key FROM names
            WHERE party_kind <> 'org' AND len(string_split(name_key, ' ')) >= 2
              AND regexp_matches(name_key, '[A-Z]{{3}}') AND length(name_key) >= 8)
        USING SAMPLE reservoir({int(n)} ROWS) REPEATABLE ({int(seed)})
    """, [])  # noqa: S608  # fmt: skip
    out: dict[str, Any] = {"queries": len(sample)}
    for variant in ("as_written", "one_typo"):
        names, records, times = 0, 0, []
        for r in sample:
            q = r["raw_name"]
            if variant == "one_typo":
                longest = max(r["name_key"].split(" "), key=len)
                q = r["name_key"].replace(longest, longest[:2] + longest[3:], 1)
            t0 = time.perf_counter()
            hits = search(con, q, limit=top)
            times.append(time.perf_counter() - t0)
            names += any(h.name_key == r["name_key"] for h in hits)
            records += any((h.source_id, h.party_id) == (r["source_id"], r["party_id"])
                           for h in hits)  # fmt: skip
        times.sort()
        k = len(sample) or 1
        out[variant] = {
            "name_recall": round(names / k, 3),
            "record_recall": round(records / k, 3),
            "p50_s": round(times[len(times) // 2], 3) if times else None,
            "p95_s": round(times[min(len(times) - 1, int(len(times) * 0.95))], 3)
            if times else None,
        }  # fmt: skip
    return out


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
    ap.add_argument("--grade", nargs=2, metavar=("DEBTOR_REF", "OWNER_REF"),
                    help="identity grade for a debtor record and an owner record")  # fmt: skip
    ap.add_argument("--parcel", help="parcel_uid, or the parcel id as the county prints it")
    ap.add_argument("--as-of", type=date.fromisoformat, help="with --parcel: owners on this date")
    ap.add_argument("--hops", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--bench", type=int, metavar="N", help="recall and latency on N names")
    args = ap.parse_args(argv)
    con = connect(args.db, read_only=True)
    out: Any
    if args.grade:
        out = grade_pair(con, *args.grade)
    elif args.parcel:
        out = show_parcel(con, args.parcel, args.as_of)
    elif args.bench:
        out = benchmark(con, args.bench)
    elif args.network:
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
