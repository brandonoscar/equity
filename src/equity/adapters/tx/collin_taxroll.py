"""Collin County, TX Tax Assessor-Collector delinquent tax roll: delinquent real property tax.

The Tax Assessor publishes the delinquent tax roll free on collincountytx.gov (Tax Assessor >
Property Taxes > Delinquent Tax Roll): one zip, rebuilt with each processing run, holding
every account with delinquent taxes for the past 20 years as of that run. It is the same
collection system's "attorney file" as Tarrant's roll, with its own layout ("Mortgage /
Attorney File Layout", file-layout.pdf on the same page): AMmmddyy.DAT is the master file
(V2, 950 bytes: owner names, mailing address, appraisal-district number, roll code) and
ARmmddyy.DAT the receivable file (V1, 224 bytes: one record per account, year, tax unit and
receivable, with the amount due, the delinquency date and, once the county sues, the suit
number, filing and judgment dates, plus any bankruptcy and installment agreement).

Read here as for Tarrant: receivables with an amount due whose delinquency date is before the
fetch date, summed per account, for real (roll code 001) and commercial (008) accounts;
COURT_ORDER when a tax-suit judgment date is on file, otherwise TAX_LIEN_STATE (Tax Code
32.01). The appraisal-district number is the Collin CAD property id, which is PROP_ID in
tx.statewide.parcels, so each account is linked to its parcel (8,719 real accounts on the
2026-11-21 roll).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

from equity.adapters.base import HealthReport
from equity.adapters.http import PoliteClient
from equity.adapters.tx.tarrant_taxroll import Spec, TarrantTaxRollDelinquent

PAGE = "https://www.collincountytx.gov/tax-assessor/property-taxes"
URL = ("https://www.collincountytx.gov/docs/default-source/tax-assessor/tax-rolls/"
       "delinquent-tax-roll.zip")  # fmt: skip
COUNTY = "48085"
# (name, start, end): 1-based inclusive positions from the layout (master V2, receivable V1)
MASTER: Spec = (("account", 1, 30), ("roll", 34, 36), ("cad_id", 174, 203),
                ("owner1", 335, 384), ("owner2", 385, 434), ("addr1", 435, 484),
                ("addr2", 485, 534), ("city", 535, 584), ("state", 585, 604),
                ("zip", 605, 622))  # fmt: skip
REC: Spec = (("account", 1, 30), ("year", 31, 34), ("unit", 35, 37), ("amount_due", 76, 87),
             ("delinquent_on", 88, 97), ("judgment_on", 108, 117), ("lawsuit", 118, 135),
             ("bankruptcy", 146, 163), ("installment", 191, 191))  # fmt: skip


class CollinTaxRollDelinquent(TarrantTaxRollDelinquent):
    source_id: ClassVar[str] = "tx.collin.tax_roll_delinquent"
    adapter_version: ClassVar[str] = "1"
    county: ClassVar[str] = COUNTY
    creditor: ClassVar[str] = "Collin County Tax Assessor-Collector"
    label: ClassVar[str] = "Collin County"
    master_spec: ClassVar[Spec] = MASTER
    rec_spec: ClassVar[Spec] = REC
    real: ClassVar[tuple[str, ...]] = ("001", "008")
    files: ClassVar[tuple[str, str]] = ("am*.dat", "ar*.dat")
    link_parcel: ClassVar[bool] = True

    def __init__(self, client: PoliteClient | None = None) -> None:
        super().__init__(client or PoliteClient(min_interval_s=2.0, timeout_s=1800.0))

    def source_row(self) -> Mapping[str, Any]:
        return {
            "source_id": self.source_id,
            "kind": "tax",
            "jurisdiction": COUNTY,
            "access_method": "bulk",
            "base_url": URL,
            "terms_url": PAGE,
            "terms_summary": (
                "Collin County Tax Assessor-Collector delinquent tax roll, a free download on "
                "the Property Taxes page, no login; no license or use restriction stated. "
                "collincountytx.gov/robots.txt answers 404 (RFC 9309: no rules, allowed)."
            ),
            "terms_checked_on": "2026-11-27",
            "robots_checked_on": "2026-11-27",
            "cost_model": "free",
        }

    def file_url(self) -> str:
        return URL

    def health(self) -> HealthReport:
        resp = self.client.get(PAGE)
        ok = resp.status == 200 and b"delinquent-tax-roll.zip" in resp.content
        return HealthReport(self.source_id, ok, datetime.now(UTC),
                            f"status={resp.status}; delinquent roll link "
                            f"{'found' if ok else 'missing'}")  # fmt: skip
