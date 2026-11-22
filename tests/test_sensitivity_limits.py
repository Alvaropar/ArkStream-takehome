"""ADRs 0086-0088: participation cap, no scale-up, leader-sweep anchor and the size-term rule (synthetic data)."""

from datetime import date

import polars as pl
import pytest
from test_replay import BASE, END, RULES, START, T

from arkstream.replay_cap import MinuteMarks, cap_legs
from arkstream.replay_orders import batches, execute, sweep_anchor
from arkstream.replay_sensitivity import SPEC, canonical, settings_for
from arkstream.replay_size import contrasts

C = pl.col
EVENT_COLS = ["trader", "coin", "seq", "oid", "event_ms", "src_row", "tid", "price", "side", "is_maker", "pos_after"]


def _events(rows):
    return pl.DataFrame(rows, schema=[*EVENT_COLS, "size"], orient="row")


def test_batch_records_leader_notional_vwap_and_deepest_fill():
    ev = _events(
        [
            ("w", "A", 1, 7, T + 1000, 1, 11, 100.0, "buy", False, 1.0, 1.0),
            ("w", "A", 2, 7, T + 1000, 2, 12, 101.0, "buy", False, 4.0, 3.0),
        ]
    )
    b = batches(ev, 250, 250, START, END).row(0, named=True)
    assert b["anchor_px"] == 100.0 and b["leader_deepest"] == 101.0
    assert b["leader_notional"] == pytest.approx(100 + 303)
    assert b["leader_vwap"] == pytest.approx(403 / 4)


def test_sweep_anchor_by_scenario_keeps_makers_and_resize_legs():
    f = pl.DataFrame(
        {
            "anchor_px": [100.0, 100.0, 100.0],
            "leader_vwap": [100.5, 100.5, 100.5],
            "leader_deepest": [101.0, 101.0, 101.0],
            "side": ["buy", "buy", "buy"],
            "is_maker": [False, True, False],
            "resize_leg": [False, False, True],
        }
    )
    base, stress, opt = (sweep_anchor(f, s) for s in ("base", "stress", "optimistic"))
    assert base["anchor_px"].to_list() == [100.5, 100.0, 100.0]
    assert stress["anchor_px"].to_list() == [101.0, 100.0, 100.0]
    assert opt["anchor_px"].to_list() == [100.0, 100.0, 100.0]
    assert base["anchor_rule"].to_list() == ["vwap", "first_fill", "first_fill"]
    assert base["sweep_bps"][0] == pytest.approx(100.0) and base["sweep_bps"][1] is None
    sell = f.with_columns(side=pl.lit("sell"), leader_deepest=pl.lit(99.0), leader_vwap=pl.lit(99.5))
    assert sweep_anchor(sell, "stress")["sweep_bps"][0] == pytest.approx(100.0)  # a sell sweeps down: a cost


def test_no_scale_up_caps_the_copy_multiplier_at_one():
    marks = MinuteMarks(T, T + 3_600_000, ["A"])
    marks.values["A"][:] = 100.0
    ev = _events([("w", "A", 1, 1, T + 1000, 1, 11, 100.0, "buy", False, 5.0, 5.0)])
    snaps = pl.DataFrame({"trader": ["w"], "equity": [2000.0], "frozen": [False], "eq_ms": [T], "equity_row": [9]})
    b = batches(ev, 250, 250, START, END)
    scaled = cap_legs(b, ev, snaps, marks, {"A"}, 10000, 15000, 250, START, END)
    capped = cap_legs(b, ev, snaps, marks, {"A"}, 10000, 15000, 250, START, END, no_scale_up=True)
    assert scaled["uncapped_target"][0] == pytest.approx(5.0 * 10000 / 2000)  # 5x the leader's own position
    assert capped["uncapped_target"][0] == pytest.approx(5.0)  # never larger than the leader


