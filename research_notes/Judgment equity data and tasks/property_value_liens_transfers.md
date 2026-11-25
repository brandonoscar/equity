# Property ownership, value, senior liens and transfers: free US sources (2026)

Research date 2026-11-25. Scope: free, lawful, no-login bulk or API sources. This note **builds on and does not repeat** the repo's existing work. Read these first, they are the baseline:
- `docs/sources/recorder-sources.md` (state-by-state recorded-instrument sources, federal mortgage files, the amortization method, load-first list)
- `reports/Recorder data records laws by state.md` (51-jurisdiction public-records/recorder fee ranking, residency blockers, commercial-purpose rules for WA, AZ, IL, OH, SC, KS)
- `docs/sources/business-registry-sources.md` (entity registries with officers/agents by state)
- `docs/gaps.md` (what is loaded: parcels in 51 jurisdictions, 31 statewide; deeds/mortgages loaded only in FL, IL, IN, MD, NY, PA)

Verification legend: **Verified** = fetched from the official host in this session (curl), file or API read directly. **Search** = from search-engine excerpts of the cited page; the page itself was not opened. **Background** = prior knowledge, not checked this session.

Hosts that failed from this session (WebFetch DNS refusal or proxy): `ffiec.cfpb.gov`, `www.zillow.com` (403 to curl, DNS refusal to WebFetch). Reachable by curl this session, unlike the earlier recorder-sources pass: `opendata.maryland.gov`, `www.fhfa.gov`, `tax.vermont.gov` and its blob store, `info.kingcounty.gov`, `aqua.kingcounty.gov`, `www.wake.gov`, `data.ny.gov`, `www.revenue.state.mn.us`, `www.stats.indiana.edu` (the SDF download app returned HTTP 500), `www.revenue.wi.gov` (data page redirects to a login).

## Which counties/states publish recorder document indexes (grantor/grantee, doc type, amount) as free open data or bulk? Which charge for bulk and how much?

### Takeaway
Nothing new changes the repo's finding: no state publishes a free statewide index of recorded mortgages with names. Free recorder-grade indexes remain NYC ACRIS, Hillsborough FL (both loaded), possibly Broward FL, and the historical Cook County 2011–2015 sets. Maryland SDAT is the only free statewide file that carries a deed-intake **mortgage amount**; this session re-verified it and found it current. Everywhere else you either pay for bulk or have to fall back on transfer-tax and assessor sales files (next question).

