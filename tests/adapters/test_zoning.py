"""Zoning district adapter: config checks, id-window plan, polygon rows."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import PoliteClient
from equity.adapters.zoning import (
    ZoningConfigError,
    all_zoning_adapters,
    load_zoning_config,
    zoning_adapter_for,
)

AT = datetime(2026, 11, 20, tzinfo=UTC)
URL = "https://x.test/FeatureServer/0"


def _cfg(tmp_path: Path, **over: Any) -> Path:
    base: dict[str, Any] = {
        "source_id": "zz.test.zoning", "state": "WV", "layers": [URL], "page_size": 2,
        "fields": {"jurisdiction": "J", "zone_code": "C", "zone_desc": "D", "zone_class": "K"},
        "terms": {"summary": "s", "checked_on": "2026-11-20", "cost_model": "free"},
    }  # fmt: skip
    base.update(over)
    path = tmp_path / "z.yaml"
    path.write_text(yaml.safe_dump(base))
    return path


def _client(body: dict[str, Any]) -> PoliteClient:
    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        return 200, json.dumps(body).encode(), "application/json"

    return PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None)


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"fields": {"bogus": "X"}}, "unknown fields"),
        ({"terms": {"summary": "s"}}, "terms.checked_on"),
        ({"source_id": "zz.test.parcels"}, "must end with .zoning"),
        ({"layers": None, "state": "WV"}, None),
    ],
)
def test_config_validation(tmp_path: Path, over: dict[str, Any], message: str | None) -> None:
    if message is None:  # a missing required key
        p = tmp_path / "bad.yaml"
        p.write_text("source_id: zz.x.zoning\n")
        with pytest.raises(ZoningConfigError, match="missing"):
            load_zoning_config(p)
        return
    with pytest.raises(ZoningConfigError, match=message):
        load_zoning_config(_cfg(tmp_path, **over))


def test_partitions_follow_the_id_list(tmp_path: Path) -> None:
    cls = zoning_adapter_for(load_zoning_config(_cfg(tmp_path)))
    plan = list(cls(_client({"objectIds": [9, 1, 2, 3]})).partitions())
    assert plan == [{"layer": "0", "oid_min": "1", "oid_max": "3"},
                    {"layer": "0", "oid_min": "3", "oid_max": "10"}]  # fmt: skip
    with pytest.raises(ZoningConfigError, match="id list"):
        list(cls(_client({"error": {"code": 400}})).partitions())
    a = cls(_client({}))
    assert a.where(FetchRequest({"oid_min": "3", "oid_max": "10"})) == "OBJECTID>=3 AND OBJECTID<10"
    assert a.where(FetchRequest({})) == "1=1"


def test_normalize_keeps_rings_box_and_fields(tmp_path: Path) -> None:
    cls = zoning_adapter_for(load_zoning_config(_cfg(tmp_path)))
    ring = [[-80.1234567, 39.1], [-80.0, 39.1], [-80.0, 39.2], [-80.1234567, 39.1]]
    hole = [[-80.05, 39.12], [-80.04, 39.12], [-80.04, 39.13], [-80.05, 39.12]]
    body = {"layer": URL, "where": "1=1", "features": [
        {"attributes": {"OBJECTID": 7, "J": " Elkins ", "C": "R-1", "D": "Residential",
                        "K": ""}, "geometry": {"rings": [ring, hole]}},
        {"attributes": {"OBJECTID": 8, "C": "C-2"}, "geometry": None},
        {"attributes": {"C": "X"}, "geometry": {"rings": [ring]}},
    ]}  # fmt: skip
    f = Fetched(cls.source_id, URL + "/query", AT, 200, json.dumps(body).encode(), "")
    rows = list(cls(_client({})).normalize(f))
    zones = [r.row for r in rows if r.table == "zoning_district"]
    assert len(zones) == 1  # no shape, or no object id: skipped
    z = zones[0]
    assert (z["zone_uid"], z["jurisdiction_name"], z["zone_code"], z["zone_desc"],
            z["zone_class"]) == ("0-7", "Elkins", "R-1", "Residential", None)  # fmt: skip
    assert json.loads(z["geom_rings"])[0][0] == [-80.123457, 39.1]
    assert (z["xmin"], z["ymin"], z["xmax"], z["ymax"]) == (-80.123457, 39.1, -80.0, 39.2)
    assert z["jurisdiction"] == "54" and z["source_id"] == "zz.test.zoning"
    assert cls(_client({})).source_row()["kind"] == "zoning"


def test_health_counts_districts(tmp_path: Path) -> None:
    cls = zoning_adapter_for(load_zoning_config(_cfg(tmp_path)))
    assert cls(_client({"count": 12})).health().ok
    assert not cls(_client({"count": 0})).health().ok


def test_real_zoning_configs_load() -> None:
    ids = {a.source_id for a in all_zoning_adapters()}
    assert {"ca.statewide.zoning", "wa.statewide.zoning", "ri.statewide.zoning"} <= ids
