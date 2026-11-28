"""CMS opt-out affidavits and revoked providers (equity.adapters.federal.cms_lists)."""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.cms_lists import PAGE, CMSOptOutAffidavits, CMSRevokedProviders
from equity.adapters.http import PoliteClient
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
ROOT = Path(__file__).parents[1] / "fixtures" / "adapters"
OPT_OUT = {"First Name": "Aileen", "Last Name": "Peters", "NPI": "1396226163",
           "Specialty": "Clinical Psychologist", "Optout Effective Date": "2024-10-24",
           "First Line Street Address": "226 MASSACHUSETTS AVE", "Second Line Street Address": "",
           "City Name": "ARLINGTON", "State Code": "MA", "Zip Code": "024748435"}  # fmt: skip
REVOKED_PERSON = {"ENRLMT_ID": "I1", "NPI": "1801839063", "FIRST_NAME": "MARGARET",
                  "MDL_NAME": "L", "LAST_NAME": "KEITH", "ORG_NAME": "", "STATE_CD": "FL",
                  "REVOCATION_EFCTV_DT": "2025-05-20"}  # fmt: skip
REVOKED_ORG = {"ENRLMT_ID": "O2", "NPI": "1234567893", "ORG_NAME": "ACME DME LLC",
               "STATE_CD": "TX", "REVOCATION_EFCTV_DT": "2099-01-01"}  # fmt: skip


def _out(cls: Any, rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    fetched = Fetched(cls.source_id, cls().url, AT, 200, canonical_json({"rows": rows}),
                      "application/json")  # fmt: skip
    return [(r.table, dict(r.row)) for r in cls().normalize(fetched)]


def test_opt_outs_are_people_at_their_practice_address() -> None:
    out = _out(CMSOptOutAffidavits, [OPT_OUT, OPT_OUT, {"NPI": "1"}])
    (p,) = [r for t, r in out if t == "party"]
    assert (p["party_kind"], p["first_name"], p["last_name"], p["jurisdiction"]) == (
        "person",
        "Aileen",
        "Peters",
        "25",
    )
    (a,) = [r for t, r in out if t == "address"]
    assert (a["address_id"], a["zip5"], a["line1"]) == (p["address_id"], "02474",
                                                        "226 MASSACHUSETTS AVE")  # fmt: skip


def test_revocations_name_people_and_organizations() -> None:
    out = _out(CMSRevokedProviders, [REVOKED_PERSON, REVOKED_ORG])
    (biz,) = [r for t, r in out if t == "business"]
    assert (biz["sos_id"], biz["status"], biz["status_date"], biz["valid_from"]) == (
        "NPI:1234567893",
        "revoked",
        None,
        AT.date(),
    )  # a future date is not a fact yet
    (p,) = [r for t, r in out if t == "party"]
    assert (p["raw_name"], p["party_kind"], p["middle"], p["address_id"]) == (
        "MARGARET L KEITH",
        "person",
        "L",
        None,
    )


class _API:
    def __init__(self, n: int) -> None:
        self.n = n

    def __call__(self, url: str, headers: Mapping[str, str], timeout: float
                 ) -> tuple[int, bytes, str]:  # fmt: skip
        base, _, qs = url.partition("?")
        if base.endswith("/robots.txt"):
            return 200, b"User-agent: *\nDisallow: /admin/\n", "text/plain"
        q = dict(urllib.parse.parse_qsl(qs))
        off, size = int(q["offset"]), int(q["size"])
        rows = [{**OPT_OUT, "NPI": str(i)} for i in range(off, min(off + size, self.n))]
        return 200, json.dumps(rows).encode(), "application/json"


def test_fetch_pages_until_a_short_page() -> None:
    adapter = CMSOptOutAffidavits(PoliteClient(transport=_API(PAGE + 3), sleep=lambda s: None,
                                               now=lambda: AT))  # fmt: skip
    assert list(adapter.partitions()) == [{"release": "latest"}]
    body = json.loads(adapter.fetch(FetchRequest({"release": "latest"})).content)
    assert len(body["rows"]) == PAGE + 3
    assert "Second Line Street Address" not in body["rows"][0]  # empty cells dropped
    body = json.loads(adapter.fetch(FetchRequest({"offset": "7", "limit": "2"})).content)
    assert [r["NPI"] for r in body["rows"]] == ["7", "8"]
    with pytest.raises(ValueError, match="bad release"):
        adapter.fetch(FetchRequest({"release": "2026-10"}))


@pytest.mark.parametrize("cls", [CMSOptOutAffidavits, CMSRevokedProviders])
def test_scrub_and_recorded_fixtures_are_pseudonymized(cls: Any) -> None:
    (r,) = json.loads(cls.scrub_fixture(canonical_json({"rows": [
        OPT_OUT if cls is CMSOptOutAffidavits else REVOKED_PERSON]})))["rows"]  # fmt: skip
    assert r["NPI"].startswith("0")
    paths = sorted((ROOT / cls.source_id).glob("*.json"))
    assert paths
    for path in paths:
        for row in json.loads(path.read_text())["rows"]:
            for k in cls.pii_fields:
                v = row.get(k)
                assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k
            assert row["NPI"].startswith("0")


@pytest.mark.parametrize("cls", [CMSOptOutAffidavits, CMSRevokedProviders])
def test_recorded_fixtures_pass_the_adapter_contract(cls: type, empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(cls, sorted((ROOT / cls.source_id).glob("*.json")), empty_db)  # type: ignore[attr-defined]
