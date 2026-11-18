# Golden cases

Hand-verified, written by Brandon. CODEOWNERS-protected: changes need Brandon's review.

Each file in `cases/` is one judgment traced by hand from the source documents:
debtor → parcels the debtor (or the debtor's entities) owned → liens on each parcel in priority
order → estimated equity → flags. The pipeline must reproduce it **exactly**.

1. Copy `TEMPLATE.yaml` to `cases/<state>-<county>-<case-number>.yaml`.
2. Fill every field from the documents themselves (deed books, docket, assessor card), not from
   this system's output.
3. Cite every fact (`source`: county + instrument number / case number / parcel id, and the date
   you looked).

`test_golden.py` runs every case through the Phase 5 query. Until that query exists, any case
file makes the test fail. That is intended: golden cases are the acceptance test for Phase 5.

Do not put real people's names in this public repo. Either keep `cases/` local (it's tracked, so
add them only once the repo is private), or replace names with stable pseudonyms and keep a
private mapping.
