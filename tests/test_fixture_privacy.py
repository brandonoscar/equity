"""The repo is public: recorded adapter fixtures must not contain real owner names."""

from __future__ import annotations

import json
from pathlib import Path

from equity.adapters.registry import REGISTRY
from equity.adapters.wv.parcelweb import MonongaliaParcelWeb, results_table

ROOT = Path(__file__).parent / "fixtures" / "adapters"


def _walk(obj: object, fields: tuple[str, ...]) -> list[str]:
    bad: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in fields and isinstance(v, str) and v.strip():
                if not (v.startswith("TESTOWNER") or v.endswith(" TEST ST")):
                    bad.append(f"{k}={v[:3]}...")
            else:
                bad += _walk(v, fields)
    elif isinstance(obj, list):
        for v in obj:
            bad += _walk(v, fields)
    return bad


def test_json_fixtures_have_only_pseudonyms_in_pii_fields() -> None:
    for cls in REGISTRY:
        fields: tuple[str, ...] = getattr(cls, "pii_fields", ())
        for path in sorted((ROOT / cls.source_id).glob("*.json")):
            assert _walk(json.loads(path.read_text()), fields) == [], path.name


def test_parcelweb_fixtures_have_only_pseudonyms() -> None:
    for path in sorted((ROOT / MonongaliaParcelWeb.source_id).glob("*.json")):
        for page in json.loads(path.read_text())["pages"]:
            _, rows = results_table(page)
            assert all(r.cells[3].startswith("TESTOWNER") or not r.cells[3] for r in rows)
            assert 'name="__VIEWSTATE"' not in page or 'value="SCRUBBED"' in page
