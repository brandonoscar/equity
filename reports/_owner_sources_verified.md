# Owner-name sources for the gap counties: live checks

Checked 2026-11-25 with curl from the session container. Nothing here needed a login, a token, a
bot-challenge workaround or a scraped search portal. Maricopa County, AZ was skipped as instructed.

**Method.** For ArcGIS layers I fetched the layer JSON (fields, edit dates, copyright), ran a
`returnCountOnly=true` query and a 2-row `outFields=*` sample, and, where the owner field could be
blank, ran a count with `<owner> IS NOT NULL AND <owner><>''`. Where an ArcGIS Online item exists, I
read its `licenseInfo` and `accessInformation`. Bulk files were downloaded into a scratch folder,
their headers and rows were checked, and then they were deleted. robots.txt was fetched from each host.

**About the robots column.**
- Every hosted ArcGIS Online host (`services*.arcgis.com`) answers `/robots.txt` with **HTTP 403
  "Invalid URL"**, shown below as "403 (AGOL)". The brief's rule ("an unreachable or 403 robots.txt
  counts as disallow") would block every AGOL layer, including ones already loaded. The existing
  configs treat 4xx as "no rules, allowed" (RFC 9309). **Brandon needs to pick one rule.**
- A 404 means the host has no robots.txt file.

**Verdicts.**
- **VERIFIED FREE**: the URL answered, the owner field exists and is filled on sample rows, and there was no login or fee.
- **BLOCKED**: login, CAPTCHA, firewall or terms block it.
- **PAID**: only a paid source has the names.
- **NONE FOUND**: no free owner source after the checks listed.
- Restrictions are flagged inline (for example "not for commercial use" or "project use only").

