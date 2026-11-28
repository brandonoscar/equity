# Owner decisions now gate every debtor answer

The software already answers most of the twelve per-debtor questions with free data, but it can rank no one yet. Exact-key matching, people merging, bankruptcy screening, transfer flags and sale watching are all built. What stops the pipeline is configuration only the owner can fill: **`config/sol.yaml` is 357 of 358 values null**, **all 11 scoring weights are null with no tiers**, **9 of 11 `rules.yaml` values are null**, the **PACER ceiling is null** (so every request is refused), and there are **zero golden cases** to check matches against ([repo inventory](../research_notes/Judgment%20equity%20data%20and%20tasks/repo_inventory.md)). After that, the largest gaps in what the software can see are senior debt and exemptions. Mortgages are netted in **1 of 70 match runs** (NYC). No homestead or tenancy-by-the-entirety rule is applied anywhere, so equity is overstated almost everywhere. Free data that would close part of this gap is already sitting unused in the repo: Philadelphia mortgages, Florida recorder mortgages, Maryland's mortgage-amount column, and an FHFA price index that is loaded but not applied. Three questions have no free lawful national source and will stay per-case checks: whether the debtor is **alive** (the Death Master File costs **$2,930 a year plus fees** and needs certification), the **current balance** on a senior loan, and **private court judgments** outside Texas and Florida. The research also found that one value per state cannot hold judgment-life law that changed in Virginia (2021), North Dakota (2021), Utah (2025) and Illinois (2026). So `sol.yaml` needs dated rules before the owner fills it, not after.

## Twelve questions, four states of readiness

Every question below was checked against the repo at HEAD 4436f70 (2026-11-25) and against new research. "Built" means code runs and produces output. "Inert" means the code exists but an owner value is null. "Partial" means real coverage with large holes. "Unanswered" means no logic exists.

| # | Question per debtor | State in repo | What limits it most | Highest-value next step |
|---|---|---|---|---|
| 1 | Who is the debtor | Built (exact keys), unvalidated | 0 golden cases; registries in 8 states; FMCSA, NPPES and licence officers loaded but not joined | Owner writes golden cases |
| 2a | Alive | Unanswered | No free national death file | Code: derive estate and probate signals from data already loaded |
| 2b | In bankruptcy | Built, forward-only | RSS feeds hold about a day; no backfill; PACER refused | Code: FJC bankruptcy IDB plus CourtListener backfill; owner sets PACER ceiling |
| 3 | What debts, amounts, status | Partial | Private court judgments only in TX and FL; 20 states have no debt list | Code: check the NY warrant series scope; build an intake path for records-request files |
| 4 | Still enforceable | Inert | `sol.yaml` all null and one value per state | Code: dated rule schema; owner fills it |
| 5 | Property owned, directly or via companies | Built, strongest layer | Company links in 7 runs; CA and NJ redaction | Code: add more registries and runs |
| 6 | Worth today | Partial | Stale assessed values; FHFA loaded but not applied | Code: ratio tables plus HPI roll-forward; owner approves the method |
| 7 | Senior debt | Partial (NY only) | Mortgages netted in 1 of 70 runs | Code: wire PA RTT, FL OR and MD SDAT mortgage fields |
| 8 | Exemptions | Unanswered | Homestead boolean in 13 states, read by nothing | Code: dated exemptions table; owner confirms amounts |
| 9 | Transferred away | Built, partly inert | `nominal` flag null; 3 of 4 related-party toggles read by no code | Owner sets thresholds; code implements the toggles |
| 10 | About to be sold | Built | Not scheduled; surplus-proceeds lists mostly PDFs | Code: schedule `sale_watch`; add Stark OH and surplus lists |
| 11 | How to reach them | Partial | Locate sources loaded but not linked; contact law unread | Legal read on collection status and channels; code: contact table with restriction tags |
| 12 | Decide and rank | Inert | Weights, tiers, buyer queries empty; nothing scheduled | Owner fills scoring and queries; code: hard gates and a scheduled run |

The pattern is consistent. Data acquisition, which was the bottleneck in the 2026-11-23 gap report, is largely done: **971 adapters** are registered, including **277 parcel sources**, **102 court RSS feeds** and **24 sheriff-sale sources**. Parcels cover **51 of 51 jurisdictions** (31 statewide) and owner names are mapped in 50 ([gaps.md](../docs/gaps.md); [registry](../src/equity/adapters/registry.py)). The remaining work is mostly rules and netting: turning matched parcels into reachable equity after senior debt, exemptions, expiry and stays. Three earlier repo reports are now stale. FHFA HPI and the Census geocoder are built, although the 2026-11-25 deal-flow report lists both as unbuilt. Tennessee owners are loaded under an owner decision, although `Legal reads needed.md` still says "not loaded" ([coverage.md](../docs/coverage.md)).

## Identity, life and bankruptcy: exact keys work, death has no free file

### Q1. Who is the debtor: exact matching runs, but nothing measures its precision

Identity resolution is deterministic and conservative. Person names need at least two words, a JR/SR mismatch blocks a match, an organization is never guessed to be a person, and addresses are keyed on street plus ZIP5 under rules the owner approved on 2026-11-22 ([resolve.py](../src/equity/matching/resolve.py)). On the local New York run (2026-11-22), **978,926 of 4,631,183 debtor parties auto-matched** an owner and **55,887 went to review**. Of those review pairs, **7,082 share a standardized single-unit street segment** with the owner's mailing or situs address ([review_geo.py](../src/equity/matching/review_geo.py)). These numbers have never been checked against hand-verified cases, because `tests/golden/cases/` is empty and only the owner may write cases ([tests/golden/README.md](../tests/golden/README.md)). The `rules.yaml` fuzzy-match cutoff (92 proposed) is null and read by no code, so it matters only if a fuzzy rule is ever added. The owner should either fill it or record that matching stays exact-only.

