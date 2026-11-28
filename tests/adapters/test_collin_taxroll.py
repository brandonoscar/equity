"""Collin County delinquent tax roll: the Tarrant reader with Collin's layout and a parcel link."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, date, datetime

from equity.adapters.base import FetchRequest
from equity.adapters.http import Response
from equity.adapters.tx.collin_taxroll import MASTER, REC, URL, CollinTaxRollDelinquent
from equity.adapters.tx.tarrant_taxroll import delinquent_accounts

AT = datetime(2025, 12, 31, tzinfo=UTC)


def _fixed(width: int, fields: dict[tuple[int, int], str]) -> str:
    line = [" "] * width
    for (a, b), v in fields.items():
        line[a - 1 : b] = list(v.ljust(b - a + 1)[: b - a + 1])
    return "".join(line)


def _master(account: str, roll: str, owner: str, cad: str) -> str:
    return _fixed(950, {(1, 30): account, (34, 36): roll, (174, 203): cad, (335, 384): owner,
                        (435, 484): "1 MAIN ST", (535, 584): "PLANO", (585, 604): "TX",
                        (605, 622): "75075"})  # fmt: skip


def _rec(account: str, year: str, due: str, delinquent_on: str,
         judged: str = "01/01/9999") -> str:  # fmt: skip
    return _fixed(224, {(1, 30): account, (31, 34): year, (35, 37): "001", (76, 87): due,
                        (88, 97): delinquent_on, (108, 117): judged,
                        (191, 191): "Y"})  # fmt: skip


class _Client:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get(self, url: str, params: object = None) -> Response:
        assert url == URL
        return Response(url, 200, self.body, "application/zip", AT)


def test_collin_layout_sums_real_and_commercial_accounts_and_links_the_parcel() -> None:
    master = [_master("R1", "001", "ANN LEE", "2728382"),
              _master("P2", "002", "BIZ INC", "2656280"),  # personal property
              _master("C3", "008", "MALL LLC", "33546")]  # fmt: skip
    rec = [_rec("R1", "2023", "000000100.00", "02/01/2024", "06/30/2025"),
           _rec("R1", "2025", "000000999.00", "02/01/2026"),  # not yet delinquent
           _rec("P2", "2024", "000000010.00", "02/01/2025"),
           _rec("C3", "2024", "000000020.25", "02/01/2025")]  # fmt: skip
    rows = delinquent_accounts(master, rec, date(2025, 12, 31), MASTER, REC, ("001", "008"))
    assert [(r["account"], r["amount"], r["installment"]) for r in rows] == [
        ("C3", "20.25", True), ("R1", "100.00", True)]  # fmt: skip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("AS112126.DAT", "x")
        z.writestr("AM112126.DAT", "\r\n".join(master))
        z.writestr("AR112126.DAT", "\r\n".join(rec))
    a = CollinTaxRollDelinquent(_Client(buf.getvalue()))  # type: ignore[arg-type]
    fetched = a.fetch(FetchRequest({}))
    assert [r["account"] for r in json.loads(fetched.content)["rows"]] == ["C3", "R1"]
    out = [(t.table, dict(t.row)) for t in a.normalize(fetched)]
    inst = {x["instrument_number"]: x for t, x in out if t == "instrument"}
    assert (inst["R1"]["doc_type"], inst["C3"]["doc_type"]) == ("COURT_ORDER", "TAX_LIEN_STATE")
    assert inst["R1"]["doc_type_raw"].startswith("Collin County tax suit judgment")
    assert sorted(x["parcel_uid"] for t, x in out if t == "instrument_parcel") == [
        "48085-2728382", "48085-33546"]  # fmt: skip
    assert "Collin County Tax Assessor-Collector" in {x["raw_name"] for t, x in out
                                                      if t == "party"}  # fmt: skip
