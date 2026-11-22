"""ADR-0160 (point-in-time Hyperliquid split-order floor for base alt drift below 300 s) and ADR-0161 (measured
receive delay)."""

from datetime import date, datetime, timedelta

import numpy as np
import polars as pl
import pytest
from conftest import make_fills, need
from test_sensitivity_limits import END, START, T, _events

from arkstream.config import load_yaml
from arkstream.replay_market import (
    SPLIT_PREFIX,
    midnight,
    split_order_cells,
    split_order_observations,
)
from arkstream.replay_orders import Parameters, batches

C = pl.col
DIRECT = ("BTC", "ETH", "HYPE", "SOL")
COLS = ["origin", "period", "coin", "band", "horizon_ms", "mean_bps", "measured"]
EDGES = (250_000, 1_000_000, 5_000_000)
V = date(2025, 10, 22)


def _fill(t: datetime, oid: int, px: float, coin="DOGE", side="buy", trader="0xa"):
    return {"ts": t, "trader": trader, "symbol": coin, "side": side, "size": 1.0 if side == "buy" else -1.0,
            "start_position": 0.0, "price": px, "oid": oid, "dir": "Open Long" if side == "buy" else "Open Short"}


# ------------------------------------------------------------------------------------ evidence
def test_split_observations_move_vs_first_vwap_and_sequences():
    t0 = midnight(date(2025, 10, 20)) + timedelta(hours=1)
    rows = [
        _fill(t0, 1, 100.0), _fill(t0, 1, 102.0),             # first order: VWAP 101
        _fill(t0 + timedelta(milliseconds=1500), 2, 101.5),   # 1.5 s later, best 101.5 -> +49.5 bps
        _fill(t0 + timedelta(seconds=90), 3, 110.0),          # 88.5 s gap > 60 s: a new sequence
        _fill(t0 + timedelta(seconds=91), 4, 90.0, side="sell"),  # other side: a new sequence
    ]
    obs = split_order_observations(make_fills(rows), 60_000, midnight(date(2025, 9, 8)), frozenset())
    assert obs.height == 1
    r = obs.row(0, named=True)
    assert r["elapsed_ms"] == 1500 and r["oid"] == 2
    assert r["move_bps"] == pytest.approx((101.5 / 101 - 1) * 1e4)
    sell = [_fill(t0, 1, 100.0, side="sell"), _fill(t0 + timedelta(seconds=2), 2, 99.0, side="sell")]
    s = split_order_observations(make_fills(sell), 60_000, midnight(date(2025, 9, 8)), frozenset())
    assert s["move_bps"][0] == pytest.approx(100.0)  # lower price on a sell = worse for the copier


def test_split_observations_exclude_makers_forced_and_stress_days():
    t0 = midnight(date(2025, 10, 10)) + timedelta(hours=1)  # a stress day
    rows = [_fill(t0, 1, 100.0), _fill(t0 + timedelta(seconds=2), 2, 101.0)]
    assert split_order_observations(make_fills(rows), 60_000, midnight(date(2025, 9, 8)),
                                    frozenset({date(2025, 10, 10)})).is_empty()
    t1 = midnight(date(2025, 10, 20))
    maker = [_fill(t1, 1, 100.0), {**_fill(t1 + timedelta(seconds=2), 2, 101.0), "is_maker": True}]
    assert split_order_observations(make_fills(maker), 60_000, midnight(date(2025, 9, 8)), frozenset()).is_empty()
    forced = [_fill(t1, 1, 100.0), {**_fill(t1 + timedelta(seconds=2), 2, 101.0), "dir": "Liquidated Isolated Short"}]
    assert split_order_observations(make_fills(forced), 60_000, midnight(date(2025, 9, 8)), frozenset()).is_empty()


def _obs(n, elapsed_ms, move, t_ms, coin="DOGE", volume=2e6):
    return pl.DataFrame({"coin": [coin] * n, "elapsed_ms": [elapsed_ms] * n, "move_bps": [move] * n,
                         "t_ms": [t_ms] * n, "bar_volume_usdc": [volume] * n})