### Cited Findings
- **Maryland SDAT `ed4q-f8tm` (re-verified 2026-11-25).** The Socrata metadata reads "Maryland Real Property Assessments_Hidden Property Owner Names", license "Public Domain", and `rowsUpdatedAt` 1793936319, which is about 2026-11-07. For each of the last 3 sales it has these columns: Grantor Name (SDAT #80/#100/#120), grantor deed liber/folio, Transfer Date (#89/#109/#129), Consideration (#90/#110/#130) and **Mortgage** (#92/#112/#132). It also carries current and prior total assessments (#172, #161, #181) and the Date Assessed — [opendata.maryland.gov API](https://opendata.maryland.gov/api/views/ed4q-f8tm.json)
- Current owner names are hidden in this public version (dataset title, above). The grantor on the next sale shows who owned the parcel before; the current owner has to come from another source — [opendata.maryland.gov](https://opendata.maryland.gov/d/ed4q-f8tm)
- Socrata federated catalog search ("real estate transfers grantee", 2026-11-25) found no new county recorder index beyond those already in the repo. The hits were the Norfolk VA assessment-and-sales series (FY19–FY27; FY27 `qva7-tzrf` updated 2026-11-24), ACRIS Real/Personal Property Master (updated 2026-11-10), and an IL PTAX view `exe5-irz5` (PTAX records since 2025-01-01, updated weekly) — [Socrata catalog API](https://api.us.socrata.com/api/catalog/v1?q=real%20estate%20transfers%20grantee&limit=25&only=dataset)
- Illinois IDOR also publishes **MyDec data files**: tab-delimited text with every recorded transfer declaration filed through MyDec for a given year, current year updated quarterly. This is a second bulk route besides the Socrata PTAX sets — [IDOR MyDec Data Files](https://tax.illinois.gov/localgovernments/property/mydecdatafiles.html) (page verified; field list not read)
- Paid bulk recorder data and prices already in the repo: Cook County Clerk transfer data (license agreement), Miami-Dade $110 per folder per month, Lake County FL $800/yr, Palm Beach subscriber FTP, Clark County NV FTP (paid), Harris County Clerk (paid), Colorado statutory daily bulk $500–$1,000/month, Salt Lake Recorder Data Services (paid), GSCCCA GA (subscription) — see `docs/sources/recorder-sources.md` and `reports/Recorder data records laws by state.md` (not re-checked this session).

### Inferences
- If a debtor owns property in MD, `ed4q-f8tm` gives the original mortgage amount as of each of the last three transfers. It does not show refinances, HELOCs or satisfactions recorded later. The figure is a purchase-money proxy, not a lien index.
- For the other states, the realistic free path to "what senior debt is recorded" is: (a) a sales or transfer file for the purchase date and price, (b) an LTV prior from HMDA, (c) public-records requests to the top-ranked recorder states in the repo's ranking (FL, NY, TX, GA, MD).

### Gaps
- No new free county recorder index was found this session. Broward's daily index extract is still unconfirmed as free (not re-checked).
- What the SDAT "Mortgage" field means (amount from the deed intake sheet? first lien only?) still needs the documentation PDF. It was not read this session.

## Which states publish property sales/transfer files with buyer and seller names for free?

### Takeaway
Free statewide files with **party names** exist in Illinois (PTAX/MyDec), Indiana (SDF), Vermont (weekly PTT XML) and Connecticut (last two sales on the CAMA parcel file). New Jersey's SR-1A has the right layout but its names are blanked (Daniel's Law). This session verified Vermont end to end: a public Azure blob holds weekly XML going back to 2006, with buyer and seller names, entity names, price, book/page, SPAN and a financing type. Wisconsin's 2026 RETR data is now search-only. Washington, Minnesota, Georgia, Colorado and the non-disclosure states have no free statewide file with names. A few county assessor files with buyer and seller names fill gaps: King WA, Wake NC, Cook IL, Detroit, Adams and Douglas CO, Norfolk VA.

### Cited Findings
**Vermont: verified, best new find**
- Vermont Tax says it "maintains weekly public Property Transfer Tax (PTT) data for access by members of the public… restructured to align closely with form PTT-172… and form PTT-175, Additional Transferors and Transferees." The format changed in 2020 — [VT Tax PTT page](https://tax.vermont.gov/data-and-statistics/ptt)
- The public container `https://taxpttrpublicblob.blob.core.usgovcloudapi.net/taxpttrpublic` can be listed anonymously (`?restype=container&comp=list`). It held 193 objects on 2026-11-25:
  - documentation: `README_2024-11.pdf`, `PTTR XML Documentation November 2024.pdf`, `Vermont-PTTR-Extract.XSD`, `PTT Decodes Whole Form_2024-11.xlsx`
  - weekly XML files (for example `PT20261116_20261122.xml`, 3.8 MB, posted 2026-11-23) and monthly ones (for example `PT20261001_20261031.xml`, 13 MB)
  - yearly archives back to `pt2006.zip` — [blob listing](https://taxpttrpublicblob.blob.core.usgovcloudapi.net/taxpttrpublic?restype=container&comp=list)
- One weekly file (2026-11-16 to 22) held 709 returns, read directly. Fields include:
  - parties: `sellerEntityName`/`buyerEntityName` (144 and 195 entity names, e.g. "SPIRESIGHT PROPERTIES LLC", "…LIVING TRUST"), `sellerLastName`/`FirstName`, `buyerLastName`/`FirstName`, buyer and seller street/city/state/ZIP, plus a `buyerSellerList` for extra parties
  - property: `span` (parcel id), `propertyLocationStreet`, `townParcelIDNo`, `townBookNumber`/`townPageNumber`, `townDateOfRecord`, `townGrandListValue`
  - transaction: `closingDate`, `dateSellerAcquired`, `valuePaidOrTransferred`, and `financing` (values: Conventional/Bank 192, Owner Financing 9, None 6, Other 502)
  - uses: `buyerUseOfProperty`, `rentedBefore`/`rentedAfter`
  - Source: [weekly XML](https://taxpttrpublicblob.blob.core.usgovcloudapi.net/taxpttrpublic/property_transfer_files/PT20261116_20261122.xml)

**Indiana: names verified at the source description**
- STATS Indiana SDF data covers July 2008 forward. Prior years are statewide (annual); the current year is weekly, updated every Friday, with partial county coverage. Variables: "parcel identifying number; address; seller; buyer; and other information as identified on the form, except for telephone numbers and email addresses" — [STATS Indiana About SDF](https://www.stats.indiana.edu/about/sdf.asp)
- The download application (`/sdf/r2`) returned HTTP 500 on 2026-11-25. Whether a loan amount is in the public file is still unverified — [STATS Indiana](https://www.stats.indiana.edu/topic/sdf.asp)

**Wisconsin: downgraded**
- DOR, 2026-02-24: "2026 RETR data – can only be accessed through the Public Search portal in MTA. The portal does not include email addresses and phone numbers for grantors and grantees." The RETR data page now redirects to the My Tax Account login. This means no free bulk for 2026 transfers; historical files may still exist but sit behind the same redirect — [WI DOR RETR status update](https://www.revenue.wi.gov/Pages/SLF/Assessor-News/2026-02-24.aspx)

**Washington: county only, with a commercial-use condition**
- WA DOR publishes REET affidavit forms and a monthly distribution report (transfer type, sale date, parcel number, taxable amount) but no affidavit-level dataset with names — [WA DOR REET forms](https://dor.wa.gov/get-form-or-publication/forms-subject/real-estate-excise-tax); [REET distribution PDF](https://dor.wa.gov/sites/default/files/2022-03/REETDistribution.pdf) (search)
- King County Assessor "Real Property Sales.zip" was reachable: 151,447,032 bytes, last modified 2026-11-21. The download page requires agreeing to a disclaimer: "Washington State law, RCW 42.56.070(9), prohibits the use of lists of individuals for 'commercial purposes'… may subject me to liability for such commercial use" — [King County Assessor Data Download](https://info.kingcounty.gov/assessor/DataDownload/default.aspx) (verified). The zip's field list was not opened. Buyer and seller names are background, unverified.

**North Carolina (Wake): verified page**
- Wake County gives ownership, sale information and property detail for all parcels, refreshed daily, as xlsx/mdb/txt/zip with a record layout. A separate qualified-sales spreadsheet covers the past 24 months — [Wake County data files](https://www.wake.gov/departments-government/tax-administration/data-files-statistics-and-reports/real-estate-property-data-files)

**Minnesota: no bulk**
- The DOR sales-ratio page offers criteria PDFs and a financing-adjustment worksheet, and links to eCRV. No sales-level download was linked — [MN DOR Sales Ratio Studies](https://www.revenue.state.mn.us/sales-ratio-studies) (verified). The repo already records that eCRV web services serve local governments only.

**New York (outside NYC): aggregates only**
- ORPTS SalesWeb covers ten years of transfers outside NYC, downloadable per search. It is not a bulk feed — [NY Tax SalesWeb](https://www.tax.ny.gov/research/property/assess/sales/salesweb.htm) (search)
- data.ny.gov has no RP-5217 sales-level dataset, only aggregates (catalog search 2026-11-25) — [data.ny.gov catalog](https://data.ny.gov/api/catalog/v1?q=property%20sales)

**Summary catalog: transfer and sales files** (combines repo findings with this session's)

| State | File | Names? | Price | Mortgage signal | Cadence | Status |
|---|---|---|---|---|---|---|
| IL | IDOR PTAX-203 (Socrata `it54-y4c6`, `exe5-irz5`) + MyDec text files | Yes | Yes | Line 15 assumed mortgage; REO/short-sale flags | Weekly / quarterly | Repo-verified; MyDec page verified |
| IN | DLGF SDF via STATS Indiana | Yes (verified description) | Yes | Unverified | Weekly / annual | Download app errored 2026-11-25 |
| VT | Tax Dept PTT XML (Azure blob) | **Yes, incl. entity names and addresses** | Yes | `financing` type only | Weekly, archive back to 2006 | **Verified** |
| CT | data.ct.gov Parcel & CAMA 2026 (`ibe8-9i3q`) | Last 2 sales G/G | Yes | No | Yearly | Repo-verified |
| MD | SDAT `ed4q-f8tm` | Grantor only (owner hidden) | Yes | **Mortgage amount** | Periodic (updated ~2026-11) | **Verified** |
| NJ | SR-1A `statdata` zips | Blank (Daniel's Law) | Yes | No | Yearly + YTD | Repo-verified |
| WI | RETR | Search only for 2026 | — | — | — | Downgraded (verified notice) |
| WA | King County Assessor sales extract | Believed yes | Yes | No | Weekly-ish | Reachable; commercial-use disclaimer |
| NC | Wake County full file + qualified sales | Owner; sale fields | Yes | No | Daily | Page verified |
| NY | ACRIS (NYC); ORPTS SalesWeb (rest) | NYC yes; rest per search | Yes | ACRIS mortgages | Daily (NYC) | Repo / search |
| VA | Norfolk assessment & sales FY27 `qva7-tzrf` | Yes (repo) | Yes | No | Daily | Catalog-verified |
| MN, GA, CO, WA (state), PA, OH, MA, ND states | — | — | — | — | — | No free statewide file with names |

### Inferences
- Vermont should be added to the load-first list as a statewide adapter, ranked just behind MD and IL. It has weekly cadence, an XSD schema, public anonymous access, entity buyer names (useful for LLC matching), seller acquisition date (holding period), buyer and seller mailing addresses (link an owner to a mailing address), and a seller-financing flag.
- `dateSellerAcquired` plus `valuePaidOrTransferred` in VT, and the 3-sale history in MD, let a pipeline compute holding period and appreciation without a recorder index.
- Washington King County data may be legally unusable for an outreach-oriented judgment business, given the RCW 42.56.070 disclaimer the downloader must accept (next question).

### Gaps
- King County `EXTR_RPSale` columns were not opened (151 MB download skipped). Name fields are unverified.
- Indiana SDF loan-amount field: unverified (download app error).
- Whether WI historical RETR bulk files are still reachable without a login: unverified (redirect to MTA).
- No statewide transfer file with names was found for GA, MN, CO, MA, NH, ME, SC, KY, OR, OH, PA or MI.

## Free value sources: assessed values by state (how stale or fractional), FHFA HPI levels, sales ratios; Zillow ZHVI terms for commercial use

### Takeaway
To get to "worth today" for free: parcel assessed value (from loaded parcel layers), divided by the jurisdiction's published assessment or equalization ratio where one exists (NY, PA, CT, NJ), then rolled forward with the FHFA all-transactions HPI at tract or ZIP5 level. FHFA files are free, U.S.-government work, and directly downloadable. Zillow ZHVI and Redfin are free to download with attribution, but their commercial-use terms could not be verified from here and should not be built in without reading them.

### Cited Findings
**FHFA HPI (verified)**
- The FHFA dataset page lists direct downloads: `hpi_at_tract.csv`, `hpi_at_zip5.xlsx`, `hpi_at_zip3.xlsx`, `hpi_at_county.xlsx`, `hpi_at_cbsa.xlsx`, `hpi_at_state.xlsx` (annual); `hpi_master.csv` and monthly purchase-only files; quarterly state and metro all-transactions and purchase-only indexes; and `hpi_dictionary.xlsx`. ZIP5 and tract files are labelled "Developmental Index; Not Seasonally Adjusted" — [FHFA HPI datasets](https://www.fhfa.gov/data/hpi/datasets)
- Local annual indexes are built from all-transactions data (sales and appraisals) for counties, ZIP codes and tracts, and FHFA calls them experimental — [FHFA local HPI FAQ](https://fhfa.gov/sites/default/files/2025-03/bdl_faqs_local_hpis_508.pdf) (search)
- FHFA claims trademarks on the HPI suite and asks users to cite working paper 16-01 for local HPIs. No restrictive data license was found — [FHFA HPI FAQ](https://www.fhfa.gov/faqs/hpi) (search); [FHFA WP 16-01](https://www.fhfa.gov:443/papers/wp1601.aspx) (search)
- The repo already plans FHFA ZIP5 as the top unbuilt free source; ZIP5 is XLSX only, while the **tract file is CSV**, so no XLSX reader is needed if tract is used — [FHFA HPI datasets](https://www.fhfa.gov/data/hpi/datasets); repo `reports/Gaps and deal flow.md`

**Assessment ratios and equalization (verified for NY and CT)**
- NY DTF publishes on data.ny.gov:
  - "Equalization Rates: Beginning Rate Year 1954" (`e6pv-77bh`, updated 2026-05-05), the level of market value at which each assessing jurisdiction assesses
  - "Residential Assessment Ratios: Beginning Rate Year 1982" (`bsmp-6um6`, updated 2026-11-10)
  - "Real Property Assessment Equity Statistics By Municipality" (`4sut-q3dt`)
  - Source: [data.ny.gov catalog](https://data.ny.gov/api/catalog/v1?q=equalization%20rate)
- CT OPM publishes "Equalized Net Grand List by Town (2011-2024 GL)" (`8rr8-a322`, updated 2026-06-05), which gives full-value estimates and assessment-to-market ratios by town. It also has a "Residential Assessment Sales Ratio Data" set (`m2ee-v5nt`, last updated 2019) — [data.ct.gov via catalog](https://data.ny.gov/api/catalog/v1?q=residential%20assessment%20ratio) (catalog results span domains)
- PA Common Level Ratio factors (reciprocals of the actual CLRs, used for realty transfer tax) are set per county each July. Examples for 2026–27: Adams 1.48, Allegheny 2.03, Erie 1.99, Beaver 1.34, Perry 1.00, Fayette 2.46 (per a July 18, 2026 amended notice) — [PA DOR CLR page](https://www.pa.gov/agencies/revenue/resources/tax-types-and-information/realty-transfer-tax/common-level-ratios.html); [Wyoming County PA PDF](https://wyomingcountypa.gov/wp-content/uploads/Common-Level-Ratio-CLR-Real-Estate-Valuation-Factors-2026-2027-.pdf) (search; factor list truncated)
- MN DOR runs annual sales-ratio studies (2027 criteria dated 2026-09-30) and publishes a financing-adjustment worksheet — [MN DOR](https://www.revenue.state.mn.us/sales-ratio-studies) (verified page links)
- The Lincoln Institute "Significant Features of the Property Tax" database gives each state's legal assessment ratio by class, e.g. Nebraska at 100% for most classes and lower for agricultural land — [Lincoln Institute](https://www.lincolninst.edu/data/significant-features-property-tax/) (search; table not retrieved)
- Background, unverified this session: CA assessed value is the Prop 13 acquisition base plus at most 2%/yr, so it is stale for long-held parcels; IL statute is 33⅓% (Cook 10% residential); MI taxable value is capped and SEV is 50%; MD reassesses on a 3-year cycle with phase-in; NY assessments are fractional and set locally, which is why equalization rates exist.

**Census ACS (verified variable)**
- ACS 5-year `B25077_001E` "Median value (dollars)" is available through the Census API, at tract or block-group level, as an owner-reported cross-check — [Census API variable](https://api.census.gov/data/2024/acs/acs5/variables/B25077_001E.json)

**Zillow and Redfin (terms not verified)**
- Zillow's Real Estate Metrics page says: "All data accessed and downloaded from this page is free for public use by consumers, media, analysts, academics and policymakers, consistent with our published Terms of Use. Proper and clear attribution of all data to Zillow is required." It does not say whether commercial product use is allowed — [Zillow Group Real Estate Metrics](https://zillowgroup.com/developers/api/public-data/real-estate-metrics) (search); [Zillow Research data](https://www.zillow.com/research/data/) (403 from here)
- Zillow says its research collaboration program is mainly for academic use, and other parties should contact Zillow — [Zillow Research more info](https://www.zillow.com/research/more-info) (search)
- FRED republishes ZHVI series under a "copyright, citation required" notice — [ALFRED release 503](https://alfred.stlouisfed.org/release/downloaddates?rid=503) (search)
- The Redfin Data Center offers free downloads (national down to ZIP and neighborhood); its pages link the general Redfin Terms of Use. No data license text was found — [Redfin Data Center](https://redfin.com/news/data-center/) (page fetched; terms not found)

### Inferences
- For ZIP-level Zillow use in a commercial product, treat ZHVI as **not cleared**: the only free-use statement found names consumers, media, analysts, academics and policymakers, and a commercial judgment-purchasing business may fall outside it. FHFA is the clean default; ACS median value is a public-domain cross-check.
- In NY, the RAR (`bsmp-6um6`) gives full market value as assessed value ÷ RAR for residential parcels. In PA, assessed value × CLR factor gives market value (that is how PA computes realty transfer tax). CT town ratios do the same.
- HPI roll-forward should start from the last arm's-length sale price (MD, IL, VT, IN, CT files) where one exists. An assessment is a second-best base.

### Gaps
- No one free, machine-readable 50-state table of legal assessment ratios was retrieved; the Lincoln Institute tables were not opened.
- Zillow Terms of Use text and Redfin data terms: not read (Zillow host blocked; Redfin page gave no terms text).
- Equalization or sales-ratio datasets for NJ (Chapter 123 / Table of Equalized Valuations), IL (IDOR sales ratio studies) and OH were not checked this session.

## Mortgage data: is there any free source of open mortgage balances, and what proxies exist (recorded original amount, satisfaction recorded, HMDA aggregates)? Tax liens?

### Takeaway
There is no free source of current balances on a named borrower's loan. The usable proxies:
- original amount: MD SDAT, NYC ACRIS, Cook 2011–2015, and any recorded index
- the financing flag in VT PTT and the assumed mortgage in IL PTAX
- satisfactions and releases where indexed (ACRIS, Hillsborough)
- HMDA loan-level records with no names, as LTV priors by tract, year and lender
- FHFA NMDB aggregates at state level, for outstanding-loan context

Federal tax liens on real property are filed wherever each state designates, usually the county recorder, so they live in the same recorder indexes.

### Cited Findings
- **HMDA public data**:
  - Loan amounts are rounded to the midpoint of the nearest $10,000 interval, and property values are treated the same way (e.g. $117,834 → $115,000). The modified LAR drops 27 fields for privacy and alters 6 more — [FFIEC Using MLAR Data](https://ffiec.cfpb.gov/documentation/publications/modified-lar/resources/using-mlar-data) (search; host blocked here)
  - The CFPB's 2018 disclosure policy guidance set the $10k-midpoint rule after a privacy balancing test — [84 FR 649 (Jan. 31, 2019)](https://www.govinfo.gov/content/pkg/FR-2019-01-31/html/2018-28404.htm) (search)
  - The repo already lists what HMDA cannot give: no borrower name, property address, loan ID or application date — `docs/sources/recorder-sources.md`
- **FHFA NMDB aggregate statistics**: built from a nationally representative 5% sample of closed-end first-lien residential mortgages. There is an "Outstanding Residential Mortgage Statistics" dashboard with CSV export. Geography goes down to national, census region/division, state and metro (100 largest metros for performance). No county level was found — [FHFA NMDB aggregate statistics](https://www.fhfa.gov/data/dashboard/nmdb-outstanding-residential-mortgage-statistics) (search); [data dictionary 2026Q1](https://www.fhfa.gov/document/d/nmdb/nmdb-aggregate-statistics-data-dictionary-technical-notes-2026q1.pdf) (search)
- **Vermont PTT `financing` field**: Conventional/Bank, Owner Financing, None, Other. It shows whether the purchase was financed, not how much — [VT weekly XML](https://taxpttrpublicblob.blob.core.usgovcloudapi.net/taxpttrpublic/property_transfer_files/PT20261116_20261122.xml) (verified)
- **MD SDAT mortgage amount** per transfer (verified, first question above).
- **IRS federal tax liens**: 26 U.S.C. § 6323(f)(1)(A)(i) says notice for real property is filed "in one office within the State (or the county, or other governmental subdivision), as designated by the laws of such State, in which the property subject to the lien is situated"; personal-property notices follow the taxpayer's residence — [26 U.S.C. 6323, Cornell LII](https://www.law.cornell.edu/uscode/text/26/6323) (verified). Free bulk IRS lien data in the repo so far: NYC ACRIS personal-property master (FL, FTL doc types) and FL Sunbiz filings (behind the shared SFTP login) — `docs/sources/judgments-liens.md`, `reports/Gaps and deal flow.md`.
- **State tax warrants** with debtor, amount and satisfaction dates: NY `v7ua-z23v` (loaded) and FL DOR's delinquent list. Both are already in the repo's judgment sources (`docs/sources/judgment-sources.md`).
- **HELOCs**: HMDA covers open-end lines of credit (background), and HELOCs show up in recorder indexes as mortgages or deeds of trust. No free HELOC-specific bulk source was found.

### Inferences
- A defensible free balance estimate is still the repo's 4-step method (original amount, else sale price × HMDA tract/year LTV; amortize at PMMS; zero on recorded satisfaction). Add a VT `financing` = None/Other flag, which suggests a cash purchase.
- NMDB state aggregates can calibrate how much a typical outstanding loan has paid down, by origination vintage, at state level. They cannot price any single lien.
- Because a federal tax lien on real property is filed locally, any free recorder index (ACRIS, Hillsborough, a records-request extract) doubles as an IRS-lien source for that county.

### Gaps
- No free source of payoff or current balance exists. A payoff statement from the lender or servicer is not public.
- Exact NMDB file names and outstanding-balance variables were not read (only search excerpts).
- Which office each state designates for real-property NFTLs (county recorder versus SOS) was not tabulated this session.

## Statutes restricting commercial use of recorder or assessor data, by state

### Takeaway
The repo's recorder report already covers WA, AZ, IL, OH, SC, KS, residency blockers and contract terms (IN, WI, UT, NM). This session adds or clarifies:
- California's assessor-confidentiality rule (R&T § 408) and its public transfer list (§ 408.1)
- Indiana's names-and-addresses list rule (IC 5-14-3-3(f))
- Rhode Island § 38-2-6, the old commercial-use bar, is **repealed** (some guides still cite it)
- King County WA makes data downloaders accept the RCW 42.56.070 commercial-use bar, citing it as subsection **(9)**, while the repo report cites (8); the numbering needs checking
- New York's LLC Transparency Act ownership data is not public

### Cited Findings
- **Washington**: King County's assessor download disclaimer cites "RCW 42.56.070(9), prohibits the use of lists of individuals for 'commercial purposes'". The downloader acknowledges liability for commercial use, including by others who receive the data — [King County Assessor](https://info.kingcounty.gov/assessor/DataDownload/default.aspx) (verified). The repo report cites RCW 42.56.070(8) and AGO 2019 No. 3.
- **California**: BOE guidance treats R&T § 408 as the general confidentiality rule for assessor records. Information the law does not require the office to keep or prepare is not a public document. § 408.1 requires a public list of transfers in counties of 50,000 or more, and § 408.1(f) keeps information from the change-in-ownership statements confidential. § 408.3 (property characteristics) is mandatory above 715,000 population — [BOE annotations 260.0000](https://boe.ca.gov/LawGuides/Property/Current/PTLG/Annt/260-0000-all.html); [BOE confidentiality of assessors' records](https://boe.ca.gov/proptaxes/pdf/confidentiality_of_county_assessors_records.pdf) (search)
- **Indiana**: IC 5-14-3-3(f) says an agency need not create lists of names and addresses. Some lists (e.g. public employees) may not be disclosed to, or used by, commercial entities for commercial purposes. The PAC reads the restriction as covering true lists of names and addresses, not broader databases (11-INF-54) — [Justia IC 5-14-3-3](https://law.justia.com/codes/indiana/title-5/article-14/chapter-3/section-5-14-3-3); [PAC 11-INF-54](https://www.in.gov/pac/files/informal/11-INF-54.pdf) (search)
- **Rhode Island**: § 38-2-6 (commercial use of public records) is listed as repealed. RCFP says the 2012 amendments (P.L. 2012, chs. 448 and 454) repealed it. Older NFOIC text still describes the solicitation bar — [RI Legislature § 38-2-6](https://webserver.rilegislature.gov/Statutes/TITLE38/38-2/38-2-6.htm); [RCFP RI](https://www.rcfp.org/open-government-guide/rhode-island/) (search)
- **New York**: the repo report notes Pub. Off. Law § 89(2)(b)(iii), which lets an agency deny name/address lists sought for solicitation (marked background there).
- **New Jersey**: Daniel's Law blanks names in SR-1A and MOD-IV (repo-verified in `docs/sources/recorder-sources.md`).
- **Maryland**: the public SDAT open-data version hides current owner names (dataset title, verified).

### Inferences
- In CA, assessor data beyond what the law requires (the transfer list, property characteristics) is presumptively confidential. Free CA owner data therefore depends on county GIS layers, which matches the repo's thin CA coverage (5 of 58 counties).
- Recent public-records requests and data use in RI no longer face a commercial-use statute. The custodian's own terms may still apply.
- For any WA source, an honest commercial requester should expect refusal or a contractual bar. Treat WA owner-name data as unusable for outreach until counsel reviews it.

### Gaps
- No systematic 50-state table of **assessor-specific** confidentiality or commercial-use statutes was built. Only CA, IN, RI, WA (plus repo items) were checked.
- Texas Tax Code home-address confidentiality for protected classes, FL § 119.071(4)(d) exempt-person redactions, and similar "protected person" programs were not researched this session (background: many states let judges, police and others hide owner names in assessor records).

## Which free signals reveal properties held in an LLC controlled by the debtor?

### Takeaway
No free government source links an LLC to its beneficial owner nationally. The federal CTA database is gone for U.S. companies, and New York's LLC Transparency Act data is not public and now covers foreign LLCs only. Free signals are indirect:
- registries that list officers, managers or beneficial owners (DC is best; CT, FL, RI and PA have principals; see the repo's registry doc)
- registered-agent and mailing-address matches between debtor and entity
- transfer files that name the entity buyer and give its mailing address (VT verified; IL PTAX organization fields)
- deeds from the debtor to an entity, with nominal consideration, in transfer files (a fraudulent-transfer red flag)

### Cited Findings
- **Federal CTA**: FinCEN's March 2025 interim final rule exempts all entities previously defined as "domestic reporting companies" from BOI reporting. Foreign reporting companies need not report U.S.-person beneficial owners. The basis is 31 U.S.C. 5336(a)(11)(B)(xxiv) — [90 FR 13688 (Mar. 26, 2025)](https://www.govinfo.gov/content/pkg/FR-2025-03-26/html/2025-05199.htm); [FinCEN news release](https://www.fincen.gov/news/news-releases/fincen-removes-beneficial-ownership-reporting-requirements-us-companies-and-us) (search). A later FinCEN document finalizes the IFR with limited changes; its date and terms were not confirmed — [FinCEN BOI final rule PDF](https://www.fincen.gov/system/files/2026-08/BOIFinalRuleforFR.pdf) (search)
- **New York LLC Transparency Act** (effective 2026-01-01):
  - BOI goes into a secure database that is not subject to FOIL; access is limited to law enforcement, court order or owner consent
  - NYDOS guidance limits filing to LLCs formed outside the U.S. and authorized in NY
  - entities that fail to file are marked "past due" in the public DOS database
  - Sources: [Sidley (Feb. 2026)](https://www.sidley.com/en/insights/newsupdates/2026/02/ny-llc-transparency-act-took-effect-but-governor-veto-exempts-us-formed-llcs); [Holland & Knight (Jan. 2026)](https://www.hklaw.com/en/insights/publications/2026/01/new-york-llc-transparency-act-reporting-limited) (search)
- **Vermont PTT** shows entity names for both parties, with mailing addresses. For example, one week had 195 entity buyers such as "SPIRESIGHT PROPERTIES LLC" and "SUSAN HAVELOCK ROOP LIVING TRUST", alongside individual buyer and seller names and street addresses — [VT weekly XML](https://taxpttrpublicblob.blob.core.usgovcloudapi.net/taxpttrpublic/property_transfer_files/PT20261116_20261122.xml) (verified). The trust names often embed the settlor's personal name.
- **Registries with officers, members or beneficial owners**: DC (beneficial owners, CC BY 4.0), CT (principals), FL Sunbiz (up to 6 officers, but via shared SFTP login), RI weekly (officers), PA (party_type, unverified), NY (chair/CEO, filers). Registered agents appear in CO, IA, NY, OR, CT and DC. All are in `docs/sources/business-registry-sources.md`.
- **Free UCC bulk** (CO, CT, OR) can tie a debtor-controlled LLC to secured lenders (repo registry doc).

### Inferences
Ranked free LLC-control signals for a debtor, strongest first:
1. A registry officer, manager or beneficial-owner name equals the debtor (DC, CT, RI, FL).
2. A transfer file shows a debtor-to-entity deed near or after the judgment date, especially at low or zero consideration (VT `valuePaidOrTransferred`, IL PTAX, MD SDAT grantor plus consideration).
3. The entity's mailing address (VT buyer address, parcel owner mailing address) or registered-agent address matches the debtor's home address.
4. The trust or LLC name contains the debtor's surname or street address (common for single-asset LLCs and revocable trusts).
5. The entity was formed shortly before the acquisition (registry formation date against transfer date).

A NY "past due" LLCTA flag only identifies foreign LLCs. It is not useful for domestic debtor LLCs.

### Gaps
- No free nationwide registered-agent dataset. Commercial registered agents (CT Corp, Northwest, etc.) mask control, and nothing public pierces that.
- Whether IL PTAX organization buyer fields carry the managing member's name was not checked.
- How a debtor-to-LLC transfer interacts legally with the judgment (fraudulent-transfer law, charging-order-only remedies for LLC interests) is outside this data scope and needs counsel.
