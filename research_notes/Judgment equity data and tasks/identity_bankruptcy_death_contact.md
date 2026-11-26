# Free, lawful US data for a judgment buyer: who the debtor is, whether alive, whether bankrupt, how to reach them (as of 2026-11-25)

Research date: 2026-11-25. This is research for internal planning, not legal advice.

**Tags.** **[LIVE]** means I fetched or queried the primary source this session. **[SEARCH]** means search-result snippets only. **[PRIOR NOTES]** means the finding was verified live in an earlier round of this project; the file is named and the original source URL is kept. **[UNVERIFIED]** means my background knowledge, not confirmed this session.

**Hosts blocked from this session.** These returned 403 or Akamai "Access Denied", so I did not guess at their content: `www.ssa.gov/dataexchange/*` and `www.ssa.gov/news/*`, `www.gao.gov/products/*`, `www.legacy.com` (terms of use), and `www.sec.gov/os/accessing-edgar-data`. `www.ntis.gov/dmf` returned 404; the live LADMF pages are under `ntis.gov/ladmf/`. In earlier rounds `www.courtlistener.com/terms/` and `justice.gov/ust/*` also returned 403. Earlier rounds could not reach `ncsl.org` or `eac.gov` either.

**Related project notes (already verified; this file summarizes them and does not repeat them):**
- `research_notes/Data source gap analysis/courts.md`: probe of all 187 CM/ECF RSS feeds, CourtListener bulk data and API, FJC bankruptcy IDB, claims agents, probate.
- `research_notes/Data source gap analysis/entities_money.md`: state SOS bulk files, SEC, IRS EO BMF, UCC.
- `research_notes/Voter file access by state/*.md`: a verdict for all 50 states plus DC, with verification passes.
- `research_notes/Voter file access by state/alternatives.md`: license files, unclaimed property, NCOA.

---

## 1. Bankruptcy: is the debtor in bankruptcy, or discharged? (CM/ECF RSS, PACER/PCL, CourtListener/RECAP, FJC IDB)

### Takeaway
Bankruptcy can be screened for free by combining three sources:
- **CourtListener's quarterly bulk `dockets` file:** free, no login, has debtor names.
- **Daily polling of CM/ECF RSS feeds:** 56 of 93 bankruptcy courts publish full "all entries" feeds.
- **The FJC Bankruptcy IDB:** free. It records chapter, discharge or dismissal, Schedule A real-property totals, and debtor ZIP code and county, but **no names**. It joins to named cases on district, office and docket number.

PACER, including the PACER Case Locator (PCL) API, is the only paid source. It bills $0.10 per page, and a PCL results page holds 54 rows. Fees are waived when a quarter's charges total $30 or less. That buys about 300 pages a quarter, which is about 16,200 PCL result rows, or about 10 documents billed at the $3 cap. CourtListener's free API tier is now 5 requests a minute, 50 an hour and 125 a day. Its commercial license terms are still unresolved.

### Cited Findings
**Source catalog: bankruptcy**

| Source | Access method | Account/key | License / commercial reuse | Coverage | Update | Notes |
|---|---|---|---|---|---|---|
| CM/ECF RSS (`https://ecf.<court>.uscourts.gov/cgi-bin/rss_outside.pl`) | RSS 2.0, about a 24-hour window | None | Public court records; no license stated | Per court. Full feeds in 56 bankruptcy and 50 district courts | Continuous; must be polled daily | Petitions, discharges and "Transfer of Claim" entries appear in full feeds |
| CourtListener bulk data (`dockets-YYYY-MM-DD.csv.bz2`, S3) | Bulk CSV (5.1 GB compressed) | None | Unresolved: site footer says CC BY-ND 4.0; terms page returns 403 | National federal courts, including bankruptcy | Quarterly (latest 2026-09-30) | Debtor names are in `case_name` |
| CourtListener REST v4 / RECAP APIs | REST API | Free account; one account per person or organization | FLP terms; commercial agreements offered | National | Live | Free tier 5/min, 50/hr, 125/day |
| FJC Bankruptcy IDB | Bulk SAS/text zip | None | US government work [UNVERIFIED: no license text read] | Every petition since 2007-10-01, all districts | About twice a year (latest snapshot `cpbankjun26`) | No debtor names |
| PACER / PCL API | REST (JSON/XML); immediate and batch searches | Paid PACER account; separate free QA account for testing | PACER policies; one account per user | National index | Live | $0.10/page; 54 rows per PCL page; $30/quarter waiver |
| uscourts.gov F-2 tables | PDF/Excel | None | Public | National aggregates | Quarterly | Aggregates only, no cases |

