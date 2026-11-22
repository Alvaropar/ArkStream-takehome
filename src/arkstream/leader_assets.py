"""Primary address returns, cross-margin snapshot checks and daily exposure (ADRs 0063, 0065)."""

from datetime import datetime

import numpy as np
import polars as pl

C = pl.col
SNAPSHOT = "cross_margin_snapshot"
BOOK = "rebuilt_core_perp_book"


def twr_series(acc: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    s = acc.filter(C("ts") <= asof).sort("trader", "ts", "src_row")
    for convention in ("start", "end"):
        r = C("r_" + convention)
        s = s.with_columns(pl.when("usable").then(1 + r).cum_prod().over("trader").alias("index_" + convention))
    return s.with_columns(
        flow_timing=pl.when("multi_day").then(pl.lit("unknown_inside_gap")).otherwise(pl.lit("daily_conventions")),
        price_source=pl.lit("hyperliquid_snapshot"),
        validation=pl.lit("unvalidated"),
        return_source=pl.lit(SNAPSHOT),
    )


def primary_source() -> pl.Expr:
    """ADR-0065 (superseded for the choice by ADR-0111): any snapshot beyond the tight tolerance selects the book.
    Kept to report the old rule next to the new one."""
    return pl.when(C("pnl_rows_gt_tight") > 0).then(pl.lit(BOOK)).otherwise(pl.lit(SNAPSHOT))


def identity_breaches(traders: pl.DataFrame, asof: datetime, rule: dict) -> tuple[pl.DataFrame, pl.DataFrame]:
    """ADR-0111. Per snapshot known by asof: `breach` when abs(pnl - (equity - net_deposit)) > max(abs floor,
    relative share of equity). Per address: snapshots, breaches, breach share and the longest run of consecutive
    breaching snapshots (in time order)."""
    from arkstream.positions import pit

    diff = C("pnl") - (C("equity") - C("net_deposit"))
    bound = pl.max_horizontal(pl.lit(float(rule["breach_abs_usdc"])), float(rule["breach_rel_equity"]) * C("equity"))
    s = (
        pit(traders, asof).sort("trader", "ts", "src_row")
        .with_columns(pnl_identity_diff=diff)
        .with_columns(breach=(C("pnl_identity_diff").abs() > bound).fill_null(False))
        .with_columns(run=(C("breach") != C("breach").shift().over("trader")).fill_null(True).cum_sum().over("trader"))
    )
    runs = s.filter("breach").group_by("trader", "run").agg(n=pl.len()).group_by("trader").agg(
        pnl_breach_max_run=C("n").max())
    per = (
        s.group_by("trader").agg(pnl_snapshots=pl.len(), pnl_breaches=C("breach").sum())
        .join(runs, on="trader", how="left")
        .with_columns(C("pnl_breach_max_run").fill_null(0).cast(pl.UInt32))
        .with_columns(pnl_breach_share=C("pnl_breaches") / C("pnl_snapshots"))
        .sort("trader")
    )
    return s.select("trader", "ts", "src_row", "pnl_identity_diff", "breach"), per


def material_source(rule: dict) -> pl.Expr:
    """ADR-0111: the rebuilt book is primary only on material and persistent breaches known by the origin."""
    persistent = (C("pnl_breach_share") >= float(rule["book_min_breach_share"])) | (
        C("pnl_breach_max_run") >= int(rule["book_min_breach_run"]))
    return pl.when(persistent.fill_null(False)).then(pl.lit(BOOK)).otherwise(pl.lit(SNAPSHOT))


def exclude_breaches(acc: pl.DataFrame, breach_rows: pl.Series, traders: pl.Series) -> pl.DataFrame:
    """ADR-0111: intervals of the given addresses whose opening or closing snapshot breaches leave the series."""
    rows = breach_rows.implode()
    hit = C("trader").is_in(traders.implode()) & (C("src_row").is_in(rows) | C("prev_src_row").is_in(rows))
    return acc.with_columns(
        exclude_reason=pl.when(hit & C("usable")).then(pl.lit("pnl_identity_breach")).otherwise("exclude_reason"),
        usable=C("usable") & ~hit,
    )


def book_check(daily_book: pl.DataFrame, frozen_rows: pl.Series, asof: datetime, min_equity: float) -> pl.DataFrame:
    """ADR-0111 item 4: the funded book compounded over its usable days (ADR-0065 exclusions), for every address."""
    ok = daily_book.filter(
        (C("ts") <= asof) & (C("missing_terms") == 0) & C("equity_base").is_not_null()
        & ~C("equity_src_row").is_in(frozen_rows.implode()) & (C("equity_base") >= min_equity)
        & C("book_ret").is_not_null()
    )
    return ok.sort("trader", "ts").group_by("trader", maintain_order=True).agg(
        book_twr_check=(1 + C("book_ret")).product() - 1, book_days_check=pl.len())


def primary_series(
    snapshot: pl.DataFrame, daily_book: pl.DataFrame, universe: pl.DataFrame,
    frozen_rows: pl.Series, asof: datetime, min_equity: float,
) -> pl.DataFrame:
    """Use one series for the address's entire history at this origin, including unmeasured days."""
    keep_book = universe.filter(C("return_source") == BOOK).select("trader")
    snap = snapshot.filter(C("ts") <= asof).join(keep_book, on="trader", how="anti")
    reason = (
        pl.when(C("missing_terms") > 0).then(pl.lit("incomplete_core_book"))
        .when(C("equity_base").is_null()).then(pl.lit("missing_opening_equity"))
        .when(C("equity_src_row").is_in(frozen_rows.implode())).then(pl.lit("frozen_opening_equity"))
        .when(C("equity_base") < min_equity).then(pl.lit("opening_equity_below_min"))
        .when(C("book_ret").is_null()).then(pl.lit("unmeasured_book_return"))
        .otherwise(pl.lit(""))
    )
    book = (
        daily_book.filter(C("ts") <= asof).join(keep_book, on="trader", how="semi")
        .select("trader", "ts", "book_pnl", "funding_paid", "equity_src_row", "eq_ts", "price_source", "validation",
                prev_ts="day_start", prev_date="day", date=C("ts").dt.date(), period_days=pl.lit(1, pl.Int64),
                prev_equity="equity_base", den_start="equity_base", gap_days=pl.lit(1.0), multi_day=pl.lit(False),
                r_start="book_ret", exclude_reason=reason, return_source=pl.lit(BOOK),
                flow_timing=pl.lit("funded_pnl_on_opening_equity"))
        .with_columns(usable=C("exclude_reason") == "")
        .with_columns(r_start=pl.when("usable").then("r_start"))
        .sort("trader", "ts")
        .with_columns(index_start=(1 + C("r_start")).cum_prod().over("trader"))
    )
    return (pl.concat([snap, book], how="diagonal_relaxed").sort("trader", "ts", "src_row")
            .with_columns(opening_index=C("index_start").forward_fill().shift().over("trader").fill_null(1.0)))


def gap_path(series: pl.DataFrame, snapshots: pl.DataFrame, daily: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    """Interim wealth relative to the actual opening snapshot, on the start-flow base."""
    iv = series.filter(C("multi_day") & C("usable") & (C("ts") <= asof)).join(
        snapshots.select(
            "trader",
            prev_src_row="src_row",
            opening_value="value",
            opening_funding="funding_total",
            opening_missing="unpriced",
            opening_rates="unknown_rates",
            opening_fees="bad_fees",
        ),
        on=["trader", "prev_src_row"],
    )
    iv = iv.with_columns(
        t=pl.datetime_ranges(
            C("prev_ts").dt.truncate("1d").dt.offset_by("1d"), C("ts") - pl.duration(milliseconds=1), "1d"
        )
    )
    j = iv.explode("t", empty_as_null=False).join(
        daily.select(
            "trader",
            t="ts",
            value="value",
            fund="funding_total",
            rates="unknown_rates",
            bad="bad_fees",
            unpriced="unpriced",
            flagged="flagged",
            unvalidated="unvalidated",
        ),
        on=["trader", "t"],
        how="left",
    )
    return (
        j.select(
            "trader",
            "prev_ts",
            "ts",
            "prev_src_row",
            "src_row",
            "t",
            "flow_timing",
            trading_pnl=pl.when(
                (C("scope") == "checkable")
                & (C("opening_missing") + C("unpriced") == 0)
                & (C("opening_rates") == C("rates"))
                & (C("opening_fees") == C("bad"))
            ).then(C("value") - C("opening_value") + C("fund") - C("opening_funding")),
            opening_index="opening_index",
            den_start="den_start",
            price_source=pl.lit("hyperliquid_4h"),
            validation=pl.when(C("unvalidated").fill_null(True))
            .then(pl.lit("unvalidated"))
            .when("flagged")
            .then(pl.lit("flagged"))
            .otherwise(pl.lit("validated")),
        )
        .with_columns(wealth=C("opening_index") * (1 + C("trading_pnl") / C("den_start")))
        .sort("trader", "t", "src_row")
    )


def _se(scores: np.ndarray) -> np.ndarray:
    # Bartlett HAC, at most seven observations. Scores are already scaled for the estimator.
    n = len(scores)
    lag = min(7, n - 1)
    meat = scores.T @ scores
    for k in range(1, lag + 1):
        cross = scores[k:].T @ scores[:-k]
        meat += (1 - k / (lag + 1)) * (cross + cross.T)
    return np.sqrt(np.maximum(np.diag(meat), 0))


def exposure(y: np.ndarray, btc: np.ndarray, eth: np.ndarray) -> dict:
    n = len(y)
    out = dict.fromkeys(
        (
            "alpha",
            "alpha_lo",
            "alpha_hi",
            "beta_btc",
            "beta_btc_lo",
            "beta_btc_hi",
            "beta_eth",
            "beta_eth_lo",
            "beta_eth_hi",
            "r_squared",
        )
    )
    x = np.column_stack((np.ones(n), btc, eth))
    if n < 4 or np.linalg.matrix_rank(x) < 3:
        return out
    inverse = np.linalg.pinv(x)
    coef = inverse @ y
    residual = y - x @ coef
    se = _se(inverse.T * residual[:, None]) * np.sqrt(n / (n - 3))
    for name, b, err in zip(("alpha", "beta_btc", "beta_eth"), coef, se, strict=True):
        out.update({name: b, name + "_lo": b - 1.96 * err, name + "_hi": b + 1.96 * err})
    total = ((y - y.mean()) ** 2).sum()
    out["r_squared"] = float(1 - residual @ residual / total) if total > 0 else None
    return out


def asset_tables(
    series: pl.DataFrame, day: pl.DataFrame, gap: pl.DataFrame, cov: pl.DataFrame, asof: datetime
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    factor = (
        day.filter((C("t") <= asof) & C("coin").is_in(["BTC", "ETH"]))
        .sort("coin", "t")
        .with_columns(
            pair_validation=pl.when(
                (C("validation") == "unvalidated") | (C("validation").shift().over("coin") == "unvalidated")
            )
            .then(pl.lit("unvalidated"))
            .when((C("validation") == "flagged") | (C("validation").shift().over("coin") == "flagged"))
            .then(pl.lit("flagged"))
            .otherwise(pl.lit("validated")),
            r=pl.when(C("t").diff().over("coin") == pl.duration(days=1)).then(
                C("price") / C("price").shift().over("coin") - 1
            ),
        )
    )
    daily = series.filter(C("usable") & (C("period_days") == 1) & (C("ts") <= asof)).with_columns(
        factor_ts=C("ts").dt.round("1d")
    )
    for coin in ("BTC", "ETH"):
        daily = daily.join(
            factor.filter(C("coin") == coin).select(
                "t", C("r").alias(coin), C("pair_validation").alias(coin + "_validation")
            ),
            left_on="factor_ts",
            right_on="t",
            how="left",
        )
    sample = (
        daily.drop_nulls(["BTC", "ETH"])
        .filter(C("factor_ts") - C("prev_ts").dt.round("1d") == pl.duration(days=1))
        .sort("trader", "ts")
    )
    fits = []
    for (trader,), g in sample.group_by("trader", maintain_order=True):
        fits.append(
            {"trader": trader, "n_days": len(g), **exposure(*[g[c].to_numpy() for c in ("r_start", "BTC", "ETH")])}
        )
    coef = {k: pl.Float64 for k in exposure(np.array([]), np.array([]), np.array([]))}
    market = (
        cov.select("trader", "calendar_days")
        .join(pl.DataFrame(fits, schema={"trader": pl.String, "n_days": pl.Int64, **coef}), on="trader", how="left")
        .with_columns(C("n_days").fill_null(0))
        .with_columns(market_coverage=C("n_days") / C("calendar_days").clip(1))
    )
    risk = []
    for (trader,), g in daily.sort("trader", "ts").group_by("trader", maintain_order=True):
        y = g["r_start"].to_numpy()
        vol = y.std(ddof=1) if len(y) > 1 else None
        sr = lo = hi = None
        if vol and vol > 0:
            z = (y - y.mean()) / vol
            sr = y.mean() / vol
            err = _se((z - 0.5 * sr * (z * z - (z * z).mean()))[:, None] / len(y))[0]
            lo, hi = sr - 1.96 * err, sr + 1.96 * err
        risk.append((trader, len(y), vol, sr, lo, hi))
    stats = pl.DataFrame(
        risk,
        orient="row",
        schema={
            "trader": pl.String,
            "daily_n": pl.Int64,
            "daily_vol": pl.Float64,
            "daily_sharpe": pl.Float64,
            "sharpe_lo": pl.Float64,
            "sharpe_hi": pl.Float64,
        },
    )
    ends = (
        series.filter("usable")
        .sort("trader", "ts", "src_row")
        .group_by("trader")
        .agg(twr=C("index_start").last() - 1, twr_end=C("index_end").last() - 1, last_src_row=C("src_row").last())
    )
    path = (
        pl.concat([series.select("trader", "ts", wealth="index_start"), gap.select("trader", ts="t", wealth="wealth")])
        .drop_nulls()
        .sort("trader", "ts")
    )
    dd = (
        path.with_columns(dd=C("wealth") / C("wealth").cum_max().over("trader").clip(1) - 1)
        .group_by("trader")
        .agg(twr_max_dd=C("dd").min().clip(upper_bound=0))
    )
    gc = gap.group_by("trader").agg(gap_marks=pl.len(), gap_marks_priced=C("wealth").count())
    summary = (
        cov.join(ends, on="trader", how="left")
        .join(stats, on="trader", how="left")
        .join(dd, on="trader", how="left")
        .join(gc, on="trader", how="left")
        .with_columns(C("daily_n", "gap_marks", "gap_marks_priced").fill_null(0))
    )
    return summary.sort("trader"), market.sort("trader"), sample
