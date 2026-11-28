---
name: parcel-dossier
description: Everything the search index holds on one parcel - every source's record, situs, latest value, homestead, owners, and the recorded documents against it (deeds, mortgages, liens, lis pendens, releases) as a dated chain. Use when asked what is on a parcel, who owns it, or what encumbers it.
---

# Parcel dossier

1. `uv run python -m equity.search --parcel <parcel_uid or the county's own id> --json`.
   A parcel_uid is `<5-digit FIPS>-<normalized local id>`; the county's printed id also works.
   Several sources can describe one parcel (county layer, statewide layer, debt lists): show
   each and say where they disagree (value, owner name, year).
2. **Chain:** sort the documents by `recorded_on`. Pair each mortgage with a later release that
   references it when the data has `instrument_ref`; otherwise say "no release recorded" (an
   absent release is not proof the loan is open: many counties have no recorder data here).
3. **Equity and history:** `equity` is the net-equity row (value minus unreleased mortgages)
   where the county has recorder data; with none, say senior debt is unknown. `value_history`
   lists every year. For "who owned it on <date>", add `--as-of YYYY-MM-DD`: snapshot owners
   in force then and the last deed's grantees by then; empty means the data does not reach
   back that far.
4. **Owners:** list owner names with refs; for each, `--show <ref>` reveals other parcels and
   debts under that record.
5. **Value:** state the basis (appraised/market vs assessed and the state's ratio if known
   from `value_basis` in the source config) and the tax year. `tax_year` from an
   `as_retrieved` source is the retrieval year, not a roll year.

Output under `data/derived/parcels/<parcel_uid>.md` (git-ignored).
