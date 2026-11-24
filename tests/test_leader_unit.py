"""Phase 2 leader evidence on synthetic data: return conventions, gaps, book marks, round-trip boundaries,
open trades at the test date, stress shocks from pre-origin moves only, and unpriced exposure."""

from __future__ import annotations

from datetime import timedelta

import polars as pl
import pytest
from conftest import make_fills, ts

from arkstream import leader_returns as lr
from arkstream import leader_risk as lk
from arkstream import leader_trips as lt
from arkstream.config import load_context
from arkstream.pipeline import positions_asof

RULES = load_context().raw["leader"]
TR = "0xaaa"


def snaps(rows: list[tuple[str, float, float]]) -> pl.DataFrame:
    df = pl.DataFrame({"trader": [TR] * len(rows), "ts": [ts(r[0]) for r in rows],
                       "equity": [r[1] for r in rows], "net_deposit": [r[2] for r in rows],
                       "src_row": list(range(2, 2 + len(rows)))})
    return df.with_columns(pl.col("ts").dt.cast_time_unit("ms"), date=pl.col("ts").dt.date())


def grid(coin: str, start: str, prices: list[float | None]) -> pl.DataFrame:
    t0 = ts(start)
    return pl.DataFrame({"coin": [coin] * len(prices), "t": [t0 + timedelta(hours=i) for i in range(len(prices))],
                         "price": prices}, schema_overrides={"price": pl.Float64}).with_columns(
        pl.col("t").dt.cast_time_unit("ms"),
        price_source=pl.when(pl.col("price").is_null()).then(pl.lit("unpriced")).otherwise(pl.lit("reference")))


# ---------------------------------------------------------------------------------------------- account
def test_both_conventions_with_a_deposit():
    s = snaps([("2025-10-01 22:00", 10_000, 0), ("2025-10-02 22:00", 12_000, 1_000)])
    a = lr.account_returns(s, ts("2025-10-03 00:00"), RULES)
    r = a.row(0, named=True)
    assert r["account_pnl"] == pytest.approx(1_000)
    assert r["r_start"] == pytest.approx(1_000 / 11_000)   # flow at the start: in the denominator
    assert r["r_end"] == pytest.approx(1_000 / 10_000)     # flow at the end
    # the two differ by ~0.9% < 1% placeholder: usable
    assert r["usable"] and r["exclude_reason"] == ""


def test_conventions_disagree_and_low_equity_excluded():
    s = snaps([("2025-10-01 22:00", 10_000, 0), ("2025-10-02 22:00", 20_000, 5_000),
               ("2025-10-03 22:00", 400, 5_000), ("2025-10-04 22:00", 450, 5_000)])
    a = lr.account_returns(s, ts("2025-10-05 00:00"), RULES)
    assert a["exclude_reason"].to_list() == ["conventions_disagree", "", "opening_equity_below_min"]


def test_gap_gives_one_return_not_interpolated():
    s = snaps([("2025-10-01 22:00", 10_000, 0), ("2025-10-05 22:00", 11_000, 0)])
    a = lr.account_returns(s, ts("2025-10-06 00:00"), RULES)
    assert a.height == 1
    r = a.row(0, named=True)
    assert r["period_days"] == 4 and r["multi_day"] and r["r_start"] == pytest.approx(0.1)
    cov = lr.account_coverage(a, s, ts("2025-10-06 00:00"))
    assert cov["usable_days"][0] == 4 and cov["calendar_days"][0] == 5


def test_account_returns_point_in_time():
    s = snaps([("2025-10-01 22:00", 10_000, 0), ("2025-10-02 22:00", 11_000, 0), ("2025-10-03 22:00", 9_000, 0)])
    a = lr.account_returns(s, ts("2025-10-03 00:00"), RULES)
    assert a.height == 1 and a["ts"].max() <= ts("2025-10-03 00:00")


# ---------------------------------------------------------------------------------------------- book
def _ledger(rows: list[dict], asof):
    return positions_asof(make_fills(rows), asof)


LONG = [
    {"ts": "2025-10-01 00:30", "trader": TR, "symbol": "BTC", "side": "buy", "size": 1.0, "start_position": 0.0,
     "price": 100.0, "fee": 0.1},
    {"ts": "2025-10-01 02:30", "trader": TR, "symbol": "BTC", "side": "sell", "size": 1.0, "start_position": 1.0,
     "price": 125.0, "dir": "Close Long", "fee": 0.1},
]


