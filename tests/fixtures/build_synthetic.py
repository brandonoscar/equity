"""Generate the synthetic fixture county as normalized JSONL.

Every name and parcel here is fake (jurisdiction 99001 is not a real FIPS code). The repo is
public, so fixtures never contain real people. Run:

    uv run python tests/fixtures/build_synthetic.py

The generated files are committed; tests/test_fixtures_in_sync.py fails if they drift from
this script.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

OUT = Path(__file__).parent / "synthetic"
J = "99001"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


SOURCES = {
    "fixture.recorder": ("recorder", "file://fixtures/recorder"),
    "fixture.assessor": ("assessor", "file://fixtures/assessor"),
    "fixture.court": ("court", "file://fixtures/court"),
}


def source_rows() -> list[dict[str, Any]]:
    return [
        {
            "table": "source",
            "row": {
                "source_id": sid,
                "kind": "fixture",
                "jurisdiction": J,
                "access_method": "fixture",
                "base_url": url,
                "terms_url": None,
                "terms_summary": f"synthetic test data ({kind})",
                "terms_checked_on": None,
                "robots_checked_on": None,
                "cost_model": "free",
            },
        }
        for sid, (kind, url) in sorted(SOURCES.items())
    ]


class Batch:
    def __init__(self, fetch_id: str, source_id: str, retrieved_at: str) -> None:
        self.fetch_id = fetch_id
        self.source_id = source_id
        self.retrieved_at = retrieved_at
        self.lines: list[dict[str, Any]] = [
            {
                "table": "fetch_log",
                "row": {
                    "fetch_id": fetch_id,
                    "source_id": source_id,
                    "adapter": "fixture",
                    "adapter_version": "1",
                    "request": f"{SOURCES[source_id][1]}/{fetch_id}.json",
                    "retrieved_at": retrieved_at,
                    "http_status": None,
                    "content_sha256": sha(fetch_id),
                    "raw_path": f"fixtures/raw/{fetch_id}.json",
                    "bytes": 0,
                },
            }
        ]
        self._records: set[str] = set()

    def record(self, key: str, record_type: str) -> dict[str, str]:
        srid = f"sr-{self.fetch_id}-{key}"
        if srid not in self._records:
            self._records.add(srid)
            self.lines.append(
                {
                    "table": "source_record",
                    "row": {
                        "source_record_id": srid,
                        "fetch_id": self.fetch_id,
                        "source_id": self.source_id,
                        "record_key": key,
                        "record_type": record_type,
                        "raw_sha256": sha(srid),
                        "first_seen_at": self.retrieved_at,
                        "last_seen_at": self.retrieved_at,
                    },
                }
            )
        return {
            "source_record_id": srid,
            "source_id": self.source_id,
            "jurisdiction": J,
            "record_key": key,
            "source_uri": f"{SOURCES[self.source_id][1]}/{self.fetch_id}.json#{key}",
            "retrieved_at": self.retrieved_at,
            "content_sha256": sha(srid),
        }

    def fact(self, table: str, key: str, record_type: str, **row: Any) -> None:
        self.lines.append({"table": table, "row": {**row, **self.record(key, record_type)}})

    def party(self, key: str, party_id: str, raw: str, kind: str, **parts: Any) -> None:
        self.fact("party", key, "party", party_id=party_id, raw_name=raw, party_kind=kind, **parts)


def assessor_initial() -> Batch:
    b = Batch("f-assessor-2026-01", "fixture.assessor", "2026-01-10T12:00:00+00:00")
    for pid, local in (("99001-01-01-0001", "01-01-0001"), ("99001-01-01-0002", "01-01-0002")):
        b.fact(
            "parcel",
            local,
            "parcel",
            parcel_uid=pid,
            district="01",
            map="01",
            parcel_no=local[-4:],
            subparcel=None,
            parid_raw=local,
        )
    b.party(
        "01-01-0001",
        "fx-a-owner-p1",
        "TESTPERSON ALPHA Q",
        "person",
        last_name="TESTPERSON",
        first_name="ALPHA",
        middle="Q",
    )
    b.party(
        "01-01-0001",
        "fx-b-owner-p1",
        "BRAVO TESTHOLDINGS LLC",
        "org",
        org_name_norm="BRAVO TESTHOLDINGS",
        org_form="LLC",
    )
    b.party(
        "01-01-0002",
        "fx-a-owner-p2",
        "TESTPERSON ALPHA Q",
        "person",
        last_name="TESTPERSON",
        first_name="ALPHA",
        middle="Q",
    )
    b.fact(
        "ownership_period",
        "01-01-0001",
        "transfer",
        parcel_uid="99001-01-01-0001",
        party_id="fx-a-owner-p1",
        owner_seq=1,
        pct_owned="100",
        deed_book="100",
        deed_page="1",
        sale_price="150000.00",
        valid_from="2010-03-01",
        valid_to="2021-06-15",
    )
    b.fact(
        "ownership_period",
        "01-01-0001",
        "transfer",
        parcel_uid="99001-01-01-0001",
        party_id="fx-b-owner-p1",
        owner_seq=1,
        pct_owned="100",
        deed_book="210",
        deed_page="5",
        sale_price="10.00",
        valid_from="2021-06-15",
        valid_to=None,
    )
    b.fact(
        "ownership_period",
        "01-01-0002",
        "transfer",
        parcel_uid="99001-01-01-0002",
        party_id="fx-a-owner-p2",
        owner_seq=1,
        pct_owned="100",
        deed_book="120",
        deed_page="44",
        sale_price="90000.00",
        valid_from="2012-09-09",
        valid_to=None,
    )
    b.fact(
        "parcel_assessment",
        "01-01-0001",
        "assessment",
        parcel_uid="99001-01-01-0001",
        tax_year=2020,
        appraised_total="150000.00",
        valid_from="2020-07-01",
    )
    b.fact(
        "parcel_assessment",
        "01-01-0001",
        "assessment",
        parcel_uid="99001-01-01-0001",
        tax_year=2025,
        appraised_land="50000.00",
        appraised_bldg="150000.00",
        appraised_total="200000.00",
        valid_from="2025-07-01",
    )
    b.fact(
        "parcel_assessment",
        "01-01-0002",
        "assessment",
        parcel_uid="99001-01-01-0002",
        tax_year=2025,
        appraised_total="95000.00",
        valid_from="2025-07-01",
    )
    return b


def assessor_correction() -> Batch:
    """A later re-fetch where the county corrected the 2025 value for parcel 1."""
    b = Batch("f-assessor-2026-03", "fixture.assessor", "2026-03-01T12:00:00+00:00")
    b.fact(
        "parcel_assessment",
        "01-01-0001",
        "assessment",
        parcel_uid="99001-01-01-0001",
        tax_year=2025,
        appraised_land="50000.00",
        appraised_bldg="160000.00",
        appraised_total="210000.00",
        valid_from="2025-07-01",
    )
    return b


def recorder() -> Batch:
    b = Batch("f-recorder-2026-01", "fixture.recorder", "2026-01-15T12:00:00+00:00")

    def inst(num: str, doc_type: str, raw: str, recorded_on: str, seq: int, **kw: Any) -> str:
        uid = f"{J}:{num}"
        b.fact(
            "instrument",
            num,
            "instrument",
            instrument_uid=uid,
            instrument_number=num,
            doc_type_raw=raw,
            doc_type=doc_type,
            recorded_on=recorded_on,
            recorded_seq=seq,
            **kw,
        )
        return uid

    def party(num: str, uid: str, pid: str, raw: str, kind: str, role: str, seq: int) -> None:
        b.party(num, pid, raw, kind)
        b.fact(
            "instrument_party",
            num,
            "instrument_party",
            instrument_uid=uid,
            party_id=pid,
            role=role,
            seq=seq,
        )

    def on_parcel(num: str, uid: str, parcel: str) -> None:
        b.fact(
            "instrument_parcel",
            num,
            "instrument_parcel",
            instrument_uid=uid,
            parcel_uid=parcel,
            method="manual",
            evidence={"fixture": True},
        )

    def ref(num: str, frm: str, to: str, ref_type: str, scope: str | None = None) -> None:
        b.fact(
            "instrument_ref",
            num,
            "instrument_ref",
            from_uid=frm,
            to_uid=to,
            ref_type=ref_type,
            scope_parcel_uid=scope,
            method="index_xref",
        )

    p1, p2 = "99001-01-01-0001", "99001-01-01-0002"
    d1 = inst(
        "2010-000101",
        "DEED",
        "DEED",
        "2010-03-01",
        1,
        book="100",
        page="1",
        consideration="150000.00",
        amount_source="manual",
    )
    party("2010-000101", d1, "fx-r-a-1", "TESTPERSON ALPHA Q", "person", "grantee", 1)
    on_parcel("2010-000101", d1, p1)

    t1 = inst(
        "2010-000102",
        "DEED_OF_TRUST",
        "DEED OF TRUST",
        "2010-03-01",
        2,
        principal_amount="120000.00",
        amount_source="manual",
    )
    party("2010-000102", t1, "fx-r-a-2", "TESTPERSON ALPHA Q", "person", "borrower", 1)
    party("2010-000102", t1, "fx-r-c-1", "CHARLIE TESTBANK NA", "org", "lender", 1)
    on_parcel("2010-000102", t1, p1)

    t3 = inst(
        "2013-000300",
        "DEED_OF_TRUST",
        "DEED OF TRUST",
        "2013-04-01",
        1,
        principal_amount="50000.00",
        amount_source="manual",
    )
    party("2013-000300", t3, "fx-r-a-3", "TESTPERSON ALPHA Q", "person", "borrower", 1)
    party("2013-000300", t3, "fx-r-c-2", "CHARLIE TESTBANK NA", "org", "lender", 1)
    on_parcel("2013-000300", t3, p1)
    on_parcel("2013-000300", t3, p2)

    r1 = inst("2015-000501", "RELEASE", "RELEASE", "2015-05-05", 1)
    ref("2015-000501", r1, t1, "releases")

    t2 = inst(
        "2015-000502",
        "DEED_OF_TRUST",
        "DEED OF TRUST",
        "2015-05-05",
        2,
        principal_amount="100000.00",
        amount_source="manual",
    )
    party("2015-000502", t2, "fx-r-a-4", "TESTPERSON ALPHA Q", "person", "borrower", 1)
    party("2015-000502", t2, "fx-r-d-1", "DELTA TESTCREDIT UNION", "org", "lender", 1)
    on_parcel("2015-000502", t2, p1)

    pr = inst("2018-000808", "PARTIAL_RELEASE", "PARTIAL RELEASE", "2018-08-08", 1)
    ref("2018-000808", pr, t3, "partial_release", scope=p1)

    jl = inst("2019-000120", "JUDGMENT_LIEN", "JUDGMENT", "2019-01-20", 1)
    party("2019-000120", jl, "fx-r-a-5", "TESTPERSON ALPHA Q", "person", "debtor", 1)
    party("2019-000120", jl, "fx-r-e-1", "ECHO TESTSUPPLY INC", "org", "creditor", 1)

    ml = inst(
        "2020-000202",
        "MECHANICS_LIEN",
        "MECHANICS LIEN",
        "2020-02-02",
        1,
        principal_amount="12000.00",
        amount_source="manual",
    )
    party("2020-000202", ml, "fx-r-f-1", "FOXTROT TESTBUILDERS", "org", "creditor", 1)
    on_parcel("2020-000202", ml, p1)

    d2 = inst(
        "2021-000615",
        "DEED",
        "DEED",
        "2021-06-15",
        1,
        book="210",
        page="5",
        consideration="10.00",
        amount_source="manual",
    )
    party("2021-000615", d2, "fx-r-a-6", "TESTPERSON ALPHA Q", "person", "grantor", 1)
    party("2021-000615", d2, "fx-r-b-1", "BRAVO TESTHOLDINGS LLC", "org", "grantee", 1)
    on_parcel("2021-000615", d2, p1)

    lp = inst("2022-000110", "LIS_PENDENS", "LIS PENDENS", "2022-01-10", 1)
    party("2022-000110", lp, "fx-r-g-1", "GOLF TESTPLAINTIFF", "org", "creditor", 1)
    on_parcel("2022-000110", lp, p1)
    return b


def court() -> Batch:
    b = Batch("f-court-2026-01", "fixture.court", "2026-01-20T12:00:00+00:00")
    case_uid = "fixture.circuit:99-C-123"
    b.fact(
        "court_case",
        "99-C-123",
        "case",
        case_uid=case_uid,
        court_id="fixture.circuit",
        case_number_raw="99-C-123",
        case_number_norm="99-C-123",
        case_type="civil",
        filed_on="2018-06-01",
        status="closed",
        closed_on="2019-01-10",
    )
    b.party("99-C-123", "fx-c-e-1", "ECHO TESTSUPPLY INC", "org")
    b.party(
        "99-C-123",
        "fx-c-a-1",
        "TESTPERSON ALPHA Q",
        "person",
        last_name="TESTPERSON",
        first_name="ALPHA",
        middle="Q",
    )
    b.fact(
        "case_party",
        "99-C-123",
        "case_party",
        case_uid=case_uid,
        party_id="fx-c-e-1",
        role="plaintiff",
    )
    b.fact(
        "case_party",
        "99-C-123",
        "case_party",
        case_uid=case_uid,
        party_id="fx-c-a-1",
        role="defendant",
    )
    b.fact(
        "judgment",
        "99-C-123",
        "judgment",
        judgment_uid=f"{case_uid}#1",
        case_uid=case_uid,
        entered_on="2019-01-10",
        principal="85000.00",
        costs="450.00",
        judgment_type="money",
        lien_instrument_uid=f"{J}:2019-000120",
    )
    b.fact(
        "judgment_event",
        "99-C-123",
        "judgment_event",
        judgment_uid=f"{case_uid}#1",
        event="docketed",
        event_date="2019-01-20",
    )
    return b


def main(out: Path = OUT) -> None:
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "00_sources.jsonl": source_rows(),
        "10_assessor.jsonl": assessor_initial().lines,
        "20_recorder.jsonl": recorder().lines,
        "30_court.jsonl": court().lines,
        "40_assessor_correction.jsonl": assessor_correction().lines,
    }
    for name, lines in files.items():
        text = "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines)
        (out / name).write_text(text, encoding="utf-8")
    manifest = {
        "batches": [
            {
                "ingested_at": "2026-02-01T00:00:00+00:00",
                "files": [
                    "00_sources.jsonl",
                    "10_assessor.jsonl",
                    "20_recorder.jsonl",
                    "30_court.jsonl",
                ],
            },
            {"ingested_at": "2026-03-02T00:00:00+00:00", "files": ["40_assessor_correction.jsonl"]},
        ]
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
