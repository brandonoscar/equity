"""USPTO trademark owners and patent assignments (equity.adapters.federal.uspto)."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.uspto import (
    USPTOPatentAssignments,
    USPTOTrademarkOwners,
    patent_assignments,
    split_last_first,
    trademark_cases,
)
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)

TM = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE trademark-applications-daily SYSTEM "trademark-applications-daily-v2.dtd">
<trademark-applications-daily><version><version-no>2.0</version-no></version>
<application-information><file-segments><action-keys><action-key>TS</action-key>
<case-file><serial-number>99000001</serial-number><registration-number>0000000</registration-number>
 <transaction-date>20251124</transaction-date>
 <case-file-header><filing-date>20251120</filing-date><status-code>630</status-code>
  <mark-identification>WIDGETRY</mark-identification></case-file-header>
 <case-file-owners>
  <case-file-owner><entry-number>01</entry-number><party-type>10</party-type>
   <nationality><state>DE</state><country>US</country></nationality>
   <legal-entity-type-code>03</legal-entity-type-code><party-name>ACME WIDGETS INC.</party-name>
   <address-1>1 MAIN ST</address-1><address-2>STE 2</address-2><city>SAN JOSE</city>
   <state>CA</state><country>US</country><postcode>95101</postcode></case-file-owner>
 </case-file-owners></case-file>
<case-file><serial-number>99000002</serial-number>
 <case-file-header><filing-date>20251121</filing-date></case-file-header>
 <case-file-owners>
  <case-file-owner><entry-number>01</entry-number><party-type>10</party-type>
   <legal-entity-type-code>01</legal-entity-type-code><party-name>Ann Lee</party-name>
   <address-1>9 ELM RD</address-1><city>AUSTIN</city><state>TX</state>
   <postcode>78701-1111</postcode><dba-aka-text>DBA Lee Bakery</dba-aka-text></case-file-owner>
  <case-file-owner><entry-number>02</entry-number><party-type>10</party-type>
   <legal-entity-type-code>01</legal-entity-type-code><party-name>Bob Ray</party-name>
   <address-1>9 ELM RD</address-1><city>AUSTIN</city><state>TX</state>
   <postcode>78701</postcode></case-file-owner>
 </case-file-owners></case-file>
<case-file><serial-number>99000003</serial-number><case-file-owners/></case-file>
</action-keys></file-segments></application-information></trademark-applications-daily>"""

PA = b"""<?xml version="1.0" encoding="UTF-8"?>
<us-patent-assignments dtd-version="0.8"><patent-assignments>
<patent-assignment><assignment-record><reel-no>71234</reel-no><frame-no>567</frame-no>
  <last-update-date><date>20251121</date></last-update-date><purge-indicator>N</purge-indicator>
  <recorded-date><date>20251120</date></recorded-date><page-count>3</page-count>
  <conveyance-text>ASSIGNMENT OF ASSIGNORS INTEREST (SEE DOCUMENT FOR DETAILS).</conveyance-text>
 </assignment-record>
 <patent-assignors>
  <patent-assignor><name>DOE, JOHN Q.</name>
   <execution-date><date>20251101</date></execution-date></patent-assignor>
  <patent-assignor><name>ROE, JANE</name>
   <execution-date><date>20251102</date></execution-date></patent-assignor>
 </patent-assignors>
 <patent-assignees><patent-assignee><name>ACME WIDGETS INC.</name><address-1>1 MAIN ST</address-1>
  <city>SAN JOSE</city><state>CA</state><postcode>95101</postcode></patent-assignee>
 </patent-assignees>
 <patent-properties><patent-property>
  <document-id><country>US</country><doc-number>18123456</doc-number><kind>X0</kind>
   <date>20230101</date></document-id>
  <invention-title lang="en">WIDGET</invention-title></patent-property></patent-properties>
</patent-assignment>
<patent-assignment><assignment-record><reel-no>71234</reel-no><frame-no>600</frame-no>
  <recorded-date><date>20251120</date></recorded-date>
  <conveyance-text>SECURITY INTEREST (SEE DOCUMENT FOR DETAILS).</conveyance-text>
 </assignment-record>
 <patent-assignors><patent-assignor><name>ACME WIDGETS INC.</name></patent-assignor>
 </patent-assignors>
 <patent-assignees><patent-assignee><name>FIRST BANK, N.A.</name><city>BOSTON</city>
  <state>MA</state><postcode>02110</postcode></patent-assignee></patent-assignees>
</patent-assignment>
<patent-assignment><assignment-record><reel-no>1</reel-no><frame-no>1</frame-no>
  <purge-indicator>Y</purge-indicator></assignment-record></patent-assignment>
</patent-assignments></us-patent-assignments>"""


def _zip(path: Path, member: str, data: bytes) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, data)
    return path


def _rows(cls: type, records: list[dict[str, object]]) -> list[tuple[str, dict[str, object]]]:
    fetched = Fetched(cls.source_id, "x", AT, None,  # type: ignore[attr-defined]
                      canonical_json({"records": records}), "application/json")  # fmt: skip
    return [(r.table, dict(r.row)) for r in cls().normalize(fetched)]


