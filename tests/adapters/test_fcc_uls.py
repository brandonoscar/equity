"""FCC ULS weekly license files (equity.adapters.federal.fcc_uls) on inline .dat samples."""

from __future__ import annotations

import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal import bulk_zip
from equity.adapters.federal.bulk_zip import DownloadClient, locate_zip
from equity.adapters.federal.fcc_uls import (
    AM_WIDTH,
    EN,
    FCC_ULS_ADAPTERS,
    HD_WIDTH,
    PII,
    FCCULSAmateur,
    FCCULSLandMobilePrivate,
    records,
    split_person,
    state_partition,
)
from equity.adapters.record import scrub

AT = datetime(2026, 11, 22, 15, 0, tzinfo=UTC)


def en(**f: str) -> str:
    cells = dict.fromkeys(EN, "")
    cells.update({"record_type": "EN", "entity_type": "L", **f})
    return "|".join(cells[k] for k in EN)


def hd(usi: str, call: str, status: str, svc: str, granted: str) -> str:
    cells = [""] * HD_WIDTH
    cells[:10] = ["HD", usi, "0001", "", call, status, svc, granted, "01/01/2036", ""]
    cells[30], cells[32] = "SECRET", "CERTIFIER"  # certifier name: never kept
    cells[42], cells[43] = granted, granted
    return "|".join(cells)


def am(usi: str, call: str, op_class: str, trustee: str = "", trustee_call: str = "") -> str:
    cells = [""] * AM_WIDTH
    cells[:9] = ["AM", usi, "", "", call, op_class, "D", "4", trustee_call]
    cells[17] = trustee
    return "|".join(cells)


AMAT_EN = [
    en(usi="100", call_sign="KA1AAA", entity_name="DOE, JANE Q", first_name="JANE", mi="Q",
       last_name="DOE", street_address="12 OAK ST", city="CHARLESTON", state="WV",
       zip_code="253011234", applicant_type_code="I", frn="0001112223", email="x@y.z",
       phone="5551234567"),
    en(usi="200", call_sign="W8CLB", entity_name="MOUNTAIN RADIO CLUB", po_box="77",
       city="MORGANTOWN", state="wv", zip_code="26505", applicant_type_code="B"),
    en(usi="300", call_sign="KB2BBB", entity_name="ROE, RICHARD", first_name="RICHARD",
       last_name="ROE", street_address="5 ELM AVE", city="AKRON", state="OH",
       zip_code="44301", applicant_type_code="I"),
    en(usi="400", call_sign="KC3CCC", entity_name="POE, AL", first_name="AL", last_name="POE",
       street_address="1 RUE X", city="PARIS", state="", applicant_type_code="I"),
]  # fmt: skip
AMAT_HD = [hd("100", "KA1AAA", "A", "HA", "03/01/2020"), hd("200", "W8CLB", "A", "HV",
           "04/02/2019"), hd("300", "KB2BBB", "E", "HA", "01/01/2000"),
           hd("400", "KC3CCC", "C", "HA", "02/02/2010")]  # fmt: skip
AMAT_AM = [am("100", "KA1AAA", "E"), am("200", "W8CLB", "", "SMITH, JOHN A JR", "KA1AAA"),
           am("300", "KB2BBB", "T"), am("400", "KC3CCC", "G")]  # fmt: skip


