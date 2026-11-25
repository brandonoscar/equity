# Lawful public-record alternatives to voter files for locating individuals and current addresses (US, 2026)

Research notes for internal planning. This is not legal advice. Method note: this session's network blocked direct fetches of law.cornell.edu, uscode.house.gov and calawyers.org. As a result, most statutory points below come from search-result summaries of primary sources (FEC, FTC, USPS PostalPro, state agency pages, govinfo) and not from full-text reads. Points marked "[background, unverified this session]" come from the researcher's prior knowledge. Check them against statute text before relying on them.

## 1. Source-type catalog: contents, bulk availability, coverage of individuals, and source-specific use restrictions

### Takeaway
The best free government sources for finding non-owners and renters are: (a) statewide professional/occupational license files (Texas TDLR and Florida DBPR publish daily or regular bulk downloads); (b) state unclaimed-property owner files (California CSV download; New York owner-name file on request); (c) state court civil/judgment bulk extracts (Maryland, Minnesota, Indiana, Arkansas, Connecticut programs), with eviction data increasingly sealed; and (d) a few states' hunting and fishing license lists (Florida publishes them; about 20 states shield them). Motor-vehicle records are federally restricted by the DPPA. FEC contributor data is barred from commercial use. Concealed-carry lists are mostly confidential. Sex-offender registries carry criminal misuse penalties in states like California.

### Cited Findings

