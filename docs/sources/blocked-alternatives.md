# Alternatives for blocked and unbuilt sources

Checked 2026-11-25, item by item, against the blocked/unbuilt audit of the research reports.
Each row says what was found through a different allowed channel (another official
publisher, a different dataset covering the same need, or a free keyless API) and whether it
is now built. Rules applied: no login, account, key, token, CAPTCHA, payment or signed
agreement; robots.txt as read by the project's own client (`equity.adapters.http`, which
honours `*` wildcards); no working around Cloudflare, Akamai, Imperva, F5 or other bot
protection. "Proxy-blocked here" means this environment's egress proxy refused or dropped
the connection, not the site. Items that other helpers are building (court ECF RSS, Fulton
GA, LA LAHD, Cincinnati, Louisville, land banks, NYSDOT, NY ABO, Oregon UCC, LA County
defaulted roll, Maricopa layer 0, NYC DOB legacy permits, Boulder voter file, and the federal
list) are not repeated here.

Internal use only, no redistribution: where a source carries a use limit it is recorded in
`use_restrictions` (shown as `RESTRICTED[...]` in the source row) and in the terms summary.

## Built in this pass

| source_id | What it gives | Rows (approx.) | Alternative for |
|---|---|---|---|
| `in.dlgf.sales_disclosures` | Indiana sales disclosure forms, statewide, July 2008 to this week: seller and buyer names and addresses, parcels, price, land-contract / sheriff-sale / quitclaim / foreclosure flags (STATS Indiana zips; new adapter `equity.adapters.indiana_sdf`) | ~3.5M forms (about 150K-270K a year) | Indiana SDF (host now reachable); recorder deed indexes; voter-file substitute for IN (buyer addresses) |
| `fl.fwc.recreational_licenses` | Every current Florida hunting and fishing license: holder name, street, city, ZIP (phone, email, age in the raw row) | ~4M license rows (712 MB; one row per license held) | FL voter file (request-only); the voter report's "hunting and fishing licenses" substitute |
| `fl.fwc.commercial_licenses` | Florida commercial fishing and dealer licenses (14 files) with holder and mailing address | ~20K | same |
| `md.mhic.guaranty_fund_awards` | Maryland Home Improvement Commission disciplinary actions FY2009-FY2025, mostly Guaranty Fund awards (contractor owes the Fund; amount parsed from the text) | ~1,500 | NJ LFCP / OH LFCP / NV NSCB recovery-fund payouts |
| `la.ebr.building_permits` | East Baton Rouge permits with owner, applicant and contractor names, site address | 145K | Building permits (EBR 7fq7-8j7r) |
| `il.chicago.building_permits` | Chicago permits with up to 15 contacts (owners, applicants, trades) and city/ZIP | 854K | Building permits (Chicago) |
| `tx.austin.construction_permits` | Austin permits with contractor and applicant names and addresses (no owner names) | 2.39M | Building permits (Austin) |
| `wa.seattle.building_permits` | Seattle permits that name the contractor company | 32K | Building permits (Seattle); tagged `no_commercial_name_address_lists` |
| `il.ptax.transfers` (extended) | Co-buyers and co-sellers on Illinois transfer declarations, joined from dwt7-rycp and rzbz-mw8b | +2.38M names | IL PTAX additional buyer/seller sets |

Adapter changes that made these possible: config/liens `link_from.all` (one partition per
file listed on an index page, keyed by the period in the file name), `amount_in_text` (the
first dollar figure inside a text column), Socrata `enrich` (all matching rows of a companion
dataset, joined) and `use_restrictions` for lien configs.

## Every blocked item

