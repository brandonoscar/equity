# Data fix list: empty lake fields (for the data session)

Read from the lake bucket on 2026-11-27: 864 built sources, every `instrument` part of all 347
instrument sources (80,325,359 rows, full scan, not sampled), every `judgment`, `bankruptcy`
and `court_case` part, and the full `fl.citrus.civil` and `us.flmb.rss` docket tables. Where the
raw files were gone, the raw field was checked against the adapter, the recorded test fixture,
or the live public dataset's column list or aggregate query (aggregates only, no rows).

`file:line` refers to **origin/main at e3eee3e**. The local branch `claude/bold-ritchie-anlm7o`
is 71 commits behind it, and several of the sources below are configured only on main.
`src/equity/search_index.py` is on this branch only.

Verdicts: **BUG** means the raw source has the value and the adapter or config drops it.
**GAP** means a configured source could fill a table or column that nothing writes yet (a design
call). **SOURCE** means the raw data has no such field, so there is nothing to fix.

## Top fixes, in order

| # | Fix | Rows affected | Where |
|---|---|---|---|
| 1 | Citrus docket satisfactions are never written as `judgment_event`, so the matcher treats satisfied judgments as open | 2,574 satisfaction entries (+1,750 vacate, 272 writs) | `src/equity/adapters/fl/citrus_civil.py:439-457` |
| 2 | `liens.py` hard-codes `book=None, page=None, executed_on=None`, but configs select those fields | 3.97M rows with a selected book field; 3.83M with a selected execution date | `src/equity/adapters/liens.py:1031-1032` |
| 3 | Lake has stale copies of renamed sources (the same debts appear twice in the index) | 12 stale source ids, 59,021 instruments | bucket folders, list in 5b |
| 4 | `bankruptcy.trustee_party_id` is never set, though the trustee party is created; discharge, dismissal and asset entries are in the feed but never reach `bankruptcy` | 2,307 rows | `src/equity/adapters/federal/ecf_rss.py:172-184` |
| 5 | CT federal and state lien releases are published (`lien_status`) but not read | 2,394 IRS liens released (live count) | `config/liens/ct.sots.liens.yaml` |
| 6 | Philadelphia RTT `DEED LAND BANK` is unmapped (4,432 `unknown_doc_type` issues) | 4,018 instruments | `config/recorders/pa.philadelphia.rtt.yaml:15` |
| 7 | Hillsborough OR `ODRNS` (an order of dismissal, respondent not served) is loaded; the similar family-court codes are excluded | 47 instruments | `config/recorders/fl.hillsborough.or.yaml:22` |

Two of the starting findings are **not** data bugs:

- `judgment.principal` is not NULL lake-wide: 83% of judgment rows have it (finding 1). The
  index showed NULL because the 16-state index held only the FL and TX judgment sources (truly
  no amounts); the federal `us.fjc.idb.direct.civil_judgments` source joined it in the 22-state
  build. The loader maps `principal` (`search_index.py`); the search session re-measures the
  fill rate after the full build.
- Federal tax lien amounts do not exist in any of the three sources (finding 2).

---

## Finding 1: judgment amounts

The lake has 489,680 judgment rows. `principal` is filled on 406,622 of them (83.0%). `interest`,
`rate` and `lien_instrument_uid` are 0% on every source.

