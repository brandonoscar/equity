-- Outputs of deterministic rule functions. Every output cites the rows it used.

CREATE TABLE rule_run (
    run_id        VARCHAR PRIMARY KEY,
    git_sha       VARCHAR NOT NULL CHECK (git_sha <> ''),
    config_sha256 VARCHAR NOT NULL CHECK (length(config_sha256) = 64),
    as_of         DATE NOT NULL,
    known_as_of   TIMESTAMPTZ NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL
);

CREATE TABLE rule_output (
    row_id       VARCHAR PRIMARY KEY,
    run_id       VARCHAR NOT NULL CHECK (run_id <> ''),
    rule_id      VARCHAR NOT NULL CHECK (rule_id <> ''),
    rule_version VARCHAR NOT NULL CHECK (rule_version <> ''),
    subject_kind VARCHAR NOT NULL CHECK (subject_kind <> ''),
    subject_id   VARCHAR NOT NULL CHECK (subject_id <> ''),
    result       JSON NOT NULL,
    citations    JSON NOT NULL CHECK (json_array_length(citations) >= 1)
);
