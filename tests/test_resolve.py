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


def test_condo_unit_mortgages_count_only_for_their_borrower(lake: Path, tmp_path: Path) -> None:
    _recorder(lake)
    r = lake / "zz.recorder"
    extra = [("u_mine", "JOHN A SMITH", 40000.0), ("u_other", "JANE DOE", 900000.0)]
    for name in ("instrument", "instrument_parcel", "instrument_party", "party"):
        rows: list[dict[str, Any]]
        if name == "instrument":
            rows = [
                {
                    "instrument_uid": u,
                    "source_id": "zz.recorder",
                    "doc_type": "MORTGAGE",
                    "recorded_on": "2024-01-01",
                    "principal_amount": a,
                }
                for u, _, a in extra
            ]
        elif name == "instrument_parcel":
            rows = [{"instrument_uid": u, "parcel_uid": "unit1"} for u, _, _ in extra]
        elif name == "instrument_party":
            rows = [
                {"instrument_uid": u, "party_id": f"b_{u}", "role": "borrower"} for u, _, _ in extra
            ]
        else:
            rows = [
                {
                    "party_id": f"b_{u}",
                    "raw_name": n,
                    "party_kind": "unknown",
                    "org_name_norm": None,
                    "address_id": None,
                }
                for u, n, _ in extra
            ]
        _write(r / name / "1.parquet", rows)  # fmt: skip
    _write(
        lake / "zz.links" / "parcel_link" / "0.parquet",
        [{"from_parcel_uid": "unit1", "to_parcel_uid": "p1", "link_type": "condo_unit_of"}],
    )
    out = tmp_path / "out"
    run(lake, out, ["zz.debts"], ["zz.parcels"], ["zz.recorder"], ["zz.links"])
    con = duckdb.connect()
    unit = dict(con.execute(
        f"SELECT instrument_uid, lot_uid FROM '{out.as_posix()}/mortgage_status.parquet' "
        "WHERE via_unit").fetchall())  # fmt: skip
    assert unit == {"u_mine": "unit1", "u_other": "unit1"}
    row = con.execute(
        "SELECT open_mortgages, open_mortgage_amount, equity_est "
        f"FROM '{out.as_posix()}/debtor_summary.parquet' WHERE debtor_party_id = 'd1'"
    ).fetchone()
    # The three open whole-lot mortgages (270,000) plus d1's own unit mortgage; the other
    # unit owner's 900,000 mortgage on the same building is not d1's debt.
    assert row == (4, 310000.0, 190000.0)


def test_street_town_rules_only_when_enabled(tmp_path: Path) -> None:
    lk = tmp_path / "lake"
    d, o = lk / "ct.debts", lk / "ct.parcels"
    _write(d / "address" / "0.parquet", [
        {"address_id": "a1", "line1": "5 ELM ST", "city": "Wilton", "zip5": "06897"},
        {"address_id": "a2", "line1": "9 MILL RD", "city": "Kent", "zip5": None}])  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": "d1", "raw_name": "ANN LEE", "party_kind": "unknown", "org_name_norm": None,
         "address_id": "a1"},
        {"party_id": "d2", "raw_name": "MILL CORP", "party_kind": "org",
         "org_name_norm": "MILL", "address_id": "a2"},
        {"party_id": "d3", "raw_name": "BO RAY", "party_kind": "unknown", "org_name_norm": None,
         "address_id": "a2"}])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{n}", "party_id": f"d{n}", "role": "debtor"} for n in (1, 2, 3)],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{n}", "source_id": "ct.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2025-01-01", "principal_amount": 10.0} for n in (1, 2, 3)])  # fmt: skip
    _write(o / "address" / "0.parquet", [
        {"address_id": "m1", "line1": "5 ELM ST", "city": "WILTON ", "zip5": None},
        {"address_id": "m2", "line1": "9 MILL RD", "city": "KENT", "zip5": None},
        {"address_id": "m3", "line1": "9 MILL RD", "city": "SHARON", "zip5": None}])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": "o1", "raw_name": "LEE ANN", "party_kind": "unknown", "org_name_norm": None,
         "address_id": "m1"},
        {"party_id": "o2", "raw_name": "MILL CORPORATION", "party_kind": "org",
         "org_name_norm": "MILL", "address_id": "m2"},
        {"party_id": "o3", "raw_name": "RAY BO", "party_kind": "unknown", "org_name_norm": None,
         "address_id": "m3"}])  # fmt: skip
    _write(
        o / "owner_snapshot" / "0.parquet",
        [{"parcel_uid": f"p{n}", "party_id": f"o{n}"} for n in (1, 2, 3)],
    )
    _write(
        o / "parcel" / "0.parquet",
        [{"parcel_uid": f"p{n}", "situs_address_id": None} for n in (1, 2, 3)],
    )
    off = run(lk, tmp_path / "off", ["ct.debts"], ["ct.parcels"])
    # No owner ZIPs: the ZIP rules cannot fire, and without street_town the same street and
    # city is only a review lead (never automatic); another town (BO RAY, Sharon) is none.
    assert off["matches_by_rule"] == {"org_name_street_city": 1, "person_name_street_city": 1}
    assert off["debtors_matched_auto"] == 0
    on = run(lk, tmp_path / "on", ["ct.debts"], ["ct.parcels"], street_town=True)
    # Same street in another town (BO RAY, Sharon) does not match.
    assert on["matches_by_rule"] == {"org_name_street_town": 1, "person_name_street_town": 1}
    assert on["debtors_matched_auto"] == 2


def test_a_lien_that_names_its_parcel_matches_it(lake: Path, tmp_path: Path) -> None:
    _write(lake / "zz.debts" / "instrument_parcel" / "0.parquet", [
        {"instrument_uid": "i4", "parcel_uid": "p3"},  # d4 (a last name only) names p3
        {"instrument_uid": "i3", "parcel_uid": "not-in-the-roll"}])  # fmt: skip
    off = run(lake, tmp_path / "off", ["zz.debts"], ["zz.parcels"])
    assert "lien_names_parcel" not in off["matches_by_rule"]
    on = run(lake, tmp_path / "on", ["zz.debts"], ["zz.parcels"], parcel_on_lien=True)
    assert on["matches_by_rule"]["lien_names_parcel"] == 1
    con = duckdb.connect()
    row = con.execute(
        "SELECT owner_party_id, parcel_uid, decision FROM "
        f"'{(tmp_path / 'on').as_posix()}/matches.parquet' WHERE rule_id = 'lien_names_parcel'"
    ).fetchone()
    assert row == (None, "p3", "auto")


def test_liens_without_a_named_debtor_are_owed_by_the_parcel_owner(tmp_path: Path) -> None:
    lk = tmp_path / "lake"
    d, o = lk / "pa.liens", lk / "pa.parcels"
    _write(
        d / "instrument" / "0.parquet",
        [
            {
                "instrument_uid": "t1",
                "source_id": "pa.liens",
                "doc_type": "TAX_LIEN_STATE",
                "doc_type_raw": "SCHOOL",
                "recorded_on": "2020-01-01",
                "principal_amount": 500.0,
            },
            {
                "instrument_uid": "t2",
                "source_id": "pa.liens",
                "doc_type": "TAX_LIEN_STATE",
                "doc_type_raw": "SCHOOL (satisfied)",
                "recorded_on": "2019-01-01",
                "principal_amount": 300.0,
            },
            {
                "instrument_uid": "t3",
                "source_id": "pa.liens",
                "doc_type": "TAX_LIEN_STATE",
                "doc_type_raw": "SEWAGE",
                "recorded_on": "2021-01-01",
                "principal_amount": 50.0,
            },
            {
                "instrument_uid": "f1",
                "source_id": "pa.liens",
                "doc_type": "LIS_PENDENS",
                "doc_type_raw": "Mortgage foreclosure filing",
                "recorded_on": "2022-03-01",
                "principal_amount": 150000.0,
            },
        ],
    )
    _write(d / "instrument_parcel" / "0.parquet", [
        {"instrument_uid": "t1", "parcel_uid": "pin1"},
        {"instrument_uid": "t2", "parcel_uid": "pin1"},
        {"instrument_uid": "t3", "parcel_uid": "pin-gone"},
        {"instrument_uid": "f1", "parcel_uid": "pin1"}])  # fmt: skip
    _write(d / "instrument_party" / "0.parquet", [
        {"instrument_uid": "t1", "party_id": "c1", "role": "creditor"}])  # fmt: skip
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": "pin1", "situs_address_id": None}])
    _write(o / "parcel_assessment" / "0.parquet", [
        {"parcel_uid": "pin1", "tax_year": 2025, "appraised_total": 80000.0,
         "assessed_value": None}])  # fmt: skip
    out = tmp_path / "out"
    result = run(lk, out, ["pa.liens"], ["pa.parcels"], parcel_on_lien=True)
    assert result["matches_by_rule"] == {"lien_names_parcel": 3}
    con = duckdb.connect()
    s = con.execute(
        "SELECT debtor_party_id, liens, open_amount, parcels, parcel_value, "
        "foreclosure_filings, last_foreclosure_on::VARCHAR "
        f"FROM '{out.as_posix()}/debtor_summary.parquet'").fetchall()  # fmt: skip
    # The satisfied lien is not open; the lien on a parcel missing from the roll is unmatched;
    # the foreclosure is counted, not added to the open lien amount.
    assert s == [("owner-of:pin1", 2, 500.0, 1, 80000.0, 1, "2022-03-01")]


def test_people_merge_a_debtor_across_liens(lake: Path, tmp_path: Path) -> None:
    """Two liens naming JOHN A SMITH at one address are one person, counted once per parcel."""
    d = lake / "zz.debts"
    _write(d / "party" / "1.parquet", [
        {"party_id": "d6", "raw_name": "SMITH JOHN A", "party_kind": "person",
         "org_name_norm": None, "address_id": "a1"}])  # fmt: skip
    _write(d / "instrument_party" / "1.parquet", [
        {"instrument_uid": "i6", "party_id": "d6", "role": "debtor"}])  # fmt: skip
    _write(d / "instrument" / "1.parquet", [
        {"instrument_uid": "i6", "source_id": "zz.other", "doc_type": "JUDGMENT_LIEN",
         "recorded_on": "2025-02-01", "principal_amount": 50.0}])  # fmt: skip
    out = tmp_path / "out"
    result = run(lake, out, ["zz.debts"], ["zz.parcels"])
    con = duckdb.connect()
    rows = con.execute(
        f"SELECT person_id, judgments_and_liens, open_count, open_amount, parcels, parcel_value,"
        f" sources FROM '{out.as_posix()}/people.parquet' WHERE person_id IN ('d1', 'd6')"
    ).fetchall()  # fmt: skip
    assert rows == [("d1", 2, 2, 150.0, 1, 500000.0, ["zz.debts", "zz.other"])]
    assert result["open_judgments_linked"] == 3  # i1, i6 (John Smith) and i5 (Pat Kim)
    assert result["open_amount_linked_once"] == 650.0


