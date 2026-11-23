# Government sales of property and assets: free bulk/API sources and repo gaps (US, as of 2026-11-23)

Tags: **[LIVE]** = fetched from this session on 2026-11-23 (HTTP status, record counts and field lists taken from the live endpoint); **[SEARCH]** = seen only in web-search results/snippets; **[UNVERIFIED]** = from memory or inference, not confirmed. "Usable" means free + bulk or API + no login/CAPTCHA/paywall + not a scrape of a search portal. Others are listed separately as "not usable".

Method note: The two best discovery tools were (a) the ArcGIS Hub search API `https://hub.arcgis.com/api/search/v1/collections/all/items?q=...` and (b) the Socrata Discovery API `https://api.us.socrata.com/api/catalog/v1?q=...`. Both are free, need no key and covered every county/city layer listed below. Running them on a schedule is itself a discovery source for new sale lists. [LIVE]

## 1. What the repo already has (baseline for the gap analysis)

### Takeaway
The repo has 8 sale-adjacent county sources, all ArcGIS/WPRDC lien-style adapters under `config/liens/`. It has no federal, statewide-platform, land-bank, state-surplus, personal-property or mineral-lease sale source, and no sale-results or redemption feed.

### Cited Findings
- Sale-related configs in the repo: `pa.washington.sheriff_sales` (ArcGIS `SheriffsSaleData/FeatureServer/1`: docket, judgement, sale_date, stayed_status), `ms.harrison.tax_sale_parcels` (`MSGCHrsnCntyDelinquentParcelAuctions2025Official`), `az.cochise.tax_liens` (`Cad_TaxLienParcel`), `fl.broward.tax_certificates` (`Unpaid_Tax_Delinquency`), `tx.harris.tax_judgments` (`Tax_Delinquent_Parcels/FeatureServer/1`), `pa.allegheny.foreclosures` (WPRDC), `pa.allegheny.tax_liens`, and `oh.mahoning.delinquent_taxes` (`Tax_Delinquent_and_Land_Bank_Eligible_Properties`). — repo `config/liens/*.yaml` [LIVE, local grep]
- A grep of `src/`, `config/` and `docs/` for hud, gsa, blm, usda, govdeals, bid4assets, realauction, land bank, treasury and marshal finds no source config. The only "land bank" hit is the Mahoning layer name. — repo grep [LIVE, local]
- `docs/gaps.md` tracks parcels, deeds, judgments, bankruptcy, business registry and zoning. It has no "government sales" layer. — `/home/user/equity/docs/gaps.md` [LIVE, local]

### Inferences
- Everything below is a gap unless it is marked as already in the repo. The existing adapter pattern (ArcGIS FeatureServer, Socrata or CSV with a `parcel:` join key) already fits most of the usable sources below. Federal JSON (GSA) and Federal Register would need new generic adapters.

### Gaps
- Not checked: whether the existing Cochise adapter also reads the separate Cochise `2026_Tax_Deed_Auction_Parcels` layer listed below. It appears not to, since the config points at `Cad_TaxLienParcel`.

## 2. Tax deed sales and tax lien certificate sales

### Takeaway
There is no free national or statewide machine-readable feed. The platforms that run these sales (RealAuction/realtaxdeed/realforeclose, LienHub, GovEase, Bid4Assets, SRI/Zeus) block bots or are search-only. The usable sources are county ArcGIS and Socrata layers published by treasurers, auditors and clerks: dozens exist and are findable through the Hub and Socrata search APIs. For results and redemptions there are a few strong outliers: Fulton GA, Sonoma CA, Cook IL (historic) and NYC.

