"""ADR-0067: uncertainty-aware data-integrity statistics and the positive-profit concentration (synthetic data)."""

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from arkstream import leader_book as lb
from arkstream import leader_trips as lt
from arkstream.selection_stats import clopper_pearson

T0 = datetime(2025, 9, 1, tzinfo=UTC)


def _fit_rows(misses: list[float]) -> pl.DataFrame:
    n = len(misses)
    return pl.DataFrame({"trader": ["w"] * n, "ts": [T0 + timedelta(days=i) for i in range(n)],
                         "src_row": list(range(n)), "miss": misses})


def test_fit_lower_bound_needs_enough_intervals():
    # a perfect fit on 10 intervals is not enough at the one-sided 80% bound (0.2 ** (1/10) = 0.851 < 0.90) ...
    ten = lb.fit_uncertainty(_fit_rows([0.0] * 10), 0.80).row(0, named=True)
    assert ten["within_1pct_lower"] == pytest.approx(0.2 ** (1 / 10), abs=1e-6) and ten["within_1pct_lower"] < 0.9
    # ... 16 perfect intervals are (0.2 ** (1/16) = 0.904)
    assert lb.fit_uncertainty(_fit_rows([0.0] * 16), 0.80)["within_1pct_lower"][0] >= 0.9
    # the bound equals the shared exact interval
    misses = [0.0] * 27 + [0.05] * 3
    got = lb.fit_uncertainty(_fit_rows(misses), 0.80)["within_1pct_lower"][0]
    assert got == pytest.approx(clopper_pearson(27, 30, alpha=0.2, two_sided=False)[0])


def test_fit_persistence_run_and_autocorrelation():
    clustered = lb.fit_uncertainty(_fit_rows([0.0] * 10 + [0.05] * 4 + [0.0] * 10), 0.80).row(0, named=True)
    spread = lb.fit_uncertainty(_fit_rows(([0.0] * 5 + [0.05]) * 4), 0.80).row(0, named=True)
    assert clustered["fit_max_miss_run"] == 4 and spread["fit_max_miss_run"] == 1
    assert clustered["fit_miss_autocorr"] > 0.5 > spread["fit_miss_autocorr"]


def test_agreement_regression_slope_intercept_nrmse_and_lower_bound():
    rng = np.random.default_rng(7)
    book = rng.normal(0, 0.02, 60)
    rows = pl.DataFrame({"trader": ["w"] * 60, "ts": [T0 + timedelta(days=i) for i in range(60)],
                         "src_row": list(range(60)), "book_r": book, "r_start": 0.001 + 1.0 * book})
    r = lb.agreement_regression(rows, 0.80).row(0, named=True)
    assert r["xc_slope"] == pytest.approx(1.0) and r["xc_intercept"] == pytest.approx(0.001)
    assert r["xc_corr_lower"] == pytest.approx(1.0, abs=1e-6)
    assert r["xc_nrmse"] == pytest.approx(0.001 / book.std(), rel=1e-6)
    noisy = rows.with_columns(r_start=pl.Series(book + rng.normal(0, 0.08, 60)))  # true corr about 0.24
    q = lb.agreement_regression(noisy, 0.80).row(0, named=True)
    assert q["xc_slope_lo"] < q["xc_slope"] < q["xc_slope_hi"] and q["xc_corr_lower"] < 0.5


def test_top_profit_share_uses_positive_profit_and_week_stats():
    # 100 trips: one +500 winner, 49 x +10, 50 x -20: net PnL -10 (old share unmeasured), positive profit 990
    pnl = [500.0] + [10.0] * 49 + [-20.0] * 50
    rt = pl.DataFrame({"trader": ["w"] * 100, "symbol": ["BTC"] * 100, "trip_no": list(range(100)),
                       "status": ["closed"] * 100, "usable": [True] * 100, "left_censored": [False] * 100,
                       "exclude_reason": [None] * 100, "ret": [p / 1000 for p in pnl], "ret_per_day": [0.0] * 100,
                       "net_pnl": pnl, "mae": [0.0] * 100, "best_gain": [0.0] * 100,
                       "open_ts": [T0 + timedelta(days=i // 10 * 7) for i in range(100)]},
                      schema_overrides={"exclude_reason": pl.String})
    s = lt.trip_summary(rt, {"trips": {"top_share": 0.01}}).row(0, named=True)
    assert s["top_pnl_share"] is None                      # old definition: net PnL not positive
    assert s["top_profit_share"] == pytest.approx(500 / 990)
    assert s["trip_weeks"] == 10 and s["ret_ci95_halfwidth"] > 0
    assert s["pnl_ex_best_week"] == pytest.approx(-10 - (500 + 9 * 10))
