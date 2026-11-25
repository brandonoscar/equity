"""IRS Exempt Organizations Business Master File (equity.adapters.federal.irs_eo)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.bulk_files import BulkClient
from equity.adapters.federal.irs_eo import IRSExemptOrgs, care_of, read_rows, ruling_date
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters" / IRSExemptOrgs.source_id
HEAD = ("EIN,NAME,ICO,STREET,CITY,STATE,ZIP,GROUP,SUBSECTION,AFFILIATION,CLASSIFICATION,RULING,"
        "DEDUCTIBILITY,FOUNDATION,ACTIVITY,ORGANIZATION,STATUS,TAX_PERIOD,ASSET_CD,INCOME_CD,"
        "FILING_REQ_CD,PF_FILING_REQ_CD,ACCT_PD,ASSET_AMT,INCOME_AMT,REVENUE_AMT,NTEE_CD,"
        "SORT_NAME\n")  # fmt: skip
CSV = (HEAD
       + "010631747,AMERICAN LEGION,% JANE DOE,PO BOX 1,CHEYENNE,WY,82001-4917,0925,19,9,1000,"
         "194603,0,00,907908000,5,01,202606,0,0,02,0,06,0,0,0,,POST 6\n"
       + "020000001,FRIENDS OF THE PARK INC,,2 MAIN ST,CASPER,WY,82601,0000,03,3,1000,"
         "209912,1,15,000000000,1,02,,0,0,02,0,12,0,0,0,B94,\n"
       + "12,BAD EIN,,,,,,,,,,,,,,,,,,,,,,,,,,\n")  # fmt: skip


def _fetched(rows: list[dict[str, object]]) -> Fetched:
    return Fetched(IRSExemptOrgs.source_id, "https://www.irs.gov/pub/irs-soi/eo_wy.csv", AT, 200,
                   canonical_json({"rows": rows}), "application/json")  # fmt: skip


def test_rows_become_businesses_keyed_by_ein_with_the_care_of_name_as_a_role() -> None:
    rows = read_rows(CSV.encode())
    assert [r["EIN"] for r in rows] == ["010631747", "020000001", "12"]
    out = [(r.table, dict(r.row)) for r in IRSExemptOrgs().normalize(_fetched(rows))]
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    assert set(biz) == {"EIN:010631747", "EIN:020000001"}  # the bad EIN is skipped
    legion = biz["EIN:010631747"]
    assert legion["status"] == "unconditional exemption"
    assert legion["status_date"] == legion["valid_from"] == date(1946, 3, 1)
    assert legion["jurisdiction"] == "56"  # Wyoming
    park = biz["EIN:020000001"]
    assert park["status"] == "conditional exemption" and park["org_form"] == "INC"
    assert park["status_date"] is None and park["valid_from"] == AT.date()  # future ruling
    (role,) = [r for t, r in out if t == "business_role"]
    assert (role["sos_id"], role["role"], role["title"]) == ("EIN:010631747", "other",
                                                             "in care of")  # fmt: skip
    (party,) = [r for t, r in out if t == "party"]
    assert party["raw_name"] == "JANE DOE" and party["address_id"] == legion["principal_address_id"]
    zips = {r["zip5"] for t, r in out if t == "address"}
    assert zips == {"82001", "82601"}


def test_care_of_and_ruling_date_parsing() -> None:
    assert care_of("% JOHN SMITH") == "JOHN SMITH"
    assert care_of("C/O FIRST BANK TRUST DEPT") == "FIRST BANK TRUST DEPT"
    assert care_of("  ") is None
    assert ruling_date("000000") is None and ruling_date("201913") is None
    assert ruling_date("201907") == date(2019, 7, 1)


def test_pii_fields_are_scrubbed_and_cover_names_and_streets() -> None:
    assert set(IRSExemptOrgs.pii_fields) == {"ICO", "STREET"}
    body = canonical_json({"rows": read_rows(CSV.encode())})
    scrubbed = json.loads(IRSExemptOrgs.scrub_fixture(body))["rows"][0]
    assert scrubbed["ICO"].startswith("TESTOWNER") and scrubbed["STREET"].endswith(" TEST ST")
    assert scrubbed["NAME"] == "AMERICAN LEGION"  # organization names are kept


def test_recorded_fixture_is_pseudonymized() -> None:
    paths = sorted(FIXTURES.glob("*.json"))
    assert paths
    for path in paths:
        for r in json.loads(path.read_text())["rows"]:
            assert not r.get("ICO") or r["ICO"].startswith("TESTOWNER")
            assert not r.get("STREET") or r["STREET"].endswith(" TEST ST")


class _Fake:
    def __init__(self, pages: Mapping[str, bytes]) -> None:
        self.pages = pages
        self.urls: list[str] = []

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                 ) -> tuple[int, bytes, str]:  # fmt: skip
        self.urls.append(url)
        if url in self.pages:
            return 200, self.pages[url], "text/html"
        return 404, b"", "text/plain"


def _client(fake: _Fake) -> BulkClient:
    return BulkClient(transport=fake, sleep=lambda s: None, now=lambda: AT)


def test_partitions_are_the_state_files_and_limit_keeps_the_first_rows() -> None:
    from equity.adapters.federal.irs_eo import PAGE

    page = (b'<a href="/pub/irs-soi/eo_wy.csv">WY</a><a href="/pub/irs-soi/eo1.csv">r1</a>'
            b'<a href="https://www.irs.gov/pub/irs-soi/eo_ny.csv">NY</a>')  # fmt: skip
    fake = _Fake({PAGE: page, "https://www.irs.gov/pub/irs-soi/eo_wy.csv": CSV.encode()})
    adapter = IRSExemptOrgs(_client(fake))
    assert list(adapter.partitions()) == [{"state": "ny"}, {"state": "wy"}]
    fetched = adapter.fetch(FetchRequest({"state": "WY", "limit": "1"}))
    rows = json.loads(fetched.content)["rows"]
    assert [r["EIN"] for r in rows] == ["010631747"]
    assert fetched.request.endswith("/eo_wy.csv")


def test_recorded_fixture_passes_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(IRSExemptOrgs, sorted(FIXTURES.glob("*.json")), empty_db)
