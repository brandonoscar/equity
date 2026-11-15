"""Queries that fail the build when the data breaks a non-negotiable.

Each check returns a list of human-readable violations; empty means pass. The checks are
generic over equity.schema.catalog, so a new fact table is covered the moment it is
registered there.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from equity.config import DocTypes
from equity.schema.catalog import FACT_TABLES, PROVENANCE_COLUMNS


@dataclass(frozen=True)
class Violation:
    check: str
    table: str
    count: int
    detail: str

    def __str__(self) -> str:
        return f"[{self.check}] {self.table}: {self.count} row(s) {self.detail}"


def _count(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = con.execute(sql).fetchone()
    return 0 if row is None else int(row[0])


def _tables_present(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute("SELECT table_name FROM information_schema.tables").fetchall()
    return {str(r[0]) for r in rows}


def provenance_violations(
    con: duckdb.DuckDBPyConnection, tables: list[str] | None = None
) -> list[Violation]:
    """Every fact row must trace to a source record, fetch and source, with a retrieval time."""
    out: list[Violation] = []
    present = _tables_present(con)
    for table in tables if tables is not None else sorted(FACT_TABLES):
        if table not in present:
            out.append(Violation("provenance", table, 1, "table is missing"))
            continue
        for col in PROVENANCE_COLUMNS:
            empty = f"{col} IS NULL" + (
                "" if col == "retrieved_at" else f" OR CAST({col} AS VARCHAR) = ''"
            )
            n = _count(con, f"SELECT count(*) FROM {table} WHERE {empty}")  # noqa: S608
            if n:
                out.append(Violation("provenance", table, n, f"have null/empty {col}"))
        n = _count(
            con,
            f"SELECT count(*) FROM {table} f LEFT JOIN source_record s "  # noqa: S608
            "ON s.source_record_id = f.source_record_id WHERE s.source_record_id IS NULL",
        )
        if n:
            out.append(Violation("provenance", table, n, "point at a missing source_record"))
        n = _count(
            con,
            f"SELECT count(*) FROM {table} f JOIN source_record s "  # noqa: S608
            "ON s.source_record_id = f.source_record_id WHERE s.source_id <> f.source_id",
        )
        if n:
            out.append(
                Violation("provenance", table, n, "disagree with their source_record on source_id")
            )
        n = _count(
            con,
            f"SELECT count(*) FROM {table} WHERE retrieved_at > ingested_at",  # noqa: S608
        )
        if n:
            out.append(
                Violation("provenance", table, n, "were ingested before they were retrieved")
            )
    n = _count(
        con,
        "SELECT count(*) FROM source_record s LEFT JOIN fetch_log f ON f.fetch_id = s.fetch_id "
        "WHERE f.fetch_id IS NULL",
    )
    if n:
        out.append(Violation("provenance", "source_record", n, "point at a missing fetch"))
    n = _count(
        con,
        "SELECT count(*) FROM fetch_log f LEFT JOIN source s ON s.source_id = f.source_id "
        "WHERE s.source_id IS NULL",
    )
    if n:
        out.append(Violation("provenance", "fetch_log", n, "point at a missing source"))
    return out


def invariant_violations(con: duckdb.DuckDBPyConnection, doc_types: DocTypes) -> list[Violation]:
    out: list[Violation] = []

    def check(name: str, table: str, sql: str, detail: str) -> None:
        n = _count(con, sql)
        if n:
            out.append(Violation(name, table, n, detail))

    # 1. Nothing dated after we retrieved it.
    for table, spec in sorted(FACT_TABLES.items()):
        for col in spec.not_after_retrieval:
            check(
                "future_date",
                table,
                f"SELECT count(*) FROM {table} WHERE {col} > CAST(retrieved_at AS DATE)",  # noqa: S608
                f"have {col} after retrieved_at",
            )

    # 2. No negative amounts in any DECIMAL column of any fact table.
    money = con.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE data_type LIKE 'DECIMAL%' ORDER BY table_name, column_name"
    ).fetchall()
    for table, col in money:
        if table in FACT_TABLES:
            check(
                "negative_amount",
                str(table),
                f"SELECT count(*) FROM {table} WHERE {col} < 0",  # noqa: S608
                f"have negative {col}",
            )

    # 3. No parcel-specific lien or notice without a parcel.
    specific = ", ".join(f"'{t}'" for t in doc_types.parcel_specific)
    if specific:
        check(
            "lien_without_parcel",
            "instrument",
            f"""SELECT count(*) FROM instrument i
                WHERE i.superseded_at IS NULL AND i.doc_type IN ({specific})
                  AND NOT EXISTS (SELECT 1 FROM instrument_parcel p
                                  WHERE p.instrument_uid = i.instrument_uid
                                    AND p.superseded_at IS NULL)""",  # noqa: S608
            "parcel-specific liens/notices have no current instrument_parcel row",
        )

    # 4. No merged entity without link evidence.
    check(
        "entity_without_link",
        "entity",
        "SELECT count(*) FROM entity e LEFT JOIN entity_link l ON l.link_id = e.created_by_link_id "
        "WHERE l.link_id IS NULL",
        "were created without an entity_link record",
    )
    check(
        "link_without_evidence",
        "entity_link",
        "SELECT count(*) FROM entity_link WHERE decision IN ('auto', 'human_accept') "
        "AND (signals IS NULL OR json_array_length(json_keys(signals)) = 0)",
        "accepted links carry no evidence signals",
    )
    check(
        "dangling_link",
        "entity_link",
        "SELECT count(*) FROM entity_link l LEFT JOIN party p ON p.party_id = l.party_id "
        "LEFT JOIN entity e ON e.entity_id = l.entity_id "
        "WHERE p.party_id IS NULL OR e.entity_id IS NULL",
        "reference a missing party or entity",
    )

    # 5. Edges must point at things that exist.
    edges = [
        ("instrument_party", "instrument_uid", "instrument", "instrument_uid"),
        ("instrument_party", "party_id", "party", "party_id"),
        ("instrument_parcel", "instrument_uid", "instrument", "instrument_uid"),
        ("instrument_parcel", "parcel_uid", "parcel", "parcel_uid"),
        ("instrument_ref", "from_uid", "instrument", "instrument_uid"),
        ("instrument_ref", "to_uid", "instrument", "instrument_uid"),
        ("ownership_period", "parcel_uid", "parcel", "parcel_uid"),
        ("ownership_period", "party_id", "party", "party_id"),
        ("case_party", "case_uid", "court_case", "case_uid"),
        ("case_party", "party_id", "party", "party_id"),
        ("judgment", "case_uid", "court_case", "case_uid"),
        ("judgment_event", "judgment_uid", "judgment", "judgment_uid"),
        ("business_role", "party_id", "party", "party_id"),
        ("parcel_assessment", "parcel_uid", "parcel", "parcel_uid"),
        ("tax_bill", "parcel_uid", "parcel", "parcel_uid"),
        ("tax_sale_event", "parcel_uid", "parcel", "parcel_uid"),
    ]
    for table, col, target, target_col in edges:
        check(
            "dangling_reference",
            table,
            f"SELECT count(*) FROM {table} x WHERE x.superseded_at IS NULL "  # noqa: S608
            f"AND NOT EXISTS (SELECT 1 FROM {target} y WHERE y.{target_col} = x.{col})",
            f"have {col} with no matching {target}",
        )

    # 6. At most one current version per domain key.
    for table, spec in sorted(FACT_TABLES.items()):
        key = ", ".join(("source_id", *spec.domain_key))
        check(
            "duplicate_current",
            table,
            f"SELECT count(*) FROM (SELECT {key} FROM {table} WHERE superseded_at IS NULL "  # noqa: S608
            f"GROUP BY ALL HAVING count(*) > 1)",
            "domain keys have more than one current row",
        )
    return out