def test_hourly_book_is_exact_mark_to_market():
    asof = ts("2025-10-01 04:00")
    ledger, _, _ = _ledger(LONG, asof)
    px = grid("BTC", "2025-10-01 00:00", [95, 110, 120, 130, 130])
    s = snaps([("2025-09-30 22:00", 1_000, 0)])
    h, marks = lr.book_hourly(ledger, px, s, asof)
    got = dict(zip(h["hour_end"].dt.hour().to_list(), h["book_pnl"].to_list(), strict=True))
    assert got[1] == pytest.approx(10 - 0.1)      # bought at 100, marked 110, fee
    assert got[2] == pytest.approx(10)            # held 110 -> 120
    assert got[3] == pytest.approx(10 - 5 - 0.1)  # held 120 -> 130, sold at 125 (-1 x (130 - 125)), fee
    assert sum(got.values()) == pytest.approx(25 - 0.2)  # = realized PnL net of fees
    assert set(h["funding"]) == {"omitted"}
    assert marks["m"].dt.hour().to_list() == [1, 2]


def test_unpriced_hour_is_null_and_exposure_reported():
    asof = ts("2025-10-01 04:00")
    ledger, _, _ = _ledger(LONG, asof)
    px = grid("BTC", "2025-10-01 00:00", [95, 110, None, 130, 130])
    h, _ = lr.book_hourly(ledger, px, snaps([("2025-09-30 22:00", 1_000, 0)]), asof)
    by = {r["hour_end"].hour: r for r in h.iter_rows(named=True)}
    assert by[1]["priced"] and by[1]["book_pnl"] is not None
    assert not by[2]["priced"] and by[2]["book_pnl"] is None     # P(02:00) missing
    assert not by[3]["priced"] and by[3]["unpriced_exposure_w"] > 0  # mark 02:00 unpriced
    m = lk.risk_metrics(h, lr.book_daily(h, snaps([("2025-09-30 22:00", 1_000, 0)]), asof),
                        lr.account_returns(snaps([("2025-09-30 22:00", 1_000, 0)]), asof, RULES),
                        lr._terms(ledger, px, asof)[1], lk.shocks(px, asof, 1), make_fills(LONG), asof, RULES)
    assert m["unpriced_exposure_share"][0] == pytest.approx(0.5)


def test_funding_hook_adds_a_term_and_label():
    asof = ts("2025-10-01 04:00")
    ledger, _, _ = _ledger(LONG, asof)
    px = grid("BTC", "2025-10-01 00:00", [95, 110, 120, 130, 130])
    f = pl.DataFrame({"ts": [ts("2025-10-01 02:00")], "coin": ["BTC"], "funding_rate": [0.001]}).with_columns(
        pl.col("ts").dt.cast_time_unit("ms"))
    h0, _ = lr.book_hourly(ledger, px, snaps([("2025-09-30 22:00", 1_000, 0)]), asof)
    pay = f.select(trader=pl.lit(TR), coin="coin", ts_hour="ts", src_row=pl.lit(2,pl.Int64),
                   payment=-120*pl.col("funding_rate"))
    h1, _ = lr.book_hourly(ledger, px, snaps([("2025-09-30 22:00", 1_000, 0)]), asof, funding=pay)
    d = h1["book_pnl"] - h0["book_pnl"]
    assert d.to_list()[1] == pytest.approx(-1 * 120 * 0.001)  # long pays funding at 02:00 on the 01:00 position
    assert set(h1["funding"]) == {"included"}


# ---------------------------------------------------------------------------------------------- round trips
def _trips(rows, asof, px):
    ledger, trips, open_pos = _ledger(rows, asof)
    ledger = ledger.filter("eligible")
    _, marks = lr.book_hourly(ledger, px, snaps([("2025-09-30 22:00", 1_000, 0)]), asof)
    om = open_pos.select("trader", "symbol").join(
        px.filter(pl.col("t") == lr.floor_hour(asof)).rename({"coin": "symbol"}), on="symbol", how="left").select(
        "trader", "symbol", mark_price="price", mark_source="price_source")
    return lt.round_trips(trips, ledger, marks, om, asof, RULES)


