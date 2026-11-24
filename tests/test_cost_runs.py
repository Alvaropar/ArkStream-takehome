"""Cost runs B and C and the v2 holdout entry point (ADRs 0098-0099): the delay draw, the tape lookup, the impact fit,
the O2 bound, C's updated view, the engine hooks leaving run A unchanged, and the guards."""

from __future__ import annotations

import csv
import hashlib
import io
import shutil
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from test_phase5_engine import T0, A, B, FakeMarket, H, costs, rules, sig

from arkstream import cost_rebuild as CR
from arkstream import cost_updated as CU
from arkstream import portfolio_engine as PE
from arkstream.freeze import FreezeError

STRESS = costs("stress", "stress", 3.0, 3.0)
Q = (994.145, 1224.654, 1843.648, 3540.094)


# ---------------------------------------------------------------------------------------------- 1. delay
def test_delay_quantile_function_is_linear_and_flat_outside():
    s = CR.DelaySampler(Q, [1])
    assert s.at(0.50) == 1225 and s.at(0.10) == 994 and s.at(0.99) == 3540
    assert s.at(0.01) == 994 and s.at(0.999) == 3540  # flat below p10 and above p99
    assert s.at(0.30) == round((994.145 + 1224.654) / 2)
    a = [CR.DelaySampler(Q, CR.delay_seed(date(2025, 11, 19), "S")).draw() for _ in range(3)]
    b = [CR.DelaySampler(Q, CR.delay_seed(date(2025, 11, 19), "S")).draw() for _ in range(3)]
    assert a == b  # fixed seed
    assert CR.delay_seed(date(2025, 11, 19), "G") != CR.delay_seed(date(2025, 11, 19), "S")


def test_delay_quantiles_read_from_the_latency_file():
    path = Path("research/latency/total_delay.csv")
    if not path.is_file():
        pytest.skip("latency output not present")
    assert CR.delay_quantiles(path) == pytest.approx(Q, abs=1e-3)


# ---------------------------------------------------------------------------------------------- 2. tape
def tape_dir(tmp_path: Path, symbol: str, d: date, rows: list[tuple[int, float]]) -> Path:
    folder = tmp_path / symbol
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{symbol}-aggTrades-{d.isoformat()}.zip"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time",
                "is_buyer_maker"])
    for i, (t, p) in enumerate(rows):
        w.writerow([i, p, 1, i, i, t, "true"])
    with zipfile.ZipFile(folder / name, "w") as z:
        z.writestr(name.replace(".zip", ".csv"), buf.getvalue())
    sha = hashlib.sha256((folder / name).read_bytes()).hexdigest()
    with open(tmp_path / "MANIFEST.csv", "w", newline="", encoding="utf-8") as fh:
        m = csv.writer(fh)
        m.writerow(["symbol", "date", "file", "bytes", "sha256", "published_sha256", "source", "retrieved_on",
                    "verified_on"])
        m.writerow([symbol, d.isoformat(), f"{symbol}/{name}", (folder / name).stat().st_size, sha, sha, "test",
                    "", ""])
    return tmp_path


def test_tape_lookup_is_as_of_with_staleness(tmp_path):
    d = date(2025, 11, 20)
    t0 = int(CR.midnight(d).timestamp() * 1000)
    root = tape_dir(tmp_path, "BTCUSDT", d, [(t0 + 1000, 100.0), (t0 + 2000, 101.0)])
    tape = CR.Tape(root, {"BTC": "BTCUSDT"}, [d], CR.midnight(date(2025, 12, 3)), 1000)
    assert tape.price("BTC", t0 + 1999) == 100.0
    assert tape.price("BTC", t0 + 2000) == 101.0
    assert tape.price("BTC", t0 + 3001) is None  # more than 1 s old
    assert tape.price("BTC", t0 + 500) is None  # nothing before
    assert tape.price("ETH", t0 + 2000) is None and not tape.has("ETH")


