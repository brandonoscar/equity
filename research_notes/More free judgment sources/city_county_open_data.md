# City and county open-data portals: liens, judgments and judgment-adjacent debt records

Researched 2026-11-22. Scope: US city and county open-data portals (Socrata, ArcGIS Hub, CKAN, Carto, OpenDataSoft) that publish free bulk datasets naming a debtor or a parcel. Out of scope because they are already loaded: NYC (OATH, evictions, HPD), NYS warrants, Allegheny/WPRDC, CT SOTS.

## How the sweep worked, and what this container could reach

The tags mean:
- **[LIVE]**: I pulled the metadata, field list, row count and a sample row myself, through the ArcGIS REST, Socrata or Carto API.
- **[CATALOG]**: I fetched the dataset's Socrata catalog record (columns, last update, license). The catalog came from the federated Socrata Discovery API, called through `datacatalog.cookcountyil.gov/api/catalog/v1`, which returns every Socrata domain. The dataset's own host was blocked, so I have no row count or sample.
- **[SEARCH]**: seen only in web-search snippets.
- **[UNVERIFIED]**: from background knowledge, or not settled.

Hosts that were reachable:
- `hub.arcgis.com`, `www.arcgis.com`, and `services*.arcgis.com` (ArcGIS Online hosted layers)
- `datacatalog.cookcountyil.gov` (and its federated catalog endpoint)
- `data.nola.gov`, `data.cityofnewyork.us`, `phl.carto.com`

Hosts that refused connections (proxy 403 or DNS failure; Bash and WebFetch both failed):
- `api.us.socrata.com` and `catalog.data.gov`
- data.cityofchicago.org, data.lacity.org, data.lacounty.gov, data.baltimorecity.gov, data.memphistn.gov, data.milwaukee.gov, milwaukeemaps.milwaukee.gov, data.kcmo.org, data.cincinnati-oh.gov, opendata.columbus.gov, dallasopendata.com, data.houstontx.gov, data.sanantonio.gov, data.austintexas.gov, opendata.miamidade.gov, data.tampagov.net, data.cityoforlando.net, data.coj.net, data.seattle.gov, data.kingcounty.gov, data.sfgov.org, data.oaklandca.gov, data.sandiego.gov, phoenixopendata.com, opendata.minneapolismn.gov, data.boston.gov, data.buffalony.gov, data.cityofrochester.gov, data.syr.gov, opendata.dc.gov, data.richmondgov.com, data.norfolk.gov, data.nashville.gov, data.louisvilleky.gov, data.indy.gov, data.okc.gov, data.cabq.gov, opendata.slc.gov, data.denvergov.org, data.providenceri.gov, data.jerseycitynj.gov, data.detroitmi.gov, opengis.detroitmi.gov, data.clevelandohio.gov, opendata.cuyahogacounty.us, stlouis-mo.gov, data.phila.gov, data.pittsburghpa.gov, gis2.co.dakota.mn.us, scgisa.starkcountyohio.gov

Many cities on blocked hubs still host their layers on ArcGIS Online (`services*.arcgis.com`), so I could reach those layers directly. That is how Detroit, Baltimore, Miami-Dade, LA County, Maricopa and Louisville were verified.

## Which large cities and counties publish such datasets?

### Takeaway

Fourteen of the roughly 55 large cities and counties in the brief publish at least one free bulk dataset that names a debtor or a parcel for a lien, judgment or tax-delinquency record:
- Detroit, New Orleans, Baltimore, Miami-Dade, Los Angeles County, Maricopa, Louisville, Philadelphia, Norfolk, Richmond, Cook County, Prince George's County, Chicago and Orlando.

The most valuable new find is **Detroit's DAH Blight Tickets**. It works like an OATH dataset for Detroit:
- 915k adjudicated civil-violation judgments
- Each row has the property owner's name, the parcel id, the judgment amount and the balance due.

Real lien datasets with a recording reference are rare. The best is **Miami-Dade Code Compliance liens**, which carry the Official Records book and page, plus the folio. Most other datasets are delinquent-tax rolls or tax-sale lists. Those are statutory liens on the parcel and usually name the owner.

No city publishes lis pendens or general civil money judgments in bulk.

### Ranked findings (lien on real property + debtor name + parcel id first)

**Tier 1: lien or judgment, debtor name and parcel id**

