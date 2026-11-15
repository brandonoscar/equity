"""The Python vocabularies match the SQL CHECK constraints exactly."""

from __future__ import annotations

import re

from equity.schema.enums import DOC_TYPES, REF_TYPES


def _check_values(con, table: str, column: str) -> set[str]:  # type: ignore[no-untyped-def]
    texts = [
        r[0]
        for r in con.execute(
            "SELECT expression FROM duckdb_constraints() "
            "WHERE table_name = ? AND constraint_type = 'CHECK'",
            [table],
        ).fetchall()
    ]
    for text in texts:
        m = re.search(rf"\b{column}\s+IN\s*\((.*?)\)\)?$", text, flags=re.S)
        if m:
            return set(re.findall(r"'([^']+)'", m.group(1)))
    raise AssertionError(f"no IN-list CHECK on {table}.{column}: {texts}")


def test_doc_types_match_sql(empty_db) -> None:  # type: ignore[no-untyped-def]
    assert _check_values(empty_db, "instrument", "doc_type") == set(DOC_TYPES)


def test_ref_types_match_sql(empty_db) -> None:  # type: ignore[no-untyped-def]
    assert _check_values(empty_db, "instrument_ref", "ref_type") == set(REF_TYPES)
