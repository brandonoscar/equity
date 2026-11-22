"""Generate docs/gaps.md: for every state, which data layers the project has, partly has, or
lacks. Built from the registered adapters, the configs and the local lake state, so it is
regenerated (not edited) as sources are added:

    uv run python -m equity.gaps > docs/gaps.md

Layers, in the order a judgment buyer needs them:
  parcels      - owner of record and value (statewide layer, some counties, or none)
  fields       - which parcel facts the configs map: owner, property address, value,
                 homestead, land use, zoning code
  instruments  - recorded deeds, mortgages, satisfactions, liens (equity behind the lien)
  judgments    - state-court civil cases / judgments
  bankruptcy   - federal bankruptcy court feeds
  entities     - Secretary of State business registry (LLC -> people)
  zoning       - zoning district maps (statewide layer, local layers, or none)
  ordinances   - links to zoning ordinances
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from equity.adapters.state_parcels import config_paths, load_config
from equity.config import CONFIG_DIR
from equity.coverage import STATES
from equity.geo import counties

LAKE = Path("data/lake")
LOCAL_ZONING = Path(__file__).resolve().parents[2] / "config" / "zoning" / "local_layers.json"

# Source-id prefixes for the non-parcel layers. A source counts for its state's two-letter
# prefix; us.* federal court feeds name their district (us.flmb -> FL).
INSTRUMENT_SOURCES = ("ny.nyc.acris.", "pa.philadelphia.rtt", "fl.hillsborough.or")
JUDGMENT_SOURCES = ("fl.hillsborough.civil.", "fl.hillsborough.garnishment", "ny.nyc.acris.real")
ENTITY_SUFFIX = ".sos.business"
ORDINANCE_SUFFIX = ".code_links"
FIELD_FLAGS = (
    ("owner", ("owner1",)),
    ("address", ("situs_line1", "situs_full")),
    ("value", ("total_value", "assessed_value", "land_value")),
    ("homestead", ("homestead",)),
    ("land use", ("land_use_code", "land_use_desc")),
    ("zoning", ("zoning",)),
)


@dataclass(frozen=True)
class StateGaps:
    state: str
    parcels: str
    fields: tuple[str, ...]
    loaded: int
    instruments: tuple[str, ...]
    judgments: tuple[str, ...]
    bankruptcy: tuple[str, ...]
    entities: tuple[str, ...]
    zoning: str
    ordinances: tuple[str, ...]


def _state_of(source_id: str) -> str:
    head = source_id.split(".")
    if head[0] == "us" and len(head) > 1:
        return head[1][:2].upper()  # us.flmb.rss -> FL
    return head[0].upper()


def _loaded_parcels(lake: Path, source_ids: Iterable[str]) -> int:
    total = 0
    for sid in source_ids:
        counts = lake / sid / "_counts.json"
        if counts.exists():
            total += int(json.loads(counts.read_text()).get("parcel", 0))
    return total


def build(
    source_ids: Iterable[str], lake: Path = LAKE, local_zoning: Path = LOCAL_ZONING
) -> list[StateGaps]:
    ids = sorted(set(source_ids))
    by_state: dict[str, list[str]] = defaultdict(list)
    for sid in ids:
        by_state[_state_of(sid)].append(sid)
    paths = config_paths() + sorted((CONFIG_DIR / "bulk").glob("*.yaml"))
    configs = {c.source_id: c for c in (load_config(p) for p in paths)}
    county_total: dict[str, int] = defaultdict(int)
    for c in counties():
        county_total[c.state] += 1
    local: dict[str, int] = defaultdict(int)
    if local_zoning.exists():
        for e in json.loads(local_zoning.read_text()).get("layers", []):
            local[e["state_fips"]] += 1
    fips_of = {c.state: c.state_fips for c in counties()}
    out = []
    for st in STATES:
        mine = by_state.get(st, [])
        parcel_ids = [s for s in mine if s.endswith(".parcels")]
        statewide = [s for s in parcel_ids if ".statewide." in s]
        if st == "TX" and parcel_ids:
            statewide = parcel_ids
        if statewide:
            parcels = "statewide"
        elif parcel_ids:
            parcels = f"{len(parcel_ids)} of {county_total[st]} counties"
        else:
            parcels = "none"
        mapped: set[str] = set()
        for sid in parcel_ids:
            cfg = configs.get(sid)
            names = set(cfg.fields) if cfg else {"owner1", "total_value"}  # hand-written: WV, TX
            mapped |= {flag for flag, keys in FIELD_FLAGS if names & set(keys)}
        zone_state = [s for s in mine if s.endswith(".zoning")]
        n_local = local.get(fips_of.get(st, ""), 0)
        if zone_state:
            zoning = "statewide" + (f" + {n_local} local" if n_local else "")
        elif n_local:
            zoning = f"{n_local} local layers"
        else:
            zoning = "none"
        out.append(StateGaps(
            state=st,
            parcels=parcels,
            fields=tuple(f for f, _ in FIELD_FLAGS if f in mapped),
            loaded=_loaded_parcels(lake, parcel_ids),
            instruments=tuple(s for s in mine if s.startswith(INSTRUMENT_SOURCES)),
            judgments=tuple(s for s in mine if s.startswith(JUDGMENT_SOURCES)),
            bankruptcy=tuple(s for s in mine if s.startswith("us.") and s.endswith(".rss")),
            entities=tuple(s for s in mine if s.endswith(ENTITY_SUFFIX)),
            zoning=zoning,
            ordinances=tuple(s for s in mine if s.endswith(ORDINANCE_SUFFIX)),
        ))  # fmt: skip
    return out


def _cell(values: tuple[str, ...]) -> str:
    return "<br>".join(f"`{v}`" for v in values) if values else "—"


def render(rows: list[StateGaps]) -> str:
    def count(pred: Callable[[StateGaps], object]) -> int:
        return sum(1 for r in rows if pred(r))

    n = len(rows)
    lines = [
        "# Data gaps by state",
        "",
        "Generated by `uv run python -m equity.gaps` from the registered adapters, the configs "
        "and the local lake state. Do not edit by hand. Source research for the missing layers "
        "is in `docs/sources/`.",
        "",
        "| Layer | States with any | Statewide (for owners: statewide with owners) |",
        "|---|---|---|",
        f"| Parcels | {count(lambda r: r.parcels != 'none')} of {n} | "
        f"{count(lambda r: r.parcels == 'statewide')} |",
        f"| Parcel owner names mapped | {count(lambda r: 'owner' in r.fields)} | "
        f"{count(lambda r: r.parcels == 'statewide' and 'owner' in r.fields)} |",
        f"| Property address mapped | {count(lambda r: 'address' in r.fields)} | |",
        f"| Homestead mapped | {count(lambda r: 'homestead' in r.fields)} | |",
        f"| Land use mapped | {count(lambda r: 'land use' in r.fields)} | |",
        f"| Recorded deeds / mortgages | {count(lambda r: r.instruments)} | 0 |",
        f"| State-court judgments | {count(lambda r: r.judgments)} | 0 |",
        f"| Bankruptcy court feeds | {count(lambda r: r.bankruptcy)} | |",
        f"| Business registry | {count(lambda r: r.entities)} | {count(lambda r: r.entities)} |",
        f"| Zoning maps | {count(lambda r: r.zoning != 'none')} | "
        f"{count(lambda r: r.zoning.startswith('statewide'))} |",
        f"| Ordinance links | {count(lambda r: r.ordinances)} | {count(lambda r: r.ordinances)} |",
        "",
        "Loaded parcels count only finished sources in this machine's lake state.",
        "",
        "| State | Parcels | Loaded | Fields mapped | Deeds / mortgages | Judgments | "
        "Bankruptcy | Business registry | Zoning maps | Ordinances |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.state} | {r.parcels} | {r.loaded:,} | {', '.join(r.fields) or '—'} | "
            f"{_cell(r.instruments)} | {_cell(r.judgments)} | {_cell(r.bankruptcy)} | "
            f"{_cell(r.entities)} | {r.zoning} | {_cell(r.ordinances)} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    from equity.adapters.registry import REGISTRY

    sys.stdout.write(render(build(c.source_id for c in REGISTRY)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
