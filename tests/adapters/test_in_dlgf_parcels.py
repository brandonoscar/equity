"""Indiana DLGF real-property PARCEL files from the Indiana Gateway download page. Offline."""

from __future__ import annotations

import io
import json
import re
import urllib.parse
import zipfile
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import Response
from equity.adapters.in_dlgf_parcels import (
    FORM_COUNTY,
    FORM_DATASET,
    FORM_YEAR,
    HEADER,
    PARCEL,
    IndianaDLGFParcels,
    county_fips5,
    dashed,
    options,
    parse_header,
    parse_record,
)
from equity.adapters.registry import by_source_id

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "in.dlgf.parcels"
URL = "https://gateway.ifionline.org/public/download.aspx"


def fixed(values: dict[str, str], spec: tuple[tuple[str, int, int], ...], width: int) -> str:
    line = [" "] * width
    cols = {n: (a, b) for n, a, b in spec}
    for name, value in values.items():
        a, b = cols[name]
        line[a - 1 : b] = list(value.ljust(b - a + 1)[: b - a + 1])
    return "".join(line)


def header(county: str = "58", fmt: str = "2021A", name: str = "PARCEL") -> str:
    return fixed({"filename": name, "county_number": county, "county_description": "Ohio",
                  "file_format_id": fmt, "assessment_year": "2025", "pay_year": "2026"},
                 HEADER, 458)  # fmt: skip


def record(i: int, **over: str) -> str:
    vals = {"parcel_number": f"5802214000030{i:05d}", "local_parcel_number": f"L{i}",
            "property_address": f"{i} MAIN ST", "property_city": "RISING SUN",
            "property_zip": "47040-0000", "property_class": "510",
            "owner_name": f"OWNER {i} LLC", "owner_address": "PO BOX 1",
            "owner_city": "DILLSBORO", "owner_state": "IN", "owner_zip": "47018-1234",
            "owner_country": "USA", "av_land": "000000010000", "av_improvements": "000000020500",
            "av_total": "000000030500", "legal_acres": "000000052500", "anonymity": "N",
            "current_av_total": "000000031000", **over}  # fmt: skip
    return fixed(vals, PARCEL, 1286)


def parcel_file(n: int, county: str = "58", **hdr: str) -> bytes:
    lines = [header(county, **hdr), *(record(i) for i in range(n)), f"TRAILER   {n:020d}"]
    return ("\r\n".join(lines) + "\r\n").encode("cp1252")


def make_zip(text: bytes, names: tuple[str, ...] = ("RealParcel_Ohio_58_2025P2026.txt",)) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.writestr(name, text)
    return buf.getvalue()


def page(counties: int = 92) -> str:
    opts = "".join(f'<option value="{i:02d}">C{i}</option>' for i in range(1, counties + 1))
    return (
        '<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="vs&amp;1" />'
        '<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="ev" />'
        f'<select name="{FORM_DATASET}" id="x"><option selected="selected" value="4">Adj'
        '</option><option value="5">Real Property</option></select>'
        f'<select name="{FORM_YEAR}"><option selected="selected" value="2025">2025 pay 2026'
        '</option><option value="2024">2024 pay 2025</option></select>'
        f'<select name="{FORM_COUNTY}">{opts}<option value="-99">All Counties</option></select>'
    )


class FakeGateway:
    retries = 0
    backoff_s = 0.0

    def __init__(self, zips: dict[str, bytes], html: str | None = None) -> None:
        self.zips, self.html = zips, html if html is not None else page()
        self.posts: list[dict[str, str]] = []

    def now(self) -> datetime:
        return AT

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        return Response(url, 200, self.html.encode(), "text/html", AT)

    def post_form(self, url: str, fields: dict[str, str]) -> Response:
        self.posts.append(dict(fields))
        body = self.zips.get(fields[FORM_COUNTY], b"<html>error</html>")
        return Response(url, 200, body, "application/octet-stream", AT)


def adapter(fake: FakeGateway, tmp_path: Path) -> IndianaDLGFParcels:
    a = IndianaDLGFParcels(fake)  # type: ignore[arg-type]
    a.cache_dir = tmp_path  # type: ignore[misc]
    return a


