"""Phase 4 v2 replays on the current A/B universes (ADRs 0073, 0076).

`run_allpriced` writes `research/replay_allpriced/`: the frozen full stack (`*_sqrt_cap_part_ns_sweep_frozen`, every
scenario, the ADR-0063 benchmark, ADR-0055 stress coverage and capture) on every coin passing the price check, built
exactly as `research/replay_frozen/` was (shared inputs from `replay.run(simulate=False)`), but on the universes after
ADR-0066. It supplies the T2-T5 inputs and the "all priced coins" copy of ADR-0073 item 5.

`run_tradable` writes `research/replay_tradable/`: the same stack where each wallet copies only its tradable set
(`selection_v2_coins`, leave-one-wallet-out T4). The cap plan is the all-priced one (scale solved on the whole priced
book); legs outside the wallet's set are `not_tradable` (never submitted, reserved or filled; the benchmark skips
them too). The shared inputs that do not depend on the set are copied from the all-priced tree. The holdout window is
never computed.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import polars as pl

from arkstream import drift
from arkstream.replay_frozen import MODEL

C = pl.col
SHARED = ("valuation_marks.parquet", "spread_estimates.parquet", "drift_cells.parquet", "drift_hold_bands.parquet")
PER_WINDOW = ("universe.parquet", "leader_series.parquet")


def tree(ctx, key: str) -> Path:
    return ctx.root / ctx.raw["selection_v2"][key]


def run_allpriced(ctx, out: Path | None = None) -> Path:
    from arkstream import replay_capture
    from arkstream.freeze import guard
    from arkstream.replay import run as replay_run
    from arkstream.replay_frozen import stress_coverage
    from arkstream.replay_market import midnight
    from arkstream.replay_sensitivity import run_sensitivities

    dr = drift.DriftRules.from_config(ctx.raw)
    guard(ctx, midnight(dr.holdout_start))  # the nine windows end at the holdout start
    out = Path(out) if out else tree(ctx, "allpriced_dir")
    replay_run(ctx, output=out, simulate=False)
    run_sensitivities(ctx, output=out, models=(MODEL,), original=out)
    stress_coverage(ctx, out).write_csv(out / "stress_coverage.csv")
    replay_capture.run(ctx, out)
    return out


def tradable_pairs(sets: dict[date, pl.DataFrame]) -> pl.DataFrame:
    return pl.concat([s.select("trader", "coin").with_columns(origin=pl.lit(o)) for o, s in sorted(sets.items())]
                     ).select("origin", "trader", "coin").sort("origin", "trader", "coin")


def copy_shared(src: Path, dest: Path, windows: list[Path]) -> None:
    for name in SHARED:
        shutil.copy2(src / name, dest / name)
    for rel in windows:
        for name in PER_WINDOW:
            if (src / rel / name).is_file():
                (dest / rel).mkdir(parents=True, exist_ok=True)
                shutil.copy2(src / rel / name, dest / rel / name)


def run_tradable(ctx, out: Path | None = None, allpriced: Path | None = None) -> Path:
    from arkstream import replay_capture
    from arkstream import selection_v2_coins as SC
    from arkstream.freeze import guard
    from arkstream.replay_frozen import stress_coverage
    from arkstream.replay_market import midnight
    from arkstream.replay_sensitivity import run_sensitivities

    dr = drift.DriftRules.from_config(ctx.raw)
    guard(ctx, midnight(dr.holdout_start))
    src = Path(allpriced) if allpriced else tree(ctx, "allpriced_dir")
    out = Path(out) if out else tree(ctx, "tradable_dir")
    out.mkdir(parents=True, exist_ok=True)
    sets = {o: SC.wallet_sets(ctx, o, src) for o in dr.origin_dates}
    tradable_pairs(sets).write_parquet(out / "tradable_pairs.parquet")
    run_sensitivities(ctx, output=out, models=(MODEL,), original=src, tradable=sets)
    rels = sorted(p.relative_to(out) for p in out.glob("origin=*/window=*") if p.is_dir())
    copy_shared(src, out, rels)
    stress_coverage(ctx, out).write_csv(out / "stress_coverage.csv")
    replay_capture.run(ctx, out)
    return out
