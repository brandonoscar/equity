"""Officers, directors, trustees and key employees named on Form 990 series e-filed returns
(IRS Tax Exempt Organization Search bulk XML), linked to the filing organization.

Each return is one XML document in a zip batch. Kept from each return:

- the filer: EIN, name, address (ReturnHeader/Filer), return type, tax period, tax year;
- the people (one list per form):
  990: Part VII Section A (Form990PartVIISectionAGrp): name, title, average hours, the
       position boxes (individual trustee or director, institutional trustee, officer, key
       employee, highest compensated employee, former) and reportable compensation;
  990-EZ: Part IV (OfficerDirectorTrusteeEmplGrp): name, title, hours, compensation;
  990-PF: Part VIII line 1 (OfficerDirTrstKeyEmplGrp): name, address, title, hours,
       compensation;
  and the officer who signed the return (BusinessOfficerGrp).
  990-T and other return types name no officers and are skipped.

What is emitted, from existing tables only:

- business: the filer, sos_id "EIN:<9 digits>" (the EO BMF source uses the same key), valid
  from the start of the tax period.
- business_role + party per person: role 'officer' (officer box; or, on a 990-EZ/PF, a title
  naming an office), 'director' (trustee or director box, or a director/trustee title), else
  'other' (key employee, highest compensated employee); a former officer is 'other' with
  "(former)" after the title. Valid from the start to the end of the tax period. Titles stay
  in business_role.title; hours and compensation stay in the source record.
- address: the filer's address, and each 990-PF person's address.

Partitions: one per year and zip batch, as linked from the Form 990 Series Downloads page
(e.g. year=2026 batch=01A). A batch (70 MB to 2 GB) is streamed to data/work/ and read member
by member, then deleted; only the kept fields are held. With `limit`, the batch is read over
HTTP Range instead (the central directory and the first members that are 990/990-EZ/990-PF
returns), so a fixture costs a few hundred kilobytes.

Source: https://www.irs.gov/charities-non-profits/form-990-series-downloads (U.S. government
data; returns of exempt organizations are public under IRC 6104; free, no login).
apps.irs.gov answers /robots.txt with a redirect to a 404 page (no rules); www.irs.gov's
robots.txt does not cover the downloads page.
"""

from __future__ import annotations

import json
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
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
    remote_zip,
    scrub_json,
    text,
)
from equity.adapters.rows import RecordContext, canonical_json

PAGE = "https://www.irs.gov/charities-non-profits/form-990-series-downloads"
BASE = "https://apps.irs.gov/pub/epostcard/990/xml"
BATCH = re.compile(r"/990/xml/(\d{4})/(\d{4})_TEOS_XML_([0-9A-Z]+)\.zip$", re.I)
CHECKED_ON = "2026-11-25"
FORMS = {"990": "IRS990", "990EZ": "IRS990EZ", "990PF": "IRS990PF"}
PEOPLE = {"IRS990": "Form990PartVIISectionAGrp", "IRS990EZ": "OfficerDirectorTrusteeEmplGrp",
          "IRS990PF": "OfficerDirTrstKeyEmplGrp"}  # fmt: skip
FLAGS = ("IndividualTrusteeOrDirectorInd", "InstitutionalTrusteeInd", "OfficerInd",
         "KeyEmployeeInd", "HighestCompensatedEmployeeInd",
         "FormerOfcrDirectorTrusteeInd")  # fmt: skip
HOURS = ("AverageHoursPerWeekRt", "AverageHoursPerWeekRltdOrgRt", "AverageHrsPerWkDevotedToPosRt")
COMP = ("ReportableCompFromOrgAmt", "ReportableCompFromRltdOrgAmt", "OtherCompensationAmt",
        "CompensationAmt", "EmployeeBenefitProgramAmt", "ExpenseAccountOtherAllwncAmt")  # fmt: skip
OFFICE = re.compile(r"\b(PRES|PRESIDENT|CEO|CFO|COO|CHIEF|TREAS|TREASURER|SECRETARY|SEC|"
                    r"CHAIR|CHAIRMAN|CHAIRPERSON|CHAIRWOMAN|VICE|VP|OFFICER|EXECUTIVE|EXEC|"
                    r"MANAGER|CONTROLLER|COMPTROLLER)\b", re.I)  # fmt: skip
BOARD = re.compile(r"\b(DIRECTOR|DIR|TRUSTEE|BOARD|MEMBER|GOVERNOR)\b", re.I)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element | None, *path: str) -> ET.Element | None:
    for name in path:
        if el is None:
            return None
        el = next((c for c in el if _local(c.tag) == name), None)
    return el


def _val(el: ET.Element | None, *path: str) -> str | None:
    found = _child(el, *path)
    return None if found is None else text("".join(found.itertext()))


