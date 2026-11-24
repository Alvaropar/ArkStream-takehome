"""End-to-end check that the frozen copy follows the leader's *net* position through a fragmented lifecycle.

Synthetic leader, one coin (BTC, a direct aggTrades coin), driven through the frozen replay's own path:
`batches` -> `reference_equity` -> `cap_legs` (no scale-up) -> `order_inputs` (1.2 s) -> `quotes` (base, sweep anchor)
-> `execute` (square-root impact, 0.5% participation, leader-batch budget, 1.5x cap, reserved pending quantity).

The leader scales in over several orders (two fills in the same millisecond on different order ids, two fills of one
order in the same millisecond), reduces in two steps (one split across two fills inside the debounce, one fill that
becomes visible only after an earlier decision), closes, opens a short, flips long in a single fill and closes again.
Acknowledgements arrive 1.2 s after the leader's fill, so later decisions are taken while earlier orders are pending.

Invariants (from the copy-trading review, decision/pre-holdout-checks.md):
1. the follower target is the frozen multiplier times the leader's latest *visible* net position;
2. a partial leader reduction never sets a flat or opposite target;
3. no double counting: each order requests target - (held + pending) at its decision;
4. no overshoot: a fill never exceeds or reverses its request, and the copy never holds more than its largest target
   (including through the flip) or more than the 1.5x gross cap;
5. a full leader close sets a zero target; without volume limits the copy ends within exchange-minimum dust of flat,
   and with them every close is still submitted.
"""

from datetime import timedelta

import polars as pl
import pytest
from test_replay import END, START, T, parameters

from arkstream.replay_cap import MinuteMarks, cap_legs, reference_equity
from arkstream.replay_orders import NOT_SUBMITTED, batches, execute, order_inputs, quotes
from arkstream.replay_sensitivity import settings_for

C = pl.col
COIN = "BTC"
PX = 100.0
ALLOC, CAP, RECEIVE, DEBOUNCE, DELAY = 10_000.0, 15_000.0, 392, 250, 1200
LEADER_EQUITY = 20_000.0  # frozen E_ref -> multiplier 0.5 (no scale-up: min(10k, 20k) / 20k)
MULT = ALLOC / LEADER_EQUITY
BASE = {"fee_bps": 4.5, "half_spread_bps": {"majors": 1.0, "other": 5.0}, "impact": "linear"}
RULES = {"allocation_usdc": ALLOC, "min_notional_usdc": 10.0, "thin_volume_usdc": 1e6, "cap_usdc": CAP,
         "receive_ms": RECEIVE, "debounce_ms": DEBOUNCE, "square_root": {"y": 1.0}, "max_participation": 0.005}

# (oid, ms after T, side, size, leader net position after the fill)
FILLS = [
    (1, 0, "buy", 60.0, 60.0),            # entry, two fills of one order in the same millisecond
    (1, 0, "buy", 40.0, 100.0),
    (2, 5_000, "buy", 50.0, 150.0),       # scale-in: two orders in the same millisecond
    (3, 5_000, "buy", 50.0, 200.0),
    (4, 5_300, "sell", 50.0, 150.0),      # partial close, visible only after the scale-in decision (5,642 ms)
    (5, 20_000, "sell", 60.0, 90.0),      # partial close split across two fills inside the debounce
    (5, 20_100, "sell", 40.0, 50.0),
    (6, 40_000, "sell", 50.0, 0.0),       # final close
    (7, 60_000, "sell", 100.0, -100.0),   # new short from flat
    (8, 80_000, "buy", 250.0, 150.0),     # flip short -> long in one fill
    (9, 100_000, "sell", 150.0, 0.0),     # close
]


def _events() -> pl.DataFrame:
    rows = [("w", COIN, seq, oid, T + dt, 100 + seq, 500 + seq, PX, side, False, pos, size)
            for seq, (oid, dt, side, size, pos) in enumerate(FILLS)]
    return pl.DataFrame(rows, schema=["trader", "coin", "seq", "oid", "event_ms", "src_row", "tid", "price", "side",
                                      "is_maker", "pos_after", "size"], orient="row")


def _visible_leader(decision_ms: int) -> float:
    """The leader's net position from the last fill visible by the decision (event + receive <= decision)."""
    pos = 0.0
    for _, dt, _, _, after in FILLS:  # chain order (seq), as the replay orders visibility
        if T + dt + RECEIVE <= decision_ms:
            pos = after
    return pos


def run(bar_volume_usdc: float) -> pl.DataFrame:
    ev = _events()
    b = batches(ev, RECEIVE, DEBOUNCE, START, END)
    snaps = pl.DataFrame({"trader": ["w"], "eq_ms": [T - 1_000], "equity": [LEADER_EQUITY], "frozen": [False],
                          "equity_row": [1]})
    sizing = reference_equity(snaps, ["w"], START, END, 14)
    marks = MinuteMarks(T - 60_000, T + 3_600_000, [COIN])
    marks.values[COIN][:] = PX
    plan = cap_legs(b, ev, sizing, marks, {COIN}, ALLOC, CAP, RECEIVE, START, END, no_scale_up=True)
    bars = pl.DataFrame({"coin": [COIN], "bar_ms": [T - 1], "bar_volume_usdc": [bar_volume_usdc],
                         "volume_daily": [6 * bar_volume_usdc], "sigma_daily": [0.02]})
    checks = pl.DataFrame({"coin": [COIN], "outcome": ["pass"]})
    mapping = pl.DataFrame({"coin": [COIN], "valid_from": [START.date()], "valid_to": [END.date()],
                            "price_factor_hl_per_binance": [1.0]})
    times = sorted({T + dt for _, dt, *_ in FILLS} | {T + dt + DELAY for _, dt, *_ in FILLS})
    tape = pl.DataFrame([(COIN, t, i, t, PX, "archive") for i, t in enumerate(times)],
                        schema=["coin", "query", "agg_trade_id", "transact_time", "price", "archive"], orient="row")
    bands = pl.DataFrame({"origin": [START.date()], "trader": ["w"], "band": ["all"]})
    spread = pl.DataFrame({"coin": [COIN], "known_at": [END + timedelta(days=1)], "cs_half_bps": [None]},
                          schema_overrides={"cs_half_bps": pl.Float64})
    frame = order_inputs(plan, sizing, bars, checks, mapping, tape, bands, [START.date()], spread, RULES, START, END,
                         DELAY)
    settings = settings_for(BASE, "part_ns_sweep_frozen", RULES)
    priced = quotes(frame, "base", settings, parameters(), sweep=True)
    return execute(priced, settings, RULES, cap_marks=marks).sort("decision_ms", "signal", "resize_leg", "batch")


