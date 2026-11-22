-- One parcel id that stands for another. condo_unit_of: a condominium unit lot (as recorders
-- index it) belongs to the condominium's billing lot (as the assessment roll carries it), so
-- documents recorded against a unit can be joined to the parcel that has the owner and value.
CREATE TABLE parcel_link (
    row_id           VARCHAR PRIMARY KEY,
    from_parcel_uid  VARCHAR NOT NULL CHECK (from_parcel_uid <> ''),
    to_parcel_uid    VARCHAR NOT NULL CHECK (to_parcel_uid <> ''),
    link_type        VARCHAR NOT NULL CHECK (link_type IN ('condo_unit_of')),
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
