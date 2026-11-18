-- Court cases, parties, judgments as event sequences, bankruptcies, docket entries.

CREATE TABLE court_case (
    row_id           VARCHAR PRIMARY KEY,
    case_uid          VARCHAR NOT NULL CHECK (case_uid <> ''),
    court_id          VARCHAR NOT NULL CHECK (court_id <> ''),
    case_number_raw   VARCHAR NOT NULL CHECK (case_number_raw <> ''),
    case_number_norm  VARCHAR NOT NULL CHECK (case_number_norm <> ''),
    case_type         VARCHAR,
    nature_of_suit    VARCHAR,
    filed_on          DATE,
    closed_on         DATE,
    status            VARCHAR,
    CHECK (closed_on IS NULL OR filed_on IS NULL OR closed_on >= filed_on),
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

CREATE TABLE case_party (
    row_id           VARCHAR PRIMARY KEY,
    case_uid          VARCHAR NOT NULL CHECK (case_uid <> ''),
    party_id          VARCHAR NOT NULL CHECK (party_id <> ''),
    role              VARCHAR NOT NULL CHECK (role IN ('plaintiff', 'defendant', 'debtor', 'creditor', 'trustee', 'garnishee', 'intervenor', 'other')),
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

CREATE TABLE judgment (
    row_id           VARCHAR PRIMARY KEY,
    judgment_uid      VARCHAR NOT NULL CHECK (judgment_uid <> ''),
    case_uid          VARCHAR NOT NULL CHECK (case_uid <> ''),
    entered_on        DATE NOT NULL,
    principal         DECIMAL(14,2) CHECK (principal IS NULL OR principal >= 0),
    interest          DECIMAL(14,2) CHECK (interest IS NULL OR interest >= 0),
    costs             DECIMAL(14,2) CHECK (costs IS NULL OR costs >= 0),
    rate              DECIMAL(9,6) CHECK (rate IS NULL OR rate >= 0),
    judgment_type     VARCHAR CHECK (judgment_type IS NULL OR judgment_type IN ('money', 'deficiency', 'default', 'consent', 'other')),
    lien_instrument_uid VARCHAR,
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

-- A judgment's life is a sequence of events, not a status column.
CREATE TABLE judgment_event (
    row_id           VARCHAR PRIMARY KEY,
    judgment_uid      VARCHAR NOT NULL CHECK (judgment_uid <> ''),
    event             VARCHAR NOT NULL CHECK (event IN ('docketed', 'abstracted', 'renewed', 'revived', 'assigned', 'partial_satisfaction', 'satisfied', 'vacated', 'execution_issued')),
    event_date        DATE NOT NULL,
    amount            DECIMAL(14,2) CHECK (amount IS NULL OR amount >= 0),
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

CREATE TABLE bankruptcy (
    row_id           VARCHAR PRIMARY KEY,
    case_uid          VARCHAR NOT NULL CHECK (case_uid <> ''),
    chapter           VARCHAR NOT NULL CHECK (chapter IN ('7', '9', '11', '12', '13', '15')),
    petition_on       DATE NOT NULL,
    discharge_on      DATE,
    dismissed_on      DATE,
    converted_on      DATE,
    trustee_party_id  VARCHAR,
    asset_case        BOOLEAN,
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

CREATE TABLE docket_entry (
    row_id           VARCHAR PRIMARY KEY,
    case_uid          VARCHAR NOT NULL CHECK (case_uid <> ''),
    entry_no          INTEGER,
    entry_date        DATE NOT NULL,
    text              VARCHAR NOT NULL,
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
