import polars as pl
import pytest
from conftest import make_fills, ts

from arkstream.positions import chain_order, continuity, order_fills, rebuild

T = "2025-10-15 15:39:40.221"


def _ledger(rows):
    led, trips = rebuild(continuity(order_fills(make_fills(rows))))
    return led, trips


def test_chain_order_needs_entry_hint():
    starts, deltas = [0.0, 2.1, 2.5372], [2.1, 0.4372, -2.5372]
    # Shuffled source order: sell first in the file.
    order = chain_order([starts[2], starts[0], starts[1]], [deltas[2], deltas[0], deltas[1]], entry=0.0)
    assert order == [1, 2, 0]
    assert chain_order([1.0, 5.0], [1.0, 1.0], entry=1.0) is None


def test_mixed_millisecond_regression_shape():
    # Same shape as 0xa0d0... ETH at 2025-10-15 15:39:40.221: flat, buy 2.1 and 0.4372, sell 2.5372, flat.
    rows = [
        dict(ts="2025-10-15 15:39:00.000", trader="0xa", symbol="ETH", side="buy", size=1.0, start_position=0.0),
        dict(ts="2025-10-15 15:39:10.000", trader="0xa", symbol="ETH", side="sell", size=1.0, start_position=1.0,
             dir="Close Long"),
        dict(ts=T, trader="0xa", symbol="ETH", side="sell", size=2.5372, start_position=2.5372, dir="Close Long"),
        dict(ts=T, trader="0xa", symbol="ETH", side="buy", size=2.1, start_position=0.0),
        dict(ts=T, trader="0xa", symbol="ETH", side="buy", size=0.4372, start_position=2.1),
        dict(ts="2025-10-15 15:39:54.870", trader="0xa", symbol="ETH", side="buy", size=0.005, start_position=0.0),
    ]
    led, trips = _ledger(rows)
    assert led["continuity_break"].sum() == 0
    g = led.filter(pl.col("ts") == ts(T)).sort("seq")
    assert g["size"].to_list() == [2.1, 0.4372, 2.5372]
    assert g["group_kind"].unique().to_list() == ["mixed"]
    assert trips.height == 3 and trips["close_ts"].null_count() == 1


def test_one_sided_group_ordered_by_signed_start():
    rows = [dict(ts=T, trader="0xa", symbol="BTC", side="sell", size=1.0, start_position=s, src_row=10 + i)
            for i, s in enumerate([1.0, 3.0, 2.0])]
    led, _ = _ledger(rows)
    assert led.sort("seq")["start_position"].to_list() == [3.0, 2.0, 1.0]
    assert led["continuity_break"].sum() == 0


def test_break_detected():
    rows = [dict(ts="2025-10-01 00:00:00", trader="0xa", symbol="BTC", side="buy", size=1.0, start_position=0.0),
            dict(ts="2025-10-01 00:00:01", trader="0xa", symbol="BTC", side="buy", size=1.0, start_position=5.0)]
    led, _ = _ledger(rows)
    assert led["continuity_break"].to_list() == [False, True]


def test_round_trips_flip_censoring_and_realized():
    rows = [
        # left-censored: first observed position is already long 2
        dict(ts="2025-10-01 00:00:00", trader="0xa", symbol="BTC", side="sell", size=2.0, start_position=2.0,
             price=110.0, dir="Close Long", closed_pnl=20.0),
        dict(ts="2025-10-01 01:00:00", trader="0xa", symbol="BTC", side="buy", size=1.0, start_position=0.0,
             price=100.0),
        # flip: long 1 -> short 1 at 120: realized (120-100)*1 = 20
        dict(ts="2025-10-01 02:00:00", trader="0xa", symbol="BTC", side="sell", size=2.0, start_position=1.0,
             price=120.0, dir="Long > Short", closed_pnl=20.0),
        dict(ts="2025-10-01 03:00:00", trader="0xa", symbol="BTC", side="buy", size=1.0, start_position=-1.0,
             price=90.0, dir="Close Short", closed_pnl=30.0),
    ]
    led, trips = _ledger(rows)
    assert trips["trip_no"].to_list() == [0, 1, 2]
    assert trips["left_censored"].to_list() == [True, False, False]
    assert trips["side"].to_list() == ["long", "long", "short"]
    assert trips["rebuilt_known"].to_list() == [False, True, True]
    assert trips["rebuilt_realized"].to_list()[1:] == pytest.approx([20.0, 30.0])
    assert led["rebuilt_realized"].to_list()[0] is None  # unknown entry: never imputed
    assert trips["close_ts"].null_count() == 0


@pytest.mark.data
def test_zero_breaks_and_real_regression_case(full_build):
    led = full_build.tables["ledger"]
    assert led.height == 864_623
    assert int(led["continuity_break"].sum()) == 0
    g = led.filter(pl.col("trader").str.starts_with("0xa0d0") & (pl.col("symbol") == "ETH")
                   & (pl.col("ts") == ts(T))).sort("seq")
    assert g["side"].to_list() == ["buy", "buy", "sell"]
    assert g["size"].to_list() == [2.1, 0.4372, 2.5372]
    assert g["pos_after"].to_list() == pytest.approx([2.1, 2.5372, 0.0])
