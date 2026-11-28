"""Commercial lead list: auto matches on commercial, mixed or industrial parcels, by owner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from equity.matching import leads


def _write(path: Path, cols: dict[str, str], rows: list[tuple[Any, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE t ({', '.join(f'{c} {t}' for c, t in cols.items())})")
    if rows:
        con.executemany(f"INSERT INTO t VALUES ({', '.join('?' * len(cols))})", rows)
    con.execute(f"COPY t TO '{path.as_posix()}' (FORMAT parquet)")


def _setup(tmp_path: Path, with_addresses: bool = True) -> tuple[Path, Path]:
    lake, derived = tmp_path / "lake", tmp_path / "derived"
    src = lake / "ny.statewide.parcels"
    V = "VARCHAR"
    _write(src / "parcel" / "0.parquet",
           {"parcel_uid": V, "land_use_code": V, "land_use_desc": V, "situs_address_id": V}, [
               ("p1", "411", None, "a1"),        # NY class 4xx: commercial
               ("p2", "04", None, "a2"),         # NYC 04: mixed
               ("p3", "210", None, "a3"),        # residential: left out
               ("p4", None, "Warehouse", None),  # by description: industrial
               ("p5", "05", None, "a5"),         # commercial, but matched only for review
           ])  # fmt: skip
    _write(
        src / "party" / "0.parquet",
        {"party_id": V, "raw_name": V},
        [("o1", "ACME LLC"), ("o2", "BETA CORP"), ("o3", "CY DU")],
    )
    if with_addresses:
        _write(src / "address" / "0.parquet",
               {"address_id": V, "line1": V, "city": V, "state": V, "zip5": V},
               [("a1", "1 MAIN ST", "ALBANY", "NY", "12207"),
                ("a2", "2 MAIN ST", "ALBANY", "NY", "12207")])  # fmt: skip
    out = derived / "ny"
    _write(out / "matches.parquet",
           {"debtor_party_id": V, "owner_party_id": V, "parcel_uid": V, "decision": V}, [
               ("d1", "o1", "p1", "auto"), ("d2", "o1", "p2", "auto"),
               ("d3", "o2", "p4", "auto"), ("d4", "o3", "p3", "auto"),
               ("d5", "o3", "p5", "review"),
           ])  # fmt: skip
    _write(out / "debtor_summary.parquet",
           {"debtor_party_id": V, "debtor_name": V, "liens": "BIGINT", "open_amount": "DOUBLE"},
           [("d1", "ACME LLC", 2, 100.0), ("d2", "ACME L L C", 1, 50.5),
            ("d3", "BETA CORP", 1, None), ("d4", "CY DU", 1, 9.0)])  # fmt: skip
    return lake, derived


def test_leads_by_owner(tmp_path: Path) -> None:
    lake, derived = _setup(tmp_path)
    got = leads.build(lake, derived, "NY")
    assert got == {"state": "NY", "owners": 2, "owners_with_open_debt": 1, "parcels": 3,
                   "parcels_by_kind": {"commercial": 1, "industrial": 1, "mixed": 1},
                   "open_amount": 150.5}  # fmt: skip
    path = (derived / "ny" / "commercial_leads.parquet").as_posix()
    rows = duckdb.connect().execute(
        "SELECT owner_name, parcel_count, kinds, property_addresses, debts_linked, open_amount "
        f"FROM '{path}'").fetchall()  # fmt: skip
    assert rows == [
        ("ACME LLC", 2, ["commercial", "mixed"],
         ["1 MAIN ST, ALBANY, NY, 12207", "2 MAIN ST, ALBANY, NY, 12207"], 2, 150.5),
        ("BETA CORP", 1, ["industrial"], None, 1, None),
    ]  # fmt: skip
    csv = (derived / "ny" / "commercial_leads.csv").read_text().splitlines()
    assert csv[0].startswith("owner_name,parcel_count,kinds") and len(csv) == 3
    assert "commercial; mixed" in csv[1]


def test_no_address_table_and_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lake, derived = _setup(tmp_path, with_addresses=False)
    assert leads.build(lake, derived, "ny")["owners"] == 2
    with pytest.raises(KeyError, match="no match run"):
        leads.build(lake, derived, "ZZ")
    with pytest.raises(FileNotFoundError, match="not in"):
        leads.build(tmp_path / "empty", derived, "NY")
    assert leads.main(["--state", "NY", "--lake", str(lake), "--derived", str(derived)]) == 0
    assert json.loads(capsys.readouterr().out)["parcels"] == 3
    with pytest.raises(SystemExit):
        leads.main(["--state", "../x"])


def test_runs_as_a_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    import sys

    lake, derived = _setup(tmp_path)
    monkeypatch.setattr(sys, "argv", ["leads", "--state", "NY", "--lake", str(lake),
                                      "--derived", str(derived)])  # fmt: skip
    monkeypatch.delitem(sys.modules, "equity.matching.leads", raising=False)
    with pytest.raises(SystemExit) as done:
        runpy.run_module("equity.matching.leads", run_name="__main__")
    assert done.value.code == 0
