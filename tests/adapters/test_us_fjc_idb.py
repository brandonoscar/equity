"""FJC Integrated Database civil money judgments (CourtListener bulk CSV). Offline."""

from __future__ import annotations

import bz2
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
from equity.adapters.federal.fjc_idb import (
    FJCCivilJudgments,
    case_uid,
    county_fips,
    iso_date,
    kept,
    list_bucket,
    load_config,
    principal,
    read_csv_rows,
    snapshot_date,
    strip_et_al,
)
from equity.adapters.http import Response
from equity.adapters.registry import by_source_id
from equity.adapters.rows import canonical_json

AT = datetime(2026, 11, 22, tzinfo=UTC)
FIX = Path(__file__).parents[1] / "fixtures" / "adapters" / "us.fjc.idb.civil_judgments"
BUCKET = "https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/"
KEY = "bulk-data/fjc-integrated-database-2026-09-30.csv.bz2"
COLUMNS = [
    "id",
    "date_created",
    "date_modified",
    "dataset_source",
    "office",
    "docket_number",
    "origin",
    "date_filed",
    "jurisdiction",
    "nature_of_suit",
    "title",
    "section",
    "subsection",
    "diversity_of_residence",
    "class_action",
    "monetary_demand",
    "county_of_residence",
    "arbitration_at_filing",
    "arbitration_at_termination",
    "multidistrict_litigation_docket_number",
    "plaintiff",
    "defendant",
    "date_transfer",
    "transfer_office",
    "transfer_docket_number",
    "transfer_origin",
    "date_terminated",
    "termination_class_action_status",
    "procedural_progress",
    "disposition",
    "nature_of_judgement",
    "amount_received",
    "judgment",
    "pro_se",
    "year_of_tape",
    "nature_of_offense",
    "version",
    "circuit_id",
    "district_id",
]


def row(**kw: str) -> dict[str, str]:
    base = {c: "" for c in COLUMNS}
    base.update(id="100", office="2", docket_number="8907217", date_filed="1989-10-05",
                nature_of_suit="190", county_of_residence="42017", plaintiff="ACME CO., INC.",
                defendant="DOE, JOHN", date_terminated="1989-11-15", nature_of_judgement="1",
                amount_received="75", judgment="1", circuit_id="ca3",
                district_id="paed")  # fmt: skip
    base.update(kw)
    return base


def csv_text(rows: list[dict[str, str]]) -> str:
    """IDB-style CSV: every field quoted, quotes escaped with a backslash."""
    buf = io.StringIO()
    w = csv.writer(buf, escapechar="\\", doublequote=False, lineterminator="\n",
                   quoting=csv.QUOTE_ALL)  # fmt: skip
    w.writerow(COLUMNS)
    for r in rows:
        w.writerow([r[c] for c in COLUMNS])
    return buf.getvalue()


def norm(rows: list[dict[str, str]]) -> list[tuple[str, dict[str, Any]]]:
    body = canonical_json({"key": KEY, "year": 1989, "rows": rows})
    f = Fetched(FJCCivilJudgments.source_id, BUCKET + KEY, AT, 200, body, "")
    return [(r.table, dict(r.row)) for r in FJCCivilJudgments().normalize(f)]


def of(rows: list[tuple[str, dict[str, Any]]], table: str) -> list[dict[str, Any]]:
    return [r for t, r in rows if t == table]


