"""Identity graph: chains of links across steps, auto vs review, hubs not crossed."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from equity.matching import graph
from equity.matching.resolve import run

from .test_resolve import _addr, _write


def _lake(tmp_path: Path, n_hub_clients: int = 0) -> Path:
    """ANN LEE (d1) is an officer of LEE VENTURES (registry B1), which owns p1 (owner o1):
    a chain debtor -> company -> owner -> parcel. BO RAY (d2) matches owner o2 by name and
    ZIP only (review). Registry B9 is a registered agent that also serves CLIENT companies."""
    lk = tmp_path / "lake"
    d, o, r = lk / "s.debts", lk / "s.parcels", lk / "s.sos"
    _write(d / "address" / "0.parquet", [_addr("da", "5 OAK LN", "10001"),
                                         _addr("db", "6 ELM ST", "10001")])  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": "d1", "raw_name": "ANN LEE", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "da"},
        {"party_id": "d2", "raw_name": "BO RAY", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "db"}])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{n}", "party_id": f"d{n}", "role": "debtor"} for n in (1, 2)],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{n}", "source_id": "s.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2025-01-01", "principal_amount": 10.0} for n in (1, 2)])  # fmt: skip
    owners = [
        ("o1", "LEE VENTURES INC", "org", "LEE VENTURES", None, "p1"),
        ("o2", "RAY BO", "unknown", None, "m2", "p2"),
    ]
    owners += [(f"c{i}", f"CLIENT {i} LLC", "org", f"CLIENT {i}", None, f"q{i}")
               for i in range(n_hub_clients)]  # fmt: skip
    _write(o / "address" / "0.parquet", [_addr("m2", "9 MAIL RD", "10001")])
    _write(o / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": kind, "org_name_norm": norm,
         "address_id": a} for k, n, kind, norm, a, _ in owners])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": u, "party_id": k} for k, *_, u in owners])  # fmt: skip
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": u} for *_, u in owners])
    biz = [{"sos_id": "B1", "name": "Lee Ventures, Inc.", "status": "Active"}]
    biz += [{"sos_id": f"C{i}", "name": f"Client {i} LLC", "status": "Active"}
            for i in range(n_hub_clients)]  # fmt: skip
    _write(r / "business" / "0.parquet", biz)
    _write(r / "party" / "0.parquet", [
        {"party_id": "h1", "raw_name": "ANN LEE", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "ha"},
        {"party_id": "h9", "raw_name": "AGENT SERVICES", "party_kind": "unknown",
         "org_name_norm": None, "address_id": None}])  # fmt: skip
    _write(
        r / "address" / "0.parquet",
        [{"address_id": "ha", "line1": "5 OAK LN", "city": "X", "state": "NY", "zip5": "10001"}],
    )
    roles = [
        {"sos_id": "B1", "party_id": "h1", "role": "officer", "title": "PRESIDENT"},
        {"sos_id": "B1", "party_id": "h9", "role": "agent", "title": "AGENT"},
    ]
    roles += [{"sos_id": f"C{i}", "party_id": "h9", "role": "agent", "title": "AGENT"}
              for i in range(n_hub_clients)]  # fmt: skip
    _write(r / "business_role" / "0.parquet", roles)
    return lk


def test_chains_across_steps_reach_parcels(tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = run(_lake(tmp_path), out, ["s.debts"], ["s.parcels"], registry_sources=["s.sos"])
    con = duckdb.connect()
    q = lambda sql: con.execute(sql.replace("OUT", out.as_posix())).fetchall()  # noqa: E731
    person = dict(q("SELECT party_id, person_id FROM 'OUT/person_of.parquet'"))
    reach = {
        (r[0], r[1]): r[2:]
        for r in q("SELECT person_id, parcel_uid, strength, direct FROM 'OUT/person_reach.parquet'")
    }
    # ANN LEE -> officer of B1 -> B1 is owner o1 -> p1: every step automatic, no direct match.
    assert reach[(person["d1"], "p1")] == ("auto", False)
    # BO RAY's only link is name + ZIP: p2 is a review lead, not an automatic reach.
    assert reach[(person["d2"], "p2")] == ("review", False)
    assert (person["d1"], "p2") not in reach and (person["d2"], "p1") not in reach
    edges = set(q("SELECT link FROM 'OUT/graph_edges.parquet'"))
    assert {("debtor_company",), ("owner_company",), ("owns",), ("same_person",),
            ("debtor_owner",), ("role_holder",)} <= edges  # fmt: skip
    g = result["graph"]
    assert isinstance(g, dict)
    assert g["people_reaching_parcels_by_chain_auto"] == 1 and g["hubs"] == 0


def test_a_hub_is_not_a_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The registered agent serves B1 and four CLIENT companies. Above the hub limit, ANN
    LEE's chain through B1 does not run on through the agent to the clients' parcels."""
    monkeypatch.setattr(graph, "HUB_MAX_DEGREE", 4)  # B1 has 4 links
    out = tmp_path / "out"
    run(_lake(tmp_path, n_hub_clients=4), out, ["s.debts"], ["s.parcels"],
        registry_sources=["s.sos"])  # fmt: skip
    con = duckdb.connect()
    q = lambda sql: con.execute(sql.replace("OUT", out.as_posix())).fetchall()  # noqa: E731
    assert q("SELECT node FROM 'OUT/graph_nodes.parquet' WHERE hub") == [("officer:h9",)]
    person = dict(q("SELECT party_id, person_id FROM 'OUT/person_of.parquet'"))
    lots = {r[0] for r in q(f"SELECT parcel_uid FROM 'OUT/person_reach.parquet' "
                            f"WHERE person_id = '{person['d1']}'")}  # fmt: skip
    assert lots == {"p1"}  # not q0..q3
