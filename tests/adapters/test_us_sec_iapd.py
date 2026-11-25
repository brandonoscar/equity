"""SEC investment advisers and Schedule A/B control persons (equity.adapters.federal.sec_iapd)."""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.bulk_files import BulkClient
from equity.adapters.federal.sec_iapd import (
    META_URL,
    SECInvestmentAdvisers,
    adv_date,
    person_parts,
    read_firms,
    roles_for,
)
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters" / SECInvestmentAdvisers.source_id
URL = ("https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/2026/"
       "ADV_Filing_Data_20261001_20261031.zip")  # fmt: skip
BASE_HEAD = ('"FilingID","FormVersion","DateSubmitted","1A","1B1","1D","1E1","1F1-Street 1",'
             '"1F1-Street 2","1F1-City","1F1-State","1F1-Country","1F1-Postal","1F1-Private",'
             '"1G-Street 1","1G-City","1G-State","1G-Country","1G-Postal"\n')  # fmt: skip
IA_BASE = (BASE_HEAD
           + '"100","10/2021","10/12/2026 11:23:12 AM","ACME CAPITAL ADVISORS, INC.","ACME",'
             '"801-1","174673","4500 BISCAYNE BLVD","SUITE 1","MIAMI","FL","United States",'
             '"33137","N","PO BOX 9","MIAMI","FL","United States","33101"\n'
           + '"101","10/2021","10/20/2026 09:00:00 AM","ACME CAPITAL ADVISORS, INC.","ACME",'
             '"801-1","174673","4500 BISCAYNE BLVD","SUITE 2","MIAMI","FL","United States",'
             '"33137","N","","","","",""\n'
           + '"102","10/2021","10/13/2026 10:00:00 AM","JANE ROE","JANE ROE WEALTH","801-2",'
             '"999","","","AUSTIN","TX","United States","78701","Y","","","","",""\n'
           + '"103","10/2021","10/14/2026 10:00:00 AM","LONDON LLP","LONDON LLP","801-3",'
             '"55","1 STRAND","","LONDON","","United Kingdom","WC2N 5","N","","","","",""\n'
           + '"104","10/2021","","NO DATE LLC","NO DATE LLC","801-4","56","","","","","","",'
             '"N","","","","",""\n')  # fmt: skip
SCHED_HEAD = ('"FilingID","SchA-3","Schedule","Full Legal Name","DE/FE/I","Entity in Which",'
              '"Title or Status","Status Acquired","Ownership Code","Control Person","PR",'
              '"OwnerID"\n')  # fmt: skip
IA_SCHED = (SCHED_HEAD
            + '"101","N","A","YATES, JR., GENE, A.","I","","OWNER; PRESIDENT; MEMBER","06/2014",'
              '"E","Y","N","4852526"\n'
            + '"101","N","A","ACME HOLDINGS, LLC","DE","","MANAGING MEMBER","07/2018","NA","Y",'
              '"N",""\n'
            + '"101","","B","GREENE, ANN","I","ACME HOLDINGS, LLC","TRUSTEE","07/2018","F","N",'
              '"N","1"\n'
            + '"100","N","A","OLD, OFFICER","I","","CHIEF COMPLIANCE OFFICER","01/2020","NA",'
              '"N","N","2"\n'
            + '"102","N","A","ROE, JANE","I","","SOLE PROPRIETOR","01/2020","E","Y","N",'
              '"3"\n')  # fmt: skip
ERA_BASE = ('"FilingID","FormVersion","DateSubmitted","1A","1B1","1D","1E1","1F1-Street 1",'
            '"1F1-City","1F1-State","1F1-Country","1F1-Postal","1F1-Private"\n'
            '"200","10/2021","10/15/2026 01:00:00 PM","VENTURE FUND MANAGER LP","VFM","802-9",'
            '"77","2 SAND HILL RD","MENLO PARK","CA","United States","94025","N"\n')  # fmt: skip
ERA_SCHED = (SCHED_HEAD
             + '"200","N","A","DOE, JOHN","I","","MANAGING DIRECTOR, DIRECTOR","02/2019","C",'
               '"Y","N","4"\n')  # fmt: skip