1. **Detroit: Blight Tickets (Department of Appeals and Hearings)** [LIVE]
   - **Source:** https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/blight_tickets/FeatureServer/0. Publisher: City of Detroit. Last edit 2026-11-21.
   - **Rows:** 915,218.
     - 890,691 have a `parcel_id`.
     - 374,145 have `amt_balance_due > 0`.
     - 196,222 tickets were issued since 2024-01-01.
     - The earliest sample row is from 2005.
   - **Fields:**
     - `ticket_number`, address, ordinance, `disposition`, `hearing_date`, `judgment_date`
     - `amt_fine`, `amt_judgment`, `amt_payment`, `amt_balance_due`, `payment_status`, `collection_status`
     - `property_owner_name` and the owner's full mailing address
     - `parcel_id`, latitude and longitude
   - **Dispositions:**
     - About 585k are "Responsible by Default/Admission/Determination".
     - About 320k are "Not responsible…".
   - **Payment status:** 366,440 NO PAYMENT APPLIED, 220,784 PAID IN FULL, 7,718 PARTIAL.
   - **Legal effect:**
     - DAH adjudicates these as civil cases, per the layer description.
     - Whether an unpaid judgment becomes a lien on the parcel or is added to the tax roll under Michigan law is **[UNVERIFIED]**.
     - Either way, this is a docketed municipal money judgment against the named owner, keyed to the parcel. It joins to the parcel graph the same way OATH does.
   - **Archive copy:** `opengis.detroitmi.gov/.../DAH/blight_violation_citations` (629,962 rows) is blocked here.
2. **New Orleans: Sheriff Sales – Lien Foreclosures** [LIVE]
   - **Source:** https://data.nola.gov/d/d52w-8nva
   - **Rows:** 1,771. Fields: `Defendant`, `Plaintiff` (CITY OF NEW ORLEANS), `CaseTitle`, `CdcCaseNumber` (Civil District Court), `PropertyAddress`, `SaleDate`, `SaleAmount`, `SaleStatus`.
   - **What it is:** code-enforcement liens foreclosed at sheriff's sale. Each row names the defendant and gives the CDC case number.
   - **Stale:** rows were last updated 2018-11-16. No parcel id; address only.
3. **New Orleans: Adjudication Enforcement Cases** [LIVE]
   - **Source:** https://data.nola.gov/d/wy29-i338
   - **Rows:** 115,036; 26,448 have `Name`. Daily; last updated 2026-11.
   - **Coverage:** Code Enforcement, ABO, HDLC, VCC, STR and Zoning cases since 2018. Older case numbers go back to 2012.
   - **Fields:** `Name`, `Address`, `UnpaidFees`, `D_Filed`, `D_Closed`, stage and status.
   - **Unpaid fees:** 17,660 cases have `UnpaidFees > 0`, totalling $52.1M.
   - **Companion datasets:**
     - Fines and fees, https://data.nola.gov/d/f5zm-xkyr: 225,395 rows with `Amount`, `IsPaid` and `D_Due`. No name or parcel.
     - Hearings, https://data.nola.gov/d/uzyk-jrck: 53,128 rows with a `Judgment` field. [LIVE]
     - Code Enforcement All Hearings, https://data.nola.gov/d/44ct-56tr: 103,430 rows with `Judgment` (e.g. "Found Guilty") and `GeoPIN`. CC0. [LIVE]
   - **Legal effect:**
     - The catalog says pipeline cases close "when the in rem judgement is paid" [SEARCH].
     - NOLA code judgments are in rem against the property and can be enforced by lien and sheriff's sale, as the d52w-8nva records show.
     - Joins: by GeoPIN for hearings; by name and address for cases.
4. **Baltimore City: Tax Lien Certificate Sale Properties** [LIVE]
   - **Source:** https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services/Tax_Lien_Certificate_Sale_Properties1/FeatureServer/0
   - **Rows:** 43,736 across sale years 2019 (12,166), 2020 (7,028), 2021 (11,327), 2022 (7,491) and 2023 (5,724).
   - **Fields:** `OWNER_NAME`, `BLOCK`, `LOT`, `PROPERTY_ADDRESS`, `LIENS`, `INTEREST`, `LEGAL_FEES`, `TOTAL_AMOUNT`, `REDEMPTION_DATE`, `REDEMPTION_NAME`, `ASSESSED_VALUE`.
   - **What it is:** an annual tax lien certificate sale covering property tax, water and other municipal liens.
   - **Stale:** last edit 2023-06-30; no 2024–2026 sales.
   - **Related layers** [LIVE]:
     - `Tax_Sale/FeatureServer/0`, the 2021 list: 11,570 rows with `ownername`, `pin`, `block`, `lot`, `total_lien`, city and state tax, `soldto`. Last edit 2023-05.
     - `tax_sale_properties2`: 10,921 rows with `Client` (owner) and `Owed_Value`. Last edit 2021.
     - `Tax_Sale_2023_Locations`: 7,657 rows with `lienAmount`, block and lot, and no owner.
