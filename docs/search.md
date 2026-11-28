# Search and queries

Three pieces, all deterministic (fixed rules, no models), all under permissive licenses:

| Piece | What it is | License |
|---|---|---|
| `equity.search_index` | One local DuckDB file (`data/search_index.duckdb`; not `equity.lake`'s views catalog) indexing the lake: names, owners, parcels, values, documents, cases, businesses, addresses | this repo |
| `equity.search` | Name and address search over the catalog, every hit scored by a named rule and listed with its links | this repo |
| `equity-search` MCP server (`.mcp.json`) | [mcp-server-motherduck](https://github.com/motherduckdb/mcp-server-motherduck) 1.1.1 over the search index, read-only, so any Claude session can run SQL against it | MIT |

## Build the catalog

```bash
uv run python -m equity.search_index build --remote          # every built source in object storage
uv run python -m equity.search_index build                   # or the local data/lake
uv run python -m equity.search_index build --remote --states OH NY --workers 8
uv run python -m equity.search_index compact                 # sort the lookup tables (faster)
uv run python -m equity.search_index compact --only addresses # re-sort one table
uv run python -m equity.search_index status
uv run python -m equity.search_index export            # share: sorted Parquet parts in storage
uv run python -m equity.search_index pull              # another machine: load the shared index
uv run python -m equity.search_index refresh           # all of it, unattended: pull if missing,
                                                       # build, compact and export when changed
```

`export` writes every table, sorted by its lookup key, as zstd Parquet parts of at most 40 MB
under `_search_index/` in the lake bucket (the bucket takes 50 MB per object), with a manifest
of the source versions it holds, including the matcher tables (`m_*`). Each table's local copy
is deleted once uploaded, and `pull` loads one table at a time, so neither needs twice the
index's disk. `pull` downloads them and loads a fresh local index, so the
data and cross-linking sessions can search without rebuilding; a later `build --remote`
re-indexes only the sources that changed since the export.

`--workers` fetches that many sources at once (each into local Parquet of only the columns
the index needs, deleted after) while one writer indexes them: Delaware's 14 sources take
3.3 minutes with 8 workers, 8.5 serially.

**Size.** The index takes about 260 bytes per party name (Delaware: 818k names, 256 MB).
The whole lake has about 197 million party names, so a national index is roughly 50 GB:
build by state (`--states`) unless the machine has that much free disk.

A source is re-indexed only when its version changed (the `_state.json` bundle remotely, the
part markers locally), and sources gone from the lake are dropped, so `build` is cheap to
re-run. Each source is replaced in one transaction. The file (`data/search_index.duckdb`, git-ignored)
is written in DuckDB's v1.5 storage format so the MCP server, which pins its own DuckDB, can
open it.

## Search

```bash
uv run python -m equity.search "JOHN A SMITH" --state OH
uv run python -m equity.search "ACME HOLDINGS LLC" --kind org --json
uv run python -m equity.search --show <source_id>:<party_id>
uv run python -m equity.search --address "123 Main St" --zip 43215
uv run python -m equity.search --network <source_id>:<party_id> --hops 2
uv run python -m equity.search --parcel 39049-010-001234       # or the county's own id
uv run python -m equity.search --bench 60
```

`--parcel` shows each source's record of a parcel (situs, latest value, homestead), its
owners, and every document recorded against it with its parties (`instrument_parcels`:
deeds, mortgages, liens, lis pendens).

`--network` walks a party's links outward, breadth first: parcels and their other owners,
documents and their other parties, cases, businesses and their officers, parties at the same
address, and the same name in other sources. Edges are labelled (`owns`, `party_to:<role>`,
`in_case:<role>`, `role:<role>`, `same_address`, `same_name`); the last two are leads, not
established identity.

Names are compared on the matcher's `name_key` (upper-case words, punctuation and
JR/SR/AND/TR... dropped, de-duplicated, sorted), so "Smith, John A." and "JOHN A SMITH" are the
same key. Rules, best first:

| Rule | When | Score |
|---|---|---|
| `exact` | same name_key | 1.00 |
| `all_words` | every query word is in the name, plus 1–2 more | 0.95 / 0.90 |
| `typo` | same word count, every query word but one is in the name, and that one is one edit (a letter dropped, added, changed, or two swapped) from a name word; 4+ letters | 0.88 |
| `initial` | all query words but one are in the name, that one is an initial of a name word (or the reverse), and every full name word is accounted for | 0.85 |
| `sounds_like` | every query word is in the name or has the same Soundex code and Jaro-Winkler similarity of at least 0.80 with a name word (3+ letters), word counts within one | 0.82, less 0.03 for an extra name word |
| `similar` | each query word's best Jaro-Winkler match among the name's words, averaged, is at least 0.90, and the word counts differ by at most one | 0.80 × similarity |

Candidates come first from every name holding all the query's words in some form: the word,
an equivalent given name, an indexed word with the same Soundex code and Jaro-Winkler
similarity of at least 0.85 (`word_sounds`; American Soundex as a SQL macro), or an indexed word
one edit away (`word_edits`: every word of 4+ letters stored under itself and each one-letter
deletion of it, so a query word's own deletions meet it there; the symmetric-delete method,
implemented here in SQL). A dropped letter that changes the Soundex code (MAIA for MARIA) is
still found.
That list is not capped, so a typo in "ROBINSON" among 111,000 Robinsons still finds the right
one. Only when it finds fewer than 50 names does search add the capped lists: names with one of
the query's two rarest words, or a word that sounds like one of its two longest.
Registered businesses are searched alongside parties: their refs read
`<source_id>:business:<sos_id>` and `--show` lists officers, agents and members. Each hit lists
parcels owned (with the latest value), debts and amounts, documents, cases and business roles;
`--show` lists them in full with same-name parties in other sources. A same name in two sources
is a candidate, not a match: linking is the matcher's job (address and ZIP rules).

Address search standardizes the street with the matcher's `street_norm` (USPS Publication 28
words: STREET → ST and so on) and finds parcels at that situs and parties whose address it is,
including addresses kept as one unsplit line.

