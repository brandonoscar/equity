"""Zoning layer catalog: license rules, field picks, state lookup, catalog build, loader."""

from __future__ import annotations

import io
import json
import struct
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import PoliteClient
from equity.adapters.zoning import LocalZoningAdapter
from equity.zoning_catalog import (
    StateShape,
    build,
    contains,
    is_base_zoning,
    license_class,
    load_states,
    pick_field,
    read_shp_polygons,
    state_at,
)

SQUARE = ((0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0), (0.0, 0.0))
HOLE = ((4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0), (4.0, 4.0))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, "empty"),
        ("<p>&nbsp;</p>", "empty"),
        ("<p>Public Domain</p>", "open"),
        ("Licensed CC BY 4.0", "open"),
        ("The County accepts no liability for errors or omissions.", "disclaimer"),
        ("Data provided as-is for informational purposes.", "disclaimer"),
        ("Not for commercial use. No liability.", "restricted"),
        ("Shall not use lists of names to sell (K.S.A. 45-230).", "restricted"),
        ("May not be resold or redistributed without written permission.", "restricted"),
        ("Public domain, but subject to a license agreement is required", "restricted"),
    ],
)
def test_license_class(text: str | None, expected: str) -> None:
    assert license_class(text) == expected


def test_base_zoning_titles() -> None:
    assert is_base_zoning("Zoning Districts")
    assert is_base_zoning("City of Elkins Zoning")
    for t in ("Zoning History", "Rezoning Cases", "Proposed Zoning", "Zoning Buffer", "Parcels"):
        assert not is_base_zoning(t)


def test_pick_field_is_case_insensitive_and_ordered() -> None:
    assert pick_field(["objectid", "Zone_Code", "Zoning"], ("ZONING", "ZONE_CODE")) == "Zoning"
    assert pick_field(["A", "B"], ("ZONING",)) is None


def test_point_in_polygon_with_hole() -> None:
    assert contains([SQUARE], 1, 1)
    assert not contains([SQUARE, HOLE], 5, 5)
    assert not contains([SQUARE], 11, 5)
    s = StateShape("54", (0, 0, 10, 10), (SQUARE,))
    assert state_at([s], 1, 1) == "54"
    assert state_at([s], 20, 20) is None


