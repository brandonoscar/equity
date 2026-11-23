"""FJC Integrated Database civil money judgments from the FJC's own cumulative file. Offline."""

from __future__ import annotations

import json
import os
import zipfile
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.fjc_idb_direct import (
    FJCDirectCivilJudgments,
    court,
    dedupe_key,
    file_stem,
    kept_direct,
    load_config,
    us_date,
)
from equity.adapters.registry import by_source_id
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 23, tzinfo=UTC)
FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "us.fjc.idb.direct.civil_judgments"
URL = "https://www.fjc.gov/sites/default/files/idb/textfiles/cv88on.zip"
COLUMNS = ["CIRCUIT", "DISTRICT", "OFFICE", "DOCKET", "ORIGIN", "FILEDATE", "FDATEUSE", "JURIS",
           "NOS", "TITL", "SECTION", "SUBSECT", "RESIDENC", "JURY", "CLASSACT", "DEMANDED",
           "FILEJUDG", "FILEMAG", "COUNTY", "ARBIT", "MDLDOCK", "PLT", "DEF", "TRANSDAT",
           "TRANSOFF", "TRANSDOC", "TRANSORG", "TERMDATE", "TDATEUSE", "TRCLACT", "TERMJUDG",
           "TERMMAG", "PROCPROG", "DISP", "NOJ", "AMTREC", "JUDGMENT", "DJOINED", "PRETRIAL",
           "TRIBEGAN", "TRIALEND", "TRMARB", "PROSE", "IFP", "STATUSCD", "TAPEYEAR"]  # fmt: skip


def row(**kw: str) -> dict[str, str]:
    base = {c: "-8" for c in COLUMNS}
    base.update(CIRCUIT="3", DISTRICT="13", OFFICE="2", DOCKET="2307217", FILEDATE="10/05/2023",
                NOS="190", COUNTY="42017", PLT="ACME CO., INC.", DEF="DOE, JOHN",
                TERMDATE="11/15/2024", NOJ="1", AMTREC="75", JUDGMENT="1", STATUSCD="L",
                TAPEYEAR="2025")  # fmt: skip
    base.update(kw)
    return base


def norm(rows: list[dict[str, str]]) -> list[tuple[str, dict[str, Any]]]:
    body = canonical_json({"file": "cv88on-20260826-1", "year": 2024, "rows": rows})
    f = Fetched(FJCDirectCivilJudgments.source_id, URL, AT, 200, body, "")
    return [(r.table, dict(r.row)) for r in FJCDirectCivilJudgments().normalize(f)]


def of(rows: list[tuple[str, dict[str, Any]]], table: str) -> list[dict[str, Any]]:
    return [r for t, r in rows if t == table]


def test_helpers() -> None:
    cfg = load_config()
    assert us_date("03/31/2025") == date(2025, 3, 31)
    assert us_date("02/30/2025") is None and us_date("-8") is None and us_date("") is None
    assert us_date("3/31/25") is None and us_date(None) is None
    assert court(row(), cfg) == "paed" and court(row(DISTRICT="7-"), cfg) == "akd"
    assert court(row(DISTRICT="99"), cfg) is None
    assert dedupe_key(row(), cfg) == "us.paed:2:2307217:2023-10-05"
    assert dedupe_key(row(OFFICE="", FILEDATE="-8"), cfg) == "us.paed:-:2307217:-8"
    assert dedupe_key(row(FILEDATE=""), cfg) == "us.paed:2:2307217:-"
    assert dedupe_key(row(DISTRICT="99"), cfg) is None
    assert dedupe_key(row(DOCKET=" "), cfg) is None
    assert len(set(cfg.districts.values())) == len(cfg.districts) == 94


def test_filter_is_the_courtlistener_filter() -> None:
    assert kept_direct(row()) == (date(2024, 11, 15), 75)
    assert kept_direct(row(NOJ="2")) is not None
    for bad in ({"JUDGMENT": "2"}, {"JUDGMENT": "-8"}, {"NOJ": "0"}, {"NOJ": "5"},
                {"NOJ": "6"}, {"AMTREC": "0"}, {"AMTREC": "-8"}, {"TERMDATE": ""},
                {"TERMDATE": "13/01/2024"}):  # fmt: skip
        assert kept_direct(row(**bad)) is None, bad