def test_split_cells_point_in_time_seeded_leak():
    before = int(midnight(V).timestamp() * 1000) - 1
    after = int(midnight(V).timestamp() * 1000)  # at the vintage's midnight: not before it
    clean = _obs(30, 1500, 1.0, before)
    leak = pl.concat([clean, _obs(30, 1500, 1000.0, after)])
    a = split_order_cells(clean, {V: {"DOGE"}}, [1000, 2000], EDGES, 30)
    b = split_order_cells(leak, {V: {"DOGE"}}, [1000, 2000], EDGES, 30)
    assert a.equals(b)  # a split order at or after the vintage never enters its estimate
    assert a.select("coin", "horizon_ms", "measured", "mean_bps").rows() == [("hlsplit:all", 2000, 30, 1.0)]


def test_split_cells_bins_minimum_buckets_and_coins():
    t = int(midnight(V).timestamp() * 1000) - 10
    o = pl.concat([_obs(30, 1000, 2.0, t), _obs(29, 1001, 5.0, t), _obs(40, 0, 9.0, t),
                   _obs(30, 1500, 7.0, t, coin="BTC"), _obs(30, 1500, 7.0, t, coin="FAILED")])
    c = split_order_cells(o, {V: {"DOGE", "BTC"}}, [1000, 2000], EDGES, 30)
    # 1,000 ms is in (0, 1]; 1,001 ms in (1, 2] with 29 < 30 -> no cell; 0 ms in no bin; BTC (direct) and a coin
    # failing the price check never enter
    assert c.select("coin", "horizon_ms", "measured", "mean_bps").rows() == [("hlsplit:all", 1000, 30, 2.0)]
    # every bucket with >= 30 -> per-bucket cells; one short -> pooled
    vols = (1e5, 5e5, 2e6, 1e7)
    full = pl.concat([_obs(30, 1500, float(i), t, volume=v) for i, v in enumerate(vols)])
    c = split_order_cells(full, {V: {"DOGE"}}, [2000], EDGES, 30)
    assert sorted(c["coin"]) == sorted(SPLIT_PREFIX + b for b in ("<250k", "250k-1M", "1M-5M", ">=5M"))
    short = pl.concat([full.head(119)])
    c = split_order_cells(short, {V: {"DOGE"}}, [2000], EDGES, 30)
    assert c["coin"].to_list() == ["hlsplit:all"] and c["measured"].to_list() == [119]


# ------------------------------------------------------------------------------------ rule
def _params(split, own=3.68, proxy=-0.5, bins=(1000, 2000, 5000, 10000)):
    cells = [(V, "development", c, "all", h, proxy, 100) for c in DIRECT for h in (1200, 5000, 60_000)]
    cells.append((V, "development", "ALT", "all", 300_000, own, 50))
    cells += [(V, "development", SPLIT_PREFIX + coin, "all", h, m, 40) for coin, h, m in split]
    cells.append((V, "stress", "ALT", "all", 300_000, 9.0, 50))
    cells += [(V, "stress", c, "all", h, 1.0, 100) for c in DIRECT for h in (1200, 5000)]
    return Parameters(pl.DataFrame(cells, orient="row", schema=COLS), short_bins=bins)


def test_floor_uses_the_split_estimate_for_the_delays_bin():
    p = _params([("all", 2000, 0.25)])
    value, method, used, reason = p.lookup(V, "development", "ALT", "all", 1200, conservative=True, bucket="1M-5M")
    assert value == 0.25 and method == "base_max_proxy_hlsplit_zero" and reason == ""
    assert '"hlsplit:all","all",2000' in used and '"ALT"' not in used  # the own 300 s cell is not read
    # never favourable: a negative estimate and a negative proxy floor at zero
    assert _params([("all", 2000, -4.0)]).lookup(V, "development", "ALT", "all", 1200, conservative=True)[0] == 0.0
    # the proxy still wins when it is larger
    q = _params([("all", 2000, 0.25)], proxy=2.0)
    assert q.lookup(V, "development", "ALT", "all", 1200, conservative=True)[0] == 2.0


