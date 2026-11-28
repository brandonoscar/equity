---
name: lead-scan
description: Shortlist debtors who own property in a state from the stored, ranked leads table (search index: grade, net equity, homestead, bankruptcy, transfers, debt age), apply buyer criteria (debt size, parcel value, parcel count, debt type, age), drop rejects, and hand the shortlist to the verify-leads workflow or the debtor-dossier skill. Use when asked to find leads, prospects, or debtors with equity.
---

# Lead scan

1. **Query the ranked `leads` table** through the `equity-search` MCP server (or
   `duckdb data/search_index.duckdb` read-only). One row per name and state; the grade is the
   best debtor-owner pair by the matcher's rules (same order as `--grade`), and rows are
   already ranked by grade, then known net equity, then debt amount (facts, not a score):

   ```sql
   SELECT lead_id, state, debtor_name, grade, grade_rule, debts, debt_amount, doc_types,
          first_debt_on, last_debt_age_days, owned_parcels, parcel_value, value_tax_year,
          parcels_with_net_equity, net_equity_known, open_mortgage_principal, homestead_any,
          deeds_after_debt, matcher_bankruptcy, same_name_bankruptcies,
          debtor_refs, owner_refs, parcel_uids
   FROM leads
   WHERE state = 'OH' AND grade IN ('A', 'B')
     AND debt_amount >= 10000          -- buyer's minimum
     AND parcel_value >= 50000         -- gross, before mortgages
     AND owned_parcels <= 5            -- big portfolios are usually creditors or agencies
     AND NOT homestead_any             -- homestead protection cuts reachable equity
     -- owner_occupied_any: an owner record is mailed at the parcel itself (a homestead
     -- stand-in where the source has no homestead flag; check the state's exemption)
     AND matcher_bankruptcy IS NULL
   ORDER BY grade, net_equity_known DESC NULLS LAST, debt_amount DESC NULLS LAST
   LIMIT 50;
   ```

   Where the debtor's own lien is recorded against an owned parcel, `equity_behind_lien` is
   the value minus only what is senior to that lien (junior mortgages recorded after it do not
   count against it) and rows rank on it. Read the columns as they are: `net_equity_known` sums only the
   `parcels_with_net_equity` parcels (counties with recorder data); elsewhere senior debt is
   unknown, not zero. `deeds_after_debt` > 0 means a deed was recorded against an owned parcel
   after the first debt: check it (`--parcel`) before counting the equity.
   `same_name_bankruptcies` is the same name on a bankruptcy case in the state: a lead to
   check, not a match. If `leads` is missing, run `uv run python -m equity.search_index
   compact` (or `compact --only leads`). Buyer criteria live in `config/private/queries/`
   when the owner has set them; use them.
2. **Drop rejects before verifying:** governments and agencies (CITY OF, COUNTY, STATE OF,
   UNITED STATES, HOUSING AUTHORITY, UNIVERSITY, BOARD OF), placeholder names, "Name
   withheld", one-word names, names shared by more than ~25 records (check with
   `SELECT count(*) FROM names WHERE name_key = '<key>'`).
3. **Say what the table is:** one row per exact name and state, aggregated (up to 20 refs
   per side), graded by its best debtor-owner pair. A grade here is a shortlist grade over
   up to 20 records a side: confirm it on the specific records with `--grade` (the
   `debtor-dossier` skill does) before reporting a lead as A or B.
4. **Hand off:** for up to ~5 leads, run `debtor-dossier` on each. For more, run the saved
   workflow `verify-leads` with the shortlist (one `lead-verifier` agent per lead, then a
   skeptic pass on the strong ones). Report the shortlist with the criteria used and how many
   rows each filter removed.

Results name people: keep them under `data/derived/` (git-ignored).
