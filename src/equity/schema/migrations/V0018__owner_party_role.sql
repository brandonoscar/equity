-- An 'owner' role for instrument parties: a record that names a parcel's owner without being an
-- owner roll (a building permit's owner field, a landlord or rental registration, a code case
-- against the owner). With the record's instrument_parcel link it tells the matcher who owned
-- the lot on the record's date, which fills parcels whose roll publishes no owner names
-- (equity.matching.resolve, inferred owners).

-- DuckDB cannot alter a CHECK constraint: rebuild instrument_party with the wider role list.
CREATE TABLE instrument_party_v18 (
    row_id           VARCHAR PRIMARY KEY,
    instrument_uid    VARCHAR NOT NULL CHECK (instrument_uid <> ''),
    party_id          VARCHAR NOT NULL CHECK (party_id <> ''),
    role              VARCHAR NOT NULL CHECK (role IN ('grantor', 'grantee', 'borrower', 'lender', 'trustee', 'beneficiary', 'creditor', 'debtor', 'assignor', 'assignee', 'owner', 'other')),
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
    CHECK (superseded_at IS NULL OR superseded_at >= ingested_at),
    fact_hash        VARCHAR
);
INSERT INTO instrument_party_v18 SELECT * FROM instrument_party;
DROP TABLE instrument_party;
ALTER TABLE instrument_party_v18 RENAME TO instrument_party;
