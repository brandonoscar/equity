"""Enforce coverage floors per package from a coverage.py JSON report."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path


def percent(files: dict[str, dict[str, dict[str, int]]], prefix: str | None) -> tuple[float, int]:
    covered = total = 0
    for name, info in files.items():
        if prefix is not None and prefix not in name.replace("\\", "/"):
            continue
        s = info["summary"]
        covered += s["covered_lines"] + s.get("covered_branches", 0)
        total += s["num_statements"] + s.get("num_branches", 0)
    return (100.0 if total == 0 else 100.0 * covered / total), total


def main(report: str, floors_path: str) -> int:
    files = json.loads(Path(report).read_text())["files"]
    floors = tomllib.loads(Path(floors_path).read_text())
    failed = False
    checks = [("overall", None, float(floors["overall"]))]
    checks += [(k, k, float(v)) for k, v in floors.get("packages", {}).items()]
    for label, prefix, floor in checks:
        pct, size = percent(files, prefix)
        status = "ok" if pct >= floor else "FAIL"
        note = " (no statements yet)" if size == 0 else ""
        print(f"coverage {label}: {pct:.1f}% (floor {floor:.0f}%) {status}{note}")
        failed |= pct < floor
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
