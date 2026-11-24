"""The frozen replay with the selection rule's coin filter executed inside it (ADR-A0140).

`run` replays the frozen full stack (`*_sqrt_cap_part_ns_sweep_frozen`, every scenario and the ADR-0063 benchmark)
on the nine windows into `research/replay_coinfilter/`. Each window at an origin copies only that origin's coin set:
BTC, ETH, HYPE, SOL and the coins the unfiltered training-window copy captured well (`selection_coins.coin_set`,
ADR-A0136 definition, computed from `research/replay_frozen/`, point in time). Every other coin passing the price check
becomes `coin_filter_excluded`: never traded, and left out of the 1.5x cap book and resize legs. The shared inputs
that do not depend on the filter (marks, drift cells, spreads, bands, universes, leader series) are copied from the
unfiltered tree; stress coverage (ADR-0055) and capture (ADR-0063) are then rebuilt on the filtered tree.

`run_window` replays one test-shaped window through the same code with inputs bounded at its end. `run_holdout` is the
holdout path (origin 3 Dec, 3 Dec 2025 - 4 Jan 2026 00:00 UTC, the 3 Dec coin set), refused unless the freeze holds.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import polars as pl

from arkstream import drift
from arkstream.replay_frozen import MODEL

C = pl.col
OUT = "research/replay_coinfilter"
HOLDOUT_OUT = "research/replay_holdout"
RULE = "rule_b_coin_filter"
SHARED = ("valuation_marks.parquet", "spread_estimates.parquet", "drift_cells.parquet", "drift_hold_bands.parquet")
PER_WINDOW = ("universe.parquet", "leader_series.parquet")


def frozen_tree(ctx) -> Path:
    return ctx.root / "research/replay_frozen"


def coin_sets(ctx) -> dict[date, list[str]]:
    """Kept coins per origin (ADR-A0136 definition on the unfiltered frozen replay's training window)."""
    from arkstream import selection as S
    from arkstream import selection_coins as SC

    raw = {**ctx.raw, "selection": {**ctx.raw["selection"], "replay_dir": "research/replay_frozen"}}
    base = type(ctx)(raw=raw, root=ctx.root)
    rules = S.Rules.from_config(base.raw, RULE)
    out = {}
    for o in drift.DriftRules.from_config(ctx.raw).origin_dates:
        out[o] = sorted(SC.coin_set(base, o, rules).filter("kept")["coin"].to_list())
    return out


def coin_set_table(sets: dict[date, list[str]]) -> pl.DataFrame:
    return pl.DataFrame([(o, c) for o, coins in sorted(sets.items()) for c in coins],
                        schema={"origin": pl.Date, "coin": pl.String}, orient="row")


def copy_shared(src: Path, dest: Path, windows: list[Path]) -> None:
    for name in SHARED:
        shutil.copy2(src / name, dest / name)
    for rel in windows:
        for name in PER_WINDOW:
            if (src / rel / name).is_file():
                (dest / rel).mkdir(parents=True, exist_ok=True)
                shutil.copy2(src / rel / name, dest / rel / name)


def run(ctx, out: Path | None = None) -> Path:
    from arkstream import replay_capture
    from arkstream.freeze import guard
    from arkstream.replay_frozen import stress_coverage
    from arkstream.replay_market import midnight
    from arkstream.replay_sensitivity import run_sensitivities

    dr = drift.DriftRules.from_config(ctx.raw)
    guard(ctx, midnight(dr.holdout_start))  # the nine windows end at the holdout start
    out = Path(out) if out else ctx.root / OUT
    out.mkdir(parents=True, exist_ok=True)
    sets = coin_sets(ctx)
    coin_set_table(sets).write_csv(out / "coin_sets.csv")
    run_sensitivities(ctx, output=out, models=(MODEL,), original=frozen_tree(ctx), coin_sets=sets)
    rels = sorted(p.relative_to(out) for p in out.glob("origin=*/window=*") if p.is_dir())
    copy_shared(frozen_tree(ctx), out, rels)
    stress_coverage(ctx, out).write_csv(out / "stress_coverage.csv")
    replay_capture.run(ctx, out)
    return out


def run_window(ctx, origin: date, start: date, end: date, out: Path) -> Path:
    """One window through the single-window branch (the holdout's code path), copying the origin's coin set."""
    from arkstream.replay_sensitivity import run_sensitivities

    sets = coin_sets(ctx)
    out.mkdir(parents=True, exist_ok=True)
    run_sensitivities(ctx, output=out, models=(MODEL,), original=frozen_tree(ctx), coin_sets=sets,
                      window=(origin, start, end))
    return out


def holdout_window(ctx) -> tuple[date, date, date]:
    sp = ctx.raw["splits"]["holdout"]
    start = date.fromisoformat(sp["start"])
    return start, start, date.fromisoformat(sp["end"])


def run_holdout(ctx, out: Path | None = None) -> Path:
    """The holdout replay (ADR-A0140 item 6): refused by `freeze.guard` unless the freeze holds."""
    from arkstream.freeze import guard
    from arkstream.replay_market import midnight

    origin, start, end = holdout_window(ctx)
    guard(ctx, midnight(end))
    target = Path(out) if out else ctx.root / HOLDOUT_OUT
    run_window(ctx, origin, start, end, target)
    copy_shared(frozen_tree(ctx), target, [Path(f"origin={origin}") / "window=training"])
    return target
