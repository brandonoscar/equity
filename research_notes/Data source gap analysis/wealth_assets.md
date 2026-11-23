# Free bulk sources of income/wealth signals and non-real-estate assets (gap analysis for /home/user/equity)

Tags: [LIVE] = fetched or probed from this session on 2026-11-23 (HTTP status, sizes, headers or file contents seen directly). [SEARCH] = from a web-search summary or secondary page, not opened. [UNVERIFIED] = prior knowledge or inference not confirmed this session.

**Legal restrictions, up front:**
- **FEC individual contributor data: the law bars using it "for any commercial purpose" or to solicit contributions.** A debt-collection or debtor-asset product is very likely a commercial purpose. Treat FEC contributor names and addresses as off-limits for linking or enrichment in a commercial pipeline unless counsel clears it. See section 1.
- **ProPublica Nonprofit Explorer terms forbid resale, sublicensing and stand-alone redistribution.** The underlying IRS 990 XML has no such restriction, so ingest from the IRS.
- **FAA aircraft registry: owners may ask the FAA to withhold their name and address from public display (49 USC 44114(b)).** Records that are absent or redacted are not evidence that a person owns no aircraft.
- **USCG vessel documentation: individual owner names and addresses were removed from the public MVUS file in June 2017.** The public bulk file cannot reliably link a person to a vessel.
- **Crypto wallet attribution is deanonymization.** OFAC SDN addresses identify sanctioned persons, and dealing with them is prohibited. Collection use also raises FDCPA/Reg F and privacy concerns. See section 8.

## Repo baseline: none of these sources exist yet

### Takeaway
None of the eight source families has an adapter or config in `src/` or `config/`. The only trace is that the `source.kind` CHECK constraint already allows `'aircraft'` and `'vessel'`. No adapter uses those kinds.

### Cited Findings
- `grep` over `src/` and `config/` (`*.py`, `*.yaml`, `*.sql`) found no matches for: fec.gov / campaign contributions; Form 990 / ProPublica / nonprofit; SEC EDGAR / Form D / 13F / insider; ENS / OFAC / SDN / crypto / wallet / bitcoin / ethereum; USPTO / PatentsView. [LIVE, local repo]
- These hits were incidental:
  - "Edgartown" in `config/states/ma.yaml`.
  - "a professional license number" as a PII note in `config/liens/ca.ftb.top500_personal.yaml`.
  - "VESSEL LIEN" as a UCC filing type in `config/liens/ct.sots.liens.yaml`.
  - "LETTERS PATENT" as an ACRIS doc type in `config/recorders/ny.nyc.acris.yaml`. [LIVE, local repo]
- `src/equity/schema/migrations/V0014__zoning_and_new_source_kinds.sql` adds `'aircraft'` and `'vessel'` to the allowed `source.kind` values ("new source kinds for the non-parcel datasets (zoning, flood zones, aircraft, vessels)"). No Python under `src/` references aircraft or vessel adapters. [LIVE, local repo]

### Inferences
- The FAA registry (section 5) is the closest fit. The schema already expects it, and it is free, daily, with no login.

### Gaps
- None.

## 1. FEC individual contributions (employer, occupation, address, amount)

### Takeaway
The bulk files are free and huge: `indiv26.zip` is 2.69 GB and refreshed within the last day. They carry name, city, state, ZIP, employer, occupation, date and amount, but **no street address**. The OpenFEC API adds street fields. **Federal law prohibits using individual contributor information for any commercial purpose or for solicitation**, so this source is high-risk for a commercial debtor-asset product.

### Cited Findings
- **Bulk file location:**
  - `https://www.fec.gov/files/bulk-downloads/2026/indiv26.zip` returned HTTP 200: 2,686,294,501 bytes, Last-Modified Sun 22 Nov 2026 17:00 GMT. [LIVE]
  - `.../2024/indiv24.zip` is 4,234,505,004 bytes, also Last-Modified 22 Nov 2026, so prior cycles are re-published too. [LIVE]
  - The bulk-data browse page is https://www.fec.gov/data/browse-data/?tab=bulk-data [LIVE]
