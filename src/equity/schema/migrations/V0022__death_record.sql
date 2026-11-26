-- Death records published by a medical examiner or coroner (Cook County IL: unclaimed
-- persons, indigent cremations, county burials, and the remains recovered from a closed
-- crematory). A separate table, read only as a "check before acting" signal on a debtor:
-- nothing here is matched to parties, and a name in it is not proof that a debtor died.
-- A source kind for vital-record publishers.

CREATE TABLE source_v21 (
    source_id         VARCHAR PRIMARY KEY CHECK (source_id <> ''),
    kind              VARCHAR NOT NULL CHECK (kind IN (
                          'recorder', 'assessor', 'parcel_statewide', 'court', 'bankruptcy',
                          'sos', 'tax', 'fixture', 'zoning', 'flood', 'aircraft', 'vessel',
                          'government_sale', 'federal_loan', 'price_index', 'vital_record')),
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
INSERT INTO source_v21 SELECT * FROM source;
DROP TABLE source;
ALTER TABLE source_v21 RENAME TO source;

CREATE TABLE death_record (
    row_id            VARCHAR PRIMARY KEY,
    case_number       VARCHAR NOT NULL CHECK (case_number <> ''),
    record_kind       VARCHAR NOT NULL CHECK (record_kind IN (
                          'unclaimed', 'indigent_cremation', 'county_burial',
                          'crematory_remains')),
    raw_name          VARCHAR NOT NULL CHECK (raw_name <> ''),
    name_norm         VARCHAR NOT NULL CHECK (name_norm <> ''),  -- upper case, punctuation removed
    alternate_names   VARCHAR[],
    death_date        DATE,             -- null where only an arrival date is published
    listed_on         DATE,             -- arrival, cremation or burial date
    age_years         INTEGER CHECK (age_years IS NULL OR age_years BETWEEN 0 AND 130),
    sex               VARCHAR CHECK (sex IS NULL OR sex IN ('F', 'M')),
    county_fips       VARCHAR NOT NULL CHECK (length(county_fips) = 5),
    place             VARCHAR,          -- place of death or cemetery, where published
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
