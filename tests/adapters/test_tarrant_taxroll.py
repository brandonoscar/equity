"""Tarrant County tax roll: past-due receivables summed per real property account."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from equity.adapters.base import Fetched
from equity.adapters.tx.tarrant_taxroll import TarrantTaxRollDelinquent, delinquent_accounts

AT = datetime(2025, 12, 31, tzinfo=UTC)


def _fixed(width: int, fields: dict[tuple[int, int], str]) -> str:
    line = [" "] * width
    for (a, b), v in fields.items():
        line[a - 1 : b] = list(v.ljust(b - a + 1)[: b - a + 1])
    return "".join(line)


def _master(account: str, roll: str, owner: str, cad: str = "") -> str:
    return _fixed(781, {(1, 30): account, (34, 35): roll, (169, 198): cad, (327, 376): owner,
                        (427, 456): "1 MAIN ST", (487, 516): "FORT WORTH", (517, 536): "TX",
                        (537, 554): "76102"})  # fmt: skip


def _rec(account: str, year: str, due: str, delinquent_on: str, judged: str = "01/01/9999",
         lawsuit: str = "") -> str:  # fmt: skip
    return _fixed(267, {(1, 30): account, (31, 34): year, (79, 90): due,
                        (91, 100): delinquent_on, (111, 120): judged,
                        (121, 138): lawsuit})  # fmt: skip


def test_past_due_receivables_are_summed_for_real_property() -> None:
    master = [_master("00000000001", "01", "ANN LEE", "00012345"),
              _master("00000000002", "02", "BIZ INC"),  # personal property
              _master("00000000003", "01", "BO RAY")]  # fmt: skip
    rec = [_rec("00000000001", "2023", "000000100.00", "02/01/2024", "06/30/2025", "C-1"),
           _rec("00000000001", "2024", "000000050.50", "02/01/2025"),
           _rec("00000000001", "2025", "000000999.00", "02/01/2026"),  # not yet delinquent
           _rec("00000000002", "2024", "000000010.00", "02/01/2025"),
           _rec("00000000003", "2024", "000000000.00", "02/01/2025")]  # paid  # fmt: skip
    rows = delinquent_accounts(master, rec, date(2025, 12, 31))
    assert [r["account"] for r in rows] == ["00000000001"]
    r = rows[0]
    assert (r["amount"], r["years"], r["judged"], r["lawsuits"]) == (
        "150.50",
        [2023, 2024],
        "2025-06-30",
        ["C-1"],
    )
    body = json.dumps({"file": "TaxRoll.zip", "rows": rows}).encode()
    out = [(t.table, dict(t.row)) for t in TarrantTaxRollDelinquent().normalize(
        Fetched("tx.tarrant.tax_roll_delinquent", "x", AT, 200, body, ""))]  # fmt: skip
    (inst,) = [x for t, x in out if t == "instrument"]
    assert (inst["doc_type"], inst["recorded_on"], str(inst["principal_amount"])) == (
        "COURT_ORDER",
        date(2025, 6, 30),
        "150.50",
    )
    assert not [x for t, x in out if t == "instrument_parcel"]  # cad id is not the PROP_ID
    assert {x["raw_name"] for t, x in out if t == "party"} >= {"ANN LEE"}


def test_personal_property_accounts_are_roll_02() -> None:
    from equity.adapters.tx.tarrant_taxroll import MASTER, REC, TarrantPersonalPropertyDelinquent

    master = [_master("00000000001", "01", "ANN LEE"), _master("00000000002", "02", "BIZ INC")]
    rec = [_rec("00000000001", "2024", "000000050.00", "02/01/2025"),
           _rec("00000000002", "2024", "000000010.00", "02/01/2025")]  # fmt: skip
    rows = delinquent_accounts(master, rec, date(2025, 12, 31), MASTER, REC, ("02",))
    assert [r["account"] for r in rows] == ["00000000002"]
    body = json.dumps({"file": "TaxRoll.zip", "rows": rows}).encode()
    out = [(t.table, dict(t.row)) for t in TarrantPersonalPropertyDelinquent().normalize(
        Fetched("tx.tarrant.personal_property_delinquent", "x", AT, 200, body, ""))]  # fmt: skip
    (inst,) = [x for t, x in out if t == "instrument"]
    assert (
        inst["doc_type_raw"]
        == "Tarrant County delinquent business personal property tax (year 2024)"
    )


def test_mineral_tax_debts_link_to_the_mineral_interest_parcel() -> None:
    from equity.adapters.tx.tarrant_taxroll import MASTER, REC, TarrantMineralTaxDelinquent

    master = [_master("00010335366", "03", "OLIVER TR"), _master("00000000001", "01", "ANN LEE")]
    rec = [_rec("00010335366", "2024", "000000032.15", "02/01/2025"),
           _rec("00000000001", "2024", "000000050.00", "02/01/2025")]  # fmt: skip
    rows = delinquent_accounts(master, rec, date(2025, 12, 31), MASTER, REC, ("03",))
    body = json.dumps({"file": "TaxRoll.zip", "rows": rows}).encode()
    out = [(t.table, dict(t.row)) for t in TarrantMineralTaxDelinquent().normalize(
        Fetched("tx.tarrant.mineral_tax_delinquent", "x", AT, 200, body, ""))]  # fmt: skip
    (inst,) = [x for t, x in out if t == "instrument"]
    assert inst["doc_type_raw"] == "Tarrant County delinquent mineral interest tax (year 2024)"
    assert [x["parcel_uid"] for t, x in out if t == "instrument_parcel"] == [
        "48439-MIN-00010335366"]  # fmt: skip
