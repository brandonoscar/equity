"""EPA ECHO ICIS-FE&C judicial cases with a penalty or cost recovery. Offline."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.federal.epa_echo import (
    COLUMNS,
    EPAJudicialCases,
    amount,
    kept_cases,
    kept_conclusion,
    load_config,
    state_jurisdiction,
    us_date,
    zip5,
)
from equity.adapters.http import Response
from equity.adapters.registry import by_source_id

AT = datetime(2026, 11, 23, tzinfo=UTC)
URL = "https://echo.epa.gov/files/echodownloads/case_downloads.zip"
FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "us.epa.echo.judicial_cases"


def conclusion(**kw: str) -> dict[str, str]:
    base = {"ACTIVITY_TYPE_CODE": "JDC", "ENF_CONCLUSION_ID": "11", "ENF_CONCLUSION_NMBR": "1",
            "ENF_CONCLUSION_ACTION_CODE": "CDC", "ENF_CONCLUSION_NAME": "ACME SETTLEMENT",
            "SETTLEMENT_LODGED_DATE": "02/01/2020", "SETTLEMENT_ENTERED_DATE": "03/24/2020",
            "PRIMARY_LAW": "CAA", "FED_PENALTY_ASSESSED_AMT": "125000",
            "STATE_LOCAL_PENALTY_AMT": "", "COST_RECOVERY_AWARDED_AMT": ""}  # fmt: skip
    base.update(kw)
    return base


def case(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ACTIVITY_ID": "1", "CASE_NUMBER": "05-2019-0001", "CASE_NAME": "ACME CORP, ET AL",
        "ACTIVITY_TYPE_CODE": "JDC", "ACTIVITY_STATUS_DESC": "Closed",
        "conclusions": [conclusion()],
        "defendants": [{"DEFENDANT_NAME": "Acme Corp", "NAMED_IN_COMPLAINT_FLAG": "Y",
                        "NAMED_IN_SETTLEMENT_FLAG": "Y"}],
        "facilities": [{"REGISTRY_ID": "1100", "FACILITY_NAME": "ACME PLANT",
                        "LOCATION_ADDRESS": "1 MAIN ST", "CITY": "CANTON", "STATE_CODE": "OH",
                        "ZIP": "44702-1234"}],
        "dockets": [{"REGIONAL_DOCKET_NMBR": "5:19-cv-00001"}],
    }  # fmt: skip
    base.update(kw)
    return base


def norm(cases: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    body = json.dumps({"file": URL, "cases": cases}).encode()
    f = Fetched(EPAJudicialCases.source_id, URL, AT, 200, body, "")
    return [(r.table, dict(r.row)) for r in EPAJudicialCases().normalize(f)]


def of(rows: list[tuple[str, dict[str, Any]]], table: str) -> list[dict[str, Any]]:
    return [r for t, r in rows if t == table]


def parties(rows: list[tuple[str, dict[str, Any]]]) -> dict[str, tuple[str, dict[str, Any]]]:
    by_id = {p["party_id"]: p for p in of(rows, "party")}
    return {by_id[cp["party_id"]]["raw_name"]: (cp["role"], by_id[cp["party_id"]])
            for cp in of(rows, "case_party")}  # fmt: skip


def test_helpers() -> None:
    cfg = load_config()
    assert us_date("03/24/1994") == date(1994, 3, 24)
    assert us_date("") is None and us_date("13/01/2020") is None and us_date("3/1/94") is None
    assert amount("46905.01") == Decimal("46905.01") and amount("250000") == Decimal(250000)
    assert amount("") is None and amount("x") is None and amount("-5") is None
    assert amount("NaN") is None
    assert zip5("44702-1234") == "44702" and zip5("4470") is None and zip5(None) is None
    assert state_jurisdiction("OH") == "39"
    assert state_jurisdiction("ON") is None and state_jurisdiction("") is None
    assert kept_conclusion(conclusion(), cfg) == date(2020, 3, 24)
    cost_only = conclusion(FED_PENALTY_ASSESSED_AMT="0", COST_RECOVERY_AWARDED_AMT="95000")
    assert kept_conclusion(cost_only, cfg) is not None
    for bad in ({"ACTIVITY_TYPE_CODE": "AFR"}, {"SETTLEMENT_ENTERED_DATE": ""},
                {"FED_PENALTY_ASSESSED_AMT": "0"}, {"FED_PENALTY_ASSESSED_AMT": ""}):  # fmt: skip
        assert kept_conclusion(conclusion(**bad), cfg) is None, bad


def test_case_parties_and_judgment() -> None:
    got = norm([case()])
    (c,) = of(got, "court_case")
    assert c["case_uid"] == "us.epa.icis:05-2019-0001" and c["court_id"] == "us.district"
    assert c["case_number_raw"] == "5:19-cv-00001" and c["case_number_norm"] == "05-2019-0001"
    assert c["nature_of_suit"] == "CAA" and c["status"] == "Closed"
    assert c["jurisdiction"] == "39"  # the facility's state
    (j,) = of(got, "judgment")
    assert j["judgment_uid"] == "us.epa.icis:05-2019-0001:11"
    assert j["entered_on"] == date(2020, 3, 24) and j["principal"] == Decimal(125000)
    assert j["costs"] is None and j["judgment_type"] == "consent"
    p = parties(got)
    assert p["UNITED STATES"][0] == "creditor"
    role, debtor = p["Acme Corp"]
    assert role == "debtor"
    (addr,) = of(got, "address")
    assert debtor["address_id"] == addr["address_id"]  # the only facility of a one-debtor case
    assert addr["line1"] == "1 MAIN ST" and addr["zip5"] == "44702" and addr["state"] == "OH"


def test_facility_address_goes_to_the_debtor_it_names() -> None:
    defendants = [{"DEFENDANT_NAME": n, "NAMED_IN_SETTLEMENT_FLAG": f}
                  for n, f in (("ACME CORP", "Y"), ("BETA LLC", "Y"), ("GAMMA INC", "N"),
                               ("acme corp", "N"), (" ", "Y"))]  # fmt: skip
    facilities = [
        {"FACILITY_NAME": "BETA LLC", "LOCATION_ADDRESS": "9 OAK AVE", "CITY": "X",
         "STATE_CODE": "OH", "ZIP": "44000"},
        {"FACILITY_NAME": "ACME SITE", "LOCATION_ADDRESS": "1 MAIN ST", "CITY": "Y",
         "STATE_CODE": "PA", "ZIP": ""},
        {"FACILITY_NAME": "EMPTY", "LOCATION_ADDRESS": "", "CITY": "", "STATE_CODE": "",
         "ZIP": ""},
    ]  # fmt: skip
    got = norm([case(defendants=defendants, facilities=facilities)])
    p = parties(got)
    assert p["ACME CORP"][0] == "debtor" and p["ACME CORP"][1]["address_id"] is None
    assert p["BETA LLC"][0] == "debtor" and p["BETA LLC"][1]["address_id"] is not None
    assert p["GAMMA INC"] == ("defendant", p["GAMMA INC"][1])
    assert "acme corp" not in p and len(p) == 4  # repeats merge, keeping the debtor role
    assert of(got, "court_case")[0]["jurisdiction"] == "us"  # facilities in two states


def test_debtors_when_no_one_is_flagged_and_when_no_defendants() -> None:
    nobody = [{"DEFENDANT_NAME": "ACME CORP", "NAMED_IN_SETTLEMENT_FLAG": "N"},
              {"DEFENDANT_NAME": "BETA LLC", "NAMED_IN_SETTLEMENT_FLAG": "N"}]  # fmt: skip
    p = parties(norm([case(defendants=nobody)]))
    assert p["ACME CORP"][0] == p["BETA LLC"][0] == "debtor"
    assert p["ACME CORP"][1]["address_id"] is None  # two debtors, one facility: no address
    p = parties(norm([case(defendants=[])]))
    assert p["ACME CORP"][0] == "debtor"  # CASE_NAME without ET AL


def test_judgments_cost_recovery_and_skips() -> None:
    concl = [conclusion(),
             conclusion(ENF_CONCLUSION_ID="12", ENF_CONCLUSION_ACTION_CODE="JOA",
                        FED_PENALTY_ASSESSED_AMT="", COST_RECOVERY_AWARDED_AMT="95000.5"),
             conclusion(ENF_CONCLUSION_ID="13", SETTLEMENT_ENTERED_DATE="01/01/2027"),
             conclusion(ENF_CONCLUSION_ID="14", ACTIVITY_TYPE_CODE="AFR")]  # fmt: skip
    got = norm([case(conclusions=concl),
                case(CASE_NUMBER="05-2019-0002", conclusions=[conclusion(ENF_CONCLUSION_ID="15",
                     FED_PENALTY_ASSESSED_AMT="0")]),  # nothing owed: no case
                case(CASE_NUMBER="05-2019-0003", ACTIVITY_TYPE_CODE="AFR"),
                case(CASE_NUMBER="", ACTIVITY_ID="9")])  # fmt: skip
    js = {j["judgment_uid"].rsplit(":", 1)[1]: j for j in of(got, "judgment")}
    assert set(js) == {"11", "12"}
    assert js["12"]["principal"] is None and js["12"]["costs"] == Decimal("95000.50")
    assert js["12"]["judgment_type"] == "other"
    assert [c["case_number_norm"] for c in of(got, "court_case")] == ["05-2019-0001"]
    no_docket = of(norm([case(dockets=[])]), "court_case")[0]
    assert no_docket["case_number_raw"] == "05-2019-0001"


def write_zip(tables: dict[str, list[dict[str, str]]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, cols in COLUMNS.items():
            out = io.StringIO()
            w = csv.DictWriter(out, fieldnames=[*cols, "EXTRA"], quoting=csv.QUOTE_ALL)
            w.writeheader()
            for r in tables.get(name, []):
                w.writerow({c: r.get(c, "") for c in [*cols, "EXTRA"]})
            zf.writestr(f"{name}.csv", out.getvalue())
    return buf.getvalue()


def sample_zip() -> bytes:
    return write_zip({
        "CASE_ENFORCEMENTS": [
            {"ACTIVITY_ID": "1", "CASE_NUMBER": "05-2019-0001", "CASE_NAME": "ACME",
             "ACTIVITY_TYPE_CODE": "JDC", "EXTRA": "long free text"},
            {"ACTIVITY_ID": "2", "CASE_NUMBER": "05-2019-0002", "ACTIVITY_TYPE_CODE": "AFR"},
            {"ACTIVITY_ID": "3", "CASE_NUMBER": "01-2019-0003", "ACTIVITY_TYPE_CODE": "JDC"},
            {"ACTIVITY_ID": "4", "CASE_NUMBER": "01-2019-0004", "ACTIVITY_TYPE_CODE": "JDC"},
        ],
        "CASE_ENFORCEMENT_CONCLUSIONS": [
            {**conclusion(), "ACTIVITY_ID": "1"},
            {**conclusion(ACTIVITY_TYPE_CODE="AFR"), "ACTIVITY_ID": "2"},
            {**conclusion(ENF_CONCLUSION_ID="31"), "ACTIVITY_ID": "3"},
            {**conclusion(FED_PENALTY_ASSESSED_AMT="0"), "ACTIVITY_ID": "4"},
        ],
        "CASE_DEFENDANTS": [{"ACTIVITY_ID": "1", "DEFENDANT_NAME": "B  CO"},
                            {"ACTIVITY_ID": "1", "DEFENDANT_NAME": "A CO"},
                            {"ACTIVITY_ID": "4", "DEFENDANT_NAME": "C CO"}],
        "CASE_REGIONAL_DOCKETS": [{"ACTIVITY_ID": "1", "REGIONAL_DOCKET_NMBR": "1:19-cv-1"}],
    })  # fmt: skip


def test_kept_cases_reads_the_zip() -> None:
    cases = kept_cases(sample_zip(), load_config())
    assert [c["CASE_NUMBER"] for c in cases] == ["01-2019-0003", "05-2019-0001"]
    acme = cases[1]
    assert "EXTRA" not in acme and "ACTIVITY_ID" not in acme["defendants"][0]
    assert [d["DEFENDANT_NAME"] for d in acme["defendants"]] == ["A CO", "B CO"]
    assert acme["dockets"] == [{"REGIONAL_DOCKET_NMBR": "1:19-cv-1"}] and acme["facilities"] == []


class FakeClient:
    def __init__(self, content: bytes, status: int = 200, page: bytes = b"") -> None:
        self.content, self.status, self.page = content, status, page

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        if url.endswith(".zip"):
            return Response(url, self.status, self.content, "application/zip", AT)
        if self.status == 599:
            raise OSError("down")
        return Response(url, self.status, self.page, "text/html", AT)


def test_fetch_and_health() -> None:
    a = EPAJudicialCases(FakeClient(sample_zip()))  # type: ignore[arg-type]
    f = a.fetch(FetchRequest({}))
    assert f.request == URL and f.retrieved_at == AT
    assert len(json.loads(f.content)["cases"]) == 2
    lim = a.fetch(FetchRequest({"limit": "1"}))
    assert [c["CASE_NUMBER"] for c in json.loads(lim.content)["cases"]] == ["01-2019-0003"]
    assert len(of([(r.table, dict(r.row)) for r in a.normalize(f)], "judgment")) == 2
    with pytest.raises(ValueError, match="HTTP 503"):
        EPAJudicialCases(FakeClient(b"", 503)).fetch(FetchRequest({}))  # type: ignore[arg-type]
    page = b'<a href="https://echo.epa.gov/files/echodownloads/case_downloads.zip">'
    h = EPAJudicialCases(FakeClient(b"", 200, page)).health()  # type: ignore[arg-type]
    assert h.ok and h.shape == ("case_downloads.zip",)
    assert EPAJudicialCases(FakeClient(b"", 200, b"moved")).health().ok is False  # type: ignore[arg-type]
    assert EPAJudicialCases(FakeClient(b"", 599)).health().ok is False  # type: ignore[arg-type]


def test_fixture_normalizes() -> None:
    path = next(FIX.glob("*.json"))
    f = Fetched(EPAJudicialCases.source_id, path.as_uri(), AT, 200, path.read_bytes(), "")
    a = by_source_id(EPAJudicialCases.source_id)()  # type: ignore[abstract]
    rows = [(r.table, dict(r.row)) for r in a.normalize(f)]
    t = Counter(table for table, _ in rows)
    assert t["court_case"] == t["source_record"] > 0 and t["judgment"] >= t["court_case"]
    assert {r["role"] for r in of(rows, "case_party")} >= {"creditor", "debtor"}
    assert t["address"] > 0
    src = a.source_row()
    assert src["access_method"] == "bulk" and src["cost_model"] == "free"
