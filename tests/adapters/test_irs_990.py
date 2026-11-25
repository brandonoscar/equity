"""Form 990 officers (equity.adapters.federal.irs_990) and the Range-zip helpers it uses
(equity.adapters.federal.bulk_files)."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.bulk_files import BulkClient, Holder, remote_zip, zip_size
from equity.adapters.federal.irs_990 import (
    PAGE,
    IRS990Officers,
    iter_returns,
    parse_return,
    role_of,
)
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters" / IRS990Officers.source_id


def _xml(rtype: str, body: str, ein: str = "123456789") -> bytes:
    return f"""﻿<?xml version="1.0" encoding="utf-8"?>
<Return xmlns="http://www.irs.gov/efile" returnVersion="2024v5.1">
 <ReturnHeader>
  <TaxPeriodEndDt>2024-12-31</TaxPeriodEndDt><ReturnTypeCd>{rtype}</ReturnTypeCd>
  <TaxPeriodBeginDt>2024-01-01</TaxPeriodBeginDt>
  <Filer><EIN>{ein}</EIN>
   <BusinessName><BusinessNameLine1Txt>FRIENDS OF THE</BusinessNameLine1Txt>
    <BusinessNameLine2Txt>LIBRARY INC</BusinessNameLine2Txt></BusinessName>
   <USAddress><AddressLine1Txt>1 MAIN ST</AddressLine1Txt><CityNm>Rockwall</CityNm>
    <StateAbbreviationCd>TX</StateAbbreviationCd><ZIPCd>75087-1234</ZIPCd></USAddress>
  </Filer>
  <BusinessOfficerGrp><PersonNm>ANN LEE</PersonNm><PersonTitleTxt>PRESIDENT</PersonTitleTxt>
  </BusinessOfficerGrp>
  <TaxYr>2024</TaxYr>
 </ReturnHeader>
 <ReturnData>{body}</ReturnData>
</Return>""".encode()


F990 = _xml(
    "990",
    """<IRS990>
 <Form990PartVIISectionAGrp><PersonNm>ANN LEE</PersonNm><TitleTxt>PRESIDENT</TitleTxt>
  <AverageHoursPerWeekRt>10.00</AverageHoursPerWeekRt>
  <IndividualTrusteeOrDirectorInd>X</IndividualTrusteeOrDirectorInd><OfficerInd>X</OfficerInd>
  <ReportableCompFromOrgAmt>50000</ReportableCompFromOrgAmt></Form990PartVIISectionAGrp>
 <Form990PartVIISectionAGrp><PersonNm>BOB RAY</PersonNm><TitleTxt>EXEC DIR</TitleTxt>
  <KeyEmployeeInd>X</KeyEmployeeInd></Form990PartVIISectionAGrp>
 <Form990PartVIISectionAGrp><PersonNm>CY DOE</PersonNm><TitleTxt>TREASURER</TitleTxt>
  <FormerOfcrDirectorTrusteeInd>X</FormerOfcrDirectorTrusteeInd></Form990PartVIISectionAGrp>
 <Form990PartVIISectionAGrp><BusinessName><BusinessNameLine1Txt>FIRST BANK NA</BusinessNameLine1Txt>
  </BusinessName><TitleTxt>TRUSTEE</TitleTxt><InstitutionalTrusteeInd>X</InstitutionalTrusteeInd>
 </Form990PartVIISectionAGrp></IRS990>""",
)
F990PF = _xml(
    "990PF",
    """<IRS990PF><OfficerDirTrstKeyEmplInfoGrp><OfficerDirTrstKeyEmplGrp>
 <PersonNm>DEE FOX</PersonNm><USAddress><AddressLine1Txt>9 ELM RD</AddressLine1Txt>
 <CityNm>Plano</CityNm><StateAbbreviationCd>TX</StateAbbreviationCd><ZIPCd>75023</ZIPCd>
 </USAddress><TitleTxt>Director</TitleTxt><CompensationAmt>0</CompensationAmt>
