"""Hand-verified search cases: does search find the right records, and does the grade of a
debtor-owner pair match what a person established from the documents?

    uv run python -m equity.search_golden                  # cases in config/private/golden_search/
    uv run python -m equity.search_golden --dir path/to/cases --db data/search_index.duckdb

The owner writes the cases (see docs/golden-search-template.yaml); they name real people, so
they live in git-ignored config/private/golden_search/, never in this public repo. (The
pipeline's own acceptance cases are tests/golden/, owner-protected.) Each case:

  id, query, state (optional), top (default 10)
  expect:
    refs        records that must be in the top results
    not_refs    records that must not be there (a different person with the same name)
    pairs       [{debtor, owner, grade}]: the grade grade_pair must give (A, B, C, reject)
  checked_on, source   where and when the answer was established

Exit status 1 when any expectation fails, so it can gate a change to the search rules.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import yaml

from equity.search import grade_pair, search

CASES = Path("config/private/golden_search")


@dataclass
class Result:
    case_id: str
    failures: list[str] = field(default_factory=list)
    checks: int = 0

    @property
    def ok(self) -> bool:
        return not self.failures


def load_cases(directory: Path) -> list[dict[str, Any]]:
    cases = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for case in data if isinstance(data, list) else [data]:
            if not isinstance(case, dict) or "id" not in case:
                raise ValueError(f"{path.name}: each case needs an id")
            cases.append(case)
    return cases


def run_case(con: duckdb.DuckDBPyConnection, case: dict[str, Any]) -> Result:
    res = Result(str(case["id"]))
    expect = case.get("expect") or {}
    if case.get("query"):
        top = int(case.get("top", 10))
        got = [h.ref for h in search(con, str(case["query"]), case.get("state"), limit=top)]
        for ref in expect.get("refs") or []:
            res.checks += 1
            if ref not in got:
                res.failures.append(f"{ref} not in the top {top} for {case['query']!r}")
        for ref in expect.get("not_refs") or []:
            res.checks += 1
            if ref in got:
                res.failures.append(f"{ref} should not be in the top {top}")
    for pair in expect.get("pairs") or []:
        res.checks += 1
        g = grade_pair(con, str(pair["debtor"]), str(pair["owner"]))
        if g["grade"] != str(pair["grade"]):
            res.failures.append(f"{pair['debtor']} / {pair['owner']}: grade {g['grade']} "
                                f"({g['rule']}), expected {pair['grade']}")  # fmt: skip
    return res


def run(con: duckdb.DuckDBPyConnection, cases: list[dict[str, Any]]) -> list[Result]:
    return [run_case(con, c) for c in cases]


def report(results: list[Result]) -> str:
    checks = sum(r.checks for r in results)
    failed = sum(len(r.failures) for r in results)
    lines = [f"{len(results)} cases, {checks} checks, {checks - failed} passed, {failed} failed"]
    for r in results:
        lines.append(f"  {'ok  ' if r.ok else 'FAIL'} {r.case_id}")
        lines += [f"         {f}" for f in r.failures]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    from equity.search_index import DEFAULT_DB, connect

    ap = argparse.ArgumentParser(prog="equity.search_golden")
    ap.add_argument("--dir", type=Path, default=CASES)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = ap.parse_args(argv)
    cases = load_cases(args.dir)
    if not cases:
        print(f"no cases in {args.dir} (template: docs/golden-search-template.yaml)")
        return 0
    results = run(connect(args.db, read_only=True), cases)
    print(report(results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
