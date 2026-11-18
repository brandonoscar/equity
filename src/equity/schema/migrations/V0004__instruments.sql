-- Recorded documents and the edges between documents, parties and parcels.

-- One row per recorded instrument version. recorded_seq orders same-day recordings when the source gives it.
CREATE TABLE instrument (
    row_id           VARCHAR PRIMARY KEY,
    instrument_uid    VARCHAR NOT NULL CHECK (instrument_uid <> ''),
    instrument_number VARCHAR,
    book_type         VARCHAR,
    book              VARCHAR,
    page              VARCHAR,
    doc_type_raw      VARCHAR NOT NULL CHECK (doc_type_raw <> ''),
    doc_type          VARCHAR NOT NULL CHECK (doc_type IN ('DEED', 'DEED_OF_TRUST', 'MORTGAGE', 'ASSIGNMENT', 'MODIFICATION', 'EXTENSION', 'SUBORDINATION', 'RELEASE', 'PARTIAL_RELEASE', 'SUBSTITUTE_TRUSTEE', 'TRUSTEE_REPORT', 'JUDGMENT_LIEN', 'ABSTRACT_OF_JUDGMENT', 'EXECUTION', 'LIS_PENDENS', 'MECHANICS_LIEN', 'STATUTORY_LIEN', 'TAX_LIEN_STATE', 'TAX_LIEN_FEDERAL', 'FIXTURE_FILING', 'LAND_CONTRACT', 'LEASE', 'POWER_OF_ATTORNEY', 'COURT_ORDER', 'AFFIDAVIT', 'OTHER')),
    recorded_on       DATE NOT NULL,
    recorded_seq      BIGINT,
    executed_on       DATE,
    consideration     DECIMAL(14,2) CHECK (consideration IS NULL OR consideration >= 0),
    principal_amount  DECIMAL(14,2) CHECK (principal_amount IS NULL OR principal_amount >= 0),
    max_secured_amount DECIMAL(14,2) CHECK (max_secured_amount IS NULL OR max_secured_amount >= 0),
    maturity_date     DATE,
    amount_source     VARCHAR CHECK (amount_source IS NULL OR amount_source IN ('index', 'ocr', 'assessor', 'manual')),
    legal_desc_raw    VARCHAR,
    CHECK (instrument_number IS NOT NULL OR (book IS NOT NULL AND page IS NOT NULL)),
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

CREATE TABLE instrument_party (
    row_id           VARCHAR PRIMARY KEY,
    instrument_uid    VARCHAR NOT NULL CHECK (instrument_uid <> ''),
    party_id          VARCHAR NOT NULL CHECK (party_id <> ''),
    role              VARCHAR NOT NULL CHECK (role IN ('grantor', 'grantee', 'borrower', 'lender', 'trustee', 'beneficiary', 'creditor', 'debtor', 'assignor', 'assignee', 'other')),
    seq               INTEGER NOT NULL CHECK (seq >= 1),
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

-- How a document was tied to a parcel, with the evidence.
CREATE TABLE instrument_parcel (
    row_id           VARCHAR PRIMARY KEY,
    instrument_uid    VARCHAR NOT NULL CHECK (instrument_uid <> ''),
    parcel_uid        VARCHAR NOT NULL CHECK (parcel_uid <> ''),
    method            VARCHAR NOT NULL CHECK (method IN ('book_page_xref', 'assessor_deed_ref', 'legal_desc_rule', 'index_parcel_id', 'manual')),
    evidence          JSON NOT NULL,
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

-- Document-to-document references. A release points at exactly the instrument it releases.
CREATE TABLE instrument_ref (
    row_id           VARCHAR PRIMARY KEY,
    from_uid          VARCHAR NOT NULL CHECK (from_uid <> ''),
    to_uid            VARCHAR NOT NULL CHECK (to_uid <> ''),
    ref_type          VARCHAR NOT NULL CHECK (ref_type IN ('releases', 'partial_release', 'assigns', 'modifies', 'extends', 'subordinates', 'substitutes_trustee', 'corrects', 're_records', 'satisfies_judgment')),
    scope_parcel_uid  VARCHAR,
    method            VARCHAR NOT NULL CHECK (method IN ('index_xref', 'notation', 'ocr', 'manual')),
    CHECK (from_uid <> to_uid),
    CHECK (ref_type <> 'partial_release' OR scope_parcel_uid IS NOT NULL),
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

-- Only images obtained legitimately (purchase or agreement). Never scraped from view-only portals.
CREATE TABLE instrument_image (
    row_id           VARCHAR PRIMARY KEY,
    instrument_uid    VARCHAR NOT NULL CHECK (instrument_uid <> ''),
    page_no           INTEGER NOT NULL CHECK (page_no >= 1),
    image_sha256      VARCHAR NOT NULL CHECK (length(image_sha256) = 64),
    path              VARCHAR NOT NULL CHECK (path <> ''),
    obtained_via      VARCHAR NOT NULL CHECK (obtained_via IN ('purchase', 'electronic_copy_request', 'bulk_agreement')),
    cost              DECIMAL(14,2) CHECK (cost IS NULL OR cost >= 0),
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