| Source | Field | Filled | Rows | Evidence | Verdict / likely fix |
|---|---|---|---|---|---|
| `us.fjc.idb.direct.civil_judgments` | principal | 93.1% (401,318) | 430,832 | AMTREC (in thousands) mapped at `fjc_idb_direct.py:323` via `fjc_idb.py:138`; the 29,514 NULLs are AMTREC 9999 (a floor, NULL by design). Rows ingested 2026-11-23. | **Lake OK.** The index reports NULL for this source: re-pull or rebuild the `judgments` table. The loader is in `src/equity/search_index.py:399` (this branch; search session). |
| same | interest, costs, rate | 0% | 430,832 | The IDB has no such fields | SOURCE |
| `us.epa.echo.judicial_cases` | principal / costs | 69.6% / 44.5% | 7,602 | FED_PENALTY_ASSESSED_AMT and COST_RECOVERY_AWARDED_AMT mapped (`epa_echo.py:250`). STATE_LOCAL_PENALTY_AMT is fetched (`epa_echo.py:54`) and never used. | Optional: the state or local penalty is owed to a different creditor, so it would need its own judgment row with that creditor. |
| `tx.harris.district.civil_judgments` | principal | 0% | 25,647 | Docstring `tx/harris_district.py:8` and the config comment: the extracts have no amounts | SOURCE |
| `fl.citrus.civil` | principal | 0% | 25,549 | Docstring `citrus_civil.py:20`. A full scan of the 119,670 docket texts found 23 with a `$`, all foreclosure redemption deposits. | SOURCE. See the `lien_instrument_uid` row and finding 5. |
| `fl.citrus.civil` | lien_instrument_uid | 0% | 25,549 | 25,501 judgment docket entries cite `(OR.<book>.<page>. / <instrument>)`. `or_reference()` parses this already (`citrus_civil.py:78,171`) but uses it only for the uid hash. | GAP: put the OR instrument number into `lien_instrument_uid` (or an `instrument_ref`) once a Citrus OR source exists. |
| `fl.hillsborough.civil.cases` | principal | 0% | 37 | The Bulk Data Case File header has no amount column (fixture `fl.hillsborough.civil.cases/case-file-2026-01-10_limit-30.json`). The CaseType amount bands are claim ranges, not judgments. | SOURCE |
| `us.fjc.idb.civil_judgments` | principal | 84.6% | 13 | as FJC direct | OK |

## Finding 2: TAX_LIEN_FEDERAL amounts

There are 249,191 TAX_LIEN_FEDERAL instruments lake-wide (the index sees the 184k from CO).
Amount and consideration are 0% on all three sources.

| Source | Field | Filled | Rows | Evidence | Verdict / likely fix |
|---|---|---|---|---|---|
| `co.sos.ucc` | principal_amount | 0% | 183,631 | The live columns of `wffy-3uut` and `8upq-58vz` include no amount (transactionid, filingdate, lapsedate, filingtype, documenttype ...). `co_ucc.py:193` correctly writes None. | SOURCE |
| `ct.sots.liens` | principal_amount | 0% | 65,436 | The live columns of `xfev-8smz` have no amount (the config summary says so too) | SOURCE |
| `ct.sots.liens` | release (no RELEASE row, no "(satisfied)" mark) | 0% | 65,436 | Live: `lien_status` reads Active 79,256 / Released 2,394 / Terminated 2 for IRS originals. The config never reads it. | **BUG.** Add `satisfied_flag: lien_status` and `satisfied_values: [released, terminated]` (keys documented at `liens.py:61`). The matcher already treats "(satisfied)" as released. |
| `or.sos.ucc` | principal_amount | 0% | 124 | The live columns of `snfi-f79b` have no amount | SOURCE |

## Finding 3: amount and consideration fill rates

Lake-wide figures: `amount` (= coalesce(principal_amount, max_secured_amount), as the index
computes it) is 17.9%, and `consideration` is 22.2% (17.85M of 80.3M rows). By doc type:
MORTGAGE amount is 67.0% of 6,235,271, LIS_PENDENS amount is 19.4% of 312,400, and DEED
consideration is 66.8% of 23,960,261. The index's 30% for MORTGAGE reflects its 16-state mix:
ACRIS (85%) and Cook (99%) are outside it.

### 3a. Sources at 0% on a doc type where other sources fill the field

