"""Minimal dBASE III (.dbf) reader: the attribute table of a shapefile.

Only what parcel shapefiles use: C (text), N/F (numbers, kept as text), D (YYYYMMDD -> ISO date),
L (logical). Deleted records (flag '*') are skipped. Values are returned as stripped strings or
None, never converted further: the adapter decides what each field means.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from typing import IO


@dataclass(frozen=True)
class DbfField:
    name: str
    kind: str
    length: int


@dataclass(frozen=True)
class DbfHeader:
    records: int
    header_len: int
    record_len: int
    fields: tuple[DbfField, ...]


def _read_exact(stream: IO[bytes], n: int) -> bytes:
    data = stream.read(n)
    if len(data) != n:
        raise ValueError(f"dbf truncated: wanted {n} bytes, got {len(data)}")
    return data


def read_header(stream: IO[bytes]) -> DbfHeader:
    head = _read_exact(stream, 32)
    records, header_len, record_len = struct.unpack("<IHH", head[4:12])
    fields: list[DbfField] = []
    body = _read_exact(stream, header_len - 32)
    for i in range(0, len(body) - 1, 32):
        if body[i] == 0x0D:
            break
        desc = body[i : i + 32]
        name = desc[:11].split(b"\0", 1)[0].decode("ascii").strip()
        fields.append(DbfField(name, chr(desc[11]), desc[16]))
    if sum(f.length for f in fields) + 1 != record_len:
        raise ValueError("dbf field lengths do not add up to the record length")
    return DbfHeader(records, header_len, record_len, tuple(fields))


def _value(raw: bytes, kind: str, encoding: str) -> str | None:
    text = raw.decode(encoding, errors="replace").strip()
    if not text or (kind in "NF" and set(text) <= {"*"}):
        return None
    if kind == "D":
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text) == 8 and text.isdigit() else None
    if kind == "L":
        return {"Y": "true", "T": "true", "N": "false", "F": "false"}.get(text.upper())
    return text


def read_records(
    stream: IO[bytes], start: int = 0, stop: int | None = None, encoding: str = "utf-8"
) -> Iterator[tuple[int, dict[str, str | None]]]:
    """Yield (record index, {field: value}) for records start <= index < stop. The stream is
    read forward only, so it can be a zip member."""
    header = read_header(stream)
    end = header.records if stop is None else min(stop, header.records)
    for index in range(end):
        rec = _read_exact(stream, header.record_len)
        if index < start or rec[:1] == b"*":
            continue
        row: dict[str, str | None] = {}
        pos = 1
        for f in header.fields:
            row[f.name] = _value(rec[pos : pos + f.length], f.kind, encoding)
            pos += f.length
        yield index, row


def record_count(stream: IO[bytes]) -> int:
    return read_header(stream).records
