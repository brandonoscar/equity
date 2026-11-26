"""Review pairs labelled by Census-standardized addresses: same segment, same ZIP, units."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from pathlib import Path

import duckdb
import pytest

from equity.adapters.http import PoliteClient
from equity.matching import review_geo as rg

Q = ("debtor_party_id, debtor_name, debtor_line1, debtor_zip, owner_party_id, owner_name, "
     "mail_line1, mail_zip, situs_line1, situs_zip, parcel_uid, category")  # fmt: skip
PAIRS = [
    # same house, the lien spelled it differently and used another ZIP on the same segment
    ("d1", "ANN LEE", "4600 Silverhill Road", "20746", "o1", "ANN LEE",
     "4600 SILVER HILL RD", "20233", None, None, "p1", "different"),
    # different house
    ("d2", "BO RAY", "12 Oak St", "11111", "o2", "BO RAY", "99 Elm St", "11111", None, None,
     "p2", "same_number"),
    # same house but an apartment: multi-unit
    ("d3", "CY DU", "7 Pine Ave Apt 4", "22222", "o3", "CY DU", None, None, "7 PINE AVE",
     "22222", "p3", "different"),
    # the debtor's address never geocoded
    ("d4", "DE EF", "Nowhere", "33333", "o4", "DE EF", "1 X ST", "33333", None, None, "p4",
     "different"),
]  # fmt: skip
# Census answers keyed by street: (match, std line1, zip, tiger, side)
ANSWERS = {
    "4600 SILVERHILL ROAD": ("Match", "4600 SILVER HILL RD", "20746", "657091557", "L"),
    "4600 SILVER HILL RD": ("Match", "4600 SILVER HILL RD", "20233", "657091557", "L"),
    "12 OAK ST": ("Match", "12 OAK ST", "11111", "1", "R"),
    "99 ELM ST": ("Match", "99 ELM ST", "11111", "2", "R"),
    "7 PINE AVE APT 4": ("Match", "7 PINE AVE", "22222", "3", "L"),
    "7 PINE AVE": ("Match", "7 PINE AVE", "22222", "3", "L"),
}


def _derived(tmp_path: Path) -> Path:
    d = tmp_path / "derived" / "ny"
    d.mkdir(parents=True)
    con = duckdb.connect()
    cols = ", ".join(f"{c.strip()} VARCHAR" for c in Q.split(","))
    con.execute(f"CREATE TABLE q ({cols})")
    con.executemany(f"INSERT INTO q VALUES ({', '.join('?' * 12)})", PAIRS)
    con.execute(f"COPY q TO '{(d / 'review_queue.parquet').as_posix()}' (FORMAT parquet)")
    return tmp_path / "derived"


def _client(calls: list[int]) -> PoliteClient:
    def post(url: str, headers: Mapping[str, str], body: bytes, timeout: float
             ) -> tuple[int, bytes, str]:  # fmt: skip
        calls.append(1)
        text = body.decode()
        start = text.index("\r\n\r\n", text.index('filename="addresses.csv"')) + 4
        rows = csv.reader(text[start : text.index("\r\n--", start)].splitlines())
        out = []
        for key, line1, _c, _s, z in rows:
            hit = ANSWERS.get(" ".join(line1.upper().split()))
            if hit is None:
                out.append(f'"{key}","{line1}, , , {z}","No_Match"')
            else:
                m, std, zz, tiger, side = hit
                out.append(f'"{key}","{line1}, , , {z}","{m}","Exact","{std}, CITY, ST, {zz}",'
                           f'"-1.0,2.0","{tiger}","{side}"')  # fmt: skip
        return 200, "\n".join(out).encode(), "text/csv"

    def get(url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        return 404, b"", ""

    return PoliteClient(min_interval_s=0, transport=get, post_transport=post, sleep=lambda s: None)


def test_geocode_then_label(tmp_path: Path) -> None:
    derived = _derived(tmp_path)
    calls: list[int] = []
    got = rg.geocode_queue(derived, "ny", 5, _client(calls))
    assert got == {"to_geocode": 8, "sent": 8, "left": 0} and len(calls) == 1
    assert rg.geocode_queue(derived, "ny", 5, _client(calls))["to_geocode"] == 0  # cached
    s = rg.label(derived, "ny")
    assert s == {"state": "ny", "review_debtors": 4, "debtor_address_geocoded": 3,
                 "same_segment": 2, "same_segment_single_unit": 1,
                 "same_segment_multi_unit": 1, "same_zip": 1,
                 "same_segment_by_category": {"different": 2, "same_number": 0}}  # fmt: skip
    sample = (derived / "ny" / "review_geo_sample.csv").read_text().splitlines()
    assert len(sample) == 3 and "4600 Silverhill Road" in sample[1] and "Apt 4" in sample[2]
    assert json.loads((derived / "ny" / "review_geo_summary.json").read_text()) == s
    assert rg.addr_key(" 4600  silver hill rd ", "20233-1") == rg.addr_key("4600 SILVER HILL RD",
                                                                            "20233")  # fmt: skip


def test_errors_and_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                        capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    with pytest.raises(FileNotFoundError, match="no review queue"):
        rg.geocode_queue(tmp_path, "zz", 1)
    derived = _derived(tmp_path)
    rg.geocode_queue(derived, "ny", 1, _client([]))
    assert rg.main(["--state", "NY", "--derived", str(derived), "--label-only"]) == 0
    assert json.loads(capsys.readouterr().out)["labels"]["same_segment"] == 2
    monkeypatch.setattr(rg, "geocode_queue", lambda d, s, n: {"sent": 0})
    assert rg.main(["--state", "ny", "--derived", str(derived)]) == 0
    assert json.loads(capsys.readouterr().out)["geocode"] == {"sent": 0}
    with pytest.raises(SystemExit):
        rg.main(["--state", "../x", "--derived", str(derived)])


def test_batches_append_to_the_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    derived = _derived(tmp_path)
    monkeypatch.setattr(rg, "BATCH", 3)
    calls: list[int] = []
    assert rg.geocode_queue(derived, "ny", 2, _client(calls)) == {
        "to_geocode": 8, "sent": 6, "left": 2}  # fmt: skip
    assert rg.geocode_queue(derived, "ny", 2, _client(calls)) == {
        "to_geocode": 2, "sent": 2, "left": 0}  # fmt: skip
    assert len(calls) == 3 and len(rg._cached(derived)) == 8


def test_runs_as_a_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    import sys

    derived = _derived(tmp_path)
    rg.geocode_queue(derived, "ny", 1, _client([]))
    monkeypatch.setattr(sys, "argv", ["review_geo", "--state", "ny", "--derived", str(derived),
                                      "--label-only"])  # fmt: skip
    monkeypatch.delitem(sys.modules, "equity.matching.review_geo", raising=False)
    with pytest.raises(SystemExit) as done:
        runpy.run_module("equity.matching.review_geo", run_name="__main__")
    assert done.value.code == 0
