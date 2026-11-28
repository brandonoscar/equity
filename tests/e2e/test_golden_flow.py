"""The real-case golden flow on a synthetic index: sample candidates, a person fills in the
verdict, promote writes a pseudonymized scenario, and that scenario passes the e2e runner."""

from __future__ import annotations

from pathlib import Path

import yaml

from equity import golden
from tests.e2e.test_scenarios import _config, _index, check
from tests.e2e.world import write_sources

SRC = "oh.testcounty.parcels"
LIENS = "oh.testcounty.liens"


def _world(lake: Path) -> None:
    def addr(aid: str, n: int, z: str) -> dict[str, str]:
        return {"address_id": aid, "line1": f"{n} OAK TEST ST", "city": "TESTBURG",
                "state": "OH", "zip5": z}  # fmt: skip

    write_sources(lake, {
        SRC: {"party": [{"party_id": "o1", "raw_name": "TESTOWNER QUINCY ADAMS JR",
                         "address_id": "a1"}],
              "owner_snapshot": [{"party_id": "o1", "parcel_uid": "39001-0042"}],
              "parcel": [{"parcel_uid": "39001-0042", "jurisdiction": "39001",
                          "situs_address_id": "a2"}],
              "parcel_assessment": [{"parcel_uid": "39001-0042", "tax_year": 2025,
                                     "appraised_total": 150000}],
              "address": [addr("a1", 77, "43117"), addr("a2", 78, "43117")]},
        LIENS: {"party": [{"party_id": "d1", "raw_name": "ADAMS, TESTOWNER QUINCY JR.",
                           "address_id": "a1"}],
                "instrument": [{"instrument_uid": "j1", "doc_type": "JUDGMENT_LIEN",
                                "recorded_on": "2024-05-05", "principal_amount": 9000}],
                "instrument_party": [{"instrument_uid": "j1", "party_id": "d1",
                                      "role": "debtor"}],
                "address": [addr("a1", 77, "43117")]},
    })  # fmt: skip


def test_candidates_session_promote_and_replay(tmp_path: Path) -> None:
    _world(tmp_path / "lake")
    con = _index(tmp_path / "lake", tmp_path / "i.duckdb")
    cases = golden.candidates(con, per_rule=2)
    assert [c["ours"] for c in cases] == [{"grade": "A", "rule": "name_address"}]
    strata = {s["id"] for s in cases[0]["strata"]}
    assert {"rule_name_address", "edge_suffix"} <= strata
    session = golden.write_session(cases, tmp_path / "sessions", "s1")
    assert "Why it is in the set" in (session / "checklist.md").read_text()

    data = yaml.safe_load((session / "cases.yaml").read_text())
    assert data["cases"][0]["verified"]["grade"] is None  # blank for the person
    assert golden.promote(con, session / "cases.yaml", tmp_path / "out") == []  # unverified
    data["cases"][0]["verified"].update({"same_person": "yes", "grade": "A",
                                         "verified_by": "TESTOWNER VERIFIER"})  # fmt: skip
    (session / "cases.yaml").write_text(yaml.safe_dump(data))
    [path] = golden.promote(con, session / "cases.yaml", tmp_path / "out")
    text = path.read_text()
    for real in ("QUINCY", "ADAMS", "OAK TEST ST", "43117", "39001-0042", "o1", "d1", "j1",
                 "testcounty"):  # fmt: skip
        assert real not in text, real  # nothing of the case survives but its structure
    scenario = yaml.safe_load(text)
    assert scenario["name"] == path.stem and "verified by a person" in scenario["doc"]
    con.close()

    # The promoted scenario replays in the CI runner: same structure, same answer.
    lake2 = tmp_path / "lake2"
    write_sources(lake2, scenario["sources"])
    con2 = _index(lake2, tmp_path / "i2.duckdb")
    assert check(con2, scenario["expect"][0], _config(tmp_path, {}), {}, 0) == []
    con2.close()


def test_pseudonyms_keep_equal_values_equal_and_initials() -> None:
    ps = golden.Pseudonyms("x")
    a, b = ps.name("SMITH, JOHN A JR"), ps.name("JOHN A SMITH JR.")
    assert a is not None and b is not None and sorted(a.split()) == sorted(b.split())
    assert a.startswith("TESTOWNER") and " A " in f" {a} " and a.endswith("JR")
    assert ps.name("JOHN SMITH SR") != ps.name("JOHN SMITH JR")
    assert ps.zip5("43117") == ps.zip5("43117") != ps.zip5("43118")
    assert ps.street("1 MAIN ST") == ps.street("1 MAIN ST") != ps.street("2 MAIN ST")
