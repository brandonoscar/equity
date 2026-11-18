# Private configuration (git-ignored)

Everything in this folder except this README is ignored by git. The repository is public.

Put business-specific settings here, for example `buyer.yaml`:

```yaml
target_states: [XX, YY]          # states the buyer enforces in
min_judgment_amount: 0           # smallest file worth buying
min_judgment_age_years: 0        # e.g. older than ~2 years
judgment_kind: commercial        # commercial | consumer | any
```

Phase 5 reads this file if present and filters the ranked CSV. Nothing in tests depends on it.
