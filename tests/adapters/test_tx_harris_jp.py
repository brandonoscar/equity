"""Harris County JP civil judgments (Judgments Entered extract). Offline."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.http import Response
from equity.adapters.registry import by_source_id
from equity.adapters.rows import canonical_json
from equity.adapters.tx.harris_jp import (
    HarrisJPCivilJudgments,
    address,
    case_uid,
    court_id,
    money,
    months,
    party_name,
    rate,
    read_rows,
    us_date,
    winner,
)

AT = datetime(2026, 11, 23, tzinfo=UTC)
FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "tx.harris.jp.civil_judgments"
BASE: dict[str, str] = {
    "Case Number": "255100500001", "JP Court ID": "Precinct 5, Place 1",
    "Case Type": "Debt Claim", "Case File Date": "03/05/2026", "Case Status": "Disposed",
    "Plaintiff Name": "Acme Funding, LLC", "Plaintiff Addr Line 1": "1 Main St",
    "Plaintiff Addr City": "Dallas", "Plaintiff Addr State": "TX", "Plaintiff Addr Zip": "75201",
    "Defendant Name": "Ann B Doe", "Defendant Addr Line 1": "2 Oak Ave",
    "Defendant Addr Line 2": "Apt 3", "Defendant Addr City": "Houston",
    "Defendant Addr State": "TX", "Defendant Addr Zip": "77002-1234",
    "Judgment Text": "Default Judgment", "Judgment Date": "10/05/2026",
    "Judgment In Favor Of": "Acme Funding, LLC", "Judgment Against": "Doe, Ann B",
    "Judgment Amount": "1118.2900", "Attorney Fees": "0.0000", "Court Costs": "54.0000",
    "Post-Judg Int Rate": "6.7500",
}  # fmt: skip


def _norm(rows: list[dict[str, str]], at: datetime = AT) -> list[tuple[str, dict[str, Any]]]:
    body = canonical_json({"from": "2026-10-01", "to": "2026-10-31", "rows": rows})
    f = Fetched(HarrisJPCivilJudgments.source_id, "https://x.test/x", at, 200, body, "")
    return [(r.table, dict(r.row)) for r in HarrisJPCivilJudgments().normalize(f)]


def _of(out: list[tuple[str, dict[str, Any]]], table: str) -> list[dict[str, Any]]:
    return [r for t, r in out if t == table]


def test_helpers() -> None:
    assert us_date("10/05/2026") == date(2026, 10, 5)
    assert us_date("") is None and us_date("2026-10-05") is None and us_date("13/40/2026") is None
    assert money("1118.2900") == Decimal("1118.29") and money("$1,000") == Decimal("1000.00")
    assert money("") is None and money("x") is None and money("-5") is None
    assert rate("6.7500") == Decimal("0.0675") and rate("0.0000") is None
    assert rate("2511.14") is None and rate("") is None
    assert court_id("Precinct 5, Place 1") == "tx.harris.jp.5-1"
    assert court_id("Somewhere Else") == "tx.harris.jp.somewhere_else"
    assert court_id("") == "tx.harris.jp.unknown"
    assert case_uid(" cv12c0137389 ") == "tx.harris.jp:CV12C0137389"
    assert party_name("James Tritz and all other occupants") == "James Tritz"
    assert party_name("Fatima  Nunez & All Occupants") == "Fatima Nunez"
    assert party_name("Ann Doe and Current Occupants") == "Ann Doe"
    assert party_name("Acme LLC") == "Acme LLC"
    assert list(months(date(2026, 1, 15), date(2026, 3, 9))) == [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 9)),
    ]


def test_winner_and_address() -> None:
    assert winner(BASE) == "plaintiff"
    flipped = {**BASE, "Judgment In Favor Of": "Doe, Ann B",
               "Judgment Against": "Acme Funding, LLC and others"}  # fmt: skip
    assert winner(flipped) == "defendant"
    assert winner({**BASE, "Judgment In Favor Of": "", "Judgment Against": ""}) is None
    same = {**BASE, "Judgment In Favor Of": "Acme Funding", "Judgment Against": "Acme Funding"}
    assert winner(same) is None
    a = address(BASE, "Defendant Addr")
    assert a is not None and a["line1"] == "2 OAK AVE APT 3" and a["zip5"] == "77002"
    unknown = {"P Addr Line 1": "unknown", "P Addr City": "unknown", "P Addr State": "TX",
               "P Addr Zip": "00000"}  # fmt: skip
    assert address(unknown, "P Addr") is None  # a state alone is no address
    u = address({**unknown, "P Addr Zip": "77002"}, "P Addr")
    assert u is not None and u["line1"] is None and u["city"] is None and u["zip5"] == "77002"
    assert address({}, "P Addr") is None


def test_read_rows() -> None:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(["Case Number", "Style Of Case "])
    w.writerow(["1", 'A "B" vs. C'])
    w.writerow([])
    assert read_rows(buf.getvalue()) == [{"Case Number": "1", "Style Of Case": 'A "B" vs. C'}]
    assert read_rows("") == []
    with pytest.raises(ValueError, match="not a JP extract"):
        read_rows("<html>error</html>\n")


def test_fixture_creditors_debtors_judgments() -> None:
    path = next(FIX.glob("*.json"))
    f = Fetched(HarrisJPCivilJudgments.source_id, path.as_uri(), AT, 200, path.read_bytes(), "")
    out = [(r.table, dict(r.row)) for r in HarrisJPCivilJudgments().normalize(f)]
    t = Counter(table for table, _ in out)
    assert t["court_case"] == t["source_record"] > 0 and t["judgment"] > 0
    roles = Counter(r["role"] for r in _of(out, "case_party"))
    assert roles["creditor"] > 0 and roles["debtor"] > 0
    debtors = {r["party_id"] for r in _of(out, "case_party") if r["role"] == "debtor"}
    with_addr = [p for p in _of(out, "party") if p["party_id"] in debtors and p["address_id"]]
    assert with_addr and all(p["raw_name"].startswith("TESTOWNER") for p in _of(out, "party"))
    assert {r["jurisdiction"] for _, r in out if "jurisdiction" in r} == {"48201"}


def test_plaintiff_money_judgment() -> None:
    out = _norm([BASE])
    (case,) = _of(out, "court_case")
    assert case["case_uid"] == "tx.harris.jp:255100500001"
    assert case["court_id"] == "tx.harris.jp.5-1" and case["filed_on"] == date(2026, 3, 5)
    (j,) = _of(out, "judgment")
    assert j["entered_on"] == date(2026, 10, 5) and j["judgment_type"] == "default"
    assert j["principal"] == Decimal("1118.29") and j["costs"] == Decimal("54.00")
    assert j["rate"] == Decimal("0.0675") and j["judgment_uid"].startswith(
        "tx.harris.jp:255100500001:2026-10-05:default:"
    )
    names = {p["party_id"]: p for p in _of(out, "party")}
    roles = {names[cp["party_id"]]["raw_name"]: cp["role"] for cp in _of(out, "case_party")}
    assert roles == {"Acme Funding, LLC": "creditor", "Ann B Doe": "debtor"}
    debtor = next(p for p in names.values() if p["raw_name"] == "Ann B Doe")
    addr = {a["address_id"]: a for a in _of(out, "address")}
    assert addr[debtor["address_id"]]["zip5"] == "77002"


def test_counterclaim_flips_roles_and_both_ways_names_no_debtor() -> None:
    flipped = {**BASE, "Judgment In Favor Of": "Doe, Ann B", "Judgment Against": "Acme Funding"}
    roles = {cp["role"] for cp in _of(_norm([flipped]), "case_party")}
    assert roles == {"creditor", "debtor"}
    out = _norm([flipped])
    names = {p["party_id"]: p["raw_name"] for p in _of(out, "party")}
    assert {names[cp["party_id"]]: cp["role"] for cp in _of(out, "case_party")} == {
        "Acme Funding, LLC": "debtor", "Ann B Doe": "creditor"}  # fmt: skip
    # The extract repeats a case once per (in favor of, against) pairing: both ways is unclear.
    both = _norm([BASE, {**flipped, "Judgment Amount": "50.00"}])
    assert {cp["role"] for cp in _of(both, "case_party")} == {"plaintiff", "defendant"}
    assert len(_of(both, "judgment")) == 2 and len(_of(both, "court_case")) == 1


def test_what_is_not_a_judgment() -> None:
    rows = [
        {**BASE, "Case Number": "1", "Judgment Amount": "0", "Court Costs": "0"},  # no money
        {**BASE, "Case Number": "2", "Judgment Text": "Dismissed"},  # a disposition
        {**BASE, "Case Number": "3", "Case Type": "Occupational Driver's License"},  # skipped
        {**BASE, "Case Number": "4", "Judgment Date": "01/02/2027"},  # after retrieval
        {**BASE, "Case Number": "5", "Judgment Amount": "0.0000", "Case File Date": "1/1/2027"},
        {**BASE, "Case Number": "", "Judgment Amount": "5"},  # no case number
    ]
    out = _norm(rows)
    cases = {c["case_number_norm"]: c for c in _of(out, "court_case")}
    assert sorted(cases) == ["1", "2", "4", "5"]
    assert cases["5"]["filed_on"] is None
    (j,) = _of(out, "judgment")  # case 5: costs only (54.00), principal 0
    assert j["case_uid"] == "tx.harris.jp:5" and j["principal"] == Decimal("0.00")
    assert {cp["role"] for cp in _of(out, "case_party") if cp["case_uid"].endswith(":1")} == {
        "plaintiff", "defendant"}  # fmt: skip


def test_costs_only_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    from equity.adapters.tx import harris_jp

    cfg = replace(harris_jp.load_config(), costs_only_counts=False)
    monkeypatch.setattr(harris_jp, "load_config", lambda: cfg)
    costs_only = {**BASE, "Judgment Amount": "0"}
    assert _of(_norm([costs_only]), "judgment") == []
    assert len(_of(_norm([{**costs_only, "Attorney Fees": "300"}]), "judgment")) == 1


def test_occupants_and_duplicate_parties() -> None:
    row = {**BASE, "Case Type": "Eviction", "Defendant Name": "Ann B Doe and All Occupants",
           "Second Defendant Name": "ann b. doe",
           "Judgment Against": "Ann B Doe and others"}  # fmt: skip
    out = _norm([row])
    assert sorted(p["raw_name"] for p in _of(out, "party")) == ["Acme Funding, LLC", "Ann B Doe"]


class FakeClient:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body, self.status = body, status
        self.calls: list[tuple[str, dict[str, str]]] = []

    def now(self) -> datetime:
        return AT

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        self.calls.append((url, dict(params or {})))
        return Response(url + "?q", self.status, self.body, "text/plain", AT)


def _csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=[f + " " for f in rows[0]], quoting=csv.QUOTE_ALL)
    w.writeheader()
    w.writerows({k + " ": v for k, v in r.items()} for r in rows)
    return buf.getvalue().encode()


def test_fetch_partitions_scrub_health() -> None:
    real = {**BASE, "Style Of Case": "Acme Funding, LLC vs. Ann B Doe",
            "Plaintiff Atty Name": "Lawyer Person", "Second Plaintiff Name": ""}  # fmt: skip
    fake = FakeClient(_csv([real, {**BASE, "Case Number": "2"}]))
    a = HarrisJPCivilJudgments(fake)  # type: ignore[arg-type]
    plan = list(a.partitions())
    assert plan[-2:] == [
        {"from": "2016-12-17", "to": "2016-12-31"},
        {"from": "2016-12-01", "to": "2016-12-16"},
    ]  # newest first
    assert (
        plan[:2]
        == [{"from": "2026-11-12", "to": "2026-11-22"}, {"from": "2026-11-01", "to": "2026-11-11"}]
        and len(plan) == 240
    )
    assert a.split_partition({"from": "2026-02-01", "to": "2026-02-28", "x": "1"}) == [
        {"from": "2026-02-15", "to": "2026-02-28", "x": "1"},
        {"from": "2026-02-01", "to": "2026-02-14", "x": "1"},
    ]
    assert a.split_partition({"from": "2026-02-01", "to": "2026-02-01"}) == [
        {"from": "2026-02-01", "to": "2026-02-01"}]  # fmt: skip
    f = a.fetch(FetchRequest({"from": "2026-10-01", "to": "2026-10-31", "limit": "1"}))
    url, params = fake.calls[-1]
    assert url.endswith("/PublicExtracts/GetExtractData")
    assert params["extract"] == "3" and params["court"] == "300" and params["format"] == "csv"
    assert (params["fdate"], params["tdate"]) == ("10/01/2026", "10/31/2026")
    data = json.loads(f.content)
    assert len(data["rows"]) == 1 and "Second Plaintiff Name" not in data["rows"][0]
    scrubbed = HarrisJPCivilJudgments.scrub_fixture(f.content)
    text = scrubbed.decode()
    for leak in ("Acme", "Doe", "Lawyer", "Main St", "Oak Ave"):
        assert leak not in text, leak
    (row,) = json.loads(scrubbed)["rows"]
    assert winner(row) == "plaintiff" and row["Judgment In Favor Of"] == row["Plaintiff Name"]
    assert row["Style Of Case"] == f"{row['Plaintiff Name']} vs. {row['Defendant Name']}"
    with pytest.raises(ValueError, match="1 to 90 days"):
        a.fetch(FetchRequest({"from": "2026-01-01", "to": "2026-06-30"}))
    with pytest.raises(ValueError, match="1 to 90 days"):
        a.fetch(FetchRequest({"from": "2026-02-01", "to": "2026-01-01"}))
    report = a.health()
    assert report.ok and "2 rows on 2026-11-22" in report.detail and "Case Number" in report.shape
    assert fake.calls[-1][1]["fdate"] == fake.calls[-1][1]["tdate"] == "11/22/2026"
    assert not HarrisJPCivilJudgments(FakeClient(b"", 503)).health().ok  # type: ignore[arg-type]
    html = FakeClient(b"<html>maintenance</html>")
    assert not HarrisJPCivilJudgments(html).health().ok  # type: ignore[arg-type]
    empty = HarrisJPCivilJudgments(FakeClient(_csv([BASE])[:40] + b"\n"))  # type: ignore[arg-type]
    assert empty.health().shape == ()
    assert a.source_row()["kind"] == "court" and a.source_row()["cost_model"] == "free"
    assert by_source_id("tx.harris.jp.civil_judgments") is HarrisJPCivilJudgments


def test_scrub_unclear_winner_still_pseudonymized() -> None:
    row = {**BASE, "Judgment In Favor Of": "Someone Else", "Judgment Against": "Nobody"}
    body = canonical_json({"from": "a", "to": "b", "rows": [row]})
    (out,) = json.loads(HarrisJPCivilJudgments.scrub_fixture(body))["rows"]
    assert out["Judgment In Favor Of"].startswith("TESTOWNER")
    assert out["Judgment Against"].startswith("TESTOWNER")
