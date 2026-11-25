# Voter file access and permitted uses: Midwest (IL, IN, IA, KS, MI, MN, MO, NE, ND, OH, SD, WI)

Use case tested in every entry: a private company obtains the statewide voter file and uses it in an **internal records database to locate people and link them to property and debt records**. There is **no redistribution and no solicitation or mailing**. The purpose is commercial and non-political.

Research date: 2026-11-25. This is legal research for internal planning, not legal advice.

Method note: WebFetch could not reach ncsl.org, eac.gov or ballotpedia.org from this session (DNS blocked). Statute text was pulled directly with curl from official legislature sites wherever they were reachable: revisor.mo.gov, revisor.mn.gov, ksrevisor.gov, legis.iowa.gov, nebraskalegislature.gov, sdlegislature.gov, ndlegis.gov, codes.ohio.gov and legislature.mi.gov. Forms came from the agencies' own sites. Illinois (ilga.gov), Indiana (iga.in.gov) and Wisconsin (docs.legis.wisconsin.gov) statute text could not be fetched because of TLS errors or a JavaScript-only site. For those three states, statute language comes from search-result excerpts of the official pages and from agency forms and guidance. That is flagged in each entry.

---

## Summary verdict table

| State | Who may get the statewide file | Use restriction (core text) | Verdict for internal locate/link use |
|---|---|---|---|
| Illinois | Only SBE-registered political committees and government entities | "bona fide political purposes" only; never "commercial solicitation or other business purposes". **Class 4 felony** | **NOT ALLOWED** |
| Indiana | Statewide: only party state committees and independent-candidate committees. County SVRS copies: depends on each county board's policy | No solicitation; no sale or transfer for non-political purposes. The computerized list is "exclusively for voter registration and election administration" | **NOT ALLOWED statewide.** County-level copies are **ambiguous, at best ALLOWED WITH CONDITIONS** |
| Iowa | Anyone who pays and states a use | "only" for vote requests, political purposes, official purposes or political research; "shall not be used for any commercial purposes". Aggravated misdemeanor | **NOT ALLOWED** |
| Kansas | Anyone (county copies to "any person"; SoS sells the statewide file for $300) | Knowingly receiving the list "with the intent to use such list or information for any commercial purpose". Class C misdemeanor | **NOT ALLOWED** (statute undefined but broad) |
| Michigan | Anyone, via FOIA to the Bureau of Elections | No statutory use restriction found; FOIA exemptions only | **ALLOWED** |
| Minnesota | Registered Minnesota voters only; signed written statement | "purposes unrelated to elections, political activities, or law enforcement" are barred | **NOT ALLOWED** |
| Missouri | Public (SoS or election authorities) for a fee | "shall not be used for commercial purposes", defined to include any use where "the purchaser can reasonably anticipate the receipt of monetary gain". Class B misdemeanor | **NOT ALLOWED** |
| Nebraska | Anyone who swears an oath ($500 a year statewide) | "solely for purposes related to elections, political activities, voter registration, law enforcement, or jury selection"; not "used for commercial purposes". A false oath is a Class IV felony | **NOT ALLOWED** |
| North Dakota | Candidates, political parties and political committees only | "election-related purposes" only. Class A misdemeanor | **NOT ALLOWED** |
| Ohio | Anyone; public record; free statewide download from the SoS | No use restriction in statute; disclosure exemptions only | **ALLOWED** |
| South Dakota | Anyone who pays and signs an acknowledgment | "may not be sold and may not be used for any commercial purpose". Class 1 misdemeanor plus a civil penalty of up to $2,000 per violation | **NOT ALLOWED** |
| Wisconsin | Anyone via Badger Voters ($25 + $5 per 1,000 records, capped at $12,500) | WEC: "Wisconsin law does not place any restrictions on the use of data obtained through this website" | **ALLOWED** |

---

## Illinois

### Takeaway
Illinois limits electronic voter data to political committees registered with the State Board of Elections (SBE) and to government entities. The political committee must swear an affidavit that the data is for "bona fide political purposes" only. Business use is a Class 4 felony. **Verdict: NOT ALLOWED.** A private company is not an eligible requester, and "other business purposes" squarely covers an internal commercial locate database.

