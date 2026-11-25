# Voter file access and permitted uses: NM, OK, OR, TX, UT, WA, WY (west_b)

Research date: 2026-11-25. Use case tested: private company obtains the statewide voter file for a NON-political, internal commercial records database (locate people, link them to property/debt records), with no redistribution and no mailing or solicitation.

**Method and limits (read first):** Outbound fetches to every government and legal-code host failed in this session (DNS blocked: le.utah.gov, nmlegis.gov, oklahoma.gov, sos.wyo.gov, law.justia.com, texas.public.law, ncsl.org, ballotpedia.org). All findings below come from search-engine extracts of the official statute/forms pages (URLs cited), not from full-page reads. Exact quotes are reproduced only where the search extract carried the statutory or form text. Items from memory that I could not confirm are confined to Inferences/Gaps and labeled. **Before relying on any entry, confirm against the cited official pages. This is internal planning research, not legal advice.**

Summary verdicts:

| State | Verdict for internal commercial locate/link DB | One-line reason |
|---|---|---|
| New Mexico | NOT ALLOWED | Affidavit limits use to "governmental or election and election campaign purposes only"; SOS defines "commercial purposes" to include any use where the user "can reasonably anticipate monetary gain". |
| Oklahoma | NOT ALLOWED | SB 1086 (eff. Nov 1, 2025) makes commercial use of the list unlawful and limits access to OK residents/citizens, candidates, and others authorized by law (26 O.S. § 7-103.2). |
| Oregon | NOT ALLOWED | ORS 247.955(1): no recipient "shall use any information in the list for commercial purposes"; only exception is resale to candidates/committees for political purposes. |
| Texas | ALLOWED WITH CONDITIONS (most permissive in this group) | Statute bars only use "in connection with advertising or promoting commercial products or services" (§ 18.009 / § 18.067, Class A misdemeanor). Requires a sworn no-commercial-advertising affidavit and a $75 deposit. File includes full DOB. |
| Utah | NOT ALLOWED (likely; text not fully verified) | The list carries statutory use and disclosure restrictions, and DOB is private for everyone. The 2026 SB 153 rewrite (eff. Apr 6, 2026) was not read in full. |
| Washington | NOT ALLOWED (under SOS terms; statutory felony arguably not triggered) | The criminal ban (RCW 29A.08.740) targets mailing ads or solicitations. But the SOS download terms and RCW 42.56.070(8) bar giving lists of individuals "for commercial purposes", and an AG opinion reads that bar as not limited to direct contact. |
| Wyoming | NOT ALLOWED | W.S. 22-2-113(a) furnishes lists only to enumerated political requesters, and the buyer affirms under penalty of perjury that use is "for political purposes only" and not commercial. |

## New Mexico

### Takeaway
NOT ALLOWED. NMSA § 1-4-5.5 requires a signed affidavit that voter data will be used "for governmental or election and election campaign purposes only." The Secretary of State defines "commercial purposes" broadly enough (any anticipated monetary gain) to cover an internal business database, and unlawful use is a separate criminal offense (§ 1-4-5.6).

