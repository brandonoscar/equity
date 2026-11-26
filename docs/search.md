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
uv run python -m equity.search_index status
uv run python -m equity.search_index export            # share: sorted Parquet parts in storage
uv run python -m equity.search_index pull              # another machine: load the shared index
```

`export` writes every table, sorted by its lookup key, as zstd Parquet parts of at most 40 MB
under `_search_index/` in the lake bucket (the bucket takes 50 MB per object), with a manifest
of the source versions it holds. `pull` downloads them and loads a fresh local index, so the
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
| `initial` | all query words but one are in the name, that one is an initial of a name word (or the reverse), and every full name word is accounted for | 0.85 |
| `sounds_like` | every query word is in the name or has the same Soundex code as a name word (3+ letters), word counts within one | 0.82 |
| `similar` | each query word's best Jaro-Winkler match among the name's words, averaged, is at least 0.90, and the word counts differ by at most one | 0.80 × similarity |

Candidates come from the exact key, from the query's two rarest words (inverted index
`name_words`), and from words that sound like the query's two longest words (`word_sounds`,
American Soundex as a SQL macro), so a misspelling of every word still finds the name.
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

Record recall is lower than name recall when many records share one name (a common name
can have hundreds): the right name comes back, and `--state` or `--kind` narrows it.

## SQL (CLI, notebooks, or the MCP server)

The catalog keeps `name_key()` and `street_norm()` as macros, plus these views:

| View | Rows |
|---|---|
| `v_party` | every party with its state and address |
| `v_owner_parcels` | owner → parcel → latest value and situs |
| `v_party_documents` | party → recorded document or debt-list item |
| `v_party_cases` | party → court case → judgment |
| `v_debtor_owner_candidates` | debtors whose exact name also owns a parcel in the same state (name-only candidates) |

```sql
-- Debtors on a judgment or lien whose name also owns property worth $100k+ in Ohio
SELECT debtor_name, doc_type, amount, owner_ref, parcel_uid, appraised_total
FROM v_debtor_owner_candidates
WHERE state = 'OH' AND appraised_total >= 100000
ORDER BY amount DESC NULLS LAST LIMIT 50;

-- Everything one name owns, across every source
SELECT * FROM v_owner_parcels WHERE ref IN (
  SELECT ref FROM v_party WHERE name_key = name_key('Smith, John A'));

-- Owners mailed at one street address
SELECT raw_name, line1, city, zip5 FROM v_party
WHERE street_norm(line1) = street_norm('123 Main Street') AND zip5 = '43215';
```

The MCP server starts from `.mcp.json` (Claude Code asks before using a project server). It is
read-only by default, caps results at 500 rows and 120 seconds, and opens a fresh connection per
query (`--ephemeral-connections`), so it holds no lock between queries. DuckDB allows one
writer per file: while `build` or `compact` runs, queries wait for it (`status`, `export` and
search only read).

## Licenses of what this uses

Only permissive, redistributable licenses: DuckDB and its `httpfs` extension (MIT) and
mcp-server-motherduck (MIT). Nothing copyleft and nothing on `ci/blocklist.toml` (no ML
matching libraries). Before adding DuckDB's `spatial` extension, note it bundles GEOS (LGPL).
