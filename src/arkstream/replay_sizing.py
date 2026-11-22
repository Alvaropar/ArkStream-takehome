"""Frozen reference equity versus the dynamic denominator (ADR-0116), side by side on the nine windows.

`run` writes, under one folder (default `research/replay_sizing/`): the original-model replay that supplies the
shared inputs (universe, drift cells, bands, spreads), the dynamic full stack (`*_sqrt_cap_part_ns_sweep`), the
frozen one (`*_sqrt_cap_part_ns_sweep_frozen`) and the comparison tables:

* `sizing_comparison_addresses.csv`: one row per address, window and scenario with both variants' target exposure,
  gross and leverage, turnover, orders and skips, copy return and drawdown, their differences, and the leader's
  equity path in the window (start and end equity, net flows, the largest single flow, the first reference);
* `sizing_comparison_pooled.csv`: the same pooled by origin, window, scenario, universe (gate-passers, all A/B) and
  variant, plus the four development tests together.

The holdout test window is never computed (the replay stops at the 3 Dec origin).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from arkstream import drift
from arkstream.config import load_yaml
from arkstream.replay import windows
from arkstream.replay_market import bounded_inputs, midnight, ms

C = pl.col
VARIANTS = {"dynamic": "part_ns_sweep", "frozen": "part_ns_sweep_frozen"}
SCENARIOS = ("optimistic", "base", "stress")
SUMMARY = ["trader", "all_gates_pass", "return_source", "copy_return", "before_funding", "max_drawdown", "measurement",
           "priced_share", "orders", "filled", "small", "unpriced", "unsized", "reduce_only", "excluded",
           "total_turnover", "fees", "execution_cost", "mean_gross", "max_gross", "mean_leverage", "max_leverage",
           "final_equity", "parameterised_notional_share", "leader_return"]
METRICS = ["copy_return", "max_drawdown", "total_turnover", "mean_gross", "max_gross", "mean_leverage", "max_leverage",
           "mean_target_usdc", "max_target_usdc", "mean_multiplier", "orders", "filled", "small", "unpriced", "unsized",
           "reduce_only"]


def run(ctx, out: Path | None = None) -> Path:
    from arkstream.replay import run as replay_run
    from arkstream.replay_sensitivity import SIZING_MODELS, run_sensitivities

    out = Path(out) if out else ctx.root / "research/replay_sizing"
    replay_run(ctx, output=out)
    run_sensitivities(ctx, output=out, models=SIZING_MODELS, original=out)
    compare(ctx, out)
    return out


def leader_equity(traders: pl.DataFrame, start, end) -> pl.DataFrame:
    """The leader's equity path in [start, end) from the snapshots known by then (no later row is read)."""
    s = traders.filter(C("ts") < end).sort("trader", "ts", "src_row").with_columns(
        d_nd=C("net_deposit").diff().over("trader"), prev_eq=C("equity").shift().over("trader"))
    opening = s.filter(C("ts") <= start).group_by("trader").agg(equity_start=C("equity").last())
    inside = s.filter((C("ts") > start) & (C("ts") < end))
    path = inside.group_by("trader").agg(
        equity_end=C("equity").last(),
        equity_min=C("equity").min(),
        equity_max=C("equity").max(),
        net_flows=C("d_nd").sum(),
        largest_flow=C("d_nd").sort_by(C("d_nd").abs()).last(),
        largest_flow_share=(C("d_nd").abs() / C("prev_eq").clip(lower_bound=1e-9)).max(),
        snapshots=pl.len(),
    )
    return opening.join(path, on="trader", how="full", coalesce=True).with_columns(
        equity_change=pl.when(C("equity_start") > 0).then(C("equity_end") / C("equity_start") - 1),
        net_flows_share=pl.when(C("equity_start") > 0).then(C("net_flows") / C("equity_start")),
    ).sort("trader")


def _orders(path: Path) -> pl.DataFrame:
    """Target exposure at the triggering legs (USDC before the 1.5x projection) and the copy multiplier."""
    # Eager, totally sorted and order-preserving: float means come out byte-identical run to run (ADR-0008).
    o = pl.read_parquet(path, columns=["trader", "decision_ms", "coin", "batch", "resize_leg", "uncapped_gross_usdc",
                                       "copy_multiplier", "sizing_equity"])
    o = o.filter(~C("resize_leg")).sort("trader", "decision_ms", "coin", "batch")
    return o.group_by("trader", maintain_order=True).agg(
        mean_target_usdc=C("uncapped_gross_usdc").mean(),
        max_target_usdc=C("uncapped_gross_usdc").max(),
        mean_multiplier=C("copy_multiplier").mean(),
        mean_sizing_equity=C("sizing_equity").mean(),
    ).sort("trader")


def _reviews(path: Path) -> pl.DataFrame:
    o = pl.scan_parquet(path).filter(~C("resize_leg")).select("trader", "eq_ms", "equity", "review_status")
    return o.group_by("trader").agg(
        reviews_seen=C("eq_ms").n_unique(),
        reviews_not_ok=C("eq_ms").filter(C("review_status") != "ok").n_unique(),
        first_reference=C("equity").sort_by("eq_ms").first(),
    ).collect().sort("trader")


