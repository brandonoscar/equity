"""Phase 4 rule tests live here (table-driven + Hypothesis). Mutation testing targets them."""

import equity.rules


def test_rules_package_documents_its_contract() -> None:
    assert equity.rules.__doc__ is not None
    assert "config/" in equity.rules.__doc__
