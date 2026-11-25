# Repo inventory: what brandonoscar/equity already answers per debtor

Scope: internal scan of /home/user/equity, branch `claude/dreamy-ramanujan-fy6h3y` (HEAD 4436f70, 2026-11-25, includes latest main). Sources below are repo paths (relative to the repo root). Counts come from the files themselves, from the adapter registry imported in the repo's own venv, or from counts-only `summary*.json` files in the local (git-ignored) `data/derived/`. Local derived outputs may be stale (NY `summary.json` is dated 2026-11-22). Anything not stated in the repo is marked "Inferred".

Legend for each item: **[code]** = built, just code; **[owner]** = blocked on an owner-decision config that is null and marked "TODO(Brandon)" or "filled in by Brandon"; **[approval]** = change needs Brandon's sign-off (CODEOWNERS path or a matching rule he must approve); **[legal]** = blocked on a legal read; **[missing]** = not built.

Cross-cutting facts:
- 971 adapters are registered (`REGISTRY` from `src/equity/adapters/registry.py`), including 277 `*.parcels`, 102 `*.rss` court feeds, 24 `*.sheriff_sales`, 43 national `us.*` non-RSS sources — [src/equity/adapters/registry.py](src/equity/adapters/registry.py) (counted by importing it).
- Config-driven source families: `config/liens/` 317 files, `config/deeds/` 40, `config/licenses/` 128, `config/person_lists/` 22, `config/business/` 7, `config/recorders/` 5, `config/courts_state/` 5, `config/courts_federal/` 3, `config/states/` 33, `config/counties/` 236 — [config/](config/) (ls counts).
- 70 match runs are defined in `STATES` in [src/equity/matching/resolve.py](src/equity/matching/resolve.py); `docs/gaps.md` counts match runs in 49 states — [docs/gaps.md](docs/gaps.md).
- Pipeline order inside one match run: resolve -> entities (if registries) -> bankruptcy (if feeds) -> transfers (if deeds) -> equity (if mortgages) — [src/equity/matching/resolve.py](src/equity/matching/resolve.py) `run()` lines ~694-726.
- CODEOWNERS protects `/tests/golden/`, `/ci/`, `/.github/`, `/Makefile`, `/pyproject.toml`, `/config/sol.yaml`, `/config/rules.yaml`, `/config/doc_types.yaml` (all `@brandonoscar`; "The agent must never weaken anything in these paths to pass CI") — [CODEOWNERS](CODEOWNERS). Note: `config/scoring.yaml`, `config/pacer.yaml`, `config/refresh.yaml` and `config/debt_kinds.yaml` are NOT in CODEOWNERS.
- Owner-decision null counts (parsed with PyYAML): `sol.yaml` 357 null of 358 leaves (51 states x 7 fields, all null; 0 states filled); `scoring.yaml` 11 null weights of 12 leaves, `tiers: []`; `rules.yaml` 9 null of 11 leaves; `pacer.yaml` 1 null (`quarterly_ceiling`); `doc_types.yaml` 0 nulls but header says "TODO(Brandon): confirm every list"; `sol_proposed.yaml` 0 nulls (310 leaves) but every state `verified: false` and "Nothing in code reads this file" — [config/sol.yaml](config/sol.yaml), [config/scoring.yaml](config/scoring.yaml), [config/rules.yaml](config/rules.yaml), [config/pacer.yaml](config/pacer.yaml), [config/doc_types.yaml](config/doc_types.yaml), [config/sol_proposed.yaml](config/sol_proposed.yaml).
- Golden cases: `tests/golden/cases/` holds 0 files; cases are "Hand-verified, written by Brandon. CODEOWNERS-protected" — [tests/golden/README.md](tests/golden/README.md).
- Workflows: `ci.yml` (lint, types, noai, secrets, hygiene, workflows, audit, test+coverage), `lake.yml` (cron every 6 h), `refresh.yml` (cron every 2 h: append polls, listing snapshots, weekly rebuilds), `nightly.yml` (08:41 UTC health + health_history alerts), `discovery.yml` (Mondays), `match.yml` (manual `workflow_dispatch` only, uploads derived outputs to storage; needs `SUPABASE_SECRET_KEY`) — [.github/workflows/](.github/workflows/). Inferred: no workflow runs score, queries, leads, changes, sale_watch or rollup on a schedule (none of those module names appear in the workflow grep).

## 1. Who is the debtor (identity resolution, people/entity merge, registries, officers)

### Takeaway
Deterministic, exact-key identity resolution is built and running (name_key / org_name / addr_key rules, people merge, business-registry officer joins), but the fuzzy-match parameters in `rules.yaml` are null and unused, registries cover only 8 states (7 wired into match runs), and there are zero golden cases to validate against.

