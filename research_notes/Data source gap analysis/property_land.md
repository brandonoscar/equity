# Property and land data gaps, and the best free bulk sources to fill them

Researched 2026-11-23. Scope: parcels/ownership, recorder indexes, mechanic's liens, building permits, nationwide. Baseline read first: `docs/coverage.md`, `docs/gaps.md`, `docs/parcel-catalog/*.md`, `docs/sources/recorder-sources.md`, `reports/Recorder data records laws by state.md`, `config/{states,counties,bulk,recorders}`.

**Tags.** [LIVE] = I read the service's field list and/or row count (ArcGIS `?f=json` + `returnCountOnly`, Socrata `api/views/<id>.json` or `api/catalog/v1`, CKAN `package_show`/`datastore_search`, or an HTTP HEAD/download of the file) on 2026-11-23. [SEARCH] = seen in web-search results only. [UNVERIFIED] = thin/conflicting snippets or prior knowledge. "Usable" means free + bulk + no login. A [LIVE] REST layer is usable for bulk only by paging (`resultOffset`, maxRecordCount 1000-2000); none of the terms of use below were read unless stated, and "public" is not a commercial-use licence.

**Baseline (from `docs/coverage.md`, which already includes `il.cook.parcels` and `la.orleans.parcels`).** No adapter: MT, NV. Adapter but no owner names: CA, DE, HI, IN, MD, NE, NH, NJ, RI, TN, UT, WA. OH has owners but no values; AZ, KS, ME, SD have owners but no values. Only some counties covered: AL (Jefferson, Madison), AK (Anchorage, Fairbanks, Kenai), AZ (6 counties, no Maricopa or Yavapai), CA (LA, Riverside, San Bernardino; no owners), GA (Cobb, DeKalb, Fulton, Gwinnett), IA (Black Hawk, Johnson, Linn, Scott; no Polk), IL (Cook, DuPage, Lake), KS (Douglas), KY (Boone), LA (East Baton Rouge, Orleans), MI (Macomb, Oakland, Wayne), MO (Jackson, St. Louis County), NM (Dona Ana, Sandoval), OK (Canadian, Oklahoma, Tulsa), OR (Deschutes, Jackson, Marion), SC (Charleston, Greenville), SD (Lincoln), VA (Alexandria, Chesterfield, Loudoun, Prince William, Richmond City). Recorder indexes loaded: `fl.hillsborough.or`, `fl.hernando.or`, `fl.putnam.or`, `ny.nyc.acris`, `pa.philadelphia.rtt`.

## 1. Parcels and ownership: what is missing per state, and the best free source to fill each gap

### Takeaway
Six [LIVE] public layers close the biggest gaps: Maricopa Assessor (1.76M parcels: owner, mailing address, full cash value, last deed and sale), Tennessee's statewide "Public Use" layer (2.14M parcels in 86 counties, with owner names), Montana's cadastral framework on ArcGIS Online (921k parcels: owner and value), SanGIS (1.09M San Diego parcels with owner names, the first CA owner source found), Clark County NV via the City of Las Vegas (867k rows, owner and mailing address), and King County WA's free assessor CSVs. The assessor's taxpayer file has the names stripped, but the sales file names buyer and seller on every sale. After those come about 25 county layers with owner names, below. Several have use caveats: Montana MCA 2-6-1017, Tennessee's "state agencies with approved access" wording, and Indiana IC 5-14-3-3(f).

### Cited Findings

**Ranked fill list (ranked by parcels covered and by the value of the market; record counts are [LIVE] `returnCountOnly` results)**

