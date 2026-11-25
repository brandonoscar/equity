# Unclaimed-property owner lists: eastern and central states

What each of 27 jurisdictions publishes about unclaimed-property owners (names with
last-known addresses), how to get it lawfully, and what is already loaded. Checked
2026-11-25. The western and central states are in `unclaimed_property_requests_west.md`.

Loaded by script (configs in `config/person_lists/`):

| source_id | what | rows | addresses |
|---|---|---|---|
| `nj.treasury.unclaimed_owners` | NJ statutory notice, 21 county PDFs | ~2,400 (Salem) to tens of thousands per county | reported in the past year |
| `oh.commerce.unclaimed_funds_owners` | OH statutory notice (R.C. 169.06), county PDFs | 1,500 (Hocking) to ~32,000 (Summit) per county; 30 of 88 counties listed | reported in the past year |
| `nc.raleigh.uncashed_checks` | Raleigh uncashed city checks (ArcGIS table) | 912 | checks 2025-07 to now |
| `wi.madison.outstanding_checks` | Madison outstanding city checks (CSV) | 364 | checks 2024-01 to 2026-04 |
| `ri.providence.unclaimed_property` | (already loaded) | | |
| `ma.framingham.unclaimed_checks` | (already loaded) | | |

Each of these is a public notice made so owners can claim. None is licensed for
owner-recovery ("finder") solicitation. Several states require finders to register or cap
their fees, as noted per state below. Use them internally only, to locate and link people.

## Request-only and hand-download files: how they get loaded

A file that has to be requested, bought or downloaded by hand is read by the `delivered` access
method in `src/equity/adapters/person_lists.py`. That method handles CSV, delimited or
fixed-width text, .xlsx, or a .zip of those. Put the file in
`data/manual/<source_id>/`, or name it with `path=`:

    uv run python -m equity.adapters.record <source_id> path=/path/to/file.zip member=<name> lo=0 hi=20000

No eastern state publishes the layout of its request file, so no `delivered` config has been
written yet. Writing one now would mean guessing the columns. When a file arrives, copy the
template at the end of this page into `config/person_lists/<source_id>.yaml` and set the
columns from the file's header (headers are canonicalized, so 'Owner Name' becomes
`OWNER_NAME`). Then record a fixture from the first rows and check `health()`.

## Per state

### New York: request (free), the best route in the region
- **Office:** Office of the State Comptroller, Office of Unclaimed Funds, 110 State St,
  Albany NY 12236; 1-800-221-9311.
- **Form:** https://www.osc.ny.gov/unclaimed-funds/resources/owner-name-file-request-form
  (name, company, phone, email; nothing else asked).
- **Ask for:** the "list of potential unclaimed funds owners" (the owner name file).
- **Contents:** owner name and last-known address, the nature of the property, and when and by
  whom it was reported. It has no dollar amounts or SSNs. It leaves out accounts with no name or
  address, foreign addresses, accounts under $20, and pre-1985 book records.
- **Fee:** none stated. **Format:** a zipped delimited .txt file. **Delivery:** an emailed link
  to OSC's secure FTP site, which can be downloaded again at any time. **Time:** not stated.
- **Eligibility:** anyone; the form asks no purpose.
- **Use condition:** NY Abandoned Property Law § 1416 caps paid-locator fees and regulates
  locator agreements. Do not solicit owners for a fee.
- **Drop:** `data/manual/ny.osc.owner_names/` (source_id to create: `ny.osc.owner_names`,
  jurisdiction "36", `api: delivered`; set `file.delimiter` from the file).
- The online search is name-at-a-time, so it is search-only and not scripted.

### Maryland: request ($4)
- **Office:** Comptroller of Maryland, Unclaimed Property Division. The FAQ gives 7 St. Paul
  St, Suite 320, Baltimore MD 21202, but newer pages use 110 Carroll St, Annapolis, so confirm
  the address first. Phone 410-767-1700.
