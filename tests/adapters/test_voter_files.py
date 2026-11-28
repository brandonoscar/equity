"""Statewide voter files: Ohio and North Carolina (downloads: streaming parse of both layouts,
pii coverage, county partitions from the index pages, the recorded fixtures) and the eight
hand-delivered files (AK, AR, CO, DC, FL, MI, MS, WI: each state's published layout on inline
samples, county partitions of a delivery, pii coverage)."""

from __future__ import annotations

import gzip
import io
import json
import re
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters import voter_files
from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import PoliteClient
from equity.adapters.record import scrub
from equity.adapters.rows import canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.adapters.voter_files import (
    AlaskaVoterFile,
    ArkansasVoterFile,
    ColoradoVoterFile,
    DeliveredVoterFile,
    DistrictOfColumbiaVoterFile,
    FloridaVoterFile,
    MichiganVoterFile,
    MississippiVoterFile,
    NorthCarolinaVoterFile,
    OhioVoterFile,
    VoterFileAdapter,
    WisconsinVoterFile,
    county_fips,
    county_links,
    county_number,
    layout_columns,
)
from equity.schema.ids import sha256_hex

from ..test_adapter_contract import ADAPTER_FIXTURES, check_contract
from ..test_fixture_privacy import _walk

AT = datetime(2026, 11, 25, tzinfo=UTC)

NC_HEADER = [
    "county_id", "county_desc", "voter_reg_num", "ncid", "last_name", "first_name",
    "middle_name", "name_suffix_lbl", "status_cd", "voter_status_desc", "reason_cd",
    "voter_status_reason_desc", "res_street_address", "res_city_desc", "state_cd", "zip_code",
    "mail_addr1", "mail_addr2", "mail_addr3", "mail_addr4", "mail_city", "mail_state",
    "mail_zipcode", "full_phone_number", "confidential_ind", "registr_dt", "race_code",
    "ethnic_code", "party_cd", "gender_code", "birth_year", "age_at_year_end", "birth_state",
]  # fmt: skip


def _nc(**kw: str) -> dict[str, str]:
    base = dict.fromkeys(NC_HEADER, "")
    base.update(county_id="89", county_desc="TYRRELL", voter_reg_num="000000000001",
                ncid="EE1", last_name="LEE", first_name="ANN", middle_name="B",
                status_cd="A", voter_status_desc="ACTIVE", res_street_address="12  MAIN ST   ",
                res_city_desc="COLUMBIA", state_cd="NC", zip_code="27925",
                mail_addr1="12 MAIN ST", mail_city="COLUMBIA", mail_state="NC",
                mail_zipcode="279250714", full_phone_number="2525550100", confidential_ind="N",
                registr_dt="03/20/2002", party_cd="UNA", race_code="W",
                birth_year="1972")  # fmt: skip
    base.update(kw)
    return base


def _nc_zip(rows: list[dict[str, str]]) -> bytes:
    lines = ["\t".join(f'"{h}"' for h in NC_HEADER)]
    lines += ["\t".join(f'"{r[h]}"' for h in NC_HEADER) for r in rows]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ncvoter89.txt", "\r\n".join(lines) + "\r\n")
    return buf.getvalue()


OH_HEADER = [
    "SOS_VOTERID", "COUNTY_NUMBER", "COUNTY_ID", "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME",
    "SUFFIX", "DATE_OF_BIRTH", "REGISTRATION_DATE", "VOTER_STATUS", "PARTY_AFFILIATION",
    "RESIDENTIAL_ADDRESS1", "RESIDENTIAL_SECONDARY_ADDR", "RESIDENTIAL_CITY",
    "RESIDENTIAL_STATE", "RESIDENTIAL_ZIP", "RESIDENTIAL_ZIP_PLUS4", "RESIDENTIAL_COUNTRY",
    "RESIDENTIAL_POSTALCODE", "MAILING_ADDRESS1", "MAILING_SECONDARY_ADDRESS", "MAILING_CITY",
    "MAILING_STATE", "MAILING_ZIP", "MAILING_ZIP_PLUS4", "MAILING_COUNTRY",
    "MAILING_POSTAL_CODE", "CITY", "PRECINCT_NAME", "WARD", "PRIMARY-03/07/2000",
    "GENERAL-11/07/2000",
]  # fmt: skip


def _oh(**kw: str) -> dict[str, str]:
    base = dict.fromkeys(OH_HEADER, "")
    base.update({"SOS_VOTERID": "OH0016238254", "COUNTY_NUMBER": "82", "COUNTY_ID": "77",
                 "LAST_NAME": "LEE", "FIRST_NAME": "ANN", "MIDDLE_NAME": "B", "SUFFIX": "JR",
                 "DATE_OF_BIRTH": "1970-01-02", "REGISTRATION_DATE": "1990-05-06",
                 "VOTER_STATUS": "ACTIVE", "PARTY_AFFILIATION": "D",
                 "RESIDENTIAL_ADDRESS1": "9 ELM ST", "RESIDENTIAL_SECONDARY_ADDR": "APT 2",
                 "RESIDENTIAL_CITY": "MCARTHUR", "RESIDENTIAL_STATE": "OH",
                 "RESIDENTIAL_ZIP": "45651", "MAILING_ADDRESS1": "PO BOX 7",
                 "MAILING_CITY": "MCARTHUR", "MAILING_STATE": "OH", "MAILING_ZIP": "45651",
                 "PRECINCT_NAME": "ELK 1", "PRIMARY-03/07/2000": "D",
                 "GENERAL-11/07/2000": "X"})  # fmt: skip
    base.update(kw)
    return base


def _oh_gz(rows: list[dict[str, str]]) -> bytes:
    def line(vals: list[str]) -> str:
        return ",".join('"' + v.replace('"', '""') + '"' for v in vals)

    text = "\n".join([line(OH_HEADER)] + [line([r[h] for h in OH_HEADER]) for r in rows])
    return gzip.compress(text.encode() + b"\n", mtime=0)


def _run(cls: type[VoterFileAdapter], content: bytes) -> list[tuple[str, dict[str, Any]]]:
    f = Fetched(cls.source_id, "https://example.test/file", AT, 200, content, "x")
    return [(r.table, dict(r.row)) for r in cls().normalize(f)]


def _rows(out: list[tuple[str, dict[str, Any]]], table: str) -> list[dict[str, Any]]:
    return [r for t, r in out if t == table]