- [PRIOR NOTES, LIVE 2026-11-23] A probe of 187 RSS endpoints found **full ("all") bankruptcy feeds at 56 courts**: akb alsb areb azb caeb canb casb cob ctb deb flnb ganb gub iasb ilcb ilnb ilsb insb ksb kyeb kywb lamb lawb mdb mieb mnb moeb ncmb ndb neb nmb nvb nynb nysb ohnb ohsb paeb pamb pawb prb rib scb sdb tneb tnmb tnwb txnb txwb utb vaeb vtb waeb wawb wiwb wvsb wyb.
  - 28 bankruptcy courts have partial feeds (for example cacb, flmb, njb, mab, orb).
  - 3 return an empty body: miwb, nceb, nyeb.
  - 6 return 404 or 500: alnb, dcb, flsb, ianb, txsb, wvnb.
  - "Voluntary Petition" entries appeared in 44 bankruptcy feeds in a single day.
  - Source: `courts.md` §2. A 2020 count is in [LLRX 2020](https://www.llrx.com/2020/09/rss-feeds-pacer-and-the-fight-for-access-to-federal-docket-information/).
- [PRIOR NOTES, LIVE] PACER pricing quotes:
  - "$0.10 per page… You won't be charged more than $3 per document".
  - "Spend $30 or less on court records in a quarter and fees are WAIVED".
  - Search results are billed by pages generated, "even if the search displays 'no matches found'", with "no maximum fee for these searches".
  - "Court opinions are always free". Courthouse public terminals are free.
  - Source: [PACER pricing](https://pacer.uscourts.gov/pacer-pricing-how-fees-work). I re-fetched the page live on 2026-11-25 and the search-billing text is unchanged.
- [LIVE] PCL API guide (October 2026 edition):
  - "All searches in the Production environment are billable."
  - "Immediate searches return results in groups of 54. Each group of immediate search results is referred to as a 'page.' The maximum search result size for an immediate search is 5,400 items… or 100 pages." Batch searches return one downloadable result set.
  - A free QA environment (`qa-pcl.uscourts.gov`) holds "a subset of test PCL data and searches are not billable."
  - An `X-CLIENT-CODE` header lets you tag billing transactions.
  - Source: [PCL API User Guide 10-2026](https://pacer.uscourts.gov/sites/default/files/files/PCL-API-10-2026.pdf); [PACER developer resources](https://pacer.uscourts.gov/file-case/developer-resources).
- [PRIOR NOTES, LIVE] On 2026-05-07 FLP opened all APIs, including the PACER APIs, to any CourtListener member. The new default limits are "5 requests per minute, 50 requests per hour, and 125 requests per day". "Creating more than one account per project, person, or organization is forbidden." Sources: [FLP blog 2026-05-07](https://free.law/2026/05/07/api-included-in-memberships/); [REST v4 overview](https://wiki.free.law/c/courtlistener/help/api/rest/v4/overview).
- [PRIOR NOTES, LIVE] Paid membership tiers run from $10 to $100 a month (10 to 25 requests a minute, 300 to 1,400 a day). Membership API access "is not for large or funded organizations." Source: [FLP membership](https://free.law/membership/).
- [PRIOR NOTES, LIVE] RECAP Fetch is free to call but buys from PACER with your own PACER credentials, at up to 30 requests a minute. Source: [RECAP APIs](https://wiki.free.law/c/courtlistener/help/api/rest/v4/recap).
- [PRIOR NOTES, LIVE] CourtListener also collects free PACER case metadata: "For bankruptcy cases… the assigned judge, bankruptcy chapter, date the plan was confirmed, and date the debtor was discharged." Source: [Federal cases coverage](https://wiki.free.law/c/courtlistener/help/data-coverage/federal-cases-and-filings).
- [PRIOR NOTES, LIVE] Bulk `dockets-2026-09-30.csv.bz2` is 5.1 GB. In the first 40 MB, 34% of rows were bankruptcy cases, with names such as "Randall Dean Adkins and Tina Ruth Adkins" (kyeb, filed 2026-03-05). Sources: [dockets bulk](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/dockets-2026-09-30.csv.bz2); [schema](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/schema-2026-09-30.sql).
- [PRIOR NOTES, LIVE] The FLP footer reads "Content licensed under a Creative Commons BY-ND international 4.0, license, except where…". The terms page returned 403. Source: [free.law](https://free.law/membership/).
- [PRIOR NOTES, LIVE] FJC Bankruptcy IDB:
  - Covers "all petitions filed under the Bankruptcy Code on or after October 1, 2007".
  - `cpbank18on.zip` is 887 MB, last modified 2026-09-02.
  - Fields include CASEKEY, DISTRICT, OFFICE, DOCKET, FILEDATE, chapter, D1ZIP, D1CNTY (FIPS), REALPROP, TOTASSTS, SECURED, TOTLBLTS, DSCHRGD/NDSCHRGD, CLOSEDT and D1FDSP (disposition).
  - **There is no debtor-name field.**
  - Sources: [FJC bankruptcy IDB](https://www.fjc.gov/research/idb/bankruptcy-cases-filed-terminated-and-pending-fy-2008-present); [codebook](https://www.fjc.gov/sites/default/files/idb/codebooks/Bankruptcy%20IDB%20Online%20Codebook%20rev%2002282023.pdf).
- [PRIOR NOTES, SEARCH] 11 U.S.C. § 107(a): bankruptcy papers are "public records and open to examination… without charge". That means in person, not free PACER. Source: [11 USC 107](https://uscode.house.gov/us/usc/119-138/t11/s107/).
- [PRIOR NOTES, LIVE] Chapter 11 claims agents (Kroll and others) post schedules and claims registers free per case. Kroll's robots.txt disallows `/*/Home-ClaimInfo` and its PDF paths, and Epiq and Stretto use bot walls. Source: [Kroll robots.txt](https://restructuring.ra.kroll.com/robots.txt).
- [PRIOR NOTES, SEARCH] US Trustee data offers only aggregate enforcement tables, and justice.gov/ust returned 403. Source: [USTP enforcement activity](https://www.justice.gov/ust/bankruptcy-data-statistics/ustp-enforcement-activity).

### Inferences
- Recommended free pipeline:
  1. Load the bulk `dockets` file quarterly to backfill named cases.
  2. Poll the 56 full feeds plus the partial feeds that include `caseupld`/`court` daily for new petitions and discharges.
  3. Join to the FJC IDB on court, office and docket number to get chapter, discharge, REALPROP and county.
  4. Use the CourtListener API (125 calls a day) only for parcel-confirmed targets.
  5. Use PACER/PCL last, under a spend tracker that stays at or below $30 a quarter.
- For courts with no feed or a dead feed (flsb, txsb, nyeb, nceb, miwb and others), coverage depends on CourtListener and PCL.
- A PCL party-name search is the only authoritative national "is this person in bankruptcy?" check. At 54 rows per page, a targeted name search usually costs $0.10 to $0.30. The waiver covers roughly 100 to 300 targeted lookups a quarter if they are kept narrow (court, date range, exact last name). This is my estimate.
- Why it matters legally [UNVERIFIED]: the automatic stay (11 USC 362) bars enforcing the judgment once a petition is filed. A Chapter 7 discharge removes personal liability, but a judgment lien on non-exempt real property can survive unless it is avoided under § 522(f).
- CC BY-ND, if it applies to the bulk files, would bar redistributing derivatives. Internal use for screening is the low-risk reading. Get written terms before republishing any CourtListener-derived data.

### Gaps
- CourtListener's full terms of service, and whether its bulk files carry CC BY-ND or a public-domain mark. The terms page returned 403 in every round.
- Whether PCL **batch** searches are billed per 54-row page like immediate searches. The guide refers billing to the pricing page, which does not say.
- No state-level or third-party free bulk bankruptcy dataset with names was found beyond CourtListener. The FJC IDB is anonymized.
- Whether the dead feeds (flsb, txsb, ianb) moved to NextGen paths.

---

## 2. Death: is the debtor alive? (SSA DMF/LADMF, state indexes, probate, obituaries)

### Takeaway
**There is no free, lawful bulk national death file in 2026.**
- **LADMF:** the SSA public Death Master File is sold only through NTIS's Limited Access DMF (LADMF) program. It costs a **$2,930 yearly certification fee** plus attestation ($247) and firewall ($268) fees every 3 years, plus the subscription price. Under 42 USC 1306c, deaths in the last 3 calendar years go only to certified persons with a "legitimate fraud prevention interest" or a "legitimate business purpose pursuant to a law, governmental rule, regulation, or fiduciary duty".
- **Full DMF:** this version includes state-reported deaths. In 2026 Congress made Treasury's Do Not Pay access to it permanent. It is not available to private buyers.
- **National Death Index (CDC):** statistical research use only.
- **State death indexes:** generally sold, not free; Montana, for example, charges $50 per index file. Many states also restrict recent years.

The lawful free alternatives are partial: medical-examiner open data with names (Cook County, IL), free per-search probate and court portals, newspaper notices to creditors, and the debtor's own court record (a suggestion of death or a probate filing).

### Cited Findings
**Source catalog: death**

| Source | Access | Account / fee | Reuse terms | Coverage | Update | Status |
|---|---|---|---|---|---|---|
| NTIS LADMF (SSA public DMF) | Bulk file and online subscription | Certification under 15 CFR 1110; $2,930/yr plus $247 and $268 every 3 yrs, plus subscription | Certified subscribers only; resale needs a separate licensee agreement | National, SSA-reported deaths only | Weekly/monthly [UNVERIFIED] | **Not free** |
| SSA Full DMF (with state records) | Data exchange | Federal and state agencies only; Treasury Do Not Pay | Not available to private parties | National | n/a | **Not available** |
| CDC National Death Index | Application | Researchers only | "Statistical purposes"; not for "legal, administrative" use | National | Annual | **Not available** for this use |
| State vital-records death index files | Purchase per file | Fee (MT $50 per file) | Varies by state | Statewide | Varies | **Not free** |
| Cook County (IL) Medical Examiner open data | Socrata SODA API | None | County open-data terms [UNVERIFIED] | ME cases in Cook County only | Daily | Free; names only in some tables |
| Santa Clara (CA) Medical Examiner-Coroner | Socrata | None | County open-data terms | ME cases | Daily | Free; no names |
| Probate: county search portals, newspaper notice-to-creditor sites | Per-search web | None | Site terms | County | Daily | Free, but no bulk (see `courts.md` §5) |

- [LIVE] NTIS LADMF program text: NTIS "established a certification program… pursuant to Section 203 of the Bipartisan Budget Act of 2013 (Pub. L. 113-67)… regulations can be found at 15 C.F.R Part 1110." Subscribers "must have a legitimate fraud prevention interest, or have a legitimate business purpose pursuant to a law, governmental rule, regulation, or fiduciary duty." Certification and subscription are renewed every year; attestation and firewall every 3 years. Source: [NTIS LADMF](https://ntis.gov/ladmf/ladmf.xhtml).
- [LIVE] NTIS fees (non-refundable):
  - Certification Form Processing Fee $2,930.00, "Required every year".
  - Attestation Form Processing Fee $247.00, every 3 years.
  - Firewall Form Processing Fee $268.00, every 3 years "(if applicable)".
  - Paper checks are no longer accepted from 2025-09-01.
  - Source: [NTIS LADMF pay](https://ntis.gov/ladmf/pay.xhtml).
- [SEARCH] A March 2026 Federal Register notice seeks OMB renewal of the LADMF certification collection (OMB 0692-0013). NTIS publishes a Certified Persons List dated 2026-05-01. Sources: [FR 2026-06019](https://www.govinfo.gov/content/pkg/FR-2026-03-27/pdf/2026-06019.pdf); [DMF Certified List](https://ntis.gov/ladmf/ladmf_assets/DMFCertifiedList.pdf).
- [LIVE] 42 U.S.C. § 1306c(a): "The Secretary of Commerce shall not disclose to any person information contained on the Death Master File with respect to any deceased individual at any time during the 3-calendar-year period beginning on the date of the individual's death, unless such person is certified". Under § 1306c(b)(2), certification requires (A) "(i) a legitimate fraud prevention interest, or (ii) a legitimate business purpose pursuant to a law, governmental rule, regulation, or fiduciary duty", and (B) safeguards "similar to the requirements of section 6103(p)(4) of the Internal Revenue Code". Source: [42 USC 1306c (govinfo)](https://www.govinfo.gov/link/uscode/42/1306c?link-type=html).
- [LIVE] Treasury press release, 2026-07-21: the Consolidated Appropriations Act, 2021 gave Treasury "temporary access" to the Full DMF for a three-year pilot. The release continues "In February 2026, Congr[ess]…", and the snippet for the same release says that act gave Treasury permanent access. Source: [Treasury sb0569](https://home.treasury.gov/news/press-releases/sb0569).
- [SEARCH] The search snippet names the law the "Ending Improper Payments to Deceased People Act". GAO-26-107181 (2026-02-12) reviewed the pilot's first year. Sources: [GAO-26-107181](https://www.gao.gov/products/GAO-26-107181) (403 to fetch); [Treasury sb0569](https://home.treasury.gov/news/press-releases/sb0569).
- [SEARCH] SSA: "SSA provides the Department of Commerce's National Technical Information Service (NTIS) a public file of death information, which excludes state death records." Source: [SSA Requesting SSA's Death Information](https://www.ssa.gov/dataexchange/request_dmf.html) (403 to fetch).
- [SEARCH] Press reports in 2025 said SSA had added living immigrants to the DMF. I found no official SSA confirmation. Source: [Yahoo/news summary](https://www.yahoo.com/news/know-social-security-administration-listing-213950586.html).
- [SEARCH] SSA OIG (July 2026) audited undocumented removals of incorrect death postings. Source: [SSA OIG 2026-07-02](https://oig.ssa.gov/news-releases/2026-07-02-audit-finds-social-security-administration%E2%80%99s-employees-did-not-always-document-reasons-for-removing-beneficiaries%E2%80%99-incorrect-death-postings/).
- [SEARCH] CDC NDI: "NDI is not available for use by organizations or the general public for any non-statistical purposes, including personal losses, legal, administrative, or genealogical purposes." Source: [CDC NDI](https://www.cdc.gov/nchs/ndi/index.html).
- [SEARCH] Montana's Office of Vital Records says death index files "are the most frequently requested index", sold electronically for $50 per file (2024 fee schedule). Source: [MT VSB Services and Fees 2024](https://prod-dphhs.mt.gov/assets/publichealth/Epidemiology/VSU/VSBServicesandFees_2024.pdf).
- [LIVE] Socrata catalog search, "medical examiner":
  - Cook County `cjeq-bs86` "Medical Examiner Case Archive" (updated 2026-11-25): has death_date and age, but no name column in the catalog listing.
  - Cook County tables that **do** carry `name`: `jmub-3h99` "Unclaimed Persons" (updated 2026-11-19), `f9wk-2wb9` "Indigent Cremations" (2026-10-29) and `hc2f-evny` "Burial Locations" (2025-10-23).
  - Santa Clara `s3fb-yrjp` and related tables: death date, city, ZIP and cause, but no names.
  - San Diego `jkvb-n4p7`: no names.
  - Sources: [Cook ME Case Archive](https://datacatalog.cookcountyil.gov/d/cjeq-bs86); [Cook Unclaimed Persons](https://datacatalog.cookcountyil.gov/d/jmub-3h99); [Cook Indigent Cremations](https://datacatalog.cookcountyil.gov/d/f9wk-2wb9); [Santa Clara ME-C full](https://data.sccgov.org/d/s3fb-yrjp).
- [LIVE] ArcGIS also hosts the Cook County ME archive as a FeatureServer. Source: [meCaseNew_openData](https://services2.arcgis.com/I5Or36sMcO7Y9vQ3/arcgis/rest/services/meCaseNew_openData/FeatureServer).
- [PRIOR NOTES, LIVE] I found no current free bulk probate filing index on Socrata or ArcGIS. The only probate open data is archival (Santa Clara `rh64-rgza`, 1800s to 1900s). Free channels are per-search county portals, court calendars and newspaper notice-to-creditor sites. Source: `courts.md` §5; [Santa Clara rh64-rgza](https://data.sccgov.org/resource/rh64-rgza.json).
- Obituary aggregators: `www.legacy.com/about/terms-of-use` returned 403, so I could not read its terms. Per the assignment, scraping is excluded.

### Inferences
- Cost-free "alive?" screening has to be indirect. Good signals:
  - Recent activity in free sources, such as a new voter-file record where use is lawful, a license renewal, a new NPPES or FMCSA update, or a new recorded deed or mortgage.
  - A "suggestion of death" or substitution entry on a court docket.
  - A probate case found by name in the county portal of the debtor's last-known county.
  - A deed from an estate or a personal-representative instrument in recorder data.
- Do a free per-name probate portal check in the debtor's county before any PACER spend.
- LADMF eligibility for a judgment buyer is doubtful. Debt collection is not plainly a "legitimate business purpose pursuant to a law… or fiduciary duty". Some collection firms claim a fraud-prevention interest; whether that fits would need counsel. In any case it costs at least $2,930 a year, so it falls outside "free". Records older than 3 years are not restricted by § 1306c, but NTIS still sells them.
- Free genealogy indexes, such as the SSDI on FamilySearch (through about 2014) and the California Death Index 1940–1997, are search-only, carry site terms, and are stale for 2026 debtors [UNVERIFIED].

### Gaps
- The current price of a NTIS LADMF subscription, and whether NTIS still sells a non-certified file restricted to deaths more than 3 years old. ntis.gov/dmf returned 404.
- Text of the SSA 2026-10-20 press release (403).
- Whether any state publishes a free, current, named death index in bulk. None was found.
- Legacy.com and other obituary-aggregator terms (403).

---

## 3. Identity and entity resolution: who is the debtor across records?

### Takeaway
Free bulk identity anchors are strongest for **business debtors and licensed individuals**:
- **State SOS registries with free bulk:** FL Sunbiz (SFTP, quarterly and daily, up to 6 officers per entity), PA (4.2M officer rows, public domain), NY (entities plus 7.5M name-history rows), CT, CO, OR, DC beneficial owners, RI weekly.
- **SEC EDGAR** `submissions.zip`: nightly, with former names and addresses.
- **IRS EO BMF:** monthly, 1,984,891 records as of 2026-11-10.
- **Professional and occupational license files:** for example TX TDLR, updated daily, and FL DBPR.
- **NPPES:** 1.08 GB monthly file plus weekly files, with names, mailing and practice addresses, and phones.
- **FMCSA Company Census:** 4.54M carriers, with officer names, phone and email.

For individuals, voter files are the broadest source, but only about a dozen jurisdictions allow non-political commercial use. FEC individual-contributor data is **barred** for commercial use. USPS NCOA is licensed and tied to mailing. The Census Geocoder is free, with no key and batches of up to 10,000 addresses, for address standardization.

### Cited Findings
**Source catalog: identity and entities**

| Source | Access | Key? | Reuse terms | Coverage | Update |
|---|---|---|---|---|---|
| FL Sunbiz data downloads | SFTP (user `Public`, password published) | No | "free data downloads for informational purposes… as is" | FL entities, up to 6 officers | Daily and quarterly |
| PA DOS registered businesses `xvd7-5r2c` | Socrata | No | Public Domain | 4,200,322 officer rows | Periodic |
| NY DOS entities and name history `ekwr-p59j` | Socrata | No | NY Open Data terms | 7.5M name-history rows | Periodic |
| CT `ka36-64k6`, CO `4ykn-tg5h`, OR `tckn-sxa6`, DC beneficial owners | Socrata / ArcGIS | No | Open-data terms | Statewide | Periodic |
| SEC EDGAR `submissions.zip`, `company_tickers.json` | Bulk / JSON | No key; declared User-Agent | Public | SEC filers | Nightly |
| IRS EO BMF | CSV per state | No | Public | 1,984,891 exempt organizations | Monthly |
| TX TDLR license files | CSV | No | Texas PIA | Statewide licensees | Daily |
| FL DBPR licensee files | CSV | No | Ch. 119 public records | Statewide licensees | Regular |
| NPPES (NPI) | Bulk zip and NPI Registry API | No | CMS public release | National, health-care providers | Monthly full, weekly increments |
| FMCSA Company Census `az4n-8mr2` | Socrata | No (app token optional) | No license tag | 4,535,564 USDOT entities | Daily |
| Census Geocoder | REST API; batch CSV | No | US government | National | Benchmarks |
| FEC individual contributions | Bulk / API | api.data.gov key for the API | **No commercial use** (52 USC 30111(a)(4)) | National | Daily |
| Voter files | Per-state request | Varies | Varies (see below) | Statewide | Varies |

- [PRIOR NOTES, LIVE] Free statewide SOS bulk files that name people: CT (principals), DC (about 495k beneficial owners), FL (officers), PA (officers), NY (chair/CEO, organizer), OR (authorized representative), RI (one officer, weekly; unverified), CO (none), WA L&I contractors (principals with dates). Ohio, Vermont and Alaska bulk offerings could not be fetched or are paid. Sources: `entities_money.md` §1; [data.pa.gov xvd7-5r2c](https://data.pa.gov/Licenses-Certificates/Registered-Businesses-in-PA-Current-by-County-Depa/xvd7-5r2c); [FL Data Downloads](https://dos.fl.gov/sunbiz/other-services/data-downloads/); [FL Quarterly Data](https://dos.fl.gov/sunbiz/other-services/data-downloads/quarterly-data/).
- [PRIOR NOTES, LIVE] SEC data:
  - `submissions.zip` is 1.58 GB, a nightly archive of all filer JSON.
  - Per-filer JSON includes `formerNames` and business and mailing addresses.
  - Sources: [submissions.zip](https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip); [data.sec.gov example](https://data.sec.gov/submissions/CIK0000072971.json).
  - SEC fair-access limits (declared User-Agent, at most 10 requests a second) are [UNVERIFIED]: the SEC policy page returned 403.
- [LIVE] IRS EO BMF: "Updated data posting date: 11/10/2026 Record Count: 1,984,891", with CSV files by state. Source: [IRS EO BMF](https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf).
- [LIVE] NPPES files:
  - Monthly "NPPES Data Dissemination V.2 (November 09, 2026) – ZIP format (1,079.11 MB)".
  - A monthly deactivation file and weekly incremental files (for example 111626_112226, 6.08 MB).
  - "Effective 03/03/2026 NPPES will no longer support Version 1."
  - Source: [CMS NPI Files](https://download.cms.gov/nppes/NPI_Files.html).
- [LIVE] Header of the weekly NPPES `npidata_pfile` (330 columns): provider legal last, first and middle name; other names; business mailing address with telephone and fax; practice-location address with telephone and fax; and authorized-official name and telephone. **There is no email column.** Source: [NPPES weekly V2 zip](https://download.cms.gov/nppes/NPPES_Data_Dissemination_111626_112226_Weekly_V2.zip).
- [LIVE] FMCSA Company Census `az4n-8mr2`:
  - 4,535,564 records, with `rowsUpdatedAt` of 2026-11-25 11:55 UTC.
  - Columns include `legal_name`, `dba_name`, `company_officer_1`, `company_officer_2`, `phone`, `cell_phone`, `fax`, `email_address`, the `phy_*` physical address, `carrier_mailing_*` address and `mcs150_date`.
  - Non-null counts: email_address 3,004,243; company_officer_1 3,887,130; cell_phone 134,239.
  - The dataset JSON shows no license field.
  - Source: [FMCSA Company Census File](https://data.transportation.gov/d/az4n-8mr2).
- [PRIOR NOTES, SEARCH] TX TDLR publishes licensee CSVs by program, updated daily. FL DBPR offers licensee download files as public records under Chapter 119. Sources: [TDLR license file download](https://www.tdlr.texas.gov/licensesearch/licfile.asp); [DBPR readme](https://www2.myfloridalicense.com/sto/documents/readme.pdf); [DBPR public records](https://www2.myfloridalicense.com/?p=15875).
- [LIVE] Census Geocoder: single-record and batch geocoding of CSV or Excel files. "There is currently an upper limit of 10,000 records per batch file", via `https://geocoding.geo.census.gov/geocoder/<returntype>/addressbatch`. Source: [Census Geocoding Services API](https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html).
- [LIVE] FEC rules:
  - Contributor information may not be "used for soliciting contributions… or for any commercial purpose".
  - "This restriction applies only to the use of individual contributor information. Any person may compile and sell the names of political committees."
  - There is an exception for "bona fide academic research projects that do not involve the sale or use of that information for a commercial purpose."
  - Source: [FEC sale or use of contributor information](https://www.fec.gov/updates/sale-or-use-contributor-information/).
- [PRIOR NOTES] Voter files, tested for internal locate-and-link use with no solicitation or mailing:
  - **ALLOWED:** AK, AR, CO, DC, FL (full DOB, phone, email), MI, MS, NC (phone, birth year), OH, WI.
  - **ALLOWED WITH CONDITIONS:** ID (no mailing of ads or solicitations), IN county copies, NJ (requester must be a voter; solicitation ban), RI (APRA route), SC (buyer must be an SC voter; no "commercial solicitation"), TX (no use for advertising commercial products; notarized affidavit).
  - **NOT ALLOWED:** most others, including IL (felony), IA, KS, MN, MO, NE, ND, SD, IN statewide, CT (PA 26-1 § 96, signed 2026-03-03), AL (Act 2026-570, effective 2026-06-01), GA, KY, LA, TN, VA, WV, AZ, CA, HI, MT, NV, NM, OK (SB 1086), OR, UT (SB 153), WA, WY.
  - Sources: `Voter file access by state/verification_1.md`, `verification_2.md`, `midwest.md`, `southeast.md`, `west_a.md`, `west_b.md`, for example [NCSBE voter data](https://ncsbe.gov/results-data/voter-registration-data) and [AR SoS FAQ](https://www.sos.arkansas.gov/frequently-asked-questions/35).
- [PRIOR NOTES, SEARCH] USPS NCOALink is limited to "use in mailing operations to prepare Deliverables for delivery by USPS". The list owner signs a Processing Acknowledgement Form (PAF). Sources: [USPS NCOALink End User License](https://postalpro.usps.com/mnt/glusterfs/2020-01/End_User_License.pdf); [USPS PAF Guide](https://postalpro.usps.com/mnt/glusterfs/2018-12/PAF_Guide.pdf).

### Inferences
- Resolve identity in three steps:
  1. Normalize the debtor name and address with the Census Geocoder, using lat/long and the matched address.
  2. Link entity debtors to people through SOS officer files (FL, PA, NY, CT, DC) and FMCSA officers.
  3. Link individuals through license files (TDLR, DBPR, NPPES) and, in the ALLOWED states, voter files, which give the best date-of-birth or birth-year match.
- The voter-file verdicts were tested for **internal locate/link with no mailing**. Using a voter-file address to **mail a collection letter** is a separate question:
  - ID bars mailing "any advertisement or offer… or solicitation".
  - NJ and SC bar "solicitation".
  - TX bars only advertising commercial products.
  - A collection demand is arguably not a solicitation, but this has not been tested. Counsel should confirm per state before using a voter address for contact.
- FEC data should be excluded from any commercial pipeline, even for matching.
- NCOA can lawfully refresh addresses only when the buyer actually mails the debtor, for example a notice or a demand. It is not a free skip-trace lookup.

### Gaps
- Terms on the FMCSA dataset and on the NPPES files were not read in full. Neither page shows a license; both are federal releases [UNVERIFIED as public domain].
- SEC's current fair-access text (403).
- A complete 50-state list of free SOS bulk downloads. Only the states above were verified; others are paid, search-only, or unconfirmed.

---

## 4. Contact: which free sources lawfully give a phone or email, and what TCPA, FDCPA and Reg F allow

### Takeaway
Free, lawful phone and email fields exist mainly for **business and licensed debtors**:
- **FMCSA Census:** phone, cell and email; 3.0M non-null emails.
- **NPPES:** mailing, practice and authorized-official phones; no email.
- **SOS registries and license files:** addresses, sometimes phones.
- **Voter files in FL and NC:** phone, and email in FL, in states that allow the use.

The rules on using these numbers and addresses are where the risk sits:
- **TCPA § 227(b)(1)(A)(iii):** an autodialed or prerecorded call to a cell phone needs "prior express consent". A number taken from a public registry is not consent from the debtor.
- **Regulation F:** a call-frequency presumption of at most 7 calls in 7 days. Its email safe harbor (§ 1006.6(d)(4)) covers only emails obtained **from the consumer or the creditor**, so an email found in a public registry gets **no safe harbor**.
- **FCC "revoke-all" rule:** delayed again, to 2027-01-31 (DA 26-12).
- **FDCPA coverage:** a buyer collecting its own purchased judgments can still be a "debt collector" if collection is the "principal purpose" of its business.

### Cited Findings
**Free contact-field sources**
- [LIVE] FMCSA `az4n-8mr2`: `phone`, `cell_phone`, `fax`, `email_address`, `company_officer_1/2`, and physical and mailing addresses. 3,004,243 rows have email. Source: [FMCSA Company Census](https://data.transportation.gov/d/az4n-8mr2).
- [LIVE] NPPES V2: "Provider Business Mailing Address Telephone Number", "Provider Business Practice Location Address Telephone Number", "Authorized Official Telephone Number", and fax fields. No email. Source: [CMS NPI Files](https://download.cms.gov/nppes/NPI_Files.html).
- [PRIOR NOTES] The FL voter extract includes phone and email; the NC public file includes phone. Sources: `Voter file access by state/verification_1.md`; [NCSBE](https://ncsbe.gov/results-data/voter-registration-data).

**TCPA**
- [LIVE] 47 U.S.C. § 227(b)(1)(A) makes it unlawful "to make any call (other than a call made for emergency purposes or made with the prior express consent of the called party) using any automatic telephone dialing system or an artificial or prerecorded voice… (iii) to any telephone number assigned to a… cellular telephone service… unless such call is made solely to collect a debt owed to or guaranteed by the United States". Source: [47 USC 227 (govinfo)](https://www.govinfo.gov/link/uscode/47/227?link-type=html).
- [LIVE] FCC Order DA 26-12, adopted 2026-01-06, extends the waiver of § 64.1200(a)(10) "to the extent the rule requires callers to treat a request to revoke consent made… in response to one type of informational message as applicable to all future robocalls and robotexts from that caller on unrelated matters". The new date is "until January 31, 2027". The earlier date was April 11, 2026. Source: [FCC DA 26-12](https://docs.fcc.gov/public/attachments/DA-26-12A1.txt).
- [SEARCH] The other revocation rules remain in effect, such as revoking consent "by any reasonable means". Sources: [Burr & Forman](https://www.burr.com/telephone-consumer-protection-act/the-fcc-delays-effective-date-of-tcpa-revoke-all-rule-until-january-31-2027); [Orrick InfoBytes 2026-01-16](https://infobytes.orrick.com/2026-01-16/fcc-extends-robocall-consent-revocation-rule-waiver-to-january-2027/).
- [UNVERIFIED] Background:
  - *Facebook v. Duguid* (2021) narrowed "ATDS" to equipment using a random or sequential number generator.
  - *McLaughlin Chiropractic v. McKesson* (2025) held that district courts are not bound by FCC interpretations of the TCPA.
  - The prerecorded-voice prong still applies to any equipment.
  - State "mini-TCPAs" (for example Florida's FTSA) add their own limits.

**FDCPA / Regulation F**
- [LIVE] 15 U.S.C. § 1692a(6): a "debt collector" is "any person who uses any instrumentality of interstate commerce or the mails in any business the principal purpose of which is the collection of any debts, or who regularly collects… debts owed or due… another." Reg F § 1006.2(i) mirrors this. Sources: [15 USC 1692a](https://www.govinfo.gov/link/uscode/15/1692a?link-type=html); [12 CFR 1006 (govinfo CFR 2025)](https://www.govinfo.gov/content/pkg/CFR-2025-title12-vol8/xml/CFR-2025-title12-vol8-part1006.xml).
- [LIVE] Reg F § 1006.14(b)(2)(i): a collector "is presumed to comply" if it does not call a person about a particular debt "(A) More than seven times within seven consecutive days; nor (B) Within a period of seven consecutive days after having had a telephone conversation". Source: [12 CFR 1006](https://www.govinfo.gov/content/pkg/CFR-2025-title12-vol8/xml/CFR-2025-title12-vol8-part1006.xml).
- [SEARCH] Official commentary: under § 1006.14(b)(1)–(4), a "telephone call" includes ringless voicemail but "does not include sending an email or text message". Source: [CFPB Reg F interp 14](https://www.consumerfinance.gov/rules-policy/regulations/1006/interp-14).
- [LIVE] Reg F § 1006.6(d)(4), the email safe-harbor procedures, applies only where:
  - "(A) The consumer used the email address to communicate with the debt collector…", or
  - "(B) The debt collector has received directly from the consumer prior consent", or
  - "(ii) Procedures based on communication by the creditor": the creditor got the address "from the consumer", used it, and sent a prior transfer notice.
  - Source: [12 CFR 1006.6(d)(4)](https://www.govinfo.gov/content/pkg/CFR-2025-title12-vol8/xml/CFR-2025-title12-vol8-part1006.xml).
- [LIVE] Reg F § 1006.10 governs skip-tracing calls to third parties for "location information" ("place of abode and telephone number at such place; or… place of employment"). The collector must identify himself or herself individually by name, must "Not state that the consumer owes any debt", must not use postcards, and must not use language or symbols on an envelope showing a collection purpose. Source: [12 CFR 1006.10](https://www.govinfo.gov/content/pkg/CFR-2025-title12-vol8/xml/CFR-2025-title12-vol8-part1006.xml).

### Inferences
- **Phones from FMCSA, NPPES, voter files or license lists are lawful to hold and to dial by hand.**
  - Under the TCPA, calling a cell phone with an autodialer or prerecorded voice needs prior express consent. A number found in a public registry is not consent from the debtor.
  - Hand-dialed or live calls stay outside § 227(b). They are still subject to Reg F frequency and time-of-day limits (8 a.m. to 9 p.m. local, under § 1006.6(b), [UNVERIFIED wording]) if the buyer is a debt collector.
- **Emails from public registries.** Sending one is not prohibited outright, but it **gets no § 1006.6(d)(3) safe harbor** from liability for third-party disclosure. Likely safest practice: use postal mail first, then use email only after the debtor emails in or consents.
- **Business vs. consumer debt.** The FDCPA and Reg F cover consumer debts (personal, family or household purposes). A judgment on a commercial debt against an LLC or a carrier, which is what FMCSA data describes, is generally outside the FDCPA. The TCPA cell-phone rule still applies to a carrier's `cell_phone` field.
- **Is a judgment buyer a debt collector?** [UNVERIFIED] *Henson v. Santander* (2017) held that a buyer collecting debts it owns is not collecting debts "owed… another". A buyer whose business is mainly collecting purchased judgments can still meet the "principal purpose" prong. Plan to comply with Reg F for consumer judgments.
- **Do-Not-Call rules** cover telemarketing, not collection [UNVERIFIED]. The FCC Reassigned Numbers Database (paid, low cost [UNVERIFIED]) is the TCPA safe harbor for numbers that were reassigned after consent.

### Gaps
- Exact text of Reg F § 1006.6(b)(1) (inconvenient times) and the text and SMS safe harbor (§ 1006.6(d)(5)) were not pulled this session.
- *McLaughlin* (2025) and *Henson* (2017) were not fetched this session.
- State collection laws that add call caps or licensing (for example the CA Rosenthal Act, NYC and MA rules, and state debt-buyer licensing) were not researched. Several states require a license to collect purchased debt.

---

## 5. What is NOT free, why, and the lawful free alternatives (FCRA, DPPA, GLBA, 42 USC 1306c, voter limits, NCOA)

### Takeaway
The best locate data is either restricted by statute or sold: credit-header and skip-trace data (GLBA and FCRA), DMV records (DPPA), the LADMF (§ 1306c, $2,930 a year or more), the full DMF and NDI (government and research only), NCOA (licensed, mailing only), PACER documents (paid beyond the $30 quarterly waiver), state death indexes (sold), and most voter files (barred for commercial use).

The DPPA does list "execution or enforcement of judgments" as a permissible use, so a judgment buyer can **lawfully request** DMV records. But states charge fees and require a request process, so it is not free. The CFPB's 2024 proposal to treat credit-header data as consumer reports was **withdrawn on 2025-05-15**, so the status quo applies: header data sold under GLBA exceptions, and FCRA collection permissible purpose for full reports.

### Cited Findings
| Not free / restricted | Why | Lawful free alternative |
|---|---|---|
| SSA LADMF | 42 USC 1306c certification; NTIS fees $2,930/yr plus $247 and $268 every 3 yrs | Probate portals; court docket "suggestion of death"; Cook County ME named tables; recorder estate deeds |
| SSA Full DMF, CDC NDI | Government (Do Not Pay) only; NDI for "statistical purposes" only | Same as above |
| State death index files | Sold (e.g. MT $50/file); recent years often closed | Same as above |
| DMV records | DPPA (18 USC 2721): permissible use exists but states charge and gate requests | SOS, license and FMCSA addresses; voter files where allowed |
| Credit header / skip-trace data | GLBA reuse limits; FCRA if used as a consumer report; sold by bureaus | Free registries above; the debtor's own court filings (bankruptcy schedules list addresses) |
| USPS NCOALink | Licensed; "use in mailing operations" only; PAF required | Mail demand letters through an NCOA-licensed mailer (paid) or use returned-mail data; Census Geocoder for standardizing |
| PACER beyond $30/quarter | $0.10/page; $3 document cap | CourtListener bulk, API and RECAP; RSS; FJC IDB; free courthouse terminals |
| Voter files in about 38 states | State bans on commercial / non-political use, some criminal | The about 12 ALLOWED or conditional states (see §3) |
| FEC contributor data | 52 USC 30111(a)(4): no commercial use | None needed; drop it |

- [LIVE] DPPA 18 U.S.C. § 2721(b)(4) permits use "in connection with any civil, criminal, administrative, or arbitral proceeding… including the service of process, investigation in anticipation of litigation, and the execution or enforcement of judgments and orders, or pursuant to an order of a Federal, State, or local court." Source: [18 USC 2721 (govinfo)](https://www.govinfo.gov/link/uscode/18/2721?link-type=html).
- [LIVE] DPPA § 2721(b)(5) research use applies "so long as the personal information is not published, redisclosed, or used to contact individuals". Source: [18 USC 2721](https://www.govinfo.gov/link/uscode/18/2721?link-type=html).
- [SEARCH] The CFPB withdrew its 2024-12-13 FCRA data-broker proposal on 2025-05-15 (90 FR, 2025-08644). It said the rulemaking was not needed given new Bureau policies and doubts about fit with the FCRA. The proposal would have treated credit-header identifiers (SSN, address, phone) as consumer reports. Sources: [FR 2025-05-15 withdrawal](https://www.govinfo.gov/content/pkg/FR-2025-05-15/html/2025-08644.htm); [Consumer Financial Services Law Monitor](https://www.consumerfinancialserviceslawmonitor.com/2025/05/cfpb-withdraws-proposed-fcra-data-broker-rule/).
- [LIVE] 42 USC 1306c and the NTIS fees are cited in §2.
- [LIVE] The FEC restriction is cited in §3.
- [PRIOR NOTES] NCOALink field-of-use is cited in §3.
- [UNVERIFIED] FCRA 15 USC 1681b(a)(3)(A) allows a consumer report for "collection of an account". A buyer that compiles public records only for its own use, without furnishing them to third parties, is generally not a consumer reporting agency. Selling or sharing the compiled data could make it one.
- [UNVERIFIED] GLBA (15 USC 6802) restricts reuse and redisclosure of nonpublic personal information that came from financial institutions, which is the origin of credit-header data. Collection is not a free source of it in any case.

### Inferences
- A lawful, zero-cost stack for 2026:
  1. Bankruptcy: CourtListener bulk, RSS and FJC IDB, with PCL kept under $30 a quarter.
  2. Death: per-name probate and recorder checks plus court-docket signals. No free DMF exists.
  3. Identity: SOS bulk files, license files, NPPES, FMCSA, SEC, IRS BMF, voter files in the allowed states, and the Census Geocoder.
  4. Contact: postal mail to verified addresses first, hand-dialed calls to registry phones within Reg F limits, and email only after the debtor consents.
- DMV records under DPPA § 2721(b)(4) are the cheapest **lawful** paid upgrade for consumer debtors. They are outside the "free" constraint, so they are listed here for the report writer only.
- Keep any compiled locate database internal. Furnishing it to other buyers raises FCRA consumer-reporting-agency risk and breaks several voter-file and DPPA redisclosure limits.

### Gaps
- FCRA and GLBA statute text was not fetched this session (background only).
- Per-state DMV fee schedules and request forms for § 2721(b)(4) requests were not researched.
- Whether any state's obituary or probate notice site offers bulk access under terms that allow commercial reuse.