def _name(el: ET.Element) -> tuple[str | None, str | None]:
    """(person name, business name) of a person group or a filer."""
    person = _val(el, "PersonNm")
    biz = _child(el, "BusinessName")
    org = None
    if biz is not None:
        org = text(" ".join(p for p in (_val(biz, "BusinessNameLine1Txt"),
                                        _val(biz, "BusinessNameLine2Txt")) if p))  # fmt: skip
    return person, org


def _address(el: ET.Element | None) -> dict[str, Any]:
    us = _child(el, "USAddress")
    if us is not None:
        street = " ".join(p for p in (_val(us, "AddressLine1Txt"), _val(us, "AddressLine2Txt"))
                          if p)  # fmt: skip
        return {"street_address": street or None, "city": _val(us, "CityNm"),
                "state": _val(us, "StateAbbreviationCd"), "zip": _val(us, "ZIPCd")}  # fmt: skip
    fa = _child(el, "ForeignAddress")
    if fa is not None:
        street = " ".join(p for p in (_val(fa, "AddressLine1Txt"), _val(fa, "AddressLine2Txt"))
                          if p)  # fmt: skip
        return {"street_address": street or None, "city": _val(fa, "CityNm"),
                "state": _val(fa, "ProvinceOrStateNm"), "country": _val(fa, "CountryCd"),
                "zip": _val(fa, "ForeignPostalCd")}  # fmt: skip
    return {}


def parse_return(xml: bytes, object_id: str) -> dict[str, Any] | None:
    """The kept fields of one e-filed return, or None for a return that names no officers."""
    root = ET.fromstring(xml)  # noqa: S314 - IRS e-file XML (no DTD); repo-configured gov host
    hdr = _child(root, "ReturnHeader")
    rtype = _val(hdr, "ReturnTypeCd")
    form = FORMS.get(rtype or "")
    filer = _child(hdr, "Filer")
    data = _child(root, "ReturnData")
    if form is None or filer is None or data is None:
        return None
    person, org = _name(filer)
    out: dict[str, Any] = {
        "object_id": object_id, "return_type": rtype, "ein": _val(filer, "EIN"),
        "name": org or person, "tax_year": _val(hdr, "TaxYr"),
        "tax_period_begin": _val(hdr, "TaxPeriodBeginDt"),
        "tax_period_end": _val(hdr, "TaxPeriodEndDt"), **_address(filer),
    }  # fmt: skip
    signer = _child(hdr, "BusinessOfficerGrp")
    if signer is not None and _val(signer, "PersonNm"):
        out["signing_officer"] = {"person_name": _val(signer, "PersonNm"),
                                  "title": _val(signer, "PersonTitleTxt")}  # fmt: skip
    people = []
    body = _child(data, form)
    for grp in body.iter() if body is not None else ():
        if _local(grp.tag) != PEOPLE[form]:
            continue
        pname, bname = _name(grp)
        if not (pname or bname):
            continue
        p: dict[str, Any] = {"person_name": pname, "business_name": bname,
                             "title": _val(grp, "TitleTxt")}  # fmt: skip
        flags = [f for f in FLAGS if _val(grp, f)]
        if flags:
            p["positions"] = flags
        for k in (*HOURS, *COMP):
            if (v := _val(grp, k)) is not None:
                p[k] = v
        if addr := _address(grp):
            p.update(addr)
        people.append(p)
    out["people"] = people
    return out


def role_of(person: Mapping[str, Any]) -> list[tuple[str, str | None]]:
    """(role, title) pairs for one listed person."""
    title = text(person.get("title"))
    flags = set(person.get("positions") or ())
    if flags:
        roles = []
        if "OfficerInd" in flags:
            roles.append("officer")
        if flags & {"IndividualTrusteeOrDirectorInd", "InstitutionalTrusteeInd"}:
            roles.append("director")
        if roles:
            return [(r, title) for r in roles]
        if "FormerOfcrDirectorTrusteeInd" in flags:
            return [("other", f"{title} (former)" if title else "former officer/director")]
        return [("other", title or ("key employee" if "KeyEmployeeInd" in flags
                                    else "highest compensated employee"))]  # fmt: skip
    if title and OFFICE.search(title):
        return [("officer", title)]
    if title and BOARD.search(title):
        return [("director", title)]
    return [("other", title)]


def _day(value: Any) -> date | None:
    s = text(value) or ""
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def iter_returns(zf: zipfile.ZipFile, limit: int | None = None) -> Iterator[dict[str, Any]]:
    """Kept returns of a batch, member by member, in the zip's order."""
    n = 0
    for info in zf.infolist():
        if info.is_dir() or not info.filename.lower().endswith(".xml"):
            continue
        if limit is not None and n >= limit:
            return
        object_id = Path(info.filename).name.removesuffix(".xml").removesuffix("_public")
        try:
            kept = parse_return(zf.read(info), object_id)
        except ET.ParseError:
            continue
        if kept is not None:
            n += 1
            yield kept


