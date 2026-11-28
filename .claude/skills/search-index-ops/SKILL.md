---
name: search-index-ops
description: Build, refresh, compact, benchmark, export and pull the equity search index (data/search_index.duckdb) - which command, in what order, how long, and how much disk. Use when the index is missing, stale, slow, or another session needs it.
---

# Search index operations

| Goal | Command | Notes |
|---|---|---|
| Everything, unattended (for a scheduled task) | `uv run python -m equity.search_index refresh` | pulls if there is no local index, builds, loads matcher output and supplements, checks the watchlist, then compacts and exports only if something changed; stops below 3 GB free |
| Get the shared index (fastest) | `uv run python -m equity.search_index pull` | ~3 min for OH/KY/LA; replaces the local file |
| Index more states | `uv run python -m equity.search_index build --remote --states NY FL --workers 8` | re-indexes only changed sources; ~260 bytes per name of disk |
| After any build | `uv run python -m equity.search_index compact` | sorts lookup tables (3x faster) and stores `debtor_owner_candidates` |
| Re-sort or rebuild one table | `uv run python -m equity.search_index compact --only addresses` | `--only word_edits` rebuilds the one-edit word table from `word_sounds` |
| Measure | `uv run python -m equity.search --bench 60` | name/record recall, as written and with one typo, p50/p95 |
| Share | `uv run python -m equity.search_index export` | sorted Parquet parts under `_search_index/` in the lake bucket |
| Status | `uv run python -m equity.search_index status` | read-only |

- One writer at a time (DuckDB): while build/compact runs, MCP queries wait or fail on the
  lock. Run builds when nobody is querying.
- `compact` sorts each table through Parquet in key-range chunks (`sort_table`): peak extra
  disk is one compressed copy of the largest table (`names`, about 5 GB at 173M names).
- Disk: check `df -h .` first. `export` frees each table's Parquet after upload and `pull` loads
  one table at a time, so neither needs twice the index. The whole lake (~197M names) is ~50 GB: build by state.
- A layout change bumps `INDEX_VERSION` in `src/equity/search_index.py`; the next build then
  re-indexes every source.
- `data/catalog.duckdb` is a different file (`equity.lake`'s views): never point the search
  index at it.
