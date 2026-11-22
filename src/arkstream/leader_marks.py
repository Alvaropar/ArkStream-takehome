"""Valuation sources and actual held-position funding accruals (ADRs 0040, 0061)."""

from datetime import datetime

import polars as pl

from arkstream import funding as hf
from arkstream.positions import pit

C = pl.col
MS = pl.Datetime("ms", "UTC")


def price_panels(
    hourly: pl.DataFrame, candles: pl.DataFrame, outcomes: pl.DataFrame, asof: datetime, bounds: dict
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Daily marks require the closing bar. Only funding proxies may use an earlier traded HL bar."""
    hour = hourly.filter(C("t") <= asof).join(outcomes.select("coin", "outcome"), on="coin", how="left")
    good = C("outcome") == "pass"
    hour = hour.with_columns(
        price=pl.when(good & C("price_source").is_in(["reference", "binance_1m"])).then("price"),
        price_source=pl.lit("binance_1m"),
    ).with_columns(
        validation=pl.when(C("price").is_not_null()).then(pl.lit("validated")).otherwise(pl.lit("unvalidated"))
    )
    hl = candles.filter((C("ts") <= asof) & (C("n_trades") > 0)).select(
        "coin", price_ts=C("ts").cast(MS), hl_price="price", src_file="src_file"
    )
    day = hour.filter(C("t").dt.hour() == 0).rename(
        {"price": "binance_price", "validation": "binance_validation", "price_source": "binance_price_source"}
    )
    day = (
        day.join(hl.with_columns(t=C("price_ts")), on=["coin", "t"], how="left")
        .rename({"hl_price": "price"})
        .with_columns(gap_bps=(C("price") / C("binance_price") - 1) * 1e4, price_source=pl.lit("hyperliquid_4h"))
        .with_columns(
            above_median_bound=C("gap_bps").abs() > bounds["max_median_abs_bps"],
            above_tail_bound=C("gap_bps").abs() > bounds["max_p95_abs_bps"],
            validation=pl.when(C("price").is_null())
            .then(pl.lit("unvalidated"))
            .when(C("outcome") == "fail")
            .then(pl.lit("flagged"))
            .when(C("gap_bps").is_null())
            .then(pl.lit("unvalidated"))
            .when(C("gap_bps").abs() > bounds["max_p95_abs_bps"])
            .then(pl.lit("flagged"))
            .otherwise(pl.lit("validated")),
        )
    )
    proxy = (
        hour.sort("t")
        .join_asof(
            hl.sort("price_ts"), left_on="t", right_on="price_ts", by="coin", tolerance="4h", check_sortedness=False
        )
        .select(
            "coin",
            ts_hour="t",
            price=pl.when(good).then("price").otherwise("hl_price"),
            price_ts=pl.when(good).then("ref_ts").otherwise("price_ts"),
            price_file=pl.when(good).then("ref_file").otherwise("src_file"),
            price_source=pl.when(good).then(pl.lit("binance_1m")).otherwise(pl.lit("hyperliquid_4h")),
            validation=pl.when(good)
            .then("validation")
            .when(C("outcome") == "fail")
            .then(pl.lit("flagged"))
            .otherwise(pl.lit("unvalidated")),
        )
    )
    return hour.sort("coin", "t"), day.sort("coin", "t"), proxy.sort("coin", "ts_hour")


def payments(ledger: pl.DataFrame, rates: pl.DataFrame, proxies: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    """Enumerate expected hours even if a published rate or oracle proxy is missing."""
    keys = ["trader", "symbol"]
    led = (
        pit(ledger, asof)
        .sort(*keys, "ts", "seq")
        .with_columns(
            next_ts=C("ts").shift(-1).over(keys).fill_null(asof),
            trip_no=C("trip_no") + ((C("pos_before") * C("pos_after")) < 0).cast(pl.Int64),
        )
    )
    hours = (
        led.filter(C("pos_after").abs() > 1e-9)
        .select(
            "trader",
            coin="symbol",
            pos="pos_after",
            trip_no="trip_no",
            src_row="src_row",
            tid="tid",
            oid="oid",
            fill_ts="ts",
            ts_hour=pl.datetime_ranges(
                (C("ts").dt.truncate("1h") + pl.duration(hours=1)).cast(MS),
                C("next_ts").dt.truncate("1h").cast(MS),
                "1h",
            ),
        )
        .explode("ts_hour", empty_as_null=False)
        .filter(C("ts_hour").is_not_null())
    )
    known = hf.funding_asof(rates, asof).select("coin", C("ts_hour").cast(MS), "known_at", "funding_rate", "src_file")
    return (
        hours.join(known, on=["coin", "ts_hour"], how="left")
        .join(proxies, on=["coin", "ts_hour"], how="left")
        .with_columns(
            payment=-C("pos") * C("price") * C("funding_rate"),
            missing_reason=pl.when(C("funding_rate").is_null())
            .then(pl.lit("rate_unknown"))
            .when(C("price").is_null())
            .then(pl.lit("proxy_unpriced"))
            .otherwise(pl.lit("")),
        )
        .sort("trader", "ts_hour", "coin")
    )
