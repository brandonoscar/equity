---
name: debtor-dossier
description: Build an evidence-backed dossier on one debtor (a person or business, by name or ref) from the search index - identity candidates graded A/B/C like the matcher, parcels and values, debts, recorded documents, cases, business roles, transfers and bankruptcy - every fact cited by ref. Use when asked to look someone up, research a debtor, or check whether a debtor owns property.
---

# Debtor dossier

Deterministic tools only: you read evidence, you do not invent scores. Every line of the
dossier cites a ref (`source_id:party_id`, `parcel_uid`, `instrument_uid`).

## Steps

1. **Find the name.** `uv run python -m equity.search "<NAME>" [--state XX] --limit 25`
   (add `--kind org` for a business). Note each hit's rule (`exact`, `all_words`,
   `initial`, `sounds_like`, `similar`) and ref. With a ref already in hand, skip to 2.
2. **Pull each plausible record.** `uv run python -m equity.search --show <ref> --json` for
   the debtor record(s) and the owner record(s). For a business ref
   (`<source>:business:<sos_id>`) `--show` lists its officers and members.
3. **Read the matcher first.** `--show` output has `matcher` when the state's matcher
   output is loaded: `as_debtor` / `as_owner` links with rule and decision (`auto` or
   `review`), `summary` (open amount, parcels, equity when recorder data allows), `person`,
   `bankruptcy`, `transfers`. An `auto` link is the deterministic system's own grade A; say
   so and cite the rule. Hits also carry `name_flag`: a flagged name is never a lead.
   Then grade any pair the matcher did not link yourself.
4. **Grade identity per debtor-owner pair** (same tiers as `equity.matching.resolve`):
   - **A**: a debt document lists the owned parcel (`documents[].parcels` contains the
     `parcel_uid`), or same name_key and the debtor's address equals the owner's mailing
     address or the parcel's situs.
   - **B**: same name_key and ZIP; same business name and county; same address with one
     extra middle initial on one side.
   - **C**: same name in the state, nothing else (say how many records share the name).
   - **Reject**: placeholder names (digits and `|`), surname only, different JR/SR, or the
     name is the creditor (county treasurer, city, state).
5. **Each owned parcel:** `uv run python -m equity.search --parcel <parcel_uid> --json`.
   Record situs, latest value (appraised vs assessed, tax year), homestead flag, `equity`
   (net of unreleased mortgages, only where recorder data exists), and every document
   recorded against it (`released` says whether a recorded release points at it): mortgages / deeds of trust (senior debt), releases, liens,
   lis pendens, and deeds recorded after the debt date (possible transfer away).
6. **Wider links (optional):** `uv run python -m equity.search --network <ref> --hops 2`.
   Same-name and same-address edges are leads; follow them only to a document or parcel.
7. **Bankruptcy and cases:** `--show` lists cases; a court id ending in `b` is a bankruptcy
   court. An open bankruptcy stays collection (automatic stay): flag it first.

## Output

Write the dossier to `data/derived/dossiers/<slug>.md` (git-ignored: it names people). Never
commit it, never paste it into a public file. Structure:

```
# <NAME> (<state>)  [identity grade: A/B/C]
## Debts            doc type, date, amount, creditor, ref
## Property         parcel_uid, situs, value (basis, year), homestead, ref
## Senior debt      mortgages/liens on each parcel still open (or "none recorded")
## Red flags        bankruptcy, transfers after the debt, homestead, value basis caveats
## Identity evidence  the rule that holds for each debtor-owner pair, with refs
## Gaps             what the data cannot show (no mortgage index in this county, etc.)
```

End with one line: the strongest supported conclusion and its grade.