def _zip(members: Mapping[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


MONTH = _zip({
    "ADV_Filing_Types_20261001_20261031.csv": '"FilingID"\n',
    "IA_ADV_Base_A_20261001_20261031.csv": IA_BASE,
    "IA_Schedule_A_B_20261001_20261031.csv": IA_SCHED,
    "IA_Schedule_D_7B1_20261001_20261031.csv": '"FilingID"\n',
    "ERA_ADV_Base_20261001_20261031.csv": ERA_BASE,
    "ERA_Schedule_A_B_20261001_20261031.csv": ERA_SCHED,
})  # fmt: skip
META = json.dumps({
    "advFilingData": {"sectionDisplayOrder": 1,
                      "2026": {"files": [{"fileName": "ADV_Filing_Data_20261001_20261031.zip"},
                                         {"fileName": "ADV_Filing_Data_20260901_20260930.zip"}]},
                      "2025": {"files": [{"fileName": "ADV_Filing_Data_20250101_20250131.zip"},
                                         {"fileName": "notes.pdf"}]}},
    "advBrochures": {"2026": {"files": [{"fileName": "ADV_Brochures_2026_October.zip"}]}},
}).encode()  # fmt: skip


class _RangeServer:
    def __init__(self, files: Mapping[str, bytes]) -> None:
        self.files = files
        self.bytes_sent = 0

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                 ) -> tuple[int, bytes, str]:  # fmt: skip
        data = self.files.get(url)
        if data is None:
            return 404, b"", "text/plain"
        rng = headers.get("Range")
        if rng is None:
            return 200, data, "application/json"
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng)
        assert m is not None
        part = (data[-int(m.group(2)) :] if m.group(1) == ""
                else data[int(m.group(1)) : int(m.group(2)) + 1])  # fmt: skip
        self.bytes_sent += len(part)
        return 206, part, "application/zip"


def _adapter(files: Mapping[str, bytes]) -> SECInvestmentAdvisers:
    client = BulkClient(transport=_RangeServer(files), sleep=lambda s: None, now=lambda: AT)
    client.min_interval_s = 0
    return SECInvestmentAdvisers(client)


def _firms() -> list[dict[str, object]]:
    with zipfile.ZipFile(io.BytesIO(MONTH)) as zf:
        return read_firms(zf)


def _fetched(firms: list[dict[str, object]]) -> Fetched:
    return Fetched(SECInvestmentAdvisers.source_id, URL, AT, 200,
                   canonical_json({"firms": firms}), "application/json")  # fmt: skip


def test_firms_are_keyed_by_crd_from_their_latest_filing() -> None:
    firms = _firms()
    got = [(f["crd"], f["register"]) for f in firms]
    assert got == [("55", "IA"), ("77", "ERA"), ("999", "IA"), ("174673", "IA")]
    acme = firms[-1]
    assert acme["base"]["FilingID"] == "101"  # the amendment of 10/20 wins over 10/12
    assert {o["Full Legal Name"] for o in acme["owners"]} == {
        "YATES, JR., GENE, A.", "ACME HOLDINGS, LLC", "GREENE, ANN"}  # fmt: skip
    assert all("OwnerID" not in o for o in acme["owners"])
    with zipfile.ZipFile(io.BytesIO(MONTH)) as zf:
        assert [f["crd"] for f in read_firms(zf, 2)] == ["55", "77"]


def test_normalize_emits_businesses_and_control_persons() -> None:
    out = [(r.table, dict(r.row)) for r in SECInvestmentAdvisers().normalize(_fetched(_firms()))]
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    assert set(biz) == {"CRD:55", "CRD:77", "CRD:999", "CRD:174673"}
    acme = biz["CRD:174673"]
    assert acme["name"] == "ACME CAPITAL ADVISORS, INC." and acme["org_form"] == "INC"
    assert acme["valid_from"] == date(2026, 10, 20) and acme["status"] == "SEC registered"
    assert acme["jurisdiction"] == "12" and acme["mailing_address_id"] is None
    assert biz["CRD:77"]["status"] == "exempt reporting"
    assert biz["CRD:55"]["jurisdiction"] == "US"  # a London main office
    addr = {r["address_id"]: r for t, r in out if t == "address"}
    assert addr[acme["principal_address_id"]]["line1"].startswith("4500 BISCAYNE")
    home = addr[biz["CRD:999"]["principal_address_id"]]  # a residence: street not published
    assert home["line1"] is None and home["zip5"] == "78701"
    assert addr[biz["CRD:55"]["principal_address_id"]]["zip5"] is None
    party = {r["party_id"]: r for t, r in out if t == "party"}
    roles = sorted((r["sos_id"], r["role"], party[r["party_id"]]["raw_name"], r["title"])
                   for t, r in out if t == "business_role")  # fmt: skip
    assert roles == [
        ("CRD:174673", "member", "ACME HOLDINGS, LLC",
         "MANAGING MEMBER (under 5%; control person)"),
        ("CRD:174673", "member", "GENE A. YATES JR.",
         "OWNER; PRESIDENT; MEMBER (75% or more; control person)"),
        ("CRD:174673", "officer", "GENE A. YATES JR.",
         "OWNER; PRESIDENT; MEMBER (75% or more; control person)"),
        ("CRD:174673", "other", "ANN GREENE",
         "indirect owner via ACME HOLDINGS, LLC: TRUSTEE "
         "(general partner, trustee or elected manager)"),
        ("CRD:77", "director", "JOHN DOE", "MANAGING DIRECTOR, DIRECTOR (25-50%; control person)"),
        ("CRD:77", "officer", "JOHN DOE", "MANAGING DIRECTOR, DIRECTOR (25-50%; control person)"),
        ("CRD:999", "other", "JANE ROE", "SOLE PROPRIETOR (75% or more; control person)"),
    ]  # fmt: skip
    gene = next(r for r in party.values() if r["raw_name"] == "GENE A. YATES JR.")
    assert gene["party_kind"] == "person"
    assert (gene["first_name"], gene["middle"], gene["last_name"], gene["suffix"]) == (
        "GENE", "A.", "YATES", "JR.")  # fmt: skip
    holdco = next(r for r in party.values() if r["raw_name"] == "ACME HOLDINGS, LLC")
    assert holdco["party_kind"] == "org" and holdco["last_name"] is None


