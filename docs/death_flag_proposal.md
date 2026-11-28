# Proposal: a "check before acting" flag from the Cook County death lists

Status: **proposal for the owner**. Nothing is matched; `death_record` is only loaded. Counts
measured 2026-11-27 against the IL-COOK debtor sources loaded locally:
`il.chicago.doah_judgments`, `il.chicago.doe_judgments`, `il.chicago.vacant_building_judgments`.

| | Count |
|---|---|
| Death records (4 Medical Examiner lists) | 4,747 (4,597 distinct names; 68 names on more than one record) |
| Non-company debtor names on Chicago judgments | 52,888 names, 336,366 judgments, $860.5M |
| Debtor names exactly equal to a death-record name (upper case, punctuation removed) | **247 names, 3,990 judgments, $13.06M** |
| ... of which a judgment was entered after that death date | 65 names, 705 judgments, $1.85M |

By list: indigent cremations 205 names, county burials 25, Heights Crematory 24, unclaimed 2.
By length: 242 of the 247 shared names are two words (first and last name only), 5 are three.

## Why this needs a decision

No death list gives an address or a birth date, so a shared name cannot tell a debtor from a
different person with the same name: with two-word names in a county of five million, many of
the 247 will be different people. A judgment entered after the death date (65 names) is either a
different person or a default judgment against someone already dead; the data cannot say which. The flag would be a warning on the person, never a
match, a removal or a change in amounts.

## Decision for the owner

1. Flag debtors whose full name exactly equals a Cook death-record name, as "check probate /
   obituary before acting", with the death date and list shown: yes or no.
2. If yes, limit it to names of three or more words (5 names today), or to death dates before
   the debtor's latest judgment, or neither.
