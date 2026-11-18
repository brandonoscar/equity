-- Property tax bills and the delinquency / tax-sale lifecycle.

CREATE TABLE tax_bill (
    row_id           VARCHAR PRIMARY KEY,
    parcel_uid        VARCHAR NOT NULL CHECK (parcel_uid <> ''),
    tax_year          INTEGER NOT NULL CHECK (tax_year BETWEEN 1800 AND 2200),
    ticket            VARCHAR,
    taxpayer_party_id VARCHAR,
    billed            DECIMAL(14,2) CHECK (billed IS NULL OR billed >= 0),
    first_half_paid_on  DATE,
    second_half_paid_on DATE,
    unpaid_amount     DECIMAL(14,2) CHECK (unpaid_amount IS NULL OR unpaid_amount >= 0),
    as_of             DATE NOT NULL,
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

CREATE TABLE tax_sale_event (
    row_id           VARCHAR PRIMARY KEY,
    parcel_uid        VARCHAR NOT NULL CHECK (parcel_uid <> ''),
    tax_year          INTEGER CHECK (tax_year IS NULL OR tax_year BETWEEN 1800 AND 2200),
    event             VARCHAR NOT NULL CHECK (event IN ('listed_delinquent', 'certified_to_auditor', 'sold', 'redeemed', 'deed_issued', 'status_reported')),
    event_date        DATE NOT NULL,
    amount            DECIMAL(14,2) CHECK (amount IS NULL OR amount >= 0),
    certificate_no    VARCHAR,
    status_raw        VARCHAR,
    purchaser_party_id VARCHAR,
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
