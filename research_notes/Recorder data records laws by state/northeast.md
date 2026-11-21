# Northeast (ME, NH, VT, MA, RI, CT, NY, NJ, PA): public records law and bulk county/town recorder index data

Method note: WebSearch worked; WebFetch failed (DNS refused) for every primary host tried: mainelegislature.org, legislature.vermont.gov, state.ct.us (CT FOIC archive), pacourts.us, docsopengovernment.dos.ny.gov, pria.us. Findings marked with a [Source] come from search-result extracts of those or other pages, not full-text reads. Statements marked **[background, unverified this session]** come from prior knowledge, with no page confirmed here. Each one is listed again under Gaps and needs a check against the official statute before anyone relies on it.

Who holds land records (this sets how many requests are needed):
- ME: 16 county registries of deeds.
- NH: 10 county registries.
- VT: about 246 town and city clerks.
- MA: 21 registry districts, state-run under the Secretary of the Commonwealth.
- RI: 39 city and town clerks / recorders of deeds.
- CT: 169 town clerks.
- NY: 57 county clerks, plus the NYC City Register (ACRIS).
- NJ: 21 county clerks or registers.
- PA: 67 county recorders of deeds.

## 1. Public records statute name and citation

### Takeaway
Every state has a general access statute. The one with the biggest effect on recorder data is PA's: its RTKL defers to recorder-specific fee statutes and allows special fees for "enhanced electronic access".