### Cited Findings
- Debtors = debtor parties of lien/judgment instruments; owners = parcel-snapshot owner parties; keys `name_key` (sorted name words, person needs >= 2 words, last name alone never matches), `suffix_key` (JR/SR mismatch refuses), `org_name`, `addr_key` (street + ZIP5, USPS suffix/direction normalization, "approved by the project owner 2026-11-22"), `town_key` (CT) — [src/equity/matching/resolve.py](src/equity/matching/resolve.py) docstring.
- Rules strongest first: `person_name_address` auto, `org_name_address` auto, `org_name_zip` auto, `person_name_zip` review, `person_name_initial_address` review (owner-approved 2026-11-22), `lien_names_parcel` auto (34 runs use `parcel_on_lien`), `org_name_county` review, `person_name_street_town`/`org_name_street_town` auto (CT only, owner-approved 2026-11-22; `street_town` set in 4 runs) — [src/equity/matching/resolve.py](src/equity/matching/resolve.py).
- People merge: `PEOPLE_SQL` groups debtor parties into one person by identity key (`org:<name>|<addr or zip>` or `person:<name_key>|<addr or zip>`) plus any auto-matched owner party, connected-components style; output `people.parquet` (open judgments, open amount, matched parcels per person) — [src/equity/matching/resolve.py](src/equity/matching/resolve.py) lines 423-460.
- Org classification never guesses a person; names without org markers are 'unknown' — [src/equity/matching/orgs.py](src/equity/matching/orgs.py).
- Business registries: exact org-key joins, outputs `owner_companies`, `company_people`, `debtor_companies` (rules `org_name_registry` auto, `person_officer_address` auto, `person_officer_zip` review), `debtor_company_parcels`; name-history (e.g. `ny.sos.name_history`) keys former/assumed names — [src/equity/matching/entities.py](src/equity/matching/entities.py).
- Registry adapters: `co.sos.business`, `ct.sos.business`, `dc.dlcp.business`, `ia.sos.business`, `ny.sos.business`, `ny.sos.name_history`, `or.sos.business`, `pa.dos.business`, `ri.sos.business` (8 states) — registry import; gaps table "Business registry 8 of 8 statewide" — [docs/gaps.md](docs/gaps.md).
- Match runs with `registries`: NY, PA-ALLEGHENY, CT, CO, IA, OR, DC (7). RI has a registry but no match run ("RI ... Match runs —") — [src/equity/matching/resolve.py](src/equity/matching/resolve.py) STATES; [docs/gaps.md](docs/gaps.md).
- Other officer/entity-people sources registered: `us.irs.990_officers`, `us.sec.insiders`, `us.sec.form_d`, `us.senate.lda_*`, `us.fmcsa.carrier_census`, notaries (CO/DE/OR/TX), 128 license configs — registry import. Inferred: these are loaded into the lake but none appears in a match run's `registries` list.
- Most other registries are "paid or restricted (GA, KY, WV, VA, WA, IN, OK, MN, NC, TX SOS). Florida Sunbiz is the large free one left" — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md).
- Sunbiz uses a published shared SFTP password; "Whether an SFTP login with a password the state publishes for everyone counts against the project's no-login rule" is an open legal/owner decision — [reports/Legal reads needed.md](reports/Legal%20reads%20needed.md).
- `rules.yaml` `matching.name_similarity_cutoff: null` ("proposed starting value 92, review after gold cases") and `min_corroborating_signals: null` ("proposed 1") — [config/rules.yaml](config/rules.yaml). Grep finds no code reading these two keys; resolve.py says "no fuzzy scores".
- Local counts-only NY summary: 4,631,183 debtor parties, 4,859,349 owner parties, 978,926 debtors auto-matched, 55,887 review-only; matches by rule org_name_address 485,756, org_name_zip 436,644, person_name_address 342,567, person_name_zip 189,569 — `data/derived/ny/summary.json` (local, dated 2026-11-22).
- Local `summary_by_state.json` (rollup) covers az-cochise, co, ct, md-baltimore, mi-wayne (and more); e.g. CT 515,461 debtor parties, 27,387 auto, 26,373 debtors with company parcels auto; CO 334,350 / 7,247 auto / 6,388 review — `data/derived/summary_by_state.json` (local).

### Inferences
- The two `rules.yaml` matching nulls are latent: the shipped matcher is exact-key only, so these only matter if a fuzzy rule is added. Any such rule change needs owner approval ([approval]; `rules.yaml` is CODEOWNERS-protected).
- People merge is name+address/ZIP based; the same human at two unrelated addresses stays two people unless an auto owner-match ties them.

### Gaps
- No DOB/SSN-style identifiers in debtor sources; voter files carry DOB/birth year but are not wired into matching (see Q11).
- Zero golden cases, so no measured precision/recall exists in the repo.

## 2. Alive? In bankruptcy (automatic stay / discharge)?

### Takeaway
Bankruptcy screening is built (name-only, always `review`) from 102 free CM/ECF RSS feeds polled every 2 hours; there is no historical backfill and no deceased-debtor source at all.