### Cited Findings
- **Who may obtain the file.** 10 ILCS 5/4-8 (and its parallels 5-7 and 6-35) limits electronic voter records to "a State or local political committee" and "a governmental entity for a governmental purpose". — [ILGA 10 ILCS 5/4-8](https://ilga.gov/documents/legislation/ilcs/documents/001000050K4-8.htm) (statute excerpt via search; direct fetch failed on TLS)
- Counties restate the rule: only "units of government or political committees, who are registered with the State Board of Elections, may purchase voter registration lists and associated voter history in electronic form for bona fide political purposes". — [Lake County IL](https://www.lakecountyil.gov/314/List-of-Registered-Voters-Voting-History); [Will County Clerk](https://www.willcountyclerk.gov/voter-data/)
- **Affidavit.** The statutory text says "The individual representing a political committee requesting copies of such tapes shall make a sworn affidavit that the information shall be used only for bona fide political purposes". — [10 ILCS 5/4-8](https://ilga.gov/documents/legislation/ilcs/documents/001000050K4-8.htm)
- The SBE's suggested Form R-6 affidavit (Revised July 1999) reads: "the above information requested shall be used only for bona fide political purposes, including by or for any candidate for office or incumbent office holders and will not be used under any circumstances by any political committee or individual for purposes of commercial solicitation or other business purposes". The applicant must identify the requester as a "political committee, registered pursuant to the Illinois Campaign Financing Act". — [SBE Form R-6](https://www.elections.il.gov/agencyforms/LIST%20OF%20FORMS%20WORD/R-6.doc)
- **Operative restriction.** "Such tapes, discs or other electronic data shall not be used under any circumstances by any political committee or individuals for purposes of commercial solicitation or other business purposes." — [10 ILCS 5/4-8](https://ilga.gov/documents/legislation/ilcs/documents/001000050K4-8.htm)
- **Penalty.** "Any person who violates this provision shall be guilty of a Class 4 felony." — [10 ILCS 5/4-8](https://ilga.gov/documents/legislation/ilcs/documents/001000050K4-8.htm)
- **Enforcement (2024).** At the SBE's request, the Attorney General sought a TRO against Local Government Information Services (LGIS), Dan Proft's publisher, for publishing voter data. The AG argued that LGIS "is not a political committee and could not have legally obtained the voter information" and cited violations of sections 4-8, 5-7 and 6-35. The AG sought removal of "voters' birthdates and street numbers", and an agreed order followed in May 2024. — [Capitol Fax, 2024-05-08](https://capitolfax.com/2024/05/08/ag-raoul-asks-court-to-force-timponeproft-papers-to-remove-personal-voter-information-from-its-websites); [Peoria Journal Star via PressReader, 2024-05-14](https://www.pressreader.com/usa/journal-star-peoria/20240514/281487871447589)
- **Related 2026 matter.** In August 2026 a federal judge denied DOJ's demand for unredacted Illinois voter rolls, which shows that the state actively protects the file. — [WTTW, 2026-08-03](https://news.wttw.com/2026/08/03/federal-judge-denies-trump-administration-access-unredacted-illinois-voter-data)

### Inferences
- The LGIS case shows that the file distributed to political committees contains birthdates and full street addresses. Exact field lists were not confirmed.
- "Other business purposes" is broader than "solicitation", so no-mailing and no-redistribution terms do not help. A private company cannot obtain the file lawfully in the first place.

### Gaps
- I could not fetch the current consolidated text of 10 ILCS 5/4-8 or 1A-25 (statewide list provisions) because ilga.gov TLS failed. I found no 2023–2026 amendment to the access rules.
- The current SBE fee and field layout were not confirmed.

---

## Indiana

### Takeaway
The statewide compilation from the Indiana Election Division goes only to major party state committees, qualifying minor party state organizations and independent-candidate committees (IC 3-7-26.4-6). A private company is not eligible. **Verdict: NOT ALLOWED statewide.**

Counties may adopt a policy of releasing county SVRS data (IC 3-7-27-6(c)). The requester then signs State Form VRG-24, agreeing not to use the data to solicit and not to sell or transfer it for non-political purposes. Our use breaches neither literal condition. However, HAVA list statutes say the computerized list is used "exclusively for voter registration and election administration". **County-level: ambiguous, at best ALLOWED WITH CONDITIONS** (no solicitation, no transfer), and it depends county by county on board policy.

### Cited Findings
- **Statewide eligibility.** "the election division shall provide a complete compilation of the voter registration information contained in the computerized list" to "(1) The state committee of a major political party. (2) The state organization of a bona fide political party that is not a major political party if the party has at least two (2) candidates on the ballot in the next election. (3) The committee of an independent candidate for federal or state office if the candidate is on the ballot in the next general election." — [IC 3-7-26.4-6 (FindLaw excerpt via search)](https://codes.findlaw.com/in/title-3-elections/in-code-sect-3-7-26-4-6.html)
- **Disclosure bar.** IC 3-7-26.4-2 prohibits the Election Division from providing "any part of the compilation of the voter registration information contained in the computerized list" except as the statute allows. A 2025 trial court upheld this against a media plaintiff (The Indiana Citizen). — [PAC advisory 24-FC-81](https://www.in.gov/pac/files/advisory/24-FC-81.pdf); [Indiana Citizen](https://indianacitizen.org/no-public-disclosure-trial-court-allows-state-to-keep-private-the-names-of-nearly-600k-indiana-voters-sent-to-uscis/)
- **Exclusive-use clause.** "except as expressly provided by statute, the computerized list and each of its components must be used exclusively for voter registration and election administration and for no other purpose." — [Justia IC 3-7-26.3/30 (search excerpt)](https://law.justia.com/codes/indiana/2012/title3/article7/chapter30/)
- **Form restriction (IC 3-7-26.4-10).** The form must state that the recipient "may not: (1) use the compilation to solicit for the sale of merchandise, goods, services, or subscriptions", nor sell, loan, give away or deliver it to others "for a purpose other than political activities or political fundraising activities". — [IC 3-7-26.4-10 (2025, Justia)](https://law.justia.com/codes/indiana/title-3/article-7/chapter-26-4/section-3-7-26-4-10/)
- **Fee and the restricted/unrestricted distinction (2026 Election Division guidebook).**
  - "Certain persons (state major political party committees, for example) may purchase an annual subscription for the unrestricted voter registration file from the Indiana Election Division".
  - "All other persons may obtain a restricted copy of the list, after certain information such as date of birth and gender, has been redacted by the Division."
  - All persons pay "$5,000 per calendar year … for the annual subscription to the unrestricted voter registration file".
  - Reports may not include "date of birth, gender, telephone number, voting history, or registration date" unless the requester holds a subscription.
  - Sources cited there: IC 3-7-26.4-4 and 26.4-8.
  - Source: [2026 Indiana Voter Registration Guidebook (rev. Apr 2026), p. ~93](https://www.in.gov/sos/elections/files/2026-Voter-Registration-Guidebook-Revised-Apr-2026.FINAL.pdf)
- **County route.** "A county voter registration office shall … act in accordance with the non-discriminatory uniform policy adopted by the county election board … [to] either permit a person to duplicate or obtain a copy … or not" (IC 3-7-27-6(c)). A requester "must submit the request on State Form VRG-24. This form requires the requesting person to agree that the information will not be used to solicit merchandise, goods, services or subscriptions. The person must also agree not to sell, loan, give away or otherwise deliver the information to any other person for a purpose other than political activities or political fundraising activities" (IC 5-14-3-8(d)). — [2026 Indiana Voter Registration Guidebook](https://www.in.gov/sos/elections/files/2026-Voter-Registration-Guidebook-Revised-Apr-2026.FINAL.pdf)
- **Address Confidentiality Program.** Records of Attorney General ACP participants are withheld. — [same guidebook](https://www.in.gov/sos/elections/files/2026-Voter-Registration-Guidebook-Revised-Apr-2026.FINAL.pdf)
- **Pending change (2025).** Introduced HB 1680 (2025) would have added IC 3-7-26.4-14, barring commercial use of the computerized list. "a person who intentionally uses the computerized list for commercial purposes commits a Class A misdemeanor." — [HB 1680 introduced](https://iga.in.gov/pdf-documents/124/2025/house/bills/HB1680/HB1680.01.INTR.pdf)
- HEA 1679 (P.L. 240-2025) did pass and "prescribes fees to be charged by the election division". — [2025 Indiana Election Legislation Summary](https://secure.in.gov/sboa/files/Nussmeyer_2025-Indiana-Election-Legislation-Summary.FINAL.pdf)

### Inferences
- The guidebook says "All other persons may obtain a restricted copy" of the list, which appears to conflict with IC 3-7-26.4-2/-6. It may refer to redacted reports under IC 3-7-26.4-8 or 3-7-26.3-29. Treat it as an unresolved conflict.
- HB 1680's commercial-use ban does not appear in the April 2026 guidebook, which suggests it was not enacted. This is unconfirmed.
- At the county level, the VRG-24 conditions (no solicitation, no transfer) fit our use literally. Still, the "exclusively for voter registration and election administration" clause in IC 3-7-26.3 creates real risk, and many counties may simply refuse.

### Gaps
- I could not fetch the iga.in.gov statute text (JavaScript-only site). The exact current text of IC 3-7-26.4-6, -8 and -12, and the penalty for violating the -10 form restrictions, are unverified.
- I did not confirm whether the $5,000 fee was changed by HEA 1679.

---

## Iowa

### Takeaway
Anyone may order a list from the Secretary of State by stating its intended use, but the statute lists exclusive permitted uses and expressly bars "any commercial purposes". Misuse is an aggravated misdemeanor. **Verdict: NOT ALLOWED.**

### Cited Findings
- **Operative statute (Iowa Code 2026 §48A.39).** "Information about individual registrants obtained from voter registration records shall be used only to request the registrant's vote at an election, or for another genuine political purpose, or for a bona fide official purpose by an elected official, or for bona fide political research, but shall not be used for any commercial purposes." — [Iowa Code §48A.39 (official PDF, 2026 code)](https://www.legis.iowa.gov/docs/code/48A.39.pdf)
- **Penalty (Iowa Code §39A.3(1)(c)).** Election misconduct in the second degree includes when a person "Uses voter registration information, including resale or redistribution of the voter registration list without written permission of the state registrar, for purposes other than those permitted by section 48A.39". §39A.3(2): "Election misconduct in the second degree is an aggravated misdemeanor." — [Iowa Code §39A.3](https://www.legis.iowa.gov/docs/code/39A.3.pdf)
- **Process.** Requests go on the SoS "Specifications and Order Form for Voter List" (Revised 02/2024), which requires the intended use and lists the same four permitted uses. Voter profiles cost $5.00 each, and preparation can take up to 14 days. — [Iowa SoS voter list order form](https://sos.iowa.gov/elections/pdf/voterlistrequest.pdf) (summary via search; direct fetch returned HTML); [Iowa Admin. Code ch. 821 analysis](https://www.legis.iowa.gov/docs/iac/agency/06-19-2019.821.pdf)
- Recent SoS rulemaking (ARC 6772C) restates that misuse is an aggravated misdemeanor under §39A.3(1)(c). — [ARC 6772C](https://rules.iowa.gov/Notice/Details/6772C)

### Inferences
- "Used only" plus an express "commercial purposes" bar leaves no room for an internal commercial database, even without redistribution.

### Gaps
- The full statewide list price and field list were not confirmed because the form could not be fetched directly.

---

## Kansas

### Takeaway
Anyone can buy the statewide file from the Secretary of State ($300). However, K.S.A. 25-2320a makes it a crime to knowingly receive voter list information "with the intent to use such list or information for any commercial purpose". The only safe harbor is "solely for political campaign or election purposes". **Verdict: NOT ALLOWED.** "Commercial purpose" is undefined in the statute. The SoS form glosses it as including "using public records to sell property or services", but the statutory text is "any commercial purpose", and a for-profit locate/link database is commercial in the ordinary sense.

### Cited Findings
- **K.S.A. 25-2320a.** "Use of voter registration lists for commercial purposes is knowingly selling, giving or receiving the information on or derived from voter registration lists with the intent to use such list or information for any commercial purpose. Use of voter registration lists for commercial purposes is a class C misdemeanor. For purposes of this section, compiling, using, giving, receiving, selling or purchasing the information on or derived from voter registration lists, solely for political campaign or election purposes, shall not constitute a commercial use of voter registration lists." History: L. 1977; L. 1994. Governmental Ethics Commission Op. 2002-11 says interpreting the section is outside its jurisdiction. — [ksrevisor.gov K.S.A. 25-2320a](https://ksrevisor.gov/statutes/chapters/ch25/025_023_0020a.html)
- **Access (K.S.A. 25-2320(a)).** "Any person may make a written request for a copy of the registration books." Under (b), copies are released only after the "social security number, driver's license number, nondriver's identification card number or any part thereof" is removed. — [ksrevisor.gov K.S.A. 25-2320](https://ksrevisor.gov/statutes/chapters/ch25/025_023_0020.html)
- **SoS form CVR (Rev. 3/2/26).**
  - Fee: "The entire state ($300/CD-ROM)"; districts cost $100 each.
  - Notice: "K.S.A. 25-2320a prohibits using information derived from voter registration records for commercial purposes. This includes using public records to sell property or services. Persons are also prohibited from obtaining public records with the intention of making the records available to a third party for such purposes. Use of voter registration lists for commercial purposes is a crime."
  - The requester signs to indicate understanding and certifies a right of access.
  - Source: [Kansas SoS Voter Registration Data Request (CVR)](https://www.kssos.org/forms/elections/CVR.pdf)
- County offices (e.g., Johnson and Leavenworth) use the same notice. — [Johnson County Election Office](https://www.jocoelection.org/voting-election-info/information-requests); [Leavenworth County form](https://files.leavenworthcounty.gov/Department/Clerk/Election/Document%20Center/Voter%20Information%20Request.pdf)

### Inferences
- The form's examples (selling property or services, giving records to third parties) track the Kansas Open Records Act's anti-solicitation provisions. Our use involves neither. But 25-2320a itself says "any commercial purpose", and the only exemption is political/election use. A court would likely read it to cover a for-profit internal database, so this is high risk.

### Gaps
- I found no AG opinion or case defining "commercial purpose" under 25-2320a.
- The statewide file's field list (e.g., whether DOB is included) was not confirmed.

---

## Michigan

### Takeaway
The Qualified Voter File (QVF) is available to any requester under FOIA from the Bureau of Elections. Michigan Election Law exempts certain fields from disclosure, but I found no statutory limit on how a recipient may use the data. **Verdict: ALLOWED.** Use the standard QVF request form; no use declaration is required on the form.

### Cited Findings
- **Request form (Rev. 03/26).** Requests go by email to MDOS-FOIA@Michigan.gov or by mail to the Bureau of Elections. Data comes as fixed-length ASCII or CSV on an encrypted flash drive, by FTP or by pickup. "Each list will include complete name, residential address, mailing address (if available), year of birth, registration date, voter status, voter ID and voter history (when available and requested)." The form includes no purpose or use certification; it collects only requester contact details and a signature. — [MDOS QVF Data Request Form](https://www.michigan.gov/-/media/Project/Websites/sos/02lehman/FOIA_FORM.pdf)
- **FOIA-exempt fields listed on the form.** The record that a person declined registration; the receiving office; "driver's license or state personal identification card number"; "month and day of birth"; "telephone number"; "email address"; digitized signature; "last 4 digits of a registered voter's social security number". — [MDOS QVF Data Request Form](https://www.michigan.gov/-/media/Project/Websites/sos/02lehman/FOIA_FORM.pdf)
- **Statute (MCL 168.509gg).**
  - Exempts the declination record, receiving office, DL/ID number, "month and day of birth", "telephone number provided by a registered elector" and digitized signature.
  - The last 4 SSN digits "must not be used or released for any other purpose".
  - Pre-registrant records stay confidential until age 17½.
  - Last amended by 2023 PA 258, effective Feb. 13, 2024.
  - The section contains no restriction on recipients' use.
  - Source: [MCL 168.509gg](https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-168-509gg)
- **Price.** The EAC chart lists Michigan as "open" at $23. This is secondary and not verified on an MDOS page. — [EAC Available Voter File Information](https://www.eac.gov/sites/default/files/voters/Available_Voter_File_Information.pdf) (via search excerpt)

### Inferences
- With no use restriction in the Election Law and FOIA access open to "any person", internal commercial use with no redistribution appears lawful. Email is withheld per the MDOS form, although 509gg's enumerated list names phone but not email. That suggests a separate basis, possibly a newer amendment.

### Gaps
- I did not exhaustively search all of MCL ch. 168 for a use restriction. I found none, and no secondary source reported one. The statewide fee was not verified on MDOS's own page. I did not check how Address Confidentiality Program participants are handled in QVF extracts.

---

## Minnesota

### Takeaway
Only registered Minnesota voters may obtain the public information list. The requester must state in writing that the data will not be used "for purposes unrelated to elections, political activities, or law enforcement". 2023–2025 amendments added bans on internet publication and on sale or transfer. **Verdict: NOT ALLOWED.**

### Cited Findings
- **Contents (Minn. Stat. 201.091 subd. 4(a)).** The list "must contain the name, address, year of birth, and voting history of each registered voter"; "The telephone number must be included on the list if provided by the voter"; it excludes presidential-primary party choice. — [Minn. Stat. 201.091 (Revisor, current)](https://www.revisor.mn.gov/statutes/cite/201.091)
- **Use restriction (subd. 4(b)).** "No individual who inspects the public information list or who acquires a list of registered voters prepared from the public information list may use any information contained in the list for purposes unrelated to elections, political activities, or law enforcement." — [Minn. Stat. 201.091](https://www.revisor.mn.gov/statutes/cite/201.091)
- **Written statement (subd. 4(c)).** The individual "shall provide identification … and shall state in writing that any information obtained from the list will not be used for purposes unrelated to elections, political activities, or law enforcement." — [Minn. Stat. 201.091](https://www.revisor.mn.gov/statutes/cite/201.091)
- **Safety withholding (subd. 4(d)).** A voter's name is withheld when the voter signs a statement that withholding is required for the safety of the voter or the voter's family. — [Minn. Stat. 201.091](https://www.revisor.mn.gov/statutes/cite/201.091)
- **Sale and publication bar (subd. 4(e)).** A recipient must not "publish any of the information from the list on the Internet" or "sell, loan, provide access to, or otherwise surrender any information obtained from the list to any person or entity". There is a narrow exception for an organization's volunteers or employees doing election, political or law-enforcement work, and a separate allowance for aggregated databases "used exclusively for purposes related to elections or political activities". The subd. 4(e) prohibitions "do not apply if the subject of the information provides express written permission". — [Minn. Stat. 201.091](https://www.revisor.mn.gov/statutes/cite/201.091)
- **Registered voters only (subd. 5).** Copies go "to any voter registered in Minnesota … accompanied by payment of the cost of reproduction". — [Minn. Stat. 201.091](https://www.revisor.mn.gov/statutes/cite/201.091)
- **Amendment history.** The section history includes 2023 c 34 art 1 s 8; 2023 c 62 art 4 s 17; 2024 c 112 art 2 s 8; and 2025 c 39 art 8 s 12, 13. — [Minn. Stat. 201.091](https://www.revisor.mn.gov/statutes/cite/201.091)
- **SoS process and fees.** "This information is only available to registered Minnesota voters, and may only be used for purposes related to elections, political activities, or law enforcement." "Reports covering the whole state are $46. Reports covering any area within the state are $30." Payment is by check, money order or cash; no credit cards. Delivery is an encrypted email link active for 7 days. The form warns: "Use of the list of registered voters for purposes unrelated to elections, political activities or law enforcement is a violation of Minnesota law." — [MN SoS Registered Voter List Requests](https://www.sos.mn.gov/election-administration-campaigns/data-maps/registered-voter-list-requests/); [MN SoS Registered Voter List Request Form](https://www.sos.mn.gov/media/2641/registered-voter-list-request-form.pdf)

### Inferences
- A company cannot be the requester; the requester must be a registered Minnesota voter. Even with a voter as nominal requester, a locate/link database is "unrelated to elections, political activities, or law enforcement". The subd. 4(e) consent exception does not lift the subd. 4(b) purpose limit.
- 201.091 states no specific penalty. Minnesota's default rule (Minn. Stat. 645.241) makes violation of a statute with no stated penalty a misdemeanor. This was not verified in this session.

### Gaps
- The specific penalty provision was not confirmed. I found no AG opinion on the meaning of "political activities".

---

## Missouri

### Takeaway
Voter lists (names, year of birth, addresses, districts and party) are sold to the public. However, RSMo 115.158.6 bars commercial use and defines "commercial purposes" to include any use from which "the purchaser can reasonably anticipate the receipt of monetary gain from the direct or indirect use of the public record". Violation is a class B misdemeanor. **Verdict: NOT ALLOWED.** The definition squarely captures an internal for-profit locate/link database even without resale or solicitation.

### Cited Findings
- **Operative text (RSMo 115.158, effective 28 Aug 2003).** "Any information contained in any state or local voter registration system, limited to the master voter registration list or any other list generated from the information, subject to chapter 610, shall not be used for commercial purposes; provided, however, that the information may be used for elections, for candidates, or for ballot measures, furnished at a reasonable fee. Violation of this section shall be a class B misdemeanor." — [RSMo 115.158 (Revisor)](https://revisor.mo.gov/main/OneSection.aspx?section=115.158)
- **Definition (same section).** "'commercial purposes' means the use of a public record for the purpose of sale or resale or for the purpose of producing a document containing all or part of the copy, printout, or photograph for sale or the obtaining of names and addresses from public records for the purpose of solicitation or the sale of names and addresses to another for the purpose of solicitation or for any purpose in which the purchaser can reasonably anticipate the receipt of monetary gain from the direct or indirect use of the public record." — [RSMo 115.158](https://revisor.mo.gov/main/OneSection.aspx?section=115.158)
- **Fields (RSMo 115.157.1).** The election authority or SoS "shall make available electronic media or printouts showing only unique voter identification numbers, voters' names, year of birth, addresses, townships or wards, and precincts". Required separate fields include voter ID, name parts, street address parts, city/state/zip, township/ward/precinct, senatorial, representative and congressional districts, and "Political party affiliation". §115.157.3 (voted-in-election lists) adds that the data "shall not be used for commercial purposes". Fees are set under ch. 610. — [RSMo 115.157](https://revisor.mo.gov/main/OneSection.aspx?section=115.157)
- **Local practice.** A county MCVR request form (Oct 2025) quotes §115.158, requires a no-commercial-use promise and lists a $15 fee (county rate). — [McDonald County MCVR request](https://mcdonaldcountymo.gov/wp-content/uploads/2025/10/REQUEST-FOR-VOTER-REGISTRATION-FROM-MCVR.pdf)
- **Pending bills.** SB 280 (2025) and SB 983 (2026) proposed rewriting 115.158. Their enactment was not confirmed. The Revisor still shows the 2003 version as current (accessed 2026-11-25). — [SB 280 SCS](https://www.senate.mo.gov/25info/pdf-bill/SCSfromResearch/SB280.pdf); [SB 983](https://www.senate.mo.gov/26info/pdf-bill/intro/SB983.pdf)

### Inferences
- The "reasonably anticipate … monetary gain from the direct or indirect use" prong is the broadest commercial definition in this region, and it covers internal business use.

### Gaps
- The statewide SoS fee was not confirmed. I found no case law applying the definition.

---

## Nebraska

### Takeaway
Anyone may buy the statewide file ($500 a year from the Secretary of State) but must swear an oath to use it "only for the purposes prescribed in section 32-330". Those purposes are elections, political activities, voter registration, law enforcement and jury selection, and the list may not be "used for commercial purposes". The oath is made under penalty of election falsification, a Class IV felony. **Verdict: NOT ALLOWED.**

### Cited Findings
- **Neb. Rev. Stat. 32-330(2).** "Lists shall be used solely for purposes related to elections, political activities, voter registration, law enforcement, or jury selection. Lists shall not be posted, displayed, or used for commercial purposes or made accessible on the Internet." The price may not exceed 3 cents per name. — [Neb. Rev. Stat. 32-330 (Legislature)](https://nebraskalegislature.gov/laws/statutes.php?statute=32-330&print=true)
- **Fields (32-330(3)(b)).** The list contains "no more than": name; residential address; mailing address; telephone number; registration status; voter ID number; "birth year"; registration date; precinct; polling site; party affiliation; political subdivisions; and voter history. Under (3)(a), information designated confidential under 32-331 or "marked private" on the application is withheld. Under (1), the digital signature is never included. — [32-330](https://nebraskalegislature.gov/laws/statutes.php?statute=32-330&print=true)
- **Requester disclosures and oath (32-330(4)).** The requester provides name, address, phone, email, committee or organization name, and "the reason for requesting the list". The oath reads: "I will use the list … only for the purposes prescribed in section 32-330 and for no other purpose, that I will not permit the use or copying of such list for unauthorized purposes, and that I will not post, display, or make such list accessible on the Internet. … The penalty for election falsification is a Class IV felony." — [32-330](https://nebraskalegislature.gov/laws/statutes.php?statute=32-330&print=true)
- **Breach duty (32-330(9)).** Recipients must disclose security breaches to the SoS "without delay". — [32-330](https://nebraskalegislature.gov/laws/statutes.php?statute=32-330&print=true)
- **Amendment history.** The section was last amended by Laws 2024, LB287 §17; earlier by 2021 LB285 and 2022 LB843. — [32-330](https://nebraskalegislature.gov/laws/statutes.php?statute=32-330&print=true)
- **SoS process.** Requesters complete a Public Service Request Form plus a voter file affidavit (revised June 2022). The fee is $500, and the office's "practice [is] to request a new voter file affidavit and fee annually". — [NE SoS Voter File Requests](https://sos.nebraska.gov/elections/voter-file-requests); [NE voter file affidavit](https://sos.nebraska.gov/sites/default/files/doc/elections/voter-file-affidavit.pdf)

### Gaps
- I found no AG opinion on "political activities". I did not confirm whether the 2024 LB287 amendment changed the substantive use language.

---

## North Dakota

### Takeaway
North Dakota has no voter registration. The Secretary of State keeps a **central voter file** (NDCC ch. 16.1-02), built from driver's license and ID records and pollbook data and used to run elections. Lists from it go only to candidates, political parties and political committees for "election-related purposes", and the rest of the file is an exempt record. **Verdict: NOT ALLOWED.** A private company is not an eligible recipient, and the purpose limit excludes commercial use.

### Cited Findings
- **Contents (NDCC 16.1-02-12).** The central voter file contains:
  1. legal name
  2. residential address
  3. mailing address
  4. unique identifier
  5. eligibility status
  6. county and districts
  7. "four years of an individual's voting history"
  8. "Date of birth"
  9. DL/nondriver ID number or tribal ID identifier
  10. other information deemed necessary by the SoS
  - Source: [NDCC ch. 16.1-02 (official PDF)](https://ndlegis.gov/cencode/t16-1c02.pdf)
- **Access (NDCC 16.1-02-15).** "a voter list or a report generated from the central voter file may be made available to a candidate, political party, or a political committee for election-related purposes. Any information obtained … may not be sold or distributed for a purpose that is not election-related. Except for information identified in the central voter file under subsections 1, 2, 3, 4, 5, 6, 7, and 10 of section 16.1-02-12 … information in the central voter file is an exempt record. An individual's record that is designated as 'secured active' is an exempt record and is not available to any candidate, political party, or political committee for any purpose." — [NDCC ch. 16.1-02](https://ndlegis.gov/cencode/t16-1c02.pdf)
- **Fields released.** Recipients get fields 1–7 and 10. DOB (field 8) and DL/ID number (field 9) are withheld. — [NDCC 16.1-02-15](https://ndlegis.gov/cencode/t16-1c02.pdf); consistent with [NCSL summary (via search)](https://www.ncsl.org/elections-and-campaigns/access-to-and-use-of-voter-registration-lists)
- **Penalty (NDCC 16.1-02-16(3)).** "An individual who intentionally violates any provision of this chapter is guilty of a class A misdemeanor, unless a different penalty is specifically provided by law." — [NDCC ch. 16.1-02](https://ndlegis.gov/cencode/t16-1c02.pdf)
- **Pending change.** 2025 bill draft 25.0733.01000 would amend 16.1-02-15. Its enactment was not confirmed, and the official chapter PDF fetched 2026-11-25 shows the text quoted above. — [ND Legislature 25.0733.01000](https://ndlegis.gov/assembly/69-2025/regular/documents/25-0733-01000.pdf)

### Gaps
- I did not confirm what the 2025 bill would change or whether it passed. The chapter PDF reflects the current code.

---

## Ohio

### Takeaway
The statewide voter registration database is a public record under ORC 149.43 (ORC 3503.13(A)(1)). The Secretary of State publishes a free statewide download. No Ohio statute restricts how a recipient may use the data. **Verdict: ALLOWED.** A 2026 amendment (SB 293, effective Mar. 20, 2026) codified that SSN, DL/ID number, **telephone and email**, confidential (ACP) records, redacted public-service-worker addresses and proof of citizenship are not disclosed.

### Cited Findings
- **Public record status (ORC 3503.13(A)(1), effective March 20, 2026, SB 293, 136th GA).** "voter registration forms submitted by applicants and the statewide voter registration database established under section 3503.15 of the Revised Code are public records subject to disclosure under section 149.43 of the Revised Code." — [ORC 3503.13](https://codes.ohio.gov/ohio-revised-code/section-3503.13)
- **Not disclosed (ORC 3503.13(A)(2)).**
  - "(a) An elector's full or partial social security number, driver's license or state identification card number, telephone number, or electronic mail address"
  - "(b) A confidential voter registration record, as described in section 111.44" (Safe at Home ACP)
  - "(c) The address of a designated public service worker" who has submitted a redaction request
  - "(d) An elector's proof of citizenship"
  - "(e) Any other information that is prohibited from being disclosed by state or federal law"
  - Source: [ORC 3503.13](https://codes.ohio.gov/ohio-revised-code/section-3503.13)
- **Database contents (ORC 3503.15(C), effective Oct. 3, 2023, HB 33).** Name; "birth date"; residence address; precinct; DL/ID number; last-4 SSN; telephone; email; registration date; and voting history. — [ORC 3503.15](https://codes.ohio.gov/ohio-revised-code/section-3503.15)
- **Free download.** MIT Election Lab says Ohio is one of the few states that makes current versions of its voter registration database available for download through the Voter Files Download page. A 2023 Demos report says the complete file is updated weekly and "can be immediately downloaded in an electronic format for free". It includes voter ID, status and voting history, but not race or status reason code. — [MIT Election Lab, Ohio](https://electionlab.mit.edu/landscapes/ohio); [Demos 2023 excerpt](https://www.demos.org/sites/default/files/2023-11/Ohio%20-%20Excerpt%20-%20Protecting%20Voter%20Registration_1.pdf)
- **DOB in the download.** A third-party tutorial loading Ohio SWVF county files shows a DATE_OF_BIRTH column (106 columns, .txt.gz). This is secondary and unverified against the official layout. — [r4campaigns "State Voter Files"](https://r4campaigns.netlify.com/state-voter-files)
- **Download page status.** The SoS Voter Files Download page (ohiosos.gov/elections/voters/voter-files-download/) returned a "Website Maintenance" page when fetched on 2026-11-25. — [Ohio SoS Voter Files Download](https://www.ohiosos.gov/elections/voters/voter-files-download/)

### Inferences
- Because the database is a public record with enumerated exemptions and no use clause, internal commercial use is lawful. Ohio public-records law generally does not let agencies ask for or condition release on purpose.
- Phone and email are excluded from the public file. DOB is not on the exemption list and appears in the SWVF in practice, which makes Ohio the best dataset for identity matching in this region.

### Gaps
- I could not view the official field layout because the SoS page was under maintenance. I did not confirm whether SB 293 changed the download's fields, for example by removing DOB.

---

## South Dakota

### Takeaway
Anyone may buy the statewide file from the SoS ($225 electronic) but must sign an acknowledgment of SDCL 12-4-41. That section says voter information "may not be sold and may not be used for any commercial purpose". 2025 and 2026 amendments dropped the older "only for election purposes" wording but kept the commercial-use ban. **Verdict: NOT ALLOWED.**

### Cited Findings
- **Current SDCL 12-4-41.**
  - "Any information obtained from the statewide voter registration file or any county voter registration file may not be sold and may not be used for any commercial purpose. Except as provided in §§ 12-4-37 and 12-4-37.1, information obtained from the statewide voter registration file may not be placed for unrestricted access on the internet."
  - "'commercial purpose' does not include campaign or political polling activities."
  - "Any violation of this section is a Class 1 misdemeanor. In addition to any criminal sanctions, the court may impose a civil penalty not to exceed two thousand dollars for each violation."
  - Source: SL 2001 ch 66; 2002 ch 72; 2017 ch 68; **2025 ch 60 §5; 2026 ch 66 §3**.
  - Source: [SDCL 12-4-41 (SD Legislature)](https://sdlegislature.gov/api/Statutes/12-4-41.html)
- **Prior text (2020).** The information "may be used or sold only for election purposes, may not be used for any commercial purpose". — [Justia SDCL 12-4-41 (2020)](https://law.justia.com/codes/south-dakota/2020/title-12/chapter-04/section-12-4-41/)
- **The 2025–2026 bills.** HB 1062 (2025) and SB 214 (2026, ch. 66) amended the section. — [2025 HB 1062](https://sdlegislature.gov/Session/Bill/25746/284452); [2026 SB 214 session law](https://mylrc.sdlegislature.gov/api/Documents/SessionLaw/306441.pdf?Year=2026)
- **SoS form (last updated 12.03.2025).**
  - Statewide electronic file: $225 (ARSD 5:04:06:07). Statewide paper: $1,000. Annual update file: $50.
  - The form asks the buyer to "list the name of candidate, ballot question or party committee utilizing the voter registration file".
  - The requester signs: "I understand that the voter registration data obtained from the statewide voter registration database may not be used or sold for any commercial purpose and may not be placed for unrestricted access on the Internet."
  - Source: [SD SoS Voter File Data Request Form](https://www.sdsos.gov/elections-voting/upcoming-elections/assets/20251203VoterFileRequestFormFILLABLE.pdf)
- **Fields (SDCL 12-4-9, quoted on form).** The master file holds voter registration card information, last election voted, update date and absentee application details. "An individual's social security number, driver license number, South Dakota nondriver identification number, or month and day of birth is not open to public inspection." — [SD SoS form](https://www.sdsos.gov/elections-voting/upcoming-elections/assets/20251203VoterFileRequestFormFILLABLE.pdf)

### Inferences
- Removing "only for election purposes" in 2025/2026 widened permitted non-commercial uses, such as research or journalism. "Any commercial purpose" still covers a for-profit internal database. The form's candidate/committee field suggests the SoS expects political buyers.

### Gaps
- I did not determine the exact effective date of the 2026 amendment or whether the SoS form has been updated since. The form predates the 2026 change.

---

## Wisconsin

### Takeaway
The Wisconsin Elections Commission (WEC) sells the statewide WisVote list to anyone through Badger Voters. WEC states that "Wisconsin law does not place any restrictions on the use of data obtained through this website." DOB, DL numbers, SSNs and confidential voters are withheld. **Verdict: ALLOWED.**

### Cited Findings
- **Use.** "Wisconsin law does not place any restrictions on the use of data obtained through this website." — [Badger Voters FAQ](https://badgervoters.wi.gov/faq)
- Wisconsin Watch (Aug 2026), citing Legislative Council guidance, reports that state laws do not limit how purchased data can be used, and buyers may use it "to contact individuals for any purpose". — [Wisconsin Watch, Aug 2026](https://wisconsinwatch.org/2026/08/wisconsin-voter-roll-list-data-buy-election-commission-trump-names-addresses-voting-history/)
- **Fields.** A voter record "includes a voter's name, address, and any contact information they provided with their registration; as well as the electoral districts that voter is in, what elections they voted in, and whether they voted at the polls or absentee back to 2006." — [Badger Voters FAQ](https://badgervoters.wi.gov/faq)
- **Withheld.** "The WEC will never provide date of birth information (including age or age range), driver license numbers or social security numbers." Wis. Stat. §6.36(1)(b) also bars release of a confidential voter's name or address and any indication of a required voting accommodation. — [Badger Voters FAQ](https://badgervoters.wi.gov/faq); [Wisconsin Watch](https://wisconsinwatch.org/2026/08/wisconsin-voter-roll-list-data-buy-election-commission-trump-names-addresses-voting-history/)
- **Fees.** "Voter lists and custom requests have a base fee of $25. Additionally, there is a fee of $5 for every thousand records returned … The fee is capped at $12,500." Custom requests cost an extra $75 per half hour. No data is free except to election officials, law enforcement, other states' agencies and ERIC. Since Dec. 22, 2025, accounts require My Wisconsin ID with MFA. — [Badger Voters FAQ](https://badgervoters.wi.gov/faq)
- **Litigation.** A conservative firm sued WEC's administrator over the fee and the omission of DOB under the NVRA. Wisconsin is NVRA-exempt. — [WPR](https://www.wpr.org/news/conservative-firm-sues-elections-commission-meagan-wolfe-voter-list)

### Inferences
- Wisconsin offers the cheapest unrestricted path in the region relative to file size: the full statewide list is capped at $12,500, and it includes phone or email where voters provided them. The lack of DOB weakens identity matching.

### Gaps
- I could not fetch Wis. Stat. §6.36 text (TLS error on docs.legis.wisconsin.gov). The withheld-field list comes from WEC and press sources.

---

## Cross-state inferences for planning

### Takeaway
Only **Ohio, Wisconsin and Michigan** permit this use. Every other state in the region either limits who may obtain the file (IL, IN statewide, MN, ND) or bars commercial or non-political use outright (IA, KS, MO, NE, SD), with criminal penalties ranging from a misdemeanor to a Class 4 or Class IV felony (IL; NE false oath).

### Cited Findings
- See the per-state citations above.

### Inferences
- **Best data for identity resolution.**
  - Ohio: full DOB, likely; verify.
  - Michigan: birth year.
  - Wisconsin: no age data, but phone or email where provided.
- **Indiana is the only partially open path among the restricted states.** County-level copies under VRG-24 are possible where the county board's policy permits them. The conditions are no solicitation and no transfer for non-political purposes. This needs Indiana counsel review because of the IC 3-7-26.3 "exclusively for voter registration and election administration" clause.
- Purchasing indirectly through a political committee or vendor in a restricted state would not cure the use restriction. Most of these statutes bind any person who receives or uses the data (IL, IA, KS, MO, NE, SD, MN).

### Gaps
- NCSL, EAC and Ballotpedia compilations could not be fetched directly in this session (DNS blocked). Cross-checks against them rely on search excerpts only.
