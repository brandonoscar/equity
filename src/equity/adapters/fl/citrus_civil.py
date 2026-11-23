"""Citrus County (FL) Clerk: civil cases, parties and judgments from the free Bulk Data export.

The clerk's "Court Records Search - Bulk Data" page (config/courts_state/fl.citrus.civil.yaml)
is a public export form: pick filings or dispositions, a date window, the court types and
what to include, and it returns export.zip with three CSVs:

    export_Case.csv    UniformCaseNumber, CaseNumber, CourtType, CaseType, FileDate,
                       DispositionDate, Judge, CaseStatus, Disposition
    export_Party.csv   UniformCaseNumber, Description (Plaintiff/Defendant/Attorney...),
                       PartyType (PRIMARY/AKA), Last/First/Middle/Suffix name, ActiveAddress
                       (one line: "street, city, ST zip"), LinkedParty, BarNumber (plus Race,
                       DOB, Gender, DLNo: dropped at fetch, never stored)
    export_Docket.csv  UniformCaseNumber, DocketDate, dockettext

Partitions are calendar months of disposition date (civil court types only). Each case
becomes a court_case with its plaintiffs and defendants (addresses kept). Judgments come
from docket entries such as "DEFAULT FINAL JUDGMENT E - RECORDED (OR.3725.1856. /
2026069564)" (the clerk records the judgment in Official Records: book, page, instrument);
a case with no judgment entry but a "DISPOSED BY DEFAULT" disposition gets one default
judgment on its disposition date. The export carries no judgment amounts.

The form is a Livewire page: GET it (session cookie + CSRF token + component snapshot),
then POST the form's update with a call to submitForm; the JSON answer holds the zip,
base64-encoded. Both requests go through PoliteClient (robots.txt, spacing, retries).
"""

from __future__ import annotations

import base64
import csv
import html
import http.cookiejar
import io
import json
import re
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, timedelta
from functools import cache
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient, Response, decode_body
from equity.adapters.rows import RecordContext, canonical_json
from equity.adapters.state_parcels import normalized_address, parse_full_address
from equity.config import CONFIG_DIR
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

CONFIG = "courts_state/fl.citrus.civil.yaml"
COUNTY = "12017"
COURT_ID = "fl.5th_circuit.citrus.civil"
CASE_COLUMNS = ("UniformCaseNumber", "CaseNumber", "CourtType", "CourtTypeLong", "CaseType",
                "FileDate", "DispositionDate", "CourtTypeCategory", "Judge", "CaseStatus",
                "Disposition")  # fmt: skip
# Party columns kept; Race, DOB, Gender, DLNo and BarNumber are never stored.
PARTY_COLUMNS = ("UniformCaseNumber", "Description", "PartyType", "LastName", "FirstName",
                 "MiddleName", "SuffixName", "ActiveAddress", "LinkedParty")  # fmt: skip
DOCKET_COLUMNS = ("UniformCaseNumber", "DocketDate", "dockettext")
# Pseudonymized in fixtures (the repo is public).
PII_FIELDS: tuple[str, ...] = ("LastName", "FirstName", "MiddleName", "ActiveAddress",
                               "LinkedParty")  # fmt: skip
# Words docket text may keep in a fixture (scrub_fixture); everything else is pseudonymized.
_DOCKET_VOCABULARY = """
A AFFIDAVIT AFTER AGAINST AGREED AMENDED AND ANSWER AS AT BANKRUPTCY CASE CERTIFICATE CLERK
CONSENT CONTINUING COSTS COUNT COURT DEFAULT DEFENDANT DEFENDANTS DEFERRED DEFICIENCY DENYING
DISMISS DISMISSAL DISMISSED DISMISSING DISBURSEMENT E ENTRY EVICTION EXECUTION EXHIBITS FEES
FILED FILING FINAL FOR FORECLOSURE FROM FUNDS GARNISHMENT GRANTING HEARING IN INTEREST JUDGMENT
LEVY LIEN MORTGAGE MOTION NOTICE OF ON OR ORDER PARTIAL PLAINTIFF PLAINTIFFS POSSESSION REM
RECORDED REPLEVIN RESPONSE SATISFACTION SET STIPULATED STIPULATION SUGGESTION SUMMARY THE TO
UNIFORM VACATE WITH WRIT
"""
DOCKET_WORDS = frozenset(_DOCKET_VOCABULARY.split())
_OR_REF = re.compile(r"\(OR\.(\d+)\.(\d+)\.?\s*/\s*(\d+)\)")
_SNAPSHOT = re.compile(r'wire:snapshot="([^"]*)"')
_TOKEN = re.compile(r'<meta name="csrf-token" content="([^"]+)"')


