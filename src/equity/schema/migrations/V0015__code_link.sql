-- Where each jurisdiction's zoning ordinance, zoning map and planning website live. Links
-- only: the ordinance text stays with its publisher (see docs/sources/zoning-sources.md).
-- publisher is derived from the ordinance URL's host (municode, ecode360, amlegal,
-- codepublishing, or government for anything else).
CREATE TABLE code_link (
    row_id            VARCHAR PRIMARY KEY,
    jurisdiction_uid  VARCHAR NOT NULL CHECK (jurisdiction_uid <> ''),
    jurisdiction_name VARCHAR,
    county_name       VARCHAR,
    ordinance_url     VARCHAR,
    zoning_map_url    VARCHAR,
    website_url       VARCHAR,
    publisher         VARCHAR,
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
