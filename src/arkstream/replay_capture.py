"""ADR-0162: copy capture against a zero-delay, zero-cost benchmark with the follower's own sizing, and the copy's
market-relative return (BTC / ETH buy-and-hold, alpha and betas as in Phase 2's market exposure).

Inputs are the frozen replay's own outputs (`research/replay_frozen/`): each window's scenario ledgers, the benchmark
ledgers written beside them (`benchmark=unattainable_frozen/`, ADR-0162 item 1), the leader's daily series
(`leader_series.parquet`) and the Hyperliquid daily marks (`valuation_marks.parquet`). Nothing here reads a price
the replay did not already use; the holdout window is never present."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from arkstream.leader_assets import exposure
from arkstream.replay_market import DAY

C = pl.col
BENCH = "benchmark=unattainable_frozen"
SUFFIX = "_sqrt_cap_part_ns_sweep_frozen"
# ADR-0162: |benchmark PnL| below this share of the allocation makes the ratio not meaningful.
MIN_BENCHMARK_SHARE = 0.01
PARTS = ("delay_drift", "sweep_anchor", "half_spread", "impact", "fees", "funding_difference",
         "not_executed_below_minimum", "not_executed_cap_deferral", "not_executed_uncopyable_coin",
         "not_executed_pricing_failure", "not_executed_participation_clip", "not_executed_other")
CATEGORY = {
    "below_minimum": "below_minimum", "below_minimum_at_ack": "below_minimum",
    "cap_headroom": "cap_deferral", "missing_cap_mark": "cap_deferral",
    "failed_price_check": "uncopyable_coin", "no_binance_mapping": "uncopyable_coin",
    "insufficient_price_check": "uncopyable_coin", "coin_filter_excluded": "uncopyable_coin",
    "no_drift_cell": "pricing_failure", "stress_sample_unavailable": "pricing_failure",
    "no_eligible_aggtrade": "pricing_failure", "outside_mapping_window": "pricing_failure",
    "missing_sqrt_inputs": "pricing_failure", "missing_impact_volume": "pricing_failure",
    "missing_participation_volume": "pricing_failure", "missing_order_budget": "pricing_failure",
    "invalid_scenario_price": "pricing_failure",
}
WEIGHTED = ("below_minimum", "cap_deferral", "uncopyable_coin", "pricing_failure", "participation_clip")


def end_marks(marks: pl.DataFrame, end_ms: int) -> pl.DataFrame:
    """The Hyperliquid daily mark every ledger values the closing book at (the boundary at the window end)."""
    return marks.filter(C("boundary") == end_ms // DAY).select("coin", m_end="mark")


def book_pnl(daily: pl.DataFrame, allocation: float) -> pl.DataFrame:
    """Final equity minus allocation, from the ledger's own last day (null when a mark or funding rate is missing)."""
    return daily.sort("trader", "day").group_by("trader", maintain_order=True).agg(
        pnl=C("equity").last() - allocation, funding=C("funding").sum(), days=pl.len())


def price_parts(orders: pl.DataFrame) -> pl.DataFrame:
    """Per filled follower order, its price relative to the leader's own first fill L split exactly into the parts
    of the replay's price chain (ADR-0080, ADR-0088): q(anchor - L) + q(mid_L - anchor) + q(ref - mid_L)
    + q(fill - ref)."""
    f = orders.filter(C("status") == "filled")
    lead = C("leader_first_px").fill_null(C("anchor_px"))
    impact = C("quantity").abs() * C("ref_px") * C("impact_bps").fill_null(0.0) / 1e4
    return f.select(
        "trader", "coin", "quantity", L=lead,
        sweep_anchor=C("quantity") * (C("anchor_px") - lead),
        delay_drift=C("quantity") * (C("ref_px") - C("mid_L")),
        half_spread=C("quantity") * (C("mid_L") - C("anchor_px"))
        + C("quantity") * (C("fill_px") - C("ref_px")) - impact,
        impact=impact,
        fees=C("fee"),
    )


