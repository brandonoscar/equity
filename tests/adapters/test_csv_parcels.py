"""Config-driven CSV parcel-owner adapters (a plain CSV file, or one member of a zip read over
HTTP byte ranges): config validation, row filtering and normalization, slicing with the local
cache, health, and every config in config/bulk/ with a csv block against its recorded fixture.
Offline: a fake client serves the files."""

from __future__ import annotations

import io
import json
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.csv_parcels import (
    CsvParcelAdapter,
    CsvParcelError,
    all_csv_parcel_adapters,
    csv_adapter_for,
    csv_config_paths,
    load_csv_config,
)
from equity.adapters.http import Response
from equity.adapters.state_parcels import StateConfigError

from ..test_fixture_privacy import _walk

FIX = Path(__file__).parents[1] / "fixtures" / "adapters"
AT = datetime(2026, 11, 25, 12, tzinfo=UTC)
URL = "https://files.test/roll.csv"
ZIP_URL = "https://files.test/rolls.zip"

CSV = (
    "﻿Parcel_ID,Seq,Name,Street,City,State,Zip5,Market,Year,Account,Extra\r\n"
    "100,1,ANN LEE,1 MAIN ST,AUSTIN,TX,78701,1000,2026,R1,x\r\n"
    "200,2,SECOND OWNER,2 OAK ST,AUSTIN,TX,78702,2000,2026,R2,x\r\n"
    "200,1,FIRST OWNER LLC,3 ELM ST,AUSTIN,TX,78703,2000,2026,R2,x\r\n"
    ",,,,,,,,,,\r\n"
    "300,1,*** CONFIDENTIAL OWNER ***,,,,,3000,2026,R3,x\r\n"
    "400,1,ACME SUPPLY INC,4 PINE ST,DALLAS,TX,75201,500,2026,BP400,x\r\n"
    '500,1,"SMITH, JOHN",5 ASH ST,WACO,TX,76701,700,2026,R5,"multi\nline"\r\n'
)


def _cfg(tmp_path: Path, csv: dict[str, Any] | None = None, **over: Any) -> Path:
    base: dict[str, Any] = {
        "source_id": "zz.csv.parcels", "state": "TX", "layer_url": URL,
        "order_by": "Seq", "county": {"constant": "349"},
        "csv": {"exclude_prefix": {"Account": ["BP"]},
                "null_values": ["*** CONFIDENTIAL OWNER ***"]} if csv is None else csv,
        "fields": {"parcel_id": "Parcel_ID", "owner1": "Name", "mail_line1": "Street",
                   "mail_city": "City", "mail_state": "State", "mail_zip": "Zip5",
                   "total_value": "Market", "tax_year": "Year"},
        "value_basis": "test",
        "terms": {"summary": "s", "checked_on": "2026-11-25", "cost_model": "free"},
    }  # fmt: skip
    base.update(over)
    path = tmp_path / "zz.csv.parcels.yaml"
    path.write_text(yaml.safe_dump(base))
    return path


class FakeFiles:
    """Serves whole files, byte ranges and suffix ranges (or no ranges at all)."""

    retries = 0
    backoff_s = 0.0

    def __init__(self, files: dict[str, bytes], ranges: bool = True) -> None:
        self.files, self.ranges = files, ranges
        self.calls: list[tuple[str, int, int]] = []

    def now(self) -> datetime:
        return AT

    def _resp(self, url: str, body: bytes, status: int) -> Response:
        return Response(url, status, body, "application/octet-stream", AT)

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        self.calls.append((url, 0, -1))
        return self._resp(url, self.files[url], 200)

    def get_range(self, url: str, first: int, last: int) -> Response:
        self.calls.append((url, first, last))
        data = self.files[url]
        if not self.ranges:
            return self._resp(url, data, 200)
        return self._resp(url, data[first : last + 1], 206)

    def get_suffix(self, url: str, n: int) -> Response:
        self.calls.append((url, -n, -1))
        data = self.files[url]
        if not self.ranges:
            return self._resp(url, data, 200)
        return self._resp(url, data[-n:], 206)


def _adapter(path: Path, files: dict[str, bytes], tmp_path: Path, ranges: bool = True
             ) -> CsvParcelAdapter:  # fmt: skip
    cls = csv_adapter_for(load_csv_config(path))
    cls.cache_dir = tmp_path / "cache"
    return cls(FakeFiles(files, ranges))  # type: ignore[arg-type]


def _attrs(f: Fetched) -> list[dict[str, str]]:
    attrs: list[dict[str, str]] = json.loads(f.content)["attributes"]
    return attrs


