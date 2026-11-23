# ArcGIS Online and Socrata sweep: more free judgment and lien datasets

Sweep date: 2026-11-22. Method: ArcGIS Online search API (about 90 terms, `type:"Feature Service"`, paged up to 400 results each, about 9,350 unique items). Every item whose title matched a money or lien keyword was probed automatically: service JSON, layer fields, and a row count when the layer had an amount-like field plus a name-like or parcel-like field (about 5,300 layers probed, 1,270 counted). The Socrata discovery catalog was queried through the Cook County proxy (`datacatalog.cookcountyil.gov/api/catalog/v1`, 50 terms, about 2,860 unique datasets). Shortlisted layers were then pulled directly for samples, status breakdowns and sums.

Everything tagged **[LIVE]** was fetched from the publisher's FeatureServer or Socrata host in this session. Counts, sums and status values come from `returnCountOnly` and `outStatistics` queries run today. "Edit" is the layer's `editingInfo.lastEditDate`.

Excluded as already loaded or already reported: Detroit blight_tickets (and its DEGC copies `Blight_Tickets_Table`, `Blight_Tickets_In_Collections*`), Louisville final orders and foreclosures, Miami-Dade CodeComplianceViolation_Lien_View, NOLA, Baltimore tax lien certificate sale, LA defaulted roll, Maricopa `DelinquentTax` (it now has a `Master_List` table with `TOTALDUE` and `TFCDE='JUD'`; see the note at the end), Allegheny, Philadelphia, NYC OATH and HPD litigation, and the rest of the brief's list.

## Headline

- **Real court money judgments that name a debtor and a parcel:**
  - **Harris County TX tax-suit judgments** ("Venue Unsold PJ Accounts"): 1,934 judgments, $42.2M, with defendant, cause number, judgment date and status, including `JUDGMENT PAID` and `ABSTRACT OF JUDGMENT`.
  - **Washington County PA sheriff sales:** 948 mortgage and other foreclosure judgments, $146M. Each row gives the full "Plaintiff Vs Defendant" caption, the docket and the parcel.
  - **Harris County delinquent accounts 2025:** 52,863 named and parcel-keyed accounts. 6,121 of them carry a tax-suit cause number, and about 2,025 are in judgment status.
- **Biggest new municipal lien feed:** Baltimore City **Environmental Citations**. 96,262 open citations carry a $71.5M balance, are keyed to block/lot, and include a lien code (`L` on 73,047 of the open ones). It is updated daily.
- **Socrata via the Cook County proxy:** the catalog works and finds good datasets: Chicago DOAH ordinance violations, Chicago vacant-building fines, Mesa code-compliance balances, Vermont top delinquent taxpayers, WA PDC enforcement balances, Sonoma defaulted taxes and Clermont OH taxes due. But **every Socrata data host except data.cityofnewyork.us refused the connection** (curl status 000). The two new NYC items are HPD Handyman Work Order charges and DOF Property Charges Balance.
- There are 30 qualifying ArcGIS datasets across 14 states (TX, MD, PA, CA, OH, VA, AZ, NC, MS, FL, CO, KY, IN, KS), plus 2 NYC Socrata datasets. Most are tax or code liens keyed to a parcel. Only the Harris and Washington County PA layers are true court judgments.

## Ranked table

Score = unpaid rows × linkability. Linkability is 3 for name + parcel, 2 for parcel only and 1 for name only, with a bonus where a court judgment or a recorded lien is explicit.

