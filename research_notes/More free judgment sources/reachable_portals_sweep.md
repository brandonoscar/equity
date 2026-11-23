# Reachable-portal sweep: more free judgment, lien and charge datasets

Sweep date: 2026-11-22. Scope: only hosts this container can reach (data.ny.gov, data.cityofnewyork.us, data.ct.gov, data.colorado.gov, data.oregon.gov, data.iowa.gov, data.nola.gov, datacatalog.cookcountyil.gov, data.wprdc.org, phl.carto.com, ArcGIS Online). Everything in `arcgis_socrata_sweep.md`, `reports/More free judgment sources.md` and the brief's exclusion list was skipped.

Method:
- Socrata `/api/catalog/v1?q=<term>&domains=<host>` on 7 hosts, 40 terms (1,329 unique datasets), then 35 more targeted terms. Candidates were filtered by column names (money field plus name or parcel field) and by title keywords.
- WPRDC CKAN `package_search` (17 terms), then `datastore_search_sql` for counts and sums.
- Philadelphia Carto: guessed table names (system catalogs are forbidden).
- ArcGIS Online: 40 phrase searches not used in the earlier sweep, deduplicated against the earlier notes.

**[LIVE]** means the count or sum was fetched today with `$select=count(*)`, sum or group-by queries, or CKAN SQL. Socrata aggregates work again; the 503s seen in the earlier sweep are gone.

## Headline

- **No new large court-judgment feed is reachable.** The judgment-grade data on these hosts is already loaded (OATH, NYS warrants, NOLA, Allegheny liens). The one new court-judgment source is small. The NYC Law Department's civil-litigation table holds about 136 judgments the City won as plaintiff, plus a large set of foreclosure cases, keyed by BBL, that name the City as a defendant lienor.
- **DOB ECB Violations (`6bgk-3dad`) is fully covered by OATH.** 400 of 400 sampled ECB numbers with an open balance (200 from 2009, 200 from 2023 on) were found in OATH `jz4z-kudi` as `ticket_number = '0' + ecb_violation_number`. OATH already has block and lot. ECB adds only `bin`, `certification_status` and a second balance figure, so it is a cross-check, not a source.
- **The biggest new reachable layer is NYC charges that sit ahead of a judgment lien on the parcel.**
  - DOF Property Charges Balance: 189,647 BBLs with a past-due balance of $3.76B in the 2026-08-15 extract.
  - HPD emergency-repair charges (OMO, HWO, vacate relocation): 67,507, 30,375 and 736 BBLs.
  - These do not name a debtor. They join on BBL, so they belong in the equity netting, not in debtor discovery.
- **New on WPRDC:**
  - Allegheny County cumulative delinquent real-estate taxes: 541,929 bills on 58,112 parcels, about $92.4M.
  - City of Pittsburgh full tax-delinquency list: 26,329 parcels, $94.5M. This replaces the URA 3-plus-year copy (12,313) listed in the earlier sweep.
- **Dead ends:**
  - data.iowa.gov is no longer Socrata. Every API path returns a Next.js 404.
  - Philadelphia's `real_estate_tax_delinquencies` and `tax_delinquency` tables exist but return "permission denied".
  - Cook County publishes no current lien, judgment or tax-sale data. Its tax-sale tables stop in 2016 and its recorder tables in 2015.
  - CT, CO and OR have no new debtor-level money datasets. NYS publishes no WCB, DOL, AG or DEC penalty or judgment lists on data.ny.gov.

## Ranked table

Score = unpaid units × linkability.
- Linkability is 3 for name + parcel, 2 for parcel only and 1 for name only or an indirect join. Court judgments score ×1.5.
- Sources that duplicate loaded data are scored ×0.1 and marked **dup**.

