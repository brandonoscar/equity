`county_fips_2020.csv`: U.S. Census Bureau, 2020 national county FIPS codes
(https://www2.census.gov/geo/docs/reference/codes2020/national_county2020.txt), public domain.
Connecticut appears as its 8 legacy counties (the 2022 planning-region codes are not used here).

`nicknames.csv`: given names and their nicknames as `name1,relationship,name2` triplets
(`aaron,has_nickname,ron`), from https://github.com/carltonnorthern/nicknames (Old Dominion
University, Web Science and Digital Libraries Research Group), copied 2026-11-27 (sha256
prefix e6a4e5a55ca5b47a). License: Apache-2.0 as declared in that project's
`python/pyproject.toml` and its PyPI package `nicknames`; the repository itself carries no
LICENSE file. The list was first mined from the Center for African American Research
genealogy page (caagri.org/nicknames.html). Used by `equity.search_index` for nickname
expansion at query time (deterministic lookup, no model).
