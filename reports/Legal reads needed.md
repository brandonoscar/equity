# Legal reads needed (TODO(Brandon))

Sources found during the parcel-owner work (gap-report step 5) whose use depends on a legal
read. Each line says what is blocked and the exact text or statute. Nothing below is loaded
without a restriction tag; the two marked "not loaded" are not in the repo at all.

| Source | Status | What to decide | The text |
|---|---|---|---|
| King County WA Assessor sales file (`EXTR_RPSale.csv`: buyer, seller, price, recording no. on every sale since the 1990s) | **Not loaded** | Whether the project may download it at all. The download page is a disclaimer the requester acknowledges. | "I understand that Washington State law, RCW 42.56.070(9), prohibits the use of lists of individuals for 'commercial purposes' ... may subject me to liability for such commercial use." (info.kingcounty.gov/assessor/DataDownload, read 2026-11-23) |
| Tennessee "Property Boundaries Public Use" (2.14M parcels, owners in 86 counties) | **Not loaded** | Whether a layer that answers without a token may be used although its description restricts it. | "intended for use by state agencies with approved access" (layer description) |
| Montana Cadastral Framework (`mt.statewide.parcels`) | Loaded, tagged `no_mailing_list` | Whether owner names and addresses may be used for outreach. | MCA 2-6-1017: agencies may not distribute or sell a distribution list; "State law does not prevent an individual from compiling a distribution list by examination of records that are otherwise open to public inspection." |
| Washington owner names (`wa.spokane.parcels`; any future WA county) | Loaded, tagged `no_commercial_name_address_lists` | Whether project use is a "commercial purpose" under RCW 42.56.070(9). | RCW 42.56.070(9): agencies may not "give, sell or provide access to lists of individuals requested for commercial purposes." |
| Indiana owner names (`in.marion.parcels`, `config/states/in.yaml`) | Loaded, tagged `no_commercial_name_address_lists` | The same question under Indiana law. | IC 5-14-3-3(f): limits disclosing lists of names and addresses to commercial entities for commercial purposes. |
| Arizona assessor data (`az.maricopa.parcels`, the ADWR county copies, `az.yavapai.parcels`) | Loaded | Whether a commercial-purpose statement is owed. | A.R.S. 39-121.03(D): obtaining public records for a commercial purpose without stating it exposes the requester to treble the fee. |
| Genesee County MI (`mi.genesee.parcels`) | Loaded, tagged `no_redistribution` | Whether showing owner names to users "conveys" the data. | "Requester agrees not to sell, loan or otherwise convey said data to third parties in any digital form." |

Not blocked on law, just not found free: San Diego owner names (the official SanGIS layer drops
them; the copy with names is a private firm's 2025 republication), Clark County NV (the City
of Las Vegas `ADDR_OWN` layer is 867,385 blank rows; the Assessor's roll is sold).