| Item | Alternative found | Status | Notes |
|---|---|---|---|
| CourtListener bulk dockets | None with a clear licence; the courts' own RSS feeds are being built by another helper | not available | Licence still unresolved (CC BY-ND vs public domain mark) |
| Harris County TX Clerk foreclosure notices (FRCL_R.aspx) | None (no open-data or ArcGIS copy found) | not available | Existing `tx.harris.delinquent_taxes`, `tx.harris.tax_judgments` cover the tax side only |
| Statewide public-notice sites (PNRC, FL 50.0211) | None | not available | Search portals, no bulk file |
| Detroit DAH blight archive (629,962 tickets) | The current DAH layer on services2.arcgis.com already holds 915,638 tickets back to 2004 | built (`mi.detroit.blight_judgments`) | The opengis.detroitmi.gov archive service now answers 404 "Service not found" |
| Franklin OH Municipal Court eviction CSVs | Host now reachable (monthly CSVs with tenant and landlord names and addresses) | not available | robots.txt `Disallow: /storage/shared/*` covers the CSVs; not used |
| Dallas County JP eviction list | None | not available | The page now answers 404 |
| MD District Court eviction data (mvqb-b4hf) | Host now reachable (814,426 rows) | not built | No party names: case number, tenant city/ZIP, event dates only |
| MI EGLE perfected environmental liens | None | not available | www.michigan.gov answers Akamai 403 |
| Iowa DNR environmental (UST) liens | PDF reachable (www.iowadnr.gov/media/8397) | not built | 3 liens on the list; wrapped PDF cells; not worth an extractor |
| WI DNR contamination liens | Not found as a list | not available | |
| SC DOR top delinquent taxpayers | The list is served by MyDORWAY (mydorway.dor.sc.gov) | proxy-blocked here | dor.sc.gov itself is reachable and says every listed taxpayer has a filed lien; retry from an allowed network |
| NY court landlord-tenant XML (ww2.nycourts.gov) | None | not available | Redirects to www.nycourts.gov, Cloudflare challenge |
| NJ Lawyers' Fund (LFCP) payouts | None | not available | njcourts.gov serves an Imperva "Pardon Our Interruption" challenge |
| OH LFCP reimbursements | Page reachable | not built | The reimbursements page carries no per-claim table |
| MD MHIC Guaranty Fund awards | Yearly disciplinary pages on labor.maryland.gov | built (`md.mhic.guaranty_fund_awards`) | robots allows /license/; Content-Signal ai-train=no, ai-input=no (parsed deterministically) |
| NV NSCB Recovery Fund awards | PDFs are press releases | not built | Counts and a few names in prose, no table |
| TX abstract-of-judgment indexes (Tarrant, Fort Bend), OH certificates of judgment (Franklin), PA prothonotaries, FL clerks (Pinellas, Orange, Duval) | None free | needs request | Records requests or sold extracts |
| Georgia GSCCCA lien index | None | needs request (paid) | |
| Santa Clara civil index, MD District Court judgments ($2,775), MN bulk, CT bulk civil, IN IOCS | None | needs request (fee / licence) | |
| Probate indexes | None | not available | No bulk anywhere checked |
| Bankruptcy claims registers (Kroll, Epiq, Stretto) | None | not available | robots / 403 |
| Bankruptcy RSS disallowed by robots (pamb, mdb, canb, arwb, areb, kyeb, utb, wawb, nmb, wiwb) | None | not available | robots.txt |
| King County WA sales file EXTR_RPSale.csv | None without the RCW 42.56.070(9) acknowledgement | needs legal read | Unchanged (reports/Legal reads needed.md) |
| Broward FL official-records FTP; Pasco subscription | None | needs request (subscription) | |
| Other FL clerks' free subscriber files | Hillsborough's publicrec site also publishes a daily "Money in Escrow" (foreclosure sale surplus) PDF and a tax-deed claim workbook | not built | Hillsborough OR, civil and garnishment files are already built; the escrow PDF wraps case captions across lines |
| IL PTAX additional buyers (dwt7-rycp) and sellers (rzbz-mw8b) | Hosts now reachable (1,274,547 and 1,105,502 names, Public Domain) | built (joined into `il.ptax.transfers`) | New Socrata `enrich` in config/liens: every co-buyer and co-seller becomes a grantee / grantor on the declaration's DEED |
| IL PTAX Cook/Chicago forms (vbnw-q5s8) | Reachable | not built | Form flags and amounts, no names |
| Cook Recorder 2011-15 mortgages / foreclosures (33fu-uwca, myuk-usmm, 4f2q-h3b7) | Reachable | not built | PIN, document type and amount, no party names; 2015 and older |
| CT real estate sales 5mzw-sjtu | Reachable | not built | No names; `ct.cama.sales` already carries grantor and grantee |
| Indiana SDF (STATS Indiana) | Host now reachable | built (`in.dlgf.sales_disclosures`) | Tagged `no_commercial_name_address_lists` (IC 5-14-3-3(f)), as `in.statewide.parcels` |
| WI RETR | None | not available | DOR moved the data into My Tax Account (login) |
| Wake County NC real estate data file | None | not available | services.wake.gov answers 403 |
| Mechanic's liens as a separate type | None | not available | FL LN code not separable |
| Building permits: East Baton Rouge 7fq7-8j7r | Socrata, Public Domain | built (`la.ebr.building_permits`) | Owner tied to the site address (no parcel id) |
| Building permits: Collin County 82ee-gbj5 | None | proxy-blocked here | data.collincountytx.gov TLS connect fails through the proxy |
| Building permits: Chicago, Austin, Seattle | Socrata portals | built (`il.chicago.building_permits`, `tx.austin.construction_permits`, `wa.seattle.building_permits`) | Chicago PINs are 10-digit block PINs, Austin TCAD ids mixed, so no parcel links |
| Recorder records-request pilot (FL, NY, TX Tarrant, GA, MD, NC Wake, WV Harrison, IA ICRA, ID Ada, CT, NV, WY, OH, PA; HI BOC) | None | needs request | |
| Tennessee "Property Boundaries Public Use" owners | Four county owner layers are already loaded (Davidson, Hamilton, Rutherford, Washington) | not available beyond those | Shelby: Cloudflare challenge; Knox (KGIS): 401 login; Williamson and Clarksville GIS proxy-blocked here |
| Clark County NV owner roll | None | needs request (sold) | No free owner layer in ArcGIS Online search |
| SanGIS owner names | None official | not available | Only private republications carry names |
| California counties' owner names | None | not available | Redacted by the counties |
| NJ owner names (Daniel's Law) | None | not available | Masked by law |
| Montana statewide cadastral | Same layer on services.arcgis.com | built earlier (`mt.statewide.parcels`) | robots on the state host only |
| NM statewide parcels (token), TN owner layers (token), KY statewide (agencies) | County layers (other helpers) | not available statewide | |
| Ohio SWVF voter file | None | built, waiting on file | All ohiosos.gov hosts still "Website Maintenance" 403 |
| FL voter file (request) | FWC hunting/fishing license holders: current name and address | built (`fl.fwc.recreational_licenses`, `fl.fwc.commercial_licenses`) | No use restriction on the FWC page |
| MI, CO, WI, AR, MS, AK, DC voter files (request/delivery) | None new (existing license and parcel layers remain the substitutes) | needs request | Hunting/fishing lists in these states are shielded or not published |
| TX, ID, NJ, RI, SC, IN conditional voter files | IN: `in.dlgf.sales_disclosures` (buyer and seller addresses); TX: the existing TX license lists | built (IN, partial substitute) | ID, NJ, RI, SC: none new |
| CA SCO unclaimed property and estates of deceased owners | `ca.orange_county.unclaimed_property` (7M-row county copy, already built); city stale-check lists (Roseville vtyn-52t8, 3,768 names; Marin er4x-svwp, 97) | not built (the city lists) | SCO download still behind Cloudflare. The city lists publish names only, no address; person lists must carry addresses (tests/adapters/test_person_lists.py), so they were left out |
| TX Comptroller unclaimed property | City of Austin unclaimed property (h3i4-5e5v, 47,822 last/first names) | not built | Names only, no address or amount (same reason); statewide file still email request |
| NY OSC owner-name file | None | needs request | |
| OH remaining county unclaimed-funds notices | None | not available | com.ohio.gov index still 404 |
| NC AOC unclaimed PDFs; PA Bulletin notices | None | not available | 403 / robots `Disallow: /` |
| MD, MA, NJ full, OH full, RI, KY, FL, VA, WV, DC, CT, GA, SC, AL, MS, TN, MI, IN, AK, ND, WY, CO, OR, AR, KS, HI, NM, MT unclaimed files | None free | needs request / fee | Ramsey County MN lists (ea8s-irrm, t2fe-qrnd) exist but robots.txt disallows /resource/ |
| WA, MN, IL, DE, UT, ID, IA, LA, NV, AZ, NE, SD unclaimed | None | not available | Barred or search-only |
| FAA aircraft registry, USPTO, ATF FFL, OSHA, DOL WHD, FJC IDB, FCC ULS | None | built, waiting on file | Each official channel needs a key or sits behind Akamai / AWS WAF / robots; no other official publisher found |
| GSA Auctions | None | not available | api.data.gov key (DEMO_KEY is still a key) |
| BLM sale parcels, BOEM lease owners, MT DNRC leases | BOEM lease-owner files reachable on data.boem.gov | not built | Company names only, low value for locating people |
| HMDA LAR, Freddie PMMS | Reachable | not built | No names (not people data) |
| Business registries blocked (OH, AK, NV, VT, VA, WA, FL Sunbiz, MD, KY, MN, WY, GA, TX, NC, OK, ND, WI, SD, WV, LA, NE, MT, AR, AZ, NJ, CA, DE, MS, ME, TN, MI, IL, NH, IN, MA) | No state open-data copy found (Socrata catalog search); existing city business-licence and tax lists remain the partial substitute | not available | Ohio SOS still in Cloudflare maintenance; FL Sunbiz SFTP needs the published login (legal read) |
| GLEIF golden copy | CC0 confirmed on gleif.org (open data page); api.gleif.org free, no key: 366,254 US LEIs | not built | Needs a JSON:API adapter or streaming the 488 MB golden-copy zip; next step |
| Boston licence data (robots), AZ ROC (Cloudflare), NC contractors (robots), NC real estate (403) | None | not available | |
| CA CSLB full licence file ($235) | CSLB's Public Data Portal offers the License Master, Personnel and Workers' Comp files free ("There is no charge for this service") | needs hand download | An F5 WAF rejects a scripted postback of the portal form; a person can save the CSV and it could load as a delivered file |
| FL FWC hunting/fishing licence holders | myfwc.com public-record files | built (`fl.fwc.recreational_licenses`, `fl.fwc.commercial_licenses`) | |
| Surplus-funds PDFs (Gwinnett excess funds, Wise TX, Hillsborough tax deed) | Pages reachable; no machine-readable list linked (Gwinnett and Wise), Hillsborough claim workbook dated 2023 | not built | Per-county extractors still needed |

## Other federal sale notices (checked 2026-11-26)

The Federal Register API was searched for NOTICE documents on loan, note and asset sales and
surplus real property beyond the HUD and BLM queries already loaded
(`us.federalregister.loan_sales`, `us.federalregister.realty_notices`):

| Agency | Result |
|---|---|
| USDA (Rural Development, RBCS) | Two Intermediary Relending Program loan-sale invitations, 1999-2000; none since. Not added. |
| SBA | Business and disaster loan sale notices 2000-2002 only; SBA stopped noticing sales in the Federal Register. Not added. |
| VA | None. |
| GSA | No sale notices: GSA lists surplus real property on realestatesales.gov, whose robots.txt disallows everything. Not added. |
| Treasury, FDIC, others | Only HUD notices match "loan sale" since 2010. |

HUD remains the only federal agency noticing loan sales in the Federal Register.

## Discovery leads reviewed (2026-11-27)

`equity.discovery` returned 90 candidates. 45 are land-bank inventories, Survey123 forms, or
national and foreign layers (land banks are owned by the land bank, so they name no debtor);
19 are the Brooklyn Borough President's 2024 tax-lien maps, one per community district (water
debt by block and lot, no owner); the rest were read field by field:

