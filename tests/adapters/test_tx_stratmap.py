"""Texas StratMap parcels (bulk county zips in S3) and the .dbf reader. Offline."""

from __future__ import annotations

import io
import json
import struct
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.dbf import read_header, read_records, record_count
from equity.adapters.http import Response
from equity.adapters.registry import by_source_id
from equity.adapters.tx.stratmap import TexasStratMapParcels, list_bucket

AT = datetime(2026, 11, 18, tzinfo=UTC)
FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "tx.statewide.parcels"
FIELDS = [
    ("PROP_ID", "C", 10), ("OWNER_NAME", "C", 30), ("MKT_VALUE", "F", 12), ("TAX_YEAR", "C", 4),
    ("FIPS", "N", 11), ("DATE_ACQ", "D", 8), ("FLAG", "L", 1),
]  # fmt: skip


def make_dbf(rows: list[tuple[Any, ...]], deleted: tuple[int, ...] = ()) -> bytes:
    rec_len = 1 + sum(f[2] for f in FIELDS)
    hdr_len = 32 + 32 * len(FIELDS) + 1
    out = bytearray(struct.pack("<BBBBIHH20x", 3, 126, 11, 18, len(rows), hdr_len, rec_len))
    for name, kind, ln in FIELDS:
        out += struct.pack("<11sc4xB15x", name.encode(), kind.encode(), ln)
    out += b"\r"
    for i, row in enumerate(rows):
        out += b"*" if i in deleted else b" "
        for (_, _, ln), v in zip(FIELDS, row, strict=True):
            out += str("" if v is None else v).encode("utf-8").ljust(ln)[:ln]
    return bytes(out + b"\x1a")


def make_zip(dbf: bytes, cpg: str | None = "UTF-8") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("shp/x_48261.dbf", dbf)
        if cpg is not None:
            zf.writestr("shp/x_48261.cpg", cpg)
    return buf.getvalue()


ROWS = [(f"P{i}", f"OWNER {i}", f"{1000 * i}.5", "2026", "48261", "20260301", "Y")
        for i in range(10)]  # fmt: skip


def test_dbf_reader() -> None:
    data = make_dbf(ROWS, deleted=(3,))
    h = read_header(io.BytesIO(data))
    assert h.records == 10 and h.fields[0].name == "PROP_ID"
    got = list(read_records(io.BytesIO(data), 2, 6))
    assert [i for i, _ in got] == [2, 4, 5]  # 3 is deleted
    row = got[0][1]
    assert row == {"PROP_ID": "P2", "OWNER_NAME": "OWNER 2", "MKT_VALUE": "2000.5",
                   "TAX_YEAR": "2026", "FIPS": "48261", "DATE_ACQ": "2026-03-01",
                   "FLAG": "true"}  # fmt: skip
    blanks = make_dbf([("P", None, "***", "", "", "2026", "?")])
    only = next(read_records(io.BytesIO(blanks)))[1]
    assert only["OWNER_NAME"] is None and only["MKT_VALUE"] is None
    assert only["DATE_ACQ"] is None and only["FLAG"] is None
    assert record_count(io.BytesIO(data)) == 10
    with pytest.raises(ValueError, match="truncated"):
        list(read_records(io.BytesIO(data[:-200])))
    bad = bytearray(data)
    bad[10] += 1  # record length no longer matches the fields
    with pytest.raises(ValueError, match="add up"):
        read_header(io.BytesIO(bytes(bad)))


class FakeS3:
    retries = 0
    backoff_s = 0.0

    def __init__(self, objects: dict[str, bytes], page: int = 1000) -> None:
        self.objects, self.page = objects, page
        self.calls: list[str] = []

    def now(self) -> datetime:
        return AT

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        self.calls.append(url)
        if params and params.get("list-type") == "2":
            keys = sorted(k for k in self.objects if k.startswith(params["prefix"]))
            start = int(params.get("continuation-token", "0"))
            chunk = keys[start : start + self.page]
            more = start + self.page < len(keys)
            xml = "".join(f"<Contents><Key>{k}</Key><Size>{len(self.objects[k])}</Size>"
                          "</Contents>" for k in chunk)  # fmt: skip
            if more:
                xml += f"<NextContinuationToken>{start + self.page}</NextContinuationToken>"
            return Response(url, 200, xml.encode(), "application/xml", AT)
        key = url.split("data.tnris.org/", 1)[1]
        return Response(url, 200, self.objects[key], "application/zip", AT)


PREFIX = "1d33dafb-6e9c-40ac-887d-f4577909ed9b/resources/"


def adapter(objects: dict[str, bytes], tmp_path: Path, page: int = 1000) -> TexasStratMapParcels:
    a = TexasStratMapParcels(FakeS3(objects, page))  # type: ignore[arg-type]
    a.cache_dir = tmp_path  # type: ignore[misc]
    return a


