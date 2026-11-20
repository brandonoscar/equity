# Midwest: Public Records Law and Bulk County Recorder Index Data (OH, MI, IN, IL, WI, MN, IA, MO)

Method note (read first): in this session, WebFetch could not reach any official statute host (codes.ohio.gov, ilga.gov, revisor.mn.gov, docs.legis.wisconsin.gov, revisor.mo.gov, ago.mo.gov all failed DNS under the session's network allowlist). Findings below come from web-search result excerpts of those primary pages, plus some well-established points from background knowledge. Items marked **[background, not verified in-session]** were not confirmed against a fetched source and must be checked before use. Statute subsection numbers move often; re-check every pin cite on the official site before putting it in a request template. Date of research: 2026-11-20.

Scoring scale (Q9): 5 = statute plus practice make a free or near-free CSV/database index export likely; 1 = a recorder-specific fee statute, a no-new-record rule or a commercial restriction makes free bulk data very unlikely.

## Q1. Public records statute name and citation

### Takeaway
Every state has a general open-records act that reaches county recorders. In most of them, though, a recorder-specific fee statute overrides that act for recorded documents, and sometimes for indexes too.

### Cited Findings
- Ohio: Public Records Act, R.C. 149.43. Versions dated 4-9-2025, 9-30-2025 and 9-7-2026 appear on the official site, so the section was amended again in 2026. — [codes.ohio.gov 149.43 (9-7-2026 PDF)](https://codes.ohio.gov/assets/laws/revised-code/authenticated/1/149/149.43/9-7-2026/149.43-9-7-2026.pdf)
- Michigan: Freedom of Information Act, 1976 PA 442, MCL 15.231 et seq. — [Michigan Legislature, Act 442 of 1976](https://www.legislature.mi.gov/documents/mcl/pdf/mcl-act-442-of-1976.pdf)
- Indiana: Access to Public Records Act (APRA), IC 5-14-3. It was heavily amended by HEA 1360 (P.L. 97-2026), signed March 4, 2026 and effective July 1, 2026. — [Indiana PAC overview of HEA 1360](https://secure.in.gov/pac/files/Overview_of_APRA_Changes_under_HEA_1360.pdf); [Indiana Capital Chronicle](https://indianacapitalchronicle.com/2026/01/22/indiana-public-records-access-law-to-get-anti-bot-overhaul/)
- Illinois: Freedom of Information Act, 5 ILCS 140. — [Illinois AG FOIA FAQ (10/2023)](https://illinoisattorneygeneral.gov/Page-Attachments/FOIAPAC/FAQ_FOIA_Public.pdf)
- Wisconsin: Public Records Law, Wis. Stat. 19.31–19.39. — [Wisconsin DOJ PRL Compliance Guide, June 2025](https://www.wisdoj.gov/Open%20Government/PRL_guide.pdf)
- Minnesota: Minnesota Government Data Practices Act, Minn. Stat. ch. 13; access and fees are in 13.03. — [Minn. Stat. 13.03](https://www.revisor.mn.gov/statutes/cite/13.03)
- Iowa: Examination of Public Records (Open Records), Iowa Code ch. 22. — [Iowa Code ch. 22 PDF](https://www.legis.iowa.gov/docs/ico/chapter/22.pdf)
- Missouri: Sunshine Law, RSMo 610.010–610.035; fees are in 610.026. — [RSMo 610.026](https://revisor.mo.gov/main/OneSection.aspx?section=610.026)

### Inferences
- In every state the general act is the vehicle for the request. The real fight is whether a recorder fee statute such as Ohio 317.32, Michigan 600.2567/565.551, Indiana 36-2-7-10.1, Illinois 55 ILCS 5/3-5018, Wisconsin 59.43(2), Minnesota 357.18 or Missouri 59.310 displaces the general fee cap.

### Gaps
- None of the official statute pages could be fetched in this session (see Method note).

## Q2. Fee rules, and recorder fee statutes that override the general cap

### Takeaway
On paper the general acts mostly cap fees at actual cost. Ohio, Missouri and Iowa have the strongest pro-requester rules for electronic copies, and Ohio's comes from case law. Michigan, Wisconsin, Indiana and Illinois each have a recorder statute that can override FOIA pricing. Minnesota lets counties add a "commercial value" charge.

### Cited Findings
**Ohio**
- A "bulk commercial special extraction request" may be charged at actual cost plus special extraction costs plus ten percent. A requester who assures the office the copies won't be used for "surveys, marketing, solicitation, or resale for commercial purposes" falls outside the definition, and that phrase is to be narrowly construed. — [codes.ohio.gov 149.43](https://codes.ohio.gov/ohio-revised-code/section-149.43); [FindLaw 149.43](https://codes.findlaw.com/oh/title-i-state-government/oh-rev-code-sect-149-43/)
- *State ex rel. Data Trace Information Servs., L.L.C. v. Cuyahoga Cty. Fiscal Officer*, 2012-Ohio-753, addressed whether a recorder may charge the R.C. 317.32(I) per-page photocopy fee when electronic copies are requested. — [Ohio Supreme Court, 2012-Ohio-753](https://www.supremecourt.ohio.gov/rod/docs/pdf/0/2012/2012-ohio-753.pdf). **[Background, not verified in-session]**: my recollection is that the court held 317.32(I) covers photocopies only, so electronic copies of recorded documents cost only actual cost under 149.43(B). Read the opinion to confirm.
- Ohio AG Opinion 2000-046: a county recorder may not charge a fee for Internet access to indexed public records, because 317.32 lists the fees a recorder may collect. — [OAG 2000-046](https://ohioattorneygeneral.gov/getattachment/31e85dee-8ce6-4f2c-9e7c-14ef9f5a71bf/2000-046.aspx)
- A 2021 LSC bill analysis says recorders must put electronic indexes and images on their websites and may not charge to create a login or to access them. — [Ohio LSC analysis, Apr. 19, 2021](https://www.legislature.ohio.gov/download?key=16345). (I did not confirm whether that bill was enacted.)
- Current 317.32 sets a fee for certifying a copy or electronic record of a recorded instrument. — [R.C. 317.32 (10-24-2024)](https://codes.ohio.gov/assets/laws/revised-code/authenticated/3/317/317.32/10-24-2024/317.32-10-24-2024.pdf)

**Michigan**
- MCL 15.234(10), formerly (4), says FOIA fee limits do not apply to records prepared under a statute "specifically authorizing the sale of those public records to the public," or where a statute specifically sets the copy fee. — [MCL 15.234](https://www.legislature.mi.gov/(S(rtsp4qenx0q0yf4bvevjdwe3))/mileg.aspx?page=getobject&objectname=mcl-15-234&query=on&highlight=foia)
- *Title Office, Inc. v. Van Buren County Treasurer* (Mich. 2004): electronic copies of property tax records are "transcripts," so the fees in the property-tax statute govern, not FOIA. The Supreme Court criticized the contrary *Oakland County Treasurer v. Title Office* (Mich. App. 2001). — [FindLaw, Title Office (2004)](https://caselaw.findlaw.com/court/mi-supreme-court/1457611.html); [CourtListener](https://www.courtlistener.com/opinion/848747/title-office-inc-v-van-buren-county-treasurer/)
- MCL 565.551: the register of deeds must provide facilities for inspection. For reproductions other than paper copies, the fee may not exceed the register's reasonable costs unless another law sets a fee. — [MCL 565.551](https://zeus-milenia.legislature.mi.gov/documents/mcl/pdf/MCL-565-551.pdf)
- MCL 600.2567 sets register fees, including a search fee of 50 cents per year searched with a $5 minimum for grantor/grantee searches. — [MCL 600.2567](https://www.legislature.mi.gov/documents/mcl/pdf/MCL-600-2567.pdf)
- **[Background, not verified in-session]**: MCL 15.234 otherwise allows labor charges (search, examination, separation) at the lowest-paid capable employee's hourly wage, itemized on a standard form.

**Indiana**
- IC 36-2-7-10.1 governs bulk recorder data. A "bulk form copy" is an aggregation of copies of recorded documents, the indices used to find them, or both, delivered to a "bulk user" under a contract with the recorder. A state presentation cites $0.10 per page under 10.1(d). Howard County's ordinance sets $0.13 per page where actual cost exceeds the statutory amount. Revenue goes to the recorder's records perpetuation fund. — [Indiana SBOA "Heath Bulk Copies"](https://secure.in.gov/sboa/files/Heath-Bulk-Copies.pdf); [FindLaw IC 36-2-7-10.1](https://codes.findlaw.com/in/title-36-local-government/in-code-sect-36-2-7-10-1/); [Howard County ordinance](https://codelibrary.amlegal.com/codes/howardcountyin/latest/howardcounty_in/0-0-0-805)
- IC 5-14-3-8 allows fees for recorder records when they are authorized under IC 36-2-7-10 or 10.1. — [Doxpop Indiana statute references](https://www.doxpop.com/prod/public_access.jsp)
- HEA 1360 (effective July 1, 2026) lets an agency collect a supplemental fee, "reasonably related to the cost," for requests from non-Indiana residents, out-of-state entities or automated systems (IC 5-14-3-8(n)). The agency may waive it in the public interest (8(o)). The final bill changed "shall" to "may." — [PAC overview](https://secure.in.gov/pac/files/Overview_of_APRA_Changes_under_HEA_1360.pdf); [PAC statutory additions](https://secure.in.gov/pac/files/Statutory_Additions_under_HEA_1360.pdf). News reports of a cap of 25 cents per page or $25 per staff hour were not confirmed in the statutory text. — [Indiana Capital Chronicle](https://indianacapitalchronicle.com/2026/01/22/indiana-public-records-access-law-to-get-anti-bot-overhaul/)

**Illinois**
- 55 ILCS 5/3-5018 ("Traditional fee schedule," amended by P.A. 100-1034) excludes from its fee provisions people who get non-certified copies (i) in bulk for all documents recorded on a given day, (ii) for an amount negotiated with the recorder, or (iii) through internet access under 55 ILCS 5/5-1106.1. — [P.A. 100-1034](https://ilga.gov/ftp/Public%20Acts/100/100-1034.htm)
- SB3143 (introduced 2/2/2026) would require first- and second-class counties to adopt a "predictable fee schedule" under 3-5018.2. Its status is unknown. — [SB3143 text](https://ilga.gov/ftp/legislation/104/SB/10400SB3143.htm)
- One state agency's FOIA page says electronic records cost the actual cost of the recording medium. — [Illinois HFS FOIA page](https://hfs.illinois.gov/info/legal/foia.html)
- **[Background, not verified in-session]**: 5 ILCS 140/6(a) allows no fee for electronic copies beyond the cost of the medium, "except when fees are otherwise fixed by statute." 6(b) makes the first 50 black-and-white pages free and then caps copies at 15 cents per page. 6(a-5) and 6(f) allow tiered charges for "voluminous requests" (about $20 / $40 / $100 by file size). A recorder can treat 3-5018's negotiated-bulk clause as a statute that "fixes" the fee.

**Wisconsin**
- The per-page fee in 59.43(2)(b) ($2 for the first page and $1 for each additional page of each document), not the 19.35(3) actual-cost fee, applies to electronic copies of records obtained under 59.43(4), unless the requester has a contract under 59.43(2)(c). An annotation says such contracts may bar resale or dissemination. — [FindLaw Wis. Stat. 59.43 with annotations](https://codes.findlaw.com/wi/municipalities-ch-59-to-68/wi-st-59-43/); [Wis. Stat. 59.43](https://docs.legis.wisconsin.gov/document/statutes/59.43)
- The real estate index must be searchable by at least grantor name, grantee name and document number (59.43(9)). — [Wis. Stat. 59.43](https://docs.legis.wisconsin.gov/document/statutes/59.43)
- **[Background, not verified in-session]**: 19.35(3) limits fees to "actual, necessary and direct" costs. A location fee is allowed only when location costs reach $50 or more. *Milwaukee Journal Sentinel v. City of Milwaukee*, 2012 WI 65, bars charging for redaction.

**Minnesota**
- Minn. Stat. 13.03 subd. 3(d): when data have commercial value and are a substantial, discrete portion of a database or compilation developed with significant public expenditure, the authority may add a reasonable fee on top of copy costs, and must document and justify it on request. Inspection must be free. — [Minn. Stat. 13.03](https://www.revisor.mn.gov/statutes/cite/13.03); [FindLaw 13.03](https://codes.findlaw.com/mn/data-practices-ch-13-13c/mn-st-sect-13-03/)
- Advisory Opinion 03-025: a county could charge $75 for a copy of an inventory plus a $175 commercial-value add-on, and had to provide it electronically if reasonably able. — [MN Admin AO 03-025](https://mn.gov/admin/data-practices/opinions/library/?id=36-267501). AO 00-006: no commercial-value charge is allowed when no copies are provided. — [AO 00-006](https://mn.gov/admin/data-practices/opinions/library/?id=36-267523). AO 02-004 reviewed a $13,703 electronic-copy charge for Hennepin property tax records that included a commercial-value add-on; I could not see the outcome. — [AO 02-004](https://mn.gov/admin/data-practices/opinions/library/?id=36-267664)
- Minn. Stat. 357.18: the county sets the fee for a noncertified copy of a recorded instrument; certified copies are $10. 357.182 bars counties from charging recording-related fees not set by state law. — [357.18 (2025)](https://www.revisor.mn.gov/statutes/?id=357.18); [357.182](https://www.revisor.mn.gov/statutes/cite/357.182)
- **[Background, not verified in-session]**: 13.03 subd. 3(c) allows "actual costs of searching for and retrieving" data plus copying, and a flat 25 cents per page for 100 or fewer black-and-white pages.

**Iowa**
- Iowa Code 22.3 limits fees to actual costs. 22.3A(2)(d) allows "the reasonable costs of any required processing, programming, or other work required to produce the public record in the specific format." — [Iowa Code 22.3A (Justia)](https://law.justia.com/codes/iowa/title-i/chapter-22/section-22-3a/); [22.3A PDF](https://www.legis.iowa.gov/docs/code/22.3A.pdf); [RCFP Iowa](https://www.rcfp.org/open-government-guide/iowa/)
- Example: the University of Iowa charges $75/hour for database extraction. — [UI public records fee schedule](https://transparency.uiowa.edu/public-records-request)
- Iowa Code 331.604 is the recorder fee section; it also funds the county land record information system through a $1 electronic transaction fee (331.604(3)). — [2012 LSA filing](https://www.legis.iowa.gov/DOCS/LSA/Docs_Filed/2012/DFJYD069.PDF); [Iowa Code ch. 331 (2025)](https://www.legis.iowa.gov/docs/code/2025/331.html)

**Missouri**
- RSMo 610.026 is the fee section. A requester may ask for a cost estimate before production. A 2025 amendment added a withdrawal rule: a request lapses if a clarification request gets no reply within 90 days (150 days when fees exceed $1,000). — [RSMo 610.026](https://revisor.mo.gov/main/OneSection.aspx?section=610.026); [Justia 610.026](https://law.justia.com/codes/missouri/title-xxxix/chapter-610/section-610-026/)
- RSMo 59.310 caps recorder copies at $2 for the first page and $1 for each later page. For non-paper duplicates, the recorder sets "a reasonable fee not to exceed the costs associated with document search and duplication." — [RSMo 59.310](https://revisor.mo.gov/main/OneSection.aspx?section=59.310)
- *Webster County Abstract Co. v. Atkison* (Mo. App. S.D. 2010) involved a recorder's per-record charges under the "except as otherwise provided by law" clause of 610.026. The search excerpt was internally inconsistent: one passage said the recorder could keep statutory per-record charges, another said a uniform per-electronic-record fee was not authorized. — [Missouri AG Sunshine fee decisions page](https://ago.mo.gov/get-help/programs-services-from-a-z/sunshine-law/court-decisions-and-attorney-general-opinions/fees/). Treat the holding as unverified.
- **[Background, not verified in-session]**: 610.026.1(1) sets 10 cents per page for paper up to 9x14 inches, plus staff time at the average clerical rate. 610.026.1(2) limits electronic-record fees to the medium, staff time and programming costs where needed.

### Inferences
- Ohio is the best fee environment because of Data Trace, assuming my reading holds, and OAG 2000-046.
- Wisconsin is the worst for document images ($2/$1 per page for electronic copies). An index-only extract arguably isn't a "copy of a recorded document," so it may fall back to 19.35(3) actual cost. That argument is untested in what I found.
- Indiana bulk pricing is set per page. How a pure index extract is priced under 10.1 is unclear; it may come out very cheap or at a negotiated amount.

### Gaps
- I did not verify the Data Trace holding, Michigan FOIA labor rules, Illinois 6(a)/(b) text, Missouri 610.026.1 text or the Atkison holding against fetched primary text.
- I did not find a Michigan statute specifically authorizing bulk sale of register of deeds data. MCL 565.551 only covers inspection and reproduction cost. 2016 PA 224 (SB 599), which showed up in the search, was not reviewed.

## Q3. Database extracts: existing record or "new record"? Format rules

### Takeaway
Iowa (IPIB 24AO:0003) and Wisconsin (WIREdata) treat data pulled from an existing database as an existing record. Ohio follows Kerner [background, not verified in-session]. Wisconsin and Michigan statutes also say there is no duty to compile a new record. Illinois, Minnesota, Missouri, Indiana and Ohio favor delivery in the electronic format requested or kept.

### Cited Findings
- Iowa: IPIB Advisory Opinion 24AO:0003 says data pulled from an existing database or software system is covered, but a request cannot require creating information the body never stored. — [IPIB 24AO:0003](https://ipib.iowa.gov/advisory-opinion-24ao0003-data-and-public-records-requests). Agency guidance (Board of Regents, U. Iowa) says bodies are not required to create a new dataset or compilation. — [Regents fee guidelines](https://www.iowaregents.edu/media/cms/Fees_for_Open_Records_Requests_3FD538D6FEE1F.pdf)
- Wisconsin: 19.35(1)(L) says an authority need not "create a new record by extracting information from existing records and compiling the information in a new format." — [Justia 19.35](https://law.justia.com/codes/wisconsin/2015/chapter-19/section-19.35); [WI DOJ guide](https://www.wisdoj.gov/Open%20Government/PRL_guide.pdf). *WIREdata, Inc. v. Village of Sussex*, 2008 WI 69, held the requester was entitled to access to the computerized assessment database through municipal extraction. The court of appeals had listed options such as exporting through Market Drive or MS Access, or copying the database file. — [Justia WIREdata (2008)](https://law.justia.com/cases/wisconsin/supreme-court/2008/33183.html); [FindLaw WIREdata (Ct. App. 2007)](https://caselaw.findlaw.com/court/wi-court-of-appeals/1090718.html). RCFP describes the case more narrowly: no right to direct database access. — [RCFP Wisconsin](https://www.rcfp.org/open-government-guide/wisconsin/)
- Minnesota: AO 03-025 says a county must provide data electronically if it is reasonably able to. — [AO 03-025](https://mn.gov/admin/data-practices/opinions/library/?id=36-267501)
- Indiana: a 2009 informal PAC opinion said an agency is not required to grant access to bulk records. It predates the 2026 amendments. — [PAC 09-INF-35](https://www.in.gov/pac/files/informal/09-INF-35.pdf)
- **[Background, not verified in-session]**:
  - Ohio: *State ex rel. Kerner v. State Teachers Retirement Bd.*, 82 Ohio St.3d 273 (1998), says output that existing programming can produce is not a "new record." R.C. 149.43(B)(6) lets the requester choose paper, the same medium the office uses, or another medium the office can reasonably use.
  - Illinois: 5 ILCS 140/6(a) requires electronic copies in the format requested if the body maintains the record that way and it is feasible, or else in the format maintained.
  - Indiana: IC 5-14-3-3(d) requires reasonable efforts to provide disclosable data on paper, disk, tape or another electronic medium if the requested medium is compatible with the agency's storage system.
  - Missouri: RSMo 610.029 requires an electronic copy in the format requested when the record is kept electronically.
  - Michigan: FOIA says the Act does not require a compilation, summary or report of information (MCL 15.233). Michigan also defines public records to include computerized data.

### Inferences
- A template should ask for "an export of the existing index table(s) in the native or CSV format produced by the system's existing export/report functions." It should name the fields and cite Kerner, WIREdata or IPIB 24AO:0003, as applicable, so the request can't be refused as a "new record."

### Gaps
- I found no recorder-specific case in any of these states deciding whether an index-table export is a "new record."

## Q4. Residency restriction

### Takeaway
None of the eight states has a hard residency bar. Indiana, from July 1, 2026, lets agencies deprioritize and surcharge non-resident and automated requests.

### Cited Findings
- Indiana HEA 1360: agencies may prioritize Indiana residents (IC 5-14-3-8.1), delay out-of-state and automated requests as needed to protect core functions (8.1(b)), and charge them a supplemental fee. Sponsor statements mention verifying the requester's physical address. — [PAC overview](https://secure.in.gov/pac/files/Overview_of_APRA_Changes_under_HEA_1360.pdf); [Indiana Lawyer commentary](https://www.theindianalawyer.com/articles/jessica-laurin-meek-and-meg-christensen-what-to-know-about-changes-to-indiana-public-records-law)
- **[Background, not verified in-session]**: Ohio 149.43(B)(4) bars requiring identity or purpose. Michigan 15.233(1) covers "a person" (incarcerated persons excluded). Illinois 5 ILCS 140/1 and 3 cover "any person." Wisconsin 19.35(1)(i) bars requiring identity or purpose in most cases. Minnesota 13.05 subd. 12 bars requiring identity or purpose except as needed. Iowa 22.2 covers "every person." Missouri 610.011 has no residency rule.

### Inferences
- In Indiana, a requester with an Indiana address can avoid the out-of-state surcharge and delay. Since requests go out honestly under a real person's name, that only helps if the person actually lives in Indiana.

### Gaps
- I did not confirm the identity and residency provisions marked as background against current text.

## Q5. Commercial-purpose restrictions, certification or surcharges

### Takeaway
Illinois requires disclosure of commercial purpose and gives the agency 21 business days. Ohio's bulk-commercial pricing applies unless the requester certifies no commercial use. Indiana bars bulk users from transferring data to third parties for commercial purposes. Minnesota adds a commercial-value fee. Michigan, Wisconsin, Iowa and Missouri have no general commercial-purpose rule.

### Cited Findings
- Illinois: "commercial purpose" (5 ILCS 140/2(c-10)) means use of a record or derived information for sale, resale, or solicitation or advertising of sales or services. Commercial requests get 21 business days. Knowingly getting a record for a commercial purpose without disclosing it violates FOIA. — [IL AG FAQ](https://illinoisattorneygeneral.gov/Page-Attachments/FOIAPAC/FAQ_FOIA_Public.pdf); [Cook County FOIA form](https://www.cookcountyil.gov/sites/g/files/ywwepo161/files/service/foia-form-3-2020.pdf); [Illinois State Police FOIA FAQ](https://isp.illinois.gov/Foia/FAQ)
- Ohio: bulk commercial special extraction (surveys, marketing, solicitation, resale) costs actual cost plus extraction cost plus 10%. A requester who assures non-commercial use is outside the definition. — [codes.ohio.gov 149.43](https://codes.ohio.gov/ohio-revised-code/section-149.43); [FindLaw](https://codes.findlaw.com/oh/title-i-state-government/oh-rev-code-sect-149-43/)
- Indiana: under IC 36-2-7-10.1(i), a bulk user may not transfer bulk copies to a third party for commercial purposes, except licensed title plants or title companies filling a title-search order. Some counties require a "Not for resale pursuant to I.C. 36-2-7-10.1(K)" legend. — [Tippecanoe County code](https://codelibrary.amlegal.com/codes/tippecanoe/latest/tippecanoeco_in/0-0-0-17299); [Vanderburgh County code 2.86](https://www.codepublishing.com/IN/VanderburghCounty/html/VanderburghCounty02/VanderburghCounty0286.html); [FindLaw IC 36-2-7-10.1](https://codes.findlaw.com/in/title-36-local-government/in-code-sect-36-2-7-10-1/)
- Minnesota: 13.03 subd. 3(d) commercial-value add-on (see Q2). — [Minn. Stat. 13.03](https://www.revisor.mn.gov/statutes/cite/13.03)
- Wisconsin: contracts under 59.43(2)(c) may prohibit resale or dissemination. — [FindLaw 59.43 annotations](https://codes.findlaw.com/wi/municipalities-ch-59-to-68/wi-st-59-43/)

### Inferences
- A judgment buyer using the data to find and contact judgment creditors is probably making a "commercial" request in Illinois (solicitation of services) and probably fits Ohio's "solicitation" language too. An honest template should disclose commercial use in Illinois, and in Ohio should either accept bulk-commercial pricing or state the actual internal-analysis use accurately. Indiana's restriction is on transfer to third parties, so an internal graph is likely fine, though resale of derived data is risky.

### Gaps
- I found no AG opinion on whether internal analytics without resale counts as "commercial purpose" in Illinois or Ohio.

## Q6. Response deadlines

### Takeaway
Deadlines run from 3 business days (Missouri) to "reasonable time" (Ohio, Wisconsin, Minnesota, Indiana production). Illinois commercial requests get 21 business days.

### Cited Findings
- Illinois commercial requests: 21 business days. — [IL AG FAQ](https://illinoisattorneygeneral.gov/Page-Attachments/FOIAPAC/FAQ_FOIA_Public.pdf)
- Indiana: HEA 1360 allows delay for out-of-state and automated requests. — [PAC overview](https://secure.in.gov/pac/files/Overview_of_APRA_Changes_under_HEA_1360.pdf)
- Missouri: a request lapses if a clarification request gets no reply within 90 days (150 if fees exceed $1,000), per the 2025 amendment. — [RSMo 610.026](https://revisor.mo.gov/main/OneSection.aspx?section=610.026)
- **[Background, not verified in-session]**:
  - Ohio: "promptly" for inspection, copies "within a reasonable period of time" (149.43(B)(1)).
  - Michigan: 5 business days, plus one 10-business-day extension (MCL 15.235).
  - Indiana: response within 24 hours (in person or phone) or 7 days (mail, email); production within a "reasonable time" (IC 5-14-3-9).
  - Illinois non-commercial: 5 business days plus a 5-day extension (5 ILCS 140/3(d)–(e)).
  - Wisconsin: "as soon as practicable and without delay" (19.35(4)(a)); DOJ suggests about 10 business days for simple requests.
  - Minnesota: "appropriate and prompt manner and within a reasonable time" (13.03 subd. 2).
  - Iowa: good-faith delay "shall not exceed twenty calendar days and ordinarily should not exceed ten business days" (22.8(4)).
  - Missouri: no later than the end of the third business day, with an explanation for any delay (610.023.3).

### Gaps
- The background deadlines were not checked against current text. Indiana's portal and timing changes for July 2026 need the enrolled text.

## Q7. Recorder-specific bulk and subscription statutes, and typical prices

### Takeaway
Indiana (IC 36-2-7-10.1, about $0.10 per page by contract) and Illinois (55 ILCS 5/3-5018 negotiated or daily bulk) have explicit bulk-sale statutes. Wisconsin uses contracts under 59.43(2)(c). Minnesota counties sell subscriptions under the 13.03 subd. 3(d) commercial-value rule. Ohio, Michigan, Missouri and Iowa have no explicit bulk-sale statute that I found.

### Cited Findings
- Indiana: 10.1(d) is $0.10 per page per the state presentation. A 2016 county listing showed $0.07; Howard County charges $0.13. The recorder may refuse bulk users who violated earlier contracts. — [SBOA Heath Bulk Copies](https://secure.in.gov/sboa/files/Heath-Bulk-Copies.pdf); [Lopez recorder fees 2017](https://Www.in.gov/sboa/files/Lopez-Recorders-Fees-2017-Current.pdf); [Howard County ordinance](https://codelibrary.amlegal.com/codes/howardcountyin/latest/howardcounty_in/0-0-0-805)
- Illinois: 3-5018 exempts daily bulk, negotiated-amount and 5-1106.1 internet access from the fee schedule. — [P.A. 100-1034](https://ilga.gov/ftp/Public%20Acts/100/100-1034.htm)
- Minnesota: Washington County's RecordEASE web agreement treats its system as commercial-value data under 13.03 subd. 3(d), with a monthly subscription plus per-search and per-tract-view fees. — [Washington County RecordEASE agreement](https://washingtoncountymn.gov/DocumentCenter/View/812/RecordEASE-Web-Agreement?bidId=)
- Wisconsin: 59.43(2)(c) contracts (see Q2). — [FindLaw 59.43](https://codes.findlaw.com/wi/municipalities-ch-59-to-68/wi-st-59-43/)
- Missouri: 59.310 sets cost-based fees for non-paper duplicates. — [RSMo 59.310](https://revisor.mo.gov/main/OneSection.aspx?section=59.310)
- Michigan: 565.551 sets reasonable cost for non-paper reproductions; 600.2567 sets search fees. — [MCL 565.551](https://zeus-milenia.legislature.mi.gov/documents/mcl/pdf/MCL-565-551.pdf); [MCL 600.2567](https://www.legislature.mi.gov/documents/mcl/pdf/MCL-600-2567.pdf)

### Gaps
- I found no actual county bulk index price sheets: no dollar figures for an Illinois negotiated bulk deal, a Wisconsin register contract, a Cook County Clerk recordings data subscription, or a Michigan register of deeds bulk deal.

## Q8. Known free statewide or county bulk recorder and land-records data

### Takeaway
I confirmed no free bulk grantor/grantee index download in any of these eight states. Iowa has a statewide recorder portal, and Ohio recorders must provide free online index access.

### Cited Findings
- Iowa: the County Land Record Information System is mandatory for all counties (Iowa Code 331.604(3)) and is run through the Iowa County Recorders Association (iowalandrecords.org). The search results don't show a bulk index download or subscription. — [2012 LSA filing](https://www.legis.iowa.gov/DOCS/LSA/Docs_Filed/2012/DFJYD069.PDF); [ICRA Recorder's Manual (Aug. 2025)](https://iowalandrecords.org/wp-content/uploads/2026/06/Recorders-Manual_Aug.7.2025.2025.pdf)
- Ohio: per OAG 2000-046 and the 2021 LSC analysis, recorders may not charge for Internet index access. This is free per-search access, not a bulk download. — [OAG 2000-046](https://ohioattorneygeneral.gov/getattachment/31e85dee-8ce6-4f2c-9e7c-14ef9f5a71bf/2000-046.aspx); [LSC 2021](https://www.legislature.ohio.gov/download?key=16345)
- Minnesota (Washington County) sells access by subscription rather than offering it free. — [RecordEASE agreement](https://washingtoncountymn.gov/DocumentCenter/View/812/RecordEASE-Web-Agreement?bidId=)

### Inferences
- **[Background, not verified in-session]**: possible free proxies worth checking:
  - The Cook County Assessor parcel-sales dataset on the Cook County open data portal, which may include deed/document number, deed type and buyer/seller names.
  - Statewide sales-ratio or transfer-return data: Wisconsin eRETR, Minnesota eCRV and Ohio county auditor conveyance files.
  - Those cover transfers only, not mortgages, liens or releases.

### Gaps
- I did not verify the Cook County open data fields, Iowa bulk terms, or Wisconsin, Minnesota and Ohio transfer-data downloads.

## Q9. Score: free or near-free machine-readable recorder index via a records request (1–5)

### Takeaway
Ohio scores highest. Iowa, Missouri and Illinois are middling. Michigan, Indiana, Minnesota and Wisconsin are low, because a recorder fee statute or a commercial-value rule overrides actual-cost pricing.

### Cited Findings (score: reason)
- **Ohio: 4.** Electronic copies at actual cost (Data Trace, unverified reading) and no fee for internet index access (OAG 2000-046), but commercial bulk extraction can add employee time plus 10%. — [2012-Ohio-753](https://www.supremecourt.ohio.gov/rod/docs/pdf/0/2012/2012-ohio-753.pdf); [149.43](https://codes.ohio.gov/ohio-revised-code/section-149.43)
- **Iowa: 3.** Actual-cost rule, and IPIB treats database extracts as existing records, but 22.3A allows programming costs. — [IPIB 24AO:0003](https://ipib.iowa.gov/advisory-opinion-24ao0003-data-and-public-records-requests); [22.3A](https://law.justia.com/codes/iowa/title-i/chapter-22/section-22-3a/)
- **Missouri: 3.** Non-paper recorder copies are capped at search and duplication cost (59.310), but staff time and programming may be charged, and Atkison is unclear. — [59.310](https://revisor.mo.gov/main/OneSection.aspx?section=59.310)
- **Illinois: 3.** Electronic copies are cheap under FOIA, but 3-5018 allows negotiated bulk pricing, commercial disclosure applies, and 21-day timing. — [P.A. 100-1034](https://ilga.gov/ftp/Public%20Acts/100/100-1034.htm); [IL AG FAQ](https://illinoisattorneygeneral.gov/Page-Attachments/FOIAPAC/FAQ_FOIA_Public.pdf)
- **Michigan: 2.** FOIA fee limits yield to statutory fees (15.234(10), Title Office), FOIA allows labor charges, and there is no duty to compile. — [15.234](https://www.legislature.mi.gov/(S(rtsp4qenx0q0yf4bvevjdwe3))/mileg.aspx?page=getobject&objectname=mcl-15-234&query=on&highlight=foia); [Title Office](https://caselaw.findlaw.com/court/mi-supreme-court/1457611.html)
- **Indiana: 2.** Bulk is by contract only at about $0.10 per page (36-2-7-10.1), with a resale bar, and from 2026 a surcharge and delay for out-of-state requests. It could rise to 3 if a pure index extract is priced low. — [SBOA](https://secure.in.gov/sboa/files/Heath-Bulk-Copies.pdf); [PAC HEA 1360](https://secure.in.gov/pac/files/Overview_of_APRA_Changes_under_HEA_1360.pdf)
- **Minnesota: 2.** Search and retrieval costs plus a commercial-value add-on (13.03 subd. 3(d)), and counties sell subscriptions. — [13.03](https://www.revisor.mn.gov/statutes/cite/13.03); [RecordEASE](https://washingtoncountymn.gov/DocumentCenter/View/812/RecordEASE-Web-Agreement?bidId=)
- **Wisconsin: 2.** Electronic copies of recorded documents cost $2/$1 per page (59.43(2)(b)) unless there is a contract, and 19.35(1)(L) says there is no duty to create a record. An index-only export might get actual cost under WIREdata (untested). — [FindLaw 59.43](https://codes.findlaw.com/wi/municipalities-ch-59-to-68/wi-st-59-43/); [WIREdata](https://law.justia.com/cases/wisconsin/supreme-court/2008/33183.html)

### Inferences
- Across all eight states, asking for index fields only (no images) is the best way to stay under general actual-cost rules, since most recorder fee statutes are written per page of a recorded document.

### Gaps
- These scores are not checked against any county's actual responses. A pilot request to one or two counties per state would calibrate them. (The constraint not to contact agencies was respected in this research.)
