"""Typed access to YAML config. Code reads parameters from here; it never hard-codes them."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _load(name: str, config_dir: Path | None = None) -> dict[str, Any]:
    path = (config_dir or CONFIG_DIR) / name
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return data


def _str_tuple(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"doc_types.yaml: {key} must be a list of strings")
    return tuple(value)


@dataclass(frozen=True)
class DocTypes:
    lien: tuple[str, ...]
    notice: tuple[str, ...]
    parcel_specific: tuple[str, ...]
    general_lien: tuple[str, ...]
    terminating_refs: tuple[str, ...]
    parcel_scoped_terminating_refs: tuple[str, ...]

    @property
    def encumbrances(self) -> tuple[str, ...]:
        return (*self.lien, *self.notice)


def doc_types(config_dir: Path | None = None) -> DocTypes:
    data = _load("doc_types.yaml", config_dir)
    return DocTypes(
        lien=_str_tuple(data, "lien_doc_types"),
        notice=_str_tuple(data, "notice_doc_types"),
        parcel_specific=_str_tuple(data, "parcel_specific_doc_types"),
        general_lien=_str_tuple(data, "general_lien_doc_types"),
        terminating_refs=_str_tuple(data, "terminating_ref_types"),
        parcel_scoped_terminating_refs=_str_tuple(data, "parcel_scoped_terminating_ref_types"),
    )
