# Recorded-instrument sources: free bulk, state by state

Researched 2026-11-21. The goal is free bulk data on recorded real-estate instruments (deeds,
mortgages and deeds of trust, satisfactions and releases, liens, lis pendens). The business use is
estimating the mortgage balance behind a judgment lien, which tells us how much equity is left.

"Free bulk" here means downloadable files, an open-data portal (Socrata, ArcGIS, CKAN), a published
index file, or an official API whose terms allow automated use. Recorder search sites, logins,
paywalls and purchases are out of scope.

Already loaded, so not repeated below: NYC ACRIS (all document types), Philadelphia real estate
transfers (Carto), Hillsborough FL Official Records daily index.

## How each item was checked

- **Verified**: the metadata or column list was read from the live portal API in this session
  (Socrata `api/views/<id>.json` or `api/catalog/v1`, the ArcGIS REST `?f=json` field list, or the
  CKAN `package_show`), or the download page was read directly.
- **Search only**: seen in web-search results; the portal itself was not read.
- **Unverified**: from search snippets that conflict or are thin, or from prior knowledge. Check
  before building a loader.

Many hosts were blocked by this session's network allowlist. Those are listed with each source and
in the load-first list, so they can be allowed before loading.

## The main finding

No state has a free, statewide index of recorded **mortgages** with amounts and names. These are
the only free bulk sources found that carry a **mortgage amount** tied to a property:

1. **Maryland SDAT** real-property file on opendata.maryland.gov. It holds the last three transfers
   per parcel, each with grantor name, consideration, **mortgage amount**, transfer date and deed
   liber/folio. It covers the whole state and is public domain.
2. **Illinois PTAX-203** transfer declarations, statewide since 2013 and updated weekly. They give
   buyer and seller names, full consideration, and line 15, the outstanding mortgage the buyer
   **assumes**. This is not new purchase-money financing. The Cook County supplemental form
   dataset has a `county_form_mortgage_amount` field; what that field means is unverified.
3. **Cook County Recorder** mortgages, foreclosures and quit-claim deeds, 2011 to March 2015 only,
   with consideration amounts. The data is old and has no party names.
4. **NYC ACRIS**, already loaded.

Everywhere else, free bulk data stops at **deed-level sales**: grantor, grantee, price and
book/page. That is still useful, because a sale gives a ceiling on the original loan and a start
date for amortization. HMDA and the other federal files have loan amounts but no names or
addresses, so they cannot be joined to a particular lien (see the Federal section).

## Summary table

Abbreviations: G/G = grantor/grantee names; Mtg$ = mortgage amount; ND = non-disclosure state
(sale prices are not public by law or practice).

