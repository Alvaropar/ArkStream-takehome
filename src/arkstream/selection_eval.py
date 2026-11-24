"""Phase 4 development walk-forward and baselines (ADR-A0133), market-relative (ADR-A0134) and copy capture (ADR-A0134)
for the selected basket, its sleeves and the baselines.

The rule is applied at an origin with `selection.select_origin` (data up to the origin only); this module then reads
the following test window of the frozen replay, which is an outcome only. Every random draw is seeded; every table is
sorted on a total order.

Basket = equal separate sleeves of the replay allocation (10,000 USDC each), so its return over a window is the mean
of the sleeves' copy returns and its daily return is the change in the summed sleeve equity.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import numpy as np
import polars as pl

from arkstream import selection as S
from arkstream import selection_stats as st
from arkstream.replay_capture import BENCH, MIN_BENCHMARK_SHARE, PARTS, market_relative
from arkstream.replay_market import ms

C = pl.col
SCENARIOS = ("base", "optimistic", "stress")


def test_end(origins: list[date], origin: date) -> date:
    return origins[origins.index(origin) + 1]


def sleeve_outcomes(ctx, origin: date, crash: list[date], ladder: float) -> pl.DataFrame:
    """Per A/B address, the test window's copy return in each scenario, the return without the crash dates (chained
    daily TWR over the other days; null if any other day is missing), stress measurement and the ADR-0055 stress
    check (measured, not exhausted, stress max drawdown no worse than the ladder step)."""
    out = None
    for sc in SCENARIOS:
        d = S.scenario_dir(ctx, origin, "test", sc)
        s = pl.read_parquet(d / "address_summary.parquet", columns=[
            "trader", "copy_return", "measurement", "max_drawdown", "exhausted", "all_gates_pass"])
        daily = pl.read_parquet(d / "daily_copy_twr.parquet", columns=["trader", "day", "daily_twr"])
        ex = daily.filter(~C("day").is_in(crash)).sort("trader", "day").group_by("trader", maintain_order=True).agg(
            ex=pl.when(C("daily_twr").null_count() == 0).then((1 + C("daily_twr")).product() - 1))
        s = s.join(ex, on="trader", how="left")
        cols = [C("copy_return").alias(sc), C("ex").alias(f"{sc}_ex_crash")]
        if sc == "stress":
            cols += [
                (C("measurement") == "measured").alias("stress_measured"),
                pl.when(C("measurement") != "measured").then(pl.lit("fail_unmeasured"))
                .when(C("exhausted") | C("max_drawdown").is_null() | (C("max_drawdown") < ladder))
                .then(pl.lit("fail_loss")).otherwise(pl.lit("pass")).alias("stress_check"),
                C("max_drawdown").alias("stress_max_drawdown"),
            ]
        if sc == "base":
            cols += [C("max_drawdown").alias("base_max_drawdown")]
        part = s.select("trader", *cols)
        out = part if out is None else out.join(part, on="trader", how="full", coalesce=True)
    assert out is not None
    return out.sort("trader")


def basket_daily(ctx, origin: date, scenario: str, traders: list[str], daily: pl.DataFrame | None = None
                 ) -> pl.DataFrame:
    """Summed sleeve equity per day and the basket's daily return (null on a day any sleeve is unvalued). `daily`
    (trader, day, equity) replaces the replay's ledger, e.g. the coin-filtered sleeves (ADR-A0136)."""
    if daily is None:
        d = S.scenario_dir(ctx, origin, "test", scenario)
        daily = pl.read_parquet(d / "daily_copy_twr.parquet", columns=["trader", "day", "equity"])
    daily = daily.select("trader", "day", "equity").filter(C("trader").is_in(traders))
    if not traders:
        return pl.DataFrame(schema={"day": pl.Date, "equity": pl.Float64, "daily_twr": pl.Float64})
    alloc = float(ctx_allocation(ctx)) * len(traders)
    b = daily.sort("day", "trader").group_by("day", maintain_order=True).agg(
        equity=pl.when(C("equity").null_count() == 0).then(C("equity").sum()), n=pl.len()).sort("day")
    return b.with_columns(
        daily_twr=C("equity") / C("equity").shift(1).fill_null(alloc) - 1).select("day", "equity", "daily_twr")


def ctx_allocation(ctx) -> float:
    from arkstream.config import load_yaml

    return float(load_yaml("execution.yaml", ctx.root / "config")["replay"]["allocation_usdc"])