def test_tape_refuses_a_day_at_or_after_the_stop(tmp_path):
    with pytest.raises(ValueError, match="refused"):
        CR.Tape(tmp_path, {"BTC": "BTCUSDT"}, [date(2025, 12, 3)], CR.midnight(date(2025, 12, 3)), 1000)


# ---------------------------------------------------------------------------------------------- 4. impact
def test_impact_fit_is_least_squares_through_zero_with_a_minimum_and_a_floor():
    d = date(2025, 11, 20)
    xs = [float(i + 1) for i in range(40)]
    obs = pl.DataFrame({"coin": ["BTC"] * 40 + ["ETH"] * 40 + ["SOL"] * 10, "day": [d] * 90,
                        "x": xs + xs + xs[:10], "z": [0.5 * x for x in xs] + [-x for x in xs] + xs[:10]})
    fit = CR.fit_y(obs)
    assert fit[("BTC", d)][0] == pytest.approx(0.5) and fit[("BTC", d)][1] == 40
    assert fit[("ETH", d)][0] == 0.0  # floored at zero
    assert ("SOL", d) not in fit  # fewer than 30 orders: the frozen y applies


# ---------------------------------------------------------------------------------------------- the pricer and O2
class TapeStub:
    def __init__(self, prices):
        self.p = prices  # coin -> {t: price}

    def has(self, coin):
        return coin in self.p

    def price(self, coin, t):
        return self.p.get(coin, {}).get(t)


def pricer(o2=None, spread=None, y=None, prices=None, updated=None):
    inp = CR.RebuildInputs(tape=TapeStub(prices or {}), spread_day=spread or {}, y_day=y or {},
                           o2=o2 or {">=5M": 1000.0}, quantiles=Q, receive_ms=392, debounce_ms=250, fee_bps=4.5,
                           frozen_y=1.0)
    return CR.Rebuild(inp, CR.DelaySampler(Q, [7]), costs(), STRESS, updated=updated)


class EngStub:
    def __init__(self):
        self.market = FakeMarket()

    def mark(self, coin, t):
        return self.market.mark(coin, t)


def test_rebuild_prices_drift_from_the_tape_ratio_and_falls_back_when_missing():
    t = T0 + H
    p = pricer(prices={"BTC": {}})
    p.delays = CR.DelaySampler((1000.0, 1000.0, 1000.0, 1000.0), [1])
    p.inp.tape.p["BTC"] = {t: 100.0, t + 1000 - 642: 100.5}
    rec = p.price(EngStub(), "BTC", t, 1.0, A, None, False, px_f=100.02, impact_f=1.0, half_f=1.0, ack_f=t + 558,
                  source_f="parameterised", anchor=100.0)
    assert rec["drift_flag"] == "tape" and rec["rebuilt_drift_bps"] == pytest.approx(50.0)
    assert rec["ack_ms"] == t + 358  # decision + max(draw - receive - debounce, 0)
    assert rec["half_flag"] == "frozen" and rec["rebuilt_half_bps"] == 1.0  # no same-day spread: frozen
    assert rec["impact_flag"] == "frozen" and rec["rebuilt_y"] == 1.0
    rec2 = p.price(EngStub(), "HYPE", t, 1.0, A, None, False, px_f=10.002, impact_f=1.0, half_f=1.0,
                   ack_f=t + 558, source_f="parameterised", anchor=10.0)
    assert rec2["drift_flag"] == "frozen_no_tape"
    assert rec2["rebuilt_drift_bps"] == pytest.approx(rec2["frozen_drift_bps"])


def test_rebuild_rejects_above_the_o2_bound():
    t = T0 + H
    p = pricer(o2={">=5M": 5.0}, spread={("BTC", CR.day_of(t)): 10.0})
    rec = p.price(EngStub(), "BTC", t, 1.0, A, None, False, px_f=100.02, impact_f=1.0, half_f=1.0, ack_f=t + 558,
                  source_f="parameterised", anchor=100.0)
    assert rec["half_flag"] == "day" and rec["rebuilt_half_bps"] == 10.0  # no floor
    assert rec["status"] == "rejected_o2" and rec["px"] is None and rec["fee"] == 0.0