| # | Dataset (state) | Kind | Unpaid rows / total | Unpaid $ | Name | Parcel | Paid/status | Edit | Tag |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Harris Co TX Delinquent Parcels 2025 | Tax delinquency; 6,121 in suit, ~2,025 judgment | 52,863 / 52,863 | $60.1M levy due | owner_name_1..3, OWNERNAME1..4 | HCAD_NUM / acct_num | LEGALSTATUS (A,J,B,F,SO), CAUSENO, BANKRUPTNO | 2026-06-12 | [LIVE] |
| 2 | Baltimore City Environmental Citations (ECB) (MD) | Code citation fines, lien-coded | 96,262 / 159,682 | $71.5M | none | Block + Lot | CitationStatus O/P/V/A, LienCode L/N, TotalPaid | 2026-11-22 | [LIVE] |
| 3 | Harris Co TX Unsold PJ (post-judgment) tax-suit accounts | **Court judgment** (tax suit) | 1,934 (88 paid) | $46.2M current; $42.2M judgment | Defendant, owner_name_1 | HCAD_NUM | Litigation_Status | 2026-06-17 | [LIVE] |
| 4 | Washington Co PA Sheriff Sales | **Court judgment** (foreclosure and other writs) | 948 judgments (64 active) | $146.0M | title = "Plaintiff Vs Defendant" | parcels1..15 | activeStatus, stayed_status | 2026-11-18 | [LIVE] |
| 5 | Mahoning Co / Youngstown OH Tax Delinquent & Land Bank Eligible | Tax delinquency | 15,983 | $36.8M | DeededOwner, TaxpName | ParcelID | TaxesPaid, Delinquent | 2026-11-12 | [LIVE] |
| 6 | Virginia Beach VA Delinquent Real Estate Taxes | Tax delinquency (VA lien) | 13,708 bills | $15.5M | Owner_Name | GPIN | per-bill, years 2012–2026 | 2026-11-22 | [LIVE] |
| 7 | Buncombe Co NC Unpaid Property Bills (one layer per levy year, 2013–2026) | Tax delinquency (NC lien) | ~31,200 prior-year + 85,219 levy-2026 | n/a (amounts stored as text) | owner1/owner2 last/first | pin | per bill; active_flag | 2026-11-22 | [LIVE] |
| 8 | Cochise Co AZ Tax Lien Parcels + 2026 Tax Lien Auction | Tax lien certificates | 11,090 + 4,093 | $14.5M (purchasetotal) | fullname / NameOfOwner | apn | foreclosureyear | 2026-11-22 / 2026-01-16 | [LIVE] |
| 9 | Guilford Co NC Tax Delinquent Report | Tax delinquency | 8,110 | $7.69M | OWNER_NAME + mail address | PARCEL_NUM | BILL_STATUS = UNPAID | 2026-11-22 | [LIVE] |
| 10 | Pittsburgh city taxes 3+ years delinquent (URA) | Tax delinquency | 12,313 | $65.0M | none (billing city only) | pin, mapblocklo | prior_years | 2026-11-22 | [LIVE] |
| 11 | LA County Unsecured Tax Roll Billing (CA) | Unsecured property tax (lien when certificate recorded) | 100,921 / 443,406 | $291.1M | none | Parcel_Number | Amount_Paid, Balance_Due | 2026-11-21 | [LIVE] |
| 12 | Harrison Co MS 2025 Delinquent Parcel Auctions | Tax sale (MS lien) | 6,224 | $8.92M | Owner, ownerCalc | PARCEL_ID | Prior_Lienholder_1/2 | 2026-07-19 | [LIVE] |
| 13 | Lee Co FL Nuisance Accumulation Violations | Code enforcement; 1,301 "Lien Recorded" | 1,407 balance > 0 / 94,294 | $6.36M | none | parcel_number (STRAP) | record_status (Lien Recorded, Closed-Satisfied, Closed-Released...) | 2026-11-22 | [LIVE] |
| 14 | Miami-Dade Waste Collection Delinquent Accounts in Court Judgement Process (FL) | Solid-waste fee judgments | 1,393 with fees / 27,186 | n/a (amounts stored as text) | OWNER | FOLIO_NUMBER | none | 2026-11-22 | [LIVE] |
| 15 | Tucson AZ Recorder Liens (code enforcement) + Code Enforcement Invoices | Recorded code liens | 517 + 603 unpaid | $1.20M (liens) | Customer_1..4 | address only | Payment_Status, Release_* | 2026-07-08 | [LIVE] |
| 16 | Douglas Co CO Tax Liens | Tax lien certificates | 1,395 | $5.58M | none | account_id | lien_type, sale date | 2026-11-22 | [LIVE] |
| 17 | Broward Co FL Local Business Tax (RTT) | Business tax receipts | 13,543 unpaid / 77,625 | $1.01M | Owner_Name, Business_Name | FOLIO | Balance_Status Paid In Full / Unpaid | 2026-11-17 | [LIVE] |
| 18 | Raleigh NC Active Special Assessments | Special-assessment liens | 865 | $4.26M | none | REID, NCPIN | StatusCode | 2026 (AccountDate ≤ 2022) | [LIVE] |
| 19 | Hopkinsville KY Lien Property (2026) | Delinquent tax / lien list | 509 | $4.47M | Name + mailing address | PARCEL_ID, Account | Year | 2026-03-13 | [LIVE] |
| 20 | Yavapai Co AZ Tax Sale (2025 levy) | Tax lien sale | 2,602 | n/a (text) | NAME | ParNumAsr | none | 2026-10-19 | [LIVE] |
| 21 | Delaware Co IN (Muncie) Fall Tax Sale 2025 / 2026 (+ results) | Tax sale; IN tax-sale judgment cause numbers | 632 + 630 | Minimum_Bid | Owner_Name | State_PIN | Sale_Result; results layers | 2026-10-13 / 2026-11-05 | [LIVE] |
| 22 | St Joseph Co IN Tax Sale Properties 2026 | Tax sale | 1,266 | Minimum_Bi | NAME_1 | PARCELID, state PIN | none | 2026-08-05 | [LIVE] |
| 23 | NYC HPD Handyman Work Order Charges (Socrata `sbnd-xujn`) | Emergency-repair charges billed to the property | 100,096 rows | chargeamount (max $13.9k) | none | bbl | n/a | rows updated 2026-11 | [LIVE sample; aggregates 503] |
| 24 | NYC DOF Property Charges Balance (Socrata `scjx-j6np`) | All DOF property charges per BBL, quarterly | 109.7M snapshot rows | sum_bal | none | parid (BBL) | sum_coll, sum_bal | extract 2025-08-16 | [LIVE sample] |
| 25 | Saguache Co CO 2026 Tax Sale | Tax lien sale | 900 | Total_Due | TaxSale_Owner | TaxSale_Parcel | none | 2026-09-22 | [LIVE] |
| 26 | Lake Co CO 2026 Delinquent Tax Lien Sales | Tax lien sale | 370 | CUR_BAL / LST_BAL | Owner_Name | PARCELNB | none | 2026-10-08 | [LIVE] |
| 27 | Summit Co OH Tax Delinquent ≥ $10k | Tax delinquency | 3,812 | DELINQUENT_DUE | OWNER_1, OWNER_2 | PARCEL | CERTIFIED_DELQ_YR | 2025-08-06 | [LIVE] |
| 28 | Medina Co OH Delinquent Parcels | Tax delinquency | 454 | Delinquent | Owner | ParcelPIN | PaidThisYear, Contract | 2026-11-22 | [LIVE] |
| 29 | Cuyahoga Co OH Delinquency Update Table | Tax delinquency | 29,157 | total_net_delq_balance | none | parcel_id | total_net_delq_paid | 2025-04-17 | [LIVE] |
| 30 | Kalamazoo Co MI Forfeited Parcels (3/1/26) | Tax forfeiture | 289 | TAX | ONERNAME1 | PELNUMBER | n/a | 2026-03-24 | [LIVE] |
| 31 | Hot Springs AR Housing Liens / Housing Lien Parcels | City liens (vacant/weedy lot etc.) | 257 (2026) / 763 (2024) | Amount | none | RPID | Type_of_Lien, Date_of_Lien | 2026-10-05 | [LIVE] |
| 32 | El Dorado KS Special Assessments | Special assessments | 839 | TotalAmount, TotalDue1..n | none | PID | yearly payoff | 2026-10-05 | [LIVE] |

