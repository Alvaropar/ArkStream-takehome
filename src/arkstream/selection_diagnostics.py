"""Phase 4 pre-registered diagnostics (brief item 5c, ADR-0135). They inform the rule; only the gates, the key, the
clusters and the walk select. Predictors come from data up to each development origin, outcomes from the following
test window (frozen replay, base), across all A/B addresses unless stated. One table each in
research/selection/diagnostics/.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import polars as pl

from arkstream import selection as S
from arkstream import selection_stats as st
from arkstream.replay_market import DAY, midnight, ms

C = pl.col
SCREEN = ("median_hold_s", "maker_share", "orders_per_day", "leverage_p95", "wc_max_dd", "alpha", "beta_btc",
          "train_capture_ratio", "train_median_sweep_bps", "train_parameterised_share", "trips")
GATES = (*S.PHASE2_GATES, *S.SELECTION_GATES)


def hit_rate(pred: np.ndarray, out: np.ndarray) -> tuple[float | None, int]:
    """Share of the top quintile by `pred` whose outcome is above the median outcome (pairs with both finite)."""
    ok = np.isfinite(pred) & np.isfinite(out)
    p, o = pred[ok], out[ok]
    if len(p) < 5:
        return None, 0
    top = p >= np.quantile(p, 0.8)
    return float((o[top] > np.median(o)).mean()), int(top.sum())


def predictor_frame(ctx, origin: date, cands: pl.DataFrame, outcomes: pl.DataFrame) -> pl.DataFrame:
    """Candidates at the origin with training-window predictors and the test-window outcome (base)."""
    cap = pl.read_parquet(S.replay_dir(ctx) / "capture_summary.parquet").filter(
        (C("origin") == origin) & (C("window") == "training") & (C("scenario") == "base"))
    cap = cap.select("trader", train_capture_ratio=pl.when(C("status") == "ok").then(C("capture_ratio")))
    o = pl.read_parquet(S.scenario_dir(ctx, origin, "training", "base") / "follower_orders.parquet",
                        columns=["trader", "status", "sweep_bps"])
    sweep = o.filter(C("status") == "filled").group_by("trader").agg(train_median_sweep_bps=C("sweep_bps").median())
    return (cands.join(cap, on="trader", how="left").join(sweep, on="trader", how="left")
            .join(outcomes.select("trader", test_base="base", test_base_max_drawdown="base_max_drawdown"),
                  on="trader", how="left"))


def persistence(frames: dict[date, pl.DataFrame]) -> pl.DataFrame:
    rows = []
    for origin, f in frames.items():
        for pred in ("key", "mean_net", "train_copy_return"):
            x, y = f[pred].cast(pl.Float64).to_numpy(), f["test_base"].cast(pl.Float64).to_numpy()
            h, ntop = hit_rate(x, y)
            rows.append({"origin": origin, "predictor": pred, "n": int((np.isfinite(x) & np.isfinite(y)).sum()),
                         "spearman": st.spearman(x, y), "top_quintile_hit_rate": h, "top_quintile_n": ntop})
    return pl.DataFrame(rows, infer_schema_length=None).sort("origin", "predictor")


def feature_screen(frames: dict[date, pl.DataFrame]) -> pl.DataFrame:
    rows = []
    for origin, f in frames.items():
        for feat in SCREEN:
            x, y = f[feat].cast(pl.Float64).to_numpy(), f["test_base"].cast(pl.Float64).to_numpy()
            h, ntop = hit_rate(x, y)
            rows.append({"origin": origin, "feature": feat, "n": int((np.isfinite(x) & np.isfinite(y)).sum()),
                         "spearman": st.spearman(x, y), "top_quintile_hit_rate": h, "top_quintile_n": ntop})
    return pl.DataFrame(rows, infer_schema_length=None).sort("origin", "feature")


def gate_audit(frames: dict[date, pl.DataFrame]) -> pl.DataFrame:
    parts = []
    for origin, f in frames.items():
        g = f.with_columns(all_gates_pass=pl.when("all_gates_pass").then(pl.lit("pass")).otherwise(pl.lit("fail")),
                           eligible=pl.when("eligible").then(pl.lit("pass")).otherwise(pl.lit("fail")))
        for gate in (*GATES, "all_gates_pass", "eligible"):
            parts.append(g.group_by(C(gate).alias("status")).agg(
                n=pl.len(), measured=C("test_base").count(), mean_return=C("test_base").mean(),
                median_return=C("test_base").median(), positive=(C("test_base") > 0).sum(),
                mean_max_drawdown=C("test_base_max_drawdown").mean(),
                median_max_drawdown=C("test_base_max_drawdown").median(),
            ).with_columns(origin=pl.lit(origin), gate=pl.lit(gate)))
    df = pl.concat(parts)
    pooled = df.group_by("gate", "status").agg(origin=pl.lit(None, pl.Date), n=C("n").sum(),
                                               measured=C("measured").sum(), positive=C("positive").sum(),
                                               mean_return=(C("mean_return") * C("measured")).sum()
                                               / C("measured").sum())
    return pl.concat([df, pooled], how="diagonal_relaxed").select(
        "origin", "gate", "status", "n", "measured", "positive", "mean_return", "median_return", "mean_max_drawdown",
        "median_max_drawdown").sort("gate", "origin", "status", nulls_last=True)


def btc_weeks(marks: pl.DataFrame) -> pl.DataFrame:
    b = marks.filter(C("coin") == "BTC").sort("boundary").select(
        "boundary", "mark", week=(C("boundary") + st.WEEK_OFFSET_DAYS) // 7)
    w = b.group_by("week", maintain_order=True).agg(first=C("mark").first(), last=C("mark").last())
    return w.with_columns(btc_week_return=C("last") / C("first") - 1).select("week", "btc_week_return")


def attribution(ctx, origin: date, end: date, cands: pl.DataFrame, crash: list[date]) -> pl.DataFrame:
    """Completed test-window follower trips (base, all A/B): PnL by coin group, side, holding band, leader order
    size and market regime (crash days, else the sign of BTC's return over the trip's closing calendar week)."""
    f, fund = S.load_ledger(ctx, origin, "test", "base", ms(midnight(end)))
    trips = S.follower_trips(f, fund)
    marks = pl.read_parquet(S.replay_dir(ctx) / "valuation_marks.parquet")
    weeks = btc_weeks(marks)
    crash_days = [d.toordinal() - date(1970, 1, 1).toordinal() for d in crash]
    t = (trips.join(cands.select("trader", "hold_band", "eligible"), on="trader", how="left")
         .with_columns(close_day=C("close_ms") // DAY, week=(C("close_ms") // DAY + st.WEEK_OFFSET_DAYS) // 7)
         .join(weeks, on="week", how="left")
         .with_columns(
            coin_group=pl.when(C("coin").is_in(list(S.FOUR))).then(pl.lit("BTC/ETH/HYPE/SOL"))
            .otherwise(pl.lit("other")),
            size_bucket=pl.when(C("entry_leader_notional") < 1e4).then(pl.lit("<10k"))
            .when(C("entry_leader_notional") < 1e5).then(pl.lit("10k-100k"))
            .when(C("entry_leader_notional") < 1e6).then(pl.lit("100k-1M")).otherwise(pl.lit(">=1M")),
            regime=pl.when(C("close_day").is_in(crash_days)).then(pl.lit("10-11 Oct"))
            .when(C("btc_week_return") >= 0).then(pl.lit("BTC up week"))
            .when(C("btc_week_return") < 0).then(pl.lit("BTC down week")).otherwise(pl.lit("unknown"))))
    parts = []
    for dim in ("coin_group", "side", "hold_band", "size_bucket", "regime"):
        for scope, frame in (("all_ab", t), ("eligible", t.filter("eligible"))):
            parts.append(frame.group_by(C(dim).alias("value")).agg(
                trips=pl.len(), addresses=C("trader").n_unique(), pnl_usdc=C("pnl").sum(),
                net_bps_per_trip=C("net").mean() * 1e4, peak_notional=C("peak").sum(),
            ).with_columns(dimension=pl.lit(dim), scope=pl.lit(scope)))
    return pl.concat(parts).with_columns(origin=pl.lit(origin)).select(
        "origin", "scope", "dimension", "value", "trips", "addresses", "pnl_usdc", "net_bps_per_trip",
        "peak_notional").sort("origin", "scope", "dimension", "value", nulls_last=True)


def capture_drivers(frames: dict[date, pl.DataFrame]) -> pl.DataFrame:
    rows = []
    for origin, f in frames.items():
        y = f["train_capture_ratio"].cast(pl.Float64).to_numpy()
        for feat in (s for s in SCREEN if s != "train_capture_ratio"):
            x = f[feat].cast(pl.Float64).to_numpy()
            rows.append({"origin": origin, "trait": feat, "n": int((np.isfinite(x) & np.isfinite(y)).sum()),
                         "spearman_with_training_capture": st.spearman(x, y)})
    return pl.DataFrame(rows, infer_schema_length=None).sort("origin", "trait")


def alpha_beta(ctx, origin: date, cands: pl.DataFrame, chosen: list[str]) -> pl.DataFrame:
    m = pl.read_parquet(S.replay_dir(ctx) / "market_relative.parquet").filter(
        (C("origin") == origin) & (C("window") == "test") & (C("scenario") == "base"))
    m = m.join(cands.select("trader", "eligible"), on="trader", how="left")
    rows = []
    for scope, frame in (("all_ab", m), ("eligible", m.filter("eligible")),
                         ("selected", m.filter(C("trader").is_in(chosen)))):
        fr = frame.filter(C("r_squared").is_not_null())
        rows.append({"origin": origin, "scope": scope, "addresses": frame.height, "fitted": fr.height,
                     "median_r_squared": fr["r_squared"].median(), "share_r_squared_above_0_5":
                     (fr["r_squared"] > 0.5).cast(pl.Float64).mean() if fr.height else None,
                     "median_abs_beta_btc": fr["beta_btc"].abs().median(),
                     "median_abs_beta_eth": fr["beta_eth"].abs().median(),
                     "alpha_ci_excludes_zero": int(((fr["alpha_lo"] > 0) | (fr["alpha_hi"] < 0)).sum())})
    return pl.DataFrame(rows, infer_schema_length=None)


def effective_bets(daily: pl.DataFrame, traders: list[str]) -> tuple[float | None, int]:
    """(sum of eigenvalues)^2 / sum of squared eigenvalues of the daily copy-return correlation matrix, over days on
    which every address has a return; None with fewer than 2 addresses or 10 days."""
    if len(traders) < 2:
        return (1.0 if traders else None), 0
    w = (daily.filter(C("trader").is_in(traders)).drop_nulls("daily_twr")
         .pivot(on="trader", index="day", values="daily_twr").drop_nulls().sort("day"))
    cols = [t for t in sorted(traders) if t in w.columns]
    if w.height < 10 or len(cols) < 2:
        return None, w.height
    x = w.select(cols).to_numpy()
    x = x[:, x.std(axis=0) > 0]
    if x.shape[1] < 2:
        return None, w.height
    lam = np.linalg.eigvalsh(np.corrcoef(x, rowvar=False))
    return float(lam.sum() ** 2 / (lam**2).sum()), w.height


def crowding(origin: date, data: S.OriginData, pool: list[str], chosen: list[str]) -> pl.DataFrame:
    p = data.positions.filter(C("trader").is_in(pool)).with_columns(sign=C("exposure").sign())
    slots = p.group_by("coin", "boundary", "sign").agg(n=C("trader").n_unique())
    held = p.select("coin", "boundary").unique().height
    shared = slots.filter(C("n") >= 2).select("coin", "boundary").unique().height
    rows = []
    for scope, members in (("eligible", pool), ("selected", chosen)):
        eff, days = effective_bets(data.daily, members)
        rows.append({"origin": origin, "scope": scope, "addresses": len(members), "effective_bets": eff,
                     "common_days": days,
                     "share_slots_same_direction": (shared / held if held else None) if scope == "eligible" else None,
                     "held_slots": held if scope == "eligible" else None})
    return pl.DataFrame(rows, infer_schema_length=None)


def tail(origin: date, data: S.OriginData, cands: pl.DataFrame, crash: list[date]) -> pl.DataFrame:
    pool = cands.filter("eligible").select("trader", "key", "best_block_share")
    d = data.daily.filter(C("trader").is_in(pool["trader"].to_list())).with_columns(
        week=(C("day").cast(pl.Int64) + st.WEEK_OFFSET_DAYS) // 7)
    crash_r = d.filter(C("day").is_in(crash)).sort("trader", "day").group_by("trader", maintain_order=True).agg(
        crash_return=pl.when(C("daily_twr").null_count() == 0).then((1 + C("daily_twr")).product() - 1),
        crash_days=pl.len())
    weekly = (d.sort("trader", "day").group_by("trader", "week", maintain_order=True)
              .agg(r=(1 + C("daily_twr")).product() - 1).group_by("trader", maintain_order=True).agg(
        worst_week=C("r").min(), best_week=C("r").max(), weeks=pl.len()))
    return (pool.join(crash_r, on="trader", how="left").join(weekly, on="trader", how="left")
            .with_columns(origin=pl.lit(origin)).sort("trader"))


def decay(frames: dict[date, pl.DataFrame]) -> pl.DataFrame:
    origins = sorted(frames)
    rows: list[dict[str, Any]] = []
    for i, o in enumerate(origins):
        f = frames[o].filter(C("key").is_not_null())
        if f.height < 5:
            continue
        cut = float(np.quantile(f["key"].to_numpy(), 0.8))
        top = f.filter(C("key") >= cut)["trader"].to_list()
        for later in origins[i:]:
            g = frames[later]
            x = g.filter(C("trader").is_in(top))["test_base"].drop_nulls()
            rows.append({"ranked_at": o, "test_origin": later, "top_quintile": len(top), "present": x.len(),
                         "mean_return": x.mean(), "median_return": x.median(),
                         "all_ab_median_return": g["test_base"].median()})
    return pl.DataFrame(rows, infer_schema_length=None)
