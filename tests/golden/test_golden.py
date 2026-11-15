"""Check 12: pipeline output must match Brandon's hand-verified golden cases exactly."""

from __future__ import annotations

from pathlib import Path

import yaml

HERE = Path(__file__).parent
REQUIRED = {"schema_version", "case_id", "verified_by", "verified_on", "as_of", "judgment",
            "debtor_entities", "parcels"}  # fmt: skip


def _cases() -> list[Path]:
    return sorted((HERE / "cases").glob("*.yaml"))


def test_template_is_valid_yaml_with_required_keys() -> None:
    data = yaml.safe_load((HERE / "TEMPLATE.yaml").read_text())
    assert set(data) >= REQUIRED


def test_golden_cases_match_pipeline_exactly() -> None:
    # One test over all cases so an empty cases/ directory passes rather than skipping.
    for path in _cases():
        case = yaml.safe_load(path.read_text())
        assert set(case) >= REQUIRED, f"{path.name}: missing keys"
        # Phase 5 provides equity.query.debtor_report. Until then this import fails, which
        # is the intended signal: a golden case exists that the pipeline cannot yet answer.
        from equity.query import debtor_report  # type: ignore[import-not-found]

        assert debtor_report(case["judgment"], as_of=case["as_of"]) == case, path.name
