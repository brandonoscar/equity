# Phase 0: WV state and federal sources (Monongalia County pilot)

Researched 2026-11-15. No logins, sign-ups, payments or CAPTCHA solving. About 3 to 8 requests per host, with a 10 s gap on www.wvnd.uscourts.gov (it sets `Crawl-delay: 10`).

Tags:
- **VERIFIED**: I fetched the official page or PDF myself in this session.
- **FROM SEARCH**: seen only in web-search results or snippets. Needs a direct check before anyone relies on it.

Sandbox limits on reachable hosts:
- **Did not answer:** www.wvsao.gov (the TLS connection was reset on all 4 attempts).
- **Outside the sandbox allowlist:** apps.sos.wv.gov, code.wvlegislature.gov, wiki.free.law (CourtListener's help and terms now redirect there), ecf.wvnb.uscourts.gov, www.wvnb.uscourts.gov, monongalia.softwaresystems.com and webgen1files1.revize.com.

Everything about those hosts below is FROM SEARCH.

---

## robots.txt summary (all VERIFIED unless noted)

| Host | Result | Relevant lines |
|---|---|---|
| apps.wv.gov | 200 | `User-agent: *` ... `Disallow: /WebCommand/`, `Disallow: /PaymentSystem/`, `Disallow: /uat/` ... `# Known Public Applications` `Allow: /SOS` |
| sos.wv.gov | 200 | Drupal default file: `Disallow: /search/`, `Disallow: /search?`, `Disallow: /user/login`, `/admin/` etc. Nothing blocks `/sites/default/files/` or `/media/` (the form PDFs). |
| www.wvsao.gov | not reachable | TLS reset on 4 tries, so robots.txt is unknown. |
| tax.wv.gov | 404 | No robots.txt (SharePoint "File Not Found"). |
| www.wvnd.uscourts.gov | 200 | `User-agent: *` `Crawl-delay: 10` plus Drupal defaults (`Disallow: /search/`, `/user/login/` ...). |
| ecf.wvnd.uscourts.gov | 404 | No robots.txt (Apache 404). |
| pacer.uscourts.gov | 200 | Drupal defaults only (`Disallow: /search/`, `/user/login` ...). |
| www.courtlistener.com | 200 | `# If you would like to crawl CourtListener, please contact us. We also have an extensive REST API and provide bulk data.` Then for `User-agent: Claude-User` (and other AI agents): `Allow: /help/`, `/feeds/`, `/terms/` ... `Disallow: /`. For `User-agent: *`: `# Be conservative; Block everything.` `Disallow: /`. The named search engines are also blocked from `/api/rest/v1/`, `/v2/`, `/v3/`. |
| www.wvlegislature.gov | 200 | `User-agent: *` `Disallow: /WVCODE/` (also `/apps/`, `/media/`, `/js/` ...). `/Bill_Text_HTML/` is **not** disallowed. The current Code is served from code.wvlegislature.gov (the homepage links there), which is outside the sandbox. |
| www.courtswv.gov | 200 | Drupal defaults only. |
| monongaliasheriff.gov | 302 | `/robots.txt` redirects to `https://webgen1files1.revize.com/monongaliacntysheriffwv/robots.txt` (Revize CMS), which is outside the sandbox, so the rules are **unknown**. I fetched only 2 pages there. |

---

## A. WV Secretary of State: business entities and UCC

### A1. Free Business Entity Search: https://apps.wv.gov/SOS/BusinessEntitySearch/
- **Access method (VERIFIED):** an ASP.NET WebForms POST (`__VIEWSTATE`/`__EVENTVALIDATION`) with **one input field, "Organization Name"** (maxlength 50). Google reCAPTCHA v3 loads (`https://www.google.com/recaptcha/api.js?render=...`), and on page load `grecaptcha.execute(..., {action:'homepage'})` writes a token into the hidden field `ctl00$phMain$hiddenRecpatcha`, which is submitted with the search. It is invisible and score-based, but it **is** a CAPTCHA gate on search. Automated searching would mean defeating it, so this route is out under our rules.
- **Freshness (VERIFIED):** the page says "Search Data Current as of Sunday, November 15, 2026 12:00 AM", so the data refreshes nightly.
- **Search by officer or agent? (VERIFIED, for this app):** no. The only search is by entity name.
- **Fields shown (VERIFIED from the Help page):** the results list gives entity name, entity type, city and status. "Details" adds full address, registered number, entity creation date and registered agent contact information. "There are no fees associated with viewing this information." Certificates of Existence or Authorization cost $10 each, by credit card.
- **Terms of use (VERIFIED):** the Disclaimer page has only an accuracy disclaimer. I found no clause on automated access or resale. The page footer links to the WV.gov "Privacy, Security and Accessibility" policies (www.wv.gov is outside the sandbox).
- **Rate limits:** none published.
- URLs: https://apps.wv.gov/SOS/BusinessEntitySearch/Help/Default.aspx, https://apps.wv.gov/SOS/BusinessEntitySearch/Help/Disclaimer.aspx

### A1b. Business Organization Information System (detail pages): http://apps.sos.wv.gov/business/corporations/
- sos.wv.gov's own navigation sends "Search Business Organizations" to this host (VERIFIED). The host itself is outside the sandbox, so everything else here is **FROM SEARCH**.
- **Search modes (FROM SEARCH):** an "Organization" tab and an **"Agent/Officer/Name" tab**, so officer and agent name search exists here. Also "Show Advanced Search Options" (third parties mention the `%` wildcard and a county filter). It is free. **I could not confirm whether it has a CAPTCHA.**
- **Detail URL pattern (FROM SEARCH):** `https://apps.sos.wv.gov/business/corporations/organization.aspx?org=<id>`
- **Detail fields (FROM SEARCH, from snippets of many org pages):**
  - Org type, effective date, established date, filing date, charter, class, termination date and termination reason
  - Charter county, charter state, control number, business purpose, capital stock, management type ("Member Managed")
  - Addresses: Designated Office, Mailing, Notice of Process, Principal Office
  - **Officers**, with roles such as Incorporator, President, Secretary, and Member or Manager
  - **Annual Reports** (years filed), plus a "Not in compliance" flag
  - Also seen: amendments, DBAs, name changes and mergers. Pages carry a "no warranty" notice.

### A2. SOS Bulk Data Service: https://apps.wv.gov/SOS/BulkData/
- **Access (VERIFIED):** login only, for "authorized Monthly Account Holders". The steps are:
  1. Register a WV.gov account.
  2. Sign the **WV.gov Monthly Account Holder Agreement**.
  3. Submit the **Business Entity** and/or **UCC** and/or **UCC Images** Bulk Data Request Form.
  4. If reselling, sign the **Contract for Commercial Resale of Secretary of State Records**.
  5. For UCC images, sign the **notarized UCC Bulk Images Nondisclosure Agreement**.
  - The forms sit behind go.wv.gov short links (`sosbdmaha`, `sosbdbe`, `sosbducc`, `sosbducci`, `sosbdrsc`). Source: https://apps.wv.gov/SOS/BulkData/RegistrationInformation.aspx
- **Files offered (VERIFIED, FileDescriptions.aspx):**
  - Business Entity: All Companies (monthly), New Companies Monthly, New Companies Weekly (Mondays) and New Companies (daily, prior business day)
  - UCC: All UCC Filings (monthly), New Monthly, New Weekly and New Daily
  - UCC Images: All active UCC1 images since 1/1/2015 (monthly), New Monthly and New Weekly
- **Business Entity file format (VERIFIED, BED_FileInformation.pdf v1.0, Dec 2009):** 9 files, tilde (`~`) delimited, header row, zipped.
  - **Addresses.csv** ("all officers on file"): Recordid, ContactType, ContactName, Street1, Street2, City, StateProvince, Country, ZipCode. This is the officer, agent and address table.
  - **Corporations.csv:** Recordid, Name, EffectiveDate, FilingDate, BusinessType*, CharterType*, CharterStateProvince, CharterCounty*, BusinessClass*, TerminationDate, TerminationReason*, TerminationEntryDate, TotalAuthorizedShares, ParValue. (* = coded value.)
  - Amendments.csv (Recordid, Amendment, AmendmentDate)
  - Annual_Reports.csv (Recordid, HistoryNumber, DateFiled, FilingFor)
  - DBAs.csv (Recordid, DBAName, DBAType, EffectiveDate, TerminationDate)
  - Dissolutions.csv (Recordid, HistoryNumber, ActionPending, StatementOfIntentDate, ApprovalRequestedDate, ESApprovalDate, WCApprovalDate, TaxApprovalDate, ArticlesOfDissolutionDate)
  - Mergers.csv (SurvivingCorporationID/Name/State, MergerDate, MergingCorporationID/Name/State)
  - NameChanges.csv (Recordid, OldName, ChangeDate)
  - Subsidiaries.csv (Recordid, SubsidiaryName, Street1, Street2, City, StateProvince, Zipcode)
- **UCC file format (VERIFIED, UCC_FileInformation-v3.0.pdf, 2017):** 3 files, tilde delimited.
  - **Debtors.csv:** UCC_ID, Debtor_Name, Address, City, State, ZipCode, Country
  - **SecuredParties.csv:** UCC_ID, SecuredParty_Name, Address, City, State, ZipCode, Country
  - **Documents.csv:** UCC_ID, DocumentDate, DateAdded, DateModified, UccStatus, UccDocumentType (1, 3 or 5), Continuation, Amendment, Assignment, PartialRelease, Termination, Other (booleans: NULL, 0 or -1), Other_text
- **Price (VERIFIED, "Request for Purchase of Bulk Data" form, https://sos.wv.gov/sites/default/files/2026-04/BED_RequestForm.pdf, modified Apr 7 2026, signed by Sec. Kris Warner):**
  - "purchase the entire Business Organizations database at the one time purchase cost of **$12,000**"
  - "monthly updates of the Business Organizations database at the cost of **$1,750 per month** for ___ consecutive months". This can be bought on its own or on top of the full purchase.
  - The form asks you to check "do NOT intend to resell" or "do intend to resell ... agrees to comply with ... Contract for Commercial Resale".
- **Resale contract (VERIFIED, https://sos.wv.gov/sites/default/files/2026-04/BulkDataResaleContract.pdf, 6 pp.):**
  - Recital: records "shall not be obtained for purchase or commercial resale without the written agreement of the state to a contract including reimbursement to the state for each instance (W. V. Code §59-1-2)."
  - Art. IV Initial Purchase Price: **$12,000** (Business Organizations) or **$12,360** (UCC). If the annual renewal lapses, a new contract is needed and the initial price is paid again.
  - Art. V Update Price (from July 1, 2012): **$21,000/yr** (Business Organizations) or **$15,000/yr** (UCC), giving 12 monthly updates, paid in advance.
  - Art. VI Resale Fee: **$1,800 per database per year**, on top of the above.
  - Art. VII: WV consumer sales tax applies if applicable.
  - Art. VIII: "VENDOR shall only distribute the data in its Product"; "VENDOR may not authorize its users, customers or others ... to resell the data in its original bulk data format"; the State may terminate immediately on breach.
  - Art. X: Vendor indemnifies the State.
  - Art. XIII: 1-year term, auto-renews yearly up to 5 years if paid; 60-day notice to terminate.
  - Delivery is electronic only.
- **UCC statutory prices (FROM SEARCH, W. Va. Code §46-9-523):** whole UCC database $12,360; weekly updates $258; weekly updates in monthly form $1,030.
- **UCC Images NDA (VERIFIED, https://apps.wv.gov/SOS/BulkData/Content/UCC-Bulk-Images-Agreement.pdf):** notarized. "Subscriber shall not use, release, sell, or further disclose any PII furnished by the SOS" and must indemnify the State over SSN/TIN disclosure.
- **WV.gov Monthly Account Holder Agreement fee:** not found (the form is behind go.wv.gov, outside the sandbox). Open question.

### A3. Business Entity Custom List Service: https://apps.wv.gov/SOS/BusinessEntity/
- **Price (VERIFIED):** "List fees consist of a minimum **$25.00** search fee plus **$0.05** per record." Names and addresses only, no phone or email. It "Includes Business Name & Address, Registered Officers, Principals, Partners, Registered Agents."
- **Filters (VERIFIED, MainMenu.aspx, no CAPTCHA found):**
  - Business type, class, and registration status (Active or Inactive)
  - Business purpose, **officer name**, **notice of process (agent) name** and city
  - **WV charter county (includes Monongalia)**, charter state, ZIP codes
  - Original registration date range and **last updated date range**
  - With the date filters this could serve as a cheap delta feed. Example: new or updated Monongalia entities each month for $25 plus $0.05 per row.
- **File format (VERIFIED, BEL_FileInformation.pdf v1.0, Mar 2010):** 9 tilde-delimited files joined on Record ID.
  - **BusinessEntity.csv** (28 fields): Record ID, Business Name, Effective and Filing Date, Business Type, Charter Type, Charter State and County, Business Class, Termination Date, Reason and Entry Date, Business Purpose, Last Renewal Date and Year, Mailing Street 1 and 2, City, State and Zip, **Notice of Process Name**, Street 1 and 2, City, State and Zip, Total Authorized Shares, Par Value
  - **Addresses.csv** ("officer/partner addresses"): Record ID, Business Name, Business Type, Contact Type, Contact Name, Street 1 and 2, City, State, Country, Zip
  - Plus Amendments, Annual_Reports, DBAs, Dissolutions, Mergers, NameChanges and Subsidiaries, in the same layout as the bulk files
- **Terms on the list page:** I found no resale clause there. The §59-1-2 resale rule cited in the bulk contract probably still applies (open question).

### A4. UCC Online Search: https://apps.wv.gov/SOS/UCC/Search
- **Access (VERIFIED):** a JavaScript (Knockout) single-page app with **Google reCAPTCHA Enterprise** (`RECAPTCHA_ENABLED = true`, `recaptcha/enterprise.js`). Automated use is out.
- **Search keys (VERIFIED):** Debtor, Secured Party or Filing Number. Options are Active (unlapsed only), Active with lapsed +1 year, and a filing date range. A space is the wildcard. "Information available for searches may be delayed up to twenty minutes."
- **Result columns (VERIFIED):** Filing Number, Date, Type, Debtor, Secured Party, Status. The order grid adds Pages and Price.
- **Cost (VERIFIED, https://sos.wv.gov/ucc-filing-procedures):** "UCC Searches: initial fee **$10.00**, Per page fee **$1.00**, WV Portal Fee **$3.00**". Card only. Since 2/27/2018 searches are online only.
  - **FROM SEARCH / unconfirmed:** browsing the name index and filing-results list before checkout appears free. The fee covers the emailed search order or copies.
- **Search instructions (VERIFIED):** https://sos.wv.gov/media/333/download?inline= (Rev. 3/2/2018). Regular Search gives copies only. Certified Search gives a certificate (regular, date-range, to-date, or "No Records Found").

---

## B. PACER, N.D. W. Va. (district and bankruptcy), CourtListener

### B1. PACER fees (VERIFIED, https://pacer.uscourts.gov/pacer-pricing-how-fees-work and https://pacer.uscourts.gov/policy-procedures)
- **$0.10 per page.** Documents (dockets, motions, orders, judgments, briefs): "You won't be charged more than **$3 per document**."
- **No cap** on search results (charged "even if the search displays 'no matches found'"), on non-case-specific reports, or on transcripts.
- Audio is $2.40 per file. No registration fee.
- **Quarterly waiver:** "no account is billed for usage of less than **$30** in a quarter" / "Spend $30 or less ... fees are WAIVED". Billing is quarterly. A firm-level PACER Administrative Account gets one $30 waiver for the whole firm, not one per user.
- Free: opinions; one free copy via NEF/NDA for parties; public terminals at courthouses; court-granted fee exemptions.
- PACER Service Center research: $30 per name searched plus $0.10/page electronic (max 5 docs), or $0.50/page by mail.

### B2. PACER Case Locator (PCL) and PCL API (VERIFIED, https://pacer.uscourts.gov/help/pacer/pacer-case-locator-pcl-api-user-guide and PDF `PCL-API-10-2026.pdf`)
- PCL is the nationwide index, searchable by party or case, and can be limited by court. It is billable at PACER page rates.
- The REST API (JSON/XML) needs a PACER account and authentication token (`X-NEXT-GEN-CSO` header). "All searches in the Production environment are billable."
- Immediate searches return pages of 54 results, up to 5,400 items (100 pages). Batch searches go up to 108,000 items (2,000 pages).
- The QA environment (qa-pcl.uscourts.gov) is free but holds test data only.
- Search fields include courtId, caseType, dateFiledFrom/To, lastName, firstName, partyRole and jurisdictionType (Civil, Bankruptcy ...). Production host: pcl.uscourts.gov.

### B3. PACER terms relevant to automation and redistribution
- **VERIFIED (policy-procedures):**
  - "Any attempt to collect data from PACER in a manner that avoids billing is strictly prohibited and may result in criminal prosecution or civil action."
  - "Misuse includes ... using an automated process to repeatedly access those portions of the PACER application that do not assess a fee (i.e., calendar events report or case header information) for purposes of collecting case information."
  - PACER may "Suspend or reduce service ... by any account that causes an unacceptable level of congestion".
  - The account is "for my use only, unless specifically designated otherwise".
  - I found **no clause on that page barring resale** of data bought at normal fees.
- **FROM SEARCH:** data obtained under a **fee exemption** may not be sold for profit, transferred or redistributed online. This comes from the EPA fee schedule as quoted in court exemption orders, e.g. https://www.scd.uscourts.gov/StandingOrders/Fees/PACER_Fee_Exemption-Fitzpatrick.pdf. So a fee exemption is not usable for a commercial pipeline.

### B4. U.S. District Court N.D. W. Va. (wvnd)
- **Monongalia County is in the N.D. W. Va., Clarksburg division** (VERIFIED). Sources: county map PDF https://www.wvnd.uscourts.gov/sites/wvnd/files/sites/wvnd/files/County%20Division%20Map%20WV%202016.pdf ("MONONGALIA ... Clarksburg") and PACER court page https://pacer.uscourts.gov/file-case/court-cmecf-lookup/court/WVNDC.
  - CM/ECF office codes (VERIFIED, https://ecf.wvnd.uscourts.gov/cgi-bin/CourtInfo.pl): **1 Clarksburg**, 2 Elkins, 3 Martinsburg, 5 Wheeling.
  - Case number format: `O:YY-TY-#####-INI-RIN`, so Monongalia cases look like `1:26-cv-...`.
- **Free RSS (VERIFIED):** https://ecf.wvnd.uscourts.gov/cgi-bin/rss_outside.pl, no login, returns `text/xml`.
  - CourtInfo.pl says: "RSS Feed: **Docket entries of type: all**, Last 24 hours' entries". The feed `<description>` says "Docket entries of type: all".
  - Item structure: `<title>` = case number plus caption; `<link>` = `DktRpt.pl?<caseid>`; `<description>` = `[Entry Type]` plus a link to the document number (`/doc1/...`, which needs a PACER login and is billed); `<guid>` = `DktRpt.pl?<caseid>&<de_seq_num>`; `<pubDate>`.
  - It gives no docket text beyond the bracketed entry type, no party addresses and no amounts. 3 items were live on a Sunday afternoon.
  - Rate limits: none published. ecf has no robots.txt. Poll politely (e.g. hourly).

### B5. U.S. Bankruptcy Court N.D. W. Va. (wvnb)
- **Host (VERIFIED via PACER lookup https://pacer.uscourts.gov/file-case/court-cmecf-lookup/court/WVNBK):** https://ecf.wvnb.uscourts.gov, website http://www.wvnb.uscourts.gov.
  - NextGen CM/ECF 1.9. P.O. Box 70, Wheeling, WV 26003; 304-233-1655.
  - **Monongalia is listed among its counties.**
- **Division (FROM SEARCH, https://www.wvnb.uscourts.gov/court-info):** four points of holding court. Monongalia falls in the **Clarksburg** list (Braxton, Calhoun, Doddridge, Gilmer, Harrison, Marion, Monongalia, Pleasants, Preston, Ritchie, Taylor).
- **RSS (FROM SEARCH):** the wvnb site has an "RSS for CM/ECF" menu item. The expected URL is https://ecf.wvnb.uscourts.gov/cgi-bin/rss_outside.pl, which I could not fetch (outside the sandbox). **The entry types it covers are unverified.** Check them at https://ecf.wvnb.uscourts.gov/cgi-bin/CourtInfo.pl.

### B6. CourtListener / RECAP (Free Law Project)
- **robots.txt (VERIFIED):** it says "We also have an extensive REST API and provide bulk data". Generic crawlers and AI user agents are disallowed everywhere except /help/, /feeds/, /terms/ and similar. /help/api/rest/ and /terms/ now 301 to wiki.free.law (outside the sandbox).
- **API (FROM SEARCH):**
  - REST v4 needs a header `Authorization: Token <key>`; the token comes from a free account profile.
  - Since May 7, 2026, API access is included with memberships (https://free.law/2026/05/07/api-included-in-memberships/).
  - Rate limits reported for a **new free account: 5/min, 50/hr, 125/day** (third-party, citing the docs; older sources say 5,000/hr). Memberships start around $10/month for small organizations (third-party).
  - Membership API use is "intended for personal, educational, research, journalistic, and exploratory use". Larger commercial users reportedly need a negotiated agreement, and the prices are not public.
  - "Creating more than one account per project, person, or organization is forbidden." A Usage API reports your limits.
- **Coverage of wvnd and wvnb (FROM SEARCH / unverified):** CourtListener builds docket alerts largely from court RSS feeds. RECAP holds only what users bought plus RSS-derived entries. I could not query `/api/rest/v4/dockets/?court=wvnd` (robots disallows it and it needs a token). A FreeLaw wiki table appears to list N.D. W. Va. under full feeds, but the text was garbled. Treat coverage as unknown.

---

## C. Delinquent property tax / tax lien sales (Monongalia)

### C1. Who sells: the State Auditor, not the Sheriff, since SB 552 (2022)
- **VERIFIED** from Enrolled CS for SB 552 (2022), https://www.wvlegislature.gov/Bill_Text_HTML/2022_SESSIONS/RS/bills/SB552%20SUB1%20ENR.pdf:
  - **§11A-3-2:** "On or before the September 10 of each year, the sheriff shall prepare a second list of delinquent lands ... will be certified to the Auditor for disposition pursuant to West Virginia Code §11A-3-44 on the 31st day of October". The sheriff publishes it as a **Class III-0 legal advertisement** in the county and sends certified-mail notices at least 30 days before the Auditor's sale.
    - The list's columns are: "Name of person charged with taxes | Quantity of land | Local description | Total amount of taxes, interest and charges due to date of sale".
  - **§11A-3-8:** property not redeemed by Oct 31 "the sheriff shall certify ... to the Auditor".
  - **§11A-3-13:** within one month the sheriff publishes the certification list as a Class II-0 legal ad.
  - **§11A-3-44:** "On or after March 1 and on or before August 1 of each year, the Auditor shall certify a list of all lands subject to sale".
  - **§11A-3-45:** the Auditor sells "at public auction at the courthouse of the county to the highest bidder ... within 90 days after the Auditor has certified the lands".
  - References to sales "by or from the Auditor shall be construed as the sale or purchase of the tax lien".
- **Conflict to flag (VERIFIED):** the Monongalia Sheriff's tax page (https://monongaliasheriff.gov/tax/index.php) still says the Tax Office is responsible for "the selling of delinquent Real Estate taxes in November". This looks stale given SB 552; confirm with the office (304-291-7244).
- **Later changes (FROM SEARCH):**
  - 2023 SB 548 (bidder eligibility; the Auditor may refuse unsold lands to some buyers) was enacted.
  - **2026 SB 651** (private auctioneer and 10% buyer's fee) passed the Senate 33-0 on 2/27/2026, then was referred to House Judiciary on 3/2/2026. I found no enrolled version (`sb651 enr.pdf` returns 404 on wvlegislature.gov, VERIFIED), so it probably died. Confirm.
  - Also FROM SEARCH: a WVSAO newsletter (April 2026) says properties still delinquent on Oct 31 are certified to the Auditor on Nov 1. Third-party guides put the county auctions around April to June.

### C2. WV State Auditor, Land / County Collections (www.wvsao.gov / main.wvsao.gov). Not reachable, so all FROM SEARCH.
- Pages: https://www.wvsao.gov/CountyCollections, https://www.wvsao.gov/CountyCollections/SheriffTaxSaleResults, https://www.wvsao.gov/LegalNotices/Default.aspx
- **"SB552 Land Sale Listings":** a per-county row with sale date, time, location and a "View Listings" link (HTML).
- **"Certified to State" search:** HTML search by Tax Year and County (any one field). Result columns: **Cert Number, Assessed Name, Purchaser Name, Bidder Id, Description, Ticket, Account**. I found no owner-address or amount-due column, and no bulk download (CSV/PDF).
- **Legal notices:** copies of the newspaper sale ads by county.
- **Bidders:** one statewide pre-registration per year; payment by check or money order "payable to the sheriff of the county".
- Cost: free to view. Terms, robots and rate limits are unknown (host unreachable).

### C3. Monongalia County Sheriff Tax Office online tax search
- **Vendor (VERIFIED from links on https://monongaliasheriff.gov/tax/index.php):** "Online Search" goes to https://monongalia.softwaresystems.com/index.html and "Online Payment" to https://monongalia.softwaresystems.com/INDEXp.html (Software Systems, Inc. hosting).
  - The same page also links the Monongalia County Parcel Viewer and the County Clerk Record Search.
  - Office: 243 High St. Rm 300, Morgantown; (304) 291-7244.
- **Fields and search keys (FROM SEARCH):** search by name, account number, map/parcel or ticket number. The record fields (tax year, owner, district/map/parcel, assessed values, tax due, paid or delinquent) are unverified.
- **Terms and robots:** unknown. The vendor host is outside the sandbox.
- Sheriff site robots.txt: unknown (redirects to Revize).

---

## D. WV judgment-lien and recording law (for the open-questions list only)

> **For Brandon to confirm. Do NOT encode any of this as rules.** These are pointers, not legal conclusions.
>
> The official Code is served at code.wvlegislature.gov. www.wvlegislature.gov links there, and its robots.txt disallows `/WVCODE/`. That host is outside the sandbox, so items marked FROM SEARCH were not read on the official page.

1. **Judgment lien on real estate: §38-3-6, docketing §38-3-5, and the bona-fide-purchaser rule §38-3-7.**
   - https://code.wvlegislature.gov/38-3-6/ (FROM SEARCH): "every judgment for money rendered in this state, other than by confession in vacation, shall be a lien on all the real estate of or to which the defendant in such judgment is or becomes [possessed/the owner] ..." The lien "shall continue so long as such judgment remains valid and enforceable, and has not been released or otherwise discharged."
   - https://code.wvlegislature.gov/38-3-7/ (FROM SEARCH): "No judgment shall be a lien as against a purchaser of real estate for valuable consideration without notice, unless it be docketed according to the fifth section of this article." There is also a 10-year limit against purchasers unless an execution was issued and filed.
   - §38-3-5 is titled "Docketing abstracts of judgments; indexing ..." (title only, FROM SEARCH).
   - Question for Brandon: does the lien attach when the judgment is entered, with docketing in the county clerk's judgment lien docket needed only against bona fide purchasers?
2. **Enforcement period: §38-3-18** (https://code.wvlegislature.gov/38-3-18/, FROM SEARCH).
   - (a) "On a judgment, execution may be issued within ten years after the date thereof." Further executions may issue within 10 years of the return day of the last one.
   - (c) An action or scire facias within ten years.
   - Against a decedent's personal representative: within five years of qualification.
   - Exceptions are in §38-3-19. A child-support variant runs from emancipation.
3. **Homestead exemption.**
   - **§38-10-4(a), bankruptcy only (VERIFIED as existing law reproduced in 2026 HB 5393 as introduced, https://www.wvlegislature.gov/Bill_Text_HTML/2026_SESSIONS/RS/bills/hb5393%20intr.pdf):** "The debtor's interest, not to exceed **$35,000** in value, in real property or personal property that the debtor or a dependent of the debtor uses as a residence ...". A physician carve-out goes up to $250,000. The bill would change the wildcard in (e); I did not check whether it passed.
   - **Non-bankruptcy (FROM SEARCH):** W. Va. Const. art. VI §48 and §38-9-1 give a **$5,000** homestead "exempt from forced sale", last amended 1973. Exact wording not verified: https://code.wvlegislature.gov/ (Constitution).
4. **Recording priority: §40-1-9** (https://code.wvlegislature.gov/40-1-9/, FROM SEARCH). A contract, deed, deed of trust or mortgage "shall be void, as to creditors, and subsequent purchasers for valuable consideration without notice, until and except from the time that it is duly admitted to record in the county wherein the property embraced in such contract, deed, deed of trust [or mortgage] may be". Whether WV is race-notice or notice is for Brandon to confirm.

---

## Open questions
1. Does the SOS reCAPTCHA v3 also cover detail pages, and does apps.sos.wv.gov (Agent/Officer/Name search) have a CAPTCHA? I could not reach it.
2. Is there a WV.gov Monthly Account Holder Agreement fee? Does §59-1-2 resale reimbursement apply to the $25 + $0.05 Custom List output?
3. What is the current UCC bulk price: §46-9-523 ($12,360 / $258 weekly / $1,030 monthly) or the contract ($12,360 + $15,000/yr)?
4. Which entry types does the wvnb RSS carry (CourtInfo.pl)? Does CourtListener actually ingest wvnd and wvnb?
5. Is the CourtListener API acceptable for our commercial use under membership terms, or do we need a Free Law Project data-services agreement?
6. When is Monongalia's Auditor sale for 2025 taxes? Can WVSAO "View Listings" be downloaded? Does Software Systems publish terms of use?
7. Section D items, all for Brandon.
