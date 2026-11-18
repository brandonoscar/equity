"""Phase 3 matching tests live here (table-driven). Mutation testing targets them."""

import equity.matching


def test_matching_package_documents_its_contract() -> None:
    assert equity.matching.__doc__ is not None
    assert "review queue" in equity.matching.__doc__
