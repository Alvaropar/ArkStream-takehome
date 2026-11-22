# PROTOTYPE (2026-11-19, main session), kept as a reference for the Phase 2 rework brief. Not part of the
# package and not tested. It rebuilds account value changes from fills at the exact snapshot times, with
# Hyperliquid funding, for core-perp-only addresses, and writes per-interval errors. Results: see ADR-0009.
# Key point: fills sharing a timestamp must be put in chain order (positions.order_fills) before taking the
# position at a time; ordering by src_row gave misses of up to 29x equity.

"""Account rebuild from fills, marked at the exact snapshot times, with funding; compared with each snapshot."""
import sys; sys.path.insert(0, "src")
from datetime import datetime, UTC
from pathlib import Path
import polars as pl
from arkstream.config import load_context
from arkstream.pipeline import load_inputs
from arkstream.prices import price_asof, scan_reference
from arkstream.positions import order_fills
pl.Config.set_tbl_cols(20); pl.Config.set_tbl_width_chars(230); pl.Config.set_tbl_rows(30)
ctx = load_context(); i = load_inputs(ctx); T = ctx.cutoff
t, f = i.traders, i.fills
nc = f.group_by("trader").agg(bad=((pl.col("instrument_class") == "spot") | (~pl.col("eligible") & pl.col("is_perp")) | (pl.col("event_kind") == "non_trade")).any())
core = set(nc.filter(~pl.col("bad"))["trader"]) & set(t["trader"])
f = order_fills(f.filter(pl.col("trader").is_in(list(core)) & pl.col("eligible") & (pl.col("event_kind") == "trade")))
f = f.with_columns(end_pos=pl.col("start_position") + pl.col("delta"), usdc_fee=pl.when(pl.col("fee_token") == "USDC").then("fee"),
                   ts=pl.col("ts").dt.cast_time_unit("ms"))
fills_raw = f
# one row per (trader, coin, ts): position before the first and after the last fill of that instant, in chain order
f = (f.sort("trader", "symbol", "ts", "seq").group_by("trader", "symbol", "ts", maintain_order=True)
     .agg(start_position=pl.col("start_position").first(), end_pos=pl.col("end_pos").last(),
          cashf=(-pl.col("delta") * pl.col("price")).sum(), feef=pl.col("usdc_fee").sum(), nonusdc=pl.col("usdc_fee").is_null().sum())
     .sort("ts"))
s = t.filter(pl.col("trader").is_in(list(core))).select("trader", "src_row", ts=pl.col("ts").dt.cast_time_unit("ms"), E="equity", ND="net_deposit").sort("trader", "ts")
coins = f.select("trader", "symbol").unique()
# ---- position of each (trader, coin) at every snapshot time
q = s.select("trader", "src_row", "ts").join(coins, on="trader").sort("ts")
back = q.join_asof(f.select("trader", "symbol", fts="ts", end_pos="end_pos"), left_on="ts", right_on="fts", by=["trader", "symbol"], strategy="backward")
fwd = q.join_asof(f.select("trader", "symbol", fts2="ts", start_position="start_position"), left_on="ts", right_on="fts2", by=["trader", "symbol"], strategy="forward")
pos = back.join(fwd.select("trader", "symbol", "src_row", "start_position"), on=["trader", "symbol", "src_row"]).with_columns(
    pos=pl.coalesce("end_pos", "start_position")).select("trader", "symbol", "src_row", "ts", "pos")
ref = scan_reference(ctx.path("reference_prices_dir"))
need = pos.filter(pl.col("pos").abs() > 0)
pr = price_asof(need.select(coin="symbol", t="ts"), ref, i.fills, T, 60, 60)
need = need.with_columns(P=pr["price"])
pos = pos.join(need.select("trader", "symbol", "src_row", "P"), on=["trader", "symbol", "src_row"], how="left")
val = pos.group_by("trader", "src_row", "ts").agg(V=(pl.col("pos") * pl.col("P")).filter(pl.col("pos").abs() > 0).sum(),
          unpriced=((pl.col("pos").abs() > 0) & pl.col("P").is_null()).sum())