# ---------------------------------------------------------------------------------------------- engine hooks
class IdentityPricer:
    """Returns the frozen price: the engine path with a pricer must then equal run A."""

    own: list = []

    def price(self, eng, coin, t, q, trader, sig, flatten, px, impact, half, ack, source, anchor):
        fee = abs(q) * px * (STRESS.fee_bps if flatten else 4.5) / PE.BPS
        return {"px": px, "fee": fee, "impact_bps": impact, "half_bps": half, "ack_ms": ack, "status": "filled"}

    def filled(self, rec):
        pass


class RejectPricer(IdentityPricer):
    def price(self, *a, **k):
        r = super().price(*a, **k)
        r.update(status="rejected_o2", px=None, fee=0.0)
        return r


def run_engine(**kw):
    r = rules()
    eng = PE.Engine(r, costs(), FakeMarket(), T0, T0 + 30 * H, **kw)
    res = eng.run([sig(T0 + H, A, "BTC", 50.0), sig(T0 + 2 * H, B, "HYPE", -300.0), sig(T0 + 5 * H, A, "BTC", 20.0)])
    return eng, res


def test_engine_hooks_off_and_identity_pricer_leave_run_a_unchanged():
    _, a = run_engine()
    _, b = run_engine(risk_market=None, pricer=None, shadow_market=None)
    _, c = run_engine(pricer=IdentityPricer())
    for x in (b, c):
        assert x.fills == a.fills and x.hourly == a.hourly and x.events == a.events
    assert c.orders == a.orders
    assert a.cost_records == [] and len(c.cost_records) >= sum(o["status"] == "filled" for o in a.orders) > 0


def test_rejected_order_fills_nothing_and_releases_pending():
    eng, res = run_engine(pricer=RejectPricer())
    assert not [f for f in res.fills if f["kind"] == "physical"]
    assert "rejected_o2" in {o["status"] for o in res.orders} and "filled" not in {o["status"] for o in res.orders}
    assert all(abs(q) < 1e-12 for s in eng.sleeves.values() for q in s.pending.values())


def test_risk_market_feeds_the_stress_limits_and_c1_keeps_the_frozen_model():
    class Costly(FakeMarket):
        def half_spread(self, coin, t, regime):
            return 2000.0  # a much more expensive updated model: a stress limit binds

    _, a = run_engine()
    eng, c = run_engine(risk_market=Costly(), shadow_market=Costly())
    lam_a = [h["lambda"] for h in a.hourly]
    lam_c = [h["lambda"] for h in c.hourly]
    assert sum(lam_c) < sum(lam_a)  # the stress limits bind more on the updated model
    stress_limits = ("S2", "P4", "P5")
    assert any(h["lambda_set_by"].startswith(stress_limits) for h in c.hourly)
    assert not any(h["lambda_set_by"].startswith(stress_limits) for h in a.hourly)
    # C1 compares with the frozen market: every recorded model cost is the frozen one
    for s in eng.sleeves.values():
        for (_, _, model), (_, _, shadow) in zip(s.shortfalls, s.shadow_shortfalls, strict=True):
            assert shadow > model


def test_exit_bps_reads_y_from_an_updated_view():
    class WithY(FakeMarket):
        def impact_y(self, coin, t):
            return 2.0

    base = PE.exit_bps(FakeMarket(), STRESS, "BTC", T0, A, 1000.0)
    two = PE.exit_bps(WithY(), STRESS, "BTC", T0, A, 1000.0)
    assert base is not None and two is not None
    impact = two - base
    assert impact == pytest.approx(3 * PE.BPS * 0.02 * (1000.0 / 6e9) ** 0.5)  # y 2 vs 1 at 3x


