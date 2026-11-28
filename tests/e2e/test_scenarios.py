"""End-to-end scenarios: each file in scenarios/ is a tiny synthetic world and the answers the
whole pipeline must give on it (see world.py for the format). One file per rule or edge, so a
change that breaks a rule fails by name. These are the public, pseudonymized half of the
golden set; real cases verified by hand live in config/private/golden_search/ (git-ignored)
and are promoted here as pseudonymized scenarios (equity.golden promote)."""

from __future__ import annotations

import copy
import re
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pytest
import yaml

from equity import facts, forensic, search, watch
from equity.search_index import (
    FileSource,
    build,
    compact,
    connect,
    index_matcher,
    index_supplements,
)
from tests.e2e.world import write_derived, write_sources

SCENARIOS = sorted((Path(__file__).parent / "scenarios").glob("*.yaml"))
AS_OF = date(2026, 11, 27)  # fixed, so ages and years left do not drift


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    assert data["name"] == path.stem, f"{path.name}: name must match the file name"
    assert data.get("doc"), f"{path.name}: say in doc what rule the scenario pins"
    return data


def _config(tmp: Path, cfg: dict[str, Any]) -> Path:
    """Owner config for this scenario only (defaults: every owner decision unset)."""
    d = tmp / "config"
    d.mkdir()
    rules = cfg.get("rules", {"transfer_flags": {"nominal_consideration_max": None}})
    (d / "rules.yaml").write_text(yaml.safe_dump(rules))
    (d / "sol.yaml").write_text(yaml.safe_dump({"states": cfg.get("sol", {})}))
    return d


def _same(got: Any, want: Any) -> bool:
    if isinstance(want, dict) and isinstance(got, dict):
        return set(got) == set(want) and all(_same(got[k], want[k]) for k in want)
    if isinstance(want, float) or isinstance(got, float):
        return got is not None and want is not None and abs(float(got) - float(want)) < 0.01
    if isinstance(got, date):
        return str(got) == str(want)
    if isinstance(want, list) and isinstance(got, list):
        return len(got) == len(want) and all(_same(g, w) for g, w in zip(got, want, strict=True))
    if hasattr(got, "__float__") and isinstance(want, int) and not isinstance(got, bool):
        return float(got) == float(want)
    return bool(got == want)


def _check_fields(where: str, got: dict[str, Any], want: dict[str, Any]) -> list[str]:
    return [f"{where}.{k}: got {got.get(k)!r}, want {v!r}" for k, v in want.items()
            if not _same(got.get(k), v)]  # fmt: skip


def _index(lake: Path, db: Path) -> duckdb.DuckDBPyConnection:
    con = connect(db)
    src = FileSource(lake)
    build(con, src, workers=1, log=lambda _m: None)
    index_matcher(con, src, log=lambda _m: None)
    index_supplements(con, src, log=lambda _m: None)
    compact(con)
    return con


