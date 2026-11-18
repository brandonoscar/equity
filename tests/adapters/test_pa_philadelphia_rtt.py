"""Philadelphia RTT: owner-window SQL, document grouping, roles, edge cases. Offline."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import Response
from equity.adapters.pa.philadelphia_rtt import (
    PhiladelphiaRTT,
    split_names,
    window_sql,
)
from equity.adapters.rows import canonical_json

FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "pa.philadelphia.rtt"
AT = datetime(2026, 11, 16, tzinfo=UTC)


def _row(doc: int, cid: int, **kw: Any) -> dict[str, Any]:
    return {"cartodb_id": cid, "document_id": doc, "document_type": "MORTGAGE",
            "recording_date": "2014-01-27T10:00:00Z", "document_date": "2014-01-20T00:00:00Z",
            "grantors": "SMITH JOHN; SMITH MARY", "grantees": "FIRST BANK",
            "total_consideration": 0, "opa_account_num": "011000023", "record_id": f"r{cid}",
            "street_address": "1 MAIN ST", **kw}  # fmt: skip


def _norm(rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    f = Fetched("pa.philadelphia.rtt", "https://x.test", AT, 200,
                canonical_json({"sql": "s", "rows": rows}), "application/json")  # fmt: skip
    return [(r.table, dict(r.row)) for r in PhiladelphiaRTT().normalize(f)]


def test_window_sql_selects_documents_owned_by_the_window() -> None:
    sql = window_sql(100, 200)
    assert "cartodb_id >= 100 AND cartodb_id < 200" in sql
    assert "x.cartodb_id < 100" in sql  # documents that started earlier belong elsewhere
    assert sql.endswith("ORDER BY r.document_id, r.cartodb_id")
    assert "legal_remarks" not in sql
    assert window_sql(1, 2, limit=5).endswith(" LIMIT 5")


def test_split_names() -> None:
    assert split_names("SMITH  JOHN; SMITH MARY;;SMITH JOHN ") == ["SMITH JOHN", "SMITH MARY"]
    assert split_names(None) == [] and split_names("  ") == []


def test_fixture_normalizes_whole_documents() -> None:
    path = next(FIX.resolve().glob("*.json"))
    f = Fetched("pa.philadelphia.rtt", path.as_uri(), AT, 200, path.read_bytes(), "")
    rows = list(PhiladelphiaRTT().normalize(f))
    t = Counter(r.table for r in rows)
    docs = {r["document_id"] for r in json.loads(path.read_text())["rows"]}
    assert t["source_record"] == len(docs) and t["instrument"] <= len(docs)
    assert t["party"] == t["instrument_party"] > 0
    types = {r.row["doc_type"] for r in rows if r.table == "instrument"}
    assert {"DEED", "MORTGAGE", "RELEASE"} <= types


def test_multi_parcel_document_is_one_instrument() -> None:
    rows = _norm([_row(7, 11, opa_account_num="011000024"), _row(7, 10), _row(7, 12),
                  _row(7, 13, opa_account_num=None)])  # fmt: skip
    t = Counter(table for table, _ in rows)
    assert t["instrument"] == 1 and t["instrument_parcel"] == 2
    lots = [r["parcel_uid"] for table, r in rows if table == "instrument_parcel"]
    assert lots == ["42101-011000023", "42101-011000024"]
    dup = next(r for table, r in rows if table == "instrument_parcel"
               and r["parcel_uid"] == "42101-011000023")  # fmt: skip
    assert [e["record_id"] for e in dup["evidence"]["rows"]] == ["r10", "r12"]
    issue = next(r for table, r in rows if table == "data_issue")
    assert issue["issue_code"] == "no_parcel_id"
    assert issue["detail"]["rows"][0]["street_address"] == "1 MAIN ST"
    assert rows == _norm([_row(7, 13, opa_account_num=None), _row(7, 12), _row(7, 10),
                          _row(7, 11, opa_account_num="011000024")])  # fmt: skip


def test_roles_follow_document_type() -> None:
    sat = _norm([_row(8, 1, document_type="SATISFACTION", grantors="FIRST BANK",
                      grantees="SMITH JOHN")])  # fmt: skip
    roles = {r["role"] for t, r in sat if t == "instrument_party"}
    assert roles == {"lender", "borrower"}
    mtg = _norm([_row(9, 1)])
    ip = sorted((r["role"], r["seq"]) for t, r in mtg if t == "instrument_party")
    assert ip == [("borrower", 1), ("borrower", 2), ("lender", 1)]
    lp = _norm([_row(10, 1, document_type="DM - LIS PENDENS", grantors="A", grantees="COURT")])
    assert sorted((r["role"], r["seq"]) for t, r in lp if t == "instrument_party") == [
        ("other", 1),
        ("other", 2),
    ]


def test_consideration_only_on_deeds() -> None:
    deed = _norm([_row(1, 1, document_type="DEED SHERIFF", total_consideration=125000.5)])
    inst = next(r for t, r in deed if t == "instrument")
    assert inst["doc_type"] == "DEED" and inst["consideration"] == Decimal("125000.50")
    assert inst["amount_source"] == "index"
    mtg = next(r for t, r in _norm([_row(2, 1, total_consideration=99)]) if t == "instrument")
    assert mtg["consideration"] is None and mtg["principal_amount"] is None


def test_bad_dates_and_unknown_types() -> None:
    for bad in ({"recording_date": None}, {"recording_date": "1969-12-31T19:00:00Z"},
                {"document_type": None}):  # fmt: skip
        out = _norm([_row(3, 1, **bad)])
        assert [t for t, _ in out] == ["source_record", "data_issue"]
    late = _norm([_row(4, 1, recording_date="2027-01-01T00:00:00Z")])
    assert late[1][1]["issue_code"] == "recorded_after_retrieval"
    odd = _norm([_row(5, 1, document_type="MYSTERY", document_date="2099-01-01T00:00:00Z")])
    inst = next(r for t, r in odd if t == "instrument")
    assert inst["doc_type"] == "OTHER" and inst["executed_on"] is None
    codes = {r["issue_code"] for t, r in odd if t == "data_issue"}
    assert codes == {"unknown_doc_type", "executed_after_retrieval"}


class FakeCarto:
    retries = 1
    backoff_s = 1.0

    def __init__(self, responses: list[tuple[int, bytes]]) -> None:
        self.responses = responses
        self.sql: list[str] = []
        self.slept: list[float] = []

    def sleep(self, s: float) -> None:
        self.slept.append(s)

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        self.sql.append((params or {})["q"])
        status, body = self.responses[min(len(self.sql) - 1, len(self.responses) - 1)]
        return Response(url, status, body, "application/json", AT)


def test_fetch_retries_carto_timeouts() -> None:
    ok = json.dumps({"rows": [_row(1, 5)]}).encode()
    c = FakeCarto([(400, b'{"error": ["query_wait_timeout"]}'), (200, ok)])
    f = PhiladelphiaRTT(c).fetch(FetchRequest({"lo": "1", "hi": "11"}))  # type: ignore[arg-type]
    assert json.loads(f.content)["rows"][0]["cartodb_id"] == 5 and c.slept == [1.0]
    stuck = FakeCarto([(400, b'{"error": ["query_wait_timeout"]}')])
    with pytest.raises(RuntimeError, match="HTTP 400"):
        PhiladelphiaRTT(stuck).fetch(FetchRequest({"lo": "1", "hi": "11"}))  # type: ignore[arg-type]
    assert len(stuck.sql) == 4  # first try + retries + 2


def test_max_id_binary_search_and_partitions() -> None:
    top = 25_123

    class Probe(FakeCarto):
        def get(self, url: str, params: dict[str, str] | None = None) -> Response:
            q = (params or {})["q"]
            self.sql.append(q)
            if "rtt_summary WHERE cartodb_id >=" in q and "LIMIT 1" in q:
                n = int(q.split(">=")[1].split()[0])
                rows = [{"cartodb_id": n}] if n <= top else []
                return Response(url, 200, json.dumps({"rows": rows}).encode(), "", AT)
            return Response(url, 200, b'{"rows": []}', "", AT)

    a = PhiladelphiaRTT(Probe([]))  # type: ignore[arg-type]
    assert a.max_id() == top
    parts = list(a.partitions())
    assert parts[0] == {"lo": "1", "hi": "10001"} and parts[-1] == {"lo": "20001", "hi": "30001"}


def test_health() -> None:
    good = json.dumps(
        {
            "rows": [
                _row(
                    1,
                    1,
                    unit_num=None,
                    zip_code="19149",
                    matched_regmap=None,
                    reg_map_id=None,
                    property_count=1,
                    discrepancy=None,
                )
            ]
        }
    )
    assert PhiladelphiaRTT(FakeCarto([(200, good.encode())])).health().ok  # type: ignore[arg-type]
    assert not PhiladelphiaRTT(FakeCarto([(200, b'{"rows": []}')])).health().ok  # type: ignore[arg-type]
    assert not PhiladelphiaRTT(FakeCarto([(500, b"down")])).health().ok  # type: ignore[arg-type]
