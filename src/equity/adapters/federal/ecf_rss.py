"""CM/ECF public RSS ("Recent Entries") for a district or bankruptcy court.

Free, no login, no PACER charge, robots.txt absent (404, checked 2026-11-15). Each feed
covers roughly the last 24 hours, so history comes from polling daily. Items give case number,
caption, entry type and (bankruptcy) office, chapter and trustee. Not the docket text. Criminal
and magistrate-criminal cases are skipped: they never create the civil judgments or
bankruptcies this system tracks.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Mapping
from datetime import UTC, date
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

# Case-number layouts seen in CM/ECF feeds:
#   1:25-bk-00040 Caption       office:yy-type-number (district style)
#   26-31038- Caption           yy-number-[judge initials] (many bankruptcy courts)
#   26-55830-pwb Caption / 26-23147 Caption / 26-35279-mvl7 Caption
_CASE = re.compile(r"^(?:(\d+):)?(\d{2})-(?:([a-z]{2})-)?(\d{3,6})(?:-[A-Za-z0-9]*)*(?:\s+(.*))?$")
# Western New York (nywb) writes office-year-number with dashes and no type: "2-26-20862- Name".
_CASE_DASHED = re.compile(r"^(\d)-(\d{2})-(\d{3,6})-?(?:\s+(.*))?$")
_BK = re.compile(
    r"Type:\s*(?P<type>\w+)\s+Office:\s*(?P<office>\d+)\s+Chapter:\s*(?P<chapter>\w+)"
    r"(?:\s+Trustee:\s*(?P<trustee>.*?))?\s*\[(?P<entry>[^\]]+)\]\s*\(?\s*(?P<doc>\d+)?",
    re.S,
)
_ENTRY = re.compile(r"\[(?P<entry>[^\]]+)\]\s*\(?\s*(?P<doc>\d+)?")
_TAGS = re.compile(r"<[^>]+>")
# "Voluntary Petition (Chapter 7)", "Voluntary Petition Ch 13", "Involuntary Petition ...";
# not a motion or certificate about one.
_PETITION = re.compile(r"^\s*(Voluntary|Involuntary)\s+Petition", re.I)
_SKIP_TYPES = {"cr", "mj", "po"}  # criminal, magistrate-criminal, petty offense
_VS = re.compile(r"\s+v\.?\s+", re.I)
_CHAPTERS = {"7", "9", "11", "12", "13", "15"}


def _text(el: ET.Element, tag: str) -> str:
    return " ".join((el.findtext(tag) or "").split())


def parse_case(title: str, bankruptcy_court: bool = False) -> tuple[str, str, str, str, str] | None:
    """Case number and caption -> (office, yy, type, number, caption).

    When the number carries no type (bankruptcy-court style), the type is decided by a fixed
    rule: in a bankruptcy court a caption of the form "A v. B" is an adversary proceeding
    ("ap"), anything else is the bankruptcy case ("bk"). Outside bankruptcy courts an untyped
    number is "cv"."""
    text = " ".join(title.split())
    m = _CASE.match(text)
    if m is not None:
        office, yy, ctype, num, caption = m.groups()
    else:
        d = _CASE_DASHED.match(text)
        if d is None:
            return None
        office, yy, num, caption = d.groups()
        ctype = None
    caption = (caption or "").strip()
    if ctype is None:
        ctype = ("ap" if _VS.search(caption) else "bk") if bankruptcy_court else "cv"
    return office or "0", yy, ctype, num.lstrip("0") or "0", caption


def caption_parties(ctype: str, caption: str) -> list[tuple[str, str]]:
    """Deterministic caption split. bk: all names are debtors; civil: 'A v. B'."""
    if not caption:
        return []
    if ctype == "bk":
        names = [n.strip() for n in re.split(r"\s+and\s+|;", caption) if n.strip()]
        return [(n, "debtor") for n in names]
    parts = _VS.split(caption, maxsplit=1)
    if len(parts) == 2:
        return [(parts[0].strip(), "plaintiff"), (parts[1].strip(), "defendant")]
    return [(caption, "other")]


class ECFRecentEntries(Adapter):
    source_id: ClassVar[str]
    court_id: ClassVar[str]
    host: ClassVar[str]
    jurisdiction: ClassVar[str] = "54"
    adapter_version: ClassVar[str] = "2"  # 2: bankruptcy rows from petition entries
    access_method: ClassVar[str] = "feed"
    # The feed holds only the last day or so of entries: each poll is a new lake part, and
    # rows already stored are dropped from it (equity.lake.drop_known, equity.refresh).
    append_polls: ClassVar[bool] = True

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=5.0)

    @property
    def url(self) -> str:
        return f"https://{self.host}/cgi-bin/rss_outside.pl"

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "bankruptcy" if self.court_id.endswith("b") else "court",  # e.g. flmb, njb
            "jurisdiction": self.court_id,
            "access_method": "feed",
            "base_url": self.url,
            "terms_url": "https://pacer.uscourts.gov/policy-procedures",
            "terms_summary": (
                "Public CM/ECF RSS, no login or fee; PACER terms bar fee-avoiding harvesting "
                "of PACER itself; this feed is published for public consumption"
            ),
            "terms_checked_on": date(2026, 11, 15),
            "robots_checked_on": date(2026, 11, 15),
            "cost_model": "free",
        }

    def fetch(self, request: FetchRequest) -> Fetched:
        resp = self.client.get(self.url)
        if resp.status != 200:  # a court's error page is HTML, not an empty feed
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status} from {self.url}")
        return Fetched(self.source_id, resp.url, resp.retrieved_at, resp.status, resp.content,
                       resp.content_type)  # fmt: skip

    def normalize(self, fetched: Fetched) -> Iterator[NormalizedRow]:
        root = ET.fromstring(fetched.content)  # noqa: S314 - feed from a federal court host
        channel = root.find("channel")
        if channel is None:
            raise ValueError("RSS has no channel")
        seen_cases: set[str] = set()
        seen_keys: dict[str, int] = {}
        for item in channel.findall("item"):
            title = _text(item, "title")
            # Descriptions carry escaped HTML (the document number is a link): strip tags.
            desc = " ".join(_TAGS.sub(" ", item.findtext("description") or "").split())
            parsed = parse_case(title, bankruptcy_court=self.court_id.endswith("b"))
            pub = _text(item, "pubDate")
            if parsed is None or not pub:
                continue
            office, yy, ctype, num, caption = parsed
            if ctype in _SKIP_TYPES:
                continue
            entry_at = parsedate_to_datetime(pub).astimezone(UTC)
            case_norm = f"{office}:{yy}-{ctype}-{int(num):05d}"
            case_uid = f"{self.court_id}:{case_norm}"
            bk = _BK.search(desc)
            em = bk or _ENTRY.search(desc)
            entry_type = em.group("entry").strip() if em else desc[:200]
            doc_no = em.group("doc") if em and em.group("doc") else None
            key = f"{case_norm}@{entry_at.isoformat()}#{doc_no or entry_type}"
            seen_keys[key] = seen_keys.get(key, 0) + 1
            if seen_keys[key] > 1:  # identical items in one feed: keep each, keyed by order
                key = f"{key}~{seen_keys[key]}"
            ctx = RecordContext(fetched, self.court_id, key, "rss_item",
                                {"title": title, "description": desc, "pubDate": pub})  # fmt: skip
            yield ctx.source_record()
            chapter = bk.group("chapter") if bk else None
            if case_uid not in seen_cases:
                seen_cases.add(case_uid)
                yield ctx.fact(
                    "court_case",
                    case_uid=case_uid,
                    court_id=self.court_id,
                    case_number_raw=title.split(" ", 1)[0],
                    case_number_norm=case_norm,
                    case_type=ctype,
                    nature_of_suit=f"chapter {chapter}" if chapter in _CHAPTERS else None,
                )
                for seq, (name, role) in enumerate(caption_parties(ctype, caption), start=1):
                    pid = stable_id(self.source_id, case_uid, role, str(seq), clean(name))
                    nc = classify(name)
                    yield ctx.fact("party", party_id=pid, raw_name=name,
                                   party_kind=nc.party_kind, org_form=nc.org_form,
                                   org_name_norm=nc.org_name_norm)  # fmt: skip
                    yield ctx.fact("case_party", case_uid=case_uid, party_id=pid, role=role)
                trustee = (bk.group("trustee") or "").strip() if bk else ""
                if trustee:
                    pid = stable_id(self.source_id, case_uid, "trustee", clean(trustee))
                    yield ctx.fact("party", party_id=pid, raw_name=trustee,
                                   party_kind="unknown")  # fmt: skip
                    yield ctx.fact("case_party", case_uid=case_uid, party_id=pid, role="trustee")
            if bk and chapter in _CHAPTERS and _PETITION.search(entry_type):
                # The petition entry dates the case; later entries only show it is open.
                yield ctx.fact(
                    "bankruptcy", case_uid=case_uid, chapter=chapter, petition_on=entry_at.date(),
                    discharge_on=None, dismissed_on=None, converted_on=None,
                    trustee_party_id=None, asset_case=None,
                )  # fmt: skip
            yield ctx.fact(
                "docket_entry",
                case_uid=case_uid,
                entry_no=None if doc_no is None else int(doc_no),
                entry_date=entry_at.date(),
                text=f"[{entry_type}]",
            )

    def health(self) -> HealthReport:
        try:
            resp = self.client.get(self.url)
            if resp.status != 200:  # report the HTTP status, not a parse error on its page
                return HealthReport(self.source_id, False, self.client.now(),
                                    f"status={resp.status}", ("channel", "item"))  # fmt: skip
            root = ET.fromstring(resp.content)  # noqa: S314
            ok = root.find("channel") is not None
            detail = "ok" if ok else "no channel"
        except (ET.ParseError, OSError) as exc:
            ok, detail = False, repr(exc)
        return HealthReport(self.source_id, ok, self.client.now(), detail, ("channel", "item"))

    @staticmethod
    def scrub_fixture(content: bytes) -> bytes:
        """Replace caption and trustee names with pseudonyms (public repo). Every <title> that
        parses as a case gets its caption replaced; titles that don't parse are left as they
        are and must not contain names (tests/test_fixture_privacy.py checks every item)."""
        from equity.adapters.record import pseudonym

        text = content.decode("utf-8")

        def title(m: re.Match[str]) -> str:
            raw = html.unescape(m.group(2))
            parsed = parse_case(raw, bankruptcy_court=True)
            if parsed is None:
                return m.group(0)
            caption = parsed[-1]
            number = " ".join(raw.split())[: len(" ".join(raw.split())) - len(caption)].strip()
            fake = " v. ".join(pseudonym("Owner", p) for p in _VS.split(caption)) if caption else ""
            return f"{m.group(1)}{html.escape(number)} {fake}{m.group(3)}".replace(" </", "</")

        text = re.sub(r"(<title>)([^<]*)(</title>)", title, text)
        text = re.sub(
            r"(Trustee:\s*)([^\[<]+?)(\s*\[)",
            lambda m: m.group(1) + pseudonym("Owner", m.group(2)) + m.group(3),
            text,
        )
        return text.encode("utf-8")


class NDWVDistrictRSS(ECFRecentEntries):
    source_id: ClassVar[str] = "us.wvnd.rss"
    court_id: ClassVar[str] = "wvnd"
    host: ClassVar[str] = "ecf.wvnd.uscourts.gov"


class NDWVBankruptcyRSS(ECFRecentEntries):
    source_id: ClassVar[str] = "us.wvnb.rss"
    court_id: ClassVar[str] = "wvnb"
    host: ClassVar[str] = "ecf.wvnb.uscourts.gov"


def court_adapters(config_dir: Path | None = None) -> list[type[ECFRecentEntries]]:
    """Adapter classes for the courts in config/courts.yaml `enabled` (source_id us.<id>.rss).

    A court is enabled once its host is reachable and a scrubbed feed fixture is recorded;
    `planned` lists the rest.
    """
    import yaml

    from equity.config import CONFIG_DIR

    data = yaml.safe_load(((config_dir or CONFIG_DIR) / "courts.yaml").read_text())
    planned = {cid: st for st, ids in data["courts"].items() for cid in ids}
    out: list[type[ECFRecentEntries]] = []
    for cid in sorted(data.get("enabled") or []):
        if cid not in planned:
            raise ValueError(f"enabled court {cid!r} is not listed under courts")
        attrs = {
            "source_id": f"us.{cid}.rss",
            "court_id": cid,
            "host": f"ecf.{cid}.uscourts.gov",
            "jurisdiction": planned[cid],
            "__module__": __name__,
        }
        out.append(type(f"ECF_{cid}", (ECFRecentEntries,), attrs))
    return out
