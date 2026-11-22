"""Deterministic debtor -> owner matching on a tiny synthetic lake."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any

import duckdb
import pytest

from equity.matching.resolve import run


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM read_json_auto(?)", [_tmp_json(path, rows)])
    con.execute(f"COPY t TO '{path.as_posix()}' (FORMAT PARQUET)")


def _tmp_json(path: Path, rows: list[dict[str, Any]]) -> str:
    p = path.with_suffix(".json")
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return str(p)


def _addr(aid: str, line1: str | None, zip5: str | None) -> dict[str, Any]:
    return {"address_id": aid, "line1": line1, "zip5": zip5}


@pytest.fixture
def lake(tmp_path: Path) -> Path:
    lk = tmp_path / "lake"
    d = lk / "zz.debts"
    o = lk / "zz.parcels"
    _write(d / "address" / "0.parquet", [
        _addr("a1", "12 MAIN ST", "10001"), _addr("a2", "9 ELM AVE", "10002"),
        _addr("a3", "1 FAR RD", "10001"), _addr("a4", "5 OAK LN", "14850"),
    ])  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": "d1", "raw_name": "JOHN A SMITH", "party_kind": "person",
         "org_name_norm": None, "address_id": "a1"},
        {"party_id": "d2", "raw_name": "ACME HOLDINGS LLC", "party_kind": "org",
         "org_name_norm": "ACME HOLDINGS", "address_id": "a3"},
        {"party_id": "d3", "raw_name": "MARY JONES", "party_kind": "person",
         "org_name_norm": None, "address_id": "a3"},
        {"party_id": "d4", "raw_name": "SMITH", "party_kind": "person",
         "org_name_norm": None, "address_id": "a1"},
        {"party_id": "d5", "raw_name": "PAT KIM", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "a4"},
    ])  # fmt: skip
    _write(d / "instrument_party" / "0.parquet", [
        {"instrument_uid": f"i{n}", "party_id": f"d{n}", "role": "debtor"} for n in range(1, 6)
    ] + [{"instrument_uid": "i1", "party_id": "c1", "role": "creditor"}])  # fmt: skip
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{n}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2025-01-01", "principal_amount": 100.0 * n} for n in range(1, 6)
    ])  # fmt: skip
    _write(d / "instrument_ref" / "0.parquet", [
        {"from_uid": "r2", "to_uid": "i2", "ref_type": "releases"}])  # fmt: skip
    _write(o / "address" / "0.parquet", [
        _addr("m1", "12 MAIN ST", "10001"), _addr("s1", "300 PARK AVE", "10001"),
        _addr("m2", "77 BAY ST", "10001"), _addr("m3", "5 OAK LN", "14850"),
    ])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": "o1", "raw_name": "SMITH JOHN A", "party_kind": "person",
         "org_name_norm": None, "address_id": "m1"},
        {"party_id": "o2", "raw_name": "ACME HOLDINGS L.L.C.", "party_kind": "org",
         "org_name_norm": "ACME HOLDINGS", "address_id": "m2"},
        {"party_id": "o3", "raw_name": "JONES MARY", "party_kind": "person",
         "org_name_norm": None, "address_id": "m2"},
        {"party_id": "o4", "raw_name": "KIM PAT JR", "party_kind": "person",
         "org_name_norm": None, "address_id": "m3"},
    ])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet", [
        {"parcel_uid": "p1", "party_id": "o1"}, {"parcel_uid": "p2", "party_id": "o2"},
        {"parcel_uid": "p3", "party_id": "o3"}, {"parcel_uid": "p4", "party_id": "o4"},
    ])  # fmt: skip
    _write(o / "parcel" / "0.parquet", [
        {"parcel_uid": "p1", "situs_address_id": "s1"},
        {"parcel_uid": "p2", "situs_address_id": None},
        {"parcel_uid": "p3", "situs_address_id": None},
        {"parcel_uid": "p4", "situs_address_id": None},
    ])  # fmt: skip
    _write(o / "parcel_assessment" / "0.parquet", [
        {"parcel_uid": "p1", "tax_year": 2024, "appraised_total": 400000.0, "assessed_value": None},
        {"parcel_uid": "p1", "tax_year": 2025, "appraised_total": 500000.0, "assessed_value": None},
        {"parcel_uid": "p2", "tax_year": 2025, "appraised_total": None, "assessed_value": 90000.0},
    ])  # fmt: skip
    return lk


def test_rules_and_summary(lake: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = run(lake, out, ["zz.debts"], ["zz.parcels"])
    con = duckdb.connect()
    m = {r[0]: r[1:] for r in con.execute(
        f"SELECT debtor_party_id, owner_party_id, rule_id, decision "
        f"FROM '{out.as_posix()}/matches.parquet'").fetchall()}  # fmt: skip
    # Word order and suffixes do not matter; the address must agree for an auto person match.
    assert m["d1"] == ("o1", "person_name_address", "auto")
    # Org: same normalized name, different street, same ZIP.
    assert m["d2"] == ("o2", "org_name_zip", "auto")
    # Same name and ZIP but a different street: review, not auto.
    assert m["d3"] == ("o3", "person_name_zip", "review")
    # A last name alone never matches.
    assert "d4" not in m
    # JR is dropped, so KIM PAT JR == PAT KIM at the same address. Names the parser could not
    # classify ("unknown") use the person rules; only orgs use the org rules.
    assert m["d5"] == ("o4", "person_name_address", "auto")
    assert result["matches_by_rule"] == {"org_name_zip": 1, "person_name_address": 2,
                                         "person_name_zip": 1}  # fmt: skip
    s = {r[0]: r[1:] for r in con.execute(
        f"SELECT debtor_party_id, open_amount, parcels, parcel_value, has_auto "
        f"FROM '{out.as_posix()}/debtor_summary.parquet'").fetchall()}  # fmt: skip
    assert s["d1"] == (100.0, 1, 500000.0, True)  # latest assessment year wins
    assert s["d2"] == (None, 1, 90000.0, True)  # released lien: nothing open
    assert s["d3"][3] is False
    assert result["debtors_matched_auto"] == 3 and result["debtors_matched_review_only"] == 1
    assert json.loads((out / "summary.json").read_text())["owner_parties"] == 4


def test_missing_sources_give_empty_results(tmp_path: Path) -> None:
    result = run(tmp_path / "empty", tmp_path / "out", ["none.a"], ["none.b"])
    assert result["matches_by_rule"] == {} and result["debtor_parties"] == 0


def test_cli_runs_a_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                          capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    argv = ["resolve", "--state", "NY", "--lake", str(tmp_path / "lake"),
            "--out", str(tmp_path / "out")]  # fmt: skip
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.delitem(sys.modules, "equity.matching.resolve")  # run it fresh as __main__
    with pytest.raises(SystemExit) as done:
        runpy.run_module("equity.matching.resolve", run_name="__main__")
    assert done.value.code == 0
    assert json.loads(capsys.readouterr().out)["debtor_parties"] == 0
    assert (tmp_path / "out" / "ny" / "summary.json").exists()


def _recorder(lake: Path) -> None:
    """Mortgages on p1 (owned by the matched debtor d1, value 500,000)."""
    r = lake / "zz.recorder"
    docs = [  # uid, doc_type, recorded_on, amount
        ("m_payoff", "MORTGAGE", "2010-01-01", 300000.0),  # satisfied by s_same
        ("m_open", "MORTGAGE", "2018-01-01", 200000.0),  # nothing closes it
        ("m_sold", "MORTGAGE", "2005-01-01", 100000.0),  # lot sold to d1 in 2008
        ("m_ref", "MORTGAGE", "2019-01-01", 50000.0),  # a release cites it
        ("m_self", "MORTGAGE", "2020-01-01", 70000.0),  # deed to self, other-name SAT
        ("m_partial", "MORTGAGE", "2021-01-01", None),  # partial release only: open, no amount
        ("s_same", "RELEASE", "2015-01-01", None),
        ("s_other", "RELEASE", "2022-01-01", None),
        ("s_cites", "RELEASE", "2023-01-01", None),
        ("p_rel", "PARTIAL_RELEASE", "2022-06-01", None),
        ("d_sale", "DEED", "2008-01-01", None),
        ("d_self", "DEED", "2021-06-01", None),
    ]
    _write(r / "instrument" / "0.parquet", [
        {"instrument_uid": u, "source_id": "zz.recorder", "doc_type": t, "recorded_on": d,
         "principal_amount": a} for u, t, d, a in docs])  # fmt: skip
    _write(r / "instrument_parcel" / "0.parquet",
           [{"instrument_uid": u, "parcel_uid": "p1"} for u, *_ in docs])  # fmt: skip
    names = {"smith": "JOHN A SMITH", "smith2": "SMITH JOHN A", "old": "OLD OWNER CORP",
             "doe": "JANE DOE"}  # fmt: skip
    _write(r / "party" / "0.parquet", [
        {"party_id": k, "raw_name": v, "party_kind": "unknown", "org_name_norm": None,
         "address_id": None} for k, v in names.items()])  # fmt: skip
    roles = [("m_payoff", "smith", "borrower"), ("m_open", "smith", "borrower"),
             ("m_sold", "old", "borrower"), ("m_ref", "smith", "borrower"),
             ("m_self", "smith", "borrower"), ("m_partial", "smith", "borrower"),
             ("s_same", "smith2", "borrower"), ("s_other", "doe", "borrower"),
             ("p_rel", "smith", "borrower"), ("d_sale", "smith", "grantee"),
             ("d_self", "smith2", "grantee")]  # fmt: skip
    _write(
        r / "instrument_party" / "0.parquet",
        [{"instrument_uid": u, "party_id": p, "role": role} for u, p, role in roles],
    )
    _write(r / "instrument_ref" / "0.parquet", [
        {"from_uid": "s_cites", "to_uid": "m_ref", "ref_type": "releases"}])  # fmt: skip


def test_open_mortgages_and_equity(lake: Path, tmp_path: Path) -> None:
    _recorder(lake)
    out = tmp_path / "out"
    result = run(lake, out, ["zz.debts"], ["zz.parcels"], ["zz.recorder"])
    con = duckdb.connect()
    status = dict(con.execute(
        f"SELECT instrument_uid, status FROM '{out.as_posix()}/mortgage_status.parquet'"
    ).fetchall())  # fmt: skip
    assert status == {"m_payoff": "paid_payoff", "m_open": "open", "m_sold": "paid_sale",
                      "m_ref": "paid_ref", "m_self": "open", "m_partial": "open"}  # fmt: skip
    row = con.execute(
        "SELECT open_mortgages, open_mortgage_amount, open_mortgages_no_amount, equity_est "
        f"FROM '{out.as_posix()}/debtor_summary.parquet' WHERE debtor_party_id = 'd1'"
    ).fetchone()
    assert row == (3, 270000.0, 1, 230000.0)
    d2 = con.execute(
        "SELECT open_mortgages, equity_est "
        f"FROM '{out.as_posix()}/debtor_summary.parquet' WHERE debtor_party_id = 'd2'"
    ).fetchone()
    assert d2 == (0, 90000.0)  # no recorded mortgages on p2
    assert result["mortgage_lots_by_status"] == {"open": 3, "paid_payoff": 1, "paid_ref": 1,
                                                 "paid_sale": 1}  # fmt: skip
    # d1 and d2; d5's parcel has no assessment, so its equity is unknown, not positive.
    assert result["debtors_auto_with_positive_equity"] == 2
