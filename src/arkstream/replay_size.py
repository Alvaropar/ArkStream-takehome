"""Development-only measurement of signed aggTrade moves following visible taker sweeps (ADR-0088).

For BTC, ETH, HYPE and SOL, each leader taker order (trader, oid, timestamp) is followed on Binance aggTrades from
the order time to order time + h, signed by the leader's side. Orders are bucketed by notional and by notional over
the latest completed Hyperliquid 4h bar's USDC volume. At each origin only observations whose end is before the
origin are used; 10-11 Oct is excluded. A size term qualifies only where at least three of the four coins show
both large > small and high share > low share with at least 30 observations per arm.
"""

import polars as pl

from arkstream import drift, hlprices
from arkstream.instruments import forced_fill
from arkstream.replay_market import DAY, DIRECT, bounded_inputs, midnight, ms, trade_queries

C = pl.col
KEY = ["origin", "coin", "delay_s"]
# ADR-0088's horizons (s), fixed for this study: ADR-0150 added 1.2 s and 5 s to the drift grid for the replay's
# measured delays, not to the size study, whose result (no qualifying size term) is unchanged and not rerun.
HORIZONS_MS = (1_000, 10_000, 60_000, 300_000)
USD = ([1000, 10000, 100000, 1e6], ["<1k", "1k-10k", "10k-100k", "100k-1M", ">=1M"])
SHARE = ([0.0001, 0.001, 0.005], ["<0.01%", "0.01-0.1%", "0.1-0.5%", ">=0.5%"])
ARMS = {
    "small": C("q") < 1000,
    "large": C("q") >= 100000,
    "low": C("share") < 0.0001,
    "high": C("share") >= 0.005,
}
MIN_ARM = 30
MIN_COINS = 3


def bucket(x, limits, labels):
    expr = pl.lit(labels[-1])
    for bound, label in reversed(list(zip(limits, labels[:-1], strict=True))):
        expr = pl.when(x < bound).then(pl.lit(label)).otherwise(expr)
    return pl.when(x.is_not_null()).then(expr)


def taker_orders(fills, bars):
    orders = (
        fills.group_by("trader", "symbol", "oid", "ts", "side")
        .agg(q=(C("size").abs() * C("price")).sum())
        .select(
            "trader",
            "oid",
            "q",
            coin="symbol",
            t=C("ts").dt.epoch("ms"),
            sign=pl.when(C("side") == "buy").then(1).otherwise(-1),
        )
        .sort("t", "trader", "oid")
    )
    # The latest completed bar known at the order: a bar's volume is usable only after it closes.
    orders = orders.join_asof(
        bars,
        left_on="t",
        right_on="known_ms",
        by="coin",
        strategy="backward",
        tolerance=4 * 3600 * 1000 - 1,
        check_sortedness=False,
    )
    return orders.with_columns(share=C("q") / C("volume")).with_columns(
        usd_bucket=bucket(C("q"), *USD), share_bucket=bucket(C("share"), *SHARE)
    )


def contrasts(obs, origins):
    summaries, tests = [], []
    for date in origins:
        f = obs.filter(C("ack") < ms(midnight(date))).with_columns(origin=pl.lit(date))
        for axis in ["usd_bucket", "share_bucket"]:
            summaries.append(
                f.group_by(*KEY, axis, maintain_order=True)
                .agg(n=pl.len(), mean_bps=C("bps").mean())
                .rename({axis: "bucket"})
                .with_columns(axis=pl.lit(axis))
            )
        expr = []
        for name, mask in ARMS.items():
            expr += [mask.sum().alias(name + "_n"), C("bps").filter(mask).mean().alias(name)]
        tests.append(f.group_by(*KEY, maintain_order=True).agg(*expr, avg=C("bps").mean()))
    panels = (
        pl.concat(tests)
        .sort(*KEY)
        .with_columns(
            support=(pl.min_horizontal(*[C(k + "_n") for k in ARMS]) >= MIN_ARM)
            & (C("large") > C("small"))
            & (C("high") > C("low"))
        )
    )
    terms = (
        panels.group_by("origin", "delay_s", maintain_order=True)
        .agg(support=C("support").sum(), premium=(C("high") - C("avg")).filter("support").median())
        .with_columns(
            size_term_bps=pl.when(C("support") >= MIN_COINS).then(C("premium").clip(lower_bound=0)).otherwise(0.0)
        )
        .sort("origin", "delay_s")
    )
    return pl.concat(summaries).sort(*KEY, "axis", "bucket"), panels, terms


def study(ctx, dest):
    rules = drift.DriftRules.from_config(ctx.raw)
    end = midnight(rules.holdout_start)
    fills = bounded_inputs(ctx, end).fills.filter(
        C("eligible") & (C("event_kind") == "trade") & C("symbol").is_in(DIRECT) & ~C("is_maker")
        & ~forced_fill()  # ADR-0112: forced fills are not signals
    )
    tape = trade_queries(ctx, fills, rules, end)
    candles, _ = hlprices.load_candles(ctx.path("hyperliquid_dir"), end)
    bars = (
        candles.filter(C("n_trades") > 0)
        .select("coin", known_ms=C("ts").dt.epoch("ms"), volume=C("price") * C("volume"))
        .sort("known_ms")
    )
    orders = taker_orders(fills, bars)
    obs = []
    missing = set(HORIZONS_MS) - set(rules.horizons_ms)
    if missing:
        raise ValueError(f"size-study horizons {sorted(missing)} ms are not in the drift grid (no aggTrades query)")
    for h in HORIZONS_MS:
        f = (
            orders.with_columns(ack=C("t") + h)
            .join(tape.select("coin", t="query", p0="price"), on=["coin", "t"])
            .join(tape.select("coin", ack="query", p1="price"), on=["coin", "ack"])
        )
        obs.append(f.with_columns(delay_s=pl.lit(h // 1000), bps=C("sign") * (C("p1") / C("p0") - 1) * 10000))
    excluded = sorted(rules.exclude)
    obs = (
        pl.concat(obs)
        .filter(
            ~(C("t") // DAY).cast(pl.Date).is_in(excluded) & ~(C("ack") // DAY).cast(pl.Date).is_in(excluded)
        )
        .sort("coin", "delay_s", "t", "trader", "oid")
    )
    summaries, panels, terms = contrasts(obs, rules.origin_dates)
    dest.mkdir(parents=True, exist_ok=True)
    summaries.write_csv(dest / "leader_size_buckets.csv")
    panels.write_csv(dest / "leader_size_contrasts.csv")
    terms.write_csv(dest / "leader_size_terms.csv")
    return terms