def test_court_judgments_match_businesses_by_county_for_review(tmp_path: Path) -> None:
    lk = tmp_path / "lake"
    c, o = lk / "zz.courts", lk / "zz.parcels"
    _write(c / "party" / "0.parquet", [
        {"party_id": "k1", "raw_name": "ACME HOLDINGS LLC", "party_kind": "org",
         "org_name_norm": "ACME HOLDINGS", "address_id": None},
        {"party_id": "k2", "raw_name": "STERLING", "party_kind": "unknown",
         "org_name_norm": None, "address_id": None}])  # fmt: skip
    _write(c / "case_party" / "0.parquet", [
        {"case_uid": "c1", "party_id": "k1", "role": "debtor"},
        {"case_uid": "c1", "party_id": "k2", "role": "debtor"},
        {"case_uid": "c2", "party_id": "k1", "role": "debtor"}])  # fmt: skip
    _write(c / "judgment" / "0.parquet", [
        {"judgment_uid": "j1", "case_uid": "c1", "source_id": "zz.courts",
         "entered_on": "2020-01-01", "principal": 7000.0, "jurisdiction": "36061"},
        {"judgment_uid": "j2", "case_uid": "c2", "source_id": "zz.courts",
         "entered_on": "2020-01-01", "principal": 9.0, "jurisdiction": "06037"}])  # fmt: skip
    _write(c / "judgment_event" / "0.parquet", [{"judgment_uid": "none", "event": "satisfied"}])
    _write(o / "party" / "0.parquet", [
        {"party_id": "o1", "raw_name": "ACME HOLDINGS INC", "party_kind": "org",
         "org_name_norm": "ACME HOLDINGS", "address_id": None}])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet", [{"parcel_uid": "36061-1", "party_id": "o1"}])
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": "36061-1", "situs_address_id": None}])
    out = tmp_path / "out"
    result = run(lk, out, ["zz.none"], ["zz.parcels"], court_sources=["zz.courts"])
    m = duckdb.connect().execute(
        f"SELECT debtor_party_id, instrument_uid, rule_id, decision"
        f" FROM '{out.as_posix()}/matches.parquet'").fetchall()  # fmt: skip
    # Same business in the parcel's county: review. The LA judgment (other county) and the
    # surname-only person are never matched.
    assert m == [("k1", "j1", "org_name_county", "review")]
    assert result["debtor_parties"] == 2


def test_garnishment_writs_make_their_defendants_judgment_debtors(
    lake: Path, tmp_path: Path
) -> None:
    w = lake / "zz.writs"
    _write(w / "address" / "0.parquet", [_addr("wa1", "12 MAIN ST", "10001")])
    _write(w / "party" / "0.parquet", [
        {"party_id": "w1", "raw_name": "SMITH, JOHN A", "party_kind": "person",
         "org_name_norm": None, "address_id": "wa1"},
        {"party_id": "w2", "raw_name": "BANK NA", "party_kind": "org",
         "org_name_norm": "BANK", "address_id": None}])  # fmt: skip
    _write(w / "case_party" / "0.parquet", [
        {"case_uid": "k1", "party_id": "w1", "role": "defendant"},
        {"case_uid": "k1", "party_id": "w2", "role": "plaintiff"}])  # fmt: skip
    _write(w / "docket_entry" / "0.parquet", [
        {"case_uid": "k1", "entry_date": "2026-03-02", "source_id": "zz.writs",
         "jurisdiction": "99001"},
        {"case_uid": "k1", "entry_date": "2026-02-01", "source_id": "zz.writs",
         "jurisdiction": "99001"}])  # fmt: skip
    out = tmp_path / "out"
    run(lake, out, ["zz.none"], ["zz.parcels"], writ_sources=["zz.writs"])
    m = duckdb.connect().execute(
        f"SELECT debtor_party_id, instrument_uid, owner_party_id, rule_id"
        f" FROM '{out.as_posix()}/matches.parquet'").fetchall()  # fmt: skip
    assert m == [("w1", "writ:k1", "o1", "person_name_address")]  # the plaintiff is no debtor


def test_a_lien_citing_a_property_address_is_owed_by_that_parcels_owner(
    lake: Path, tmp_path: Path
) -> None:
    c = lake / "zz.charges"
    _write(c / "address" / "0.parquet", [
        _addr("ca1", "300 PARK AVE", "10001"), _addr("ca2", "77 BAY ST", "10001")])  # fmt: skip
    _write(c / "party" / "0.parquet", [
        {"party_id": "pp1", "raw_name": "CITED PROPERTY", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "ca1"},
        {"party_id": "pp2", "raw_name": "CITED PROPERTY", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "ca2"}])  # fmt: skip
    _write(c / "instrument_party" / "0.parquet", [
        {"instrument_uid": "ch1", "party_id": "pp1", "role": "other"},
        {"instrument_uid": "ch2", "party_id": "pp2", "role": "other"}])  # fmt: skip
    _write(
        c / "instrument" / "0.parquet",
        [
            {
                "instrument_uid": u,
                "source_id": "zz.charges",
                "doc_type": "STATUTORY_LIEN",
                "recorded_on": "2026-01-01",
                "principal_amount": 40.0,
            }
            for u in ("ch1", "ch2")
        ],
    )
    out = tmp_path / "out"
    run(lake, out, ["zz.charges"], ["zz.parcels"], parcel_on_lien=True)
    m = duckdb.connect().execute(
        f"SELECT debtor_party_id, instrument_uid, parcel_uid, rule_id"
        f" FROM '{out.as_posix()}/matches.parquet'").fetchall()  # fmt: skip
    # 300 PARK AVE is p1's situs address; 77 BAY ST is only a mailing address, so ch2 names no lot.
    assert m == [("owner-of:p1", "ch1", "p1", "lien_names_parcel")]


def test_defendants_owe_default_judgments_when_no_debtor_is_recorded(
    lake: Path, tmp_path: Path
) -> None:
    c = lake / "zz.county_court"
    _write(c / "address" / "0.parquet", [_addr("ka", "12 MAIN ST", "10001")])
    _write(c / "party" / "0.parquet", [
        {"party_id": "df", "raw_name": "SMITH JOHN A", "party_kind": "person",
         "org_name_norm": None, "address_id": "ka"},
        {"party_id": "pl", "raw_name": "CARD BANK", "party_kind": "org",
         "org_name_norm": "CARD BANK", "address_id": None}])  # fmt: skip
    _write(c / "case_party" / "0.parquet", [
        {"case_uid": "k1", "party_id": "df", "role": "defendant"},
        {"case_uid": "k1", "party_id": "pl", "role": "plaintiff"},
        {"case_uid": "k2", "party_id": "df", "role": "defendant"}])  # fmt: skip
    _write(c / "judgment" / "0.parquet", [
        {"judgment_uid": "jd", "case_uid": "k1", "source_id": "zz.county_court",
         "entered_on": "2026-01-01", "principal": 900.0, "jurisdiction": "99001",
         "judgment_type": "default"},
        {"judgment_uid": "jo", "case_uid": "k2", "source_id": "zz.county_court",
         "entered_on": "2026-01-01", "principal": None, "jurisdiction": "99001",
         "judgment_type": "other"}])  # fmt: skip
    _write(c / "judgment_event" / "0.parquet", [{"judgment_uid": "none", "event": "satisfied"}])
    _write(
        lake / "zz.parcels" / "parcel" / "1.parquet",
        [{"parcel_uid": "99001-9", "situs_address_id": None}],
    )  # puts county 99001 in the owners
    out = tmp_path / "out"
    run(lake, out, ["zz.none"], ["zz.parcels"], court_sources=["zz.county_court"])
    m = duckdb.connect().execute(
        f"SELECT debtor_party_id, instrument_uid, owner_party_id, rule_id"
        f" FROM '{out.as_posix()}/matches.parquet'").fetchall()  # fmt: skip
    # The default judgment's defendant owes it; the plaintiff and the 'other' judgment do not.
    assert m == [("df", "jd", "o1", "person_name_address")]


def test_review_queue_labels_name_zip_matches(tmp_path: Path) -> None:
    lk = tmp_path / "lake"
    d, o = lk / "q.debts", lk / "q.parcels"
    cases = [  # debtor address, owner mailing address
        ("12 Main Street", "12 MAIN ST"),  # same address, spelled differently: auto
        ("40 North Oak Avenue Apt 3", "40 N OAK AVE APT 3"),  # same: auto
        ("12 OAK AVE", "12 ELM AVE"),  # same_number
        ("P.O. BOX 55", "9 PINE RD"),  # po_box
        ("1 FAR RD", "77 BAY ST"),  # different
    ]
    names = ["ANN LEE", "BO RAY", "CY DOE", "DI FOX", "ED KAY"]
    _write(
        d / "address" / "0.parquet", [_addr(f"a{i}", c[0], "10001") for i, c in enumerate(cases)]
    )
    _write(
        o / "address" / "0.parquet", [_addr(f"m{i}", c[1], "10001") for i, c in enumerate(cases)]
    )
    _write(d / "party" / "0.parquet", [
        {"party_id": f"d{i}", "raw_name": n, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"a{i}"} for i, n in enumerate(names)])  # fmt: skip
    owners = [{"party_id": f"o{i}", "raw_name": " ".join(reversed(n.split())),
               "party_kind": "unknown", "org_name_norm": None, "address_id": f"m{i}"}
              for i, n in enumerate(names)]  # fmt: skip
    owners.append(
        {
            "party_id": "o9",
            "raw_name": "KAY ED",
            "party_kind": "unknown",
            "org_name_norm": None,
            "address_id": "m3",
        }
    )  # a second ED KAY in the ZIP
    _write(o / "party" / "0.parquet", owners)
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{i}", "party_id": f"d{i}", "role": "debtor"} for i in range(5)],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{i}", "source_id": "q.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2025-01-01", "principal_amount": 10.0} for i in range(5)])  # fmt: skip
    _write(
        o / "owner_snapshot" / "0.parquet",
        [{"parcel_uid": f"p{p['party_id'][1:]}", "party_id": p["party_id"]} for p in owners],
    )
    _write(
        o / "parcel" / "0.parquet",
        [{"parcel_uid": f"p{p['party_id'][1:]}", "situs_address_id": None} for p in owners],
    )
    out = tmp_path / "out"
    result = run(lk, out, ["q.debts"], ["q.parcels"])
    con = duckdb.connect()
    got = dict(con.execute(
        f"SELECT debtor_party_id, category FROM '{out.as_posix()}/review_queue.parquet' "
        "WHERE owner_party_id <> 'o9'").fetchall())  # fmt: skip
    assert got == {"d2": "same_number", "d3": "po_box", "d4": "different"}
    assert result["review"] == {
        "debtors": 3,
        "debtors_by_category": {"different": 1, "po_box": 1, "same_number": 1},
        "debtors_name_unique_in_zip": 2,  # two owners named ED KAY in 10001
    }  # fmt: skip
    # Street spelling is evened out in the address key, so d0 and d1 are address matches;
    # the review queue itself never accepts anything.
    assert result["matches_by_rule"]["person_name_address"] == 2
    assert result["debtors_matched_auto"] == 2


