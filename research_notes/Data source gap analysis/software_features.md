# Software features audit: equity repo vs. desired feature list

Scope: code as it stands on branch `claude/ecstatic-archimedes-vzc9jb` (HEAD `b238028`), read on 2026-11-23. No code was changed. Citations are repo-relative file paths. Status is **done**, **partial** or **missing**. Effort: S is under a day, M is 1 to 3 days, L is a week or more.

Summary table

| # | Feature | Status | Effort to close |
|---|---|---|---|
| 1 | Adapter per source (fetch/normalize/health) | done (183 adapters) | S (gaps are in health depth, see #3) |
| 2 | Nightly runner + daily snapshot of sale listings | partial: runner builds each source once, with no recurring re-fetch and no daily listing snapshots | M |
| 3 | Health alerts on >10% row drop or field change | partial: field-set check on some adapters; no row counts, no history | M |
| 4 | Parquet + DuckDB with spatial queries | partial: Parquet/DuckDB done; spatial not used, no geometry loaded | M–L |
| 5 | CI tests on every adapter | done | — |
| 6 | Saved criteria queries ("Trey") | missing | S–M |
| 7 | Debtor scoring | missing (raw inputs exist in debtor_summary/people) | M |
| 8 | Bankruptcy schedules vs. property ownership | missing | L |
| 9 | Post-judgment transfers / nominee LLCs | missing (schema + config placeholders only) | M–L |
| 10 | Overassessed parcel finder | missing | M (L for broad coverage) |
| 11 | Coverage report by state and data type | partial: parcel coverage current; gaps.md misses most judgment/lien sources | S |
| 12 | PACER spend tracker (≤$30/quarter) | missing (no PACER adapter exists) | S–M |

## 1. Adapter for every source (fetch, normalize, health check)

### Takeaway
Done. Every source is an `Adapter` subclass with `source_row()`, `fetch()`, `normalize()` and `health()`, registered in one list. 183 adapters are registered, and a contract test runs each one against recorded fixtures.

### Cited Findings
- The contract is an ABC with four abstract methods: `source_row`, `fetch` (the only method allowed to touch the network), `normalize` (a pure function of the fetched bytes) and `health` (a live check, nightly only). `access_method` is one of bulk/api/arcgis/feed/html/manual. — [src/equity/adapters/base.py](src/equity/adapters/base.py)
- `REGISTRY` is filled from a single `_ALL` tuple. It mixes hand-written adapters with config-generated families: `all_state_adapters()`, `all_zoning_adapters()`, `all_lien_adapters()`, `all_registry_adapters()` and `court_adapters()` from `config/courts.yaml`. — [src/equity/adapters/registry.py](src/equity/adapters/registry.py)
- Counted at runtime with `uv run python -c "from equity.adapters.registry import REGISTRY..."`: **183 registered adapters**. By access_method: arcgis 99, api 58, bulk 13, feed 11, html 1, manual 1. By module: state_parcels 89, liens 49 (one per `config/liens/*.yaml`), ecf_rss 11, zoning 7, business_registry 4, hillsborough_civil 3, acris 2, and 18 single hand-written adapters (WV statewide/delinquent/parcelweb, TX StratMap, Cook, NYC condo units, Philadelphia RTT, Hillsborough/Hernando/Putnam OR, Citrus civil, Hernando civil, FJC IDB, FJC direct, EPA ECHO, Harris JP, Harris District, NJ code links). — [src/equity/adapters/registry.py](src/equity/adapters/registry.py), [src/equity/adapters/liens.py](src/equity/adapters/liens.py), [config/courts.yaml](config/courts.yaml)
- `tests/fixtures/adapters/` has 183 directories, one per registered source id. — [tests/fixtures/adapters/](tests/fixtures/adapters/)
- 34 per-adapter unit test modules sit in `tests/adapters/`, for example test_liens.py, test_ecf_rss.py, test_tx_harris_jp.py and test_snapshot_reload.py. — [tests/adapters/](tests/adapters/)

### Inferences
- "Adapter for every source" holds for every source the repo knows about. Covering more states or data types is a source-acquisition problem, and the framework itself is complete.
- The `health()` methods differ a lot in depth (see #3), so "health check per source" is only nominally complete.

### Gaps
- Whether all 183 health checks pass live today could not be checked: they need network access, and no health history is stored.

## 2. Nightly runner plus a daily snapshot of every sale listing

### Takeaway
Partial. There is a hosted loader (`lake.yml`, every 6 hours) and a nightly job (`nightly.yml`), but the nightly job only runs health checks and mutation tests. The loader builds each source **once**: after a source has `_counts.json` it is never re-fetched. Nothing snapshots sale listings (sheriff/tax sale lists) daily. The schema already supports transaction-time snapshots, so the missing piece is scheduling and re-fetching.

### Cited Findings
- `nightly.yml` (cron `41 8 * * *`) has two jobs. `adapter-health` runs `python -m equity.adapters.health` and opens a GitHub issue on failure. `mutation` runs mutmut over rules/ and matching/. It ingests no data. — [.github/workflows/nightly.yml](.github/workflows/nightly.yml)
- `lake.yml` runs on cron `23 */6 * * *`. A plan job pulls state from Supabase Storage and groups unfinished sources by host. One load job per host builds for up to 5 hours and pushes Parquet back. Without the `SUPABASE_SECRET_KEY` secret it is a no-op. — [.github/workflows/lake.yml](.github/workflows/lake.yml)
- `host_groups()` and `run_all()` skip any source whose `data/lake/<sid>/_counts.json` exists. A finished source is never rebuilt, so there is no recurring refresh. — [src/equity/lake.py](src/equity/lake.py) (`host_groups`, `run_all`)
- `parcel_sources()` limits what the loader builds: `*.parcels`, `*.zoning`, lien-config adapters and three EXTRA_SOURCES (`wv.statewide.delinquent`, `ny.nyc.acris.real`, `ny.nyc.dof.condo_units`). Court adapters (FJC, Harris JP/District, Hillsborough/Citrus/Hernando, Hillsborough/Hernando/Putnam OR) and the CM/ECF RSS feeds are **not** in the hosted loader. They exist in the local lake only because someone ran `lake build` by hand. — [src/equity/lake.py](src/equity/lake.py) (`EXTRA_SOURCES`, `parcel_sources`)
- The CM/ECF RSS feeds cover only about the last 24 hours, so "history comes from polling daily". No job polls them, and no `us.*.rss` source is in the local lake. — [src/equity/adapters/federal/ecf_rss.py](src/equity/adapters/federal/ecf_rss.py) docstring; `ls data/lake`
- docs/phase2.md says: "nothing schedules real ingestion … The RSS feeds only cover 24 hours, so history starts accruing only once a daily job writes somewhere durable." — [docs/phase2.md](docs/phase2.md)
- Transaction time is in place. Every fact table has `ingested_at`/`superseded_at`. The row loader supersedes a current row with the same domain key and different content. The bulk loader does the same set-based (one UPDATE to supersede, one INSERT for new keys). — [src/equity/schema/load.py](src/equity/schema/load.py), [src/equity/schema/bulk.py](src/equity/schema/bulk.py)
- Snapshot tables are designed for repeated fetches: `owner_snapshot` and `tax_delinquency_snapshot` carry `observed_on`, and a re-fetch showing the same status changes nothing. As-of queries (`owners_as_of`, `known_as_of`) read transaction time. — [src/equity/schema/migrations/V0008__owner_snapshot.sql](src/equity/schema/migrations/V0008__owner_snapshot.sql), [src/equity/schema/migrations/V0009__tax_delinquency_snapshot.sql](src/equity/schema/migrations/V0009__tax_delinquency_snapshot.sql), [src/equity/schema/temporal.py](src/equity/schema/temporal.py)
- `single_store` adapters (Hillsborough OR and civil, Hernando OR and civil, Harris District) load a series of daily or weekly files in order into one store so later files supersede earlier ones. They are rebuilt whole each time. — [src/equity/lake.py](src/equity/lake.py) (`_build_single_store`), [src/equity/adapters/fl/hillsborough_or.py](src/equity/adapters/fl/hillsborough_or.py)
- The Parquet lake has no transaction-time history across builds. `export_part` overwrites `<table>/<part>.parquet`, and `_build_single_store` deletes old parts first. The catalog is views over the current Parquet only. — [src/equity/lake.py](src/equity/lake.py) (`export_part`, `build_catalog`)
- Sale-listing sources: `tax_sale_event` is in the schema (events listed_delinquent/sold/redeemed/...). Sale-list sources exist as lien configs, for example `pa.washington.sheriff_sales` and `ms.harrison.tax_sale_parcels`. No code snapshots them on a schedule. — [src/equity/schema/migrations/V0006__tax.sql](src/equity/schema/migrations/V0006__tax.sql), [src/equity/matching/resolve.py](src/equity/matching/resolve.py) (STATES)

### Inferences
- Because Parquet parts are overwritten, a daily re-fetch into the current lake would supersede rows inside each scratch DB, but the earlier version would be lost when the part is overwritten. A true daily listing snapshot needs date-partitioned output (for example `data/lake/<sid>/<table>/dt=YYYY-MM-DD/*.parquet`), or an append-only `*_snapshot` table that keeps `observed_on`.
- Suggested approach (M): (a) add a `refresh` attribute or YAML key per source (daily/weekly/once), with a `lake refresh` command that ignores `_counts.json` for due sources and writes to a dated part; (b) add `nightly-ingest` jobs to nightly.yml for the RSS feeds, sale lists (sheriff/tax-sale/delinquent lists) and court daily files; (c) add a generic `sale_listing_snapshot` table (parcel_uid, sale_date, list_status, amount, observed_on), or reuse `tax_sale_event` with an `observed_on` column, so listing changes (added, pulled, postponed) can be diffed day over day.

### Gaps
- Whether lake.yml has actually run successfully (secret set, runs green) could not be checked from code.

## 3. Health alerts on a >10% row-count drop or field changes

### Takeaway
Partial. Nightly health opens a GitHub issue when any adapter's `health()` fails. About 100 ArcGIS-style adapters fail on a field-set change, and a few others check that required columns are present. There is **no row-count tracking at all**: no history, no percentage-drop rule. The `shape` fingerprint is computed but thrown away.

### Cited Findings
- `health.main()` calls each adapter's `health()` and prints JSON with only `source_id`, `ok` and `detail`. The `shape` field of `HealthReport` is not written. It exits 1 if any adapter is not ok. — [src/equity/adapters/health.py](src/equity/adapters/health.py), [src/equity/adapters/base.py](src/equity/adapters/base.py) (`HealthReport.shape`)
- nightly.yml opens an issue titled "Adapter health failure <date>" (deduplicated by title) with health.json in the body. health.json is not uploaded as an artifact or stored anywhere. — [.github/workflows/nightly.yml](.github/workflows/nightly.yml)
- Field-change detection, where it exists, takes three forms: (1) state parcel and ArcGIS adapters require the sorted attribute set to equal the configured field set exactly (`shape == tuple(sorted(self.fields))`); (2) Philadelphia RTT checks that required COLUMNS are present; (3) the business registry checks that its key and name columns are present. — [src/equity/adapters/state_parcels.py](src/equity/adapters/state_parcels.py) (`health`), [src/equity/adapters/arcgis_adapter.py](src/equity/adapters/arcgis_adapter.py), [src/equity/adapters/pa/philadelphia_rtt.py](src/equity/adapters/pa/philadelphia_rtt.py), [src/equity/adapters/business_registry.py](src/equity/adapters/business_registry.py)
- The 49 lien adapters only check that at least one row comes back (`ok=bool(rows)`). Zoning adapters check `returnCountOnly` > 0 or that the catalog is non-empty. ECF RSS checks that a `<channel>` element exists. None of these compares fields or counts against a baseline. — [src/equity/adapters/liens.py](src/equity/adapters/liens.py) (`health`), [src/equity/adapters/zoning.py](src/equity/adapters/zoning.py), [src/equity/adapters/federal/ecf_rss.py](src/equity/adapters/federal/ecf_rss.py)
- Row counts exist only as build outputs: `data/lake/<sid>/_counts.json` (per-table counts after a build) and per-part markers in `_parts/*.json`. Nothing compares them across runs. — [src/equity/lake.py](src/equity/lake.py) (`export_source`, `build`, `status`)
- `data_issue` holds records an adapter could not turn into facts. It is for per-record review, not source-level drift. — [src/equity/schema/migrations/V0010__data_issue.sql](src/equity/schema/migrations/V0010__data_issue.sql)

### Inferences
- Suggested approach (M): add an optional `count()` method to the contract (ArcGIS `returnCountOnly=true`, Socrata `$select=count(*)`, CKAN `total`, file size or line count for bulk files). Have `health.main()` write `{source_id, checked_at, ok, count, shape}` to a durable `health_history.jsonl` (an Actions cache/artifact, the Supabase bucket the lake already uses, or a `source_health` table). Then a `health diff` step flags `count < 0.9 × previous` or `shape != previous shape` and opens one issue per source. That covers lien and zoning adapters, which today only check for a non-empty response. S for the shape history alone, M with counts for all access methods.

### Gaps
- None for the code question.

## 4. Parquet storage and DuckDB with spatial queries

### Takeaway
Parquet + DuckDB: done. Spatial: missing. `parcel_geometry` exists in the schema (WKB + bbox), but no adapter emits it and no code loads the DuckDB spatial extension. Point-in-polygon work for zoning uses hand-written pure-Python shapefile code.

### Cited Findings
- Each source is ingested into a scratch DuckDB, exported to zstd Parquet under `data/lake/<source_id>/<table>/<part>.parquet` (split at 40 MB for object storage), and exposed through `data/catalog.duckdb`, which holds only views (`read_parquet([...], union_by_name=true)`, DISTINCT for non-fact tables). — [src/equity/lake.py](src/equity/lake.py) (module docstring, `export_part`, `build_catalog`)
- Parquet parts sync to a Supabase Storage bucket so builds can resume on another machine. — [src/equity/lake_sync.py](src/equity/lake_sync.py)
- Match runs are DuckDB SQL over the lake Parquet and write Parquet outputs to `data/derived/<state>/`. — [src/equity/matching/resolve.py](src/equity/matching/resolve.py) (`run`)
- The migration comment says: "Geometry is stored as WKB so migrations need no DuckDB extension; spatial queries load the spatial extension and call ST_GeomFromWKB at query time." `parcel_geometry` has geom_wkb, srid and xmin/ymin/xmax/ymax. — [src/equity/schema/migrations/V0003__property.sql](src/equity/schema/migrations/V0003__property.sql)
- `parcel_geometry` appears only in the catalog registration. No adapter yields it (grep for `"parcel_geometry"` in src/equity/adapters finds nothing). — [src/equity/schema/catalog.py](src/equity/schema/catalog.py)
- No `INSTALL spatial`, `LOAD spatial` or `ST_` call appears anywhere in src/. — grep over [src/equity/](src/equity/)
- docs/phase2.md: "County ArcGIS parcel layer (geometry) not built yet … Geometry needs the DuckDB spatial extension, whose download host isn't reachable here." — [docs/phase2.md](docs/phase2.md)
- Zoning-to-state assignment uses a custom .shp reader and bbox/point-in-polygon in Python (`StateShape`, `state_at`). — [src/equity/zoning_catalog.py](src/equity/zoning_catalog.py)
- The zoning adapters store `zoning_district` geometry (they skip features with no shape), but parcel × zoning joins are not computed. — [src/equity/adapters/zoning.py](src/equity/adapters/zoning.py)

### Inferences
- Suggested approach (M–L): (1) request `returnGeometry=true` with `outSR=4326` in the ArcGIS/state parcel adapters, behind a config flag because it multiplies payload size, and emit `parcel_geometry` rows with bbox; (2) pin the DuckDB spatial extension in CI, cache the extension directory, or vendor it, because the download host is blocked in the cloud session; (3) add spatial helpers (parcel→zoning district, parcel→flood zone, adjacent parcels owned by the same debtor). Spatial is not needed for the current debtor→parcel matching, which is key-based. Its value is in zoning, assemblage and comparable-sales radius queries (#10).

### Gaps
- Whether the spatial extension host is reachable from GitHub Actions runners (as opposed to the cloud session) was not tested.

## 5. CI tests on every adapter

### Takeaway
Done. `test_registered_adapters` loops over all 183 registered adapters and checks the abstract methods, a non-empty fixture, deterministic normalize(), loading into the schema and the provenance gate. CI runs it with network blocked on Python 3.12 and 3.13.

### Cited Findings
- `check_contract` requires a recorded fixture dir per source and runs normalize() twice, asserting equal and non-empty output. It loads every row via `load_rows` and asserts `provenance_violations(con) == []`. `test_every_fixture_dir_has_an_adapter` catches orphaned fixtures. The harness tests itself with a dummy adapter. — [tests/test_adapter_contract.py](tests/test_adapter_contract.py)
- The ci.yml `tests` job runs `make sync test coverage` on a Python 3.12/3.13 matrix. Separate jobs run lint (ruff), types (`mypy --strict`), no-AI guard, secrets scan, repo hygiene, actionlint and dependency audit. `all-green` is the single required check. — [.github/workflows/ci.yml](.github/workflows/ci.yml), [Makefile](Makefile)
- Network is blocked in tests (`tests/test_no_network.py`). Fixture privacy is checked (`tests/test_fixture_privacy.py`). — [tests/](tests/)
- Coverage floors: 80% overall, 95% for `equity/rules/` and `equity/matching/`. — [ci/coverage_floors.toml](ci/coverage_floors.toml)
- Nightly mutation testing runs on rules/ and matching/ and files an issue for survivors. — [.github/workflows/nightly.yml](.github/workflows/nightly.yml)

### Inferences
- The only weak spot is that `health()` itself is never exercised against fixtures (it is live-only). A fixture-based health test (mock client returns the fixture, expect ok=True) would catch broken health code before the nightly run (S).

### Gaps
- CI pass/fail status on the current branch was not checked.

## 6. Saved criteria queries for Trey

### Takeaway
Missing. There is no saved-query, saved-search, report or user-facing filter layer. The only outputs are fixed per-state Parquet files and a counts-only summary.json.

### Cited Findings
- `resolve.main()` takes only `--state`, `--lake` and `--out`, and writes `matches.parquet`, `debtor_summary.parquet`, `people.parquet`, `mortgage_status.parquet` (when recorder sources exist) and `summary.json`. It has no filter or threshold arguments. — [src/equity/matching/resolve.py](src/equity/matching/resolve.py) (`run`, `main`)
- The columns needed for Trey's example query exist. `people`: person_id, name, open_count, open_amount, foreclosure_filings, sources, debt_kinds, parcels, parcel_value. `debtor_summary` adds open_mortgages, open_mortgage_amount and equity_est (where mortgages exist: NY only). — [src/equity/matching/resolve.py](src/equity/matching/resolve.py) (`PEOPLE_SUMMARY_SQL`, `match`), [src/equity/matching/equity.py](src/equity/matching/equity.py)
- No module, config dir or CLI for queries/reports was found: no `queries/` or `reports/` code, and `reports/` holds only research markdown. `config/private/` is git-ignored "business settings". — [README.md](README.md), `ls reports config`
- `people` has no per-person state or county column (it has sources and parcel counts). `equity_est` lives in `debtor_summary` (per party), not in `people` (per merged person). — [src/equity/matching/resolve.py](src/equity/matching/resolve.py)

### Inferences
- Suggested approach (S–M): add `config/private/queries/*.yaml`, git-ignored because criteria may be business-sensitive, for example `{name, state(s), min_open_amount, min_equity, debt_kinds, min_parcels, decision: auto}`. Add `python -m equity.queries run <name>`, which compiles the YAML into parameterized DuckDB SQL over `data/derived/*/people.parquet` and `debtor_summary.parquet` and writes CSV/Parquet with a run timestamp. Optionally diff against the last run so it only reports new hits ("new since yesterday"). First add `state` (from the run) and `equity_est` to `people` so one file answers the query. Keep thresholds as config so the no-AI and determinism rules still hold.

### Gaps
- Who Trey is and exactly which criteria he wants are not in the repo.

## 7. Debtor scoring (worth a PACER pull or a purchase)

### Takeaway
Missing. `rules/` is an empty package (docstring only). Matching outputs carry raw inputs (open_amount, parcels, parcel_value, equity_est, foreclosure_filings, match strength) but no score or rank. The SOL and threshold configs it would depend on are entirely null.

### Cited Findings
- `src/equity/rules/__init__.py` contains only a docstring: "Deterministic rule functions (Phase 4): lien priority, equity, judgment age, transfer flags." `tests/rules/test_package.py` only checks that the docstring exists. — [src/equity/rules/__init__.py](src/equity/rules/__init__.py), [tests/rules/test_package.py](tests/rules/test_package.py)
- resolve.py says it runs with "no fuzzy scores". Each match gets a rule_id and an auto/review decision. `debtor_summary` has `best_rank` (the strongest match rule) and `has_auto`. — [src/equity/matching/resolve.py](src/equity/matching/resolve.py)
- equity.py gives an `equity_est` lower bound (parcel_value − open recorded mortgage principal) only for runs with mortgage sources, and only NY lists `mortgages`. — [src/equity/matching/equity.py](src/equity/matching/equity.py), [src/equity/matching/resolve.py](src/equity/matching/resolve.py) (STATES)
- `config/sol.yaml` has every state's `judgment_enforceable_years`/`lien_years`/... set to null (358 nulls). The header says "Rules that need a null value refuse to run." — [config/sol.yaml](config/sol.yaml)
- `config/rules.yaml` has every threshold null: matching cutoffs, transfer_flags, `valuation.assessed_ratio.WV`, `priority.same_day_tiebreak`. — [config/rules.yaml](config/rules.yaml)
- `tests/golden/cases/` is empty, and docs/phase2.md reports "Golden-file pass rate: n/a (0 cases)". — [tests/golden/](tests/golden/), [docs/phase2.md](docs/phase2.md)

### Inferences
- Suggested approach (M): write a deterministic, config-weighted score in `rules/score.py`, for example `config/scoring.yaml` with explicit points or tiers, no ML. Inputs: equity_est, or parcel_value when there is no mortgage data; open_amount; the ratio equity/open_amount; judgment age vs. SOL (needs sol.yaml filled); debt kind (court_judgment > tax_delinquency, from debt_kinds.yaml); match decision (auto only); absence of bankruptcy (#8) and of post-judgment transfers (#9); homestead flag (owner_snapshot/parcel V0012 homestead) as a negative. Output: tier and the list of reasons, so it stays citable. Add a "PACER-worthy" flag: federal court judgment debtor (FJC IDB) with matched parcels above $X, where a docket pull would confirm amount and status. Effort rises to L if lien priority (recording-date stack) must be computed first.

### Gaps
- Brandon's weights and thresholds are not in the repo. Every relevant config value is null.

## 8. Bankruptcy schedules checked against property ownership

### Takeaway
Missing. The ECF RSS adapters (11 courts) emit `court_case`, `party`, `case_party` and `docket_entry` rows, but never `bankruptcy` rows, and they are not loaded into the lake or matched. No schedule (A/B real property) data is fetched: it would need PACER documents.

### Cited Findings
- ecf_rss.py parses the case number, caption, entry type, chapter and trustee. It emits court_case (`nature_of_suit="chapter N"`), party/case_party (including trustee) and docket_entry `text="[entry_type]"`. The docstring says "Not the docket text." There is no `ctx.fact("bankruptcy", ...)`. — [src/equity/adapters/federal/ecf_rss.py](src/equity/adapters/federal/ecf_rss.py)
- The `bankruptcy` table (chapter, petition_on, discharge_on, dismissed_on, converted_on, trustee_party_id, asset_case) exists, but no adapter writes it. — [src/equity/schema/migrations/V0005__courts.sql](src/equity/schema/migrations/V0005__courts.sql); grep `"bankruptcy"` in src/equity/adapters finds only the source `kind`
- Enabled RSS courts: flmb, flsb, flnb, nysb, paeb, ohnb, njb, ganb, txnb, plus NDWV wvnd/wvnb, all hand-registered. — [config/courts.yaml](config/courts.yaml), [src/equity/adapters/registry.py](src/equity/adapters/registry.py)
- No `us.*.rss` source is in `parcel_sources()` or in the local `data/lake/`. matching/ never references bankruptcy. — [src/equity/lake.py](src/equity/lake.py), [src/equity/matching/](src/equity/matching/)
- federal/__init__.py: "CM/ECF public feeds; PACER later, metered and approved." No PACER adapter exists. — [src/equity/adapters/federal/__init__.py](src/equity/adapters/federal/__init__.py)

### Inferences
- Step 1 (M): build the RSS feeds daily (#2) and emit `bankruptcy` rows (chapter, petition_on from the first "Voluntary Petition" entry, discharge or dismissal from the entry type). Add a match step that flags debtors in `people` whose name_key and ZIP/county match a bankruptcy debtor party (automatic stay means do not buy or enforce; discharge may void unsecured judgments but not liens already attached to real property). That is a cheap, high-value negative filter for #7.
- Step 2 (L): the schedules check proper. Fetch the Schedule A/B PDF through PACER (metered, so it needs #12) only for top-scored debtors with matched parcels, parse the real-property lines with the existing `pdf_table.py`, and compare against `matches`. Parcels the debtor owns but did not list are an undisclosed-asset flag.

### Gaps
- RSS item formats differ by court (the adapter handles several layouts). Whether "discharge" and "dismissed" entries reliably show up in the feeds was not verified.

## 9. Detection of transfers after a judgment and of nominee LLCs

### Takeaway
Missing. The schema can represent dated ownership and deeds with consideration, and `config/rules.yaml` has a `transfer_flags` section, but every parameter is null and no code implements it. The business registries (LLC → officers/agents) are adapters only: not in the lake and not used in matching.

### Cited Findings
- `config/rules.yaml` `transfer_flags` sets `nominal_consideration_max`, `nominal_fraction_of_appraised` and `related_party_rules` (same_surname, same_mailing_address, debtor_is_member_or_agent_of_grantee_llc) all to null with `TODO(Brandon)`. — [config/rules.yaml](config/rules.yaml)
- `rules/` is empty apart from its docstring, which lists "transfer flags" as Phase 4. — [src/equity/rules/__init__.py](src/equity/rules/__init__.py)
- `ownership_period` (valid_from/valid_to, sale_price, deed_book/page) is emitted only by the WV Monongalia ParcelWeb adapter. Statewide parcel adapters emit `owner_snapshot` (current owner, with `observed_on`). — [src/equity/schema/migrations/V0003__property.sql](src/equity/schema/migrations/V0003__property.sql), [src/equity/adapters/wv/parcelweb.py](src/equity/adapters/wv/parcelweb.py), [src/equity/schema/migrations/V0008__owner_snapshot.sql](src/equity/schema/migrations/V0008__owner_snapshot.sql)
- Deeds with consideration and grantor/grantee parties come from ACRIS (`consideration=amount`), Philadelphia RTT (`consideration=price`) and Hillsborough OR (`consideration=price`). Hernando and Putnam OR emit deeds with `consideration=None`. — [src/equity/adapters/ny/acris.py](src/equity/adapters/ny/acris.py), [src/equity/adapters/pa/philadelphia_rtt.py](src/equity/adapters/pa/philadelphia_rtt.py), [src/equity/adapters/fl/hillsborough_or.py](src/equity/adapters/fl/hillsborough_or.py), [src/equity/adapters/fl/hernando_or.py](src/equity/adapters/fl/hernando_or.py), [src/equity/adapters/fl/putnam_or.py](src/equity/adapters/fl/putnam_or.py)
- The only existing deed logic is `paid_sale` in equity.py: a later deed to grantees who are not the borrowers marks a mortgage paid. It is not used to flag debtor transfers. — [src/equity/matching/equity.py](src/equity/matching/equity.py)
- Business registry adapters exist for NY, CO, CT and OR. They emit business and business_role rows (agent/officer/director). `gaps.md` lists `*.sos.business` under entities, but no `*.sos.business` source is in the local lake, and matching/ never reads business or business_role. — [src/equity/adapters/business_registry.py](src/equity/adapters/business_registry.py), [docs/gaps.md](docs/gaps.md), [src/equity/matching/resolve.py](src/equity/matching/resolve.py)
- `entity`/`entity_link`/`review_queue` tables and quality gates for link evidence exist, but no code fills them. — [src/equity/schema/migrations/V0002__parties_entities.sql](src/equity/schema/migrations/V0002__parties_entities.sql), [src/equity/quality/gates.py](src/equity/quality/gates.py)

### Inferences
- Two cheap detectors work with data already loaded (M):
  1. **Post-judgment deed-out** (ACRIS NYC, Philadelphia RTT, Hillsborough OR): for each debtor in `people`, find DEED instruments where a debtor party (name_key) is grantor and recorded_on > judgment recorded/entered date. Flag nominal consideration (thresholds from rules.yaml), a grantee sharing the surname or mailing address, or a grantee that is an org.
  2. **Snapshot owner change**: once parcels are re-snapshotted (#2), an `owner_snapshot` row superseded after the judgment date, where the debtor drops off, flags a transfer. This works statewide where there is no recorder data, and depends on #2.
- Nominee LLC (M–L): load the business registries into the lake and match a debtor name_key/address against `business_role` (agent/officer/organizer). Then join the business's org_name_norm to parcel owners. That turns "LLC owns parcel, debtor is its officer" into a review-queue entry with evidence (`entity_link.signals`). Coverage is limited to 4 registry states until more SOS sources are added.

### Gaps
- Most states' statewide parcel layers carry no sale date or price (see #10), so deed-based detection is limited to recorder sources.

## 10. Overassessed parcel finder (property tax appeals)

### Takeaway
Missing. `parcel_assessment` is populated widely (appraised land/bldg/total, assessed value, tax_year), but sales data is thin. The canonical parcel field list has no sale price or date, and no code compares assessments with sales or with neighbors.

### Cited Findings
- `parcel_assessment` columns: tax_year, appraised_land/bldg/total, assessed_value, tax_class, valid_from/to. State parcel adapters fill them from `land_value`, `bldg_value`, `total_value` and `assessed_value`. — [src/equity/schema/migrations/V0003__property.sql](src/equity/schema/migrations/V0003__property.sql), [src/equity/adapters/state_parcels.py](src/equity/adapters/state_parcels.py)
- The canonical parcel config fields are parcel_id, owner1/2, mail_*, land/bldg/total/assessed value, tax_year and deed_book/page/ref. There is no sale_price or sale_date key, and grep of config/states and config/counties finds no `sale*` mapping. — [src/equity/adapters/state_parcels.py](src/equity/adapters/state_parcels.py) (field list, ~line 44)
- Sale-price sources in code: `ownership_period.sale_price` (WV ParcelWeb only) and deed `consideration` (ACRIS, Philadelphia RTT, Hillsborough OR). — see #9 citations
- `config/rules.yaml` `valuation.assessed_ratio.WV: null`. No other valuation logic exists. — [config/rules.yaml](config/rules.yaml)
- Grep for "overassess", "appeal", "sales_ratio" and "comparable" finds nothing in src/ or docs/. — grep over [src/equity/](src/equity/), [docs/](docs/)

### Inferences
- Suggested approach (M for NYC, Philadelphia, Hillsborough and WV; L for broad coverage): `equity/rules/assessment.py`. (1) Arm's-length sales: deeds with consideration > nominal, not between related parties (reuse #9's flags), within 24 months. (2) Sales ratio = assessed (or appraised) / sale price per parcel. Flag parcels whose ratio exceeds the jurisdiction median by a configured factor, plus the IAAF-style COD/PRD per neighborhood. (3) For parcels without a sale, compare $/sqft or $/acre against same-land-use parcels in the same district or zip, or a spatial radius once #4 lands. Needs per-state assessment-level ratios in config (statutory 100%, 60% in WV, ...). Most statewide parcel layers carry only values, so coverage grows only as sale fields are mapped in the state YAMLs (many ArcGIS parcel layers publish SALE_PRICE/SALE_DATE that are currently unmapped).
- This feature serves a different customer (owners appealing taxes) from the debtor-equity core, so it should be scoped separately.

### Gaps
- How many configured parcel layers expose sale price or date fields that are just unmapped was not counted.

## 11. Coverage report by state and data type

### Takeaway
Partial. `docs/coverage.md` (parcels) is generated and CI-checked for drift, so it is current. `docs/gaps.md` (layers by state) is generated but uses hard-coded source prefixes. It misses most judgment, lien and recorder sources added since, has no liens/tax column, and is not CI-checked.

### Cited Findings
- `equity.coverage` generates docs/coverage.md from config/states, config/counties and coverage_notes.yaml: per state, its adapters and owner/values/mailing flags. It reports 49 of 51 states/DC with an adapter and 32 with owners+values. `tests/test_coverage.py` asserts the generated output equals the committed file. — [src/equity/coverage.py](src/equity/coverage.py), [tests/test_coverage.py](tests/test_coverage.py), [docs/coverage.md](docs/coverage.md)
- `equity.gaps` generates docs/gaps.md with layers parcels / fields / instruments / judgments / bankruptcy / entities / zoning / ordinances. `INSTRUMENT_SOURCES = ("ny.nyc.acris.", "pa.philadelphia.rtt", "fl.hillsborough.or")` and `JUDGMENT_SOURCES = ("fl.hillsborough.civil.", "fl.hillsborough.garnishment", "ny.nyc.acris.real")`. — [src/equity/gaps.py](src/equity/gaps.py)
- So the committed gaps.md shows TX judgments "—" (Harris JP and District adapters exist) and FL instruments only `fl.hillsborough.or` (Hernando and Putnam OR exist). It has no column for the 49 lien/warrant/tax-delinquency configs, and its summary says "State-court judgments: 2". It also omits federal FJC/EPA court data. — [docs/gaps.md](docs/gaps.md), [src/equity/adapters/registry.py](src/equity/adapters/registry.py)
- gaps.md's "Loaded" column reads the local `data/lake/*/_counts.json`, so it differs by machine. Regenerating here changes every Loaded cell (for example AK 218,934 → 0). `tests/test_gaps.py` tests the generator but does not compare against the committed file. — [src/equity/gaps.py](src/equity/gaps.py) (`_loaded_parcels`), [tests/test_gaps.py](tests/test_gaps.py)
- `config/debt_kinds.yaml` already labels every debtor/court/writ source with a debt kind (court_judgment, recorded_judgment_or_lien, administrative_judgment, tax_warrant, tax_lien, tax_delinquency, code_enforcement_charge/lien, statutory_lien, foreclosure, housing_court_case, eviction). `tests/test_debt_kinds.py` requires every match-run source to be listed. — [config/debt_kinds.yaml](config/debt_kinds.yaml), [tests/test_debt_kinds.py](tests/test_debt_kinds.py)
- docs/gaps.md and docs/coverage.md were last committed 2026-11-23 01:29 UTC. gaps.py was last changed in b69fbfa (2026-11-21). — `git log`

### Inferences
- Suggested fix (S): drive gaps.py from `debt_kinds.yaml` and the source `kind` instead of prefixes. Add one column per debt kind, or group into "court judgments", "recorded liens", "tax", "code enforcement". Add a "match run" column (state is in resolve.STATES), and move "Loaded" into a separate locally generated file, or drop it, so gaps.md can get the same committed-equals-generated test as coverage.md.

### Gaps
- None.

## 12. PACER spending tracker (≤$30/quarter fee waiver)

### Takeaway
Missing. No PACER adapter exists. Everything federal is free (CM/ECF RSS, FJC IDB, CourtListener copy, EPA ECHO). Fee terms are documented only in docs/phase0.md. The `source.cost_model` column exists but nothing meters it.

### Cited Findings
- docs/phase0.md records the PACER fees: "$0.10/page, $3 cap per document (search results and reports uncapped), waived if a quarter totals ≤ $30", and "Terms bar automated harvesting that avoids billing". — [docs/phase0.md](docs/phase0.md)
- The base contract says adapters "never call a paid source unless the source is approved in config". federal/__init__.py says "PACER later, metered and approved." — [src/equity/adapters/base.py](src/equity/adapters/base.py), [src/equity/adapters/federal/__init__.py](src/equity/adapters/federal/__init__.py)
- `source.cost_model VARCHAR NOT NULL` is filled from each source's `terms.cost_model` in YAML. No code reads it to enforce a budget. — [src/equity/schema/migrations/V0001__provenance.sql](src/equity/schema/migrations/V0001__provenance.sql), [src/equity/adapters/liens.py](src/equity/adapters/liens.py)
- `fetch_log` records request, bytes, http_status and content_sha256 per fetch, but no cost. — [src/equity/schema/migrations/V0001__provenance.sql](src/equity/schema/migrations/V0001__provenance.sql), [tests/test_adapter_contract.py](tests/test_adapter_contract.py)
- The ECF RSS docstring notes there is no PACER charge and that PACER terms bar fee-avoiding harvesting. — [src/equity/adapters/federal/ecf_rss.py](src/equity/adapters/federal/ecf_rss.py)

### Inferences
- Suggested approach (S–M, built before any PACER adapter): a `pacer_ledger` table, or `config/private/pacer_ledger.jsonl` because it is account data, with `{ts, court_id, case, doc/page count, billable_pages, cost, quarter}`. Add a `budget` guard in a `PacerClient` that computes the cost before fetching (pages × $0.10, $3 cap per document, uncapped for search/report pages) and refuses when quarter-to-date + cost > a configured ceiling (for example $28, leaving margin under $30). Reconcile against the PACER account's quarterly statement by hand, and raise a nightly alert at 80%. Couple it to #7 so only top-scored debtors are pulled. One person or one account should own the quota, because the waiver is per account per quarter.

### Gaps
- Whether the project has a PACER account, and whether the waiver applies to its account type, is not in the repo.

## Other notable findings (match runs, debt kinds, quality gates, branches, workflows)

### Takeaway
There are 18 match runs. WV, the stated pilot state, has none. 13 lake sources are loaded but used by no run. Quality gates run only in tests, never on real builds. The current branch is 57 commits ahead of `main` and unmerged, and scheduled workflows (lake.yml, nightly.yml) run only from `main`, so the hosted loader builds main's 8 lien configs instead of this branch's 49.

### Cited Findings
- `resolve.STATES` has 18 runs: AZ-COCHISE, AZ-PIMA, CT, FL, IL-COOK, LA-NOLA, MI-DETROIT, MS-HARRISON, NC, NY, OH, PA, PA-ALLEGHENY, PA-WASHINGTON, TX-HARRIS, VA-RICHMOND, VT, WI-MILWAUKEE. All but PA-WASHINGTON add `FEDERAL_COURTS` (FJC IDB, FJC direct, EPA ECHO). Only NY has `mortgages` (ACRIS) and `links` (condo units), so equity_est exists only for NY. CT, PA, VT and IL-COOK use street+town. — [src/equity/matching/resolve.py](src/equity/matching/resolve.py)
- WV has no match run, even though lake.py `PRIORITY` puts `wv.` first ("pilot state"). No `wv.*` source is in the local `data/lake/`. — [src/equity/lake.py](src/equity/lake.py), [src/equity/matching/resolve.py](src/equity/matching/resolve.py); `ls data/lake`
- Lake sources loaded locally but in no run: ca.cdtfa.top500, ca.ftb.top500_corporate, ca.ftb.top500_personal, de.revenue.top_delinquent_business/personal, ne.dor.delinquent_taxpayers, nj.dol.wage_watchlist, nj.dol.wall, ny.nyc.acris.personal, ny.nyc.evictions, va.virginia_beach.delinquent_taxes, fl.hernando.civil.filings, fl.hillsborough.civil.filings. CA, DE, NE and NJ have no owner parcel source for a run (CA counties redact owner names, per coverage.md). — computed from `resolve.STATES` vs `data/lake/`; [docs/coverage.md](docs/coverage.md)
- `data/derived/` has stale run folders (`oh-hamilton`, `nc-buncombe`) that no longer match STATES keys (`OH`, `NC`). — `ls data/derived`
- The latest NY run (`data/derived/ny/summary.json`): 4,691,003 debtor parties; 969,754 auto-matched debtors; open_amount_auto $540.5M; people_with_parcels 168,405; mortgage lots open 242,586 / paid_payoff 233,328 / paid_sale 72,121 / paid_ref 3,188; debtors_auto_with_positive_equity 556,594. — [data/derived/ny/summary.json](data/derived/ny/summary.json) (git-ignored, local)
- Match rules (deterministic, strongest first): person_name_address (auto), org_name_address (auto), org_name_zip (auto), person_name_zip (review), lien_names_parcel (auto), org_name_county (review), person/org_name_street_town (auto, CT-approved). — [src/equity/matching/resolve.py](src/equity/matching/resolve.py) docstring
- `config/debt_kinds.yaml` defines 13 kinds and maps every match-run source to one (test-enforced). Outputs: `people.debt_kinds`, `summary.open_linked_by_kind`. — [config/debt_kinds.yaml](config/debt_kinds.yaml), [tests/test_debt_kinds.py](tests/test_debt_kinds.py)
- Quality gates: `provenance_violations` checks that every fact traces to a source record, fetch and source. `invariant_violations` checks no dates after retrieval, no negative decimals, no parcel-specific lien without a parcel, no entity without link evidence, and no dangling edges. These are called only from tests (test_adapter_contract, test_ingest, test_lake, test_provenance_gate). `lake build`, `ingest` and `resolve` never call them, so real loaded data is never gated. — [src/equity/quality/gates.py](src/equity/quality/gates.py); grep of callers
- Branches: `claude/ecstatic-archimedes-vzc9jb` (current) is 57 commits ahead of `origin/main` and 0 behind (163 files, +40,603 lines). `claude/dreamy-ramanujan-fy6h3y` is already contained in the current branch. Main holds 8 `config/liens/*.yaml`; this branch holds 49. — `git rev-list`, `git ls-tree`
- GitHub runs `schedule` triggers only on the default branch, so lake.yml and nightly.yml run main's code. Here that means main's registry. Unmerged lien sources and the `lake.py`/`lake_sync.py` changes on this branch (+51/−11 lines) are not built or health-checked by the hosted jobs until merged. — [.github/workflows/lake.yml](.github/workflows/lake.yml), [.github/workflows/nightly.yml](.github/workflows/nightly.yml), `git diff --stat origin/main HEAD`
- `config/rules.yaml` and `config/sol.yaml` are entirely null, waiting on the owner. Golden cases are empty. — [config/rules.yaml](config/rules.yaml), [config/sol.yaml](config/sol.yaml), [tests/golden/](tests/golden/)

### Inferences
- Highest-leverage next steps, in order: (1) merge the branch so the hosted loader and nightly health cover the 49 lien sources (S); (2) add the WV match run (pilot) and recurring refreshes plus RSS polling (#2, M); (3) run `invariant_violations` and `provenance_violations` on each scratch DB in `lake.build`, failing the part instead of exporting it (S); (4) store health history with row counts (#3, M); (5) saved queries over people/debtor_summary (#6, S–M); (6) bankruptcy rows as a negative filter (#8 step 1, M); (7) a scoring rule (#7), which is blocked on sol.yaml/rules.yaml values from the owner.

### Gaps
- Whether lake.yml's `SUPABASE_SECRET_KEY` is set on the GitHub repo, and whether recent scheduled runs succeeded, could not be determined from code.
