-- Content hash of each fact's non-provenance columns (the loader's change detector),
-- stored so bulk loads can find unchanged/changed facts with set-based SQL.

ALTER TABLE bankruptcy ADD COLUMN fact_hash VARCHAR;
ALTER TABLE business ADD COLUMN fact_hash VARCHAR;
ALTER TABLE business_role ADD COLUMN fact_hash VARCHAR;
ALTER TABLE case_party ADD COLUMN fact_hash VARCHAR;
ALTER TABLE court_case ADD COLUMN fact_hash VARCHAR;
ALTER TABLE data_issue ADD COLUMN fact_hash VARCHAR;
ALTER TABLE docket_entry ADD COLUMN fact_hash VARCHAR;
ALTER TABLE instrument ADD COLUMN fact_hash VARCHAR;
ALTER TABLE instrument_image ADD COLUMN fact_hash VARCHAR;
ALTER TABLE instrument_parcel ADD COLUMN fact_hash VARCHAR;
ALTER TABLE instrument_party ADD COLUMN fact_hash VARCHAR;
ALTER TABLE instrument_ref ADD COLUMN fact_hash VARCHAR;
ALTER TABLE judgment ADD COLUMN fact_hash VARCHAR;
ALTER TABLE judgment_event ADD COLUMN fact_hash VARCHAR;
ALTER TABLE owner_snapshot ADD COLUMN fact_hash VARCHAR;
ALTER TABLE ownership_period ADD COLUMN fact_hash VARCHAR;
ALTER TABLE parcel ADD COLUMN fact_hash VARCHAR;
ALTER TABLE parcel_assessment ADD COLUMN fact_hash VARCHAR;
ALTER TABLE parcel_geometry ADD COLUMN fact_hash VARCHAR;
ALTER TABLE party ADD COLUMN fact_hash VARCHAR;
ALTER TABLE tax_bill ADD COLUMN fact_hash VARCHAR;
ALTER TABLE tax_delinquency_snapshot ADD COLUMN fact_hash VARCHAR;
ALTER TABLE tax_sale_event ADD COLUMN fact_hash VARCHAR;
