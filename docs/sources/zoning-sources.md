# Zoning maps and municipal code text: free, bulk sources

Checked 2026-11-20. Nobody was contacted.

**How each fact was checked.** From this session, `www.arcgis.com` and `*.arcgis.com` (ArcGIS
Online and hosted feature services) answered, so every ArcGIS item, license field and feature
count below was read live (**verified**). Every other host was refused by the session proxy or
did not resolve: zoningatlas.org, mercatus.org, anselm.edu, library.municode.com, ecode360.com,
codelibrary.amlegal.com, law.resource.org, catalog.data.gov, huggingface.co, mdpgis.mdp.state.md.us
and maps.edc.uri.edu. GitHub API calls were limited to this repository. Facts about those
sources come from web-search results only (**search only**). Read the live page before relying
on any of them.

---

## A. Zoning district maps

### A1. National Zoning Atlas (NZA): not usable for bulk loading

| | |
|---|---|
| Site | https://www.zoningatlas.org (Land Use Atlas, Inc.; founded by Sara Bronin, Cornell) |
| Coverage | About 30,000 zoning codes are in scope. One 2024 report says about 36 states are mapped in part ([Route Fifty](https://route-fifty.com/management/2024/08/see-how-your-state-uses-zoning-codes-control-land-use/398787)). New America lists 16 complete states: AK, AZ, CA, CO, CT, DE, HI, MA, NH, NC, NM, NV, RI, UT, VA and VT ([New America](https://www.newamerica.org/insights/where-is-multi-family-housing-actually-allowed/)). |
| Granularity | **One record per zoning district**: district polygons carrying about 30 regulatory attributes (uses allowed, minimum lot size, parking, ADUs and so on). The data is not per parcel ([HUD Cityscape paper](https://www.huduser.gov/portal/periodicals/cityscape/vol25num3/ch3.pdf); [data dictionary](https://www.mercatus.org/sites/default/files/2024-09/zoning_atlas_data_dictionary_1.pdf)). |
| Format | Web map only. There is no bulk download on zoningatlas.org. |
| License | **Restrictive.** The terms at https://zoningatlas.org/terms say that without express written permission you may not "use, host, store, reproduce, modify, license, create derivative works of, communicate, download, publish, publicly display, or distribute any of the Website Content". Commercial use and scraping are also barred. Screenshots are allowed with the credit "National Zoning Atlas, online at zoningatlas.org" (search only). The NZA FAQ says a licensing arm started in spring 2026 and sells regulatory and geospatial data, including tabular "Zoning Snapshots", to third parties ([FAQ](https://www.zoningatlas.org/faqs), search only). |
| ArcGIS item | `13d78ab5ad5b4651a1c21524daab7fd1` is a Web Mapping Application only, with an empty `licenseInfo` (verified). |
| Hosts | zoningatlas.org, www.zoningatlas.org |

**Conclusion:** NZA's own data is not free to bulk load. Use the open state and partner copies
listed below. Several of them were built with the NZA method, so they share its attribute set.

**Mercatus mirror of partner-team data.** https://www.mercatus.org/state-and-regional-zoning-atlas-datasets
links GeoJSON and XLS/CSV files from state teams that Mercatus funded: Montana (Frontier
Institute, 2023), Middle Tennessee (Beacon Center, 2023), Texas DFW (2024) and others. The files
were hosted at `statezoningatlasdata.s3.amazonaws.com`. **That bucket now returns
`NoSuchBucket` (verified 2026-11-20)**, so the links are dead. A GitHub copy,
`github.com/MercatusUrbanity/ZoningAtlas`, has files such as `MT_zoning.geojson` and
`Central_TN_zoning.geojson` (search only; its license was not seen). No data license was found for
any Mercatus file. NZA's code repositories (`github.com/zoningatlas`: web-map, combine-jurisdictions)
are reported as MIT, but that license covers the code, not the data.

### A2. Statewide and regional zoning layers

Feature counts are from `/query?where=1=1&returnCountOnly=true` (verified). Any ArcGIS
FeatureServer can be paged with `/query?where=1=1&outFields=*&f=geojson&resultOffset=N`, up to
`maxRecordCount` features per page.

| State | Layer, owner | Endpoint | Features | Updated | License or terms |
|---|---|---|---|---|---|
| **CA** | California Statewide Zoning North / South, Office of Land Use and Climate Innovation (formerly OPR). 535 of 539 jurisdictions. Zoning was transferred onto assessor parcel shapes, so the polygons are per parcel. | `services8.arcgis.com/Xr1lDrwMv89PhjD9/arcgis/rest/services/California_Statewide_Zoning_North/FeatureServer/1` and `.../California_Statewide_Zoning_South/FeatureServer/0`; shapefile zip of about 747 MB on data.ca.gov | 264,417 + 304,324 | 2024-10-17 data; item 2024-12-19 | ArcGIS `licenseInfo` is empty. data.gov says "License not specified". The description is a disclaimer: "provided as a public service, for informational purposes only" (verified). |
| **WA** | Washington State Zoning Atlas (WAZA), Dept. of Commerce. 320 jurisdictions (39 counties, 281 cities), NZA-style attributes. | `services6.arcgis.com/tboeqGwETr5ppr5Q/arcgis/rest/services/WAZA_Prototype_Layers/FeatureServer` (0 Zones, 1 Overlays, 2 Jurisdictions); maxRecordCount 1000 | 470,130 zones | 2026-07-02 | Terms of use: "as-is", illustrative only, user holds Commerce harmless. Clause 5 cites RCW 42.56.070(8): no commercial use of **lists of individuals**. Zoning polygons hold no personal data, but note the clause (verified). |
| **RI** | Rhode Island Zoning and Overlay Zones, RIGIS / URI EDC (Land Use 2050). All 39 municipalities, plus a generalized statewide class. | `services2.arcgis.com/S8zZg9pg23JUEexQ/arcgis/rest/services/RI_Zoning/FeatureServer` (0 overlays, 1 municipal zoning) | 15,733 + 1,639 | 2026-03-11 | "Shared under the RIGIS license agreement": as-is, acknowledge RIGIS and the producer in derived products (verified). Data hub: www.rigis.org. |
| **MD** | Generalized Zoning 2025, Maryland Dept. of Planning. 11 generalized classes; county zoning plus municipal annexations through Sept 2025. | `mdpgis.mdp.state.md.us/arcgis/rest/services/PlanningCadastre/Generalized_Zoning_2025/MapServer/0` (query supports geoJSON, max 2000; not reachable from here). Mirror: `services.arcgis.com/njFNhDsUCentVYJW/arcgis/rest/services/Generalized_Zoning_2025_Draft/FeatureServer/0` | 2,257 (mirror) | 2025-12-01 | State of Maryland disclaimer only, "as is"; no restriction on reuse (verified). |
| **NH** | NH Zoning Atlas Full Districts, Saint Anselm College Center for Ethics in Society. Statewide, NZA method. | `services1.arcgis.com/aguSsLS841Hp3EC4/arcgis/rest/services/NH_Zoning_Atlas_Full_Districts/FeatureServer/0` (also `_2022` versions) | 3,302 | 2024-03-12 | "Informational only", no liability; no restriction on reuse (verified). |
| **VT** | Vermont Zoning Public View, Agency of Commerce and Community Development (from the UVM Vermont Zoning Atlas). | `services1.arcgis.com/rnCtPMpypTkqwvYT/arcgis/rest/services/Vermont_Zoning_Public_View/FeatureServer/8` | not counted | 2024-10-25 | `licenseInfo` is empty. UVM's "Vermont Zoning Atlas Abbreviated" web map (`f203c5cf70e8496e8ed8e2ce17c431f8`) says **CC BY** (verified). The Vermont Open Geodata Policy (v1.1, Dec 2025) says no cost, no login and no request form ([policy](https://files.vcgi.vermont.gov/other/policies/vermont-open-geodata-policy.html), search only). VCGI zoning standard v2.0, built on the NZA schema, is planned as a statewide open layer ([standard](https://files.vcgi.vermont.gov/other/standards-guidelines/zoning/zoning-standard.html)). |
| **MA** | (a) MBTA Communities 3A District Atlas, MassGIS/HLC: 3A districts and their parcels only. (b) Legacy statewide `ZONING_POLY`: MassGIS says it is not kept up to date ([PIE-LTER note](https://pie-lter.ecosystems.mbl.edu/section/zoning)). (c) MAPC Zoning Atlas covers Greater Boston; code under 0BSD ([zoningatlas.mapc.org](https://zoningatlas.mapc.org/about/)). | (a) `services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/MBTA_Communities_3A_District_Atlas/FeatureServer` | (a) 494 districts, 29,992 parcels | (a) 2026-11-03 | (a) "Data are public", with a caution that it is not a legal record (verified). Download page: [mass.gov](https://www.mass.gov/info-details/massgis-data-mbta-communities-3a-district-atlas). |
| **NJ** | (a) NJTPA Zoning Atlas, covering the 13-county north NJ region; polygons digitized from municipal maps where no GIS existed. (b) NJ DCA "Municipal Zoning" is **points that link** to each town's zoning map and ordinance, not polygons. (c) Pinelands Municipal Zoning. | (a) `gis.njtpa.org/server/rest/services/LandUse/NJTPA_Zoning_Atlas/FeatureServer/0` (b) `services.arcgis.com/Aur8tCo478N3VovT/arcgis/rest/services/Municipal_Zoning/FeatureServer` (c) `services1.arcgis.com/nCm6SZaiGMuGX35l/arcgis/rest/services/Pinelands_Municipal_Zoning/FeatureServer` | not counted | (a) 2026-10-09 (b) 2026-03-23 | (a) Disclaimer only. (b) Asks for credit to NJDCA and NJOGIS (verified). (c) NJ Pinelands Commission Data Distribution Agreement; read it before use. |
| **CT** | No official statewide polygon layer found on the CT Geodata Portal (search only). The Connecticut Zoning Atlas (2,620 districts, 169 towns) is on NZA, so NZA's terms apply. Town layers exist, for example Hartford (`data.hartford.gov`, asks for credit). | — | — | — | — |
| **MN** | No statewide zoning layer. Metropolitan Council's Generalized Land Use 2020 (7-county metro) is land use, not zoning; public domain under MGDPA ([gisdata.mn.gov](https://gisdata.mn.gov/dataset/us-mn-state-metc-plan-generl-lnduse2020)). Saint Paul's zoning layers say "Public Domain" in `licenseInfo` (verified). | — | — | — | — |

Hosts for A2: `www.arcgis.com`, `services*.arcgis.com` (services1, 2, 6 and 8 are used above),
`gis.njtpa.org`, `mdpgis.mdp.state.md.us`, `data.ca.gov` and `lab.data.ca.gov`, `www.rigis.org`,
`geodata.vermont.gov`, `www.mass.gov` and `s3.us-east-1.amazonaws.com` (MassGIS downloads).

### A3. Finding city and county zoning layers through the ArcGIS Online search API

The endpoint is `https://www.arcgis.com/sharing/rest/search`. It is public, needs no key and
returns JSON. Every query below was run on 2026-11-20 (verified).

```bash
curl -G https://www.arcgis.com/sharing/rest/search \
  --data-urlencode 'q=title:zoning type:"Feature Service" access:public' \
  --data-urlencode 'bbox=-125,24,-66,50' \
  --data-urlencode 'f=json' --data-urlencode 'num=100' --data-urlencode 'start=1'
```

- **`total` stops at 10,000.** To count or list everything, split the query by `created:[ms TO ms]`
  ranges. Split by half-years from 2014 to 2026, `title:zoning type:"Feature Service" access:public`
  inside the US bounding box gave **about 63,700 items**. Many are copies, student projects,
  tests or buffers.
- Narrower queries:
  - `title:"zoning districts" type:"Feature Service"` in the US box: **1,987**
  - `title:zoning type:"Feature Service" contentstatus:org_authoritative` in the US box:
    **2,632**. These are items an organization marked authoritative, and they are the best list
    to start from.
  - `title:zoning contentstatus:org_authoritative` with no box and any type: 6,557
- Each result has `id`, `owner`, `orgId`, `url` (the FeatureServer), `extent`, `modified` and
  **`licenseInfo`**, which is free-text HTML set per item. A sample of authoritative items shows
  the range: "Public Domain" (Saint Paul); "Users may view, download, and use the data for lawful
  purposes" (Albemarle County, VA); disclaimer only (Eugene, Garner, Grant County WA, Charles
  County MD); and **empty** for many. Store `licenseInfo` with every layer, classify it, and treat
  an empty value as unknown, not as open.
- Item metadata: `https://www.arcgis.com/sharing/rest/content/items/{id}?f=json`
- Hub's OGC search API, `https://hub.arcgis.com/api/search/v1/collections/dataset/items?q=zoning`,
  also works but stops at 10,000 too. The older `https://hub.arcgis.com/api/v3/datasets?q=zoning`
  reports 508,992 matches for the bare word "zoning", which is mostly noise.
- Caveats:
  - Layers do not share a schema (zone code and description fields differ in every city).
  - Many cities run their own ArcGIS Server rather than ArcGIS Online, and those servers are not
    indexed here.
  - Esri's own ArcGIS Online terms govern use of the API itself.
  - Feature services allow `/query`, and some also allow `Extract`. That is the publisher's
    intended access path, not scraping.
- Hosts: `www.arcgis.com`, `hub.arcgis.com`, `services*.arcgis.com`, `*.maps.arcgis.com`, plus each
  city's own GIS host.

---

## B. Municipal code and zoning ordinance text

### B4. Open or bulk sources

| Source | Coverage | Format | License | Hosts |
|---|---|---|---|---|
| **Open Law Library**, https://openlawlib.org | Washington DC (first client 2014; platform 2018), Baltimore, San Mateo CA, Maryland (COMAR, the first state, around Dec 2025) and about a dozen tribal governments ([StateScoop](https://statescoop.com/ux-user-experience-open-law-library-saving-legal-code/), [StateScoop MD](https://statescoop.com/maryland-oll-legal-code-comar/), search only). No complete client list was found. | Git repositories per jurisdiction; XML source and HTML builds | The government owns its laws ("Own Your Laws"). Repository LICENSE files were **not seen**. | openlawlib.org, github.com, the jurisdiction's own site |
| **DC Council on GitHub**, `github.com/DCCouncil/law-xml` (also law-html, law-xml-codified) | DC Code and DC laws; the Council calls it the authoritative source | XML | LICENSE file not seen. Other DCCouncil and DCgov repositories use CC0 1.0 ([DCgov/license](https://github.com/DCgov/license), search only). Government-edicts doctrine applies anyway (B6). | github.com |
| **San Francisco**, `github.com/SFMOCI/openlaw` | SF municipal codes. Posted in 2013 with American Legal; probably stale. | Raw data files | Not seen | github.com |
| **LOCUS-v1**, `huggingface.co/datasets/LocalLaws/LOCUS-v1` ([arXiv 2606.19334](https://arxiv.org/pdf/2606.19334)) | 2.2M local laws from 9,239 cities and counties. For each county, v1 keeps the largest code of the county or its largest city. | HF dataset (raw corpus about 80 GB from PDFs) | **CC BY-NC 4.0** (search only). **Non-commercial**, and the paper says collection "worked around ... anti-bot protections", so its source platforms may have been crawled against their terms. Raise both with whoever approves sources before loading. | huggingface.co |
| **Eviction Lab NZLUD**, https://evictionlab.org/national-zoning-and-land-use-database/ ; `github.com/mtmleczko/nzlud` | 2,600+ municipalities | CSV of NLP-derived zoning measures. **Not full ordinance text.** | "Publicly available for anyone to access and build on"; formal license not seen | evictionlab.org, github.com |
| **NJ DCA Municipal Zoning** (A2, row NJ) | All NJ municipalities, as known to DCA in March 2026 | Points that link to each ordinance and map | Credit NJDCA and NJOGIS | services.arcgis.com, plus each link's host |
| **Public.Resource.Org**, https://law.resource.org/pub/us/ | State codes; "State and Local Public Safety Codes" (last changed 2014); Sonoma County. No current multi-city municipal code collection found. | PDF, HTML | Public domain position | law.resource.org |
| **Council Data Project**, https://councildataproject.github.io | About 17 city councils | Meeting transcripts, votes and Legistar data. **Not codified code.** | Code is open source; data license not seen | github.com |
| **Free Law Project / CourtListener** | Court opinions only. No municipal codes. | — | — | — |

City open-data portals sometimes post the code as a dataset, for example "City of Sioux Falls
Code of Ordinances" on catalog.data.gov. Find them case by case. A data.gov CKAN search was not
reachable from this session.

### B5. Terms of the main code publishers

All four big hosts sell codification to governments and present their sites as licensed use.
**None was found to offer a free bulk or data license to the public.**

- **Municode / CivicPlus** (`library.municode.com`, terms at https://www.municode.com/code/page/terms-use
  and https://library.municode.com/termsofuse.htm): the terms grant "a nonexclusive,
  nontransferable, revocable, limited license to access and use this Website and Content" and say
  "Any use of the Content not expressly permitted by these Terms and Conditions of Use is a
  breach". Title to the content "remains with Municipal Code Corporation or the municipalities".
  Florida law governs (search only; no robots clause seen in the snippets). CivicPlus's API
  Acceptable Use Policy bars "automated scraping" of its APIs
  ([CivicPlus](https://www.civicplus.help/docs/civicplus-proprietary-api-acceptable-use-policy)).
  There is no public bulk API.
- **General Code / eCode360** (`ecode360.com`; owned by ICC with American Legal Publishing, Code
  Publishing Co. and Franklin Legal): ICC's Terms of Use name eCode 360 as E-Content. Its license
  is "limited, non-exclusive, non-transferable, non-sublicensable, revocable" and **excludes "use
  of data mining, robots, or similar data" tools** ([ICC Terms of Use](https://www.iccsafe.org/about/terms-of-use/),
  search only; full clause not seen). Sanctioned machine access is the **eCode360 API**, a REST
  interface offered to partner communities and developers
  ([ICC developers](https://www.iccsafe.org/developers/)). It is not open, and its pricing was not
  found.
- **American Legal Publishing** (`codelibrary.amlegal.com`; part of General Code/ICC since the
  merger, per [ICC](https://www.iccsafe.org/about/periodicals-and-newsroom/industry-leaders-american-legal-publishing-and-general-code-unite-to-provide-communities-with-best-in-class-codification-services/)):
  the text of its Terms of Use was not found. Expect the ICC/General Code terms above to apply.
  Some city codes carry the **city's** own notice; for example, the LA Municipal Code PDF says "no
  part ... may be ... stored in a database or retrieval system without prior written permission
  of the City of Los Angeles".
- **Code Publishing Co.** (`codepublishing.com`, Seattle; part of General Code since Dec 2021):
  terms text not found. It is now a General Code company, so the same position applies.

**Practical rule.** Do not crawl these four hosts. For each jurisdiction, take the code from:
(a) the government's own site or open-data portal;
(b) a git or Open Law Library publication;
(c) a records request to the city;
(d) a written license from the publisher.

### B6. Legal background

- **Georgia v. Public.Resource.Org, Inc., 590 U.S. 255 (2020)** ([opinion](https://www.supremecourt.gov/opinions/19pdf/18-1150_7m58.pdf)).
  Under the government-edicts doctrine, officials acting in their legislative or judicial role
  cannot be "authors" for copyright purposes. Even the non-binding annotations that Georgia's
  legislature commissioned were held uncopyrightable. The Court's rationale was that "no one can
  own the law". **For municipal codes:** ordinances that a city council adopts are themselves not
  copyrightable. The case dealt with a state code, but the rule turns on who acts as legislator,
  and a city council fits.
- **What a codifier may still claim:** its own editorial material, for example headnotes,
  annotations, indexes, search tools and site design, **if** a private party wrote it and the
  legislature did not adopt it. It may also rely on its **terms of use**, which are a contract
  claim and not copyright. Georgia removes the copyright objection to reusing ordinance text. It
  does not license the act of crawling a publisher's site against its terms.
- **Model codes adopted by reference:** *Veeck v. SBCCI*, 293 F.3d 791 (5th Cir. 2002, en banc)
  allowed posting a building code "as enacted" by a town. *ASTM v. Public.Resource.Org* (D.C. Cir.
  2018, 896 F.3d 437; and 2023) found posting incorporated standards to be fair use. The Pro Codes
  Act has been proposed to protect such standards ([CRS R47656](https://www.everycrsreport.com/files/2023-08-21_R47656_6f5fd47af900ea6408da10260283e38462be910e.html)).
  This matters because zoning ordinances often incorporate building and fire codes (ICC I-codes).
  Leave incorporated standards out of the corpus.

---

## Recommended load order

1. **State and regional zoning layers on ArcGIS (A2):** CA North and South, WA WAZA, RI, NH, MD,
   VT, MA 3A and NJTPA. They are free, public FeatureServers with disclaimer-only or attribution
   terms, need one host family (`*.arcgis.com`), and roughly 1.1M district polygons are already
   counted. Store `licenseInfo` with each layer. Get approval for the WA RCW 42.56.070(8) clause
   and the RIGIS attribution requirement.
2. **City and county zoning from the ArcGIS search API (A3):** start with the 2,632
   `org_authoritative` items in the US. Load only items whose `licenseInfo` is public domain or
   explicitly allows reuse. Put items with empty or disclaimer-only text in a review queue.
3. **Pointer table for ordinance text:** the NJ DCA links layer, the government-hosted code URL
   for each jurisdiction, and Open Law Library and DC Council git repositories for the few
   jurisdictions that publish that way. Store citations and URLs, not text, until each source is
   cleared.
4. **NZLUD (Eviction Lab):** use its derived zoning measures as attributes for about 2,600 towns
   after the LICENSE file is confirmed.
5. **On hold:**
   - LOCUS-v1: CC BY-NC and how it was collected.
   - National Zoning Atlas: its terms forbid downloading; the paid license is the only route.
   - The Mercatus mirror: its S3 bucket is gone and it has no data license.
   - Any Municode, eCode360, AmLegal or Code Publishing content without a written license.

**Hosts to allow for steps 1 to 3:**
- Steps 1 and 2: `www.arcgis.com`, `hub.arcgis.com`, `services.arcgis.com`,
  `services1.arcgis.com` through `services9.arcgis.com`, `gis.njtpa.org`,
  `mdpgis.mdp.state.md.us`, `data.ca.gov`, `www.rigis.org`, `geodata.vermont.gov`
- Step 3: `github.com`, `raw.githubusercontent.com`, `evictionlab.org`
