# NY Unified Court System: free bulk landlord-tenant / civil case data with names and judgment amounts?

Question: does the NYS Unified Court System (OCA, Division of Technology & Court Research) publish a free, no-login bulk file of landlord-tenant or other civil cases that carries **party names** (or addresses) **and judgment amounts**, which we could load as `court_case` / `case_party` / `party` / `judgment`?

Answer: **No.** The only bulk civil product OCA publishes is the landlord-tenant XML extract, and it is built "without personally identifying information": no party names, no property street address, a hashed index number, and judgment text scrubbed of names. Nothing was built; no adapter qualifies.

Tags: [LIVE] I read it myself in this session. [SEARCH] web-search snippets only. [UNVERIFIED] inference or uncited.

Network limits: every `nycourts.gov` / `ww2.nycourts.gov` page returned a Cloudflare "Just a moment..." challenge (HTTP 403) to curl, and WebFetch could not resolve the host. `web.archive.org` connections were reset by the proxy. `nysenate.gov` returned 403. So the court pages themselves are [SEARCH]; the OCA extract specification is [LIVE] via the copy OCA gave the Housing Data Coalition (`docs/oca-extract-info.pdf` in github.com/housing-data-coalition/oca).

## 1. OCA "Landlord-Tenant Data" (the public XML)

