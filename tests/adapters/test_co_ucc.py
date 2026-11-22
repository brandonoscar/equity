"""Colorado UCC: one instrument per transaction, amendments linked to the original filing."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from equity.adapters.base import Fetched
from equity.adapters.co_ucc import ColoradoUCC, doc_type_of
from equity.schema.ids import stable_id


def test_doc_types() -> None:
    init = {"transactiontype": "Initial Filing"}
    assert doc_type_of({**init, "filingtype": "ucc"}) == ("FIXTURE_FILING", None)
    assert doc_type_of({**init, "filingtype": "lien_irs"}) == ("TAX_LIEN_FEDERAL", None)
    assert doc_type_of({**init, "filingtype": "lien_hosp"}) == ("STATUTORY_LIEN", None)
    amend = {"transactiontype": "Amendment"}
    assert doc_type_of({**amend, "terminationflag": True}) == ("RELEASE", "releases")
    assert doc_type_of({**amend, "documenttype": "IRS termination/release"})[0] == "RELEASE"
    assert doc_type_of({**amend, "continuation": True}) == ("EXTENSION", "extends")
    assert doc_type_of({**amend}) == ("MODIFICATION", "modifies")
    assert doc_type_of({"transactiontype": "Correction"}) == ("MODIFICATION", "corrects")


def test_transactions_parties_and_links() -> None:
    body = {
        "filings": [
            {"transactionid": "100", "masterdocumentid": "100", "fileid": "1",
             "transactiontype": "Initial Filing", "filingtype": "lien_irs",
             "documenttype": "IRS tax lien", "filingdate": "2020-01-02T00:00:00.000",
             "lapsedate": "2030-01-02T00:00:00.000"},
            {"transactionid": "101", "masterdocumentid": "100", "fileid": "2",
             "transactiontype": "Amendment", "terminationflag": True,
             "documenttype": "IRS termination/release", "filingdate": "2022-05-01T00:00:00.000"},
            {"transactionid": "", "fileid": "3", "filingdate": "2022-05-01"},  # no id: skipped
        ],
        "debtors": [
            {"fileid": "1", "firstname": "ANN", "middlename": "B", "lastname": "TEST",
             "suffix": "JR", "address1": "1 TEST ST", "city": "Denver", "state": "CO",
             "zipcode": "80202", "recordstatus": "active", "actiontype": "add"},
            {"fileid": "1", "organizationname": "TEST CO LLC", "recordstatus": "inactive"},
            {"fileid": "1", "organizationname": "GONE LLC", "actiontype": "delete only"},
        ],
        "secured": [{"fileid": "1", "organizationname": "INTERNAL REVENUE SERVICE",
                     "recordstatus": "active", "actiontype": "add"}],
    }  # fmt: skip
    f = Fetched("co.sos.ucc", "x", datetime(2026, 11, 22, tzinfo=UTC), 200,
                json.dumps(body).encode(), "application/json")  # fmt: skip
    rows = list(ColoradoUCC().normalize(f))
    by = lambda t: [r.row for r in rows if r.table == t]  # noqa: E731
    inst = {i["instrument_number"]: i for i in by("instrument")}
    assert set(inst) == {"100", "101"}
    assert (inst["100"]["doc_type"], inst["100"]["maturity_date"]) == (
        "TAX_LIEN_FEDERAL", date(2030, 1, 2))  # fmt: skip
    (ref,) = by("instrument_ref")
    assert (ref["ref_type"], ref["to_uid"]) == (
        "releases",
        stable_id("co.sos.ucc", "filing", "100"),
    )
    assert ref["to_uid"] == inst["100"]["instrument_uid"]
    people = {p["raw_name"]: p for p in by("party")}
    assert set(people) == {"ANN B TEST JR", "INTERNAL REVENUE SERVICE"}  # removed debtors dropped
    ann = people["ANN B TEST JR"]
    assert (ann["first_name"], ann["middle"], ann["last_name"], ann["suffix"], ann["party_kind"]) \
        == ("ANN", "B", "TEST", "JR", "person")  # fmt: skip
    roles = sorted((ip["role"], ip["seq"]) for ip in by("instrument_party"))
    assert roles == [("creditor", 1), ("debtor", 2)]


def test_partitions_cover_every_fileid(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from equity.adapters import co_ucc

    seen = {}

    def fake_page(client: object, query: object, offset: int) -> SimpleNamespace:
        seen["params"] = query.params(offset)  # type: ignore[attr-defined]
        return SimpleNamespace(content=b'[{"fileid": "120000"}]')

    monkeypatch.setattr(co_ucc, "get_page", fake_page)
    parts = list(ColoradoUCC().partitions())
    assert parts == [{"lo": "0", "hi": "50000"}, {"lo": "50000", "hi": "100000"},
                     {"lo": "100000", "hi": "150000"}]  # fmt: skip
    assert seen["params"]["$order"].startswith("fileid DESC")  # no aggregate: Socrata rejects it
