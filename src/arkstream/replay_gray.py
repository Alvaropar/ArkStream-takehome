"""Phase 5 step P5-1: the two sleeves at the gray sizes (ADR-0095 item 3, ADR-0090 item 4).

The frozen tradable stack (`*_sqrt_cap_part_ns_sweep_frozen`, ADR-0076) replayed for the hand-off 0x2cd9 and the
observation sleeve 0x971f only, at 2,500 and 5,000 USDC (10,000 is `research/replay_tradable/`). Every per-address
input is the tradable tree's; only the sleeve size (and the gross cap at the same 1.5x multiple) changes. The
single-sleeve rule keeps the per-order participation budget (ADR-0087 item 6).

`gray_sizing.csv` reports, per size, sleeve and test window (base): the sized order intents, the sub-minimum share
(count share of intents under the 10 USDC minimum, ADR-0090 item 4) and the filled orders per week. This share is the
unscaled one: the share that sets the gray size is measured on G* after `λ` by the P5-3 engine (ADR-0090 item 6).
The holdout window is never computed.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from arkstream import drift
from arkstream.config import load_yaml
from arkstream.replay_book import PRICING_FAILURES, SMALL
from arkstream.replay_frozen import MODEL
from arkstream.replay_orders import EXCLUDED
from arkstream.replay_sensitivity import canonical

C = pl.col
SIZES = (2500, 5000)
REFERENCE_SIZE = 10000
DEFAULT_OUT = "research/replay_gray"
NOT_INTENTS = ("at_target", "reduce_only", "unusable_equity", *EXCLUDED)


def sleeves(ctx) -> tuple[str, ...]:
    """The hand-off and the observation sleeves of the scheme (ADR-0086), in address order."""
    risk = load_yaml("risk.yaml", ctx.root / "config")
    hand_off = pl.read_parquet(ctx.root / risk["scheme"]["handoff_source"])
    if "role" in hand_off.columns:
        hand_off = hand_off.filter(C("role") == "hand_off")
    return tuple(sorted({*hand_off["trader"], *risk["scheme"]["observation_sleeves"]}))


def intent_counts(orders: pl.DataFrame) -> pl.DataFrame:
    """Per trader: sized intents (after the cap, before the minimum check), sub-minimum intents, fills."""
    intents = orders.filter(
        C("quantity").is_not_null() & (C("quantity").abs() > 1e-12) & ~C("status").is_in(NOT_INTENTS)
    )
    return intents.group_by("trader").agg(
        intents=pl.len(),
        sub_minimum=C("status").is_in(SMALL).sum(),
        below_minimum=(C("status") == "below_minimum").sum(),
        below_minimum_at_ack=(C("status") == "below_minimum_at_ack").sum(),
        filled=(C("status") == "filled").sum(),
        unpriced=C("status").is_in(PRICING_FAILURES).sum(),
        filled_notional=(C("quantity").abs() * C("fill_px")).filter(C("status") == "filled").sum(),
    )


def sizing_table(trees: dict[int, Path], origins, traders, scenario: str = "base") -> pl.DataFrame:
    rows = []
    for size, root in sorted(trees.items()):
        for origin in origins:
            folder = root / f"origin={origin}" / "window=test" / f"scenario={canonical(scenario, MODEL)}"
            path = folder / "follower_orders.parquet"
            if not path.is_file():
                continue
            orders = pl.read_parquet(path).filter(C("trader").is_in(list(traders)))
            rows.append(intent_counts(orders).with_columns(sleeve_usdc=pl.lit(size), origin=pl.lit(origin)))
    per_window = pl.concat(rows).with_columns(window_days=pl.lit(14))
    pooled = per_window.group_by("sleeve_usdc", "trader").agg(
        C("intents", "sub_minimum", "below_minimum", "below_minimum_at_ack", "filled", "unpriced",
          "filled_notional", "window_days").sum()
    ).with_columns(origin=pl.lit(None, pl.Date))
    out = pl.concat([per_window, pooled.select(per_window.columns)])
    return out.with_columns(
        scenario=pl.lit(scenario),
        sub_minimum_share=pl.when(C("intents") > 0).then(C("sub_minimum") / C("intents")),
        filled_per_week=C("filled") / C("window_days") * 7,
        scope=pl.when(C("origin").is_null()).then(pl.lit("pooled_4_test_windows")).otherwise(pl.lit("test_window")),
        label=pl.lit("unscaled single-sleeve replay; the gray size is set on G* after lambda (ADR-0090 item 6)"),
    ).sort("sleeve_usdc", "trader", "origin", nulls_last=True)


def summarize(ctx, out: Path, sizes=SIZES) -> Path:
    dr = drift.DriftRules.from_config(ctx.raw)
    trees = {size: out / f"sleeve={size}" for size in sizes}
    trees[REFERENCE_SIZE] = ctx.root / ctx.raw["selection_v2"]["tradable_dir"]
    test_origins = [o for o in dr.origin_dates if o < dr.holdout_start]
    path = out / "gray_sizing.csv"
    sizing_table(trees, test_origins, sleeves(ctx)).write_csv(path)
    return path


def run(ctx, out: Path | None = None, sizes=SIZES) -> Path:
    from arkstream.freeze import guard
    from arkstream.replay_market import midnight
    from arkstream.replay_sensitivity import run_sensitivities

    dr = drift.DriftRules.from_config(ctx.raw)
    guard(ctx, midnight(dr.holdout_start))
    out = Path(out) if out else ctx.root / DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    allpriced = ctx.root / ctx.raw["selection_v2"]["allpriced_dir"]
    traders = sleeves(ctx)
    pairs = pl.read_parquet(ctx.root / ctx.raw["selection_v2"]["tradable_dir"] / "tradable_pairs.parquet")
    pairs = pairs.filter(C("trader").is_in(list(traders)))  # the published ADR-0076 sets of the 10k tree
    sets = {o: pairs.filter(C("origin") == o).select("trader", "coin") for o in dr.origin_dates}
    for size in sizes:
        target = out / f"sleeve={size}"
        run_sensitivities(ctx, output=target, models=(MODEL,), original=allpriced, tradable=sets,
                          allocation_usdc=size, traders=traders)
    summarize(ctx, out, sizes)
    return out
