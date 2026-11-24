"""Instrument classes and fill-event kinds (data hygiene; rules in config/instruments.yaml).

core_perp: default; spot: '@n' and explicit pairs such as 'PURR/USDC'; hip3: 'dex:SYMBOL'.
Only `eligible_classes` may ever be selected or traded. Spot Dust Conversion rows are kept as
non-trade events (event_kind='non_trade'), never deleted.
"""

from __future__ import annotations

from typing import Any

import polars as pl

FILL_KEY = ["trader", "tid", "oid", "ts", "symbol", "dir"]
FORCED_DIRS = ("Auto-Deleveraging", "Settlement")  # ADR-0046: forced fills, plus every dir starting "Liquidated"
FORCED_PREFIX = "Liquidated"


def forced_fill(col: str = "dir") -> pl.Expr:
    """ADR-0046: auto-deleveraging, settlement and liquidation fills. They change the position (and are mirrored)
    but the leader did not choose them, so they are not signals for drift, the sweep anchor or the size study."""
    c = pl.col(col)
    return c.is_in(FORCED_DIRS) | c.str.starts_with(FORCED_PREFIX)


def classify_expr(rules: dict[str, Any], col: str = "symbol") -> pl.Expr:
    c = pl.col(col)
    spot = c.is_in(rules["classes"]["spot"].get("explicit", []))
    for pat in rules["classes"]["spot"].get("patterns", []):
        spot = spot | c.str.contains(pat)
    hip3 = pl.lit(False)
    for pat in rules["classes"]["hip3"].get("patterns", []):
        hip3 = hip3 | c.str.contains(pat)
    return pl.when(spot).then(pl.lit("spot")).when(hip3).then(pl.lit("hip3")).otherwise(pl.lit("core_perp"))


def annotate_fills(fills: pl.DataFrame, rules: dict[str, Any]) -> pl.DataFrame:
    """Add instrument_class, eligible, event_kind, signed size delta and is_perp."""
    eligible = rules["eligible_classes"]
    return fills.with_columns(classify_expr(rules).alias("instrument_class")).with_columns(
        eligible=pl.col("instrument_class").is_in(eligible),
        is_perp=pl.col("instrument_class").is_in(["core_perp", "hip3"]),
        event_kind=pl.when(pl.col("dir").is_in(rules["non_trade_dirs"])).then(pl.lit("non_trade"))
        .otherwise(pl.lit("trade")),
        delta=pl.when(pl.col("side") == "buy").then(pl.col("size")).otherwise(-pl.col("size")),
    )


def key_report(fills: pl.DataFrame) -> dict[str, int]:
    """Key diagnostics: tid is not unique; the composite key must be."""
    rep = fills.group_by("trader", "tid").len().filter(pl.col("len") > 1)
    rep_rows = fills.join(rep.select("trader", "tid"), on=["trader", "tid"])
    comp_dups = fills.group_by(FILL_KEY).len().filter(pl.col("len") > 1).height
    return {
        "tid_zero_rows": int((fills["tid"] == 0).sum()),
        "repeated_trader_tid_pairs": rep.height,
        "repeated_trader_tid_rows": rep_rows.height,
        "repeated_trader_tid_excess_rows": rep_rows.height - rep.height,
        "repeated_rows_not_dust": int((rep_rows["dir"] != "Spot Dust Conversion").sum()),
        "composite_key_duplicates": comp_dups,
    }


def instrument_master(fills: pl.DataFrame) -> pl.DataFrame:
    """Point-in-time instrument master: class and first/last print per symbol (from the given fills)."""
    return (fills.group_by("symbol", "instrument_class", "eligible")
            .agg(first_seen=pl.col("ts").min(), last_seen=pl.col("ts").max(), n_fills=pl.len(),
                 n_traders=pl.col("trader").n_unique(), notional=pl.col("notional").sum())
            .sort("symbol"))
