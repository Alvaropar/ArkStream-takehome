"""Phase 4 v2 coin eligibility T1-T5 and the leader-level copyability gates (ADRs 0073, 0076).

At each origin o, from the all-priced replay's base training window ending at o (all A/B, the provisional 10k
sleeve):

* T1 priced: the price check passes at o (ADR-0044) and the coin has a base drift source at the base delay
  (aggTrades for BTC/ETH/HYPE/SOL; otherwise a `Parameters.lookup` value at vintage o, ADRs 0048/0061);
* T2 valued: share of the follower's held notional-hours with a known funding payment and a closing daily mark;
* T3 liquid: share of orders whose requested notional fits the participation limit of the latest completed 4h bar;
* T4 affordable: traded-notional-weighted median implementation shortfall per side (half-spread + impact + delay
  drift + fee), pooled; leave-one-wallet-out when it decides a wallet's own set;
* T5 wallets: effective number of wallets in the coin's traded notional (1 / HHI).

No PnL or capture enters a condition; capture is reported beside them. `wallet_sets` returns each universe
address's tradable (trader, coin) pairs; `leader_shares` measures `sel_tradable_share` and `sel_direction` on the
leader's own notional-hours.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import polars as pl

from arkstream.config import load_yaml
from arkstream.replay_market import DAY, DIRECT, bucket_labels
from arkstream.replay_orders import EXCLUDED
from arkstream.selection_v2_market import FACTORS, group_sum, scenario_dir

C = pl.col
BPS = 10_000


def rules_of(ctx) -> dict:
    return ctx.raw["selection_v2"]["tradable"]


def replay_rules(ctx) -> tuple[dict, dict]:
    from arkstream.replay import replay_settings

    return replay_settings(load_yaml("execution.yaml", ctx.root / "config"))


def weighted_median(x: np.ndarray, w: np.ndarray) -> float | None:
    """Lower weighted median: the smallest x whose cumulative weight reaches half the total."""
    ok = np.isfinite(x) & np.isfinite(w) & (w > 0)
    x, w = x[ok], w[ok]
    if not len(x):
        return None
    order = np.lexsort((w, x))
    x, w = x[order], w[order]
    cw = np.cumsum(w)
    return float(x[int(np.searchsorted(cw, 0.5 * cw[-1], side="left"))])


def drift_sources(ctx, origin: date, tree: Path, coins: list[str]) -> pl.DataFrame:
    """T1's drift condition: aggTrades coins, or a base `Parameters.lookup` value at vintage o (band `all`) for at
    least one liquidity bucket (ADR-0053 labels or none)."""
    from arkstream.replay_orders import Parameters

    scenarios, rules = replay_rules(ctx)
    delay = int(scenarios["base"]["delay_ms"])
    params = Parameters.from_rules(pl.read_parquet(tree / "drift_cells.parquet"), rules)
    buckets = ["unknown", *bucket_labels(params.edges)]
    rows = []
    for c in sorted(coins):
        if c in DIRECT:
            rows.append((c, True, "aggtrades"))
            continue
        method = None
        for b in buckets:
            value, m, _, _ = params.lookup(origin, "development", c, "all", delay, conservative=True, bucket=b)
            if value is not None:
                method = m
                break
        rows.append((c, method is not None, method or "no_drift_cell"))
    return pl.DataFrame(rows, schema={"coin": pl.String, "drift_source": pl.Boolean, "drift_method": pl.String},
                        orient="row")


def base_training(tree: Path, origin: date) -> Path:
    return scenario_dir(tree, origin, "training", "base")


def valued_hours(tree: Path, origin: date, marks: pl.DataFrame) -> pl.DataFrame:
    """T2 per (trader, coin): held notional-hours, and those with a known payment and a closing daily mark."""
    d = base_training(tree, origin)
    fund = pl.read_parquet(d / "funding_payments.parquet",
                           columns=["trader", "coin", "batch", "oid", "pos", "hour", "proxy", "payment",
                                    "missing_reason"])
    lots = pl.read_parquet(d / "follower_orders.parquet", columns=["trader", "coin", "batch", "oid", "status",
                                                                     "fill_px"]).filter(C("status") == "filled")
    mk = marks.select("coin", "boundary", close_mark="mark")
    x = (fund.join(lots.select("trader", "coin", "batch", "oid", "fill_px"), on=["trader", "coin", "batch", "oid"],
                   how="left")
         .with_columns(boundary=(C("hour") * 3_600_000 - 1) // DAY + 1)  # the day the held hour ends in
         .join(mk, on=["coin", "boundary"], how="left")
         .with_columns(nh=C("pos").abs() * C("proxy").fill_null(C("fill_px")))
         .with_columns(valued=C("payment").is_not_null() & C("close_mark").is_not_null()))
    one = pl.lit(1, pl.Int64)
    return group_sum(
        x.sort("trader", "coin", "hour", "batch", "oid"), ["trader", "coin"],
        {"notional_hours": C("nh"), "valued_notional_hours": pl.when(C("valued")).then(C("nh")).otherwise(0.0)},
        {"held_hours": one, "unvalued_hours": (~C("valued")).cast(pl.Int64),
         "funding_unknown_hours": C("payment").is_null().cast(pl.Int64),
         "mark_missing_hours": C("close_mark").is_null().cast(pl.Int64),
         "notional_unpriced_hours": C("nh").is_null().cast(pl.Int64)})


def order_stats(tree: Path, origin: date, participation: float) -> tuple[pl.DataFrame, pl.DataFrame]:
    """T3 per (trader, coin) order counts, and the filled orders with their implementation shortfall (T4, T5)."""
    o = pl.read_parquet(base_training(tree, origin) / "follower_orders.parquet",
                        columns=["trader", "coin", "status", "requested_qty", "decision_mark", "bar_volume_usdc",
                                 "quantity", "fill_px", "fee", "half_bps", "impact_bps", "shortfall_bps", "ack_ms",
                                 "batch", "oid"])
    checked = o.filter(~C("status").is_in([*EXCLUDED, "at_target"]) & C("requested_qty").is_not_null()
                       & (C("requested_qty") != 0))
    fits = (C("requested_qty").abs() * C("decision_mark") <= participation * C("bar_volume_usdc")).fill_null(False)
    t3 = checked.with_columns(fits=fits).sort("trader", "coin").group_by("trader", "coin", maintain_order=True).agg(
        orders_checked=pl.len(), orders_fit=C("fits").sum(),
        orders_no_volume=(C("bar_volume_usdc").is_null() | (C("bar_volume_usdc") <= 0)).sum())
    filled = o.filter(C("status") == "filled").with_columns(notional=C("quantity").abs() * C("fill_px")).with_columns(
        is_bps=C("half_bps") + C("impact_bps").fill_null(0.0) + C("shortfall_bps") + C("fee") / C("notional") * BPS,
    ).select("trader", "coin", "ack_ms", "batch", "oid", "notional", "is_bps", "half_bps", "impact_bps",
             "shortfall_bps", fee_bps=C("fee") / C("notional") * BPS).sort("coin", "trader", "ack_ms", "batch", "oid")
    return t3, filled


def coin_table(ctx, origin: date, tree: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    """`coins.parquet` rows (T1-T5, pooled decision and coverage) and the per-wallet T4 leave-one-out table."""
    from arkstream import hlprices
    from arkstream.replay_market import midnight

    r = rules_of(ctx)
    scenarios, rules = replay_rules(ctx)
    marks = pl.read_parquet(tree / "valuation_marks.parquet")
    checks = hlprices.PointInTimeCheck.load(ctx).checks(midnight(origin)).select("coin", price_check="outcome")
    vh = valued_hours(tree, origin, marks)
    t3, filled = order_stats(tree, origin, float(rules["max_participation"]))
    coins = sorted(set(checks["coin"]) | set(vh["coin"]) | set(t3["coin"]) | set(filled["coin"]))
    src = drift_sources(ctx, origin, tree, coins)
    agg2 = group_sum(vh.sort("coin", "trader"), ["coin"],
                     {"notional_hours": C("notional_hours"), "valued_notional_hours": C("valued_notional_hours")},
                     {k: C(k) for k in ("held_hours", "unvalued_hours", "funding_unknown_hours",
                                        "mark_missing_hours", "notional_unpriced_hours")}
                     | {"wallets_held": pl.lit(1, pl.Int64)})
    agg3 = t3.sort("coin", "trader").group_by("coin", maintain_order=True).agg(
        C("orders_checked", "orders_fit", "orders_no_volume").sum())
    rows4, loo = [], []
    for (coin,), g in filled.group_by("coin", maintain_order=True):
        x, w = g["is_bps"].to_numpy(), g["notional"].to_numpy()
        tr = g["trader"].to_numpy()
        wallets, inv = np.unique(tr, return_inverse=True)
        per_n = np.bincount(inv, weights=w)  # sequential sums: byte-identical on rerun (no threaded group-by)
        share = per_n / per_n.sum()
        rows4.append((coin, g.height, float(w.sum()), weighted_median(x, w), float(np.average(x, weights=w)),
                      len(wallets), float(1.0 / np.sum(share ** 2))))
        for t in wallets.tolist():
            keep = tr != t
            loo.append((coin, t, int(keep.sum()), weighted_median(x[keep], w[keep]) if keep.any() else None))
    s4 = {"coin": pl.String, "fills": pl.Int64, "traded_notional": pl.Float64, "is_median_bps": pl.Float64,
          "is_mean_bps": pl.Float64, "wallets_traded": pl.Int64, "effective_wallets": pl.Float64}
    agg4 = pl.DataFrame(rows4, schema=s4, orient="row")
    loo_t = pl.DataFrame(loo, schema={"coin": pl.String, "trader": pl.String, "fills_others": pl.Int64,
                                      "is_median_loo_bps": pl.Float64}, orient="row")
    t = (pl.DataFrame({"coin": coins}, schema={"coin": pl.String}).join(checks, on="coin", how="left")
         .join(src, on="coin", how="left").join(agg2, on="coin", how="left").join(agg3, on="coin", how="left")
         .join(agg4, on="coin", how="left")
         .with_columns(
             valued_share=pl.when(C("notional_hours") > 0).then(C("valued_notional_hours") / C("notional_hours")),
             unclipped_share=pl.when(C("orders_checked") > 0).then(C("orders_fit") / C("orders_checked")))
         .with_columns(
             t1_priced=(C("price_check") == "pass").fill_null(False) & C("drift_source").fill_null(False),
             t2_valued=(C("valued_share") >= float(r["min_valued_share"])).fill_null(False),
             t3_liquid=(C("unclipped_share") >= float(r["min_unclipped_share"])).fill_null(False),
             t4_affordable=(C("is_median_bps") <= float(r["max_cost_bps_per_side"])).fill_null(False),
             t5_wallets=(C("effective_wallets") >= float(r["min_effective_wallets"])).fill_null(False))
         .with_columns(
             others_pass=C("t1_priced") & C("t2_valued") & C("t3_liquid") & C("t5_wallets"))
         .with_columns(tradable=C("others_pass") & C("t4_affordable")))
    loo_t = loo_t.join(t.select("coin", "others_pass", "tradable"), on="coin", how="left").with_columns(
        t4_loo=(C("is_median_loo_bps") <= float(r["max_cost_bps_per_side"])).fill_null(False)).with_columns(
        tradable_for_wallet=C("others_pass") & C("t4_loo")).with_columns(
        flips=C("tradable_for_wallet") != C("tradable")).sort("coin", "trader")
    flips = loo_t.filter("flips").group_by("coin").agg(loo_flips=pl.len())
    t = t.join(flips, on="coin", how="left").with_columns(C("loo_flips").fill_null(0), origin=pl.lit(origin))
    return t.sort("coin"), loo_t.with_columns(origin=pl.lit(origin))


def wallet_sets(ctx, origin: date, tree: Path) -> pl.DataFrame:
    """(trader, coin) tradable pairs for every address of the origin's universe: the pooled set, with each wallet's
    own coins decided on leave-one-wallet-out T4 (ADR-0076 item 4)."""
    coins, loo = coin_table(ctx, origin, tree)
    universe = pl.read_parquet(tree / f"origin={origin}" / "window=training" / "universe.parquet", columns=["trader"])
    return sets_from(coins, loo, universe)


def sets_from(coins: pl.DataFrame, loo: pl.DataFrame, universe: pl.DataFrame) -> pl.DataFrame:
    pooled = coins.filter("tradable").select("coin")
    base = universe.join(pooled, how="cross")
    own = loo.join(universe, on="trader", how="semi")
    drop = own.filter(~C("tradable_for_wallet") & C("tradable")).select("trader", "coin")
    add = own.filter(C("tradable_for_wallet") & ~C("tradable")).select("trader", "coin")
    return pl.concat([base.join(drop, on=["trader", "coin"], how="anti"), add]).unique().sort("trader", "coin")


def leader_notional_hours(fills: pl.DataFrame, origin: date, start: date) -> pl.DataFrame:
    """Per (trader, coin): the leader's notional-hours and signed notional-hours over [start, origin) on hour marks
    (|pos| x the latest fill price, the gate-18 convention), from fills known by the origin; core perps and HIP-3
    (spot excluded, ADR-0047)."""
    from arkstream.leader_returns import ceil_hour_expr
    from arkstream.pipeline import positions_asof

    asof = datetime(origin.year, origin.month, origin.day, tzinfo=UTC)
    led, _, _ = positions_asof(fills, asof)
    hour = 3_600_000
    s_ms = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp() * 1000)
    o_ms = int(asof.timestamp() * 1000)
    x = (led.sort("trader", "symbol", "seq")
         .with_columns(next_ts=C("ts").shift(-1).over(["trader", "symbol"]))
         .filter(C("pos_after").abs() > 1e-9)
         .with_columns(lo=ceil_hour_expr(C("ts")).dt.epoch("ms"),
                       hi=pl.when(C("next_ts").is_null()).then(pl.lit(o_ms - hour))
                       .otherwise(pl.min_horizontal(((C("next_ts").dt.epoch("ms") - 1) // hour) * hour,
                                                    pl.lit(o_ms - hour))))
         .with_columns(lo=pl.max_horizontal(C("lo"), pl.lit(s_ms)))
         .with_columns(n=pl.when(C("hi") >= C("lo")).then((C("hi") - C("lo")) // hour + 1).otherwise(0))
         .filter(C("n") > 0))
    x = x.with_columns(coin=C("symbol"))
    s = group_sum(x, ["trader", "coin"], {"notional_hours": C("pos_after").abs() * C("price") * C("n"),
                                          "signed_notional_hours": C("pos_after") * C("price") * C("n")},
                  {"hip3_rows": (C("instrument_class") == "hip3").cast(pl.Int64)})
    return s.with_columns(hip3=C("hip3_rows") > 0).drop("hip3_rows").sort("trader", "coin")


def leader_shares(nh: pl.DataFrame, pairs: pl.DataFrame, betas: pl.DataFrame, rules: dict) -> pl.DataFrame:
    """`sel_tradable_share` and `sel_direction` per leader (ADR-0076 items 6-7)."""
    from arkstream.selection_v2_market import beta_lookup

    b = beta_lookup(betas, nh["coin"].unique().to_list())
    x = (nh.join(pairs.with_columns(tr=pl.lit(True)), on=["trader", "coin"], how="left")
         .with_columns(tradable=C("tr").fill_null(False) & ~C("hip3")).drop("tr")
         .join(b, on="coin", how="left"))
    zero = pl.lit(0.0)
    vals = {"leader_notional_hours": C("notional_hours"),
            "non_tradable_notional_hours": pl.when(~C("tradable")).then(C("notional_hours")).otherwise(zero),
            "hip3_notional_hours": pl.when(C("hip3")).then(C("notional_hours")).otherwise(zero),
            "tradable_notional_hours": pl.when(C("tradable")).then(C("notional_hours")).otherwise(zero)}
    for f in FACTORS:
        vals[f"sb_full_{f}"] = C("signed_notional_hours") * C(f"beta_{f}")
        vals[f"sb_tr_{f}"] = pl.when(C("tradable")).then(C("signed_notional_hours") * C(f"beta_{f}")).otherwise(zero)
    g = group_sum(x.sort("trader", "coin"), ["trader"], vals)
    beta = {}
    for f in FACTORS:
        beta[f"full_{f}"] = pl.when(C("leader_notional_hours") > 0).then(C(f"sb_full_{f}") / C("leader_notional_hours"))
        beta[f"copied_{f}"] = pl.when(C("tradable_notional_hours") > 0).then(
            C(f"sb_tr_{f}") / C("tradable_notional_hours"))
    out = g.with_columns(**beta).select(
        "trader", "leader_notional_hours", "non_tradable_notional_hours", "hip3_notional_hours", *beta
    ).with_columns(
        non_tradable_share=pl.when(C("leader_notional_hours") > 0).then(
            C("non_tradable_notional_hours") / C("leader_notional_hours")),
        **{f"delta_beta_{f}": C(f"copied_{f}") - C(f"full_{f}") for f in FACTORS},
    ).with_columns(max_abs_delta_beta=pl.max_horizontal(*[C(f"delta_beta_{f}").abs() for f in FACTORS]))
    lim, dlim = float(rules["max_leader_non_tradable_share"]), float(rules["max_abs_delta_beta"])
    from arkstream.selection import gate

    return out.with_columns(
        sel_tradable_share=gate(C("non_tradable_share") <= lim, C("non_tradable_share").is_not_null()),
        sel_direction=gate(C("max_abs_delta_beta") <= dlim, C("max_abs_delta_beta").is_not_null()),
    ).sort("trader")
