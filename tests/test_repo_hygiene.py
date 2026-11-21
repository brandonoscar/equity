"""ci/check_repo_hygiene.py: data files, big files, hidden sources, missing packages."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("hygiene", ROOT / "ci" / "check_repo_hygiene.py")
assert _spec and _spec.loader
hygiene = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hygiene)


def test_clean_tree_has_no_problems(tmp_path: Path) -> None:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "a.py").write_text("x = 1\n")
    tracked = ["src/pkg/__init__.py", "src/pkg/a.py", "README.md"]
    assert hygiene.problems(tracked, ["src/pkg/__pycache__/a.cpython-313.pyc"], tmp_path) == []


def test_each_problem_is_reported(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "big.json").write_bytes(b"x" * (hygiene.MAX_BYTES + 1))
    tracked = ["data/lake/x/parcel/00000.parquet", "tests/big.json", "src/equity/lake/a.py"]
    # The bug this guards against: a package folder git-ignored by a too-broad 'data/' rule.
    ignored = ["src/equity/data/county_fips_2020.csv", "src/equity/__pycache__/x.pyc"]
    found = hygiene.problems(tracked, ignored, tmp_path)
    assert found == sorted([
        "data file tracked in git: data/lake/x/parcel/00000.parquet",
        f"tracked file over {hygiene.MAX_BYTES} bytes: tests/big.json",
        "source file hidden by .gitignore: src/equity/data/county_fips_2020.csv",
        "package without a tracked __init__.py: src/equity/lake",
    ])  # fmt: skip


def test_the_repository_itself_is_clean() -> None:
    assert hygiene.main() == 0
