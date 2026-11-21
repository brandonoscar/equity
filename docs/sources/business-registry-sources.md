# Business-entity registry and UCC sources: all states plus DC

Checked 2026-11-21. This covers free bulk data only: downloadable files, open-data portals
(Socrata, CKAN, ArcGIS), SFTP, or official APIs whose terms allow automated use. Scraping entity
search pages, sources that need a login or account, and paid products are all excluded.

**How the facts were checked.** Most state sites could not be fetched from this environment, so
most rows rest on web-search results that quote official pages. Those rows are marked
**unverified**. A row is marked **verified** only where the API was queried from here on
2026-11-21 (column lists, row counts, license field). Prices are as stated on official pages
found in search, or by vendors where noted. Prices change, so treat them as indicative.

Legend: RA = registered or statutory agent. "Officers" = officers, managers, members, partners,
governors or beneficial owners.

## Summary table

| St | Source | Free bulk? | Officers | RA | Format / frequency | Cost / terms | Status |
|---|---|---|---|---|---|---|---|
| AK | Division of Corporations (CBPL) | No | (search only) | (search only) | none found | No bulk product found | unverified |
| AL | SOS Business Entities | No | – | – | none found | None found | unverified |
| AR | SOS via portal.arkansas.gov (Tyler) | No | ? | ? | FTP full download | Paid; list builder $0.10/record; Tyler account | unverified |
| AZ | Corporation Commission | No | – | – | none found | Public-records requests only | unverified |
| CA | SOS bizfile "BE & UCC Bulk Orders" | No | ? | ? | bulk files | Paid (price not found) | unverified |
| **CO** | data.colorado.gov `4ykn-tg5h` (loaded) | **Yes** | No | Yes | Socrata, daily | Public Domain | verified |
| **CO UCC** | data.colorado.gov `wffy-3uut`, `8upq-58vz`, `4am6-w6u4` | **Yes** | – | – | Socrata, daily | Public Domain | verified |
| **CT** | data.ct.gov `n7gp-d28j` + `ka36-64k6` + `qh2m-n44y` (loaded) | **Yes** | Yes (principals) | Yes | Socrata, daily | Public Domain | verified |
| **CT UCC** | data.ct.gov `xfev-8smz` | **Yes** | – | – | Socrata, daily | Public Domain | verified |
| **DC** | DLCP via DC GIS ArcGIS MapServer (Corporate Registration, Beneficial Owners, Trade Name) | **Yes** | **Yes (beneficial owners)** | Yes | ArcGIS REST, about daily | CC BY 4.0 per data.gov (confirm on opendata.dc.gov) | verified (fields, counts) |
| DE | Division of Corporations | No | – | – | none | No bulk entity product; site prohibits data mining | unverified |
| **FL** | Sunbiz quarterly and daily data files | **Yes** | **Yes (up to 6)** | Yes | Fixed-width text, quarterly and daily, SFTP | Free, "informational purposes, as is"; no explicit commercial-use clause found | unverified (official pages via search) |
| GA | GTA / SOS bulk corporations data | No | Yes | Yes | SFTP | $1,000 one-time plus monthly fee; signed agreement | unverified |
| HI | data.honolulu.gov `9k54-ztb8` | Stale | ? | ? | Socrata | Dataset says it is out of date; no license tag | unverified |
| **IA** | Iowa Data Hub dataset 554 (was Socrata `ez5t-3qay`) | **Yes** | No | Likely (sources conflict) | CSV, about monthly | CC BY 4.0 | partly verified (Socrata API is gone; new host blocked here) |
| ID | SOS master list / UCC files | No | ? | ? | CSV | $30 registration plus per-file fees; UCC $125 per file | unverified |
| IL | SOS Dept. of Business Services | No | ? | ? | FTP by contract | Contract pricing; site bans bulk copying | unverified |
| IN | INBiz Bulk Data Services | No | ? | ? | monthly file | $8,000 one-time or $9,500/yr; INBiz account | unverified |
| KS | SOS / Information Network of Kansas | No | No | Yes | database request | $150 request fee; full database via INK | unverified |
| KY | SOS Bulk Data Service (Kentucky.gov) | No | Yes | Yes | monthly, weekly, daily | Subscriber agreement; vendor cites $2,000/mo | unverified |
| LA | SOS Commercial API | No | ? | ? | API | $500/yr subscription | unverified |
| MA | Corporations Division | No | – | – | none found | None found | unverified |
| MD | SDAT master file via SpecPrint | No | ? | Yes | master file | Paid through a contractor | unverified |
| ME | SOS via InforME | No | ? | ? | monthly or weekly | $600/mo full; $300/wk updates | unverified |
| MI | LARA (MiBusiness Registry) | No | – | – | none found | Counts only | unverified |
| MN | SOS business bulk order | No | Yes (filing parties) | Yes | bulk files | $710 full; $30 active-business CSV; account and license required | unverified |
| MO | SOS Corporations | No | – | – | none found | None found | unverified |
| MS | SOS "Business Reports" export tool | Partial | ? | ? | Excel export from a search UI | Free, but a search tool, not a bulk feed | unverified |
| MT | SOS corporate bulk download | No | ? | ? | data file plus spec | Sold under MCA 2-15-403 | unverified |
| NC | SOS Data Subscriptions | No | ? | Yes | CSV | $750 setup + $2,000/yr; scripted searching banned | unverified |
| ND | SOS FirstStop data lists | No | ? | ? | Excel | $40 per list; NDLogin required | unverified |
| NE | Nebraska.gov (Tyler) batches | No | ? | ? | CSV | $15 per 1,000 records; subscription. New system due end of 2026 | unverified |
| NH | QuickStart | No | – | – | none found | None found | unverified |
| NJ | DORES bulk access | No | No | ? | by request | Priced per request (500+ records) | unverified |
| NM | SOS Enterprise | No | – | Yes (search only) | none found | IPRA requests only | unverified |
| NV | SOS bulk data download service | No | ? | ? | download | Paid (vendor cites $125); account required | unverified |
| **NY** | data.ny.gov `n9v6-gdp6` (loaded) | **Yes** | Partial (chair/CEO) | Yes | Socrata, monthly | NY Open Data terms | verified |
| **NY all filings** | data.ny.gov `63wc-4exh`, `2tms-hftb`, `k4vb-judh`, and others | **Yes** | Filer/organizer names | Process address | Socrata, daily or weekly | No license tag; NY Open Data terms | verified (fields, counts) |
| OH | SOS monthly "business reports" | **Probably** | Incorporator/filer names | Yes | download, monthly (2nd Saturday) | Free; format and scope unverified; host blocks bots | unverified |
| OK | SOS bulk orders | No | ? | Yes | master plus weekly | Paid (vendor cites $500 master) | unverified |
| **OR** | data.oregon.gov `tckn-sxa6` (loaded) | **Yes** | Authorized reps only | Yes | Socrata | Public record; no license text | verified |
| **OR UCC** | data.oregon.gov `snfi-f79b`, `2kf7-i54h` | **Yes** | – | – | Socrata, monthly | Public Domain | verified |
| **PA** | data.pa.gov `xvd7-5r2c` | **Yes (likely)** | Yes per 3rd parties (party_type) | No (per 3rd parties) | Socrata, weekly | Public Domain per 3rd party | unverified (host blocked here) |
| RI | SOS weekly corporate export (new entities) | **Partial** | **Yes** | Yes | tab-delimited, weekly | Free; new filings only. Full database $250 one-time or $3,000/yr | unverified |
| SC | SOS bulk data | No | ? | Yes | subscription | $12,000/yr (2015–19 figure) | unverified |
| SD | SOS database downloads | No | ? | ? | monthly or weekly | $750/mo; $250/wk | unverified |
| TN | TNCaB database download wizard | No | ? | ? | download | Paid (vendor cites $1,000) | unverified |
| TX | SOS SOSDirect bulk order | No | ? | ? | JSON master plus daily | $1,350 master unload | unverified |
| TX (Comptroller) | data.texas.gov `9cir-efmm` (franchise taxpayers) | Yes (entity only) | No | No | Socrata | Texas open data | unverified |
| TX (Comptroller) | FTOFFDIR.zip (officers and directors) | Login | **Yes** | – | zip, monthly | Free(?) but needs a data-secure.comptroller.texas.gov account, so it is excluded | unverified |
| UT | Division of Corporations list builder | No | ? | ? | custom list | Paid | unverified |
| VA | SCC Clerk's Information System | No | Yes | Yes | weekly FTP | $1,000/mo license (page may be stale) | unverified |
| VT | SOS bizfilings "Bulk Database Download" | **Possibly** | ? | ? | CSV(?), weekly | Described as public; terms and price not confirmed | unverified |
| WA | SOS Corporations Data Extract | No (retired) | – | – | – | Extract discontinued (about 2024); CCFS search only | unverified |
| WI | DFI Commercial Bulk Data (CORP51) | No | No (master file excludes officers) | ? | txt | Paid; UCC $250/week | unverified |
| WV | SOS Bulk Data | No | Yes | Yes | monthly or daily | Paid monthly account; lists $25 + $0.05/record | unverified |
| WY | SOS business database download | No | Yes (parties) | Yes | monthly zip | Paid subscription | unverified |

