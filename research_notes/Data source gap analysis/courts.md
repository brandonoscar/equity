# Court data gaps and the best free sources to fill them

Research date: 2026-11-23 (a Monday, so the 24-hour RSS windows mostly cover Sunday). Tags: **[LIVE]** = fetched or probed by me this session; **[SEARCH]** = search-result snippets only; **[UNVERIFIED]** = my background knowledge, not confirmed this session.

**Network note.** Unlike the earlier rounds, `curl` from the shell now reaches courtlistener.com, wiki.free.law, free.law, www.fjc.gov, every `ecf.*.uscourts.gov` host, nclc.org, Socrata and ArcGIS. The WebFetch tool still fails on some hosts (free.law: DNS failure), so I fetched pages with `curl`. Still refused: `www.justice.gov/ust/*` (403), `dm.epiq11.com`, `cases.stretto.com`, `omniagentsolutions.com` home pages (403 bot walls), `*.realforeclose.com` (403), `www.courtlistener.com/terms/` (CloudFront 403).

**What the repo already has (court side).** State: FL Hillsborough, Citrus and Hernando civil; TX Harris JP and District civil judgments; Harris tax judgments. Foreclosure: PA Allegheny filings (WPRDC), PA Washington sheriff sales, NYC (lead_bbl). Federal: ECF RSS for 9 enabled bankruptcy courts (`flmb, flsb, flnb, nysb, paeb, ohnb, njb, ganb, txnb`), the FJC IDB (CourtListener copy plus direct) and EPA ECHO judicial cases. `config/sol.yaml` has all 51 jurisdictions with every field null. No probate, claims-register or bankruptcy-schedule source is loaded.

## 1. State court judgments and foreclosures: what remains, and foreclosure filings on open data

### Takeaway
The earlier reports still hold. No state publishes named private civil money judgments in free bulk. The remaining named-judgment upside is records requests: Texas abstract indexes, Ohio certificate-of-judgment indexes, Pennsylvania prothonotaries, Florida clerks, and Georgia GSCCCA, which is paid. On foreclosures, a live Socrata and ArcGIS sweep found **no lis pendens dataset anywhere**. The best new free items are parcel-keyed foreclosure *registries*: Prince George's County MD (78,657 rows, updated 2026-07), LA City LAHD (2,761 rows for 2026, with APN and lender) and Cincinnati (7,200). There is also a free, no-login monthly Harris County Clerk foreclosure-notice search with images back to 2013-12. None of these name the borrower except old or small layers (Las Vegas 2020, South Euclid 2025).

### Cited Findings
**Carried over from the existing reports (not re-verified)**
- No state publishes general private civil money judgments in free bulk, and no city portal outside New York publishes lis pendens or civil judgment dockets — [More free judgment sources report](../../reports/More%20free%20judgment%20sources.md)
- Recorded-judgment indexes are sold or reachable only by records request: Texas abstracts (Tex. Prop. Code 52.004), Ohio certificates of judgment (ORC 2329.02), Pennsylvania prothonotaries, and Florida clerks other than Hillsborough. Georgia's GSCCCA lien index covers all 159 counties since 2004, by subscription — [Republished court judgment datasets report](../../reports/Republished%20court%20judgment%20datasets.md); [GSCCCA lien index](https://gsccca.org/learn/search-systems/lien-index)
- Still on the earlier to-do list: Harris County District Clerk public datasets; Broward OR FTP index (price unconfirmed); Pasco subscription; Franklin OH Municipal Court eviction CSVs; Debt Collection Lab state files; the NY `ww2.nycourts.gov` landlord-tenant XML; Santa Clara's CD civil index (nominal fee) — same reports.