def test_middle_names_and_suffixes_must_agree(tmp_path: Path) -> None:
    lk = tmp_path / "lake"
    d, o = lk / "s.debts", lk / "s.parcels"
    pairs = [  # debtor name, owner name: each pair at its own address
        ("JOHN A SMITH", "SMITH JOHN A"),  # same person: match
        ("JOHN A SMITH JR", "SMITH JOHN A SR"),  # father and son: no match
        ("ANN B LEE JR", "LEE ANN B"),  # suffix on one side only: match
        ("CY D ROE", "ROE CY E"),  # different middle initial: no match
        ("ED KAY", "KAY ED F"),  # middle initial on one side only: review, never auto
        ("FAY GEE", "GEE FAY HOPE"),  # a full extra middle name: no match
    ]
    _write(
        d / "address" / "0.parquet",
        [_addr(f"a{i}", f"{i + 1} ELM ST", "10001") for i in range(len(pairs))],
    )
    _write(
        o / "address" / "0.parquet",
        [_addr(f"m{i}", f"{i + 1} ELM ST", "10001") for i in range(len(pairs))],
    )
    _write(d / "party" / "0.parquet", [
        {"party_id": f"d{i}", "raw_name": dn, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"a{i}"} for i, (dn, _) in enumerate(pairs)])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": f"o{i}", "raw_name": on, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"m{i}"} for i, (_, on) in enumerate(pairs)])  # fmt: skip
    _write(d / "instrument_party" / "0.parquet", [
        {"instrument_uid": f"i{i}", "party_id": f"d{i}", "role": "debtor"}
        for i in range(len(pairs))])  # fmt: skip
    _write(
        d / "instrument" / "0.parquet",
        [
            {
                "instrument_uid": f"i{i}",
                "source_id": "s.debts",
                "doc_type": "TAX_LIEN_STATE",
                "recorded_on": "2025-01-01",
                "principal_amount": 1.0,
            }
            for i in range(len(pairs))
        ],
    )
    _write(
        o / "owner_snapshot" / "0.parquet",
        [{"parcel_uid": f"p{i}", "party_id": f"o{i}"} for i in range(len(pairs))],
    )
    _write(
        o / "parcel" / "0.parquet",
        [{"parcel_uid": f"p{i}", "situs_address_id": None} for i in range(len(pairs))],
    )
    out = tmp_path / "out"
    run(lk, out, ["s.debts"], ["s.parcels"])
    con = duckdb.connect()
    got = sorted(con.execute(
        f"SELECT debtor_party_id, owner_party_id FROM '{out.as_posix()}/matches.parquet' "
        "WHERE rule_id = 'person_name_address'").fetchall())  # fmt: skip
    assert got == [("d0", "o0"), ("d2", "o2")]
    initial = con.execute(
        f"SELECT debtor_party_id, owner_party_id, decision FROM '{out.as_posix()}/matches.parquet' "
        "WHERE rule_id = 'person_name_initial_address'").fetchall()  # fmt: skip
    assert initial == [("d4", "o4", "review")]
    queued = con.execute(
        f"SELECT debtor_party_id, category, rule_id FROM '{out.as_posix()}/review_queue.parquet'"
    ).fetchall()
    assert ("d4", "middle_initial", "person_name_initial_address") in queued


def test_debtor_doc_types_limit_which_instruments_are_debts(lake: Path, tmp_path: Path) -> None:
    kept = run(lake, tmp_path / "a", ["zz.debts"], ["zz.parcels"],
               debtor_doc_types=["TAX_LIEN_STATE"])  # fmt: skip
    dropped = run(lake, tmp_path / "b", ["zz.debts"], ["zz.parcels"],
                  debtor_doc_types=["FIXTURE_FILING"])  # fmt: skip
    assert kept["debtor_parties"] == 5
    assert dropped["debtor_parties"] == 0 and dropped["matches_by_rule"] == {}