| # | Dataset | Kind | Unpaid units | Unpaid $ | Name | Parcel | Paid/status | Last update | Tag |
|---|---|---|---|---|---|---|---|---|---|
| 1 | NYC DOF Property Charges Balance `scjx-j6np` | All DOF charges per BBL (tax, sundry, HPD/DOB charges) | 189,647 BBLs; 1,176,107 past-due rows | $3.758B | none | `parid` (BBL) | `sum_liab`/`sum_coll`/`sum_bal` | extract 2026-08-15 (quarterly) | [LIVE] |
| 2 | NYC HPD Open Market Order charges `mdbu-nrqn` + invoices `emrz-5p35` | Emergency-repair, AEP and demolition work billed to the property | 67,507 BBLs (497,561 OMOs) | $1.076B awarded; $891.9M invoice charges sent to DOF | none | `bbl`, `bin` | via `datetransferdof`; payoff only via #1 | daily (2026-11-22) | [LIVE] |
| 3 | Allegheny Co Cumulative Delinquent RE Taxes (WPRDC) | County RE tax delinquency (PA municipal claim) | 58,112 parcels / 541,929 bills | ~$92.4M | none | `parcel_id` | `total_payments`, `last_pay_date` | 2026-11-21 (daily) | [LIVE] |
| 4 | NOLA Adjudication Fines and Fees `f5zm-xkyr` | Itemized fees in in-rem code judgments | 92,287 cases / 189,061 unpaid fee rows | $86.8M | via join to `wy29-i338` | address only | `ispaid`, `d_paid` | 2026-11-22 | [LIVE] |
| 5 | NYC HPD Handyman Work Order charges `sbnd-xujn` | Emergency repair charges | 30,375 BBLs / 80,970 charges | $15.1M | none | `bbl` | `datetransferdof` | 2026-11-22 | [LIVE] |
| 6 | Pittsburgh Property Tax Delinquency (WPRDC) | City RE tax delinquency | 26,329 parcels | $94.5M | none (billing city) | `pin` | current vs prior years | 2026-11-19 | [LIVE] |
| 7 | NYC Law Dept Civil Litigation `pjgc-h7uv` | Court cases: City-plaintiff judgments + foreclosures naming the City | 136 City-plaintiff judgments; 12,384 Commercial/RE and 104,905 Tax & Bankruptcy cases with `lead_bbl` | $192.5M (judgments) | `matter_name` caption | `lead_bbl` (12,384 + 104,905) | `disposition`, `closed_date` | 2026-07-01 | [LIVE] |
| 8 | NYC DOB ECB Violations `6bgk-3dad` (**dup** of OATH) | ECB judgments (default / in violation) | 125,651 default/in-violation with balance (161,112 balance > 0) | $750.2M ($882.8M) | `respondent_name` | block/lot + `bin` | `hearing_status`, `ecb_violation_status`, `certification_status` | 2026-11-21 | [LIVE] |
| 9 | NYC DOF Tax Lien Sale Lists `9rz4-mjek` | Lien-sale notice lists (no amounts) | 2025 cycle: 29,972 (90-day) → 4,545 (final sale) | n/a | none | borough/block/lot | cycle stage, `water_debt_only` | 2025-12-01 | [LIVE] |
| 10 | NYC LL159 Vacate Relocation Charges `3bkg-usya` | Relocation charges that "become a tax lien" | 736 BBLs / 8,783 monthly rows | $27.75M | none | `bbl` | none | 2026-11-01 | [LIVE] |
| 11 | NYC BIC Issued Violations `upii-frjc` | Trade-waste violations adjudicated at OATH | 202 default/guilty unpaid (1,144 unpaid any status) | $2.07M ($7.96M) | `account_name` + address | `bbl` | `violation_disposition`, `date_fine_paid` | 2026-11-20 (quarterly) | [LIVE] |
| 12 | NYS Contractor Registry `i4jv-zkey` | DOL registry flags (no amounts) | 44 with outstanding wage assessments; 138 with a final labor or tax-law determination | n/a | `business_name`, `business_officers` + address | none | yes/no flags | 2026-11-22 | [LIVE] |

Below the cut (qualify only partly, or tiny):
- HPD Fee Charges `cp6j-7bjj` has 132,196 rows by BBL, but `feeamount` looks corrupted: values such as 2,692,970 for an inspection fee, and sums in the billions.
- Pittsburgh City Treasury Sales lists 96 parcels with `total_tax_due` plus demolition and clean-lien due.
- Allegheny Conservatorship Filings: 582 petitions with no amounts.
- Pittsburgh PLI violations now carry `docket_number` and `court_decision` (5,443 rows "Guilty") but no amounts.
- Oregon ODA pesticide/fertilizer violations `qbd4-4qzh`: 929 rows; `party`, text `amount`.
- NOLA Code Enforcement Abatements `xv8z-gn8b`: 7,240 rows with a judgment field and no amounts.

## Per-dataset details

