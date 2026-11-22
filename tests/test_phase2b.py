"""Contract regressions for the funded address-as-asset outputs."""

from datetime import timedelta

import numpy as np
import polars as pl
import pytest
from conftest import make_fills, ts
from test_leader_unit import LONG, RULES, grid, snaps

from arkstream import leader_assets as assets
from arkstream import leader_book, leader_marks, leader_returns, quality
from arkstream.book_state import book_state
from arkstream.config import load_context
from arkstream.pipeline import positions_asof
from arkstream.reconcile import snapshot_summary


def test_trailing_gap_and_unusable_days_share_a_denominator():
    t = ts("2025-10-10")
    stats = pl.DataFrame({"first_date": [ts("2025-10-01").date()], "days_present": [8], "usable_days": [7]})
    r = quality.coverage_to_origin(stats, t).row(0, named=True)
    assert r["calendar_days"] == 10 and r["days_present_share"] == 0.8 and r["unusable_day_share"] == pytest.approx(0.3)


def test_frozen_only_when_the_book_moves_and_chain_end_is_used():
    t = ts("2025-10-04")
    fills = make_fills(
        [
            {**LONG[0], "ts": "2025-10-01 01:00", "size": 2.0, "start_position": 1.0},
            {**LONG[0], "ts": "2025-10-01 01:00", "size": 1.0, "start_position": 0.0},
        ]
    )
    ledger, _, _ = positions_asof(fills, t)
    obs = snaps([(f"2025-10-0{i} 22:00", 1000.0, 0.0) for i in (1, 2, 3)])
    ref = obs.select("ts", coin=pl.lit("BTC"), price=pl.Series([100.0, 103.0, 103.0])).lazy()
    flags, _ = quality.snapshot_flags(obs, t, load_context().raw)
    flags = quality.frozen_flags(flags, ledger, fills, t, ref, ["BTC"])
    assert flags["frozen"].to_list() == [False, True, False]
    states, marks = book_state(obs, ledger, t, ref, ["BTC"], fills)
    assert marks["pos"].to_list() == [3.0, 3.0, 3.0]
    assert states["value"].diff()[1] == 9.0


def test_accrue_to_actual_position_before_hour_only_after_publication():
    t = ts("2025-10-01 02:00")
    fills = make_fills(
        [
            LONG[0],
            {**LONG[0], "ts": "2025-10-01 01:35", "size": 2.0, "start_position": 1.0},
            {**LONG[1], "ts": t, "size": 3.0, "start_position": 3.0},
        ]
    )
    ledger, _, _ = positions_asof(fills, t)
    rate = pl.DataFrame(
        {
            "coin": ["BTC"],
            "ts_hour": [t],
            "known_at": [t + timedelta(milliseconds=50)],
            "funding_rate": [0.001],
            "src_file": ["rate"],
        }
    ).with_columns(pl.col("ts_hour", "known_at").cast(leader_marks.MS))
    px = grid("BTC", "2025-10-01", [100.0, 110.0, 120.0]).rename({"t": "ts_hour"})

    def last(asof):
        return leader_marks.payments(ledger, rate, px, asof).row(-1, named=True)

    assert last(t)["missing_reason"] == "rate_unknown" and last(t)["payment"] is None
    later = last(t + timedelta(milliseconds=50))
    assert later["pos"] == 3 and later["payment"] == pytest.approx(-0.36)


def test_daily_marks_require_a_traded_bar_at_the_boundary():
    a = ts("2025-10-01")
    b = a + timedelta(days=1)
    h = grid("BTC", "2025-10-01", [100.0] * 49).with_columns(ref_ts=pl.col("t"), ref_file=pl.lit("binance"))
    bars = pl.DataFrame(
        {
            "coin": ["BTC"] * 3,
            "ts": [a, b, b + timedelta(days=1)],
            "n_trades": [1, 0, 1],
            "price": [101.0, 101.0, 99.0],
            "src_file": ["c"] * 3,
        }
    )
    outcomes = pl.DataFrame({"coin": ["BTC"], "outcome": ["pass"]})
    _, d, _ = leader_marks.price_panels(h, bars, outcomes, b, load_context().raw["funding"]["price_check"])
    assert d["price"].to_list() == [101.0, None] and d["validation"].to_list() == ["flagged", "unvalidated"]
    assert d["t"].max() == b


def test_withdrawal_deposit_and_gap_chain_both_conventions():
    s = snaps(
        [("2025-10-01 22:00", 10000.0, 0.0), ("2025-10-02 22:00", 12000.0, 1000.0), ("2025-10-05 22:00", 11220.0, 0.0)]
    )
    t = ts("2025-10-06")
    x = assets.twr_series(leader_returns.account_returns(s, t, RULES), t)
    assert x["period_days"].to_list() == [1, 3]
    assert x["index_start"][-1] == pytest.approx((1 + 1000 / 11000) * (1 + 220 / 11000))
    assert x["index_end"][-1] == pytest.approx(1.1 * (1 + 220 / 12000))


def test_joint_betas_and_daily_alpha():
    rng = np.random.default_rng(67)
    btc, eth = rng.normal(0, 0.01, (2, 90))
    fit = assets.exposure(0.001 + 1.2 * btc - 0.4 * eth, btc, eth)
    assert [fit[k] for k in ("alpha", "beta_btc", "beta_eth", "r_squared")] == pytest.approx([0.001, 1.2, -0.4, 1])
    assert assets.exposure(btc, btc, btc)["alpha"] is None


