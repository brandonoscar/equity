# Government programs that publish named debtor lists (court-ordered / adjudicated debts) — beyond prior coverage

Scope note: prior report (`reports/More free judgment sources.md`) covered state tax top-delinquent lists, NJ DOL WALL/Watchlist, PA L&I, FL DOR warrants, child-support posters, federal enforcement, court bulk sales. None of the angles below (recovery funds, client-protection funds, scofflaw/boot data, HPD litigation, court-fine programs) appear in it (grep for CSLB, recovery fund, scofflaw, FARE, restitution, client security, HPD litigation returned 0 hits).

Tags: [LIVE] = pulled from host in this session; [SEARCH] = seen only in search-result snippets/indexes; [UNVERIFIED] = inferred or not confirmed.

Reachability this session: only `data.cityofnewyork.us` and `data.oregon.gov` resolved. Blocked (DNS fail from shell and WebFetch): `www.njcourts.gov`, `www.labor.maryland.gov`, `nvcontractorsboard.com`, `www.madera.courts.ca.gov`, `www.harkerheights.gov`, `www.supremecourt.ohio.gov`, `courtnewsohio.gov`, `www.cslb.ca.gov`, `roc.az.gov`, `www.dpor.virginia.gov`, `data.texas.gov`, `data.wa.gov`, `catalog.data.gov`, `www.nyc.gov`, `huntsvilletx.gov`, `www.dallascounty.org`, `landlordwatchlist.com`.

## 1. Court-ordered debt / restitution / fines collection programs that publish delinquent lists

### Takeaway
No statewide court-ordered-debt program (Arizona FARE, Texas OCA CIP, California court collections) was found to publish a named delinquent-debtor file. The publishable artifacts are local: Texas municipal-court "capias pro fine" warrant lists (PDF; a capias pro fine issues when a defendant fails to satisfy a judgment), Dallas County's delinquent-fine lookup (search portal, not a file), and odd California court PDFs.