def test_case_parties_judgment() -> None:
    got = norm([row(PLT="USA, ET AL", DEF="DOE, ET AL", COUNTY="88888", AMTREC="9999"),
                row(DOCKET="2300001", AMTREC="5277")])  # fmt: skip
    cases = {c["case_number_raw"]: c for c in of(got, "court_case")}
    case = cases["2307217"]
    assert case["case_uid"] == "us.paed:2:2307217:2023-10-05#2024-11-15"
    assert case["court_id"] == "us.paed" and case["case_number_norm"] == "2:2307217"
    assert case["filed_on"] == date(2023, 10, 5) and case["closed_on"] == date(2024, 11, 15)
    assert case["nature_of_suit"] == "190" and case["jurisdiction"] == "paed"
    assert cases["2300001"]["jurisdiction"] == "42017"
    js = {j["case_uid"]: j for j in of(got, "judgment")}
    assert js[case["case_uid"]]["principal"] is None  # 9999: a floor, not an amount
    assert js[cases["2300001"]["case_uid"]]["principal"] == Decimal(5_277_000)
    assert {j["judgment_type"] for j in js.values()} == {"money"}
    parties = {p["party_id"]: p for p in of(got, "party")}
    roles = {(cp["case_uid"], cp["role"]): parties[cp["party_id"]] for cp in of(got, "case_party")}
    assert roles[(case["case_uid"], "creditor")]["raw_name"] == "USA, ET AL"
    assert roles[(case["case_uid"], "debtor")]["raw_name"] == "DOE, ET AL"
    plain = norm([row(PLT="USA", DEF="DOE", COUNTY="88888", AMTREC="9999")])
    assert {p["party_id"] for p in of(plain, "party")} <= set(parties)  # ET AL: same party
    lone = norm([row(DEF="-8")])
    assert [cp["role"] for cp in of(lone, "case_party")] == ["creditor"]


def test_uids_are_unique_and_repeats_are_dropped() -> None:
    a = row()
    reopened = row(TERMDATE="03/01/2025", AMTREC="80")  # same docket, later termination
    twin = row(AMTREC="90")  # same docket and same termination day
    got = norm([twin, a, a, reopened])
    uids = sorted(c["case_uid"] for c in of(got, "court_case"))
    assert uids == ["us.paed:2:2307217:2023-10-05#2024-11-15~1",
                    "us.paed:2:2307217:2023-10-05#2024-11-15~2",
                    "us.paed:2:2307217:2023-10-05#2025-03-01"]  # fmt: skip
    assert len(of(got, "judgment")) == 3  # the exact repeat of `a` is dropped
    assert norm([a, twin, reopened]) == norm([reopened, twin, a])  # order does not matter


def test_bad_rows_are_skipped_or_cleaned() -> None:
    got = norm([
        row(DOCKET="1", FILEDATE="garbage"),        # filed unknown, judgment kept
        row(DOCKET="2", FILEDATE="12/01/2024"),     # filed after termination: dropped
        row(DOCKET="3", TERMDATE="01/01/2027"),     # after retrieval: skipped
        row(DOCKET="4", DISTRICT="99"),             # unknown court: skipped
        row(DOCKET="5", JUDGMENT="2"),              # not for the plaintiff: skipped
        row(DOCKET="6", NOS="-8"),                  # no nature of suit
    ])  # fmt: skip
    cases = {c["case_number_raw"]: c for c in of(got, "court_case")}
    assert set(cases) == {"1", "2", "6"}
    assert cases["1"]["filed_on"] is None and cases["2"]["filed_on"] is None
    assert cases["1"]["case_uid"] == "us.paed:2:1:garbage#2024-11-15"
    assert cases["6"]["nature_of_suit"] is None


