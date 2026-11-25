"""DOL Wage and Hour Division compliance actions (equity.adapters.federal.dol_whd).

The recorded fixture is a fetch of the only rows DOL serves without an API key: the 10-row
preview in the dataset's metadata (apiprod.dol.gov/v4/datasets/10362), saved as API JSON; the
4 cases with back wages are kept.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.dol_whd import DOLWageHourCases, case_key, day, money
from equity.adapters.federal.fcc_uls import OTHER
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters" / DOLWageHourCases.source_id
HEAD = ("case_id,trade_nm,legal_name,street_addr_1_txt,cty_nm,st_cd,zip_cd,naic_cd,"
        "bw_atp_amt,ee_atp_cnt,cmp_assd,findings_start_date,findings_end_date,"
        "flsa_repeat_violator,flsa_bw_atp_amt,flsa_ot_bw_atp_amt,dbra_bw_atp_amt,"
        "flsa_cl_cmp_assd_amt,flsa_cmp_assd_amt,load_dt\n")  # fmt: skip
CSV = (HEAD
       + "1001,Joe's Diner,JOE'S DINER LLC,1 Main St,Austin,TX,78701,722511,5000.50,4,1200,"
         "2024-01-01,2025-06-30,R,4000.50,4000.50,1000,1200,0,2025-07-01\n"
       + "1002,ACME INC,Acme Inc,2 Elm St,Dallas,TX,75201,236220,0,0,0,2024-01-01,2025-01-31,"
         "N/A,0,0,0,0,0,2025-07-01\n"
       + "1003,Bobs Bakery,Bobs Bakery,3 Oak Ave,Reno,NV,89501,311811,250,1,0,2023-02-01,"
         "2023-03-01,N/A,250,0,0,0,0,2025-07-01\n"
       + "1004,Future Co,Future Co,4 Pine Rd,Austin,TX,78701,1,100,1,0,2026-01-01,2027-01-01,"
         "N/A,100,0,0,0,0,2025-07-01\n"
       + "1005,Overseas Ltd,Overseas Ltd,9 Rue,Paris,ZZ,,1,0,0,500,2020-01-01,2020-12-31,N/A,"
         "0,0,0,0,500,2025-07-01\n")  # fmt: skip


def _save(tmp_path: Path, name: str = "whd_whisard.csv") -> Path:
    path = tmp_path / name
    path.write_text(CSV, encoding="utf-8")
    return path


def _fetched(rows: list[dict[str, object]]) -> Fetched:
    return Fetched(DOLWageHourCases.source_id, "https://apiprod.dol.gov/v4/x", AT, 200,
                   canonical_json({"rows": rows}), "application/json")  # fmt: skip


def test_back_wages_and_penalties_become_two_instruments(tmp_path: Path) -> None:
    fetched = DOLWageHourCases().fetch(FetchRequest({"path": str(_save(tmp_path))}))
    rows = json.loads(fetched.content)["rows"]
    # 1002 owes nothing; the rest are kept by fetch (normalize drops the future case).
    assert [r["case_id"] for r in rows] == ["1001", "1003", "1004", "1005"]
    assert "load_dt" not in rows[0] and "flsa_cmp_assd_amt" not in rows[0]
    out = [(r.table, dict(r.row)) for r in DOLWageHourCases().normalize(_fetched(rows))]
    inst = {r["instrument_number"]: r for t, r in out if t == "instrument"}
    assert set(inst) == {"1001-BW", "1001-CMP", "1003-BW", "1005-CMP"}
    bw = inst["1001-BW"]
    assert bw["doc_type"] == "OTHER" and bw["principal_amount"] == Decimal("5000.50")
    assert bw["recorded_on"] == date(2025, 6, 30) and bw["jurisdiction"] == "48"
    assert bw["doc_type_raw"] == ("WHD back wages agreed to pay, 4 employees (DBRA, FLSA); "
                                  "FLSA repeat violator")  # fmt: skip
    cmp = inst["1001-CMP"]
    assert cmp["principal_amount"] == Decimal("1200.00")
    assert cmp["doc_type_raw"].startswith("WHD civil money penalties assessed (FLSA CL)")
    party = {r["party_id"]: r for t, r in out if t == "party"}
    links = sorted((r["instrument_uid"] == bw["instrument_uid"], r["role"], r["seq"],
                    party[r["party_id"]]["raw_name"])
                   for t, r in out if t == "instrument_party")  # fmt: skip
    assert [x[1:] for x in links if x[0]] == [
        ("creditor", 1, "U.S. Department of Labor, Wage and Hour Division"),
        ("debtor", 1, "JOE'S DINER LLC"), ("debtor", 2, "Joe's Diner")]  # fmt: skip
    debtor = next(r for r in party.values() if r["raw_name"] == "JOE'S DINER LLC")
    addr = {r["address_id"]: r for t, r in out if t == "address"}
    assert addr[debtor["address_id"]]["zip5"] == "78701"
    # Same legal and trade name: one debtor. A foreign state: no address state, US juris.
    bob = [r for t, r in out if t == "instrument_party" and r["role"] == "debtor"
           and r["instrument_uid"] == inst["1003-BW"]["instrument_uid"]]  # fmt: skip
    assert len(bob) == 1
    assert inst["1005-CMP"]["jurisdiction"] == "US"


def test_state_partitions_limit_and_saved_formats(tmp_path: Path) -> None:
    adapter = DOLWageHourCases()
    parts = list(adapter.partitions())
    assert {"state": "TX"} in parts and parts[-1] == {"state": OTHER}
    path = str(_save(tmp_path))
    tx = adapter.fetch(FetchRequest({"path": path, "state": "TX"}))
    assert [r["case_id"] for r in json.loads(tx.content)["rows"]] == ["1001", "1004"]
    assert tx.request.endswith(":st_cd=TX") and tx.http_status is None
    one = adapter.fetch(FetchRequest({"path": path, "state": "TX", "limit": "1"}))
    assert [r["case_id"] for r in json.loads(one.content)["rows"]] == ["1001"]
    other = adapter.fetch(FetchRequest({"path": path, "state": OTHER}))
    assert [r["case_id"] for r in json.loads(other.content)["rows"]] == ["1005"]
    with pytest.raises(ValueError, match="unknown state"):
        adapter.fetch(FetchRequest({"path": path, "state": "XX"}))
    # A zip of the CSV and saved API JSON read the same.
    zdir = tmp_path / "z"
    zdir.mkdir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("whd_whisard_20260101.csv", CSV)
    (zdir / "whd.zip").write_bytes(buf.getvalue())
    api = [{"case_id": 1006, "legal_name": "X LLC", "st_cd": "TX", "bw_atp_amt": 10.0,
            "cmp_assd": 0.0, "findings_end_date": "2025-01-01T00:00:00"}]  # fmt: skip
    (zdir / "page1.json").write_text(json.dumps({"data": api}))
    both = adapter.fetch(FetchRequest({"path": str(zdir), "state": "TX"}))
    assert [str(r["case_id"]) for r in json.loads(both.content)["rows"]] == ["1001", "1004", "1006"]


def test_missing_saved_files_say_where_to_put_them(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"data\.dol\.gov"):
        DOLWageHourCases().fetch(FetchRequest({"path": str(tmp_path)}))


def test_value_helpers() -> None:
    assert money("12136.0") == Decimal("12136.00") and money("$1,234.5") == Decimal("1234.50")
    assert money("0") is None and money("") is None and money("-5") is None
    assert day("2005-07-19T00:00:00") == date(2005, 7, 19) == day("07/19/2005")
    assert day("") is None
    assert case_key(1460300) == "1460300" == case_key("1460300.0")


def test_pii_fields_cover_names_and_streets() -> None:
    assert set(DOLWageHourCases.pii_fields) == {"trade_nm", "legal_name", "street_addr_1_txt"}
    row = {"legal_name": "ANN LEE", "trade_nm": "LEE CAFE LLC", "street_addr_1_txt": "1 MAIN ST",
           "cty_nm": "X"}  # fmt: skip
    body = canonical_json({"rows": [row]})
    r = json.loads(DOLWageHourCases.scrub_fixture(body))["rows"][0]
    assert r["legal_name"].startswith("TESTOWNER") and r["trade_nm"].endswith(" LLC")
    assert r["street_addr_1_txt"].endswith(" TEST ST") and r["cty_nm"] == "X"
    for path in sorted(FIXTURES.glob("*.json")):
        for row in json.loads(path.read_text())["rows"]:
            for k in DOLWageHourCases.pii_fields:
                assert (
                    not row.get(k)
                    or str(row[k]).startswith("TESTOWNER")
                    or str(row[k]).endswith(" TEST ST")
                )


def test_recorded_fixture_passes_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(DOLWageHourCases, sorted(FIXTURES.glob("*.json")), empty_db)
