"""What each table is, so loaders, gates and as-of queries treat them uniformly."""

from __future__ import annotations

from dataclasses import dataclass

# Columns every fact table carries. The provenance gate fails the build if any is null/empty.
PROVENANCE_COLUMNS: tuple[str, ...] = (
    "source_record_id",
    "source_id",
    "jurisdiction",
    "record_key",
    "source_uri",
    "retrieved_at",
    "content_sha256",
)
TRANSACTION_COLUMNS: tuple[str, ...] = ("ingested_at", "superseded_at")
# Columns the loader owns. Callers never pass them.
LOADER_COLUMNS: tuple[str, ...] = ("row_id", "fact_hash", *TRANSACTION_COLUMNS)


@dataclass(frozen=True)
class FactTable:
    name: str
    # Natural key of one fact *within one source*. A new version with the same key
    # supersedes the old one. source_id is always prepended.
    domain_key: tuple[str, ...]
    # Valid-time column(s): a single event date, or a (valid_from, valid_to) interval.
    event_date: str | None = None
    interval: bool = False
    # Date columns that must not be later than the retrieval date.
    not_after_retrieval: tuple[str, ...] = ()
    # Columns excluded from change detection: the first loaded value is kept (e.g. the date a
    # snapshot value was first observed).
    unhashed: tuple[str, ...] = ()


FACT_TABLES: dict[str, FactTable] = {
    t.name: t
    for t in (
        FactTable("party", ("party_id",)),
        FactTable("data_issue", ("record_key", "issue_code")),
        FactTable("business", ("sos_id", "valid_from"), interval=True),
        FactTable("business_role", ("sos_id", "party_id", "role", "valid_from"), interval=True),
        FactTable("parcel", ("parcel_uid",)),
        FactTable("parcel_geometry", ("parcel_uid", "valid_from"), interval=True),
        FactTable("zoning_district", ("zone_uid",)),
        FactTable("code_link", ("jurisdiction_uid",)),
        FactTable("parcel_assessment", ("parcel_uid", "tax_year"), interval=True),
        FactTable(
            "ownership_period",
            ("parcel_uid", "owner_seq", "valid_from"),
            interval=True,
            not_after_retrieval=("valid_from",),
        ),
        FactTable(
            "owner_snapshot",
            ("parcel_uid", "owner_seq"),
            not_after_retrieval=("observed_on",),
            unhashed=("observed_on",),
        ),
        FactTable(
            "instrument",
            ("instrument_uid",),
            event_date="recorded_on",
            not_after_retrieval=("recorded_on", "executed_on"),
        ),
        FactTable("instrument_party", ("instrument_uid", "role", "seq")),
        FactTable("instrument_parcel", ("instrument_uid", "parcel_uid")),
        FactTable("instrument_ref", ("from_uid", "to_uid", "ref_type")),
        FactTable("instrument_image", ("instrument_uid", "page_no")),
        FactTable(
            "court_case",
            ("case_uid",),
            event_date="filed_on",
            not_after_retrieval=("filed_on", "closed_on"),
        ),
        FactTable("case_party", ("case_uid", "role", "party_id")),
        FactTable(
            "judgment",
            ("judgment_uid",),
            event_date="entered_on",
            not_after_retrieval=("entered_on",),
        ),
        FactTable(
            "judgment_event",
            ("judgment_uid", "event", "event_date"),
            event_date="event_date",
            not_after_retrieval=("event_date",),
        ),
        FactTable(
            "bankruptcy",
            ("case_uid",),
            event_date="petition_on",
            not_after_retrieval=("petition_on", "discharge_on", "dismissed_on", "converted_on"),
        ),
        FactTable(
            "docket_entry",
            ("case_uid", "entry_no", "entry_date", "text"),
            event_date="entry_date",
            not_after_retrieval=("entry_date",),
        ),
        FactTable("tax_bill", ("parcel_uid", "tax_year", "ticket"), event_date="as_of"),
        FactTable(
            "tax_delinquency_snapshot",
            ("parcel_uid", "certificate_no"),
            not_after_retrieval=("observed_on",),
            unhashed=("observed_on",),
        ),
        FactTable(
            "tax_sale_event",
            ("parcel_uid", "event", "event_date"),
            event_date="event_date",
            not_after_retrieval=("event_date",),
        ),
    )
}

# Provenance backbone tables, loaded insert-if-absent by primary key.
PROVENANCE_TABLES: dict[str, str] = {
    "source": "source_id",
    "fetch_log": "fetch_id",
    "source_record": "source_record_id",
}

# Lookup/derived tables that are not source facts.
OTHER_TABLES: dict[str, str] = {
    "address": "address_id",
    "entity": "entity_id",
    "entity_link": "link_id",
    "review_queue": "link_id",
    "rule_run": "run_id",
    "rule_output": "row_id",
}


def primary_key(table: str) -> str:
    if table in FACT_TABLES:
        return "row_id"
    if table in PROVENANCE_TABLES:
        return PROVENANCE_TABLES[table]
    if table in OTHER_TABLES:
        return OTHER_TABLES[table]
    raise KeyError(f"unknown table {table!r}")


def all_tables() -> list[str]:
    return sorted([*FACT_TABLES, *PROVENANCE_TABLES, *OTHER_TABLES])
