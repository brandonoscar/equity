"""Known-vulnerability scan of the locked dependencies (pip-audit against uv.lock's export)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "requirements.txt"
        subprocess.run(  # noqa: S603
            ["uv", "export", "--locked", "--format", "requirements-txt", "--no-hashes",  # noqa: S607
             "--no-emit-project", "-q", "-o", str(req)],
            check=True,
        )  # fmt: skip
        cmd = [sys.executable, "-m", "pip_audit", "-r", str(req), "--disable-pip", "--no-deps",
               "--progress-spinner", "off"]  # fmt: skip
        return subprocess.run(cmd, check=False).returncode  # noqa: S603


if __name__ == "__main__":
    sys.exit(main())
