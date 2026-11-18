# Free statewide parcel data: MT through WY, plus DC (Phase 0 research)

Researched 2026-11-15. Scope: 25 states plus DC. This is research only; nothing was downloaded in bulk.

## How to read this

- **Method.** WV was checked directly against its official servers (curl/WebFetch). The other hosts are outside the sandbox allowlist, so every other row comes **only from WebSearch result summaries** of official pages and ArcGIS REST endpoints. I did not open those pages myself, and I did not retry blocked hosts.
- **Confidence tags.**
  - **VERIFIED**: I fetched the official source myself and saw the fields. Only WV gets this tag.
  - **VERIFIED\***: Search results quoted or summarized the official page or REST layer and named the relevant fields. I did not open the page myself.
  - **LIKELY**: Secondary sources, partial official info, or inference (including "no statewide source found").
  - **UNKNOWN**: Not enough information either way.
- **Commercial fallback prices (vendor-published, check before buying).**
  - Regrid's Jan-2023 list price for one state (annual license) was $8,000 for the standard schema, $12,000 for premium, and $20,000 for premium with building footprints. A single county was $300, $500 or $800 on the same tiers. Regrid gives no current per-state price list ("contact parcels@regrid.com").
  - ReportAll: Texas statewide is $7,000 and each county is $200, with up to 20% off for multi-county orders.
  - Treat these as rough estimates for every "county-by-county" row.
- **Commercial use.** This is for a commercial judgment-buying business. Where a row says "terms not read", nobody has confirmed the license yet. Get the actual terms before production use.

## Summary table

