"""Leader evidence, daily level: account returns from snapshots and book returns from rebuilt positions.

Point in time: every function takes `asof` and uses only rows with ts <= asof.

Cross-margin account returns (ADRs 0021, 0041 and 0065). For consecutive snapshots of one address,
E is cross-margin account equity and ND is reported net deposits:

    pnl     = E_t - E_{t-1} - (ND_t - ND_{t-1})
    r_start = pnl / (E_{t-1} + dND)        flow at the start of the interval (base case)
    r_end   = pnl / E_{t-1}                flow at the end (sensitivity)

A snapshot gap gives one return over the whole gap (`period_days` > 1); nothing is interpolated. A return is
excluded, with a reason, when opening equity is below `min_open_equity_usdc`, a denominator is not positive,
or the two conventions differ by more than `max_convention_gap`. Transfers to other margin accounts or spot
can move E without a corresponding change in ND. The identity check determines the primary series at each origin.

Book returns (ADR-0022). Positions come from `positions.rebuild` (core perps only) and are marked at hour
boundaries using the ADR-0040 Binance panel on its validated coins. The following terms give the PnL
of hour (m, m + 1h] per coin.

    pos_m * (P_{m+1h} - P_m)                           position held at the mark          (term "hold")
  + sum over fills in (m, m+1h]: delta * (P_{m+1h} - px) - fee                             (term "fill")
  + for the first observed fill of a left-censored series: pos_before * (P_{m+1h} - px)    (term "inherit")
  + funding (precomputed held-position payments known at the origin)

Any term with a missing price makes the hour's book PnL null for that address (no partial sums are used as
returns); the priced part and the unpriced exposure are reported. Production funding comes from leader_marks.payments.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import polars as pl

from arkstream import prices
from arkstream.positions import pit

HOUR = timedelta(hours=1)


def floor_hour(t: datetime) -> datetime:
    return t.replace(minute=0, second=0, microsecond=0)


def ceil_hour_expr(c: pl.Expr) -> pl.Expr:
    f = c.dt.truncate("1h")
    return pl.when(f == c).then(f).otherwise(f + pl.duration(hours=1)).dt.cast_time_unit("ms")


# ---------------------------------------------------------------------------------------------- account
def account_returns(traders: pl.DataFrame, asof: datetime, rules: dict) -> pl.DataFrame:
    """One row per snapshot interval (prev snapshot -> snapshot), both conventions, usable flag and reason."""
    r = rules["returns"]
    s = pit(traders, asof).sort("trader", "ts", "src_row").with_columns(
        prev_ts=pl.col("ts").shift().over("trader"),
        prev_date=pl.col("date").shift().over("trader"),
        prev_src_row=pl.col("src_row").shift().over("trader"),
        prev_equity=pl.col("equity").shift().over("trader"),
        prev_net_deposit=pl.col("net_deposit").shift().over("trader"),
    ).filter(pl.col("prev_ts").is_not_null())
    s = s.with_columns(d_net_deposit=pl.col("net_deposit") - pl.col("prev_net_deposit")).with_columns(
        account_pnl=pl.col("equity") - pl.col("prev_equity") - pl.col("d_net_deposit"),
        den_start=pl.col("prev_equity") + pl.col("d_net_deposit"),
        period_days=(pl.col("date") - pl.col("prev_date")).dt.total_days(),
        gap_days=(pl.col("ts") - pl.col("prev_ts")).dt.total_milliseconds() / 86_400_000,
    ).with_columns(
        r_start=pl.when(pl.col("den_start") > 0).then(pl.col("account_pnl") / pl.col("den_start")),
        r_end=pl.when(pl.col("prev_equity") > 0).then(pl.col("account_pnl") / pl.col("prev_equity")),
    )
    reason = (pl.when(pl.col("prev_equity") < r["min_open_equity_usdc"]).then(pl.lit("opening_equity_below_min"))
              .when(pl.col("r_start").is_null() | pl.col("r_end").is_null()).then(pl.lit("nonpositive_denominator"))
              .when((pl.col("r_start") - pl.col("r_end")).abs() > r["max_convention_gap"])
              .then(pl.lit("conventions_disagree"))
              .otherwise(pl.lit("")))
    return s.with_columns(exclude_reason=reason).with_columns(
        usable=pl.col("exclude_reason") == "", multi_day=pl.col("period_days") > 1,
        asof=pl.lit(asof).dt.cast_time_unit("ms"),
    ).select("trader", "prev_ts", "ts", "prev_src_row", "src_row", "prev_date", "date", "period_days", "gap_days",
             "multi_day", "prev_equity", "equity", "d_net_deposit", "account_pnl", "den_start", "r_start", "r_end",
             "usable", "exclude_reason", "asof").sort("trader", "ts", "src_row")


def account_coverage(acc: pl.DataFrame, traders: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    """Per address: return intervals, usable ones, days covered by usable returns / calendar days to asof."""
    first = pit(traders, asof).group_by("trader").agg(first_date=pl.col("date").min())
    a = acc.group_by("trader").agg(
        n_intervals=pl.len(), n_usable=pl.col("usable").sum(),
        usable_days=pl.col("period_days").filter("usable").sum(),
        n_multi_day=pl.col("multi_day").filter("usable").sum(),
        n_below_min=(pl.col("exclude_reason") == "opening_equity_below_min").sum(),
        n_conventions_disagree=(pl.col("exclude_reason") == "conventions_disagree").sum(),
    )
    return first.join(a, on="trader", how="left").with_columns(
        calendar_days=(pl.lit(asof.date()) - pl.col("first_date")).dt.total_days(),
    ).with_columns(
        account_coverage=pl.when(pl.col("calendar_days") > 0)
        .then(pl.col("usable_days").fill_null(0) / pl.col("calendar_days")),
    ).sort("trader")


# ---------------------------------------------------------------------------------------------- prices
PriceGrid = Callable[[pl.DataFrame, datetime], pl.DataFrame]
"""(queries with coin, t) , asof -> same rows + price, price_source. A second source plugs in here."""


@dataclass(frozen=True)
class ReferenceGrid:
    """Binance reference (ADR-0002) via prices.price_asof: reference, else package print, else unpriced."""
    ref: pl.LazyFrame | pl.DataFrame
    fills: pl.DataFrame
    max_age_s: float
    print_window_s: float

    def __call__(self, queries: pl.DataFrame, asof: datetime) -> pl.DataFrame:
        return prices.price_asof(queries, self.ref, self.fills, asof, self.max_age_s, self.print_window_s)


def hourly_prices(grid: PriceGrid, coins: list[str], start: datetime, asof: datetime) -> pl.DataFrame:
    """Price of every coin at every hour boundary in [start, asof] (coin, t, price, price_source)."""
    end = floor_hour(asof)
    if not coins or end < start:
        return pl.DataFrame(schema={"coin": pl.String, "t": pl.Datetime("ms", "UTC"), "price": pl.Float64,
                                    "price_source": pl.String})
    hours = pl.datetime_range(floor_hour(start), end, "1h", eager=True, time_unit="ms", time_zone="UTC")
    q = pl.DataFrame({"coin": sorted(coins)}).join(pl.DataFrame({"t": hours}), how="cross")
    return grid(q, asof).select("coin", "t", "price", "price_source").sort("coin", "t")


# ---------------------------------------------------------------------------------------------- book
def _terms(ledger: pl.DataFrame, px: pl.DataFrame, asof: datetime) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Hourly PnL terms per (trader, coin, hour_end) and the position marks (trader, coin, mark, pos, price).

    The ledger must be core perps, ordered (positions.rebuild output). Only marks m with m + 1h <= asof.
    """
    last_end = floor_hour(asof)
    p = px.select(pl.col("coin").alias("symbol"), "t", "price")
    led = ledger.sort("trader", "symbol", "seq").with_columns(
        next_ts=pl.col("ts").shift(-1).over(["trader", "symbol"]),
        first_in_series=pl.int_range(pl.len()).over(["trader", "symbol"]) == 0,
        trip_after=pl.col("trip_no") + ((pl.col("pos_before") * pl.col("pos_after")) < 0).cast(pl.Int64),
    )
    # hold: marks m in [ts_i, next_ts_i) (or up to the last full hour), position after fill i
    lim = pl.lit(last_end - HOUR).dt.cast_time_unit("ms")
    hi = pl.when(pl.col("next_ts").is_null()).then(lim).otherwise(
        pl.min_horizontal((pl.col("next_ts") - pl.duration(milliseconds=1)).dt.truncate("1h"), lim))
    marks = (led.filter(pl.col("pos_after").abs() > 1e-9)
             .select("trader", "symbol", "src_row", "tid", "oid", pl.col("pos_after").alias("pos"),
                     pl.col("trip_after").alias("trip_no"), pl.col("price").alias("last_fill_px"),
                     m=pl.datetime_ranges(ceil_hour_expr(pl.col("ts")), hi.dt.cast_time_unit("ms"), "1h",
                                          closed="both"))
             .explode("m", empty_as_null=False).filter(pl.col("m").is_not_null())
             .with_columns(pl.col("m").dt.cast_time_unit("ms").dt.replace_time_zone("UTC"))
             .join(p.rename({"t": "m", "price": "p_m"}), on=["symbol", "m"], how="left")
             .with_columns(hour_end=(pl.col("m") + pl.duration(hours=1)).dt.cast_time_unit("ms"))
             .join(p.rename({"t": "hour_end", "price": "p_end"}), on=["symbol", "hour_end"], how="left"))
    hold = marks.select("trader", "symbol", "hour_end", "src_row",
                        term=pl.lit("hold"), pnl=pl.col("pos") * (pl.col("p_end") - pl.col("p_m")),
                        fee=pl.lit(0.0))
    fl = (led.with_columns(hour_end=ceil_hour_expr(pl.col("ts"))).filter(pl.col("hour_end") <= last_end)
          .join(p.rename({"t": "hour_end", "price": "p_end"}), on=["symbol", "hour_end"], how="left"))
    fill = fl.select("trader", "symbol", "hour_end", "src_row", term=pl.lit("fill"),
                     pnl=pl.when((pl.col("fee_token") == "USDC") | (pl.col("fee") == 0)).then(
                         pl.col("delta") * (pl.col("p_end") - pl.col("price")) - pl.col("fee")), fee=pl.col("fee"))
    inherit = fl.filter(pl.col("first_in_series") & (pl.col("pos_before").abs() > 1e-9)).select(
        "trader", "symbol", "hour_end", "src_row", term=pl.lit("inherit"),
        pnl=pl.col("pos_before") * (pl.col("p_end") - pl.col("price")), fee=pl.lit(0.0))
    terms = pl.concat([hold, fill, inherit]).sort("trader", "symbol", "hour_end", "term", "src_row")
    return terms, marks.sort("trader", "symbol", "m", "src_row")