| Gap | Source (URL) | Owner field | Value/address fields | Rows | Updated | robots | Terms/notes | Verdict |
|---|---|---|---|---|---|---|---|---|
| CA Alameda, Santa Clara, Fresno | AGOL searches found no county parcel layer with owners; gis.fresnocountyca.gov does not resolve | - | - | - | - | - | CA counties generally withhold owner names from online GIS; rolls sold/requested. | NONE FOUND |
| CA Kern | https://services5.arcgis.com/Y8jwjGUWbRjuqpG5/arcgis/rest/services/Assessor_Parcels_Land_2026_gdb/FeatureServer/0 | none (APN, acreage only) | - | 424,125 | 2026-08-17 | 403 (AGOL) | KernGIS org; geometry + APN only. | NONE FOUND |
| CA Los Angeles | already configured layer (Assessor Parcel Data Roll 2026) has no owners; no other free owner source found | - | - | - | - | - | Assessor sells roll (gap doc: $50). | NONE FOUND (paid roll) |
| CA Orange | https://www.ocgis.com/arcpub/rest/services/Map_Layers/Parcels/FeatureServer/0 | none (OBJECTID, SITE_ADDRESS, ASSESSMENT_NO, YEAR_BUILT, NBR_BEDROOMS) | SITE_ADDRESS | 703,000 | - | ocgis.com robots: Disallow /art only | OC Survey layer, no owner or value. | NONE FOUND |
| CA Riverside | https://gis.countyofriverside.us/arcgis/rest/services/parcels/Parcels/MapServer/0 (already in config 06065, owner columns removed pending decision) | PRIMARY_OWNER, ALL_OWNER_LIST | values per config | 913,693 (912,832 with owner) per config 2026-11-16 | - | per config | County's open-data copy omits owners; this non-open-data public map service carries them. Not re-probed. | VERIFIED FREE earlier; needs owner decision |
| CA Sacramento | mapservices.gis.saccounty.gov answered 403; assessor site offers 'Find an owner' lookup + fee schedule, no bulk file found | - | - | - | - | - | - | NONE FOUND |
| CA San Bernardino | configured layer redacts OwnerName ('Protected Per CA Gov Code 7928.205') | - | - | - | - | - | - | NONE FOUND |
| CO Chaffee | https://services8.arcgis.com/fRzYA77NIM7odeAM/arcgis/rest/services/CHAFFEE_PARCELS_20260803/FeatureServer/0 | NAME1/NAME2 + ADDRESS1/ADDRESS2/CITY/STATECODE/ZIPCODE (mailing often blank) | ADDRESS (situs), ACCT_TYPE; no values | 18,403 (16,998 with NAME1) | 2026-08-13 (Aug 2026 snapshot) | 403 (AGOL) | Hosted in the Salida org (owner PWDirector2); license = Chaffee County 'User Agreement' no-warranty text. | VERIFIED FREE (snapshot, no values) |
| CO Delta | https://services3.arcgis.com/iISaUisYi4rM2M0D/arcgis/rest/services/Delta_County_Parcels_01232025/FeatureServer/0 | none (TaxPIN_GIS only) | - | 19,009 | 2025-03-16 | 403 | - | NONE FOUND |
| CO El Paso | https://gisservices.elpasoco.com/arcgis2/rest/services/HubPublic/Parcels/MapServer/0 | none (PARCEL, HYPERLINK to spatialest viewer) | - | 278,440 | item modified 2026-11-17 | 404 | License: 'All rights reserved. No part ... may be reproduced ... or distributed without the specific written approval of the Board of County Commissioners'. | NONE FOUND (and restrictive license) |
| CO Fremont | no AGOL parcel layer found | - | - | - | - | - | - | NONE FOUND |
| CO Montrose | https://mcmap.montrosecounty.net/server/rest/services/MontroseCounty/FeatureServer/47 | name + address1/address2/city/state/zipcode, careof | full_add/loccity, accountno, mill_levy; no values | 29,206 | item modified 2026-07-13 | 404 (no rules) | Copyright 'Montrose County Assessor's Office & GIS Department'; item license 'OPEN DISTRIBUTION ... may be displayed publicly, and may be shared publicly'. | VERIFIED FREE (no values) |
| CO Summit | https://services6.arcgis.com/dmNYNuTJZDtkcRJq/arcgis/rest/services/SummitCnty_Parcels_Pictometry/FeatureServer/0 | OwnerFullName, OwnerNamesPublicHTML, OwnerSearchValue (no mailing) | SitusAddress, TownName; no values | 38,590 | 2026-11-25 | 403 (AGOL) | SummitCountyGIS org item; licenseInfo empty. | VERIFIED FREE (no values/mailing) |
| HI Hawaii County | hawaiipropertytax.com answered 403; gis.hawaiicounty.gov answered 'Request blocked by security policy' | - | - | - | - | - | We do not work around blocks. | BLOCKED |
| HI Honolulu | https://services.arcgis.com/tNJpAOha4mODLkXz/arcgis/rest/services/CadastralTables/FeatureServer/8 (OWNMLT); also /5 OWNALL and /9 ASMTGIS | OWNMLT: ownname1/ownname2 + taxbilladdress/city/state/zip5; OWNALL: own1/own2/paddr1-3 | ASMTGIS: landvalue, buildingvalue, exemptions, tnettaxval, taxyr (join on parid/tmk) | OWNMLT 263,347; OWNALL 590,559; ASMTGIS 325,569 | 2026-11-20 (taxyr 2027) | 403 (AGOL) | honolulugis org; licenseInfo is a no-warranty statement only. | VERIFIED FREE |
| HI Kauai | kauaipropertytax.com: connection reset; gis.kauai.gov does not resolve; the state layer geodata.hawaii.gov ParcelsZoning/9 has no owners | - | - | - | - | - | - | NONE FOUND |
| HI Maui | https://services1.arcgis.com/x4h61KaW16vFs7PM/arcgis/rest/services/Parcels_w_Owners_Maui_County_2026/FeatureServer/0 | Owner, OwnerType | none (qpub_link only) | 51,245 | 2026-08-20 | 403 (AGOL) | Copy made by an individual AGOL user (jpl8484), not the county; provenance unclear. The county's own RPT site is qPublic, a search portal. | THIRD-PARTY ONLY (not county) |
| IA Polk | assessor site (polkcountyiowa.gov/county-assessor) shows no bulk download link; gap-states.md: HTML search forms only | - | - | - | - | - | Would mean scraping a search portal. | NONE FOUND |
| ID Ada | https://services2.arcgis.com/dgGjZc6xAH5m5JyP/arcgis/rest/services/Parcels/FeatureServer/5 | none (no owner field) | ADDRESS, TOTALVALUE | the count query returned 0 | 2026-11-23 | 403 (AGOL) | CC0 license (Ada County Assessor), but owner names are left out. | NONE FOUND |
| ID Bannock | https://maps.bannockcounty.us/server/rest/services/Parcels_Public/MapServer/0 | OwnerName + Address, Address2, CityStZip (mailing) | SitusAddress, CurMktValue, MktValue, ValCurrentYear/TaxChargeCurrentYear plus 4 prior years | 46,081 (44,474 with OwnerName) | AGOL item modified 2025-01-23 | 404 (no rules) | County server; AGOL item 'Bannock County Parcels' has no licenseInfo. | VERIFIED FREE |
| ID Bonneville | https://services2.arcgis.com/Xd5SMhLZ1h9t0F3b/arcgis/rest/services/Bonneville_Parcels_April_2025/FeatureServer/0 | owner, additional, owneraddre/ownercity/ownerstate/ownerzipco | parceladdr/parcelcity/parcelzipc, landvalue, valueofabo, taxcharge2 | 63,803 | 2025-05-07 (April 2025 snapshot) | 403 (AGOL) | Hosted by BonnevilleAdmin (county org); no licenseInfo. Stale snapshot. | VERIFIED FREE (2025-04 snapshot) |
| ID Canyon | https://services.arcgis.com/gfpXnknjcY6QHKhU/arcgis/rest/services/Web_Parcels_CanyonCo_20230315/FeatureServer/0 (third-party copy) | none | SiteAddres, FCVLand/FCVImp/FCVTotal | 14,310 (partial) | 2026-11-12 | 403 (AGOL) | Copy held by a state DEQ account. The county host gis.canyonco.org does not resolve. | NONE FOUND |
| ID Kootenai | https://gis.kcgov.us/arcgis/rest/services | - | - | - | - | - | Server answers 'Could not access any server machines'. | NONE FOUND (server down) |
| ID Twin Falls | https://services3.arcgis.com/2lFfYsoBD697ZuE3/arcgis/rest/services/TFCO_Parcels_08_2025/FeatureServer/0 | PM_MAIL_NM + PM_MAIL_A1/A2/CT/ST/ZP | PM_PROP_AD/PM_PROP_ZP; no values | 46,094 | 2025-12-04 (Aug 2025 data) | 403 (AGOL) | Item 'TFCO Parcel Map', owner publicworks13 (county public works); no licenseInfo. | VERIFIED FREE (no values) |
| IN statewide (DLGF) | https://gateway.ifionline.org/public/download.aspx (Property Files > Data Set "Real Property", Tax Bill Year, Geography = a county or "All Counties"; ASP.NET form POST returns e.g. realparcel_Ohio_58_2025p2026.zip) | owner name + owner mailing address (positional PARCEL file, 50 IAC 26 layout; doc: gateway.ifionline.org/guides/downloads/property-file-documentation.xlsx) | situs address, land/improvement AV | Ohio County test: 3,521 parcel rows, owner filled on every sampled row | 2025-pay-2026 file dated 2026-07-31 | 404 (no rules) | No license text on the page. DLGF says it publishes the "most recent compliant data set"; questions go to Gateway@dlgf.in.gov. Tax Bill (TAXDATA) and Adjustments files are also offered. | VERIFIED FREE |
| KS Johnson, KS Sedgwick, NV Clark, NM Bernalillo, AK Mat-Su | not re-probed; see docs/sources/gap-states.md | - | - | - | - | - | Johnson: KORA form or paid; Sedgwick: firewall blocks queries; Clark: county sells roll ($2,500 / $7,500 yr); Bernalillo: robots.txt disallows /server/*; Mat-Su: internal-use-only license. | BLOCKED / PAID (unchanged) |
| KY Jefferson (LOJIC) | https://gis.lojic.org/maps/rest/services/LojicSolutions/OpenDataPVA/MapServer/1 | none (PARCELID, PARCEL_TYPE, LRSN, PIN only) | - | 293,456 | item modified 2022-06-01 | 404 | LOJIC open data omits PVA owner names. | NONE FOUND |
| LA Jefferson Parish | no assessor layer found; gis.jeffparish.net does not resolve; Gretna 'MGO_Parcels_View' has no layer 0 | - | - | - | - | - | - | NONE FOUND |
| MD Howard, Frederick, Harford | Howard copy (services6 drkDXByy...) has no fields; Frederick fcgis server has no parcel/owner service; Harford only third-party/inquiry map | - | - | - | - | - | - | NONE FOUND |
| MD Montgomery | already configured (24031, mcmaps.org OWNERS_NAME) | - | - | - | - | - | - | already loaded |
| MD statewide (SDAT) | https://opendata.maryland.gov/d/ed4q-f8tm ('Maryland Real Property Assessments_Hidden Property Owner Names', per-county variants e.g. Howard 9t52-zebk, Harford ygxu-5v84) | none: owner names hidden by design | premises address, SDAT values | - | 2026-11-06 | - | State publishes values with names hidden; CAMA with names sold via vendor. | NONE FOUND (names hidden) |
| ME Aroostook | https://gis.maine.gov/mapservices/rest/services/mrs/Maine_Parcels_Unorganized_Territory/MapServer/0 | GRANTOR/GRANTEE fields exist but are empty on all 36,875 rows | - | 36,875 | - | 404 | Maine Revenue Services UT layer; organized-town ADB table is voluntary. | NONE FOUND |
| MI Oakland | configured layer (26125) has NAME1/NAME2 empty on all rows; county hosts not found; AGOL search found no owner layer | - | - | - | - | - | - | NONE FOUND |
| MN Beltrami | https://arcgis.co.beltrami.mn.us/arcgis/rest/services/BeltramiData/BeltramiOpenData/MapServer/2 | OWNERNAME1/2 + OWNER1_ADD.., OWNER_CITY/ST/ZIP | PROP_ADD1/PROP_CITY/PROP_ZIP, EMV_LAND/EMV_BLDG/EMV_TTL, TOTAL_TAX, SALE_DATE/VALUE, PARCEL_YR 2026 | 41,645 | PARCEL_YR 2026 | 404 (no rules) | County 'BeltramiOpenData' service; item has no licenseInfo. | VERIFIED FREE |
| MN Blue Earth | https://services.arcgis.com/sLe4VrKqV1JxToKz/arcgis/rest/services/BlueEarthParcels/FeatureServer/0 | DEEDHOLDER (+_1/_2), MAILTO_ADD/CIT/STA/ZIP | ADDRESS; no values | 31,930 | 2022-05-03 (stale) | 403 (AGOL) | Copy under a GDITAdmin account, not the county; stale. | STALE THIRD-PARTY COPY |
| MN Carver | https://services.arcgis.com/wMZT8kNwa6tOxhKg/arcgis/rest/services/Open_Data_Parcels/FeatureServer/0 | TAX_NAME + TAX_ADD_L1/L2 (OWNER_NAME empty) | address parts, EMV_LAND/EMV_BLDG/EMV_TOTAL, TOTAL_TAX, TAX_YEAR | 48,131 (47,841 with TAX_NAME) | 2026-11-15 | 403 (AGOL) | CarverCounty org; reference-only disclaimer. Met Council copy (layer 1) has 0 OWNER_NAME. Taxpayer name, not owner of record. | VERIFIED FREE (taxpayer name) |
| MN Goodhue | https://publicmaps.co.goodhue.mn.us/arcgis/rest/services/GoodhueCounty/ParcelsAGOL/MapServer/0 | C0NAME1P/C0NAME2P + C0ADRLN1P..3P | C0HSENO1/C0STRNM/C0CITY/C0ZIP, C0SALEDT/C0SALPRC; no EMV | 29,289 (29,049 with name) | web map modified 2025-11-18 | 404 (no rules) | County public map server (Tax Parcel Viewer); no licenseInfo. | VERIFIED FREE (no values) |
| MN Kandiyohi | https://gis.kcmn.us/arcgis/rest/services/Kandiyohi/PublicMailingKandi/FeatureServer/0 | TAXNAME/TAXNAME2 + TAXADDRESS/CITY/STATE/ZIP; OWNNAME/OWNNAME2 + OWNADDRESS | PROPHSENUM/PROPROAD/PROPZIP, EMV, VALUE1-9 | 29,766 | - | 404 (no rules) | County server 'PublicMailingKandi' (built by Bolton & Menk); license not read. | VERIFIED FREE |
| MN Rice | https://asr-arcgis01.ricecountymn.gov/arcgis/rest/services/Maps/TaxParcels/MapServer/1 | OWNER_NAME, OWNER_MORE + OWN_ADD_L1..L4 | SiteAddrFull, EMV_LAND/EMV_BLDG/EMV_TOTAL, MKT_YEAR 2026, SALE_DATE/VALUE | 28,263 | last_edited 2025-07; MKT_YEAR 2026 | 404 (no rules) | County assessor server; item rcgis@ricecountymn.gov; license not read. | VERIFIED FREE |
| MN Scott | https://services.arcgis.com/DqIh9WAsIZcPlBEF/arcgis/rest/services/Parcels/FeatureServer/0 (also Met Council Parcels/FeatureServer/5, 61,872 all with OWNER_NAME) | TaxPayerName + TaxpayerAddress/TaxAddress1/2 | PropertyAddress, EMVLand/EMVImprove/EMVTotal, TaxYear 2026, LastSaleDate/Price | 62,203 | 2026-11-20 | 403 (AGOL); metc 404 | ScottCountyGIS; licenseInfo = reference-only disclaimer (Minn. Stat. 466.03). Met Council license: public domain under MN Data Practices Act. | VERIFIED FREE |
| MN Stearns | https://gis.co.stearns.mn.us/arcgis/rest/services/Vendor/Parcels/MapServer/0 | OWNER, OWNERDISPLAY, OWNERATTNLINE + OWNERADDR, OWNER_CITYSTATEZIP | PROPADDR, EMV_LAND/EMV_BLDG/emvtotal, TOTAL_TAX, TAX_YEAR, ASSESSMENT_YEAR | 73,260 (70,608 with OWNER) | item modified 2025-08-25 | 404 (no rules) | County server, 'Vendor' folder (item owner BoltonMenk_Rockville); no licenseInfo. | VERIFIED FREE |
| MO Greene | https://maps.springfieldmo.gov/arcgis/rest/services/Maps/GisViewer/MapServer/66 | OWN1, OWN2, CAREOF + ADRNO/ADRSTR/CITYNAME/STATECODE/ZIP1 mailing, Own_Addr | L_ADRNO/L_ADRSTR/PropAdr situs, RESLAND/RESBLDG/AGLAND/COMLAND..., TOTLAND/TOTBLDG, assessed values, SALEDT, BOOK/PAGE | 123,884 (123,840 with OWN1), countywide | no edit date | robots.txt answers 200 with an HTML 404 page (no rules) | City of Springfield GIS viewer service (county assessor data); no copyright text. Greene County's own hosts unreachable as before. | VERIFIED FREE |
| MO St. Louis City | https://static.stlouis-mo.gov/open-data/assessor/Parcels-CSV-1997-Current.zip (yearly CSVs; 2025.csv) | OWNERNAME, OWNERNAME2 + OWNERADDR, OWNERCITY, OWNERSTATE, OWNERZIP | SITEADDR, ASMTLAND, ASMTIMPROV, ASMTTOTAL, sale book/page | 2025.csv: 127,025 rows, 127,023 with OWNERNAME | zip Last-Modified 2026-10-26; rows UPDATED 2026-01-01 | static.stlouis-mo.gov 404 (no rules); www robots only blocks /data/*&dataType=json | City Assessor's Office open data. Current PARCELS.zip shapefile has only OwnerCode, no name. | VERIFIED FREE |
| NC Clay, Hoke | no county parcel layer found on AGOL (only NCDOT statewide VAD layers) | - | - | - | - | - | - | NONE FOUND |
| NC Swain | https://services3.arcgis.com/bAaHaqP9BvQhS7eE/arcgis/rest/services/Swain_County_Parcels/FeatureServer/0 | Name__1, Name__2 + Address_Line_1..3, City, State, Zip_Code | ParcelPropertyAddress, Land_Value_Parcel, Building_Value_Parcel, Total_Assessed_Value, Deed_Date/Book/Page | 13,569 | 2026-11-25 | 403 (AGOL) | Swain County GIS item; licenseInfo = informational/no-warranty text. | VERIFIED FREE |
| NE Sarpy | already configured (config/counties/31153.yaml, OWNERNME1/2) | - | - | - | - | - | - | already loaded |
| NE statewide (NebraskaMAP) | https://gis.ne.gov/Enterprise/rest/services/StatewideParcelsExternal/FeatureServer/0 | none: no owner field (has situs, legal, values, Sales_Date/Sales_Value, Parcel_URL to the county site) | Situs_Address/Ph_Full_Address, Total_Assessed_Value, Land_Value, Improvements_Value | 1,154,898 | item modified 2026-11-23 | 301 to /portal/home/robots.txt, which answers 404 | 'Provided as a public service for general use'; updated annually from county CAMA. | NONE FOUND (no owner) |
| NH Manchester | gis.manchesternh.gov does not resolve; no AGOL layer found | - | - | - | - | - | - | NONE FOUND |
| NH Nashua | already configured (33011, NRPC CAMA Lookup ownername) | - | - | - | - | - | - | already loaded |
| NH statewide | https://nhgeodata.unh.edu/nhgeodata/rest/services/CAD/ParcelMosaic/MapServer (Parcel Points, Parcels, Additional Lines) | none | - | - | - | 404 | Copyright NHDRA, Axiomatic; no owner fields. | NONE FOUND |
| OR Marion, Clackamas, Washington | not re-probed: Marion's configured layer (41047) has no owners; Metro (Clackamas, Washington) strips names from free data, RLIS is paid (gap-states.md) | - | - | - | - | - | - | NONE FOUND (paid RLIS) |
| PA Allegheny | WPRDC already checked (no owner names); no other owner layer found | - | - | - | - | - | - | NONE FOUND |
| PA Erie | no county owner layer found (city of Erie zoning view has no fields; third-party copies only) | - | - | - | - | - | - | NONE FOUND |
| PA Lancaster | https://arcgis.co.lancaster.pa.us/arcgis/rest/services/Land_Parcels/MapServer/0 (also Parcels_app, parcel_poly) | OWNER_NAME + OWNERADD1..3, OWNER_CITY, OWNERSTATE, OWNER_ZIP | HOUSE_NO/STREET_NAME/ADDRESS, LANDASSESS, BLDGASSESS, TOTLASSESS, SALE_PRICE/SALE_DATE, DEED_BK_PG | 189,165 (189,119 with OWNER_NAME) | live (EDIT_DATE per row) | robots.txt 301 to /portal/home/ (no robots file) | County server; no copyright or description text in the service. | VERIFIED FREE |
| RI Cranston | https://arcgisserver.cranstonri.org/arcgis/rest/services/Parcels/FeatureServer/54 | CAMAExtract_Owner1/Owner2 + OwnerAddress/City/State/Zip | CAMAExtract_ParcAddress, AssessedValueTotal/Land/Building, TaxRollYear, LastSaleDate/Price, LastBook/LastPage | 36,632 | item modified 2026-01-16 | 404 (no rules) | City server, item 'Cranston Parcels (RIGIS Format)'; no licenseInfo. | VERIFIED FREE |
| RI Warwick | gis.warwickri.gov does not resolve; AGOL has only sewer and tax-title layers | - | - | - | - | - | - | NONE FOUND |
| RI statewide | none found (RIGIS parcels are town-submitted, without owners) | - | - | - | - | - | - | NONE FOUND |
| TN Comptroller (TPAD counties) | https://comptroller.tn.gov/office-functions/pa/gisredistricting/redistricting-and-land-use-maps/parcel-data.html | Assessment_Data_##.dbf, joined on GISLINK, has owner fields (per page text; not downloaded) | assessment, building, land use | n/a | weekly (Mondays) | comptroller.tn.gov: 200, Allow: / ; assessment.cot.tn.gov: 403 | Download URLs are issued only after a per-county Formstack request form with invisible reCAPTCHA. The page says there are no bulk, recurring or automated downloads, and that any use is allowed, including commercial. The 9 non-state-system counties (Chester, Davidson, Hamilton, Hickman, Knox, Montgomery, Rutherford, Shelby, Williamson) are not offered. | BLOCKED (manual form + CAPTCHA) |
| TN Knox | https://www.kgis.org/arcgis/rest/services answers 401 (credentials) | - | - | - | - | - | KGIS sells data. | BLOCKED (login) |
| TN Montgomery | maps.mcgtn.net answers Cloudflare 522; cmcrpc org has subdivisions only | - | - | - | - | - | - | NONE FOUND |
| TN Shelby | gis.shelbycountytn.gov answers a Cloudflare 'Attention Required' challenge; Collierville 'Certified Parcels' copy has no owner field (20,249 rows) | - | - | - | - | - | We do not work around bot challenges. | BLOCKED |
| TN Williamson | gis.williamsoncounty-tn.gov does not resolve; only a university user's shapefile copy on AGOL | - | - | - | - | - | - | NONE FOUND |
| TN statewide (86 TPAD counties) | https://services1.arcgis.com/YuVBSS7Y1of2Qud1/arcgis/rest/services/Tennessee_Property_Boundaries_Public_Use/FeatureServer/0 | OWNER, OWNER2 (no mailing) | ADDRESS (situs), DEEDAC, LINK_TPAD; no values | 2,144,655 (2,143,354 with OWNER), 86 counties | 2026-11-12 | 403 (AGOL) | Item tnmap_oir, copyright TN Comptroller DPA. Description: 'This service is not intended for commercial use. For commercial purposes, we recommend that you download the data at the Comptroller's webpage' (that page is the CAPTCHA form above). Excludes Shelby, Knox, Williamson, Montgomery, Davidson, Hamilton, Rutherford, Chester, Hickman. | FREE BUT 'NOT FOR COMMERCIAL USE' (needs decision) |
| TX Bowie | bowiecad.org is a parked domain; real site www.bowieappraisal.com is the same JS app platform as Hunt | - | - | - | - | - | No static roll-export link found. | NONE FOUND (static) |
| TX Hunt | https://www.hunt-cad.org/ (JS single-page app; 'mass download' feature inside app) | - | - | - | - | 200 | No static roll-export link; getting data would mean driving the app's API. TxGIO StratMap copy already loaded statewide. | NONE FOUND (static) |
| TX Matagorda | https://matagorda-cad.org/roll-export-data/ -> wp-content/uploads/2026/10/26_CertRoll_Supp14.zip (APPRAISAL_INFO.TXT, PACS 8.0 layout) | owner name (APPRAISAL_INFO pos ~609), C/O, mailing address | situs, legal, values (APPRAISAL_INFO), entity values | APPRAISAL_INFO 490.6 MB; OWNER_EXPORT 71,854 rows (names blank in that file) | 2026-10-29 (Supp 14) | 200, only /wp-admin/ disallowed | 'Tax Roll and GIS Downloads' page; owner export zip has blank name area, use CertRoll APPRAISAL_INFO. | VERIFIED FREE |
| TX Navarro | https://www.navarrocad.com/home/DataRecords -> /Forms/ExcelDownload?subPath=Data%20Records&fileName=1784751390_2026+Navarro+CAD+Certified+Appraisal+Roll+-+Real-Personal++-+Excel+-+20260721_130536.csv | Name, Careof + Street/City/State/Zip5 | Prop_Street_Number/Prop_Street/Prop_City, Land_*/Improvement_*/market fields | 50,033 rows, all with Name | 2026-07-21 (2026 certified) | 404 (no rules) | Public page, no login needed for this file (site offers optional account). | VERIFIED FREE |
| TX Smith | https://www.smithcad.org/data/2026/2026_Real_Property_Certifled_AppraisalRoll_cd.zip (also BPP, Mineral, All_Property zips on /downloads.html) | NAME, NAME2, NAME3 + ADDRESS LINE 1/2, CITY, STATE, ZIP | SITUS_ADDRESSS, LAND MKT VALUE, BUILDING value, assessed values, taxing units | Extract1 CSV 124.8 MB + Extract2 13.6 MB (2026 certified) | Last-Modified 2026-08-04 | robots: User-agent * Allow /, Content-Signal ai-train=no; explicitly Disallow / for ClaudeBot, GPTBot, CCBot etc. | Cloudflare-fronted; no license text on page beyond 'cannot offer technical support'. A client identifying as ClaudeBot would be disallowed. | VERIFIED FREE (note bot-specific robots) |
| UT Cache | gis.cachecounty.gov/arcgis/rest/services (Assessor, Cadastral, Treasurer folders) | none: the 'Land Ownership' layer is 151 generalized PRIVATE/agency polygons | - | - | - | 404 | No parcel-owner layer published. UGRC Parcels_Cache has no owners. | NONE FOUND |
| UT Davis | UGRC Parcels_Davis and Parcels_Davis_LIR (no owners); county host gis.daviscountyutah.gov does not resolve | - | - | - | - | - | No county owner layer found in 2 searches. | NONE FOUND |
| UT Iron | https://services.arcgis.com/xGNWaeXY0POVazgT/arcgis/rest/services/Parcels_Public/FeatureServer/0 | OWNER + MAIL_ADD1/2, MAIL_CITY, MAIL_ST, MAIL_ZIP | SITUS; no values | 56,108 | 2025-02-26 | 403 (AGOL) | County org IronGIS1, item 'Parcels_Public'; no licenseInfo. A Stantec copy covering Iron and Washington with owners and values is licensed 'For Project use only'. | VERIFIED FREE (no values; 2025-02 data) |
| UT Washington | UGRC Parcels_Washington and _LIR (no owners); gis.washco.utah.gov does not resolve | - | - | - | - | - | The only copy with owners is the Stantec 'Three_Peaks_AGO_Parcel_Publish_20260708' item, licensed 'For Project use only'. | NONE FOUND (restricted copy only) |
| UT Weber | https://maps.webercountyutah.gov/arcgis/rest/services/gis/parcels_geogizmo2/MapServer/0 | NAME_ONE + STREET, CITY_STATE, ZIPCODE (mailing) | PROP_STREET/PROP_CITY/PROP_ZIP, TOT_MARKET, TOT_TAXABLE, TaxYear | 115,765 | TaxYear/ASSESSED_YR 2026 | 404 (no rules) | County server; no copyright or license text. | VERIFIED FREE |
| VA Arlington | not re-probed (gap-states.md: no layer with owner names) | - | - | - | - | - | - | NONE FOUND |
| VA Fairfax | https://www.fairfaxcounty.gov/mercator/rest/services/GIS/ParcelsPlus/MapServer (5 fields), ParcelPlusAssessedValues (values only) | none | values only | - | - | - | Confirms gap-states.md: no owner layer. | NONE FOUND |
| VA Henrico | gis.henrico.us / gis.henrico.gov do not resolve; AGOL copy by an unrelated developer account only | - | - | - | - | - | - | NONE FOUND |
| WA Clark | https://services2.arcgis.com/ylxwjFBdCPBzP16d/arcgis/rest/services/TaxlotsforPublicUse/FeatureServer/0 | none (MainOwnerID only) | SitusAddrsFull, MktLandVal/MktBldgVal/MktTotVal, TaxYear, SaleDate/SaleAmount | 196,562 | 2026-11-25 | 403 (AGOL) | The county's public layer strips names. The City of Battle Ground copy (Taxlots_OutsideBG, 186,679 rows, Owner/MailName) is licensed 'Subject to Clark County's data use and redistribution terms... for reference/display purposes on internal dashboards'. | NONE FOUND (restricted copy only) |
| WA King | https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/PARCEL_ADDRESS_PUB_AREA_3069/FeatureServer/0 | KCTP_ATTN (taxpayer attention line, sometimes the name) + KCTP_ADDR/CTYST/ZIP | ADDR_FULL, APPRLNDVAL/APPR_IMPR, TAX_LNDVAL/TAX_IMPR, KCTP_TAXYR | 636,786 rows; KCTP_ATTN filled on only 27,412 (4%) | 2026-11-25 | 403 (AGOL) | KingCounty org; terms link to the King County GIS no-warranty terms. The assessor bulk files (info.kingcounty.gov/assessor/DataDownload) sit behind an RCW 42.56.070(9) acknowledgment that they will not be used for 'commercial purposes'; robots allows that path. | PARTIAL (4% of rows); bulk BLOCKED by commercial-use terms |
| WA Kitsap | https://www.kitsap.gov/assessor/Pages/DataDownload.aspx (Parcels.txt, Valuations.txt, Property_addresses.txt and others) | none (Parcels.txt has no owner column) | Property_addresses.txt, Valuations.txt | Parcels.txt 11.1 MB | 2026-11-19 | 200; /assessor/ is allowed | The AGOL Kitsap_Parcel_and_Boundary layer needs a token. | NONE FOUND (no names) |
| WA Pierce | https://services2.arcgis.com/1UvBaQ5y1ubjUPmd/arcgis/rest/services/Tax_Parcels/FeatureServer/0 | none (Delivery_Address mailing street and Business_Name only) | Site_Address, Land_Value, Improvement_Value, Taxable_Value | 340,193 | 2026-11-20 | 403 (AGOL) | Pierce County IT.DataCurator. The county data-download page answered 403 (not pursued). | NONE FOUND (mailing address without name) |
| WA Thurston | already configured (53067, OWNER_NAME) | - | - | - | - | - | - | already loaded |

