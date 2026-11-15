-- Source records an adapter could not turn into facts without guessing (e.g. an ownership
-- interval that ends before it starts). Kept with full provenance for human review; rules
-- never read from this table.
CREATE TABLE data_issue (
    row_id           VARCHAR PRIMARY KEY,
    issue_code       VARCHAR NOT NULL CHECK (issue_code <> ''),
    target_table     VARCHAR NOT NULL CHECK (target_table <> ''),
    detail           JSON NOT NULL,
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
