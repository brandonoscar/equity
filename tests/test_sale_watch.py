"""Sale watch: matched parcels on sale lists and foreclosure filings; changes between runs."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pytest

from equity.matching import changes, sale_watch

V = "VARCHAR"


def _write(path: Path, cols: dict[str, str], rows: list[tuple[Any, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE t ({', '.join(f'{c} {t}' for c, t in cols.items())})")
    if rows:
        con.executemany(f"INSERT INTO t VALUES ({', '.join('?' * len(cols))})", rows)
    con.execute(f"COPY t TO '{path.as_posix()}' (FORMAT parquet)")


def _config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "refresh.yaml").write_text(
        "rules:\n"
        "  - match: [zz.county.tax_sale, zz.other.empty]\n    every_hours: 24\n    mode: listing\n"
        "    listing_table: instrument\n"
        "  - match: [zz.state.delinquent]\n    every_hours: 24\n    mode: listing\n"
        "    listing_table: tax_delinquency_snapshot\n")  # fmt: skip
    (cfg / "debt_kinds.yaml").write_text(
        "kinds: {foreclosure: x}\nsources:\n  zz.county.foreclosures: foreclosure\n"
        "  zz.county.liens: tax_lien\n")  # fmt: skip
    return cfg


INST = {"instrument_uid": V, "recorded_on": "DATE", "principal_amount": "DOUBLE",
        "doc_type_raw": V, "superseded_at": "TIMESTAMP"}  # fmt: skip
LOT = {"instrument_uid": V, "parcel_uid": V}


def _lake(tmp_path: Path) -> tuple[Path, Path]:
    lake, derived = tmp_path / "lake", tmp_path / "derived"
    sale = lake / "zz.county.tax_sale"
    _write(
        sale / "instrument" / "0.parquet",
        INST,
        [
            ("s1", date(2026, 10, 1), 500.0, "Tax sale", None),
            ("s2", date(2026, 10, 1), 9.0, "Tax sale", "2026-10-02 00:00:00"),
        ],
    )  # superseded
    _write(sale / "instrument_parcel" / "0.parquet", LOT, [("s1", "p1"), ("s2", "p2")])
    fc = lake / "zz.county.foreclosures"
    _write(
        fc / "instrument" / "0.parquet",
        INST,
        [("f1", date(2024, 3, 5), None, "Mortgage foreclosure filing", None)],
    )
    _write(fc / "instrument_parcel" / "0.parquet", LOT, [("f1", "p2")])
    _write(lake / "zz.state.delinquent" / "tax_delinquency_snapshot" / "0.parquet",
           {"parcel_uid": V, "certificate_no": V, "observed_on": "DATE", "status_raw": V,
            "superseded_at": "TIMESTAMP"},
           [("p3", "C9", date(2026, 9, 1), "Certified", None)])  # fmt: skip
    (lake / "zz.county.liens" / "instrument").mkdir(parents=True)  # not an event source
    (lake / "zz.other.empty").mkdir(parents=True)
    (lake / "zz.county.tax_sale_copy").mkdir()
    out = derived / "zz"
    _write(out / "matches.parquet",
           {"debtor_party_id": V, "owner_party_id": V, "parcel_uid": V, "decision": V},
           [("d1", "o1", "p1", "auto"), ("d2", "o2", "p2", "auto"), ("d3", "o3", "p3", "auto"),
            ("d4", "o4", "p4", "review")])  # fmt: skip
    _write(
        out / "debtor_summary.parquet",
        {"debtor_party_id": V, "debtor_name": V, "open_amount": "DOUBLE"},
        [("d1", "ANN LEE", 100.0), ("d2", "BO RAY", 20.0), ("d3", "CY DU", None)],
    )
    return lake, derived


def test_event_sources(tmp_path: Path) -> None:
    lake, _ = _lake(tmp_path)
    assert sale_watch.event_sources(lake, _config(tmp_path)) == {
        "zz.county.foreclosures": "foreclosure", "zz.county.tax_sale": "listing",
        "zz.other.empty": "listing", "zz.state.delinquent": "listing"}  # fmt: skip
    assert sale_watch.event_sources(tmp_path / "none", _config(tmp_path / "x")) == {}


def test_sale_watch(tmp_path: Path) -> None:
    lake, derived = _lake(tmp_path)
    hist = tmp_path / "hist.parquet"
    _write(hist, {"source_id": V, "listing_key": V, "first_seen": "DATE", "last_seen": "DATE",
                  "on_latest": "BOOLEAN"},
           [("zz.county.tax_sale", "s1", date(2026, 9, 1), date(2026, 10, 1), True)])  # fmt: skip
    got = sale_watch.build(lake, derived, "zz", hist, _config(tmp_path))
    assert got["parcels_hit"] == 3 and got["events"] == 3
    assert got["by_source"] == {"zz.county.foreclosures": 1, "zz.county.tax_sale": 1,
                                "zz.state.delinquent": 1}  # fmt: skip
    assert got["debtor_open_amount"] == 120.0
    rows = duckdb.connect().execute(
        "SELECT parcel_uid, event_kind, event_amount, first_seen IS NOT NULL FROM "
        f"'{(derived / 'zz' / 'sale_watch.parquet').as_posix()}'").fetchall()  # fmt: skip
    assert rows == [("p1", "listing", 500.0, True), ("p3", "listing", None, False),
                    ("p2", "foreclosure", None, False)]  # newest first  # fmt: skip
    assert (derived / "zz" / "sale_watch.csv").read_text().startswith("parcel_uid,")


def test_sale_watch_without_sources_or_matches(tmp_path: Path) -> None:
    lake, derived = _lake(tmp_path)
    got = sale_watch.build(tmp_path / "nolake", derived, "zz", tmp_path / "no.parquet",
                           _config(tmp_path))  # fmt: skip
    assert got["events"] == 0 and got["by_source"] == {}
    with pytest.raises(FileNotFoundError, match="resolve first"):
        sale_watch.build(lake, tmp_path / "nothing", "zz")


LEADS = {"owner_name": V, "parcels": "VARCHAR[]", "open_amount": "DOUBLE"}


def test_changes_between_runs(tmp_path: Path) -> None:
    lake, derived = _lake(tmp_path)
    out = derived / "zz"
    _write(
        out / "commercial_leads.parquet",
        LEADS,
        [("ACME LLC", ["p1"], 100.0), ("BETA CORP", ["p2"], 50.0)],
    )
    sale_watch.build(lake, derived, "zz", tmp_path / "no.parquet", _config(tmp_path))
    first = changes.diff(derived, "zz", date(2026, 11, 1))
    assert first["first_run"] and first["compared_with"] is None
    assert set(first["changes"].values()) == {0}
    _write(out / "commercial_leads.parquet", LEADS,
           [("ACME LLC", ["p1", "p9"], 160.0), ("BETA CORP", ["p2"], 50.0),
            ("GAMMA INC", ["p7"], 5.0)])  # fmt: skip
    _write(
        lake / "zz.county.tax_sale" / "instrument" / "1.parquet",
        INST,
        [("s3", date(2026, 11, 2), 75.0, "Tax sale", None)],
    )
    _write(lake / "zz.county.tax_sale" / "instrument_parcel" / "1.parquet", LOT, [("s3", "p2")])
    sale_watch.build(lake, derived, "zz", tmp_path / "no.parquet", _config(tmp_path))
    second = changes.diff(derived, "zz", date(2026, 11, 2))
    assert second["compared_with"] == "2026-11-01" and "first_run" not in second
    assert second["changes"] == {"new_owner": 1, "open_amount_up": 1, "new_parcel": 1,
                                 "new_sale_event": 1}  # fmt: skip
    rows = duckdb.connect().execute(
        f"SELECT change, subject, parcel_uid, before, after FROM "
        f"'{(out / 'changes.parquet').as_posix()}'").fetchall()  # fmt: skip
    assert rows[:3] == [("new_owner", "GAMMA INC", None, None, 5.0),
                        ("open_amount_up", "ACME LLC", None, 100.0, 160.0),
                        ("new_parcel", "ACME LLC", "p9", None, 160.0)]  # fmt: skip
    assert rows[3][:3] == ("new_sale_event", "BO RAY", "p2")
    assert json.loads((out / "changes_summary.json").read_text()) == second
    again = changes.diff(derived, "zz", date(2026, 11, 2))  # same day: compared with Nov 1
    assert again["compared_with"] == "2026-11-01"


def test_changes_with_one_tracked_file_and_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "derived" / "yy"
    _write(out / "commercial_leads.parquet", LEADS, [("ACME LLC", ["p1"], 1.0)])
    (out / "history" / "notes").mkdir(parents=True)  # ignored: not a date
    changes.diff(tmp_path / "derived", "yy", date(2026, 1, 1))
    got = changes.diff(tmp_path / "derived", "yy", date(2026, 1, 2))
    assert got["changes"]["new_sale_event"] == 0
    (out / "commercial_leads.parquet").unlink()
    _write(out / "sale_watch.parquet", {"parcel_uid": V, "source_id": V, "listing_key": V,
                                        "event_date": "DATE", "status": V,
                                        "example_debtor_name": V}, [])  # fmt: skip
    assert changes.diff(tmp_path / "derived", "yy", date(2026, 1, 3))["changes"]["new_owner"] == 0
    with pytest.raises(FileNotFoundError, match="no commercial"):
        changes.diff(tmp_path / "derived", "none")
    assert changes.main(["--state", "yy", "--derived", str(tmp_path / "derived")]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "YY"
    with pytest.raises(SystemExit):
        changes.main(["--state", "../x"])


def test_clis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
              capsys: pytest.CaptureFixture[str]) -> None:  # fmt: skip
    import runpy
    import sys

    lake, derived = _lake(tmp_path)
    monkeypatch.setattr(sale_watch, "HISTORY", tmp_path / "no.parquet")
    assert sale_watch.main(["--state", "zz", "--lake", str(lake), "--derived", str(derived)]) == 0
    assert "parcels_hit" in json.loads(capsys.readouterr().out)
    with pytest.raises(SystemExit):
        sale_watch.main(["--state", "../x"])
    for mod, argv in (("equity.matching.sale_watch", ["--state", "zz", "--lake", str(lake),
                                                      "--derived", str(derived)]),
                      ("equity.matching.changes", ["--state", "zz", "--derived",
                                                   str(derived)])):  # fmt: skip
        monkeypatch.setattr(sys, "argv", ["x", *argv])
        monkeypatch.delitem(sys.modules, mod, raising=False)
        with pytest.raises(SystemExit) as done:
            runpy.run_module(mod, run_name="__main__")
        assert done.value.code == 0
