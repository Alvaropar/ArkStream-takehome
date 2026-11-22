"""Worst-case drawdown inside each 4h bar (ADR-0045).

The existing drawdowns value positions at one price per hour (Binance 1m close at the hour) or per day (Hyperliquid
4h close at midnight), so a coin that falls 70% and recovers inside an hour is never seen. Here every position is
also valued at the most adverse price its coin reached inside each 4h bar.

Per address, coin and 4h bar (open o, high h, low l, close c, known at the bar close):

* the position at the bar open comes from the fills (the last fill's position after, or the first later fill's
  position before for a position opened before the data); fills inside the bar add their cash and fees;
* close PnL  = pos_end x c - pos_open x o - sum(fill delta x fill price) - fees;
* worst PnL  = the minimum of pos_open x (x - o) and pos_end x x - pos_open x o - sum(delta x price) - fees over
  x in {l, h}: the position before and after the bar's fills, each at the bar's adverse extreme. Positions opened and
  closed inside one bar are not caught at this resolution.

Per address, bars are chained on the close PnL (index I_k = I_{k-1} x (1 + close_k / E_k), with E_k the latest
cross-margin snapshot equity known at the bar open). The worst-case trough in bar k is I_{k-1} x (1 + worst_k / E_k)
and the worst-case drawdown is min_k trough_k / max(1, I_0..I_{k-1}) - 1.

Primary source: Hyperliquid 4h OHLC for every coin. Check: the same computation with the Binance 1m lows and highs
over the same four hours (times the price factor, only minutes with volume inside the coin's validity window) for the
163 coins that passed the price check; Hyperliquid extremes are kept for the other coins. A held coin with no
Hyperliquid bar makes that address's bar unpriced: it is counted and skipped, never filled in. Funding is not in
this measure (an hourly accrual of a few bps cannot hide a wick).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import polars as pl

C = pl.col
BAR_MS = 4 * 3600 * 1000
NS_PER_MS = 1_000_000


def ceil_bar_ms(ms: pl.Expr) -> pl.Expr:
    """The close (ms) of the 4h UTC bar that contains an event at `ms`; an event at a boundary belongs to the bar
    that closes there."""
    return ((ms + BAR_MS - 1) // BAR_MS) * BAR_MS


def binance_extremes(lake_dir: Path, mapping: pl.DataFrame, passing: list[str], cutoff: datetime) -> pl.DataFrame:
    """Per (Hyperliquid coin, 4h bar close): lowest low and highest high of the Binance 1m bars that close inside the
    bar, in Hyperliquid units. Only minutes with volume > 0 inside the coin's validity window."""
    m = mapping.filter(C("hl").is_in(passing) & C("valid_from").is_not_null()).select(
        symbol="binance", coin="hl", factor="price_factor_hl_per_binance", valid_from="valid_from", valid_to="valid_to"
    )
    k = (
        pl.scan_parquet(str(lake_dir / "venue=binance/dataset=binance.um.klines/interval=1m/symbol=*/date=*/*.parquet"),
                        hive_partitioning=False)
        .select("symbol", "ts_event", "high", "low", "volume")
        .filter((C("volume") > 0) & (C("ts_event") <= int(cutoff.timestamp() * 1000) * NS_PER_MS))
        .join(m.lazy(), on="symbol")
        .with_columns(close_ms=C("ts_event") // NS_PER_MS)
        .with_columns(day=pl.from_epoch("close_ms", time_unit="ms").dt.date())
        .filter((C("day") >= C("valid_from")) & (C("day") <= C("valid_to")))
        .with_columns(bar_ms=ceil_bar_ms(C("close_ms")))
        .group_by("coin", "bar_ms")
        .agg(b_low=(C("low") * C("factor")).min(), b_high=(C("high") * C("factor")).max(), b_minutes=pl.len())
    )
    return k.collect(engine="streaming").sort("coin", "bar_ms")


def _bars(ledger: pl.DataFrame, candles: pl.DataFrame, extremes: pl.DataFrame, start: datetime,
          asof: datetime) -> pl.DataFrame:
    """One row per (trader, coin, 4h bar) where the coin is held or traded, with close and worst PnL."""
    f = ledger.filter(C("ts") <= asof).sort("trader", "symbol", "ts", "seq").with_columns(
        ms=C("ts").dt.epoch("ms"), usdc_fee=pl.when(C("fee_token") == "USDC").then(C("fee")).otherwise(None)
    )
    # Fills sharing a millisecond: position before the first and after the last, in chain order.
    inst = f.group_by("trader", "symbol", "ms", maintain_order=True).agg(
        pos_before=C("pos_before").first(), pos_after=C("pos_after").last()
    )
    first_bar = int(start.timestamp() * 1000) // BAR_MS * BAR_MS + BAR_MS
    last_bar = int(asof.timestamp() * 1000) // BAR_MS * BAR_MS
    grid = pl.DataFrame({"bar_ms": pl.int_range(first_bar, last_bar + 1, BAR_MS, eager=True)})
    tc = f.select("trader", "symbol").unique()
    g = tc.join(grid, how="cross").with_columns(open_ms=C("bar_ms") - BAR_MS).sort("open_ms")
    back = inst.select("trader", "symbol", ms_b="ms", pos_b="pos_after").sort("ms_b")
    fwd = inst.select("trader", "symbol", ms_f="ms", pos_f="pos_before").sort("ms_f")
    g = g.join_asof(back, left_on="open_ms", right_on="ms_b", by=["trader", "symbol"], strategy="backward",
                    check_sortedness=False)
    g = g.join_asof(fwd, left_on="open_ms", right_on="ms_f", by=["trader", "symbol"], strategy="forward",
                    check_sortedness=False)
    g = g.with_columns(pos_open=pl.coalesce("pos_b", "pos_f").fill_null(0.0)).drop("pos_b", "pos_f", "ms_b", "ms_f")
    inside = (
        f.with_columns(bar_ms=ceil_bar_ms(C("ms")))
        .group_by("trader", "symbol", "bar_ms", maintain_order=True)
        .agg(cash=(C("delta") * C("price")).sum(), fees=C("usdc_fee").sum(), bad_fee=C("usdc_fee").is_null().sum(),
             pos_end=C("pos_after").last(), n_fills=pl.len())
    )
    g = g.join(inside, on=["trader", "symbol", "bar_ms"], how="left").with_columns(
        cash=C("cash").fill_null(0.0), fees=C("fees").fill_null(0.0), n_fills=C("n_fills").fill_null(0),
        bad_fee=C("bad_fee").fill_null(0), pos_end=pl.coalesce("pos_end", "pos_open"),
    )
    g = g.filter((C("pos_open").abs() > 1e-12) | (C("n_fills") > 0))
    cd = candles.select("coin", "o", "h", "l", "c", "src_file", bar_ms=C("ts").dt.epoch("ms"))
    g = g.join(cd.rename({"coin": "symbol"}), on=["symbol", "bar_ms"], how="left").join(
        extremes.rename({"coin": "symbol"}), on=["symbol", "bar_ms"], how="left"
    )

    def worst(lo: str, hi: str) -> pl.Expr:
        rest = C("pos_open") * C("o") + C("cash") + C("fees")
        return pl.min_horizontal(
            C("pos_open") * (C(lo) - C("o")), C("pos_open") * (C(hi) - C("o")),
            C("pos_end") * C(lo) - rest, C("pos_end") * C(hi) - rest,
        )

    # Binance check: Binance extremes where they exist (passing coins, minutes with volume), Hyperliquid elsewhere.
    return g.with_columns(bl=pl.coalesce("b_low", "l"), bh=pl.coalesce("b_high", "h")).with_columns(
        close_pnl=C("pos_end") * C("c") - C("pos_open") * C("o") - C("cash") - C("fees"),
        worst_hl=worst("l", "h"),
        worst_check=worst("bl", "bh"),
        priced=C("o").is_not_null(),
        binance_bar=C("b_low").is_not_null(),
    )


def _dd(close_r: pl.Expr, worst_r: pl.Expr) -> tuple[pl.Expr, pl.Expr]:
    """(worst-case drawdown, close-to-close drawdown). A loss larger than equity wipes the account: the index and
    the trough are floored at zero, so a drawdown is never below -100%."""
    idx = (1 + close_r).clip(lower_bound=0.0).cum_prod()
    prev = idx.shift(1).fill_null(1.0)
    peak = prev.cum_max().clip(lower_bound=1.0)
    trough = (prev * (1 + worst_r)).clip(lower_bound=0.0)
    return (trough / peak - 1).min(), (idx / idx.cum_max().clip(lower_bound=1.0) - 1).min()


def worstcase(ledger: pl.DataFrame, candles: pl.DataFrame, extremes: pl.DataFrame, traders: pl.DataFrame,
              start: datetime, asof: datetime) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(per-address worst-case drawdown table, per-coin Hyperliquid vs Binance extreme comparison)."""
    # Sorted, order-preserving aggregation: float sums then come out byte-identical run to run (ADR-0008).
    rows = _bars(ledger, candles, extremes, start, asof).sort("trader", "bar_ms", "symbol")
    per_bar = rows.group_by("trader", "bar_ms", maintain_order=True).agg(
        close_pnl=C("close_pnl").sum(), worst_hl=C("worst_hl").sum(), worst_check=C("worst_check").sum(),
        unpriced=(~C("priced")).sum(), coins=pl.len(),
        worst_coin=C("symbol").sort_by("worst_hl").first(),
    )
    eq = traders.filter(C("equity") > 0).select("trader", eq_ms=C("ts").dt.epoch("ms"), equity="equity").sort("eq_ms")
    per_bar = (
        per_bar.with_columns(open_ms=C("bar_ms") - BAR_MS).sort("open_ms")
        .join_asof(eq, left_on="open_ms", right_on="eq_ms", by="trader", strategy="backward", check_sortedness=False)
        .sort("trader", "bar_ms")
    )
    usable = per_bar.filter((C("unpriced") == 0) & C("equity").is_not_null())
    usable = usable.with_columns(r_close=C("close_pnl") / C("equity"), r_worst=C("worst_hl") / C("equity"),
                                 r_check=C("worst_check") / C("equity"))
    wc_hl, close_dd = _dd(C("r_close"), C("r_worst"))
    wc_check, _ = _dd(C("r_close"), C("r_check"))
    per = usable.sort("trader", "bar_ms").group_by("trader", maintain_order=True).agg(
        wc_max_dd=wc_hl, wc_max_dd_binance_check=wc_check, close_max_dd_4h=close_dd,
        wc_worst_bar=C("r_worst").min(),
        wc_worst_bar_ts=pl.from_epoch(C("bar_ms").sort_by("r_worst").first(), time_unit="ms")
        .dt.replace_time_zone("UTC"),
        wc_worst_coin=C("worst_coin").sort_by("r_worst").first(),
        wc_bars=pl.len(),
    )
    skipped = per_bar.group_by("trader", maintain_order=True).agg(
        wc_bars_unpriced=(C("unpriced") > 0).sum(), wc_bars_no_equity=C("equity").is_null().sum()
    )
    per = skipped.join(per, on="trader", how="left").with_columns(
        wc_check_gap=C("wc_max_dd_binance_check") - C("wc_max_dd"),
        wc_source=pl.lit("hyperliquid_4h_ohlc"), wc_check_source=pl.lit("binance_1m_high_low"),
    ).sort("trader")
    cmp = rows.filter(C("priced") & C("binance_bar")).select("symbol", "bar_ms", "l", "h", "b_low", "b_high").unique(
        maintain_order=True)
    check = cmp.sort("symbol", "bar_ms").group_by("symbol", maintain_order=True).agg(
        bars=pl.len(),
        low_gap_bps_median=((C("l") / C("b_low") - 1) * 1e4).median(),
        low_gap_bps_p05=((C("l") / C("b_low") - 1) * 1e4).quantile(0.05),
        high_gap_bps_median=((C("h") / C("b_high") - 1) * 1e4).median(),
        high_gap_bps_p95=((C("h") / C("b_high") - 1) * 1e4).quantile(0.95),
        hl_deeper_low_share=(C("l") < C("b_low")).mean(),
    ).rename({"symbol": "coin"}).sort("coin")
    return per, check
