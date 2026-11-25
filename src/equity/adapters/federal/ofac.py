"""Treasury OFAC sanctions lists: the Specially Designated Nationals and Blocked Persons List
(SDN, ~19k entries: individuals, companies, vessels, aircraft) and the Consolidated
Sanctions List (the non-SDN lists: SSI, FSE, NS-MBS, CAPTA..., ~500 entries), from the
Sanctions List Service's CSV exports.

Each list is three headerless CSV files ('-0-' marks an empty cell), joined on ent_num:

  primary   SDN.CSV / CONS_PRIM.CSV: ent_num, name, type (individual, vessel, aircraft;
            '-0-' for an entity), program(s), title, call sign, vessel type, tonnage, GRT,
            vessel flag, vessel owner, remarks (dates and places of birth, ID numbers...)
  address   ADD.CSV / CONS_ADD.CSV: ent_num, address number, street address, city / state /
            postal code (one cell), country, remarks
  alias     ALT.CSV / CONS_ALT.CSV: ent_num, alias number, type (aka, fka, nka), alias name,
            remarks

What is emitted, from existing tables only (one source record per entry, record_type
sanctions_entry, key = ent_num; programs, remarks and vessel details stay in the hashed raw
record):

- party: the entry's name (role 'sanctioned'; a person with name parts, 'LAST, First
  Middle' as OFAC prints them, when the type is individual) and each alias (role 'alias'),
  once per U.S. address of the entry (or with no address when it has none); a vessel's or
  aircraft's owner (role 'vessel_owner'). A vessel's or aircraft's own name is not a party.
- address: the entry's U.S. addresses (country United States; foreign addresses stay raw).

Source: https://sanctionslistservice.ofac.treas.gov/ (exports linked from
https://ofac.treasury.gov/sanctions-list-service). U.S. government data, free, no login;
the export URLs redirect to signed download links. sanctionslistservice.ofac.treas.gov
serves no robots.txt (404 on 2026-11-25: no restrictions).
"""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import emit_party, jurisdiction, scrub_json, text
from equity.adapters.http import PoliteClient
from equity.adapters.person_lists import split_name
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address, parse_city_state_zip

EXPORTS = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports"
PAGE = "https://ofac.treasury.gov/sanctions-list-service"
CHECKED_ON = "2026-11-25"
PRIMARY = ("ent_num", "name", "type", "program", "title", "call_sign", "vess_type", "tonnage",
           "grt", "vess_flag", "vess_owner", "remarks")  # fmt: skip
ADDRESS = ("ent_num", "add_num", "address", "city_state_zip", "country", "add_remarks")
ALIAS = ("ent_num", "alt_num", "alt_type", "alt_name", "alt_remarks")
NAMES = ("name", "alt_name", "vess_owner", "remarks", "alt_remarks", "add_remarks")
THINGS = frozenset({"vessel", "aircraft"})


def read_csv(content: bytes, columns: tuple[str, ...]) -> list[dict[str, str]]:
    """A headerless OFAC CSV: '-0-' cells dropped, the trailing ^Z ignored."""
    body = content.decode("utf-8-sig", errors="replace").replace("\x1a", "")
    out = []
    for cells in csv.reader(io.StringIO(body, newline="")):
        row = {k: v for k, c in zip(columns, cells, strict=False)
               if (v := text(c)) is not None and v != "-0-"}  # fmt: skip
        if row.get("ent_num"):
            out.append(row)
    return out


def join(prim: list[dict[str, str]], adds: list[dict[str, str]], alts: list[dict[str, str]]
         ) -> list[dict[str, Any]]:  # fmt: skip
    """One entry per ent_num with its addresses and aliases."""
    by: dict[str, list[dict[str, str]]] = defaultdict(list)
    for a in adds:
        by["A" + a["ent_num"]].append(a)
    for a in alts:
        by["N" + a["ent_num"]].append(a)
    return [{**p, "addresses": by.get("A" + p["ent_num"], []),
             "aliases": by.get("N" + p["ent_num"], [])} for p in prim]  # fmt: skip


def us_address(a: Mapping[str, Any]) -> dict[str, Any] | None:
    if (text(a.get("country")) or "").upper() not in {"UNITED STATES", "USA", "US"}:
        return None
    city, st, zip5 = parse_city_state_zip(text(a.get("city_state_zip")) or "")
    return normalized_address(text(a.get("address")), city, st, zip5)


