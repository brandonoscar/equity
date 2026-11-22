"""Colorado Secretary of State UCC filings and statutory liens (data.colorado.gov, Public Domain).

Three datasets, joined on fileid (one fileid per transaction):
  wffy-3uut  transactions: initial filings and amendments, filing and lapse dates; every
             amendment names its original filing (masterdocumentid = the initial transactionid)
  8upq-58vz  debtors added or changed by a transaction: person name parts or organization,
             address
  ap62-sav4  secured parties, the same shape

Besides UCC financing statements the transactions include federal tax liens, hospital liens and
other statutory liens. Each transaction is one instrument:
  initial filing   UCC/EFS -> FIXTURE_FILING; IRS -> TAX_LIEN_FEDERAL; others -> STATUTORY_LIEN
  amendment        termination -> RELEASE (releases), continuation -> EXTENSION (extends),
                   other amendments and corrections -> MODIFICATION (modifies / corrects),
                   each with an instrument_ref to the original filing
Debtors are role debtor and secured parties role creditor, with first/middle/last/suffix kept
when the state gives them. The lapse date is the instrument's maturity_date.

Partitions are fileid ranges, so the three datasets are read for the same range and an
amendment links to its original filing by id, wherever that filing falls.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataQuery, fetch_all, get_page, parse_rows
from equity.adapters.state_parcels import normalized_address
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

PORTAL = "https://data.colorado.gov"
FILINGS, DEBTORS, SECURED = "wffy-3uut", "8upq-58vz", "ap62-sav4"
WINDOW = 50_000  # fileids per partition
INITIAL_TYPES = {"ucc": "FIXTURE_FILING", "efs": "FIXTURE_FILING", "lien_irs": "TAX_LIEN_FEDERAL"}
_ZIP5 = "0123456789"


def _text(v: Any) -> str | None:
    s = " ".join(str(v).split()) if v is not None else ""
    return s or None


def _date(v: Any) -> date | None:
    s = str(v or "")[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _flag(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("true", "1", "y", "yes")


def doc_type_of(tx: Mapping[str, Any]) -> tuple[str, str | None]:
    """(doc_type, ref_type to the original filing or None for an initial filing)."""
    kind = str(tx.get("transactiontype") or "")
    doc = str(tx.get("documenttype") or "").lower()
    if kind == "Initial Filing":
        return INITIAL_TYPES.get(str(tx.get("filingtype") or ""), "STATUTORY_LIEN"), None
    if _flag(tx.get("terminationflag")) or "termination" in doc or "release" in doc:
        return "RELEASE", "releases"
    if _flag(tx.get("continuation")) or "continuation" in doc:
        return "EXTENSION", "extends"
    if "correction" in kind.lower():
        return "MODIFICATION", "corrects"
    return "MODIFICATION", "modifies"


def person_name(r: Mapping[str, Any]) -> tuple[str | None, dict[str, str | None]]:
    org = _text(r.get("organizationname"))
    parts = {"first_name": _text(r.get("firstname")), "middle": _text(r.get("middlename")),
             "last_name": _text(r.get("lastname")), "suffix": _text(r.get("suffix"))}  # fmt: skip
    if org:
        return org, {k: None for k in parts}
    name = " ".join(p for p in (parts["first_name"], parts["middle"], parts["last_name"],
                                parts["suffix"]) if p)  # fmt: skip
    return (name or None), parts


def address(r: Mapping[str, Any]) -> dict[str, Any] | None:
    street = " ".join(x for x in (_text(r.get("address1")), _text(r.get("address2"))) if x)
    z = str(r.get("zipcode") or "").strip()
    zip5 = z[:5] if len(z) >= 5 and all(c in _ZIP5 for c in z[:5]) else None
    return normalized_address(street or None, _text(r.get("city")), _text(r.get("state")), zip5)


class ColoradoUCC(Adapter):
    source_id: ClassVar[str] = "co.sos.ucc"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = ("organizationname", "firstname", "middlename",
                                             "lastname", "address1", "address2")  # fmt: skip

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",
            "jurisdiction": "08",
            "access_method": "api",
            "base_url": f"{PORTAL}/resource/{FILINGS}.json",
            "terms_url": "https://data.colorado.gov/Business/Uniform-Commercial-Code-UCC-Filing-Information-in-/wffy-3uut",
            "terms_summary": (
                "Colorado Department of State UCC filing, debtor and secured party datasets on "
                "data.colorado.gov; license Public Domain. Records inactive two years or more "
                "may carry old data-entry errors (publisher's note)."
            ),
            "terms_checked_on": "2026-11-22",
            "robots_checked_on": "2026-11-22",
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        q = SocrataQuery(PORTAL, FILINGS, "fileid IS NOT NULL", (":id",), 1,
                         select=("max(fileid) AS hi",))  # fmt: skip
        hi = int(float(parse_rows(get_page(self.client, q, 0).content)[0]["hi"]))
        for lo in range(0, hi + 1, WINDOW):
            yield {"lo": str(lo), "hi": str(lo + WINDOW)}

    def _rows(self, dataset: str, where: str, limit: int | None) -> list[dict[str, Any]]:
        q = SocrataQuery(PORTAL, dataset, where, ("fileid", ":id"), limit or 50_000)
        rows, _ = fetch_all(self.client, q, max_pages=1 if limit else 10_000, sample=bool(limit))
        return rows

    def fetch(self, request: FetchRequest) -> Fetched:
        p = request.params
        lo, hi = int(p["lo"]), int(p["hi"])  # ints only reach the query
        limit = int(p["limit"]) if "limit" in p else None
        where = f"fileid >= {lo} AND fileid < {hi}"
        filings = self._rows(FILINGS, where, limit)
        if limit:  # a fixture keeps the parties of the transactions it sampled
            ids = sorted({int(float(r["fileid"])) for r in filings if r.get("fileid")})
            where = "fileid in (" + ",".join(str(i) for i in ids) + ")" if ids else "false"
        body = {"where": where, "filings": filings, "debtors": self._rows(DEBTORS, where, None),
                "secured": self._rows(SECURED, where, None)}  # fmt: skip
        return Fetched(self.source_id, f"{PORTAL}/resource/{FILINGS}.json?$where={where}",
                       datetime.now(UTC), 200, canonical_json(body),
                       "application/json")  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        parties: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        for role, key in (("debtor", "debtors"), ("creditor", "secured")):
            for r in data.get(key) or []:
                status = str(r.get("recordstatus") or r.get("recordstatuscd") or "").lower()
                action = str(r.get("actiontype") or "").lower()
                if status == "inactive" or action.startswith("delete"):
                    continue  # removed from the filing
                parties[str(r.get("fileid") or "").split(".")[0]].append((role, r))
        for tx in sorted(data.get("filings") or [], key=lambda r: str(r.get("transactionid"))):
            tid, master = _text(tx.get("transactionid")), _text(tx.get("masterdocumentid"))
            recorded = _date(tx.get("filingdate"))
            if tid is None or recorded is None:
                continue
            fileid = str(tx.get("fileid") or "").split(".")[0]
            doc_type, ref_type = doc_type_of(tx)
            uid = stable_id(self.source_id, "filing", tid)
            rows = {"filing": tx, "parties": [r for _, r in parties.get(fileid, [])]}
            ctx = RecordContext(fetched, "08", tid, "ucc_transaction", rows)
            yield ctx.source_record()
            yield ctx.fact(
                "instrument", instrument_uid=uid, instrument_number=tid, book_type=None,
                book=None, page=None, doc_type_raw=_text(tx.get("documenttype")),
                doc_type=doc_type, recorded_on=recorded, recorded_seq=None, executed_on=None,
                consideration=None, principal_amount=None, max_secured_amount=None,
                maturity_date=_date(tx.get("lapsedate")), amount_source=None,
                legal_desc_raw=None,
            )  # fmt: skip
            if ref_type and master and master != tid:
                yield ctx.fact("instrument_ref", from_uid=uid,
                               to_uid=stable_id(self.source_id, "filing", master),
                               ref_type=ref_type, scope_parcel_uid=None,
                               method="index_xref")  # fmt: skip
            seen: set[tuple[str, str]] = set()
            for seq, (role, r) in enumerate(sorted(parties.get(fileid, []),
                                                   key=lambda x: (x[0], canonical_json(x[1]))),
                                            start=1):  # fmt: skip
                name, parts = person_name(r)
                if name is None or (role, clean(name)) in seen:
                    continue
                seen.add((role, clean(name)))
                addr = address(r)
                if addr is not None:
                    yield NormalizedRow("address", addr)
                nc = classify(name)
                party_id = stable_id(self.source_id, tid, role, clean(name))
                yield ctx.fact("party", party_id=party_id, raw_name=name,
                               party_kind="person" if parts["last_name"] else nc.party_kind,
                               org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                               address_id=addr["address_id"] if addr else None,
                               **parts)  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=party_id,
                               role=role, seq=seq)  # fmt: skip

    def health(self) -> HealthReport:
        q = SocrataQuery(PORTAL, FILINGS, "fileid IS NOT NULL", (":id",), 1)
        resp = get_page(self.client, q, 0)
        ok = resp.status == 200 and len(parse_rows(resp.content)) == 1
        return HealthReport(self.source_id, ok, datetime.now(UTC), f"status={resp.status}")
