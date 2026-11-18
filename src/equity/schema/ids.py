"""Deterministic identifiers. Same natural key in, same id out, on every machine."""

from __future__ import annotations

import hashlib

_SEP = "\x1f"  # ASCII unit separator: cannot appear in normalized key parts


def stable_id(*parts: str) -> str:
    """Return a 32-hex-char id derived from the given key parts.

    Parts are joined with a separator that normalized text never contains, so
    ("ab", "c") and ("a", "bc") hash differently.
    """
    if not parts:
        raise ValueError("stable_id needs at least one key part")
    for part in parts:
        if _SEP in part:
            raise ValueError("key part contains the reserved separator")
    return hashlib.sha256(_SEP.join(parts).encode("utf-8")).hexdigest()[:32]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