def test_partitions_slice_large_counties(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import equity.adapters.tx.stratmap as tx

    monkeypatch.setattr(tx, "SLICE_ZIP_BYTES", 100)
    objs = {PREFIX + "stratmap26-landparcels_48261_lp.zip": b"x" * 250,
            PREFIX + "stratmap26-landparcels_48001_lp.zip": b"x" * 50,
            PREFIX + "stratmap26-landparcels_48_lp.zip": b"x",  # statewide file: skipped
            PREFIX + "land-parcels-supplemental-report.zip": b"x"}  # fmt: skip
    a = adapter(objs, tmp_path, page=2)  # two listing pages
    parts = list(a.partitions())
    assert [(p["county_fips"], p["slice"], p["slices"]) for p in parts] == [
        ("001", "0", "1"), ("261", "0", "3"), ("261", "1", "3"), ("261", "2", "3")]  # fmt: skip
    assert a.health().ok is False  # 2 counties, not ~254
    with pytest.raises(ValueError, match="pair up"):
        list_bucket("<Key>a</Key>")


def test_fetch_slices_cache_and_cleanup(tmp_path: Path) -> None:
    key = PREFIX + "stratmap26-landparcels_48261_lp.zip"
    blob = make_zip(make_dbf(ROWS))
    a = adapter({key: blob}, tmp_path)
    base = {"key": key, "size": str(len(blob)), "slices": "2"}
    first = a.fetch(FetchRequest({**base, "slice": "0"}))
    assert (tmp_path / Path(key).name).exists()  # kept for the next slice
    body = json.loads(first.content)
    assert body["rows"] == [0, 5] and [r["_row"] for r in body["attributes"]] == list("01234")
    second = a.fetch(FetchRequest({**base, "slice": "1"}))
    assert json.loads(second.content)["rows"] == [5, 10]
    assert not (tmp_path / Path(key).name).exists()  # removed after the last slice
    downloads = [c for c in a.client.calls if c.endswith(".zip")]  # type: ignore[attr-defined]
    assert len(downloads) == 1  # second slice read the cache
    lim = a.fetch(FetchRequest({**base, "slice": "0", "limit": "2"}))
    assert len(json.loads(lim.content)["attributes"]) == 2


def test_fetch_rejects_bad_downloads(tmp_path: Path) -> None:
    key = PREFIX + "stratmap26-landparcels_48261_lp.zip"
    blob = make_zip(make_dbf(ROWS), cpg="ANSI 1252")
    a = adapter({key: blob}, tmp_path)
    with pytest.raises(ValueError, match="bytes"):
        a.fetch(FetchRequest({"key": key, "size": str(len(blob) + 1)}))
    got = json.loads(a.fetch(FetchRequest({"key": key, "size": str(len(blob))})).content)
    assert len(got["attributes"]) == 10  # cp1252 path
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("readme.txt", b"")
    a = adapter({key: empty.getvalue()}, tmp_path)
    with pytest.raises(ValueError, match=r"no \.dbf"):
        a.fetch(FetchRequest({"key": key, "size": str(len(empty.getvalue()))}))


def test_split_county_files_read_as_one_table(tmp_path: Path) -> None:
    key = PREFIX + "stratmap26-landparcels_48201_lp.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("shp/harris-west_48201.dbf", make_dbf(ROWS[5:]))
        zf.writestr("shp/harris-east_48201.dbf", make_dbf(ROWS[:5]))
    blob = buf.getvalue()
    a = adapter({key: blob}, tmp_path)
    base = {"key": key, "size": str(len(blob)), "slices": "3"}
    got = [json.loads(a.fetch(FetchRequest({**base, "slice": str(i)})).content)["attributes"]
           for i in range(3)]  # fmt: skip
    ids = [r["PROP_ID"] for part in got for r in part]
    assert ids == [f"P{i}" for i in range(10)]  # east (P0-P4) then west, no gaps or repeats
    assert [r["_row"] for part in got for r in part] == [str(i) for i in range(10)]


def test_fixture_normalizes() -> None:
    path = next(FIX.glob("*.json"))
    f = Fetched("tx.statewide.parcels", path.as_uri(), AT, 200, path.read_bytes(), "")
    rows = list(by_source_id("tx.statewide.parcels")().normalize(f))  # type: ignore[abstract]
    t = Counter(r.table for r in rows)
    assert t["parcel"] > 0 and t["owner_snapshot"] > 0 and t["parcel_assessment"] > 0
    uids = {r.row["parcel_uid"] for r in rows if r.table == "parcel"}
    assert all(u.startswith("48261-") for u in uids)
    src = by_source_id("tx.statewide.parcels")().source_row()  # type: ignore[abstract]
    assert src["access_method"] == "bulk" and src["jurisdiction"] == "48"
    assert TexasStratMapParcels.attributes(f) and TexasStratMapParcels().layer_of(f) == 0
    bad = Fetched("tx.statewide.parcels", "x", AT, 200, b'{"attributes": {}}', "")
    with pytest.raises(ValueError, match="attributes"):
        TexasStratMapParcels.attributes(bad)