def compare(ctx, out: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    from arkstream.replay_sensitivity import canonical

    dr = drift.DriftRules.from_config(ctx.raw)
    stop = midnight(dr.holdout_start)
    origins = [midnight(o) for o in dr.origin_dates]
    inputs = bounded_inputs(ctx, stop)  # nothing at or after the 3 Dec origin
    first = midnight(inputs.fills["ts"].min().date())  # the replay's training start
    traders = inputs.traders
    rows, leaders = [], []
    for origin, window, start, end in windows(origins, first, stop):
        folder = out / f"origin={origin.date()}" / f"window={window}"
        leaders.append(
            leader_equity(traders, start, end).with_columns(origin=pl.lit(origin.date()), window=pl.lit(window)))
        for scenario in SCENARIOS:
            for variant, model in VARIANTS.items():
                sub = folder / f"scenario={canonical(scenario, model)}"
                s = pl.read_parquet(sub / "address_summary.parquet", columns=SUMMARY)
                s = s.join(_orders(sub / "follower_orders.parquet"), on="trader", how="left")
                if variant == "frozen":
                    s = s.join(_reviews(sub / "follower_orders.parquet"), on="trader", how="left")
                rows.append(s.with_columns(origin=pl.lit(origin.date()), window=pl.lit(window),
                                           scenario=pl.lit(scenario), variant=pl.lit(variant)))
    long = pl.concat(rows, how="diagonal_relaxed")
    keys = ["origin", "window", "scenario", "trader"]
    # The review fields exist only for the frozen variant (null on dynamic rows after the diagonal concat).
    dyn = long.filter(C("variant") == "dynamic").drop("variant", "reviews_seen", "reviews_not_ok", "first_reference")
    frz = long.filter(C("variant") == "frozen").drop("variant", "all_gates_pass", "return_source", "leader_return")
    wide = dyn.join(frz, on=keys, how="full", coalesce=True, suffix="_frozen").rename(
        {m: f"{m}_dynamic" for m in METRICS + ["before_funding", "measurement", "priced_share", "excluded", "fees",
                                              "execution_cost", "final_equity", "parameterised_notional_share",
                                              "mean_sizing_equity"]})
    # Counts are unsigned: difference in floats so a smaller frozen count is negative, not a wrapped integer.
    wide = wide.with_columns(*[(C(f"{m}_frozen").cast(pl.Float64) - C(f"{m}_dynamic").cast(pl.Float64))
                               .alias(f"{m}_diff") for m in METRICS])
    wide = wide.join(pl.concat(leaders), on=["origin", "window", "trader"], how="left").sort(keys)
    allocation = float(load_yaml("execution.yaml", ctx.root / "config")["replay"]["allocation_usdc"])
    pooled = _pooled(long, allocation)
    wide.write_csv(out / "sizing_comparison_addresses.csv")
    pooled.write_csv(out / "sizing_comparison_pooled.csv")
    return wide, pooled


def _pool(allocation: float) -> list[pl.Expr]:
    return [
        pl.len().alias("addresses"),
        C("copy_return").count().alias("measured"),
        (C("measurement") == "unmeasured_low_coverage").sum().alias("unmeasured_low_coverage"),
        (C("copy_return") > 0).sum().alias("positive"),
        C("copy_return").mean().alias("mean_copy_return"),
        C("copy_return").median().alias("median_copy_return"),
        (C("final_equity") - allocation).filter(C("copy_return").is_not_null()).sum().alias("pnl_usdc"),
        C("total_turnover").sum().alias("turnover_usdc"),
        C("max_drawdown").mean().alias("mean_max_drawdown"),
        C("max_drawdown").min().alias("worst_max_drawdown"),
        (C("max_drawdown") < -0.10).sum().alias("drawdown_over_10pct"),
        C("mean_gross").mean().alias("mean_gross_usdc"),
        C("max_gross").max().alias("max_gross_usdc"),
        C("mean_leverage").mean().alias("mean_leverage"),
        C("max_leverage").max().alias("max_leverage"),
        C("mean_target_usdc").mean().alias("mean_target_usdc"),
        C("mean_multiplier").mean().alias("mean_multiplier"),
        C("orders").sum().alias("intents"),
        C("filled").sum().alias("filled"),
        C("small").sum().alias("small_skips"),
        C("unpriced").sum().alias("unpriced"),
        C("unsized").sum().alias("unsized"),
        C("reduce_only").sum().alias("reduce_only"),
    ]


def _pooled(long: pl.DataFrame, allocation: float) -> pl.DataFrame:
    parts = []
    for universe, data in (("gate_passers", long.filter("all_gates_pass")), ("all_ab", long)):
        by = data.group_by("origin", "window", "scenario", "variant").agg(_pool(allocation))
        tests = data.filter(C("window") == "test").group_by("scenario", "variant").agg(_pool(allocation)).with_columns(
            origin=pl.lit(None, pl.Date), window=pl.lit("all_tests"))
        parts.append(pl.concat([by, tests.select(by.columns)]).with_columns(universe=pl.lit(universe)))
    pooled = pl.concat(parts)
    return pooled.with_columns(
        cost_to_absorb_bps=pl.when(C("turnover_usdc") > 0).then(C("pnl_usdc") / C("turnover_usdc") * 1e4)
    ).sort("universe", "window", "origin", "scenario", "variant", nulls_last=True)


def review_audit(orders: pl.DataFrame, end) -> dict[str, int]:
    """Checks on a frozen-variant ledger: no review after its decision, the multiplier bound, the window end, and
    no reduce-only order that adds risk (a filled reduce-only leg always moves the position toward zero)."""
    o = orders.filter(~C("resize_leg"))
    return o.select(
        review_after_decision=(C("eq_ms") > C("decision_ms")).sum(),
        multiplier_above_one=(C("copy_multiplier") > 1 + 1e-12).sum(),
        ack_after_end=(C("ack_ms") >= ms(end)).sum(),
    ).row(0, named=True)
