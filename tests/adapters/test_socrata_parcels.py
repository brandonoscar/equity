"""Config-driven Socrata / CKAN parcel-owner adapters: config validation, normalization on an
inline table, pii fields, partitioning and paging (offline, fake client), and every config in
config/socrata_parcels/ against its recorded fixture."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from equity.adapters.base import REGISTRY, Fetched, FetchRequest, register
from equity.adapters.http import Response
from equity.adapters.socrata_parcels import (
    ApiParcelAdapter,
    all_api_parcel_adapters,
    api_adapter_for,
    api_config_paths,
    load_api_config,
)
from equity.adapters.state_parcels import StateConfigError
from equity.geo import state_fips

from ..test_fixture_privacy import _walk

FIX = Path(__file__).parents[1] / "fixtures" / "adapters"
AT = datetime(2026, 11, 25, 12, tzinfo=UTC)


def _cfg(tmp_path: Path, **over: Any) -> Path:
    base: dict[str, Any] = {
        "source_id": "zz.test.parcels", "state": "NY",
        "layer_url": "https://data.test/resource/abcd-1234.json",
        "order_by": "swis", "page_size": 2, "row_window": 3,
        "county": {"field": "county_name", "format": "code_map",
                   "code_map": {"Albany": "001", "St Lawrence": "089"}},
        "fields": {"parcel_id": ["swis", "key"],
                   "owner1": {"join": ["first", "last"]}, "owner2": "own2",
                   "mail_line1": {"join": ["mnum", "mstreet"]}, "mail_city": "mcity",
                   "mail_state": "mst", "mail_zip": "mzip",
                   "situs_line1": ["pnum", "pstreet"], "total_value": "fmv",
                   "assessed_value": "av", "tax_year": {"year_of": "rolldate"},
                   "homestead": "hmstd"},
        "value_basis": "test",
        "terms": {"summary": "s", "checked_on": "2026-11-25", "cost_model": "free"},
    }  # fmt: skip
    base.update(over)
    path = tmp_path / "zz.yaml"
    path.write_text(yaml.safe_dump(base))
    return path


def _rows(cls: type[ApiParcelAdapter], attrs: list[dict[str, Any]]) -> list[tuple[str, Any]]:
    body = json.dumps({"layer": "x", "where": "1=1", "row_min": 0, "attributes": attrs}).encode()
    f = Fetched(cls.source_id, "fixture://zz", AT, 200, body, "application/json")
    return [(r.table, dict(r.row)) for r in cls().normalize(f)]


class Client:
    """Answers Socrata count queries from `counts` (keyed by $where) and row pages from `rows`."""

    retries = 0
    backoff_s = 0.0

    def __init__(self, rows: list[dict[str, Any]] | None = None,
                 counts: dict[str, int] | None = None, ckan: bool = False) -> None:  # fmt: skip
        self.rows = rows or []
        self.counts = counts or {}
        self.ckan = ckan
        self.calls: list[dict[str, str]] = []

    def sleep(self, s: float) -> None:
        pass

    def now(self) -> datetime:
        return AT

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        p = dict(params or {})
        self.calls.append(p)
        if self.ckan:
            lo, n = int(p["offset"]), int(p["limit"])
            result = {"records": self.rows[lo : lo + n], "total": len(self.rows)}
            body: Any = {"success": True, "result": result}
        elif p.get("$select", "").startswith("count("):
            body = [{"n": str(self.counts.get(p["$where"], 0))}]
        else:
            lo, n = int(p["$offset"]), int(p["$limit"])
            body = self.rows[lo : lo + n]
        return Response(url, 200, json.dumps(body).encode(), "application/json", AT)


def test_normalize_emits_the_arcgis_row_set(tmp_path: Path) -> None:
    cls = api_adapter_for(load_api_config(_cfg(tmp_path)))
    out = _rows(cls, [
        {"swis": "010100", "key": "40.-3-1", "county_name": "Albany", "first": "ANN",
         "last": "LEE", "own2": "ACME LLC", "mnum": "1", "mstreet": "Main St", "mcity": "Albany",
         "mst": "NY", "mzip": "12203-1111", "pnum": "5", "pstreet": "Elm", "fmv": "20833",
         "av": "20000", "rolldate": "2025-07-01T00:00:00.000", "hmstd": True},
        {"swis": "010100", "key": "40.-3-2", "county_name": "Nowhere", "last": "SKIPPED"},
        {"swis": "010100", "county_name": "Albany", "last": "NO KEY"},
    ])  # fmt: skip
    counts = Counter(t for t, _ in out)
    assert counts == {"source_record": 1, "parcel": 1, "address": 2, "party": 2,
                      "owner_snapshot": 2, "parcel_assessment": 1}  # fmt: skip
    parcel = next(r for t, r in out if t == "parcel")
    assert parcel["parcel_uid"] == "36001-010100-40.-3-1"
    names = [r["raw_name"] for t, r in out if t == "party"]
    assert names == ["ANN LEE", "ACME LLC"]
    assessment = next(r for t, r in out if t == "parcel_assessment")
    assert assessment["tax_year"] == 2025 and assessment["valid_from"] == date(2025, 1, 1)
    assert assessment["appraised_total"] == "20833.00" and assessment["homestead"] is True
    mail = [r for t, r in out if t == "address" and r["zip5"] == "12203"]
    assert mail and mail[0]["line1"] == "1 MAIN ST"


def test_pii_fields_cover_list_and_join_columns(tmp_path: Path) -> None:
    cls = api_adapter_for(load_api_config(_cfg(tmp_path)))
    assert set(cls.pii_fields) == {"first", "last", "own2", "mnum", "mstreet", "pnum", "pstreet"}
    assert "fmv" not in cls.pii_fields and "county_name" in cls.fields
    assert cls.access_method == "api" and cls().source_row()["access_method"] == "api"


@pytest.mark.parametrize(("over", "message"), [
    ({"layer_url": "https://data.test/api/views/abcd-1234"}, "resource/<4x4>.json"),
    ({"api": "carto"}, "api must be one of"),
    ({"api": "ckan", "layer_url": "https://d.test/api/3/action/datastore_search",
      "county": {"constant": "001"}}, "resource_id"),
    ({"api": "ckan", "layer_url": "https://d.test/api/3/action/datastore_search",
      "resource_id": "r1"}, "constant county"),
    ({"county": {"field": "c", "format": "name"}}, "name format"),
])  # fmt: skip
def test_config_validation(tmp_path: Path, over: dict[str, Any], message: str) -> None:
    with pytest.raises(StateConfigError, match=message):
        load_api_config(_cfg(tmp_path, **over))


def test_code_map_partitions_count_each_mapped_county_and_cut_row_windows(tmp_path: Path) -> None:
    cls = api_adapter_for(load_api_config(_cfg(tmp_path, filter="roll_year = 2025")))
    client = Client(counts={"(roll_year = 2025) AND (county_name='Albany')": 7})
    plan = list(cls(client).partitions())  # type: ignore[arg-type]
    assert plan == [
        {"county_fips": "001", "row_min": "0", "row_max": "3"},
        {"county_fips": "001", "row_min": "3", "row_max": "6"},
        {"county_fips": "001", "row_min": "6", "row_max": "7"},
    ]  # St Lawrence counted 0 rows: no partition
    assert len(client.calls) == 2  # one count per mapped county, nothing for the other 60


def test_constant_county_partitions_are_row_windows(tmp_path: Path) -> None:
    cls = api_adapter_for(load_api_config(_cfg(tmp_path, county={"constant": "001"})))
    plan = list(cls(Client(counts={"1=1": 4})).partitions())  # type: ignore[arg-type]
    assert plan == [{"row_min": "0", "row_max": "3"}, {"row_min": "3", "row_max": "4"}]


def test_fetch_pages_inside_the_row_window_in_a_total_order(tmp_path: Path) -> None:
    cls = api_adapter_for(load_api_config(_cfg(tmp_path, county={"constant": "001"})))
    client = Client(rows=[{"swis": str(i)} for i in range(10)])
    f = cls(client).fetch(FetchRequest({"row_min": "3", "row_max": "8"}))  # type: ignore[arg-type]
    body = json.loads(f.content)
    assert [r["swis"] for r in body["attributes"]] == ["3", "4", "5", "6", "7"]
    pages = [(c["$offset"], c["$limit"]) for c in client.calls]
    assert pages == [("3", "2"), ("5", "2"), ("7", "1")]
    assert all(c["$order"] == "swis,:id" for c in client.calls)
    assert "row_min=3&row_max=8" in f.request
    sample = cls(Client(rows=[{"swis": "1"}] * 9)).fetch(  # type: ignore[arg-type]
        FetchRequest({"sample": "1", "limit": "4"})
    )
    assert len(json.loads(sample.content)["attributes"]) == 4


def test_ckan_datastore_fetch_count_and_health(tmp_path: Path) -> None:
    path = _cfg(tmp_path, api="ckan", resource_id="r-1", county={"constant": "001"},
                layer_url="https://d.test/api/3/action/datastore_search")  # fmt: skip
    cls = api_adapter_for(load_api_config(path))
    client = Client(rows=[{"swis": str(i), "_id": i} for i in range(5)], ckan=True)
    adapter = cls(client)  # type: ignore[arg-type]
    assert list(adapter.partitions()) == [{"row_min": "0", "row_max": "3"},
                                          {"row_min": "3", "row_max": "5"}]  # fmt: skip
    f = adapter.fetch(FetchRequest({"row_min": "0", "row_max": "3"}))
    assert [r["swis"] for r in json.loads(f.content)["attributes"]] == ["0", "1", "2"]
    assert client.calls[-1]["sort"] == "swis,_id" and client.calls[-1]["resource_id"] == "r-1"
    assert adapter.health().ok
    assert adapter.source_row()["base_url"].endswith("?resource_id=r-1")


def test_health_selects_every_mapped_column(tmp_path: Path) -> None:
    cls = api_adapter_for(load_api_config(_cfg(tmp_path)))
    client = Client(rows=[{"swis": "1"}])
    report = cls(client).health()  # type: ignore[arg-type]
    assert report.ok and report.shape == tuple(sorted(cls.fields))
    assert client.calls[0]["$select"] == ",".join(cls.fields)
    assert not cls(Client()).health().ok  # type: ignore[arg-type]


# --- every real config -------------------------------------------------------------------

CONFIGS = api_config_paths()


def test_all_configs_load_with_unique_new_source_ids() -> None:
    import equity.adapters.registry  # noqa: F401  (the production registry)

    adapters = all_api_parcel_adapters()
    assert len(adapters) == len(CONFIGS) >= 4
    ids = [a.source_id for a in adapters]
    assert len(set(ids)) == len(ids)
    taken = {c.source_id for c in REGISTRY if not issubclass(c, ApiParcelAdapter)}
    assert not set(ids) & taken
    for cls in adapters:  # registering is idempotent; registry.py will list them later
        if cls not in REGISTRY:
            register(cls)
    assert {c.source_id for c in REGISTRY} >= set(ids)


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.stem)
def test_config_against_fixture(path: Path) -> None:
    cls = api_adapter_for(load_api_config(path))
    fixtures = sorted((FIX / cls.source_id).glob("*.json"))
    assert fixtures, f"{cls.source_id}: record a fixture with equity.adapters.record"
    out: list[tuple[str, Any]] = []
    for fx in fixtures:
        data = json.loads(fx.read_text())
        assert _walk(data, cls.pii_fields) == [], fx.name  # pseudonyms only
        f = Fetched(cls.source_id, "fixture://s", AT, 200, fx.read_bytes(), "application/json")
        out += [(r.table, dict(r.row)) for r in cls().normalize(f)]
    parcels = [r for t, r in out if t == "parcel"]
    assert len(parcels) >= 5, "fixture should yield at least 5 parcels"
    assert all(r["parcel_uid"].startswith(state_fips(cls.config.state)) for r in parcels)
    assert any(t == "owner_snapshot" for t, _ in out)
