"""Hillsborough Official Records daily index: parsing, mapping, exclusions. Offline."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.fl.hillsborough_or import (
    CASE_NO,
    D_FIELDS,
    HillsboroughOfficialRecords,
    daily_files,
    parse_lines,
)
from equity.adapters.http import Response
from equity.adapters.rows import canonical_json

FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "fl.hillsborough.or"
AT = datetime(2026, 11, 16, tzinfo=UTC)


def _d(inst: str, code: str, desc: str = "X", legal: str = "", consideration: str = "",
       action: str = "DDA", day: str = "11/04/2026") -> str:  # fmt: skip
    return f"{action}|29|{inst}|{code}|{desc}|{legal}|||||1|{day}|07:36|{consideration}|"


def _p(inst: str, seq: int, direction: str, name: str) -> str:
    return f"DPA|29|{inst}|{seq}|{direction}|{name}|"


def _norm(d: list[str], p: list[str]) -> list[tuple[str, dict[str, Any]]]:
    body = {"d_file": "D", "p_file": "P", "d": "\n".join(d) + "\nEOF|\n", "p": "\n".join(p)}
    f = Fetched("fl.hillsborough.or", "https://x.test/D", AT, 200, canonical_json(body), "")
    return [(r.table, dict(r.row)) for r in HillsboroughOfficialRecords().normalize(f)]


def test_parse_lines_and_listing() -> None:
    rows = parse_lines(_d("1", "JUD") + "\r\nEOF|\n", D_FIELDS)
    assert len(rows) == 1 and rows[0]["code"] == "JUD" and rows[0]["date"] == "11/04/2026"
    listing = "D2026090401id.29 P2026090401id.29 D2026110401id.29 D2026090401id.29 xD20"
    assert daily_files(listing) == [("20260904", "01"), ("20261104", "01")]
    assert CASE_NO.match("26-CA-006969") and CASE_NO.match("2025-CC-1")
    assert not CASE_NO.match("L 88 B A BAY CREST PARK")


def test_fixture() -> None:
    path = next(FIX.resolve().glob("*.json"))
    f = Fetched("fl.hillsborough.or", path.as_uri(), AT, 200, path.read_bytes(), "")
    rows = list(HillsboroughOfficialRecords().normalize(f))
    t = Counter(r.table for r in rows)
    assert t["instrument"] > 0 and t["party"] == t["instrument_party"]
    types = Counter(r.row["doc_type"] for r in rows if r.table == "instrument")
    assert types["JUDGMENT_LIEN"] > 0
    raw = {r.row["doc_type_raw"] for r in rows if r.table == "instrument"}
    assert not raw & {"DRCP", "DRJUD", "DC"}  # family and vital records are never loaded


def test_judgment_roles_seq_and_dedup() -> None:
    rows = _norm([_d("2026430401", "JUD", legal="26-CC-000123")],
                 [_p("2026430401", 2, "TO", "SMITH JANE"), _p("2026430401", 1, "TO", "SMITH JOE"),
                  _p("2026430401", 1, "FRM", "ACME FUNDING LLC"),
                  _p("2026430401", 3, "TO", "SMITH  JOE")])  # fmt: skip
    inst = next(r for t, r in rows if t == "instrument")
    assert inst["doc_type"] == "JUDGMENT_LIEN" and inst["recorded_seq"] == 2026430401
    assert inst["legal_desc_raw"] == "26-CC-000123" and inst["consideration"] is None
    ip = sorted((r["role"], r["seq"]) for t, r in rows if t == "instrument_party")
    assert ip == [("creditor", 1), ("debtor", 1), ("debtor", 2)]
    names = [r["raw_name"] for t, r in rows if t == "party"]
    assert names == ["ACME FUNDING LLC", "SMITH JOE", "SMITH JANE"]  # clerk sequence order


def test_deed_consideration_and_exclusions() -> None:
    rows = _norm([_d("10", "D", consideration="185000.0000"),
                  _d("11", "", desc="MARRIAGE RECORD"), _d("12", "DC"),
                  _d("13", "MTG", consideration="5")],
                 [_p("11", 1, "FRM", "A B"), _p("12", 1, "FRM", "C D")])  # fmt: skip
    inst = {r["instrument_number"]: r for t, r in rows if t == "instrument"}
    assert set(inst) == {"10", "13"}
    assert inst["10"]["consideration"] == Decimal("185000.00")
    assert inst["13"]["consideration"] is None  # amounts are read only for deeds
    assert not [r for t, r in rows if t == "party"]
    assert [r["record_key"] for t, r in rows if t == "source_record"] == ["10", "13"]


def test_bad_rows_become_issues() -> None:
    rows = _norm([_d("20", "JUD", action="DDD"), _d("21", "JUD", day="13/45/2026"),
                  _d("22", "JUD", day="01/02/2027"), _d("23", "ZZZ")], [])  # fmt: skip
    codes = [r["issue_code"] for t, r in rows if t == "data_issue"]
    assert codes == ["non_add_action", "missing_doc_type_or_recorded_date",
                     "recorded_after_retrieval", "unknown_doc_code"]  # fmt: skip
    assert [r["doc_type"] for t, r in rows if t == "instrument"] == ["OTHER"]


class FakeClerk:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.urls: list[str] = []

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        self.urls.append(url)
        name = url.rsplit("/", 1)[-1]
        if name in self.files:
            return Response(url, 200, self.files[name], "text/plain", AT)
        return Response(url, 404, b"", "text/html", AT)


def test_fetch_limit_partitions_and_health() -> None:
    d = "\n".join([_d("1", "JUD"), _d("2", "D"), _d("3", "MTG")]).encode()
    p = "\n".join([_p("1", 1, "FRM", "A"), _p("3", 1, "TO", "B")]).encode()
    files = {"": b"<a>D2026110401id.29</a> <a>P2026110401id.29</a>",
             "D2026110401id.29": d, "P2026110401id.29": p}  # fmt: skip
    a = HillsboroughOfficialRecords(FakeClerk(files))  # type: ignore[arg-type]
    assert list(a.partitions()) == [{"day": "20261104", "n": "01"}]
    body = json.loads(a.fetch(FetchRequest({"day": "20261104", "n": "01", "limit": "2"})).content)
    assert body["d"].count("\n") == 2 and "|3|" not in body["p"] and "|1|" in body["p"]
    with pytest.raises(ValueError, match="bad day"):
        a.fetch(FetchRequest({"day": "2026-11-04"}))
    with pytest.raises(RuntimeError, match="HTTP 404"):
        a.fetch(FetchRequest({"day": "20261105"}))
    assert a.health().ok
    assert not HillsboroughOfficialRecords(FakeClerk({"": b"none"})).health().ok  # type: ignore[arg-type]
    assert not HillsboroughOfficialRecords(FakeClerk({})).health().ok  # type: ignore[arg-type]


def test_scrub_keeps_case_numbers_only() -> None:
    body = canonical_json({"d_file": "D", "p_file": "P",
                           "d": _d("1", "FIN", legal="123 MAIN ST TAMPA") + "\n"
                           + _d("2", "ORD", legal="26-CA-006969"),
                           "p": _p("1", 1, "FRM", "REAL PERSON")})  # fmt: skip
    out = json.loads(HillsboroughOfficialRecords.scrub_fixture(body))
    assert "MAIN ST" not in out["d"] and "26-CA-006969" in out["d"]
    assert "REAL PERSON" not in out["p"] and "TESTOWNER" in out["p"]