def test_nc_layout_people_addresses_and_skips() -> None:
    rows = [
        _nc(),
        _nc(),  # the same NCID twice: one registration
        _nc(ncid="EE2", last_name="RAY", first_name="BOB", middle_name="", name_suffix_lbl="III",
            mail_addr1="PO BOX 9", mail_zipcode="27925"),
        _nc(ncid="EE3", status_cd="R", res_street_address="REMOVED", res_city_desc="",
            state_cd="", zip_code="", mail_addr1="", mail_city=" ", mail_state=" ",
            mail_zipcode=" "),
        _nc(ncid="EE4", res_street_address="CONFIDENTIAL", confidential_ind="Y"),
        _nc(ncid="EE5", last_name="L#E"),  # masked under county review: no party
        _nc(ncid="", voter_reg_num="000000000042", last_name="KIM"),
    ]  # fmt: skip
    out = _run(NorthCarolinaVoterFile, _nc_zip(rows))
    srs = _rows(out, "source_record")
    assert [s["record_key"] for s in srs] == ["EE1", "EE2", "EE3", "EE5", "89-000000000042"]
    parties = {p["record_key"]: p for p in _rows(out, "party")}
    assert set(parties) == {"EE1", "EE2", "EE3", "89-000000000042"}
    ann = parties["EE1"]
    assert ann["raw_name"] == "LEE ANN B" and ann["party_kind"] == "person"
    assert (ann["last_name"], ann["first_name"], ann["middle"], ann["suffix"]) == (
        "LEE", "ANN", "B", None)  # fmt: skip
    assert ann["jurisdiction"] == "37177"  # Tyrrell: county 89 -> FIPS 177
    home = normalized_address("12 MAIN ST", "COLUMBIA", "NC", "27925")
    assert home is not None and ann["address_id"] == home["address_id"]
    assert parties["EE2"]["raw_name"] == "RAY BOB III"
    assert parties["EE3"]["address_id"] is None  # 'REMOVED' is no street
    addresses = _rows(out, "address")
    assert [a["line1"] for a in addresses] == ["12 MAIN ST", "PO BOX 9"]  # mailing == home once
    # Phone, race and other unkept columns never reach the hashed record.
    kept = {k: v for k, v in rows[0].items() if k in NorthCarolinaVoterFile.keep}
    assert srs[0]["raw_sha256"] == sha256_hex(canonical_json(kept))
    assert out == _run(NorthCarolinaVoterFile, _nc_zip(rows))


def test_ohio_layout_keeps_no_voting_history() -> None:
    rows = [_oh(), _oh(SOS_VOTERID="OH2", LAST_NAME="RAY", FIRST_NAME="BOB", MIDDLE_NAME="",
                       SUFFIX="", MAILING_ADDRESS1="", MAILING_CITY="", MAILING_STATE="",
                       MAILING_ZIP="", RESIDENTIAL_SECONDARY_ADDR="")]  # fmt: skip
    out = _run(OhioVoterFile, _oh_gz(rows))
    parties = _rows(out, "party")
    assert [p["raw_name"] for p in parties] == ["LEE ANN B JR", "RAY BOB"]
    assert {p["jurisdiction"] for p in parties} == {"39163"}  # Vinton: county 82 -> FIPS 163
    lines = [a["line1"] for a in _rows(out, "address")]
    assert lines == ["9 ELM ST APT 2", "PO BOX 7", "9 ELM ST"]
    sr = _rows(out, "source_record")[0]
    kept = {k: v for k, v in rows[0].items() if k in OhioVoterFile.keep}
    assert "PRIMARY-03/07/2000" not in kept and "PRECINCT_NAME" not in kept
    assert sr["raw_sha256"] == sha256_hex(canonical_json(kept))
    assert all("1970-01-02" not in json.dumps(r, default=str) for _, r in out)


def test_json_sample_normalizes_like_the_raw_file() -> None:
    raw = _oh_gz([_oh()])
    kept = {k: v for k, v in _oh().items() if k in OhioVoterFile.keep}
    sample = canonical_json({"url": "u", "rows": [kept]})
    assert _run(OhioVoterFile, raw) == _run(OhioVoterFile, sample)


@pytest.mark.parametrize("cls", [OhioVoterFile, NorthCarolinaVoterFile])
def test_pii_fields_cover_every_name_address_dob_and_id_column(
    cls: type[VoterFileAdapter],
) -> None:
    assert set(cls.pii_fields) <= set(cls.keep)
    words = ("NAME", "ADDR", "BIRTH", "VOTERID", "NCID", "REG_NUM", "REGISTR", "COUNTY_ID")
    for col in cls.keep:
        street = any(col in group[0] for group in (cls.res_columns, cls.mail_columns))
        named = col in cls.name_columns
        if (street or named or any(w in col.upper() for w in words)) and col != "county_id":
            assert col in cls.pii_fields, col
    sample = _oh() if cls is OhioVoterFile else _nc()
    kept = {k: v for k, v in sample.items() if k in cls.keep}
    skips = frozenset(cls.config["skip_names"])
    assert _walk(scrub([kept], cls.pii_fields, skips), cls.pii_fields, skips) == []


def _client(pages: Mapping[str, tuple[int, bytes, str]]) -> PoliteClient:
    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("/robots.txt"):
            return 404, b"", "text/plain"
        return pages.get(url, (404, b"missing", "text/plain"))

    return PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None, retries=0)


NC_PAGE = b"""<ul>
<li><a href="https://s3.amazonaws.com/dl.ncsbe.gov/data/ncvoter_Statewide.zip">Statewide</a></li>
<li><a href="https://s3.amazonaws.com/dl.ncsbe.gov/data/ncvoter2.zip">Alexander County</a></li>
<li><a href="https://s3.amazonaws.com/dl.ncsbe.gov/data/ncvoter100.zip">Yancey County</a></li>
<li><a href="https://s3.amazonaws.com/dl.ncsbe.gov/data/ncvoter1.zip">Alamance County</a></li>
<li><a href="https://s3.amazonaws.com/dl.ncsbe.gov/data/layout_ncvoter.txt">layout</a></li>
</ul>"""

OH_PAGE = b"""<table><tr><th>County</th><th>File</th></tr>
<tr><td>ADAMS</td><td><a href="f?p=VOTERFTP:DOWNLOAD::FILE:NO:2:P2_PRODUCT_NUMBER:1">Download</a>
</td></tr>
<tr><td>Van Wert</td><td><a href="f?p=VOTERFTP:DOWNLOAD::FILE:NO:2:P2_PRODUCT_NUMBER:81">Download
</a></td></tr></table>
<a href="/ords/files/VINTON.txt.gz">Vinton County</a>
<a href="f?p=VOTERFTP:DOWNLOAD::FILE:NO:2:P2_PRODUCT_NUMBER:363">SWVF_1_22 (Adams-Erie)</a>
<a href="/elections/">Elections</a>"""


def test_partitions_from_the_index_pages() -> None:
    nc = NorthCarolinaVoterFile(_client({NorthCarolinaVoterFile.index_url: (200, NC_PAGE, "")}))
    assert list(nc.partitions()) == [{"county": "1"}, {"county": "2"}, {"county": "100"}]
    links = county_links(OH_PAGE.decode(), OhioVoterFile.index_url, OhioVoterFile.counties)
    base = "https://www6.ohiosos.gov/ords/"
    assert links == {
        1: base + "f?p=VOTERFTP:DOWNLOAD::FILE:NO:2:P2_PRODUCT_NUMBER:1",
        81: base + "f?p=VOTERFTP:DOWNLOAD::FILE:NO:2:P2_PRODUCT_NUMBER:81",
        82: "https://www6.ohiosos.gov/ords/files/VINTON.txt.gz",
    }
    oh = OhioVoterFile(_client({OhioVoterFile.index_url: (200, OH_PAGE, "text/html")}))
    assert list(oh.partitions()) == [{"county": "01"}, {"county": "81"}, {"county": "82"}]
    with pytest.raises(RuntimeError, match="HTTP 403"):
        list(OhioVoterFile(_client({OhioVoterFile.index_url: (403, b"<html>", "")})).partitions())


