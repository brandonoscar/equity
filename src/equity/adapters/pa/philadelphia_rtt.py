"""Philadelphia Real Estate Transfers (Department of Records `rtt_summary`) on the City's Carto
SQL API: deeds, sheriff deeds, mortgages, assignments, satisfactions, lis pendens and UCC
fixture filings recorded since December 1999, plus older records.

One row per document per property. A fetch covers the documents whose FIRST row (lowest
cartodb_id) falls in a cartodb_id window, with all of their rows, so every document is loaded
whole and exactly once even when its rows are scattered through the table.

Parcels: opa_account_num is the OPA account, the same key as pa.philadelphia.parcels
(parcel_uid 42101-<OPA account>). This source emits no parcel rows of its own.

Source: https://phl.carto.com/api/v2/sql (robots.txt only names search-engine bots; checked
2026-11-16). License: City of Philadelphia open data terms ("as is", City reserves rights);
the full terms page has not been read. Judgments and municipal liens are filed with the
Prothonotary, not the Recorder, so they are not in this table.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from functools import cache
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient, Response
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import norm_parcel_id
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

SQL_URL = "https://phl.carto.com/api/v2/sql"
CONFIG = "recorders/pa.philadelphia.rtt.yaml"
COUNTY = "42101"
# legal_remarks is left out on purpose: it can carry names and is not needed for the graph.
COLUMNS: tuple[str, ...] = (
    "cartodb_id", "document_id", "record_id", "document_type", "recording_date",
    "document_date", "grantors", "grantees", "total_consideration", "opa_account_num",
    "street_address", "unit_num", "zip_code", "matched_regmap", "reg_map_id", "property_count",
    "discrepancy",
)  # fmt: skip
PII_FIELDS: tuple[str, ...] = ("grantors", "grantees")
WINDOW = 10_000
# Carto's anonymous tier cancels slow statements with HTTP 400 "query_wait_timeout"; the same
# statement usually succeeds on a retry.
TIMEOUT_MARK = b"query_wait_timeout"


@dataclass(frozen=True)
class RttType:
    doc_type: str
    grantors: str
    grantees: str


@dataclass(frozen=True)
class RttConfig:
    types: Mapping[str, RttType]
    consideration_doc_types: frozenset[str]


@cache
def load_config() -> RttConfig:
    import yaml

    data = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    types = {
        str(k).strip(): RttType(str(v["doc_type"]), str(v["grantors"]), str(v["grantees"]))
        for k, v in data["types"].items()
    }
    return RttConfig(types, frozenset(str(t) for t in data["consideration_doc_types"]))


def window_sql(lo: int, hi: int, limit: int | None = None) -> str:
    """Every row of the documents whose lowest cartodb_id is in [lo, hi)."""
    cols = ", ".join(f"r.{c}" for c in COLUMNS)
    # Only integers and fixed column names are interpolated.
    sql = (
        "WITH w AS (SELECT DISTINCT document_id FROM rtt_summary "  # noqa: S608
        f"WHERE cartodb_id >= {int(lo)} AND cartodb_id < {int(hi)}), "
        "own AS (SELECT w.document_id FROM w WHERE NOT EXISTS (SELECT 1 FROM rtt_summary x "
        f"WHERE x.document_id = w.document_id AND x.cartodb_id < {int(lo)})) "
        f"SELECT {cols} FROM rtt_summary r JOIN own USING (document_id) "
        "ORDER BY r.document_id, r.cartodb_id"
    )
    return sql + (f" LIMIT {int(limit)}" if limit else "")


def split_names(value: Any) -> list[str]:
    """'SMITH JOHN; SMITH MARY' -> two names, whitespace collapsed, order and duplicates
    removed (row order is not meaningful)."""
    if not isinstance(value, str):
        return []
    return sorted({" ".join(p.split()) for p in value.split(";") if p.strip()})


def _date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        amt = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return None if amt < 0 else amt.quantize(Decimal("0.01"))


def _text(value: Any) -> str | None:
    if value is None:
        return None
    s = " ".join(str(value).split())
    return s or None


# The table uses the Unix epoch as a "no date" placeholder (seen as 1969-12-31 in local time).
PLACEHOLDER_DATES = frozenset({date(1969, 12, 31), date(1970, 1, 1)})


class PhiladelphiaRTT(Adapter):
    source_id: ClassVar[str] = "pa.philadelphia.rtt"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "api"
    pii_fields: ClassVar[tuple[str, ...]] = PII_FIELDS

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "recorder",
            "jurisdiction": COUNTY,
            "access_method": "api",
            "base_url": SQL_URL,
            "terms_url": "https://metadata.phila.gov/#help/help-faqs/what-are-the-terms-of-use/",
            "terms_summary": (
                "City of Philadelphia open data license: provided as is, City reserves rights; "
                "no commercial-use clause found. Full terms page not yet read."
            ),
            "terms_checked_on": date(2026, 11, 16),
            "robots_checked_on": date(2026, 11, 16),
            "cost_model": "free",
        }

    def query(self, sql: str) -> Response:
        attempt = 0
        while True:
            resp = self.client.get(SQL_URL, {"q": sql})
            busy = resp.status == 400 and TIMEOUT_MARK in resp.content
            if not busy or attempt >= self.client.retries + 2:
                return resp
            self.client.sleep(self.client.backoff_s * (2**attempt))
            attempt += 1

    def rows(self, sql: str) -> list[dict[str, Any]]:
        resp = self.query(sql)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from Carto: {resp.content[:200]!r}")
        data = json.loads(resp.content)
        rows = data.get("rows")
        if not isinstance(rows, list):
            raise RuntimeError(f"Carto response has no rows: {str(data)[:200]}")
        return rows

    def max_id(self) -> int:
        """Highest cartodb_id, by binary search on the indexed key (ORDER BY ... DESC and
        count(*) both time out on the anonymous tier)."""
        lo, hi = 1, 1 << 24
        while lo < hi:
            mid = (lo + hi + 1) // 2
            probe = f"SELECT cartodb_id FROM rtt_summary WHERE cartodb_id >= {mid} "  # noqa: S608
            hit = self.rows(probe + "ORDER BY cartodb_id LIMIT 1")
            lo, hi = (mid, hi) if hit else (lo, mid - 1)
        return lo

    def partitions(self) -> Iterator[dict[str, str]]:
        top = self.max_id()
        for lo in range(1, top + 1, WINDOW):
            yield {"lo": str(lo), "hi": str(lo + WINDOW)}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: lo, hi (cartodb_id window, hi exclusive)."""
        lo, hi = int(request.params["lo"]), int(request.params["hi"])
        sql = window_sql(lo, hi)
        body = {"sql": sql, "rows": self.rows(sql)}
        return Fetched(
            source_id=self.source_id,
            request=f"{SQL_URL}?q={sql}",
            retrieved_at=datetime.now(UTC),
            http_status=200,
            content=canonical_json(body),
            content_type="application/json",
        )

    @staticmethod
    def scrub_fixture(content: bytes) -> bytes:
        """Pseudonymize each ';'-separated name so splitting stays testable."""
        from equity.adapters.record import pseudonym  # the recorder imports the registry

        data = json.loads(content)
        for row in data["rows"]:
            for field in PII_FIELDS:
                names = row.get(field)
                if isinstance(names, str) and names.strip():
                    row[field] = ";".join(
                        pseudonym(field, n.strip()) for n in names.split(";") if n.strip()
                    )
        return canonical_json(data)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = load_config()
        data = json.loads(fetched.content)
        docs: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in data["rows"]:
            if row.get("document_id") is not None:
                docs[str(row["document_id"])].append(row)
        today = fetched.retrieved_at.astimezone(UTC).date()
        for doc_id in sorted(docs, key=lambda d: (len(d), d)):
            rows = sorted(docs[doc_id], key=lambda r: int(r.get("cartodb_id") or 0))
            yield from self._document(cfg, fetched, today, doc_id, rows)

    def _document(
        self,
        cfg: RttConfig,
        fetched: Fetched,
        today: date,
        doc_id: str,
        rows: list[dict[str, Any]],
    ) -> Iterator[NormalizedRow]:
        first = rows[0]
        ctx = RecordContext(fetched, COUNTY, doc_id, "rtt_document", rows)
        yield ctx.source_record()

        def issue(code: str, table: str, /, **detail: Any) -> NormalizedRow:
            return ctx.fact("data_issue", issue_code=code, target_table=table,
                            detail={"document_id": doc_id, **detail})  # fmt: skip

        raw_type = _text(first.get("document_type"))
        recorded_on = _date(first.get("recording_date"))
        if raw_type is None or recorded_on is None or recorded_on in PLACEHOLDER_DATES:
            yield issue(
                "missing_doc_type_or_recorded_date", "instrument",
                document_type=raw_type, recording_date=first.get("recording_date"),
            )  # fmt: skip
            return
        if recorded_on > today:
            yield issue("recorded_after_retrieval", "instrument", recorded=str(recorded_on))
            return
        spec = cfg.types.get(raw_type)
        if spec is None:
            yield issue("unknown_doc_type", "instrument", document_type=raw_type)
            spec = RttType("OTHER", "other", "other")
        executed_on = _date(first.get("document_date"))
        if executed_on is not None and (executed_on > today or executed_on in PLACEHOLDER_DATES):
            if executed_on > today:
                yield issue("executed_after_retrieval", "instrument", executed=str(executed_on))
            executed_on = None
        price = (
            _amount(first.get("total_consideration"))
            if spec.doc_type in cfg.consideration_doc_types
            else None
        )
        uid = f"{self.source_id}:{doc_id}"
        yield ctx.fact(
            "instrument",
            instrument_uid=uid,
            instrument_number=doc_id,
            book_type=None,
            book=None,
            page=None,
            doc_type_raw=raw_type,
            doc_type=spec.doc_type,
            recorded_on=recorded_on,
            recorded_seq=None,
            executed_on=executed_on,
            consideration=price,
            principal_amount=None,
            max_secured_amount=None,
            maturity_date=None,
            amount_source="index" if price is not None else None,
            legal_desc_raw=None,
        )
        lots: dict[str, list[dict[str, Any]]] = defaultdict(list)
        missing: list[dict[str, Any]] = []
        for r in rows:
            opa = _text(r.get("opa_account_num"))
            if opa is None:
                # Kept for a later address-match step: the property's street address.
                missing.append({k: r.get(k) for k in ("record_id", "street_address", "unit_num",
                                                      "zip_code")})  # fmt: skip
                continue
            lots[norm_parcel_id(opa)].append(
                {
                    k: r.get(k)
                    for k in (
                        "record_id",
                        "street_address",
                        "unit_num",
                        "matched_regmap",
                        "reg_map_id",
                    )
                }
            )
        for opa in sorted(lots):
            yield ctx.fact(
                "instrument_parcel", instrument_uid=uid, parcel_uid=f"{COUNTY}-{opa}",
                method="index_parcel_id", evidence={"rows": lots[opa]},
            )  # fmt: skip
        if missing:
            yield issue("no_parcel_id", "instrument_parcel", rows=missing)
        seqs: dict[str, int] = defaultdict(int)  # per role: both columns can map to "other"
        for column, role in (("grantors", spec.grantors), ("grantees", spec.grantees)):
            for name in split_names(first.get(column)):
                seqs[role] += 1
                nc = classify(name)
                party_id = stable_id(self.source_id, doc_id, column, clean(name))
                yield ctx.fact(
                    "party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
                    org_form=nc.org_form, org_name_norm=nc.org_name_norm, address_id=None,
                )  # fmt: skip
                yield ctx.fact("instrument_party", instrument_uid=uid, party_id=party_id,
                               role=role, seq=seqs[role])  # fmt: skip

    def health(self) -> HealthReport:
        try:
            rows = self.rows("SELECT * FROM rtt_summary WHERE cartodb_id >= 1 "
                             "ORDER BY cartodb_id LIMIT 1")  # fmt: skip
        except (RuntimeError, ValueError) as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        shape = tuple(sorted(rows[0])) if rows else ()
        ok = bool(rows) and set(COLUMNS) <= set(shape)
        detail = "ok" if ok else f"missing={sorted(set(COLUMNS) - set(shape))}"
        return HealthReport(self.source_id, ok, datetime.now(UTC), detail, shape)