def test_helpers() -> None:
    assert iso_date("1987-08-14") == date(1987, 8, 14)
    assert iso_date("9100103") is None and iso_date("1987-02-30") is None
    assert iso_date("") is None and iso_date(None) is None
    assert strip_et_al("USA, ET AL") == "USA"
    assert strip_et_al("ALMO MUSIC CORP., ET AL.") == "ALMO MUSIC CORP."
    assert strip_et_al("ACME CO ETAL") == "ACME CO"
    assert strip_et_al("ROE, ET. AL.") == "ROE"
    assert strip_et_al("DOE, ET ALS") == "DOE"
    assert strip_et_al("CITY OF X, ET AL.  \\") == "CITY OF X"
    assert strip_et_al("INTERNATIONAL BROTHERHOOD, ET") == "INTERNATIONAL BROTHERHOOD"
    assert strip_et_al("SHEET METAL WORKERS") == "SHEET METAL WORKERS"
    assert strip_et_al("BETA LLC") == "BETA LLC"
    assert county_fips("42017") == "42017" and county_fips("6037") == "06037"
    assert county_fips("88888") is None and county_fips("99999") is None
    assert county_fips("0") is None and county_fips("") is None and county_fips("123456") is None
    assert county_fips("42000") is None
    assert snapshot_date(KEY) == date(2026, 9, 30)
    with pytest.raises(ValueError, match="snapshot"):
        snapshot_date("bulk-data/other.csv")
    with pytest.raises(ValueError, match="pair up"):
        list_bucket("<Key>a</Key>")


def test_filter_keeps_only_money_judgments_for_the_plaintiff() -> None:
    cfg = load_config()
    assert kept(row(), cfg) == (date(1989, 11, 15), 75)
    assert kept(row(nature_of_judgement="2"), cfg) is not None  # money and other relief
    for bad in ({"judgment": "2"}, {"judgment": "3"}, {"judgment": "4"}, {"judgment": ""},
                {"nature_of_judgement": "0"}, {"nature_of_judgement": "3"},
                {"nature_of_judgement": "5"}, {"nature_of_judgement": "6"},
                {"amount_received": "0"}, {"amount_received": ""},
                {"amount_received": "-8"}, {"date_terminated": "9100103"},
                {"date_terminated": ""}):  # fmt: skip
        assert kept(row(**bad), cfg) is None, bad
    got = norm([row(id="1"), row(id="2", judgment="2"), row(id="3", date_terminated="9100103"),
                row(id="4", amount_received="0")])  # fmt: skip
    assert [r["record_key"] for r in of(got, "judgment")] == ["1"]


def test_amounts_are_thousands_and_9999_is_a_floor() -> None:
    cfg = load_config()
    assert principal(75, cfg) == Decimal(75000)
    assert principal(9998, cfg) == Decimal(9_998_000)
    assert principal(9999, cfg) is None  # "$9,999,000 or more": not an amount
    got = of(norm([row(id="1"), row(id="2", amount_received="9999")]), "judgment")
    assert [(j["record_key"], j["principal"]) for j in got] == [("1", Decimal(75000)),
                                                                ("2", None)]  # fmt: skip
    assert {j["judgment_type"] for j in got} == {"money"}
    assert got[0]["entered_on"] == date(1989, 11, 15)


def test_case_parties_and_jurisdiction() -> None:
    got = norm([row(plaintiff="USA, ET AL", defendant="DOE, ET AL", county_of_residence="88888")])
    case = of(got, "court_case")[0]
    assert case["case_uid"] == "us.paed:2:8907217:1989-10-05#100"
    assert case["court_id"] == "us.paed" and case["case_number_norm"] == "2:8907217"
    assert case["filed_on"] == date(1989, 10, 5) and case["closed_on"] == date(1989, 11, 15)
    assert case["nature_of_suit"] == "190" and case["jurisdiction"] == "paed"
    parties = {p["party_id"]: p for p in of(got, "party")}
    roles = {cp["role"]: parties[cp["party_id"]] for cp in of(got, "case_party")}
    assert roles["creditor"]["raw_name"] == "USA, ET AL"  # raw name kept as given
    assert roles["debtor"]["raw_name"] == "DOE, ET AL"
    clean_ids = {p["party_id"] for p in of(norm([row(plaintiff="USA", defendant="DOE")]), "party")}
    assert set(parties) == clean_ids  # the ET AL marker does not change who the party is
    assert of(norm([row()]), "judgment")[0]["jurisdiction"] == "42017"
    lone = norm([row(defendant="  ")])
    assert [cp["role"] for cp in of(lone, "case_party")] == ["creditor"]


