"""Out-of-state owners: a debtor reaches property in another state mailed to their home."""

from __future__ import annotations

from pathlib import Path

import duckdb

from equity.matching import crossstate
from equity.matching.resolve import run

from .test_resolve import _write


def test_a_parcel_mailed_from_another_state_reaches_the_debtor(tmp_path: Path) -> None:
    lk = tmp_path / "lake"
    d, ny, fl = lk / "ny.t.debts", lk / "ny.t.parcels", lk / "fl.t.parcels"
    _write(d / "address" / "0.parquet", [
        {"address_id": "a1", "line1": "1 ELM ST", "city": "TESTVILLE", "state": "NY",
         "zip5": "10001"}])  # fmt: skip
    _write(d / "party" / "0.parquet", [
        {"party_id": "d1", "raw_name": "ANN LEE", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "a1"}])  # fmt: skip
    _write(d / "instrument_party" / "0.parquet",
           [{"instrument_uid": "i1", "party_id": "d1", "role": "debtor"}])  # fmt: skip
    _write(d / "instrument" / "0.parquet", [
        {"instrument_uid": "i1", "source_id": "ny.t.debts", "doc_type": "TAX_LIEN_STATE",
         "recorded_on": "2025-01-01", "principal_amount": 10.0}])  # fmt: skip
    # The NY roll: someone else.
    _write(ny / "address" / "0.parquet", [
        {"address_id": "n1", "line1": "5 OAK ST", "city": "TESTVILLE", "state": "NY",
         "zip5": "10001"}])  # fmt: skip
    _write(ny / "party" / "0.parquet", [
        {"party_id": "n1", "raw_name": "TESTOWNER ONE", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "n1"}])  # fmt: skip
    _write(ny / "owner_snapshot" / "0.parquet", [{"parcel_uid": "36001-1", "party_id": "n1"}])
    _write(ny / "parcel" / "0.parquet", [{"parcel_uid": "36001-1"}])
    # The FL roll: LEE ANN's parcel, its bill mailed to her NY home; RAY BO's mailed in FL.
    _write(fl / "address" / "0.parquet", [
        {"address_id": "f1", "line1": "1 Elm Street", "city": "TESTVILLE", "state": "NY",
         "zip5": "10001"},
        {"address_id": "f2", "line1": "1 ELM ST", "city": "TESTTOWN", "state": "FL",
         "zip5": "33001"}])  # fmt: skip
    _write(fl / "party" / "0.parquet", [
        {"party_id": "f1", "raw_name": "LEE ANN", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "f1"},
        {"party_id": "f2", "raw_name": "RAY BO", "party_kind": "unknown",
         "org_name_norm": None, "address_id": "f2"}])  # fmt: skip
    _write(fl / "owner_snapshot" / "0.parquet", [
        {"parcel_uid": "12086-1", "party_id": "f1"},
        {"parcel_uid": "12086-2", "party_id": "f2"}])  # fmt: skip
    _write(fl / "parcel" / "0.parquet", [{"parcel_uid": "12086-1"}, {"parcel_uid": "12086-2"}])
    index = tmp_path / "derived" / "_national" / "out_of_state_owners.parquet"
    n = crossstate.build(lk, index, sources=["ny.t.parcels", "fl.t.parcels"])
    assert n == 1  # only LEE ANN's FL parcel is mailed out of its state
    con = duckdb.connect()
    assert con.execute(f"SELECT parcel_uid, parcel_state, mail_state, source_id "
                       f"FROM '{index.as_posix()}'").fetchall() == [
        ("12086-1", "FL", "NY", "fl.t.parcels")]  # fmt: skip
    out = tmp_path / "out"
    run(lk, out, ["ny.t.debts"], ["ny.t.parcels"], out_of_state=(index, "NY"))
    assert con.execute(
        f"SELECT debtor_party_id, parcel_uid, rule_id, decision, owner_basis "
        f"FROM '{out.as_posix()}/matches.parquet'").fetchall() == [
        ("d1", "12086-1", "person_name_address", "auto", "out_of_state")]  # fmt: skip
    # A run without the index (or for another state) sees nothing of it.
    out2 = tmp_path / "out2"
    run(lk, out2, ["ny.t.debts"], ["ny.t.parcels"], out_of_state=(index, "FL"))
    assert con.execute(f"SELECT count(*) FROM '{out2.as_posix()}/matches.parquet'"
                       ).fetchone() == (0,)  # fmt: skip