def write_zip(path: Path, members: Mapping[str, list[str]]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, lines in members.items():
            zf.writestr(name, "".join(line + "\r\n" for line in lines))
        zf.writestr("counts", "File Creation Date: Sun Nov 22 09:41:30 EST 2026\n")
    return path


@pytest.fixture
def amat_zip(tmp_path: Path) -> Path:
    # File order differs between tables, as in the real files.
    return write_zip(tmp_path / "l_amat.zip",
                     {"EN.dat": AMAT_EN, "HD.dat": AMAT_HD[::-1], "AM.dat": AMAT_AM})  # fmt: skip


def fetch(cls: type, path: Path, **params: str) -> Fetched:
    return cls().fetch(FetchRequest({"path": str(path), **params}))  # type: ignore[no-any-return]


def test_records_rejoin_split_lines_and_skip_bad_ones() -> None:
    lines = ["EN|1|a\r\n", "b|c\r\n", "EN|2|x|y\r\n", "EN|3|p|q|r|s\r\n", "\r\n", "XX|4|a|b\r\n"]
    assert list(records(lines, "EN", 4)) == [["EN", "1", "a b", "c"], ["EN", "2", "x", "y"]]


def test_state_partitions() -> None:
    parts = [p["state"] for p in FCCULSAmateur().partitions()]
    assert parts[-1] == "other" and {"WV", "PR", "GU", "AE", "DC"} <= set(parts)
    assert len(parts) == len(set(parts)) == 61
    assert (state_partition(" wv "), state_partition(""), state_partition("ONTARIO")) == (
        "WV", "other", "other")  # fmt: skip


def test_fetch_keeps_one_state_and_joins_hd_and_am(amat_zip: Path) -> None:
    f = fetch(FCCULSAmateur, amat_zip, state="WV")
    body = json.loads(f.content)
    assert (body["file"], body["state"], body["as_of"]) == (
        "l_amat.zip",
        "WV",
        "Sun Nov 22 09:41:30 EST 2026",
    )
    assert [r["usi"] for r in body["rows"]] == ["100", "200"]
    jane = body["rows"][0]
    assert jane["license"] == {
        "uls_file_number": "0001",
        "call_sign": "KA1AAA",
        "license_status": "A",
        "radio_service_code": "HA",
        "grant_date": "03/01/2020",
        "expired_date": "01/01/2036",
        "effective_date": "03/01/2020",
        "last_action_date": "03/01/2020",
    }
    assert jane["amateur"]["operator_class"] == "E"
    text = f.content.decode()
    for never in ("x@y.z", "5551234567", "SECRET", "CERTIFIER"):  # email, phone, certifier
        assert never not in text
    assert f.request.endswith("l_amat.zip#state=WV") and f.http_status is None
    assert [r["usi"] for r in json.loads(fetch(FCCULSAmateur, amat_zip, state="other").content)
            ["rows"]] == ["400"]  # fmt: skip
    assert [
        r["usi"]
        for r in json.loads(fetch(FCCULSAmateur, amat_zip, state="WV", limit="1").content)["rows"]
    ] == ["100"]
    with pytest.raises(ValueError, match="unknown state"):
        fetch(FCCULSAmateur, amat_zip, state="ZZ")


def test_normalize_person_and_club(amat_zip: Path) -> None:
    f = fetch(FCCULSAmateur, amat_zip, state="WV")
    out = [(r.table, dict(r.row)) for r in FCCULSAmateur().normalize(f)]
    assert out == [(r.table, dict(r.row)) for r in FCCULSAmateur().normalize(f)]
    srs = [r for t, r in out if t == "source_record"]
    assert [(s["record_key"], s["record_type"]) for s in srs] == [
        ("100", "fcc_license"),
        ("200", "fcc_license"),
    ]
    parties = {r["raw_name"]: r for t, r in out if t == "party"}
    jane = parties["DOE, JANE Q"]
    assert (jane["party_kind"], jane["last_name"], jane["first_name"], jane["middle"]) == (
        "person", "DOE", "JANE", "Q")  # fmt: skip
    assert jane["jurisdiction"] == "54"  # West Virginia
    addrs = {a["address_id"]: a for t, a in out if t == "address"}
    assert addrs[jane["address_id"]]["zip5"] == "25301"
    club = parties["MOUNTAIN RADIO CLUB"]
    assert club["party_kind"] == "org"
    assert addrs[club["address_id"]]["line1"] == "PO BOX 77"
    trustee = parties["SMITH, JOHN A JR"]
    assert (trustee["party_kind"], trustee["last_name"], trustee["suffix"]) == (
        "person",
        "SMITH",
        "JR",
    )
    (biz,) = [r for t, r in out if t == "business"]  # the individual's license has none
    assert (biz["sos_id"], biz["name"], biz["status"], str(biz["formed_on"])) == (
        "FCC-ULS:200", "MOUNTAIN RADIO CLUB", "ACTIVE", "2019-04-02")  # fmt: skip
    roles = sorted((r["title"], r["party_id"]) for t, r in out if t == "business_role")
    assert roles == sorted([("LICENSEE", club["party_id"]), ("TRUSTEE", trustee["party_id"])])


def test_land_mobile_licensee_and_contact(tmp_path: Path) -> None:
    path = write_zip(tmp_path / "l_LMpriv.zip", {
        "EN.dat": [
            en(usi="9", call_sign="WQAA001", entity_type="CL", entity_name="", first_name="ANN",
               last_name="LEE", street_address="2 PINE RD", city="DAYTON", state="OH",
               zip_code="45402"),
            en(usi="9", call_sign="WQAA001", entity_name="ACME TRUCKING LLC",
               street_address="9 DOCK ST", city="DAYTON", state="OH", zip_code="45402",
               applicant_type_code="L"),
        ],
        "HD.dat": [hd("9", "WQAA001", "A", "IG", "05/05/2015")],
    })  # fmt: skip
    f = fetch(FCCULSLandMobilePrivate, path, state="OH")
    out = [(r.table, dict(r.row)) for r in FCCULSLandMobilePrivate().normalize(f)]
    parties = {r["raw_name"]: r for t, r in out if t == "party"}
    assert parties["ACME TRUCKING LLC"]["org_form"] == "LLC"
    ann = parties["ANN LEE"]
    assert (ann["party_kind"], ann["last_name"], ann["first_name"]) == ("person", "LEE", "ANN")
    (biz,) = [r for t, r in out if t == "business"]
    assert (biz["sos_id"], biz["org_form"]) == ("FCC-ULS:9", "LLC")
    assert sorted(r["title"] for t, r in out if t == "business_role") == ["CONTACT", "LICENSEE"]


def test_pii_fields_cover_names_streets_and_ids(amat_zip: Path) -> None:
    body = json.loads(fetch(FCCULSAmateur, amat_zip, state="WV").content)
    for cls in FCC_ULS_ADAPTERS:
        assert cls.pii_fields == PII
    for key in (
        "entity_name",
        "first_name",
        "last_name",
        "street_address",
        "po_box",
        "trustee_name",
        "call_sign",
        "usi",
        "frn",
    ):
        assert key in PII
    scrubbed = json.dumps(scrub(body, PII))
    for real in ("DOE", "JANE", "12 OAK ST", "MOUNTAIN RADIO", "SMITH", "KA1AAA", "0001112223"):
        assert real not in scrubbed
    assert "CHARLESTON" in scrubbed  # cities and states stay


def test_split_person() -> None:
    assert split_person("NELSON, DOUGLAS J") == {
        "last_name": "NELSON",
        "first_name": "DOUGLAS",
        "middle": "J",
        "suffix": None,
    }
    assert split_person("NO COMMA")["last_name"] is None


def test_download_streams_to_cache_and_reuses_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bulk_zip, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(bulk_zip, "MANUAL_DIR", tmp_path / "manual")
    src = write_zip(tmp_path / "src.zip", {"EN.dat": AMAT_EN, "HD.dat": AMAT_HD})
    calls: list[str] = []

    def stream(url: str, headers: Mapping[str, str], timeout: float, dest: Path
               ) -> tuple[int, str]:  # fmt: skip
        calls.append(url)
        dest.write_bytes(src.read_bytes())
        return 200, "application/zip"

    client = DownloadClient(transport=lambda u, h, t: (404, b"", ""), stream=stream,
                            sleep=lambda s: None)  # fmt: skip
    url = "https://data.fcc.gov/download/pub/uls/complete/l_amat.zip"
    path, got, status = locate_zip(client, "us.fcc.uls_amateur", url, {}, 3600.0)
    assert (path, got, status) == (
        tmp_path / "work" / "us.fcc.uls_amateur" / "l_amat.zip",
        url,
        200,
    )
    locate_zip(client, "us.fcc.uls_amateur", url, {}, 3600.0)
    assert calls == [url]  # the fresh cached zip is reused
    locate_zip(client, "us.fcc.uls_amateur", url, {}, 0.0)
    assert len(calls) == 2  # an expired one is fetched again

    def blocked(url: str, headers: Mapping[str, str], timeout: float, dest: Path
                ) -> tuple[int, str]:  # fmt: skip
        dest.write_bytes(b"<HTML>Access Denied</HTML>")
        return 403, "text/html"

    client.stream = blocked
    with pytest.raises(RuntimeError, match="Save it by hand"):
        locate_zip(client, "us.fcc.uls_gmrs", url.replace("amat", "gmrs"), {}, 3600.0)
    manual = tmp_path / "manual" / "us.fcc.uls_gmrs" / "l_gmrs.zip"
    manual.parent.mkdir(parents=True)
    manual.write_bytes(src.read_bytes())
    assert locate_zip(client, "us.fcc.uls_gmrs", url.replace("amat", "gmrs"), {}, 3600.0)[
        0] == manual  # fmt: skip


def test_source_rows_are_public_bulk() -> None:
    for cls in FCC_ULS_ADAPTERS:
        row = cls().source_row()
        assert row["source_id"].startswith("us.fcc.uls_") and row["access_method"] == "bulk"
        assert row["cost_model"] == "free" and "robots.txt" in row["terms_summary"]
        assert row["base_url"].endswith(cls.file)