| Lead | Rows | Result |
|---|---|---|
| Pitt County NC "Delinquent Taxes" (gis.pittcountync.gov) | 8,573 | Not added: a log of payment transactions against bills (TXN_DATE, AMOUNT, BILLALLOCATION), keyed by Pitt's short parcel number, not a list of open balances. Needs a design (net payments per bill) before it can stand for a debt. |
| "DC Tax Liens" (dcgis.org) | 380 | Not added: dcgis.org appears to be Douglas County NE's GIS, not the District's; Douglas County tax liens are already loaded (`ne.douglas.tax_liens`). |
| Muncie IN Fall 2026 tax sale | 630 | Owner name, PIN, minimum bid. Publisher not confirmed (a personal ArcGIS account); held until the county's own list is found. |
| Hammond IN 2027 tax sale | 142 | Deeded owner, mailing address, parcel. Published by a sanitary-district account; held for the same reason. |
| Fulton GA "Tax Deed Activity" (Socrata) | 34,300 | Not a debt list: the assessor's internal deed-processing work queue. |
| Frederick County, McPherson KS, other "tax sale" layers | 2-304 | Too small, no owner field, or a geocoded address list without parcel or owner. |
| Cochise AZ 2026 tax deed layers | — | Already loaded (`az.cochise.tax_deed_auction`). |
| WA candidate surplus funds, Massachusetts settlements | — | Campaign finance and state settlements, not property debts. |