def max_drawdown(equity: np.ndarray, start: float) -> float | None:
    if len(equity) == 0 or not np.isfinite(equity).all():
        return None
    peak = np.maximum.accumulate(np.concatenate([[start], equity]))
    return float((np.concatenate([[start], equity]) / peak - 1).min())


def summarise(x: np.ndarray, trim: float) -> dict[str, float | None]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return {"mean": None, "median": None, "trimmed_mean": None, "n": 0}
    return {"mean": float(x.mean()), "median": float(np.median(x)), "trimmed_mean": st.trimmed_mean(x, trim),
            "n": len(x)}


def random_k(pool: list[str], values: dict[str, float], k: int, draws: int, rng: np.random.Generator
             ) -> tuple[np.ndarray, np.ndarray]:
    """Seeded draws of k addresses without replacement from `pool` (sorted); returns the index matrix and the mean of
    `values` per draw."""
    pool = sorted(pool)
    if k == 0 or len(pool) < k:
        return np.zeros((0, k), dtype=np.int64), np.zeros(0)
    idx = np.stack([rng.choice(len(pool), size=k, replace=False) for _ in range(draws)])
    v = np.array([values[p] for p in pool], dtype=float)
    return idx, v[idx].mean(axis=1)


def evaluate_window(ctx, origin: date, tables: dict[str, pl.DataFrame], outcomes: pl.DataFrame,
                    cfg: dict[str, Any], variant: str, daily: dict[str, pl.DataFrame] | None = None
                    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One development window: the basket against matched random-k, all-A/B random-k, equal weight and cash.
    For the coin-filter variant `outcomes` are the filtered sleeves and `daily` their daily equity per scenario."""
    b = cfg["baselines"]
    trim = float(b["trimmed_share"])
    o = outcomes
    cands = tables["candidates"]
    chosen = S.selected(tables)
    pool = sorted(cands.filter("eligible")["trader"].to_list())
    ab = sorted(cands["trader"].to_list())
    k = len(chosen)
    row: dict[str, Any] = {"origin": origin, "variant": variant, "ab_addresses": len(ab), "eligible_pool": len(pool),
                           "selectable": int(cands["selectable"].sum()), "k": k,
                           "selected": ",".join(chosen)}
    base = dict(o.select("trader", "base").drop_nulls("base").iter_rows())
    pool_m = [p for p in pool if p in base]
    ab_m = [p for p in ab if p in base]
    row["eligible_pool_measured"] = len(pool_m)
    row["ab_measured"] = len(ab_m)
    row["possible_matched_picks"] = math.comb(len(pool_m), k) if len(pool_m) >= k else 0
    row["possible_ab_picks"] = math.comb(len(ab_m), k) if len(ab_m) >= k else 0
    sl = o.filter(C("trader").is_in(chosen))
    for sc in SCENARIOS:
        for suffix in ("", "_ex_crash"):
            col = sc + suffix
            s = summarise(sl[col].to_numpy() if k else np.array([]), trim)
            row[f"basket_{col}"] = s["mean"] if k else 0.0
            row[f"basket_{col}_median"] = s["median"]
            row[f"basket_{col}_trimmed"] = s["trimmed_mean"]
            row[f"basket_{col}_n"] = s["n"]
            e = summarise(o.filter(C("trader").is_in(pool))[col].to_numpy(), trim)
            row[f"equal_weight_{col}"] = e["mean"]
            row[f"equal_weight_{col}_median"] = e["median"]
    row["basket_stress_measured"] = int(sl["stress_measured"].sum()) if k else 0
    row["basket_stress_check_pass"] = int((sl["stress_check"] == "pass").sum()) if k else 0
    row["basket_stress_check_fail_loss"] = int((sl["stress_check"] == "fail_loss").sum()) if k else 0
    row["basket_stress_check_fail_unmeasured"] = int((sl["stress_check"] == "fail_unmeasured").sum()) if k else 0
    alloc = ctx_allocation(ctx)
    for sc in ("base", "stress"):
        bd = basket_daily(ctx, origin, sc, chosen, None if daily is None else daily[sc])
        row[f"basket_{sc}_max_drawdown"] = max_drawdown(bd["equity"].to_numpy(), alloc * k) if k else None
    row["basket_stress_check"] = (
        None if not k else "pass" if (row["basket_stress_measured"] == k and row["basket_stress_max_drawdown"]
                                      is not None and row["basket_stress_max_drawdown"] >= -0.10) else "fail")
    seed = int(b["seed"])
    dist_rows: list[dict[str, Any]] = []
    for name, pl_pool, salt in (("matched_random_k", pool_m, 1), ("ab_random_k", ab_m, 2)):
        for col in ("base", "base_ex_crash", "optimistic", "stress"):
            vals = dict(o.select("trader", col).drop_nulls(col).iter_rows())
            usable = [p for p in pl_pool if p in vals]
            rng = np.random.default_rng([seed, origin.toordinal(), salt])
            idx, means = random_k(usable, vals, k, int(b["draws"]), rng)
            basket = row[f"basket_{col}"]
            d: dict[str, Any] = {"origin": origin, "variant": variant, "baseline": name, "scenario": col, "k": k,
                                 "pool": len(usable), "draws": len(means),
                                 "possible_picks": math.comb(len(usable), k) if len(usable) >= k else 0}
            if len(means):
                d.update(mean=float(means.mean()), median=float(np.median(means)),
                         trimmed_mean=st.trimmed_mean(means, trim), p10=st.quantile(means, 0.1),
                         p90=st.quantile(means, 0.9), basket=basket, basket_percentile=st.percentile_of(basket, means),
                         basket_above_median=bool(basket > float(np.median(means))),
                         distinct_draws=len({tuple(sorted(r.tolist())) for r in idx}))
            dist_rows.append(d)
            if col == "base":
                tag = "matched" if name == "matched_random_k" else "ab"
                row[f"{tag}_rk_median"] = d.get("median")
                row[f"{tag}_rk_mean"] = d.get("mean")
                row[f"{tag}_rk_p10"] = d.get("p10")
                row[f"{tag}_rk_p90"] = d.get("p90")
                row[f"{tag}_percentile"] = d.get("basket_percentile")
                row[f"{tag}_win"] = bool(d.get("basket_above_median", False))
            if col == "base_ex_crash":
                tag = "matched" if name == "matched_random_k" else "ab"
                row[f"{tag}_rk_median_ex_crash"] = d.get("median")
                row[f"{tag}_win_ex_crash"] = bool(d.get("basket_above_median", False))
    row["ranking_testable"] = k > 0 and row["possible_matched_picks"] > 1
    row["cash"] = 0.0
    row["beats_equal_weight"] = (k > 0 and row["equal_weight_base"] is not None
                                 and row["basket_base"] > row["equal_weight_base"])
    return row, dist_rows


def intervals(wins: int, n: int) -> dict[str, float | int]:
    lo, hi = st.clopper_pearson(wins, n)
    lo1, _ = st.clopper_pearson(wins, n, two_sided=False)
    return {"wins": wins, "windows": n, "cp95_lo": lo, "cp95_hi": hi, "cp95_one_sided_lo": lo1}


def mintrl(daily: np.ndarray) -> dict[str, Any]:
    m = st.moments(daily)
    if m is None:
        return {"days": int(np.isfinite(daily).sum()), "sharpe_daily": None}
    sr, skew, kurt = m
    return {"days": int(np.isfinite(daily).sum()), "sharpe_daily": sr, "sharpe_annual": sr * math.sqrt(365),
            "skew": skew, "kurtosis": kurt, "min_trl_days": st.min_track_record(sr, skew, kurt),
            "min_trl_days_half_sharpe": st.min_track_record(sr / 2, skew, kurt)}


# ---------------------------------------------------------------- market-relative (5a) and capture (5b), ADR-A0134


def series_market(ctx, origin: date, end: date, scenario: str, name: str, traders: list[str],
                  daily: pl.DataFrame | None = None) -> dict[str, Any]:
    """Basket-level market-relative row: the basket's return, BTC / ETH buy-and-hold, and the daily alpha / betas of
    the basket's daily return on BTC and ETH (Phase 2's regression)."""
    marks = pl.read_parquet(S.replay_dir(ctx) / "valuation_marks.parquet")
    bd = basket_daily(ctx, origin, scenario, traders, daily)
    if bd.height == 0:
        return {"series": name, "scenario": scenario, "addresses": 0}
    m = market_relative(bd.select(pl.lit(name).alias("trader"), "day", "daily_twr"), marks,
                        ms(S.midnight(origin)), ms(S.midnight(end)))
    r = m.row(0, named=True)
    r.pop("trader")
    r["series"] = name
    r["scenario"] = scenario
    r["addresses"] = len(traders)
    r["return_over_btc"] = (r["copy_return"] - r["btc_buy_hold"]) if r["copy_return"] is not None and r[
        "btc_buy_hold"] is not None else None
    r["return_over_eth"] = (r["copy_return"] - r["eth_buy_hold"]) if r["copy_return"] is not None and r[
        "eth_buy_hold"] is not None else None
    return r


def benchmark_turnover(ctx, origin: date) -> pl.DataFrame:
    d = S.window_dir(ctx, origin, "test") / BENCH
    o = pl.read_parquet(d / "follower_orders.parquet", columns=["trader", "status", "quantity", "fill_px"])
    return o.filter(C("status") == "filled").sort("trader", "quantity", "fill_px").group_by(
        "trader", maintain_order=True).agg(
        benchmark_turnover=(C("quantity").abs() * C("fill_px")).sum()).sort("trader")


def capture_rows(cap: pl.DataFrame, groups: dict[str, list[str]], fee_bps: pl.DataFrame, turnover: pl.DataFrame,
                 allocation: float) -> pl.DataFrame:
    """Capture per sleeve and per group (basket, equal weight) from `capture_summary` rows of one window and scenario.
    A group's ratio is total follower PnL / total benchmark PnL, and its gap parts are sums (they still close to the
    gap). Not meaningful when |benchmark PnL| < 1% of the group's allocation (ADR-0063). The leader-fee benchmark
    subtracts each leader's own fee rate (Phase 2 `fee_rate_bps`) on the benchmark's filled turnover."""
    c = (cap.join(fee_bps, on="trader", how="left").join(turnover, on="trader", how="left")
         .with_columns(C("benchmark_turnover").fill_null(0.0))
         .with_columns(leader_fee=C("fee_rate_bps").fill_null(0.0) * C("benchmark_turnover") / 1e4))
    rows = []
    for name, members in groups.items():
        g = c.filter(C("trader").is_in(members))
        level = "sleeve" if name == "sleeve" else name
        units = [(t, g.filter(C("trader") == t)) for t in sorted(members)] if name == "sleeve" else [(name, g)]
        for label, u in units:
            if u.height == 0:
                continue
            n = u.height
            r: dict[str, Any] = {"level": level, "series": label, "addresses": n,
                                 "follower_pnl": float(u["follower_pnl"].sum()),
                                 "benchmark_pnl": float(u["benchmark_pnl"].sum()),
                                 "leader_return_median": u["leader_return"].median()
                                 if u["leader_return"].drop_nulls().len() else None,
                                 "incomplete": int((u["status"] == "incomplete").sum())}
            for p in (*PARTS, "gap", "closure", "leader_fee"):
                r[p] = float(u[p].sum())
            bench = r["benchmark_pnl"]
            threshold = MIN_BENCHMARK_SHARE * allocation * n
            ok = abs(bench) >= threshold and r["incomplete"] == 0
            r["status"] = "ok" if ok else ("incomplete" if r["incomplete"] else "not_meaningful")
            r["capture_ratio"] = r["follower_pnl"] / bench if ok else None
            lf = bench - r["leader_fee"]
            r["benchmark_leader_fee_pnl"] = lf
            r["capture_ratio_leader_fee"] = r["follower_pnl"] / lf if abs(lf) >= threshold and ok else None
            r["benchmark_won"] = bench > 0
            for p in PARTS:
                r[p + "_share"] = r[p] / bench if ok else None
            rows.append(r)
    return pl.DataFrame(rows, infer_schema_length=None)


def capture_medians(sleeves: pl.DataFrame) -> dict[str, Any]:
    """Median and spread of per-sleeve ratios, separately where the benchmark won and where it lost."""
    out: dict[str, Any] = {}
    s = sleeves.filter(C("status") == "ok")
    for tag, cond in (("won", C("benchmark_won")), ("lost", ~C("benchmark_won"))):
        x = s.filter(cond)["capture_ratio"].to_numpy()
        out[f"n_{tag}"] = len(x)
        out[f"median_{tag}"] = float(np.median(x)) if len(x) else None
        out[f"p25_{tag}"] = st.quantile(x, 0.25) if len(x) else None
        out[f"p75_{tag}"] = st.quantile(x, 0.75) if len(x) else None
    out["not_meaningful"] = int((sleeves["status"] == "not_meaningful").sum())
    return out