## Per-dataset details

### 1. Harris County TX: Delinquent Parcels 2025 [LIVE]
- URL: https://services.arcgis.com/su8ic9KbA7PYVxPS/arcgis/rest/services/Delinquent_Parcels_2025/FeatureServer/0 (points). Layer 3 holds the same data as polygons.
- Owner account `melvicdegracia`. The description reads "Official Dataset ... Data as of 04/04/2026, GIS Division, 13013 Northwest Fwy, Houston" (the HCAD address). Edited 2026-06-12.
- Rows: 52,863, all for TAXYEAR 2025 and all with LEVYDUE > 0. Total LEVYDUE is $60,144,722.
- Fields:
  - Debtor: `owner_name_1..3` (HCAD) and `OWNERNAME1..4` (tax office), with mailing address.
  - Parcel: `HCAD_NUM`, `acct_num`.
  - Amounts: `BASELEVY`, `LEVYPAID`, `LEVYDUE`, `AMOUNT`, `DUEDATE`.
  - Legal: `LEGALSTATUS`, `CAUSENO` (tax-suit cause number, present on 6,121 rows), `BANKRUPTNO`, `TAXDEFSTRT/END` (deferral).
- LEGALSTATUS counts: A 4,022; J 1,955; B 197; F 44; A,J 38; B,J 21; SO 15; F,J 10. J most likely means judgment, A attorney/suit, B bankruptcy and SO struck off; the codes are inferred, not documented.
- Note: this is one tax year's levy, not the full delinquent balance. The rows with a cause number point to Harris County district-court tax suits.

### 2. Baltimore City MD: Environmental Citations [LIVE]
- URL: https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services/ECB_OB/FeatureServer/0
- Owner `baltimore_city`. Edited 2026-11-22, daily.
- Rows: 159,682. Violation dates run from 2004 to 2026-11, with 99,764 since 2024-01-01.
- Open: 96,262 citations with Balance > 0, totalling $71,508,916. 73,047 of the open ones are LienCode `L`.
- Fields: `CitationNo`, `LienCode` (L 132,799 / N 26,883), `ViolationDate`, `DueDate`, `Agency` (DHCD 153,053; Health 5,332; DPW 1,019...), `FineAmount`, `Balance`, `TotalPaid`, `TotalAbated`, `TotalVoided`, `LastPaidDate`, `HearingDate`, `HearingStatus`, `CitationStatus` (O 96,251; P 56,243; V 5,138; A 2,050), `ViolationLocation`, `Block`, `Lot`.
- Debtor name: none. The respondent is not published, so the join to the owner runs through Block/Lot and SDAT.
- Legal effect: not stated in the layer. `LienCode` suggests the Environmental Control Board fine is lienable against the property. Verify the Baltimore City Code (Art. 1, Environmental Control Board) before relying on it.
- Sister layers in the same org are parking and moving citations (11.3M rows, `Finance_Parking_Fines`). They are vehicle debts, not parcel debts, so they are skipped.

