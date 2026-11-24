"""Phase 5 step P5-2: the risk model fitted once per origin (ADR-0088 item 2, ADR-0095 item 4).

Per origin, written to `research/risk_model/origin=<date>/`:

* `stress_shocks.parquet`: per coin, the largest fall (`shock_down`, applied to longs) and rise (`shock_up`, applied
  to shorts) of P(t) / P(t - 24 h) at hour marks over the history expanding from 1 Jul 2025 to the origin. This is
  the Phase 2 table of ADR-0017 (`research/leader/origin=<date>/stress_shocks.parquet`, `leader_risk.shocks`), read
  as published. A tradable coin without a shock takes the largest shock of its ADR-0053 liquidity bucket (latest
  completed 4h Hyperliquid volume at the origin); `source` says which;
* `betas.parquet`: the single-factor BTC beta of each coin's daily Hyperliquid return, OLS with intercept on the 90
  days before the origin, at least 10 days, shrunk toward the cross-coin median with weight n / (n + 30), BTC = 1
  (P3's BTC-equivalent beta; ADR-0077 fit rules);
* `covariance.parquet` (long form) and `covariance_info.json`: Ledoit-Wolf constant-correlation shrinkage (ADR-0079)
  on the origin's pooled tradable coins over the 90 days before it. **Reporting only:** no limit uses it.

Everything uses data before the origin only; a planted later move must not change any output (the leak test).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

from arkstream.replay_market import liquidity_bucket
from arkstream.selection_v2_comove import risk_cov
from arkstream.selection_v2_market import coin_returns, epoch_day

C = pl.col
DEFAULT_OUT = "research/risk_model"
BAR_MS = 4 * 3_600_000


def origin_buckets(bars: pl.DataFrame, origin: date, edges) -> pl.DataFrame:
    """ADR-0053 bucket of each coin's latest completed 4h bar strictly before the origin (bar closes <= origin)."""
    o_ms = epoch_day(origin) * 86_400_000
    last = (bars.filter(C("bar_ms") + BAR_MS <= o_ms).sort("coin", "bar_ms")
            .group_by("coin", maintain_order=True).last().select("coin", "bar_volume_usdc"))
    return last.with_columns(liq_bucket=liquidity_bucket(C("bar_volume_usdc"), edges))


def shock_table(shocks: pl.DataFrame, coins: list[str], buckets: pl.DataFrame, origin: date) -> pl.DataFrame:
    """Own shock where the expanding history has one, else the bucket's largest (never a smaller one)."""
    want = pl.DataFrame({"coin": sorted(set(coins) | set(shocks["coin"]))}, schema={"coin": pl.String})
    own = shocks.select("coin", "shock_down", "shock_up", "n_obs", "first_mark")
    x = want.join(own, on="coin", how="left").join(buckets.select("coin", "liq_bucket"), on="coin", how="left")
    x = x.with_columns(C("liq_bucket").fill_null("unknown"))
    by_bucket = (x.filter(C("shock_down").is_not_null()).group_by("liq_bucket")
                 .agg(bucket_down=C("shock_down").max(), bucket_up=C("shock_up").max()))
    overall = x.select(all_down=C("shock_down").max(), all_up=C("shock_up").max())
    x = x.join(by_bucket, on="liq_bucket", how="left").join(overall, how="cross")
    has = C("shock_down").is_not_null() & C("shock_up").is_not_null()
    return x.select(
        "coin",
        shock_down=pl.when(has).then("shock_down").otherwise(pl.coalesce("bucket_down", "all_down")),
        shock_up=pl.when(has).then("shock_up").otherwise(pl.coalesce("bucket_up", "all_up")),
        source=pl.when(has).then(pl.lit("own_expanding_24h")).otherwise(pl.lit("bucket_max")),
        liq_bucket="liq_bucket",
        n_obs="n_obs",
        first_mark="first_mark",
        origin=pl.lit(origin),
    ).sort("coin")


def btc_betas(returns: pl.DataFrame, origin: date, coins: list[str], lookback: int = 90, min_days: int = 10,
              shrink_k: int = 30) -> pl.DataFrame:
    """Single-factor beta on BTC (P3, ADR-0088 item 2) with the ADR-0077 fit rules."""
    o = epoch_day(origin)
    r = returns.filter(C("t").is_between(o - lookback, o - 1))
    btc = r.filter(C("coin") == "BTC").select("t", btc="r")
    joined = r.join(btc, on="t", how="inner")
    names = sorted(set(coins) | set(joined["coin"].unique().to_list()))
    by = {c: g for (c,), g in joined.sort("coin", "t").group_by("coin", maintain_order=True)}
    ols: dict[str, tuple[int, float | None]] = {}
    for c in names:
        g = by.get(c)
        n = 0 if g is None else g.height
        est = None
        if g is not None and n >= min_days and c != "BTC":
            x = g["btc"].to_numpy()
            if np.var(x) > 0:
                design = np.column_stack([np.ones(n), x])
                est = float(np.linalg.lstsq(design, g["r"].to_numpy(), rcond=None)[0][1])
        ols[c] = (n, est)
    fitted = [b for c, (_, b) in ols.items() if b is not None and c != "BTC"]
    prior = float(np.median(fitted)) if fitted else 1.0
    rows = []
    for c in names:
        n, est = ols[c]
        if c == "BTC":
            beta, w, kind = 1.0, 1.0, "identity"
        elif est is None:
            beta, w, kind = prior, 0.0, "prior"
        else:
            w = n / (n + shrink_k)
            beta, kind = w * est + (1 - w) * prior, "shrunk_ols"
        rows.append((c, n, kind, w, beta, est, prior, origin))
    schema = {"coin": pl.String, "n_days": pl.Int64, "kind": pl.String, "weight": pl.Float64, "beta_btc": pl.Float64,
              "ols_btc": pl.Float64, "prior_btc": pl.Float64, "origin": pl.Date}
    return pl.DataFrame(rows, schema=schema, orient="row").sort("coin")


