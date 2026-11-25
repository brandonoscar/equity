# Data gaps list (scan of 2026-11-25)

This list compares what is actually **loaded in the lake** (Supabase bucket `lake`, 435 sources, read from each source's `_state.json` part counts) with the registry (652 sources) and the configs. A layer we have in one state and not another counts as a gap. Fill rates are rows written ÷ parcels: an owner row is written only when an owner name exists, and a value row only when a value **and** a tax year exist.

The gaps come first, numbered. The fix for each one is under the same number in the second half.

---

## Part 1: Gaps

### A. Owner names missing (by county)

1. **CA:** no owner names in any of the 58 counties. Los Angeles, Riverside and San Bernardino are loaded with parcel ids and values only. San Diego and San Jose (Santa Clara) are configured but not built. The other 53 counties have no parcel layer at all.
2. **HI:** no owner names, values or addresses in any county (Hawaii, Honolulu, Kauai, Maui). The statewide layer has boundaries only, and there is no match run.
3. **IN:** the statewide layer (all 92 counties) has no owners and no values. Owners exist only in Lake and Vanderburgh. Marion (Indianapolis) is configured but not built.
4. **TN:** the statewide layer (86 counties) has no owners and no values. Owners exist only in Davidson, Hamilton, Rutherford and Washington. Shelby, Knox, Williamson, Montgomery, Chester and Hickman have no parcels at all.
5. **WA:** the statewide layer (all 39 counties) has no owners. Owners exist only in Snohomish and Spokane. King, Pierce and Clark have none. Thurston and Whatcom are configured but not built.
6. **UT:** both statewide layers (boundaries and LIR) have no owners and no values. Owners exist only in Salt Lake and Utah counties.
7. **NE:** the statewide layer (93 counties) has no owners and no addresses. Owners exist only in Douglas, Lancaster and Cass. Sarpy is configured but not built.
8. **NH:** no owners, values or addresses statewide. Owners exist only in the 13-town NRPC region.
9. **NJ:** no owners in 20 of 21 counties (Daniel's Law redaction). Only Monmouth has them. The statewide layer also carries no values.
10. **RI:** no owners, values or addresses in any municipality except Providence. There is no match run.
11. **MD:** the statewide layer has no owners and no addresses. Owners exist in 8 of 24 counties. Montgomery is configured but not built, and the three SDAT transfer files (which name grantees) are registered but not built.
12. **ID:** the statewide layer covers 13 of 44 counties, and is a draft config. Ada (Boise) has no owners. These 31 counties are missing entirely: Adams, Bannock, Benewah, Bingham, Blaine, Bonner, Bonneville, Boundary, Butte, Canyon, Caribou, Cassia, Clark, Clearwater, Custer, Elmore, Franklin, Fremont, Gem, Idaho, Jefferson, Kootenai, Latah, Lemhi, Lewis, Madison, Owyhee, Payette, Power, Shoshone and Twin Falls.
13. **MN:** 27 counties are missing from the statewide layer: Beltrami, Blue Earth, Brown, Cottonwood, Faribault, Freeborn, Goodhue, Hubbard, Kanabec, Kandiyohi, Kittson, Le Sueur, Lincoln, Mahnomen, Martin, Meeker, Nicollet, Nobles, Pine, Redwood, Rock, Roseau, Sibley, Swift, Todd, Wadena and Watonwan.
    - 18 counties have no owners: Benton, Big Stone, Carver, Clay, Clearwater, Fillmore, Grant, Houston, Itasca, Lake of the Woods, McLeod, Mille Lacs, Norman, Rice, Scott, Stearns, Traverse and Waseca.
    - 6 counties have owners on under 10% of parcels: Marshall, Pope, Red Lake, Renville, Wilkin and Yellow Medicine.
    - The Metro regional layer is configured but not built.
14. **NY:** 22 counties are missing from the statewide layer: Chemung, Chenango, Clinton, Columbia, Delaware, Dutchess, Essex, Franklin, Fulton, Herkimer, Jefferson, Madison, Monroe, Nassau, Niagara, Orleans, Saratoga, Schenectady, Schoharie, Seneca, Washington and Yates. Allegany and Cattaraugus returned 0 rows. `ny.local_rolls.parcels` is configured but not built.
15. **CO:** 20 counties are missing or returned 0 rows: Alamosa, Baca, Bent, Chaffee, Cheyenne, Conejos, Costilla, Crowley, Delta, Fremont, Jackson, Kiowa, Kit Carson, Las Animas, Lincoln, Mineral, Montrose, Otero, Phillips and Prowers. El Paso (Colorado Springs), Summit and Washington have no owners.
16. **TX:** 9 counties returned 0 rows from StratMap: Bailey, Bowie, Hunt, Matagorda, Navarro, Roberts, Robertson, Terrell and Willacy. Donley is missing. Smith (Tyler) has no owners, and Cottle and Frio have owners on under 50%. Collin and Dallas city layers are configured but not built.
17. **NC:** Clay and Swain returned 0 rows, and Hoke has no owners.
18. **PA:** Allegheny (Pittsburgh), Lancaster and Erie are loaded as ids only, with no owners. 54 of 67 counties have no parcel layer.
19. **MI:** Oakland (490k parcels) has no owners, values or addresses. 73 of 83 counties have no parcel layer.
20. **OR:** Marion has no owners. Clackamas, Washington and 29 other counties have no parcel layer. Multnomah, Lane, Deschutes and Jackson are loaded.
21. **ME:** Aroostook is missing from the statewide layer.
22. **County-only states with thin coverage** (counties with owners ÷ all counties):
    - GA 7 of 159
    - KY 1 of 120 (Boone only; Jefferson/Louisville is missing)
    - KS 1 of 105 (Douglas only; Johnson, Sedgwick, Wyandotte and Shawnee are missing)
    - MO 4 of 115 (St. Louis City and Greene are missing)
    - IA 6 of 99 (Polk/Des Moines is missing)
    - IL 8 of 102
    - OK 2 of 77 (Tulsa build unfinished)
    - LA 2 of 64 (Lafayette configured, not built; Jefferson Parish missing)
    - AL 12 of 67 (Blount configured, not built)
    - SD 3 of 66
    - SC 8 of 46
    - NM 3 of 33 (Bernalillo/Albuquerque configured, not built)
    - NV 1 of 17 (Clark/Las Vegas is missing)
    - AK 3 of 30 (Mat-Su and Juneau are missing)
    - VA 20 of 133 (Fairfax, Arlington, Henrico and Portsmouth are missing)
    - AZ 14 of 15 (Yavapai configured, not built)

### B. Values, addresses and other parcel fields

23. **Value is mapped but thrown away (a repo bug):** 13 layers map a value column but no `tax_year`, so the normalizer drops every assessment row. The layers are Kenai Peninsula AK, Jefferson AL, Cobb GA, Black Hawk IA, Scott IA, East Baton Rouge LA, Oakland MI, Doña Ana NM, Jackson OR, Marion OR, York SC, Davidson TN and **TN statewide**.
24. **No assessed or market value at all** (equity can't be estimated). This covers whole states, or most counties:
    - Whole states: HI, IN, ME, NH, NJ, RI, UT, DE (statewide layer)
    - AZ: 13 of 14 ADWR county copies
    - AL: 8 of 12 counties
    - VA: all 20 county layers
    - OH: 13 of 16 county layers, plus the statewide layer
    - MD: all 8 county layers
    - SC: 6 of 8 counties
    - IL: 6 of 8 counties
    - GA: 4 of 7 counties
    - MI: 7 of 10 counties
    - PA: 8 of 13 counties
    - Single counties: Montgomery and Williamson TX
    - MN: 40 of 60 counties in the statewide layer, including Hennepin (Minneapolis)
    - CO: 14 counties, including El Paso and Larimer
    - ND: 12 counties
    - ID: 6 counties, including Ada
    - NC: Alleghany
25. **No property address** (situs) even though one is mapped:
    - AZ: Cochise, Mohave, Pima, Pinal and Yuma
    - CA: Los Angeles and Riverside
    - MD, MN and NE statewide layers
    - TN: 67 of 86 counties
    - WA: 17 or more counties, including King and Clark
    - IN: 12 counties
    - TX: Jim Wells, Johnson, Montague and Smith
    - CO: El Paso, Sedgwick and Washington
26. **Homestead flag** is mapped in only 13 states. The other 38 can't tell which parcels a homestead exemption protects.
27. **Land use and zoning on parcels:** the per-county null-count scan is still running, and these results will be added on the next pass.

### C. Deeds, mortgages and sales (equity behind the lien)

28. **Recorded deeds and mortgages are loaded in only three places:** FL (Hernando, Hillsborough, Putnam), IL (Cook sales, PTAX statewide transfers) and NYC (ACRIS real property).
    - None in the other 48 states.
    - Registered but not built: MD SDAT transfers 1–3, NYC ACRIS personal property, Philadelphia RTT, CT CAMA sales, VT property transfers, Norfolk VA transfers, and the Adams, Douglas and Denver CO sales.
    - Also registered but not built: Clark NV sales, Detroit sales, Rutherford TN last sale, St. Joseph IN transfer history, and the Grant, Isanti and Polk MN parcel sales.
29. **Mortgage amounts and satisfactions:** only the NYC ACRIS and MD SDAT transfer files carry mortgage amounts, and MD isn't built. Equity in every other state is the gross value.

### D. Debt lists (judgments, liens, taxes)

30. **Private court money judgments:** only FL and TX. Missing in the other 49.
31. **Tax delinquency lists:** missing in 26 states: AL, AR, CT, FL, HI, IA, ID, IL, KY, LA, MA, MD, ME, MT, ND, NH, NJ, NM, NV, OK, OR, RI, SD, TN, WA and WY.
32. **Tax lien or certificate lists:** only AZ, CA, CO, FL, MD, NE, OH and PA. Missing in 43 states, including the big lien-sale states IL, NJ, IA, AL, SC, KY, MO, IN, MS, WV and DC.
33. **Tax sale, auction, land bank and forfeited land lists:** 17 states registered. Missing in 34. Most of the registered ones (37 sources) are not built.
34. **Foreclosure filings and sheriff sales:** only MD, MI, MN, OH, PA and WI. Missing in 45 states. Prince George's MD, Dakota MN and Milwaukee WI are registered but not built.
35. **Code enforcement liens and charges:** only AZ, FL, MD, NC, OH and PA. Missing in 45 states. The four Miami-Dade lien lists are registered but not built.
36. **Administrative judgments** (city hearing bureaus, labor departments): only FL, IL, LA, MI, NJ and NY.
37. **State tax warrants:** only FL and NY. Missing in 49 states.
38. **Recorded judgment and lien indexes:** only CT, FL and NY.
39. **Evictions and housing court:** NY only.
40. **Federal tax liens:** none anywhere. Only CO UCC is loaded, and OR and CT UCC are not.
41. **UCC filings:** CO only. Missing in 50.
42. **Mechanic's liens:** none anywhere.
43. **Probate and estates:** none anywhere.
44. **Deaths and changes of address:** none anywhere.

### E. Bankruptcy

45. **Only 3 of the 69 enabled bankruptcy feeds have data in the lake:** M.D. Fla., N.D. Ohio and S.D. Ohio. The other 66 are configured and never polled, so the bankruptcy screen is effectively blank in 42 states.
46. **20 districts have no feed:**
    - Robots.txt disallows the feed: areb, arwb, canb, kyeb, mdb, nmb, utb, wawb, wiwb and pamb.
    - The feed is empty: meb, nceb, nyeb and miwb.
    - The feed doesn't answer: txsb and mob.
    - The parser can't read the titles: nywb.
    - Never checked: ilnb, ilcb and ilsb.
    - The result: **AR, IL, MD, ME, NM and UT have no bankruptcy coverage at all.**

### F. Entities, licenses and people

47. **Business registry (LLC to people):** 8 states (CO, CT, DC, IA, NY, OR, PA, RI). Missing in 43, including FL, TX, CA, OH, GA, NC and IL. The matcher also does not yet read `business_role`.
48. **Professional and trade licenses:** 12 states registered. Missing in 39, and 8 of the registered license sources are not built.
49. **City business licenses and tax receipts:** 14 states registered. Missing in 37. Six are not built: Denver, Chicago, New Orleans, Kansas City, Seattle and DE revenue.
50. **Liquor and tobacco licenses:** 7 states. Missing in 44.
51. **Unclaimed property:** 12 states registered, and **none of them are built**. Missing in 39.
52. **Voter files:** NC only, not built. Missing in 50.
53. **Building permits:** NY, PA and TX registered, none built. Missing in 48.
54. **Rental registrations:** NYC and Seattle only, not built.
55. **Charities and nonprofits:** CO only at state level. The IRS EO BMF and 990 officers are registered but not built.

### G. Federal sources registered but not loaded

56. These are registered but not in the lake:
    - SBA: PPP loans, PPP charge-offs, 7(a)/504 loans
    - USAspending recipients
    - IRS: EO BMF, 990 officers
    - SEC: Form D, insiders, investment advisers
    - CMS: NPPES, Open Payments
    - FMCSA carriers
    - DOL wage-and-hour cases
    - Five FCC ULS files
    - Federal Register loan sales

    Loaded today: FJC civil judgments, EPA judicial cases, SBA charge-offs, HUD REO and Federal Register realty notices.

### H. Zoning, ordinances, match runs

57. **Zoning maps:** none in AK, AR, DC, IN, KS, MS, SD and WY. 36 more states have local layers only, with no statewide map. The MD statewide zoning build is unfinished.
58. **Ordinance links:** NJ only. Missing in 50.
59. **Match runs:** none for HI or RI.

### I. Build and bookkeeping gaps

60. **231 of 652 registered sources are not in the lake** (never built, or unfinished):
    - Never built: 18 parcel layers, 68 bankruptcy feeds, all unclaimed property, most licenses, and the federal sets in item 56.
    - Unfinished: `ok.tulsa.parcels`, `md.statewide.zoning`, `ny.nyc.acris.personal` and `in.st_joseph.transfer_history`.
61. **8 sources are in the lake but no longer registered,** so runs may not read them: `la.nola.code_judgments`, `nc.buncombe.unpaid_taxes_2023/2024/2025`, `nc.guilford.delinquent_taxes`, `oh.clermont.delinquent_taxes` and `va.richmond.delinquent_taxes`.
62. **`docs/gaps.md` overstates owner coverage.** It counts a field as covered when a config *maps* it, not when data exists. For example, it lists DE, IN, MD, NE, NH, NJ, RI, TN, UT and WA as having owners, but their statewide layers have none.
63. **Maricopa AZ is loaded (1.76M owners),** but `docs/sources/gap-states.md` says it was "left out on purpose" under A.R.S. 39-121.03 (commercial purpose). One of the two is wrong.
64. **Config values that only the owner can fill:**
    - `sol.yaml`: all 51 jurisdictions are null.
    - `scoring.yaml`: 11 weights are null and there are no tiers.
    - `rules.yaml`: 9 values are null.
    - There is no homestead exemption table per state.
    - There are no buyer criteria in `config/private/queries/`.

---

## Part 2: Where each fix comes from

Tags: **[repo]** = no new source needed, just build, map or fix code. **[free]** = a free public source. **[paid]** = costs money or needs a contract. **[legal]** = needs an owner decision first. URLs are taken from the repo's research files (`docs/parcel-catalog/`, `docs/sources/`, `reports/`) unless a fix says otherwise.

1. **CA owners**
   - [repo] Build `ca.sandiego.parcels` (SanGIS, 1.09M parcels with owner) and `ca.san_jose.parcels`.
   - [paid] County assessor secured roll files: LA about $50, Sacramento free, Alameda about $20, most others under $500.
   - [paid] Fallbacks: ReportAll CA statewide at $6,000, or ParcelQuest.
2. **HI owners and values**
   - [free/paid] County Real Property Assessment tables, joined on TMK: Honolulu RPAD/HOLIS downloads, plus the Maui, Hawaii and Kauai real property tax offices. Statewide TMK boundaries come from `geodata.hawaii.gov/.../ParcelsZoning/MapServer/25`.
   - [legal] Confirm commercial use with gis@hawaii.gov.
3. **IN owners and values**
   - [free] DLGF PARCEL file (owner plus current and prior assessed value, all 92 counties) from the Indiana Gateway: `gateway.ifionline.org/public/download.aspx`, or email data@dlgf.in.gov. Join it to `in.statewide` on the parcel number.
   - [repo] Build `in.marion.parcels`.
   - [legal] IC 5-14-3-3(f) allows matching only, no lists.
4. **TN owners and values**
   - [free] Comptroller county downloads include `Assessment_Data_##.dbf` (owner, values, land use), joined on GISLINK. The page says the data "can be used in a commercial application": `comptroller.tn.gov/office-functions/pa/gisredistricting/redistricting-and-land-use-maps/parcel-data.html`.
   - The 9 missing counties need their own assessors: Shelby (Shelby County Assessor), Knox (KGIS, paid), Williamson, Montgomery, Chester and Hickman.
5. **WA owners**
   - [free] County assessor data downloads, starting with King (`info.kingcounty.gov/assessor/datadownload`), Pierce and Clark. [unverified: not in the repo's research]
   - [repo] Build `wa.thurston.parcels` and `wa.whatcom.parcels`.
   - [legal] RCW 42.56.070(8) bars agencies from giving out lists of individuals for commercial purposes, and some counties limit their owner version to state business. A vendor license (Regrid or ReportAll) avoids that.
6. **UT owners**
   - [free/paid] County assessors and recorders: Davis, Weber, Washington, Cache and Iron next. UGRC's LIR layer carries tax-roll attributes for only some counties.
   - [paid] ReportAll or Regrid.
7. **NE owners**
   - [repo] Build `ne.sarpy.parcels`.
   - [free] Check the NebraskaMAP "Statewide Parcels" 2025 FGDB field list for an owner column (`nebraskamap.gov/datasets/statewide-parcels`).
   - [paid] County assessors, or Regrid.
8. **NH owners and values**
   - [free] Town assessor databases (234 towns, mostly on Vision or AxisGIS), taken town by town.
   - [legal] The NH DRA CAMA table (Parcel Mosaic layer 3) is restricted; ask DRA.
   - [paid] Regrid.
9. **NJ owners and values**
   - [free] SR-1A deed-sales files (the grantee stands in for the owner) and the MOD-IV table for assessed values: `nj.gov/treasury/taxation/pdf/lpt/modiv-2026.zip`.
   - [repo] Map the MOD-IV value fields on `nj.statewide`.
   - [legal] Daniel's Law masks covered owners in every source, vendors included.
10. **RI owners**
    - [free] Municipal assessor databases (39 towns, mostly Vision Government Solutions).
    - [free] Watch RIGIS's statewide aggregation (37 of 39 towns submitted as of fall 2025).
11. **MD owners**
    - [repo] Build `md.sdat.transfers_1/2/3` (data.maryland.gov `ed4q-f8tm`). The latest grantee stands in for the owner, and the files carry mortgage amounts. Also build `md.montgomery.parcels`.
    - [paid] SDAT CAMA master file through SpecPrint (quote only).
12. **ID**
    - [repo] The draft config is blocked because `services1.arcgis.com` answers robots.txt with HTTP 403. Re-test, then finish the 31 counties.
    - [free] Ada County Assessor's own GIS download, for Ada owners.
    - [legal] Read Idaho Code 74-120 (mailing-list limit) first.
13. **MN**
    - [repo] Build `mn.metro.parcels` (MetroGIS regional parcels), which covers the Carver and Scott owners and the Hennepin values.
    - [free] The 27 counties that don't opt in to MnGeo's compiled parcels need their own county GIS or assessor downloads.
    - [repo] Map the address fields on `mn.statewide`.
14. **NY**
    - [repo] Build `ny.local_rolls.parcels`.
    - [free] NYS "Property Assessment Data from Local Assessment Rolls" on data.ny.gov, with owner names, for the 22 counties that don't share GIS parcels. [unverified: confirm owner columns]
    - [free] Fallback: county Real Property Tax Services offices (Monroe, Nassau, Dutchess and Saratoga first).
15. **CO**
    - [free] County assessor downloads for El Paso, Summit, Washington and the 20 missing counties. El Paso's assessor publishes free data downloads. [unverified]
16. **TX**
    - [free] Each county's appraisal district publishes a certified-roll export, usually free (PACS / True Automation "appraisal export"): Smith CAD, Bowie CAD, Hunt CAD, Navarro CAD and the rest.
    - [repo] Build `tx.collin.parcels` and `tx.dallas_city.parcels`.
17. **NC**
    - [free] Clay, Swain and Hoke county GIS or tax office downloads. Also check whether NC OneMap's next release has them.
18. **PA**
    - [free/legal] Allegheny: WPRDC "Property Assessments" on `data.wprdc.org`. The host is blocked from this environment, so it needs an allowlist change.
    - [free] Lancaster and Erie: the county assessment office or PASDA.
    - [paid] The other 54 counties: PASDA where it is free, otherwise Regrid (about 5.95M parcels).
19. **MI**
    - [free] Oakland County's own open-data parcel and assessing layers. [unverified]
    - [paid] The 73 missing counties: county downloads (often a fee) or ReportAll MI at $7,000.
20. **OR**
    - [paid] Marion owners: the county assessor roll (the free layer strips owners).
    - [paid] Clackamas and Washington owners are only in Metro's RLIS subscription.
21. **ME**
    - [free] Aroostook from Maine GeoLibrary town parcels, or from municipal assessors.
22. **Thin county-only states**
    - [free] The repo's Hub and Socrata discovery job (`config/discovery.yaml`) finds owner layers. The named big counties to try first:
      - Louisville (LOJIC) and the KyGovMaps PVA layers
      - Johnson KS (KORA form) and Sedgwick (firewall issue)
      - St. Louis City (free city shapefiles)
      - Polk IA (scrape-only today)
      - Clark NV ($2,500 roll)
      - Mat-Su (internal-use license)
      - Fairfax and Arlington (no owner layer)
      - Jefferson Parish
      - Bernalillo (configured)
      - Tulsa (finish the build)
    - [paid] Statewide fallbacks: ReportAll GA $9,000, IL $6,000 and IA $6,000; Regrid for the rest.
23. **Values thrown away** [repo]: add `tax_year` to those 13 configs, or a constant year from the layer's roll date. This is a config change, and no new source is needed.
24. **Missing values**
    - [repo] Check each layer for an unmapped value column. VA locality layers and MD county layers often have one.
    - [free] HI, IN, NJ and TN: same as fixes 2, 3, 9 and 4.
    - [free] ME: municipal valuation from Maine Revenue Services.
    - [free] AZ: county assessor layers. The ADWR copies carry owners only, and Maricopa already has values.
    - [free] Values can be rolled forward with FHFA HPI at ZIP5 or county level (public domain; needs an XLSX reader).
25. **Missing addresses** [repo]: in each listed layer the situs fields exist but come out empty, so check the field names and the `situs_form` setting. Also map the mailing fields where only those exist (MD has OWNADD1 and others), and run the Census batch geocoder (free) to standardize them.
26. **Homestead** [repo/free]: map the homestead or exemption column where the layer has one, which many assessor layers do. Otherwise use each state's exemption statute, with NCLC "No Fresh Start 2025" as a cross-check.
27. **Land use and zoning:** pending.
28. **Deeds and sales**
    - [repo] Build the registered but unbuilt sets listed in gap 28.
    - [free] NJ SR-1A, the IL PTAX already loaded, and Broward and Pasco FL Official Records downloads.
    - [legal] Maricopa Recorder JSON API (names and doc codes); confirm the terms.
    - [paid] Most other recorders: Cook County Clerk at $400 a year, or ATTOM and Cotality.
29. **Mortgages** [repo]: build MD SDAT (it has mortgage amounts). No free bulk mortgage index was found for King, Miami-Dade or Cook, so elsewhere it is [paid]: ATTOM, Cotality or PropertyRadar.
30. **Court judgments**
    - [free] NYC OATH docketed judgments, Detroit DAH blight judgments, NJ DOL wage watchlist and WALL, Louisville lien final orders, TCEQ civil judgments, and the Harris County District Clerk datasets.
    - [paid] MD District Court bulk ($2,775 plus $500 per update), Maricopa Justice Courts ($33 a month plus an agreement), NC AOC (needs a $5,000 bond), NJ CJOD reports and MN court extracts.
    - [paid] Nationally: UniCourt (about $2,250 a month), Trellis or Docket Alarm.
    - Everywhere else: the records-request program in `reports/Republished court judgment datasets.md`.
31. **Tax delinquency** [free]
    - County treasurer delinquent lists. Many are ArcGIS or Socrata layers that the discovery job finds, and the rest are published as newspaper legal notices before each sale.
    - Big counties to try first: Cook IL (Treasurer annual tax sale list), King WA (foreclosure list), Shelby TN, Jefferson KY and Clark NV.
32. **Tax liens** [free]: county lien-sale lists and certificates. Examples are Maricopa "Unsold Lien Parcels" (registered) and Lake, Saguache and Douglas CO (registered, not built). NJ municipal tax sale notices and IL county "annual tax sale" lists come next.
33. **Tax sales and land banks** [repo]: build the 37 registered sources. [free] Also add Genesee MI land bank (14,053 parcels) and the Oregon DLCD surplus inventory.
34. **Foreclosures** [repo]: build Prince George's MD (78,657 parcels), Dakota MN sheriff sales and Milwaukee WI foreclosures. [free] Also add Stark OH sheriff civil sales and the Dallas County JP list.
35. **Code liens** [repo]: build the four Miami-Dade lien lists. [free] Also add city open-data code-lien layers: Detroit, Chicago DOAH and Baltimore citations (already registered).
36. **Administrative judgments** [free]: Chicago DOAH ordinance violations and the Detroit DAH archive (629,962 records).
37. **State tax warrants** [free]: state revenue department delinquent lists. Examples:
    - CA FTB and CDTFA top 500
    - SC DOR top 250 (all in lien status)
    - NE DOR list (over $20k, lien filed)
    - DE top 100
    - FL DOR warrants of $100k or more (monthly Excel)
    - PA L&I UC tax liens (weekly)
38. **Judgment lien indexes** [free]: CT is loaded. The CA SOS JL1 and GA GSCCCA lien indexes are [paid] subscriptions.
39. **Evictions** [free]: Franklin OH Municipal Court nightly CSVs, the Dallas County JP eviction list, and Harris JP (in the TX judgments). Eviction Lab data is licensed [paid/legal]. Check the sealing laws in 17–19 states plus DC first.
40. **Federal tax liens** [legal]: FL Sunbiz SFTP federal lien files. The shared public password needs the owner's OK under the no-login rule. [free] Also CO UCC (IRS liens) and the OR UCC rolling month `snfi-f79b`.
41. **UCC** [free]: CT `xfev-8smz` and OR `snfi-f79b` / `2kf7-i54h` (Socrata, Public Domain).
42. **Mechanic's liens:** no free bulk source exists. In FL they sit inside the Official Records `LN` type, so [repo] split them out of the loaded FL recorder data.
43. **Probate:** no bulk index exists. [free] FL's statewide public-notice site must be searchable by party name (Fla. Stat. 50.0211). [paid] Otherwise per-county requests.
44. **Deceased and change of address:** no free, compliant source. [paid/legal] The NTIS LADMF needs certification. Do per-case checks through PACER and probate.
45. **Bankruptcy feeds** [repo]: run the RSS poller for the 66 enabled feeds; `refresh.yml` should already schedule it, so check why only flmb, ohnb and ohsb wrote rows.
46. **Missing districts**
    - [free] The FJC Bankruptcy IDB covers every district since FY2008, including the robots-blocked ones (`cpbank18on.zip`, 887 MB, no login: `fjc.gov/research/idb`).
    - [free] CourtListener quarterly dockets bulk (free S3) for the case names.
    - [repo] Probe ilnb, ilcb and ilsb RSS feeds; IL has never been checked.
    - [paid] Per-case lookups through PACER, at no more than about $28 a quarter.
47. **Business registries**
    - [free] PA `xvd7-5r2c` (4.2M officer rows), DC beneficial owners, and the NY all-filings sets.
    - [free] OH monthly business reports (the host is behind Cloudflare; retry later).
    - [legal] FL Sunbiz (shared SFTP password).
    - [paid] GA $1,000 plus a monthly fee, IN $8,000, KY $2,000 a month, NC $750 plus $2,000 a year, SC about $12,000 a year, WY $10,200 a year, TX $1,350 master file, and others in `docs/sources/business-registry-sources.md`.
48. **Licenses**
    - [repo] Build the 8 registered license sources.
    - [free] CA CSLB contractor master, FL DBPR weekly files and TX TDLR "All Licenses" (already registered).
49. **City business licenses** [repo]: build the six. [free] Also add LA and SF business lists (registered) and more city portals through the discovery job.
50. **Liquor** [repo]: build CO, MO, NY and OR. [free] Most state alcohol control boards publish licensee lists.
51. **Unclaimed property**
    - [repo] Build the 12 registered sources.
    - [free] Oklahoma full CSV (472.6 MB, yearly), California SCO weekly CSV, and the NY OSC quarterly file (on request).
    - IL has no bulk files, and finders there need a license.
52. **Voter files** [free/paid/legal]: state-by-state access rules are in `docs/voter_file_requests.md` and `reports/Voter file access by state.md`. [repo] Build NC first.
53. **Building permits** [repo]: build NYC DOB `ipu4-2q9a`, Philadelphia L&I and the TX set. [free] Also add East Baton Rouge `7fq7-8j7r` and Collin CAD `82ee-gbj5`.
54. **Rental registration** [repo]: build NYC HPD and Seattle. [free] Other city registries can come through the discovery job.
55. **Nonprofits** [repo]: build IRS EO BMF and 990 officers (IRS e-file XML).
56. **Federal sets** [repo]: build each one with the lake build command; they are all free downloads.
57. **Zoning** [free]: see `docs/sources/zoning-sources.md`. [repo] Finish `md.statewide.zoning`.
58. **Ordinances** [free/legal]: the municipal code publishers' public library indexes (Municode, General Code eCode360, American Legal). Read their terms first.
59. **HI and RI match runs** [repo]: add them to `STATES` in `equity/matching/resolve.py` once owners exist (fixes 2 and 10).
60. **Unbuilt sources** [repo]: run the lake build for each one (`uv run python -m equity.lake run --only <ids>`). `uv run python -m equity.lake hosts` groups them by host, which shows which hosts are blocked.
61. **Orphan sources** [repo]: re-register them or delete them from the lake.
62. **`docs/gaps.md`** [repo]: have `gaps.py` read the lake's `_counts.json` and part counts, so "owner" means owner rows exist, not just a mapped field.
63. **Maricopa** [legal]: owner decision. Either file Maricopa's commercial-use statement, or remove the source.
64. **Owner-only config values** [owner]:
    - For `sol.yaml`, the White and Williams 50-state chart (rev. 2020) is a cross-check, and each state's statute is the source.
    - For homestead amounts, use the state statutes plus 11 USC 522(d).
    - Set the weights, tiers and buyer criteria yourself.
