"""Phase 4 v2 copy economics (ADRs 0071, 0077): residual PnL, alpha per unit of gross exposure-time with its
week-clustered standard error, the static-replica decomposition, utilisation and the reported statistic set.

`market_at` fits the origin's factors and coin betas once (90 days before the origin); `window_panel` turns one replay
window into per-coin and per-day residual series; `statistics` computes every address's statistic set on the common
training window; `window_alpha` gives the same alpha on any other window (the flat-start test windows) with the
origin's betas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

from arkstream.selection_v2_market import (
    FACTORS,
    beta_lookup,
    coin_days,
    coin_returns,
    epoch_day,
    factor_returns,
    fit_betas,
    group_sum,
    load_window,
    residual_coin_days,
    scenario_dir,
    trader_days,
    week_index,
    window_bounds,
)
from arkstream.selection_v2_math import norm_ppf, t_ppf

C = pl.col
BPS = 10_000


@dataclass
class Market:
    origin: date
    members: list[str]
    returns: pl.DataFrame
    factors: pl.DataFrame
    betas: pl.DataFrame
    funding_in_alpha: bool = True  # ADR-0084 (config selection_v2.market.funding_in_alpha)


def market_at(ctx, origin: date, marks: pl.DataFrame, members: list[str], extra_coins: list[str] | None = None
              ) -> Market:
    """ADR-0077 items 4-5: the origin's factors (ALT on the pooled tradable set) and betas fitted on the 90 days
    before it. `marks` must not be trusted to end at the origin: everything is cut at the fit window."""
    m = ctx.raw["selection_v2"]["market"]
    returns = coin_returns(marks)
    factors = factor_returns(returns, members)
    betas = fit_betas(returns, factors, origin, coins=extra_coins, lookback=int(m["beta_lookback_days"]),
                      shrink_days=int(m["beta_shrink_days"]), min_fit=int(m["min_fit_days"]))
    return Market(origin, sorted(members), returns, factors, betas, bool(m.get("funding_in_alpha", True)))


def alpha_core(t: np.ndarray, U: np.ndarray, G: np.ndarray, conf: float) -> dict:
    """α = ΣU / ΣG; CR1 week-clustered delta-method SE; s = SE × t_{conf, W-1} / z_conf (ADR-0077 item 7)."""
    out = {"alpha": None, "se_cluster": None, "s": None, "weeks": 0, "days": int(len(t)), "sum_U": float(U.sum()),
           "sum_G": float(G.sum())}
    g = float(G.sum())
    if len(t) == 0 or g <= 0:
        return out
    a = float(U.sum()) / g
    _, inv = np.unique(week_index(t), return_inverse=True)
    w = int(inv.max()) + 1
    out.update(alpha=a, weeks=w)
    if w >= 2:
        s = np.bincount(inv, weights=U - a * G, minlength=w)
        se = math.sqrt(w / (w - 1) * float((s ** 2).sum())) / g
        out.update(se_cluster=se, s=se * t_ppf(conf, w - 1) / norm_ppf(conf))
    return out


def window_panel(tree: Path, origin: date, window: str, start: date, end: date, market: Market,
                 traders: list[str], scenario: str = "base", min_exposure: float = 0.0
                 ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """(ledger, funding, residual coin-days, trader-days) of one replay window over [start, end)."""
    marks = pl.read_parquet(tree / "valuation_marks.parquet")
    f, fund = load_window(tree, origin, window, scenario, end)
    cd = coin_days(f, fund, marks, start, end)
    rc = residual_coin_days(cd, market.betas, market.factors, market.returns, market.funding_in_alpha)
    td = trader_days(rc, traders, start, end, min_exposure)
    return f, fund, rc, td


def replica(rc: pl.DataFrame, td: pl.DataFrame, market: Market) -> pl.DataFrame:
    """ADR-0077 item 8: the static replica's residual PnL per trader on its valid exposed days."""
    ex = td.filter("exposed").select("trader", "t", "G")
    pos = rc.join(ex.select("trader", "t"), on=["trader", "t"], how="semi").filter(C("e") != 0)
    mix = group_sum(pos.sort("trader", "coin", "t"), ["trader", "coin"], {"E": C("e")})
    den = group_sum(mix.sort("trader", "coin"), ["trader"], {"den": C("E").abs()})
    mix = mix.join(den, on="trader", how="left").filter(C("den") > 0).with_columns(
        w=C("E") / C("den")).select("trader", "coin", "w")
    b = beta_lookup(market.betas, mix["coin"].unique().to_list())
    rr = (market.returns.join(b, on="coin", how="inner").join(market.factors.select("t", *FACTORS), on="t",
                                                               how="inner")
          .with_columns(rr=C("r") - sum((C(f"beta_{f}") * C(f) for f in FACTORS), pl.lit(0.0)))
          .select("coin", "t", "rr"))
    x = group_sum(ex.join(mix, on="trader", how="inner").join(rr, on=["coin", "t"], how="left")
                  .sort("trader", "t", "coin"), ["trader", "t"], {"UR": C("G") * C("w") * C("rr")},
                  {"missing": C("rr").is_null().cast(pl.Int64)}).join(ex, on=["trader", "t"], how="left")
    return group_sum(x.filter(C("missing") == 0).sort("trader", "t"), ["trader"],
                     {"replica_U": C("UR"), "replica_G": C("G")}, {"replica_days": pl.lit(1, pl.Int64)})