| State | Free statewide? | Publisher + URL | Owner? | Value? | Coverage | Access | Terms/commercial use | Confidence | Notes |
|---|---|---|---|---|---|---|---|---|---|
| MT | Yes | Montana State Library, MSDI Cadastral Framework (data from MT Dept of Revenue ORION CAMA). Help: https://docs.msl.mt.gov/geoinfo/cadastral/MontanaCadastralHelp.pdf ; REST: https://gisservice.mt.gov/ArcGIS/rest/services/msdi_cadastral_map_v1/MapServer ; FTP path cited in metadata: ftpgeoinfo.msl.mt.gov/Data/Spatial/MSDI/Cadastral/Parcels | Yes: OwnerName plus owner address (from ORION) | Yes: TotalValue (per search snippet of a statewide service) | All 56 counties (FTP has 56 county folders, each with a GIS file and a CAMA file). Updated monthly. | Bulk download (FTP, by county) + REST + web app | Free. **Metadata cites MCA 2-6-1017**: agencies may not distribute or sell a "distribution list" of persons without their permission, and such lists can't be used for unsolicited contact. **Risk for mailing or outreach use.** | VERIFIED\* (owner) / LIKELY (value field) | Five counties keep their own parcel geometry (Ravalli, Silver Bow, Missoula, Flathead, Yellowstone). The CAMA table joins on geocode. Get a legal read on 2-6-1017 before using owner names for outreach. |
| NE | Yes (dataset exists) | NE Office of the CIO, NebraskaMAP "Statewide Parcels": https://www.nebraskamap.gov/datasets/statewide-parcels | UNKNOWN | UNKNOWN (preview shows numeric value columns, but no headers were visible) | Built annually from each county's CAMA plus GIS. 2025 file has about 1,154,898 rows; how many of the 93 counties is not stated. FGDBs listed for 2024 and 2025. | FGDB download + feature service | Terms not read | LIKELY (exists) / UNKNOWN (fields) | Check the field list next. The preview's metadata looked stale ("updated ~829 days ago"). |
| NV | No | No public statewide source. NV Division of Water Resources has "County Parcels in Nevada" (https://arcgis.water.nv.gov/arcgis/rest/services/BaseLayers/County_Parcels_in_Nevada/MapServer), but its terms say the data **cannot be shared outside the department (NRS 250)**. NDOT's statewide service (gis.dot.nv.gov .../Reference/Statewide_Parcels) is dated 2018-12-31. | n/a | n/a | County-by-county (17 counties; Esmeralda has no digital parcels) | County assessor sites | DWR copy is **not redistributable** | LIKELY | Commercial fallback: Regrid state about $8k (2023 list) or by county. |
| NH | Partial (boundaries) | NH Dept of Revenue Administration, NH Parcel Mosaic (hosted by UNH GRANIT): https://nhgeodata.unh.edu/nhgeodata/rest/services/CAD/ParcelMosaic/MapServer (also misspelled "ParcelMosiac") ; hub: https://www.nhgeodata.unh.edu/datasets/nh-parcel-mosaic-polygons | **No** in the public layers (fields such as PID, NH_GIS_ID, Town, SLU, StreetAddress). A CAMA table (layer 3) exists, but the public data carries only a subset of about 50 attributes. | UNKNOWN / probably not | "Communities in NH". Some towns have only linework, not polygons. | REST + hub download | Copyright NH DRA and Axiomatic. License not read. | LIKELY | The NHDOT mapper has a "search by owner" function, so owner data may exist in a restricted copy. Owner and value have to come town by town (234 municipalities) or from a vendor. |
| NJ | Yes | NJ Office of GIS (NJOGIS), "Parcels and MOD-IV Composite of NJ": https://nj.gov/njgin/edata/parcels/ ; FeatureServer: https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0 ; metadata: https://www.nj.gov/dep/gis/digidownload/metadata/html/Cad_parcel_mod4.html | **No**: OWNER_NAME is redacted in every hosted download and service under Daniel's Law | Yes (MOD-IV assessed land, improvement and net values; field names inferred, not seen in snippets) | All 21 counties / all municipalities. A news item mentions a tax-year-2022 update; the current vintage was not confirmed. | FGDB download (parcels joined with MOD-IV) + MOD-IV table download + REST | Free. License not read. | VERIFIED\* (owner redaction) / LIKELY (values) | Owner names have to come from county or municipal tax records. Daniel's Law also limits redistributing covered persons' addresses. |
| NM | No | None found. Search returned only Regrid and LandRecords. | n/a | n/a | County-by-county (33 counties) | County assessors | n/a | LIKELY | Commercial: Regrid statewide (about 1.58M parcels). |
| NY | Yes, partial | NYS ITS Geospatial Services, "NYS Tax Parcels Public": https://gis.ny.gov/parcels ; REST: https://gisservices.its.ny.gov/arcgis/rest/services/NYS_Tax_Parcels_Public/MapServer and https://nysgeohub.ny.gov/arcgis/rest/services/Parcels/NYS_Tax_Parcels_Public/FeatureServer | Yes: PRIMARY_OWNER (plus mailing fields) | Yes: LAND_AV, TOTAL_AV, FULL_MARKET_VAL | **38 of 62 counties** (2025 file, published May 2026). Updated annually. | FGDB download + REST | Only counties that gave ITS permission to share publicly are included. Others "must be obtained directly from those counties" (several charge). "Planning and general use." | VERIFIED\* | The county list and whether NYC is included were not confirmed. Excluded counties go county by county. |
| NC | Yes | NC Dept of IT / CGIA, NC OneMap "NC Parcels": https://data.nconemap.gov ; REST: https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer (also services.gis.nc.gov) | Yes: OWNNAME (+OWNNAME2) and mailing address | Yes: PARVAL (total), IMPROVVAL, LANDVAL, PARVALTYPE | **All 100 counties** plus Eastern Band of Cherokee lands. Refreshed weekly. | Bulk download by county or all at once + REST | Terms page nconemap.gov/pages/terms **not read** | VERIFIED\* | One of the best sources. Read the terms page before commercial use. |
| ND | Yes | ND Information Technology, State Parcel Program on ND GIS Hub: https://gishubdata-ndgov.hub.arcgis.com/datasets/NDGOV::parcels/explore ; tax roll table: https://gishubdata-ndgov.hub.arcgis.com/datasets/parcels-taxroll | LIKELY, in the TaxRoll table (one-to-many on UniqueGISID). Not confirmed. | LIKELY (TaxRoll). Not confirmed. | All 53 counties contributing. About 727k parcels / 731k tax-roll rows (Jul 2023). Focus is rural; **some city parcels missing**. | Zipped FGDB download + feature service | "Limitations of Use" section in the metadata not read | LIKELY | Check the TaxRoll schema (gis.nd.gov Parcel Program dataset schema, Aug 2021). |
| OH | Yes | OGRIP (Ohio DAS), "Ohio Statewide Parcels Public View": https://ohioparcels-geohio.hub.arcgis.com/ ; ODNR copy: https://gis.ohiodnr.gov/arcgis/rest/services/OIT_Services/odnr_landbase/MapServer/4 | Yes: OWNER1, OWNER2 (ODNR copy) | UNKNOWN (fields not confirmed) | Described as all 88 counties. Dates conflict: "Updated Jan 21, 2024" vs. May 14, 2025. | Hub downloads (CSV, GeoJSON, zip, etc.) + REST | Custom license: "available for public use at the user's own risk", informational only. OGRIP says public downloads "have no use restrictions." | LIKELY | Values and mailing address go to the 88 county auditors, which mostly offer free downloads. |
| OK | No | None found. OKMAPS has no parcel layer. | n/a | n/a | County-by-county (77 counties) | County assessors (many run on vendor platforms) | n/a | LIKELY | Commercial: LandRecords, Regrid, ReportAll. |
| OR | No (in progress) | Oregon GEO Statewide Parcels Initiative (started 2023; pilot of 5 counties, expansion through June 2026). ORMAP (https://catalog.data.gov/dataset/ormap-the-oregon-property-tax-map) offers PDF maps and a viewer only. | n/a | n/a | County-by-county (36 counties). No public statewide layer was confirmed as of Sept 2026. | County assessors; ORMAP viewer | Some state-held copies carry sharing restrictions | LIKELY | Check GEOHub again in 2027. |
| PA | No | None. PASDA (pasda.psu.edu) hosts *some* county parcel layers. | n/a | n/a | County-by-county (67 counties) | PASDA + county GIS | Varies by county; some charge fees | LIKELY | Commercial: Regrid about 5.95M parcels statewide. |
| RI | No (in progress) | RIGIS is aggregating 39 municipal layers (37 submitted per the Fall 2025 newsletter). A RIDEM "Tax_Parcels" service exists at risegis.ri.gov, contents unknown. | n/a | n/a | Municipality-by-municipality (39) | Town assessor sites (many on Vision/VGSI) | n/a | LIKELY | No released statewide product found. Commercial: Regrid about 398k parcels. |
| SC | No | None found. Revenue & Fiscal Affairs has a GIS hub with a few county shapefiles. SCDNR says "Parcel Data: contact the county." | n/a | n/a | County-by-county (46 counties) | County GIS / assessor | Varies | LIKELY | Commercial: Regrid or LandRecords (about 2.9–3.0M parcels). |
| SD | No | None found | n/a | n/a | County-by-county (66 counties) | County | n/a | LIKELY | Commercial: Regrid statewide (785,179 parcels). |
| TN | Yes (most counties) | TN Comptroller, Division of Property Assessments: https://comptroller.tn.gov/office-functions/pa/gisredistricting/redistricting-and-land-use-maps/parcel-data.html | Yes: Assessment_Data_##.dbf joins on GISLINK and adds "owner, property, building, land use, and assessment" fields | Yes (assessment fields; exact names are in the field-dictionary spreadsheet) | **86 of 95 counties.** Not covered: Chester, Davidson, Hamilton, Hickman, Knox, Montgomery, Rutherford, Shelby, Williamson. Updated weekly. | Shapefile download by county | **Page says shapefile data "can be used in a commercial application."** No historical or automated extracts. | VERIFIED\* | The 9 big or excluded counties (Nashville, Memphis, Knoxville, Chattanooga, etc.) need county sources. |
| TX | Yes, partial | TxGIO (TNRIS), StratMap Land Parcels: https://www.geographic.texas.gov/stratmap/land-parcels.html ; REST: https://feature.geographic.texas.gov/arcgis/rest/services/Parcels/stratmap_land_parcels_48_most_recent/MapServer | Yes: owner_name plus mailing address | Yes: LAND_VALUE, IMP_VALUE, MKT_VALUE (filled where the appraisal district supplied them) | "Not all" of 254 counties; count not confirmed. Annual refresh (2025 service exists). | Shapefile/FGDB download + REST | Free "at no cost". Data is provided "as-is"; formal license not read. | VERIFIED\* | Check the availability map for gaps. ReportAll TX statewide is $7,000. |
| UT | Yes (boundaries) | UGRC, SGID Utah Parcels: https://gis.utah.gov/products/sgid/cadastre/ ; LIR FeatureServer: https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_Utah_LIR/FeatureServer | **No**: only OWN_TYPE (Federal, Private, State, Tribal) | Basic: no. LIR parcels carry tax-roll attributes for **some** counties only. | All 29 counties (basic boundaries) | Download (UGRC open data) + REST | **CC BY 4.0** by default (UGRC license policy), so commercial use is OK with attribution | VERIFIED\* | Owner names: county recorder or assessor. |
| VT | Yes | VCGI (Agency of Digital Services), Statewide Standardized Parcel Data joined with the Grand List. Metadata: https://maps.vcgi.vermont.gov/gisdata/metadata/CadastralParcels_VTPARCELS.htm ; download via geodata.vermont.gov | Yes: OWNER1 (Grand List owner of record as of April 1) | LIKELY (Grand List values; field names not confirmed) | Statewide program, downloadable as one statewide file or by town. Grand List attributes updated yearly. | Bulk download + streaming service | Free; license not read | VERIFIED\* (owner) / LIKELY (value) | A geometry-only version without the join also exists. |
| VA | Yes (boundaries) | VDEM / VGIN, Virginia Parcels: https://vgin.vdem.virginia.gov/pages/cl-data-download (clearinghouse) | **No**: attributes limited to locality ID and parcel ID | **No** | Statewide. Localities submit twice a year and VGIN publishes quarterly. Not confirmed that every one of the 133 localities is included. | Bulk download + REST | "Openly available without charge." Dataset license not read. | VERIFIED\* | Owner and value: 133 locality assessors. Commercial: Regrid or ReportAll. |
| WA | Yes (no owner) | WaTech, Washington Statewide Parcels (public no-owner version on geo.wa.gov). Current_Parcels FeatureServer: https://services.arcgis.com/jsIt88o09Q0r1j8h/ArcGIS/rest/services/Current_Parcels/FeatureServer/0 ("Parcels_2026", updated April 2026) | **No** (owner and taxpayer fields exist only in a state-internal version) | **Yes**: VALUE_LAND and VALUE_BLDG (aliases "Market Land/Building Value") | Counties that have digital parcels (full 39-county coverage not confirmed) | GDB download + REST (maxRecordCount 2000) | Free. **Some counties restrict the owner version to "State of Washington business only."** | VERIFIED\* | Owner names: 39 county assessors. |
| WV | **Yes** | WV GIS Technical Center + WV Property Tax Division. REST: https://services.wvgis.wvu.edu/arcgis/rest/services/Planning_Cadastre/WV_Parcels/MapServer ; bulk download: https://data.wvgis.wvu.edu/pub/Clearinghouse/planningLanduseCadastres/Parcels/WVGISTC_2026/ ; viewer: https://www.mapwv.gov/parcel/ | **Yes**: owner name(s), care-of, full mailing address, plus pending "NewOwner" and new book/page | **Yes**: LandAppraisal, BuildingAppraisal, TotalAppraisal, Dwelling/Commercial/OtherBuilding values. These are *appraised* values; no separate "assessed" field. | **All 55 counties.** TaxYear 2026 on all 1,503,439 rows. Monongalia (31) is included. | Bulk FGDB (statewide and per county) + ArcGIS REST query (max 2000/request, paging supported) + viewer | Free (SB 588, 2017: GIS files downloadable at no charge). As-is disclaimer. **No explicit license or commercial-use clause found.** robots.txt does not block. | **VERIFIED** | See the detail section below. There is also a statewide **Delinquent_Properties** service, relevant to tax liens. |
| WI | Yes | WI DOA + State Cartographer's Office, Statewide Parcel Map **V12 (2026)**: https://www.sco.wisc.edu/parcels/data ; FeatureServer: https://services3.arcgis.com/n6uYoouQZW75n5WI/ArcGIS/rest/services/Wisconsin_Statewide_Parcels_DB/FeatureServer/0 ; schema: https://sco.wisc.edu/parcels/data/assets/V12/V12_Wisconsin_Statewide_Parcels_Schema_Documentation.pdf | Yes: OWNERNME1, OWNERNME2, PSTLADRESS (owner mailing) | Yes: CNTASSDVALUE, LNDVALUE, IMPVALUE, ESTFMKVALUE (null for ag/MFL parcels) | **All 72 counties**, about 3.57M parcels. Released June 2026. | Bulk download (statewide or by county) + REST | Free; formal license not read | VERIFIED\* | DOA keeps owner names "as much as possible while complying with law", so some may be redacted. Tax-roll attributes lag the geometry by about a year. |
| WY | No (viewer only) | WY Dept of Revenue Property Tax Division "Statewide Parcel Viewer": https://wyo-prop-div.wyo.gov/tax-districts/maps-gis-data ; DEQ map service: https://gis.deq.wyo.gov/arcgis/rest/services/WY_PRIVATE_PARCELS/MapServer (credits DOR and county assessors; maxRecordCount 1000; fields not seen) | UNKNOWN in the DEQ service | UNKNOWN | Statewide viewer covers 23 counties. No parcel bulk download is listed (only tax-district shapefiles). | Viewer; DEQ REST (use rights unclear) | Not stated | LIKELY | Treat as county-by-county for owner and value. Commercial: Regrid or LandRecords. |
| DC | Yes | DC OCTO / OCFO, Open Data DC. Owner Polygons (Common Ownership Lots): https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Property_and_Land/MapServer/40 ; ITSPE tax extract: https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Property_and_Land/MapServer/53 | Yes: OWNERNAME ("Property Owner's Name") in ITSPE; OWNER_NAME_PRIMARY in ITSPE FACTS (layer 56) | LIKELY (ITSPE carries assessment and cap fields; exact assessed-value field name not confirmed) | Entire District (about 220k ITSPE rows). Updated regularly. | Download (CSV, GeoJSON, SHP) + REST | **CC BY 4.0**, so commercial use is OK with attribution | VERIFIED\* (owner, license) / LIKELY (value) | Joins on SSL (square, suffix, lot). |

### Counts (26 rows)

- **Free statewide with owner and value (9):** MT, NY (38/62 counties), NC, TN (86/95), TX (partial), VT, WV, WI, DC.
- **Free statewide with owner, value unconfirmed (2):** OH, ND.
- **Boundaries without owner (5):** NJ and WA have values; UT, VA and NH have no values.
- **Statewide layer exists, fields unknown (1):** NE.
- **County-by-county, no free public statewide (9):** NV, NM, OK, OR, PA, RI, SC, SD, WY.

---

## WV statewide layer detail

Everything in this section was fetched directly on 2026-11-15, in about 20 small requests and no bulk pulls.

### Services

The ArcGIS root `https://services.wvgis.wvu.edu/arcgis/rest/services` runs ArcGIS Server 11.4. The `Planning_Cadastre` folder holds two services.

**`Planning_Cadastre/WV_Parcels/MapServer`**
- Document title: "FloodTool Parcel and Address Service".
- Description: "This service provides parcel geometry, parcel labels and address labels. Address labels provided by the WVSAMS-II, WVDHSEM".
- copyrightText: "WV County Assessor, WV Property Tax Division, WVDHSEM, WVGISTC".
- Capabilities: `Map,Query,Data`. Query formats: `JSON, geoJSON, PBF`.
- **maxRecordCount: 2000**, for the service and for each layer and table. `supportsPagination: true`, so `resultOffset` paging works.
- Layers:
  - Layer **0 `WVParcels`**: polygons.
  - Layer **1 `Districts`**.
  - Layer **5 `Site Address Points`**.
  - Table **11 `ParcelSummary`**: the full CAMA/IAS attribute table.
- The layer 0 description still says "updated for Tax Year 2023", but the table data is TaxYear 2026 (see below).

**`Planning_Cadastre/Delinquent_Properties/MapServer`**
- Layer 0 is "Statewide Delinquent Properties (point)" and layer 1 is "(polygon)". maxRecordCount 2000.
- Fields: `OBJECTID, Shape, tblInput_latest_status, ORIG_FID, OBJECTID_1, ROOTID, CODIST, CleanParcelID, Label, GISPID, Dist, Map, Parcel, Suffix, CountyID, FloodRisks, FullLegalDescription, FullOwnerName, FullOwnerAddress, FullPhysicalAddress, Acres_C, Sensitive, PID, FREQUENCY, MAX_certno, county, name_1, name_2, description, district, municipality, status, certno, map_1, parcel_1, deed_book, page_number, account_number`.
- The MapWV FAQ says this layer is updated **weekly** from the State Auditor's delinquent and nonentered lands records.

### Layer 0 `WVParcels` fields (polygons)

`Map, Parcel, Suffix, Label, CleanParcelID (str 30), Shape, GISPID, ROOTID, CODIST, Dist, OBJECTID, CountyID (str 2), FullLegalDescription, FullOwnerName (100), FullOwnerAddress (200), FullPhysicalAddress (200), IAS_LEGAL, OWNER1, OWNER2, COUNTY, CALC_ACRE`

### Table 11 `ParcelSummary` fields (join to layer 0 on `CleanParcelID`)

- **IDs and location:** ID, CleanParcelID, CountyCode (int), CountyName, ParcelID, DistrictCode, DistrictName, Map, ParcelNumber, Suffix, Card, Cards, CommercialCard
- **Legal and acreage:** LegalDescription1/2/3, FullLegalDescription, DeededAcres, CalculatedAcres
- **Tax:** **TaxYear**, TaxDistrict, TaxClass, PropertyClassCode, PropertyClassDescription, LandUse, LandUseCode
- **Deed:** **DeedBook, DeedPage**. Pending transfer: **NewOwner, NewOwnerAddress1/2/3, FullNewOwnerAddress, NewBook, NewPage**
- **Owner:** **Owner1, Owner2, FullOwnerName, CareOf**
- **Owner mailing address:** **OwnerAddress1/2/3, OwnerCity, OwnerStateCode, OwnerZipCode, FullOwnerAddress**
- **Situs (IAS):** PhysicalNumber, PhysicalDirection, PhysicalStreet, PhysicalSuffix, PhysicalSuffix2, PhysicalCity, PhysicalZip, PhysicalZipPlus4, FullPhysicalAddress
- **Situs (E-911 / SAMS):** SAMSAddress, SAMSCity, SAMSState, SAMSZip, PREADDRNUM, ADDRNUM, ADDRNUMSUF, FULLNAME, UNITTYPE, UNITID, ALTUNITTYPE, ALTUNITID
- **Building:** OccupancyDescription, HazardOccupancyCode, YearBuilt, Grade, StyleCode, StyleDescription, Stories, CommercialStories, BasementType, CommercialBasement, ExteriorWallType, ExteriorWallCommercial, ConstructionType, TotalRooms, UseType, BusinessLivingArea, StructureArea, CubicFeet, Units, OBYCount
- **Values:** **DwellingValue, CommercialValue, OtherBuildingYardValue, LandAppraisal, BuildingAppraisal, TotalAppraisal**
- **Other:** FloodRisks

Notes on values: there is no separately labeled "assessed value" field. WV assesses real property at 60% of appraised value (this is general knowledge of WV law, not something stated in the service), so assessed value would be about `TotalAppraisal × 0.6`.

### Coverage and vintage (measured with count and statistics queries)

- **ParcelSummary:** 1,503,439 rows across **55 distinct CountyCodes (all 55 WV counties)**. **Every row is `TaxYear = 2026`.**
- **WVParcels polygons:** 1,394,081 statewide. 1,378,573 of them (98.9%) have a non-null FullOwnerName.
- **Monongalia** (`CountyID='31'` / `CountyCode=31`, FIPS 54061) **is included**:
  - 55,287 polygons, of which 54,981 have an owner name.
  - 65,497 ParcelSummary rows. There are more rows than polygons because of multiple cards per parcel and stacked or condo parcels.

### Sample query

Request:

```
GET .../WV_Parcels/MapServer/11/query?where=CountyCode%3D31&outFields=*&resultRecordCount=2&f=json
```

The response came back with `exceededTransferLimit: true`, so paging works. Here is one record, with personal names and addresses redacted in this write-up (the live data has them populated):

```
CleanParcelID 31140024000400010000 | CountyName Monongalia | DistrictName Morgantown-6th Ward Corp
TaxYear 2026 | TaxClass 2 | DeedBook 1785 | DeedPage 654 | PropertyClass R Residential
Owner1/FullOwnerName [individual name] | FullOwnerAddress [street], MORGANTOWN, WV 26505
LandUse 101 - Residential 1 Family | YearBuilt 2018 | StructureArea 1200
LandAppraisal 57400 | BuildingAppraisal 118800 | TotalAppraisal 176200 | FloodRisks Low
```

The same query against layer 0 (`CountyID='31'`, `returnGeometry=false`) returned polygon rows with `GISPID` (for example 31-00-3001-2003-5000) and `CALC_ACRE`. The first two rows returned happened to have null owner fields, but 99.4% of Monongalia polygons do have owner names. For owner, value and deed fields, use table 11 joined on CleanParcelID.

### Bulk download (clearinghouse directory listing, nothing downloaded)

`https://data.wvgis.wvu.edu/pub/Clearinghouse/planningLanduseCadastres/Parcels/WVGISTC_2026/`

| File | Size (bytes) | Date |
|---|---|---|
| `WV_Parcels_raw_2026.gdb.zip` | 306,303,568 | 2026-09-18 |
| `WV_WVGISTC_Tax_2026.gdb.zip` | 532,301,070 | 2026-09-23 |
| `CountySplits/Monongalia_31_WVGISTCTax_2026_UTM83.zip` | 355,740,526 | 2026-08-03 |

- CountySplits has one zip per county (01 Barbour through 55 Wyoming). Kanawha was re-posted on 2026-09-23.
- A 2025 folder is also referenced. PDF tax maps are under `.../wv_tax_maps/`.
- I did not open the FGDBs. Their schema is presumably the same as the service's, but that is not verified.
- The WV Tax Division page `https://tax.wv.gov/Business/PropertyTax/FormsAndPublications/SurfaceMaps/Pages/PropertyTaxSurfaceMaps.aspx` links to a "West Virginia Surface Map Database File" (`https://cdn.wv.gov/taxdept/PropertyTax/PropertyTax.SurfaceMaps.gdb.zip`). I did not fetch it because cdn.wv.gov is not on the allowlist.

### robots.txt

| Host | Result |
|---|---|
| `services.wvgis.wvu.edu` | 404 (none) |
| `data.wvgis.wvu.edu` | 404 (none) |
| `mapwv.gov` / `www.mapwv.gov` | 200, `User-agent: *` with **no Disallow lines**, so all crawling is allowed |
| `tax.wv.gov` | 404 (SharePoint "file not found") |
| `gis.transportation.wv.gov` | 404 (none) |

### Terms of use

- **Layer 0 disclaimer:** "provided as a public service, as is, as available, and without warranties … County Assessors and Clerk offices should be consulted for verification."
- **MapWV FAQ** (https://mapwv.gov/parcel/template/helpPanel.html):
  - "The passing of SB 588 in July 2017 permitted the WV Property Tax Division to allow all digital surface tax maps and GIS files to be downloaded at no charge … from an authorized tax map distribution site located at the State Data Clearinghouse."
  - Privacy: property records and maps "are not private information."
  - Parcels are "for property tax assessment purposes only and do not represent legal boundaries"; the co-custodians have "no liability to any third party."
  - Search results are capped at 1000 records in the viewer.
- **No license, registration requirement, non-commercial clause or resale clause** appeared on any WV host I could reach.
- One search summary said a WVDOT parcel layer is limited to "internal, non-commercial purposes." I could **not** find that text in the WVDOT iteminfo I fetched (`gis.transportation.wv.gov/.../Economic/MapServer/5` and `/7`). Those layers are WVDOT extracts anyway, not the WVGISTC source.
- W. Va. Code §11-1C-7 (via search snippet) says tax maps "shall be made available for sale" by assessors and the Property Tax Division. That is a conflicting signal, though SB 588 and Rule 189-5-3 allow free download.
- **Recommendation:** email WVGISTC or the Property Tax Division to confirm commercial reuse before relying on it.

---

## Sources by state

Except for WV, these were seen only through WebSearch results.

- **MT:**
  - https://docs.msl.mt.gov/geoinfo/cadastral/MontanaCadastralHelp.pdf
  - https://gisservice.mt.gov/ArcGIS/rest/services/msdi_cadastral_map_v1/MapServer
  - https://gisservice.mt.gov/ArcGIS/rest/services/msdi_cadastral_map_v1/MapServer/1
  - https://gis.dnrc.mt.gov/arcgis/rest/services/WRD/WRB_MSL_Historic_Parcels/MapServer/1/metadata
  - https://mca.legmt.gov/bills/2015/mca/2/6/2-6-1017.htm
  - https://archive.legmt.gov/content/Committees/Interim/2017-2018/Water-Policy/Meetings/Jan-2018/DistributionListMemo-DNRC.pdf
- **NE:**
  - https://www.nebraskamap.gov/datasets/statewide-parcels
  - https://www.nebraskamap.gov/content/ba7dda0642cd4c0c9660a35081fee517
  - https://www.nebraskamap.gov/
- **NV:**
  - https://arcgis.water.nv.gov/arcgis/rest/services/BaseLayers/County_Parcels_in_Nevada/MapServer
  - https://arcgis.water.nv.gov/arcgis/rest/services/BaseLayers/County_Parcels_in_Nevada/MapServer/0/iteminfo?f=pjson
  - https://gis.dot.nv.gov/agsphs/rest/services/Reference/Statewide_Parcels/MapServer/0
  - https://www.landrecords.us/documentation/coverage/states/32-nevada
- **NH:**
  - https://nhgeodata.unh.edu/nhgeodata/rest/services/CAD/ParcelMosaic/MapServer
  - https://nhgeodata.unh.edu/nhgeodata/rest/services/CAD/ParcelMosiac/MapServer
  - https://www.nhgeodata.unh.edu/datasets/nh-parcel-mosaic-polygons
  - https://www.nhgeodata.unh.edu/datasets/89983c1affc74805b7f5e997e3c1d6e8_0/about
  - https://granitweb.sr.unh.edu/MetadataForViewers/CommonViewers/lite/Parcels.html
  - https://experience.arcgis.com/experience/148ee63e49394146b8d3f2aeaa2400c4/page/Search-Parcels
- **NJ:**
  - https://nj.gov/njgin/edata/parcels/
  - https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/Parcels_Composite_NJ_WM/FeatureServer/0
  - https://www.nj.gov/dep/gis/digidownload/metadata/html/Cad_parcel_mod4.html
  - https://modiv.rutgers.edu/
  - https://www.nj.gov/njgin/resources/archives
- **NM:**
  - https://app.regrid.com/store/us/nm
  - https://landrecords.us/products/us-nm-parcels
  - (no official source found)
- **NY:**
  - https://gis.ny.gov/parcels
  - https://gis.ny.gov/system/files/documents/2026/05/current_parcel_polygon_metadata.pdf
  - https://gisservices.its.ny.gov/arcgis/rest/services/NYS_Tax_Parcels_Public/MapServer/1
  - https://nysgeohub.ny.gov/arcgis/rest/services/Parcels/NYS_Tax_Parcels_Public/FeatureServer
  - https://gis.ny.gov/system/files/documents/2025/04/current_parcel_centroid_metadata.pdf
  - https://nysac-001-us.govstack.com/media/gcalnbea/gis-jan-21-2021-40889.pdf
- **NC:**
  - https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/MapServer/1
  - https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/FeatureServer/0
  - https://it.nc.gov/documents/files/nc-parcels-brief/open
  - https://it.nc.gov/documents/gicc/seamless-parcels-fields-november-2023/open
  - https://it.nc.gov/media/809/download?attachment
- **ND:**
  - https://gishubdata-ndgov.hub.arcgis.com/datasets/NDGOV::parcels/explore
  - https://gishubdata-ndgov.hub.arcgis.com/datasets/parcels-taxroll
  - https://www.gis.nd.gov/news/north-dakota-statewide-parcels
  - https://www.it.nd.gov/sites/www/files/documents/project-management-office/startup-closeout-iterative-reports/ndit-statewide-parcel-dataset-closeout-report.pdf
  - https://gis.nd.gov/node/69
- **OH:**
  - https://ohioparcels-geohio.hub.arcgis.com/
  - https://ohioparcels-geohio.hub.arcgis.com/maps/geohio::ohio-statewide-parcels-public-view/explore
  - https://gis.ohiodnr.gov/arcgis/rest/services/OIT_Services/odnr_landbase/MapServer/4
  - https://das.ohio.gov/technology-and-strategy/OGRIP/data_services
  - https://geo.btaa.org/catalog/26ab5fad8d5d4258a7492a14de83bc0e
  - https://www.co.fairfield.oh.us/auditor/pdf/PRESS-OGRIP-02.01.24.pdf
- **OK:**
  - https://atlas.co/data-portals/okmaps-oklahoma/
  - https://landrecords.us/products/us-ok-parcels
- **OR:**
  - https://www.oregon.gov/eis/geo/Pages/statewide-data-initiatives.aspx
  - https://ftp.gis.oregon.gov/framework/ZZ_SHARE/MINUTES/FIT/FORUMS/32nd_FW_Forum_May2025/Presentations/03-Statewide%20Parcels%20Update.pdf
  - https://geohub.oregon.gov/pages/parcel-viewer
  - https://catalog.data.gov/dataset/ormap-the-oregon-property-tax-map
  - https://www.oregon.gov/eis/geo/OGIC%20Documents1/2026_OGIC_September_Newsletter.pdf
- **PA:**
  - https://geo.btaa.org/catalog/pasda-335
  - https://www.Pasda.psu.edu/publications/PASDAAnnualReport_2021.pdf
  - https://app.regrid.com/store/us/pa
  - https://reportallusa.com/store/pennsylvania
- **RI:**
  - https://planning.ri.gov/sites/g/files/xkgbur826/files/2025-08/Statewide_GIS_Report_February_2025_FINAL_appendices_sent.pdf
  - https://experience.arcgis.com/experience/30be9f4db3884018a4757853b5f089f2
  - https://risegis.ri.gov/hosting/rest/services/RIDEM/Tax_Parcels/MapServer
  - https://www.rigis.org/pages/municipal-gis-resources
- **SC:**
  - https://rfa.sc.gov/resources/mapping
  - https://data-scdnr.opendata.arcgis.com/
  - https://app.regrid.com/store/us/sc
  - https://landrecords.us/products/us-sc-parcels
- **SD:**
  - https://app.regrid.com/store/us/sd
  - https://landrecords.us/products/us-sd-parcels
- **TN:**
  - https://comptroller.tn.gov/office-functions/pa/gisredistricting/redistricting-and-land-use-maps/parcel-data.html
  - https://comptroller.tn.gov/office-functions/pa/gisredistricting/parcel-data-stewardship.html
  - https://tnmugfiles.utk.edu/presentations/2019Nov/GIS+CAMA-Hill.pdf
- **TX:**
  - https://www.geographic.texas.gov/stratmap/land-parcels.html
  - https://tnris.org/stratmap/land-parcels.html
  - https://feature.geographic.texas.gov/arcgis/rest/services/Parcels/stratmap_land_parcels_48_most_recent/MapServer/0
  - https://feature.geographic.texas.gov/arcgis/rest/services/Parcels/stratmap25_land_parcels_48/MapServer
- **UT:**
  - https://gis.utah.gov/products/sgid/cadastre/gop-parcels/
  - https://gis.utah.gov/data/cadastre/parcels
  - https://gis.utah.gov/documentation/policy/license/
  - https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/Parcels_Utah_LIR/FeatureServer
- **VT:**
  - https://maps.vcgi.vermont.gov/gisdata/metadata/CadastralParcels_VTPARCELS.htm
  - https://maps.vtrans.vermont.gov/arcgis/rest/services/ROW/Parcel_Reporting/FeatureServer/layers
  - https://tax.vermont.gov/sw/node/7246
  - https://windhamregional.org/?p=953
- **VA:**
  - https://vaemergency.gov/divisions/911-and-geospatial/geographic-information-network
  - https://dsfmportal.dcr.virginia.gov/server/rest/services/CivilReference/Civil_Reference_Layers/MapServer
  - https://cmap22.vims.edu/arcgis/rest/services/VirginiaAndBaywide/VirginiaParcelsAndTables/MapServer/info/iteminfo?f=pjson
  - https://gismaps.vdem.virginia.gov/download/
- **WA:**
  - https://services.arcgis.com/jsIt88o09Q0r1j8h/ArcGIS/rest/services/Current_Parcels/FeatureServer/0
  - https://geodataservices.wdfw.wa.gov/arcgis/rest/services/MapServices/LocatorsWM/MapServer/0
  - https://wisaard.dahp.wa.gov/server/rest/services/County_Parcels/MapServer/0
  - https://depts.washington.edu/wagis/projects/parcels/about.php
- **WV (fetched directly):**
  - https://services.wvgis.wvu.edu/arcgis/rest/services?f=json
  - https://services.wvgis.wvu.edu/arcgis/rest/services/Planning_Cadastre/WV_Parcels/MapServer?f=json
  - https://services.wvgis.wvu.edu/arcgis/rest/services/Planning_Cadastre/WV_Parcels/MapServer/0?f=json
  - https://services.wvgis.wvu.edu/arcgis/rest/services/Planning_Cadastre/WV_Parcels/MapServer/11?f=json
  - https://services.wvgis.wvu.edu/arcgis/rest/services/Planning_Cadastre/Delinquent_Properties/MapServer?f=json
  - https://data.wvgis.wvu.edu/pub/Clearinghouse/planningLanduseCadastres/Parcels/WVGISTC_2026/
  - https://data.wvgis.wvu.edu/pub/Clearinghouse/planningLanduseCadastres/Parcels/WVGISTC_2026/CountySplits/
  - https://mapwv.gov/parcel/template/helpPanel.html
  - https://tax.wv.gov/Business/PropertyTax/FormsAndPublications/SurfaceMaps/Pages/PropertyTaxSurfaceMaps.aspx
  - https://gis.transportation.wv.gov/arcgis/rest/services/Economic/MapServer/5/iteminfo?f=pjson
  - https://gis.transportation.wv.gov/arcgis/rest/services/Economic/MapServer/7/iteminfo?f=pjson
  - Via search: https://code.wvlegislature.gov/signed_bills/2017/2017-RS-SB588-SUB1%20ENR_signed.pdf and https://code.wvlegislature.gov/pdf/11-1C-7/
- **WI:**
  - https://www.sco.wisc.edu/parcels/data
  - https://sco.wisc.edu/parcels/data/assets/V12/V12_Wisconsin_Statewide_Parcels_Schema_Documentation.pdf
  - https://sco.wisc.edu/parcels/data/assets/V12/V12_Submission_Documentation.pdf
  - https://services3.arcgis.com/n6uYoouQZW75n5WI/ArcGIS/rest/services/Wisconsin_Statewide_Parcels_DB/FeatureServer/0
  - https://doa.wi.gov/DIR/V12_Final_Report.pdf
  - https://doa.wi.gov/DIR/V11_Final_Report.pdf
- **WY:**
  - https://wyo-prop-div.wyo.gov/tax-districts/maps-gis-data
  - https://gis.deq.wyo.gov/arcgis/rest/services/WY_PRIVATE_PARCELS/MapServer
  - https://gis.deq.wyo.gov/arcgis/rest/services/WY_PARCELS/MapServer
  - https://ets.wyo.gov/gis-office/georesources
- **DC:**
  - https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Property_and_Land/MapServer/40
  - https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Property_and_Land/MapServer/53
  - https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Property_and_Land/MapServer/56
  - https://catalog.data.gov/dataset/common-ownership-lots
  - https://catalog.data.gov/dataset/integrated-tax-system-public-extract
- **Commercial pricing:**
  - https://regrid.com/blog/2023-parcel-data-price-change
  - https://support.regrid.com/docs/general-faqs
  - https://reportallusa.com/store/texas
  - https://reportallusa.com/store
