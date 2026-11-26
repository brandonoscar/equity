"""Query catalog and search, on a tiny synthetic lake written as Parquet (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from equity.catalog import FileSource, build, compact, connect, status
from equity.search import address_search, query_key, search, show

T = "TIMESTAMPTZ '2026-01-01 00:00:00+00'"


def _write(lake: Path, source_id: str, table: str, rows: list[dict[str, Any]]) -> None:
    out = lake / source_id / table
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM read_json_auto(?)", [_json(lake, rows)])
    con.execute(f"COPY t TO '{out / '00000.parquet'}' (FORMAT parquet)")


def _json(lake: Path, rows: list[dict[str, Any]]) -> str:
    p = lake / f"_rows_{abs(hash(json.dumps(rows, sort_keys=True)))}.json"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return str(p)


def _finish(lake: Path, source_id: str, counts: dict[str, int]) -> None:
    (lake / source_id / "_counts.json").write_text(json.dumps(counts))


def _party(pid: str, name: str, kind: str, sid: str, addr: str | None = None) -> dict[str, Any]:
    return {"party_id": pid, "raw_name": name, "party_kind": kind, "org_form": None,
            "address_id": addr, "source_id": sid, "jurisdiction": "39049",
            "superseded_at": None}  # fmt: skip


@pytest.fixture
def lake(tmp_path: Path) -> Path:
    lake = tmp_path / "lake"
    p = "oh.franklin.parcels"
    _write(lake, p, "party", [
        _party("o1", "SMITH, JOHN A", "unknown", p, "a1"),
        _party("o2", "ACME HOLDINGS LLC", "org", p),
        _party("o3", "SMYTH JOHN A", "unknown", p),
        _party("o4", "LUCAS JOHN S", "unknown", p),
        _party("o5", "old name", "unknown", p) | {"superseded_at": "2026-02-01T00:00:00Z"},
    ])  # fmt: skip
    _write(lake, p, "owner_snapshot", [
        {"party_id": "o1", "parcel_uid": "39049-010-1", "observed_on": "2026-11-01",
         "source_id": p, "superseded_at": None},
        {"party_id": "o2", "parcel_uid": "39049-010-2", "observed_on": "2026-11-01",
         "source_id": p, "superseded_at": None},
    ])  # fmt: skip
    _write(lake, p, "parcel", [
        {"parcel_uid": "39049-010-1", "jurisdiction": "39049", "parid_raw": "010-1",
         "situs_address_id": "a1", "land_use_code": "510", "source_id": p,
         "superseded_at": None},
        {"parcel_uid": "39049-010-2", "jurisdiction": "39049", "parid_raw": "010-2",
         "situs_address_id": None, "land_use_code": "400", "source_id": p,
         "superseded_at": None},
    ])  # fmt: skip
    _write(lake, p, "parcel_assessment", [
        {"parcel_uid": "39049-010-1", "tax_year": 2024, "appraised_total": 150000.0,
         "assessed_value": 52500.0, "valid_from": "2024-01-01", "source_id": p,
         "superseded_at": None},
        {"parcel_uid": "39049-010-1", "tax_year": 2025, "appraised_total": 180000.0,
         "assessed_value": 63000.0, "valid_from": "2025-01-01", "source_id": p,
         "superseded_at": None},
    ])  # fmt: skip
    _write(lake, p, "address", [
        {"address_id": "a1", "line1": "123 MAIN STREET", "city": "COLUMBUS", "state": "OH",
         "zip5": "43215"},
    ])  # fmt: skip
    _finish(lake, p, {"party": 4, "parcel": 2})
    d = "oh.cuyahoga.liens"
    _write(lake, d, "party", [_party("d1", "John A. Smith", "unknown", d, "a1")])
    _write(lake, d, "instrument", [
        {"instrument_uid": "i1", "doc_type": "JUDGMENT_LIEN", "doc_type_raw": "JL",
         "recorded_on": "2025-06-01", "principal_amount": 12500.0, "source_id": d,
         "superseded_at": None},
    ])  # fmt: skip
    _write(lake, d, "instrument_party", [
        {"instrument_uid": "i1", "party_id": "d1", "role": "debtor", "source_id": d,
         "superseded_at": None},
    ])  # fmt: skip
    _finish(lake, d, {"party": 1, "instrument": 1})
    return lake


@pytest.fixture
def cat(lake: Path, tmp_path: Path) -> duckdb.DuckDBPyConnection:
    con = connect(tmp_path / "c.duckdb")
    assert build(con, FileSource(lake), log=lambda _m: None) == [
        "oh.cuyahoga.liens", "oh.franklin.parcels"]  # fmt: skip
    return con


def test_query_key_ignores_order_punctuation_and_suffixes(cat: duckdb.DuckDBPyConnection) -> None:
    assert query_key(cat, "Smith, John A. Jr") == query_key(cat, "JOHN A SMITH") == "A JOHN SMITH"


def test_exact_hits_carry_their_links(cat: duckdb.DuckDBPyConnection) -> None:
    hits = search(cat, "john a smith")
    top = [(h.source_id, h.rule, h.score) for h in hits if h.rule == "exact"]
    assert top == [("oh.cuyahoga.liens", "exact", 1.0), ("oh.franklin.parcels", "exact", 1.0)]
    debtor = next(h for h in hits if h.source_id == "oh.cuyahoga.liens")
    assert (debtor.debts, debtor.debt_amount, debtor.documents) == (1, 12500.0, 1)
    assert debtor.address == "123 MAIN STREET, COLUMBUS, OH 43215"
    owner = next(h for h in hits if h.source_id == "oh.franklin.parcels" and h.rule == "exact")
    assert (owner.parcels, owner.parcel_value) == (1, 180000.0)  # latest assessment only


def test_rules_rank_partial_and_similar_names(cat: duckdb.DuckDBPyConnection) -> None:
    rules = {h.raw_name: h.rule for h in search(cat, "JOHN SMITH")}
    assert rules["SMITH, JOHN A"] == "all_words"
    assert rules["SMYTH JOHN A"] == "similar"
    assert "LUCAS JOHN S" not in rules  # two initials would be needed: not a match
    assert search(cat, "nobody here") == []
    assert search(cat, "") == []


def test_filters_and_superseded_rows(cat: duckdb.DuckDBPyConnection) -> None:
    assert {h.state for h in search(cat, "john a smith", state="oh")} == {"OH"}
    assert search(cat, "john a smith", state="TX") == []
    assert [h.raw_name for h in search(cat, "acme holdings", kind="org")] == ["ACME HOLDINGS LLC"]
    assert search(cat, "old name") == []  # superseded in the lake


def test_show_lists_parcels_documents_and_same_name(cat: duckdb.DuckDBPyConnection) -> None:
    e = show(cat, "oh.franklin.parcels:o1")
    assert e is not None
    assert [(p["parcel_uid"], p["tax_year"], p["situs_line1"]) for p in e.parcels] == [
        ("39049-010-1", 2025, "123 MAIN STREET")]  # fmt: skip
    assert [s["ref"] for s in e.same_name] == ["oh.cuyahoga.liens:d1"]
    d = show(cat, "oh.cuyahoga.liens:d1")
    assert d is not None and [x["doc_type"] for x in d.documents] == ["JUDGMENT_LIEN"]
    assert show(cat, "oh.franklin.parcels:nope") is None


def test_address_search_normalizes_the_street(cat: duckdb.DuckDBPyConnection) -> None:
    found = address_search(cat, "123 Main St.", zip5="43215")
    assert [p["parcel_uid"] for p in found["parcels"]] == ["39049-010-1"]
    assert sorted(p["ref"] for p in found["parties"]) == [
        "oh.cuyahoga.liens:d1", "oh.franklin.parcels:o1"]  # fmt: skip
    assert address_search(cat, "999 Elm St", zip5="43215") == {"parcels": [], "parties": []}


def test_rebuild_only_reindexes_changed_sources(cat: duckdb.DuckDBPyConnection, lake: Path) -> None:
    src = FileSource(lake)
    assert build(cat, src, log=lambda _m: None) == []
    _finish(lake, "oh.cuyahoga.liens", {"party": 1, "instrument": 1, "x": 1})
    assert build(cat, src, log=lambda _m: None) == ["oh.cuyahoga.liens"]
    assert cat.execute("SELECT count(*) FROM names WHERE source_id = 'oh.cuyahoga.liens'"
                       ).fetchone() == (1,)  # fmt: skip
    (lake / "oh.cuyahoga.liens" / "_counts.json").unlink()
    logs: list[str] = []
    build(cat, src, log=logs.append)
    assert logs == ["dropped oh.cuyahoga.liens (no longer in the lake)"]
    assert search(cat, "john a smith")[0].source_id == "oh.franklin.parcels"


def test_compact_and_status(cat: duckdb.DuckDBPyConnection) -> None:
    compact(cat)
    text = status(cat)
    assert text.startswith("2 sources indexed")
    assert "names" in text and search(cat, "john a smith")


def test_read_only_catalog_searches(cat: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    cat.close()
    ro = connect(tmp_path / "c.duckdb", read_only=True)
    assert search(ro, "john a smith")
    assert address_search(ro, "123 main street")["parcels"]


def test_remote_source_lists_built_sources_and_part_urls() -> None:
    from equity.catalog import RemoteSource
    from equity.lake_sync import Store

    bundles = {"a.b.parcels": {"_counts.json": "{}"}, "a.c.parcels": {"_plan.json": "[]"}}

    def transport(method: str, url: str, data: bytes | None, headers: dict[str, str]) -> bytes:
        if url.endswith("/object/list/lake"):
            prefix = json.loads(data or b"{}")["prefix"]
            if prefix == "":
                return json.dumps([{"name": k, "metadata": None} for k in
                                   (*bundles, "archive")]).encode()  # fmt: skip
            return json.dumps([{"name": "00000.parquet", "metadata": {"size": 1}},
                               {"name": "_x.json", "metadata": {"size": 1}}]).encode()  # fmt: skip
        sid = url.split("/object/lake/")[1].split("/")[0]
        if sid not in bundles:
            raise OSError("404")
        return json.dumps(bundles[sid]).encode()

    store = Store(base_url="https://x.test/storage/v1", transport=transport,
                  sleep=lambda _s: None, log=lambda _m: None)  # fmt: skip
    src = RemoteSource(store)
    assert src.sources() == ["a.b.parcels"]  # unfinished and non-source folders skipped
    assert src.sources(["a.b.parcels", "zz.none"]) == ["a.b.parcels"]
    assert len(src.version("a.b.parcels")) == 16
    assert src.files("a.b.parcels", "party") == [
        "https://x.test/storage/v1/object/lake/a.b.parcels/party/00000.parquet"]  # fmt: skip


def test_states_filter_force_and_city_address(lake: Path, tmp_path: Path) -> None:
    con = connect(tmp_path / "s.duckdb")
    assert build(con, FileSource(lake), states=["oh"], log=lambda _m: None) == [
        "oh.cuyahoga.liens", "oh.franklin.parcels"]  # fmt: skip
    assert build(con, FileSource(lake), states=["TX"], log=lambda _m: None) == []
    assert build(con, FileSource(lake), only=["oh.cuyahoga.liens"], force=True,
                 log=lambda _m: None) == ["oh.cuyahoga.liens"]  # fmt: skip
    hits = address_search(con, "123 main street", city="Columbus")
    assert [p["parcel_uid"] for p in hits["parcels"]] == ["39049-010-1"]
    assert address_search(con, "   ") == {"parcels": [], "parties": []}


def test_views_and_saved_macros_for_sql_clients(
    cat: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    rows = cat.execute("SELECT debtor_ref, owner_ref, parcel_uid, amount, appraised_total "
                       "FROM v_debtor_owner_candidates").fetchall()  # fmt: skip
    assert rows == [("oh.cuyahoga.liens:d1", "oh.franklin.parcels:o1", "39049-010-1",
                     12500.0, 180000.0)]  # fmt: skip
    cat.close()
    plain = duckdb.connect(str(tmp_path / "c.duckdb"), read_only=True)  # no helper macros
    assert plain.execute("SELECT name_key('Smith, John A.')").fetchone() == ("A JOHN SMITH",)
    assert plain.execute("SELECT count(*) FROM v_owner_parcels").fetchone() == (2,)
