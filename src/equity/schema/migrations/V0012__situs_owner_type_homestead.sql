-- Fields every judgment search needs, where the source publishes them:
--   parcel.situs_address_id      the property's own street address (an address row), which is
--                                how recorded documents and court filings name a parcel;
--   owner_snapshot.owner_type    the source's own owner-type wording (individual, corporation,
--                                trust, government ...), kept as published;
--   parcel_assessment.homestead  whether the roll carries a homestead exemption for the year.
--                                Legal effect (e.g. Florida's exemption from forced sale) is
--                                decided by rules, not here.

ALTER TABLE parcel ADD COLUMN situs_address_id VARCHAR;
ALTER TABLE owner_snapshot ADD COLUMN owner_type VARCHAR;
ALTER TABLE parcel_assessment ADD COLUMN homestead BOOLEAN;
