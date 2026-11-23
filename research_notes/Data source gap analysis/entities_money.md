# Entity and money/lender data gaps: free bulk sources

Research date: 2026-11-23. Scope: what the repo already loads (CT/OR/CO/NY entity registries via
`config/business/*.yaml` and `src/equity/adapters/business_registry.py`; CT UCC via
`config/liens/ct.sots.liens.yaml`; deterministic `name_key`/`org_name`/`addr_key` matching in
`src/equity/matching/resolve.py` and `orgs.py`), and what free bulk sources would fill the
remaining gaps. Builds on `docs/sources/business-registry-sources.md` (2026-11-21); this note only
adds, corrects or re-verifies.

Tags: **[LIVE]** = queried or downloaded from this sandbox on 2026-11-23 (headers, row counts,
sample rows). **[SEARCH]** = search-result snippets or official pages quoted by search, not
fetched. **[UNVERIFIED]** = background knowledge, not confirmed this session.

Network note: unlike earlier notes, `data.sba.gov`, `api.fdic.gov`, `cdr.ffiec.gov`, `ncua.gov`,
`api.usaspending.gov`, `files.usaspending.gov`, `api.gleif.org`, `goldencopy.gleif.org`,
`www.sec.gov`/`data.sec.gov`, `www.irs.gov`, `data.pa.gov`, `dos.fl.gov`, `sftp.floridados.gov`,
`yourmoney.ok.gov` and Socrata's catalog API were all reachable with curl. Hosts that refused curl
(bot walls/Cloudflare, HTTP 403): `sco.ca.gov`, `ttc.lacounty.gov`, `www.ffiec.gov/npw` (NIC),
`www.commerce.alaska.gov`, `www.ohiosos.gov`, `opencorporates.com/info/licence` (404). The
WebFetch tool could not resolve `sco.ca.gov` or `taxlien.io` (curl could reach taxlien.io).


**Priority list (free, bulk, loadable now):**

1. **SBA 7(a)/504 FOIA** — named borrowers + address + lender + `CHGOFF` with date and amount; quarterly; `data.sba.gov` reachable. [LIVE]
2. **PA `xvd7-5r2c` officers** — 4.2M rows, Public Domain, existing Socrata adapter. [LIVE]
3. **CO UCC full set** (filings, debtors, collateral, secured parties `ap62-sav4`). [LIVE]
4. **NY name-status history `ekwr-p59j`** — alias table for org matching. [LIVE]
5. **FL Sunbiz quarterly** — officers/managers for all FL entities; HTTPS host reachable, needs fixed-width parser. [LIVE page]
6. **Lender reference tables** — FDIC institutions/history/failures API, NCUA FOICU, SEC submissions (former names), GLEIF golden copy + ELF list. [LIVE]
7. **PPP FOIA** — `Charged Off` flags with borrower names; PII-heavy. [LIVE]
8. **WA L&I contractor principals** — owner names keyed to UBI. [LIVE]
9. **USAspending recipients** — UEI/name/address. [LIVE]
10. **Unclaimed property** — OK [LIVE], CA [SEARCH; host blocked]; asset signal only.
11. **Surplus lists** — county PDFs (FL, GA, CA, TX first); manual or per-county extractors.

---

## 1. Secretary of State entity records with members/managers/officers and registered agents

### Takeaway
The existing doc's picture holds: free, complete statewide bulk with person names exists only in
CT, DC, FL, PA (now verified), plus partial NY/OR/CO. New this session: **PA `xvd7-5r2c` is live
and has one row per officer (4.2M rows, Public Domain)**, FL's bulk host answers over HTTPS with
published public credentials, and two non-SOS stand-ins add owner names where the SOS sells data:
**WA L&I contractor principals** (with UBI, the WA SOS entity number) and **NY name-history**
(former names, for matching renamed LLCs). True LLC *member/manager* names remain rare: FL
(officer/manager slots), DC (beneficial owners), PA (party_type incl. Member/Manager is not
confirmed; sample showed President, Governor), CT (principals, undesignated).

