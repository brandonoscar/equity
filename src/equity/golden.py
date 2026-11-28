"""Golden cases from real records, for a person to verify and CI to keep.

    uv run python -m equity.golden candidates --per-rule 3        # a stratified sample
    uv run python -m equity.golden promote config/private/golden_search/<session>/cases.yaml

`candidates` samples the leads table deterministically: every identity grade rule, and the
edge cases that break matchers (generational suffixes, deeds after the debt, same-name
bankruptcies, homestead, owner-occupied, equity behind a lien, many records under one name),
a few per stratum per state. It writes a session folder under config/private/golden_search/
(git-ignored: real names) with cases.yaml for the verifier to fill in and checklist.md, what
to look at for each case.

`promote` takes the filled-in cases.yaml and, for each verified case, writes a public scenario
to tests/e2e/scenarios/golden_<id>.yaml: the same records and their structure (which records
share a name, an address, a ZIP, a parcel; amounts and dates as recorded) with every name,
street, city, ZIP, party id and parcel id replaced by a consistent pseudonym, and the
verifier's grade as the expected answer. A real case where the pipeline disagrees with the
person then fails CI until the rule is fixed. Deterministic: no model, no scoring.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import yaml

from equity.search import _in, _rows, grade_pair
from equity.search_index import DEFAULT_DB, connect

SESSIONS = Path("config") / "private" / "golden_search"
SCENARIOS = Path("tests") / "e2e" / "scenarios"

# Each stratum: (id, SQL condition on leads, why it is worth a person's look).
STRATA: tuple[tuple[str, str, str], ...] = (
    ("rule_lien_names_parcel", "grade_rule = 'lien_names_parcel'",
     "A by a debt recorded against the parcel: is the recorded parcel really the owner's?"),
    ("rule_matcher_auto", "grade_rule = 'matcher_auto'", "A by the matcher's auto link"),
    ("rule_name_address", "grade_rule = 'name_address'",
     "A by same name and address: a relative or a namesake at one address?"),
    ("rule_matcher_review", "grade_rule = 'matcher_review'", "B by the matcher's review link"),
    ("rule_name_zip", "grade_rule = 'name_zip'", "B by same name and ZIP: same person?"),
    ("rule_name_only", "grade_rule = 'name_only'", "C by name only: how often is it right?"),
    ("edge_suffix", "regexp_matches(upper(debtor_name), '\\b(JR|SR|II|III|IV)\\b')",
     "a generational suffix: father and son records"),
    ("edge_common_name", "len(owner_refs) >= 10 OR len(debtor_refs) >= 10",
     "a name held by many records"),
    ("edge_deed_after_debt", "deeds_after_debt > 0", "a deed after the debt: transfer or sale?"),
    ("edge_bankruptcy", "same_name_bankruptcies > 0 OR matcher_bankruptcy IS NOT NULL",
     "a bankruptcy under the name"),
    ("edge_homestead", "homestead_any", "homestead parcel"),
    ("edge_owner_occupied", "owner_occupied_any AND NOT homestead_any",
     "owner-occupied without a homestead flag"),
    ("edge_equity_behind_lien", "equity_behind_lien IS NOT NULL",
     "the lien's position and the equity behind it"),
    ("edge_released", "open_debts < debts", "a released or satisfied debt"),
)  # fmt: skip


def candidates(
    con: duckdb.DuckDBPyConnection,
    per_rule: int = 3,
    states: list[str] | None = None,
    seed: str = "golden-1",
) -> list[dict[str, Any]]:
    """A deterministic stratified sample of leads: per stratum and state, `per_rule` leads
    (ordered by a hash of the seed and the lead id, so the same index gives the same set)."""
    where_state = f"AND state IN {_in(s.upper() for s in states)}" if states else ""
    out: dict[int, dict[str, Any]] = {}
    for sid, cond, why in STRATA:
        rows = _rows(con, f"""
            SELECT * FROM (
                SELECT *, row_number() OVER (PARTITION BY state
                    ORDER BY hash(? || lead_id::VARCHAR)) AS k
                FROM leads WHERE ({cond}) {where_state})
            WHERE k <= ? ORDER BY state, k""", [seed, per_rule])  # noqa: S608  # fmt: skip
        for r in rows:
            case = out.setdefault(int(r["lead_id"]), {
                "case_id": f"g{int(r['lead_id'])}", "lead_id": int(r["lead_id"]),
                "state": r["state"], "debtor_name": r["debtor_name"], "strata": [],
                "ours": {"grade": r["grade"], "rule": r["grade_rule"]},
                "debtor_refs": list(r["debtor_refs"] or [])[:5],
                "owner_refs": list(r["owner_refs"] or [])[:5],
                "parcel_uids": list(r["parcel_uids"] or [])[:5],
            })  # fmt: skip
            case["strata"].append({"id": sid, "why": why})
    return sorted(out.values(), key=lambda c: (c["state"], c["lead_id"]))


def checklist(cases: list[dict[str, Any]]) -> str:
    lines = ["# Golden cases to verify", "",
             "For each case: decide from the documents (recorded deed, lien, mortgage, court "
             "file), not from our grade. Fill in `verified` in cases.yaml: same_person (yes / "
             "no / unsure), the grade it deserves (A, B, C or reject), the pair you checked, "
             "the documents you looked at, and a note. Leave `verified` empty to skip a case.",
             "", "Grades: A = proven by a recorded document or the same name and address; "
             "B = same name and ZIP or a matcher review link; C = same name only; reject = "
             "different people, a creditor, a placeholder, or JR vs SR.", ""]  # fmt: skip
    for c in cases:
        lines += [f"## {c['case_id']}: {c['debtor_name']} ({c['state']})",
                  f"- Ours: {c['ours']['grade']} {c['ours']['rule']}",
                  "- Why it is in the set: " + "; ".join(s["why"] for s in c["strata"]),
                  f"- Debtor records: {', '.join(c['debtor_refs'])}",
                  f"- Owner records: {', '.join(c['owner_refs'])}",
                  f"- Parcels: {', '.join(c['parcel_uids'])}",
                  f"- Look up: `uv run python -m equity.search --grade {c['debtor_refs'][0]} "
                  f"{c['owner_refs'][0]}`, `--parcel {c['parcel_uids'][0]}`" if c["debtor_refs"]
                  and c["owner_refs"] and c["parcel_uids"] else "- Look up: refs above",
                  ""]  # fmt: skip
    return "\n".join(lines)


def write_session(cases: list[dict[str, Any]], root: Path = SESSIONS, label: str = "") -> Path:
    """A new session folder with cases.yaml (to fill in) and checklist.md."""
    label = label or datetime.now(UTC).strftime("%Y-%m-%d")
    d = root / label
    d.mkdir(parents=True, exist_ok=True)
    blank: dict[str, Any] = {
        "same_person": None, "grade": None, "debtor_ref": None, "owner_ref": None,
        "documents": [], "verified_by": None, "note": None}  # fmt: skip
    (d / "cases.yaml").write_text(yaml.safe_dump(
        {"session": label, "cases": [{**c, "verified": dict(blank)} for c in cases]},
        sort_keys=False, allow_unicode=True, width=100))  # fmt: skip
    (d / "checklist.md").write_text(checklist(cases))
    return d


# -- promote -----------------------------------------------------------------------------------


class Pseudonyms:
    """Consistent replacements: the same real value always maps to the same fake one, and
    different values to different fakes, so the structure the rules read is kept."""

    def __init__(self, salt: str) -> None:
        self.salt = salt
        self.seen: dict[tuple[str, str], str] = {}

    def _n(self, kind: str, value: str) -> int:
        key = (kind, value)
        if key not in self.seen:
            self.seen[key] = str(len([k for k in self.seen if k[0] == kind]) + 1)
        return int(self.seen[key])

    def word(self, w: str) -> str:
        if w in ("JR", "SR", "II", "III", "IV", "LLC", "INC", "CORP", "CO", "TRUST", "OF",
                 "COUNTY", "CITY", "STATE", "TREASURER", "BANK", "THE", "AND"):  # fmt: skip
            return w
        if len(w) == 1:
            return w  # an initial stays an initial (the initial rule reads it)
        return "W" + _letters(self._n("word", w))

    def name(self, raw: str | None) -> str | None:
        if raw is None:
            return None
        words = re.sub(r"[^A-Za-z0-9 ]+", " ", raw.upper()).split()
        return " ".join(["TESTOWNER", *(self.word(w) for w in words)])

    def street(self, line: str | None) -> str | None:
        return None if line is None else f"{self._n('street', line)} ELM TEST ST"

    def zip5(self, z: str | None) -> str | None:
        return None if z is None else f"{90000 + self._n('zip', z):05d}"

    def ident(self, kind: str, v: str | None) -> str | None:
        return None if v is None else f"{kind}{self._n(kind, v)}"

    def parcel(self, uid: str | None) -> str | None:
        return None if uid is None else f"{uid[:5]}-{self._n('parcel', uid):06d}"


def _letters(n: int) -> str:
    out = ""
    while True:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
        if n == 0:
            return "ZZ" + out  # 3+ letters, so name words never read as initials


def extract_case(con: duckdb.DuckDBPyConnection, debtor_ref: str, owner_ref: str
                 ) -> dict[str, dict[str, list[dict[str, Any]]]]:  # fmt: skip
    """The records a grade for this pair reads, as lake rows per source: both parties, their
    addresses, the owner's parcels (with values and situs), and the debtor's debt documents
    with their parcel links and releases."""
    d_src, _, d_pid = debtor_ref.partition(":")
    o_src, _, o_pid = owner_ref.partition(":")
    sources: dict[str, dict[str, list[dict[str, Any]]]] = {}

    def add(sid: str, table: str, rows: list[dict[str, Any]]) -> None:
        sources.setdefault(sid, {}).setdefault(table, []).extend(rows)

    for src, pid in ((d_src, d_pid), (o_src, o_pid)):
        add(src, "party", _rows(con, """SELECT party_id, raw_name, party_kind, address_id
            FROM names WHERE source_id = ? AND party_id = ?""", [src, pid]))  # fmt: skip
    owned = _rows(con, "SELECT party_id, parcel_uid, observed_on FROM owners "
                       "WHERE source_id = ? AND party_id = ?", [o_src, o_pid])  # fmt: skip
    add(o_src, "owner_snapshot", owned)
    uids = {r["parcel_uid"] for r in owned}
    if uids:
        add(o_src, "parcel", _rows(con, f"""SELECT parcel_uid, situs_address_id FROM parcels
            WHERE source_id = ? AND parcel_uid IN {_in(uids)}""", [o_src]))  # noqa: S608  # fmt: skip
        add(o_src, "parcel_assessment", _rows(con, f"""SELECT parcel_uid, tax_year,
            appraised_total, assessed_value, homestead FROM parcel_values
            WHERE source_id = ? AND parcel_uid IN {_in(uids)}""", [o_src]))  # noqa: S608  # fmt: skip
    docs = _rows(con, """SELECT i.instrument_uid, i.doc_type, i.recorded_on,
        i.amount AS principal_amount, ip.role FROM instrument_parties ip
        JOIN instruments i USING (source_id, instrument_uid)
        WHERE ip.source_id = ? AND ip.party_id = ?""", [d_src, d_pid])  # fmt: skip
    add(d_src, "instrument", [{k: v for k, v in r.items() if k != "role"} for r in docs])
    add(d_src, "instrument_party", [{"instrument_uid": r["instrument_uid"], "party_id": d_pid,
                                     "role": r["role"]} for r in docs])  # fmt: skip
    iids = {r["instrument_uid"] for r in docs}
    if iids:
        links = f"""SELECT instrument_uid, parcel_uid FROM instrument_parcels
            WHERE source_id = ? AND instrument_uid IN {_in(iids)}"""  # noqa: S608
        add(d_src, "instrument_parcel", _rows(con, links, [d_src]))
        add(d_src, "instrument_ref", _rows(con, f"""SELECT from_uid, to_uid, ref_type
            FROM instrument_refs WHERE source_id = ? AND to_uid IN {_in(iids)}""", [d_src]))  # noqa: S608  # fmt: skip
    aids = {r["address_id"] for t in sources.values() for r in t.get("party", [])}
    aids |= {r["situs_address_id"] for t in sources.values() for r in t.get("parcel", [])}
    aids.discard(None)
    if aids:
        cols = "address_id, line1, city, state, zip5"
        sql = f"SELECT {cols} FROM addresses WHERE address_id IN {_in(aids)}"  # noqa: S608
        rows = _rows(con, sql, [])
        for src in sources:
            add(src, "address", rows)
    return sources


def pseudonymize(sources: dict[str, dict[str, list[dict[str, Any]]]], salt: str
                 ) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], Pseudonyms]:  # fmt: skip
    ps = Pseudonyms(salt)
    out: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for sid, tables in sources.items():
        fake_sid = f"{sid.split('.')[0]}.golden{ps._n('source', sid)}.records"
        for table, rows in tables.items():
            new = []
            for r in rows:
                r = dict(r)
                if "raw_name" in r:
                    r["raw_name"] = ps.name(r["raw_name"])
                if "line1" in r:
                    r["line1"], r["city"] = ps.street(r["line1"]), "TESTVILLE"
                    r["zip5"] = ps.zip5(r["zip5"])
                for k in ("party_id",):
                    if k in r:
                        r[k] = ps.ident("p", r[k])
                for k in ("address_id", "situs_address_id"):
                    if k in r:
                        r[k] = ps.ident("a", r[k])
                for k in ("instrument_uid", "from_uid", "to_uid"):
                    if k in r:
                        r[k] = ps.ident("i", r[k])
                if "parcel_uid" in r:
                    r["parcel_uid"] = ps.parcel(r["parcel_uid"])
                for k, v in list(r.items()):
                    if hasattr(v, "isoformat"):
                        r[k] = v.isoformat()
                    elif v is not None and not isinstance(v, (str, int, float, bool)):
                        r[k] = float(v)
                new.append(r)
            if table == "address":  # one copy of each address per source
                new = list({r["address_id"]: r for r in new}.values())
            out.setdefault(fake_sid, {})[table] = new
        ps.seen[("sid", sid)] = fake_sid
    return out, ps


def promote(con: duckdb.DuckDBPyConnection, cases_file: Path, out_dir: Path = SCENARIOS
            ) -> list[Path]:  # fmt: skip
    """Write one pseudonymized scenario per verified case (module doc). Returns the files."""
    data = yaml.safe_load(cases_file.read_text())
    written = []
    for c in data.get("cases", []):
        v = c.get("verified") or {}
        if not v.get("grade") or not v.get("verified_by"):
            continue
        debtor = v.get("debtor_ref") or c["debtor_refs"][0]
        owner = v.get("owner_ref") or c["owner_refs"][0]
        salt = hashlib.sha256(f"{c['case_id']}:{debtor}:{owner}".encode()).hexdigest()[:12]
        sources, ps = pseudonymize(extract_case(con, debtor, owner), salt)
        d_src, _, d_pid = debtor.partition(":")
        o_src, _, o_pid = owner.partition(":")
        fake_d = f"{ps.seen[('sid', d_src)]}:{ps.ident('p', d_pid)}"
        fake_o = f"{ps.seen[('sid', o_src)]}:{ps.ident('p', o_pid)}"
        ours = grade_pair(con, debtor, owner)
        name = f"golden_{c['case_id']}"
        same = {"yes": "same person", "no": "not the same person"}.get(
            str(v.get("same_person")), "unsure"
        )
        doc = (
            f"Real case verified by a person ({v['verified_by']}): {same}, grade "
            f"{v['grade']}. Pseudonymized; strata: "
            + ", ".join(st["id"] for st in c.get("strata", []))
        )
        if ours["grade"] != v["grade"]:
            doc += f". At promotion the pipeline said {ours['grade']} {ours['rule']}."
        scenario = {
            "name": name, "doc": doc, "sources": sources,
            "expect": [{"grade": {"debtor": fake_d, "owner": fake_o, "grade": v["grade"],
                                  "rule": v.get("rule") or ours["rule"]}}],
        }  # fmt: skip
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{name}.yaml"
        path.write_text(yaml.safe_dump(scenario, sort_keys=False, allow_unicode=True, width=100))
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates")
    c.add_argument("--per-rule", type=int, default=3)
    c.add_argument("--states", nargs="*")
    c.add_argument("--label", default="")
    p = sub.add_parser("promote")
    p.add_argument("cases", type=Path)
    args = ap.parse_args(argv)
    con = connect(args.db, read_only=True)
    if args.cmd == "candidates":
        cases = candidates(con, args.per_rule, args.states)
        print(f"{len(cases)} cases -> {write_session(cases, label=args.label)}")
    else:
        for path in promote(con, args.cases):
            print(path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
