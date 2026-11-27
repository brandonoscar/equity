"""Search index and search, on a tiny synthetic lake written as Parquet (no network)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest
import yaml

from equity.search import address_search, query_key, search, show
from equity.search_index import FileSource, build, compact, connect, status

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
    _write(lake, d, "instrument_parcel", [
        {"instrument_uid": "i1", "parcel_uid": "39049-010-1", "method": "index_parcel_id",
         "source_id": d, "superseded_at": None},
    ])  # fmt: skip
    _write(lake, d, "instrument_party", [
        {"instrument_uid": "i1", "party_id": "d1", "role": "debtor", "source_id": d,
         "superseded_at": None},
    ])  # fmt: skip
    _finish(lake, d, {"party": 1, "instrument": 1})
    b = "oh.sos.business"
    _write(lake, b, "business", [
        {"sos_id": "B7", "name": "Acme Holdings, L.L.C.", "org_form": "LLC", "status": "Active",
         "formed_on": "2019-03-01", "source_id": b, "superseded_at": None},
    ])  # fmt: skip
    _write(lake, b, "party", [_party("m1", "JOHN A SMITH", "unknown", b)])
    _write(lake, b, "business_role", [
        {"sos_id": "B7", "party_id": "m1", "role": "member", "title": "Managing member",
         "source_id": b, "superseded_at": None},
    ])  # fmt: skip
    _finish(lake, b, {"business": 1, "party": 1})
    return lake


@pytest.fixture
def cat(lake: Path, tmp_path: Path) -> duckdb.DuckDBPyConnection:
    con = connect(tmp_path / "c.duckdb")
    assert build(con, FileSource(lake), log=lambda _m: None) == [
        "oh.cuyahoga.liens", "oh.franklin.parcels", "oh.sos.business"]  # fmt: skip
    return con


def test_query_key_ignores_order_punctuation_and_suffixes(cat: duckdb.DuckDBPyConnection) -> None:
    assert query_key(cat, "Smith, John A. Jr") == query_key(cat, "JOHN A SMITH") == "A JOHN SMITH"


def test_exact_hits_carry_their_links(cat: duckdb.DuckDBPyConnection) -> None:
    hits = search(cat, "john a smith")
    top = [(h.source_id, h.rule, h.score) for h in hits if h.rule == "exact"]
    assert top == [("oh.sos.business", "exact", 1.0), ("oh.cuyahoga.liens", "exact", 1.0),
                   ("oh.franklin.parcels", "exact", 1.0)]  # fmt: skip
    debtor = next(h for h in hits if h.source_id == "oh.cuyahoga.liens")
    assert (debtor.debts, debtor.debt_amount, debtor.documents) == (1, 12500.0, 1)
    assert debtor.address == "123 MAIN STREET, COLUMBUS, OH 43215"
    owner = next(h for h in hits if h.source_id == "oh.franklin.parcels" and h.rule == "exact")
    assert (owner.parcels, owner.parcel_value) == (1, 180000.0)  # latest assessment only


def test_rules_rank_partial_and_similar_names(cat: duckdb.DuckDBPyConnection) -> None:
    rules = {h.raw_name: h.rule for h in search(cat, "JOHN SMITH")}
    assert rules["SMITH, JOHN A"] == "all_words"
    assert rules["SMYTH JOHN A"] == "sounds_like"
    assert "LUCAS JOHN S" not in rules  # two initials would be needed: not a match
    assert search(cat, "nobody here") == []
    assert search(cat, "") == []


def test_filters_and_superseded_rows(cat: duckdb.DuckDBPyConnection) -> None:
    assert {h.state for h in search(cat, "john a smith", state="oh")} == {"OH"}
    assert search(cat, "john a smith", state="TX") == []
    assert [h.raw_name for h in search(cat, "acme holdings", kind="org")] == [
        "ACME HOLDINGS LLC", "Acme Holdings, L.L.C."]  # fmt: skip
    assert [h.party_kind for h in search(cat, "acme holdings", kind="business")] == ["business"]
    assert search(cat, "old name") == []  # superseded in the lake


def test_show_lists_parcels_documents_and_same_name(cat: duckdb.DuckDBPyConnection) -> None:
    e = show(cat, "oh.franklin.parcels:o1")
    assert e is not None
    assert [(p["parcel_uid"], p["tax_year"], p["situs_line1"]) for p in e.parcels] == [
        ("39049-010-1", 2025, "123 MAIN STREET")]  # fmt: skip
    assert [s["ref"] for s in e.same_name] == ["oh.cuyahoga.liens:d1", "oh.sos.business:m1"]
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
    assert {h.source_id for h in search(cat, "john a smith")} == {
        "oh.franklin.parcels", "oh.sos.business"}  # fmt: skip


def test_compact_and_status(cat: duckdb.DuckDBPyConnection) -> None:
    compact(cat)
    assert cat.execute("SELECT debtor_refs FROM debtor_owner_candidates").fetchall() == [
        (["oh.cuyahoga.liens:d1"],)]  # fmt: skip
    text = status(cat)
    assert text.startswith("3 sources indexed")
    assert "names" in text and search(cat, "john a smith")


def test_read_only_catalog_searches(cat: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    cat.close()
    ro = connect(tmp_path / "c.duckdb", read_only=True)
    assert search(ro, "john a smith")
    assert address_search(ro, "123 main street")["parcels"]


def test_remote_source_lists_built_sources_and_part_urls() -> None:
    from equity.lake_sync import Store
    from equity.search_index import RemoteSource

    bundles = {"a.b.parcels": {"_counts.json": "{}"}, "a.c.parcels": {"_plan.json": "[]"}}

    def transport(method: str, url: str, data: bytes | None, headers: dict[str, str]) -> bytes:
        if url.endswith("/object/list/lake"):
            prefix = json.loads(data or b"{}")["prefix"]
            if prefix == "derived/":
                dirs = [{"name": n, "metadata": None} for n in ("oh", "sale_listings")]
                return json.dumps(dirs).encode()
            if prefix == "derived/oh/":
                files = [{"name": "matches.parquet", "metadata": {"size": 5}},
                         {"name": "summary.json", "metadata": {"size": 9}}]  # fmt: skip
                return json.dumps(files).encode()
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
    assert src.derived() == {"OH": {
        "matches": "https://x.test/storage/v1/object/lake/derived/oh/matches.parquet"}}  # fmt: skip
    assert len(src.derived_version("OH", {})) == 16
    assert src.files("a.b.parcels", "party") == [
        "https://x.test/storage/v1/object/lake/a.b.parcels/party/00000.parquet"]  # fmt: skip


def test_states_filter_force_and_city_address(lake: Path, tmp_path: Path) -> None:
    con = connect(tmp_path / "s.duckdb")
    assert build(con, FileSource(lake), states=["oh"], log=lambda _m: None) == [
        "oh.cuyahoga.liens", "oh.franklin.parcels", "oh.sos.business"]  # fmt: skip
    assert build(con, FileSource(lake), states=["TX"], log=lambda _m: None) == []
    assert build(con, FileSource(lake), only=["oh.cuyahoga.liens"], force=True,
                 log=lambda _m: None) == ["oh.cuyahoga.liens"]  # fmt: skip
    hits = address_search(con, "123 main street", city="Columbus")
    assert [p["parcel_uid"] for p in hits["parcels"]] == ["39049-010-1"]
    assert address_search(con, "   ") == {"parcels": [], "parties": []}


def test_views_and_saved_macros_for_sql_clients(
    cat: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    q = ("SELECT state, debts, debt_amount, parcels, parcel_value, debtor_refs, owner_refs, "
         "parcel_uids FROM v_debtor_owner_candidates")  # fmt: skip
    rows = cat.execute(q).fetchall()
    assert rows == [("OH", 1, 12500.0, 1, 180000.0, ["oh.cuyahoga.liens:d1"],
                     ["oh.franklin.parcels:o1"], ["39049-010-1"])]  # fmt: skip
    cat.close()
    plain = duckdb.connect(str(tmp_path / "c.duckdb"), read_only=True)  # no helper macros
    assert plain.execute("SELECT name_key('Smith, John A.')").fetchone() == ("A JOHN SMITH",)
    assert plain.execute("SELECT count(*) FROM v_owner_parcels").fetchone() == (2,)


def test_sounds_like_survives_a_typo_in_every_word(cat: duckdb.DuckDBPyConnection) -> None:
    hits = {h.raw_name: h.rule for h in search(cat, "JON SMYTHE")}
    assert hits["SMITH, JOHN A"] == "sounds_like"  # JON~JOHN, SMYTHE~SMITH (Soundex)
    assert cat.execute("SELECT soundex('ASHCRAFT'), soundex('TYMCZAK'), soundex('42')"
                       ).fetchone() == ("A261", "T522", "42")  # fmt: skip


def test_business_hit_and_its_people(cat: duckdb.DuckDBPyConnection) -> None:
    from equity.search import show_business

    firm = next(h for h in search(cat, "Acme Holdings") if h.party_kind == "business")
    assert (firm.ref, firm.officers) == ("oh.sos.business:business:B7", 1)
    member = next(h for h in search(cat, "john a smith") if h.source_id == "oh.sos.business")
    assert member.businesses == 1
    b = show_business(cat, firm.ref)
    assert b is not None and b["status"] == "Active"
    assert [(p["role"], p["raw_name"], p["parcels_under_same_name"]) for p in b["people"]] == [
        ("member", "JOHN A SMITH", 1)]  # fmt: skip
    assert show_business(cat, "oh.sos.business:business:none") is None


def test_network_walks_parcels_documents_names_and_addresses(
    cat: duckdb.DuckDBPyConnection,
) -> None:
    from equity.search import network

    g = network(cat, "oh.cuyahoga.liens:d1", hops=2)
    ids = {n["id"] for n in g["nodes"]}
    assert {"party:oh.cuyahoga.liens:d1", "doc:oh.cuyahoga.liens:i1",
            "party:oh.franklin.parcels:o1", "parcel:39049-010-1",
            "business:oh.sos.business:B7"} <= ids  # fmt: skip
    kinds = {(e["from"], e["to"], e["kind"]) for e in g["edges"]}
    assert ("party:oh.cuyahoga.liens:d1", "doc:oh.cuyahoga.liens:i1", "party_to:debtor") in kinds
    assert ("party:oh.cuyahoga.liens:d1", "party:oh.franklin.parcels:o1", "same_address") in kinds
    assert ("party:oh.franklin.parcels:o1", "parcel:39049-010-1", "owns") in kinds
    one = network(cat, "oh.cuyahoga.liens:d1", hops=1)
    assert "business:oh.sos.business:B7" not in {n["id"] for n in one["nodes"]}  # 2 hops away


def test_an_old_word_index_is_rebuilt(lake: Path, tmp_path: Path) -> None:
    db = tmp_path / "old.duckdb"
    con = connect(db)
    build(con, FileSource(lake), log=lambda _m: None)
    con.execute("CREATE OR REPLACE TABLE name_words AS "
                "SELECT 'X' AS word, 'oh.x' AS source_id, 'p' AS party_id")  # fmt: skip
    con.execute("DROP TABLE word_sounds")
    con.close()
    con = connect(db)  # migrates
    assert search(con, "john a smith")[0].rule == "exact"
    assert con.execute("SELECT count(*) > 0 FROM word_sounds").fetchone() == (True,)


def test_parallel_build_matches_the_serial_one(lake: Path, tmp_path: Path) -> None:
    serial = connect(tmp_path / "a.duckdb")
    build(serial, FileSource(lake), log=lambda _m: None)
    par = connect(tmp_path / "b.duckdb")
    got = build(par, FileSource(lake), log=lambda _m: None, workers=3,
                scratch=tmp_path / "scratch")  # fmt: skip
    assert got == ["oh.cuyahoga.liens", "oh.franklin.parcels", "oh.sos.business"]
    for t in ("names", "owners", "parcel_values", "instruments", "businesses", "name_words"):
        q = f"SELECT * FROM {t} ORDER BY ALL"
        assert serial.execute(q).fetchall() == par.execute(q).fetchall(), t
    assert not any((tmp_path / "scratch").glob("*/_counts.json"))  # scratch cleaned up


def test_benchmark_reports_recall_and_latency(cat: duckdb.DuckDBPyConnection) -> None:
    from equity.search import benchmark

    b = benchmark(cat, n=10, top=10)
    assert b["queries"] >= 3
    assert b["as_written"]["name_recall"] == 1.0
    assert 0 <= b["one_typo"]["record_recall"] <= b["one_typo"]["name_recall"] <= 1
    assert b["as_written"]["p95_s"] >= b["as_written"]["p50_s"] >= 0


def test_export_and_pull_round_trip(cat: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    from equity.search_index import export, pull

    class MemStore:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        def upload(self, key: str, data: bytes) -> None:
            self.objects[key] = data

        def download(self, key: str) -> bytes:
            return self.objects[key]

    store = MemStore()
    sent = export(cat, store, tmp_path / "exp", log=lambda _m: None)
    assert sent == len(store.objects) and "_search_index/manifest.json" in store.objects
    assert all(len(v) < 40_000_000 for v in store.objects.values())
    n = pull(store, tmp_path / "pulled.duckdb", tmp_path / "pull", log=lambda _m: None)
    assert n == 3
    other = connect(tmp_path / "pulled.duckdb", read_only=True)
    assert [h.ref for h in search(other, "john a smith")] == [
        h.ref for h in search(cat, "john a smith")
    ]
    assert other.execute("SELECT count(*) FROM v_debtor_owner_candidates").fetchone() == (1,)


def test_parcel_view_and_document_edges(cat: duckdb.DuckDBPyConnection) -> None:
    from equity.search import network, show_parcel

    (p,) = [r for r in show_parcel(cat, "010-1") if r["source_id"] == "oh.franklin.parcels"]
    assert (p["parcel_uid"], p["appraised_total"], p["situs_line1"]) == (
        "39049-010-1", 180000.0, "123 MAIN STREET")  # fmt: skip
    assert [o["raw_name"] for o in p["owners"]] == ["SMITH, JOHN A"]
    assert [(d["doc_type"], d["parties"]) for d in p["documents"]] == [
        ("JUDGMENT_LIEN", ["John A. Smith (debtor)"])]  # fmt: skip
    assert show_parcel(cat, "nope") == []
    d = show(cat, "oh.cuyahoga.liens:d1")
    assert d is not None and d.documents[0]["parcels"] == ["39049-010-1"]
    g = network(cat, "oh.cuyahoga.liens:d1", hops=1)
    assert {"from": "doc:oh.cuyahoga.liens:i1", "to": "parcel:39049-010-1",
            "kind": "recorded_against"} in g["edges"]  # fmt: skip


def test_placeholder_names_are_not_word_indexed(lake: Path, tmp_path: Path) -> None:
    p = "oh.statewide.parcels"
    _write(lake, p, "party", [_party("z1", "39005 | A01-001-0-0001-00", "unknown", p)])
    _finish(lake, p, {"party": 1})
    con = connect(tmp_path / "z.duckdb")
    build(con, FileSource(lake), log=lambda _m: None)
    assert con.execute("SELECT count(*) FROM name_words WHERE source_id = ?", [p]
                       ).fetchone() == (0,)  # fmt: skip
    assert con.execute("SELECT count(*) FROM names WHERE source_id = ?", [p]).fetchone() == (1,)


def test_initial_rule_does_not_reuse_a_query_initial(cat: duckdb.DuckDBPyConnection) -> None:
    # "JOHN A SMOTH": SMOTH may not be explained by the name's initial A, which the query's
    # own A already matches; the closer spelling decides the order instead.
    rules = {h.raw_name: h.rule for h in search(cat, "JOHN A SMOTH")}
    assert rules.get("SMITH, JOHN A") == "typo"  # SMOTH is one letter from SMITH
    assert rules.get("SMYTH JOHN A") == "typo"


def test_network_does_not_walk_through_creditors(lake: Path, tmp_path: Path) -> None:
    from equity.search import network

    d = "oh.cuyahoga.liens"
    _write(lake, d, "party", [_party("d1", "John A. Smith", "unknown", d, "a1"),
                              _party("c1", "COUNTY TREASURER", "org", d),
                              _party("d2", "MARY Q PUBLIC", "unknown", d)])  # fmt: skip
    _write(lake, d, "instrument_party", [
        {"instrument_uid": "i1", "party_id": "d1", "role": "debtor", "source_id": d,
         "superseded_at": None},
        {"instrument_uid": "i1", "party_id": "c1", "role": "creditor", "source_id": d,
         "superseded_at": None},
        {"instrument_uid": "i2", "party_id": "c1", "role": "creditor", "source_id": d,
         "superseded_at": None},
        {"instrument_uid": "i2", "party_id": "d2", "role": "debtor", "source_id": d,
         "superseded_at": None},
    ])  # fmt: skip
    _finish(lake, d, {"party": 3, "v": 2})
    con = connect(tmp_path / "n.duckdb")
    build(con, FileSource(lake), log=lambda _m: None)
    ids = {n["id"] for n in network(con, f"{d}:d1", hops=3)["nodes"]}
    assert f"party:{d}:c1" in ids  # the creditor is shown
    assert f"party:{d}:d2" not in ids  # but not walked through to its other debtors


# --- matcher output, history, equity, nicknames, flags, aliases -------------------------


@pytest.fixture
def rich(lake: Path, tmp_path: Path) -> duckdb.DuckDBPyConnection:
    p = "oh.franklin.parcels"
    _write(lake, p, "party", [
        _party("o1", "SMITH, JOHN A", "unknown", p, "a1"),
        _party("o2", "ACME HOLDINGS LLC", "org", p),
        _party("o6", "DOE, JANE", "unknown", p),
        _party("o7", "SMITH, ROBERT", "unknown", p),
        _party("o8", "CITY OF COLUMBUS", "org", p),
    ])  # fmt: skip
    _write(lake, p, "owner_snapshot", [
        {"party_id": "o1", "parcel_uid": "39049-010-1", "observed_on": "2026-11-01",
         "source_id": p, "superseded_at": None},
        {"party_id": "o6", "parcel_uid": "39049-010-1", "observed_on": "2025-01-01",
         "source_id": p, "superseded_at": "2026-01-01T00:00:00Z"},
        {"party_id": "o8", "parcel_uid": "39049-010-2", "observed_on": "2026-11-01",
         "source_id": p, "superseded_at": None},
    ])  # fmt: skip
    _finish(lake, p, {"party": 5, "v": 2})
    r = "oh.franklin.recorder"
    _write(lake, r, "party", [_party("g1", "SMITH, JOHN A", "unknown", r)])
    _write(lake, r, "instrument", [
        {"instrument_uid": "m1", "doc_type": "MORTGAGE", "doc_type_raw": "MTG",
         "recorded_on": "2020-05-01", "principal_amount": 100000.0, "source_id": r,
         "superseded_at": None},
        {"instrument_uid": "m2", "doc_type": "MORTGAGE", "doc_type_raw": "MTG",
         "recorded_on": "2010-05-01", "principal_amount": 50000.0, "source_id": r,
         "superseded_at": None},
        {"instrument_uid": "r1", "doc_type": "RELEASE", "doc_type_raw": "SAT",
         "recorded_on": "2019-01-01", "principal_amount": None, "source_id": r,
         "superseded_at": None},
        {"instrument_uid": "d9", "doc_type": "DEED", "doc_type_raw": "DEED",
         "recorded_on": "2025-06-01", "principal_amount": None, "source_id": r,
         "superseded_at": None},
    ])  # fmt: skip
    _write(lake, r, "instrument_parcel", [
        {"instrument_uid": u, "parcel_uid": "39049-010-1", "method": "index_parcel_id",
         "source_id": r, "superseded_at": None} for u in ("m1", "m2", "r1", "d9")
    ])  # fmt: skip
    _write(lake, r, "instrument_ref", [
        {"from_uid": "r1", "to_uid": "m2", "ref_type": "releases", "source_id": r,
         "superseded_at": None},
    ])  # fmt: skip
    _write(lake, r, "instrument_party", [
        {"instrument_uid": "d9", "party_id": "g1", "role": "grantee", "source_id": r,
         "superseded_at": None},
    ])  # fmt: skip
    _finish(lake, r, {"instrument": 4})
    h = "oh.sos.name_history"
    _write(lake, h, "business", [
        {"sos_id": "B7", "name": "OLD ACME LLC", "org_form": "LLC", "status": "former name",
         "formed_on": "2015-01-01", "source_id": h, "superseded_at": None},
    ])  # fmt: skip
    _finish(lake, h, {"business": 1})
    derived = lake.parent / "derived" / "oh"
    derived.mkdir(parents=True)
    c = duckdb.connect()
    c.execute(f"""COPY (SELECT 'd1' AS debtor_party_id, 'i1' AS instrument_uid,
        'o1' AS owner_party_id, '39049-010-1' AS parcel_uid, 'lien_names_parcel' AS rule_id,
        'auto' AS decision, '39049-010-1' AS key) TO '{derived / "matches.parquet"}'""")
    c.execute(f"""COPY (SELECT 'd1' AS debtor_party_id, 'John A. Smith' AS debtor_name,
        1::BIGINT AS liens, 12500.0 AS open_amount, 1::BIGINT AS parcels,
        180000.0 AS parcel_value, true AS has_auto, 70000.0 AS equity_est)
        TO '{derived / "debtor_summary.parquet"}'""")
    c.execute(f"""COPY (SELECT * FROM (VALUES ('d1', 'P1'), ('o1', 'P1')) t(party_id, person_id))
        TO '{derived / "person_of.parquet"}'""")
    c.execute(f"""COPY (SELECT 'P1' AS person_id, 'JOHN A SMITH' AS name, 12500.0 AS open_amount,
        1::BIGINT AS parcels, 180000.0 AS parcel_value) TO '{derived / "people.parquet"}'""")
    con = connect(tmp_path / "rich.duckdb")
    build(con, FileSource(lake), log=lambda _m: None)
    from equity.search_index import index_matcher

    assert index_matcher(con, FileSource(lake), log=lambda _m: None) == ["OH"]
    assert index_matcher(con, FileSource(lake), log=lambda _m: None) == []  # unchanged
    compact(con)
    return con


def test_matcher_grade_person_and_equity_on_hits(rich: duckdb.DuckDBPyConnection) -> None:
    hits = {h.ref: h for h in search(rich, "john a smith")}
    debtor, owner = hits["oh.cuyahoga.liens:d1"], hits["oh.franklin.parcels:o1"]
    assert (debtor.matcher, debtor.person_id) == ("auto lien_names_parcel", "P1")
    assert (owner.matcher, owner.person_id) == ("auto lien_names_parcel", "P1")
    m = show(rich, "oh.cuyahoga.liens:d1").matcher  # type: ignore[union-attr]
    assert m["as_debtor"][0]["parcel_uid"] == "39049-010-1"
    assert m["summary"][0]["equity_est"] == 70000.0  # columns beyond the core ones are kept
    assert m["person"][0]["name"] == "JOHN A SMITH"
    assert rich.execute("SELECT matcher_auto_debtors, matcher_rules FROM debtor_owner_candidates"
                        ).fetchall() == [(1, ["lien_names_parcel"])]  # fmt: skip


def test_net_equity_pairs_mortgages_with_releases(rich: duckdb.DuckDBPyConnection) -> None:
    from equity.search import show_parcel

    (p,) = [r for r in show_parcel(rich, "39049-010-1") if r["source_id"] == "oh.franklin.parcels"]
    eq = p["equity"]
    assert (eq["value"], eq["mortgages"], eq["open_mortgages"], eq["open_principal"],
            eq["equity_est"]) == (180000.0, 2, 1, 100000.0, 80000.0)  # fmt: skip
    released = {d["instrument_uid"]: d["released"] for d in p["documents"]}
    assert released["m2"] is True and released["m1"] is False
    # no value for 39049-010-2, so no equity row; and only counties with recorder data get rows
    assert show_parcel(rich, "39049-010-2")[0]["equity"] is None
    assert rich.execute("SELECT count(*) FROM parcel_equity WHERE left(parcel_uid, 5) <> '39049'"
                        ).fetchone() == (0,)  # fmt: skip


def test_owners_as_of_a_date_and_value_history(rich: duckdb.DuckDBPyConnection) -> None:
    from datetime import date

    from equity.search import show_parcel

    def owner(when: str) -> dict[str, Any]:
        (p,) = [r for r in show_parcel(rich, "39049-010-1", date.fromisoformat(when))
                if r["source_id"] == "oh.franklin.parcels"]  # fmt: skip
        out: dict[str, Any] = p["as_of"]
        return out

    early = owner("2025-03-01")
    assert [o["raw_name"] for o in early["snapshot_owners"]] == ["DOE, JANE"]
    assert "last_deed" not in early
    later = owner("2025-07-01")
    assert later["last_deed"]["grantees"] == ["SMITH, JOHN A"]
    assert owner("2024-01-01") == {"date": "2024-01-01"}  # nothing known then: no guess
    (p,) = [r for r in show_parcel(rich, "39049-010-1") if r["source_id"] == "oh.franklin.parcels"]
    assert [v["tax_year"] for v in p["value_history"]] == [2025, 2024]


def test_nicknames_flags_and_aliases(rich: duckdb.DuckDBPyConnection) -> None:
    from equity.search import show_business

    rules = {h.raw_name: h.rule for h in search(rich, "BOB SMITH")}
    assert rules["SMITH, ROBERT"] == "nickname"
    city = [h for h in search(rich, "City of Columbus")]
    assert city[0].name_flag == "government"
    assert rich.execute("SELECT count(*) FROM debtor_owner_candidates "
                        "WHERE debtor_name ILIKE 'city%'").fetchone() == (0,)  # fmt: skip
    b = show_business(rich, "oh.sos.business:business:B7")
    assert b is not None and [(a["name"], a["status"]) for a in b["aka"]] == [
        ("OLD ACME LLC", "former name")]  # fmt: skip


def test_grade_pair_follows_the_matcher_rules(rich: duckdb.DuckDBPyConnection) -> None:
    from equity.search import grade_pair

    g = grade_pair(rich, "oh.cuyahoga.liens:d1", "oh.franklin.parcels:o1")
    assert (g["grade"], g["rule"]) == ("A", "lien_names_parcel")  # the lien names o1's parcel
    assert grade_pair(rich, "oh.cuyahoga.liens:d1", "oh.franklin.parcels:o7")["grade"] == "reject"
    assert grade_pair(rich, "oh.cuyahoga.liens:d1", "oh.franklin.parcels:o8")["rule"] == (
        "flag_government")  # fmt: skip
    assert grade_pair(rich, "x:y", "oh.franklin.parcels:o1")["rule"] == "not_found"


def test_grade_pair_name_rules(cat: duckdb.DuckDBPyConnection) -> None:
    from equity.search import grade_pair

    # same name and address, no lien on the parcel (the business-registry record)
    g = grade_pair(cat, "oh.cuyahoga.liens:d1", "oh.franklin.parcels:o1")
    assert g["grade"] == "A"
    assert grade_pair(cat, "oh.sos.business:m1", "oh.franklin.parcels:o1")["rule"] == "name_only"


def test_golden_harness_scores_cases(rich: duckdb.DuckDBPyConnection, tmp_path: Path) -> None:
    from equity.search_golden import load_cases, report, run

    (tmp_path / "c.yaml").write_text(yaml.safe_dump([
        {"id": "good", "query": "Smith, John A", "state": "OH",
         "expect": {"refs": ["oh.franklin.parcels:o1"], "not_refs": ["oh.franklin.parcels:o7"],
                    "pairs": [{"debtor": "oh.cuyahoga.liens:d1",
                               "owner": "oh.franklin.parcels:o1", "grade": "A"}]}},
        {"id": "bad", "query": "Smith, John A",
         "expect": {"refs": ["oh.nowhere:zz"],
                    "pairs": [{"debtor": "oh.cuyahoga.liens:d1",
                               "owner": "oh.franklin.parcels:o1", "grade": "C"}]}},
    ]))  # fmt: skip
    results = run(rich, load_cases(tmp_path))
    assert [(r.case_id, r.ok, r.checks) for r in results] == [("good", True, 3), ("bad", False, 2)]
    text = report(results)
    assert text.startswith("2 cases, 5 checks, 3 passed, 2 failed")
    assert "grade A (lien_names_parcel), expected C" in text
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump({"query": "x"}))
    with pytest.raises(ValueError, match="needs an id"):
        load_cases(tmp_path)


def test_one_edit_neighbours() -> None:
    from equity.search import _one_edit

    assert [_one_edit("MARIA", w) for w in ("MAIA", "MARIAS", "MARTA", "MAIRA", "MRAIA")] == [
        True, True, True, True, True]  # fmt: skip
    assert not _one_edit("MARIA", "MIRA") and not _one_edit("MARIA", "MARIA S")


def test_extra_word_ranks_below_the_sound_alike(cat: duckdb.DuckDBPyConnection) -> None:
    from equity.search import rank, strict_keys

    rows = rank(cat, "JOHNSN MARY", ["JOHNSON MARY", "ADAM JOHNSON MARY"])
    assert [(r[0], r[1]) for r in rows] == [("JOHNSON MARY", "typo"),
                                            ("ADAM JOHNSON MARY", "sounds_like")]  # fmt: skip
    assert rows[0][3] > rows[1][3]
    # every query word in some form (here a dropped letter in each): no cap, no rare-word luck
    assert "A JOHN SMITH" in strict_keys(cat, "JOHN SMTH")
    # one edit finds a word even when the dropped letter changes its Soundex code
    assert "A JOHN SMITH" in strict_keys(cat, "JOHN SITH")
    assert strict_keys(cat, "JOHN") == set()  # one word: the capped lists handle it


def test_sort_table_in_chunks_keeps_every_row_in_order(
    cat: duckdb.DuckDBPyConnection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import equity.search_index as si

    cat.execute("CREATE TABLE t AS SELECT * FROM (VALUES ('BB', 1), ('AA', 2), (NULL, 3), "
                "('AB', 4), ('BA', 5), ('AA', 6)) v(k, n)")  # fmt: skip
    monkeypatch.setattr(si, "SORT_CHUNK_ROWS", 2)  # several chunks of two-letter prefixes
    si.sort_table(cat, "t", "k", tmp_path / "sort")
    keys = [r[0] for r in cat.execute("SELECT k FROM t").fetchall()]
    assert keys == ["AA", "AA", "AB", "BA", "BB", None]
    assert not (tmp_path / "sort").exists()


def test_supplements_load_by_their_own_version(lake: Path, tmp_path: Path) -> None:
    from equity.search_index import index_supplements

    bk = "us.ohnb.rss"
    _write(lake, bk, "bankruptcy", [
        {"case_uid": "ohnb:1:25-bk-1", "chapter": "7", "petition_on": "2025-02-01",
         "discharge_on": None, "dismissed_on": None, "converted_on": None,
         "trustee_party_id": None, "asset_case": False, "source_id": bk, "superseded_at": None},
    ])  # fmt: skip
    _finish(lake, bk, {"bankruptcy": 1})
    ct = "ct.opm.equalized_grand_list"
    _write(lake, ct, "assessment_ratio", [
        {"geo_level": "town", "geo_id": "09001-01", "geo_name": "TESTTOWN", "year": 2024,
         "property_class": "residential", "ratio_kind": "sales", "ratio_pct": 70.0,
         "source_id": ct, "superseded_at": None},
    ])  # fmt: skip
    _finish(lake, ct, {"assessment_ratio": 1})
    fl = "fl.testcounty.civil"
    _write(lake, fl, "judgment", [
        {"judgment_uid": "j1", "case_uid": "flx:1", "entered_on": "2024-01-02",
         "principal": None, "interest": 120.5, "costs": None, "rate": 0.0912,
         "judgment_type": "money", "lien_instrument_uid": None, "source_id": fl,
         "superseded_at": None},
        {"judgment_uid": "j2", "case_uid": "flx:2", "entered_on": "2024-01-03",
         "principal": None, "interest": None, "costs": None, "rate": None,
         "judgment_type": "money", "lien_instrument_uid": None, "source_id": fl,
         "superseded_at": None},  # nothing worth keeping
    ])  # fmt: skip
    _finish(lake, fl, {"judgment": 2})
    con = connect(tmp_path / "s.duckdb")
    src = FileSource(lake)
    loaded = index_supplements(con, src, log=lambda _m: None)
    assert {bk, ct, fl} <= set(loaded)
    assert con.execute("SELECT chapter, petition_on::VARCHAR FROM bankruptcies").fetchall() == [
        ("7", "2025-02-01")]  # fmt: skip
    assert con.execute("SELECT ratio_pct FROM assessment_ratios").fetchall() == [(70.0,)]
    assert con.execute("SELECT judgment_uid, rate::DOUBLE FROM judgment_terms").fetchall() == [
        ("j1", 0.0912)]  # fmt: skip
    assert index_supplements(con, src, log=lambda _m: None) == []  # unchanged: nothing to do
    assert index_supplements(con, src, states=["OH"], force=True, log=lambda _m: None) == [
        "oh.cuyahoga.liens", "oh.franklin.parcels", "oh.sos.business", bk]  # fmt: skip


def test_parcel_shows_supplements(cat: duckdb.DuckDBPyConnection) -> None:
    from equity.search import house_price_adjustment, show_parcel, town_assessment_ratio

    cat.execute(
        "INSERT INTO house_prices VALUES ('us.fhfa.hpi_zip5', 'zip5', '43215', 2020, "
        "0, 200.0, NULL), ('us.fhfa.hpi_zip5', 'zip5', '43215', 2025, 0, 260.0, 4.1)"
    )
    cat.execute("INSERT INTO tax_delinquencies VALUES ('wv.statewide.delinquent', '39049-010-1',"
                " 'C-1', 'certified', 2, DATE '2025-06-01')")  # fmt: skip
    cat.execute("INSERT INTO value_parts VALUES ('oh.franklin.parcels', '39049-010-1', 2024, "
                "40000, 140000, 'R')")  # fmt: skip
    cat.execute("INSERT INTO assessment_ratios VALUES ('ny.orpts.residential_assessment_ratios',"
                " 'ny_swis', '010100', 'TESTTOWN', 2024, 'residential',"
                " 'residential_assessment_ratio', 85.71)")  # fmt: skip
    hpi = house_price_adjustment(cat, "43215", 2020, 100000)
    assert hpi is not None and (hpi["to_year"], hpi["factor"], hpi["adjusted_value"]) == (
        2025, 1.3, 130000)  # fmt: skip
    assert house_price_adjustment(cat, "43215", 2019, 100000) is None  # no index for the year
    assert house_price_adjustment(cat, None, 2020, 100000) is None
    ratio = town_assessment_ratio(cat, "ny.albany.parcels", "testtown", 2024)
    assert ratio is not None and (ratio["ratio_pct"], ratio["matched_on"]) == (
        85.71, "situs town name")  # fmt: skip
    assert town_assessment_ratio(cat, "oh.franklin.parcels", "testtown", 2024) is None
    p = show_parcel(cat, "39049-010-1")[0]
    assert [d["status_raw"] for d in p["tax_delinquency"]] == ["certified"]
    assert [(v["appraised_land"], v["appraised_bldg"]) for v in p["value_parts"]] == [
        (40000, 140000)]  # fmt: skip
    assert p["parcel_links"] == [] and p["owner_types"] == []


def test_leads_table_grades_and_ranks(cat: duckdb.DuckDBPyConnection) -> None:
    compact(cat)
    rows = cat.execute("""
        SELECT state, grade, grade_rule, debts, debt_amount, owned_parcels, homestead_any,
               deeds_after_debt, same_name_bankruptcies, first_debt_age_days > 0
        FROM leads""").fetchall()  # fmt: skip
    assert len(rows) == 1
    state, grade, rule, debts, amount, owned, homestead, deeds, bk, aged = rows[0]
    assert (state, debts, amount, owned, deeds, bk, aged) == ("OH", 1, 12500.0, 1, 0, 0, True)
    from equity.search import grade_pair

    pair = grade_pair(cat, "oh.cuyahoga.liens:d1", "oh.franklin.parcels:o1")
    assert (grade, rule) == (pair["grade"], pair["rule"]) == ("A", "lien_names_parcel")
    assert homestead in (True, False)