# ---------------------------------------------------------------------------------------------- C's view
def test_updated_impact_y_pools_14_days_and_own_fills_before_the_day():
    d = date(2025, 11, 20)
    rows = [("BTC", d - timedelta(days=k), 1.0, 0.4) for k in range(1, 15) for _ in range(2)]  # 28 orders
    rows += [("BTC", d - timedelta(days=20), 1.0, 10.0)] * 5  # outside the 14 days
    taker = pl.DataFrame(rows, schema={"coin": pl.String, "day": pl.Date, "x": pl.Float64, "z": pl.Float64},
                         orient="row")
    own = type("P", (), {"own": []})()
    v = CU.UpdatedMarket(FakeMarket(), None, pl.DataFrame(schema={"origin": pl.Date, "trader": pl.String,
                                                                 "band": pl.String}), {}, taker, own, 1.0)
    t = int(CR.midnight(d).timestamp() * 1000) + H
    assert v.impact_y("BTC", t) == 1.0  # 28 < 30: the frozen y
    own.own += [(d - timedelta(days=1), "BTC", 1.0, 0.4), (d - timedelta(days=1), "BTC", 1.0, 0.4),
                (d, "BTC", 1.0, 99.0)]  # today's own fill is not yet known
    v2 = CU.UpdatedMarket(FakeMarket(), None, v_bands(), {}, taker, own, 1.0)
    assert v2.impact_y("BTC", t) == pytest.approx(0.4)


def v_bands() -> pl.DataFrame:
    return pl.DataFrame(schema={"origin": pl.Date, "trader": pl.String, "band": pl.String})


def test_updated_spread_keeps_the_floor():
    d = date(2025, 11, 20)
    t = int(CR.midnight(d).timestamp() * 1000)

    class M(FakeMarket):
        costs = {"base": costs(), "stress": STRESS}

    v = CU.UpdatedMarket(M(), None, v_bands(), {("BTC", d): 0.4, ("HYPE", d): 7.0}, pl.DataFrame(),
                         type("P", (), {"own": []})(), 1.0)
    assert v.half_spread("BTC", t, "base") == 1.0  # max(floor, 0.4)
    assert v.half_spread("HYPE", t, "stress") == 7.0  # max(3, 7)
    assert v.half_spread("ETH", t, "base") == 1.0  # no estimate: the frozen view


# ---------------------------------------------------------------------------------------------- guards
def tmp_ctx(tmp_path: Path):
    from arkstream.config import load_context

    ctx = load_context()
    shutil.copytree(ctx.root / "config", tmp_path / "config")
    return type(ctx)(raw=ctx.raw, root=tmp_path)


def test_holdout_entry_point_is_refused_without_the_freeze(tmp_path):
    from arkstream import holdout

    with pytest.raises(FreezeError):
        holdout.run(tmp_ctx(tmp_path))
    assert not (tmp_path / holdout.OUT).exists()  # nothing ran before the guard


def test_runs_b_and_c_refuse_before_the_decision_entry(tmp_path):
    from arkstream import holdout

    ctx = tmp_ctx(tmp_path)
    with pytest.raises(RuntimeError, match="decision_A.json"):
        holdout.stage_bc(ctx, holdout.holdout_spec(ctx), tmp_path)


def test_leader_series_past_the_last_origin_needs_the_flag_and_the_freeze(tmp_path):
    from arkstream import leader

    ctx = tmp_ctx(tmp_path)
    with pytest.raises(ValueError, match="final configured origin"):
        leader.compute(ctx, None, datetime(2025, 12, 20, tzinfo=UTC))
    with pytest.raises(FreezeError):
        leader.compute(ctx, None, datetime(2025, 12, 20, tzinfo=UTC), beyond_last_origin=True)


def test_holdout_window_is_32_rows_from_the_3_dec_origin():
    from arkstream import holdout
    from arkstream.config import load_context

    s = holdout.holdout_spec(load_context())
    assert s.origin == date(2025, 12, 3) and (s.end - s.start).days == 32 and s.end.hour == 0
    c = holdout.check_spec(load_context())
    assert c.origin == date(2025, 11, 19) and c.end == holdout.midnight(date(2025, 12, 3))


def test_resume_is_refused_outside_check_mode(tmp_path):
    from arkstream import holdout

    with pytest.raises(ValueError, match="check mode only"):
        holdout.run(tmp_ctx(tmp_path), resume=True)
    assert not (tmp_path / holdout.OUT).exists()
