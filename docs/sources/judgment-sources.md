# Free bulk civil-judgment sources, all 50 states and DC

Researched 2026-11-21. These are sources of civil-case and judgment data that can be pulled
in bulk for free, with no scraping of search portals, no logins and no paywalls. PACER is
the only paid source allowed and is covered elsewhere (`judgments-liens.md`). These sources
are already loaded and are not repeated here: Hillsborough FL (civil cases, filings,
garnishment, Official Records index), NYC ACRIS, and federal courts through
PACER/CourtListener.

## How each claim was checked

| Tag | Meaning |
|---|---|
| **[LIVE]** | This session pulled the dataset's metadata and row counts from its API. The host is reachable from the session container. |
| **[SEARCH]** | Confirmed only from web-search snippets of the official page. The page was not fetched. |
| **[UNVERIFIED]** | From background knowledge, or the search did not settle it. Confirm before building. |

Several hosts refused connections from this container (proxy 403 or DNS failure):
`jpwebsite.harriscountytx.gov`, `jp.hctx.net`, `www.hcdistrictclerk.com`, `fcmcclerk.com`,
`www.broward.org`, `www.browardclerk.org`, `www.lakecountyclerkfl.gov`,
`www.miamidade.gov`, `www2.miamidadeclerk.gov`, `api.us.socrata.com` and
`catalog.data.gov`. Anything on those hosts is at best [SEARCH].

## Main finding

No state publishes a free, statewide bulk file of civil court judgments. State court
systems either sell bulk data (MD, NJ, NC, WI, PA, AZ, MN, UT), require an application
under a data-dissemination rule (IN, WA, HI, AK, IL-Cook, KY), or forbid bulk download
outright (NM). County recorders that sell daily index files nearly always charge
(Miami-Dade, Lake FL, Palm Beach, Maricopa, Cook, Harris County Clerk, Tarrant).

The free bulk sources that do exist are:

1. **New York**, the richest state:
   - State tax and child-support warrants. These are filed with the Department of State and have had statewide lien effect since 2025-07-01.
   - NYC OATH/ECB docketed judgments with BBL.
   - NYC marshal evictions and HPD housing litigation.
2. **Pennsylvania (Allegheny County)** via WPRDC: 3.25M tax-lien docket records and 40.7k mortgage-foreclosure filings, both keyed to the parcel PIN, under a CC0 license.
3. **Connecticut** Secretary of the State lien filings. These include judgment liens on personal property and 222k municipal liens. The data is nightly and free.
4. **Texas (Harris County)** JP Public Data Extract: civil case extracts from all 16 justice courts, covering debt claims, evictions and small claims. Free status is [SEARCH/UNVERIFIED], and the host is blocked here.
5. **Florida (Broward)** Official Records FTP index. Free status is [UNVERIFIED], and the host is blocked here.
6. **Ohio (Franklin County Municipal Court)** eviction CSVs, built nightly. Evictions only.

### State-level judgment-lien filing systems (recorder side, part b)

| State | Statewide filing office | Free bulk? |
|---|---|---|
| **CT** | Secretary of the State: judgment lien certificate on personal property (CGS 52-355a) | **Yes [LIVE].** data.ct.gov `xfev-8smz`: 381 `JUDGMENT LIEN` filings, 453 `JUDGMENT - PERS` and 83 `JUDGMENT` descriptions. |
| **NY** | Department of State: state tax warrants and child-support warrants (Tax Law §6, from 2025-07-01). DTF says a warrant is equivalent to a civil judgment. | **Yes [LIVE].** data.ny.gov `v7ua-z23v` and `8pp4-isha`. |
| **CA** | Secretary of State: Notice of Judgment Lien JL1, personal property (CCP 697.510) | No. Search, certificates and paid bulk orders only [SEARCH; price UNVERIFIED]. |
| **FL** | Department of State Judgment Lien File, personal property (ss. 55.201–55.209) | No. Online search only. The Sunbiz daily and quarterly downloads carry federal liens, not judgment liens. Sunbiz SFTP uses published credentials, which counts as a login under the brief [SEARCH]. |
| **ME** | Secretary of State: judgment lien on personal property by financing-statement-style filing (14 MRSA §4651-A) | Not found free [UNVERIFIED]. |
| **GA** | GSCCCA statewide lien index (court judgment liens, fi.fas, lis pendens) run by the clerks, not the SOS | No. Online by subscription; free only at clerk terminals [SEARCH]. |
| **MN** | SOS central system holds tax liens, not judgment liens | Paid bulk, tax liens only [SEARCH]. |
| **CO, OR** | The SOS UCC systems hold IRS, hospital and statutory liens, not judgment liens | Free open data [LIVE], but no judgments in it. |