# ---- cash flows of fills, assigned to the snapshot interval that ends at the next snapshot
fl = f.sort("ts").join_asof(s.select("trader", nxt_row="src_row", nts="ts"), left_on="ts", right_on="nts", by="trader", strategy="forward")
cash = fl.group_by("trader", "nxt_row").agg(cash=pl.col("cashf").sum(), fees=pl.col("feef").sum(), nonusdc_fees=pl.col("nonusdc").sum())
# ---- funding: hourly, position at the hour x reference price at the hour x rate
fu = pl.read_parquet("research/hyperliquid/funding.parquet").select(symbol="coin", h=pl.col("ts_hour").dt.cast_time_unit("ms"), rate="funding_rate")
hrs = coins.join(fu, on="symbol").filter(pl.col("h") <= T).sort("h")
hrs = hrs.join_asof(f.select("trader", "symbol", fts="ts", end_pos="end_pos"), left_on="h", right_on="fts", by=["trader", "symbol"], strategy="backward")
hrs = hrs.join_asof(f.select("trader", "symbol", fts2="ts", start_position="start_position"), left_on="h", right_on="fts2", by=["trader", "symbol"], strategy="forward")
hrs = hrs.with_columns(pos=pl.coalesce("end_pos", "start_position")).filter(pl.col("pos").abs() > 0)
refh = ref.filter(pl.col("ts").dt.minute() == 0).select(symbol="coin", h=pl.col("ts").dt.cast_time_unit("ms"), Ph="price").collect()
hrs = hrs.join(refh, on=["symbol", "h"], how="left").with_columns(pay=-pl.col("pos") * pl.col("Ph") * pl.col("rate"))
hrs = hrs.sort("h").join_asof(s.select("trader", nxt_row="src_row", nts="ts"), left_on="h", right_on="nts", by="trader", strategy="forward")
fund = hrs.group_by("trader", "nxt_row").agg(funding=pl.col("pay").sum(), fund_unpriced=pl.col("Ph").is_null().sum())
# ---- intervals
x = (s.join(val, on=["trader", "src_row", "ts"], how="left").sort("trader", "ts")
     .with_columns(V=pl.col("V").fill_null(0), unpriced=pl.col("unpriced").fill_null(0))
     .with_columns(prev_E=pl.col("E").shift().over("trader"), prev_ND=pl.col("ND").shift().over("trader"), prev_V=pl.col("V").shift().over("trader"),
                   prev_unp=pl.col("unpriced").shift().over("trader"), prev_ts=pl.col("ts").shift().over("trader"))
     .filter(pl.col("prev_E").is_not_null())
     .join(cash.rename({"nxt_row": "src_row"}), on=["trader", "src_row"], how="left").join(fund.rename({"nxt_row": "src_row"}), on=["trader", "src_row"], how="left")
     .with_columns([pl.col(c).fill_null(0) for c in ["cash", "fees", "nonusdc_fees", "funding", "fund_unpriced"]])
     .with_columns(acct=pl.col("E") - pl.col("prev_E") - (pl.col("ND") - pl.col("prev_ND")),
                   trade=pl.col("V") - pl.col("prev_V") + pl.col("cash") - pl.col("fees"))
     .with_columns(pred=pl.col("trade") + pl.col("funding"))
     .filter((pl.col("unpriced") == 0) & (pl.col("prev_unp") == 0) & (pl.col("fund_unpriced") == 0) & (pl.col("nonusdc_fees") == 0) & (pl.col("prev_E") > 500)))
def summ(x, name, col):
    e = (pl.col("acct") - pl.col(col)).abs() / pl.col("prev_E")
    return x.select(pl.lit(name).alias("model"), pl.len().alias("intervals"), pl.col("trader").n_unique().alias("addresses"),
        (e < 0.0001).mean().round(3).alias("within_0.01pct"), (e < 0.001).mean().round(3).alias("within_0.1pct"),
        (e < 0.01).mean().round(3).alias("within_1pct"), e.median().round(6).alias("median_err"),
        pl.corr("acct", col).round(4).alias("corr"), (pl.col("acct").sum() / 1e6).round(3).alias("acct_M"), (pl.col(col).sum() / 1e6).round(3).alias("pred_M"))
print(pl.concat([summ(x, "exact times, no funding", "trade"), summ(x, "exact times + funding", "pred")]))
ok = x.with_columns(err=(pl.col("acct") - pl.col("pred")).abs() / pl.col("prev_E"))
pa = ok.group_by("trader").agg(n=pl.len(), share=(pl.col("err") < 0.001).mean())
print("addresses:", pa.height, "| >=95% of intervals within 0.1%:", (pa["share"] >= 0.95).sum(), "| >=80%:", (pa["share"] >= 0.8).sum(), "| <50%:", (pa["share"] < 0.5).sum())
ok.select("trader", "src_row", "prev_ts", "ts", "prev_E", "acct", "trade", "funding", "pred", "err").write_parquet(
    "rebuild_intervals.parquet")