def test_flip_splits_the_crossing_fill():
    rows = [
        {"ts": "2025-10-01 00:10", "trader": TR, "symbol": "ETH", "side": "buy", "size": 1.0, "start_position": 0.0,
         "price": 100.0, "fee": 0.0},
        {"ts": "2025-10-01 01:10", "trader": TR, "symbol": "ETH", "side": "sell", "size": 3.0, "start_position": 1.0,
         "price": 110.0, "fee": 0.3},
        {"ts": "2025-10-01 02:10", "trader": TR, "symbol": "ETH", "side": "buy", "size": 2.0, "start_position": -2.0,
         "price": 105.0, "fee": 0.0},
    ]
    rt = _trips(rows, ts("2025-10-01 04:00"), grid("ETH", "2025-10-01 00:00", [100, 105, 108, 104, 104]))
    assert rt["status"].to_list() == ["closed", "closed"]
    t0, t1 = rt.row(0, named=True), rt.row(1, named=True)
    assert t0["net_pnl"] == pytest.approx(10 - 0.1)          # 1/3 of the fee to the closing part
    assert t1["net_pnl"] == pytest.approx(2 * 5 - 0.2)       # short 2 at 110, covered at 105
    assert t1["peak_notional"] == pytest.approx(220) and t1["ret"] == pytest.approx(9.8 / 220)
    assert t0["exit_src_row"] == t1["entry_src_row"]


def test_open_trade_at_test_date_valued_and_close_after_asof_not_seen():
    rows = [*LONG]
    asof = ts("2025-10-01 02:00")  # before the close at 02:30
    rt = _trips(rows, asof, grid("BTC", "2025-10-01 00:00", [95, 110, 90]))
    r = rt.row(0, named=True)
    assert r["status"] == "open_at_asof" and r["close_ts"] is None
    assert r["mark_price"] == 90 and r["net_pnl"] == pytest.approx(-10 - 0.1)
    assert r["mae"] == pytest.approx(min(0, 10 - 0.1) / 100)  # mark at 01:00 only: a gain, so MAE 0
    assert r["usable"] and r["hold_s"] == pytest.approx(5400)
    s = lt.trip_summary(rt, RULES)
    assert s["rt_closed"][0] == 0 and s["rt_open_valued"][0] == 1


def test_left_censored_trip_excluded_and_open_unpriced_flagged():
    rows = [{"ts": "2025-10-01 00:30", "trader": TR, "symbol": "BTC", "side": "sell", "size": 1.0,
             "start_position": 2.0, "price": 100.0, "dir": "Close Long"}]
    rt = _trips(rows, ts("2025-10-01 02:00"), grid("BTC", "2025-10-01 00:00", [100, 101, None]))
    r = rt.row(0, named=True)
    assert r["left_censored"] and not r["usable"] and r["exclude_reason"] == "left_censored_entry_unknown"
    rows2 = [{**LONG[0]}]
    rt2 = _trips(rows2, ts("2025-10-01 02:00"), grid("BTC", "2025-10-01 00:00", [100, 101, None]))
    assert rt2["exclude_reason"][0] == "open_unpriced_at_asof"


def test_top_share_removes_at_least_one_trade():
    rt = pl.DataFrame({"trader": [TR] * 3, "symbol": ["A", "B", "C"], "trip_no": [0, 0, 0],
                       "status": ["closed"] * 3, "usable": [True] * 3, "left_censored": [False] * 3,
                       "exclude_reason": [""] * 3, "ret": [0.5, -0.1, 0.01], "ret_per_day": [0.5, -0.1, 0.01],
                       "net_pnl": [100.0, -20.0, 2.0], "mae": [0.0] * 3, "best_gain": [0.0] * 3})
    s = lt.trip_summary(rt, RULES).row(0, named=True)
    assert s["mean_ret_ex_top"] == pytest.approx((-0.1 + 0.01) / 2)
    assert s["top_pnl_share"] == pytest.approx(1 - (-18) / 82)
    assert s["win_rate"] == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------------------------- risk
def test_stress_shock_uses_only_moves_before_the_origin():
    px = grid("BTC", "2025-10-08 00:00", [100, 98, 99, 100, 60, 61])  # crash at 04:00
    early = lk.shocks(px, ts("2025-10-08 03:00"), 1)
    late = lk.shocks(px, ts("2025-10-08 05:00"), 1)
    assert early["shock_down"][0] == pytest.approx(0.02)
    assert late["shock_down"][0] == pytest.approx(0.40)
    assert early["shock_down_end"][0] <= ts("2025-10-08 03:00")


