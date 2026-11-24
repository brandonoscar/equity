"""SBA PPP charge-offs (equity.adapters.federal.sba_ppp)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from equity.adapters.base import Fetched
from equity.adapters.federal.sba_ppp import SBAPPPChargeOffs, charged_off, unforgiven

AT = datetime(2026, 11, 24, tzinfo=UTC)
HEAD = ("LoanNumber,DateApproved,BorrowerName,BorrowerAddress,BorrowerCity,BorrowerState,"
        "BorrowerZip,LoanStatusDate,LoanStatus,CurrentApprovalAmount,ForgivenessAmount,"
        "ServicingLenderName,ProjectCountyName,ProjectState\n")  # fmt: skip


def test_only_charged_off_rows_are_kept_and_the_balance_is_unforgiven() -> None:
    body = (HEAD
            + "1,04/30/2020,ACME LLC,1 MAIN ST,Richmond,VA,23226-1,11/20/2021,Charged Off,"
              "84207,4207,Celtic Bank,HENRICO,VA\n"
            + "2,04/30/2020,BETA INC,2 MAIN ST,Richmond,VA,23226,11/20/2021,Paid in Full,"
              "100,100,Celtic Bank,HENRICO,VA\n"
            + "3,04/30/2020,Exemption 6,,,,,11/20/2021,Charged Off,500,,Lender,,\n")  # fmt: skip
    rows = charged_off(body.encode())
    assert [r["LoanNumber"] for r in rows] == ["1", "3"]
    assert unforgiven(rows[0]) == Decimal("80000")
    assert unforgiven({"CurrentApprovalAmount": "10", "ForgivenessAmount": "10"}) is None
    fetched = Fetched("us.sba.ppp_chargeoffs", "x", AT, 200,
                      json.dumps({"rows": rows}).encode(), "")  # fmt: skip
    out = [(r.table, dict(r.row)) for r in SBAPPPChargeOffs().normalize(fetched)]
    (inst,) = [r for t, r in out if t == "instrument"]  # the withheld name is not loaded
    assert (inst["instrument_number"], inst["principal_amount"]) == ("1", Decimal("80000"))
    assert inst["jurisdiction"] == "51087"  # Henrico County
    roles = sorted(r["role"] for t, r in out if t == "instrument_party")
    assert roles == ["creditor", "debtor"]