**Foreclosure: live Socrata catalog sweep** (`api.us.socrata.com/api/catalog/v1`, queries: foreclosure, "lis pendens", "sheriff sale", "notice of default", "trustee sale", "mortgage foreclosure")
- [LIVE] "lis pendens" returns **zero** Socrata datasets. "notice of default" and "trustee sale" return nothing relevant — [Socrata catalog API](https://api.us.socrata.com/api/catalog/v1?q=lis%20pendens&only=dataset)
- [LIVE] **Prince George's County MD "County Foreclosures"** has two copies. `mnie-hrv7` holds 78,657 rows and was last updated 2026-07-28; `cni6-nr5g` holds 78,740 rows and was last updated 2026-08-31. Fields: `taxaccountnumber` (parcel key), `propertyid`, `submitteddate` (2019 to 2026-07), street address, city and zip, plus `addressoccupied`. No borrower or lender name and no amount — [PG County mnie-hrv7](https://data.princegeorgescountymd.gov/resource/mnie-hrv7.json); [cni6-nr5g](https://data.princegeorgescountymd.gov/resource/cni6-nr5g.json)
- [LIVE] **LA City LAHD Registered Foreclosure Properties.** The 2026 set (`5nzp-isg9`) has 2,761 rows and was updated 2026-10-26. A 2025 set (`2qnc-kq4g`) also exists. Fields: `apn`, `registered_date`, property type and address, `lender`, lender contact, property manager. No owner name — [LAHD 2026](https://data.lacity.org/resource/5nzp-isg9.json); [LAHD 2025](https://data.lacity.org/d/2qnc-kq4g)
- [LIVE] **Cincinnati "Vacant & Foreclosed Property Registration"** (`w3jp-dfxy`): 7,200 rows, updated 2026-11-22, with a case number, address, status and a link to the Hamilton County property-activity map — [Cincinnati w3jp-dfxy](https://data.cincinnati-oh.gov/resource/w3jp-dfxy.json)
- [LIVE] Maryland publishes Notices of Intent to Foreclose only as aggregates, by county (`w3bc-8mnv`), zip (`ftsr-vapt`) and tract (`nme2-wik5`), current to 2026-11-06. There are no addresses — [MD ftsr-vapt](https://opendata.maryland.gov/d/ftsr-vapt)
- [LIVE] Other hits are stale or aggregate: Cook County Recorder foreclosures for 2011–2012 (`epxa-9ihc`, `9br9-dhca`, with PIN and doc number); NOLA lien-foreclosure sheriff sales (ended 2018); CT monthly counts (ended 2022); Colorado 2016 counts; King County WA tax-foreclosure parcels (145) — [Cook epxa-9ihc](https://datacatalog.cookcountyil.gov/d/epxa-9ihc); [King nx4x-daw6](https://data.kingcounty.gov/d/nx4x-daw6)
- [LIVE] Oregon publishes yearly "Foreclosure Avoidance Program Beneficiary Exemption Affidavits" for 2013–2026 (`xyak-25e9` is 2026). They name lenders, not borrowers — [OR xyak-25e9](https://data.oregon.gov/d/xyak-25e9)

**Foreclosure: live ArcGIS Online sweep**
- [LIVE] **Las Vegas "Parcel_Foreclosures"**: 1,925 Clark County recorder documents (e.g. "NOTICE OF TRUSTEE SALE") with `DirectName` (the trustee or law firm), `IndirectName` (the trustor, i.e. borrower), `InstrumentNumber`, `RecordDate` and `ParcelNumber` (APN). Last edited 2020-09, so it is a format sample, not a feed — [Las Vegas layer](https://services1.arcgis.com/F1v0ufATbBQScMtY/arcgis/rest/services/Parcel_Foreclosures/FeatureServer/0)
- [LIVE] **South Euclid OH "Active Mortgage Foreclosures"**: 76 parcels with Cuyahoga `parcelpin`, deeded owner and mailing address. Edited 2025-04 — [South Euclid layer](https://services6.arcgis.com/rjcgtzQWIZbOJPXu/arcgis/rest/services/Active_Mortgage_Foreclosures_WFL1/FeatureServer/0)
- [LIVE] Philadelphia "Foreclosure_Filings" holds tract-level counts only (384 tracts, 2022) — [Phila layer](https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest/services/Foreclosure_Filings/FeatureServer/0)
- [LIVE] An ArcGIS search for "lis pendens" returns 1 item, a Las Cruces vacant-registry form, so nothing useful — [ArcGIS search API](https://www.arcgis.com/sharing/rest/search?q=%22lis%20pendens%22&f=json)

**Foreclosure: court and clerk web sources**
- [LIVE] The **Harris County Clerk "Foreclosures"** page is free, shows no login wall and has no CAPTCHA in its form. It searches posted foreclosure-sale notices by sale year and month or by document id. The page says it "Reflect(s) postings accepted through 11/20/2026" and "Images available from 12/3/2013 to Present". robots.txt disallows only `/Forms/`. It is an ASP.NET form, so a polite monthly pull is feasible — [Harris Clerk FRCL](https://www.cclerk.hctx.net/applications/websearch/FRCL_R.aspx); [robots.txt](https://www.cclerk.hctx.net/robots.txt)
- [UNVERIFIED] Texas non-judicial sale notices must be filed with the county clerk and posted at least 21 days before the first-Tuesday sale (Tex. Prop. Code 51.002(b)). Every Texas county clerk therefore holds a monthly list, and Dallas, Tarrant, Bexar and Travis also post them online.
- [LIVE] `*.realforeclose.com` returned 403 from this sandbox (Miami-Dade, Hillsborough). These are the Florida clerks' foreclosure-auction sites, which list case number, final-judgment amount, parcel id and sale date — [Miami-Dade realforeclose](https://www.miamidade.realforeclose.com/index.cfm). The field list is [UNVERIFIED] background knowledge.
- [SEARCH] Statewide newspaper public-notice websites carry foreclosure-sale notices and probate notices to creditors. A 2022 PNRC survey counted "43 press associations operating statewide public notice websites in 44 states". Florida law requires a statewide site "accessible and searchable by party name and case number" (Fla. Stat. 50.0211). Iowa Code 618.3A requires notices to be searchable and free — [PNRC survey](https://www.pnrc.net/2022/09/06/a-survey-of-statewide-public-notice-websites/); [Fla. Stat. 50.0211](https://www.flsenate.gov/Laws/Statutes/2022/0050.0211); [Iowa 618.3A](https://www.legis.iowa.gov/docs/code/2026/618.3A.pdf)

### Inferences
- A parcel-keyed foreclosure registry, such as PG County's tax account number or LAHD's APN, joins straight onto parcels. It flags "foreclosed or in foreclosure, so equity is likely gone or contested", which is a negative screen. It fits the existing `foreclosure` debt kind ("counted, not added to open amounts").
- Harris County Clerk foreclosure notices plus the already loaded Harris JP and District judgments would give Harris County a complete court-plus-foreclosure picture. Notice images carry the borrower name, but the result grid's fields were not checked. Read the result grid before building.
- Public-notice sites are the only multi-state free channel for both foreclosure notices and probate notices to creditors. They are search portals, though, and their terms have not been read, so treat them as candidates and do not crawl them blind.

### Gaps
- No free lis pendens feed exists outside NYC ACRIS and Allegheny (already loaded). I found no state that publishes judicial-foreclosure dockets as open data.
- The Harris County Clerk foreclosure result columns and terms of use were not read. I did not run a search.
- realforeclose.com terms and field layout could not be checked (403).
- Records-request targets are unchanged from earlier reports. I found nothing new free.

## 2. Federal cases: CourtListener, PACER RSS coverage, PACER fees

### Takeaway
CourtListener's **free bulk `dockets` file carries bankruptcy dockets with debtor names in `case_name`**. In a 40 MB sample, 34% of rows were bankruptcy cases, filed from 2013 through 2026. It needs no login and is the cheapest backfill for named bankruptcy debtors. The CourtListener API is now open to every account, but new free accounts get **5/minute, 50/hour and 125/day**. The terms page is still unreadable, and the site footer says CC BY-ND 4.0. A live probe of all 187 CM/ECF RSS endpoints found **106 courts with "all entries" feeds (50 district, 56 bankruptcy)**, 54 partial feeds, 18 that answer with an empty body, and 9 that 404 or 500. **`flsb`, which `courts.yaml` lists as enabled, now returns 404.** PACER charges $0.10 a page, capped at $3 a document, and waives the bill if a quarter's charges are $30 or less. That buys about 300 pages, or 10 capped documents, a quarter for free.

### Cited Findings
**CourtListener / Free Law Project**
- [LIVE] From 2026-05-07, "any CourtListener member can connect directly to all our APIs… That includes our PACER APIs, which previously required special permission". The old default of "5,000 API requests per hour" was lowered for new users. Users who had made 1,000 or more requests are grandfathered — [FLP blog 2026-05-07](https://free.law/2026/05/07/api-included-in-memberships/)
- [LIVE] Current default: "authenticated users may make up to **5 requests per minute**, **50 requests per hour**, and **125 requests per day**". "Creating more than one account per project, person, or organization is forbidden." Commercial agreements are offered — [REST v4 overview](https://wiki.free.law/c/courtlistener/help/api/rest/v4/overview)
- [LIVE] Membership API tiers: Free 5/min, 50/hr, 125/day. Tier 1 ($10/mo) 10/min, 75/hr, 300/day. Tier 2 ($25/mo) 15/min, 150/hr, 600/day. Tier 3 ($50/mo) 20/min, 250/hr, 1,000/day. Tier 4 ($100/mo) 25/min, 300/hr, 1,400/day. Membership API access "is for small law firms, small governmental bodies, legal service organizations, small media outlets, academics, and organizations that are pre-revenue and pre-funding. It is not for large or funded organizations." — [FLP membership](https://free.law/membership/)
- [LIVE] RECAP Fetch (`/api/rest/v4/recap-fetch/`) is "a free API to use, but it uses your PACER credentials to purchase… You'll still have to pay your PACER bill". It allows 30 requests a minute. PACER passwords must rotate every 180 days. Attachment pages "are free in PACER". Pray-and-Pay lets you wait until someone else buys a document — [RECAP APIs](https://wiki.free.law/c/courtlistener/help/api/rest/v4/recap)
- [LIVE] Coverage sources: CourtListener crawls court RSS feeds. Each night it downloads every document clerks mark as an opinion (free in PACER). It also scrapes free "basic case metadata… For bankruptcy cases… the assigned judge, bankruptcy chapter, date the plan was confirmed, and date the debtor was discharged." The archive gains "around 100,000 new docket entries" a day — [Federal cases coverage](https://wiki.free.law/c/courtlistener/help/data-coverage/federal-cases-and-filings)
- [LIVE] **Bulk `dockets-2026-09-30.csv.bz2` holds named bankruptcy debtors.** I decompressed the first 40 MB of the 5.1 GB file into 481,365 rows. Of those, **163,658 (34%) are bankruptcy courts**, e.g. `cacb 2:13-bk-35100 "Nelson Salvador Lucero"`, `kyeb 26-60317 "Randall Dean Adkins and Tina Ruth Adkins"` (filed 2026-03-05) and `flsb 17-23137`. Columns include `docket_number`, `docket_number_core` (e.g. `17023137`), `pacer_case_id`, `date_filed` and `date_terminated`. Bankruptcy filing years in the sample run 2013–2026, with 32,210 in 2025 — [dockets bulk file](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/dockets-2026-09-30.csv.bz2)
- [LIVE] The schema has a `search_bankruptcyinformation` table (chapter, trustee, claims bar dates, date converted or dismissed). The earlier round found it is **not** in the bulk load script — [schema-2026-09-30.sql](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/schema-2026-09-30.sql); [federal_sources.md](../More%20free%20judgment%20sources/federal_sources.md)
- [LIVE] The FLP site footer reads "Content licensed under a Creative Commons BY-ND international 4.0, license, except where…". `www.courtlistener.com/terms/` still returns 403 — [free.law](https://free.law/membership/)

**PACER RSS: live probe of `https://ecf.<court>.uscourts.gov/cgi-bin/rss_outside.pl` for 94 district and 93 bankruptcy ids** [LIVE, 2026-11-23 ~04:20 UTC]. The channel `<description>` reads "Docket entries of type: all" for full feeds and lists the types for partial ones.

| Status | District courts | Bankruptcy courts |
|---|---|---|
| **Full ("all")** | 50: akd almd alsd arwd azd cacd cand casd ctd dcd ded flmd flsd gud iasd ilcd innd ksd kywd laed lawd moed mssd mtd nced ncmd ncwd ned nhd njd nvd ohsd okwd ord paed prd rid scd sdd tned tnwd txed txsd vawd vtd waed wawd wied wiwd wyd | 56: akb alsb areb azb caeb canb casb cob ctb deb flnb ganb gub iasb ilcb ilnb ilsb insb ksb kyeb kywb lamb lawb mdb mieb mnb moeb ncmb ndb neb nmb nvb nynb nysb ohnb ohsb paeb pamb pawb prb rib scb sdb tneb tnmb tnwb txnb txwb utb vaeb vtb waeb wawb wiwb wvsb wyb |
| **Partial (types listed)** | 26: ared caed cod gamd hid iand idd ilnd ilsd insd lamd med mied miwd mnd mowd nmd nmid nynd nysd ohnd pawd tnmd txnd utd vid | 28: almb cacb flmb gamb gasb hib idb innb laeb mab meb mowb msnb mssb mtb ncwb nhb njb nmib nywb okeb oknb okwb orb txeb vawb vib wieb |
| **HTTP 200, empty body (feed off)** | 15: alnd flnd gand gasd kyed mdd msnd ndd nyed nywd oked oknd pamd vaed wvsd | 3: miwb nceb nyeb |
| **404 / 500 / timeout** | 3: mad (timeout twice) txwd (404) wvnd (500) | 6: alnb (500, then 404 on retry) dcb flsb ianb txsb wvnb (404) |

- [LIVE] Typical partial-feed types: most bankruptcy partials list `answer,appeal,court,motion,order` (gamb, idb, msnb, mtb, ncwb, vawb, nmib). Some add `misc,caseupld,trustee,plan` (flmb, njb, okeb, orb, wieb). gasb gives only `order` and meb only `answer`. District partials are mostly `order,order-cr,motion[,cmp]` — same probe.
- [LIVE] On Sunday's window, "Voluntary Petition" entries appeared in 44 bankruptcy feeds, led by cacb 52, caeb 19, mdb 16, tnwb 12 and nynb 12. Partial feeds that include `caseupld` or `court` still carried petitions (flmb 7, njb 2, almb 2). District full feeds carried "Judgment" entries (e.g. nysd 3, txsd, ohsd, tnwd) — same probe.
- [LIVE] Several bankruptcy feeds are dominated by "BNC Certificate of Mailing" noise (e.g. okwb 138 of 138, gamb 252 of 253). Feed size does not equal new-case volume — same probe.
- [SEARCH] A 2020 LLRX article reported that about 70% of bankruptcy courts and 50% of district courts had full feeds. My probe gives 56 of 93 (60%) bankruptcy and 50 of 94 (53%) district, so the order of magnitude matches — [LLRX 2020](https://www.llrx.com/2020/09/rss-feeds-pacer-and-the-fight-for-access-to-federal-docket-information/)
- [LIVE] CourtListener's own "Full / Partial / No RSS Feeds" lists render from a template (`[[ rss_feeds.full ]]`), so no static copy could be read — [Docket alerts coverage gaps](https://wiki.free.law/c/courtlistener/help/alerts/docket-alerts-for-pacer)

**PACER fees**
- [LIVE] "$0.10 per page… You won't be charged more than $3 per document". "Spend $30 or less on court records in a quarter and fees are WAIVED". "Reports that aren't case-specific and transcripts have no maximum fee." Search results are billed by pages generated, even when nothing matches. Audio costs $2.40 a file. "Court opinions are always free." Courthouse terminals are free. Courts can grant exemptions to "academic researchers, and nonprofits". Service Center requests cost $30 per name searched — [PACER pricing](https://pacer.uscourts.gov/pacer-pricing-how-fees-work)
- [SEARCH] The $3 cap equals 30 pages and also applies to case-specific reports such as the docket report, creditor listing and claims register. Courthouse public terminals view dockets and claims registers free — [txnb fee note](https://www.txnb.uscourts.gov/node/214); [flsb](https://www.flsb.uscourts.gov/node/768)
- [SEARCH] 11 U.S.C. 107(a) says bankruptcy papers and dockets "are public records and open to examination… without charge", but that is in-person examination, not free PACER — [11 USC 107](https://uscode.house.gov/us/usc/119-138/t11/s107/)
- [UNVERIFIED] The PACER Case Locator (PCL) API bills each results page at $0.10, and a page holds dozens of rows. It counts against the same $30 quarterly waiver. The per-page row count was not checked.

### Inferences
- **Gap in `courts.yaml`.** Of the 9 enabled courts, `flsb` is now 404, and `flmb` and `njb` are partial (though they still carry petitions). Five full bankruptcy feeds sit in the buyer's states and are not enabled: `ohsb, pamb, pawb, lamb, lawb`. Also not enabled but full: `ilnb, mieb, mdb, caeb, canb, casb, insb, tnwb, txwb, vaeb, kyeb, kywb, scb, ncmb`. `nceb, nyeb, miwb` have feeds switched off (empty body), and `txsb, flsb, alnb` 404. Those must come from CourtListener instead.
- **Free path for history.** Bulk `dockets` (quarterly, free, no login) gives named bankruptcy cases with court, number and dates. Polled RSS gives the daily delta. The rate-limited API gives detail only for the few dockets that matter (at most 125 calls a day free).
- **Staying under the PACER waiver.** At $30 a quarter, spend PACER money only on parcel-confirmed targets. Ten capped documents a quarter could be 10 Schedule A/B PDFs or 10 claims registers. Check CourtListener first (RECAP may hold the file free) and use Pray-and-Pay. Never run PCL name searches in bulk. One account per person is the rule both at FLP and implicitly at PACER.
- Licence: CC BY-ND forbids derivatives, if it applies to the bulk data. Commercial reuse of the bulk files is still unresolved. The bulk-data page and the footer disagree, and the terms page cannot be reached.

### Gaps
- The full CourtListener terms of service (403) and whether bulk files carry the Public Domain Mark or CC BY-ND.
- Full row count of bulk `dockets` and the bankruptcy share across the whole file. My 34% is from the first 40 MB only, which sorts by id and is not random.
- Whether the 18 "empty body" courts are disabled permanently or were failing on the day. One retry (alnd, nyed) gave the same result.
- Whether `flsb`, `txsb` and `ianb` moved RSS to another path (for example NextGen URLs).

## 3. Bankruptcy filings and schedules (A/B real property)

### Takeaway
There is no free bulk of petition or Schedule A/B *documents*. But the **FJC Bankruptcy IDB is free, current to the June 2026 snapshot, and carries `REALPROP` (Schedule A real-property total), `TOTASSTS`, `SECURED`, `TOTLBLTS`, debtor zip and county FIPS, and discharge or dismissal disposition for every case since FY2008**. It carries no names. Its `CASEKEY` (district, office, docket number) should join to the named case in CourtListener bulk dockets or ECF RSS. That join yields "named debtor plus scheduled real property value plus outcome" for free. US Trustee data pages were unreachable (403).

### Cited Findings
- [LIVE] The FJC bankruptcy IDB "include[s] all petitions filed under the Bankruptcy Code on or after October 1, 2007". Each fiscal-year snapshot has one record per case filed, terminated or pending. Files: yearly SAS zips `cpbank08`–`cpbankfy26`, `cpbankjun26`, multi-year `cpbank16to26` and `cpbank21to26`, and text files `cpbank08to17.zip` and `cpbank18on.zip`. `cpbank18on.zip` is 887,034,431 bytes, last-modified 2026-09-02. No login — [FJC bankruptcy IDB page](https://www.fjc.gov/research/idb/bankruptcy-cases-filed-terminated-and-pending-fy-2008-present); [cpbank18on.zip](https://www.fjc.gov/sites/default/files/idb/textfiles/cpbank18on.zip)
- [LIVE] Codebook (rev. 2023-02-28) fields include CASEKEY ("prefix 'BK' followed by the Circuit code, District code, Office code, Docket Number, Generation, and Sequence"), DISTRICT, OFFICE, DOCKET, FILEDATE, ORGFLCHP and CRNTCHP, ORGFLSUBCHP (Subchapter V), JOINT, D1ZIP, D1CNTY ("five digit FIPS code"), DBTRTYP, NOB, PRFILE (prior filing), ASSTCASE, SMLLBUS, **TOTASSTS** ("sum of the debtor's real property from Schedule A and… personal property from Schedule B"), **REALPROP** ("sum of the debtor's real property from Schedule A… at filing"), PERSPROP, TOTLBLTS, **SECURED** ("secured claims from Schedule D"), UNSECPR, UNSECNPR, DSCHRGD and NDSCHRGD, CLOSEDT, and D1FDSP with D1FDSPDT (final disposition). **There is no debtor-name field** — [Bankruptcy IDB codebook](https://www.fjc.gov/sites/default/files/idb/codebooks/Bankruptcy%20IDB%20Online%20Codebook%20rev%2002282023.pdf)
- [LIVE] Data caveat: FJC took the file down in August 2021 over anomalies in D1ZIP, D1CNTY and pro se fields from FY2008 through 2021-06-30. Corrected files were posted November 2021, and older downloads must be refreshed — same FJC page.
- [LIVE] Named bankruptcy debtors are free from CourtListener bulk dockets (section 2) and ECF RSS captions. Adapter `ecf_rss.py` already parses bankruptcy captions as debtors — [ecf_rss.py](../../src/equity/adapters/federal/ecf_rss.py)
- [LIVE] CourtListener scrapes free PACER case metadata, including bankruptcy chapter, plan-confirmation and discharge dates — [coverage page](https://wiki.free.law/c/courtlistener/help/data-coverage/federal-cases-and-filings)
- [LIVE] Schedules, SOFAs and petitions in Chapter 11 cases with a claims agent are posted free on the agent's site. Kroll's Bed Bath & Beyond page links "Voluntary Petitions", "Schedules & SOFA" and the "Master Service List" — [Kroll BBBY](https://restructuring.ra.kroll.com/bbby/Home-Index)
- [SEARCH] USTP posts annual enforcement-activity data tables with a codebook (FY11, FY17 PDFs) on justice.gov. I found no case-level public download. `justice.gov/ust/*` returned 403 here — [USTP enforcement activity](https://www.justice.gov/ust/bankruptcy-data-statistics/ustp-enforcement-activity); [FY17 codebook](https://www.justice.gov/ust/file/USTP_Enforcement_Activity_Data_Codebook_FY17_1.pdf/download)
- [SEARCH] The AO's F-2 tables give quarterly filings by chapter (to 2026-03-31), aggregate only — [uscourts bankruptcy tables](https://www.uscourts.gov/data-table-topics/bankruptcy?page=0)
- [UNVERIFIED] An individual's Schedule A/B (Official Form 106A/B) lists each property's street address and value, but it exists only as a PDF on PACER ($0.30 to $3) or in RECAP if someone uploaded it. No bulk set of schedules exists.

### Inferences
- Join plan: take court and `docket_number_core` (yy plus number) from CourtListener or RSS, and DISTRICT, OFFICE and DOCKET from FJC CASEKEY. A match attaches REALPROP, SECURED, D1CNTY and discharge to a named debtor. REALPROP > 0 with D1CNTY equal to the parcel county is a strong owner screen before any PACER spend. The exact docket-format mapping (5- vs 6-digit numbers, office digit) needs testing.
- Bankruptcy matters to equity two ways. The automatic stay blocks enforcing a judgment lien. A Chapter 7 discharge does not remove a pre-petition judgment lien on non-exempt real property unless it was avoided under 11 USC 522(f) [UNVERIFIED]. Discharge status plus REALPROP tells whether the lien probably survived.
- USTP adds little beyond the FJC IDB for this graph.

### Gaps
- The exact join between FJC CASEKEY/DOCKET and CM/ECF numbers was not tested on real rows.
- The FJC bankruptcy IDB lags. The latest snapshot is `cpbankjun26` (2026-06-30), so recent filings lack REALPROP until the next release.
- USTP data pages (403) were not reachable.
- No free bulk source of Schedule A/B *addresses* exists.

## 4. Bankruptcy claims registers (Kroll, Epiq, Stretto, Omni, Donlin Recano, BMC, Verita/KCC)

### Takeaway
Claims agents host free, per-case claims registers and schedules for large (mostly Chapter 11) cases. These are web UIs, not bulk files. Kroll's `robots.txt` explicitly **disallows** `/*/Home-ClaimInfo`, `/*/Home-ClaimDetails` and the PDF-download paths. Epiq, Stretto and Omni sit behind bot walls (403 to curl). Omni's robots.txt allows crawling, but its Content-Signal says `ai-train=no, use=reference`. Volume of individual real-property debtors here is low. Their value is creditor-side: claims filed by judgment creditors and tax authorities against a corporate debtor that owns real estate.

### Cited Findings
- [LIVE] The Kroll page states "Kroll Restructuring Administration (formerly known as Prime Clerk)". Case pages show Claims, "Submit a Claim", "Schedules & SOFA" and the docket, e.g. Bed Bath & Beyond Inc., Case No. 23-13359. The page links a TermsOfUse file — [Kroll BBBY claims](https://restructuring.ra.kroll.com/bbby/Home-ClaimInfo)
- [LIVE] Kroll robots.txt: `disallow: /*/Home-DownloadPDF`, `/*/Home-ClaimInfo`, `/*/External-DownloadPDF`, `/*/Home-ClaimDetails`, `/*/Home-DownloadPDF_Post` — [robots.txt](https://restructuring.ra.kroll.com/robots.txt)
- [LIVE] Omni Agent Solutions robots.txt sets `Content-Signal: search=yes,ai-train=no,use=reference` and `Allow: /`. It blocks Amazonbot, Applebot-Extended and Bytespider. Its home page returned 403 to curl — [Omni robots.txt](https://omniagentsolutions.com/robots.txt)
- [LIVE] Stretto (`cases.stretto.com`) robots.txt disallows only `/wp-admin/`, but the home page returned 403 (bot wall). Epiq (`dm.epiq11.com`) returned 403 even for robots.txt — direct curl.
- [LIVE] `www.donlinrecano.com` now 301-redirects to `bankruptcy.angeiongroup.com/cases`, so Donlin Recano appears to be part of Angeion Group. `www.kccllc.net` redirects to `veritaglobal.net`. The BMC restructuring site redirects to `ServiceList.aspx` — direct curl.
- [SEARCH] "Kurtzman Carson Consultants LLC (KCC), Gilardi & Co., and RicePoint… unification under the newly created Verita Global (Verita) brand". Sources disagree on the date (2024 vs 2026) — [Verita: KCC is now Verita](https://veritaglobal.com/kcc-is-now-verita/); [PR Newswire](https://www.prnewswire.com/news-releases/kcc-gilardi-and-ricepoint-rebrand-as-verita-302171213.html)
- [SEARCH] Without an agent, the claims register is a PACER case-specific report capped at $3. Courthouse terminals show it free. Claims must be listed on a register "only when there may be a distribution to unsecured creditors" (Fed. R. Bankr. P. 5003 note) — [txnb fee note](https://www.txnb.uscourts.gov/node/214); [Rule 5003](https://law.justia.com/codes/us/2012/title-11/appendix-title-11/323/part-v/rule-5003/index.html)
- [LIVE] RSS feeds carry claim activity: "Transfer of Claim" (kyeb 25 in one day) and "Notice of Assignment of Claim – BNC" (ohsb 29) — section 2 probe.
- [UNVERIFIED] Agents are retained under 28 U.S.C. 156(c) and court retention orders that typically require a free public claims register. Most agents offer per-case Excel or CSV export from the register UI (Kroll, Stretto, Epiq). Formats and terms vary by case and were not confirmed.

### Inferences
- Do not crawl Kroll claims pages: robots.txt forbids it. Pull per-case registers by hand only for corporate debtors that own parcels, or buy the $3 PACER claims register.
- Claims registers name judgment creditors and taxing authorities with amounts. Where the debtor owns real estate, they show competing secured claims (Schedule D) against the parcel. That use is narrow and per case.
- For individual Chapter 7 and 13 debtors, the main volume, there is no agent, so the register sits only in PACER or RSS "Proof of Claim" entries.

### Gaps
- Agent terms of use (Kroll TermsOfUse, Stretto, Epiq, Omni, Verita, Angeion, BMC) were not read, because of bot walls or because I did not fetch them.
- Whether any agent offers a cross-case bulk feed. I found none.
- How long the Donlin Recano to Angeion redirect has been in place, and whether it is an acquisition.

## 5. Probate: free bulk indexes and notices to creditors

### Takeaway
I found **no current free bulk probate filing index** on Socrata or ArcGIS. The only probate open data is archival or tiny: Santa Clara historic probate cases (1800s–1900s, 7,536), Ramsey County MN "Missing Heirs" (36 rows), King County WA microfiche indexes (2018) and Macoupin IL indexes from the 1800s. The usable free channels are county court search portals (e.g. Harris County Clerk probate court records), court hearing calendars (Santa Clara probate advance case status reports, Tuolumne probate notes), and statewide newspaper public-notice sites, which carry notices to creditors. All are per-search, not bulk.

### Cited Findings
- [LIVE] A Socrata catalog query for "probate" returns only probation datasets plus `data.sccgov.org rh64-rgza` "County Probate Cases". That set has 7,536 rows of archival case folders, with fields last, first, probate_date (e.g. "07 Oct 1903"), death_date, box and accession — [Santa Clara rh64-rgza](https://data.sccgov.org/resource/rh64-rgza.json)
- [LIVE] Ramsey County MN "Missing Heirs" (`t2fe-qrnd`): 36 rows with estate_of, heir, court_file (e.g. P8-03-5929), dollar_amount and write_off, updated 2026-03-27 — [Ramsey t2fe-qrnd](https://data.ramseycountymn.gov/resource/t2fe-qrnd.json)
- [LIVE] King County "Superior Court Records from microfiche" (`vu5j-8bgd`) indexes probate and civil microfiche, last updated 2018. Macoupin IL probate indexes cover 1832–1910 — [King vu5j-8bgd](https://data.kingcounty.gov/d/vu5j-8bgd); [Macoupin 2b3e-t2e7](https://data.macoupincountyil.gov/d/2b3e-t2e7)
- [LIVE] An ArcGIS search for "probate" returns 404 items, none a probate case layer (probation, census and district layers). "estate notices" returns 0 — [ArcGIS search API](https://www.arcgis.com/sharing/rest/search?q=%22probate%22&f=json)
- [LIVE] The Harris County Clerk site menu has "Courts → Probate → Probate Court Settings", alongside the free foreclosure search. Harris County probate courts sit with the County Clerk — [Harris Clerk](https://www.cclerk.hctx.net/applications/websearch/FRCL_R.aspx)
- [SEARCH] Santa Clara Superior Court posts "Probate Advance Case Status Reports" for scheduled hearings, and Tuolumne posts a weekly probate notes archive. Both are hearing-based PDFs — [Santa Clara probate reports](https://santaclara.courts.ca.gov/divisions/probate-division/probate-advance-case-status-reports); [Tuolumne probate notes](https://www.tuolumne.courts.ca.gov/online-services/probate-notes/probate-notes-archive)
- [SEARCH] Statewide press-association public-notice sites (43 associations, 44 states in 2022) are free and searchable, and carry probate notices to creditors and foreclosure notices. Examples: FloridaPublicNotices.com (all 67 counties, required by Fla. Stat. 50.0211), Georgia (database "free to all users"), Nebraska (searchable by type and county). Utah runs a government Public Notice Website — [PNRC survey](https://www.pnrc.net/2022/09/06/a-survey-of-statewide-public-notice-websites/); [Nebraska](https://nebpress.com/?p=5287); [Utah](https://archives.utah.gov/Public-Notice-Website); [NJ statewide list](https://nj.gov/www.nj.gov/state/statewide-legal-notices-list.shtml)
- [LIVE] Earlier notes: Alabama probate judges hold the land records, and local acts let them *sell* index data (Mobile, Elmore) — [Recorder laws report](../../reports/Recorder%20data%20records%20laws%20by%20state.md)

### Inferences
- Probate matters because a decedent-owner's parcel is where judgment creditors file claims and where liens survive into the estate. A notice to creditors names the decedent and personal representative, and often the county and case number. That makes it a debtor-discovery or "estate" flag joinable by name and county. The practical free route is a scheduled, polite pull from one or two public-notice sites per target state, after reading their terms.
- No county was found that publishes a downloadable new-estates list. Assume records requests (for example under Florida Chapter 119, for the probate index of a target county) for bulk.

### Gaps
- I did not read the terms or test any public-notice site's search or export. The vendor (Illinois Press Association platform, Column) terms may forbid scraping.
- No probate-court open data was found in the buyer's states (FL, OH, LA, NY, NJ, IN, MI, GA, AL, TX, CA, NC, SC, PA, WV).
- Harris County probate search fields were not checked.

## 6. Per-state judgment lien rules (all 50 states + DC)

### Takeaway
No single free, authoritative 50-state source covers all four items: how the lien is created, its duration and renewal, the interest rate and the homestead amount. The best free compilations are the **White and Williams LLP "Judgment Lien Duration, Expiration, Renewal or Revival" chart** (law firm, rev. 2020-01-20, all 50 states plus DC, with statute cites) and **NCLC "No Fresh Start 2025" Table 2 and Appendix B** (homestead amounts with citations, all 50 plus DC, December 2025). Lien creation and interest rates have no free compiled source. The creation column below is my statute knowledge and is marked [UNVERIFIED]. These should fill `config/sol.yaml`'s `lien_years`, `renewable`, `renewal_years` and `statute` only after Brandon confirms each row, as the file requires.

### Cited Findings
- [LIVE] White and Williams chart: "Certain exceptions may apply and law is subject to change… This summary should not be construed as legal advice". It gives duration and renewal with cites for every state plus DC. The duration column below is quoted from it — [White and Williams PDF](https://www.whiteandwilliams.com/assets/htmldocuments/Judgment%20Liens%20-%20Rev%201-20-20.PDF)
- [LIVE] NCLC Table 2, "Protection of the Family Home", grades every state plus DC, PR and VI, and Appendix B gives the statute cite per state. The ratings assume "the debtor has filed any required homestead declaration" — [NCLC Table 2](https://www.nclc.org/wp-content/uploads/2025/12/2025.12_Report_No-Fresh-Start_Table-02.pdf); [Appendix B State Summaries](https://www.nclc.org/wp-content/uploads/2026/01/2025_Report_No-Fresh-Start_State-Summaries.pdf); [report page](https://www.nclc.org/resources/no-fresh-start/)
- [SEARCH] Other compilations exist but are secondary or marketing: a Bernstein-Burkley 50-state renewal-timing chart (2016 PDF, which would not download here), an ezel.ai "50-State Survey" (403 here, likely machine-generated) and a usassetrecords "All 50 States" page — [Bernstein PDF](https://bernsteinlaw.com/wp-content/uploads/2016/01/50-State-Judgment-Renewal-Timing.pdf); [ezel.ai](https://ezel.ai/surveys/judgment-lien-duration-renewal); [usassetrecords](https://usassetrecords.com/how-long-is-a-judgment-good-for/)
- [SEARCH] Lien-creation examples confirmed by search. CA: "a judgment lien on real property is created… by recording an abstract of a money judgment with the county recorder" (CCP 697.310). TX: a recorded and indexed abstract creates the lien (Prop. Code 52.001). NY: Civil Court judgments need a transcript docketed with the county clerk. WA: other counties are reached by filing an abstract (RCW 4.56.200). WY: the lien runs from recording the transcript. MN: a docket transcript is filed per county, with an extra step for Torrens land — [CCP 697.310](https://law.justia.com/codes/california/2010/ccp/697.310-697.410.html); [Tex. Prop. Code ch. 52](https://statutes.capitol.texas.gov/Docs/PR/pdf/PR.52.pdf); [NYC Civil transcript](https://www.nycourts.gov/new-york-city-civil-court/nyc-civil-court-transcript-judgment); [RCW 4.56.200](https://app.leg.wa.gov/RCW/default.aspx?cite=4.56.200); [Nolo MN](https://www.nolo.com/legal-encyclopedia/judgment-liens-minnesota-46814.html)
- [SEARCH] Interest-rate sources found. Federal: weekly 1-year Treasury (28 U.S.C. 1961), 3.69%–3.79% in spring 2026. TX: OCCC monthly rate, 6.75% in February 2026. MI: 1% plus the 5-year Treasury auction average, with 3.959% certified for the period ending 2026-07-01. UT: 5.51% for 2026. TN: 2% below the TDFI formula rate since 2012-07-01. DC publishes a historical judgment-rate PDF — [nmid](https://www.nmid.uscourts.gov/post-judgment-interest-rates); [TX OCCC](https://www.occc.texas.gov/publications/interest-rates); [MI Treasury](https://www.michigan.gov/taxes/0,4676,7-238-43551_84523-107013--,00.html); [Utah courts](https://www.utcourts.gov/en/court-records-publications/resources/interest-rates/historic.html); [TN courts](https://tncourts.gov/node/1232344); [DC courts](https://www.dccourts.gov/sites/default/files/matters-docs/Historical-Judgment-Interest-Rate.pdf)

**Table.** Column notes:
- *Created by*: **R** = record a certified copy, abstract, transcript or notice with the county recorder or land records. **D** = docketing or entry by the court clerk creates the lien automatically in the county of entry, with other counties reached by transcript. **X** = no general judgment lien; the creditor must levy or attach execution.
- *Lien duration*: White and Williams, rev. 2020 [LIVE source, secondary].
- *Homestead*: NCLC 2025 [LIVE].
- *Interest*: [UNVERIFIED] unless a source is given above. It is not the lien.

| St | Created by [UNVERIFIED] | Where / instrument [UNVERIFIED] | Lien duration & renewal (W&W 2020) | Homestead (NCLC 2025; cite) | Post-judgment interest [UNVERIFIED] |
|---|---|---|---|---|---|
| AL | R | Certificate of judgment recorded in probate office (Ala. Code 6-9-210/211) | Judgment 10 yrs; revivable, not after 20 yrs (6-9-190/191) | $18,800 (6-10-2) | 7.5% fixed (8-8-10) |
| AK | R | Certified copy/abstract in recording district (AS 09.30.010) | Recorded lien no more than 10 yrs (09.30.010) | $72,900 (09.38.010) | Floating, 3 pts over Fed discount (09.30.070) |
| AZ | R | Certified copy or info statement with county recorder (ARS 33-961) | Execution within 10 yrs of entry/renewal (12-1551) | $425,200 (33-1101) | Lesser of 10% or prime+1% (44-1201) |
| AR | D | Automatic in county of circuit/federal court; other counties by filing (16-65-117) | Act within 10 yrs; revive by scire facias (16-65-501) | No $ cap, acreage limit (Const. art. 9) | 10% cap or rule rate (16-65-114) |
| CA | R | Abstract of judgment, county recorder (CCP 697.310) | Expires 10 yrs after entry (683.020); renewable (683.110) | County median ≥$361,479, cap $722,507 (CCP 704.730) | 10% (CCP 685.010); reduced rate for some consumer debt (reported) |
| CO | R | Transcript with county clerk & recorder (CRS 13-52-102) | Lien 6 yrs unless revived; judgment revivable within 20 yrs | $250,000 (38-41-201) | 8% or contract rate (5-12-102) |
| CT | R | Judgment lien certificate on town land records (CGS 52-380a) | Lien 20 yrs (52-380a) | $250,000 (52-352b(t)) | Up to 10% discretionary (37-3a) |
| DE | D | Entry on Superior Court docket, county (10 Del. C. 4711) | Lien 10 yrs, renewable 10 (4711) | $500 (NCLC; tit. 10 § 4903) | Fed discount + 5% (6 Del. C. 2301) |
| DC | R | Filed/recorded with Recorder of Deeds (D.C. Code 15-102) | Enforceable 12 yrs; revival +12 (15-101, 15-103) | No $ cap if head of family | Contract rate or 70% of 1-yr T-bill (28-3302); see DC PDF above |
| FL | R | Certified copy + address affidavit in Official Records (55.10) | Lien expires after 20 yrs (55.081); 10 yrs + re-record (55.10, reported) | No $ cap, acreage (Const. art. X § 4) | Quarterly CFO rate (55.03) |
| GA | D/R | Fi.fa. entered on clerk's general execution docket; GSCCCA index (OCGA 9-12-81/86) | Dormant after 7 yrs; renewable (9-12-60) | $21,500 (44-13-1) | Prime + 3% (7-4-12) |
| HI | R | Bureau of Conveyances / Land Court (HRS 636-3) | Presumed paid 10 yrs; extend to 20 max (657-5) | $30,000 (651-92) | 10% (478-3) |
| ID | R | Transcript/abstract with county recorder (10-1110) | Lien 10 yrs; renew +10 (10-1110/1111) | $175,000 (55-1001 ff.) | Treasury-based annual rate (28-22-104) |
| IL | R | Memorandum of judgment with county recorder (735 ILCS 5/12-101) | Lien 7 yrs from entry/revival; revive within 20 (12-101, 13-218) | $50,000 (12-901, reported) | 9%; lower for small consumer debt (2-1303) |
| IN | D | Entry in circuit clerk's judgment docket, county (IC 34-55-9-2) | Lien 10 yrs; judgment presumed paid at 20 | $22,750 (34-55-10-2) | Up to 8% (24-4.6-1-101) |
| IA | D | Entry in judgment docket, county; transcript elsewhere (624.23) | Lien 10 yrs from judgment; judgment 20 yrs (624.23, 614.1) | No $ cap, acreage (561.2) | Treasury-based (535.3) |
| KS | D | Filing in district court, county (60-2202) | Dormant if no execution/renewal in 5 yrs (60-2403) | No $ cap, acreage (60-2301) | Fed discount + 4% (16-204) |
| KY | R | Certified judgment lien notice in county clerk's office (KRS 426.720) | Action on judgment within 15 yrs of last execution (413.090) | $5,000 (427.060) | 6% or contract (360.040) |
| LA | R | Certified judgment in parish mortgage records (judicial mortgage, CC art. 3300) | Judgment 10 yrs; revival by motion (CCP 3501, 2031) | $35,000 (R.S. 20:1) | Annual rate set by Commissioner (R.S. 13:4202) |
| ME | R | Writ of execution recorded in registry of deeds (14 MRSA 4651-A) | Lien 20 yrs from filing of writ; renew once 20 | $188,550 (tit. 14 § 4422(1)) | 1-yr T-bill + 6% (14 MRSA 1602-C) |
| MD | D | Indexed in circuit court; District Court judgments recorded there (Rule 2-621) | Judgment 12 yrs; renewable by notice (Rule 3-625) | $6,000 (CJP 11-504) | 10% (CJP 11-107); 6% for rent |
| MA | X | No general judgment lien; levy of execution / attachment recorded (MGL c.236 § 4) | Presumed paid after 20 yrs (c.260 § 20) | $1,000,000 (declared homestead, c.188) | 12% (c.231 § 6B/6C) |
| MI | R | Notice of judgment lien with register of deeds (MCL 600.2803) | Lien 5 yrs from recording; re-record once +5 (600.2809) | $3,500 (600.6023) | 1% + 5-yr T-note avg (600.6013); 3.959% (2026) |
| MN | D | Docketing in district court, county; transcript elsewhere (548.09) | Enforce 10 yrs from entry (550.01) | $510,000 (510.01-.02) | Annual rate set by court admin (549.09); 10% over $50k |
| MS | D | Enrollment on circuit clerk's judgment roll (11-7-191) | Action within 7 yrs of entry/renewal (15-1-43) | $75,000 (85-3-21) | Rate set by judge (75-17-7) |
| MO | D | Entry in circuit court, county; transcript elsewhere (RSMo 511.350) | Lien 10 yrs (Rule 74.08); revive within 10 (74.09) | $15,000 (513.475) | 9% or contract; tort: T-bill + 5% (408.040) |
| MT | D | Docketing in district court, county; abstract elsewhere (25-9-301) | Action on judgment within 10 yrs (27-2-201) | $409,450 (70-32-104) | Prime + 3% (25-9-205) |
| NE | D | Entry in district court, county; transcript elsewhere (25-1504) | Dormant if not executed in 5 yrs; revive within 10 (25-1515, 25-1420) | $120,000 (40-101) | T-bill-based (45-103) |
| NV | R | Transcript/abstract with county recorder (NRS 17.150) | Judgment 6 yrs; renewable within 6 yrs (17.150, 17.214) | $605,000 (115.010) | Prime + 2% (17.130) |
| NH | X | Real estate reached by attachment/levy recorded in registry (RSA 511) | Action on judgment within 20 yrs (508:5) | $120,000 (480:1) | Treasury-based annual (336:1) |
| NJ | D | Docketing in Superior Court Civil Judgment and Order Docket, statewide (2A:16-1) | Judgment 20 yrs; renewable (2A:14-5) | No protection | Court-rule rate based on Cash Management Fund (R. 4:42-11) |
| NM | R | Transcript of judgment with county clerk (NMSA 39-1-6) | Lien expires after 14 yrs (39-1-6) | $150,000 (42-10-9) | 8.75% or higher for tort/intentional (56-8-4) |
| NY | D | Docketed by county clerk; lower courts by transcript (CPLR 5018, 5203) | Lien 10 yrs; renew in last year (5203, 5014); presumed paid at 20 (211) | $204,825 NYC-area counties, less elsewhere (CPLR 5206) | 9% (CPLR 5004); 2% consumer debt (2022) |
| NC | D | Docketing/indexing by superior court clerk, county; transcript elsewhere (1-233) | Lien 10 yrs from entry (1-234) | $35,000 (1C-1601) | 8% legal rate (24-1) |
| ND | D | Docketing in county; transcript elsewhere (28-20-13) | Lien 10 yrs; renew by affidavit within 90 days of 10 yrs (28-20-21) | $150,000 (47-18-01) | Prime-based annual (28-20-34) |
| OH | R/D | Certificate of judgment filed with common pleas clerk, county (ORC 2329.02) | Dormant after 5 yrs; revive within 10 of dormancy (2329.07, 2325.18) | $182,625 (2329.66) | Statutory annual rate (1343.03, 5703.47) |
| OK | R | Statement/certified copy filed with county clerk (12 O.S. 706) | Unenforceable if not executed/renewed in 5 yrs (12 O.S. 735) | No $ cap, acreage (31 O.S. § 1) | Prime + 2% (12 O.S. 727.1) |
| OR | D/R | Lien in county of entry if judgment says so; lien record abstract elsewhere (ORS 18.150-.152) | Remedies 10 yrs; extend 10 by certificate (18.180, 18.182) | $150,000 (18.395) | 9% (82.010) |
| PA | D | Entry in prothonotary's judgment index, county (42 Pa.C.S. 4303) | Lien 5 yrs; revival needed (Pa.R.C.P. 3023, 3031.1) | $300 (wildcard only; 42 Pa.C.S. 8123) | 6% legal rate (42 Pa.C.S. 8101) |
| RI | X | Execution levied/recorded in land evidence records | Lien discharged 20 yrs from judgment (9-26-33) | $500,000 (9-26-4.1) | 12% (9-21-10) |
| SC | D | Entry/indexing in county of judgment; transcript elsewhere (15-35-810) | Lien 10 yrs (15-35-810) | $76,125 ($152,250 joint) (15-41-30) | Prime + 4% (34-31-20) |
| SD | D | Docketing with clerk of courts, county (15-16-7) | Lien 10 yrs; renew +10 (15-16-7, 15-16-35) | No $ cap, acreage (43-31-1) | Category B rate (54-3-16) |
| TN | R | Certified copy recorded with register of deeds (TCA 25-5-101) | Enforceable 10 yrs; renew by motion (28-3-110; Rule 69.04) | $35,000 (26-2-301) | 2% below TDFI formula rate (47-14-121) |
| TX | R | Abstract of judgment recorded and indexed by county clerk (Prop. Code 52.001) | Dormant if not executed in 10 yrs; revive within 2 yrs (CPRC 34.001, 31.006) | No $ cap, acreage (Prop. Code 41.002); homestead immune | OCCC monthly rate, floor 5% cap 15% (Fin. Code 304.003); 6.75% Feb 2026 |
| UT | R | Judgment/abstract recorded with county recorder (78B-5-202) | Lien 8 yrs; renew +8 by motion (78B-5-202, 78B-6-1802) | $52,400 ($104,700 joint) (78B-5-503) | 1-yr T-bill + 2% (15-1-4); 5.51% in 2026 |
| VT | R | Certified copy recorded in town land records (12 VSA 2901) | Lien 8 yrs from final judgment; renewal within 8 (2903, 506) | $125,000 (27 VSA § 101) | 12% (9 VSA 41a) |
| VA | D | Docketing in circuit clerk's judgment lien docket (8.01-446, 8.01-458) | Enforceable 20 yrs; extend by motion (8.01-251) | $56,000 (34-4, reported) | 6% judgment rate (6.2-302) |
| WA | D/R | Automatic in county of superior court entry; abstract elsewhere (RCW 4.56.190/200) | Expires 10 yrs; extend 10 (4.56.190, 6.17.020(3)) | ≥$125,000 or county median (6.13.030) | 12% or contract; consumer/tort lower (4.56.110) |
| WV | R | Docketing in county commission clerk's judgment lien docket (38-3-5/6) | Lien 10 yrs from entry; renewable 10 (38-3-7) | $5,000 (38-9-1, reported) | Fed discount + 2% (56-6-31) |
| WI | D | Docketing in circuit court, county; transcript elsewhere (806.15) | Lien 10 yrs from entry; execution up to 20 (806.15, 815.04) | $75,000 (815.20) | Prime + 1% (815.05(8)) |
| WY | R | Transcript/certified copy recorded with county clerk (1-17-302) | Dormant if no execution in 5 yrs; revive within 10 (1-17-307, 1-16-503) | $100,000 (1-20-101) | 10% or contract (1-16-102) |

Notes on the table:
- [LIVE] NCLC lists Florida, Iowa, Kansas, Oklahoma, South Dakota, Texas and Arkansas as "Limit on number of acres, but no dollar cap", and DC as "No dollar cap if head of family" — [NCLC Table 2](https://www.nclc.org/wp-content/uploads/2025/12/2025.12_Report_No-Fresh-Start_Table-02.pdf)
- [LIVE] W&W Florida text reads "A judgment lien on real or personal property expires after 20 years. Fla. Stat. § 55.081". Search snippets from Bernstein and usassetrecords add the 10-year re-recording step under 55.10 — [W&W](https://www.whiteandwilliams.com/assets/htmldocuments/Judgment%20Liens%20-%20Rev%201-20-20.PDF); [Bernstein](https://bernsteinlaw.com/wp-content/uploads/2016/01/50-State-Judgment-Renewal-Timing.pdf)
- The W&W chart is dated January 2020. At least Arizona (the 2018 change to 10 years), Idaho and Georgia should be re-checked against current statutes before filling `sol.yaml` [UNVERIFIED that any of them changed after 2020].

### Inferences
- `config/sol.yaml` fields map as follows. `judgment_enforceable_years` and `lien_years` come from the W&W column. `renewable` and `renewal_years` come from W&W. `statute` comes from the W&W cite. A `lien_created_by` (R/D/X) field and a `homestead_cap` field would let rules tell whether a docketed judgment found in a court feed is already a lien (D states) or needs a recorder hit (R states).
- That distinction drives data needs. In **D states** (PA, NJ, NY, NC, SC, WI, MN, IN, IA, KS, MO, NE, ND, SD, MD, DE, VA, WA in the county of entry), a court-docket judgment *is* the lien in that county, so court feeds suffice. In **R states** (CA, TX, FL, AZ, NV, UT, CO, IL, MI, TN, KY, OK, NM, CT, VT, HI, AK, AL, WY, WV, OH), a court judgment shows lien potential only. A recorder or official-records hit (abstract, certificate or memorandum) is needed to prove a lien. Massachusetts, New Hampshire and Rhode Island need a levy or attachment.
- Homestead immunity (TX, FL, plus no-cap acreage states) means a judgment lien may not reach the debtor's homestead at all. Owner-occupancy is therefore a critical parcel flag in those states.

### Gaps
- No free authoritative compiled source for lien **creation method** or **post-judgment interest rates** was found. Those columns come from my background knowledge and must be verified statute by statute. The NCLC "Collection Actions" treatise, which covers these, is paywalled.
- W&W is a 2020 law-firm summary. Post-2020 amendments were not checked.
- Renewal-keeps-priority (`renewal_keeps_priority` in sol.yaml) is not covered by any source I found.
- Some NCLC homestead citations (IL, VA, WV) were parsed from a jumbled PDF layout and are marked "reported".
