# Free bulk recorded-judgment and civil-judgment files from county clerks: live check

Checked live on 2026-11-23, with unrestricted network, from the shell (curl and the repo's
PoliteClient). Tags: **LOADED** = adapter built and loaded into the lake; **REJECTED** =
checked and fails the brief (free, no login, no shared login, no CAPTCHA, no paywall, no
scraping of search portals, robots.txt obeyed). Already loaded before this round and not
re-checked: Hillsborough FL (OR + civil), NYC ACRIS, Philadelphia RTT, Harris County TX.
Already rejected: Broward, Miami-Dade, Palm Beach, Lee, Lake (FL); Franklin OH Common Pleas.

## Loaded

### Citrus County FL Clerk: Court Records Search - Bulk Data (`fl.citrus.civil`) [LOADED]
- Page: https://www.citrusclerk.org/186/Court-Records-Search-SCORSS. It says: "By accessing
  the link above, you may access bulk data at no charge ... You may request information for
  filings or dispositions during a selected period of time. The information is then exported
  to an Excel format."
- Export form: https://apps.citrusclerk.org/BulkDataExport/ (a Laravel Livewire page). No
  login, no CAPTCHA, no fee. `apps.citrusclerk.org/robots.txt` is 404 (no restrictions);
  citrusclerk.org's robots.txt blocks only admin/search pages. No other terms posted.
- Output: `export.zip` with `export_Case.csv` (UniformCaseNumber, CaseNumber, court type,
  case type, file date, disposition date, judge, status, disposition), `export_Party.csv`
  (plaintiff/defendant/attorney rows with name parts and **ActiveAddress**, a one-line
  mailing address; also Race/DOB/Gender/DLNo columns, almost always blank in civil cases:
  dropped at fetch and never stored) and `export_Docket.csv` (date + text).
- Judgments: docket entries such as "DEFAULT FINAL JUDGMENT E - RECORDED (OR.3725.1856. /
  2026069564)"; the clerk records each judgment in Official Records and the entry carries
  the OR book, page and instrument. No amounts in the export.
- Speed: a whole year of civil dispositions (~5,300 cases, 27k party rows, 150k docket rows)
  returns in ~20 s. Dispositions go back to at least 1990; docket entries to ~2002.
- Adapter: `src/equity/adapters/fl/citrus_civil.py`, config
  `config/courts_state/fl.citrus.civil.yaml`. Monthly partitions of disposition date,
  2006-01 to yesterday, court types CA, CAM, CC, SC.
- Parcel source covering the county: `fl.statewide.parcels` (Florida DOR statewide parcels).

### Hernando County FL Clerk: Official Records weekly index (`fl.hernando.or`) [LOADED]
- Page: https://hernandoclerk.com/clerk-data-subscriptions/ says "Files no longer require
  an account. Click on the button below to access the files." The button opens
  https://subscriber.hernandoclerk.com/, an open listing of weekly Official Records index
  CSVs (`/data_files/official_records/MM-DD-YYYY.csv`, 121 weeks from 2024-08-02), plus
  daily Civil Data, Case Data and traffic files.
- Terms: the subscription disclaimer disclaims liability, asks users to comply with state
  and federal law and reserves the right to cut access. No fee, no login, no CAPTCHA.
  `subscriber.hernandoclerk.com/robots.txt` is 404; hernandoclerk.com has Crawl-delay 10 and
  admin-only Disallow rules.
- Layout (on the listing page): Grantor, Grantee, ClerkFileNumber, Book, PageNumber,
  DocumentTypeDescription, LegalDescription, DateRecorded. No header, no addresses, no
  amounts; names cut at 25 characters. A week is ~1,300-2,100 instruments; the 2026-11-20
  week had 176 JUDGMENT and 19 CERT COPY CRT JDGMNT instruments (creditor = grantor).
- Descriptions with an X suffix (JUDGMENTX, ORDERX2, COURT PAPERX...) are family-law and
  child-support filings; they, marriage, death and probate records are not loaded.
- Adapter: `src/equity/adapters/fl/hernando_or.py`, config `config/recorders/fl.hernando.or.yaml`.
- Parcel source covering the county: `fl.statewide.parcels`.

### Hernando County FL Clerk: daily Civil Data Index (`fl.hernando.civil.filings`) [LOADED]
- Same open site: `/data_files/civil_data/YYYY-MM-DD.csv`, daily from 2024-01-01 (~919
  files with one back-file), pipe-delimited: case type code and description, case number,
  filing type, filed date, status, party type, party name, Address 1/2, city, state, zip,
  attorney. New filings (no judgments), but every party has a street address.
