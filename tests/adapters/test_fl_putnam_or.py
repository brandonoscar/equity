"""Putnam County (FL) Official Records Index downloads. Offline."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.fl.putnam_or import (
    PutnamOfficialRecords,
    amount,
    file_date,
    load_config,
    parse_lines,
    zip_text,
)
from equity.adapters.http import PoliteClient
from equity.adapters.registry import by_source_id
from equity.adapters.rows import canonical_json
from equity.schema.enums import DOC_TYPES

AT = datetime(2026, 11, 23, tzinfo=UTC)
FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "fl.putnam.or"
TEXT = "\n".join([
    "1848|1746|01-02-2026|LVNV FUNDING LLC||202654000006|CCJ|$1,622.55 ET AL",
    "1848|1746|01-02-2026||DOE ANN|202654000006|CCJ|$1,622.55 ET AL",
    "1848|1693|01-02-2026|SELLER SAM||202654000001|D|LT 29 BLK 11 ILE",
    "1848|1693|01-02-2026||BUYER BO|202654000001|D|LT 29 BLK 11 ILE",
    "1848|1693|01-02-2026||BUYER BO|202654000001|D|LT 30 BLK 11 ILE",
    "1849|1|01-05-2026|ROE JOHN||202654000100|JUD|25-885-FD-54",
    "1849|2|01-05-2026|FLORIDA STATE OF||202654000101|CJD|2023-000870-CF",
    "1849|3|01-05-2026|X||202654000102|ZZZ|WHAT",
    "1849|4|12-31-2026|X||202654000103|D|FUTURE",
    "1849|5|bad|X||202654000104|D|NO DATE",
    "1849|6|01-06-2026|ACME LIEN CO||202654000105|LN|SEE INSTRUMENT",
    "1849|7|01-06-2025|OLD||202554000105|D|LT 1",
    "short|row",
])  # fmt: skip


def _norm(text: str = TEXT) -> list[tuple[str, dict[str, Any]]]:
    body = canonical_json({"file": "year", "year": None, "rows": parse_lines(text)})
    f = Fetched(PutnamOfficialRecords.source_id, "https://x.test/x", AT, 200, body, "")
    return [(r.table, dict(r.row)) for r in PutnamOfficialRecords().normalize(f)]


def _of(out: list[tuple[str, dict[str, Any]]], table: str) -> list[dict[str, Any]]:
    return [r for t, r in out if t == table]


def test_helpers() -> None:
    assert file_date("10-03-2007") == date(2007, 10, 3)
    assert file_date("bad") is None and file_date("13-40-2007") is None
    assert amount("$1,622.55 ET AL") == Decimal("1622.55") and amount("$0.00") is None
    assert amount("SEE INSTRUMENT") is None and amount("$12,583") == Decimal("12583.00")
    assert len(parse_lines(TEXT)) == 12 and len(parse_lines(TEXT, 2025)) == 1
    assert "to" not in parse_lines(TEXT)[0]
    cfg = load_config()
    assert {c.doc_type for c in cfg.codes.values()} <= set(DOC_TYPES)
    assert not set(cfg.codes) & cfg.exclude_codes


def test_normalize() -> None:
    out = _norm()
    inst = {i["instrument_number"]: i for i in _of(out, "instrument")}
    assert set(inst) == {"202654000006", "202654000001", "202654000102", "202654000105",
                         "202554000105"}  # fmt: skip
    j = inst["202654000006"]
    assert j["doc_type"] == "JUDGMENT_LIEN" and j["principal_amount"] == Decimal("1622.55")
    assert j["amount_source"] == "index" and j["recorded_on"] == date(2026, 1, 2)
    assert (
        j["book"] == "1848"
        and j["page"] == "1746"
        and j["instrument_uid"].startswith("fl.putnam.or:")
    )
    d = inst["202654000001"]
    assert d["principal_amount"] is None and d["legal_desc_raw"] == (
        "LT 29 BLK 11 ILE | LT 30 BLK 11 ILE"
    )
    assert inst["202654000105"]["principal_amount"] is None  # a lien without an amount
    assert inst["202654000102"]["doc_type"] == "OTHER"
    names = {p["party_id"]: p["raw_name"] for p in _of(out, "party")}
    roles = sorted((names[p["party_id"]], p["role"]) for p in _of(out, "instrument_party")
                   if p["instrument_uid"].endswith("4000006"))  # fmt: skip
    assert roles == [("DOE ANN", "debtor"), ("LVNV FUNDING LLC", "creditor")]
    assert "ROE JOHN" not in names.values() and "FLORIDA STATE OF" not in names.values()
    issues = sorted(i["issue_code"] for i in _of(out, "data_issue"))
    assert issues == ["missing_doc_type_or_recorded_date", "recorded_after_retrieval",
                      "unknown_doc_code"]  # fmt: skip


def _zip(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("orihelp.txt", "help")
        z.writestr("Rec_20260101_20261122.txt", text.encode("latin-1"))
    return buf.getvalue()


class FakeTransport:
    def __init__(self, files: Mapping[str, bytes]) -> None:
        self.files = files
        self.calls: list[str] = []

    def __call__(
        self, url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes, str]:
        self.calls.append(url)
        name = url.rsplit("/", 1)[-1]
        if name in self.files:
            return 200, self.files[name], "application/zip"
        return 404, b"", "text/html"


def _adapter(files: Mapping[str, bytes]) -> tuple[PutnamOfficialRecords, FakeTransport]:
    t = FakeTransport(files)
    client = PoliteClient(min_interval_s=0, retries=0, transport=t, sleep=lambda _s: None,
                          now=lambda: AT)  # fmt: skip
    return PutnamOfficialRecords(client=client), t


def test_fetch_partitions_health() -> None:
    a, t = _adapter({"orimaster.zip": _zip(TEXT), "oriyear.zip": _zip(TEXT),
                     "oriweekly.zip": _zip(TEXT)})  # fmt: skip
    parts = list(a.partitions())
    assert parts[0] == {"file": "history", "year": "2006"}
    assert parts[-2] == {"file": "history", "year": "2025"} and parts[-1] == {"file": "year"}
    f = a.fetch(FetchRequest({"file": "history", "year": "2025"}))
    assert [r["instrument"] for r in json.loads(f.content)["rows"]] == ["202554000105"]
    a.fetch(FetchRequest({"file": "history", "year": "2026"}))
    assert sum(u.endswith("orimaster.zip") for u in t.calls) == 1  # downloaded once
    f = a.fetch(FetchRequest({"file": "year", "limit": "2"}))
    assert {r["instrument"] for r in json.loads(f.content)["rows"]} == {"202654000006",
                                                                        "202654000001"}  # fmt: skip
    with pytest.raises(ValueError, match="file must be"):
        a.fetch(FetchRequest({"file": "weekly"}))
    report = a.health()
    assert report.ok is False  # a bad date among the first rows
    good, _ = _adapter({"oriweekly.zip": _zip(TEXT.replace("|bad|", "|01-05-2026|"))})
    assert good.health().ok
    missing, _ = _adapter({})
    assert not missing.health().ok
    with pytest.raises(RuntimeError, match="HTTP 404"):
        missing.fetch(FetchRequest({"file": "year"}))
    empty = io.BytesIO()
    zipfile.ZipFile(empty, "w").close()
    with pytest.raises(RuntimeError, match="no Rec_"):
        zip_text(empty.getvalue())


def test_scrub_and_fixture() -> None:
    body = canonical_json({"file": "year", "year": None, "rows": parse_lines(TEXT)})
    data = json.loads(PutnamOfficialRecords.scrub_fixture(body))
    descs = {r["description"] for r in data["rows"]}
    assert "LT 29 BLK 11 ILE" not in descs and "$1,622.55 ET AL" in descs
    assert all(r.get("from", "TESTOWNER").startswith("TESTOWNER") for r in data["rows"])
    assert by_source_id("fl.putnam.or") is PutnamOfficialRecords
    paths = sorted(FIX.glob("*.json"))
    assert paths
    for path in paths:
        for r in json.loads(path.read_text())["rows"]:
            for col in ("from", "to"):
                assert not r.get(col) or r[col].startswith("TESTOWNER"), col