### Cited Findings
- `bankruptcy.py`: matches person `name_key` (>= 2 words) or `org_name_norm` to bankruptcy debtors within the state; every flag is `review`; status 'dismissed' / 'discharged' / 'open' from docket text seen since polling began; output `bankruptcy_flags` — [src/equity/matching/bankruptcy.py](src/equity/matching/bankruptcy.py).
- 102 `*.rss` adapters registered; `config/courts.yaml` enabled list covers bankruptcy and district courts; robots-disallowed or dead feeds listed (e.g. ohnd, nyed, txnd, canb, pamb, kyeb, mdb, utb, nmb, ilnb disallow; txsd/txsb 404; mob no answer; nywb titles don't parse) — [config/courts.yaml](config/courts.yaml).
- Feeds hold about a day, polled every 2 h in `append` mode — [config/refresh.yaml](config/refresh.yaml).
- `docs/gaps.md`: bankruptcy court feeds in 47 states; none for AR, MD, NM, UT (all four's bankruptcy feeds disallowed by robots) — [docs/gaps.md](docs/gaps.md).
- CourtListener quarterly dockets bulk (5.1 GB) is listed as free-but-not-built backfill; "it cannot prove a debtor has no case" — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md). CourtListener licence is on "Hold" — [reports/Data source gap analysis.md](reports/Data%20source%20gap%20analysis.md).
- PACER: guard built (`Budget.authorize()`, ledger at `data/private/pacer_ledger.jsonl`) but "No PACER client exists yet"; `quarterly_ceiling: null` refuses every request — [src/equity/pacer.py](src/equity/pacer.py), [config/pacer.yaml](config/pacer.yaml). **[owner]**
- Scoring has `bankruptcy_open` and `bankruptcy_discharged` penalty factors, weights null — [config/scoring.yaml](config/scoring.yaml). Saved queries support `exclude_bankruptcy` — [config/queries.example.yaml](config/queries.example.yaml).
- Deceased: "no free compliant source. The SSA DMF is restricted (42 USC 1306c), the NTIS LADMF is paid and needs certification ... Handle these as per-case checks through PACER and probate" — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md). Grep of `src/` for deceased/death/probate finds no matching logic.
- Schema has `bankruptcy`, `court_case`, `docket_entry` tables — `src/equity/schema/migrations/`.

### Inferences
- A debtor with a pre-polling bankruptcy (before RSS polling began, ~2026-11) is invisible; "open" status may be wrong for cases first seen mid-way (docstring says so).
- "Alive?" is fully unanswered by code: **[missing]**, and the repo's own position is per-case manual checks.

### Gaps
- No CourtListener backfill, no FJC bankruptcy IDB adapter found in the registry (the 2026-11-23 report recommended the IDB's Schedule A totals; Inferred not built since no `us.fjc.*bankruptcy*` id is registered).

## 3. What judgments/liens/debts, amounts, status (released/satisfied)

### Takeaway
Debt lists are broad (34 states, 14 debt kinds, 317 lien configs) and status handling exists (RELEASE instruments, `(satisfied)` doc types, `satisfied` judgment events), but private court money judgments with free bulk exist only in TX and FL, and 20 states have no debt list at all.

### Cited Findings
- 14 debt kinds: court_judgment, recorded_judgment_or_lien, administrative_judgment, administrative_order, tax_warrant, tax_lien, tax_delinquency, code_enforcement_charge, code_enforcement_lien, statutory_lien, foreclosure (counted, not added to open amounts), housing_court_case, eviction, charged_off_loan; every debtor/court/writ source of a match run must be mapped (test) — [config/debt_kinds.yaml](config/debt_kinds.yaml).
- Court judgment sources: `us.fjc.idb.civil_judgments`, `us.fjc.idb.direct.civil_judgments`, `us.epa.echo.judicial_cases`, `tx.harris.jp.civil_judgments`, `tx.harris.district.civil_judgments`, `tx.harris.tax_judgments`, `tx.tceq.civil_judgments`, `fl.hillsborough.civil.cases`, `fl.hillsborough.garnishment`, `fl.citrus.civil` — [config/debt_kinds.yaml](config/debt_kinds.yaml). The three federal sources are in 68 of 70 match runs' `courts` — resolve.py STATES.
- FJC IDB: keeps plaintiff-won monetary judgments with an amount; names cut at ~30 chars; people are surnames only — [src/equity/adapters/federal/fjc_idb.py](src/equity/adapters/federal/fjc_idb.py), [src/equity/matching/resolve.py](src/equity/matching/resolve.py).
- Tax warrants: NY (`ny.dtf.tax_warrants`, `ny.dtf.child_support_warrants`), FL (`fl.dor.tax_warrants`); NY and FL each list tax_warrant sources — [docs/gaps.md](docs/gaps.md), resolve.py STATES['NY'], ['FL'].
- Recorder judgment/lien indexes: ACRIS real/personal (incl. federal tax liens, UCC), Hillsborough/Hernando/Putnam OR, `ct.sots.liens` — [config/debt_kinds.yaml](config/debt_kinds.yaml), [src/equity/adapters/ny/acris.py](src/equity/adapters/ny/acris.py).
- Charged-off loans: `us.sba.chargeoffs` (7(a)/504 CHGOFF rows, gross charge-off amount) and `us.sba.ppp_chargeoffs` registered — [src/equity/adapters/federal/sba_chargeoffs.py](src/equity/adapters/federal/sba_chargeoffs.py), registry import.
- Status: lien sources turn a satisfaction date into a RELEASE instrument that `releases` the lien — [src/equity/adapters/liens.py](src/equity/adapters/liens.py); resolve marks `released` when a RELEASE refers to it or `doc_type_raw LIKE '%(satisfied)'`; court debtors: "A 'satisfied' judgment event releases it"; open_amount excludes released and LIS_PENDENS — [src/equity/matching/resolve.py](src/equity/matching/resolve.py) lines 259-323, 460-473. Terminating ref types `releases`, `satisfies_judgment`, parcel-scoped `partial_release` — [config/doc_types.yaml](config/doc_types.yaml) (**[approval]**: "TODO(Brandon): confirm every list", CODEOWNERS).
- States with any debt list: 34; court judgments: 2 (TX, FL); none in AL, AR, HI, IA... (list in report: AL, AR, HI, IA, ID, KY, MA, ME, MT, ND, NH, NM, NV, OK, OR, RI, SD, TN, WA, WY) — [docs/gaps.md](docs/gaps.md), [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md). Note: gaps.md table shows IA has tax_lien (1) and OR statutory_lien (1), conflicting with the report's "none in 20 states" list for IA/OR (report scanned main 9fd9114; gaps.md is newer).
- "Private court money judgments: only TX (Harris JP; Travis tax suits) and FL (Hillsborough) have free bulk. Elsewhere this needs the records-request programme" — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md).
- 87 county delinquent-tax/certificate lists registered (71 delinquency, 16 tax-lien) as of that scan — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md).
- Writ sources: FL Hillsborough garnishment defendants join as judgment debtors "(amount unpublished)" — resolve.py docstring.

