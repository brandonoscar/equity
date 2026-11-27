"""Registry links: owner companies -> people, debtors -> their companies' parcels."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from equity.matching.entities import org_key_macro
from equity.matching.orgs import classify
from equity.matching.resolve import run

from .test_resolve import _addr, _write

NAMES = ["Acme Holdings, L.L.C.", "ACME HOLDINGS LLC", "Smith & Sons Inc.", "LLC",
         "Blue Corp", "Professional Limited Liability Company Test PLLC", "Main St Partners",
         "Two Rivers Limited Liability Company", "THE CO", "x  y   Co."]  # fmt: skip


@pytest.mark.parametrize("name", NAMES)
def test_sql_org_key_agrees_with_the_loader(name: str) -> None:
    con = duckdb.connect()
    org_key_macro(con)
    row = con.execute("SELECT org_key(?)", [name]).fetchone()
    nc = classify(name)
    if nc.org_form:  # names with an entity form: the loader's org_name_norm, exactly
        assert row == (nc.org_name_norm or "",)


def test_owner_and_debtor_company_links(tmp_path: Path) -> None:
    lk = tmp_path / "lake"
    d, o, r = lk / "s.debts", lk / "s.parcels", lk / "s.sos"
    _write(d / "address" / "0.parquet", [_addr("da", "5 OAK LN", "10001")])
    _write(d / "party" / "0.parquet", [
        {"party_id": "d1", "raw_name": "ACME HOLDINGS L.L.C.", "party_kind": "org",
         "org_name_norm": "ACME HOLDINGS", "address_id": None},
        {"party_id": "d2", "raw_name": "ANN LEE", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "da"},
        {"party_id": "d3", "raw_name": "ANN Q LEE", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "da"},  # extra initial: no officer link
    ])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{n}", "party_id": f"d{n}", "role": "debtor"} for n in (1, 2, 3)],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{n}", "source_id": "s.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2025-01-01", "principal_amount": 10.0} for n in (1, 2, 3)])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": "o1", "raw_name": "ACME HOLDINGS LLC", "party_kind": "org",
         "org_name_norm": "ACME HOLDINGS", "address_id": None},
        {"party_id": "o2", "raw_name": "LEE VENTURES INC", "party_kind": "org",
         "org_name_norm": "LEE VENTURES", "address_id": None}])  # fmt: skip
    _write(
        o / "owner_snapshot" / "0.parquet",
        [{"parcel_uid": "p1", "party_id": "o1"}, {"parcel_uid": "p2", "party_id": "o2"}],
    )
    _write(o / "parcel" / "0.parquet", [
        {"parcel_uid": "p1", "situs_address_id": None},
        {"parcel_uid": "p2", "situs_address_id": None}])  # fmt: skip
    _write(o / "parcel_assessment" / "0.parquet", [
        {"parcel_uid": "p2", "tax_year": 2025, "appraised_total": 250000.0,
         "assessed_value": None}])  # fmt: skip
    _write(r / "business" / "0.parquet", [
        {"sos_id": "B1", "name": "ACME HOLDINGS, LLC", "status": "Active"},
        {"sos_id": "B2", "name": "Lee Ventures, Inc.", "status": "Active"}])  # fmt: skip
    _write(r / "party" / "0.parquet", [
        {"party_id": "h1", "raw_name": "BO RAY", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "ha"},
        {"party_id": "h2", "raw_name": "LEE ANN", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "hb"},
        {"party_id": "h3", "raw_name": "ANN LEE SR", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "hb"}])  # fmt: skip
    _write(r / "address" / "0.parquet", [
        {"address_id": "ha", "line1": "1 MAIN ST", "city": "X", "state": "NY", "zip5": "10002"},
        {"address_id": "hb", "line1": "5 Oak Lane", "city": "X", "state": "NY",
         "zip5": "10001"}])  # fmt: skip
    _write(
        r / "business_role" / "0.parquet",
        [
            {"sos_id": "B1", "party_id": "h1", "role": "member", "title": "MEMBER"},
            {"sos_id": "B2", "party_id": "h2", "role": "officer", "title": "PRESIDENT"},
        ],
    )
    out = tmp_path / "out"
    result = run(lk, out, ["s.debts"], ["s.parcels"], registry_sources=["s.sos"])
    con = duckdb.connect()
    q = lambda sql: con.execute(sql.replace("OUT", out.as_posix())).fetchall()  # noqa: E731
    assert q("SELECT parcel_uid, sos_id, ambiguous FROM 'OUT/owner_companies.parquet' "
             "ORDER BY 1") == [("p1", "B1", False), ("p2", "B2", False)]  # fmt: skip
    assert q("SELECT name, role FROM 'OUT/company_people.parquet' WHERE sos_id = 'B1'") == [
        ("BO RAY", "member")
    ]
    links = q("SELECT debtor_party_id, sos_id, rule_id, decision "
              "FROM 'OUT/debtor_companies.parquet' ORDER BY 1")  # fmt: skip
    # The org debtor is the owner company; ANN LEE is B2's president at the same address
    # (street spelled differently); ANN Q LEE has an extra initial and never links.
    assert links == [("d1", "B1", "org_name_registry", "auto"),
                     ("d2", "B2", "person_officer_address", "auto")]  # fmt: skip
    assert q("SELECT debtor_party_id, parcel_uid, parcel_value "
             "FROM 'OUT/debtor_company_parcels.parquet' ORDER BY 1") == [
        ("d1", "p1", None), ("d2", "p2", 250000.0)]  # fmt: skip
    reg = result["registries"]
    assert isinstance(reg, dict)
    assert reg["owner_orgs_linked"] == 2 and reg["debtors_with_company_parcels_auto"] == 2


def test_a_former_name_still_reaches_the_entity(tmp_path: Path) -> None:
    lk = tmp_path / "lake"
    d, o, r, h = lk / "s.debts", lk / "s.parcels", lk / "s.sos", lk / "s.names"
    _write(d / "party" / "0.parquet", [
        {"party_id": "d1", "raw_name": "X", "party_kind": "unknown", "org_name_norm": None,
         "address_id": None}])  # fmt: skip
    _write(d / "instrument_party" / "0.parquet",
           [{"instrument_uid": "i1", "party_id": "d1", "role": "debtor"}])  # fmt: skip
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": "i1", "source_id": "s.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2025-01-01", "principal_amount": 1.0}])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": "o1", "raw_name": "REIN TEEN TOURS INC", "party_kind": "org",
         "org_name_norm": "REIN TEEN TOURS", "address_id": None}])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet", [{"parcel_uid": "p1", "party_id": "o1"}])
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": "p1", "situs_address_id": None}])
    _write(
        r / "business" / "0.parquet",
        [{"sos_id": "100", "name": "NORMAN'S TEEN TOURS, INC.", "status": "Active"}],
    )
    _write(h / "business" / "0.parquet", [
        {"sos_id": "100", "name": "REIN TEEN TOURS, INC.", "status": "former name"},
        {"sos_id": "100", "name": "NORMAN'S TEEN TOURS, INC.",
         "status": "active name"}])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["s.debts"], ["s.parcels"], registry_sources=["s.sos", "s.names"])
    got = duckdb.connect().execute(
        f"SELECT parcel_uid, sos_id, business_name, ambiguous "
        f"FROM '{out.as_posix()}/owner_companies.parquet'").fetchall()  # fmt: skip
    # The deed is in the old name; the entity shows under its current registry name.
    assert got == [("p1", "100", "NORMAN'S TEEN TOURS, INC.", False)]


def test_registries_keep_only_the_runs_state(tmp_path: Path) -> None:
    """National lists name businesses everywhere: with state_fips only the run's state's
    businesses link (jurisdiction is a state or county FIPS code)."""
    lk = tmp_path / "lake"
    d, o, r = lk / "s.debts", lk / "s.parcels", lk / "us.carriers"
    _write(d / "party" / "0.parquet", [
        {"party_id": "d1", "raw_name": "ACME HAULING LLC", "party_kind": "org",
         "org_name_norm": "ACME HAULING", "address_id": None},
        {"party_id": "d2", "raw_name": "BLUE FREIGHT INC", "party_kind": "org",
         "org_name_norm": "BLUE FREIGHT", "address_id": None}])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{n}", "party_id": f"d{n}", "role": "debtor"} for n in (1, 2)],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{n}", "source_id": "s.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2025-01-01", "principal_amount": 10.0} for n in (1, 2)])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": "o9", "raw_name": "NOBODY", "party_kind": "person",
         "org_name_norm": None, "address_id": None}])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet", [{"parcel_uid": "36001-1", "party_id": "o9"}])
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": "36001-1", "situs_address_id": None}])
    _write(r / "business" / "0.parquet", [
        {"sos_id": "USDOT:1", "name": "Acme Hauling, LLC", "status": "A", "jurisdiction": "36001"},
        {"sos_id": "USDOT:2", "name": "Blue Freight Inc", "status": "A", "jurisdiction": "06037"},
    ])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["s.debts"], ["s.parcels"], registry_sources=["us.carriers"], state_fips="36")
    got = (
        duckdb.connect()
        .execute(f"SELECT debtor_party_id, sos_id FROM '{out.as_posix()}/debtor_companies.parquet'")
        .fetchall()
    )
    assert got == [("d1", "USDOT:1")]  # Blue Freight is a California business


def test_officer_links_see_through_units_nicknames_and_typos(tmp_path: Path) -> None:
    """A filing at "5 OAK LN STE 2" is the debtor's "5 OAK LN" (auto with the same name); at
    the officer's address, a nickname or a one-letter typo of the name is a review link."""
    lk = tmp_path / "lake"
    d, o, r = lk / "s.debts", lk / "s.parcels", lk / "s.sos"
    _write(d / "address" / "0.parquet", [_addr("da", "5 OAK LN", "10001"),
                                         _addr("db", "6 ELM ST", "10001"),
                                         _addr("dc", "7 FIR ST", "10001")])  # fmt: skip
    debtors = {"d1": ("ANN LEE", "da"), "d2": ("BOB RAY", "db"), "d3": ("CY DOEE", "dc")}
    _write(d / "party" / "0.parquet", [
        {"party_id": k, "raw_name": n, "party_kind": "unknown", "org_name_norm": None,
         "address_id": a} for k, (n, a) in debtors.items()])  # fmt: skip
    _write(
        d / "instrument_party" / "0.parquet",
        [{"instrument_uid": f"i{k}", "party_id": k, "role": "debtor"} for k in debtors],
    )
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": f"i{k}", "source_id": "s.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2025-01-01", "principal_amount": 10.0} for k in debtors])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": "o1", "raw_name": "SOMEONE", "party_kind": "unknown",
         "org_name_norm": None, "address_id": None}])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet", [{"parcel_uid": "p1", "party_id": "o1"}])
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": "p1", "situs_address_id": None}])
    _write(
        r / "business" / "0.parquet",
        [{"sos_id": f"B{n}", "name": f"CO {n} LLC", "status": "Active"} for n in (1, 2, 3)],
    )
    _write(r / "party" / "0.parquet", [
        {"party_id": "h1", "raw_name": "ANN LEE", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "ha"},
        {"party_id": "h2", "raw_name": "ROBERT RAY", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "hb"},
        {"party_id": "h3", "raw_name": "CY DOE", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "hc"}])  # fmt: skip
    _write(r / "address" / "0.parquet", [
        {"address_id": "ha", "line1": "5 OAK LN STE 2", "city": "X", "state": "NY",
         "zip5": "10001"},
        {"address_id": "hb", "line1": "6 ELM ST", "city": "X", "state": "NY", "zip5": "10001"},
        {"address_id": "hc", "line1": "7 FIR ST", "city": "X", "state": "NY",
         "zip5": "10001"}])  # fmt: skip
    _write(r / "business_role" / "0.parquet", [
        {"sos_id": f"B{n}", "party_id": f"h{n}", "role": "officer", "title": "PRESIDENT"}
        for n in (1, 2, 3)])  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["s.debts"], ["s.parcels"], registry_sources=["s.sos"])
    links = duckdb.connect().execute(
        f"SELECT debtor_party_id, sos_id, rule_id, decision "
        f"FROM '{out.as_posix()}/debtor_companies.parquet' ORDER BY 1").fetchall()  # fmt: skip
    assert links == [("d1", "B1", "person_officer_address", "auto"),
                     ("d2", "B2", "person_officer_nickname", "review"),
                     ("d3", "B3", "person_officer_typo", "review")]  # fmt: skip