### 1. NYC DOF Property Charges Balance [LIVE]
- Endpoint: `https://data.cityofnewyork.us/resource/scjx-j6np.json`. 136,838,310 rows in total, covering quarterly snapshots with `extractdt` from 2020-06-15 to 2026-08-15.
- Query used: `$where=extractdt='2026-08-15T00:00:00.000' AND sum_bal>0 AND due_date<'2026-08-15T00:00:00.000'`. It returns 189,647 distinct `parid`.
- Past-due balances by `code`:

  | Code | Rows | Past-due balance | Notes |
  |---|---|---|---|
  | CHG | 600,372 | $3,219.5M | Property tax charges |
  | SAC | 238,574 | $475.2M | 47,276 BBLs |
  | SAF | 204,981 | $49.0M | |
  | SAT | 125,074 | $14.4M | |
  | NSF | 6,307 | $0.15M | |
  | FPF, FSF, SIF | under 800 each | small | |

- Fields:
  - Parcel: `parid` (10-digit BBL), plus `id_block`/`id_lot`.
  - Amounts: `sum_liab`, `sum_coll`, `sum_int`, `sum_dsc`, `sum_bal`.
  - Dates: `due_date`, `dt_pd_begin`/`dt_pd_end`, `taxyear`.
  - Flags: `prior_owner_flag`, `city_owned_flag`, `int_agree` (installment agreement).
- No owner name. The join to the debtor is BBL → ACRIS/PLUTO.
- Legal effect: NYC property taxes and the sundry charges billed through DOF are liens on the parcel and are sold in the lien sale. The code meanings come from DOF's data dictionary, which was not fetched. Treat "SAC = sundry account charges, which include HPD/DOB emergency charges" as inferred.
- Use: net senior liens out of equity per BBL. The snapshot is large, so pull only the latest `extractdt`, filtered to `sum_bal>0`.

### 2. NYC HPD Open Market Order charges and invoices [LIVE]
- OMO endpoint: `https://data.cityofnewyork.us/resource/mdbu-nrqn.json`.
  - 517,619 rows; 497,561 with `omoawardamount > 0` ($1.076B) on 67,507 BBLs. Created 1999-05 to 2026-11-20.
  - Since 2020: 159,589 OMOs, $447.3M, 35,885 BBLs.
- Invoices endpoint: `https://data.cityofnewyork.us/resource/emrz-5p35.json`.
  - 797,571 rows; 727,293 with `chargeamount > 0` and `datetransferdof` set ($891.9M), transferred 2000-03 to 2026-11-09.
  - Since 2020: 194,342 charges, $344.3M.
  - Join to BBL through `omonumber` → `mdbu-nrqn.omonumber`.
- Fields: `omonumber`, `bbl`, `bin`, `block`, `lot`, `worktypegeneral`, `omostatusreason`, `omoawardamount`, `omocreatedate`, `isaep`, `iscommercialdemolition`. On invoices: `invoicestatus`, `invoicebillamount`, `invoicepayamount`, `chargeamount`, `datetransferdof`.
- Legal effect: the description says HPD does emergency repairs when an owner fails to correct a hazardous violation and bills the cost to the property. The charges reach DOF and become liens, the same mechanism as the HWO and LL159 sets. Payoff status lives only in #1.

### 3. Allegheny County Cumulative Delinquent Real Estate Taxes [LIVE]
- Endpoint: `https://data.wprdc.org/api/3/action/datastore_search_sql?sql=SELECT ... FROM "96e9d6b2-3e1a-4a0c-8ef6-23a049c263d8"`. Package `delinquent-real-estate-taxes`, which also has per-year resources for 2009–2025.
- 541,929 bills on 58,112 distinct parcels. Tax years 2009–2025; 2025 has 44,980 bills and 2024 has 39,679. `asof_date` 2026-11-21.
- Owed is about $92.4M, computed as `orig_bill + penalties + interest − total_payments`.
- Fields: `ar_id`, `year`, `parcel_id` (16-character Allegheny parcel id), `parcel_id_formatted`, `muni_name`, `school_district`, `orig_bill`, `penalties`, `interest`, `total_payments`, `last_pay_date`.
- No owner name. Join to owner through Allegheny Property Assessments on `parcel_id`.
- Overlap: the loaded "Allegheny tax liens" set is filed liens and satisfactions. This set is the receivable behind them and includes unliened delinquencies, so de-duplicate by parcel and year.