**Count.** Free, complete bulk entity data from the state: CO, CT, DC, FL, IA, NY, OR, and very
likely PA. Partial or unconfirmed: OH (monthly reports), RI (weekly new entities only), VT
(weekly bulk download, unconfirmed), MS (search-tool export). The other 39 states sell bulk
data, require an account, or offer only one-record-at-a-time search.

**Free UCC bulk data: CO, CT and OR only (all verified).** Every other state found sells UCC
bulk data or offers none.

## Per-state notes (free or partial sources)

### District of Columbia: the biggest find (verified)
- **Source.** DLCP Corporations Division layers on the DC GIS MapServer
  `https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Business_Licensing_and_Grants_WebMercator/MapServer`.
  The same data is mirrored as opendata.dc.gov items (Beneficial Owners item
  `c0c5d27952c84a6ca745556d0691d606`, layer 2).
- **Layer 0, Corporate Registration.** 507,201 rows. Fields: `FILE_NUMBER, ENTITY_STATUS, MODELTYPE,
  BUSINESS_NAME`, business address (`BUSNIESS_ADDRESS_LINE1–4`, city, state, zip), `RA_NAME`,
  `RA_ADDRESS1–4/CITY/STATE/ZIPCODE`, `EFFECTIVE_DATE, FOREIGN_DATEOF_ORGANIZATION`, and report
  years. Status mix: about 120k active and in good standing, about 313k revoked, about 33k
  dissolved.
