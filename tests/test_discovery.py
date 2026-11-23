"""Discovery of new sale and debt layers (equity.discovery), against fake catalogs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from equity import discovery

NOW = datetime(2026, 11, 23, tzinfo=UTC)


@dataclass
class _Resp:
    content: bytes


class FakeClient:
    def __init__(self, arcgis: list[dict[str, Any]], socrata: list[dict[str, Any]]) -> None:
        self.arcgis, self.socrata = arcgis, socrata

    def get(self, url: str, params: dict[str, str] | None = None) -> _Resp:
        if url == discovery.ARCGIS:
            return _Resp(json.dumps({"results": self.arcgis}).encode())
        return _Resp(json.dumps({"results": self.socrata}).encode())


def _cfg(tmp_path: Path) -> Path:
    cfg = tmp_path / "cfg"
    (cfg / "liens").mkdir(parents=True)
    (cfg / "discovery.yaml").write_text(
        "terms: [tax sale]\nmax_age_days: 365\nper_term: 10\nexclude_title_words: [test]\n"
    )
    (cfg / "liens" / "known.yaml").write_text(
        "layer_url: https://services1.arcgis.com/abc/arcgis/rest/services/Known_Tax_Sale/"
        "FeatureServer/0\ndataset: abcd-1234\n")  # fmt: skip
    return cfg


def _ag(title: str, url: str, days_old: int) -> dict[str, Any]:
    ms = int((NOW.timestamp() - days_old * 86400) * 1000)
    return {"id": title[:4], "title": title, "owner": "o", "url": url, "modified": ms}


def test_new_candidates_skip_known_old_and_off_topic_layers(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    base = "https://services1.arcgis.com/abc/arcgis/rest/services/"
    client = FakeClient(
        [_ag("2026 Tax Sale", base + "County_2026/FeatureServer", 10),
         _ag("Known Tax Sale", base + "Known_Tax_Sale/FeatureServer", 5),     # configured
         _ag("Old Tax Sale", base + "Old/FeatureServer", 900),                # stale
         _ag("Tax Sale test copy", base + "T/FeatureServer", 3),              # excluded word
         _ag("Parcels", base + "P/FeatureServer", 3)],                        # term not in title
        [{"resource": {"id": "abcd-1234", "name": "Tax Sale List", "data_updated_at": "2026-11-01"},
          "metadata": {"domain": "data.x.gov"}},                              # configured
         {"resource": {"id": "wxyz-9876", "name": "Annual Tax Sale",
                       "data_updated_at": "2026-10-01"},
          "metadata": {"domain": "data.y.gov"}}],
    )  # fmt: skip
    out = tmp_path / "out"
    first = discovery.run(out, client, NOW, cfg)  # type: ignore[arg-type]
    assert first["candidates"] == 2 and first["compared_with"] is None
    assert [c["title"] for c in first["new"]] == ["2026 Tax Sale", "Annual Tax Sale"]
    later = datetime(2026, 11, 30, tzinfo=UTC)
    client.arcgis.append(_ag("Spring Tax Sale", base + "Spring/FeatureServer", 1))
    second = discovery.run(out, client, later, cfg)  # type: ignore[arg-type]
    assert second["compared_with"] == "2026-11-23"
    assert [c["title"] for c in second["new"]] == ["Spring Tax Sale"]
    text = discovery.markdown(second)
    assert "New candidate layers since 2026-11-23 (1 of 3)" in text and "Spring Tax Sale" in text


def test_known_urls_normalize_layer_and_service_forms(tmp_path: Path) -> None:
    known = discovery.known_urls(_cfg(tmp_path))
    assert "services1.arcgis.com/abc/arcgis/rest/services/known_tax_sale/featureserver" in known
    assert "socrata:abcd-1234" in known
    assert discovery.normalize("https://h/x/MapServer/3?f=json") == "h/x/mapserver"
    assert discovery.known_urls()  # the repo's own configs