### 3. Harris County TX: Unsold Post-Judgment Tax-Suit Accounts [LIVE]
- URL: https://services5.arcgis.com/GtNPpPrhcOMhYgh4/arcgis/rest/services/Tax_Delinquent_Parcels/FeatureServer/1 ("Harris Venue Unsold PJ Accounts V5 Parcels"; the item is titled "Harris County Tax Delinquent Parcel Boundaries")
- Owner `paul.suckow_HCCSD`. Description: "tax-delinquent properties were forwarded from the Tax Office. Data as of 06/01/2026". Edited 2026-06-17.
- Rows: 1,934, all with Judgment_Amount > 0. Judgment_Amount totals $42,208,445 and Current_Amount $46,180,580. Judgment_Date runs from 2006-08-30 to 2026-04-17.
- Fields: `Cause_Number`, `Defendant`, `Judgment_Amount`, `Judgment_Juris_Breakout`, `Judgment_Start_Year`/`End_Year`, `Judgment_Date`, `Current_Amount`, `Litigation_Status`, `Category`, `Active/Paid/Defaulted_PPA_Count` (payment plans), `Sale_Memo`, plus HCAD owner, mailing address and `HCAD_NUM`.
- Litigation_Status counts:

  | Status | Rows |
  |---|---|
  | HOLD ON FILE | 1,375 |
  | ABSTRACT OF JUDGMENT | 107 |
  | JUDGMENT PAID | 88 |
  | JUDGMENT ENTERED | 86 |
  | JUDGMENT ENTERED, SUBSEQUENT YEARS DUE | 85 |
  | SET FOR SALE | 62 |
  | READY FOR SALE | 44 |
  | PROJECTED FOR SALE | 25 |
  | NEEDS NUNC PRO TUNC | 20 |
  | STRUCK OFF | 7 |
  | STRUCK OFF TO OTHER | 8 |

- Category counts: Payment Agreement 607; Current Taxes Not Under Contract 365; Over 65 / Deferral 233; Bankruptcy 15.
- Legal effect: Texas tax-suit judgments foreclose the tax lien. "Abstract of judgment" rows add a judgment lien. These are the only free, parcel-keyed Texas court judgments found.

### 4. Washington County PA: Sheriff Sale Data [LIVE]
- URL: https://services2.arcgis.com/LgK9DpUhNjdU0HLy/arcgis/rest/services/SheriffsSaleData/FeatureServer/1
- Owner `jursachr_washco`. Edited 2026-11-18. Sale dates run from 2022-02 to 2027-02.
- Rows: 949. 948 carry a judgment, totalling $146,044,035. activeStatus is active for 64 and inactive for 883.
- Fields: `docket` (Common Pleas number, e.g. 2015-7355), `title` (full caption, e.g. "First Federal Savings And Loan ... Vs Joy L. Daviduk"), `judgement`, `parcels1..15`, `location_address`, `location_municipality`, `attorney`, `sale_date`, `stayed_status` (Stayed 362, Continued 161, Purchased by Plaintiff 10, 3rd party sale 11...), `handbill_link`, `costsheet_Link`.
- Debtor: the defendant is parsed from `title` after "Vs". The parcel is in `parcels1`.
- Legal effect: these are in-rem and in-personam judgments being executed by sheriff sale. The amount is the judgment amount on the writ.

### 5. Mahoning County OH: Tax Delinquent and Land Bank Eligible Properties [LIVE]
- URL: https://services7.arcgis.com/BdxVWim3RqQp6zGH/arcgis/rest/services/Tax_Delinquent_and_Land_Bank_Eligible_Properties/FeatureServer/3
- Owner `GIS_Man_Development` (Youngstown). Edited 2026-11-12.
- Rows: 15,983, all with Delinquent > 0, totalling $36,841,645.
- Fields: `ParcelID`, `DeededOwner`, `TaxpName`, owner and taxpayer address, `AnnualTax`, `TaxesPaid`, `Delinquent`, `SpecAssessment`, `CodeViolation`, `VacantType`, market values.

### 6. Virginia Beach VA: Delinquent Real Estate Taxes [LIVE]
- URL: https://services2.arcgis.com/CyVvlIiUfRBmMQuu/arcgis/rest/services/Delinquent_Real_Estate_Taxes_view/FeatureServer/0
- Owner `VBCGIS_OrgAcct1`. Edited 2026-11-22.
- Rows: 13,708 bill installments, totalling $15,519,843. Tax years run from 2012 to 2026 (2026: 4,276; 2025: 2,258; 2024: 1,411).
- Fields: `Owner_Name`, `Mailing_Address`, `GPIN`, `Situs_Address`, `Tax_Year`, `Bill_Number`, `Installment`, `Tax_Due`, `Penalty_Due`, `Interest_Due`, `Fee_Due`, `Total_Delinquent_Amount_Due`.
- Legal effect: Virginia real-estate taxes are a lien on the parcel (Va. Code 58.1-3340).

