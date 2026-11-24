"""Accounting reconciliation, point in time.

1. Snapshot identity: pnl vs equity - net_deposit, per row and per address.
2. Fill identity: venue closed_pnl vs average-cost realized PnL rebuilt from fills.
Differences are reported as *unexplained reconciliation differences*. They mix funding, pricing,
account scope (isolated / non-cross positions) and entry-price rounding; they bound none of them and
are never used as a funding estimate.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from arkstream.positions import pit


def snapshot_rows(traders: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    return pit(traders, asof).with_columns(
        pnl_identity_diff=pl.col("pnl") - (pl.col("equity") - pl.col("net_deposit"))
    )


def snapshot_summary(traders: pl.DataFrame, asof: datetime, tight: float, loose: float,
                     material: dict | None = None) -> pl.DataFrame:
    """Per address. `material` (ADR-0066, config `grades.B`) adds the materiality-based offset statistics."""
    rows = snapshot_rows(traders, asof)
    d = pl.col("pnl_identity_diff")
    extra: list[pl.Expr] = []
    if material is not None:
        e = pl.col("equity")
        bound = pl.max_horizontal(pl.lit(float(material["material_abs_usdc"])),
                                  pl.when(e > 0).then(e * material["material_rel_equity"]).otherwise(0.0))
        scale = pl.max_horizontal(e.median(), pl.lit(float(material["offset_scale_floor_usdc"])))
        n, half = pl.len(), pl.len() // 2
        idx = pl.int_range(pl.len())
        extra = [
            (d.abs() <= bound).mean().alias("material_match_share"),
            (d.abs() > bound).sum().alias("pnl_rows_material"),
            (d.median().abs() / scale).alias("offset_level"),
            ((d - d.median()).abs().median() / scale).alias("offset_mad"),
            ((d - d.median()).abs() <= bound).mean().alias("offset_match_share"),
            pl.when(n >= 4).then((d.filter(idx >= half).median() - d.filter(idx < half).median()).abs() / scale)
            .alias("offset_shift"),
        ]
    return (rows.sort("trader", "ts", "src_row").group_by("trader", maintain_order=True).agg(
        *extra,
        n_snapshots=pl.len(),
        pnl_rows_gt_tight=(d.abs() > tight).sum(),
        pnl_rows_gt_loose=(d.abs() > loose).sum(),
        pnl_match_share=(d.abs() <= tight).mean(),
        pnl_diff_mean=d.mean(),
        pnl_diff_std=d.std(),
        pnl_diff_last=d.last(),
        pnl_larger_when_loose=((d > loose).sum() == (d.abs() > loose).sum()),
        first_mismatch_src_row=pl.col("src_row").filter(d.abs() > tight).first(),
        first_mismatch_ts=pl.col("ts").filter(d.abs() > tight).first(),
    ).with_columns(
        pnl_offset_cv=pl.when(pl.col("pnl_diff_mean").abs() > 0)
        .then(pl.col("pnl_diff_std") / pl.col("pnl_diff_mean").abs()).otherwise(None)
    ))


def fill_summary(ledger: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    """Per address: sum of closed_pnl vs rebuilt realized PnL on fills where the entry is known."""
    led = pit(ledger, asof)
    known = pl.col("rebuilt_realized").is_not_null()
    diff = (pl.col("rebuilt_realized") - pl.col("closed_pnl"))
    tol = 0.01 + 1e-6 * pl.col("notional")
    return led.group_by("trader").agg(
        closed_pnl_total=pl.col("closed_pnl").sum(),
        closed_pnl_known=pl.col("closed_pnl").filter(known).sum(),
        rebuilt_realized_known=pl.col("rebuilt_realized").filter(known).sum(),
        fills_unknown_entry=(~known).sum(),
        fills_pnl_mismatch=(known & (diff.abs() > tol)).sum(),
        first_pnl_mismatch_src_row=pl.col("src_row").filter(known & (diff.abs() > tol)).min(),
    ).with_columns(
        realized_diff=pl.col("rebuilt_realized_known") - pl.col("closed_pnl_known"),
        realized_diff_rel=(pl.col("rebuilt_realized_known") - pl.col("closed_pnl_known")).abs()
        / pl.max_horizontal(pl.col("closed_pnl_known").abs(), pl.lit(1.0)),
    ).sort("trader")


def headline(traders: pl.DataFrame, asof: datetime, tight: float, loose: float) -> dict[str, int]:
    rows = snapshot_rows(traders, asof)
    d = pl.col("pnl_identity_diff").abs()
    return {
        "pnl_rows_gt_tight": rows.filter(d > tight).height,
        "pnl_addresses_gt_tight": rows.filter(d > tight)["trader"].n_unique(),
        "pnl_addresses_gt_loose": rows.filter(d > loose)["trader"].n_unique(),
        "pnl_rows_gt_loose_pnl_smaller": rows.filter(pl.col("pnl_identity_diff") < -loose).height,
    }