### Inferences
- For FJC judgments, "status" is amount received at termination; post-judgment satisfaction is not tracked (no satisfaction source for federal judgments found).
- Amounts are face/principal amounts; no post-judgment interest computation exists (interest rates are only in `sol_proposed.yaml`, unread by code).

### Gaps
- No per-state private judgment docket outside TX/FL (Ohio certificates of judgment, PA prothonotary, TX abstracts, GA GSCCCA are paid or request-only per the 2026-11-23 report).

## 4. Still enforceable (SOL / renewal; config/sol.yaml)

### Takeaway
Fully blocked on the owner: `sol.yaml` is 100% null (51 states, 357 null fields), it is CODEOWNERS-protected, and even when filled the scorer only uses `judgment_enforceable_years` as a flat number because `people` lacks the oldest-debt date; `lien_years`, renewal and priority fields are read by no code.

### Cited Findings
- Header: "Judgment enforceability by state. Filled in by Brandon, never by code or by Claude. Every value starts as null. Rules that need a null value refuse to run" — fields judgment_enforceable_years, lien_years, renewable, renewal_years, renewal_keeps_priority, statute, confirmed_by — [config/sol.yaml](config/sol.yaml). **[owner] [approval]**
- Counted: 51 states, 357 nulls of 358 leaves, 0 states with any value — PyYAML parse of [config/sol.yaml](config/sol.yaml).
- `sol_proposed.yaml`: research proposals per state (lien_created_by R/D/X, duration_and_renewal, homestead, post_judgment_interest), sourced to the White and Williams chart (rev. 2020-01-20) and NCLC 2025; "NOT confirmed ... Nothing in code reads this file"; every state `verified: false` — [config/sol_proposed.yaml](config/sol_proposed.yaml).
- Score: `sol_years_left` = `judgment_enforceable_years` of the run's state or NULL; code comment "Years left needs the oldest open debt date, which people does not carry yet: until it does, the factor is the period itself" — [src/equity/rules/score.py](src/equity/rules/score.py) lines 37-38, 98-105.
- Grep for `lien_years`/`renew`/`expir` in `src/equity` finds no SOL logic (only FCC/FAA/ATF license fields) — repo grep.
- "No judgment is ever flagged expired or near expiry, and `sol_years_left` is never scored ... No free machine-readable table exists" — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md).

### Inferences
- Even after Brandon fills sol.yaml, a code change is needed (judgment date per person -> years left; renewal handling) before enforceability is actually computed. **[code]** after **[owner]**.

### Gaps
- No source tracks judgment renewals/revivals filings.

## 5. What real property do they own, directly and via companies

### Takeaway
Strongest layer: parcels in 51 of 51 states (owner names mapped in 50), matched by exact rules, with company-held parcels via registries in 7 runs; limits are CA/NJ/HI owner-name redaction, county-by-county coverage in ~20 states, and several licence-tagged layers.

