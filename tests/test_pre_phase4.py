"""Pre-Phase 4 fixes on synthetic data: return-source materiality (ADR-0045), forced fills (ADR-0046), the
not-copyable exposure (ADR-0047), the alt drift bound (ADR-0048), unmeasured stress (ADR-0049, narrowed by ADR-0055)
and the frozen reference equity with reviews and reduce-only (ADR-A0116, ADR-0052)."""

from datetime import timedelta

import polars as pl
import pytest
from conftest import make_fills, need, ts
from test_replay import BASE, RULES, START, T, parameters
from test_sensitivity_limits import _events

from arkstream import drift, leader_assets
from arkstream.leader import not_copyable_exposure
from arkstream.replay_book import MEASURED_OUTCOMES, PRICING_FAILURES, summaries
from arkstream.replay_cap import MinuteMarks, cap_legs, reference_equity, review_times
from arkstream.replay_market import DAY, ms
from arkstream.replay_orders import Parameters, batches, execute, sweep_anchor
from arkstream.replay_sizing import leader_equity

C = pl.col
RULE = {"breach_abs_usdc": 10, "breach_rel_equity": 0.005, "book_min_breach_share": 0.05, "book_min_breach_run": 3}
ASOF = ts("2025-11-01 00:00:00")


# ------------------------------------------------------------------------------------ ADR-0045 materiality
def _snapshots(diffs: list[float], equity: float = 1000.0, trader: str = "a") -> pl.DataFrame:
    """Daily snapshots whose PnL identity residual pnl - (equity - net_deposit) is the given value."""
    n = len(diffs)
    t0 = ASOF - timedelta(days=n)
    return pl.DataFrame({
        "trader": [trader] * n,
        "ts": [t0 + timedelta(days=i) for i in range(n)],
        "src_row": [10_000 + i for i in range(n)] if trader == "a" else [20_000 + i for i in range(n)],
        "equity": [equity] * n,
        "net_deposit": [500.0] * n,
        "pnl": [equity - 500.0 + d for d in diffs],
    }, schema_overrides={"ts": pl.Datetime("ms", "UTC")})


def _source(diffs, equity=1000.0):
    _, per = leader_assets.identity_breaches(_snapshots(diffs, equity), ASOF, RULE)
    return per.with_columns(source=leader_assets.material_source(RULE)).row(0, named=True)


def test_small_and_isolated_breaches_keep_the_snapshot_series():
    tiny = [0.0] * 95 + [0.02] * 5  # ADR-0028 would have switched on any of these
    assert _source(tiny)["source"] == leader_assets.SNAPSHOT and _source(tiny)["pnl_breaches"] == 0
    one = [0.0] * 50 + [50.0] + [0.0] * 49
    r = _source(one)
    assert (r["pnl_breaches"], r["pnl_breach_max_run"], r["source"]) == (1, 1, leader_assets.SNAPSHOT)


def test_share_and_run_triggers_choose_the_book():
    run3 = [0.0] * 50 + [50.0] * 3 + [0.0] * 47
    assert _source(run3)["pnl_breach_max_run"] == 3 and _source(run3)["source"] == leader_assets.BOOK
    spread = ([0.0] * 19 + [50.0]) * 5  # 5 of 100, never two in a row
    r = _source(spread)
    assert r["pnl_breach_share"] == pytest.approx(0.05) and r["pnl_breach_max_run"] == 1
    assert r["source"] == leader_assets.BOOK
    four = ([0.0] * 24 + [50.0]) * 4  # 4 of 100
    assert _source(four)["source"] == leader_assets.SNAPSHOT


def test_breach_bound_is_the_larger_of_10_usdc_and_half_a_percent():
    assert _source([0.0] * 9 + [4_000.0], equity=1e6)["pnl_breaches"] == 0  # 0.4% of equity
    assert _source([0.0] * 9 + [6_000.0], equity=1e6)["pnl_breaches"] == 1  # 0.6% of equity
    assert _source([0.0] * 9 + [9.0], equity=100.0)["pnl_breaches"] == 0  # under the 10 USDC floor


