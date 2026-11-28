"""Denton County, TX Tax Assessor-Collector delinquent tax roll: delinquent real property tax.

The Tax Office publishes the current and delinquent tax rolls free and weekly, as Texas Tax
Code 1.10 requires (dentoncounty.gov, Tax Roll Data - Current & Delinquent; the files are
served from apps.dentoncounty.gov/website/taxfiles/). Each roll is a zip of the collection
system's attorney files, in the same layout as Collin's (File Layout Guide on the same page):
AMmmddyy.DAT, the master file (950 bytes), and ARmmddyy.DAT, the receivables (224 bytes); the
full roll's members are MM/MR instead. The listing names the two zips only by their run time,
so the first member name of each is read with a small range request and the one starting 'AM'
is the delinquent roll.

Read as for Collin: past-due receivables summed per account, real property (roll 001; 5,890
accounts on the 2026-11-25 roll; 002 personal property, 003 mineral interests and others are
not read here). Denton's own accounts are '295693DEN': without the 'DEN' suffix the number is
the Denton CAD property id, PROP_ID in tx.statewide.parcels, so those accounts are linked to
their parcel; accounts another county's appraisal district keys ('767116WIS') are not.
"""

from __future__ import annotations

import re
import struct
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

from equity.adapters.base import HealthReport
from equity.adapters.http import RangeClient
from equity.adapters.tx.collin_taxroll import MASTER, REC, CollinTaxRollDelinquent
from equity.adapters.tx.tarrant_taxroll import Spec

PAGE = "https://www.dentoncounty.gov/890/Tax-Roll-Data-Current-Delinquent"
LISTING = "https://apps.dentoncounty.gov/website/taxfiles/"
LINK = re.compile(r'href="(Download\.ashx\?file=TaxRoll_[^"]+\.zip)"', re.I)
COUNTY = "48121"
OWN_ACCOUNT = re.compile(r"^(\d+)DEN$")


def first_member(head: bytes) -> str | None:
    """The file name in a zip's first local file header ('AM112526.DAT'), from its first
    bytes; None when they are not a zip header."""
    if len(head) < 30 or head[:4] != b"PK\x03\x04":
        return None
    n = struct.unpack("<H", head[26:28])[0]
    return head[30 : 30 + n].decode("latin-1") if len(head) >= 30 + n else None


class DentonTaxRollDelinquent(CollinTaxRollDelinquent):
    source_id: ClassVar[str] = "tx.denton.tax_roll_delinquent"
    adapter_version: ClassVar[str] = "1"
    county: ClassVar[str] = COUNTY
    creditor: ClassVar[str] = "Denton County Tax Assessor-Collector"
    label: ClassVar[str] = "Denton County"
    master_spec: ClassVar[Spec] = MASTER
    rec_spec: ClassVar[Spec] = REC
    real: ClassVar[tuple[str, ...]] = ("001",)
    files: ClassVar[tuple[str, str]] = ("am*.dat", "ar*.dat")
    link_parcel: ClassVar[bool] = True

    def __init__(self, client: RangeClient | None = None) -> None:
        super().__init__(client or RangeClient(min_interval_s=2.0, timeout_s=1800.0))

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "tax",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": LISTING,
            "terms_url": PAGE,
            "terms_summary": (
                "Denton County Tax Assessor-Collector current and delinquent tax roll files, "
                "free weekly downloads under Tax Code 1.10, no login; no license or use "
                "restriction stated. apps.dentoncounty.gov/robots.txt disallows only Amazonbot; "
                "dentoncounty.gov/robots.txt only admin and search paths."
            ),
            "terms_checked_on": "2026-11-28",
            "robots_checked_on": "2026-11-28",
            "cost_model": "free",
        }

    def file_url(self) -> str:
        resp = self.client.get(LISTING)
        if resp.status != 200:
            raise RuntimeError(f"{self.source_id}: HTTP {resp.status} for {LISTING}")
        links: list[str] = LINK.findall(resp.content.decode("utf-8", "replace"))
        get_range = getattr(self.client, "get_range", None)  # a RangeClient
        if get_range is None:
            raise RuntimeError(f"{self.source_id}: needs a client with ranged reads")
        for link in links:
            url = LISTING + link
            head = get_range(url, 0, 99)
            name = first_member(head.content[:100]) if head.status in (200, 206) else None
            if name and name.upper().startswith("AM"):
                return url
        raise RuntimeError(f"{self.source_id}: no delinquent (AM) roll among {len(links)} files")

    def parcel_key(self, row: Mapping[str, Any]) -> str | None:
        """'295693DEN' -> '295693' (the Denton CAD PROP_ID); other counties' accounts: None."""
        m = OWN_ACCOUNT.match(str(row.get("account") or "").strip())
        return m.group(1) if m and self.link_parcel else None

    def health(self) -> HealthReport:
        try:
            url = self.file_url()
        except RuntimeError as exc:
            return HealthReport(self.source_id, False, datetime.now(UTC), repr(exc))
        return HealthReport(self.source_id, True, datetime.now(UTC), f"delinquent roll {url}")


class DentonPersonalPropertyDelinquent(DentonTaxRollDelinquent):
    """The same roll's business personal property accounts (roll 002: 7,155 on the 2026-11-25
    roll), owed by the business, with no parcel (Tax Code 32.01 lien on the personal
    property)."""

    source_id: ClassVar[str] = "tx.denton.personal_property_delinquent"
    adapter_version: ClassVar[str] = "1"
    real: ClassVar[tuple[str, ...]] = ("002",)
    link_parcel: ClassVar[bool] = False
    tax_label: ClassVar[str] = "business personal property tax"


class DentonMineralTaxDelinquent(DentonTaxRollDelinquent):
    """The same roll's mineral interest accounts (roll 003: 23,019 with past-due tax, $0.78M,
    132 with a tax-suit judgment on the 2026-11-25 roll), owed by the interest's owner; no
    parcel (Denton's mineral interests are not in a parcel source yet)."""

    source_id: ClassVar[str] = "tx.denton.mineral_tax_delinquent"
    adapter_version: ClassVar[str] = "1"
    real: ClassVar[tuple[str, ...]] = ("003",)
    link_parcel: ClassVar[bool] = False
    tax_label: ClassVar[str] = "mineral interest tax"
