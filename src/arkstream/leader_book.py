"""Snapshot reconciliation and daily closing book on independent UTC boundary marks."""

import math
from datetime import datetime
from statistics import NormalDist

import numpy as np
import polars as pl

from arkstream.book_state import KEY, book_state
from arkstream.leader_marks import MS
from arkstream.positions import order_fills, pit
from arkstream.selection_stats import clopper_pearson

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
    g = rules["gates"]
    summary = (
        counts.join(per, on="trader", how="left")
        .join(agreement, on="trader", how="left")
        .join(fit_uncertainty(ok, float(g["fit_lower_conf"])), on="trader", how="left")
        .join(agreement_regression(ok.filter("usable"), float(g["book_corr_lower_conf"])), on="trader", how="left")
        .join(agreement_v2(ok.filter("usable"), rules), on="trader", how="left")
        .join(ok.group_by("trader").agg(fit_misses=(C("miss") > 0.01).sum()), on="trader", how="left")
        .with_columns(xc_n=C("xc_n").fill_null(0), fit_coverage=C("xc_n").fill_null(0) / C("intervals"))
        .with_columns(
            xc_flag=pl.when(C("agreement_n").fill_null(0) < rules["book"]["min_intervals"])
            .then(pl.lit("too_few_intervals"))
            .when(C("xc_corr").is_nan() | C("xc_corr").is_null())
            .then(pl.lit("no_variation"))
            # ADR-0069 gate 7 v2: 7a rank agreement, 7b steady-gap rate, 7c one-for-one slope, 7d tracking
            .when(C("xc_spearman_lower").fill_null(-1.0) < rules["book"]["min_corr"])
            .then(pl.lit("disagree_rank"))
            .when(C("xc_gap_rate_lower_bps").is_null())
            .then(pl.lit("gap_unmeasured"))  # fewer than two calendar weeks: unmeasured, never passes (ADR-0068)
            .when(C("xc_gap_rate_lower_bps") > rules["book"]["max_gap_bps_per_day"])
            .then(pl.lit("disagree_gap"))
            .when(~C("xc_ts_slope").is_between(*rules["book"]["slope_band"]).fill_null(False))
            .then(pl.lit("disagree_slope"))
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


def _run_max(flags: list[bool]) -> int:
    best = run = 0
    for f in flags:
        run = run + 1 if f else 0
        best = max(best, run)
    return best


def fit_uncertainty(ok: pl.DataFrame, conf: float) -> pl.DataFrame:
    """ADR-0067 gate 6: per address over fit-eligible intervals in time order, the one-sided `conf` Clopper-Pearson
    lower bound of the share within 1%, the longest run of consecutive misses and the lag-1 autocorrelation of the
    miss indicator (persistence)."""
    rows = []
    for (trader,), grp in ok.sort("trader", "ts", "src_row").group_by("trader", maintain_order=True):
        miss = (grp["miss"] > 0.01).to_list()
        n, k = len(miss), sum(1 for m in miss if not m)
        lo = clopper_pearson(k, n, alpha=1 - conf, two_sided=False)[0] if n else None
        x = np.asarray(miss, dtype=float)
        ac = None
        if n >= 3 and x[:-1].std() > 0 and x[1:].std() > 0:
            ac = float(np.corrcoef(x[:-1], x[1:])[0, 1])
        rows.append((trader, lo, _run_max(miss), ac))
    return pl.DataFrame(rows, schema={"trader": pl.String, "within_1pct_lower": pl.Float64,
                                      "fit_max_miss_run": pl.Int64, "fit_miss_autocorr": pl.Float64}, orient="row")


def agreement_regression(usable: pl.DataFrame, conf: float) -> pl.DataFrame:
    """ADR-0067 gate 7: per address, account return regressed on book return over the usable fit intervals: slope and
    intercept with 95% CIs, the normalised RMSE of (account - book), and the one-sided `conf` Fisher-z lower bound of
    the correlation."""
    z95, zc = NormalDist().inv_cdf(0.975), NormalDist().inv_cdf(conf)
    rows = []
    for (trader,), grp in usable.sort("trader", "ts", "src_row").group_by("trader", maintain_order=True):
        y, x = grp["r_start"].to_numpy().astype(float), grp["book_r"].to_numpy().astype(float)
        keep = np.isfinite(x) & np.isfinite(y)
        x, y = x[keep], y[keep]
        n = len(x)
        out = [trader, None, None, None, None, None, None, None]
        if n >= 4 and x.std() > 0 and y.std() > 0:
            b, a = np.polyfit(x, y, 1)
            resid = y - (a + b * x)
            s2 = float((resid ** 2).sum() / (n - 2))
            sxx = float(((x - x.mean()) ** 2).sum())
            se_b, se_a = math.sqrt(s2 / sxx), math.sqrt(s2 * (1 / n + x.mean() ** 2 / sxx))
            r = float(np.corrcoef(x, y)[0, 1])
            lo = math.tanh(math.atanh(max(min(r, 1 - 1e-12), -1 + 1e-12)) - zc / math.sqrt(n - 3))
            nrmse = float(np.sqrt(((y - x) ** 2).mean()) / y.std())
            out = [trader, float(b), float(b - z95 * se_b), float(b + z95 * se_b), float(a),
                   float(a - z95 * se_a), float(a + z95 * se_a), nrmse]
            out.append(lo)
        else:
            out.append(None)
        rows.append(tuple(out))
    schema = {"trader": pl.String, "xc_slope": pl.Float64, "xc_slope_lo": pl.Float64, "xc_slope_hi": pl.Float64,
              "xc_intercept": pl.Float64, "xc_intercept_lo": pl.Float64, "xc_intercept_hi": pl.Float64,
              "xc_nrmse": pl.Float64, "xc_corr_lower": pl.Float64}
    return pl.DataFrame(rows, schema=schema, orient="row")


def theil_sen(x: np.ndarray, y: np.ndarray) -> float | None:
    """Median of pairwise slopes over pairs with distinct x."""
    i, j = np.triu_indices(len(x), k=1)
    dx = x[j] - x[i]
    keep = dx != 0
    return float(np.median((y[j] - y[i])[keep] / dx[keep])) if keep.any() else None


def agreement_v2(usable: pl.DataFrame, rules: dict) -> pl.DataFrame:
    """ADR-0069 gate 7 v2 statistics per address over the usable fit intervals:
    7a Spearman rho with a one-sided Fisher-z lower bound (Bonett-Wright variance (1 + rho^2 / 2) / (n - 3));
    7b the gap rate sum(r_start - book_r) / sum(interval days), its week-clustered standard error and the one-sided
       lower bound of its absolute value, in bps per day; 7c the Theil-Sen slope of account on book.
    Reported: lag-1 autocorrelation of the residual and the three largest residual intervals (src_row)."""
    zc = NormalDist().inv_cdf(float(rules["gates"]["book_corr_lower_conf"]))
    zg = NormalDist().inv_cdf(float(rules["book"]["gap_lower_conf"]))
    rows = []
    for (trader,), grp in usable.sort("trader", "ts", "src_row").group_by("trader", maintain_order=True):
        g = grp.filter(C("r_start").is_not_null() & C("book_r").is_not_null())
        g = g.with_columns(days=(C("ts") - C("prev_ts")).dt.total_milliseconds() / 86_400_000,
                           week=C("ts").dt.truncate("1w"))
        y, x = g["r_start"].to_numpy().astype(float), g["book_r"].to_numpy().astype(float)
        ok = np.isfinite(x) & np.isfinite(y)
        g, x, y = g.filter(pl.Series(ok)), x[ok], y[ok]
        n = len(x)
        out: dict = {"trader": trader, "xc_spearman": None, "xc_spearman_lower": None, "xc_gap_rate_bps": None,
                     "xc_gap_rate_se_bps": None, "xc_gap_rate_lower_bps": None, "xc_ts_slope": None,
                     "xc_resid_autocorr": None, "xc_top_residual_rows": None}
        if n >= 4:
            rx = pl.Series(x).rank("average").to_numpy()
            ry = pl.Series(y).rank("average").to_numpy()
            if rx.std() > 0 and ry.std() > 0:
                rho = float(np.corrcoef(rx, ry)[0, 1])
                rc = max(min(rho, 1 - 1e-12), -1 + 1e-12)
                se = math.sqrt((1 + rho ** 2 / 2) / (n - 3))
                out["xc_spearman"], out["xc_spearman_lower"] = rho, math.tanh(math.atanh(rc) - zc * se)
            d = y - x
            days = g["days"].to_numpy().astype(float)
            if days.sum() > 0:
                rate = float(d.sum() / days.sum())
                e = d - rate * days
                wk = g["week"].to_physical().to_numpy()
                cl = np.array([e[wk == w].sum() for w in np.unique(wk)])
                se_g = float(math.sqrt((cl ** 2).sum()) / days.sum()) if len(cl) >= 2 else None
                out["xc_gap_rate_bps"] = rate * 1e4
                if se_g is not None:
                    out["xc_gap_rate_se_bps"] = se_g * 1e4
                    out["xc_gap_rate_lower_bps"] = (abs(rate) - zg * se_g) * 1e4
            out["xc_ts_slope"] = theil_sen(x, y)
            if d[:-1].std() > 0 and d[1:].std() > 0:
                out["xc_resid_autocorr"] = float(np.corrcoef(d[:-1], d[1:])[0, 1])
            top = np.argsort(-np.abs(d), kind="stable")[:3]
            out["xc_top_residual_rows"] = ";".join(str(int(g["src_row"][int(k)])) for k in top)
        rows.append(out)
    schema = {"trader": pl.String, "xc_spearman": pl.Float64, "xc_spearman_lower": pl.Float64,
              "xc_gap_rate_bps": pl.Float64, "xc_gap_rate_se_bps": pl.Float64, "xc_gap_rate_lower_bps": pl.Float64,
              "xc_ts_slope": pl.Float64, "xc_resid_autocorr": pl.Float64, "xc_top_residual_rows": pl.String}
    return pl.DataFrame(rows, schema=schema, orient="row")
