---
name: ontology-sql
description: Write correct, fast DuckDB SQL over the equity search index and lake - the ontology's tables, ids and keys, the macros (name_key, street_norm, soundex), the views, and the patterns that stay fast on 10M+ rows. Use when asked to write or run a query, count something, or explore the data with SQL.
---

# SQL over the ontology

The ontology is the schema (`docs/ontology.md`): a **party** is a name as printed in one
source record (never merged); identity between parties comes only from evidenced links
(the matcher's rules, or an `entity_link`). Ids are namespaced: `parcel_uid` =
`<5-digit FIPS>-<local id>`, refs = `source_id:party_id`, businesses =
`source_id:business:<sos_id>`.

## Search index tables (`data/search_index.duckdb`, MCP server `equity-search`)

| Table | Key columns | Sorted by |
|---|---|---|
| `sources` | source_id, state, version, rows | source_id |
| `names` | source_id, party_id, raw_name, party_kind, name_key, address_id | name_key |
| `name_words` | word -> name_key, source_id | word |
| `word_sounds` | word -> sound (Soundex) | sound |
| `owners` | source_id, party_id, parcel_uid, observed_on | party_id |
| `parcels` | source_id, parcel_uid, parid_raw, situs_address_id, land_use_desc, zoning | parcel_uid |
| `parcel_values` | latest per parcel: tax_year, appraised_total, assessed_value, homestead | parcel_uid |
| `addresses` | address_id, line1, city, state, zip5, street_key | (none) |
| `instruments` | source_id, instrument_uid, doc_type, doc_type_raw, recorded_on, amount | instrument_uid |
| `instrument_parties` | instrument_uid, party_id, role (debtor, creditor, grantor, ...) | party_id |
| `instrument_parcels` | instrument_uid, parcel_uid, method | parcel_uid |
| `cases`, `case_parties`, `judgments` | case_uid, court_id, role, entered_on, principal | case_uid / party_id |
| `businesses`, `business_roles` | sos_id, name, name_key / party_id, role, title | name_key / party_id |
| `owner_history` | superseded owner snapshots: party_id, parcel_uid, observed_on, superseded_at | parcel_uid |
| `value_history` | every assessment year per parcel | parcel_uid |
| `instrument_refs` | from_uid -> to_uid, ref_type (releases, satisfies_judgment, assigns...) | to_uid |
| `parcel_equity` | value, mortgages, open_mortgages, open_principal, equity_est (recorder counties only) | parcel_uid |
| `m_matches`, `m_debtor_summary`, `m_people`, `m_person_of`, `m_bankruptcy_flags`, `m_transfer_flags`, `m_mortgage_status` | the matcher's output per state (`state` column) | (none) |
| `nicknames` | word -> alt (equivalent given names) | (none) |
| `debtor_owner_candidates` | one row per name and state: debts, debt_amount, parcels, parcel_value, refs | state, name_key |

Views (recompute; slower over MCP): `v_party`, `v_owner_parcels`, `v_party_documents`,
`v_party_cases`, `v_debtor_owner_candidates`.

## Macros

`name_key('Smith, John A.')` -> `'A JOHN SMITH'` (the matcher's key), `street_norm('12 Main
Street')` -> `'12 MAIN ST'`, `soundex('SMYTHE')` -> `'S530'`, `name_flag('CITY OF X')` ->
`'government'` (NULL for a usable name). `names.name_flag` is stored; filter
`name_flag IS NULL` for leads.

## Keep it fast

- Filter on a sorted key with `=` or a short literal `IN (...)` list: `name_key = name_key(?)`,
  `party_id IN ('..','..')`, `parcel_uid = '..'`, `word = '..'`. DuckDB skips row groups by
  min/max; a join against a big table or a `LIKE '%x%'` scans everything.
- Two steps beat one big join: fetch the keys first, then look them up with a literal list.
- Always `LIMIT` exploratory queries; aggregate before joining two big sides (a common name
  multiplies rows).
- doc_type vocabulary: `src/equity/schema/migrations/V0004__instruments.sql`. Debts are
  JUDGMENT_LIEN, ABSTRACT_OF_JUDGMENT, EXECUTION, LIS_PENDENS, MECHANICS_LIEN,
  STATUTORY_LIEN, TAX_LIEN_STATE, TAX_LIEN_FEDERAL, COURT_ORDER; the owing side has role
  debtor, borrower or grantor.

## Examples

```sql
-- everything one name owns, all sources
SELECT o.source_id, o.parcel_uid, v.tax_year, v.appraised_total, v.assessed_value
FROM names n JOIN owners o USING (source_id, party_id)
LEFT JOIN parcel_values v USING (source_id, parcel_uid)
WHERE n.name_key = name_key('Smith, John A');

-- documents recorded against a parcel, newest first
SELECT i.recorded_on, i.doc_type, i.amount, ip.role, n.raw_name
FROM instrument_parcels x JOIN instruments i USING (source_id, instrument_uid)
LEFT JOIN instrument_parties ip USING (source_id, instrument_uid)
LEFT JOIN names n ON n.source_id = ip.source_id AND n.party_id = ip.party_id
WHERE x.parcel_uid = '39035-10114026' ORDER BY i.recorded_on DESC;

-- how common is a name (common names are weak evidence)
SELECT count(*) FROM names WHERE name_key = name_key('John Smith');
```

The full lake (every column, every source) is `equity.lake`'s views in `data/catalog.duckdb`
(`uv run python -m equity.lake catalog` to rebuild); use it only for columns the index lacks.