### 4. NOLA Adjudication Enforcement Fines and Fees [LIVE]
- Endpoint: `https://data.nola.gov/resource/f5zm-xkyr.json`.
- 225,395 fee rows, created 2000 to 2026-11-20.
  - Unpaid: 189,061 rows, $86.8M, on 92,287 incidents.
  - Paid: 36,334 rows, $20.1M.
- Largest unpaid types: One Time Fine $46.8M; Administrative $9.1M; Demolition $7.0M; Court Costs $5.6M; Daily Fines $4.0M; Grass Abatement $3.2M.
- Fields: `incident_number`, `codeincidid` (joins to `wy29-i338.codeincidid`, which carries `name`), `address`, `amount`, `type`, `ispaid`, `d_due`, `d_paid`, `o_c`. Coordinates are a placeholder (-101.5, 28.1), so use the address.
- Legal effect: this is the fee ledger behind the in-rem adjudication judgments already loaded. It adds per-fee paid flags and dates and shows that the case-level `UnpaidFees` total ($52.1M) understates the unpaid ledger ($86.8M). Load it as an enrichment of the existing NOLA node.

### 5. NYC HPD Handyman Work Order charges [LIVE]
- Endpoint: `https://data.cityofnewyork.us/resource/sbnd-xujn.json`.
- 100,097 rows; 80,970 with `chargeamount > 0` ($15.15M) on 30,375 BBLs. 79,405 of them were transferred to DOF. Created 2004-12 to 2026-10.
- Fields: `hwonumber`, `bbl`, `bin`, `block`, `lot`, `hwoapprovedamount`, `salestax`, `adminfee`, `chargeamount`, `datetransferdof`, `hwostatusreason`.

### 6. Pittsburgh Property Tax Delinquency [LIVE]
- Endpoint: `https://data.wprdc.org/api/3/action/datastore_search?resource_id=ed0d1550-c300-4114-865c-82dc7c23235b`.
- 26,329 parcels. Total `current_delq_tax + current_delq_pi + prior_delq_tax + prior_delq_pi` = $94.45M. Modified 2026-11-19.
- Fields: `pin`, `address`, `billing_city`, `current_delq_tax`, `current_delq_pi`, `prior_years`, `prior_delq_tax`, `prior_delq_pi`, `state_description`.
- Supersedes the URA `city_tax_delinquent_3yr` layer (rank 10 in the earlier sweep). Same caveat as before: possible overlap with the loaded Allegheny liens for city tax.

### 7. NYC Law Department Case-Related Civil Litigation [LIVE]
- Endpoint: `https://data.cityofnewyork.us/resource/pjgc-h7uv.json`. 547,358 cases, filed 1964 to 2025-06-30; updated 2026-07-01.
- Fields: `matter_name` (caption, e.g. "CITY OF NY VS FAITH MINISTRIES INC"), `docket_index`, `court_name`, `judge`, `ld_division`, `lit_start`, `closed_date`, `disposition`, `total_disposition_amt`, `total_city_received_amt`, `total_city_payout_amt`, `lead_bbl` (format `B-BBBBBB-LLLL`).
- Judgments: 10,768 rows have `disposition = 'Order/Judgment (Verdict)'`. Of the cases with `matter_name` starting "CITY OF", "NYC" or "PEOPLE", those judgments are:

  | Division | Judgments | Amount |
  |---|---|---|
  | Affirmative Litigation | 68 | $189.6M |
  | Administrative Law | 49 | $0.1M |
  | Commercial/RE | 19 | $2.8M |

  Human Rights Commission judgments (e.g. $220,900 against BKUK Corp) show up under the caption "HUMAN RIGHTS, COMMISSION ON, NYC VS ...".
- Foreclosure lead feed: 12,384 Commercial/RE cases with `lead_bbl` (filed 1977–2025; 646 still open; 824 filed since 2020) and most of 104,905 Tax & Bankruptcy rows with `lead_bbl`. They are mortgage foreclosures such as "DEUTSCHE BANK ... VS WILLIAMS, FRANK" in which the City is a defendant, presumably as a junior lienor (ECB, HPD or tax). Some Tax & Bankruptcy rows are certiorari cases.
- The defendant must be parsed from `matter_name` after "VS". There are no amounts on the foreclosure rows.
- Linkability is strong (BBL + caption), but this is a lis pendens–type signal that probably overlaps ACRIS LP documents.