### Cited Findings
- MA: Public Records Law, M.G.L. c. 66, § 10. It covers records made or received by a Massachusetts agency or municipality, and denials can be appealed to the Supervisor of Records — [Mass. SOC](https://www.sec.state.ma.us/divisions/public-records/public-records-law/public-records-request.htm); [Barnstable Registry public records page](https://www.capecod.gov/departments/registry-of-deeds/general-information/massachusetts-public-records-law)
- CT: Freedom of Information Act, C.G.S. § 1-200 et seq. Copy fees are in § 1-212 — [CT FOIC § 1-212 page](https://portal.ct.gov/FOI/regulations/the-foi-act/sec-1212--formerly-sec-115--copies-and-scanning-of-public-records--fees); [Justia § 1-212](https://law.justia.com/codes/connecticut/title-1/chapter-14/section-1-212-formerly-sec-1-15)
- VT: Public Records Act, 1 V.S.A. §§ 315–320. Access and copying are in § 316 — [Vt. Legislature § 316](https://legislature.vermont.gov/statutes/section/01/005/00316); [FindLaw § 316](https://codes.findlaw.com/vt/title-1-general-provisions/vt-st-tit-1-sect-316/)
- RI: Access to Public Records Act (APRA), R.I. Gen. Laws § 38-2-1 et seq. Fees are in § 38-2-4 — [RI Legislature § 38-2-4](https://webserver.rilegislature.gov/Statutes/TITLE38/38-2/38-2-4.htm)
- NH: Right-to-Know Law, RSA ch. 91-A — [RSA 91-A](https://www.gencourt.state.nh.us/rsa/html/VI/91-A/91-A-10.htm)
- NJ: Open Public Records Act (OPRA), N.J.S.A. 47:1A-1 et seq. It was heavily amended by P.L. 2024, c. 16, effective September 3, 2024 — [GRC readable OPRA (Sept 2024)](https://nj.gov/grc/laws/act/Readable%20Version%20of%20OPRA%20(Sept%202024)(P.L.%202024,%20c.16).pdf); [P.L.2024 c.16](https://pub.njleg.gov/Bills/2024/AL24/16_.HTM)
- PA: Right-to-Know Law (RTKL), 65 P.S. § 67.101 et seq. Fees are in § 67.1307, and the Office of Open Records (OOR) publishes the fee schedule — [OOR fee structure](https://www.openrecords.pa.gov/RTKL/FeeStructure.cfm)
- NY: Freedom of Information Law (FOIL), Public Officers Law §§ 84–90. It applies to county clerk land records per Matter of Data Tree, LLC v. Romaine, 9 N.Y.3d 454 (2007) — [Leagle opinion](https://www.leagle.com/decision/20074639ny3d4541422)
- ME: Freedom of Access Act (FOAA), 1 M.R.S. § 400 et seq. Registry-specific fees are in 33 M.R.S. § 751 — [33 M.R.S. § 751](https://www.mainelegislature.org/legis/statutes/33/title33sec751.pdf)

### Inferences
- In every state the recorder/clerk is a covered "agency/public body". The live disputes are about fees and "creating a record", not coverage. Data Tree confirms coverage in NY, and MacImage's FOAA litigation confirms it in ME.

### Gaps
- Exact current section numbers for the ME FOAA fee section (believed to be 1 M.R.S. § 408-A) and the NH fee provision (believed to be RSA 91-A:4, IV) were not opened this session.

## 2. Fee rules (duplication only? staff time/programming? does a recorder fee statute override?)

### Takeaway
Recorder fee statutes override the general cap in PA (statutory recorder copy fee $0.50/page) and in ME (registry bulk schedule in 33 M.R.S. § 751). CT's FOI Commission has signaled that the $1/page land-records copy fee is not automatically the right fee for an electronic index. Per-page fees are what make bulk requests expensive, so whether they apply to an electronic export is the key question in each state.

### Cited Findings
- PA: a Recorder of Deeds may charge $0.50 per uncertified page and $1.50 per certified page under 42 P.S. § 21051, and the OOR's official fee schedule recognizes this. No fee may be charged for search or retrieval — [OOR fee structure](https://www.openrecords.pa.gov/RTKL/FeeStructure.cfm)
- PA: agencies may require prepayment under § 1307(h). A pending OOR appeal against the Fayette County Recorder of Deeds (AP 2026-2429) disputes a prepayment demand. The requester argues the RTKL does not let an agency shift its costs, and the county relies on the $0.50/page § 21051 fee. The outcome was not found — [Fayette ROD answer](https://fayettecorecorderpa.gov/wp-content/uploads/2026/07/Recorder-of-Deeds-Appeal-Answer.pdf_Redacted.pdf); [Requester reply](https://fayettecorecorderpa.gov/wp-content/uploads/2026/07/2026-07-09_AP2026-2429_RequesterReply_FINAL.pdf)
- PA: Noto/Zillow v. Luzerne County, No. 194 C.D. 2025 (Pa. Cmwlth. June 9, 2026), upheld a market-value fee for bulk CAMA (assessment) data in Excel/CSV. It relied on § 1307's provision for integrated property assessment lists and accepted the county's method of comparing other counties' prices. The OOR had held below that no fee was allowed. This involves assessment data, not recorder data, but it shows the court's tolerance for market-based bulk-data pricing — [Bloomberg Law](https://news.bloomberglaw.com/daily-tax-report/zillow-denied-pennsylvania-fee-refund-for-access-to-tax-data); [opinion PDF](https://wwwsecure.pacourts.us/assets/opinions/Commonwealth/out/194CD25_6-9-26.pdf?cb=1)
- CT: under § 1-212(b) the fee may not exceed the agency's cost. A public agency may require prepayment if the fee is estimated at $10 or more — [CT FOIC § 1-212](https://portal.ct.gov/FOI/regulations/the-foi-act/sec-1212--formerly-sec-115--copies-and-scanning-of-public-records--fees)
- CT: in a 1997 FOI Commission decision on a request for an electronic grantor/grantee index, the Commission stated: "nothing in this opinion shall be construed as suggesting that the Commission believes that the copying fee provided at § 7-34a(a), G.S., is an appropriate fee for a copy of land records in an electronic form." — [FIC 1996-558](https://state.ct.us/foi/1997FD/19970625/1996-558.htm) (search extract only, because the host was blocked)
- CT: 2021 HB 5011 amended both § 1-212 and § 7-34a, effective October 1, 2021, so the current § 7-34a text needs checking — [LegiScan HB 5011](https://legiscan.com/CT/text/HB05011/id/2387138/Connecticut-2021-HB05011-Comm_Sub.pdf)
- CT town fee schedules list land records under § 7-34a as a category separate from FOI copy fees — [Bethany FOI page](https://bethanyct.gov/foi); [East Haven fee schedule](https://www.easthaven-ct.gov/DocumentCenter/View/188/Basic-Fee-Schedule-PDF)
- RI: search and retrieval at up to $15/hour, with the first hour free. Copies at up to $0.15/page. Only a court may reduce or waive fees, if the information is in the public interest. Electronic records at the "reasonable actual cost" — [RI § 38-2-4](https://webserver.rilegislature.gov/Statutes/TITLE38/38-2/38-2-4.htm); [Justia 2015 § 38-2-4](https://law.justia.com/codes/rhode-island/2015/title-38/chapter-38-2/section-38-2-4/); [RI EOC APRA policy](https://eoc.ri.gov/sites/g/files/xkgbur986/files/2025-01/EOC%20APRA-Policy%202023_%20-%20Copy.pdf)
- VT: many town clerks charge $1/page for land record copies, even when the user photographs them. Clerks may charge for examining records under 32 V.S.A. § 1671(a)(3), at $5/hour and a $25/day maximum per one schedule. The Secretary of State publishes a uniform charges schedule under 1 V.S.A. § 316(d)–(e), which applies to municipalities that have not adopted their own — [Washington VT](https://www.washingtonvt.org/town-notices/charges-for-public-records-requests); [Guilford VT](https://guilfordvt.gov/services/land-records/); [Rutland Town fee schedule](https://www.rutlandtown.com/wp-content/uploads/2025/04/State-Town-Fee-Schedule.pdf); [VSARA uniform charges](https://sos.vermont.gov/vsara/manage/information-governance/compliance/uniform-charges-schedule)
- VT: the Secretary of State's land records standard says town clerk fees should follow statute "in a manner consistent with 1 V.S.A. § 316" — [VT Land Records Standard](https://outside.vermont.gov/dept/sos/VSARA/Manage/Governance/Standards/Vermont_LandRecordsStandard.pdf)
- NY: the Committee on Open Government (COOG) has opined that a county clerk may charge for electronic records only when preparation takes more than 2 hours of employee time. In another opinion it said the county may charge only consistent with CPLR § 8019(f)(5) and FOIL § 87(1)(c) — [COOG FOIL AO 19722](https://docsopengovernment.dos.ny.gov/coog/ftext/f19722.htm); [COOG f19252](https://docsopengovernment.dos.ny.gov/coog/ftext/2015/f19252.htm) (search extracts only)
- ME: see Q7 for the registry bulk schedule in 33 M.R.S. § 751(14-D).

### Inferences
- In PA, expect recorders to try either $0.50/page (§ 21051) or market pricing (the Luzerne reasoning). A requester should ask for an electronic index export, not documents or images, and argue that § 21051's per-page fee does not apply to a data file. That argument is not settled law.
- In CT and NY, the general cost-based caps (CT § 1-212(b) "cost"; NY § 87(1)(c) actual cost, with staff time only beyond 2 hours) are favorable for a single index export. Clerks may still invoke recording-office fee statutes (CT § 7-34a, NY CPLR 8019/8021).

### Gaps
- **[background, unverified this session]** MA: 2016 reform (St. 2016, c. 121). $0.05/page; staff time at $25/hour, with the first 2 hours free for municipalities and 4 hours free for state agencies. Petition to the Supervisor of Records for higher fees. Registry copy fees under G.L. c. 262 § 38 ($1/page). Whether c. 262 overrides c. 66 § 10 for electronic index exports was not determined.
- **[background, unverified]** NH: RSA 91-A:4, IV allows only the "actual cost" of copying and no charge for staff time spent searching. Registry copy fees appear in RSA 478:17-g. A 2008 bill (HB 1363) proposed $0.50/page, but its enactment was not confirmed — [HB 1363](https://bills.nhliberty.org/bills/2008/HB1363)
- **[background, unverified]** NJ: under OPRA 47:1A-5(b) the fee is actual cost ($0.05/letter page), "except as otherwise provided by law or regulation", so county clerk fee statutes (N.J.S.A. 22A:4-4.1 et seq.) can control. § 5(c) allows a special service charge for extraordinary effort. § 5(d) allows a special charge when a request needs substantial manipulation or programming of IT.
- **[background, unverified]** ME FOAA § 408-A: $0.10/page and staff time after the first 2 hours (rate believed $25/hour after a 2021 amendment).
- **[background, unverified]** NY CPLR 8019(f) county clerk copy fee is about $0.65/page.

## 3. Database extracts: existing record vs. "no duty to create"; format requirements

### Takeaway
NY and CT have the strongest statutory pro-extract rules. NY FOIL § 89(3)(a) treats a computer retrieval or extraction as not creating a new record, and Data Tree puts the burden on the clerk. CT § 1-211 requires providing computer-stored data in the medium requested. VT requires the standard electronic format if the agency keeps records electronically, but it need not create a record or use a nonstandard format. PA courts generally treat a database query as not creating a record, but this was not verified this session.

### Cited Findings
- NY: in Data Tree, LLC v. Romaine, 9 N.Y.3d 454 (2007), a data company requested Suffolk County Clerk land records electronically. The Court of Appeals held that questions of fact existed over whether compliance would require creating new records. It reversed a ruling that had put the privacy burden on the requester, holding that "the burden of proof rests solely with the [agency] to justify the denial of access", and remanded — [Leagle](https://www.leagle.com/decision/20074639ny3d4541422); [RCFP](https://rcfp.org/?p=40519); [Prison Legal News summary](https://www.prisonlegalnews.org/news/2009/feb/15/ny-land-records-denial-remanded-for-privacy-preparation-determination/)
- NY: the 2005 trial court had upheld the clerk's denial of the requested electronic format. The Appellate Division (36 A.D.3d 804) later remanded for in camera review of electronic accessibility and redaction (SSNs) — [2005 trial decision](https://www.nycourts.gov/reporter/pdfs/2005/2005_30134.pdf); [CounselStack AD summary](https://law.counselstack.com/opinion/data-tree-llc-v-romaine-nyappdiv-2007)
- VT: "If an agency maintains public records in an electronic format, nonexempt public records shall be available for copying in either the standard electronic format or the standard paper format, as designated by the party requesting the records." Also: "an agency may, but is not required to, provide copies of public records in a nonstandard format, create a public record, or convert paper public records to electronic format." — [FindLaw 1 V.S.A. § 316](https://codes.findlaw.com/vt/title-1-general-provisions/vt-st-tit-1-sect-316/)
- CT: any person applying in writing is entitled to a plain, facsimile, electronic or certified copy of a public record "promptly upon request" — [CT FOIC § 1-212](https://portal.ct.gov/FOI/regulations/the-foi-act/sec-1212--formerly-sec-115--copies-and-scanning-of-public-records--fees). A 2026 FIC decision addresses cost estimates for electronic records — [FIC 2025-0213](https://portal.ct.gov/-/media/foi/finaldecisions/2026/mar25/2025-0213.pdf)
- NH: RSA 478-A:4 lets a register receive, index, store and transmit electronic documents, with paper and electronic entries in the same index. RSA 478:5 requires grantor/grantee indexing — [RSA 478-A:4](https://gc.nh.gov/rsa/html/XLVIII/478-A/478-A-4.htm); [RSA 478](https://gencourt.state.nh.us/rsa/html/XLVIII/478/478-mrg.htm)

### Inferences
- Because every registry indexes grantor and grantee electronically (statutory in NH; universal in practice), an index export is a "retrieval" in NY/CT/VT terms rather than a new record. Clerks in NH, RI and NJ still have textual grounds to refuse a custom extract.

### Gaps
- **[background, unverified]** NY POL § 89(3)(a): any programming needed to retrieve a record maintained in a computer storage system "shall not be deemed to be the preparation or creation of a new record" when it takes a reasonable effort.
- **[background, unverified]** CT § 1-211(a): an agency with computer-stored records "shall provide... a copy of any nonexempt data... on paper, disk, tape or any other electronic storage device or medium requested... if the agency can reasonably make any such copy". § 1-212(b) lets computer-record fees include employee time for formatting or programming.
- **[background, unverified]** PA RTKL § 705 says there is no duty to create a record. Commonwealth Court case law (e.g., Dep't of Env. Prot. v. Cole, 2012) holds that pulling information from an existing database is not creating a record.
- **[background, unverified]** MA c. 66 § 6A(d) requires electronic records in the requested format "if feasible"; MA also has 950 CMR 32.
- **[background, unverified]** NJ OPRA 47:1A-5(d) requires the medium requested, with a special charge for substantial programming. NJ case law (e.g., Paff v. Galloway Twp., 2017) held that an email log drawn from a database is a government record and not a new creation.
- **[background, unverified]** RI § 38-2-3: an agency need not reorganize, consolidate or compile data it does not maintain in that form.
- NH 91-A "no duty to compile a new record" language was not verified.

## 4. Residency restriction

### Takeaway
Only PA (any "legal resident of the United States") and possibly NH ("citizen") have restrictions. Neither should block a U.S.-resident individual requester. The other states grant access to "any person". NJ was believed to be similar, but this is unverified.

### Cited Findings
- NH: the Right-to-Know Law applies to "citizens", which has been read both as "citizen of New Hampshire" and as "citizen of the United States" (third-party guide) — [MuckRock NH](https://muckrock.com/place/united-states-of-america/new-hampshire)
- CT: "any person applying in writing" — [CT FOIC § 1-212](https://portal.ct.gov/FOI/regulations/the-foi-act/sec-1212--formerly-sec-115--copies-and-scanning-of-public-records--fees)

### Inferences
- A requester who lives outside NH should consider using a New Hampshire-resident name if one is honestly available. Otherwise expect some registers to cite the "citizen" language.

### Gaps
- **[background, unverified]** PA 65 P.S. § 67.102 defines "requester" as a legal resident of the United States.
- **[background, unverified]** NY, NJ, MA, RI, VT and ME FOAA all use "any person".
- **[background, unverified]** VA-style residency limits: none known in this region.

## 5. Commercial-purpose restriction, certification, or surcharge

### Takeaway
NJ now requires commercial requesters to certify and gives the agency 14 business days, but cannot deny on that basis. NY can deny lists of names and addresses sought for commercial or fund-raising purposes, which is a real risk for grantor/grantee lists. No commercial restriction was found in the other states.

### Cited Findings
- NJ: P.L. 2024, c. 16 defines "commercial purpose" as direct or indirect use of a government record for sale, resale, solicitation, rent or lease of a service, or any use by which the user expects a profit. News media are excepted. The uniform request form has a certification box for commercial use and intended use — [NJSBA](https://njsba.org/news-information/school-leader/despite-strong-opposition-from-certain-segmentsnew-jersey-overhauls-its-open-public-records-act); [Pashman Stein](https://pbnlaw.com/Amendments-to-New-Jersey-Open-Public-Records-Act); [GRC readable OPRA](https://nj.gov/grc/laws/act/Readable%20Version%20of%20OPRA%20(Sept%202024)(P.L.%202024,%20c.16).pdf)
- NJ: commercial requests get 14 business days instead of 7. DCA materials say commercial use is "also still allowed" and a custodian cannot deny a request because the requester is commercial — [GRC 2024 seminar](https://nj.gov/grc/meetings/present/2024%20Annual%20OPRA%20Seminar%20-%20The%20Future%20of%20OPRA%20is%20Now.pdf); [Marshall Dennehey](https://marshalldennehey.com/articles/changes-nj%E2%80%99s-open-public-records-act-and-implications-siu)

### Inferences
- A judgment-buying business's use is "commercial" under NJ's definition, so the request must truthfully certify commercial use. This lengthens the deadline but does not raise the fee unless a special service charge applies.

### Gaps
- **[background, unverified]** NY POL § 89(2)(b)(iii): "sale or release of lists of names and addresses if such lists would be used for solicitation or fund-raising purposes" is an unwarranted invasion of personal privacy, and agencies may require certification of purpose. Grantor/grantee indexes without addresses arguably fall outside this. Requesting index fields only (no mailing addresses) reduces the risk.
- Whether the 2024 NJ amendments authorize a commercial surcharge (as distinct from the § 5(c)/(d) special service charges) was not confirmed.

## 6. Response deadline

### Takeaway
Deadlines range from 3 business days (VT) to 10 business days (MA, RI). NY, ME and NH only require an acknowledgment or estimate, which permits long extensions.

### Cited Findings
- NJ: 7 business days standard; 14 business days for verified commercial-purpose requests — [Marshall Dennehey](https://marshalldennehey.com/articles/changes-nj%E2%80%99s-open-public-records-act-and-implications-siu)
- PA: a recorder may demand prepayment before producing records (§ 1307(h)) — [Fayette prepayment letter](https://fayettecorecorderpa.gov/wp-content/uploads/2026/06/RTK-Dowling-dated-June-9-2026-Prepayment-requirement-2.pdf)

### Gaps
**[background, unverified]** for each of the following:
- PA: 5 business days, plus up to 30 calendar days of extension (§ 67.902).
- NY: acknowledge within 5 business days, with an approximate grant date that must be "reasonable" (§ 89(3)(a)).
- MA: 10 business days; agencies may petition for more time.
- RI: 10 business days, extendable by 20 for good cause.
- CT: 4 business days for inspection requests (§ 1-206); for copies, "promptly".
- VT: 3 business days, extendable by 10.
- NH: 5 business days to produce, deny, or acknowledge with a time estimate.
- ME: acknowledge within 5 working days and give a good-faith estimate.

## 7. Recorder-specific bulk/subscription statutes and prices

### Takeaway
ME has the clearest registry bulk statute. It set 5¢/image for downloads of 1,000 or more images, and a version effective January 1, 2026 reportedly makes bulk downloads available only where a county voluntarily agrees in writing. That is a major negative for ME requests. PA has an OOR-approved "enhanced electronic access" fee mechanism, and courts there have approved market pricing for bulk property data.

### Cited Findings
- ME: in MacImage of Maine, LLC v. Androscoggin County, 2012 ME 44, 40 A.3d 975, the Law Court unanimously reversed the trial court. It upheld the Legislature's fee schedule for bulk copies of registry records against MacImage's FOAA challenge, ruling for six counties (Androscoggin, Aroostook, Cumberland, Knox, Penobscot, York) — [Justia 2012 ME 44](https://law.justia.com/cases/maine/supreme-court/2012/2012-me-44.html); [Bangor Daily News](https://www.bangordailynews.com/2012/03/27/bangor/maine-supreme-court-upholds-law-setting-copying-fees-for-counties/)
- ME: 33 M.R.S. § 751(14-D), in its 2013 version, set 5¢ per image or electronic abstract for downloads of 1,000 or more consecutive images. A version effective January 1, 2026 reportedly applies only where the county voluntarily agrees to provide downloads under a written agreement — [33 M.R.S. § 751](https://www.mainelegislature.org/legis/statutes/33/title33sec751.pdf) (search extract; full text not read)
- ME: MacImage's owner said even 5¢/page made a statewide database cost-prohibitive — [BDN 2012](https://www.bangordailynews.com/2012/04/27/news/deeds-website-owner-says-court-ruling-makes-macimage-business-plan-unviable/)
- ME: earlier trial-level FOAA wins against Hancock and other counties (2009) preceded the 2012 reversal — [MacImage v. Hancock County](https://law.justia.com/cases/maine/superior-court/2009/cumcv-08-589.html); [BDN 2011](https://www.bangordailynews.com/2011/02/24/news/maine-high-court-rules-against-counties-in-freedom-of-access-suit/)
- PA: § 1307(e) allows user fees for "enhanced electronic access". The fees must be reasonable and pre-approved by the OOR, and must supplement, not replace, RTKL access — [OOR fee structure](https://www.openrecords.pa.gov/RTKL/FeeStructure.cfm); [OOR § 1307(e) application](https://www.openrecords.pa.gov/Documents/RTKL/Section_1307e_Fee_Application.pdf)
- PRIA (the recorders' trade body) notes that pricing and terms for bulk sale of electronic land records are "less established" — [PRIA Bulk Records paper (July 2025)](https://pria.us/wp-content/uploads/Bulk-Records_STYLE_07_2025_CLEAN-1.pdf)

### Inferences
- In PA, a county's online subscription (often Landex, Infocon or similar vendors) is the § 1307(e) channel. Under the OOR's own conditions, that channel cannot replace a standard RTKL request for the same records. Leverage this in requests.
- The ME text "only where the county voluntarily agrees" (if accurate) means a FOAA request for a bulk index download can be refused or priced by contract.

### Gaps
- Actual price lists (e.g., per-county PA subscription prices, NY county clerk bulk data prices, NJ county clerk bulk image/index sales) were not retrieved.
- The exact text of the 2026 Maine amendment and its session law were not read.
- **[background, unverified]** NY Real Property Law / County Law provisions on county clerk electronic access contracts.

## 8. Known free statewide or county bulk land-records data

### Takeaway
NYC ACRIS is the only confirmed free bulk recorder index in the region (NYC Open Data, already ingested by this project). MA has a statewide search portal, masslandrecords.com, but no bulk download was found.

### Cited Findings
- MA: there are 21 registries of deeds, each maintaining its own online database. masslandrecords.com is an official Secretary of the Commonwealth site. No bulk-purchase page was found — [Forbes Library guide](https://forbeslibrary.org/databases/massachusetts-registry-of-deeds/); [mass.gov recorders page](https://www.mass.gov/info-details/viewing-and-requesting-recorders-office-records)
- MA: the Trial Court's no-bulk-distribution policy applies to court records, not registry records — [Trial Court Rule 4](https://mass.gov/trial-court-rules/uniform-rules-on-public-access-to-court-records-rule-4-requests-for-bulk-data)
- VT: the land records standard calls for electronic land records portals with published access rules — [VT Land Records Standard](https://outside.vermont.gov/dept/sos/VSARA/Manage/Governance/Standards/Vermont_LandRecordsStandard.pdf)

### Inferences
- MA registries share state IT, so one c. 66 request to the Secretary of the Commonwealth (or to each registry's Records Access Officer, e.g., recordsaccessofficer@barnstabledeeds.org) for a CSV export of the index is the highest-leverage request in New England.

### Gaps
- **[background, unverified]** NJ Division of Taxation SR-1A sales data and MOD-IV tax lists. These carry deed date, book/page, consideration and grantor/grantee from recorded deeds, and some counties or the state distribute them free or cheaply. The search for this failed and needs targeted verification. It could be a strong NJ substitute for a county clerk index.
- **[background, unverified]** PA: Philadelphia's Real Estate Transfer Tax dataset (OpenDataPhilly/Carto) is free and already ingested by this project (task #7). Allegheny County publishes property sales via WPRDC.
- **[background, unverified]** CT: the Office of Policy and Management publishes a statewide "Real Estate Sales" dataset (data.ct.gov) with town, date, sale amount and address, but no grantor/grantee names.
- **[background, unverified]** NY State ORPS/Tax and Finance property sales (RP-5217) data. Grantor/grantee names may not be included.
- ME, NH, RI: no free statewide bulk data found.

## 9. Scores (1–5: free/near-free machine-readable recorder index via records request)

### Takeaway
The best targets are NY counties outside NYC (score 4), MA, CT and NJ (3–4, with NJ subject to fee-statute risk). PA is 2–3 (per-page and market-pricing risk). VT is 2 (a strong format statute, but about 246 town requests). RI and NH are 2. ME is 1–2 (bulk statute now voluntary/contractual).

### Cited Findings
Scores are inferences built on the findings cited above:
- **NY (excluding NYC, which is already free via ACRIS): 4.** FOIL treats a computer extraction as retrieval. Data Tree puts the burden on the clerk and confirms land records are subject to FOIL. COOG limits fees to actual cost, with staff time only beyond 2 hours. Risks: CPLR 8019 per-page claims and § 89(2)(b)(iii) name-list denials — [Leagle](https://www.leagle.com/decision/20074639ny3d4541422); [COOG](https://docsopengovernment.dos.ny.gov/coog/ftext/f19722.htm)
- **MA: 3.** State-run registries on shared IT and a cost-capped c. 66 regime with free hours make one export plausible. No bulk precedent was found, and registry fee statutes are a risk — [Mass. SOC](https://www.sec.state.ma.us/divisions/public-records/public-records-law/public-records-request.htm)
- **CT: 3.** The cost-capped § 1-212 regime and the FIC's 1997 signal against § 7-34a per-page fees for electronic indexes are favorable. But land records sit with 169 town clerks, and many indexes are hosted by vendors — [FIC 1996-558](https://state.ct.us/foi/1997FD/19970625/1996-558.htm)
- **NJ: 3.** There are 21 county clerks, and OPRA allows commercial requesters (with certification and 14 days). The "except as otherwise provided by law" carve-out for clerk fee statutes and the special IT-programming charges are risks — [Marshall Dennehey](https://marshalldennehey.com/articles/changes-nj%E2%80%99s-open-public-records-act-and-implications-siu)
- **PA: 2.** The RTKL bars search fees, but recorders invoke the $0.50/page § 21051 fee and § 1307(e) subscriptions, and the Commonwealth Court upheld market pricing for bulk property data in 2026 — [OOR](https://www.openrecords.pa.gov/RTKL/FeeStructure.cfm); [Bloomberg Law](https://news.bloomberglaw.com/daily-tax-report/zillow-denied-pennsylvania-fee-refund-for-access-to-tax-data)
- **VT: 2.** § 316 requires the standard electronic format at the requester's choice. But land records are held by about 246 town clerks, often on vendor systems with $1/page habits — [FindLaw § 316](https://codes.findlaw.com/vt/title-1-general-provisions/vt-st-tit-1-sect-316/)
- **RI: 2.** 39 municipal clerks; $15/hour after the first hour; waivers only by a court — [RI § 38-2-4](https://webserver.rilegislature.gov/Statutes/TITLE38/38-2/38-2-4.htm)
- **NH: 2.** 10 county registries and a cost-only fee model (unverified). The "citizen" ambiguity and weak extract language are risks — [MuckRock NH](https://muckrock.com/place/united-states-of-america/new-hampshire)
- **ME: 1.** The Law Court upheld the legislated registry bulk fees, and per the 2026 text bulk downloads are only by voluntary written agreement — [2012 ME 44](https://law.justia.com/cases/maine/supreme-court/2012/2012-me-44.html); [33 M.R.S. § 751](https://www.mainelegislature.org/legis/statutes/33/title33sec751.pdf)

### Inferences
- Request order by value per request: MA (one state system), then the NY counties, then the NJ counties, then the PA counties. The town-level states (CT, VT, RI) only make sense with a vendor-level approach, such as asking the index host for a multi-town export, which is not a public-records request.

### Gaps
- Scores are provisional. They rest partly on **[background, unverified]** statute text, because WebFetch could not reach any official legislature site.
- Before finalizing scores, verify: NY POL § 89(3)(a); CT § 1-211; MA c. 66 § 6A and § 10; NJ 47:1A-5; PA § 705; the 2026 ME amendment; NH RSA 91-A:4.