- **Bulk file layout** (pipe-delimited text; header from the FEC data dictionary, `indiv_header_file.csv`): `CMTE_ID, AMNDT_IND, RPT_TP, TRANSACTION_PGI, IMAGE_NUM, TRANSACTION_TP, ENTITY_TP, NAME, CITY, STATE, ZIP_CODE, EMPLOYER, OCCUPATION, TRANSACTION_DT, TRANSACTION_AMT, OTHER_ID, TRAN_ID, FILE_NUM, MEMO_CD, MEMO_TEXT, SUB_ID`. There is no street column. [LIVE](https://www.fec.gov/files/bulk-downloads/data_dictionaries/indiv_header_file.csv)
- **OpenFEC API, Schedule A (`/v1/schedules/schedule_a/`):**
  - Works with `api_key=DEMO_KEY`.
  - Returns `contributor_name`, `contributor_first_name`/`last_name`/`middle_name`, `contributor_street_1`, `contributor_street_2`, `contributor_city`, `contributor_state`, `contributor_zip`, `contributor_employer`, `contributor_occupation`, `contributor_aggregate_ytd`, `contributor_id`.
  - A 2026-cycle query with `min_amount=1000` reported about 2.69M matching rows.
  - The API uses keyset pagination (`last_index`). [LIVE](https://api.open.fec.gov/v1/schedules/schedule_a/)
- **What the FEC says the law prohibits:**
  - "information about individual contributors taken from FEC reports cannot be sold or used for soliciting contributions (including any political or charitable contribution) or for any commercial purpose."
  - The FEC adds that "the Act prohibits the sale or use of any information about those donors, including their names and addresses, for the purpose of soliciting contributions or for commercial purposes."
  - The restriction "applies only to the use of individual contributor information"; names of political committees may be compiled and sold. [LIVE](https://www.fec.gov/updates/sale-or-use-contributor-information/)
- **Permitted uses** the FEC lists from advisory opinions:
  - bona fide academic research that does not involve commercial use or solicitation (AO 1986-25);
  - news media use (newspapers, magazines, books) where the principal purpose is not solicitation or commercial activity;
  - commercial websites that show only **aggregated** committee data without contributors' contact information (AO 2014-07, AO 2012-22). [LIVE](https://www.fec.gov/updates/sale-or-use-contributor-information/)
- **Disclosure threshold:** committees must itemize contributors who give more than $200 per election cycle (or calendar year for PACs and parties), with name, mailing address, occupation and employer. [LIVE](https://www.fec.gov/updates/sale-or-use-contributor-information/)
- The statutory cite is 52 U.S.C. 30111(a)(4), as given in the assignment. The FEC page refers to "the Act". [UNVERIFIED that the page cites the section number]
- Committees may "salt" reports with up to 10 pseudonyms to detect misuse (11 CFR 104.3(e)). [UNVERIFIED, prior knowledge]

### Inferences
- **Linkage:** match on name plus city/state/ZIP5 from the bulk files, or on street from the API. EMPLOYER/OCCUPATION is an income proxy, and repeated large gifts signal disposable wealth. Without street in bulk, matches on common names are weak.
- **Legal:** using these records to find or score debtors for collection or for sale is almost certainly the "commercial purpose" the Act bans. Do not build this for a commercial product. At most, an aggregate-only research feature with no PII output, after counsel review.

### Gaps
- No FEC enforcement case on debt-collection use specifically was found this session.
- The exact bulk refresh cadence was not captured; the page is JavaScript-rendered. Last-Modified suggests at least daily or weekly regeneration.

## 2. Nonprofit Form 990s (IRS e-file XML, officer compensation, ProPublica API)

### Takeaway
The IRS now publishes 990 e-file XML as monthly-batched ZIPs (about 70 MB each) plus a yearly CSV index, free with no login. Officer, director and key-employee compensation (Part VII / Schedule J) lives in the XML. ProPublica's API is free and needs no key, but its **terms forbid resale, sublicensing and stand-alone redistribution**, so ingest from the IRS instead.

### Cited Findings
- **IRS "Form 990 Series Downloads" page:**
  - 79 links, covering 2019–2026 (10/10/2/2/13/13/17/12 files per year).
  - Example: `https://apps.irs.gov/pub/epostcard/990/xml/2026/2026_TEOS_XML_01A.zip`, 71,497,607 bytes, Last-Modified 19 Feb 2026. [LIVE](https://www.irs.gov/charities-non-profits/form-990-series-downloads)
- **Index file:** `index_2026.csv` has columns `RETURN_ID, FILING_TYPE, EIN, TAX_PERIOD, SUB_DATE, TAXPAYER_NAME, RETURN_TYPE (990/990EZ/990PF…), DLN, OBJECT_ID, XML_BATCH_ID` and about 516,019 rows. [LIVE](https://apps.irs.gov/pub/epostcard/990/xml/2026/index_2026.csv)
- **EO Business Master File extract** (org name, EIN, address, asset/income codes): the page is live. [LIVE](https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf)
- **ProPublica Nonprofit Explorer API v2:**
  - Endpoints: `/nonprofits/api/v2/search.json?q=` and `/nonprofits/api/v2/organizations/{EIN}.json`. Both returned JSON with no key.
  - The org object has `ein, name, careofname, address, city, state, zipcode, ntee_code, asset_amount, income_amount, revenue_amount`.
  - `filings_with_data` has `totrevenue, totassetsend, totliabend, compnsatncurrofcr, pct_compnsatncurrofcr, secrdmrtgsend, pdf_url`, among others.
  - Search returns 25 results per page (changelog, Sept 2023).
  - Per-person compensation rows are **not** in the API summary, only total officer compensation. [LIVE](https://projects.propublica.org/nonprofits/api)
- **ProPublica data terms:** "You can't republish the raw data in its entirety or otherwise distribute the data (in whole or in part) on a stand-alone basis… You can't charge people money to look at the data or sell advertising specifically against it. You can't sub-license or resell the data to others. If you use the data for publication, you must cite ProPublica." [LIVE](https://www.propublica.org/about/propublica-data-terms-of-use)
- The XML element for Part VII rows (`Form990PartVIISectionAGrp` with PersonNm, TitleTxt, ReportableCompFromOrgAmt, ReportableCompFromRltdOrgAmt, OtherCompensationAmt) was not opened this session. [UNVERIFIED, prior knowledge]
- 990 XML has historically also been on AWS (the s3 `irs-form-990` bucket). The IRS stopped updating that bucket around end of 2021 in favor of these downloads. [UNVERIFIED]

### Inferences
- **Linkage:**
  - **Person to income:** officer name plus organization (with EIN and org address) to reported compensation. There is no home address, so the link to a debtor needs a name plus a corroborating signal such as the org's city or a recorder/SOS hit.
  - **Entity debtors:** an EIN or entity name match gives a nonprofit's assets, liabilities and secured mortgage balances (`secrdmrtgsend`).
- 990 returns are public by statute (IRC 6104). There is no use restriction on the IRS copy beyond ordinary privacy law, and Schedule B donor names are redacted in public copies. [UNVERIFIED]

### Gaps
- No total-size figure for all IRS 990 ZIPs.
- The per-person compensation XPath was not verified against a 2026 file.

## 3. SEC EDGAR: Forms 3/4/5 insider holdings, Form D, 13F; bulk/full-text APIs and fair-access rules

### Takeaway
The SEC publishes quarterly flattened TSV datasets for Forms 3/4/5, Form D and 13F. They are free and contain names, addresses and amounts. The fair-access rules are **10 requests/second max and a declared User-Agent with a contact email**. EDGAR has no use restriction for commercial purposes beyond those access rules.

### Cited Findings
- **Fair access:** "10 requests/second… SEC reserves the right to limit request rates… The SEC does not allow botnets or automated tools to crawl the site." Declare a User-Agent such as "Sample Company Name AdminContact@<sample company domain>.com". EDGAR data goes back to 1994/1995. [LIVE](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
- **Insider Transactions (Forms 3/4/5) data sets:** quarterly, e.g. `/files/datastandardsinnovation/data/insider-transactions-data-sets/2026q3_form345.zip`, 8.66 MB. [LIVE](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets) Tables:
  - `REPORTINGOWNER`: `RPTOWNERCIK, RPTOWNERNAME, RPTOWNER_RELATIONSHIP, RPTOWNER_TITLE, RPTOWNER_STREET1/2, CITY, STATE, ZIPCODE`.
  - `SUBMISSION`: `ISSUERCIK, ISSUERNAME, ISSUERTRADINGSYMBOL, FILING_DATE, PERIOD_OF_REPORT`.
  - `NONDERIV_TRANS`: `TRANS_DATE, TRANS_CODE, TRANS_SHARES, TRANS_PRICEPERSHARE, SHRS_OWND_FOLWNG_TRANS, VALU_OWND_FOLWNG_TRANS, DIRECT_INDIRECT_OWNERSHIP`.
  - `NONDERIV_HOLDING`, `DERIV_TRANS`, `DERIV_HOLDING`, `FOOTNOTES`, `OWNER_SIGNATURE`.
- **Form D data sets:** quarterly, e.g. `/files/datastandardsinnovation/data/form-d-data-sets/2026q3_d.zip`, 3.65 MB. The old `/dera/data/form-d-data-sets` path now returns 404, and file paths moved between `structureddata` and `datastandardsinnovation` in 2026. [LIVE](https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets) Tables:
  - `RELATEDPERSONS`: `FIRSTNAME, MIDDLENAME, LASTNAME, STREET1, STREET2, CITY, STATEORCOUNTRY, ZIPCODE, RELATIONSHIP_1..3` (Executive Officer, Director, Promoter).
  - `ISSUERS`: `CIK, ENTITYNAME, address, JURISDICTIONOFINC, ENTITYTYPE`, previous names.
  - `OFFERING`: `INDUSTRYGROUPTYPE, TOTALOFFERINGAMOUNT, TOTALAMOUNTSOLD, TOTALREMAINING, MINIMUMINVESTMENTACCEPTED, SALE_DATE`, security-type flags.
  - `RECIPIENTS` (sales compensation recipients with CRD numbers), `SIGNATURES`, `FORMDSUBMISSION`.
- **Form 13F data sets:** published in three-month windows, e.g. `01jun2026-31aug2026_form13f.zip`, 100.7 MB. [LIVE](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets) Tables:
  - `COVERPAGE`: `FILINGMANAGER_NAME`, street/city/state/zip, `CRDNUMBER`.
  - `INFOTABLE` (397 MB uncompressed): `NAMEOFISSUER, CUSIP, FIGI, VALUE, SSHPRNAMT, PUTCALL, VOTING_AUTH_*`.
  - `SIGNATURE`, `OTHERMANAGER`, `SUMMARYPAGE`.
- **EDGAR full-text search** (`efts.sec.gov/LATEST/search-index`) returned 403 to a simple unauthenticated probe. The documented endpoint is `efts.sec.gov/LATEST/search-index?q=...` behind efts. [LIVE probe 403; access path not resolved]
- Other free bulk feeds include `submissions.zip` and `companyfacts.zip` (nightly at `/Archives/edgar/daily-index/bulkdata/`), `data.sec.gov/submissions/CIK##########.json`, and quarterly `form.idx`/`master.idx` indexes. [UNVERIFIED this session]

### Inferences
- **Linkage:**
  - Form D `RELATEDPERSONS` gives a person's name and an address (often the issuer's business address, not home) tied to an issuer raising $X. It signals equity stakes in private companies.
  - Forms 3/4/5 give a person's name and address (often c/o the issuer), the issuer and share counts. Price times shares is a hard wealth value.
  - The owner CIK is a stable identifier for deduplication.
  - 13F is mostly institutions. It is useful only for entity debtors that are investment managers.
- Match keys: last/first name plus state/ZIP, then confirm with the issuer address or the SOS officer graph the repo already has (`config/business`).

### Gaps
- Did not confirm whether full-text search requires a browser-like request. It is free but not a bulk product.
- Did not verify the nightly `submissions.zip` size.

## 4. State business and professional licenses (bulk licensee files)

### Takeaway
Several large states publish free bulk licensee files:
- **Texas TDLR**: daily CSV, "All Licenses" 190 MB.
- **California CSLB**: contractor master, personnel and workers' comp files.
- **Florida DBPR**: weekly ASCII CSV, free download under Ch. 119 F.S.
- **New York**: attorney registrations on data.ny.gov, with name, firm and street address.

Coverage is patchy and per-board; there is no national file.

### Cited Findings
- **Texas TDLR:**
  - License Files page: "The files are updated everyday and saved in CSV (Comma delimited) format."
  - Links: `lrformat.txt` (layout), `ltlicfile.csv` ("All Licenses (190.19 Mb)"), plus per-program files (auctioneers, A/C technicians, etc.). [LIVE](https://www.tdlr.texas.gov/LicenseSearch/licfile.asp)
  - A copy is listed on data.gov as "TDLR - All Licenses". [SEARCH](https://catalog.data.gov/dataset/tdlr-all-licenses)
  - The "Other Files" page says previously published data must be requested via Open Records. [SEARCH](https://www.tdlr.texas.gov/LicenseSearch/otherfile.asp)
- **California CSLB, "Master List of California Licensed Contractors":**
  - Three files: License Master (license number, business name, address, phone, status, issue/expiration dates, classifications, bond and workers' comp info); Personnel (names, titles, classifications, bond); Workers' Compensation.
  - Only renewed or expired-but-renewable licenses are included.
  - "Email addresses are not provided (Business & Professions Code Section 27)". [LIVE](https://www.cslb.ca.gov/OnlineServices/DataPortal/ContractorList)
- **Florida DBPR:** "Under Chapter 119, Florida Statutes… the DBPR provides copies of electronic records to the public through free download." Files are ASCII quote/comma-delimited, refreshed weekly (per search summary). [LIVE disclaimer page](https://www2.myfloridalicense.com/?p=15875); weekly cadence [SEARCH]. The direct file-list page URL was not confirmed (the `instant-public-records` path returned no file links).
- **New York, "NYS Attorney Registrations"** (Socrata `eqw2-r5nb`):
  - Columns: Registration Number, First/Middle/Last Name, Suffix, Company Name, Street 1, Street 2, City, State, Zip, Zip Plus Four, Country, County, Phone Number, Year Admitted, Judicial Department of Admission, Law School, Status, Next Registration.
  - `rowsUpdatedAt` is about 2026-11-22. [LIVE](https://data.ny.gov/api/views/eqw2-r5nb.json)
- Medical boards: no free bulk physician file was confirmed this session. [Gap]

### Inferences
- **Linkage:**
  - A license gives a name plus a business address, sometimes home (sole-prop contractors often list home).
  - A license type is an income proxy (attorney, physician, general contractor).
  - CSLB bond and workers' comp fields show an active operating business; CSLB personnel links individuals to licensed entities.
  - A license number is a stable ID.
- **Legal:** most of these are public records with no use restriction on the face of the pages checked. Some states restrict commercial use of licensee lists or require a signed certification, e.g. some public-records statutes bar using lists for commercial solicitation. Check each state before ingesting. [UNVERIFIED]

### Gaps
- No state-by-state inventory of medical, real estate (e.g. TX TREC, FL DBPR real estate) or bar bulk files was built.
- Did not verify Florida's file URLs or layout.
- Did not check state-specific commercial-use bans (e.g. statutes barring use of public-records lists for solicitation).

## 5. FAA aircraft registry (Releasable Aircraft Database)

### Takeaway
A free daily ZIP of about 73 MB, with no login. MASTER.txt has about 319.5k registered aircraft with owner NAME, STREET, CITY, STATE, ZIP, registrant type, N-number, serial, year and Mode S. **Owners can request that their PII be withheld (49 USC 44114(b)).** The repo's schema already reserves `kind='aircraft'`.

### Cited Findings
- **Download:**
  - `https://registry.faa.gov/database/ReleasableAircraft.zip` returned HTTP 206 to a ranged GET: 73,166,663 bytes, Last-Modified Sat 21 Nov 2026 05:59 GMT. It needs a browser-like User-Agent; a HEAD with a custom UA got 403. [LIVE]
  - FAA page: "The data in the download is refreshed daily at 11:30 pm central time… Comma-Delimited text file (.txt extension) format". The archive contains the Master, Dealer, Document Index, Aircraft Reference, Deregistered, Engine and Reserved N-Number files. [LIVE](https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download)
- **Withholding:** "The FAA has established a procedure in accordance with 49 U.S.C. § 44114(b) by which private aircraft owners can request certain personally identifiable information, such as names and addresses, be withheld from broad dissemination or display on a publicly available FAA website." [LIVE](https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download)
- **Layout change:** the Document Index layout changed 30 July 2024 (Doc Type added). [LIVE](https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download)
- **ZIP contents** (sizes uncompressed): MASTER.txt 196 MB, DEREG.txt 278 MB, RESERVED.txt 24.7 MB, DEALER.txt 18.3 MB, ACFTREF.txt 14.9 MB, DOCINDEX.txt 2.9 MB, ENGINE.txt 0.2 MB. [LIVE]
- **MASTER.txt header:** `N-NUMBER, SERIAL NUMBER, MFR MDL CODE, ENG MFR MDL, YEAR MFR, TYPE REGISTRANT, NAME, STREET, STREET2, CITY, STATE, ZIP CODE, REGION, COUNTY, COUNTRY, LAST ACTION DATE, CERT ISSUE DATE, CERTIFICATION, TYPE AIRCRAFT, TYPE ENGINE, STATUS CODE, MODE S CODE, FRACT OWNER, AIR WORTH DATE, OTHER NAMES(1..5), EXPIRATION DATE, UNIQUE ID, KIT MFR, KIT MODEL, MODE S CODE HEX`. The file has a UTF-8 BOM and a trailing comma. 319,538 lines including header. [LIVE]

### Inferences
- **Linkage:**
  - Exact name plus street/ZIP to debtor addresses. TYPE REGISTRANT separates individual, partnership, corporation, co-owned and LLC.
  - OTHER NAMES(1..5) list co-owners.
  - Many aircraft are held in LLCs or Delaware trusts, so join through the SOS entity graph.
  - DEREG.txt gives ownership history, useful for transfer-before-judgment patterns.
  - ACFTREF gives make/model for value estimation.
- No use restriction appears on the download page beyond the PII-withholding procedure. A withheld record is not proof of non-ownership.

### Gaps
- Did not measure what share of MASTER records are PII-withheld.
- No aircraft valuation source (bluebook values are commercial).

## 6. Coast Guard vessels (NVDC, MVUS, PSIX) and state boat registrations

### Takeaway
Federal documented-vessel data is public, but **individual owner name and address were removed from the public MVUS bulk file in June 2017**. It now carries vessel particulars and "managing owner" identification. PSIX is a weekly FOIA snapshot with a search and XLSX export. Current owner records require NVDC abstracts of title (paid) or FOIA. The dco.uscg.mil and navcen.uscg.gov hosts blocked automated access from this session.

### Cited Findings
- **MVUS:**
  - The Coast Guard "Merchant Vessels of the United States" page publishes text, Excel and Access formats, with monthly ReadMe files (ReadMeVesdocJul2026, Aug2026, Sep2026 PDFs exist).
  - Per the search summary: "Effective June 12, 2017, in regards to Vessel Owner information, the following columns have been removed", including person name and address. Newer readmes describe "vessel particulars and managing owner identification".
  - Other documents require FOIA. [SEARCH](https://www.dco.uscg.mil/Our-Organization/Assistant-Commandant-for-Prevention-Policy-CG-5P/Inspections-Compliance-CG-5PC-/Office-of-Investigations-Casualty-Analysis/Merchant-Vessels-of-the-United-States/)
  - Fetching that page and the ReadMe PDF directly returned 403 (Akamai) to curl and a DNS failure to WebFetch. [LIVE probe failed]
- **PSIX:** "The information contained in PSIX represents a weekly snapshot of Freedom of Information Act (FOIA) data on U.S. flag vessels, foreign vessels operating in U.S. waters, and Coast Guard contacts with those vessels." Menu items: PSIX Vessel Search, Vessel Contact Search, PSIX XLSX Export. [LIVE](https://cgmix.uscg.mil/psix/) An XML web service exists. [SEARCH](https://cgmix.uscg.mil/XML/PSIXExportSearch.aspx)
- **NOAA Fisheries** mirrors vessel-by-name and vessel-by-ID lookups. Its caveats: it shows ownership only for craft with current Certificate of Documentation dates, and "we no longer are provided with the initial documentation issuance date for the current owner". The search summary says USCG no longer gives NOAA ownership data. [LIVE](https://www.st.nmfs.noaa.gov/st1/CoastGuard/VesselDataCaveats.html); [SEARCH](https://www.fisheries.noaa.gov/inport/item/20701)
- `https://www.navcen.uscg.gov/nvdc-data` returned 403/404. [LIVE probe failed]
- **Liens:** the repo already sees "VESSEL LIEN" filings in CT SOTS UCC data (`config/liens/ct.sots.liens.yaml`). [LIVE, local]

### Inferences
- **Linkage:** the managing owner (often an entity) plus vessel name, official number and hailing port. Individuals are mostly not linkable from bulk. PSIX may carry owner/operator names for commercial vessels, but this was not checked.
- **State boat registrations** (numbered, not documented, so most recreational boats): no free statewide bulk owner file was found. Many states treat registrant PII as confidential or sell it under restrictions. [UNVERIFIED]

### Gaps
- Could not open the latest MVUS ReadMe to list current columns (host blocked). The `www.dco.uscg.mil` and `www.navcen.uscg.gov` hosts would need to be reachable, or the work done from a browser.
- No state boat-registration bulk sources were verified.

## 7. USPTO patents, trademarks and assignments (ODP, PatentsView)

### Takeaway
USPTO bulk data has moved to the Open Data Portal (`data.uspto.gov` / `api.uspto.gov`). The legacy `bulkdata.uspto.gov` host no longer answers, and PatentsView now redirects to an ODP "transition guide". The ODP products API returned 401 without a key, so **a free API key is needed** for programmatic bulk listing. Assignment datasets (ownership transfers with assignor/assignee names and addresses) are the asset-relevant products.

### Cited Findings
- `https://patentsview.org/download/data-download-tables` redirects to `https://data.uspto.gov/support/transition-guide/patentsview`, which returned HTTP 200 (a JavaScript app shell, 12 KB). [LIVE]
- `https://data.uspto.gov/bulkdata` returned HTTP 200 (app shell). [LIVE]
- `https://bulkdata.uspto.gov/` gave no response (curl status 000, and 502 at the proxy on `/data/trademark/dailyxml/assignments/`). [LIVE probe]
- `https://api.uspto.gov/api/v1/datasets/products/search` and `/datasets/products/PASDL` returned `{"message":"Unauthorized"}` with HTTP 401. [LIVE]
- ODP product IDs such as PASDL (patent assignment), TRASDL/trademark assignment daily XML, patent grant full text and PatentsView tables are from prior knowledge. ODP API keys are free but require a USPTO.gov account with identity verification. [UNVERIFIED]
- Patent and trademark assignment records are public. USPTO data is generally US-government work in the public domain. [UNVERIFIED]

### Inferences
- **Linkage:**
  - Assignment records name the assignor and assignee (with addresses), the conveyance type (assignment, security agreement, release) and the execution date. Security agreements show IP pledged to lenders.
  - Trademark owner records give the entity name and address.
  - Best for entity debtors, matching on the normalized entity name plus the SOS ID chain.
  - For individuals, inventors are listed with city/state only, so matching is weak.
- IP is a collectable asset (it can be levied or assigned), but valuing it is hard.

### Gaps
- Could not read ODP product listings, sizes or cadences without a key. `data.uspto.gov` failed DNS in WebFetch; curl reached it, but the content is JavaScript-rendered.
- The ODP API-key terms were not verified.

## 8. Crypto wallets from public sources (OFAC SDN, ENS, court filings, self-published)

### Takeaway
**OFAC's SDN list is a free, authoritative, daily-updated source of about 1,080 digital-currency addresses tied to named sanctioned persons.** It is for screening only: **transacting with listed addresses is prohibited, and SDN attribution does not establish debtor ownership.** ENS reverse records link human-readable names to Ethereum addresses via a free subgraph or a BigQuery dataset. Attributing wallets to private debtors is deanonymization, with real legal and ethical risk.

### Cited Findings
- **SDN download:**
  - `https://www.treasury.gov/ofac/downloads/sdn.xml` redirects to Treasury's Sanctions List Service S3; the file was 29.6 MB, Last-Modified 20 Nov 2026.
  - It has 1,082 "Digital Currency Address" feature entries: XBT 534, TRX 273, ETH 124, USDT 94, LTC 14, XMR 11, BCH 7, DASH 5, ZEC 4, SOL 4, USDC 2, DOGE 2, plus single entries for XVG, XRP, ETC, BTG, BSV, BSC, BNB, ARB. [LIVE](https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML)
- **ENS:**
  - The ENS subgraph exposes domains with owner, resolver and an account→domains relation. [SEARCH](https://docs.ens.domains/web/subgraph)
  - ENS publishes a community dataset on Google BigQuery; the BigQuery free tier is 1 TiB of queries per month, with CSV export. [SEARCH](https://ens.domains/blog/post/google-bigquery-community-dataset)
  - Known subgraph limits: no ENSIP-10 effective resolver (wildcard), and offchain names are missing. [SEARCH](https://ensnode-1jazhfbf5-namehash.vercel.app/docs/integrate/ens-subgraph/key-limitations)
- Court filings (e.g. DOJ civil forfeiture complaints, bankruptcy schedules, divorce asset disclosures) sometimes list wallet addresses. There is no free bulk index of them; PACER is fee-based. [UNVERIFIED]
- Self-published addresses (social bios, donation pages, GitHub) can be collected only by scraping; there is no bulk source. [UNVERIFIED]

### Inferences
- **Linkage:**
  - SDN: the SDN entity name to a debtor name is a screening hit (and a compliance flag), not an asset to collect.
  - ENS: an ENS name such as `johnsmith.eth` is self-asserted and not tied to legal identity. Matching ENS names or text records (twitter, url, email) to a debtor is probabilistic and against the repo's "deterministic records graph" design. Keep any crypto link out of the deterministic graph, or mark it low-confidence.
- **Legal and ethical cautions:**
  - Mislabeling a wallet as a debtor's could cause unlawful or defamatory collection actions.
  - The FDCPA and CFPB Reg F limit third-party contacts and deceptive conduct.
  - State privacy laws (e.g. CCPA) may treat wallet-to-person inferences as personal information.
  - Interacting with SDN-listed addresses violates OFAC sanctions.
  - Any blockchain-analytics attribution beyond public, self-asserted records should be reviewed by counsel. [UNVERIFIED legal analysis]

### Gaps
- Did not fetch the ENS BigQuery dataset name or freshness.
- No free bulk source of court-filed wallet addresses was found.