Every other state attaches judgments to real property by docketing or recording at the
county level: the clerk of court's judgment docket, or the recorder's abstract or
transcript of judgment. No free statewide index of those was found.

## Summary table

Verdict key:
- **FREE-BULK**: usable now.
- **PARTIAL**: free, but only part of the picture (one county, one case type, or liens close to judgments).
- **CANDIDATE**: probably free; confirm terms or reach the host first.
- **NONE**: nothing free in bulk.

| State | Best free bulk source | Coverage | Verdict |
|---|---|---|---|
| AL | None (Alacourt is a paid subscription; judgments recorded with probate) | — | NONE |
| AK | None (CourtView search; bulk at the administrative director's discretion, Admin R. 37.8) | — | NONE |
| AZ | None free. Maricopa Justice Courts monthly bulk is $33/month plus a dissemination agreement and insurance; Recorder bulk is $250/day | — | NONE (paid) |
| AR | None (search only) [UNVERIFIED] | — | NONE |
| CA | None. SOS JL1 judgment liens: paid bulk orders. Recorder abstracts: no open data found | — | NONE |
| CO | data.colorado.gov UCC filing data: IRS, hospital and statutory liens, no judgments | Statewide | PARTIAL (adjacent liens) |
| CT | data.ct.gov `xfev-8smz`: SOTS lien filings, including judgment liens on personal property and municipal liens | Statewide | FREE-BULK (small judgment slice) |
| DE | None [UNVERIFIED] | — | NONE |
| DC | None (Recorder of Deeds search runs on a vendor site; Superior Court search only) | — | NONE |
| FL | Broward Official Records FTP index [UNVERIFIED free] (Hillsborough already loaded) | Broward | CANDIDATE |
| GA | None (GSCCCA lien index is a subscription) | — | NONE |
| HI | None (bulk at the administrative director's discretion, Rule 10.17) | — | NONE |
| ID | None [UNVERIFIED] | — | NONE |
| IL | None. Cook County Clerk transfer data costs $400/year; Circuit Court bulk needs the Chief Judge's approval | — | NONE |
| IN | None free. Bulk by application under Admin. Rule 9 / Access Rule 5; fees possible; no redistribution | — | NONE (application) |
| IA | None (Iowa Courts Online search) [UNVERIFIED] | — | NONE |
| KS | None [UNVERIFIED] | — | NONE |
| KY | None. Supreme Court Order 2026-30 calls commercial use inconsistent with the courts' public mission | — | NONE |
| LA | None for judgments (NOLA open data has code-enforcement hearings) | — | NONE |
| ME | None verified (SOS personal-property judgment liens exist) | — | NONE |
| MD | None free. District Court civil-judgment bulk costs $2,775 up front plus $500 per update | — | NONE (paid) |
| MA | None. Trial Court publishes only aggregate eviction reports (PDF and Tableau) | — | NONE |
| MI | None [UNVERIFIED] | — | NONE |
| MN | None. Court bulk extracts and SOS lien bulk are both paid | — | NONE (paid) |
| MS | None [UNVERIFIED] | — | NONE |
| MO | None (Case.net search) | — | NONE |
| MT | None [UNVERIFIED] | — | NONE |
| NE | None [UNVERIFIED] | — | NONE |
| NV | None [UNVERIFIED] | — | NONE |
| NH | None [UNVERIFIED] | — | NONE |
| NJ | None free. Civil Judgment and Order Docket bulk reports are sold | — | NONE (paid) |
| NM | None. Bulk download is prohibited by Supreme Court Orders 10-8500 and 13-8500 | — | NONE |
| NY | data.ny.gov tax and child-support warrants; data.cityofnewyork.us OATH docketed judgments, Evictions, HPD Housing Litigations (ACRIS already loaded) | Statewide (warrants), NYC | **FREE-BULK** |
| NC | None free. NCAOC extracts are paid and need a $5,000 bond | — | NONE (paid) |
| ND | None [UNVERIFIED] | — | NONE |
| OH | Franklin County Municipal Court eviction CSVs (nightly) | Franklin County Municipal Court | PARTIAL (evictions) |
| OK | None (OSCN is case-by-case; 2009 directive restricts bulk) | — | NONE |
| OR | data.oregon.gov monthly UCC list: IRS liens only | Statewide | PARTIAL (adjacent liens) |
| PA | data.wprdc.org Allegheny tax liens and mortgage foreclosures (Philadelphia RTT already loaded) | Allegheny County | FREE-BULK (lien and foreclosure dockets) |
| RI | None [UNVERIFIED] | — | NONE |
| SC | None (county public indexes are search only) [UNVERIFIED] | — | NONE |
| SD | None [UNVERIFIED] | — | NONE |
| TN | None (Shelby Register is search only) | — | NONE |
| TX | Harris County JP Public Data Extract (civil and eviction) | Harris County justice courts | CANDIDATE |
| UT | None. Xchange is a subscription; bulk fee is set by the State Court Administrator | — | NONE (paid) |
| VT | None [UNVERIFIED] | — | NONE |
| VA | None (OES publishes aggregate caseload statistics; GDC search only) | — | NONE |
| WA | None. AOC data dissemination charges fees; JIS-Link is paid; King County Recorder is search only | — | NONE |
| WV | None (see `wv-state-federal.md`) | — | NONE |
| WI | None. WCCA REST interface is a paid subscription | — | NONE (paid) |
| WY | None [UNVERIFIED] | — | NONE |

## Per-state notes

Each free source lists:
- **Source:** name and URL
- **Contents:** what the records hold
- **Coverage:** where they apply
- **Format and frequency:** file format and how often it updates
- **Terms:** license or terms of use
- **Bulk and free:** whether it really is both

### New York (best state)

1. **NYS Tax Warrants: Beginning 7/1/2025** [LIVE]
   - **Source:** https://data.ny.gov/d/v7ua-z23v, API `https://data.ny.gov/resource/v7ua-z23v.json`
   - **Contents:**
     - Warrants filed by DTF with the Department of State, with their satisfactions, vacates and amendments.
     - Fields: `warrant_id`, `status_code`, `debtor_name_1-4`, debtor address and ZIP, `county_code`, `warrant_filed_amount`, `warrant_filed_date`, satisfaction, vacate, amend and expiration dates, and `url`.
     - 797,150 rows. Rows were last updated 2026-11-18.
   - **Coverage:** statewide.
   - **Legal effect:**
     - Since 2025-07-01 the DOS filing is the lien docket.
     - It reaches real property in every county.
     - Filings made at the county after that date are informational only.
     - DTF calls a warrant "equivalent to a civil judgment".
     - Sources: [DOS notices](https://dos.ny.gov/state-tax-warrant-notices), [Stewart bulletin](https://www.stewart.com/insights/new-york-state-tax-warrant-filing-changes), [DTF](https://www.tax.ny.gov/enforcement/collections/tax-warrants.htm).
     - Warrants filed before 2025-07-01 stay in the county records and are not in this dataset.
   - **Format and frequency:** Socrata (CSV, JSON, SODA). Updated daily or weekly.
   - **Terms:** no license is set in the metadata. Standard NY Open Data terms apply [UNVERIFIED].
   - **Bulk and free:** yes.
   - TODO(Brandon): whether a tax warrant counts as a "judgment" for the business is a legal call.
2. **NYS Child Support Warrants: Beginning 7/1/2025** [LIVE]
   - **Source:** https://data.ny.gov/d/8pp4-isha
   - **Contents:** the same structure as the tax warrants (debtor, address, amount, filed and satisfied dates). 108,541 rows, updated daily.
   - **Bulk and free:** yes.
   - Probably not a purchasable asset, but useful as a lien on the debtor.
3. **NYC OATH Hearings Division Case Status** [LIVE]
   - **Source:** https://data.cityofnewyork.us/d/jz4z-kudi
   - **Contents:**
     - ECB and OATH administrative judgments.
     - Fields: `date_judgment_docketed`, `penalty_imposed`, `paid_amount`, `balance_due`, `compliance_status`, `hearing_result`, the issuing agency, `respondent_last_name`, and the violation borough, block and lot (BBL).
     - 22.26M rows; 3,730,622 have a docketed-judgment date.
     - Since 2026-05-04 the respondent's first name and street address have been removed. Only the last name and the respondent's ZIP and borough remain.
   - **Coverage:** NYC.
   - **Format and frequency:** Socrata, updated daily.
   - **Bulk and free:** yes.
   - **Value:** docketed ECB judgments are city-held money judgments tied to a BBL, which joins straight to the parcel graph.
4. **NYC Evictions (City Marshals)** [LIVE]
   - **Source:** https://data.cityofnewyork.us/d/6z8x-wfk4
   - **Contents:** `court_index_number`, `docket_number`, `executed_date`, address, BBL and BIN. 137,618 executed evictions since 2017.
   - **Format and frequency:** daily.
   - **Bulk and free:** yes.
   - **Value:** evidence of a judgment of possession, keyed to the court index number.
5. **HPD Housing Litigations** [LIVE]
   - **Source:** https://data.cityofnewyork.us/d/59kj-x8nc
   - **Contents:** HPD housing-court cases. Fields: `casejudgement`, `penalty`, `respondent`, BBL. 242,293 rows. Updated monthly.
   - **Bulk and free:** yes.
6. **NYC Law Department, Case-Related Information About Civil Litigation** [LIVE]
   - **Source:** https://data.cityofnewyork.us/d/pjgc-h7uv
   - **Contents:** `docket_index`, `court_name`, `disposition`, `total_disposition_amt`, `total_city_received_amt`, `lead_bbl`. 547,358 rows.
   - **Value:** small for judgment buying. It covers only litigation the city is a party to.
7. **Tax Lien Sale Lists** (`9rz4-mjek`) [LIVE] are already relevant to ACRIS TLS documents.
8. **Not free:**
   - NY OCA housing-court data has no names (already noted).
   - County Clerk judgment dockets are search only. Some counties use paid vendors.

### Connecticut

- **Source:** data.ct.gov, "Uniform Commercial Code (UCC) Lien Filings", https://data.ct.gov/d/xfev-8smz [LIVE]
- **Contents:**
  - Liens filed with the Secretary of the State.
  - By description:
    - UCC financing statements (506k)
    - **municipal liens (221,969)**
    - IRS (81,563)
    - CT Department of Labor (21,909)
    - Department of Revenue Services (5,207)
    - **"JUDGMENT - PERS" (453) and "JUDGMENT" (83)**
    - attachments (907)
  - Fields: filing number, status, filing type, debtor name and address, secured party (the judgment creditor), `dt_accept`, `dt_lapse`.
  - No amount and no court docket number.
- **Coverage:** statewide, but only active liens, plus those within one year after lapse or release. There is no deep history.
- **Format and frequency:** Socrata. Nightly per the state; rows were updated 2026-11-21.
- **Terms:** free, per CT's fee page ("access online > $0") [SEARCH]. Images cost $1,000 a year.
- **Bulk and free:** yes.
- **Limits:**
  - The judgment-lien slice is tiny.
  - Real-property judgment liens are recorded in the 169 town clerks' land records. No free bulk was found for those.
- **Court side:** CT Judicial has no bulk civil data found. data.ct.gov carries only aggregate evictions by tract (`j5dt-tcp7`) and monthly foreclosures (`jfkq-xawu`, stale since 2022).

### Pennsylvania

1. **Allegheny County Tax Liens (Filings, Satisfactions, and Current Status)** [LIVE]
   - **Source:** https://data.wprdc.org/dataset/allegheny-county-tax-liens-filed-and-satisfied
   - **Contents:**
     - County, municipal, school-district and water/sewer tax liens docketed in the Department of Court Records since 1995.
     - Raw records: 3,251,891 rows with `pin`, `block_lot`, `filing_date`, `tax_year`, `dtd` (the Delinquent Tax Docket number), `lien_description`, `municipality`, `amount`, `assignee` and `last_docket_entry`.
     - There are also a satisfactions table and a current-status summary.
   - **Coverage:** Allegheny County. Not every municipality files.
   - **Format and frequency:** CKAN datastore (CSV and API). Monthly per the notes; metadata was modified 2026-11-07.
   - **Terms:** CC0.
   - **Bulk and free:** yes.
   - **Value:** these are liens on the judgment docket keyed to the parcel PIN. They are not private money judgments.
2. **Allegheny County Mortgage Foreclosure Records** [LIVE]
   - **Source:** https://data.wprdc.org/dataset/allegheny-county-mortgage-foreclosure-records
   - **Contents:** `pin`, `filing_date`, `case_id`, `docket_type`, `amount`, `plaintiff`, `last_activity`. 40,743 rows.
   - **Terms:** CC0.
   - **Bulk and free:** yes.
3. **Not free:**
   - AOPC statewide bulk is paid, at hourly or per-file fees.
   - Philadelphia FJD is paid ($85/hour plus $300 per report; $25k for historical data, per a 2012 schedule).
   - Sources: [PA courts](https://www.pacourts.us/page/1624), [FJD fee schedule](https://www.courts.phila.gov/pdf/accesspolicy/FJD-Public-Access-Policy-with-Exhibits-and-Fee-Schedule.pdf) [SEARCH].
   - Philadelphia judgments are with the Prothonotary, not in the loaded RTT data.

### Texas

1. **Harris County JP Public Data Extract Service** [SEARCH; free UNVERIFIED]
   - **Source:** https://jpwebsite.harriscountytx.gov/PublicExtracts/search.jsp
   - **Contents:** civil extracts from all 16 justice courts. You pick the extract type: all case types or one type, such as evictions. Debt claims and small claims are JP case types.
   - **Format:** a single day or a date range, delivered as tab-delimited text, CSV or XML. A published file-layout spec exists, and the site warns that the layouts have changed.
   - **Access:** no login or price appeared in any snippet. Researchers (January Advisors, Rice/Kinder) built 20-year eviction datasets from this court data.
   - **Host:** blocked here (DNS). Add it to the allowlist, then read the spec and terms before building.
   - **Value:** possibly the best free court-side source outside NY, if judgment fields (judgment date, amount, parties) are in the layout.
2. **Harris County District Clerk "Public Datasets"** [SEARCH]
   - The clerk asks commercial scrapers to use its Public Datasets instead.
   - Its search site requires a free registered login. It is unclear whether the datasets do. If they need a login, they are excluded under the brief.
   - **Host:** blocked here. URL [UNVERIFIED]: https://www.hcdistrictclerk.com/Common/e-services/PublicDatasets.aspx
3. **Not free:**
   - Harris County Clerk real-property data is sold (datasales@cco.hctx.net).
   - Tarrant County Clerk bulk data is paid.
   - Fort Bend District Clerk bulk is paid and criminal only.
   - The Travis County civil dashboard (https://courtsdata.traviscountytx.gov/CivilAnalytics) is aggregate.
   - OCA publishes only aggregate statistics.
   - Abstracts of judgment are recorded in county real-property records. No free bulk was found.

### Florida

- **Hillsborough** is already loaded.
- **Broward Records, Taxes & Treasury Official Records FTP** [SEARCH; free UNVERIFIED]
  - **Source:** https://www.broward.org/RecordsTaxesTreasury/Records/Pages/IndexFiles-Completed.aspx
  - **Contents:** daily text-file index and images. Each file stays up 7 to 10 days. The index runs from 1978 to the present.
  - Recorded judgments are in Official Records (s. 28.222). An amount is unlikely.
  - Images are free to view on the web. Whether the FTP index is free is not stated in the snippets.
  - This is separate from the Broward Clerk's paid daily court extracts.
  - **Host:** blocked here.
- **Palm Beach Electronic Distribution Index Service**
  - A daily OR index file by FTP, kept at least 45 days. It is subscription-only, by application, with the price not shown [SEARCH].
  - Index CD-ROMs cost $40 per year.
  - Treat it as paid until confirmed.
- **Paid:**
  - Miami-Dade Clerk: $80, then $110 per folder per month, with notarized registration.
  - Lake: setup fee plus an annual subscription.
  - Pinellas and Lee.
- **Department of State Judgment Lien File:** search only, as covered above.
- **Sunbiz:** federal liens through SFTP with published credentials, which the brief excludes.

### Ohio

- **Franklin County Municipal Court eviction reports** [SEARCH]
  - **Source:** https://fcmcclerk.com/reports/evictions
  - **Contents:** CSV files built nightly for forcible entry and detainer cases filed in the current month and each of the previous 12 months.
  - Judgment fields are [UNVERIFIED]. Evictions only.
  - **Host:** blocked here.
- **Franklin Common Pleas, Cuyahoga and Hamilton:** their portals say they are not for bulk download. Data files go through public-records requests.
- Ohio judgment liens are certificates of judgment filed with each county's Common Pleas clerk. No free bulk was found.

### Colorado and Oregon (adjacent lien data, no judgments)

- **Colorado** [LIVE]
  - **Source:** data.colorado.gov `wffy-3uut` (filings), `8upq-58vz` (debtors), `ap62-sav4` (secured parties)
  - **Contents:** IRS liens (184k), hospital liens (61k), other statutory liens (31k), agistor's and harvester's liens.
  - **Terms:** public domain, daily.
  - No judgment liens. Colorado real-property judgment liens are recorded with the county recorders.
- **Oregon** [LIVE]
  - **Source:** data.oregon.gov `snfi-f79b`
  - **Contents:** filings entered last month only, about 5.3k: UCC, IRS and EFS.
  - **Terms:** public domain.
  - No judgments.

### Paid or application-only states (the reason given)

| State | Reason |
|---|---|
| **MD** | District Court civil-judgment bulk: $2,775 for 12 years of history plus $500 per update; weekly updates cover judgments and satisfactions. [DCA-107](https://mdcourts.gov/sites/default/files/court-forms/district/forms/acct/dca107.pdf/dca107.pdf) [SEARCH] |
| **NJ** | Civil Judgment and Order Docket (statewide liens, 1984 to present) is sold as bulk reports; the subscriber portal is screen-only with no download. [Record layout](https://www.njcourts.gov/sites/default/files/attorneys/ecourts/judgment-report-descriptions-record-layout.pdf) [SEARCH] |
| **NC** | NCAOC extracts: civil tax liens $2,355 historical or $365/month, evictions $2,839, $495 setup, $5,000 bond. Judgments are available only through paid online access. [RPA extracts](https://www.nccourts.gov/services/rpa-extract-access) [SEARCH] |
| **WI** | The WCCA REST interface is an annual paid subscription (a 2010 figure was $5,000/year). [WCCA REST](https://wcca.wicourts.gov/rest-help.html) [SEARCH] |
| **AZ** | Rule 123 bulk needs a dissemination contract. Maricopa Justice Courts: $33 per monthly file plus insurance. Pima Justice Court: $3,000/year. Maricopa Recorder: previous-day bulk at $250/day. [SEARCH] |
| **MN** | Court bulk extracts follow a fee schedule. SOS lien bulk is paid and holds tax liens only. [SEARCH] |
| **UT** | Xchange is a subscription; bulk data carries a fee set by the State Court Administrator. Free remote access by statute starts 2027-01-01, but it is a portal, not bulk. [SEARCH] |
| **IN** | Bulk by application to the Office of Court Services under Admin. Rule 9(F) / Access Rule 5. Fees possible, no redistribution, MyCase scraping barred. [IN bulk data](https://www.in.gov/courts/iocs/statistics/bulk-data/) [SEARCH] |
| **WA** | The AOC Data Dissemination Policy sets fees and bars commercial solicitation; JIS-Link is paid. [SEARCH] |
| **NM** | Bulk download is prohibited by Supreme Court order. [SEARCH] |
| **KY** | Order 2026-30 disfavors commercial use; no bulk program was found. [SEARCH] |
| **IL** | Cook Circuit Court bulk needs approval under GAO 02-03. The County Clerk's transfer data license costs $400/year. Cook open data has only criminal data plus Recorder foreclosure and mortgage archives for 2011–2015. [SEARCH/LIVE] |
| **GA** | GSCCCA lien index is a subscription; UCC bulk costs $200/day. [SEARCH] |
| **CA** | SOS JL1 judgment liens and UCC bulk orders are paid [SEARCH; price UNVERIFIED]. Superior Courts have no bulk; recorders sell bulk index data. [UNVERIFIED] |
| **VA** | OES publishes only aggregate caseload statistics; GDC Online Case Information is search only. [SEARCH] |
| **OK** | OSCN is case-by-case; the 2009 directive restricts bulk distribution. [SEARCH] |
| **MA** | Trial Court publishes monthly aggregate summary-process (eviction) PDFs and Tableau; no case-level data. [SEARCH] |
| **AK, HI** | Bulk is at the administrative director's discretion (AK Admin R. 37.8, HI Rule 10.17); nothing published. [SEARCH] |
| **DC** | Recorder of Deeds search runs on a vendor site (washington.dc.publicsearch.us); no bulk. [SEARCH] |
| **TN** | Shelby Register is search only. [SEARCH] |
| **MO** | Case.net search only. [SEARCH] |

**No free bulk source was found, and none was verified this session, for:** AL, AR, DE, ID,
IA, KS, LA, ME, MI, MS, MT, NE, NV, NH, ND, RI, SC, SD, VT, WV and WY. These states offer
search portals, paid county vendors or statewide paid subscriptions. In AL, Alacourt is
paid. In LA, NOLA open data has only code-enforcement hearings and sheriff sales on lien
foreclosures (`d52w-8nva`, stale since 2018). For WV, see `wv-state-federal.md`.

## Ranked: what to load first

| Rank | Source | Why | Hostnames |
|---|---|---|---|
| 1 | NYC OATH Hearings Division Case Status (`jz4z-kudi`) | 3.7M docketed city judgments with balance due and BBL, which joins to parcels; daily | `data.cityofnewyork.us` |
| 2 | NYS Tax Warrants (`v7ua-z23v`) and Child Support Warrants (`8pp4-isha`) | Statewide liens with judgment effect, amount, debtor address and satisfaction dates; daily | `data.ny.gov` |
| 3 | Allegheny tax liens and mortgage foreclosures (WPRDC) | 3.25M liens plus 40.7k foreclosures keyed to the PIN; CC0 | `data.wprdc.org`, `tools.wprdc.org` |
| 4 | CT SOTS lien filings (`xfev-8smz`) | The only free statewide judgment-lien filings (personal property), plus 222k municipal liens; nightly | `data.ct.gov` |
| 5 | NYC Evictions (`6z8x-wfk4`) and HPD Housing Litigations (`59kj-x8nc`) | Court index numbers and BBL; possession judgments and penalties | `data.cityofnewyork.us` |
| 6 | Harris County JP Public Data Extract | Case-level civil and eviction data from 16 courts by date range; **verify it is free and has judgment fields first** | `jpwebsite.harriscountytx.gov` (blocked here; needs allowlisting) |
| 7 | Broward Official Records FTP index | Daily recorded judgments (Official Records); **verify it is free** | `www.broward.org`, plus the FTP host named on that page [UNVERIFIED] (blocked here) |
| 8 | Franklin County OH Municipal Court eviction CSVs | Nightly, 13 months of eviction cases | `fcmcclerk.com` (blocked here) |
| 9 | Harris County District Clerk Public Datasets | Large civil datasets; **excluded if a login is needed** | `www.hcdistrictclerk.com` (blocked here) |
| 10 | Colorado and Oregon SOS lien data | IRS, hospital and statutory liens for debtor enrichment, not judgments | `data.colorado.gov`, `data.oregon.gov` |

Ranks 1 to 5 can be loaded today: the hosts are reachable, and each is a Socrata or CKAN
API with no key. Ranks 6 to 9 need the hosts added to the session's network allowlist
and their terms read before building.

## Open questions for Brandon

1. Do tax warrants, child-support warrants, municipal tax liens and ECB judgments count as
   "judgments" for the business, or only as liens and enrichment? TODO(Brandon)
2. Harris JP extract and Broward FTP: may I allowlist those hosts and read their terms and
   file layouts? Nothing has been contacted.
3. The Harris District Clerk Public Datasets may require a free registered account. Is a
   free account a "login" under the brief?
