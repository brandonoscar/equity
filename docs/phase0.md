# Phase 0: Orientation

Status: research only, no pipeline code. Waiting for approval before Phase 1.
Date: 2026-11-15. Everything marked **VERIFIED** was fetched from the official source during this session. **FROM SEARCH** means it was only seen in search results. **NOT VERIFIED** means it's an inference or a guess and is listed in §7.

---

## 0. Decisions needed before Phase 1

1. **Recorder access (blocker for the most valuable adapter).** The County Clerk's record search sits behind an anti-bot slider CAPTCHA, and its terms say "This service is for viewing only. Please do not attempt to copy documents from this site." There's no compliant way to automate it. Options:
   - (a) Ask the Clerk for an electronic index export (and images) under W. Va. Code §59-1-10(e). The fee is a "reasonable fee, not to exceed cost". **Recommended.** You or the buyer would need to make the request. A draft request is in §7.
   - (b) Ask the vendor (Compiled Technologies) whether it offers a subscriber or bulk feed for Monongalia.
   - (c) Don't automate the recorder in v1. Hand-pull documents for golden cases only.
2. **OCR test (brief item 3).** It can't run yet. It needs 20 purchased document copies (≈ $60–$70 for the first 2–3 pages of each, or ≈ $320 for full documents). See §3. Approve the spend, or fold it into the request in decision 1.
3. **Circuit court judgments.** WVPASS (statewide circuit records) requires registration and login, and caps each search at 100 results. Non-negotiable 6 rules out automation behind a login. Options: request bulk data from the WV Supreme Court Administrative Office, or get judgment liens from the County Clerk's judgment lien docket (same access problem as decision 1).
4. **WV Secretary of State bulk data is a paid subscription.** See §2.5 for price and terms. The free entity search is usable record-by-record.
5. **Pilot choice.** Monongalia is workable for parcels, assessments, ownership history and tax status, all of which are open. It's blocked on recorder and court data. It's also outside the buyer's enforcement states (the buyer's list: FL, OH, LA, NY, NJ, IN, MI, GA, AL, TX, CA, NC, SC, PA), though the sourcing memo says "West Virginia first, then Pennsylvania". See §4.

---

## 1. court-scraper fork review

Repo: `brandonoscar/court-scraper`. HEAD is `364bd91` (2022-12-13, Ben Welsh). The fork has **no commits of its own**. It's identical to upstream `biglocalnews/court-scraper` at that point, and upstream has been inactive since Dec 2022.

### What it covers
| Platform | Place IDs in `sites_meta.csv` | Method | Notes |
|---|---|---|---|
| Odyssey (Tyler) | 4 CA, 3 GA, 37 WA (`docs/odyssey_sites.csv`) | Selenium | Several sites flagged `captcha_protected`. Has a login page object. |
| OSCN (Oklahoma) | 81 OK counties | requests + BeautifulSoup | Case-number search, daily filings. Upstream has a test demonstrating a known `search_by_date` bug. |
| WCCA (Wisconsin) | 72 WI counties | JSON POST API + Selenium | **Solves hCaptcha through the paid Anti-Captcha service (`anticaptchaofficial`).** |
| Iowa Courts Online | 100 IA counties | Selenium | **Also wired to a CAPTCHA-solving API key.** |
| **West Virginia** | **none** | n/a | No WV, no federal courts, no recorder data. |

### Data shape
- `CaseInfo` is a dict wrapper with a per-platform field map. `standard_data` returns only `place_id`, `number`, `filing_date`, `status`.
- `Datastore` is SQLite through SQLAlchemy with one table, `cases(place_id, number, filing_date, status, created, updated)`, upserted on `(place_id, number)`.
- Detail pages are cached as raw HTML under `~/.court-scraper/cache/<place_id>/<case>.html`.
- **There are no party names, roles, judgment amounts, judgment dates, docket entries or dispositions in the stored schema.** Some parsers extract a few extra fields (OSCN: judge, close date, type; WI: `civilJdgmts`, attorneys) but nothing persists them.

