"""Catalog of city and county zoning layers found through the ArcGIS Online search API.

    uv run python -m equity.zoning_catalog build    # writes config/zoning/local_layers.json

Steps, all deterministic:
1. Page through public Feature Services titled "zoning" inside the US bounding box that an
   organization marked authoritative (www.arcgis.com/sharing/rest/search).
2. Classify each item's license text (licenseInfo) with fixed keyword rules:
   open (public domain, CC, open data), disclaimer (liability or accuracy text only),
   empty, or restricted (non-commercial, no redistribution, permission required, lists of
   names). Only open and disclaimer items are loadable; empty ones wait for review;
   restricted ones are excluded. Titles that are not current base zoning (history, cases,
   applications, proposed, draft) are dropped.
3. Read each service's layers and pick the polygon layer with a zone-code field, choosing
   the code, description and jurisdiction fields by name.
4. Assign the state from the layer extent's center, tested against Census state outlines.

The catalog is data the zoning loader reads (source us.local.zoning); review the
`review` and `excluded` lists before widening what is loaded.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import struct
import urllib.parse
import zipfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from equity.adapters.arcgis import get_json
from equity.adapters.http import PoliteClient
from equity.config import CONFIG_DIR

SEARCH = "https://www.arcgis.com/sharing/rest/search"
QUERY = 'title:zoning type:"Feature Service" access:public contentstatus:org_authoritative'
US_BBOX = "-125,24,-66,50"
STATES_ZIP = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_20m.zip"
CATALOG = CONFIG_DIR / "zoning" / "local_layers.json"
LOADABLE = ("open", "disclaimer")

_OPEN = re.compile(
    r"public domain|cc0|creative commons|\bcc[ -]by\b|open data|no restrictions|"
    r"without restriction|freely (available|distributed|used)|may be freely|"
    r"open government licen[cs]e|odbl|open database licen[cs]e",
    re.I,
)
_RESTRICTED = re.compile(
    r"non-?commercial|not for commercial|commercial (use|purpose)s? (is|are)? ?(prohibited|"
    r"not (allowed|permitted))|may not be (sold|resold|redistributed|reproduced)|resale|"
    r"written (permission|consent|authorization)|internal use only|personal use only|"
    r"lists? of (individuals|names)|45-230|42\.56\.070|39-121\.03|subscription|"
    r"license agreement (is )?required|must (sign|execute)",
    re.I,
)
_DISCLAIMER = re.compile(
    r"liab|warrant|as[- ]is|accura|informational|no guarantee|not a survey|reference only|"
    r"responsib|errors|omissions|disclaim",
    re.I,
)
_NOT_BASE = re.compile(
    r"histor|case|application|petition|request|proposed|draft|notice|notif|buffer|"
    r"comment|public hearing|amendment|test|copy|old\b|archive",
    re.I,
)
_TAGS = re.compile(r"<[^>]+>|&nbsp;|&quot;|&amp;")

CODE_FIELDS = ("ZONING", "ZONE_CODE", "ZONECODE", "ZONING_CODE", "ZONINGCODE", "ZONE",
               "ZONE_CLASS", "ZONECLASS", "ZONING_DISTRICT", "ZONINGDISTRICT", "ZONEDIST",
               "ZONE_DIST", "DISTRICT", "ZONING_CLASS", "ZONINGCLASS", "ZONE_TYPE", "ZONETYPE",
               "CLASS", "ZN_CODE", "ZONING_ABBR", "ZONEABBR", "ZONE_ABBR")  # fmt: skip
DESC_FIELDS = ("ZONE_DESC", "ZONEDESC", "ZONING_DESC", "ZONINGDESC", "DESCRIPTION", "DESC_",
               "ZONE_NAME", "ZONENAME", "ZONING_NAME", "ZONINGNAME", "ZONE_DESCRIPTION",
               "ZONING_DESCRIPTION", "LONG_NAME", "NAME", "LABEL")  # fmt: skip
JURIS_FIELDS = ("JURISDICTION", "JURIS", "MUNICIPALITY", "MUNI", "MUNI_NAME", "CITY",
                "CITY_NAME", "TOWN", "TOWNSHIP", "COMMUNITY", "JURISDICT", "AUTHORITY")  # fmt: skip


def license_class(text: str | None) -> str:
    """open, restricted, disclaimer or empty, from an item's licenseInfo HTML."""
    plain = _TAGS.sub(" ", text or "").strip()
    if not plain:
        return "empty"
    if _RESTRICTED.search(plain):
        return "restricted"
    if _OPEN.search(plain):
        return "open"
    if _DISCLAIMER.search(plain):
        return "disclaimer"
    return "empty" if len(plain) < 20 else "disclaimer"


