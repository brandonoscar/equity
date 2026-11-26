"""Every production adapter, registered in one place."""

from __future__ import annotations

# REGISTRY is re-exported: importing it from here guarantees every adapter below is registered.
from equity.adapters.base import REGISTRY as REGISTRY
from equity.adapters.base import Adapter, register
from equity.adapters.business_registry import all_registry_adapters
from equity.adapters.co_ucc import ColoradoUCC
from equity.adapters.code_links import NJMunicipalCodeLinks
from equity.adapters.dc_business import DCBusiness
from equity.adapters.deeds import all_deed_adapters
from equity.adapters.federal.cms_lists import CMSOptOutAffidavits, CMSRevokedProviders
from equity.adapters.federal.cms_nppes import CMSNPPES
from equity.adapters.federal.cms_open_payments import CMSOpenPayments
from equity.adapters.federal.dol_whd import DOLWageHourCases
from equity.adapters.federal.ecf_rss import NDWVBankruptcyRSS, NDWVDistrictRSS, court_adapters
from equity.adapters.federal.eia import EIA860
from equity.adapters.federal.epa_echo import EPAJudicialCases
from equity.adapters.federal.fcc_uls import FCC_ULS_ADAPTERS
from equity.adapters.federal.fda import FDADrugEstablishments
from equity.adapters.federal.fdic import FDICInstitutions, FDICLocations
from equity.adapters.federal.federal_register import FederalRegisterLoanSales, FederalRegisterRealty
from equity.adapters.federal.fhfa_hpi import FhfaHpiZip5
from equity.adapters.federal.fjc_idb import FJCCivilJudgments
from equity.adapters.federal.fjc_idb_direct import FJCDirectCivilJudgments
from equity.adapters.federal.fmcsa import FMCSACarrierCensus
from equity.adapters.federal.hhs_oig import HHSOIGExclusions
from equity.adapters.federal.hud_reo import HudFhaReo
from equity.adapters.federal.irs_990 import IRS990Officers
from equity.adapters.federal.irs_eo import IRSExemptOrgs
from equity.adapters.federal.msha import MSHAAssessedPenalties, MSHAMines
from equity.adapters.federal.ncua import NCUACreditUnions
from equity.adapters.federal.ofac import OFACSDN, OFACConsolidated
from equity.adapters.federal.sba_chargeoffs import SBAChargeOffs
from equity.adapters.federal.sba_loans import SBA7a504Loans, SBAPPPLoans
from equity.adapters.federal.sba_ppp import SBAPPPChargeOffs
from equity.adapters.federal.sec_edgar import SECFormD, SECInsiders
from equity.adapters.federal.sec_iapd import SECInvestmentAdvisers
from equity.adapters.federal.sec_submissions import SECSubmissions
from equity.adapters.federal.senate_lda import LDAClients, LDALobbyists, LDARegistrants
from equity.adapters.federal.usaspending import USASpendingRecipients
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
from equity.adapters.indiana_sdf import IndianaSalesDisclosures
from equity.adapters.licenses import all_license_adapters
from equity.adapters.liens import all_lien_adapters
from equity.adapters.md_baltimore_citations import BaltimoreCitationLiens
from equity.adapters.md_prince_georges import PrinceGeorgesProperty
from equity.adapters.ne_douglas_tax_liens import DouglasTaxLiens
from equity.adapters.ny.acris import AcrisPersonalProperty, AcrisRealProperty
from equity.adapters.ny.condo_units import NycCondoUnits
from equity.adapters.ny.name_history import NYNameHistory
from equity.adapters.pa.allegheny_assessments import AlleghenyAssessments
from equity.adapters.pa.philadelphia_rtt import PhiladelphiaRTT
from equity.adapters.person_lists import all_person_list_adapters
from equity.adapters.ri_providence import ProvidenceTaxRoll
from equity.adapters.socrata_parcels import all_api_parcel_adapters
from equity.adapters.state_parcels import all_state_adapters
from equity.adapters.tx.harris_district import HarrisDistrictCivilJudgments
from equity.adapters.tx.harris_jp import HarrisJPCivilJudgments
from equity.adapters.tx.stratmap import TexasStratMapParcels
from equity.adapters.tx_harris_jp import HarrisJPJudgments
from equity.adapters.tx_travis_delinquent import TravisTaxDelinquent
from equity.adapters.voter_files import BoulderCountyVoterFile, NorthCarolinaVoterFile
from equity.adapters.vt_pttr_archive import VermontTransferArchive
from equity.adapters.wv.delinquent import WVDelinquentProperties
from equity.adapters.wv.parcelweb import MonongaliaParcelWeb
from equity.adapters.wv.statewide_parcels import WVStatewideParcels
from equity.adapters.zoning import LocalZoningAdapter, all_zoning_adapters

_ALL: tuple[type[Adapter], ...] = (
    NorthCarolinaVoterFile,  # OhioVoterFile joins once a hand-saved county fixture exists
    BoulderCountyVoterFile,  # one county's free VR-011B file, read by ColoradoVoterFile's layout
    WVStatewideParcels,
    WVDelinquentProperties,
    MonongaliaParcelWeb,
    NDWVDistrictRSS,
    NDWVBankruptcyRSS,
    *all_state_adapters(),
    *all_api_parcel_adapters(),
    *all_zoning_adapters(),
    *all_lien_adapters(),
    *all_deed_adapters(),
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
    IndianaSalesDisclosures,
    AlleghenyAssessments,
    ProvidenceTaxRoll,
    HarrisJPJudgments,
    TravisTaxDelinquent,
    VermontTransferArchive,
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
    FederalRegisterLoanSales,
    FhfaHpiZip5,
    SBAChargeOffs,
    SBAPPPChargeOffs,
    SBAPPPLoans,
    SBA7a504Loans,
    USASpendingRecipients,
    IRSExemptOrgs,
    IRS990Officers,
    SECFormD,
    SECInsiders,  # USPTO trademark/patent adapters join once hand-saved fixtures exist
    SECInvestmentAdvisers,
    CMSNPPES,
    CMSOpenPayments,
    FMCSACarrierCensus,  # ATFFirearmsLicensees joins once a hand-saved fixture exists
    DOLWageHourCases,  # reads saved files (the DOL API needs a key); DOLOSHAPenalties too, once
    HHSOIGExclusions,
    SECSubmissions,
    OFACSDN,
    OFACConsolidated,
    FDICInstitutions,
    FDICLocations,
    NCUACreditUnions,
    MSHAMines,
    MSHAAssessedPenalties,
    LDARegistrants,
    LDAClients,
    LDALobbyists,
    CMSOptOutAffidavits,
    CMSRevokedProviders,
    FDADrugEstablishments,
    EIA860,
    *FCC_ULS_ADAPTERS,  # FAAAircraftRegistry joins once a hand-saved fixture exists
    PrinceGeorgesProperty,
    NYNameHistory,
    HarrisJPCivilJudgments,
    HarrisDistrictCivilJudgments,
    *all_registry_adapters(),
    *all_license_adapters(),
    *all_person_list_adapters(),
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