def test_list_sources_names_every_source_a_state_reads(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from equity.matching.resolve import (
        STATES,
        TABLES_READ,
        main,
        optional_registries,
        state_sources,
    )

    assert state_sources("NY") == sorted({*STATES["NY"]["debtors"], *STATES["NY"]["owners"],
                                          *STATES["NY"]["record_owners"],
                                          "ny.sos.business", "ny.sos.name_history",
                                          "ny.nyc.acris.real",
                                          "ny.nyc.dof.condo_units",
                                          "us.nynb.rss", "us.nysb.rss", "us.nywb.rss",  # NY bankr.
                                          "us.sba.chargeoffs",
                                          "us.sba.ppp_chargeoffs"})  # fmt: skip
    assert main(["--state", "TX-TRAVIS", "--list-sources"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got == {"sources": ["tx.statewide.parcels", "tx.travis.tax_delinquent",
                               "us.sba.chargeoffs", "us.sba.ppp_chargeoffs",
                               "us.txeb.rss", "us.txnb.rss", "us.txwb.rss"],
                   "tables": list(TABLES_READ),
                   "optional_sources": optional_registries("TX-TRAVIS")}  # fmt: skip
    # Optional registries: the national lists plus Texas's own license boards, no others.
    opt = got["optional_sources"]
    assert "us.fmcsa.carrier_census" in opt and "tx.tdlr.licenses" in opt
    assert not any(s.startswith(("ny.", "fl.")) for s in opt)


def test_bankruptcy_screen_flags_debtors_named_in_state_bankruptcy_cases(
    lake: Path, tmp_path: Path
) -> None:
    from equity.matching.bankruptcy import sources_for

    bk = lake / "us.zzb.rss"
    _write(bk / "court_case" / "0.parquet", [
        {"case_uid": "zzb:1", "court_id": "zzb", "case_type": "bk",
         "nature_of_suit": "chapter 7"},
        {"case_uid": "zzb:2", "court_id": "zzb", "case_type": "bk",
         "nature_of_suit": "chapter 13"},
        {"case_uid": "zzb:3", "court_id": "zzb", "case_type": "bk", "nature_of_suit": None},
        {"case_uid": "zzd:9", "court_id": "zzd", "case_type": "cv",
         "nature_of_suit": None}])  # fmt: skip
    _write(bk / "party" / "0.parquet", [
        {"party_id": "b1", "raw_name": "Smith John A", "party_kind": "person",
         "org_name_norm": None},
        {"party_id": "b2", "raw_name": "Acme Holdings, LLC", "party_kind": "org",
         "org_name_norm": "ACME HOLDINGS"},
        {"party_id": "b3", "raw_name": "Mary Jones", "party_kind": "person", "org_name_norm": None},
        {"party_id": "b4", "raw_name": "Pat Kim", "party_kind": "person",
         "org_name_norm": None}])  # fmt: skip
    _write(
        bk / "case_party" / "0.parquet",
        [
            {"case_uid": "zzb:1", "party_id": "b1", "role": "debtor"},
            {"case_uid": "zzb:2", "party_id": "b2", "role": "debtor"},
            {"case_uid": "zzb:3", "party_id": "b3", "role": "debtor"},
            {"case_uid": "zzd:9", "party_id": "b4", "role": "debtor"},
        ],
    )  # civil case: not a bk debtor
    _write(bk / "docket_entry" / "0.parquet", [
        {"case_uid": "zzb:1", "entry_date": "2026-11-01",
         "text": "[Voluntary Petition (Chapter 7)]"},
        {"case_uid": "zzb:1", "entry_date": "2026-11-20",
         "text": "[BNC Certificate of Mailing - Order of Discharge]"},
        {"case_uid": "zzb:2", "entry_date": "2026-11-05",
         "text": "[BNC Certificate of Mailing - Order Dismissing Case]"},
        {"case_uid": "zzb:3", "entry_date": "2026-11-06",
         "text": "[Notice of Order on Trustee's Motion to Dismiss Case]"}])  # fmt: skip
    out = tmp_path / "out"
    result = run(lake, out, ["zz.debts"], ["zz.parcels"], bankruptcy_sources=["us.zzb.rss"])
    flags = {r[0]: r[1:] for r in duckdb.connect().execute(
        f"SELECT debtor_party_id, case_uid, chapter, status, rule_id, decision "
        f"FROM '{out.as_posix()}/bankruptcy_flags.parquet'").fetchall()}  # fmt: skip
    assert flags["d1"] == ("zzb:1", "7", "discharged", "person_name", "review")
    assert flags["d2"] == ("zzb:2", "13", "dismissed", "org_name", "review")
    assert flags["d3"] == (
        "zzb:3",
        None,
        "open",
        "person_name",
        "review",
    )  # a motion is not an order
    assert "d4" not in flags and "d5" not in flags  # SMITH alone; PAT KIM only in a civil case
    assert result["bankruptcy"]["bankruptcy_cases_seen"] == 3
    assert result["bankruptcy"]["people_flagged_by_status"] == {
        "discharged": 1, "dismissed": 1, "open": 1}  # fmt: skip
    assert result["bankruptcy"]["people_with_parcels_flagged"] == 2  # d1, d2 matched owners
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "courts.yaml").write_text(
        "enabled: [ohnb, ohsb, ohnd]\ncourts:\n  OH: [ohnd, ohsd, ohnb, ohsb]\n"
    )
    assert sources_for("oh", cfg) == ["us.ohnb.rss", "us.ohsb.rss"]
    assert sources_for("ZZ", cfg) == []


def test_federal_debt_lists_count_whatever_the_state_doc_type_filter(
    lake: Path, tmp_path: Path
) -> None:
    from equity.matching.resolve import FEDERAL_DEBTS

    sba = lake / FEDERAL_DEBTS[0]
    _write(sba / "address" / "0.parquet", [_addr("sa1", "12 MAIN ST", "10001")])
    _write(sba / "party" / "0.parquet", [
        {"party_id": "s1", "raw_name": "JOHN A SMITH", "party_kind": "person",
         "org_name_norm": None, "address_id": "sa1"}])  # fmt: skip
    _write(sba / "instrument_party" / "0.parquet", [
        {"instrument_uid": "sba1", "party_id": "s1", "role": "debtor"}])  # fmt: skip
    _write(sba / "instrument" / "0.parquet", [
        {"instrument_uid": "sba1", "source_id": FEDERAL_DEBTS[0], "doc_type": "OTHER",
         "recorded_on": "2024-05-01", "principal_amount": 50000.0}])  # fmt: skip
    out = tmp_path / "out"
    run(
        lake, out, ["zz.debts", *FEDERAL_DEBTS], ["zz.parcels"], debtor_doc_types=["JUDGMENT_LIEN"]
    )  # zz.debts are TAX_LIEN_STATE: filtered out
    matches = f"'{out.as_posix()}/matches.parquet'"
    m = duckdb.connect().execute(f"SELECT debtor_party_id, rule_id FROM {matches}").fetchall()
    assert m == [("s1", "person_name_address")]


def test_a_per_source_doc_type_filter_leaves_other_sources_alone(
    lake: Path, tmp_path: Path
) -> None:
    from equity.matching.resolve import doc_type_filter

    out = tmp_path / "out"
    # zz.debts holds only TAX_LIEN_STATE: a filter naming another source keeps all of them.
    result = run(lake, out, ["zz.debts"], ["zz.parcels"],
                 debtor_doc_types={"zz.ucc": ["TAX_LIEN_FEDERAL"]})  # fmt: skip
    assert result["debtors_matched_auto"] == 3  # as with no filter
    run(lake, out, ["zz.debts"], ["zz.parcels"], debtor_doc_types={"zz.debts": ["JUDGMENT_LIEN"]})
    assert duckdb.connect().execute(
        f"SELECT count(*) FROM '{out.as_posix()}/matches.parquet'").fetchone() == (0,)  # fmt: skip
    sql = doc_type_filter({"b.src": ["X"], "a.src": ["Y", "Z"]})
    assert sql == ("AND (i.source_id NOT IN ('a.src', 'b.src') OR (i.source_id = 'a.src' AND "
                   "i.doc_type IN ('Y', 'Z')) OR (i.source_id = 'b.src' AND "
                   "i.doc_type IN ('X')))")  # fmt: skip
    assert doc_type_filter(None) == "" and doc_type_filter([]) == ""


def test_every_mortgage_source_yields_mortgages_on_parcels() -> None:
    """A run's mortgage source must give MORTGAGE instruments linked to parcels, or equity
    netting silently does nothing for that run (the reason the Florida official-records
    indexes, which carry no parcel ids, are not mortgage sources)."""
    from datetime import UTC, datetime
    from pathlib import Path

    from equity.adapters.base import Fetched
    from equity.adapters.registry import by_source_id
    from equity.matching.resolve import STATES

    fixtures = Path(__file__).parent / "fixtures" / "adapters"
    sources = sorted({s for spec in STATES.values() for s in spec.get("mortgages") or []})
    assert "pa.philadelphia.rtt" in sources
    for sid in sources:
        cls = by_source_id(sid)
        path = sorted((fixtures / sid).glob("*"))[0].resolve()
        rows = list(cls().normalize(Fetched(sid, path.as_uri(), datetime(2025, 12, 31, tzinfo=UTC),
                                            200, path.read_bytes(), "")))  # fmt: skip
        mortgages = {r.row["instrument_uid"] for r in rows
                     if r.table == "instrument" and r.row["doc_type"] == "MORTGAGE"}  # fmt: skip
        linked = {r.row["instrument_uid"] for r in rows if r.table == "instrument_parcel"}
        assert mortgages & linked, f"{sid}: no MORTGAGE linked to a parcel in its fixture"


def test_records_that_name_an_owner_fill_parcels_without_roll_owners(tmp_path: Path) -> None:
    """A permit's owner or a deed's grantee names the owner of a lot whose roll has no owner
    names: the latest such record per parcel joins the owners. A roll owner is never displaced,
    and an old non-deed record only reaches review (the lot may have been sold since)."""
    lk = tmp_path / "lake"
    d, o, r, s = lk / "zz.debts", lk / "zz.parcels", lk / "zz.permits", lk / "zz.sales"
    _write(d / "address" / "0.parquet", [
        _addr("da1", "1 A ST", "10001"), _addr("da2", "2 B ST", "10001"),
        _addr("da3", "3 C ST", "10001"), _addr("da4", "4 D ST", "10001")])  # fmt: skip
    names = {"d1": ("ANN LEE", "da1"), "d2": ("BO RAY", "da2"), "d3": ("CY DOE", "da3"),
             "d4": ("EVE FOX", "da4"), "d5": ("OLD OWNER", "da1")}  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": "person", "org_name_norm": None,
         "address_id": a} for k, (n, a) in names.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{k}", "party_id": k, "role": "debtor"} for k in names],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{k}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for k in names])  # fmt: skip
    _write(o / "address" / "0.parquet", [
        _addr("s1", "1 A ST", "10001"), _addr("s2", "2 B ST", "10001"),
        _addr("s3", "3 C ST", "10001"), _addr("s4", "4 D ST", "10001"),
        _addr("m4", "40 MAIL RD", "10009")])  # fmt: skip
    _write(
        o / "parcel" / "0.parquet",
        [{"parcel_uid": f"99001-{n:03d}", "situs_address_id": f"s{n}"} for n in range(1, 5)],
    )
    # p4 is the only lot with a roll owner.
    _write(o / "party" / "0.parquet", [
        {"party_id": "o4", "raw_name": "ROLL OWNER", "party_kind": "person",
         "org_name_norm": None, "address_id": "m4"}])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet", [{"parcel_uid": "99001-004", "party_id": "o4"}])
    recs = [  # (instrument, party, name, role, parcel, date, source)
        ("r1", "q1", "LEE ANN", "owner", "99001-001", "2026-03-01", "zz.permits"),
        ("r0", "q0", "OLD OWNER", "owner", "99001-001", "2012-05-01", "zz.permits"),
        ("r2", "q2", "RAY BO", "owner", "99001-002", "2012-05-01", "zz.permits"),
        ("r4", "q4", "FOX EVE", "owner", "99001-004", "2026-03-01", "zz.permits"),
        ("s3", "g3", "DOE CY", "grantee", "99001-0.03", "2009-07-01", "zz.sales"),
        ("s3", "g9", "SELLER NINE", "grantor", "99001-0.03", "2009-07-01", "zz.sales"),
    ]  # fmt: skip
    for src, folder in (("zz.permits", r), ("zz.sales", s)):
        rows = [x for x in recs if x[6] == src]
        _write(folder / "party" / "0.parquet", [
            {"party_id": q, "raw_name": n, "party_kind": "person", "org_name_norm": None,
             "address_id": None} for _, q, n, *_ in rows])  # fmt: skip
        _write(
            folder / "instrument_party" / "0.parquet",
            [{"instrument_uid": i, "party_id": q, "role": role} for i, q, _, role, *_ in rows],
        )
        insts = sorted({(x[0], x[4], x[5]) for x in rows})  # (instrument, parcel, date)
        _write(folder / "instrument" / "0.parquet", [
            {"instrument_uid": i, "source_id": src, "recorded_on": day,
             "doc_type": "DEED" if src == "zz.sales" else "OTHER"}
            for i, _p, day in insts])  # fmt: skip
        _write(
            folder / "instrument_parcel" / "0.parquet",
            [{"instrument_uid": i, "parcel_uid": p} for i, p, _d in insts],
        )
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"], record_owner_sources=["zz.permits", "zz.sales"])
    m = {row[0]: row[1:] for row in duckdb.connect().execute(
        f"SELECT debtor_party_id, parcel_uid, rule_id, decision, owner_basis "
        f"FROM '{out.as_posix()}/matches.parquet'").fetchall()}  # fmt: skip
    # The latest record on p1 (2026) names the owner; the 2012 one is not an owner any more.
    assert m["d1"] == ("99001-001", "person_name_address", "auto", "record:zz.permits")
    assert "d5" not in m
    # An old permit owner: the lot may have been sold since, so review only.
    assert m["d2"] == ("99001-002", "person_name_address", "review", "record:zz.permits")
    # The latest deed's grantee is the owner of record however old the deed (the sale prints
    # the lot as 99001-0.03: punctuation does not matter); its grantor is not.
    assert m["d3"] == ("99001-003", "person_name_address", "auto", "deed:zz.sales")
    # p4 has a roll owner: a permit naming someone else does not add an owner.
    assert "d4" not in m


def test_a_debtor_living_at_a_nameless_lot_is_a_review_lead(tmp_path: Path) -> None:
    """California rolls publish no owner names: a debtor whose address is a nameless lot's
    property address is a lead (owner or tenant), ranked higher when the roll's homeowner
    exemption says an owner lives there. Lots that share an address, lots with a known owner
    and businesses give no lead."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    _write(d / "address" / "0.parquet", [
        _addr("a1", "1 HOME ST", "90001"), _addr("a2", "2 RENT ST", "90001"),
        _addr("a3", "3 CONDO WAY", "90001"), _addr("a4", "4 KNOWN ST", "90001")])  # fmt: skip
    people = {"d1": ("ANN LEE", "a1", "person"), "d2": ("BO RAY", "a2", "person"),
              "d3": ("CY DOE", "a3", "person"), "d4": ("EVE FOX", "a4", "person"),
              "d5": ("HOME CORP", "a1", "org")}  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": kind,
         "org_name_norm": "HOME" if kind == "org" else None, "address_id": a}
        for k, (n, a, kind) in people.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{k}", "party_id": k, "role": "debtor"} for k in people],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{k}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for k in people])  # fmt: skip
    _write(o / "address" / "0.parquet", [
        _addr("s1", "1 Home Street", "90001"), _addr("s2", "2 RENT ST", "90001"),
        _addr("s3", "3 CONDO WAY", "90001"), _addr("s4", "4 KNOWN ST", "90001"),
        _addr("m4", "9 MAIL RD", "90002")])  # fmt: skip
    lots = [("06037-1", "s1"), ("06037-2", "s2"), ("06037-3a", "s3"), ("06037-3b", "s3"),
            ("06037-4", "s4")]  # fmt: skip
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": u, "situs_address_id": a} for u, a in lots])
    _write(o / "parcel_assessment" / "0.parquet", [
        {"parcel_uid": "06037-1", "tax_year": 2025, "appraised_total": 1.0, "homestead": False},
        {"parcel_uid": "06037-1", "tax_year": 2026, "appraised_total": 1.0, "homestead": True},
        {"parcel_uid": "06037-2", "tax_year": 2026, "appraised_total": 1.0, "homestead": False},
    ])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": "o4", "raw_name": "SOMEONE ELSE", "party_kind": "person",
         "org_name_norm": None, "address_id": "m4"}])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet", [{"parcel_uid": "06037-4", "party_id": "o4"}])
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    con = duckdb.connect()
    m = {row[0]: row[1:] for row in con.execute(
        f"SELECT debtor_party_id, parcel_uid, rule_id, decision "
        f"FROM '{out.as_posix()}/matches.parquet'").fetchall()}  # fmt: skip
    assert m["d1"] == ("06037-1", "person_at_owner_occupied_property", "review")
    assert m["d2"] == ("06037-2", "person_at_property", "review")
    assert "d3" not in m  # two lots at one address: which one is unknown
    assert "d4" not in m  # the lot has a roll owner, someone else
    assert "d5" not in m  # a business at a home address says nothing about the home
    q = dict(con.execute(
        f"SELECT debtor_party_id, category FROM '{out.as_posix()}/review_queue.parquet'"
    ).fetchall())  # fmt: skip
    assert q == {"d1": "at_owner_occupied_property", "d2": "at_property"}


def test_joint_owners_and_trust_settlors_are_matched_by_their_own_names(tmp_path: Path) -> None:
    """Rolls print couples and trusts in one string: each person in it is an owner name. A
    joint owner matches like any owner (auto with the address); a trust's settlor only
    reaches review (the trust, not the person, holds title)."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    _write(d / "address" / "0.parquet", [_addr("a1", "1 ELM ST", "10001"),
                                         _addr("a2", "2 OAK ST", "10001")])  # fmt: skip
    people = {"d1": ("JANE B SMITH", "a1"), "d2": ("JOHN Q DOE", "a2"),
              "d3": ("JANE SMITH", "a1")}  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": "person", "org_name_norm": None,
         "address_id": a} for k, (n, a) in people.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{k}", "party_id": k, "role": "debtor"} for k in people],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{k}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for k in people])  # fmt: skip
    _write(o / "address" / "0.parquet", [_addr("m1", "1 Elm Street", "10001"),
                                         _addr("m2", "2 OAK ST", "10001")])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": "o1", "raw_name": "SMITH JOHN A & JANE B", "party_kind": "person",
         "org_name_norm": None, "address_id": "m1"},
        {"party_id": "o2", "raw_name": "JOHN Q DOE REVOCABLE TRUST", "party_kind": "org",
         "org_name_norm": "JOHN Q DOE REVOCABLE", "address_id": "m2"}])  # fmt: skip
    _write(
        o / "owner_snapshot" / "0.parquet",
        [{"parcel_uid": "99001-1", "party_id": "o1"}, {"parcel_uid": "99001-2", "party_id": "o2"}],
    )
    _write(
        o / "parcel" / "0.parquet",
        [
            {"parcel_uid": "99001-1", "situs_address_id": None},
            {"parcel_uid": "99001-2", "situs_address_id": None},
        ],
    )
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    m = {row[0]: row[1:] for row in duckdb.connect().execute(
        f"SELECT debtor_party_id, owner_party_id, rule_id, decision, owner_name_variant "
        f"FROM '{out.as_posix()}/matches.parquet'").fetchall()}  # fmt: skip
    assert m["d1"] == ("o1", "person_name_address", "auto", "joint")
    assert m["d2"] == ("o2", "person_name_address", "review", "trust")
    # JANE SMITH at the same address lacks JANE B SMITH's middle initial: the existing
    # middle-initial rule, review only.
    assert m["d3"] == ("o1", "person_name_initial_address", "review", None)


