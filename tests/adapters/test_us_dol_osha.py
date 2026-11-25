"""OSHA inspections with citation penalties (equity.adapters.federal.dol_osha).

No fixture is recorded: the only keyless OSHA rows (the DOL portal's 10-row previews of the
inspection and violation tables) do not share an inspection, so the contract is checked on a
fetch of the inline sample below.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from equity.adapters.base import FetchRequest
from equity.adapters.federal.dol_osha import DOLOSHAPenalties, kind_of, penalized
from equity.adapters.federal.fcc_uls import OTHER

AT = datetime(2026, 11, 25, tzinfo=UTC)
INSPECTIONS = (
    "activity_nr,reporting_id,estab_name,site_address,site_city,site_state,site_zip,"
    "mail_street,mail_city,mail_state,mail_zip,owner_type,naics_code,insp_type,open_date,"
    "close_case_date\n"
    "306953084,0111700,ACME ROOFING LLC,92 Cluff Crossing Rd,Salem,NH,03079,PO Box 1,Salem,NH,"
    "03079,A,238160,B,2024-12-20,2025-03-01\n"
    "306953085,0111700,QUIET SHOP INC,1 Elm St,Salem,NH,03079,,,,,A,452990,F,2024-12-20,\n"
    "306953086,0950621,SUN FARMS,5 Rd 9,Fresno,CA,93701,,,,,A,111,A,2025-02-01,\n"
    "306953087,0111700,FUTURE CO,1 Way,Concord,NH,03301,,,,,A,1,A,2026-11-01,\n"
    "306953088,0111700,ISLAND DOCKS,Pier 2,Hagatna,ZZ,96910,,,,,A,1,A,2025-01-01,\n"
)  # fmt: skip
VIOLATIONS = (
    "activity_nr,citation_id,delete_flag,standard,viol_type,issuance_date,abate_date,"
    "current_penalty,initial_penalty,final_order_date,fta_penalty\n"
    "306953084,01001,,19260501,S,2025-01-15,2025-02-01,4000.00,6000.00,2025-02-10,\n"
    "306953084,01002,,19261053,S,2025-01-10,2025-02-01,1500.5,2000.00,,\n"
    "306953084,02001,X,19260100,O,2025-01-15,2025-02-01,900.00,900.00,,\n"
    "306953084,02002,,19260100,O,2025-01-15,2025-02-01,0,500.00,,\n"
    "306953085,01001,,19100151,O,2025-01-15,2025-02-01,,,,\n"
    "306953086,01001,,19280110,W,2025-03-01,2025-04-01,12000,15000,,\n"
    "306953087,01001,,19260501,S,2026-12-01,2027-01-01,100,100,,\n"
    "306953088,01001,,19170000,R,2025-02-01,2025-03-01,700,700,,\n"
)  # fmt: skip


def _save(tmp_path: Path, zipped: bool = False) -> Path:
    folder = tmp_path / "osha"
    folder.mkdir()
    if zipped:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("osha_inspection0.csv", INSPECTIONS)
            zf.writestr("osha_violation0.csv", VIOLATIONS)
        (folder / "osha.zip").write_bytes(buf.getvalue())
    else:
        (folder / "inspection.csv").write_text(INSPECTIONS)
        (folder / "violation.csv").write_text(VIOLATIONS)
    return folder


@pytest.fixture
def adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DOLOSHAPenalties:
    monkeypatch.setattr(DOLOSHAPenalties, "cache_dir", tmp_path / "work")
    return DOLOSHAPenalties()


def test_penalized_inspections_become_instruments(tmp_path: Path,
                                                  adapter: DOLOSHAPenalties) -> None:  # fmt: skip
    fetched = adapter.fetch(FetchRequest({"path": str(_save(tmp_path))}))
    data = json.loads(fetched.content)
    # 306953085 has no penalty: not kept. Deleted and zero-penalty citations are not kept.
    assert [i["activity_nr"] for i in data["inspections"]] == [
        "306953084", "306953086", "306953087", "306953088"]  # fmt: skip
    assert [v["citation_id"] for v in data["inspections"][0]["violations"]] == ["01001", "01002"]
    out = [(r.table, dict(r.row)) for r in adapter.normalize(fetched)]
    inst = {r["instrument_number"]: r for t, r in out if t == "instrument"}
    assert set(inst) == {"306953084", "306953086", "306953088"}  # 087: issued in the future
    acme = inst["306953084"]
    assert acme["principal_amount"] == Decimal("5500.50") and acme["doc_type"] == "OTHER"
    assert acme["recorded_on"] == date(2025, 1, 10) and acme["jurisdiction"] == "33"
    assert acme["doc_type_raw"] == "OSHA citation penalties, 2 violations (S 2); office 0111700"
    party = {r["party_id"]: r for t, r in out if t == "party"}
    uid = acme["instrument_uid"]
    roles = sorted((r["role"], party[r["party_id"]]["raw_name"]) for t, r in out
                   if t == "instrument_party" and r["instrument_uid"] == uid)  # fmt: skip
    assert roles == [("creditor", "Occupational Safety and Health Administration"),
                     ("debtor", "ACME ROOFING LLC")]  # fmt: skip
    debtor = next(r for r in party.values() if r["raw_name"] == "ACME ROOFING LLC")
    addr = {r["address_id"]: r for t, r in out if t == "address"}
    assert addr[debtor["address_id"]]["zip5"] == "03079"
    assert debtor["org_form"] == "LLC"
    assert inst["306953088"]["jurisdiction"] == "US"  # an unknown state code


def test_state_partitions_limit_and_zip(tmp_path: Path, adapter: DOLOSHAPenalties) -> None:
    parts = list(adapter.partitions())
    assert {"state": "NH"} in parts and parts[-1] == {"state": OTHER}
    path = str(_save(tmp_path, zipped=True))
    nh = adapter.fetch(FetchRequest({"path": path, "state": "NH"}))
    assert [i["activity_nr"] for i in json.loads(nh.content)["inspections"]] == [
        "306953084", "306953087"]  # fmt: skip
    assert nh.request.endswith(":site_state=NH")
    one = adapter.fetch(FetchRequest({"path": path, "state": "NH", "limit": "1"}))
    assert len(json.loads(one.content)["inspections"]) == 1
    assert list(adapter.cache_dir.glob("*.sqlite"))  # the work index is reused...
    other = adapter.fetch(FetchRequest({"path": path, "state": OTHER}))
    assert [i["activity_nr"] for i in json.loads(other.content)["inspections"]] == ["306953088"]
    assert not list(adapter.cache_dir.glob("*.sqlite"))  # ...and deleted after the last one
    with pytest.raises(ValueError, match="unknown state"):
        adapter.fetch(FetchRequest({"path": path, "state": "XX"}))


def test_row_kinds_and_penalty_filter() -> None:
    assert kind_of({"activity_nr": "1", "estab_name": "X"}) == "inspection"
    assert kind_of({"activity_nr": "1", "citation_id": "01001", "current_penalty": "1"}) == (
        "violation"
    )
    assert kind_of({"activity_nr": "1", "hist_penalty": "1"}) is None  # violation_event
    assert penalized({"current_penalty": "10"}) and not penalized({"current_penalty": "0"})
    assert not penalized({"current_penalty": "10", "delete_flag": "X"})


def test_pii_fields_cover_names_and_streets(tmp_path: Path, adapter: DOLOSHAPenalties) -> None:
    assert set(DOLOSHAPenalties.pii_fields) == {"estab_name", "site_address", "mail_street"}
    fetched = adapter.fetch(FetchRequest({"path": str(_save(tmp_path)), "limit": "1"}))
    (i,) = json.loads(DOLOSHAPenalties.scrub_fixture(fetched.content))["inspections"]
    assert i["estab_name"].startswith("TESTOWNER") and i["estab_name"].endswith(" LLC")
    assert i["site_address"].endswith(" TEST ST") and i["mail_street"].endswith(" TEST ST")
    assert i["site_city"] == "Salem"


def test_a_fetched_sample_passes_the_adapter_contract(
    tmp_path: Path,
    adapter: DOLOSHAPenalties,
    empty_db,  # type: ignore[no-untyped-def]
) -> None:
    from ..test_adapter_contract import check_contract

    fetched = adapter.fetch(FetchRequest({"path": str(_save(tmp_path))}))
    sample = tmp_path / "sample.json"
    sample.write_bytes(DOLOSHAPenalties.scrub_fixture(fetched.content))
    check_contract(DOLOSHAPenalties, [sample], empty_db)
