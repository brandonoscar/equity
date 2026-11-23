# Broward OR daily index, Franklin County OH eviction CSVs, Debt Collection Lab: loadable?

Date: 2026-11-23. Network: unrestricted for HTTPS through the session proxy (no raw TCP).

Question: can any of these three be loaded under the project rules (free, no login, no CAPTCHA, no paywall, robots.txt honored, no search-portal scraping; a published bulk file is fine) as instruments or court cases with debtor names, addresses and judgment amounts?

Answer: **No, not today. Nothing was built or loaded.** Each source fails a different rule:

| Source | Free | No login | robots.txt | Names | Amounts | Result |
|---|---|---|---|---|---|---|
| Broward County FL OR daily index | yes [SEARCH] | **no**: SFTP with a published shared username and password | n/a (SFTP) | yes, per name file [SEARCH] | consideration only, probably [UNVERIFIED] | not loaded |
| Franklin County OH Municipal Court F.E.D. CSVs | yes [LIVE] | yes [LIVE] | **disallowed**: `Disallow: /storage/shared/*` covers the files | first plaintiff, first defendant + mailing address [LIVE, page text] | not listed ("last disposition information") [LIVE, page text] | not loaded |
| Debt Collection Lab (Princeton / January Advisors) | yes [LIVE] | yes [LIVE] | allows all [LIVE] | **no defendant names**: per-collector aggregates | aggregate dollars per collector | not loaded |

Tags: [LIVE] I read it myself in this session. [SEARCH] web-search snippets only. [UNVERIFIED] inference or uncited.

## 1. Broward County FL: Records, Taxes & Treasury daily index files