| State | Best free bulk source | Document types | Coverage | Verdict |
|---|---|---|---|---|
| AL | None found | n/a | n/a | No |
| AK | None found (ND) | n/a | n/a | No |
| AZ | None. Maricopa Recorder has no public bulk feed; the Assessor's API needs a token. | n/a | n/a | No |
| AR | None found | n/a | n/a | No |
| CA | None statewide. SF recorded documents need registration. The MTC "Parcel" dataset has lender and price fields but no stated license. | (sales, lender) | Bay Area, unverified | No (CA); MTC unverified |
| CO | Adams County Property Sales; Douglas County Property Sales Data (ArcGIS) | Deeds/sales: G/G, price, deed type, book/page, reception number | 2 counties | Yes (county) |
| CT | data.ct.gov Real Estate Sales 2001-2024 (no names) plus statewide Parcel & CAMA 2026 (last sale G/G, price, book/page) | Sales | Statewide | Yes |
| DE | None found | n/a | n/a | No |
| DC | None. The Recorder of Deeds search site is privately run and has no bulk feed. | n/a | n/a | No |
| FL | Broward daily Official Records index extract (pipe-delimited). Whether it is free is unconfirmed. Hillsborough is already loaded. | Index of all OR doc types | Broward | Unverified |
| GA | None. The GSCCCA deed and PT-61 indexes are subscription only. | n/a | n/a | No |
| HI | None. Bureau of Conveyances access is paid. A Maui "Sales" ArcGIS layer exists but its fields were not checked. | (sales) | Maui | Unverified |
| ID | None found (ND) | n/a | n/a | No |
| IL | **IDOR PTAX-203** (statewide); **Cook Assessor Parcel Sales**; Cook Recorder 2011 to 2015 mortgages | Deeds: G/G, consideration, assumed mortgage; Cook mortgages 2011 to 2015 | Statewide since 2013; Cook since 1999 | **Yes** |
| IN | STATS Indiana Sales Disclosure Form database | Sales: buyer, seller, price; mortgage Y/N (loan amount unverified) | Statewide | Yes (fields partly unverified) |
| IA | None statewide found | n/a | n/a | No |
| KS | None found (sale prices largely confidential) | n/a | n/a | No |
| KY | None. Jefferson PVA sales reports are paid. | n/a | n/a | No |
| LA | East Baton Rouge tax roll (instrument type, transfer date, conveyance number; no price) (ND) | Transfer references | EBR Parish | Partial |
| ME | None found | n/a | n/a | No |
| MD | **opendata.maryland.gov SDAT Real Property (`ed4q-f8tm`)** | Last 3 transfers: grantor, consideration, **Mtg$**, date, liber/folio | Statewide | **Yes** |
| MA | None. MassLandRecords is search only. Cambridge has old historical grantee and price tables. | (sales) | Cambridge, historical | No |
| MI | Detroit Property Sales (ArcGIS) | Sales: G/G, price, liber/page, instrument | Detroit, 2011 on | Yes (city) |
| MN | None bulk. The eCRV public search is per query and the eCRV download API is for local governments only. | n/a | n/a | No |
| MS | None found (ND) | n/a | n/a | No |
| MO | St. Louis City property sales dataset (fields unverified) (ND) | (sales) | St. Louis City | Unverified |
| MT | None found (ND) | n/a | n/a | No |
| NE | Lancaster County Property Sales tables 2013 to 2017 (fields unverified) | (sales) | Lancaster | Unverified |
| NV | None. Clark County Recorder FTP is paid. | n/a | n/a | No |
| NH | None found | n/a | n/a | No |
| NJ | **NJ Treasury SR-1A sales files** | Deeds: grantor and grantee names and addresses, reported and verified price, deed book/page/date | Statewide, yearly 2020 on plus year to date | **Yes** |
| NM | None found (ND) | n/a | n/a | No |
| NY | ACRIS (loaded). NYC HPD LL7 Qualified Transactions (grantee, price). ORPTS SalesWeb is a per-search export, not bulk. | Sales | NYC | Yes (NYC) / No (rest of state) |
| NC | Wake County real estate data file (daily; ownership, sale, deed book/page) | Sales | Wake | Yes (search only) |
| ND | None found (ND) | n/a | n/a | No |
| OH | Franklin County Auditor anonymous FTP (contents unverified); Cuyahoga transfers via NEOCANDO (access unverified) | (transfers) | 2 counties | Unverified |
| OK | None found | n/a | n/a | No |
| OR | None found | n/a | n/a | No |
| PA | Allegheny County Property Sale Transactions (WPRDC, CC0; names removed by ordinance). Philadelphia is loaded. | Deeds: price, deed book/page, instrument type | Allegheny, 2013 on | Yes (no names) |
| RI | None found | n/a | n/a | No |
| SC | None found | n/a | n/a | No |
| SD | None found | n/a | n/a | No |
| TN | None bulk. TPAD exports are per search; Comptroller GIS parcel shapefiles' sale fields unverified. | n/a | n/a | No |
| TX | None from county clerks; Harris County Clerk bulk data is paid (ND). Appraisal-district sales tables such as Williamson CAD give instrument numbers. | (CAD sales refs) | Williamson | Partial |
| UT | None. Salt Lake Recorder Data Services is paid (ND). | n/a | n/a | No |
| VT | Vermont Tax Dept weekly public Property Transfer Tax data | Transfers: buyer, seller, price | Statewide | Likely yes (unverified) |
| VA | Norfolk Property Assessment and Sales (daily; G/G, consideration, document number). Fairfax sales table has price and book/page but no names. | Sales | Norfolk; Fairfax | Yes (city) |
| WA | King County Assessor data download, real property sales extract (unverified) | Sales: buyer, seller, price, excise number | King | Unverified |
| WV | See `wv-state-federal.md`; no recorder bulk source | n/a | n/a | No |
| WI | DOR RETR historical monthly files (5 years). The system moved to My Tax Account in Jan 2026; name fields unverified. | Transfers | Statewide | Likely yes (unverified) |
| WY | None found (ND) | n/a | n/a | No |