def write_zip(path: Path, rows: list[dict[str, str]], extra: str = "") -> None:
    lines = ["\t".join(COLUMNS)] + ["\t".join(r[c] for c in COLUMNS) for r in rows]
    info = zipfile.ZipInfo("cv88on.txt", date_time=(2026, 8, 26, 11, 12, 0))
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(info, "\r\n".join(lines) + "\r\n" + extra)
    os.utime(path, (AT.timestamp(), AT.timestamp()))


def adapter(tmp_path: Path, rows: list[dict[str, str]], extra: str = "") -> FJCDirectCivilJudgments:
    path = tmp_path / "manual" / "cv88on.zip"
    path.parent.mkdir()
    write_zip(path, rows, extra)
    a = FJCDirectCivilJudgments(path)
    a.cache_dir = tmp_path / "work"  # type: ignore[misc]
    return a


def test_manual_file_partitions_extract_and_keys(tmp_path: Path) -> None:
    rows = [row(), row(DOCKET="9", JUDGMENT="2"), row(DOCKET="8", TERMDATE="05/05/2026")]
    a = adapter(tmp_path, rows, extra="short\tline\r\n")
    stem = a.stem()
    assert stem == file_stem(a.manual_path, "cv88on.txt")
    assert stem.startswith("cv88on-20260826-")
    parts = list(a.partitions())
    assert parts[0] == {"file": stem, "year": "1984"} and parts[-1]["year"] == "2026"
    assert a.retrieved_at() == AT
    name, keys = a.kept_keys()
    assert name == stem
    assert keys == {"us.paed:2:2307217:2023-10-05", "us.paed:2:8:2023-10-05"}
    manifest = json.loads((a.cache_dir / stem / "_manifest.json").read_text())
    assert manifest["rows"] == 4 and manifest["bad_rows"] == 1 and manifest["kept"] == 2
    got = a.fetch(FetchRequest({"file": stem, "year": "2024"}))
    assert [r["DOCKET"] for r in json.loads(got.content)["rows"]] == ["2307217"]
    assert got.request == f"{URL}#{stem}:TERMDATE=2024" and got.retrieved_at == AT
    lim = a.fetch(FetchRequest({"year": "2026", "limit": "1"}))
    assert len(json.loads(lim.content)["rows"]) == 1 and (a.cache_dir / stem).exists()
    a.fetch(FetchRequest({"file": stem, "year": "2026"}))
    assert not (a.cache_dir / stem).exists()  # the last partition frees the extract
    assert a.kept_keys()[1] == keys  # the keys file stays
    with pytest.raises(ValueError, match="planned for"):
        a.fetch(FetchRequest({"file": "cv88on-20250101-1", "year": "2024"}))
    h = a.health()
    assert h.ok and h.detail == stem and h.shape == ("cv88on.txt",)


def test_missing_manual_file_says_where_to_get_it(tmp_path: Path) -> None:
    a = FJCDirectCivilJudgments(tmp_path / "nope.zip")
    with pytest.raises(FileNotFoundError, match="by hand"):
        list(a.partitions())
    assert a.health().ok is False
    (tmp_path / "bad.zip").write_bytes(b"not a zip")
    assert FJCDirectCivilJudgments(tmp_path / "bad.zip").health().ok is False


def test_fixture_normalizes() -> None:
    path = next(FIX.glob("*.json"))
    f = Fetched(FJCDirectCivilJudgments.source_id, path.as_uri(), AT, 200, path.read_bytes(), "")
    a = by_source_id(FJCDirectCivilJudgments.source_id)()  # type: ignore[abstract]
    rows = [(r.table, dict(r.row)) for r in a.normalize(f)]
    t = Counter(table for table, _ in rows)
    assert t["court_case"] == t["judgment"] == t["source_record"] > 0
    assert {r["role"] for r in of(rows, "case_party")} == {"creditor", "debtor"}
    assert all(r["court_id"].startswith("us.") for r in of(rows, "court_case"))
    assert all(r["closed_on"].year == 2025 for r in of(rows, "court_case"))
    src = a.source_row()
    assert src["access_method"] == "manual" and src["cost_model"] == "free"
    assert src["terms_checked_on"] == date(2026, 11, 23)