def test_floor_falls_back_to_adr0114_without_an_estimate():
    p = _params([("all", 5000, 1.0)])
    v, method, _, _ = p.lookup(V, "development", "ALT", "all", 1200, conservative=True)  # (1, 2] has no cell
    assert v == 3.68 and method == "base_max_proxy_coin_300s_zero"
    v, method, _, _ = p.lookup(V, "development", "ALT", "all", 60_000, conservative=True)  # 60 s: no bin
    assert v == 3.68 and method == "base_max_proxy_coin_300s_zero"
    assert p.lookup(V, "development", "ALT", "all", 5000, conservative=True)[:2] == (1.0, "base_max_proxy_hlsplit_zero")
    # no bins configured (rule own_300s): ADR-0114 everywhere
    old = _params([("all", 2000, 0.25)], bins=())
    assert old.lookup(V, "development", "ALT", "all", 1200, conservative=True)[:2] == (
        3.68, "base_max_proxy_coin_300s_zero")
    # the fallback still needs the own cell
    none = _params([], own=float("nan"))
    assert none.lookup(V, "development", "ALT", "all", 1200, conservative=True)[3] == "no_drift_cell"


def test_floor_bucket_cells_and_bins_are_right_closed():
    p = _params([(b, 2000, float(i)) for i, b in enumerate(("<250k", "250k-1M", "1M-5M", ">=5M"))])
    assert p.lookup(V, "development", "ALT", "all", 1200, conservative=True, bucket="1M-5M")[0] == 2.0
    # an order with no completed bar has no bucket cell -> the ADR-0114 floor
    assert p.lookup(V, "development", "ALT", "all", 1200, conservative=True, bucket="unknown")[0] == 3.68
    assert [p.short_bin(d) for d in (1, 1000, 1001, 1200, 2000, 5000, 10_000, 10_001, 60_000)] == [
        1000, 1000, 2000, 2000, 2000, 5000, 10_000, None, None]


def test_optimistic_stress_and_long_horizons_ignore_the_split_estimate():
    p = _params([("all", 2000, 50.0)])
    assert p.lookup(V, "development", "ALT", "all", 1200)[:2] == (-0.5, "four_coin_proxy")  # optimistic
    v, method, used, _ = p.lookup(V, "stress", "ALT", "all", 1200, bucket="1M-5M")  # stress (and severe)
    assert v == 9.0 and method == "stress_max_proxy_coin_300s" and "hlsplit" not in used
    assert p.lookup(V, "development", "ALT", "all", 300_000, conservative=True)[:2] == (3.68, "coin_approximate")


def test_config_fixes_the_adr0160_rule_and_receive(ctx):
    r = load_yaml("execution.yaml", ctx.root / "config")["replay"]
    assert r["receive_ms"] == 392 and r["debounce_ms"] == 250
    assert r["alt_short_floor"] == {"rule": "hl_split_orders", "bins_ms": [1000, 2000, 5000, 10000],
                                    "sequence_gap_ms": 60000, "min_orders": 30}
    assert Parameters.from_rules(pl.DataFrame(schema=dict.fromkeys(COLS, pl.Float64)).cast(
        {"origin": pl.Date, "period": pl.String, "coin": pl.String, "band": pl.String, "horizon_ms": pl.Int64}),
        r).short_bins == (1000, 2000, 5000, 10000)


