"""CM/ECF public RSS ("Recent Entries") for a district or bankruptcy court.

Free, no login, no PACER charge, robots.txt absent (404, checked 2026-11-15). Each feed
covers roughly the last 24 hours, so history comes from polling daily. Items give case number,
caption, entry type and (bankruptcy) office, chapter and trustee. Not the docket text. Criminal
and magistrate-criminal cases are skipped: they never create the civil judgments or
bankruptcies this system tracks.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Mapping
from datetime import UTC, date
from email.utils import parsedate_to_datetime
from typing import Any, ClassVar

from equity.adapters.base import Adapter, Fetched, FetchRequest, HealthReport, NormalizedRow
from equity.adapters.http import PoliteClient
from equity.adapters.rows import RecordContext
from equity.matching.orgs import classify, clean
from equity.schema.ids import stable_id

_CASE = re.compile(r"^(\d+):(\d{2})-([a-z]{2})-(\d{3,6})(?:-[A-Z0-9]+)*\s*(.*)$")
_BK = re.compile(
    r"Type:\s*(?P<type>\w+)\s+Office:\s*(?P<office>\d+)\s+Chapter:\s*(?P<chapter>\w+)"
    r"(?:\s+Trustee:\s*(?P<trustee>.*?))?\s*\[(?P<entry>[^\]]+)\]\s*\(?\s*(?P<doc>\d+)?",
    re.S,
)
_ENTRY = re.compile(r"\[(?P<entry>[^\]]+)\]\s*\(?\s*(?P<doc>\d+)?")
_TAGS = re.compile(r"<[^>]+>")
_SKIP_TYPES = {"cr", "mj", "po"}  # criminal, magistrate-criminal, petty offense
_VS = re.compile(r"\s+v\.?\s+", re.I)
_CHAPTERS = {"7", "9", "11", "12", "13", "15"}


def _text(el: ET.Element, tag: str) -> str:
    return " ".join((el.findtext(tag) or "").split())


def parse_case(title: str) -> tuple[str, str, str, str, str] | None:
    """'1:25-bk-00040 Doe, Jane' -> (office, yy, type, number, caption)."""
    m = _CASE.match(title)
    if m is None:
        return None
    office, yy, ctype, num, caption = m.groups()
    return office, yy, ctype, num.lstrip("0") or "0", caption.strip()


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
    adapter_version: ClassVar[str] = "1"
    access_method: ClassVar[str] = "feed"

    def __init__(self, client: PoliteClient | None = None) -> None:
        self.client = client or PoliteClient(min_interval_s=5.0)

    @property
    def url(self) -> str:
        return f"https://{self.host}/cgi-bin/rss_outside.pl"

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "bankruptcy" if self.court_id.endswith("b") else "court",
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
            parsed = parse_case(title)
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
            root = ET.fromstring(resp.content)  # noqa: S314
            ok = resp.status == 200 and root.find("channel") is not None
            detail = "ok" if ok else f"status={resp.status}"
        except (ET.ParseError, OSError) as exc:
            ok, detail = False, repr(exc)
        return HealthReport(self.source_id, ok, self.client.now(), detail, ("channel", "item"))

    @staticmethod
    def scrub_fixture(content: bytes) -> bytes:
        """Replace caption and trustee names with pseudonyms (public repo)."""
        from equity.adapters.record import pseudonym

        text = content.decode("utf-8")

        def title(m: re.Match[str]) -> str:
            parsed = parse_case(m.group(2))
            if parsed is None:
                return m.group(0)
            *_, caption = parsed
            fake = " v. ".join(pseudonym("Owner", p) for p in _VS.split(caption)) if caption else ""
            return f"{m.group(1)}{m.group(2)[: len(m.group(2)) - len(caption)]}{fake}{m.group(3)}"

        text = re.sub(r"(<title>)(\d+:\d{2}-[a-z]{2}-\d+[^<]*)(</title>)", title, text)
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
