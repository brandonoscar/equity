"""Shared ArcGIS adapter behavior: county fetch, sampling, health shape check. Offline."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from equity.adapters.arcgis_adapter import ArcGISCountyAdapter
from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import PoliteClient
from equity.adapters.wv.delinquent import FIELDS, WVDelinquentProperties


def fake_client(pages: list[dict[str, object]], status: int = 200) -> PoliteClient:
    calls: list[str] = []

    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("/robots.txt"):
            return 404, b"", ""
        calls.append(url)
        # Replay the last page once exhausted (retries on 5xx ask again).
        page = pages[min(len(calls), len(pages)) - 1]
        return status, json.dumps(page).encode(), "application/json"

    return PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None,
                        now=lambda: datetime(2026, 11, 15, tzinfo=UTC))  # fmt: skip


def _feat(oid: int) -> dict[str, object]:
    return {"attributes": {f: None for f in FIELDS} | {"OBJECTID": oid}}


def test_fetch_whole_county_and_sample() -> None:
    pages = [{"features": [_feat(1), _feat(2)], "exceededTransferLimit": True},
             {"features": [_feat(3)]}]  # fmt: skip
    f = WVDelinquentProperties(fake_client(pages)).fetch(FetchRequest({"county_number": "31"}))
    data = json.loads(f.content)
    assert [a["OBJECTID"] for a in data["attributes"]] == [1, 2, 3]
    assert data["where"] == "CountyID='31'"
    assert f.retrieved_at == datetime(2026, 11, 15, tzinfo=UTC)
    sample = WVDelinquentProperties(fake_client(pages)).fetch(
        FetchRequest({"county_number": "31", "limit": "2"})
    )
    assert len(json.loads(sample.content)["attributes"]) == 2


def test_health_compares_field_shape() -> None:
    ok = WVDelinquentProperties(fake_client([{"features": [_feat(1)]}])).health()
    assert ok.ok
    assert ok.shape == tuple(sorted(FIELDS))
    changed = {"features": [{"attributes": {"OBJECTID": 1, "renamed": 2}}]}
    bad = WVDelinquentProperties(fake_client([changed])).health()
    assert not bad.ok
    assert "renamed" in bad.detail
    down = WVDelinquentProperties(fake_client([{}], status=503)).health()
    assert not down.ok


def test_health_handles_non_json() -> None:
    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        return (404, b"", "") if url.endswith("robots.txt") else (502, b"<html>", "text/html")

    c = PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None)
    assert not WVDelinquentProperties(c).health().ok


def test_base_requires_overrides() -> None:
    class Bare(ArcGISCountyAdapter):
        source_id = "wv.statewide.delinquent"
        adapter_version = "1"
        layer_url = "x"
        fields = ("A",)
        health_where = "1=1"

        def source_row(self) -> Mapping[str, object]:
            return {}

    bare = Bare()
    with pytest.raises(NotImplementedError):
        bare.where(FetchRequest({}))
    with pytest.raises(NotImplementedError):
        list(bare.normalize(Fetched("x", "x", datetime(2026, 1, 1, tzinfo=UTC), 200, b"", "")))
    with pytest.raises(ValueError, match="attributes"):
        bare.attributes(Fetched("x", "x", datetime(2026, 1, 1, tzinfo=UTC), 200,
                                b'{"attributes": 1}', ""))  # fmt: skip