def is_base_zoning(title: str) -> bool:
    return bool(re.search(r"zon", title, re.I)) and not _NOT_BASE.search(title)


def pick_field(fields: Sequence[str], preferred: Sequence[str]) -> str | None:
    """The first preferred name present (case-insensitive), else None."""
    by_upper = {f.upper(): f for f in fields}
    for name in preferred:
        if name in by_upper:
            return by_upper[name]
    return None


# --- Census state outlines (ESRI shapefile polygons, read without extra libraries) --------


@dataclass(frozen=True)
class StateShape:
    fips: str
    box: tuple[float, float, float, float]
    rings: tuple[tuple[tuple[float, float], ...], ...]


def read_shp_polygons(shp: bytes) -> Iterator[list[list[tuple[float, float]]]]:
    """Yield each polygon record's rings from a .shp file (shape types 5 and 15)."""
    pos = 100
    while pos + 8 <= len(shp):
        _, length = struct.unpack(">ii", shp[pos : pos + 8])
        rec = shp[pos + 8 : pos + 8 + 2 * length]
        pos += 8 + 2 * length
        (shape_type,) = struct.unpack("<i", rec[:4])
        if shape_type not in (5, 15):
            yield []
            continue
        nparts, npoints = struct.unpack("<ii", rec[36:44])
        parts = list(struct.unpack(f"<{nparts}i", rec[44 : 44 + 4 * nparts]))
        base = 44 + 4 * nparts
        pts = [
            struct.unpack("<dd", rec[base + 16 * i : base + 16 * i + 16]) for i in range(npoints)
        ]
        bounds = [*parts, npoints]
        yield [list(pts[bounds[k] : bounds[k + 1]]) for k in range(nparts)]


def load_states(zip_bytes: bytes) -> list[StateShape]:
    from equity.adapters.dbf import read_records

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        shp_name = next(n for n in z.namelist() if n.endswith(".shp"))
        dbf_name = next(n for n in z.namelist() if n.endswith(".dbf"))
        shp = z.read(shp_name)
        records = [r for _, r in read_records(io.BytesIO(z.read(dbf_name)))]
    out = []
    for rings, rec in zip(read_shp_polygons(shp), records, strict=True):
        xs = [p[0] for r in rings for p in r]
        ys = [p[1] for r in rings for p in r]
        out.append(StateShape(str(rec["STATEFP"]), (min(xs), min(ys), max(xs), max(ys)),
                              tuple(tuple(r) for r in rings)))  # fmt: skip
    return out


def contains(rings: Sequence[Sequence[tuple[float, float]]], x: float, y: float) -> bool:
    """Even-odd point-in-polygon over all rings (holes included)."""
    inside = False
    for ring in rings:
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % n]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def state_at(states: Sequence[StateShape], x: float, y: float) -> str | None:
    for s in states:
        x0, y0, x1, y1 = s.box
        if x0 <= x <= x1 and y0 <= y <= y1 and contains(s.rings, x, y):
            return s.fips
    return None


# --- catalog build -------------------------------------------------------------------------


def search_items(client: PoliteClient) -> Iterator[dict[str, Any]]:
    start = 1
    while start > 0:
        body = get_json(client, SEARCH, {"q": QUERY, "bbox": US_BBOX, "num": "100",
                                         "start": str(start), "sortField": "created",
                                         "sortOrder": "asc", "f": "json"})  # fmt: skip
        yield from body.get("results") or []
        start = int(body.get("nextStart") or -1)