def weights(orders: pl.DataFrame) -> pl.DataFrame:
    """Missed notional per trader, coin and category: intents not executed at their visible anchor, and the clipped
    part of a filled order (ADR-0086/0087 budget)."""
    miss = orders.filter(C("status").is_in(list(CATEGORY))).select(
        "trader", "coin", category=C("status").replace_strict(CATEGORY, default=None),
        w=C("intended_notional").fill_null(0.0))
    clip = orders.filter((C("status") == "filled") & C("requested_qty").is_not_null()).select(
        "trader", "coin", category=pl.lit("participation_clip"),
        w=((C("requested_qty").abs() - C("submitted_qty").abs()).clip(0) * C("anchor_px")).fill_null(0.0))
    return (pl.concat([miss, clip]).sort("trader", "coin", "category")
            .group_by("trader", "coin", "category", maintain_order=True).agg(C("w").sum()))


def capture(orders: pl.DataFrame, daily: pl.DataFrame, bench_daily: pl.DataFrame, bench_orders: pl.DataFrame,
            marks_end: pl.DataFrame, universe: pl.DataFrame, allocation: float) -> pl.DataFrame:
    """ADR-0162 item 2: one row per address. gap = benchmark PnL - follower PnL = the sum of PARTS, exactly."""
    f = book_pnl(daily, allocation)
    b = book_pnl(bench_daily, allocation).rename({"pnl": "benchmark_pnl", "funding": "benchmark_funding",
                                                   "days": "benchmark_days"})
    pp = price_parts(orders).join(marks_end, on="coin", how="left").sort("trader", "coin")
    # follower's own trades revalued at the leader's prices, per coin: sum q (M_end - L)
    at_leader = pp.group_by("trader", "coin", maintain_order=True).agg(
        f_at_l=(C("quantity") * (C("m_end") - C("L"))).sum(), unmarked=C("m_end").is_null().sum())
    bf = bench_orders.filter(C("status") == "filled").join(marks_end, on="coin", how="left").sort("trader", "coin")
    b_at_l = bf.group_by("trader", "coin", maintain_order=True).agg(
        b_at_l=(C("quantity") * (C("m_end") - C("fill_px"))).sum(), b_unmarked=C("m_end").is_null().sum())
    q = at_leader.join(b_at_l, on=["trader", "coin"], how="full", coalesce=True).with_columns(
        C("f_at_l", "b_at_l", "unmarked", "b_unmarked").fill_null(0))
    q = q.with_columns(r=C("b_at_l") - C("f_at_l")).sort("trader", "coin")
    w = weights(orders)
    tot = w.group_by("trader", "coin", maintain_order=True).agg(w_total=C("w").sum())
    alloc = (q.join(w, on=["trader", "coin"], how="left").join(tot, on=["trader", "coin"], how="left")
             .with_columns(share=pl.when(C("w_total") > 0).then(C("w") / C("w_total")))
             .sort("trader", "category", "coin"))
    split = (alloc.filter(C("share").is_not_null())
             .group_by("trader", "category", maintain_order=True).agg((C("r") * C("share")).sum().alias("v"))
             .with_columns(category=pl.lit("not_executed_") + C("category")))
    other = (q.join(tot, on=["trader", "coin"], how="left").filter(~(C("w_total") > 0)).sort("trader", "coin")
             .group_by("trader", maintain_order=True).agg(v=C("r").sum())
             .with_columns(category=pl.lit("not_executed_other")))
    qty = pl.concat([split.select("trader", "category", "v"), other.select("trader", "category", "v")])
    qty = qty.sort("trader", "category").pivot(on="category", index="trader", values="v", aggregate_function="first")
    prices = pp.group_by("trader", maintain_order=True).agg(
        C("delay_drift", "sweep_anchor", "half_spread", "impact", "fees").sum())
    unmarked = q.group_by("trader", maintain_order=True).agg(unmarked=(C("unmarked") + C("b_unmarked")).sum())
    out = (universe.select("trader", "all_gates_pass", "return_source", "leader_return", "leader_days")
           .join(f, on="trader", how="left").join(b, on="trader", how="left")
           .join(prices, on="trader", how="left").join(qty, on="trader", how="left")
           .join(unmarked, on="trader", how="left"))
    for p in PARTS:
        if p not in out.columns:
            out = out.with_columns(pl.lit(0.0).alias(p))
    out = out.with_columns(C(*[p for p in PARTS if p != "funding_difference"]).fill_null(0.0),
                           funding_difference=C("benchmark_funding") - C("funding"))
    gap = C("benchmark_pnl") - C("pnl")
    threshold = MIN_BENCHMARK_SHARE * allocation
    complete = C("pnl").is_not_null() & C("benchmark_pnl").is_not_null() & (C("unmarked").fill_null(0) == 0)
    out = out.with_columns(gap=gap, closure=gap - pl.sum_horizontal(*PARTS)).with_columns(
        status=pl.when(~complete).then(pl.lit("incomplete"))
        .when(C("benchmark_pnl").abs() < threshold).then(pl.lit("not_meaningful"))
        .otherwise(pl.lit("ok")),
    )
    out = out.with_columns(
        capture_ratio=pl.when(C("status") == "ok").then(C("pnl") / C("benchmark_pnl")),
        **{p + "_share": pl.when(C("status") == "ok").then(C(p) / C("benchmark_pnl")) for p in PARTS},
    )
    out = out.rename({"pnl": "follower_pnl", "funding": "follower_funding"}).drop("benchmark_days", "days", "unmarked")
    head = ["trader", "all_gates_pass", "return_source", "leader_return", "leader_days", "status", "capture_ratio",
            "follower_pnl", "benchmark_pnl", "gap", *PARTS, "closure", *[p + "_share" for p in PARTS],
            "follower_funding", "benchmark_funding"]
    return out.select(head).sort("trader")