def test_breaches_after_asof_are_not_known_and_intervals_are_excluded():
    snaps = _snapshots([0.0] * 10)
    later = snaps.tail(3).with_columns(ts=C("ts") + pl.duration(days=30), src_row=C("src_row") + 100,
                                       pnl=C("pnl") + 50.0)
    flags, per = leader_assets.identity_breaches(pl.concat([snaps, later]), ASOF, RULE)
    assert per["pnl_breaches"][0] == 0 and flags.height == 10  # the later breaches are invisible at ASOF
    flags, _ = leader_assets.identity_breaches(_snapshots([0.0] * 5 + [50.0] + [0.0] * 4), ASOF, RULE)
    acc = pl.DataFrame({"trader": ["a"] * 9, "src_row": list(range(10_001, 10_010)),
                        "prev_src_row": list(range(10_000, 10_009)), "usable": [True] * 8 + [False],
                        "exclude_reason": [""] * 8 + ["opening_equity_below_min"]})
    out = leader_assets.exclude_breaches(acc, flags.filter("breach")["src_row"], pl.Series(["a"]))
    hit = out.filter(C("exclude_reason") == "pnl_identity_breach")
    assert hit["src_row"].to_list() == [10_005, 10_006]  # the interval into and out of the breaching snapshot
    assert out["exclude_reason"][-1] == "opening_equity_below_min"  # an earlier reason is kept
    untouched = leader_assets.exclude_breaches(acc, flags.filter("breach")["src_row"], pl.Series(["b"]))
    assert untouched["usable"].sum() == 8  # book-primary addresses keep their snapshot check unchanged


# ------------------------------------------------------------------------------------ ADR-0046 forced fills
def test_forced_fills_leave_the_drift_sample_but_stay_in_the_replay():
    rows = [{"ts": "2025-10-10 21:00:00", "trader": "a", "symbol": "ETH", "side": "sell", "size": 1.0,
             "start_position": 2.0, "dir": d, "oid": 70 + i} for i, d in
            enumerate(["Close Long", "Auto-Deleveraging", "Liquidated Cross Long", "Settlement"])]
    f = make_fills(rows)
    orders = drift.leader_orders(f, ts("2025-10-10 00:00:00"), ts("2025-10-11 00:00:00"))
    assert orders["oid"].to_list() == [70]
    ev = _events([("w", "A", i, 7 + i, T + 1000 * (i + 1), i, 11 + i, 100.0, "sell", False, 1.0 - i / 4, 1.0)
                  for i in range(2)]).with_columns(dir=pl.Series(["Close Long", "Auto-Deleveraging"]))
    b = batches(ev, 250, 250, START, START + timedelta(days=1))
    assert b["forced"].to_list() == [False, True]  # both are still copied as position changes
    frame = b.with_columns(leader_vwap=pl.lit(99.0), leader_deepest=pl.lit(98.0))
    base = sweep_anchor(frame, "base")
    assert base["anchor_rule"].to_list() == ["vwap", "first_fill"]
    assert base["anchor_px"].to_list() == [99.0, 100.0]


# ------------------------------------------------------------------------------------ ADR-0047 exposure
def test_not_copyable_exposure_shares():
    legs = [("BTC", 6.0), ("XPL", 3.0), ("xyz:TSLA", 1.0), ("@107", 50.0)]  # spot @107: in neither share
    f = make_fills([{"ts": f"2025-10-01 00:00:0{i}", "trader": "a", "symbol": sym, "side": "buy", "size": size,
                     "start_position": 0.0} for i, (sym, size) in enumerate(legs)])
    r = not_copyable_exposure(f, ["BTC"]).row(0, named=True)
    assert r["perp_notional_to_origin"] == pytest.approx(1000.0)
    assert (r["share_not_passing"], r["share_hip3"], r["share_not_copyable"]) == pytest.approx((0.3, 0.1, 0.4))


# ------------------------------------------------------------------------------------ ADR-0048 alt drift
def _cells(proxy, own_dev, own_stress=None):
    cells = [(START.date(), "development", c, "all", 10_000, proxy, 30) for c in ("BTC", "ETH", "HYPE", "SOL")]
    cells += [(START.date(), "stress", c, "all", 10_000, proxy, 30) for c in ("BTC", "ETH", "HYPE", "SOL")]
    if own_dev is not None:
        cells.append((START.date(), "development", "ALT", "all", 300_000, own_dev, 30))
    if own_stress is not None:
        cells.append((START.date(), "stress", "ALT", "all", 300_000, own_stress, 30))
    return Parameters(pl.DataFrame(cells, orient="row",
                                   schema=["origin", "period", "coin", "band", "horizon_ms", "mean_bps", "measured"]))


