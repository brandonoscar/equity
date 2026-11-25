"""Indiana sales disclosure forms: both zip layouts become one compact row per form, served
one county per partition, and normalize to DEED / LAND_CONTRACT instruments."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from typing import Any

from equity.adapters.base import FetchRequest
from equity.adapters.http import PoliteClient
from equity.adapters.indiana_sdf import (
    _YEAR,
    IndianaSalesDisclosures,
    county_name,
    parse_legacy,
    parse_relational,
    zip_url,
)


def _tsv(rows: list[list[str]]) -> str:
    return "\r\n".join("\t".join(f'"{c}"' for c in r) for r in rows) + "\r\n"


def _relational() -> bytes:
    disc = [["SDF_ID", "County_ID", "C7_Conveyance_Date", "E1_Sales_Price", "B5_Land_Contract",
             "C1_Sheriff_Sale", "E8_Mortgage_Loan"],
            ["C01-2026-1", "01", "2026-01-06", "15000000", "N", "Y", "Y"],
            ["C49-2026-2", "49", "1900-01-01", "0", "Y", "N", "N"],
            ["C99-2026-3", "99", "2026-02-01", "100", "N", "N", "N"]]  # fmt: skip
    parcel = [["SDF_ID", "Parcel_Instance_No", "A1_Parcel_Number", "P2_1_Parcel_Num_Verified",
               "A5_Street1", "A5_City", "A5_ZipCode"],
              ["C01-2026-1", "001", "010618100005000015", "", "1 MAIN ST", "DECATUR", "46733"],
              ["C01-2026-1", "002", "x", "010618100005000016", "", "", ""],
              ["C49-2026-2", "001", "490101", "", "", "", ""],
              ["NONE", "001", "1", "", "", "", ""]]  # fmt: skip
    contac = [["SDF_ID", "Contact_Instance_No", "Contact_Type", "Name", "Company", "Street1",
               "Street2", "City", "State", "zipCode", "Phone", "EmailAddress"],
              ["C01-2026-1", "001", "S", "ANN LEE", "", "2 ELM", "APT 3", "BERNE", "IN",
               "46711", "555", "a@b.c"],
              ["C01-2026-1", "001", "B", "BO RAY", "ACME LLC", "3 OAK", "", "FORT WAYNE", "IN",
               "46802", "", ""],
              ["C01-2026-1", "001", "P", "TITLE CO", "", "", "", "", "", "", "", ""],
              ["C49-2026-2", "001", "B", "CY DOE", "", "", "", "", "", "", "", ""]]  # fmt: skip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("SALEDISC.txt", _tsv(disc).encode("utf-16"))
        z.writestr("SALEPARCEL.txt", _tsv(parcel).encode("utf-8"))
        z.writestr("SALECONTAC.txt", _tsv(contac).encode("utf-16"))
        z.writestr("SDF_File_Parsing_MetaData.xlsx", b"not read")
    return buf.getvalue()


def _legacy() -> bytes:
    head = ["Parcel1", "Parcel2", "Parcel3", "PropStreet", "Conveyance_Date", "Quitclaim",
            "B8_Land_Contract_Assessor", "Seller1", "Seller1Street", "Seller1City",
            "Seller1State", "Seller1ZIP", "Seller2Name", "Buyer1", "Buyer1Street",
            "Buyer1City", "Buyer1State", "Buyer1ZIP", "Buyer2", "SDF_ID", "County_ID",
            "SDF_Date", "C6_Sales_Price"]  # fmt: skip
    rows = [["01-02-36-301-008.000-014", "", "", "1 A ST", "04/17/2008", "Y", "N", "DEE INC",
             "9 X", "EDEN PRAIRIE", "MN", "55344", "", "EVE FOX", "1 A ST", "DECATUR", "IN",
             "46733", "GUS FOX", "01-2008-1", "1", "2008-08-11 14:32:28.8", "152000"],
            ["", "", "", "", "", "N", "Y", "", "", "", "", "", "", "HAL", "", "", "", "", "",
             "45-2008-2", "45", "2008-09-01 10:00:00", "x"]]  # fmt: skip
    text = "\n".join("|".join(r) for r in [head, *rows]) + "\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("2008.txt", text.encode("utf-8"))
    return buf.getvalue()


def test_county_numbers_and_urls() -> None:
    assert county_name("01") == "Adams County" and county_name("71") == "St. Joseph County"
    assert county_name("93") is None and county_name("x") is None
    assert zip_url(2021).endswith("/SDF_2021.zip") and zip_url(2020).endswith(
        "/SDF_View_CSV_2020.zip")  # fmt: skip


def test_relational_zip_is_joined_per_form() -> None:
    out = parse_relational(_relational())
    assert sorted(out) == ["01", "49"]  # county 99 is not an Indiana county
    (adams,) = out["01"]
    assert adams["price"] == "150000.00" and adams["conveyed_on"] == "2026-01-06"
    assert adams["kind"] == "SALES DISCLOSURE (sheriff sale, buyer loan)"
    assert (adams["pin1"], adams["pin2"]) == ("010618100005000015", "010618100005000016")
    assert adams["seller1"] == "ANN LEE" and adams["seller1_street"] == "2 ELM APT 3"
    assert adams["buyer1"] == "ACME LLC"  # the company, not the signer
    assert "buyer2" not in adams and not any("a@b" in str(v) for v in adams.values())
    (marion,) = out["49"]
    assert marion["kind"] == "LAND CONTRACT" and marion["conveyed_on"] is None
    assert marion["price"] is None and marion["county_name"] == "Marion County"


def test_legacy_zip_rows() -> None:
    out = parse_legacy(_legacy())
    (adams,) = out["01"]
    assert (adams["conveyed_on"], adams["price"], adams["kind"]) == (
        "2008-04-17", "152000.00", "SALES DISCLOSURE (quitclaim)")  # fmt: skip
    assert adams["pin1"] == "01-02-36-301-008.000-014" and "pin2" not in adams
    assert (adams["seller1"], adams["buyer1"], adams["buyer2"]) == ("DEE INC", "EVE FOX",
                                                                    "GUS FOX")  # fmt: skip
    (lake,) = out["45"]
    assert lake["conveyed_on"] == "2008-09-01" and lake["kind"] == "LAND CONTRACT"


def _client(routes: Mapping[str, bytes]) -> PoliteClient:
    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("robots.txt"):
            return 404, b"", ""
        for part, body in routes.items():
            if url.endswith(part):
                return 200, body, ""
        return 404, b"", ""

    return PoliteClient(min_interval_s=0, transport=transport, sleep=lambda s: None)


def test_fetch_one_county_and_normalize() -> None:
    _YEAR.clear()
    from datetime import UTC, datetime

    listed = zip_url(datetime.now(UTC).year).rsplit("/", 1)[1]
    page = f"<a href='{listed}'>".encode()
    a = IndianaSalesDisclosures(_client({"SDF_2026.zip": _relational(), "topic/sdf.asp": page}))
    assert {"year": "2008", "county": "92"} in list(a.partitions())
    f = a.fetch(FetchRequest({"year": "2026", "county": "1"}))
    assert [r["sdf_id"] for r in json.loads(f.content)["rows"]] == ["C01-2026-1"]
    out: list[tuple[str, dict[str, Any]]] = [(r.table, dict(r.row)) for r in a.normalize(f)]
    (inst,) = [r for t, r in out if t == "instrument"]
    assert (inst["doc_type"], str(inst["consideration"]), inst["jurisdiction"]) == (
        "DEED", "150000.00", "18001")  # fmt: skip
    assert sorted(r["parcel_uid"] for t, r in out if t == "instrument_parcel") == [
        "18001-010618100005000015", "18001-010618100005000016"]  # fmt: skip
    roles = sorted(r["role"] for t, r in out if t == "instrument_party")
    assert roles == ["grantee", "grantor"]
    assert a.fetch(FetchRequest({"year": "2026", "county": "02", "limit": "5"})).content
    assert a.health().ok
    assert a.source_row()["terms_summary"].startswith("RESTRICTED[no_commercial_name_address")
    _YEAR.clear()
    assert not IndianaSalesDisclosures(_client({})).health().ok