## Per-state notes

### Illinois (best overall)

- **PTAX-203, 203-A and 203-B** (Illinois Department of Revenue). Verified in the Socrata catalog.
  - URL: https://illinois-edp.data.socrata.com/d/it54-y4c6
  - Contents: every real estate transfer declaration filed since 2013-01-01. Buyer and seller
    names (`step_4_buyer_name`, `step_4_seller_name`, plus organization fields), primary PIN,
    address, `date_recorded`, `document_number`, instrument type and date,
    `line_11_full_consideration`, and `line_15_outstanding_mortgage` (a mortgage the buyer
    assumes). It also has sale-condition flags such as bank REO, short sale, court-ordered sale and
    sale in lieu of foreclosure, and the legal description.
  - Companion datasets:
    - `dwt7-rycp`: additional buyers.
    - `rzbz-mw8b`: additional sellers.
    - `vbnw-q5s8`: Cook County and Chicago supplemental forms. It includes
      `county_form_mortgage_amount`, whose meaning is unverified.
  - Format: Socrata (CSV, JSON, SODA API). Updated weekly.
  - License: Public Domain.
  - Host `illinois-edp.data.socrata.com` was blocked in this session.
  - Verdict: free bulk, yes. Statewide.
- **Cook County Assessor: Parcel Sales** (`wvhk-k5uv`). Verified.
  - URL: https://datacatalog.cookcountyil.gov/d/wvhk-k5uv
  - Contents: 2.69M rows. PIN, `sale_date`, `sale_price`, `doc_no` (Clerk document number),
    `deed_type`, `seller_name`, `buyer_name`, plus multi-sale and filter flags.
  - Coverage: earliest date 1971, though the county documents it as 1999 to present. Latest sale
    2026-09-15.
  - Format: Socrata. Updated about weekly. No license is stated on the dataset; the portal terms
    apply.
- **Cook County Recorder of Deeds, 2011 to March 27, 2015.** Verified.
  - `4f2q-h3b7` (2013 to 2015, 511k rows, Public Domain) plus yearly sets: `33fu-uwca`,
    `myuk-usmm`, `epxa-9ihc`, `9br9-dhca`, `dskn-nj3p`, `687c-wufc`.
  - Contents: mortgages, foreclosures (lis pendens) and quit-claim deeds. PIN, document number and
    type, recorded and execution dates, `consideration_amount` (the mortgage amount, for
    mortgages), and address. No names.
  - Inactive since 2015. Useful only for mortgages from that era.
- **Clerk recordings now**: the Cook County Clerk sells "transfer data" under a license agreement
  (cookcountyclerkil.gov/publication/transfer-data-license-agreement). Not free.
- **Macoupin County** (`data.macoupincountyil.gov`): recorded mortgages, foreclosures and quit-claim
  deeds for 2015 only. Tiny and historical.
- **Lake County**: an ArcGIS Hub item titled "Deeds, Mortage Documents, and Other Recorded
  Documents" (catalog.data.gov). It is a "documents" item, probably a link to the search site.
  Unverified, probably not bulk.

### Maryland (only free statewide mortgage amounts)

- **Maryland Real Property Assessments: Hidden Property Owner Names** (`ed4q-f8tm`). Verified
  column list.
  - URL: https://opendata.maryland.gov/d/ed4q-f8tm
  - Publisher: SDAT and the Maryland Department of Planning.
  - Contents: one row per parcel. Sales segments 1 to 3 each have grantor name, consideration,
    **mortgage** (SDAT fields 92, 112 and 132), transfer date, how conveyed, transfer number, and
    grantor deed liber/folio. Current deed liber/folio is also included. Current owner names are
    hidden in this version; the grantor on the next sale, or other loaded parcel data, can fill
    that in.
  - Documentation PDF is linked from the dataset page.
  - License: Public Domain. Refresh frequency differs from SDAT's own products (see metadata).
  - The exact meaning of the "mortgage" field (amount reported on the deed intake sheet?) still
    needs checking against the documentation PDF.
  - Host `opendata.maryland.gov` was blocked in this session.
