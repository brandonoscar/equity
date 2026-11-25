"""Professional, occupational and business licenses published on Socrata, one YAML per dataset
in config/licenses/<st>.<agency>.<name>.yaml. One adapter class per file, generated at import.

A license names who holds it (a person or a company, often with an address) and what it is
(type, number, status, issue date). The existing registry tables carry it, so no schema is
added:

  business       one row per license record: sos_id = `id_prefix` + the record key, name =
                 the first non-empty `license.name` column (trade name, business name) else
                 the first holder's name, status, formed_on = first issue date, principal and
                 mailing address
  party          each holder (licensee, owner, qualifier, principal...) as printed
  business_role  holder -> license, role from config (mostly 'other'), title = the holder
                 title plus the license type ("LICENSEE: Electrician")
  address        normalized addresses

Holders come from columns of the license row (`holders`) and from related datasets keyed by
the same column (`related`, e.g. contractor principals or business owners). Rows sharing a
record key (one row per associated person, or one row per renewal) make one license record:
the license fields come from the representative row (the latest by `latest_by`, else the
first in canonical order) and holders from every row.

Partitions are ranges of the partition `key`, planned by keyset paging over its sorted
distinct values (no deep offsets), as in business_registry; a numeric key is compared as
text in every dataset so ranges agree.

Valid time (a convention, as for registries): a license runs from its first issue date (the
retrieval date when none is published); a role runs from the same day unless the related
dataset publishes its own start and end. Expiration dates stay in the raw record: the
business table has no column for them.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import Any, ClassVar

import yaml

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataQuery, fetch_all, quote
from equity.adapters.state_parcels import (
    normalized_address,
    parse_city_state_zip,
    parse_full_address,
)
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

LICENSE_DIR = CONFIG_DIR / "licenses"
PLAN_KEYS = 50_000
ROLES = frozenset({"member", "manager", "officer", "director", "organizer", "incorporator",
                   "registered_agent", "other"})  # fmt: skip
PART_NAMES = ("first", "middle", "last", "suffix")
_TRAILING_ST_ZIP = re.compile(
    r"^(?P<rest>.*?)[,\s]+(?P<st>[A-Za-z]{2})\s+(?P<zip>\d{5})(?:-?\d{4})?$"
)
US_STATES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA",
    "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL",
    "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA",
    "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR",
    "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA",
    "WASHINGTON": "WA", "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
    "PUERTO RICO": "PR",
}  # fmt: skip
_MDY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})")
_YMD8 = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


class LicenseConfigError(ValueError):
    pass


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    s = " ".join(str(value).split())
    return s or None


def parse_date(value: Any) -> date | None:
    """ISO (Socrata calendar_date), MM/DD/YYYY or YYYYMMDD; anything else is None."""
    s = _text(value)
    if s is None:
        return None
    try:
        if len(s) >= 10 and s[4] == "-":
            return date.fromisoformat(s[:10])
        if m := _MDY.match(s):
            return date(int(m[3]), int(m[1]), int(m[2]))
        if m := _YMD8.match(s.split(".")[0]):
            return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None
    return None


def _cols(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    return (value,) if isinstance(value, str) else tuple(value)


@dataclass(frozen=True)
class AddressSpec:
    """street columns joined; city/state/zip columns, or `city_state_zip` ('AUSTIN TX 78701'),
    or `line`, a one-line address ('1 MAIN ST, AUSTIN, TX 78701' or '1 MAIN ST AUSTIN TX
    78701' when the row's `city` column says where the street ends)."""

    street: tuple[str, ...] = ()
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    city_state_zip: str | None = None
    line: str | None = None

    @staticmethod
    def parse(data: Mapping[str, Any] | None) -> AddressSpec | None:
        if not data:
            return None
        unknown = set(data) - {"street", "city", "state", "zip", "city_state_zip", "line"}
        if unknown:
            raise LicenseConfigError(f"unknown address keys {sorted(unknown)}")
        return AddressSpec(
            _cols(data.get("street")), data.get("city"), data.get("state"), data.get("zip"),
            data.get("city_state_zip"), data.get("line"),
        )  # fmt: skip


def _zip5(value: Any) -> str | None:
    z = _text(value)
    return z[:5] if z and len(z) >= 5 and z[:5].isdigit() and z[:5] != "00000" else None


def address_of(row: Mapping[str, Any], spec: AddressSpec | None) -> dict[str, Any] | None:
    if spec is None:
        return None
    street = " ".join(p for p in (_text(row.get(c)) for c in spec.street) if p) or None
    city = _text(row.get(spec.city)) if spec.city else None
    state = _text(row.get(spec.state)) if spec.state else None
    zip5 = _zip5(row.get(spec.zip)) if spec.zip else None
    if spec.city_state_zip and (csz := _text(row.get(spec.city_state_zip))):
        c, s, z = parse_city_state_zip(csz)
        city, state, zip5 = city or c, state or s, zip5 or z
    if spec.line and (line := _text(row.get(spec.line))):
        street, city, state, zip5 = _one_line(line, street, city, state, zip5)
    if state is not None and len(state) != 2:
        state = US_STATES.get(state.upper())  # 'New York' -> NY; 'ST. JAMES' -> None
    return normalized_address(street, city, state.upper() if state else None, zip5)


def _one_line(
    line: str, street: str | None, city: str | None, state: str | None, zip5: str | None
) -> tuple[str | None, str | None, str | None, str | None]:
    s, c, st, z = parse_full_address(line)
    if c is not None:
        return street or s, city or c, state or st, zip5 or z
    m = _TRAILING_ST_ZIP.match(line)
    if m is None:
        return street or line, city, state, zip5
    rest = m["rest"].rstrip(", ")
    if city and rest.upper().endswith(" " + city.upper()):
        rest = rest[: -len(city)].rstrip(", ")
    return street or rest or None, city, state or m["st"].upper(), zip5 or m["zip"]


@dataclass(frozen=True)
class HolderSpec:
    """A person or company on a license: the first non-empty `name` column, else `parts`
    (first/middle/last/suffix columns) joined. `last_first` reads a one-column name printed
    'LAST, FIRST MIDDLE' into parts. `split` cuts a one-column list of names ('ANN LEE, BO
    RAY') into one holder each. `title_field` names a column holding the title."""

    role: str = "other"
    title: str | None = None
    name: tuple[str, ...] = ()
    parts: Mapping[str, str] | None = None
    last_first: bool = False
    address: AddressSpec | None = None
    title_field: str | None = None
    with_type: bool = True  # append the license type to the title
    split: str | None = None

    @staticmethod
    def parse(data: Mapping[str, Any]) -> HolderSpec:
        role = str(data.get("role", "other"))
        if role not in ROLES:
            raise LicenseConfigError(f"unknown business role {role!r}")
        parts = data.get("parts")
        if parts is not None and (set(parts) - set(PART_NAMES) or "last" not in parts):
            raise LicenseConfigError(f"parts needs 'last' and only {PART_NAMES}: {parts}")
        if not (data.get("name") or parts):
            raise LicenseConfigError("a holder needs name or parts")
        if data.get("split") and (parts or data.get("last_first")):
            raise LicenseConfigError("split works on name columns, without last_first")
        return HolderSpec(
            role=role, title=data.get("title"), name=_cols(data.get("name")),
            parts=dict(parts) if parts else None, last_first=bool(data.get("last_first")),
            address=AddressSpec.parse(data.get("address")), title_field=data.get("title_field"),
            with_type=bool(data.get("with_type", True)), split=data.get("split"),
        )  # fmt: skip


def names_someone(name: str) -> bool:
    """False for placeholders that name nobody: '0', '`', '-', 'N/A'."""
    c = clean(name)
    return any(ch.isalpha() for ch in c) and c not in {"NA", "N A", "NONE", "NULL", "UNKNOWN"}


def holders_of(row: Mapping[str, Any], spec: HolderSpec) -> list[tuple[str, dict[str, str | None]]]:
    """Every holder the row names under `spec` (one, or one per `split` piece)."""
    got = holder_of(row, spec)
    if got is None or spec.split is None:
        return [] if got is None else [got]
    parts = [p for p in (_text(x) for x in got[0].split(spec.split)) if p and names_someone(p)]
    return [(p, got[1]) for p in parts]


def holder_of(row: Mapping[str, Any], spec: HolderSpec) -> tuple[str, dict[str, str | None]] | None:
    """(raw name, name parts) or None when the row names nobody."""
    none: dict[str, str | None] = dict.fromkeys(("first_name", "middle", "last_name", "suffix"))
    for col in spec.name:
        if (who := _text(row.get(col))) and names_someone(who):
            if spec.last_first and "," in who and classify(who).party_kind != "org":
                last, _, rest = who.partition(",")
                given = rest.split()
                if last.strip() and given:
                    return who, {"first_name": given[0],
                                 "middle": " ".join(given[1:]) or None,
                                 "last_name": last.strip(), "suffix": None}  # fmt: skip
            return who, none
    if spec.parts:
        vals = {k: _text(row.get(c)) for k, c in spec.parts.items()}
        who = " ".join(v for k in PART_NAMES if (v := vals.get(k))) or None
        if who is None or not names_someone(who):
            return None
        if not vals.get("last"):
            return who, none
        return who, {"first_name": vals.get("first"), "middle": vals.get("middle"),
                     "last_name": vals.get("last"), "suffix": vals.get("suffix")}  # fmt: skip
    return None


@dataclass(frozen=True)
class Related:
    dataset: str
    key: str
    holder: HolderSpec
    role_field: str | None
    role_map: Mapping[str, str]  # raw role (upper case) -> role
    valid_from_field: str | None
    valid_to_field: str | None


@dataclass(frozen=True)
class LicenseConfig:
    source_id: str
    state: str
    jurisdiction: str
    portal: str
    dataset: str
    key: str
    key_is_number: bool
    record_key: tuple[str, ...]
    id_prefix: str
    terms_url: str
    terms_summary: str
    checked_on: date
    name: tuple[str, ...]
    number: str | None
    type: str | None
    type_value: str | None
    status: str | None
    status_value: str | None
    issued_on: str | None
    latest_by: str | None
    address: AddressSpec | None
    mailing: AddressSpec | None
    holders: tuple[HolderSpec, ...]
    related: tuple[Related, ...]
    pii_fields: tuple[str, ...]

    def key_expr(self, column: str) -> str:
        return f"{column}::text" if self.key_is_number else column

    def get(self, name: str, default: Any = None) -> Any:
        """Config lookup in the lien-config style (record.py asks for skip_names)."""
        return getattr(self, name, default)


_TOP = {"source_id", "state", "jurisdiction", "portal", "dataset", "key", "key_is_number",
        "record_key", "id_prefix", "terms_url", "terms_summary", "checked_on", "license",
        "holders", "related", "pii_fields"}  # fmt: skip
_LICENSE = {"name", "number", "type", "type_value", "status", "status_value", "issued_on",
            "expires_on", "latest_by", "address", "mailing"}  # fmt: skip


def load_license(path: Path) -> LicenseConfig:
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    if unknown := set(d) - _TOP:
        raise LicenseConfigError(f"{path.name}: unknown keys {sorted(unknown)}")
    lic = d.get("license") or {}
    if unknown := set(lic) - _LICENSE:
        raise LicenseConfigError(f"{path.name}: unknown license keys {sorted(unknown)}")
    if path.stem != d["source_id"]:
        raise LicenseConfigError(f"{path.name}: file must be named <source_id>.yaml")
    if not str(d.get("id_prefix") or "").strip():
        raise LicenseConfigError(f"{path.name}: id_prefix is required (keeps ids apart)")
    related = []
    for r in d.get("related") or ():
        role_map = {str(k).upper(): v for k, v in (r.get("role_map") or {}).items()}
        for v in role_map.values():
            if v not in ROLES:
                raise LicenseConfigError(f"{path.name}: unknown business role {v!r}")
        related.append(Related(
            dataset=r["dataset"], key=r["key"], holder=HolderSpec.parse(r["holder"]),
            role_field=r.get("role_field"), role_map=role_map,
            valid_from_field=r.get("valid_from"), valid_to_field=r.get("valid_to"),
        ))  # fmt: skip
    holders = tuple(HolderSpec.parse(h) for h in d.get("holders") or ())
    if not holders and not related:
        raise LicenseConfigError(f"{path.name}: a license source needs holders or related")
    return LicenseConfig(
        source_id=d["source_id"], state=d["state"], jurisdiction=str(d["jurisdiction"]),
        portal=d["portal"], dataset=d["dataset"], key=d["key"],
        key_is_number=bool(d.get("key_is_number", False)),
        record_key=_cols(d.get("record_key")) or (d["key"],), id_prefix=str(d["id_prefix"]),
        terms_url=d["terms_url"], terms_summary=d["terms_summary"],
        checked_on=d["checked_on"], name=_cols(lic.get("name")), number=lic.get("number"),
        type=lic.get("type"), type_value=lic.get("type_value"), status=lic.get("status"),
        status_value=lic.get("status_value"), issued_on=lic.get("issued_on"),
        latest_by=lic.get("latest_by"), address=AddressSpec.parse(lic.get("address")),
        mailing=AddressSpec.parse(lic.get("mailing")), holders=holders,
        related=tuple(related), pii_fields=tuple(d.get("pii_fields") or ()),
    )  # fmt: skip


Holder = tuple[str, str | None, str, dict[str, Any] | None, dict[str, str | None],
               date | None, date | None]  # fmt: skip


class LicenseAdapter(Adapter):
    access_method: ClassVar[str] = "api"
    adapter_version: ClassVar[str] = "1"
    config: ClassVar[LicenseConfig]
    pii_fields: ClassVar[tuple[str, ...]] = ()

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        c = self.config
        return {
            "source_id": c.source_id,
            "kind": "sos",  # the nearest source kind: a state or city registry of names
            "jurisdiction": c.jurisdiction,
            "access_method": "api",
            "base_url": f"{c.portal}/resource/{c.dataset}.json",
            "terms_url": c.terms_url,
            "terms_summary": c.terms_summary,
            "terms_checked_on": c.checked_on,
            "robots_checked_on": c.checked_on,
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        """Keyset paging over sorted distinct keys; each page of PLAN_KEYS keys is one range."""
        c = self.config
        expr = c.key_expr(c.key)
        firsts: list[str] = []
        last: str | None = None
        while True:
            where = f"{expr} > {quote(last)}" if last is not None else f"{c.key} IS NOT NULL"
            q = SocrataQuery(c.portal, c.dataset, where, (expr,), PLAN_KEYS,
                             select=(f"distinct {expr} as k",))  # fmt: skip
            rows, _ = fetch_all(self.client, q, max_pages=1, sample=True)
            keys = [str(r["k"]) for r in rows if r.get("k") is not None]
            if not keys:
                break
            firsts.append(keys[0])
            last = keys[-1]
            if len(keys) < PLAN_KEYS:
                break
        for i, lo in enumerate(firsts):
            yield {"lo": lo, "hi": firsts[i + 1] if i + 1 < len(firsts) else ""}

    def _range(self, column: str, lo: str, hi: str) -> str:
        expr = self.config.key_expr(column)
        where = f"{expr} >= {quote(lo)}"
        return where + (f" AND {expr} < {quote(hi)}" if hi else "")

    def _rows(self, dataset: str, where: str, order: str, limit: int | None) -> list[Any]:
        q = SocrataQuery(self.config.portal, dataset, where, (order, ":id"), limit or 50_000)
        rows, _ = fetch_all(self.client, q, max_pages=1 if limit else 10_000, sample=bool(limit))
        return rows

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: lo, hi (key range; empty hi = open end); limit (fixtures)."""
        c = self.config
        p = request.params
        limit = int(p["limit"]) if "limit" in p else None
        where = self._range(c.key, p["lo"], p.get("hi", ""))
        rows = self._rows(c.dataset, where, c.key_expr(c.key), limit)
        body: dict[str, Any] = {"portal": c.portal, "where": where, "rows": rows}
        keys = sorted({str(r[c.key]) for r in rows if r.get(c.key) is not None})
        for rd in c.related:
            expr = c.key_expr(rd.key)
            if limit:
                related = []
                for i in range(0, len(keys), 300):
                    ids = ",".join(quote(k) for k in keys[i : i + 300])
                    related += self._rows(rd.dataset, f"{expr} in ({ids})", expr, None)
            else:
                related = self._rows(rd.dataset, self._range(rd.key, p["lo"], p.get("hi", "")),
                                     expr, None)  # fmt: skip
            body[rd.dataset] = related
        return Fetched(
            source_id=c.source_id,
            request=f"{c.portal}/resource/{c.dataset}.json?$where={where}",
            retrieved_at=datetime.now(UTC),
            http_status=200,
            content=canonical_json(body),
            content_type="application/json",
        )

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        c = self.config
        data = json.loads(fetched.content)
        records: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for r in data["rows"]:
            rk = tuple(_text(r.get(k)) or "" for k in c.record_key)
            if all(rk) and _text(r.get(c.key)):
                records[rk].append(r)
        related: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for rd in c.related:
            for r in data.get(rd.dataset, []):
                if k := _text(r.get(rd.key)):
                    related[k][rd.dataset].append(r)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        for rk in sorted(records):
            rows = sorted(records[rk], key=canonical_json)
            key = _text(rows[0].get(c.key)) or ""
            yield from self._license(fetched, observed, rk, rows, related.get(key, {}))

    def _representative(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        col = self.config.latest_by
        if col is None:
            return rows[0]
        return max(rows, key=lambda r: (parse_date(r.get(col)) or date.min,
                                        canonical_json(r)))  # fmt: skip

    def _license(
        self,
        fetched: Fetched,
        observed: date,
        rk: tuple[str, ...],
        rows: list[dict[str, Any]],
        related: Mapping[str, list[dict[str, Any]]],
    ) -> Iterator[NormalizedRow]:
        c = self.config
        record_key = "|".join(rk)
        raw = {"rows": rows, **{k: sorted(v, key=canonical_json) for k, v in related.items()}}
        ctx = RecordContext(fetched, c.jurisdiction, record_key, "license", raw)
        yield ctx.source_record()
        first = self._representative(rows)
        ltype = (_text(first.get(c.type)) if c.type else None) or c.type_value
        issued = parse_date(first.get(c.issued_on)) if c.issued_on else None
        if issued is not None and issued > observed:
            issued = None
        valid_from = issued or observed
        holders: list[Holder] = []
        for spec in c.holders:
            for r in rows:
                for got in holders_of(r, spec):
                    holders.append(self._holder(r, spec, got, ltype, None, None))
        for rd in c.related:
            for r in related.get(rd.dataset, []):
                for got in holders_of(r, rd.holder):
                    holders.append(self._related(r, rd, got, ltype))
        name = next(
            (n for col in c.name if (n := _text(first.get(col))) and names_someone(n)), None
        )
        if name is None and holders:
            name = sorted(holders, key=lambda h: (h[0], h[2]))[0][2]
        if name is None:
            yield ctx.fact("data_issue", issue_code="missing_license_name",
                           target_table="business", detail={"key": record_key})  # fmt: skip
            return
        principal = address_of(first, c.address)
        mailing = address_of(first, c.mailing)
        for addr in (principal, mailing):
            if addr is not None:
                yield NormalizedRow("address", addr)
        sos_id = c.id_prefix + record_key
        yield ctx.fact(
            "business", sos_id=sos_id, name=name, org_form=classify(name).org_form,
            status=(_text(first.get(c.status)) if c.status else None) or c.status_value,
            formed_on=issued, status_date=None,
            principal_address_id=None if principal is None else principal["address_id"],
            mailing_address_id=None if mailing is None else mailing["address_id"],
            valid_from=valid_from, valid_to=None,
        )  # fmt: skip
        seen: set[tuple[str, str, date]] = set()
        parties: set[str] = set()

        def order(h: Holder) -> tuple[Any, ...]:
            return (h[0], h[2], h[1] or "", canonical_json(h[4]), h[5] or date.min,
                    h[6] or date.min, canonical_json(h[3]))  # fmt: skip

        for role, title, who, addr, parts, start, end in sorted(holders, key=order):
            party_id = stable_id(c.source_id, record_key, role, clean(who))
            role_from = start if start is not None and start <= observed else valid_from
            role_to = end if end is not None and end >= role_from else None
            if (party_id, role, role_from) in seen:
                continue
            seen.add((party_id, role, role_from))
            if party_id not in parties:  # one party row per name, however many roles
                parties.add(party_id)
                if addr is not None:
                    yield NormalizedRow("address", addr)
                pc = classify(who)
                yield ctx.fact(
                    "party", party_id=party_id, raw_name=who, party_kind=pc.party_kind,
                    org_form=pc.org_form, org_name_norm=pc.org_name_norm,
                    address_id=None if addr is None else addr["address_id"], **parts,
                )  # fmt: skip
            yield ctx.fact("business_role", sos_id=sos_id, party_id=party_id, role=role,
                           title=title, valid_from=role_from, valid_to=role_to)  # fmt: skip

    def _related(
        self,
        r: Mapping[str, Any],
        rd: Related,
        got: tuple[str, dict[str, str | None]],
        ltype: str | None,
    ) -> Holder:
        raw_role = _text(r.get(rd.role_field)) if rd.role_field else None
        spec = rd.holder
        if raw_role is not None:
            spec = replace(spec, role=rd.role_map.get(raw_role.upper(), spec.role),
                           title=raw_role)  # fmt: skip
        start = parse_date(r.get(rd.valid_from_field)) if rd.valid_from_field else None
        end = parse_date(r.get(rd.valid_to_field)) if rd.valid_to_field else None
        return self._holder(r, spec, got, ltype, start, end)

    def _holder(
        self,
        row: Mapping[str, Any],
        spec: HolderSpec,
        got: tuple[str, dict[str, str | None]],
        ltype: str | None,
        start: date | None,
        end: date | None,
    ) -> Holder:
        title = (_text(row.get(spec.title_field)) if spec.title_field else None) or spec.title
        if spec.with_type and ltype:
            title = f"{title}: {ltype}" if title else ltype
        return (spec.role, title, got[0], address_of(row, spec.address), got[1], start, end)

    def health(self) -> HealthReport:
        c = self.config
        q = SocrataQuery(c.portal, c.dataset, f"{c.key} IS NOT NULL", (c.key_expr(c.key),), 1)
        resp = self.client.get(q.url, q.params(0))
        try:
            rows = json.loads(resp.content)
        except ValueError:
            rows = []
        ok = resp.status == 200 and isinstance(rows, list) and bool(rows) and c.key in rows[0]
        shape = tuple(sorted(rows[0])) if ok else ()
        detail = "ok" if ok else f"status={resp.status}"
        return HealthReport(c.source_id, ok, datetime.now(UTC), detail, shape)


@cache
def all_license_adapters() -> tuple[type[LicenseAdapter], ...]:
    out = []
    for path in sorted(LICENSE_DIR.glob("*.yaml")):
        cfg = load_license(path)
        cls = type(
            f"License_{cfg.source_id.replace('.', '_')}",
            (LicenseAdapter,),
            {"source_id": cfg.source_id, "config": cfg, "pii_fields": cfg.pii_fields},
        )
        out.append(cls)
    return tuple(out)
