"""Cook County, IL parcels: the Cook County Assessor's open data on Socrata.

Parcel Addresses (3723-97qp) gives each PIN's property address, owner name and address, and
taxpayer (mailing) name and address; Assessed Values (uzyt-m557) gives the property class and
assessed values. Both carry one row per PIN per tax year, so they are joined on (pin, year)
for the latest year in Parcel Addresses (fixed when the build is planned).

The build is cut into PIN ranges: a PIN starts with its two-digit area and two-digit section,
so each partition is one area's sections 0x, 1x, 2x or 3x+ (at most about 60k parcels).

Normalization is the shared statewide-parcel code (config/bulk/il.cook.parcels.yaml): rows are
handed over in the shape an ArcGIS layer would return. On top of it, the taxpayer of record is
a second owner (owner_seq 2, owner_type 'taxpayer') with its own mailing address when it names
someone else than the owner: the dataset notes that owner names are only intermittently
updated, so the taxpayer is often the current owner.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC
from itertools import pairwise
from typing import Any, ClassVar

from equity.adapters.base import Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.socrata import SocrataError, SocrataQuery, fetch_all, parse_rows, quote
from equity.adapters.state_parcels import (
    _ZIP,
    _text,
    adapter_for,
    load_config,
    normalized_address,
)
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

CONFIG = load_config(CONFIG_DIR / "bulk" / "il.cook.parcels.yaml")
PORTAL = "https://datacatalog.cookcountyil.gov"
ADDRESSES = "3723-97qp"
VALUES = "uzyt-m557"
ADDRESS_COLS = (
    "pin", "year", "prop_address_full", "prop_address_city_name", "prop_address_state",
    "prop_address_zipcode_1", "mail_address_name", "mail_address_full",
    "mail_address_city_name", "mail_address_state", "mail_address_zipcode_1",
    "owner_address_name", "owner_address_full", "owner_address_city_name",
    "owner_address_state", "owner_address_zipcode_1",
)  # fmt: skip
VALUE_COLS = (
    "pin", "year", "class", "township_code", "mailed_land", "mailed_bldg", "mailed_tot",
    "certified_land", "certified_bldg", "certified_tot", "board_land", "board_bldg", "board_tot",
)  # fmt: skip
# Latest assessment stage first: Board of Review, Assessor certified, Assessor mailed.
STAGES = ("board", "certified", "mailed")
# Names the roll uses when no name is on file: not a party.
PLACEHOLDERS = frozenset({
    "TAXPAYER OF", "TAX PAYER OF", "TAXPAYER", "CURRENT OWNER", "CURRENT TAXPAYER", "OWNER",
    "OCCUPANT", "CURRENT OCCUPANT", "UNKNOWN",
})  # fmt: skip
NAME_FIELDS = ("owner_address_name", "mail_address_name")
ADDRESS_FIELDS = ("owner_address_full", "mail_address_full", "prop_address_full")
_Base = adapter_for(CONFIG)


def norm_pin(raw: Any) -> str | None:
    """A 14-digit PIN; exports can drop leading zeros, so shorter digit strings are padded."""
    s = str(raw or "").strip().replace("-", "")
    if not (s.isascii() and s.isdigit()) or len(s) > 14:
        return None
    return s.zfill(14)


def _name(value: Any) -> str | None:
    text = _text(value)
    return None if text is None or clean(text) in PLACEHOLDERS else text


def assessed(values: Mapping[str, Any]) -> tuple[str | None, Any]:
    """(stage, total) of the latest stage with a total: board, then certified, then mailed."""
    for stage in STAGES:
        total = values.get(f"{stage}_tot")
        if _text(total) is not None:
            return stage, total
    return None, None


def pin_bounds(lo_area: int, hi_area: int) -> list[tuple[str, str]]:
    """Half-open PIN ranges covering areas lo_area..hi_area: per area, sections 0x, 1x, 2x
    and 3x-9x (sections run 01-36)."""
    cuts = [f"{a:02d}{d}" for a in range(lo_area, hi_area + 1) for d in range(4)]
    cuts.append(f"{hi_area + 1:02d}0")
    return list(pairwise(cuts))


class CookCountyParcels(_Base):  # type: ignore[valid-type,misc]
    access_method: ClassVar[str] = "api"
    url: ClassVar[str] = f"{PORTAL}/resource/{ADDRESSES}.json"

    def __init__(self, client: PoliteClient | None = None) -> None:
        super().__init__(client or PoliteClient(min_interval_s=CONFIG.min_interval_s,
                                                timeout_s=300.0))  # fmt: skip

    def source_row(self) -> Mapping[str, Any]:
        return {**super().source_row(), "kind": "assessor", "jurisdiction": "17031",
                "access_method": "api"}  # fmt: skip

    # -- planning -----------------------------------------------------------------------
    def _one(self, dataset: str, select: str, where: str | None = None) -> dict[str, Any]:
        params = {"$select": select} | ({"$where": where} if where else {})
        resp = self.client.get(f"{PORTAL}/resource/{dataset}.json", params)
        if resp.status != 200:
            raise SocrataError(f"HTTP {resp.status} from {resp.url}")
        rows = parse_rows(resp.content)
        if not rows:
            raise SocrataError(f"{dataset}: empty answer to {select}")
        return rows[0]

    def partitions(self, window: int = 0) -> Iterator[dict[str, str]]:
        """The latest tax year, cut into PIN ranges (see pin_bounds)."""
        year = int(float(self._one(ADDRESSES, "max(year) AS y")["y"]))
        span = self._one(ADDRESSES, "min(pin) AS lo, max(pin) AS hi", f"year = {year}")
        for lo, hi in pin_bounds(int(span["lo"][:2]), int(span["hi"][:2])):
            yield {"year": str(year), "pin_min": lo, "pin_max": hi}

    # -- fetching -----------------------------------------------------------------------
    def fetch(self, request: FetchRequest) -> Fetched:
        """params: year, pin_min, pin_max (half-open); optional limit = one page (fixtures)."""
        p = request.params
        year = int(p["year"])
        where = f"year = {year} AND pin >= {quote(p['pin_min'])} AND pin < {quote(p['pin_max'])}"
        limit = p.get("limit")
        size = int(limit) if limit else CONFIG.page_size
        aq = SocrataQuery(PORTAL, ADDRESSES, where, ("pin", ":id"), size, ADDRESS_COLS)
        addrs, resps = fetch_all(self.client, aq, max_pages=1 if limit else 10_000,
                                 sample=limit is not None)  # fmt: skip
        vwhere = where
        if limit:  # a fixture keeps only the values of its sampled PINs
            pins = ",".join(quote(x) for x in sorted({str(a.get("pin")) for a in addrs}))
            vwhere = f"year = {year} AND pin in ({pins or quote('')})"
        vq = SocrataQuery(PORTAL, VALUES, vwhere, ("pin", ":id"), CONFIG.page_size, VALUE_COLS)
        values, _ = fetch_all(self.client, vq)
        body = canonical_json({"year": year, "where": where, "addresses": addrs,
                               "values": values})  # fmt: skip
        return Fetched(self.source_id, f"{self.url}?$where={where}", resps[-1].retrieved_at,
                       200, body, "application/json")  # fmt: skip

    @staticmethod
    def scrub_fixture(content: bytes) -> bytes:
        """Fixture pseudonyms (equity.adapters.record): owner and taxpayer names share one
        pseudonym space, as do the three street lines, so equal values stay equal."""
        from equity.adapters.record import pseudonym  # record imports the registry

        data = json.loads(content)
        for row in data["addresses"]:
            for k, label in [(f, "name") for f in NAME_FIELDS] + [
                (f, "address") for f in ADDRESS_FIELDS
            ]:
                v = row.get(k)
                if isinstance(v, str) and v.strip():
                    row[k] = pseudonym(label, v)
        return canonical_json(data)

    def health(self) -> HealthReport:
        """Live: both datasets answer, and their latest year has rows with a PIN."""
        try:
            got = []
            for dataset in (ADDRESSES, VALUES):
                q = SocrataQuery(PORTAL, dataset, "pin IS NOT NULL", ("year DESC", ":id"), 1)
                resp = self.client.get(q.url, q.params(0))
                rows = parse_rows(resp.content) if resp.status == 200 else []
                got.append(rows[0] if rows else {})
        except (ValueError, OSError) as exc:
            return HealthReport(self.source_id, False, self.client.now(), repr(exc))
        ok = all("pin" in r for r in got)
        shape = tuple(sorted(set(got[0]) | set(got[1])))
        return HealthReport(self.source_id, ok, self.client.now(), "ok" if ok else repr(got),
                            shape)  # fmt: skip

    # -- normalization ------------------------------------------------------------------
    def layer_of(self, fetched: Fetched) -> int:
        return 0

    @staticmethod
    def attributes(fetched: Fetched) -> list[Mapping[str, Any]]:
        """Address rows joined to their PIN's values: 14-digit pin, placeholder names
        dropped, and _av_total / _av_stage from the latest assessment stage."""
        data = json.loads(fetched.content)
        year = str(data["year"])
        values: dict[str, Mapping[str, Any]] = {}
        for v in data.get("values") or []:
            pin = norm_pin(v.get("pin"))
            if pin is not None and str(v.get("year")) == year:
                values.setdefault(pin, v)
        out: list[Mapping[str, Any]] = []
        for a in data.get("addresses") or []:
            pin = norm_pin(a.get("pin"))
            if pin is None or str(a.get("year")) != year:
                continue
            v = values.get(pin, {})
            stage, total = assessed(v)
            out.append({**a, "pin": pin, "class": v.get("class"),
                        "owner_address_name": _name(a.get("owner_address_name")),
                        "mail_address_name": _name(a.get("mail_address_name")),
                        "_av_total": total, "_av_stage": stage})  # fmt: skip
        return out

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        yield from super().normalize(fetched)
        yield from self._taxpayers(fetched)

    def _taxpayers(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        """The taxpayer as owner 2, unless it is the owner (same name, or one name a
        truncation of the other: the roll cuts names at 22 characters)."""
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for a in sorted(self.attributes(fetched), key=lambda r: str(r["pin"])):
            pin = str(a["pin"])
            name = a.get("mail_address_name")
            if pin in seen or not name:
                continue
            seen.add(pin)
            tp, owner = clean(str(name)), clean(str(a.get("owner_address_name") or ""))
            if owner and (tp.startswith(owner) or owner.startswith(tp)):
                continue
            ctx = RecordContext(fetched, "17031", pin, "parcel", dict(a))
            m = _ZIP.match(str(a.get("mail_address_zipcode_1") or ""))
            addr = normalized_address(_text(a.get("mail_address_full")),
                                      _text(a.get("mail_address_city_name")),
                                      _text(a.get("mail_address_state")),
                                      m.group(1) if m else None)  # fmt: skip
            if addr is not None:
                yield NormalizedRow("address", addr)
            nc = classify(str(name))
            party_id = stable_id(self.source_id, pin, "owner", "2", tp)
            yield ctx.fact("party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
                           org_form=nc.org_form, org_name_norm=nc.org_name_norm,
                           address_id=None if addr is None else addr["address_id"])  # fmt: skip
            yield ctx.fact("owner_snapshot", parcel_uid=f"17031-{pin}", owner_seq=2,
                           party_id=party_id, deed_book=None, deed_page=None,
                           owner_type="taxpayer", observed_on=observed)  # fmt: skip
