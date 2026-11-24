"""ADR-0069: gate 7 v2 (rank agreement, steady-gap rate, Theil-Sen slope, tracking) on synthetic intervals."""

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest

from arkstream import leader_book as lb
from arkstream.config import load_context

T0 = datetime(2025, 8, 1, 22, tzinfo=UTC)
RULES = load_context().raw["leader"]


def frame(book: np.ndarray, account: np.ndarray, days: list[float] | None = None) -> pl.DataFrame:
    n = len(book)
    days = days or [1.0] * n
    ends = list(np.cumsum(days))
    ts = [T0 + timedelta(days=float(e)) for e in ends]
    prev = [T0] + ts[:-1]
    return pl.DataFrame({"trader": ["w"] * n, "prev_ts": prev, "ts": ts, "src_row": list(range(100, 100 + n)),
                         "book_r": book, "r_start": account},
                        schema_overrides={"prev_ts": pl.Datetime("ms", "UTC"), "ts": pl.Datetime("ms", "UTC")})


def stats(f: pl.DataFrame) -> dict:
    return lb.agreement_v2(f, RULES).row(0, named=True)


def test_rank_agreement_survives_outliers_that_break_pearson():
    rng = np.random.default_rng(3)
    book = rng.normal(0, 0.01, 100)
    acct = book + rng.normal(0, 0.001, 100)
    acct[[10, 40, 70]] = [0.4, -0.35, 0.3]                      # three large venue-dislocation intervals
    f = frame(book, acct)
    pearson = lb.agreement_regression(f, 0.80).row(0, named=True)
    assert pearson["xc_corr_lower"] < 0.5                        # the old gate fails it
    s = stats(f)
    assert s["xc_spearman_lower"] > 0.5                          # 7a passes
    assert set(s["xc_top_residual_rows"].split(";")) == {"110", "140", "170"}


@pytest.mark.parametrize("n", [30, 120])
def test_steady_gap_fails_7b_at_any_length(n):
    rng = np.random.default_rng(n)
    book = rng.normal(0, 0.01, n)
    s = stats(frame(book, book + 0.0020 + rng.normal(0, 0.005, n)))   # +20 bps/day, 0.5% daily noise
    assert s["xc_gap_rate_lower_bps"] > RULES["book"]["max_gap_bps_per_day"]


@pytest.mark.parametrize("n", [30, 120])
def test_zero_mean_residual_passes_7b(n):
    rng = np.random.default_rng(100 + n)
    book = rng.normal(0, 0.01, n)
    s = stats(frame(book, book + rng.normal(0, 0.005, n)))
    assert s["xc_gap_rate_lower_bps"] <= RULES["book"]["max_gap_bps_per_day"]


def test_gap_rate_weights_multi_day_intervals_by_days():
    book = np.zeros(20)
    acct = np.array([0.003] * 10 + [0.0] * 10)              # 30 bps in each of ten 3-day intervals, then nothing
    days = [3.0] * 10 + [1.0] * 10
    s = stats(frame(book, acct, days))
    assert s["xc_gap_rate_bps"] == pytest.approx(10 * 30 / (30 + 10))   # 300 bps over 40 days = 7.5 bps/day


def test_hidden_half_hedge_fails_7c():
    rng = np.random.default_rng(9)
    book = rng.normal(0, 0.01, 80)
    s = stats(frame(book, 0.5 * book + rng.normal(0, 0.0005, 80)))   # half the book's moves offset elsewhere
    assert s["xc_ts_slope"] == pytest.approx(0.5, abs=0.02)
    lo, hi = RULES["book"]["slope_band"]
    assert not lo <= s["xc_ts_slope"] <= hi


def test_clean_book_passes_every_check_and_tiny_samples_are_unmeasured():
    """A faithful book passes 7a-7c; with too few intervals the statistics are not computed (unmeasured)."""
    rng = np.random.default_rng(5)
    book = rng.normal(0, 0.01, 60)
    good = stats(frame(book, book + rng.normal(0, 0.0005, 60)))
    lo, hi = RULES["book"]["slope_band"]
    assert good["xc_spearman_lower"] >= 0.5 and lo <= good["xc_ts_slope"] <= hi
    assert good["xc_gap_rate_lower_bps"] <= RULES["book"]["max_gap_bps_per_day"]
    few = stats(frame(book[:3], book[:3]))
    assert few["xc_spearman"] is None and few["xc_ts_slope"] is None