def test_rows_are_filtered_and_keep_mapped_columns_and_record_index(tmp_path: Path) -> None:
    a = _adapter(_cfg(tmp_path), {URL: CSV.encode()}, tmp_path)
    f = a.fetch(FetchRequest())
    rows = _attrs(f)
    # The blank line and the BP (personal property) account are gone; _row counts records.
    assert [(r["Parcel_ID"], r["_row"]) for r in rows] == [
        ("100", "0"), ("200", "1"), ("200", "2"), ("300", "4"), ("500", "6")]  # fmt: skip
    assert set(rows[0]) == {"Parcel_ID", "Seq", "Name", "Street", "City", "State", "Zip5",
                            "Market", "Year", "_row"}  # fmt: skip
    assert f.request == f"{URL}#rows=0-5" and f.retrieved_at == AT
    assert json.loads(f.content)["member"] is None


def test_normalize_lowest_sequence_wins_and_null_values_name_nobody(tmp_path: Path) -> None:
    a = _adapter(_cfg(tmp_path), {URL: CSV.encode()}, tmp_path)
    out = list(a.normalize(a.fetch(FetchRequest())))
    by: dict[str, list[dict[str, Any]]] = {}
    for r in out:
        by.setdefault(r.table, []).append(dict(r.row))
    assert [p["parcel_uid"] for p in by["parcel"]] == ["48349-100", "48349-200", "48349-300",
                                                        "48349-500"]  # fmt: skip
    names = sorted(p["raw_name"] for p in by["party"])
    assert names == ["ANN LEE", "FIRST OWNER LLC", "SMITH, JOHN"]  # 300 is confidential
    assert {a["tax_year"] for a in by["parcel_assessment"]} == {2026}
    assert {a["appraised_total"] for a in by["parcel_assessment"]} >= {"3000.00"}


