-- Parcels, geometry, assessments and dated ownership.
-- Geometry is stored as WKB so migrations need no DuckDB extension; spatial queries load
-- the spatial extension and call ST_GeomFromWKB at query time.

-- Identity only. parcel_uid = <state+county FIPS>-<normalized local id>.
CREATE TABLE parcel (
    row_id           VARCHAR PRIMARY KEY,
    parcel_uid        VARCHAR NOT NULL CHECK (parcel_uid <> ''),
    district          VARCHAR,
    map               VARCHAR,
    parcel_no         VARCHAR,
    subparcel         VARCHAR,
    parid_raw         VARCHAR NOT NULL CHECK (parid_raw <> ''),
    -- provenance (required on every fact table; checked by quality.gates)
    source_record_id VARCHAR NOT NULL CHECK (source_record_id <> ''),
    source_id        VARCHAR NOT NULL CHECK (source_id <> ''),
    jurisdiction     VARCHAR NOT NULL CHECK (jurisdiction <> ''),
    record_key       VARCHAR NOT NULL CHECK (record_key <> ''),
    source_uri       VARCHAR NOT NULL CHECK (source_uri <> ''),
    retrieved_at     TIMESTAMPTZ NOT NULL,
    content_sha256   VARCHAR NOT NULL CHECK (length(content_sha256) = 64),
    -- transaction time
    ingested_at      TIMESTAMPTZ NOT NULL,
    superseded_at    TIMESTAMPTZ,
    CHECK (superseded_at IS NULL OR superseded_at >= ingested_at)
);

CREATE TABLE parcel_geometry (
    row_id           VARCHAR PRIMARY KEY,
    parcel_uid        VARCHAR NOT NULL CHECK (parcel_uid <> ''),
    geom_wkb          BLOB NOT NULL,
    srid              INTEGER NOT NULL,
    xmin DOUBLE NOT NULL,
    ymin DOUBLE NOT NULL,
    xmax DOUBLE NOT NULL,
    ymax DOUBLE NOT NULL,
    acres             DOUBLE CHECK (acres IS NULL OR acres >= 0),
    valid_from        DATE NOT NULL,
    valid_to          DATE,
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    -- provenance (required on every fact table; checked by quality.gates)
    source_record_id VARCHAR NOT NULL CHECK (source_record_id <> ''),
    source_id        VARCHAR NOT NULL CHECK (source_id <> ''),
    jurisdiction     VARCHAR NOT NULL CHECK (jurisdiction <> ''),
    record_key       VARCHAR NOT NULL CHECK (record_key <> ''),
    source_uri       VARCHAR NOT NULL CHECK (source_uri <> ''),
    retrieved_at     TIMESTAMPTZ NOT NULL,
    content_sha256   VARCHAR NOT NULL CHECK (length(content_sha256) = 64),
    -- transaction time
    ingested_at      TIMESTAMPTZ NOT NULL,
    superseded_at    TIMESTAMPTZ,
    CHECK (superseded_at IS NULL OR superseded_at >= ingested_at)
);

-- Values as published for a tax year. valid_from is set by the adapter per source config.
CREATE TABLE parcel_assessment (
    row_id           VARCHAR PRIMARY KEY,
    parcel_uid        VARCHAR NOT NULL CHECK (parcel_uid <> ''),
    tax_year          INTEGER NOT NULL CHECK (tax_year BETWEEN 1800 AND 2200),
    appraised_land    DECIMAL(14,2) CHECK (appraised_land IS NULL OR appraised_land >= 0),
    appraised_bldg    DECIMAL(14,2) CHECK (appraised_bldg IS NULL OR appraised_bldg >= 0),
    appraised_total   DECIMAL(14,2) CHECK (appraised_total IS NULL OR appraised_total >= 0),
    assessed_value    DECIMAL(14,2) CHECK (assessed_value IS NULL OR assessed_value >= 0),
    tax_class         VARCHAR,
    valid_from        DATE NOT NULL,
    valid_to          DATE,
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    -- provenance (required on every fact table; checked by quality.gates)
    source_record_id VARCHAR NOT NULL CHECK (source_record_id <> ''),
    source_id        VARCHAR NOT NULL CHECK (source_id <> ''),
    jurisdiction     VARCHAR NOT NULL CHECK (jurisdiction <> ''),
    record_key       VARCHAR NOT NULL CHECK (record_key <> ''),
    source_uri       VARCHAR NOT NULL CHECK (source_uri <> ''),
    retrieved_at     TIMESTAMPTZ NOT NULL,
    content_sha256   VARCHAR NOT NULL CHECK (length(content_sha256) = 64),
    -- transaction time
    ingested_at      TIMESTAMPTZ NOT NULL,
    superseded_at    TIMESTAMPTZ,
    CHECK (superseded_at IS NULL OR superseded_at >= ingested_at)
);

-- Owner of record over an interval (assessor transfer history or snapshot).
CREATE TABLE ownership_period (
    row_id           VARCHAR PRIMARY KEY,
    parcel_uid        VARCHAR NOT NULL CHECK (parcel_uid <> ''),
    party_id          VARCHAR NOT NULL CHECK (party_id <> ''),
    owner_seq         INTEGER NOT NULL CHECK (owner_seq >= 1),
    pct_owned         DECIMAL(7,4) CHECK (pct_owned IS NULL OR (pct_owned > 0 AND pct_owned <= 100)),
    life_estate       BOOLEAN,
    survivorship      BOOLEAN,
    marital_status_raw VARCHAR,
    deed_book         VARCHAR,
    deed_page         VARCHAR,
    sale_price        DECIMAL(14,2) CHECK (sale_price IS NULL OR sale_price >= 0),
    warranty_type     VARCHAR,
    valid_from        DATE NOT NULL,
    valid_to          DATE,
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    -- provenance (required on every fact table; checked by quality.gates)
    source_record_id VARCHAR NOT NULL CHECK (source_record_id <> ''),
    source_id        VARCHAR NOT NULL CHECK (source_id <> ''),
    jurisdiction     VARCHAR NOT NULL CHECK (jurisdiction <> ''),
    record_key       VARCHAR NOT NULL CHECK (record_key <> ''),
    source_uri       VARCHAR NOT NULL CHECK (source_uri <> ''),
    retrieved_at     TIMESTAMPTZ NOT NULL,
    content_sha256   VARCHAR NOT NULL CHECK (length(content_sha256) = 64),
    -- transaction time
    ingested_at      TIMESTAMPTZ NOT NULL,
    superseded_at    TIMESTAMPTZ,
    CHECK (superseded_at IS NULL OR superseded_at >= ingested_at)
);
