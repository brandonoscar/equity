-- Names as printed (party), resolved actors (entity), and the evidence linking them.

CREATE TABLE address (
    address_id VARCHAR PRIMARY KEY,
    line1      VARCHAR,
    line2      VARCHAR,
    city       VARCHAR,
    state      VARCHAR,
    zip5       VARCHAR CHECK (zip5 IS NULL OR regexp_full_match(zip5, '[0-9]{5}')),
    norm_key   VARCHAR NOT NULL UNIQUE CHECK (norm_key <> '')
);

-- One row per name as it appears on one source record. Never merged.
CREATE TABLE party (
    row_id           VARCHAR PRIMARY KEY,
    party_id          VARCHAR NOT NULL CHECK (party_id <> ''),
    raw_name          VARCHAR NOT NULL CHECK (raw_name <> ''),
    party_kind        VARCHAR NOT NULL CHECK (party_kind IN ('person', 'org', 'unknown')),
    last_name         VARCHAR,
    first_name        VARCHAR,
    middle            VARCHAR,
    suffix            VARCHAR,
    org_name_norm     VARCHAR,
    org_form          VARCHAR,
    address_id        VARCHAR,
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

-- A resolved real-world person or organization. Exists only because a link created it.
CREATE TABLE entity (
    entity_id          VARCHAR PRIMARY KEY,
    entity_kind        VARCHAR NOT NULL CHECK (entity_kind IN ('person', 'org')),
    display_name       VARCHAR NOT NULL CHECK (display_name <> ''),
    created_by_link_id VARCHAR NOT NULL CHECK (created_by_link_id <> ''),
    created_at         TIMESTAMPTZ NOT NULL
);

-- party -> entity, with the deterministic rule that fired and its evidence.
CREATE TABLE entity_link (
    link_id       VARCHAR PRIMARY KEY,
    party_id      VARCHAR NOT NULL CHECK (party_id <> ''),
    entity_id     VARCHAR NOT NULL CHECK (entity_id <> ''),
    rule_id       VARCHAR NOT NULL CHECK (rule_id <> ''),
    rule_version  VARCHAR NOT NULL CHECK (rule_version <> ''),
    name_score    DOUBLE CHECK (name_score IS NULL OR (name_score >= 0 AND name_score <= 100)),
    signals       JSON NOT NULL,
    decision      VARCHAR NOT NULL CHECK (decision IN (
                      'auto', 'review', 'rejected', 'human_accept', 'human_reject')),
    decided_at    TIMESTAMPTZ NOT NULL,
    decided_by    VARCHAR NOT NULL CHECK (decided_by <> ''),
    superseded_at TIMESTAMPTZ
);

CREATE TABLE review_queue (
    link_id   VARCHAR PRIMARY KEY,
    reason    VARCHAR NOT NULL CHECK (reason IN ('below_cutoff', 'single_signal', 'conflict')),
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ
);

-- Secretary of State entity, as of the valid interval.
CREATE TABLE business (
    row_id           VARCHAR PRIMARY KEY,
    sos_id            VARCHAR NOT NULL CHECK (sos_id <> ''),
    name              VARCHAR NOT NULL CHECK (name <> ''),
    org_form          VARCHAR,
    status            VARCHAR,
    formed_on         DATE,
    status_date       DATE,
    principal_address_id VARCHAR,
    mailing_address_id   VARCHAR,
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

-- Officer, member, manager and registered-agent edges.
CREATE TABLE business_role (
    row_id           VARCHAR PRIMARY KEY,
    sos_id            VARCHAR NOT NULL CHECK (sos_id <> ''),
    party_id          VARCHAR NOT NULL CHECK (party_id <> ''),
    role              VARCHAR NOT NULL CHECK (role IN ('member', 'manager', 'officer', 'director', 'organizer', 'incorporator', 'registered_agent', 'other')),
    title             VARCHAR,
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
