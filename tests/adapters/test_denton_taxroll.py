"""Denton County delinquent tax roll: the Collin layout, the AM zip found by its first member."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime

from equity.adapters.base import FetchRequest
from equity.adapters.http import Response
from equity.adapters.tx.denton_taxroll import (
    LISTING,
    DentonMineralTaxDelinquent,
    DentonPersonalPropertyDelinquent,
    DentonTaxRollDelinquent,
    first_member,
)

AT = datetime(2025, 12, 31, tzinfo=UTC)


def _fixed(width: int, fields: dict[tuple[int, int], str]) -> str:
    line = [" "] * width
    for (a, b), v in fields.items():
        line[a - 1 : b] = list(v.ljust(b - a + 1)[: b - a + 1])
    return "".join(line)


def _zip(members: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in members.items():
            z.writestr(name, text)
    return buf.getvalue()


MASTER = "\r\n".join([
    _fixed(950, {(1, 30): "295693DEN", (34, 36): "001", (174, 203): "295693DEN",
                 (335, 384): "LANDA VALENTE", (435, 484): "1 MAIN ST", (535, 584): "DENTON",
                 (585, 604): "TX", (605, 622): "76201"}),
    _fixed(950, {(1, 30): "767116WIS", (34, 36): "001", (335, 384): "ROE JO"}),
    _fixed(950, {(1, 30): "900001DEN", (34, 36): "002", (335, 384): "BIZ INC"}),
    _fixed(950, {(1, 30): "800001DEN", (34, 36): "003", (335, 384): "ROYALTY LLC"}),
])  # fmt: skip
REC = "\r\n".join(
    _fixed(224, {(1, 30): acct, (31, 34): "2024", (35, 37): "001", (76, 87): "000000100.00",
                 (88, 97): "02/01/2025"})
    for acct in ("295693DEN", "767116WIS", "900001DEN", "800001DEN")
)  # fmt: skip
FULL = _zip({"MM112526.DAT": "x", "MR112526.DAT": "x"})
DELQ = _zip({"AM112526.DAT": MASTER, "AR112526.DAT": REC})


class _Client:
    """The listing, two zips (full roll first), and ranged reads of their first bytes."""

    def __init__(self) -> None:
        self.files = {"TaxRoll_V1_1.zip": FULL, "TaxRoll_V1_2.zip": DELQ}

    def get(self, url: str, params: object = None) -> Response:
        if url == LISTING:
            body = "".join(f'<a href="Download.ashx?file={n}">' for n in self.files).encode()
            return Response(url, 200, body, "text/html", AT)
        return Response(url, 200, self.files[url.rsplit("=", 1)[1]], "application/zip", AT)

    def get_range(self, url: str, first: int, last: int) -> Response:
        data = self.files[url.rsplit("=", 1)[1]][first : last + 1]
        return Response(url, 206, data, "application/zip", AT)


def test_first_member_reads_the_zip_local_header() -> None:
    assert first_member(DELQ[:100]) == "AM112526.DAT"
    assert first_member(b"<html>") is None


def test_delinquent_roll_is_the_am_zip_and_own_accounts_link_to_their_parcel() -> None:
    a = DentonTaxRollDelinquent(_Client())  # type: ignore[arg-type]
    assert a.file_url().endswith("TaxRoll_V1_2.zip")
    out = [(t.table, dict(t.row)) for t in a.normalize(a.fetch(FetchRequest({})))]
    assert sorted(x["instrument_number"] for t, x in out if t == "instrument") == [
        "295693DEN", "767116WIS"]  # fmt: skip
    assert [x["parcel_uid"] for t, x in out if t == "instrument_parcel"] == ["48121-295693"]
    p = DentonPersonalPropertyDelinquent(_Client())  # type: ignore[arg-type]
    pout = [(t.table, dict(t.row)) for t in p.normalize(p.fetch(FetchRequest({})))]
    assert [x["instrument_number"] for t, x in pout if t == "instrument"] == ["900001DEN"]
    assert not [x for t, x in pout if t == "instrument_parcel"]


def test_mineral_accounts_are_roll_003_with_no_parcel() -> None:
    m = DentonMineralTaxDelinquent(_Client())  # type: ignore[arg-type]
    out = [(t.table, dict(t.row)) for t in m.normalize(m.fetch(FetchRequest({})))]
    assert [x["instrument_number"] for t, x in out if t == "instrument"] == ["800001DEN"]
    assert not [x for t, x in out if t == "instrument_parcel"]
