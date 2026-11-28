"""Dallas County TRW tax roll: past-due real property records summed per CAD account."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from equity.adapters.base import Fetched
from equity.adapters.tx.dallas_trw import DallasTaxRollDelinquent, delinquent_accounts, parse_record

AT = datetime(2025, 12, 31, tzinfo=UTC)


def _rec(**f: str) -> str:
    """One 534-character TRW record with the given fields at their layout positions."""
    pos = {"account": (1, 34), "year": (35, 38), "jurisdiction": (39, 42),
           "cad_account": (43, 76), "date_paid": (93, 100), "due_date": (101, 108),
           "suit": (122, 122), "cause": (123, 162), "bankrupt": (163, 163),
           "owner": (226, 265), "addr2": (266, 305), "city": (386, 425), "state": (426, 427),
           "zip": (428, 439), "roll": (440, 440), "agreement": (489, 489),
           "total_due": (490, 500)}  # fmt: skip
    line = [" "] * 534
    for k, v in f.items():
        a, b = pos[k]
        line[a - 1 : b] = list(v.ljust(b - a + 1)[: b - a + 1])
    return "".join(line)


def test_parse_record_reads_layout_positions() -> None:
    r = parse_record(_rec(account="A1", cad_account="00000455263000000", total_due="00000012345"))
    assert (r["cad_account"], r["total_due"]) == ("00000455263000000", "00000012345")


def test_past_due_real_property_is_summed_per_account() -> None:
    lines = [
        _rec(cad_account="C1", year="2023", due_date="20240201", total_due="00000010000",
             roll="R", owner="ANN LEE", addr2="1 MAIN ST", city="DALLAS", state="TX",
             zip="75201", suit="J", cause="TX-24-00001"),
        _rec(cad_account="C1", year="2024", due_date="20250201", total_due="00000005050",
             roll="R", owner="ANN LEE", agreement="Y"),
        _rec(cad_account="C1", year="2025", due_date="20260201", total_due="00000009999",
             roll="R", owner="ANN LEE"),  # not yet due on 2025-12-31
        _rec(cad_account="C2", year="2024", due_date="20250201", total_due="00000001000",
             roll="P", owner="BIZ INC"),  # personal property: left out
        _rec(cad_account="C3", year="2024", due_date="20250201", total_due="00000002000",
             roll="R", owner="BO RAY", date_paid="20251001"),  # paid
    ]  # fmt: skip
    rows = delinquent_accounts(iter(lines), date(2025, 12, 31))
    assert [r["cad_account"] for r in rows] == ["C1"]
    c1 = rows[0]
    assert (c1["cents"], c1["years"], c1["suits"], c1["agreement"]) == (
        15050,
        [2023, 2024],
        ["J:TX-24-00001"],
        True,
    )
    body = json.dumps({"file": "flat404.x", "rows": rows}).encode()
    out = [(r.table, dict(r.row)) for r in DallasTaxRollDelinquent().normalize(
        Fetched("tx.dallas.tax_roll_delinquent", "x", AT, 200, body, ""))]  # fmt: skip
    (inst,) = [r for t, r in out if t == "instrument"]
    assert (str(inst["principal_amount"]), inst["recorded_on"]) == ("150.5", date(2023, 1, 1))
    assert (
        "tax suit J:TX-24-00001" in inst["doc_type_raw"]
        and "payment agreement" in inst["doc_type_raw"]
    )
    assert [r["parcel_uid"] for t, r in out if t == "instrument_parcel"] == ["48113-C1"]
    assert {r["role"] for t, r in out if t == "instrument_party"} == {"debtor", "creditor"}


def test_commercial_is_real_property_and_personal_property_is_its_own_source() -> None:
    from equity.adapters.tx.dallas_trw import DallasPersonalPropertyDelinquent

    lines = [_rec(cad_account="C1", year="2024", due_date="20250201", total_due="00000001000",
                  roll="C", owner="MALL LLC"),
             _rec(cad_account="P1", year="2024", due_date="20250201", total_due="00000000500",
                  roll="P", owner="BIZ INC")]  # fmt: skip
    assert [r["cad_account"] for r in delinquent_accounts(iter(lines), date(2025, 12, 31))] == [
        "C1"]  # fmt: skip
    rows = delinquent_accounts(iter(lines), date(2025, 12, 31), ("P",))
    body = json.dumps({"file": "flat404.x", "rows": rows}).encode()
    out = [(r.table, dict(r.row)) for r in DallasPersonalPropertyDelinquent().normalize(
        Fetched("tx.dallas.personal_property_delinquent", "x", AT, 200, body, ""))]  # fmt: skip
    (inst,) = [r for t, r in out if t == "instrument"]
    assert (
        inst["doc_type_raw"]
        == "Dallas County delinquent business personal property tax (year 2024)"
    )
    assert not [r for t, r in out if t == "instrument_parcel"]


def test_mineral_records_are_their_own_source() -> None:
    from equity.adapters.tx.dallas_trw import DallasMineralTaxDelinquent

    lines = [_rec(cad_account="N1", year="2024", due_date="20250201", total_due="00000000300",
                  roll="N", owner="ROYALTY LLC")]  # fmt: skip
    rows = delinquent_accounts(iter(lines), date(2025, 12, 31), ("N",))
    body = json.dumps({"file": "flat404.x", "rows": rows}).encode()
    out = [(r.table, dict(r.row)) for r in DallasMineralTaxDelinquent().normalize(
        Fetched("tx.dallas.mineral_tax_delinquent", "x", AT, 200, body, ""))]  # fmt: skip
    (inst,) = [r for t, r in out if t == "instrument"]
    assert inst["doc_type_raw"] == "Dallas County delinquent mineral interest tax (year 2024)"
    assert not [r for t, r in out if t == "instrument_parcel"]