| Source | Doc type, field | Filled | Rows | Evidence | Verdict |
|---|---|---|---|---|---|
| `pa.philadelphia.rtt` | MORTGAGE amount | 0% | 1,377,786 | Live Carto: 0 of 111,879 mortgages recorded since 2024 have `total_consideration > 0`. `philadelphia_rtt.py:272` uses it for deeds only. | SOURCE |
| `fl.putnam.or` | MORTGAGE amount | 0% | 41,344 | MTG descriptions are legal descriptions (fixture). Amounts are read only for JUDGMENT_LIEN and STATUTORY_LIEN (`fl.putnam.or.yaml:26`). | SOURCE |
| `fl.hernando.or` | MORTGAGE amount | 0% | 19,954 | "The index carries no ... amounts" (`hernando_or.py:11`) | SOURCE |
| `fl.hillsborough.or` | MORTGAGE amount | 0% | 5,986 | The `consideration` column is blank on every MTG row in the day fixture (filled on D rows) | SOURCE (re-check against a full daily file if one is kept) |
| `il.cook.recorder_foreclosures_2011` / `_2012` | LIS_PENDENS amount | 0% | 39,398 / 38,852 | `consideration_amount` is selected but not mapped. Live (`epxa-9ihc`): only 152 of 46,573 lis pendens rows have one. | SOURCE (could add `amount: consideration_amount` for those 0.3%) |
| `il.cook.recorder_mortgages_2013_2015` | LIS_PENDENS amount | 0% | 46,586 | Same dataset family. Mortgages in it are 100%. | SOURCE |
| `md.prince_georges.foreclosures`, `ca.los_angeles.registered_foreclosures`, `oh.stark.foreclosures`, `ky.louisville.*foreclosures` | LIS_PENDENS amount | 0% | 76,968 / 2,758 / 24,838 / 1,747 | The configs say no amount is published. Stark has only Total_Property_Value (not a debt). | SOURCE |
| `mn.dakota.sheriff_sales` | LIS_PENDENS amount | 0% (consideration 100%) | 9,542 | SaleAmount (the sheriff bid) goes to `consideration`. The index amount excludes consideration. | Design note for the search session, not a data bug |
| `wi.milwaukee.foreclosure_sales` | LIS_PENDENS amount | 0% | 399 | Sale_Price is selected but unused (it is a sale price, not the debt) | Optional `consideration: Sale_Price` |
| `sc.spartanburg.last_deed` | DEED consideration | 0% | 181,820 | `consideration: SaleAmount` is configured. Live layer: count(SaleAmount) = 0. | SOURCE (the county publishes the field empty) |
| `al.madison.last_deed` | DEED consideration | 0% | 180,690 | The live layer fields have no price | SOURCE |
| `in.st_joseph.transfer_history`, `ok.oklahoma.deed_filings`, `tx.williamson.cad_last_transfer` | DEED consideration | 0% | 452,317 / 257,432 / 232,376 | The configs say no price (TX is a non-disclosure state) | SOURCE |
| `fl.putnam.or`, `fl.hernando.or` | DEED consideration | 0% | 138,822 / 28,384 | No price in either index | SOURCE |
| `us.hud.fha_reo` | DEED consideration | 0% | 622 | "no ... list price" (`hud_reo.py:7`) | SOURCE |

### 3b. Selected but never written (adapter bugs)

| Source(s) | Field | Filled | Rows | Evidence | Likely fix |
|---|---|---|---|---|---|
| 8 Cook recorder sources (`il.cook.recorder_{mortgages,foreclosures,quitclaims}_*`) | executed_on | 0% | 857,803 | `execution_date` is in every `select` (e.g. `il.cook.recorder_foreclosures_2011.yaml:13`). Live: 499,768 of 511,173 rows filled (`4f2q-h3b7`). | `liens.py:1032` writes `executed_on=None`. Add an `executed_on: <field>` config key (read with `_date`, reject dates after the recording date or after retrieval) and set it in these 8 configs. |
| `il.ptax.transfers` | executed_on | 0% | 2,975,443 | `line_4_instrument_date` is selected (`il.ptax.transfers.yaml:13`) | Same key |
| `va.fairfax.real_estate_sales`, `co.adams.property_sales`, `co.douglas.property_sales`, `va.virginia_beach.property_sales`, `sc.spartanburg.last_deed`, `al.madison.last_deed`, `sc.york.last_deed`, `fl.miami_dade.{code_collections,building_liens,code_liens}` | book, page | 0% | 3,970,779 | Each config selects a deed or OR book (BOOK, DeedBook, LN_RECBOOK, LIEN_BOOK ...). `liens.py:1031` writes `book=None, page=None`. | Add `book` / `page` (and `book_type`) config keys. The Miami-Dade liens then cite their OR book and page, which a recorder index can join on. |
| `ny.nyc.oath.judgments` | principal_amount | 63.6% | 3,734,112 | `amount: balance_due`, so paid judgments are NULL. `penalty_imposed` is selected and unused. | Owner call: either keep the balance (open debt) or take `penalty_imposed` and mark paid ones satisfied. |
| `tx.harris.tax_judgments`, `mi.detroit.blight_judgments` | principal_amount | 100% | 1,934 / 587,954 | `Judgment_Amount` and `amt_judgment` are selected and unused (the balance is used instead) | Fine as is. Note only: the original judgment amount is dropped. |
| `fl.hillsborough.civil.cases` | court_case.closed_on | 0% | 77,736 | `closed_on=None` (`hillsborough_civil.py:259`) although CaseStatus/JudgmentDate exist | Low priority: closed_on = JudgmentDate when CaseStatus is Closed |