### 7. Buncombe County NC: Unpaid Property Bills, one layer per levy year [LIVE]
- Example URL: https://services6.arcgis.com/VLA0ImJ33zhtGEaP/arcgis/rest/services/Unpaid%20Property%20Bills%20from%202026/FeatureServer/0. Sister layers are named "Unpaid Property Bills from 20xx".
- Owner `GISAdminBC`. All layers edited 2026-11-22.
- Row counts by levy year:

  | Levy year | Rows |
  |---|---|
  | 2026 (current year, not yet delinquent) | 85,219 |
  | 2025 | 7,268 |
  | 2024 | 6,086 |
  | 2023 | 4,763 |
  | 2022 | 4,122 |
  | 2021 | 3,248 |
  | 2020 | 3,099 |
  | 2019 | 877 |
  | 2018 | 533 |
  | 2017 | 280 |
  | 2014 | 206 |
  | 2016 | 181 |
  | 2015 | 125 |
  | 2013 | 411 |

- Fields: `bill`, `owner1_*`, `owner2_*`, mailing address, `pin`, `deed_book`/`deed_page`, `mortgage_co`, `loan_num`, `real_value`, `personal_value`, `original_bill_amount`, `tax_due`, `interest_due`, `cost_due`, `fees_due`, `total_due`.
- Caveats: amounts are stored as text, so the server cannot sum them; sum them client-side. Personal-property bills are mixed in; filter on `real_value > 0` (66,652 rows in 2026).

### 8. Cochise County AZ: Tax Lien Parcels and 2026 Tax Lien Auction [LIVE]
- Lien parcels: https://services6.arcgis.com/Yxem0VOcqSy8T6TE/arcgis/rest/services/Cad_TaxLienParcel/FeatureServer/0
  - 11,090 rows, edited 2026-11-22. `purchasetotal` sums to $14,512,416.
  - Fields: `apn`, `fullname`, `legaldesc`, `purchasetotal`, `foreclosureyear` (2012–2029; the year the certificate becomes foreclosable).
- Auction list: https://services6.arcgis.com/Yxem0VOcqSy8T6TE/arcgis/rest/services/TaxLienAuctionParcel_2026/FeatureServer/0
  - 4,093 rows. Fields: `NameOfOwner`, `AmtDue`, `GisApn`, `situs_address`, `fcv`.
  - Description: "available Tax Lien Auction Parcels ... 2026 Cochise County Tax Lien Auction".

### 9. Guilford County NC: Tax Delinquent Report [LIVE]
- URL: https://services5.arcgis.com/RR1v7NWFfwk98pUn/arcgis/rest/services/Tax_Delinquent_Report_/FeatureServer/0
- Owner `GuilfordCountyGIS`. Edited 2026-11-22.
- Rows: 8,110, all BILL_STATUS = UNPAID, totalling $7,687,913. Tax years run from 2016 to 2025 (2025: 2,430).
- Fields: `PARCEL_NUM`, `OWNER_NAME`, `MAIL_*`, `TAX_YEAR`, `BILL_AMOUNT`, `BILL_DUE_AMT`, `INTEREST_DUE`, `TOTAL_DUE_AMOUNT`, `BILL_DUE_DATE`.

### 10. Pittsburgh PA: City Tax Delinquent 3+ Years [LIVE]
- URL: https://services1.arcgis.com/0DMNBNaacQNEfN4H/arcgis/rest/services/city_tax_delinquent_3yr/FeatureServer/0
- Owner `gis_urap` (Urban Redevelopment Authority). Edited 2026-11-22.
- Rows: 12,313, with `total_owed` summing to $65,044,042.
- Fields: `pin`, `mapblocklo`, `address`, `billing_city`, `current_delq`, `prior_years`, `prior_delq_tax`, `total_owed`.
- No owner name. This is city real-estate tax, which may overlap the already-loaded Allegheny tax liens; check before loading.
- An older URA copy, `City_Tax_Delinquent_3_Plus_Years` (11,423 rows, 2025-06), also exists.

### 11. LA County: TTC Unsecured Tax Roll Billing and Secured Tax Roll [LIVE]
- Unsecured: https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/Unsecured%20Tax%20Roll%20Billing/FeatureServer/0
  - 443,406 rows for roll years 2025 and 2026. 100,921 have Balance_Due > 0, totalling $291,123,272.
  - Fields: `Bill_Number`, `Parcel_Number`, `Tax_Due`, `Penalty`, `Additional_Penalty`, `Total_Due`, `Amount_Paid`, `Balance_Due`, `Delinquency_Date`, situs.
  - Many rows are supplemental bills on a parcel. Unsecured taxes become a lien on the assessee's property only when the county records a certificate of tax lien.
- Secured: https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/Secured%20Tax%20Roll/FeatureServer/0
  - 2,538,917 rows, edited 2026-11-16. 2,251,832 have TOTAL_TAX_DUE > 0, but those are current-year bills. YEAR_TAX_DEFAULTED ≠ '00' on only 3,143 rows.
  - This duplicates the defaulted roll already loaded. Use it only for the current-year balance.
