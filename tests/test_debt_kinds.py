"""Every judgment / lien source a match run reads is labeled with its kind of debt."""

from __future__ import annotations

from equity.matching.resolve import STATES, debt_kinds


def test_every_debtor_court_and_writ_source_has_a_kind() -> None:
    kinds = debt_kinds()
    used = {s for spec in STATES.values()
            for key in ("debtors", "courts", "writs") for s in spec.get(key) or []}  # fmt: skip
    missing = sorted(used - set(kinds))
    assert not missing, f"add to config/debt_kinds.yaml: {missing}"
    assert kinds["us.fjc.idb.direct.civil_judgments"] == "court_judgment"
    assert kinds["ny.dtf.tax_warrants"] == "tax_warrant"
