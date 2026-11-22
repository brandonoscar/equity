"""Honolulu owners and values: lots key to the statewide TMK, CPR units link to their lot."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.hi.honolulu_owners import HonoluluOwners, mailing, parcel_uid


def _fetched(body: dict[str, object]) -> Fetched:
    return Fetched("hi.honolulu.owners", "x", datetime(2026, 11, 22, tzinfo=UTC), 200,
                   json.dumps(body).encode(), "application/json")  # fmt: skip


def test_parcel_uid_and_mailing() -> None:
    assert parcel_uid("21044041", "0000") == "15003-121044041"
    assert parcel_uid("21044041", "0289") == "15003-121044041-0289"
    a = mailing({"paddr1": "1 TEST ST", "paddr2": "APT 2", "paddr3": "HONOLULU HI 96813-3037"})
    assert a is not None and (a["line1"], a["city"], a["state"], a["zip5"]) == (
        "1 TEST ST APT 2", "HONOLULU", "HI", "96813")  # fmt: skip
    foreign = mailing({"paddr1": "1 TEST RD", "paddr3": "TOKYO JAPAN"})
    assert foreign is not None and foreign["zip5"] is None and foreign["city"] == "TOKYO JAPAN"


def test_owners_values_and_unit_links() -> None:
    body = {
        "owners": [
            {"tmk": "21044041", "suffix": "0000", "own1": "LOT OWNER LLC", "own2": None,
             "ownseq": 0, "owntble": "OWNDAT", "ownfld": "OWN1", "objectid": 1,
             "paddr1": "1 TEST ST", "paddr3": "HONOLULU HI 96813"},
            {"tmk": "21044041", "suffix": "0289", "own1": "ANN TEST", "own2": "BO TEST",
             "ownseq": 0, "owntble": "OWNDAT", "ownfld": "OWN1", "objectid": 3},
            {"tmk": "21044041", "suffix": "0289", "own1": "ANN TEST", "own2": None,
             "ownseq": 1, "owntble": "OWNMLT", "ownfld": "OWN1", "objectid": 2},  # repeat
            {"tmk": "BAD", "suffix": "0000", "own1": "SKIPPED"},
        ],
        "values": [
            {"tmk": "21044041", "suffix": "0000", "taxyr": 2026, "seq": 1, "landvalue": 1,
             "buildingvalue": 1, "tnettaxval": 2},
            {"tmk": "21044041", "suffix": "0000", "taxyr": 2026, "seq": 8, "landvalue": 300000,
             "buildingvalue": 200000, "tnettaxval": 450000},  # highest seq wins
        ],
    }  # fmt: skip
    rows = list(HonoluluOwners().normalize(_fetched(body)))
    by = lambda t: [r.row for r in rows if r.table == t]  # noqa: E731
    assert sorted(p["parcel_uid"] for p in by("parcel")) == ["15003-121044041",
                                                             "15003-121044041-0289"]  # fmt: skip
    links = by("parcel_link")
    assert [(x["from_parcel_uid"], x["to_parcel_uid"]) for x in links] == [
        ("15003-121044041-0289", "15003-121044041")
    ]
    unit_owners = [s for s in by("owner_snapshot") if s["parcel_uid"].endswith("-0289")]
    assert [s["owner_seq"] for s in unit_owners] == [1, 2]  # ANN once, then BO
    names = {p["party_id"]: p["raw_name"] for p in by("party")}
    assert [names[s["party_id"]] for s in unit_owners] == ["ANN TEST", "BO TEST"]
    (v,) = by("parcel_assessment")
    assert (v["appraised_total"], v["assessed_value"], v["valid_from"]) == (
        Decimal("500000"), Decimal("450000"), date(2026, 1, 1))  # fmt: skip


def test_prefix_must_be_two_digits() -> None:
    with pytest.raises(ValueError, match="bad TMK prefix"):
        HonoluluOwners().fetch(FetchRequest({"prefix": "1'"}))
