"""Hamilton County TN Trustee delinquent file: real property bills, GISLINK parcel keys."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import Response
from equity.adapters.tn.hamilton_delinquent import (
    URL,
    HamiltonTNDelinquentTaxes,
    delinquent_bills,
    gislink,
    mailing,
)

AT = datetime(2025, 12, 31, tzinfo=UTC)


def _fixed(fields: dict[int, str], width: int = 810) -> str:
    line = [" "] * width
    for a, v in fields.items():
        line[a - 1 : a - 1 + len(v)] = list(v)
    return "".join(line)


def _bill(map_: str, group: str, parcel: str, owner: str, year: str, county: str,
          mun: str = "000000000", city_line: str = "CHATT, TN 37416,") -> str:  # fmt: skip
    return _fixed({9: map_, 14: group, 17: parcel, 27: owner, 62: year, 66: "001668",
                   115: "2430   CAMPBELL   ST", 150: city_line, 572: "Y ", 593: county,
                   602: mun, 611: "000000000"})  # fmt: skip


def test_gislink_and_mailing_lines() -> None:
    assert gislink("137A", "T", "016") == "033137AT01600"
    assert gislink("128P", "L", "013.01") == "033128PL01301"
    assert gislink("085", "", "007.33") == "03308500733"
    assert gislink("PER", "", "10046449") is None
    assert gislink("146P", "C", "002   C037") is None  # a condominium unit
    assert mailing({"mail1": "2430   CAMPBELL   ST", "mail2": "CHATT TN 37416,"}) == (
        "2430 CAMPBELL ST", "CHATT", "TN", "37416")  # fmt: skip
    assert mailing({"mail1": "PO BOX 8789", "mail2": "WILMINGTON, DE 19899,"})[1:] == (
        "WILMINGTON", "DE", "19899")  # fmt: skip


class _Client:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get(self, url: str, params: object = None) -> Response:
        assert url == URL
        return Response(url, 200, self.body, "application/zip", AT)


def test_real_property_bills_become_liens_on_the_parcel() -> None:
    lines = [
        _bill("137A", "T", "016", "LEE ANN", "2023", "000010050", "000000100"),
        _bill("PER", "", "10046449", "BIZ INC", "2024", "000005000"),  # personal property
        _bill("128P", "L", "013.01", "RAY BO", "2024", "000000000"),
    ]  # nothing owed
    assert [(b["owner1"], b["cents"]) for b in delinquent_bills(lines)] == [("LEE ANN", 10150)]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CTRUDELQ.TXT", "\r\n".join(lines) + "\r\n")
    a = HamiltonTNDelinquentTaxes(_Client(buf.getvalue()))  # type: ignore[arg-type]
    fetched = a.fetch(FetchRequest({}))
    out = [(t.table, dict(t.row)) for t in a.normalize(fetched)]
    (inst,) = [x for t, x in out if t == "instrument"]
    assert (inst["recorded_on"], str(inst["principal_amount"]), inst["doc_type"]) == (
        date(2023, 1, 1), "101.5", "TAX_LIEN_STATE")  # fmt: skip
    assert inst["doc_type_raw"].endswith("bill year 2023 (back tax)")
    assert [x["parcel_uid"] for t, x in out if t == "instrument_parcel"] == [
        "47065-033137AT01600"]  # fmt: skip
    (addr,) = [x for t, x in out if t == "address"]
    assert (addr["city"], addr["zip5"]) == ("CHATT", "37416")
    assert {x["raw_name"] for t, x in out if t == "party"} == {"LEE ANN", "Hamilton County Trustee"}
    refetched = Fetched(a.source_id, URL, AT, 200, json.dumps(json.loads(fetched.content)).encode(),
                        "application/json")  # fmt: skip
    assert len(list(a.normalize(refetched))) == len(out)


def test_personal_property_bills_are_the_per_map_records_with_no_parcel() -> None:
    from equity.adapters.tn.hamilton_delinquent import HamiltonTNPersonalPropertyTaxes

    lines = [
        _bill("137A", "T", "016", "LEE ANN", "2023", "000010050"),
        _bill("PER", "", "10046449", "BIZ INC", "2024", "000005000", "000000025"),
    ]
    assert [b["owner1"] for b in delinquent_bills(lines, personal=True)] == ["BIZ INC"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CTRUDELQ.TXT", "\r\n".join(lines) + "\r\n")
    a = HamiltonTNPersonalPropertyTaxes(_Client(buf.getvalue()))  # type: ignore[arg-type]
    out = [(t.table, dict(t.row)) for t in a.normalize(a.fetch(FetchRequest({})))]
    (inst,) = [x for t, x in out if t == "instrument"]
    assert (str(inst["principal_amount"]), inst["doc_type_raw"]) == (
        "50.25", "Hamilton County delinquent business personal property tax, bill year 2024 "
        "(back tax)")  # fmt: skip
    assert not [x for t, x in out if t == "instrument_parcel"]
    assert {x["raw_name"] for t, x in out if t == "party"} == {"BIZ INC", "Hamilton County Trustee"}
