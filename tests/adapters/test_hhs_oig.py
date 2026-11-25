"""HHS OIG LEIE exclusions (equity.adapters.federal.hhs_oig)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.hhs_oig import URL, HHSOIGExclusions, npi, read_rows
from equity.adapters.http import PoliteClient
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters" / HHSOIGExclusions.source_id
CSV = (
    "LASTNAME,FIRSTNAME,MIDNAME,BUSNAME,GENERAL,SPECIALTY,UPIN,NPI,DOB,ADDRESS,CITY,STATE,ZIP,"
    "EXCLTYPE,EXCLDATE,REINDATE,WAIVERDATE,WVRSTATE\n"
    ',,,"ACME PHARMACY, INC",PHARMACY,,,1234567893,,1 MAIN ST,BROOKLYN,NY,11235,1128a1,'
    "20200319,0,0,\n"
    "SMITH,JOHN,A,,NURSING,NURSE,,0,19600101,2 ELM ST,BUTTE,MT,59701,1128b4,20991231,0,0,\n"
    "DOE,JANE,,DOE HOME CARE LLC,HOME HEALTH,,,0,,3 OAK AVE,ORLANDO,FL,32803,1128a1,20020919,"
    "0,0,\n"
    "SMITH,JOHN,A,,NURSING,NURSE,,0,19600101,2 ELM ST,BUTTE,MT,59701,1128b4,20991231,0,0,\n"
)


def _fetched(rows: list[dict[str, str]]) -> Fetched:
    return Fetched(HHSOIGExclusions.source_id, URL, AT, 200, canonical_json({"rows": rows}),
                   "application/json")  # fmt: skip


def test_companies_become_excluded_businesses_and_individuals_parties() -> None:
    out = [(r.table, dict(r.row)) for r in HHSOIGExclusions().normalize(
        _fetched(read_rows(CSV.encode())))]  # fmt: skip
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    assert len(biz) == 2 and "NPI:1234567893" in biz
    acme = biz["NPI:1234567893"]
    assert (acme["status"], acme["status_date"], acme["valid_from"], acme["jurisdiction"]) == (
        "excluded",
        date(2020, 3, 19),
        date(2020, 3, 19),
        "36",
    )
    doe = next(r for s, r in biz.items() if s.startswith("LEIE:"))
    assert doe["name"] == "DOE HOME CARE LLC" and doe["org_form"] == "LLC"
    roles = [r for t, r in out if t == "business_role"]
    assert [(r["role"], r["title"]) for r in roles] == [("other", "EXCLUDED INDIVIDUAL")]
    people = [r for t, r in out if t == "party" and r["party_kind"] == "person"]
    smith = [p for p in people if p["last_name"] == "SMITH"]
    # Two identical rows stay two records (numbered keys), each naming the person once.
    assert len(smith) == 2 and {p["record_key"] for p in smith} != {smith[0]["record_key"]}
    assert (smith[0]["first_name"], smith[0]["middle"]) == ("JOHN", "A")
    addrs = {r["address_id"]: r for t, r in out if t == "address"}
    assert addrs[smith[0]["address_id"]]["zip5"] == "59701"
    assert len([t for t, _ in out if t == "source_record"]) == 4


def test_helpers_and_step_sampling() -> None:
    assert npi("1234567893") == "1234567893" and npi("0") is None and npi(None) is None
    rows = read_rows(CSV.encode(), limit=2, step=2)
    assert [r.get("LASTNAME") for r in rows] == [None, "DOE"]
    assert "DOB" in read_rows(CSV.encode())[1]
    with pytest.raises(RuntimeError, match="not an LEIE file"):
        read_rows(b"a,b\n1,2\n")


def test_scrub_hides_names_streets_and_identifiers() -> None:
    (a, s) = json.loads(HHSOIGExclusions.scrub_fixture(canonical_json(
        {"rows": read_rows(CSV.encode(), limit=2)})))["rows"]  # fmt: skip
    assert a["BUSNAME"].startswith("TESTOWNER") and a["BUSNAME"].endswith(" INC")
    assert a["ADDRESS"].endswith(" TEST ST") and a["NPI"].startswith("0")
    assert s["LASTNAME"].startswith("TESTOWNER") and s["DOB"] == "19000101"


def test_recorded_fixture_is_pseudonymized() -> None:
    paths = sorted(FIXTURES.glob("*.json"))
    assert paths
    for path in paths:
        for r in json.loads(path.read_text())["rows"]:
            for k in HHSOIGExclusions.pii_fields:
                v = r.get(k)
                assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k
            assert r.get("DOB") in (None, "19000101")
            assert r.get("NPI") in (None, "0") or r["NPI"].startswith("0")


def test_fetch_reads_the_whole_file() -> None:
    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("/robots.txt"):
            return 404, b"", "text/html"
        assert url == URL
        return 200, CSV.encode(), "text/csv"

    adapter = HHSOIGExclusions(PoliteClient(transport=transport, sleep=lambda s: None,
                                            now=lambda: AT))  # fmt: skip
    assert list(adapter.partitions()) == [{"file": "updated"}]
    body = json.loads(adapter.fetch(FetchRequest({"file": "updated", "limit": "1"})).content)
    assert len(body["rows"]) == 1 and body["url"] == URL
    with pytest.raises(ValueError, match="bad file"):
        adapter.fetch(FetchRequest({"file": "supplement"}))


def test_recorded_fixture_passes_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(HHSOIGExclusions, sorted(FIXTURES.glob("*.json")), empty_db)
