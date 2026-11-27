# Proposal: two address-spelling rules for NY review pairs

Status: **proposal for the owner**. Nothing here changes a matching rule. The counts come from
`data/derived/ny/review_geo.parquet` (the NY review queue run through the Census geocoder,
`equity.matching.review_geo`), measured 2026-11-27.

The NY review queue holds 102,070 debtor/owner pairs with the same name whose typed addresses
did not agree. Two spelling differences were suspected of keeping real same-house pairs in
review. Each was measured as: after the change, the debtor's street line equals the owner's
mailing or property street line, and the 5-digit ZIPs agree.

| Rule | Pairs it would move | Geocoder says same street segment | Single-unit (no APT/UNIT) | Open amount on those pairs |
|---|---|---|---|---|
| Ordinal suffix dropped: `88TH ST` = `88 ST`, `1ST AVE` = `1 AVE` | 1,318 | 1,300 (98.6%) | 1,005 | $15,424,312 |
| Queens hyphenated house number: `88-12 150 ST` = `8812 150 ST` | 0 | — | — | — |

The hyphen form does not occur in the NY queue on either side (no house number of the form
`NN-NN` in 48,977 pairs with a 11xxx ZIP), so that rule would change nothing today.

## Decision for the owner

Approve or reject: "a street line that differs from the other only by an ordinal suffix
(ST, ND, RD, TH after a number) counts as the same street line". If approved, it would be
added to the address normalization the existing name + address + ZIP rules use. Up to 1,005
single-unit pairs could then match under those rules (fewer where another review reason,
such as a middle initial on one side only, still applies); the 313 multi-unit pairs would
stay in review (the unit is not compared).