def test_daily_funded_book_uses_the_hl_boundary_and_reports_a_missing_close():
    start = ts("2025-10-01")
    end = start + timedelta(days=3)
    fills = make_fills([LONG[0]])
    ledger, _, _ = positions_asof(fills, end)
    obs = snaps([("2025-10-01", 1000.0, 0.0)])
    h = grid("BTC", "2025-10-01", [500.0] * 73).with_columns(ref_ts=pl.col("t"), ref_file=pl.lit("validator"))
    bars = pl.DataFrame(
        {
            "coin": ["BTC"] * 3,
            "ts": [start, start + timedelta(days=1), end],
            "n_trades": [1] * 3,
            "price": [100.0, 110.0, 80.0],
            "src_file": ["hl"] * 3,
        }
    )
    _, day, proxy = leader_marks.price_panels(
        h,
        bars,
        pl.DataFrame({"coin": ["BTC"], "outcome": ["no_binance"]}),
        end,
        load_context().raw["funding"]["price_check"],
    )
    assert proxy.filter(pl.col("ts_hour") == start + timedelta(hours=4))["price"][0] == 100
    assert proxy.filter(pl.col("ts_hour") == start + timedelta(hours=5))["price"][0] is None
    # Independently specify every booked payment in this valuation fixture.
    pay = h.select(trader=pl.lit(LONG[0]["trader"]), coin="coin", ts_hour="t", payment=pl.lit(-0.1))
    d, _ = leader_book.daily_book(obs, ledger, day, pay, end, pl.DataFrame().lazy(), fills, start)
    assert d["book_pnl"][0] == pytest.approx(10 - 0.1 - 2.4)
    assert d["book_pnl"].to_list()[1:] == [None, None]


def test_gap_drawdown_keeps_the_book_trough_between_flat_snapshots():
    start, end = ts("2025-10-01 22:00"), ts("2025-10-04 22:00")
    obs = snaps([(start.isoformat(), 1000.0, 0.0), (end.isoformat(), 1000.0, 0.0)])
    series = assets.twr_series(leader_returns.account_returns(obs, end, RULES), end).with_columns(
        opening_index=pl.lit(1.0), scope=pl.lit("checkable")
    )

    def state(points, values):
        return points.with_columns(
            value=pl.Series(values),
            funding_total=pl.lit(0.0),
            unknown_rates=pl.lit(0),
            bad_fees=pl.lit(0),
            unpriced=pl.lit(0),
            flagged=pl.lit(False),
            unvalidated=pl.lit(False),
        )

    boundary = pl.DataFrame(
        {"trader": [LONG[0]["trader"]] * 3, "ts": [ts("2025-10-02"), ts("2025-10-03"), ts("2025-10-04")]}
    )
    path = assets.gap_path(
        series,
        state(obs, [0.0, 0.0]),
        state(boundary.with_columns(pl.col("ts").cast(leader_marks.MS)), [-200.0, -100.0, 0.0]),
        end,
    )
    assert path["wealth"].to_list() == pytest.approx([0.8, 0.9, 1.0])
    assert path["flow_timing"].unique().to_list() == ["unknown_inside_gap"]


def test_identity_breach_selects_whole_book_history_only_when_known():
    start = ts("2025-10-01")
    end = start + timedelta(days=4)
    dates = [start + timedelta(days=i) for i in range(5)]
    clean = snaps([(d.isoformat(), 1000. + 10*i, 0.) for i, d in enumerate(dates)]).with_columns(
        trader=pl.lit("clean"), pnl=pl.col("equity"))
    breach = clean.with_columns(trader=pl.lit("breach"), src_row=pl.col("src_row") + 10,
                                pnl=pl.col("pnl") + pl.when(pl.col("ts") == end).then(1.).otherwise(0.))
    obs = pl.concat([clean, breach])
    book = pl.DataFrame({"trader": ["breach"]*4, "day_start": dates[:-1], "ts": dates[1:],
                         "equity_base": [1000., 1000., 1000., 400.], "book_pnl": [100., None, -50., 20.],
                         "funding_paid": [0.]*4, "missing_terms": [0, 1, 0, 0], "book_ret": [.1, None, -.05, .05],
                         "equity_src_row": [12, 13, 14, 15], "price_source": ["hyperliquid_4h"]*4,
                         "validation": ["validated"]*4}).with_columns(
                             pl.col("ts", "day_start").cast(leader_marks.MS), eq_ts=pl.col("day_start"),
                             day=pl.col("day_start").dt.date())

    def primary(asof):
        universe = snapshot_summary(obs, asof, .01, 1.).with_columns(return_source=assets.primary_source())
        snapshot = assets.twr_series(leader_returns.account_returns(obs, asof, RULES), asof)
        return assets.primary_series(snapshot, book, universe, pl.Series([], dtype=pl.Int64), asof, 500.)

    early = primary(dates[-2])
    assert early["return_source"].unique().to_list() == [assets.SNAPSHOT]
    s = primary(end)
    assert s.filter(pl.col("trader") == "clean")["index_start"][-1] == pytest.approx(1.04)
    b = s.filter(pl.col("trader") == "breach")
    assert b["return_source"].unique().to_list() == [assets.BOOK]
    assert b["r_start"].to_list() == [.1, None, -.05, None]
    assert b["index_start"].drop_nulls().to_list() == pytest.approx([1.1, 1.045])
    assert b["r_end"].null_count() == b.height
    assert b["exclude_reason"].to_list() == ["", "incomplete_core_book", "", "opening_equity_below_min"]
