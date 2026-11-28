"""Arkansas COSL unsold tax-delinquent parcels: one lien per listing, owner split, parcel key."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from equity.adapters.ar.cosl_unsold import URL, ArkansasUnsoldTaxParcels, owner_names
from equity.adapters.base import FetchRequest
from equity.adapters.http import Response

AT = datetime(2026, 11, 28, tzinfo=UTC)


def _listing(pid: int, owner: str, county: str, parcel: str, bid: float) -> dict[str, object]:
    return {"Owner": owner, "CoSLCountyName": county, "CoSLParcelNumber": parcel,
            "Acreage": 0.25, "StartingBid": bid, "CoSLPropertyId": pid, "SaleType": "S2",
            "Added": "2026-11-17T07:00:02.524218", "Section": "5", "Township": "20N",
            "Range": "5W", "ListingToken": "x", "GisId": 1}  # fmt: skip


class _Client:
    def __init__(self, rows: list[dict[str, object]], total: int | None = None) -> None:
        self.rows, self.total = rows, len(rows) if total is None else total
        self.fields: dict[str, str] = {}

    def post_form(self, url: str, fields: dict[str, str]) -> Response:
        assert url == URL
        self.fields = fields
        body = json.dumps({"Data": self.rows, "Total": self.total, "Errors": None}).encode()
        return Response(url, 200, body, "application/json", AT)


def test_owner_names_split_on_percent_and_drop_care_of() -> None:
    assert owner_names("RICKY N  NICHOLSON%SUSAN E NICHOLSON") == [
        "RICKY N NICHOLSON", "SUSAN E NICHOLSON"]  # fmt: skip
    assert owner_names("LOUISE J  MONK C/O BENJAMIN MONK") == ["LOUISE J MONK"]
    assert owner_names("") == []


def test_listing_is_a_parcel_linked_state_tax_lien() -> None:
    rows = [
        _listing(833473, "CHARLES  JOHNSON% DORIS JOHNSON", "FULTON", "627-31057-000", 393.46),
        _listing(9, "ANN LEE", "ST FRANCIS", "001-00001-000", 50.0),
        _listing(10, "NO BID", "PULASKI", "1", 0.0),  # no amount: skipped
        _listing(11, "NOWHERE", "ATLANTIS", "2", 5.0),
    ]  # unknown county: skipped
    client = _Client(rows)
    a = ArkansasUnsoldTaxParcels(client)  # type: ignore[arg-type]
    fetched = a.fetch(FetchRequest({}))
    assert client.fields["pageSize"] == "100000"
    assert "ListingToken" not in json.loads(fetched.content)["rows"][0]
    out = [(t.table, dict(t.row)) for t in a.normalize(fetched)]
    inst = {x["instrument_number"]: x for t, x in out if t == "instrument"}
    assert sorted(inst) == ["833473", "9"]
    assert (inst["833473"]["doc_type"], inst["833473"]["principal_amount"],
            inst["833473"]["recorded_on"]) == ("TAX_LIEN_STATE", Decimal("393.46"),
                                               date(2026, 11, 17))  # fmt: skip
    assert sorted(x["parcel_uid"] for t, x in out if t == "instrument_parcel") == [
        "05049-627-31057-000", "05123-001-00001-000"]  # fmt: skip
    debtors = {x["party_id"] for t, x in out if t == "instrument_party" and x["role"] == "debtor"}
    names = {x["raw_name"] for t, x in out if t == "party" and x["party_id"] in debtors}
    assert names == {"CHARLES JOHNSON", "DORIS JOHNSON", "ANN LEE"}
    assert "Arkansas Commissioner of State Lands" in {x["raw_name"] for t, x in out
                                                     if t == "party"}  # fmt: skip


def test_short_page_fails_rather_than_loading_part_of_the_list() -> None:
    a = ArkansasUnsoldTaxParcels(_Client([_listing(1, "A B", "CLAY", "1", 1.0)], total=2))  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="1 of 2"):
        a.fetch(FetchRequest({}))