### Measured

`uv run python -m equity.search --bench 60` samples real indexed names, searches each as
written and with one typo (a letter dropped from the longest word), and reports how often the
sampled name and record are in the top 10. On the Delaware index (818k names), after `compact`:

| Query | Recall in top 10 | Median | 95th percentile |
|---|---|---|---|
| as written | 1.00 | 0.23 s | 0.55 s |
| one typo | 0.95 | 0.20 s | 0.42 s |

Before `compact` the median was 0.63 s: sorting the lookup tables lets DuckDB skip blocks.

On Ohio, Kentucky and Louisiana (81 sources, 13.5M names, 2.7 GB), 80 sampled names:

| Query | Name in top 10 | Record in top 10 | Median | 95th percentile |
|---|---|---|---|---|
| as written | 1.00 | 0.79 | 0.62 s | 1.18 s |
| one typo | 0.94 | 0.75 | 0.65 s | 1.15 s |

On 16 states (OH KY LA FL TX PA NC IL MI WI MN GA MD VA AZ CO: 457 sources, 152M names,
48.7 GB after `compact`), 60 sampled names:

| Query | Name in top 10 | Record in top 10 | Median | 95th percentile |
|---|---|---|---|---|
| as written | 1.00 | 0.82 | 1.00 s | 1.61 s |
| one typo | 0.98 | 0.78 | 0.83 s | 1.56 s |

Every built source (864 sources, all states, 272.7M names; 48 GB after `compact`), 60 sampled
names:

| Query | Name in top 10 | Record in top 10 | Median | 95th percentile |
|---|---|---|---|---|
| as written | 1.00 | 0.75 | 1.21 s | 2.64 s |
| one typo | 0.97 | 0.70 | 1.18 s | 2.25 s |

`--parcel` takes about 8 s at this size: `owners` is sorted by party (for name search), so a
parcel's owners are a scan; a fact sheet takes about 30 s.

Before the uncapped all-words candidates and `word_edits`, one-typo name recall at this size was
0.68 (a typo in a surname held by 100,000 names fell outside the capped lists), and fetching
every record of all 500 scored names put the median at 3.4 s; records are now fetched one score
tier at a time until the page is full.

Record recall is lower than name recall when many records share one name (a common name
can have hundreds): the right name comes back, and `--state` or `--kind` narrows it.

## What the index adds on top of names