5. **Louisville Metro: Property Foreclosures (Metro lien foreclosures)** [LIVE]
   - **Source:** https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/Louisville_Metro_KY_Property_Foreclosures/FeatureServer/0
   - **Rows:** 3,624. Fields: `Case_` (e.g. 22CI400965, Jefferson Circuit), `Case_Style` (e.g. "CW vs TERRY REAL PROPERTIES LLC ET AL"), `Action_Filed`, `Sale_Date`, `Purchaser`, `Full_Parcel_ID` (often null), address. Last edit 2026-09-24.
   - **Companion:** `2021_Present_Metro_Foreclosure`, 105 rows with `Owner`, `Parcel_ID`, `Case_Style`, `Sale_Date`, `Purchaser`. Last edit 2026-07.
   - **Legal effect:** these are Louisville Metro's foreclosures of its code-enforcement and demolition liens in circuit court [UNVERIFIED that every row is a lien foreclosure].
6. **Louisville Metro: Lien Holder Final Orders** [LIVE]
   - **Source:** https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/lien_notification_final_orders/FeatureServer/0
   - **Rows:** 513. Fields: `fullname` (owner), owner mailing address, property address, `final_order_state`, `final_citation_amount`, hearing fields. No parcel id. Updated 2026-11-22.
   - **What it is:** code-enforcement final orders noticed to lienholders. Under KY's local code-enforcement statute (KRS 65.8835 [UNVERIFIED]) a final order becomes a lien on the property.
   - **Deprecation:** data.gov says an older "lien notification final order history" version is deprecated [SEARCH](https://catalog.data.gov/dataset/louisville-metro-ky-lien-holder-final-orders-1db8d).

**Tier 2: recorded lien or delinquent-tax lien with parcel id; owner name missing or only via a parcel join**

7. **Miami-Dade County: Code Compliance Violation – Lien View** [LIVE]
   - **Source:** https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/CodeComplianceViolation_Lien_View/FeatureServer/0
   - **Rows:** about 6,920–7,138. Fields: `CASE_NUM`, `CASE_DATE`, `STAT_DESC`, `FOLIO` (parcel), `PROBLEM_DESC`, `LAST_ACTV`, `LN_RECBOOK`, `LN_RECPAGE`, `LN_RECDATE` (Official Records citation of the recorded lien). Daily (edited 2026-11-22).
   - **Lien status** is in `LAST_ACTV`: e.g. 1,190 "Lien Satisfied", 308 "Lien Cancelled", 373 "Lien Referral Accepted by Lien Unit".
   - **Legal effect:** a recorded code lien. Debtor name comes from a folio join to the property appraiser roll.
   - **Sister layers** in the same org [LIVE]:
     - `CodeComplianceViolation_ReferredtoFinance_View`: 15,222 rows, with the same lien book, page and date fields plus "Referred to ICD for Collections".
     - `BuildingViolationLien`: 8,439 rows with `CASE_NUM`, `LIEN_BOOK`, `LIEN_PAGE`, `LIEN_RECDT`. Building-code liens, no folio, so join through `BuildingViolation_gdb`.
     - `data_judgement`: 27,186 rows with `OWNER`, `FOLIO_NUMBER`, `PARCEL_TYPE` ("H-Household"), and `ATTORNEY_FEES`, `JUDGEMENT_FEES` and `TOTAL_FEES`. 1,393 rows have non-zero fees. My guess is that these are Solid Waste fee judgments or liens; the purpose is **[UNVERIFIED]**.
8. **Los Angeles County Treasurer-Tax Collector: Secured Defaulted Tax Roll** [LIVE]
   - **Source:** https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/Secured%20Defaulted%20Tax%20Roll/FeatureServer/0
   - **Rows:** 1,746,758. Fields: `AIN`, `Defaulted_Year`, `Redemption_Amount`, `Tax_Balance`, `Penalty_Balance`, `Redemption_Date`, `Sale_Number`, `Deeded_Year`, payment-plan fields. Last edit 2026-11-16. No owner name.
   - **Legal effect:** tax-defaulted secured property. The tax lien is statutory and attaches to the parcel.
9. **Los Angeles County: Liens Secured Tax Roll** [LIVE]
   - **Source:** https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/Liens%20Secured%20Tax%20Roll/FeatureServer/0
   - **Rows:** 2,427,192. Fields: `PARCEL_NUMBER`, plus up to 25 direct-assessment and special-assessment lien slots (`Fn_AGENCY_NAME`, `Fn_LIEN_AMT`). Updated 2026-11-16.
   - **What it is:** special assessments levied as liens on the secured roll (stormwater, vector control, lighting districts and similar). No owner name. Each lien is small.
   - **Tax-defaulted auction lists:** `2025B_Tax_Defaulted_Properties` (1,260 rows; APN, `MIN_BID`, legal description), `2025A_Tax_Defaulted_Parcels`, `TAX_DEFAULT_PROPERTIES_2024A`.
10. **Maricopa County Treasurer: Lien and Delinquent Parcels** [LIVE]
    - **Source:** https://services.arcgis.com/ykpntM6e3tHvzKRJ/arcgis/rest/services/ParcelLienDelinquent/FeatureServer (layer 1 "Unsold Lien Parcels", 1,455 rows; layer 2 "Delinquent Tax Parcels", 34,594 rows). Daily (2026-11-22).
    - **Fields:** `APN`, address, `DeedNumber` (Recorder), links to the assessor and treasurer. No owner name and no amounts. Owner comes from an APN join.
11. **Philadelphia: Real Estate Tax Balances** [LIVE]
    - **Source:** Carto `real_estate_tax_balances` via https://phl.carto.com/api/v2/sql
    - **Rows:** 683,926 covering 102,829 parcels. Fields: `parcel_number` (OPA), `owner`, `location`, `tax_period`, `principal`, `interest`, `penalty`, `total`, `lien_number`. 579,765 rows have a lien number (e.g. "1512R11605339"). Total due is $451M.
    - **Stale:** tax periods run 1972–2016 only.
    - **Retired:** the companion `real_estate_tax_delinquencies` table now returns "permission denied". Treat it as retired or restricted on Carto.
    - **Lien effect:** Philadelphia's municipal claims for taxes are liens docketed with the Court of Common Pleas, and `lien_number` looks like that claim number. The lien link is an inference [UNVERIFIED].
12. **Philadelphia: L&I Demolitions** [LIVE]
    - **Source:** Carto `demolitions`.
    - **Rows:** 14,373, of which 8,186 have `city_demo = YES`. Fields: `opa_account_num`, `opa_owner`, address, dates, status.
    - **Legal effect:** demolition costs on city-performed demolitions are billed and can be liened [UNVERIFIED]. This dataset itself carries no amounts.
    - **Not liens:** Carto `violations` (2.04M) and `case_investigations` (2.15M) carry `opa_account_num`, `opa_owner`, casetype and status [LIVE]. They are violations, not liens.

**Tier 3: delinquent-tax lists naming the owner (Socrata, host blocked; catalog record only)**

13. **Norfolk VA: Delinquent Property Taxes** [CATALOG]
    - **Source:** https://data.norfolk.gov/d/7qie-z5gv
    - **Columns:** `PIN`, `PROPERTY OWNER`, `ACCOUNT NUMBER`, `TAX DUE`, `INTEREST DUE`, `PENALTY DUE`, `TOTAL`, `YEAR`, `QUARTER`, `PROPERTY ADDRESS`. Updated 2026-11-22.
    - **Scope:** every parcel at least one quarter behind. The description says it excludes nuisance abatement liens. VA real-estate taxes are a lien on the parcel.
    - **Also:** code cases with `GPIN`, https://data.norfolk.gov/d/mxtv-99gh [CATALOG].
14. **Richmond VA: Delinquent Real Estate Taxes (Six Months or More)** [CATALOG]
    - **Source:** https://data.richmondgov.com/d/83t5-hbac
    - **Columns:** `Property Code`, `Bill Year`, `Current Owner Name 1/2`, `Total Due`. Updated 2026-08-31.
15. **East Baton Rouge Parish: Adjudicated Parcel / Adjudicated Property** [CATALOG]
    - **Sources:** https://data.brla.gov/d/shrr-fsqq (`OWNER NAME`, `ASSESSMENT NO.`, `SALE YEAR`, values; updated 2026-05) and https://data.brla.gov/d/a4h4-zi7e (`TAXPAYER NAME`, `PROPERTY NUMBER`; updated 2024-02).
    - **What it is:** tax-adjudicated property, meaning title has passed to the parish after an unsold tax sale. Baton Rouge is not on the top-75 list.
16. **Clermont County OH (Cincinnati metro)** [CATALOG]
    - Publisher: internal.opendata.clermontauditor.org. Daily (2026-11-22), Public Domain.
    - `q52y-wzm4` Delinquent Tax Values: `NAME`, `OWN1/2`, `Parcel Number`, `NETDELQ`, `CERTDLQYR`.
    - `77ey-nevf` Non-TIF Special Assessments: `PARCEL ID`, `Owner 1/2`, `AMOUNT`, project.
    - `94fc-2usj` Total Taxes Due and Paid: owner, parcel, `NETDELQDUE`, special-assessment delinquencies.
    - The best Ohio find, but it covers a suburban county, not Hamilton.
17. **Cook County Treasurer: Annual Tax Sale / Scavenger Sale** [CATALOG]
    - **Sources:** https://datacatalog.cookcountyil.gov/d/55ju-2fs9 and https://datacatalog.cookcountyil.gov/d/ydgz-vkrp
    - **Columns:** `PIN`, `Buyer Name`, tax amounts offered and paid, `Sold at Sale`.
    - **Stale:** last updated 2016-12. They name the tax buyer, not the owner.
    - **Older one-year files:** 2009–2011 sold, forfeited and no-bid PIN files.
    - **Recorder foreclosure files** (`Pin`):
      - `epxa-9ihc` and `9br9-dhca` (2011–2012)
      - `4f2q-h3b7` (2015)

**Tier 4: foreclosure registries, demolition and code records, tax-sale lists without owner (lower value)**

- **Prince George's County MD: County Foreclosures** [CATALOG]
  - Sources: https://data.princegeorgescountymd.gov/d/cni6-nr5g (weekly; updated 2026-08) and `mnie-hrv7` (2009 to present).
  - Columns: `Tax Account Number`, address, submitted date, occupied flag. No borrower name.
- **Chicago: Foreclosed Rental Property** [CATALOG], https://data.cityofchicago.org/d/yhcw-iu53
  - Columns: `OWNER NAME`, owner address and agent. The owner is the post-foreclosure owner (lender or REO), not the debtor.
  - Updated 2026-11-21.
- **Chicago: Ordinance Violations** [SEARCH], `6br9-quuz`
  - DOAH (administrative hearings) cases, with respondents. The catalog warns that respondents "are not necessarily the parties believed to have committed the violations".
  - Whether fines, judgment amounts and PIN are included is unconfirmed: [data.gov](https://catalog.data.gov/dataset/ordinance-violations). Host blocked.
- **Los Angeles City (LAHD):** Registered Foreclosure Properties 2025 (`2qnc-kq4g`) and 2026 (`5nzp-isg9`), with `APN` and `Lender`; and Property Look-Up for Eviction Cases (`2u8b-eyuu`, `APN`) [CATALOG].
- **King County WA: Foreclosure parcels** [CATALOG], https://data.kingcounty.gov/d/nx4x-daw6
  - Tax-foreclosure parcel list, one `Parcels` column. Updated 2026-06. Public Domain.
- **Orlando: Code Enforcement Cases** [CATALOG], https://data.cityoforlando.net/d/k6e8-nw6w
  - Columns: `Case Name`, `Parcel ID`, case type and status. Rolling 5 years, daily.
  - Lien and fine amounts are not in the column list.
- **Orange County FL: Tax Sale Data** [LIVE], `services1.arcgis.com/0U8EQ1FrumPeIqDb/.../Tax_Sale_Data/FeatureServer/0`
  - Only 41 rows: `USER_TDA_NUM` (tax deed application), `USER_PARCEL`, sale date (e.g. 12/10/2026), status. Live as of 2026-11-17.
- **Cincinnati** [CATALOG]:
  - Private Lot Abatement Program `pk9w-99n6`: abatement costs, `CLEAN_BALANCE`, owner-invoiced date. Address only.
  - Vacant & Foreclosed Property Registration `w3jp-dfxy`.
- **Wayne County / Detroit (archival)** [LIVE]:
  - Data Driven Detroit tax foreclosures 2002–2013: 83,381 parcels, parcel number only.
  - Wayne County Tax Auction 2017: 3,911 rows with `parcel_id`, `deed_name` (buyer), bids. Stale.
- **Detroit (current)** [LIVE]: demolition layers (`bseed_demolition_permits` 16,326 rows; `city_completed_demolitions`; pipeline). Demolition costs may be liened; the layers carry no amounts.
- **Maryland District Court: Eviction Case Data** [CATALOG], https://opendata.maryland.gov/d/mvqb-b4hf
  - Statewide. Columns: case number, event type and date, tenant ZIP and city. No names.
- **Texas TCEQ: Civil Judgments Issued** [CATALOG], https://data.texas.gov/d/7ift-kbgd
  - A state agency, not a city, but these are true court judgments: `Customer Name`, `District Court Docket No.`, `Penalty Assessed`, `Payable Amount`, `Judgment Date`.
  - Small, annual. Updated 2025-11.
- **Missouri DOR: Child Support Lien List** [CATALOG], https://data.mo.gov/d/7t5a-79ri
  - VIN and make only. Vehicle liens, not usable.
- **Milwaukee: Delinquent Real Estate Tax Accounts** [SEARCH], https://data.milwaukee.gov/dataset/delinquent-real-estate-tax-accounts
  - CKAN, monthly, sorted by tax account and levy year. Field list unconfirmed. Host blocked.
  - A Sept 2025 snapshot showed about $46.4M across 10,302 properties, per a [Marquette blog](https://law.marquette.edu/facultyblog/?p=31291).
  - The ArcGIS "Tax delinquent parcels" layer (milwaukeemaps.milwaukee.gov MapServer/11, 160,379 features) is also blocked here.
- **Syracuse: parcel file** [SEARCH], on the DataCuse portal. About 42k parcels with owner and `amtdelinqu` (delinquent tax).
- **DC: Integrated Tax System Public Extract** [SEARCH], https://catalog.data.gov/dataset/integrated-tax-system-public-extract
  - Owner and mailing address per SSL. CC-BY-4.0.
  - No tax-sale or lien dataset was found.

### Cities checked with nothing qualifying found

A dataset named for liens, judgments, tax sales or delinquency with a debtor or parcel field was not found for:
- **Texas, Southwest and Mountain West:** Dallas, Houston/Harris, San Antonio, Austin, Fort Worth, El Paso, Phoenix city, Tucson/Pima, Albuquerque, Las Vegas/Clark, Salt Lake, Denver, Oklahoma City, Tulsa
- **West Coast:** Seattle, Portland, SF, Oakland, San Diego, Sacramento
- **Upper Midwest:** Minneapolis/Hennepin, Kansas City, St. Louis, Indianapolis, Columbus/Franklin, Cleveland/Cuyahoga
- **Southeast:** Nashville, Memphis/Shelby, Birmingham, Charlotte, Raleigh, Atlanta/Fulton, Jacksonville, Tampa
- **Northeast:** Boston, Providence, Buffalo, Rochester, Newark, Jersey City

This covers both the federated Socrata catalog and the ArcGIS Hub search. Specific notes:
- **Cuyahoga:** tax-lien certificates are sold by negotiated bulk sale. The county has no open dataset; sheriff-sale results are search only [SEARCH](https://cuyahogacounty.gov/treasury/delinquency/tax-lien-certificate-sales). Case Western's NEOCANDO holds foreclosure filings (2005+) and sheriff sales (2000+); access terms are unclear [SEARCH](https://neocando.case.edu/property-data.html).
- **St. Louis:** the Land Tax Sale list is posted as a web list two weeks before each sale. It is not an open dataset [SEARCH](https://www.stlouis-mo.gov/government/departments/sheriff/land-tax/index.cfm).
- **Kansas City (Jackson County):** the Delinquent Land Tax suit database is search only [SEARCH](https://www.16thcircuit.org/delinquent-land-tax).

### Cited findings (sources)

- Detroit DAH Blight Tickets: 915,218 rows, with owner name, parcel id, judgment and balance due — [ArcGIS layer](https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/blight_tickets/FeatureServer/0) [LIVE]
- NOLA Sheriff Sales – Lien Foreclosures, with defendant and CDC case number, stale since 2018 — [data.nola.gov](https://data.nola.gov/d/d52w-8nva) [LIVE]
- NOLA adjudication cases: Name and UnpaidFees, 17,660 unpaid totalling $52.1M — [data.nola.gov](https://data.nola.gov/d/wy29-i338) [LIVE]
- Baltimore tax lien certificate sales 2019–2023, with owner and block/lot — [ArcGIS layer](https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services/Tax_Lien_Certificate_Sale_Properties1/FeatureServer/0) [LIVE]
- Miami-Dade code liens with folio and OR book/page — [ArcGIS layer](https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/CodeComplianceViolation_Lien_View/FeatureServer/0) [LIVE]
- LA County Secured Defaulted Tax Roll, 1.75M rows — [ArcGIS layer](https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/Secured%20Defaulted%20Tax%20Roll/FeatureServer/0) [LIVE]
- LA County Liens Secured Tax Roll, 2.43M rows — [ArcGIS layer](https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/Liens%20Secured%20Tax%20Roll/FeatureServer/0) [LIVE]
- Louisville Metro foreclosures — [ArcGIS layer](https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/Louisville_Metro_KY_Property_Foreclosures/FeatureServer/0) [LIVE]
- Louisville lien final orders — [ArcGIS layer](https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/lien_notification_final_orders/FeatureServer/0) [LIVE]
- Maricopa lien and delinquent parcels — [ArcGIS layer](https://services.arcgis.com/ykpntM6e3tHvzKRJ/arcgis/rest/services/ParcelLienDelinquent/FeatureServer) [LIVE]
- Philadelphia tax balances, 1972–2016, with lien_number — [Carto SQL API](https://phl.carto.com/api/v2/sql?q=SELECT%20*%20FROM%20real_estate_tax_balances%20LIMIT%205) [LIVE]
- Norfolk delinquent taxes — [data.norfolk.gov](https://data.norfolk.gov/d/7qie-z5gv) [CATALOG]
- Richmond delinquent taxes — [data.richmondgov.com](https://data.richmondgov.com/d/83t5-hbac) [CATALOG]
- Clermont County delinquent taxes and special assessments — [catalog](https://datacatalog.cookcountyil.gov/api/catalog/v1?ids=q52y-wzm4&ids=77ey-nevf) [CATALOG]
- Milwaukee delinquent RE tax accounts, monthly — [data.milwaukee.gov](https://data.milwaukee.gov/dataset/delinquent-real-estate-tax-accounts) [SEARCH]

### Inferences

- Joining by owner name gives the strongest debtor linkage. Detroit Blight Tickets, NOLA adjudication cases, the Baltimore tax-sale lists, Norfolk, Richmond and Clermont all carry the owner's name with a parcel or address.
- Owner on these lists equals debtor. For tax and code liens the owner of record is the liable party, so a name match also confirms that the debtor owns the parcel.
- Feeding the "does the debtor own property with equity" question:
  - The delinquent-tax and tax-defaulted rolls (LA, Maricopa, Norfolk, Richmond, Milwaukee) mainly add **senior liens that reduce equity**. Property-tax liens prime a judgment lien.
  - They are not new judgment debtors.
- Detroit blight judgments and NOLA in-rem code judgments are the only new judgment-like money-debt sources at city scale. Detroit is by far the largest; both are worth loading.
- Most portals that blocked this container are Socrata. Re-running from an unrestricted network would give row counts and samples for the [CATALOG] items. It would also allow fuller checks of Chicago `6br9-quuz`, Milwaukee and Syracuse.

### Gaps

- Many hosts were blocked, so no row counts, licenses or samples are available for Norfolk, Richmond, Chicago, Orlando, Prince George's, King County, Cincinnati, Milwaukee, Syracuse or DC.
- Not determined: whether Detroit DAH judgments attach as liens to the parcel or the tax roll. The same goes for Philadelphia `lien_number` and the Miami-Dade `data_judgement` layer.
- No lis pendens, general civil judgment, or housing-court judgment dataset with names was found on any municipal portal outside NY.
- Water and sewer lien datasets naming owners were not found. Baltimore's tax-sale lists include water liens inside `LIENS`/`total_lien`, but they are not broken out.

## Row counts, update frequency, fields, license and date range

### Takeaway

The ArcGIS-hosted layers have no license field set on the layer. Treat them as public-records data under each city's open-data terms [UNVERIFIED]. NOLA hearings and cases are CC0, and the Clermont, Howard and King County datasets are Public Domain. Frequency is daily for Detroit, NOLA, Miami-Dade, Maricopa and Norfolk, and roughly weekly to monthly elsewhere. Several tax-sale files are stale.

### Cited findings

| Dataset | Rows | Last update | Debtor name | Parcel | Amount | Status/satisfied | License |
|---|---|---|---|---|---|---|---|
| Detroit Blight Tickets [LIVE] | 915,218 | 2026-11-21 | yes (owner) | yes | judgment, balance | payment_status | not set |
| NOLA Adjudication Cases wy29-i338 [LIVE] | 115,036 | 2026-11 daily | yes (26k) | no (address) | UnpaidFees | IsClosed | not set |
| NOLA All Hearings 44ct-56tr [LIVE] | 103,430 | 2026-11 daily | no | GeoPIN | no | Judgment | CC0 |
| NOLA Sheriff Lien Foreclosures [LIVE] | 1,771 | 2018-11 (stale) | defendant | no | sale amount | SaleStatus | not set |
| Baltimore Tax Lien Cert Sale [LIVE] | 43,736 | 2023-06 (stale) | yes | block/lot | yes | redemption date | not set |
| Miami-Dade Code Lien View [LIVE] | ~7,000 | 2026-11-22 | no | folio | no | satisfied/cancelled | not set |
| LA Co Secured Defaulted Roll [LIVE] | 1,746,758 | 2026-11-16 | no | AIN | redemption amount | redemption date | not set |
| LA Co Liens Secured Roll [LIVE] | 2,427,192 | 2026-11-16 | no | parcel | per lien | — | not set |
| Maricopa Delinquent/Unsold Lien [LIVE] | 34,594 / 1,455 | 2026-11-22 | no | APN | no | — | not set |
| Louisville Foreclosures [LIVE] | 3,624 | 2026-09-24 | case style | partly | sale price | sale date | not set |
| Philadelphia Tax Balances [LIVE] | 683,926 | periods to 2016 (stale) | yes | OPA | yes | — | not checked |
| Norfolk Delinquent Taxes [CATALOG] | ? | 2026-11-22 | yes | PIN | yes | — | none listed |
| Richmond Delinquent RE [CATALOG] | ? | 2026-08-31 | yes | property code | yes | — | none listed |
| Clermont Delinquent / Special Assessments [CATALOG] | ? | 2026-11-22 | yes | yes | yes | — | Public Domain |
| Cook Tax Sale 55ju-2fs9 [CATALOG] | ? | 2016-12 (stale) | buyer only | PIN | yes | sold | none listed |

Sources are the layer URLs listed in the first section.

### Inferences

- If data must be current, drop these stale sets or treat them as history only: Baltimore (2023), NOLA sheriff sales (2018), Cook tax sale (2016), Philadelphia balances (2016), Wayne 2017 auction and D3 2002–2013.

### Gaps

- The Detroit `judgment_date` field could not be filtered with `IS NOT NULL` (a date-only type error), so the count of rows with a judgment date is unknown. The row-level date range runs at least 2005–2026.

## Legal lien on real property, or just a fine/violation record?

### Takeaway

These records have **legal lien effect on the parcel**:
- Tax-delinquency, defaulted-roll and tax-sale datasets: LA County, Maricopa, Baltimore, Norfolk, Richmond, Clermont, Philadelphia and Cook. These are statutory tax liens.
- Miami-Dade recorded code liens, which cite the OR book and page.
- NOLA lien foreclosures and in-rem code judgments.
- LA County special-assessment liens.

These are **judgments, but their lien status is unverified**:
- Detroit blight tickets.
- Louisville final orders and lien foreclosures.

These are **violation or registration records only**, not liens:
- Philadelphia violations, Orlando code cases, foreclosure registries (Chicago, LA City, Prince George's, Cincinnati), and Maryland evictions.

### Cited findings

- Miami-Dade lien rows carry `LN_RECBOOK`, `LN_RECPAGE` and `LN_RECDATE` and statuses "Lien Satisfied" and "Lien Cancelled". These show the liens are recorded in Official Records — [layer](https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/CodeComplianceViolation_Lien_View/FeatureServer/0) [LIVE]
- NOLA code-enforcement cases close "when the in rem judgement is paid and violations are abated" — [data.gov listing](https://catalog.data.gov/dataset/code-enforcement-active-pipeline) [SEARCH]
- NOLA lien foreclosures appear as City of New Orleans v. owner sheriff sales — [d52w-8nva](https://data.nola.gov/d/d52w-8nva) [LIVE]
- Detroit: blight tickets "are adjudicated as civil cases by the Department of Appeals and Hearings" — [layer description](https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/blight_tickets/FeatureServer/0) [LIVE]
- Baltimore tax sale is a "tax lien certificate sale" of delinquent property taxes — [layer description](https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services/Tax_Lien_Certificate_Sale_Properties1/FeatureServer/0) [LIVE]
- Cook annual tax sale: "The buyer is buying a tax lien on the property not the property itself" — [Cook catalog](https://datacatalog.cookcountyil.gov/d/55ju-2fs9) [CATALOG]
- Norfolk's list "does not include nuisance abatement liens" and disclaims use for title — [catalog](https://data.norfolk.gov/d/7qie-z5gv) [CATALOG]

### Inferences

- For the product, tax liens and special-assessment liens are senior encumbrances, used to net down equity. Detroit and NOLA judgments are debtor-side money judgments, used to find debtors and to compete with our lien.

### Gaps

- Not verified: whether unpaid Detroit DAH judgments are recorded or tax-rolled as liens; Michigan law and Detroit's ordinance were not checked.
- Not checked: the Louisville code-lien statute (KRS 65.8835) and whether Philadelphia's `lien_number` is a docketed municipal claim.