### Cited Findings
- Arizona FARE (Fines/Fees and Restitution Enforcement) is a 2003 AOC public/private program to collect delinquent court-ordered obligations. Its tools are MVD registration holds and intercepts of tax refunds, lottery and gaming winnings. Courts refer cases more than 90 days delinquent. Nothing found shows it publishes debtor names [SEARCH] — [azcourts.gov FARE](https://azcourts.gov/courtservices/Consolidated-Collections-Unit/FARE); [FARE Overview PDF](https://www.azcourts.gov/Portals/0/27/FARE/Documents/Overview_200.pdf); [AO 2023-195](https://www.azcourts.gov/Portals/0/22/admorder/Orders23/2023-195.pdf)
- Huntsville TX posts a PDF of active municipal-court warrants ("current at the time of posting"). Its page defines a capias pro fine as issued when "an individual fails to satisfy a judgment according to its terms" [SEARCH] — [huntsvilletx.gov/388/Warrants](https://huntsvilletx.gov/388/Warrants)
- The legal basis for capias pro fine is Tex. Code Crim. Proc. art. 45.045 [SEARCH] — [Laredo Municipal Court](https://www.cityoflaredo.com/departments/municipal-court/warrants-arrests); TMCEC bench guide [Warrant/Capias/Capias Pro Fine 2025](https://www.tmcec.com/wp-content/uploads/2025/12/Warrant-Capias-Capias-Pro-Fine-2025-FINAL.pdf)
- Harker Heights TX publishes a dated warrant-listing PDF (`WARRANTLISTING08092026xls.pdf`, Aug 2026) exported from a spreadsheet. Columns and amounts are unverified because the host is blocked [SEARCH] — [harkerheights.gov PDF](https://www.harkerheights.gov/images/PDF/WARRANTLISTING08092026xls.pdf). Other TX cities with warrant pages: [Cibolo](https://cibolotx.gov/services/municipal_court/warrants.php), [Deer Park](https://deerparktx.gov/409/Warrants), [Harlingen](https://harlingentx.gov/departments/municipal_court/warrant.php), [Fulshear](https://www.fulsheartexas.gov/about-us/departments-h-z/municipal-court/warrants), [Fort Worth](https://fortworthtexas.gov/municipalcourt/warrants), [Roanoke](https://roanoketexas.gov/182/Warrant-Information), [Horseshoe Bay](https://horseshoe-bay-tx.gov/762/Warrants)
- Dallas County runs an "Online Wanted and Delinquent Offender Lookup" covering people owing traffic, criminal or civil fines and fees. A balance is removed when it reaches zero or the case is disposed. It is a search portal, not a file [SEARCH] — [dallascounty.org/dcwantedsearch](https://www.dallascounty.org/dcwantedsearch/); [FAQ](https://www.dallascounty.org/dcwantedsearch/faq.jsp)
- Madera Superior Court (CA) hosts alphabetical PDF lists titled "list-2-fy-2021-22-d-g", "list-5-fy-2021-22-l-m". Their purpose (unclaimed bail/refunds vs. debts) is unverified [SEARCH] — [Madera list 2](https://www.madera.courts.ca.gov/system/files/list-2-fy-2021-22-d-g.pdf)
- Monterey County CA posts board "discharge of accountability" reports for uncollectible delinquent criminal and traffic fines. These are write-offs, and whether they name debtors is unverified [SEARCH] — [Monterey 2023](https://www.monterey.courts.ca.gov/system/files/general/discharge-accountability-10-17-2023.pdf)

### Inferences
- Texas capias-pro-fine lists are literally lists of people who failed to pay a criminal or traffic-fine judgment. They are small (tens to low thousands per city), PDF, and usually carry name plus offense and sometimes amount. They are not liens and are a poor fit for civil judgment purchase. They are mainly useful as a "judgment-debtor-with-unpaid-court-debt" flag.
- The Madera PDFs are most likely unclaimed-money (bail refund) lists, i.e. money owed *to* people, not debtors [UNVERIFIED].

### Gaps
- Texas OCA Collection Improvement Program: found nothing showing it publishes named lists. Search returned no OCA results.
- California court-ordered debt (FTB COD program): not searched in depth. Nothing was found showing FTB publishes COD debtor names.
- Row counts and fields of the TX warrant PDFs: the hosts are blocked.

## 2. Licensing-board unsatisfied-judgment lists (contractor / DMV)

### Takeaway
Contractor boards enforce unpaid construction judgments by suspending licenses, but none found publishes a free bulk "suspended for judgment" file. California CSLB offers a free master list of active licenses (without judgment status) and sells the full file for $235. Washington L&I publishes contractor bond data on Socrata, but not bond-claim judgments.

### Cited Findings
- CSLB: a construction-related judgment must be reported within 90 days or the license is suspended. A creditor uses form 13S-28 to request suspension. If the judgment is paid or a payment plan is set, no mention appears on license check [SEARCH] — [CSLB Civil Judgments](https://www.cslb.ca.gov/Consumers/Legal_Issues_For_Consumers/Civil_Judgments.aspx); [Notice of Unsatisfied Final Judgment form](https://www.cslb.ca.gov/Resources/FormsAndApplications/NoticeUnsatisfiedFinalJudgment.pdf); [Resolving Judgments](https://www.cslb.ca.gov/contractors/license_problems/Resolving_Judgments.aspx)
- The CSLB Data Portal free master list covers only currently renewed or renewable licenses. The full License Master File (700,000+ records) costs $235. The custom "ALL" order includes renewed-but-suspended licenses. The record layout is published as LBL780J1 [SEARCH] — [Data Portal ContractorList](https://www.cslb.ca.gov/OnlineServices/DataPortal/ContractorList); [order form](https://WWW.CSLB.CA.GOV/Resources/FormsAndApplications/FULL_FILE_-_UPDATE_FILE_ORDER_FORM.pdf); [layout](https://WWW.CSLB.CA.GOV/Resources/FormsAndApplications/License_Master_Record_Layout_LBL780J1.pdf)
- CSLB annual revocation lists by year exist at `/About_us/Library/Revoked/Default.aspx?Year=YYYY` (contents unverified) [SEARCH] — [CSLB Revoked 2021](https://cslb.ca.gov/About_us/Library/Revoked/Default.aspx?Year=2021)
- WA L&I: "L&I Contractor License Data – Bond" dataset (data.wa.gov `bzff-4fmt`, modified 2026-04-12), plus General, Insurance and Principal datasets. L&I does not handle lawsuits against bonds and only keeps copies of judgments [SEARCH] — [catalog.data.gov bond](https://catalog.data.gov/dataset/li-contractor-license-data-bond); [L&I Filing a Lawsuit](https://lni.wa.gov/licensing-permits/contractors/problems-with-a-contractor/filing-a-lawsuit)
- Oregon open data has "CCB Active Licenses" (`g77e-6bhs`, updated 2026-11-22). No CCB dispute or final-order dataset turned up in a catalog search [LIVE] — [data.oregon.gov](https://data.oregon.gov/api/catalog/v1?q=contractor%20judgment)

### Inferences
- The CSLB free master list might carry a judgment or suspension status field in LBL780J1. Diffing it monthly could reveal licenses newly suspended for judgments [UNVERIFIED; needs `www.cslb.ca.gov` allowlisted and the layout read].

### Gaps
- DMV financial-responsibility / unsatisfied-judgment suspensions: found no state publishing names (driver records are DPPA-protected, so none expected).
- Arizona ROC: no public list of Recovery Fund payments by licensee was found. The ROC must publish an unlicensed-contractor list (HB2077), which is not a payment list [SEARCH] — [azleg HB2077 summary](https://www.azleg.gov/legtext/56leg/2R/summary/H.HB2077_013124_CAUCUSCOW.DOCX.htm); fund financials only: [AZ Auditor FY2024](https://www.azauditor.gov/sites/default/files/2025-06/ArizonaRegistrarOfContractorsResidentialContractorsRecoveryFundJune30_2024FinancialReport.pdf)

## 3. State recovery / guaranty funds publishing paid claims against named licensees

### Takeaway
Two concrete publishers were found. **Maryland Home Improvement Commission** posts fiscal-year disciplinary pages (FY2014 to FY2025) listing contractor name and trade name, case number and Guaranty Fund award amount. **Nevada State Contractors Board** posts Residential Recovery Fund meeting/award PDFs (2010 to 2024). Most other funds (FL Homeowners' Construction Recovery Fund, VA DPOR, CA DRE, TX TREC, AZ ADRE/ROC) publish only aggregates or bury awards in board minutes.

### Cited Findings
- Maryland MHIC: pages `labor.maryland.gov/license/mhic/mhicdisc{YYYY}.shtml` (FY2014 to FY2025). Each logs complaint date, case number, decree type and either a Guaranty Fund award amount (about $500 to $30,000) or a denial, with contractor name and trade name. Example entries are a $30,000 award (WMC Contractors LLC) and $27,339.11 (Win Win Home Improvement). These are HTML pages, not files [SEARCH] — [MHIC FY2025](https://www.labor.maryland.gov/license/mhic/mhicdisc2025.shtml); [FY2024](https://www.labor.maryland.gov/license/mhic/mhicdisc2024.shtml); [FY2022](https://labor.maryland.gov/license/mhic/mhicdisc2022.shtml)
- Nevada NSCB: Recovery Fund committee PDFs such as `12-01-22-Recovery-Fund-Meeting.pdf`, `01-30-19-Recovery-Fund-Awards.pdf` and `100519-Residential-Recovery-Fund-Awards_May-2010.pdf`. Press releases give totals, e.g. Jan 2024: $394,068 to 24 homeowners. Whether the PDFs name the contractor is unverified (host blocked) [SEARCH] — [NSCB 12-01-22](https://nvcontractorsboard.com/wp-content/uploads/2023/09/12-01-22-Recovery-Fund-Meeting.pdf); [NSCB 01-30-19 awards](https://www.nvcontractorsboard.com/wp-content/uploads/2023/09/01-30-19-Recovery-Fund-Awards.pdf); [Jan 2024 release](https://nvcontractorsboard.com/wp-content/uploads/2024/05/01-22-2024-NEVADA-STATE-CONTRACTORS-BOARD-AWARDS-394000-TO-HARMED-HOMEOWNERS-THROUGH-RECOVERY-FUND-NEWS-RELEASE.pdf)
- Florida: under Fla. Stat. 489.143 a license is "automatically suspended... upon the date of payment from the fund". Caps are $50k per claim and $500k per contractor (a 2024 bill proposed doubling them, enactment unverified). Case detail appears in CILB minutes, and no payment list was found [SEARCH] — [Fla. Stat. 489.143](https://m.flsenate.gov/Statutes/489.143); [CILB minutes example](https://www2.myfloridalicense.com/pro/cilb/documents/cilb_minutes_0726.pdf)
- Virginia DPOR Contractor Transaction Recovery Fund: the Board issues payment directives (Va. Code 54.1-1122) and a payout triggers license revocation. Disciplinary actions are posted in minutes on Virginia Regulatory Town Hall, and file orders are visible via License Lookup. No payment list was found [SEARCH] — [DPOR Contractor Recovery Fund](https://www.dpor.virginia.gov/Boards/Contractors_Recovery_Fund/); [Va. Code 54.1-1122](https://law.lis.virginia.gov/vacode/54.1-1122/); [DPOR revocations release 2023](https://www.dpor.virginia.gov/news/NewsReleases_09-19-23ContractorRevoke)
- Real estate recovery funds: CA DRE reports only an aggregate (more than $65M paid since 1964). AZ ADRE has a $30,000 per-transaction cap. TX TREC and LA LREC have fund pages without payout rosters [SEARCH] — [CA DRE CRA](https://www.dre.ca.gov/consumers/ConsumerRecoveryAccount.html); [AZ ADRE](https://azre.gov/consumers/recovery-fund); [TREC](https://www.trec.texas.gov/public/real-estate-recovery-funds); [LREC](https://lrec.gov/enforcement/recovery-fund); [VA real estate fund](https://www.dpor.virginia.gov/Boards/Real_Estate_Recovery_Fund)

### Inferences
- A recovery-fund payment usually requires the claimant to first obtain an unsatisfied court judgment against the licensee. Each MHIC or NSCB award therefore marks a licensee with at least one uncollectible judgment, and the fund is subrogated to it (the state now holds the judgment) [UNVERIFIED per state; true for FL 489.143, VA 54.1-1120 et seq.]. As a buy target these debtors are by definition judgment-proof. They are better used as a negative screen.
- Volume is small: MHIC is likely tens to low hundreds of awards per year, and NSCB about 20 to 60 awards per meeting cycle.

### Gaps
- Exact row counts and fields for MHIC and NSCB: hosts blocked. Allowlist `www.labor.maryland.gov` and `nvcontractorsboard.com`.
- Auto dealer and travel recovery funds (e.g. FL, CA travel consumer restitution, MD MVA dealer bond) were not searched in this budget.

## 4. Attorney client-protection funds naming attorneys

### Takeaway
**New Jersey Lawyers' Fund for Client Protection** publishes a quarterly "List of Claims Paid" PDF naming each attorney, last town of practice, amount paid this quarter, cumulative amount, claim count, disciplinary status and claim basis. This is the cleanest find in this area. **Ohio LFCP** names attorneys in quarterly Court News Ohio releases, on a reimbursements table page and in annual-report PDFs.

### Cited Findings
- NJ LFCP quarterly PDFs: `lfcp2025q1.pdf` to `lfcp2025q4.pdf`, `lf-2quarter-2024.pdf`, `2024-fourth-quarter-revised.pdf`, back to `lf-4quarter-2022.pdf`. Fields are attorney name, town, law practice, disciplinary status, amount paid, a cumulative column and claim basis. Example names: Santo V. Artusa Jr., Dwight Hugh Day, Rodrigo Sanchez, Edward G. D'Alessandro Jr. [SEARCH] — [NJ LFCP 2025 Q4](https://www.njcourts.gov/sites/default/files/lfcp2025q4.pdf); [2025 Q3](https://www.njcourts.gov/sites/default/files/attorneys/new-jersey-lawyers-fund-client-protection/lfcp2025q3.pdf); [2024 Q2](https://www.njcourts.gov/sites/default/files/attorneys/new-jersey-lawyers-fund-client-protection/lf-2quarter-2024.pdf); [2022 Q4](https://www.njcourts.gov/sites/default/files/attorneys/new-jersey-lawyers-fund-client-protection/lf-4quarter-2022.pdf)
- NJ LFCP quarterly volumes: Jan 2026, over $85,000 on 14 claims; Oct 2025, nearly $315,000 on 11 claims; Jul 2025, nearly $127,000 on 13 claims. A 2024 release cites 4,916 claims against 903 attorneys over the fund's history [SEARCH] — [NJ press Jan 2026](https://www.njcourts.gov/press-releases/2026/01/lawyers-fund-client-protection-awards-over-85000-14-claims); [Oct 2025](https://njcourts.gov/press-releases/2025/10/lawyers-fund-client-protection-awards-nearly-315000-11-claims); [Jul 2025](https://www.njcourts.gov/press-releases/2025/07/lawyers-fund-client-protection-awards-nearly-127000-13-claims)
- Ohio LFCP: in June 2026 it reimbursed $408,112.67 to 22 victims and named attorneys (e.g. Javier H. Armengau, $56,020 across 7 clients; David E. Stenson, $2,500). March 2026 was more than $240,000 and Dec 2025 was $80,007.62. There is a reimbursements table page and annual-report PDFs (2024, 2025) [SEARCH] — [CNO Jun 2026](https://courtnewsohio.gov/happening/2026/LFCP_061526.asp); [CNO Mar 2026](https://courtnewsohio.gov/happening/2026/LFCP_031826.asp); [Ohio reimbursements page](https://www.supremecourt.ohio.gov/courts/advisory/boards/client-protection/reimbursements/); [2025 annual report](https://www.supremecourt.ohio.gov/docs/Boards/clientprotection/annual_reports/2025.pdf)

### Inferences
- These are not court judgments against the attorney. They are administrative findings of dishonest conduct, and the fund is typically subrogated to the client's claim. Under NJ R. 1:28 the fund can pursue the attorney [UNVERIFIED rule cite]. Debtors are mostly disbarred or insolvent attorneys, so they have low collectability but are a high-signal fraud screen. Volume is about 10 to 25 claims per quarter in each state.

### Gaps
- The other ~48 state funds were not surveyed. Many (e.g. CA State Bar CSF, NY Lawyers' Fund) publish annual reports. Whether they name attorneys is unverified.

## 5. Municipal scofflaw / parking judgment and housing-litigation data (reachable now)

### Takeaway
Two NYC Open Data sets are live and not in the prior report. **DOF Scofftow Case Information** has 1,565,097 boot/tow cases for unpaid parking-judgment debt, with judgment amount, but is keyed by plate with no names. **HPD Housing Litigations** has 242,293 cases naming landlord respondents, with 3,671 flagged `casejudgement=YES` and a `penalty` field. Both have the legal effect of adjudicated judgments, but they offer limited debtor identity.

### Cited Findings
- `data.cityofnewyork.us/resource/qmh3-uvgq` (DOF Scofftow Case Information). Updated 2026-11-16, 1,565,097 rows, latest boot_date 2026-11-12. Fields: case_number, case_status, plate, state, type, judgment_amount, boot_date, tow, redeemed, redemption_date, total_amount_owed, total_amount_collected, auction fields. Status mix: 1,358,917 Redeemed, 87,631 Sold, 54,776 Runaway, 43,025 Other. Sample: plate KUY1182, judgment $809.77, owed $1,089.77, Redeemed 2026-11-12 [LIVE] — [Socrata API](https://data.cityofnewyork.us/resource/qmh3-uvgq.json)
- The booting threshold for combined parking and camera judgments was lowered to $400 in Feb 2023. The Open Parking and Camera Violations dataset is refreshed weekly [SEARCH] — [DOF 2023 Local Law 6 report](https://www.nyc.gov/assets/finance/downloads/pdf/23pdf/2023-local-law-6-report.pdf); [2026 LL6 report](https://www.nyc.gov/assets/finance/downloads/pdf/26pdf/2026-local-law-6-report.pdf)
- `data.cityofnewyork.us/resource/59kj-x8nc` (HPD Housing Litigations). Updated 2026-11-01. casejudgement YES = 3,671, NO = 238,622. Judgments by case type: Heat and Hot Water 2,392, Tenant Action 656, Comprehensive 280, Tenant Action/Harassment 216, Comp Supplemental 55. Rows with a non-zero `penalty` = 277 (latest open date 2026-07-02, e.g. $5,000 harassment penalties "After Inquest"). Fields: respondent (multiple owner, LLC and manager names), address, BBL, BIN, casetype, casestatus, findingofharassment, findingdate, penalty [LIVE] — [Socrata API](https://data.cityofnewyork.us/resource/59kj-x8nc.json)
- NYC Public Advocate Worst Landlord Watchlist (Jan 21, 2026 edition) ranks by average open HPD violations Dec 2024 to Nov 2025, at landlordwatchlist.com. No download was confirmed and it carries no fine amounts [SEARCH] — [Public Advocate release](https://advocate.nyc.gov/press/nyc-public-advocate-unveils-annual-worst-landlord-watchlist-top-two-have-most-violations-in-history)

### Inferences
- HPD `casejudgement=YES` rows are Housing Court judgments (civil penalties) in HPD v. owner proceedings. With respondent names and BBL they join directly to ACRIS and the OATH data already loaded. The `penalty` field is sparsely populated, so most judgment amounts are absent and would need the Housing Court docket [UNVERIFIED that penalty equals judgment amount].
- Scofftow is a satisfied/unsatisfied judgment-debt signal on vehicles only. Without a DMV-name join (DPPA-barred) it cannot identify debtors.

### Gaps
- Other cities' scofflaw lists (Chicago, Boston, Philadelphia, DC) were not checked.

## 6. Debt setoff lists, vendor debarment, judgment docket indexes

### Takeaway
Nothing found in this budget. Setoff programs (lottery, gaming, tax intercepts such as Arizona FARE's) operate confidentially. No state was found publishing a free abstract-of-judgment index file.

### Cited Findings
- FARE intercepts lottery and gaming (event wagering and fantasy sports) winnings for delinquent court-ordered obligations, with no public list [SEARCH] — [AO 2023-195](https://www.azcourts.gov/Portals/0/22/admorder/Orders23/2023-195.pdf)

### Gaps
- Vendor debarment for unpaid judgments, state judgment docket bulk indexes, and liquor-license tax/judgment holds were not searched in depth.

## Hostnames to allowlist (priority order)
1. `www.njcourts.gov`: NJ LFCP quarterly claims-paid PDFs
2. `www.labor.maryland.gov` (also `labor.maryland.gov`, `dllr.state.md.us`): MHIC Guaranty Fund awards
3. `nvcontractorsboard.com` / `www.nvcontractorsboard.com`: NSCB Recovery Fund award PDFs
4. `www.supremecourt.ohio.gov`, `courtnewsohio.gov`: Ohio LFCP
5. `www.cslb.ca.gov` / `web.cslb.ca.gov`: CSLB data portal and record layout
6. Texas municipal courts: `www.harkerheights.gov`, `huntsvilletx.gov`, `www.dallascounty.org`
7. `www2.myfloridalicense.com`: CILB minutes; `www.dpor.virginia.gov`; `data.wa.gov`
