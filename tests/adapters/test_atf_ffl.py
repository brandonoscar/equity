"""ATF Federal Firearms Licensee listing (equity.adapters.federal.atf_ffl).

www.atf.gov blocks automated clients (Akamai 403), so the adapter reads hand-saved files and
is not registered; these tests use synthetic listings only (no recorded fixture).
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.atf_ffl import (
    ATFFirearmsLicensees,
    file_month,
    license_number,
    person_parts,
)
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
HEADER = ("Lic Regn\tLic Dist\tLic Cnty\tLic Type\tLic Xprdte\tLic Seqn\tLicense Name\t"
          "Business Name\tPremise Street\tPremise City\tPremise State\tPremise Zip Code\t"
          "Mail Street\tMail City\tMail State\tMail Zip Code\tVoice Phone\n")  # fmt: skip
TXT = (HEADER
       + "8\t83\t021\t01\t6K\t12345\tDOE, JOHN A\tJOHNS GUNS\t1 MAIN ST\tCASPER\tWY\t82601\t"
         "PO BOX 1\tCASPER\tWY\t82602\t3075551212\n"
       + "8\t83\t025\t07\t7B\t00042\tACME ARMS LLC\t\t2 ELM ST\tCHEYENNE\tWY\t820011234\t"
         "\t\t\t\t\n"
       + "\t\t\t\t\t\tNO NUMBER\t\t\t\t\t\t\t\t\t\t\n")  # fmt: skip


def _fetched(rows: list[dict[str, str]], month: str | None = "2026-11-01") -> Fetched:
    return Fetched(ATFFirearmsLicensees.source_id, "https://www.atf.gov/x#1126", AT, None,
                   canonical_json({"month": month, "rows": rows}), "application/json")  # fmt: skip


def _save(tmp_path: Path, name: str = "1126-ffl-list-wyoming.txt", body: str = TXT) -> Path:
    d = tmp_path / "data" / "manual" / ATFFirearmsLicensees.source_id
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")
    return d / name


def test_a_hand_saved_month_file_is_read_by_header_and_partitioned_by_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    adapter = ATFFirearmsLicensees()
    assert list(adapter.partitions()) == []
    _save(tmp_path)
    _save(tmp_path, "1026-ffl-list-wyoming.txt")
    assert list(adapter.partitions()) == [{"file": "1026-ffl-list-wyoming.txt"},
                                          {"file": "1126-ffl-list-wyoming.txt"}]  # fmt: skip
    fetched = adapter.fetch(FetchRequest({"file": "1126-ffl-list-wyoming.txt"}))
    body = json.loads(fetched.content)
    assert body["month"] == "2026-11-01" and len(body["rows"]) == 3
    assert body["rows"][0]["LICENSE_NAME"] == "DOE, JOHN A"
    assert "VOICE_PHONE" not in body["rows"][0]
    assert fetched.http_status is None and fetched.request.endswith("#1126-ffl-list-wyoming.txt")
    one = adapter.fetch(FetchRequest({"file": "1126-ffl-list-wyoming.txt", "limit": "1"}))
    assert len(json.loads(one.content)["rows"]) == 1
    with pytest.raises(ValueError, match="name one"):
        adapter.fetch(FetchRequest({}))
    with pytest.raises(RuntimeError, match="by hand"):
        adapter.fetch(FetchRequest({"file": "0101-ffl-list.txt"}))


def test_xlsx_and_path_are_read_too(tmp_path: Path) -> None:
    cells = [h for h in HEADER.rstrip("\n").split("\t")]
    values = ["8", "83", "021", "01", "6K", "12345", "DOE, JOHN A", "JOHNS GUNS", "1 MAIN ST",
              "CASPER", "WY", "82601", "", "", "", "", ""]  # fmt: skip

    def row(n: int, vals: list[str]) -> str:
        cs = "".join(f'<c r="{chr(65 + i)}{n}" t="inlineStr"><is><t>{v}</t></is></c>'
                     for i, v in enumerate(vals) if v)  # fmt: skip
        return f'<row r="{n}">{cs}</row>'

    sheet = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             f"<sheetData>{row(1, cells)}{row(2, values)}</sheetData></worksheet>")  # fmt: skip
    path = tmp_path / "1126-ffl-list-complete.xlsx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    path.write_bytes(buf.getvalue())
    body = json.loads(ATFFirearmsLicensees().fetch(FetchRequest({"path": str(path)})).content)
    assert body["rows"] == [{"LIC_REGN": "8", "LIC_DIST": "83", "LIC_CNTY": "021",
                             "LIC_TYPE": "01", "LIC_XPRDTE": "6K", "LIC_SEQN": "12345",
                             "LICENSE_NAME": "DOE, JOHN A", "BUSINESS_NAME": "JOHNS GUNS",
                             "PREMISE_STREET": "1 MAIN ST", "PREMISE_CITY": "CASPER",
                             "PREMISE_STATE": "WY", "PREMISE_ZIP_CODE": "82601"}]  # fmt: skip


def test_licenses_become_businesses_with_the_licensee_as_a_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _save(tmp_path)
    rows = json.loads(ATFFirearmsLicensees().fetch(FetchRequest({})).content)["rows"]
    out = [(r.table, dict(r.row)) for r in ATFFirearmsLicensees().normalize(_fetched(rows))]
    records = {r["record_key"] for t, r in out if t == "source_record"}
    assert records == {"8-83-021-01-6K-12345", "8-83-025-07-7B-00042"}
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    shop = biz["FFL:8-83-021-01-12345"]
    assert (shop["name"], shop["status"], shop["valid_from"]) == (
        "JOHNS GUNS",
        "licensed",
        date(2026, 11, 1),
    )
    assert shop["jurisdiction"] == "56021"  # LIC_CNTY read as the county FIPS code
    addrs = {r["address_id"]: r for t, r in out if t == "address"}
    assert addrs[shop["principal_address_id"]]["line1"] == "1 MAIN ST"
    assert addrs[shop["mailing_address_id"]]["zip5"] == "82602"
    maker = biz["FFL:8-83-025-07-00042"]
    assert maker["name"] == "ACME ARMS LLC" and maker["org_form"] == "LLC"
    assert maker["mailing_address_id"] is None
    parties = {r["party_id"]: r for t, r in out if t == "party"}
    roles = {(r["sos_id"], r["role"], r["title"], parties[r["party_id"]]["party_kind"])
             for t, r in out if t == "business_role"}  # fmt: skip
    assert roles == {
        ("FFL:8-83-021-01-12345", "other",
         "LICENSEE: Dealer in firearms other than destructive devices", "person"),
        ("FFL:8-83-025-07-00042", "other",
         "LICENSEE: Manufacturer of firearms other than destructive devices", "org"),
    }  # fmt: skip
    doe = next(p for p in parties.values() if p["raw_name"] == "DOE, JOHN A")
    assert (doe["first_name"], doe["middle"], doe["last_name"]) == ("JOHN", "A", "DOE")


def test_helpers() -> None:
    assert file_month("1126-ffl-list-complete.txt") == date(2026, 11, 1)
    assert file_month("ffl-list.txt") is None and file_month("1326-ffl.txt") is None
    r = {"LIC_REGN": "1", "LIC_DIST": "57", "LIC_CNTY": "013", "LIC_TYPE": "01",
         "LIC_XPRDTE": "4K", "LIC_SEQN": "12345"}  # fmt: skip
    assert license_number(r) == "1-57-013-01-4K-12345"
    assert license_number(r, with_expiry=False) == "1-57-013-01-12345"
    assert license_number({"LIC_SEQN": "1"}) is None
    assert person_parts("SMITH, ANN")["last_name"] == "SMITH"
    assert person_parts("ANN SMITH")["last_name"] is None  # order unknown without a comma


def test_pii_fields_cover_names_and_streets() -> None:
    assert set(ATFFirearmsLicensees.pii_fields) == {"LICENSE_NAME", "BUSINESS_NAME",
                                                   "PREMISE_STREET", "MAIL_STREET"}  # fmt: skip
    rows = [{"LICENSE_NAME": "DOE, JOHN A", "BUSINESS_NAME": "JOHNS GUNS LLC",
             "PREMISE_STREET": "1 MAIN ST", "MAIL_STREET": "PO BOX 1"}]  # fmt: skip
    (r,) = json.loads(ATFFirearmsLicensees.scrub_fixture(canonical_json({"rows": rows})))["rows"]
    assert r["LICENSE_NAME"].startswith("TESTOWNER") and r["BUSINESS_NAME"].endswith(" LLC")
    assert r["PREMISE_STREET"].endswith(" TEST ST") and r["MAIL_STREET"].endswith(" TEST ST")


def test_the_adapter_contract_on_a_synthetic_month(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, empty_db
) -> None:
    from ..test_adapter_contract import check_contract

    monkeypatch.chdir(tmp_path)
    _save(tmp_path)
    fetched = ATFFirearmsLicensees().fetch(FetchRequest({}))
    sample = tmp_path / "sample.json"
    sample.write_bytes(ATFFirearmsLicensees.scrub_fixture(fetched.content))
    check_contract(ATFFirearmsLicensees, [sample], empty_db)
