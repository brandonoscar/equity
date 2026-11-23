"""Citrus County (FL) Clerk civil bulk data export. Offline."""

from __future__ import annotations

import base64
import csv
import io
import json
import re
import zipfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from equity.adapters.base import Fetched, FetchRequest
from equity.adapters.fl.citrus_civil import (
    DOCKET_WORDS,
    CitrusCivil,
    CookieTransport,
    ExportClient,
    case_uid,
    default_client,
    iso_date,
    judgment_type,
    load_config,
    months,
    or_reference,
    party_address,
    party_name,
    unpack_export,
)
from equity.adapters.registry import by_source_id
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 23, tzinfo=UTC)
FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "fl.citrus.civil"
UCN = "092026CC000100XXXAIN"
CASE = {"UniformCaseNumber": UCN, "CaseNumber": "2026 CC 000100 A", "CourtType": "CC",
        "CourtTypeLong": "COUNTY CIVIL", "CaseType": "COUNTY CIVIL $8,001 TO $15,000",
        "FileDate": " 2026-03-02 00:00:00", "DispositionDate": " 2026-10-14 00:00:00",
        "CaseStatus": "CLOSED", "Disposition": "DISPOSED BY DEFAULT"}  # fmt: skip
PARTIES = [
    {"UniformCaseNumber": UCN, "Description": "Plaintiff", "PartyType": "PRIMARY",
     "LastName": "ACME FUNDING LLC", "ActiveAddress": "1 MAIN ST, TAMPA, FL 33602"},
    {"UniformCaseNumber": UCN, "Description": "Defendant", "PartyType": "PRIMARY",
     "LastName": "DOE", "FirstName": "ANN", "MiddleName": "B",
     "ActiveAddress": "2 OAK AVE, INVERNESS, FL 34450"},
    {"UniformCaseNumber": UCN, "Description": "Defendant", "PartyType": "AKA",
     "LastName": "DOE", "FirstName": "ANNIE"},
    {"UniformCaseNumber": UCN, "Description": "Defendant", "PartyType": "PRIMARY",
     "LastName": "DOE", "FirstName": "ANN", "MiddleName": "B"},
    {"UniformCaseNumber": UCN, "Description": "Third Party Defendant", "LastName": "ROE"},
]  # fmt: skip
DOCKETS = [
    {"UniformCaseNumber": UCN, "DocketDate": " 2026-10-14 00:00:00",
     "dockettext": "DEFAULT FINAL JUDGMENT E - RECORDED (OR.3725.1856. / 2026069564)"},
    {"UniformCaseNumber": UCN, "DocketDate": " 2026-10-14 00:00:00",
     "dockettext": "DEFAULT FINAL JUDGMENT E - RECORDED (OR.3725.1856. / 2026069564)"},
    {"UniformCaseNumber": UCN, "DocketDate": " 2026-09-01 00:00:00",
     "dockettext": "MOTION FOR DEFAULT FINAL JUDGMENT"},
    {"UniformCaseNumber": UCN, "DocketDate": " 2027-01-01 00:00:00",
     "dockettext": "FINAL JUDGMENT E - RECORDED"},
]  # fmt: skip


def _fetched(cases: list[dict[str, str]], parties: list[dict[str, str]],
             dockets: list[dict[str, str]]) -> Fetched:  # fmt: skip
    body = canonical_json({"from": "2026-10-01", "to": "2026-10-31", "cases": cases,
                           "parties": parties, "dockets": dockets})  # fmt: skip
    return Fetched(CitrusCivil.source_id, "https://x.test/x", AT, 200, body, "")


def _norm(f: Fetched) -> list[tuple[str, dict[str, Any]]]:
    return [(r.table, dict(r.row)) for r in CitrusCivil(client=ExportClient()).normalize(f)]


def _of(out: list[tuple[str, dict[str, Any]]], table: str) -> list[dict[str, Any]]:
    return [r for t, r in out if t == table]


