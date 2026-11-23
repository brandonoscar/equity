# Federal free bulk datasets naming judgment, penalty and lien debtors

Research date: 2026-11-22. Tags: [LIVE] = fetched by me this session; [SEARCH] = search-result snippets only; [UNVERIFIED] = my own background knowledge, not confirmed this session.

**Network note (important for anyone re-checking):** this sandbox's egress proxy refused (HTTP 403 "no rule or network setting allows this host", or DNS failure) every one of these hosts: www.courtlistener.com/terms (CloudFront 403), wiki.free.law, free.law, www.fjc.gov, enforcedata.dol.gov, apiprod.dol.gov, data.dol.gov, echo.epa.gov, www.sec.gov, sam.gov, www.treasury.gov, www.govinfo.gov, api.govinfo.gov, api.consumerfinance.gov, www.consumerfinance.gov, data.sba.gov, banks.data.fdic.gov, www.occ.treas.gov, www.cftc.gov, www.ftc.gov, www.nlrb.gov, www.finra.org, catalog.data.gov. The only federal-court bulk host reachable was the CourtListener S3 bucket `com-courtlistener-storage.s3-us-west-2.amazonaws.com` (the `storage.courtlistener.com` alias itself failed). So everything outside CourtListener S3 is [SEARCH] at best. These hosts must be allowed in the session's network settings to verify live.

## Ranking (most useful first, for "debtor with money judgment who owns real property")

1. **FJC Integrated Database (civil), via CourtListener S3 bulk copy or FJC directly** — names plaintiff and defendant, who won, nature of judgment (monetary), amount received, county of residence, termination date. Only free federal bulk source that pairs a named party with a money judgment. Weaknesses: names truncated, no addresses, amounts in thousands, CourtListener copy ends at filings through 2022-03-31, no satisfaction status.
2. **EPA ECHO ICIS-FE&C case download (CASE_DEFENDANTS + CASE_PENALTIES + cost recovery)** — named defendants with penalty and Superfund cost-recovery amounts; facility addresses link to real property; CERCLA 107(l) liens attach to the cleaned-up property itself.
3. **DOL WHD compliance actions** — named employer, address, back wages and civil money penalties assessed; but assessed amounts are not judgments; free API key required on the new portal.
4. **SBA 7(a)/504 FOIA loan files** — borrower name and address with loan status including charged-off (a debt owed to lender/SBA, often later referred to Treasury). Not a judgment, but strong "distressed debtor" signal tied to a business address.
5. **CourtListener dockets bulk file** — every federal docket CourtListener knows, with case name, nature of suit, dates, PACER case id; party names only inside `case_name`; no parties table, no docket entries, no judgment amounts in the bulk export.
6. **SEC / CFTC / FTC / CFPB / OCC / FDIC enforcement** — name defendants and amounts, but no confirmed official structured bulk feed (mostly HTML lists or spreadsheets on blocked hosts).
7. **SAM.gov exclusions** — names and addresses of debarred parties; not a debt record; daily public extract but access path (key vs no key) is contradictory.
8. **GovInfo USCOURTS** — opinions as PDFs with metadata; requires free api.data.gov key; party names only in case titles; low yield.
9. Not available in bulk: federal tax liens (IRS), Treasury Do Not Pay / Fiscal Service delinquent-debt data, FINRA disciplinary bulk, NLRB backpay structured data.

## 1. CourtListener / Free Law Project bulk data files: what is in them, party names, license, size, cadence

### Takeaway
The CourtListener bulk export (quarterly, public S3, no login) contains dockets (case name only, no parties table and no docket entries or RECAP documents), opinions, citations, judges/people, financial disclosures, and a full copy of the FJC Integrated Database. Party names are available only via `case_name` text and via the FJC IDB `plaintiff`/`defendant` columns. The bulk data is described as public-domain-marked, which reads as allowing commercial use, but the Free Law Project site footer says CC BY-ND 4.0, and I could not reach the terms page to settle it.

