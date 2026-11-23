"""State business registries (config/business/*.yaml): layouts, roles, planning. Offline."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.business_registry import (
    BUSINESS_DIR,
    AddressSpec,
    NameSpec,
    address_of,
    all_registry_adapters,
    holder_name,
    load_registry,
)
from equity.adapters.http import Response
from equity.adapters.registry import by_source_id
from equity.adapters.rows import canonical_json

FIX = Path(__file__).parents[1] / "fixtures" / "adapters"
AT = datetime(2026, 11, 16, tzinfo=UTC)


def _norm(source_id: str, body: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    f = Fetched(source_id, "https://x.test", AT, 200, canonical_json(body), "")
    return [(r.table, dict(r.row)) for r in by_source_id(source_id)().normalize(f)]  # type: ignore[abstract]


def _fixture(source_id: str) -> list[tuple[str, dict[str, Any]]]:
    path = next((FIX / source_id).resolve().glob("*.json"))
    f = Fetched(source_id, path.as_uri(), AT, 200, path.read_bytes(), "")
    return [(r.table, dict(r.row)) for r in by_source_id(source_id)().normalize(f)]  # type: ignore[abstract]


def test_every_config_loads_and_registers() -> None:
    ids = {c.source_id for c in all_registry_adapters()}
    assert ids == {"ny.sos.business", "co.sos.business", "ct.sos.business", "or.sos.business",
                   "pa.dos.business"}  # fmt: skip
    for path in BUSINESS_DIR.glob("*.yaml"):
        assert load_registry(path).pii_fields


def test_unknown_roles_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown business role"):
        NameSpec.parse({"role": "owner"})
    bad = (BUSINESS_DIR / "ct.yaml").read_text().replace("Director: director", "Director: boss")
    (tmp_path / "x.yaml").write_text(bad)
    with pytest.raises(ValueError, match="boss"):
        load_registry(tmp_path / "x.yaml")


def test_names_and_addresses() -> None:
    spec = NameSpec("registered_agent", org="org", name_parts=("f", "m", "l"))
    assert holder_name({"org": " ACME  LLC ", "f": "A"}, spec) == "ACME LLC"
    assert holder_name({"f": "ANN", "l": "LEE"}, spec) == "ANN LEE"
    assert holder_name({}, spec) is None
    assert holder_name({"n": "X Y", "org": "Z"}, NameSpec("other", name="n", org="org")) == "X Y"
    a = AddressSpec(("s1", "s2"), "c", "st", "z")
    row = {"s1": "1 MAIN ST", "s2": "STE 2", "c": "Denver", "st": "CO", "z": "80202-1234"}
    addr = address_of(row, a)
    assert addr is not None and addr["zip5"] == "80202" and addr["line1"] == "1 MAIN ST STE 2"
    assert address_of({"z": "8020"}, a) is None and address_of(row, None) is None


def test_ny_inline_roles_and_constant_status() -> None:
    rows = _fixture("ny.sos.business")
    biz = [r for t, r in rows if t == "business"]
    assert biz and all(b["status"] == "Active" for b in biz)
    roles = Counter((r["role"], r["title"]) for t, r in rows if t == "business_role")
    assert roles[("other", "DOS PROCESS")] > 0


def test_co_agents() -> None:
    rows = _fixture("co.sos.business")
    t = Counter(table for table, _ in rows)
    assert t["business"] == t["source_record"] > 0
    assert {r["role"] for tb, r in rows if tb == "business_role"} == {"registered_agent"}


def test_ct_role_datasets() -> None:
    rows = _fixture("ct.sos.business")
    roles = Counter(r["role"] for t, r in rows if t == "business_role")
    assert roles["registered_agent"] > 0 and sum(roles.values()) > roles["registered_agent"]


def test_or_grouped_rows_become_one_business() -> None:
    body = {"entities": [
        {"registry_number": "9", "business_name": "ACME LLC", "registry_date": "2001-02-03",
         "associated_name_type": "PRINCIPAL PLACE OF BUSINESS", "address": "1 A ST",
         "city": "SALEM", "state": "OR", "zip": "97301"},
        {"registry_number": "9", "business_name": "ACME LLC", "registry_date": "2001-02-03",
         "associated_name_type": "REGISTERED AGENT", "first_name": "ANN", "middle_name": "Q",
         "last_name": "LEE",
         "address": "2 B ST", "city": "SALEM", "state": "OR", "zip": "97301"},
        {"registry_number": "9", "business_name": "ACME LLC", "registry_date": "2001-02-03",
         "associated_name_type": "AUTHORIZED REPRESENTATIVE",
         "entity_of_record_name": "AGENTS INC"},
        {"registry_number": "9", "business_name": "ACME LLC",
         "associated_name_type": "SOMETHING NEW", "first_name": "IGNORED"},
    ]}  # fmt: skip
    rows = _norm("or.sos.business", body)
    biz = [r for t, r in rows if t == "business"]
    assert len(biz) == 1 and biz[0]["org_form"] == "LLC"
    assert biz[0]["principal_address_id"] is not None and biz[0]["mailing_address_id"] is None
    roles = sorted((r["role"], r["title"]) for t, r in rows if t == "business_role")
    assert roles == [
        ("other", "AUTHORIZED REPRESENTATIVE"),
        ("registered_agent", "REGISTERED AGENT"),
    ]
    names = {r["raw_name"]: r for t, r in rows if t == "party"}
    assert set(names) == {"ANN Q LEE", "AGENTS INC"}
    ann, org = names["ANN Q LEE"], names["AGENTS INC"]
    assert (ann["first_name"], ann["middle"], ann["last_name"], ann["suffix"]) == (
        "ANN",
        "Q",
        "LEE",
        None,
    )  # name parts are kept
    assert org["last_name"] is None and org["middle"] is None  # an organization has none
    assert all(r["valid_from"].isoformat() == "2001-02-03" for t, r in rows if t == "business_role")


def test_dates_duplicates_and_missing_names() -> None:
    future = {"entities": [
        {"entityid": "1", "entityname": "X INC", "entityformdate": "2099-01-01T00:00:00.000",
         "agentfirstname": "A", "agentlastname": "B"},
        {"entityid": "2", "entityname": None}]}  # fmt: skip
    rows = _norm("co.sos.business", future)
    b = next(r for t, r in rows if t == "business")
    assert b["formed_on"] is None and b["valid_from"] == AT.date()
    assert next(r for t, r in rows if t == "data_issue")["issue_code"] == "missing_entity_name"
    dup = {"entities": [{"dos_id": "5", "current_entity_name": "Y LLC",
                         "registered_agent_name": "Z", "dos_process_name": "Z"}]}  # fmt: skip
    roles = [r["role"] for t, r in _norm("ny.sos.business", dup) if t == "business_role"]
    assert sorted(roles) == ["other", "registered_agent"]  # same person, two roles: both kept


class FakeSocrata:
    retries = 0
    backoff_s = 0.0

    def __init__(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self.data = data
        self.queries: list[tuple[str, dict[str, str]]] = []

    def sleep(self, s: float) -> None:
        pass

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        ds = url.rsplit("/", 1)[-1].removesuffix(".json")
        p = dict(params or {})
        self.queries.append((ds, p))
        rows = self.data.get(ds, [])
        if p.get("$select", "").startswith("distinct"):
            w = p["$where"]
            last = w.split("> '")[1].rstrip("'") if "> '" in w else None
            keys = sorted({r["k"] for r in rows})
            keys = [k for k in keys if last is None or k > last][: int(p["$limit"])]
            rows = [{"k": k} for k in keys]
        else:
            off, lim = int(p.get("$offset", "0")), int(p.get("$limit", "50000"))
            rows = rows[off : off + lim]
        return Response(url, 200, json.dumps(rows).encode(), "application/json", AT)


def test_keyset_partitions(monkeypatch: pytest.MonkeyPatch) -> None:
    import equity.adapters.business_registry as br

    monkeypatch.setattr(br, "PLAN_KEYS", 2)
    cls = by_source_id("or.sos.business")
    fake = FakeSocrata({"tckn-sxa6": [{"k": k} for k in ("10", "11", "12", "20", "21")]})
    parts = list(cls(fake).partitions())  # type: ignore[call-arg]
    assert parts == [{"lo": "10", "hi": "12"}, {"lo": "12", "hi": "21"}, {"lo": "21", "hi": ""}]
    assert fake.queries[0][1]["$where"] == "registry_number IS NOT NULL"
    assert fake.queries[1][1]["$where"] == "registry_number > '11'"
    co = by_source_id("co.sos.business")
    fake = FakeSocrata({"4ykn-tg5h": []})
    assert list(co(fake).partitions()) == []  # type: ignore[call-arg]
    assert fake.queries[0][1]["$order"] == "entityid::text"  # distinct keys: no :id tiebreak


def test_fetch_ranges_and_limit_mode() -> None:
    cls = by_source_id("ct.sos.business")
    fake = FakeSocrata({"n7gp-d28j": [{"id": "A1", "name": "X"}, {"id": "A2", "name": "Y"}]})
    body = json.loads(cls(fake).fetch(FetchRequest({"lo": "A", "hi": "B"})).content)  # type: ignore[call-arg]
    wheres = [(ds, q["$where"]) for ds, q in fake.queries]
    assert wheres == [("n7gp-d28j", "id >= 'A' AND id < 'B'"),
                      ("ka36-64k6", "business_id >= 'A' AND business_id < 'B'"),
                      ("qh2m-n44y", "business_key >= 'A' AND business_key < 'B'")]  # fmt: skip
    assert len(body["entities"]) == 2
    fake = FakeSocrata({"n7gp-d28j": [{"id": "A1", "name": "X"}]})
    cls(fake).fetch(FetchRequest({"lo": "A", "limit": "1"}))  # type: ignore[call-arg]
    assert fake.queries[0][1]["$where"] == "id >= 'A'" and fake.queries[0][1]["$limit"] == "1"
    assert fake.queries[1][1]["$where"] == "business_id in ('A1')"


def test_health_and_source_row() -> None:
    cls = by_source_id("co.sos.business")
    ok = FakeSocrata({"4ykn-tg5h": [{"entityid": "1", "entityname": "X"}]})
    assert cls(ok).health().ok  # type: ignore[call-arg]
    assert not cls(FakeSocrata({})).health().ok  # type: ignore[call-arg]
    row = cls().source_row()  # type: ignore[abstract]
    assert row["kind"] == "sos" and row["jurisdiction"] == "08"


def test_pa_grouped_roles_are_case_insensitive_with_a_default() -> None:
    base = {"filing_number": "7", "business_name": "TEST LLC", "creationdate": "2010-05-06"}
    body = {"entities": [
        {**base, "address_line1": "1 TEST ST", "city": "ERIE", "state": "PA", "zip": "16501"},
        {**base, "party_type": "MEMBER", "first_name": "ANN", "middle_name": "Q",
         "last_name": "LEE"},
        {**base, "party_type": "Governor", "first_name": "BO", "last_name": "RAY"},
        {**base, "party_type": "Trustee", "first_name": "CY", "last_name": "DOE"},
    ]}  # fmt: skip
    rows = _norm("pa.dos.business", body)
    (biz,) = [r for t, r in rows if t == "business"]
    assert biz["principal_address_id"] is not None and biz["status"] == "Active"
    roles = sorted((r["role"], r["title"]) for t, r in rows if t == "business_role")
    assert roles == [("director", "Governor"), ("member", "MEMBER"), ("other", "Trustee")]
    ann = next(r for t, r in rows if t == "party" and r["raw_name"] == "ANN Q LEE")
    assert (ann["first_name"], ann["middle"], ann["last_name"], ann["suffix"]) == (
        "ANN", "Q", "LEE", None)  # fmt: skip