def pick_layer(client: PoliteClient, service_url: str) -> dict[str, Any] | None:
    """The first polygon layer of a service that has a zone-code field, with field picks."""
    svc = get_json(client, service_url, {"f": "json"})
    for lyr in svc.get("layers") or []:
        if "Polygon" not in str(lyr.get("geometryType", "")):
            continue
        url = f"{service_url.rstrip('/')}/{lyr['id']}"
        meta = get_json(client, url, {"f": "json"})
        names = [f["name"] for f in meta.get("fields") or []]
        code = pick_field(names, CODE_FIELDS)
        if code is None:
            continue
        return {
            "layer_url": url,
            "order_by": meta.get("objectIdField") or "OBJECTID",
            "fields": {
                k: v
                for k, v in (
                    ("zone_code", code),
                    ("zone_desc", pick_field([n for n in names if n != code], DESC_FIELDS)),
                    ("jurisdiction", pick_field(names, JURIS_FIELDS)),
                )
                if v
            },
        }
    return None


def build(
    client: PoliteClient,
    states: Sequence[StateShape],
    cache: dict[str, Any] | None = None,
    save: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """`cache` maps service URL to its layer pick (or None), so a restarted build skips
    services it already read; `save` is called with the cache every 50 new reads."""
    cache = {} if cache is None else cache
    reads = 0
    layers: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for item in search_items(client):
        title = str(item.get("title") or "")
        lic = license_class(item.get("licenseInfo"))
        entry = {"item_id": item["id"], "title": title, "owner": item.get("owner"),
                 "access": _TAGS.sub(" ", item.get("accessInformation") or "").strip()[:200],
                 "license_class": lic, "service_url": item.get("url")}  # fmt: skip
        if not is_base_zoning(title):
            excluded.append({**entry, "reason": "not base zoning"})
            continue
        if lic == "restricted":
            text = _TAGS.sub(" ", item["licenseInfo"])[:400]
            excluded.append({**entry, "reason": "license restricts use", "license_text": text})
            continue
        host = urllib.parse.urlparse(entry["service_url"] or "").hostname or ""
        if not re.fullmatch(r"services\d*\.arcgis\.com", host):
            review.append({**entry, "reason": f"host {host} not on the network allowlist"})
            continue
        ext = item.get("extent") or [[0, 0], [0, 0]]
        cx, cy = (ext[0][0] + ext[1][0]) / 2, (ext[0][1] + ext[1][1]) / 2
        state = state_at(states, cx, cy)
        if state is None:
            review.append({**entry, "reason": "extent center outside every state"})
            continue
        if lic == "empty":
            review.append({**entry, "state_fips": state, "reason": "no license text"})
            continue
        try:
            url = entry["service_url"]
            if url in cache:
                picked = cache[url]
            else:
                picked = cache[url] = pick_layer(client, url)
                reads += 1
                if save is not None and reads % 50 == 0:
                    save(cache)
        except Exception as exc:
            review.append({**entry, "reason": f"service unreadable: {str(exc)[:80]}"})
            continue
        if picked is None:
            review.append({**entry, "reason": "no polygon layer with a zone-code field"})
            continue
        layers.append({**entry, "state_fips": state, **picked})
    key = "item_id"
    return {
        "query": QUERY,
        "bbox": US_BBOX,
        "loadable_license_classes": list(LOADABLE),
        "layers": sorted(layers, key=lambda e: e[key]),
        "review": sorted(review, key=lambda e: e[key]),
        "excluded": sorted(excluded, key=lambda e: e[key]),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="equity.zoning_catalog")
    ap.add_argument("command", choices=["build"])
    ap.add_argument("--out", type=Path, default=CATALOG)
    args = ap.parse_args(argv)
    client = PoliteClient(min_interval_s=0.5)
    resp = client.get(STATES_ZIP, {})
    states = load_states(resp.content)
    cache_path = Path("data/work/zoning_catalog_cache.json")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    def save(c: dict[str, Any]) -> None:
        cache_path.write_text(json.dumps(c))
        print(f"{len(c)} services read", flush=True)

    cat = build(client, states, cache, save)
    save(cache)
    args.out.write_text(json.dumps(cat, indent=1, sort_keys=True) + "\n")
    print(f"{len(cat['layers'])} loadable, {len(cat['review'])} to review, "
          f"{len(cat['excluded'])} excluded -> {args.out}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