### Cited Findings
- Parcels: 51 of 51 states, 31 statewide; owner names mapped 50 (30 statewide with owners); property address 46; land use 44 — [docs/gaps.md](docs/gaps.md). "With owner names and values: 43" — [docs/coverage.md](docs/coverage.md).
- 277 `*.parcels` adapters — registry import.
- Owner-name holes: CA counties redact owner names; NJ owner names redacted (Daniel's Law); HI statewide layer zoning only (Honolulu owners adapter exists); RI statewide no owner — [docs/coverage.md](docs/coverage.md). "Owner names: only HI is missing statewide" — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md).
- Matching rules and outputs (`matches.parquet`, `debtor_summary.parquet`, `people.parquet`) — [src/equity/matching/resolve.py](src/equity/matching/resolve.py).
- Via companies: `owner_companies`, `debtor_companies`, `debtor_company_parcels` — [src/equity/matching/entities.py](src/equity/matching/entities.py); only runs with registries (7) produce these.
- Condo units: `ny.nyc.dof.condo_units` parcel_link joins unit lots to billing lots (NY only) — resolve.py STATES['NY'], [src/equity/matching/equity.py](src/equity/matching/equity.py).
- Commercial lead list: owners of commercial/mixed/industrial parcels with auto-linked open debt; land use via NY property class, NYC land use codes, description keywords — [src/equity/matching/leads.py](src/equity/matching/leads.py).
- Use restrictions tagged per source (e.g. `internal_use_only`, `no_redistribution`, `no_commercial_name_address_lists` for IN, WA) — [docs/coverage.md](docs/coverage.md). TN `tn.owners.parcels` "loaded for internal use on the owner's decision, 2026-11-25" — [docs/coverage.md](docs/coverage.md); note [reports/Legal reads needed.md](reports/Legal%20reads%20needed.md) still lists it "Not loaded" (stale vs coverage.md).
- Legal reads pending: WA RCW 42.56.070(9), IN IC 5-14-3-3(f), AZ A.R.S. 39-121.03(D), MT MCA 2-6-1017, Genesee MI no-convey clause, King County sales file (not loaded), Maricopa unsold lien parcels (not loaded) — [reports/Legal reads needed.md](reports/Legal%20reads%20needed.md). **[legal]**

### Inferences
- Coverage is "parcel-layer" ownership (current roll), not chain of title; historical ownership exists only where deed sources exist (Q9).

### Gaps
- No vehicle/aircraft/vessel ownership in matching (FAA adapter file exists; task list shows "FAA aircraft registry adapter" pending; USCG individual owners removed 2017 per the gap report).

## 6. What is it worth today (assessed values, FHFA HPI, sales)

### Takeaway
Value = latest `coalesce(appraised_total, assessed_value)` per parcel; the FHFA ZIP5 HPI adapter (`us.fhfa.hpi_zip5`) is now built and refreshed monthly but is not used in any estimate ("a separate, owner-approved step"); sales files exist but are used only for transfer detection.

### Cited Findings
- `parcel_value` = `arg_max(coalesce(appraised_total, assessed_value), tax_year)` — [src/equity/matching/resolve.py](src/equity/matching/resolve.py) lines 555-556.
- FHFA adapter: annual ZIP5 HPI (~690,000 rows), loads `house_price_index` (geo_level 'zip5'); "using it in equity estimates is a separate, owner-approved step"; read with stdlib XML (no pyproject change) — [src/equity/adapters/federal/fhfa_hpi.py](src/equity/adapters/federal/fhfa_hpi.py); migration `V0018__house_price_index.sql`; refresh every 720 h rebuild — [config/refresh.yaml](config/refresh.yaml). Commit 5ab35fc "FHFA ZIP5 house price index, read with the standard library".
- Grep: no `hpi`/`fhfa` reference in `src/equity/matching` or `src/equity/rules` — repo grep. **[owner/approval]** to wire it in.
- Contradiction: [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md) lists FHFA HPI as #1 "Free sources not yet built" and says it needs an XLSX dependency (a pyproject change); the code since built it without that dependency (the report predates it).
- `rules.yaml` `valuation.assessed_ratio.WV: null` ("statute says 60%? confirm and cite") — [config/rules.yaml](config/rules.yaml); grep finds no code reading it. **[owner]**
- "Values" mapped per state in gaps.md "Fields mapped" column (e.g. DE, ME, NH, NJ, KS have no value) — [docs/gaps.md](docs/gaps.md), [docs/coverage.md](docs/coverage.md).
- Sales sources registered: 12 `*.property_sales`, 5 `*.parcel_sales`, 5 `*.last_deed`, 2 `*.last_sale`, `in.dlgf.sales_disclosures` (Indiana SDF 2008-present with price), `il.cook.sales`, `md.sdat.transfers_*` — registry import, [src/equity/adapters/indiana_sdf.py](src/equity/adapters/indiana_sdf.py).

### Inferences
- No comparable-sales valuation or sale-price-based value exists; sales prices are only consideration on DEED instruments used by transfers.py.
- Tax-year staleness is not adjusted today; equity is stated in assessed/appraised dollars.

### Gaps
- No AVM, no county-level HPI fallback, no assessed-to-market ratio table (only the WV null placeholder).

## 7. Senior debt (mortgages/satisfactions; tax liens; equity.py)

### Takeaway
Mortgage netting (`equity.py`) is built but wired into exactly one match run (NY, ACRIS); recorder/deed data in PA (Philadelphia RTT), FL, IL, MD, IN is used only for transfer flags, so equity is gross parcel value everywhere else.

### Cited Findings
- equity.py: mortgage paid when `paid_ref` (release cites it), `paid_payoff` (same-lot release naming a borrower), `paid_sale` (later deed to non-borrowers); else open; amounts are original secured amounts so "open debt is an upper bound and equity a lower bound"; rules "chosen by the project owner (2026-11-22)" — [src/equity/matching/equity.py](src/equity/matching/equity.py).
- Only `STATES['NY']` has a `mortgages` key (`ny.nyc.acris.real`); 1 of 70 runs — resolve.py STATES (counted).
- Local NY outputs: mortgage lots open 31,772, paid_payoff 3,830, paid_ref 542, paid_sale 962; 923,322 auto debtors with positive equity — `data/derived/ny/summary.json` (local, 2026-11-22).
- About 3% of ACRIS satisfactions cite the mortgage they pay — [src/equity/matching/equity.py](src/equity/matching/equity.py).
- Recorded deeds/mortgages in 6 states per gaps.md (FL Hernando/Hillsborough/Putnam OR, IL Cook recorder 2011-2015 + PTAX, IN SDF, MD SDAT, NY ACRIS, PA Philadelphia RTT), "0" statewide — [docs/gaps.md](docs/gaps.md). Philadelphia RTT includes mortgages, assignments, satisfactions — [src/equity/adapters/pa/philadelphia_rtt.py](src/equity/adapters/pa/philadelphia_rtt.py); STATES['PA'] uses it only under `deeds`.
- "In the other 46 states, `equity_est` cannot net out senior debt"; no free bulk recorder index for King, Miami-Dade, Cook; Maricopa recorder JSON API (no amounts, terms unconfirmed) — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md).
- Lien priority: `rules.yaml priority.method: recording_date`, `same_day_tiebreak: null` — [config/rules.yaml](config/rules.yaml). Grep: no code reads `same_day_tiebreak`; `src/equity/rules/` holds only `score.py` and `queries.py` (no priority module) — repo ls.
- Tax liens/delinquencies on the parcel are loaded as debts (tax_lien, tax_delinquency kinds) and `lien_names_parcel` links them to parcels — [config/debt_kinds.yaml](config/debt_kinds.yaml), resolve.py.

