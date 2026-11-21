-- Land use and zoning as each source reports them, kept raw (codes differ by state and
-- town). land_use_code is the assessor/state class code, land_use_desc its text where the
-- source gives one, zoning the local zoning district code.
ALTER TABLE parcel ADD COLUMN land_use_code VARCHAR;
ALTER TABLE parcel ADD COLUMN land_use_desc VARCHAR;
ALTER TABLE parcel ADD COLUMN zoning VARCHAR;
