# Free bulk indexes of recorded judgments (county recorders/clerks/prothonotaries) and state judgment-lien registries

Researched 2026-11-22. Tags: [LIVE] = pulled from the publisher's API in this session; [SEARCH] = from web-search snippets only (publisher host blocked); [UNVERIFIED] = thin/conflicting evidence. Skipped per brief: Hillsborough FL, NYC ACRIS, Philadelphia RTT (loaded); Miami-Dade, Palm Beach, Lee, Lake, Cook, Harris, Tarrant, Maricopa (known paid). WebFetch was also blocked for every county host tried (broward.org, pascoclerk.com, rcfp.org), so county pages could only be read through search snippets.

## Q1. Are there free bulk files of recorded judgments, from county offices or state registries, that name debtor and creditor?

### Takeaway
The one big new find is a **state-level registry, not a county one**. New York's Department of Taxation and Finance publishes every **state tax warrant** filed with the NY Department of State since 2025-07-01 on data.ny.gov, updated daily. That is **797,150 rows covering 711,082 distinct warrants**. Each row gives the debtor's name and address, the amount, the filing date, and satisfaction, vacate and expiration dates, plus a link to the document image. A companion dataset covers child-support warrants (108,541 rows). Both are free, need no login, and come through the Socrata API [LIVE]. No free county-recorder judgment index was found on ArcGIS Online, ArcGIS Hub or the federated Socrata catalog. The Broward FL daily OR index is still the only plausible free county feed, and whether it is free remains unconfirmed [SEARCH].

### Cited Findings

**New York State Tax Warrants: Beginning 7/1/2025 (`v7ua-z23v`) [LIVE]**
- **Endpoints:**
  - https://data.ny.gov/d/v7ua-z23v
  - API: `https://data.ny.gov/resource/v7ua-z23v.json` (also `.csv`)
  - Metadata: `https://data.ny.gov/api/views/v7ua-z23v.json`
  - Host: `data.ny.gov`, reachable from the shell.
