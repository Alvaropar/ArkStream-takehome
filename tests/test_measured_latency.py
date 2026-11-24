"""ADR-0058: the measured copy delay. Delays and drift horizons are whole milliseconds end to end (1.2 s is never
truncated to 1 s), the scenarios come from config/execution.yaml (base 1.2 s, stress 5 s for every coin, optimistic
1 s, severe 60 s / 300 s at stress costs), and severe prices exactly as stress at its own delays."""

from datetime import date

import polars as pl
import pytest
from conftest import make_fills, need, ts
from test_drift import _rules, _zip
from test_replay import START, example

from arkstream import drift
from arkstream.config import load_yaml
from arkstream.replay import delay_results, stress_floor
from arkstream.replay_frozen import stress_scenarios
from arkstream.replay_orders import Parameters, delay_plan, regime, resolve_scenarios

C = pl.col
DIRECT = ("BTC", "ETH", "HYPE", "SOL")


@pytest.fixture(scope="module")
def scenarios():
    return resolve_scenarios(load_yaml("execution.yaml")["scenarios"])


# ------------------------------------------------------------------------------------ milliseconds, not seconds
def test_seconds_to_ms_is_exact():
    assert [drift.seconds_to_ms(x) for x in (1, 1.2, 5, 10, 60, 300, "1.2")] == [1000, 1200, 5000, 10_000, 60_000,
                                                                                 300_000, 1200]
    for bad in (0, -1, 0.0005, 1.2345, True):
        with pytest.raises(ValueError):
            drift.seconds_to_ms(bad)


def test_config_horizons_and_delays_in_ms(ctx, scenarios):
    r = drift.DriftRules.from_config(ctx.raw)
    assert r.horizons_ms == (1000, 1200, 5000, 10_000, 60_000, 300_000)
    assert r.approx_horizons_ms == (300_000, 3_600_000) and r.approx_min_horizon_ms == 300_000
    assert {n: (s["delay_ms"], s["delay_thin_ms"]) for n, s in scenarios.items()} == {
        "optimistic": (1000, None), "base": (1200, None), "stress": (5000, None), "severe": (60_000, 300_000)}
    with pytest.raises(ValueError, match="ascending"):
        _rules(horizons_ms=(1000, 1000))


def test_aggtrades_drift_at_1_2_s_reads_the_1_2_s_print(tmp_path):
    root = tmp_path / "agg"
    _zip(root, "BTCUSDT", "2025-10-09", [("2025-10-09 00:00:09.900", 100.0), ("2025-10-09 00:00:11", 101.0),
                                         ("2025-10-09 00:00:11.150", 103.0)])
    r = _rules(horizons_ms=(1000, 1200))
    src = drift.AggTradesSource(root, r, require_manifest=False)
    fills = make_fills([dict(ts="2025-10-09 00:00:10", trader="0xa", symbol="BTC", side="buy", size=1.0,
                             start_position=0.0, price=100.0, oid=1)])
    m = drift.aggtrades_drift(drift.leader_orders(fills, ts("2025-10-09 00:00:00"), r.est_end_ts), src, r)
    got = dict(m.select("horizon_ms", "drift_bps").rows())
    assert got[1000] == pytest.approx(100.0)  # the print at t + 1.0 s
    assert got[1200] == pytest.approx(300.0)  # the print at t + 1.15 s: a 1 s truncation would give 100 bps
    cells = drift.pool(m, pl.DataFrame({"trader": ["0xa"], "band": ["<1m"]}), r, "development")
    assert sorted(set(cells["horizon_ms"])) == [1000, 1200] and sorted(set(cells["horizon_s"])) == [1.0, 1.2]


def test_order_inputs_acknowledge_at_exactly_1_2_s():
    o = example(delay=1200)
    assert o["delay_ms"].unique().to_list() == [1200] and o["delay_s"].unique().to_list() == [1.2]
    assert (o["ack_ms"] - o["event_ms"]).unique().to_list() == [1200]
    assert (o["b1_ms"] - o["event_ms"]).unique().to_list() == [1200]  # the print at t + 1.2 s, not t + 1 s
    with pytest.raises(ValueError, match="whole milliseconds"):
        example(delay=1.2)  # a delay in seconds is refused, not truncated