- **Layer 2, Beneficial Owners.** 494,530 rows: `NAME, ADDRESS, BUSINESSNAME, MODELTYPE, LOCALE,
  INITIALFILENUMBER, STATUS`. These are the person names behind entities from DC's own
  beneficial-ownership filing requirement, which is exactly the link this project needs.
- **Layer 1, Trade Name.**
- **Freshness and access.** `DCS_LAST_MOD_DTTM` max is about 2026-11-20, so updates are about
  daily. Paging is limited to `maxRecordCount` 2000.
- **License.** data.gov's harvest record lists CC BY 4.0. Confirm on opendata.dc.gov, which was
  not reachable from here.
- **PII.** The beneficial-owner table holds personal names and addresses. Handle it like other
  `pii_fields`.

### Florida: officers for every entity (unverified; official pages quoted in search)
- **Source.** Division of Corporations "Data Downloads", <https://dos.fl.gov/sunbiz/other-services/data-downloads/>:
  quarterly (`cordata0–9.zip`, `corevent.zip`) and daily files. There are also fictitious-name,
  partnership and federal-lien files.
- **Fields.** File structure page: name, status, type, filing date, principal and mailing
  addresses, RA name, type and address, and **up to 6 officers/managers** with title and
  address. Annual-report data covers the last 3 years. Format is fixed-width text, about 1 GB or
  more.
- **Access.** SFTP host `sftp.floridados.gov`. The username and password are published openly on
  the quarterly-data page, so this is not a private login. A browser "Data Access Portal" is
  also mentioned.
- **Terms.** "Free data downloads for informational purposes ... offered as is." No explicit
  commercial-use clause was found. Florida records are public under Ch. 119.
- **Coverage.** All entities on record. Quarterly: January, April, July, October. Daily on
  business days.
- **Caveats.** Annual reports and address changes are not "events", so they may be missing from
  the event files. SFTP on port 22 probably will not pass the HTTPS agent proxy. Confirm the
  browser download path before planning the load.

### Pennsylvania (unverified; data.pa.gov not reachable from here)
- **Source.** data.pa.gov `xvd7-5r2c`, "Registered Businesses in PA Current by County Department
  of State".
- **Fields.** Third-party sources (a public gist and vendors) say there is one row per officer
  with `party_type` (President, Treasurer, Governor, Partner) and Public Domain licensing. They
  also say there is no status field and no RA field. About 2.3M entities, weekly.
- **Conflict.** The official page description calls it counts by county. Check `columns.json`
  first.

### Iowa (partly verified)
- **Source.** Iowa Data Hub dataset 554, CSV at `https://idh-be.iowa.gov/api/v1/datasets/554/rows.csv`,
  with columns at `.../columns.json`. The legacy Socrata `ez5t-3qay` endpoints now return the new
  Next.js site rather than data.
