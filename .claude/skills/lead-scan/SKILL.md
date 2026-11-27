---
name: lead-scan
description: Shortlist debtors who own property in a state from the stored debtor_owner_candidates table (search index), apply buyer criteria (debt size, parcel value, parcel count, debt type, age), drop rejects, and hand the shortlist to the verify-leads workflow or the debtor-dossier skill. Use when asked to find leads, prospects, or debtors with equity.
---

# Lead scan

1. **Query the stored table** through the `equity-search` MCP server (or
   `duckdb data/search_index.duckdb` read-only). Start from:

   ```sql
   SELECT state, debtor_name, name_key, debts, debt_amount, doc_types, first_debt_on,
          last_debt_on, parcels, parcel_value, debtor_refs, owner_refs, parcel_uids
   FROM debtor_owner_candidates
   WHERE state = 'OH'
     AND debt_amount >= 10000          -- buyer's minimum
     AND parcel_value >= 50000         -- gross, before mortgages
     AND parcels <= 5                  -- big portfolios are usually creditors or agencies
   ORDER BY debt_amount DESC NULLS LAST
   LIMIT 50;
   ```

   If `debtor_owner_candidates` is missing, the index has not been compacted: run
   `uv run python -m equity.search_index compact` (writes; MCP queries wait meanwhile).
   Buyer criteria live in `config/private/queries/` when the owner has set them; use them.
2. **Drop rejects before verifying:** governments and agencies (CITY OF, COUNTY, STATE OF,
   UNITED STATES, HOUSING AUTHORITY, UNIVERSITY, BOARD OF), placeholder names, "Name
   withheld", one-word names, names shared by more than ~25 records (check with
   `SELECT count(*) FROM names WHERE name_key = '<key>'`).
3. **Say what the table is:** name-only matches per state, aggregated (up to 20 refs per
   side). Every row still needs the identity grading in `debtor-dossier`.
4. **Hand off:** for up to ~5 leads, run `debtor-dossier` on each. For more, run the saved
   workflow `verify-leads` with the shortlist (one `lead-verifier` agent per lead, then a
   skeptic pass on the strong ones). Report the shortlist with the criteria used and how many
   rows each filter removed.

Results name people: keep them under `data/derived/` (git-ignored).