class _OFACList(Adapter):
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = (*NAMES, "address")
    files: ClassVar[tuple[str, str, str]]
    title: ClassVar[str]

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=2.0, timeout_s=300.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a federal list of named people and companies
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": f"{EXPORTS}/{self.files[0]}",
            "terms_url": PAGE,
            "terms_summary": (
                f"Treasury OFAC {self.title}, CSV exports of the Sanctions List Service "
                "(updated as designations change); U.S. government data, free, no login. "
                "sanctionslistservice.ofac.treas.gov serves no robots.txt (404)."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        yield {"list": "all"}

    def _get(self, name: str) -> tuple[bytes, datetime]:
        url = f"{EXPORTS}/{name}"
        resp = self.client.get(url)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {url}")
        return resp.content, resp.retrieved_at

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: list ('all', the only partition); limit (fixtures: the first entries, those
        with a U.S. address first)."""
        p = request.params
        if p.get("list", "all") != "all":
            raise ValueError(f"bad list {p['list']!r}")
        (prim, at), (adds, _), (alts, _) = (self._get(f) for f in self.files)
        entries = join(read_csv(prim, PRIMARY), read_csv(adds, ADDRESS), read_csv(alts, ALIAS))
        if "limit" in p:
            entries.sort(
                key=lambda e: (
                    not any(us_address(a) for a in e["addresses"]),
                    int(e["ent_num"]) if e["ent_num"].isdigit() else 0,
                )
            )
            entries = entries[: int(p["limit"])]
        body = {"files": [f"{EXPORTS}/{f}" for f in self.files], "entries": entries}
        return Fetched(self.source_id, f"{EXPORTS}/{self.files[0]}", at, 200,
                       canonical_json(body), "application/json")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, NAMES, ("address",))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        seen: set[str] = set()
        for e in sorted(data.get("entries") or [], key=canonical_json):
            key = text(e.get("ent_num"))
            name = text(e.get("name"))
            if key is None or name is None or key in seen:
                continue
            seen.add(key)
            addrs = [a for a in (us_address(x) for x in e.get("addresses") or []) if a]
            addrs = list({a["address_id"]: a for a in addrs}.values())
            ctx = RecordContext(fetched, jurisdiction(addrs[0]["state"] if addrs else None), key,
                                "sanctions_entry", e)  # fmt: skip
            yield ctx.source_record()
            kind = (text(e.get("type")) or "").lower()
            person = kind == "individual"
            places: list[dict[str, Any] | None] = [*addrs] or [None]
            names: list[tuple[str, str]] = []
            if kind not in THINGS:
                names.append(("sanctioned", name))
                names += [("alias", n) for a in e.get("aliases") or []
                          if (n := text(a.get("alt_name")))]  # fmt: skip
            elif owner := text(e.get("vess_owner")):
                names.append(("vessel_owner", owner))
            for role, who in dict.fromkeys(names):
                p = split_name(who, "last_comma_first") if person else {}
                parts = {"first_name": p.get("first"), "middle": p.get("middle"),
                         "last_name": p.get("last"), "suffix": p.get("suffix")}  # fmt: skip
                for addr in places:
                    yield from emit_party(ctx, self.source_id, role, who, addr,
                                          person=person and role != "vessel_owner",
                                          parts=parts)  # fmt: skip

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            rows = read_csv(self._get(self.files[0])[0], PRIMARY)
        except (OSError, RuntimeError, ValueError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        return HealthReport(self.source_id, bool(rows), now, f"entries={len(rows)}", PRIMARY,
                            rows=len(rows))  # fmt: skip


class OFACSDN(_OFACList):
    source_id: ClassVar[str] = "us.treasury.ofac_sdn"
    files: ClassVar[tuple[str, str, str]] = ("SDN.CSV", "ADD.CSV", "ALT.CSV")
    title: ClassVar[str] = "Specially Designated Nationals and Blocked Persons List (SDN)"


class OFACConsolidated(_OFACList):
    source_id: ClassVar[str] = "us.treasury.ofac_consolidated"
    files: ClassVar[tuple[str, str, str]] = ("CONS_PRIM.CSV", "CONS_ADD.CSV", "CONS_ALT.CSV")
    title: ClassVar[str] = "Consolidated Sanctions List (non-SDN lists)"
