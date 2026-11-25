"""SEC EDGAR bulk submissions (equity.adapters.federal.sec_submissions)."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.bulk_files import BulkClient
from equity.adapters.federal.sec_submissions import (
    URL,
    SECSubmissions,
    _Window,
    data_end,
    filer,
    is_company,
    members,
)
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters" / SECSubmissions.source_id


def _addr(street: str, city: str, st: str, zip5: str) -> dict[str, Any]:
    return {"street1": street, "street2": None, "city": city, "stateOrCountry": st,
            "zipCode": zip5, "stateOrCountryDescription": st, "isForeignLocation": 0}  # fmt: skip


COMPANY = {
    "cik": "0000005270", "entityType": "other", "sic": "6211", "name": "PINEBRIDGE SECURITIES LLC",
    "ein": "132701087", "phone": "(917) 938-4780", "stateOfIncorporation": "DE",
    "formerNames": [{"name": "AIG EQUITY SALES CORP.", "from": "2002-03-01", "to": "2009-04-01"}],
    "addresses": {"business": _addr("65 EAST 55TH STREET", "NEW YORK", "NY", "10022"),
                  "mailing": _addr("PO BOX 1", "NEW YORK", "NY", "10022")},
    "filings": {"recent": {"filingDate": ["2026-10-01", "2025-01-02"], "form": ["4", "4"]}},
}  # fmt: skip
INSIDER = {
    "cik": "0001209180", "entityType": "other", "sic": "", "name": "LEE ANN Q",
    "insiderTransactionForOwnerExists": 1, "ein": None,
    "addresses": {"business": _addr("1 MAIN ST", "MALTA", "NY", "12020"),
                  "mailing": _addr("2 ELM ST", "MALTA", "NY", "12020")},
    "filings": {"recent": {"filingDate": []}},
}  # fmt: skip
FOREIGN = {
    "cik": "77", "entityType": "other", "name": "OVERSEAS TRUST FUND",
    "addresses": {"business": {"street1": "AV. 4040", "city": "SANTIAGO",
                               "stateOrCountry": "F3", "isForeignLocation": 1}},
}  # fmt: skip


def _zip(docs: list[dict[str, Any]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in docs:
            zf.writestr(f"CIK{int(d['cik']):010d}.json", json.dumps(d))
        zf.writestr("CIK0000005270-submissions-001.json", json.dumps({"filingDate": []}))
    return buf.getvalue()


class _Server:
    """Serves one file with byte ranges (suffix ranges too)."""

    def __init__(self, data: bytes) -> None:
        self.data, self.ranges = data, 0

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                 ) -> tuple[int, bytes, str]:  # fmt: skip
        if url.endswith("/robots.txt"):
            return 200, b"User-agent: *\nDisallow: /cgi-bin/\n", "text/plain"
        assert url == URL and "@" not in headers["User-Agent"]
        rng = headers["Range"].removeprefix("bytes=")
        self.ranges += 1
        if rng.startswith("-"):
            return 206, self.data[-int(rng[1:]) :], "application/zip"
        a, b = (int(x) for x in rng.split("-"))
        return 206, self.data[a : b + 1], "application/zip"


def _client(server: _Server) -> BulkClient:
    return BulkClient(transport=server, sleep=lambda s: None, now=lambda: AT)


def test_members_are_walked_from_any_window_start() -> None:
    data = _zip([COMPANY, INSIDER, FOREIGN])
    end = data_end(data[-65536:])
    window = _Window(_client(_Server(data)), URL, end, 64)
    names = [n for n, _ in members(window, 0, end)]
    assert names == ["CIK0000005270.json", "CIK0001209180.json", "CIK0000000077.json",
                     "CIK0000005270-submissions-001.json"]  # fmt: skip
    second = data.find(b"PK\x03\x04", 1)
    # A window starting inside the first member begins at the next header; windows
    # [0, second + 1) and [second + 1, end) together read every member once.
    first_half = [n for n, _ in members(_Window(_client(_Server(data)), URL, end, 64), 0,
                                        second + 1)]  # fmt: skip
    rest = [n for n, _ in members(_Window(_client(_Server(data)), URL, end, 64), second + 1,
                                  end)]  # fmt: skip
    assert first_half + rest == names and first_half == names[:2]


def test_filer_keeps_the_kept_keys_and_latest_filing() -> None:
    f = filer(COMPANY)
    assert "phone" not in f and "filings" not in f and f["lastFiled"] == "2026-10-01"
    assert f["addresses"]["business"]["street1"] == "65 EAST 55TH STREET"
    assert "street2" not in f["addresses"]["business"]
    assert is_company(f) and not is_company(filer(INSIDER))


def test_companies_are_businesses_and_individual_filers_parties() -> None:
    body = {"filers": [filer(d) for d in (COMPANY, INSIDER, FOREIGN)]}
    fetched = Fetched(SECSubmissions.source_id, URL, AT, 200, canonical_json(body),
                      "application/json")  # fmt: skip
    out = [(r.table, dict(r.row)) for r in SECSubmissions().normalize(fetched)]
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    assert set(biz) == {"CIK:0000005270", "CIK:0000000077"}
    pine = biz["CIK:0000005270"]
    assert pine["jurisdiction"] == "36" and pine["valid_from"] == AT.date()
    addrs = {r["address_id"]: r for t, r in out if t == "address"}
    assert addrs[pine["principal_address_id"]]["line1"] == "65 EAST 55TH STREET"
    assert addrs[pine["mailing_address_id"]]["line1"] == "PO BOX 1"
    assert biz["CIK:0000000077"]["principal_address_id"] is None
    parties = [r for t, r in out if t == "party"]
    assert [p["raw_name"] for p in parties if p["record_key"] == "0000005270"] == [
        "AIG EQUITY SALES CORP."
    ]
    lee = [p for p in parties if p["record_key"] == "0001209180"]
    assert len(lee) == 2  # at the mailing and the business address
    assert {(p["party_kind"], p["last_name"], p["first_name"], p["middle"]) for p in lee} == {
        ("person", "LEE", "ANN", "Q")
    }


def test_partitions_and_limited_fetch() -> None:
    data = _zip([COMPANY, INSIDER, FOREIGN])
    server = _Server(data)
    adapter = SECSubmissions(_client(server))
    parts = list(adapter.partitions())
    assert parts == [{"lo": "0", "hi": str(data_end(data[-65536:]))}]
    body = json.loads(adapter.fetch(FetchRequest({**parts[0], "limit": "2"})).content)
    assert [f["cik"] for f in body["filers"]] == ["0000005270", "0001209180"]
    body = json.loads(adapter.fetch(FetchRequest(parts[0])).content)
    assert len(body["filers"]) == 3  # the -submissions-001 member is skipped
    with pytest.raises(ValueError, match="bad window"):
        adapter.fetch(FetchRequest({"lo": "5", "hi": "5"}))


def test_scrub_and_recorded_fixture_are_pseudonymized() -> None:
    (f,) = json.loads(SECSubmissions.scrub_fixture(canonical_json(
        {"filers": [filer(COMPANY)]})))["filers"]  # fmt: skip
    assert f["name"].startswith("TESTOWNER") and f["name"].endswith(" LLC")
    assert f["formerNames"][0]["name"].startswith("TESTOWNER")
    assert f["addresses"]["business"]["street1"].endswith(" TEST ST")
    assert f["cik"].startswith("99") and "ein" not in f
    paths = sorted(FIXTURES.glob("*.json"))
    assert paths
    for path in paths:
        for f in json.loads(path.read_text())["filers"]:
            assert f["cik"].startswith("99") and "ein" not in f
            assert f["name"].startswith("TESTOWNER")
            for a in f.get("addresses", {}).values():
                for k in ("street1", "street2"):
                    assert not a.get(k) or a[k].endswith(" TEST ST")


def test_recorded_fixture_passes_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(SECSubmissions, sorted(FIXTURES.glob("*.json")), empty_db)
