"""Cook County Assessor parcels: PIN ranges, the address/value join, owner and taxpayer."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import Response
from equity.adapters.il.cook_parcels import (
    CookCountyParcels,
    assessed,
    norm_pin,
    pin_bounds,
)
from equity.schema.ids import stable_id

AT = datetime(2026, 11, 23, 12, tzinfo=UTC)


class Client:
    """Socrata stand-in: answers by dataset id and records every query."""

    retries = 0
    backoff_s = 0.0

    def __init__(self, answers: dict[str, list[Any]], status: int = 200) -> None:
        self.answers = answers
        self.status = status
        self.calls: list[tuple[str, dict[str, str]]] = []

    def sleep(self, s: float) -> None:  # pragma: no cover - retries are 0
        pass

    def now(self) -> datetime:
        return AT

    def get(self, url: str, params: dict[str, str]) -> Response:
        self.calls.append((url, dict(params)))
        dataset = url.rsplit("/", 1)[-1].removesuffix(".json")
        body = self.answers[dataset].pop(0) if self.answers.get(dataset) else []
        return Response(url, self.status, json.dumps(body).encode(), "application/json", AT)


def _fetched(addresses: list[dict[str, Any]], values: list[dict[str, Any]]) -> Fetched:
    body = {"year": 2026, "where": "w", "addresses": addresses, "values": values}
    return Fetched("il.cook.parcels", "https://x.test/r?$where=w", AT, 200,
                   json.dumps(body).encode(), "application/json")  # fmt: skip


ROW = {
    "pin": "1011000020000",  # leading zero lost: padded to 14 digits
    "year": "2026",
    "prop_address_full": "231 W MAIN ST", "prop_address_city_name": "BARRINGTON",
    "prop_address_state": "IL", "prop_address_zipcode_1": "60010",
    "owner_address_name": "TESTOWNER AAA LLC", "owner_address_full": "5277 OAK BLVD",
    "owner_address_city_name": "HOFFMAN ESTS", "owner_address_state": "IL",
    "owner_address_zipcode_1": "60192-1234",
    "mail_address_name": "TESTOWNER BBB", "mail_address_full": "9 ELM ST",
    "mail_address_city_name": "CHICAGO", "mail_address_state": "IL",
    "mail_address_zipcode_1": "60601",
}  # fmt: skip


def test_rows_become_parcel_owner_taxpayer_and_assessment() -> None:
    values = [
        {"pin": "01011000020000", "year": "2026", "class": "5-17", "mailed_tot": "1000",
         "certified_tot": "1200.5"},
        {"pin": "01011000020000", "year": "2025", "class": "X", "board_tot": "1"},  # other year
    ]  # fmt: skip
    rows = list(CookCountyParcels().normalize(_fetched([ROW], values)))
    by = {}
    for r in rows:
        by.setdefault(r.table, []).append(r.row)
    (parcel,) = by["parcel"]
    assert parcel["parcel_uid"] == "17031-01011000020000"
    assert parcel["parid_raw"] == "01011000020000" and parcel["land_use_code"] == "5-17"
    assert parcel["jurisdiction"] == "17031"
    addrs = {a["address_id"]: a for a in by["address"]}
    assert addrs[parcel["situs_address_id"]]["norm_key"] == "231 W MAIN ST|BARRINGTON|IL|60010"
    snaps = sorted(by["owner_snapshot"], key=lambda s: s["owner_seq"])
    assert [(s["owner_seq"], s["owner_type"]) for s in snaps] == [(1, None), (2, "taxpayer")]
    assert {s["parcel_uid"] for s in snaps} == {"17031-01011000020000"}
    parties = {p["party_id"]: p for p in by["party"]}
    owner, payer = parties[snaps[0]["party_id"]], parties[snaps[1]["party_id"]]
    assert (owner["raw_name"], owner["party_kind"], owner["org_name_norm"]) == (
        "TESTOWNER AAA LLC", "org", "TESTOWNER AAA")  # fmt: skip
    assert addrs[owner["address_id"]]["norm_key"] == "5277 OAK BLVD|HOFFMAN ESTS|IL|60192"
    assert payer["raw_name"] == "TESTOWNER BBB"
    assert addrs[payer["address_id"]]["norm_key"] == "9 ELM ST|CHICAGO|IL|60601"
    assert payer["party_id"] == stable_id("il.cook.parcels", "01011000020000", "owner", "2",
                                          "TESTOWNER BBB")  # fmt: skip
    (assessment,) = by["parcel_assessment"]
    assert assessment["tax_year"] == 2026 and assessment["assessed_value"] == "1200.50"
    assert assessment["appraised_total"] is None
    assert str(assessment["valid_from"]) == "2026-01-01"


def test_taxpayer_is_skipped_when_it_is_the_owner_or_a_placeholder() -> None:
    same = {**ROW, "pin": "01011000030000", "mail_address_name": "TESTOWNER AAA L.L.C."}
    cut = {**ROW, "pin": "01011000040000", "owner_address_name": "CHICAGO TITLE LAND TRUST CO",
           "mail_address_name": "CHICAGO TITLE LAND TRU"}  # fmt: skip
    placeholder = {**ROW, "pin": "01011000050000", "mail_address_name": "Taxpayer of",
                   "owner_address_name": "CURRENT OWNER"}  # fmt: skip
    no_owner = {**ROW, "pin": "01011000060000", "owner_address_name": None,
                "mail_address_full": None, "mail_address_city_name": None,
                "mail_address_state": None, "mail_address_zipcode_1": None}  # fmt: skip
    bad = {**ROW, "pin": "12-AB"}  # not a PIN: skipped
    wrong_year = {**ROW, "pin": "01011000070000", "year": "2025"}
    rows = list(CookCountyParcels().normalize(
        _fetched([same, cut, placeholder, no_owner, no_owner, bad, wrong_year], [])))  # fmt: skip
    snaps = [(r.row["parcel_uid"][-6:], r.row["owner_seq"]) for r in rows
             if r.table == "owner_snapshot"]  # fmt: skip
    assert sorted(snaps) == [("030000", 1), ("040000", 1), ("060000", 2)]
    payer = next(r.row for r in rows if r.table == "party" and r.row["raw_name"] == "TESTOWNER BBB")
    assert payer["address_id"] is None
    assert not [r for r in rows if r.table == "parcel_assessment"]  # no values joined
    assert {r.row["parcel_uid"] for r in rows if r.table == "parcel"} == {
        f"17031-010110000{n}0000" for n in (3, 4, 5, 6)}  # fmt: skip


def test_helpers() -> None:
    assert norm_pin("17031000010000") == "17031000010000"
    assert norm_pin(" 1011000020000 ") == "01011000020000"
    assert norm_pin("17-03-100-001-0000") == "17031000010000"
    assert norm_pin("123456789012345") is None and norm_pin(None) is None
    assert assessed({"board_tot": "5", "mailed_tot": "1"}) == ("board", "5")
    assert assessed({"board_tot": None, "mailed_tot": "1"}) == ("mailed", "1")
    assert assessed({}) == (None, None)
    bounds = pin_bounds(1, 2)
    assert len(bounds) == 8 and bounds[0] == ("010", "011") and bounds[3] == ("013", "020")
    assert bounds[-1] == ("023", "030")


def test_partitions_use_the_latest_year_and_its_pin_span() -> None:
    c = Client({"3723-97qp": [[{"y": "2026"}], [{"lo": "01011000020000",
                                                 "hi": "33324000010000"}]]})  # fmt: skip
    parts = list(CookCountyParcels(c).partitions())  # type: ignore[arg-type]
    assert len(parts) == 33 * 4
    assert parts[0] == {"year": "2026", "pin_min": "010", "pin_max": "011"}
    assert parts[-1] == {"year": "2026", "pin_min": "333", "pin_max": "340"}
    assert c.calls[1][1]["$where"] == "year = 2026"


def test_partitions_fail_loudly() -> None:
    import pytest

    from equity.adapters.socrata import SocrataError

    with pytest.raises(SocrataError, match="HTTP 500"):
        list(CookCountyParcels(Client({}, status=500)).partitions())  # type: ignore[arg-type]
    with pytest.raises(SocrataError, match="empty answer"):
        list(CookCountyParcels(Client({})).partitions())  # type: ignore[arg-type]


def test_fetch_joins_one_pin_range_of_both_datasets() -> None:
    c = Client({"3723-97qp": [[ROW]], "uzyt-m557": [[{"pin": "x"}]]})
    f = CookCountyParcels(c).fetch(  # type: ignore[arg-type]
        FetchRequest({"year": "2026", "pin_min": "170", "pin_max": "171"})
    )
    where = "year = 2026 AND pin >= '170' AND pin < '171'"
    assert [p["$where"] for _, p in c.calls] == [where, where]
    assert c.calls[0][1]["$order"] == "pin,:id" and c.calls[0][1]["$limit"] == "50000"
    body = json.loads(f.content)
    assert body["addresses"] == [ROW] and body["values"] == [{"pin": "x"}]
    assert f.request.endswith(f"3723-97qp.json?$where={where}")
    # A fixture sample: one page, and only the values of the sampled PINs.
    c = Client({"3723-97qp": [[ROW]], "uzyt-m557": [[]]})
    CookCountyParcels(c).fetch(  # type: ignore[arg-type]
        FetchRequest({"year": "2026", "pin_min": "010", "pin_max": "011", "limit": "5"})
    )
    assert c.calls[0][1]["$limit"] == "5"
    assert c.calls[1][1]["$where"] == "year = 2026 AND pin in ('1011000020000')"
    c = Client({"3723-97qp": [[]], "uzyt-m557": [[]]})
    CookCountyParcels(c).fetch(  # type: ignore[arg-type]
        FetchRequest({"year": "2026", "pin_min": "010", "pin_max": "011", "limit": "5"})
    )
    assert c.calls[1][1]["$where"] == "year = 2026 AND pin in ('')"


def test_scrub_fixture_keeps_equal_names_equal() -> None:
    body = {"addresses": [{**ROW, "mail_address_name": ROW["owner_address_name"],
                           "prop_address_full": ROW["owner_address_full"]}]}  # fmt: skip
    (row,) = json.loads(CookCountyParcels.scrub_fixture(json.dumps(body).encode()))["addresses"]
    assert row["owner_address_name"] == row["mail_address_name"]
    name = row["owner_address_name"]
    assert name.startswith("TESTOWNER") and name.endswith(" LLC")
    assert row["prop_address_full"] == row["owner_address_full"]
    assert row["owner_address_full"].endswith(" TEST ST")
    assert row["prop_address_city_name"] == "BARRINGTON"


def test_health_and_source_row() -> None:
    a = CookCountyParcels(Client({"3723-97qp": [[{"pin": "1"}]], "uzyt-m557": [[{"pin": "1",
                                                                                 "class": "2"}]]}))  # type: ignore[arg-type]  # fmt: skip
    rep = a.health()
    assert rep.ok and rep.shape == ("class", "pin")
    assert not CookCountyParcels(Client({}, status=503)).health().ok  # type: ignore[arg-type]

    class Down(Client):
        def get(self, url: str, params: dict[str, str]) -> Response:
            raise OSError("down")

    assert "down" in CookCountyParcels(Down({})).health().detail  # type: ignore[arg-type]
    row = a.source_row()
    assert (row["kind"], row["jurisdiction"], row["access_method"]) == ("assessor", "17031", "api")
