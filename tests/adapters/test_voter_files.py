"""Ohio and North Carolina statewide voter files: streaming parse of both layouts, pii coverage,
county partitions from the index pages, and the recorded fixtures."""

from __future__ import annotations

import gzip
import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import PoliteClient
from equity.adapters.record import scrub
from equity.adapters.rows import canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.adapters.voter_files import (
    NorthCarolinaVoterFile,
    OhioVoterFile,
    VoterFileAdapter,
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