@pytest.mark.parametrize(("proxy", "own", "expected"), [(1.0, 4.0, 4.0), (3.0, -5.0, 3.0), (-2.0, -1.0, 0.0)])
def test_base_drift_below_300s_is_bounded_from_below(proxy, own, expected):
    p = _cells(proxy, own, own_stress=7.0)
    value, method, used, reason = p.lookup(START.date(), "development", "ALT", "all", 10_000, conservative=True)
    assert value == expected and method == "base_max_proxy_coin_300s_zero" and reason == ""
    assert "ALT" in used
    assert p.lookup(START.date(), "development", "ALT", "all", 10_000)[0] == proxy  # optimistic keeps the proxy
    assert p.lookup(START.date(), "stress", "ALT", "all", 10_000)[0] == max(proxy, 7.0)  # stress unchanged
    assert p.lookup(START.date(), "development", "ALT", "all", 300_000, conservative=True)[0] == own  # 300 s: own


def test_base_bound_needs_the_coin_estimate():
    value, _, _, reason = _cells(1.0, None).lookup(START.date(), "development", "ALT", "all", 10_000, conservative=True)
    assert value is None and reason == "no_drift_cell"
    assert parameters().lookup(START.date(), "development", "ALT", "all", 10_000, conservative=True)[0] == 4.0


# ------------------------------------------------------------------------------------ ADR-0049 stress coverage
def _summary_inputs(statuses):
    n = len(statuses)
    orders = pl.DataFrame({"trader": ["a"] * n, "status": statuses, "intended_notional": [100.0] * n,
                           "price_source": ["parameterised"] * n, "quantity": [1.0] * n, "fill_px": [100.0] * n})
    daily = pl.DataFrame({"trader": ["a"], "day": [START.date()], "equity": [10_100.0], "pre_equity": [10_100.0],
                          "daily_twr": [0.01], "daily_twr_before_funding": [0.01], "turnover": [100.0],
                          "fees": [0.0], "execution_cost": [0.0], "funding": [0.0], "unknown_funding": [0],
                          "gross": [100.0], "leverage": [0.01]})
    uni = pl.DataFrame({"trader": ["a"], "leader_return": [0.02]})
    return daily, orders, uni


def test_stress_result_below_80pct_priced_is_unmeasured():
    daily, orders, uni = _summary_inputs(["filled"] * 7 + ["stress_sample_unavailable"] * 3)
    low = summaries(daily, orders, uni, 10_000, 0.80).row(0, named=True)
    assert low["measurement"] == "unmeasured_low_coverage" and low["priced_share"] == pytest.approx(0.7)
    assert low["copy_return"] is None and low["copy_efficiency"] is None and low["max_drawdown"] is None
    ok = summaries(daily, orders, uni, 10_000).row(0, named=True)  # base: no floor
    assert ok["measurement"] == "measured" and ok["copy_return"] == pytest.approx(0.01)
    daily, orders, uni = _summary_inputs(["filled"] * 8 + ["no_drift_cell"] * 2)
    assert summaries(daily, orders, uni, 10_000, 0.80)["copy_return"][0] == pytest.approx(0.01)
    flat = summaries(daily, orders.clear(), uni, 10_000, 0.80).row(0, named=True)
    assert flat["measurement"] == "measured" and flat["priced_share"] == 1.0  # no intents: a flat book is measured
    assert ok["parameterised_notional_share"] == pytest.approx(1.0)


# ------------------------------------------------------------------------------------ ADR-0055 pricing failures
@pytest.mark.parametrize("status", [*PRICING_FAILURES, *MEASURED_OUTCOMES])
def test_only_pricing_failures_are_unpriced(status):
    daily, orders, uni = _summary_inputs(["filled"] * 4 + [status])
    r = summaries(daily, orders, uni, 10_000, 0.80).row(0, named=True)
    assert r["unpriced"] == (status in PRICING_FAILURES)
    assert r["priced_share"] == pytest.approx(0.8 if status in PRICING_FAILURES else 1.0)
    assert r["measurement"] == "measured"  # 0.8 is not below the floor


def test_policy_outcomes_count_as_measured_and_the_broad_measure_is_kept():
    statuses = ["filled"] * 5 + ["cap_headroom"] * 2 + ["failed_price_check", "reduce_only", "no_eligible_aggtrade"]
    daily, orders, uni = _summary_inputs(statuses)
    r = summaries(daily, orders, uni, 10_000, 0.80).row(0, named=True)
    assert r["unpriced"] == 1 and r["priced_share"] == pytest.approx(0.9) and r["measurement"] == "measured"
    assert r["unpriced_broad"] == 4 and r["priced_share_broad"] == pytest.approx(0.6)  # ADR-0049: would be unmeasured
    assert r["cap_headroom"] == 2 and r["copy_return"] == pytest.approx(0.01)
    daily, orders, uni = _summary_inputs(["filled"] * 7 + ["missing_participation_volume"] * 3)
    assert summaries(daily, orders, uni, 10_000, 0.80)["measurement"][0] == "unmeasured_low_coverage"


