"""Deed and sales files whose dates or parcel ids need a small rewrite before they read like a
config/liens source: one YAML per source in config/deeds/, with every config/liens key (see
equity.adapters.liens) plus:

  date_format     {field: ymd | mdy}: ymd is a yyyymmdd number or text (20150121), mdy a
                  'M/D/YYYY[ h:mm:ss AM]' text; the field is rewritten to an ISO date before
                  the row is read. When the date_field has a format the year windows are
                  queried on the raw value: ymd as numbers (field >= 20150101 AND field <
                  20160101, arcgis and socrata; quoted when date_is_text is true), mdy as
                  text (field LIKE '%/2015 %' OR field LIKE '%/2015', socrata only;
                  partition must be year)
  rewrite         {field: {pattern, replace}}: a regex substitution on the field's text
                  (re.sub, applied once), e.g. a SPAN published without its dashes
                  ('78625010932' -> '786-250-10932') so the id matches the owner layer

Rows are otherwise exactly LienAdapter rows: one instrument per uid (grantor and grantee as
parties, the price as consideration), linked to the parcel the row names.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from equity.adapters.liens import LienAdapter, LienConfig, LienConfigError, load_lien_config
from equity.adapters.liens import us_date as _us_date
from equity.config import CONFIG_DIR

DEEDS_DIR = CONFIG_DIR / "deeds"
DATE_FORMATS = ("ymd", "mdy")
YMD = re.compile(r"^\s*(\d{4})(\d{2})(\d{2})(?:\.0+)?\s*$")


def ymd_date(value: Any) -> str | None:
    """20150121 (number or text) -> '2015-01-21'; anything else -> None."""
    if value is None or isinstance(value, bool):
        return None
    m = YMD.match(str(value))
    if not m or not ("01" <= m.group(2) <= "12" and "01" <= m.group(3) <= "31"):
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def mdy_date(value: Any) -> str | None:
    """'7/2/2012 12:00:00 AM' or '7/2/2012' -> '2012-07-02'; anything else -> None."""
    if value is None:
        return None
    return _us_date(str(value).strip().split(" ")[0])


def load_deed_config(path: Path) -> LienConfig:
    cfg = load_lien_config(path)
    formats = cfg.get("date_format") or {}
    bad = {k: v for k, v in formats.items() if v not in DATE_FORMATS}
    if bad:
        raise LienConfigError(f"{path.name}: date_format must be one of {DATE_FORMATS}: {bad}")
    windowed = (cfg.get("api", "socrata"), cfg.get("partition", "year")) == ("socrata", "year")
    if formats.get(cfg["date_field"]) == "mdy" and not windowed:
        raise LienConfigError(f"{path.name}: mdy date windows need api socrata, year")
    for field, spec in (cfg.get("rewrite") or {}).items():
        if not isinstance(spec, Mapping) or "pattern" not in spec or "replace" not in spec:
            raise LienConfigError(f"{path.name}: rewrite {field} needs pattern and replace")
        re.compile(str(spec["pattern"]))
    return cfg


class DeedAdapter(LienAdapter):
    """A LienAdapter whose rows get the config's date_format and rewrite applied first."""

    def where(self, params: Mapping[str, str]) -> str:
        f = self.config["date_field"]
        fmt = (self.config.get("date_format") or {}).get(f)
        if fmt is None or "from" not in params:
            return super().where(params)
        clauses = [f"({self.config['where']})"] if self.config.get("where") else []
        if fmt == "ymd":
            lo, hi = (str(int(params[k].replace("-", ""))) for k in ("from", "to"))
            if self.config.get("date_is_text"):  # yyyymmdd text compares as text
                lo, hi = f"'{lo}'", f"'{hi}'"
            clauses.append(f"{f} >= {lo} AND {f} < {hi}")
        else:  # mdy text: one calendar year per partition
            year = params["from"][:4]
            clauses.append(f"({f} LIKE '%/{year} %' OR {f} LIKE '%/{year}')")
        return " AND ".join(clauses)

    def _derive(self, row: Mapping[str, Any]) -> Mapping[str, Any]:
        out = dict(row)
        for field, fmt in (self.config.get("date_format") or {}).items():
            out[field] = ymd_date(row.get(field)) if fmt == "ymd" else mdy_date(row.get(field))
        for field, spec in (self.config.get("rewrite") or {}).items():
            value = row.get(field)
            if value is not None:
                text = str(value).strip()
                out[field] = re.sub(str(spec["pattern"]), str(spec["replace"]), text, count=1)
        return super()._derive(out)


def deed_adapter_for(cfg: LienConfig) -> type[DeedAdapter]:
    sid = cfg["source_id"]
    return type("Deeds_" + sid.replace(".", "_"), (DeedAdapter,),
                {"config": cfg, "source_id": sid, "pii_fields": cfg.pii_fields,
                 "__module__": __name__})  # fmt: skip


def all_deed_adapters(directory: Path = DEEDS_DIR) -> list[type[DeedAdapter]]:
    return [deed_adapter_for(load_deed_config(p)) for p in sorted(directory.glob("*.yaml"))]
