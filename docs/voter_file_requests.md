# Voter file request kit

How to obtain the statewide voter file in the eight jurisdictions where the research found **no use restriction** for an internal, non-redistributed records database: Alaska, Arkansas, Colorado, the District of Columbia, Florida, Michigan, Mississippi and Wisconsin. North Carolina (free download) is already loaded, and Ohio's adapter reads a hand-saved county file. The legal basis for each state is in `reports/Voter file access by state.md` and `research_notes/Voter file access by state/`. This is legal research for internal planning, not legal advice. Recheck each statute and form right before each request.

None of these eight offers a public download that needs no login or payment. Each file has to be requested, and the adapters in `src/equity/adapters/voter_files.py` read the delivery from disk. Nothing below was submitted or paid. Forms and pages were read on 2026-11-25 unless noted.

## How every request works

1. **Requester block.** Use the company's name, business mailing address, business phone and a business e-mail. Use a person's name only where the form asks for a contact person.
2. **Purpose.** Most of these forms have no purpose field (CO, DC, FL, MI, MS, WI). Do not add one where none is asked. Where the request is free text (an e-mail, or "Other requested information" or "Description of request"), describe the file only. If an office asks what the file is for, answer with this statement, which is accurate for this project:

   > The file will be used internally to maintain a reference database that matches public records (property, court and business filings) to the correct individuals. It will not be published, sold, shared or redistributed, and it will not be used for solicitation, mailing lists, telephone or e-mail contact, or political purposes.

3. **Ask for registration data only.** Ask for the statewide registration file without voting history. The adapters never read history, so requesting it only adds cost and size.
4. **Drop the delivery as received** into `data/manual/<source_id>/` (gitignored, never committed). A zip, a folder, a `.gz` or a plain file all work. Voting-history and code-table files may stay in the folder, because the adapters skip them. If more than one statewide file is present, the newest (by modification time) is read. For Florida, every county file is read and the newest month of each county wins.
5. **Load.** Run `uv run python -m equity.ingest <source_id> --all` once the adapter is registered (see "After delivery" below). A statewide file is split once into per-county extracts under `data/work/<source_id>/`. Allow disk space for those extracts, about the size of the delivery compressed.

## Summary

| State | Route | Cost | Delivery | Source id / drop folder |
|---|---|---|---|---|
| Alaska | Ask the Division of Elections (e-mail, phone or mail); no online form | Fee set by the director: about $20 (EAC, unverified) | Not stated; ask for CSV | `ak.doe.voter_file` |
| Arkansas | E-mail the Elections Division for the current Data Request Form | Reportedly no cost | Reportedly a Dropbox link | `ar.sos.voter_file` |
| Colorado | Elections Data Request Form, by mail with a check | $50 per report (EX-003), or $1,000 for the election-cycle subscription | Disc by first-class mail within 72 hours; download for subscribers | `co.sos.voter_file` |
| District of Columbia | BOE Data Request Form, online or by e-mail | Free | Excel by secure link, within 15 business days | `dc.boe.voter_file` |
| Florida | E-mail or mail the Division of Elections for the monthly voter extract | Free (one request a year covers every monthly disk) | Disk by mail or pickup; not by e-mail or online | `fl.dos.voter_file` |
| Michigan | QVF Data Request Form, by FOIA e-mail or mail | FOIA fee estimate; EAC lists about $23 (unverified) | CSV or fixed-length ASCII on an encrypted flash drive, by FTP, or for pickup | `mi.sos.voter_file` |
| Mississippi | Weekly Distribution Program sign-up, or a public records request | Free weekly; at actual cost by PRR | E-mailed ShareFile link to a CSV, weekly | `ms.sos.voter_file` |
| Wisconsin | Badger Voters account (My Wisconsin ID with MFA) | $25 + $5 per 1,000 records, capped at $12,500 (the statewide list hits the cap) | CSV download (zipped when large) from the account, kept for 6 months | `wi.wec.voter_file` |

Cheapest order: DC, Florida, Mississippi (weekly), Arkansas and Alaska cost nothing or nearly nothing. Colorado ($50) and Michigan (a FOIA fee) are small. Wisconsin costs about $12,500, so it needs a decision first.

## Alaska: Division of Elections