# ------------------------------------------------------------------------------------ receive (ADR-0161)
def test_receive_shift_keeps_batch_grouping_and_moves_the_decision():
    ev = _events([
        ("w", "A", 1, 7, T + 1000, 1, 11, 100.0, "buy", False, 1.0, 1.0),
        ("w", "A", 2, 7, T + 1250, 2, 12, 101.0, "buy", False, 2.0, 1.0),   # at the debounce deadline: same batch
        ("w", "A", 3, 7, T + 1251, 3, 13, 102.0, "buy", False, 3.0, 1.0),   # after it: a new batch
    ])
    old, new = batches(ev, 250, 250, START, END), batches(ev, 392, 250, START, END)
    assert old["source_rows"].to_list() == new["source_rows"].to_list() == [[1, 2], [3]]
    assert (new["decision_ms"] - old["decision_ms"]).to_list() == [142, 142]
    assert new["decision_ms"].to_list() == [T + 1000 + 392 + 250, T + 1251 + 392 + 250]
    assert (new["last_visible_ms"] - new["event_ms"]).to_list() == [250 + 392, 392]


# ------------------------------------------------------------------------------------ published outputs
@pytest.mark.data
def test_published_split_cells_and_methods(ctx):
    root = ctx.root / "research/replay_frozen"
    need(root / "drift_cells.parquet", "run `python -m arkstream replay --frozen`")
    cells = pl.read_parquet(root / "drift_cells.parquet").filter(C("source") == "hl_split_orders")
    assert not cells.is_empty() and (cells["measured"] >= 30).all()
    assert set(cells["horizon_ms"]) <= {1000, 2000, 5000, 10000} and set(cells["band"]) == {"all"}
    assert cells["origin"].max() <= date(2025, 12, 3)
    folder = root / "origin=2025-11-19" / "window=test" / "scenario=base_sqrt_cap_part_ns_sweep_frozen"
    o = pl.scan_parquet(folder / "follower_orders.parquet").select("method", "parameter_cells").collect()
    split = o.filter(C("method") == "base_max_proxy_hlsplit_zero")
    assert split.height > 0 and split["parameter_cells"].str.contains("hlsplit:").all()


# ------------------------------------------------------------------------------------ capture (ADR-0162)
def _capture_case():
    from arkstream.replay_capture import capture

    ref, w, imp, fee = 100.5, 5.0, 10.0, 0.05
    fill = ref * (1 + (w + imp) / 1e4)
    orders = pl.DataFrame({
        "trader": ["t", "t", "t"], "coin": ["X", "X", "Y"], "status": ["filled", "below_minimum", "failed_price_check"],
        "quantity": [1.0, 0.05, 1.0], "fill_px": [fill, None, None], "fee": [fee, None, None],
        "anchor_px": [100.2, 100.0, 50.0], "leader_first_px": [100.0, 100.0, 50.0], "mid_L": [100.1, None, None],
        "ref_px": [ref, None, None], "impact_bps": [imp, None, None], "intended_notional": [100.2, 5.0, 50.0],
        "requested_qty": [1.0, 0.05, 1.0], "submitted_qty": [1.0, 0.05, 1.0]})
    bench = pl.DataFrame({"trader": ["t"] * 3, "coin": ["X", "X", "Y"], "status": ["filled"] * 3,
                          "quantity": [1.0, 0.05, 1.0], "fill_px": [100.0, 100.0, 50.0]})
    m_end = pl.DataFrame({"coin": ["X", "Y"], "m_end": [110.0, 45.0]})
    f_pnl = 1.0 * (110 - fill) - fee - 0.1
    b_pnl = 1.05 * (110 - 100) + 1.0 * (45 - 50) - 0.2
    day = date(2025, 10, 23)
    daily = pl.DataFrame({"trader": ["t"], "day": [day], "equity": [10_000 + f_pnl], "funding": [-0.1]})
    bdaily = pl.DataFrame({"trader": ["t"], "day": [day], "equity": [10_000 + b_pnl], "funding": [-0.2]})
    universe = pl.DataFrame({"trader": ["t"], "all_gates_pass": [True], "return_source": ["book"],
                             "leader_return": [0.3], "leader_days": [14]})
    return capture(orders, daily, bdaily, bench, m_end, universe, 10_000.0).row(0, named=True), fill, f_pnl, b_pnl