- DR (domestic relations) rows are dropped at fetch time; CA, CC and SC are kept.
- Adapter: `src/equity/adapters/fl/hernando_civil.py`, config
  `config/courts_state/fl.hernando.civil.yaml`.

### Putnam County FL: Open Data, Clerk Official Records Index (`fl.putnam.or`) [LOADED]
- Page: https://apps.putnam-fl.com/bocc/putsubs/main.php ("Putnam County, Florida Open
  Data - Available Downloads"). Clerk of Court files: `orimaster.zip` (History: October 1983
  to the end of last year; one 258 MB text file, 46 MB zipped), `oriyear.zip` (current year
  to last Sunday), `oriweekly.zip` (last 4 weeks, updated Wednesdays). Layout:
  `subscriptions/coc/orihelp.txt`. No login, no CAPTCHA, no fee, no terms posted;
  `apps.putnam-fl.com/robots.txt` is 404.
- Fields: book | page | file date | from party | to party | instrument | transaction code |
  description. Same codes as Hillsborough (JUD, CCJ, LN, SAT, LP, MTG, D...). The
  description of a judgment or lien starts with its **amount** ("$1,622.55 ET AL"), loaded
  as principal_amount. ~80-100k party rows a year; 2026 year-to-date has 1,004 JUD+CCJ
  instruments.
- Not loaded: JUD rows whose description is a family-court case number (FD/DR/DP), CJD/CS
  (criminal judgments and cost liens), marriage, death, military discharge and fee codes.
- Adapter: `src/equity/adapters/fl/putnam_or.py`, config `config/recorders/fl.putnam.or.yaml`.
  Partitions: history file by year from 2006, then the current-year file.
