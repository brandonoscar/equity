"""WV parcel identifiers.

WV's Integrated Assessment System (IAS) id is shared by the state GIS layer (`ParcelID`) and
county layers (`parid`): 2-char district, 4-char map (space- or zero-padded), 4-char parcel,
4-char suffix, 4-char sub-suffix. WV counties are numbered 1-55 alphabetically, and their FIPS
codes are the odd numbers 001-109 in the same order.
"""

from __future__ import annotations

WV_STATE_FIPS = "54"


def county_fips(county_number: int) -> str:
    if not 1 <= county_number <= 55:
        raise ValueError(f"WV county number must be 1-55, got {county_number}")
    return f"{WV_STATE_FIPS}{2 * county_number - 1:03d}"


def normalize_parid(parid: str) -> str:
    """Canonical IAS id: spaces become zeros; 18-char ids keep their layout."""
    text = parid.strip("\n\r\t")
    if not text.strip():
        raise ValueError("empty parcel id")
    return text.replace(" ", "0").upper()


def parcel_uid(county_number: int, parid: str) -> str:
    return f"{county_fips(county_number)}-{normalize_parid(parid)}"


def parcel_uid_from_clean(clean_parcel_id: str) -> str:
    """From the state layer's CleanParcelID (2-digit county number + canonical IAS id)."""
    if len(clean_parcel_id) < 3 or not clean_parcel_id[:2].isdigit():
        raise ValueError(f"bad CleanParcelID {clean_parcel_id!r}")
    return f"{county_fips(int(clean_parcel_id[:2]))}-{clean_parcel_id[2:].upper()}"