- **SDAT Real Property Sales File**: sold through SpecPrint. Not free.
- The SDAT search site forbids automated collection.

### New Jersey

- **SR-1A sales files** (NJ Division of Taxation). Verified on the download page and the layout
  PDF.
  - URL: https://nj.gov/treasury/taxation/lpt/statdata.shtml
  - Files: `statdata/Sales2020.zip` through `Sales2026.zip`, plus `YTDSR1A2027.zip` (2025 file is
    about 11 MB).
  - Layout: https://nj.gov/treasury/taxation/pdf/lpt/SR1Afilelayout.pdf. Fields include grantor
    and grantee name, street, city/state and ZIP; reported and verified sales price; deed book,
    page and date; block/lot; assessed values; usable/non-usable code with reasons 01 to 33.
  - No mortgage data.
  - The same page has the MOD-IV assessment files (`modiv-2021` to `modiv-2026.zip`).
  - Fixed-width text. Updated yearly, plus a running year-to-date file. Public state download with
    no login.
  - Verdict: free bulk, yes.

### Connecticut

- **Real Estate Sales 2001-2024 GL** (`5mzw-sjtu`). Verified.
  - Fields: serial number, list year, date recorded, town, address, assessed value, sale amount,
    sales ratio, property type, non-use code, remarks. No names.
  - Sales of $2,000 or more, October to September years. Public Domain.
- **2026 Connecticut Parcel and CAMA Data** (`ibe8-9i3q`; earlier years `rny9-6ak2`, `pqrn-qghw`,
  `ezgm-i4uu`). Verified.
  - Statewide, 1.36M parcels. Owner and mailing address, `sale_grantor_name`,
    `sale_grantee_name`, `sale_price`, `sale_date`, `book_page`, `instrument`, plus prior sale
    price, date and book/page.
  - Holds only the latest and prior sale per parcel. Dates are text and messy.
  - No license field; the data.ct.gov terms apply.
- **UCC Lien Filings** (`xfev-8smz`): secured-party liens on personal property, not real estate.
- `data.ct.gov` works through curl here, but WebFetch was refused.

### Pennsylvania

- **Allegheny County Property Sale Transactions** (WPRDC). Verified with the CKAN API.
  - URL: https://data.wprdc.org/dataset/real-estate-sales
  - Contents: 508,658 rows in the main resource. PARID, address, record date, sale date, price,
    deed book/page, sale code and description, instrument type.
  - **Buyer and seller names are removed** because of County Ordinance 3478-07.
  - Monthly, 2013 on, plus yearly files. License CC0.
- **Philadelphia**: already loaded.
- No other county open-data deed sets were found (Montgomery, Chester, Lancaster and Bucks were
  searched).

### Michigan

- **Detroit Property Sales**. Verified field list.
  - URL: https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/assessor_property_sales_view/FeatureServer/0
  - Also on detroitdata.org.
  - Contents: 545k rows. `grantor`, `grantee`, `amt_sale_price`, `sale_date`, `liber_page`,
    `sale_instrument`, `term_of_sale`, verification, parcel. Coverage 2011 on; some dates are bad,
    up to 2206.
  - Detroit open-data terms apply.

### Colorado

- **Adams County Property Sales**. Verified field list.
  - URL: https://services3.arcgis.com/4PNQOtAivErR7nbT/arcgis/rest/services/Property_Sales/FeatureServer/0
  - Contents: 771k rows. Grantor, grantee, sale date, sale price, deed type, book/page, reception
    number, documentary fee.
- **Douglas County Property Sales Data**. Verified field list.
  - URL: https://services.arcgis.com/seTexOicoRXDvRsJ/arcgis/rest/services/OpenData/FeatureServer/7
  - Contents: 687k rows. Grantor, grantee, sale price and date, deed type, book/page, recording
    number. Refreshed by ETL to 2026-11.
- Colorado's documentary fee gives a check on the price. Denver open data was not confirmed.

### Virginia

