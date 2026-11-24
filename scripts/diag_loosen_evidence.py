"""Diagnostic (not a rule change): Phase 4 v2 with looser Phase 2 evidence-sufficiency gates.

The Phase 2 gates are re-applied in memory to the stored `research/leader/origin=*/evidence.parquet` (every gate input
is a column there) with `gate_evidence` at 8 completed round trips (was 20) and `gate_history` at 45 snapshot days
(was 90), then `selection_v2.run` reads those re-gated tables instead of the published ones and writes to
research/audit/diag_evidence_<variant>/. Replays, statistics, tau2 and categories do not depend on the gates, so only
S2 and what follows change. Published outputs (research/leader, research/selection_v2) are not touched.

Variants:
- `asked`: 8 trips, 45 snapshot days, usable return days unchanged at 60;
- `scaled`: 8 trips, 45 snapshot days, usable days halved like the snapshot days (60 -> 30).
Usage: uv run python scripts/diag_loosen_evidence.py [variant ...]
"""

import sys

sys.path.insert(0, "src")
import copy
from pathlib import Path

import polars as pl

from arkstream import leader_risk as lk
from arkstream import selection_v2 as V2
from arkstream.config import load_context

C = pl.col
OUT = Path("research/audit")
ORIGINS = ["2025-10-08", "2025-10-22", "2025-11-05", "2025-11-19", "2025-12-03"]
VARIANTS = {"asked": {"min_round_trips": 8, "min_snapshot_days": 45, "min_usable_days": 60},
            "scaled": {"min_round_trips": 8, "min_snapshot_days": 45, "min_usable_days": 30}}


def regated(ctx, overrides: dict) -> dict[str, pl.DataFrame]:
    rules = copy.deepcopy(ctx.raw["leader"])
    rules["gates"].update(overrides)
    out = {}
    for o in ORIGINS:
        p = ctx.root / "research/leader" / f"origin={o}" / "evidence.parquet"
        out[str(p.resolve())] = lk.apply_gates(pl.read_parquet(p), rules)
    return out


def run_variant(ctx, name: str) -> Path:
    tables = regated(ctx, VARIANTS[name])
    real = pl.read_parquet

    def read_parquet(source, *args, **kwargs):
        key = str(Path(source).resolve()) if isinstance(source, (str, Path)) else None
        if key in tables and not args and not kwargs.get("columns"):
            return tables[key]
        if key in tables and kwargs.get("columns"):
            return tables[key].select(kwargs["columns"])
        return real(source, *args, **kwargs)

    out = OUT / f"diag_evidence_{name}"
    pl.read_parquet = read_parquet
    try:
        V2.run(ctx, out=out, verbose=False)
    finally:
        pl.read_parquet = real
    pl.concat([t.select("trader", "all_gates_pass", "gates_failed", "rt_closed", "snapshot_days", "usable_days")
               .with_columns(origin=pl.lit(o)) for o, t in zip(ORIGINS, tables.values(), strict=True)]
              ).write_csv(out / "phase2_regated.csv")
    return out


def main() -> None:
    ctx = load_context()
    for name in sys.argv[1:] or list(VARIANTS):
        print(name, run_variant(ctx, name), flush=True)


if __name__ == "__main__":
    main()