def test_trademark_owners(tmp_path: Path) -> None:
    src = _zip(tmp_path / "apc251124.zip", "apc251124.xml", TM)
    cases = trademark_cases(src)
    assert [c["serial_number"] for c in cases] == ["99000001", "99000002"]  # no owners: skipped
    assert trademark_cases(src, 1)[0]["mark"] == "WIDGETRY"
    out = _rows(USPTOTrademarkOwners, cases)
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    assert set(biz) == {"USPTO-TM:99000001:10-01", "USPTO-TM:99000002:10-01"}
    acme = biz["USPTO-TM:99000001:10-01"]
    assert acme["name"] == "ACME WIDGETS INC." and acme["valid_from"] == date(2025, 11, 20)
    assert acme["jurisdiction"] == "06"
    assert biz["USPTO-TM:99000002:10-01"]["name"] == "Lee Bakery"  # the dba, prefix dropped
    (role,) = [r for t, r in out if t == "business_role"]
    assert role["title"] == "trademark owner (individual)"
    people = {r["raw_name"]: r for t, r in out if t == "party"}
    assert set(people) == {"Ann Lee", "Bob Ray"}
    assert all(p["party_kind"] == "person" and p["address_id"] for p in people.values())
    lines = {r["line1"] for t, r in out if t == "address"}
    assert "1 MAIN ST STE 2" in lines


def test_patent_assignments(tmp_path: Path) -> None:
    src = _zip(tmp_path / "ad20251124.zip", "ad20251124.xml", PA)
    recs = patent_assignments(src)
    assert len(recs) == 3 and len(patent_assignments(src, 1)) == 1
    assert recs[0]["properties"][0]["documents"][0]["doc_number"] == "18123456"
    out = _rows(USPTOPatentAssignments, recs)
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    assert set(biz) == {"USPTO-PA:071234-0567:1", "USPTO-PA:071234-0600:1"}  # purged: skipped
    roles = [r for t, r in out if t == "business_role"]
    # Inventors assigning to their company are tied to it; a security interest ties nobody.
    assert {(r["sos_id"], r["title"]) for r in roles} == {
        ("USPTO-PA:071234-0567:1", "patent assignor")
    }
    assert len(roles) == 2
    people = {r["raw_name"]: r for t, r in out if t == "party"}
    doe = people["DOE, JOHN Q."]
    assert (doe["party_kind"], doe["first_name"], doe["middle"], doe["last_name"]) == (
        "person", "JOHN", "Q.", "DOE")  # fmt: skip
    assert "ACME WIDGETS INC." in people  # the security-interest assignor, without a role
    assert split_last_first("FIRST BANK, N.A.") == {}


def test_fetch_reads_the_drop_folder_with_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("equity.adapters.federal.uspto.MANUAL_DIR", tmp_path)
    adapter = USPTOTrademarkOwners()
    with pytest.raises(RuntimeError, match="save the daily zips"):
        list(adapter.partitions())
    assert adapter.health().ok is False
    drop = tmp_path / USPTOTrademarkOwners.source_id
    drop.mkdir()
    _zip(drop / "apc251124.zip", "apc251124.xml", TM)
    (drop / "notes.txt").write_text("not a data file")
    assert list(adapter.partitions()) == [{"file": "apc251124.zip"}]
    fetched = adapter.fetch(FetchRequest({"file": "apc251124.zip", "limit": "1"}))
    body = json.loads(fetched.content)
    assert len(body["records"]) == 1 and fetched.request.endswith("#file=apc251124.zip")
    path = adapter.fetch(FetchRequest({"path": str(drop / "apc251124.zip")}))
    assert len(json.loads(path.content)["records"]) == 2
    assert adapter.health().ok and adapter.source_row()["access_method"] == "manual"


def test_pii_fields_are_scrubbed() -> None:
    tm = json.loads(USPTOTrademarkOwners.scrub_fixture(canonical_json({"records": [{
        "owners": [{"owner_name": "Ann Lee", "owner_address_1": "9 ELM RD",
                    "dba_aka": "DBA Lee Bakery", "city": "AUSTIN"}]}]})))  # fmt: skip
    o = tm["records"][0]["owners"][0]
    assert o["owner_name"].startswith("TESTOWNER") and o["dba_aka"].startswith("TESTOWNER")
    assert o["owner_address_1"].endswith(" TEST ST") and o["city"] == "AUSTIN"
    assert {"owner_name", "owner_address_1", "dba_aka"} <= set(USPTOTrademarkOwners.pii_fields)
    pa = json.loads(USPTOPatentAssignments.scrub_fixture(canonical_json({"records": [{
        "assignors": [{"name": "DOE, JOHN"}],
        "assignees": [{"name": "ACME INC", "address_1": "1 MAIN ST"}]}]})))  # fmt: skip
    assert pa["records"][0]["assignors"][0]["name"].startswith("TESTOWNER")
    assert pa["records"][0]["assignees"][0]["name"].startswith("TESTOWNER")
    assert pa["records"][0]["assignees"][0]["name"].endswith(" INC")  # entity suffix kept
    assert pa["records"][0]["assignees"][0]["address_1"].endswith(" TEST ST")
