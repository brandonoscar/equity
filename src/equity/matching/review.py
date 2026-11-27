"""The name + ZIP review queue: evidence for each debtor matched only by person_name_zip.

Nothing here accepts or rejects a match. Each candidate gets fixed, re-derivable labels so a
person (or a rule the project owner approves later) can work the queue in order:

  category   middle_initial  matched by person_name_initial_address: same address, a middle
                             initial on one side only (a parent and child can share both)
             nickname        matched by person_nickname_address: same address, a nickname
                             on one side (BOB / ROBERT)
             one_letter      matched by person_name_typo_address: same address, one name
                             word one letter off (SMITH / SMIHT)
             spelling_only   street lines agree once suffix and direction words are
                             spelled one way (ST/STREET, N/NORTH, ...), ordinals dropped (88TH
                             = 88) and punctuation dropped;
                             none now that address keys use that spelling (kept as a check)
             same_number     same house number, different street
             po_box          the debtor's address is a PO box (says nothing about property)
             at_owner_occupied_property  the debtor lives at a lot no source names an owner
                             for, and the roll's homeowner exemption says an owner lives there
             at_property     the debtor lives at a nameless lot (owner or tenant: unknown)
             at_company_mailing  a company owner's tax bill goes to the debtor's address
             different       anything else
  owners_with_name_in_zip    owner parties in that ZIP with the same name key (1 = unique)
  rule_id                    the review rule that proposed the pair

Output review_queue.parquet in the state's derived folder (git-ignored: it names people) and
counts in summary.json under "review".
"""

from __future__ import annotations

import duckdb

# One spelling for street suffix and direction words (USPS Publication 28 abbreviations).
# A numbered street also loses its ordinal suffix: 88TH = 88, 1ST = 1 (approved by the project
# owner 2026-11-27; NY: 1,318 review pairs, 1,300 confirmed on one street segment by the Census
# geocoder, docs/address_spelling_proposal.md).
WORDS = {
    "STREET": "ST", "STR": "ST", "AVENUE": "AVE", "AV": "AVE", "ROAD": "RD", "DRIVE": "DR",
    "PLACE": "PL", "BOULEVARD": "BLVD", "LANE": "LN", "COURT": "CT", "TERRACE": "TER",
    "PARKWAY": "PKWY", "HIGHWAY": "HWY", "CIRCLE": "CIR", "SQUARE": "SQ", "TURNPIKE": "TPKE",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW",
    "APARTMENT": "APT", "FLOOR": "FL", "SUITE": "STE",
}  # fmt: skip


def street_macro(con: duckdb.DuckDBPyConnection) -> None:
    pairs = ", ".join(f"'{k}': '{v}'" for k, v in sorted(WORDS.items()))
    con.execute(f"""
        CREATE OR REPLACE MACRO street_norm(s) AS array_to_string(list_transform(
            list_filter(string_split(trim(regexp_replace(upper(coalesce(s, '')),
                '[^A-Z0-9 ]+', ' ', 'g')), ' '), lambda w: w <> ''),
            lambda w: coalesce(MAP {{{pairs}}}[w],
                               regexp_replace(w, '^([0-9]+)(ST|ND|RD|TH)$', '\\1'))), ' ');
        CREATE OR REPLACE MACRO house_no(s) AS regexp_extract(upper(coalesce(s, '')),
            '^\\s*([0-9]+[A-Z]?)\\b', 1);
    """)


SQL = """
CREATE TEMP TABLE review_queue AS
WITH q AS (
    SELECT m.debtor_party_id, m.instrument_uid, m.owner_party_id, m.parcel_uid, m.key, m.rule_id
    FROM matches m
    WHERE m.decision = 'review'
      AND m.debtor_party_id NOT IN (SELECT debtor_party_id FROM matches WHERE decision = 'auto')
), d AS (
    SELECT DISTINCT party_id, raw_name, split_part(addr_key, '|', 1) AS line1, zip5,
           instrument_uid, source_id, doc_type, recorded_on, principal_amount, released
    FROM debtors
), o AS (
    SELECT DISTINCT party_id, parcel_uid, raw_name, split_part(mail_key, '|', 1) AS mail_line1,
           mail_zip, split_part(situs_key, '|', 1) AS situs_line1, situs_zip
    FROM owners
), same_name AS (
    SELECT name_key, zip, count(DISTINCT party_id) AS n FROM (
        SELECT name_key, mail_zip AS zip, party_id FROM owners WHERE mail_zip IS NOT NULL
        UNION SELECT name_key, situs_zip, party_id FROM owners WHERE situs_zip IS NOT NULL)
    GROUP BY ALL
)
SELECT q.debtor_party_id, d.raw_name AS debtor_name, d.line1 AS debtor_line1,
       d.zip5 AS debtor_zip, d.source_id, d.doc_type, d.recorded_on, d.principal_amount,
       d.released, q.instrument_uid, q.owner_party_id, o.raw_name AS owner_name,
       o.mail_line1, o.mail_zip, o.situs_line1, o.situs_zip, q.parcel_uid, v.value AS parcel_value,
       CASE
         WHEN q.rule_id = 'person_name_initial_address' THEN 'middle_initial'
         WHEN q.rule_id = 'person_nickname_address' THEN 'nickname'
         WHEN q.rule_id = 'person_name_typo_address' THEN 'one_letter'
         WHEN q.rule_id = 'person_at_owner_occupied_property' THEN 'at_owner_occupied_property'
         WHEN q.rule_id = 'person_at_property' THEN 'at_property'
         WHEN q.rule_id = 'person_at_org_owner_mailing' THEN 'at_company_mailing'
         WHEN regexp_matches(street_norm(d.line1), '^(P ?O ?BOX|POB|BOX) ')
           THEN 'po_box'
         WHEN street_norm(d.line1) <> '' AND street_norm(d.line1)
              IN (street_norm(o.mail_line1), street_norm(o.situs_line1)) THEN 'spelling_only'
         WHEN house_no(d.line1) <> '' AND house_no(d.line1)
              IN (house_no(o.mail_line1), house_no(o.situs_line1)) THEN 'same_number'
         ELSE 'different' END AS category,
       coalesce(sn.n, 0) AS owners_with_name_in_zip, q.rule_id
FROM q
JOIN d ON d.party_id = q.debtor_party_id AND d.instrument_uid = q.instrument_uid
LEFT JOIN o ON o.party_id = q.owner_party_id AND o.parcel_uid = q.parcel_uid
LEFT JOIN parcel_value v ON v.parcel_uid = q.parcel_uid
LEFT JOIN same_name sn ON sn.name_key = q.key AND sn.zip = d.zip5;
"""


def build(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SQL)


def summary(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    cats = dict(con.execute(
        "SELECT category, count(DISTINCT debtor_party_id) FROM review_queue GROUP BY 1 ORDER BY 1"
    ).fetchall())  # fmt: skip
    row = con.execute(
        "SELECT count(DISTINCT debtor_party_id) FILTER (WHERE owners_with_name_in_zip = 1), "
        "count(DISTINCT debtor_party_id) FROM review_queue"
    ).fetchone()
    return {
        "debtors": row[1] if row else 0,
        "debtors_by_category": cats,
        "debtors_name_unique_in_zip": row[0] if row else 0,
    }
