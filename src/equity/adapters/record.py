"""Record a small live sample as an adapter fixture, with personal data replaced by pseudonyms.

    uv run python -m equity.adapters.record wv.statewide.parcels county_number=31 limit=25

The repo is public: names and street lines are replaced deterministically (same input, same
pseudonym) so tests stay stable and no real person's data is committed. Entity-form suffixes
(LLC, INC...) are kept so name classification can still be tested.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from equity.adapters.base import FetchRequest
from equity.adapters.registry import by_source_id
from equity.matching.orgs import classify
from equity.schema.ids import stable_id

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "adapters"


def pseudonym(field: str, value: str) -> str:
    token = stable_id("scrub", field, value)[:6].upper()
    if "ADDRESS" in field.upper():
        return f"{int(token, 16) % 9000 + 100} TEST ST"
    form = classify(value).org_form
    return f"TESTOWNER {token}" + (f" {form}" if form else "")


def scrub(obj: Any, fields: tuple[str, ...]) -> Any:
    if isinstance(obj, dict):
        return {
            k: (pseudonym(k, v) if k in fields and isinstance(v, str) and v.strip() else
                scrub(v, fields))
            for k, v in obj.items()
        }  # fmt: skip
    if isinstance(obj, list):
        return [scrub(v, fields) for v in obj]
    return obj


def main(argv: list[str]) -> int:
    source_id, *pairs = argv
    params = dict(p.split("=", 1) for p in pairs)
    cls = by_source_id(source_id)
    adapter = cls()
    fetched = adapter.fetch(FetchRequest(params))
    custom = getattr(cls, "scrub_fixture", None)
    out = FIXTURES / source_id
    out.mkdir(parents=True, exist_ok=True)
    if fetched.content_type.split(";")[0].strip() in (
        "text/xml",
        "application/xml",
        "application/rss+xml",
    ):
        assert custom is not None, "XML fixtures need an adapter scrub_fixture"
        path = out / "feed.xml"
        path.write_bytes(custom(fetched.content))
        print(f"wrote {path} ({len(path.read_bytes())} bytes)")
        return 0
    if custom is not None:
        data = json.loads(custom(fetched.content))
    else:
        pii: tuple[str, ...] = getattr(cls, "pii_fields", ())
        data = scrub(json.loads(fetched.content), pii)
    name = "_".join(f"{k}-{v.replace('/', '')}" for k, v in sorted(params.items())) or "sample"
    path = out / f"{name}.json"
    path.write_text(json.dumps(data, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(path.read_bytes())} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