def test_parcel_numbers_and_counties() -> None:
    assert dashed("580221400003000005") == "58-02-21-400-003.000-005"
    assert dashed(" 58-02-21 ") == "58-02-21" and dashed("12345") == "12345"
    assert county_fips5("01") == "18001" and county_fips5("58") == "18115"
    assert county_fips5("92") == "18183"
    with pytest.raises(ValueError, match="county number"):
        county_fips5("93")


def test_header_and_record_parsing() -> None:
    h = parse_header(header())
    assert h["county_number"] == "58" and h["assessment_year"] == "2025"
    with pytest.raises(ValueError, match="format"):
        parse_header(header(fmt="2011A"))
    with pytest.raises(ValueError, match="not a PARCEL"):
        parse_header(header(name="LAND"))
    rec = parse_record(record(3), h, 3)
    assert rec["parcel_id"] == "58-02-21-400-003.000-003" and rec["county_fips"] == "18115"
    assert rec["av_land"] == "10000" and rec["av_total"] == "30500"
    assert rec["legal_acres"] == "5.25" and rec["_row"] == "3" and rec["pay_year"] == "2026"
    assert "current_av_land" not in rec  # blank columns are dropped
    short = parse_record(record(1).rstrip(), h, 1)  # trailing blanks trimmed: padded back
    assert short["owner_name"] == "OWNER 1 LLC"
    bad = parse_record(record(2, av_land="00000ABC0000", legal_acres="x"), h, 2)
    assert "av_land" not in bad and "legal_acres" not in bad


def test_anonymity_requests_drop_owner_and_mailing() -> None:
    rec = parse_record(record(1, anonymity="Y"), parse_header(header()), 1)
    assert not {"owner_name", "owner_address", "owner_city", "owner_zip"} & set(rec)
    assert rec["property_address"] == "1 MAIN ST" and rec["av_total"] == "30500"


def test_page_options() -> None:
    p = page(3)
    assert options(p, FORM_YEAR) == [("2025", "2025 pay 2026"), ("2024", "2024 pay 2025")]
    assert options(p, "missing") == []
    years, counties = IndianaDLGFParcels(FakeGateway({}, p)).offered(p)  # type: ignore[arg-type]
    assert years == ["2025", "2024"] and counties == ["01", "02", "03"]
    with pytest.raises(RuntimeError, match="Real Property"):
        IndianaDLGFParcels().offered(p.replace('value="5"', 'value="7"'))


def test_partitions_slice_large_counties(tmp_path: Path) -> None:
    a = adapter(FakeGateway({}), tmp_path)
    parts = list(a.partitions())
    assert parts[0] == {"county": "01", "year": "2025", "slice": "0", "slices": "1"}
    marion = [p for p in parts if p["county"] == "49"]
    assert [p["slice"] for p in marion] == [str(i) for i in range(7)]
    assert len({p["county"] for p in parts}) == 92
    assert a.health().ok and a.health().shape == ("2025",)
    assert not adapter(FakeGateway({}, page(91)), tmp_path).health().ok
    with pytest.raises(RuntimeError, match="no year"):
        list(adapter(FakeGateway({}, page().replace("2025", "x").replace("2024", "y")),
                     tmp_path).partitions())  # fmt: skip


def test_fetch_posts_the_form_slices_caches_and_cleans_up(tmp_path: Path) -> None:
    fake = FakeGateway({"58": make_zip(parcel_file(5))})
    a = adapter(fake, tmp_path)
    base = {"county": "58", "year": "2025", "slices": "2"}
    first = a.fetch(FetchRequest({**base, "slice": "0"}))
    post = fake.posts[0]
    assert post["__VIEWSTATE"] == "vs&1" and post["__EVENTVALIDATION"] == "ev"
    assert post[FORM_DATASET] == "5" and post[FORM_YEAR] == "2025" and post[FORM_COUNTY] == "58"
    assert (tmp_path / "realparcel_58_2025.zip").exists()  # kept for the next slice
    body = json.loads(first.content)
    assert body["rows"] == [0, 2] and [r["_row"] for r in body["attributes"]] == ["0", "1"]
    assert first.request.endswith("#county=58&year=2025&rows=0-2")
    second = json.loads(a.fetch(FetchRequest({**base, "slice": "1"})).content)
    assert second["rows"] == [2, 5] and [r["_row"] for r in second["attributes"]] == ["2", "3", "4"]
    assert len(fake.posts) == 1  # the second slice read the cache
    assert not (tmp_path / "realparcel_58_2025.zip").exists()  # removed after the last slice
    lim = json.loads(a.fetch(FetchRequest({"county": "58", "year": "2025", "limit": "2"})).content)
    assert len(lim["attributes"]) == 2 and (tmp_path / "realparcel_58_2025.zip").exists()


