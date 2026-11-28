"""Indiana real-property parcels: the DLGF PARCEL file from the Indiana Gateway, per county.

Every county assessor submits a PARCEL file (50 IAC 26-20-4) to the Department of Local
Government Finance each year; the Gateway download page (config/bulk/in.dlgf.parcels.yaml)
hands out the most recent compliant one for a county as a zip, through an ASP.NET form
post. Each record carries the state parcel number, situs address, owner of record and the
owner's mailing address, property class and certified land / improvement assessed values.

One partition is one county (large counties: one row slice of it). The county zip is
downloaded once into a local cache, read slice by slice and deleted after its last slice.
Fetched content is the decoded records of the slice as JSON, in the shape an ArcGIS layer
would return, so normalization is the shared statewide-parcel code.

The state parcel number (18 digits) is written dashed, CC-TT-SS-SSS-PPP.PPP-DDD, as
in.statewide.parcels and the IN county sources carry it, so parcel_uid matches theirs.
Records whose owner asked for anonymity under IC 36-1-8.5 are kept without owner name or
mailing address: those fields are dropped before anything is stored.
"""

from __future__ import annotations

import html
import io
import json
import re
import zipfile
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, ClassVar

import yaml

from equity.adapters.base import Fetched, FetchRequest, HealthReport
from equity.adapters.http import PoliteClient, Response
from equity.adapters.rows import canonical_json
from equity.adapters.state_parcels import adapter_for, load_config
from equity.adapters.tx.harris_district import hidden_fields
from equity.config import CONFIG_DIR

CONFIG_PATH = CONFIG_DIR / "bulk" / "in.dlgf.parcels.yaml"
CONFIG = load_config(CONFIG_PATH)
COUNTY_SLICES: dict[str, int] = {
    str(k): int(v)
    for k, v in (yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")).get("county_slices")
                 or {}).items()
}  # fmt: skip

# The page's Property Files form (download.aspx, read 2026-11-25).
FORM_DATASET = "ctl00$ContentPlaceHolder1$DropDownList1"
FORM_YEAR = "ctl00$ContentPlaceHolder1$DropDownList2"
FORM_COUNTY = "ctl00$ContentPlaceHolder1$DropDownList3"
FORM_BUTTON = "ctl00$ContentPlaceHolder1$button2"
REAL_PROPERTY = "5"  # Data Set option "Real Property"
# The page's other form's selects are posted with their selected defaults, as a browser does.
FORM_DEFAULTS = {
    "ctl00$ContentPlaceHolder1$RadComboBox1": "Annual Financial Reports",
    "ctl00$ContentPlaceHolder1$RadComboBox2": "Capital Assets",
    "ctl00$ContentPlaceHolder1$DropDownListUnitType": "All",
}
FILE_FORMAT = "2021A"

# 50 IAC 26-20-4(a) HEADER record: (name, first column, last column), 1-based inclusive.
HEADER: tuple[tuple[str, int, int], ...] = (
    ("filename", 1, 10), ("county_number", 11, 12), ("county_description", 13, 32),
    ("file_format_id", 33, 37), ("assessment_year", 110, 113), ("pay_year", 114, 117),
)  # fmt: skip
# 50 IAC 26-20-4(b) PARCEL record, format 2021A: the columns kept. Not kept: neighborhood and
# site attributes, AV adjustments, circuit-breaker splits, prior values, legal description.
PARCEL: tuple[tuple[str, int, int], ...] = (
    ("parcel_number", 1, 25), ("local_parcel_number", 26, 50), ("township", 51, 54),
    ("tax_district", 58, 60), ("routing_number", 69, 93),
    ("property_address", 94, 153), ("property_city", 154, 183), ("property_zip", 184, 193),
    ("property_class", 194, 196),
    ("owner_name", 224, 303), ("owner_address", 304, 363), ("owner_city", 364, 393),
    ("owner_state", 394, 423), ("owner_zip", 424, 433), ("owner_country", 434, 436),
    ("transfer_date", 437, 446), ("zoning", 463, 467),
    ("av_land", 469, 480), ("av_improvements", 481, 492), ("av_total", 493, 504),
    ("legal_acres", 697, 708), ("anonymity", 1250, 1250),
    ("current_av_land", 1251, 1262), ("current_av_improvements", 1263, 1274),
    ("current_av_total", 1275, 1286),
)  # fmt: skip
RECORD_LENGTH = 1286
# Dropped when the record's anonymity flag (IC 36-1-8.5) is Y.
ANONYMIZED = ("owner_name", "owner_address", "owner_city", "owner_state", "owner_zip",
              "owner_country")  # fmt: skip
_NUMERIC = frozenset({"av_land", "av_improvements", "av_total", "current_av_land",
                      "current_av_improvements", "current_av_total"})  # fmt: skip