def test_case_uid_is_unique_per_idb_record() -> None:
    # The same docket reported twice (a reopened case): two cases, two judgments.
    a, b = row(id="7"), row(id="8", date_terminated="1991-02-14", amount_received="5277")
    assert case_uid(a) != case_uid(b)
    assert case_uid(a).rsplit("#", 1)[0] == case_uid(b).rsplit("#", 1)[0]
    got = norm([b, a])
    assert len({c["case_uid"] for c in of(got, "court_case")}) == 2
    assert [c["record_key"] for c in of(got, "court_case")] == ["7", "8"]  # sorted by id
    assert case_uid(row(office="", date_filed="")) == "us.paed:-:8907217:-#100"


def test_bad_rows_are_skipped_or_cleaned() -> None:
    got = norm([
        row(id="1", date_filed="garbage"),                  # filed unknown, judgment kept
        row(id="2", date_filed="1990-01-01"),               # filed after termination: dropped
        row(id="3", date_terminated="2027-01-01"),          # after retrieval: skipped
        row(id="", docket_number="1"),                      # no record id: skipped
        row(id="5", district_id=""),                        # no court: skipped
    ])  # fmt: skip
    cases = {c["record_key"]: c for c in of(got, "court_case")}
    assert set(cases) == {"1", "2"}
    assert cases["1"]["filed_on"] is None and cases["2"]["filed_on"] is None


def test_csv_reader_handles_backslash_escapes() -> None:
    rows = [row(id="1", defendant='O"NEILL'), row(id="2", plaintiff='"SOUTHERN CALIF')]
    text = csv_text(rows)
    assert '"O\\"NEILL"' in text
    got = list(read_csv_rows(io.StringIO(text + '"short","row"\n')))
    assert got[0] == rows[0] and got[1] == rows[1] and got[2] is None


class FakeS3:
    retries = 0
    backoff_s = 0.0

    def __init__(self, objects: dict[str, bytes], page: int = 1000) -> None:
        self.objects, self.page = objects, page
        self.calls: list[str] = []
        self.status = 200

    def now(self) -> datetime:
        return AT

    def get(self, url: str, params: dict[str, str] | None = None) -> Response:
        self.calls.append(url)
        if params and params.get("list-type") == "2":
            keys = sorted(k for k in self.objects if k.startswith(params["prefix"]))
            start = int(params.get("continuation-token", "0"))
            chunk = keys[start : start + self.page]
            xml = "".join(f"<Contents><Key>{k}</Key><Size>{len(self.objects[k])}</Size>"
                          "</Contents>" for k in chunk)  # fmt: skip
            if start + self.page < len(keys):
                xml += f"<NextContinuationToken>{start + self.page}</NextContinuationToken>"
            return Response(url, self.status, xml.encode(), "application/xml", AT)
        key = url.split(".amazonaws.com/", 1)[1]
        return Response(url, 200, self.objects[key], "application/x-bzip2", AT)


def adapter(objects: dict[str, bytes], tmp_path: Path, page: int = 1000) -> FJCCivilJudgments:
    a = FJCCivilJudgments(FakeS3(objects, page))  # type: ignore[arg-type]
    a.cache_dir = tmp_path  # type: ignore[misc]
    return a


def snapshot(key: str, rows: list[dict[str, str]]) -> dict[str, bytes]:
    return {key: bz2.compress(csv_text(rows).encode())}


def test_partitions_follow_the_latest_snapshot(tmp_path: Path) -> None:
    old = "bulk-data/fjc-integrated-database-2025-12-31.csv.bz2"
    objs = {**snapshot(old, [row()]), **snapshot(KEY, [row()]),
            "bulk-data/fjc-integrated-database-notes.txt": b"x"}  # fmt: skip
    a = adapter(objs, tmp_path, page=1)  # one key per listing page
    parts = list(a.partitions())
    assert {p["key"] for p in parts} == {KEY}
    assert parts[0]["year"] == "1970" and parts[-1]["year"] == "2026"
    assert parts[0]["size"] == str(len(objs[KEY]))
    h = a.health()
    assert h.ok and h.shape == (Path(KEY).name,)
    empty = adapter({}, tmp_path)
    assert empty.health().ok is False
    empty.client.status = 503  # type: ignore[attr-defined]
    assert "HTTP 503" in empty.health().detail