def test_an_unclassified_status_stops_the_summary():
    daily, orders, uni = _summary_inputs(["filled", "something_new"])
    with pytest.raises(ValueError, match="unclassified"):
        summaries(daily, orders, uni, 10_000, 0.80)


def _stress_rows():
    # trader, origin, narrow share, broad share, return, drawdown (both null when unmeasured under ADR-0055)
    rows = [("t1", "A", 1.0, 0.9, 0.02, -0.03), ("t2", "A", 0.9, 0.7, -0.05, -0.12),
            ("t3", "A", 0.5, 0.4, None, None), ("t4", "B", 0.6, 0.5, None, None)]
    return pl.DataFrame(rows, schema=["trader", "origin", "priced_share", "priced_share_broad", "copy_return",
                                      "max_drawdown"], orient="row").with_columns(
        measurement=pl.when(C("priced_share") >= 0.8).then(pl.lit("measured"))
        .otherwise(pl.lit("unmeasured_low_coverage")),
        exhausted=pl.lit(False), orders=pl.lit(10), unpriced=pl.lit(1), unpriced_broad=pl.lit(3),
        cap_headroom=pl.lit(2))


def test_unmeasured_stress_fails_the_check_and_takes_the_worst_measured_return():
    from arkstream.replay_frozen import coverage_table

    t = coverage_table(_stress_rows(), 0.80, -0.10)
    narrow = {r["origin"]: r for r in t.filter(C("measure") == "pricing_failures_adr0122").iter_rows(named=True)}
    broad = {r["origin"]: r for r in t.filter(C("measure") == "broad_adr0115").iter_rows(named=True)}
    n, b = narrow["all_tests"], broad["all_tests"]
    assert (n["gate_passers"], n["measured"], n["unmeasured"], n["positive"]) == (4, 2, 2, 1)
    assert (n["stress_check_pass"], n["stress_check_fail_loss"], n["stress_check_fail_unmeasured"]) == (1, 1, 2)
    assert n["stress_check_pass"] + n["stress_check_fail_loss"] + n["stress_check_fail_unmeasured"] == 4  # none dropped
    assert n["mean_return"] == pytest.approx(-0.015)
    assert narrow["A"]["worst_measured_return"] == pytest.approx(-0.05)
    assert (n["imputed"], n["not_imputable"]) == (1, 1)  # origin B has no measured window
    assert n["mean_return_worst_imputed"] == pytest.approx((0.02 - 0.05 - 0.05) / 3)
    assert narrow["B"]["worst_measured_return"] is None and narrow["B"]["mean_return_worst_imputed"] is None
    # ADR-0049 side by side: only t1 is measured; t2's return exists but is not counted under the broad measure.
    assert (b["measured"], b["positive"], b["stress_check_pass"], b["stress_check_fail_unmeasured"]) == (1, 1, 1, 3)
    assert b["mean_return"] == pytest.approx(0.02) and broad["A"]["worst_measured_return"] == pytest.approx(0.02)
    assert (b["imputed"], b["positive_worst_imputed"]) == (2, 3)


def test_coverage_table_rejects_a_measurement_flag_that_disagrees():
    from arkstream.replay_frozen import coverage_table

    rows = _stress_rows().with_columns(measurement=pl.lit("measured"))
    with pytest.raises(ValueError, match="disagrees"):
        coverage_table(rows, 0.80, -0.10)


# ------------------------------------------------------------------------------------ ADR-A0116 frozen E_ref
WINDOW_END = START + timedelta(days=30)


def _equity(rows):
    return pl.DataFrame(rows, schema=["trader", "eq_ms", "equity", "frozen", "equity_row"], orient="row")


