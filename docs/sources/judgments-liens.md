# Judgments, liens, recorded documents and business registries

Free sources with no login, added on 2026-11-16. Every mapping that is a legal or
classification call lives in config with a `TODO(Brandon)` and is not settled until you
confirm it.

## Recorded documents and liens

| Source id | What it holds | Parcel link | Gaps |
|---|---|---|---|
| `ny.nyc.acris.real` | NYC City Register: deeds, mortgages, assignments, satisfactions, recorded judgments (JUDG), tax-lien sale certificates (TLS), condo common-charge liens. Manhattan, Bronx, Brooklyn, Queens. 17M documents. | BBL to the NYS parcel id (`<county>-<SWIS><BBL>`) | Money judgments are docketed with the County Clerk, not ACRIS. Staten Island isn't covered. References that cite only a CRFN or reel/page are kept as `unresolved_reference` issues until a linking step. |
| `ny.nyc.acris.personal` | UCC filings and federal liens: IRS liens (FL), other federal liens (FTL), estate-tax liens, and their releases, withdrawals and continuations. 4.6M documents. | Lots when the filing lists them; federal tax liens attach to the debtor, not a lot | Same as above |
| `pa.philadelphia.rtt` | Philadelphia Recorder: deeds, sheriff deeds, mortgages, assignments, satisfactions, lis pendens, UCC. 5.35M rows. | OPA account (same key as `pa.philadelphia.parcels`) | No mortgage amounts. Judgments and municipal liens are filed with the Prothonotary, not here. Rows without an OPA account keep the street address for a later address match. |
| `fl.hillsborough.or` | Hillsborough Official Records daily index: recorded judgments (JUD, CCJ), liens (LN, corporate tax liens), lis pendens, satisfactions, deeds and mortgages. About 1,800 documents a day, 500+ of them judgments. | None in the index. A later step must link through the legal description or the debtor's ownership. | Only about 2 months are online, so a daily pull is needed to build history. No judgment or mortgage amounts. Family and vital records are excluded on purpose. |

## Court cases and enforcement (Hillsborough)

| Source id | What it holds |
|---|---|
| `fl.hillsborough.civil.cases` | Monthly: circuit and county civil cases filed that month, with type (including claim-amount tier), status and judgment code as of the report. Kept one year. |
| `fl.hillsborough.civil.filings` | Daily: every party of each new case, with address and attorney. Kept about a month. |
| `fl.hillsborough.garnishment` | Weekly: writs of garnishment. Gives the judgment creditor, the judgment debtor with address, the garnishee (bank or employer), and the dates writs were filed and issued. This is direct evidence that a judgment exists and is being collected. |

All Hillsborough court rows use `case_uid = fl.hillsborough:<case number>`, the same case
number the Official Records index carries in its legal column.

## Court judgments (Harris County, TX)

| Source id | What it holds |
|---|---|
| `tx.harris.jp.civil_judgments` | Justice Courts "Judgments Entered" public extract, all 16 JP courts: debt claims, small claims, evictions and other civil judgments with judgment date, amount, attorney fees, court costs, post-judgment rate, who it was for and against, and the first two plaintiffs and defendants with addresses. Back to at least 2005; loaded in monthly parts from 2016-12, newest first. |
| `tx.harris.district.civil_judgments` | District Clerk CaseSummaryMods datasets: district-court civil debt cases (debt/contract, sworn account, note, foreign judgment) with filing date, court, first plaintiff and defendant names, and judgments for the plaintiff (default, agreed, summary, for plaintiff) with date and text. No amounts, no addresses. Cases filed from 2015, plus every case changed since 2025. |

JP judgments name the creditor and debtor (who won is read from the judgment's "in favor
of" and "against" names) and the debtor's address, so the matcher can link them to Harris
parcel owners by name and address. District Clerk files come through the page's own
Download button (a form post); no account is needed.

## Federal courts

Bankruptcy-court RSS feeds are enabled for FL (M, S, N), NY-S, PA-E, OH-N, NJ, GA-N and
TX-N, plus WV-N district and bankruptcy (`config/courts.yaml`). The feeds cover only the
last 24 hours or so, so history builds only if they are polled regularly.

## Business registries

| Source id | Entities | Roles |
|---|---|---|
| `ny.sos.business` | 4.2M active NY entities | Registered agent, chairman/CEO, service-of-process name and address |
| `co.sos.business` | 3.1M CO entities, all statuses | Registered agent |
| `ct.sos.business` | 1.3M CT entities | Principals (officers, directors), agents |
| `or.sos.business` | Active OR entities | Registered agent, authorized representatives |

These feed Phase 3: linking an LLC that owns a parcel to the people behind it.

## Loading these

```bash
uv run python -m equity.lake plan ny.nyc.acris.real --set 'codes=JUDG|TLS|ATL|AMTL|DTL|LOCC|TOLCC|RTXL|CTOR|DCTO'
```

```bash
uv run python -m equity.lake run --only ny.nyc.acris.real ny.nyc.acris.personal fl.hillsborough.or
```

The first command loads only NYC's lien and judgment documents. The full ACRIS set (about
200M rows) does not fit in a session container next to the parcels. The lake runner starts
at most one build per host, across all of its sources.

## Not usable without a decision

- **Florida Sunbiz business data:** served by SFTP with a published username and password, which counts as a login under the brief.
- **Other Florida clerks:**
  - Miami-Dade, Palm Beach, Pinellas and Lee charge fees.
  - Broward offers 7–10 days of daily extracts; not built yet.
- **Philadelphia parcel-level tax delinquency:** retired; only aggregates are published now.
- **NY OCA housing-court judgments:** no names or addresses, so they can't be matched.