def test_capture_parts_sum_exactly_to_the_gap():
    from arkstream.replay_capture import PARTS

    r, fill, f_pnl, b_pnl = _capture_case()
    assert r["gap"] == pytest.approx(b_pnl - f_pnl)
    assert abs(r["closure"]) < 1e-9 and sum(r[p] for p in PARTS) == pytest.approx(r["gap"], abs=1e-9)
    assert r["sweep_anchor"] == pytest.approx(0.2) and r["delay_drift"] == pytest.approx(0.4)
    assert r["impact"] == pytest.approx(ref_impact := 100.5 * 10 / 1e4) and r["fees"] == 0.05
    assert r["half_spread"] == pytest.approx((100.1 - 100.2) + (fill - 100.5) - ref_impact)
    assert r["funding_difference"] == pytest.approx(-0.1)
    assert r["not_executed_below_minimum"] == pytest.approx(0.05 * 10)  # the 0.05 X the follower missed
    assert r["not_executed_uncopyable_coin"] == pytest.approx(-5.0)  # Y: the benchmark lost there
    assert r["status"] == "not_meaningful"  # |benchmark| = 5.3 < 100 USDC: no ratio
    assert r["capture_ratio"] is None and r["leader_return"] == 0.3


def test_market_relative_regression_and_buy_and_hold():
    from arkstream.replay_capture import market_relative

    rng = np.random.default_rng(1)
    n = 30
    btc, eth = rng.normal(0, 0.02, n), rng.normal(0, 0.03, n)
    y = 0.001 + 0.5 * btc - 0.2 * eth
    b0 = 20_000
    marks = pl.DataFrame({"coin": ["BTC"] * (n + 1) + ["ETH"] * (n + 1),
                          "boundary": list(range(b0, b0 + n + 1)) * 2,
                          "mark": list(100 * np.cumprod(np.r_[1, 1 + btc])) + list(10 * np.cumprod(np.r_[1, 1 + eth]))})
    days = [date(1970, 1, 1) + timedelta(days=b0 + i) for i in range(n)]
    daily = pl.DataFrame({"trader": ["t"] * n, "day": days, "daily_twr": y})
    r = market_relative(daily, marks, b0 * 86_400_000, (b0 + n) * 86_400_000).row(0, named=True)
    assert r["n_days"] == n and r["alpha"] == pytest.approx(0.001) and r["beta_btc"] == pytest.approx(0.5)
    assert r["beta_eth"] == pytest.approx(-0.2) and r["btc_buy_hold"] == pytest.approx(np.prod(1 + btc) - 1)


@pytest.mark.data
def test_published_capture_closes_and_covers_every_window(ctx):
    root = ctx.root / "research/replay_frozen"
    need(root / "capture_summary.parquet", "run `python -m arkstream replay --frozen`")
    cap = pl.read_parquet(root / "capture_summary.parquet")
    assert cap.filter(C("status") != "incomplete")["closure"].abs().max() < 1e-4
    assert set(cap["scenario"]) == {"optimistic", "base", "stress", "severe"}
    assert cap.select("origin", "window").unique().height == 9  # five training and four test windows
    assert cap["origin"].max() == date(2025, 12, 3) and set(cap.filter(C("origin") == date(2025, 12, 3))["window"]) \
        == {"training"}  # the holdout test window is never computed
    ok = cap.filter(C("status") == "ok")
    assert (ok["follower_pnl"] / ok["benchmark_pnl"] - ok["capture_ratio"]).abs().max() < 1e-12
    assert (cap.filter(C("status") == "not_meaningful")["benchmark_pnl"].abs() < 100).all()
    mr = pl.read_parquet(root / "market_relative.parquet")
    assert set(mr["scenario"]) == {"optimistic", "base", "stress", "severe", "benchmark"}