@dataclass(frozen=True)
class CitrusConfig:
    source_id: str
    base_url: str
    court_types: tuple[str, ...]
    first_month: date
    docket_keep: re.Pattern[str]
    judgment_marker: re.Pattern[str]
    judgment_words: re.Pattern[str]
    judgment_kinds: re.Pattern[str]
    not_judgment: re.Pattern[str]
    judgment_types: tuple[tuple[re.Pattern[str], str], ...]
    disposition_judgments: Mapping[str, str]
    party_roles: Mapping[str, str]
    terms: Mapping[str, Any]


@cache
def load_config() -> CitrusConfig:
    import yaml

    d = yaml.safe_load((CONFIG_DIR / CONFIG).read_text(encoding="utf-8"))
    y, m = (int(x) for x in str(d["first_month"]).split("-")[:2])
    return CitrusConfig(
        source_id=d["source_id"],
        base_url=d["base_url"],
        court_types=tuple(str(c) for c in d["court_types"]),
        first_month=date(y, m, 1),
        docket_keep=re.compile(d["docket_keep"], re.IGNORECASE),
        judgment_marker=re.compile(d["judgment_marker"]),
        judgment_words=re.compile(d["judgment_words"]),
        judgment_kinds=re.compile(d["judgment_kinds"]),
        not_judgment=re.compile(d["not_judgment"]),
        judgment_types=tuple((re.compile(k), str(v)) for k, v in d["judgment_types"].items()),
        disposition_judgments=dict(d["disposition_judgments"]),
        party_roles=dict(d["party_roles"]),
        terms=dict(d["terms"]),
    )


# -- parsing helpers -----------------------------------------------------------------------
def iso_date(value: str | None) -> date | None:
    """' 2026-11-16 00:00:00' -> date; blank or malformed -> None."""
    head = (value or "").strip()[:10]
    try:
        return date.fromisoformat(head)
    except ValueError:
        return None


def case_uid(uniform: str) -> str:
    return f"fl.citrus:{clean_case(uniform)}"


def clean_case(raw: str) -> str:
    return re.sub(r"\s+", "", raw.upper())


def party_name(row: Mapping[str, str]) -> str:
    """'Doe', 'Ann', 'B', 'Jr' -> 'Ann B Doe Jr'; an organization is its LastName alone."""
    parts = (row.get("FirstName"), row.get("MiddleName"), row.get("LastName"),
             row.get("SuffixName"))  # fmt: skip
    return " ".join(" ".join(p.split()) for p in parts if p and p.strip())


def party_address(raw: str | None) -> dict[str, Any] | None:
    text = " ".join((raw or "").split())
    if not text:
        return None
    line, city, state, zip5 = parse_full_address(text)
    return normalized_address(line or None, city, state, zip5)


def judgment_type(cfg: CitrusConfig, text: str) -> str | None:
    """Docket text -> judgment_type, or None when the entry is not a judgment."""
    t = " ".join(_OR_REF.sub("", text).upper().split())
    if not (cfg.judgment_marker.search(t) and cfg.judgment_words.search(t)
            and cfg.judgment_kinds.search(t)):  # fmt: skip
        return None
    if cfg.not_judgment.search(t):
        return None
    for pattern, jtype in cfg.judgment_types:
        if pattern.search(t):
            return jtype
    return "other"


def or_reference(text: str) -> str | None:
    """'... E - RECORDED (OR.3725.1924. / 2026069580)' -> 'OR 3725/1924 instrument 2026069580'."""
    m = _OR_REF.search(text)
    return None if m is None else f"OR {m.group(1)}/{m.group(2)} instrument {m.group(3)}"


def read_csv(data: bytes) -> list[dict[str, str]]:
    text = data.decode("utf-8-sig", errors="replace")
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()}
            for r in csv.DictReader(io.StringIO(text, newline=""))]  # fmt: skip