def test_counties_and_fips() -> None:
    assert county_number("089", NorthCarolinaVoterFile.counties) == 89
    assert county_number("New Hanover", NorthCarolinaVoterFile.counties) == 65
    assert county_number("vinton", OhioVoterFile.counties) == 82
    assert county_fips("37", 100) == "37199" and county_fips("39", 88) == "39175"
    with pytest.raises(ValueError, match="unknown county"):
        county_number("101", NorthCarolinaVoterFile.counties)


def test_fetch_limit_keeps_a_json_sample_of_kept_columns() -> None:
    url = "https://s3.amazonaws.com/dl.ncsbe.gov/data/ncvoter89.zip"
    body = _nc_zip([_nc(ncid=f"EE{i}") for i in range(5)])
    nc = NorthCarolinaVoterFile(_client({url: (200, body, "application/zip")}))
    f = nc.fetch(FetchRequest({"county": "Tyrrell", "limit": "3"}))
    data = json.loads(f.content)
    assert f.request == url and data["url"] == url and len(data["rows"]) == 3
    assert set(data["rows"][0]) == set(NorthCarolinaVoterFile.keep)  # no phone, race...
    assert nc.fetch(FetchRequest({"county": "89"})).content == body


def test_ohio_block_page_and_hand_saved_file(tmp_path: Path) -> None:
    blocked = OhioVoterFile(_client({OhioVoterFile.index_url: (403, b"<!DOCTYPE html>", "")}))
    with pytest.raises(RuntimeError, match="path=<file>"):
        blocked.fetch(FetchRequest({"county": "82"}))
    path = tmp_path / "VINTON.txt.gz"
    path.write_bytes(_oh_gz([_oh(), _oh(SOS_VOTERID="OH2")]))
    f = blocked.fetch(FetchRequest({"county": "VINTON", "path": str(path), "limit": "1"}))
    assert f.request.endswith("voter-files-download/#county=82") and f.http_status is None
    assert [r["SOS_VOTERID"] for r in json.loads(f.content)["rows"]] == ["OH0016238254"]
    # A download that answers with an HTML page is refused, not parsed.
    link = "https://www6.ohiosos.gov/ords/files/VINTON.txt.gz"
    page = b"<html>maintenance</html>"
    html_dl = OhioVoterFile(_client({OhioVoterFile.index_url: (200, OH_PAGE, ""),
                                     link: (200, page, "text/html")}))  # fmt: skip
    with pytest.raises(RuntimeError, match="not a voter file"):
        html_dl.fetch(FetchRequest({"county": "82"}))


def test_nc_health_reads_the_layout() -> None:
    layout = (b"-- File layout (from 02/01/2026)\nname   data type   description\n----\n"
              + b"\n".join(f"{c}   varchar(9)   x".encode() for c in NC_HEADER)
              + b"\n----\nname   data type\n----\nold_col  int  x\n----\n")  # fmt: skip
    assert layout_columns(layout.decode()) == tuple(NC_HEADER)
    url = "https://s3.amazonaws.com/dl.ncsbe.gov/data/layout_ncvoter.txt"
    rep = NorthCarolinaVoterFile(_client({url: (200, layout, "text/plain")})).health()
    assert rep.ok and "ncid" in rep.shape
    bad = NorthCarolinaVoterFile(_client({url: (200, layout.replace(b"ncid", b"nc_id"), "")}))
    assert not bad.health().ok


@pytest.mark.parametrize("cls", [OhioVoterFile, NorthCarolinaVoterFile])
def test_recorded_fixtures_are_pseudonymized_and_load(
    cls: type[VoterFileAdapter], empty_db: Any
) -> None:
    """Until registry.py lists these adapters, check their fixtures here."""
    files = sorted((ADAPTER_FIXTURES / cls.source_id).glob("*.json"))
    if not files:
        pytest.skip(f"{cls.source_id}: no fixture recorded yet")
    skips = frozenset(cls.config["skip_names"])
    for path in files:
        data = json.loads(path.read_text())
        assert data["rows"], path.name
        assert _walk(data, cls.pii_fields, skips) == [], path.name
    check_contract(cls, files, empty_db)


# =========================================================================================
# Hand-delivered statewide files (AK, AR, CO, DC, FL, MI, MS, WI): inline samples in each
# state's published layout. No fixtures are recorded until a delivery arrives.
# =========================================================================================


def _csv(header: list[str], rows: list[dict[str, str]], delim: str = ",") -> str:
    def line(vals: list[str]) -> str:
        return delim.join('"' + v.replace('"', '""') + '"' if delim == "," else v for v in vals)

    return "\r\n".join([line(header)] + [line([r.get(h, "") for h in header]) for r in rows])


