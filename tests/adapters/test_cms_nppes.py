"""CMS NPPES NPI registry (equity.adapters.federal.cms_nppes)."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.bulk_files import BulkClient
from equity.adapters.federal.cms_nppes import (
    CMSNPPES,
    PAGE,
    SHARDS,
    parse_day,
    practice_state,
    pseudo_digits,
    rows_of,
    shard,
)
from equity.adapters.federal.fcc_uls import us_states
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters" / CMSNPPES.source_id
ZIP_NAME = "NPPES_Data_Dissemination_November_2026_V2.zip"
URL = f"https://download.cms.gov/nppes/{ZIP_NAME}"
MEMBER = "npidata_pfile_20050523-20261102.csv"
HEADER = [
    "NPI", "Entity Type Code", "Provider Organization Name (Legal Business Name)",
    "Provider Last Name (Legal Name)", "Provider First Name", "Provider Middle Name",
    "Provider Name Suffix Text", "Provider Credential Text", "Provider Other Last Name",
    "Provider Other First Name", "Provider Other Last Name Type Code",
    "Provider First Line Business Mailing Address",
    "Provider Second Line Business Mailing Address",
    "Provider Business Mailing Address City Name",
    "Provider Business Mailing Address State Name",
    "Provider Business Mailing Address Postal Code",
    "Provider Business Mailing Address Country Code (If outside U.S.)",
    "Provider Business Mailing Address Telephone Number",
    "Provider First Line Business Practice Location Address",
    "Provider Business Practice Location Address City Name",
    "Provider Business Practice Location Address State Name",
    "Provider Business Practice Location Address Postal Code",
    "Provider Business Practice Location Address Country Code (If outside U.S.)",
    "Provider Enumeration Date", "Last Update Date", "NPI Deactivation Date",
    "NPI Reactivation Date", "Provider Sex Code", "Authorized Official Last Name",
    "Authorized Official First Name", "Authorized Official Middle Name",
    "Authorized Official Title or Position", "Is Organization Subpart",
    "Parent Organization LBN", "Healthcare Provider Taxonomy Code_1",
    "Provider License Number_1", "Provider License Number State Code_1",
    "Healthcare Provider Primary Taxonomy Switch_1", "Healthcare Provider Taxonomy Code_2",
    "Provider License Number_2", "Provider License Number State Code_2",
    "Healthcare Provider Primary Taxonomy Switch_2",
]  # fmt: skip
ROWS = [
    # an individual with a former name, practice in Delaware, mailing a PO box
    ["1000000004", "1", "", "DOE", "JANE", "Q", "JR", "M.D.", "ROE", "JANE", "1",
     "PO BOX 1", "", "DOVER", "DE", "199010001", "US", "3025551212", "1 MAIN ST", "DOVER",
     "DE", "199010002", "US", "05/23/2005", "07/13/2026", "", "", "F", "", "", "", "", "",
     "", "207X00000X", "C1234", "DE", "Y", "", "", "", ""],
    # an organization subpart with an authorized official and a parent
    ["1000000012", "2", "DOVER CLINIC LLC", "", "", "", "", "", "", "", "",
     "PO BOX 2", "SUITE 5", "DOVER", "DE", "19901", "US", "", "2 MAIN ST", "DOVER", "DE",
     "19901", "US", "01/02/2010", "01/02/2026", "", "", "", "SMITH", "ANN", "B", "CEO", "Y",
     "DOVER HEALTH INC", "261QP2300X", "", "", "Y", "282N00000X", "L9", "DE", "N"],
    # deactivated: the name is blanked
    ["1000000020", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
     "", "", "", "", "", "", "05/01/2020", "", "", "", "", "", "", "", "", "", "", "", "",
     "", "", "", ""],
    # an organization practicing abroad, deactivated then reactivated
    ["1000000038", "2", "TORONTO PHYSIO", "", "", "", "", "", "", "", "", "", "", "", "", "",
     "", "", "9 KING ST", "TORONTO", "ON", "M5H", "CA", "03/04/2015", "03/04/2016",
     "01/01/2016", "02/01/2016", "", "", "", "", "", "N", "", "", "", "", "", "", "", "", ""],
]  # fmt: skip


def _csv(rows: list[list[str]] = ROWS) -> str:
    out = io.StringIO()
    w = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(HEADER)
    w.writerows(rows)
    return out.getvalue()


def _zip(rows: list[list[str]] = ROWS) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MEMBER.replace(".csv", "_fileheader.csv"), _csv([]))
        zf.writestr(MEMBER, _csv(rows))
        zf.writestr("othername_pfile_20050523-20261102.csv", "x\n")
    return buf.getvalue()


def _fetched(rows: list[dict[str, Any]]) -> Fetched:
    return Fetched(CMSNPPES.source_id, f"{URL}#state=DE", AT, 200,
                   canonical_json({"rows": rows}), "application/json")  # fmt: skip


def test_rows_keep_names_addresses_dates_and_taxonomies_not_phones() -> None:
    rows = list(rows_of(io.StringIO(_csv(), newline="")))
    jane = rows[0]
    assert jane["npi"] == "1000000004" and jane["last_name"] == "DOE"
    assert jane["taxonomies"] == [{"code": "207X00000X", "license": "C1234",
                                   "license_state": "DE", "primary": "Y"}]  # fmt: skip
    assert not any("phone" in k or "sex" in k for k in jane)
    assert rows[1]["taxonomies"][1] == {"code": "282N00000X", "license": "L9",
                                        "license_state": "DE", "primary": "N"}  # fmt: skip
    assert [practice_state(r) for r in rows] == ["DE", "DE", "other", "other"]
    assert shard("1000000004") == 0 and shard("1234567893") == 9 and shard("x") == 0
    assert parse_day("05/23/2005") == date(2005, 5, 23) and parse_day("13/01/2005") is None


def test_normalize_emits_organizations_as_businesses_and_individuals_as_people() -> None:
    rows = list(rows_of(io.StringIO(_csv(), newline="")))
    out = [(r.table, dict(r.row)) for r in CMSNPPES().normalize(_fetched(rows))]
    records = {r["record_key"]: r["record_type"] for t, r in out if t == "source_record"}
    assert records == {"1000000004": "npi_individual", "1000000012": "npi_organization",
                       "1000000038": "npi_organization"}  # fmt: skip
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    clinic = biz["NPI:1000000012"]
    assert (clinic["name"], clinic["status"], clinic["org_form"]) == ("DOVER CLINIC LLC",
                                                                      "active", "LLC")  # fmt: skip
    assert clinic["valid_from"] == date(2010, 1, 2) and clinic["jurisdiction"] == "10"
    addrs = {r["address_id"]: r for t, r in out if t == "address"}
    assert addrs[clinic["principal_address_id"]]["line1"] == "2 MAIN ST"
    assert addrs[clinic["mailing_address_id"]]["line1"] == "PO BOX 2 SUITE 5"
    abroad = biz["NPI:1000000038"]
    assert abroad["principal_address_id"] is None and abroad["jurisdiction"] == "US"
    assert abroad["status"] == "active" and abroad["status_date"] == date(2016, 2, 1)
    roles = {(r["sos_id"], r["role"], r["title"]) for t, r in out if t == "business_role"}
    assert roles == {("NPI:1000000012", "officer", "CEO"),
                     ("NPI:1000000012", "other", "PARENT ORGANIZATION")}  # fmt: skip
    parties = {r["raw_name"]: r for t, r in out if t == "party"}
    ann = parties["ANN B SMITH"]
    assert (ann["party_kind"], ann["first_name"], ann["last_name"]) == ("person", "ANN", "SMITH")
    assert parties["DOVER HEALTH INC"]["party_kind"] == "org"
    jane = parties["JANE Q DOE JR"]
    assert (jane["party_kind"], jane["last_name"], jane["suffix"]) == ("person", "DOE", "JR")
    assert addrs[jane["address_id"]]["line1"] == "1 MAIN ST"
    assert jane["jurisdiction"] == "10"
    former = parties["JANE ROE"]
    assert former["last_name"] == "ROE" and former["address_id"] == jane["address_id"]
    assert former["party_id"] != jane["party_id"]


def test_deactivation_without_reactivation_is_the_status() -> None:
    row = {"npi": "1000000046", "entity_type": "2", "org_name": "GONE INC",
           "deactivation_date": "05/01/2020", "enumeration_date": "01/01/2019"}  # fmt: skip
    (biz,) = [r.row for r in CMSNPPES().normalize(_fetched([row])) if r.table == "business"]
    assert (biz["status"], biz["status_date"]) == ("deactivated", date(2020, 5, 1))


def test_pii_fields_cover_names_and_streets_and_the_scrub_hides_individual_ids() -> None:
    assert {"last_name", "first_name", "ao_last_name", "other_last_name", "practice_line1",
            "mail_line1", "mail_line2"} <= set(CMSNPPES.pii_fields)  # fmt: skip
    rows = list(rows_of(io.StringIO(_csv(), newline="")))
    scrubbed = json.loads(CMSNPPES.scrub_fixture(canonical_json({"rows": rows})))["rows"]
    jane, clinic = scrubbed[0], scrubbed[1]
    for k in ("last_name", "first_name", "middle_name", "other_last_name"):
        assert jane[k].startswith("TESTOWNER")
    assert jane["practice_line1"].endswith(" TEST ST") and jane["mail_line1"].endswith(" TEST ST")
    assert jane["npi"] == pseudo_digits("npi", "1000000004", 10) and jane["npi"][0] == "0"
    assert jane["taxonomies"][0]["license"].startswith("TEST")
    assert clinic["npi"] == "1000000012" and clinic["org_name"] == "DOVER CLINIC LLC"
    assert clinic["ao_last_name"].startswith("TESTOWNER")


def test_recorded_fixture_is_pseudonymized() -> None:
    paths = sorted(FIXTURES.glob("*.json"))
    assert paths
    for path in paths:
        for r in json.loads(path.read_text())["rows"]:
            for k in CMSNPPES.pii_fields:
                v = r.get(k)
                assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k
            if r.get("entity_type") != "2":
                assert r["npi"].startswith("0")


def test_partitions_are_states_by_shard() -> None:
    parts = list(CMSNPPES().partitions())
    assert len(parts) == (len(us_states()) + 1) * SHARDS
    assert parts[0] == {"state": us_states()[0], "shard": "0"}
    assert parts[-1] == {"state": "other", "shard": str(SHARDS - 1)}


class _RangeServer:
    """A fake transport: the NPI files page, and the zip with Range support."""

    def __init__(self, files: Mapping[str, bytes]) -> None:
        self.files = files
        self.ranges = 0

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                 ) -> tuple[int, bytes, str]:  # fmt: skip
        data = self.files.get(url)
        if data is None:
            return 404, b"", "text/plain"
        rng = headers.get("Range")
        if rng is None:
            return 200, data, "text/html"
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng)
        assert m is not None
        self.ranges += 1
        if m.group(1) == "":
            return 206, data[-int(m.group(2)) :], "application/zip"
        return 206, data[int(m.group(1)) : int(m.group(2)) + 1], "application/zip"


def _no_download(url: str, headers: Mapping[str, str], timeout: float, dest: Path
                 ) -> tuple[int, str]:  # fmt: skip
    raise AssertionError("a sample must not download the zip")


def test_limit_reads_the_zip_over_range_requests_without_downloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    page = f"<a id='DDSMTH.ZIP.D' href='./{ZIP_NAME}'>x</a>".encode()
    server = _RangeServer({PAGE: page, URL: _zip()})
    client = BulkClient(transport=server, stream_transport=_no_download, sleep=lambda s: None,
                        now=lambda: AT)  # fmt: skip
    client.min_interval_s = 0
    fetched = CMSNPPES(client).fetch(FetchRequest({"state": "DE", "limit": "1"}))
    body = json.loads(fetched.content)
    assert [r["npi"] for r in body["rows"]] == ["1000000004"]
    assert body["member"] == MEMBER and server.ranges >= 1  # the tail holds this small zip
    assert fetched.request == f"{URL}#state=DE" and fetched.retrieved_at == AT
    with pytest.raises(ValueError, match="unknown state"):
        CMSNPPES(client).fetch(FetchRequest({"state": "ZZ", "limit": "1"}))


def test_a_full_partition_splits_the_zip_once_by_state_and_keeps_its_shard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    zpath = tmp_path / ZIP_NAME
    zpath.write_bytes(_zip())
    adapter = CMSNPPES(BulkClient(transport=_RangeServer({}), sleep=lambda s: None))
    de0 = json.loads(adapter.fetch(FetchRequest({"state": "DE", "shard": "0",
                                                 "path": str(zpath)})).content)  # fmt: skip
    assert [r["npi"] for r in de0["rows"]] == ["1000000004"]
    split = CMSNPPES.split_dir(zpath)
    assert sorted(p.name for p in split.iterdir()) == ["DE.jsonl.gz", "_complete", "other.jsonl.gz"]
    de1 = json.loads(adapter.fetch(FetchRequest({"state": "DE", "shard": "1",
                                                 "path": str(zpath)})).content)  # fmt: skip
    assert [r["npi"] for r in de1["rows"]] == ["1000000012"]
    ak = json.loads(adapter.fetch(FetchRequest({"state": "AK", "path": str(zpath)})).content)
    assert ak["rows"] == [] and ak["url"] == URL


def test_recorded_fixture_passes_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(CMSNPPES, sorted(FIXTURES.glob("*.json")), empty_db)
