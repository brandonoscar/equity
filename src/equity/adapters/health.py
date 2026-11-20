"""Nightly live health check over every registered adapter. Not run in PR CI (no network)."""

from __future__ import annotations

import json
import sys

from equity.adapters.registry import REGISTRY


def main() -> int:
    results = []
    for cls in REGISTRY:
        try:
            report = cls().health()
            results.append(
                {"source_id": report.source_id, "ok": report.ok, "detail": report.detail}
            )
        except Exception as exc:
            results.append({"source_id": cls.source_id, "ok": False, "detail": repr(exc)})
    json.dump({"adapters": len(REGISTRY), "results": results}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
