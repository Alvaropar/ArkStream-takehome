"""Phase 4 v2 (ADRs 0070-0075, pinned by ADRs 0076-0079): tradable sets and `not_tradable`, the market model,
alpha per unit of gross, DerSimonian-Laird evidence, the IC rule, co-movement and the hand-off schema."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest
from conftest import need
from test_coin_filter import two_coin_setup
from test_replay import BASE, END, RULES, START

from arkstream import selection_v2_coins as SC
from arkstream import selection_v2_comove as CM
from arkstream import selection_v2_evidence as EV
from arkstream import selection_v2_market as MK
from arkstream import selection_v2_math as M
from arkstream import selection_v2_stats as ST
from arkstream.config import ROOT, load_context
from arkstream.replay_book import MEASURED_OUTCOMES
from arkstream.replay_cap import cap_legs
from arkstream.replay_capture import CATEGORY
from arkstream.replay_orders import EXCLUDED, NOT_SUBMITTED, execute
from arkstream.replay_sensitivity import mark_tradable

C = pl.col
TRADABLE = ROOT / "research/replay_tradable"
ALLPRICED = ROOT / "research/replay_allpriced"
OUT = ROOT / "research/selection_v2"
SUFFIX = "_sqrt_cap_part_ns_sweep_frozen"


# ---------------------------------------------------------------------------------------------- distributions
def test_distribution_functions_match_tables():
    assert M.t_ppf(0.8, 3) == pytest.approx(0.9784723, abs=1e-6)
    assert M.t_ppf(0.975, 5) == pytest.approx(2.5705818, abs=1e-6)
    assert M.chi2_sf(3.841458820694124, 1) == pytest.approx(0.05, abs=1e-9)
    assert M.chi2_sf(10.0, 10) == pytest.approx(0.4404933, abs=1e-6)
    assert M.spearman(np.array([1, 2, 3, 4.0]), np.array([10, 20, 30, 40.0])) == pytest.approx(1.0)
    assert M.spearman(np.ones(5), np.arange(5.0)) is None


# ---------------------------------------------------------------------------------------------- P4-2
def test_not_tradable_is_an_excluded_measured_uncopyable_status():
    assert "not_tradable" in EXCLUDED and "not_tradable" in NOT_SUBMITTED
    assert "not_tradable" in MEASURED_OUTCOMES
    assert CATEGORY["not_tradable"] == "uncopyable_coin"


def test_cap_scale_is_solved_on_the_full_book_and_excluded_legs_are_flagged():
    marks, ev, snaps, b = two_coin_setup()
    full = cap_legs(b, ev, snaps, marks, {"A", "B"}, 10000, 15000, 250, START, END)
    pairs = pl.DataFrame({"trader": ["w"], "coin": ["B"]})
    flagged = mark_tradable(full, pairs)
    # the plan (scale, legs, order) is the all-priced one; only the flag is added
    assert flagged.drop("not_tradable").equals(full)
    sig = flagged.filter(C("signal") == 1).sort("coin")
    assert sig["cap_scale"][0] == pytest.approx(15000 / 35000) and sig["coin"].to_list() == ["A", "B"]
    assert sig["not_tradable"].to_list() == [True, False]
    # kept legs stay exactly proportional to the leader's book
    assert sig.filter(C("coin") == "B")["capped_target"][0] == pytest.approx(50.0 * 15000 / 35000)


def test_not_tradable_leg_is_never_reserved_or_filled():
    marks, ev, snaps, b = two_coin_setup()
    legs = mark_tradable(cap_legs(b, ev, snaps, marks, {"A", "B"}, 10000, 15000, 250, START, END),
                         pl.DataFrame({"trader": ["w"], "coin": ["B"]})).sort("signal")
    frame = legs.with_columns(
        equity=pl.lit(10000.0), frozen=pl.lit(False), ack_ms=C("decision_ms") + 500, ref_px=pl.lit(100.0),
        price_reason=pl.when(C("not_tradable")).then(pl.lit("not_tradable")).otherwise(pl.lit("")),
        half_bps=pl.lit(1.0), bar_volume_usdc=pl.lit(1e9), mean_bps=pl.lit(None, pl.Float64), mid_L=pl.lit(100.0),
    )
    got = execute(frame, BASE, dict(RULES, cap_usdc=15000), cap_marks=marks)
    a = got.filter(C("coin") == "A")
    assert (a["status"] == "not_tradable").all() and a["fill_px"].null_count() == a.height
    bf = got.filter((C("coin") == "B") & (C("status") == "filled"))
    assert bf.height >= 1 and bf["reserved_gross_before"][0] == pytest.approx(0.0)


def test_weighted_median_and_leave_one_wallet_out_sets():
    assert SC.weighted_median(np.array([1.0, 2.0, 30.0]), np.array([1.0, 1.0, 1.0])) == 2.0
    assert SC.weighted_median(np.array([1.0, 30.0]), np.array([1.0, 3.0])) == 30.0
    coins = pl.DataFrame({"coin": ["X", "Y"], "tradable": [True, False]})
    loo = pl.DataFrame({"coin": ["X", "Y", "X"], "trader": ["a", "b", "b"], "tradable": [True, False, True],
                        "tradable_for_wallet": [False, True, True]})
    uni = pl.DataFrame({"trader": ["a", "b", "c"]})
    got = SC.sets_from(coins, loo, uni)
    # a loses X (its own costs decided it), b gains Y, c (no orders) keeps the pooled set
    assert got.rows() == [("b", "X"), ("b", "Y"), ("c", "X")]


# ---------------------------------------------------------------------------------------------- P4-3 market
ORIGIN = date(2025, 11, 5)


def synthetic_marks(origin: date, days: int = 120, plant: bool = False, seed: int = 3) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    o = MK.epoch_day(origin)
    rows = []
    for c, vol in (("BTC", 0.02), ("ETH", 0.03), ("AAA", 0.05), ("BBB", 0.06), ("CCC", 0.04)):
        p = 100.0
        for b in range(o - days, o + 15):
            rows.append((c, b, p))
            p *= 1 + rng.normal(0, vol)
    df = pl.DataFrame(rows, schema={"coin": pl.String, "boundary": pl.Int64, "mark": pl.Float64}, orient="row")
    if plant:  # a wild post-origin day: boundaries after the origin's
        df = df.with_columns(mark=pl.when(C("boundary") > o).then(C("mark") * 7.0).otherwise(C("mark")))
    return df


def test_betas_fit_once_before_the_origin_and_ignore_a_planted_later_day():
    members = ["AAA", "BBB", "CCC"]
    out = []
    for plant in (False, True):
        r = MK.coin_returns(synthetic_marks(ORIGIN, plant=plant))
        f = MK.factor_returns(r, members)
        out.append(MK.fit_betas(r, f, ORIGIN, lookback=90))
    assert out[0].equals(out[1])
    b = out[0]
    assert (b["fit_date"] == ORIGIN).all() and int(b["last_day"].max()) == MK.epoch_day(ORIGIN) - 1
    btc = b.filter(C("coin") == "BTC").row(0, named=True)
    assert (btc["beta_BTC"], btc["beta_ETH"], btc["beta_ALT"], btc["kind"]) == (1.0, 0.0, 0.0, "identity")
    aaa = b.filter(C("coin") == "AAA").row(0, named=True)
    w = aaa["n_days"] / (aaa["n_days"] + 30)
    assert aaa["beta_ALT"] == pytest.approx(w * aaa["ols_ALT"] + (1 - w) * aaa["prior_ALT"])


def one_coin_book(qty: float, origin: date, n: int = 40):
    """A copy that buys `qty` AAA at the first day's noon and holds it; ledger in the replay's shape."""
    s = origin - timedelta(days=n)
    s_ms = MK.epoch_day(s) * 86_400_000
    f = pl.DataFrame({"trader": ["w"], "coin": ["AAA"], "ack_ms": [s_ms + 43_200_000], "quantity": [qty],
                      "fill_px": [100.0], "fee": [0.0], "batch": [1], "oid": [1]}).with_columns(
        pos=C("quantity"), cash=-C("quantity") * C("fill_px"), day=(C("ack_ms") // 86_400_000).cast(pl.Date),
        next_ms=pl.lit(MK.epoch_day(origin) * 86_400_000))
    fund = pl.DataFrame(schema={"trader": pl.String, "coin": pl.String, "batch": pl.Int64, "payment": pl.Float64,
                                "day": pl.Date})
    return f, fund, s


def test_one_coin_book_reproduces_alpha_exactly_and_is_scale_free():
    marks = synthetic_marks(ORIGIN)
    r = MK.coin_returns(marks)
    fac = MK.factor_returns(r, ["AAA", "BBB", "CCC"])
    betas = MK.fit_betas(r, fac, ORIGIN)
    res = []
    for qty in (10.0, 5.0):
        f, fund, s = one_coin_book(qty, ORIGIN)
        cd = MK.coin_days(f, fund, marks, s, ORIGIN)
        rc = MK.residual_coin_days(cd, betas, fac, r)
        td = MK.trader_days(rc, ["w"], s, ORIGIN)
        ex = td.filter("exposed")
        core = ST.alpha_core(ex["t"].to_numpy(), ex["U"].to_numpy(), ex["G"].to_numpy(), 0.8)
        res.append(core)
        if qty == 10.0:
            # by hand: the entry day (bought at 100 at noon, flat at its start) counts with G = q M(s+1) and its
            # whole PnL (ADR-0082); later days U_t = q (M(t+1) - M(t)) - q M(t) Σ β r_f, G = max(q M(t), q M(t+1))
            m = dict(((c, b), v) for c, b, v in marks.select("coin", "boundary", "mark").rows())
            b = betas.filter(C("coin") == "AAA").row(0, named=True)
            fx = {t: (x, y, z) for t, x, y, z in fac.select("t", "BTC", "ETH", "ALT").rows()}
            t0 = MK.epoch_day(s)
            su, sg = qty * (m[("AAA", t0 + 1)] - 100.0), qty * m[("AAA", t0 + 1)]
            for t in range(t0 + 1, MK.epoch_day(ORIGIN)):
                e = qty * m[("AAA", t)]
                pnl = qty * (m[("AAA", t + 1)] - m[("AAA", t)])
                su += pnl - e * (b["beta_BTC"] * fx[t][0] + b["beta_ETH"] * fx[t][1] + b["beta_ALT"] * fx[t][2])
                sg += max(e, qty * m[("AAA", t + 1)])
            assert ex.height == MK.epoch_day(ORIGIN) - t0
            assert core["alpha"] == pytest.approx(su / sg, rel=1e-12)
    assert res[0]["alpha"] == pytest.approx(res[1]["alpha"], rel=1e-12)
    assert res[0]["s"] == pytest.approx(res[1]["s"], rel=1e-12)


def test_dust_residual_is_not_exposure():
    """ADR-0080: a residual below the 10 USDC minimum order neither counts for measurability nor carries the PnL of a
    trade opened on its day."""
    days = list(range(20000, 20040))
    rc = pl.DataFrame({"trader": ["w"] * 40, "coin": ["LINK"] * 40, "t": days, "e": [-0.002] * 40,
                       "H": [-0.002] * 40, "funding": [0.0] * 40,
                       "pnl": [0.0] * 39 + [-50.0], "U": [0.0] * 39 + [-50.0], "bad": [False] * 40,
                       "beta_BTC": [0.0] * 40, "beta_ETH": [0.0] * 40, "beta_ALT": [1.0] * 40})
    start, end = date(1970, 1, 1) + timedelta(days=20000), date(1970, 1, 1) + timedelta(days=20040)
    td = MK.trader_days(rc, ["w"], start, end, min_exposure=10.0)
    assert not td["exposed"].any() and td["valid"].all()
    st = ST.per_trader(td, rc, 0.8, 10000.0, 20, 4).row(0, named=True)
    assert st["measured"] is False and st["exposed_days"] == 0 and st["alpha"] is None
    assert st["pnl_flat_days"] == pytest.approx(-50.0)
    # without the materiality rule the same record would be "measured" on 40 dust days
    assert MK.trader_days(rc, ["w"], start, end)["exposed"].all()


def gross_case(e: list[float], h: list[float], pnl: list[float], funding: list[float] | None = None):
    n = len(e)
    days = list(range(20000, 20000 + n))
    return pl.DataFrame({"trader": ["w"] * n, "coin": ["BTC"] * n, "t": days, "e": e, "H": h,
                         "funding": funding or [0.0] * n, "pnl": pnl, "U": pnl, "bad": [False] * n,
                         "beta_BTC": [1.0] * n, "beta_ETH": [0.0] * n, "beta_ALT": [0.0] * n})


def test_entry_day_from_flat_is_exposed_with_its_costs():
    """ADR-0082: G = max(start, end gross); a day that opens from flat counts, with its entry costs."""
    rc = gross_case([0.0, 1000.0, 1000.0, 5.0], [1000.0, 1000.0, 5.0, 5.0], [-3.0, 4.0, -2.0, 0.0])
    start = date(1970, 1, 1) + timedelta(days=20000)
    td = MK.trader_days(rc, ["w"], start, start + timedelta(days=4), min_exposure=10.0).sort("t")
    assert td["G"].to_list() == [1000.0, 1000.0, 1000.0, 5.0]
    assert td["exposed"].to_list() == [True, True, True, False]  # the last day is dust at both ends
    st = ST.per_trader(td, rc, 0.8, 10000.0, 1, 1).row(0, named=True)
    assert st["sum_U"] == pytest.approx(-1.0) and st["sum_G"] == pytest.approx(3000.0)  # entry cost -3 included


def test_alpha_excluding_funding_and_carry_label():
    """ADR-0083: α ex funding = Σ (U - F) / Σ G; a carry book has a positive α at least half funding."""
    rc = gross_case([1000.0] * 4, [1000.0] * 4, [0.3, 0.2, 0.3, 0.2], funding=[0.25] * 4)
    start = date(1970, 1, 1) + timedelta(days=20000)
    td = MK.trader_days(rc, ["w"], start, start + timedelta(days=4), min_exposure=10.0)
    st = ST.per_trader(td, rc, 0.8, 10000.0, 1, 1).row(0, named=True)
    assert st["alpha"] == pytest.approx(1.0 / 4000) and st["alpha_funding"] == pytest.approx(1.0 / 4000)
    assert st["alpha_ex_funding"] == pytest.approx(0.0, abs=1e-15) and st["carry_book"] is True
    assert st["alpha_incl_funding"] == pytest.approx(st["alpha"])


def test_funding_out_of_alpha():
    """ADR-0084: with funding_in_alpha off, the residual and α exclude funding; α incl. funding and the carry label
    (measured on the total) stay reported."""
    days = list(range(20000, 20004))
    cd = pl.DataFrame({"trader": ["w"] * 4, "coin": ["BTC"] * 4, "t": days, "e": [1000.0] * 4, "H": [1000.0] * 4,
                       "cash": [0.0] * 4, "funding": [0.25] * 4, "fills": [0] * 4, "unknown_funding": [0] * 4,
                       "bad": [False] * 4, "pnl": [0.3, 0.2, 0.3, 0.2]})
    fac = pl.DataFrame({"t": days, "BTC": [0.0] * 4, "ETH": [0.0] * 4, "ALT": [0.0] * 4})
    ret = pl.DataFrame({"coin": ["BTC"] * 4, "t": days, "r": [0.0] * 4})
    betas = pl.DataFrame({"coin": ["BTC"], "beta_BTC": [1.0], "beta_ETH": [0.0], "beta_ALT": [0.0],
                          "prior_BTC": [1.0], "prior_ETH": [0.0], "prior_ALT": [0.0]})
    incl = MK.residual_coin_days(cd, betas, fac, ret, funding_in_alpha=True)
    excl = MK.residual_coin_days(cd, betas, fac, ret, funding_in_alpha=False)
    assert incl["U"].to_list() == pytest.approx([0.3, 0.2, 0.3, 0.2])
    assert excl["U"].to_list() == pytest.approx([0.05, -0.05, 0.05, -0.05])
    start = date(1970, 1, 1) + timedelta(days=20000)
    td = MK.trader_days(excl, ["w"], start, start + timedelta(days=4), min_exposure=10.0)
    st = ST.per_trader(td, excl, 0.8, 10000.0, 1, 1, funding_in_alpha=False).row(0, named=True)
    assert st["alpha"] == pytest.approx(0.0, abs=1e-15) == st["alpha_ex_funding"]
    assert st["alpha_incl_funding"] == pytest.approx(1.0 / 4000) and st["alpha_funding"] == pytest.approx(1.0 / 4000)
    assert st["carry_book"] is True


def test_clustered_standard_error_formula():
    t = np.arange(14) + 4  # two Monday-based weeks
    U = np.linspace(-1, 2, 14)
    G = np.full(14, 10.0)
    core = ST.alpha_core(t, U, G, 0.8)
    a = U.sum() / G.sum()
    wk = MK.week_index(t)
    s = np.array([(U - a * G)[wk == w].sum() for w in np.unique(wk)])
    se = np.sqrt(2 / 1 * (s ** 2).sum()) / G.sum()
    assert core["weeks"] == 2 and core["se_cluster"] == pytest.approx(se)
    assert core["s"] == pytest.approx(se * M.t_ppf(0.8, 1) / M.norm_ppf(0.8))


# ---------------------------------------------------------------------------------------------- P4-4 / P4-5
def test_equal_true_alpha_gives_tau2_about_zero_and_no_e2():
    rng = np.random.default_rng(20251203)
    s = rng.uniform(0.5, 5.0, 300)
    a = 0.3 + rng.normal(0, s)
    dl = EV.dersimonian_laird(a, s, 0.20)
    assert dl["tau2"] < 0.05 * float(np.mean(s ** 2))
    cats = []
    for ai, si in zip(a, s, strict=True):
        _, m, v, p = EV.posterior(float(ai), float(si), dl["tau2"], dl["mu0"])
        cats.append(EV.category(True, float(ai), p, bool(dl["robust_zero"]), True))
    assert "E2" not in cats


def test_dispersed_alpha_gives_positive_tau2():
    rng = np.random.default_rng(7)
    true = rng.normal(0, 1.0, 200)
    s = np.full(200, 0.1)
    dl = EV.dersimonian_laird(true + rng.normal(0, s), s, 0.20)
    assert dl["tau2"] == pytest.approx(1.0, rel=0.3) and dl["robust_zero"] is False
    assert dl["mu0"] <= 0


def test_degenerate_posterior_and_one_week_record():
    w, m, v, p = EV.posterior(5.0, 1.0, 0.0, -0.2)
    assert (w, m, v, p) == (0.0, -0.2, 0.0, 0.0)
    t = np.arange(4, 11)  # one calendar week
    rob = EV.robustness(t, np.ones(7), np.ones(7), 0.8, [], np.zeros(0))
    assert rob["robust"] is False and rob["alpha_ex_best_week"] is None


def test_robustness_removes_the_best_week_from_both_sums():
    t = np.arange(4, 25)  # three weeks
    U = np.r_[np.full(7, -0.1), np.full(7, 5.0), np.full(7, 0.2)]
    G = np.r_[np.full(7, 1.0), np.full(7, 10.0), np.full(7, 1.0)]
    rob = EV.robustness(t, U, G, 0.8, [], np.zeros(0))
    assert rob["alpha_ex_best_week"] == pytest.approx((7 * -0.1 + 7 * 0.2) / 14.0)
    assert rob["robust"] is True


def test_bootstrap_draw_is_seeded_and_shared():
    a = EV.block_counts(84, 7, 50, np.random.default_rng([20251203, 1, 7]))
    b = EV.block_counts(84, 7, 50, np.random.default_rng([20251203, 1, 7]))
    assert np.array_equal(a, b) and (a.sum(axis=1) == 84).all()


def test_placebo_constant_exposure_is_shift_invariant():
    marks = synthetic_marks(ORIGIN)
    r = MK.coin_returns(marks)
    fac = MK.factor_returns(r, ["AAA", "BBB", "CCC"])
    market = ST.Market(ORIGIN, ["AAA", "BBB", "CCC"], r, fac, MK.fit_betas(r, fac, ORIGIN))
    start = ORIGIN - timedelta(days=28)
    days = list(range(MK.epoch_day(start), MK.epoch_day(ORIGIN)))
    rc = pl.DataFrame({"trader": ["0xabcdef12"] * 28, "coin": ["AAA"] * 28, "t": days, "e": [1000.0] * 28})
    rc = rc.join(r.rename({"coin": "c2"}).filter(C("c2") == "AAA").select("t", "r"), on="t").join(
        fac.select("t", "BTC", "ETH", "ALT"), on="t")
    b = market.betas.filter(C("coin") == "AAA").row(0, named=True)
    rc = rc.with_columns(U=C("e") * (C("r") - b["beta_BTC"] * C("BTC") - b["beta_ETH"] * C("ETH")
                                      - b["beta_ALT"] * C("ALT")) - 1.0)
    resid = rc.select("trader", "t", "U", G=C("e"), exposed=pl.lit(True))
    p = EV.placebo(rc, resid, market, start, ORIGIN, ["0xabcdef12"], 20251203, ORIGIN)
    q = EV.placebo(rc, resid, market, start, ORIGIN, ["0xabcdef12"], 20251203, ORIGIN)
    row = p.row(0, named=True)
    assert p.equals(q) and row["missing_coin_days"] == 0
    # every day holds the same position, so a circular shift leaves the holding part and α unchanged
    assert row["placebo_median"] == pytest.approx(row["alpha"], rel=1e-9)
    assert row["alpha_other_part"] == pytest.approx(-28.0 / 28_000.0)


def test_undefined_ic_counts_as_zero_and_not_positive():
    cur = pl.DataFrame({"trader": list("abcdef"), "m": [0.0] * 6, "alpha": np.arange(6.0),
                        "info_ratio": np.arange(6.0), "t_stat": np.arange(6.0), "nav_key": np.arange(6.0),
                        "trip_key": np.arange(6.0)})
    nxt = pl.DataFrame({"trader": list("abcdef"), "alpha": np.arange(6.0)})
    per = {date(2025, 10, 8) + timedelta(days=14 * i): (cur, nxt) for i in range(4)}
    t, d = EV.ranking_validation(per, {"hit_quantile": 0.2, "min_mean_ic": 0.05, "min_positive_origins": 3})
    assert d["mean_ic_m"] == 0.0 and d["positive_origins_m"] == 0 and d["ordering_used"] is False
    assert t.filter(C("key") == "alpha")["ic"].to_list() == [1.0] * 4


# ---------------------------------------------------------------------------------------------- P4-6
def test_ledoit_wolf_is_a_valid_shrunk_covariance():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.03, (60, 5)) + rng.normal(0, 0.02, (60, 1))
    sig, delta = CM.ledoit_wolf_cc(x)
    y = x - x.mean(axis=0)
    s = y.T @ y / 60
    assert 0 <= delta <= 1 and np.allclose(np.diag(sig), np.diag(s)) and np.allclose(sig, sig.T)
    assert np.linalg.eigvalsh(sig).min() > 0


def test_covariance_has_one_fit_date_before_the_origin():
    out = []
    for plant in (False, True):
        r = MK.coin_returns(synthetic_marks(ORIGIN, plant=plant))
        out.append(CM.risk_cov(r, ["AAA", "BBB", "CCC"], ORIGIN, 90, 60, 30))
    assert out[0][0] == out[1][0] and np.array_equal(out[0][1], out[1][1])
    assert out[0][2]["fit_date"] == ORIGIN and out[0][2]["last_day"] == MK.epoch_day(ORIGIN) - 1


def pair_inputs(n_days: int, crash_spike: bool):
    start = date(2025, 9, 29)
    days = [start + timedelta(days=i) for i in range(n_days)]
    rng = np.random.default_rng(5)
    ra, rb = rng.normal(0, 0.01, n_days), rng.normal(0, 0.01, n_days)
    if crash_spike:
        for d in (date(2025, 10, 10), date(2025, 10, 11)):
            if d in days:
                i = days.index(d)
                ra[i], rb[i] = -0.3, -0.3
    daily = pl.DataFrame({"trader": ["a"] * n_days + ["b"] * n_days, "day": days * 2,
                          "daily_twr": np.r_[ra, rb]})
    resid = daily.select("trader", t=C("day").cast(pl.Int64), G=pl.lit(1000.0), valid=pl.lit(True),
                         exposed=pl.lit(True))
    rc = resid.select("trader", "t", coin=pl.lit("BTC"), e=pl.lit(1000.0))
    fac = pl.DataFrame({"t": [MK.epoch_day(d) for d in days], "ALT": rng.normal(0, 0.02, n_days)})
    prof = pl.DataFrame({"trader": ["a", "b"]}).with_columns(
        exposure_by_coin=pl.lit([{"coin": "BTC", "mean_exposure_usdc": 1000.0}]))
    return start, start + timedelta(days=n_days), daily, resid, rc, fac, prof


RULES_DUP = {"min_overlap": 0.7, "min_corr_lower95": 0.5, "min_common_exposed_days": 20, "downside_share": 0.2,
             "min_downside_days": 10, "large_loss_quantile": 0.1}


def test_crash_days_are_excluded_from_the_duplicate_correlation():
    start, end, daily, resid, rc, fac, prof = pair_inputs(40, crash_spike=True)
    crash = [date(2025, 10, 10), date(2025, 10, 11)]
    p = CM.pair_table(["a", "b"], resid, daily, rc, fac, start, end, crash, ["BTC"], np.array([[1e-4]]), prof,
                      RULES_DUP).row(0, named=True)
    assert p["corr_both"] > 0.8  # driven by the two crash days
    assert abs(p["corr_both_ex_crash"]) < 0.5 and p["both_ex_crash_days"] == 38
    assert p["overlap"] == pytest.approx(1.0) and p["risk_corr"] == pytest.approx(1.0)
    assert p["near_duplicate"] is False


def test_unmeasured_pair_gets_no_credit():
    start, end, daily, resid, rc, fac, prof = pair_inputs(12, crash_spike=False)
    p = CM.pair_table(["a", "b"], resid, daily, rc, fac, start, end, [], ["BTC"], None, prof,
                      RULES_DUP).row(0, named=True)
    assert p["measured"] is False and p["corr_for_phase5"] == 1.0 and p["risk_corr_for_phase5"] == 1.0
    cands = pl.DataFrame({"trader": ["a", "b"], "category": ["E1", "E2"], "m": [0.1, 0.0]})
    pairs = pl.DataFrame({"trader_a": ["a"], "trader_b": ["b"], "near_duplicate": [True]})
    d = CM.duplicate_screen(cands, pairs)
    assert dict(d.select("trader", "duplicate_decision").rows()) == {"b": "kept", "a": "near_duplicate"}


# ---------------------------------------------------------------------------------------------- data tests
def orders(tree, origin, window, scenario):
    base = tree / f"origin={origin}" / f"window={window}"
    d = base / ("benchmark=unattainable_frozen" if scenario == "benchmark" else f"scenario={scenario}{SUFFIX}")
    return pl.read_parquet(d / "follower_orders.parquet",
                           columns=["trader", "coin", "status", "signal", "cap_scale", "resize_leg"])


@pytest.mark.data
def test_published_tradable_replay_never_trades_outside_the_wallet_sets():
    need(TRADABLE / "origin=2025-11-19", "uv run python -m arkstream replay --tradable")
    pairs = pl.read_parquet(TRADABLE / "tradable_pairs.parquet")
    o = date(2025, 11, 19)
    ok = pairs.filter(C("origin") == o).select("trader", "coin")
    for window in ("training", "test"):
        for sc in ("base", "stress", "benchmark"):
            x = orders(TRADABLE, o, window, sc)
            bad = x.filter(C("status") == "filled").join(ok, on=["trader", "coin"], how="anti")
            assert bad.height == 0, (window, sc, bad.head())
            assert x.filter(C("status") == "not_tradable").join(ok, on=["trader", "coin"], how="semi").height == 0
            assert (x["status"] == "not_tradable").sum() > 0


@pytest.mark.data
def test_tradable_cap_scale_equals_the_all_priced_scale():
    need(TRADABLE / "origin=2025-11-19", "uv run python -m arkstream replay --tradable")
    need(ALLPRICED / "origin=2025-11-19", "uv run python -m arkstream replay --allpriced")
    a = orders(TRADABLE, date(2025, 11, 19), "test", "base").select("trader", "signal", "coin", "cap_scale")
    b = orders(ALLPRICED, date(2025, 11, 19), "test", "base").select("trader", "signal", "coin", "cap_scale")
    j = a.join(b, on=["trader", "signal", "coin"], suffix="_all")
    assert j.height > 0.9 * min(a.height, b.height)
    assert j.filter(~((C("cap_scale") == C("cap_scale_all")) | (C("cap_scale").is_null()
                                                               & C("cap_scale_all").is_null()))).height == 0


@pytest.mark.data
def test_leave_one_wallet_out_sets_are_reproducible():
    need(ALLPRICED / "origin=2025-12-03", "uv run python -m arkstream replay --allpriced")
    need(OUT / "origin=2025-12-03/coins.parquet", "uv run python -m arkstream select-v2")
    ctx = load_context()
    o = date(2025, 12, 3)
    coins, loo = SC.coin_table(ctx, o, ALLPRICED)
    assert coins.equals(pl.read_parquet(OUT / f"origin={o}/coins.parquet"))
    assert loo.equals(pl.read_parquet(OUT / f"origin={o}/coins_loo.parquet"))
    uni = pl.read_parquet(ALLPRICED / f"origin={o}/window=training/universe.parquet", columns=["trader"])
    stored = pl.read_parquet(TRADABLE / "tradable_pairs.parquet").filter(C("origin") == o).select("trader", "coin")
    assert SC.sets_from(coins, loo, uni).equals(stored)


@pytest.mark.data
def test_handoff_schema_is_fixed():
    from arkstream.selection_v2 import HANDOFF_COLUMNS

    need(OUT / "origin=2025-12-03/eligible.parquet", "uv run python -m arkstream select-v2")
    for p in sorted(OUT.glob("origin=*/eligible.parquet")):
        e = pl.read_parquet(p)
        assert e.columns == HANDOFF_COLUMNS
        assert e["category"].is_in(["E1", "E2"]).all() and e["trader"].n_unique() == e.height
