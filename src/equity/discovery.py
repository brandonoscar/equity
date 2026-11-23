"""Find new government sale and debt layers: ArcGIS Online and the Socrata catalog, searched
by title for config/discovery.yaml terms, minus what config/ already loads.

    uv run python -m equity.discovery --out data/derived/discovery    # writes <day>.json

Each candidate is {catalog, id, title, owner or domain, url, modified, term}. A candidate is
a lead for a person: the licence, publisher and fields are checked before any config is
written (as for every source). With an earlier day's file in --out, the run also lists what
is new since then.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from equity.adapters.http import PoliteClient
from equity.config import CONFIG_DIR, _load

ARCGIS = "https://www.arcgis.com/sharing/rest/search"
SOCRATA = "https://api.us.socrata.com/api/catalog/v1"
URL_RE = re.compile(r"https?://[^\s'\"\]]+")


def known_urls(config_dir: Path | None = None) -> set[str]:
    """Every layer/service URL and Socrata dataset id already in config/ (normalized)."""
    root = config_dir or CONFIG_DIR
    out: set[str] = set()
    for path in root.rglob("*.yaml"):
        if "private" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for url in URL_RE.findall(text):
            out.add(normalize(url))
        for ds in re.findall(r"^dataset:\s*([a-z0-9]{4}-[a-z0-9]{4})\s*$", text, re.M):
            out.add(f"socrata:{ds}")
    return out


def normalize(url: str) -> str:
    """Service root, lower case, no scheme, no trailing layer number or query."""
    u = urllib.parse.urlsplit(url.strip().rstrip("/"))
    path = re.sub(r"/(FeatureServer|MapServer)(/\d+)?$", r"/\1", u.path, flags=re.I)
    return (u.netloc + path).lower()


def arcgis(client: PoliteClient, term: str, num: int) -> list[dict[str, Any]]:
    q = f'title:"{term}" AND (type:"Feature Service" OR type:"Map Service")'
    resp = client.get(ARCGIS, {"q": q, "f": "json", "num": str(num),
                               "sortField": "modified", "sortOrder": "desc"})  # fmt: skip
    rows = json.loads(resp.content).get("results") or []
    return [{"catalog": "arcgis", "id": r.get("id"), "title": r.get("title"),
             "owner": r.get("owner"), "url": r.get("url"),
             "modified": datetime.fromtimestamp(int(r.get("modified") or 0) / 1000, tz=UTC)
             .date().isoformat(), "term": term} for r in rows if r.get("url")]  # fmt: skip


def socrata(client: PoliteClient, term: str, num: int) -> list[dict[str, Any]]:
    resp = client.get(SOCRATA, {"q": term, "limit": str(num), "only": "dataset"})
    rows = json.loads(resp.content).get("results") or []
    out = []
    for r in rows:
        res, meta = r.get("resource") or {}, r.get("metadata") or {}
        updated = str(res.get("data_updated_at") or res.get("updatedAt") or "")[:10]
        out.append({"catalog": "socrata", "id": res.get("id"), "title": res.get("name"),
                    "owner": meta.get("domain"),
                    "url": f"https://{meta.get('domain')}/d/{res.get('id')}",
                    "modified": updated, "term": term})  # fmt: skip
    return out


def candidates(found: Iterable[dict[str, Any]], known: set[str], today: datetime,
               max_age_days: int, exclude: Iterable[str]) -> list[dict[str, Any]]:  # fmt: skip
    cutoff = (today - timedelta(days=max_age_days)).date().isoformat()
    bad = [w.lower() for w in exclude]
    seen: dict[str, dict[str, Any]] = {}
    for c in found:
        title = str(c.get("title") or "")
        key = f"socrata:{c['id']}" if c["catalog"] == "socrata" else normalize(str(c["url"]))
        if key in known or str(c.get("modified") or "") < cutoff:
            continue
        # Catalog search matches descriptions too: keep only titles that carry the term.
        if not re.search(rf"\b{re.escape(str(c['term']).lower())}", title.lower()):
            continue
        if any(re.search(rf"\b{re.escape(w)}\b", title.lower()) for w in bad):
            continue
        seen.setdefault(key, {**c, "key": key})
    return sorted(seen.values(), key=lambda c: (str(c["modified"]), str(c["key"])), reverse=True)


def run(out: Path, client: PoliteClient | None = None, today: datetime | None = None,
        config_dir: Path | None = None) -> dict[str, Any]:  # fmt: skip
    cfg = _load("discovery.yaml", config_dir)
    client = client or PoliteClient(min_interval_s=1.0)
    now = today or datetime.now(UTC)
    found: list[dict[str, Any]] = []
    for term in cfg["terms"]:
        found += arcgis(client, str(term), int(cfg["per_term"]))
        found += socrata(client, str(term), int(cfg["per_term"]))
    cands = candidates(found, known_urls(config_dir), now, int(cfg["max_age_days"]),
                       cfg.get("exclude_title_words") or [])  # fmt: skip
    out.mkdir(parents=True, exist_ok=True)
    day = now.date().isoformat()
    earlier = sorted(p for p in out.glob("????-??-??.json") if p.stem < day)
    before = (
        {c["key"] for c in json.loads(earlier[-1].read_text())["candidates"]} if earlier else set()
    )
    new = [c for c in cands if c["key"] not in before]
    (out / f"{day}.json").write_text(json.dumps({"day": day, "candidates": cands}, indent=1))
    return {"day": day, "candidates": len(cands), "new": new,
            "compared_with": earlier[-1].stem if earlier else None}  # fmt: skip


def markdown(result: dict[str, Any]) -> str:
    lines = [f"New candidate layers since {result['compared_with'] or 'the first run'} "
             f"({len(result['new'])} of {result['candidates']}):", "",
             "| Modified | Catalog | Title | Publisher | Term |",
             "|---|---|---|---|---|"]  # fmt: skip
    for c in result["new"]:
        title = str(c["title"]).replace("|", "/")
        lines.append(f"| {c['modified']} | {c['catalog']} | [{title}]({c['url']}) | "
                     f"{c['owner']} | {c['term']} |")  # fmt: skip
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.discovery")
    ap.add_argument("--out", type=Path, default=Path("data") / "derived" / "discovery")
    args = ap.parse_args(argv)
    sys.stdout.write(markdown(run(args.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
