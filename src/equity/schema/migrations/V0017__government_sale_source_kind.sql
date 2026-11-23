-- A source kind for government property sale and disposal feeds that are neither a recorder,
-- an assessor, a court nor a tax collector: HUD FHA REO homes, Federal Register realty and
-- surplus-property notices; and one for federal loan records (SBA 7(a)/504 charge-offs).

-- DuckDB cannot alter a CHECK constraint: rebuild source with the wider kind list.
CREATE TABLE source_v17 (
    source_id         VARCHAR PRIMARY KEY CHECK (source_id <> ''),
    kind              VARCHAR NOT NULL CHECK (kind IN (
                          'recorder', 'assessor', 'parcel_statewide', 'court', 'bankruptcy',
                          'sos', 'tax', 'fixture', 'zoning', 'flood', 'aircraft', 'vessel',
                          'government_sale', 'federal_loan')),
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
INSERT INTO source_v17 SELECT * FROM source;
DROP TABLE source;
ALTER TABLE source_v17 RENAME TO source;
