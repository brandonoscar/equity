---
name: forensic-trace
description: Trace a debtor's reachable property like a judgment-recovery investigator - lien priority on each parcel (who is senior, equity behind our lien), badges on deeds out after the debt, LLCs the debtor runs and their parcels, a dated timeline, household and cross-state leads, and which creditors hold judgments worth buying - from the deterministic equity.forensic tools, every finding cited and labelled as evidence, never a legal conclusion. Use when asked to investigate, trace assets, find hidden property, check for fraudulent transfers, or build a forensic dossier.
---

# Forensic trace

The tools gather facts by fixed rules (`uv run python -m equity.forensic ...`, or the
`equity-tools` MCP server). You read them like an investigator and write what they show. You
never conclude "fraudulent transfer", "alter ego" or "same person": those are a lawyer's and a
court's calls. Say "badges present", "lead", "consistent with", and cite the ref.

## Order of work

1. **Identity first.** `uv run python -m equity.search --grade <debtor_ref> <owner_ref>` on
   the pairs you rely on. Everything below is gathered by exact name in the state, so a
   namesake's records can appear: weigh each against the identity evidence.
2. **Timeline.** `--timeline <debtor_ref>`: the dated story. Look for a deed, a new LLC, a
   refinance or a new mortgage shortly after a judgment or lien.
3. **Lien position.** For each owned parcel the debtor's lien is recorded against:
   `--stack <parcel_uid> --lien <instrument_uid>`. Report the rank, what is senior, the equity
   behind the lien (value minus senior debt only), and junior mortgages recorded after it
   (equity the lien still sits ahead of). Say the value's basis and year, and that priority
   needs a title search to confirm (tax liens and purchase-money mortgages can jump ahead).
4. **Transfers out.** `--badges <debtor_ref>`: each deed with its badges. Several badges on
   one deed (to an LLC the debtor runs, no consideration, a quitclaim, the debtor still listed
   after) make it worth an attorney's review under the state's voidable-transactions law; one
   weak badge (a shared common surname) does not.
5. **Entities.** `--ring <debtor_ref>`: businesses the name holds a role in, their parcels,
   formation after the debt, deeds from the debtor into them. Property held this way is a
   lead for a nominee or alter-ego theory, for counsel to assess.
6. **Household and other states.** `--household <debtor_ref>`: owners at the debtor's
   address, parcels at it, the same name owning elsewhere with the same mailing ZIP. Leads to
   check, never identity.
7. **Paper to buy (sourcing).** `--portfolios <STATE>`: creditors holding open judgments
   against graded leads with equity. A creditor with many is a portfolio-purchase prospect.

## Writing it up

- One finding per claim: what the records show, the refs, how strong (strong, moderate, weak)
  and why, and what would confirm or break it (the document to pull, the title search).
- Separate facts from leads from open questions. Never fill a gap with a guess.
- Dossiers name people: write them only under `data/derived/forensic/` (git-ignored).
- Purpose: recovery of debts the business holds or is evaluating to buy. Do not produce this
  for credit, insurance, employment or housing decisions, or for anyone else as a consumer
  report.
