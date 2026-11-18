# Phase 2 status: adapters

Date: 2026-11-15. Cost: $0. No login, CAPTCHA, paid source or signed agreement was used.

## Built (open sources), each with recorded fixtures, contract test and live health check
| Adapter | Source | Method | Feeds tables | Notes |
|---|---|---|---|---|
| `wv.statewide.parcels` | WVGISTC ParcelSummary (all 55 counties, TY2026) | ArcGIS REST, one county per fetch | parcel, party, address, owner_snapshot, parcel_assessment | Deterministic rule for duplicate parcel rows; IAS id shared with county data |
| `wv.statewide.delinquent` | WVGISTC Delinquent Properties (weekly, State Auditor) | ArcGIS REST | tax_delinquency_snapshot | Status per certificate (Redeemed / No Bid / Deed / Dismissed / Sold-did-not-follow-through); no dates in source |
| `wv.monongalia.assessor.parcelweb` | County ParcelWeb sales/transfer history | HTML (GET pages, 3 s spacing) | parcel, party, ownership_period, data_issue | Dated chain of title with sale price and deed book/page |
| `us.wvnd.rss` | N.D. W. Va. district court CM/ECF feed | RSS (24 h window) | court_case, party, case_party, docket_entry | Criminal skipped |
| `us.wvnb.rss` | N.D. W. Va. bankruptcy court CM/ECF feed | RSS (24 h window) | same + chapter, trustee | Chapter 7 no-asset / asset notices visible |

**Privacy:** the repo is public, so every fixture replaces names and street lines with deterministic
pseudonyms (`TESTOWNER xxxxxx`, `NNN TEST ST`) and drops ASP.NET view state.
`tests/test_fixture_privacy.py` fails the build if a real name slips in.

**Data quality found in real data:** ParcelWeb has transfers whose end date precedes their start
date (14 of 40 sampled rows, all on one deed). Those go to `data_issue` for review rather than
being guessed into ownership intervals.

## Blocked (needs you): in the brief's priority order
| Adapter | Blocker | What unblocks it |
|---|---|---|
| Recorder (County Clerk, Compiled Technologies IDX) | Slider CAPTCHA + "viewing only, do not copy" terms | Clerk electronic export under §59-1-10(e) (draft request in phase0 §7) |
| Court judgments (circuit) | WVPASS requires login; 100-result cap | WV Supreme Court Administrative Office bulk request, or Clerk judgment docket export |
| Secretary of State | Search behind reCAPTCHA v3; bulk $12,000 + $1,750/mo | Approve Custom List Service ($25 + $0.05/record) |
| PACER | Needs your PACER account; metered | Your OK + account credential (stored as a network secret, never in the repo) |

## What doesn't work yet
- **No persistent database.** Adapters run and load in tests, but nothing schedules real
  ingestion or stores the DuckDB/Parquet lake. The RSS feeds only cover 24 hours, so history
  starts accruing only once a daily job writes somewhere durable. **Decision: where should the
  lake live?** (Your machine, a cloud bucket, or a small VM.)
- **Loader speed won't scale nationally.** It checks each row individually: fine for one county
  (~65K parcels), far too slow for 150M US parcels. National scale needs a set-based loader
  (normalize to Parquet, then supersede with one SQL anti-join per table). That's the next
  engineering step before adding more states.
- County ArcGIS parcel layer (geometry) not built yet; the statewide table covers attributes.
  Geometry needs the DuckDB spatial extension, whose download host isn't reachable here.
- Golden-file pass rate: n/a (0 cases).