def test_street_norm_drops_ordinal_suffixes_on_numbered_streets() -> None:
    """88TH ST = 88 ST (approved 2026-11-27); spelled-out numbers (FIRST, from the numbered-
    street words) land on the same key; words that only look like ordinals stay."""
    from equity.matching.review import street_macro

    con = duckdb.connect()
    street_macro(con)

    def norm(s: str) -> str:
        return str(con.execute("SELECT street_norm(?)", [s]).fetchall()[0][0])

    assert norm("12 West 88th Street") == norm("12 W 88 ST") == "12 W 88 ST"
    assert norm("100 1ST AVE") == "100 1 AVE" and norm("7 22ND PL") == "7 22 PL"
    assert norm("5 STH AVE") == "5 STH AVE"
    assert norm("9 FIRST ST") == norm("9 1ST ST") == norm("9 1 ST") == "9 1 ST"
    assert norm("12 Fifth Avenue") == norm("12 5TH AVE") == "12 5 AVE"


def test_a_company_whose_tax_bill_goes_to_a_debtors_home_is_a_review_lead(
    tmp_path: Path,
) -> None:
    """An LLC need name no members, but the roll says where its tax bill goes: a person debtor
    at that address likely runs it, so the company's lots are review leads. Not when the
    address is the company's own lot (a tenant), an office that takes bills for many owners,
    or when the debtor is itself a business."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    _write(d / "address" / "0.parquet", [
        _addr("a1", "1 HOME ST", "10001"), _addr("a2", "7 FLAT ST", "10001"),
        _addr("a3", "100 MGR PLZ", "10001")])  # fmt: skip
    people = {"d1": ("ANN LEE", "a1", "person"), "d2": ("BO RAY", "a2", "person"),
              "d3": ("CY DOE", "a3", "person"), "d4": ("HOME CORP", "a1", "org")}  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": kind,
         "org_name_norm": "HOME" if kind == "org" else None, "address_id": a}
        for k, (n, a, kind) in people.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{k}", "party_id": k, "role": "debtor"} for k in people],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{k}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for k in people])  # fmt: skip
    _write(o / "address" / "0.parquet", [
        _addr("m1", "1 Home Street", "10001"), _addr("s1", "5 RENTAL AVE", "10001"),
        _addr("s2", "7 FLAT ST", "10001"), _addr("m3", "100 MGR PLZ", "10001"),
        *[_addr(f"s3{i}", f"{i} LOT RD", "10001") for i in range(11)]])  # fmt: skip
    lots = [("p1", "s1"), ("p2", "s2"), *[(f"p3{i}", f"s3{i}") for i in range(11)]]
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": u, "situs_address_id": a} for u, a in lots])
    owners = [("o1", "LEE HOLDINGS LLC", "LEE HOLDINGS", "m1", "p1"),
              ("o2", "FLAT CO LLC", "FLAT CO", "s2", "p2"),
              *[(f"o3{i}", f"CLIENT {i} LLC", f"CLIENT {i}", "m3", f"p3{i}")
                for i in range(11)]]  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": "org", "org_name_norm": norm,
         "address_id": a} for k, n, norm, a, _ in owners])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": u, "party_id": k} for k, _, _, _, u in owners])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    con = duckdb.connect()
    m = con.execute(
        f"SELECT debtor_party_id, owner_party_id, parcel_uid, rule_id, decision "
        f"FROM '{out.as_posix()}/matches.parquet' ORDER BY ALL").fetchall()  # fmt: skip
    assert m == [("d1", "o1", "p1", "person_at_org_owner_mailing", "review")]
    q = dict(con.execute(
        f"SELECT debtor_party_id, category FROM '{out.as_posix()}/review_queue.parquet'"
    ).fetchall())  # fmt: skip
    assert q == {"d1": "at_company_mailing"}


def test_debtor_aliases_and_joint_debtors_match_by_each_name(tmp_path: Path) -> None:
    """Liens print a sole proprietor with a trade name, a renamed company, or several
    debtors in one string: each name is the debtor's own. An alias is the same debtor (auto
    with the address, one person); one of several joint debtors is liable too, but stays a
    separate person; a trust's settlor only reaches review."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    _write(d / "address" / "0.parquet", [
        _addr("a1", "1 ELM ST", "10001"), _addr("a2", "2 OAK ST", "10001"),
        _addr("a3", "3 PINE ST", "10001"), _addr("a5", "5 FIR ST", "10001")])  # fmt: skip
    people = {
        "d1": ("SMITH JOHN DBA SMITH PLUMBING", "a1", "unknown", None),
        "d2": ("ACME LLC FKA ACME INC", "a2", "org", "ACME LLC FKA ACME"),
        "d3": ("JOHN & MARY DOE", "a3", "unknown", None),
        "d4": ("JOHN DOE", "a3", "unknown", None),
        "d5": ("JANE ROE REVOCABLE TRUST", "a5", "org", "JANE ROE REVOCABLE TRUST"),
    }
    _write(d / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": kind, "org_name_norm": norm,
         "address_id": a} for k, (n, a, kind, norm) in people.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{k}", "party_id": k, "role": "debtor"} for k in people],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{k}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for k in people])  # fmt: skip
    _write(o / "address" / "0.parquet", [
        _addr("m1", "1 Elm Street", "10001"), _addr("m2", "2 OAK ST", "10001"),
        _addr("m3", "3 PINE ST", "10001"), _addr("m5", "5 FIR ST", "10001")])  # fmt: skip
    owners = [("o1", "JOHN SMITH", "unknown", None, "m1", "p1"),
              ("o2", "ACME INC", "org", "ACME", "m2", "p2"),
              ("o3", "MARY DOE", "unknown", None, "m3", "p3"),
              ("o5", "JANE ROE", "unknown", None, "m5", "p5")]  # fmt: skip
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": u} for *_, u in owners])
    _write(o / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": kind, "org_name_norm": norm,
         "address_id": a} for k, n, kind, norm, a, _ in owners])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": u, "party_id": k} for k, *_, u in owners])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    con = duckdb.connect()
    m = {(r[0], r[1]): r[2:] for r in con.execute(
        f"SELECT debtor_party_id, owner_party_id, rule_id, decision, debtor_name_variant "
        f"FROM '{out.as_posix()}/matches.parquet'").fetchall()}  # fmt: skip
    assert m[("d1", "o1")] == ("person_name_address", "auto", "alias")
    assert m[("d2", "o2")] == ("org_name_address", "auto", "alias")
    assert m[("d3", "o3")] == ("person_name_address", "auto", "joint")
    assert m[("d5", "o5")] == ("person_name_address", "review", "trust")
    assert ("d4", "o3") not in m  # JOHN DOE is not MARY DOE
    # "JOHN & MARY DOE" is two people rows, each with the lien; John's row is also the
    # JOHN DOE debtor at the same address (d4), so it holds both liens.
    rows = {r[0]: r[1:] for r in con.execute(
        f"SELECT name, judgments_and_liens, parcels "
        f"FROM '{out.as_posix()}/people.parquet'").fetchall()}  # fmt: skip
    assert rows["MARY DOE"] == (1, 1)  # her own lot, through her own name
    assert rows["JOHN DOE"] == (2, 0)  # the joint lien and his own; Mary's lot is not his
    assert "JOHN & MARY DOE" not in rows
    of = con.execute(
        f"SELECT party_id, count(*) FROM '{out.as_posix()}/person_of.parquet' GROUP BY 1"
    ).fetchall()
    assert dict(of)["d3"] == 2


def test_an_address_matches_its_building_without_the_unit(tmp_path: Path) -> None:
    """A lien at "12 MAIN ST APT 3" and a roll at "12 MAIN ST" (or the reverse) are one
    building: with the same name it is the owner (auto). Two different units of a building are
    not one address; they meet only through the name and ZIP (review)."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    _write(d / "address" / "0.parquet", [
        _addr("a1", "12 MAIN ST APT 3", "10001"), _addr("a2", "20 OAK AVE", "10001"),
        _addr("a3", "30 PINE ST APT 1", "10001"), _addr("a4", "40 ELM ST STE 100", "10001"),
    ])  # fmt: skip
    people = {"d1": ("ANN LEE", "a1", "unknown", None), "d2": ("BO RAY", "a2", "unknown", None),
              "d3": ("CY DOE", "a3", "unknown", None),
              "d4": ("ACME LLC", "a4", "org", "ACME")}  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": kind, "org_name_norm": norm,
         "address_id": a} for k, (n, a, kind, norm) in people.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{k}", "party_id": k, "role": "debtor"} for k in people],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{k}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for k in people])  # fmt: skip
    _write(o / "address" / "0.parquet", [
        _addr("m1", "12 Main Street", "10001"), _addr("m2", "9 MAIL RD", "10002"),
        _addr("s2", "20 OAK AVE #5", "10001"), _addr("m3", "30 PINE ST APT 2", "10001"),
        _addr("m4", "40 ELM ST", "10001")])  # fmt: skip
    _write(o / "parcel" / "0.parquet", [
        {"parcel_uid": "p1"}, {"parcel_uid": "p2", "situs_address_id": "s2"},
        {"parcel_uid": "p3"}, {"parcel_uid": "p4"}])  # fmt: skip
    owners = [("o1", "LEE ANN", "unknown", None, "m1", "p1"),
              ("o2", "BO RAY", "unknown", None, "m2", "p2"),
              ("o3", "CY DOE", "unknown", None, "m3", "p3"),
              ("o4", "ACME LLC", "org", "ACME", "m4", "p4")]  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": kind, "org_name_norm": norm,
         "address_id": a} for k, n, kind, norm, a, _ in owners])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": u, "party_id": k} for k, *_, u in owners])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    con = duckdb.connect()
    m = {r[0]: r[1:] for r in con.execute(
        f"SELECT debtor_party_id, owner_party_id, rule_id, decision "
        f"FROM '{out.as_posix()}/matches.parquet'").fetchall()}  # fmt: skip
    assert m["d1"] == ("o1", "person_name_address_unit", "auto")
    assert m["d2"] == ("o2", "person_name_address_unit", "auto")
    assert m["d3"] == ("o3", "person_name_zip", "review")
    assert m["d4"] == ("o4", "org_name_address_unit", "auto")


def test_a_nickname_at_the_same_address_is_a_review_lead(tmp_path: Path) -> None:
    """ "BOB SMITH" on a lien and "SMITH ROBERT" on the roll at one address: one person to
    review. Another address, a different formal name, or a different surname gives nothing."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    _write(d / "address" / "0.parquet", [
        _addr("a1", "1 ELM ST", "10001"), _addr("a2", "2 OAK ST", "10001"),
        _addr("a3", "3 PINE ST", "10001")])  # fmt: skip
    people = {"d1": ("BOB SMITH", "a1"), "d2": ("BILL JONES", "a2"),
              "d3": ("MIKE ROE", "a3")}  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": "unknown", "org_name_norm": None,
         "address_id": a} for k, (n, a) in people.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{k}", "party_id": k, "role": "debtor"} for k in people],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{k}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for k in people])  # fmt: skip
    _write(o / "address" / "0.parquet", [
        _addr("m1", "1 Elm Street", "10001"), _addr("m2", "2 OAK ST", "10001"),
        _addr("m3", "3 PINE ST", "10001")])  # fmt: skip
    owners = [("o1", "SMITH ROBERT", "m1", "p1"), ("o2", "JONES ROBERT", "m2", "p2"),
              ("o3", "DOE MICHAEL", "m3", "p3")]  # fmt: skip
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": u} for *_, u in owners])
    _write(o / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": "unknown", "org_name_norm": None,
         "address_id": a} for k, n, a, _ in owners])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": u, "party_id": k} for k, *_, u in owners])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    con = duckdb.connect()
    m = con.execute(
        f"SELECT debtor_party_id, owner_party_id, rule_id, decision "
        f"FROM '{out.as_posix()}/matches.parquet' ORDER BY ALL").fetchall()  # fmt: skip
    # BILL is WILLIAM, not ROBERT; MIKE ROE is not MICHAEL DOE.
    assert m == [("d1", "o1", "person_nickname_address", "review")]
    q = dict(con.execute(
        f"SELECT debtor_party_id, category FROM '{out.as_posix()}/review_queue.parquet'"
    ).fetchall())  # fmt: skip
    assert q == {"d1": "nickname"}