def test_zip_member_is_read_over_byte_ranges(tmp_path: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("rolls_1997-2025/2024.csv", "Parcel_ID\r\n" + "9\r\n" * 50_000)
        zf.writestr("rolls_1997-2025/2025.csv", CSV)
    data = buf.getvalue()
    path = _cfg(tmp_path, layer_url=ZIP_URL,
                csv={"member": "2025.csv", "exclude_prefix": {"Account": ["BP"]}})  # fmt: skip
    a = _adapter(path, {ZIP_URL: data}, tmp_path)
    f = a.fetch(FetchRequest())
    assert [r["Parcel_ID"] for r in _attrs(f)] == ["100", "200", "200", "300", "500"]
    assert f.request == f"{ZIP_URL}#member=2025.csv&rows=0-5"
    calls = a.client.calls  # type: ignore[attr-defined]
    assert all(last >= 0 or first < 0 for _, first, last in calls)  # ranges only
    assert sum(last - first + 1 for _, first, last in calls if first >= 0) < len(data)
    # A host without byte ranges: the archive is downloaded whole.
    b = _adapter(path, {ZIP_URL: data}, tmp_path, ranges=False)
    assert _attrs(b.fetch(FetchRequest())) == _attrs(f)
    missing = _cfg(tmp_path, layer_url=ZIP_URL, csv={"member": "2026.csv"})
    with pytest.raises(CsvParcelError, match=r"0 members named 2026\.csv"):
        _adapter(missing, {ZIP_URL: data}, tmp_path).fetch(FetchRequest())


def test_slices_share_one_cached_read_and_detect_a_changed_file(tmp_path: Path) -> None:
    path = _cfg(tmp_path, csv={"slice_rows": 2}, order_by="_row")
    a = _adapter(path, {URL: CSV.encode()}, tmp_path)
    plan = list(a.partitions())
    size = str(len(CSV.encode()))
    # No exclusions here: 6 kept rows (the BP account too), 2 per slice.
    assert plan == [{"slice": str(i), "slices": "3", "bytes": size} for i in range(3)]
    cached = a.cache_dir / "zz.csv.parcels.csv"
    assert cached.exists()
    got = [_attrs(a.fetch(FetchRequest(p))) for p in plan]
    assert [len(g) for g in got] == [2, 2, 2]
    assert [r["_row"] for g in got for r in g] == ["0", "1", "2", "4", "5", "6"]
    assert not cached.exists()  # deleted after the last slice
    assert len(a.client.calls) == 1  # type: ignore[attr-defined]
    with pytest.raises(CsvParcelError, match="plan again"):
        a.fetch(FetchRequest({**plan[0], "bytes": "12"}))
    whole = _adapter(_cfg(tmp_path), {URL: CSV.encode()}, tmp_path)
    assert list(whole.partitions()) == [{"slice": "0", "slices": "1"}]


def test_fixture_limit_reads_the_start_of_the_file(tmp_path: Path) -> None:
    big = CSV + "".join(f"{i},1,NAME {i},1 ST,X,TX,78701,1,2026,R,x\r\n" for i in range(9000))
    a = _adapter(_cfg(tmp_path), {URL: big.encode()}, tmp_path)
    rows = _attrs(a.fetch(FetchRequest({"limit": "3"})))
    assert [r["Parcel_ID"] for r in rows] == ["100", "200", "200"]
    _, first, last = a.client.calls[0]  # type: ignore[attr-defined]
    assert (first, last) == (0, 262_143)


def test_missing_columns_and_health(tmp_path: Path) -> None:
    a = _adapter(_cfg(tmp_path), {URL: CSV.encode()}, tmp_path)
    h = a.health()
    assert h.ok and "Name" in h.shape
    broken = CSV.replace("Market", "MarketValue", 1).encode()
    b = _adapter(_cfg(tmp_path), {URL: broken}, tmp_path)
    assert not b.health().ok and "Market" in b.health().detail
    with pytest.raises(CsvParcelError, match=r"columns missing from the file: \['Market'\]"):
        b.fetch(FetchRequest())
    no_account = CSV.replace(",Account,", ",Acct,", 1).encode()
    assert not _adapter(_cfg(tmp_path), {URL: no_account}, tmp_path).health().ok


@pytest.mark.parametrize(
    ("csv", "over", "message"),
    [
        ({"members": "x"}, {}, "unknown csv keys"),
        ({"member": "dir/2025.csv"}, {}, "without folders"),
        ({"exclude_prefix": {"Account": "BP"}}, {}, "exclude_prefix"),
        ({"slice_rows": 0}, {}, "slice_rows must be positive"),
        ({}, {"county": {"field": "FIPS", "format": "fips5"}}, "constant county"),
        ({}, {"layer_url": "http://files.test/x.csv"}, "https://"),
    ],
)
def test_config_validation(tmp_path: Path, csv: dict[str, Any], over: dict[str, Any],
                           message: str) -> None:  # fmt: skip
    with pytest.raises(StateConfigError, match=message):
        load_csv_config(_cfg(tmp_path, csv=csv, **over))


def test_only_bulk_configs_with_a_csv_block_become_csv_adapters() -> None:
    names = {p.name for p in csv_config_paths()}
    assert {"mo.st_louis_city.parcels.yaml", "tx.navarro.parcels.yaml"} <= names
    assert "tx.stratmap.yaml" not in names and "il.cook.parcels.yaml" not in names
    ids = {c.source_id for c in all_csv_parcel_adapters()}
    assert {"mo.st_louis_city.parcels", "tx.navarro.parcels"} <= ids
    assert all(c.access_method == "bulk" for c in all_csv_parcel_adapters())


@pytest.mark.parametrize("cls", all_csv_parcel_adapters(), ids=lambda c: c.source_id)
def test_csv_config_against_fixture(cls: type[CsvParcelAdapter]) -> None:
    files = sorted((FIX / cls.source_id).glob("*.json"))
    assert files, f"{cls.source_id}: no fixture"
    county = cls.config.state_fips + str(cls.config.county["constant"])
    for path in files:
        data = json.loads(path.read_text())
        assert _walk(data, cls.pii_fields) == [], path.name
        f = Fetched(cls.source_id, path.as_uri(), AT, 200, path.read_bytes(), "application/json")
        rows = list(cls().normalize(f))
        tables = Counter(r.table for r in rows)
        assert tables["parcel"] and tables["party"] and tables["parcel_assessment"]
        for r in rows:
            if r.table == "parcel":
                assert r.row["parcel_uid"].startswith(county + "-")
            if r.table == "party":
                assert r.row["raw_name"].startswith("TESTOWNER")


def test_navarro_keys_match_texas_statewide_parcel_uids() -> None:
    """tx.navarro.parcels is keyed on the district property id, so its parcel_uid has the
    shape tx.statewide.parcels gives (fips5-PROP_ID)."""
    cls = next(c for c in all_csv_parcel_adapters() if c.source_id == "tx.navarro.parcels")
    path = next((FIX / cls.source_id).glob("*.json"))
    f = Fetched(cls.source_id, path.as_uri(), AT, 200, path.read_bytes(), "application/json")
    uids = [r.row["parcel_uid"] for r in cls().normalize(f) if r.table == "parcel"]
    assert uids and all(u.startswith("48349-") and u[6:].isdigit() for u in uids)