def test_helpers() -> None:
    assert iso_date(" 2026-11-16 00:00:00") == date(2026, 11, 16)
    assert iso_date("") is None and iso_date("11/16/2026") is None
    assert case_uid(" 092026cc000100xxxain ") == "fl.citrus:092026CC000100XXXAIN"
    assert party_name({"FirstName": "ANN", "MiddleName": " B ", "LastName": "DOE",
                       "SuffixName": "JR"}) == "ANN B DOE JR"  # fmt: skip
    assert party_name({"LastName": "ACME  LLC"}) == "ACME LLC"
    addr = party_address("2 OAK AVE, INVERNESS, FL 34450")
    assert addr is not None and addr["zip5"] == "34450" and addr["city"] == "INVERNESS"
    assert party_address("  ") is None
    assert or_reference("X E - RECORDED (OR.3725.1924. / 2026069580)") == (
        "OR 3725/1924 instrument 2026069580"
    )
    assert or_reference("FINAL JUDGMENT") is None
    assert list(months(date(2026, 1, 15), date(2026, 3, 9))) == [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 9)),
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("DEFAULT FINAL JUDGMENT E - RECORDED (OR.3725.1856. / 2026069564)", "default"),
        ("FINAL JUDGMENT E - Recorded (OR.1.2. / 3)", "other"),
        ("FINAL JUDGMENT OF FORECLOSURE E - RECORDED", "other"),
        ("CONSENT FINAL JUDGMENT E - RECORDED", "consent"),
        ("FINAL DEFICIENCY JUDGMENT E - Recorded", "deficiency"),
        ("FINAL JUDGMENT E", "other"),
        ("MOTION FOR DEFAULT FINAL JUDGMENT", None),
        ("FINAL JUDGMENT FOR POSSESSION E - RECORDED", None),
        ("FINAL JUDGMENT - EVICTION E - RECORDED", None),
        ("SATISFACTION OF FINAL JUDGMENT", None),
        ("MOTION NOTICE AND JUDGMENT OF DISMISSAL E - Recorded", None),
        ("RETURNED MAIL- FINAL JUDGMENT 9/15/15", None),
        ("JUDGE THOMAS, AMBER: ASSIGNED", None),
        ("FINAL JUDGMENT", None),
    ],
)
def test_judgment_type(text: str, expected: str | None) -> None:
    assert judgment_type(load_config(), text) == expected


def test_normalize_case_parties_judgments() -> None:
    out = _norm(_fetched([CASE], PARTIES, DOCKETS))
    case = _of(out, "court_case")[0]
    uid = "fl.citrus:" + UCN
    assert case["case_uid"] == uid and case["court_id"] == "fl.5th_circuit.citrus.civil"
    assert case["filed_on"] == date(2026, 3, 2) and case["closed_on"] == date(2026, 10, 14)
    assert case["status"] == "CLOSED - DISPOSED BY DEFAULT"
    assert case["nature_of_suit"] == "COUNTY CIVIL $8,001 TO $15,000"
    names = {p["party_id"]: p["raw_name"] for p in _of(out, "party")}
    roles = sorted((names[c["party_id"]], c["role"]) for c in _of(out, "case_party"))
    assert roles == [("ACME FUNDING LLC", "plaintiff"), ("ANN B DOE", "defendant"),
                     ("ANNIE DOE", "defendant"), ("ROE", "other")]  # fmt: skip
    debtor = next(p for p in _of(out, "party") if p["raw_name"] == "ANN B DOE")
    addr = {a["address_id"]: a for a in _of(out, "address")}[debtor["address_id"]]
    assert addr["zip5"] == "34450"
    # One judgment: the repeated docket line collapses; the motion and the future-dated
    # line do not count, and the default disposition adds nothing when the docket has one.
    (j,) = _of(out, "judgment")
    assert j["entered_on"] == date(2026, 10, 14) and j["judgment_type"] == "default"
    assert j["principal"] is None and j["judgment_uid"].startswith(uid + ":2026-10-14:default:")
    assert len(_of(out, "docket_entry")) == 2


def test_disposition_fallback_and_open_cases() -> None:
    open_case = {**CASE, "UniformCaseNumber": "X1", "CaseStatus": "REOP",
                 "FileDate": " 2027-02-01 00:00:00"}  # fmt: skip
    judge = {**CASE, "UniformCaseNumber": "X2", "Disposition": "DISPOSED BY JUDGE"}
    out = _norm(_fetched([CASE, open_case, judge, {"CaseNumber": "no ucn"}], [], []))
    by_case = {j["case_uid"]: j for j in _of(out, "judgment")}
    assert set(by_case) == {"fl.citrus:" + UCN, "fl.citrus:X1"}
    assert by_case["fl.citrus:" + UCN]["judgment_uid"].endswith(":default:disposition")
    cases = {c["case_uid"]: c for c in _of(out, "court_case")}
    assert cases["fl.citrus:X1"]["closed_on"] is None and cases["fl.citrus:X1"]["filed_on"] is None
    # A disposition before the file date is not a closing date.
    early = {**CASE, "UniformCaseNumber": "X3", "FileDate": " 2026-11-01 00:00:00"}
    (c,) = _of(_norm(_fetched([early], [], [])), "court_case")
    assert c["closed_on"] is None and c["filed_on"] == date(2026, 11, 1)


