"""Hernando County (FL) Official Records weekly index. Offline."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.fl.hernando_or import (
    HernandoOfficialRecords,
    OrCode,
    load_config,
    lookup,
    parse_rows,
    recorded_date,
    weekly_files,
)
from equity.adapters.http import PoliteClient
from equity.adapters.registry import by_source_id
from equity.adapters.rows import canonical_json
from equity.schema.enums import DOC_TYPES

AT = datetime(2026, 11, 23, tzinfo=UTC)
FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "fl.hernando.or"
CSV = (
    '"ACME BANK NA","DOE ANN","2026076273","4783","483","JUDGMENT","L Blk Un Sub S T R",'
    "11/06/26 10:45:15 AM\n"
    '"ACME BANK NA","DOE ANN","2026076273","4783","483","JUDGMENT","L Blk Un Sub S T R",'
    "11/06/26 10:45:15 AM\n"
    '"ACME BANK","DOE ANN","2026076273","4783","483","JUDGMENT",'
    '"L7 Blk125 Un9 SubROYAL HIGHLANDS S T R",11/06/26 10:45:15 AM\n'
    '"ROE JOHN","ROE JANE","2026076274","4783","484","JUDGMENTX","",11/06/26 10:46:00 AM\n'
    '"SELLER SAM","BUYER BO","2026076275","4783","485","DEED1","",11/06/26 10:47:00 AM\n'
    '"X","Y","2026076276","4783","486","NEW KIND","",11/06/26 10:48:00 AM\n'
    '"X","Y","2026076277","4783","487","DEED","",12/31/26 10:48:00 AM\n'
    '"X","Y","2026076278","4783","488","DEED","","not a date"\n'
    '"MARRIED","PERSON","2026076279","4783","489","MARRIAGE RECORD","",11/06/26 10:48:00 AM\n'
    "short,row\n"
)
PAGE = ('<a href="/data_files/official_records/11-20-2026.csv">x</a>'
        '<a href="/data_files/official_records/08-02-2024.csv">x</a>'
        '<a href="/data_files/official_records/01-02-2026.csv">x</a>'
        '<a href="/data_files/civil_data/2026-11-20.csv">x</a>')  # fmt: skip


def _norm(text: str = CSV) -> list[tuple[str, dict[str, Any]]]:
    body = canonical_json({"file": "11-20-2026.csv", "rows": parse_rows(text)})
    f = Fetched(HernandoOfficialRecords.source_id, "https://x.test/x", AT, 200, body, "")
    return [(r.table, dict(r.row)) for r in HernandoOfficialRecords().normalize(f)]


def _of(out: list[tuple[str, dict[str, Any]]], table: str) -> list[dict[str, Any]]:
    return [r for t, r in out if t == table]


def test_helpers() -> None:
    assert recorded_date("11/06/26 10:44:57 AM") == date(2026, 11, 6)
    assert recorded_date("1/2/1998") == date(1998, 1, 2) and recorded_date("1/2/98") == date(
        1998, 1, 2
    )
    assert recorded_date("13/40/26") is None and recorded_date("x") is None
    assert weekly_files(PAGE) == ["08-02-2024.csv", "01-02-2026.csv", "11-20-2026.csv"]
    assert len(parse_rows(CSV)) == 8  # the exact repeat and the short row are gone
    cfg = load_config()
    assert lookup(cfg, "JUDGMENT") == OrCode("JUDGMENT_LIEN", "creditor", "debtor")
    assert lookup(cfg, "DEED1") == OrCode("DEED", "grantor", "grantee")
    assert lookup(cfg, "AGREEMENT/CONTR DEED3") == OrCode("LAND_CONTRACT", "grantor", "grantee")
    for family in ("JUDGMENTX", "ORDERX2", "COURT PAPER X2", "AFFIDAVITX1", "RELEASEX1"):
        assert lookup(cfg, family) == "excluded", family
    assert lookup(cfg, "MARRIAGE RECORD W/O COURSE") == "excluded"
    assert lookup(cfg, "PROBATE DOCUMENTS1") == "excluded"
    assert lookup(cfg, "NEW KIND") is None
    assert {c.doc_type for c in cfg.descriptions.values()} <= set(DOC_TYPES)


def test_normalize() -> None:
    out = _norm()
    inst = {i["instrument_number"]: i for i in _of(out, "instrument")}
    assert set(inst) == {"2026076273", "2026076275", "2026076276"}
    j = inst["2026076273"]
    assert j["doc_type"] == "JUDGMENT_LIEN" and j["recorded_on"] == date(2026, 11, 6)
    assert j["book"] == "4783" and j["page"] == "483" and j["book_type"] == "OR"
    assert j["legal_desc_raw"] == "L7 Blk125 Un9 SubROYAL HIGHLANDS S T R"
    assert j["recorded_seq"] == 2026076273 and j["instrument_uid"] == "fl.hernando.or:2026076273"
    names = {p["party_id"]: p["raw_name"] for p in _of(out, "party")}
    roles = sorted((names[p["party_id"]], p["role"]) for p in _of(out, "instrument_party")
                   if p["instrument_uid"].endswith("6273"))  # fmt: skip
    assert roles == [("ACME BANK", "creditor"), ("ACME BANK NA", "creditor"),
                     ("DOE ANN", "debtor")]  # fmt: skip
    assert inst["2026076275"]["doc_type"] == "DEED" and inst["2026076275"]["legal_desc_raw"] is None
    assert inst["2026076276"]["doc_type"] == "OTHER"
    issues = sorted(i["issue_code"] for i in _of(out, "data_issue"))
    assert issues == ["missing_doc_type_or_recorded_date", "recorded_after_retrieval",
                      "unknown_doc_code"]  # fmt: skip
    # Family-law and marriage records are not loaded at all: no source record either.
    assert "ROE JOHN" not in names.values() and "MARRIED" not in names.values()
    assert len(_of(out, "source_record")) == 5


class FakeTransport:
    def __init__(self, pages: Mapping[str, tuple[int, str]]) -> None:
        self.pages = pages

    def __call__(
        self, url: str, headers: Mapping[str, str], timeout: float
    ) -> tuple[int, bytes, str]:
        status, text = self.pages.get(url, (404, ""))
        return status, text.encode(), "text/plain"


def _adapter(pages: Mapping[str, tuple[int, str]]) -> HernandoOfficialRecords:
    client = PoliteClient(min_interval_s=0, retries=0, transport=FakeTransport(pages),
                          sleep=lambda _s: None, now=lambda: AT)  # fmt: skip
    return HernandoOfficialRecords(client=client)


SITE = "https://subscriber.hernandoclerk.com/"
FILE = SITE + "data_files/official_records/11-20-2026.csv"


def test_fetch_partitions_health() -> None:
    a = _adapter({SITE: (200, PAGE), FILE: (200, CSV)})
    assert list(a.partitions())[-1] == {"file": "11-20-2026.csv"}
    f = a.fetch(FetchRequest({"file": "11-20-2026.csv", "limit": "1"}))
    rows = json.loads(f.content)["rows"]
    assert {r["ClerkFileNumber"] for r in rows} == {"2026076273"} and len(rows) == 2
    assert f.request == FILE and f.retrieved_at == AT
    with pytest.raises(ValueError, match="not a weekly"):
        a.fetch(FetchRequest({"file": "../x.csv"}))
    report = a.health()
    assert report.ok and report.detail == "11-20-2026.csv: 8 rows"
    assert not _adapter({SITE: (200, "")}).health().ok
    assert not _adapter({SITE: (500, "")}).health().ok
    assert not _adapter({SITE: (200, PAGE), FILE: (200, "a,b\n")}).health().ok
    with pytest.raises(RuntimeError, match="HTTP 404"):
        _adapter({SITE: (200, PAGE)}).fetch(FetchRequest({"file": "11-20-2026.csv"}))


def test_scrub_fixture_and_fixture_privacy() -> None:
    body = canonical_json({"file": "x.csv", "rows": parse_rows(CSV)})
    data = json.loads(HernandoOfficialRecords.scrub_fixture(body))
    assert all(r["Grantor"].startswith("TESTOWNER") for r in data["rows"])
    legal = {r["LegalDescription"] for r in data["rows"]}
    assert "L7 Blk125 Un9 SubROYAL HIGHLANDS S T R" not in legal
    assert by_source_id("fl.hernando.or") is HernandoOfficialRecords
    paths = sorted(FIX.glob("*.json"))
    assert paths
    empty = load_config().empty_legal
    for path in paths:
        for r in json.loads(path.read_text())["rows"]:
            for col in ("Grantor", "Grantee"):
                assert not r[col] or r[col].startswith("TESTOWNER"), col
            assert r["LegalDescription"] in ("", empty, "L1 Blk1 Un1 SubTEST SUBDIVISION S T R")