### Cited Findings: usable county layers (not in the repo) [LIVE unless noted]
- **Lucas County OH, Forfeited Land Sale 2026**: 43 parcels, edited 2026-11-18. Fields include parid, owner, property_address, taxesowed, totvalinias, datetransferred. Also `Forfeited_Land_Parcels_2025_view` on the county's own server. — [ArcGIS](https://services3.arcgis.com/T8dczfwPixv79EgZ/arcgis/rest/services/Forfeited_Land_Sale_2026/FeatureServer/0), [2025](https://lcaudgis.co.lucas.oh.us/gisaudserver/rest/services/Hosted/Forfeited_Land_Parcels_2025_view/FeatureServer)
- **Lake County CO, 2026 Delinquent Tax Lien Sales**: 370 rows, 2026-10-08. Fields include ACCOUNTNO, Owner_Name, NAME, ADDRESS1, CITY, STATE, PARCELNB. There is a separate `2025_Tax_Liens` layer. — [ArcGIS](https://services1.arcgis.com/38PTfoP8IjlBsxZN/arcgis/rest/services/2026_Delinquent_Tax_Lien_Sales/FeatureServer/0)
- **Douglas County CO, Treasurer Tax Liens**: the schema includes lien_id, interest rate, lien_balance, sale_or_purchase_date and subsequent-tax years 1–5. It returned **count 0** on 2026-11-23 while edited 2026-11-20, so it is probably emptied between sales. A separate `Tax_Sale_List_Locations` layer exists. — [ArcGIS](https://services.arcgis.com/seTexOicoRXDvRsJ/arcgis/rest/services/Treasurer_Tax_Liens/FeatureServer/0), [list](https://services.arcgis.com/seTexOicoRXDvRsJ/arcgis/rest/services/Tax_Sale_List_Locations/FeatureServer)
- **Douglas County (dcgis.org; state not confirmed), DC Tax Liens**: modified 2026-11-22. [SEARCH via Hub API; not probed] — [ArcGIS](https://dcgis.org/server/rest/services/Hosted/DC_Tax_Liens_view/FeatureServer)
- **Maricopa County AZ, "Unsold Lien Parcels"** (state-held liens left over from the sale): 1,455 rows, edited 2026-11-22. Fields: APN, address, DeedNumber, Assessor/Treasurer links. Layer 0 "Bad Investment Parcels" has 690 rows. — [ArcGIS](https://services.arcgis.com/ykpntM6e3tHvzKRJ/arcgis/rest/services/ParcelLienDelinquent/FeatureServer/1)
- **Cochise County AZ, 2026 Tax Deed Auction Parcels**: 345 rows. Fields: apn, Previous_Owner_s_Name, Full_Cash_Value, Taxes, Minimum_Bid, Legal_Description. This is separate from the repo's `Cad_TaxLienParcel`. — [ArcGIS](https://services6.arcgis.com/Yxem0VOcqSy8T6TE/arcgis/rest/services/2026_Tax_Deed_Auction_Parcels/FeatureServer)
- **Navajo County AZ, Back Tax Auction Properties**: 191 rows, with APN and AuctionURL only. — [ArcGIS](https://services.arcgis.com/cghC2lEIpJ2TRrs5/arcgis/rest/services/BackTaxAuctionProperties/FeatureServer/1)
- **Wyandotte County / KCK (KS), 2026 Tax Sale**: 161 rows. Fields: PARCEL, ADDRESS, MINIMUM_BID, PROPERTY_TYPE, ACRE. — [ArcGIS](https://services1.arcgis.com/Qo2HHQp8vgPs2wg3/arcgis/rest/services/Property_Tax_Sale/FeatureServer/0)
- **St. Joseph County IN, Tax Sale Properties 09/01/2026**: 1,266 rows. Fields: PARCELID, NAME_1 (owner), mailing address, land/improvement values, last SALESDATE/SALESPRICE. — [ArcGIS](https://services.arcgis.com/OjftlhRHkAABcyiF/arcgis/rest/services/Tax_Sale_Properties_09012026/FeatureServer/0)
- Other county tax-sale layers found by Hub search but not probed [SEARCH]: Hammond IN "2027 Tax Sale" (2026-11-12), Linn Co KS "TAX SALE 2025", Franklin Co KS, McPherson Co KS, Finney Co KS, Spartanburg SC, Kings Co CA "Tax Sale Data", San Bernardino CA 2020, Pope Co MN "Tax Forfeit Sales", Polk Co MN "Tax Foreclosures", Baltimore City "Tax Lien Certificate Sale Properties" (2025-01-27) and several older Baltimore lists, and Camden City NJ "Tax Lien Parcels (Ownership Redacted)". — URLs from [Hub search API](https://hub.arcgis.com/api/search/v1/collections/all/items?q=tax%20sale)
- **Fulton County GA, "Tax Deed Activity" (Socrata 7dey-txkb)**: 33,912 rows, updated 2026-11-22, CC-BY-4.0. These are workflow task records keyed by parid/taxyr with task_type_name, status and dates. It is a process log, not a clean sale list. — [Socrata](https://sharefulton.fultoncountyga.gov/resource/7dey-txkb.json)
- **Sonoma County CA, "Defaulted Tax Data" (bp8v-uax7)**: 9,789 rows, updated 2026-11-21. It includes assessment_number, taxyear, base tax, penalty, **redemption_fee** and full-redemption columns. This is the defaulted-tax pool that feeds CA tax-defaulted sales (Chapter 7). — [Socrata](https://data.sonomacounty.ca.gov/resource/bp8v-uax7.json)
- **Riverside County CA, "Inventory of Parcels Subject to Power of Sale"** (2016–2017 snapshots only; stale). — [Socrata catalog](https://api.us.socrata.com/api/catalog/v1?q=tax%20sale)
- **Cook County IL Treasurer, Annual and Scavenger Tax Sale datasets** (55ju-2fs9 and ydgz-vkrp, plus sold, forfeited and registered-buyer tables for 2009–2010). The last update was 2016, so these are historic only. — [Cook County data catalog](https://datacatalog.cookcountyil.gov/d/55ju-2fs9)
- **Howard County MD, "Tax Sales: 2010 – Current" (etp2-fnbu)**: last updated 2018 (stale). — [Socrata](https://opendata.howardcountymd.gov/d/etp2-fnbu)
- **NYC DOF, Tax Lien Sale Lists (9rz4-mjek)**: 264,142 rows, rows updated 2025-12-01. Fields: month, cycle (90-day/60-day/... notice), borough-block-lot, building class, address, water_debt_only. No owner names. This is a lien-sale list, not a deed sale. — [NYC Open Data](https://data.cityofnewyork.us/resource/9rz4-mjek.json)
- **Florida tax deeds**: clerks run them on county RealAuction subdomains (e.g., duval.realtaxdeed.com, volusia/lake realtaxdeed, brevard.realforeclose.com). The search found one clerk-published file: Hillsborough's "Weekly Tax Deed Spreadsheet", which holds only the file number and unclaimed (surplus) amount. — [Hillsborough Clerk](https://hillsclerk.com/taxdeeds), [Duval Clerk](https://www.duvalclerk.com/departments/county-services/tax-deed-files), [Brevard Clerk](https://www.brevardclerk.us/tax-deeds) [SEARCH]

### Cited Findings: platforms (not usable)
- `realtaxdeed.com` and `*.realforeclose.com` return HTTP 403 even for `/robots.txt` to a non-browser client. — [realtaxdeed robots](https://www.realtaxdeed.com/robots.txt), [miamidade.realforeclose robots](https://miamidade.realforeclose.com/robots.txt) [LIVE]
- `lienhub.com` (FL tax certificate sales) serves a Cloudflare "managed challenge" page even for `/robots.txt`. — [LienHub](https://lienhub.com/robots.txt) [LIVE]
- `realestatesales.gov` and `hudhomestore.gov` both publish `robots.txt` with `Disallow: /` (see §5). Bid4Assets' terms page (`/pages/public/content/b4a/terms-of-service`) loads (HTTP 200) but its text is rendered client-side, so no scraping clause could be confirmed. Bid4Assets appears among the domains covered by the Liquidity Services privacy policy. — [Bid4Assets ToS](https://www.bid4assets.com/pages/public/content/b4a/terms-of-service) [LIVE: page loads; clause UNVERIFIED], [Liquidity Services privacy policy](https://liquidityservices.com/privacy-policy) [SEARCH]
- GovEase's robots.txt is a stock HubSpot file (marketing site only; auction data sits behind the app). — [GovEase robots](https://www.govease.com/robots.txt) [LIVE]
- `zeusauction.com/robots.txt` returns 404. No public listing feed was found for SRI/Zeus. — [LIVE: robots 404; no feed found]
- Municibid's terms prohibit "Scraping, reproducing, republishing…" the site. This is a sign of the sector norm, not of other platforms' terms. — [Municibid Terms PDF](https://www.municibid.com/Content/documents/Municibid%20Terms%20of%20Use%20Agreement.pdf) [SEARCH]

### Inferences
- No platform (RealAuction, LienHub, GovEase, Bid4Assets, SRI) offers a usable feed. A nationwide tax-sale aggregator has to be built county by county from treasurer/auditor GIS layers and clerk spreadsheets, using Hub/Socrata search for discovery.
- Many county "tax sale" layers are point-in-time (named by sale date) and get replaced or emptied (Douglas CO count 0). Adapters must snapshot on each run and key on sale year to keep history. This suits the repo's transaction-time model.
- FL coverage stays weak because every FL clerk uses RealAuction. The repo's `fl.broward.tax_certificates` is the delinquency layer, not the certificate sale results.

### Gaps
- Not found: a free statewide list of FL tax certificate sale results, AZ statewide lien results, NJ municipal tax lien sale results, IL statewide, MD statewide, or IA statewide. Each state's results appear to sit with each county or municipality, usually as PDF or vendor portal [UNVERIFIED].
- TX county tax-sale (sheriff/constable "tax resale") lists are mostly PDFs from the linebarger/PBFCM law firms. No machine-readable statewide source was found [UNVERIFIED].
- GA and CA statewide: no aggregated tax-deed or tax-defaulted-sale feed was found beyond the Fulton and Sonoma datasets.

## 3. Sheriff and mortgage-foreclosure sales

### Takeaway
There is no national feed. Usable sheriff-sale data is county GIS. The two best finds give **sale results with buyer and price**: Dakota County MN (2007–2025 yearly layers) and Milwaukee County WI (plaintiff, defendant, case number, sale price, purchaser). Statewide sale platforms (NJ CivilView, Ohio's statewide sheriff-sale site, RealForeclose) are search portals, not feeds.

### Cited Findings
- **Dakota County MN, Sheriff Foreclosure Sales**: separate MapServer layers per year, 2007 through 2025 (e.g., layer 80 = 2025 with 110 rows). Fields: CRN (parcel), SaleDate, SaleAmount, PersonIsBu (buyer-type flag), GeoAddress, GeoCity. — [MapServer/80](https://gis2.co.dakota.mn.us/arcgis/rest/services/DCGIS_OL_PropertyInformation/MapServer/80) [LIVE]
- **Milwaukee County WI, Foreclosed Parcels**: 400 rows, edited 2026-11-06. Fields: Sale_No, Sale_Date, **Plaintiff, Defendant, Case_No, Sale_Price, Attorney, Purchaser**, MCLIO_TAXKEY. — [FeatureServer/25](https://services2.arcgis.com/s1wgJQKbKJihhhaT/arcgis/rest/services/Foreclosed_Parcels/FeatureServer/25) [LIVE]
- **Washington County PA**: besides the repo's `SheriffsSaleData`, there is a newer `Sheriffs_Sale_Active_Data` service (modified 2026-08-11) and a `Municipal_Sheriff_Sale_Count_Geodatabase_v5`. — [Active](https://services2.arcgis.com/LgK9DpUhNjdU0HLy/arcgis/rest/services/Sheriffs_Sale_Active_Data/FeatureServer) [SEARCH via Hub API]
- **New Orleans, "Sheriff Sales – Lien Foreclosures" (d52w-8nva)**: 1,771 rows with defendant, plaintiff, address, saleamount, saledate, salestatus. Last updated 2018-11-16 (historic only). — [data.nola.gov](https://data.nola.gov/resource/d52w-8nva.json) [LIVE]
- **Baton Rouge "Adjudicated Property" (a4h4-zi7e)**: LA tax-adjudicated parcels, updated 2024-02-27. — [data.brla.gov](https://data.brla.gov/d/a4h4-zi7e) [SEARCH via Socrata API]
- Cuyahoga Land Bank has a "Sheriff Sale Analysis 2021" layer (stale). Case Western has a 2016 "Foreclosure Status" layer. — [Hub search](https://hub.arcgis.com/api/search/v1/collections/all/items?q=sheriff%20sale) [SEARCH]
- Colorado has statewide "Foreclosure Sales in Colorado 2016" (tn2f-pf3u) on data.colorado.gov, last updated 2017 (stale). Cambridge MA "Housing Foreclosures 2003–present" was updated 2024-04-23. — [Socrata catalog](https://api.us.socrata.com/api/catalog/v1?q=foreclosure%20auction) [SEARCH via API]
- NJ CivilView (`salesweb.civilview.com`) responds with an HTML county picker (HTTP 200). It is a search portal, not a file or API. — [CivilView](https://salesweb.civilview.com/) [LIVE]
- `sheriffsaleauction.ohio.gov` did not respond (connection failed) from this session. — [LIVE: no response]

### Inferences
- The Milwaukee and Dakota layers map directly onto the repo's lien model (plaintiff → creditor, defendant → debtor, parcel key) and also give **outcomes** (price, purchaser). They are the highest-value sheriff-sale additions.
- PA/NJ/OH sheriff sales are the largest gap by volume. In PA, Allegheny is already in the repo through WPRDC foreclosures. Other PA, NJ and OH counties mostly use vendor portals (Bid4Assets for Philadelphia, CivilView, RealAuction) [UNVERIFIED for Philadelphia's current vendor].

### Gaps
- Not checked: whether the Philadelphia carto table `real_estate_tax_delinquencies` still exposes a sheriff-sale flag. The table now returns "permission denied" on the public Carto SQL API. — [phl.carto.com](https://phl.carto.com/api/v2/sql?q=SELECT%20*%20FROM%20real_estate_tax_delinquencies%20LIMIT%201) [LIVE: 403]

## 4. Land bank, county/city surplus land, and state surplus land

### Takeaway
Land-bank inventories are widely published as ArcGIS or Socrata layers with parcel IDs, and many are current to November 2026. The strongest are Genesee MI, Lucas OH, Mahoning OH, Kansas City MO, Chicago and Detroit. State surplus land is patchy: CA DGS, Oregon DLCD, WisDOT, OK DOT and NYSDOT (sold history) are the usable ones found.

### Cited Findings: land banks / city-owned [LIVE unless noted]
- **Genesee County Land Bank MI**: 14,053 parcels (July 2025 snapshot), with owner, tax-mailing address, class and homestead. — [ArcGIS](https://services2.arcgis.com/5ckbIY7K9TUKoseK/arcgis/rest/services/Land_Bank_Parcels/FeatureServer/0)
- **Lucas County Land Bank OH**: 1,789 parcels, edited 2026-11-05 (parid, owner, address, legal). — [ArcGIS](https://services3.arcgis.com/T8dczfwPixv79EgZ/arcgis/rest/services/Land_Bank/FeatureServer/0)
- **Mahoning County Land Bank OH**: 2,206 parcels, edited 2026-11-12. A separate Youngstown Land Bank Holdings service exists. Same org as the repo's `oh.mahoning.delinquent_taxes`, different layer. — [ArcGIS](https://services7.arcgis.com/BdxVWim3RqQp6zGH/arcgis/rest/services/Mahoning_Land_Bank_Holdings/FeatureServer/7)
- **Kansas City MO Land Bank & Homesteading Authority (4257-6mtc)**: 6,587 rows, updated 2026-09-21. Fields: parcel_number, acquisition_date, disposition, foreclosure_year, **asking_price, available**, current_owners, quiet_title. — [data.kcmo.org](https://data.kcmo.org/resource/4257-6mtc.json)
- **Chicago City-Owned Land Inventory (aksk-kvfp)**: updated 2026-11-23. Fields: pin, address, property_status, sales_status, sale_offering_status, land_value, application_deadline, offer_round. — [data.cityofchicago.org](https://data.cityofchicago.org/resource/aksk-kvfp.json)
- **Seattle Current City Properties (qhwj-ipk4)**: 1,344 rows, Public Domain, updated 2026-11-22 (city-owned, including status). — [cos-data.seattle.gov](https://cos-data.seattle.gov/resource/qhwj-ipk4.json)
- **Lee County FL "County Lands Surplus"**: 10 parcels, edited 2026-11-16, with STRAP/Folio, SurplusNumber and BidPackage. — [ArcGIS](https://services2.arcgis.com/LvWGAAhHwbCJ2GMP/arcgis/rest/services/County_Lands_Surplus_/FeatureServer/0)
- Others found [SEARCH via Hub/Socrata APIs, not probed]: Detroit Land Bank Authority "DLBA Owned Properties" ([detroitdata.org](https://detroitdata.org/dataset/dlba-owned-properties)), Louisville "Property Available for Purchase" ([data.gov](https://catalog.data.gov/dataset/louisville-metro-ky-property-available-for-purchase)), St. Louis LRA ([stlouis-mo.gov](https://www.stlouis-mo.gov/data/datasets/dataset.cfm?id=30)), Dallas Land Bank Lots/Potential, Cleveland Land Bank Application Layer (2026-09-29), St. Joseph Co IN Land Bank Properties (2026-07-16), Franklin Co OH, Hutchinson KS "Land Bank Listings Active" (2026-01-15), Oakland CA Surplus Properties, and Shelby County TN Land Bank "for sale" ([MapServer](https://uasiportal.shelbycountytn.gov/arcgis/rest/services/LandBank/LBWebApp/MapServer/0), which failed a TLS legacy-renegotiation check from Python here).

### Cited Findings: state surplus land
- **California DGS State Surplus** (Executive Order N-06-19 excess sites): `State_Surplus_Parcels_` has 30 rows (uid, Abbreviation only), edited 2026-10-05. There are also `State_Surplus_Points` and `State_Surplus_Sites_`. — [ArcGIS](https://services8.arcgis.com/a4GMqC2tQHvYiVtK/arcgis/rest/services/State_Surplus_Parcels_/FeatureServer/0) [LIVE]
- **Oregon DLCD Surplus Lands Inventory**: 608 rows (state + local jurisdictions), edited 2026-02-12. Fields: JurisdictionName, Address, ORTaxLot, Acres, Zoning, constraints. — [ArcGIS](https://services.arcgis.com/uUvqNMGPm7axC2dD/arcgis/rest/services/Surplus_Lands_Inventory/FeatureServer/0) [LIVE]
- **NYSDOT "Surplus Properties Sold: Beginning 2009" (869e-5zik)**: 447 rows, updated 2026-11-13. Fields: closing_date, region, county, method_of_disposal, acres, **sale_price**. — [data.ny.gov](https://data.ny.gov/resource/869e-5zik.json) [LIVE]
- **NY ABO "Real Property Transactions of State Authorities" (t7uh-5ac8)**: 2,025 rows (FY to 2025-12-02). Fields: property address, FMV, transaction type, price, **buyer/tenant name**. Sibling datasets cover local authorities, IDAs and LDCs. — [data.ny.gov](https://data.ny.gov/resource/t7uh-5ac8.json) [LIVE]
- Wisconsin DOT "Surplus Land" (modified 2026-11-12), Oklahoma DOT "Surplus_Property_Public_Current", UDOT surplus review candidates, Metropolitan Water District (CA) Surplus Properties, and NPS Historic Surplus Properties Program. — [Hub search](https://hub.arcgis.com/api/search/v1/collections/all/items?q=surplus%20property) [SEARCH via API]
- NYS Thruway historical surplus auction data 2010– (udn2-m26a) was last updated 2013. — [Socrata catalog](https://api.us.socrata.com/api/catalog/v1?q=surplus%20property) [SEARCH via API]

### Inferences
- Land-bank inventories are the easiest category to add: county/city FeatureServers with parcel IDs, refreshed monthly. Ownership by a land bank is also a negative signal for the equity graph (a debtor no longer owns the parcel).
- State surplus is thin. CA and OR are statewide registries mandated by statute (CA Surplus Land Act / EO N-06-19; OR HB 2003-era inventory) [UNVERIFIED on the OR statute]. Most other states publish only PDFs or press releases.

### Gaps
- Not found: a national land-bank registry with data (the Center for Community Progress lists land banks but not their inventories) [UNVERIFIED]. Detroit DLBA's freshness was not probed.

## 5. Federal real property: HUD, USDA RD/FSA, VA, GSA, Treasury/IRS, US Marshals

### Takeaway
**HUD's FHA REO inventory is available as a free, no-login ArcGIS FeatureServer**: 622 homes, refreshed 2026-10-23. This is the single best federal real-estate feed. USDA RD/FSA is a tiny server-rendered search. VA (VRM) and Treasury (CWS) listings are small server-rendered HTML pages. GSA real property (realestatesales.gov) disallows all crawling. The **Federal Register API** carries GSA/HUD Title V surplus notices and BLM "Notice of Realty Action" land sales as structured JSON.

### Cited Findings
- **HUD "FHA Single Family REO Properties For Sale"**: 622 rows, lastEdit 2026-10-23, © HUD. Fields: CASE_NUM, address, CITY, STATE_CODE, ZIP, census block/tract, lat/long, DATE_ACQUIRED, DATE_CLOSED, REVITE_NAME (revitalization area). It has **no list price, bid deadline or listing period**: those stay on HUD Home Store. — [FeatureServer/0](https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/SF_REO/FeatureServer/0) [LIVE]; also listed on [data.gov](https://catalog.data.gov/dataset/fha-single-family-reo-properties-for-sale) [SEARCH]
- HUD Home Store (`hudhomestore.gov`, a Yardi platform) serves `robots.txt: Disallow: /`. Listing cards are rendered client-side; the only "APIs" are third-party Apify scrapers. — [robots](https://www.hudhomestore.gov/robots.txt) [LIVE]; [Apify HUD scraper](https://apify.com/solidcode/hudhomestore-scraper) [SEARCH]
- **USDA RD/FSA REO** (`properties.sc.egov.usda.gov/resales`): server-rendered search forms (searchSFH/searchMFH/searchFSA) with state as a required field. On 2026-11-23 the SFH page listed GA 2, IL 1, KY 2, MS 5, NE 4, SC 1, TN 1 (16 total). There is no export. — [searchSFH](https://properties.sc.egov.usda.gov/resales/public/searchSFH) [LIVE]
- **VA REO via VRM** (`vrmproperties.com`): server-rendered `/Properties-For-Sale?state=..&city=..` pages. robots.txt disallows only /Auth, /Error, /User and /Lead. There is no feed or export. — [VRM](https://www.vrmproperties.com/) [LIVE]
- **Treasury seized/forfeited real property** (IRS-CI, HSI, Secret Service; contractor CWS Asset Management & Sales): a static HTML "Upcoming Auctions" page with about 10 properties on 2026-11-23 (e.g., Silverton OR SFH auction 2026-11-20, Orlando FL office condos 2026-12-11), each with a Sale # and a details page. — [realprop.shtml](https://www.treasury.gov/auctions/treasury/rp/realprop.shtml) [LIVE]; [program](https://www.treasury.gov/auctions/treasury/rp/about.shtml) [SEARCH]
- **US Marshals**: `usmarshals.gov` asset-forfeiture pages return HTTP 403 to a non-browser client (Akamai). A USMS RFI (August 2026) seeks a contractor for real-property valuation, management and disposal. — [USMS](https://www.usmarshals.gov/what-we-do/asset-forfeiture/property-for-sale) [LIVE: 403]; [Starbridge RFI summary](https://starbridge.ai/rfp/usms-asset-forfeiture-program-real-property-services) [SEARCH]
- **GSA real property**: `realestatesales.gov` (auctions) has `robots.txt: User-agent: * Disallow: /`. `disposal.gsa.gov` is a Salesforce Experience Cloud site with no public data endpoint found. — [realestatesales.gov robots](https://realestatesales.gov/robots.txt), [disposal.gsa.gov](https://disposal.gsa.gov/s/) [LIVE]
- **Federal Register API** (free, no key): `"assist the homeless"` + HUD returns 1,234 documents. These are the weekly Title V "Federal Property Suitable as Facilities to Assist the Homeless" notices listing excess federal property. `"notice of realty action"` returns 1,594 documents, newest 2026-11-19 ("Modified Competitive Sale of 20 Parcels of Public Land in Clark County, Nevada"). — [FR API query](https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=%22notice%20of%20realty%20action%22&per_page=3&order=newest) [LIVE]
- usa.gov's "Real estate and federal lands for sale by the government" page lists the official federal outlets, including USMS (seized homes, condos, commercial real estate and land). — [usa.gov](https://usa.gov/real-estate-sales) [SEARCH]
- SAM.gov Opportunities API (notice type "Sale of Surplus Property") returned 404 with `DEMO_KEY` at both `/opportunities/v2/search` and `/prod/opportunities/v2/search`. It likely needs a registered SAM.gov key. — [LIVE: 404; key requirement UNVERIFIED]

### Inferences
- HUD REO joins to parcels only by address or lat/long: there is no APN. HUD-owned means the borrower lost the property, which is a strong "no equity / already foreclosed" signal for the graph.
- Federal Register notices are text (HTML/XML full text). Turning a "Notice of Realty Action" into parcels needs a deterministic parser of PLSS legal descriptions. That is doable without AI but is real work.

### Gaps
- Not found: a free bulk feed of FSA inventory farm property beyond the RD/FSA search, any machine-readable VA Vendee list, or IRS-collection (not forfeiture) seized real-estate sales. IRS auction pages moved (`irs.gov/compliance/irs-auctions` returned 404 here).
- Fannie/Freddie (HomePath/HomeSteps) are GSEs, not government agencies. They are out of scope and were not researched.

## 6. Personal property platforms: GSA Auctions, GovDeals, Public Surplus

### Takeaway
**GSA Auctions has a real free JSON API** (api.data.gov key): 740 active/preview lots on 2026-11-23. It carries personal property only, including IRS-seized items. GovDeals publishes public XML sitemaps (about 28k asset URLs) but no data API. Public Surplus has neither.

### Cited Findings
- **GSA Auctions API**: `https://api.gsa.gov/assets/gsaauctions/v2/auctions?api_key=…&format=JSON` redirects (303) to a pre-signed S3 `active-auctions.json` (2.39 MB). It returned **740 lots** (590 Active, 150 Preview). Fields: saleNo, lotNo, aucStartDt, aucEndDt, itemName, lotInfo (HTML), property address/city/state/zip, agencyName/bureauName, highBidAmount, biddersCount, reserve, contractOfficer, imageURL. Top states: TX 97, OR 61, PA 49, CA 47. `DEMO_KEY` showed `x-ratelimit-limit: 10`. Sample lot: "This sale from the U.S. Internal Revenue Service…". — [API](https://api.gsa.gov/assets/gsaauctions/v2/auctions?api_key=DEMO_KEY&format=JSON) [LIVE]
- The feed is active lots only. No closed-sale or results endpoint was observed in the response. — [LIVE observation]
- **GovDeals** (Liquidity Services): robots.txt sets `Crawl-delay: 5`, disallows `/account/` and `/assets/`, and lists public sitemaps on `files.lqdt1.com`. `Assets_Sitemap_GovDeals.xml` (20.7 MB, UTF-16) holds **28,366** asset URLs (`/en/asset/{account}/{id}`). The asset pages themselves are a JS app. — [robots](https://www.govdeals.com/robots.txt), [sitemap](https://files.lqdt1.com/zstcntr-sitemap/Assets_Sitemap_GovDeals.xml) [LIVE]
- **Public Surplus**: server-rendered per-state browse pages (`/sms/all,{st}/browse/home`). A guessed RSS path returned 404 and no feed link was found on the home page. robots.txt disallows only `/images/`. — [Public Surplus](https://www.publicsurplus.com/sms/browse/home) [LIVE]

### Inferences
- GSA Auctions is trivially ingestible, but personal property (vehicles, equipment) has no parcel link. It only fits the repo if the aggregator covers assets other than real estate.
- For GovDeals, an "index from the sitemap" approach stays inside robots.txt, but each item page still needs rendering and the Liquidity Services ToS was not confirmed. Treat it as not usable for now.

### Gaps
- The GovDeals/Liquidity Services terms of use text could not be extracted (JS app), so the scraping status is UNVERIFIED. Public Surplus terms were not located.

## 7. Mineral and oil-gas lease sales: BLM, BOEM, state land offices

### Takeaway
BLM publishes each quarterly sale's parcels as ArcGIS FeatureServers (Montana-Dakotas, Wyoming and Colorado are current through Q2 2027), plus PDF/XLSX results and annual statistics. Sale notices are also in the Federal Register API. BOEM offers free bulk offshore lease/owner files. State sales (TX GLO, ND, WY, NM, etc.) run mostly on **EnergyNet**, a commercial platform that is not usable. TX GLO posts PDF bid tabulations. Montana DNRC and Oklahoma CLO publish lease GIS.

### Cited Findings
- BLM quarterly sale parcel layers on ArcGIS Online (Hub search): "BLM Montana Dakotas Quarter 2 2027 Oil and Gas Lease Sale Parcels" (2026-11-17), Q1 2027, Q3 and Q4 2026; "BLM WY 2026Q3 Oil and Gas Lease Sale"; WY final-sale-parcel layers 2023–2025; "BLM CO FM Lease Sale Q4 2025"; "BLM CO Deferred Removed Closed Sale Parcels"; "Colorado Lease Sale 2027 Q1 Scoping". — [MT-Dakotas Q2 2027](https://services1.arcgis.com/KbxwQRRfWyEYLgp4/arcgis/rest/services/BLM_Montana_Dakotas_Quarter_2_2027_Oil_and_Gas_Lease_), [WY 2026Q3](https://services6.arcgis.com/doW1zMBdj2GVxvrs/arcgis/rest/services/BLM_WY_2026Q3_Oil_and_Gas_Lease_Sale/FeatureServer) [SEARCH via Hub API, not probed]
- data.gov lists "BLM CO Oil and Gas Lease Sale Q1 (March) 2026" and "BLM CO Oil Gas Lease Sale 2013–2022" polygon datasets. — [data.gov](https://catalog.data.gov/dataset/blm-co-oil-gas-lease-sale-2013-2022) [SEARCH]
- BLM state-office pages post sale notices and results. Examples: a Nevada "September 2026 Day of Sale Summary" PDF, and Alaska NPR-A tract-winner shapefiles and bid recap. The national statistics page links annual tables, including "Table 15 Oil and Gas Lease Sales" (FY2017–FY2024 tables as XLSX/PDF). — [BLM statistics](https://www.blm.gov/programs/energy-and-minerals/oil-and-gas/oil-and-gas-statistics) [LIVE], [NV Sept 2026 summary](https://www.blm.gov/sites/default/files/docs/2026-09/NV%20September%202026%20Day%20of%20Sale%20Summary.pdf) [SEARCH], [Alaska lease sales](https://www.blm.gov/alaska/lease-sales) [SEARCH]
- NFLSS (`nflss.blm.gov`) and MLRS (`mlrs.blm.gov/s/`) both respond (HTTP 200). NFLSS is the expression-of-interest/nomination system and MLRS is a Salesforce case-records portal. Neither exposed a documented bulk sale-results download in this session. — [NFLSS](https://nflss.blm.gov/), [MLRS](https://mlrs.blm.gov/s/) [LIVE: reachable only]
- Federal Register API: BLM + `"lease sale"` returns 318 documents (e.g., "Notice of 2026 Coastal Plain Oil and Gas Lease Sale", 2026-04-20). — [FR API](https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=%22lease%20sale%22&conditions%5Bagencies%5D%5B%5D=land-management-bureau&per_page=4&order=newest) [LIVE]
- **BOEM** (offshore): `data.boem.gov/Main/Leasing.aspx` links free bulk zip files: lease owner (`lseowndelimit.zip`), lease data (`lsetapefixed.zip`), lease list (`lstleasefixed.zip`) and company files. — [BOEM Leasing](https://www.data.boem.gov/Main/Leasing.aspx) [LIVE]
- **Texas GLO**: semi-annual online lease sales run on EnergyNet (e.g., October 21 2025 sale: 56 tracts, 13,019.64 net acres). Bid tabulations are posted as PDF (e.g., `2026-05/Item 9 - Tabulation of Bids.pdf`). — [GLO leasing](https://glo.texas.gov/energy/mineral-leasing/leasing) [LIVE page; sale details SEARCH], [Tabulation PDF](https://www.glo.texas.gov/sites/default/files/2026-05/Item%209%20-%20Tabulation%20of%20Bids.pdf) [SEARCH]
- **EnergyNet** government listing pages (`govt_listing.pl?sg=…`) return a 4 KB shell titled "Efficient Markets Platform" with no data links to a non-browser client. Its `/robots.txt` returns a full HTML page instead of a robots file. — [EnergyNet](https://www.energynet.com/govt_listing.pl?sg=6265) [LIVE]
- Montana DNRC "MMB Oil and Gas Active Lease" and "Trust Lands Surface Tracts" (both modified 2026-11-22). Oklahoma CLO lease data MapServer. Alaska DNR "Lease Sale Tract Current" (2026-02-04). — [MT DNRC](https://services2.arcgis.com/DRQySz3VhPgOv7Bo/arcgis/rest/services/MMB_Oil_and_Gas_Active_Lease/FeatureServer), [OK CLO](https://gis.clo.ok.gov/arcgis/rest/services/Public/OKLeaseData_ExternalProd/MapServer), [AK DNR](https://services1.arcgis.com/7HDiw78fcUiM2BWn/arcgis/rest/services/Lease_Sale_Tract_Current/FeatureServer) [SEARCH via Hub API]
- The NM State Land Office has a GIS data download page (`/maps-gis/gis-data-download/`, HTTP 200). Its lease-sale page URL guessed here returned 404. NM SLO sale results were not located. — [NM SLO GIS](https://www.nmstatelands.org/maps-gis/gis-data-download/) [LIVE]

### Inferences
- BLM and state lease sales sell leases, not land, and the buyers are companies. They connect to the equity graph only through lessee entities, not debtor parcels. They are lower priority for a judgment-to-equity tool and higher priority for a general government-sale aggregator.

### Gaps
- Not found: a single BLM national machine-readable results file per sale (results are per-state PDF/XLSX), BOEM sale-by-sale bid recap as bulk CSV (page not located), or ND/WY/NM state results in machine-readable form (EnergyNet-hosted).

## 8. Past sale results and redemptions (cross-cutting)

### Takeaway
Free machine-readable **results** exist for only a handful of sources: Milwaukee and Dakota sheriff sales (price and buyer), NYSDOT surplus sold (price), NY state-authority dispositions (price and buyer), the Fulton GA tax-deed workflow, and Cook County tax sale (2009–2010 sold/forfeited/buyers, stale). **Redemption** fields were found only in Sonoma CA defaulted tax data and Douglas CO lien schema (subsequent taxes; currently empty).

### Cited Findings
- Milwaukee County foreclosed parcels: Sale_Price and Purchaser — [ArcGIS](https://services2.arcgis.com/s1wgJQKbKJihhhaT/arcgis/rest/services/Foreclosed_Parcels/FeatureServer/25) [LIVE]
- Dakota County MN: SaleAmount by year, 2007–2025 — [MapServer](https://gis2.co.dakota.mn.us/arcgis/rest/services/DCGIS_OL_PropertyInformation/MapServer/80) [LIVE]
- NYSDOT surplus sold: sale_price and method_of_disposal — [data.ny.gov](https://data.ny.gov/resource/869e-5zik.json) [LIVE]
- NY ABO state-authority property transactions: price and buyer name — [data.ny.gov](https://data.ny.gov/resource/t7uh-5ac8.json) [LIVE]
- Sonoma CA defaulted tax: redemption_fee and full-redemption columns — [Socrata](https://data.sonomacounty.ca.gov/resource/bp8v-uax7.json) [LIVE]
- Cook County Treasurer 2009/2010 Annual Tax Sale Sold PINs, Forfeited PINs and Registered Buyers — [Socrata catalog](https://api.us.socrata.com/api/catalog/v1?q=tax%20sale) [SEARCH via API]
- Hillsborough FL weekly tax deed spreadsheet (file number + unclaimed surplus amount) — [hillsclerk.com](https://hillsclerk.com/taxdeeds) [SEARCH]

### Inferences
- Results data is rarer than listings. Where it is absent, the repo's recorded-deed sources can stand in for "sale results" by catching the sheriff's, tax or trustee's deed when it records (where deeds are available: FL Hillsborough, NYC ACRIS, Philadelphia).

### Gaps
- No free redemption feed was found for FL tax certificates, AZ liens, NJ municipal liens or IL tax sales.

## 9. Access/terms summary and highest-leverage first build

### Takeaway
The first build should be (1) HUD FHA REO (national, one FeatureServer), (2) Milwaukee and Dakota sheriff-sale results plus about 10 current county tax-sale and land-bank FeatureServers, which fit the existing ArcGIS lien adapter, and (3) a Federal Register API adapter for federal realty and lease-sale notices. GSA Auctions JSON is cheap to add if non-real-estate assets are in scope. Every platform-hosted sale (RealAuction, LienHub, GovEase, Bid4Assets, EnergyNet, HUD Home Store, realestatesales.gov) should be treated as not usable.

### Cited Findings: usable (free, bulk/API, no login), none in the repo
| Source | Coverage | Format | Fresh | Parcel key | Results? |
|---|---|---|---|---|---|
| HUD FHA SF REO | national, 622 homes | ArcGIS FS | 2026-10-23 | address, lat/long | acquired/closed dates |
| GSA Auctions API | national federal surplus, 740 lots | JSON (api.data.gov key) | live | none (personal property) | high bid only |
| Federal Register API | federal notices (HUD Title V, BLM realty, lease sales) | JSON + full text | daily | legal descriptions | no |
| Milwaukee Co WI foreclosed | county sheriff sales, 400 | ArcGIS FS | 2026-11-06 | taxkey | price, purchaser |
| Dakota Co MN sheriff sales | county 2007–2025 | ArcGIS MapServer | 2026-01 | CRN | price |
| Lucas OH forfeited + land bank | county | ArcGIS FS | 2026-11 | parid | no |
| Lake CO / Douglas CO tax liens | county | ArcGIS FS | 2026-10/11 | account/parcel | lien schema |
| Maricopa AZ unsold liens | county, 1,455 | ArcGIS FS | 2026-11-22 | APN | no |
| Cochise AZ tax deed auction | county, 345 | ArcGIS FS | 2026-06 | APN | min bid |
| St. Joseph IN tax sale | county, 1,266 | ArcGIS FS | 2026-08 | parcel | no |
| Wyandotte KS tax sale | county, 161 | ArcGIS FS | 2026-08 | parcel | min bid |
| Fulton GA tax deed activity | county, 33,912 | Socrata (CC-BY) | 2026-11-22 | parid | workflow |
| Sonoma CA defaulted tax | county, 9,789 | Socrata | 2026-11-21 | APN | redemption |
| NYC tax lien sale lists | city, 264k | Socrata | 2025-12 | BBL | no |
| Genesee MI / Mahoning OH / KCMO land banks | county/city | ArcGIS / Socrata | 2025-07 to 2026-11 | parcel | KC: disposition, price |
| Chicago city-owned land, Seattle city properties | city | Socrata | 2026-11 | PIN | sales status |
| CA DGS state surplus, OR surplus lands, NYSDOT sold, NY ABO | state | ArcGIS / Socrata | 2025-12 to 2026-11 | varies | NYSDOT/ABO prices |
| BLM quarterly sale parcels (MT-Dak, WY, CO) | federal minerals | ArcGIS FS | through Q2 2027 | PLSS | separate PDFs |
| BOEM leasing bulk | offshore | zip (fixed/delimited) | periodic | lease/block | owners |
(Sources are cited in sections 2–8 above.)

### Cited Findings: not usable (login, CAPTCHA, bot-block, robots disallow, or search-portal only)
- RealAuction realtaxdeed/realforeclose: 403 to non-browser clients [LIVE]. LienHub: Cloudflare challenge [LIVE]. realestatesales.gov and hudhomestore.gov: robots `Disallow: /` [LIVE]. usmarshals.gov: 403 [LIVE]. EnergyNet: JS shell [LIVE]. disposal.gsa.gov and MLRS: Salesforce portals [LIVE]. NJ CivilView, USDA resales, VRM, Public Surplus and Treasury realprop: HTML search or listing pages only (usable only as portal scraping, which is excluded) [LIVE]. Bid4Assets / GovEase / SRI-Zeus: no public feed found; terms not confirmed [LIVE/UNVERIFIED].

### Inferences
- **Highest-leverage first build:**
  1. `us.hud.fha_reo` (one FeatureServer, national, address join).
  2. A batch of county ArcGIS sale layers using the existing `config/liens` ArcGIS pattern: Milwaukee, Dakota (multi-year, results), Lucas, Maricopa unsold liens, Cochise deed auction, Lake CO, St. Joseph IN, Wyandotte, plus land banks (Genesee, Lucas, Mahoning, KCMO).
  3. A scheduled Hub/Socrata discovery job that flags new "tax sale / sheriff sale / land bank / surplus" layers by keyword. This is the only realistic path to 50-state county coverage.
  4. `us.federalregister.realty_notices` for BLM/GSA/HUD notices.
  5. Optional `us.gsa.auctions` JSON.
- Because these layers are snapshots, adapters should store each pull (transaction time) so that a parcel's disappearance from a sale list can be read as sold, redeemed or withdrawn. The repo's supersession model already supports that.

### Gaps
- License and terms were not checked per county layer. Most ArcGIS Online items carry no explicit license. The repo's `no_resale` / `attribution_required` flags will need per-source review (e.g., Fulton is CC-BY-4.0, Seattle is Public Domain).
- Not verified: whether SAM.gov's "Sale of Surplus Property" notices are reachable with a free registered key, and the current terms text of GovDeals, Bid4Assets and RealAuction.
