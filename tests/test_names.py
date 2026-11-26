"""Owner strings split into the people they name (equity.matching.names)."""

from __future__ import annotations

import pytest

from equity.matching.names import owner_name_variants

CASES = [
    ("SMITH JOHN A & JANE B", [("SMITH JOHN A", "joint"), ("SMITH JANE B", "joint")]),
    ("JOHN A & JANE B SMITH", [("JOHN A SMITH", "joint"), ("JANE B SMITH", "joint")]),
    ("SMITH JOHN AND DOE JANE", [("SMITH JOHN", "joint"), ("DOE JANE", "joint")]),
    ("SMITH JOHN A ET UX", []),  # one owner: the tag is dropped by the name key anyway
    ("SMITH JOHN A & JANE B JTWROS", [("SMITH JOHN A", "joint"), ("SMITH JANE B", "joint")]),
    ("SMITH, JOHN A. & JANE", [("SMITH JOHN A", "joint"), ("SMITH JANE", "joint")]),
    ("JOHN A SMITH REVOCABLE TRUST", [("JOHN A SMITH", "trust")]),
    ("SMITH JOHN A TR", [("SMITH JOHN A", "trust")]),
    ("SMITH JOHN A TRUSTEE U/A DTD 01/02/2003", [("SMITH JOHN A", "trust")]),
    ("JOHN & JANE SMITH LIVING TRUST", [("JOHN SMITH", "trust"), ("JANE SMITH", "trust")]),
    ("SMITH FAMILY TRUST", []),  # no person named
    ("JOHN SMITH", []),
    ("SMITH JR JOHN & MARY", [("SMITH JR JOHN", "joint"), ("SMITH MARY", "joint")]),
    ("ACME HOLDINGS LLC", []),
    ("", []),
    (None, []),
]  # fmt: skip


@pytest.mark.parametrize(("raw", "want"), CASES)
def test_owner_name_variants(raw: str | None, want: list[tuple[str, str]]) -> None:
    assert owner_name_variants(raw) == want


def test_variants_are_deterministic() -> None:
    assert owner_name_variants("SMITH JOHN A & JANE B") == owner_name_variants(
        "SMITH JOHN A & JANE B"
    )
