"""Lake gap report: built from synthetic _state.json bundles, no network."""

from __future__ import annotations

import json

from equity.lake_gaps import parse_bundle, render


def _bundle(
    total: dict[str, int], parts: list[tuple[str | None, dict[str, int]]]
) -> dict[str, str]:
    out = {"_counts.json": json.dumps(total)}
    for i, (fips3, counts) in enumerate(parts):
        params = {"county_fips": fips3} if fips3 else {"oid_min": "1"}
        out[f"_parts/{i:05d}.json"] = json.dumps({"counts": counts, "params": params})
    return out


def test_parts_split_by_county() -> None:
    parts: list[tuple[str | None, dict[str, int]]] = [
        ("001", {"parcel": 10, "owner_snapshot": 10}),
        ("003", {"parcel": 20}),
    ]
    b = _bundle({"parcel": 30, "owner_snapshot": 10}, parts)
    g = parse_bundle("de.statewide.parcels", b, "10")
    assert g.fill.parcels == 30
    assert {k: (f.parcels, f.owners) for k, f in g.by_county.items()} == {
        "10001": (10, 10), "10003": (20, 0)}  # fmt: skip
    assert (
        parse_bundle("x.statewide.parcels", _bundle({}, [(None, {"parcel": 1})]), "10").by_county
        == {}
    )


def test_render_reports_unbuilt_empty_fields_and_counties() -> None:
    bundles = {
        # Delaware statewide: Kent (001) has owners, New Castle (003) none, Sussex (005) missing.
        "de.statewide.parcels": _bundle(
            {"parcel": 30, "owner_snapshot": 10, "parcel_assessment": 30, "address": 30},
            [("001", {"parcel": 10, "owner_snapshot": 10, "parcel_assessment": 10}),
             ("003", {"parcel": 20, "parcel_assessment": 20})]),
        "de.old.parcels": _bundle({"parcel": 1}, []),
        "de.half.parcels": None,
    }  # fmt: skip
    md = render(["de.statewide.parcels", "de.half.parcels", "de.never.parcels"], bundles)
    assert "Registered but not built: 2 of 3" in md
    assert "`de.half.parcels` `de.never.parcels`" in md
    assert "`de.old.parcels`" in md.split("no longer registered")[1]
    assert "| `de.statewide.parcels` | 30 | 33% | 100% | 100% |" in md
    assert "| DE | 1 of 3 | 1: Sussex | 1: New Castle | — |" in md


def test_county_layer_is_matched_by_its_slug() -> None:
    bundles = {"wv.monongalia.parcels": _bundle({"parcel": 5, "owner_snapshot": 5}, [])}
    md = render(["wv.monongalia.parcels"], bundles)
    wv = next(line for line in md.splitlines() if line.startswith("| WV |"))
    assert wv.startswith("| WV | 1 of 55 |")


def test_independent_city_is_not_its_namesake_county() -> None:
    bundles = {"md.baltimore_city.parcels": _bundle({"parcel": 5, "owner_snapshot": 5}, [])}
    md = render(["md.baltimore_city.parcels"], bundles)
    md_row = next(line for line in md.splitlines() if line.startswith("| MD |"))
    assert "Baltimore city" not in md_row.split("|")[3]  # not listed as missing
    assert " Baltimore," in md_row.split("|")[3]  # the county still is
