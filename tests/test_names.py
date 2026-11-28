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


def test_debtor_aliases_name_the_same_debtor() -> None:
    from equity.matching.names import debtor_name_variants as d

    assert d("SMITH JOHN DBA SMITH PLUMBING") == [("SMITH JOHN", "alias"),
                                                  ("SMITH PLUMBING", "alias")]  # fmt: skip
    assert d("JOHN SMITH D.B.A. JS CAFE") == [("JOHN SMITH", "alias"), ("JS CAFE", "alias")]
    assert d("J.SMITH D/B/A ACME INC") == [("J SMITH", "alias"), ("ACME INC", "alias")]
    assert d("JOHN SMITH A/K/A JACK SMITH") == [("JOHN SMITH", "alias"),
                                                ("JACK SMITH", "alias")]  # fmt: skip
    assert d("ACME INC FKA ACME LLC") == [("ACME INC", "alias"), ("ACME LLC", "alias")]
    assert d("JOHN & JANE SMITH DBA JOE CAFE") == [
        ("JOHN SMITH", "joint"), ("JANE SMITH", "joint"), ("JOE CAFE", "alias")]  # fmt: skip
    assert d("JOHN & JANE SMITH") == [("JOHN SMITH", "joint"), ("JANE SMITH", "joint")]
    # No alias marker, or a marker-like word that is a name: nothing to split.
    assert d("JOHN SMITH") == []
    assert d("TA VAN NGUYEN") == []
    assert d(None) == []


def test_business_names_are_not_split_into_people() -> None:
    assert owner_name_variants("SMITH & JONES LLC") == []
    assert owner_name_variants("FIRST BANK & TRUST") == []
    assert owner_name_variants("JOHN A SMITH REVOCABLE TRUST") == [("JOHN A SMITH", "trust")]


def test_every_nickname_names_one_formal_name() -> None:
    from equity.matching.nicknames import GROUPS, nickname_map

    m = nickname_map()
    assert m["BOB"] == "ROBERT" and m["BILL"] == "WILLIAM" and m["PEGGY"] == "MARGARET"
    assert not set(m) & set(GROUPS)  # no nickname is also a formal name
    for ambiguous in ("CHRIS", "PAT", "SAM", "ALEX", "TED", "HARRY", "AL"):
        assert ambiguous not in m