def _zip(members: Mapping[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in members.items():
            zf.writestr(name, body)
    return buf.getvalue()


def _norm(cls: type[VoterFileAdapter], content: bytes) -> list[tuple[str, dict[str, Any]]]:
    return _run(cls, content)


# -- Florida: 67 headerless tab-delimited county files, 38 fields --------------------------
def _fl(**kw: str) -> dict[str, str]:
    base = dict.fromkeys(FloridaVoterFile.columns, "")
    base.update(COUNTY_CODE="DAD", VOTER_ID="100000001", NAME_LAST="LEE", NAME_SUFFIX="JR",
                NAME_FIRST="ANN", NAME_MIDDLE="B", REQUESTED_PUBLIC_RECORDS_EXEMPTION="N",
                RESIDENCE_ADDRESS_LINE_1="9 ELM ST", RESIDENCE_ADDRESS_LINE_2="APT 2",
                RESIDENCE_CITY="MIAMI", RESIDENCE_STATE="", RESIDENCE_ZIPCODE="331301234",
                MAILING_ADDRESS_LINE_1="PO BOX 7", MAILING_CITY="MIAMI", MAILING_STATE="FL",
                MAILING_ZIPCODE="33101", GENDER="F", RACE="5", BIRTH_DATE="01/02/1970",
                REGISTRATION_DATE="05/06/1990", PARTY_AFFILIATION="NPA", VOTER_STATUS="ACT",
                DAYTIME_AREA_CODE="305", DAYTIME_PHONE_NUMBER="5550100",
                EMAIL_ADDRESS="ann@example.test")  # fmt: skip
    base.update(kw)
    return base


def _fl_file(rows: list[dict[str, str]]) -> str:
    return "".join("\t".join(r[c] for c in FloridaVoterFile.columns) + "\r\n" for r in rows)


def test_fl_county_files_partitions_and_exemptions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(voter_files, "MANUAL_DIR", tmp_path)
    drop = FloridaVoterFile.drop_dir()
    drop.mkdir(parents=True)
    dad = [_fl(), _fl(VOTER_ID="100000002", REQUESTED_PUBLIC_RECORDS_EXEMPTION="Y",
                      RESIDENCE_ADDRESS_LINE_1="*"),
           _fl(VOTER_ID="100000003", NAME_LAST="RAY", NAME_FIRST="BOB", NAME_MIDDLE="",
               NAME_SUFFIX="", MAILING_ADDRESS_LINE_1="")]  # fmt: skip
    (drop / "DAD_20261110.txt").write_text(_fl_file(dad))
    (drop / "DAD_H_20261110.txt").write_text("DAD\t100000001\t11/03/2026\tGEN\tY\n")
    (drop / "disk.zip").write_bytes(_zip({
        "ALA_20261010.txt": _fl_file([_fl(COUNTY_CODE="ALA", VOTER_ID="9")]),
        "ALA_20261110.txt": _fl_file([_fl(COUNTY_CODE="ALA", VOTER_ID="8")]),
    }))  # fmt: skip
    fl = FloridaVoterFile()
    assert list(fl.partitions()) == [{"county": "12001"}, {"county": "12086"}]
    f = fl.fetch(FetchRequest({"county": "Miami-Dade"}))
    assert f.content == _fl_file(dad).encode() and f.http_status is None
    assert f.request.startswith(FloridaVoterFile.request_url) and "DAD_20261110" in f.request
    ala = fl.fetch(FetchRequest({"county": "ALA"}))  # the newest monthly file wins
    assert [s["record_key"] for s in _rows(_norm(FloridaVoterFile, ala.content),
                                           "source_record")] == ["8"]  # fmt: skip
    out = _norm(FloridaVoterFile, f.content)
    assert [s["record_key"] for s in _rows(out, "source_record")] == ["100000001", "100000003"]
    parties = _rows(out, "party")
    assert [p["raw_name"] for p in parties] == ["LEE ANN B JR", "RAY BOB"]
    assert {p["jurisdiction"] for p in parties} == {"12086"}  # Miami-Dade, not 12025
    home = normalized_address("9 ELM ST APT 2", "MIAMI", "FL", "33130")  # state defaults
    assert home is not None and parties[0]["address_id"] == home["address_id"]
    # RAY's mailing record has a city and ZIP but no street: a city-level address row.
    assert [a["line1"] for a in _rows(out, "address")] == ["9 ELM ST APT 2", "PO BOX 7", None]
    sample = json.loads(fl.fetch(FetchRequest({"county": "12086", "limit": "1"})).content)
    assert set(sample["rows"][0]) == set(FloridaVoterFile.keep)
    assert "EMAIL_ADDRESS" not in sample["rows"][0] and "RACE" not in sample["rows"][0]
    assert _norm(FloridaVoterFile, canonical_json(sample)) == _norm(
        FloridaVoterFile, _fl_file(dad[:1]).encode())  # fmt: skip


# -- Michigan: QVF CSV with header, or fixed-length .lst ------------------------------------
MI_HEADER = [c for c, _, _ in voter_files.MI_FIXED] + ["COUNTY_NAME", "JURISDICTION_NAME"]


def _mi(**kw: str) -> dict[str, str]:
    base = dict.fromkeys(MI_HEADER, "")
    base.update(LAST_NAME="LEE", FIRST_NAME="ANN", MIDDLE_NAME="B", NAME_SUFFIX="JR",
                YEAR_OF_BIRTH="1970", GENDER="F", REGISTRATION_DATE="05061990",
                STREET_NUMBER="9", DIRECTION_PREFIX="N", STREET_NAME="ELM", STREET_TYPE="ST",
                EXTENSION="APT 2", CITY="DETROIT", STATE="MI", ZIP_CODE="48201",
                MAILING_ADDRESS_LINE_ONE="PO BOX 7", MAILING_ADDRESS_LINE_TWO="DETROIT MI 48231",
                VOTER_IDENTIFICATION_NUMBER="0123456789012", COUNTY_CODE="82",
                COUNTY_NAME="WAYNE", JURISDICTION_CODE="82000", JURISDICTION_NAME="DETROIT",
                VOTER_STATUS_TYPE_CODE="A")  # fmt: skip
    base.update(kw)
    return base


def _mi_fixed(rows: list[dict[str, str]]) -> str:
    def line(r: dict[str, str]) -> str:
        buf = [" "] * 519
        for c, a, b in voter_files.MI_FIXED:
            buf[a:b] = list(r[c][: b - a].ljust(b - a))
        return "".join(buf)

    return "\r\n".join(line(r) for r in rows) + "\r\n"


def test_mi_csv_and_fixed_width_agree_and_split_by_county(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [_mi(), _mi(VOTER_IDENTIFICATION_NUMBER="2", LAST_NAME="RAY", FIRST_NAME="BOB",
                       MIDDLE_NAME="", NAME_SUFFIX="", COUNTY_CODE="01", COUNTY_NAME="ALCONA",
                       MAILING_ADDRESS_LINE_ONE="", MAILING_ADDRESS_LINE_TWO="")]  # fmt: skip
    csv_out = _norm(MichiganVoterFile, _csv(MI_HEADER, rows).encode())
    parties = _rows(csv_out, "party")
    assert [(p["raw_name"], p["jurisdiction"]) for p in parties] == [
        ("LEE ANN B JR", "26163"), ("RAY BOB", "26001")]  # fmt: skip
    assert [a["line1"] for a in _rows(csv_out, "address")] == ["9 N ELM ST APT 2", "PO BOX 7"]
    mail = normalized_address("PO BOX 7", "DETROIT", "MI", "48231")
    assert mail is not None and mail["address_id"] in {a["address_id"] for a in
                                                         _rows(csv_out, "address")}  # fmt: skip
    # The .lst has no COUNTY_NAME/JURISDICTION_NAME: same people, same addresses.
    lst = MichiganVoterFile().read_member("entire_state_v.lst", io.BytesIO(
        _mi_fixed(rows).encode()))  # fmt: skip
    first = next(lst)
    assert first["VOTER_IDENTIFICATION_NUMBER"] == "0123456789012" and first["STATE"] == "MI"
    fixed_out = _norm(MichiganVoterFile, _mi_fixed(rows).encode())
    assert [(p["raw_name"], p["jurisdiction"], p["address_id"]) for p in
            _rows(fixed_out, "party")] == [(p["raw_name"], p["jurisdiction"], p["address_id"])
                                           for p in parties]  # fmt: skip
    # A statewide delivery (zip with history and code tables) splits into county extracts.
    monkeypatch.setattr(voter_files, "MANUAL_DIR", tmp_path / "manual")
    monkeypatch.setattr(voter_files, "WORK_DIR", tmp_path / "work")
    drop = MichiganVoterFile.drop_dir()
    drop.mkdir(parents=True)
    (drop / "qvf.zip").write_bytes(_zip({
        "EntireStateVoters.csv": _csv(MI_HEADER, rows),
        "EntireStateVoterHistory.csv": "VOTER_IDENTIFICATION_NUMBER,ELECTION_DATE\r\n1,2026\r\n",
        "countycd.lst": "01ALCONA\r\n",
    }))  # fmt: skip
    mi = MichiganVoterFile()
    assert list(mi.partitions()) == [{"county": "26001"}, {"county": "26163"}]
    wayne = mi.fetch(FetchRequest({"county": "Wayne"}))
    assert wayne.content_type == "application/gzip" and "county=26163" in wayne.request
    out = _norm(MichiganVoterFile, wayne.content)
    assert [p["raw_name"] for p in _rows(out, "party")] == ["LEE ANN B JR"]
    direct = _norm(MichiganVoterFile, _csv(MI_HEADER, rows[:1]).encode())
    assert _rows(out, "source_record")[0]["raw_sha256"] == _rows(direct, "source_record")[0][
        "raw_sha256"]  # fmt: skip
    with pytest.raises(ValueError, match="county= is required"):
        mi.fetch(FetchRequest({}))
    assert mi.health().ok


# -- Colorado: EX-003 header names, or the short SCORE export names ------------------------
CO_HEADER = ["VOTER_ID", "COUNTY_CODE", "COUNTY", "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME",
             "NAME_SUFFIX", "VOTER_NAME", "STATUS_CODE", "PRECINCT_NAME", "RESIDENTIAL_ADDRESS",
             "RESIDENTIAL_CITY", "RESIDENTIAL_STATE", "RESIDENTIAL_ZIP_CODE",
             "RESIDENTIAL_ZIP_PLUS", "EFFECTIVE_DATE", "REGISTRATION_DATE", "STATUS",
             "STATUS_REASON", "BIRTH_YEAR", "GENDER", "PARTY", "PARTY_AFFILIATION_DATE",
             "PHONE_NUM", "MAILING_ADDRESS_1", "MAILING_ADDRESS_2", "MAILING_ADDRESS_3",
             "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP_CODE", "MAILING_ZIP_PLUS",
             "MAILING_COUNTRY", "CONGRESSIONAL"]  # fmt: skip
BOCO_HEADER = ["COUNTY", "VOTER_ID", "FIRST_NAME", "MIDDLE_NAME", "LAST_NAME", "NAME_SUFFIX",
               "VOTER_NAME", "YOB", "GENDER", "PARTY", "POLPARTY_AFF_DATE", "STATUS",
               "STATUS_REASON", "COUNTY_REGN_DATE", "EFF_DATE", "VR_PHONE", "RES_ADDRESS",
               "RES_CITY", "RES_STATE", "RES_ZIP_CODE", "RES_ZIP_PLUS", "MAIL_ADDR1",
               "MAIL_ADDR2", "MAIL_ADDR3", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
               "MAILING_ZIP_PLUS", "MAILING_COUNTRY"]  # fmt: skip


def test_co_ex003_and_score_export_names_read_alike() -> None:
    ex003 = [{"VOTER_ID": "600001", "COUNTY_CODE": "8", "COUNTY": "Broomfield",
              "LAST_NAME": "LEE", "FIRST_NAME": "ANN", "MIDDLE_NAME": "B",
              "RESIDENTIAL_ADDRESS": "9 ELM ST", "RESIDENTIAL_CITY": "BROOMFIELD",
              "RESIDENTIAL_STATE": "CO", "RESIDENTIAL_ZIP_CODE": "80020",
              "REGISTRATION_DATE": "05/06/1990", "STATUS": "Active", "BIRTH_YEAR": "1970",
              "PARTY": "UAF", "PHONE_NUM": "3035550100", "MAILING_ADDRESS_1": "PO BOX 7",
              "MAILING_CITY": "BROOMFIELD", "MAILING_STATE": "CO", "MAILING_ZIP_CODE": "80038"},
             {"VOTER_ID": "600002", "COUNTY": "El Paso", "LAST_NAME": "RAY",
              "FIRST_NAME": "BOB", "RESIDENTIAL_ADDRESS": "1 PINE AVE",
              "RESIDENTIAL_CITY": "COLORADO SPRINGS", "RESIDENTIAL_STATE": "CO",
              "RESIDENTIAL_ZIP_CODE": "80903"}]  # fmt: skip
    out = _norm(ColoradoVoterFile, _csv(CO_HEADER, ex003).encode())
    parties = _rows(out, "party")
    assert [(p["raw_name"], p["jurisdiction"]) for p in parties] == [
        ("LEE ANN B", "08014"), ("RAY BOB", "08041")]  # fmt: skip
    assert [a["line1"] for a in _rows(out, "address")] == ["9 ELM ST", "PO BOX 7", "1 PINE AVE"]
    renamed = {"BIRTH_YEAR": "YOB", "REGISTRATION_DATE": "COUNTY_REGN_DATE",
               "RESIDENTIAL_ADDRESS": "RES_ADDRESS", "RESIDENTIAL_CITY": "RES_CITY",
               "RESIDENTIAL_STATE": "RES_STATE", "RESIDENTIAL_ZIP_CODE": "RES_ZIP_CODE",
               "MAILING_ADDRESS_1": "MAIL_ADDR1", "MAILING_ZIP_CODE": "MAILING_ZIP",
               "PHONE_NUM": "VR_PHONE"}  # fmt: skip
    boco = [{renamed.get(k, k): v for k, v in r.items()} for r in ex003]
    pipe = _norm(ColoradoVoterFile, _csv(BOCO_HEADER, boco, "|").encode())
    assert [(p["raw_name"], p["jurisdiction"], p["address_id"]) for p in
            _rows(pipe, "party")] == [(p["raw_name"], p["jurisdiction"], p["address_id"])
                                      for p in parties]  # fmt: skip
    sample = json.loads(ColoradoVoterFile().sample("u", iter(
        ColoradoVoterFile().raw_rows(_csv(BOCO_HEADER, boco, "|").encode())), 1))  # fmt: skip
    assert sample["rows"][0]["BIRTH_YEAR"] == "1970" and "VR_PHONE" not in sample["rows"][0]


def test_boulder_county_file_is_downloaded_and_read_like_colorado() -> None:
    """Boulder's free VR-011B zip is fetched directly, read through Colorado's SCORE aliases,
    and its health is the data-access page still linking the zip."""
    cls = voter_files.BoulderCountyVoterFile
    row = {"COUNTY": "Boulder", "VOTER_ID": "600009", "LAST_NAME": "LEE", "FIRST_NAME": "ANN",
           "YOB": "1970", "VR_PHONE": "3035550100", "RES_ADDRESS": "9 ELM ST",
           "RES_CITY": "BOULDER", "RES_STATE": "CO", "RES_ZIP_CODE": "80302"}  # fmt: skip
    body = _zip({"CE-VR011B_EXTERNAL_20261125.txt": _csv(BOCO_HEADER, [row], "|")})
    page = f'<a href="{cls.download_url}">Download</a>'.encode()
    client = _client({cls.download_url: (200, body, "application/x-zip-compressed"),
                      cls.request_url: (200, page, "text/html")})  # fmt: skip
    a = cls(client)
    assert list(a.partitions()) == [{"county": "08013"}]
    fetched = a.fetch(FetchRequest({"county": "08013"}))
    out = [(r.table, dict(r.row)) for r in a.normalize(fetched)]
    assert [(p["raw_name"], p["jurisdiction"]) for p in _rows(out, "party")] == [
        ("LEE ANN", "08013")]  # fmt: skip
    sample = json.loads(a.fetch(FetchRequest({"county": "08013", "limit": "5"})).content)
    assert sample["rows"][0]["BIRTH_YEAR"] == "1970" and "VR_PHONE" not in sample["rows"][0]
    assert a.health().ok
    src = a.source_row()
    assert (src["cost_model"], src["base_url"], src["jurisdiction"]) == (
        "free", cls.download_url, "08013")  # fmt: skip
    bad = cls(_client({cls.download_url: (200, b"<html>blocked</html>", "text/html")}))
    with pytest.raises(RuntimeError, match="not the voter file zip"):
        bad.fetch(FetchRequest({"county": "08013"}))
    assert not bad.health().ok


# -- Wisconsin: Badger Voters CSV ----------------------------------------------------------
WI_HEADER = ["Voter Reg Number", "LastName", "FirstName", "MiddleName", "Suffix",
             "PhoneNumber", "EmailAddress", "Address1", "Address2", "MailingAddress1",
             "MailingAddress2", "MailingCityStateZip", "HouseNumber", "StreetName", "UnitType",
             "UnitNumber", "ZipCode", "Jurisdiction", "DistrictCombo", "Ward", "County",
             "Municipality", "Voter Status", "Voter Status Reason", "RegistrationDate",
             "ApplicationSource", "IsPermanentAbsentee", "Voter Type", "Nov-24",
             "Apr-24"]  # fmt: skip


def test_wi_badger_voters_layout() -> None:
    rows = [{"Voter Reg Number": "0009000001", "LastName": "Lee", "FirstName": "Ann",
             "MiddleName": "B", "PhoneNumber": "(608) 555-0100", "EmailAddress": "a@x.test",
             "Address1": "9 N ELM ST APT 2", "Address2": "MADISON WI 53703-1234",
             "ZipCode": "53703-1234", "County": "Dane County", "Voter Status": "Active",
             "RegistrationDate": "05/06/1990", "Nov-24": "At Polls"},
            {"Voter Reg Number": "0009000002", "LastName": "Ray", "FirstName": "Bob",
             "Address1": "1 PINE RD", "Address2": "KESHENA WI 54135",
             "MailingAddress1": "PO BOX 7", "MailingCityStateZip": "KESHENA, WI 54135",
             "County": "Menominee County", "Voter Status": "Inactive"}]  # fmt: skip
    out = _norm(WisconsinVoterFile, _csv(WI_HEADER, rows).encode())
    parties = _rows(out, "party")
    assert [(p["raw_name"], p["jurisdiction"]) for p in parties] == [
        ("Lee Ann B", "55025"), ("Ray Bob", "55078")]  # fmt: skip
    addresses = _rows(out, "address")
    assert [(a["line1"], a["city"], a["zip5"]) for a in addresses] == [
        ("9 N ELM ST APT 2", "MADISON", "53703"), ("1 PINE RD", "KESHENA", "54135"),
        ("PO BOX 7", "KESHENA", "54135")]  # fmt: skip
    kept = WisconsinVoterFile().kept(next(iter(WisconsinVoterFile().raw_rows(
        _csv(WI_HEADER, rows).encode()))))  # fmt: skip
    assert "PHONENUMBER" not in kept and "NOV_24" not in kept
    assert kept["VOTER_REG_NUMBER"] == "0009000001" and kept["COUNTY"] == "Dane County"


# -- Arkansas: VR.csv (VH.csv is history) --------------------------------------------------
AR_HEADER = ["County", "VoterID", "KEY_REGISTRANT", "CDE_REGISTRANT_STATUS",
             "CDE-REGISTRANT_REASON", "date_of_birth", "date_of_registration", "CDE_NAME_TITLE",
             "TEXT_NAME_LAST", "TEXT_NAME_FIRST", "TEXT_NAME_MIDDLE", "CDE_NAME_SUFFIX",
             *voter_files.AR_STREET, "TEXT_RES_CITY", "CDE_RES_STATE", "TEXT_RES_ZIP5",
             "TEXT_RES_ZIP4", "IND_MAIL", *voter_files.AR_MAIL, "TEXT_MAIL_ZIP5",
             "TEXT_MAIL_ZIP4", "PrecinctName", "CDE_PARTY", "date_of_party_affiliation",
             "TEXT_PHONE_AREA_CODE", "TEXT_PHONE_EXCHANGE", "TEXT_PHONE_LAST_FOUR",
             "CongressionalDistrict", "DateLastVoted"]  # fmt: skip


def test_ar_vr_file_in_zip_skips_history() -> None:
    row = {"County": "Pulaski", "VoterID": "000123", "CDE_REGISTRANT_STATUS": "A",
           "date_of_birth": "01/02/1970", "date_of_registration": "05/06/1990",
           "TEXT_NAME_LAST": "LEE", "TEXT_NAME_FIRST": "ANN", "TEXT_NAME_MIDDLE": "B",
           "TEXT_REGISTRANT_ADDRESS_NBR": "9", "TEXT_STREET_NAME": "ELM",
           "DESC_STREET_TYPE": "ST", "TEXT_RES_CITY": "LITTLE ROCK", "CDE_RES_STATE": "AR",
           "TEXT_RES_ZIP5": "72201", "TEXT_MAIL_ADDRESS1": "PO BOX 7",
           "TEXT_MAIL_ADDRESS2": "LITTLE ROCK AR 72203", "TEXT_MAIL_ZIP5": "72203",
           "CDE_PARTY": "R", "TEXT_PHONE_LAST_FOUR": "0100",
           "DateLastVoted": "11/03/2026"}  # fmt: skip
    body = _zip({"VR.csv": _csv(AR_HEADER, [row]), "VH.csv": "VoterID,GEN24\r\n000123,Y\r\n"})
    out = _norm(ArkansasVoterFile, body)
    (party,) = _rows(out, "party")
    assert party["raw_name"] == "LEE ANN B" and party["jurisdiction"] == "05119"
    assert [a["line1"] for a in _rows(out, "address")] == ["9 ELM ST", "PO BOX 7"]
    kept = ArkansasVoterFile().kept(next(iter(ArkansasVoterFile().raw_rows(body))))
    assert kept["VOTER_ID"] == "000123" and kept["DATE_OF_BIRTH"] == "01/02/1970"
    assert "DATELASTVOTED" not in kept and "TEXT_PHONE_LAST_FOUR" not in kept
    (sr,) = _rows(out, "source_record")
    assert sr["record_key"] == "000123"


# -- Mississippi: weekly program CSV ---------------------------------------------------------
MS_HEADER = ["Mapping Value", "FIRST_NAME", "MIDDLE_NAME", "LAST_NAME", "SUFFIX",
             "RESIDENTIAL_ADDRESS", "HOUSE_NUM", "STREET_NAME", "STREET_TYPE", "PRE-DIRECTION",
             "POST-DIRECTION", "RES_CITY", "RES_STATE", "RES_ZIP_CODE", "RES_COUNTY",
             "PRECINCT_CODE", "PRECINCT_NAME", "MAILING_ADDRESS", "MAIL_CITY", "MAIL_STATE",
             "MAIL_ZIP_CODE", "EFFECTIVE_REGN_DATE", "STATUS", "DATE_VOTED", "US",
             "CONG"]  # fmt: skip


def test_ms_weekly_file_layout() -> None:
    rows = [{"Mapping Value": "M1", "FIRST_NAME": "ANN", "LAST_NAME": "LEE",
             "RESIDENTIAL_ADDRESS": "9 ELM ST", "RES_CITY": "JACKSON", "RES_STATE": "MS",
             "RES_ZIP_CODE": "39201", "RES_COUNTY": "HINDS", "MAILING_ADDRESS": "9 ELM ST",
             "MAIL_CITY": "JACKSON", "MAIL_STATE": "MS", "MAIL_ZIP_CODE": "39201",
             "EFFECTIVE_REGN_DATE": "05/06/1990", "STATUS": "A", "DATE_VOTED": "11/03/2026"},
            {"Mapping Value": "M2", "FIRST_NAME": "BOB", "LAST_NAME": "RAY",
             "RESIDENTIAL_ADDRESS": "1 OAK DR", "RES_CITY": "OLIVE BRANCH",
             "RES_STATE": "MS", "RES_ZIP_CODE": "38654", "RES_COUNTY": "DeSoto"}]  # fmt: skip
    out = _norm(MississippiVoterFile, _csv(MS_HEADER, rows).encode())
    assert [(p["raw_name"], p["jurisdiction"]) for p in _rows(out, "party")] == [
        ("LEE ANN", "28049"), ("RAY BOB", "28033")]  # fmt: skip
    assert [a["line1"] for a in _rows(out, "address")] == ["9 ELM ST", "1 OAK DR"]
    kept = MississippiVoterFile().kept(dict(zip(
        [voter_files.canon(h) for h in MS_HEADER], [rows[0].get(h, "") for h in MS_HEADER],
        strict=True)))  # fmt: skip
    assert "DATE_VOTED" not in kept and kept["MAPPING_VALUE"] == "M1"


# -- Alaska: one statewide CSV, no borough --------------------------------------------------
AK_HEADER = ["UN", "PARTY", "DP", "PRECINCT", "LAST_NAME", "FIRST_NAME", "MIDDLE_NAME",
             "SUFFIX_NAME", "ASCENSION", "REG_DATE", "ORG_REG_DATE", "RESIDENCE_ADDRESS",
             "RESIDENCE_CITY", "RESIDENCE_ZIP", "MAILING_ADDRESS1", "MAILING_ADDRESS2",
             "MAILING_ADDRESS3", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
             "MAILING_COUNTRY", "GENDER", "CC", "STATUS", "BIRTH_DATE",
             "GENERAL 2024"]  # fmt: skip


def test_ak_statewide_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [{"PARTY": "U", "LAST_NAME": "LEE", "FIRST_NAME": "ANN", "ASCENSION": "A1",
             "REG_DATE": "05/06/1990", "RESIDENCE_ADDRESS": "9 ELM ST",
             "RESIDENCE_CITY": "JUNEAU", "RESIDENCE_ZIP": "99801",
             "MAILING_ADDRESS1": "PO BOX 7", "MAILING_CITY": "JUNEAU", "MAILING_STATE": "AK",
             "MAILING_ZIP": "99802", "STATUS": "Active", "BIRTH_DATE": "01/01/1900"},
            {"LAST_NAME": "RAY", "FIRST_NAME": "BOB", "ASCENSION": "A2",
             "MAILING_ADDRESS1": "PO BOX 9", "MAILING_CITY": "NOME", "MAILING_STATE": "AK",
             "MAILING_ZIP": "99762"}]  # fmt: skip
    body = _csv(AK_HEADER, rows).encode()
    out = _norm(AlaskaVoterFile, body)
    parties = _rows(out, "party")
    assert [(p["raw_name"], p["jurisdiction"]) for p in parties] == [
        ("LEE ANN", "02"), ("RAY BOB", "02")]  # fmt: skip
    home = normalized_address("9 ELM ST", "JUNEAU", "AK", "99801")
    assert home is not None and parties[0]["address_id"] == home["address_id"]
    assert parties[1]["address_id"] is None  # residence kept private: mailing only
    assert "BIRTH_DATE" not in AlaskaVoterFile.keep
    monkeypatch.setattr(voter_files, "MANUAL_DIR", tmp_path)
    ak = AlaskaVoterFile()
    with pytest.raises(RuntimeError, match="request it"):
        list(ak.partitions())
    assert not ak.health().ok and "awaiting delivery" in ak.health().detail
    AlaskaVoterFile.drop_dir().mkdir(parents=True)
    (AlaskaVoterFile.drop_dir() / "statewide.csv").write_bytes(body)
    assert list(ak.partitions()) == [{"county": "02"}]
    assert ak.fetch(FetchRequest({"county": "02"})).content == body


# -- District of Columbia: Excel workbook by secure link --------------------------------------
DC_HEADER = ["REGISTERED", "LASTNAME", "FIRSTNAME", "MIDDLE", "SUFFIX", "STATUS", "PARTY",
             "RES_HOUSE", "RES_FRAC", "RES_APT", "RES STREET", "RES_CITY", "RES_STATE",
             "RES_ZIP", "RES_ZIP4", "PRECINCT", "WARD", "ANC", "SMD", "110526-G"]  # fmt: skip


def _xlsx(rows: list[list[str]]) -> bytes:
    """A minimal workbook: the header and text cells as shared strings, numbers inline."""
    strings: list[str] = []
    xml_rows = []
    for i, row in enumerate(rows, start=1):
        cells = []
        for j, v in enumerate(row):
            ref = f"{chr(65 + j) if j < 26 else 'A' + chr(65 + j - 26)}{i}"
            if not v:
                continue
            if v.isdigit():
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                strings.append(v)
                cells.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
        xml_rows.append(f'<row r="{i}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    sst = "".join(f"<si><t>{s}</t></si>" for s in strings)
    return _zip({
        "xl/workbook.xml": f"<workbook {ns}/>",
        "xl/sharedStrings.xml": f"<sst {ns}>{sst}</sst>",
        "xl/worksheets/sheet1.xml": f'<worksheet {ns}><sheetData>{"".join(xml_rows)}'
                                    "</sheetData></worksheet>",
    })  # fmt: skip


def test_dc_workbook_without_voter_id() -> None:
    ann = ["32874", "LEE", "ANN", "B", "", "A", "DEMOCRATIC", "1234", "1/2", "5",
           "MAIN ST NW", "WASHINGTON", "DC", "20001", "", "21", "6", "6E", "6E01", "Y"]  # fmt: skip
    bob = ["40000", "RAY", "BOB", "", "", "A", "NO PARTY", "10", "", "", "K ST SE",
           "WASHINGTON", "DC", "20003", "", "131", "8", "", "", ""]  # fmt: skip
    out = _norm(DistrictOfColumbiaVoterFile, _xlsx([DC_HEADER, ann, bob]))
    parties = _rows(out, "party")
    assert [(p["raw_name"], p["jurisdiction"]) for p in parties] == [
        ("LEE ANN B", "11001"), ("RAY BOB", "11001")]  # fmt: skip
    lines = [a["line1"] for a in _rows(out, "address")]
    assert lines == ["1234 1 2 MAIN ST NW 5", "10 K ST SE"]  # clean(): "1/2" -> "1 2"
    keys = [s["record_key"] for s in _rows(out, "source_record")]
    assert all(k.startswith("h-") for k in keys) and len(set(keys)) == 2
    assert "ANN" not in keys[0] and "LEE" not in keys[0]  # an opaque hash, not the name
    # The same list as CSV reads the same, and a VOTER_ID column is used when present.
    as_csv = _csv(DC_HEADER, [dict(zip(DC_HEADER, r, strict=True)) for r in (ann, bob)])
    assert _rows(_norm(DistrictOfColumbiaVoterFile, as_csv.encode()), "party") == parties
    with_id = _csv(
        ["VOTER ID", *DC_HEADER], [{"VOTER ID": "DC9", **dict(zip(DC_HEADER, ann, strict=True))}]
    )
    srs = _rows(_norm(DistrictOfColumbiaVoterFile, with_id.encode()), "source_record")
    assert [s["record_key"] for s in srs] == ["DC9"]


# -- shared -----------------------------------------------------------------------------------
DELIVERED: list[type[DeliveredVoterFile]] = [
    FloridaVoterFile, MichiganVoterFile, ColoradoVoterFile, WisconsinVoterFile,
    ArkansasVoterFile, MississippiVoterFile, AlaskaVoterFile, DistrictOfColumbiaVoterFile,
]  # fmt: skip


@pytest.mark.parametrize("cls", DELIVERED)
def test_delivered_pii_fields_cover_names_streets_ids_and_dates(
    cls: type[DeliveredVoterFile],
) -> None:
    assert set(cls.pii_fields) <= set(cls.keep), cls.source_id
    assert len(set(cls.keep)) == len(cls.keep)
    must = {cls.id_column, *cls.name_columns, *cls.res_columns[0], *cls.mail_columns[0]}
    dates = re.compile(r"BIRTH|YEAR_OF_BIRTH|YOB|REG.*DATE|REGISTERED|REGISTRATIONDATE|EFFECTIVE")
    must |= {c for c in cls.keep if dates.search(c)}
    assert must - set(cls.pii_fields) == set(), cls.source_id
    never = re.compile(r"PHONE|EMAIL|GENDER|RACE|SSN|LICENSE|HIST|VOTED")
    assert [c for c in cls.keep if never.search(c)] == [], cls.source_id
    row = {c: f"X{c}" for c in cls.keep}
    skips = frozenset(cls.config["skip_names"])
    assert _walk(scrub([row], cls.pii_fields, skips), cls.pii_fields, skips) == []
    assert cls.access_method == "manual" and not cls.index_url
    assert cls.request_url.startswith("https://") and cls.layout_url.startswith("https://")


@pytest.mark.parametrize(
    ("cls", "body"),
    [
        (FloridaVoterFile, lambda: _fl_file([_fl(), _fl(VOTER_ID="7", NAME_LAST="RAY")])),
        (MichiganVoterFile, lambda: _csv(MI_HEADER, [_mi()])),
        (ColoradoVoterFile, lambda: _csv(CO_HEADER, [{"VOTER_ID": "1", "COUNTY": "Denver",
                                                      "LAST_NAME": "LEE",
                                                      "RESIDENTIAL_ADDRESS": "9 ELM ST"}])),
        (WisconsinVoterFile, lambda: _csv(WI_HEADER, [{"Voter Reg Number": "1",
                                                       "LastName": "Lee",
                                                       "Address1": "9 ELM ST",
                                                       "County": "Dane County"}])),
        (ArkansasVoterFile, lambda: _csv(AR_HEADER, [{"VoterID": "1", "County": "Pope",
                                                      "TEXT_NAME_LAST": "LEE"}])),
        (MississippiVoterFile, lambda: _csv(MS_HEADER, [{"Mapping Value": "1",
                                                         "LAST_NAME": "LEE",
                                                         "RES_COUNTY": "Lee"}])),
        (AlaskaVoterFile, lambda: _csv(AK_HEADER, [{"ASCENSION": "1", "LAST_NAME": "LEE"}])),
        (DistrictOfColumbiaVoterFile, lambda: _xlsx([DC_HEADER, ["1", "LEE", "ANN"]])),
    ],
)  # fmt: skip
def test_delivered_samples_load_and_pass_provenance(
    cls: type[DeliveredVoterFile], body: Any, tmp_path: Path, empty_db: Any
) -> None:
    """Each layout's inline sample loads into the schema (source row included) and passes the
    provenance gate, as check 7 would once a delivery is recorded."""
    content = body()
    path = tmp_path / "sample"
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    check_contract(cls, [path], empty_db)


def test_helpers() -> None:
    assert voter_files.canon("﻿Voter Reg Number") == "VOTER_REG_NUMBER"
    assert voter_files.canon("PRE-DIRECTION") == "PRE_DIRECTION"
    assert voter_files.canon("LastName") == "LASTNAME"
    co = voter_files.fips_table("08", voter_files.CO_COUNTIES, {"Broomfield": "014"})
    assert (co["ADAMS"], co["BOULDER"], co["BROOMFIELD"], co["CHAFFEE"], co["YUMA"]) == (
        "08001", "08013", "08014", "08015", "08125")  # fmt: skip
    mi = MichiganVoterFile.fips
    assert (mi["82"], mi["WAYNE"], mi["STCLAIR"], mi["83"]) == (
        "26163", "26163", "26147", "26165")  # fmt: skip
    fl = FloridaVoterFile.fips
    assert (fl["DAD"], fl["DES"], fl["STJ"], fl["SAN"], fl["WAS"]) == (
        "12086", "12027", "12109", "12113", "12133")  # fmt: skip
    wi = WisconsinVoterFile.fips
    assert (wi["MENOMINEE"], wi["MILWAUKEE"], wi["WOOD"]) == ("55078", "55079", "55141")
    assert (ArkansasVoterFile.fips["YELL"], MississippiVoterFile.fips["YAZOO"]) == (
        "05149", "28163")  # fmt: skip
    a = voter_files.split_city_line(["PO BOX 7", "DETROIT, MI 48231-0007"])
    assert a is not None and (a["line1"], a["city"], a["state"], a["zip5"]) == (
        "PO BOX 7", "DETROIT", "MI", "48231")  # fmt: skip
    b = voter_files.split_city_line(["12 OAK CT"], "06511")  # no ZIP on the line: all street
    assert b is not None and (b["line1"], b["city"], b["zip5"]) == ("12 OAK CT", None, "06511")
    assert voter_files.split_city_line([None, " "]) is None
    with pytest.raises(ValueError, match="unknown MI county"):
        MichiganVoterFile().county_key("Atlantis")
