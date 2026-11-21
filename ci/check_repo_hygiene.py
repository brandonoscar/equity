"""Fail when the repository holds what it must not, or misses what the code needs.

1. No data files in git: Parquet, DuckDB, archives, shapefile parts. The lake lives in object
   storage; a committed extract would publish personal data and bloat history.
2. No tracked file over MAX_BYTES (fixtures are small samples by design).
3. No source file hidden by an ignore rule: a file under src/, config/, tests/, ci/ or .github/
   that exists locally but is git-ignored passes tests here and breaks every clean checkout
   (the county FIPS table was lost this way once).
4. Every directory under src/ that holds Python files is a tracked package (has __init__.py).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_SUFFIXES = (".parquet", ".duckdb", ".wal", ".gz", ".zip", ".shp", ".dbf", ".shx", ".gdb")
MAX_BYTES = 1_000_000
SOURCE_DIRS = ("src", "config", "tests", "ci", ".github")
IGNORED_OK = ("__pycache__", ".pyc", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis")


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True)  # noqa: S603, S607
    return [line for line in out.stdout.splitlines() if line]


def problems(tracked: list[str], ignored: list[str], root: Path = ROOT) -> list[str]:
    found: list[str] = []
    for name in tracked:
        if name.lower().endswith(DATA_SUFFIXES):
            found.append(f"data file tracked in git: {name}")
        path = root / name
        if path.is_file() and path.stat().st_size > MAX_BYTES:
            found.append(f"tracked file over {MAX_BYTES} bytes: {name}")
    for name in ignored:
        if not any(part in name for part in IGNORED_OK):
            found.append(f"source file hidden by .gitignore: {name}")
    tracked_set = set(tracked)
    for py in sorted({n for n in tracked if n.startswith("src/") and n.endswith(".py")}):
        init = str(Path(py).parent / "__init__.py")
        if init not in tracked_set:
            found.append(f"package without a tracked __init__.py: {Path(py).parent}")
    return sorted(set(found))


def main() -> int:
    tracked = git("ls-files")
    ignored = git("ls-files", "--others", "--ignored", "--exclude-standard", "--", *SOURCE_DIRS)
    found = problems(tracked, ignored)
    for line in found:
        print(line)
    print(f"repo hygiene: {len(found)} problem(s) in {len(tracked)} tracked files")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
