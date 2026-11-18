-- Delinquent-property status as listed by a snapshot source (WV State Auditor via WVGISTC).
-- The source carries no event dates, only a current status per certificate, so a status
-- change supersedes the previous row (history lives in transaction time). observed_on is the
-- first date we saw this status.
CREATE TABLE tax_delinquency_snapshot (
    row_id           VARCHAR PRIMARY KEY,
    parcel_uid       VARCHAR NOT NULL CHECK (parcel_uid <> ''),
    certificate_no   VARCHAR NOT NULL CHECK (certificate_no <> ''),
    status_raw       VARCHAR NOT NULL CHECK (status_raw <> ''),
    times_listed     INTEGER CHECK (times_listed IS NULL OR times_listed >= 0),
    deed_book        VARCHAR,
    deed_page        VARCHAR,
    legal_desc_raw   VARCHAR,
    observed_on      DATE NOT NULL,
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