- **Norfolk Property Assessment and Sales FY27** (`qva7-tzrf`). Verified in the Socrata catalog.
  - Contents: owner, grantor, grantee, consideration, transfer date, document number. Updated
    daily. Earlier fiscal-year snapshots exist.
  - Host `data.norfolk.gov` was blocked in this session.
- **Fairfax County, Tax Administration's Real Estate - Sales Data**. Verified.
  - URL: services1.arcgis.com/ioennV6PpG5Xodq0, OpenData_A5 layer 1
  - Contents: PARID, sale date, price, book/page, validity. No names.
- Arlington "property sale history" appears on catalog.data.gov. Unverified.

### Indiana

- **Sales Disclosure Form database** (DLGF and IBRC).
  - URL: https://www.stats.indiana.edu/topic/sdf.asp
  - Contents: parcel, address, seller, buyer, sale price and other form fields. Phone numbers and
    emails are withheld. The form asks about mortgage financing and loan amount; whether the
    public file carries the loan amount is **unverified**.
  - Prior years statewide; the current year is partial and updated weekly (Fridays).
  - Zipped tab-delimited files (2021 on) or pipe-delimited files (older).
  - Search only. Host `www.stats.indiana.edu` was blocked in this session.

### Vermont

- **Weekly public Property Transfer Tax data**.
  - URL: https://tax.vermont.gov/data-and-statistics/ptt
  - The files are laid out to match forms PTT-172 and PTT-175 (buyer and seller, price, parcel,
    acres). The data sits on a separate, possibly third-party, host; the hostname is unverified.
  - The format changed in 2020.
  - Search only. data.vermont.gov holds only town and county aggregates (`86s3-34zj`,
    `ds3p-x2cx`).

### Wisconsin

- **RETR historical data**.
  - URL: https://revenue.wi.gov/Pages/ERETR/data-home.aspx
  - Monthly downloads, 5 years. The system moved into My Tax Account on 2026-01-12; whether the
    bulk download still exists without a login is **unverified**.
  - The data dictionary shows grantor state and ZIP; grantor and grantee name columns are
    unconfirmed.

### Washington

- **King County Assessor data download**.
  - URL: https://info.kingcounty.gov/assessor/DataDownload/default.aspx
  - The real property sales extract (`EXTR_RPSale`) is believed to carry seller and buyer names,
    sale price, excise tax number and recording number. This is from prior knowledge and the
    search did not confirm it, so it is **unverified**.
  - Host was blocked in this session.
- WA DOR publishes only blank REET forms and distribution totals. No statewide affidavit data.

### Minnesota

- **eCRV**: the data is public by statute, but:
  - The web-services download returns at most 100 records per request and only for the user's own
    local government.
  - The public eCRV search (ecrvsearch.revenue.mn.gov) is a per-query site, which is out of scope.
- DOR annual sales listings exist; whether they carry names is unverified.
- Hennepin publishes yearly sales feature services on services.arcgis.com/afSMGVsC7QlRK1kZ (fields
  unverified).
- Verdict: no free statewide bulk.

### Massachusetts

- MassLandRecords.com is search only, with per-document baskets. No bulk export was found; a WPI
  study got registry data only by request.
- MassGIS parcels carry last-sale price, date and book/page (prior knowledge, unverified).
- Cambridge has FY2015 and FY2016 assessor tables with up to six prior sales (grantee and price).

### Florida

- **Broward**: "Daily Index Extract Files", pipe-delimited, kept 7 to 10 days.
  - URL: https://www.broward.org/RecordsTaxesTreasury/Records/Pages/IndexFiles-Completed.aspx
  - Whether these are free is **unverified**: the fee schedule lists $30 for an index CD, and the
    page wording suggests a public download.
  - If free, it is the same kind of source as the Hillsborough loader and needs a daily pull.
- Miami-Dade ($110 per folder per month), Palm Beach (subscriber FTP) and Lake ($800 a year) are
  paid.

### Texas, Utah and other non-disclosure states (AK, ID, KS, LA, MS, MO, MT, NM, ND, WY)