def test_review_schedule_and_reference_table():
    assert review_times(START, WINDOW_END, 14) == [T, T + 14 * DAY, T + 28 * DAY]
    snaps = _equity([("w", T - 1000, 20_000.0, False, 1), ("w", T + DAY, 40_000.0, False, 2),
                     ("w", T + 13 * DAY, 30_000.0, True, 3), ("w", T + 20 * DAY, 25_000.0, False, 4)])
    ref = reference_equity(snaps, ["w", "x"], START, WINDOW_END, 14)
    w = ref.filter(C("trader") == "w")
    assert w["eq_ms"].to_list() == [T, T + 14 * DAY, T + 28 * DAY]
    assert w["review_status"].to_list() == ["ok", "frozen", "ok"]
    assert w["equity"].to_list() == [20_000.0, 20_000.0, 25_000.0]  # unusable review keeps the last usable E_ref
    assert w["review_reduce_only"].to_list() == [False, True, False]
    assert w["equity_row"].to_list() == [1, 1, 4] and w["review_row"].to_list() == [1, 3, 4]
    x = ref.filter(C("trader") == "x")
    assert x["review_status"].to_list() == ["missing"] * 3 and x["equity"].null_count() == 3
    assert w["review_kind"].to_list() == ["schedule"] * 3  # a usable start review needs no extra review


def test_first_review_at_the_first_usable_snapshot():
    """ADR-0052: no usable equity at the window start -> first review at the first usable snapshot in the window,
    then the 14-day schedule from the window start as before."""
    snaps = _equity([("y", T + 3 * DAY, 8_000.0, False, 7), ("y", T + 20 * DAY, 9_000.0, False, 8),
                     ("z", T - DAY, 5_000.0, True, 9), ("z", T + 2 * DAY, 0.0, False, 10),
                     ("z", T + 5 * DAY, 6_000.0, False, 11)])
    ref = reference_equity(snaps, ["y", "z"], START, WINDOW_END, 14)
    y = ref.filter(C("trader") == "y")
    assert y["eq_ms"].to_list() == [T, T + 3 * DAY, T + 14 * DAY, T + 28 * DAY]
    assert y["review_kind"].to_list() == ["schedule", "first_usable_snapshot", "schedule", "schedule"]
    assert y["equity"].to_list() == [None, 8_000.0, 8_000.0, 9_000.0]
    z = ref.filter(C("trader") == "z")  # frozen at the start, then a zero equity: the first usable one is day 5
    assert z["eq_ms"].to_list() == [T, T + 5 * DAY, T + 14 * DAY, T + 28 * DAY]
    assert z["review_status"].to_list() == ["frozen", "ok", "ok", "ok"] and z["equity"][1] == 6_000.0


def _targets(snaps, frozen_ref: bool):
    marks = MinuteMarks(T, ms(WINDOW_END), ["A"])
    marks.values["A"][:] = 100.0
    ev = _events([("w", "A", 1, 1, T + 1000, 1, 11, 100.0, "buy", False, 50.0, 50.0),
                  ("w", "A", 2, 2, T + 2 * DAY, 2, 12, 100.0, "buy", False, 60.0, 10.0)])
    b = batches(ev, 250, 250, START, WINDOW_END)
    sizing = reference_equity(snaps, ["w"], START, WINDOW_END, 14) if frozen_ref else snaps
    return cap_legs(b, ev, sizing, marks, {"A"}, 10_000, 15_000, 250, START, WINDOW_END, no_scale_up=True)


def test_leader_equity_between_reviews_cannot_change_the_target():
    """The plan's invariant: with positions and prices fixed, the leader's equity alone cannot move exposure."""
    deposit = _equity([("w", T - 1000, 20_000.0, False, 1), ("w", T + DAY, 40_000.0, False, 2)])
    loss = _equity([("w", T - 1000, 20_000.0, False, 1), ("w", T + DAY, 12_000.0, False, 2)])
    frozen_a, frozen_b = _targets(deposit, True), _targets(loss, True)
    assert frozen_a["uncapped_target"].to_list() == frozen_b["uncapped_target"].to_list() == [25.0, 30.0]
    assert frozen_a["copy_multiplier"].to_list() == [0.5, 0.5]
    dyn_a, dyn_b = _targets(deposit, False), _targets(loss, False)
    assert dyn_a["uncapped_target"][1] == pytest.approx(15.0) and dyn_b["uncapped_target"][1] == pytest.approx(50.0)
    small = _equity([("w", T - 1000, 4_000.0, False, 1)])
    assert _targets(small, True)["copy_multiplier"].to_list() == [1.0, 1.0]  # no scale-up above the leader