def unpack_export(
    zip_bytes: bytes, docket_keep: re.Pattern[str]
) -> dict[str, list[dict[str, str]]]:
    """export.zip -> {'cases', 'parties', 'dockets'} with only the stored columns: attorney
    rows and docket rows that say nothing about a judgment are dropped."""
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = set(z.namelist())

    def table(name: str, cols: tuple[str, ...]) -> list[dict[str, str]]:
        if name not in names:
            return []
        return [{c: r.get(c, "") for c in cols if r.get(c, "")} for r in read_csv(z.read(name))]

    cases = table("export_Case.csv", CASE_COLUMNS)
    parties = [r for r in table("export_Party.csv", PARTY_COLUMNS)
               if "ATTORNEY" not in r.get("Description", "").upper()]  # fmt: skip
    dockets = [r for r in table("export_Docket.csv", DOCKET_COLUMNS)
               if docket_keep.search(r.get("dockettext", ""))]  # fmt: skip
    key = canonical_json
    return {"cases": sorted(cases, key=key), "parties": sorted(parties, key=key),
            "dockets": sorted(dockets, key=key)}  # fmt: skip


def months(first: date, last: date) -> Iterator[tuple[date, date]]:
    """Calendar-month windows [from, to] covering first..last (last window ends at last)."""
    start = first.replace(day=1)
    while start <= last:
        nxt = (start + timedelta(days=32)).replace(day=1)
        yield start, min(nxt - timedelta(days=1), last)
        start = nxt


