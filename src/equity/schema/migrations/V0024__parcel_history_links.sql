-- Parcel id history. A parcel renumbered (renumbered_to), split into new lots (split_into, one
-- row per new lot) or merged into another (merged_into): from_parcel_uid is the old id,
-- to_parcel_uid the current one. Matching follows these links so a lien or a record that
-- names an old parcel id reaches today's parcel (equity.matching.resolve).
CREATE TABLE parcel_link_v24 (
    row_id           VARCHAR PRIMARY KEY,
    from_parcel_uid  VARCHAR NOT NULL CHECK (from_parcel_uid <> ''),
    to_parcel_uid    VARCHAR NOT NULL CHECK (to_parcel_uid <> ''),
    link_type        VARCHAR NOT NULL CHECK (link_type IN (
                         'condo_unit_of', 'renumbered_to', 'split_into', 'merged_into')),
    detail           VARCHAR,
    -- provenance (required on every fact table; checked by quality.gates)
    source_record_id VARCHAR NOT NULL CHECK (source_record_id <> ''),
    source_id        VARCHAR NOT NULL CHECK (source_id <> ''),
    jurisdiction     VARCHAR NOT NULL CHECK (jurisdiction <> ''),
    record_key       VARCHAR NOT NULL CHECK (record_key <> ''),
    source_uri       VARCHAR NOT NULL CHECK (source_uri <> ''),
    retrieved_at     TIMESTAMPTZ NOT NULL,
    content_sha256   VARCHAR NOT NULL CHECK (length(content_sha256) = 64),
    fact_hash        VARCHAR,
    -- transaction time
    ingested_at      TIMESTAMPTZ NOT NULL,
    superseded_at    TIMESTAMPTZ,
    CHECK (superseded_at IS NULL OR superseded_at >= ingested_at)
);

INSERT INTO parcel_link_v24 SELECT * FROM parcel_link;
DROP TABLE parcel_link;
ALTER TABLE parcel_link_v24 RENAME TO parcel_link;