def check(con: duckdb.DuckDBPyConnection, e: dict[str, Any], cfg: Path,
          baselines: dict[int, Path], i: int) -> list[str]:  # fmt: skip
    """The failures of one expectation (empty when it holds)."""
    got: Any
    rows: Any
    kind, x = next(iter(e.items()))
    if kind == "search":
        hits = search.search(con, x["query"], x.get("state"), x.get("kind"), x.get("limit", 25))
        refs = [h.ref for h in hits]
        out = []
        if "top" in x and (not refs or refs[0] != x["top"]):
            out.append(f"search {x['query']!r}: top {refs[:1]}, want {x['top']}")
        if "rule" in x and (not hits or hits[0].rule != x["rule"]):
            out.append(f"search {x['query']!r}: rule {hits[0].rule if hits else None}, "
                       f"want {x['rule']}")  # fmt: skip
        out += [f"search {x['query']!r}: missing {r}" for r in x.get("includes", [])
                if r not in refs]  # fmt: skip
        out += [f"search {x['query']!r}: must not return {r}" for r in x.get("excludes", [])
                if r in refs]  # fmt: skip
        if "count" in x and len(hits) != x["count"]:
            out.append(f"search {x['query']!r}: {len(hits)} hits, want {x['count']}")
        return out
    if kind == "grade":
        g = search.grade_pair(con, x["debtor"], x["owner"])
        return _check_fields("grade", g, {"grade": x["grade"], "rule": x["rule"]})
    if kind == "lead":
        rows = search._rows(con, "SELECT * FROM leads WHERE name_key = name_key(?) AND state = ?",
                            [x["name"], x["state"]])  # fmt: skip
        if x.get("absent"):
            return [f"lead {x['name']}: present, want absent"] if rows else []
        if len(rows) != 1:
            return [f"lead {x['name']} {x['state']}: {len(rows)} rows, want 1"]
        return _check_fields(f"lead {x['name']}", rows[0], x.get("fields", {}))
    if kind == "stack":
        s = forensic.priority_stack(con, x["parcel"], x.get("lien"))
        out = []
        if "order" in x:
            order = [d["instrument_uid"] for d in s["encumbrances"]]
            if order != x["order"]:
                out.append(f"stack {x['parcel']}: order {order}, want {x['order']}")
        if "released" in x:
            rel = sorted(d["instrument_uid"] for d in s["encumbrances"] if d["released"])
            if rel != sorted(x["released"]):
                out.append(f"stack {x['parcel']}: released {rel}, want {x['released']}")
        return out + _check_fields("stack.position", s.get("position") or {},
                                   x.get("position", {}))  # fmt: skip
    if kind == "badges":
        b = forensic.transfer_badges(con, x["debtor"], config_dir=cfg)
        deeds = {d["deed"].split(":", 1)[1]: d for d in b["deeds"]}
        out = []
        if "deeds" in x and sorted(deeds) != sorted(x["deeds"]):
            out.append(f"badges: deeds {sorted(deeds)}, want {sorted(x['deeds'])}")
        for uid, want in x.get("on", {}).items():
            got = set(deeds.get(uid, {}).get("badges", []))
            out += [f"badges {uid}: missing {m}" for m in want.get("has", []) if m not in got]
            out += [f"badges {uid}: must not have {m}" for m in want.get("lacks", [])
                    if m in got]  # fmt: skip
        return out
    if kind == "ring":
        r = forensic.entity_ring(con, x["debtor"])
        firms = {f["name"]: f for f in r["businesses"]}
        if "businesses" in x and sorted(firms) != sorted(x["businesses"]):
            return [f"ring: businesses {sorted(firms)}, want {sorted(x['businesses'])}"]
        out = []
        for name, want in x.get("on", {}).items():
            f = firms.get(name)
            if f is None:
                out.append(f"ring: no business {name}")
                continue
            if "parcels" in want:
                got = sorted(p["parcel_uid"] for p in f["parcels"])
                if got != sorted(want.pop("parcels")):
                    out.append(f"ring {name}: parcels {got}")
            if "deeds_from_debtor" in want:
                got = sorted(d["deed"].split(":", 1)[1] for d in f["deeds_from_debtor"])
                if got != sorted(want.pop("deeds_from_debtor")):
                    out.append(f"ring {name}: deeds {got}")
            out += _check_fields(f"ring {name}", f, want)
        return out
    if kind == "facts":
        rows = con.execute("SELECT lead_id FROM leads WHERE name_key = name_key(?) AND state = ?",
                           [x["name"], x["state"]]).fetchall()  # fmt: skip
        if len(rows) != 1:
            return [f"facts {x['name']}: {len(rows)} leads"]
        sheet = facts.fact_sheet(con, int(rows[0][0]), config_dir=cfg, as_of=AS_OF)
        assert sheet is not None
        out = _check_fields("facts.factors", sheet["factors"], x.get("factors", {}))
        out += [f"facts: no gap containing {g!r}" for g in x.get("gaps_include", [])
                if not any(g in s for s in sheet["gaps"])]  # fmt: skip
        out += [f"facts: unexpected gap containing {g!r}" for g in x.get("gaps_exclude", [])
                if any(g in s for s in sheet["gaps"])]  # fmt: skip
        return out
    if kind == "parcel":
        recs = search.show_parcel(con, x["parcel"])
        if not recs:
            return [f"parcel {x['parcel']}: not found"]
        out = []
        for path, want in x.get("fields", {}).items():
            got = recs[0]
            for part in path.split("."):
                got = got.get(part) if isinstance(got, dict) else None
            if not _same(got, want):
                out.append(f"parcel {x['parcel']}.{path}: got {got!r}, want {want!r}")
        return out
    if kind == "name_flag":
        got = con.execute("SELECT name_flag(?)", [x["raw_name"]]).fetchone()
        return [] if got and got[0] == x["flag"] else [f"name_flag {x['raw_name']!r}: {got}"]
    if kind == "watch":
        results = watch.check(con, x["entries"], baselines[i])
        out = []
        for r, want in zip(results, x.get("new", []), strict=False):
            got = r["new"]
            if sorted(got) != sorted(want):
                out.append(f"watch {r['key']}: new {got}, want {want}")
        return out
    if kind == "household":
        h = forensic.household(con, x["debtor"])
        links = {(lk["link"], lk.get("parcel_uid") or lk.get("ref")) for lk in h["leads"]}
        out = [f"household: missing {tuple(w)}" for w in x.get("includes", [])
               if tuple(w) not in links]  # fmt: skip
        out += [f"household: must not have {tuple(w)}" for w in x.get("excludes", [])
                if tuple(w) in links]  # fmt: skip
        return out
    if kind == "portfolios":
        rows = forensic.creditor_portfolios(con, x["state"], x.get("min_leads", 1))
        got = [(r["creditor"], int(r["leads"])) for r in rows]
        want = [tuple(w) for w in x["creditors"]]
        return [] if got == want else [f"portfolios: {got}, want {want}"]
    if kind == "timeline":
        kinds = [ev["kind"] for ev in forensic.timeline(con, x["debtor"])["events"]]
        it = iter(kinds)
        if not all(k in it for k in x["in_order"]):
            return [f"timeline: {kinds} lacks the order {x['in_order']}"]
        return []
    raise AssertionError(f"unknown expectation {kind}")


