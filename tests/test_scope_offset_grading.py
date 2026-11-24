"""ADR-0066: the PnL-identity residual is graded by economic size (ADR-0045 materiality), not a cent tolerance + CV."""

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from arkstream.quality import grade
from arkstream.reconcile import snapshot_summary

T0 = datetime(2025, 9, 1, tzinfo=UTC)
ASOF = T0 + timedelta(days=60)
MATERIAL = {"material_abs_usdc": 10, "material_rel_equity": 0.005, "offset_scale_floor_usdc": 500}
CFG = {
    "A": {"min_days_present_share": 0.95, "min_material_match_share": 0.99, "max_zero_equity_days_with_position": 0},
    "B": {"max_unusable_day_share": 0.20, **MATERIAL, "min_offset_match_share": 0.99, "max_offset_shift": 0.005,
          "max_offset_level": 0.10},
    "C": {"near_zero_equity_usdc": 10, "max_near_zero_equity_share": 0.5},
}


def snaps(trader: str, equity: float, residuals: list[float], start: datetime = T0) -> pl.DataFrame:
    n = len(residuals)
    return pl.DataFrame({
        "trader": [trader] * n, "src_row": list(range(n)),
        "ts": [start + timedelta(days=i) for i in range(n)],
        "equity": [equity] * n, "net_deposit": [equity] * n,
        "pnl": list(residuals),  # pnl - (equity - net_deposit) = residual
    }, schema_overrides={"ts": pl.Datetime("ms", "UTC")})


def summary(*frames: pl.DataFrame) -> pl.DataFrame:
    return snapshot_summary(pl.concat(frames), ASOF, 0.01, 1.0, MATERIAL).sort("trader")


def graded(s: pl.DataFrame) -> dict[str, tuple[str, str]]:
    base = s.with_columns(no_snapshots=pl.lit(False), no_fills=pl.lit(False), continuity_breaks=pl.lit(0),
                          near_zero_equity_share=pl.lit(0.0), unusable_day_share=pl.lit(0.0),
                          days_present_share=pl.lit(1.0), zero_equity_holding_rows=pl.lit(0))
    g = grade(base, {"grades": CFG})
    return {t: (gr, why) for t, gr, why in g.select("trader", "grade", "grade_reason").rows()}


def test_small_noisy_residual_is_grade_a_although_its_cv_explodes():
    # +-3 USDC around zero on a 10,000 USDC account: every row misses the cent tolerance, the CV is huge,
    # and no row is material (bound = max(10, 50) = 50 USDC)
    s = summary(snaps("noise", 10_000.0, [3.0, -3.0] * 30))
    r = s.row(0, named=True)
    assert r["pnl_match_share"] == 0.0 and (r["pnl_offset_cv"] is None or r["pnl_offset_cv"] > 100)
    assert r["material_match_share"] == 1.0
    assert graded(s)["noise"] == ("A", "")


def test_stable_offset_within_ten_percent_is_b():
    s = summary(snaps("stable", 10_000.0, [500.0 + (i % 3) for i in range(60)]))  # 5% of equity, MAD 1 USDC
    r = s.row(0, named=True)
    assert r["offset_level"] == pytest.approx(0.05, abs=1e-3) and r["offset_match_share"] == 1.0
    assert graded(s)["stable"] == ("B", "stable_scope_offset:use_rebuilt_book")


def test_stable_offset_larger_than_the_cap_is_c():
    # the review's example: a stable 2,000 USDC difference on a 5,000 USDC account
    s = summary(snaps("big", 5_000.0, [2_000.0] * 60))
    assert s["offset_level"][0] == pytest.approx(0.4)
    assert graded(s)["big"] == ("C", "scope_offset_too_large")


def test_drifting_or_dispersed_offset_is_unstable():
    drift = summary(snaps("drift", 10_000.0, [100.0] * 30 + [900.0] * 30))   # shift 8% of equity
    scatter = summary(snaps("scatter", 10_000.0, [100.0, 900.0] * 30))      # 400 USDC around its median
    assert graded(drift)["drift"] == ("C", "unstable_scope_mismatch")
    assert graded(scatter)["scatter"] == ("C", "unstable_scope_mismatch")


def test_thresholds_scale_with_equity_and_the_floor():
    # 300 USDC residual: material on a 10k account (bound 50), immaterial on a 100k account (bound 500)
    small, large = snaps("small", 10_000.0, [300.0] * 60), snaps("large", 100_000.0, [300.0] * 60)
    s = summary(small, large)
    by = {r["trader"]: r for r in s.iter_rows(named=True)}
    assert by["small"]["material_match_share"] == 0.0 and by["large"]["material_match_share"] == 1.0
    # equity below the 500 USDC scale floor: the level is measured against 500
    tiny = summary(snaps("tiny", 100.0, [40.0] * 60))
    assert tiny["offset_level"][0] == pytest.approx(40.0 / 500)


def test_shift_needs_four_snapshots_and_is_point_in_time():
    few = summary(snaps("few", 10_000.0, [500.0] * 3))
    assert few["offset_shift"][0] is None
    assert graded(few)["few"] == ("C", "unstable_scope_mismatch")  # an offset not shown to be stable
    # snapshots after asof never enter the statistics
    later = snaps("pit", 10_000.0, [0.0] * 40 + [5_000.0] * 40)  # days 40-79: the last 20 are after asof
    s = summary(later)
    known = later.filter(pl.col("ts") <= ASOF).height
    assert s["n_snapshots"][0] == known == 61


def test_episodic_material_breaches_are_not_a_stable_offset():
    # clean 90% of the time, a 1,000 USDC (10% of equity) breach on every tenth snapshot: the median residual and its
    # MAD are both 0, so a robust-dispersion rule would call it stable; around the median 10% of rows are material
    s = summary(snaps("episodic", 10_000.0, [1_000.0 if i % 10 == 0 else 0.0 for i in range(60)]))
    r = s.row(0, named=True)
    assert r["offset_level"] == 0.0 and r["offset_mad"] == 0.0
    assert r["offset_match_share"] == pytest.approx(0.9)
    assert graded(s)["episodic"] == ("C", "unstable_scope_mismatch")
