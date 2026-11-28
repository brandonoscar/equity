"""EIA Form EIA-860 annual electric generator data: every utility that owns or operates a power
plant of 1 MW or more (~6.9k, with street address and entity type), every plant (~17k, with
its street address, county and operating utility) and the owners of jointly or third-party
owned generators (~5.7k ownership rows, with each owner's address and percent owned).

Read from the current year's zip (xls/eia860YYYY.zip on the EIA-860 page, ~24 MB; the
sheets 1___Utility_YYYYY.xlsx, 2___Plant_YYYYY.xlsx and 4___Owner_YYYYY.xlsx; the generator,
wind, solar, storage and environmental sheets are not read). Earlier years sit under
/archive/, which eia.gov's robots.txt disallows, so only the current release is read; the
early-release (ER) zip is not read.

What is emitted, from existing tables only:

- a utility (record_type eia_utility, key = utility id): business, sos_id EIA-UTIL:<id>, the
  utility name, principal address = its street address; the entity type stays in the raw
  record.
- a plant (record_type eia_plant, key = plant code): business, sos_id EIA-PLANT:<code>, the
  plant name, principal address = the plant's street address, valid from January 1 of the
  report year (as for utilities); holders (role 'other'): the operating utility (title
  OPERATOR, at the utility's address) and each owner of a generator at the plant (title
  OWNER, at the owner's address).
- address: normalized U.S. addresses.

The workbooks are read with the standard library (equity.adapters.person_lists.xlsx_rows).
One partition (year=YYYY, the current release). `limit` (fixtures) keeps the first
utilities and plants.

Source: https://www.eia.gov/electricity/data/eia860/ (U.S. Energy Information
Administration; U.S. government data, public domain, free, no login; reuse terms:
https://www.eia.gov/about/copyrights_reuse.php). robots.txt (read 2026-11-25) allows
/electricity/data/eia860/xls/ and disallows */archive/.
"""

from __future__ import annotations

import io
import json
import re
import urllib.parse
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.federal.bulk_files import (
    BulkClient,
    Holder,
    address,
    emit_business,
    jurisdiction,
    scrub_json,
    text,
)
from equity.adapters.person_lists import xlsx_rows
from equity.adapters.rows import RecordContext, canonical_json
from equity.geo import county_by_name

PAGE = "https://www.eia.gov/electricity/data/eia860/"
TERMS = "https://www.eia.gov/about/copyrights_reuse.php"
CHECKED_ON = "2026-11-25"
FILE = re.compile(r"^xls/eia860(\d{4})\.zip$", re.I)
STREETS = ("Street Address", "Owner Street Address")
NAMES = ("Utility Name", "Plant Name", "Owner Name")  # fixtures: a small owner may be a person


def sheet(zf: zipfile.ZipFile, prefix: str) -> list[dict[str, str]]:
    """The rows of the workbook whose name starts with `prefix`, keyed by its header row (the
    first row naming 'Utility ID'; the title row above it is skipped)."""
    name = next((n for n in zf.namelist() if Path(n).name.startswith(prefix)), None)
    if name is None:
        raise KeyError(f"no {prefix}* workbook in the zip")
    header: list[str] | None = None
    out = []
    for cells in xlsx_rows(io.BytesIO(zf.read(name))):
        if header is None:
            if "Utility ID" in cells:
                header = [c.strip() for c in cells]
            continue
        row = {h: v for h, c in zip(header, cells, strict=False) if h and (v := text(c))}
        if row:
            out.append(row)
    if header is None:
        raise KeyError(f"{name}: no header row")
    return out


def read_860(zf: zipfile.ZipFile, limit: int | None = None) -> dict[str, list[dict[str, Any]]]:
    utilities = sheet(zf, "1___Utility")
    plants = sheet(zf, "2___Plant")
    owners = sheet(zf, "4___Owner")
    if limit is not None:
        utilities, plants = utilities[:limit], plants[:limit]
    by_plant: dict[str, list[dict[str, str]]] = defaultdict(list)
    wanted = {p.get("Plant Code") for p in plants}
    for o in owners:
        if o.get("Plant Code") in wanted:
            by_plant[o["Plant Code"]].append(o)
    return {"utilities": utilities,
            "plants": [{**p, "owners": by_plant.get(p.get("Plant Code", ""), [])}
                       for p in plants]}  # fmt: skip


def place(st: str | None, county: str | None) -> str:
    if st and county:
        try:
            return county_by_name(st, county).fips5
        except KeyError:
            pass
    return jurisdiction(st)


