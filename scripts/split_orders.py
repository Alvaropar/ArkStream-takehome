"""Leader trades split into several taker orders: the Hyperliquid price path across child orders, from their fills.
Development data only (fills before 2025-12-03); forced fills (ADL, liquidation, settlement) excluded."""

import sys

sys.path.insert(0, "src")
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from arkstream.config import load_context
from arkstream.pipeline import load_inputs

pl.Config.set_tbl_cols(20)
pl.Config.set_tbl_width_chars(240)
pl.Config.set_tbl_rows(40)
C = pl.col
GAP_MS = 60_000
DIRECT = ["BTC", "ETH", "HYPE", "SOL"]
END = datetime(2025, 12, 3, tzinfo=UTC)
f = load_inputs(load_context()).fills.filter(
    C("eligible")
    & (C("event_kind") == "trade")
    & (C("ts") < END)
    & ~C("is_maker")
    & ~C("dir").str.starts_with("Liquidated")
    & (C("dir") != "Auto-Deleveraging")
    & (C("dir") != "Settlement")
)
# one row per taker order: time, side, best (first) / deepest / VWAP fill price, notional
o = (
    f.group_by("trader", "oid")
    .agg(
        coin=C("symbol").first(),
        side=C("side").first(),
        t=C("ts").min(),
        t_last=C("ts").max(),
        n_fills=pl.len(),
        notional=C("notional").sum(),
        qty=C("size").abs().sum(),
        best=pl.when(C("side").first() == "buy").then(C("price").min()).otherwise(C("price").max()),
        deepest=pl.when(C("side").first() == "buy").then(C("price").max()).otherwise(C("price").min()),
        src_row=C("src_row").min(),
    )
    .with_columns(
        vwap=C("notional") / C("qty"),
        sign=pl.when(C("side") == "buy").then(1).otherwise(-1),
        t_ms=C("t").dt.epoch("ms"),
    )
    .sort("trader", "coin", "t_ms", "oid")
)
print("taker orders:", o.height, "| orders whose fills span more than 1 ms:", o.filter(C("t_last") > C("t")).height)
# sequences: same trader and coin, same side, consecutive orders at most 60 s apart
o = o.with_columns(prev_t=C("t_ms").shift().over("trader", "coin"), prev_side=C("side").shift().over("trader", "coin"))
o = o.with_columns(
    new=(C("prev_t").is_null() | (C("t_ms") - C("prev_t") > GAP_MS) | (C("side") != C("prev_side"))).fill_null(True)
)
o = o.with_columns(seq=C("new").cast(pl.Int64).cum_sum().over("trader", "coin"))
o = o.with_columns(
    k=pl.int_range(pl.len()).over("trader", "coin", "seq"), n_children=pl.len().over("trader", "coin", "seq")
)
first = o.filter(C("k") == 0).select(
    "trader",
    "coin",
    "seq",
    t0="t_ms",
    best0="best",
    deep0="deepest",
    vwap0="vwap",
    notional0="notional",
    seq_notional=pl.lit(None),
)
seqn = o.group_by("trader", "coin", "seq").agg(seq_notional=C("notional").sum())
first = first.drop("seq_notional").join(seqn, on=["trader", "coin", "seq"])
o = o.join(first, on=["trader", "coin", "seq"])
o = o.with_columns(
    group=pl.when(C("coin").is_in(DIRECT)).then(pl.lit("BTC/ETH/HYPE/SOL")).otherwise(pl.lit("other coins")),
    dt_s=(C("t_ms") - C("t0")) / 1000,
)
# prevalence
prev = (
    o.filter(C("k") == 0)
    .group_by("group")
    .agg(
        sequences=pl.len(),
        split=(C("n_children") > 1).sum(),
        orders=C("n_children").sum(),
        orders_in_split=C("n_children").filter(C("n_children") > 1).sum(),
        notional_M=(C("seq_notional").sum() / 1e6).round(1),
        split_notional_share=(C("seq_notional").filter(C("n_children") > 1).sum() / C("seq_notional").sum()).round(3),
        median_children_if_split=C("n_children").filter(C("n_children") > 1).median(),
    )
    .sort("group")
)
print(prev)
# path: later children relative to the first child
later = o.filter(C("k") > 0).with_columns(
    move_vs_first=C("sign")
    * (C("best") / C("best0") - 1)
    * 1e4,  # child's best fill vs first child's best (first) fill
    move_vs_vwap0=C("sign") * (C("best") / C("vwap0") - 1) * 1e4,  # vs the first child's VWAP (base anchor)
    move_vs_deep0=C("sign") * (C("best") / C("deep0") - 1) * 1e4,  # vs the first child's deepest fill (stress anchor)
    sweep0=C("sign") * (C("deep0") / C("best0") - 1) * 1e4,
    bucket=C("notional0").cut([1e3, 1e4, 1e5], labels=["<1k", "1k-10k", "10k-100k", ">=100k"]),
    dt_bin=C("dt_s").cut([1, 2, 5, 10, 30], labels=["<=1s", "1-2s", "2-5s", "5-10s", "10-30s", "30-60s+"]),
)
path = (
    later.group_by("group", "dt_bin")
    .agg(
        children=pl.len(),
        sequences=pl.struct("trader", "coin", "seq").n_unique(),
        sweep0_mean=C("sweep0").mean().round(2),
        vs_first_mean=C("move_vs_first").mean().round(2),
        vs_first_median=C("move_vs_first").median().round(2),
        vs_vwap0_mean=C("move_vs_vwap0").mean().round(2),
        vs_deep0_mean=C("move_vs_deep0").mean().round(2),
        vs_deep0_median=C("move_vs_deep0").median().round(2),
        vs_first_p90=C("move_vs_first").quantile(0.9).round(1),
    )
    .sort("group", "dt_bin")
)
print(path)
# second child only, by first-child size: the price the next leader order got vs where the first one ended
second = (
    later.filter(C("k") == 1)
    .group_by("group", "bucket")
    .agg(
        n=pl.len(),
        dt_median_s=C("dt_s").median().round(2),
        sweep0_mean=C("sweep0").mean().round(2),
        vs_first_mean=C("move_vs_first").mean().round(2),
        vs_vwap0_mean=C("move_vs_vwap0").mean().round(2),
        vs_deep0_mean=C("move_vs_deep0").mean().round(2),
        vs_deep0_median=C("move_vs_deep0").median().round(2),
    )
    .sort("group", "bucket")
)
print(second)
out = Path("research/split_orders")
out.mkdir(parents=True, exist_ok=True)
prev.write_csv(out / "prevalence.csv")
path.write_csv(out / "path_by_elapsed.csv")
second.write_csv(out / "second_child_by_size.csv")
later.select(
    "trader",
    "coin",
    "seq",
    "k",
    "oid",
    "src_row",
    "side",
    "t",
    "dt_s",
    "notional0",
    "best0",
    "vwap0",
    "deep0",
    "best",
    "move_vs_first",
    "move_vs_vwap0",
    "move_vs_deep0",
).sort("trader", "coin", "seq", "k").write_parquet(out / "children.parquet")
