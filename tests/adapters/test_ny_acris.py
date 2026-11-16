"""NYC ACRIS: lot keys, partition ranges, document normalization, edge cases. Offline."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import Response
from equity.adapters.ny.acris import (
    AcrisPersonalProperty,
    AcrisRealProperty,
    bbl,
    load_config,
    month_ranges,
    parcel_uid_for,
    prefix_ranges,
)
from equity.adapters.rows import canonical_json

FIX = Path(__file__).parents[1] / "fixtures" / "adapters"
AT = datetime(2025, 12, 31, tzinfo=UTC)


def _fixture(source_id: str) -> Fetched:
    path = next((FIX / source_id).resolve().glob("*.json"))
    return Fetched(source_id, path.as_uri(), AT, 200, path.read_bytes(), "application/json")


def _doc(doc_id: str = "2019010100001001", **master: Any) -> dict[str, Any]:
    return {"document_id": doc_id, "doc_type": "MTGE",
            "recorded_datetime": "2019-01-04T00:00:00.000",
            "document_date": "2018-12-28T00:00:00.000", "document_amt": "250000.00",
            "crfn": "2019000000001", **master}  # fmt: skip


def _fetched(master: list[dict[str, Any]], legals: list[dict[str, Any]] | None = None,
             parties: list[dict[str, Any]] | None = None,
             references: list[dict[str, Any]] | None = None) -> Fetched:  # fmt: skip
    body = {"portal": "x", "where": "w", "master": master, "legals": legals or [],
            "parties": parties or [], "references": references or []}  # fmt: skip
    return Fetched("ny.nyc.acris.real", "https://x.test/r", AT, 200, canonical_json(body), "")


def _rows(fetched: Fetched) -> list[tuple[str, dict[str, Any]]]:
    return [(r.table, dict(r.row)) for r in AcrisRealProperty().normalize(fetched)]


def _lot(doc_id: str, boro: str, block: str, lot: str) -> dict[str, Any]:
    return {"document_id": doc_id, "borough": boro, "block": block, "lot": lot}


def test_bbl_and_parcel_uid_follow_the_state_layer() -> None:
    assert bbl({"borough": "3", "block": "429", "lot": "65"}) == "3004290065"
    assert bbl({"borough": "6", "block": "1", "lot": "1"}) is None
    assert bbl({"borough": "1", "block": None, "lot": "1"}) is None
    assert bbl({"borough": "1", "block": "100000", "lot": "1"}) is None
    cfg = load_config()
    assert parcel_uid_for("3004290065", cfg) == "36047-6101003004290065"
    assert parcel_uid_for("1000167509", cfg) == "36061-6201001000167509"


def test_partition_ranges_cover_months_and_legacy_prefixes() -> None:
    months = list(month_ranges(date(2002, 12, 1), date(2003, 2, 9)))
    assert months == [("200212", "200301"), ("200301", "200302"), ("200302", "200303")]
    ft = list(prefix_ranges("FT_1"))
    assert len(ft) == 100 and ft[0] == ("FT_100", "FT_101") and ft[-1] == ("FT_199", "FT_19:")
    assert "FT_1990009008899" < "FT_19:" and "FT_2" > "FT_19:"  # ':' sorts after every digit
    assert AcrisRealProperty.where({"lo": "201901", "hi": "201902"}) == (
        "document_id >= '201901' AND document_id < '201902'"
    )
    assert AcrisRealProperty.where({"ids": "a,b'"}) == "document_id in ('a','b''')"


def test_real_property_fixture() -> None:
    rows = list(AcrisRealProperty().normalize(_fixture("ny.nyc.acris.real")))
    tables = Counter(r.table for r in rows)
    assert tables["instrument"] == tables["source_record"] == 25
    assert tables["instrument_party"] == tables["party"] > 0
    deed = next(r.row for r in rows if r.table == "instrument" and r.row["doc_type"] == "DEED")
    assert deed["consideration"] is not None and deed["principal_amount"] is None
    mtge = next(r.row for r in rows if r.table == "instrument" and r.row["doc_type"] == "MORTGAGE")
    assert mtge["principal_amount"] is not None and mtge["consideration"] is None
    roles = {r.row["role"] for r in rows if r.table == "instrument_party"}
    assert {"grantor", "grantee", "borrower", "lender"} <= roles
    lots = [r.row["parcel_uid"] for r in rows if r.table == "instrument_parcel"]
    assert lots and all(uid.startswith("360") for uid in lots)
    refs = [r.row for r in rows if r.table == "instrument_ref"]
    assert refs and all(r["method"] == "index_xref" for r in refs)
    unresolved = [r.row for r in rows if r.table == "data_issue"
                  and r.row["issue_code"] == "unresolved_reference"]  # fmt: skip
    assert unresolved and all(i["detail"]["crfns"] for i in unresolved)


def test_personal_property_fixture_has_debtors_and_creditors() -> None:
    rows = list(AcrisPersonalProperty().normalize(_fixture("ny.nyc.acris.personal")))
    roles = Counter(r.row["role"] for r in rows if r.table == "instrument_party")
    assert roles["debtor"] > 0 and roles["creditor"] > 0
    types = {r.row["doc_type"] for r in rows if r.table == "instrument"}
    assert "FIXTURE_FILING" in types and "RELEASE" in types


def test_dates_after_retrieval_are_issues_not_facts() -> None:
    late = _doc(recorded_datetime="2026-02-01T00:00:00.000")
    rows = _rows(_fetched([late]))
    assert [t for t, _ in rows] == ["source_record", "data_issue"]
    assert rows[1][1]["issue_code"] == "recorded_after_retrieval"
    odd = _doc(document_date="2109-01-01T00:00:00.000")
    rows = _rows(_fetched([odd]))
    inst = next(r for t, r in rows if t == "instrument")
    assert inst["executed_on"] is None
    assert any(r.get("issue_code") == "executed_after_retrieval" for _, r in rows)


def test_zero_amount_unknown_code_and_missing_date() -> None:
    rows = _rows(_fetched([_doc(document_amt="0.00", doc_type="ZZZZ")]))
    inst = next(r for t, r in rows if t == "instrument")
    assert inst["doc_type"] == "OTHER" and inst["doc_type_raw"] == "ZZZZ"
    assert inst["principal_amount"] is None and inst["amount_source"] is None
    assert any(r.get("issue_code") == "unknown_doc_code" for _, r in rows)
    rows = _rows(_fetched([_doc(recorded_datetime=None)]))
    assert [r["issue_code"] for t, r in rows if t == "data_issue"] == [
        "missing_doc_type_or_recorded_date"
    ]


def test_parties_are_ordered_by_content_and_deduplicated() -> None:
    d = "2019010100001001"
    p = [{"document_id": d, "party_type": "1", "name": "ZED ZED"},
         {"document_id": d, "party_type": "1", "name": "ABLE ABLE"},
         {"document_id": d, "party_type": "1", "name": "ABLE ABLE"},
         {"document_id": d, "party_type": "2", "name": "BANK NA", "zip": "10001-1234"},
         {"document_id": d, "party_type": "9", "name": "STRAY"}]  # fmt: skip
    rows = _rows(_fetched([_doc(d)], parties=p))
    ip = [(r["role"], r["seq"]) for t, r in rows if t == "instrument_party"]
    assert sorted(ip) == [("borrower", 1), ("borrower", 2), ("lender", 1), ("other", 1)]
    names = {r["party_id"]: r["raw_name"] for t, r in rows if t == "party"}
    first = next(r for t, r in rows if t == "instrument_party" and r["seq"] == 1
                 and r["role"] == "borrower")  # fmt: skip
    assert names[first["party_id"]] == "ABLE ABLE"
    zips = {r["zip5"] for t, r in rows if t == "address"}
    assert zips == {"10001"}
    # Reversed server order gives the same rows.
    assert rows == _rows(_fetched([_doc(d)], parties=list(reversed(p))))


def test_partial_release_needs_exactly_one_lot() -> None:
    d, m = "2019010100001002", "2007021501183002"
    psat = _doc(d, doc_type="PSAT")
    ref = [{"document_id": d, "reference_by_doc_id": m}]
    one = _rows(_fetched([psat], legals=[_lot(d, "3", "429", "65")], references=ref))
    r = next(r for t, r in one if t == "instrument_ref")
    assert r["ref_type"] == "partial_release" and r["scope_parcel_uid"] == "36047-6101003004290065"
    two = _rows(_fetched([psat], legals=[_lot(d, "3", "429", "65"), _lot(d, "3", "429", "66")],
                         references=ref))  # fmt: skip
    assert not [r for t, r in two if t == "instrument_ref"]
    assert any(r.get("issue_code") == "partial_release_scope_ambiguous" for _, r in two)


def test_satisfaction_links_and_reel_references() -> None:
    d = "2019010100001003"
    refs = [{"document_id": d, "reference_by_doc_id": "2007021501183002"},
            {"document_id": d, "reference_by_doc_id": d},  # self-reference dropped
            {"document_id": d, "reference_by_reel_year": "1995", "reference_by_reel_borough": "3",
             "reference_by_reel_nbr": "3501", "reference_by_reel_page": "77"}]  # fmt: skip
    rows = _rows(_fetched([_doc(d, doc_type="SAT")], references=refs))
    links = [r for t, r in rows if t == "instrument_ref"]
    assert [(r["to_uid"], r["ref_type"]) for r in links] == [
        ("ny.nyc.acris:2007021501183002", "releases")
    ]
    issue = next(r for t, r in rows if t == "data_issue")
    assert issue["detail"]["reels"] == [{"year": 1995, "borough": 3, "reel": 3501, "page": 77}]
    # A deed has no reference type: its references are ignored.
    rows = _rows(_fetched([_doc(d, doc_type="DEED")], references=refs))
    assert not [r for t, r in rows if t in ("instrument_ref", "data_issue")]


def test_unparsable_lots_are_reported_and_amounts_quantized() -> None:
    d = "2019010100001004"
    rows = _rows(_fetched([_doc(d, document_amt="1234.5")],
                          legals=[_lot(d, "9", "1", "1"), _lot(d, "1", "1", "1")]))  # fmt: skip
    assert [r["parcel_uid"] for t, r in rows if t == "instrument_parcel"] == [
        "36061-6201001000010001"
    ]
    assert any(r.get("issue_code") == "unparsable_lot" for _, r in rows)
    inst = next(r for t, r in rows if t == "instrument")
    assert inst["principal_amount"] == Decimal("1234.50")


class FakeSocrata:
    """Serves canned rows per dataset id; records every query."""

    retries = 0
    backoff_s = 0.0

    def __init__(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self.data = data
        self.queries: list[tuple[str, dict[str, str]]] = []

    def sleep(self, s: float) -> None:
        pass

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        ds = url.rsplit("/", 1)[-1].removesuffix(".json")
        self.queries.append((ds, dict(params or {})))
        limit = int((params or {}).get("$limit", "50000"))
        offset = int((params or {}).get("$offset", "0"))
        rows = self.data.get(ds, [])[offset : offset + limit]
        return Response(url, 200, json.dumps(rows).encode(), "application/json", AT)


def test_fetch_reads_four_datasets_and_limit_pins_document_ids() -> None:
    fam = AcrisRealProperty.family
    client = FakeSocrata({fam.master: [_doc("A1"), _doc("A2")],
                          fam.parties: [{"document_id": "A1", "name": "X"}]})  # fmt: skip
    fetched = AcrisRealProperty(client).fetch(FetchRequest({"lo": "2019", "hi": "2020"}))  # type: ignore[arg-type]
    assert [q[0] for q in client.queries] == [fam.master, fam.legals, fam.parties, fam.references]
    assert {q[1]["$where"] for q in client.queries} == {
        "document_id >= '2019' AND document_id < '2020'"
    }
    body = json.loads(fetched.content)
    assert len(body["master"]) == 2 and len(body["parties"]) == 1
    client = FakeSocrata({fam.master: [_doc("A1"), _doc("A2")]})
    AcrisRealProperty(client).fetch(FetchRequest({"lo": "2019", "hi": "2020", "limit": "1"}))  # type: ignore[arg-type]
    assert client.queries[0][1]["$limit"] == "1"
    assert client.queries[1][1]["$where"] == "document_id in ('A1')"


def test_fetch_by_doc_codes_reads_related_rows_in_id_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import equity.adapters.ny.acris as acris

    monkeypatch.setattr(acris, "ID_CHUNK", 2)
    fam = AcrisRealProperty.family
    client = FakeSocrata({fam.master: [_doc("A3"), _doc("A1"), _doc("A2")],
                          fam.parties: [{"document_id": "A1", "name": "X"}]})  # fmt: skip
    params = {"lo": "2019", "hi": "2020", "codes": "JUDG|DEED, LE"}
    body = json.loads(AcrisRealProperty(client).fetch(FetchRequest(params)).content)  # type: ignore[arg-type]
    master_where = client.queries[0][1]["$where"]
    assert master_where.endswith("AND doc_type in ('JUDG','DEED, LE')")
    related = [q[1]["$where"] for q in client.queries[1:]]
    assert related == ["document_id in ('A1','A2')", "document_id in ('A3')"] * 3
    # The fake ignores $where, so each chunk returns the party row again: two copies.
    assert len(body["parties"]) == 2
    empty = FakeSocrata({})
    AcrisRealProperty(empty).fetch(FetchRequest(params))  # type: ignore[arg-type]
    assert len(empty.queries) == 1  # no documents: nothing else is read


def test_partitions_and_health() -> None:
    parts = list(AcrisRealProperty().partitions())
    assert parts[0] == {"lo": "200212", "hi": "200301"}
    assert {"lo": "FT_100", "hi": "FT_101"} in parts and {"lo": "BK_899", "hi": "BK_89:"} in parts
    client = FakeSocrata({AcrisRealProperty.family.master: [_doc("2025010100001001")]})
    assert AcrisRealProperty(client).health().ok  # type: ignore[arg-type]
    assert not AcrisRealProperty(FakeSocrata({})).health().ok  # type: ignore[arg-type]
