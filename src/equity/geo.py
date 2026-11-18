"""State and county FIPS lookups from the bundled Census 2020 table (deterministic, offline)."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import cache
from importlib import resources


@dataclass(frozen=True)
class County:
    state: str  # USPS abbreviation
    state_fips: str  # 2 digits
    county_fips: str  # 3 digits
    name: str  # e.g. "Monongalia County"

    @property
    def fips5(self) -> str:
        return self.state_fips + self.county_fips


_SUFFIXES = re.compile(
    r"\b(COUNTY|PARISH|BOROUGH|CENSUS AREA|CITY AND BOROUGH|MUNICIPALITY|MUNICIPIO|"
    r"PLANNING REGION)\b"
)


def norm_county_name(name: str) -> str:
    """'St. Mary's County' / 'SAINT MARYS' -> 'SAINT MARYS'. Independent cities keep CITY."""
    text = name.upper().replace(".", " ").replace("'", "")
    text = re.sub(r"\bST\b", "SAINT", text)
    text = re.sub(r"\bSTE\b", "SAINTE", text)
    text = _SUFFIXES.sub(" ", text)
    return " ".join(text.split())


@cache
def counties() -> tuple[County, ...]:
    text = resources.files("equity.data").joinpath("county_fips_2020.csv").read_text("utf-8")
    rows = csv.DictReader(text.splitlines())
    return tuple(County(r["state"], r["statefp"], r["countyfp"], r["countyname"]) for r in rows)


@cache
def state_fips(state: str) -> str:
    for c in counties():
        if c.state == state.upper():
            return c.state_fips
    raise KeyError(f"unknown state {state!r}")


def counties_in(state: str) -> list[County]:
    return [c for c in counties() if c.state == state.upper()]


@cache
def _by_name(state: str) -> dict[str, County]:
    out: dict[str, County] = {}
    for c in counties_in(state):
        key = norm_county_name(c.name)
        # Virginia etc. have "X County" and "X city": keep both distinguishable.
        if c.name.lower().endswith(" city"):
            key = norm_county_name(c.name[: -len(" city")]) + " CITY"
        out.setdefault(key, c)
    return out


def county_by_name(state: str, name: str) -> County:
    key = norm_county_name(name)
    table = _by_name(state.upper())
    if key in table:
        return table[key]
    raise KeyError(f"no county {name!r} in {state}")


def county_by_fips(state: str, code: str | int) -> County:
    text = str(code).strip()
    if len(text) == 5:
        if text[:2] != state_fips(state):
            raise KeyError(f"FIPS {text} is not in {state}")
        text = text[2:]
    fips3 = text.zfill(3)
    for c in counties_in(state):
        if c.county_fips == fips3:
            return c
    raise KeyError(f"no county FIPS {code!r} in {state}")