| # | Gap | Source (publisher) | Owner? | Value? | Rows | Tag |
|---|---|---|---|---|---|---|
| 1 | AZ Maricopa (no adapter; AZ has no values) | Maricopa County Assessor `https://gis.mcassessor.maricopa.gov/arcgis/rest/services/Parcels/MapServer/0` | Yes: `OWNER_NAME`, `MAIL_ADDR1..`, `INCAREOF` | Yes: `FCV_CUR`, `LPV_CUR`, prior-year FCV/LPV, plus `DEED_NUMBER`, `DEED_DATE`, `SALE_DATE`, `SALE_PRICE` | 1,763,230 (max 1000/page) | [LIVE] |
| 2 | TN owners (statewide adapter has none) | TN Comptroller / STS GIS "Tennessee Property Boundaries Public Use" `https://services1.arcgis.com/YuVBSS7Y1of2Qud1/arcgis/rest/services/Tennessee_Property_Boundaries_Public_Use/FeatureServer/0` | Yes: `OWNER`, `OWNER2` (sample row: Anderson County, owner populated) | No (links to TPAD) | 2,144,655; owners grouped across **86 counties**. Davidson, Shelby, Knox, Hamilton, Rutherford, Williamson, Montgomery, Chester and Hickman do not appear. | [LIVE]. The layer's own description says it is "intended for use by state agencies with approved access", yet it answers without a token. Get a legal read. |
| 3 | TN Davidson (Nashville) | Nashville GIS `https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services/Parcels_view/FeatureServer/0` | Yes: `Owner`, `OwnAddr1-3`, `OwnCity/State/Zip` | `SalePrice`, `OwnDate`, `OwnInstr` (deed instrument) | 287,930 | [LIVE] |
| 4 | MT (no adapter) | Montana Geographic Information (State Library) ArcGIS Online copy of the Cadastral Framework `https://services.arcgis.com/qnjIrwR8z5Izc0ij/arcgis/rest/services/Montana_Cadastral_Framework/FeatureServer/1` | Yes: `OwnerName`, `OwnerAddress1-3`, `OwnerCity/State/ZipCode`, `CareOfTaxpayer` | Yes: `TotalValue`, `TotalLandValue`, `TotalBuildingValue` | 921,278 | [LIVE]. This host is services.arcgis.com, not gisservice.mt.gov. gisservice.mt.gov's robots.txt disallows `/arcgis/*` ([LIVE]), and services.arcgis.com served no robots.txt. The MCA 2-6-1017 distribution-list caveat in `docs/parcel-catalog/states-M-W.md` still applies. |
| 5 | CA owners: San Diego | SD County SanGIS `https://services7.arcgis.com/3kQCXzNCo2WKILzp/arcgis/rest/services/SanGIS_Parcels/FeatureServer/0` | Yes: `OWN_NAME1-3`, `OWN_ADDR1-3` | No value field matched | 1,088,759 | [LIVE] |
| 6 | NV Clark (no adapter) | City of Las Vegas `ADDR_OWN` `https://services1.arcgis.com/F1v0ufATbBQScMtY/arcgis/rest/services/ADDR_OWN/FeatureServer/0`. Fields: TAXDIST, PARCEL, OWNER, ADDRESS1-5. | Yes (`OWNER` + 5 mailing lines) | No | 867,385 | [LIVE]. I infer countywide coverage from the row count and the `TAXDIST` field; not checked. The official Clark Assessor secured roll (AOEXTRACT) is **for purchase**, and the GIS office sells parcels at $2,500 for the county ([LIVE] page read: [Clark Assessor data files](https://www.clarkcountynv.gov/government/assessor/datafiles.php); [SEARCH] GIS price). |
| 7 | WA King (WA has no owners) | King County Assessor free zips: `https://aqua.kingcounty.gov/extranet/assessor/Real%20Property%20Sales.zip` (151 MB) and `.../Real%20Property%20Account.zip` (18.8 MB), `.../Parcel.zip` | Account file is `EXTR_RPAcct_NoName.csv`: **names stripped**, but it keeps mailing address and appraised land/improvement values. Sales file `EXTR_RPSale.csv` has `SellerName`, `BuyerName`, `SalePrice`, `RecordingNbr`, `Volume/Page`, `SaleInstrument`. | Yes (account file) | Files dated 2026-11-20/21 | [LIVE] (downloaded and read the headers). The latest buyer works as an owner proxy. |
| 8 | NV Washoe | Washoe County ArcGIS Online "Nightly_OpenData_Update" layer 1 `https://services.arcgis.com/iCGWaR7ZHc5saRIl/arcgis/rest/services/Nightly_OpenData_Update/FeatureServer/1` | Yes: `FIRSTNAME`, `LASTNAME`, `MAILING1-2`, `MAILCITY/STATE/ZIP` | `SALEDATE`, `SALEPRICE` | 194,398 | [LIVE]. I attribute the org to Washoe County because a washoecounty.gov user publishes in it (Hub search). |
| 9 | IN owners: Marion (Indianapolis) | City of Indianapolis `https://gis.indy.gov/server/rest/services/MapIndy/MapIndyProperty/MapServer/10` | Yes: `FULLOWNERNAME`, `OWNERADDRESS..`, `OWNERZIP` | Yes: `ASSESSORYEAR_LANDTOTAL`, `_IMPTOTAL`, `_TOTALAV` | 347,182 | [LIVE]. The IC 5-14-3-3(f) commercial name/address-list limit noted in coverage.md applies. |
| 10 | UT owners: Utah County | Utah County `https://maps.utahcounty.gov/arcgis/rest/services/Parcels/Parcel_TaxParcels_Simple_wgs84/MapServer/0`. UGRC also hosts `https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Utah/FeatureServer/0` with `OWNERNAME`. | Yes: `OWNER_NAME`, `OWN_FULL_ADDRESS` | Yes: `MKT_LAND_VALUE`, `MKT_IMP_VALUE` | 286,164 | [LIVE] |
| 11 | MD owners | Baltimore City parcels on the State's "ArcGIS Online for Maryland" org `https://services.arcgis.com/njFNhDsUCentVYJW/arcgis/rest/services/Baltimore_City_Parcel_Polygons/FeatureServer/0` (`OWNNAME1/2`, `OWNADD1`); Prince George's County Socrata "Property" `qzrv-2tnv` (`owner_name`, updated 2026-10-27); Baltimore County copy (UMD) `https://services5.arcgis.com/njRHYVhl2CMXMsap/arcgis/rest/services/BaltimoreCountyParcels/FeatureServer/0` (`OWNER_NA1`, `TOTAL_VALU`, 363,145) | Yes | Yes (Baltimore County) | 235,769 / ? / 363,145 | [LIVE]. The statewide `geodata.md.gov` MD_ParcelBoundaries returned HTTP 503. The Socrata Parcel Points `x8a5-h2sy` carries owner *mailing* fields (`ownadd1`, `owncity`, `ownerzip`) but no owner name column ([LIVE]). The `OWNNAME1` field in these State-org copies suggests the iMap source has names; statewide is [UNVERIFIED]. |
| 12 | OR Multnomah / Lane | Multnomah County "Taxlot Parcels" `https://services5.arcgis.com/x7DNZL1YqNQVNykA/arcgis/rest/services/Multnomah_County_Taxlot_Parcels/FeatureServer/0` (`NAME`, `NAME2`; 284,349). The likely Metro RLIS `taxlot` layer `https://services2.arcgis.com/6Miy5NqQWjMYTGFY/arcgis/rest/services/taxlot/FeatureServer/0` has `OWNER1-3`, `TOTALVAL`, `ASSESSVAL` (285,678; publisher unconfirmed). Lane County A&T `https://services5.arcgis.com/W1uyphp8h2tna3qJ/arcgis/rest/services/Taxlots/FeatureServer/0` has `ownname`, `totval`, `assdtotval` (156,960). | Yes | Yes | see left | [LIVE] |
| 13 | NE owners | Douglas County (Omaha) `https://services.arcgis.com/pDAi2YK0L0QxVJHj/arcgis/rest/services/Parcels_for_BOE/FeatureServer/0` (`OWNER_NAME`, owner city/state/zip; 216,645); Sarpy County `https://geodata.sarpy.gov/arcgis/rest/services/Cadastral/LandRecordsSearch/MapServer/5` (`OWNERNME1/2`, `LNDVALUE`, `IMPVALUE`; 77,794) | Yes | Sarpy yes | | [LIVE] |
| 14 | WA Spokane / Snohomish / Clark | Spokane County `https://gismo.spokanecounty.org/arcgis/rest/services/SCOUT/LayersMenu/MapServer/15` (`owner_name`, `taxpayer_*`, `land_value`; 214,835). The Snohomish County Assessor layer `https://services7.arcgis.com/N43GZXnFnEYv2m0v/arcgis/rest/services/Snohomish_County_Parcels/FeatureServer/0` has `OWNERNAME` but only 8,676 rows (partial). Clark County WA "Taxlots for Public Use" has only `MainOwnerID` (no name). The Pierce County Tax_Parcels layer has values but no owner name (only `Business_Name`). | Spokane yes | Spokane yes | | [LIVE] |
| 15 | RI owners: Providence | Providence Socrata "2026 Property Tax Roll" `data.providenceri.gov p9dd-mw2m` (`owner`), with yearly rolls back to 2002 | Yes | Probably (tax roll) | ? | [LIVE] (catalog columns) |
| 16 | VA Norfolk (VA has no Norfolk/Virginia Beach/Fairfax owners) | Norfolk "Property Assessment and Sales FY27" `data.norfolk.gov qva7-tzrf` (owner, grantor, grantee, consideration; updated daily) | Yes | Yes | ? | [LIVE] (catalog columns, updated 2026-11-22) |
| 17 | AZ Yavapai | Yavapai County `https://services1.arcgis.com/BajuNXbtZNiBKFkx/arcgis/rest/services/Parcels_WGS84/FeatureServer/0` (`NAME`; 186,480; last edit about 2025-06). The ADWR per-county layers (`azwatermaps.azwater.gov/.../General/Parcels/MapServer/0-14`) include a **Maricopa layer 7** with `OWNER_NAME` (1,751,155) and Yavapai (13), Gila, Navajo, Apache, Santa Cruz and others. | Yes | No | | [LIVE]. The ADWR use terms remain unread, per coverage.md. |
| 18 | SC York | York County `https://services1.arcgis.com/2AGLxyiJoNiVHKwq/arcgis/rest/services/Parcels/FeatureServer/0` (`Owner1-3`, `AprTotVal`, `TaxTotVal`, `PreviousOwner`) | Yes | Yes | 134,525 | [LIVE] |
| 19 | SD Minnehaha (Sioux Falls) | City of Sioux Falls `https://gis.siouxfalls.gov/arcgis/rest/services/Data/Property/MapServer/1` (`OWNNAME1/2`, `OWNADDRESS`) | Yes | No | 67,167 | [LIVE] |
| 20 | IL McHenry | McHenry County GIS `https://services1.arcgis.com/6iYC5AXXYapRVNzl/arcgis/rest/services/McHenry_County_TaxParcels/FeatureServer/0` (`Owner`) | Yes | No | 150,159 | [LIVE] |
| 21 | MI Ingham / Genesee | Ingham County Drain Office 2024 view `https://services3.arcgis.com/ySzhFSJfYeginRjx/arcgis/rest/services/Ingham_County_Parcels_2024_view/FeatureServer/0` (`OWNERNAME`; 101,733). "GC_Parcels" `https://services2.arcgis.com/PrYwGqAi1wKjoFb1/arcgis/rest/services/Parcels2025County/FeatureServer/0` (`OwnName`, `Assessment`; 189,790; publisher not shown, likely Genesee County). | Yes | Genesee yes | | [LIVE] |
| 22 | NM Santa Fe | City of Santa Fe copy of the county parcels, Apr 2025 `https://services7.arcgis.com/p0Gk2nDbPs7KEqSZ/arcgis/rest/services/SFC_Parcels_20250415/FeatureServer/0` (`Owner_*` lines) | Yes | No | 80,927 | [LIVE] (snapshot) |
| 23 | AK Mat-Su / Anchorage values | Municipality of Anchorage `PropertyInformation_Hosted` has `Owner_Name` and appraised values (99,792), and Anchorage is already loaded. Mat-Su: only a 2009 "Preshift" layer was found (stale). | | | | [LIVE] |
| 24 | KS Wyandotte / Sedgwick | The "Wyandotte_Parcels" layer has `OWNERNAME1`, `ASSESSEDVALUE` but only 10,457 rows (partial, publisher unknown). The Sedgwick layer is a GDIT 2021 mirror (`Owner`, `TotVal`; 226,956), not the county's. | | | | [LIVE]. Treat both as leads, not sources. |
| 25 | CA Alameda | City of Oakland GIS `AC_Parcels2020` `https://services.arcgis.com/9tC74aDHuml0x5Yz/arcgis/rest/services/AC_Parcels2020/FeatureServer/0` (`OWNER_NAME`, `ASSESSED_VALUE`; 224,041; **2020 vintage**). MTC/BayAreaMetro Socrata: "San Mateo County Property Parcels" `q2fy-xss3` (`owner_name`, 2023) and "Parcels" `q48c-gc2g` (`ownername`, 2025-09; county and licence unstated). | Yes | Yes | | [LIVE]. The vintage and licence problems already flagged in recorder-sources.md for MTC apply. |
| 26 | VA Dumfries | Town of Dumfries "Real Estate Assessments" `data.dumfriesva.gov rdxq-jfzf` (current_owner) | Yes | | | [LIVE], but tiny and covered by Prince William. |

**Checked and confirmed as not filling the gap [LIVE]:**
- Jefferson County KY (LOJIC) `https://gis.lojic.org/maps/rest/services/LojicSolutions/OpenDataPVA/MapServer/1`: 293,463 parcels with no owner or value fields. This matches coverage.md.
- Fairfax County `Tax_Administration_Real_Estate_Parcels_Data` (370,782): no owner fields. `OpenData_A5` has sales and commercial tables only.
- Pierce County WA Tax_Parcels (340,193): values but no owner name.
- Virginia Beach: only "Delinquent Real Estate Taxes" (`Owner_Name`, 13,708) and Historic Parcels were found on the city's ArcGIS Online. No full owner layer was found.
- Henrico: VGIN "Henrico_county" is a county boundary (1 row).
- NJ MOD-IV 2026 statewide zip `https://www.nj.gov/treasury/taxation/pdf/lpt/modiv-2026.zip` (268 MB, 21 county fixed-width files, last modified 2026-08-03). In the Essex rows I sampled, the **owner-name positions are blank but the owner mailing street/city/ZIP is present**. This confirms the Daniel's Law redaction in bulk while giving a mailing address. The NJ SR-1A sales files on the same page carry grantor/grantee names ([LIVE] link list; see recorder-sources.md).
- Hawaii: the CKAN search on opendata.hawaii.gov found no OWNALL/HOLIS owner table ([LIVE], 0 hits). Web search says the City and County of Honolulu RPAD posts weekly OWNALL/OWNMLT tables on the state open-data portal ([SEARCH], [Honolulu search result summary](https://opendata.hawaii.gov/bs/dataset/?tags=holis)). Those are unconfirmed. Maui owner layers exist only as third-party copies (2026, University of Hawaii org: `Parcels_w_Owners_Maui_County_2026`).

**Remaining gaps by state (no free owner source found this session):**
- CA counties other than San Diego and Alameda: Orange, Santa Clara, Sacramento, Riverside, San Bernardino and LA owner names were not found. Hub searches returned only public-owner flags or small subsets.
- DE: New Castle, Kent and Sussex owner layers were not found. The FirstMap public version has no owner names (coverage.md).
- NH: town by town.
- IA Polk, KS Johnson/Sedgwick (official), KY Fayette, LA Jefferson Parish/St. Tammany/Caddo (Lafayette only a 2023 LEDA copy with `Name`), MI Kent/Washtenaw, MO St. Louis City/St. Charles (official), NM Bernalillo, OK Cleveland, SC Richland/Horry/Spartanburg/Lexington, GA Chatham/Cherokee/Forsyth/Clayton/Henry, AL Mobile/Baldwin/Montgomery/Shelby, IL Will/Kane/Winnebago, VA Fairfax/Virginia Beach/Henrico/Arlington: no official owner-bearing layer found in ArcGIS Hub searches (the 30-plus queries above).
- OH values: not researched this session. County auditors (Franklin, Cuyahoga, Hamilton) are the candidates.

### Inferences
- Priority by size: Maricopa (1.76M), TN 86 counties (about 1.85M owner rows beyond Davidson), SanGIS (1.09M), MT (0.92M), Clark NV (0.87M), King WA, then Indianapolis, Nashville, Utah County, Douglas NE, Multnomah, Spokane and Washoe at 0.2-0.35M each. These seven or so sources would add owner names for roughly 8-9M parcels. That figure is my sum of the [LIVE] counts above.
- With Davidson added from Nashville GIS, only Shelby, Knox, Hamilton, Rutherford, Williamson, Montgomery, Chester and Hickman would remain without TN owners.
- In the "no owner" states, the deed/sales files are often a better owner proxy than parcel layers: King EXTR_RPSale, NJ SR-1A, the MD SDAT grantor on the next sale, and Norfolk grantee. The latest grantee on a parcel is very likely its current owner, apart from unrecorded transfers.
- The repo's `tn.statewide.parcels` and `mt` notes predate these services. Re-point TN to the Public Use layer only after a legal read of its "approved access" wording.

### Gaps
- Terms of use were not read for any [LIVE] layer above. In particular I could not confirm the commercial terms for Maricopa, the City of Las Vegas, TN STS and the MT AGOL copy.
- Whether `ADDR_OWN` covers all of Clark County is unverified, and so is the MD statewide owner field (geodata.md.gov returned 503).
- The Honolulu OWNALL table location, Broward and King County's own terms, and Polk IA (the Polk County Assessor downloads are known only from prior knowledge) are all unresolved.

## 2. Recorder indexes (deeds, mortgages, liens, lis pendens, releases)

### Takeaway
Still almost nothing free in bulk beyond the five loaded indexes. FL clerks are the only family that publishes full official-records indexes (Hillsborough, Hernando, Putnam, all loaded); every other large FL clerk found is paid. Deed-level sales with names exist for IL (PTAX-203), MD (SDAT with mortgage amount), NJ (SR-1A), CT, Cook, Detroit, Adams/Douglas CO, Norfolk, and now King County WA and Maricopa (last deed only).

### Cited Findings
- **Newly verified this session [LIVE]:**
  - King County WA `EXTR_RPSale.csv` (650 MB unzipped). Seller and buyer names, sale price, `RecordingNbr`, volume/page, `SaleInstrument` (deed type) and `SaleReason`, with history back decades (sample rows from 1996 and 2003). Free zip at `aqua.kingcounty.gov/extranet/assessor/`, refreshed 2026-11-20. This upgrades the "King County Assessor data download (unverified)" row in `docs/sources/recorder-sources.md` to verified.
  - Maricopa Assessor parcel layer carries the **last** `DEED_NUMBER`, `DEED_DATE`, `SALE_DATE` and `SALE_PRICE` per parcel (see §1). It is not an index, but it gives a recorder document number for the last conveyance. AZ is a 1 in the law ranking ([recorder laws report](../../reports/Recorder%20data%20records%20laws%20by%20state.md)).
  - Nashville `Parcels_view` has `OwnInstr` (deed instrument reference), `OwnDate` and `SalePrice`.
  - Socrata federated catalog searches: "lis pendens" returned **0 datasets**; "mechanic(s) lien" returned 0; "construction lien" returned none relevant. "Recorded documents" turned up only the known Macoupin IL 2015 sets and the Cook Recorder 2011-2015 set (`4f2q-h3b7`). This confirms that no Socrata portal publishes a live recorder index ([LIVE], `api.us.socrata.com/api/catalog/v1`).
  - Washoe NV parcels carry `SALEDATE`/`SALEPRICE` (§1). NV is a non-disclosure-light state.
- **FL clerks (the best remaining family):**
  - Broward "Bulk Data Files": Official Records FTP index plus images, pipe-delimited, kept 7 days. Price not stated in snippets ([SEARCH], [Broward bulk data page](https://www.broward.org/RecordsTaxesTreasury/Records/Pages/IndexFiles-Completed.aspx)). `www.broward.org` would not resolve from this session's WebFetch, so this stays [UNVERIFIED].
  - Paid: Miami-Dade (per-folder fees: [Miami-Dade Commercial Data Services](https://www.miamidade.gov/clerk/commercial-data-services.page)); Lake ($75 setup + $275/yr, or $60 + $800-$850/yr FTP: the pages conflict, [Lake clerk subscribers](https://lakeclerkfl.gov/subscribers)); Palm Beach (electronic distribution index service: [Palm Beach clerk](https://www.mypalmbeachclerk.com/records/official-records/electronic-distribution-index-service)); Pasco (daily index data in a paid enhanced service: [Pasco agreement](https://www.pascoclerk.com/DocumentCenter/View/7677/Non-Government-Access-Agreement)) — all [SEARCH].
  - Fla. Stat. 28.222 requires a direct and inverse index ([flsenate 28.222](https://www.flsenate.gov/Laws/Statutes/2020/28.222)) [SEARCH]. Hernando's and Putnam's loaders show small clerks sometimes post these indexes free (`config/recorders/fl.hernando.or.yaml`, `fl.putnam.or.yaml`).
- **Carried forward from `docs/sources/recorder-sources.md` (2026-11-21), still the best free bulk set not yet loaded:**
  1. MD SDAT `ed4q-f8tm` (statewide; last 3 transfers with grantor, consideration and **mortgage amount**; catalog updated 2026-11-06 [LIVE]).
  2. IL PTAX-203 `it54-y4c6`, plus `vbnw-q5s8` with `county_form_mortgage_amount` (catalog [LIVE]).
  3. NJ SR-1A yearly and year-to-date zips (`statdata/Sales2020-2026.zip` links [LIVE]).
  4. Cook Assessor Parcel Sales `wvhk-k5uv` (updated 2026-11-15 [LIVE]).
  5. CT Parcel and CAMA `ibe8-9i3q`.
  6. Detroit and Adams/Douglas CO sales.
  7. Allegheny WPRDC.
  8. Norfolk `qva7-tzrf` (updated 2026-11-22 [LIVE]).
  9. Indiana SDF.
  10. Vermont PTT.
  11. Wake NC.
  12. WI RETR.
- **Law-based outlook** (from the 51-jurisdiction report; not legal advice): FL, NY, TX, GA, MD, NC, WV, IA, ID, CT, NV and WY score 4-5 for a free or near-free index export on request. The report's pilot list starts with large FL clerks (Pinellas, Orange, Duval) ([report](../../reports/Recorder%20data%20records%20laws%20by%20state.md)).

### Inferences
- The most likely new free FL index is another small or mid-size clerk using the same "subscriber data files" software as Hernando (`subscriber.<county>clerk.com/data_files`) or the Putnam ORI zips. A scripted probe of each FL clerk domain for those paths is cheap and has not been done.
- For equity math, King County EXTR_RPSale and Maricopa last-sale give purchase-price ceilings in two large non-loaded markets.

### Gaps
- Broward pricing, the Pinellas/Orange/Duval index files, and the Texas county clerk open-data portals were not checked live.

## 3. Mechanic's liens: where they are recorded, and free bulk sources

### Takeaway
In most states mechanic's/construction liens are recorded with the county recorder, register of deeds or county clerk, so they sit inside the recorder index (Hillsborough and Putnam index them under the generic code `LN`, which does not separate them from other liens). The main exceptions are court-clerk filing in PA (prothonotary) and NC (clerk of superior court, judgment docket), and a central state registry in Iowa (MNLR at the Secretary of State). No free bulk mechanic's-lien dataset was found anywhere.

### Cited Findings
- **Iowa:** the Mechanics' Notice and Lien Registry (MNLR) is "a centralized computer database maintained on the Internet" by the Secretary of State. All mechanics' liens filed on or after 2013-01-01 must be posted there, along with notices of commencement and preliminary notices; search is at sos.iowa.gov/mnlr/search ([Iowa Admin. Code 721-45](https://www.legis.iowa.gov/docs/iac/chapter/02-18-2026.721.45.pdf); [Iowa SOS GC info](https://sos.iowa.gov/mnlr/info/GCinfo.aspx)) [SEARCH]. No bulk export was found; per-search only.
- **North Carolina:** claims of lien on real property are filed with the clerk of superior court in the county. The clerk notes the lien on the **judgment docket**, indexed under the record owner ([G.S. 44A-12](https://www.ncleg.gov/EnactedLegislation/Statutes/HTML/BySection/Chapter_44a/GS_44a-12.html)) [SEARCH]. So NC mechanic's liens travel with court judgment data, not register-of-deeds data.
- **Pennsylvania:** filed with the prothonotary, not the recorder ([Levelset](https://www.levelset.com/blog/rejected-mechanics-liens-2-common-culprits/), vendor blog) [SEARCH]. This is consistent with the repo note that Philadelphia mechanic's liens are not in the RTT table (`config/recorders/pa.philadelphia.rtt.yaml`). PA's State Construction Notices Directory (Act 142 of 2014) holds notices of commencement and furnishing for projects of $1.5M or more. It is not a lien filing, and DGS does not verify it ([PA DGS](https://www.pa.gov/dgs/state-construction-notices-directory)) [SEARCH].
- **Utah:** the State Construction Registry is the central repository for notices of commencement, preliminary notices and notices of completion. Only parties who filed a preliminary notice may lien, and the liens themselves are recorded with the county recorder ([Utah Commerce SCR](https://commerce.utah.gov/?p=22511); [SCR homeowners](https://secure.utah.gov/scr/homeowners/index.html)) [SEARCH]. That the lien goes to the county recorder is prior knowledge, [UNVERIFIED].
- **West Virginia:** the county clerk records lien notices in a "mechanic's lien record" ([W. Va. Code 38-2-33](https://code.wvlegislature.gov/38-2-33/)) [SEARCH].
- **New York:** private-improvement liens are filed with the County Clerk (Lien Law § 10) ([FindLaw case](https://caselaw.findlaw.com/court/ny-supreme-court/1308705.html)) [SEARCH]. Inference: they are therefore not in ACRIS; the repo notes NY money judgments are likewise County Clerk records (`config/recorders/ny.nyc.acris.yaml`).
- **Oklahoma:** county clerk (1977 amendment moved filing from the district court clerk) ([Tulsa Excavation v. Pinalto](https://law.justia.com/cases/oklahoma/court-of-appeals-civil/1984/9778.html)) [SEARCH].
- **Missouri:** some notices go to the recorder of deeds and others to the clerk of court ([Levelset](https://www.levelset.com/blog/notice-compliance-missouri-you-cant-trust-county-recorder/)) [SEARCH].
- **Virginia:** memoranda of mechanic's lien are filed in the circuit court clerk's land records (for example [Prince William Circuit Court](https://www.pwcva.gov/department/circuit-court/mechanics-lien)) [SEARCH].
- **Florida:** recorded in Official Records. The loaded indexes code them as `LN`/`LIEN` together with other statutory liens (`config/recorders/fl.hillsborough.or.yaml` comment) [LIVE repo].
- **Free bulk:** the Socrata catalog returned 0 datasets for "mechanic lien" and "mechanics lien" ([LIVE]). No ArcGIS Hub layer was found.

### Inferences
- The practical free mechanic's-lien coverage is whatever the loaded FL recorder indexes hold. Separating construction liens there needs the description text: Putnam descriptions carry amounts, and Hernando has "LIEN".
- NC is a special case: if a NC court-judgment docket source is ever loaded, mechanic's liens come with it.

### Gaps
- Wisconsin (believed to be the clerk of circuit court under Wis. Stat. 779.06), Hawaii (circuit court application), Montana (Secretary of State notice of right to claim a lien) and Georgia (superior court clerk via the GSCCCA lien index, paid) were not confirmed this session. Treat them as [UNVERIFIED].
- I found no source on whether Iowa MNLR offers any bulk export.

## 4. Building permits: free bulk datasets

### Takeaway
Dozens of city and county portals publish permits free in bulk. The most useful for a debtor-property graph carry owner name plus parcel ID: NYC DOB (two datasets), Philadelphia, East Baton Rouge, Collin CAD (TX), Kansas City (2014 listing) and Marin County. Contractor and valuation fields are common: Austin, Seattle, Chicago, Mesa, Cincinnati, Dallas, Boston, LA. National aggregators with names and contractors (BuildZoom, Shovels, ATTOM, Construction Monitor) are paid; the free federal series is aggregate only.

### Cited Findings
All rows are [LIVE] Socrata `api/views` / catalog columns or CKAN/Carto field lists, read 2026-11-23.

| Jurisdiction | Dataset | Owner | Contractor | Valuation | Parcel key | Updated |
|---|---|---|---|---|---|---|
| NYC | DOB Permit Issuance `data.cityofnewyork.us ipu4-2q9a` | `owner_s_first/last_name`, `owner_s_business_name`, owner address/zip | permittee name, business | — | BIN, block/lot | 2026-11-22 |
| NYC | DOB NOW: Build – Approved Permits `rbx6-tga4` | `owner_name`, `owner_business_name`, owner street/city/state | applicant (licence, business) | `estimated_job_costs` | BIN, lot | 2026-11-21 |
| NYC | DOB NOW Electrical `dm9a-ab7w` | owner first/last, address | firm | — | BIN, lot | 2026-11-21 |
| Philadelphia | L&I permits (Carto `phl.carto.com` table `permits`) | `opa_owner` | `contractorname`, contractor address | — | `opa_account_num`, `parcel_id_num` | live |
| East Baton Rouge LA | `data.brla.gov 7fq7-8j7r` | `ownername` | `contractorname`, address | `projectvalue` | lot | 2026-11-22 |
| Collin CAD TX | `data.texas.gov 82ee-gbj5` | `propownername` | `permitbuildername` | `permitvalue` | CAD property (subdivision/lot) | 2026-11-22 |
| Kansas City MO | 2014 listing `data.kcmo.org qt6m-65bz` (owner_name), CPD permits `ntw8-aacc` | 2014 only | contractor company, licence | `estprojectcost` | `pin` | 2025-05 |
| Marin County CA | `data.marincounty.gov mkbn-caye` | — | contractor, address, licence | `construction_value` | `parcel_number` | 2026-11-22 |
| San Diego County | `internal-sandiegocounty.data.socrata.com dyzh-7eat`, plus yearly sets 2010-2017 | `homeowner_biz_owner` | contractor name, address, phone, licence | `valuation` | `parcel_number` | 2024-08 |
| Chicago | `data.cityofchicago.org ydr8-5enu` | contact_1..15 names (roles include owner) | contacts | `reported_cost` | `pin_list` | 2026-11-21 |
| Austin | Issued Construction Permits `datahub.austintexas.gov 3syk-w9eu` | — | contractor company, name, phone, address | `total_job_valuation` + trade valuations | — | 2026-11-22 |
| Seattle | `cos-data.seattle.gov 76t5-zqzr` | — | `contractorcompanyname` | `estprojectcost` | — | 2026-11-23 |
| Mesa AZ | `citydata.mesaaz.gov dzpk-hxfb` | — | contractor name, address, phone, email, licence | `total_valuation`, `job_value` | `parcel_number` | 2026-11-22 |
| Cincinnati | `data.cincinnati-oh.gov uhjb-xac9` | — | `companyname` | `estprojectcostdec` | `pin` | 2026-11-22 |
| Dallas | `www.dallasopendata.com e7gq-4sah` | — | `contractor` | `value` | — | 2026-11-22 |
| Los Angeles | `data.lacity.org pi9x-tg5x` (2020 on) | — | — | `valuation` | `apn`, `pin_nbr` | 2026-11-16 |
| Boston | CKAN "Approved Building Permits" `data.boston.gov` resource `6ddcd912-...` | — | `applicant` | `declared_valuation` | `parcel_id`, `property_id` | 2026-11-22 |
| Norfolk VA | `data.norfolk.gov fahm-yuh4` | — | — | `project_cost` | `gpin` | 2026-11-22 |
| Montgomery County MD | Residential `m88u-pqki` | — | — | `declaredvaluation` | — | 2026-11-20 |
| Williamson CAD TX | `data.wcad.org fqhf-gyjx` | — | — | `amount` | CAD id | 2026-11-22 |
| Cambridge MA | several permit sets (for example `9qm7-wbdc`) | — | — | cost fields | — | 2026-11-22 |
| Other small sets | Rockford IL `3k8p-pkx8` (contractor, `pin`, `valuation`), Corona CA, Roseville CA, Gainesville FL (2023), Albany NY 2009-13 (owner), Asotin and Clarkston WA (owner), New Orleans `nbcf-m6c2` (stale since 2025-08; no key fields) | | | | | |

- The Socrata federated search for "building permits" returned 476 datasets ([LIVE]), so the table is a sample, not a census.
- ArcGIS Hub: Denver publishes "2-9-Unit Residential Construction Permits" (`services1.arcgis.com/zdB7qR0BtYrg0Xpl/.../ODC_DEV_RESIDENTIALCONSTPERMIT_P`) [LIVE search hit, fields not read]. Hub searches for Nashville, Phoenix, Houston and San Antonio permits returned no official permit layer ([LIVE] search).
- San Francisco: the dataset id `i98e-djp9` did not resolve through `data.sfgov.org/api/views`, and the catalog returned nothing for the domain ([LIVE] failure). SF permits are [UNVERIFIED] this session.

### Inferences
- For the debtor graph, permits matter in two ways. Owner-named permits (NYC, Philadelphia, EBR, Collin) link a debtor name to a parcel, as a check on ownership. High `estimated_job_costs` and contractor records flag likely mechanic's-lien exposure and improvements that raise equity.
- Join keys exist in most sets: BIN/BBL (NYC), OPA account (Philadelphia), APN/PIN (LA, Chicago, Cincinnati, Mesa, Marin, Boston, Norfolk GPIN).

### Gaps
- I did not verify the pricing of BuildZoom, Shovels, ATTOM or Construction Monitor. From prior knowledge they are commercial or paid-API products, so they are [UNVERIFIED] and outside the usable set.
- I did not verify the Census Bureau Building Permits Survey this session. From prior knowledge it holds aggregate counts and valuation by permit-issuing place, with no owner, contractor or address, so it is [UNVERIFIED] and of no use per parcel.
- Houston, Phoenix, San Antonio, Nashville, Jacksonville and Denver (fields) permit feeds were not found or read.