### What's broken or missing
- **Test suite:** 40 passed, 18 failed, 3 skipped, 22 deselected (`-m "not webtest"`, Python 3.13, network blocked). Failures are OSCN parsers getting `None` (`find_next` on missing nodes), WI API `JSONDecodeError`, a VCR cassette mismatch, and a CLI cache-file `FileNotFoundError`. Many tests not marked `webtest` still reach the live network.
- `CaseInfo._map` is a **class attribute mutated at runtime** (`wicourts/search_api.py`), so two platforms in one process overwrite each other's field maps.
- Uses deprecated `datetime.utcnow()` and the SQLAlchemy 1.x `declarative_base` import. Python 3.7–3.9 era.
- `cli.py`: "TODO: Restore catch-all try/except". A single failure aborts the batch.
- No rate limiting, no robots.txt handling, no provenance beyond the cached HTML file name, no retrieval timestamp on the case row.
- Dependencies include `selenium` and `anticaptchaofficial`. **The CAPTCHA-solving code paths conflict with non-negotiable 6** and must never be imported by our integration module.

### Recommendation
Treat the fork as a reference library, not a dependency for WV. It has nothing for West Virginia, and its storage model drops everything we need. Plan for the separate integration module (no changes to the fork's internals):
- Wrap individual platform *parsers* (e.g. OSCN case detail) behind our adapter interface only when we expand into a covered state (OK, WI, IA, WA, GA, CA).
- Add `anticaptchaofficial` and other CAPTCHA-solving packages (`2captcha-python`, `capsolver`, …) to the CI blocklist alongside the AI/ML packages. This needs your approval because `ci/` is CODEOWNERS-protected.

---

## 2. Monongalia County source survey

All fetches used a normal browser User-Agent, a handful of requests per host, and no login, CAPTCHA or payment. robots.txt was checked where it exists.

### 2.0 Summary table
| Source | Vendor / platform | Access | Bulk? | Cost | Terms / restrictions | Rate limits | Automatable now? |
|---|---|---|---|---|---|---|---|
| Recorder (County Clerk) | **Compiled Technologies "IDX Search Online"** (ASP.NET + DevExpress) | Web app behind slider CAPTCHA | Not offered online. Electronic copies under §59-1-10(e) on request | Search free. Copies $1.50/page (first 2), $1.00/page after. Certified $2.50 | "Viewing only… do not attempt to copy documents." CAPTCHA added "due to use of scripting tools and DDoS attacks" | Not published. CAPTCHA is the limit | **No** |
| Assessor: parcel GIS | Esri ArcGIS Online (county org `MGBEQZtkTlJin8UB`). Imagery and annotation from AGD Maps | **ArcGIS REST FeatureServer**, open | Yes, by paging (1,000 records/query, 55,953 parcels) | Free | No license text on the layer (open question: commercial use) | maxRecordCount 1000 | **Yes** |
| Assessor: transfer history ("ParcelWeb") | `monongalia.wvassessor.com/parcelweb` (ASP.NET WebForms) | HTML search + detail pages | No | Free | No robots.txt (404). No terms on page | None published | Yes (HTML, last resort) |
| Assessor: property record card | WV Integrated Assessment System (`wvias.io`), WV State Tax Dept | Linked per parcel from the GIS layer | Not checked | Free (presumed) | Not checked | Not checked | Not checked |
| Tax office (Sheriff) | **Software Systems, Inc.** tax inquiry (`monongalia.softwaresystems.com`) | HTML form POST | No | Free | No robots.txt (404). No terms on page | None published | Yes (HTML) |
| Delinquent tax sales | WV State Auditor (see §2.4) | see §2.4 | see §2.4 | see §2.4 | see §2.4 | see §2.4 | see §2.4 |
| Circuit Clerk | **WVPASS** (i3 Verticals, for the WV Supreme Court), `wvpass.courtswva.com` | Web app, **registration + login** | No public bulk offer found | Search free. Downloads $0.25/page + card fee | Login required. 100-result cap per search (FROM SEARCH) | Unknown | **No** (login) |
| Magistrate Court | `mcrsearch.courtswv.gov` | Web search | No | Free | Civil cap is below the buyer's $30K minimum | Unknown | Not needed |
| WV Secretary of State | see §2.5 | | | | | | |
| PACER NDWV + bankruptcy | see §2.6 | | | | | | |

### 2.1 Recorder: Monongalia County Clerk (VERIFIED)
- Official site `www.monongaliacountyclerk.com` (Joomla) links to `https://searchrecords.monongaliacountyclerk.com/`.
- **Vendor:** Compiled Technologies (footer "Copyright © 2020 by Compiled Technologies"). Help docs at `compiled-technologies.com/Help/IDXSearchOnline/`. The same product serves other WV counties (Preston, Tyler, Nicholas: FROM SEARCH).
- **Access:** every request, including `/robots.txt`, redirects to `reCAPTCHA.aspx`, a "Slide to verify" page with the notice: *"Due to use of scripting tools and DDoS Attacks being used on this site, we had to implemented some advanced security tools."* Direct deep links return "Access Denied. This page cannot be opened directly."
- **Terms (vendor help, "Void Watermark"):** *"The county is providing a service to allow individuals to view public records. This service is for viewing only. Please do not attempt to copy documents from this site. The County charges for copies and certified copies of documents."*
- **Search keys (vendor help, VERIFIED):** individual name, firm name, book & page, instrument number, legal description (slow, up to 3 minutes), date range (max 1 year per search). No record limit on results. Sub-indexes named in search results: grantor/grantee, creditor/debtor, plus vital records.
- **Index tabs:** Deeds, Liens, Misc, Estates, UCCs, Marriages, Births, Deaths (FROM SEARCH, for Preston and Nicholas on the same product).
- **Result grid (vendor "New Features" page, VERIFIED):** searched name, opposing party ("GRANTOR shows the GRANTEE"), cross-reference date ("date of the last cross reference"), return-to address in the detail panel, notations, description, multi-line legal description. Instrument type, recording date, book/page and instrument number are implied by the search keys. **NOT VERIFIED:** whether any consideration, loan amount or judgment amount column exists. That can only be confirmed by a person passing the CAPTCHA in a browser. See §7, Q1.
- **Document types recorded** (Clerk fee schedule effective 2025-07-01, VERIFIED): Deed, Deed of Trust, Memorandum of Deed of Trust, Fixture Filing, Plat/Map, UCC, Assignment, Affidavit, Execution, **Judgment**, Land Contract, Lease, **Lis Pendens**, **Mechanics Lien**, Modification Agreement, Court Orders, Power of Attorney, **Release**, Right-of-Way, **Statutory Lien**, Subordination Agreement, Substitute Trustee, **Trustee's Report** (foreclosure sale), Appraisements. The Clerk also takes a **Sales Listing Form** and a **Disclosure Form for Report of Trustee Sale**.
- **Copy fees** (§59-1-10(d)(1)): $1.50/page for the first 2 pages, $1.00 each additional page. Certified copy $2.50. Electronic-form copies: "Reasonable fee, not to exceed cost of Document Search & Duplication" (§59-1-10(e)).

### 2.2 Assessor (VERIFIED)
Three public surfaces:
1. **ArcGIS FeatureServer**, `services3.arcgis.com/MGBEQZtkTlJin8UB/arcgis/rest/services/Monongalia_AGOL/FeatureServer/6` (layer "Parcels"). 55,953 features. `maxRecordCount` 1000. Capability: Query only. Last edit 2026-08-03.
   Fields: `dmp` (dist-map-parcel), `dist`, `map`, `parcel`, `parid`, `nbhd`, `own1`, `own2`, `careof`, `owneraddr`, `cityname`, `statecode` (owner **mailing** address), `legal1..3`, `book`, `page` (current deed book/page), `aprland`, `aprbldg` (appraised land and building, integers), `acres`, `PRC` and `IAS_Details` (links to `wvias.io/prc/Monongalia/2026/<parid>`, tax year 2026), `DB_DP`, plus shape area and length.
   No owner ZIP. Appraised, not assessed (WV assessed value is normally 60% of appraised, an open question for config, not code).
2. **ParcelWeb**, `monongalia.wvassessor.com/parcelweb/`. Search by district, map, parcel or range, owner last/first, business, development, street, city, deed type, date range, **sale price range**, acreage, **deed book/page**, plus flags (plat, multiples, life estate, not mapped, minerals, void, duplicate assessment). A "current vs history" toggle returns past ownership periods.
   Results grid: District, Map, Parcel, Owner, Book, Page, **Sale Price**, **Date From**, **Date Thru**, Area, Acreage.
   Detail page: tax year, sale price, deed book/page, owner name, **percent owned**, **life estate**, warranty type (general/special), **survivorship**, owner status (Single, Husband/Wife, Widow/Widower), transfer and parcel notes, links to scanned map, card and Sheriff tax.
   **This is a dated ownership chain per parcel, with consideration and deed book/page.** It's the best free source for transfer-after-judgment and nominal-consideration flags, and the join key into recorder data.
3. **Property record card / IAS** (`wvias.io`): not fetched (host not allowlisted). Expected to carry assessed values and building details (NOT VERIFIED).

### 2.3 Circuit Clerk and judgments
- **WVPASS** (VERIFIED from the Supreme Court's 2025-02-24 release and the `courtswv.gov/court-record-access` page): all 55 circuit courts, public civil and criminal cases from 1999 on. "Registration to use the new system is free… The WVPASS search function will be free for registered users." Downloads cost $0.25/page plus a card fee. Vendor i3 Verticals. Host `wvpass.courtswva.com`. 100-result search cap (FROM SEARCH). No published bulk or API program found.
- **Judgment liens on real property are recorded at the County Clerk** (fee schedule lists "Judgment" and "Execution" as recordable instruments). In WV, the judgment lien docket is kept by the county commission's clerk (see §2.7 for statute citations). For our question (does a judgment encumber real property, and in what order), **the Clerk's judgment docket matters more than the circuit file**, but it has the same access problem as §2.1.
- Magistrate courts: separate system. Civil jurisdiction is capped below the buyer's $30K minimum (cap amount from memory, to confirm), so this is low priority.

### 2.4 Tax office and delinquency
- **Sheriff tax inquiry** (VERIFIED): vendor Software Systems, Inc. Search by taxpayer name, account, tax year + ticket, or district/map/parcel/sub-parcel. Filters: tax year, real/personal, **paid/unpaid**. Results grid: Ticket, Type, Taxpayer Name, Address, Half-Year Tax. The field names visible in page source are `TATYR, TATICK, TATSUF, TANAM1, TAASID, TADIST, TAMAP, TAPARC, TASPAR, TASPID, TA2PDF, TAADR, TATAX, TARCD, TACNTY`.
- ⚠️ **Security note:** the results page echoes its full SQL statement in an HTML comment, with the search text spliced into a `LIKE '…%'` clause. That pattern usually means a SQL-injection hole on a county system. I sent only one ordinary name search and did nothing else. Our adapter will use only the normal form. You may want to tell the county (Sheriff's office or the vendor).
- Sheriff duties per its site: collects real and personal property tax, mails statements in July, sells delinquent real estate taxes in November (FROM SEARCH; sale mechanics in §2.4b).

<!-- 2.4b, 2.5, 2.6, 2.7 filled from research agents -->

---

## 3. Recorder fields: index vs. image, and the OCR question

| Field | In searchable index? | On image only? | Other free source |
|---|---|---|---|
| Grantor / grantee (debtor / creditor for liens) | **Yes** (VERIFIED) | | Assessor owner names |
| Document type | **Yes** (index tabs + type; VERIFIED in fee schedule and search UI) | | |
| Recording date | **Yes** (date-range search; VERIFIED) | | |
| Instrument number | **Yes** (search key; VERIFIED) | | |
| Book / page | **Yes** (search key; VERIFIED) | | Assessor GIS + ParcelWeb carry deed book/page |
| Cross-reference to released/assigned instrument | **Partly**: "cross date" and notations (VERIFIED as UI features). Whether the referenced instrument number is shown is NOT VERIFIED | Release text names the instrument | |
| Legal description | **Yes** (searchable; VERIFIED) | Full text on image | Assessor `legal1..3` |
| Return-to address | Yes (detail panel; VERIFIED) | | |
| **Deed consideration** | NOT VERIFIED | Likely on image and transfer-tax stamp | **ParcelWeb sale price (VERIFIED)** |
| **Deed-of-trust principal amount** | NOT VERIFIED; unlikely | **Likely image-only** | none |
| **Maturity date** (needed for the buyer's "lapsed mortgage" screen) | No (strong expectation) | **Image-only** | none |
| **Judgment amount / judgment date** | NOT VERIFIED | Likely on image (abstract/order) | Circuit file (WVPASS, login) |
| Tenancy (survivorship, husband/wife) | No | On deed image | **ParcelWeb flags (VERIFIED)** |

**OCR test status: not run.** Reasons:
1. The only free image source is the CAPTCHA-gated viewer, and its terms forbid copying. Pulling 20 images from it would break non-negotiable 6.
2. Legitimate copies cost money, which needs your approval per non-negotiable 5. Estimate for 20 documents (10 deeds of trust, 10 judgment/lien instruments), using the fee schedule above:
   - First 2 pages of each (amount is usually on p.1–2): 20 × $3.00 = **$60**
   - First 3 pages of deeds of trust (to catch maturity date): 10 × $4.00 + 10 × $3.00 = **$70**
   - Full documents (DOT ≈ 15 pp): ≈ 10 × $16 + 10 × $3 = **≈ $190–$320**
3. A person has to pick the 20 instrument numbers in the viewer, since we can't automate past the CAPTCHA.

When copies are in hand, the test is mechanical: `tesseract` 5.x (apt package, not installed yet) → fixed regex set (`\$\s?[\d,]+\.\d{2}`, "principal sum of", "maturity date", "final payment due", "judgment in the amount of") → hit rate per field, compared against hand-read values. No model, no tuning.

---

## 4. Is Monongalia a good pilot?

**Works well:**
- The best open parcel data I've seen for a WV county: ArcGIS layer with owner, mailing address, appraised values and deed book/page, plus ParcelWeb ownership history with sale prices and survivorship and marital flags.
- Per-parcel paid/unpaid tax status is open.
- Online recorder index and images exist, which is rare in WV, so a sanctioned export is plausible.
- University town with many LLC-owned rentals, which gives realistic test cases for LLC officer/agent linking.

**Problems:**
1. **Recorder automation is blocked** (CAPTCHA + view-only terms). The adapter you rank most valuable can't be built until the Clerk agrees to an export.
2. **Court judgments are behind WVPASS login.** A bulk request goes to the Supreme Court Administrative Office.
3. **SOS bulk data costs money** (§2.5).
4. **WV isn't one of the buyer's enforcement states.** the buyer's list is FL, OH, LA, NY, NJ, IN, MI, GA, AL, TX, CA, NC, SC, PA. A Monongalia lead list may produce files the buyer wouldn't buy unless it adds WV or works them through a partner.
5. Small volume: about 106K people. The count of commercial judgments ≥ $30K and ≥ 2 years old may be in the dozens, not hundreds. Fine for golden files, thin for a ranked CSV.

**Recommendation:** keep Monongalia for Tier-1 parcel and ownership work and as the schema test bed, since its open data is good. Send the Clerk and Supreme Court requests now. In parallel, consider a second pilot in an enforcement state with published bulk recorder data. **Hillsborough County, FL** is a candidate: the Clerk publishes three Official Records index files per business day plus monthly civil bulk files (FROM SEARCH, `hillsclerk.com/Records-and-Reports/Public-Data-Files`), and Florida's statewide parcel file is free (see §5). I haven't verified it in depth; that would be a short follow-up if you want it.

---

<!-- 5. 50-state catalog -->

## 6. Proposed schema

### 6.1 Design rules
- **Three layers.**
  - `raw/`: the bytes we fetched, as Parquet or original files with a sha256 hash, partitioned `source/county/retrieved_date`.
  - `core`: normalized DuckDB tables, append-only.
  - `derived`: rule outputs, each row citing the core rows it used.
- **Mentions are never merged.** A name as printed on a document is a `party` row. Linking a party to a real-world `entity` happens only through `entity_link` rows, which carry the rule that fired and its evidence. A link either clears the cutoffs in config or goes to `review_queue`.
- **Bitemporal.** Every fact has a *valid* time (what the record says: recorded, filed, effective dates) and a *transaction* time (when we learned it: `retrieved_at`, `superseded_at`). Re-fetches never update in place. A changed record closes the old row (`superseded_at`) and inserts a new one.
- **Deterministic IDs.** Primary keys are sha256 of natural keys (e.g. `county_fips|instrument_number`), not random UUIDs. The ingest clock is injected so fixture runs can be byte-identical.
- **Money** is `DECIMAL(14,2)`. Dates are `DATE`. Instants are `TIMESTAMPTZ` in UTC.

### 6.2 Provenance and temporal columns (on every fact table)
| Column | Type | Null? | Meaning |
|---|---|---|---|
| `source_record_id` | VARCHAR | NOT NULL | FK to `source_record`, the exact row/page/feature we read |
| `source_id` | VARCHAR | NOT NULL | e.g. `wv.monongalia.assessor.arcgis` |
| `jurisdiction` | VARCHAR | NOT NULL | `54061` (state+county FIPS) or court id (`wvnd`, `wvnb`) |
| `record_key` | VARCHAR | NOT NULL | instrument number / book-page / case number / parcel id / SOS id |
| `source_uri` | VARCHAR | NOT NULL | URL with query, or `file://…#row=` |
| `retrieved_at` | TIMESTAMPTZ | NOT NULL | when we fetched it |
| `content_sha256` | VARCHAR | NOT NULL | hash of the raw payload |
| `event_date` | DATE | per table | recorded / filed / entered / sale date: the valid-time anchor |
| `valid_from`, `valid_to` | DATE | `valid_to` null = still true | for stateful facts (ownership, assessment year, entity status) |
| `ingested_at` | TIMESTAMPTZ | NOT NULL | load time (injected clock) |
| `superseded_at` | TIMESTAMPTZ | null = current | set when a later fetch changes the fact |

As-of query pattern: `valid_from <= :d AND (valid_to IS NULL OR valid_to > :d) AND retrieved_at <= :known AND (superseded_at IS NULL OR superseded_at > :known)`.

### 6.3 Provenance tables
| Table | Key columns | Purpose |
|---|---|---|
| `source` | `source_id`, `kind` (recorder/assessor/court/sos/tax/pacer/parcel_statewide), `jurisdiction`, `access_method` (bulk/api/arcgis/feed/html), `base_url`, `terms_url`, `terms_summary`, `robots_checked_at`, `cost_model` | registry of adapters' sources |
| `fetch` | `fetch_id`, `source_id`, `adapter`, `adapter_version`, `request` (url+params or file), `retrieved_at`, `http_status`, `content_sha256`, `raw_path`, `bytes` | one row per retrieval |
| `source_record` | `source_record_id`, `fetch_id`, `source_id`, `record_key`, `record_type`, `raw_sha256`, `first_seen_at`, `last_seen_at` | row-level provenance that every fact points to |

### 6.4 People, businesses and resolution
| Table | Key columns | Notes |
|---|---|---|
| `party` | `party_id`, `raw_name`, `party_kind` (person/org/unknown), `last`, `first`, `middle`, `suffix`, `org_name_norm`, `org_form` (LLC/INC/LP/…), `address_id`, + provenance | one row per name *as printed*, per source record |
| `address` | `address_id`, `line1`, `line2`, `city`, `state`, `zip5`, `norm_key` | normalized (USPS abbreviations, no ML), used as a corroboration signal |
| `entity` | `entity_id`, `entity_kind` (person/org), `display_name`, `created_by_link_id` | resolved real-world actor. Exists only if a link created it |
| `entity_link` | `link_id`, `party_id`, `entity_id`, `rule_id`, `rule_version`, `name_score`, `signals` (JSON: same_address / same_agent / same_parcel / same_case), `decision` (auto/review/rejected/human_accept/human_reject), `decided_at`, `decided_by` | invariant: every party→entity mapping has exactly one active link row |
| `review_queue` | `link_id`, `reason` (below cutoff / single signal / conflict), `opened_at`, `closed_at` | never silently merged |
| `business` | `sos_id`, `jurisdiction`, `name`, `org_form`, `status`, `formed_on`, `status_date`, `principal_address_id`, `mailing_address_id`, + provenance, `valid_from/to` | Secretary of State entity |
| `business_role` | `sos_id`, `party_id`, `role` (member/manager/officer/organizer/registered_agent/incorporator), `title`, `valid_from/to`, + provenance | LLC officer/agent edges |

### 6.5 Property
| Table | Key columns | Notes |
|---|---|---|
| `parcel` | `parcel_uid` (`54061-01-01-1`), `jurisdiction`, `dist`, `map`, `parcel`, `subparcel`, `parid_raw` | identity only |
| `parcel_geometry` | `parcel_uid`, `geom` (GEOMETRY, EPSG:4326), `acres`, `valid_from/to`, + provenance | DuckDB spatial |
| `parcel_assessment` | `parcel_uid`, `tax_year`, `appraised_land`, `appraised_bldg`, `appraised_total`, `assessed_value` (if published), `class`, + provenance | tax year is the valid-time key |
| `ownership_period` | `parcel_uid`, `party_id`, `owner_seq`, `pct_owned`, `life_estate`, `survivorship`, `marital_status_raw`, `deed_book`, `deed_page`, `sale_price`, `warranty_type`, `valid_from` (Date From), `valid_to` (Date Thru), + provenance | ParcelWeb history and statewide/assessor snapshots |

### 6.6 Recorded documents
| Table | Key columns | Notes |
|---|---|---|
| `instrument` | `instrument_uid`, `jurisdiction`, `instrument_number`, `book_type`, `book`, `page`, `doc_type_raw`, `doc_type` (enum below), `recorded_at`, `executed_on`, `consideration`, `principal_amount`, `max_secured_amount`, `maturity_date`, `amount_source` (index/ocr/assessor/manual), `legal_desc_raw`, + provenance | one row per recorded instrument |
| `instrument_party` | `instrument_uid`, `party_id`, `role` (grantor/grantee/borrower/lender/trustee/beneficiary/creditor/debtor/assignor/assignee), `seq` | |
| `instrument_parcel` | `instrument_uid`, `parcel_uid`, `method` (book_page_xref / assessor_deed_ref / legal_desc_rule / manual), `evidence` | how a document was tied to a parcel |
| `instrument_ref` | `from_uid`, `to_uid`, `ref_type` (releases / partial_release / assigns / modifies / extends / subordinates / substitutes_trustee / corrects / re_records / satisfies_judgment), `method` (index_xref / notation / ocr / manual), + provenance | a release points at exactly the lien it releases |
| `instrument_image` | `instrument_uid`, `page_no`, `sha256`, `path`, `obtained_via`, `cost` | only if images are obtained legitimately |
| `ocr_field` *(only if Tesseract is approved)* | `instrument_uid`, `page_no`, `field`, `value`, `regex_id`, `text_span`, `tesseract_version` | deterministic given image + version + regex |

`doc_type` enum: `DEED, DEED_OF_TRUST, MORTGAGE, ASSIGNMENT, MODIFICATION, EXTENSION, SUBORDINATION, RELEASE, PARTIAL_RELEASE, SUBSTITUTE_TRUSTEE, TRUSTEE_REPORT, JUDGMENT_LIEN, ABSTRACT_OF_JUDGMENT, EXECUTION, LIS_PENDENS, MECHANICS_LIEN, STATUTORY_LIEN, TAX_LIEN_STATE, TAX_LIEN_FEDERAL, FIXTURE_FILING, LAND_CONTRACT, LEASE, POWER_OF_ATTORNEY, COURT_ORDER, AFFIDAVIT, OTHER`. The raw-to-enum mapping table lives in config.

### 6.7 Courts
| Table | Key columns | Notes |
|---|---|---|
| `court_case` | `case_uid`, `court_id` (`wv.cir.monongalia`, `wvnd`, `wvnb`), `case_number_raw`, `case_number_norm`, `case_type`, `nature_of_suit`, `filed_on`, `closed_on`, `status`, + provenance | |
| `case_party` | `case_uid`, `party_id`, `role` (plaintiff/defendant/debtor/creditor/trustee/garnishee) | |
| `judgment` | `judgment_uid`, `case_uid`, `entered_on`, `principal`, `interest`, `costs`, `rate`, `judgment_type` (money/deficiency/default/consent), `lien_instrument_uid` (Clerk docket entry, if found), + provenance | |
| `judgment_event` | `judgment_uid`, `event` (docketed/abstracted/renewed/revived/assigned/partial_satisfaction/satisfied/vacated/execution_issued), `event_date`, `amount`, + provenance | judgment life as a sequence of events, not a status column |
| `bankruptcy` | `case_uid`, `chapter`, `petition_on`, `discharge_on`, `dismissed_on`, `converted_on`, `trustee_party_id`, `asset_case` | |
| `docket_entry` | `case_uid`, `entry_no`, `entry_date`, `text`, + provenance | PACER / RSS / RECAP |

### 6.8 Tax
| Table | Key columns |
|---|---|
| `tax_bill` | `parcel_uid`, `tax_year`, `ticket`, `taxpayer_party_id`, `billed`, `first_half_paid_on`, `second_half_paid_on`, `unpaid_amount`, `as_of`, + provenance |
| `tax_sale_event` | `parcel_uid`, `tax_year`, `event` (listed_delinquent / certified_to_auditor / sold / redeemed / deed_issued), `event_date`, `amount`, `purchaser_party_id`, + provenance |

### 6.9 Derived (Phases 4–5)
| Table | Key columns |
|---|---|
| `rule_run` | `run_id`, `git_sha`, `config_sha256`, `as_of`, `known_as_of`, `started_at` |
| `rule_output` | `run_id`, `rule_id`, `subject_kind`, `subject_id`, `result` (JSON), `citations` (list of `table:row_id`) |
| `lien_stack` (view) | per parcel as of a date: open liens ordered by the configured priority rule, each with its citations |

### 6.10 Graph view
The graph in the brief is a set of edge views over these tables: `entity —link→ party —role→ instrument/case/business —→ parcel`. No separate graph store in v1. DuckDB recursive CTEs cover LLC→member→LLC chains.


## 7. Open questions and places I'd otherwise guess

### Access and data
1. **Recorder index columns.** Does the IDX grid show consideration, loan amount or judgment amount, and does a release show the instrument number it releases? *Needs a person: pass the slider once, search any common surname, and screenshot the grid and detail panel.* (5 minutes)
2. **Clerk export.** Will the Clerk provide an electronic index export (all books, with cross-references) and images under §59-1-10(e)? At what fee, in what format, how often? Any resale or use restrictions? Draft request:
   > "Under W. Va. Code §59-1-10(e) and the WV FOIA (§29B-1), we request an electronic copy of the land-records index (deeds, deeds of trust, liens, judgment lien docket, releases, lis pendens, trustee reports) from [start year] to present, with instrument number, book/page, type, recording date, all parties, and cross-references, in CSV or any machine-readable format, plus a quote for monthly updates and for document images."
3. **Circuit court bulk data.** Does the WV Supreme Court Administrative Office provide bulk civil case and judgment data outside WVPASS? Under what terms?
4. **ArcGIS parcel layer license.** No license text on the county's layer. Is commercial use OK? (Ask the Assessor. Data is public record, but confirm.)
5. **Assessed vs appraised.** The layer gives appraised land and building. Is assessed = 60% of appraised for every class in Monongalia? This goes in config as a TODO for you, not in code.
6. **wvias.io** (State Tax Department IAS) property record cards: not yet checked. Allow the host if you want this verified.
7. **Sheriff tax site security issue** (§2.4): do you want to notify the county? I won't touch it beyond normal searches.

### Legal rules (config with TODO, never encoded by me)
8. Lien priority rule for WV: race-notice under §40-1-9? How do judgment liens rank against later deeds of trust? Purchase-money priority? Federal and state tax lien super-priority?
9. Judgment lien life and renewal in WV (§38-3-18 and related): duration, renewal mechanics, and whether renewal keeps priority.
10. Deed-of-trust lapse ("ancient mortgage") rule for WV, needed for the buyer's lapsed-mortgage screen. Which date starts the clock, and what is the period?
11. Homestead exemption amount and who qualifies, in WV and in each enforcement state.
12. Tenancy by the entirety: does WV recognize it? ParcelWeb exposes "Survivorship" and "Husband/Wife" flags, so the code can *flag* but not *decide*.
13. Statute-of-limitations table: you said you'd fill it in. I'll ship `config/sol.yaml` with every state present and every value `null # TODO(Brandon)`.
14. "Nominal consideration" threshold for transfer flags (e.g. ≤ $10, or < X% of appraised). Config value, needs your number.
15. "Related-party grantee" definition: same surname? same mailing address? LLC where the debtor is a member or agent? Each is a separate config-switchable rule.

### Scope
16. Pilot: Monongalia only, or Monongalia + one county in an enforcement state (Hillsborough, FL suggested)? See §4.
17. the buyer buys **commercial** judgments ≥ $30K, roughly ≥ 2 years old. Should the Phase 5 CSV filter to these by default?
18. "No evals": I read this as dropping the gold-set precision/recall harness from the earlier draft and keeping only your exact-match golden files (`tests/golden/`, written by you) and the Phase 5 snapshot. Correct?
19. The invariant "no lien without a parcel" conflicts with WV judgment liens, which attach to all of the debtor's real property in the county, not to one parcel. Proposal: judgment liens link to parcels *through* the debtor's resolved ownership, and the invariant applies to parcel-specific liens (deeds of trust, mechanics' liens, lis pendens). Confirm.
20. CI protection: GitHub branch protection and CODEOWNERS need repo-admin settings. I can write the files, but you have to turn branch protection on. Also: add CAPTCHA-solving packages to the blocklist?

### Where I'd have to guess (and won't)
- Any legal rule above.
- IDX column semantics without a human look (Q1).
- Mapping each raw IDX doc-type label to the `doc_type` enum. I'll build the mapping from the export and you review it.
- Name-match cutoffs for rapidfuzz. I'll propose starting values in config, and you approve them.

