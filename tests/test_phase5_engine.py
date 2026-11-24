"""Phase 5 engine fault tests (F1), shape (F6) and determinism (F5), ADRs 0087-0089 and 0095, on a synthetic market."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from arkstream import portfolio_engine as PE
from arkstream import risk_model as RM
from arkstream.leader_risk import shocks

H = PE.HOUR
A, B = "0xa", "0xb"
T0 = 1_760_000_400_000 - (1_760_000_400_000 % PE.DAY)  # a UTC midnight


class FakeMarket:
    def __init__(self, marks=None, path=None, volume=1e9, shock=0.10, beta=1.0, drift=0.0):
        self.marks = marks or {"BTC": 100.0, "HYPE": 10.0, "BNB": 50.0, "ETH": 20.0}
        self.path = path or {}  # coin -> [(t, price)] overriding the constant mark from t on
        self.volume, self._shock, self._beta, self._drift = volume, shock, beta, drift

    def mark(self, coin, t):
        p = self.marks.get(coin)
        for when, price in self.path.get(coin, []):
            if t >= when:
                p = price
        return p

    def bar(self, coin, t):
        return (t // PE.BAR) * PE.BAR - PE.BAR, self.volume, self.volume * 6, 0.02

    def drift(self, coin, t, trader, regime, delay_ms, bucket):
        return self._drift

    def half_spread(self, coin, t, regime):
        return 1.0 if regime != "stress" else 3.0

    def funding(self, coin, hour):
        return None, None

    def shock(self, coin, long):
        return self._shock

    def beta(self, coin):
        return self._beta

    def bucket(self, volume):
        return ">=5M"


def costs(name="base", regime="base", impact=1.0, half=1.0):
    return PE.Costs(name=name, regime=regime, delay_ms=1200, delay_thin_ms=None, fee_bps=4.5, half_majors=half,
                    half_other=half, impact_mult=impact, sqrt_y=1.0, thin_volume_usdc=1e6, receive_ms=392,
                    debounce_ms=250)


STRESS = costs("stress", "stress", 3.0, 3.0)


def rules(kind="S", alloc=None, **kw):
    alloc = alloc or {A: 10000.0, B: 10000.0}
    D = sum(alloc.values())
    kw.setdefault("p5_usdc", 0.4 * 0.15 * D)
    return PE.Rules(kind=kind, D=D, allocations=alloc, stress_costs=STRESS, **kw)


def sig(t, trader, coin, pos, e_ref=10000.0, legs=None, forced=False, event_ms=None, tradable=True):
    legs = legs or [PE.Leg(coin, pos, tradable, True, None, "", None, None, None)]
    ev = t - 642 if event_ms is None else event_ms
    return PE.Signal(t=t, trader=trader, coin=coin, event_ms=ev, ack_ms=ev + 1200, legs=tuple(legs), e_ref=e_ref,
                     forced=forced)


def run(r, signals, market=None, end_h=48, **kw):
    eng = PE.Engine(r, costs(), market or FakeMarket(), T0, T0 + end_h * H, **kw)
    return eng, eng.run(signals)


def held(eng, trader, coin):
    s = eng.sleeves[trader]
    return s.held[coin]


# ---------------------------------------------------------------------------------------------- solver (F1)
def test_p2_sleeve_scales_the_whole_sleeve_never_a_leg():
    m = FakeMarket()
    base = {A: {"HYPE": 1365.0, "BTC": 10.0}}  # 13,650 USDC HYPE, 1,000 USDC BTC
    res = PE.solve(rules("S", {A: 10000.0}, ), base, {A: 1.0}, m.marks, m, T0, {A: 10000.0})
    assert res.lam[A] == pytest.approx(0.10 * 10000 / 13650, rel=1e-9)
    assert res.set_by[A] == "P2_sleeve"


def test_each_portfolio_limit_is_restored_by_a_common_factor():
    m = FakeMarket(shock=0.20)
    r = rules()
    base = {A: {"BTC": 60.0}, B: {"BTC": 40.0}}  # net BTC 10,000 > 25% of 20,000
    res = PE.solve(r, base, {A: 1.0, B: 1.0}, m.marks, m, T0, {A: 1e4, B: 1e4})
    net = sum(res.lam[i] * base[i]["BTC"] for i in base) * 100.0
    assert net <= 0.25 * 20000 + 1e-6
    assert res.lam[A] == pytest.approx(res.lam[B], rel=1e-9)  # one common factor on the contributing sleeves
    # P4: stress plus exit within 15% of D
    stress = PE.stress_loss({"BTC": net / 100.0}, m.marks, m, STRESS, T0, A)
    assert stress <= 0.15 * 20000 + 1e-6


def test_p5_budget_binds_on_a_high_shock_coin_without_a_waiver():
    m = FakeMarket(shock=0.60)
    base = {A: {"HYPE": 190.0}, B: {"HYPE": 10.0}}  # 2,000 USDC of HYPE in total
    res = PE.solve(rules(), base, {A: 1.0, B: 1.0}, m.marks, m, T0, {A: 1e4, B: 1e4})
    q = sum(res.lam[i] * base[i]["HYPE"] for i in base)
    assert PE.stress_loss({"HYPE": q}, m.marks, m, STRESS, T0, A) <= 1200 + 1e-6
    assert "HYPE" in res.p5_binding


def test_offsetting_sleeve_is_not_touched_by_a_net_limit():
    m = FakeMarket(shock=0.0)
    base = {A: {"ETH": 400.0}, B: {"ETH": -100.0}}  # net 6,000 USDC ETH > 5,000
    res = PE.solve(rules(), base, {A: 1.0, B: 1.0}, m.marks, m, T0, {A: 1e4, B: 1e4})
    assert res.lam[B] == 1.0 and res.lam[A] < 1.0


def test_solver_non_convergence_goes_to_zero_and_is_a_fault():
    m = FakeMarket()
    base = {A: {"HYPE": 1365.0}}
    res = PE.solve(rules("S", {A: 10000.0}, max_passes=1), base, {A: 1.0}, m.marks, m, T0, {A: 1e4})
    assert not res.converged and res.lam[A] == 0.0 and res.fault == "solver_no_convergence"


def test_gray_cap_on_the_remaining_budget():
    m = FakeMarket(shock=0.20)
    base = {A: {"HYPE": 500.0}}  # 5,000 USDC
    r = rules("G", {A: 2500.0})
    full = PE.solve(r, base, {A: 1.0}, m.marks, m, T0, {A: 2500.0}, loss_to_date=0.0)
    used = PE.solve(r, base, {A: 1.0}, m.marks, m, T0, {A: 2500.0}, loss_to_date=500.0)
    s_full = PE.stress_loss({"HYPE": full.lam[A] * 500}, m.marks, m, STRESS, T0, A)
    s_used = PE.stress_loss({"HYPE": used.lam[A] * 500}, m.marks, m, STRESS, T0, A)
    assert s_full == pytest.approx(750, rel=1e-6) and s_used == pytest.approx(250, rel=1e-6)


# ---------------------------------------------------------------------------------------------- engine (F1)
def test_participation_budget_is_shared_within_a_bar():
    m = FakeMarket(volume=200_000.0)  # budget 0.5% = 1,000 USDC per coin per bar
    r = rules("U")
    eng, res = run(r, [sig(T0 + 60_000, A, "BTC", 8.0), sig(T0 + 60_000, B, "BTC", 8.0)], m, end_h=1)
    traded = sum(abs(o["quantity"]) * o["mark"] for o in res.orders if o["status"] == "filled")
    assert traded <= 1000.0 + 1e-6
    assert any(e["event"] == "participation_clip" for e in res.events)


def test_internal_cross_books_no_cost():
    m = FakeMarket()
    r = rules("U")
    # B's short is rejected (no tape), so B still has its delta when A's long arrives two seconds later
    bad = PE.Leg("BTC", -10.0, True, True, None, "no_eligible_aggtrade", None, None, None)
    s1 = [sig(T0 + 60_000, B, "BTC", -10.0, legs=[bad]), sig(T0 + 62_000, A, "BTC", 10.0)]
    eng, res = run(r, s1, m, end_h=1)
    crosses = [f for f in res.fills if f["kind"] == "internal_cross"]
    assert crosses and all(f["fee"] == 0.0 and f["fill_px"] == m.marks["BTC"] for f in crosses)
    assert held(eng, A, "BTC") == pytest.approx(10.0) and held(eng, B, "BTC") == pytest.approx(-10.0)
    physical = [o for o in res.orders if o["status"] == "filled"]
    assert not physical  # the two deltas offset: nothing reached the venue


def test_stale_signal_is_dropped_and_resynced():
    r = rules("U", {A: 10000.0})
    stale = sig(T0 + 60_000, A, "BTC", 10.0, event_ms=T0 + 60_000 - 31_000)
    eng, res = run(r, [stale], end_h=1)
    assert any(e["event"] == "stale_signal" for e in res.events)
    first = [o for o in res.orders if o["reason"] == "signal"]
    assert not first  # not executed at its own decision
    assert held(eng, A, "BTC") == pytest.approx(10.0)  # resynced at the next sweep from the leader's state


def test_flatten_sweep_closes_a_residual():
    r = rules("U", {A: 10000.0})
    eng, res = run(r, [sig(T0 + 60_000, A, "BTC", 10.0), sig(T0 + 2 * H, A, "BTC", 0.0)], end_h=4)
    assert held(eng, A, "BTC") == pytest.approx(0.0)


def test_rejected_order_is_recomputed_from_state_not_resent():
    leg = PE.Leg("BTC", 10.0, True, True, None, "no_eligible_aggtrade", None, None, None)
    r = rules("U", {A: 10000.0})
    eng, res = run(r, [sig(T0 + 60_000, A, "BTC", 10.0, legs=[leg])], end_h=1)
    statuses = [o["status"] for o in res.orders]
    assert statuses[0] == "no_eligible_aggtrade" and "filled" in statuses[1:]
    assert held(eng, A, "BTC") == pytest.approx(10.0)


def test_eref_invariant_no_scale_up():
    r = rules("U", {A: 10000.0})
    eng, _ = run(r, [sig(T0 + 60_000, A, "BTC", 10.0, e_ref=2000.0)], end_h=1)
    assert eng.sleeves[A].k == 1.0 and held(eng, A, "BTC") == pytest.approx(10.0)


def test_reduce_only_never_increases_and_a_sign_flip_closes_in_shape():
    r = rules("S", {A: 10000.0}, triggers=False)
    eng = PE.Engine(r, costs(), FakeMarket(), T0, T0 + 10 * H)
    legs = [PE.Leg("BTC", 10.0, True, True, None, "", None, None, None),
            PE.Leg("ETH", 25.0, True, True, None, "", None, None, None)]
    eng.push(T0 + 60_000, 2, "signal", sig(T0 + 60_000, A, "BTC", 10.0, legs=legs))
    eng.queue.sort()
    eng.on_signal(sig(T0 + 60_000, A, "BTC", 10.0, legs=legs))
    while eng.queue:
        t, _, _, kind, payload = PE.heapq.heappop(eng.queue)
        if kind == "ack":
            eng.on_ack(payload)
    before = {c: abs(q) for c, q in eng.sleeves[A].held.items()}
    eng.set_state(eng.sleeves[A], "REDUCE_ONLY", T0 + H, "test")
    eng.on_signal(sig(T0 + H, A, "BTC", 20.0, legs=[PE.Leg("BTC", 20.0, True, True, None, "", None, None, None)]))
    for c, q in eng.sleeves[A].held.items():
        assert abs(q + eng.sleeves[A].pending[c]) <= before.get(c, 0.0) + 1e-9
    # leader flips BTC: the common scale goes to 0 and every leg closes
    eng.on_signal(sig(T0 + 2 * H, A, "BTC", -5.0, legs=[PE.Leg("BTC", -5.0, True, True, None, "", None, None, None)]))
    assert eng.sleeves[A].ro_scale == 0.0
    targets = [d for d in eng.decisions if d["t"] == T0 + 2 * H][-1]
    assert targets["state_scalar"] == 0.0


def test_ladder_steps_down_and_releases_only_at_a_review():
    m = FakeMarket(path={"BTC": [(T0 + 2 * H, 94.5), (T0 + 4 * H, 80.0), (T0 + 30 * H, 100.0)]})
    r = rules("S", {A: 10000.0}, triggers=False, p2_major=10.0, s2_share=10.0, p4_share=10.0, p5_usdc=1e9,
              p3_x=10.0)
    review = T0 + 40 * H
    eng, res = run(r, [sig(T0 + 60_000, A, "BTC", 100.0)], m, end_h=48, reviews=[T0, review])
    ev = [(e["event"], e.get("state_to")) for e in res.events if "scheme" in e["event"]]
    assert ("scheme_firing", "HALVED") in ev and ("scheme_firing", "REDUCE_ONLY") in ev
    release = [e for e in res.events if e["event"] == "scheme_release"]
    assert release and all(e["t"] == review for e in release)  # never before the review


def test_flatten_completes_within_o1_at_stress_costs_then_pauses():
    m = FakeMarket(path={"BTC": [(T0 + 2 * H, 82.0)]}, volume=4e6)  # budget 20,000 USDC per bar
    r = rules("S", {A: 10000.0}, triggers=False, p2_major=10.0, s2_share=10.0, p4_share=10.0, p5_usdc=1e9,
              p3_x=10.0)
    eng, res = run(r, [sig(T0 + 60_000, A, "BTC", 100.0)], m, end_h=24)
    flat = [o for o in res.orders if o["flatten"]]
    assert flat and all(o["half_bps"] == 3.0 for o in flat if o["status"] == "filled")  # stress costs
    assert held(eng, A, "BTC") == pytest.approx(0.0)
    assert eng.scheme_state in ("EXITED",)


def test_passive_p4_breach_blocks_increases_without_selling():
    m = FakeMarket(path={"BTC": [(T0 + 2 * H, 100.0)]}, shock=0.10)
    r = rules("S", {A: 10000.0, B: 10000.0}, triggers=False, p4_share=0.15, p5_usdc=1e9, s2_share=10.0)
    eng = PE.Engine(r, costs(), m, T0, T0 + 6 * H)
    eng.run([sig(T0 + 60_000, A, "BTC", 100.0)])
    m._shock = 0.7  # marks-driven breach: P4 usage now above 3,000
    before = held(eng, A, "BTC")
    eng.end = T0 + 12 * H
    eng.hourly_check(T0 + 7 * H)
    assert eng.p4_passive
    assert held(eng, A, "BTC") == pytest.approx(before)  # nothing sold by marks alone


def test_c3_feed_outage_freezes_increases():
    r = rules("S", {A: 10000.0}, triggers=False, p2_major=10.0, p4_share=10.0, p5_usdc=1e9, p3_x=10.0,
              s2_share=10.0)
    gaps = {A: [(T0 + H, T0 + 5 * H)]}
    eng, res = run(r, [sig(T0 + 60_000, A, "BTC", 10.0), sig(T0 + 2 * H, A, "BTC", 30.0)], end_h=4,
                   feed_gaps=gaps)
    assert any(e["event"] == "C3_freeze_increase" for e in res.events)
    assert held(eng, A, "BTC") == pytest.approx(10.0)


def test_l5_forced_fill_flattens_then_pauses():
    r = rules("S", {A: 10000.0}, p2_major=10.0, p4_share=10.0, p5_usdc=1e9, p3_x=10.0, s2_share=10.0)
    eng, res = run(r, [sig(T0 + 60_000, A, "BTC", 10.0), sig(T0 + 2 * H, A, "BTC", 5.0, forced=True)], end_h=12)
    reasons = [(e.get("state_to"), e.get("reason")) for e in res.events if e["event"] == "state_firing"]
    assert ("FLATTEN", "L5") in reasons and ("PAUSED", "L5") in reasons
    assert held(eng, A, "BTC") == pytest.approx(0.0)


# ---------------------------------------------------------------------------------------------- shape (F6), F5
def test_shape_every_leg_is_one_scalar_times_the_twin():
    m = FakeMarket(shock=0.15)
    legs = [PE.Leg("HYPE", 1200.0, True, True, None, "", None, None, None),
            PE.Leg("BTC", 5.0, True, True, None, "", None, None, None),
            PE.Leg("XRP", 50.0, False, True, None, "", None, None, None)]
    signals = [sig(T0 + 60_000, A, "HYPE", 1200.0, legs=legs), sig(T0 + 90_000, B, "BTC", 40.0)]
    eng, res = run(rules("S", triggers=False), signals, m, end_h=6)
    assert res.faults == []
    d = [x for x in res.decisions if x["trader"] == A]
    assert any(x["lambda"] < x["s1"] for x in d)  # a limit bound, and the whole sleeve was scaled


def test_two_runs_are_identical():
    signals = [sig(T0 + 60_000 + k * 600_000, A if k % 2 else B, "BTC", float(k)) for k in range(12)]
    out = []
    for _ in range(2):
        _, res = run(rules("S", triggers=False), signals, end_h=6)
        out.append((res.orders, res.fills, res.decisions, res.hourly, res.events))
    assert out[0] == out[1]


# ---------------------------------------------------------------------------------------------- P5-2 leak test
def test_risk_model_ignores_moves_after_the_origin():
    origin = date(2025, 11, 19)
    o = RM.epoch_day(origin)
    days = list(range(o - 120, o + 10))
    marks = pl.DataFrame({
        "coin": ["BTC"] * len(days) + ["HYPE"] * len(days),
        "boundary": days * 2,
        "mark": [100.0 * (1 + 0.01 * ((d * 7) % 5 - 2)) for d in days]
        + [10.0 * (1 + 0.02 * ((d * 3) % 7 - 3)) for d in days],
    })
    bars = pl.DataFrame({"coin": ["BTC", "HYPE"], "bar_ms": [o * PE.DAY - PE.BAR] * 2,
                         "bar_volume_usdc": [1e8, 2e6]})
    sh = pl.DataFrame({"coin": ["BTC", "HYPE"], "shock_down": [0.1, 0.17], "shock_up": [0.08, 0.16],
                       "n_obs": [10, 10], "first_mark": [None, None]})
    cfg = {"beta": {"lookback_days": 90, "min_days": 10, "shrink_k": 30}}
    cov = {"covariance_lookback_days": 90, "cov_min_days": 60, "cov_min_complete_days": 30}
    edges = [250_000, 1_000_000, 5_000_000]
    a = RM.build(origin, sh, marks, bars, ["BTC", "HYPE"], cfg, cov, edges)
    planted = marks.with_columns(mark=pl.when(pl.col("boundary") > o).then(pl.col("mark") * 3).otherwise("mark"))
    later_bar = pl.concat([bars, pl.DataFrame({"coin": ["HYPE"], "bar_ms": [o * PE.DAY + PE.HOUR],
                                               "bar_volume_usdc": [1.0]})])
    b = RM.build(origin, sh, planted, later_bar, ["BTC", "HYPE"], cfg, cov, edges)
    for name in ("stress_shocks", "betas", "covariance"):
        assert a[name].equals(b[name]), name  # type: ignore[union-attr]
    assert a["covariance_info"] == b["covariance_info"]


def test_shock_function_is_point_in_time():
    import datetime as dt

    start = dt.datetime(2025, 7, 1, tzinfo=dt.UTC)
    hours = [start + dt.timedelta(hours=k) for k in range(200)]
    px = pl.DataFrame({"coin": ["BTC"] * 200, "t": hours, "price": [100.0 + (k % 10) for k in range(200)]})
    px = px.with_columns(pl.col("t").dt.cast_time_unit("ms"))
    asof = hours[150]
    a = shocks(px, asof, 24)
    planted = px.with_columns(price=pl.when(pl.col("t") > asof).then(1.0).otherwise("price"))
    b = shocks(planted, asof, 24)
    assert a.equals(b)


# ---------------------------------------------------------------------------------------------- P5-6 report
def test_d4_statistic_switches_to_own_alpha_when_m_is_constant():
    from arkstream.holdout_report import statistic_choice

    varied = pl.DataFrame({"m": [0.1, 0.2, -0.1], "alpha": [1.0, 2.0, 3.0]})
    constant = pl.DataFrame({"m": [0.0, 0.0, 0.0], "alpha": [1.0, 2.0, 3.0]})
    assert statistic_choice(varied) == ("m", -0.20)
    assert statistic_choice(constant) == ("alpha", -0.14)


def test_decision_rule_needs_every_condition_and_fails_unmeasured():
    from arkstream.holdout_report import decide

    h1 = pl.DataFrame({"clean": [True, True]})
    h2 = pl.DataFrame({"config": ["S", "S", "G2500", "G2500"], "scenario": ["base", "stress"] * 2,
                       "within_limit": [True] * 4, "cap_breaches_at_update": [None, None, 0, 0]})
    h3 = pl.DataFrame({"measured": [True], "within_p90": [True]})
    h5 = pl.DataFrame({"test": ["d4"], "group": ["alpha"], "value": [-0.10], "note": ["threshold -0.14"]})
    tables = {"h1_engine": h1, "h2_risk": h2, "h3_costs": h3, "h5_cross_section": h5}
    assert decide(tables, True, False)["decision"] == "CONDITIONAL GO"
    assert decide(tables, False, False)["decision"] == "NO-GO"  # D5: empty cutoff hand-off
    unmeasured = {**tables, "h3_costs": pl.DataFrame({"measured": [False], "within_p90": [True]})}
    assert decide(unmeasured, True, False)["D3"] is False
    bad_ic = {**tables, "h5_cross_section": h5.with_columns(value=pl.lit(-0.15))}
    assert decide(bad_ic, True, False)["D4"] is False
