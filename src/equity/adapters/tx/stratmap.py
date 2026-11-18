"""Texas statewide parcels: TxGIO StratMap Land Parcels, one shapefile zip per county.

The county zips sit in TxGIO's public S3 bucket (access decision in config/bulk/tx.stratmap.yaml).
Each partition is a slice of one county's .dbf, so the largest counties (Harris: about 1.6M
parcels) never have to be held in memory at once. A county's zip is downloaded once into a
local cache, read slice by slice, and deleted after its last slice.

Normalization is the shared statewide-parcel code: the .dbf attributes are handed over in the
same shape an ArcGIS layer would return.
"""

from __future__ import annotations

import io
import json
import math
import re
import urllib.parse
import zipfile
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, ClassVar

from equity.adapters.base import Fetched, FetchRequest, HealthReport
from equity.adapters.dbf import read_records, record_count
from equity.adapters.rows import canonical_json
from equity.adapters.state_parcels import adapter_for, load_config
from equity.config import CONFIG_DIR

CONFIG = load_config(CONFIG_DIR / "bulk" / "tx.stratmap.yaml")
# stratmap26-landparcels_48201_lp.zip; the statewide file (…_48_lp.zip) is skipped.
COUNTY_ZIP = re.compile(r"stratmap\d{2}-landparcels_48(?P<county>\d{3})_lp\.zip$")
# About 50k parcels per slice: county zips run ~270 bytes per parcel.
SLICE_ZIP_BYTES = 15_000_000
_Base = adapter_for(CONFIG)


def list_bucket(xml: str) -> list[tuple[str, int]]:
    """(key, size) pairs from one S3 ListObjectsV2 page."""
    keys = re.findall(r"<Key>([^<]+)</Key>", xml)
    sizes = [int(s) for s in re.findall(r"<Size>(\d+)</Size>", xml)]
    if len(keys) != len(sizes):
        raise ValueError("S3 listing: keys and sizes do not pair up")
    return list(zip(keys, sizes, strict=True))


class TexasStratMapParcels(_Base):  # type: ignore[valid-type,misc]
    access_method: ClassVar[str] = "bulk"
    cache_dir: ClassVar[Path] = Path("data") / "work" / "tx_stratmap"

    def source_row(self) -> Mapping[str, Any]:
        return {**super().source_row(), "access_method": "bulk"}

    # -- the bucket ---------------------------------------------------------------------
    def _bucket_and_prefix(self) -> tuple[str, str]:
        parts = urllib.parse.urlsplit(self.config.layer_url)
        bucket, _, prefix = parts.path.lstrip("/").partition("/")
        return f"{parts.scheme}://{parts.netloc}/{bucket}/", prefix

    def county_zips(self) -> list[tuple[str, str, int]]:
        """(county fips3, object key, size) for every county zip in the collection, sorted."""
        base, prefix = self._bucket_and_prefix()
        found: list[tuple[str, str, int]] = []
        token: str | None = None
        while True:
            params = {"list-type": "2", "prefix": prefix}
            if token:
                params["continuation-token"] = token
            xml = self.client.get(base, params).content.decode("utf-8")
            for key, size in list_bucket(xml):
                m = COUNTY_ZIP.search(key)
                if m:
                    found.append((m.group("county"), key, size))
            nxt = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", xml)
            if not nxt:
                return sorted(found)
            token = nxt.group(1)

    def partitions(self, window: int = 0) -> Iterator[dict[str, str]]:
        for county, key, size in self.county_zips():
            slices = max(1, math.ceil(size / SLICE_ZIP_BYTES))
            for i in range(slices):
                yield {"county_fips": county, "key": key, "size": str(size),
                       "slice": str(i), "slices": str(slices)}  # fmt: skip

    # -- fetching -----------------------------------------------------------------------
    def _zip_bytes(self, key: str, size: int) -> tuple[bytes, Any]:
        """The county zip, from the local cache when a complete copy is there."""
        base, _ = self._bucket_and_prefix()
        cached = self.cache_dir / Path(key).name
        if cached.exists() and cached.stat().st_size == size:
            return cached.read_bytes(), self.client.now()
        resp = self.client.get(base + key)
        if resp.status != 200 or len(resp.content) != size:
            raise ValueError(f"{key}: status {resp.status}, {len(resp.content)} of {size} bytes")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_suffix(".part")
        tmp.write_bytes(resp.content)
        tmp.replace(cached)
        return resp.content, resp.retrieved_at

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: key, size, slice, slices (from partitions); optional limit (fixtures)."""
        p = request.params
        key, size = p["key"], int(p["size"])
        index, slices = int(p.get("slice", "0")), int(p.get("slices", "1"))
        content, retrieved_at = self._zip_bytes(key, size)
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # Large counties ship split files (Harris: -east and -west): read them in name
            # order as one table, so record numbers are stable across slices.
            dbfs = sorted(n for n in zf.namelist() if n.lower().endswith(".dbf"))
            if not dbfs:
                raise ValueError(f"{key}: no .dbf in the zip")
            cpg = [n for n in zf.namelist() if n.lower().endswith(".cpg")]
            encoding = zf.read(cpg[0]).decode("ascii").strip().lower() if cpg else "utf-8"
            encoding = "utf-8" if encoding in ("utf-8", "utf8") else "cp1252"
            counts = []
            for name in dbfs:
                with zf.open(name) as f:
                    counts.append(record_count(f))
            total = sum(counts)
            start, stop = total * index // slices, total * (index + 1) // slices
            if "limit" in p:
                stop = min(stop, start + int(p["limit"]))
            rows: list[dict[str, Any]] = []
            offset = 0
            for name, n in zip(dbfs, counts, strict=True):
                lo, hi = max(start - offset, 0), min(stop - offset, n)
                if lo < hi:
                    with zf.open(name) as f:
                        rows += [{**rec, "_row": str(offset + i)}
                                 for i, rec in read_records(f, lo, hi, encoding)]  # fmt: skip
                offset += n
        if index == slices - 1 and "limit" not in p:
            (self.cache_dir / Path(key).name).unlink(missing_ok=True)
        body = canonical_json({"layer": self.config.layer_url, "key": key,
                               "rows": [start, stop], "attributes": rows})  # fmt: skip
        url = f"{self.config.layer_url}{Path(key).name}#rows={start}-{stop}"
        return Fetched(self.source_id, url, retrieved_at, 200, body, "application/json")

    def health(self) -> HealthReport:
        """Live: the collection still lists a zip for (nearly) every one of 254 counties."""
        try:
            zips = self.county_zips()
        except (ValueError, OSError) as exc:
            return HealthReport(self.source_id, False, self.client.now(), repr(exc))
        ok = len(zips) >= 250
        return HealthReport(self.source_id, ok, self.client.now(), f"{len(zips)} county zips")

    def layer_of(self, fetched: Fetched) -> int:
        return 0

    @staticmethod
    def attributes(fetched: Fetched) -> list[Mapping[str, Any]]:
        attrs = json.loads(fetched.content)["attributes"]
        if not isinstance(attrs, list):
            raise ValueError("fetched content has no attributes list")
        return attrs
