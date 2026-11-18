"""Fail the build if a blocklisted package, import or host appears anywhere in the project.

Checks: uv.lock package names, pyproject dependencies, every `import` in tracked Python files,
and literal hostnames in tracked source/config files.
"""

from __future__ import annotations

import ast
import fnmatch
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCKLIST = ROOT / "ci" / "blocklist.toml"
SCANNED_SUFFIXES = {".py", ".toml", ".yaml", ".yml", ".json", ".cfg", ".ini", ".sql", ".sh"}
# The blocklist and this checker name the forbidden things on purpose.
SELF_FILES = {"ci/blocklist.toml", "ci/check_no_ai.py", "tests/test_no_ai_guard.py"}


@dataclass(frozen=True)
class Blocklist:
    packages: tuple[str, ...]
    modules: tuple[str, ...]
    hosts: tuple[str, ...]


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def load_blocklist(path: Path = BLOCKLIST) -> Blocklist:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    pk: list[str] = []
    md: list[str] = []
    hs: list[str] = []
    for section in data.values():
        pk += [normalize(p) for p in section.get("packages", [])]
        md += section.get("modules", [])
        hs += [h.lower() for h in section.get("hosts", [])]
    return Blocklist(tuple(pk), tuple(md), tuple(hs))


def blocked_package(name: str, bl: Blocklist) -> str | None:
    norm = normalize(name)
    for pattern in bl.packages:
        if fnmatch.fnmatchcase(norm, pattern):
            return pattern
    return None


def blocked_module(name: str, bl: Blocklist) -> str | None:
    parts = name.split(".")
    candidates = {".".join(parts[: i + 1]) for i in range(len(parts))}
    for pattern in bl.modules:
        if any(fnmatch.fnmatchcase(c, pattern) for c in candidates):
            return pattern
    return None


def lock_packages(lock_text: str) -> list[str]:
    data = tomllib.loads(lock_text)
    return [str(p["name"]) for p in data.get("package", [])]


def pyproject_requirements(text: str) -> list[str]:
    data = tomllib.loads(text)
    reqs: list[str] = list(data.get("project", {}).get("dependencies", []))
    for group in data.get("dependency-groups", {}).values():
        reqs += [r for r in group if isinstance(r, str)]
    for group in data.get("project", {}).get("optional-dependencies", {}).values():
        reqs += group
    return [re.split(r"[\s<>=!~;\[(]", r.strip(), maxsplit=1)[0] for r in reqs]


def imports_in(source: str, filename: str = "<src>") -> list[str]:
    tree = ast.parse(source, filename=filename)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, (ast.Name, ast.Attribute))
            and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
            in {"import_module", "__import__"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            found.append(node.args[0].value)
    return found


def hosts_in(text: str, bl: Blocklist) -> list[str]:
    low = text.lower()
    return [h for h in bl.hosts if h in low]


def tracked_files(root: Path = ROOT) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],  # noqa: S607
        cwd=root, check=True, capture_output=True,
    ).stdout  # fmt: skip
    return [root / p for p in out.decode().split("\0") if p]


def scan(root: Path = ROOT, bl: Blocklist | None = None) -> list[str]:
    bl = bl or load_blocklist()
    problems: list[str] = []
    lock = root / "uv.lock"
    if not lock.exists():
        problems.append("uv.lock is missing: the dependency check needs the lockfile")
    else:
        for pkg in lock_packages(lock.read_text(encoding="utf-8")):
            hit = blocked_package(pkg, bl)
            if hit:
                problems.append(f"uv.lock: package {pkg!r} matches blocklist {hit!r}")
    pyproject = root / "pyproject.toml"
    for req in pyproject_requirements(pyproject.read_text(encoding="utf-8")):
        hit = blocked_package(req, bl)
        if hit:
            problems.append(f"pyproject.toml: dependency {req!r} matches blocklist {hit!r}")
    for path in tracked_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in SELF_FILES or not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix == ".py":
            for mod in imports_in(text, rel):
                hit = blocked_module(mod, bl)
                if hit:
                    problems.append(f"{rel}: imports {mod!r} (blocklist {hit!r})")
        for host in hosts_in(text, bl):
            problems.append(f"{rel}: references blocked host {host!r}")
    return problems


def main() -> int:
    problems = scan()
    for p in problems:
        print(f"NO-AI GUARD: {p}", file=sys.stderr)
    if problems:
        return 1
    print("no-ai guard: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