The free identity anchors that can still be added fall into two groups. For **business and licensed debtors** they are strong: FMCSA's Company Census has **4,535,564 carriers with officer names, 3,004,243 email addresses** and phones ([FMCSA](https://data.transportation.gov/d/az4n-8mr2)). NPPES offers a monthly 1.08 GB provider file with names, mailing and practice addresses and phones ([CMS NPI files](https://download.cms.gov/nppes/NPI_Files.html)). The IRS EO BMF lists 1,984,891 exempt organizations ([IRS](https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf)). Several of these are already loaded but appear in no match run's `registries` list. For **individuals** the only broad free anchor with birth data is the voter file, which is usable in about a dozen jurisdictions (AK, AR, CO, DC, FL, MI, MS, NC, OH, WI, plus conditional ID, NJ, RI, SC and TX). FEC contributor data is barred for any commercial use ([FEC](https://www.fec.gov/updates/sale-or-use-contributor-information/)).

| Source category | Free, lawful examples | Status |
|---|---|---|
| Debtor and owner names, addresses | Lien, judgment and parcel parties | In repo, matched |
| State business registries with officers | NY, PA, CT, CO, OR, DC, IA, RI | In repo (8 states); RI has no match run |
| FL Sunbiz officers, plus FL federal tax lien filings | SFTP, password published by the state | Blocked pending owner ruling on shared login ([Legal reads](Legal%20reads%20needed.md)) |
| Other free registries | WA L&I contractor principals | Missing |
| Federal entity and person files | FMCSA census, NPPES, IRS BMF and 990 officers, SEC submissions and insiders, Form D | In repo (adapters incl. `cms_nppes.py`, `fmcsa.py`), not wired to matching |
| Professional licences | 128 licence configs (TX TDLR, FL DBPR and others) | In repo, not wired |
| Voter files (DOB or birth year) | NC, Boulder CO loaded; Ohio pending fixture; 8 request routes | In repo, not wired; most states barred |
| Address standardization | Census batch geocoder, 10,000 per batch ([Census](https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html)) | In repo; changes no match |
| Paid or restricted registries | GA, KY, WV, VA, WA, IN, OK, MN, NC, TX SOS | Blocked (paid) |
| FEC individual contributors | 52 USC 30111(a)(4) | Barred; exclude |

| Kind | Remaining task | Priority |
|---|---|---|
| Owner | Write 30–50 golden cases spanning auto, review and refused pairs in NY, CT and CO | P1 |
| Owner | Approve or reject promoting `same_segment` single-unit review pairs (7,082 in NY) to auto | P2 |
| Owner | Fill or formally retire `name_similarity_cutoff` and `min_corroborating_signals` | P3 |
| Owner/legal | Rule on the Sunbiz shared SFTP login | P2 |
| Code | Add FMCSA officers, NPPES authorized officials and IRS 990 officers as `registries`-style joins with exact keys (new rules need owner approval) | P2 |
| Code | Add an RI match run (registry exists, no run) | P3 |
| Code | Use voter DOB or birth year only as a corroborating tie-breaker in allowed states (rule needs approval) | P3 |

### Q2a. Alive: no free national file, so derive signals from data already held

**No free, lawful bulk death file exists in 2026.** The SSA public Death Master File is sold only through NTIS's Limited Access DMF. It carries a **$2,930 yearly certification fee**, plus $247 and $268 every three years, plus the subscription price ([NTIS fees](https://ntis.gov/ladmf/pay.xhtml)). Under 42 USC 1306c, deaths in the last three calendar years go only to certified persons with a fraud-prevention interest or a business purpose "pursuant to a law, governmental rule, regulation, or fiduciary duty" ([42 USC 1306c](https://www.govinfo.gov/link/uscode/42/1306c?link-type=html)). It is doubtful that a judgment buyer qualifies, and the cost is outside the free rule anyway. The CDC's National Death Index excludes "legal, administrative" uses ([CDC NDI](https://www.cdc.gov/nchs/ndi/index.html)). State death indexes are sold, for example $50 per file in Montana ([MT VSB](https://prod-dphhs.mt.gov/assets/publichealth/Epidemiology/VSU/VSBServicesandFees_2024.pdf)).

The lawful free route is indirect, and most of it can be computed from data the repo already loads. Recorder and transfer data show deeds from an "estate of" or a personal representative. Federal dockets can carry a suggestion of death. Recent activity in any source is a proof-of-life signal: a new deed, a new mortgage, a licence renewal, a new FMCSA MCS-150 date, or a new voter registration. Cook County publishes medical-examiner tables that carry names (Unclaimed Persons, Indigent Cremations) ([Cook Unclaimed Persons](https://datacatalog.cookcountyil.gov/d/jmub-3h99)). Probate has no free bulk index anywhere, so it remains a per-name portal check in the debtor's county.

| Source category | Free, lawful examples | Status |
|---|---|---|
| SSA DMF / LADMF, full DMF, NDI | NTIS certification; Treasury Do Not Pay; CDC | Blocked (paid, certified, or government only) |
| State death indexes | Sold per file | Blocked (paid) |
| Estate deeds and personal-representative instruments | ACRIS, PA RTT, FL OR, VT PTT, MD SDAT grantor names | In repo, no logic reads them for death |
| Medical-examiner open data with names | Cook County IL | Missing (narrow) |
| Court-docket death signals | Federal RSS and CourtListener dockets | Partial (federal only) |
| Probate filings | County portals, newspaper notice-to-creditor sites | Per-case manual only; no bulk; obituary aggregators not scraped |

| Kind | Remaining task | Priority |
|---|---|---|
| Code | Add a `deceased_signal` and a `last_activity_date` per person, using deterministic text rules on grantor and doc-type strings ("ESTATE OF", "PERSONAL REPRESENTATIVE", "AFFIDAVIT OF DEATH") and the latest dated record across sources; the rule list needs owner approval | P2 |
| Code | Write a per-case probate checklist (county portal URL per county) into the dossier for parcel-confirmed targets | P3 |
| Owner | Approve the death-signal string list; decide that LADMF stays out (cost and eligibility) | P3 |
| Legal | Only if LADMF is reconsidered: whether a judgment buyer meets 1306c(b)(2) | P3 |

### Q2b. Bankruptcy: forward screening works, history does not

The screen matches debtor names to bankruptcy debtors from **102 free CM/ECF RSS feeds polled every 2 hours**. Every flag goes to review, and status (open, dismissed, discharged) comes from the docket text seen since polling began ([bankruptcy.py](../src/equity/matching/bankruptcy.py)). Feeds hold about a day, so **any case filed before polling began is invisible**. Four states have no bankruptcy feed the project may read: AR, MD, NM and UT, whose robots.txt disallow it ([courts.yaml](../config/courts.yaml)). One discrepancy needs noting. The 2026-11-23 probe found full feeds at mdb, nmb and utb, but the repo's robots list disallows them, and robots.txt wins.

Three free sources would close most of the history gap. CourtListener's quarterly `dockets` bulk file (5.1 GB, debtor names in `case_name`) backfills named cases ([CourtListener bulk](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/dockets-2026-09-30.csv.bz2)). Its licence is unresolved: the footer says CC BY-ND and the terms page returned 403. The FJC Bankruptcy IDB covers every petition since 2007-10-01 with chapter, discharge, disposition, **REALPROP** (Schedule A real-property total), debtor ZIP and county. It has **no names**, but it joins to named dockets on district, office and docket number ([FJC IDB](https://www.fjc.gov/research/idb/bankruptcy-cases-filed-terminated-and-pending-fy-2008-present)). PACER's Case Locator is the only authoritative national name check. It bills **$0.10 per 54-row page**, waives fees when a quarter totals **$30 or less**, and offers a free non-billable QA environment for building the client ([PCL API guide](https://pacer.uscourts.gov/sites/default/files/files/PCL-API-10-2026.pdf); [PACER pricing](https://pacer.uscourts.gov/pacer-pricing-how-fees-work)). The repo's PACER guard exists, but there is no client, and the null ceiling refuses everything ([pacer.py](../src/equity/pacer.py)).

| Source category | Free, lawful examples | Status |
|---|---|---|
| CM/ECF RSS (new petitions, discharges) | 56 full bankruptcy feeds nationally | In repo (102 feeds, bankruptcy and district) |
| Historical named dockets | CourtListener quarterly bulk | Missing; licence read needed |
| Chapter, discharge, real-property totals | FJC Bankruptcy IDB (`cpbank18on.zip`, 887 MB) | Missing |
| Authoritative name search | PACER PCL API ($30/quarter waiver) | Guard built, client missing, ceiling null |
| CourtListener REST API | 5/min, 50/hr, 125/day per account ([FLP](https://free.law/2026/05/07/api-included-in-memberships/)) | Missing; one account only |
| Claims-agent registers (Kroll, Epiq, Stretto) | Per-case | Blocked (robots, bot walls) |
| Robots-disallowed feeds (AR, MD, NM, UT and others) | — | Blocked; honour robots |

| Kind | Remaining task | Priority |
|---|---|---|
| Owner | Set `pacer.yaml quarterly_ceiling` (research suggests about 28.00, under the $30 waiver) | P1 |
| Code | Build the PCL client behind `Budget.authorize()`: test in QA first, tag `X-CLIENT-CODE`, search exact last name plus court plus date range, and run only for parcel-confirmed, top-ranked targets | P1 |
| Code | FJC Bankruptcy IDB adapter, joined to named dockets on district, office and docket, to fill chapter, discharge and REALPROP | P2 |
| Legal/owner | Request written terms from Free Law Project for internal use of the bulk dockets file | P2 |
| Code | CourtListener bulk backfill into `bankruptcy`, once terms allow | P2 |
| Code | Make an open bankruptcy a hard exclusion (automatic stay, 11 USC 362) and a discharged one a separate state that still allows a surviving lien | P1 |

## Debts and enforceability: one number per state cannot hold 2021–2026 law

### Q3. What they owe: broad lien lists, thin private judgments

The repo maps **14 debt kinds** and every debtor source of every match run to one of them. These include court judgments, recorded liens, tax warrants and liens, code-enforcement liens, evictions and SBA charge-offs ([debt_kinds.yaml](../config/debt_kinds.yaml)). Status logic exists: satisfaction dates become RELEASE instruments, "(satisfied)" document types and satisfied-judgment events close a debt, and open amounts exclude releases and lis pendens ([resolve.py](../src/equity/matching/resolve.py)). Private court money judgments with free bulk access exist **only in Texas (Harris JP and district, Travis tax suits) and Florida (Hillsborough, Citrus)**. The three federal sources (FJC civil judgments, EPA ECHO) run in 68 of 70 match runs. FJC truncates names at about 30 characters and gives people as surnames only ([fjc_idb.py](../src/equity/adapters/federal/fjc_idb.py)).

The new research found no further free statewide private-judgment index. A Socrata sweep for "judgment", "abstract of judgment" and "garnishment" returned only agency and aggregate sets ([Socrata catalog](https://api.us.socrata.com/api/catalog/v1?q=judgment&only=dataset)). Clerks sell what exists. Polk FL charges **$75 a month per court division** ([Polk Clerk](https://pro.polkcountyclerk.net/PRR/Home/BulkDataSubscriber)), Miami-Dade **$110 a month per folder** ([Miami-Dade Clerk](https://www.miamidadeclerk.gov/clerk/commercial-data-services.page)), and Lee **$150–350 a year** for court lists ([Lee Clerk](https://www.leeclerk.org/services/bulk-data-services)). Under the free-only rule these stay out; a free public-records request for an existing export, charged at duplication cost, remains the lawful path. There is one concrete fix inside the repo. New York's tax-warrant and child-support-warrant datasets were re-created in mid-2025 and are now titled **"Beginning 7/1/2025"**, while the repo's configs still call them "Beginning 1982" and "Beginning 2004" ([NY catalog record](https://api.us.socrata.com/api/catalog/v1?ids=v7ua-z23v); [ny.dtf.tax_warrants.yaml](../config/liens/ny.dtf.tax_warrants.yaml)). If the history was dropped, older open warrants are silently missing. Connecticut's UCC lien file already includes IRS and Department of Labor liens ([CT](https://api.us.socrata.com/api/catalog/v1?ids=xfev-8smz)). California's weekly UCC data is reported free but is unverified ([CA SOS fee schedule](https://bpd.cdn.sos.ca.gov/ucc/ucc-fee-schedule.pdf)).

| Source category | Free, lawful examples | Status |
|---|---|---|
| Federal civil judgments | FJC IDB civil, EPA ECHO judicial | In repo (68 of 70 runs) |
| State private court judgments | Harris JP and district, Travis, Hillsborough, Citrus | In repo (TX, FL only) |
| Recorded judgments and liens (recorder indexes) | ACRIS, Hillsborough, Hernando, Putnam OR | In repo (NY, FL) |
| State tax warrants and lists | NY DTF warrants, FL DOR, VT top 100, NE | In repo; NY scope needs checking |
| HTML or PDF delinquent-taxpayer lists | WI (>$5,000), OR (≥$50,000), SC | Missing (parse by config) |
| UCC and SOS liens incl. federal tax liens | CT (IRS liens), CO, OR UCC | In repo |
| CA weekly UCC | CA SOS | Missing; free status unverified |
| County delinquent property tax and certificate lists | 87 registered | In repo; keep adding by config |
| Code-enforcement liens, evictions, SBA charge-offs | Many | In repo |
| Clerk bulk feeds (FL, ID $125/file, KY, AR) | — | Blocked (paid) |
| Ohio certificates of judgment, PA prothonotary, GA GSCCCA | — | Blocked (paid or request-only) |
| MO child-support liens | VIN only; joining needs DMV data under DPPA | Do not add |

| Kind | Remaining task | Priority |
|---|---|---|
| Code | Check the minimum `Warrant filed date` in NY `v7ua-z23v` and `8pp4-isha`; if history is gone, look for the older series IDs and fix the labels | P1 |
| Owner | Confirm every list in `doc_types.yaml` (header says "TODO(Brandon)"; release logic depends on it) | P1 |
| Code | Build a generic intake adapter for files received from public-records requests (CSV/XLSX in a private folder, with a terms tag per file) | P2 |
| Owner | Start the records-request programme for court-judgment and certificate-of-judgment indexes, Ohio clerks of courts first | P2 |
| Code | Post-judgment interest per judgment, from a dated rate table (the TX OCCC rate was **6.75%** for 2026 ([OCCC](https://occc.texas.gov/wp-content/uploads/2026/11/PostjudgmentInterestRate_History.pdf))) | P3 |
| Code | WI and OR delinquent-taxpayer list configs; verify the CA UCC terms | P3 |

### Q4. Still enforceable: the hardest gap, and the schema must change first

This is the most consequential inert layer. `sol.yaml` is "filled in by Brandon, never by code or by Claude", **0 of 51 states have any value**, and the file is CODEOWNERS-protected ([sol.yaml](../config/sol.yaml)). Even when filled, the scorer uses only `judgment_enforceable_years` as a flat number, because `people.parquet` does not carry the oldest open debt date ([score.py](../src/equity/rules/score.py)). `lien_years`, renewal and priority fields are read by no code.

A deeper problem surfaced in the statute checks: **one value per state cannot express current law**. Virginia judgments dated on or after **2021-07-01** last 10 years, extendable twice by recorded certificate to a maximum of 30, while older ones keep 20 ([Va. Code 8.01-251](https://law.lis.virginia.gov/vacode/title8.01/chapter3/section8.01-251/)). North Dakota judgments docketed after **2021-08-01** carry a 20-year lien that is then cancelled and cannot be renewed ([N.D.C.C. 28-20](https://ndlegis.gov/cencode/t28c20.pdf)). Illinois consumer-debt judgments entered from **2026-01-01** are enforceable for 15 years and "may not be revived" ([P.A. 104-0120](https://ilga.gov/documents/legislation/PublicActs/104/104-0120.htm)). Utah's 2025 law lets judgments be renewed repeatedly, keeping the original date and priority ([Utah S.B. 326](https://le.utah.gov/Session/2025/bills/enrolled/SB0326.pdf)). Arizona's 10-year rule applies only to judgments entered on or after 2013-08-03 ([A.R.S. 12-1551](https://www.azleg.gov/ars/12/01551.htm)). The unverified `sol_proposed.yaml` draft contradicts the Virginia and North Dakota texts outright.

How a judgment attaches also decides whether it touches the real property at all. In **recording states** (AZ, ID, NV, UT, MI, VT, DC, and probably CA, TX, FL, IL, CO and TN) the lien exists only once an abstract or certified copy is recorded. Arizona's statute says that failure to comply "results in the judgment not becoming a lien" ([A.R.S. 33-961](https://www.azleg.gov/ars/33/00961.htm)). In **docketing states** (NC, SC, SD, ND, MN, IA, KS, MO, NE, WA, VA, MD, DE) the court docket is the lien index. **Ohio** uses a certificate filed with the common pleas clerk ([R.C. 2329.02](https://codes.ohio.gov/ohio-revised-code/section-2329.02)). **Maine, Massachusetts, New Hampshire and Rhode Island** have no general judgment lien. The lien clock may also start at recording rather than entry: Michigan's runs 5 years from recording ([MCL 600.2809](https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-600-2809)), Nevada's 6 years from docketing ([NRS 17](https://www.leg.state.nv.us/NRS/NRS-017.html)). The model needs `lien_perfected_on` separate from `entered_on`.

No current machine-readable 50-state table exists. The White and Williams chart (rev. 2020-01-20) is the best free compilation and is out of date for at least five states ([W&W](https://www.whiteandwilliams.com/assets/htmldocuments/Judgment%20Liens%20-%20Rev%201-20-20.PDF)). Primary text was verified for 25 jurisdictions. It could not be read for CA, FL, NY, TX, PA, WI, CT, WV, OK, HI, LA and others, because those legislature hosts blocked the session.

| Source category | Free, lawful examples | Status |
|---|---|---|
| Primary statutes (official legislature sites) | 25 jurisdictions verified 2026-11-25 | Research only; not in config |
| 50-state compilations | W&W 2020, Bernstein 2016 | In `sol_proposed.yaml` (unverified, unread by code) |
| Judgment renewal or revival filings | Court dockets, recorder indexes | Missing everywhere; no source tracks them |
| Abstract or certificate recordings (lien perfection) | Recorder indexes (FL OR, ACRIS) | Partial (NY, FL) |

| Kind | Remaining task | Priority |
|---|---|---|
| Code | Correct `sol_proposed.yaml` (not CODEOWNERS-protected) for VA, ND, IL, UT, AZ, WA, OH (method "C"), KS (relates back to the petition date), MO (associate-division judgments are not liens) | P1 |
| Code (owner approval) | Propose a dated rule schema for `sol.yaml`: rules keyed by `entered_on` range and consumer or non-consumer debt, plus lien method D/R/C/X, lien start (entry or recording), renewal count and term | P1 |
| Owner | Approve the schema, then fill `sol.yaml` for all 51 jurisdictions with statutes, starting with states that have matched equity (NY, FL, TX, CT, CO, PA) | P1 |
| Code | Carry oldest and per-judgment `entered_on` and `lien_perfected_on` into `people.parquet`; compute expiry, years left and renewal window per judgment; flag "no lien on land" for X states and for recording states with no recorded abstract | P1 |
| Legal | Primary-text reads for the blocked states (CA SB 1200 rate and renewal bar, FL, NY, TX, PA) and the pending MD one-renewal rule | P2 |

## Property, value and senior debt: rich data, little netting

### Q5. What they own: the strongest layer, with company links in 7 runs

Parcel ownership is the best-covered question. Parcels are loaded in 51 jurisdictions, **owner names are mapped in 50**, and auto-matching uses the exact rules above. A rule matching a lien that names its parcel (`lien_names_parcel`) is used in 34 runs ([gaps.md](../docs/gaps.md); [resolve.py](../src/equity/matching/resolve.py)). Ownership through companies runs only where a match run has registries, which is **7 runs** (NY, PA-Allegheny, CT, CO, IA, OR, DC). It produces `owner_companies`, `debtor_companies` and `debtor_company_parcels` ([entities.py](../src/equity/matching/entities.py)). Two kinds of hole cannot be fixed with code. One is redaction: California assessor data is confidential beyond the statutory lists (R&T 408), and New Jersey blanks names under Daniel's Law ([BOE](https://boe.ca.gov/LawGuides/Property/Current/PTLG/Annt/260-0000-all.html)). The other is legal reads still open for WA, IN, AZ, MT and Genesee MI sources ([Legal reads](Legal%20reads%20needed.md)). For hidden LLC control, no free national beneficial-ownership source exists. FinCEN exempted all domestic companies from BOI reporting in March 2025 ([90 FR 13688](https://www.govinfo.gov/content/pkg/FR-2025-03-26/html/2025-05199.htm)), and New York's LLC Transparency Act data is not public ([Sidley](https://www.sidley.com/en/insights/newsupdates/2026/02/ny-llc-transparency-act-took-effect-but-governor-veto-exempts-us-formed-llcs)). Indirect signals are what is left: officer names, shared mailing or agent addresses, entity buyers in transfer files, and trust names that embed the debtor's name.

| Source category | Free, lawful examples | Status |
|---|---|---|
| Parcel layers with owners | 277 adapters, 51 jurisdictions | In repo |
| Condo unit to billing lot | NYC DOF condo units | In repo (NY only) |
| Registry officers and managers | 8 states | In repo; 7 runs |
| Entity buyers in transfer files | VT PTT, IL PTAX | In repo (VT via VCGI since 2019) |
| Owner names in CA, NJ, HI statewide, San Diego, Clark NV | — | Blocked (statute or sold) |
| WA, IN, AZ, MT, Genesee owner data | Loaded with restriction tags | Legal read pending |
| Beneficial ownership (CTA, NY LLCTA) | — | Not public |

| Kind | Remaining task | Priority |
|---|---|---|
| Code | Add registries to runs that have parcel owners but no registry join, as free registries become available; join on registered-agent or mailing address equal to the debtor's address (new rule, owner approval) | P2 |
| Code | Add a trust or LLC-name rule (entity name contains the debtor's full name), review-only, owner approval | P3 |
| Legal | Close the six open reads in `Legal reads needed.md` (WA RCW 42.56.070(9), IN IC 5-14-3-3(f), AZ 39-121.03(D), MT 2-6-1017, Genesee, Maricopa unsold liens) and update its stale TN line | P2 |

### Q6. Worth today: the index is loaded but not applied

Value today is the latest `coalesce(appraised_total, assessed_value)` per parcel ([resolve.py](../src/equity/matching/resolve.py)). Fractional and stale assessments therefore pass straight into equity. Examples are New York's locally set fractions, California's Prop 13 base, and Michigan's capped taxable value. The FHFA ZIP5 HPI adapter is built and refreshed monthly. Its own docstring says "using it in equity estimates is a separate, owner-approved step", and no matching or rules code reads it ([fhfa_hpi.py](../src/equity/adapters/federal/fhfa_hpi.py)). FHFA also publishes a **tract-level file as CSV**, which gives finer geography with no XLSX reader ([FHFA datasets](https://www.fhfa.gov/data/hpi/datasets)). Free ratio tables convert assessed value to market value in the states where fractions bite hardest. These are New York's Residential Assessment Ratios (`bsmp-6um6`) and equalization rates (`e6pv-77bh`), Connecticut's Equalized Net Grand List, and Pennsylvania's Common Level Ratio factors, for example **Allegheny 2.03** for 2026–27 ([data.ny.gov](https://data.ny.gov/api/catalog/v1?q=equalization%20rate); [PA DOR CLR](https://www.pa.gov/agencies/revenue/resources/tax-types-and-information/realty-transfer-tax/common-level-ratios.html)). The better base is the last arm's-length sale price where a transfer file gives one (MD, IL, VT, IN, CT), rolled forward by HPI. ACS median value (`B25077_001E`) is a public-domain cross-check ([Census API](https://api.census.gov/data/2024/acs/acs5/variables/B25077_001E.json)). Zillow ZHVI and Redfin are free to download, but their commercial-use terms were not readable, so treat them as **not cleared** ([Zillow metrics](https://zillowgroup.com/developers/api/public-data/real-estate-metrics)).

| Source category | Free, lawful examples | Status |
|---|---|---|
| Assessed or appraised values | Parcel layers | In repo (used as-is) |
| FHFA HPI ZIP5 | Annual | In repo, not applied |
| FHFA HPI tract (CSV), county | Annual | Missing |
| Assessment and equalization ratios | NY RAR and equalization, CT equalized list, PA CLR | Missing |
| Sale prices | MD SDAT, IL PTAX, IN SDF, VT PTT, CT CAMA, 12 `*.property_sales` | In repo, used only for transfers |
| ACS median value | Census API | Missing (cross-check) |
| Zillow ZHVI, Redfin | — | Terms not cleared; do not build |
| AVMs, MLS | — | Paid or behind logins |

| Kind | Remaining task | Priority |
|---|---|---|
| Code | Load ratio tables (NY RAR, CT, PA CLR) into a dated config read by the value step | P2 |
| Code | Write `value_today`: last arm's-length sale × HPI change since sale, else assessed ÷ ratio × HPI change since tax year; keep the raw value beside it; never overwrite | P2 |
| Owner | Approve the valuation rule and the HPI geography fallback order (tract, ZIP5, county) | P2 |
| Owner | Fill `rules.yaml valuation.assessed_ratio.WV` (or drop it in favour of the ratio table) | P3 |

### Q7. Senior debt: one run of seventy nets mortgages

`equity.py` treats a mortgage as paid when a release cites it, when a same-lot release names the borrower, or when a later deed goes to non-borrowers. It uses original amounts, so "open debt is an upper bound and equity a lower bound" ([equity.py](../src/equity/matching/equity.py)). Only NY has a `mortgages` key. In the local NY run, **31,772 mortgage lots** stayed open and **923,322 auto-matched debtors** showed positive equity. In every other run, equity is gross parcel value.

Free data to extend this is already in the repo but unused. **Philadelphia RTT** carries mortgages, assignments and satisfactions, but STATES['PA'] uses it only under `deeds` ([philadelphia_rtt.py](../src/equity/adapters/pa/philadelphia_rtt.py)). The Florida Official Records indexes (Hillsborough, Hernando, Putnam) are loaded as debt and deed sources. Maryland SDAT carries a **Mortgage** column for each of the last three transfers (#92, #112, #132), and the repo's `md.sdat.transfers_*` configs do not select it ([SDAT metadata](https://opendata.maryland.gov/api/views/ed4q-f8tm.json); [md.sdat.transfers_1.yaml](../config/liens/md.sdat.transfers_1.yaml)). Illinois PTAX line 15 gives an assumed mortgage, and Vermont's Azure blob extract adds a **financing type** (Conventional, Owner Financing, None) and history back to 2006. The repo's VCGI-based VT loader starts in 2019 and has no financing field ([VT blob](https://taxpttrpublicblob.blob.core.usgovcloudapi.net/taxpttrpublic?restype=container&comp=list)).

No free source gives a current balance on a named loan. The defensible deterministic proxy uses the original amount, or failing that the sale price × an HMDA tract and vintage LTV prior, then amortizes at the published 30-year rate and zeroes the balance on a recorded satisfaction. HMDA rounds amounts to $10,000 midpoints and has no names ([84 FR 649](https://www.govinfo.gov/content/pkg/FR-2019-01-31/html/2018-28404.htm)). Federal tax liens on real property are filed in the office each state designates, usually the county recorder, so every recorder index doubles as an IRS-lien source ([26 USC 6323](https://www.law.cornell.edu/uscode/text/26/6323)). Lien priority has a placeholder only: `priority.method: recording_date` exists, `same_day_tiebreak` is null, and no priority module exists ([rules.yaml](../config/rules.yaml)). Delinquent property tax is added to the debtor's open amount rather than subtracted from the parcel's equity, which double-counts it as an asset to the buyer.

| Source category | Free, lawful examples | Status |
|---|---|---|
| Recorded mortgages and satisfactions | NYC ACRIS | In repo, netted (NY only) |
| Recorded mortgages and satisfactions | Philadelphia RTT, Hillsborough, Hernando, Putnam OR | In repo, not netted |
| Purchase-mortgage amount | MD SDAT #92/#112/#132 | In source, not selected |
| Assumed mortgage, financing flag | IL PTAX line 15; VT PTT blob `financing` | Missing |
| LTV priors | HMDA modified LAR, FHFA NMDB (state level) | Missing |
| Property-tax liens and delinquencies | 87 lists, `lien_names_parcel` | In repo, counted as debt not senior lien |
| Federal tax liens | ACRIS personal property, CT UCC | In repo |
| Recorder indexes for King, Miami-Dade, Cook, Harris, Clark | — | Blocked (paid) |
| Maricopa recorder API | Names and codes, no amounts | Terms unconfirmed |
| Current balances, payoffs | — | Not public anywhere |

| Kind | Remaining task | Priority |
|---|---|---|
| Code | Add `mortgages: ['pa.philadelphia.rtt']` to PA and FL OR sources to FL; validate paid rules on each source's doc codes first | P1 |
| Code | Select the MD SDAT mortgage columns and treat them as open purchase-money liens until a later transfer | P1 |
| Code (owner approval) | Amortization and LTV-prior balance estimate, labelled as an estimate, beside the existing upper bound | P2 |
| Code | Subtract parcel-level tax delinquency from that parcel's equity | P2 |
| Code | Minimal priority engine: order recorded liens on a parcel by recording date and put the buyer's judgment in the stack | P2 |
| Owner | Approve the balance rule; set `same_day_tiebreak` | P2 |
| Owner | File free public-records requests to top-ranked recorder states for mortgage and satisfaction index exports | P2 |
| Code | VT blob loader (2006–2018 history and financing type); IL PTAX assumed mortgage | P3 |

## Exemptions, transfers and imminent sales

### Q8. Exemptions: equity behind a homestead is counted as reachable

Nothing in matching or scoring reads exemptions. A `homestead` boolean exists in the schema and is mapped in 13 states, and the migration comment says its legal effect "is not encoded there" (V0012). Homestead dollar figures exist only as unverified strings in `sol_proposed.yaml`, from the December 2025 NCLC table. The new research produced a sourced 2026 table. **Seven states have no dollar cap**: AR, FL, IA, KS, OK, SD and TX, plus DC. **NJ and PA give no homestead protection.** DE and MD protect a home only in bankruptcy ([NCLC Table 2](https://www.nclc.org/wp-content/uploads/2025/12/2025.12_Report_No-Fresh-Start_Table-02.pdf)). At least six amounts changed in 2026: MN $540,000, NH $400,000, OR $158,300, SC $80,125, UT $53,700 and MT about $425,829. Illinois became $50,000 ($100,000 for two or more owners) under P.A. 104-120, and Virginia's § 34-4 text confirms $50,000 plus $5,000 general plus $500 per dependent ([Va. Code 34-4](https://law.lis.virginia.gov/vacode/title34/chapter1/section34-4/); [Alper chart](https://www.alperlaw.com/asset-protection/homestead-exemptions-by-state/)).

A recorded declaration is a precondition in **NV, MT, UT and VA**, and in MA for the amount above $125,000. A Nevada home with no declaration on record "can be sold on execution" ([Alper Nevada](https://www.alperlaw.com/asset-protection/states/nevada/homestead/)). That is testable from recorder indexes. Tenancy by the entirety fully shields a home from a creditor of one spouse in FL, PA, MD, VA, DC, HI, IN, MI, MO, VT, WY, DE, NC, IL (homestead only) and MA. That matters most where the homestead cap is low or nil, as in PA, MD and VA ([Alper TBE 2026](https://www.alperlaw.com/wp-content/uploads/charts/tenancy-by-the-entirety-states-2026.pdf)). Indexed amounts change on known schedules, with the next large wave on **2027-04-01** (NY, AL, ME, VA). The table therefore needs `effective_from` dates. Federal 522(d) amounts, such as the **$31,575 homestead**, apply to cases filed through 2028-03-31 ([FR 2025-02207](https://www.govinfo.gov/content/pkg/FR-2025-02-04/html/2025-02207.htm)). No government body maintains a 50-state table. NCLC is the base, statutes and agency notices are the overlay, and Alper is a change detector only.

| Source category | Free, lawful examples | Status |
|---|---|---|
| Homestead flag on parcels | 13 states mapped | In repo, read by nothing |
| Owner-occupancy proxy | Situs address equal to owner mailing address | In repo (fields), no rule |
| Homestead amounts, acreage, declaration rules | NCLC 2025, statutes, MN Commerce notice | Missing as config |
| Recorded homestead declarations | Recorder doc types (NV, MT, UT, VA, MA) | Missing (needs recorder index) |
| TBE status | Deed vesting text, co-owner names | Missing |
| Federal 522(d) amounts | Federal Register | Missing |

| Kind | Remaining task | Priority |
|---|---|---|
| Code | Create `config/exemptions.yaml` (dated rows: state, amount, tiers, acreage, declaration required, TBE rule, exceptions such as KY's predating-debt rule and RI's bank-debt rule) prefilled from the 2026 research, marked unverified | P1 |
| Owner | Confirm each row; resolve the ME, CA and AZ conflicts | P1 |
| Code (owner approval) | Deterministic owner-occupancy rule (homestead flag true, or situs equal to mailing address); subtract the exemption from equity on owner-occupied parcels; mark unlimited states "home out of reach" | P1 |
| Code (owner approval) | TBE flag: exactly two individual co-owners sharing a surname, in TBE states, debt against one only; review-only | P2 |
| Code | Declaration check from recorder doc types where indexes exist | P3 |

### Q9. Transferred away: detection is built, its thresholds are not

`transfers.py` flags post-debt deeds on a matched parcel (auto) or in the same county (review). It marks the grantee as an organization, as having the same name, or as a nominee LLC whose registry role holder carries the debtor's name. The module calls these "leads for a fraudulent-transfer review (e.g. UVTA badges of fraud), not findings" ([transfers.py](../src/equity/matching/transfers.py)). The flags run in **16 of 70 match runs**, and the nominee check only where both deeds and registries exist (NY, CT, CO, inferred). The `nominal` flag stays NULL until the owner sets `nominal_consideration_max`. Three related-party toggles (same surname, same mailing address, debtor is member or agent of the grantee LLC) and `nominal_fraction_of_appraised` are null and **read by no code** ([rules.yaml](../config/rules.yaml)). Free transfer files with party names exist in IL (PTAX and the MyDec quarterly text files ([IDOR MyDec](https://tax.illinois.gov/localgovernments/property/mydecdatafiles.html))), IN, VT, CT and MD (grantor only). Wisconsin moved 2026 RETR data to a search-only portal behind its tax-account login, so no free bulk exists for new Wisconsin transfers ([WI DOR](https://www.revenue.wi.gov/Pages/SLF/Assessor-News/2026-02-24.aspx)). King County's sales extract is reachable but makes the downloader accept the RCW 42.56.070(9) commercial-use bar ([King County](https://info.kingcounty.gov/assessor/DataDownload/default.aspx)).

| Source category | Free, lawful examples | Status |
|---|---|---|
| Deed and transfer files with names | 40 `config/deeds/`, MD SDAT, IN SDF, IL PTAX, VT VCGI, PA RTT, ACRIS | In repo (16 runs) |
| IL MyDec text files | IDOR | Missing |
| VT 2006–2018 history | Azure blob | Missing |
| Entity formation dates | Registries | In repo, not compared with transfer date |
| King County sales | — | Legal read (not loaded) |
| WI 2026 RETR | — | Blocked (login) |

| Kind | Remaining task | Priority |
|---|---|---|
| Owner | Set `nominal_consideration_max`, `nominal_fraction_of_appraised` and the three related-party toggles | P1 |
| Code | Implement the three toggles and the fraction rule (currently unread); add "entity formed within N days before the transfer" (N is an owner value) | P2 |
| Code | Add a transfer-flag count per person to the dossier, with deed, date and consideration | P2 |
| Code | IL MyDec and VT blob history loaders | P3 |

### Q10. About to be sold: built end to end, run by hand

About **64 listing-mode sale sources** are snapshotted daily: tax sales, sheriff sales including New Jersey's CivilView, forfeited land, land banks, HUD REO and excess proceeds. `sale_watch.py` joins auto-matched parcels to listings and foreclosures with first-seen and last-seen dates ([refresh.yaml](../config/refresh.yaml); [sale_watch.py](../src/equity/matching/sale_watch.py)). No workflow runs it on a schedule. Imminent sales matter twice to a judgment buyer: a junior judgment can be wiped by a senior foreclosure, and surplus proceeds can pay it. The best new public layer found is **Stark County OH Sheriff Civil Sales**: **29,043 rows** with case number, plaintiff, defendant, parcels, **judgment amount**, appraisal, minimum bid and sale dates running into January 2027 ([Stark CivilSales](https://scgisa.starkcountyohio.gov/arcgis/rest/services/Sheriff/CivilSales/MapServer)). The repo reads a different, historic Stark service. Harris County's tax-sale layer requires a token, so it is unusable ([HCED](https://www.gis.hctx.net/arcgishcpid/rest/services/TaxSales/TaxSales_ALL/MapServer)). The auction platforms (RealAuction, LienHub, GovEase, Bid4Assets) stay off-limits.

Surplus proceeds are a direct recovery channel. After *Tyler v. Hennepin County* (2023), surplus must go back to owners ([Journal of Accountancy](https://www.journalofaccountancy.com/issues/2023/sep/surplus-from-homes-tax-forfeiture-sale-must-be-returned-to-owner-supreme-court-holds.html)). Several statutes pay recorded lienholders first. Florida's 45.032 expressly names a subordinate "judgment" lienholder ([F.S. 45.032](https://m.flsenate.gov/statutes/45.032)). Florida's tax-deed surplus pays senior liens before the owner, with claims due within **120 days** ([F.S. 197.582](https://www.flsenate.gov/Laws/Statutes/2025/197.582)). California pays lienholders of record first within **1 year** ([R&T 4675](https://california.public.law/codes/revenue_and_taxation_code_section_4675)). Nevada pays by recorded-lien priority within 1 year ([NRS 361](https://www.leg.state.nv.us/nrs/nrs-361.html)). In Georgia a bare judgment lien has been held insufficient, and Michigan limits claims to holders of a "legal interest" ([MCL 211.78t](https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-211-78t)). Surplus lists are almost all county PDFs (Sacramento, Mohave, Worcester MD, Canadian OK, Utah County). An ArcGIS Hub sweep found no surplus feature layers.

| Source category | Free, lawful examples | Status |
|---|---|---|
| Sheriff, tax, forfeiture, land-bank lists | About 64 daily listing sources | In repo |
| Stark OH civil sales with judgment amounts | ArcGIS MapServer | Missing |
| Further county layers (Albany and Oswego NY, Hubbard MN, Spartanburg and Oconee SC, Milwaukee, Otter Tail) | Hub search hits | Missing; probe needed |
| Surplus and excess-proceeds lists | GA DeKalb, NV Washoe | In repo (2) |
| Surplus lists in PDF | CA counties, Mohave AZ, Worcester MD, Canadian OK, Utah County | Missing |
| Recorded notices of default or trustee sale | Recorder indexes | Partial (NY, FL) |
| HUD loan-sale notices | Federal Register | In repo; loan files need HUD-9611 |
| Auction platforms; Harris tax-sale layer | — | Blocked (login, bot walls, token) |

| Kind | Remaining task | Priority |
|---|---|---|
| Code | Add `oh.stark.sheriff_sales` from CivilSales (listing mode); its defendants and judgment amounts are also a debt source | P1 |
| Code | Schedule `sale_watch` and `changes` after each listings refresh; alert on any matched debtor parcel newly listed | P1 |
| Code | Surplus-list adapters (PDF tables) carrying the claim deadline, ranked by days left | P2 |
| Legal | Who may claim surplus as a judgment creditor in FL, CA, NV and MN, and the GA and MI limits | P2 |
| Code | Probe and add the Hub candidates; let `discovery.yml` sweep "sheriff sale", "tax sale 2026", "tax forfeited", "excess proceeds" | P3 |
| Owner | Decide on HUD-9611 qualification | P3 |

## Contact and decision: the law decides channels, the owner decides rank

### Q11. How to reach them: addresses exist, permissions do not

Contact data today is the debtor address on the lien, the owner's mailing address on the roll, and registry officer addresses. Address fields go to the Census geocoder, which "changes no match" ([geocode.py](../src/equity/geocode.py)). Two voter files and 22 person lists (unclaimed property, rental registries, permit contacts) are loaded as locate sources, but no matching or rules code reads them. The voter request statement the project filed promises no "solicitation, mailing lists, telephone or e-mail contact" use ([voter_file_requests.md](../docs/voter_file_requests.md)). Several parcel sources carry `no_mailing_list` (ID, KS, MT) or `no_commercial_name_address_lists` (IN, WA) tags ([coverage.md](../docs/coverage.md)).

The law defines the channels more than the data does. Under the TCPA, an autodialed or prerecorded call to a cell phone needs "prior express consent", and a number found in a public registry is not consent ([47 USC 227](https://www.govinfo.gov/link/uscode/47/227?link-type=html)). Regulation F presumes compliance at no more than **seven calls in seven days** ([12 CFR 1006](https://www.govinfo.gov/content/pkg/CFR-2025-title12-vol8/xml/CFR-2025-title12-vol8-part1006.xml)). Its email safe harbor covers only addresses obtained **from the consumer or the creditor**, so a registry email gets no protection. Location calls to third parties must not mention the debt. A buyer collecting its own purchased judgments can still be a "debt collector" if collection is the business's principal purpose ([15 USC 1692a](https://www.govinfo.gov/link/uscode/15/1692a?link-type=html)). The DPPA expressly permits DMV records for "the execution or enforcement of judgments", but states charge for them, so they are outside the free rule ([18 USC 2721](https://www.govinfo.gov/link/uscode/18/2721?link-type=html)). NCOA is licensed for mailing operations only ([USPS NCOALink](https://postalpro.usps.com/mnt/glusterfs/2020-01/End_User_License.pdf)). The CFPB withdrew its credit-header proposal on 2025-05-15, so header data remains a paid, GLBA-governed product ([FR 2025-08644](https://www.govinfo.gov/content/pkg/FR-2025-05-15/html/2025-08644.htm)).

| Source category | Free, lawful examples | Status |
|---|---|---|
| Lien, roll and registry addresses | Already joined | In repo |
| Address standardization | Census geocoder | In repo |
| Voter files (allowed states) | NC, Boulder CO; FL has phone and email | In repo, not linked; use for mail needs a per-state read |
| Person lists | 22 configs | In repo, not linked |
| Business phones and emails | FMCSA census, NPPES (phones, no email) | In repo, not linked |
| NCOA | Licensed mailers | Blocked (paid, mailing only) |
| Credit header, skip-trace, DMV | GLBA/FCRA; DPPA 2721(b)(4) | Blocked (paid) |
| FEC contributors | — | Barred |

| Kind | Remaining task | Priority |
|---|---|---|
| Legal | Whether the business is an FDCPA debt collector; which states require a debt-buyer or collector licence; whether a collection demand counts as "solicitation" under the ID, NJ, SC and TX voter rules | P1 |
| Owner | Write a contact policy: mail first; hand-dialled calls only; no autodialled or prerecorded calls to cells without consent; email only after the debtor consents | P1 |
| Code | Build a `contact_points` table per person, with source, date, and the use restriction copied from source tags; the output refuses any channel a tag forbids | P2 |
| Code | Link voter, person-list, FMCSA and NPPES records to people with exact keys only (owner approval) | P2 |

### Q12. Decide and rank: every module exists, none can produce a list

The decision layer is complete as code and inert as configuration. `score.py` writes factors per person but writes a score and tier "only when every weight in `config/scoring.yaml` is set". All 11 weights are null and `tiers: []` ([scoring.yaml](../config/scoring.yaml)). Saved queries run every file in `config/private/queries/`, and that folder holds only a README ([queries.py](../src/equity/rules/queries.py)). `match.yml` is manual-only, and no workflow runs score, queries, leads, changes, sale_watch or rollup ([match.yml](../.github/workflows/match.yml)). The review queue sorts pairs into categories but "nothing here accepts or rejects a match", so there is no place to record the owner's decisions ([review.py](../src/equity/matching/review.py)). The ranking should not be purely additive. Four conditions are binary disqualifiers, and a weighted score should never outrank them: an open bankruptcy, an expired judgment, no lien on land in a state where one is required, and a homestead that covers all the equity.

| Kind | Remaining task | Priority |
|---|---|---|
| Owner | Fill the 11 scoring weights and the tiers; write `buyer.yaml` and at least one saved query | P1 |
| Code | Hard gates before the score: open bankruptcy, expired, no lien perfected, exemption ≥ equity, deceased signal; each gate reports its reason | P1 |
| Code | A per-debtor dossier: one row answering all twelve questions with source and date for each answer, plus "unknown" where no source exists | P1 |
| Code | A scheduled workflow running match → score → queries → sale_watch → changes for states that fit the runner, with counts-only summaries | P2 |
| Code | A review-decision file (owner accept or reject per pair), read on the next run, with an audit trail | P2 |
| Code | A golden test runner that fails CI when a hand-verified case changes outcome (cases themselves are owner-only) | P2 |

## One prioritized task list

The order puts first whatever stops the buyer from paying for an uncollectable judgment across every debtor: expiry, stays, missing liens, senior debt and exemptions. Next come tasks that produce a ranked list. Last come coverage gains. "Owner" means a config value, approval or decision only the owner can make. "Legal" means a statute or terms read, or an access ruling. Code tasks that change a matching rule or a CODEOWNERS file are marked as needing approval.

| # | Kind | Task | Question | Why it ranks here | Depends on |
|---|---|---|---|---|---|
| 1 | Code | Correct `sol_proposed.yaml` (VA, ND, IL, UT, AZ, WA, OH, KS, MO) and propose a dated `sol.yaml` schema (entry-date ranges, consumer flag, lien method D/R/C/X, lien start, renewals) | 4 | Without it the owner would fill a schema that cannot express current law | — |
| 2 | Owner | Approve the schema and fill `sol.yaml` with statutes, top equity states first | 4 | Stops purchases of expired or unsecured judgments; unblocks `sol_years_left` | 1 |
| 3 | Code | Per-judgment `entered_on` and `lien_perfected_on` into people; compute expiry, years left, renewal window; "no lien" for ME, MA, NH, RI and unrecorded abstracts | 4 | Makes item 2 do something | 2 |
| 4 | Owner | Write 30–50 golden cases | 1, 12 | Only way to measure match precision before money moves | — |
| 5 | Owner | Fill scoring weights, tiers, `buyer.yaml`, first saved query | 12 | Turns about a million NY matches into a ranked list | — |
| 6 | Code | Hard gates (bankruptcy open, expired, no lien, exemption ≥ equity, deceased signal) and the per-debtor dossier | 2, 4, 8, 12 | Disqualifiers must not be outweighed by a large balance | 3, 9 |
| 7 | Owner | Set `pacer.yaml quarterly_ceiling` (about 28.00) | 2b | Enables the only authoritative bankruptcy check within the free waiver | — |
| 8 | Code | PCL client behind the budget guard, QA environment first, only for top-ranked parcel-confirmed targets | 2b | Final pre-purchase stay check | 7 |
| 9 | Code + Owner | `config/exemptions.yaml` (dated, prefilled, unverified), owner confirms; owner-occupancy rule; subtract from equity | 8 | Equity in FL, TX and other unlimited states is counted as reachable today | — |
| 10 | Code | Net mortgages from Philadelphia RTT and FL OR; read MD SDAT mortgage columns | 7 | Free data already loaded; cuts overstated equity in three more states | — |
| 11 | Owner | Confirm `doc_types.yaml` lists | 3, 7 | Release and satisfaction logic depends on them | — |
| 12 | Code | Check the NY tax and child-support warrant series scope (Beginning 7/1/2025) and fix the configs | 3 | Older open warrants may be silently missing | — |
| 13 | Legal | FDCPA status, state collector and debt-buyer licensing, voter-address use for collection mail | 11 | Must precede any outreach | — |
| 14 | Owner | Contact policy (mail first, hand-dial, no autodial to cells, email only with consent) | 11 | Keeps outreach inside TCPA and Reg F | 13 |
| 15 | Code | Schedule match → score → queries → sale_watch → changes; alert on newly listed matched parcels | 10, 12 | Sale and foreclosure deadlines are missed when runs are manual | 5 |
| 16 | Code | Add Stark OH CivilSales (listing mode and debt source) | 3, 10 | Judgment amounts and future sale dates in one public layer | — |
| 17 | Owner | Set transfer thresholds and related-party toggles | 9 | `nominal` flag is NULL everywhere today | — |
| 18 | Code | Implement the three unread related-party toggles, the fraction rule and entity-formed-before-transfer | 9 | Completes fraudulent-transfer leads | 17 |
| 19 | Code + Owner | Ratio tables (NY RAR, CT, PA CLR) and `value_today` with FHFA roll-forward; owner approves the method | 6 | Fractional assessments understate or overstate equity by multiples | — |
| 20 | Code | FJC Bankruptcy IDB adapter joined on district, office and docket | 2b | Free chapter, discharge and REALPROP since 2007 | — |
| 21 | Legal + Code | Get written CourtListener bulk terms; then backfill named dockets | 2b | Closes the pre-polling blind spot | — |
| 22 | Code + Owner | Balance estimate (amortized original amount, HMDA LTV prior), approved rule; subtract parcel tax delinquency; minimal priority stack; set `same_day_tiebreak` | 7 | Moves equity from a lower bound to an estimate | 10 |
| 23 | Legal | Surplus-claim rights (FL 45.032 and 197.582, CA 4675, NV 361.610, MN, GA, MI) | 10 | A new recovery channel with hard deadlines | — |
| 24 | Code | Surplus-proceeds PDF adapters with claim deadlines | 10 | Ranks claims before they expire | 23 |
| 25 | Code + Owner | Death signals (estate deeds, "personal representative", last activity date); owner approves strings | 2a | Avoids buying against the dead without a paid DMF | — |
| 26 | Legal | Close the open reads: WA, IN, AZ, MT, Genesee, King County, Maricopa; update the stale TN line | 5, 9, 11 | Several loaded sources carry unresolved use limits | — |
| 27 | Owner/Legal | Rule on the Sunbiz shared SFTP login | 1, 3, 5 | Largest free registry left, plus FL federal tax lien filings | — |
| 28 | Owner | Start public-records requests (Ohio clerks for certificates of judgment; FL and other top recorder states for mortgage and judgment indexes) | 3, 7 | The only free path to private judgments outside TX and FL | — |
| 29 | Code | Records-request intake adapter with per-file terms tags | 3, 7 | Lets delivered files enter the lake safely | 28 |
| 30 | Code | `contact_points` table with source restriction tags enforced; link voter, person-list, FMCSA and NPPES records with exact keys (approval) | 11 | Uses locate data already loaded, within its terms | 13, 14 |
| 31 | Code | Join FMCSA officers, NPPES officials and IRS 990 officers as registries; add an RI match run | 1, 5 | More company-held parcels | — |
| 32 | Owner | Approve or reject promoting `same_segment` single-unit review pairs | 1 | About 7,000 more NY matches if approved | 4 |
| 33 | Code | Review-decision file and golden test runner in CI | 1, 12 | Records owner rulings; guards regressions | 4 |
| 34 | Code + Owner | TBE co-owner flag (review-only) and homestead-declaration check | 8 | Shields in PA, MD, VA where caps are low | 9 |
| 35 | Code | Post-judgment interest from dated rate tables | 3 | Correct claim amounts | 2 |
| 36 | Code | VT blob history and financing type; IL MyDec; IL PTAX assumed mortgage | 7, 9 | Deeper transfer history, cash-purchase signal | — |
| 37 | Legal | Primary-text reads for states whose hosts were blocked (CA SB 1200, FL, NY, TX, PA) and MD's pending renewal cap | 4 | Moves unverified `sol.yaml` rows to verified | 1 |
| 38 | Code | Probe Hub candidates; extend discovery sweeps; WI, OR delinquent lists; CA UCC once terms verified | 3, 10 | Incremental coverage | — |
| 39 | Owner | Decide on HUD-9611 qualification and any paid feed (outside the free rule) | 10, 12 | Deal flow, not debtor answers | — |

## Conclusion

The research changes what "missing data" means for this business. The binding constraint is not coverage, because parcels, owners and debt lists already reach every state. It is the absence of the legal arithmetic that converts a matched parcel into collectable equity. That arithmetic is expiry by entry date, lien perfection by attachment method, exemption by occupancy and marriage, and stays by bankruptcy status. Every piece of it is deterministic and encodable from public statutes, which suits the no-AI rule. Every piece also needs the owner's signature, because it lives in CODEOWNERS files or matching rules. The fastest gain therefore comes from Claude drafting dated, sourced tables (judgment life, exemptions, ratios) that the owner can approve row by row, rather than from adding sources.

Two second-order points follow. First, a judgment's value is now date-sensitive in ways a per-state number hides. An Illinois consumer judgment entered in 2026 cannot be revived. A Virginia judgment from 2022 dies at 10 years unless a certificate is recorded. A Utah renewal keeps its priority. Pricing must therefore read the entry date, not just the state. Second, the free-data ceiling is real but narrow. Death, current loan balances and private judgments outside two states will stay per-case checks, done through PACER's $30 waiver, county probate portals and public-records requests. The pipeline's job is to rank who deserves those checks, and it cannot do that until the owner fills the configs.
