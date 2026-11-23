"""Config files are well-formed, and legal parameters stay null until Brandon fills them."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from equity.config import CONFIG_DIR, doc_types
from equity.schema.enums import DOC_TYPES, REF_TYPES

STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
    "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
}  # fmt: skip
SOL_FIELDS = {
    "judgment_enforceable_years", "lien_years", "renewable", "renewal_years",
    "renewal_keeps_priority", "statute", "confirmed_by",
}  # fmt: skip


def test_doc_type_config_uses_known_values() -> None:
    cfg = doc_types()
    for group in (cfg.lien, cfg.notice, cfg.parcel_specific, cfg.general_lien):
        assert set(group) <= set(DOC_TYPES)
    assert set(cfg.terminating_refs) | set(cfg.parcel_scoped_terminating_refs) <= set(REF_TYPES)
    assert not set(cfg.lien) & set(cfg.notice)
    assert set(cfg.parcel_specific) <= set(cfg.encumbrances)
    assert set(cfg.general_lien) <= set(cfg.lien)


def test_doc_type_config_rejects_malformed(tmp_path: Path) -> None:
    (tmp_path / "doc_types.yaml").write_text("lien_doc_types: DEED\n")
    with pytest.raises(ValueError, match="list of strings"):
        doc_types(tmp_path)
    (tmp_path / "doc_types.yaml").write_text("- a\n")
    with pytest.raises(ValueError, match="mapping"):
        doc_types(tmp_path)


def test_sol_table_lists_every_state_with_every_field() -> None:
    data = yaml.safe_load((CONFIG_DIR / "sol.yaml").read_text())
    assert set(data["states"]) == STATES
    for state, fields in data["states"].items():
        assert set(fields) == SOL_FIELDS, state


def test_sol_values_are_only_set_with_a_citation_and_confirmer() -> None:
    data = yaml.safe_load((CONFIG_DIR / "sol.yaml").read_text())
    for state, f in data["states"].items():
        filled = [k for k, v in f.items() if v is not None and k not in {"statute", "confirmed_by"}]
        if filled:
            assert f["statute"] and f["confirmed_by"], (
                f"{state}: values need statute + confirmed_by"
            )


def test_rules_config_parses() -> None:
    data = yaml.safe_load((CONFIG_DIR / "rules.yaml").read_text())
    assert data["priority"]["method"] == "recording_date"


def test_sol_proposed_covers_every_state_and_is_unverified() -> None:
    """The research draft lists every state and never claims to be confirmed."""
    data = yaml.safe_load((CONFIG_DIR / "sol_proposed.yaml").read_text())
    assert set(data["states"]) == STATES
    for state, f in data["states"].items():
        assert f["lien_created_by"] in {"R", "D", "X", "D/R", "R/D"}, state
        assert f["verified"] is False, state
