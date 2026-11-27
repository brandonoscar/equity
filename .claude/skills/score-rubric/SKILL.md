---
name: score-rubric
description: Score one lead's recoverability by hand against the owner's rubric (config/scoring_rubric.yaml) from its deterministic fact sheet (uv run python -m equity.facts <lead_id>) - gates, banded points, deductions, tier and confidence, every point cited to a fact and ref, scores labelled draft until the owner approves the rubric. Use when asked to score, rate or rank a debtor or lead for recovery risk.
---

# Score a lead against the rubric

Claude is the scorer here, by hand, with no model in the code: the rubric's numbers are the
owner's (Brandon's) decisions in `config/scoring_rubric.yaml`, and the facts come only from the
fact sheet. Never invent a number, a band or a fact; when a fact is missing, use the rubric's
"unknown" band and say so.

## Before scoring

1. **Purpose check.** The score ranks recovery of debts the business holds or is evaluating to
   buy. Do not score for credit, insurance, employment or housing decisions, or for anyone
   who would receive it as a consumer report (FCRA): decline and say why.
2. **Read the rubric.** `config/scoring_rubric.yaml`: note `version` and `status`. If
   `status` is `draft`, every score you give is labelled **DRAFT (rubric not approved)**.
3. **Get the fact sheet.** `uv run python -m equity.facts <lead_id>` (lead ids come from the
   `leads` table; the `lead-scan` skill finds them). Score only from the sheet; if you look
   something up beyond it (`--show`, `--parcel`), cite that ref too.

## Scoring

1. **Gates, in order.** Identity (best `identity[]` grade C or reject: `not_scored`), open
   bankruptcy (`hold`), enforcement expired (`score_zero`). A gate that fires ends the score.
2. **Factors.** For each factor, pick exactly one band, quote the fact that put it there with
   its ref (`parcel_uid`, `instrument_uid`, `source_id:party_id`), and give the points. Use
   the arithmetic the rubric states (for reachable equity: net equity known minus a homestead
   exemption on homestead parcels, over `factors.open_amount`); show the numbers.
3. **Deductions.** Apply each that the facts support, with its ref; respect the caps.
4. **Total, tier, confidence.** Sum (floor 0), the tier by `tiers`, the confidence by the
   rubric's rule. List the sheet's `gaps` that lowered confidence.
5. **What would change it.** One or two facts that, if found, would move the tier (for
   example "the mortgage amount on 39049-...").

## Output

Return JSON (the `score-people` workflow's schema), and a two-line summary:

```json
{"lead_id": 123, "rubric_version": "draft-1", "rubric_status": "draft",
 "sheet_sha256": "...", "gate": null,
 "factors": [{"id": "identity", "band": "...", "points": 25, "max": 25,
              "facts": ["oh.x:abc lien recorded against 39049-..."]}],
 "deductions": [{"id": "deed_after_debt", "points": -10, "facts": ["..."]}],
 "total": 61, "tier": "2", "confidence": "medium", "gaps_used": ["..."],
 "would_change": ["..."]}
```

Scores name people: write them only under `data/derived/scores/` (git-ignored), never in the
repository or a chat channel others read.
