# Golden cases

Two layers keep the search and matching rules honest.

## 1. Synthetic scenarios (in CI, public)

`tests/e2e/scenarios/*.yaml`: one tiny synthetic world per rule or edge (identity grades
and rejects, suffixes, flagged names, debt types, releases, equity and lien priority, every
transfer badge, entity rings, fact-sheet factors and gaps, supplements, the watchlist,
household and creditor portfolios, search ranking). `tests/e2e/test_scenarios.py` builds each
one as a lake, runs the real pipeline (build, supplements, compact, leads) and checks every
expectation with the real functions. Names are pseudonyms (`TESTOWNER ...`), streets end in
`TEST ST`, and each scenario's owner config (rules.yaml, sol.yaml) is its own, so a config
change never moves a CI answer. A test also flips an answer to prove the harness fails.

Adding one: copy the closest scenario, change the records and the `expect` list, keep `name`
equal to the file name and say in `doc` which rule it pins. Run
`uv run pytest tests/e2e -k <name>`.

## 2. Real cases verified by a person (private, then promoted)

The session with a verifier:

1. **Sample.** `uv run python -m equity.golden candidates --per-rule 3 --label <date>` picks
   a deterministic, stratified sample of the `leads` table: every grade rule and every edge
   stratum (`equity.golden.STRATA`), a few per state. It writes
   `config/private/golden_search/<date>/` (git-ignored): `cases.yaml` to fill in and
   `checklist.md`, what to check per case.
2. **Verify.** For each case, from the documents (recorded deed, lien, mortgage, court file),
   not from our grade: `same_person` (yes / no / unsure), the `grade` it deserves (A, B, C,
   reject), the pair checked, the documents, `verified_by`, a note. Skip a case by leaving
   `verified` empty. `uv run python -m equity.search --grade/--parcel/--show` and
   `uv run python -m equity.forensic --timeline` show what the index holds.
3. **Promote.** `uv run python -m equity.golden promote config/private/golden_search/<date>/cases.yaml`
   writes `tests/e2e/scenarios/golden_<case>.yaml` for each verified case: the same records
   and structure (who shares a name, an address, a ZIP, a parcel; amounts and dates as
   recorded) with every name, street, ZIP and id replaced by a consistent pseudonym, and the
   verifier's grade as the expected answer. Read each file before committing it.
4. **Fix what disagrees.** A promoted case where the pipeline's grade differs from the
   verifier's fails CI (its `doc` says what the pipeline said). Fix the rule, not the case.

What makes a good verified case: the documents settle it either way (a "no" is as valuable as
a "yes"), and it is in a stratum with few verified cases. Unsure cases stay out of CI.
