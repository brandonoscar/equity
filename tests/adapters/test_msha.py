"""MSHA mines and assessed penalties (equity.adapters.federal.msha)."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.bulk_files import BulkClient
from equity.adapters.federal.msha import (
    DATASETS,
    MSHAAssessedPenalties,
    MSHAMines,
    mdy,
    mine_place,
    money,
)
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
ROOT = Path(__file__).parents[1] / "fixtures" / "adapters"


def _pipe(*rows: tuple[str, ...]) -> str:
    return "\r\n".join("|".join(f'"{c}"' if c else "" for c in r) for r in rows) + "\r\n"


def _zip(name: str, body: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, body.encode("latin-1"))
    return buf.getvalue()


MINES = _zip("Mines.txt", _pipe(
    ("MINE_ID", "CURRENT_MINE_NAME", "CURRENT_MINE_STATUS", "CURRENT_STATUS_DT",
     "CURRENT_OPERATOR_NAME", "CURRENT_CONTROLLER_NAME", "STATE", "FIPS_CNTY_CD"),
    ("0100003", "O'Neal Quarry", "Active", "01/22/1979", "Martin Marietta Materials, Inc.",
     "Martin Marietta Materials Inc", "AL", "117"),
    ("4300001", "Barre Granite Pit", "Abandoned", "05/01/1990", "", "", "VT", "023"),
    ("4300002", "", "Active", "", "", "", "VT", "023"),
))  # fmt: skip
AOR = _zip("AddressOfRecord.txt", _pipe(
    ("MINE_ID", "MINE_NAME", "BUSINESS_NAME", "STREET", "PO_BOX", "CITY", "STATE_ABBR", "ZIP_CD",
     "COUNTRY"),
    ("0100003", "O'Neal Quarry", "Martin Marietta Materials, Inc.", "2885 Highway 3", "",
     "Calera", "AL", "35040", "USA"),
    ("4300001", "Barre Granite Pit", "Rock Co LLC", "", "PO Box 7", "Barre", "VT", "05641",
     "USA"),
))  # fmt: skip
HIST = _zip("ControllerOperatorHistory.txt", _pipe(
    ("CONTROLLER_ID", "CONTROLLER_NAME", "CONTROLLER_START_DT", "CONTROLLER_END_DT",
     "CONTROLLER_TYPE", "MINE_ID", "OPERATOR_ID", "OPERATOR_NAME", "OPERATOR_START_DT",
     "OPERATOR_END_DT"),
    ("C1", "John  Smith", "10/30/1985", "12/31/1989", "PERSON", "4300001", "L1", "Rock Co LLC",
     "10/30/1985", ""),
    ("C1", "John  Smith", "01/01/1980", "10/29/1985", "PERSON", "4300001", "L2", "Old Rock Inc",
     "01/01/1980", "10/29/1985"),
))  # fmt: skip
VIOL = _zip("AssessedViolations.txt", _pipe(
    ("EVENT_NBR", "VIOLATION_NO", "MINE_ID", "VIOLATOR_ID", "VIOLATOR_NAME", "VIOLATOR_TYPE_CD",
     "ASSESS_CASE_NO", "ISSUE_DT", "FINAL_ORDER_DT", "DELINQUENT_DT", "CURRENT_ASSESSMENT_AMT",
     "PAID_PROPOSED_PENALTY_AMT", "MINEACT_INTEREST_AMT"),
    ("1", "V1", "4300001", "L1", "Rock Co LLC", "Operator", "A1", "01/05/2024", "02/20/2024",
     "02/20/2024", "159.00", "0.00", "2.20"),
    ("1", "V2", "4300001", "L1", "Rock Co LLC", "Operator", "A1", "01/06/2024", "02/20/2024",
     "02/20/2024", "100.00", "40.00", "0.00"),
    ("2", "V3", "0100003", "L9", "Paid Up Inc", "Operator", "A2", "01/05/2024", "02/20/2024",
     "02/20/2024", "55.00", "55.00", "1.94"),
    ("3", "V4", "0100003", "L9", "Paid Up Inc", "Operator", "A3", "11/01/2026", "12/20/2026",
     "12/20/2026", "55.00", "0.00", "0.00"),
))  # fmt: skip


class _Server:
    def __init__(self) -> None:
        self.files = {
            "Mines.zip": MINES,
            "AddressofRecord.zip": AOR,
            "ControllerOperatorHistory.zip": HIST,
            "AssessedViolations.zip": VIOL,
        }
        self.gets: list[str] = []

    def get(self, url: str, headers: Mapping[str, str], timeout: float
            ) -> tuple[int, bytes, str]:  # fmt: skip
        if url.endswith("/robots.txt"):
            return 404, b"", "text/html"
        self.gets.append(url)
        data = self.files[url.rsplit("/", 1)[-1]]
        if rng := headers.get("Range"):
            r = rng.removeprefix("bytes=")
            if r.startswith("-"):
                return 206, data[-int(r[1:]) :], "application/zip"
            a, b = (int(x) for x in r.split("-"))
            return 206, data[a : b + 1], "application/zip"
        return 200, data, "application/zip"

    def stream(self, url: str, headers: Mapping[str, str], timeout: float, dest: Path
               ) -> tuple[int, str]:  # fmt: skip
        dest.write_bytes(self.files[url.rsplit("/", 1)[-1]])
        return 200, "application/zip"


def _client(server: _Server) -> BulkClient:
    return BulkClient(transport=server.get, stream_transport=server.stream,
                      sleep=lambda s: None, now=lambda: AT)  # fmt: skip


def test_mines_become_businesses_with_operators_and_controllers() -> None:
    server = _Server()
    adapter = MSHAMines(_client(server))
    assert list(adapter.partitions()) == [{"state": "AL"}, {"state": "VT"}]
    fetched = adapter.fetch(FetchRequest({"state": "VT"}))
    assert sum(u.endswith("/Mines.zip") for u in server.gets) == 1  # fetched once per instance
    out = [(r.table, dict(r.row)) for r in adapter.normalize(fetched)]
    (biz,) = [r for t, r in out if t == "business"]
    assert (biz["sos_id"], biz["name"], biz["status"], biz["status_date"], biz["valid_from"],
            biz["jurisdiction"]) == ("MSHA:4300001", "Barre Granite Pit", "Abandoned",
                                     date(1990, 5, 1), date(1980, 1, 1), "50023")  # fmt: skip
    addrs = {r["address_id"]: r for t, r in out if t == "address"}
    assert addrs[biz["principal_address_id"]]["line1"] == "PO BOX 7"
    parties = {r["party_id"]: r for t, r in out if t == "party"}
    roles = sorted((r["title"], parties[r["party_id"]]["raw_name"], r["valid_to"])
                   for t, r in out if t == "business_role")  # fmt: skip
    assert roles == [
        ("CONTROLLER", "John Smith", date(1989, 12, 31)),
        ("OPERATOR", "Old Rock Inc", date(1985, 10, 29)),
        ("OPERATOR", "Rock Co LLC", None),
    ]
    rock = next(p for p in parties.values() if p["raw_name"] == "Rock Co LLC")
    assert rock["address_id"] == biz["principal_address_id"]  # the address of record
    smith = next(p for p in parties.values() if p["raw_name"] == "John Smith")
    assert smith["party_kind"] == "person"
    with pytest.raises(ValueError, match="bad state"):
        adapter.fetch(FetchRequest({"state": "V1"}))


def test_unpaid_penalties_become_debts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MSHAAssessedPenalties, "cache_dir", tmp_path)
    server = _Server()
    adapter = MSHAAssessedPenalties(_client(server))
    for params in ({"file": "all"}, {"file": "all", "limit": "5"}):
        body = json.loads(adapter.fetch(FetchRequest(params)).content)
        assert not list(tmp_path.rglob("*.zip"))  # the downloaded zip is deleted after reading
        # A2 is paid; A3 is not delinquent yet (12/20/2026).
        assert [c["assess_case_no"] for c in body["cases"]] == ["A1"]
    fetched = Fetched(adapter.source_id, DATASETS, AT, 200, canonical_json(body),
                      "application/json")  # fmt: skip
    out = [(r.table, dict(r.row)) for r in adapter.normalize(fetched)]
    (inst,) = [r for t, r in out if t == "instrument"]
    assert (
        inst["instrument_number"],
        inst["principal_amount"],
        inst["recorded_on"],
        inst["executed_on"],
        inst["doc_type"],
        inst["jurisdiction"],
    ) == ("A1", Decimal("219.00"), date(2024, 2, 20), date(2024, 1, 5), "OTHER", "50023")
    parties = {r["party_id"]: r for t, r in out if t == "party"}
    roles = sorted((r["role"], parties[r["party_id"]]["raw_name"])
                   for t, r in out if t == "instrument_party")  # fmt: skip
    assert roles == [("creditor", "MINE SAFETY AND HEALTH ADMINISTRATION"),
                     ("debtor", "Rock Co LLC")]  # fmt: skip
    with pytest.raises(ValueError, match="bad file"):
        adapter.fetch(FetchRequest({"file": "x"}))


def test_helpers() -> None:
    assert mdy("02/20/2024") == date(2024, 2, 20) and mdy("2024-02-20") is None
    assert money("159.00") == Decimal("159.00") and money("x") == 0
    assert mine_place({"STATE": "VT", "FIPS_CNTY_CD": "023"}) == "50023"
    assert mine_place(None) == "US" and mine_place({"STATE": "VT"}) == "50"


@pytest.mark.parametrize("cls", [MSHAMines, MSHAAssessedPenalties])
def test_recorded_fixtures_are_pseudonymized(cls: Any) -> None:
    paths = sorted((ROOT / cls.source_id).glob("*.json"))
    assert paths

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in cls.pii_fields and isinstance(v, str):
                    assert v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for path in paths:
        walk(json.loads(path.read_text()))


@pytest.mark.parametrize("cls", [MSHAMines, MSHAAssessedPenalties])
def test_recorded_fixtures_pass_the_adapter_contract(cls: type, empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(cls, sorted((ROOT / cls.source_id).glob("*.json")), empty_db)  # type: ignore[attr-defined]