def daily_series(daily: pl.DataFrame, bench_daily: pl.DataFrame, leader: pl.DataFrame, allocation: float):
    """Daily cumulative follower PnL, benchmark PnL and the leader's own cumulative TWR (ADR-0162 item 3)."""
    f = daily.select("trader", "day", follower_pnl=C("equity") - allocation)
    b = bench_daily.select("trader", "day", benchmark_pnl=C("equity") - allocation)
    lead = (leader.with_columns(day=(C("ts") - pl.duration(milliseconds=1)).dt.date())
            .sort("trader", "ts").with_columns(leader_twr=(1 + C("r")).cum_prod().over("trader") - 1)
            .group_by("trader", "day", maintain_order=True).agg(C("leader_twr").last(), C("return_source").last()))
    return (f.join(b, on=["trader", "day"], how="full", coalesce=True)
            .join(lead, on=["trader", "day"], how="left").sort("trader", "day")
            .with_columns(C("leader_twr").forward_fill().over("trader")))


def factor_returns(marks: pl.DataFrame, start_ms: int, end_ms: int) -> pl.DataFrame:
    """BTC and ETH daily returns from the Hyperliquid daily marks: day d = mark at boundary d+1 / mark at d - 1."""
    m = marks.filter(C("coin").is_in(["BTC", "ETH"]) & C("boundary").is_between(start_ms // DAY, end_ms // DAY))
    m = m.sort("coin", "boundary").with_columns(
        r=pl.when(C("boundary").diff().over("coin") == 1).then(C("mark") / C("mark").shift().over("coin") - 1),
        day=(C("boundary") - 1).cast(pl.Date))
    return m.pivot(on="coin", index="day", values="r").drop_nulls(["BTC", "ETH"]).sort("day")


def market_relative(daily: pl.DataFrame, marks: pl.DataFrame, start_ms: int, end_ms: int) -> pl.DataFrame:
    """ADR-0162 item 4: buy-and-hold BTC / ETH over the window and the copy's daily alpha and betas to BTC and ETH
    (one regression on both, Bartlett HAC standard errors, 95% intervals: `leader_assets.exposure`)."""
    fac = factor_returns(marks, start_ms, end_ms)
    hold, since = {}, {}
    for coin in ("BTC", "ETH"):
        # from the first boundary in the window with a mark (the daily marks start on 28 Jul 2025) to the end
        e = (marks.filter((C("coin") == coin) & C("boundary").is_between(start_ms // DAY, end_ms // DAY)
                          & C("mark").is_not_null()).sort("boundary"))
        ok = e.height >= 2 and e["boundary"][-1] == end_ms // DAY
        hold[coin] = e["mark"][-1] / e["mark"][0] - 1 if ok else None
        since[coin] = (e.select(C("boundary").first().cast(pl.Date)).item()) if ok else None
    sample = (daily.select("trader", "day", "daily_twr").drop_nulls("daily_twr").join(fac, on="day")
              .sort("trader", "day"))
    rows = []
    for (trader,), g in sample.group_by("trader", maintain_order=True):
        rows.append({"trader": trader, "n_days": g.height,
                     **exposure(*[g[c].to_numpy().astype(float) for c in ("daily_twr", "BTC", "ETH")])})
    coef = {k: pl.Float64 for k in exposure(np.array([]), np.array([]), np.array([]))}
    fits = pl.DataFrame(rows, schema={"trader": pl.String, "n_days": pl.Int64, **coef})
    copy = daily.sort("trader", "day").group_by("trader", maintain_order=True).agg(
        copy_return=(1 + C("daily_twr")).product() - 1, copy_days=C("daily_twr").count())
    return (copy.join(fits, on="trader", how="left")
            .with_columns(C("n_days").fill_null(0), btc_buy_hold=pl.lit(hold["BTC"], pl.Float64),
                          eth_buy_hold=pl.lit(hold["ETH"], pl.Float64),
                          buy_hold_from=pl.lit(min(d for d in since.values() if d) if any(since.values()) else None,
                                               pl.Date))
            .sort("trader"))


def run(ctx, out: Path) -> list[Path]:
    """Capture and market-relative tables for every window and scenario of the frozen replay under `out`."""
    from arkstream import drift
    from arkstream.config import load_yaml
    from arkstream.replay import windows
    from arkstream.replay_market import midnight, ms

    rules = load_yaml("execution.yaml", ctx.root / "config")["replay"]
    allocation = float(rules["allocation_usdc"])
    dr = drift.DriftRules.from_config(ctx.raw)
    origins = [midnight(o) for o in dr.origin_dates]
    marks = pl.read_parquet(out / "valuation_marks.parquet")
    caps, days, market = [], [], []
    for origin, window, start, end in windows(origins, midnight(dr.est_start), origins[-1]):
        folder = out / f"origin={origin.date()}" / f"window={window}"
        if not (folder / BENCH).is_dir():
            continue
        bench_daily = pl.read_parquet(folder / BENCH / "daily_copy_twr.parquet")
        if window == "training":  # a training window starts at the first fill day: the ledger's own first day
            start = midnight(bench_daily.select(C("day").min()).item())
        bench_orders = pl.read_parquet(folder / BENCH / "follower_orders.parquet",
                                       columns=["trader", "coin", "status", "quantity", "fill_px"])
        universe = pl.read_parquet(folder / "universe.parquet")
        leader = pl.read_parquet(folder / "leader_series.parquet")
        me = end_marks(marks, ms(end))
        tag = {"origin": pl.lit(origin.date()), "window": pl.lit(window)}
        names = (p.name.removeprefix("scenario=").removesuffix(SUFFIX) for p in folder.glob(f"scenario=*{SUFFIX}"))
        for sc in sorted(names):
            path = folder / f"scenario={sc}{SUFFIX}"
            daily = pl.read_parquet(path / "daily_copy_twr.parquet")
            orders = pl.read_parquet(path / "follower_orders.parquet", columns=[
                "trader", "coin", "status", "quantity", "fill_px", "fee", "anchor_px", "leader_first_px", "mid_L",
                "ref_px", "impact_bps", "intended_notional", "requested_qty", "submitted_qty"])
            t = {**tag, "scenario": pl.lit(sc)}
            caps.append(capture(orders, daily, bench_daily, bench_orders, me, universe, allocation).with_columns(**t))
            days.append(daily_series(daily, bench_daily, leader, allocation).with_columns(**t))
            market.append(market_relative(daily, marks, ms(start), ms(end)).with_columns(**t))
        market.append(market_relative(bench_daily, marks, ms(start), ms(end)).with_columns(
            **tag, scenario=pl.lit("benchmark")))
    keys = ["origin", "window", "scenario", "trader"]
    written = []
    for name, parts, sort in (("capture_summary", caps, keys), ("capture_daily", days, [*keys[:3], "trader", "day"]),
                              ("market_relative", market, keys)):
        df = pl.concat(parts, how="diagonal_relaxed")
        df = df.select(*keys, *[c for c in df.columns if c not in keys]).sort(sort)
        path = out / f"{name}.parquet"
        df.write_parquet(path, compression="zstd", statistics=False)
        written.append(path)
    return written
