import pytest

from equity.adapters.wv.parcel_ids import (
    county_fips,
    normalize_parid,
    parcel_uid,
    parcel_uid_from_clean,
)


@pytest.mark.parametrize(
    ("n", "fips"),
    [(1, "54001"), (20, "54039"), (31, "54061"), (55, "54109")],  # Barbour, Kanawha, Mon, Wyoming
)
def test_county_fips(n: int, fips: str) -> None:
    assert county_fips(n) == fips


@pytest.mark.parametrize("n", [0, 56, -1])
def test_county_fips_range(n: int) -> None:
    with pytest.raises(ValueError, match="1-55"):
        county_fips(n)


@pytest.mark.parametrize(
    ("parid", "clean"),
    [
        ("01   1000100000000", "31010001000100000000"),  # state ParcelID == county parid
        ("15  51000300010000", "31150051000300010000"),
        ("150051000300010000", "31150051000300010000"),  # the duplicate spelling
        ("01000012", "3101000012"),
        ("07 06B000300100000", "3107006B000300100000"),
    ],
)
def test_state_and_county_ids_agree(parid: str, clean: str) -> None:
    assert parcel_uid(31, parid) == parcel_uid_from_clean(clean)


def test_bad_ids() -> None:
    with pytest.raises(ValueError, match="empty"):
        normalize_parid("   ")
    with pytest.raises(ValueError, match="bad CleanParcelID"):
        parcel_uid_from_clean("X1")
