-- House price indexes (FHFA HPI): an index value per geography and period, used to roll an
-- old assessed or sale value forward to today. A source kind for price-index publishers.

CREATE TABLE source_v18 (
    source_id         VARCHAR PRIMARY KEY CHECK (source_id <> ''),
    kind              VARCHAR NOT NULL CHECK (kind IN (
                          'recorder', 'assessor', 'parcel_statewide', 'court', 'bankruptcy',
                          'sos', 'tax', 'fixture', 'zoning', 'flood', 'aircraft', 'vessel',
                          'government_sale', 'federal_loan', 'price_index')),
    jurisdiction      VARCHAR NOT NULL CHECK (jurisdiction <> ''),
    access_method     VARCHAR NOT NULL CHECK (access_method IN (
                          'bulk', 'api', 'arcgis', 'feed', 'html', 'manual', 'fixture')),
    base_url          VARCHAR NOT NULL CHECK (base_url <> ''),
    terms_url         VARCHAR,
    terms_summary     VARCHAR NOT NULL CHECK (terms_summary <> ''),
    terms_checked_on  DATE,
    robots_checked_on DATE,
    cost_model        VARCHAR NOT NULL CHECK (cost_model <> '')
);
INSERT INTO source_v18 SELECT * FROM source;
DROP TABLE source;
ALTER TABLE source_v18 RENAME TO source;

CREATE TABLE house_price_index (
    row_id            VARCHAR PRIMARY KEY,
    geo_level         VARCHAR NOT NULL CHECK (geo_level IN ('zip5', 'zip3', 'county', 'state')),
    geo_id            VARCHAR NOT NULL CHECK (geo_id <> ''),
    year              INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 2200),
    period            INTEGER NOT NULL CHECK (period BETWEEN 0 AND 12),  -- 0 = annual; else quarter or month
    index_value       DOUBLE,               -- the index on its own (first-year) base
    index_1990_base   DOUBLE,
    index_2000_base   DOUBLE,
    annual_change_pct DOUBLE,
    -- provenance (required on every fact table; checked by quality.gates)
    source_record_id  VARCHAR NOT NULL CHECK (source_record_id <> ''),
    source_id         VARCHAR NOT NULL CHECK (source_id <> ''),
    jurisdiction      VARCHAR NOT NULL CHECK (jurisdiction <> ''),
    record_key        VARCHAR NOT NULL CHECK (record_key <> ''),
    source_uri        VARCHAR NOT NULL CHECK (source_uri <> ''),
    retrieved_at      TIMESTAMPTZ NOT NULL,
    content_sha256    VARCHAR NOT NULL CHECK (length(content_sha256) = 64),
    fact_hash         VARCHAR,
    -- transaction time
    ingested_at       TIMESTAMPTZ NOT NULL,
    superseded_at     TIMESTAMPTZ,
    CHECK (superseded_at IS NULL OR superseded_at >= ingested_at)
);