def _leg(signal, decision, target, reduce_only):
    return {"trader": "w", "coin": "A", "decision_ms": decision, "ack_ms": decision + 500, "equity": 20_000.0,
            "pos_after": target, "anchor_px": 100.0, "ref_px": 100.0, "price_reason": "", "half_bps": 1.0,
            "bar_volume_usdc": 1e9, "frozen": False, "capped_target": target, "decision_mark": 100.0,
            "resize_leg": False, "mean_bps": None, "mid_L": 100.0, "reduce_only": reduce_only, "signal": signal,
            "batch": signal, "oid": signal}


def test_reduce_only_orders_never_add_or_flip_risk():
    marks = MinuteMarks(T, T + 3_600_000, ["A"])
    marks.values["A"][:] = 100.0
    legs = [_leg(0, T + 1000, 10.0, False), _leg(1, T + 3000, 15.0, True), _leg(2, T + 5000, 4.0, True),
            _leg(3, T + 7000, -5.0, True)]
    frame = pl.DataFrame(legs, schema_overrides={"mean_bps": pl.Float64})
    got = execute(frame, BASE, dict(RULES, cap_usdc=15_000), cap_marks=marks).sort("decision_ms")
    assert got["status"].to_list() == ["filled", "reduce_only", "filled", "filled"]
    assert got["quantity"].to_list() == pytest.approx([10.0, 0.0, -6.0, -4.0])  # the last stops at flat
    assert got.filter(C("status") == "reduce_only")["fill_px"].null_count() == 1


def test_leader_equity_path_uses_only_snapshots_in_the_window():
    snaps = pl.DataFrame({
        "trader": ["w"] * 4, "src_row": [1, 2, 3, 4], "equity": [20_000.0, 30_000.0, 15_000.0, 1e9],
        "net_deposit": [0.0, 10_000.0, 10_000.0, 0.0],
        "ts": [START - timedelta(hours=1), START + timedelta(days=1), START + timedelta(days=2),
               WINDOW_END + timedelta(hours=1)],
    }, schema_overrides={"ts": pl.Datetime("ms", "UTC")})
    r = leader_equity(snaps, START, WINDOW_END).row(0, named=True)
    assert (r["equity_start"], r["equity_end"], r["net_flows"]) == (20_000.0, 15_000.0, 10_000.0)
    assert r["largest_flow_share"] == pytest.approx(0.5) and r["equity_change"] == pytest.approx(-0.25)


def _audit_ledgers(ctx, root, suffixes, scenarios=("optimistic", "base", "stress")):
    """Reviews precede decisions, the multiplier never exceeds one, nothing is acknowledged at or after the window
    end, reduce-only legs never add risk, and daily cash reconciles with the fills."""
    from arkstream.replay import windows
    from arkstream.replay_market import midnight

    rules = drift.DriftRules.from_config(ctx.raw)
    dates = rules.origin_dates
    assert not (root / f"origin={dates[-1]}" / "window=test").exists()  # the holdout is never computed
    origins = [midnight(d) for d in dates]
    for origin, window, _, end in windows(origins, midnight(rules.est_start), origins[-1]):
        for scenario in scenarios:
            for suffix in suffixes:
                folder = root / f"origin={origin.date()}" / f"window={window}" / f"scenario={scenario}{suffix}"
                o = pl.scan_parquet(folder / "follower_orders.parquet")
                filled = C("status") == "filled"
                bad = (
                    (C("ack_ms") >= ms(end)) | (C("eq_ms") > C("decision_ms")) | (C("copy_multiplier") > 1 + 1e-12)
                    | (C("decision_ms") >= C("ack_ms")) | (filled & (C("quantity").abs() * C("fill_px") < 10))
                )
                assert not o.select(bad.any()).collect().item(), (origin, window, scenario, suffix)
                if suffix.endswith("frozen"):
                    # A filled reduce-only order moves the follower position toward zero.
                    f = (o.filter(filled).sort("trader", "coin", "ack_ms", "decision_ms", "batch", "oid")
                         .with_columns(after=C("quantity").cum_sum().over("trader", "coin"))
                         .with_columns(before=C("after") - C("quantity"))
                         .filter(C("reduce_only")))
                    grows = (C("after").abs() > C("before").abs() + 1e-9) | (C("after") * C("before") < -1e-12)
                    assert not f.select(grows.any()).collect().item(), (origin, window, scenario)
                cash = o.filter(filled).group_by("trader").agg(net=(-C("quantity") * C("fill_px") - C("fee")).sum())
                daily = pl.scan_parquet(folder / "daily_copy_twr.parquet").group_by("trader").agg(book=C("cash").sum())
                gap = (C("book") - C("net").fill_null(0)).abs() > 1e-6
                assert daily.join(cash, on="trader", how="left").filter(gap).collect().is_empty(), (origin, window)


