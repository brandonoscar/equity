# Unclaimed-property owner lists: western states (request kit)

Checked 2026-11-25. Covers AK, AZ, AR, CA, CO, HI, ID, IA, KS, LA, MN, MT, NE, NV, NM, ND, OR, SD,
TX, UT, WA, WY. Oklahoma and Missouri are already loaded (see config/person_lists/).

What we want from each office: every apparent owner's **name and last-known address** (street,
city, state, ZIP), with property id, holder, property type, report year and amount where the
office includes them. Electronic (CSV, Excel, delimited text), the whole list as of the request
date.

A delivered file goes, exactly as delivered (zip and all), into `data/manual/<source_id>/`
(git-ignored; never committed). Sources with an adapter read it from there, or from `path=`:

    uv run python -m equity.adapters.record <source_id> path=<file> lo=0 hi=200000 limit=25

Use conditions below are a summary, not legal advice. Every office that releases a list does so
for owners to be found and paid; most states regulate paid "finders". Our use is internal
locate/link only: no fee-based owner-recovery solicitation, no resale.

Nothing here was submitted, paid for or signed. Each request needs Brandon's name, business and
contact details, which this repo does not hold.

## Available now (adapters live)

| State | source_id | Route | Rows | Notes |
|---|---|---|---|---|
| CA | `ca.orange_county.unclaimed_property` | ArcGIS layer by OC Public Works | ~7.0M | The Controller's records whose owner address is in Orange County, rebuilt from the Controller's file (v2026.2, 2026-04-21). CC BY-SA 3.0. |
| TX | `tx.college_station.unclaimed_property` | City open data (Socrata) | ~12k | City-held property 1994-present; street line only (no city/ZIP). |

## Request or hand-download routes

### California: State Controller (hand download; adapter `ca.sco.unclaimed_property`)

- Office: State Controller's Office, Unclaimed Property Division.
- Where: <https://sco.ca.gov/upd_download_property_records.html> ("Download Unclaimed Property
  Records").
- What: the whole public database as zipped CSVs (split by value range), refreshed every
  Thursday. Free; no request, no form.
- Blocker: every request to sco.ca.gov, robots.txt aside, gets a Cloudflare browser challenge
  (403 "Just a moment..."). **Blocked for scripts; hand download possible** in a browser. We do
  not work around it.
- Format: CSV with header PROPERTY_ID, PROPERTY_TYPE, CASH_REPORTED, SHARES_REPORTED,
  NAME_OF_SECURITIES_REPORTED, NO_OF_OWNERS, OWNER_NAME, OWNER_STREET_1..3, OWNER_CITY,
  OWNER_STATE, OWNER_ZIP, OWNER_COUNTRY_CODE, CURRENT_CASH_BALANCE, NUMBER_OF_PENDING_CLAIMS,
  NUMBER_OF_PAID_CLAIMS, HOLDER_NAME, HOLDER_STREET_1..3, HOLDER_CITY, HOLDER_STATE,
  HOLDER_ZIP, CUSIP. (From the Controller's file as mirrored by Orange County and Irvine;
  confirm on the first download: `health()` prints the header it finds.)
- Size: several GB zipped in total. Download one value band at a time if disk is tight; the
  adapter reads zip members in byte windows and never unpacks them.
- Drop: `data/manual/ca.sco.unclaimed_property/` (the zips as downloaded).
- Use: robots.txt says `Content-Signal: search=yes, ai-train=no`: no model training. CCP 1582
  caps locator fees at 10% and voids agreements made within 24 months after the property
  reaches the Controller.

### Texas: Comptroller (free on request; adapter `tx.comptroller.unclaimed_property`)

