# equity: working notes for Claude

A deterministic land and court records graph. It answers one question with evidence: *does
this debtor own reachable real property with equity behind our lien?*

## The one rule that shapes everything

**No AI in the system.** The runtime has no LLM calls, embeddings or ML models
(`ci/check_no_ai.py` and `ci/blocklist.toml` fail the build otherwise; that includes ML
matchers like Splink, dedupe and recordlinkage). Claude is the *operator*: it runs the
deterministic tools, reads their evidence, and writes up what the evidence shows. It never
adds a model, a score it invented, or a guess to the data. When a fact is not in the data,
say so.

## How to answer questions

1. **Search, don't scan.** Use the search index (`docs/search.md`), not raw lake Parquet:
   - CLI (fast, explained hits): `uv run python -m equity.search "NAME" --state OH`,
     `--show <ref>`, `--parcel <id>`, `--network <ref>`, `--address "..." --zip 12345`
   - SQL through the `equity-search` MCP server (read-only DuckDB). Small, keyed queries
     only: filter on `name_key = name_key('...')`, `party_id`, `parcel_uid`, `state`. The
     stored table `debtor_owner_candidates` is fast; the `v_*` views recompute and can time
     out over MCP.
2. **Grade identity like the matcher does** (`src/equity/matching/resolve.py` rules):
   - **A (auto):** the debt is recorded against the parcel (`instrument_parcels`), or the
     same name with the same address (debtor address = owner mailing or property address).
   - **B (review):** same name and ZIP; same business name in the same county; same address
     with one extra middle initial.
   - **C (lead only):** same name in the same state, nothing else.
   - **Reject:** placeholder names (`39005 | <parcel id>`), surname only, conflicting
     suffixes (JR vs SR), the creditor itself (cities, treasurers, the state).
   Same name or same address in `--network` is a lead, never proof.
3. **Equity is gross until netted:** parcel value (say whether appraised or assessed, and
   the tax year), minus recorded mortgages still open, minus homestead protection. Flag
   transfers after the debt date (`src/equity/matching/transfers.py` lists the badges).
4. **Cite every fact** by ref (`source_id:party_id`, `parcel_uid`, `instrument_uid`) so it
   can be re-derived.

## Privacy

The repository is public. Never commit a real person's name, address or a dossier. Write
research output under `data/derived/` (git-ignored). Test fixtures are pseudonymized
(`TESTOWNER ...`); keep them that way.

## Workflows (in `.claude/`)

| Ask | Use |
|---|---|
| "Look up / dossier on <name or ref>" | skill `debtor-dossier` |
| "Find leads in <state> with <criteria>" | skill `lead-scan` (shortlist), then the saved workflow `verify-leads` for many leads at once |
| "What's on parcel <id>?" | skill `parcel-dossier` |
| "Write SQL for ..." | skill `ontology-sql` |
| "Build / refresh / share the index" | skill `search-index-ops` |
| Verify one lead independently | subagent `lead-verifier` |

## Sessions

Three sessions share this repo: **data** (sources, lake builds), **cross-linking** (the
matcher, entity links) and **search** (this tooling). Use separate branches; the lake bucket
is shared. Get the index with `uv run python -m equity.search_index pull` instead of
rebuilding it.

## Checks

`make check` is exactly what CI runs (lint, mypy --strict, no-AI guard, secrets, tests,
coverage floors; about 25 minutes). Protected paths (`ci/`, `.github/`, `tests/golden/`,
`Makefile`, `pyproject.toml`, `config/sol.yaml`, `config/rules.yaml`, `config/doc_types.yaml`)
need the owner's review: never weaken them to pass CI.
