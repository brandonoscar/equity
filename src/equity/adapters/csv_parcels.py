"""Config-driven parcel-owner adapters for plain CSV files, whole or as one member of a zip.

Some assessors and appraisal districts publish their roll only as a CSV download (no ArcGIS
layer, no open-data API). One YAML file per source in config/bulk/<source_id>.yaml, in the
statewide-parcel vocabulary (config/states/README.md, read by state_parcels.load_config:
`fields`, `county`, `terms`, `value_basis`...) plus a `csv` block, which is what marks a bulk
config as one of these:

  csv:
    member: 2025.csv         # a zip archive: the member to read, matched by file name
                             # (omit for a plain CSV)
    encoding: utf-8-sig      # default utf-8-sig (a byte-order mark is dropped)
    exclude_prefix:          # rows dropped when a column starts with one of the prefixes
      Account: [BP, SI]      #   (e.g. business personal property accounts: not parcels)
    null_values: ["*** CONFIDENTIAL OWNER ***"]   # cell texts that name nobody: read as empty
    slice_rows: 50000        # rows per partition (default: the whole file in one). Only for
                             # files with one row per parcel: a parcel's rows must not straddle
                             # two partitions.

layer_url is the file's URL and county a constant (one county per file). Rows come out
exactly as from the ArcGIS path: normalization is StateParcelAdapter's, and pii_fields are
derived the same way. Fetched rows keep only the mapped columns, plus `_row`: the record's
index in the file (0 = the first line after the header), usable as order_by.

A zip member is read over HTTP Range requests when the host serves them (the central
directory, then the member's own bytes), so one year out of a 300 MB archive of yearly files
costs about 10 MB; a host without ranges gets one whole download. A file cut into slices is
cached in data/work/csv_parcels/ by the plan and deleted after its last slice; each slice
checks the file is still the planned size.
"""

from __future__ import annotations

import csv
import io
import math
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import yaml

from equity.adapters.base import Fetched, FetchRequest, HealthReport
from equity.adapters.federal.bulk_files import BulkClient, remote_zip
from equity.adapters.rows import canonical_json
from equity.adapters.state_parcels import (
    StateConfig,
    StateConfigError,
    StateParcelAdapter,
    load_config,
)
from equity.config import CONFIG_DIR

CSV_DIR = CONFIG_DIR / "bulk"
ROW = "_row"  # record index in the file, added by the adapter
FIXTURE_BYTES = 262_144  # a fixture (limit=N) reads this much of the file
HEAD_BYTES = 65_536  # health reads this much: the header line
_KEYS = frozenset({"member", "encoding", "exclude_prefix", "null_values", "slice_rows"})


class CsvParcelError(RuntimeError):
    pass


@dataclass(frozen=True)
class CsvParcelConfig:
    base: StateConfig
    member: str | None
    encoding: str
    exclude_prefix: Mapping[str, tuple[str, ...]]
    null_values: frozenset[str]
    slice_rows: int | None


def is_csv_config(path: Path) -> bool:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return isinstance(data, dict) and "csv" in data


def load_csv_config(path: Path) -> CsvParcelConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec = data.get("csv") if isinstance(data, dict) else None
    if not isinstance(spec, dict):
        raise StateConfigError(f"{path.name}: needs a csv block")
    unknown = set(spec) - _KEYS
    if unknown:
        raise StateConfigError(f"{path.name}: unknown csv keys {sorted(unknown)}")
    base = load_config(path)
    if base.layers or "constant" not in base.county:
        raise StateConfigError(f"{path.name}: one file per config, with a constant county")
    if not base.layer_url.startswith("https://"):
        raise StateConfigError(f"{path.name}: layer_url must be an https:// file URL")
    exclude = spec.get("exclude_prefix") or {}
    if not isinstance(exclude, dict) or not all(
        isinstance(v, list) and v and all(isinstance(x, str) and x for x in v)
        for v in exclude.values()
    ):
        raise StateConfigError(f"{path.name}: exclude_prefix maps a column to a list of prefixes")
    member = spec.get("member")
    if member is not None and ("/" in str(member) or not str(member).strip()):
        raise StateConfigError(f"{path.name}: csv.member is a file name, without folders")
    slice_rows = spec.get("slice_rows")
    if slice_rows is not None and int(slice_rows) < 1:
        raise StateConfigError(f"{path.name}: csv.slice_rows must be positive")
    return CsvParcelConfig(
        base=base,
        member=None if member is None else str(member),
        encoding=str(spec.get("encoding", "utf-8-sig")),
        exclude_prefix={str(k): tuple(v) for k, v in sorted(exclude.items())},
        null_values=frozenset(str(v).strip().upper() for v in spec.get("null_values") or ()),
        slice_rows=None if slice_rows is None else int(slice_rows),
    )


