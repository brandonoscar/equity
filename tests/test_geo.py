import pytest

from equity.geo import (
    counties,
    counties_in,
    county_by_fips,
    county_by_name,
    norm_county_name,
    state_fips,
)


def test_table_is_complete() -> None:
    assert len(counties()) == 3235
    assert len({c.state for c in counties()}) == 57  # 50 states, DC, PR and island areas
    assert len(counties_in("WV")) == 55


@pytest.mark.parametrize(
    ("state", "name", "fips5"),
    [
        ("WV", "Monongalia", "54061"),
        ("MD", "St. Mary's County", "24037"),
        ("MD", "SAINT MARYS", "24037"),
        ("LA", "Orleans Parish", "22071"),
        ("VA", "Richmond city", "51760"),
        ("VA", "Richmond", "51159"),
        ("AK", "Anchorage Municipality", "02020"),
    ],
)
def test_county_by_name(state: str, name: str, fips5: str) -> None:
    assert county_by_name(state, name).fips5 == fips5


def test_lookups_and_errors() -> None:
    assert state_fips("wv") == "54"
    assert county_by_fips("WV", 61).name == "Monongalia County"
    assert county_by_fips("WV", "54061").county_fips == "061"
    assert norm_county_name("St. Louis County") == "SAINT LOUIS"
    for bad in (
        lambda: state_fips("XX"),
        lambda: county_by_fips("WV", "999"),
        lambda: county_by_fips("WV", "24037"),
        lambda: county_by_name("WV", "Nowhere"),
    ):
        with pytest.raises(KeyError):
            bad()