</OfficerDirTrstKeyEmplGrp></OfficerDirTrstKeyEmplInfoGrp></IRS990PF>""",
    ein="222222222",
)
F990EZ = _xml(
    "990EZ",
    """<IRS990EZ><OfficerDirectorTrusteeEmplGrp><PersonNm>EVE GO</PersonNm>
 <TitleTxt>SECRETARY</TitleTxt></OfficerDirectorTrusteeEmplGrp></IRS990EZ>""",
    ein="333333333",
)
F990T = _xml("990T", "<IRS990T/>", ein="444444444")


def _zip(members: Mapping[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


BATCH = _zip({"2025001_public.xml": F990, "2025002_public.xml": F990T,
              "2025003_public.xml": F990PF, "2025004_public.xml": F990EZ})  # fmt: skip


def _normalize(filings: list[dict[str, object]]) -> list[tuple[str, dict[str, object]]]:
    fetched = Fetched(IRS990Officers.source_id, "https://apps.irs.gov/x.zip", AT, 200,
                      canonical_json({"filings": filings}), "application/json")  # fmt: skip
    return [(r.table, dict(r.row)) for r in IRS990Officers().normalize(fetched)]


def test_part_vii_people_become_roles_of_the_filer() -> None:
    f = parse_return(F990, "2025001")
    assert f is not None
    assert (f["ein"], f["name"], f["return_type"]) == ("123456789", "FRIENDS OF THE LIBRARY INC",
                                                       "990")  # fmt: skip
    assert [p["person_name"] or p["business_name"] for p in f["people"]] == [
        "ANN LEE", "BOB RAY", "CY DOE", "FIRST BANK NA"]  # fmt: skip
    assert f["people"][0]["ReportableCompFromOrgAmt"] == "50000"
    out = _normalize([f])
    (biz,) = [r for t, r in out if t == "business"]
    assert biz["sos_id"] == "EIN:123456789" and biz["valid_from"] == date(2024, 1, 1)
    assert biz["jurisdiction"] == "48"
    roles = sorted((r["role"], r["title"]) for t, r in out if t == "business_role")
    assert roles == [("director", "PRESIDENT"), ("director", "TRUSTEE"),
                     ("officer", "PRESIDENT"), ("other", "EXEC DIR"),
                     ("other", "TREASURER (former)")]  # fmt: skip
    # The signing officer (ANN LEE, PRESIDENT) is the Part VII officer, not a second row.
    assert all(r["valid_to"] == date(2024, 12, 31) for t, r in out if t == "business_role")
    kinds = {r["raw_name"]: r["party_kind"] for t, r in out if t == "party"}
    assert kinds["ANN LEE"] == "person" and kinds["FIRST BANK NA"] == "org"


def test_990pf_people_keep_their_address_and_ez_roles_come_from_titles() -> None:
    pf, ez = parse_return(F990PF, "3"), parse_return(F990EZ, "4")
    assert pf is not None and ez is not None
    assert pf["people"][0]["street_address"] == "9 ELM RD"
    out = _normalize([pf, ez])
    party = {r["raw_name"]: r for t, r in out if t == "party"}
    addr = {r["address_id"]: r for t, r in out if t == "address"}
    assert addr[party["DEE FOX"]["address_id"]]["city"] == "PLANO"
    roles = {(r["sos_id"], r["role"], r["title"]) for t, r in out if t == "business_role"}
    assert ("EIN:333333333", "officer", "SECRETARY") in roles
    assert ("EIN:222222222", "director", "Director") in roles


def test_role_of_titles_and_returns_without_officers() -> None:
    assert role_of({"title": "Board Member"}) == [("director", "Board Member")]
    assert role_of({"title": "Vice President"}) == [("officer", "Vice President")]
    assert role_of({"title": "Volunteer"}) == [("other", "Volunteer")]
    assert role_of({"positions": ["HighestCompensatedEmployeeInd"]}) == [
        ("other", "highest compensated employee")]  # fmt: skip
    assert parse_return(F990T, "2") is None


def test_iter_returns_streams_members_and_limit_counts_kept_returns() -> None:
    with zipfile.ZipFile(io.BytesIO(BATCH)) as zf:
        assert [f["object_id"] for f in iter_returns(zf)] == ["2025001", "2025003", "2025004"]
        assert [f["object_id"] for f in iter_returns(zf, 2)] == ["2025001", "2025003"]


class _RangeServer:
    """A fake transport serving files with Range support (and the downloads page)."""

    def __init__(self, files: Mapping[str, bytes]) -> None:
        self.files = files
        self.bytes_sent = 0

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                 ) -> tuple[int, bytes, str]:  # fmt: skip
        data = self.files.get(url)
        if data is None:
            return 404, b"", "text/plain"
        rng = headers.get("Range")
        if rng is None:
            return 200, data, "text/html"
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng)
        assert m is not None
        if m.group(1) == "":
            part = data[-int(m.group(2)) :]
        else:
            part = data[int(m.group(1)) : int(m.group(2)) + 1]
        self.bytes_sent += len(part)
        return 206, part, "application/zip"


def test_remote_zip_reads_members_over_range_requests() -> None:
    url = "https://apps.irs.gov/b.zip"
    noise = b"".join(hashlib.sha256(b"%d" % i).digest() for i in range(64))  # incompressible
    big = _zip({f"{i:04d}.xml": b"<x>%d</x>" % i + noise for i in range(1000)})
    server = _RangeServer({url: big})
    client = BulkClient(transport=server, sleep=lambda s: None)
    client.min_interval_s = 0
    assert zip_size(big[-5000:]) == len(big)
    with remote_zip(client, url) as zf:
        assert len(zf.infolist()) == 1000
        assert zf.read("0007.xml").startswith(b"<x>7</x>")
    assert server.bytes_sent < len(big) / 2


def test_fetch_with_limit_uses_range_and_partitions_come_from_the_page() -> None:
    url = "https://apps.irs.gov/pub/epostcard/990/xml/2026/2026_TEOS_XML_01A.zip"
    page = (
        b'<a href="https://apps.irs.gov/pub/epostcard/990/xml/2026/2026_TEOS_XML_01A.zip">'
        b'<a href="https://apps.irs.gov/pub/epostcard/990/xml/2026/index_2026.csv">'
        b'<a href="https://apps.irs.gov/pub/epostcard/990/xml/2025/2025_TEOS_XML_11B.zip">'
    )
    server = _RangeServer({url: BATCH, PAGE: page})
    adapter = IRS990Officers(BulkClient(transport=server, sleep=lambda s: None, now=lambda: AT))
    assert list(adapter.partitions()) == [{"year": "2025", "batch": "11B"},
                                          {"year": "2026", "batch": "01A"}]  # fmt: skip
    fetched = adapter.fetch(FetchRequest({"year": "2026", "batch": "01a", "limit": "1"}))
    body = json.loads(fetched.content)
    assert [f["object_id"] for f in body["filings"]] == ["2025001"]
    with pytest.raises(ValueError, match="bad batch"):
        adapter.batch_url("2026", "../x")


def test_full_fetch_streams_the_batch_to_disk_and_deletes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "https://apps.irs.gov/pub/epostcard/990/xml/2026/2026_TEOS_XML_01A.zip"
    seen: list[Path] = []

    def stream(u: str, headers: Mapping[str, str], timeout: float, dest: Path
               ) -> tuple[int, str]:  # fmt: skip
        assert u == url
        dest.write_bytes(BATCH)
        seen.append(dest)
        return 200, "application/zip"

    monkeypatch.setattr(IRS990Officers, "cache_dir", tmp_path)
    client = BulkClient(transport=_RangeServer({}), stream_transport=stream,
                        sleep=lambda s: None, now=lambda: AT)  # fmt: skip
    fetched = IRS990Officers(client).fetch(FetchRequest({"year": "2026", "batch": "01A"}))
    assert len(json.loads(fetched.content)["filings"]) == 3
    assert seen and not any(p.exists() for p in tmp_path.rglob("*.zip"))


def test_pii_fields_are_scrubbed_and_the_fixture_is_pseudonymized() -> None:
    assert set(IRS990Officers.pii_fields) == {"person_name", "street_address"}
    body = canonical_json({"filings": [parse_return(F990PF, "3")]})
    f = json.loads(IRS990Officers.scrub_fixture(body))["filings"][0]
    assert f["people"][0]["person_name"].startswith("TESTOWNER")
    assert f["people"][0]["street_address"].endswith(" TEST ST")
    assert f["signing_officer"]["person_name"].startswith("TESTOWNER")
    assert f["street_address"].endswith(" TEST ST")
    paths = sorted(FIXTURES.glob("*.json"))
    assert paths
    for path in paths:
        for f in json.loads(path.read_text())["filings"]:
            for p in [*f["people"], f.get("signing_officer") or {}]:
                assert not p.get("person_name") or p["person_name"].startswith("TESTOWNER")
                assert not p.get("street_address") or p["street_address"].endswith(" TEST ST")


def test_holder_rejects_unknown_roles() -> None:
    with pytest.raises(ValueError, match="unknown business role"):
        Holder("ceo", None, "ANN LEE")


def test_recorded_fixture_passes_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(IRS990Officers, sorted(FIXTURES.glob("*.json")), empty_db)
