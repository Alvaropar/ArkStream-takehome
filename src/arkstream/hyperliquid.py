"""`python -m arkstream funding`: Hyperliquid funding table, price check and userFunding check. No network.

Steps (each reads only manifest-verified files from inputs.hyperliquid_dir):

* coins        - data/reference/hyperliquid/coins.csv: core perps traded in eligible fills (the fetch list).
* table        - funding.parquet (rates only), funding_coverage.csv, funding_gaps.csv.
* price-check  - ADR-0012 rule: price_check.csv, price_check_bars.parquet, candles_dropped.csv.
* price-check-origins - ADR-0110: the same rule as of each origin: price_check_by_origin.csv and
                 price_check_changes.csv (coins that differ from the CUTOFF list, orders and notional moved).
* user-check   - actual payments of a few leaders vs rebuilt position x rate x Binance proxy price:
                 user_funding_check.parquet (every payment) and user_funding_summary.csv. A check only.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from arkstream import funding as fu
from arkstream import hlprices as hp
from arkstream.config import Context
from arkstream.pipeline import load_inputs, positions_asof
from arkstream.prices import price_asof, scan_reference


def _no_binance(ctx: Context) -> set[str]:
    return hp.no_binance_coins(ctx.path("binance_map"))


def _leaders(ledger: pl.DataFrame, n: int) -> list[str]:
    s = ledger.group_by("trader").agg(fills=pl.len()).sort(["fills", "trader"], descending=[True, False])
    return s.head(n)["trader"].to_list()


def run(ctx: Context, steps: list[str], out_dir: str | None) -> int:
    hl, cut = ctx.path("hyperliquid_dir"), ctx.cutoff
    cfg = ctx.section("funding")
    out = Path(out_dir) if out_dir else ctx.root / "research" / "hyperliquid"
    out.mkdir(parents=True, exist_ok=True)
    inp = load_inputs(ctx)
    coins = fu.eligible_coins(inp.fills, cut)
    if "coins" in steps:
        coins.write_csv(hl / "coins.csv")
        print(f"wrote {hl / 'coins.csv'}: {coins.height} coins")
    need_table = any(s in steps for s in ("table", "user-check"))
    table = fu.load_funding(hl, cut) if need_table else None
    if "table" in steps:
        assert table is not None
        table.write_parquet(out / "funding.parquet", statistics=False)
        cov = fu.coverage(table, coins, cut)
        cov.write_csv(out / "funding_coverage.csv")
        fu.gaps(table, coins, cut).write_csv(out / "funding_gaps.csv")
        print(cov.group_by("flag").agg(coins=pl.len(), notional=pl.col("notional").sum()).sort("flag"))
    rp = ctx.raw["reference_prices"]
    ref = scan_reference(ctx.path("reference_prices_dir"))
    if "price-check" in steps:
        pc = cfg["price_check"]
        candles, dropped = hp.load_candles(hl, cut)
        dropped.write_csv(out / "candles_dropped.csv")
        bars = hp.compare_bars(candles, ref, inp.fills, cut, pc["max_ref_age_s"])
        bars.write_parquet(out / "price_check_bars.parquet", statistics=False)
        res = hp.price_check(bars, coins["coin"].to_list(), _no_binance(ctx), pc["min_bars"],
                             pc["max_median_abs_bps"], pc["max_p95_abs_bps"])
        res = res.join(coins.select("coin", "notional"), on="coin", how="left").sort("coin")
        res.write_csv(out / "price_check.csv")
        print(res.group_by("outcome").agg(coins=pl.len(), notional=pl.col("notional").sum()).sort("outcome"))
    if "price-check-origins" in steps:
        # ADR-0110: the same rule on the bars closing by each origin (reads research/hyperliquid/ inputs).
        from datetime import UTC, date, datetime

        pit = hp.PointInTimeCheck.load(ctx)
        origins = [datetime.combine(date.fromisoformat(str(o)), datetime.min.time(), UTC)
                   for o in ctx.raw["drift"]["origins"]]
        holdout = datetime.combine(date.fromisoformat(str(ctx.raw["splits"]["holdout"]["start"])),
                                   datetime.min.time(), UTC)
        recorded = pl.read_csv(ctx.root / hp.COINS_FILE).select("coin", "outcome")
        if not pit.checks(cut).equals(recorded.sort("coin")):
            raise ValueError("the bars no longer reproduce the CUTOFF price check (ADR-0013)")
        pit.by_origin(origins).write_csv(out / "price_check_by_origin.csv")
        changes = hp.origin_changes(pit, origins, cut, inp.fills, holdout)
        changes.write_csv(out / "price_check_changes.csv")
        with pl.Config(tbl_rows=60, tbl_cols=-1, tbl_width_chars=200):
            print(pit.by_origin(origins).group_by("origin", "outcome").len().sort("origin", "outcome"))
            print(changes.select("origin", "coin", "cutoff_outcome", "outcome", "next_window_orders",
                                 "next_window_notional_share"))
    if "user-check" in steps:
        assert table is not None
        ledger, _, _ = positions_asof(inp.fills.filter(pl.col("eligible")), cut)
        uf = fu.load_user_funding(hl, cut)
        q = (uf.select("coin", d=pl.col("ts_hour").dt.cast_time_unit("ms"), k=pl.int_ranges(0, 24)).explode("k")
             .select("coin", t=(pl.col("d") + pl.duration(hours=pl.col("k"))).dt.cast_time_unit("ms"))
             .filter(pl.col("t") <= cut).unique().sort("coin", "t"))
        px = price_asof(q, ref, inp.fills.clear(), cut, rp["max_age_s"], 0)
        prices = px.filter(pl.col("price_source") == "reference").select("coin", ts_hour="t", price="price")
        chk = fu.user_funding_check(uf, ledger, table, prices, cfg["user_funding_rel_tol"])
        chk.write_parquet(out / "user_funding_check.parquet", statistics=False)
        summ = chk.group_by("trader").agg(
            records=pl.len(), coins=pl.col("coin").n_unique(), sign_ok=pl.col("sign_ok").mean(),
            samples_ok=pl.col("samples_ok").mean(), rate_ok=pl.col("rate_ok").mean(),
            amount_known=pl.col("amount_known").mean(),
            amount_ok_when_known=pl.col("amount_ok").filter(pl.col("amount_known")).mean(),
            amount_ok_when_samples_ok=pl.col("amount_ok").filter(pl.col("amount_known") & pl.col("samples_ok")).mean(),
            median_abs_rel_err=pl.col("amount_rel_err").abs().median(),
            usdc_actual=pl.col("usdc").sum(),
            usdc_calc_when_known=pl.col("calc_usdc").filter(pl.col("amount_known")).sum(),
            usdc_actual_when_known=pl.col("usdc").filter(pl.col("amount_known")).sum()).sort("trader")
        summ.write_csv(out / "user_funding_summary.csv")
        with pl.Config(tbl_cols=-1, tbl_width_chars=200):
            print(summ)
    print(f"wrote {out}")
    return 0


def leaders_for_check(ctx: Context) -> list[str]:
    """The leaders whose userFunding is fetched for the check (top N by eligible fills; deterministic)."""
    inp = load_inputs(ctx)
    ledger, _, _ = positions_asof(inp.fills.filter(pl.col("eligible")), ctx.cutoff)
    return _leaders(ledger, int(ctx.section("funding")["user_funding_leaders"]))
