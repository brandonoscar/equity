"""Harris County District Clerk CaseSummaryMods civil debt judgments. Offline."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import Response
from equity.adapters.record import scrub
from equity.adapters.registry import by_source_id
from equity.adapters.rows import canonical_json
from equity.adapters.tx.harris_district import (
    HarrisDistrictCivilJudgments,
    case_uid,
    court_id,
    hidden_fields,
    iso_date,
    listed_files,
    read_rows,
)

AT = datetime(2026, 11, 23, tzinfo=UTC)
FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "tx.harris.district.civil_judgments"
URL = "https://www.hcdistrictclerk.com/Common/e-services/PublicDatasets.aspx"
BASE = {"region": "CIV", "casenbr": "202456660", "file_crt": "129", "curr_crt": "055",
        "file_dt": "2024-08-26 00:00:00", "cst": "D", "cs_typ": "20140005", "toac": "DCC",
        "plaintiff": "ACME BANK NA", "defendant": "DOE, ANN", "judgment_dt": "2025-05-14",
        "judgment": "DEFAULT JUDGMENT SIGNED", "lastmoddt": "2025-10-01 11:42:00"}  # fmt: skip
PAGE = (
    '<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="abc&amp;d" />'
    '<input type="hidden" name="hiddenDownloadFile" id="hiddenDownloadFile" value="" />'
    '<input type="hidden" name="__EVENTVALIDATION" value="ev" />'
    "<a onclick=\"DownloadDoc('Civil\\\\CaseSummaryMods_Historical-2010-2014.txt');\">D</a>"
    "<a onclick=\"DownloadDoc('Civil\\\\CaseSummaryMods_Historical-2015-2019.txt');\">D</a>"
    "<a onclick=\"DownloadDoc('Civil\\\\CaseSummaryMods_Historical-2020-2024.txt');\">D</a>"
    "<a onclick=\"DownloadDoc('Civil\\\\CaseSummaryMods_HistoricalCurrent-2025-261101.txt');\">"
    "<a onclick=\"DownloadDoc('Civil\\\\CaseSummaryMods_Daily-2026-11-20.txt');\">D</a>"
    "<a onclick=\"DownloadDoc('Criminal\\\\CaseSummaryMods_Historical-2020-2024.txt');\">D</a>"
)


def _norm(rows: list[dict[str, str]]) -> list[tuple[str, dict[str, Any]]]:
    body = canonical_json({"file": "f.txt", "rows": rows})
    f = Fetched(HarrisDistrictCivilJudgments.source_id, URL, AT, 200, body, "")
    return [(r.table, dict(r.row)) for r in HarrisDistrictCivilJudgments().normalize(f)]


def _of(out: list[tuple[str, dict[str, Any]]], table: str) -> list[dict[str, Any]]:
    return [r for t, r in out if t == table]


def test_helpers() -> None:
    assert iso_date("2024-08-26 00:00:00") == date(2024, 8, 26)
    assert iso_date("2025-05-14") == date(2025, 5, 14)
    assert iso_date("") is None and iso_date("ORDER") is None and iso_date("2025-02-30") is None
    assert case_uid(" 202456660 ") == "tx.harris.district:202456660"
    assert (
        court_id("055") == "tx.harris.district.55" and court_id("") == "tx.harris.district.unknown"
    )
    assert court_id("A1") == "tx.harris.district.a1"
    assert listed_files(PAGE, "Civil") == [
        "CaseSummaryMods_Daily-2026-11-20.txt",
        "CaseSummaryMods_Historical-2010-2014.txt",
        "CaseSummaryMods_Historical-2015-2019.txt",
        "CaseSummaryMods_Historical-2020-2024.txt",
        "CaseSummaryMods_HistoricalCurrent-2025-261101.txt",
    ]
    assert hidden_fields(PAGE) == {"__VIEWSTATE": "abc&d", "__EVENTVALIDATION": "ev"}
    text = 'rundate\tregion\tcasenbr\tjudgment\nx\tCIV\t 1 \tA "B"\n\n'
    assert read_rows(text) == [{"rundate": "x", "region": "CIV", "casenbr": "1",
                                "judgment": 'A "B"'}]  # fmt: skip
    assert read_rows("") == []
    with pytest.raises(ValueError, match="not a CaseSummaryMods"):
        read_rows("<html>\n")


def test_fixture() -> None:
    path = next(FIX.glob("*.json"))
    f = Fetched(HarrisDistrictCivilJudgments.source_id, path.as_uri(), AT, 200,
                path.read_bytes(), "")  # fmt: skip
    out = [(r.table, dict(r.row)) for r in HarrisDistrictCivilJudgments().normalize(f)]
    t = Counter(table for table, _ in out)
    assert t["court_case"] == t["source_record"] > 0 and t["judgment"] > 0
    roles = Counter(r["role"] for r in _of(out, "case_party"))
    assert roles["creditor"] == roles["debtor"] == t["court_case"] - roles["plaintiff"]
    assert all(p["raw_name"].startswith("TESTOWNER") for p in _of(out, "party"))
    assert {r["jurisdiction"] for _, r in out if "jurisdiction" in r} == {"48201"}


def test_judgments_and_roles() -> None:
    out = _norm([
        BASE,
        {**BASE, "pj_num": "1", "judgment": "DEFAULT JDGMT (PJ)", "judgment_dt": "2026-01-02"},
        {**BASE, "casenbr": "2", "judgment": "ORDER OF NON-SUIT SIGNED"},
        {**BASE, "casenbr": "3", "judgment": "Default Judgment", "judgment_dt": "2027-01-01",
         "file_dt": "2027-01-01"},
        {**BASE, "casenbr": "4", "cs_typ": "20140017"},  # motor vehicle accident: not kept
        {**BASE, "casenbr": "5", "region": "FAM"},
        {**BASE, "casenbr": "6", "judgment": "final judgment signed for plaintiff  (non-jury)"},
    ])  # fmt: skip
    cases = {c["case_number_norm"]: c for c in _of(out, "court_case")}
    assert sorted(cases) == ["2", "202456660", "3", "6"]
    c = cases["202456660"]
    assert c["court_id"] == "tx.harris.district.55" and c["filed_on"] == date(2024, 8, 26)
    assert c["case_type"] == "DEBT/CONTRACT - CONSUMER/DTPA" and c["nature_of_suit"] == "DCC"
    assert cases["3"]["filed_on"] is None
    js = {j["case_uid"]: j for j in _of(out, "judgment")}
    assert sorted(js) == ["tx.harris.district:202456660", "tx.harris.district:6"]
    j = js["tx.harris.district:202456660"]
    assert j["judgment_type"] == "default" and j["entered_on"] == date(2025, 5, 14)
    assert j["principal"] is None and js["tx.harris.district:6"]["judgment_type"] == "money"
    names = {p["party_id"]: p["raw_name"] for p in _of(out, "party")}
    by_case: dict[str, dict[str, str]] = {}
    for cp in _of(out, "case_party"):
        by_case.setdefault(cp["case_uid"].rsplit(":", 1)[1], {})[names[cp["party_id"]]] = cp["role"]
    assert by_case["202456660"] == {"ACME BANK NA": "creditor", "DOE, ANN": "debtor"}
    assert by_case["2"] == {"ACME BANK NA": "plaintiff", "DOE, ANN": "defendant"}
    assert by_case["3"] == {"ACME BANK NA": "plaintiff", "DOE, ANN": "defendant"}


class FakeSite:
    def __init__(self, page: str, files: dict[str, bytes], status: int = 200) -> None:
        self.page, self.files, self.status = page, files, status
        self.posts: list[dict[str, str]] = []

    def now(self) -> datetime:
        return AT

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        return Response(url, self.status, self.page.encode(), "text/html", AT)

    def post_form(self, url: str, fields: dict[str, str]) -> Response:
        self.posts.append(dict(fields))
        name = fields["hiddenDownloadFile"].split("\\", 1)[1]
        body = self.files.get(name)
        return Response(url, 200 if body else 500, body or b"", "application/octet-stream", AT)


def _tsv(rows: list[dict[str, str]]) -> bytes:
    cols = ["rundate", *BASE, "pj_num"]
    lines = ["\t".join(cols)] + ["\t".join(r.get(c, "") for c in cols) for r in rows]
    return ("\r\n".join(lines) + "\r\n").encode("latin-1")


def test_files_fetch_health() -> None:
    cur = "CaseSummaryMods_HistoricalCurrent-2025-261101.txt"
    rows = [BASE, {**BASE, "casenbr": "9", "region": "FAM"},
            {**BASE, "casenbr": "8", "plaintiff": "RENÉ CO"}]  # fmt: skip
    site = FakeSite(PAGE, {cur: _tsv(rows)})
    a = HarrisDistrictCivilJudgments(site)  # type: ignore[arg-type]
    assert [p["file"] for p in a.partitions()] == [
        "CaseSummaryMods_Historical-2015-2019.txt",
        "CaseSummaryMods_Historical-2020-2024.txt",
        cur,
    ]  # 2010-2014 is before first_year; daily and criminal files are not used
    f = a.fetch(FetchRequest({"file": cur}))
    (post,) = site.posts
    assert post["hiddenDownloadFile"] == "Civil\\" + cur and post["__VIEWSTATE"] == "abc&d"
    assert post[a.config.download_button] == ""
    data = json.loads(f.content)
    assert [r["casenbr"] for r in data["rows"]] == ["202456660", "8"]  # FAM row not stored
    assert data["rows"][1]["plaintiff"] == "RENÉ CO" and "pj_num" not in data["rows"][0]
    assert f.request.endswith("#Civil/" + cur)
    limited = a.fetch(FetchRequest({"file": cur, "limit": "1"}))
    assert len(json.loads(limited.content)["rows"]) == 1
    scrubbed = scrub(json.loads(f.content), HarrisDistrictCivilJudgments.pii_fields)
    assert "ACME" not in json.dumps(scrubbed) and "DOE" not in json.dumps(scrubbed)
    with pytest.raises(ValueError, match="not a CaseSummaryMods"):
        a.fetch(FetchRequest({"file": "../x.txt"}))
    with pytest.raises(ValueError, match="not offered"):
        a.fetch(FetchRequest({"file": "CaseSummaryMods_Historical-2000-2004.txt"}))
    with pytest.raises(RuntimeError, match="HTTP 500 posting"):
        a.fetch(FetchRequest({"file": "CaseSummaryMods_Historical-2020-2024.txt"}))
    assert a.health().ok and a.health().shape == (cur,)
    no_current = HarrisDistrictCivilJudgments(FakeSite(PAGE.replace("Current", "X"), {}))  # type: ignore[arg-type]
    assert not no_current.health().ok
    down = HarrisDistrictCivilJudgments(FakeSite(PAGE, {}, status=503))  # type: ignore[arg-type]
    assert not down.health().ok and "HTTP 503" in down.health().detail
    assert a.source_row()["cost_model"] == "free" and a.single_store
    assert by_source_id(a.source_id) is HarrisDistrictCivilJudgments