def book_hourly(ledger: pl.DataFrame, px: pl.DataFrame, traders: pl.DataFrame, asof: datetime,
                funding: pl.DataFrame | None = None) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Per (trader, hour_end): book PnL (null if any term is unpriced), exposure at the mark, equity base.

    Returns (hourly, marks). Hours with neither a position nor a fill are absent (their PnL is exactly 0).
    """
    led = pit(ledger, asof)
    terms, marks = _terms(led, px, asof)
    if funding is not None:
        fund = funding.filter(pl.col("ts_hour") <= asof).select(
            "trader", symbol="coin", hour_end="ts_hour", src_row="src_row", term=pl.lit("funding"),
            pnl="payment", fee=pl.lit(0.0))
        terms = pl.concat([terms, fund]).sort("trader", "hour_end", "symbol", "term", "src_row")
    agg = terms.group_by("trader", "hour_end").agg(
        book_pnl_priced=pl.col("pnl").sum(), funding_paid=pl.col("pnl").filter(pl.col("term") == "funding").sum(),
        n_terms=pl.len(), n_unpriced_terms=pl.col("pnl").is_null().sum(),
        fees=pl.col("fee").sum(), first_src_row=pl.col("src_row").min(),
    )
    ex = marks.group_by("trader", "hour_end").agg(
        gross_exposure=(pl.col("pos").abs() * pl.col("p_m")).sum(),
        net_exposure=(pl.col("pos") * pl.col("p_m")).sum(),
        n_coins=pl.len(),
        unpriced_exposure_w=(pl.col("pos").abs() * pl.col("last_fill_px")).filter(pl.col("p_m").is_null()).sum(),
        exposure_w=(pl.col("pos").abs() * pl.col("last_fill_px")).sum(),
    )
    snaps = pit(traders, asof).sort("ts", "src_row").select(
        "trader", pl.col("ts").alias("eq_ts"), pl.col("equity").alias("equity_base"),
        pl.col("src_row").alias("equity_src_row"))
    h = (agg.join(ex, on=["trader", "hour_end"], how="full", coalesce=True)
         .with_columns(m=(pl.col("hour_end") - pl.duration(hours=1)).dt.cast_time_unit("ms"))
         .sort("m").join_asof(snaps, left_on="m", right_on="eq_ts", by="trader", strategy="backward",
                              check_sortedness=False))
    h = h.with_columns(
        pl.col("book_pnl_priced", "fees").fill_null(0.0), pl.col("n_terms", "n_unpriced_terms").fill_null(0),
        pl.col("gross_exposure", "net_exposure", "unpriced_exposure_w", "exposure_w").fill_null(0.0),
    ).with_columns(
        priced=pl.col("n_unpriced_terms") == 0,
    ).with_columns(
        book_pnl=pl.when("priced").then(pl.col("book_pnl_priced")),
        funding=pl.lit("included" if funding is not None else "omitted"),
    ).with_columns(
        book_ret=pl.when(pl.col("equity_base") > 0).then(pl.col("book_pnl") / pl.col("equity_base")),
        leverage=pl.when(pl.col("equity_base") > 0).then(pl.col("gross_exposure") / pl.col("equity_base")),
    )
    return (h.select("trader", "hour_end", "m", "book_pnl", "book_pnl_priced", "book_ret", "priced", "n_terms",
                     "n_unpriced_terms", "fees", "gross_exposure", "net_exposure", "n_coins", "exposure_w",
                     "unpriced_exposure_w", "leverage", "equity_base", "eq_ts", "equity_src_row",
                     "first_src_row", "funding_paid",
                     "funding").sort("trader", "hour_end"), marks)


def book_daily(hourly: pl.DataFrame, traders: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    """Calendar-day book PnL (hours ending in (d, d+1]), return on equity at the day start. Full days only."""
    h = hourly.with_columns(day=(pl.col("hour_end") - pl.duration(milliseconds=1)).dt.date())
    d = h.group_by("trader", "day").agg(
        book_pnl_priced=pl.col("book_pnl_priced").sum(), unpriced_hours=(~pl.col("priced")).sum(),
        hours=pl.len(), max_leverage=pl.col("leverage").max(),
    ).filter(pl.col("day") < asof.date())
    # complete calendar from each trader's first active day: missing days have exactly zero book PnL
    span = d.group_by("trader").agg(d0=pl.col("day").min()).with_columns(
        day=pl.date_ranges("d0", pl.lit(asof.date() - timedelta(days=1)), "1d")).explode("day").drop("d0")
    d = span.join(d, on=["trader", "day"], how="left").with_columns(
        pl.col("book_pnl_priced").fill_null(0.0), pl.col("unpriced_hours", "hours").fill_null(0),
        day_start=pl.col("day").cast(pl.Datetime("ms")).dt.replace_time_zone("UTC"))
    snaps = pit(traders, asof).sort("ts", "src_row").select(
        "trader", pl.col("ts").alias("eq_ts"), pl.col("equity").alias("equity_base"),
        pl.col("src_row").alias("equity_src_row"))
    d = d.sort("day_start").join_asof(snaps, left_on="day_start", right_on="eq_ts", by="trader",
                                      strategy="backward", check_sortedness=False)
    return d.with_columns(
        book_pnl=pl.when(pl.col("unpriced_hours") == 0).then(pl.col("book_pnl_priced")),
    ).with_columns(
        book_ret=pl.when(pl.col("equity_base") > 0).then(pl.col("book_pnl") / pl.col("equity_base")),
        funding=pl.lit(hourly["funding"][0] if hourly.height else "omitted"),
    ).select("trader", "day", "book_pnl", "book_pnl_priced", "book_ret", "unpriced_hours", "hours", "max_leverage",
             "equity_base", "eq_ts", "equity_src_row", "funding").sort("trader", "day")
