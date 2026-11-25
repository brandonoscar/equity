"""Treasury OFAC sanctions lists (equity.adapters.federal.ofac)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.ofac import (
    ADDRESS,
    ALIAS,
    EXPORTS,
    OFACSDN,
    PRIMARY,
    OFACConsolidated,
    join,
    read_csv,
    us_address,
)
from equity.adapters.http import PoliteClient
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
ROOT = Path(__file__).parents[1] / "fixtures" / "adapters"
SDN = (
    b'10,"ROE, Richard Q.","individual","SDGT",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,"DOB 1960."\r\n'
    b'20,"ACME TRADING LLC",-0- ,"IRAN",-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- ,-0- \r\n'
    b'30,"SEA STAR","vessel","IRAN",-0- ,"9XYZ","Tanker",-0- ,-0- ,"Iran","OCEAN SHIPPING CO",'
    b"-0- \r\n\x1a"
)
ADD = (
    b'10,1,"1 Main St","Richardson, TX 75081","United States",-0- \r\n'
    b'10,2,"PO Box 9","Paterson, NJ 07503","United States",-0- \r\n'
    b'20,3,"Ibex House","London EC3N 1DY","United Kingdom",-0- \r\n'
)
ALT = b'10,7,"aka","ROE, Dick",-0- \r\n20,8,"fka","ACME IMPORTS LTD",-0- \r\n'


def _entries() -> list[dict[str, object]]:
    return join(read_csv(SDN, PRIMARY), read_csv(ADD, ADDRESS), read_csv(ALT, ALIAS))


def _fetched(entries: list[dict[str, object]]) -> Fetched:
    return Fetched(OFACSDN.source_id, f"{EXPORTS}/SDN.CSV", AT, 200,
                   canonical_json({"entries": entries}), "application/json")  # fmt: skip


def test_csv_reading_and_join() -> None:
    entries = _entries()
    assert [e["ent_num"] for e in entries] == ["10", "20", "30"]
    roe = entries[0]
    assert "title" not in roe and roe["type"] == "individual"
    assert len(roe["addresses"]) == 2 and roe["aliases"][0]["alt_name"] == "ROE, Dick"  # type: ignore[index]
    a = us_address({"address": "1 Main St", "city_state_zip": "Richardson, TX 75081",
                    "country": "United States"})  # fmt: skip
    assert a is not None and (a["city"], a["state"], a["zip5"]) == ("RICHARDSON", "TX", "75081")
    assert us_address({"address": "Ibex House", "country": "United Kingdom"}) is None


def test_entries_become_parties_at_us_addresses() -> None:
    out = [(r.table, dict(r.row)) for r in OFACSDN().normalize(_fetched(_entries()))]
    parties = [r for t, r in out if t == "party"]
    roe = [p for p in parties if p["record_key"] == "10"]
    # Two names (the entry and its alias) x two U.S. addresses.
    assert (
        len(roe) == 4
        and {p["address_id"] for p in roe} - {None}
        and all(p["address_id"] for p in roe)
    )
    main = next(p for p in roe if p["raw_name"] == "ROE, Richard Q.")
    assert (main["party_kind"], main["last_name"], main["first_name"], main["middle"]) == (
        "person",
        "ROE",
        "Richard",
        "Q.",
    )
    assert main["jurisdiction"] == "48"  # the first U.S. address: Texas
    acme = [p for p in parties if p["record_key"] == "20"]
    assert {p["raw_name"] for p in acme} == {"ACME TRADING LLC", "ACME IMPORTS LTD"}
    assert all(p["address_id"] is None and p["party_kind"] == "org" for p in acme)
    vessel = [p for p in parties if p["record_key"] == "30"]
    assert [p["raw_name"] for p in vessel] == ["OCEAN SHIPPING CO"]  # the owner, not the ship
    assert len([t for t, _ in out if t == "source_record"]) == 3


def test_fetch_joins_the_three_files_and_samples_us_entries_first() -> None:
    files = {"SDN.CSV": SDN, "ADD.CSV": ADD, "ALT.CSV": ALT}

    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("/robots.txt"):
            return 404, b"", "text/html"
        return 200, files[url.rsplit("/", 1)[-1]], "text/csv"

    adapter = OFACSDN(PoliteClient(transport=transport, sleep=lambda s: None, now=lambda: AT))
    assert list(adapter.partitions()) == [{"list": "all"}]
    body = json.loads(adapter.fetch(FetchRequest({"list": "all", "limit": "1"})).content)
    assert [e["ent_num"] for e in body["entries"]] == ["10"]
    with pytest.raises(ValueError, match="bad list"):
        adapter.fetch(FetchRequest({"list": "sdn"}))
    assert OFACConsolidated.files[0] == "CONS_PRIM.CSV"


def test_scrub_and_recorded_fixtures_are_pseudonymized() -> None:
    (e, *_) = json.loads(OFACSDN.scrub_fixture(canonical_json({"entries": _entries()})))[
        "entries"]  # fmt: skip
    assert e["name"].startswith("TESTOWNER") and e["remarks"].startswith("TESTOWNER")
    assert e["addresses"][0]["address"].endswith(" TEST ST")
    assert e["aliases"][0]["alt_name"].startswith("TESTOWNER")
    for cls in (OFACSDN, OFACConsolidated):
        paths = sorted((ROOT / cls.source_id).glob("*.json"))
        assert paths, cls.source_id
        for path in paths:
            for entry in json.loads(path.read_text())["entries"]:
                for row in (entry, *entry["addresses"], *entry["aliases"]):
                    for k in cls.pii_fields:
                        v = row.get(k)
                        assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k


@pytest.mark.parametrize("cls", [OFACSDN, OFACConsolidated])
def test_recorded_fixtures_pass_the_adapter_contract(cls: type, empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(cls, sorted((ROOT / cls.source_id).glob("*.json")), empty_db)  # type: ignore[attr-defined]
