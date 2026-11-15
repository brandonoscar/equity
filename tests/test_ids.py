import pytest

from equity.schema.ids import sha256_hex, stable_id


def test_stable_id_is_deterministic_and_short() -> None:
    assert stable_id("54061", "2010-000101") == stable_id("54061", "2010-000101")
    assert len(stable_id("x")) == 32


@pytest.mark.parametrize(
    ("a", "b"),
    [(("ab", "c"), ("a", "bc")), (("x",), ("x", "")), (("1", "2"), ("2", "1"))],
)
def test_stable_id_separates_parts(a: tuple[str, ...], b: tuple[str, ...]) -> None:
    assert stable_id(*a) != stable_id(*b)


def test_stable_id_rejects_empty_and_separator() -> None:
    with pytest.raises(ValueError, match="at least one"):
        stable_id()
    with pytest.raises(ValueError, match="separator"):
        stable_id("a\x1fb")


def test_sha256_hex() -> None:
    # sha256 of the empty string (a public constant, not a secret)
    empty = (
        "e3b0c44298fc1c149afbf4c8996fb924"  # pragma: allowlist secret
        "27ae41e4649b934ca495991b7852b855"  # pragma: allowlist secret
    )
    assert sha256_hex(b"") == empty
