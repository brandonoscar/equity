# Ontology

The system's ontology is its schema: classes are tables, relations are edge tables, and every
assertion carries provenance and two clocks. It's national by construction: identifiers are
namespaced by FIPS code and court id, and every source is an adapter.

## Classes
| Class | Table | Identity |
|---|---|---|
| Name as printed (mention) | `party` | per source record; never merged |
| Real-world person / organization | `entity` | created only by an evidenced `entity_link` |
| Business registration | `business` | state + SOS id |
| Parcel | `parcel` | `<state+county FIPS>-<normalized local id>` (e.g. `54061-010001000100000000`) |
| Recorded instrument | `instrument` | `<FIPS>:<instrument number>` (or book/page) |
| Court case | `court_case` | `<court id>:<normalized case number>` (e.g. `wvnb:1:25-bk-00040`) |
| Judgment | `judgment` | case + sequence |
| Address | `address` | normalized key |

## Relations (edges)
| Relation | Table | Meaning |
|---|---|---|
| party —refers to→ entity | `entity_link` | rule id, score, evidence; or review queue |
| party —role→ business | `business_role` | member, manager, officer, registered agent |
| party —owns (dated)→ parcel | `ownership_period` | chain of title with valid_from/valid_to |
| party —listed owner→ parcel | `owner_snapshot` | snapshot source, first-observed date |
| party —role→ instrument | `instrument_party` | grantor, grantee, borrower, lender, creditor, debtor… |
| instrument —encumbers→ parcel | `instrument_parcel` | with linkage method + evidence |
| instrument —releases/assigns/modifies→ instrument | `instrument_ref` | a release points at exactly one instrument |
| party —role→ case | `case_party` | plaintiff, defendant, debtor, trustee… |
| judgment —docketed as→ instrument | `judgment.lien_instrument_uid` | |
| parcel —tax status→ certificate | `tax_delinquency_snapshot`, `tax_bill`, `tax_sale_event` | |

## Every assertion carries
- **Provenance:** source, record key, URI, retrieval time, content hash → `source_record` → `fetch_log` → `source`.
- **Valid time:** recorded/filed/effective dates, or intervals.
- **Transaction time:** `ingested_at` / `superseded_at`, so "what did we know on date X" is a query.

## Coverage path to every US parcel
1. Statewide free sources (13 states with owner + value, see `phase0.md` §5): one adapter
   each, mostly an `ArcGISCountyAdapter` subclass or a bulk-file adapter.
2. Partial / owner-less states: statewide boundaries plus county adapters where needed.
3. County-by-county states: buy single counties only when a live file needs them
   ($200–$400 each), each as one adapter.
4. Before step 1 at scale: the set-based loader (see `phase2.md`).
