"""Search the query catalog (equity.catalog) by name or address, with every hit explained.

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
  similar      each query word's best Jaro-Winkler similarity to a    0.80 x similarity
               name word, averaged, >= 0.90 (word counts within 1), among
               names sharing one of the query's two rarest words

Each hit carries what the catalog links to it: parcels owned (with the latest value), debts
and recorded documents it is a party to, court cases, and businesses it holds a role in.
Address search standardizes the street with the matcher's street_norm (USPS Publication 28
words) and finds parcels at that situs and parties mailed there.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from equity.catalog import DEFAULT_DB, connect

# Doc types that are debts or liens against the party (not deeds or mortgages they hold).
# (The schema's doc_type vocabulary: equity/schema/migrations/V0004__instruments.sql.)
DEBT_TYPES = (
    "JUDGMENT_LIEN", "ABSTRACT_OF_JUDGMENT", "EXECUTION", "LIS_PENDENS", "MECHANICS_LIEN",
    "STATUTORY_LIEN", "TAX_LIEN_STATE", "TAX_LIEN_FEDERAL", "COURT_ORDER",
)  # fmt: skip
SIMILAR_MIN = 0.90
MAX_CANDIDATES = 20000  # names sharing the rarest word that are scored for similarity


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
    businesses: int = 0

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


def search(
    con: duckdb.DuckDBPyConnection,
    name: str,
    state: str | None = None,
    kind: str | None = None,
    limit: int = 25,
) -> list[Hit]:
    """Name search: candidates by exact key, then by the rarest query word, scored by rule."""
    key = query_key(con, name)
    if not key:
        return []
    words = key.split(" ")
    # The query word with the fewest index entries bounds the candidate set.
    counts = _rows(con, "SELECT word, count(*) AS n FROM name_words WHERE word IN "
                        "(SELECT unnest(?::VARCHAR[])) GROUP BY word", [words])  # fmt: skip
    present = {r["word"]: r["n"] for r in counts}
    # The two rarest query words: a typo in one still finds candidates through the other.
    rare = sorted(present, key=lambda w: (present[w], -len(w), w))[:2] or [key]
    filters, params = [], []
    if state:
        filters.append("s.state = ?")
        params.append(state.upper())
    if kind:
        filters.append("n.party_kind = ?")
        params.append(kind)
    extra = "".join(f" AND {f}" for f in filters)
    sql = f"""
    WITH cand AS (
        SELECT source_id, party_id FROM names WHERE name_key = ?
        UNION
        SELECT source_id, party_id FROM (
            SELECT source_id, party_id FROM name_words WHERE word = ? LIMIT {MAX_CANDIDATES})
        UNION
        SELECT source_id, party_id FROM (
            SELECT source_id, party_id FROM name_words WHERE word = ? LIMIT {MAX_CANDIDATES})
    ), scored AS (
        SELECT n.source_id, n.party_id, n.raw_name, n.party_kind, n.address_id, s.state,
               n.name_key,
               string_split(n.name_key, ' ') AS w,
               -- each query word against its closest name word, averaged
               list_avg(list_transform(?::VARCHAR[], lambda q: list_max(list_transform(
                   string_split(n.name_key, ' '),
                   lambda x: jaro_winkler_similarity(q, x))))) AS sim
        FROM cand c JOIN names n USING (source_id, party_id)
        JOIN sources s USING (source_id)
        WHERE TRUE {extra}
    ), ruled AS (
        SELECT *,
          CASE
            WHEN name_key = ? THEN 'exact'
            WHEN list_has_all(w, ?::VARCHAR[]) AND len(w) - ? BETWEEN 1 AND 2 THEN 'all_words'
            -- every query word but one is in the name; that one is an initial of a name
            -- word (or the name has its initial), and the word counts differ by at most 1
            WHEN len(list_filter(?::VARCHAR[], lambda q: list_contains(w, q))) = ? - 1
                 AND len(list_filter(?::VARCHAR[], lambda q: NOT list_contains(w, q)
                   AND ((length(q) = 1 AND len(list_filter(w, lambda x: x[1] = q)) > 0)
                     OR len(list_filter(w, lambda x: length(x) = 1 AND q[1] = x)) > 0))) = 1
                 -- and no full name word is left unexplained (LUCAS in LUCAS JOHN S)
                 AND len(list_filter(w, lambda x: length(x) >= 2 AND NOT list_contains(
                     ?::VARCHAR[], x) AND NOT list_contains(?::VARCHAR[], x[1]))) = 0
                 AND abs(len(w) - ?) <= 1 THEN 'initial'
            WHEN sim >= {SIMILAR_MIN} AND abs(len(w) - ?) <= 1 THEN 'similar'
          END AS rule
        FROM scored
    )
    SELECT source_id, party_id, raw_name, party_kind, address_id, state, rule,
           CASE rule WHEN 'exact' THEN 1.0
                     WHEN 'all_words' THEN 1.0 - 0.05 * (len(w) - ?)
                     WHEN 'initial' THEN 0.85
                     ELSE round(0.8 * sim, 4) END AS score
    FROM ruled WHERE rule IS NOT NULL
    ORDER BY score DESC, raw_name, source_id, party_id
    LIMIT ?
    """  # noqa: S608
    n = len(words)
    rows = _rows(con, sql, [key, rare[0], rare[-1], words, *params, key, words, n, words, n,
                            words, words, words, n, n, n, limit])  # fmt: skip
    hits = [Hit(r["source_id"], r["party_id"], r["raw_name"], r["party_kind"], r["rule"],
                float(r["score"]), r["state"]) for r in rows]  # fmt: skip
    _annotate(con, hits, {(r["source_id"], r["party_id"]): r["address_id"] for r in rows})
    return hits


def _annotate(
    con: duckdb.DuckDBPyConnection, hits: list[Hit], addr: dict[tuple[str, str], str | None]
) -> None:
    if not hits:
        return
    keys = [[h.source_id, h.party_id] for h in hits]
    con.execute("CREATE OR REPLACE TEMP TABLE _hits (source_id VARCHAR, party_id VARCHAR)")
    con.executemany("INSERT INTO _hits VALUES (?, ?)", keys)
    stats = _rows(con, f"""
        SELECT h.source_id, h.party_id,
          (SELECT count(DISTINCT parcel_uid) FROM owners o
            WHERE o.source_id = h.source_id AND o.party_id = h.party_id) AS parcels,
          (SELECT sum(coalesce(v.appraised_total, v.assessed_value)) FROM owners o
            JOIN parcel_values v ON v.source_id = o.source_id AND v.parcel_uid = o.parcel_uid
            WHERE o.source_id = h.source_id AND o.party_id = h.party_id) AS parcel_value,
          (SELECT count(*) FROM instrument_parties ip JOIN instruments i
             USING (source_id, instrument_uid)
            WHERE ip.source_id = h.source_id AND ip.party_id = h.party_id
              AND i.doc_type IN {DEBT_TYPES}) AS debts,
          (SELECT sum(i.amount) FROM instrument_parties ip JOIN instruments i
             USING (source_id, instrument_uid)
            WHERE ip.source_id = h.source_id AND ip.party_id = h.party_id
              AND i.doc_type IN {DEBT_TYPES}) AS debt_amount,
          (SELECT count(*) FROM instrument_parties ip
            WHERE ip.source_id = h.source_id AND ip.party_id = h.party_id) AS documents,
          (SELECT count(*) FROM case_parties cp
            WHERE cp.source_id = h.source_id AND cp.party_id = h.party_id) AS cases,
          (SELECT count(*) FROM business_roles b
            WHERE b.source_id = h.source_id AND b.party_id = h.party_id) AS businesses
        FROM _hits h
    """, [])  # noqa: S608  # fmt: skip
    by = {(r["source_id"], r["party_id"]): r for r in stats}
    ids = [a for a in addr.values() if a]
    lines = {r["address_id"]: _addr_text(r) for r in _rows(
        con, "SELECT * FROM addresses WHERE address_id IN (SELECT unnest(?::VARCHAR[]))",
        [ids])} if ids else {}  # fmt: skip
    for h in hits:
        r = by[(h.source_id, h.party_id)]
        h.parcels, h.documents, h.cases = int(r["parcels"]), int(r["documents"]), int(r["cases"])
        h.debts, h.businesses = int(r["debts"]), int(r["businesses"])
        h.parcel_value = r["parcel_value"]
        h.debt_amount = r["debt_amount"]
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
                f"{h.businesses} business roles" if h.businesses else ""]  # fmt: skip
        links = "; ".join(b for b in bits if b) or "no links"
        print(f"{h.score:.2f} {h.rule:9} {h.raw_name}  [{h.state}] {h.address or ''}")
        print(f"     {links}  -> --show {h.ref}")


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(prog="equity.search")
    ap.add_argument("name", nargs="?")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--state")
    ap.add_argument("--kind", choices=("person", "org", "unknown"))
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--address")
    ap.add_argument("--zip")
    ap.add_argument("--city")
    ap.add_argument("--show", help="source_id:party_id from a search hit")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    con = connect(args.db, read_only=True)
    out: Any
    if args.show:
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