def covariance(returns: pl.DataFrame, coins: list[str], origin: date, lookback: int, min_days: int,
               min_complete: int) -> tuple[pl.DataFrame, dict]:
    keep, sigma, info = risk_cov(returns, coins, origin, lookback, min_days, min_complete)
    rows = []
    if sigma is not None:
        for i, a in enumerate(keep):
            for j, b in enumerate(keep):
                rows.append((a, b, float(sigma[i, j])))
    frame = pl.DataFrame(rows, schema={"coin_a": pl.String, "coin_b": pl.String, "cov_daily": pl.Float64},
                         orient="row")
    info = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in info.items()}
    info["use"] = "reporting only; no limit uses the covariance (ADR-0088 item 2)"
    return frame, info


def build(origin: date, shocks: pl.DataFrame, marks: pl.DataFrame, bars: pl.DataFrame, coins: list[str],
          cfg: dict, cov_cfg: dict, edges) -> dict[str, object]:
    """Every table of one origin. `shocks` is the ADR-0017 table at the origin; `marks` the Hyperliquid daily
    closes (coin, boundary, mark); `bars` the 4h impact bars; `coins` the origin's pooled tradable coins."""
    o_day = epoch_day(origin)
    marks = marks.filter(C("boundary") <= o_day)  # a return on day t needs the mark at t + 1 <= the origin
    returns = coin_returns(marks)
    beta_cfg = cfg["beta"]
    cov, info = covariance(returns, coins, origin, int(cov_cfg["covariance_lookback_days"]),
                           int(cov_cfg["cov_min_days"]), int(cov_cfg["cov_min_complete_days"]))
    return {
        "stress_shocks": shock_table(shocks, coins, origin_buckets(bars, origin, edges), origin),
        "betas": btc_betas(returns, origin, coins, int(beta_cfg["lookback_days"]), int(beta_cfg["min_days"]),
                           int(beta_cfg["shrink_k"])),
        "covariance": cov,
        "covariance_info": info,
    }


def write(tables: dict[str, object], folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, table in tables.items():
        if isinstance(table, pl.DataFrame):
            path = folder / f"{name}.parquet"
            table.write_parquet(path, compression="zstd", statistics=True)
        else:
            path = folder / f"{name}.json"
            path.write_text(json.dumps(table, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def load(root: Path, origin: date) -> dict[str, pl.DataFrame]:
    folder = root / f"origin={origin}"
    return {name: pl.read_parquet(folder / f"{name}.parquet") for name in ("stress_shocks", "betas", "covariance")}


def run(ctx, out: Path | None = None) -> Path:
    from arkstream import drift, hlprices
    from arkstream.config import load_yaml
    from arkstream.freeze import guard
    from arkstream.replay_cap import impact_bars
    from arkstream.replay_market import midnight

    dr = drift.DriftRules.from_config(ctx.raw)
    stop = midnight(dr.holdout_start)
    guard(ctx, stop)
    out = Path(out) if out else ctx.root / DEFAULT_OUT
    risk = load_yaml("risk.yaml", ctx.root / "config")
    ex = load_yaml("execution.yaml", ctx.root / "config")["replay"]
    edges = ex["stress_fallback"]["bucket_edges_usdc"]
    tradable = ctx.root / ctx.raw["selection_v2"]["tradable_dir"]
    marks = pl.read_parquet(tradable / "valuation_marks.parquet")
    pairs = pl.read_parquet(tradable / "tradable_pairs.parquet")
    candles, _ = hlprices.load_candles(ctx.path("hyperliquid_dir"), stop)
    bars = impact_bars(candles, stop, ex["square_root"]["volatility_bars"])
    cov_cfg = {**ctx.raw["selection_v2"]["duplicates"], **risk["stress"]}
    for origin in dr.origin_dates:
        shocks = pl.read_parquet(ctx.root / "research/leader" / f"origin={origin}" / "stress_shocks.parquet")
        coins = sorted(pairs.filter(C("origin") == origin)["coin"].unique().to_list())
        write(build(origin, shocks, marks, bars, coins, risk["stress"], cov_cfg, edges), out / f"origin={origin}")
    return out