### Cited Findings
- **Who and how:** Data is provided on written request to any requester who signs the SOS-prescribed affidavit. "Each requester of voter data, mailing labels or special voter lists shall sign an affidavit that the voter data, mailing labels and special voter lists shall be used for governmental or election and election campaign purposes only" (§ 1-4-5.5). The SOS "shall prescribe the form of the affidavit." — [Justia NMSA 1-4-5.5 (2011)](https://law.justia.com/codes/new-mexico/2011/chapter1/article4/section1-4-5.5/); [Justia NMSA 1-4-5.5 (2020)](https://law.justia.com/codes/new-mexico/2020/chapter-1/article-4/section-1-4-5-5/)
- The SOS rule requires "all requesters of voter file data or public service requests" to "complete the affidavit of authorization prescribed by the secretary of state." — [1.10.35 NMAC](https://www.srca.nm.gov/parts/title01/01.010.0035.html)
- The 2015 amendment (eff. July 1, 2015) added definitions of "election campaign purposes", "governmental purposes", "mailing labels", "special voter list" and "voter data". — [Justia NMSA 1-4-5.5 (2020)](https://law.justia.com/codes/new-mexico/2020/chapter-1/article-4/section-1-4-5-5/)
- **"Commercial purposes":** The SOS materials, as quoted in federal litigation, say it "includes use in connection with advertising or promoting commercial products or services, or for the purpose of sale, resale, solicitation, or any purpose in which the user can reasonably anticipate monetary gain." — [Voter Reference Foundation v. Torrez, No. 24-2133 (10th Cir. Nov. 25, 2025)](https://law.justia.com/cases/federal/appellate-courts/ca10/24-2133/24-2133-2025-11-25.html); [D.N.M. 2024 order, Doc. 173](https://law.justia.com/cases/federal/district-courts/new-mexico/nmdce/1:2022cv00222/472295/173/)
- **Penalty:** "Unlawful use of voter data, mailing labels or special voter lists consists of the knowing and willful use of such information for purposes prohibited by the Voter Records System Act" (§ 1-4-5.6). — [FindLaw NMSA 1-4-5.6](https://codes.findlaw.com/nm/chapter-1-elections/nm-st-sect-1-4-5-6/)
- **Litigation (recent):** On Nov. 25, 2025 the Tenth Circuit affirmed that the NVRA preempts New Mexico's restrictions to the extent they bar broad public disclosure/online publication of voter data, and remanded the First Amendment claims. The court noted the State relies on the "governmental or election and campaign purposes only" restriction to ban internet publication. The district court (2024) had held the data-sharing ban and use restrictions constitutional under the First Amendment. — [10th Cir. opinion](https://law.justia.com/cases/federal/appellate-courts/ca10/24-2133/24-2133-2025-11-25.html); [FindLaw summary](https://caselaw.findlaw.com/court/us-10th-circuit/117976439.html); [D.N.M. Doc. 173](https://law.justia.com/cases/federal/district-courts/new-mexico/nmdce/1:2022cv00222/472295/173/)
- **Fees:** $15.00 setup fee on all voter data requests; $4.00 per 1,000 records with voting history (electronic); the maximum for any request is $600.00. — [NM SOS Voter Data Information](https://www.sos.nm.gov/voting-and-elections/data-and-maps/voter-data-information/). A vendor page gives $3.00/1,000 without history, and Ballotpedia lists an older $5,215 figure; both conflict with or predate the SOS cap. — [voterfile.io NM](https://voterfile.io/new-mexico-voter-file-software); [Ballotpedia](https://ballotpedia.org/Availability_of_state_voter_files)
- **Fields:** Name, address, telephone number (only with the voter's consent), year of birth, party affiliation, registration data (county, precinct, districts), and voting history. Withheld: SSN and day/month of birth. — [NM SOS Voter Data Information](https://www.sos.nm.gov/voting-and-elections/data-and-maps/voter-data-information/); [Ballotpedia](https://ballotpedia.org/Availability_of_state_voter_files)
- **Pending changes:** 2024 SB 157 proposed amendments to § 1-4-5.5. Its enactment was not confirmed. — [SB 157 (2024)](https://www.nmlegis.gov/Sessions/24%20Regular/bills/senate/SB0157.PDF)

### Inferences
- An internal locate/link database used in a debt- or property-related business is neither "governmental" nor "election campaign" use, and it falls squarely within "any purpose in which the user can reasonably anticipate monetary gain." Signing the affidavit for this use would be a false affidavit. The lack of redistribution does not cure this.
- The 10th Cir. NVRA preemption ruling concerns public disclosure/publication of voter data. Nothing found suggests it licenses commercial use, and the case was remanded, so the use restriction should be treated as enforceable.

### Gaps
- Could not read the current (post-2023) text of §§ 1-4-5.5 and 1-4-5.6. From memory, unverified: unlawful use is a fourth-degree felony, with an additional per-voter fine. Confirm on nmlegis.gov.
- Whether 2023 HB 4 (Voting Rights Act) amended § 1-4-5.5 could not be confirmed; nmlegis.gov was blocked.
- No NM AG opinion on "commercial purposes" was located.

## Oklahoma

### Takeaway
NOT ALLOWED. SB 1086 (signed May 27, 2025; effective Nov 1, 2025) restricts access to the voter registration list to Oklahoma citizens/residents, candidates and others authorized by law under 26 O.S. § 7-103.2. It makes it unlawful for any person to use the list for commercial purposes, with exceptions only for campaigns, parties, government officials and pollsters.

### Cited Findings
- **Status:** SB 1086 was "Signed by Governor May 27, 2025", and the act is effective November 1, 2025. — [Plural Policy SB1086](https://open.pluralpolicy.com/ok/bills/2025/SB1086); [SB1086 ENGR](https://www.oklegislature.gov/cf_pdf/2025-26%20ENGR/SB/SB1086%20ENGR.PDF)
- **Who may obtain:** The House summaries describe the electronic list as available to Oklahoma citizens, candidates and their representatives, and other persons authorized by state law, on completion of an application form; the House amendment text says "free of charge." — [SB1086 ENGR BILLSUM](https://oklegislature.gov/cf_pdf/2025-26%20SUPPORT%20DOCUMENTS/BILLSUM/House/SB1086%20ENGR%20BILLSUM.PDF); [SB1086 HASB](https://www.oklegislature.gov/cf_pdf/2025-26%20AMENDMENTS/Amendment%20and%20Engr/SB1086%20HASB%20AND%20ENGR.PDF)
- The State Election Board says basic EDW access "does not include the list of currently registered voters"; "only individuals that meet the qualifications of 26 O.S. § 7-103.2 may request access." Press coverage reports that, effective Nov. 1, 2025, access is limited to bona fide Oklahoma residents who are U.S. citizens, among other groups. — [OK EDW readme](https://oklahoma.gov/content/dam/ok/en/elections/ok-election-data-warehouse/readme-basic.pdf); [Southwest Ledger](https://www.southwestledger.news/news/state-election-board-us-justice-department-settle-oklahoma-voter-registration-spat)
- **Use restriction:** The bill makes it "unlawful for any person to use the voter registration list for commercial purposes." Campaigns, political parties, government officials and public opinion pollsters are excluded when they contact or interact with voters. It also prohibits providing the list to a foreign national, foreign commercial interest or foreign governmental entity. — [SB1086 ENGR](https://www.oklegislature.gov/cf_pdf/2025-26%20ENGR/SB/SB1086%20ENGR.PDF); [SB1086 HCS](https://www.oklegislature.gov/cf_pdf/2025-26%20COMMITTEE%20SUBS/HCSS/SB1086%20HCS.PDF)
- **Pre-SB 1086 form:** The State Election Board's request form had the requester attest under penalty of perjury that they qualify, and acknowledge that use of the list "for commercial marketing or advertising" is unlawful. — [EDW VR list form](https://oklahoma.gov/content/dam/ok/en/elections/ok-election-data-warehouse/edw-form-vrlist.pdf)
- **Fields:** The EDW layout includes date of birth, registration address, county, and election dates and method of voting. — [OK EDW readme](https://oklahoma.gov/content/dam/ok/en/elections/ok-election-data-warehouse/readme-basic.pdf). A full or partial SSN or driver license number in a voter record "shall not be considered a public record and shall be kept confidential." — [OK Personally Identifiable Data Notice](https://oklahoma.gov/elections/about-us/personally-identifiable-data-notice.html)
- **Confidential voters:** Oklahoma runs voter privacy programs (e.g., address confidentiality). — [OK voter privacy programs](https://www.oklahoma.gov/elections/voter-registration/voter-privacy-programs.html)
- **Context:** In a March 2026 settlement with DOJ, Oklahoma will provide its statewide list with privacy protections; this concerns federal access, not private access. — [OK AG release](https://oklahoma.gov/oag/news/newsroom/2026/march/drummond-enters-settlement-with-doj-to-safeguard-voter-registration-data.html)

### Inferences
- The change from "commercial marketing or advertising" (old form) to "commercial purposes" (SB 1086) widens the ban well beyond solicitation. An internal commercial locate database is "commercial purposes" in plain meaning, and a non-Oklahoma company may not even qualify as a requester.
- Oklahoma includes full DOB, which would make the file high-value for record linkage, but that use is now barred.

### Gaps
- The enrolled text of 26 O.S. § 7-103.2 (exact wording, definition of "commercial purposes" if any, penalty class) was not readable; oklegislature.gov/oklahoma.gov were blocked. The penalty is unconfirmed.
- Whether a fee still applies after SB 1086 ("free of charge" appears in amendment text) is unconfirmed.

## Oregon

### Takeaway
NOT ALLOWED. Anyone may buy the statewide list ($500), but ORS 247.955(1) flatly bars use of "any information in the list for commercial purposes." The only carve-out is resale to candidates or political committees for political purposes.

### Cited Findings
- **Operative text, ORS 247.955:** "(1) Except as provided in subsection (2) of this section, no person to whom a list of electors is made available or supplied under ORS 247.940 or 247.945 shall use any information in the list for commercial purposes." "(2) A person shall not be considered to use for commercial purposes any information contained in a list of electors made available or supplied under ORS 247.940 or 247.945 if the person obtains the list of electors for the purposes of resale to candidates or political committees for political purposes only." — [oregon.public.law ORS 247.955](https://oregon.public.law/statutes/ors_247.955); [FindLaw ORS 247.955](https://codes.findlaw.com/or/title-23-elections/or-rev-st-sect-247-955/)
- **Who and how:** Lists are delivered to "any person" on request (ORS 247.945). "Except as provided in ORS 247.940(4), the secretary of state must charge a $500 fee" for the statewide list; OAR 165-002-0020 confirms "the charge for a statewide voter list is $500.00", and its subsection (8) repeats that the list must not be used for commercial purposes. — [oregon.public.law ORS 247.945](https://oregon.public.law/statutes/ors_247.945); [OAR 165-002-0020 (Cornell LII)](https://www.law.cornell.edu/regulations/oregon/Or-Admin-Code-SS-165-002-0020)
- **Withheld:** The list "may not contain any information about participants in the Address Confidentiality Program established under ORS 192.820 to 192.868." ORS 247.948 governs "information required for or prohibited from inclusion in lists of electors." — [ORS ch. 247](https://www.oregonlegislature.gov/bills_laws/ors/ors247.html); [ORS 247.948](https://oregon.public.law/statutes/ors_247.948)
- The Oregon AG has issued opinions (from 1968) construing "list" and "commercial purposes"; their contents were not retrieved. — [Justia ORS 247.955 annotations](https://law.justia.com/codes/oregon/2019/volume-06/chapter-247/section-247-955/)

### Inferences
- "Commercial purposes" is undefined in the text found but unqualified, unlike Texas or Washington, which tie their bans to advertising or solicitation. An internal business database is very likely "commercial purposes." Non-redistribution does not help; the ban is on use, not on resale.

### Gaps
- ORS 247.948 field list (whether DOB/birth year, phone are included) was not readable. From memory, unverified: Oregon lists have included birth date/year and phone. Confirm.
- Penalty for violating ORS 247.955 (likely a civil penalty under ORS 260.995) is unconfirmed.

## Texas

### Takeaway
ALLOWED WITH CONDITIONS. Texas furnishes the statewide list to "any person" on request. The statutory use ban is narrow: only use "in connection with advertising or promoting commercial products or services" is an offense (Class A misdemeanor). An internal locate/link database with no advertising, solicitation or redistribution falls outside that text. Conditions: a sworn (notarized) affidavit, the $75 deposit, and strict internal-only use with no marketing.

### Cited Findings
- **Who and how:** The SOS must furnish statewide list information to any person on request, within 15 days (§ 18.066). The request requires a mailed form, a notarized no-commercial-use affidavit and a $75 deposit payable to the SOS. "Files will not be released or uploaded until full payment is received." — [Tex. Elec. Code ch. 18](https://statutes.capitol.texas.gov/Docs/EL/htm/EL.18.htm); [SOS public information request form (pi.pdf)](https://www.sos.state.tx.us/elections/forms/pi.pdf); [CampaignKnock TX guide](https://www.campaignknock.com/voter-list/texas)
- **Affidavit text (SOS form):** The requester swears that information from the Statewide Computerized Voter Registration List "will not be used to advertise or promote commercial products or services." The SOS index lists a newer "Voter Data Request and Affidavit" form (24-1). — [SOS form 24-4f](https://www.sos.state.tx.us/elections/forms/pol-sub/24-4f.pdf); [SOS form 24-1f](https://www.sos.texas.gov/elections/forms/pol-sub/24-1f.pdf); [SOS forms index](https://www.sos.state.tx.us/elections/forms/pol-sub/index.shtml)
- **Offense, § 18.009:** "(a) A person commits an offense if the person uses information in connection with advertising or promoting commercial products or services that the person knows was obtained under Section 18.008 [SOS form quotes: Section 18.066]." "(b) An offense under this section is a Class A misdemeanor." The SOS form cites § 18.067 as the parallel offense for the statewide list, also a Class A misdemeanor. — [Tex. Elec. Code ch. 18](https://statutes.capitol.texas.gov/Docs/EL/htm/EL.18.htm); [texas.public.law § 18.009](https://texas.public.law/statutes/tex._election_code_section_18.009); [SOS form 24-4f](https://www.sos.state.tx.us/elections/forms/pol-sub/24-4f.pdf)
- **Use guidance:** The Texas Press Association reports that the code allows list information to be used for political campaign purposes, "but not for the promotion of commercial products or services." — [Texas Press Association](https://www.texaspress.com/node/7171)
- **Fields:** NCSL lists name, DOB, registration number and residence address as contents of the Texas list. SOS seminar material says DOB is confidential for all voters "unless the request is for a list of voters with voter information under Chapter 18," so the Chapter 18 list does carry DOB. DOB of protected persons cannot be posted online. — [NCSL summary](https://www.ncsl.org/elections-and-campaigns/access-to-and-use-of-voter-registration-lists); [SOS 2026 seminar, voter reg fundamentals](https://www.sos.state.tx.us/elections/forms/seminar/2026/voter-reg-fundamental.pdf)

### Inferences
- The statute's trigger is "advertising or promoting commercial products or services." An internal database used to locate people and link them to property/debt records, never used to market, contact or solicit, is not on its face covered. That makes Texas the one state in this group where the use case is plausibly lawful.
- Risk points: (1) if the database is used to locate debtors for collection outreach, a prosecutor could argue that contact "promotes" a commercial service; keep the database strictly non-outreach. (2) The exact wording of the current affidavit (form 24-1) should be checked in case it is broader than the statute. (3) Texas DOB in the file materially increases linkage accuracy.
- Note the cross-reference discrepancy (§ 18.008 vs. § 18.066) between the Legislature's text and the SOS form; both point to the same offense structure.

### Gaps
- Could not read § 18.066/§ 18.067 in full, the current fee schedule (beyond the $75 deposit), or the full text of form 24-1.
- Whether 2023–2026 legislation changed Chapter 18 was not confirmed; statutes.capitol.texas.gov was blocked for fetch.
- No AG opinion or case interpreting "advertising or promoting commercial products or services" for non-marketing internal use was found.

## Utah

### Takeaway
NOT ALLOWED (likely; text not fully verified). Utah's list carries statutory use/disclosure restrictions, and DOB is private for everyone. SB 153 (2026) rewrote 20A-2-104 effective Apr 6, 2026 and reclassified many previously private records as public. The current text of the use restriction could not be read, so this verdict rests partly on prior versions and NCSL.

### Cited Findings
- **Versioning:** 20A-2-104 ("Voter registration form -- Registered voter lists -- Fees for copies") was effective 5/7/2025 and "Superseded 4/6/2026." The 2025 version defines "qualified person" in subsection (4)(a). — [Utah Code 20A-2-104 (eff. 5/7/2025)](https://le.utah.gov/xcode/Title20A/Chapter2/C20A-2-S104_2025050720250507.pdf)
- **2025 text, birth year:** "(k) A qualified person may not obtain, provide, or use the year of birth of a registered voter, if the year of birth is obtained from the list of registered voters or from a voter registration record…" Qualified persons must sign a document stating their purpose and agreeing to use the data only for listed purposes. — [Utah Code 20A-2-104 (eff. 5/7/2025)](https://le.utah.gov/xcode/Title20A/Chapter2/C20A-2-S104_2025050720250507.pdf)
- **Withheld fields (NCSL):** DL and SSN numbers, email addresses and day of birth are confidential. Months and years of birth are restricted to government officials and employees, political parties and certain other persons under certain circumstances. — [NCSL summary](https://www.ncsl.org/elections-and-campaigns/access-to-and-use-of-voter-registration-lists)
- **2026 SB 153 (Election Amendments):** Records classified private "without requiring a reason" before April 6, 2026 are reclassified public unless the voter files a form with any required proof with the county clerk. Reporting says this applies to more than 300,000 Utahns, with records viewable on request for a fee from May 25, 2026. Public fields include full legal name, voter ID number, residential and mailing address, party, precinct/district and voter status. "At-risk" voters (DV victims, law enforcement, military, threatened public figures, court-order protected) may keep records private. DOB, DL number, state ID number and SSN remain private. The legislative summary says the bill "places restrictions on the use and disclosure of information from the voter registration list." — [SB 153 enrolled](https://le.utah.gov/Session/2026/bills/enrolled/SB0153.pdf); [KUTV](https://kutv.com/news/local/voter-registration-records-for-more-than-300000-utahns-to-go-public-under-new-law); [ABC4](https://www.abc4.com/news/politics/inside-utah-politics/lt-governor-voter-registration-records-private-new-law/); [BillTrack50 SB0153](https://www.billtrack50.com/billdetail/1941442)
- **Competing bill:** SB 194 (2026, "Election Modifications") also amends 20A-2-104, with a listed effective date of 01/01/27. — [SB 194 introduced](https://le.utah.gov/Session/2026/bills/introduced/SB0194.pdf)
- **Withheld category:** Voters may have their records withheld from anyone other than a government entity under Utah Code 63G-2-302 and 20A-2-104(7)–(8). — [vote.utah.gov Voter Privacy](https://vote.utah.gov/?p=8618)
- **Historical:** A 2014 bill (SB 36) proposed restricting use to "political, scholarly, journalistic, or governmental purposes" and described a class B misdemeanor for using the list "for commercial purposes"; enactment of that exact language was not confirmed. — [2014 SB 36 S03](https://le.utah.gov/~2014/bills/sbillint/SB0036S03.pdf)

### Inferences
- The search results consistently show a statutory use restriction plus DOB fully private. On that basis the file (name/address/voter ID/party/history, no DOB) is both of limited linkage value and very likely restricted against commercial use.
- From memory, unverified: earlier Utah law let certain "qualified persons" (including financial institutions and insurers) obtain birth-date data for identity verification. If SB 153 kept such a carve-out, it would be the only possible path for a debt-related use, but it would not cover a general-purpose locate database. Verify before relying on it.

### Gaps
- Could not read the current (eff. 4/6/2026) text of 20A-2-104: the exact use-restriction language, who may obtain the list, fee and penalty are all unconfirmed. le.utah.gov was blocked.
- The interaction with SB 194 (eff. 1/1/2027) is unresolved.

## Washington

### Takeaway
NOT ALLOWED (as a practical/contractual matter); the statutory criminal ban arguably does not reach the use case. The VRDB extract is freely downloadable. But: the SOS requires users to agree to use the data in accordance with the listed laws; RCW 42.56.070(8) bars agencies from giving out lists of individuals "for commercial purposes"; and an AG opinion reads that bar as not limited to direct contact. The felony in RCW 29A.08.740 targets mailing or delivering ads or solicitations.

### Cited Findings
- **Who and how:** Free download from the SOS. The requester supplies a valid email and receives a download link upon approval. "By clicking the button below, I agree to use the data in accordance with the laws listed above." — [SOS: Order the latest statewide list of voters](https://sos.wa.gov/node/199); [sos.wa.gov/node/10458](https://sos.wa.gov/node/10458)
- **Fields (RCW 29A.08.710):** Name, address, political jurisdiction, gender, year of birth, voting record, date of registration and registration number. "No other information from voter registration records or files is available for public inspection or copying." Full DOB, driver's license number and last four of SSN are protected and not in the public database. — [SOS VRDB database fields](https://www.sos.wa.gov/_assets/elections/vrdb-database-fields.pdf); [SOS response to DOJ (Sept. 2025)](https://www.sos.wa.gov/node/29984)
- **Criminal/civil penalty, RCW 29A.08.740(1):** Using registered voter data furnished under RCW 29A.08.720 "for the purpose of mailing or delivering any advertisement or offer" for any property, establishment, organization, product or service, or any solicitation for money, services or anything of value, is a class C felony. It is punishable by up to five years in a state correctional facility or a fine of up to $10,000. The violator is also liable to each recipient of an unwanted solicitation for a "nuisance value of five dollars for each item," with class actions and attorney's fees available. Mailing "for a political purpose" is exempt ("political purpose" = support of or opposition to any candidate or ballot proposition or issue). — [RCW 29A.08.740](https://lawfilesext.leg.wa.gov/Law/RCWPDF/RCW%20%2029A%20TITLE/RCW%20%2029A.%2008%20%20CHAPTER/RCW%20%2029A.%2008%20.740.pdf); [LawServer RCW 29A.08.740](https://www.lawserver.com/law/state/washington/wa-code/washington_code_29a-08-740)
- **Due care, RCW 29A.08.740(2):** Each person furnished data "shall take reasonable precautions designed to assure that the data is not used for" those purposes; failure makes that person jointly and severally liable. — [RCW 29A.08.740](https://lawfilesext.leg.wa.gov/Law/RCWPDF/RCW%20%2029A%20TITLE/RCW%20%2029A.%2008%20%20CHAPTER/RCW%20%2029A.%2008%20.740.pdf)
- **Statewide file, RCW 29A.08.760:** The commercial-use restrictions and penalties for the statewide voter file "shall be the same as provided in RCW 29A.08.720 and 29A.08.740." — [RCW 29A.08.760](https://lawfilesext.leg.wa.gov/Law/RCW/RCW%20%2029A%20TITLE/RCW%20%2029A.%2008%20%20CHAPTER/RCW%20%2029A.%2008%20.760.htm)
- **Political-purposes-only forms:** County election data request forms state the data "shall be used for political purposes only" and may not be used for commercial purposes. WAC also provides that auditor-furnished voter lists may not be used for commercial purposes. — [Lewis County form](https://elections.lewiscountywa.gov/documents/382/Election_Data_Request_Form_Lewis_Fillable_etHadst.pdf); [Lincoln County form](https://www.lincolncountywa.com/DocumentCenter/View/238/Election-Data-Request-PDF)
- **PRA commercial-lists bar:** RCW 42.56.070(8) bars agencies from giving, selling or providing access to lists of individuals requested for commercial purposes unless specifically authorized. SOS public-records requesters sign: "By signing below, I understand I will not use this list of individuals for commercial purposes." — [SOS RCW 42.56.070(8) declaration](https://www.sos.wa.gov/_assets/publicrecords/rcw-42.56.70(8)-commercial-lists.docx)
- **AG interpretation:** A Washington AG opinion (under predecessor RCW 42.17.260(9)) concluded the commercial-lists prohibition "is not limited to situations in which individuals are directly contacted." — [WA AGO, Authority of public agencies to allow inspection and copying of lists of individuals](https://atg.wa.gov/ago-opinions/authority-public-agencies-allow-inspection-and-copying-lists-individuals)

### Inferences
- On the text of RCW 29A.08.740, an internal locate/link database with no mailing, delivery or solicitation is not the felony conduct. But the SOS conditions release on lawful use, and RCW 42.56.070(8) plus the AG's broad reading make "commercial purposes" (contact or not) the governing test. Obtaining the VRDB for a commercial database would conflict with the access terms and likely the PRA, so treat it as NOT ALLOWED.
- The file has birth year only, which limits linkage value.

### Gaps
- Could not read the current full text of RCW 29A.08.720 (the exact "political purposes" sentence) or the VRDB click-through terms verbatim.
- WSR 26-01-021 (a 2026 rulemaking filing surfaced in search) was not reviewed and may touch voter data rules.

## Wyoming

### Takeaway
NOT ALLOWED. W.S. 22-2-113(a) has the Secretary of State furnish registry lists "at a reasonable price" only to enumerated political requesters. The buyer affirms under penalty of perjury that use is "for political purposes only" and "not … for commercial purposes."

### Cited Findings
- **Who:** "The secretary of state shall furnish at a reasonable price registry lists to any" of the listed categories: Wyoming candidates for political office, ballot issue proponents, individuals promoting or opposing a candidate or ballot issue, party committees, and representatives of organizations promoting voter participation. "All lists are for political purposes only and are not available for commercial use." — [Wyoming SOS Voter Product Order Form](https://sos.wyo.gov/Forms/Elections/General/VoterProductOrderForm.pdf); [Albany County WY instructions](https://www.albanycountywy.gov/DocumentCenter/View/6252); [W.S. 22-2-113](https://law.counselstack.com/statute/wy/22-2-113)
- **Affirmation:** "I affirm under penalty of perjury that I will use the above voter registration data for political purposes only and that I will not use it for commercial purposes." (The form was updated October 2023.) — [Wyoming SOS Voter Product Order Form](https://sos.wyo.gov/Forms/Elections/General/VoterProductOrderForm.pdf)
- **Fees:** Statewide file $125, party $50, county $35, legislative district $25. An older EAC table listing $0 conflicts with this and appears outdated. — [Wyoming SOS Voter Product Order Form](https://sos.wyo.gov/Forms/Elections/General/VoterProductOrderForm.pdf); [EAC Availability of State Voter File](https://www.eac.gov/sites/default/files/voters/Available_Voter_File_Information.pdf)
- **Fields:** "Registry list" (W.S. 22-1-102(a)(xxix)) is the list by precinct of names, addresses, party affiliations, unique state-generated ID numbers, absentee status, registration dates and precinct/district numbers. The order form's file includes voter ID, name, residence address, county and precinct. — [Wyoming SOS form](https://sos.wyo.gov/Forms/Elections/General/VoterProductOrderForm.pdf); [WY Legislature 2022 SOS memo on public/confidential election records](https://wyoleg.gov/InterimCommittee/2022/07-202208252-04SOSElectionlawsrelatingtopublicandconfidentialrecords.pdf)

### Inferences
- A private non-political business is not an eligible requester, and the use would contradict a perjury-backed affirmation. Penalty exposure is perjury (from the affirmation) in addition to any election-code penalty.
- DOB or birth year does not appear in the defined fields, so linkage value is low anyway.

### Gaps
- Could not confirm any 2023–2026 amendment to W.S. 22-2-113 or a specific election-code penalty for misuse (beyond perjury on the affirmation).
- Whether DOB or birth year is included was not confirmed by any source.