_STATE_PARCEL = re.compile(r"^\d{18}$")
_OPTION = re.compile(r'<option[^>]*?value="([^"]*)"[^>]*>([^<]*)</option>', re.IGNORECASE)
_Base = adapter_for(CONFIG)


def dashed(parcel_number: str) -> str:
    """'580221400003000005' -> '58-02-21-400-003.000-005' (50 IAC 26-8-1 digits, written as
    IGIO and the county layers write them). Anything that is not 18 digits stays as it is."""
    p = parcel_number.strip()
    if not _STATE_PARCEL.match(p):
        return p
    return f"{p[0:2]}-{p[2:4]}-{p[4:6]}-{p[6:9]}-{p[9:12]}.{p[12:15]}-{p[15:18]}"


def county_fips5(county_number: str) -> str:
    """DLGF county number (code list 59: alphabetical 01-92) -> FIPS: Adams 01 is 18001, each
    next county two higher (Ohio 58 -> 18115, Whitley 92 -> 18183)."""
    n = int(county_number)
    if not 1 <= n <= 92:
        raise ValueError(f"not an Indiana county number: {county_number!r}")
    return f"18{2 * n - 1:03d}"


def _cut(line: str, spec: tuple[tuple[str, int, int], ...]) -> dict[str, str]:
    return {name: line[a - 1 : b].strip() for name, a, b in spec}


def _number(text: str) -> str | None:
    """'000000157400' -> '157400' (whole dollars); blank or malformed -> None."""
    t = text.strip()
    if not re.fullmatch(r"-?\d+", t):
        return None
    return str(int(t))


def _acres(text: str) -> str | None:
    """Legally deeded acreage, format 8.4 with the point implied: '000001045200' -> '104.52'."""
    t = text.strip()
    if not t.isdigit():
        return None
    whole, frac = divmod(int(t), 10_000)
    return f"{whole}.{frac:04d}".rstrip("0").rstrip(".")


def parse_header(line: str) -> dict[str, str]:
    h = _cut(line, HEADER)
    if h["filename"] != "PARCEL":
        raise ValueError(f"not a PARCEL file (header filename {h['filename']!r})")
    if h["file_format_id"] != FILE_FORMAT:
        raise ValueError(f"PARCEL file format {h['file_format_id']!r}, expected {FILE_FORMAT}")
    return h


def parse_record(line: str, header: Mapping[str, str], row: int) -> dict[str, str]:
    """One PARCEL record as attributes: the kept columns (blanks dropped), the dashed parcel
    id, the county FIPS and the header's assessment and pay years."""
    if len(line) < RECORD_LENGTH:
        line = line.ljust(RECORD_LENGTH)  # trailing blanks trimmed by some exports
    rec = _cut(line, PARCEL)
    for name in _NUMERIC:
        rec[name] = _number(rec[name]) or ""
    rec["legal_acres"] = _acres(rec["legal_acres"]) or ""
    if rec["anonymity"].upper() == "Y":
        for name in ANONYMIZED:
            rec[name] = ""
    out = {k: v for k, v in rec.items() if v}
    out.update(parcel_id=dashed(rec["parcel_number"]),
               county_fips=county_fips5(header["county_number"]),
               assessment_year=header["assessment_year"], pay_year=header["pay_year"],
               _row=str(row))  # fmt: skip
    return out


def options(page: str, select_name: str) -> list[tuple[str, str]]:
    """(value, label) of every option of one <select> on the page."""
    m = re.search(rf'<select[^>]*name="{re.escape(select_name)}"[^>]*>(.*?)</select>', page,
                  re.IGNORECASE | re.DOTALL)  # fmt: skip
    if m is None:
        return []
    return [(html.unescape(v), html.unescape(t).strip()) for v, t in _OPTION.findall(m.group(1))]


