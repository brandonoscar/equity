"""State business-entity registries published on Socrata, one YAML per state in
config/business/. One adapter class per file, generated at import.

A registry gives the entity (name, status, formation date, principal and mailing address) and
the people or companies tied to it (registered agent, officers, directors, representatives).
Three layouts are supported, all keyed by the registry's entity id (`key`):

- roles inline on the entity row (NY, CO): `roles` lists the name/address column groups;
- roles in separate datasets keyed by the entity id (CT): `role_datasets`;
- one row per associated name (OR): `grouped` names the type column and what each type means.

Partitions are ranges of the entity key, planned by keyset paging over the sorted distinct
keys (no deep offsets): each partition holds PLAN_KEYS consecutive keys.

Valid time (a convention, see config TODOs): a registry is a snapshot, so business rows run
from the formation date, and a role is dated from the same day because its true start is not
published.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import Any, ClassVar

import yaml

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataQuery, fetch_all, quote
from equity.adapters.state_parcels import normalized_address
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

BUSINESS_DIR = CONFIG_DIR / "business"
PLAN_KEYS = 50_000
ROLES = frozenset({"member", "manager", "officer", "director", "organizer", "incorporator",
                   "registered_agent", "other"})  # fmt: skip


@dataclass(frozen=True)
class AddressSpec:
    street: tuple[str, ...]
    city: str | None
    state: str | None
    zip: str | None

    @staticmethod
    def parse(data: Mapping[str, Any] | None) -> AddressSpec | None:
        if not data:
            return None
        street = data.get("street") or ()
        return AddressSpec(
            tuple([street] if isinstance(street, str) else street),
            data.get("city"), data.get("state"), data.get("zip"),
        )  # fmt: skip


@dataclass(frozen=True)
class NameSpec:
    """A role holder: `name` (one column) or `org` else `name_parts` joined with spaces."""

    role: str
    title: str | None = None
    name: str | None = None
    org: str | None = None
    name_parts: tuple[str, ...] = ()
    address: AddressSpec | None = None
    title_field: str | None = None

    @staticmethod
    def parse(data: Mapping[str, Any]) -> NameSpec:
        role = str(data.get("role", "other"))
        if role not in ROLES:
            raise ValueError(f"unknown business role {role!r}")
        return NameSpec(
            role=role, title=data.get("title"), name=data.get("name"), org=data.get("org"),
            name_parts=tuple(data.get("name_parts") or ()),
            address=AddressSpec.parse(data.get("address")), title_field=data.get("title_field"),
        )  # fmt: skip


@dataclass(frozen=True)
class RoleDataset:
    dataset: str
    key: str
    holder: NameSpec
    role_field: str | None
    role_map: Mapping[str, str]


@dataclass(frozen=True)
class Grouped:
    type_field: str
    roles: Mapping[str, NameSpec]  # type value -> role holder
    addresses: Mapping[str, str]  # type value -> "principal" | "mailing"
    address: AddressSpec


@dataclass(frozen=True)
class RegistryConfig:
    source_id: str
    state: str
    jurisdiction: str
    portal: str
    dataset: str
    key: str
    key_is_number: bool
    terms_url: str
    terms_summary: str
    checked_on: date
    name: str
    status: str | None
    status_value: str | None
    formed_on: str | None
    principal: AddressSpec | None
    mailing: AddressSpec | None
    roles: tuple[NameSpec, ...]
    role_datasets: tuple[RoleDataset, ...]
    grouped: Grouped | None
    pii_fields: tuple[str, ...]
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def key_expr(self) -> str:
        return f"{self.key}::text" if self.key_is_number else self.key


def load_registry(path: Path) -> RegistryConfig:
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    b = d["business"]
    role_sets = []
    for rd in d.get("role_datasets") or ():
        role_sets.append(RoleDataset(
            dataset=rd["dataset"], key=rd["key"], holder=NameSpec.parse(rd["holder"]),
            role_field=rd.get("role_field"), role_map=dict(rd.get("role_map") or {}),
        ))  # fmt: skip
        for r in role_sets[-1].role_map.values():
            if r not in ROLES:
                raise ValueError(f"{path.name}: unknown business role {r!r}")
    grouped = None
    if d.get("grouped"):
        g = d["grouped"]
        grouped = Grouped(
            type_field=g["type_field"],
            roles={k: NameSpec.parse(v) for k, v in (g.get("roles") or {}).items()},
            addresses=dict(g.get("addresses") or {}),
            address=AddressSpec.parse(g["address"]),  # type: ignore[arg-type]
        )
    return RegistryConfig(
        source_id=d["source_id"], state=d["state"], jurisdiction=str(d["jurisdiction"]),
        portal=d["portal"], dataset=d["dataset"], key=d["key"],
        key_is_number=bool(d.get("key_is_number", False)), terms_url=d["terms_url"],
        terms_summary=d["terms_summary"], checked_on=d["checked_on"], name=b["name"],
        status=b.get("status"), status_value=b.get("status_value"),
        formed_on=b.get("formed_on"),
        principal=AddressSpec.parse(b.get("principal")),
        mailing=AddressSpec.parse(b.get("mailing")),
        roles=tuple(NameSpec.parse(r) for r in d.get("roles") or ()),
        role_datasets=tuple(role_sets), grouped=grouped,
        pii_fields=tuple(d.get("pii_fields") or ()),
    )  # fmt: skip


def _text(value: Any) -> str | None:
    if value is None:
        return None
    s = " ".join(str(value).split())
    return s or None


def _date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def address_of(row: Mapping[str, Any], spec: AddressSpec | None) -> dict[str, Any] | None:
    if spec is None:
        return None
    street = " ".join(p for p in (_text(row.get(c)) for c in spec.street) if p) or None
    z = _text(row.get(spec.zip)) if spec.zip else None
    zip5 = z[:5] if z and len(z) >= 5 and z[:5].isdigit() else None
    return normalized_address(
        street,
        _text(row.get(spec.city)) if spec.city else None,
        _text(row.get(spec.state)) if spec.state else None,
        zip5,
    )


def holder_name(row: Mapping[str, Any], spec: NameSpec) -> str | None:
    if spec.name and _text(row.get(spec.name)):
        return _text(row.get(spec.name))
    if spec.org and _text(row.get(spec.org)):
        return _text(row.get(spec.org))
    parts = [_text(row.get(c)) for c in spec.name_parts]
    return " ".join(p for p in parts if p) or None


class BusinessRegistryAdapter(Adapter):
    access_method: ClassVar[str] = "api"
    adapter_version: ClassVar[str] = "1"
    config: ClassVar[RegistryConfig]
    pii_fields: ClassVar[tuple[str, ...]] = ()

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=1.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        c = self.config
        return {
            "source_id": c.source_id,
            "kind": "sos",
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
        firsts: list[str] = []
        last: str | None = None
        while True:
            where = f"{c.key_expr} > {quote(last)}" if last is not None else f"{c.key} IS NOT NULL"
            q = SocrataQuery(c.portal, c.dataset, where, (c.key_expr,), PLAN_KEYS,
                             select=(f"distinct {c.key_expr} as k",))  # fmt: skip
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

    def _range(self, key_expr: str, lo: str, hi: str) -> str:
        where = f"{key_expr} >= {quote(lo)}"
        return where + (f" AND {key_expr} < {quote(hi)}" if hi else "")

    def _rows(self, dataset: str, where: str, order: str, limit: int | None) -> list[Any]:
        q = SocrataQuery(self.config.portal, dataset, where, (order, ":id"), limit or 50_000)
        rows, _ = fetch_all(self.client, q, max_pages=1 if limit else 10_000, sample=bool(limit))
        return rows

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: lo, hi (key range; empty hi = open end); limit (fixtures)."""
        c = self.config
        p = request.params
        limit = int(p["limit"]) if "limit" in p else None
        where = self._range(c.key_expr, p["lo"], p.get("hi", ""))
        entities = self._rows(c.dataset, where, c.key_expr, limit)
        body: dict[str, Any] = {"portal": c.portal, "where": where, "entities": entities}
        keys = sorted({str(r[c.key]) for r in entities if r.get(c.key) is not None})
        for rd in c.role_datasets:
            if limit:
                rows = []
                for i in range(0, len(keys), 300):
                    ids = ",".join(quote(k) for k in keys[i : i + 300])
                    rows += self._rows(rd.dataset, f"{rd.key} in ({ids})", rd.key, None)
            else:
                rows = self._rows(rd.dataset, self._range(rd.key, p["lo"], p.get("hi", "")),
                                  rd.key, None)  # fmt: skip
            body[rd.dataset] = rows
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
        by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in data["entities"]:
            if _text(r.get(c.key)):
                by_key[str(r[c.key]).strip()].append(r)
        related: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        for rd in c.role_datasets:
            for r in data.get(rd.dataset, []):
                if _text(r.get(rd.key)):
                    related[str(r[rd.key]).strip()][rd.dataset].append(r)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        for key in sorted(by_key):
            rows = sorted(by_key[key], key=canonical_json)
            yield from self._entity(fetched, observed, key, rows, related.get(key, {}))

    def _entity(
        self,
        fetched: Fetched,
        observed: date,
        key: str,
        rows: list[dict[str, Any]],
        related: Mapping[str, list[dict[str, Any]]],
    ) -> Iterator[NormalizedRow]:
        c = self.config
        raw = {"entity": rows, **{k: sorted(v, key=canonical_json) for k, v in related.items()}}
        ctx = RecordContext(fetched, c.jurisdiction, key, "business_entity", raw)
        yield ctx.source_record()
        first = rows[0]
        name = _text(first.get(c.name))
        if name is None:
            yield ctx.fact("data_issue", issue_code="missing_entity_name",
                           target_table="business", detail={"key": key})  # fmt: skip
            return
        formed = _date(first.get(c.formed_on)) if c.formed_on else None
        if formed is not None and formed > observed:
            formed = None
        valid_from = formed or observed
        principal = address_of(first, c.principal)
        mailing = address_of(first, c.mailing)
        holders: list[tuple[str, str | None, str, dict[str, Any] | None]] = []
        for spec in c.roles:
            who = holder_name(first, spec)
            if who:
                holders.append((spec.role, spec.title, who, address_of(first, spec.address)))
        for rd in c.role_datasets:
            for r in related.get(rd.dataset, []):
                who = holder_name(r, rd.holder)
                if not who:
                    continue
                raw_role = _text(r.get(rd.role_field)) if rd.role_field else None
                role = rd.role_map.get(raw_role or "", rd.holder.role)
                title = raw_role or rd.holder.title
                holders.append((role, title, who, address_of(r, rd.holder.address)))
        if c.grouped is not None:
            g = c.grouped
            for r in rows:
                t = _text(r.get(g.type_field)) or ""
                if g.addresses.get(t) == "principal" and principal is None:
                    principal = address_of(r, g.address)
                elif g.addresses.get(t) == "mailing" and mailing is None:
                    mailing = address_of(r, g.address)
                elif t in g.roles:
                    who = holder_name(r, g.roles[t])
                    if who:
                        holders.append((g.roles[t].role, g.roles[t].title or t, who,
                                        address_of(r, g.address)))  # fmt: skip
        for addr in (principal, mailing):
            if addr is not None:
                yield NormalizedRow("address", addr)
        nc = classify(name)
        yield ctx.fact(
            "business", sos_id=key, name=name, org_form=nc.org_form,
            status=_text(first.get(c.status)) if c.status else c.status_value, formed_on=formed,
            status_date=None,
            principal_address_id=None if principal is None else principal["address_id"],
            mailing_address_id=None if mailing is None else mailing["address_id"],
            valid_from=valid_from, valid_to=None,
        )  # fmt: skip
        seen: set[tuple[str, str]] = set()
        for role, title, who, addr in sorted(holders, key=lambda h: (h[0], h[2], h[1] or "")):
            party_id = stable_id(c.source_id, key, role, clean(who))
            if (party_id, role) in seen:
                continue
            seen.add((party_id, role))
            if addr is not None:
                yield NormalizedRow("address", addr)
            pc = classify(who)
            yield ctx.fact(
                "party", party_id=party_id, raw_name=who, party_kind=pc.party_kind,
                org_form=pc.org_form, org_name_norm=pc.org_name_norm,
                address_id=None if addr is None else addr["address_id"],
            )  # fmt: skip
            yield ctx.fact("business_role", sos_id=key, party_id=party_id, role=role,
                           title=title, valid_from=valid_from, valid_to=None)  # fmt: skip

    def health(self) -> HealthReport:
        c = self.config
        q = SocrataQuery(c.portal, c.dataset, f"{c.key} IS NOT NULL", (c.key_expr,), 1)
        resp = self.client.get(q.url, q.params(0))
        try:
            rows = json.loads(resp.content)
        except ValueError:
            rows = []
        ok = resp.status == 200 and bool(rows) and c.key in rows[0] and c.name in rows[0]
        shape = tuple(sorted(rows[0])) if rows else ()
        detail = "ok" if ok else f"status={resp.status} keys={list(shape)}"
        return HealthReport(c.source_id, ok, datetime.now(UTC), detail, shape)


@cache
def all_registry_adapters() -> tuple[type[BusinessRegistryAdapter], ...]:
    out = []
    for path in sorted(BUSINESS_DIR.glob("*.yaml")):
        cfg = load_registry(path)
        cls = type(
            f"Registry_{cfg.source_id.replace('.', '_')}",
            (BusinessRegistryAdapter,),
            {"source_id": cfg.source_id, "config": cfg, "pii_fields": cfg.pii_fields},
        )
        out.append(cls)
    return tuple(out)
