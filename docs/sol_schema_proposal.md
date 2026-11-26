# Proposal: a dated layout for `config/sol.yaml`

Status: **proposal for the owner**. `config/sol.yaml` is CODEOWNERS-protected and filled only by
Brandon; nothing here changes it. Code that reads the new layout will be written only after the
layout is approved.

## Why one value per state no longer works

`sol.yaml` today holds one `judgment_enforceable_years`, one `lien_years` and one renewal rule per
state. Several states now set the answer by the judgment's **entry date** or **type**, checked
against statute text on 2026-11-25:

| State | Rule that a single number cannot hold |
|---|---|
| VA | Judgments dated on or after 2021-07-01: 10 years (child support 20), extendable by recorded certificate +10, once more +10 (30 at most). Earlier judgments: 20 years. (Va. Code 8.01-251) |
| ND | Docketed on or after 2021-08-01: a 20-year lien, no renewal, then cancelled. Earlier: 10 years, or 20 if renewed by affidavit; that renewal section is repealed 2031-08-01. (NDCC 28-20-13, -21, -35) |
| IL | Consumer-debt judgments entered on or after 2026-01-01: 15 years, no revival. Other judgments: lien 7 years, revivable before 20. (P.A. 104-0120; 735 ILCS 5/12-101, 2-1602) |
| UT | Renewals of 8 years can repeat and keep the original date and priority (S.B. 326, 2025). |
| AZ | The 10-year rule applies to judgments entered on or after 2013-08-03; no lien unless a certified copy **and** an information statement are recorded. (A.R.S. 12-1551, 33-961) |

Whether a judgment is a lien on land at all also depends on how it attaches:

| Code | Meaning | States (verified text where marked in the draft) |
|---|---|---|
| D | docketing by the court clerk creates the lien in that county | NC, SC, SD, ND, MN, IA, KS, MO, VA, MD, DE, WA |
| R | recording with the county recorder is required | AZ, ID, NV, UT, MI, VT, DC (likely CA, TX, FL, IL, CO, TN) |
| C | **new:** a certificate filed with the court clerk (not the recorder) | OH |
| E | **new:** a lien only by recording an execution | ME |
| X | no general judgment lien (attachment or levy needed) | MA, NH, RI |

## Proposed layout

Each state holds an ordered list of **rules**. The first rule whose conditions match a judgment
applies. Every rule carries a statute citation, and the state carries `confirmed_by`, as today.

```yaml
schema_version: 2
states:
  VA:
    lien_method: D                       # D, R, C, E or X (above)
    rules:
      - when: {entered_on_or_after: 2021-07-01, kind_not: [child_support]}
        enforceable_years: 10
        renewals: {count: 2, years_each: 10, by: recorded_certificate, before: expiry}
        keeps_priority: null             # owner to confirm
        statute: "Va. Code 8.01-251(B)"
      - when: {kind: [child_support]}
        enforceable_years: 20
        statute: "Va. Code 8.01-251(A)"
      - when: {entered_before: 2021-07-01}
        enforceable_years: 20
        renewals: {by: motion}
        statute: "Va. Code 8.01-251 (pre-2021 text)"
    confirmed_by: null
  ND:
    lien_method: D
    rules:
      - when: {docketed_on_or_after: 2021-08-01}
        lien_years: 20
        renewals: {count: 0}
        statute: "NDCC 28-20-13, 28-20-35"
      - when: {docketed_before: 2021-08-01}
        lien_years: 10
        renewals: {count: 1, years_each: 10, by: affidavit, window_days_before_expiry: 90,
                   ends: 2031-08-01}
        statute: "NDCC 28-20-21 (repealed 2031-08-01)"
    confirmed_by: null
  IL:
    lien_method: R
    rules:
      - when: {entered_on_or_after: 2026-01-01, kind: [consumer_debt]}
        enforceable_years: 15
        renewals: {count: 0}
        statute: "735 ILCS 5/2-1602 as amended by P.A. 104-0120"
      - when: {}
        lien_years: 7
        enforceable_years: 20
        renewals: {by: revival, before_years: 20}
        statute: "735 ILCS 5/12-101, 5/13-218"
    confirmed_by: null
  UT:
    lien_method: R
    rules:
      - when: {}
        enforceable_years: 8
        renewals: {count: unlimited, years_each: 8, by: motion_or_action}
        keeps_priority: true
        statute: "Utah Code 78B-6-1802/1804 (S.B. 326, 2025)"
    confirmed_by: null
  AZ:
    lien_method: R
    lien_requires: [certified_copy, information_statement]
    rules:
      - when: {entered_on_or_after: 2013-08-03}
        enforceable_years: 10
        renewals: {by: affidavit_or_action, before: expiry, years_each: 10}
        statute: "A.R.S. 12-1551, 12-1612, 33-964"
    confirmed_by: null
```

Condition keys: `entered_on_or_after` / `entered_before` (judgment entry date),
`docketed_on_or_after` / `docketed_before`, `kind` / `kind_not` (from the source's debt kind,
plus `consumer_debt`, `child_support` and `state_tax` where a source marks them). `when: {}`
matches every judgment.

## What code would do once approved

1. Read the first matching rule per judgment, using its entry or docket date, and compute
   `expires_on`, `years_left` and the renewal window.
2. Mark `no_lien` when `lien_method` is X, or E/R/C with no recording seen in the data (the
   recording is only known where a recorder source is loaded).
3. Refuse to compute anything for a state without `confirmed_by`, as `sol.yaml` does today.
4. Feed `years_left` into the scorer's `sol_years_left` factor and make an expired judgment a
   hard disqualifier.

## Owner decisions

1. Approve or change this layout (it replaces `sol.yaml` schema 1).
2. Approve the two new lien codes, C and E.
3. Fill the states, starting with the ones with the most matches (NY, NC, MI, PA, CT), from the
   corrected draft in `config/sol_proposed.yaml`; its rows marked `statute_text_checked` were
   re-read against statute text, the rest come from a 2020 chart.
