-- Identifiers a source prints for a party or a registry entity: tax ids (EIN), NPI, SEC CIK,
-- FCC FRN, USDOT, license numbers, parcel ids, phone numbers and email addresses. Matching
-- (equity.matching.graph) joins records that carry the same identifier; a record without one
-- still links by name and address, so an identifier only ever adds links.
CREATE TABLE party_identifier (
    row_id            VARCHAR PRIMARY KEY,
    party_id          VARCHAR,          -- the party that carries it, or
    sos_id            VARCHAR,          -- the registry entity (business) that carries it
    id_type           VARCHAR NOT NULL CHECK (id_type IN (
                          'ein', 'npi', 'sec_cik', 'fcc_frn', 'usdot', 'license', 'parcel',
                          'phone', 'email', 'other')),
    id_value          VARCHAR NOT NULL CHECK (id_value <> ''),
    issuer            VARCHAR,          -- for licenses: the board or agency
    CHECK (party_id IS NOT NULL OR sos_id IS NOT NULL),
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
