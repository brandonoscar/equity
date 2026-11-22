# Republished US civil judgment / debt-collection / eviction datasets (GitHub and data repositories)

Scope note: I skipped sources already in `reports/More free judgment sources.md`. That report already covers Harris County JP extracts, the FJC IDB on CourtListener, LSC CCDI and Eviction Lab (case data only under agreements), ProPublica debt-collection data (terms gate), the Oklahoma bulk-distribution bar, and a search-only mention of Debt Collection Lab. Debt Collection Lab and Eviction Lab are re-evaluated below only where new [LIVE] evidence adds something.

Tags: [LIVE] means I fetched it myself from github.com, raw.githubusercontent.com or the S3 host. [SEARCH] means web-search snippets only. [UNVERIFIED] means inference or uncited.

Network limits in this session: `api.github.com` repo trees, the Debt Collection Lab netlify site, `virginiacourtdata.org`, `opendata.maryland.gov` and `catalog.data.gov` were all refused by the proxy. WebFetch also failed on the netlify host. I could not inspect Hugging Face, Kaggle, Zenodo, Dataverse or data.world directly. Only web search reached them.

## Q1. Which repos and republished datasets hold case-level civil judgment data, and what fields do they carry?

### Takeaway
There is no free, no-login, currently maintained republished dataset that names judgment debtors with amounts in bulk across a whole state. The well-known projects either strip names before publishing (NYC/NYS OCA, virginiacourtdata.org, Debt Collection Lab, Eviction Lab, January Advisors) or have moved behind licensed or approved access (Maryland Case Harvester, the named Virginia data). The only named, amount-bearing tables I found are small, stale one-off scrapes in personal GitHub repos. They are Oregon (Multnomah) evictions 2020–2021 with defendant name, address and a "judgment creates lien" flag, and Cleveland Municipal Court evictions 2014–2020 with defendant name and property address but only costs, not judgment amounts. The largest free source of judgment amounts is the NYS OCA housing-court judgments table, which is current to 2026-11-22 but de-identified.

### Cited Findings

