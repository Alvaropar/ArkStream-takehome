"""ADR-0039: worst-case drawdown inside each 4h bar (synthetic data)."""

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from arkstream.leader_worstcase import BAR_MS, ceil_bar_ms, worstcase

T0 = datetime(2025, 10, 1, tzinfo=UTC)
C = pl.col


def _ledger(rows):
    """rows: (ts, symbol, delta, price, pos_before, fee)"""
    return pl.DataFrame(
        [
            {"trader": "w", "ts": ts, "symbol": s, "delta": d, "price": p, "pos_before": pb, "pos_after": pb + d,
             "seq": i, "fee": fee, "fee_token": "USDC"}
            for i, (ts, s, d, p, pb, fee) in enumerate(rows)
        ]
    ).with_columns(C("ts").dt.cast_time_unit("ms"))


def _candles(coin, bars):
    """bars: list of (o, h, l, c) for consecutive 4h bars starting at T0."""
    return pl.DataFrame(
        [
            {"ts": T0 + timedelta(hours=4 * (i + 1)), "open_ts": T0 + timedelta(hours=4 * i), "coin": coin,
             "o": o, "h": h, "l": lo, "c": c, "n_trades": 1, "src_file": "x"}
            for i, (o, h, lo, c) in enumerate(bars)
        ]
    ).with_columns(C("ts", "open_ts").dt.cast_time_unit("ms"))


EMPTY_EXTREMES = pl.DataFrame(schema={"coin": pl.String, "bar_ms": pl.Int64, "b_low": pl.Float64,
                                      "b_high": pl.Float64, "b_minutes": pl.UInt32})
SNAP = pl.DataFrame({"trader": ["w"], "ts": [T0 - timedelta(hours=1)], "equity": [1000.0]}).with_columns(
    C("ts").dt.cast_time_unit("ms"))


def test_bar_boundaries():
    df = pl.DataFrame({"ms": [1, BAR_MS, BAR_MS + 1]}).select(b=ceil_bar_ms(C("ms")))
    assert df["b"].to_list() == [BAR_MS, BAR_MS, 2 * BAR_MS]  # an event at a boundary belongs to the closing bar


def test_wick_that_recovers_is_caught():
    """A 10-unit long bought at 100 (1x on 1,000 equity): the price falls to 30 and recovers to 100 inside one bar.
    Close-to-close shows nothing; the worst case shows -10 x 70 / 1000 = -70%."""
    led = _ledger([(T0 - timedelta(minutes=30), "A", 10.0, 100.0, 0.0, 0.0)])
    bars = [(100, 101, 30, 100), (100, 100, 100, 100)]
    per, _ = worstcase(led, _candles("A", bars), EMPTY_EXTREMES, SNAP, T0, T0 + timedelta(hours=8))
    r = per.row(0, named=True)
    assert r["close_max_dd_4h"] == pytest.approx(0.0)
    assert r["wc_max_dd"] == pytest.approx(-0.70)
    assert r["wc_worst_coin"] == "A" and r["wc_bars"] == 2


def test_short_uses_the_high_and_fills_inside_the_bar_count():
    """A short of 5 at 100, then the price spikes to 140; a fill inside the bar closes it at 120."""
    led = _ledger([
        (T0 - timedelta(minutes=10), "A", -5.0, 100.0, 0.0, 0.0),
        (T0 + timedelta(hours=2), "A", 5.0, 120.0, -5.0, 1.0),
    ])
    bars = [(100, 140, 95, 110)]
    per, _ = worstcase(led, _candles("A", bars), EMPTY_EXTREMES, SNAP, T0, T0 + timedelta(hours=4))
    r = per.row(0, named=True)
    # worst: position before the fill at the high: -5 x (140 - 100) = -200 -> -20%
    assert r["wc_max_dd"] == pytest.approx(-0.20)
    # close: realised -5 x (120 - 100) = -100 and a 1 USDC fee -> -10.1%
    assert r["close_max_dd_4h"] == pytest.approx(-0.101)


def test_missing_bar_is_unpriced_not_filled():
    led = _ledger([(T0 - timedelta(minutes=30), "A", 1.0, 100.0, 0.0, 0.0)])
    candles = _candles("A", [(100, 100, 90, 95), (95, 95, 50, 95)]).filter(C("ts") != T0 + timedelta(hours=8))
    per, _ = worstcase(led, candles, EMPTY_EXTREMES, SNAP, T0, T0 + timedelta(hours=8))
    r = per.row(0, named=True)
    assert r["wc_bars_unpriced"] == 1 and r["wc_bars"] == 1  # the 50 low is never seen, and never invented


def test_binance_check_substitutes_extremes_and_later_bars_do_not_leak():
    led = _ledger([(T0 - timedelta(minutes=30), "A", 1.0, 100.0, 0.0, 0.0)])
    bars = [(100, 101, 90, 100), (100, 100, 10, 100)]
    ex = pl.DataFrame({"coin": ["A"], "bar_ms": [int((T0 + timedelta(hours=4)).timestamp() * 1000)],
                       "b_low": [80.0], "b_high": [101.0], "b_minutes": [240]})
    ex = ex.with_columns(C("b_minutes").cast(pl.UInt32))
    per, check = worstcase(led, _candles("A", bars), ex, SNAP, T0, T0 + timedelta(hours=4))
    r = per.row(0, named=True)
    assert r["wc_max_dd"] == pytest.approx(-0.01)  # Hyperliquid low 90
    assert r["wc_max_dd_binance_check"] == pytest.approx(-0.02)  # Binance low 80
    assert check["bars"].to_list() == [1] and check["low_gap_bps_median"][0] == pytest.approx((90 / 80 - 1) * 1e4)
    # the second bar (low 10) closes after asof: it must not appear
    assert r["wc_bars"] == 1


def test_a_loss_beyond_equity_is_a_wipe_not_below_minus_100pct():
    led = _ledger([(T0 - timedelta(minutes=30), "A", 30.0, 100.0, 0.0, 0.0)])  # 3x on 1,000 equity
    per, _ = worstcase(led, _candles("A", [(100, 100, 40, 90)]), EMPTY_EXTREMES, SNAP, T0, T0 + timedelta(hours=4))
    assert per["wc_max_dd"][0] == pytest.approx(-1.0)  # -60 x 30 = -1,800 on 1,000: wiped, floored at -100%