### 8. NYC DOB ECB Violations (duplicate of OATH) [LIVE]
- Endpoint: `https://data.cityofnewyork.us/resource/6bgk-3dad.json`. 1,846,537 rows, issued 1988 to 2026-11-19.
- 161,112 rows with `balance_due > 0` ($882.8M) on 46,553 BINs; 159,723 of them were issued 2016 or later. By `hearing_status`:

  | Hearing status | Rows | Balance |
  |---|---|---|
  | DEFAULT | 72,115 | $580.7M |
  | IN VIOLATION | 53,536 | $169.4M |
  | PENDING | 23,376 | $80.6M |
  | STIPULATION/IN-VIO | 2,123 | $1.4M |

- By `ecb_violation_status`: ACTIVE 89,105 ($556.6M); RESOLVE 72,007 ($326.3M).
- Fields:
  - Ids: `ecb_violation_number`, `dob_violation_number`.
  - Respondent: `respondent_name`, `respondent_house_number`, `respondent_street`, `respondent_city`, `respondent_zip`.
  - Parcel: `boro`, `block`, `lot`, `bin`.
  - Money: `penality_imposed`, `amount_paid`, `balance_due`.
  - Dates and status: `issue_date`, `hearing_date`, `hearing_status`, `certification_status`.
- Overlap test: OATH `jz4z-kudi.ticket_number = '0' || ecb_violation_number`. 200 of 200 matched for a random 2009-era default/in-violation sample (OATH status: DOCKETED 169, HEARING COMPLETED 17, APPEAL DECIS RENDERD 8...). 200 of 200 matched for a 2023-plus sample (OATH NEW ISSUANCE 151, STIPULATION OFFERED 49).
- OATH already carries `violation_location_block_no`/`lot_no`. Use ECB only to add `bin` and `certification_status` and to cross-check `balance_due`.

### 9. NYC DOF Tax Lien Sale Lists [LIVE]
- Endpoint: `https://data.cityofnewyork.us/resource/9rz4-mjek.json`. 264,142 rows; last cycle 2025 (notices Feb–May 2025, final sale 2025-06).
- 2025 cycle: 90-day 29,972; 60-day 26,511; 30-day 21,546; 10-day 18,445; Final Sale 4,545.
- Fields: `month`, `cycle`, `borough`, `block`, `lot`, `tax_class_code`, `building_class`, `water_debt_only`. No amounts.
- Use as a flag: a parcel on the final-sale list carries a sold tax or water lien that ranks ahead of judgments.

### 10. NYC Local Law 159 Vacate Relocation Charges [LIVE]
- Endpoint: `https://data.cityofnewyork.us/resource/3bkg-usya.json`. 8,783 monthly rows, 736 BBLs, $27.75M `monthlyrelocationtotal`. Updated 2026-11-01.
- The description says these charges, "if not paid by the owner, become a tax lien against the property".
- Fields: `bbl`, `bin`, `vacateagency`, `vacatenumber`, `vacatereason`, `monthlyrelocationtotal`, `month`, `year`.

### 11. NYC BIC Issued Violations [LIVE]
- Endpoint: `https://data.cityofnewyork.us/resource/upii-frjc.json`. 18,567 rows, 4,786 account names, issued 2002 to 2026-11.
- Unpaid (`fine_amount > 0` and `date_fine_paid` null): Default-Granted 176 ($1.95M), Judgement-Guilty 26 ($0.13M), Calendared 498 ($4.16M), Settled or pending 343.
- Fields: `account_name`, `violation_account_address`/`city`/`postcode`, `bbl`, `bin`, `fine_amount`, `date_fine_paid`, `violation_disposition`.
- Adjudicated at OATH, so expect overlap with `jz4z-kudi`.

### 12. NYS Contractor Registry Certificate [LIVE]
- Endpoint: `https://data.ny.gov/resource/i4jv-zkey.json`. 15,314 active certificates.
- Flags:
  - `business_has_outstanding_wage_assessments = 'Yes'`: 44.
  - `business_has_final_determination_for_violation_of_labor_or_tax_law = 'Yes'`: 138.
  - Debarment fields are also present.
- Fields: `business_name`, `dba_name`, `business_officers`, `address`, `city`, `zip_code`. No amounts.
- Flag only. Join by name to NYS tax warrants or OATH.