def test_fetch_rejects_bad_requests_and_downloads(tmp_path: Path) -> None:
    a = adapter(FakeGateway({"58": make_zip(parcel_file(2, county="57"))}), tmp_path)
    with pytest.raises(ValueError, match="bad county"):
        a.fetch(FetchRequest({"county": "5", "year": "2025"}))
    with pytest.raises(ValueError, match="not offered"):
        a.fetch(FetchRequest({"county": "58", "year": "2019"}))
    with pytest.raises(RuntimeError, match="not a zip"):
        a.fetch(FetchRequest({"county": "12", "year": "2025"}))
    with pytest.raises(ValueError, match="file is 57"):
        a.fetch(FetchRequest({"county": "58", "year": "2025"}))
    two = make_zip(parcel_file(1), names=("a.txt", "b.txt"))
    b = adapter(FakeGateway({"58": two}), tmp_path / "b")
    with pytest.raises(ValueError, match=r"one \.txt"):
        b.fetch(FetchRequest({"county": "58", "year": "2025"}))


def _normalized() -> tuple[Fetched, list[Any]]:
    path = next(FIX.glob("*.json"))
    f = Fetched("in.dlgf.parcels", path.as_uri(), AT, 200, path.read_bytes(), "")
    return f, list(by_source_id("in.dlgf.parcels")().normalize(f))


def test_fixture_normalizes_with_parcel_ids_matching_igio() -> None:
    f, rows = _normalized()
    t = Counter(r.table for r in rows)
    n = len(json.loads(f.content)["attributes"])
    assert t["parcel"] == t["owner_snapshot"] == t["parcel_assessment"] == t["party"] == n
    uids = [r.row["parcel_uid"] for r in rows if r.table == "parcel"]
    # The form in.statewide.parcels (IGIO) and the IN county layers use: county FIPS, then
    # the dashed 18-digit state parcel number.
    assert all(re.fullmatch(r"18115-58-\d{2}-\d{2}-\d{3}-\d{3}\.\d{3}-\d{3}", u) for u in uids)
    assess = [r.row for r in rows if r.table == "parcel_assessment"]
    assert {a["tax_year"] for a in assess} == {2025}
    assert {a["valid_from"] for a in assess} == {date(2025, 1, 1)}
    assert all(a["appraised_total"] == a["assessed_value"] for a in assess)
    first = next(a for a in assess if a["parcel_uid"] == "18115-58-02-21-400-003.000-005")
    assert (first["appraised_land"], first["appraised_bldg"], first["appraised_total"]) == (
        "157400.00", "212900.00", "370300.00")  # fmt: skip
    parties = [r.row for r in rows if r.table == "party"]
    assert all(p["raw_name"].startswith("TESTOWNER") for p in parties)
    assert any(p["party_kind"] == "org" for p in parties)
    assert all(r.row.get("source_record_id") for r in rows if r.table != "address")
    addrs = [r.row for r in rows if r.table == "address"]
    assert {a["state"] for a in addrs} >= {"IN"} and all(a["norm_key"] for a in addrs)


def test_source_row_records_the_use_restriction() -> None:
    src = IndianaDLGFParcels().source_row()
    assert src["access_method"] == "bulk" and src["jurisdiction"] == "18"
    assert src["terms_summary"].startswith(
        "RESTRICTED[no_commercial_name_address_lists,no_mailing_list] "
    )
    assert "5-14-3-3(f)" in src["terms_summary"]
    assert urllib.parse.urlsplit(src["base_url"]).path == "/public/download.aspx"
    bad = Fetched("in.dlgf.parcels", "x", AT, 200, b'{"attributes": {}}', "")
    with pytest.raises(ValueError, match="attributes"):
        IndianaDLGFParcels.attributes(bad)
    assert IndianaDLGFParcels().layer_of(bad) == 0