- Office: Texas Comptroller of Public Accounts, Unclaimed Property Division.
- How: email **up.dbrequests@cpa.texas.gov** (instructions: data.texas.gov dataset
  [3un9-h9it](https://data.texas.gov/d/3un9-h9it)). Give: full contact name, phone, business
  name, full mailing address, TX private-investigator license number (if any; we have none).
- Ask for: "the Texas Unclaimed Property Listing (all report years), with the Layout file".
- Fee: none published. Delivery: through the Comptroller's SIFT secure file transfer
  (<https://data-secure.comptroller.texas.gov>, an account they set up). Refreshed in the first
  7 working days of each month.
- Format: a zip of text files, one per holder report year, plus a Layout file. The adapter
  assumes a delimited file with a header row named as in the Comptroller's field list (Former
  Owner Last Name, Former Owner First Name, Former Owner Address Line 1-3, City, State, ZipCode,
  County, Holder ..., Property Type, Dollar Amount Remitted, Report Year...). If the delivery is
  headerless or fixed-width, copy the Layout into `file.columns` or `file.fixed` in
  config/person_lists/tx.comptroller.unclaimed_property.yaml.
- Drop: `data/manual/tx.comptroller.unclaimed_property/` (Layout and ReadMe files are skipped).
- Use: contacting owners to locate/recover property for a fee may need a PI company license
  (Tex. Occ. Code ch. 1702); Prop. Code ch. 74 limits locator agreements.

### Alaska: Department of Revenue, Treasury Division (free on request; no adapter yet)

- How: email **ucproperty@alaska.gov** (<https://unclaimedproperty.alaska.gov/app/fee-finders>).
  Include name, business name, address, phone, and an acknowledgment of the Alaska Unclaimed
  Property Act's fee-finder contract conditions and allowable fees (AS 34.45).
- What: the periodically compiled list of properties worth $100 or more. Free. Format and
  delivery time not published.
- Note: rows with the same PSN are one property with several owners (the amount repeats).
- Use: no finder license in Alaska; fee-finder contracts are limited by AS 34.45.
- Adapter: add an `api: delivered` config once the layout is seen; drop into
  `data/manual/ak.revenue.unclaimed_property/`.

### North Dakota: Department of Trust Lands, Unclaimed Property Division (request; fee possible)

- How: email **unclaimed@nd.gov** (<https://unclaimedproperty.nd.gov>, fee-finder FAQ).
- What: list of apparent owners of all property held as of the request date: owner name,
  last-known address, holder name, date of last activity, property type. Excel.
- Fee: "charges may be incurred" under N.D.C.C. 44-04-18 (open-records copy and staff-time
  fees). Delivery time not published.
- Use: heir finders not exempt under N.D.C.C. 43-30-02 must hold a ND private-investigator
  license (NDPISB). Since 2025 the Division auto-pays single-owner property up to $1,000.
- Drop: `data/manual/nd.trust_lands.unclaimed_property/`.

### Wyoming: State Treasurer, Unclaimed Property Division (purchase, $1,000)

- Where: <https://statetreasurer.wyo.gov/asset-finders/>.
- What (Wyo. Stat. 34-24-119): (1) a list of all properties valued $50+, for inspection at the
  Cheyenne office during business hours (free, in person); (2) properties more than 24 months
  old as an Excel-searchable database on an **encrypted DVD, $1,000**.
- How: letter asking to buy the asset finder list, saying where to send the DVD, with a
  certified check payable to "Wyoming Treasurer's Office", to Wyoming State Treasurer,
  Unclaimed Property Division, 122 W. 25th St., Ste E300, Cheyenne, WY 82002. 3-4 weeks.
- Contents: owner name(s), last-known address, holder, property type, report year, amount.
- Use: no finder registration; agreements made within 24 months after the property reaches
  the State are unenforceable, and later ones must be in writing (Wyo. Stat. 34-24-136).
- Drop: `data/manual/wy.treasurer.unclaimed_property/`.

### Colorado: State Treasury, Great Colorado Payback (purchase, $305; no street address)

- Where: <https://unclaimedproperty.colorado.gov> (Finder/Locator List page) and the Finder
  Disk Form (PDF) linked there.
- What: one CD, an Excel file, updated each January: properties older than 24 months
  (C.R.S. 38-13-1302), alphabetical by owner; **owner name, last-known city/state only** (no
  street, no ZIP), holder, property type, year reported, amount shown only as "Over $250";
  amounts under $500 removed. Includes the Estates of Deceased Owners list.
- Fee: $305 incl. shipping; cashier's check or money order to "Colorado State Treasury" with
  the completed Finder Disk Form, by mail.
- Use: no finder license; RUUPA caps finder fees and requires claims to come from the owner.
- Value for us: low (no street address). CORA requests:
  <https://treasury.colorado.gov/news-and-information/requests-for-public-records>.

### Oregon: State Treasury, Unclaimed Property Program (purchase; finders must be licensed)

- Where: <https://unclaimed.oregon.gov/app/licensed-finders>; rule OAR 170-140-0020 (Finder's
  List of Unclaimed and Escheat Property).
- What: owner and co-owner names, last-known address, amount (actual or estimated), property
  type, OST reference number; separate escheat/estates listing.
- How: Finder's List Order Form, paid through the Treasury Electronic Payment Gateway
  (<https://www.oregon.gov/treasury/electronic-payment-gateway/Pages/default.aspx>) or emailed
  to claims@ost.state.or.us. Current price not published (DSL charged about $100 per release).
- Eligibility: the Treasury tells buyers to check DPSST private-investigator licensing first
  (ORS 703.401-703.470); finder claims require a current license. Ask whether the list is sold
  to unlicensed requesters for internal use.
- Drop: `data/manual/or.treasury.unclaimed_property/`.

### Arkansas: Auditor of State (purchase, $250; PDF)

- Where: <https://www.ark.org/rosterdl/index.php?agency=auditor_unclprop> ("Finder File").
- What: properties more than 24 months old worth more than $25: owner name, address, city,
  state, ZIP, holder, property type, report received date, remaining cash/securities/tangible
  proceeds, property ID. Updated yearly (last 2026-04-30).
- Fee: $250 by card online; a download link valid 48 hours.
- Format: a zipped **PDF**. An adapter would need the PDF's table layout
  (src/equity/adapters/pdf_table.py can read machine-generated PDFs); not built until seen.
- Use: A.C.A. 18-28-201 et seq. limits finder agreements.

### Washington: Department of Revenue (public-records request; commercial use barred)

- How: DOR Public Records, Information Governance Office, PO Box 47456, Olympia, WA
  98504-7456, on DOR's public-records form (<https://dor.wa.gov/contact/public-records>),
  stating the purpose.
- Limit: RCW 42.56.070(8) bars agencies from giving lists of individuals for commercial
  purposes, and DOR says owner-identifying information is protected; DOR may charge for
  customized lists. Expect a denial for a business purpose. Search: claimyourcash.org (search
  only).

### Kansas: State Treasurer (KORA request; anti-solicitation certification)

- How: written Kansas Open Records Act request to the Records Custodian, Kansas State
  Treasurer, 900 SW Jackson, Suite 201, Topeka, KS 66612 (KORA policy:
  <https://kansascash.ks.gov/assets/Files/kora_policy_20230518.pdf>). Ask for the owner name
  and last-known address file.
- Condition: the requester certifies under K.S.A. 45-230 not to use names or addresses from the
  records to sell or offer to sell property or services. Staff-time fees may apply. Whether
  the Treasurer releases owner names and addresses is not stated. Search:
  kansascash.ks.gov (search only).

### Minnesota: Department of Commerce (blocked; counties only by statute)

- mn.gov/commerce answers scripts with a ShieldSquare bot challenge: **blocked; hand browsing
  possible** at <https://mn.gov/commerce/money/unclaimed-property/>.
- Minn. Stat. 345.42 gives counties (not the public) an electronic owner list every six months
  on written request. A Data Practices Act request is possible, but owner data is likely
  private data on individuals. Search: MissingMoney.com (search only).

## Search-only states (no list released or posted)

| State | Office / search | Published notice | List on request? |
|---|---|---|---|
| AZ | Dept. of Revenue, azdor.gov/unclaimed-property (search) | none online | No: ADOR releases nothing about a property before a signed claim with proof of ownership. |
| HI | Budget & Finance, unclaimedproperty.ehawaii.gov (search) | Annual notice PDF (budget.hawaii.gov/finance/unclaimedproperty/annual-notice) says names are kept at the office and on the search site (HRS 523A) | Inspect at the Honolulu office; ask under UIPA (HRS 92F). |
| ID | State Treasurer, yourmoney.idaho.gov (search) | Website list required by Idaho Code 14-5-503 is the search itself | STO "does not sell, rent or lease" lists; Idaho Code 74-120 bars releasing lists of people for solicitation. |
| IA | State Treasurer, greatiowatreasurehunt.gov (search) | New owners in county newspapers each year (not posted) | Treasurer rules make owner name/address in reports confidential; ask under Iowa Code ch. 22, expect refusal. |
| LA | Treasury, treasury.la.gov/unclaimed-property (search; LaCashClaim) | New owners each year in parish official journals (not posted) | La. R.S. 44:4(59)-(60) (2021) exempts claimant PII; request form treasury.la.gov/records-request, expect refusal. |
| MT | Dept. of Revenue, revenue.mt.gov/unclaimed-property (search) | none found | Not published; ask UnclaimedProperty@mt.gov (406-444-6900). Since HB 88 (2025) the Department auto-pays from tax records. |
| NE | State Treasurer, nebraskalostcash.nebraska.gov (search) | Annual tabloid by county of last residence in ~16 newspapers (Neb. Rev. Stat. 69-1311), not posted | Ask under Neb. Rev. Stat. 84-712; not offered. |
| NV | State Treasurer, claimitnevada.gov (search; did not resolve here) | County lists in local newspapers (NRS 120A.580), not posted | NRS 120A.145 keeps reported information confidential; locator agreements limited (NRS 120A.740). |
| NM | Taxation & Revenue, nmclaims.unclaimedproperty.com (search) | Annual list in newspapers (NMSA 7-8A-9), press release only on tax.newmexico.gov | IPRA request to unclaimed.property@tax.nm.gov; locator agreements void for 48 months (NMSA 7-8A-25). |
| SD | State Treasurer, sdtreasurer.gov/unclaimed-property (search) | Newspaper notice (SDCL 43-41B-19), not posted | Not offered. |
| UT | State Treasurer, mycash.utah.gov (search) | none | No: records are "private" under GRAMA; the Division does "not give or sell a list ... for commercial purposes". |

MissingMoney.com and every state search site above answer one name at a time: search only,
not scripted.

## City and county lists checked

- Used: College Station, TX (Socrata, with street line); Orange County, CA (ArcGIS, the
  Controller's records for OC owners).
- Skipped, no address published: Austin, TX (datahub.austintexas.gov h3i4-5e5v, names only);
  Sacramento County, CA (County Unclaimed Funds, County Outstanding Checks); City of
  Sacramento (Outstanding Checks); Roseville, Sonoma County and Marin County, CA (stale-dated
  checks, payee names only).
- Skipped, older subsets of the Orange County layer: City of Irvine "UnclaimedStateFunds"
  (274k rows, 2023, no city column) and City of Lake Forest (2017/2020).
- Utah's AGRC "Unclaimed Property Data Mapping" (treasurer.utah.gov/updata) is aggregated by
  census tract and district: no names.