def test_fetch_extracts_once_and_cleans_up(tmp_path: Path) -> None:
    rows = [row(id="1"), row(id="2", judgment="2"),
            row(id="3", date_filed="2025-01-02", date_terminated="2026-03-04")]  # fmt: skip
    objs = snapshot(KEY, rows)
    a = adapter(objs, tmp_path)
    first = a.fetch(FetchRequest({"key": KEY, "year": "1989"}))  # size looked up
    body = json.loads(first.content)
    assert [r["id"] for r in body["rows"]] == ["1"]  # the extract holds kept rows only
    assert first.request == BUCKET + KEY + "#date_terminated=1989"
    assert first.retrieved_at == AT
    assert not (tmp_path / Path(KEY).name).exists()  # the bz2 is gone after the extract
    manifest = json.loads((tmp_path / "fjc-integrated-database-2026-09-30" /
                           "_manifest.json").read_text())  # fmt: skip
    assert manifest["rows"] == 3 and manifest["kept"] == 2 and manifest["bad_rows"] == 0
    size = str(len(objs[KEY]))
    none = a.fetch(FetchRequest({"key": KEY, "size": size, "year": "2000"}))
    assert json.loads(none.content)["rows"] == []
    lim = a.fetch(FetchRequest({"key": KEY, "size": size, "year": "2026", "limit": "5"}))
    assert len(json.loads(lim.content)["rows"]) == 1
    assert (tmp_path / "fjc-integrated-database-2026-09-30").exists()  # kept: limit given
    last = a.fetch(FetchRequest({"key": KEY, "size": size, "year": "2026"}))
    assert [r["id"] for r in json.loads(last.content)["rows"]] == ["3"]
    assert not (tmp_path / "fjc-integrated-database-2026-09-30").exists()  # last partition
    downloads = [c for c in a.client.calls if c.endswith(".bz2")]  # type: ignore[attr-defined]
    assert len(downloads) == 1


def test_fetch_reuses_a_cached_download_and_rejects_short_ones(tmp_path: Path) -> None:
    objs = snapshot(KEY, [row()])
    (tmp_path / Path(KEY).name).write_bytes(objs[KEY])
    a = adapter(objs, tmp_path)
    a.fetch(FetchRequest({"key": KEY, "size": str(len(objs[KEY])), "year": "1989"}))
    assert not [c for c in a.client.calls if c.endswith(".bz2")]  # type: ignore[attr-defined]
    b = adapter(objs, tmp_path / "other")
    with pytest.raises(ValueError, match="bytes"):
        b.fetch(FetchRequest({"key": KEY, "size": str(len(objs[KEY]) + 1), "year": "1989"}))


def test_fixture_normalizes() -> None:
    path = next(FIX.glob("*.json"))
    f = Fetched(FJCCivilJudgments.source_id, path.as_uri(), AT, 200, path.read_bytes(), "")
    a = by_source_id(FJCCivilJudgments.source_id)()  # type: ignore[abstract]
    rows = [(r.table, dict(r.row)) for r in a.normalize(f)]
    t = Counter(table for table, _ in rows)
    assert t["court_case"] == t["judgment"] == t["source_record"] > 0
    assert {r["role"] for r in of(rows, "case_party")} == {"creditor", "debtor"}
    assert all(r["court_id"].startswith("us.") for r in of(rows, "court_case"))
    src = a.source_row()
    assert src["access_method"] == "bulk" and src["cost_model"] == "free"
    assert src["terms_checked_on"] == date(2026, 11, 22)