def nav_stats(daily: pl.DataFrame, start: date, end: date, allocation: float) -> pl.DataFrame:
    """Raw NAV return, geometric mean daily, volatility, max drawdown and 95% ES over [start, end) from the replay's
    daily NAV (`daily_copy_twr`)."""
    rows = []
    d = daily.filter(C("day") < end).sort("trader", "day")
    for (trader,), g in d.group_by("trader", maintain_order=True):
        before = g.filter(C("day") < start)
        w = g.filter(C("day") >= start)
        e0 = before["equity"][-1] if before.height else allocation
        eq = w["equity"].to_numpy().astype(float)
        r = w["daily_twr"].drop_nulls().to_numpy().astype(float)
        ok = e0 is not None and w.height > 0 and bool(np.isfinite(eq).all())
        ret = float(eq[-1] / e0 - 1) if ok else None
        geo = float((1 + ret) ** (1 / w.height) - 1) if ok and ret is not None and ret > -1 else None
        path = np.concatenate([[e0], eq]) if ok else None
        mdd = float((path / np.maximum.accumulate(path) - 1).min()) if path is not None else None
        es = float(r[r <= np.quantile(r, 0.05)].mean()) if len(r) >= 2 else None
        rows.append((trader, ret, geo, float(r.std(ddof=1)) if len(r) >= 2 else None, mdd, es, len(r)))
    return pl.DataFrame(rows, schema={"trader": pl.String, "nav_return": pl.Float64, "nav_geo_daily": pl.Float64,
                                      "nav_vol_daily": pl.Float64, "nav_max_drawdown": pl.Float64,
                                      "nav_es95_daily": pl.Float64, "nav_valid_days": pl.Int64}, orient="row")