## Host-by-host notes and dead ends

- **data.ny.gov:** no Workers' Compensation Board penalty or judgment lists, no DOL wage judgments, no Attorney General or DEC enforcement lists. The only debtor-level money sets are the already-loaded warrants. Also seen and rejected: Horse Racing Rulings `igam-2tkj` (fines on licensees), JCOPE enforcement `vsmx-hgi8` (stale 2018), `kdjh-dhwi` (utility aggregates).
- **data.cityofnewyork.us:** besides the above, rejected because they are plate-based, aggregate, or have no amount and no parcel:
  - DCWP Charges `5fn4-dr26`.
  - COIB Enforcement Fines `p39r-nm7f`: 1,420 rows, public servants.
  - CFB penalties `xrxs-qn95`, `x4w5-m7uh`: campaigns.
  - OLPS Enforcement Matters `c292-vzrn`: no employer name.
  - Open Parking and Camera Violations `nc67-uf89`: plate-based.
  - City Marshals Revenue `7ewi-9cdf`: aggregate per marshal.
  - DOF Open Balance Summary `paab-n3s5`: stale 2019.
- **data.ct.gov:** DEEP formal enforcement 1999–2021 `tvbr-6b6t` (2,070 rows, no amounts) and UST Enforcement `sfgx-68fy` (8,927 rows, client name, no amounts). `t2bf-45ba` is already in the report.
- **data.colorado.gov:** only the UCC set (already loaded) and 2016 foreclosure aggregates.
- **data.oregon.gov:** campaign-finance penalty notices `fku5-vh2b` (committees), OSHA annual aggregates `xc4e-hg3n`, ODA pesticide violations `qbd4-4qzh` (929 rows). No BOLI wage-claim dataset.
- **data.iowa.gov:** the portal has been replaced by a Next.js site, and `/api/catalog/v1`, `/api/views.json` and CKAN paths all return 404. The Iowa DNR lien table remains unreachable.
- **data.nola.gov:** new are the fee ledger `f5zm-xkyr` (#4) and Abatements `xv8z-gn8b` (no amounts). Sheriff Sales `d52w-8nva` is still stale (2018).
- **datacatalog.cookcountyil.gov:** current tables are Assessor and court-sentencing data only. The Treasurer annual and scavenger tax sale tables (`55ju-2fs9`, `ydgz-vkrp`) stop in 2016; the Recorder foreclosure and mortgage tables stop in 2015. Human Rights decisions `b5sv-ucke` have no amounts.
- **data.wprdc.org:**
  - Sheriff Sales stopped at 2022-12.
  - Mortgage foreclosure records and tax liens are already loaded.
  - Conservatorship (582) and PLI violations (`court_decision`, `docket_number`; no amounts) are noted above.
  - PWSA publishes infrastructure only, with no lien data.
- **phl.carto.com:** reachable tables with any money field are `real_estate_tax_balances` (already reported, stale) and `rtt_summary` (already loaded). `violations` (2,043,753), `li_violations`, `case_investigations`, `li_clean_seal`, `li_demolitions`, `appeals` and `li_court_appeals` carry owner and OPA account but no amounts. `real_estate_tax_delinquencies` and `tax_delinquency` exist but are permission-denied, and no water-revenue lien table was found.
- **ArcGIS Online:** 40 new phrase searches ("judgment lien", "abstract of judgment", "small claims", "uninsured employer", "restitution", "weed lien", "demolition lien", "lis pendens", "writ of execution" and others) found nothing new of size. Longview/Gregg Co TX "Lien Property" has 18, 26 and 2 parcels with names but no amounts. Camden NJ tax liens have owners redacted.

## Suggested next steps

1. Load #1 (latest extract only) and #2/#5/#10 keyed on BBL as senior-lien deductions in the NYC equity calculation. Use #1's SAC balance to tell whether the HPD charges are still unpaid.
2. Add #4 to the NOLA node and #3/#6 to the Allegheny node, de-duplicating against the loaded lien filings.
3. Parse `pjgc-h7uv` captions for the ~136 City-plaintiff judgments, and keep the BBL foreclosure cases as a "City named as junior lienor" flag.
4. Skip ECB as a source. If needed, join it to OATH on `'0'||ecb_violation_number` to add `bin`.