class IRS990Officers(Adapter):
    source_id: ClassVar[str] = "us.irs.990_officers"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = ("person_name", "street_address")
    cache_dir: ClassVar[Path] = Path("data") / "work" / "us_irs_990_officers"

    def __init__(self, client: BulkClient | None = None) -> None:
        self.client = client or BulkClient(min_interval_s=1.0, timeout_s=3600.0)

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "sos",  # nearest kind: a registry of organizations and their officers
            "jurisdiction": "US",
            "access_method": "bulk",
            "base_url": PAGE,
            "terms_url": PAGE,
            "terms_summary": (
                "IRS Form 990 series e-file XML (Tax Exempt Organization Search bulk data), "
                "zip batches by year; returns are public under IRC 6104; free, no login. "
                "apps.irs.gov has no robots.txt rules."
            ),
            "terms_checked_on": CHECKED_ON,
            "robots_checked_on": CHECKED_ON,
            "cost_model": "free",
        }

    def batches(self) -> list[tuple[str, str]]:
        resp = self.client.get(PAGE)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {PAGE}")
        page = resp.content.decode("utf-8", errors="replace")
        found = set()
        for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", page):
            m = BATCH.search(href)
            if m and m.group(1) == m.group(2):
                found.add((m.group(1), m.group(3).upper()))
        return sorted(found)

    def partitions(self) -> Iterator[dict[str, str]]:
        for year, batch in self.batches():
            yield {"year": year, "batch": batch}

    @staticmethod
    def batch_url(year: str, batch: str) -> str:
        if not re.fullmatch(r"\d{4}", year) or not re.fullmatch(r"[0-9A-Z]{2,4}", batch):
            raise ValueError(f"bad batch {year}/{batch}")
        return f"{BASE}/{year}/{year}_TEOS_XML_{batch}.zip"

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: year, batch (e.g. 2026, 01A); limit (fixtures: the first `limit` returns
        that name officers, read over HTTP Range)."""
        p = request.params
        year, batch = p["year"], p["batch"].upper()
        url = self.batch_url(year, batch)
        at = self.client.now()
        if "limit" in p:
            with remote_zip(self.client, url) as zf:
                filings = list(iter_returns(zf, int(p["limit"])))
        else:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=self.cache_dir) as tmp:
                dest = Path(tmp) / Path(url).name
                resp = self.client.download(url, dest)
                if resp.status != 200 or not zipfile.is_zipfile(dest):
                    raise RuntimeError(f"{url}: HTTP {resp.status} ({resp.content_type})")
                at = resp.retrieved_at
                with zipfile.ZipFile(dest) as zf:
                    filings = list(iter_returns(zf))
        body = {"year": year, "batch": batch, "url": url, "filings": filings}
        return Fetched(self.source_id, url, at, 200, canonical_json(body), "application/json")

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        return scrub_json(content, ("person_name",), ("street_address",))

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        data = json.loads(fetched.content)
        observed = fetched.retrieved_at.astimezone(UTC).date()
        seen: set[str] = set()
        for f in sorted(data.get("filings") or [], key=canonical_json):
            ein = "".join(ch for ch in str(f.get("ein") or "") if ch.isdigit())
            key = text(f.get("object_id"))
            name = text(f.get("name"))
            if len(ein) != 9 or key is None or name is None or key in seen:
                continue
            seen.add(key)
            ctx = RecordContext(fetched, jurisdiction(text(f.get("state"))), key, "form_990", f)
            yield ctx.source_record()
            begin, end = _day(f.get("tax_period_begin")), _day(f.get("tax_period_end"))
            valid_from = next((d for d in (begin, end) if d is not None and d <= observed),
                              observed)  # fmt: skip
            end = end if end is not None and end <= observed else None
            holders: list[Holder] = []
            people = list(f.get("people") or [])
            if f.get("signing_officer"):
                people.append(f["signing_officer"])
            for person in people:
                who = text(person.get("person_name")) or text(person.get("business_name"))
                if who is None:
                    continue
                addr = address(person.get("street_address"), person.get("city"),
                               person.get("state"), person.get("zip"))  # fmt: skip
                for role, title in role_of(person):
                    holders.append(Holder(role, title, who, addr,
                                          person=bool(text(person.get("person_name"))),
                                          valid_to=end))  # fmt: skip
            principal = address(f.get("street_address"), f.get("city"), f.get("state"),
                                f.get("zip"))  # fmt: skip
            yield from emit_business(
                ctx, source_id=self.source_id, sos_id=f"EIN:{ein}", name=name,
                valid_from=valid_from, principal=principal, holders=holders,
            )  # fmt: skip

    def health(self) -> HealthReport:
        try:
            found = self.batches()
        except (RuntimeError, OSError) as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        latest = found[-1] if found else None
        return HealthReport(self.source_id, bool(found), datetime.now(UTC),
                            f"{len(found)} batches; latest {latest}")  # fmt: skip
