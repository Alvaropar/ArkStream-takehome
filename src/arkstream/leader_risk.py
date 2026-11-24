"""Leader evidence: tail-risk gates and profiles (computed, never applied to select anyone; Phase 4 selects).

Tail-risk metrics (ADR-0017, ADR-0018):

* intraday max drawdown: compounded hourly book returns (priced hours only; unpriced hours are counted);
* worst day, worst 3 consecutive days and max drawdown: daily book returns (complete calendar, an inactive
  day is exactly 0), and the account's start-convention returns as a second view;
* stress shock: per coin, the largest fall and the largest rise of P(t) / P(t - h) at hour marks, **before the
  origin only**; the fall is applied to long and the rise to short exposure at every hourly mark, all coins at
  once; typical (median over marks) and peak (max) implied loss as a share of equity. Coins with no price
  history have no shock; their exposure is reported as unshocked;
* leverage = gross exposure / equity of the latest snapshot at the mark; p95 and max over marks with exposure.
  Distance to liquidation (cross margin, one uniform adverse move) = 1 / leverage - maintenance margin rate;
  the rate is a stated assumption (config `leader.risk.maintenance_margin_rate`) until Hyperliquid metadata;
* liquidations and auto-deleveraging from the fill `dir`;
* dependence on the top 1% of round trips (leader_trips.trip_summary).

Profiles (ADR-0019): median holding time and band (drift.BAND_LABELS), orders per day, maker share, fee rate
from the fee column, median equity and band, typical order size against Binance traded volume (impact risk).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from arkstream.drift import BAND_EDGES_S, BAND_LABELS
from arkstream.positions import pit


# ---------------------------------------------------------------------------------------------- stress
def shocks(px: pl.DataFrame, asof: datetime, horizon_h: int) -> pl.DataFrame:
    """Largest observed fall and rise per coin over `horizon_h` hours, at hour marks t <= asof (both ends priced).

    shock_down (>= 0) is applied to long exposure and shock_up to short exposure (ADR-0017).
    """
    p = px.filter((pl.col("t") <= asof) & pl.col("price").is_not_null()).select("coin", "t", "price")
    lag = p.with_columns(t=(pl.col("t") + pl.duration(hours=horizon_h)).dt.cast_time_unit("ms")).rename(
        {"price": "p0"})
    mv = p.join(lag, on=["coin", "t"], how="inner").with_columns(move=pl.col("price") / pl.col("p0") - 1)
    dn = mv.sort("coin", "move", "t").group_by("coin", maintain_order=True).first().select(
        "coin", shock_down=pl.max_horizontal(-pl.col("move"), pl.lit(0.0)), shock_down_end="t")
    up = mv.sort("coin", "move", "t", descending=[False, True, False]).group_by("coin", maintain_order=True).first(
    ).select("coin", shock_up=pl.max_horizontal(pl.col("move"), pl.lit(0.0)), shock_up_end="t")
    n = mv.group_by("coin").agg(n_obs=pl.len(), first_mark=pl.col("t").min())
    return dn.join(up, on="coin").join(n, on="coin").with_columns(
        horizon_h=pl.lit(horizon_h), asof=pl.lit(asof).dt.cast_time_unit("ms")).sort("coin")


def stress_exposure(marks: pl.DataFrame, hourly: pl.DataFrame, sh: pl.DataFrame, mmr: float = 0.0) -> pl.DataFrame:
    """Per address: typical and peak implied stress loss / equity, the share of exposure without a shock, and
    (ADR-0067) the minimum stressed residual margin headroom 1 - loss / equity - mmr x gross leverage over hours."""
    m = (marks.filter(pl.col("p_m").is_not_null())
         .join(sh.select(pl.col("coin").alias("symbol"), "shock_down", "shock_up"), on="symbol", how="left")
         .with_columns(expo=pl.col("pos").abs() * pl.col("p_m"),
                       shock=pl.when(pl.col("pos") > 0).then("shock_down").otherwise("shock_up")))
    per = m.group_by("trader", "hour_end").agg(
        loss=(pl.col("expo") * pl.col("shock")).sum(), expo=pl.col("expo").sum(),
        unshocked=pl.col("expo").filter(pl.col("shock").is_null()).sum(),
    ).join(hourly.select("trader", "hour_end", "equity_base", "leverage"), on=["trader", "hour_end"],
           how="left").with_columns(
        stress=pl.when(pl.col("equity_base") > 0).then(pl.col("loss") / pl.col("equity_base"))).with_columns(
        headroom=1 - pl.col("stress") - mmr * pl.col("leverage"))
    return per.sort("trader", "hour_end").group_by("trader").agg(  # sorted: float sums in a fixed order
        stress_typical=pl.col("stress").median(), stress_peak=pl.col("stress").max(),
        stress_headroom_min=pl.col("headroom").min(),
        unshocked_exposure_share=pl.when(pl.col("expo").sum() > 0)
        .then(pl.col("unshocked").sum() / pl.col("expo").sum()),
    ).sort("trader")


# ---------------------------------------------------------------------------------------------- drawdowns
def _dd(r: pl.Expr) -> pl.Expr:
    idx = (1 + r).cum_prod()
    return (idx / idx.cum_max().clip(1) - 1).min()


def risk_metrics(hourly: pl.DataFrame, daily: pl.DataFrame, acc: pl.DataFrame, marks: pl.DataFrame,
                 sh: pl.DataFrame, fills: pl.DataFrame, asof: datetime, rules: dict) -> pl.DataFrame:
    r = rules["risk"]
    h = hourly.filter(pl.col("book_ret").is_not_null()).sort("trader", "hour_end").group_by("trader").agg(
        intraday_max_dd=_dd(pl.col("book_ret")),
        hours_valued=pl.len(),
    )
    hu = hourly.group_by("trader").agg(
        hours_active=pl.len(), hours_unpriced=(~pl.col("priced")).sum(),
        unpriced_exposure_share=pl.when(pl.col("exposure_w").sum() > 0)
        .then(pl.col("unpriced_exposure_w").sum() / pl.col("exposure_w").sum()),
        leverage_p95=pl.col("leverage").filter(pl.col("gross_exposure") > 0).quantile(0.95, "nearest"),
        leverage_p99=pl.col("leverage").filter(pl.col("gross_exposure") > 0).quantile(0.99, "nearest"),
        leverage_max=pl.col("leverage").filter(pl.col("gross_exposure") > 0).max(),
    ).with_columns(
        liq_distance_min=pl.when(pl.col("leverage_max") > 0)
        .then(1 / pl.col("leverage_max") - r["maintenance_margin_rate"]),
        liq_distance_p5=pl.when(pl.col("leverage_p95") > 0)
        .then(1 / pl.col("leverage_p95") - r["maintenance_margin_rate"]),
    )
    d = daily.sort("trader", "day").with_columns(
        r3=((pl.col("book_ret").log1p().rolling_sum(3).over("trader")).exp() - 1))
    dd = d.group_by("trader").agg(
        days=pl.len(), days_valued=pl.col("book_ret").is_not_null().sum(),
        worst_day=pl.col("book_ret").min(), worst_3d=pl.col("r3").min(),
        max_dd_book=_dd(pl.col("book_ret").drop_nulls()),
    )
    a = acc.filter("usable").sort("trader", "ts").group_by("trader").agg(
        worst_interval_account=pl.col("r_start").min(), max_dd_account=_dd(pl.col("r_start")),
    )
    f = pit(fills, asof).filter(pl.col("is_perp")).group_by("trader").agg(
        liquidations=pl.col("dir").str.starts_with("Liquidated").sum(),
        adl=(pl.col("dir") == "Auto-Deleveraging").sum(),
        liquidation_first_src_row=pl.col("src_row").filter(pl.col("dir").str.starts_with("Liquidated")).min(),
        adl_first_src_row=pl.col("src_row").filter(pl.col("dir") == "Auto-Deleveraging").min(),
    )
    st = stress_exposure(marks, hourly, sh, float(r["maintenance_margin_rate"]))
    out = (hu.join(h, on="trader", how="left").join(dd, on="trader", how="left").join(a, on="trader", how="full",
                                                                                         coalesce=True)
           .join(f, on="trader", how="left").join(st, on="trader", how="left"))
    return out.with_columns(pl.col("liquidations", "adl").fill_null(0), stress_horizon_h=pl.lit(r["stress_horizon_h"]),
                            maintenance_margin_rate=pl.lit(r["maintenance_margin_rate"]),
                            funding=pl.lit("included")).sort("trader")


def apply_gates(metrics: pl.DataFrame, rules: dict) -> pl.DataFrame:
    """One status column per gate: pass | fail | unmeasured (a missing metric never passes, ADR-0068), a status per
    category (ADR-0067) and `all_gates_pass` over the binding gates. Style gates are diagnostics."""
    g = rules["gates"]

    def gate(col: str, ok: pl.Expr) -> pl.Expr:
        missing = pl.col(col).is_null() | pl.col(col).cast(pl.Float64).is_nan().fill_null(False)
        return (pl.when(missing).then(pl.lit("unmeasured"))
                .when(ok).then(pl.lit("pass")).otherwise(pl.lit("fail")))

    m = metrics
    gates = {
        # data integrity
        "gate_rebuild_fit": pl.when(pl.col("xc_n").fill_null(0) < rules["book"]["min_intervals"])
        .then(pl.lit("unmeasured"))
        .otherwise(gate("within_1pct_lower", pl.col("within_1pct_lower") >= g["min_fit_within_1pct"])),
        "gate_book_account": pl.when(pl.col("xc_flag") == "ok").then(pl.lit("pass"))
        .when(pl.col("xc_flag").str.starts_with("disagree")).then(pl.lit("fail")).otherwise(pl.lit("unmeasured")),
        "gate_unpriced": gate("unpriced_exposure_share",
                              pl.col("unpriced_exposure_share") <= g["max_unpriced_exposure_share"]),
        # evidence sufficiency
        "gate_evidence": gate("rt_closed", pl.col("rt_closed") >= g["min_round_trips"]),
        "gate_active": gate("days_since_fill", pl.col("days_since_fill") <= g["recent_fill_days"]),
        "gate_history": pl.when(pl.col("snapshot_days").is_null() | pl.col("usable_days").is_null())
        .then(pl.lit("unmeasured"))
        .when((pl.col("snapshot_days") >= g["min_snapshot_days"]) & (pl.col("usable_days") >= g["min_usable_days"]))
        .then(pl.lit("pass")).otherwise(pl.lit("fail")),
        # trading style (diagnostic since ADR-0067)
        "gate_hold": gate("median_hold_s", pl.col("median_hold_s") >= g["min_hold_seconds"]),
        "gate_order_rate": gate("orders_per_day", pl.col("orders_per_day") <= g["max_orders_per_day"]),
        "gate_maker": gate("maker_share", pl.col("maker_share") <= g["max_maker_share"]),
        # risk and account safety: historical
        "gate_intraday_dd": gate("intraday_max_dd", pl.col("intraday_max_dd") >= -g["max_intraday_dd"]),
        "gate_worst_day": gate("worst_day", pl.col("worst_day") >= -g["max_worst_day_loss"]),
        "gate_worst_3d": gate("worst_3d", pl.col("worst_3d") >= -g["max_worst_3d_loss"]),
        "gate_max_dd": gate("max_dd_book", pl.col("max_dd_book") >= -g["max_drawdown"]),
        "gate_liquidations": gate("liquidations", pl.col("liquidations") <= g["max_liquidations"]),
        "gate_top_dependence": gate("top_profit_share", pl.col("top_profit_share") <= g["max_top_profit_share"]),
        # position
        "gate_leverage_p95": gate("leverage_p95", pl.col("leverage_p95") <= g["max_leverage_p95"]),
        "gate_liq_distance": gate("liq_distance_min", pl.col("liq_distance_min") >= g["min_liq_distance"]),
        # stress
        "gate_worstcase_dd": gate("wc_max_dd", pl.col("wc_max_dd") >= -g["max_worstcase_dd"]),
        "gate_stress_peak": gate("stress_headroom_min", pl.col("stress_headroom_min") >= g["min_stress_headroom"]),
    }
    m = m.with_columns(**gates)

    def status(cols: tuple[str, ...]) -> pl.Expr:
        return (pl.when(pl.any_horizontal([pl.col(c) == "fail" for c in cols])).then(pl.lit("fail"))
                .when(pl.any_horizontal([pl.col(c) == "unmeasured" for c in cols])).then(pl.lit("unmeasured"))
                .otherwise(pl.lit("pass")))

    m = m.with_columns(**{cat: status(cols) for cat, cols in CATEGORIES.items()})
    return m.with_columns(
        gates_failed=pl.concat_list([pl.when(pl.col(c) == "fail").then(pl.lit(c)) for c in BINDING])
        .list.drop_nulls().list.join(";"),
        gates_unmeasured=pl.concat_list([pl.when(pl.col(c) == "unmeasured").then(pl.lit(c)) for c in BINDING])
        .list.drop_nulls().list.join(";"),
        style_flags=pl.concat_list([pl.when(pl.col(c) != "pass").then(pl.lit(c) + ":" + pl.col(c)) for c in STYLE])
        .list.drop_nulls().list.join(";"),
    ).with_columns(all_gates_pass=(pl.col("gates_failed") == "") & (pl.col("gates_unmeasured") == ""))


# ADR-0067: four categories; the risk category in three subgroups. Style gates are reported, not binding.
DATA_INTEGRITY = ("gate_rebuild_fit", "gate_book_account", "gate_unpriced")
EVIDENCE = ("gate_evidence", "gate_active", "gate_history")
STYLE = ("gate_hold", "gate_order_rate", "gate_maker")
RISK_HISTORICAL = ("gate_intraday_dd", "gate_worst_day", "gate_worst_3d", "gate_max_dd", "gate_liquidations",
                   "gate_top_dependence")
RISK_POSITION = ("gate_leverage_p95", "gate_liq_distance")
RISK_STRESS = ("gate_worstcase_dd", "gate_stress_peak")
CATEGORIES = {
    "cat_data_integrity": DATA_INTEGRITY,
    "cat_evidence": EVIDENCE,
    "cat_style_diagnostic": STYLE,
    "cat_risk_historical": RISK_HISTORICAL,
    "cat_risk_position": RISK_POSITION,
    "cat_risk_stress": RISK_STRESS,
    "cat_risk": RISK_HISTORICAL + RISK_POSITION + RISK_STRESS,
}
BINDING = DATA_INTEGRITY + EVIDENCE + RISK_HISTORICAL + RISK_POSITION + RISK_STRESS
GATE_COLS = [*DATA_INTEGRITY, *EVIDENCE, *STYLE, *RISK_HISTORICAL, *RISK_POSITION, *RISK_STRESS]
CATEGORY_COLS = list(CATEGORIES)


# ---------------------------------------------------------------------------------------------- profiles
def binance_daily_volume(lake_dir: Path, mapping: pl.DataFrame, cutoff: datetime) -> pl.DataFrame:
    """Daily Binance quote volume (USDT = sum close x volume of 1m bars) per Hyperliquid coin, inside validity."""
    from arkstream.refprices import scan_klines

    cut_ns = int(cutoff.timestamp() * 1e9)
    m = mapping.filter(pl.col("valid_from").is_not_null()).select(
        pl.col("hl").alias("coin"), pl.col("binance").alias("symbol"), "valid_from", "valid_to")
    k = (scan_klines(lake_dir).filter(pl.col("ts_known") <= cut_ns)
         .with_columns(day=pl.from_epoch(pl.col("ts_known") - 1, time_unit="ns").dt.date())
         .group_by("symbol", "day").agg(quote_volume=(pl.col("close") * pl.col("volume")).sum())
         .collect(engine="streaming"))
    return (k.join(m, on="symbol", how="inner")
            .filter((pl.col("day") >= pl.col("valid_from")) & (pl.col("day") <= pl.col("valid_to")))
            .select("coin", "symbol", "day", "quote_volume").sort("coin", "day"))


def profiles(fills: pl.DataFrame, rt: pl.DataFrame, traders: pl.DataFrame, volume: pl.DataFrame | None,
             asof: datetime, rules: dict) -> pl.DataFrame:
    p = rules["profile"]
    f = pit(fills, asof).filter(pl.col("eligible") & (pl.col("event_kind") == "trade"))
    act = f.group_by("trader").agg(
        days_since_fill=(pl.lit(asof)-pl.col("ts").max()).dt.total_milliseconds()/86_400_000,
        n_fills=pl.len(), n_orders=pl.col("oid").n_unique(), first_fill=pl.col("ts").min(),
        maker_share=pl.col("is_maker").mean(),
        fee_rate_bps=pl.col("fee").filter(pl.col("fee_token") == "USDC").sum()
        / pl.col("notional").filter(pl.col("fee_token") == "USDC").sum() * 1e4,
        notional=pl.col("notional").sum(),
    ).with_columns(
        active_days=(pl.lit(asof) - pl.col("first_fill")).dt.total_milliseconds() / 86_400_000,
    ).with_columns(
        orders_per_day=pl.when(pl.col("active_days") > 0).then(pl.col("n_orders") / pl.col("active_days")),
        maker_heavy=pl.col("maker_share") > p["maker_heavy_share"],
    )
    closed = rt.filter((pl.col("status") == "closed") & ~pl.col("left_censored"))
    profit = pl.col("net_pnl").clip(lower_bound=0)
    shorts = []
    for cut in rules["gates"].get("short_hold_s", []):
        short = pl.col("hold_s") < cut
        share = pl.when(profit.sum() > 0).then(profit.filter(short).sum() / profit.sum())
        shorts += [share.alias(f"short_profit_share_{cut}s"),
                   pl.col("net_pnl").filter(short).sum().alias(f"short_net_pnl_{cut}s")]
    hold = closed.group_by("trader").agg(
        *shorts,
        median_hold_s=pl.col("hold_s").median(),
        hold_p10_s=pl.col("hold_s").quantile(0.10, "nearest"),
        hold_p25_s=pl.col("hold_s").quantile(0.25, "nearest"))
    labels: pl.Expr = pl.lit(BAND_LABELS[-1])
    for edge, lab in reversed(list(zip(BAND_EDGES_S, BAND_LABELS[:-1], strict=True))):
        labels = pl.when(pl.col("median_hold_s") < edge).then(pl.lit(lab)).otherwise(labels)
    hold = hold.with_columns(hold_band=pl.when(pl.col("median_hold_s").is_not_null()).then(labels))
    lo, hi = p["equity_band_usdc"]
    eq = pit(traders, asof).group_by("trader").agg(median_equity=pl.col("equity").median()).with_columns(
        equity_in_band=(pl.col("median_equity") >= lo) & (pl.col("median_equity") <= hi))
    out = act.join(hold, on="trader", how="left").join(eq, on="trader", how="full", coalesce=True).with_columns(
        # ADR-0067 gate 3 (reported): notional turnover per active day as a multiple of median equity
        turnover_equity_per_day=pl.when((pl.col("active_days") > 0) & (pl.col("median_equity") > 0))
        .then(pl.col("notional") / pl.col("active_days") / pl.col("median_equity")))
    if volume is not None:
        w0 = asof.date() - timedelta(days=int(p["volume_window_days"]))
        v = volume.filter((pl.col("day") >= w0) & (pl.col("day") < asof.date())).group_by("coin").agg(
            median_daily_volume=pl.col("quote_volume").median())
        o = (f.group_by("trader", "oid", "symbol").agg(order_notional=pl.col("notional").sum())
             .join(v.rename({"coin": "symbol"}), on="symbol", how="left")
             .with_columns(impact_bps=pl.col("order_notional") / pl.col("median_daily_volume") * 1e4))
        imp = o.group_by("trader").agg(
            median_order_notional=pl.col("order_notional").median(),
            order_to_volume_bps_median=pl.col("impact_bps").median(),
            order_to_volume_bps_p95=pl.col("impact_bps").quantile(0.95, "nearest"),
            orders_without_volume=pl.col("impact_bps").is_null().sum(),
        )
        out = out.join(imp, on="trader", how="left")
    return out.with_columns(volume_source=pl.lit("binance_usdm_1m_klines" if volume is not None else "none"),
                            asof=pl.lit(asof).dt.cast_time_unit("ms")).sort("trader")
