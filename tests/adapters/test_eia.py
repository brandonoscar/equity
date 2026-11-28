"""EIA Form EIA-860 utilities, plants and owners (equity.adapters.federal.eia)."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.bulk_files import BulkClient
from equity.adapters.federal.eia import EIA860, PAGE, read_860
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters" / EIA860.source_id
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _xlsx(rows: list[list[str]]) -> bytes:
    """A minimal workbook with inline strings."""
    body = "".join(
        f'<row r="{i}">' + "".join(
            f'<c r="{chr(65 + j)}{i}" t="inlineStr"><is><t>{escape(v)}</t></is></c>'
            for j, v in enumerate(r)) + "</row>" for i, r in enumerate(rows, 1))  # fmt: skip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{NS}"><sheetData>{body}</sheetData></worksheet>',
        )
    return buf.getvalue()


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("1___Utility_Y2025.xlsx", _xlsx([
            ["2025 Form EIA-860 Data - Schedule 1, 'Utility Data'"],
            ["Utility ID", "Utility Name", "Street Address", "City", "State", "Zip", "Entity Type"],
            ["195", "Alabama Power Co", "600 North 18th Street", "Birmingham", "AL", "35291", "I"],
        ]))  # fmt: skip
        zf.writestr("2___Plant_Y2025.xlsx", _xlsx([
            ["2025 Form EIA-860 Data - Schedule 2, 'Plant Data'"],
            ["Utility ID", "Utility Name", "Plant Code", "Plant Name", "Street Address", "City",
             "State", "Zip", "County"],
            ["195", "Alabama Power Co", "10", "Greene County", "1 Plant Rd", "Demopolis", "AL",
             "36732", "Greene"],
        ]))  # fmt: skip
        zf.writestr("4___Owner_Y2025.xlsx", _xlsx([
            ["2025 Form EIA-860 Data - Schedule 4"],
            ["Utility ID", "Utility Name", "Plant Code", "Plant Name", "State", "Generator ID",
             "Owner Name", "Owner Street Address", "Owner City", "Owner State", "Owner Zip",
             "Percent Owned"],
            ["195", "Alabama Power Co", "10", "Greene County", "AL", "1", "Mississippi Power Co",
             "2992 W Beach Blvd", "Gulfport", "MS", "39501", "0.4"],
            ["195", "Alabama Power Co", "99", "Other Plant", "AL", "1", "Nobody LLC", "", "", "",
             "", "1"],
        ]))  # fmt: skip
    return buf.getvalue()


def test_workbooks_join_owners_to_plants() -> None:
    with zipfile.ZipFile(io.BytesIO(_zip())) as zf:
        data = read_860(zf)
    assert data["utilities"][0]["Utility Name"] == "Alabama Power Co"
    (plant,) = data["plants"]
    assert [o["Owner Name"] for o in plant["owners"]] == ["Mississippi Power Co"]


def test_utilities_and_plants_become_businesses() -> None:
    with zipfile.ZipFile(io.BytesIO(_zip())) as zf:
        body = {"year": "2025", **read_860(zf)}
    fetched = Fetched(EIA860.source_id, PAGE, AT, 200, canonical_json(body), "application/json")
    out = [(r.table, dict(r.row)) for r in EIA860().normalize(fetched)]
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    assert set(biz) == {"EIA-UTIL:195", "EIA-PLANT:10"}
    plant = biz["EIA-PLANT:10"]
    assert (plant["valid_from"], plant["jurisdiction"]) == (date(2025, 1, 1), "01063")
    parties = {r["party_id"]: r for t, r in out if t == "party"}
    roles = sorted((r["title"], parties[r["party_id"]]["raw_name"])
                   for t, r in out if t == "business_role")  # fmt: skip
    assert roles == [("OPERATOR", "Alabama Power Co"), ("OWNER", "Mississippi Power Co")]
    op = next(p for p in parties.values() if p["raw_name"] == "Alabama Power Co")
    assert op["address_id"] == biz["EIA-UTIL:195"]["principal_address_id"] is not None


def test_partition_is_the_current_release_only() -> None:
    page = (b'<a href="xls/eia8602025.zip"><a href="xls/eia8602025ER.zip">'
            b'<a href="archive/xls/eia8602024.zip">')  # fmt: skip

    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("/robots.txt"):
            return 200, b"User-agent: *\nDisallow: /*archive/\n", "text/plain"
        if url == PAGE:
            return 200, page, "text/html"
        assert url.endswith("/xls/eia8602025.zip")
        return 200, _zip(), "application/zip"

    adapter = EIA860(BulkClient(transport=transport, sleep=lambda s: None, now=lambda: AT))
    assert list(adapter.partitions()) == [{"year": "2025"}]
    body = json.loads(adapter.fetch(FetchRequest({"year": "2025", "limit": "1"})).content)
    assert len(body["utilities"]) == 1 and body["year"] == "2025"
    with pytest.raises(RuntimeError, match="no current EIA-860 zip"):
        adapter.fetch(FetchRequest({"year": "2024"}))


def test_recorded_fixture_is_pseudonymized() -> None:
    paths = sorted(FIXTURES.glob("*.json"))
    assert paths
    for path in paths:
        data = json.loads(path.read_text())
        for row in [*data["utilities"], *data["plants"],
                    *(o for p in data["plants"] for o in p["owners"])]:  # fmt: skip
            for k in EIA860.pii_fields:
                v = row.get(k)
                assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k


def test_recorded_fixture_passes_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(EIA860, sorted(FIXTURES.glob("*.json")), empty_db)