class EIA860(Adapter):
    source_id: ClassVar[str] = "us.eia.form860"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = (*NAMES, *STREETS)

    def __init__(self, client: BulkClient | None = None) -> None:
        self.client = client or BulkClient(min_interval_s=2.0, timeout_s=600.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a federal register of plants and their owners
            "jurisdiction": "US",
            "access_method": self.access_method,
            "base_url": PAGE,
            "terms_url": TERMS,
            "terms_summary": (
                "EIA Form EIA-860 annual release (utilities, plants, generator owners), one "
                "zip of workbooks; U.S. government data, public domain, free, no login. "
                "robots.txt allows the current release (xls/) and disallows */archive/."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def year_urls(self) -> dict[str, str]:
        resp = self.client.get(PAGE)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {PAGE}")
        out = {}
        for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", resp.content.decode(
                "utf-8", errors="replace")):  # fmt: skip
            if m := FILE.match(href):
                out[m.group(1)] = urllib.parse.urljoin(PAGE, href)
        return dict(sorted(out.items()))

    def partitions(self) -> Iterator[dict[str, str]]:
        for year in self.year_urls():
            yield {"year": year}

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: year (the current release's year); limit (fixtures: the first utilities
        and plants)."""
        p = request.params
        year = p["year"]
        if not re.fullmatch(r"\d{4}", year):
            raise ValueError(f"bad year {year!r}")
        url = self.year_urls().get(year)
        if url is None:
            raise RuntimeError(f"{year}: no current EIA-860 zip linked on {PAGE}")
        resp = self.client.get(url)
        if resp.status != 200 or not resp.content.startswith(b"PK"):
            raise RuntimeError(f"{url}: HTTP {resp.status} ({resp.content_type}); not a zip")
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            body = read_860(zf, int(p["limit"]) if "limit" in p else None)
        return Fetched(self.source_id, url, resp.retrieved_at, 200,
                       canonical_json({"year": year, "url": url, **body}),
                       "application/json")  # fmt: skip

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, NAMES, STREETS)

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        year = str(data.get("year") or "")
        start = date(int(year), 1, 1) if year.isdigit() else observed
        start = min(start, observed)
        util_addr: dict[str, dict[str, Any] | None] = {}
        for u in data.get("utilities") or []:
            if uid := text(u.get("Utility ID")):
                util_addr[uid] = address(u.get("Street Address"), u.get("City"), u.get("State"),
                                         u.get("Zip"))  # fmt: skip
        seen: set[str] = set()
        for u in sorted(data.get("utilities") or [], key=canonical_json):
            uid, name = text(u.get("Utility ID")), text(u.get("Utility Name"))
            if not uid or not name or f"U{uid}" in seen:
                continue
            seen.add(f"U{uid}")
            ctx = RecordContext(fetched, jurisdiction(text(u.get("State"))), uid, "eia_utility",
                                u)  # fmt: skip
            yield ctx.source_record()
            yield from emit_business(ctx, source_id=self.source_id, sos_id=f"EIA-UTIL:{uid}",
                                     name=name, valid_from=start,
                                     principal=util_addr.get(uid))  # fmt: skip
        for pl in sorted(data.get("plants") or [], key=canonical_json):
            code, name = text(pl.get("Plant Code")), text(pl.get("Plant Name"))
            if not code or not name or f"P{code}" in seen:
                continue
            seen.add(f"P{code}")
            st = text(pl.get("State"))
            ctx = RecordContext(fetched, place(st, text(pl.get("County"))), code, "eia_plant", pl)
            yield ctx.source_record()
            holders = []
            if op := text(pl.get("Utility Name")):
                holders.append(Holder("other", "OPERATOR", op,
                                      util_addr.get(text(pl.get("Utility ID")) or "")))  # fmt: skip
            for o in sorted(pl.get("owners") or [], key=canonical_json):
                if owner := text(o.get("Owner Name")):
                    holders.append(Holder("other", "OWNER", owner, address(
                        o.get("Owner Street Address"), o.get("Owner City"), o.get("Owner State"),
                        o.get("Owner Zip"))))  # fmt: skip
            yield from emit_business(
                ctx, source_id=self.source_id, sos_id=f"EIA-PLANT:{code}", name=name,
                valid_from=start, principal=address(pl.get("Street Address"), pl.get("City"), st,
                                                    pl.get("Zip")),
                holders=holders,
            )  # fmt: skip

    def health(self) -> HealthReport:
        now = datetime.now(UTC)
        try:
            found = self.year_urls()
        except (OSError, RuntimeError) as exc:
            return HealthReport(self.source_id, False, now, repr(exc))
        return HealthReport(self.source_id, bool(found), now, f"current release {list(found)}")