def test_a_one_letter_typo_at_the_same_address_is_a_review_lead(tmp_path: Path) -> None:
    """ "JOHN SMIHT" on a lien and "JOHN SMITH" on the roll at one address: one person to
    review. JOHN and JOAN are two real first names (husband and wife), not a typo; two
    letters off, or another address, gives nothing."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    _write(d / "address" / "0.parquet", [
        _addr("a1", "1 ELM ST", "10001"), _addr("a2", "2 OAK ST", "10001"),
        _addr("a3", "3 PINE ST", "10001")])  # fmt: skip
    people = {"d1": ("JOHN SMIHT", "a1"), "d2": ("JOAN BAKER", "a2"),
              "d3": ("ANN GARCIA", "a3")}  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": "unknown", "org_name_norm": None,
         "address_id": a} for k, (n, a) in people.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{k}", "party_id": k, "role": "debtor"} for k in people],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{k}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for k in people])  # fmt: skip
    _write(o / "address" / "0.parquet", [
        _addr("m1", "1 Elm Street", "10001"), _addr("m2", "2 OAK ST", "10001"),
        _addr("m3", "3 PINE ST", "10001")])  # fmt: skip
    owners = [("o1", "SMITH JOHN", "m1", "p1"), ("o2", "BAKER JOHN", "m2", "p2"),
              ("o3", "GRACIAS ANN", "m3", "p3")]  # fmt: skip
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": u} for *_, u in owners])
    _write(o / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": "unknown", "org_name_norm": None,
         "address_id": a} for k, n, a, _ in owners])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": u, "party_id": k} for k, *_, u in owners])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    con = duckdb.connect()
    m = con.execute(
        f"SELECT debtor_party_id, owner_party_id, rule_id, decision "
        f"FROM '{out.as_posix()}/matches.parquet' ORDER BY ALL").fetchall()  # fmt: skip
    # GARCIA / GRACIAS is two letters off: never a typo, but a surname that differs at one
    # address with the same first name is a name-change lead (person_name_change_address).
    assert m == [("d1", "o1", "person_name_typo_address", "review"),
                 ("d3", "o3", "person_name_change_address", "review")]  # fmt: skip
    q = dict(con.execute(
        f"SELECT debtor_party_id, category FROM '{out.as_posix()}/review_queue.parquet'"
    ).fetchall())  # fmt: skip
    assert q == {"d1": "one_letter", "d3": "name_change"}


def test_every_address_rule_sees_through_units(tmp_path: Path) -> None:
    """A unit counts as its building in every address rule: middle initial, nickname, a
    nameless lot (but not a building of several nameless units, and a unit says nothing
    about the building's homeowner exemption), a company's mailing address, and one person
    across their liens at the unit and at the building."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    _write(d / "address" / "0.parquet", [
        _addr("a1", "1 ELM ST APT 2", "10001"), _addr("a2", "2 OAK ST #4", "10001"),
        _addr("a3", "3 PINE ST APT 1", "10001"), _addr("a4", "4 FIR ST", "10001"),
        _addr("a5", "5 ASH ST STE 3", "10001"), _addr("a6", "6 BAY ST APT 9", "10001"),
        _addr("a7", "6 BAY ST", "10001")])  # fmt: skip
    people = {"d1": "JOHN A SMITH", "d2": "BOB JONES", "d3": "ANN LEE", "d4": "CY DOE",
              "d5": "EVE FOX", "d6": "GUS HALE", "d7": "GUS HALE"}  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": "unknown", "org_name_norm": None,
         "address_id": "a" + k[1]} for k, n in people.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{k}", "party_id": k, "role": "debtor"} for k in people],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{k}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for k in people])  # fmt: skip
    _write(o / "address" / "0.parquet", [
        _addr("m1", "1 ELM ST", "10001"), _addr("m2", "2 OAK ST", "10001"),
        _addr("s3", "3 PINE ST", "10001"), _addr("s4a", "4 FIR ST UNIT 1", "10001"),
        _addr("s4b", "4 FIR ST UNIT 2", "10001"), _addr("m5", "5 ASH ST", "10001"),
        _addr("s5", "50 LOT RD", "10001")])  # fmt: skip
    _write(o / "parcel" / "0.parquet", [
        {"parcel_uid": "p1"}, {"parcel_uid": "p2"}, {"parcel_uid": "p3", "situs_address_id": "s3"},
        {"parcel_uid": "p4a", "situs_address_id": "s4a"},
        {"parcel_uid": "p4b", "situs_address_id": "s4b"},
        {"parcel_uid": "p5", "situs_address_id": "s5"}])  # fmt: skip
    _write(
        o / "parcel_assessment" / "0.parquet",
        [{"parcel_uid": "p3", "tax_year": 2026, "appraised_total": 1.0, "homestead": True}],
    )
    owners = [("o1", "JOHN SMITH", "unknown", None, "m1", "p1"),
              ("o2", "ROBERT JONES", "unknown", None, "m2", "p2"),
              ("o5", "FOX HOLDINGS LLC", "org", "FOX HOLDINGS", "m5", "p5")]  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": kind, "org_name_norm": norm,
         "address_id": a} for k, n, kind, norm, a, _ in owners])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": u, "party_id": k} for k, *_, u in owners])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    con = duckdb.connect()
    m = {r[0]: r[1:] for r in con.execute(
        f"SELECT debtor_party_id, parcel_uid, rule_id FROM '{out.as_posix()}/matches.parquet'"
    ).fetchall()}  # fmt: skip
    assert m["d1"] == ("p1", "person_name_initial_address")
    assert m["d2"] == ("p2", "person_nickname_address")
    assert m["d3"] == ("p3", "person_at_property")  # the exemption is the building's
    assert "d4" not in m  # two nameless units at that building: which one is unknown
    assert m["d5"] == ("p5", "person_at_org_owner_mailing")
    person = dict(
        con.execute(
            f"SELECT party_id, person_id FROM '{out.as_posix()}/person_of.parquet'"
        ).fetchall()
    )
    assert person["d6"] == person["d7"]  # GUS HALE at the unit and at the building


def test_names_are_split_on_every_side(tmp_path: Path) -> None:
    """Owner strings with a DBA, joint bankruptcy captions and joint deed grantors are split
    like debtor strings: JOHN SMITH meets "SMITH JOHN DBA SMITH RENTALS" on the roll, "JOHN
    SMITH AND JANE SMITH" in a bankruptcy caption and "JOHN SMITH & JANE SMITH" on a deed."""
    lk = tmp_path / "lake"
    d, o, bk, dd = lk / "zz.debts", lk / "zz.parcels", lk / "us.zzb.rss", lk / "zz.deeds"
    _write(d / "address" / "0.parquet", [_addr("a1", "1 ELM ST", "10001")])
    _write(d / "party" / "0.parquet", [
        {"party_id": "d1", "raw_name": "JOHN SMITH", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "a1"}])  # fmt: skip
    _write(d / "instrument_party" / "0.parquet",
           [{"instrument_uid": "i1", "party_id": "d1", "role": "debtor"}])  # fmt: skip
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": "i1", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2025-01-01", "principal_amount": 10.0}])  # fmt: skip
    _write(o / "address" / "0.parquet", [_addr("m1", "1 Elm Street", "10001")])
    _write(o / "party" / "0.parquet", [
        {"party_id": "o1", "raw_name": "SMITH JOHN DBA SMITH RENTALS", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "m1"}])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet", [{"parcel_uid": "p1", "party_id": "o1"}])
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": "p1"}])
    _write(bk / "court_case" / "0.parquet", [
        {"case_uid": "zzb:1", "court_id": "zzb", "case_type": "bk",
         "nature_of_suit": "chapter 7"}])  # fmt: skip
    _write(bk / "party" / "0.parquet", [
        {"party_id": "b1", "raw_name": "John Smith and Jane Smith", "party_kind": "unknown",
         "org_name_norm": None}])  # fmt: skip
    _write(bk / "case_party" / "0.parquet",
           [{"case_uid": "zzb:1", "party_id": "b1", "role": "debtor"}])  # fmt: skip
    _write(
        bk / "docket_entry" / "0.parquet",
        [{"case_uid": "zzb:1", "entry_date": "2026-11-01", "text": "[Voluntary Petition]"}],
    )
    _write(dd / "instrument" / "0.parquet", [
        {"instrument_uid": "k1", "source_id": "zz.deeds", "doc_type": "DEED",
         "recorded_on": "2025-06-01", "consideration": 300000.0}])  # fmt: skip
    _write(dd / "instrument_parcel" / "0.parquet", [{"instrument_uid": "k1", "parcel_uid": "p1"}])
    _write(dd / "party" / "0.parquet", [
        {"party_id": "g1", "raw_name": "JOHN SMITH & JANE SMITH", "party_kind": "unknown",
         "org_name_norm": None, "address_id": None},
        {"party_id": "g2", "raw_name": "ROE RICHARD", "party_kind": "unknown",
         "org_name_norm": None, "address_id": None}])  # fmt: skip
    _write(dd / "instrument_party" / "0.parquet", [
        {"instrument_uid": "k1", "party_id": "g1", "role": "grantor"},
        {"instrument_uid": "k1", "party_id": "g2", "role": "grantee"}])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"], bankruptcy_sources=["us.zzb.rss"],
        deed_sources=["zz.deeds"])  # fmt: skip
    con = duckdb.connect()
    q = lambda sql: con.execute(sql.replace("OUT", out.as_posix())).fetchall()  # noqa: E731
    assert q(
        "SELECT owner_party_id, rule_id, decision, owner_name_variant FROM 'OUT/matches.parquet'"
    ) == [("o1", "person_name_address", "auto", "alias")]
    assert q("SELECT debtor_party_id, case_uid FROM 'OUT/bankruptcy_flags.parquet'") == [
        ("d1", "zzb:1")]  # fmt: skip
    assert q("SELECT debtor_party_id, deed_uid, rule_id FROM 'OUT/transfer_flags.parquet'") == [
        ("d1", "k1", "on_matched_parcel")]  # fmt: skip


