"""Every production adapter, registered in one place."""

from __future__ import annotations

from equity.adapters.base import REGISTRY, Adapter, register
from equity.adapters.federal.ecf_rss import NDWVBankruptcyRSS, NDWVDistrictRSS
from equity.adapters.state_parcels import all_state_adapters
from equity.adapters.wv.delinquent import WVDelinquentProperties
from equity.adapters.wv.parcelweb import MonongaliaParcelWeb
from equity.adapters.wv.statewide_parcels import WVStatewideParcels

for _cls in (
    WVStatewideParcels,
    WVDelinquentProperties,
    MonongaliaParcelWeb,
    NDWVDistrictRSS,
    NDWVBankruptcyRSS,
    *all_state_adapters(),
):
    if _cls not in REGISTRY:
        register(_cls)


def by_source_id(source_id: str) -> type[Adapter]:
    for cls in REGISTRY:
        if cls.source_id == source_id:
            return cls
    raise KeyError(source_id)