def per_trader(td: pl.DataFrame, rc: pl.DataFrame, conf: float, allocation: float, min_days: int,
               min_weeks: int, funding_in_alpha: bool = True) -> pl.DataFrame:
    """α, s, measurability, IR, utilisation, residual return on NAV, CT, top-3 coin-day share, copy betas."""
    rows = []
    ex_days = td.filter("exposed").select("trader", "t")
    top = (rc.join(ex_days, on=["trader", "t"], how="semi").filter(C("U").is_not_null())
           .sort("trader", "U", "coin", "t", descending=[False, True, False, False])
           .group_by("trader", maintain_order=True).agg(top3=C("U").head(3).sum()))
    top_map = dict(top.rows())
    betas = group_sum(rc.join(ex_days, on=["trader", "t"], how="semi").sort("trader", "t", "coin"), ["trader"],
                      {f"eb_{f}": C("e") * C(f"beta_{f}") for f in FACTORS})
    beta_map = {r[0]: r[1:] for r in betas.rows()}
    for (trader,), g in td.group_by("trader", maintain_order=True):
        valid = g["valid"].to_numpy()
        G_all = g["G"].to_numpy().astype(float)
        ex = g["exposed"].to_numpy()
        t = g["t"].to_numpy()[ex]
        U = g["U"].to_numpy().astype(float)[ex]
        G = G_all[ex]
        P = g["pnl"].to_numpy().astype(float)[ex]
        F = g["F"].to_numpy().astype(float)[ex]
        core = alpha_core(t, U, G, conf)
        # ADRs 0083, 0084: α with and without funding are both reported; `U` (binding) follows the config
        exf = core if not funding_in_alpha else alpha_core(t, U - F, G, conf)
        inc = core if funding_in_alpha else alpha_core(t, U + F, G, conf)
        weeks = core["weeks"]
        measured = int(ex.sum()) >= min_days and weeks >= min_weeks
        status = "ok" if measured else ("too_few_exposed_days" if int(ex.sum()) < min_days
                                        else "too_few_exposed_weeks")
        flat = valid & ~ex
        pnl_flat = float(np.nansum(g["pnl"].to_numpy().astype(float)[flat]))
        gv = G_all[valid]
        ir = float(U.mean() / U.std(ddof=1)) if len(U) >= 2 and U.std(ddof=1) > 0 else None
        su = core["sum_U"]
        eb = beta_map.get(trader)
        sg = core["sum_G"]
        rows.append({
            "trader": trader, "measured": measured, "measure_status": status,
            "window_days": int(len(valid)), "valid_days": int(valid.sum()), "days_invalid": int((~valid).sum()),
            "exposed_days": int(ex.sum()), "exposed_weeks": weeks,
            "sum_U": su, "sum_G": sg, "sum_pnl": float(P.sum()),
            "alpha": core["alpha"], "se_cluster": core["se_cluster"], "s": core["s"],
            "alpha_funding": float(F.sum()) / sg if sg > 0 else None,
            "alpha_ex_funding": exf["alpha"], "s_ex_funding": exf["s"],
            "alpha_incl_funding": inc["alpha"], "s_incl_funding": inc["s"],
            "carry_book": bool(inc["alpha"] is not None and inc["alpha"] > 0 and sg > 0
                               and float(F.sum()) / sg >= inc["alpha"] / 2),
            "t_stat": core["alpha"] / core["s"] if core["alpha"] is not None and core["s"] else None,
            "info_ratio": ir,
            "util_mean": float(gv.mean() / allocation) if len(gv) else None,
            "util_p50": float(np.quantile(gv, 0.5) / allocation) if len(gv) else None,
            "util_p95": float(np.quantile(gv, 0.95) / allocation) if len(gv) else None,
            "resid_nav_daily": su / (allocation * int(valid.sum())) if valid.sum() else None,
            "ct_total": float(P.sum()) / sg if sg > 0 else None,
            "pnl_flat_days": pnl_flat,
            "top3_coinday_share": top_map.get(trader) / su if su > 0 and trader in top_map else None,
            **{f"copy_beta_{f}": (eb[i] / sg if eb is not None and sg > 0 else None) for i, f in enumerate(FACTORS)},
        })
    schema = {"trader": pl.String, "measured": pl.Boolean, "measure_status": pl.String, "window_days": pl.Int64,
              "valid_days": pl.Int64, "days_invalid": pl.Int64, "exposed_days": pl.Int64, "exposed_weeks": pl.Int64,
              "sum_U": pl.Float64, "sum_G": pl.Float64, "sum_pnl": pl.Float64, "alpha": pl.Float64,
              "se_cluster": pl.Float64, "s": pl.Float64, "alpha_funding": pl.Float64, "alpha_ex_funding": pl.Float64,
              "s_ex_funding": pl.Float64, "alpha_incl_funding": pl.Float64, "s_incl_funding": pl.Float64,
              "carry_book": pl.Boolean, "t_stat": pl.Float64, "info_ratio": pl.Float64,
              "util_mean": pl.Float64, "util_p50": pl.Float64, "util_p95": pl.Float64, "resid_nav_daily": pl.Float64,
              "ct_total": pl.Float64, "pnl_flat_days": pl.Float64, "top3_coinday_share": pl.Float64,
              **{f"copy_beta_{f}": pl.Float64 for f in FACTORS}}
    return pl.DataFrame(rows, schema=schema).sort("trader")