def held_at(orders: pl.DataFrame, t: int) -> float:
    return float(orders.filter((C("status") == "filled") & (C("ack_ms") <= t))["quantity"].sum())


@pytest.fixture(params=[1e12, 600_000.0], ids=["unconstrained", "participation_clipped"])
def orders(request):
    return run(request.param), request.param


def test_batches_follow_orders_and_debounce(orders):
    o, _ = orders
    legs = o.filter(~C("resize_leg"))
    # one decision per (order id, debounce batch): oid 1's two same-ms fills and oid 5's two fills are one batch each
    assert legs["oid"].to_list() == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert (legs["ack_ms"] - legs["event_ms"]).unique().to_list() == [DELAY]


def test_target_is_the_visible_net_position(orders):
    o, _ = orders
    for r in o.filter(~C("resize_leg")).iter_rows(named=True):
        leader = _visible_leader(r["decision_ms"])
        assert r["pos_after"] == pytest.approx(leader), r["oid"]                       # invariant 1
        assert r["capped_target"] == pytest.approx(MULT * leader), r["oid"]
        if leader != 0:                                                                 # invariant 2
            assert r["capped_target"] * leader > 0, r["oid"]
    # the reduction that arrives after the scale-in decision is seen by its own decision, not by the earlier one
    by_oid = dict(o.filter(~C("resize_leg")).select("oid", "capped_target").iter_rows())
    assert by_oid[2] == by_oid[3] == pytest.approx(MULT * 200.0)
    assert by_oid[4] == pytest.approx(MULT * 150.0)
    assert by_oid[5] == pytest.approx(MULT * 50.0)                                     # partial, not flat
    assert by_oid[6] == by_oid[9] == 0.0                                                # invariant 5: closes


def test_requests_net_out_held_and_pending(orders):
    o, _ = orders
    rows = o.with_row_index("k").iter_rows(named=True)
    seen: list[dict] = []
    for r in rows:
        d = r["decision_ms"]
        held = sum(p["quantity"] for p in seen if p["status"] == "filled" and p["ack_ms"] <= d)
        pending = sum(p["submitted_qty"] for p in seen if p["status"] not in NOT_SUBMITTED and p["ack_ms"] > d)
        if r["requested_qty"] is not None:                                              # invariant 3
            assert r["requested_qty"] == pytest.approx(r["capped_target"] - held - pending, abs=1e-9), r["oid"]
        seen.append(r)
    # oid 4 decides at 5,942 ms while the scale-in orders (ack 6,200 ms) are still pending
    r4 = o.filter(C("oid") == 4).row(0, named=True)
    assert r4["decision_ms"] < o.filter(C("oid") == 2)["ack_ms"][0]


def test_no_overshoot_and_no_overexposure(orders):
    o, _ = orders
    filled = o.filter(C("status") == "filled")
    for r in filled.iter_rows(named=True):                                              # invariant 4
        assert r["quantity"] * r["requested_qty"] > 0
        assert abs(r["quantity"]) <= abs(r["requested_qty"]) + 1e-9
    largest = max(abs(t) for t in o["capped_target"].drop_nulls())
    for t in sorted(set(filled["ack_ms"].to_list())):
        pos = held_at(o, t)
        assert abs(pos) <= largest + 1e-9, t
        assert abs(pos) * PX <= CAP + 1e-6, t
    # the flip goes from the short straight to the long target in one order, never beyond it
    flip = o.filter(C("oid") == 8).row(0, named=True)
    assert flip["capped_target"] == pytest.approx(MULT * 150.0)
    assert held_at(o, flip["ack_ms"]) <= flip["capped_target"] + 1e-9


def test_closes_reach_flat(orders):
    o, volume = orders
    for oid in (6, 9):
        close = o.filter(C("oid") == oid).row(0, named=True)
        before = held_at(o, close["decision_ms"])
        assert close["status"] == "filled" and close["quantity"] * before < 0           # every close is submitted
    final = held_at(o, int(o["ack_ms"].max()))
    if volume > 1e9:
        # invariant 5: without volume limits only the leader-batch budget can shave a close (impact makes the order
        # slightly larger than the leader's notional), so the copy ends within exchange-minimum dust of flat
        assert abs(final) * PX < RULES["min_notional_usdc"]
    else:
        # clipped closes leave a residual that waits for the leader's next order in the coin (Check 5); the target is
        # zero and nothing adds to the position
        assert o.filter(C("oid") == 9)["capped_target"][0] == 0.0
        assert abs(final) <= abs(held_at(o, o.filter(C("oid") == 9)["decision_ms"][0])) + 1e-9