@pytest.mark.data
def test_published_sizing_ledgers(ctx):
    """ADR-A0116 archived comparison (not rerun after ADR-0052): both variants pass the ledger audit."""
    root = ctx.root / "research/replay_sizing"
    need(root / "origin=2025-10-08" / "window=test" / "scenario=base_sqrt_cap_part_ns_sweep_frozen"
         / "follower_orders.parquet", "the archived `replay --sizing` output")
    _audit_ledgers(ctx, root, ("_sqrt_cap_part_ns_sweep", "_sqrt_cap_part_ns_sweep_frozen"))


@pytest.mark.data
def test_published_frozen_replay(ctx):
    """ADR-0052/0055 output audit: frozen only (no dynamically sized scenario anywhere), prepared universes, the
    ledger audit, and a stress coverage table that keeps every gate-passing window."""
    root = ctx.root / "research/replay_frozen"
    need(root / "origin=2025-10-08" / "window=test" / "scenario=stress_sqrt_cap_part_ns_sweep_frozen"
         / "follower_orders.parquet", "run `python -m arkstream replay --frozen`")  # the CSVs ship, ledgers do not
    scenarios = {p.name for p in root.glob("origin=*/window=*/scenario=*")}
    names = ("optimistic", "base", "stress", "severe")  # ADR-0058: severe = the old 60 s / 300 s at stress costs
    assert scenarios == {f"scenario={s}_sqrt_cap_part_ns_sweep_frozen" for s in names}
    assert len(list(root.glob("origin=*/window=*/universe.parquet"))) == 9
    _audit_ledgers(ctx, root, ("_sqrt_cap_part_ns_sweep_frozen",), names)
    cov = pl.read_csv(root / "stress_coverage.csv")
    assert set(cov["measure"]) == {"broad_adr0115", "pricing_failures_adr0122"}
    assert set(cov["scenario"]) == {"stress", "severe"}
    checks = C("stress_check_pass") + C("stress_check_fail_loss") + C("stress_check_fail_unmeasured")
    assert cov.filter(checks != C("gate_passers")).is_empty()
    assert cov.filter(C("unmeasured") != C("stress_check_fail_unmeasured")).is_empty()
    assert set(pl.read_csv(root / "cost_surface.csv")["policy"]) == {"frozen"}


# ------------------------------------------------------------------------------------ ADR-0050 cost surface
def test_surface_points_and_corner_rule():
    from arkstream.replay_surface import CENTRE, corners, one_at_a_time

    names = [n for n, _ in one_at_a_time()]
    assert names == ["centre", "y=0.5", "y=2.0", "participation=0.0025", "participation=0.01", "participation=none",
                     "cap_x=1.0", "cap_x=2.0"]
    assert all(sum(p[k] != CENTRE[k] for k in CENTRE) <= 1 for _, p in one_at_a_time())  # one at a time
    means = {"centre": 0.0, "y=0.5": 0.01, "y=2.0": -0.02, "participation=0.0025": 0.0, "participation=0.01": -0.01,
             "participation=none": 0.005, "cap_x=1.0": 0.0, "cap_x=2.0": 0.0}
    pooled = pl.DataFrame([{"policy": pol, "origin": "all_tests", "point": k, "mean_return": v}
                           for pol in ("dynamic", "frozen") for k, v in means.items()])
    best, worst = corners(pooled)["dynamic"]
    assert best == ("most_favourable", {"y": 0.5, "participation": None, "cap_x": 1.5})  # cap tie goes to the centre
    assert worst == ("least_favourable", {"y": 2.0, "participation": 0.01, "cap_x": 1.5})


# ------------------------------------------------------------------------------------ ADR-0053 stress fallback
def _fallback_cells(stress_vintage=True, own_stress=None, own_dev=2.0, bucket=None, proxy=1.0, dev_proxy=0.5):
    v = START.date()
    rows = [(v, "development", c, "all", 60_000, dev_proxy, 30) for c in ("BTC", "ETH", "HYPE", "SOL")]
    if stress_vintage:
        rows += [(v, "stress", c, "all", 60_000, proxy, 30) for c in ("BTC", "ETH", "HYPE", "SOL")]
    if own_stress is not None:
        rows.append((v, "stress", "ALT", "all", 300_000, own_stress, 30))
    if own_dev is not None:
        rows.append((v, "development", "ALT", "all", 300_000, own_dev, 30))
    if bucket is not None:
        rows.append((v, "stress", "bucket:<250k", "all", 300_000, bucket, 40))
    return Parameters(pl.DataFrame(rows, orient="row",
                                   schema=["origin", "period", "coin", "band", "horizon_ms", "mean_bps", "measured"]))


