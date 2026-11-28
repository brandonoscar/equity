"""Vermont transfer-return archive: XML extracts in year zips, sellers and buyers, financing."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import PoliteClient
from equity.adapters.vt_pttr_archive import (
    VermontTransferArchive,
    parse_zip,
    span_uid,
)

FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "vt.tax.property_transfers_archive"
AT = datetime(2026, 11, 26, tzinfo=UTC)
XML = """<?xml version='1.0' encoding='UTF-8'?>
<PropertyTransferExtract><List_formData>
<formData><formHeader><DLN>1</DLN><closingDate>2015-12-06</closingDate>
<financingBank>true</financingBank><financingOwner>false</financingOwner>
<totalPricePaid>177000.00</totalPricePaid><span>40512611977</span><countyCode>12</countyCode>
</formHeader>
<sellerList><seller><index>1</index><lastName>LEE</lastName><firstName>ANN</firstName>
<initial>B</initial><street>1 ELM ST</street><city>MONTPELIER</city><state>VT</state>
<postal>05602-1234</postal></seller></sellerList>
<buyerList><buyer><index>1</index><entityName>ACME LLC</entityName><street>2 OAK ST</street>
<city>BARRE</city><state>VT</state><postal>05641</postal></buyer>
<buyer><index>2</index></buyer></buyerList></formData>
<formData><formHeader><DLN>2</DLN><closingDate>2019-01-03</closingDate><span>1</span>
</formHeader></formData>
<formData><formHeader><DLN>3</DLN><closingDate>2016-02-01</closingDate><span>bad</span>
<totalPricePaid>n/a</totalPricePaid>
<countyCode>99</countyCode></formHeader></formData>
<formData/>
</List_formData></PropertyTransferExtract>"""


def _zip(files: Mapping[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def _rows(content: bytes) -> list[tuple[str, dict[str, object]]]:
    f = Fetched("vt.tax.property_transfers_archive", "x", AT, 200, content, "")
    return [(r.table, dict(r.row)) for r in VermontTransferArchive().normalize(f)]


def test_span_uid() -> None:
    assert span_uid("40512611977", "12") == "50023-405-126-11977"  # Washington County
    assert span_uid("405-126-11977", 1) == "50001-405-126-11977"  # Addison
    assert span_uid("123", "12") is None and span_uid("40512611977", "15") is None


def test_parse_and_normalize() -> None:
    rows = parse_zip(_zip({"PT201601.xml": XML, "readme.txt": "x"}))
    assert rows is not None and [r["DLN"] for r in rows] == ["1", "2", "3"]
    assert parse_zip(_zip({"pt2006.txt": "fixed width"})) is None
    out = _rows(json.dumps({"rows": rows + rows[:1]}).encode())
    inst = [r for t, r in out if t == "instrument"]
    assert [r["instrument_number"] for r in inst] == ["1", "3"]  # 2019 closing dropped; dup once
    one = inst[0]
    assert one["doc_type"] == "DEED" and one["recorded_on"] == date(2015, 12, 6)
    assert one["consideration"] == Decimal("177000.00")
    assert one["doc_type_raw"] == "Vermont property transfer tax return (financing: bank)"
    assert inst[1]["doc_type_raw"] == "Vermont property transfer tax return"
    assert inst[1]["consideration"] is None
    assert [r["parcel_uid"] for t, r in out if t == "instrument_parcel"] == ["50023-405-126-11977"]
    parties = {(r["raw_name"], r["party_kind"]) for t, r in out if t == "party"}
    assert {n for n, _ in parties} == {"ANN B LEE", "ACME LLC"} and ("ACME LLC", "org") in parties
    roles = sorted(r["role"] for t, r in out if t == "instrument_party")
    assert roles == ["grantee", "grantor"]  # the nameless second buyer is skipped
    zips = {r["zip5"] for t, r in out if t == "address"}
    assert zips == {"05602", "05641"}


def test_recorded_fixture() -> None:
    path = next(FIX.glob("*.json"))
    out = _rows(path.read_bytes())
    assert sum(t == "instrument" for t, _ in out) == 20
    assert all(str(r["recorded_on"]) < "2019" for t, r in out if t == "instrument")
    assert all(r["parcel_uid"].startswith("50") for t, r in out if t == "instrument_parcel")


def test_partitions_fetch_and_errors() -> None:
    listing = (b"<EnumerationResults><Blobs>"
               b"<Blob><Name>property_transfer_files/Archive/PT2009/pt2009.zip</Name></Blob>"
               b"<Blob><Name>property_transfer_files/Archive/PT2016/PT2016.zip</Name></Blob>"
               b"<Blob><Name>property_transfer_files/Archive/PT2010/a.zip</Name></Blob>"
               b"<Blob><Name>property_transfer_files/Weekly/x.zip</Name></Blob>"
               b"</Blobs></EnumerationResults>")  # fmt: skip
    book = _zip({"PT201601.xml": XML})
    status = {"list": 200, "zip": 200}

    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        if "comp=list" in url:
            return status["list"], listing, "application/xml"
        return status["zip"], book, "application/zip"

    a = VermontTransferArchive(PoliteClient(min_interval_s=0, retries=0, transport=transport,
                                            sleep=lambda s: None))  # fmt: skip
    assert [p["blob"] for p in a.partitions()] == [
        "property_transfer_files/Archive/PT2010/a.zip",
        "property_transfer_files/Archive/PT2016/PT2016.zip"]  # 2009 is out of range  # fmt: skip
    f = a.fetch(FetchRequest({"blob": "property_transfer_files/Archive/PT2016/PT2016.zip",
                              "limit": "1"}))  # fmt: skip
    assert len(json.loads(f.content)["rows"]) == 1
    assert a.source_row()["kind"] == "recorder"
    assert not a.health().ok  # two archives in this listing
    with pytest.raises(ValueError, match="not an archive"):
        a.fetch(FetchRequest({"blob": "property_transfer_files/Archive/PT2009/pt2009.zip"}))
    status["zip"] = 503
    with pytest.raises(RuntimeError, match="HTTP 503"):
        a.fetch(FetchRequest({"blob": "property_transfer_files/Archive/PT2016/PT2016.zip"}))
    status["list"] = 500
    with pytest.raises(RuntimeError, match="listing"):
        list(a.partitions())
