"""Generate docs/gaps.md: for every state, which data layers the project has, partly has, or
lacks. Built from the registered adapters and the configs only (no machine state), so it is
regenerated (not edited) as sources are added and checked in CI:

    uv run python -m equity.gaps > docs/gaps.md

Layers, in the order a judgment buyer needs them:
  parcels      - owner of record and value (statewide layer, some counties, or none)
  fields       - which parcel facts the configs map: owner, property address, value,
                 homestead, land use, zoning code
  instruments  - recorded deeds, mortgages, satisfactions, liens (equity behind the lien)
  debts        - judgment, lien, tax and other debt lists by kind (config/debt_kinds.yaml)
  match runs   - the state's match runs (equity.matching.resolve STATES)
  bankruptcy   - federal bankruptcy court feeds
  entities     - Secretary of State business registry (LLC -> people)
  zoning       - zoning district maps (statewide layer, local layers, or none)
  ordinances   - links to zoning ordinances
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from equity.adapters.state_parcels import config_paths, load_config
from equity.config import CONFIG_DIR
from equity.coverage import STATES
from equity.geo import counties

LOCAL_ZONING = Path(__file__).resolve().parents[2] / "config" / "zoning" / "local_layers.json"

# Source-id prefixes for the non-parcel layers. A source counts for its state's two-letter
# prefix; us.* federal court feeds name their district (us.flmb -> FL).
INSTRUMENT_SOURCES = ("ny.nyc.acris.", "pa.philadelphia.rtt", "fl.hillsborough.or",
                      "fl.hernando.or", "fl.putnam.or")  # fmt: skip
ENTITY_SUFFIX = ".business"  # *.sos.business, pa.dos.business, dc.dlcp.business
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
    instruments: tuple[str, ...]
    debts: tuple[tuple[str, int], ...]  # (debt kind, number of sources), by kind
    bankruptcy: tuple[str, ...]
    entities: tuple[str, ...]
    zoning: str
    ordinances: tuple[str, ...]
    runs: tuple[str, ...] = ()


def _state_of(source_id: str) -> str:
    head = source_id.split(".")
    if head[0] == "us" and len(head) > 1:
        return head[1][:2].upper()  # us.flmb.rss -> FL
    return head[0].upper()


def build(
    source_ids: Iterable[str],
    local_zoning: Path = LOCAL_ZONING,
    kinds: dict[str, str] | None = None,
    runs: Iterable[str] = (),
) -> list[StateGaps]:
    ids = sorted(set(source_ids))
    debt_kind = kinds or {}
    run_names = sorted(set(runs))
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
            instruments=tuple(s for s in mine if s.startswith(INSTRUMENT_SOURCES)),
            debts=tuple(sorted(Counter(debt_kind[s] for s in mine if s in debt_kind).items())),
            bankruptcy=tuple(s for s in mine if s.startswith("us.") and s.endswith(".rss")),
            entities=tuple(s for s in mine if s.endswith(ENTITY_SUFFIX)),
            zoning=zoning,
            ordinances=tuple(s for s in mine if s.endswith(ORDINANCE_SUFFIX)),
            runs=tuple(r for r in run_names if r.split("-", 1)[0] == st),
        ))  # fmt: skip
    return out


def _cell(values: tuple[str, ...]) -> str:
    return "<br>".join(f"`{v}`" for v in values) if values else "—"


def _kinds(debts: tuple[tuple[str, int], ...]) -> str:
    return "<br>".join(f"{k} ({n})" for k, n in debts) if debts else "—"


def render(rows: list[StateGaps]) -> str:
    def count(pred: Callable[[StateGaps], object]) -> int:
        return sum(1 for r in rows if pred(r))

    n = len(rows)
    lines = [
        "# Data gaps by state",
        "",
        "Generated by `uv run python -m equity.gaps` from the registered adapters and the "
        "configs (CI checks it is current). Do not edit by hand. Debts are counted by kind from "
        "`config/debt_kinds.yaml` (number of sources). Source research for the missing layers "
        "is in `docs/sources/` and `reports/`.",
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
        f"| Debt lists (any kind) | {count(lambda r: r.debts)} | |",
        f"| Court judgments | {count(lambda r: 'court_judgment' in dict(r.debts))} | |",
        f"| Bankruptcy court feeds | {count(lambda r: r.bankruptcy)} | |",
        f"| Business registry | {count(lambda r: r.entities)} | {count(lambda r: r.entities)} |",
        f"| Match runs | {count(lambda r: r.runs)} | |",
        f"| Zoning maps | {count(lambda r: r.zoning != 'none')} | "
        f"{count(lambda r: r.zoning.startswith('statewide'))} |",
        f"| Ordinance links | {count(lambda r: r.ordinances)} | {count(lambda r: r.ordinances)} |",
        "",
        "Federal sources (FJC civil judgments, EPA judicial cases, SBA charge-offs, HUD REO, "
        "Federal Register notices) are national and read by every match run; they are not "
        "counted per state.",
        "",
        "| State | Parcels | Fields mapped | Deeds / mortgages | Debts by kind | Bankruptcy | "
        "Business registry | Match runs | Zoning maps | Ordinances |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.state} | {r.parcels} | {', '.join(r.fields) or '—'} | "
            f"{_cell(r.instruments)} | {_kinds(r.debts)} | {_cell(r.bankruptcy)} | "
            f"{_cell(r.entities)} | {_cell(r.runs)} | {r.zoning} | {_cell(r.ordinances)} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    from equity.adapters.registry import REGISTRY
    from equity.matching.resolve import STATES as RUNS
    from equity.matching.resolve import debt_kinds

    ids = [c.source_id for c in REGISTRY]
    sys.stdout.write(render(build(ids, kinds=debt_kinds(), runs=RUNS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