- **License.** CC BY 4.0, active entities only. The catalog text says the RA name and address
  and the principal office are included, but a third-party README says the RA was removed.
- **Access.** The proxy blocks `idh-be.iowa.gov`, so the columns could not be checked.
- **Robots.** `data.iowa.gov` robots.txt allows `*` but blocks AI crawlers (`ClaudeBot`,
  `anthropic-ai`) and sets `ai-train=no`. Use a plain client User-Agent for data pulls and
  respect that line.

### New York: beyond the loaded active-corporations set (verified)
- `63wc-4exh` All Filings: 21.2M rows, every filing including dissolved entities.
- `2tms-hftb` All Filings – Address: 18.7M rows, with `addr_type` 1–4 plus a name per filed
  address.
- `3gg2-jgnp` entity status history, `dnbf-xifz` merger constituents, `kiwr-v7e8` stock.
- `k4vb-judh` Daily filings (last 30 days), with filer and SOP name and address.
- **Why it matters.** This adds inactive LLCs and the filer/organizer names, which often belong to
  the attorney or the principal. There is no license tag on these datasets; the NY Open Data
  terms apply.

### Connecticut (loaded; UCC verified)
- The registry has 5 datasets. A filing-history dataset `ah3s-bes7` also exists.
- **UCC `xfev-8smz`.** 851,348 rows with debtor name and address (individual or business),
  secured party name and address, lien status, lapse and accept dates. Public Domain. The UCC
  rows hold debtor names that can be joined to judgment debtors.

### Colorado UCC (verified)
- `wffy-3uut` filings: 2.6M rows.
- `8upq-58vz` debtors: 2.0M rows, person or organization name plus address.
- `4am6-w6u4` collateral: 1.7M rows.
- All three are Public Domain and updated daily. Join them on `fileid`.
- Also available: `qpft-q492` (entities with true name) and `casm-dbbj` (entity transaction
  history).

### Oregon UCC (verified)
- `snfi-f79b` new UCC filings from the last month (about 5.3k rows): party type, entity name,
  address, image link.
- `2kf7-i54h` all current secured parties.
- Public Domain, monthly.
- Note: the loaded entity set `tckn-sxa6` has only REGISTERED AGENT, AUTHORIZED REPRESENTATIVE,
  PRINCIPAL PLACE OF BUSINESS and MAILING ADDRESS rows. It has no members or managers.

### Ohio (unverified)
- **Source.** Free monthly "business reports" at `https://www.ohiosos.gov/businesses/business-reports/download-business-report/`,
  regenerated on the 2nd Saturday of each month.
- **Fields.** The new-entity report has document number, incorporation date, entity type,
  statutory agent address, filer and incorporator names. Ohio publishes no officer or member
  lists.
- **Unknowns.** Format and whether there is a full active-entity file are unverified. Gist notes
  say the host sits behind a bot wall; check robots and terms before pulling.

### Rhode Island (unverified)
- **Source.** Free weekly export of entities filed the previous week:
  `https://business.sos.ri.gov/corp/WeeklyCorpExport/WeeklyCorpExportList.asp`.
- **Fields.** Tab-delimited. The 2007 layout lists the agent and one officer (name, type,
  address).
- **Limits.** New filings only. The full database is paid.

### Vermont (unverified)
- A 2025 SOS legislative document says a full-dataset "bulk data download", updated weekly, is
  on bizfilings.vermont.gov (Online Services → Bulk Database Download).
- Entity types, fields, price and terms are all unconfirmed. Small state, low priority.

### Texas (no free bulk registry)
- SOS bulk data is paid (Master Unload about $1,350).
- The Comptroller's `9cir-efmm` on data.texas.gov is free, but holds entity-level fields only
  (name, mailing address, SOS file number, org type).
- The Comptroller's FTOFFDIR.zip has officers, directors and managers from Public Information
  Reports, refreshed monthly. It requires an account on `data-secure.comptroller.texas.gov`, so
  it is excluded under the no-login rule. It is worth asking the user about.

### Washington (no)
- The Corporations Data Extract (`apps.sos.wa.gov/corps/AllData.aspx`) was retired. The SOS FAQ
  and data.gov both say it is no longer available.

## Ranked load-first list

Ranked by officer or owner names first, then by how many properties are likely held by LLCs in
that state, then by how easy the load is.