### Inferences
- Adding `mortgages: ['pa.philadelphia.rtt']` (and FL OR sources) to their runs looks like a code/config change rather than new data, but would need the paid-rule logic validated on those sources (Inferred; not stated in repo). PA's RTT row-per-property layout and FL OR doc codes may differ from ACRIS.
- Property-tax delinquency as senior debt is counted as the debtor's "open amount", not subtracted from the parcel's equity (Inferred from equity.py only netting mortgages).

### Gaps
- No lien-stack/priority engine (Phase 4 per `src/equity/rules/__init__.py` docstring "lien priority, equity, judgment age, transfer flags" — only score/queries exist).

## 8. Exemptions protecting it (homestead)

### Takeaway
Only a homestead boolean exists (schema column, mapped in 13 states); no exemption amounts are encoded and nothing in matching or scoring reads the flag.

### Cited Findings
- `parcel_assessment.homestead BOOLEAN` added in V0012; comment: legal effect (e.g. Florida's exemption from forced sale) is not encoded there — `src/equity/schema/migrations/V0012__situs_owner_type_homestead.sql`.
- Homestead mapped: 13 states — [docs/gaps.md](docs/gaps.md) (e.g. CA, DC, FL, IA, ID, LA, MI, MN, OH, OK, PA, SC, SD in the "Fields mapped" column).
- Adapters setting it: `state_parcels.parse_homestead` (positive amount -> True), Allegheny `HOMESTEADFLAG == 'HOM'` — [src/equity/adapters/state_parcels.py](src/equity/adapters/state_parcels.py), [src/equity/adapters/pa/allegheny_assessments.py](src/equity/adapters/pa/allegheny_assessments.py).
- Grep: `homestead` appears in no file under `src/equity/matching` or `src/equity/rules` — repo grep.
- Homestead dollar amounts per state exist only as unverified strings in `sol_proposed.yaml` (e.g. AL "$18,800 (6-10-2)", AK "$72,900", AZ "$425,200") from NCLC 2025 — [config/sol_proposed.yaml](config/sol_proposed.yaml).
- "Equity is gross parcel value, so equity a homestead protects is counted as reachable ... No free maintained table exists. Encode each state's exemption statute; 11 USC 522(d) amounts change every 3 years" — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md). **[owner]**

### Inferences
- Needs both an owner-confirmed exemption table (no config file exists for it yet; sol.yaml has no homestead field) and code to subtract it. **[missing]**

### Gaps
- Other exemptions (tenancy by the entirety, wildcard, senior/disabled) are not represented anywhere found.

## 9. Transferred away after the debt (transfers.py, nominee LLCs)

### Takeaway
Built: post-debt deed detection with nominee-LLC check in 16 match runs with deed sources; the `nominal` flag stays NULL until Brandon sets `nominal_consideration_max`, and the related-party toggles are null.