class IndianaDLGFParcels(_Base):  # type: ignore[valid-type,misc]
    access_method: ClassVar[str] = "bulk"
    cache_dir: ClassVar[Path] = Path("data") / "work" / "in_dlgf"

    def __init__(self, client: PoliteClient | None = None) -> None:
        super().__init__(client or PoliteClient(min_interval_s=CONFIG.min_interval_s,
                                                timeout_s=900.0))  # fmt: skip

    def source_row(self) -> Mapping[str, Any]:
        return {**super().source_row(), "access_method": "bulk"}

    # -- the page -----------------------------------------------------------------------
    def _page(self) -> str:
        resp: Response = self.client.get(self.config.layer_url)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {self.config.layer_url}")
        return resp.content.decode("utf-8", errors="replace")

    def offered(self, page: str) -> tuple[list[str], list[str]]:
        """(years newest first, county numbers) the Property Files form offers."""
        datasets = [v for v, _ in options(page, FORM_DATASET)]
        if REAL_PROPERTY not in datasets:
            raise RuntimeError("the download page no longer offers Real Property")
        years = sorted((v for v, _ in options(page, FORM_YEAR) if v.isdigit()), reverse=True)
        counties = [v for v, _ in options(page, FORM_COUNTY) if re.fullmatch(r"\d{2}", v)]
        return years, counties

    def partitions(self, window: int = 0) -> Iterator[dict[str, str]]:
        """Every county of the newest year offered, large counties in several row slices."""
        years, counties = self.offered(self._page())
        if not years:
            raise RuntimeError("the download page offers no year")
        for county in counties:
            slices = COUNTY_SLICES.get(county, 1)
            for i in range(slices):
                yield {"county": county, "year": years[0], "slice": str(i),
                       "slices": str(slices)}  # fmt: skip

    # -- fetching -----------------------------------------------------------------------
    def _cached(self, county: str, year: str) -> Path:
        return self.cache_dir / f"realparcel_{county}_{year}.zip"

    def _zip_bytes(self, county: str, year: str) -> tuple[bytes, Any]:
        """The county zip, from the local cache when a readable copy is there."""
        cached = self._cached(county, year)
        if cached.exists() and zipfile.is_zipfile(cached):
            return cached.read_bytes(), self.client.now()
        page = self._page()
        years, counties = self.offered(page)
        if year not in years or county not in counties:
            raise ValueError(f"county {county} / year {year} is not offered on the page")
        form = {**hidden_fields(page), **FORM_DEFAULTS, FORM_DATASET: REAL_PROPERTY,
                FORM_YEAR: year, FORM_COUNTY: county, FORM_BUTTON: "Download"}  # fmt: skip
        resp = self.client.post_form(self.config.layer_url, form)
        if resp.status != 200 or not resp.content.startswith(b"PK"):
            raise RuntimeError(f"county {county} / {year}: HTTP {resp.status}, "
                               f"{resp.content_type!r}, not a zip")  # fmt: skip
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_suffix(".part")
        tmp.write_bytes(resp.content)
        tmp.replace(cached)
        return resp.content, resp.retrieved_at

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: county (DLGF number, 2 digits), year (assessment year), slice, slices (from
        partitions); optional limit (fixtures): the first N records of the slice."""
        p = request.params
        county, year = p["county"], p["year"]
        if not (re.fullmatch(r"\d{2}", county) and re.fullmatch(r"\d{4}", year)):
            raise ValueError(f"bad county/year {county!r}/{year!r}")
        index, slices = int(p.get("slice", "0")), int(p.get("slices", "1"))
        content, retrieved_at = self._zip_bytes(county, year)
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = sorted(n for n in zf.namelist() if n.lower().endswith(".txt"))
            if len(names) != 1:
                raise ValueError(f"county {county}: expected one .txt in the zip, got {names}")
            name = names[0]
            with zf.open(name) as f:  # records: non-blank lines less header and trailer
                total = sum(1 for ln in f if ln.strip() and not ln.startswith(b"TRAILER")) - 1
            start, stop = total * index // slices, total * (index + 1) // slices
            if "limit" in p:
                stop = min(stop, start + int(p["limit"]))
            rows: list[dict[str, str]] = []
            with zf.open(name) as f:
                # Single-byte decoding keeps every character in its fixed column.
                text = io.TextIOWrapper(f, encoding="cp1252", errors="replace", newline=None)
                lines = (ln for ln in text if ln.strip() and not ln.startswith("TRAILER"))
                header = parse_header(next(lines))
                if header["county_number"] != county:
                    raise ValueError(f"asked for county {county}, file is "
                                     f"{header['county_number']}")  # fmt: skip
                for i, line in enumerate(lines):
                    if i >= stop:
                        break
                    if i >= start:
                        rows.append(parse_record(line.rstrip("\r\n"), header, i))
        if index == slices - 1 and "limit" not in p:
            self._cached(county, year).unlink(missing_ok=True)
        body = canonical_json({"layer": self.config.layer_url, "file": name,
                               "rows": [start, stop], "attributes": rows})  # fmt: skip
        url = f"{self.config.layer_url}#county={county}&year={year}&rows={start}-{stop}"
        return Fetched(self.source_id, url, retrieved_at, 200, body, "application/json")

    def health(self) -> HealthReport:
        """Live: the page still offers Real Property for a year and all 92 counties."""
        try:
            years, counties = self.offered(self._page())
        except (RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, self.client.now(), repr(exc))
        ok = bool(years) and len(counties) == 92
        return HealthReport(self.source_id, ok, self.client.now(),
                            f"years {years[:1]}, {len(counties)} counties",
                            tuple(years[:1]))  # fmt: skip

    def layer_of(self, fetched: Fetched) -> int:
        return 0

    @staticmethod
    def attributes(fetched: Fetched) -> list[Mapping[str, Any]]:
        attrs = json.loads(fetched.content)["attributes"]
        if not isinstance(attrs, list):
            raise ValueError("fetched content has no attributes list")
        return attrs