## Finding 4: doc_type = 'OTHER'

OTHER is 27,966,329 instruments lake-wide (34.8%; the index sees 16M). It is almost all
municipal activity that has no category in the enum, and it is not recorder documents mapped
badly:

| Kind of source | OTHER rows | Sources |
|---|---|---|
| Building and trade permits | 19,350,612 | 53 |
| Code, rental, vacant-building and eviction cases | 6,643,959 | 45 |
| SBA 7(a) and PPP charge-offs (unsecured federal debt, amounts filled) | 877,050 | 2 |
| NYC HPD open-market-order awards | 497,800 | 1 |
| Recorder, UCC and sales indexes (where a remap can matter) | 228,607 | 8 |
| Everything else (land banks, appeals, disclosures ...) | ~368,000 | ~40 |

The top 60 `(source, doc_type_raw)` pairs are 15.1M rows (54% of OTHER). None of them maps to an
existing category:

| # | Source | doc_type_raw | Rows | Proposal |
|---|---|---|---|---|
| 1 | `ca.san_francisco.building_permits` | otc alterations permit | 882,513 | keep OTHER (permit) |
| 2 | `tx.austin.construction_permits` | Electrical Permit | 691,205 | keep OTHER (permit) |
| 3 | `us.sba.ppp_chargeoffs` | SBA PPP loan charged off | 643,032 | keep OTHER (unsecured debt, not recorded) |
| 4 | `ca.los_angeles.code_cases_closed` | PACE | 574,950 | keep OTHER (code case) |
| 5 | `il.cook.assessor_permits` | RESIDENTIAL PERMIT | 565,565 | keep OTHER (permit) |
| 6 | `tx.austin.construction_permits` | Plumbing Permit | 548,745 | keep OTHER (permit) |
| 7 | `tx.austin.construction_permits` | Building Permit | 522,567 | keep OTHER (permit) |
| 8 | `tx.austin.construction_permits` | Mechanical Permit | 507,687 | keep OTHER (permit) |
| 9 | `ny.nyc.dob_electrical_permits` | DOB NOW electrical permit | 503,680 | keep OTHER (permit) |
| 10 | `tx.fort_worth.development_permits` | Plumbing | 414,066 | keep OTHER (permit) |
| 11 | `tx.fort_worth.development_permits` | Electrical | 349,928 | keep OTHER (permit) |
| 12 | `ca.los_angeles.building_permits_pre2010` | Bldg-Alter/Repair | 348,866 | keep OTHER (permit) |
| 13 | `fl.orlando.permit_applications` | Building Permit | 340,051 | keep OTHER (permit) |
| 14 | `ca.los_angeles.building_permits_2010s` | Bldg-Alter/Repair | 333,183 | keep OTHER (permit) |
| 15 | `nc.mecklenburg.building_permits` | One/Two Family | 319,765 | keep OTHER (permit) |
| 16 | `fl.cape_coral.building_permits` | Trades | 285,571 | keep OTHER (permit) |
| 17 | `ca.los_angeles.building_permits` | Bldg-Alter/Repair | 285,181 | keep OTHER (permit) |
| 18 | `ny.nyc.hpd_omo_charges` | GC | 282,995 | keep OTHER (contract award, not the billed charge, per its config; the owner may revisit, since `hpd_hwo_charges` is STATUTORY_LIEN) |
| 19 | `tx.fort_worth.development_permits` | Mechanical | 282,933 | keep OTHER (permit) |
| 20 | `tx.fort_worth.development_permits` | Residential Building Permit | 254,293 | keep OTHER (permit) |
| 21 | `in.indianapolis.code_enforcement` | Enforcement/Investigation/High Weeds & Grass/NA | 236,546 | keep OTHER (code case) |
| 22 | `mo.kansas_city.permits` | Electrical | 227,867 | keep OTHER (permit) |
| 23 | `ca.san_francisco.building_permits` | additions alterations or repairs | 225,247 | keep OTHER (permit) |
| 24 | `us.sba.chargeoffs` | SBA 7A loan charged off | 222,230 | keep OTHER (unsecured debt) |
| 25 | `pa.philadelphia.violations` | CLIP VIOLATION NOTICE | 212,551 | keep OTHER (code case) |
| 26 | `fl.orlando.permit_applications` | Electrical | 212,257 | keep OTHER (permit) |
| 27 | `ny.nyc.dob_permits` | General Construction | 198,850 | keep OTHER (permit) |
| 28 | `ca.los_angeles.code_cases_closed` | GENERAL | 181,791 | keep OTHER (code case) |
| 29 | `ca.san_francisco.dbi_complaints` | OTHER | 180,620 | keep OTHER (code case) |
| 30 | `nc.raleigh.building_permits` | Building | 173,510 | keep OTHER (permit) |
| 31 | `dc.dob.building_permits` | ELECTRICAL | 173,464 | keep OTHER (permit) |
| 32 | `fl.cape_coral.building_permits` | Accessories | 171,260 | keep OTHER (permit) |
| 33 | `in.indianapolis.code_enforcement` | Enforcement/Violation/High Weeds & Grass/NA | 165,804 | keep OTHER (code case) |
| 34 | `in.indianapolis.code_enforcement` | Enforcement/Investigation/Zoning/NA | 164,203 | keep OTHER (code case) |
| 35 | `ny.nyc.dob_permits` | Plumbing | 158,629 | keep OTHER (permit) |
| 36 | `nc.mecklenburg.building_permits` | Commercial | 156,890 | keep OTHER (permit) |
| 37 | `ca.sacramento.building_permits_archive` | Single Family | 154,589 | keep OTHER (permit) |
| 38 | `dc.dob.building_permits` | PLUMBING AND GAS | 153,783 | keep OTHER (permit) |
| 39 | `pa.philadelphia.permits` | PP_PLUMBNG | 149,974 | keep OTHER (permit) |
| 40 | `la.nola.code_enforcement_cases` | 6 - Case Closed | 149,247 | keep OTHER (code case) |
| 41 | `dc.dob.building_permits` | ALTERATION AND REPAIR | 148,484 | keep OTHER (permit) |
| 42 | `tx.fort_worth.development_permits` | Plumbing Backflow | 147,553 | keep OTHER (permit) |
| 43 | `wa.pierce.permits` | Construction Residential | 144,953 | keep OTHER (permit) |
| 44 | `ny.nyc.lpc_permits` | Certificate of No Effect | 139,037 | keep OTHER (landmarks permit) |
| 45 | `mn.minneapolis.building_permits` | Plumbing | 137,356 | keep OTHER (permit) |
| 46 | `ca.los_angeles.lahd_eviction_notices` | 3 Day | 137,254 | keep OTHER (eviction notice) |
| 47 | `mo.kansas_city.permits` | Mechanical | 127,270 | keep OTHER (permit) |
| 48 | `nv.las_vegas.building_permits_archive` | OTC | 124,588 | keep OTHER (permit) |
| 49 | `pa.philadelphia.violations` | EXTERIOR AREA WEEDS | 124,388 | keep OTHER (code case) |
| 50 | `fl.orlando.permit_applications` | Plumbing | 121,898 | keep OTHER (permit) |
| 51 | `ny.nyc.hpd_omo_charges` | DELEAD | 120,333 | keep OTHER (as #18) |
| 52 | `fl.orlando.code_enforcement_cases` | OTHER | 119,178 | keep OTHER (code case) |
| 53 | `mo.kansas_city.permits` | Building | 117,949 | keep OTHER (permit) |
| 54 | `tx.austin.construction_permits` | Driveway / Sidewalks | 116,819 | keep OTHER (permit) |
| 55 | `mo.kansas_city.permits` | Plumbing | 112,217 | keep OTHER (permit) |
| 56 | `ny.nyc.dob_permits` | Sidewalk Shed | 111,985 | keep OTHER (permit) |
| 57 | `fl.orlando.permit_applications` | History | 111,191 | keep OTHER (permit) |
| 58 | `fl.orlando.permit_applications` | Mechanical Permit | 110,720 | keep OTHER (permit) |
| 59 | `mn.minneapolis.building_permits` | Res | 109,752 | keep OTHER (permit) |
| 60 | `mn.minneapolis.code_violations` | Nuisance | 107,443 | keep OTHER (code case) |

The remaps that do matter are in the recorder, UCC and sales indexes. The proposal below
reclassifies **10,190 OTHER rows (0.04% of OTHER)**.

`config/doc_types.yaml` holds category lists, not raw-to-category maps. The maps live in each
source's own config, so each block names the file to change. The snippet keeps doc_types.yaml's
style (a commented top-level key, then entries) for review:

```yaml
# Proposed doc_type_raw -> doc_type remaps, for owner review. Not a legal conclusion.
# Apply each block in the named source config; nothing here changes config/doc_types.yaml's lists.
proposed_raw_remaps:
  fl.putnam.or:                  # config/recorders/fl.putnam.or.yaml:38 (codes)
    CCP: JUDGMENT_LIEN           # 5,965 rows. Certified copy of a county civil judgment, already
                                 # creditor/debtor roles; Fla. Stat. 55.10 lien on recording. Confirm.
  pa.philadelphia.rtt:           # config/recorders/pa.philadelphia.rtt.yaml:15 (types)
    DEED LAND BANK: DEED         # 4,018 rows; also clears 4,432 unknown_doc_type data_issue rows
    RELEASE: RELEASE             # 57 rows
  fl.hillsborough.or:            # config/recorders/fl.hillsborough.or.yaml:24 (codes)
    SATCORPTX: RELEASE           # 102 rows; satisfaction of LNCORPTX (TAX_LIEN_STATE, line 39)
    ASINT: ASSIGNMENT            # 30 rows; assignment of interest
    PRREL: PARTIAL_RELEASE       # 11 rows; confirm the code's meaning first (PR is PARTIAL_RELEASE)
    TAXDEED: DEED                # 6 rows
  ct.sots.liens:                 # config/liens/ct.sots.liens.yaml:16 (doc_type.map)
    JUDGMENT: JUDGMENT_LIEN      # 1 row; the map has 'JUDGMENT - PERS' only

keep_other:                      # reviewed, no existing category fits
  - permits and code/rental/eviction cases (26.0M rows, ~98 sources; table above)
  - us.sba.* charge-offs (877,050): unsecured federal debt, already a debt kind
  - ny.nyc.hpd_omo_charges (497,800): award, not the billed charge (config note)
  - ny.nyc.acris.real WSAT "WITHHELD SATISFACTION" (6,355) and TLS (350): as configured
  - FL OR NOC / PRO / NOT / CP / EAS / AGR / GOV / CTF (notices of commencement, probate, court
    papers, easements ...): not encumbrances

needs_owner_lookup:              # codes nothing in the source defines
  co.adams.property_sales:       # config/liens/co.adams.property_sales.yaml:13 TODO
    DTH: "?"                     # 26,221 rows, 6,806 with a price, so a conveyance of some kind
    MRG: "?"                     # 2,447 rows, 490 with a price
  fl.putnam.or: [TCL, LNC]       # 9 and 10 rows, not in codes
```

`ODRNS` (47 rows in `fl.hillsborough.or`) should not be remapped. It belongs in
`exclude_codes` (`fl.hillsborough.or.yaml:22`) next to ODNPFL and DRJUD, because an order of
dismissal with "respondent not served" reads as a domestic-relations filing. Check that before
excluding it.

Structural point for the owner: 93% of OTHER is permits and code cases. If they should not count
as documents, the fix is a new category (an enum, a migration and a protected
`config/doc_types.yaml` change) or a source-kind filter in the index. Remapping raw strings will
not shrink it.

## Finding 5: tables or columns empty everywhere

### 5a. Empty or near-empty tables

| Table / column | Rows | Should a configured source fill it? |
|---|---|---|
| `judgment_event` | 0 | **Yes, `fl.citrus.civil`.** Its docket keeps SATISF, VACAT and WRIT texts (`fl.citrus.civil.yaml:26`): 2,574 satisfactions (9 partial), 1,750 vacate entries and 272 writs of execution, all written only as `docket_entry` (`citrus_civil.py:441`). The matcher counts a court judgment as released only if a `satisfied` event exists (`matching/resolve.py:553-565`). Emit `satisfied` / `partial_satisfaction` / `vacated` / `execution_issued` events against the case's judgment_uid. `fl.hillsborough.garnishment` writ dates are a possible `execution_issued` source (owner call: there is no judgment row there yet). |
| `bankruptcy` (discharge_on, dismissed_on, converted_on, trustee_party_id, asset_case) | 2,307 rows, those 5 columns 0% | **Partly a bug.** `ecf_rss.py:178-184` writes None for all five. The trustee party is created just above (`ecf_rss.py:172-177`), so `trustee_party_id` can be its `pid` today. The feeds do carry the outcomes (`us.flmb.rss` sample: 83 "ADI - Discharge Of Debtor", 382 discharge notices, 31 "Order Dismissing Case", 21 "Final Report - Chapter 7 Asset"). But a `bankruptcy` row needs `petition_on`, and the RSS window rarely holds a case's petition and its discharge together. So the fix is an update path for an existing row, or a backfill source (`config/pacer.yaml`). The row count is small (2,307) because only petition entries create rows. |
| `ownership_period` | 0 | Only `wv/parcelweb.py` writes it, and `wv.monongalia.assessor.parcelweb` is registered but not built (`reports/lake_gaps.md`). Build that source. No other adapter targets this table. |
| `tax_sale_event` | 0 | No adapter writes it. 43 built tax-sale sources (692,838 instruments: `ny.nyc.tax_lien_sale` 264,142, `il.cook.annual_tax_sale` 200,907, `md.baltimore_city.tax_lien_certificate_sale` 68,399, `ia.linn.tax_sale_certificates` 22,225, `fl.broward.tax_certificates` 2,753 ...) are loaded as instruments instead. Their sold / redeemed / certificate / purchaser fields fit this table. GAP (design call: a `tax_sale_event` emit mode in `liens.py`). |
| `tax_bill` | 0 | No adapter writes it. 42 delinquent-tax lists (1,126,716 instruments) are TAX_LIEN_STATE instruments. Some publish bill parts that are selected and unused, e.g. `pa.philadelphia.tax_delinquencies` (PRINCIPAL_DUE, PENALTY_DUE, INTEREST_DUE, OLDEST_YEAR_OWED) and `oh.stark.delinquent_taxes` (TOTAL_BILLED, TOTAL_PAID). GAP. |
| `tax_delinquency_snapshot` | 32,619 | Only `wv.statewide.delinquent`. That is expected. |
| `instrument_image` | 0 | Purchase or bulk-agreement only. Expected. |
| `judgment.interest`, `judgment.rate` | 0% | No source publishes them. SOURCE. |
| `instrument.max_secured_amount` | 877,050 (SBA only) | No recorder source publishes it. SOURCE. |
| `court_case.filed_on` for `us.epa.echo.judicial_cases` | 0% of 6,895 | `epa_echo.py:242` writes None. None of the ICIS columns kept (`epa_echo.py:45-58`) is a filing date. SOURCE unless another ICIS column is added. |

### 5b. Stale renamed sources still in the bucket

Each of these has no config on main. Most have a renamed successor in the lake with the same or
nearly the same rows, so the index (which reads every built source) counts those debts twice.
Delete the old folders from the bucket, after checking each successor's counts:

| Stale source (instruments) | Current source on main |
|---|---|
| `ky.louisville.foreclosures` (1,747, LIS_PENDENS) | `ky.louisville.metro_foreclosures` (1,747, OTHER) |
| `va.richmond.delinquent_taxes` (16,669) | `va.richmond.tax_delinquent` (16,669) |
| `nc.guilford.delinquent_taxes` (8,083) | `nc.guilford.tax_delinquent` (8,045) |
| `oh.clermont.delinquent_taxes` (4,422) | `oh.clermont.tax_delinquent` (4,380) |
| `la.nola.code_judgments` (12,324) | `la.nola.code_hearing_judgments` (14,758) |
| `la.east_baton_rouge.adjudicated` (10,333) | `la.ebr.adjudicated_parcels` |
| `nc.buncombe.unpaid_taxes_2023/2024/2025` (176 / 321 / 755) | `nc.buncombe.unpaid_bills` |
| `ky.louisville.code_liens` (473) | `ky.louisville.code_final_orders`? (confirm) |
| `ky.jefferson.tax_sale_bills` (3,534), `al.shelby.tax_sale_parcels` (184) | none on main (removed?) |

Sixteen parcel sources are also built without a config id on main (for example
`mo.st_louis_city.parcels` and `ut.weber.parcels`). They may be registered some other way (a
bulk or statewide config), so check them before deleting anything.

### 5c. Handoffs to other sessions (not data fixes)

- **Search:** `judgments.principal` in the index is NULL while the lake has 406,622 values (see
  finding 1). Also, the index `amount` excludes `consideration`, so sheriff-sale bids
  (`mn.dakota.sheriff_sales`) read as missing.
- **Cross-linking:** `ny.nyc.acris.real` has 3,346,324 `unresolved_reference` data_issue rows.
  They are releases and assignments that cite a pre-2003 reel/page or CRFN, deferred by design to
  a later join on instrument_number / book / page (`ny/acris.py:421-423`). 47.7% of ACRIS
  instruments carry a book, so the join is possible. Until it runs, the mortgages those releases
  satisfy stay open. `pa.philadelphia.rtt` has 627,173 `no_parcel_id` issues (address only),
  which need an address-to-OPA join.

## Method notes

- The numbers are row counts over every part file (current and superseded rows: only 6
  instrument rows and 315 court_case rows are superseded). `_counts.json` lags the parts on
  append-poll sources (for example, `bankruptcy` is 1,787 in `_counts.json` and 2,307 in the
  parts).
- Live-source checks were aggregate queries only: Socrata `$select=count(...)`, ArcGIS
  `outStatistics`, Carto `count(*) FILTER`, and dataset column listings. No rows were downloaded.
- Raw downloads were not available for most sources (`data/raw` holds only `in.dlgf.parcels`
  and `us.wvnd.rss`).

## Handoff to the cross-linking session: name_key gaps (from the search session)

The search index uses the matcher's `name_key` and `STOP` (`src/equity/matching/resolve.py:164,297`)
so both sides compare names the same way. These cases are wrong today in both; each is common in
recorder and court records. A fix belongs in the matcher (the index follows it automatically):

| Printed names | name_key today | Should be |
|---|---|---|
| `O'BRIEN, JOHN` vs `OBRIEN JOHN` | `BRIEN JOHN O` vs `JOHN OBRIEN` (different) | equal: drop apostrophes before splitting |
| `ACME HOLDINGS, L.L.C.` vs `ACME HOLDINGS LLC` | `ACME C HOLDINGS L` vs `ACME HOLDINGS LLC` | equal: drop periods before splitting (the index's `org_key` does this for organizations only) |
| `SMITH JOHN ET UX` / `ET VIR` | keeps `UX` / `VIR` | `UX`, `VIR` are "and wife / and husband": add to `STOP` like `ETAL` |
| `ESTATE OF JOHN SMITH`, `JOHN SMITH DECEASED`, `HEIRS OF ...` | keeps `ESTATE`, `DECEASED`, `HEIRS` | a separate flag (the estate is the debtor), not a plain name match |
| `AL SMITH` (a person named Al) | `SMITH` (one word: `AL` is a stop word for ET AL) | drop `AL` only after `ET` |
| `JOHN V SMITH` | the matcher's `suffix_key` counts `V` as a suffix | `V` is usually a middle initial; keep `V` a suffix only as a last word after a full name |
| `JOHN & MARY SMITH` (joint owners on one line) | `JOHN MARY SMITH` | split co-owners into one name each before matching a single debtor |
