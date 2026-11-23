"""EPA civil judicial enforcement cases with a penalty or cost recovery, from ECHO's ICIS-FE&C
case download (config/courts_federal/us.epa.echo.judicial_cases.yaml).

case_downloads.zip is a set of CSVs keyed by ACTIVITY_ID (one per case): the case itself, its
conclusions (settlements: consent decrees and court orders, with the entered date and the
federal penalty and cost recovery), its defendants and its facilities. Kept: judicial cases
with at least one judicial conclusion that has an entered date and a federal penalty or cost
recovery above zero.

Each kept case becomes one court_case, the United States as creditor, each defendant named
in a settlement as debtor (others as defendant), and one judgment per kept conclusion
(principal = federal penalty, costs = cost recovery). ICIS has no defendant address; a
facility's street address goes on the debtor whose name is the facility's name, or on the
only debtor of a single-facility case (see the config's TODOs on what that address is).

fetch() downloads the zip and stores only the kept cases, with the columns used here, as one
JSON document (the whole download is one partition: about 7,000 cases).
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from functools import cache
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.fjc_idb import strip_et_al
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

CONFIG = "courts_federal/us.epa.echo.judicial_cases.yaml"
# Columns kept from each CSV (free-text summaries are left out).
COLUMNS: Mapping[str, tuple[str, ...]] = {
    "CASE_ENFORCEMENTS": ("ACTIVITY_ID", "CASE_NUMBER", "CASE_NAME", "ACTIVITY_TYPE_CODE",
                          "ACTIVITY_STATUS_DESC", "ACTIVITY_STATUS_DATE", "REGION_CODE",
                          "FISCAL_YEAR", "LEAD", "DOJ_DOCKET_NMBR", "ENF_OUTCOME_DESC",
                          "TOTAL_PENALTY_ASSESSED_AMT", "TOTAL_COST_RECOVERY_AMT"),
    "CASE_ENFORCEMENT_CONCLUSIONS": ("ACTIVITY_ID", "ENF_CONCLUSION_ID", "ENF_CONCLUSION_NMBR",
                                     "ENF_CONCLUSION_ACTION_CODE", "ENF_CONCLUSION_NAME",
                                     "SETTLEMENT_LODGED_DATE", "SETTLEMENT_ENTERED_DATE",
                                     "PRIMARY_LAW", "ACTIVITY_TYPE_CODE",
                                     "FED_PENALTY_ASSESSED_AMT", "STATE_LOCAL_PENALTY_AMT",
                                     "COST_RECOVERY_AWARDED_AMT"),
    "CASE_DEFENDANTS": ("ACTIVITY_ID", "DEFENDANT_NAME", "NAMED_IN_COMPLAINT_FLAG",
                        "NAMED_IN_SETTLEMENT_FLAG"),
    "CASE_FACILITIES": ("ACTIVITY_ID", "REGISTRY_ID", "FACILITY_NAME", "LOCATION_ADDRESS",
                        "CITY", "STATE_CODE", "ZIP"),
    "CASE_REGIONAL_DOCKETS": ("ACTIVITY_ID", "REGIONAL_DOCKET_NMBR"),
}  # fmt: skip
CHILDREN = {"CASE_ENFORCEMENT_CONCLUSIONS": "conclusions", "CASE_DEFENDANTS": "defendants",
            "CASE_FACILITIES": "facilities", "CASE_REGIONAL_DOCKETS": "dockets"}  # fmt: skip


@dataclass(frozen=True)
class EchoConfig:
    source_id: str
    download_page: str
    file_url: str
    judicial: frozenset[str]
    court_id: str
    creditor_name: str
    judgment_types: Mapping[str, str]
    terms: Mapping[str, Any]


@cache
def load_config() -> EchoConfig:
    import yaml

    d = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    return EchoConfig(
        source_id=d["source_id"],
        download_page=d["download_page"],
        file_url=d["file_url"],
        judicial=frozenset(d["judicial_activity_types"]),
        court_id=d["court_id"],
        creditor_name=d["creditor_name"],
        judgment_types=dict(d["judgment_types"]),
        terms=dict(d["terms"]),
    )


def text(value: str | None) -> str:
    return " ".join((value or "").split())


def us_date(value: str | None) -> date | None:
    """'03/24/1994' -> date; anything else -> None."""
    parts = text(value).split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts) or len(parts[2]) != 4:
        return None
    try:
        return date(int(parts[2]), int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def amount(value: str | None) -> Decimal | None:
    """'46905.01' -> Decimal; blank, unparseable or negative -> None."""
    try:
        d = Decimal(text(value))
    except InvalidOperation:
        return None
    return d.quantize(Decimal("0.01")) if d.is_finite() and d >= 0 else None


def kept_conclusion(c: Mapping[str, str], cfg: EchoConfig) -> date | None:
    """Entered date of a judicial conclusion with a federal penalty or cost recovery owed."""
    if text(c.get("ACTIVITY_TYPE_CODE")) not in cfg.judicial:
        return None
    entered = us_date(c.get("SETTLEMENT_ENTERED_DATE"))
    if entered is None:
        return None
    money = [amount(c.get(k)) for k in ("FED_PENALTY_ASSESSED_AMT", "COST_RECOVERY_AWARDED_AMT")]
    return entered if any(m is not None and m > 0 for m in money) else None


def read_member(zf: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    cols = COLUMNS[name]
    with zf.open(f"{name}.csv") as raw:
        fh = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
        for r in csv.DictReader(fh):
            yield {c: text(r.get(c)) for c in cols}


def kept_cases(content: bytes, cfg: EchoConfig) -> list[dict[str, Any]]:
    """The kept cases of a case_downloads.zip, each with its child rows, by CASE_NUMBER."""
    zf = zipfile.ZipFile(io.BytesIO(content))
    keep = {c["ACTIVITY_ID"] for c in read_member(zf, "CASE_ENFORCEMENT_CONCLUSIONS")
            if kept_conclusion(c, cfg) is not None}  # fmt: skip
    heads = {e["ACTIVITY_ID"]: e for e in read_member(zf, "CASE_ENFORCEMENTS")
             if e["ACTIVITY_ID"] in keep and e["ACTIVITY_TYPE_CODE"] in cfg.judicial}  # fmt: skip
    children: dict[str, dict[str, list[dict[str, str]]]] = {
        a: {k: [] for k in CHILDREN.values()} for a in heads
    }
    for member, key in CHILDREN.items():
        for r in read_member(zf, member):
            found = children.get(r.pop("ACTIVITY_ID"))
            if found is not None:
                found[key].append(r)
    cases: list[dict[str, Any]] = []
    for a, head in heads.items():
        kids = {k: sorted(v, key=canonical_json) for k, v in children[a].items()}
        cases.append({**head, **kids})
    return sorted(cases, key=lambda c: (c["CASE_NUMBER"], c["ACTIVITY_ID"]))


def state_jurisdiction(state: str) -> str | None:
    from equity.geo import state_fips

    try:
        return state_fips(state) if state else None
    except KeyError:
        return None


class EPAJudicialCases(Adapter):
    source_id: ClassVar[str] = "us.epa.echo.judicial_cases"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = (
        "CASE_NAME", "ENF_CONCLUSION_NAME", "DEFENDANT_NAME", "FACILITY_NAME", "LOCATION_ADDRESS",
    )  # fmt: skip

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.config = load_config()
        self.client = client or PoliteClient(min_interval_s=10.0, timeout_s=600.0)

    def source_row(self) -> Mapping[str, Any]:
        t = self.config.terms
        return {
            "source_id": self.source_id,
            "kind": "court",
            "jurisdiction": "us",
            "access_method": self.access_method,
            "base_url": self.config.file_url,
            "terms_url": t["url"],
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t["robots_checked_on"],
            "cost_model": t["cost_model"],
        }

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: limit (fixtures: the first N kept cases)."""
        resp = self.client.get(self.config.file_url)
        if resp.status != 200:
            raise ValueError(f"{self.config.file_url}: HTTP {resp.status}")
        cases = kept_cases(resp.content, self.config)
        if "limit" in request.params:
            cases = cases[: int(request.params["limit"])]
        body = canonical_json({"file": self.config.file_url, "bytes": len(resp.content),
                               "cases": cases})  # fmt: skip
        return Fetched(self.source_id, self.config.file_url, resp.retrieved_at, 200, body,
                       "application/json")  # fmt: skip

    def health(self) -> HealthReport:
        """Live: the downloads page still links the case download."""
        now = datetime.now(UTC)
        try:
            resp = self.client.get(self.config.download_page)
        except OSError as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        name = self.config.file_url.rsplit("/", 1)[1]
        ok = resp.status == 200 and name.encode() in resp.content
        return HealthReport(self.source_id, ok, now, f"HTTP {resp.status}", (name,) if ok else ())

    # -- normalizing ----------------------------------------------------------------------
    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = self.config
        today = fetched.retrieved_at.astimezone(UTC).date()
        for case in json.loads(fetched.content)["cases"]:
            number = text(case.get("CASE_NUMBER"))
            judgments = [(c, d) for c in case.get("conclusions", [])
                         if (d := kept_conclusion(c, cfg)) is not None and d <= today]  # fmt: skip
            if not number or not judgments or case.get("ACTIVITY_TYPE_CODE") not in cfg.judicial:
                continue
            uid = f"us.epa.icis:{number}"
            facilities = case.get("facilities", [])
            states = {f["STATE_CODE"] for f in facilities if f.get("STATE_CODE")}
            jurisdiction = (state_jurisdiction(states.pop()) if len(states) == 1 else None) or "us"
            ctx = RecordContext(fetched, jurisdiction, number, "icis_judicial_case", case)
            yield ctx.source_record()
            dockets = sorted({d["REGIONAL_DOCKET_NMBR"] for d in case.get("dockets", [])
                              if d.get("REGIONAL_DOCKET_NMBR")})  # fmt: skip
            laws = sorted({c["PRIMARY_LAW"] for c, _ in judgments if c.get("PRIMARY_LAW")})
            yield ctx.fact(
                "court_case", case_uid=uid, court_id=cfg.court_id,
                case_number_raw="; ".join(dockets) or number, case_number_norm=number,
                case_type="civil", nature_of_suit="/".join(laws) or None, filed_on=None,
                closed_on=None, status=case.get("ACTIVITY_STATUS_DESC") or None,
            )  # fmt: skip
            yield from self._party(ctx, uid, "creditor", cfg.creditor_name, None)
            yield from self._defendants(ctx, uid, case, facilities)
            for c, entered in sorted(judgments, key=lambda cd: canonical_json(cd[0])):
                yield ctx.fact(
                    "judgment", judgment_uid=f"{uid}:{c['ENF_CONCLUSION_ID']}", case_uid=uid,
                    entered_on=entered, principal=amount(c.get("FED_PENALTY_ASSESSED_AMT")),
                    interest=None, costs=amount(c.get("COST_RECOVERY_AWARDED_AMT")), rate=None,
                    judgment_type=cfg.judgment_types.get(c.get("ENF_CONCLUSION_ACTION_CODE", ""),
                                                         "other"),
                    lien_instrument_uid=None,
                )  # fmt: skip

    def _defendants(
        self, ctx: RecordContext, uid: str, case: Mapping[str, Any], facilities: list[Any]
    ) -> Iterator[NormalizedRow]:
        roles: dict[str, tuple[str, str]] = {}  # clean name -> (role, name)
        for d in case.get("defendants", []):
            name = text(d.get("DEFENDANT_NAME"))
            if not clean(name):
                continue
            role = "debtor" if d.get("NAMED_IN_SETTLEMENT_FLAG") == "Y" else "defendant"
            prev = roles.get(clean(name))
            if prev is None or (role == "debtor" and prev[0] != "debtor"):
                roles[clean(name)] = (role, name)
        if roles and all(role != "debtor" for role, _ in roles.values()):
            # Nobody is flagged as named in a settlement: the judgment binds the defendants.
            roles = {k: ("debtor", name) for k, (_, name) in roles.items()}
        if not roles:  # no defendant rows: the case is named for the defendant
            name = strip_et_al(text(case.get("CASE_NAME")))
            if clean(name):
                roles[clean(name)] = ("debtor", name)
        by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for f in facilities:
            addr = normalized_address(f.get("LOCATION_ADDRESS") or None, f.get("CITY") or None,
                                      f.get("STATE_CODE") or None,
                                      zip5(f.get("ZIP")))  # fmt: skip
            if addr is not None:
                by_name[clean(text(f.get("FACILITY_NAME")))].append(addr)
        debtors = [k for k, (role, _) in roles.items() if role == "debtor"]
        only = [a for v in by_name.values() for a in v]
        for key in sorted(roles):
            role, name = roles[key]
            addr = None
            if role == "debtor":
                named = {a["address_id"]: a for a in by_name.get(key, [])}
                if len(named) == 1:
                    addr = next(iter(named.values()))
                elif not named and len(debtors) == 1 and len(facilities) == 1 and only:
                    addr = only[0]
            yield from self._party(ctx, uid, role, name, addr)

    def _party(
        self, ctx: RecordContext, uid: str, role: str, name: str, address: dict[str, Any] | None
    ) -> Iterator[NormalizedRow]:
        if address is not None:
            yield NormalizedRow("address", address)
        nc = classify(name)
        party_id = stable_id(self.source_id, uid, role, clean(name))
        yield ctx.fact(
            "party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
            org_form=nc.org_form, org_name_norm=nc.org_name_norm,
            address_id=None if address is None else address["address_id"],
        )  # fmt: skip
        yield ctx.fact("case_party", case_uid=uid, party_id=party_id, role=role)


def zip5(value: str | None) -> str | None:
    z = text(value)[:5]
    return z if len(z) == 5 and z.isdigit() else None