- Sale prices are not public, so even deed indexes carry no amounts.
- Harris County Clerk sells index and image bulk data.
- Williamson CAD (`data.wcad.org`) publishes sales tables with instrument numbers and dates.
- East Baton Rouge's tax roll (`data.brla.gov` `myfc-nh6n`) has conveyance instrument numbers.

### Remaining states

- **North Carolina**: the Wake County real estate data file is a free daily full parcel file with
  ownership, sale and deed book/page (search only).
  - URL: https://www.wake.gov/departments-government/tax-administration/data-files-statistics-and-reports/real-estate-property-data-files
- **Ohio**:
  - The Franklin County Auditor's anonymous FTP (apps.franklincountyauditor.com) is free, but
    whether it holds transfer files is unverified.
  - Cuyahoga transfers since 1975 are in NEOCANDO (Case Western); public access terms are
    unverified.
  - Clermont Auditor has a Socrata parcel table with sale price.
- **New York (outside NYC)**: ORPTS SalesWeb has 10 years of RP-5217 data, but only as a
  per-search Excel export. Not bulk; verdict no.
  - NYC HPD "Local Law 7-2018 Qualified Transactions" (`8wi4-bsy4`) has grantee, price and CRFN for
    rent-regulated buildings.
- **California**:
  - MTC/ABAG "Parcel" (`data.bayareametro.gov` `yspg-yqv7`) has `lender`, `price`, `priorprice`
    and `deedtype`. It looks vendor-derived and has no license, so do not load it without checking
    the terms.
  - SF recorded documents need an identity-verified registration, which is out of scope.
- **Georgia**: GSCCCA (deeds, liens, PT-61) needs a paid subscription.
- **Nevada**: Clark County recorder index FTP is paid.
- **Kentucky**: Jefferson PVA sales reports are paid.
- **Tennessee**: TPAD exports are per search. The Comptroller GIS parcel shapefiles' sales columns
  are unverified.
- **Hawaii**: a Maui "Sales" layer on ArcGIS exists (fields unverified).
- **Nebraska**: Lancaster County Property Sales 2013 to 2017 tables (fields unverified).
- **Missouri**: St. Louis City "Property Sales" dataset (stlouis-mo.gov/data, fields unverified).
- **No source found** in AL, AR, DE, ME, NH, OK, OR, RI, SC, SD.

## Federal sources (none can name a borrower or a property)

| Source | URL | What it gives | What it cannot give | Verdict |
|---|---|---|---|---|
| HMDA public LAR (CFPB/FFIEC) | ffiec.cfpb.gov/data-publication | Loan-level originations and applications yearly: lender (LEI), loan amount (midpoint of a $10k band), rate, LTV and DTI bands, census tract, loan purpose and lien status | No borrower name, no property address, no loan id, no application date. Cannot be joined to a recorded mortgage except by fuzzy matching on lender, tract, year and amount band. | Free bulk yes; no names |
| FHFA Enterprise Public Use Database | fhfa.gov/data/public-use-database | Fannie/Freddie loan-level purchases, tract file and national file | No location in the national file; tract only in the other; no names | Free bulk yes; no names |
| FHFA NSMO public use file / NMDB aggregates | fhfa.gov/nsmo | Survey and aggregate performance | Sample-based; no geography finer than broad areas | Free; not usable per lien |
| Fannie Mae / Freddie Mac single-family loan performance | capitalmarkets.fanniemae.com, freddiemac.com/research/datasets/sf-loanlevel-dataset | Monthly balance and performance by loan | Needs registration and login (excluded); 3-digit ZIP only | Excluded (login) |
| HUD FHA Single Family Portfolio Snapshot | hud.gov (also DataLumos E220223) | Monthly loan-level FHA endorsement records | Field list (ZIP, amount, mortgagee) unverified; no borrower names | Free; unverified fields |
| Freddie Mac PMMS | freddiemac.com/pmms | Weekly average 30- and 15-year rates since 1971 | Not loan data | Free; use for amortization |

**How these fit the equity estimate**: no federal file gives a payoff for a named debtor. The
practical estimate is:

1. Take the original amount and date of each mortgage from MD SDAT, ACRIS, IL PTAX, the Cook
   Recorder 2011 to 2015 data, or a recorded index.
2. If the amount is missing, use the sale price times a typical LTV from HMDA for that tract, year
   and lender.
