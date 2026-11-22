"""Snapshot reconciliation and daily closing book on independent UTC boundary marks."""

from datetime import datetime

import polars as pl

from arkstream.book_state import KEY, book_state
from arkstream.leader_marks import MS
from arkstream.positions import order_fills, pit

C = pl.col


def funded_state(state: pl.DataFrame, pay: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    hourly = (
        pay.filter(C("ts_hour") <= asof)
        .sort("trader", "ts_hour", "coin")
        .group_by("trader", "ts_hour", maintain_order=True)
        .agg(funding_total=C("payment").sum(), unknown_rates=C("payment").is_null().sum())
        .with_columns(C("funding_total", "unknown_rates").cum_sum().over("trader"))
        .sort("ts_hour")
    )
    return (
        state.sort("ts")
        .join_asof(hourly, left_on="ts", right_on="ts_hour", by="trader", check_sortedness=False)
        .with_columns(C("funding_total", "unknown_rates").fill_null(0))
        .sort("trader", "ts", "src_row")
    )


def noncore_state(points: pl.DataFrame, fills: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    # Never assign a USDC value to spot or HIP-3. Track possible inventory and changes only.
    other = (
        order_fills(pit(fills, asof).filter(~C("eligible")))
        .sort(*KEY, "ts", "seq")
        .with_columns(
            outstanding=(C("start_position") + C("delta")).abs() > 1e-9,
            event_count=pl.int_range(1, pl.len() + 1, dtype=pl.Int64).over(KEY),
        )
    )
    series = other.group_by(KEY).agg(inherited=C("start_position").first().abs() > 1e-9)
    s = (
        points.join(series, on="trader")
        .sort("ts")
        .join_asof(
            other.select(*KEY, event_ts="ts", outstanding="outstanding", event_count="event_count").sort(
                "event_ts", maintain_order=True
            ),
            left_on="ts",
            right_on="event_ts",
            by=KEY,
            check_sortedness=False,
        )
    )
    return s.group_by("trader", "src_row").agg(
        noncore=C("outstanding").fill_null(C("inherited")).any(), events=C("event_count").sum()
    )


def intervals(
    acc: pl.DataFrame, state: pl.DataFrame, fills: pl.DataFrame, asof: datetime, feed_start: datetime, rules: dict
) -> tuple[pl.DataFrame, pl.DataFrame]:
    state = state.join(noncore_state(state, fills, asof), on=["trader", "src_row"], how="left").with_columns(
        C("events").fill_null(0), C("noncore").fill_null(False)
    )
    deltas = ["value", "funding_total", "unknown_rates", "bad_fees", "events", "n_fill"]
    s = state.sort("trader", "ts", "src_row").with_columns(
        *(C(k).cast(pl.Float64).diff().over("trader").alias("d_" + k) for k in deltas),
        *(C(k).shift().over("trader").alias("prev_" + k) for k in ("unpriced", "n_held", "noncore")),
    )
    x = (
        acc.join(s, on=["trader", "ts", "src_row"])
        .with_columns(
            active=(C("n_held") + C("prev_n_held") + C("d_n_fill")) > 0,
            noncore_interval=C("noncore") | C("prev_noncore") | (C("d_events") > 0) | (C("d_bad_fees") != 0),
            stale_snapshot=(C("equity") == C("prev_equity"))
            & (C("unpriced") + C("prev_unpriced") == 0)
            & (C("d_bad_fees") == 0)
            & (C("d_value").abs() > 0.000001),
            price_source=pl.lit("binance_1m"),
            validation=pl.when(C("unpriced") + C("prev_unpriced") == 0)
            .then(pl.lit("validated"))
            .otherwise(pl.lit("unvalidated")),
        )
        .with_columns(
            scope=pl.when(C("prev_ts") < feed_start)
            .then(pl.lit("before_fill_feed"))
            .when(C("noncore_interval"))
            .then(pl.lit("noncore"))
            .when((C("unpriced") + C("prev_unpriced") > 0) | (C("d_unknown_rates") > 0))
            .then(pl.lit("unpriced_or_rate_unknown"))
            .otherwise(pl.lit("checkable"))
        )
    )
    x = x.with_columns(
        book_pnl=pl.when(C("scope") == "checkable").then(C("d_value") + C("d_funding_total")),
        fit_eligible=(C("scope") == "checkable")
        & C("active")
        & ~C("stale_snapshot")
        & (C("prev_equity") >= rules["returns"]["min_open_equity_usdc"]),
    ).with_columns(
        miss=pl.when("fit_eligible").then((C("account_pnl") - C("book_pnl")).abs() / C("prev_equity")),
        book_r=pl.when(C("den_start") > 0).then(C("book_pnl") / C("den_start")),
    )
    ok = x.filter("fit_eligible")
    per = ok.group_by("trader").agg(
        xc_n=pl.len(),
        pnl_corr=pl.corr("account_pnl", "book_pnl"),
        within_0_1pct=(C("miss") <= 0.001).mean(),
        within_1pct=(C("miss") <= 0.01).mean(),
        median_miss=C("miss").median(),
    )
    counts = x.group_by("trader").agg(
        stale_snapshots=C("stale_snapshot").sum(),
        intervals=pl.len(),
        not_checkable=(C("scope") != "checkable").sum(),
        active_intervals=C("active").sum(),
    )
    agreement = (
        ok.filter("usable")
        .group_by("trader")
        .agg(agreement_n=pl.len(), xc_corr=pl.corr("r_start", "book_r"), xc_gap_std=(C("r_start") - C("book_r")).std())
    )
    summary = (
        counts.join(per, on="trader", how="left")
        .join(agreement, on="trader", how="left")
        .with_columns(xc_n=C("xc_n").fill_null(0), fit_coverage=C("xc_n").fill_null(0) / C("intervals"))
        .with_columns(
            xc_flag=pl.when(C("agreement_n").fill_null(0) < rules["book"]["min_intervals"])
            .then(pl.lit("too_few_intervals"))
            .when(C("xc_corr").is_nan() | C("xc_corr").is_null())
            .then(pl.lit("no_variation"))
            .when(C("xc_corr") < rules["book"]["min_corr"])
            .then(pl.lit("disagree_corr"))
            .when(C("xc_gap_std") > rules["book"]["max_tracking_gap_std"])
            .then(pl.lit("disagree_tracking"))
            .otherwise(pl.lit("ok"))
        )
    )
    return x.sort("trader", "ts", "src_row"), summary.sort("trader")


def daily_book(
    traders: pl.DataFrame,
    ledger: pl.DataFrame,
    marks: pl.DataFrame,
    pay: pl.DataFrame,
    asof: datetime,
    ref: pl.LazyFrame,
    fills: pl.DataFrame,
    feed_start: datetime,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    start = pit(traders, asof).group_by("trader").agg(start=C("ts").min().dt.truncate("1d"))
    start = start.with_columns(start=pl.max_horizontal("start", pl.lit(feed_start).cast(MS)))
    points = (
        start.select("trader", ts=pl.datetime_ranges("start", pl.lit(asof).cast(MS), "1d"))
        .explode("ts", empty_as_null=False)
        .sort("trader", "ts")
        .with_row_index("src_row")
    )
    state, _ = book_state(points, ledger, asof, ref, [], fills, daily=marks)
    state = funded_state(state, pay, asof)
    d = state.with_columns(
        day_start=C("ts").shift().over("trader"),
        trade=C("value").diff().over("trader"),
        funding_paid=C("funding_total").diff().over("trader"),
        missing=C("unpriced")
        + C("unpriced").shift().over("trader")
        + C("unknown_rates").diff().over("trader")
        + C("bad_fees").diff().over("trader"),
        validation=pl.when(C("unvalidated") | C("unvalidated").shift().over("trader"))
        .then(pl.lit("unvalidated"))
        .when(C("flagged") | C("flagged").shift().over("trader"))
        .then(pl.lit("flagged"))
        .otherwise(pl.lit("validated")),
    ).drop_nulls("day_start")
    snaps = traders.select("trader", eq_ts="ts", equity_src_row="src_row", equity_base="equity").sort("eq_ts")
    d = d.sort("day_start").join_asof(snaps, left_on="day_start", right_on="eq_ts", by="trader", check_sortedness=False)
    return (
        d.select(
            "trader",
            "day_start",
            "ts",
            "equity_src_row",
            "eq_ts",
            "equity_base",
            "validation",
            day=C("day_start").dt.date(),
            book_pnl=pl.when(C("missing") == 0).then(C("trade") + C("funding_paid")),
            funding_paid="funding_paid",
            missing_terms="missing",
            price_source=pl.lit("hyperliquid_4h"),
        )
        .with_columns(book_ret=pl.when(C("equity_base") > 0).then(C("book_pnl") / C("equity_base")))
        .sort("trader", "day"),
        state,
    )


def attribution(intervals: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    """Disjoint account-minus-book buckets. Preserve the account subtotal when a valuation is unknowable."""
    x = intervals.filter(C("ts") <= asof).sort("trader", "ts", "src_row")
    complete_marks = C("unpriced") + C("prev_unpriced") == 0
    in_feed = C("scope") != "before_fill_feed"
    x = x.with_columns(
        trade_identified=pl.when(in_feed & complete_marks).then("d_value").otherwise(0.0),
        known_funding=pl.when(in_feed).then("d_funding_total").otherwise(0.0),
    )
    x = x.with_columns(residual=C("account_pnl") - C("trade_identified") - C("known_funding"))
    return x.select(
        intervals=pl.len(),
        account=C("account_pnl").sum(),
        core_trade=C("trade_identified").sum(),
        funding=C("known_funding").sum(),
        before_feed=C("residual").filter(~in_feed).sum(),
        noncore=C("residual").filter(C("scope") == "noncore").sum(),
        unpriced=C("residual").filter(C("scope") == "unpriced_or_rate_unknown").sum(),
        unexplained=C("residual").filter(C("scope") == "checkable").sum(),
        fit_intervals=C("fit_eligible").sum(),
        within_1pct=C("miss").drop_nulls().le(0.01).mean(),
        median_miss=C("miss").median(),
        asof=pl.lit(asof).cast(MS),
    )