- Parcel source covering the county: `fl.statewide.parcels`. (The same page also offers
  the Putnam Property Appraiser's certified data packages.)

## Florida clerks checked and rejected

| County | What was found (live) | Why rejected |
|---|---|---|
| Orange (occompt.com, Comptroller/recorder) | Homepage and every path return 403 from Cloudflare | Bot wall; nothing reachable |
| Orange (myorangeclerk.com, courts) | Site up; no bulk or data-download page in its links or sitemap | No bulk file found |
| Duval | Official Records pages offer copy request forms; bulk is a "complex records request" under its cost-recovery policy | Request/fee, not a file |
| Pinellas (mypinellasclerk.gov) | 403 on homepage (Cloudflare) | Bot wall |
| Polk | No bulk or download page on site or sitemap | Not found |
| Brevard | "Download Court Related & Miscellaneous Reports" goes to an SAP BusinessObjects login with a published shared user name (instructions PDF; 10 concurrent licences) | Shared login |
| Volusia (clerk.org) | Official Records search and forms only | Not found |
| Pasco | "Subscription Download Data": Official Records daily/weekly index, sales data, weekly evictions (XLS/TXT) | Every link redirects to a subscriber login |
| Seminole | Official Records search (DuProcess) only | Not found |
| Sarasota | 403 (Akamai "Access Denied") | Bot wall |
| Manatee | "Subscribers" link to electronic access | Subscription |
| Collier | Report Portal (cms.collierclerk.com): public SSRS reports "Monthly Civil Cases Filed", "Foreclosure Sales By Year"; robots.txt disallows ClaudeBot/anthropic-ai and AI crawlers | Report viewer (scraping), filings not judgments |
| Marion | Reports page is financial only; "searchable database" link | Not found |
| Leon | cvweb.leonclerk.com 403 (Akamai); main site has no bulk page | Bot wall / not found |
| Escambia | 403 on homepage | Bot wall |
| St. Lucie | 403; earlier search: $220/yr data subscriptions | Bot wall / paid |
| Osceola | Public PDFs: scheduled mortgage-foreclosure sales (6 months), refreshed daily | PDF list of sales, not judgments; not built |
| Lake | Subscription services (OR FTP $75 + $900/yr; court data files by subscription) | Paid (already rejected) |
| St. Johns, Alachua, Okaloosa | Landmark/Benchmark search portals only | Not found |
| Hernando | Free open file site | **Loaded** (OR); civil filings qualify, not built |
| Citrus | Free bulk export | **Loaded** |
| Bay, Bradford, Calhoun, Charlotte, Clay, Columbia, DeSoto, Dixie, Franklin, Gadsden, Gilchrist, Glades, Gulf, Hamilton, Hardee, Hendry, Highlands, Holmes, Indian River, Jackson, Jefferson, Lafayette, Levy, Liberty, Madison, Martin, Monroe, Nassau, Santa Rosa, Sumter, Taylor, Wakulla, Walton, Washington | Homepages fetched and scanned for bulk/data/FTP/subscription/export links: none (Santa Rosa: property-fraud notification sign-up only) | Not found (homepage scan only; deeper pages not crawled) |
| Baker, Flagler, Union | 403 on homepage | Bot wall |
| Putnam | County Open Data page with the Clerk's full ORI history | **Loaded** |
| Okeechobee, Suwannee | Guessed hostnames did not resolve / redirect | Not checked further |

## Texas

| County | Found | Verdict |
|---|---|---|
| Dallas | County Clerk pages moved (404); the DCHHS eviction dashboard page now 404; JP pages are filing instructions | Not found |
| Bexar | bexar.org behind a Cloudflare JavaScript challenge | Bot wall |
| Travis | County Clerk site has no bulk page; "Civil Courts Data" on courtsdata.traviscountytx.gov is a Qlik dashboard (district civil statistics) | Dashboard, not a file |
| Tarrant | County Clerk "Bulk Data Payments" (ncourt.com) | Paid |
| Collin, Denton, El Paso, Hidalgo, Williamson (403) | No bulk/data pages linked; open-records request links | Not found |
| Fort Bend | District Clerk "bulk data sales" (from earlier research) | Paid |
| Statewide | data.texas.gov has only OCA landlord/tenant caseload counts and TCEQ judgments (already loaded) | Counts only |

## Ohio

| County | Found | Verdict |
|---|---|---|
| Cuyahoga | Clerk of Courts site is a docket search; coc.cuyahogacounty.gov does not resolve | Not found |
| Hamilton (courtclerk.org) | Certified judgments/liens search by case and by debtor name; robots.txt: "Disallow: /data/" (all data endpoints) | Search portal; robots |
| Montgomery (mcclerkofcourts.org) | Monthly "Mortgage / Tax Foreclosures" PDF reports (case, caption, filing docket, property address) | Foreclosure filings in PDF, not judgments; not built |
| Summit | clerk.summitoh.net is a JavaScript app; no file links | Not found |
| Lucas, Stark, Lorain | Guessed clerk hostnames did not resolve; Stark county site has treasurer delinquent-tax pages only | Not found |
| Butler | 403 | Bot wall |
| Franklin Municipal Court (fcmcclerk.com) | Monthly F.E.D. (eviction) CSVs with first plaintiff/defendant and addresses, under /storage/shared/civil-fed/ | robots.txt "Disallow: /storage/shared/*" |

## Other states

| Source | Found | Verdict |
|---|---|---|
| Fulton County GA (sharefulton Socrata) | Superior Court current pending cases (caption, case type, judge), daily | Pending cases, no judgments or addresses |
| Maryland District Court eviction data (opendata.maryland.gov `mvqb-b4hf`) | Events, tenant city/zip, case number | No names |
| Allegheny County PA tax liens (WPRDC) | Already loaded as `pa.allegheny.tax_liens` | Skip |
| Socrata catalog (api.us.socrata.com) for "abstract of judgment", "lis pendens", "judgments", "civil cases", "county clerk recordings" | Only known sets (TCEQ, NYC, NOLA, Cook) | Nothing new |
| Georgia GSCCCA lien index | Subscription (earlier research) | Paid |

## Takeaways
- Free bulk exists where a small clerk chose to publish it: Citrus (a deliberate "bulk data at
  no charge" export), Hernando (subscriber files opened up) and Putnam (county open-data page
  with the whole OR index since 1983, judgment amounts included). Large clerks either sell
  (Pasco, Lake, Miami-Dade, Palm Beach, Tarrant) or sit behind Cloudflare/Akamai (Orange
  Comptroller, Pinellas, Sarasota, Escambia, St. Lucie, Bexar).
- Hernando's civil filings tie to its OR judgments by name, not case number (the OR index
  carries no case number). Citrus docket judgments carry the OR book/page/instrument, but
  Citrus OR itself is not published in bulk.
- Small-clerk subscription pages are worth one more sweep: Hernando's and Putnam's were found
  only by reading their "subscriber"/"open data" pages, not from homepage links.