**NYS OCA housing court data (OCA Data Collective / Housing Data Coalition)**
- [LIVE] The repo `housing-data-coalition/oca` runs ETL on XML filings that OCA delivers by SFTP. It publishes CSV tables on S3: oca_index, causes, addresses, parties, events, appearances, outcomes, motions, decisions, judgments and warrants. It is licensed **CC BY-NC-SA 4.0**, which is non-commercial — [repo README](https://github.com/housing-data-coalition/oca)
- [LIVE] The S3 `last-updated-date.txt` reads **2026-11-22**. The files were last modified on 2026-11-22 — [last-updated](https://oca-2-dev.s3.amazonaws.com/public/last-updated-date.txt)
- [LIVE] `oca_judgments.csv` is about 193.5 MB. Its columns are: indexnumberid (a hashed id), sequence, judgmenttype, fileddate, entereddatetime, withpossession, latestjudgmentstatus, latestjudgmentstatusdate, **totaljudgmentamount**, creditorsroles and debtorsroles. Sample rows date from 2016 — [oca_judgments.csv](https://oca-2-dev.s3.amazonaws.com/public/oca_judgments.csv)
- [LIVE] `oca_parties.csv` is about 689 MB. It has only role, partytype (Person/Business), representationtype and undertenant, with **no names**. `oca_addresses.csv` has only city, state and postal code. `oca_index.csv` (about 529 MB) covers courts statewide, not just NYC (for example Yonkers City Court and Suffolk District Court), plus classification, disposition and primaryclaimtotal — [oca_parties](https://oca-2-dev.s3.amazonaws.com/public/oca_parties.csv); [oca_index](https://oca-2-dev.s3.amazonaws.com/public/oca_index.csv); [oca_addresses](https://oca-2-dev.s3.amazonaws.com/public/oca_addresses.csv)
- [LIVE] The README says the same data are also "publicly available in XML format on the court system's website" (ww2.nycourts.gov/landlord-tenant-data-34621) — [repo README](https://github.com/housing-data-coalition/oca)
- [LIVE] The older derivative `osdcny/nyc_housing_court_filings` (MIT, last pushed 2021) keeps only the hashed id, file date, property type, classification and zip — [repo](https://github.com/osdcny/nyc_housing_court_filings)

**Virginia: Ben Schoenfeld, virginiacourtdata.org (`bschoenfeld/virginia-court-data`, MIT code, last commit 2025-12-10)**
- [LIVE, site source in repo] The site offers bulk CSV downloads of Circuit Civil and General District Civil cases. The "Last Update" is **April 4, 2025**, with "All cases heard through the end of 2024." District Civil cases from April to June 2022 were back-filled in April 2025 — [index.html in repo](https://github.com/bschoenfeld/virginia-court-data/blob/master/index.html)
- [LIVE] The page says the files are "**Anonymized**: Case numbers, names, and dates of birth have been removed." Un-anonymized data is only for journalists, non-profits, research institutions and government bodies, who must create a Firebase account and submit their organization and purpose for manual approval (`signin.html`; a cloud function emails "requesting access to the full data set"). So **named data fails the no-login rule** — [repo](https://github.com/bschoenfeld/virginia-court-data)
- [LIVE] Alexandria and Fairfax circuit courts are not covered. In 2019, about 100,000 duplicate cases were removed — [index.html](https://github.com/bschoenfeld/virginia-court-data/blob/master/index.html)
- [LIVE] The newer `VirginiaJusticeData/virginia-court-data` (CC BY 4.0, built 2026-11-03) is **criminal only**. It has 15,908,120 court records and 6,587,761 charged offenses with defendant names. Civil matters are excluded unless they are part of a charged incident. It does carry fine and cost amounts due and paid. Those are criminal costs, not civil judgments — [README.txt / data_dictionary.csv](https://github.com/VirginiaJusticeData/virginia-court-data)

**Maryland: Case Harvester (`dismantl/CaseHarvester`, GPL-3.0)**
- [LIVE] The README says the old public site mdcaseexplorer.com and the **monthly table exports are retired**. The relaunched caseharvester.org offers "licensed access" (REST API, CSV export, MCP) on request. "The personal details of criminal defendants and eviction tenants are withheld." The pipeline moved to a private repo — [README](https://github.com/dismantl/CaseHarvester)
- [SEARCH] The Maryland Judiciary publishes "District Court of Maryland Eviction Case Data" on opendata.maryland.gov (dataset mvqb-b4hf). Collection started on 2023-01-01. The search snippets did not show whether names or amounts are included, and the host was blocked, so I could not check the columns — [data.gov record](https://catalog.data.gov/dataset/district-court-of-maryland-eviction-case-data)

**Oregon: `devinmacarthur/TopEvictors2021` (no license, last push 2021-07-31)**
- [LIVE] `data/full_scrape_07_22_2021/flat_file.csv` is 2.9 MB with **9,036 rows**, filed 2020-01-01 to 2021-07-22, mostly Multnomah County. Its fields are case_code, case_name, date, status, location, plaintiff_name, **defendant_names**, **defendant_addr**, judgment, Judgment_General, **Judgment_Creates_Lien**, Judgment_Dismissal, lawyer fields and zip. It has **no dollar amount**. Judgment counts are: "General Dismissal" 3,910; "General Creates Lien" 1,315; "General" 1,074; "General; Supplemental Creates Lien" 352 — [flat_file.csv](https://raw.githubusercontent.com/devinmacarthur/TopEvictors2021/master/data/full_scrape_07_22_2021/flat_file.csv)
- [LIVE] The same folder has RDS tables case_parties, judgments, events and lawyers from the same scrape. The companion repo `devinmacarthur/ojd-eviction-scraping-daily-PLUS` (last push 2021-12-16) is a daily scraper of Oregon Judicial Department records — [repo](https://github.com/devinmacarthur/TopEvictors2021); [scraper](https://github.com/devinmacarthur/ojd-eviction-scraping-daily-PLUS)

**Cleveland: `sdl60660/cleveland_eviction_mapping` (no license, last push 2025-08-28; data 2014–2020)**
- [LIVE] `data/eviction_data.csv` is 17.3 MB with **53,465 rows**, filed 2014-01-02 to 2020-10-20. Its columns are Case Number, Case Status, File Date, Action, **Defendants** (names), **Property Address/City**, Plaintiff, Plaintiff Address, **Costs**, Disposition Status and Disposition Date. There is no judgment-amount column. The top dispositions are dismissal for want of prosecution (15,961), hearing by magistrate (15,776) and other dismissals (13,762). The repo also has geocoded versions — [eviction_data.csv](https://raw.githubusercontent.com/sdl60660/cleveland_eviction_mapping/master/data/eviction_data.csv); [README](https://github.com/sdl60660/cleveland_eviction_mapping)

**Debt Collection Lab (Princeton / January Advisors), site repo `hoshmn/debt-collection-lab` (no license, 2021-08-20)**
- [LIVE] `data/lawsuit_data.csv` is **case-level but de-identified**. Its columns are id (census tract GEOID), name (the tract label), **plaintiff**, date, default_judgment (0/1), has_representation and **amount**. Sample rows are Harris County TX 2020 (for example LVNV Funding, $1,574.09). It has **no defendant names** — [lawsuit_data.csv](https://raw.githubusercontent.com/hoshmn/debt-collection-lab/master/data/lawsuit_data.csv)
- [LIVE] `static/data/lawsuits.csv` holds state aggregates with top-collector totals. For example, Connecticut has 24,873 suits to 04/2021, with Portfolio Recovery Associates at 7,124 suits and $11.80M — [lawsuits.csv](https://raw.githubusercontent.com/hoshmn/debt-collection-lab/master/static/data/lawsuits.csv)
- [SEARCH] The current "Get the data" page links state downloads for CA, CT, IN, MN, MO, ND and VA. The tracker covers 12 states and 333 counties, with suits from 2009 to 2025, and the data were prepared by January Advisors. I could not open the netlify host to confirm whether today's files carry names — [Get the data](https://student-debt-research--debt-collection-lab.netlify.app/get-the-data); [Lawsuit tracker](https://student-debt-research--debt-collection-lab.netlify.app/lawsuit-tracker)

**Houston (January Advisors)**
- [SEARCH] The Harris County Eviction Dashboard presents "de-identified" JP Court data from 2020-01-01 onward. Its downloads are for tracts and top filers — [New America case study](https://www.newamerica.org/insights/eviction-event-case-studies/houston-texas-how-access-to-eviction-filing-data-helped-hold-decision-makers-accountable/)

**Oklahoma (OSCN)**
- [LIVE] `darrenjaworski/oscn-scraper` (no license, last commit 2022-01-02, about 4.4 GB) holds about 89,500 files. They are **scanned docket images (.tif)** under files/2017–2021 and cases/<id>, plus a "search-term/oklahoma-city-housing-authority" folder. There is no structured table — [repo](https://github.com/darrenjaworski/oscn-scraper)
- [LIVE] `OK-Data-Exchange/oscn_scraper` (MIT, 2026-08-06) is a Ruby gem with code only and no data — [README](https://github.com/OK-Data-Exchange/oscn_scraper)

**Eviction Lab (Princeton)**
- [LIVE, search API metadata] The GitHub repos are `EvictionLab/eviction-maps` (MIT), `eviction-lab-etl` (MIT, 2025-02-21) and `eviction-lab-website` (2026-11-21). The descriptions show code for the maps and ETL of aggregates — [EvictionLab org](https://github.com/EvictionLab)
- [SEARCH] Eviction Lab says its records include defendant names, addresses and monetary judgments. Public downloads are aggregated to state, county, city or tract levels — [Eviction Lab methods](https://evictionlab.org/methods/); [Eviction Research Network](https://evictionresearch.net/state-of-eviction-data/)

**Other repos found that only hold code or aggregates (all [LIVE] via the GitHub search API)**
- `NewsappAJC/eviction_scrapers` (Atlanta metro, 2018, code only), `vhaley13/Eviction-Scraping` (Fulton and DeKalb, 2020, 5 files, no data), `atlregional/EvictionScraper` (2022), `al-fz-ha/fcmc_data_scraper` (Franklin County OH, MIT, 2022), `jonathanlamar/case-scraper` (Colorado, 2020), `yxlol/Virginia-Eviction` (Williamsburg/James City, CC-BY-4.0, 2022), `AdamBlaisdell/evictions-web-scraper` (Alexandria VA), `zachgirazian/eviction_scraper` (Iowa, 2025), `evictdb/evict-scrape` (MIT, 2021) — [GitHub search](https://github.com/search?q=eviction+scraper&type=repositories)
- `chengren/nys-eviction` (2026-10-02) has only an aggregated `eviction_state.json` and ACS data — [repo](https://github.com/chengren/nys-eviction)
- [SEARCH] The LSC/CCDI Baseline Court Statistics and the LSC filings-by-county Zenodo record are counts only — [Zenodo](https://zenodo.org/records/23963459); [LSC BCS](https://civilcourtdata.lsc.gov/research/reports/baseline-court-statistics)
- [SEARCH] I found no Hugging Face or Kaggle dataset of named US civil-judgment or eviction cases. The searches returned only aggregate sources — [search context: New America](https://www.newamerica.org/insights/us-eviction-court-data/)

### Inferences
- The best fit for a records graph is OCA `oca_judgments`, which is current, statewide NY, carries amounts and status, and refreshes daily or weekly. But it can only be joined to the graph at zip or city level because the index number is hashed. Its CC BY-NC-SA licence may also bar commercial use. [UNVERIFIED: whether the raw ww2.nycourts.gov XML carries names. Its README calls the OCA data "deidentified."]
- The Oregon and Cleveland repos are loadable (named defendant plus address), but they are one-off snapshots with no licence, which means all rights are reserved by default. They also lack amounts, apart from Oregon's lien flag. They work as historical debtor-discovery seeds, not as a judgment feed.
- The trend has been toward withdrawing names: Case Harvester relaunched as licensed access, virginiacourtdata.org gates names, and Debt Collection Lab and January Advisors publish de-identified data. Named bulk data in republished form is mostly gone.

### Gaps
- I could not read the current Debt Collection Lab state download files (host blocked) to confirm whether they carry names.
- I could not read the Maryland eviction dataset mvqb-b4hf columns (host blocked).
- I did not confirm whether the NYS court's own landlord-tenant XML at ww2.nycourts.gov includes party names.
- I did not inspect Hugging Face, Kaggle, data.world, Zenodo, Dataverse, OSF or figshare directly. Search found nothing relevant, but that is weak evidence of absence.
- I found nothing for Philadelphia (only ML-analysis repos), Shelby County, Michigan, CPAL Dallas (only `childpovertyactionlab/school-housing-profiles`), The Markup or Reveal in GitHub repo search. I did not search newsroom orgs one by one.

## Q2. License, currency and size for each

### Takeaway
Only OCA (CC BY-NC-SA, updated 2026-11-22), VirginiaJusticeData (CC BY 4.0, criminal) and virginiacourtdata.org (anonymized civil, data through 2024) are current and licensed. The named civil scrapes are unlicensed and frozen at 2020–2021.

### Cited Findings
| Dataset | Names? | Amount? | Licence | Last data | Size/rows | Tag |
|---|---|---|---|---|---|---|
| NYS OCA judgments/index (S3) | No (hashed id) | totaljudgmentamount, primaryclaimtotal | CC BY-NC-SA 4.0 | 2026-11-22 | judgments 193 MB; index 529 MB; parties 689 MB | [LIVE] [README](https://github.com/housing-data-coalition/oca) |
| virginiacourtdata.org civil (GD and Circuit) | Removed (named data needs approval) | per field list (Medium post, not read) | Code MIT; data terms unstated | Through 2024 (updated 2025-04-04) | >250k cases per file split | [LIVE] [repo](https://github.com/bschoenfeld/virginia-court-data) |
| VirginiaJusticeData | Yes (criminal) | Fines and costs | CC BY 4.0 | Statewide through May 2026 | 15.9M records | [LIVE] [repo](https://github.com/VirginiaJusticeData/virginia-court-data) |
| Oregon TopEvictors2021 | Yes plus address | Lien flag only | None | 2021-07-22 | 9,036 rows | [LIVE] [repo](https://github.com/devinmacarthur/TopEvictors2021) |
| Cleveland eviction_data | Yes plus property address | Costs only | None | 2020-10-20 | 53,465 rows | [LIVE] [repo](https://github.com/sdl60660/cleveland_eviction_mapping) |
| Debt Collection Lab site CSV | Plaintiff only | Amount plus default flag | None | 2021 snapshot | n/a | [LIVE] [repo](https://github.com/hoshmn/debt-collection-lab) |
| Case Harvester (MD) | Withheld for tenants; licensed | n/a | Licensed access | Continuous | n/a | [LIVE] [README](https://github.com/dismantl/CaseHarvester) |

### Inferences
- If a debtor-name field is required, nothing in this table is both licensed for commercial reuse and current.

### Gaps
- I did not determine row counts for the OCA tables, because the files are too large to pull in full within the budget. Byte sizes only.

## Q3. Scraper repos and ethical/legal flags

### Takeaway
Scraper code exists for Maryland (Case Harvester), Oregon (OJD), Cleveland, Franklin County OH, Atlanta counties, Colorado, Iowa, Oklahoma and Virginia localities. All of them scrape search portals, which the project forbids, so they are useful only as references. Sealing laws and FCRA make reuse of named eviction data risky.

### Cited Findings
- [LIVE] Case Harvester's spider "submit[s] search queries to the MJCS" and splits them recursively around the 500-result cap. That is search-portal scraping. No repo states court permission to scrape — [README](https://github.com/dismantl/CaseHarvester)
- [LIVE] The Cleveland scraper (`sdl60660/cleveland_eviction_scraper`) uses Selenium against the Municipal Court site — [repo](https://github.com/sdl60660/cleveland_eviction_scraper)
- [SEARCH] 17 states plus DC (Stateline, 2024), or 19 states plus DC (NLIHC 2026), now seal at least some eviction records. California automatically seals unlawful-detainer cases unless the landlord wins within 60 days — [Stateline](https://stateline.org/2024/08/21/landlords-cry-foul-as-more-states-seal-eviction-records/); [NLIHC 2026](https://nlihc.org/sites/default/files/AG-2026/CH7/2_Eviction_Record_Sealing_Expungement_Chapter_7.pdf)
- [SEARCH] Maryland enacted eviction-record sealing (2024) — [Multifamily Dive](https://www.multifamilydive.com/news/maryland-seals-eviction-records/728992/)
- [SEARCH] Filings name the plaintiff and defendant subject to state and local tenant-privacy laws — [New America](https://www.newamerica.org/insights/us-eviction-court-data/)
- From the existing report: Oklahoma bars bulk distribution of court data, so derived OSCN dumps carry that cloud — [OK 2009 order](https://law.justia.com/cases/oklahoma/supreme-court/2009/457676.html)

### Inferences
- Frozen scrapes such as Cleveland 2014–2020 and Oregon 2020–2021 may contain cases that have since been sealed or set aside. Republishing or reloading them could resurface sealed records. [UNVERIFIED for Ohio and Oregon specifically. I could not confirm Oregon's set-aside statute.]
- FCRA: if graph output is used for tenant screening, credit or employment decisions, the operator may be a consumer reporting agency. FCRA §605 (15 U.S.C. §1681c) limits reporting civil judgments older than 7 years. Stale and sealed records raise accuracy liability under §1681e(b). [UNVERIFIED, from general knowledge, not fetched this session.]
- The OCA NC (non-commercial) licence and the unlicensed GitHub repos (all rights reserved) are separate legal blockers from privacy.

### Gaps
- I found no repo with explicit court permission for bulk scraping.
- I did not verify Oregon or Ohio eviction sealing or set-aside rules.