def test_title_roles_names_and_dates() -> None:
    assert roles_for("OWNER; PRESIDENT; CHIEF COMPLIANCE OFFICER") == ["officer"]
    assert roles_for("MANAGING MEMBER") == ["member"]
    assert roles_for("MANAGING DIRECTOR") == ["officer"]
    assert roles_for("DIRECTOR") == ["director"]
    assert roles_for("GENERAL MANAGER") == ["manager"]
    assert roles_for("SHAREHOLDER") == ["other"] == roles_for(None)
    assert person_parts("RINALDI, III, JOSEPH, FRANCIS") == {
        "first_name": "JOSEPH", "middle": "FRANCIS", "last_name": "RINALDI",
        "suffix": "III"}  # fmt: skip
    assert person_parts("CHER") == {"first_name": None, "middle": None, "last_name": "CHER",
                                    "suffix": None}  # fmt: skip
    assert adv_date("10/12/2026 11:23:12 AM") == date(2026, 10, 12) == adv_date("10/12/2026")
    assert adv_date("") is None


def test_partitions_come_from_the_manifest_and_fetch_reads_over_range() -> None:
    adapter = _adapter({META_URL: META, URL: MONTH})
    assert list(adapter.partitions()) == [{"month": "2025-01"}, {"month": "2026-09"},
                                          {"month": "2026-10"}]  # fmt: skip
    fetched = adapter.fetch(FetchRequest({"month": "2026-10", "limit": "1"}))
    body = json.loads(fetched.content)
    assert [f["crd"] for f in body["firms"]] == ["55"] and fetched.request == URL
    assert fetched.retrieved_at == AT
    with pytest.raises(ValueError, match="bad month"):
        adapter.fetch(FetchRequest({"month": "2026-1"}))
    with pytest.raises(RuntimeError, match="no Form ADV"):
        adapter.fetch(FetchRequest({"month": "2024-12"}))
    assert adapter.health().ok


def test_pii_fields_cover_names_and_streets() -> None:
    assert set(SECInvestmentAdvisers.pii_fields) >= {"Full Legal Name", "Entity in Which",
                                                     "1F1-Street 1", "1G-Street 1"}  # fmt: skip
    body = canonical_json({"firms": _firms()})
    scrubbed = json.loads(SECInvestmentAdvisers.scrub_fixture(body))["firms"][-1]
    assert scrubbed["base"]["1F1-Street 1"].endswith(" TEST ST")
    assert scrubbed["base"]["1A"].startswith("TESTOWNER") and scrubbed["base"]["1A"].endswith(
        " INC"
    )
    assert all(o["Full Legal Name"].startswith("TESTOWNER") for o in scrubbed["owners"])
    for path in sorted(FIXTURES.glob("*.json")):
        for firm in json.loads(path.read_text())["firms"]:
            for row in (firm["base"], *firm["owners"]):
                for k in SECInvestmentAdvisers.pii_fields:
                    v = row.get(k)
                    assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k


def test_recorded_fixture_passes_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(SECInvestmentAdvisers, sorted(FIXTURES.glob("*.json")), empty_db)