### Cited Findings
- Flags: `on_matched_parcel` auto, `same_county` review, `nominal`, `grantee_org`, `grantee_same_name`, `nominee_llc` (registry role holder with debtor's name); "leads for a fraudulent-transfer review (e.g. UVTA badges of fraud), not findings" — [src/equity/matching/transfers.py](src/equity/matching/transfers.py).
- `nominal` reads `rules.yaml transfer_flags.nominal_consideration_max`; "NULL while that threshold is not set" — [src/equity/matching/transfers.py](src/equity/matching/transfers.py) lines 15-45; value null — [config/rules.yaml](config/rules.yaml). **[owner] [approval]**
- Also null: `nominal_fraction_of_appraised`, `related_party_rules.same_surname`, `same_mailing_address`, `debtor_is_member_or_agent_of_grantee_llc` — [config/rules.yaml](config/rules.yaml). Grep: none read by code (only nominal_consideration_max is).
- Runs with `deeds`: NY, CT, MD-BALTIMORE, CO, MI-DETROIT, FL, PA, VT, IL-COOK, IN-STJOSEPH, MN, AL, TN, VA-COUNTIES, OH-COUNTIES, IN (16 of 70) — resolve.py STATES. `config/deeds/` has 40 files.
- Scoring factors `transfers_after_debt`, `nominee_transfer` (weights null) — [config/scoring.yaml](config/scoring.yaml). Query filter `max_transfers_after_debt` — [config/queries.example.yaml](config/queries.example.yaml).

### Inferences
- `nominee_llc` only fires where the run has registries and deeds both: NY, CT, CO (intersection of the two lists; Inferred).

### Gaps
- King County sales file (buyer/seller every sale) not loaded pending legal read — [reports/Legal reads needed.md](reports/Legal%20reads%20needed.md).

## 10. About to be sold (tax/sheriff/foreclosure lists; listing mode; sale_watch.py)

### Takeaway
Built end to end: ~64 listing-mode sale sources snapshotted daily, `refresh listings` builds sale history, and `sale_watch.py` joins auto-matched parcels to listings and foreclosures with first/last seen.

### Cited Findings
- `refresh.yaml` listing-mode rules: one rule with 62 patterns (tax sales, sheriff sales incl. `nj.*.sheriff_sales` CivilView, forfeited land, land banks, HUD REO, excess proceeds, vacant lists), plus `ga.fulton.superior_pending_civil` and `wv.statewide.delinquent`; all every 24 h — [config/refresh.yaml](config/refresh.yaml) (counted).
- Registered: 24 `*.sheriff_sales`, 9 `*.tax_sale`, 5 `*.tax_lien_sale`, 5 `*.land_bank`, 3 `*.foreclosures`, 3 `*.forfeited_land_sale` etc. — registry import.
- sale_watch: listing sources + `foreclosure`-kind sources; adds first_seen / last_seen / on_latest from `sale_listing_history`; uses only auto-matched parcels — [src/equity/matching/sale_watch.py](src/equity/matching/sale_watch.py).
- refresh.yml runs `equity.refresh listings` every 2 h cycle and pushes `data/derived/sale_listings` — [.github/workflows/refresh.yml](.github/workflows/refresh.yml).
- HUD loan sales: `us.federalregister.loan_sales`, "109 notices since 2000, refreshed daily"; loan files need HUD-9611 qualification — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md). **[owner]**
- Auction platforms (RealAuction, LienHub, GovEase, Bid4Assets...) unusable/blocked — "do not work around the blocks" — [reports/Data source gap analysis.md](reports/Data%20source%20gap%20analysis.md).

### Inferences
- Local `data/derived/ny/sale_watch.parquet` is 380 bytes (Inferred: empty or near-empty for NY, as NY has few listing sources).
- sale_watch is not in any scheduled workflow (Inferred from workflow grep); it runs by hand.

### Gaps
- No surplus-proceeds claim tracker beyond a few excess-funds lists (ga.dekalb.excess_funds, nv.washoe.excess_proceeds).

## 11. How to reach them (addresses, geocode.py, voter/person lists, contact)

### Takeaway
Addresses come from debt/parcel sources (owner mailing address, situs) and the Census geocoder standardizes them; locate sources (2 voter files, 22 person lists) are loaded but not used by matching, and contact-use is restricted for many sources; no phone/email, NCOA or skip-trace exists.

