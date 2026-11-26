-- Assessment ratios published by state equalization agencies: the share of market value at
-- which a municipality assesses, per year (and property class where published). Dividing an
-- assessed value by its ratio gives a market-value estimate; using that in equity is a
-- separate, owner-approved step.
CREATE TABLE assessment_ratio (
    row_id            VARCHAR PRIMARY KEY,
    geo_level         VARCHAR NOT NULL CHECK (geo_level IN ('ny_swis', 'ct_town')),
    geo_id            VARCHAR NOT NULL CHECK (geo_id <> ''),
    geo_name          VARCHAR,
    year              INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 2200),
    property_class    VARCHAR NOT NULL CHECK (property_class IN (
                          'all', 'residential', 'apartments', 'commercial_industrial',
                          'vacant', 'personal')),
    ratio_kind        VARCHAR NOT NULL CHECK (ratio_kind IN (
                          'residential_assessment_ratio', 'equalization_rate',
                          'equalized_ratio')),
    ratio_pct         DOUBLE NOT NULL CHECK (ratio_pct > 0),
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