def _csv(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO()
    fields = sorted({k for r in rows for k in r})
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\r\n")
    w.writeheader()
    w.writerows(rows)
    return ("﻿" + buf.getvalue()).encode()


def _zip(dob: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("export_Case.csv", _csv([CASE]))
        party_rows = [{**p, "DOB": "1990-01-01", "Race": "W", "DLNo": "D123"} if dob else p
                      for p in PARTIES]  # fmt: skip
        party_rows.append({"UniformCaseNumber": UCN, "Description": "Attorney",
                           "LastName": "LAWYER", "BarNumber": "1"})  # fmt: skip
        z.writestr("export_Party.csv", _csv(party_rows))
        z.writestr("export_Docket.csv", _csv([*DOCKETS, {"UniformCaseNumber": UCN,
                   "DocketDate": " 2026-01-01 00:00:00", "dockettext": "ANSWER"}]))  # fmt: skip
    return buf.getvalue()


def test_unpack_drops_sensitive_columns_attorneys_and_other_docket_rows() -> None:
    data = unpack_export(_zip(), load_config().docket_keep)
    assert len(data["cases"]) == 1 and data["cases"][0]["FileDate"] == "2026-03-02 00:00:00"
    assert all(not {"DOB", "Race", "DLNo", "BarNumber"} & set(p) for p in data["parties"])
    assert all(p["Description"] != "Attorney" for p in data["parties"])
    assert len(data["parties"]) == len(PARTIES)
    assert [d["dockettext"] for d in data["dockets"]].count("ANSWER") == 0
    empty = io.BytesIO()
    zipfile.ZipFile(empty, "w").close()
    assert unpack_export(empty.getvalue(), load_config().docket_keep) == {
        "cases": [],
        "parties": [],
        "dockets": [],
    }


PAGE = ('<html><head><meta name="csrf-token" content="tok123"></head><body>'
        '<div wire:snapshot="{&quot;data&quot;:{}}" wire:id="a"></div></body></html>')  # fmt: skip


class FakeTransport:
    def __init__(self, answer: Mapping[str, Any] | None, page: str = PAGE) -> None:
        self.answer, self.page = answer, page
        self.posts: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        if url.endswith("/robots.txt"):
            return 404, b"", "text/html"
        return 200, self.page.encode(), "text/html"

    def post(
        self, url: str, headers: Mapping[str, str], body: bytes, timeout: float
    ) -> tuple[int, bytes, str]:
        self.posts.append((url, dict(headers), json.loads(body)))
        if self.answer is None:
            return 500, b"", "text/html"
        return 200, json.dumps(self.answer).encode(), "application/json"


def _client(t: FakeTransport) -> ExportClient:
    return ExportClient(min_interval_s=0, retries=0, transport=t.get, post_transport=t.post,
                        sleep=lambda _s: None, now=lambda: AT)  # fmt: skip


def _answer(zip_bytes: bytes) -> dict[str, Any]:
    content = base64.b64encode(zip_bytes).decode()
    return {"components": [{"effects": {"download": {"name": "export.zip",
                                                     "content": content}}}]}  # fmt: skip


def test_fetch_posts_the_livewire_form_and_keeps_the_zip_tables() -> None:
    t = FakeTransport(_answer(_zip()))
    adapter = CitrusCivil(client=_client(t))
    f = adapter.fetch(FetchRequest({"from": "2026-10-01", "to": "2026-10-31", "limit": "1"}))
    url, headers, payload = t.posts[0]
    assert url == "https://apps.citrusclerk.org/BulkDataExport/livewire/update"
    assert headers["X-CSRF-TOKEN"] == "tok123" and headers["Content-Type"] == "application/json"
    comp = payload["components"][0]
    assert payload["_token"] == "tok123" and comp["snapshot"]  # noqa: S105 - test token == '{"data":{}}'
    assert comp["updates"]["form.start_date"] == "2026-10-01"
    assert comp["updates"]["form.selected_court_types"] == ["CA", "CAM", "CC", "SC"]
    assert comp["calls"][0]["method"] == "submitForm"
    data = json.loads(f.content)
    assert data["from"] == "2026-10-01" and len(data["cases"]) == 1
    assert f.request.endswith("?dispositions=2026-10-01..2026-10-31")
    assert _of(_norm(f), "judgment")
    with pytest.raises(ValueError, match="1 day to 1 year"):
        adapter.fetch(FetchRequest({"from": "2026-10-31", "to": "2026-10-01"}))


def test_fetch_errors() -> None:
    req = FetchRequest({"from": "2026-10-01", "to": "2026-10-31"})
    with pytest.raises(RuntimeError, match="HTTP 500"):
        CitrusCivil(client=_client(FakeTransport(None))).fetch(req)
    with pytest.raises(RuntimeError, match="form changed"):
        CitrusCivil(client=_client(FakeTransport(None, page="<html></html>"))).fetch(req)
    no_file = {"components": [{"effects": {"html": "<div></div>"}}]}
    with pytest.raises(RuntimeError, match="no export"):
        CitrusCivil(client=_client(FakeTransport(no_file))).fetch(req)


def test_health_and_partitions() -> None:
    good = CitrusCivil(client=_client(FakeTransport(_answer(_zip()))))
    report = good.health()
    assert report.ok and report.detail == "1 cases" and "UniformCaseNumber" in report.shape
    bad = CitrusCivil(client=_client(FakeTransport(None)))
    assert not bad.health().ok
    empty = io.BytesIO()
    zipfile.ZipFile(empty, "w").close()
    assert not CitrusCivil(client=_client(FakeTransport(_answer(empty.getvalue())))).health().ok
    parts = list(good.partitions())
    assert parts[0] == {"from": "2026-11-01", "to": "2026-11-22"}
    assert parts[-1] == {"from": "2006-01-01", "to": "2006-01-31"}


def test_cookie_transport_and_default_client(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    class Resp:
        status = 200
        headers: Mapping[str, str] = {"Content-Type": "text/plain"}

        def read(self) -> bytes:
            return b"ok"

        def __enter__(self) -> Resp:
            return self

        def __exit__(self, *a: object) -> None:
            return None

    seen: list[Any] = []

    class Opener:
        def open(self, req: Any, timeout: float) -> Resp:
            seen.append(req)
            if req.data == b"fail":
                raise urllib.error.HTTPError(req.full_url, 419, "x", {}, io.BytesIO(b"no"))  # type: ignore[arg-type]
            return Resp()

    monkeypatch.setattr("urllib.request.build_opener", lambda *_a: Opener())
    t = CookieTransport()
    assert t.get("https://x.test/", {"User-Agent": "u"}, 5) == (200, b"ok", "text/plain")
    assert t.post("https://x.test/", {"Content-Type": "application/json"}, b"{}", 5)[0] == 200
    assert t.post("https://x.test/", {}, b"fail", 5)[:2] == (419, b"no")
    assert seen[1].get_header("Content-type") == "application/json"
    assert isinstance(default_client(), ExportClient)


def test_fixture_is_registered_and_scrubbed() -> None:
    assert by_source_id("fl.citrus.civil") is CitrusCivil
    paths = sorted(FIX.glob("*.json"))
    assert paths
    for path in paths:
        data = json.loads(path.read_text())
        for p in data["parties"]:
            assert all(not {"DOB", "Race", "DLNo", "Gender"} & set(p) for p in data["parties"])
            for col in ("LastName", "FirstName", "MiddleName", "ActiveAddress"):
                v = p.get(col, "")
                assert not v or v.startswith("TESTOWNER") or v.endswith(" TEST ST"), col
        for d in data["dockets"]:
            for w in d["dockettext"].split():
                assert (w == "TESTOWNER" or not re.search(r"[A-Za-z]", w)
                        or re.fullmatch(r"\(OR\.[\d.]+", w)
                        or w.upper().strip(",.()/-:'") in DOCKET_WORDS), w  # fmt: skip


def test_scrub_fixture() -> None:
    text = "FINAL JUDGMENT AGAINST ANN DOE E - RECORDED (OR.1.2. / 3)"
    raw = _fetched([CASE], PARTIES, [{**DOCKETS[0], "dockettext": text}]).content
    data = json.loads(CitrusCivil.scrub_fixture(raw))
    assert data["parties"][1]["LastName"].startswith("TESTOWNER")
    assert data["parties"][1]["ActiveAddress"].endswith(" TEST ST")
    assert data["dockets"][0]["dockettext"] == (
        "FINAL JUDGMENT AGAINST TESTOWNER TESTOWNER E - RECORDED (OR.1.2. / 3)"
    )