def exposure_profile(rc: pl.DataFrame, td: pl.DataFrame) -> pl.DataFrame:
    """Mean signed start-of-day exposure by coin over the valid window days (flat days count as 0)."""
    n = td.group_by("trader").agg(n=C("valid").sum())
    v = rc.join(td.filter("valid").select("trader", "t"), on=["trader", "t"], how="semi").filter(C("e") != 0)
    p = (group_sum(v.sort("trader", "coin", "t"), ["trader", "coin"], {"E": C("e")})
         .join(n, on="trader").with_columns(mean_exposure_usdc=C("E") / C("n")).sort("trader", "coin"))
    return p.group_by("trader", maintain_order=True).agg(
        exposure_by_coin=pl.struct(C("coin"), C("mean_exposure_usdc")))


def window_trips(f: pl.DataFrame, fund: pl.DataFrame, start: date, end: date) -> pl.DataFrame:
    """Completed copy trips opened and closed inside [start, end) (`selection.follower_trips`)."""
    from arkstream.selection import follower_trips

    s, e = epoch_day(start) * 86_400_000, epoch_day(end) * 86_400_000
    return follower_trips(f, fund).filter(C("open_ms").is_between(s, e - 1) & C("close_ms").is_between(s, e - 1))


def training_extras(tree: Path, origin: date, band_min: int) -> pl.DataFrame:
    """Reported beside the statistic (ADR-0077 item 9): training summaries, capture, market-relative, hold band."""
    def summ(sc: str, cols: dict[str, str]) -> pl.DataFrame:
        s = pl.read_parquet(scenario_dir(tree, origin, "training", sc) / "address_summary.parquet")
        return s.select("trader", **{v: C(k) for k, v in cols.items()})

    base = pl.read_parquet(scenario_dir(tree, origin, "training", "base") / "address_summary.parquet").select(
        "trader", "hold_band", "return_source", train_copy_return="copy_return",
        train_max_drawdown="max_drawdown", break_even_delay_status="break_even_delay_status",
        break_even_delay_lo_ms="break_even_delay_lo_ms",
        train_fill_rate=pl.when(C("orders") > 0).then(C("filled") / C("orders")),
        train_max_copy_leverage="max_leverage", train_excluded_share="excluded_share")
    stress = summ("stress", {"copy_return": "train_stress_return", "max_drawdown": "train_stress_max_drawdown",
                             "measurement": "train_stress_measurement"})
    opt = summ("optimistic", {"copy_return": "train_optimistic_return"})
    cap = pl.read_parquet(tree / "capture_summary.parquet").filter(
        (C("origin") == origin) & (C("window") == "training") & (C("scenario") == "base")).select(
        "trader", capture_status="status", capture_ratio="capture_ratio", capture_gap="gap",
        **{f"gap_{p}_share": C(f"{p}_share") for p in ("fees", "half_spread", "impact", "delay_drift",
                                                         "not_executed_uncopyable_coin")})
    mr = pl.read_parquet(tree / "market_relative.parquet").filter(
        (C("origin") == origin) & (C("window") == "training") & (C("scenario") == "base")).select(
        "trader", btceth_alpha="alpha", btceth_beta_btc="beta_btc", btceth_beta_eth="beta_eth",
        btceth_n_days="n_days")
    bands = pl.read_parquet(scenario_dir(tree, origin, "training", "base") / "band_break_even.parquet").select(
        "hold_band", band_net_bps="net_bps", band_completed="completed")
    return (base.join(stress, on="trader", how="left").join(opt, on="trader", how="left")
            .join(cap, on="trader", how="left").join(mr, on="trader", how="left")
            .join(bands, on="hold_band", how="left")
            .with_columns(hold_band_diagnostic=pl.when(C("band_net_bps").is_null()).then(pl.lit("unmeasured"))
                          .when((C("band_net_bps") > 0) & (C("band_completed") >= band_min)).then(pl.lit("pass"))
                          .otherwise(pl.lit("fail")))).sort("trader")


