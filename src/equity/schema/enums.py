"""Closed vocabularies. tests/test_enums.py proves these match the CHECK constraints in SQL."""

from __future__ import annotations

DOC_TYPES: tuple[str, ...] = (
    "DEED", "DEED_OF_TRUST", "MORTGAGE", "ASSIGNMENT", "MODIFICATION", "EXTENSION",
    "SUBORDINATION", "RELEASE", "PARTIAL_RELEASE", "SUBSTITUTE_TRUSTEE", "TRUSTEE_REPORT",
    "JUDGMENT_LIEN", "ABSTRACT_OF_JUDGMENT", "EXECUTION", "LIS_PENDENS", "MECHANICS_LIEN",
    "STATUTORY_LIEN", "TAX_LIEN_STATE", "TAX_LIEN_FEDERAL", "FIXTURE_FILING", "LAND_CONTRACT",
    "LEASE", "POWER_OF_ATTORNEY", "COURT_ORDER", "AFFIDAVIT", "OTHER",
)  # fmt: skip

REF_TYPES: tuple[str, ...] = (
    "releases", "partial_release", "assigns", "modifies", "extends", "subordinates",
    "substitutes_trustee", "corrects", "re_records", "satisfies_judgment",
)  # fmt: skip
