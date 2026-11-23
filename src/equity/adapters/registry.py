"""Every production adapter, registered in one place."""

from __future__ import annotations

# REGISTRY is re-exported: importing it from here guarantees every adapter below is registered.
from equity.adapters.base import REGISTRY as REGISTRY
from equity.adapters.base import Adapter, register
from equity.adapters.business_registry import all_registry_adapters
from equity.adapters.co_ucc import ColoradoUCC
from equity.adapters.code_links import NJMunicipalCodeLinks
from equity.adapters.dc_business import DCBusiness
from equity.adapters.federal.ecf_rss import NDWVBankruptcyRSS, NDWVDistrictRSS, court_adapters
from equity.adapters.fl.hillsborough_civil import (
    HillsboroughCivilCases,
    HillsboroughCivilFilings,
    HillsboroughGarnishment,
)
from equity.adapters.fl.hillsborough_or import HillsboroughOfficialRecords
from equity.adapters.hi.honolulu_owners import HonoluluOwners
from equity.adapters.liens import all_lien_adapters
from equity.adapters.md_baltimore_citations import BaltimoreCitationLiens
from equity.adapters.mi_detroit_blight import DetroitBlightJudgments
from equity.adapters.ne_douglas_tax_liens import DouglasTaxLiens
from equity.adapters.ny.acris import AcrisPersonalProperty, AcrisRealProperty
from equity.adapters.ny.condo_units import NycCondoUnits
from equity.adapters.pa.allegheny_assessments import AlleghenyAssessments
from equity.adapters.pa.philadelphia_rtt import PhiladelphiaRTT
from equity.adapters.ri_providence import ProvidenceTaxRoll
from equity.adapters.state_parcels import all_state_adapters
from equity.adapters.tx.stratmap import TexasStratMapParcels
from equity.adapters.tx_harris_jp import HarrisJPJudgments
from equity.adapters.tx_travis_delinquent import TravisTaxDelinquent
from equity.adapters.wv.delinquent import WVDelinquentProperties
from equity.adapters.wv.parcelweb import MonongaliaParcelWeb
from equity.adapters.wv.statewide_parcels import WVStatewideParcels
from equity.adapters.zoning import LocalZoningAdapter, all_zoning_adapters

_ALL: tuple[type[Adapter], ...] = (
    WVStatewideParcels,
    WVDelinquentProperties,
    MonongaliaParcelWeb,
    NDWVDistrictRSS,
    NDWVBankruptcyRSS,
    *all_state_adapters(),
    *all_zoning_adapters(),
    *all_lien_adapters(),
    LocalZoningAdapter,
    NJMunicipalCodeLinks,
    ColoradoUCC,
    DCBusiness,
    BaltimoreCitationLiens,
    DetroitBlightJudgments,
    DouglasTaxLiens,
    TexasStratMapParcels,
    AcrisRealProperty,
    NycCondoUnits,
    HonoluluOwners,
    AcrisPersonalProperty,
    PhiladelphiaRTT,
    AlleghenyAssessments,
    ProvidenceTaxRoll,
    HarrisJPJudgments,
    TravisTaxDelinquent,
    HillsboroughOfficialRecords,
    HillsboroughCivilCases,
    HillsboroughCivilFilings,
    HillsboroughGarnishment,
    *all_registry_adapters(),
    # NDWV keeps its original source ids; config/courts.yaml adds every other court.
    *[c for c in court_adapters() if c.court_id not in ("wvnd", "wvnb")],
)
for _cls in _ALL:
    if _cls not in REGISTRY:
        register(_cls)


def by_source_id(source_id: str) -> type[Adapter]:
    for cls in REGISTRY:
        if cls.source_id == source_id:
            return cls
    raise KeyError(source_id)
