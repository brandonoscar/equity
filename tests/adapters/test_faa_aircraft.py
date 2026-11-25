"""FAA Releasable Aircraft Database (equity.adapters.federal.faa_aircraft) on inline samples
of MASTER.txt, ACFTREF.txt and ENGINE.txt."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.faa_aircraft import (
    MASTER,
    PII,
    FAAAircraftRegistry,
    registration_state,
    split_last_first,
    table,
)
from equity.adapters.record import scrub

HEADER = ",".join(MASTER) + ","  # the real header ends in a comma too


def master_row(**v: str) -> str:
    # Values are space-padded to fixed widths in the real file.
    return ",".join(f"{v.get(col, ''):<6}" for col in MASTER) + ","


ROWS = [
    master_row(**{"N-NUMBER": "12345", "SERIAL NUMBER": "17280001", "MFR MDL CODE": "2072738",
                  "ENG MFR MDL": "17003", "YEAR MFR": "1998", "TYPE REGISTRANT": "1",
                  "NAME": "DOE JOHN Q JR", "STREET": "12 OAK ST", "STREET2": "APT 4",
                  "CITY": "CHARLESTON", "STATE": "WV", "ZIP CODE": "253011234",
                  "COUNTY": "039", "COUNTRY": "US", "LAST ACTION DATE": "20240131",
                  "CERT ISSUE DATE": "20190405", "STATUS CODE": "V",
                  "EXPIRATION DATE": "20290430", "MODE S CODE HEX": "A0B1C2"}),
    master_row(**{"N-NUMBER": "777AB", "MFR MDL CODE": "2072738", "TYPE REGISTRANT": "7",
                  "NAME": "SKY HOLDINGS LLC", "STREET": "9 RUNWAY RD", "CITY": "MORGANTOWN",
                  "STATE": "WV", "ZIP CODE": "26505", "COUNTY": "061", "COUNTRY": "US"}),
    master_row(**{"N-NUMBER": "55", "TYPE REGISTRANT": "4", "NAME": "ROE ANN",
                  "OTHER NAMES(1)": "ROE BOB", "OTHER NAMES(2)": "ROE FARMS INC",
                  "STREET": "1 FARM LN", "CITY": "WHEELING", "STATE": "WV",
                  "ZIP CODE": "26003", "COUNTRY": "US"}),
    master_row(**{"N-NUMBER": "66", "TYPE REGISTRANT": "1", "NAME": "", "STATE": "WV",
                  "COUNTRY": "US"}),  # owner data withheld: skipped
    master_row(**{"N-NUMBER": "88", "TYPE REGISTRANT": "3", "NAME": "ACME AIR CORP",
                  "STREET": "1 MAIN", "CITY": "AKRON", "STATE": "OH", "ZIP CODE": "44301",
                  "COUNTRY": "US"}),
    master_row(**{"N-NUMBER": "99", "TYPE REGISTRANT": "8", "NAME": "AERO GMBH",
                  "STREET": "HAUPTSTR 1", "CITY": "BERLIN", "STATE": "", "COUNTRY": "DE"}),
]  # fmt: skip
ACFTREF = ("CODE,MFR,MODEL,TYPE-ACFT,TYPE-ENG,AC-CAT,BUILD-CERT-IND,NO-ENG,NO-SEATS,"
           "AC-WEIGHT,SPEED,TC-DATA-SHEET,TC-DATA-HOLDER,\r\n"
           "2072738,CESSNA                        ,172R      ,4,1,1,0,01,004,CLASS 1,0000,,,\r\n"
           "9999999,UNUSED,X,4,1,1,0,01,002,CLASS 1,0000,,,\r\n")  # fmt: skip
ENGINE = ("CODE,MFR,MODEL,TYPE,HORSEPOWER,THRUST,\r\n"
          "17003,LYCOMING  ,IO-360-L2A ,1,00160,000000,\r\n")  # fmt: skip


@pytest.fixture
def faa_zip(tmp_path: Path) -> Path:
    path = tmp_path / "ReleasableAircraft.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MASTER.txt", ("﻿" + HEADER + "\r\n" + "\r\n".join(ROWS) + "\r\n"))
        zf.writestr("ACFTREF.txt", ACFTREF)
        zf.writestr("ENGINE.txt", ENGINE)
    return path


def fetch(path: Path, **params: str) -> Fetched:
    return FAAAircraftRegistry().fetch(FetchRequest({"path": str(path), **params}))


def test_table_reads_by_header_through_bom_and_padding(faa_zip: Path) -> None:
    from equity.adapters.federal.bulk_zip import member_lines

    first = next(table(member_lines(faa_zip, "MASTER.txt")))
    assert first["N-NUMBER"] == "12345" and first["NAME"] == "DOE JOHN Q JR"
    assert "" not in first  # the trailing comma's blank header is dropped


def test_partitions_and_state_filter(faa_zip: Path) -> None:
    parts = [p["state"] for p in FAAAircraftRegistry().partitions()]
    assert parts[-1] == "other" and "WV" in parts and len(parts) == 61
    assert registration_state({"state": "WV", "country": "US"}) == "WV"
    assert registration_state({"state": "", "country": "DE"}) == "other"
    body = json.loads(fetch(faa_zip, state="WV").content)
    assert [r["n_number"] for r in body["rows"]] == ["12345", "777AB", "55", "66"]
    assert [r["n_number"] for r in json.loads(fetch(faa_zip, state="other").content)["rows"]] \
        == ["99"]  # fmt: skip
    limited = json.loads(fetch(faa_zip, state="WV", limit="2").content)["rows"]
    assert [r["n_number"] for r in limited] == ["12345", "777AB"]
    with pytest.raises(ValueError, match="unknown state"):
        fetch(faa_zip, state="XX")


def test_reference_files_join_by_code(faa_zip: Path) -> None:
    row = json.loads(fetch(faa_zip, state="WV", limit="1").content)["rows"][0]
    assert (row["aircraft_mfr"], row["aircraft_model"], row["no_seats"]) == (
        "CESSNA",
        "172R",
        "004",
    )
    assert (row["engine_mfr"], row["engine_model"]) == ("LYCOMING", "IO-360-L2A")
    assert (row["status_code"], row["cert_issue_date"], row["street2_address"]) == (
        "V", "20190405", "APT 4")  # fmt: skip


def test_normalize(faa_zip: Path) -> None:
    f = fetch(faa_zip, state="WV")
    out = [(r.table, dict(r.row)) for r in FAAAircraftRegistry().normalize(f)]
    assert out == [(r.table, dict(r.row)) for r in FAAAircraftRegistry().normalize(f)]
    keys = sorted(r["record_key"] for t, r in out if t == "source_record")
    assert keys == ["N12345", "N55", "N777AB"]  # N66 (withheld) is skipped
    parties = {r["raw_name"]: r for t, r in out if t == "party"}
    doe = parties["DOE JOHN Q JR"]
    assert (doe["party_kind"], doe["last_name"], doe["first_name"], doe["middle"],
            doe["suffix"]) == ("person", "DOE", "JOHN", "Q", "JR")  # fmt: skip
    assert doe["jurisdiction"] == "54039"  # Kanawha County, WV
    addrs = {a["address_id"]: a for t, a in out if t == "address"}
    assert (addrs[doe["address_id"]]["line1"], addrs[doe["address_id"]]["zip5"]) == (
        "12 OAK ST APT 4", "25301")  # fmt: skip
    sky = parties["SKY HOLDINGS LLC"]
    assert (sky["party_kind"], sky["org_form"]) == ("org", "LLC")
    assert (parties["ROE ANN"]["party_kind"], parties["ROE BOB"]["party_kind"]) == (
        "person",
        "person",
    )
    assert parties["ROE BOB"]["address_id"] is None  # co-owners share no address of their own
    assert parties["ROE FARMS INC"]["party_kind"] == "org"
    assert {t for t, _ in out} == {"source_record", "address", "party"}


def test_foreign_registrant_has_no_address(faa_zip: Path) -> None:
    out = [(r.table, dict(r.row)) for r in FAAAircraftRegistry().normalize(
        fetch(faa_zip, state="other"))]  # fmt: skip
    (party,) = [r for t, r in out if t == "party"]
    assert (party["party_kind"], party["address_id"], party["jurisdiction"]) == ("org", None, "US")
    assert not [r for t, r in out if t == "address"]


def test_pii_fields_cover_names_streets_and_aircraft_ids(faa_zip: Path) -> None:
    body = json.loads(fetch(faa_zip, state="WV").content)
    for key in (
        "name",
        "other_name_1",
        "street_address",
        "street2_address",
        "n_number",
        "serial_number",
        "mode_s_code_hex",
        "unique_id",
    ):
        assert key in PII
    assert FAAAircraftRegistry.pii_fields == PII
    scrubbed = scrub(body, PII)
    text = json.dumps(scrubbed)
    for real in ("DOE JOHN", "12 OAK ST", "ROE BOB", "17280001", "A0B1C2", "12345"):
        assert real not in text
    assert scrubbed["rows"][0]["street_address"].endswith(" TEST ST")
    assert scrubbed["rows"][0]["name"].startswith("TESTOWNER")


def test_split_last_first() -> None:
    assert split_last_first("SMITH JOHN") == {
        "last_name": "SMITH",
        "first_name": "JOHN",
        "middle": None,
        "suffix": None,
    }
    assert split_last_first("CHER")["last_name"] is None


def test_source_row() -> None:
    row = FAAAircraftRegistry().source_row()
    assert (row["kind"], row["access_method"], row["cost_model"]) == ("aircraft", "bulk", "free")
    assert "44114" in row["terms_summary"]
