"""FAA Aircraft Registry: the Releasable Aircraft Database (ReleasableAircraft.zip).

The FAA Civil Aviation Registry publishes every U.S.-registered aircraft as one zip of
comma-delimited text files, refreshed daily (11:30 pm Central). This adapter reads:

- MASTER.txt: one row per registered aircraft: N-number, serial number, manufacturer/model
  and engine codes, year built, TYPE REGISTRANT (1 individual, 2 partnership, 3 corporation,
  4 co-owned, 5 government, 7 LLC, 8 non-citizen corporation, 9 non-citizen co-owned),
  NAME and OTHER NAMES(1-5) (co-owners), STREET, STREET2, CITY, STATE, ZIP CODE, REGION,
  COUNTY (FIPS county code), COUNTRY, certificate issue / last action / airworthiness /
  expiration dates, STATUS CODE, Mode S code, fractional-owner flag, UNIQUE ID.
- ACFTREF.txt and ENGINE.txt: the make/model, seats, weight and engine named by the MASTER
  codes (only the codes the partition uses are kept).

Every file has a header row (MASTER: UTF-8 BOM, trailing comma, space-padded values), so
columns are read by header name.

What is emitted, from existing tables only:

- source_record: one per aircraft (record_key = the N-number with its N). The hashed raw
  record keeps the registration columns (ids, dates, status, registrant type, make/model).
- party: the registrant (NAME) and each co-owner (OTHER NAMES). TYPE REGISTRANT 1 (and a
  co-owner name with no organization marker on a co-owned registration) is a person, split
  as the FAA prints it, LAST FIRST MIDDLE; types 2, 3, 5, 7, 8 are organizations. The
  registrant's party carries the registration address; co-owners have none of their own.
  Dates (certificate issue, last action, airworthiness, expiration) stay in the raw record.
- address: the registration address (STREET + STREET2), for a U.S. registrant only (a
  foreign address stays in the raw record).

Withheld records: under 49 U.S.C. 44114(b) an owner may ask the FAA to withhold their name
and address; a MASTER row with no registrant name is skipped entirely.

Partitions: the registrant's STATE (the Census states and territories plus military
AA/AE/AP), and "other" for a foreign (COUNTRY not US) or blank state. A partition streams
MASTER.txt from the cached zip keeping only its state's rows, then ACFTREF and ENGINE for the
codes they use. `limit` (fixtures) stops after that many aircraft. fetch() returns the kept
rows as JSON {"file", "url", "state", "rows"}.

Access: registry.faa.gov and www.faa.gov (robots.txt included) answered every request from
this project's network with an Akamai 403 "Access Denied" on 2026-11-25, whatever the client.
The adapter does not work around it: save the zip from the download page by hand to
data/manual/us.faa.aircraft_registry/ReleasableAircraft.zip or pass path=<zip>.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_zip import DownloadClient, file_time, locate_zip, member_lines
from equity.adapters.federal.fcc_uls import MILITARY, OTHER, state_partition, us_states
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.geo import county_by_fips, state_fips
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"
PAGE = ("https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/"
        "releasable_aircraft_download")  # fmt: skip

# MASTER.txt header -> kept key. Name and street keys are the pii_fields.
MASTER = {
    "N-NUMBER": "n_number", "SERIAL NUMBER": "serial_number", "MFR MDL CODE": "mfr_mdl_code",
    "ENG MFR MDL": "eng_mfr_mdl", "YEAR MFR": "year_mfr", "TYPE REGISTRANT": "type_registrant",
    "NAME": "name", "STREET": "street_address", "STREET2": "street2_address", "CITY": "city",
    "STATE": "state", "ZIP CODE": "zip_code", "REGION": "region", "COUNTY": "county",
    "COUNTRY": "country", "LAST ACTION DATE": "last_action_date",
    "CERT ISSUE DATE": "cert_issue_date", "CERTIFICATION": "certification",
    "TYPE AIRCRAFT": "type_aircraft", "TYPE ENGINE": "type_engine",
    "STATUS CODE": "status_code", "MODE S CODE": "mode_s_code", "FRACT OWNER": "fract_owner",
    "AIR WORTH DATE": "air_worth_date", "OTHER NAMES(1)": "other_name_1",
    "OTHER NAMES(2)": "other_name_2", "OTHER NAMES(3)": "other_name_3",
    "OTHER NAMES(4)": "other_name_4", "OTHER NAMES(5)": "other_name_5",
    "EXPIRATION DATE": "expiration_date", "UNIQUE ID": "unique_id", "KIT MFR": "kit_mfr",
    "KIT MODEL": "kit_model", "MODE S CODE HEX": "mode_s_code_hex",
}  # fmt: skip
ACFTREF = {"MFR": "aircraft_mfr", "MODEL": "aircraft_model", "TYPE-ACFT": "aircraft_type",
           "AC-CAT": "aircraft_category", "NO-ENG": "no_engines", "NO-SEATS": "no_seats",
           "AC-WEIGHT": "aircraft_weight"}  # fmt: skip
ENGINE = {"MFR": "engine_mfr", "MODEL": "engine_model", "TYPE": "engine_type",
          "HORSEPOWER": "engine_horsepower", "THRUST": "engine_thrust"}  # fmt: skip
OTHER_NAMES = tuple(f"other_name_{i}" for i in range(1, 6))
PII = ("name", *OTHER_NAMES, "street_address", "street2_address", "n_number", "serial_number",
       "mode_s_code", "mode_s_code_hex", "unique_id")  # fmt: skip

PERSON_TYPES = frozenset({"1"})
CO_OWNED = frozenset({"4", "9"})
ORG_TYPES = frozenset({"2", "3", "5", "7", "8"})
SUFFIXES = frozenset({"JR", "SR", "II", "III", "IV", "V"})


def _text(value: Any) -> str | None:
    s = " ".join(str(value).split()) if value is not None else ""
    return s or None


def _zip5(value: Any) -> str | None:
    z = str(value or "").strip()
    return z[:5] if len(z) >= 5 and z[:5].isdigit() else None


def table(lines: Iterable[str]) -> Iterator[dict[str, str]]:
    """Rows of one FAA text file as {HEADER: stripped value} (blank headers dropped)."""
    reader = csv.reader(lines)
    header = [h.strip().upper() for h in next(reader, [])]
    for cells in reader:
        if cells:
            yield {h: c.strip() for h, c in zip(header, cells, strict=False) if h}


def registration_state(row: Mapping[str, Any]) -> str:
    """The partition of a MASTER row: its STATE, or 'other' when foreign or blank."""
    country = (_text(row.get("country")) or "US").upper()
    return state_partition(row.get("state")) if country == "US" else OTHER


def split_last_first(name: str) -> dict[str, str | None]:
    """'SMITH JOHN A JR' -> last SMITH, first JOHN, middle A, suffix JR (FAA order)."""
    out: dict[str, str | None] = dict.fromkeys(("last_name", "first_name", "middle", "suffix"))
    words = name.replace(",", " ").split()
    if words and words[-1].upper().rstrip(".") in SUFFIXES:
        out["suffix"] = words.pop()
    if len(words) < 2:
        return dict.fromkeys(out)
    out["last_name"], out["first_name"] = words[0], words[1]
    out["middle"] = " ".join(words[2:]) or None
    return out


class FAAAircraftRegistry(Adapter):
    source_id: ClassVar[str] = "us.faa.aircraft_registry"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    file: ClassVar[str] = "ReleasableAircraft.zip"
    pii_fields: ClassVar[tuple[str, ...]] = PII
    max_age_s: ClassVar[float] = 20 * 3600.0  # daily file; one build reuses one download

    def __init__(self, client: DownloadClient | None = None) -> None:
        self.client = client or DownloadClient(min_interval_s=2.0, timeout_s=1800.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "aircraft",
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": URL,
            "terms_url": PAGE,
            "terms_summary": (
                "FAA Releasable Aircraft Database: the Civil Aviation Registry's registered "
                "aircraft (MASTER), make/model (ACFTREF) and engine (ENGINE) files, one zip "
                "refreshed daily, free, no login; public U.S. government data. No use "
                "restriction on the download page beyond the 49 U.S.C. 44114(b) procedure "
                "by which owners have name and address withheld (such rows are skipped). "
                "registry.faa.gov and www.faa.gov, robots.txt included, answered this "
                "client with an Akamai 403 on 2026-11-25, so neither could be re-read; the "
                "adapter then reads a hand-saved zip (path= or data/manual/<source_id>/)."
            ),
            "terms_checked_on": None,
            "robots_checked_on": None,
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        for st in (*us_states(), OTHER):
            yield {"state": st}

    # -- fetch ----------------------------------------------------------------------------
    def fetch(self, request: FetchRequest) -> Fetched:
        """params: state (a partition); limit (fixtures: the first `limit` aircraft);
        path (a hand-saved zip, read instead of downloading)."""
        p = request.params
        state = p.get("state", "")
        if state != OTHER and state not in us_states():
            raise ValueError(f"unknown state partition {state!r}")
        limit = int(p["limit"]) if "limit" in p else None
        path, url, status = locate_zip(self.client, self.source_id, URL, p, self.max_age_s)
        body = {"file": self.file, "url": url, **self.extract(path, state, limit)}
        return Fetched(self.source_id, f"{url}#state={state}", file_time(path), status,
                       canonical_json(body), "application/json")  # fmt: skip

    @staticmethod
    def extract(path: Path, state: str, limit: int | None) -> dict[str, Any]:
        rows: list[dict[str, str]] = []
        for raw in table(member_lines(path, "MASTER.txt")):
            row = {k: v for col, k in MASTER.items() if (v := raw.get(col, ""))}
            if registration_state(row) != state:
                continue
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
        for member, code_key, keep in (("ACFTREF.txt", "mfr_mdl_code", ACFTREF),
                                       ("ENGINE.txt", "eng_mfr_mdl", ENGINE)):  # fmt: skip
            codes = {r[code_key] for r in rows if r.get(code_key)}
            found: dict[str, dict[str, str]] = {}
            for ref in table(member_lines(path, member)):
                code = ref.get("CODE", "")
                if code in codes and code not in found:
                    found[code] = {k: v for col, k in keep.items() if (v := ref.get(col, ""))}
            for r in rows:
                r.update(found.get(r.get(code_key, ""), {}))
        return {"state": state, "rows": rows}

    # -- normalize ------------------------------------------------------------------------
    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        seen: set[str] = set()
        addresses: set[str] = set()
        for r in sorted(data.get("rows") or [], key=canonical_json):
            nnum = _text(r.get("n_number"))
            name = _text(r.get("name"))
            if nnum is None or name is None:  # no N-number, or the owner's data withheld
                continue
            key = nnum if nnum.upper().startswith("N") else f"N{nnum}"
            if key in seen:
                continue
            seen.add(key)
            ctx = RecordContext(fetched, self.jurisdiction(r), key, "aircraft_registration", r)
            yield ctx.source_record()
            street = (
                " ".join(
                    s
                    for s in (_text(r.get("street_address")), _text(r.get("street2_address")))
                    if s
                )
                or None
            )
            addr = None
            if registration_state(r) != OTHER:
                addr = normalized_address(street, _text(r.get("city")), _text(r.get("state")),
                                          _zip5(r.get("zip_code")))  # fmt: skip
            if addr is not None and addr["address_id"] not in addresses:
                addresses.add(addr["address_id"])
                yield NormalizedRow("address", addr)
            rtype = str(r.get("type_registrant") or "").strip()
            names = [("registrant", name), *(("co_owner", n) for k in OTHER_NAMES
                                             if (n := _text(r.get(k))))]  # fmt: skip
            parties: set[str] = set()
            for role, who in names:
                party_id = stable_id(self.source_id, key, role, clean(who))
                if party_id in parties:
                    continue
                parties.add(party_id)
                address_id = addr["address_id"] if addr and role == "registrant" else None
                yield self._party(ctx, party_id, who, rtype, role, address_id)

    @staticmethod
    def _party(
        ctx: RecordContext,
        party_id: str,
        who: str,
        rtype: str,
        role: str,
        address_id: str | None,
    ) -> NormalizedRow:
        nc = classify(who)
        person = (rtype in PERSON_TYPES and role == "registrant") or (
            rtype in PERSON_TYPES | CO_OWNED and nc.party_kind != "org"
        )
        parts = split_last_first(who) if person else {}
        if person and parts.get("last_name"):
            return ctx.fact("party", party_id=party_id, raw_name=who, party_kind="person",
                            org_form=None, org_name_norm=None, address_id=address_id,
                            **parts)  # fmt: skip
        kind = "org" if rtype in ORG_TYPES else nc.party_kind
        return ctx.fact("party", party_id=party_id, raw_name=who, party_kind=kind,
                        org_form=nc.org_form,
                        org_name_norm=nc.org_name_norm or (clean(who) if kind == "org" else None),
                        address_id=address_id)  # fmt: skip

    @staticmethod
    def jurisdiction(r: Mapping[str, Any]) -> str:
        st = registration_state(r)
        if st in (OTHER, *MILITARY):
            return "US"
        county = _text(r.get("county"))
        if county and county.isdigit():
            try:
                return county_by_fips(st, county).fips5
            except KeyError:
                pass
        try:
            return state_fips(st)
        except KeyError:
            return "US"

    def health(self) -> HealthReport:
        """The download page answers and still links the zip."""
        now = datetime.now(UTC)
        try:
            resp = self.client.get(PAGE)
        except (OSError, RuntimeError) as exc:  # RuntimeError: robots.txt AccessDenied
            return HealthReport(self.source_id, False, now, repr(exc))
        linked = resp.status == 200 and self.file.encode() in resp.content
        return HealthReport(self.source_id, linked, now, f"status={resp.status} "
                            f"linked={linked}")  # fmt: skip
