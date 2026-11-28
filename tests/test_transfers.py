"""Transfers after a debt and nominee LLCs (equity.matching.transfers)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from equity.matching import transfers
from equity.matching.resolve import run

from .test_resolve import _addr, _write, lake  # noqa: F401 (the lake fixture)


def _deed(uid: str, on: str, price: float | None, parcel: str) -> dict[str, object]:
    return {"instrument_uid": uid, "source_id": "zz.deeds", "doc_type": "DEED",
            "recorded_on": on, "consideration": price, "parcel": parcel}  # fmt: skip


def test_deeds_after_a_debt_are_flagged_with_nominee_companies(
    lake: Path,  # noqa: F811 (the pytest fixture from test_resolve)
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transfers, "nominal_max", lambda config_dir=None: 100.0)
    # The fixture lake: d1 JOHN A SMITH owes i1 (2025-01-01) and is auto-matched to p1.
    # d3 MARY JONES owes i3 in county 36001 (jurisdiction) and matches nothing automatically.
    inst = lake / "zz.debts" / "instrument" / "0.parquet"
    rows = duckdb.connect().execute(f"SELECT * FROM '{inst.as_posix()}'").fetchall()
    cols = [c[0] for c in duckdb.connect().execute(f"DESCRIBE SELECT * FROM '{inst}'").fetchall()]
    debts = [dict(zip(cols, r, strict=True)) for r in rows]
    for d in debts:
        d["recorded_on"] = str(d["recorded_on"])
        d["jurisdiction"] = "36001" if d["instrument_uid"] == "i3" else None
    _write(inst, debts)
    deeds = lake / "zz.deeds"
    rows_d = [_deed("k1", "2025-06-01", 10.0, "p1"),        # after the debt, nominal, to an LLC
              _deed("k0", "2024-06-01", 300000.0, "p1"),    # before the debt: not flagged
              _deed("k3", "2025-03-01", 250000.0, "36001-77"),  # same county, no parcel match
              _deed("k4", "2025-03-01", 1.0, "99999-1")]  # elsewhere: not flagged  # fmt: skip
    _write(deeds / "instrument" / "0.parquet",
           [{k: v for k, v in r.items() if k != "parcel"} for r in rows_d])  # fmt: skip
    _write(
        deeds / "instrument_parcel" / "0.parquet",
        [{"instrument_uid": r["instrument_uid"], "parcel_uid": r["parcel"]} for r in rows_d],
    )
    _write(deeds / "party" / "0.parquet", [
        {"party_id": "g1", "raw_name": "SMITH JOHN A", "party_kind": "person",
         "org_name_norm": None, "address_id": None},
        {"party_id": "g2", "raw_name": "SMITH HOLDINGS LLC", "party_kind": "org",
         "org_name_norm": "SMITH HOLDINGS", "address_id": None},
        {"party_id": "g3", "raw_name": "JONES MARY", "party_kind": "person",
         "org_name_norm": None, "address_id": None},
        {"party_id": "g4", "raw_name": "ROE RICHARD", "party_kind": "person",
         "org_name_norm": None, "address_id": None}])  # fmt: skip
    _write(deeds / "instrument_party" / "0.parquet", [
        {"instrument_uid": "k1", "party_id": "g1", "role": "grantor"},
        {"instrument_uid": "k1", "party_id": "g2", "role": "grantee"},
        {"instrument_uid": "k0", "party_id": "g1", "role": "grantor"},
        {"instrument_uid": "k3", "party_id": "g3", "role": "grantor"},
        {"instrument_uid": "k3", "party_id": "g4", "role": "grantee"},
        {"instrument_uid": "k4", "party_id": "g1", "role": "grantor"}])  # fmt: skip
    reg = lake / "zz.sos"
    _write(
        reg / "business" / "0.parquet",
        [{"sos_id": "B9", "name": "Smith Holdings, LLC", "status": "Active"}],
    )
    _write(reg / "party" / "0.parquet", [
        {"party_id": "h9", "raw_name": "JOHN A SMITH", "party_kind": "person",
         "org_name_norm": None, "address_id": "ha9"}])  # fmt: skip
    _write(reg / "address" / "0.parquet", [_addr("ha9", "1 ELM ST", "10009")])
    _write(
        reg / "business_role" / "0.parquet",
        [{"sos_id": "B9", "party_id": "h9", "role": "manager", "title": "MANAGER"}],
    )
    out = tmp_path / "out"
    result = run(lake, out, ["zz.debts"], ["zz.parcels"], registry_sources=["zz.sos"],
                 deed_sources=["zz.deeds"])  # fmt: skip
    got = {r[0]: r[1:] for r in duckdb.connect().execute(
        "SELECT deed_uid, debtor_party_id, parcel_uid, nominal, grantee_org, nominee_llc, "
        f"nominee_sos_id, rule_id, decision FROM '{out.as_posix()}/transfer_flags.parquet'"
    ).fetchall()}  # fmt: skip
    assert got["k1"] == ("d1", "p1", True, True, True, "B9", "on_matched_parcel", "auto")
    assert got["k3"] == ("d3", "36001-77", False, False, False, None, "same_county", "review")
    assert "k0" not in got and "k4" not in got
    t = result["transfers"]
    assert isinstance(t, dict)
    assert (t["deeds"], t["nominee_llc"], t["debtors_with_transfers_auto"]) == (4, 1, 1)


def test_the_nominal_flag_stays_unknown_while_the_threshold_is_unset(tmp_path: Path) -> None:
    (tmp_path / "rules.yaml").write_text("transfer_flags:\n  nominal_consideration_max: null\n")
    assert transfers.nominal_max(tmp_path) is None
    (tmp_path / "rules.yaml").write_text("transfer_flags:\n  nominal_consideration_max: 100\n")
    assert transfers.nominal_max(tmp_path) == 100.0
    assert transfers.nominal_max() == 100.0  # the repo's rules.yaml: Brandon set it 2026-11-28