def test_spellings_middle_names_and_spacing_are_review_leads(tmp_path: Path) -> None:
    """At one address: JON / JOHN and ERIK / ERIC (one name spelled two ways), a middle
    name or second surname on one side only, an initial against its middle name, and
    O'BRIEN / OBRIEN or DE LA CRUZ / DELACRUZ are review leads. An initial against a middle
    name with another first letter is not."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    pairs = {  # debtor, owner, expected rule
        "1": ("JON SMITH", "JOHN SMITH", "person_name_typo_address"),
        "2": ("ERIK HALL", "HALL ERIC", "person_nickname_address"),
        "3": ("PAUL KING", "KING PAUL ANDREW", "person_middle_name_address"),
        "4": ("MARK A WEST", "WEST MARK ALAN", "person_middle_name_address"),
        "5": ("SEAN OBRIEN", "O'BRIEN SEAN", "person_name_spacing_address"),
        "6": ("ROSA DELACRUZ", "DE LA CRUZ ROSA", "person_name_spacing_address"),
        "7": ("LUIS GARCIA", "GARCIA LOPEZ LUIS", "person_middle_name_address"),
        "8": ("AMY J COLE", "COLE AMY KAY", None),
    }
    _write(d / "address" / "0.parquet",
           [_addr(f"a{n}", f"{n} ELM ST", "10001") for n in pairs])  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": f"d{n}", "raw_name": dn, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"a{n}"} for n, (dn, _, _) in pairs.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{n}", "party_id": f"d{n}", "role": "debtor"} for n in pairs],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{n}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for n in pairs])  # fmt: skip
    _write(o / "address" / "0.parquet",
           [_addr(f"m{n}", f"{n} Elm Street", "10001") for n in pairs])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": f"o{n}", "raw_name": on, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"m{n}"} for n, (_, on, _) in pairs.items()])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": f"p{n}", "party_id": f"o{n}"} for n in pairs])  # fmt: skip
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": f"p{n}"} for n in pairs])
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    m = dict(duckdb.connect().execute(
        f"SELECT debtor_party_id, rule_id FROM '{out.as_posix()}/matches.parquet' "
        f"WHERE decision = 'review'").fetchall())  # fmt: skip
    for n, (_, _, rule) in pairs.items():
        assert m.get(f"d{n}") == rule, n


def test_po_boxes_numbered_streets_company_and_and_no_zip_addresses(tmp_path: Path) -> None:
    """P.O. BOX 12 / POB 12 and 12 FIFTH AVENUE / 12 5TH AVE are one address; SMITH AND SONS
    and SMITH & SONS at one address are one company; an address without a ZIP meets the same
    street and city (review)."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    _write(d / "address" / "0.parquet", [
        _addr("a1", "P.O. Box 12", "10001"), _addr("a2", "12 Fifth Avenue", "10001"),
        _addr("a3", "40 ELM ST", "10001"),
        {"address_id": "a4", "line1": "3 PINE ST", "city": "Kent", "zip5": None}])  # fmt: skip
    people = {"d1": ("ANN LEE", "unknown", None), "d2": ("BO RAY", "unknown", None),
              "d3": ("SMITH AND SONS INC", "org", "SMITH AND SONS"),
              "d4": ("CY DOE", "unknown", None)}  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": kind, "org_name_norm": norm,
         "address_id": "a" + k[1]} for k, (n, kind, norm) in people.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{k}", "party_id": k, "role": "debtor"} for k in people],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{k}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for k in people])  # fmt: skip
    _write(
        o / "address" / "0.parquet",
        [
            _addr("m1", "POB 12", "10001"),
            _addr("m2", "12 5TH AVE", "10001"),
            _addr("m3", "40 Elm Street", "10001"),
            {"address_id": "m4", "line1": "3 Pine Street", "city": "KENT", "zip5": "06757"},
        ],
    )
    owners = [("o1", "LEE ANN", "unknown", None), ("o2", "RAY BO", "unknown", None),
              ("o3", "SMITH & SONS LLC", "org", "SMITH & SONS"),
              ("o4", "DOE CY", "unknown", None)]  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": kind, "org_name_norm": norm,
         "address_id": "m" + k[1]} for k, n, kind, norm in owners])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": "p" + k[1], "party_id": k} for k, *_ in owners])  # fmt: skip
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": "p" + k[1]} for k, *_ in owners])
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    m = {r[0]: r[1:] for r in duckdb.connect().execute(
        f"SELECT debtor_party_id, rule_id, decision FROM '{out.as_posix()}/matches.parquet'"
    ).fetchall()}  # fmt: skip
    assert m["d1"] == ("person_name_address", "auto")
    assert m["d2"] == ("person_name_address", "auto")
    assert m["d3"] == ("org_name_loose_address", "auto")
    assert m["d4"] == ("person_name_street_city", "review")


def test_a_mortgage_borrower_names_a_parcel_the_roll_does_not(tmp_path: Path) -> None:
    """A roll without owner names (06037-1, 06037-2): each mortgage's borrower owned the lot
    when it was recorded. A recent one matches like a roll owner; one older than
    RECORD_OWNER_AUTO_DAYS only reaches review (the lot may have been sold since)."""
    import datetime as dt

    lk = tmp_path / "lake"
    d, o, m = lk / "zz.debts", lk / "zz.parcels", lk / "zz.mortgages"
    _write(d / "address" / "0.parquet", [_addr("a1", "1 ELM ST", "90001"),
                                         _addr("a2", "2 OAK ST", "90001")])  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": f"d{n}", "raw_name": nm, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"a{n}"} for n, nm in ((1, "ANN LEE"), (2, "BO RAY"))])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{n}", "party_id": f"d{n}", "role": "debtor"} for n in (1, 2)],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{n}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for n in (1, 2)])  # fmt: skip
    _write(o / "address" / "0.parquet", [_addr("s1", "1 Elm Street", "90001"),
                                         _addr("s2", "2 OAK ST", "90001")])  # fmt: skip
    _write(o / "parcel" / "0.parquet", [
        {"parcel_uid": "06037-1", "situs_address_id": "s1"},
        {"parcel_uid": "06037-2", "situs_address_id": "s2"}])  # fmt: skip
    recent = (dt.datetime.now(dt.UTC).date() - dt.timedelta(days=30)).isoformat()
    _write(m / "instrument" / "0.parquet", [
        {"instrument_uid": "k1", "source_id": "zz.mortgages", "doc_type": "MORTGAGE",
         "recorded_on": recent, "principal_amount": 100.0},
        {"instrument_uid": "k2", "source_id": "zz.mortgages", "doc_type": "MORTGAGE",
         "recorded_on": "2015-01-01", "principal_amount": 100.0}])  # fmt: skip
    _write(m / "instrument_parcel" / "0.parquet", [
        {"instrument_uid": "k1", "parcel_uid": "06037-1"},
        {"instrument_uid": "k2", "parcel_uid": "06037-2"}])  # fmt: skip
    _write(m / "party" / "0.parquet", [
        {"party_id": "b1", "raw_name": "LEE ANN", "party_kind": "unknown",
         "org_name_norm": None, "address_id": None},
        {"party_id": "b2", "raw_name": "RAY BO", "party_kind": "unknown",
         "org_name_norm": None, "address_id": None},
        {"party_id": "l1", "raw_name": "TEST BANK NA", "party_kind": "org",
         "org_name_norm": "TEST BANK", "address_id": None}])  # fmt: skip
    _write(m / "instrument_party" / "0.parquet", [
        {"instrument_uid": "k1", "party_id": "b1", "role": "borrower"},
        {"instrument_uid": "k1", "party_id": "l1", "role": "lender"},
        {"instrument_uid": "k2", "party_id": "b2", "role": "borrower"}])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"], record_owner_sources=["zz.mortgages"])
    m_ = {r[0]: r[1:] for r in duckdb.connect().execute(
        f"SELECT debtor_party_id, parcel_uid, rule_id, decision, owner_basis "
        f"FROM '{out.as_posix()}/matches.parquet'").fetchall()}  # fmt: skip
    assert m_["d1"] == ("06037-1", "person_name_address", "auto", "mortgage:zz.mortgages")
    assert m_["d2"] == ("06037-2", "person_name_address", "review", "mortgage:zz.mortgages")


def test_a_debtor_who_moved_reaches_the_new_home(tmp_path: Path) -> None:
    """JOHN KING's lien is at 1 OLD RD, which he sold (the deed's seller, mailing 5 NEW ST):
    KING JOHN who owns 5 NEW ST is a review lead. ANN LEE's lien is at 9 A ST; her rental's
    roll mailed to 9 A ST one year and 8 B ST the next, so her home at 8 B ST is a lead too.
    A same-named owner at an address no record ties to the lien's address is none."""
    lk = tmp_path / "lake"
    d, o, dd = lk / "zz.debts", lk / "zz.parcels", lk / "zz.deeds"
    _write(d / "address" / "0.parquet", [_addr("a1", "1 OLD RD", "10001"),
                                         _addr("a2", "9 A ST", "10001")])  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": f"d{n}", "raw_name": nm, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"a{n}"} for n, nm in ((1, "JOHN KING"), (2, "ANN LEE"))])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{n}", "party_id": f"d{n}", "role": "debtor"} for n in (1, 2)],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{n}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for n in (1, 2)])  # fmt: skip
    _write(o / "address" / "0.parquet", [
        _addr("old", "1 OLD RD", "10001"), _addr("new", "5 NEW ST", "20002"),
        _addr("buyer", "70 FAR AVE", "10009"), _addr("ra", "9 A ST", "10001"),
        _addr("rb", "8 B ST", "20002"), _addr("rent", "3 RENT RD", "10001"),
        _addr("other", "44 ELSE ST", "10001")])  # fmt: skip
    rows = [
        ("b1", "TESTOWNER BUYER", "buyer", "36001-1"),
        ("k1", "KING JOHN", "new", "36001-2"),
        ("l1", "LEE ANN", "ra", "36001-3"),
        ("l2", "LEE ANN", "rb", "36001-3"),
        ("l3", "LEE ANN", "rb", "36001-4"),
        ("k2", "KING JOHN", "other", "36001-5"),
    ]
    _write(o / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": "unknown", "org_name_norm": None,
         "address_id": a} for k, n, a, _ in rows])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": u, "party_id": k} for k, _, _, u in rows])  # fmt: skip
    _write(o / "parcel" / "0.parquet", [
        {"parcel_uid": "36001-1", "situs_address_id": "old"},
        {"parcel_uid": "36001-2", "situs_address_id": "new"},
        {"parcel_uid": "36001-3", "situs_address_id": "rent"},
        {"parcel_uid": "36001-4", "situs_address_id": "rb"},
        {"parcel_uid": "36001-5", "situs_address_id": "other"}])  # fmt: skip
    _write(dd / "address" / "0.parquet", [_addr("g", "5 New Street", "20002")])
    _write(dd / "instrument" / "0.parquet", [
        {"instrument_uid": "k9", "source_id": "zz.deeds", "doc_type": "DEED",
         "recorded_on": "2025-06-01", "consideration": 300000.0}])  # fmt: skip
    _write(dd / "instrument_parcel" / "0.parquet",
           [{"instrument_uid": "k9", "parcel_uid": "36001-1"}])  # fmt: skip
    _write(dd / "party" / "0.parquet", [
        {"party_id": "g1", "raw_name": "KING JOHN", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "g"}])  # fmt: skip
    _write(dd / "instrument_party" / "0.parquet",
           [{"instrument_uid": "k9", "party_id": "g1", "role": "grantor"}])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"], record_owner_sources=["zz.deeds"])
    m = {(r[0], r[1]): r[2:] for r in duckdb.connect().execute(
        f"SELECT debtor_party_id, owner_party_id, rule_id, decision "
        f"FROM '{out.as_posix()}/matches.parquet'").fetchall()}  # fmt: skip
    assert m[("d1", "k1")] == ("person_name_former_address", "review")  # 5 NEW ST
    assert m[("d2", "l1")] == ("person_name_address", "auto")  # the rental's old-year record
    assert m[("d2", "l3")] == ("person_name_former_address", "review")  # her home, 8 B ST
    assert m[("d1", "k2")][0] != "person_name_former_address"  # no record ties 44 ELSE ST


