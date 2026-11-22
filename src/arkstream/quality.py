"""Coverage flags, grades and the per-address quality report, point in time.

Every flag has (a) a column in the quality report, (b) a `<flag>_first_src_row` pointer, and (c) rows in
the long evidence table (trader, flag, file, src_row, ts, tid, oid) listing every raw row behind it.
Grade thresholds are placeholders in config/decision_context.yaml, fixed on development data only.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import polars as pl

from arkstream.book_state import book_state
from arkstream.positions import is_flat, pit

EVIDENCE_SCHEMA = {"trader": pl.String, "flag": pl.String, "file": pl.String, "src_row": pl.Int64,
                   "ts": pl.Datetime("ms", "UTC"), "tid": pl.Int64, "oid": pl.Int64, "detail": pl.String}


def _evidence(df: pl.DataFrame, flag: str, file: str, detail: pl.Expr | None = None) -> pl.DataFrame:
    cols = df.columns
    return df.select(
        pl.col("trader"), pl.lit(flag).alias("flag"), pl.lit(file).alias("file"), pl.col("src_row"),
        pl.col("ts"),
        (pl.col("tid") if "tid" in cols else pl.lit(None, pl.Int64)).alias("tid"),
        (pl.col("oid") if "oid" in cols else pl.lit(None, pl.Int64)).alias("oid"),
        (detail if detail is not None else pl.lit("")).cast(pl.String).alias("detail"),
    )


def snapshot_flags(traders: pl.DataFrame, asof: datetime, cfg: dict) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Per-snapshot flags (gaps, outage, stale, zero) and their evidence rows."""
    cov = cfg["coverage"]
    o0, o1 = date.fromisoformat(cov["outage_start"]), date.fromisoformat(cov["outage_end"])
    s = pit(traders, asof).sort("trader", "ts", "src_row").with_columns(
        prev_src_row=pl.col("src_row").shift().over("trader"),
        prev_ts=pl.col("ts").shift().over("trader"),
        prev_date=pl.col("date").shift().over("trader"),
        prev_equity=pl.col("equity").shift().over("trader"),
    ).with_columns(
        gap_days=(pl.col("ts") - pl.col("prev_ts")).dt.total_milliseconds() / 86_400_000,
    ).with_columns(
        is_gap=pl.col("gap_days") > cov["snapshot_gap_days"],
        stale=pl.col("equity") == pl.col("prev_equity"),
        zero_equity=pl.col("equity") == 0,
        near_zero=pl.col("equity").abs() < cfg["grades"]["C"]["near_zero_equity_usdc"],
    ).with_columns(
        # gap that bridges the whole outage window: last snapshot before it, next one after it
        outage_spanned=pl.col("is_gap") & (pl.col("prev_date") < o0) & (pl.col("date") > o1),
        # the outage is the whole gap: snapshot the day before and the day after
        outage_exact=pl.col("is_gap") & (pl.col("prev_date") == o0 - timedelta(days=1))
        & (pl.col("date") == o1 + timedelta(days=1)),
    )
    ev = pl.concat([
        _evidence(s.filter("is_gap"), "snapshot_gap", "traders.csv",
                  pl.format("gap {} d since {}", pl.col("gap_days").round(3), pl.col("prev_ts"))),
        _evidence(s.filter("outage_exact"), "outage_exact", "traders.csv"),
        _evidence(s.filter("outage_spanned"), "outage_spanned", "traders.csv"),
        _evidence(s.filter("stale"), "stale_equity", "traders.csv"),
        _evidence(s.filter("zero_equity"), "zero_equity", "traders.csv"),
    ])
    return s, ev


def frozen_flags(snaps: pl.DataFrame, ledger: pl.DataFrame, fills: pl.DataFrame, asof: datetime,
                 ref: pl.LazyFrame, passing: list[str]) -> pl.DataFrame:
    stale = pit(snaps, asof).filter("stale")
    endpoints = pl.concat([stale.select("trader", "ts", "src_row"),
                           stale.select("trader", ts="prev_ts", src_row="prev_src_row")]).unique()
    state, _ = book_state(endpoints, ledger, asof, ref, passing, fills)
    prev = state.select("trader", prev_src_row="src_row", prev_value="value", prev_unpriced="unpriced",
                        prev_bad_fees="bad_fees")
    moved = (stale.join(state, on=["trader", "ts", "src_row"]).join(prev, on=["trader", "prev_src_row"])
             .filter((pl.col("unpriced") == 0) & (pl.col("prev_unpriced") == 0)
                     & (pl.col("bad_fees") == pl.col("prev_bad_fees"))
                     & ((pl.col("value") - pl.col("prev_value")).abs() > 0.000001)))
    return snaps.with_columns(frozen=pl.col("src_row").is_in(moved["src_row"].implode()))