- Special-assessment direct-charge liens: `Liens Secured Tax Roll`, 2,427,192 rows (already noted in the report).
- No owner names in any of these layers.

### 12. Harrison County MS: 2025 Delinquent Parcel Auctions [LIVE]
- URL: https://services3.arcgis.com/giRjiTL1UH17pAvy/arcgis/rest/services/MSGCHrsnCntyDelinquentParcelAuctions2025Official/FeatureServer/0
- Owner `c_hymel`. Edited 2026-07-19.
- Rows: 6,224, with `Face_Value_Owed` summing to $8,917,627.
- Fields: `PARCEL_ID`, `Owner`, `Address_1..6`, `Prior_Lienholder_1/2`, `Face_Value_Owed`, true and assessed values.
- A smaller sister layer, `MSGCDelinquentParcels` (168 rows), also exists.

### 13. Lee County FL: Nuisance Accumulation Violations [LIVE]
- URL: https://services2.arcgis.com/LvWGAAhHwbCJ2GMP/arcgis/rest/services/NuisanceAccumulationViolations/FeatureServer/0
- Owner `LeeCountyFLGIS`. Edited 2026-11-22. File dates run from 2005 to 2026-11.
- Rows: 94,294. 1,407 have balance_due > 0, totalling $6,355,482.
- record_status counts:

  | Status | Rows |
  |---|---|
  | Closed-Conversion | 70,356 |
  | Closed-Owner Abated | 19,850 |
  | Lien Recorded | 1,301 |
  | Closed-Satisfied | 836 |
  | Closed-Ownership Change | 430 |
  | Closed-Released | 421 |
  | In Violation | 410 |
  | Certified Notice Sent | 91 |
  | Closed-Costs Paid | 77 |
  | Hearing Scheduled | 42 |
  | Closed-Paid | 25 |

- Fields: `record_number`, `parcel_number` (STRAP), situs address, `daily_fine`, `start_fine_date`, `end_fine_date`, `total_fees_amount`, `balance_due`, `record_status_date`.
- Legal effect: a recorded Florida code-enforcement fine order is a lien on the land (Fla. Stat. 162.09(3)). The satisfied and released statuses give a satisfaction signal. No owner name, so join through the Lee Property Appraiser STRAP.

### 14. Miami-Dade FL: Waste Collection System Delinquent Accounts in Court Judgement Process [LIVE]
- URL: https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/data_judgement/FeatureServer/0
- This clarifies the unknown purpose of the `data_judgement` layer flagged in the earlier report.
- Rows: 27,186 (Household 20,621; Commercial 6,565). 1,393 have nonzero TOTAL_FEES and 1,381 have nonzero JUDGEMENT_FEES. Amounts are stored as text.
- Fields: `ACCOUNT_NO`, `OWNER`, `FOLIO_NUMBER`, `PROPERTY_ADDRESS`, `PARCEL_DATE`, `ATTORNEY_FEES`, `FILING_FEES`, `JUDGEMENT_FEES`, `MASTER_FEES`, `INTEREST_FEES`, `TOTAL_FEES`.
- Sister layer: `data_complaints`, 166,087 enforcement complaints with CITATION_AMOUNT.

### 15. Tucson AZ: Recorder Liens and Code Enforcement Invoices [LIVE]
- Recorder liens: https://services3.arcgis.com/9coHY2fvuFjG9HQX/arcgis/rest/services/Recorder_Liens_May_2019_2024/FeatureServer/0
  - 517 rows, all Payment_Status = Unpaid and Invoice_Type = Code Enforcement. Amount_Due totals $1,203,655. Lien_Recording_Date runs from 2019-05 to 2024-06. Edited 2026-07-08.
  - Fields: `Lien_Sequence_Number` (Pima Recorder sequence), `Customer_1..4`, `Address`, `Invoice_Date`, `Lien_Recording_Date`, `Amount_Due`, `Lien_URL`.
- Invoices: https://services3.arcgis.com/9coHY2fvuFjG9HQX/arcgis/rest/services/WD_Code_Enfrcmnt_Invoices_June_2022_Feb_2024/FeatureServer/0
  - 603 rows. Adds `Collection_Code` ("Lien Placed"), `Release_Sequence_Number`, `Release_Recording_Date` (a satisfaction signal) and `Invoice_Amount`.

### 16–32. Smaller qualifying datasets [LIVE]

**16. Douglas County CO tax liens**
- URL: https://services.arcgis.com/seTexOicoRXDvRsJ/arcgis/rest/services/OpenData/FeatureServer/2
- 1,395 liens totalling $5.58M: Investor Held 1,239, County 156.
- Fields: `account_id`, `lien_id`, `lien_balance`, `sale_or_purchase_date`, `subsequent_tax_year_n_balance`. No name.
- Sister layer: `Tax_Sale_List_Locations` (896 rows).

**17. Broward County FL local business tax (RTT)**
- URL: https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/Broward_RTT_Business/FeatureServer/0
- Year 2025: 64,082 Paid In Full and 13,543 Unpaid; unpaid balances total $1.01M.
- Fields: `Owner_Name`, `Business_Name`, `FOLIO`, `Balance_Status`.
- This is a business tax, not a real-property lien.