@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_scenario(path: Path, tmp_path: Path) -> None:
    sc = _load(path)
    lake, db = tmp_path / "lake", tmp_path / "index.duckdb"
    write_sources(lake, sc["sources"])
    write_derived(lake, sc.get("derived", {}))
    cfg = _config(tmp_path, sc.get("config", {}))
    con = _index(lake, db)
    baselines: dict[int, Path] = {}
    for i, e in enumerate(sc["expect"]):
        if "watch" in e:  # first look, before the scenario's later rows arrive
            baselines[i] = tmp_path / f"watch-{i}.json"
            watch.check(con, e["watch"]["entries"], baselines[i])
    if sc.get("then"):
        con.close()
        write_sources(lake, sc["then"])
        con = _index(lake, db)
    failures = [f for i, e in enumerate(sc["expect"]) for f in check(con, e, cfg, baselines, i)]
    con.close()
    assert failures == [], f"{path.name}: {sc['doc']}\n  " + "\n  ".join(failures)


def test_every_scenario_uses_pseudonyms_only() -> None:
    """The repo is public: scenario names start with TESTOWNER (organizations may be
    TESTOWNER ... LLC, governments COUNTY OF TEST...), street lines end in TEST ST."""
    bad = []
    for path in SCENARIOS:
        sc = yaml.safe_load(path.read_text())
        for part in ("sources", "then"):
            for _sid, tables in (sc.get(part) or {}).items():
                for row in tables.get("party", []):
                    n = str(row.get("raw_name", ""))
                    placeholder = not re.search(r"[A-Za-z]{2}", n)  # names nobody
                    if n and not placeholder and "TESTOWNER" not in n.upper():
                        bad.append(f"{path.name}: {n}")
                for table in ("address",):
                    for row in tables.get(table, []):
                        line = str(row.get("line1") or "")
                        if line and not line.upper().endswith("TEST ST"):
                            bad.append(f"{path.name}: {line}")
                for row in tables.get("business", []):
                    if "TESTOWNER" not in str(row.get("name", "")).upper():
                        bad.append(f"{path.name}: business {row.get('name')}")
    assert bad == []


def test_the_harness_fails_a_wrong_expectation(tmp_path: Path) -> None:
    """A scenario run that cannot fail proves nothing: flip one answer and it must fail."""
    sc = _load(Path(__file__).parent / "scenarios" / "grade_name_zip.yaml")
    lake, db = tmp_path / "lake", tmp_path / "i.duckdb"
    write_sources(lake, sc["sources"])
    con = _index(lake, db)
    cfg = _config(tmp_path, {})
    good = sc["expect"][0]
    bad = copy.deepcopy(good)
    bad["grade"]["grade"] = "A"
    assert check(con, good, cfg, {}, 0) == []
    assert check(con, bad, cfg, {}, 0) == ["grade.grade: got 'B', want 'A'"]
    lead = {"lead": {"name": "TESTOWNER ALPHA SMITH", "state": "OH", "fields": {"debts": 7}}}
    assert check(con, lead, cfg, {}, 0) == ["lead TESTOWNER ALPHA SMITH.debts: got 1, want 7"]
    con.close()