def test_parameter_cells_keyed_by_ms():
    v = START.date()
    cells = [(v, "development", c, "all", 1200, 2.0, 30) for c in DIRECT]
    cells.append((v, "development", "ALT", "all", 300_000, 1.0, 30))
    p = Parameters(pl.DataFrame(cells, orient="row",
                                schema=["origin", "period", "coin", "band", "horizon_ms", "mean_bps", "measured"]))
    assert p.lookup(v, "development", "ALT", "all", 1200)[0] == 2.0  # the 1.2 s four-coin proxy
    assert p.lookup(v, "development", "ALT", "all", 1000)[0] is None  # no 1 s cell: never borrowed from 1.2 s
    assert p.lookup(v, "development", "ALT", "all", 1200, conservative=True)[0] == 2.0  # max(2, own 1, 0)


def test_break_even_bracket_keeps_1_2_s():
    g = pl.DataFrame({"trader": ["a"] * 3, "delay_ms": [1000, 1200, 5000], "copy_return": [0.01, -0.01, -0.02],
                      "filled": [1, 1, 1]})
    r = delay_results(g).row(0, named=True)
    assert (r["break_even_delay_lo_ms"], r["break_even_delay_hi_ms"]) == (1000, 1200)
    assert (r["break_even_delay_lo_s"], r["break_even_delay_hi_s"]) == (1.0, 1.2)


# ------------------------------------------------------------------------------------ scenarios and severe
def test_severe_takes_the_stress_costs_and_only_its_own_delays(scenarios):
    st, sv = scenarios["stress"], scenarios["severe"]
    assert {k: sv[k] for k in ("fee_bps", "half_spread_bps", "impact")} == \
        {k: st[k] for k in ("fee_bps", "half_spread_bps", "impact")}
    assert sv["costs"] == "stress" and sv["label"] == "sensitivity" and st["costs"] == "stress"
    assert regime("severe", sv) == "stress" and regime("unattainable_all") == "unattainable_all"
    rules = {"stress_min_priced_share": 0.8}
    assert stress_floor("severe", rules, sv) == stress_floor("stress", rules, st) == 0.8
    assert stress_floor("base", rules, scenarios["base"]) is None


def test_scenario_config_is_refused_when_ambiguous():
    raw = load_yaml("execution.yaml")["scenarios"]
    with pytest.raises(ValueError, match="delay_ms"):
        resolve_scenarios({**raw, "base": {**raw["base"], "delay_s": 1.2}})
    with pytest.raises(ValueError, match="whole milliseconds"):
        resolve_scenarios({**raw, "base": {**raw["base"], "delay_ms": 1.2}})
    with pytest.raises(ValueError, match="may not set"):
        resolve_scenarios({**raw, "severe": {**raw["severe"], "fee_bps": 1.0}})  # costs come from stress only
    with pytest.raises(ValueError, match="cost regime"):
        resolve_scenarios({**raw, "severe": {**raw["severe"], "costs_of": "nowhere"}})


def test_delay_plan_runs_each_scenario_once_at_its_main_delay(scenarios):
    grid = (1000, 1200, 5000, 10_000, 60_000, 300_000)
    plan = delay_plan(scenarios, grid)
    assert [k for k, _ in plan] == [*grid, (60_000, 300_000)]
    mains = {name: k for k, runs in plan for name, _, main in runs if main}
    assert mains == {"optimistic": 1000, "base": 1200, "stress": 5000, "severe": (60_000, 300_000)}
    on_grid = {name for _, runs in plan for name, g, _ in runs if g}
    assert on_grid == {"optimistic", "base", "stress"}  # severe shares the stress grid (same costs, fixed delays)
    assert all(len([r for r in runs if r[1]]) == 3 for k, runs in plan if isinstance(k, int))
    with pytest.raises(ValueError, match="not a point of the delay grid"):
        delay_plan(scenarios, (1000, 10_000, 60_000, 300_000))  # 1.2 s and 5 s missing: no aggTrades query