**18. Raleigh NC active special assessments**
- URL: https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/Active_Assessments/FeatureServer/0
- 865 rows, `TotalLienAmount` $4.26M, keyed by `REID`/`NCPIN`.
- Sister layer: `Paid_Assessments` (the satisfaction side).

**19. Hopkinsville KY lien property**
- URL: https://services9.arcgis.com/IQlUcmqslgffs5GD/arcgis/rest/services/LienProperty/FeatureServer/0
- 509 rows for 2026, `Amount_Due` $4.47M, with name, mailing address and `PARCEL_ID`.
- The lien type is not documented; it is likely delinquent city tax.
- Sister layer: `Vac_Liens` (300 rows, 2024).

**20. Yavapai County AZ tax sale**
- URL: https://services1.arcgis.com/BajuNXbtZNiBKFkx/arcgis/rest/services/Tax_Sale_map_Manual_Load_for_Tax_Sale/FeatureServer/0
- 2,602 parcels for tax year 2025, with `NAME`, `ParNumAsr` and `Amount` (text).

**21. Delaware County IN (Muncie) tax sales**
- 2025: https://services.arcgis.com/VyRjdyMziYNF5Bwe/arcgis/rest/services/Fall_Tax_Sale_2025/FeatureServer/0. Fields: `USER_Cause_Number` (e.g. 18C05-2509-TS-000198, the tax-sale judgment cause), `USER_Owner_Name`, `USER_State_PIN`, `USER_Minimum_Bid`. `USER_Judgment_Amount` is empty in the samples.
- 2026: https://services.arcgis.com/VyRjdyMziYNF5Bwe/arcgis/rest/services/Fall_Tax_Sale_2026/FeatureServer/0 (632 rows).
- 2026 with tax bills: https://services6.arcgis.com/eVA2BCtRxhBWjuqd/arcgis/rest/services/Muncie_IN_Tax_Sale_Fall_2026/FeatureServer/15 (630 rows).
- Results: `Munci_IN_TaxSaleResults_Fall2026` (414 rows).

**22. St Joseph County IN tax sale**
- URL: https://services.arcgis.com/OjftlhRHkAABcyiF/arcgis/rest/services/Tax_Sale_Properties_09012026/FeatureServer/0
- 1,266 rows with `NAME_1`, mailing address, `PARCELID` and `Minimum_Bi`.

**23–24. NYC Socrata: HPD Handyman Work Order charges and DOF Property Charges Balance**
- HPD Handyman Work Order charges, `sbnd-xujn`: 100,096 charges with BBL.
  - The description says HPD performs emergency repairs when an owner fails to correct a violation. The charges are billed to the property and are lienable through DOF.
- DOF Property Charges Balance, `scjx-j6np`: a quarterly snapshot of charges by `parid` (BBL), with `code` (CHG, SAC, SAF, SAT, NSF, SIF), `sum_liab`, `sum_coll`, `sum_bal` and `due_date`.
  - The latest `extractdt` is 2025-08-16.
- Socrata aggregate queries returned 503 (service unavailable); simple row fetches worked.
- Also reachable: DOB ECB Violations (`6bgk-3dad`, respondent + balance_due + block/lot), but it is a subset of the OATH judgments already loaded.

**25. Saguache County CO 2026 tax sale**
- URL: https://services1.arcgis.com/zH7gQ37AKcpvTX6d/arcgis/rest/services/2026_Tax_Sale/FeatureServer/204
- 900 rows with `TaxSale_Owner`, `TaxSale_Parcel` and `Total_Due`.

**26. Lake County CO 2026 delinquent tax lien sales**
- URL: https://services1.arcgis.com/38PTfoP8IjlBsxZN/arcgis/rest/services/2026_Delinquent_Tax_Lien_Sales/FeatureServer/0
- 370 rows with owner, `PARCELNB`, `CUR_BAL` and `LST_BAL`.
- Earlier years: `2025_Tax_Liens` (174 rows), `2023_Tax_Liens` (317), `2021taxlien` (231).

**27. Summit County OH delinquent ≥ $10k**
- URL: https://services3.arcgis.com/3Ukh5HzAdI6WZ3KP/arcgis/rest/services/Vacant_Land_Map_Summit_County_2025_WFL1/FeatureServer/23
- 3,812 rows, `DELINQUENT_DUE`, owner and parcel. Last edited 2025-08, so it is a static extract.

**28. Medina County OH delinquent parcels**
- URL: https://services5.arcgis.com/m37BbrYBtVXq1nb8/arcgis/rest/services/Medina_Delinquent_Parcels/FeatureServer/0
- 454 rows, edited 2026-11-22.

