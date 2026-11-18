# County parcel sources

Same YAML format as `config/states/` (see that README), one file per county named
`<state+county FIPS>.yaml`, e.g. `13121.yaml` for Fulton County, GA. Use
`county: {constant: "121"}` and `source_id: <st>.<county>.parcels` (e.g. `ga.fulton.parcels`).

Used for states with no free statewide layer: largest counties first.