def _shp(rings: list[tuple[tuple[float, float], ...]], with_point: bool = False) -> bytes:
    pts = [p for r in rings for p in r]
    parts, k = [], 0
    for r in rings:
        parts.append(k)
        k += len(r)
    body = struct.pack("<i", 5) + struct.pack("<4d", 0, 0, 10, 10)
    body += struct.pack("<ii", len(rings), len(pts)) + struct.pack(f"<{len(parts)}i", *parts)
    body += b"".join(struct.pack("<dd", *p) for p in pts)
    point = struct.pack("<i", 1) + struct.pack("<dd", 1, 1)  # a non-polygon record
    recs = struct.pack(">ii", 1, len(body) // 2) + body
    if with_point:
        recs += struct.pack(">ii", 2, len(point) // 2) + point
    return b"\0" * 100 + recs


def test_shapefile_reader_and_state_loading() -> None:
    shp = _shp([SQUARE, HOLE], with_point=True)
    got = list(read_shp_polygons(shp))
    assert got[0] == [list(SQUARE), list(HOLE)]
    assert got[1] == []
    # a dBASE table with one STATEFP column and one row
    header = struct.pack("<BBBBIHH20x", 3, 126, 1, 1, 1, 32 + 32 + 1, 1 + 2)
    field = b"STATEFP".ljust(11, b"\0") + b"C" + b"\0" * 4 + bytes([2, 0]) + b"\0" * 14
    dbf = header + field + b"\r" + b" 54" + b"\x1a"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("s.shp", _shp([SQUARE]))
        z.writestr("s.dbf", dbf)
    states = load_states(buf.getvalue())
    assert [(s.fips, s.box) for s in states] == [("54", (0.0, 0.0, 10.0, 10.0))]


def _client(routes: Mapping[str, Any]) -> PoliteClient:
    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        for key, body in routes.items():
            if key in url:
                return 200, json.dumps(body).encode(), "application/json"
        return 404, b"{}", "application/json"

    return PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None)


def _item(i: str, title: str, lic: str, host: str = "services1.arcgis.com",
          ext: list[list[float]] | None = None) -> dict[str, Any]:  # fmt: skip
    return {"id": i, "title": title, "owner": "o", "licenseInfo": lic,
            "accessInformation": "Town of X", "url": f"https://{host}/a/FeatureServer",
            "extent": ext or [[1.0, 1.0], [3.0, 3.0]]}  # fmt: skip


def test_build_sorts_items_into_layers_review_and_excluded() -> None:
    items = [
        _item("a", "Zoning", "Public Domain"),
        _item("b", "Zoning History", "Public Domain"),
        _item("c", "Zoning", "Not for commercial use"),
        _item("d", "Zoning", ""),
        _item("e", "Zoning", "no liability", host="gis.city.test"),
        _item("f", "Zoning", "no liability", ext=[[50, 50], [51, 51]]),
    ]
    routes = {
        "sharing/rest/search": {"results": items, "nextStart": -1},
        "FeatureServer/0?": {
            "objectIdField": "FID",
            "fields": [
                {"name": "FID"},
                {"name": "ZONING"},
                {"name": "ZONE_DESC"},
                {"name": "MUNI"},
            ],
        },
        "FeatureServer?": {"layers": [{"id": 0, "geometryType": "esriGeometryPolygon"}]},
    }
    states = [StateShape("54", (0, 0, 10, 10), (SQUARE,))]
    cat = build(_client(routes), states)
    assert [e["item_id"] for e in cat["layers"]] == ["a"]
    a = cat["layers"][0]
    assert a["state_fips"] == "54" and a["order_by"] == "FID"
    assert a["fields"] == {"zone_code": "ZONING", "zone_desc": "ZONE_DESC", "jurisdiction": "MUNI"}
    assert {e["item_id"]: e["reason"] for e in cat["excluded"]} == {
        "b": "not base zoning", "c": "license restricts use"}  # fmt: skip
    reasons = {e["item_id"]: e["reason"] for e in cat["review"]}
    assert reasons["d"] == "no license text"
    assert reasons["e"].startswith("host gis.city.test")
    assert reasons["f"] == "extent center outside every state"


class _Local(LocalZoningAdapter):
    catalog_path: ClassVar[Path]


def test_local_adapter_plans_fetches_and_normalizes(tmp_path: Path) -> None:
    url = "https://services1.arcgis.com/a/FeatureServer/0"
    cat = {"loadable_license_classes": ["open", "disclaimer"], "layers": [
        {"item_id": "a", "title": "Zoning", "access": "Town of X", "license_class": "open",
         "state_fips": "54", "layer_url": url, "order_by": "FID",
         "fields": {"zone_code": "ZONING"}},
        {"item_id": "z", "title": "Zoning", "access": "", "license_class": "empty",
         "state_fips": "54", "layer_url": url, "order_by": "FID", "fields": {}},
    ], "review": [], "excluded": []}  # fmt: skip
    path = tmp_path / "local.json"
    path.write_text(json.dumps(cat))
    _Local.catalog_path = path
    ring = [[-80.0, 39.0], [-79.0, 39.0], [-79.0, 40.0], [-80.0, 39.0]]
    feats = [{"attributes": {"FID": 3, "ZONING": "R-1"}, "geometry": {"rings": [ring]}}]
    routes = {"returnIdsOnly": {"objectIds": [3, 1]},
              "query": {"features": feats, "exceededTransferLimit": False}}  # fmt: skip
    a = _Local(_client(routes))
    assert list(a.items) == ["a"]  # the empty-license layer is not loaded
    assert list(a.partitions()) == [{"item": "a", "oid_min": "1", "oid_max": "4"}]
    f = a.fetch(FetchRequest({"item": "a", "oid_min": "1", "oid_max": "4"}))
    rows = [r.row for r in a.normalize(f) if r.table == "zoning_district"]
    assert [(r["zone_uid"], r["zone_code"], r["jurisdiction_name"], r["jurisdiction"])
            for r in rows] == [("a-3", "R-1", "Town of X", "54")]  # fmt: skip
    gone = Fetched(a.source_id, "x", datetime(2026, 11, 20, tzinfo=UTC), 200,
                   json.dumps({"item": "old", "features": feats}).encode(), "")  # fmt: skip
    assert list(a.normalize(gone)) == []
    assert a.health().ok and a.source_row()["kind"] == "zoning"
