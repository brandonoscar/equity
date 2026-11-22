# Non-obvious free bulk sources of US civil judgments and judgment liens (recorders, court files, nonprofit/academic datasets, public-records pathways)

Researched 2026-11-22. Builds on `docs/sources/judgment-sources.md` and `docs/sources/recorder-sources.md`; does not repeat sources already loaded (NYC ACRIS, Hillsborough FL OR/civil/garnishment, Philadelphia RTT, NYC OATH, Allegheny WPRDC liens, CT SOTS liens).

Tags: **[LIVE]** = fetched this session from the publisher's API; **[SEARCH]** = web-search snippets only; **[UNVERIFIED]** = background knowledge or snippets that do not settle it.

**Network note (important for the report writer):** this session's proxy refused nearly every county/court/nonprofit host, so the Harris, Broward and Franklin candidates could NOT be verified. Hosts that refused (proxy 403 / DNS ENOTFOUND, via both curl and WebFetch): `jpwebsite.harriscountytx.gov`, `www.hcdistrictclerk.com`, `www.broward.org`, `ftp.broward.org`, `fcmcclerk.com`, `civilcourtdata.lsc.gov`, `evictionlab.org`, `biglocalnews.org`, `www.propublica.org`, `student-debt-research--debt-collection-lab.netlify.app`, `openjustice.okpolicy.org`, `data.world`, `dataverse.harvard.edu`, `www.muckrock.com`, `www.courtlistener.com`, `myorangeclerk.com`, `www.duvalclerk.com`, `www.mypinellasclerk.gov`, `www.pascoclerk.com`, `www.clarkcountynv.gov`, `www.dallascounty.org`, `www.traviscountyclerk.org`, `santaclara.courts.ca.gov`, `mncourts.gov`, `fbctxdocs.fortbendcountytx.gov`, `www.cookcountyclerkofcourt.org`, `scgisa.starkcountyohio.gov`, `github.com` web pages (and the GitHub API refused repo `childpovertyactionlab/cpal-evictions`). Reachable: Socrata federated catalog (via `datacatalog.cookcountyil.gov/api/catalog/v1`), `hub.arcgis.com`, `services1.arcgis.com`, `publicrec.hillsclerk.com`, `api.github.com` search.

## Ranked list (most useful first)

| Rank | Source | Names (debtor/creditor) | Amount | Date | County | Satisfaction | Parcel link | Free / no login | Tag |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Harris County TX JP Public Data Extract (16 justice courts, civil incl. debt claims, small claims, evictions) | Defendant name + address per Debt Collection Lab paper; plaintiff presumably | Unknown (layout not read) | Yes (by day/range) | Harris | Unknown | Via defendant address only | Apparently free, no login seen in snippets | [SEARCH] |
| 2 | Harris County District Clerk "Public Datasets" (daily civil text files) | Party files listed (monthly party files, party-modification dailies) | Unknown | Yes | Harris (district courts) | Unknown | Address match only | Free status and login unknown | [SEARCH] |
| 3 | Fulton County GA Superior Court "Current Pending Cases" (`u8gi-zru8`) + "Case Assignments" (`e8ne-c2s2`) | Case `style` (caption, i.e. "X vs Y") in pending-cases table; no names in assignments table | No | `datefiled`, `dispositiondate` | Fulton | `disposition` / `casestatus` only | No | Free, Socrata, no key; daily | [LIVE] |
| 4 | TCEQ "Civil Judgments Issued" (`data.texas.gov/d/7ift-kbgd`) | `respondent_name` (debtor); creditor = State of Texas | `payable_amount`, `penalty_assessed`, `attorney_fees`, `court_costs` | `order_date` | `county` | No | No (TCEQ ID only) | Free, Socrata; annual | [LIVE] |
| 5 | Debt Collection Lab (Princeton) / January Advisors case-level files for CT, IN, MN, ND, VA, WI | Unknown | Unknown | Yes | Statewide in those states | Unknown | No | Downloads listed; names unknown | [SEARCH] |
| 6 | Broward FL Official Records bulk data files (FTP) | Index (grantor/grantee) | Unlikely | Yes | Broward | Satisfactions recorded as separate docs | Possibly via legal description | Free status still unknown | [SEARCH/UNVERIFIED] |
| 7 | Pasco FL Clerk "Subscription Download Data" (OR indexing, daily and weekly) | Index | Unlikely | Yes | Pasco | Separate docs | Possibly | Title says "Subscription"; free unknown | [SEARCH] |
| 8 | Franklin County OH Municipal Court eviction CSVs | Unknown | Unknown | Yes | Franklin | Unknown | Address | Free, nightly per prior research | [SEARCH] (host blocked) |
| 9 | Louisville Metro KY "Lien Holder Final Orders" (ArcGIS) | `fullname` (owner) | `final_citation_amount` | `date_of_notification`, hearing dates | Jefferson KY | `final_order_state` | Street address + lat/long | Free, ArcGIS REST | [LIVE] |
| 10 | Maryland District Court Eviction Case Data (`mvqb-b4hf`) | No names | No | `eventdate`, `evicteddate` | `county` | No | ZIP only | Free, Socrata | [LIVE] |
| 11 | King County WA "Superior Court Records from microfiche" (`vu5j-8bgd`) | Historical plaintiff/defendant indexes (files) | No | `years` | King | No | No | Free; stale (2018) | [LIVE] |

