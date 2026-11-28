"""FDA drug establishment registrations (equity.adapters.federal.fda)."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.fda import (
    URL,
    FDADrugEstablishments,
    agent_name,
    read_rows,
    split_address,
    us_address,
)
from equity.adapters.http import PoliteClient
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 25, tzinfo=UTC)
FIXTURES = Path(__file__).parents[1] / "fixtures" / "adapters" / FDADrugEstablishments.source_id
HEAD = ("FEI_NUMBER", "DUNS_NUMBER", "FIRM_NAME", "ADDRESS", "EXPIRATION_DATE", "OPERATIONS",
        "ESTABLISHMENT_CONTACT_NAME", "ESTABLISHMENT_CONTACT_EMAIL", "AGENT_DETAILS",
        "REGISTRANT_NAME", "REGISTRANT_DUNS", "REGISTRANT_CONTACT_NAME",
        "REGISTRANT_CONTACT_EMAIL", "EXCLUSION_FLAG")  # fmt: skip
ROWS = [
    ("0000000360", "271408412", "DSP", "RUE DES GRANDS NAVOIRS, CHAUNY F-02300, France (FRA)",
     "12/31/2027", "API MANUFACTURE", "Sylvie Roe", "sr@example.com",
     "139242874 - Registrar Corp - drugs@example.com - 1-757-224-0177", "DSP", "271408412",
     "David Doe", "drugs@example.com", "N"),
    ("0001014492", "039106281", "Tyson Foods, Inc",
     "233 S. Secrest Ave, Monroe, North Carolina (NC) 28112, United States (USA)", "12/31/2026",
     "MEDICATED ANIMAL FEED MANUFACTURE", "Rocky Roe", "rr@example.com", "", "Tyson Chicken, Inc",
     "057061806", "Branda Doe", "bd@example.com", "N"),
]  # fmt: skip


def _zip() -> bytes:
    body = "\r\n".join(" " + " \t ".join(r) + " " for r in (HEAD, *ROWS)) + "\r\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("drls_reg.txt", body.encode("latin-1"))
        zf.writestr("drls_reg.xls", b"not read")
    return buf.getvalue()


def test_rows_drop_emails_and_split_the_address() -> None:
    rows = read_rows(_zip())
    assert len(rows) == 2 and not any("EMAIL" in k for r in rows for k in r)
    assert rows[0]["AGENT_DETAILS"] == "Registrar Corp" and "ADDRESS" not in rows[0]
    assert rows[1]["STREET"] == "233 S. Secrest Ave"
    assert rows[1]["LOCALITY"] == "Monroe, North Carolina (NC) 28112, United States (USA)"
    assert split_address("1 Rue X, Paris, France (FRA)") == {
        "STREET": "1 Rue X, Paris, France (FRA)"
    }
    a = us_address(rows[1])
    assert a is not None and (a["city"], a["state"], a["zip5"]) == ("MONROE", "NC", "28112")
    assert us_address(rows[0]) is None
    assert agent_name("1 - A - B Co - x@y.z - 555-0100") == "A - B Co" and agent_name("") is None


def test_establishments_become_businesses_with_contacts() -> None:
    fetched = Fetched(FDADrugEstablishments.source_id, URL, AT, 200,
                      canonical_json({"rows": read_rows(_zip())}), "application/json")  # fmt: skip
    out = [(r.table, dict(r.row)) for r in FDADrugEstablishments().normalize(fetched)]
    biz = {r["sos_id"]: r for t, r in out if t == "business"}
    assert set(biz) == {"FEI:0000000360", "FEI:0001014492"}
    tyson = biz["FEI:0001014492"]
    assert (tyson["status"], tyson["jurisdiction"], tyson["valid_from"]) == ("registered", "37",
                                                                            AT.date())  # fmt: skip
    assert biz["FEI:0000000360"]["principal_address_id"] is None
    parties = {r["party_id"]: r for t, r in out if t == "party"}
    roles = sorted((r["sos_id"], r["title"], parties[r["party_id"]]["raw_name"])
                   for t, r in out if t == "business_role")  # fmt: skip
    assert ("FEI:0000000360", "US AGENT", "Registrar Corp") in roles
    assert ("FEI:0001014492", "ESTABLISHMENT CONTACT", "Rocky Roe") in roles
    roe = next(p for p in parties.values() if p["raw_name"] == "Rocky Roe")
    assert roe["party_kind"] == "person"


def test_fetch_samples_us_establishments_first() -> None:
    def transport(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("/robots.txt"):
            return 200, b"User-agent: *\nDisallow: /scripts/\n", "text/plain"
        return 200, _zip(), "application/zip"

    adapter = FDADrugEstablishments(PoliteClient(transport=transport, sleep=lambda s: None,
                                                 now=lambda: AT))  # fmt: skip
    assert list(adapter.partitions()) == [{"file": "drls_reg"}]
    body = json.loads(adapter.fetch(FetchRequest({"limit": "1"})).content)
    assert [r["FEI_NUMBER"] for r in body["rows"]] == ["0001014492"]
    with pytest.raises(ValueError, match="bad file"):
        adapter.fetch(FetchRequest({"file": "drls_excluded"}))


def test_recorded_fixture_is_pseudonymized() -> None:
    paths = sorted(FIXTURES.glob("*.json"))
    assert paths
    for path in paths:
        for r in json.loads(path.read_text())["rows"]:
            for k in FDADrugEstablishments.pii_fields:
                v = r.get(k)
                assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), k
            assert not any("EMAIL" in k for k in r)


def test_recorded_fixture_passes_the_adapter_contract(empty_db) -> None:  # type: ignore[no-untyped-def]
    from ..test_adapter_contract import check_contract

    check_contract(FDADrugEstablishments, sorted(FIXTURES.glob("*.json")), empty_db)
