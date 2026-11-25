# Gaps and deal flow (scan of 2026-11-25)

This scan covers the repo at main 9fd9114, `docs/gaps.md` as regenerated, and two web research passes. It follows `Data source gap analysis.md` (2026-11-23), and almost all of that report's 15-step build plan has since landed:
- refresh and snapshots
- health history
- scoring and saved queries
- PACER guard
- bankruptcy screen
- transfer and nominee detection
- HUD REO
- Federal Register notices
- SBA charge-offs
- registries
- deed-sales files

What is left is mostly decisions only the owner can make, plus a few free sources.

## 1. Blocked on owner decisions (highest value, no code needed)

| Gap | Effect today | What unblocks it |
|---|---|---|
| `config/sol.yaml`: all 51 states null | No judgment is ever flagged expired or near expiry, and `sol_years_left` is never scored | Fill each state's enforceable years, lien years and renewal rules, with statutes. No free machine-readable table exists. The White and Williams 50-state chart (rev. 2020) is a cross-check only. |
| `config/scoring.yaml`: 11 weights null, no tiers | The scorer writes factors but ranks nobody | Set the weights and tiers |
| `config/rules.yaml`: 9 values null | Rule thresholds don't run | Fill them |
| Execution (homestead) exemptions by state | Equity is gross parcel value, so equity a homestead protects is counted as reachable | No free maintained table exists. Encode each state's exemption statute; 11 USC 522(d) amounts change every 3 years. |
| Buyer criteria (`config/private/queries/`) | Saved queries and "new since last run" have nothing to run | Add the criteria privately |

## 2. Data gaps (from `docs/gaps.md`)

- **Mortgages and satisfactions:** loaded in 5 states (NYC ACRIS, Philadelphia RTT, Hillsborough, IL PTAX, MD SDAT). In the other 46 states, `equity_est` cannot net out senior debt, so equity is overstated. No free bulk recorder index was found for King, Miami-Dade or Cook. Maricopa's recorder has a public JSON API (names and doc codes, no amounts); its terms are unconfirmed.
- **Debt lists:** none in 20 states: AL, AR, HI, IA, ID, KY, MA, ME, MT, ND, NH, NM, NV, OK, OR, RI, SD, TN, WA, WY.
- **Private court money judgments:** only TX (Harris JP; Travis tax suits) and FL (Hillsborough) have free bulk. Elsewhere this needs the records-request programme in the earlier report.
- **Business registries:** 8 states loaded. Most others are paid or restricted (GA, KY, WV, VA, WA, IN, OK, MN, NC, TX SOS). Florida Sunbiz is the large free one left (see section 4).
- **Owner names:** only HI is missing statewide.
- **Deceased debtors and change of address:** no free compliant source. The SSA DMF is restricted (42 USC 1306c), the NTIS LADMF is paid and needs certification, and NCOA is licensed. Handle these as per-case checks through PACER and probate.

## 3. Deal-flow sources (where judgments and notes are sold)

**No US judgment marketplace has an API.** The research found:

| Source | Listed | Machine access | Needs | Status |
|---|---|---|---|---|
| **HUD loan sales** (Federal Register notices) | Defaulted HUD-held notes: single-family vacant and non-vacant, multifamily, healthcare | **Federal Register API, free** | Loan files need HUD's confidentiality agreement and qualification statement (HUD-9611) | **Built:** `us.federalregister.loan_sales`, 109 notices since 2000, refreshed daily |
| County delinquent-tax and certificate lists | Parcels and certificates before tax sales | Public CSV/XLS/ArcGIS | None | 87 already registered (71 delinquency lists, 16 tax-lien lists); keep adding by config |
| Fannie Mae / Freddie Mac NPL and RPL sales | Pool fact sheets, winning bidders | Public PDFs, no API | Bidder qualification and capital | Announcements only; robots and terms not yet checked |
| FDIC loan sales; First Financial Network; Mission Capital; Heritage DebtX | Failed-bank and portfolio loans | No public API | Free registration plus NDA per deal | Owner decision |
| Paperstac; Debexpert | Notes; charged-off consumer debt | No API found | Account; Debexpert may need collection licensing | Owner decision |
| JudgmentMarketplace.com | Judgments listed by creditors (5% fee) | No API | Unclear | Possibly stale; unverified |
| RealAuction, GovEase, Bid4Assets, LienHub, SRI, MVBA | Tax liens and deeds | No public API; logged-in portals | Bidder registration | Use the county's own public list instead; do not scrape |
| Paid judgment and lien data: UniCourt (~$2,250/mo), Trellis, Docket Alarm, LexisNexis, Enformion, ATTOM, Cotality, PropertyRadar | Judgments, liens, debtor property | APIs | Paid contract | Needs budget approval; get quotes first |

## 4. Free sources not yet built (ranked)

1. **FHFA HPI at ZIP5 / county** (public domain). Rolls stale assessed values forward to today, so `parcel_value` is closer to market. The ZIP5 file is served as XLSX, which needs an XLSX reader (a pyproject change).
2. **CourtListener quarterly dockets bulk** (free S3, 5.1 GB). Gives "In re <debtor>" names for bankruptcy cases before the RSS polling began. It backfills the bankruptcy screen; it cannot prove a debtor has no case.
3. **Florida Sunbiz bulk** (SFTP, using credentials the state posts publicly). Covers FL entity status and **federal tax lien filings**, the only free bulk IRS lien data found. Using the shared login needs the owner's OK under the no-login rule.
4. **Census batch geocoder** (free). Standardizes addresses before matching, so fewer spelling-only misses.
5. **Maricopa recorder API**. Shows whether mortgages and releases exist, after its terms are confirmed.

## 5. Recommended order

1. Owner fills `sol.yaml`, then `scoring.yaml` weights and tiers. This turns matches into ranked buy, skip and check lists.
2. Decide on the HUD loan-sale qualification (the notices now arrive daily) and whether to price one paid judgment feed.
3. Approve the Sunbiz shared SFTP login and an XLSX dependency (for FHFA and Milwaukee).
4. Build the CourtListener bankruptcy backfill and the Census geocoding pass.