### Wider search, all years (2026-11-27)

ArcGIS Online searched for public layers titled delinquent, tax lien, unpaid tax and tax sale
list, any age, minus configured URLs (235 items). Added: `nc.pitt.delinquent_taxes` (the bill
rows of Pitt's table, owner joined from its parcel table) and `sc.beaufort.delinquent_taxes`
(the Treasurer's interactive tax map). Read and not added:

| Lead | Why not |
|---|---|
| Pittsburgh URA city_tax_delinquent_3yr (12,313) | Same data as `pa.pittsburgh.tax_delinquency` (WPRDC). |
| LA County TTC "Secured Property Taxes Liens" (2.4M) | The current year's direct assessments on every parcel (water, flood control, lighting), not delinquencies. |
| Lake County CO 2021-2025 "Tax Liens" | Prior years' tax lien sales; the current 2026 sale is loaded (`co.lake.tax_lien_sale`); redemption is not shown. |
| Gregg TX delinquent accounts (403), Tyler TX delinquent properties (468) | City copies of county lists (Longview, Tyler), small; Tyler's has no owner. Not in any run's counties. |
| Harrison MS, Midland, Elgin/Shorb, Tax_Delinquent (MSIDesign, Censeo) and similar | Student, consultant or planning copies; or already loaded (Harrison). |
| Brooklyn 2024 tax lien maps | Borough President's maps of the 2024 NYC lien sale (water debt by block and lot, no owner). |

### Reachable-portal ranked list, status (2026-11-27)

From `research_notes/More free judgment sources/reachable_portals_sweep.md`: #1 NYC DOF Property
Charges Balance is now built (`ny.nyc.dof.past_due_charges`); #2, #5, #9 and #12 were already
loaded. Not added:

| # | Dataset | Why not |
|---|---|---|
| 7 | NYC Law Dept civil litigation `pjgc-h7uv` | Its Tax & Bankruptcy cases are mostly owners' assessment challenges against the City, not debts; 136 City-plaintiff judgments only. |
| 10 | NYC LL159 vacate relocation charges `3bkg-usya` | Unpaid charges are billed through the DOF statement of account, so they are in the DOF past-due charges. |
| 4 | NOLA adjudication fines and fees `f5zm-xkyr` | `la.nola.code_hearing_judgments` already carries each case's unpaid fees. |

### Sweep of the servers we already read (2026-11-27)

Every ArcGIS server and ArcGIS Online org already in config/ was listed for services and
layers named delinquent, tax sale, tax lien, foreclosure, forfeit, redemption, surplus or
excess. Added: `ga.dekalb.delinquent_taxes`, `md.baltimore_city.tax_sale_2026`,
`oh.franklin.delinquent_taxes`, `ga.richmond.delinquent_taxes`; `nc.buncombe.unpaid_bills` now holds back the current roll.

| Lead | Status |
|---|---|
| Mahoning OH county "ALL TAX DELINQUENT PARCELS" (gisapp.mahoningcountyoh.gov, 25,464 parcels with owner, mailing address and a DELINQUENT amount) | **Owner decision:** it overlaps `oh.mahoning.delinquent_taxes` (15,983, a Youngstown/county layer). Loading both would count the same parcels twice; replace one with the other, or keep the current one. |
| Baltimore City 2025 tax sale (15,686, $168.9M) | Held back: no redemption shown, so liens paid since the 2025 sale would count as open. |
| Douglas CO investor- and county-held tax liens (1,395) | Account number only (no parcel id, no owner): cannot be linked yet. |
| Cuyahoga, Dakota MN, St. Mary's MD, Cochise, Kalamazoo, Bluefield layers | Already loaded under other names. |
| Muncie and Hammond IN tax sale lists | Held: Indiana limits commercial use of name and address lists from public agencies (IC 5-14-3-3(f), docs/coverage.md); owner decision. |
| Lexington SC "DelinquentTaxParcels_2023" (1,138) | A 2023 list; not current. |
| Wyandotte KS Tax_Delinquent, Utah County UT May tax sale | The servers answer 403 and 401 (login required). |
| Butler KS 2018 tax sale (7), Evansville IN tax sale layers | Stale or tiny; Indiana layers held for the IC 5-14-3-3(f) decision. |

### Free-data list: big counties (2026-11-27)

Items from the 100-item free-data list, starting with the large counties already in runs.
Liquor licenses and the HUD items are skipped at the owner's request.

| County | Result |
|---|---|
| Dallas TX | **Built:** `tx.dallas.tax_roll_delinquent` (Tax Office TRW file, weekly, free): 24,715 delinquent real property accounts, $240.4M; new TX-DALLAS run, linked by CAD account. |
| Tarrant TX | **Built:** `tx.tarrant.tax_roll_delinquent` (Tax Office roll export, weekly, free; crawl-delay 30 honored): 25,143 accounts, $78.6M base tax, 1,584 with a tax-suit judgment; new TX-TARRANT run, matched by name and address. |
| Summit OH | **Built:** `oh.summit.delinquent_taxes` (Fiscal Office CAMA export SC720_DELQ, weekly, free): 18,185 parcels with an amount, $204.8M; parcel-linked in OH-COUNTIES. |
| Collin TX | **Built:** `tx.collin.tax_roll_delinquent` (Tax Assessor delinquent tax roll zip, free; same collection-system file as Tarrant with Collin's layout): 8,707 delinquent real and commercial accounts, $28.8M base tax due, 152 with a tax-suit judgment; parcel-linked to `tx.statewide.parcels` (CAD id = PROP_ID) in a new TX-COLLIN run. |
| Hamilton TN | **Built:** `tn.hamilton.delinquent_taxes` (Trustee delinquent file CTRUDELQ, monthly, free): 11,879 unpaid real property bills on 7,459 parcels, $12.9M owed (2026-11-01 file); each bill names its year's owner; 11,190 linked to `tn.hamilton.parcels` by GISLINK in the TN run. The file's 40,000 business personal property bills (map PER) are not read. |
| Clark NV | **Built:** `nv.clark.delinquent_taxes_fy2026` (Treasurer's annual NRS 361.565 delinquency publication, Excel version): 13,984 parcels delinquent on 2026-05-06, $49.2M with penalties and costs; dated by that as-of date (an annual list: parcels redeemed since stay on it). In NV-COUNTIES, parcel-linked where `nv.clark.parcels` (Las Vegas Valley only) has the APN. |
| Wake NC, Durham NC | Blocked: the file hosts' robots.txt (services.wake.gov, dconc.gov) disallow all crawlers. Wake's daily delinquent file was not downloaded. |
| Pima AZ | The tax roll is sold ($50); the lien sale inventory is on the sale vendor's site. |
| Fulton GA | Sheriff's tax sale list is a scanned PDF (no text layer); no OCR is used. No other free bulk list found. |
| Wayne MI | Only the Treasurer's foreclosed-parcel PDF (parcel numbers, no owners); the auction site is the third-party sale platform. Not loaded. |
| Hennepin MN | No bulk delinquent file; delinquency is shown per parcel in the property search only (no scraping). |
| Palm Beach FL | Tax certificate and tax deed lists are on the vendor auction sites (login), not a county download. |
| El Paso TX | The tax roll file is sold ($73.20); paid sources need owner approval. |
| Bexar TX | No free tax roll export found; per-account search only. |
| Montgomery OH | Search tool only, no export. |

ArcGIS Online search for layers named delinquent, tax sale or tax lien that changed since
2026-06 (2026-11-27): most were already loaded. New ones:

| Layer | Status |
|---|---|
| Albany County NY "AC_DelinquentParcels_11_2026" (RPTSA, 5,174 parcels with owner and SWIS/print key, no amount) | **Owner decision:** the item's license reads "Not an Official Record. Not for use with Collection or Enforcement. Not a Legal Document." Not loaded. |
| Pittsburgh city_tax_delinquent_3yr, DC Tax Liens (380), Harris tax-delinquent parcels | Already covered by `pa.pittsburgh.tax_delinquency`, `dc.otr.delinquent_taxes`, `tx.harris.delinquent_taxes`. |
| Tyler TX Delinquent Properties (468, no owner), Washington Twp delinquencies (340), Dougherty GA 2026 tax sale (139), Shelby AL parcels to be bid (191), Blair PA judicial sale (30) | Small lists; left for a later pass. |
| Nassau County NY weekly unpaid-tax and lien reports (DocumentCenter, 2026-11-20) | Readable: the DQ110 "Delinquent Taxes Unpaid" PDFs (general and school, 441 pages each) parse with the in-house PDF reader into parcel (section/block/lot), owner name, tax year, amount and class; the base-tax CSVs carry no owner. Held for now: no owner address is printed and Nassau is not among the counties in `ny.statewide.parcels` (only unofficial third-party copies of its parcel layer exist), so rows could be matched by name alone. The DQ106 lien summaries list lien numbers and status per parcel without owners. |

### Sheriff and tax sale listings (2026-11-28)

| Source | Result |
|---|---|
| CivilView sheriff and constable sales, 16 more counties | **Built:** Lake IL, Stearns and St. Louis MN, Lorain, Medina and Allen OH, Pottawattamie and Story IA, Shawnee KS, Deschutes and Josephine OR, Snohomish WA, Canyon ID, Guadalupe TX (Constable Pct. 1), Orleans and Ascension Parish LA (with the writ amount). Same page and terms as the NJ and PA configs; wired into their state runs as foreclosure debts and snapshotted daily. |
| CivilView counties with no sales listed today | Palm Beach FL (2 rows, names cut off on the page), Maricopa AZ, Ocean NJ, Kent DE, Dallas County TX constables 1-5, McLennan, Rockwall and Guadalupe TX (other precincts), Champaign IL, Coweta GA, Pulaski AR, Richland OH, Santa Rosa FL, Scott IA: add when the pages carry sales. |
| Tarrant County constable monthly tax-sale listings | About 30 accounts per precinct with cause and account numbers only; the accounts and lawsuits are already in `tx.tarrant.tax_roll_delinquent`. |
| Harris County delinquent tax sale listing (hctax.net, 241 accounts for the 2026-12-01 sale) | Terms are disclaimers only; the accounts are judgments already in `tx.harris.tax_judgments`, so it would add only the sale date and minimum bid. Left for later. |
| Arkansas Commissioner of State Lands auction | Post-auction sales on the vendor's site (registration) and a search tool; no list download. |

### Free-only pass: parcels, state lists, business registries (2026-11-28)

The owner set the rule on 2026-11-28: nothing paid, PACER included (`config/pacer.yaml` keeps
`quarterly_ceiling: null`, which refuses every PACER request).

| Source | Result |
|---|---|
| Kent County MI parcels | The public layer (ParcelsPublicView) has no owner names; the open-data parcel services now answer "Token Required". |
| Will County IL parcels | The service's license bars redistribution or network use without the GIS Department's permission; owner fields not confirmed. Not loaded. |
| Illinois statewide parcels database (ISGS) | Token required. |
| Henrico VA tax parcels | The county's hosted copy is a 735-row 2022 extract. |
| Kentucky and West Virginia SOS bulk business data | Subscription services for prepaid account holders (paid). |
| Ohio SOS business reports (free, monthly) | The site answered with a maintenance page (HTTP 403) on 2026-11-28; retry. |
| South Carolina DOR top delinquent taxpayers | Lists sit in the MyDORWAY web app; the connection was refused from this environment. |
| Wyoming DOR excise delinquent taxpayer list | The page answers 404 (moved). |

### Owner decisions of 2026-11-28

The owner approved four held sources (API keys stay on hold):

| Source | Result |
|---|---|
| Albany County NY delinquent parcels | **Built:** `ny.albany.delinquent_parcels`, 5,174 parcels, parcel-linked to `ny.statewide.parcels` (SWIS + SBL) and `ny.local_rolls.parcels` (SWIS + print key) in the NY run. Tagged `not_for_collection_or_enforcement` from the item's license. |
| Indiana tax sale lists | **Built:** `in.hammond.tax_sale_2027` (142 Lake County parcels with owner mailing addresses, parcel-linked to `in.lake.parcels`), tagged `no_commercial_name_address_lists`. The Muncie list is the same sale as `in.delaware.tax_sale`, already loaded. Vanderburgh's 2026 tax sale layer (maps.evansvillegis.com) did not answer from this environment; retry. |
| Nassau County NY delinquent taxes | **Built:** `ny.nassau.delinquent_general_taxes` (6,592 parcels, $24.1M) and `ny.nassau.delinquent_school_taxes` (5,078 parcels, $47.6M) from the weekly DQ110 PDFs, tax year 2026, in the NY run. Nassau's towns are in `ny.local_rolls.parcels`, but the report's section/block/lot did not match the rolls' print keys in a spot check, so rows match by owner name. |
| Florida Sunbiz bulk files | Not built yet. The HTTPS portal (sftp.floridados.gov) has `robots.txt: Disallow: /` for all agents, so it is not used. The state's own instructions invite "a secure FTP client of your choice" with the published Public account, which robots.txt does not govern, but port 22 is closed from this environment: it would run from a GitHub Actions runner and needs an SFTP client library added to `pyproject.toml` (CODEOWNERS). |

### No-barrier pass (2026-11-28)

| Source | Result |
|---|---|
| Hamilton TN Trustee delinquent file, business personal property bills | **Built:** `tn.hamilton.personal_property_taxes`, 40,509 bills owed by 14,652 businesses, $12.0M (same free CTRUDELQ file as `tn.hamilton.delinquent_taxes`), in the TN run, matched by name and mailing address. |
| Summit OH Fiscal Office conveyances (SC719_CVPAR) | 624,878 conveyances with grantor, grantee, price, mortgage amount and book/page, but the export stops in 2023 (15,119 that year, none after), so it fails the freshness check. Not loaded. |
| Texas business personal property (Dallas, Tarrant, Collin) | **Built** from the same free roll files as the real property sources: `tx.dallas.personal_property_delinquent` (roll P, 51,791 accounts, $201.4M), `tx.tarrant.personal_property_delinquent` (roll 02, 21,209, $45.1M), `tx.collin.personal_property_delinquent` (roll 002, 11,935, $18.4M); each in its county run, owed by the business, no parcel. `tx.dallas.tax_roll_delinquent` now also reads roll C (commercial real property, per the TRW FAQ's roll codes): 28,421 accounts, $293.1M. |
| Denton TX delinquent tax roll | **Built:** `tx.denton.tax_roll_delinquent` (5,726 real accounts, $20.4M, 279 tax-suit judgments; 4,565 parcel-linked to `tx.statewide.parcels` by the account without its 'DEN' suffix) and `tx.denton.personal_property_delinquent` (roll 002, 7,153 accounts, $11.9M), from the Tax Office's free weekly Tax Code 1.10 files (same attorney-file layout as Collin; the delinquent zip is found by its first member name with a ranged read), in a new TX-DENTON run. |
| Scott County IA tax sale lists | The county site answers with a Cloudflare challenge; not worked around. |
| Nueces TX delinquent file (2026-10-26), Montgomery TX (2024), Williamson TX | Next to check: Nueces has a current delinquent file with an Excel layout; Montgomery's posted roll is from 2024. |
| Tarrant TX mineral interests | **Built:** `tx.tarrant.mineral_interests`, an owner source from the same free weekly roll (roll code 03, mineral): 250,236 producing oil and gas interests owned by 95,578 owners, $1.29B appraised (1,490,305 accounts at $0 not read), each a non-spatial parcel '48439-MIN-<account>' with its lease description, owners and appraised value, in the TX-TARRANT run's owners. |
| Nueces TX delinquent file | The county site answers Akamai "Access Denied" (403) to this client, robots.txt included. |
| Williamson TX tax roll | wilcotx.gov answers with a Cloudflare challenge. |
| Brazoria TX delinquent tax roll | The page found by search now answers 404; no other official link found. |
| Texas delinquent mineral interest taxes | **Built:** `tx.tarrant.mineral_tax_delinquent` (roll 03, 243,044 accounts, $17.3M, 466 tax-suit judgments; linked to the interest's `48439-MIN-` parcel in `tx.tarrant.mineral_interests`), `tx.denton.mineral_tax_delinquent` (roll 003, 23,019, $0.78M), `tx.dallas.mineral_tax_delinquent` (roll N, 1,366, $0.2M), in their county runs. Mobile home rolls are left out on the owner's instruction (2026-11-28). |
| Vanderburgh IN 2026 tax sale | **Built:** `in.vanderburgh.tax_sale_2026`, 513 parcels, $4.58M due before the sale (list as of 2026-08-03), parcel-linked to `in.vanderburgh.parcels`, tagged `no_commercial_name_address_lists`; the server answered on the retry. |
| Guilford NC tax lien foreclosures | **Built:** `nc.guilford.tax_foreclosures`, 933 parcels in the county's mortgage-style tax foreclosure (G.S. 105-374) with status and owner, parcel-linked to `nc.statewide.parcels` (PIN + '-000'); new lien option `parcel.suffix`. |
| Harris County delinquent tax sale listing | Not loaded: no owner names; its 241 accounts are tax-suit judgments already in `tx.harris.tax_judgments`, so it would add only the sale date and minimum bid. |
| Nassau NY DQ106 lien summaries | Not loaded: lien number, amounts and status per parcel with no owner, and Nassau parcels link to no owner source, so the liens would attach to nothing. |
| ArcGIS sweep for foreclosure, lien, tax deed and sheriff-sale layers changed since 2026-06 | Besides Guilford: Kodiak Island Borough foreclosures (17, data 2018), Milwaukee 2026 foreclosures (census-tract counts, no parcels), Midland MI and Hopkinsville KY foreclosure layers (empty), Seattle foreclosures by tract: not usable. |
| North Carolina G.S. 105-369 lien advertisements | **Built:** `nc.orange.tax_liens_2025` (Excel, 1,792 parcels, $4.64M), `nc.forsyth.tax_liens_2025` (three PDFs by surname, 7,670 parcels, $9.98M; new lien options: backslash hrefs read as paths, `parcel.rewrite`), `nc.randolph.tax_liens_2025` (13 PDFs, 4,262 parcels, $3.50M); each parcel-linked to `nc.statewide.parcels`, dated January 1 of the tax year, in the NC run. Johnston NC: robots.txt disallows /files/ on both hosts. Davie, McDowell, Lincoln: 2024 lists. |
| Missouri DOR child support lien list (data.mo.gov 7t5a-79ri) | 183 vehicle liens, VIN only, no names. Not usable. |
| Fulton GA "Tax Deed Activity" (sharefulton 7dey-txkb) | The Assessor's deed-processing workflow log, not tax-deed sales. Not usable. |
| NYC DOF Scofftow cases (qmh3-uvgq) | Booted/towed vehicles for parking judgments: plate only, no names. Not usable. |
| New Orleans adjudication hearings, all departments (uzyk-jrck) | Address and fees, no parcel id or owner; code cases already in `la.nola.code_hearing_judgments`. |
| SEC litigation releases, CFPB and FTC enforcement orders | Free-text announcements: defendants and amounts would have to be read out of prose. Not loaded. |
| Cobb County GA Tax Commissioner delinquent tax list | **Built:** `ga.cobb.delinquent_taxes` (monthly PDF, 2026-11-09 list: 16,575 unpaid bills, $58.6M, tax years 2021-2026), parcel-linked to `ga.cobb.parcels`, in the GA run; the link finder now honors a page's `<base href>`. |
| Greene County MO 2026 tax sale list (Collector, 8/21/2026) | **Owner decision:** the PDF says it "is provided for research purposes only" and use "for any purpose not explicitly authorized by the Greene County Collector is prohibited". About 100 parcels. Not loaded. |
| Jefferson County CO lien-sale advertisement, Columbus GA tax sale list, Chatham NC delinquent lists, Saluda/Richland SC | Jefferson's notice answers 404; Columbus's list page is empty (no sale posted); Chatham answers 403; Richland SC links no list, Saluda is small. |
| Faulkner County AR "26augdre.pdf" (Collector uploads) | A monthly "Collection Distribution" report (July 2026 receipts by district), not a delinquent list. Not usable. |
| Johnson County IA 2026 delinquent tax list (Treasurer, Gazette proof) | Newspaper proof for the June 15, 2026 sale, already held: three flowing columns with owner, parcel, item and dotted-leader amount, so rows cannot be cut reliably. Revisit if the Treasurer posts a table. |
| Arkansas Commissioner of State Lands unsold tax-delinquent parcels (auction.cosl.org) | **Built:** `ar.cosl.unsold_tax_parcels`: every parcel certified to the State and left unsold at auction, still redeemable by the owner (2026-11-28: 2,604 parcels in 48 counties, $3.02M in minimum bids = taxes, interest, penalty and costs), parcel-linked to `ar.statewide.parcels`, in the AR run, snapshotted daily. The County Reports "Tax Turnback" files are money returned to counties (and .xls only), not used. |
| Alabama Department of Revenue transcripts of tax-delinquent land held by the State | **Built:** `al.dor.state_held_tax_land`: one weekly PDF per DOR county code (68), 15,992 State-held certificates of sale in 40 counties, $7.84M bid at tax sale, sold to the State 1983-2026; parcel-linked to the 16 county layers (exact ids checked live: 12/12 in most counties, 8/12 Mobile), in the AL run. The in-house PDF reader now decodes ASCII85 streams (Oracle Reports). |
| Jefferson County KY (Louisville) Clerk delinquent property listing | **Built:** `ky.jefferson.delinquent_tax_bills`: the real estate bills eligible for the July 2026 certificate-of-delinquency sale (3,568 bills, tax year 2025, $9.64M), in the KY run. No Jefferson County owner layer is loaded (LOJIC's services answered "maintenance" on 2026-11-28; the PVA's owner data is not offered free), so they meet owners in the Northern Kentucky layers only. The tangible-property .xlsx (367 business accounts, bill number and name in one cell) is not read. |
| Oklahoma County Treasurer active resale list | The 2026 resale is complete ("See You Next Year"); the list is empty until the next resale. Revisit in May. |