3. Amortize at the PMMS rate for that month.
4. Treat a recorded satisfaction or release as a zero balance.

An exact payoff needs a lender payoff statement, which is not public.

## Load-first list (ranked)

Ranked by value for mortgage balances, then by coverage, then by effort.

| # | Source | Why first | Hostnames to allow |
|---|---|---|---|
| 1 | MD SDAT Real Property `ed4q-f8tm` | Only statewide free file with mortgage amounts and grantor names; public domain | `opendata.maryland.gov` |
| 2 | IL IDOR PTAX-203 `it54-y4c6` (+ `dwt7-rycp`, `rzbz-mw8b`, `vbnw-q5s8`) | Statewide, weekly, names and consideration, assumed mortgage, distress flags (REO, short sale, in lieu of foreclosure) | `illinois-edp.data.socrata.com` |
| 3 | NJ SR-1A yearly and year-to-date zips | Statewide grantor/grantee with addresses and deed book/page | `nj.gov` (reachable now) |
| 4 | Cook Assessor Parcel Sales `wvhk-k5uv` + Cook Recorder 2011 to 2015 mortgage sets | Buyer and seller names back to 1999; historical mortgage amounts | `datacatalog.cookcountyil.gov` (reachable now) |
| 5 | CT Parcel & CAMA 2026 `ibe8-9i3q` + Real Estate Sales `5mzw-sjtu` | Statewide last sale with G/G and book/page; 2001 to 2024 price history | `data.ct.gov` (reachable by curl) |
| 6 | Detroit, Adams CO and Douglas CO sales layers | G/G and price with book/page or reception number; ArcGIS REST | `services2.arcgis.com`, `services3.arcgis.com`, `services.arcgis.com` (reachable now) |
| 7 | Allegheny WPRDC sales | Price, deed book/page, instrument type (no names) | `data.wprdc.org` (reachable now) |
| 8 | Norfolk VA sales `qva7-tzrf` | G/G, consideration, document number, daily | `data.norfolk.gov` |
| 9 | Indiana SDF (STATS Indiana) | Statewide buyer/seller/price; check for a loan amount field | `www.stats.indiana.edu` |
| 10 | Vermont weekly PTT | Statewide buyer/seller/price | `tax.vermont.gov` + the data host it links to (unverified) |
| 11 | Broward daily index extract (if free) | Recorded mortgages, satisfactions, lis pendens, liens daily, like Hillsborough | `www.broward.org` |
| 12 | Wake NC data file; King WA sales extract; WI RETR | County or state sales with names (each needs a field check) | `www.wake.gov`, `info.kingcounty.gov`, `revenue.wi.gov` |
| 13 | HMDA LAR (for LTV priors only) | Typical loan-to-price by tract, year and lender | `ffiec.cfpb.gov`, `s3.amazonaws.com` (CFPB file host; unverified) |
| 14 | Freddie Mac PMMS | Rate series for amortization | `www.freddiemac.com` |

Hostnames confirmed blocked in this session: `opendata.maryland.gov`,
`illinois-edp.data.socrata.com`, `data.norfolk.gov`, `www.stats.indiana.edu`, `tax.vermont.gov`,
`www.broward.org`, `www.wake.gov`, `info.kingcounty.gov`, `revenue.wi.gov`, `ffiec.cfpb.gov`,
`www.fhfa.gov`, `catalog.data.gov`, `data.kingcounty.gov`, `opendata.dc.gov`.

## Search method (for repeat runs)

- **Socrata**: the federated discovery endpoint answers on any Socrata domain, for example
  `https://datacatalog.cookcountyil.gov/api/catalog/v1?q=<term>&only=dataset&limit=100`. It returns
  domain, id, name, update date and column field names, so cross-domain searches work even when
  the target domain is blocked. Terms used: recorded documents, official records, register of
  deeds, lis pendens, mortgage, grantor, grantee, deed, conveyance, transfer tax, lender, mortgage
  amount, sales disclosure.
- **ArcGIS Hub**: `https://hub.arcgis.com/api/v3/search?q=<term>`, then each layer's `?f=json`
  for its fields.
- **CKAN (WPRDC)**: `/api/3/action/package_show` and `datastore_search`.