def test_stress_exposure_by_direction_and_unshocked():
    sh = pl.DataFrame({"coin": ["BTC"], "shock_down": [0.2], "shock_up": [0.5]})
    m = pl.DataFrame({"trader": [TR] * 3, "symbol": ["BTC", "BTC", "PURR"], "hour_end": [ts("2025-10-01 01:00"),
                      ts("2025-10-01 02:00"), ts("2025-10-01 02:00")], "pos": [1.0, -1.0, 10.0],
                      "p_m": [100.0, 100.0, 1.0]})
    h = pl.DataFrame({"trader": [TR] * 2, "hour_end": [ts("2025-10-01 01:00"), ts("2025-10-01 02:00")],
                      "equity_base": [100.0, 100.0], "leverage": [1.0, 2.1]})
    st = lk.stress_exposure(m, h, sh, 0.025).row(0, named=True)
    assert st["stress_peak"] == pytest.approx(0.5) and st["stress_typical"] == pytest.approx(0.35)
    assert st["unshocked_exposure_share"] == pytest.approx(10 / 210)
    # ADR-0067: residual margin after the shock, 1 - loss/equity - MMR x leverage, minimum over hours
    assert st["stress_headroom_min"] == pytest.approx(min(1 - 0.2 - 0.025 * 1.0, 1 - 0.5 - 0.025 * 2.1))


def test_missing_metric_is_unmeasured_not_pass():
    ev = pl.DataFrame({"rt_closed": [25, 5], "intraday_max_dd": [-0.1, None], "worst_day": [-0.05, -0.3],
                       "worst_3d": [-0.1, None], "max_dd_book": [-0.2, None], "stress_headroom_min": [0.6, None],
                       "leverage_p95": [2.0, None], "liq_distance_min": [0.3, None], "liquidations": [0, 1],
                       "top_profit_share": [0.2, None], "unpriced_exposure_share": [0.0, None],
                       "median_hold_s":[3600,1],"orders_per_day":[2,99],
                       "maker_share":[0.2,0.8],
                       "xc_n":[20,3],"within_1pct_lower":[0.95,None],
                       "days_since_fill":[2,30],"xc_flag": ["ok", "too_few_intervals"],
                       "wc_max_dd": [-0.3, None], "snapshot_days": [120, 40], "usable_days": [100, 30]})
    g = lk.apply_gates(ev, RULES)
    assert g["all_gates_pass"].to_list() == [True, False]
    assert g["gate_intraday_dd"].to_list() == ["pass", "unmeasured"]
    assert g["gate_worstcase_dd"].to_list() == ["pass", "unmeasured"]
    assert g["gate_book_account"].to_list() == ["pass", "unmeasured"]
    assert g["gate_worst_day"][1] == "fail" and g["gate_liquidations"][1] == "fail"
    assert g["gate_history"].to_list() == ["pass", "fail"]


def test_style_gates_are_diagnostics_and_categories_roll_up():
    """ADR-0067: a fast, maker-heavy, high-order-rate leader passes when every binding gate passes; categories."""
    ev = pl.DataFrame({"rt_closed": [25], "intraday_max_dd": [-0.1], "worst_day": [-0.05], "worst_3d": [-0.1],
                       "max_dd_book": [-0.2], "stress_headroom_min": [0.4], "leverage_p95": [2.0],
                       "liq_distance_min": [0.3], "liquidations": [0], "top_profit_share": [0.2],
                       "unpriced_exposure_share": [0.0], "median_hold_s": [5], "orders_per_day": [500],
                       "maker_share": [0.95], "xc_n": [20], "within_1pct_lower": [0.95], "days_since_fill": [1],
                       "xc_flag": ["ok"], "wc_max_dd": [-0.3], "snapshot_days": [120], "usable_days": [100]})
    g = lk.apply_gates(ev, RULES).row(0, named=True)
    assert (g["gate_hold"], g["gate_order_rate"], g["gate_maker"]) == ("fail", "fail", "fail")
    assert g["cat_style_diagnostic"] == "fail" and g["all_gates_pass"] is True
    assert g["style_flags"] == "gate_hold:fail;gate_order_rate:fail;gate_maker:fail"
    assert all(g[c] == "pass" for c in ("cat_data_integrity", "cat_evidence", "cat_risk_historical",
                                        "cat_risk_position", "cat_risk_stress", "cat_risk"))
    stressed = lk.apply_gates(ev.with_columns(stress_headroom_min=pl.lit(-0.01)), RULES).row(0, named=True)
    assert stressed["gate_stress_peak"] == "fail" and stressed["cat_risk_stress"] == "fail"
    assert stressed["cat_risk"] == "fail" and stressed["all_gates_pass"] is False