def open_position_timeline(ledger: pl.DataFrame) -> pl.DataFrame:
    """Number of coins with a non-zero position per trader after each fill (for as-of joins)."""
    first = pl.int_range(pl.len()).over(["trader", "symbol"]) == 0
    led = ledger.with_columns(
        was=(pl.col("pos_before").abs() > 1e-9).cast(pl.Int64),
        now=(pl.col("pos_after").abs() > 1e-9).cast(pl.Int64),
    ).with_columns(d_open=pl.col("now") - pl.when(first).then(0).otherwise(pl.col("was")))
    return (led.sort("trader", "ts", "symbol", "seq").with_columns(n_open=pl.col("d_open").cum_sum().over("trader"))
            .group_by("trader", "ts", maintain_order=True).agg(pl.col("n_open").last())
            .sort("trader", "ts"))


def coverage_to_origin(stats: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    return stats.with_columns(
        calendar_days=(pl.lit(asof.date()) - pl.col("first_date")).dt.total_days() + 1,
    ).with_columns(
        days_present_share=pl.col("days_present") / pl.col("calendar_days"),
        unusable_day_share=1 - pl.col("usable_days") / pl.col("calendar_days"),
        days_to_asof=pl.col("calendar_days"),
    )


def address_table(traders: pl.DataFrame, snaps: pl.DataFrame, ledger: pl.DataFrame, fills: pl.DataFrame,
                  recon_snap: pl.DataFrame, recon_fill: pl.DataFrame, copier_clusters: pl.DataFrame,
                  asof: datetime, cfg: dict) -> tuple[pl.DataFrame, pl.DataFrame]:
    """One row per address seen in either file up to asof, one column per flag."""
    grace = timedelta(days=cfg["coverage"]["dropout_grace_days"])
    fills_pit = pit(fills, asof)
    led = pit(ledger, asof)

    universe = pl.concat([snaps.select("trader"), fills_pit.select("trader")]).unique().sort("trader")

    # zero-equity snapshots taken while holding positions
    tl = open_position_timeline(led)
    zs = snaps.filter("zero_equity").sort("trader", "ts")
    zs = zs.join_asof(tl.rename({"ts": "pos_ts"}), left_on="ts", right_on="pos_ts", by="trader",
                      strategy="backward", check_sortedness=False).with_columns(
        holding=pl.col("n_open").fill_null(0) > 0)
    zero_hold = zs.filter("holding")

    s = snaps.group_by("trader").agg(
        n_snapshots=pl.len(), first_snapshot=pl.col("ts").min(), last_snapshot=pl.col("ts").max(),
        days_present=pl.col("date").n_unique(),
        first_date=pl.col("date").min(), last_date=pl.col("date").max(),
        n_snapshot_gaps=pl.col("is_gap").sum(), max_gap_days=pl.col("gap_days").max(),
        snapshot_gap_first_src_row=pl.col("src_row").filter("is_gap").first(),
        outage_exact=pl.col("outage_exact").any(), outage_spanned=pl.col("outage_spanned").any(),
        outage_first_src_row=pl.col("src_row").filter("outage_spanned").first(),
        stale_equity_rows=pl.col("stale").sum(), stale_equity_first_src_row=pl.col("src_row").filter("stale").first(),
        zero_equity_rows=pl.col("zero_equity").sum(),
        zero_equity_first_src_row=pl.col("src_row").filter("zero_equity").first(),
        near_zero_equity_share=pl.col("near_zero").mean(),
        median_equity=pl.col("equity").median(),
        frozen_rows=pl.col("frozen").sum(),
        frozen_first_src_row=pl.col("src_row").filter("frozen").first(),
        usable_days=pl.col("date").filter(~pl.col("near_zero") & ~pl.col("frozen")).n_unique(),
    ).with_columns(
        dropped_out=pl.col("last_snapshot") < pl.lit(asof - grace),
        joined_date=pl.col("first_date"),
    )
    s = coverage_to_origin(s, asof)
    zh = zero_hold.group_by("trader").agg(zero_equity_holding_rows=pl.len(),
                                          zero_equity_holding_first_src_row=pl.col("src_row").first())
    f = fills_pit.group_by("trader").agg(
        n_fills=pl.len(), n_perp_fills=pl.col("is_perp").sum(),
        eligible_notional_share=pl.col("notional").filter("eligible").sum() / pl.col("notional").sum(),
        maker_share=pl.col("is_maker").mean(), first_fill=pl.col("ts").min(), last_fill=pl.col("ts").max(),
        non_trade_events=(pl.col("event_kind") == "non_trade").sum(),
    )
    c = led.group_by("trader").agg(
        continuity_breaks=pl.col("continuity_break").sum(),
        continuity_break_first_src_row=pl.col("src_row").filter("continuity_break").first(),
        unresolved_chains=(~pl.col("chain_resolved")).sum(),
        mixed_ms_groups=(pl.col("group_kind") == "mixed").sum(),
    )
    rs = recon_snap.select("trader", "pnl_match_share", "pnl_rows_gt_tight", "pnl_rows_gt_loose", "pnl_diff_mean",
                           "pnl_offset_cv", "pnl_larger_when_loose",
                           pl.col("first_mismatch_src_row").alias("pnl_mismatch_first_src_row"))
    rf = recon_fill.select("trader", "closed_pnl_total", "rebuilt_realized_known", "closed_pnl_known",
                           "realized_diff", "realized_diff_rel", "fills_unknown_entry", "fills_pnl_mismatch",
                           pl.col("first_pnl_mismatch_src_row").alias("realized_mismatch_first_src_row"))
    cl = copier_clusters.select("trader", pl.col("cluster_id").alias("copier_cluster"),
                                pl.col("cluster_size").alias("copier_cluster_size"),
                                pl.col("is_original").alias("copier_is_original"))

    t = (universe.join(s, on="trader", how="left").join(zh, on="trader", how="left")
         .join(f, on="trader", how="left").join(c, on="trader", how="left")
         .join(rs, on="trader", how="left").join(rf, on="trader", how="left").join(cl, on="trader", how="left"))
    t = t.with_columns(
        pl.col("n_fills", "n_perp_fills", "zero_equity_holding_rows", "continuity_breaks", "unresolved_chains",
               "mixed_ms_groups", "non_trade_events").fill_null(0),
        no_snapshots=pl.col("n_snapshots").is_null(),
        copier_flag=pl.col("copier_cluster").is_not_null(),
        copier_is_original=pl.col("copier_is_original").fill_null(False),
    ).with_columns(no_fills=pl.col("n_fills") == 0)

    ev = pl.concat([
        _evidence(zero_hold, "zero_equity_while_holding", "traders.csv"),
        _evidence(led.filter("continuity_break"), "continuity_break", "fills.csv"),
    ])
    return t, ev


def grade(table: pl.DataFrame, cfg: dict) -> pl.DataFrame:
    """A: trustworthy as is; B: usable with a stated fix; C: excluded, with the reason."""
    g = cfg["grades"]
    a, b, cc = g["A"], g["B"], g["C"]
    stable_offset = pl.col("pnl_offset_cv").is_not_null() & (pl.col("pnl_offset_cv") <= b["max_offset_cv"])
    c_reasons = [
        (pl.col("no_snapshots"), "no_snapshots"),
        (pl.col("no_fills"), "no_fills"),
        (pl.col("continuity_breaks") > 0, "continuity_break"),
        (pl.col("near_zero_equity_share") > cc["max_near_zero_equity_share"], "equity_near_zero"),
        (pl.col("unusable_day_share") > b["max_unusable_day_share"], "too_many_unusable_days"),
        ((pl.col("pnl_match_share") < a["min_pnl_match_share"]) & ~stable_offset, "unstable_scope_mismatch"),
    ]
    b_reasons = [
        (pl.col("days_present_share") < a["min_days_present_share"], "snapshot_gaps:use_multi_day_returns"),
        ((pl.col("pnl_match_share") < a["min_pnl_match_share"]) & stable_offset,
         "stable_scope_offset:use_rebuilt_book"),
        (pl.col("zero_equity_holding_rows") > a["max_zero_equity_days_with_position"],
         "zero_equity_while_holding:use_rebuilt_book"),
    ]

    def reasons(pairs: list[tuple[pl.Expr, str]]) -> pl.Expr:
        return pl.concat_list([pl.when(cond.fill_null(False)).then(pl.lit(name)).otherwise(None)
                               for cond, name in pairs]).list.drop_nulls()

    return table.with_columns(c_reasons=reasons(c_reasons), b_reasons=reasons(b_reasons)).with_columns(
        grade=pl.when(pl.col("c_reasons").list.len() > 0).then(pl.lit("C"))
        .when(pl.col("b_reasons").list.len() > 0).then(pl.lit("B")).otherwise(pl.lit("A")),
    ).with_columns(
        grade_reason=pl.when(pl.col("grade") == "C").then(pl.col("c_reasons").list.join(";"))
        .when(pl.col("grade") == "B").then(pl.col("b_reasons").list.join(";")).otherwise(pl.lit("")),
    ).drop("c_reasons", "b_reasons")


def headline(snaps: pl.DataFrame, table: pl.DataFrame) -> dict[str, int]:
    return {
        "snapshot_gaps_gt_1_5d": int(snaps["is_gap"].sum()),
        "outage_exact_addresses": int(table["outage_exact"].fill_null(False).sum()),
        "outage_spanned_addresses": int(table["outage_spanned"].fill_null(False).sum()),
        "frozen_snapshot_rows": int(snaps["frozen"].sum()),
        "stale_equity_rows": int(snaps["stale"].sum()),
        "zero_equity_rows": int(snaps["zero_equity"].sum()),
        "no_fill_addresses": int(table["no_fills"].sum()),
    }


__all__ = ["address_table", "grade", "headline", "is_flat", "open_position_timeline", "snapshot_flags"]