### Cited Findings
- geocode.py: Census batch geocoder, only address fields sent ("no name or other field is ever sent"), 10,000 per batch, output `us.census.geocoder/address_geocode`; "Nothing here changes a match" — [src/equity/geocode.py](src/equity/geocode.py).
- review_geo.py labels review pairs `same_segment`, `same_zip`, `multi_unit`; local NY: 55,887 review debtors, 51,223 geocoded, 10,075 same_segment (7,082 single-unit, 2,993 multi-unit) — [src/equity/matching/review_geo.py](src/equity/matching/review_geo.py); `data/derived/ny/review_geo_summary.json` (local). Promoting same_segment to auto would be a rule change **[approval]**.
- Voter files registered: `nc.sbe.voter_file`, `co.boulder.voter_file`; Ohio joins once a hand-saved fixture exists; 8 jurisdictions (AK, AR, CO, DC, FL, MI, MS, WI) are hand-delivered request routes, "Nothing below was submitted or paid" — [src/equity/adapters/voter_files.py](src/equity/adapters/voter_files.py), [docs/voter_file_requests.md](docs/voter_file_requests.md). Voter adapters drop phone, e-mail, history. The purpose statement promises no "solicitation, mailing lists, telephone or e-mail contact" use — [docs/voter_file_requests.md](docs/voter_file_requests.md).
- Person lists (22 configs: unclaimed property CA/MO/NJ/OH/OK/RI/TX, uncashed checks, rental registries, HPD registration contacts, Cincinnati permit owner contacts, KC LLC affidavits) — "the locate sources for states whose voter files may not be used commercially" — [src/equity/adapters/person_lists.py](src/equity/adapters/person_lists.py), `config/person_lists/`.
- Grep: no file in `src/equity/matching` or `src/equity/rules` references voter, person_list or unclaimed — repo grep. **[missing]** wiring.
- Mailing-address flags: `no_mailing_list` (ID, KS, MT), `no_commercial_name_address_lists` (IN, WA) — [docs/coverage.md](docs/coverage.md). **[legal]**
- NCOA is licensed; no change-of-address source — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md).

### Inferences
- "Contact data" for a debtor today = debtor address on the lien + owner mailing address on the roll + registry officer addresses (entities.py `company_people`).

### Gaps
- No phone/e-mail source (deliberately dropped); no skip-trace vendor integration.

## 12. Decision layer (scoring, saved queries, leads, changes, rollup, review queue, PACER guard)

### Takeaway
All decision-layer modules exist as code, but the ranking is inert: every scoring weight is null and tiers empty, buyer queries live in a git-ignored folder that only has a README, PACER is refused until a ceiling is set, and none of these run on a schedule.

### Cited Findings
- score.py: writes factors per person always, score and tier "only when every weight in config/scoring.yaml is set"; reports missing params in `score_report.json` — [src/equity/rules/score.py](src/equity/rules/score.py). 11 null factors (open_amount, parcel_value, parcels, court_judgment, charged_off_loan, tax_debt, bankruptcy_open, bankruptcy_discharged, transfers_after_debt, nominee_transfer, sol_years_left), `tiers: []` — [config/scoring.yaml](config/scoring.yaml). **[owner]** (not CODEOWNERS-listed).
- queries.py: runs every `config/private/queries/*.yaml`, writes dated parquet and `new_since_last.parquet` — [src/equity/rules/queries.py](src/equity/rules/queries.py). `config/private/` contains only README.md (no buyer.yaml, no queries/) — repo ls. **[owner]**
- leads.py commercial lead list — [src/equity/matching/leads.py](src/equity/matching/leads.py).
- changes.py: `new_owner`, `open_amount_up`, `new_parcel`, `new_sale_event` vs. latest earlier dated history; local NY reports `first_run: true`, all zero — [src/equity/matching/changes.py](src/equity/matching/changes.py), `data/derived/ny/changes_summary.json` (local).
- rollup.py: `review_queue_all.parquet`, per-state CSV, `summary_by_state.json` (counts only) — [src/equity/matching/rollup.py](src/equity/matching/rollup.py).
- review.py: categories middle_initial, spelling_only, same_number, po_box, different; "Nothing here accepts or rejects a match" — [src/equity/matching/review.py](src/equity/matching/review.py). Schema has a `review_queue` table — migrations. No UI or accept/reject workflow found.
- PACER guard: `Budget.authorize()`, fees per_page 0.10, document_cap 3.00, quarterly_waiver 30.00, `quarterly_ceiling: null` (research suggests ~28.00), alert_fraction 0.8 — [src/equity/pacer.py](src/equity/pacer.py), [config/pacer.yaml](config/pacer.yaml). **[owner]**
- Phase 5 reads `config/private/buyer.yaml` (target_states, min_judgment_amount, min_judgment_age_years, judgment_kind) "if present" — [config/private/README.md](config/private/README.md).
- Recommended order in repo: owner fills sol.yaml, then scoring weights/tiers; decide HUD qualification and paid feed pricing; approve Sunbiz login and XLSX dependency; build CourtListener backfill and Census geocoding — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md).

### Inferences
- Golden test runner "runs every case through the Phase 5 query"; with 0 cases, there is no regression check on end-to-end debtor answers — [tests/golden/README.md](tests/golden/README.md).
- match.yml is manual-only, so derived outputs refresh only when someone dispatches it or runs locally (Inferred).

### Gaps
- No deal-flow ingestion from judgment marketplaces ("No US judgment marketplace has an API") — [reports/Gaps and deal flow.md](reports/Gaps%20and%20deal%20flow.md).
- Some repo reports are stale against code: FHFA (built vs "not built"), TN owners (loaded vs "not loaded"), Census geocoder (built vs "not built" item #4).
