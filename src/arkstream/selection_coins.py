"""Coin filter (ADR-0136, variant `rule_b_coin_filter`): copy a leader only in coins where the copy keeps a high share
of the same-sizing benchmark's PnL, judged on the training window ending at the origin.

PnL per (address, coin) over a window is attributed from the replay's own ledger: the follower's cash flows in that
coin, plus its closing position at the window-end Hyperliquid daily mark, plus its funding in that coin. Summed over
coins it equals the ledger's PnL (final equity - allocation). A filtered sleeve's return is the sum over kept coins over
the allocation. **Approximation, stated:** this removes the dropped coins' PnL from the existing replay rather than
re-running it without them, so the 1.5x address cap, which scaled every coin together, is not re-solved; the replay
itself is unchanged (no new execution model, brief: out of scope).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import polars as pl

from arkstream import selection as S
from arkstream.replay_book import ledger
from arkstream.replay_capture import BENCH
from arkstream.replay_market import DAY, midnight, ms

C = pl.col
KEY = ["trader", "coin"]


def coin_pnl(f: pl.DataFrame, fund: pl.DataFrame, marks: pl.DataFrame, end_ms: int) -> pl.DataFrame:
    """PnL per (trader, coin): cash + closing position x window-end mark + funding; null if a held coin has no mark."""
    me = marks.filter(C("boundary") == end_ms // DAY).select("coin", m_end="mark")
    book = f.sort(*KEY, "ack_ms", "decision_ms", "batch", "oid").group_by(KEY, maintain_order=True).agg(
        cash=C("cash").sum(), pos=C("pos").last())
    fu = fund.sort(*KEY).group_by(KEY, maintain_order=True).agg(funding=C("payment").sum(),
                                                                 unknown=C("payment").null_count())
    out = (book.join(fu, on=KEY, how="full", coalesce=True).join(me, on="coin", how="left")
           .with_columns(C("cash", "pos", "funding").fill_null(0.0), C("unknown").fill_null(0)))
    held = C("pos").abs() > 1e-10
    return out.with_columns(
        pnl=pl.when(C("unknown") > 0).then(None).when(held & C("m_end").is_null()).then(None)
        .otherwise(C("cash") + pl.when(held).then(C("pos") * C("m_end")).otherwise(0.0) + C("funding"))
    ).select(*KEY, "cash", "pos", "m_end", "funding", "pnl").sort(KEY)


def window_coin_pnl(ctx, origin: date, window: str, scenario: str | None, end: date) -> pl.DataFrame:
    """`coin_pnl` for one window of the frozen replay; `scenario=None` reads the ADR-0162 benchmark ledger."""
    end_ms = ms(midnight(end))
    if scenario is None:
        d = S.window_dir(ctx, origin, window) / BENCH
    else:
        d = S.scenario_dir(ctx, origin, window, scenario)
    orders = pl.read_parquet(d / "follower_orders.parquet", columns=[
        "trader", "coin", "status", "quantity", "fill_px", "fee", "ack_ms", "decision_ms", "batch", "oid"])
    f = ledger(orders, datetime.fromtimestamp(end_ms / 1000, tz=UTC))
    fund = pl.read_parquet(d / "funding_payments.parquet", columns=["trader", "coin", "payment"])
    marks = pl.read_parquet(S.replay_dir(ctx) / "valuation_marks.parquet")
    return coin_pnl(f, fund, marks, end_ms)


def coin_set(ctx, origin: date, rules: S.Rules) -> pl.DataFrame:
    """ADR-0136 coin set at an origin, from its training window (all A/B, ranking scenario): a coin is kept when it is
    one of the always-kept coins, or its summed benchmark PnL is at least `min_benchmark_pnl_usdc` and the summed
    follower PnL is at least `min_capture` of it."""
    fol = window_coin_pnl(ctx, origin, "training", rules.scenario, origin)
    ben = window_coin_pnl(ctx, origin, "training", None, origin)
    agg = lambda df, name: df.sort("coin", "trader").group_by("coin", maintain_order=True).agg(  # noqa: E731
        C("pnl").sum().alias(name), C("pnl").null_count().alias(name + "_unvalued"))
    c = agg(fol, "follower_pnl").join(agg(ben, "benchmark_pnl"), on="coin", how="full", coalesce=True).with_columns(
        C("follower_pnl", "benchmark_pnl").fill_null(0.0))
    c = c.with_columns(capture=pl.when(C("benchmark_pnl") > 0).then(C("follower_pnl") / C("benchmark_pnl")))
    kept = C("coin").is_in(list(rules.filter_always)) | (
        (C("benchmark_pnl") >= rules.filter_min_benchmark_usdc) & (C("capture") >= rules.filter_min_capture))
    return c.with_columns(kept=kept, origin=pl.lit(origin)).sort("coin")


def coin_daily(ctx, origin: date, window: str, scenario: str | None, start: date, end: date,
               kept: list[str] | None) -> pl.DataFrame:
    """Daily equity per address counting only `kept` coins (all coins when None), valued as the replay values its
    ledger (`replay_book.value_book`): allocation + cash of fills by their day + funding by its posting day +
    positions held through each midnight at that boundary's Hyperliquid mark. A day with a held coin lacking a mark,
    or an unknown funding payment, is null. With `kept=None` it reproduces the replay's `daily_copy_twr.equity`."""
    from datetime import timedelta

    from arkstream.selection_eval import ctx_allocation

    end_ms = ms(midnight(end))
    d = S.window_dir(ctx, origin, window) / BENCH if scenario is None else S.scenario_dir(ctx, origin, window,
                                                                                         scenario)
    orders = pl.read_parquet(d / "follower_orders.parquet", columns=[
        "trader", "coin", "status", "quantity", "fill_px", "fee", "ack_ms", "decision_ms", "batch", "oid"])
    f = ledger(orders, datetime.fromtimestamp(end_ms / 1000, tz=UTC))
    fund = pl.read_parquet(d / "funding_payments.parquet", columns=["trader", "coin", "payment", "day"])
    if kept is not None:
        f = f.filter(C("coin").is_in(kept))
        fund = fund.filter(C("coin").is_in(kept))
    marks = pl.read_parquet(S.replay_dir(ctx) / "valuation_marks.parquet").select("coin", "boundary", "mark")
    held = (f.filter(C("pos") != 0)
            .select(*KEY, "pos", boundary=pl.int_ranges(C("ack_ms") // DAY + 1, C("next_ms") // DAY + 1))
            .explode("boundary", empty_as_null=False).drop_nulls("boundary")
            .join(marks, on=["coin", "boundary"], how="left")
            .with_columns(day=(C("boundary") - 1).cast(pl.Date)))
    hold = held.sort("trader", "day", "coin").group_by("trader", "day", maintain_order=True).agg(
        holding=(C("pos") * C("mark")).sum(), missing=C("mark").null_count())
    cash = f.sort("trader", "day", "coin", "ack_ms", "batch", "oid").group_by(
        "trader", "day", maintain_order=True).agg(cash=C("cash").sum())
    fu = fund.sort("trader", "day", "coin", "payment", nulls_last=True).group_by(
        "trader", "day", maintain_order=True).agg(funding=C("payment").sum(), unknown=C("payment").null_count())
    universe = pl.read_parquet(S.window_dir(ctx, origin, window) / "universe.parquet", columns=["trader"])
    days = pl.date_range(start, end - timedelta(days=1), eager=True)
    alloc = ctx_allocation(ctx)
    g = (universe.join(pl.DataFrame({"day": days}), how="cross")
         .join(cash, on=["trader", "day"], how="left").join(fu, on=["trader", "day"], how="left")
         .join(hold, on=["trader", "day"], how="left")
         .with_columns(C("cash", "funding", "holding").fill_null(0.0), C("missing", "unknown").fill_null(0))
         .sort("trader", "day")
         .with_columns(bad=((C("missing") > 0) | (C("unknown") > 0)).cast(pl.Int64).cum_sum().over("trader"))
         .with_columns(equity=pl.when(C("bad") == 0).then(
             alloc + C("cash").cum_sum().over("trader") + C("funding").cum_sum().over("trader") + C("holding"))))
    return g.with_columns(daily_twr=C("equity") / C("equity").shift(1).over("trader").fill_null(alloc) - 1).select(
        "trader", "day", "equity", "daily_twr")


def filtered_outcomes(ctx, origin: date, end: date, kept: list[str], crash: list[date], ladder: float,
                      unfiltered: pl.DataFrame) -> tuple[pl.DataFrame, dict[str, pl.DataFrame]]:
    """`selection_eval.sleeve_outcomes` columns for the coin-filtered sleeves, from `coin_daily`: return, return
    without the crash dates, max drawdown and the stress check on the filtered equity. Stress measurement (ADR-0122
    coverage) is the replay's own, which counts every coin's intents."""
    from arkstream.selection_eval import ctx_allocation, max_drawdown

    alloc = ctx_allocation(ctx)
    daily = {sc: coin_daily(ctx, origin, "test", sc, origin, end, kept) for sc in ("base", "optimistic", "stress")}
    out = unfiltered.select("trader", "stress_measured")
    for sc, dd in daily.items():
        rows = []
        for (trader,), g in dd.sort("trader", "day").group_by("trader", maintain_order=True):
            eq = g["equity"].to_numpy().astype(float)
            ok = bool(np.isfinite(eq).all())
            r = g.filter(~C("day").is_in(crash))["daily_twr"]
            rows.append((trader, eq[-1] / alloc - 1 if ok else None,
                         float(np.prod(1 + r.to_numpy()) - 1) if ok else None,
                         max_drawdown(eq, alloc) if ok else None))
        part = pl.DataFrame(rows, schema={"trader": pl.String, sc: pl.Float64, f"{sc}_ex_crash": pl.Float64,
                                          f"{sc}_max_drawdown": pl.Float64}, orient="row")
        out = out.join(part, on="trader", how="left")
    exhausted = unfiltered.select("trader")  # the filtered book never trades more than the replay's
    out = out.join(exhausted, on="trader").with_columns(
        stress_check=pl.when(~C("stress_measured")).then(pl.lit("fail_unmeasured"))
        .when(C("stress_max_drawdown").is_null() | (C("stress_max_drawdown") < ladder)).then(pl.lit("fail_loss"))
        .otherwise(pl.lit("pass")))
    return out.sort("trader"), daily
