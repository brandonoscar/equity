"""The repo is public: recorded adapter fixtures must not contain real owner names."""

from __future__ import annotations

import json
from pathlib import Path

from equity.adapters.registry import REGISTRY
from equity.adapters.wv.parcelweb import MonongaliaParcelWeb, results_table

ROOT = Path(__file__).parent / "fixtures" / "adapters"


def _walk(obj: object, fields: tuple[str, ...], keep: frozenset[str] = frozenset()) -> list[str]:
    bad: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in fields and isinstance(v, str) and v.strip():
                ok = v.startswith("TESTOWNER") or v.endswith(" TEST ST")
                if not ok and v.strip().upper() not in keep:
                    bad.append(f"{k}={v[:3]}...")
            else:
                bad += _walk(v, fields, keep)
    elif isinstance(obj, list):
        for v in obj:
            bad += _walk(v, fields, keep)
    return bad


def _placeholders(cls: type) -> frozenset[str]:
    """A lien source's skip_names (e.g. a literal 'NULL' purchaser): they name nobody."""
    get = getattr(getattr(cls, "config", None), "get", None)
    return frozenset(
        str(s).strip().upper() for s in (get("skip_names", []) if callable(get) else [])
    )


def test_json_fixtures_have_only_pseudonyms_in_pii_fields() -> None:
    for cls in REGISTRY:
        fields: tuple[str, ...] = getattr(cls, "pii_fields", ())
        for path in sorted((ROOT / cls.source_id).glob("*.json")):
            bad = _walk(json.loads(path.read_text()), fields, _placeholders(cls))
            assert bad == [], path.name


def test_scrub_keeps_placeholders_and_pseudonymizes_names() -> None:
    from equity.adapters.record import scrub

    rows = [{"Purchaser": "NULL", "Defendant": "ANN LEE"}, {"Purchaser": "BOB RAY", "x": "NULL"}]
    out = scrub(rows, ("Purchaser", "Defendant"), frozenset({"NULL"}))
    assert out[0]["Purchaser"] == "NULL" and out[0]["Defendant"].startswith("TESTOWNER")
    assert out[1]["Purchaser"].startswith("TESTOWNER") and out[1]["x"] == "NULL"
    assert scrub(rows, ("Purchaser",))[0]["Purchaser"].startswith("TESTOWNER")  # no keep set


def test_parcelweb_fixtures_have_only_pseudonyms() -> None:
    for path in sorted((ROOT / MonongaliaParcelWeb.source_id).glob("*.json")):
        for page in json.loads(path.read_text())["pages"]:
            _, rows = results_table(page)
            assert all(r.cells[3].startswith("TESTOWNER") or not r.cells[3] for r in rows)
            assert 'name="__VIEWSTATE"' not in page or 'value="SCRUBBED"' in page


def test_rss_fixtures_have_only_pseudonyms() -> None:
    import re
    import xml.etree.ElementTree as ET

    from equity.adapters.federal.ecf_rss import parse_case

    for path in sorted(ROOT.glob("us.*.rss/feed.xml")):
        channel = ET.parse(path).getroot().find("channel")  # noqa: S314 - our own fixtures
        assert channel is not None
        for item in channel.findall("item"):
            title = " ".join((item.findtext("title") or "").split())
            parsed = parse_case(title, bankruptcy_court=True)
            assert parsed is not None, f"{path.parent.name}: unparsed title would leak names"
            caption = parsed[-1]
            for part in re.split(r"\s+v\.?\s+", caption) if caption else []:
                assert part.startswith("TESTOWNER"), f"{path.parent.name}: unscrubbed caption"
            trustee = re.search(r"Trustee:\s*([^\[]+?)\s*\[", item.findtext("description") or "")
            assert trustee is None or trustee.group(1).startswith("TESTOWNER")


def test_csv_fixtures_have_only_pseudonyms() -> None:
    from equity.adapters.fl.hillsborough_civil import (
        HillsboroughCivilCases,
        HillsboroughCivilFilings,
        HillsboroughGarnishment,
        read_csv,
        split_style,
    )

    for cls in (HillsboroughCivilCases, HillsboroughCivilFilings, HillsboroughGarnishment):
        paths = sorted((ROOT / cls.source_id).glob("*.json"))
        assert paths, cls.source_id
        for path in paths:
            for row in read_csv(json.loads(path.read_text())["csv"]):
                for col in cls.pii_columns:
                    v = row.get(col, "")
                    assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), col
                for col in cls.style_columns:
                    for side in split_style(row.get(col, "")):
                        assert side is None or side.startswith("TESTOWNER"), col


def test_official_records_party_names_are_pseudonyms() -> None:
    for path in sorted((ROOT / "fl.hillsborough.or").glob("*.json")):
        for line in json.loads(path.read_text())["p"].splitlines():
            cells = line.split("|")
            if len(cells) > 5 and cells[5].strip():
                assert cells[5].startswith("TESTOWNER")
