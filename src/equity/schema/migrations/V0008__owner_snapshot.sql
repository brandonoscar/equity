-- Owner of record as listed by a snapshot source (assessor roll, statewide parcel file).
-- A snapshot says who owns the parcel now, not since when. observed_on is the date we first
-- saw this owner in this slot; re-fetches that show the same owner change nothing (the loader
-- excludes observed_on from change detection). Dated chains of title go in ownership_period.
CREATE TABLE owner_snapshot (
    row_id           VARCHAR PRIMARY KEY,
    parcel_uid       VARCHAR NOT NULL CHECK (parcel_uid <> ''),
    owner_seq        INTEGER NOT NULL CHECK (owner_seq >= 1),
    party_id         VARCHAR NOT NULL CHECK (party_id <> ''),
    deed_book        VARCHAR,
    deed_page        VARCHAR,
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