# -- HTTP: the export form needs its session cookie on the POST -------------------------------
@dataclass
class CookieTransport:
    """GET and POST transports for PoliteClient that share one cookie jar (the Laravel
    session the CSRF token belongs to). POST sends the Content-Type its caller names."""

    jar: http.cookiejar.CookieJar = field(default_factory=http.cookiejar.CookieJar)

    def _open(
        self, url: str, headers: Mapping[str, str], data: bytes | None, timeout: float
    ) -> tuple[int, bytes, str]:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        req = urllib.request.Request(  # noqa: S310 - https only
            url, data=data, headers={**headers, "Accept-Encoding": "gzip"}
        )
        try:
            with opener.open(req, timeout=timeout) as resp:
                body = decode_body(resp.read(), resp.headers.get("Content-Encoding"))
                return int(resp.status), body, str(resp.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as err:
            body = decode_body(err.read(), err.headers.get("Content-Encoding"))
            return int(err.code), body, str(err.headers.get("Content-Type", ""))

    def get(self, url: str, headers: Mapping[str, str], timeout: float) -> tuple[int, bytes, str]:
        return self._open(url, headers, None, timeout)

    def post(
        self, url: str, headers: Mapping[str, str], body: bytes, timeout: float
    ) -> tuple[int, bytes, str]:
        return self._open(url, headers, body, timeout)


class ExportClient(PoliteClient):
    def post_json(self, url: str, payload: Any, headers: Mapping[str, str]) -> Response:
        """POST a JSON body (with extra headers) under get()'s robots, spacing and retries."""
        body = json.dumps(payload).encode()
        hdrs = {**headers, "Content-Type": "application/json", "Accept": "application/json"}
        return self._send(
            url, lambda h: self.post_transport(url, {**h, **hdrs}, body, self.timeout_s)
        )


def default_client() -> ExportClient:
    t = CookieTransport()
    return ExportClient(min_interval_s=3.0, timeout_s=600.0, retries=3, backoff_s=10.0,
                        transport=t.get, post_transport=t.post)  # fmt: skip


class CitrusCivil(Adapter):
    source_id: ClassVar[str] = "fl.citrus.civil"
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "bulk"
    pii_fields: ClassVar[tuple[str, ...]] = PII_FIELDS

    def __init__(self, client: ExportClient | None = None) -> None:
        self.config = load_config()
        self.client = client or default_client()

    def source_row(self) -> Mapping[str, Any]:
        t = self.config.terms
        return {
            "source_id": self.source_id,
            "kind": "court",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": self.config.base_url,
            "terms_url": t["url"],
            "terms_summary": t["summary"],
            "terms_checked_on": t["checked_on"],
            "robots_checked_on": t["robots_checked_on"],
            "cost_model": t["cost_model"],
        }

    # -- fetching -----------------------------------------------------------------------
    def partitions(self) -> Iterator[dict[str, str]]:
        """Months of disposition date, newest first (a build stopped part-way has the most
        recent years)."""
        yesterday = self.client.now().astimezone(UTC).date() - timedelta(days=1)
        for start, end in reversed(list(months(self.config.first_month, yesterday))):
            yield {"from": start.isoformat(), "to": end.isoformat()}

    def _export(self, start: date, end: date) -> bytes:
        base = self.config.base_url
        page = self.client.get(base)
        if page.status != 200:
            raise RuntimeError(f"HTTP {page.status} from {page.url}")
        text = page.content.decode("utf-8", errors="replace")
        snap, token = _SNAPSHOT.search(text), _TOKEN.search(text)
        if snap is None or token is None:
            raise RuntimeError("export form changed: no Livewire snapshot or CSRF token")
        updates = {
            "form.filings_or_dispositions": "DispositionDate",
            "form.time_frame": "custom",
            "form.start_date": start.isoformat(),
            "form.end_date": end.isoformat(),
            "form.selected_court_types": list(self.config.court_types),
            "form.export_information": ["Case", "Party", "Docket"],
        }
        payload = {"_token": token.group(1), "components": [{
            "snapshot": html.unescape(snap.group(1)), "updates": updates,
            "calls": [{"path": "", "method": "submitForm", "params": []}],
        }]}  # fmt: skip
        headers = {"X-Livewire": "1", "X-CSRF-TOKEN": token.group(1)}
        resp = self.client.post_json(base + "livewire/update", payload, headers)
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} from {resp.url}")
        effects = json.loads(resp.content)["components"][0]["effects"]
        download = effects.get("download")
        if not download:
            raise RuntimeError(f"no export for {start}..{end}")
        return base64.b64decode(download["content"])

    def fetch(self, request: FetchRequest) -> Fetched:
        """params: from, to (ISO dates of disposition); limit (fixtures): first N cases and
        their parties and docket rows."""
        p = request.params
        start, end = date.fromisoformat(p["from"]), date.fromisoformat(p["to"])
        if not timedelta(0) <= end - start < timedelta(days=366):
            raise ValueError(f"window {start}..{end}: 1 day to 1 year")
        data = unpack_export(self._export(start, end), self.config.docket_keep)
        if "limit" in p:
            keep = {r.get("UniformCaseNumber") for r in data["cases"][: int(p["limit"])]}
            data = {k: [r for r in v if r.get("UniformCaseNumber") in keep]
                    for k, v in data.items()}  # fmt: skip
        body = canonical_json({"from": start.isoformat(), "to": end.isoformat(), **data})
        url = f"{self.config.base_url}?dispositions={start.isoformat()}..{end.isoformat()}"
        return Fetched(self.source_id, url, self.client.now(), 200, body, "application/json")

    @classmethod
    def scrub_fixture(cls, content: bytes) -> bytes:
        """Pseudonyms for names and addresses. Docket text keeps only words of a fixed legal
        vocabulary (and tokens without letters, such as OR references and dates): any other
        word could be a name and becomes TESTOWNER."""
        from equity.adapters.record import pseudonym  # the recorder imports the registry

        data = json.loads(content)
        for row in data["parties"]:
            for col in PII_FIELDS:
                if row.get(col, "").strip():
                    row[col] = pseudonym("ADDRESS" if col == "ActiveAddress" else col, row[col])
        for row in data["dockets"]:
            row["dockettext"] = " ".join(
                w if not re.search(r"[A-Za-z]", w) or re.fullmatch(r"\(OR\.[\d.]+", w)
                or w.upper().strip(",.()/-:'") in DOCKET_WORDS
                else "TESTOWNER" for w in row.get("dockettext", "").split()
            )  # fmt: skip
        return canonical_json(data)

    def health(self) -> HealthReport:
        """Live: last week's civil dispositions come back as an export with cases."""
        end = self.client.now().astimezone(UTC).date() - timedelta(days=1)
        try:
            f = self.fetch(FetchRequest({"from": (end - timedelta(days=6)).isoformat(),
                                         "to": end.isoformat()}))  # fmt: skip
        except (ValueError, RuntimeError, OSError, KeyError, zipfile.BadZipFile) as exc:
            return HealthReport(self.source_id, False, self.client.now(), repr(exc))
        data = json.loads(f.content)
        ok = bool(data["cases"])
        shape = tuple(sorted(data["cases"][0])) if ok else ()
        return HealthReport(self.source_id, ok, self.client.now(),
                            f"{len(data['cases'])} cases" if ok else "no cases", shape)  # fmt: skip

    # -- normalizing --------------------------------------------------------------------
    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        cfg = self.config
        data = json.loads(fetched.content)
        today = fetched.retrieved_at.astimezone(UTC).date()
        parties: dict[str, list[dict[str, str]]] = defaultdict(list)
        dockets: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in data["parties"]:
            parties[clean_case(r.get("UniformCaseNumber", ""))].append(r)
        for r in data["dockets"]:
            dockets[clean_case(r.get("UniformCaseNumber", ""))].append(r)
        cases: dict[str, dict[str, str]] = {}
        for r in data["cases"]:
            if r.get("UniformCaseNumber"):
                cases.setdefault(clean_case(r["UniformCaseNumber"]), r)
        for norm in sorted(cases):
            yield from self._case(cfg, fetched, today, cases[norm],
                                  parties.get(norm, []), dockets.get(norm, []))  # fmt: skip

    def _case(
        self,
        cfg: CitrusConfig,
        fetched: Fetched,
        today: date,
        case: Mapping[str, str],
        party_rows: list[dict[str, str]],
        docket_rows: list[dict[str, str]],
    ) -> Iterator[NormalizedRow]:
        norm = clean_case(case["UniformCaseNumber"])
        uid = case_uid(norm)
        raw = {"case": dict(case), "parties": party_rows, "dockets": docket_rows}
        ctx = RecordContext(fetched, COUNTY, norm, "civil_case", raw)
        yield ctx.source_record()
        filed = iso_date(case.get("FileDate"))
        filed = filed if filed is not None and filed <= today else None
        disposed = iso_date(case.get("DispositionDate"))
        disposed = disposed if disposed is not None and disposed <= today else None
        closed = disposed if case.get("CaseStatus", "").upper() == "CLOSED" else None
        if closed is not None and filed is not None and closed < filed:
            closed = None
        status = " - ".join(x for x in (case.get("CaseStatus"), case.get("Disposition")) if x)
        yield ctx.fact(
            "court_case", case_uid=uid, court_id=COURT_ID,
            case_number_raw=case.get("CaseNumber") or case["UniformCaseNumber"],
            case_number_norm=norm, case_type=case.get("CourtTypeLong") or None,
            nature_of_suit=" ".join(case.get("CaseType", "").split()) or None,
            filed_on=filed, closed_on=closed, status=status or None,
        )  # fmt: skip
        seen: set[tuple[str, str]] = set()
        for p in sorted(party_rows, key=canonical_json):
            name = party_name(p)
            role = cfg.party_roles.get(p.get("Description", ""), "other")
            if not name or (role, clean(name)) in seen:
                continue
            seen.add((role, clean(name)))
            yield from self._party(ctx, uid, role, name, party_address(p.get("ActiveAddress")))
        found: dict[str, tuple[date, str, str]] = {}
        entries: set[tuple[date, str]] = set()
        for d in docket_rows:
            when = iso_date(d.get("DocketDate"))
            text = " ".join(d.get("dockettext", "").split())
            if when is not None and when <= today and text:
                entries.add((when, text))
        for when, text in sorted(entries):
            ref = or_reference(text)
            yield ctx.fact("docket_entry", case_uid=uid, entry_no=None, entry_date=when,
                           text=text)  # fmt: skip
            jtype = judgment_type(cfg, text)
            if jtype is not None:
                key = f"{when.isoformat()}:{jtype}:" + stable_id(self.source_id, ref or text)[:8]
                found[key] = (when, jtype, text)
        if not found and disposed is not None:
            jtype = cfg.disposition_judgments.get(case.get("Disposition", ""))
            if jtype is not None:
                found[f"{disposed.isoformat()}:{jtype}:disposition"] = (disposed, jtype, "")
        for key in sorted(found):
            when, jtype, _ = found[key]
            yield ctx.fact(
                "judgment", judgment_uid=f"{uid}:{key}", case_uid=uid, entered_on=when,
                principal=None, interest=None, costs=None, rate=None, judgment_type=jtype,
                lien_instrument_uid=None,
            )  # fmt: skip

    def _party(
        self, ctx: RecordContext, uid: str, role: str, name: str, addr: dict[str, Any] | None
    ) -> Iterator[NormalizedRow]:
        if addr is not None:
            yield NormalizedRow("address", addr)
        nc = classify(name)
        party_id = stable_id(self.source_id, uid, role, clean(name))
        yield ctx.fact(
            "party", party_id=party_id, raw_name=name, party_kind=nc.party_kind,
            org_form=nc.org_form, org_name_norm=nc.org_name_norm,
            address_id=None if addr is None else addr["address_id"],
        )  # fmt: skip
        yield ctx.fact("case_party", case_uid=uid, party_id=party_id, role=role)