**Professional / occupational licenses (high value for individuals, incl. renters)**
- Texas TDLR publishes licensee CSV files on a license-download page, organized by program and updated daily. Some older data must be requested through the agency's Open Records Department — [TDLR license file download](https://www.tdlr.texas.gov/licensesearch/licfile.asp); see also [TDLR other files](https://www.tdlr.texas.gov/LicenseSearch/otherfile.asp)
- A data.gov catalog entry lists a "TDLR All Licenses" dataset, described in one listing as roughly 700,000 licenses — [data.gov TDLR All Licenses](https://catalog-old.data.gov/dataset/tdlr-all-licenses)
- Florida DBPR offers licensee download files as public records under Chapter 119, Florida Statutes, and publishes file layouts. Its readme warns that the files can exceed Excel's 65,536-row limit — [DBPR readme](https://www2.myfloridalicense.com/sto/documents/readme.pdf); [DBPR public records disclaimer](https://www2.myfloridalicense.com/?p=15875)
- Licensee records typically carry a name and an address of record (often a mailing or business address, which may be a home address for sole practitioners). That address is often current because licensees must keep it updated. [Inference; field-level layouts not verified this session]

**State unclaimed property databases**
- California State Controller: unclaimed-property records can be downloaded as CSV files, some very large — [SCO download property records](https://sco.ca.gov/upd_download_property_records.html); [SCO download files](https://sco.ca.gov/upd_download_property_files.html)
- New York Comptroller: an "Owner Name File" can be requested. It arrives as a zipped delimited .txt via a secure FTP link and includes owner names, last-known addresses, property type and reporting entity — [NY OSC Owner Name File Request Form](https://www.osc.ny.gov/unclaimed-funds/resources/owner-name-file-request-form)
- New York separately regulates "location service providers" (finders) who use this data to contact owners — [NY OSC Location Service Providers](https://www.osc.ny.gov/unclaimed-funds/resources/location-service-providers)
- Texas unclaimed property listing is on data.gov, but access requires a request (not an open download) — [data.gov Texas Unclaimed Property Listing](https://catalog.data.gov/dataset/texas-unclaimed-property-listing)
- New Jersey's administrator may release only the owner name and reported address. NJ also publishes advertised newspaper lists — [NJ Treasury Unclaimed Property FAQs](https://nj.gov/treasury/unclaimed-property/BusinessFAQs.shtml)
- Caveat: addresses are "last known" as reported by the holder. They are often stale by years, so they work as historical address links more than current-address sources. [Inference]

**Court records: civil, judgments, eviction, probate**
- Maryland Judiciary sells bulk District Court civil judgment data on subscription. The listed initial prepaid cost is $2,775 for the past 12 years of judgments plus the first monthly update — [MD Courts form DCA-107](https://mdcourts.gov/sites/default/files/court-forms/district/forms/acct/dca107.pdf/dca107.pdf); Maryland also has a data dashboard with exports — [MD Judiciary Data Dashboard](https://www.mdcourts.gov/dashboard/about)
- Indiana runs a formal trial-court bulk-data program with applications and per-case fees — [Indiana IOCS Bulk Data](https://www.in.gov/courts/iocs/statistics/bulk-data/); [Indiana bulk data applications](https://www.in.gov/judiciary/iocs/3285.htm)
- Minnesota publishes FAQs on bulk data extracts, reported to include civil and family case data — [MN Courts FAQ Bulk Data Extracts](https://MNCourts.gov/mncourtsgov/media/Research-Evaluation/FAQ-Bulk-Data-Extracts.pdf)
- Arkansas uses a data-request form and license agreement for compiled data — [Arkansas Courts Data Requests](https://arcourts.gov/administration/orjs/data-requests)
- Pew describes Connecticut as providing standardized bulk civil data to authorized third parties — [Pew: sharing civil justice data with third parties (2023)](https://www.pew.org/en/research-and-analysis/fact-sheets/2023/09/how-to-share-civil-justice-data-with-third-parties-to-improve-public-knowledge-over)
- Oklahoma: a 2009 Oklahoma Supreme Court order addresses "bulk distribution" of OSCN electronic case information. It provides case-by-case online access; current bulk terms were not confirmed — [In re Public Access to Electronic Case Information (Okla. 2009)](https://law.justia.com/cases/oklahoma/supreme-court/2009/457676.html)
- COSCA's 2019 white paper urges making court data as open as practical, balanced against privacy and legal limits — [COSCA 2019 White Paper](https://cosca.ncsc.org/sites/default/files/media/document/2019-COSCA-White-Paper.pdf)
- Eviction records: California CCP § 1161.2 (amended by AB 2819, 2016) makes the clerk withhold unlawful-detainer records from public access for 60 days after filing. They stay masked unless the landlord prevails at trial within that window. AB 2304 (2023–24) extended this to mobilehome tenancies — [CCP 1161.2 (Justia, 2019)](https://law.justia.com/codes/california/2019/code-ccp/part-3/title-3/chapter-4/section-1161-2/); [AB 2304 text](https://legiscan.com/CA/text/AB2304/2023)
- The stated legislative rationale was keeping tenant-screening companies and CRAs from picking up UD filings — [AB 2819 floor analysis](https://www.leginfo.ca.gov/pub/15-16/bill/asm/ab_2801-2850/ab_2819_cfa_20160504_172626_asm_floor.html)
- Other jurisdictions (e.g., D.C., Nevada) have outcome-based or lookback-based eviction sealing, per an industry memo — [CDIA Housing Case Record Sealing memo (2021)](https://www.cdiaonline.org/wp-content/uploads/2021/10/2021-10-14-Housing-Case-Record-Sealing-and-Expungement.pdf); see also [Network for Public Health Law: Limiting Public Access to Eviction Records (2025)](https://networkforphl.org/wp-content/uploads/2025/01/Limiting-Public-Access-to-Eviction-Records.pdf)
- Bulk court-data license agreements (MD, AR, IN) are contracts. Their terms can limit redistribution and require purging of sealed or expunged records. The specific terms were not read this session. [Inference]

**Hunting / fishing licenses and vessel registrations**
- Florida FWC publishes downloadable "public record compliant" listings of recreational and commercial license holders — [FWC: License Holders – Public Record](https://myfwc.com/license/public-record/)
- The Congressional Sportsmen's Foundation lists about 20 states that shield hunting/fishing license holder data from public-records requests (including AK, AZ, ID, IL, WA). It says more than half of states do not protect it — [CSF policy page](https://congressionalsportsmen.org/policy/protecting-personal-information-on-hunting-and-fishing-licenses-from-public-records-requests/)
- Idaho Code § 36-402 makes fish and game license identifying information confidential — [Idaho Code 36-402](https://legislature.idaho.gov/statutesrules/idstat/Title36/T36CH4/SECT36-402)
- New Hampshire RSA 214:12-a makes the applicant's mailing address, email and licensing status confidential — [NH RSA 214:12-a](https://gc.nh.gov/rsa/html/XVIII/214/214-12-a.htm)
- Wyoming restricts release (W.S. 23-1-706) — [Wyo. Stat. 23-1-706 (2022)](https://law.justia.com/codes/wyoming/2022/title-23/chapter-1/article-7/section-23-1-706/)
- Washington: HB 1876 (2024) addressed exemption of license holder data — [WA HB 1876 bill report](https://lawfilesext.leg.wa.gov/Biennium/2023-24/Htm/Bill%20Reports/House/1876%20HBA%20SGOV%2024.htm)
- A New Mexico appeals court reportedly ordered Game and Fish to disclose names and emails of permit applicants — [Courthouse News](https://courthousenews.com/hunting-and-fishing-permits/)
- LexisNexis markets a hunting/fishing license database from 21 states, which shows this data is commercially compiled — [LexisNexis source note](https://riskmanagement.lexisnexis.com/bps/web20_help/RSKM/bsp_source_hunting_and_fishing_r.html)

**Motor vehicle records (DPPA)**
- See section 2 for DPPA. Search results confirmed the statute's existence and structure but not its full text this session.

**Campaign finance contributor lists**
- The FEC states that the Act prohibits the sale or use of any information copied or obtained from FEC reports, including contributor names and addresses, "for the purpose of soliciting contributions or for commercial purposes." The rule is codified at 52 U.S.C. § 30111(a)(4) and 11 CFR 104.15 — [FEC: Sale or use of contributor information](https://www.fec.gov/updates/sale-or-use-contributor-information); [11 CFR 104.15](https://www.law.cornell.edu/cfr/text/11/104.15); [52 U.S.C. 30111 (govinfo)](https://www.govinfo.gov/link/uscode/52/30111)
- Committees may "salt" reports with up to 10 fictitious names to detect misuse — [FEC: Sale or use of contributor information](https://www.fec.gov/updates/sale-or-use-contributor-information)
- The FEC won a civil penalty against Legi-Tech for commercial use of FEC report data — [FEC v. Legi-Tech](https://www.fec.gov/legal-resources/court-cases/fec-v-legi-tech/). In FEC v. Political Contributions Data, the Second Circuit found no violation on those facts — [FEC v. Political Contributions Data](https://www.fec.gov/legal-resources/court-cases/fec-v-political-contributions-data)
- AO 2021-02: aggregated data without individual contact information does not implicate the prohibition — [FEC AO 2021-02](https://www.fec.gov/updates/ao-2021-02)

**Concealed-carry permits (mostly confidential)**
- Florida: licensee personal identifying info is confidential and exempt (Fla. Stat. § 790.0601) — [Fla. Stat. 790.0601](https://flsenate.gov/Laws/Statutes/2021/790.0601)
- North Carolina: the list of permit holders is confidential (G.S. 14-415.17) — [NCGS 14-415.17 (2015)](https://law.justia.com/codes/north-carolina/2015/chapter-14/article-54b/section-14-415.17/)
- Maine: confidential except municipality of residence and issuance date (25 M.R.S. § 2006) — [25 MRS 2006](https://www.mainelegislature.org/LEGIS/STATUTES/25/title25sec2006.html)
- Nevada Supreme Court held permit holder identities and permit status are public, with application contents exempt — [RCFP](https://www.rcfp.org/nevada-high-court-says-portions-gun-permit-records-public/)
- RCFP state chart on gun permit data access — [RCFP: Gun permits](https://www.rcfp.org/open-government-sections/k-gun-permits/). A 2013 Stateline report said only a handful of states (IA, MT, NC, TN, WV) would give unfettered access. NC has since made its list confidential, so that list is outdated — [Pew Stateline 2013](https://www.pewstates.org/projects/stateline/headlines/lawmakers-move-swiftly-to-block-release-of-gun-permit-records-85899457096)

**Sex offender registries**
- California Penal Code § 290.46: using Megan's Law information to commit a misdemeanor carries an additional fine of $10,000–$50,000. Use to commit a felony adds a 5-year term. Civil remedies include up to treble damages (minimum $250) plus fees, or a civil penalty up to $25,000. The DOJ states the information may be used only to protect a person at risk; use in employment, housing, insurance, loans, credit and similar decisions is generally prohibited — [CA DOJ Megan's Law: Penalties for Misuse](https://meganslaw.ca.gov/AboutMegansLaw/PenaltiesForMisuse); [Penal Code 290.46 (Justia 2023)](https://law.justia.com/codes/california/code-pen/part-1/title-9/chapter-5-5/section-290-46/)

**Property tax rolls/parcel layers, recorder indexes, business registries, UCC, permits, city business licenses, bankruptcy, obituaries/death records**
- No new sources were verified this session for these types. The project already uses parcel, recorder, business registry and court/lien sources. See Gaps.

### Inferences
- Ranked by added coverage of non-owners/renters: (1) professional/occupational license bulk files (millions of individuals statewide in TX/FL/NY/CA, with addresses that are relatively current); (2) civil court party data (defendants in debt/small-claims cases are disproportionately non-owners, but party addresses are often missing or masked in bulk extracts); (3) unclaimed property owner files (huge coverage but stale addresses); (4) hunting/fishing licenses in states that publish them (FL); (5) city business licenses and building permits (contractors and sole proprietors); (6) UCC debtor names (individual debtors with addresses, mostly sole proprietors/farmers).
- Business-entity officer and registered-agent addresses frequently resolve to commercial agents or business addresses, not residences, so they add limited residential coverage.
- Every bulk court-data product should be assumed to carry a license agreement that requires honoring later sealing/expungement. Eviction records in CA are unusable as a full feed because of masking.

### Gaps
- DPPA-style restrictions on vessel registrations: whether a state's vessel registration files are DPPA-covered depends on whether the state DMV holds them. Not verified this session.
- Building permits/code enforcement, city business license open data, UCC bulk products (state SOS fees and terms), PACER bulk/RSS terms, and death-record/obituary access (SSA Death Master File restrictions under 15 CFR Part 1110; state vital-record limits) were not researched within the tool budget.
- Field-level confirmation (whether a home address is included) for TDLR/DBPR files was not verified.

## 2. Federal and state laws limiting use of these sources for locating people or making consumer decisions (FCRA, DPPA, GLBA, data-broker registration, commercial-use restrictions)

### Takeaway
The main legal risk for an internal database linking people to property and debt records is the FCRA. If the compilation is furnished to third parties, or used to make eligibility decisions about consumers (credit, insurance, employment, housing), it can become a "consumer report," regardless of disclaimers. The FTC enforced this against Spokeo (2012) and TruthFinder/Instant Checkmate (2023). The CFPB's December 2024 proposal to extend FCRA coverage to more data brokers was withdrawn on May 15, 2025. Four registry states (CA, VT, OR, TX), plus reportedly CT and NJ as of 2026, impose data-broker registration. These generally target entities that sell or license data about consumers they do not have a direct relationship with; purely internal use is less clearly covered.

### Cited Findings

**FCRA**
- FTC: Spokeo paid $800,000 to settle charges that it operated as a consumer reporting agency (marketing profiles to HR/recruiters) without FCRA compliance — [PCWorld on Spokeo](https://www.pcworld.com/article/465241/spokeo_data_broker_to_pay_800000_in_ftc_privacy_case.html)
- FTC (2023): TruthFinder and Instant Checkmate agreed to a $5.8 million penalty for FCRA violations, including furnishing reports to users without a permissible purpose. "Not a CRA" disclaimers did not control because the companies promoted reports for tenant/employee screening — [FTC press release, Sept 2023](https://ftc.gov/news-events/news/press-releases/2023/09/ftc-says-truthfinder-instant-checkmate-deceived-users-about-background-report-accuracy-violated-fcra); [Sheppard Mullin analysis](https://www.sheppard.com/insights/blogs/ftc-settles-fcra-suit-against-people-search-companies)
- 2014 FTC settlement with data brokers over FCRA — [Hunton privacy blog](https://www.huntonprivacyblog.com/2014/04/15/ftc-announces-settlement-data-brokers-alleged-fcra-violations/)
- The FTC's 2011 staff report "Forty Years of Experience with the FCRA" is the canonical interpretation summary. Under it, a consumer report must bear on one of the seven listed characteristics and be used or expected to be used for an eligibility purpose — [FTC 40 Years report (PDF)](https://www.ftc.gov/sites/default/files/documents/reports/40-years-experience-fair-credit-reporting-act-ftc-staff-report-summary-interpretations/110720fcrareport.pdf); statute: [15 U.S.C. 1681a (govinfo)](https://govinfo.gov/link/uscode/15/1681a); FTC FCRA text (March 2026 version): [FTC FCRA PDF](https://www.ftc.gov/system/files/ftc_gov/pdf/fcra-march-2026.pdf)
- CFPB: the proposed rule "Protecting Americans From Harmful Data Broker Practices (Regulation V)" (proposed Dec 2024) was withdrawn by notice published May 15, 2025. The Bureau said the proposal did not align with its current FCRA interpretation and that it would propose a new rule if needed — [Federal Register, 90 FR (May 15, 2025)](https://www.govinfo.gov/content/pkg/FR-2025-05-15/html/2025-08644.htm); [Orrick InfoBytes](https://infobytes.orrick.com/2025-05-16/cfpb-withdraws-its-proposed-rule-on-data-brokers/)
- The withdrawn proposal would have treated many data brokers (including credit header sellers) as CRAs — [American Banker](https://www.americanbanker.com/news/cfpb-withdraws-proposed-rule-to-rein-in-data-brokers); CFPB SBREFA outline with credit-header section — [CFPB SBREFA outline](https://files.consumerfinance.gov/f/documents/cfpb_consumer-reporting-rule-sbrefa_outline-of-proposals.pdf)
- [background, unverified this session] FCRA § 604 (15 U.S.C. § 1681b) permissible purposes include "review or collection of an account" of the consumer (§ 1681b(a)(3)(A)). Debt-collection use of a CRA's report is therefore permitted. A records compilation built by a company solely for its own internal use, and not furnished to third parties, generally is not a "consumer reporting agency" output, because a CRA is defined by "furnishing consumer reports to third parties" (§ 1681a(f)).

**DPPA (18 U.S.C. §§ 2721–2725)**
- [background, unverified this session; Cornell and OLRC hosts blocked] The DPPA bars state DMVs and any recipient from disclosing or using "personal information" (which includes name and address) from motor vehicle records except for 14 permissible uses in § 2721(b). Uses relevant here include: (b)(3) verifying the accuracy of personal information submitted by an individual to a business, and correcting it to prevent fraud or pursue legal remedies or to recover on a debt; (b)(4) use in connection with civil, criminal or administrative proceedings, including service of process; (b)(6) insurers; (b)(8) licensed private investigators for a permitted use; (b)(12) bulk distribution for surveys, marketing or solicitations only with the person's express consent. § 2721(c) lets authorized recipients resell or redisclose only for a permitted use, with 5-year records of each recipient and purpose. § 2724 provides a civil action with liquidated damages of $2,500 per violation. Verify against [18 U.S.C. 2721 on govinfo](https://www.govinfo.gov/app/details/USCODE-2023-title18/USCODE-2023-title18-partI-chap123-sec2721).

**GLBA / credit header**
- The FTC's 2001 Trans Union opinion treated "credit header" data (name, address, SSN, phone) as distinct from consumer reports and noted GLBA § 6802(e) exceptions (citing § 6802(e)(8)) — [FTC Trans Union memo opinion (2001)](https://www.ftc.gov/system/files/documents/cases/010508transunionmemoopinion.pdf)
- Industry (Experian/CDIA) argues credit header is regulated under GLBA and is essential for fraud prevention and identity verification — [Experian blog (Oct 2024)](https://www.experian.com/blogs/news/2024/10/01/credit-header-data-an-indispensable-tool-to-combatting-fraud/); [CDIA response to NCLC](https://www.cdiaonline.org/wp-content/uploads/2023/02/NCLC-Letter-on-Credit-Headers-CDIA-Response.pdf)
- NCLC asked CFPB to clarify that credit header derived from consumer report files is a consumer report — [NCLC comments (2023)](https://www.nclc.org/wp-content/uploads/2023/07/NCLC-Comments-to-CFPB-RFI-on-Data-Brokers-Chi-Chi-Wu.pdf). With the 2025 withdrawal, the issue remains unresolved by rule.
- EPIC (July 2025): all 19 comprehensive state privacy laws passed by July 1, 2025 include FCRA and GLBA exemptions — [EPIC white paper](https://epic.org/wp-content/uploads/2025/07/EPIC-Unbridled-and-Underregulated-July2025-1.pdf)

**State data-broker registration laws**
- California, Oregon, Texas and Vermont require entities meeting their "data broker" definitions to register. As of 2026, Connecticut and New Jersey are reported to have added registries — [LexisNexis comparative guide (Apr 2025)](https://www.lexisnexis.com/community/amp-insights/84/navigating-data-broker-laws-a-comparative-guide-to-key-state-laws); [DataGrail 2026 field guide](https://www.datagrail.io/blog/data-privacy/data-broker-compliance/)
- Differences, per Bloomberg Law summaries: CA and VT require "knowingly" collecting and selling. TX and OR do not explicitly require that. 2025 Texas amendments may reach businesses that merely process third-party data. OR and VT have no minimum thresholds. TX applies at 50,000 Texas consumers. CA, TX and OR exclude FCRA-covered entities; VT does not. Fees: TX $300/yr, CA about $6,000 — [Bloomberg Law: data broker rules may catch businesses off guard](https://news.bloomberglaw.com/business-and-practice/data-broker-rules-from-regulators-may-catch-businesses-off-guard); [Bloomberg Law: More states aim to rein in broker sales](https://news.bloomberglaw.com/us-law-week/more-states-aim-to-rein-in-track-broker-sales-of-personal-data)
- California is the most demanding model (registration, centralized deletion mechanism (DROP) under the Delete Act, audits) — [DataGrail 2026 field guide](https://www.datagrail.io/blog/data-privacy/data-broker-compliance/)
- Privacy Rights Clearinghouse/EFF (June 2025) found many brokers registered in some states but not others — [PRC Vermont letter](https://privacyrights.org/sites/default/files/2025-06/2025-06-24%20-%20Vermont%20Data%20Broker%20Letter.pdf); [PRC Texas letter](https://privacyrights.org/sites/default/files/2025-06/2025-06-24%20-%20Texas%20Data%20Broker%20Letter.pdf); [PRC Oregon letter](https://privacyrights.org/sites/default/files/2025-06/2025-06-24%20-%20Oregon%20Data%20Broker%20Letter.pdf)

**State restrictions on commercial use of public records**
- Arizona (A.R.S. § 39-121.03): requesters seeking records for a "commercial purpose" (sale, resale, or obtaining names for solicitation) must say so and may be charged commercial fees. A custodian who finds abuse or misuse can apply to the Governor to prohibit furnishing the records. Arizona SB 1372 (2025) amended this area; current text unverified — [AZ public records law excerpts](https://azdot.gov/sites/default/files/2019/08/15-046-arizona-public-records-law-statutory-excerpts.pdf); [FindLaw ARS 39-121.03](https://codes.findlaw.com/az/title-39-public-records-printing-and-notices/az-rev-st-sect-39-121-03/); [AZ SB1372 summary (2025)](https://www.azleg.gov/legtext/57leg/1R/summary/H.SB1372_051525_SIGNED.DOCX.htm)
- Kentucky Open Records Act (KRS 61.874): defines "commercial purpose" broadly (sale, resale, solicitation, or any use from which profit is expected), permits higher fees and requires certification/contract for commercial requesters. Kentucky's 1990s accident-report solicitation restriction was struck down on First Amendment grounds (Amelkin) — [KY LRC Open Meetings/Records guide](https://legislature.ky.gov:443/LRC/Publications/Documents/OpenMtgsRecords.pdf); [Amelkin v. Commonwealth (W.D. Ky. 1996)](https://law.justia.com/cases/federal/district-courts/FSupp/936/428/1486946/); [RCFP](https://www.rcfp.org/?p=35563)
- An internal (non-solicitation, non-resale) use may fall outside many "commercial purpose" definitions, but Kentucky's "any use by which the user expects a profit" is broad enough to cover a for-profit internal database. [Inference from the KY definition quoted above]

### Inferences
- The FCRA risk depends on the use. An internal database used by the company itself to locate debtors or owners, never furnished to others, is generally not a consumer report under the CRA definition. Risk rises if (a) results are shared with clients/partners for decisions about consumers, (b) data is obtained from a CRA (then the CRA's permissible-purpose and end-user certifications bind), or (c) the database is used to deny credit/housing/employment.
- Data-broker registration generally turns on selling or licensing data about consumers with no direct relationship. A strictly internal, non-redistributed database may not trigger it, but Texas's 2025 broadening ("processing") and Oregon/Vermont's no-threshold rules make this state-specific and ambiguous.
- Source-specific restrictions (FEC, DPPA, sex-offender registries, CA eviction masking, bulk court license agreements) apply regardless of whether the user is a "data broker."

### Gaps
- Full text of 18 U.S.C. § 2721 and 15 U.S.C. §§ 1681a/1681b could not be fetched (host blocked). Permissible-use lists above are from background knowledge.
- No NCSL compilation of state commercial-use restrictions was found. Other states with solicitation bars on specific records (e.g., accident reports, arrest records) were not catalogued.
- Exact current California Delete Act/DROP dates and Texas 2025 amendment text were not verified from primary sources.

## 3. Commercial substitutes for the "current address" function and their permissible-use conditions

### Takeaway
USPS NCOALink (via licensed service providers) only updates addresses on a mailing list you already own, for the purpose of preparing USPS mail. The licenses bar using it to compile or maintain a list for non-mailing purposes. Credit-header data (name/address/SSN from bureau files) is sold under GLBA exceptions, mainly for fraud prevention, identity verification and similar uses. Its non-FCRA status rests on longstanding FTC views and remains contested.

### Cited Findings
- NCOALink field of use is "use in mailing operations to prepare Deliverables for delivery by USPS." The End User license purpose is to update "that Entity's Mailing Lists used to prepare that Entity's Deliverables for delivery by the USPS" — [USPS NCOALink End User License](https://postalpro.usps.com/mnt/glusterfs/2020-01/End_User_License.pdf); [FSP License](https://postalpro.usps.com/mnt/glusterfs/2020-01/FSP_License.pdf); [LSP License v29 (2024)](https://postalpro.usps.com/mnt/glusterfs/2024-07/LSP_License_v29.pdf)
- A "Mailing List" is defined as at least 100 names and addresses used for addressing USPS deliverables. Uses other than addressing mail pieces are excluded — [LSP License](https://postalpro.usps.com/mnt/glusterfs/2020-01/LSP_License.pdf); [Developer License](https://postalpro.usps.com/storages/2017-01/DEVELOPER_LICENSE.PDF)
- List owners must sign a Processing Acknowledgement Form (PAF). Brokers cannot sign for owners and are never the final repository of updated data — [USPS PAF Guide](https://postalpro.usps.com/mnt/glusterfs/2018-12/PAF_Guide.pdf); [USPS NCOALink overview](https://postalpro.usps.com/mailing-and-shipping-services/NCOALink)
- Credit header: see section 2 (FTC 2001 Trans Union opinion citing GLBA § 6802(e); CDIA/Experian vs. NCLC dispute; CFPB 2024 proposal withdrawn May 2025).

### Inferences
- NCOA can lawfully refresh addresses of people already in the database (e.g., parcel owners with a mailing address) when the company is mailing them, such as debt or ownership notices. Using NCOA output purely as a skip-tracing lookup without mailing likely falls outside the license field of use.
- Credit-header/skip-trace products from bureaus or aggregators come with contractual GLBA/DPPA permissible-use certifications (commonly including "collection of a debt" and "fraud prevention"). The buyer must certify a purpose and keep records.

### Gaps
- Exact NCOALink clause barring list compilation was truncated in search results (MPE Data User license). Read the full license PDFs.
- Text of 15 U.S.C. § 6802(e) exceptions was not fetched. Which subsections vendors rely on (e.g., (e)(3) fraud prevention, (e)(8) compliance with law) was not confirmed.

## 4. State examples of strong bulk sources (actionable list)

### Takeaway
Verified actionable bulk sources from this session: TX TDLR licenses (daily CSV), FL DBPR licensees (downloads under ch. 119), FL FWC hunting/fishing license holders, CA SCO unclaimed property (CSV), NY OSC unclaimed owner file (on request), MD District Court civil judgments ($2,775 subscription), and the Indiana, Minnesota and Arkansas court bulk-data programs.

### Cited Findings
- Texas — TDLR licensee CSVs, daily — [TDLR](https://www.tdlr.texas.gov/licensesearch/licfile.asp)
- Florida — DBPR licensee files — [DBPR readme](https://www2.myfloridalicense.com/sto/documents/readme.pdf); FWC license holders — [FWC](https://myfwc.com/license/public-record/)
- California — SCO unclaimed property CSV — [SCO](https://sco.ca.gov/upd_download_property_records.html); SCO also has an Estates of Deceased Persons file (relevant to probate/death linking) — [SCO Estates file](https://www.sco.ca.gov/upd_estates_investigator.html)
- New York — OSC unclaimed funds owner file — [NY OSC](https://www.osc.ny.gov/unclaimed-funds/resources/owner-name-file-request-form)
- Maryland — civil judgment bulk subscription — [MD form DCA-107](https://mdcourts.gov/sites/default/files/court-forms/district/forms/acct/dca107.pdf/dca107.pdf)
- Indiana — trial-court bulk data — [Indiana IOCS](https://www.in.gov/courts/iocs/statistics/bulk-data/)
- Minnesota — bulk extracts — [MN Courts FAQ](https://MNCourts.gov/mncourtsgov/media/Research-Evaluation/FAQ-Bulk-Data-Extracts.pdf)
- Arkansas — compiled court data by license agreement — [AR Courts](https://arcourts.gov/administration/orjs/data-requests)

### Inferences
- Florida is unusually strong for non-owner coverage because of broad ch. 119 access (DBPR, FWC). Its concealed-carry data, however, is exempt.
- Each bulk license or terms document should be reviewed for redistribution limits. These matter less for an internal, non-redistributed database, but purge and sealing-compliance clauses still bind.

### Gaps
- Not verified: New York's data.ny.gov licensee datasets, California DCA licensee downloads, Washington L&I contractor data, Pennsylvania/Illinois license lookups, statewide court open data in other states (e.g., Oregon, Connecticut terms), state vessel-registration bulk files.
