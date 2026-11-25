"""FCC Universal Licensing System (ULS) public weekly "complete" license files.

The FCC publishes every ULS radio service as one zip of pipe-delimited .dat tables
(https://data.fcc.gov/download/pub/uls/complete/l_<service>.zip, rebuilt each weekend; daily
transaction files sit beside them). Each license is one unique system identifier (USI); its
records across the tables share it:

- EN (entity, 30 fields): who holds the license (entity type L) and its contacts (CL),
  owners (O) and others: name as printed plus first/MI/last/suffix, street, city, state, ZIP,
  PO box, attention line, FRN, applicant type (I individual, B amateur club, C corporation,
  L LLC, G government, P partnership, U unincorporated association, T trust, ...).
- HD (license header, 59 fields): call sign, license status (A active, E expired, C
  canceled, T terminated, ...), radio service, grant, expiration, cancellation, effective and
  last action dates.
- AM (amateur only, 18 fields): operator class, region, club trustee call sign and name.

Services here, one adapter class each: amateur (l_amat), GMRS (l_gmrs), and the land mobile
licenses: private / business and public safety (l_LMpriv), commercial (l_LMcomm) and broadcast
auxiliary (l_LMbcast). Another service is a three-line subclass.

What is emitted, from existing tables only:

- source_record: one per license (record_key = the USI). The hashed raw record keeps the
  license id, call sign, status and dates (HD), operator class / trustee (AM) and each
  entity's name, address, FRN and applicant type. Phone, fax, email and the HD certifier
  and demographic fields are never kept.
- party: every named entity of the license (licensee, contacts, owners; an amateur club's
  trustee). party_kind 'person' for an individual (applicant type I, or a contact printed
  with first and last name) with the name parts; otherwise 'org' or classify()'s verdict.
- address: each entity's street address (the PO box when there is no street).
- business / business_role: when the licensee is not an individual (a club, company,
  government, ...), the license is a business row (sos_id FCC-ULS:<USI>, name = licensee,
  status = license status, formed_on = grant date, principal address), and the licensee,
  contacts, owners and trustee are business_role 'other' with titles LICENSEE / CONTACT /
  OWNER / TRUSTEE. A license held by an individual gets no business row.

ULS has no withheld-record marker: every license in these public access files is public (the
FCC leaves confidential and non-public data out of them). Records that do not parse (a field
holding a stray '|') are skipped, and a record split over two lines by a newline inside a
field is joined back.

Partitions: the licensee's state (postal code, the 56 Census states and territories plus
military AA/AE/AP), and "other" for a blank or unrecognized state (foreign addresses). One
partition reads the cached zip: EN twice (licensees of the state, then every entity of those
licenses), then HD and AM for those licenses, keeping only the partition's rows; nothing is
held but that partition's kept records. `limit` (fixtures) stops after that many licenses.
fetch() returns the kept records as JSON {"file", "url", "as_of", "state", "rows"}.

Access: data.fcc.gov robots.txt (read 2026-11-25) disallows only PiplBot; the files are public
U.S. government data with no login. On 2026-11-25 data.fcc.gov's Akamai edge answered Python's
urllib (this project's client) with 403 "Access Denied" while serving curl, same User-Agent; the
adapter does not work around that: save the zip by hand to data/manual/<source_id>/ or pass
path=<zip>.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_zip import (
    DownloadClient,
    file_time,
    locate_zip,
    member_lines,
)
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address
from equity.geo import counties, state_fips
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

CHECKED_ON = "2026-11-25"
BASE = "https://data.fcc.gov/download/pub/uls/complete/"
TERMS_URL = "https://www.fcc.gov/uls/transactions/daily-weekly"
MILITARY = ("AA", "AE", "AP")
OTHER = "other"

# Field names by position (FCC ULS Public Access Database Definitions).
EN = ("record_type", "usi", "uls_file_number", "ebf_number", "call_sign", "entity_type",
      "licensee_id", "entity_name", "first_name", "mi", "last_name", "suffix", "phone", "fax",
      "email", "street_address", "city", "state", "zip_code", "po_box", "attention_line",
      "sgin", "frn", "applicant_type_code", "applicant_type_other", "status_code",
      "status_date", "lic_category_code", "linked_usi", "linked_call_sign")  # fmt: skip
HD_WIDTH = 59
HD_KEEP = {2: "uls_file_number", 4: "call_sign", 5: "license_status", 6: "radio_service_code",
           7: "grant_date", 8: "expired_date", 9: "cancellation_date", 42: "effective_date",
           43: "last_action_date"}  # fmt: skip
AM_WIDTH = 18
AM_KEEP = {5: "operator_class", 6: "group_code", 7: "region_code", 8: "trustee_call_sign",
           9: "trustee_indicator", 15: "previous_call_sign", 16: "previous_operator_class",
           17: "trustee_name"}  # fmt: skip
EN_KEEP = ("entity_type", "licensee_id", "entity_name", "first_name", "mi", "last_name",
           "suffix", "street_address", "city", "state", "zip_code", "po_box", "attention_line",
           "frn", "applicant_type_code", "applicant_type_other", "status_code",
           "status_date")  # fmt: skip
NAME_KEYS = ("entity_name", "first_name", "mi", "last_name", "suffix")
# Names, street lines, and the ids that look a licensee up in ULS (call signs, USI, FRN...).
PII = (*NAME_KEYS, "street_address", "po_box", "attention_line", "trustee_name", "usi",
       "call_sign", "trustee_call_sign", "previous_call_sign", "frn", "licensee_id",
       "uls_file_number")  # fmt: skip

LICENSE_STATUS = {"A": "ACTIVE", "C": "CANCELED", "E": "EXPIRED", "L": "PENDING LEGAL STATUS",
                  "P": "PARENT STATION CANCELED", "T": "TERMINATED",
                  "X": "TERM PENDING"}  # fmt: skip
ROLE_TITLE = {"L": "LICENSEE", "CL": "CONTACT", "O": "OWNER"}
SUFFIXES = frozenset({"JR", "SR", "II", "III", "IV", "V"})


@cache
def us_states() -> tuple[str, ...]:
    """Postal codes a partition can name: Census states and territories, then AA/AE/AP."""
    return (*sorted({c.state for c in counties()}), *MILITARY)


@cache
def _state_set() -> frozenset[str]:
    return frozenset(us_states())


def state_partition(value: str | None) -> str:
    st = (value or "").strip().upper()
    return st if st in _state_set() else OTHER


def _text(value: Any) -> str | None:
    s = " ".join(str(value).split()) if value is not None else ""
    return s or None


def _zip5(value: Any) -> str | None:
    z = str(value or "").strip()
    return z[:5] if len(z) >= 5 and z[:5].isdigit() else None


def _day(value: Any, today: date) -> date | None:
    """'07/14/2024' -> date; blank, impossible or future dates -> None."""
    try:
        d = datetime.strptime(str(value or "").strip(), "%m/%d/%Y").replace(tzinfo=UTC).date()
    except ValueError:
        return None
    return d if d <= today else None


def records(lines: Iterable[str], kind: str, width: int) -> Iterator[list[str]]:
    """The '|' records of one .dat member as cell lists. A record broken over lines by a
    newline inside a field is joined back (with a space); a line with too many cells (a '|'
    inside a field) is skipped, as is anything not starting with the record type."""
    buf: str | None = None
    for line in lines:
        text = line.rstrip("\r\n")
        if buf is not None:
            joined = f"{buf} {text}"
            buf = None
            if joined.count("|") + 1 <= width:
                text = joined
        if not text:
            continue
        n = text.count("|") + 1
        if n < width:
            buf = text
        elif n == width and text.startswith(kind + "|"):
            yield text.split("|")


def _kept(cells: list[str], keep: Mapping[int, str]) -> dict[str, str]:
    return {k: v for i, k in keep.items() if (v := cells[i].strip())}


def _entity(cells: list[str]) -> dict[str, str]:
    row = dict(zip(EN, (c.strip() for c in cells), strict=True))
    return {k: row[k] for k in EN_KEEP if row[k]}


def read_as_of(lines: Iterable[str]) -> str | None:
    """'File Creation Date: Sun Nov 22 09:41:30 EST 2026' (the 'counts' member) -> text."""
    for line in lines:
        if line.startswith("File Creation Date:"):
            return line.split(":", 1)[1].strip()
    return None


def select(
    en: Iterable[list[str]],
    state: str,
    limit: int | None,
) -> list[str]:
    """USIs of the licenses whose licensee (entity type L) is in partition `state`, in file
    order, at most `limit`."""
    out: list[str] = []
    seen: set[str] = set()
    for cells in en:
        if cells[5] != "L" or state_partition(cells[17]) != state or cells[1] in seen:
            continue
        seen.add(cells[1])
        out.append(cells[1])
        if limit is not None and len(out) >= limit:
            break
    return out


def split_person(name: str) -> dict[str, str | None]:
    """'NELSON, DOUGLAS J' -> last/first/middle/suffix (the AM trustee name format)."""
    out: dict[str, str | None] = dict.fromkeys(("last_name", "first_name", "middle", "suffix"))
    last, comma, rest = name.partition(",")
    if not comma or not _text(last):
        return out
    words = rest.split()
    if words and words[-1].upper().rstrip(".") in SUFFIXES:
        out["suffix"] = words.pop()
    out["last_name"] = _text(last)
    if words:
        out["first_name"] = words[0]
        out["middle"] = " ".join(words[1:]) or None
    return out


class FCCULSAdapter(Adapter):
    """One ULS service's weekly complete license file; subclasses name the file."""

    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    file: ClassVar[str]  # l_amat.zip
    service: ClassVar[str]  # "Amateur Radio"
    has_am: ClassVar[bool] = False
    pii_fields: ClassVar[tuple[str, ...]] = PII
    max_age_s: ClassVar[float] = 20 * 3600.0  # a weekly file; one build reuses one download

    def __init__(self, client: DownloadClient | None = None) -> None:
        self.client = client or DownloadClient(min_interval_s=2.0, timeout_s=1800.0)

    @property
    def url(self) -> str:
        return BASE + self.file

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # the nearest source kind: a registry of named licensees
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": self.url,
            "terms_url": TERMS_URL,
            "terms_summary": (
                f"FCC ULS {self.service} licenses, weekly complete public access file "
                f"({self.file}, pipe-delimited .dat tables), free, no login. Public U.S. "
                "government data (ULS public access files). data.fcc.gov "
                "robots.txt disallows only PiplBot. Akamai answered this client's urllib "
                "with 403 on 2026-11-25 (curl was served); the adapter then reads a "
                "hand-saved zip (path= or data/manual/<source_id>/)."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def partitions(self) -> Iterator[dict[str, str]]:
        for st in (*us_states(), OTHER):
            yield {"state": st}

    # -- fetch ----------------------------------------------------------------------------
    def fetch(self, request: FetchRequest) -> Fetched:
        """params: state (a partition); limit (fixtures: the first `limit` licenses);
        path (a hand-saved zip, read instead of downloading)."""
        p = request.params
        state = p.get("state", "")
        if state != OTHER and state not in us_states():
            raise ValueError(f"unknown state partition {state!r}")
        limit = int(p["limit"]) if "limit" in p else None
        path, url, status = locate_zip(self.client, self.source_id, self.url, p, self.max_age_s)
        body = self.extract(path, state, limit)
        body["url"] = url
        return Fetched(self.source_id, f"{url}#state={state}", file_time(path), status,
                       canonical_json(body), "application/json")  # fmt: skip

    def extract(self, path: Path, state: str, limit: int | None) -> dict[str, Any]:
        """The partition's licenses from a local zip, streamed member by member."""
        usis = select(records(member_lines(path, "EN.dat"), "EN", len(EN)), state, limit)
        wanted = set(usis)
        entities: dict[str, list[dict[str, str]]] = {u: [] for u in usis}
        for cells in records(member_lines(path, "EN.dat"), "EN", len(EN)):
            if cells[1] in wanted:
                entities[cells[1]].append(_entity(cells))
        license: dict[str, dict[str, str]] = {}
        for cells in records(member_lines(path, "HD.dat"), "HD", HD_WIDTH):
            if cells[1] in wanted and cells[1] not in license:
                license[cells[1]] = _kept(cells, HD_KEEP)
                if len(license) == len(wanted):
                    break
        amateur: dict[str, dict[str, str]] = {}
        if self.has_am:
            for cells in records(member_lines(path, "AM.dat"), "AM", AM_WIDTH):
                if cells[1] in wanted and cells[1] not in amateur:
                    amateur[cells[1]] = _kept(cells, AM_KEEP)
                    if len(amateur) == len(wanted):
                        break
        try:
            as_of = read_as_of(member_lines(path, "counts"))
        except KeyError:
            as_of = None
        rows = []
        for u in usis:
            row: dict[str, Any] = {"usi": u, "entities": sorted(entities[u], key=canonical_json)}
            if u in license:
                row["license"] = license[u]
            if u in amateur:
                row["amateur"] = amateur[u]
            rows.append(row)
        return {"file": self.file, "as_of": as_of, "state": state, "rows": rows}

    # -- normalize ------------------------------------------------------------------------
    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        today = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for row in sorted(data.get("rows") or [], key=lambda r: (str(r.get("usi")),
                                                                canonical_json(r))):  # fmt: skip
            usi = _text(row.get("usi"))
            if usi is None or usi in seen:
                continue
            seen.add(usi)
            yield from self._license(fetched, usi, row, today)

    def _license(
        self, fetched: Fetched, usi: str, row: Mapping[str, Any], today: date
    ) -> Iterator[NormalizedRow]:
        ents: list[Mapping[str, Any]] = list(row.get("entities") or [])
        lic: Mapping[str, Any] = row.get("license") or {}
        licensee = next((e for e in ents if e.get("entity_type") == "L"), None)
        st = (licensee or {}).get("state")
        juris = "US"
        if st and state_partition(st) not in (OTHER, *MILITARY):
            juris = state_fips(state_partition(st))
        ctx = RecordContext(fetched, juris, usi, "fcc_license", row)
        yield ctx.source_record()
        licensee_name = self._raw_name(licensee) if licensee is not None else None
        org_licensee = (licensee is not None and licensee_name is not None
                        and not self._is_person(licensee))  # fmt: skip
        sos_id = f"FCC-ULS:{usi}"
        granted = _day(lic.get("grant_date"), today)
        valid_from = granted or today
        addresses: set[str] = set()
        parties: set[str] = set()
        if org_licensee:
            assert licensee is not None
            addr = self._address(licensee)
            if addr is not None:
                addresses.add(addr["address_id"])
                yield NormalizedRow("address", addr)
            bname = str(licensee_name)
            status = _text(lic.get("license_status"))
            yield ctx.fact(
                "business", sos_id=sos_id, name=bname, org_form=classify(bname).org_form,
                status=LICENSE_STATUS.get(status or "", status), formed_on=granted,
                status_date=_day(lic.get("last_action_date"), today),
                principal_address_id=addr["address_id"] if addr else None,
                mailing_address_id=None, valid_from=valid_from, valid_to=None,
            )  # fmt: skip
        order = {"L": 0, "CL": 1, "O": 2}
        for e in sorted(ents, key=lambda e: (order.get(str(e.get("entity_type")), 9),
                                             canonical_json(e))):  # fmt: skip
            name = self._raw_name(e)
            if name is None:
                continue
            etype = str(e.get("entity_type") or "")
            role = ROLE_TITLE.get(etype, etype or "ENTITY")
            addr = self._address(e)
            if addr is not None and addr["address_id"] not in addresses:
                addresses.add(addr["address_id"])
                yield NormalizedRow("address", addr)
            party_id = stable_id(self.source_id, usi, role, clean(name))
            if party_id in parties:
                continue
            parties.add(party_id)
            yield self._party(ctx, party_id, name, e, addr)
            if org_licensee:
                yield ctx.fact("business_role", sos_id=sos_id, party_id=party_id, role="other",
                               title=role, valid_from=valid_from, valid_to=None)  # fmt: skip
        trustee = _text((row.get("amateur") or {}).get("trustee_name"))
        if trustee is not None:
            party_id = stable_id(self.source_id, usi, "TRUSTEE", clean(trustee))
            if party_id not in parties:
                parts = split_person(trustee)
                kind = "person" if parts["last_name"] else classify(trustee).party_kind
                nc = classify(trustee)
                yield ctx.fact(
                    "party", party_id=party_id, raw_name=trustee, party_kind=kind,
                    org_form=nc.org_form if kind != "person" else None,
                    org_name_norm=nc.org_name_norm if kind != "person" else None,
                    address_id=None, **(parts if kind == "person" else {}),
                )  # fmt: skip
                if org_licensee:
                    yield ctx.fact("business_role", sos_id=sos_id, party_id=party_id,
                                   role="other", title="TRUSTEE", valid_from=valid_from,
                                   valid_to=None)  # fmt: skip

    @staticmethod
    def _is_person(e: Mapping[str, Any]) -> bool:
        code = str(e.get("applicant_type_code") or "")
        if code:
            return code == "I"
        return bool(_text(e.get("last_name")) and _text(e.get("first_name")))

    @staticmethod
    def _raw_name(e: Mapping[str, Any]) -> str | None:
        name = _text(e.get("entity_name"))
        if name is not None:
            return name
        parts = [_text(e.get(k)) for k in ("first_name", "mi", "last_name", "suffix")]
        return " ".join(p for p in parts if p) or None

    @staticmethod
    def _address(e: Mapping[str, Any]) -> dict[str, Any] | None:
        street = _text(e.get("street_address"))
        box = _text(e.get("po_box"))
        if street is None and box is not None:
            street = box if re.match(r"(?i)^P\.?\s*O\b", box) else f"PO BOX {box}"
        return normalized_address(street, _text(e.get("city")), _text(e.get("state")),
                                  _zip5(e.get("zip_code")))  # fmt: skip

    def _party(
        self,
        ctx: RecordContext,
        party_id: str,
        name: str,
        e: Mapping[str, Any],
        addr: Mapping[str, Any] | None,
    ) -> NormalizedRow:
        address_id = addr["address_id"] if addr else None
        if self._is_person(e) and _text(e.get("last_name")):
            return ctx.fact(
                "party", party_id=party_id, raw_name=name, party_kind="person", org_form=None,
                org_name_norm=None, address_id=address_id, last_name=_text(e.get("last_name")),
                first_name=_text(e.get("first_name")), middle=_text(e.get("mi")),
                suffix=_text(e.get("suffix")),
            )  # fmt: skip
        nc = classify(name)
        code = str(e.get("applicant_type_code") or "")
        kind = "org" if code and code != "I" else nc.party_kind
        return ctx.fact("party", party_id=party_id, raw_name=name, party_kind=kind,
                        org_form=nc.org_form, org_name_norm=nc.org_name_norm or
                        (clean(name) if kind == "org" else None),
                        address_id=address_id)  # fmt: skip

    def health(self) -> HealthReport:
        """The complete-files index lists this service's zip."""
        now = datetime.now(UTC)
        try:
            resp = self.client.get(BASE)
        except (OSError, RuntimeError) as exc:  # RuntimeError: robots.txt AccessDenied
            return HealthReport(self.source_id, False, now, repr(exc))
        listed = resp.status == 200 and self.file.encode() in resp.content
        return HealthReport(self.source_id, listed, now, f"status={resp.status} "
                            f"listed={listed}")  # fmt: skip


class FCCULSAmateur(FCCULSAdapter):
    source_id: ClassVar[str] = "us.fcc.uls_amateur"
    file: ClassVar[str] = "l_amat.zip"
    service: ClassVar[str] = "Amateur Radio (HA, HV)"
    has_am: ClassVar[bool] = True


class FCCULSGMRS(FCCULSAdapter):
    source_id: ClassVar[str] = "us.fcc.uls_gmrs"
    file: ClassVar[str] = "l_gmrs.zip"
    service: ClassVar[str] = "General Mobile Radio Service (ZA)"


class FCCULSLandMobilePrivate(FCCULSAdapter):
    source_id: ClassVar[str] = "us.fcc.uls_land_mobile_private"
    file: ClassVar[str] = "l_LMpriv.zip"
    service: ClassVar[str] = "Land Mobile Private (industrial/business, public safety)"


class FCCULSLandMobileCommercial(FCCULSAdapter):
    source_id: ClassVar[str] = "us.fcc.uls_land_mobile_commercial"
    file: ClassVar[str] = "l_LMcomm.zip"
    service: ClassVar[str] = "Land Mobile Commercial"


class FCCULSLandMobileBroadcast(FCCULSAdapter):
    source_id: ClassVar[str] = "us.fcc.uls_land_mobile_broadcast"
    file: ClassVar[str] = "l_LMbcast.zip"
    service: ClassVar[str] = "Land Mobile Broadcast Auxiliary"


FCC_ULS_ADAPTERS: tuple[type[FCCULSAdapter], ...] = (
    FCCULSAmateur, FCCULSGMRS, FCCULSLandMobilePrivate, FCCULSLandMobileCommercial,
    FCCULSLandMobileBroadcast,
)  # fmt: skip