- **Description:** "NYS Tax warrants and related satisfactions, vacates or amendments filed by the NYS Department of Tax and Finance with the NYS Department of State."
  - Posting frequency: Daily.
  - Coverage: Statewide.
  - Owner: DTF Civil Enforcement Division (contact CED.WarrantData.Contact@tax.ny.gov).
  - Time period: "From 7/1/25 (effective date of legislative change) onward."
  - No licence field is set; the data.ny.gov terms apply.
  - Source: [data.ny.gov metadata](https://data.ny.gov/api/views/v7ua-z23v.json)
- **Fields:**
  - `warrant_id`
  - `status_code` (Added/Closed/Updated)
  - `debtor_name_1`–`debtor_name_4`
  - `debtor_address_1/2`, `city`, `state`, `zip_code`, `county_code`, `country_code`
  - `warrant_filed_amount`, `warrant_filed_date`
  - `warrant_satisfaction_date`, `warrant_vacate_date`, `warrant_amend_date`, `warrant_expiration_date`
  - `filed_timestamp`
  - `url`: a document image at `www.tax.ny.gov/warrants/lookup.html?document=…pdf`
  - `georeference`
  - Source: [data.ny.gov](https://data.ny.gov/d/v7ua-z23v)
- **Counts (queried 2026-11-22):** [LIVE] [data.ny.gov API](https://data.ny.gov/resource/v7ua-z23v.json)
  - 503,335 "Added" rows ($4.25B filed amount), 293,617 "Closed" rows ($2.56B) and 198 "Updated" rows.
  - 711,082 distinct `warrant_id`s.
  - `filed_timestamp` runs from 2025-07-01 to 2026-11-18.
  - 60,869 Added warrants are ≥$10k, totalling $3.23B.
  - No Added row has a `warrant_filed_date` before 2025-07-01. Filed dates back to 1982 appear only on Closed rows, i.e. satisfactions of older, county-docketed warrants filed at DOS.
  - 77,762 Closed rows carry an expiration date.
- **Example row:** debtor "LORIANNE MILEY AND/OR WILLIAM D SEEGMULLER", Mahopac NY, $273.06, filed 2026-09-16, satisfied 2026-10-27. [LIVE]
- **Legal effect:** warrants filed with the Secretary of State on or after 2025-07-01 reach all counties within New York State. For warrants with an effective date before 7/1/2025, DOS says to obtain the official warrant from the county clerk where it was filed. Stewart Title's later bulletin says DTF confirmed that only warrants actually filed with DOS on/after 7/1/2025 are liens against real property. [SEARCH]
  - Sources: [DOS State Tax Warrant Notices](https://dos.ny.gov/state-tax-warrant-notices); [Stewart bulletin NY000721a](https://assets.stewart.com/content/stewart/virtualunderwriter/en/bulletins/2025-6/ny000721a.html); [Stewart insight](https://www.stewart.com/insights/new-york-state-tax-warrant-filing-changes); [Abstracts Inc.](https://www.abstractsinc.com/important-changes-to-nys-tax-warrant-filings-effective-july-1-2025/)
- **County clerks still matter:** DTF may still file with county clerks. The New York County Clerk says new state tax warrant records filed with it are "for informational purposes only". [SEARCH] [NY County Clerk judgment docket](https://www.nycourts.gov/courts/1st-judicial-district/new-york-county-clerks-office/judgment-docket-and-lien-section)
- **Other access route:** a per-name public search exists at `appext20.dos.ny.gov/stwarrants_public` (search portal, not bulk; blocked). [SEARCH] [DOS search](https://appext20.dos.ny.gov/stwarrants_public/st_search)

**New York State Child Support Warrants: Beginning 7/1/2025 (`8pp4-isha`) [LIVE]**
- Filed by DTF with DOS. Fields: `warrant_id`, `status_code_a_c_u`, `debtor_name`, `debtor_address`, city/state/zip/county, `warrant_filed_amount`, filed, satisfaction, vacate and expiration dates, `filed_timestamp`, `url`.
- Counts: 108,541 rows and 106,158 distinct warrants.
  - 19,064 Added ($196.8M).
  - 89,477 Closed ($491.6M); many of these close older warrants.
- Timestamps run from 2025-07-01 to 2026-11-20.
- Source: [data.ny.gov](https://data.ny.gov/d/8pp4-isha)

**Missouri Child Support Lien List (`7t5a-79ri`) [LIVE catalog]**
- Columns include `child_support_lien_date`, `lien_satisfaction_date`, `vin_number` and `make`. These are vehicle liens, not real-property judgments.
- Host `data.mo.gov` was not tested.
- Source: [data.mo.gov](https://data.mo.gov/d/7t5a-79ri)

**ArcGIS Online and Hub searches [LIVE]**
- ArcGIS Online `sharing/rest/search` found 0 items for "abstract of judgment" and "certificate of judgment".
- "judgment lien" returned only Lucas County OH forfeited-land parcels.
- "recorded documents" returned mostly Minnesota LandShark lookup apps and parcel-drafter layers, none with a judgment index.
- Source: [ArcGIS search API](https://www.arcgis.com/sharing/rest/search?q=%22judgment%20lien%22&f=json)
- Hub v3 search on "judgment lien", "recorded judgments", "official records index", "lis pendens" and "liens recorded" found only tax-lien and code-lien layers already known (Maricopa, Baltimore, Louisville, LA, Douglas CO), plus one new layer:
  - **City of Tucson "Recorder Liens May 2019 2024"**: 517 code-enforcement liens hand-collected from the Pima County Recorder. Fields: `Customer_1-4` (owner), `Address`, `Lien_Recording_Date`, `Amount_Due`, `Payment_Status`, `Lien_URL` (Pima recorder document link). It is a one-off (data last edited 2024-10). [LIVE] [Tucson layer](https://services3.arcgis.com/9coHY2fvuFjG9HQX/arcgis/rest/services/Recorder_Liens_May_2019_2024/FeatureServer/0)

**Socrata federated catalog searches [LIVE]**
- Searched via `datacatalog.cookcountyil.gov/api/catalog/v1` on: judgment(s), abstract of judgment, recorded documents, official records, recorder, lien, satisfaction, register of deeds.
- No county-recorder judgment index exists on any Socrata domain.
- Judgment-bearing hits are already known, or are government-creditor sets:
  - NYC Housing Litigations
  - NYC DOF Scofftow (`judgment_amount`)
  - NYC Open Parking and Camera Violations (`judgment_entry_date`)
  - NOLA hearings
  - TCEQ Civil Judgments (`7ift-kbgd`)
  - Ohio Court of Claims Wrongful Imprisonment (`amount_of_judgment`)
  - Cook Recorder 2011–2015
  - Macoupin 2015
- Source: [Socrata catalog](https://datacatalog.cookcountyil.gov/api/catalog/v1?q=judgment&only=dataset)

### Inferences
- The NY tax-warrant feed works like a statewide judgment-lien registry. Under the 2025 change, a DOS-filed warrant reaches real property in every county. It also carries a satisfaction signal and a link to the image. Together with ACRIS it gives statewide NY coverage of one class of government-creditor judgment. The creditor is always NYS DTF, so this is debtor discovery and competing-lien data, not inventory to buy.
- Open warrants are probably about 711k − 294k ≈ 417k. This is a rough figure, because one warrant can have several Added rows (one per debtor-name variant) and Updated rows. Computing it exactly needs a per-`warrant_id` rollup.
- Searching the platforms (ArcGIS, Hub, Socrata) turned up no county recorder that publishes recorded judgments as open data. Free recorded-judgment indexes, where they exist, are clerk FTP/HTTP index files like Hillsborough's, not portal datasets.

### Gaps
- The exact statute text was not read: Tax Law §692 as amended, and the 2025 budget Part that moved filing to DOS. The legal effect above rests on title-insurer bulletins and the DOS page.
- It is not known whether NYS DOL unemployment-insurance warrants are also moving to DOS with an open dataset. None was found on data.ny.gov.
- `www.tax.ny.gov` (image links) is blocked, so the images were not tested.

## Q2. Florida clerks (Fla. Stat. 28.2221): which give free bulk daily OR index downloads?

### Takeaway
Apart from Hillsborough (loaded), no Florida clerk was confirmed to give a free bulk OR index. Broward's Records, Taxes & Treasury Division publishes daily pipe-delimited index extracts on an FTP site, but whether they are free is still unconfirmed [SEARCH]. Pasco and St. Lucie appear to sell subscriptions. Pinellas, Duval, Orange, Sarasota, Collier, Polk and St. Johns returned nothing in search.

### Cited Findings
- **Broward:**
  - "Official Records FTP files that include both images and index data". The site gives "10 continuous days" of images and index; the daily index extracts are pipe-delimited and zero-byte on no-activity days.
  - A second page says each file stays 7 days, which conflicts with the 10-day figure.
  - Search did not state the price; the earlier note found a $30 index-CD fee.
  - [SEARCH] Sources: [Broward Bulk Data Files](https://www.broward.org/RecordsTaxesTreasury/Records/Pages/IndexFiles-Completed.aspx); [Daily Index Extract examples](https://www.broward.org/RecordsTaxesTreasury/Records/Pages/DailyIndexExtractFiles.aspx)
- **Miami-Dade:** $80 per folder per month, $110 from 2025-10-01; OR images FTP $420/month. [SEARCH] [Miami-Dade developers/FTP](https://www2.miamidadeclerk.gov/Developers/FTP)
- **Lake:** OR index plus images download costs a $75 setup fee plus $900/year, and covers the last 10 business days only. [SEARCH] [Lake Clerk](https://www.lakecountyclerkfl.gov/?p=5362)
- **Palm Beach:** daily FTP index (files kept ≥45 days) through its "electronic distribution index service", a subscription. [SEARCH] [Palm Beach EDIS](https://www.mypalmbeachclerk.com/records/official-records/electronic-distribution-index-service)
- **St. Lucie:** "Monthly Reports – 30 day Subscription" (paid). [SEARCH] [St. Lucie Clerk](https://docs.stlucieclerk.gov/monthly-reports-30-day-subscription/subscribe-to/8-monthly-reports-30-day)
- **Pasco:** "Subscription Download Data" page exists; its price and contents were not readable (host blocked). [UNVERIFIED] [Pasco](https://www.pascoclerk.com/526/Subscription-Download-Data)
- **Florida Department of State (Sunbiz):**
  - Bulk files on `sftp.floridados.gov` cover corporations, fictitious names, marks and **federal tax liens** (daily and quarterly). Access uses a published public login.
  - **Judgment-lien certificates (Fla. Stat. 55.202, personal property) are not among the bulk files.**
  - [SEARCH] Sources: [Sunbiz Data Downloads](https://dos.fl.gov/sunbiz/other-services/data-downloads/); [Daily Data](https://dos.fl.gov/sunbiz/other-services/data-downloads/daily-data/); [Judgment Lien info](https://dos.fl.gov/sunbiz/forms/judgment-lien/)

### Inferences
- Section 28.2221 requires an online searchable index, not a bulk file. Most large clerks monetise bulk feeds, so Hillsborough looks like the exception.
- The Sunbiz federal-lien daily file is free bulk competing-lien data (IRS liens on personal property filed at FL DOS). It is not a judgment index, but it is worth a separate check if `sftp.floridados.gov` is allowlisted.

### Gaps
- The other 60-odd Florida clerks were not checked one by one. Search coverage is shallow, and a per-clerk sweep would need their hosts allowlisted.
- Broward's price is unresolved.

## Q3. Texas county clerks, PA prothonotaries, Ohio common pleas clerks, Georgia GSCCCA

### Takeaway
None was found to offer a free bulk judgment index.
- **Texas:** abstracts of judgment are recorded in real-property records (Prop. Code 52.004), but county bulk data is sold. Fort Bend keeps a bulk-purchaser list.
- **Pennsylvania:** prothonotary bulk data is priced (Philadelphia) or only searchable. Lancaster's "free download" was in-office and is undated.
- **Ohio:** certificates of judgment are indexed by clerks under ORC 2329.02, but Franklin County requires a public-records request for data files and forbids mining its CIO portal.
- **Georgia:** the GSCCCA lien index (statewide since 2004, includes FiFa and judgment liens) is subscription-only. No bulk price for the lien index was found; its UCC bulk was $200/day, $750/week or $1,500/month (2018 form).

### Cited Findings
- **Texas:**
  - The clerk must record each abstract of judgment in the real property records. [SEARCH] [Tex. Prop. Code 52.004](https://codes.findlaw.com/tx/property-code/prop-sect-52-004/)
  - Abstracts cost $8 per document in Tarrant and Fort Bend. [SEARCH] [Tarrant form](https://www.tarrantcountytx.gov/content/dam/main/county-clerk/AbstractofJudgmentReqFormAug2025.pdf)
  - The Fort Bend District Clerk sells bulk data and keeps a purchaser list. [SEARCH] [Fort Bend bulk data sales](https://www.fortbendcountytx.gov/government/departments/fort-bend-county-district-clerks-office/bulk-data-sales)
  - TX SOS UCC bulk costs $65/day, with a $1,150 master unload. [SEARCH] [TX SOS](https://www.sos.state.tx.us/ucc/bulk-order.shtml)
  - TCEQ Civil Judgments (`7ift-kbgd`) remains the only free Texas judgment dataset found (already listed in prior report). [LIVE catalog]
- **Pennsylvania:**
  - Philadelphia courts price bulk civil and judgment databases (2012 fee schedule). [SEARCH] [Phila fee schedule](https://www.courts.phila.gov/pdf/accesspolicy/Fee-Schedule-Public-Access.pdf)
  - Monroe C-Track is a docket/judgment search, not bulk. [SEARCH] [Monroe](https://monroecountypa.gov/departments/prothonotary/resources/c-track)
  - RCFP reports that "anyone with a flash drive can now download, free of charge, civil court records from the Lancaster County prothonotary office" (undated; appears in-office). [SEARCH] [RCFP](https://www.rcfp.org/civil-records-free-download-pennsylvania-county/)
  - Lancaster's own resources page lists only a civil records search and a 1983–93 judgment index book. [SEARCH] [Lancaster resources](https://co.lancaster.pa.us/261/Resources)
  - AOPC handles "requests for court data" with recurring fees. [SEARCH] [pacourts.us](https://www.pacourts.us/page/1172)
- **Ohio:**
  - ORC 2329.02 (eff. 2024-10-24) requires clerks to docket and index certificates of judgment. [SEARCH] [ORC 2329.02](https://codes.ohio.gov/ohio-revised-code/section-2329.02)
  - Franklin CIO: organisations wanting data files must file a Public Records Request, and "efforts to mine large quantities of data… will be detected and stopped." [SEARCH] [Franklin CIO](https://www.franklincountyohio.gov/Service-Finder-I-Want-To/Find-Court-CIO)
  - Hamilton has a "Common Pleas Certified Judgements/Liens" search page, not bulk. [SEARCH] [courtclerk.org](https://www.courtclerk.org/records-search/common-pleas-certified-judgements-liens)
- **Georgia:**
  - The GSCCCA lien index covers all counties since at least 2004-01-01 and includes FiFa. [SEARCH] [GSCCCA lien index](https://gsccca.org/learn/search-systems/lien-index)
  - UCC bulk price list on the 2018 subscription form. [SEARCH] [Justia form](https://forms.justia.com/georgia/secretary-of-state/uniform-commercial-code/subscription-agreement-for-purchase-of-bulk-data-21602.html)
- **Other states' Secretary of State lien bulk (Idaho, Minnesota, Connecticut, Wisconsin, Kentucky):** all paid subscriptions. CT business database costs $3,000/year. [SEARCH] [Idaho](https://sos.idaho.gov/UCC/subscriptions.html); [CT](https://business.ct.gov/Knowledge-Base/Article/Sots/Bulk-Data-and-Images)
- **CA SOS:** judgment liens on personal property (JL1) can be filed, but no bulk feed was seen. [SEARCH] [CA SOS](https://www.sos.ca.gov/business-programs/ucc/judgment-lien)

### Inferences
- For TX, PA, OH and GA, the realistic free path is a public-records request for an index extract (Ohio Public Records Act, PA Right-to-Know, TX PIA), not an open file. Georgia's statewide lien index is the single most valuable paid target, since one subscription covers 159 counties.

### Gaps
- No Washington, Oregon, Utah or Colorado county recorder judgment feed was found on the open-data platforms. Their recorder sites were not checked individually; Salt Lake is known paid from prior notes.
- The GSCCCA lien-index bulk price is unknown.

## Hostnames for allowlisting
- **Reachable now:** `data.ny.gov`, `hub.arcgis.com`, `www.arcgis.com`, `services*.arcgis.com`, `datacatalog.cookcountyil.gov`, `hillsclerk.com`.
- **Blocked; needed to verify:**
  - `www.tax.ny.gov` (warrant images)
  - `appext20.dos.ny.gov`, `dos.ny.gov`
  - `www.broward.org`, `ftp.broward.org`
  - `sftp.floridados.gov`, `dos.fl.gov`
  - `www.pascoclerk.com`
  - `www.occompt.com`, `www.pinellasclerk.org`
  - `gsccca.org`, `search.gsccca.org`
  - `data.texas.gov`
  - `www.lancastercountypa.gov`, `co.lancaster.pa.us`
  - `www.rcfp.org`
  - `data.mo.gov` (untested)
