"""NCUA credit union call report data (equity.adapters.federal.ncua)."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.ncua import PAGE, NCUACreditUnions, credit_unions, mdy
from equity.adapters.http import PoliteClient
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters" / NCUACreditUnions.source_id
FOICU = (
    '"CU_NUMBER","CYCLE_DATE","CU_NAME","CITY","STATE","ZIP_CODE","COUNTY_CODE","ATTENTION_OF",'
    '"STREET","ISSUE_DATE"\n'
    '6,6/30/2026 0:00:00,"THE NEW ORLEANS FIREMEN\'S","Metairie","LA","70004",51,"","P O Box 689",'
    "1/1/1934 0:00:00\n"
    '1,6/30/2026 0:00:00,"MORRIS SHEPPARD TEXARKANA","TEXARKANA","TX","75501",37,"JANE ROE",'
    '"419 W 4TH ST",1/1/1934 0:00:00\n'
)
BRANCH = (
    '"CU_NUMBER","SiteId","CU_NAME","SiteName","SiteTypeName","MainOffice","PhysicalAddressLine1",'
    '"PhysicalAddressLine2","PhysicalAddressCity","PhysicalAddressStateCode",'
    '"PhysicalAddressPostalCode","PhysicalAddressCountry","PhoneNumber"\n'
    '"1","45553","MORRIS SHEPPARD TEXARKANA","MORRIS SHEPPARD TEXARKANA FCU","Corporate Office",'
    '"Yes","419 W 4TH ST","","TEXARKANA","TX","75501","United States","9037983918"\n'
    '"1","45557","MORRIS SHEPPARD TEXARKANA","RED RIVER FCU","Branch Office","No",'
    '"4405 SUMMERHILL RD","","TEXARKANA","TX","75503","United States","9037937681"\n'
)
TRADE = '"CU_NUMBER","CycleDate","TradeName"\n6,6/30/2026 0:00:00,"NOFFCU"\n'


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("FOICU.txt", FOICU)
        zf.writestr("Credit Union Branch Information.txt", BRANCH)
        zf.writestr("TradeNames.txt", TRADE)
        zf.writestr("FS220.txt", "CU_NUMBER,ACCT_010\n1,5\n")
    return buf.getvalue()


def _cus() -> list[dict[str, object]]:
    with zipfile.ZipFile(io.BytesIO(_zip())) as zf:
        return credit_unions(zf)


def test_credit_unions_join_branches_and_trade_names() -> None:
    cus = _cus()
    assert [c["CU_NUMBER"] for c in cus] == ["1", "6"]
    assert len(cus[0]["branches"]) == 2 and "PhoneNumber" not in cus[0]["branches"][0]  # type: ignore[index, operator, arg-type]
    assert cus[1]["trade_names"] == [{"CU_NUMBER": "6", "TradeName": "NOFFCU"}]
    with zipfile.ZipFile(io.BytesIO(_zip())) as zf:
        assert [c["CU_NUMBER"] for c in credit_unions(zf, 1)] == ["1"]


def test_credit_unions_become_businesses_with_offices() -> None:
    fetched = Fetched(NCUACreditUnions.source_id, PAGE, AT, 200,
                      canonical_json({"credit_unions": _cus()}), "application/json")  # fmt: skip
    out = [(r.table, dict(r.row)) for r in NCUACreditUnions().normalize(fetched)]
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    ms = biz["NCUA:1"]
    assert (ms["name"], ms["status"], ms["formed_on"], ms["jurisdiction"]) == (
        "MORRIS SHEPPARD TEXARKANA FCU",
        "active",
        date(1934, 1, 1),
        "48037",
    )
    addrs = {r["address_id"]: r for t, r in out if t == "address"}
    assert addrs[ms["principal_address_id"]]["zip5"] == "75501"
    assert biz["NCUA:6"]["name"] == "THE NEW ORLEANS FIREMEN'S"
    assert biz["NCUA:6"]["principal_address_id"] is None
    parties = [r for t, r in out if t == "party"]
    by = {(p["record_key"], p["raw_name"], p["address_id"] is not None) for p in parties}
    assert ("1", "MORRIS SHEPPARD TEXARKANA", False) in by  # the FOICU short name, an alias
    assert ("6", "NOFFCU", False) in by
    offices = [p for p in parties if p["record_key"] == "1" and p["address_id"]
               and p["raw_name"] == "MORRIS SHEPPARD TEXARKANA FCU"]  # fmt: skip
    assert len(offices) == 2
    roles = [(r["sos_id"], r["title"]) for t, r in out if t == "business_role"]
    assert roles == [("NCUA:1", "ATTENTION OF")]


def test_dates() -> None:
    assert mdy("6/30/2026 0:00:00") == date(2026, 6, 30) and mdy("") is None


def test_partitions_and_fetch() -> None:
    page = (b'<a href="/files/publications/analysis/call-report-data-2026-06.zip">'
            b'<a href="/files/publications/analysis/call-report-data-2026-03.zip">')  # fmt: skip

    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("/robots.txt"):
            return 200, b"User-agent: *\nDisallow: /admin/\n", "text/plain"
        if url == PAGE:
            return 200, page, "text/html"
        assert url.endswith("call-report-data-2026-06.zip")
        return 200, _zip(), "application/zip"

    adapter = NCUACreditUnions(PoliteClient(transport=transport, sleep=lambda s: None,
                                            now=lambda: AT))  # fmt: skip
    assert list(adapter.partitions()) == [{"quarter": "2026-03"}, {"quarter": "2026-06"}]
    body = json.loads(adapter.fetch(FetchRequest({"quarter": "2026-06", "limit": "1"})).content)
    assert [c["CU_NUMBER"] for c in body["credit_unions"]] == ["1"]
    with pytest.raises(ValueError, match="bad quarter"):
        adapter.fetch(FetchRequest({"quarter": "2026-05"}))


def test_recorded_fixture_is_pseudonymized() -> None:
    paths = sorted(FIXTURES.glob("*.json"))
    assert paths
    for path in paths:
        for c in json.loads(path.read_text())["credit_unions"]:
            for row in (c, *c["branches"]):
                for k in NCUACreditUnions.pii_fields:
                    v = row.get(k)
                    assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k
                assert "PhoneNumber" not in row


def test_recorded_fixture_passes_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(NCUACreditUnions, sorted(FIXTURES.glob("*.json")), empty_db)
