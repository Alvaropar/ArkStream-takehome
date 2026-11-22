"""Core-perp book at observation timestamps, using chain-ordered positions and actual fill cash."""

from datetime import datetime

import polars as pl

from arkstream.positions import pit
from arkstream.prices import price_asof

KEY = ["trader", "symbol"]
C = pl.col


def book_state(
    points: pl.DataFrame,
    ledger: pl.DataFrame,
    asof: datetime,
    ref: pl.LazyFrame,
    passing: list[str],
    fills: pl.DataFrame,
    daily: pl.DataFrame | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Mark each open coin at each point. Differences of state values give pre-funding trading PnL."""
    points = pit(points, asof).select("trader", "ts", "src_row")
    led = (
        pit(ledger, asof)
        .filter("eligible")
        .sort(*KEY, "ts", "seq")
        .with_columns(
            cash=(-C("delta") * C("price") - pl.when(C("fee_token") == "USDC").then("fee").otherwise(0))
            .cum_sum()
            .over(KEY),
            bad_fees=((C("fee_token") != "USDC") & (C("fee") != 0)).cast(pl.Int64).cum_sum().over(KEY),
            n_fill=pl.int_range(1, pl.len() + 1, dtype=pl.Int64).over(KEY),
        )
    )
    coins = led.group_by(KEY).agg(inherited=C("pos_before").first().abs() > 1e-9)
    states = (
        points.join(coins, on="trader")
        .sort("ts")
        .join_asof(
            led.select(
                *KEY,
                fill_ts="ts",
                fill_src_row="src_row",
                pos="pos_after",
                tid="tid",
                oid="oid",
                cash="cash",
                bad_fees="bad_fees",
                n_fill="n_fill",
            ).sort("fill_ts", maintain_order=True),
            left_on="ts",
            right_on="fill_ts",
            by=KEY,
            check_sortedness=False,
        )
    )
    held = C("pos").abs() > 1e-9
    if daily is None:
        q = states.filter(held & C("symbol").is_in(passing)).select(coin="symbol", t="ts").unique().sort("coin", "t")
        marks = price_asof(q, ref, fills.clear(), asof, 60, 0).select(
            symbol="coin",
            ts="t",
            price="price",
            price_ts="price_ts",
            price_file="price_ref_file",
            validation=pl.when(C("price").is_not_null()).then(pl.lit("validated")),
        )
    else:
        marks = daily.select(
            symbol="coin", ts="t", price="price", price_ts="price_ts", price_file="src_file", validation="validation"
        )
    states = (
        states.join(marks, on=["symbol", "ts"], how="left")
        .sort("trader", "ts", "symbol")
        .with_columns(
            price_source=pl.lit("binance_1m" if daily is None else "hyperliquid_4h"),
            validation=C("validation").fill_null("unvalidated"),
        )
    )
    av = states.group_by("trader", "src_row").agg(
        value=(C("cash").fill_null(0) + pl.when(held).then(C("pos") * C("price")).otherwise(0).fill_null(0)).sum(),
        flagged=(held & (C("validation") == "flagged")).any(),
        unvalidated=(held & (C("validation") == "unvalidated")).any(),
        unpriced=((held & C("price").is_null()) | (C("pos").is_null() & C("inherited"))).sum(),
        n_held=held.sum(),
        bad_fees=C("bad_fees").sum(),
        n_fill=C("n_fill").sum(),
    )
    cols = ["value", "unpriced", "n_held", "bad_fees", "n_fill"]
    return (
        points.join(av, on=["trader", "src_row"], how="left")
        .with_columns(C(*cols).fill_null(0), C("flagged", "unvalidated").fill_null(False))
        .sort("trader", "ts", "src_row"),
        states.filter(held),
    )