### Cited Findings
- [LIVE] Bucket listing works without credentials at `https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/?list-type=2&prefix=bulk-data/` (1,111 keys total). `https://storage.courtlistener.com/...` did not connect from this sandbox. — [S3 listing](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/?list-type=2&prefix=bulk-data/)
- [LIVE] Latest snapshot is dated 2026-09-30; earlier snapshots in the listing fall at quarter ends (e.g. 2025-12-31, 2026-03-31, 2026-06-30, 2026-09-30) with some irregular dates in 2024–2025. Files in the 2026-09-30 snapshot (bz2-compressed CSV, sizes compressed): `dockets` 5.144 GB; `opinions` 55.253 GB; `opinion-clusters` 2.468 GB; `citation-map` 0.533 GB; `citations` 0.127 GB; `oral-arguments` 0.692 GB; `parentheticals` 0.292 GB; `fjc-integrated-database` 0.280 GB; `originating-court-information` 0.023 GB; `unmatched-citations` 0.222 GB; `financial-disclosure*` (investments 0.037 GB, debts, gifts, etc.); `people-db-*`; `courts`, `courthouses`; plus `schema-2026-09-30.sql` and `load-bulk-data-2026-09-30.sh`. — [S3 listing](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/?list-type=2&prefix=bulk-data/)
- [LIVE] The load script COPYs only these tables: audio, citations, disclosures_*, people_db_* (person, education, position, race, retention, school, political affiliation), recap_fjcintegrateddatabase, search_citation, search_court, search_courthouse, search_docket, search_opinion, search_opinioncluster (+panel, joined_by, non-participating judges), search_opinionscited, search_originatingcourtinformation, search_parenthetical. **Not exported:** `people_db_party`, `people_db_partytype`, `people_db_attorney`, `search_docketentry`, `search_recapdocument` (these tables exist in the schema but are not in the bulk files). — [load-bulk-data-2026-09-30.sh](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/load-bulk-data-2026-09-30.sh); [schema-2026-09-30.sql](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/schema-2026-09-30.sql)
- [LIVE] `dockets` CSV columns include: id, date_filed, date_terminated, date_last_filing, case_name_short, case_name, case_name_full, docket_number, docket_number_core, pacer_case_id, cause, nature_of_suit, jury_demand, jurisdiction_type, court_id, idb_data_id (FK to FJC IDB row), assigned_to_str, originating_court_information_id, federal_dn_case_type, federal_dn_office_code, parent_docket_id. Sample rows include federal district dockets (e.g. `wvnd` 5:94-cv-00102 "Brady v. Pyle Transport", nature_of_suit "350 Motor vehicle personal injury") and also state appellate dockets (Texas Court of Criminal Appeals, Florida 4th DCA). No address, amount or satisfaction columns. — [dockets-2026-09-30.csv.bz2](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/dockets-2026-09-30.csv.bz2)
- [LIVE] `originating-court-information` has `date_judgment`, `date_judgment_eod`, `date_disposed` for appealed cases (lower-court judgment dates, no amounts). — [schema-2026-09-30.sql](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/schema-2026-09-30.sql)
- [SEARCH] CourtListener's bulk data page says the files are "free of known copyright restrictions" with a Public Domain Mark; the Free Law Project site footer says content is CC BY-ND 4.0 "except where indicated". Files are full snapshots (not deltas) regenerated quarterly on the last day of March, June, September and December. — [Bulk Legal Data](https://courtlistener.com/help/api/bulk-data/); [wiki bulk data](https://wiki.free.law/c/courtlistener/help/api/bulk-data)
- [SEARCH] API (not bulk) use: Free Law Project membership API access is limited to small firms, academics, small media and pre-revenue organizations; others are offered commercial agreements. — [API included in memberships (2026-05-07)](https://free.law/2026/05/07/api-included-in-memberships/); [GitHub discussion #6869](https://github.gg22.workers.dev/freelawproject/courtlistener/discussions/6869)
- [LIVE] `www.courtlistener.com/help/api/bulk-data/` returns 301 (to wiki.free.law, which is blocked here); `www.courtlistener.com/terms/` returned a CloudFront 403 to this sandbox. — direct curl.

### Inferences
- Bulk files need no login, no key, and are not a search portal, so they fit the constraints. The API (party lists, docket entries) does not.
- To get party names for federal civil cases in bulk, join `dockets.idb_data_id` → `fjc-integrated-database.id`, or parse `case_name` ("X v. Y").
- The public-domain mark on the bulk files suggests commercial use is allowed; the API membership limit is about the API, not the S3 files. Still to confirm against the current terms text.

### Gaps
- Exact current license wording on the bulk-data page and the FLP terms page (hosts blocked). Whether FLP considers commercial reuse of bulk files subject to any agreement.
- Row count of `dockets` (5.1 GB bz2, not decompressed here).

## 2. Federal Judicial Center Integrated Database (civil): party names? judgment amounts?

### Takeaway
Yes on both, coarsely. The civil IDB has plaintiff and defendant names (truncated), the winning side, nature of judgment (monetary vs other), amount received (in $ thousands), county of residence (FIPS) and termination date. No addresses, no satisfaction data. CourtListener's copy has 10.3 M rows but stops at filings through 2022-03-31; FJC's own site (blocked here) has newer releases.

### Cited Findings
- [LIVE] `fjc-integrated-database-2026-09-30.csv.bz2` is 279.6 MB compressed and has **10,323,280 rows**. Max `date_filed` = **2022-03-31**. `dataset_source` counts: 9 → 9,298,201; 4 → 941,006; 2 → 70,824; 10 → 11,894; 8 → 1,355. — [fjc-integrated-database-2026-09-30.csv.bz2](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/fjc-integrated-database-2026-09-30.csv.bz2)
- [LIVE] Columns: office, docket_number, origin, date_filed, jurisdiction, nature_of_suit, title, section, subsection, diversity_of_residence, class_action, monetary_demand, county_of_residence, arbitration_at_filing/termination, MDL number, **plaintiff**, **defendant**, transfer fields, date_terminated, termination_class_action_status, procedural_progress, disposition, **nature_of_judgement**, **amount_received**, **judgment**, pro_se, year_of_tape, nature_of_offense, version, circuit_id, district_id. — same file / [schema](https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/schema-2026-09-30.sql)
- [LIVE] Value distributions: `judgment` blank 5.91 M, 0 → 2.35 M, 2 → 1.20 M, 1 → 744,954, 4 → 61,818, 3 → 60,643; `nature_of_judgement` blank 5.65 M, 0 → 4.04 M, 1 → 321,584, 2 → 121,381, 4 → 92,863, 5 → 56,472, 3 → 21,282, 6 → 12,154; `amount_received` non-zero in 457,551 rows. Sample N.D. W.Va. rows: OWEN v. MCANALLEN CORP (terminated 1990-01-02, amount 1830, county 54033); UNITED STATES OF AMERICA v. DAUGHERTY COAL CO (1990-03-22, amount 6000, county 54077). — same file
- [UNVERIFIED] FJC codebook meanings (from memory): `judgment` 1 = for plaintiff, 2 = for defendant, 3 = both, 4 = unknown; `nature_of_judgement` 1 = monetary award only, 2 = monetary award and other; `amount_received` and `monetary_demand` in thousands of dollars; 9999 = over $9.999 M. Confirm against FJC civil codebook.
- [SEARCH] FJC maintains codebooks documenting field changes; IDB covers civil filings and terminations in district courts; FLP notes "many of the fields are artificially truncated" and judge fields are blank by Judicial Conference policy. — [FJC IDB](https://www.fjc.gov/research/idb); [FLP IDB facts](https://free.law/idb-facts/)

### Inferences
- Filter: `judgment=1` (plaintiff won) AND `nature_of_judgement IN (1,2)` AND `amount_received>0` gives a list of named federal judgment debtors (the defendant) with an approximate amount and county — directly matches the "lien behind our property" question. United States as plaintiff rows are candidate 28 USC 3201 judgment-lien debtors.
- Defendant names are truncated (~30 chars) and have no address, so matching to parcel owners needs county FIPS + fuzzy name.
- For post-2022 data, FJC's own downloads (blocked here) must be used; their cadence is [UNVERIFIED] (historically quarterly-to-annual releases).

### Gaps
- FJC's own current release date, format (SAS/CSV/TSV), and whether any login is needed — www.fjc.gov blocked.
- Why CourtListener's copy stops at 2022-03.

## 3. Agency enforcement data naming debtors with amounts

### Takeaway
EPA ECHO and DOL WHD are the best agency bulk sources (named respondent, address, dollar amount, date). SBA 7(a) FOIA files show charged-off borrowers. SEC/CFTC/FTC/CFPB/OCC/FDIC have no confirmed free structured bulk feed; FINRA has none; IRS liens, Do Not Pay and NLRB backpay are not published in bulk.

### Cited Findings
**EPA ECHO (ICIS-FE&C)**
- [SEARCH] The ICIS-FE&C download is a ZIP of ~22 CSVs including CASE_ENFORCEMENTS.csv, CASE_VIOLATIONS.csv, CASE_ENFORCEMENT_TYPE.csv, CASE_ENFORCEMENT_CONCLUSIONS.csv, **CASE_DEFENDANTS.csv**, **CASE_PENALTIES.csv**; penalties are reported in PENALTIES and CASE CONCLUSION files; cost recovery is EPA Superfund cleanup costs recovered from responsible parties; amounts are summed across settlements and not split among defendants; entry can lag case conclusion by several months. A data.gov record points to `case_downloads.zip` on echo.epa.gov. — [ICIS-FE&C Download Summary](https://echo.epa.gov/tools/data-downloads/icis-fec-download-summary); [ECHO Data Downloads](https://echo.epa.gov/node/113); [data.gov EPA Enforcement Action Data Set](https://catalog-beta.data.gov/dataset/epa-enforcement-and-compliance-history-online-epa-enforcement-action-data-set)
- [UNVERIFIED] No login or key needed for ECHO ZIP downloads; refreshed weekly. Not confirmed (host blocked).

**DOL Wage and Hour (WHD)**
- [SEARCH] WHD compliance action dataset covers all concluded WHD compliance actions since FY2005 with whether violations found, back wage amount, employees due back wages, and civil money penalties assessed; DOL says the enforcement website will be retired in favor of the Open Data Portal. — [data.gov WHD Compliance Action Data](https://catalog.data.gov/dataset/wage-and-hour-division-compliance-action-data); [enforcedata.dol.gov catalogs](https://enforcedata.dol.gov/views/data_catalogs.php)
- [SEARCH] Third-party docs say the DOL API (apiprod.dol.gov, v4) needs a **free API key** from dataportal.dol.gov/registration. Unofficial. — [Apify actor](https://apify.com/thoob/dol-whd-violations-feed)
- [UNVERIFIED] WHD rows include trade name, legal name, street address, city, state, zip, NAICS, findings dates; OSHA inspection/violation data (penalty, penalty paid/current) is in the same DOL catalog.

**SBA loans**
- [SEARCH] SBA 7(a)/504 FOIA loan-level CSVs on data.sba.gov, split FY1991–1999, 2000–2009, 2010–2019, 2020–present, updated quarterly (latest labeled as of 2026-06-30 / 260331 seen), loans approved since FY1991, with an XLSX data dictionary (as of 251231). — [data.sba.gov 7a-504 FOIA](https://data.sba.gov/dataset/7a-504-foia); [Data Dictionary](https://data.sba.gov/en/dataset/7-a-504-foia/resource/6898b986-a895-47b4-bb7e-c6b286b23a7b)
- [UNVERIFIED] Fields include BorrName, BorrStreet, BorrCity, BorrState, BorrZip, LoanStatus (e.g. PIF, CHGOFF), ChargeOffDate, GrossChargeOffAmount. Search could not confirm field names.
- [SEARCH] PPP all-loans CSV on sba.gov was last updated 2025-03-07; no PPP charge-off field confirmed. — [SBA PPP data](https://www.sba.gov/programas-de-financiamiento/prestamos/opciones-de-asistencia-por-covid-19/programa-de-proteccion-de-pago/datos-del-ppp)

**SEC / CFTC / FTC / CFPB / FINRA / OCC / FDIC**
- [SEARCH] SEC litigation releases are HTML listings on sec.gov; no official structured feed surfaced; sec-api.io (paid third party) offers 10,000+ releases since 1995. — [SEC Litigation Releases](https://www.sec.gov/litigation/litreleases); [sec-api.io](https://sec-api.io/docs/sec-litigation-releases-database-api)
- [UNVERIFIED] sec.gov offers RSS for litigation releases (`/litigation/litreleases.rss`) — curl was refused by the proxy, so not confirmed.
- [SEARCH] CFPB enforcement summary CSVs existed but the cited version was published November 2020, said to be updated annually; current status unconfirmed. — [CFPB enforcement database (archived)](https://webarchive.library.unt.edu/web/20201218011626/https://www.consumerfinance.gov/enforcement/payments-harmed-consumers/enforcement-database)
- [SEARCH] FINRA does not publish a general-purpose developer API for BrokerCheck or disciplinary data; its API console needs firm entitlements; an undocumented api.brokercheck.finra.org JSON endpoint exists (unofficial). — [dev.to guide](https://dev.to/nexgendata/how-to-vet-a-stockbroker-with-finra-brokercheck-free-api-guide-3hkp); [developer.finra.org](https://developer.finra.org/docs)
- [SEARCH] OCC: all public enforcement actions since August 1989 downloadable via apps.occ.gov/EASearch, plus a spreadsheet with an Enforcement Order Listing Definitions PDF; actions since 2012 have subject matter. — [OCC enforcement actions index](https://www.occ.treas.gov/topics/laws-and-regulations/enforcement-actions/index-enforcement-actions.html); [EASearch](https://apps.occ.gov/EASearch)
- FDIC, CFTC, FTC, NLRB, HUD: no search results confirmed a structured bulk feed; hosts blocked. [Gap]

**IRS / Treasury**
- [UNVERIFIED] Federal tax liens (Notices of Federal Tax Lien) are filed with county recorders / state SOS, not published in bulk by IRS. Treasury Do Not Pay and Fiscal Service Cross-Servicing / TOP delinquent-debtor data are restricted to authorized agencies, not public. No source fetched this session confirms either.

### Inferences
- Agency "assessed" penalties are not court judgments; only those reduced to judgment (or CERCLA liens) create property liens. Use them as "debtor-distress" signals and to find addresses.
- DOL's API key is free; the user must decide whether a key counts as a "login".

### Gaps
- Live row counts, field lists and cadence for ECHO, WHD, OSHA, SBA (all hosts blocked).
- Whether WHD/OSHA records show paid vs outstanding amounts.

## 4. SAM.gov exclusions, OFAC, GovInfo USCOURTS

### Takeaway
SAM exclusions extract is daily and names debarred parties with addresses, but whether it downloads without a key is contradictory. OFAC SDN is free bulk but is sanctions, not debt. GovInfo USCOURTS opinions need a free api.data.gov key and carry party names only in case titles.

### Cited Findings
- [SEARCH] SAM public exclusions extract is a list of all parties with currently active exclusions, daily file `SAM_Exclusions_Public_Extract_V2_YYDDD.ZIP`; GSA's Extracts API says a SAM.gov account + API key is needed (limits 10/day for non-federal no-role up to 1,000/day federal); SAM help says no key is needed "if you only want to download prepared data extracts". Conflict unresolved. — [SAM Entity Extracts API](https://open.gsa.gov/api/sam-entity-extracts-api); [Exclusions API](https://open.gsa.gov/api/exclusions-api); [data.gov SAM Exclusions extract](https://catalog.data.gov/dataset/system-for-award-management-sam-public-extract-exclusions); [SAM help](https://sam.gov/content/help)
- [SEARCH] GovInfo API needs a free 40-char api.data.gov key; USCOURTS = opinions from selected appellate, district and bankruptcy courts; a Bulk Data Repository exists but USCOURTS bulk availability was not confirmed. — [GovInfo USCOURTS help](https://www.govinfo.gov/help/uscourts); [usgpo/api GitHub](https://github.com/usgpo/api); [GovInfo API signup](https://www.govinfo.gov/api-signup)
- [UNVERIFIED] OFAC SDN list is free bulk (CSV/XML) at treasury.gov / sanctionslistservice.ofac.treas.gov, no key; names, addresses, programs; not debt. Host refused from sandbox.

### Inferences
- Exclusions sometimes follow fraud judgments but carry no amounts; low value for lien equity.
- USCOURTS opinions are a tiny subset of cases and require parsing PDFs; CourtListener opinions bulk already covers them.

### Gaps
- Whether SAM extract URL works without a key (sam.gov blocked).

## 5. Which sources create or evidence a lien on real property

### Takeaway
A federal civil money judgment becomes a lien on the debtor's real property only when an abstract is filed in the same place as a federal tax lien notice (28 USC 3201) — i.e. it lives in county/state lien records, not in federal bulk data. CERCLA 107(l) liens attach to the specific property subject to cleanup. Bulk federal data can only identify candidate judgments; the lien itself must be confirmed in the recorder.

### Cited Findings
- [SEARCH] 28 USC 3201: a judgment in a civil action creates a lien on all real property of the judgment debtor on filing a certified copy of the abstract of judgment in the manner a notice of tax lien would be filed; the court may order sale of real property subject to the lien; a debtor with a federal judgment lien is ineligible for federal grants/loans. Subsection (c) covers duration/renewal. — [28 USC 3201 (LII)](https://www.law.cornell.edu/uscode/text/28/3201)
- [UNVERIFIED] 3201(c): the lien lasts 20 years, renewable once for another 20 years if a notice of renewal is filed and court approves. Search snippet did not show the figure.
- [SEARCH] CERCLA 107(l): lien in favor of the US on real property that belongs to the liable person and is subject to or affected by a removal or remedial action; unfiled lien is subordinate to rights perfected before EPA files notice; ends when liability is satisfied or time-barred under section 113. — [EPA 1987 guidance on federal Superfund liens](https://www.epa.gov/sites/production/files/2013-09/documents/fed-sflien-mem.pdf)
- [UNVERIFIED] Other federal liens that attach to real property once noticed: IRS tax liens (26 USC 6321/6323), CERCLA 107(r) windfall liens, criminal restitution/fines (18 USC 3613, treated like tax liens). None are published in federal bulk data.

### Inferences
- FJC IDB rows with plaintiff "UNITED STATES" and a monetary judgment are the best federal-bulk proxy for 28 USC 3201 lien candidates; ECHO cost-recovery cases point to CERCLA lien candidates with a facility address.
- Neither source says whether the judgment was satisfied; satisfaction requires the docket (PACER/RECAP) or a recorder release.

### Gaps
- No federal bulk source records abstract filing or lien release. FJC IDB and CourtListener bulk have no satisfaction field.

## Checked live, 2026-11-23 (network open)

**FJC IDB, FJC's own file** — built as `us.fjc.idb.direct.civil_judgments`.
- [LIVE] fjc.gov "Civil Cases Filed, Terminated, and Pending (SY 1988 - present)" offers the "Civil Cases Cumulative File" as tab-delimited text (`/sites/default/files/idb/textfiles/cv88on.zip`, 329,665,474 bytes, Last-Modified 2026-08-26, terminated through 2026-06-30, 10,960,173 records) plus per-year SAS files (`cv25.sas7bdat`, `cv26.sas7bdat`, `cv21to26.zip`). Codebook: `Civil Codebook 1988 Forward 10252023.pdf`. No login.
- [LIVE] Codebook confirms JUDGMENT 1 = plaintiff, NOJ 1/2 = monetary award (only / and other), 5 = costs only, 6 = costs and attorney fees, AMTREC in thousands, and warns AMTREC is not mandatory and 9999 may mean "over $1 million" or a filler.
- [LIVE] **fjc.gov/robots.txt disallows `/research/idb/` and `/sites/default/files/idb`** (Crawl-delay 30). The adapter is therefore `manual`: a person downloads the zip and the adapter reads it from `data/manual/`.
- [LIVE] DISTRICT is the AO numeric code ("13", "3A", "7-"); the config maps it to PACER ids. 430,832 kept money judgments for the plaintiff, terminated 1984-05-03 to 2026-06-30; 15,018 terminated after 2022-03-31. 412,253 of CourtListener's 412,266 kept keys (district + office + docket + filing date) are in the FJC file.

**EPA ECHO ICIS-FE&C** — built as `us.epa.echo.judicial_cases`.
- [LIVE] `https://echo.epa.gov/files/echodownloads/case_downloads.zip` (81,294,734 bytes, 22 CSVs, Last-Modified 2026-11-21), no login; robots.txt (Crawl-delay 10) does not disallow `/files/`. 137,209 cases: 9,118 judicial (JDC), 128,091 administrative formal (AFR).
- [LIVE] Defendants have names only (no address); CASE_FACILITIES has facility street addresses; CASE_REGIONAL_DOCKETS has the court's civil action number for judicial cases; no field names the district court.

**DOL WHD** — not built.
- [LIVE] enforcedata.dol.gov and its data catalog now redirect to data.dol.gov (a JavaScript app). WHD "Enforcement" (dataset 10362, `WHD_enforcement`, quarterly, concluded actions since FY 2005) is served only by `apiprod.dol.gov/v4/get/WHD/enforcement/...`, which answers 401 "The API key is either incorrect or missing" without an `X-API-KEY`. The dataset list (`/v4/datasets`) is open but has no file download. A key requires portal registration, which counts as a login here, so WHD is skipped.