def test_severe_prices_exactly_as_stress_at_the_same_delay(scenarios):
    for coin in ("BTC", "ALT"):
        a = example(coin, scenario="stress", settings=scenarios["stress"])
        b = example(coin, scenario="severe", settings=scenarios["severe"])
        assert a.equals(b), coin
        assert a["period"].unique().to_list() == ["stress"]
    assert example("ALT", scenario="severe", settings=scenarios["severe"])["mean_bps"][0] == 4  # stress cells


def test_severe_thin_coin_rule(scenarios):
    rule = (60_000, 300_000)
    assert example(delay=rule)["delay_ms"].unique().to_list() == [60_000]  # 4h bar 10M USDC: not thin
    thin = example(delay=rule, bar_volume=1e5)
    assert thin["delay_ms"].unique().to_list() == [300_000]
    assert (thin["ack_ms"] - thin["event_ms"]).unique().to_list() == [300_000]


def test_stress_regime_scenarios(ctx):
    assert stress_scenarios(ctx) == ["stress", "severe"]


# ------------------------------------------------------------------------------------ published outputs
@pytest.mark.data
def test_new_drift_cells_at_every_origin(ctx):
    root = ctx.root / "research/drift"
    need(root / "drift_development.csv", "run `python -m arkstream drift`")
    dev = pl.read_csv(root / "drift_development.csv", try_parse_dates=True)
    st = pl.read_csv(root / "drift_stress.csv", try_parse_dates=True)
    rules = drift.DriftRules.from_config(ctx.raw)
    for h in (1200, 5000):
        for o in rules.origin_dates:
            cell = dev.filter((C("origin") == o) & (C("source") == "aggtrades") & (C("band") == "all")
                              & (C("horizon_ms") == h) & (C("estimate") == "ok"))
            assert sorted(cell["coin"]) == list(DIRECT), (h, o)  # all four: the four-coin proxy exists
            assert cell["horizon_s"].to_list() == [h / 1000] * 4
        for o in [o for o in rules.origin_dates if o > date(2025, 10, 11)]:  # the crash sample, after it only
            cell = st.filter((C("origin") == o) & (C("source") == "aggtrades") & (C("band") == "all")
                             & (C("horizon_ms") == h) & (C("estimate") == "ok"))
            assert sorted(cell["coin"]) == list(DIRECT), (h, o)
    assert st.filter(C("origin") == rules.origin_dates[0]).is_empty()  # 8 Oct: nothing borrowed from later


@pytest.mark.data
def test_published_frozen_delays(ctx):
    root = ctx.root / "research/replay_frozen"
    folder = root / "origin=2025-10-22" / "window=test"
    need(folder / "scenario=severe_sqrt_cap_part_ns_sweep_frozen" / "follower_orders.parquet",
         "run `python -m arkstream replay --frozen`")
    expected = {"optimistic": {1000}, "base": {1200}, "stress": {5000}, "severe": {60_000, 300_000}}
    for name, delays in expected.items():
        sc = folder / f"scenario={name}_sqrt_cap_part_ns_sweep_frozen"
        o = pl.scan_parquet(sc / "follower_orders.parquet").select("delay_ms", "event_ms", "ack_ms").collect()
        assert set(o["delay_ms"]) == delays, name
        assert (o["ack_ms"] - o["event_ms"] == o["delay_ms"]).all(), name
        if name == "severe":
            assert not (sc / "delay_grid.parquet").exists()  # it reports the stress grid
        else:
            g = pl.read_parquet(sc / "delay_grid.parquet")
            assert sorted(set(g["delay_ms"])) == [1000, 1200, 5000, 10_000, 60_000, 300_000], name