def statistics(ctx, origin: date, tree: Path, market: Market) -> tuple[pl.DataFrame, pl.DataFrame,
                                                                       pl.DataFrame, pl.DataFrame]:
    """(statistics, residual_daily, residual coin-days, window trips) on the common training window at `origin`."""
    v2 = ctx.raw["selection_v2"]
    alloc = float(v2["sleeve_usdc"])
    start, end = window_bounds(origin, date.fromisoformat(v2["first_priced_day"]), int(v2["window_weeks"]))
    universe = pl.read_parquet(tree / f"origin={origin}" / "window=training" / "universe.parquet")
    traders = universe["trader"].to_list()
    f, fund, rc, td = window_panel(tree, origin, "training", start, end, market, traders,
                                   min_exposure=float(v2["min_exposure_usdc"]))
    conf = float(v2["evidence"]["category_conf"])
    stats = per_trader(td, rc, conf, alloc, int(v2["min_exposed_days"]), int(v2["min_exposed_weeks"]),
                       market.funding_in_alpha)
    rep = replica(rc, td, market)
    daily = pl.read_parquet(scenario_dir(tree, origin, "training", "base") / "daily_copy_twr.parquet",
                            columns=["trader", "day", "equity", "daily_twr"])
    trips = window_trips(f, fund, start, end)
    tstats = group_sum(trips.sort("trader", "pnl", "coin", "trip"), ["trader"],
                       {"pnl_sum": C("pnl"), "peak_sum": C("peak")}, {"trips": pl.lit(1, pl.Int64)}).select(
        "trader", "trips", trip_expectancy=C("pnl_sum") / C("trips"),
        trip_pnl_per_peak=pl.when(C("peak_sum") > 0).then(C("pnl_sum") / C("peak_sum")))
    band_min = int(ctx.raw["selection"]["gates"]["band_min_completed"])
    out = (stats.join(rep, on="trader", how="left")
           .with_columns(alpha_static=pl.when(C("replica_G") > 0).then(C("replica_U") / C("replica_G")))
           .with_columns(alpha_timing=C("alpha") - C("alpha_static"))
           .join(nav_stats(daily, start, end, alloc), on="trader", how="left")
           .join(tstats, on="trader", how="left").with_columns(C("trips").fill_null(0))
           .join(exposure_profile(rc, td), on="trader", how="left")
           .join(training_extras(tree, origin, band_min), on="trader", how="left")
           .with_columns(origin=pl.lit(origin), window_start=pl.lit(start), window_end=pl.lit(end - timedelta(days=1)),
                         alpha_bps=C("alpha") * BPS, s_bps=C("s") * BPS))
    resid = td.select("trader", "t", "day", "pnl", "U", "F", "G", "G_start", "G_end", "net", "valid",
                      "exposed").with_columns(
        origin=pl.lit(origin))
    return out.sort("trader"), resid, rc, trips


def window_alpha(ctx, origin: date, tree: Path, window: str, start: date, end: date, market: Market,
                 traders: list[str], crash: list[date] | None = None) -> pl.DataFrame:
    """The same α (and its exposed days) on another window with the origin's betas; with and without `crash` days.
    An outcome α needs only Σ G > 0 (ADR-0078)."""
    conf = float(ctx.raw["selection_v2"]["evidence"]["category_conf"])
    _, _, rc, td = window_panel(tree, origin, window, start, end, market, traders,
                                min_exposure=float(ctx.raw["selection_v2"]["min_exposure_usdc"]))
    cr = {epoch_day(d) for d in (crash or [])}
    rows = []
    for (trader,), g in td.group_by("trader", maintain_order=True):
        ex = g["exposed"].to_numpy()
        t = g["t"].to_numpy()[ex]
        U = g["U"].to_numpy().astype(float)[ex]
        G = g["G"].to_numpy().astype(float)[ex]
        core = alpha_core(t, U, G, conf)
        keep = ~np.isin(t, list(cr))
        ex_core = alpha_core(t[keep], U[keep], G[keep], conf)
        rows.append((trader, core["alpha"], core["sum_U"], core["sum_G"], int(ex.sum()), ex_core["alpha"],
                     ex_core["sum_U"], ex_core["sum_G"], int((~g["valid"].to_numpy()).sum())))
    schema = {"trader": pl.String, "alpha": pl.Float64, "sum_U": pl.Float64, "sum_G": pl.Float64,
              "exposed_days": pl.Int64, "alpha_ex_crash": pl.Float64, "sum_U_ex_crash": pl.Float64,
              "sum_G_ex_crash": pl.Float64, "days_invalid": pl.Int64}
    return pl.DataFrame(rows, schema=schema, orient="row").sort("trader")
