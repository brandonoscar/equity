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
  | VA | Alexandria, Chesterfield, Loudoun, Richmond |

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

`TODO(Brandon)`: decide whether this project is a "commercial purpose" under Arizona's
A.R.S. 39-121.03. If it is not, Maricopa and Yavapai can be revisited.

## Blocked by the session's network allowlist (not yet checked)

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