- **The matcher's verdicts.** `build` also loads each state's matcher output
  (`data/derived/<state>/` or `derived/<state>/` in the bucket: matches, debtor_summary,
  people, person_of, bankruptcy_flags, transfer_flags, mortgage_status) into `m_*` tables. A
  hit then shows `matcher: auto lien_names_parcel` (decision and rule), its merged person and
  any bankruptcy flag; `--show` lists the links, the debtor summary (open amount, equity when
  the state's recorder data allows) and transfer flags. Name-only leads are still name-only.
- **Name flags.** Each printed name gets `name_flag`: `placeholder` (no real word: Ohio's
  statewide `39005 | <parcel id>`), `withheld`, `continued` (`... (CONT'D #1 OF #4)`),
  `government` (cities, counties, treasurers: usually the creditor) or `one_word`. Flagged
  names still come back in search (after clean ones) but never as leads.
- **Nicknames.** A query word is also tried as each equivalent given name (BOB <-> ROBERT;
  `equity/data/nicknames.csv`, Apache-2.0): rule `nickname`, score 0.90.
- **Business aliases.** `--show` on a business lists every other name filed under its id
  (former and assumed names from `ny.sos.name_history`).
- **History.** `value_history` keeps every tax year; `owner_history` keeps superseded owner
  snapshots. `--parcel <id> --as-of 2024-06-30` adds who owned it then: snapshot owners in
  force on that date and the grantees of the last deed recorded by then. Before the first
  snapshot and the first deed the answer is empty, not a guess.
- **Net equity.** Where the county has recorder data in the index, `parcel_equity` (stored
  by `compact`) is the latest value minus mortgages and deeds of trust recorded against the
  parcel that no recorded release points at (`instrument_refs`). A mortgage with no amount
  makes `equity_est` NULL (`principal_unknown`). Counties without recorder data get no row:
  senior debt there is unknown, not zero.

## Supplements: lake tables beside the core

`build` then loads lake tables the core leaves out into their own tables, per source, under
a version per table (`supplement_runs`, `SUPPLEMENT_VERSIONS`): adding or changing one reloads
only that table, and never re-indexes the core tables.

| Table | From | Shown in |
|---|---|---|
| `bankruptcies` | federal bankruptcy court feeds: chapter, petition, discharge, dismissal, conversion | `--show` cases |
| `judgment_terms` | judgment interest, costs, rate, the lien it was docketed as (rows with any of them) | `--show` cases |
| `docket_entries` | case docket text (FL counties, federal courts) | `--show` cases (count) |
| `tax_delinquencies` | delinquent-tax listings (WV statewide) | `--parcel` |
| `parcel_links` | splits, merges, condo units (HI, NYC) | `--parcel` |
| `value_parts` | land and building value, tax class | `--parcel` |
| `owner_types` | owner type where the source gives one (person, trust, LLC...) | `--parcel` |
| `house_prices` | FHFA house price index by ZIP and tract | `--parcel`: `house_price_index` scales the value from its tax year to the latest index year, labelled an estimate |
| `business_addresses` | a registered business's principal and mailing address ids | `--ring`: `registered_at_debtor_address` |
| `assessment_ratios` | NY and CT published assessment ratios (assessed / market) | `--parcel` for NY and CT, matched on the situs town name (`matched_on` says so) |

## Forensic tracing

`equity.forensic` gathers what a judgment-recovery investigator assembles, by fixed rules; it
lists facts and named signs and never concludes fraud, alter ego or identity:

| Command | What |
|---|---|
| `--stack <parcel> [--lien <instrument_uid>]` | every encumbrance on a parcel by recording date, released or open; for a lien, its rank, senior and junior items, and the equity behind it net of only senior debt (tax liens counted senior) |
| `--badges <ref>` | deeds out by the debtor's name from 180 days before the first debt, each with badges: same-name or name-word grantee, grantee organization, grantee run by the debtor (registry role), grantee at the debtor's address, no or nominal consideration (`rules.yaml` threshold, only when set), quitclaim, debtor still listed after, timing |
| `--ring <ref>` | businesses the name holds a role in, their parcels, formation after the first debt, deeds from the debtor into them (organizations compared by `org_key`: punctuation and legal form ignored) |
| `--timeline <ref>` | one dated list: documents, cases, judgments, bankruptcy events, business formations, deeds and mortgages on owned parcels |
| `--household <ref>` | owners mailed at the debtor's address, parcels at it, the same name owning in other states with the same mailing ZIP (leads) |
| `--portfolios <STATE>` | creditors holding open judgments against A/B leads with equity: portfolio-purchase prospects |

The `leads` table carries `equity_behind_lien` (the debtor's own lien on an owned parcel:
value minus only what is senior to it) and ranks on it where known. The `forensic-trace`
skill and the `asset-trace` workflow (gather, investigate, a skeptic per finding, dossier
under `data/derived/forensic/`) build on these; the `equity-tools` MCP server exposes them.

## Watchlists

`uv run python -m equity.watch` checks `config/private/watchlist.yaml` (git-ignored; template
`docs/watchlist-template.yaml`), and every `build` runs it at the end. Entries are a name in a
state, one record (`ref`), or a parcel. For each it collects documents (type, date, amount),
cases, judgments and bankruptcy events, owned parcels and, for a parcel, its owners, the
documents recorded against it and tax delinquency listings; compares them with the last
check (`data/derived/watch/state.json`) and writes what is new to
`data/derived/watch/alerts-<date>.md`. A name held by more than 200 records in the state is
too common to watch and is reported as such.

## Grades and the golden set

`uv run python -m equity.search --grade <debtor_ref> <owner_ref>` applies the matcher's rules
in order and returns the grade with its evidence: A `lien_names_parcel` (a debt document of the
debtor is recorded against a parcel the owner record owns), A `matcher_auto`, A `name_address`,
B `matcher_review`, B `name_zip`, C `name_only`, or `reject` (different names, or a flagged
name). Agents use it instead of grading by eye.

`uv run python -m equity.search_golden` scores hand-verified cases from
`config/private/golden_search/` (git-ignored: cases name real people; template
`docs/golden-search-template.yaml`): records that must and must not come back for a query, and
the grade each debtor-owner pair must get. It exits 1 on any failure, so a change to the search
rules can be checked against what a person established from the documents. The pipeline's own
acceptance cases stay in the owner-protected `tests/golden/`.

## SQL (CLI, notebooks, or the MCP server)

The catalog keeps `name_key()` and `street_norm()` as macros, plus these views:

| View | Rows |
|---|---|
| `v_party` | every party with its state and address |
| `v_owner_parcels` | owner → parcel → latest value and situs |
| `v_party_documents` | party → recorded document or debt-list item |
| `v_party_cases` | party → court case → judgment |
| `v_parcel_equity` / `parcel_equity` | net equity per parcel where recorder data exists |
| `leads` | stored by `compact`: one ranked row per debtor_owner_candidates row with the identity grade (best debtor-owner pair by the matcher's rules: `lien_names_parcel`, `matcher_auto`, `name_address`, `matcher_review`, `name_zip`, `name_only`), net equity over owned parcels where recorder data exists, open mortgage principal, homestead, deeds recorded after the first debt, the matcher's bankruptcy flags and same-name bankruptcy cases, and the debt's age. Ranked by grade, known net equity, then debt amount |
| `v_debtor_owner_candidates` | one row per name and state: debtor-side parties (debtor, borrower, grantor) on a judgment, lien or lis pendens whose exact name also owns parcels in the same state, with debts and parcels aggregated (name-only leads; on Ohio, Kentucky and Louisiana: 53,252 names, about 2 s) |

```sql
-- Names that owe on a judgment or lien and own property worth $100k+ in Ohio (one row per
-- name and state, debts and parcels aggregated; refs lead to --show)
SELECT debtor_name, debts, debt_amount, doc_types, parcels, parcel_value,
       debtor_refs, owner_refs
FROM v_debtor_owner_candidates
WHERE state = 'OH' AND parcel_value >= 100000 AND parcels <= 5
ORDER BY debt_amount DESC NULLS LAST LIMIT 50;

-- Everything one name owns, across every source
SELECT * FROM v_owner_parcels WHERE ref IN (
  SELECT ref FROM v_party WHERE name_key = name_key('Smith, John A'));

-- Owners mailed at one street address
SELECT raw_name, line1, city, zip5 FROM v_party
WHERE street_norm(line1) = street_norm('123 Main Street') AND zip5 = '43215';
```

A second project server, `equity-tools` (`uv run python -m equity.mcp_server`), offers the
search functions themselves as tools: `search`, `show`, `parcel`, `grade`, `network`, `leads`,
`facts` and `address`, each returning the same JSON as the CLI. It implements MCP's
JSON-RPC over stdio directly (no MCP library, no new dependency) and opens the index read-only
per call.

The MCP server starts from `.mcp.json` (Claude Code asks before using a project server). It is
read-only by default, caps results at 500 rows and 120 seconds, and opens a fresh connection per
query (`--ephemeral-connections`), so it holds no lock between queries. DuckDB allows one
writer per file: while `build` or `compact` runs, queries wait for it (`status`, `export` and
search only read).

## Licenses of what this uses

Only permissive, redistributable licenses: DuckDB and its `httpfs` extension (MIT) and
mcp-server-motherduck (MIT). Nothing copyleft and nothing on `ci/blocklist.toml` (no ML
matching libraries). Before adding DuckDB's `spatial` extension, note it bundles GEOS (LGPL).
