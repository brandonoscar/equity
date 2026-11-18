# Phase 1 status: CI and schema

Date: 2026-11-15. Cost: $0. No paid source, login, CAPTCHA or signed agreement was used.

## What works
- **`make check`** runs exactly what CI runs: ruff (lint + format), `mypy --strict` on
  `rules/`, `matching/`, `schema/` and `quality/`, the no-AI guard, the secrets scan, the tests
  and the coverage floors. Locally: **149 passed**, coverage **99%** overall
  (`rules/` and `matching/` have no code yet, so their 95% floors pass trivially).
- **GitHub Actions** (`.github/workflows/ci.yml`) runs on every push and PR as separate jobs
  (lint, types, no-ai-guard, secrets, tests) plus one aggregate job, **`all-green`**, which is
  the single check to require in branch protection.
- **Nightly** (`nightly.yml`): live adapter health (opens an issue on failure) and mutmut on
  `rules/` + `matching/` (opens an issue listing survivors). Both run but have nothing to check
  until Phases 2–4 add code.
- **Schema:** 29 tables in 7 forward-only, checksummed migrations. Editing an applied
  migration fails. Migrating twice is a no-op.
- **Loader:** append-only. A changed fact supersedes the old row instead of overwriting it, and
  re-loading identical content does nothing. IDs are sha256 of natural keys.
- **As-of queries:** owner of record, open encumbrances (release and partial release handled)
  and assessment, each by valid date *and* by what we knew at a given instant.

## How each required check is enforced
| # | Check | Where |
|---|---|---|
| 1 | ruff + mypy --strict | `make lint`, `make types` |
| 2 | No-AI guard (lockfile, pyproject, imports incl. `importlib`, LLM hostnames) + CAPTCHA-solver block | `ci/blocklist.toml`, `ci/check_no_ai.py`, `tests/test_no_ai_guard.py` |
| 3 | Rules unit + Hypothesis | Phase 4. Release semantics already property-tested in `tests/test_release_properties.py` |
| 4 | Matching tests | Phase 3 (`tests/matching/`) |
| 5 | Determinism (two full runs, byte-identical CSV snapshots) | `tests/test_determinism.py` |
| 6 | No network in tests | `--disable-socket` in pytest config, `tests/test_no_network.py` |
| 7 | Adapter contract | `tests/test_adapter_contract.py` (harness proven with an in-test adapter; no real adapters yet) |
| 8 | Migrate from empty, twice, then load fixtures | `tests/test_schema_migrations.py` |
| 9 | Provenance gate | `src/equity/quality/gates.py`, `tests/test_provenance_gate.py` |
| 10 | Temporal as-of | `tests/test_temporal.py` |
| 11 | Data invariants (future dates, negative amounts, lien without parcel, entity without link evidence, dangling refs, duplicate current rows) | `gates.py`, `tests/test_invariants.py` |
| 12 | Golden files | `tests/golden/` (template + harness; **0 cases**, so pass rate is n/a) |
| 13 | Phase 5 snapshot | Phase 5 |
| 14 | Coverage floors 95% rules/matching, 80% overall | `ci/coverage_floors.toml`, `ci/check_coverage.py` |
| 15 | Secrets scan | `ci/secrets_scan.py` (detect-secrets + `ci/.secrets.baseline`) |

## What doesn't work yet / needs you
1. **Branch protection is not on.** I can't set it, and `main` doesn't exist yet (the repo only
   has this branch). To set it up: create `main` from this branch (or merge a PR), then go to Settings → Branches →
   rule for `main` → require status check **`all-green`**, require PR review, **require review
   from Code Owners**, include administrators.
2. **The repo is public.** Two early commits on this branch (`d5a3f01`, `d1ea8b9`) contain
   private business details from your partner's memo. I removed them from the current file, but
   a history rewrite (force-push) was blocked. Options: make the repo private (recommended
   anyway before real debtor data or golden cases land), and/or tell me to rewrite this branch.
3. **DuckDB spatial extension** downloads from `extensions.duckdb.org`, which this sandbox
   can't reach. Geometry is stored as WKB so migrations don't need it. Spatial joins in Phase 2
   will need that host allowed (or the extension vendored).
4. All open decisions from `docs/phase0.md` §0 still stand (recorder export, OCR copies,
   WVPASS, SOS Custom List spend, pilot choice).

## Next (Phase 2, in your order)
Recorder adapter is blocked on access (§0.1), so the first adapters will be the ones that are
open today: WV statewide parcels (bulk file), the county ArcGIS parcel layer, ParcelWeb
ownership history, the statewide delinquent-properties layer, and the NDWV RSS feed. Each will
get recorded fixtures and the contract test.
