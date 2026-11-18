"""Generic statewide parcel adapter: config validation, county handling, normalization, and a
check of every config in config/states/ against its recorded fixture."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.state_parcels import (
    StateConfigError,
    adapter_for,
    all_state_adapters,
    config_paths,
    load_config,
    norm_parcel_id,
)
from equity.geo import state_fips

FIX = Path(__file__).parents[1] / "fixtures" / "adapters"
AT = datetime(2026, 11, 15, 12, tzinfo=UTC)


def _cfg(tmp_path: Path, **over: Any) -> Path:
    base: dict[str, Any] = {
        "source_id": "zz.test.parcels", "state": "WV", "layer_url": "https://x.test/FeatureServer/0/",
        "order_by": "OID", "page_size": 2, "county": {"field": "CO", "format": "fips3"},
        "fields": {"parcel_id": "PID", "owner1": "OWN", "owner2": "OWN2", "mail_line1": "M1",
                   "mail_city": "MC", "mail_state": "MS", "mail_zip": "MZ", "total_value": "TV",
                   "tax_year": {"const": 2025}},
        "value_basis": "test", "terms": {"summary": "s", "checked_on": "2026-11-15",
                                         "cost_model": "free"},
    }  # fmt: skip
    base.update(over)
    path = tmp_path / "zz.yaml"
    path.write_text(yaml.safe_dump(base))
    return path


def _rows(cls, attrs: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:  # type: ignore[no-untyped-def]
    body = json.dumps({"layer": "x", "where": "1=1", "attributes": attrs}).encode()
    f = Fetched(cls.source_id, "fixture://zz", AT, 200, body, "application/json")
    return [(r.table, dict(r.row)) for r in cls().normalize(f)]


def test_normalize_maps_fields(tmp_path: Path) -> None:
    cls = adapter_for(load_config(_cfg(tmp_path)))
    out = _rows(cls, [
        {"OID": 2, "PID": "01 23-4", "CO": "061", "OWN": "ACME LLC", "OWN2": "", "M1": "1 Main",
         "MC": "Morgantown", "MS": "WV", "MZ": "26505", "TV": "1,500"},
        {"OID": 1, "PID": "0123-4", "CO": "061", "OWN": "First Row Wins", "TV": 9},
        {"OID": 3, "PID": "77", "CO": "999", "OWN": "Bad County"},
        {"OID": 4, "PID": None, "CO": "061"},
    ])  # fmt: skip
    c = Counter(t for t, _ in out)
    assert c["parcel"] == 1  # duplicate ids collapse; bad county and missing id skipped
    (parcel,) = [r for t, r in out if t == "parcel"]
    assert parcel["parcel_uid"] == "54061-0123-4"
    (party,) = [r for t, r in out if t == "party"]
    assert party["raw_name"] == "First Row Wins"  # lowest order_by value
    (a,) = [r for t, r in out if t == "parcel_assessment"]
    assert (a["tax_year"], a["appraised_total"], a["valid_from"]) == (
        2025,
        "9.00",
        date(2025, 1, 1),
    )


def test_address_and_org(tmp_path: Path) -> None:
    cls = adapter_for(load_config(_cfg(tmp_path)))
    out = _rows(cls, [{"OID": 1, "PID": "9", "CO": "61", "OWN": "ACME LLC", "M1": "1 Main",
                       "MC": "Morgantown", "MS": "WV", "MZ": "26505-1111",
                       "TV": "-5"}])  # fmt: skip
    (addr,) = [r for t, r in out if t == "address"]
    assert addr["zip5"] == "26505"
    (party,) = [r for t, r in out if t == "party"]
    assert party["org_form"] == "LLC"
    assert party["address_id"] == addr["address_id"]
    assert not [r for t, r in out if t == "parcel_assessment"]  # negative value dropped


@pytest.mark.parametrize(
    ("county", "value", "where", "fips5"),
    [
        ({"field": "C", "format": "fips3"}, "061", "C='061'", "54061"),
        ({"field": "C", "format": "fips5"}, "54061", "C='54061'", "54061"),
        ({"field": "C", "format": "int"}, 61, "C=61", "54061"),
        ({"field": "C", "format": "code_map", "code_map": {"31": "061"}}, "31", "C='31'", "54061"),
        ({"constant": "061"}, None, "1=1", "54061"),
    ],
)
def test_county_formats(tmp_path: Path, county: dict[str, Any], value: Any, where: str,
                        fips5: str) -> None:  # fmt: skip
    cls = adapter_for(load_config(_cfg(tmp_path, county=county)))
    a = cls()
    assert a.where(FetchRequest({"county_fips": "061"})) == where
    assert a.county_of({"C": value}).fips5 == fips5


def test_name_format_and_other_partitions(tmp_path: Path) -> None:
    cls = adapter_for(load_config(_cfg(tmp_path, county={"field": "C", "format": "name"})))
    a = cls()
    assert a.county_of({"C": "monongalia"}).fips5 == "54061"
    with pytest.raises(StateConfigError, match="oid range"):
        a.where(FetchRequest({"county_fips": "061"}))
    assert a.where(FetchRequest({"oid_min": "1", "oid_max": "5"})) == "OID>=1 AND OID<5"
    assert a.where(FetchRequest({"sample": "1"})) == "1=1"
    with pytest.raises(StateConfigError, match="need"):
        a.where(FetchRequest({}))
    with pytest.raises(KeyError):
        a.county_of({"C": ""})


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"fields": {"owner1": "X"}}, "parcel_id"),
        ({"fields": {"parcel_id": "P", "bogus": "X"}}, "unknown canonical"),
        ({"county": {"field": "C"}}, "county needs"),
        ({"county": {"field": "C", "format": "code_map"}}, "code_map"),
        ({"terms": {"summary": "s"}}, "terms.checked_on"),
        ({"state": "XX"}, "unknown state"),
    ],
)
def test_config_validation(tmp_path: Path, over: dict[str, Any], message: str) -> None:
    with pytest.raises((StateConfigError, KeyError), match=message):
        load_config(_cfg(tmp_path, **over))


def test_config_requires_keys(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("source_id: x\n")
    with pytest.raises(StateConfigError, match="missing"):
        load_config(p)
    p.write_text("- 1\n")
    with pytest.raises(StateConfigError, match="mapping"):
        load_config(p)


def test_norm_parcel_id() -> None:
    assert norm_parcel_id(" 01 23-4a ") == "0123-4A"


def test_year_of_and_pii(tmp_path: Path) -> None:
    fields = {"parcel_id": "PID", "owner1": "OWN", "mail_line1": "M1", "total_value": "TV",
              "tax_year": {"year_of": "D"}}  # fmt: skip
    cls = adapter_for(load_config(_cfg(tmp_path, fields=fields, extra_pii=["SITUS"])))
    assert cls.pii_fields == ("M1", "OWN", "SITUS")
    assert "D" in cls.fields
    out = _rows(cls, [{"OID": 1, "PID": "1", "CO": "061", "TV": 5, "D": 1767225600000},
                      {"OID": 2, "PID": "2", "CO": "061", "TV": 5, "D": None}])  # fmt: skip
    years = sorted(r["tax_year"] for t, r in out if t == "parcel_assessment")
    assert years == [2026]


# --- every real state config ------------------------------------------------------------

CONFIGS = config_paths()


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.stem)
def test_state_config_against_fixture(path: Path) -> None:
    cfg = load_config(path)
    fixtures = sorted((FIX / cfg.source_id).glob("*.json"))
    assert fixtures, f"{cfg.source_id}: record a fixture with equity.adapters.record"
    cls = adapter_for(cfg)
    out: list[tuple[str, dict[str, Any]]] = []
    for fx in fixtures:
        out += [
            (r.table, dict(r.row))
            for r in cls().normalize(
                Fetched(cls.source_id, "fixture://s", AT, 200, fx.read_bytes(), "application/json")
            )
        ]
    parcels = [r for t, r in out if t == "parcel"]
    assert len(parcels) >= 5, "fixture should yield at least 5 parcels"
    assert all(r["parcel_uid"].startswith(state_fips(cfg.state)) for r in parcels)
    assert any(t == "owner_snapshot" for t, _ in out) or "owner1" not in cfg.fields


def test_all_configs_load() -> None:
    adapters = all_state_adapters()
    assert len(adapters) == len(CONFIGS)
    assert len({a.source_id for a in adapters}) == len(adapters)


def test_partitions_by_county_and_by_oid_window(tmp_path: Path) -> None:
    cls = adapter_for(load_config(_cfg(tmp_path)))
    plan = list(cls().partitions())
    assert len(plan) == 55
    assert plan[30] == {"county_fips": "061"}

    from collections.abc import Mapping as _M

    from equity.adapters.http import PoliteClient

    def transport(url: str, headers: _M[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        body = {"features": [{"attributes": {"lo": 1, "hi": 120000}}]}
        return 200, json.dumps(body).encode(), "application/json"

    named = adapter_for(load_config(_cfg(tmp_path, county={"field": "C", "format": "name"})))
    client = PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None)
    windows = list(named(client).partitions(window=50_000))
    assert windows == [{"oid_min": "1", "oid_max": "50001"},
                       {"oid_min": "50001", "oid_max": "100001"},
                       {"oid_min": "100001", "oid_max": "150001"}]  # fmt: skip


def test_use_restrictions_are_recorded_in_source_terms(tmp_path: Path) -> None:
    cls = adapter_for(
        load_config(_cfg(tmp_path, use_restrictions=["no_resale", "no_mailing_list"]))
    )
    assert cls.config.use_restrictions == ("no_mailing_list", "no_resale")
    assert cls().source_row()["terms_summary"].startswith("RESTRICTED[no_mailing_list,no_resale] ")
    plain = adapter_for(load_config(_cfg(tmp_path)))
    assert not plain().source_row()["terms_summary"].startswith("RESTRICTED")


@pytest.mark.parametrize(
    ("text", "parsed"),
    [
        ("123 N MAIN ST , MADISON, WI 53703", ("123 N MAIN ST", "MADISON", "WI", "53703")),
        ("PO BOX 9 , EAU CLAIRE, wi 54701-1234", ("PO BOX 9", "EAU CLAIRE", "WI", "54701")),
        ("123 MAIN ST ANYTOWN WI 53703", ("123 MAIN ST ANYTOWN WI 53703", None, None, None)),
    ],
)
def test_parse_full_address(text: str, parsed: tuple[str | None, ...]) -> None:
    from equity.adapters.state_parcels import parse_full_address

    assert parse_full_address(text) == parsed


def test_mail_full_used_when_no_split_fields(tmp_path: Path) -> None:
    fields = {"parcel_id": "PID", "owner1": "OWN", "mail_full": "ADDR", "total_value": "TV",
              "tax_year": {"const": 2025}}  # fmt: skip
    cls = adapter_for(load_config(_cfg(tmp_path, fields=fields)))
    assert "ADDR" in cls.pii_fields
    out = _rows(cls, [{"OID": 1, "PID": "1", "CO": "061", "OWN": "X", "TV": 1,
                       "ADDR": "1 MAIN ST , MORGANTOWN, WV 26505"}])  # fmt: skip
    (addr,) = [r for t, r in out if t == "address"]
    assert (addr["line1"], addr["city"], addr["state"], addr["zip5"]) == (
        "1 MAIN ST", "MORGANTOWN", "WV", "26505")  # fmt: skip


def _fake_server(responses: list[dict[str, Any]], seen: list[str]):  # type: ignore[no-untyped-def]
    from collections.abc import Mapping as _M

    from equity.adapters.http import PoliteClient

    served: list[str] = []

    def transport(url: str, headers: _M[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        seen.append(url)
        served.append(url)
        return 200, json.dumps(responses[len(served) - 1]).encode(), "application/json"

    return PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None,
                        now=lambda: AT)  # fmt: skip


def test_multiple_layers_with_per_layer_county(tmp_path: Path) -> None:
    layers = [{"url": "https://x.test/FS/1", "county": {"constant": "001"}},
              "https://x.test/FS/2/"]  # fmt: skip
    cfg = load_config(_cfg(tmp_path, layers=layers))
    assert cfg.layer_count == 2
    assert cfg.layer_url == "https://x.test/FeatureServer/0"  # explicit layer_url kept
    cls = adapter_for(cfg)
    seen: list[str] = []
    stats = {"features": [{"attributes": {"lo": 1, "hi": 3}}]}
    plan = list(cls(_fake_server([stats, {"count": 3}], seen)).partitions(window=10))
    assert plan[0] == {"layer": "0", "oid_min": "1", "oid_max": "11"}  # constant county
    assert plan[1] == {"layer": "1", "county_fips": "001"}  # county field on layer 2
    page = {"features": [{"attributes": {"OID": 1, "PID": "9", "TV": 5}}]}
    a = cls(_fake_server([page], seen))
    fetched = a.fetch(FetchRequest({"layer": "0", "oid_min": "1", "oid_max": "11"}))
    assert fetched.request.startswith("https://x.test/FS/1/query")
    assert a.layer_of(fetched) == 0
    out = [(r.table, dict(r.row)) for r in a.normalize(fetched)]
    assert [r["parcel_uid"] for t, r in out if t == "parcel"] == ["54001-9"]


def test_layers_without_layer_url_and_bad_layer(tmp_path: Path) -> None:
    path = _cfg(tmp_path, layers=["https://x.test/FS/5"])
    data = yaml.safe_load(path.read_text())
    del data["layer_url"]
    path.write_text(yaml.safe_dump(data))
    assert load_config(path).layer_url == "https://x.test/FS/5"
    del data["layers"]
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(StateConfigError, match="layer_url or layers"):
        load_config(path)
    data["layers"] = [42]
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(StateConfigError, match="each layer"):
        load_config(path)


def test_no_paging_mode_uses_small_windows(tmp_path: Path) -> None:
    cls = adapter_for(load_config(_cfg(tmp_path, paginate=False, page_size=2)))
    seen: list[str] = []
    stats = {"features": [{"attributes": {"LO": 1, "HI": 4}}]}  # upper-cased by some servers
    plan = list(cls(_fake_server([stats, {"count": 4}], seen)).partitions())
    assert plan == [{"oid_min": "1", "oid_max": "3"}, {"oid_min": "3", "oid_max": "5"}]
    page = {"features": [{"attributes": {"OID": 1, "PID": "1", "CO": "061"}}]}
    a = cls(_fake_server([page], seen))
    a.fetch(FetchRequest({"oid_min": "1", "oid_max": "3"}))
    assert "resultOffset" not in seen[-1]
    assert "orderByFields" not in seen[-1]
    from equity.adapters.arcgis import ArcGISError

    too_big = {"features": [], "exceededTransferLimit": True}
    with pytest.raises(ArcGISError, match="record limit"):
        cls(_fake_server([too_big], seen)).fetch(FetchRequest({"oid_min": "1", "oid_max": "3"}))


def test_state_health_respects_paging_mode(tmp_path: Path) -> None:
    for paginate, marker in ((True, "resultRecordCount"), (False, "OID+IN")):
        cls = adapter_for(load_config(_cfg(tmp_path, paginate=paginate)))
        seen: list[str] = []
        attrs = dict.fromkeys(cls.fields, 1)
        ok = cls(_fake_server([{"features": [{"attributes": attrs}]}], seen)).health()
        assert ok.ok
        assert marker in seen[-1]
        bad = cls(_fake_server([{"features": [{"attributes": {"X": 1}}]}], seen)).health()
        assert not bad.ok

    from collections.abc import Mapping as _M

    from equity.adapters.http import PoliteClient

    def broken(url: str, headers: _M[str, str], timeout: float) -> tuple[int, bytes, str]:
        return (404, b"", "") if url.endswith("robots.txt") else (502, b"<html>", "text/html")

    down = cls(PoliteClient(min_interval_s=0, transport=broken, sleep=lambda s: None)).health()
    assert not down.ok


@pytest.mark.parametrize(
    ("text", "parsed"),
    [
        ("WASHINGTON DC 20001-1234", ("WASHINGTON", "DC", "20001")),
        ("Saint Paul, mn 55101", ("Saint Paul", "MN", "55101")),
        ("NOWHERE", (None, None, None)),
    ],
)
def test_parse_city_state_zip(text: str, parsed: tuple[str | None, ...]) -> None:
    from equity.adapters.state_parcels import parse_city_state_zip

    assert parse_city_state_zip(text) == parsed


def test_composite_ids_numeric_codes_and_csz(tmp_path: Path) -> None:
    fields = {"parcel_id": ["TOWN", "PROP"], "owner1": "OWN", "mail_line1": "M1",
              "mail_city_state_zip": "CSZ", "total_value": "TV",
              "tax_year": {"const": 2025}}  # fmt: skip
    county = {"field": "TOWN", "format": "code_map", "numeric": True,
              "code_map": {"35": "061", "57": "061"}}  # fmt: skip
    cls = adapter_for(load_config(_cfg(tmp_path, fields=fields, county=county)))
    assert {"TOWN", "PROP", "CSZ"} <= set(cls.fields)
    assert cls().where(FetchRequest({"county_fips": "061"})) == "TOWN=35 OR TOWN=57"
    out = _rows(cls, [
        {"OID": 1, "TOWN": 35, "PROP": "A-1", "OWN": "X", "M1": "1 Main",
         "CSZ": "MORGANTOWN WV 26505", "TV": 1},
        {"OID": 2, "TOWN": 35, "PROP": "A-2", "OWN": "Y", "TV": 1},
        {"OID": 3, "TOWN": 35, "PROP": None, "OWN": "Z", "TV": 1},
    ])  # fmt: skip
    assert sorted(r["parcel_uid"] for t, r in out if t == "parcel") == [
        "54061-35-A-1",
        "54061-35-A-2",
    ]
    (addr,) = [r for t, r in out if t == "address"]
    assert (addr["city"], addr["state"], addr["zip5"]) == ("MORGANTOWN", "WV", "26505")
    assert addr["line1"] == "1 MAIN"


def test_sparse_object_ids_get_dense_windows(tmp_path: Path) -> None:
    cls = adapter_for(load_config(_cfg(tmp_path, county={"constant": "061"})))
    seen: list[str] = []
    responses = [
        {"features": [{"attributes": {"LO": 1_000_000, "HI": 9_000_000}}]},
        {"count": 3},
        {"objectIds": [9_000_000, 1_000_000, 5_000_000]},
    ]
    plan = list(cls(_fake_server(responses, seen)).partitions(window=2))
    assert plan == [{"oid_min": "1000000", "oid_max": "5000001"},
                    {"oid_min": "9000000", "oid_max": "9000001"}]  # fmt: skip
    assert "returnIdsOnly" in seen[-1]


def test_address_rows_are_normalized_value_objects() -> None:
    from equity.adapters.state_parcels import normalized_address

    a = normalized_address("12 Main St.", "Morgantown", "wv", "26505")
    b = normalized_address("12 MAIN ST", "MORGANTOWN", "WV", "26505")
    assert a == b  # same key, same content: re-loads never conflict
    assert normalized_address(None, None, "WV", None) is None


def test_fixed_filter_and_deed_ref(tmp_path: Path) -> None:
    fields = {"parcel_id": "PID", "owner1": "OWN", "deed_ref": "DREF", "total_value": "TV",
              "tax_year": {"const": 2025}}  # fmt: skip
    pattern = r"(?P<book>\d+)\s*[-/]\s*(?P<page>\d+)"
    cls = adapter_for(load_config(_cfg(tmp_path, fields=fields, filter="ROLL_YEAR = 2026",
                                       deed_ref_pattern=pattern)))  # fmt: skip
    a = cls()
    assert a.where(FetchRequest({"county_fips": "061"})) == "(ROLL_YEAR = 2026) AND (CO='061')"
    out = _rows(
        cls,
        [
            {"OID": 1, "PID": "1", "CO": "061", "OWN": "X", "DREF": "282 - 520", "TV": 1},
            {"OID": 2, "PID": "2", "CO": "061", "OWN": "Y", "DREF": "see plat", "TV": 1},
        ],
    )
    snaps = {r["parcel_uid"]: (r["deed_book"], r["deed_page"]) for t, r in out
             if t == "owner_snapshot"}  # fmt: skip
    assert snaps == {"54061-1": ("282", "520"), "54061-2": (None, None)}
    seen: list[str] = []
    stats = {"features": [{"attributes": {"lo": 1, "hi": 2}}]}
    named = adapter_for(load_config(_cfg(tmp_path, county={"constant": "061"},
                                         filter="ROLL_YEAR = 2026")))  # fmt: skip
    list(named(_fake_server([stats, {"count": 2}], seen)).partitions())
    assert all("ROLL_YEAR" in u for u in seen)


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"fields": {"parcel_id": "P", "deed_ref": "D"}}, "needs deed_ref_pattern"),
        ({"fields": {"parcel_id": "P", "deed_ref": "D"}, "deed_ref_pattern": r"(\d+)"},
         "named"),
    ],
)  # fmt: skip
def test_deed_ref_validation(tmp_path: Path, over: dict[str, Any], message: str) -> None:
    with pytest.raises(StateConfigError, match=message):
        load_config(_cfg(tmp_path, **over))
