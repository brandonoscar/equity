# Statewide parcel sources, one file per state

Each `<st>.yaml` turns a free statewide parcel layer into an adapter
(`src/equity/adapters/state_parcels.py`). No code per state.

```yaml
source_id: ar.statewide.parcels
state: AR
layer_url: https://.../FeatureServer/6      # ArcGIS REST layer
order_by: objectid                          # stable paging key (the OID field)
page_size: 1000                             # <= the layer's maxRecordCount
min_interval_s: 1.0                         # politeness
county:                                     # how to get the county FIPS for each row
  field: countyfips
  format: fips3                             # fips3 | fips5 | int | name | code_map
fields:                                     # canonical -> source field, {const: x} or {year_of: datefield}
  parcel_id: parcelid                       # required
  owner1: ownername
  total_value: totalvalue
  tax_year: {year_of: camadate}
value_basis: "totalvalue = appraised market value; assessvalue = 20% assessed"
terms:
  url: https://...
  summary: "Free; no license text found"
  checked_on: 2026-11-15
  robots_checked_on: 2026-11-15
  cost_model: free
```

Rules: free sources only. Record what the value fields mean in `value_basis` (source semantics,
not legal conclusions). Owner-name and mailing-address fields are pseudonymized automatically
in recorded fixtures.
