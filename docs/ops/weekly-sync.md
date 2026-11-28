# Weekly sync

Every source runs on GitHub Actions with no one in the loop. All three workflows need the
repository secret `SUPABASE_SECRET_KEY` (object storage); without it they do nothing.

| Step | Workflow | When | What it does |
|---|---|---|---|
| First load | `lake.yml` | every 6 hours | Builds every source not yet in the lake: parcel, zoning and lien-config sources, and every source a match run reads (`equity.lake.parcel_sources`). A new adapter wired into a run is picked up without listing it anywhere else. |
| Refresh | `refresh.yml` | every 2 hours, acting on what is due | Re-fetches each source on its `config/refresh.yaml` rule: court RSS feeds every 2 hours, sale listings daily (dated snapshots), debt and delinquent-tax lists weekly. |
| Match | `match.yml` | Mondays 10:13 UTC (or by hand) | Runs the debtor-to-owner matcher for every `STATES` key, one job per state (4 at a time), and uploads the results to storage under `derived/<state>/`. Only counts reach the job summary. |
| Health | `nightly.yml` | daily | Checks every adapter's source and opens or updates the health issue for failing ones. |

Two tests keep new sources from falling out of the sync (`tests/test_refresh.py`): every debtor
source a match run reads must have a refresh rule (or be listed as loaded once on purpose:
recorder indexes, closed past-year lists), and the hosted loader must build every source a
match run reads.

Adding a source: write its config or adapter, wire it into a run in
`src/equity/matching/resolve.py` and `config/debt_kinds.yaml`, and make sure a
`config/refresh.yaml` rule covers it (most names match the existing patterns: `*delinquent*`,
`*tax_*`, `*.sheriff_sales`, `*judgments`, ...). The next lake run loads it, the refresh keeps
it current, and the Monday match uses it.

Not automatic: paid sources (PACER), sources that need a key or account not yet given, and
anything held for an owner decision (docs/sources/blocked-alternatives.md).