- **How:** send a letter of request for the owners' list ("downloaded list"), per the
  Comptroller's Unclaimed Property FAQ
  (https://www.marylandcomptroller.gov/unclaimed-property/faqs.html, which now redirects to
  https://www.claimitmd.gov/app/faq-general).
- **Fee:** $4.00, by money order or business check payable to "Comptroller of Maryland -
  Unclaimed Property".
- **Format, delivery and time:** not published (a download). **Eligibility:** anyone.
- **Ask for:** owner name, last-known address, holder and report year, in a delimited file.
- **Use condition:** Md. Code, Com. Law § 17-327 limits agreements to locate reported property.
  No fee solicitation.
- **Drop:** `data/manual/md.comptroller.owner_list/`.
- The Comptroller also publishes about 100,000 names a year in newspapers. That is not posted
  as a structured page.

### Massachusetts: request (public-records request)
- **Office:** Treasury, Unclaimed Property Division, 1 Ashburton Pl, 12th floor, Boston MA
  02108; 617-367-0400; unclaimedproperty@tre.state.ma.us.
- **Form:** https://www.mass.gov/forms/submit-a-public-records-request-to-the-treasury
  (Records Access Officer). This is a request under M.G.L. c. 66, § 10.
- **Ask for:** the list of owners released every six months (owners over $100, under
  M.G.L. c. 200A, § 9), as an electronic file with owner name, last-known address, holder and
  date.
- **Fee:** public-records law allows fees for search and segregation time. Ask for a waiver
  or an estimate. **Format:** whatever Treasury has. **Time:** 10 business days to respond
  (c. 66).
- **Use condition:** none found on finders. Internal use only.
- **Drop:** `data/manual/ma.treasury.owner_list/`.
- findmassmoney.com is search-only and is not scripted. City lists: Framingham is already
  loaded. Its payroll-checks list (data.framinghamma.gov 9d75-5t5b) has names but no
  addresses, so it was skipped.

### New Jersey: notice list (loaded) plus OPRA for the full file
- **Loaded:** `nj.treasury.unclaimed_owners`, the 2026 newly reported owners by county.
- **Full holdings:** the UPA FAQ says data requests go through OPRA
  (https://www.nj.gov/opra/). Only owner name and reported address are releasable
  (N.J.S.A. 46:30B-76.1). Ask for all owner records with name and reported address as
  CSV. **Fee:** OPRA electronic copies are free or at actual cost. **Time:** 7 business
  days. **Drop:** `data/manual/nj.treasury.owner_list/`. N.J.S.A. 46:30B-106 restricts
  locator agreements.

### Ohio: notice list (loaded, partial) plus a public-records request
- **Loaded:** `oh.commerce.unclaimed_funds_owners`, 30 county PDFs. The index page
  https://com.ohio.gov/divisions-and-programs/unclaimed-funds/claiming-funds/county-unclaimed-fund/county-listings
  returns a CloudFront 404 to this client for every com.ohio.gov path, so the other 58
  counties' file names are unknown. A hand check of that page, or a run from a network it
  answers, fills them in: the config reads the index first. The PDFs themselves, on
  dam.assets.ohio.gov, download fine.
- **Full list:** a public-records request (R.C. 149.43) to the Division of Unclaimed Funds,
  77 S High St, 20th floor, Columbus OH 43215; 1-877-644-6823. The Division says public
  records are available on request. Ask for owner name and last-known address of all
  accounts. R.C. 169.13 regulates finder agreements and caps the fee.

### North Carolina: blocked, hand download possible; Raleigh loaded
- G.S. 116B-62 has the Treasurer send an annual list of owner names and last-known
  addresses, by surname, to the Administrative Office of the Courts. AOC posts it at
  https://www.nccourts.gov/documents/publications/unclaimed-property-by-last-name-all-counties
  (10 alphabetical PDFs, 2024-2025), and older county PDFs are at
  https://www.nccourts.gov/documents/publications/unclaimed-property-by-county.
- nccourts.gov answers 403 "Request blocked" (CloudFront) to this client on every path,
  robots.txt included. Download it by hand and drop the PDFs in
  `data/manual/nc.treasurer.unclaimed_owners/`. Their layout is not visible from here.
  `pdf_table` fetches by URL, so it works only where nccourts.gov answers: then set the
  columns and `cuts` from one PDF. Otherwise convert the PDFs to CSV and load them with a
  `delivered` config.
- Loaded instead: `nc.raleigh.uncashed_checks`. Greensboro publishes a similar layer
  (gis.greensboro-nc.gov OpenData_FIN_DS/MapServer/5), but its payee names and addresses are
  "(hidden value)", so it was skipped. Charlotte's "Aged Checks" layer has no addresses and 0
  rows.
- NCCash.com is search-only. G.S. 116B-78 restricts locator agreements.

### Pennsylvania: notice list exists, but robots.txt bars it
- Treasury prints its annual "Notice of Names of Persons Appearing to be Owners of Abandoned
  and Unclaimed Property" in the Pennsylvania Bulletin, by county and ZIP code with names
  only (no street), e.g.
  https://www.pacodeandbulletin.gov/secure/pabulletin/data/vol54/54-43/1566.html (2024,
  2.5 MB). pacodeandbulletin.gov's robots.txt says `User-agent: * Disallow: /`, so it is not
  fetched by script. A hand download is possible, giving names with ZIP only.
- **Full list:** a Right-to-Know request to Treasury (https://www.patreasury.gov,
  Open Records Officer). Ask for owner name and last-known address. Expect a confidentiality
  objection for owner data beyond what is published. patreasury.gov's search is
  search-only.

### Rhode Island: request (APRA); site blocked
- treasury.ri.gov serves a Cloudflare challenge, which was not worked around. Past
  APRA responses for "list of unclaimed property" are posted on Treasury's CKAN portal
  (https://data.treasury.ri.gov/dataset/?organization=unclaimed-p). They are scanned PDFs
  from 2015, with no text layer.
- File an APRA request (R.I. Gen. Laws 38-2) with Treasury for owner name and last-known
  address. findRImoney.gov is search-only. The statutory newspaper advertisement
  (§ 33-21.1-18) is a quarter-page notice with no names. Providence is already loaded.

### Kentucky: request (open records), limited
- Open records request (KRS 61.872) to the State Treasurer, Unclaimed Property, 1050 US Hwy
  127 South, Frankfort KY 40601. AG decision 17-ORD-089 held that Treasury must give data its
  database can already produce, but may withhold information about individual natural
  persons. Expect businesses only. treasury.ky.gov's search is search-only.

### Florida: search only; request possible
- fltreasurehunt.gov is search-only. Its robots.txt is a 404. Fla. Stat. ch. 119 makes
  agency records public unless exempt. The Division says confidential personal information
  is not released, but owner names and reported addresses appear in the public search.
  Request: Division of Unclaimed Property, Public Records (myfloridacfo.com public records
  page), asking for owner name and reported address of accounts. Claimant's
  representatives must register with the Division and fees are capped (Fla. Stat. 717.135,
  717.1400).

### Virginia, West Virginia, District of Columbia: newspaper notice, search only; FOIA possible
- **VA:** Va. Code § 55.1-2525 requires a newspaper notice titled "Commonwealth of Virginia
  Unclaimed Property List" (annual inserts). vamoneysearch.gov is search-only. A FOIA request
  (Va. Code § 2.2-3704) can go to Treasury. Fairfax County runs an "Unclaimed Property
  (Money)" web app (https://www.fairfaxcounty.gov/unclaimedmoney/), search-only.
- **WV:** W. Va. Code § 36-8-9 (as amended in 2021) requires a county newspaper bulletin of
  up to 15,000 recent properties. It is not posted as a structured page. wvtreasury.gov's
  search is search-only. A FOIA request is possible (W. Va. Code § 29B-1).
- **DC:** D.C. Code requires a newspaper notice. cfo.dc.gov's unclaimed-property page
  answered 403 to this client. A DC FOIA request can go to OCFO. The search is search-only.

### Search-only states (no bulk file, notice list not posted as a structured page)
- **Connecticut:** ctbiglist.gov is search-only. The printed "Big List" ended in 2016. A FOI
  request (C.G.S. § 1-210) to the Treasurer is possible.
- **Delaware:** unclaimedproperty.delaware.gov is a single-page search app. The names list
  was last run in newspapers in 2016. 12 Del. C. § 1189 makes owner records confidential.
- **Maine:** maine.gov answers 403 (CloudFront) to this client; maine.gov/upsearch is
  search-only.
- **New Hampshire:** the RSA 471-C:20 newspaper notice runs in the Union Leader. nh.gov
  answers 403 to this client. The search is search-only.
- **Vermont:** the newspaper list is optional under current law. missingmoney.vermont.gov
  is search-only.
- **Georgia:** the notice is the DOR website itself (O.C.G.A. § 44-12-215).
  gaclaims.unclaimedproperty.com is search-only. An Open Records Act request is possible.
- **South Carolina:** the Treasurer's newsroom posts about 10 names and towns per county,
  with no street address, so it was not loaded. The search is search-only. A FOIA request
  is possible.
- **Alabama, Mississippi, Tennessee:** newspaper notices (MS § 89-12-27; TN § 66-29-130),
  not posted. The searches are search-only. Public-records requests are possible.
- **Michigan:** MCL 567.239 notice twice a year, with the list on the website.
  unclaimedproperty.michigan.gov is search-only.
- **Indiana:** indianaunclaimed.gov answers 403 (Cloudflare) to this client. Annual newspaper notice. The
  search is search-only. An APRA request to the AG is possible.
- **Illinois:** icash is search-only. The Treasurer says it is legally barred from giving
  more than the website shows (765 ILCS 1026/15-1402), so a FOIA request is unlikely to
  give a bulk list. The newspaper notices (twice a year) carry no names. Columbus, OH's
  checks data has payee names but no addresses, so it was skipped.
- **Wisconsin:** DOR's annual newspaper campaign (Wis. Stat. 177.0503) is not posted.
  revenue.wi.gov/ucp is search-only. Madison is loaded (`wi.madison.outstanding_checks`).
  County treasurers publish their own class-1 notices of unclaimed funds.

MissingMoney.com and every state search above take one name at a time. They are not
scripted.

## Template: a delivered config for a requested file

```yaml
# <office>, <list name>: delivered on request (<form url>) as <format>.
source_id: ny.osc.owner_names
state: NY
jurisdiction: "36"
kind: tax
record_type: unclaimed_property
api: delivered
file:
  request_url: https://www.osc.ny.gov/unclaimed-funds/resources/owner-name-file-request-form
  delimiter: "|"          # from the file
  chunk_bytes: 8000000
key: [PROPERTY_ID]        # from the header, if a property id is present
key_prefix: "NY-UF:"
parties:
  - role: owner
    name: OWNER_NAME      # from the header
    format: last_first
    address: {street: [ADDRESS_1, ADDRESS_2], city: CITY, state: STATE, zip: ZIP}
terms:
  url: <form url>
  summary: >-
    Delivered on request under <law>; <use condition>. Internal locate/link use only.
  checked_on: <date>
  cost_model: free
```