**29. Cuyahoga County OH delinquency update table**
- URL: https://services7.arcgis.com/GXM8JipKyc0m6HBi/arcgis/rest/services/DelinquencyUpdateTable/FeatureServer/0
- 29,157 rows, parcel only, last updated 2025-04.
- Related: `2024_Forfeited_Land_Sale_Update` (402 forfeited parcels, with grantor = prior owner and `total_net_delq_owed`).

**30. Kalamazoo County MI forfeited parcels**
- URL: https://services3.arcgis.com/RGltUbqpl4h9E3Qh/arcgis/rest/services/3_1_26_Forfeited_Parcels/FeatureServer/0
- 289 rows.

**31. Hot Springs AR housing liens**
- URL: https://services1.arcgis.com/lCwVhIwyitVebu0v/arcgis/rest/services/Housing_Lien_Parcels/FeatureServer/90
- 257 rows with `Amount`, `Type_of_Lien` (VWL), `Date_of_Lien` and `RPID`.

**32. El Dorado KS special assessments**
- URL: https://services8.arcgis.com/peHl6Jhp6LT6yLW9/arcgis/rest/services/Special_Assessments---Public_View/FeatureServer/0
- 839 rows.

## Socrata catalog results: qualifying but host blocked

The Cook County proxy returns catalog metadata, including column names and update dates, for the whole Socrata network. A request for `https://<domain>/resource/<id>.json?$limit=1` failed on every host below with curl code 000 (proxy refusal). The catalog proxy's `/api/views/<id>.json?domain=` also returned 404 for each one. These hosts should be allowlisted.

| Domain / id | Name | Updated | Key columns |
|---|---|---|---|
| data.cityofchicago.org / 6br9-quuz | Ordinance Violations (DOAH) | 2026-11-21 | respondents, address, imposed_fine, hearing/disposition |
| data.cityofchicago.org / kc9i-wq85 | Vacant and Abandoned Buildings – Violations | 2025-10-08 | total_fines, interest_amount, original_total_amount_due, property address |
| data.cityofchicago.org / yqn4-3th2 | DOE Environmental Enforcement | 2026-11-20 | respondent, fine_amount, address |
| citydata.mesaaz.gov / hgf6-yenu | Code Compliance | 2026-11-19 | balance, parcel_number, case_address |
| data.vermont.gov / ag2q-tdje, b5xi-3qaq | Top 100 Businesses / Individuals (delinquent tax) | 2026-11-16 | taxpayer_name, balance |
| data.wa.gov / a4ma-dq6s | PDC Enforcement Cases | 2026-11-20 | respondent, total_penalties, balance_due |
| data.sonomacounty.ca.gov / bp8v-uax7 | Defaulted Tax Data | 2026-11-21 | fullredemptionpaid, redemption fees, mail address |
| internal.opendata.clermontauditor.org / 94fc-2usj, 77ey-nevf | Total Taxes Due and Paid; Non-TIF Special Assessments | 2026-11-22 | ownername, parid, netfirsthalfdue / amount |
| data.kingcounty.gov / x48t-7chj | Personal Property (tax) | 2026-11-18 | account_number, billed_amount, paid_amount, penalty |
| data.norfolk.gov / 7qie-z5gv; data.richmondgov.com / 83t5-hbac | Delinquent RE taxes (already flagged) | 2026 | owner_name, taxdue / total_due |
| data.texas.gov / u66a-qggj, 8j6x-idf8 | TCEQ Administrative Orders, SEPs | 2026-11-05 | respondent_name, payable_amount |
| data.bloomington.in.gov / bzzd-26re | CBU customer delinquent accounts | 2026-11-22 | aggregate only (no names), skip |

## Rejected or noted

- DC parking and moving violations (`maps2.dcgis.dc.gov`): monthly layers with 100k–300k rows each and fine/penalty amounts. They concern vehicle plates, not parcels. `dcgis.org` "DC Tax Liens" was refused by the proxy; it is worth allowlisting `dcgis.org`.
- Eviction point layers (ASU, Maryland DHCD and others): no amounts, or aggregates only.
- `Judgements 2024` (Knox County TN, owner `sarah3690`): only defendant address fields survive; no names and no amounts.
- Louisville Property Maintenance Inspection Violations: CitationAmount is mostly 0. Boarding & Cleaning: 66,662 rows with PenaltyAmount but stale (2022). Both are upstream of the already-loaded final orders.
- Richmond VA `Enterprise_CodeEnforcement`: Code_Case_Balance_Due = 0 on every row.
- Hamilton County OH `Parcel_Points_UNPAID_20241001` (23,997 rows): stale (2024-10). The Hamilton parcel collection is current but carries no delinquency field.
- Maricopa `DelinquentTax/FeatureServer/1` (Master_List): 34,417 rows edited 2026-11-20, now with `OWNER1`, `PIN`, `TOTALDUE`, `TFCDE` (JUD), `VOL`/`PG`. The layer is already loaded, but the loader may be missing these amount and judgment-code fields. Worth a re-check.
- Student and project copies were skipped: Swissvale tax liens (Pitt), Baltimore tax liens (NCSU), Philadelphia copies, and the UCR San Bernardino/Riverside basemaps.
