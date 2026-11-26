# Gap states: what was added, what is blocked, and why

Checked 2026-11-18. Coverage by state is generated in `docs/coverage.md`.

## Added

- **Texas, statewide** (`tx.statewide.parcels`): TxGIO StratMap 2026 Land Parcels, one zip per
  county for all 253 counties. It has owner, mailing address and appraisal-district values. It is
  read from TxGIO's public S3 bucket, because the official download host blocks non-browser
  clients. Using that copy was approved on 2026-11-18 (see `config/bulk/tx.stratmap.yaml`).
- **County layers** (`config/counties/`), all free and with no login:

  | State | Counties |
  |---|---|
  | AK | Anchorage, Fairbanks North Star, Kenai Peninsula |
  | AZ | Cochise, Coconino, Pima, Pinal, Yuma |
  | IA | Black Hawk, Linn, Scott |
  | KS | Douglas |
  | KY | Boone |
  | MO | Jackson, St. Louis County |
  | NM | Doña Ana, Sandoval |
  | OK | Canadian, Oklahoma |
  | OR | Deschutes, Marion (Marion has no owner names) |
  | VA | Alexandria, Chesterfield, Loudoun, Prince William, Richmond |
| OK (added) | Tulsa |
| IA (added) | Johnson |
| SD | Lincoln |
| OR (added) | Jackson |
| AZ (added) | Mohave (2023 data) |

  Four Arizona layers (Cochise, Pima, Pinal, Yuma) come from the state water agency's copy,
  which asks users not to pass the data on (`no_redistribution`).

## Left out on purpose

| County | Reason |
|---|---|
| Maricopa, AZ | License requires written authorization, and commercial use needs a sublicense (A.R.S. 39-121.03). |
| Yavapai, AZ | License grants non-commercial access only. |
| Clark, NV | The only free copy is a city mirror of a roll the county sells ($2,500, or $7,500 a year). |
| Washoe, NV | License limits use to internal or project work and has a signature clause. |
| Johnson, KS | Owner data needs a signed Kansas Open Records Act form or a paid subscription. |
| Oregon Metro (Multnomah, Washington, Clackamas) and Lane | Owner names are removed from the free data; the paid RLIS and RLID subscriptions have them. |
| Mat-Su, AK | License is internal use only, with no transfer to third parties. |

**Decided 2026-11-18: this project is a "commercial purpose" under A.R.S. 39-121.03.** The
statute's definition covers any use where the requester "can reasonably anticipate the receipt
of monetary gain" from the records. Finding assets behind purchased judgments does that.
Maricopa and Yavapai stay out unless we file their commercial-use statement and pay.

## Checked after the allowlist change (2026-11-18), still held back

| County | Why |
|---|---|
| Sedgwick, KS | The site's firewall rejects range and statistics queries. Loading it would mean reshaping queries around that block, which needs your decision. |
| Pennington, SD | Individual owners' names are split into separate fields, so we would get surnames only. |
| Chesapeake, VA | The city removes owner names from its own open-data release. |
| Newport News, VA | Owner names are only in the permitting app's backend, not in a published dataset. |
| Fairfax, Arlington, VA | No layer with owner names. |
| Polk, IA | HTML search forms only. Getting the data would mean scraping. |
| Virginia Beach VA, Greene MO, Bernalillo NM | robots.txt unreachable, which counts as disallowed. |
| St. Charles MO, Minnehaha SD | A bot challenge or firewall blocks access. We don't work around those. |
| Shawnee, KS | No data service found. |

## State tax-delinquent lists in states with no debt list (checked 2026-11-26)

Searched ArcGIS Online and the Socrata catalog by state for delinquent-tax, tax-sale, lien,
foreclosure and code-enforcement layers in the 20 states with no debt list (AL, AR, HI, IA,
ID, KY, MA, ME, MT, ND, NH, NM, NV, OK, OR, RI, SD, TN, WA, WY), then each state revenue
department's published delinquent-taxpayer list. Code-violation layers were not counted: a
violation is not a debt. Catalog hits were mostly aggregates (Cambridge MA foreclosure counts,
Pierce County WA quarterly violation counts) or unrelated layers.

| State | List | Result |
|---|---|---|
| SD | DOR Business Tax Delinquent Report (SDCL 10-59-46 to 51): about 200 businesses, a lien filed on each | **Built:** `sd.dor.top_delinquent_business`, in the `SD` run |
| MA | DOR Public Disclosure Tax Delinquents (over $25,000, G.L. c. 62C s. 21) | Held back: only a search form (POST with an anti-forgery token), no published file. Getting it would mean scraping the form. |
| OR | DOR Delinquent Taxpayer List (at least $50,000, ORS 305.806) | Held back: shown only inside the Revenue Online web app, no published file. |
| RI | Division of Taxation Top 100 income and business tax delinquents | Held back: tax.ri.gov answers with a Cloudflare JavaScript challenge. We don't work around those. |
| WY | DOR Excise Tax delinquent taxpayers and vendors (150+ days, monthly) | Held back: the files are on Google Drive, whose robots.txt disallows downloads (`/uc`, and all of drive.usercontent.google.com). |
| WA | DOR delinquent taxpayer list (published from 2001) | Not found any more; tax warrants are filed with each county's Superior Court. |
| AR | Commissioner of State Lands tax-delinquent auction catalog | Not built yet: a catalog and post-auction list on cosl.org; file format not confirmed. |

The other 13 states showed no published state or county debt list on these catalogs.

## Blocked by the session's network allowlist (as first found)

These hosts may serve free owner layers, but this session couldn't reach them. The biggest
missing counties are:

| State | Counties |
|---|---|
| VA | Fairfax, Prince William, Virginia Beach, Chesapeake, Newport News |
| MO | St. Charles, Greene |
| OK | Tulsa |
| KS | Sedgwick, Shawnee |
| IA | Polk, Johnson, Dubuque |
| SD | Minnehaha, Pennington, Lincoln |
| NM | Bernalillo |
| OR | Jackson |
| AK | Juneau |

The host list is in the research notes. Adding hosts is an environment change that you approve.

## Owner names behind a paywall (pricing research, unverified prices marked †)

| Source | What it covers | Cost |
|---|---|---|
| California county assessor secured rolls | Owner name, mailing address, values | LA $50, Sacramento free, Alameda $20†, others mostly under $500 |
| Regrid | Nationwide | About $50–80k a year; state licenses from about $8–12k |
| ReportAll | Nationwide, or by state | API prepay from $1,000; Texas statewide $7,000 |
| Indiana DLGF / Gateway parcel file | Indiana | Likely free; ask data@dlgf.in.gov |
| Tennessee Comptroller TPAD | Tennessee | Token terms unknown; ask |
| Maryland SDAT CAMA files | Maryland | Sold through SpecPrint; quote only |

- **New Jersey:** owners covered by Daniel's Law are masked in every source, vendors included.
- **Washington:** RCW 42.56.070(8) bars agencies from releasing lists of individuals for
  commercial use. Use a vendor license, not county lists.

Every one of these needs your approval: the brief allows no paid source except PACER.