def test_stress_fallback_branches():
    v = START.date()
    has = _fallback_cells(own_stress=7.0, bucket=9.0)
    assert has.lookup(v, "stress", "ALT", "all", 60_000, bucket="<250k")[0] == 7.0  # own cell present: no fallback
    b = _fallback_cells(bucket=9.0)
    value, method, used, _ = b.lookup(v, "stress", "ALT", "all", 60_000, bucket="<250k")
    assert value == 9.0 and "own=max_bucket_3x_dev" in method and "bucket:<250k" in used  # max(9, 3 x 2)
    assert b.lookup(v, "stress", "ALT", "all", 60_000, bucket="1M-5M")[0] == 6.0  # other bucket: no cell -> 3 x 2
    neg = _fallback_cells(own_dev=-1.0)
    assert neg.lookup(v, "stress", "ALT", "all", 60_000, bucket="<250k")[0] == 1.0  # max(proxy 1, 3 x max(-1, 0) = 0)
    thin = _fallback_cells(bucket=9.0)
    value, method, _, _ = thin.lookup(v, "stress", "ALT", "all", 300_000, bucket="<250k")
    assert value == 9.0 and method == "coin_fallback_max_bucket_3x_dev"
    none = _fallback_cells(own_dev=None)
    assert none.lookup(v, "stress", "ALT", "all", 60_000, bucket="<250k")[3] == "no_drift_cell"  # nothing to use
    fav = _fallback_cells(own_dev=None, bucket=-160.0, proxy=-5.0)
    assert fav.lookup(v, "stress", "ALT", "all", 60_000, bucket="<250k")[0] == 0.0  # a fallback is never favourable


def test_stress_fallback_before_any_crash_sample():
    early = _fallback_cells(stress_vintage=False, own_dev=2.0, dev_proxy=0.5)
    value, method, _, reason = early.lookup(START.date(), "stress", "ALT", "all", 60_000, bucket="<250k")
    assert value == 6.0 and reason == ""  # max(3 x 0.5, 3 x 2)
    assert "proxy=3x_dev" in method and "own=max_bucket_3x_dev" in method
    assert early.lookup(START.date(), "development", "ALT", "all", 60_000)[0] == 0.5  # optimistic unchanged


def test_liquidity_buckets_and_pooling():
    from arkstream.replay_market import liquidity_bucket, pool_buckets

    vols = pl.DataFrame({"v": [249_999.0, 250_000.0, 999_999.0, 1e6, 5e6, None]})
    got = vols.select(b=liquidity_bucket(C("v"), (250_000, 1_000_000, 5_000_000)))["b"].to_list()
    assert got == ["<250k", "250k-1M", "250k-1M", "1M-5M", ">=5M", "unknown"]
    t0 = ts("2025-10-10 12:00:00")
    obs = pl.DataFrame({
        "trader": ["a"] * 70, "coin": ["X"] * 40 + ["Y"] * 30, "t": [t0] * 70,
        "drift_bps": [10.0] * 40 + [40.0] * 30, "bar_volume_usdc": [100_000.0] * 70,
    }, schema_overrides={"t": pl.Datetime("ms", "UTC")})
    cells = pool_buckets(obs, {START.date(): {"X", "Y"}}, (250_000, 1_000_000, 5_000_000), 30)
    pooled = 10.0 * 4 / 7 + 40.0 * 3 / 7  # 40 orders at 10 bps and 30 at 40 bps
    assert cells.drop("mean_bps").rows() == [(START.date(), "stress", "bucket", "bucket:<250k", "all", 300_000, 70)]
    assert cells["mean_bps"][0] == pytest.approx(pooled)
    only_x = pool_buckets(obs, {START.date(): {"X"}}, (250_000, 1_000_000, 5_000_000), 30)
    assert only_x["mean_bps"].to_list() == [10.0]  # coins not passing at the vintage are left out
    assert pool_buckets(obs, {START.date(): {"Y"}}, (250_000, 1_000_000, 5_000_000), 31).is_empty()  # under 31
    before = pool_buckets(obs, {t0.date(): {"X", "Y"}}, (250_000, 1_000_000, 5_000_000), 30)
    assert before.is_empty()  # observations ending after the vintage are not known there