- Pages: [Bulk Data Files](https://www.broward.org/RecordsTaxesTreasury/Records/Pages/IndexFiles-Completed.aspx), [Daily Index Extract examples](https://www.broward.org/RecordsTaxesTreasury/Records/Pages/DailyIndexExtractFiles.aspx), [Document type descriptions (PDF)](https://www.broward.org/RecordsTaxesTreasury/Records/Documents/DocumentTypeDescriptions.pdf).
- Access to the pages: every `www.broward.org/RecordsTaxesTreasury/...` URL redirects to `/RecordsTaxesTreasury` and returns a Cloudflare "Sorry, you have been blocked" page (HTTP 403). This happened with the project User-Agent, a browser User-Agent and curl's default. WebFetch could not resolve the host. `www.broward.org/robots.txt` [LIVE] is Cloudflare-managed: `User-agent: * Allow: /` with `Content-Signal: search=yes,ai-train=no,use=reference`. It bars named AI crawlers (ClaudeBot, GPTBot...), which our identified records-research agent is not. The terms of use could not be read. [LIVE for the block and robots; page text SEARCH]
- What the pages say, per search snippets [SEARCH]:
  - Host `BCFTP.Broward.org`, **port 22 (SFTP)**, a shared public username and password printed on the page. The page notes that browsers no longer support FTP, so you need an FTP client.
  - "10 continuous days" of quality-assured images and index. A second page says each file stays 7 days.
  - Files are named `MM-DD-YYcfn.txt` / `MM-DD-YYcfn-rec.txt` (one record per Clerk's File Number) plus name files (one record per indexed name). They are pipe-delimited: blanks are `||`, trailing spaces trimmed, leading zeros trimmed. A no-activity day gives a zero-byte file. Missing files go to Records@broward.org.
  - The column-by-column layout was not in any snippet. The example page was cut off.
- Why not loaded:
  1. **Login.** Access is an authenticated SFTP session. The credential is published and shared, but it is still a username and password. The project rule (docs/phase0.md: "nothing that ... sits behind a login ... has been used") has not been read to allow published shared credentials, and the same open point is unresolved for `sftp.floridados.gov` (recorded_judgment_indexes.md).
  2. **Reachability.** The session egress is an HTTPS CONNECT proxy, and `bcftp.broward.org` does not resolve locally. A single SFTP-through-proxy probe was refused by this session's permission policy, so the host and layout were never seen.
  3. **Terms unread** (Cloudflare 403).
- If cleared: model it on `src/equity/adapters/fl/hillsborough_or.py`. The pair is one CFN file plus one name file per day. Use `single_store = True` because corrections arrive in later days. Partition by `day=MMDDYY` so a daily job builds history past the 7–10 day window. Map doc codes in `config/recorders/fl.broward.or.yaml` from the DocumentTypeDescriptions PDF. `PoliteClient` is HTTP-only, so an SFTP transport (paramiko or `curl sftp://`) would need to be added and reviewed.

## 2. Franklin County (Columbus) OH Municipal Court: monthly Civil F.E.D. (eviction) case lists

- Page: [fcmcclerk.com/reports/evictions](https://www.fcmcclerk.com/reports/evictions) (301 to `www.`), read in full [LIVE]. It says:
  - Reports are published "due to the volume of public record requests regarding Civil F.E.D. ... cases".
  - "On a nightly basis, reports will be created for F.E.D cases filed the current month and each of the previous 12 months", as CSV.
  - Contents: "case number, file date, last disposition information, first plaintiff and most recent address, and first defendant and most recent address. Party information is limited to the first plaintiff and first defendant." The addresses are "mailing address of the parties which may or may not be related to the property".
- Files [LIVE, links only]: 13 files, `https://www.fcmcclerk.com/storage/shared/civil-fed/FCMC Civil F.E.D. (Eviction) Case List YYYY-MM-01 to YYYY-MM-DD.csv?<n>`, covering 2025-11 through 2026-11.
- Terms [LIVE]: the [Mission & Privacy Statements](https://www.fcmcclerk.com/mission-and-privacy-statements) page only bars modifying or defacing the site. There are no use or redistribution terms. No login, no fee.
- **robots.txt [LIVE]** (`https://www.fcmcclerk.com/robots.txt`):
  ```
  User-agent: *
  Disallow: /case/search/results
  Disallow: /case/view
  Disallow: /case/pay/online
  Disallow: /storage/shared/*
  ...
  Disallow: /api*
  ```
  Every CSV lives under `/storage/shared/civil-fed/`, so the operator has excluded automated agents from exactly these files. Python's `robotparser`, which `PoliteClient` uses, returns `can_fetch(...) == False` for them, so an adapter would raise `AccessDenied`. No written script permission (as `SCRIPT_PERMISSIONS` holds for WPRDC) exists. I did **not** download a CSV, so the real header is unseen, and whether there is any money-judgment amount or date column is unknown. The page lists only "last disposition information", which suggests a disposition code and date, not an amount [UNVERIFIED].
- Fit even if allowed: evictions are mostly possession judgments. A money judgment (rent and damages) may appear only as a disposition description. Plaintiffs are landlords (creditor) and defendants are tenants (debtor), whose mailing address is usually the rental unit, so the source would rarely point at owned real property. It is a weak source for "does the debtor own property with equity".
- If permission is granted: build `oh.franklin.municipal.fed` on the `hillsborough_civil._CivilFiles` pattern. Partition by monthly file. Use `single_store = True`, since the current month and last-disposition data are rewritten nightly. Emit `court_case`, `case_party` (plaintiff→`creditor`, defendant→`debtor`), `party` and `address` (via `normalized_address`), and emit `judgment` only where the disposition carries a money judgment and date.

## 3. Debt Collection Lab (Princeton Dignity & Debt / January Advisors)

- The `student-debt-research--debt-collection-lab.netlify.app` branch deploy is gone (Netlify "Not Found", HTTP 404) [LIVE]. The production site is [debtcollectionlab.org](https://debtcollectionlab.org/get-the-data/) (same as `debt-collection-lab.netlify.app`). Its robots.txt allows all except `/admin/` [LIVE].
- "Get the data" [LIVE]: "**Aggregate data** for the available counties and states are listed below." Downloads are offered for CA (Jan '09–Nov '23), CT (Jan '21–Jan '25), IN (Jan '21–Dec '24), MN (Jan '21–Jan '26), MO (Jan '21–Jan '25), ND (Jan '21–May '26) and VA (Jan '21–Oct '24), as `/data/<state>_<range>.csv`. AZ, CO, OH and TX are listed without downloads. **Wisconsin is not listed.** The page gives no licence, only a requested citation (Wherry et al., *Debt Collection Tracker*, Princeton 2024).
- File layout [LIVE, every file's header read; ND fully downloaded, 2,981 rows × 36 columns]: `collector, count, percent_total, dollar_amount, dollar_percent_total, percent_with_representation, percent_default_judgement, percent_case_completed`, then the same seven per year (`count21`...). One row per plaintiff/collector. There are **no cases, no defendants, no addresses**.
- Methodology report (`/docs/methodology-report-final-october.docx`) [LIVE]: the lab collects plaintiff and defendant names and cleans defendant addresses internally, but publishes only aggregates.
- Older site repo [github.com/hoshmn/debt-collection-lab](https://github.com/hoshmn/debt-collection-lab) (2021, no LICENSE file) [LIVE, cloned]: `data/lawsuit_data.csv`, 346,915 rows of `id` (census tract GEOID), tract name, `plaintiff`, `date`, `default_judgment`, `has_representation` and `amount`. These are case-level but **de-identified to census tract**: no defendant name or address. They cover Harris County TX and similar 2020 data, not the six states.
- Why not loaded: the load bar was names + amounts + a permissive or public-government-source basis. There are no defendant names anywhere, and no licence. Collector-level dollar totals cannot attach to a debtor or parcel.

## TODO(Brandon)

- **Broward:** decide whether a published, shared SFTP credential (printed on the Broward page; Sunbiz uses the same pattern) counts as "no login". If yes, allow egress to `bcftp.broward.org:22` (the session proxy is HTTPS-only) and approve an SFTP transport. Have someone on an unblocked network read the IndexFiles-Completed and DailyIndexExtractFiles pages for terms, price and the CFN and name-file layouts. Earlier notes found a $30 index-CD fee, and whether the daily files are free is still [SEARCH] only.
- **Franklin County OH:** ask the Clerk's Office of Information Services (614-645-8186) for written permission to fetch `/storage/shared/civil-fed/*.csv` by script, or for a robots.txt carve-out. Until then the adapter cannot run. Also confirm whether the CSV has a judgment amount column. A one-off manual download by a person is allowed by robots.txt but would not give a nightly feed.
- **Debt Collection Lab:** case-level data with names exists only on request (debtcollectionlab@gmail.com) and would come with whatever terms they set. The underlying sources are state court portals (MN MCRO, IN mycase, CT, VA, ND), which are search portals we may not scrape ourselves.
