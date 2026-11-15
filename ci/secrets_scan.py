"""Run detect-secrets over tracked files against the committed baseline."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "ci/.secrets.baseline"
# Content hashes in lockfiles and fixtures are not secrets.
EXCLUDE = re.compile(r"^(uv\.lock|tests/fixtures/.*\.jsonl|ci/\.secrets\.baseline)$")


def main() -> int:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],  # noqa: S607
        cwd=ROOT, check=True, capture_output=True,
    ).stdout.decode()  # fmt: skip
    files = [f for f in listed.split("\0") if f and not EXCLUDE.match(f)]
    cmd = [sys.executable, "-m", "detect_secrets.pre_commit_hook", "--baseline", BASELINE, *files]
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode  # noqa: S603


if __name__ == "__main__":
    raise SystemExit(main())
