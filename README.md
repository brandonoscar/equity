# equity

A deterministic land and court records graph: people and businesses ↔ LLCs, officers and agents
↔ parcels ↔ recorded documents ↔ court cases ↔ dates. It answers one question with evidence:
*does this debtor own reachable real property with equity behind our lien?*

- **No AI in the system.** No LLM calls, embeddings or ML models. Parsers, explicit rules, SQL.
  `ci/check_no_ai.py` fails the build if one sneaks in.
- **Provenance on every fact.** Every row names its source, record key, URI and retrieval time.
- **Time is first-class.** Valid time (recorded/effective dates) plus transaction time
  (`ingested_at` / `superseded_at`), so any parcel can be asked about as of any past date.
- **Adapters, not scrapers.** One adapter per source: `fetch()`, `normalize()`, `health()`.

## Use

```bash
make check      # exactly what CI runs: lint, mypy --strict, no-AI guard, secrets, tests, coverage
make fixtures   # regenerate the synthetic test county
```

## Layout

| Path | What |
|---|---|
| `src/equity/schema/` | migrations (`V000N__*.sql`), loader with supersession, catalog, as-of queries |
| `src/equity/quality/` | provenance gate and data invariants (build-failing) |
| `src/equity/adapters/` | adapter contract and registry; nightly health check |
| `src/equity/rules/`, `matching/` | Phases 4 and 3 (deterministic, config-driven) |
| `src/equity/catalog.py`, `search.py` | query catalog over the lake, name and address search, MCP SQL access (`docs/search.md`) |
| `config/` | doc-type classes, rule thresholds, statute-of-limitations table (Brandon fills) |
| `config/private/` | git-ignored business settings |
| `tests/golden/` | hand-verified cases written by Brandon (CODEOWNERS) |
| `ci/` | blocklist, guard scripts, coverage floors (CODEOWNERS) |
| `docs/phase0.md` | source survey, access rules, schema design, open questions |
