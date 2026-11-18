"""Deterministic first-pass classification of a raw party name: organization or unknown.

This never guesses that a name is a person. Anything without an organization marker is
'unknown' until Phase 3's parser decides with explicit rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Entity-form suffixes, longest first, normalized without punctuation.
_FORMS: tuple[tuple[str, str], ...] = (
    ("LIMITED LIABILITY COMPANY", "LLC"),
    ("LIMITED PARTNERSHIP", "LP"),
    ("PROFESSIONAL LIMITED LIABILITY COMPANY", "PLLC"),
    ("INCORPORATED", "INC"),
    ("CORPORATION", "CORP"),
    ("COMPANY", "CO"),
    ("LIMITED", "LTD"),
    ("PLLC", "PLLC"),
    ("LLLP", "LLLP"),
    ("LLC", "LLC"),
    ("LLP", "LLP"),
    ("INC", "INC"),
    ("CORP", "CORP"),
    ("LTD", "LTD"),
    ("LP", "LP"),
    ("PC", "PC"),
    ("PA", "PA"),
    ("NA", "NA"),
    ("CO", "CO"),
)
# Words that mark an organization anywhere in the name.
_ORG_WORDS = frozenset(
    {
        "BANK", "TRUST", "TRUSTEE", "TRUSTEES", "ASSOCIATION", "ASSN", "CHURCH", "UNIVERSITY",
        "COLLEGE", "BOARD", "COMMISSION", "COUNTY", "CITY", "TOWN", "STATE", "AUTHORITY",
        "DEPARTMENT", "DEPT", "HOLDINGS", "PROPERTIES", "PARTNERS", "PARTNERSHIP", "GROUP",
        "ENTERPRISES", "INVESTMENTS", "CREDIT", "UNION", "FOUNDATION", "MINISTRIES",
        "DEVELOPMENT", "REALTY", "ESTATE", "ESTATES", "FUND", "SERVICES", "MORTGAGE",
        "FINANCIAL", "CAPITAL", "LENDING", "HOMEOWNERS", "CONDOMINIUM", "UNITED", "AMERICA",
    }
)  # fmt: skip

_NONWORD = re.compile(r"[^A-Z0-9& ]+")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class NameClass:
    party_kind: str  # 'org' | 'unknown'
    org_form: str | None
    org_name_norm: str | None


def clean(raw: str) -> str:
    """Uppercase, drop punctuation (so L.L.C. == LLC), collapse spaces."""
    text = raw.upper().replace(".", "")
    text = _NONWORD.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def classify(raw: str) -> NameClass:
    text = clean(raw)
    if not text:
        return NameClass("unknown", None, None)
    for phrase, form in _FORMS:
        if text == phrase:
            continue
        if text.endswith(" " + phrase):
            base = text[: -len(phrase) - 1].strip()
            return NameClass("org", form, base or None)
    words = set(text.split())
    if words & _ORG_WORDS:
        return NameClass("org", None, text)
    return NameClass("unknown", None, None)
