"""Census batch geocoder pass: request file, response parsing, lake parts, no re-sends."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import duckdb
import pytest

from equity import geocode
from equity.adapters.http import PoliteClient

FIX = Path(__file__).parent / "fixtures" / "geocode" / "census_batch_response.csv"


def test_request_file_strips_commas_and_quotes() -> None:
    body = geocode.request_file([("a1", '4600 Silver Hill Rd, "Bldg 3"', "Washington", "DC",
                                  "20233"), ("a2", None, None, None, None)])  # fmt: skip
    assert body.decode().splitlines() == ["a1,4600 Silver Hill Rd Bldg 3,Washington,DC,20233",
                                          "a2,,,,"]  # fmt: skip


def test_parse_response() -> None:
    got = {g.address_id: g for g in geocode.parse_response(FIX.read_bytes())}
    a1 = got["a1"]
    assert (a1.match, a1.match_type, a1.line1, a1.city, a1.state, a1.zip5) == (
        "Match", "Exact", "4600 SILVER HILL RD", "WASHINGTON", "DC", "20233")  # fmt: skip
    assert a1.lon == pytest.approx(-76.928366) and a1.lat == pytest.approx(38.845056)
    assert (a1.tiger_line_id, a1.side) == ("657091557", "L")
    assert got["a2"].match == "No_Match" and got["a2"].line1 is None
    assert got["a3"].match == "Tie" and got["a3"].lon is None
    assert geocode._matched("NO COMMAS") == (None, None, None, None)
    bad = b'"b1","x","Match","Exact","1 A ST, B, CC, 1234X","not,a-point","",""\n,,\n'
    (b1,) = geocode.parse_response(bad)
    assert (b1.zip5, b1.lon, b1.tiger_line_id) == (None, None, None)


def _lake(tmp_path: Path) -> Path:
    lake = tmp_path / "lake"
    d = lake / "zz.debts" / "address"
    d.mkdir(parents=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE a (address_id VARCHAR, line1 VARCHAR, city VARCHAR, "
                "state VARCHAR, zip5 VARCHAR)")  # fmt: skip
    con.executemany("INSERT INTO a VALUES (?, ?, ?, ?, ?)", [
        ("a1", "4600 Silver Hill Rd", "Washington", "DC", "20233"),
        ("a2", "1 Main St", "Nowhereville", "ZZ", "00000"),
        ("a3", "4600 Silverhill Road", "Suitland", "MD", "20746"),
        ("a4", "", "Nowhere", "DC", "20001"),       # no street: never sent
        ("a5", "9 Elm St", None, None, None),       # no state or ZIP: never sent
    ])  # fmt: skip
    con.execute(f"COPY a TO '{(d / '0.parquet').as_posix()}' (FORMAT parquet)")
    return lake


def test_run_writes_parts_and_never_resends(tmp_path: Path) -> None:
    sent: list[bytes] = []

    def post(url: str, headers: Mapping[str, str], body: bytes, timeout: float
             ) -> tuple[int, bytes, str]:  # fmt: skip
        assert url == geocode.URL
        assert headers["Content-Type"].startswith("multipart/form-data; boundary=")
        sent.append(body)
        return 200, FIX.read_bytes(), "text/csv"

    def get(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        return 404, b"", ""  # no robots.txt

    client = PoliteClient(min_interval_s=0, transport=get, post_transport=post,
                          sleep=lambda s: None)  # fmt: skip
    lake = _lake(tmp_path)
    assert geocode.pending(lake, ["zz.debts", "zz.none"], 10) == [
        ("a1", "4600 Silver Hill Rd", "Washington", "DC", "20233"),
        ("a2", "1 Main St", "Nowhereville", "ZZ", "00000"),
        ("a3", "4600 Silverhill Road", "Suitland", "MD", "20746")]  # fmt: skip
    out = geocode.run(lake, ["zz.debts"], 1, client)
    assert out == {"sent": 3, "parts_written": 1,
                   "by_match": {"Match/Exact": 1, "No_Match": 1, "Tie": 1}}  # fmt: skip
    body = sent[0].decode()
    assert 'name="benchmark"' in body and "Public_AR_Current" in body
    assert 'filename="addresses.csv"' in body and "a1,4600 Silver Hill Rd" in body
    part = lake / geocode.SOURCE_DIR / geocode.TABLE / "00000.parquet"
    rows = duckdb.connect().execute(
        f"SELECT address_id, match, zip5 FROM '{part.as_posix()}'").fetchall()  # fmt: skip
    assert rows == [("a1", "Match", "20233"), ("a2", "No_Match", None), ("a3", "Tie", None)]
    assert geocode.pending(lake, ["zz.debts"], 10) == []
    assert geocode.run(lake, ["zz.debts"], 1, client)["sent"] == 0
    assert len(sent) == 1
    assert geocode.pending(tmp_path / "empty", ["zz.debts"], 10) == []


def test_batch_limits_and_http_errors() -> None:
    def post(url: str, headers: Mapping[str, str], body: bytes, timeout: float
             ) -> tuple[int, bytes, str]:  # fmt: skip
        return 500, b"", ""

    def get(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        return 404, b"", ""

    client = PoliteClient(min_interval_s=0, retries=0, transport=get, post_transport=post,
                          sleep=lambda s: None)  # fmt: skip
    with pytest.raises(ValueError, match="1 to"):
        geocode.geocode_batch(client, [])
    with pytest.raises(RuntimeError, match="HTTP 500"):
        geocode.geocode_batch(client, [("a", "1 A St", "B", "DC", "20001")])
    assert [len(b) for b in geocode.batches(list(range(25)), 10)] == [10, 10, 5]


def test_main_and_debtor_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                 capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    assert "ny.dtf.tax_warrants" in geocode.debtor_sources()
    calls: list[tuple[Path, list[str], int]] = []

    def fake_run(lake: Path, sources: list[str], max_batches: int) -> dict[str, int]:
        calls.append((lake, list(sources), max_batches))
        return {"sent": 0}

    monkeypatch.setattr(geocode, "run", fake_run)
    assert geocode.main(["--lake", str(tmp_path), "--sources", "zz.a", "--max-batches", "2"]) == 0
    assert json.loads(capsys.readouterr().out) == {"sent": 0}
    assert geocode.main(["--lake", str(tmp_path), "--all-debtors"]) == 0
    assert calls[0] == (tmp_path, ["zz.a"], 2) and len(calls[1][1]) > 10


def test_runs_as_a_module(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["geocode", "--sources", "zz.none", "--lake", "/nonexistent"])
    monkeypatch.delitem(sys.modules, "equity.geocode", raising=False)
    with pytest.raises(SystemExit) as done:
        runpy.run_module("equity.geocode", run_name="__main__")
    assert done.value.code == 0
