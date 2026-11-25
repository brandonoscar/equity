"""SEC Form D and insider data sets (equity.adapters.federal.sec_edgar)."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.bulk_files import BulkClient
from equity.adapters.federal.sec_edgar import (
    FORM_D_PAGE,
    INSIDER_PAGE,
    SECFormD,
    SECInsiders,
    cik10,
    form_d_filings,
    insider_filings,
    sec_date,
)

AT = datetime(2026, 11, 25, tzinfo=UTC)
ROOT = Path(__file__).parents[1] / "fixtures" / "adapters"


def _tsv(*rows: tuple[str, ...]) -> str:
    return "".join("\t".join(r) + "\n" for r in rows)


def _zip(members: Mapping[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


FORM_D = _zip({
    "2026Q3_d/FORMDSUBMISSION.tsv": _tsv(
        ("ACCESSIONNUMBER", "FILE_NUM", "FILING_DATE", "SIC_CODE", "SUBMISSIONTYPE", "TESTORLIVE"),
        ("0001-26-000001", "021-1", "30-SEP-2026", "", "D", "LIVE"),
        ("0001-26-000002", "021-2", "01-OCT-2026", "", "D/A", "TEST"),
        ("0001-26-000003", "021-3", "02-JUL-2026", "", "D", "LIVE")),
    "2026Q3_d/ISSUERS.tsv": _tsv(
        ("ACCESSIONNUMBER", "IS_PRIMARYISSUER_FLAG", "ISSUER_SEQ_KEY", "CIK", "ENTITYNAME",
         "STREET1", "STREET2", "CITY", "STATEORCOUNTRY", "STATEORCOUNTRYDESCRIPTION", "ZIPCODE"),
        ("0001-26-000001", "YES", "101", "0002122354", "ACME FUND LP", "55 HUDSON YARDS",
         "51ST FLOOR", "NEW YORK", "NY", "NEW YORK", "10001"),
        ("0001-26-000003", "YES", "101", "12345", "OVERSEAS LTD", "AV. 4040", "", "SANTIAGO",
         "F3", "CHILE", "00000")),
    "2026Q3_d/RELATEDPERSONS.tsv": _tsv(
        ("ACCESSIONNUMBER", "RELATEDPERSON_SEQ_KEY", "FIRSTNAME", "MIDDLENAME", "LASTNAME",
         "STREET1", "STREET2", "CITY", "STATEORCOUNTRY", "STATEORCOUNTRYDESCRIPTION", "ZIPCODE",
         "RELATIONSHIP_1", "RELATIONSHIP_2", "RELATIONSHIP_3", "RELATIONSHIPCLARIFICATION"),
        ("0001-26-000001", "101", "Ann", "Q", "Lee", "1 Main St", "", "New York", "NY",
         "NEW YORK", "10001", "Executive Officer", "Director", "", ""),
        ("0001-26-000001", "102", "", "", "Acme GP LLC", "1 Main St", "", "New York", "NY",
         "NEW YORK", "10001", "Promoter", "", "", "General partner")),
    "2026Q3_d/OFFERING.tsv": _tsv(
        ("ACCESSIONNUMBER", "INDUSTRYGROUPTYPE", "TOTALOFFERINGAMOUNT", "TOTALAMOUNTSOLD"),
        ("0001-26-000001", "Pooled Investment Fund", "5000000", "100000")),
})  # fmt: skip

INSIDERS = _zip({
    "SUBMISSION.tsv": _tsv(
        ("ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT", "DOCUMENT_TYPE", "ISSUERCIK",
         "ISSUERNAME", "ISSUERTRADINGSYMBOL"),
        ("0002-26-000001", "31-JUL-2026", "29-JUL-2026", "4", "0001709048", "WIDGETS Inc.",
         "WDG"),
        ("0002-26-000002", "01-AUG-2026", "30-JUL-2026", "3", "0000000000", "NOBODY", "")),
    "REPORTINGOWNER.tsv": _tsv(
        ("ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME", "RPTOWNER_RELATIONSHIP",
         "RPTOWNER_TITLE", "RPTOWNER_TXT", "RPTOWNER_STREET1", "RPTOWNER_STREET2",
         "RPTOWNER_CITY", "RPTOWNER_STATE", "RPTOWNER_ZIPCODE", "RPTOWNER_STATE_DESC"),
        ("0002-26-000001", "0001604405", "LEE ANN", "Director,Officer", "Chief Executive Officer",
         "", "405 WAVERLEY STREET", "", "PALO ALTO", "CA", "94301", ""),
        ("0002-26-000001", "0001000001", "BIG HOLDINGS LLC", "TenPercentOwner", "", "", "1 PARK",
         "", "DOVER", "DE", "19901", ""),
        ("0002-26-000001", "0001000002", "RAY BOB", "Other", "", "Member of 13(d) group", "",
         "", "", "", "", "")),
})  # fmt: skip


def _fetched(cls: type, filings: list[dict[str, object]]) -> Fetched:
    from equity.adapters.rows import canonical_json

    return Fetched(cls.source_id, "https://www.sec.gov/files/x.zip", AT, 200,  # type: ignore[attr-defined]
                   canonical_json({"filings": filings}), "application/json")  # fmt: skip


def test_form_d_issuer_and_related_persons() -> None:
    with zipfile.ZipFile(io.BytesIO(FORM_D)) as zf:
        filings = form_d_filings(zf)
        assert [f["accession"] for f in filings] == ["0001-26-000001", "0001-26-000003"]
        assert [f["accession"] for f in form_d_filings(zf, 1)] == ["0001-26-000001"]
    out = [(r.table, dict(r.row)) for r in SECFormD().normalize(_fetched(SECFormD, filings))]
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    assert set(biz) == {"CIK:0002122354", "CIK:0000012345"}
    acme = biz["CIK:0002122354"]
    assert acme["valid_from"] == date(2026, 9, 30) and acme["org_form"] == "LP"
    assert acme["jurisdiction"] == "36"
    roles = sorted((r["role"], r["title"]) for t, r in out if t == "business_role")
    assert roles == [("director", "director"), ("officer", "executive officer"),
                     ("other", "General partner")]  # fmt: skip
    party = {r["raw_name"]: r for t, r in out if t == "party"}
    assert party["Ann Q Lee"]["party_kind"] == "person"
    assert (party["Ann Q Lee"]["first_name"], party["Ann Q Lee"]["last_name"]) == ("Ann", "Lee")
    assert party["Acme GP LLC"]["party_kind"] == "org"
    addr = {r["address_id"]: r for t, r in out if t == "address"}
    assert addr[party["Ann Q Lee"]["address_id"]]["zip5"] == "10001"
    foreign = [r for t, r in out if t == "address" and r["city"] == "SANTIAGO"]
    assert foreign and foreign[0]["state"] is None and foreign[0]["zip5"] is None


def test_insider_reporting_owners_become_roles() -> None:
    with zipfile.ZipFile(io.BytesIO(INSIDERS)) as zf:
        filings = insider_filings(zf)
        assert len(insider_filings(zf, 1)) == 1
    out = [(r.table, dict(r.row)) for r in SECInsiders().normalize(_fetched(SECInsiders,
                                                                            filings))]  # fmt: skip
    (biz,) = [r for t, r in out if t == "business"]  # CIK 0 names no issuer
    assert (biz["sos_id"], biz["name"], biz["valid_from"]) == ("CIK:0001709048", "WIDGETS Inc.",
                                                               date(2026, 7, 29))  # fmt: skip
    assert biz["principal_address_id"] is None
    roles = sorted((r["role"], r["title"]) for t, r in out if t == "business_role")
    assert roles == [("director", "director"), ("officer", "Chief Executive Officer"),
                     ("other", "10% owner"), ("other", "Member of 13(d) group")]  # fmt: skip


def test_value_helpers() -> None:
    assert sec_date("30-SEP-2026") == date(2026, 9, 30) == sec_date("2026-09-30")
    assert sec_date("") is None
    assert cik10("12345") == "0000012345" and cik10("0000000000") is None


class _Server:
    def __init__(self, pages: Mapping[str, bytes], files: Mapping[str, bytes]) -> None:
        self.pages, self.files = pages, files

    def get(self, url: str, headers: Mapping[str, str], timeout: float
            ) -> tuple[int, bytes, str]:  # fmt: skip
        if url in self.pages:
            return 200, self.pages[url], "text/html"
        return 404, b"", "text/plain"

    def stream(self, url: str, headers: Mapping[str, str], timeout: float, dest: Path
               ) -> tuple[int, str]:  # fmt: skip
        assert "@" not in headers["User-Agent"]  # no personal contact address is sent
        dest.write_bytes(self.files[url])
        return 200, "application/zip"


@pytest.mark.parametrize(("cls", "page", "name", "data"), [
    (SECFormD, FORM_D_PAGE, "2026q3_d.zip", FORM_D),
    (SECInsiders, INSIDER_PAGE, "2026q3_form345.zip", INSIDERS),
])  # fmt: skip
def test_partitions_and_limited_fetch(
    cls: type, page: str, name: str, data: bytes, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    url = f"https://www.sec.gov/files/structureddata/data/x/{name}"
    old = url.replace("2026q3", "2026q2")
    html = f'<a href="/files/structureddata/data/x/{name}"><a href="{old}">'.encode()
    server = _Server({page: html}, {url: data})
    monkeypatch.setattr(cls, "cache_dir", tmp_path)
    client = BulkClient(transport=server.get, stream_transport=server.stream,
                        sleep=lambda s: None, now=lambda: AT)  # fmt: skip
    adapter = cls(client)
    assert list(adapter.partitions()) == [{"quarter": "2026q2"}, {"quarter": "2026q3"}]
    fetched = adapter.fetch(FetchRequest({"quarter": "2026Q3", "limit": "1"}))
    body = json.loads(fetched.content)
    assert body["url"] == url and len(body["filings"]) == 1
    assert not list(tmp_path.rglob("*.zip"))  # the quarter's zip is deleted after reading
    with pytest.raises(ValueError, match="bad quarter"):
        adapter.fetch(FetchRequest({"quarter": "2026"}))


def test_pii_fields_cover_names_and_streets_and_fixtures_are_pseudonymized() -> None:
    with zipfile.ZipFile(io.BytesIO(FORM_D)) as zf:
        from equity.adapters.rows import canonical_json

        d = json.loads(SECFormD.scrub_fixture(canonical_json({"filings": form_d_filings(zf)})))
    person = d["filings"][0]["related_persons"][0]
    assert person["FIRSTNAME"].startswith("TESTOWNER") and person["STREET1"].endswith("TEST ST")
    assert d["filings"][0]["issuers"][0]["ENTITYNAME"] == "ACME FUND LP"
    for cls in (SECFormD, SECInsiders):
        paths = sorted((ROOT / cls.source_id).glob("*.json"))
        assert paths, cls.source_id
        for path in paths:
            for f in json.loads(path.read_text())["filings"]:
                for p in [*f.get("related_persons", []), *f.get("owners", []),
                          *f.get("issuers", [])]:  # fmt: skip
                    for k in cls.pii_fields:
                        v = p.get(k)
                        assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k


@pytest.mark.parametrize("cls", [SECFormD, SECInsiders])
def test_recorded_fixtures_pass_the_adapter_contract(cls: type, empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(cls, sorted((ROOT / cls.source_id).glob("*.json")), empty_db)  # type: ignore[attr-defined]
