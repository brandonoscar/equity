-- FHFA also publishes the annual HPI by 2010 census tract (11-digit GEOID). DuckDB cannot
-- alter a CHECK constraint: rebuild house_price_index with 'tract' among the geo levels.
CREATE TABLE house_price_index_v20 (
    row_id            VARCHAR PRIMARY KEY,
    geo_level         VARCHAR NOT NULL CHECK (geo_level IN ('zip5', 'zip3', 'county', 'state',
                                                            'tract')),
    geo_id            VARCHAR NOT NULL CHECK (geo_id <> ''),
    year              INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 2200),
    period            INTEGER NOT NULL CHECK (period BETWEEN 0 AND 12),
    index_value       DOUBLE,
    index_1990_base   DOUBLE,
    index_2000_base   DOUBLE,
    annual_change_pct DOUBLE,
    source_record_id  VARCHAR NOT NULL CHECK (source_record_id <> ''),
    source_id         VARCHAR NOT NULL CHECK (source_id <> ''),
    jurisdiction      VARCHAR NOT NULL CHECK (jurisdiction <> ''),
    record_key        VARCHAR NOT NULL CHECK (record_key <> ''),
    source_uri        VARCHAR NOT NULL CHECK (source_uri <> ''),
    retrieved_at      TIMESTAMPTZ NOT NULL,
    content_sha256    VARCHAR NOT NULL CHECK (length(content_sha256) = 64),
    fact_hash         VARCHAR,
    ingested_at       TIMESTAMPTZ NOT NULL,
    superseded_at     TIMESTAMPTZ,
    CHECK (superseded_at IS NULL OR superseded_at >= ingested_at)
);
INSERT INTO house_price_index_v20 SELECT * FROM house_price_index;
DROP TABLE house_price_index;
ALTER TABLE house_price_index_v20 RENAME TO house_price_index;
