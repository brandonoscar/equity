-- Zoning districts from state and regional zoning layers, and new source kinds for the
-- non-parcel datasets (zoning, flood zones, aircraft, vessels).

-- DuckDB cannot alter a CHECK constraint: rebuild source with the wider kind list.
CREATE TABLE source_v14 (
    source_id         VARCHAR PRIMARY KEY CHECK (source_id <> ''),
    kind              VARCHAR NOT NULL CHECK (kind IN (
                          'recorder', 'assessor', 'parcel_statewide', 'court', 'bankruptcy',
                          'sos', 'tax', 'fixture', 'zoning', 'flood', 'aircraft', 'vessel')),
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
INSERT INTO source_v14 SELECT * FROM source;
DROP TABLE source;
ALTER TABLE source_v14 RENAME TO source;

-- One zoning district polygon as the layer publishes it. Codes are local ("R-1" differs by
-- town); zone_class is the layer's own generalized class where it has one. Geometry is the
-- ArcGIS ring list in EPSG:4326 as JSON (even-odd rule handles holes), with its bounding box
-- for prefiltering point-in-polygon joins.
CREATE TABLE zoning_district (
    row_id            VARCHAR PRIMARY KEY,
    zone_uid          VARCHAR NOT NULL CHECK (zone_uid <> ''),
    jurisdiction_name VARCHAR,
    zone_code         VARCHAR,
    zone_desc         VARCHAR,
    zone_class        VARCHAR,
    geom_rings        VARCHAR NOT NULL CHECK (geom_rings <> ''),
    xmin DOUBLE NOT NULL,
    ymin DOUBLE NOT NULL,
    xmax DOUBLE NOT NULL,
    ymax DOUBLE NOT NULL,
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
