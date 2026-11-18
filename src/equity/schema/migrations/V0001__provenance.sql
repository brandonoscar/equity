-- Provenance backbone. Every fact row in later migrations points at a source_record.
-- Referential integrity is checked by equity.quality.gates (DuckDB foreign keys block
-- the UPDATEs that bitemporal supersession needs).

CREATE TABLE source (
    source_id         VARCHAR PRIMARY KEY CHECK (source_id <> ''),
    kind              VARCHAR NOT NULL CHECK (kind IN (
                          'recorder', 'assessor', 'parcel_statewide', 'court', 'bankruptcy',
                          'sos', 'tax', 'fixture')),
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

-- One row per retrieval (HTTP request, bulk file, or manual capture).
CREATE TABLE fetch_log (
    fetch_id        VARCHAR PRIMARY KEY,
    source_id       VARCHAR NOT NULL CHECK (source_id <> ''),
    adapter         VARCHAR NOT NULL CHECK (adapter <> ''),
    adapter_version VARCHAR NOT NULL CHECK (adapter_version <> ''),
    request         VARCHAR NOT NULL CHECK (request <> ''),
    retrieved_at    TIMESTAMPTZ NOT NULL,
    http_status     INTEGER,
    content_sha256  VARCHAR NOT NULL CHECK (length(content_sha256) = 64),
    raw_path        VARCHAR NOT NULL CHECK (raw_path <> ''),
    bytes           BIGINT NOT NULL CHECK (bytes >= 0)
);

-- Row-level provenance: the exact record (row, feature, page, docket line) a fact came from.
CREATE TABLE source_record (
    source_record_id VARCHAR PRIMARY KEY,
    fetch_id         VARCHAR NOT NULL CHECK (fetch_id <> ''),
    source_id        VARCHAR NOT NULL CHECK (source_id <> ''),
    record_key       VARCHAR NOT NULL CHECK (record_key <> ''),
    record_type      VARCHAR NOT NULL CHECK (record_type <> ''),
    raw_sha256       VARCHAR NOT NULL CHECK (length(raw_sha256) = 64),
    first_seen_at    TIMESTAMPTZ NOT NULL,
    last_seen_at     TIMESTAMPTZ NOT NULL,
    CHECK (last_seen_at >= first_seen_at)
);