| Rank | Source | Why | Hostnames needed |
|---|---|---|---|
| 1 | **FL Sunbiz quarterly + daily** | Largest LLC-property state with free data; up to 6 officers/managers plus RA for every entity | `dos.fl.gov`, `sftp.floridados.gov` (SFTP port 22, or the HTTPS data portal if one exists) |
| 2 | **DC Corporate Registration + Beneficial Owners** | Owner names for about 495k rows plus RA; ready to use now | `maps2.dcgis.dc.gov` (reachable now); optionally `opendata.dc.gov` for the license page |
| 3 | **PA data.pa.gov `xvd7-5r2c`** | Large state; officers per row (if confirmed) | `data.pa.gov` |
| 4 | **NY All Filings + Address + Daily** | Adds dissolved LLCs and filer/organizer names to the loaded active set | `data.ny.gov` (already allowed) |
| 5 | **CO, CT, OR UCC** | Free UCC debtor and secured-party names; CT and CO are large | `data.colorado.gov`, `data.ct.gov`, `data.oregon.gov` (all already allowed) |
| 6 | **OH monthly business reports** | Large state; RA plus incorporator names (format unverified) | `www.ohiosos.gov` |
| 7 | **IA Data Hub 554** | RA possibly; active entities | `idh-be.iowa.gov` (blocked now), `data.iowa.gov` |
| 8 | **RI weekly export** | Officer per new entity; small | `business.sos.ri.gov` |
| 9 | **VT bulk download** | Unconfirmed; small | `bizfilings.vermont.gov` |
| – | TX Comptroller FTOFFDIR | Officers for all TX franchise taxpayers, but needs an account | needs user approval for the login; `data-secure.comptroller.texas.gov` |

Biggest gaps, all paid, for a later budget decision: CA, TX (SOS), GA, NC, AZ, IL, MI, NJ.
Indicative prices: GA $1,000 one-time; NC $2,750 for the first year; TX $1,350; MN $710 (a $30
active-only CSV exists); ME $600/month.

## Sources