- **Legal basis.** AS 15.07.127: "any person may obtain a copy of the list ... by applying to the director and paying to the state treasury a fee as determined by the director." AS 15.07.195(a) makes age or date of birth, SSN, driver's license number, voter identification number, place of birth and signature confidential. It has no use restriction. ([AS 15.07.127](https://www.akleg.gov/basis/statutes.asp?media=print&secStart=15.07.127&secEnd=15.07.127); [AS 15.07.195](https://www.akleg.gov/basis/statutes.asp?media=print&secStart=15.07.195&secEnd=15.07.195))
- **Route.** There is no online form. The Research page says: "Voter lists are available for purchase. To purchase a list, or for other requests, contact any divisional office for assistance." ([Division of Elections, Research](https://www.elections.alaska.gov/research/))
- **Contact.** Director's Office, Division of Elections, PO Box 110017, Juneau, AK 99811-0017. Phone (907) 465-4611; toll-free (866) 952-8683. ([Contact page](https://www.elections.alaska.gov/contact-information/))
- **What to ask for.** "A copy of the statewide voter list in electronic format (CSV), with residence and mailing addresses and party, without voting history. Please tell us the fee and how to pay it." The statute's own wording is "an electronic format containing both residence and mailing addresses of voters".
- **Fee.** Set by the director. The EAC chart lists about $20 and a news report said $21; neither is verified. A 2017–18 bill (SB 192) proposed $1,500, but its enactment was not confirmed. Ask for the fee before paying.
- **Eligibility.** None ("any person").
- **Delivery and time.** Not published. Ask for CSV by e-mail or secure download.
- **Drop.** `data/manual/ak.doe.voter_file/<file as delivered>.csv` (or `.zip`). The file should have a header with `LAST_NAME`, `FIRST_NAME`, `MIDDLE_NAME`, `SUFFIX_NAME`, `ASCENSION`, `REG_DATE`, `RESIDENCE_ADDRESS`, `RESIDENCE_CITY`, `RESIDENCE_ZIP`, `MAILING_ADDRESS1`–`3`, `MAILING_CITY`, `MAILING_STATE`, `MAILING_ZIP`, `PARTY` and `STATUS`. Alaska publishes no layout; these columns come from the [Voteshield reggie Alaska config](https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/alaska.yaml). The file has no borough column, so it loads as one statewide partition (`county=02`).

## Arkansas: Secretary of State, Elections Division

- **Legal basis.** The SoS says "there are currently no state laws restricting use of the data that the SOS releases, but Federal and State laws restrict some fields on the VR record." This comes from the Data Request Form and FAQ 35, both seen only as search snippets. The form URL returned 404 on 2026-11-25. A.C.A. § 7-5-109 was not read from primary text. This is the weakest-sourced verdict, so confirm the current form's terms before relying on it. ([AR SoS FAQ 35](https://www.sos.arkansas.gov/frequently-asked-questions/35); old form [Data_Request_Form_Updated.pdf](https://www.sos.arkansas.gov/uploads/Data_Request_Form_Updated.pdf) (404))
- **Route.** E-mail the Elections Division and ask for the current Data Request Form. The old form had sections A and B and offered three statewide files: VR (registration), VH (history, which has no names) and VRVH (both).
- **Contact.** voterservices@sos.arkansas.gov; 1-800-247-3312 (from search results; confirm on the SoS site). Secretary of State, 1401 W. Capitol Ave., Little Rock, AR 72201.
- **What to fill in.** Request the **statewide VR file** only, not VH or VRVH. Use the requester block from step 1. If the form has a use statement, read it before signing.
- **Fee.** The current form reportedly says "no cost for data request". A 2017 letter cited $2.50 per file. County clerks charge reproduction cost under § 7-5-109.
- **Eligibility.** None found.
- **Delivery.** Reportedly a Dropbox link.
- **Drop.** `data/manual/ar.sos.voter_file/` holding the zip as delivered, or `VR.csv` itself. `VH.csv` is skipped. VR.csv is a CSV with a header: `County, VoterID, ..., date_of_birth, date_of_registration, TEXT_NAME_LAST, TEXT_NAME_FIRST, TEXT_NAME_MIDDLE, CDE_NAME_SUFFIX`, residential street parts, `TEXT_RES_CITY`, `CDE_RES_STATE`, `TEXT_RES_ZIP5`, `TEXT_MAIL_ADDRESS1`–`4`, `TEXT_MAIL_ZIP5` and `CDE_PARTY`. No official layout is online; the columns come from the [reggie Arkansas config](https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/arkansas.yaml).

## Colorado: Secretary of State, Elections Division

- **Legal basis.** C.R.S. § 1-2-227(1)(a) makes registration records public. § 24-72-204(8) withholds only the signature, SSN, month and day of birth, and ID. The SoS FAQ says public data is provided "without regard to how these people might use the information." ([SoS FAQ](https://www.coloradosos.gov/pubs/elections/FAQs/VoterRegistrationData.html))
- **Form.** Elections Data Request Form, revised November 2024. It has no purpose field and no certification. ([dataRequests.pdf](https://www.coloradosos.gov/pubs/elections/forms/dataRequests.pdf))
- **What to fill in.** Requestor name, company name, mailing address, phone and e-mail. Under "Public Elections Data Request on Data Disc for $50.00 per report", tick **Statewide Registered Voter List (EX-003)** and nothing else. Set the number of copies to 1, enclose $50, and sign.
- **Fee.** $50 per report, by check or money order payable to the Colorado Secretary of State. Alternatively, the Election Cycle Subscription Service costs $1,000 for the 2025–2026 cycle and gives download access to EX-003, updated weekly. Buy the $50 disc unless weekly refreshes are needed. ([Fee schedule](https://coloradosos.gov/pubs/info_center/fees/elections.html))
- **Send to.** Colorado Secretary of State, Elections Division, 1700 Broadway, Suite 550, Denver, CO 80290. Questions: (303) 894-2200, elections@coloradosos.gov.
- **Delivery and time.** "Requests will be returned via first class mail within 72 hours depending on request." For FedEx, USPS Express or UPS, include a prepaid mailer.
- **Eligibility.** None ("any person"). Confidential voters (§ 24-72-204(3.5)) and Address Confidentiality Program participants are not in the file.
- **Drop.** Copy the disc contents into `data/manual/co.sos.voter_file/`: the zip, or the EX-003 text or CSV part files. EX-002 history and split-district reports are skipped. The SoS publishes no layout. The adapter reads the EX-003 headers (`VOTER_ID, COUNTY, LAST_NAME, FIRST_NAME, MIDDLE_NAME, NAME_SUFFIX, RESIDENTIAL_ADDRESS, RESIDENTIAL_CITY, RESIDENTIAL_STATE, RESIDENTIAL_ZIP_CODE, MAILING_ADDRESS_1–3, MAILING_CITY/STATE/ZIP_CODE, REGISTRATION_DATE, STATUS, BIRTH_YEAR, PARTY ...`; from the [reggie Colorado config](https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/colorado.yaml)) and the short SCORE export names that counties use (`RES_ADDRESS, MAIL_ADDR1, YOB, COUNTY_REGN_DATE ...`). It detects the delimiter (comma, pipe or tab).
- **Note.** Boulder County posts its own county voter file (VR-011B, pipe-delimited, updated monthly) free with no login ([Boulder County data access](https://bouldercounty.gov/elections/maps-and-data/data-access/)). It is loaded as `co.boulder.voter_file` (`BoulderCountyVoterFile`), which downloads the zip directly (the file host has no robots.txt; bouldercounty.gov allows all paths, checked 2026-11-25) and reads it with the Colorado layout. It covers one county of 64. The statewide adapter also reads that layout through `path=`.

## District of Columbia: Board of Elections

- **Legal basis.** D.C. Code §§ 1-1001.05 and 1-1001.07 have no use restriction. Requests are handled on the D.C. FOIA timeline (§ 2-532(c)). ([§ 1-1001.07](https://code.dccouncil.gov/us/dc/council/code/sections/1-1001.07))
- **Form.** "Request for Voter Registration Data, Maps or Petition Signatures", revised 8/17/26. Use the [online form](https://vr.dcboe.org/230363516728053), or fill in the [PDF](https://dcboe.org/getContentAsset/6e2e6a71-294c-43a5-8bb1-02c151372f7b/5ebbd046-860b-4ee1-81c8-43d0e3bc446e/Data-Request-Form-08172026.pdf?language=en) and e-mail it. The form has no purpose field and no use terms.
- **What to fill in.** Requestor's name or group, street address, city/state/zip, day phone, contact person, e-mail, date and signature. Tick "E-mail or Secure Link of Voter Registration Data – Microsoft Excel (No Charge)" and "Voter reg. list **without** voter history". Under "Other Requested Information", write: "The entire District-wide voter registration list (all wards), by secure link." Initial the FOIA and returned-check line.
- **Send to.** Submit online, or e-mail to voterservices@dcboe.org. Office: 1015 Half Street SE, Suite 750, Washington, DC 20003; (202) 727-2525.
- **Fee.** None.
- **Delivery and time.** "The entire voter registration list can only be obtained through a secure link." It arrives as Excel, within up to 15 business days.
- **Eligibility.** None.
- **Drop.** `data/manual/dc.boe.voter_file/<workbook as delivered>.xlsx` (a CSV export also works). The adapter reads the largest worksheet, with the header on row 1: `REGISTERED, LASTNAME, FIRSTNAME, MIDDLE, SUFFIX, STATUS, PARTY, RES_HOUSE, RES_FRAC, RES_APT, RES STREET, RES_CITY, RES_STATE, RES_ZIP, RES_ZIP4, PRECINCT, WARD, ...`. DCBOE publishes no layout; these columns come from the [reggie DC config](https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/dc.yaml). The export has no voter ID. A `VOTER ID` column is used if present; otherwise the record key is a hash of name, registration date and residence. Loads as one partition (`county=11001`).

## Florida: Department of State, Division of Elections

- **Legal basis.** The old § 98.095 oath and use limit is absent from every official compilation from 2005 to 2026. Chapters 97–98 contain no use limit. § 97.0585 and § 119.071 exemptions are removed before release. ([Fla. Stat. ch. 98 (2026)](https://www.flsenate.gov/Laws/Statutes/2026/Chapter98/All))
- **Route.** There is no form. The Voter Extract Request page asks for "contact information and either a phone number or an email address, and a mailing address". The extract "IS NOT available by email or online". "A one-time request may be made each year to receive all monthly extract disks to be issued for the calendar year." ([Voter Extract Request](https://dos.fl.gov/elections/data-statistics/voter-registration-statistics/voter-extract-request/), as read by the 2026-11-25 verification pass. From this project's network, dos.fl.gov and files.floridados.gov now answer with a Cloudflare challenge, so this page was not re-read and nothing tried to get past the block.)
- **Contact.** VoterExtract@dos.fl.gov ("Voter Extract File CD" in the [DOE Subject Matter Contact Directory, 2025-06-16](https://soe.dos.state.fl.us/pdf/DOE%20-%20Subject%20Matter%20Contact%20Directory%20-%2020250616.pdf)). Mail: Florida Division of Elections, R.A. Gray Building, 500 South Bronough Street, Tallahassee, FL 32399-0250; (850) 245-6200.
- **What to send.** "Please send the statewide voter extract disk (voter registration files) for each month of calendar year 2027 under the one-time annual request, starting with the next available month, to: [company name, mailing address]. Contact: [name], [phone or e-mail]." Voting history comes on the same disk; the adapter ignores it.
- **Fee.** Free for the one annual request. Other requests are "processed as a public records request and subject to administrative fees".
- **Timing.** The disk is monthly. According to the layout documents, as summarized by search results and not re-read, a request has to arrive at least 24 hours before the scheduled availability date, or it rolls to the next month.
- **Eligibility.** None. There is no oath or purpose statement.
- **Format.** 67 county registration files `CCC_YYYYMMDD.txt` and 67 history files `CCC_H_YYYYMMDD.txt`, all tab-delimited ASCII with no header and 38 fields. Layout: [Voter Extract Disk File Layout, rev. 2025-05-16](https://files.floridados.gov/media/708728/final-voter-extract-disk-file-layout-rev-20250516.pdf). It includes full birth date, phone and e-mail. The adapter keeps the birth date but never phone or e-mail.
- **Drop.** Copy the disk into `data/manual/fl.dos.voter_file/`, either as loose `ALA_20270110.txt` ... `WAS_20270110.txt` or as the zip. Later months can go alongside; the newest file per county is read. Each county file is one partition (`county=12001` ... `12133`; Miami-Dade, code `DAD`, is `12086`).
- **Check on arrival.** The three-letter county codes (`ALA ... WAS`) in `FL_COUNTIES` should be checked against the layout's "County Codes" table on the disk. That table could not be fetched here.

## Michigan: Department of State, Bureau of Elections (QVF)

- **Legal basis.** FOIA (MCL 15.231 et seq.). MCL 168.509gg exempts fields only: driver's license or state ID number, month and day of birth, phone, e-mail, signature and the last 4 SSN digits. It does not restrict use. ([MCL 168.509gg](https://www.legislature.mi.gov/Laws/MCL?objectName=mcl-168-509gg))
- **Form.** Qualified Voter File Data Request Form, Rev. 03/26. It asks for no purpose and no use certification. ([FOIA_FORM.pdf](https://www.michigan.gov/-/media/Project/Websites/sos/02lehman/FOIA_FORM.pdf))
- **What to fill in.** Section 1: requester's name and title, organization, mailing address, phone, e-mail, signature and date. Choose a delivery: Mail (encrypted flash drive), FTP (give connection details) or Pick up. Section 2: tick **Entire state** only. Section 3: leave blank, since no history is needed. Section 4: "Statewide voter registration file only (no voter history, no absent voter data)."
- **Send to.** MDOS-FOIA@Michigan.gov, or Michigan Bureau of Elections, PO Box 20126, Lansing, MI 48901-0726.
- **Fee.** A FOIA processing fee under MCL 15.234. MDOS sends an estimate, and a deposit may be required. The EAC lists about $23 (secondary source).
- **Time.** FOIA requires a response within 5 business days, extendable by up to 10 (MCL 15.235(2)). Production of a large file may follow the response.
- **Eligibility.** None ("any person").
- **Format.** The form says both "CSV file format" and "Fixed Length ASCII". The drive includes a file layout plus county, jurisdiction and school code lists. "Electronic files will NOT be transferred via email."
- **Drop.** Copy the drive into `data/manual/mi.sos.voter_file/`: the zip, or the voter file itself (`EntireStateVoters.csv` with a header, or the fixed-width `.lst`). History, code lists and layout files are skipped. The adapter reads the CSV by header and the `.lst` by the positions in `MI_FIXED`. MDOS publishes no layout online; names and positions follow the [reggie Michigan config and preprocessor](https://github.com/Voteshield/reggie/blob/master/reggie/configs/data/michigan.yaml).
- **Check on arrival.** Compare `MI_FIXED` with the "Voter File Layout" on the drive.

## Mississippi: Secretary of State

- **Legal basis.** § 23-15-165(6): copies of voter files "shall be provided to any person in accordance with the Mississippi Public Records Act of 1983 at a cost not to exceed the actual cost of production," excluding SSN, phone, e-mail, and date of birth and age. There is no use clause. ([text as reproduced in 2025 HB 657](https://billstatus.ls.state.ms.us/documents/2025/html/HB/0600-0699/HB0657IN.htm))
- **Route A (free, weekly).** The Statewide Voter File Weekly Distribution Program. Sign up on the [Statewide Voter File Distribution List form](https://app.smartsheet.com/b/form/5c8b666a679c4c148eb513c8981a4962), which is linked from the [program document](https://www.sos.ms.gov/content/documents/about_us/2025%20Voter%20File%20Weekly%20Distribution%20Program.pdf). Each week an e-mail brings a ShareFile link to the statewide voter file and history file. "The Mississippi Secretary of State's Office will not resend or forward any emails", so download each link promptly. The program has no use terms.
- **Route B (public records request).** Use the [PRR form](https://www.sos.ms.gov/content/documents/pol_res/PRR%20Form.pdf) and tick "I would like to request a statewide voter file." Answer "No" to "member of the media", and sign the cost acknowledgement. Send it to publicrecords@sos.ms.gov, by fax to (601) 359-1499, or to 401 Mississippi Street, Jackson, MS 39201. The cost is the actual cost of production, paid before the file is produced.
- **Eligibility.** None.
- **Format.** A CSV with a header. Fields: Mapping Value, first/middle/last name, suffix, residential address and its parts, residence city/state/ZIP, residential county, precinct, mailing address/city/state/ZIP, effective registration date, voter status, date last voted, then district columns.
- **Drop.** `data/manual/ms.sos.voter_file/<statewide voter file>.csv` (or the zip). The history file is skipped. Each county is one partition (for example, Hinds is `28049`).

## Wisconsin: Elections Commission (Badger Voters)

- **Legal basis.** The Badger Voters FAQ says: "Wisconsin law does not place any restrictions on the use of data obtained through this website." The statute itself was not read. ([Badger Voters FAQ](https://badgervoters.wi.gov/faq))
- **Route.** A self-service account at [badgervoters.wi.gov](https://badgervoters.wi.gov). Since 2025-12-22, sign-in goes through **My Wisconsin ID with multi-factor authentication**. The account holder has to create and use the account themselves; the adapters never log in.
- **What to request.** A standard voter list request for **statewide** registered voters (Active, unless inactive records are wanted too). There is no purpose field.
- **Fee.** "$25 base fee ... $5 for every thousand records ... capped at $12,500." The statewide list (millions of records) hits the cap, so expect **$12,500**. Payment is by card, debit or e-check; ACH requests are released only after settlement. No free tier exists for private requesters.
- **Delivery.** After payment, a download link appears under the account's Current Requests. The file is a CSV, zipped when large, and stays downloadable for 6 months.
- **Eligibility.** Anyone with an account.
- **Format.** WEC "Standard Data Elements in a Voter Data File Request" ([PDF](https://badgervoters.wi.gov/img/Voter%20Data%20Request%20Data%20Elements.pdf)): `Voter Reg Number` (an encrypted customer number), `LastName, FirstName, MiddleName, Suffix, PhoneNumber, EmailAddress, Address1` (street and unit), `Address2` (city, state and ZIP), mailing lines, sort fields, `Jurisdiction`, districts, `County`, `Voter Status`, `Voter Status Reason`, `RegistrationDate`, then one column per election. There is no date of birth, age or party. The adapter drops phone, e-mail and every election column.
- **Drop.** `data/manual/wi.wec.voter_file/<download as received>.zip` (or the `.csv`). Each county is one partition (for example, Menominee is `55078`).
- **Decision needed.** At $12,500, Wisconsin is the only expensive file in this set.

## After delivery: fixture and registration

For each state, once its file is in place:

1. Record a 25-row pseudonymized fixture from its smallest partition, through a copy of the record wrapper (`record.py` cannot see unregistered classes):

   ```python
   # scratch record_delivered.py (not committed)
   import sys
   import equity.adapters.registry  # noqa: F401
   from equity.adapters import record
   from equity.adapters.base import REGISTRY, register
   from equity.adapters.voter_files import FloridaVoterFile  # the state being recorded

   for cls in (FloridaVoterFile,):
       if cls not in REGISTRY:
           register(cls)
   raise SystemExit(record.main(sys.argv[1:]))
   ```

   Run it as `uv run python record_delivered.py fl.dos.voter_file county=12077 limit=25`. Suggested small partitions: FL Liberty `12077`, MI Keweenaw `26083`, CO San Juan `08111`, WI Menominee `55078` or Florence `55037`, AR Calhoun `05013`, MS Issaquena `28055`, AK `02`, DC `11001`. The fixture lands in `tests/fixtures/adapters/<source_id>/`. Check it for real names before committing (`tests/test_fixture_privacy.py`).
2. Add the class to `src/equity/adapters/registry.py`, next to `NorthCarolinaVoterFile`:

   ```python
   from equity.adapters.voter_files import (
       AlaskaVoterFile,
       ArkansasVoterFile,
       ColoradoVoterFile,
       DistrictOfColumbiaVoterFile,
       FloridaVoterFile,
       MichiganVoterFile,
       MississippiVoterFile,
       NorthCarolinaVoterFile,
       WisconsinVoterFile,
   )
   ```

   Then list each recorded class in the registry tuple. Only register a class once its fixture exists, because check 7 fails a registered adapter without one.
3. Run `uv run python -m equity.ingest <source_id> --all`.
