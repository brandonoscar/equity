"""Table-driven: organization markers are detected; nothing is assumed to be a person."""

import pytest

from equity.matching.orgs import NameClass, classify, clean


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ACME HOLDINGS LLC", NameClass("org", "LLC", "ACME HOLDINGS")),
        ("Acme Holdings, L.L.C.", NameClass("org", "LLC", "ACME HOLDINGS")),
        ("ACME HOLDINGS LIMITED LIABILITY COMPANY", NameClass("org", "LLC", "ACME HOLDINGS")),
        ("Widget Co.", NameClass("org", "CO", "WIDGET")),
        ("WIDGET COMPANY", NameClass("org", "CO", "WIDGET")),
        ("Widget Corp", NameClass("org", "CORP", "WIDGET")),
        ("Widget Incorporated", NameClass("org", "INC", "WIDGET")),
        ("SMITH & JONES LLP", NameClass("org", "LLP", "SMITH & JONES")),
        ("FIRST UNITED BANK", NameClass("org", None, "FIRST UNITED BANK")),
        ("MONONGALIA COUNTY COMMISSION", NameClass("org", None, "MONONGALIA COUNTY COMMISSION")),
        ("SMITH JOHN A", NameClass("unknown", None, None)),
        ("SMITH JOHN A JR", NameClass("unknown", None, None)),
        ("COMPANY", NameClass("unknown", None, None)),  # a bare form word is not an org name
        ("", NameClass("unknown", None, None)),
        ("  ...  ", NameClass("unknown", None, None)),
    ],
)
def test_classify(raw: str, expected: NameClass) -> None:
    assert classify(raw) == expected


@pytest.mark.parametrize(
    ("raw", "out"),
    [("L.L.C.", "LLC"), ("  o'brien,  pat ", "O BRIEN PAT"), ("A&B", "A&B")],
)
def test_clean(raw: str, out: str) -> None:
    assert clean(raw) == out