## Summary

**Verified free fixes, 26 gaps:**
- **Statewide:** IN (DLGF Gateway real-property file, per county or all counties).
- **ID:** Bannock, Bonneville (April 2025 snapshot), Twin Falls.
- **UT:** Weber, Iron.
- **RI:** Cranston.
- **HI:** Honolulu.
- **MN:** Beltrami, Goodhue, Kandiyohi, Stearns, Scott, Carver (taxpayer name), Rice.
- **CO:** Summit, Montrose, Chaffee.
- **TX:** Smith, Matagorda, Navarro.
- **Others:** NC Swain, PA Lancaster, MO St. Louis City, MO Greene.

**Needs a decision before loading:**
- **TN statewide layer (86 counties, about 2.14M parcels with OWNER):** its description says "not intended for commercial use." The commercial route is the Comptroller download, and that sits behind a CAPTCHA form.
- **CA Riverside:** a public map service has owner names, but the county's own open-data copy deliberately leaves them out.
- **robots rule:** a 403 on ArcGIS Online hosts is either "allowed" (RFC 9309, the project's current convention) or "disallowed" (the brief).
- **TX Smith:** robots.txt allows `*` but names and disallows ClaudeBot, GPTBot and CCBot. Its Content-Signal says ai-train=no.

**Partial or restricted only:**
- **WA King:** 4% of rows have a taxpayer line. The bulk files require a no-commercial-use acknowledgment.
- **HI Maui:** only a copy made by an individual user.
- **MN Blue Earth:** a stale 2022 copy held by another organization.
- **UT Washington, WA Clark:** the only copies with owners are licensed for "project use only" or "internal dashboards".

**Blocked:**
- TN Comptroller downloads (CAPTCHA form)
- TN Shelby (Cloudflare challenge)
- TN Knox (KGIS 401)
- HI Hawaii County (security block)
- KS Johnson and Sedgwick, NV Clark, NM Bernalillo, AK Mat-Su (unchanged from gap-states.md)

**No free owner source found:**
- **CA:** Los Angeles, San Bernardino, Orange, Sacramento, Alameda, Santa Clara, Fresno, Kern
- **MD:** statewide SDAT (names hidden by design), Howard, Frederick, Harford
- **NE:** statewide layer (no owner field)
- **NH:** statewide, Manchester
- **RI:** statewide, Warwick
- **UT:** Davis, Cache
- **ID:** Ada (a CC0 layer, but without owners), Canyon, Kootenai
- **WA:** Pierce, Kitsap
- **CO:** El Paso (also has an all-rights-reserved license), Delta, Fremont
- **TX:** Hunt, Bowie (JavaScript app only)
- **TN:** Williamson, Montgomery
- **NC:** Clay, Hoke
- **OR:** Marion, Clackamas, Washington
- **Others:** MI Oakland; PA Erie, Allegheny; ME Aroostook; KY Jefferson (LOJIC); VA Fairfax, Arlington, Henrico; LA Jefferson Parish; IA Polk; HI Kauai

**Already loaded:** NE Sarpy, NH Nashua, MD Montgomery, WA Thurston.