- Florida: [Data Downloads](https://dos.fl.gov/sunbiz/other-services/data-downloads/), [Quarterly Data](https://dos.fl.gov/sunbiz/other-services/data-downloads/quarterly-data), [Daily Data](https://dos.fl.gov/sunbiz/other-services/data-downloads/daily-data/), [Corporate Data File](https://dos.fl.gov/sunbiz/other-services/data-downloads/corporate-data-file/), [Data usage guide](https://dos.fl.gov/sunbiz/other-services/data-downloads/data-usage-guide/)
- DC: [Corporate Registration (data.gov)](https://catalog.data.gov/dataset/corporate-registration-6459e), [Beneficial Owners (data.gov)](https://catalog.data.gov/dataset/beneficial-owners), [DC GIS MapServer](https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Business_Licensing_and_Grants_WebMercator/MapServer) (queried)
- PA: [data.pa.gov xvd7-5r2c](https://data.pa.gov/Licenses-Certificates/Registered-Businesses-in-PA-Current-by-County-Depa/xvd7-5r2c), [state Socrata gist](https://gist.github.com/BhackerJ/22a35fead8764782189c7a20c5ded0d7) (third party)
- IA: [Active Iowa Business Entities (data.gov)](https://catalog.data.gov/dataset/active-iowa-business-entities)
- CT: [Bulk Data & Images](https://portal.ct.gov/sots/business-services/bulk-data-and-images), [Principals](https://catalog.data.gov/dataset/connecticut-business-registry-principals), [UCC Lien Filings](https://catalog.data.gov/dataset/uniform-commercial-code-ucc-lien-filings)
- OR UCC: [UCC filings last month](https://catalog.data.gov/dataset/ucc-list-of-filings-entered-last-month)
- OH: [Business reports](https://www.ohiosos.gov/businesses/business-reports/), [Download business report](https://www.ohiosos.gov/businesses/business-reports/download-business-report/)
- RI: [Weekly export](https://business.sos.ri.gov/corp/WeeklyCorpExport/WeeklyCorpExportList.asp), [file structure](https://business.sos.ri.gov/corp/WeeklyCorpExport/filestructure.htm), [Data subscription](https://sos.ri.gov/divisions/business-services/business-data-hub/data-subscription)
- VT: [SOS transparency testimony 2025](https://legislature.vermont.gov/Documents/2026/Workgroups/House%20Energy%20and%20Digital/Data/W~Lauren%20Hibbert~Transparency%20and%20Accessibility%20of%20SOS%20Data~4-29-2025.pdf), [MuckRock request](https://www.muckrock.com/foi/vermont-80/vermont-data-broker-db-107096/)
- TX: [SOS bulk order](https://www.sos.state.tx.us/corp/bulk-order.shtml), [Comptroller tax files](https://comptroller.texas.gov/data/openrec/requests/taxfiles.php), [Franchise tax permit holders](https://catalog.data.gov/dataset/active-franchise-tax-permit-holders)
- WA: [Data extract page](https://apps.sos.wa.gov/corps/AllData.aspx), [data.gov note](https://catalog.data.gov/dataset/corporations-search-from-secretary-of-state)
- Paid or none:
  - [KY](https://www.sos.ky.gov/bus/Pages/Bulk-Data-Service.aspx)
  - WV: [file descriptions](https://apps.wv.gov/SOS/BulkData/Forms/FileDescriptions.aspx), [request form](https://sos.wv.gov/sites/default/files/2026-04/BED_RequestForm.pdf)
  - [IN](https://inbiz.in.gov/Inbiz/BulkDataServices/Index)
  - [GA](https://georgia.gov/bulk-corporations-data)
  - NC: [data subscriptions](https://www.sosnc.gov/online_services/data_subscriptions), [fees](https://sosnc.gov/fees/by_title/_data_subscriptions)
  - [VA](https://appspre.scc.virginia.gov/clk/purch.aspx)
  - [WY](https://sos.wyo.gov:443/Forms/Business/General/WYSOS-BusinessDatabaseDownload.pdf)
  - [AR](https://portal.arkansas.gov/service/ar-corp-bulk-data-download/)
  - [OK](https://oklahoma.gov/sos/businesses/business-services/bulk-orders.html)
  - [MN](https://www.sos.mn.gov/business-liens/business-liens-data/business-data-available/)
  - [ME](https://www.maine.gov/sos/corporations-commissions/bulk-data)
  - [WI](https://dfi.wi.gov/Pages/BusinessServices/BusinessEntities/CorpDataServices.aspx)
  - [KS](https://sos.kansas.gov/forms/elections/RAR.pdf)
  - [LA](https://static.sos.la.gov/COAPI/Commercial_API_Guide.pdf)
  - [MD](https://dat.maryland.gov/pages/services.aspx)
  - [NE](https://sos.nebraska.gov/new-online-business-filing-system)
  - [SD](https://sdsos.gov/business-services/databasedownloads.aspx)
  - [ND](https://www.sos.nd.gov/services/data-list-requests)
  - [ID](https://sos.idaho.gov/business-services/)
  - [IL rules](https://ilga.gov/commission/jcar/admincode/014/014001800000140R.html)
  - [NJ rules](https://regulations.justia.com/states/new-jersey/title-17/chapter-34/subchapter-4/section-17-34-4-1/)
  - [SC fees](https://www.scstatehouse.gov/CommitteeInfo/HouseLegislativeOversightCommittee/AgencyWebpages/SecretaryofState/Fee%20revenue%20collected%20for%20business%20certificates%20of%20existence,%20copies,%20and%20bulk%20data%20(FY%202015-16%20-%20FY%202018-19).pdf)
  - [TN](https://sos.tn.gov/node/886)
  - [MT](https://sosmt.gov/business-services/)
  - [NV](https://nvsosuat.nv.gov/sos-information/public-records-requests)
  - [DE FOIA](https://www.muckrock.com/foi/delaware-236/uniform-commercial-code-filing-buyers-124842/)
  - [CA](https://www.sos.ca.gov/business-programs/business-entities/information-requests)
  - [AK](https://www.commerce.alaska.gov/web/cbpl/corporations)
  - [AL](https://www.sos.alabama.gov/business-entities)
  - [AZ](https://azcc.gov/public-records-request)
  - [MI](https://www.michigan.gov/lara/bureau-list/cscl/corps/other/total-business-entities-as-of-october-1-2026)
  - [MO](https://www.sos.mo.gov/business/corporations/about.asp)
  - [MS](https://corp.sos.ms.gov/corpreporting/Corp/BusinessSearch3)
  - [NH](https://sos.nh.gov/corporation-ucc-securities/corporation/faqs)
  - [NM](https://www.sos.nm.gov/legislation-and-lobbying/legal-resources/ipra-request-information/)
  - [UT](https://corporations.utah.gov/other-services)
  - [HI](https://catalog.data.gov/dataset/hawaii-business-registration)
  - [MA](https://www.mass.gov/info-details/appendix-divisions-of-the-secretary-of-the-commonwealth-of-massachusetts)