## 1. County recorders / clerks with free bulk index downloads (FL, TX, CA, AZ, NV, OH, MI, GA, NC, CO, WA, OR, IL)

### Takeaway
No new county recorder or clerk with a confirmed free, no-login bulk index of recorded judgments was found beyond Hillsborough (already loaded). Florida clerks that publish daily Official Records index files mostly sell them (Miami-Dade, Palm Beach, Lee, Lake), and the two that might be free (Broward, Pasco) are on hosts this session could not reach. In Texas, abstracts of judgment are indexed by plaintiff and defendant in county real-property records, but no county gives those indexes away in bulk.

### Cited Findings
- **Broward FL**: the county's "Bulk Data Files" page (Records, Taxes & Treasury) offers Official Records FTP files with both images and index data. Search results do not show the price. The host was blocked, so this is still [SEARCH/UNVERIFIED] — [Broward Bulk Data Files](https://www.broward.org/RecordsTaxesTreasury/Records/Pages/IndexFiles-Completed.aspx)
- **Pasco FL**: the clerk's download page lists Official Records indexing as bulk data, "daily and weekly indexing data available for the period-ending date indicated in the file name". The page is titled "Subscription Download Data", so whether it is free is not settled [SEARCH] — [Pasco Clerk Subscription Download Data](https://www.pascoclerk.com/526/Subscription-Download-Data)
- **Lee FL**: bulk daily images, indexes and plat files go to "customers who establish an FTP account with the Clerk's office" (an account, so excluded) [SEARCH] — [Lee Clerk](https://www.leeclerk.org/departments/official-records-services/search-official-records)
- **Palm Beach FL**: daily OR index updates on FTP, kept at least 45 days, by subscription application [SEARCH] — [Palm Beach EDIS](https://www.mypalmbeachclerk.com/records/official-records/electronic-distribution-index-service), [FTP application](https://mypalmbeachclerk.com/records/official-records/electronic-distribution-index-service/ftp-subscription-application). The clerk's product cart also sells a daily "new cases filed in circuit civil" report [SEARCH] — [Palm Beach Products](https://appsgp.mypalmbeachclerk.com/clerkcart/ProductList.aspx)
- **Miami-Dade FL**: daily civil files (circuit and county civil, a zip per extraction date) and OR files, for registered commercial users. FTP costs $110 per folder per month; OR images cost $420 per month [SEARCH] — [Commercial Data Services](https://www.miamidadeclerk.gov/clerk/commercial-data-services.page), [Civil FTP layout](https://www.miamidadeclerk.gov/resources-clerk/library/FTP_File_Layouts/FTP_Layout_Civil.pdf)
- **Lake FL**: OR index and images cost a $75 setup fee plus $275 a year. A second Lake page lists different fees [SEARCH] — [Lake Clerk subscribers](https://lakecountyclerk.org/subscribers)
- **Volusia FL**: online OR index and images from 1988, but no bulk index download was found. Its daily files are court reports [SEARCH] — [Volusia Clerk](https://www.clerk.org/Search-Records.aspx)
- **Texas abstracts of judgment**: Property Code §52.004 requires the county clerk to record each abstract and index it alphabetically by every plaintiff and defendant, with volume/page or instrument number. So the debtor-creditor index exists in every county, but no free bulk copy was found [SEARCH] — [Tex. Prop. Code 52.004](https://codes.findlaw.com/tx/property-code/prop-sect-52-004/)
- **Texas, Fort Bend**: the district clerk sells bulk data (the purchaser list covers criminal data). A Fort Bend file server (`fbctxdocs.fortbendcountytx.gov`) shows a "County_Clerk" folder of about 3 GB with unknown contents. The host was blocked [SEARCH] — [Fort Bend bulk purchaser list](https://www.fortbendcountytx.gov/sites/default/files/document-central/document-central/district-clerk-documents/Bulk-Data-Purchaser-List-Online.pdf), [fbctxdocs](https://fbctxdocs.fortbendcountytx.gov/)
- **Texas, Tarrant**: abstracts are sold per document ($8 per abstract, $5 per certificate of dormant judgment) [SEARCH] — [Tarrant form](https://www.tarrantcountytx.gov/content/dam/main/county-clerk/AbstractofJudgmentReqFormAug2025.pdf)
- **Socrata-wide sweep** [LIVE]: I ran the federated catalog for "judgment(s)", "lis pendens", "abstract of judgment", "writ of execution", "garnishment", "official records", "small claims", "civil cases/filings", "sheriff sale" and "foreclosure filings" across every Socrata domain. No county recorder judgment or lis pendens index turned up anywhere. Hits were aggregate court statistics (TX OCA landlord/tenant caseload `8qme-eqs9`, Fulton performance), stale foreclosure files (Colorado 2016 `chpv-m4xq`, Macoupin IL 2015 `ighx-ur68`), NOLA sheriff lien-foreclosure sales (`d52w-8nva`, stale 2018), and the items ranked above — [Socrata catalog API](https://datacatalog.cookcountyil.gov/api/catalog/v1?q=lis%20pendens&only=dataset)
- **ArcGIS Hub sweep** [LIVE]: "lis pendens", "judgment lien", "judgments", "sheriff sale" and "writ of execution" found no recorder judgment layers. Relevant hits:
  - Stark County OH Sheriff "Civil Sales" MapServer, `scgisa.starkcountyohio.gov/arcgis/rest/services/Sheriff/CivilSales/MapServer` (host blocked; fields unread)
  - Louisville code-enforcement lien final orders (rank 9)
  - Maricopa "Lien and Delinquent Parcels" (tax liens)
  - Cochise tax-lien parcels
  - [ArcGIS Hub search](https://hub.arcgis.com/api/v3/datasets?q=sheriff%20sale)
- **Louisville Metro KY Lien Holder Final Orders** [LIVE]: 513 rows. Fields: `b1_alt_id`, `final_order_state`, `date_of_notification`, the street address parts, `latitude`/`longitude`, `fullname`, `addr1`, `city`, `state`, `zip`, inspection fields, hearing dates and results, and `final_citation_amount`. These are code-enforcement citations, not court judgments — [FeatureServer](https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/lien_notification_final_orders/FeatureServer/0)

### Inferences
- In Florida, Hillsborough is still the only confirmed free daily OR index. The best remaining FL leads are Broward and Pasco; both need their hosts allowlisted to check terms.
- Any free recorder bulk index would give the debtor (grantor or defendant) and creditor (grantee or plaintiff), recording date and instrument number, but rarely an amount. Satisfaction would come from matching a later "satisfaction" or "release" instrument. The parcel link is only by legal description or by the debtor's other recorded deeds.

### Gaps
- Orange, Duval, Pinellas, Polk, Brevard, Seminole, Sarasota, Leon, Escambia, Collier and Manatee FL: searches did not surface any bulk download page, and the clerk hosts were blocked. Not verified either way.
- Dallas, Bexar, Travis, Collin, Denton and El Paso TX; Clark NV; the CA, AZ, MI, NC, CO, WA, OR and IL recorders: no free bulk judgment index found by search. Prior research already lists Maricopa, Cook and Tarrant as paid.
- The Broward FTP price and terms are still unknown, because the host was blocked again.

## 2. Courts that publish civil dockets, judgment lists or filing reports as downloadable files

### Takeaway
The best court-side lead is still Harris County, Texas. Its JP extract service delivers case-level civil data (including defendant names and addresses) for a day or a date range as TXT, CSV or XML, and the District Clerk posts daily civil text files. Neither could be reached to confirm the cost or login terms. Fulton County GA's daily Odyssey extract on Socrata is a verified free source with case captions, but it has no amounts.

### Cited Findings
- **Harris JP extract**:
  - "Select the type of extract you'd like, then select the format in which you'd like the data delivered."
  - The page links a "File Layout Specification for Civil Data Extracts" and warns "our file layouts have changed".
  - Extracts cover all case types or one type (e.g. evictions), for a single day or a date range, as tab-delimited text, CSV or XML.
  - [SEARCH] — [JP extract page](https://jpwebsite.harriscountytx.gov/PublicExtracts/search.jsp), [JP services](https://jp.hctx.net/services.htm)
- **Harris JP data content**: a Debt Collection Lab paper by January Advisors' Jeff Reichman says the Harris JP courts "make their case data publicly available, including defendant name and address" [SEARCH] — [Enriching court data (PDF)](https://student-debt-research--debt-collection-lab.netlify.app/docs/enriching-court-data.pdf)
- **Texas JP courts generally**: the 803 justice courts are not centralized. Only aggregate monthly caseload goes to OCA [SEARCH] — [Texas Tribune/ProPublica](https://api.texastribune.org/2020/08/31/texas-oportun-lender-lawsuits/)
- **Harris District Clerk "Public Datasets"**:
  - A 2024 cached copy lists daily text files such as `CivilHistoricalDaily.txt`, case-setting and party-modification dailies, and monthly party files.
  - The clerk asks commercial scrapers to use these datasets instead.
  - The clerk's search site needs a registered login. Whether the datasets need one is unconfirmed.
  - The "Trial Judgments" search (by judgment date, type and court) is search only.
  - [SEARCH] — [Public Datasets](https://hcdistrictclerk.com/common/e-services/PublicDatasets.aspx), [Public Reports](https://www.hcdistrictclerk.com/Common/e-services/PublicReports.aspx)
- **Fulton County GA Superior Court, Current Pending Cases (`u8gi-zru8`)** [LIVE]:
  - "all currently pending Superior Court cases … criminal complex, criminal non-complex, family, civil, and business … extracted daily from the Odyssey system, and also updated here daily."
  - Columns: `casenbr`, `style`, `casetypedesc`, `casecategorykey`, `datefiled`, `casestatus`, `statuson`, `days_pending`, `judge`, `assigndate`, `chgoffdesc`, `datepulled`. Rows updated 2026-11-22.
  - [Socrata](https://sharefulton.fultoncountyga.gov/d/u8gi-zru8)
- **Fulton Superior Court Case Assignments (`e8ne-c2s2`)** [LIVE]:
  - Covers civil, criminal, business and family cases from 1992-01-01.
  - Columns: `caseid`, `casenbr`, `casetype`, `datefiled`, `disposition`, `dispositiondate`, `casestatus`, `judge`, and others.
  - No party names. Updated 2026-11-22.
  - [Socrata](https://sharefulton.fultoncountyga.gov/d/e8ne-c2s2)
- **Maryland District Court Eviction Case Data (`mvqb-b4hf`)** [LIVE]:
  - A statewide listing required by a 2022 law.
  - Columns: `casenumber`, `eventtype`, `eventdate`, `evicteddate`, `casetype`, `county`, `location`, `tenantcity`, `tenantzipcode`, `eventcomment`. No names.
  - Updated 2026-10-27.
  - [Socrata](https://opendata.maryland.gov/d/mvqb-b4hf)
- **TCEQ Civil Judgments Issued (`7ift-kbgd`)** [LIVE]:
  - From the Annual Enforcement Report (Tex. Water Code §5.126): civil judgments obtained by the Attorney General on TCEQ referrals.
  - Columns: `county`, `respondent_name`, `district_court_docket_no`, `case_no`, `payable_amount`, `penalty_assessed`, `penalty_deferred`, `attorney_fees`, `court_costs`, `order_date`, `program`, `tceq_id`.
  - Updated 2025-11-21 (annual).
  - [Socrata](https://data.texas.gov/d/7ift-kbgd)
- **King County WA "Superior Court Records from microfiche" (`vu5j-8bgd`)** [LIVE]: "Index and download location for King County Superior Court civil, criminal, domestic general defendant, general plaintiff, and probate records from microfiche". Columns: `name_in_index`, `file_size_in_mb`, `years`, `type`. Last updated 2018 — [Socrata](https://data.kingcounty.gov/d/vu5j-8bgd)
- **Franklin County OH Municipal Court eviction CSVs**: still [SEARCH] from prior research; the host was blocked again — [fcmcclerk.com/reports/evictions](https://fcmcclerk.com/reports/evictions)
- **Dallas County TX**: the county's eviction page "provides the community with a list of all eviction cases that have been filed in our Justice of the Peace courts". The format is unknown and the host was blocked [SEARCH] — [Dallas County evictions](https://www.dallascounty.org/departments/dchhs/housing-programs/evictions.php)
- **Aggregate only (no case level)**:
  - Virginia circuit caseload in Power BI, with monthly PDFs [SEARCH] — [VA OES](https://www.courts.state.va.us/courtadmin/aoc/djs/programs/cpss/csi/cc/home)
  - Massachusetts civil filings in XLSX/CSV by year, month and county [SEARCH] — [Mass.gov](https://www.mass.gov/info-details/civil-court-reports-and-dashboards)
  - TX OCA landlord/tenant caseload (`8qme-eqs9`) [LIVE] — [data.texas.gov](https://data.texas.gov/d/8qme-eqs9)
- **Sheriff sale lists**:
  - Stark County OH publishes a "Sheriff Civil Sales" GIS service (point and polygon layers), but the host was blocked, so its fields are unknown [LIVE: listed on Hub only] — [Hub listing](https://hub.arcgis.com/api/v3/datasets?q=sheriff%20sale)
  - NOLA "Sheriff Sales – Lien Foreclosures" is stale since 2018 [LIVE] — [data.nola.gov](https://data.nola.gov/d/d52w-8nva)
  - No free, case-level writ-of-execution list was found anywhere.

### Inferences
- Fulton `style` gives "Plaintiff v. Defendant" text for pending civil cases. Combined with the daily refresh, closing cases can be inferred when they drop out of the table (a satisfaction proxy is not possible). Judgment amounts are absent, so this is a lead feed, not a judgment feed.
- TCEQ judgments are small (state creditor, environmental penalties) but carry names, amounts, county and the district-court docket. Useful as a high-confidence enrichment of debtors who own industrial or commercial property.
- If the Harris JP layout includes judgment date and amount, it is the only free court source of private money judgments with debtor addresses outside NY. Allowlisting `jpwebsite.harriscountytx.gov` is the single highest-value action.

### Gaps
- The Harris JP layout fields (judgment amount, judgment date, plaintiff, satisfaction) and terms were not read; the host was blocked.
- No daily "new case filings" CSV was found for courts in OH, MI, GA (other than Fulton), NV, CO, NC, AZ, WA, OR or IL.

## 3. Nonprofit / academic / journalism datasets

### Takeaway
None of the nonprofit or academic sources offers a free, open, bulk, case-level file of civil judgments with party names. LSC CCDI and Eviction Lab release aggregates and give granular data only under agreements or de-identified merges. ProPublica's debt-collection data requires agreeing to terms of use. The Debt Collection Lab says "all data are available for download" and lists case-level data for six states; whether those files include names is unconfirmed, because the host was blocked.

### Cited Findings
- **LSC Civil Court Data Initiative**:
  - Collects civil court records from over 1,200 counties in 30+ states and territories.
  - The public site shows eviction trends for 1,250 counties.
  - LSC "may provide you more granular information about cases, parties, and events" under data-sharing agreements, so names are not public.
  - LSC built the open-source CleanCourt library for party-name cleaning.
  - [SEARCH] — [CCDI about](https://civilcourtdata.lsc.gov/about), [CCDI FAQ](https://civilcourtdata.lsc.gov/about/faq), [Thomson Reuters interview](https://www.thomsonreuters.com/en-us/posts/government/how-the-legal-services-corporation-is-analyzing-court-data-to-increase-access-to-justice/)
- **Princeton Eviction Lab**:
  - Its data merge matches a researcher's file to eviction records on names and addresses, then returns de-identified data (case IDs and eviction information).
  - Applicants pledge not to re-identify or publish names, and must use encrypted storage.
  - Case-level names are not released.
  - [SEARCH] — [Data request](https://evictionlab.org/data-request), [Data merge](https://evictionlab.org/es/data-merge)
- **Debt Collection Lab (Princeton) with January Advisors**:
  - Covers all or parts of 12 states, using scraping and FOIA requests.
  - The "Get the data" page has download links for CT, IN, MN, MO, ND and VA; none for AZ, CO, OH, PA or TX.
  - Individual-case data is said to exist for CT, IN, MN, ND, VA and WI.
  - Names are unconfirmed and the license is unknown.
  - [SEARCH] — [Get the data](https://student-debt-research--debt-collection-lab.netlify.app/get-the-data), [Lawsuit tracker](https://student-debt-research--debt-collection-lab.netlify.app/lawsuit-tracker), [Journalist's Resource](https://journalistsresource.org/economics/debt-collection-lawsuits/), [Princeton project page](https://dignityanddebt.princeton.edu/projects/the-debt-collection-lab/)
- **January Advisors' Texas data** is aggregate only. Pew's case-level analysis covered MN, MO, IN, ND, CT and VA [SEARCH] — [Pew 2025](https://www.pew.org/fr/research-and-analysis/articles/2025/09/02/debt-collection-lawsuits-surge-to-pre-pandemic-highs)
- **ProPublica Data Store "Debt Collection Datasets"**: state-court data behind "So Sue Them". Downloading requires agreeing to ProPublica's data terms of use. Fields and years were unconfirmed; the host was blocked [SEARCH] — [ProPublica datastore](https://www.propublica.org/datastore/dataset/debt-collection-datasets)
- **Pew**:
  - Reports are aggregate. Default judgments resolved more than 70% of debt suits.
  - Pew also published guidance on courts sharing civil data with third parties.
  - [SEARCH] — [Pew 2020](https://www.pew.org/research-and-analysis/reports/2020/05/how-debt-collectors-are-transforming-the-business-of-state-courts), [Pew data-sharing guide](https://www.pewtrusts.org/-/media/assets/2023/09/courts/how-to-share-civil-justice-data-with-third-parties-to-improve-public-knowledge-and-oversight.pdf)
- **Temple CPHLR / LawAtlas**: a dataset of debt-collection litigation laws (statutes, rules), not cases [SEARCH] — [LawAtlas](https://lawatlas.org/datasets/debt-collection-litigation-laws)
- **Open Justice Oklahoma**:
  - Builds OSCN data by scraping; its R package writes an `oscn_debt` table.
  - The 2009 OK Supreme Court order bars "bulk distribution" of OSCN/ODCR data.
  - No public bulk download was found.
  - [SEARCH] — [ojodb GitHub](https://github.com/openjusticeok/ojodb), [2009 order](https://law.justia.com/cases/oklahoma/supreme-court/2009/457676.html)
- **CPAL North Texas Eviction Project**:
  - The GitHub repo holds "source data for populating the database" behind its site. Filing data comes "from County sources or from January Advisors".
  - Dallas County DEAC reports cite CPAL for "record level data".
  - The repo could not be read: GitHub access to it is not enabled for this session.
  - [SEARCH] — [cpal-evictions](https://github.com/childpovertyactionlab/cpal-evictions), [DEAC report Oct 2026](https://www.dallascounty.org/Assets/uploads/docs/hhs/wepp/2026/DEAC-Report-10-31-2026.pdf)
- **Georgetown Civil Justice Data Commons**: code (including PACER scraping tools), not state judgment data [SEARCH] — [CJDC Data & Code](https://www.law.georgetown.edu/tech-institute/initiatives/georgetown-justice-lab/civil-justice-data-commons/knowledge-base/data-code/)
- **GitHub search** [LIVE via API]:
  - No repository with a case-level debt or judgment dataset was found.
  - Only eviction scrapers turned up: Colorado (`jonathanlamar/case-scraper`) and Oregon OJD (`devinmacarthur/ojd-eviction-scraping-*`, last pushed 2021-2022).
  - Also `accessible-justice/california-small-claims-court-data-analysis` (aggregate Judicial Council data).
  - [GitHub search API](https://api.github.com/search/repositories?q=eviction+court+records+scraper)

### Inferences
- For judgment buying, the nonprofit datasets are mostly useful as (a) proof of which courts will release case-level data on request (see section 4) and (b) the Debt Collection Lab's six case-level states, if their files carry names.
- Using Eviction Lab or LSC data through an agreement would almost certainly forbid the business's re-identification use.

### Gaps
- I could not reach Big Local News, Harvard Dataverse, ICPSR, data.world, Kaggle, Code for America or Measures for Justice, and searches surfaced no case-level civil judgment dataset with names from any of them. Measures for Justice and Code for America are criminal-justice focused [UNVERIFIED].
- Debt Collection Lab file contents (names, judgment amounts) and license.
- ProPublica debt-collection file fields and terms text.

## 4. Public-records-request pathways

### Takeaway
Court records mostly fall outside state FOIA statutes. They are governed instead by court rules on bulk distribution, which range from allowed at cost (CA trial courts, MN, FL clerks) to licensed or paid (AZ, IN, MD, NJ, NC) to prohibited (OK, NM). Florida is the strongest pathway: clerks are covered by Chapter 119 for court-file records, and the state constitution guarantees access to judicial records. A concrete low-cost precedent with party names is the Santa Clara Superior Court Civil Case Index.

### Cited Findings
- **Florida**:
  - Art. I §24 of the state constitution gives access to judicial-branch records.
  - §119.0714 says nothing in Chapter 119 exempts "a public record that was made a part of a court file and that is not specifically closed by order of court".
  - Chapter 119 bars agencies from contracts that impair public inspection or copying of public-records databases.
  - Duval Clerk's policy treats "bulk data reports or recurring data subscriptions" as complex requests, subject to redaction.
  - [SEARCH] — [Fla. Stat. 119.0714](https://m.flsenate.gov/Statutes/119.0714), [Duval complex request form](https://www.duvalclerk.gov/getmedia/8bcf13d4-2ae5-4639-ace0-f0a829350491/RequesttoObtainComplexPublicAndCourtRecords_ADA_Compliant.pdf), [FL AG opinion](https://myfloridalegal.com/print/pdf/node/2530)
  - Search snippets cited the old Rule 2.051. The current Fla. R. Gen. Prac. & Jud. Admin. 2.420 is [UNVERIFIED].
- **California (Santa Clara Superior Court)**:
  - The Civil Case Index includes case number, title, file and disposition dates, status, case type, related cases, and "party names and types".
  - It is updated quarterly and delivered on CD or by secure download.
  - The fee is "production cost … plus administrative costs"; a Justia copy of the form lists $150. That is nominal, not free.
  - One request per quarter (per a mirror).
  - Fresno and Mendocino courts have similar case-index ordering pages.
  - [SEARCH] — [Santa Clara Civil Case Index](https://santaclara.courts.ca.gov/online-services/case-information-online/requesting-cd-civil-case-index), [Fresno case index ordering](https://fresno.courts.ca.gov/online-services/case-information/case-index-ordering)
- **Minnesota**: seven bulk extracts, including "Judgments" (civil and family cases that have received a judgment), Evictions and Conciliation (small claims). Prior research says they are paid [SEARCH] — [MN bulk data](https://mncourts.gov/help-topics/court-statistics/bulk-data), [FAQ](https://MNCourts.gov/mncourtsgov/media/Research-Evaluation/FAQ-Bulk-Data-Extracts.pdf)
- **Maricopa County Justice Courts**: a monthly file set of new filings and terminations through a separate bulk-request form (paid, per prior research) [SEARCH] — [Maricopa JC records request info](https://www.justicecourts.maricopa.gov/media/zkkeicbs/records-request-info.pdf)
- **Indiana**: bulk by online application with a fee per file [SEARCH] — [IN bulk data applications](https://www.in.gov/judiciary/iocs/3285.htm)
- **Court requests generally**: an approved court data request "usually leads to a memorandum of understanding (MOU) or a data-sharing agreement". New America published an annotated example request [SEARCH] — [New America example](https://newamerica.org/future-land-housing/blog/eviction-data-request-annotated-example)
- **Eviction Lab's 50-state experiment**: Eviction Lab sent a simple eviction data request to all 50 states and published what it learned. It is a useful map of which states' courts answer requests [SEARCH] — [Eviction Lab 2024](https://evictionlab.org/we-made-a-simple-eviction-data-request-to-all-50-states-this-is-what-we-learned/)
- **Oklahoma**: bulk distribution of OSCN data is prohibited by the 2009 order [SEARCH] — [Justia](https://law.justia.com/cases/oklahoma/supreme-court/2009/457676.html)
- **Debt Collection Lab**: obtained its multi-state data by "scraping and FOIA requests with courts" [SEARCH] — [Get the data](https://student-debt-research--debt-collection-lab.netlify.app/get-the-data)
- **MuckRock**: no MuckRock release of bulk civil judgment dockets was found. One MuckRock-hosted response shows California's statewide office does not hold superior-court case records and sends requesters to each court's clerk [SEARCH] — [MuckRock CA request](https://muckrock.com/foi/california-52/untitled-162145)

### Inferences
- **Best request targets**:
  - **Florida clerks.** They hold both the Official Records (recorded judgments, lis pendens, satisfactions) and the court dockets, and Chapter 119 limits charges to the actual cost of duplication [UNVERIFIED for bulk-extract programming charges, which s.119.07(4)(d) may allow as a "special service charge"].
  - **California superior courts' case indexes.** These are cheap and carry party names.
  - **Ohio.** Sup.R. 44-47 permits bulk distribution at cost [UNVERIFIED].
  - **Texas.** The Public Information Act excludes the judiciary (Gov't Code 552.003) [UNVERIFIED], but county clerks' real-property records (abstracts of judgment) are county records open under the PIA and common law [UNVERIFIED]. A PIA request to a county clerk for an export of the abstract-of-judgment index is plausible at programming cost.

### Gaps
- No documented example of a free (no-cost) bulk judgment-docket release was found.
- Current fee schedules for Santa Clara and Fresno, and whether a digital index is cheaper than the CD.
- Whether Ohio, Georgia, Michigan and Nevada courts have answered bulk requests for party-level civil data.