class CsvParcelAdapter(StateParcelAdapter):
    """StateParcelAdapter's normalization over one CSV file."""

    csv_config: ClassVar[CsvParcelConfig]
    access_method: ClassVar[str] = "bulk"
    cache_dir: ClassVar[Path] = Path("data") / "work" / "csv_parcels"

    def __init__(self, client: BulkClient | None = None) -> None:
        self.params = {"page_size": self.config.page_size}
        self.client: BulkClient = client or BulkClient(
            min_interval_s=self.config.min_interval_s, timeout_s=600.0
        )

    def source_row(self) -> Mapping[str, Any]:
        return {**super().source_row(), "access_method": "bulk"}

    @property
    def _columns(self) -> tuple[str, ...]:
        """The file columns fetched rows keep: every mapped one."""
        return tuple(f for f in self.fields if f != ROW)

    @property
    def _required(self) -> frozenset[str]:
        return frozenset(self._columns) | set(self.csv_config.exclude_prefix)

    # -- reading the file ---------------------------------------------------------------
    def _member_name(self, zf: zipfile.ZipFile) -> str:
        want = self.csv_config.member
        names = [n for n in zf.namelist() if n.rsplit("/", 1)[-1] == want]
        if len(names) != 1:
            raise CsvParcelError(f"{self.config.layer_url}: {len(names)} members named {want}")
        return names[0]

    def _zip(self) -> zipfile.ZipFile:
        """The archive over byte ranges, or downloaded whole when the host has no ranges."""
        try:
            return remote_zip(self.client, self.config.layer_url)
        except RuntimeError:
            resp = self.client.get(self.config.layer_url)
            if resp.status != 200:
                raise CsvParcelError(f"HTTP {resp.status} from {resp.url}") from None
            return zipfile.ZipFile(io.BytesIO(resp.content))

    def _read(self, prefix: int | None = None) -> tuple[bytes, datetime]:
        """The CSV's bytes (only about the first `prefix` bytes, cut after the last complete
        line, when given) and when they were retrieved."""
        url = self.config.layer_url
        if self.csv_config.member is not None:
            with self._zip() as zf, zf.open(self._member_name(zf)) as f:
                data = f.read() if prefix is None else f.read(prefix)
            at = self.client.now()
        else:
            resp = (
                self.client.get(url)
                if prefix is None
                else self.client.get_range(url, 0, prefix - 1)
            )
            if resp.status not in (200, 206):
                raise CsvParcelError(f"HTTP {resp.status} from {url}")
            data = resp.content if prefix is None else resp.content[:prefix]
            at = resp.retrieved_at
        if prefix is not None and len(data) >= prefix:
            data = data[: data.rfind(b"\n") + 1]  # the last line may be cut off
        return data, at

    def _cached(self) -> Path:
        return self.cache_dir / f"{self.source_id}.csv"

    def _file(self, size: int | None) -> tuple[bytes, datetime]:
        """The whole file: the cached copy when it has the planned size, else a fresh read
        (cached for the next slice). A fresh read of another size than planned is refused."""
        cached = self._cached()
        if size is not None and cached.exists() and cached.stat().st_size == size:
            return cached.read_bytes(), self.client.now()
        data, at = self._read()
        if size is not None and len(data) != size:
            raise CsvParcelError(
                f"{self.source_id}: the file is {len(data)} bytes, the plan was cut from "
                f"{size}: plan again"
            )
        cached.parent.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(cached)
        return data, at

    def _header(self, reader: Iterator[list[str]]) -> list[str]:
        header = [h.strip() for h in next(reader, [])]
        missing = sorted(self._required - set(header))
        if missing:
            raise CsvParcelError(f"{self.source_id}: columns missing from the file: {missing}")
        return header

    def _rows(self, data: bytes) -> list[dict[str, str]]:
        """Kept rows, mapped columns only, in file order. Blank lines and excluded rows are
        dropped; `_row` stays the record's index in the file either way."""
        reader = csv.reader(io.StringIO(data.decode(self.csv_config.encoding), newline=""))
        header = self._header(reader)
        at = {h: i for i, h in reversed(list(enumerate(header)))}  # first column of a name

        def cell(rec: list[str], col: str) -> str:
            i = at[col]
            return rec[i] if i < len(rec) else ""

        exclude = [(col, tuple(p.upper() for p in pre))
                   for col, pre in self.csv_config.exclude_prefix.items()]  # fmt: skip
        rows: list[dict[str, str]] = []
        for n, rec in enumerate(reader):
            if not any(v.strip() for v in rec):
                continue
            if any(cell(rec, col).strip().upper().startswith(pre) for col, pre in exclude):
                continue
            row = {c: cell(rec, c) for c in self._columns}
            row[ROW] = str(n)
            rows.append(row)
        return rows

    # -- partitioning and fetching ------------------------------------------------------
    def partitions(self, window: int = 0) -> Iterator[dict[str, str]]:
        """One partition for the whole file, or slices of at most slice_rows kept rows (the
        file is read once here to count them, and cached for the slices)."""
        size = self.csv_config.slice_rows
        if not size:
            yield {"slice": "0", "slices": "1"}
            return
        data, _ = self._file(None)
        slices = max(1, math.ceil(len(self._rows(data)) / size))
        for i in range(slices):
            yield {"slice": str(i), "slices": str(slices), "bytes": str(len(data))}

    def split_partition(self, params: Mapping[str, str]) -> list[dict[str, str]]:
        return [dict(params)]

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: slice, slices, bytes (from partitions; default the whole file); optional
        limit = the file's first kept rows only (fixtures)."""
        p = request.params
        index, slices = int(p.get("slice", "0")), int(p.get("slices", "1"))
        if "limit" in p:
            data, at = self._read(FIXTURE_BYTES)
            rows = self._rows(data)[: int(p["limit"])]
            start, stop = 0, len(rows)
        else:
            data, at = self._file(int(p["bytes"]) if "bytes" in p else None)
            rows = self._rows(data)
            start, stop = len(rows) * index // slices, len(rows) * (index + 1) // slices
            rows = rows[start:stop]
            if index == slices - 1:
                self._cached().unlink(missing_ok=True)
        member = self.csv_config.member
        body = canonical_json({"layer": self.config.layer_url, "member": member,
                               "rows": [start, stop], "attributes": rows})  # fmt: skip
        where = f"member={member}&" if member else ""
        url = f"{self.config.layer_url}#{where}rows={start}-{stop}"
        return Fetched(self.source_id, url, at, 200, body, "application/json")

    def health(self) -> HealthReport:
        """Live: the file (the zip member) is there and its header has every mapped column."""
        try:
            data, _ = self._read(HEAD_BYTES)
            text = data.decode(self.csv_config.encoding, "replace")
            self._header(iter(csv.reader(io.StringIO(text, newline=""))))
        except (CsvParcelError, ValueError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
            return HealthReport(self.source_id, False, self.client.now(), repr(exc))
        return HealthReport(self.source_id, True, self.client.now(), "ok",
                            tuple(sorted(self._columns)))  # fmt: skip

    def layer_of(self, fetched: Fetched) -> int:
        return 0

    # -- normalization ------------------------------------------------------------------
    def _get(self, attrs: Mapping[str, Any], canonical: str) -> Any:
        value = super()._get(attrs, canonical)
        if isinstance(value, str) and value.strip().upper() in self.csv_config.null_values:
            return None
        return value


def csv_adapter_for(cfg: CsvParcelConfig) -> type[CsvParcelAdapter]:
    base = cfg.base
    return type(
        "CsvParcels_" + base.source_id.replace(".", "_"),
        (CsvParcelAdapter,),
        {
            "config": base,
            "csv_config": cfg,
            "source_id": base.source_id,
            "layer_url": base.layer_url,
            "fields": base.source_fields,
            "order_by": (base.order_by,),
            "pii_fields": base.pii_fields,
            "health_where": "1=1",
            "__module__": __name__,
        },
    )


def csv_config_paths(*dirs: Path) -> list[Path]:
    return [p for d in (dirs or (CSV_DIR,)) for p in sorted(d.glob("*.yaml")) if is_csv_config(p)]


def all_csv_parcel_adapters(*dirs: Path) -> list[type[CsvParcelAdapter]]:
    return [csv_adapter_for(load_csv_config(p)) for p in csv_config_paths(*dirs)]