def test_a_joint_role_holder_is_each_person(tmp_path: Path) -> None:
    """A registry that prints two members in one string ("ANN & BO LEE") lists each."""
    lk = tmp_path / "lake"
    d, o, r = lk / "s.debts", lk / "s.parcels", lk / "s.sos"
    _write(d / "address" / "0.parquet", [_addr("da", "5 OAK LN", "10001")])
    _write(d / "party" / "0.parquet", [
        {"party_id": "d1", "raw_name": "BO LEE", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "da"}])  # fmt: skip
    _write(d / "instrument_party" / "0.parquet",
           [{"instrument_uid": "i1", "party_id": "d1", "role": "debtor"}])  # fmt: skip
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": "i1", "source_id": "s.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2025-01-01", "principal_amount": 10.0}])  # fmt: skip
    _write(o / "party" / "0.parquet", [
        {"party_id": "o1", "raw_name": "SOMEONE", "party_kind": "unknown",
         "org_name_norm": None, "address_id": None}])  # fmt: skip
    _write(o / "owner_snapshot" / "0.parquet", [{"parcel_uid": "p1", "party_id": "o1"}])
    _write(o / "parcel" / "0.parquet", [{"parcel_uid": "p1", "situs_address_id": None}])
    _write(r / "business" / "0.parquet", [{"sos_id": "B1", "name": "LEE LLC", "status": "Active"}])
    _write(r / "party" / "0.parquet", [
        {"party_id": "h1", "raw_name": "ANN & BO LEE", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "ha"}])  # fmt: skip
    _write(
        r / "address" / "0.parquet",
        [{"address_id": "ha", "line1": "5 OAK LN", "city": "X", "state": "NY", "zip5": "10001"}],
    )
    _write(
        r / "business_role" / "0.parquet",
        [{"sos_id": "B1", "party_id": "h1", "role": "member", "title": "MEMBER"}],
    )
    out = tmp_path / "out"
    run(lk, out, ["s.debts"], ["s.parcels"], registry_sources=["s.sos"])
    links = (
        duckdb.connect()
        .execute(
            f"SELECT debtor_party_id, sos_id, rule_id "
            f"FROM '{out.as_posix()}/debtor_companies.parquet'"
        )
        .fetchall()
    )
    assert links == [("d1", "B1", "person_officer_address")]