- Page: [ww2.nycourts.gov/landlord-tenant-data-34621](https://ww2.nycourts.gov/landlord-tenant-data-34621), also linked as [nycourts.gov/division-technology-court-research/landlord-tenant-data](https://www.nycourts.gov/division-technology-court-research/landlord-tenant-data), under [Housing Data and Reports](https://www.nycourts.gov/division-technology-court-research/housing-data-and-reports). [SEARCH]
- What it says: "case-level, **de-identified** landlord-tenant data" in XML files for all local civil courts **except Town & Village courts** (so NYC Civil Court Housing Part plus City Courts and Nassau/Suffolk District Courts). A rolling five years, updated monthly, one file per filing year. The page links an extract-information document, an XSD (`Landlord-Tenant Extract.xsd`) and a "template file **without personal identifying info**". [SEARCH]
- A separate "Housing tab" page ([ww2.nycourts.gov/housing-tab-35946](https://ww2.nycourts.gov/housing-tab-35946)) describes a Housing Court XML extract with "100+ fields" and, per search summary, "property address & party names excluded". [SEARCH; one search summary, could not open the page]
- Free and no login: yes per search snippets (direct links on the page). Terms of use for the files: not readable (Cloudflare). [UNVERIFIED]

### Fields (from OCA's own spec, "Customized Statewide LT Data Extract Without Personally Identifying Information", 5/2/19) [LIVE]

Source: [oca-extract-info.pdf](https://github.com/housing-data-coalition/oca/blob/main/docs/oca-extract-info.pdf); CSV data dictionary in [docs/csv-data-dictionary](https://github.com/housing-data-coalition/oca/tree/main/docs/csv-data-dictionary).

- Index: `IndexNumberId` (a 64-hex hash, not the real index number; the HDC dictionary says the "true case index number that can be used to look up a specific case is replaced by a random number"), `Court`, `FiledDate`, `PropertyType`, `Classification`, `Status`, `DisposedDate`, `DisposedReasonNoPersonallyIdentifyingInfo`, `FirstPaper`, `PrimaryClaimTotal`, causes of action with amounts.
- PropertyAddresses: **City, State, PostalCode only** (no street, no unit, no BBL).
- Parties: **Role, PartyType (Person/Business/Agency), RepresentationType, Undertenant only. No name, no address.**
- Judgments: sequence, type, filed/entered dates, withpossession, latest status (Entered/Vacated/Partially Satisfied), **total judgment amount**, creditor and debtor *roles*.
- Decisions: `HighlightNoPersonallyIdentifyingInfo` (amount, interest rate, liability text, but names scrubbed). Warrants, motions, appearances, events: similar, role-only.
- Deletion rule 5: sealed, invalidated or deleted indexes arrive as `<Delete/>` records and "all invalidated, sealed or deleted OCA records [must] be expunged from the target database". Rule 2: use may be governed by an MOU with OCA.

### Republished copy

- Housing Data Coalition / OCA Data Collective CSVs on `oca-2-dev.s3.amazonaws.com/public/` (oca_index, oca_parties, oca_judgments, ...), last updated 2026-11-22, **CC BY-NC-SA 4.0**. Same de-identified content; see `github_and_data_repos.md` in this folder. [LIVE, earlier session]
- Why it does not fit the graph: with no names, no street address and a hashed index number, nothing in it can join to a debtor, a parcel or a lien. At most it gives zip-level counts of housing-court money judgments. Not worth an adapter for this project.

## 2. Other NY court bulk files

- [DoTCR Additional Data Resources](https://www.nycourts.gov/division-technology-court-research/dotcr-additional-data-resources): caseload trends, criminal, family, housing and interpreter data plus external dashboards. **No civil (Supreme, County, Civil Court commercial/consumer) case-level download.** [SEARCH]
- [Criminal Data and Reports](https://www.nycourts.gov/division-technology-court-research/criminal-data-and-reports): CSV extracts of felony/misdemeanor arraignments, de-identified; criminal, so out of scope. [SEARCH]
- Fee products: Criminal History Record Search at $95 per name ([CHRS](https://ww2.nycourts.gov/apps/chrs/index.shtml)). No published civil-judgment bulk licence or price list found. [SEARCH]
- Search portals (WebCivil Local, WebCivil Supreme, WebHousing, eCourts, NYSCEF, CourtPass): per-case lookups only, and forbidden for this project. NYSCEF terms say data "may not be mined or sold, or used in any pay-for-use application" and bar bots ([NYSCEF FAQ](https://iappscontent.courts.state.ny.us/nyscef/live/faq.htm)). [SEARCH]
- County Clerk judgment dockets (where Supreme/County Court judgments and transcripted Civil Court judgments become liens on real property): per-county search systems, no free bulk file found; covered in `recorded_judgment_indexes.md`.
- NYC Open Data: Marshal evictions (address, no names, no amounts) and the Law Department's "Case-Related Information About Civil Litigation" (`pjgc-h7uv`, City as party) are not court-wide judgment files. [SEARCH]

## 3. Policy history: why names are absent

- From 1 June 2012 the UCS stopped selling the names of parties in housing court cases in electronic form, after a letter from Chief Administrative Judge A. Gail Prudenti; announced by Sen. Liz Krueger as ending the "tenant blacklist" feed to screening companies ([press release](https://www.nysenate.gov/newsroom/press-releases/2012/liz-krueger/victory-tenants-sen-krueger-announces-courts-end)). [SEARCH]
- Screening vendors then moved to clerk-office paper-file collection (e.g. LexisNexis). [SEARCH, secondary]
- The 2019 HSTPA added Real Property Law § 227-f, barring landlords from refusing to rent because of a prospective tenant's housing-court history ([NYSBA explainer](https://nysba.org/legalease-the-use-of-tenant-screening-reports-and-tenant-blacklisting/)). [SEARCH]
- Advocates have asked OCA for more fields since (BetaNYC [Jan 2019 letter](https://beta.nyc/beta/wp-content/uploads/Letter-to-Office-of-Court-Administration-Jan.-2019-.docx.pdf)); the public release that followed kept the no-PII design. [SEARCH]

## 4. Conclusion

- No free, no-login NY court bulk file carries party names plus judgment amounts. OCA's design is deliberately de-identified, and this has been policy since 2012.
- Named NY money-judgment data for this graph has to come from county-clerk judgment dockets (lien-bearing) or recorded instruments, not from OCA extracts.
- The OCA amounts could at most add zip-level context, under a non-commercial licence (HDC copy) or unknown terms (OCA copy). Not built.

## TODO(Brandon)

- Licence/terms: the OCA XML page's terms of use could not be read (Cloudflare). If zip-level aggregates are ever wanted, confirm whether OCA's own XML carries any use restriction (spec rule 2 mentions an MOU), and whether HDC's CC BY-NC-SA blocks commercial use of their CSVs.
- Sealing: OCA requires sealed/invalidated indexes to be expunged on receipt of a delete record. Any NY housing-court data we hold from any source would need the same delete handling. Check whether pending NY eviction-record sealing bills have passed. [UNVERIFIED]
- RPL § 227-f / FCRA: if graph output about tenants' housing-court history is ever used for rental decisions, § 227-f and FCRA consumer-report rules apply. Confirm our use (judgment-creditor lien collection) is outside both.
- Do not try to re-identify the hashed OCA index numbers by joining to WebCivil or eCourts. That is portal scraping (forbidden) and works against OCA's de-identification.