def test_nickname_initials_and_spacing_together_are_a_review_lead(tmp_path: Path) -> None:
    """No single rule meets "BOB A SMITH" and "SMITH ROBERT" (a nickname and an initial) or
    "BILL O BRIEN" and "OBRIEN WILLIAM" (a nickname and spacing); read all at once they agree.
    JOHN A KING and JOHN B KING (two middle initials) never do."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    pairs = {"1": ("BOB A SMITH", "SMITH ROBERT", "person_loose_name_address"),
             "2": ("BILL O BRIEN", "OBRIEN WILLIAM", "person_loose_name_address"),
             "3": ("JOHN A KING", "KING JOHN B", None)}  # fmt: skip
    _write(d / "address" / "0.parquet",
           [_addr(f"a{n}", f"{n} ELM ST", "10001") for n in pairs])  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": f"d{n}", "raw_name": dn, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"a{n}"} for n, (dn, _, _) in pairs.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{n}", "party_id": f"d{n}", "role": "debtor"} for n in pairs],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{n}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for n in pairs])  # fmt: skip
    _write(o / "address" / "0.parquet",
           [_addr(f"m{n}", f"{n} Elm Street", "10001") for n in pairs])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": f"o{n}", "raw_name": on, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"m{n}"} for n, (_, on, _) in pairs.items()])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": f"p{n}", "party_id": f"o{n}"} for n in pairs])  # fmt: skip
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": f"p{n}"} for n in pairs])
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    m = dict(duckdb.connect().execute(
        f"SELECT debtor_party_id, rule_id FROM '{out.as_posix()}/matches.parquet' "
        f"WHERE rule_id <> 'person_name_zip'").fetchall())  # fmt: skip
    for n, (_, _, rule) in pairs.items():
        assert m.get(f"d{n}") == rule, n


def test_a_new_surname_at_the_same_address_is_a_review_lead(tmp_path: Path) -> None:
    """JANE SMITH's lien and JANE DOE on the roll at one address: a name change (review).
    MARY SMITH at JOHN SMITH's address is a household, not a name change."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    pairs = {"1": ("JANE SMITH", "DOE JANE", "person_name_change_address"),
             "2": ("JOHN SMITH", "SMITH MARY", None)}  # fmt: skip
    _write(d / "address" / "0.parquet",
           [_addr(f"a{n}", f"{n} ELM ST", "10001") for n in pairs])  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": f"d{n}", "raw_name": dn, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"a{n}"} for n, (dn, _, _) in pairs.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{n}", "party_id": f"d{n}", "role": "debtor"} for n in pairs],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{n}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for n in pairs])  # fmt: skip
    _write(o / "address" / "0.parquet",
           [_addr(f"m{n}", f"{n} Elm Street", "10001") for n in pairs])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": f"o{n}", "raw_name": on, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"m{n}"} for n, (_, on, _) in pairs.items()])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": f"p{n}", "party_id": f"o{n}"} for n in pairs])  # fmt: skip
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": f"p{n}"} for n in pairs])
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    m = dict(
        duckdb.connect()
        .execute(f"SELECT debtor_party_id, rule_id FROM '{out.as_posix()}/matches.parquet'")
        .fetchall()
    )
    assert m.get("d1") == "person_name_change_address"
    assert m.get("d2") is None


def test_two_independent_kinds_of_review_evidence_make_one_strong_link(tmp_path: Path) -> None:
    """JOHN KING's lien is at 1 OLD RD (he sold it: the deed's seller mails at 5 NEW ST), and
    KING JOHN owns 5 NEW ST in the same ZIP. Name + ZIP (place) and a former address are two
    independent kinds of evidence: one automatic link. ANN LEE has only name + ZIP: review."""
    lk = tmp_path / "lake"
    d, o, dd = lk / "zz.debts", lk / "zz.parcels", lk / "zz.deeds"
    _write(d / "address" / "0.parquet", [_addr("a1", "1 OLD RD", "10001"),
                                         _addr("a2", "2 ANY RD", "10001")])  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": f"d{n}", "raw_name": nm, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"a{n}"} for n, nm in ((1, "JOHN KING"), (2, "ANN LEE"))])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{n}", "party_id": f"d{n}", "role": "debtor"} for n in (1, 2)],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{n}", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0} for n in (1, 2)])  # fmt: skip
    _write(o / "address" / "0.parquet", [
        _addr("old", "1 OLD RD", "10001"), _addr("new", "5 NEW ST", "10001"),
        _addr("buyer", "70 FAR AVE", "10009"), _addr("ann", "9 ELSE ST", "10001")])  # fmt: skip
    rows = [("b1", "TESTOWNER BUYER", "buyer", "36001-1"), ("k1", "KING JOHN", "new", "36001-2"),
            ("l1", "LEE ANN", "ann", "36001-3")]  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": "unknown", "org_name_norm": None,
         "address_id": a} for k, n, a, _ in rows])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet",
           [{"parcel_uid": u, "party_id": k} for k, _, _, u in rows])  # fmt: skip
    _write(o / "parcel" / "0.parquet", [
        {"parcel_uid": "36001-1", "situs_address_id": "old"},
        {"parcel_uid": "36001-2", "situs_address_id": "new"},
        {"parcel_uid": "36001-3", "situs_address_id": "ann"}])  # fmt: skip
    _write(dd / "address" / "0.parquet", [_addr("g", "5 New Street", "10001")])
    _write(dd / "instrument" / "0.parquet", [
        {"instrument_uid": "k9", "source_id": "zz.deeds", "doc_type": "DEED",
         "recorded_on": "2025-06-01", "consideration": 300000.0}])  # fmt: skip
    _write(dd / "instrument_parcel" / "0.parquet",
           [{"instrument_uid": "k9", "parcel_uid": "36001-1"}])  # fmt: skip
    _write(dd / "party" / "0.parquet", [
        {"party_id": "g1", "raw_name": "KING JOHN", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "g"}])  # fmt: skip
    _write(dd / "instrument_party" / "0.parquet",
           [{"instrument_uid": "k9", "party_id": "g1", "role": "grantor"}])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"], record_owner_sources=["zz.deeds"])
    m = {r[0]: r[1:] for r in duckdb.connect().execute(
        f"SELECT debtor_party_id, rule_id, decision, corroborated_by "
        f"FROM '{out.as_posix()}/matches.parquet'").fetchall()}  # fmt: skip
    assert m["d1"] == ("person_name_zip", "auto", ["former_address", "place"])
    assert m["d2"] == ("person_name_zip", "review", None)


def test_an_estate_reaches_the_deceased_debtor_for_review(tmp_path: Path) -> None:
    """The roll prints the parcel's owner as "ESTATE OF JOHN SMITH": a lien against JOHN SMITH
    at its address is a review lead (the estate, not the person, holds title now)."""
    lk = tmp_path / "lake"
    d, o = lk / "zz.debts", lk / "zz.parcels"
    _write(d / "address" / "0.parquet", [_addr("a1", "1 ELM ST", "10001")])
    _write(d / "party" / "0.parquet", [
        {"party_id": "d1", "raw_name": "JOHN SMITH", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "a1"}])  # fmt: skip
    _write(d / "instrument_party" / "0.parquet",
           [{"instrument_uid": "i1", "party_id": "d1", "role": "debtor"}])  # fmt: skip
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": "i1", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2026-01-01", "principal_amount": 10.0}])  # fmt: skip
    _write(o / "address" / "0.parquet", [_addr("m1", "1 Elm Street", "10001")])
    _write(o / "party" / "0.parquet", [
        {"party_id": "o1", "raw_name": "ESTATE OF JOHN SMITH", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "m1"}])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet", [{"parcel_uid": "p1", "party_id": "o1"}])
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": "p1"}])
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"])
    assert duckdb.connect().execute(
        f"SELECT rule_id, decision, owner_name_variant "
        f"FROM '{out.as_posix()}/matches.parquet'").fetchall() == [
        ("person_name_address", "review", "estate")]  # fmt: skip


def test_the_owner_on_the_lien_date_is_reached_after_a_sale(tmp_path: Path) -> None:
    """JOHN KING bought 1 OLD RD (deed 2020) and sold it (deed 2025) to a buyer; his lien was
    recorded in 2023, at 1 OLD RD: on that date he owned it (review: sold since). ANN LEE's
    lien (2019) predates her deed (2020): she did not own it then."""
    lk = tmp_path / "lake"
    d, o, dd = lk / "zz.debts", lk / "zz.parcels", lk / "zz.deeds"
    _write(d / "address" / "0.parquet", [_addr("a1", "1 OLD RD", "10001"),
                                         _addr("a2", "2 NEW RD", "10001")])  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": f"d{n}", "raw_name": nm, "party_kind": "unknown", "org_name_norm": None,
         "address_id": f"a{n}"} for n, nm in ((1, "JOHN KING"), (2, "ANN LEE"))])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{n}", "party_id": f"d{n}", "role": "debtor"} for n in (1, 2)],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": "i1", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2023-05-01", "principal_amount": 10.0},
        {"instrument_uid": "i2", "source_id": "zz.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2019-05-01", "principal_amount": 10.0}])  # fmt: skip
    _write(o / "address" / "0.parquet", [_addr("s1", "1 OLD RD", "10001"),
                                         _addr("s2", "2 NEW RD", "10001"),
                                         _addr("bm", "70 FAR AVE", "10009")])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": "b1", "raw_name": "TESTOWNER BUYER", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "bm"},
        {"party_id": "b2", "raw_name": "TESTOWNER OTHER", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "bm"}])  # fmt: skip
    _write(
        o / "owner_snapshot" / "0.parquet",
        [{"parcel_uid": "36001-1", "party_id": "b1"}, {"parcel_uid": "36001-2", "party_id": "b2"}],
    )
    _write(
        o / "parcel" / "0.parquet",
        [
            {"parcel_uid": "36001-1", "situs_address_id": "s1"},
            {"parcel_uid": "36001-2", "situs_address_id": "s2"},
        ],
    )
    deeds = [("k1", "2020-01-01", "36001-1", "g1"), ("k2", "2025-01-01", "36001-1", "g2"),
             ("k3", "2020-01-01", "36001-2", "g3")]  # fmt: skip
    _write(dd / "instrument" / "0.parquet", [
        {"instrument_uid": k, "source_id": "zz.deeds", "doc_type": "DEED", "recorded_on": on,
         "consideration": 1.0} for k, on, _, _ in deeds])  # fmt: skip
    _write(dd / "instrument_parcel" / "0.parquet",
           [{"instrument_uid": k, "parcel_uid": u} for k, _, u, _ in deeds])  # fmt: skip
    _write(dd / "party" / "0.parquet", [
        {"party_id": "g1", "raw_name": "KING JOHN", "party_kind": "unknown",
         "org_name_norm": None, "address_id": None},
        {"party_id": "g2", "raw_name": "TESTOWNER BUYER", "party_kind": "unknown",
         "org_name_norm": None, "address_id": None},
        {"party_id": "g3", "raw_name": "LEE ANN", "party_kind": "unknown",
         "org_name_norm": None, "address_id": None}])  # fmt: skip
    _write(
        dd / "instrument_party" / "0.parquet",
        [{"instrument_uid": k, "party_id": g, "role": "grantee"} for k, _, _, g in deeds],
    )
    out = tmp_path / "out"
    run(lk, out, ["zz.debts"], ["zz.parcels"], record_owner_sources=["zz.deeds"])
    m = {(r[0], r[1]): r[2:] for r in duckdb.connect().execute(
        f"SELECT debtor_party_id, parcel_uid, rule_id, decision "
        f"FROM '{out.as_posix()}/matches.parquet'").fetchall()}  # fmt: skip
    assert m[("d1", "36001-1")] == ("person_owned_at_lien_address", "review")
    assert ("d2", "36001-2") not in m