def _candidate(qty_target, leader_usdc, volume):
    marks = MinuteMarks(T, T + 3_600_000, ["A"])
    marks.values["A"][:] = 100.0
    frame = pl.DataFrame(
        {
            "trader": ["w"],
            "coin": ["A"],
            "decision_ms": [T + 2000],
            "ack_ms": [T + 12000],
            "equity": [10000.0],
            "pos_after": [qty_target],
            "anchor_px": [100.0],
            "ref_px": [100.0],
            "price_reason": [""],
            "half_bps": [1.0],
            "bar_volume_usdc": [volume],
            "frozen": [False],
            "capped_target": [qty_target],
            "decision_mark": [100.0],
            "resize_leg": [False],
            "mean_bps": [None],
            "mid_L": [100.0],
            "leader_notional": [leader_usdc],
            "volume_daily": [6 * volume],
            "sigma_daily": [0.02],
            "signal": [0],
            "batch": [0],
            "oid": [1],
        },
        schema_overrides={"mean_bps": pl.Float64, "leader_notional": pl.Float64},
    )
    return frame, marks


@pytest.mark.parametrize("no_scale_up", [False, True])
def test_order_budget_clips_at_decision_and_at_fill(no_scale_up):
    frame, marks = _candidate(qty_target=50.0, leader_usdc=2000.0, volume=200_000.0)  # wants 5,000 USDC
    settings = dict(BASE, sqrt_y=1.0, participation=0.005, no_scale_up=no_scale_up)
    got = execute(frame, settings, dict(RULES, cap_usdc=15000), cap_marks=marks).row(0, named=True)
    budget = min(1000.0, 2000.0) if no_scale_up else 1000.0  # 0.5% of a 200k bar; leader traded 2k
    assert got["order_budget_usdc"] == pytest.approx(budget)
    assert got["requested_qty"] == pytest.approx(50.0)
    assert got["submitted_qty"] == pytest.approx(budget / 100.0)
    assert got["status"] == "filled"
    assert abs(got["quantity"]) * got["fill_px"] <= budget + 1e-9  # repriced with impact, still inside the budget
    tight, marks = _candidate(qty_target=50.0, leader_usdc=300.0, volume=200_000.0)
    got = execute(tight, settings, dict(RULES, cap_usdc=15000), cap_marks=marks).row(0, named=True)
    assert got["order_budget_usdc"] == pytest.approx(300.0 if no_scale_up else 1000.0)


def test_missing_budget_inputs_skip_the_order():
    frame, marks = _candidate(qty_target=50.0, leader_usdc=None, volume=200_000.0)
    rules = dict(RULES, cap_usdc=15000)
    no_leader = execute(frame, dict(BASE, sqrt_y=1.0, participation=0.005, no_scale_up=True), rules, cap_marks=marks)
    assert no_leader["status"][0] == "missing_order_budget"
    frame, marks = _candidate(qty_target=50.0, leader_usdc=2000.0, volume=0.0)
    no_volume = execute(frame, dict(BASE, sqrt_y=1.0, participation=0.005, no_scale_up=False), rules, cap_marks=marks)
    assert no_volume["status"][0] == "missing_participation_volume"


def test_variant_specs_are_cumulative():
    rules = {"square_root": {"y": 1.0}, "max_participation": 0.005}
    assert settings_for(BASE, "part", rules)["no_scale_up"] is False
    assert settings_for(BASE, "part_ns_sweep", rules)["no_scale_up"] is True
    assert SPEC["part_ns_sweep"]["sweep"] and SPEC["part_ns"]["plan"] == "capped_ns"
    assert canonical("base", "part_ns_sweep") == "base_sqrt_cap_part_ns_sweep"


def test_size_term_needs_three_coins_on_both_axes():
    rows = []
    for coin, large_extra in (("BTC", 2.0), ("ETH", 2.0), ("HYPE", 2.0), ("SOL", -1.0)):
        for i in range(40):
            for q, share, bps in ((500.0, 0.00005, 0.0), (200_000.0, 0.01, large_extra)):
                rows.append((coin, 10, T + i, T + i + 10_000, q, share, bps))
    obs = pl.DataFrame(rows, schema=["coin", "delay_s", "t", "ack", "q", "share", "bps"], orient="row").with_columns(
        usd_bucket=pl.lit("x"), share_bucket=pl.lit("y")
    )
    _, panels, terms = contrasts(obs, [date(2025, 10, 23)])
    assert panels["support"].sum() == 3
    assert terms["size_term_bps"][0] == pytest.approx(1.0)  # high-share mean 2 minus the coin average 1
    weak = obs.filter(C("coin") != "BTC")
    assert contrasts(weak, [date(2025, 10, 23)])[2]["size_term_bps"][0] == 0.0  # two supporting coins: no term
