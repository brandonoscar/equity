# Search and queries

Three pieces, all deterministic (fixed rules, no models), all under permissive licenses:

| Piece | What it is | License |
|---|---|---|
| `equity.catalog` | One local DuckDB file indexing the lake: names, owners, parcels, values, documents, cases, businesses, addresses | this repo |
| `equity.search` | Name and address search over the catalog, every hit scored by a named rule and listed with its links | this repo |
| `equity-catalog` MCP server (`.mcp.json`) | [mcp-server-motherduck](https://github.com/motherduckdb/mcp-server-motherduck) 1.1.1 over the catalog, read-only, so any Claude session can run SQL against it | MIT |

## Build the catalog

```bash
uv run python -m equity.catalog build --remote          # every built source in object storage
uv run python -m equity.catalog build                   # or the local data/lake
uv run python -m equity.catalog build --remote --states OH NY
uv run python -m equity.catalog compact                 # sort the lookup tables (faster)
uv run python -m equity.catalog status
```

A source is re-indexed only when its version changed (the `_state.json` bundle remotely, the
part markers locally), and sources gone from the lake are dropped, so `build` is cheap to
re-run. Each source is replaced in one transaction. The file (`data/catalog.duckdb`, git-ignored)
is written in DuckDB's v1.5 storage format so the MCP server, which pins its own DuckDB, can
open it.

## Search

```bash
uv run python -m equity.search "JOHN A SMITH" --state OH
uv run python -m equity.search "ACME HOLDINGS LLC" --kind org --json
uv run python -m equity.search --show <source_id>:<party_id>
uv run python -m equity.search --address "123 Main St" --zip 43215
```

Names are compared on the matcher's `name_key` (upper-case words, punctuation and
JR/SR/AND/TR... dropped, de-duplicated, sorted), so "Smith, John A." and "JOHN A SMITH" are the
same key. Rules, best first:

| Rule | When | Score |
|---|---|---|
| `exact` | same name_key | 1.00 |
| `all_words` | every query word is in the name, plus 1–2 more | 0.95 / 0.90 |
| `initial` | all query words but one are in the name, that one is an initial of a name word (or the reverse), and every full name word is accounted for | 0.85 |
| `similar` | each query word's best Jaro-Winkler match among the name's words, averaged, is at least 0.90, and the word counts differ by at most one | 0.80 × similarity |

Candidates come from the exact key and from the query's two rarest words (inverted index
`name_words`), so a typo in one word still finds the name through the other. Each hit lists
parcels owned (with the latest value), debts and amounts, documents, cases and business roles;
`--show` lists them in full with same-name parties in other sources. A same name in two sources
is a candidate, not a match: linking is the matcher's job (address and ZIP rules).

Address search standardizes the street with the matcher's `street_norm` (USPS Publication 28
words: STREET → ST and so on) and finds parcels at that situs and parties whose address it is,
including addresses kept as one unsplit line.

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
query (`--ephemeral-connections`) so `equity.catalog build` can keep writing.

## Licenses of what this uses

Only permissive, redistributable licenses: DuckDB and its `httpfs` extension (MIT) and
mcp-server-motherduck (MIT). Nothing copyleft and nothing on `ci/blocklist.toml` (no ML
matching libraries). Before adding DuckDB's `spatial` extension, note it bundles GEOS (LGPL).
