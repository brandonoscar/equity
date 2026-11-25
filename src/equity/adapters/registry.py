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
from equity.adapters.federal.epa_echo import EPAJudicialCases
from equity.adapters.federal.federal_register import FederalRegisterRealty
from equity.adapters.federal.fjc_idb import FJCCivilJudgments
from equity.adapters.federal.fjc_idb_direct import FJCDirectCivilJudgments
from equity.adapters.federal.hud_reo import HudFhaReo
from equity.adapters.federal.sba_chargeoffs import SBAChargeOffs
from equity.adapters.federal.sba_ppp import SBAPPPChargeOffs
from equity.adapters.fl.citrus_civil import CitrusCivil
from equity.adapters.fl.hernando_civil import HernandoCivilFilings
from equity.adapters.fl.hernando_or import HernandoOfficialRecords
from equity.adapters.fl.hillsborough_civil import (
    HillsboroughCivilCases,
    HillsboroughCivilFilings,
    HillsboroughGarnishment,
)
from equity.adapters.fl.hillsborough_or import HillsboroughOfficialRecords
from equity.adapters.fl.putnam_or import PutnamOfficialRecords
from equity.adapters.hi.honolulu_owners import HonoluluOwners
from equity.adapters.il.cook_parcels import CookCountyParcels
from equity.adapters.liens import all_lien_adapters
from equity.adapters.md_baltimore_citations import BaltimoreCitationLiens
from equity.adapters.md_prince_georges import PrinceGeorgesProperty
from equity.adapters.ne_douglas_tax_liens import DouglasTaxLiens
from equity.adapters.ny.acris import AcrisPersonalProperty, AcrisRealProperty
from equity.adapters.ny.condo_units import NycCondoUnits
from equity.adapters.ny.name_history import NYNameHistory
from equity.adapters.pa.allegheny_assessments import AlleghenyAssessments
from equity.adapters.pa.philadelphia_rtt import PhiladelphiaRTT
from equity.adapters.ri_providence import ProvidenceTaxRoll
from equity.adapters.socrata_parcels import all_api_parcel_adapters
from equity.adapters.state_parcels import all_state_adapters
from equity.adapters.tx.harris_district import HarrisDistrictCivilJudgments
from equity.adapters.tx.harris_jp import HarrisJPCivilJudgments
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
    *all_api_parcel_adapters(),
    *all_zoning_adapters(),
    *all_lien_adapters(),
    LocalZoningAdapter,
    NJMunicipalCodeLinks,
    ColoradoUCC,
    DCBusiness,
    BaltimoreCitationLiens,
    DouglasTaxLiens,
    TexasStratMapParcels,
    CookCountyParcels,
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
    CitrusCivil,
    HernandoOfficialRecords,
    HernandoCivilFilings,
    PutnamOfficialRecords,
    FJCCivilJudgments,
    FJCDirectCivilJudgments,
    EPAJudicialCases,
    HudFhaReo,
    FederalRegisterRealty,
    SBAChargeOffs,
    SBAPPPChargeOffs,
    PrinceGeorgesProperty,
    NYNameHistory,
    HarrisJPCivilJudgments,
    HarrisDistrictCivilJudgments,
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