### Cited Findings
**Pennsylvania (upgrade from unverified to verified)**
- [LIVE] `data.pa.gov/resource/xvd7-5r2c` "Registered Businesses in PA Current by County Department of State": license field "Public Domain U.S. Government"; **4,200,322 rows**; columns `business_name_source_, business_name, filing_number, address_line1/2, city, state, zip, typeofbusinessregistration, creationdate, party_type, last_name, middle_name, first_name, shortcountyname, county_code, georeferenced_latitude__longitude`. Sample rows: party_type "President" (ANNE Q KELLEY INC) and "Governor" (Align Technology). No status column and no registered-agent column. One row per (entity, party), so it fits the `role_datasets`/`grouped` patterns in `business_registry.py` keyed on `filing_number`. — [data.pa.gov xvd7-5r2c](https://data.pa.gov/Licenses-Certificates/Registered-Businesses-in-PA-Current-by-County-Depa/xvd7-5r2c)
- [UNVERIFIED] Whether `party_type` includes "Member"/"Manager"/"Organizer" for LLCs; a `select distinct party_type` query is the first load task.

**Florida Sunbiz**
- [LIVE] Data Downloads page: "free data downloads for informational purposes. Downloads are offered as is and may be changed, replaced or deleted at any time." Daily files on work days; quarterly files in January, April, July, October "contain all active data". Host `https://sftp.floridados.gov`, username `Public`, password published on the page; "available through your browser or a secure FTP client". The HTTPS host returned HTTP 200 (a JavaScript web file-manager UI), so the HTTPS path works through the proxy, but scripted download needs that UI's API or SFTP. Corporate data covers corporations, LLCs and LPs, not trademarks; fictitious-name data is a separate download. — [FL Data Downloads](https://dos.fl.gov/sunbiz/other-services/data-downloads/); [Quarterly Data](https://dos.fl.gov/sunbiz/other-services/data-downloads/quarterly-data/)
- [SEARCH, per existing doc] Up to 6 officers/managers with title and address, plus RA, per entity (fixed-width). — [Corporate Data File](https://dos.fl.gov/sunbiz/other-services/data-downloads/corporate-data-file/)

**New owner-name stand-ins found via Socrata catalog sweep**
- [LIVE] WA `data.wa.gov/4xk5-x9j6` "L&I Contractor License - Principal Data": ODC Public Domain (PDDL); **251,789 rows**; `businessname, contractorlicensenumber, contractorlicensetypecode(desc), businesstypecode(desc), ubi, principalname, startdate, enddate`. Principals of licensed contractors with start/end dates, keyed by UBI (the WA SOS entity number). Covers only contractor businesses, but WA has no free SOS bulk (extract retired). — [WA L&I principals](https://data.wa.gov/d/4xk5-x9j6)
- [LIVE] NY `data.ny.gov/ekwr-p59j` "Corporations and Other Entities: All Filings - Name Status History": **7,542,618 rows**; `corpid_num, film_num, date_filed, name_type, name_status, corp_name`. No license tag (NY Open Data terms). Gives every former and assumed name per DOS ID, so a judgment against "ABC REALTY LLC" can be matched to the entity now called something else. — [NY name status history](https://data.ny.gov/d/ekwr-p59j)
- [LIVE] DE `data.delaware.gov/5zy2-grhr` "Delaware Business Licenses": Public Domain; 74,465 rows; name, trade name, category, address, license number. No officers; DE SOS itself has no bulk product. — [DE business licenses](https://data.delaware.gov/d/5zy2-grhr)
- [LIVE] Also surfaced by the sweep: CO `casm-dbbj` (entity transaction history), CO `qpft-q492` (true name), OR `esjy-u4fc` (new businesses last month), TX `9cir-efmm` (active franchise taxpayers), NY `3gg2-jgnp`, `kiwr-v7e8`, `63wc-4exh`, `2tms-hftb` (already noted in the existing doc).

**Rechecked but not confirmed**
- [LIVE] `www.ohiosos.gov` business-report download and `www.commerce.alaska.gov` both returned HTTP 403 (bot wall) to curl. Ohio's free monthly reports stay unverified.
- [SEARCH] Alaska: no official bulk CSV found; only the one-record search and a paid vendor CSV (16,932 companies). — [AK Corporations](https://www.commerce.alaska.gov/web/cbpl/corporations); [companydata.com (vendor)](https://companydata.com/usa/alaska/)
- [LIVE] Vermont `bizfilings.vermont.gov/online/DatabrokerInquire/` returned 200, but no file links were in the static HTML (likely needs a login or a JS flow); still unconfirmed.

**Summary of member/manager coverage (free bulk)**

| State | Source | Person roles | RA | Status |
|---|---|---|---|---|
| CT | data.ct.gov ka36-64k6 (loaded) | principals (Officer/Director/undesignated) | yes | verified earlier |
| DC | DC GIS layer 2 Beneficial Owners | beneficial owners (~495k) | yes | verified earlier |
| FL | Sunbiz quarterly/daily | up to 6 officers/managers/members with titles | yes | page [LIVE], fields [SEARCH] |
| PA | data.pa.gov xvd7-5r2c | officers (President, Governor, ...) | no | [LIVE] |
| NY | n9v6-gdp6 (loaded) + 63wc-4exh | chair/CEO, filer/organizer | yes | verified earlier |
| OR | tckn-sxa6 (loaded) | authorized representative only | yes | verified earlier |
| CO | 4ykn-tg5h (loaded) | none | yes | verified earlier |
| WA | L&I 4xk5-x9j6 (contractors only) | principals with dates | no | [LIVE] |
| RI | weekly new-entity export | one officer | yes | unverified |

### Inferences
- PA and FL are the two highest-value entity loads still missing: both are large LLC-property states and both name people. PA loads with the existing Socrata adapter unchanged; FL needs a fixed-width parser and a non-Socrata fetcher.
- NY name history is a cheap, high-yield add for matching (not for new people): the `org_name` rule in `resolve.py` would miss renamed entities without it.

### Gaps
- PA `party_type` value list, and whether LLC members/managers are included.
- FL file layout and whether the HTTPS file-manager has a scriptable listing endpoint.
- Ohio, Vermont and Alaska bulk offerings could not be fetched (403 or JS).

---

## 2. UCC filings: free bulk from Secretary of State offices

### Takeaway
A Socrata-wide catalog sweep for "UCC", "financing statement" and "secured party" found **only CO,
CT and OR** state UCC data, confirming the earlier conclusion. One addition: **CO `ap62-sav4`
Secured Party Information (2.1M rows)** completes the CO set (filings + debtors + collateral +
secured parties). Everything else is paid or search-only.

### Cited Findings
- [LIVE] Socrata catalog results for "UCC": OR `2kf7-i54h` (secured parties), OR `snfi-f79b` (filings last month), CO `wffy-3uut` (filings), CO `8upq-58vz` (debtors), CO `4am6-w6u4` (collateral), CO `ap62-sav4` (secured parties), CO `ej2c-jkvh` and OR `3qaz-7u98` (farm-products effective financing statements), CT `xfev-8smz`. No other state appeared. — [Socrata catalog API](https://api.us.socrata.com/api/catalog/v1?q=UCC&only=dataset)
- [LIVE] CO `ap62-sav4`: Public Domain; **2,101,816 rows**; `spid, fileid, actiontypecode, actiontype, actionrefid, recordstatuscd, recordstatus, lastname, firstname, middlename, suffix, organizationname, address1, address2, city, state, country, zipcode, zipcode4, assignor`. Joins to `wffy-3uut` on `fileid`. Updated 2026-11-22. — [CO secured parties](https://data.colorado.gov/d/ap62-sav4)
- [LIVE] NYC ACRIS `q9kp-jvxv` is only a UCC collateral code table; NYC ACRIS UCC/fixture filings (county-recorded) are inside the ACRIS document datasets already covered by recorder notes.
- [SEARCH, existing doc] Paid UCC bulk: WI ($250/week), ID ($125/file), others; FL's Sunbiz downloads include a federal lien file (and the UCC registry is run by a private contractor in FL). — [FL Data Downloads](https://dos.fl.gov/sunbiz/other-services/data-downloads/)

### Inferences
- UCC debtor + secured-party pairs are the best free "who lends to this business" signal. CO UCC (debtors 2.0M + secured parties 2.1M) should be loaded with the same party model as `ct.sots.liens.yaml`; OR `snfi-f79b` is only a rolling month, so it must be pulled monthly to accumulate.
- CO `ej2c-jkvh` (farm products) is low value for real-property equity.

### Gaps
- No free UCC bulk found in any other state; FOIA/public-records requests would be the only route (e.g., the MuckRock DE request cited in the existing doc).

---

## 3. Owner-name cleanup and entity matching: free reference data and practice

### Takeaway
Four free, bulk, scriptable reference sets help deterministic matching: **GLEIF** (3.5M LEIs, 366k
US, each with the state registry file number and registry code, CC0), **GLEIF ISO 20275 ELF code
list** (legal-form suffixes per jurisdiction), **SEC EDGAR submissions** (names with *former
names* and addresses), **IRS EO BMF** (every tax-exempt org with EIN and address), and the **FDIC
BankFind institutions/history** API (bank names plus merger successor chains, to collapse lender
names on mortgages and UCCs). OpenCorporates is ODbL share-alike; free only for open-data
projects, bulk is paid or discretionary.

### Cited Findings
**GLEIF**
- [LIVE] Golden Copy "latest" publish 2026-11-23: LEI2 CSV full file **3,502,737 records, 487 MB zipped**; JSON 1.05 GB; files under `goldencopy.gleif.org/storage/golden-copy-files/...`; publishes several times a day with delta files. — [GLEIF golden copy API](https://goldencopy.gleif.org/api/v2/golden-copies/publishes/latest)
- [LIVE] API `filter[entity.legalAddress.country]=US` returns **366,012** records. Sample: "VREP III MAGNUS HOLDINGS II LLC", `registeredAs` 10819910, `registeredAt` RA000602 (the Delaware Division of Corporations registry code), `legalForm` HZEH, `jurisdiction` US-DE. A `region` filter is not allowed by the API ("Filter should contain only allowed values"). — [GLEIF API](https://api.gleif.org/api/v1/lei-records?filter%5Bentity.legalAddress.country%5D=US&page%5Bsize%5D=1)
- [UNVERIFIED] GLEIF data is CC0 (no restrictions).
- [LIVE] ISO 20275 Entity Legal Forms code list v1.6 (2026-02-19), CSV and XLSX: lists legal-form names and abbreviations per jurisdiction (incl. US states). — [ELF code list page](https://www.gleif.org/en/about-lei/code-lists/iso-20275-entity-legal-forms-code-list); [CSV](https://www.gleif.org/lei-data/code-lists/iso-20275-entity-legal-forms-code-list/2026-02-19-elf-code-list-v1.6.csv)

**SEC EDGAR**
- [LIVE] `company_tickers.json` (≈796 KB) downloads with a declared User-Agent; `submissions.zip` bulk (**1.58 GB**, last-modified 2026-11-21) is the nightly archive of all filer submissions JSON. — [SEC company tickers](https://www.sec.gov/files/company_tickers.json); [submissions.zip](https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip)
- [LIVE] Per-filer JSON carries `formerNames` with date ranges and business/mailing addresses, e.g. CIK 72971: "WELLS FARGO & COMPANY/MN", former "WELLS FARGO & CO/MN" (1998–2012) and "NORWEST CORP" (1994–1998), business address 333 MARKET STREET, SAN FRANCISCO, CA 94105. — [data.sec.gov submissions](https://data.sec.gov/submissions/CIK0000072971.json)
- [UNVERIFIED] SEC fair-access policy: declare a User-Agent with contact, ≤10 requests/second. Note the `/MN`-style state suffixes need stripping before name matching.

**IRS EO BMF**
- [LIVE] Per-state CSVs (e.g. `eo_ct.csv`) with `EIN, NAME, ICO (in-care-of), STREET, CITY, STATE, ZIP, GROUP, SUBSECTION, ..., STATUS, TAX_PERIOD, ASSET_AMT, INCOME_AMT, REVENUE_AMT, NTEE_CD, SORT_NAME`. One file per state, DC, PR and international; sorted by EIN; state = filing address of HQ. — [IRS EO BMF extract](https://www.irs.gov/charities-non-profits/exempt-organizations-business-master-file-extract-eo-bmf); [eo_ct.csv](https://www.irs.gov/pub/irs-soi/eo_ct.csv)
- [UNVERIFIED] Updated monthly; public domain (US government work).

**FDIC BankFind (lender name normalization)**
- [LIVE] `api.fdic.gov/banks/institutions`: 4,206 active institutions with `NAME, CERT, FED_RSSD, CITY, STALP`; index refreshed 2026-11-20. No key required. — [FDIC institutions API](https://api.fdic.gov/banks/institutions?filters=ACTIVE:1&limit=1)
- [LIVE] `api.fdic.gov/banks/history` with `CHANGECODE:223` (Merger - Without Assistance) returns 222 events since 2025-01-01 with `OUT_INSTNAME` → `SUR_INSTNAME`/`SUR_CERT` (e.g. Piggott State Bank → Farmers Bank and Trust Company, 2025-01-01). — [FDIC history API](https://api.fdic.gov/banks/history?filters=CHANGECODE:223&limit=1)
- [LIVE] `api.fdic.gov/banks/failures`: 4,117 failures with name, cert, date (latest SMALL BUSINESS BANK, 7/17/2026). — [FDIC failures API](https://api.fdic.gov/banks/failures?limit=1)
- [LIVE] SBA 7(a) rows carry `BankFDICNumber` and `BankNCUANumber`, and NCUA call-report `FOICU.txt` carries `CU_NUMBER`, `CU_NAME`, `STREET`, `CITY`, `STATE`, `ZIP_CODE`, `RSSD`, so lender names can be keyed to FDIC CERT / NCUA charter / RSSD (see sections 4–6).
- [LIVE] FFIEC NIC (`www.ffiec.gov/npw`, bank holding company structure and transformations) returned HTTP 403 to curl.

**OpenCorporates**
- [SEARCH] Data under ODbL (attribution + share-alike on derived data); free "share-alike" API keys only for eligible open-data users who show evidence of public use; paid non-share-alike terms otherwise; bulk delivered by SFTP per jurisdiction, "we can usually provide... at no cost" for open projects (discretionary); one pricing tier cited at £1,200/month. — [OpenCorporates API reference](https://api.opencorporates.com/documentation/API-Reference); [Pricing](https://opencorporates.com/pricing/); [Self-serve API terms](https://opencorporates.com/legal-information/self-service-api-terms-of-service/)
- [LIVE] `opencorporates.com/info/licence` returned 404 (page moved).

**Address standardization reference**
- [LIVE] USPS Publication 28 (street suffix and unit designator tables, appendix C) is reachable. — [USPS Pub 28 appendix C2](https://pe.usps.com/text/pub28/28apc_002.htm)

**Deterministic-matching practice (what the repo does vs. gaps)**
- [Repo] `orgs.py` strips a fixed list of entity-form suffixes (LLC, INC, CORP, CO, LTD, LP, PC, PA, NA, ...) and classifies by org words; `resolve.py` matches on exact `org_name` + address/ZIP/county and person `name_key` (sorted word set, ≥2 words) + address/ZIP. — `src/equity/matching/orgs.py`, `src/equity/matching/resolve.py`
- [Inference] Free reference data maps onto concrete deterministic rules: (a) ELF list → extend `_FORMS` with state-specific forms (e.g. "L L C", "LIMITED LIABILITY CO", "PROFESSIONAL CORPORATION", "SERIES LLC"); (b) NY name history, SEC `formerNames`, FDIC history → alias tables (old name → current entity key) applied before the `org_name` join, each alias keeping its source and date range so every match can be re-derived; (c) registry IDs (NY DOS ID, PA filing_number, CT id, GLEIF `registeredAs`) → an `entity_id` key so two org names that resolve to the same registry record match exactly; (d) FDIC CERT / NCUA CU_NUMBER / RSSD → a canonical lender key for mortgage and UCC secured parties; (e) USPS Pub 28 → suffix/unit normalization inside `addr_key`; (f) strip "DBA", "FKA", "AKA", "C/O", "/MN"-style suffixes into separate alias rows rather than deleting them.

### Inferences
- GLEIF's `registeredAs`/`registeredAt` pair is the only free cross-state bridge from an entity name to a specific SOS file number (mostly for larger, financial-market entities: 366k US LEIs vs. tens of millions of US entities), so it helps most on lender/servicer/investor names, not small LLC landlords.
- FDIC history + SEC former names directly fix a common mortgage-satisfaction problem: assignments and releases recorded by successor banks (e.g. NORWEST → WELLS FARGO).

### Gaps
- GLEIF license (CC0) and EO BMF update cadence not confirmed this session.
- No free bulk source of DBA/assumed names was found beyond NY name history and FL fictitious-name files.

---

## 4. Bank charge-offs: FFIEC Call Reports (CDR) and FDIC BankFind

### Takeaway
Free and bulk, but **only aggregate per bank per quarter** (gross charge-offs, recoveries, net, by
loan category). There is no borrower- or loan-level charge-off data. Useful only as lender context
(e.g. flagging lenders with high real-estate charge-off rates) and for lender name/ID tables, not
for finding debtors.

### Cited Findings
- [LIVE] FFIEC CDR Bulk Data Download page: products "Call Reports -- Single Period", "Call Reports -- Balance Sheet, Income Statement, Past Due -- Four Periods", UBPR Ratio/Rank/Stats; "for All Commercial Banks"; "Call Updated: 11/14/2026, UBPR Updated: 11/15/2026"; Excel-compatible (tab-delimited) or XBRL; no login for bulk download. — [FFIEC CDR Bulk Data](https://cdr.ffiec.gov/public/PWS/DownloadBulkData.aspx)
- [UNVERIFIED] Charge-offs are in Call Report Schedule RI-B Part I (charge-offs and recoveries by loan category, e.g. RIAD4635 total charge-offs, RIAD4605 total recoveries; separate lines for construction, farmland, 1–4 family, multifamily, nonfarm nonresidential real estate). Quarterly, year-to-date amounts in thousands.
- [LIVE] FDIC BankFind `financials` API returns per-quarter fields including `DRLNLS` (gross loan and lease charge-offs), `CRLNLS` (recoveries), `NTLNLS` (net charge-offs), `NTRE` (net charge-offs, real estate), `NTRERES` (1–4 family residential), `NTCI` (C&I), `NCLNLS`, `P9ASSET` (90+ days past due); e.g. Wells Fargo Bank NA (CERT 3511) 2026-06-30: DRLNLS 2,660,000, CRLNLS 683,000, NTLNLS 1,977,000 (thousands); 170 quarterly records for that bank; index built 2026-11-16. No API key needed. — [FDIC financials API](https://api.fdic.gov/banks/financials?filters=CERT:3511&fields=CERT,REPDTE,NAME,NTLNLS,DRLNLS,CRLNLS,NTRE&limit=2)
- [UNVERIFIED] Field definitions above follow FDIC's RIS data dictionary; confirm against the `financials` definitions file before using them.

### Inferences
- Low usefulness for the debtor→parcel graph. The practical use is building a `lender` dimension (CERT, RSSD, name, history, failure date) and attaching quarterly RE charge-off and past-due rates as context. Failed-bank records (4,117) matter more: mortgages held by failed banks are often assigned to the FDIC or an acquirer, which affects mortgage-open/paid status in `mortgage_status.parquet`.

### Gaps
- No public loan-level bank charge-off data exists (it is confidential supervisory/borrower data). [UNVERIFIED but consistent with all sources seen]

---

## 5. Credit union charge-offs: NCUA 5300 call report quarterly data

### Takeaway
Free quarterly ZIPs, aggregate per credit union only. Contains charge-off totals by loan category
and a credit-union master file (name, address, RSSD), useful as a lender table for credit-union
mortgages and SBA loans (`BankNCUANumber`).

### Cited Findings
- [LIVE] Quarterly ZIPs listed on the NCUA page, e.g. `call-report-data-2026-06.zip` (last-modified 2026-09-14), back through 2024 and earlier. — [NCUA Quarterly Data](https://ncua.gov/analysis/credit-union-corporate-call-report-data/quarterly-data)
- [LIVE] The 2026-06 ZIP contains `FOICU.txt` (master: `CU_NUMBER, CYCLE_DATE, JOIN_NUMBER, RSSD, CU_TYPE, CU_NAME, CITY, STATE, ..., ZIP_CODE, COUNTY_CODE, ..., STREET, ..., YEAR_OPENED, ..., INSURED_DATE`), `FS220.txt` through `FS220S.txt` (account values), `AcctDesc.txt` (account dictionary), `Credit Union Branch Information.txt`, `ATM Locations.txt`, `TradeNames.txt`, `Readme.txt`.
- [LIVE] `AcctDesc.txt` charge-off accounts include `Acct_550` "Total Amount of All Loans Charged Off Year-to-Date" (FS220), `Acct_548` first-mortgage charge-offs YTD, `Acct_549` other real estate charge-offs YTD, `Acct_550G1` member business loans secured by real estate charge-offs YTD, `Acct_550G3` member commercial loans secured by RE charged off YTD, `Acct_550C1/C2` new/used vehicle, `Acct_136` PAL loans.

### Inferences
- Same usefulness as section 4: lender context and a name/ID table (`TradeNames.txt` helps map credit-union trade names seen on mortgages back to the charter). No member-level data.

### Gaps
- NCUA data license/terms text not checked (US government work, presumably public domain) [UNVERIFIED].

---

## 6. SBA 7(a)/504 and PPP loan-level data (data.sba.gov)

### Takeaway
**The strongest free money source in this note.** Loan-level, named borrowers with street
addresses, lender names with FDIC/NCUA IDs, and an explicit charge-off status, date and gross
charge-off amount for 7(a) and 504; PPP has borrower name/address and a "Charged Off" status (no
charge-off amount). All are free CSV downloads, no login. data.sba.gov is now a Drupal site (the
old CKAN API returns "Page not found").

### Cited Findings
**7(a) and 504 FOIA**
- [LIVE] Dataset page lists: `FOIA_7a_FY1991_FY1999`, `FOIA_7a_FY2000_FY2009`, `FOIA_7a_FY2010_FY2019`, `FOIA_7a_FY2020_Present`, `FOIA_504_FY1991_FY2009`, `FOIA_504_FY2010_Present`, all `_asof_260930.csv`, plus `7a_504_foia_data_dictionary.xlsx`. — [SBA 7(a) & 504 FOIA](https://data.sba.gov/dataset/7a-504-foia)
- [LIVE] 7(a) header: `AsOfDate, Program, LocationID, BorrName, BorrStreet, BorrCity, BorrState, BorrZip, BankName, BankFDICNumber, BankNCUANumber, BankStreet, BankCity, BankState, BankZip, GrossApproval, SBAGuaranteedApproval, ApprovalDate, ApprovalFY, FirstDisbursementDate, ProcessingMethod, InitialInterestRate, FixedorVariableInterestInd, TermInMonths, NaicsCode, NaicsDescription, FranchiseCode, FranchiseName, ProjectCounty, ProjectState, SBADistrictOffice, CongressionalDistrict, BusinessType, BusinessAge, LoanStatus, PaidInFullDate, ChargeOffDate, GrossChargeOffAmount, RevolverStatus, JobsSupported, CollateralInd, SoldSecMrktInd`. FY2020–present file is 188 MB, last-modified 2026-10-30. — [FOIA_7a_FY2020_Present](https://data.sba.gov/sites/default/files/uploaded_resources/FOIA_7a_FY2020_Present_asof_260930.csv)
- [LIVE] 504 header: `... BorrName, BorrStreet, BorrCity, BorrState, BorrZip, CDC_Name, CDC_Street, CDC_City, CDC_State, CDC_Zip, ThirdPartyLender_Name, ThirdPartyLender_City, ThirdPartyLender_State, ThirdPartyDollars, GrossApproval, ..., ProjectCounty, ProjectState, ..., BusinessType, BusinessAge, LoanStatus, PaidInFullDate, ChargeOffDate, GrossChargeOffAmount, JobsSupported, CollateralInd`. FY2010–present file 60 MB. Sample borrower "70 West Main Street Realty Corp", 68-70 West Main Street, Patchogue NY, third-party lender Manufacturers and Traders Trust Company. — [FOIA_504_FY2010_Present](https://data.sba.gov/sites/default/files/uploaded_resources/FOIA_504_FY2010_Present_asof_260930.csv)
- [LIVE] `LoanStatus` values in a 427-row sample of the FY2010–2019 7(a) file: `P I F` 337, `CANCLD` 49, **`CHGOFF` 38**, `EXEMPT` 3 (the 2020+ file also shows `EXEMPT` for active loans). Quarterly refresh (as-of 2026-09-30, posted 2026-10-30).
- [Inference from fields] 504 loans finance real estate and equipment, so 504 borrowers are often the property-owning entity (or its operating affiliate) at the project address; `CollateralInd` flags secured 7(a) loans.

**PPP FOIA**
- [LIVE] Dataset page lists `public_150k_plus_240930.csv` (452 MB) and `public_up_to_150k_1..12_240930.csv`, plus `ppp-data-dictionary.xlsx`; data as of 2024-09-30 (file last-modified 2026-06-26). — [SBA PPP FOIA](https://data.sba.gov/dataset/ppp-foia)
- [LIVE] PPP header: `LoanNumber, DateApproved, SBAOfficeCode, ProcessingMethod, BorrowerName, BorrowerAddress, BorrowerCity, BorrowerState, BorrowerZip, LoanStatusDate, LoanStatus, Term, SBAGuarantyPercentage, InitialApprovalAmount, CurrentApprovalAmount, UndisbursedAmount, FranchiseName, ServicingLenderLocationID, ServicingLenderName, ServicingLenderAddress/City/State/Zip, RuralUrbanIndicator, HubzoneIndicator, LMIIndicator, BusinessAgeDescription, ProjectCity, ProjectCountyName, ProjectState, ProjectZip, CD, JobsReported, NAICSCode, Race, Ethnicity, *_PROCEED (utilities, payroll, mortgage interest, rent, refinance EIDL, health care, debt interest), BusinessType, OriginatingLenderLocationID, OriginatingLender, OriginatingLenderCity/State, Gender, Veteran, NonProfit, ForgivenessAmount, ForgivenessDate`.
- [LIVE] `LoanStatus` in a 6,664-row sample of the up-to-150k file: `Paid in Full` 6,601, **`Charged Off` 36**, `Exemption 4` 27. No charge-off amount or date field (`LoanStatusDate` is the date of the status). Many small PPP borrowers are sole proprietors, so `BorrowerName` is often a person's name with a home address.
- [SEARCH, earlier note] The sba.gov PPP page was last updated 2025-03-07. — [SBA PPP data](https://www.sba.gov/programas-de-financiamiento/prestamos/opciones-de-asistencia-por-covid-19/programa-de-proteccion-de-pago/datos-del-ppp)

### Inferences
- `CHGOFF` 7(a)/504 rows are a ready-made "business owes a large defaulted federal-guaranteed loan" list with names, addresses and amounts, matchable with the existing `org_name_address`/`org_name_zip` rules. A charge-off is not a judgment or lien, so it should enter as its own debt kind (e.g. `charged_off_loan`) in `config/debt_kinds.yaml`, not as a judgment.
- PPP `Charged Off` is a weaker signal (no amount; many were small, forgiven-in-part, or fraud cases) and contains many personal names; treat as PII like other `pii_fields`.
- 7(a) `BankFDICNumber`/`BankNCUANumber` let lender names join to FDIC/NCUA tables (sections 3–5).
- COVID EIDL loans are not in these files (see section 7).

### Gaps
- Data dictionary XLSX not opened; meanings of `EXEMPT` (likely active loans withheld under FOIA exemption 4) and `CANCLD` not confirmed.
- No SBA terms-of-use text was checked (US government data, presumably public domain) [UNVERIFIED].

---

## 7. Federal contracts and grants: USAspending API and bulk

### Takeaway
Free, no-key API and monthly bulk ZIP archives with recipient legal name, UEI, parent UEI and full
recipient address. It identifies businesses receiving federal money (an asset/income signal, and a
UEI-to-name-to-address link), not debts.

### Cited Findings
- [LIVE] `POST api.usaspending.gov/api/v2/search/spending_by_award/` returns per-award `Recipient Name`, `Recipient UEI`, `Award Amount`, and a full `Recipient Location` (address lines, city, county, state, ZIP5, ZIP4, congressional district), e.g. HAMILTON SUNDSTRAND CORPORATION, UEI JC42EBJ5NFJ1, 1 HAMILTON RD, WINDSOR LOCKS CT 06096. The API notes search is limited to dates from 2007-10-01; older data (from 2000-10-01) via download endpoints. — [USAspending API endpoints](https://api.usaspending.gov/docs/endpoints)
- [LIVE] `POST /api/v2/bulk_download/list_monthly_files/` lists award archives, e.g. `FY2026_All_Contracts_Full_20261106.zip` and `FY(All)_All_Contracts_Delta_20261106.zip` at `files.usaspending.gov/award_data_archive/`. Archives are monthly full + delta files by fiscal year and type (contracts, assistance). — [USAspending award data archive](https://files.usaspending.gov/award_data_archive/FY2026_All_Contracts_Full_20261106.zip)
- [UNVERIFIED] Assistance archives (grants, direct loans, insurance) include SBA disaster/EIDL direct loans at record level, with individual recipients' names redacted ("REDACTED DUE TO PII") and aggregated; business recipients are named. Data is public domain; no key required.

### Inferences
- Use: a `recipient` table (UEI, legal name, parent, address) to give the matcher another authoritative name+address for business debtors, and to flag judgment debtors who receive federal contracts (a source of garnishable receivables). Medium priority; the files are large (full contract archives are multi-GB per year) so filter by recipient state.
- If EIDL direct loans are named for businesses, that would add a large population of federal debtors (EIDL loans are 30-year federal debts), but repayment/charge-off status is not in USAspending.

### Gaps
- Exact column list of the assistance archive and whether EIDL loan records include business names/addresses was not confirmed this session.

---

## 8. State unclaimed property: bulk lists

### Takeaway
Most states are search-only (and several bar bulk use). **Free full-database downloads confirmed:
Oklahoma [LIVE] and California [SEARCH]**. New York provides a quarterly owner-name file on request
(delivered by secure FTP). Texas requires an emailed request. Illinois refuses bulk. Unclaimed
property is money *owed to* the named person, so it is an asset signal, not a debt.

### Cited Findings
- [LIVE] **Oklahoma** "Oklahoma Unclaimed Property Data Portal" (Angular app at yourmoney.ok.gov): "records available in the Treasurer's Unclaimed Property database. The records will download in a CSV format ... larger than 2 GB ... The Oklahoma Unclaimed Property Division does not provide technical support ... The files will be updated annually." Two files: `RegularFinderFile_20261029.csv` (**472.6 MB**, last-modified 2026-10-29) and `InsuranceFinderFile_20261029.csv`, under `https://yourmoney.ok.gov/upd-property-records/`. Header: `PropertyID, PropertyTypeCD, OwnerRelationshipTypeCode, OwnerName, OwnerAddress1-3, OwnerCity, OwnerState, OwnerZipCode, RemainingCash, StartTransactionDT, EndTransactionDT, ReportYear, ReportReceivedDT, HolderName, HolderAddress1-3, HolderCity, HolderState, HolderZipCode, RemainingShares, Symbol, CUSIP`. Names are "LAST FIRST" with a leading space. — [OK Data Portal](https://yourmoney.ok.gov/app/Oklahoma-Unclaimed-Property-Data-Portal)
- [SEARCH] **California** SCO: "download all of the unclaimed property records in the Controller's public database in .CSV format", files updated every Thursday; separate Estates of Deceased Persons file (Excel) refreshed April and October. sco.ca.gov blocks curl (Cloudflare challenge). — [CA Download Unclaimed Property Records](https://sco.ca.gov/upd_download_property_records.html); [CA Estates file](https://www.sco.ca.gov/upd_estates_investigator.html)
- [SEARCH] **New York** OSC: owner-name file by request form; link to a secure FTP site emailed; zipped delimited text; updated quarterly; may be retrieved as often as wanted. — [NY Owner Name File Request Form](https://www.osc.ny.gov/unclaimed-funds/resources/owner-name-file-request-form); [NY Location Service Providers](https://www.osc.ny.gov/unclaimed-funds/resources/location-service-providers)
- [LIVE] **Texas** data.texas.gov `3un9-h9it` "Texas Unclaimed Property Listing" is a placeholder: "please send a request to up.dbrequests@cpa.texas.gov" with name, company, mailing address, phone and PI license number (if applicable). Last updated 2017. — [TX listing](https://data.texas.gov/d/3un9-h9it)
- [SEARCH] **Illinois**: the Treasurer does not provide bulk data files, exports or API access; its database is exempt from disclosure; finders must be licensed. — [IL finder FAQ](https://www.illinoistreasurer.gov/?p=11602)
- [LIVE] **Rhode Island** Treasury CKAN, Unclaimed Property org: 14 datasets, all 2015 public-records (APRA) responses (PDF/XLS), including "Property Tax Excess Funds" and "Overages from foreclosures and tax sales" (PDF). Stale. — [RI Treasury open data](https://data.treasury.ri.gov/organization/about/unclaimed-p)
- [SEARCH] Ohio licenses finders who can use the unclaimed-funds database; no data-file fee found. — [Ohio Finder Agreement Procedure](https://dam.assets.ohio.gov/image/upload/com.ohio.gov/UNFD/Finders/Finder_Agreement_Procedure.pdf)
- [LIVE] City-level Socrata sets: Providence RI `4hhd-fzq6` (payee name/address/amount, updated 2026-11-16), Austin TX `h3i4-5e5v` (first/last name), Ramsey County MN `t2fe-qrnd` "Missing Heirs" (estate, heir, amount). — [Socrata catalog](https://api.us.socrata.com/api/catalog/v1?q=unclaimed%20property&only=dataset)

### Inferences
- OK (now) and CA (after allowing `sco.ca.gov`, which needs a browser-like client or manual download) are loadable as `owed_to` party records. For the equity product, unclaimed property is mostly useful as identity confirmation (name + historic address) and as a "money owed to debtor" flag; it does not create debts.
- Terms: OK's page disclaims support but sets no use restriction in the text seen; CA's terms were not readable here.

### Gaps
- No complete 50-state survey was possible in this budget; states other than OK, CA, NY, TX, IL, RI, OH are unchecked (most are believed search-only via MissingMoney.com) [UNVERIFIED].
- CA file field list and terms (host blocked).

---

## 9. Surplus funds from tax and foreclosure sales (excess proceeds lists)

### Takeaway
Published county by county, almost always as **PDF** (sometimes Excel), with no statewide bulk
file in the states checked. Lists name the former owner, parcel/case number, sale date and surplus
amount — money owed *to* the former owner (or to junior lienholders, who can claim it). Best
coverage is FL (clerks, Fla. Stat. 197.582), GA (tax commissioners, O.C.G.A. 48-4-5), CA (county
tax collectors, RTC 4675), TX (district clerks, Tax Code 34.03–34.04), PA tax claim bureaus, OH,
NY (RPTL 1197), NV.

### Cited Findings
- [LIVE] taxlien.io index of official county surplus pages (59 lists, 15 states per the search snippet). Counties and statutes it links, by state: CA (LA, Fresno, Imperial, Madera, Orange, Sacramento, San Diego, San Joaquin; RTC 4675), FL (Brevard, Citrus, Hillsborough, Lee, Manatee, Marion, Okaloosa, Osceola, Pasco, Polk, Sarasota, Pinellas `clerk.org` PDF; Fla. Stat. 197.582), GA (Athens-Clarke, Chatham, Clayton, DeKalb, Douglas, Forsyth, Gwinnett, Hall, Henry, Rockdale; O.C.G.A. 48-4-5), MS (Rankin; 27-41-77), NV (Clark, Washoe; NRS 361.610), NY (Chemung, Erie; RPTL 1197), OH (Hamilton `courtclerk.org`, Lucas, Montgomery; R.C. 5721.20), OK (Tulsa; 68 O.S. 3131), PA (Bucks, Butler, Cumberland, Erie, Lehigh, Luzerne, Wayne), SC (Oconee, York; 12-51-130), TN (Davidson; 67-5-2702), TX (Denton, Hockley, Tom Green, Wise; Tax Code 34.03/34.04), UT (Utah County; 59-2-1351.1), WA (RCW 84.64.080), MO (Clay), AR (26-37-205). Third-party index; links point to official pages. — [taxlien.io county lists](https://taxlien.io/surplus-funds/county-lists/)
- [LIVE] Gwinnett County GA: `excess-funds-all-years` is a 1-page **PDF** (118 KB); claim packet separate. — [Gwinnett Tax Sale Excess Funds](https://www.gwinnetttaxcommissioner.com/property-tax/tax-sale-excess-funds)
- [SEARCH] Gwinnett pays excess funds only to the record owner or a lienholder with an interest at the time of sale. — [Gwinnett](https://www.gwinnetttaxcommissioner.com/property-tax/tax-sale-excess-funds)
- [LIVE] DeKalb County GA: `Excess-Funds-List.pdf` linked from the delinquent-taxes page. — [DeKalb delinquent taxes](https://dekalbtaxga.gov/property-tax/delinquent-taxes/)
- [LIVE] Wise County TX: monthly "SEPTEMBER-2026-EXCESS-PROCEEDS-REPORT-PDF" in the DocumentCenter. — [Wise County Excess Proceeds](https://www.co.wise.tx.us/453/Excess-Proceeds)
- [LIVE] Erie County NY: surplus funds are a web search (by street number/name) on `www2.erie.gov/surplusfunds`; the ZIPs on the page (`citynew.zip`, `countynew.zip`, `mortgage.zip`) contain claim forms (PDF), not lists. — [Erie County Surplus Funds](https://www4.erie.gov/surplusfunds/)
- [LIVE] Hillsborough FL `/taxdeeds`, Pasco FL `Tax-Deed-Surplus`, Clark NV `excess-proceeds`, San Diego `excess-proceeds`, Lucas OH `excess-funds`, Harris TX District Clerk `ExcessFunds.aspx` pages returned HTTP 200, but the static HTML showed only claim forms/affidavits (lists are in JS widgets, separate pages, or a search). LA County TTC returned 403.
- [SEARCH] Vendor guidance: lists are "typically" PDF or spreadsheets; search terms vary ("excess funds", "excess proceeds", "overages", "surplus funds"); vendors (LienSuite $27/county; Tax Sale Results) resell compiled lists. — [LienSuite guide](https://liensuite.com/tools/surplus-funds-guide); [Tax Sale Results](https://taxsaleresults.com/surplus-funds-list/)
- [LIVE] Socrata catalog: no county surplus/excess-proceeds dataset found on any Socrata portal (queries "excess proceeds", "surplus funds", "tax deed surplus", "overbid"). RI Treasury has 2015 PDF APRA responses for "Property Tax Excess Funds" and "Overages from foreclosures and tax sales". — [RI Treasury open data](https://data.treasury.ri.gov/organization/about/unclaimed-p)
- [UNVERIFIED] *Tyler v. Hennepin County* (U.S. Supreme Court, 2023) held that keeping surplus equity from tax foreclosure is a taking, pushing states such as MI, MN, NE and others to create surplus-claim processes and owner notices; Michigan county treasurers publish post-foreclosure surplus notices under MCL 211.78t.

### Inferences
- Surplus lists are small per county but high-signal: each row ties a named former owner to a specific parcel and an amount of *their* equity that was converted to cash. For the graph they belong as a parcel-level event ("tax_sale_surplus"), and the junior lienholders on that parcel (judgment creditors) are the parties with claims against the surplus.
- Loading needs a PDF table extractor per county; start with counties that publish Excel/CSV or stable PDF layouts. FL clerks (statewide statutory duty, many counties) and GA metro counties are the densest sets.

### Gaps
- Per-county format (PDF vs Excel), field lists and update cadence were confirmed only for Gwinnett, DeKalb, Wise and Erie. LA County and other CA counties not reachable.
- No statewide surplus bulk file found in any state.

