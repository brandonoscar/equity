"""Indiana property sales disclosure forms (SDF), statewide, July 2008 to the current week.

Indiana requires a sales disclosure form (State Form 46021, IC 6-1.1-5.5) for every sale of
real property. The Department of Local Government Finance and the Indiana Business Research
Center publish the forms on STATS Indiana (www.stats.indiana.edu/topic/sdf.asp) as one zip
per year, no login or fee: seller and buyer names and addresses, the parcels, the property
address, the conveyance date, the sale price and the assessor's flags (land contract,
sheriff sale, quitclaim, court order, foreclosure). Phone and email columns are dropped.

Two layouts:
  2021 forward  SDF_<year>.zip: tab-delimited, quoted, SALEDISC (one row per form; UTF-16),
                SALEPARCEL (one per parcel), SALECONTAC (one per buyer, seller or preparer;
                UTF-16); the price is in cents
  2008 to 2020  SDF_View_CSV_<year>.zip: one pipe-delimited file, one row per form with up
                to three parcels, two sellers and two buyers inline; the price in dollars

A year's zip (12-66 MB) is parsed once into compact rows (the module keeps the last year
parsed) and served one county per partition {year, county} (Indiana county number 01-92,
alphabetical; FIPS = 2 x number - 1). Each form becomes a LienAdapter row: a DEED instrument
(LAND_CONTRACT when the land-contract box is checked) with the sellers as grantors, the
buyers as grantees, the price as consideration and every parcel linked as
<county FIPS>-<parcel number as printed> (newer forms print the 18-digit state number,
older ones the dashed form).
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from equity.adapters.base import Fetched, FetchRequest, HealthReport
from equity.adapters.liens import LienAdapter, LienConfig
from equity.adapters.rows import canonical_json
from equity.geo import county_by_fips

PAGE = "https://www.stats.indiana.edu/topic/sdf.asp"
BASE = "https://www.stats.indiana.edu/sdfdata/"
FIRST_YEAR = 2008
RELATIONAL_FROM = 2021
MAX_PARTIES = 4  # buyers and sellers kept per form (each)
MAX_PARCELS = 10  # parcels linked per form
COUNTIES = 92

CONFIG = LienConfig({
    "source_id": "in.dlgf.sales_disclosures",
    "state": "IN",
    "county_fips": "18",
    "api": "csv",
    "url": PAGE,
    "date_field": "conveyed_on",
    "uid": "sdf_id",
    "doc_type": {"field": "kind", "map": {"LAND CONTRACT": "LAND_CONTRACT"},
                 "default": "DEED"},
    "doc_type_raw": {"field": "kind"},
    "consideration": "price",
    "county_name_field": "county_name",
    "parcel": {"kind": "pin", "field": [f"pin{i}" for i in range(1, MAX_PARCELS + 1)],
               "county_fips": None},
    "parties": [
        *({"role": "grantor", "name": f"seller{i}",
           "address": {"line1": f"seller{i}_street", "city": f"seller{i}_city",
                       "state": f"seller{i}_state", "zip": f"seller{i}_zip"}}
          for i in range(1, MAX_PARTIES + 1)),
        *({"role": "grantee", "name": f"buyer{i}",
           "address": {"line1": f"buyer{i}_street", "city": f"buyer{i}_city",
                       "state": f"buyer{i}_state", "zip": f"buyer{i}_zip"}}
          for i in range(1, MAX_PARTIES + 1)),
    ],
    "extra_pii": ["prop_street"],
    "use_restrictions": ["no_commercial_name_address_lists"],
    "terms": {
        "url": "https://www.stats.indiana.edu/about/sdf.asp",
        "summary": (
            "STATS Indiana (Indiana Business Research Center, IU Kelley School, for the "
            "Department of Local Government Finance): free zip downloads, no login, form or "
            "fee; 'made available ... for research'; citation requested ('Source: Sales "
            "Disclosure Form Database, STATS Indiana'); no license text or use restriction. "
            "Owner names and addresses fall under Indiana APRA IC 5-14-3-3(f) (no lists of "
            "names and addresses to commercial entities for commercial purposes), tagged as "
            "in.statewide.parcels. www.stats.indiana.edu/robots.txt allows /sdfdata/."
        ),
        "checked_on": "2026-11-25",
        "robots_checked_on": "2026-11-25",
        "cost_model": "free",
    },
})  # fmt: skip


def county_name(number: str) -> str | None:
    """Indiana county number (alphabetical, 01-92) -> the census county name ('01' -> 'Adams
    County', '71' -> 'St. Joseph County'): Indiana's FIPS codes are 2 x number - 1. None
    outside 01-92."""
    try:
        n = int(number)
    except ValueError:
        return None
    return county_by_fips("IN", f"{2 * n - 1:03d}").name if 1 <= n <= COUNTIES else None


def zip_url(year: int) -> str:
    return f"{BASE}SDF_{year}.zip" if year >= RELATIONAL_FROM else f"{BASE}SDF_View_CSV_{year}.zip"


def _t(value: Any) -> str | None:
    s = " ".join(str(value or "").split())
    return s or None


def _iso(value: Any) -> str | None:
    """'2026-01-06', '2008-08-11 14:32:28.8' or '04/17/2008' -> ISO date; else None."""
    s = (_t(value) or "").split(" ")[0]
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        s = f"{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) or s.startswith("1900"):
        return None
    return s


def _price(value: Any, cents: bool) -> str | None:
    try:
        d = Decimal((_t(value) or "").replace(",", ""))
    except InvalidOperation:
        return None
    if cents:
        d = d / 100
    return str(d.quantize(Decimal("0.01"))) if d > 0 else None


def _kind(flags: Mapping[str, bool]) -> str:
    """'LAND CONTRACT' (mapped to LAND_CONTRACT) or 'SALES DISCLOSURE' with its flags."""
    if flags.get("land contract"):
        return "LAND CONTRACT"
    marks = [k for k, on in flags.items() if on]
    return "SALES DISCLOSURE" + (f" ({', '.join(marks)})" if marks else "")


def _reader(z: zipfile.ZipFile, name: str, delimiter: str) -> Iterator[dict[str, str]]:
    """Rows of a zip member as dicts; UTF-16 when the member starts with a byte-order mark."""
    with z.open(name) as raw:
        enc = "utf-16" if raw.read(2) in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    with z.open(name) as raw:
        text = io.TextIOWrapper(raw, encoding=enc, errors="replace", newline="")
        yield from csv.DictReader(text, delimiter=delimiter)


def _member(z: zipfile.ZipFile, stem: str) -> str | None:
    for n in z.namelist():
        if n.upper().endswith(stem.upper()):
            return n
    return None


def _contact(prefix: str, n: int, name: Any, street: Any, city: Any, state: Any,
             zipc: Any) -> dict[str, str | None]:  # fmt: skip
    return {f"{prefix}{n}": _t(name), f"{prefix}{n}_street": _t(street),
            f"{prefix}{n}_city": _t(city), f"{prefix}{n}_state": _t(state),
            f"{prefix}{n}_zip": _t(zipc)}  # fmt: skip


def parse_relational(content: bytes) -> dict[str, list[dict[str, Any]]]:
    """SDF_<year>.zip (2021 forward) -> {county number: [compact form rows]}."""
    z = zipfile.ZipFile(io.BytesIO(content))
    forms: dict[str, dict[str, Any]] = {}
    disc = _member(z, "SALEDISC.txt")
    for r in _reader(z, disc, "\t") if disc else ():
        sid = _t(r.get("SDF_ID"))
        county = (_t(r.get("County_ID")) or "").zfill(2)
        if not sid or not county_name(county):
            continue
        flags = {
            "land contract": r.get("B5_Land_Contract") == "Y",
            "sheriff sale": r.get("C1_Sheriff_Sale") == "Y",
            "short sale": r.get("C2_Short_Sale") == "Y",
            "quitclaim": r.get("C3_Quitclaim") == "Y",
            "auction": r.get("C4_Auction") == "Y",
            "court order": r.get("B8_Court_Order") == "Y",
            "foreclosure": r.get("G11_Special_Foreclosure") == "Y",
            "buyer loan": r.get("E8_Mortgage_Loan") == "Y",
        }
        forms[sid] = {
            "sdf_id": sid, "county_id": county, "county_name": county_name(county),
            "conveyed_on": _iso(r.get("C7_Conveyance_Date")) or _iso(r.get("P2_13_Date_Sale")),
            "price": _price(r.get("E1_Sales_Price"), cents=True), "kind": _kind(flags),
        }  # fmt: skip
    parcels = _member(z, "SALEPARCEL.txt")
    for r in _reader(z, parcels, "\t") if parcels else ():
        form = forms.get(_t(r.get("SDF_ID")) or "")
        if form is None:
            continue
        pin = _t(r.get("P2_1_Parcel_Num_Verified")) or _t(r.get("A1_Parcel_Number"))
        n = sum(1 for k in form if re.fullmatch(r"pin\d+", k)) + 1
        if pin and n <= MAX_PARCELS:
            form[f"pin{n}"] = pin
        if "prop_street" not in form:
            form.update(prop_street=_t(r.get("A5_Street1")), prop_city=_t(r.get("A5_City")),
                        prop_zip=_t(r.get("A5_ZipCode")))  # fmt: skip
    contacts = _member(z, "SALECONTAC.txt")
    for r in _reader(z, contacts, "\t") if contacts else ():
        form = forms.get(_t(r.get("SDF_ID")) or "")
        role = {"B": "buyer", "S": "seller"}.get(_t(r.get("Contact_Type")) or "")
        if form is None or role is None:
            continue
        n = sum(1 for k in form if re.fullmatch(rf"{role}\d+", k)) + 1
        name = _t(r.get("Company")) or _t(r.get("Name"))
        if name and n <= MAX_PARTIES:
            street = " ".join(s for s in (_t(r.get("Street1")), _t(r.get("Street2"))) if s)
            form.update(_contact(role, n, name, street, r.get("City"), r.get("State"),
                                 r.get("zipCode")))  # fmt: skip
    out: dict[str, list[dict[str, Any]]] = {}
    for sid in sorted(forms):
        out.setdefault(forms[sid]["county_id"], []).append(forms[sid])
    return out


# (role, column prefix, second name column): the second seller's name is 'Seller2Name'.
LEGACY_PARTIES = (("seller", "Seller", "Seller2Name"), ("buyer", "Buyer", "Buyer2"))


def parse_legacy(content: bytes) -> dict[str, list[dict[str, Any]]]:
    """SDF_View_CSV_<year>.zip (2008-2020) -> {county number: [compact form rows]}."""
    z = zipfile.ZipFile(io.BytesIO(content))
    out: dict[str, list[dict[str, Any]]] = {}
    for name in sorted(n for n in z.namelist() if n.lower().endswith(".txt")):
        for r in _reader(z, name, "|"):
            sid = _t(r.get("SDF_ID"))
            county = (_t(r.get("County_ID")) or "").zfill(2)
            if not sid or not county_name(county):
                continue
            flags = {
                "land contract": r.get("B8_Land_Contract_Assessor") == "Y",
                "quitclaim": r.get("Quitclaim") == "Y",
                "foreclosure": r.get("Foreclosure") == "Y",
                "non-warranty deed": r.get("NonWarrantyDeed") == "Y",
            }
            form: dict[str, Any] = {
                "sdf_id": sid, "county_id": county, "county_name": county_name(county),
                "conveyed_on": _iso(r.get("Conveyance_Date")) or _iso(r.get("SDF_Date")),
                "price": _price(r.get("C6_Sales_Price") or r.get("C6_Sales_price_Assessor"),
                                cents=False),
                "kind": _kind(flags), "prop_street": _t(r.get("PropStreet")),
                "prop_city": _t(r.get("PropCity")), "prop_zip": _t(r.get("PropZip")),
            }  # fmt: skip
            pins = [p for p in (_t(r.get(f"Parcel{i}")) for i in (1, 2, 3)) if p]
            form.update({f"pin{i}": p for i, p in enumerate(pins, start=1)})
            for role, col, second in LEGACY_PARTIES:
                for i, name_col in ((1, f"{col}1"), (2, second)):
                    if _t(r.get(name_col)):
                        form.update(_contact(role, i, r.get(name_col), r.get(f"{col}{i}Street"),
                                             r.get(f"{col}{i}City"), r.get(f"{col}{i}State"),
                                             r.get(f"{col}{i}ZIP")))  # fmt: skip
            out.setdefault(county, []).append(form)
    return out


# The last year parsed: (url, {county number: rows}). A build walks a year's 92 counties in
# order, so one zip is downloaded and parsed once per year, not once per county.
_YEAR: dict[str, dict[str, list[dict[str, Any]]]] = {}


class IndianaSalesDisclosures(LienAdapter):
    config: ClassVar[LienConfig] = CONFIG
    source_id = "in.dlgf.sales_disclosures"
    pii_fields: ClassVar[tuple[str, ...]] = CONFIG.pii_fields

    def partitions(self) -> Iterator[dict[str, str]]:
        last = datetime.now(UTC).year
        for year in range(FIRST_YEAR, last + 1):
            for n in range(1, COUNTIES + 1):
                yield {"year": str(year), "county": f"{n:02d}"}

    def year_rows(self, year: int) -> dict[str, list[dict[str, Any]]]:
        url = zip_url(year)
        if url not in _YEAR:
            resp = self.client.get(url)
            if resp.status != 200:
                raise RuntimeError(f"{self.source_id}: HTTP {resp.status} from {url}")
            parse = parse_relational if year >= RELATIONAL_FROM else parse_legacy
            _YEAR.clear()
            _YEAR[url] = parse(resp.content)
        return _YEAR[url]

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: year, county (01-92); limit (fixtures: first rows only)."""
        p = request.params
        year, county = int(p["year"]), str(p["county"]).zfill(2)
        rows = self.year_rows(year).get(county, [])
        if p.get("limit"):
            rows = rows[: int(p["limit"])]
        url = zip_url(year)
        body = canonical_json({"url": url, "county": county, "rows": rows})
        return Fetched(self.source_id, f"{url}#county={county}", datetime.now(UTC), 200, body,
                       "application/json")  # fmt: skip

    def health(self) -> HealthReport:
        """Up when the download page still links this year's (or, early in January, last
        year's) zip; no zip is downloaded."""
        now = datetime.now(UTC)
        page = self.client.get(PAGE)
        names = [zip_url(y).rsplit("/", 1)[1] for y in (now.year, now.year - 1)]
        listed = page.status == 200 and any(n.encode() in page.content for n in names)
        return HealthReport(self.source_id, listed, now,
                            "ok" if listed else f"{names[0]} not linked on {PAGE}")  # fmt: skip
