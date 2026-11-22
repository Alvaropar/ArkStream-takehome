"""ADR-0110: the price check as of each origin, with a seeded look-ahead leak that must be caught."""

from datetime import timedelta

import polars as pl
import pytest
from conftest import ts
from test_replay import example

from arkstream import hlprices
from arkstream.hlprices import PointInTimeCheck, price_check, price_check_asof

C = pl.col
RULE = {"min_bars": 30, "max_median_abs_bps": 10, "max_p95_abs_bps": 30}
ORIGIN = ts("2025-10-22 00:00:00")


def _bars(coin: str, gaps: list[float], first, step=timedelta(hours=4)) -> pl.DataFrame:
    times = [first + i * step for i in range(len(gaps))]
    return pl.DataFrame({"ts": times, "coin": [coin] * len(gaps), "gap_bps": gaps, "stress": [False] * len(gaps)},
                        schema_overrides={"ts": pl.Datetime("us", "UTC")})


def _known(n_before: int, gap_before: float, n_after: int, gap_after: float) -> pl.DataFrame:
    """n_before bars closing by the origin, then n_after bars closing after it."""
    before = _bars("X", [gap_before] * n_before, ORIGIN - n_before * timedelta(hours=4) + timedelta(hours=4))
    after = _bars("X", [gap_after] * n_after, ORIGIN + timedelta(hours=4))
    return pl.concat([before, after])


def test_only_bars_closing_by_the_origin_count():
    bars = _known(40, 5.0, 40, 80.0)
    assert bars.filter(C("ts") <= ORIGIN).height == 40  # the bar closing exactly at the origin is known
    at_origin = price_check_asof(bars, ["X"], set(), ORIGIN, RULE)
    assert at_origin.row(0, named=True)["outcome"] == "pass" and at_origin["n"][0] == 40
    later = price_check_asof(bars, ["X"], set(), ORIGIN + timedelta(days=30), RULE)
    assert later["outcome"][0] == "fail"  # the same coin fails once the later bars are known


def test_minimum_sample_stress_bars_and_no_binance():
    bars = _known(29, 1.0, 0, 0.0)
    assert price_check_asof(bars, ["X"], set(), ORIGIN, RULE)["outcome"][0] == "insufficient"
    bars = _known(30, 1.0, 0, 0.0)
    assert price_check_asof(bars, ["X"], set(), ORIGIN, RULE)["outcome"][0] == "pass"
    crash = bars.with_columns(gap_bps=pl.lit(500.0), stress=pl.lit(True))  # 10-11 Oct closes: reported apart
    both = price_check_asof(pl.concat([bars, crash]), ["X"], set(), ORIGIN, RULE).row(0, named=True)
    assert both["outcome"] == "pass" and both["stress_n"] == 30
    assert price_check_asof(bars, ["X", "Y"], {"Y"}, ORIGIN, RULE)["outcome"].to_list() == ["pass", "no_binance"]
    assert price_check_asof(bars, ["X", "Z"], set(), ORIGIN, RULE)["outcome"].to_list() == ["pass", "insufficient"]


def _violations(check, bars: pl.DataFrame, asof) -> bool:
    """The point-in-time invariance check: the outcome at asof must not change when later bars are replaced by
    adversarial ones or removed."""
    truncated = bars.filter(C("ts") <= asof)
    poisoned = pl.concat([truncated, _bars("X", [9999.0] * 60, asof + timedelta(hours=4))])
    return not check(truncated, asof).equals(check(poisoned, asof))


def test_seeded_leak_a_bar_after_the_origin_is_caught():
    bars = _known(40, 5.0, 40, 80.0)

    def correct(b, asof):
        return price_check_asof(b, ["X"], set(), asof, RULE)

    def leaky(b, asof):  # the bug fixed here: every bar to the CUTOFF, whatever the origin
        return price_check(b, ["X"], set(), RULE["min_bars"], RULE["max_median_abs_bps"], RULE["max_p95_abs_bps"])

    assert leaky(bars, ORIGIN)["outcome"][0] != correct(bars, ORIGIN)["outcome"][0]  # the leak changes the result
    assert not _violations(correct, bars, ORIGIN)
    assert _violations(leaky, bars, ORIGIN)  # ... and the invariance check catches it


def test_point_in_time_check_object_and_replay_reason():
    bars = pl.concat([_known(40, 5.0, 40, 80.0), _bars("Y", [1.0] * 10, ORIGIN - timedelta(days=1))])
    checker = PointInTimeCheck(bars.with_columns(), ["X", "Y"], set(), RULE)
    assert checker.passing(ORIGIN) == ["X"]
    assert checker.checks(ORIGIN).rows() == [("X", "pass"), ("Y", "insufficient")]
    assert checker.passing(ORIGIN + timedelta(days=30)) == []
    later = ORIGIN + timedelta(days=30)
    by = checker.by_origin([ORIGIN, later])
    assert by.select("origin", "coin", "outcome").rows()[-2:] == [(later.date(), "X", "fail"),
                                                                   (later.date(), "Y", "insufficient")]
    assert example("ALT", outcome="insufficient")["status"][0] == "insufficient_price_check"


@pytest.mark.data
def test_bars_reproduce_the_cutoff_record_and_the_origin_file(ctx):
    path = ctx.root / hlprices.BY_ORIGIN_FILE
    if not path.exists():
        pytest.skip("run `python -m arkstream funding --step price-check-origins`")
    checker = PointInTimeCheck.load(ctx)
    recorded = pl.read_csv(ctx.root / hlprices.COINS_FILE).select("coin", "outcome").sort("coin")
    assert checker.checks(ctx.cutoff).equals(recorded)  # ADR-0013 is the same rule at the CUTOFF
    saved = pl.read_csv(path, try_parse_dates=True)
    for (origin,), part in saved.group_by("origin", maintain_order=True):
        t = ts(f"{origin} 00:00:00")
        assert part.drop("origin").select("coin", "outcome").equals(checker.checks(t)), origin
        assert part["n"].to_list() == checker.outcomes(t)["n"].to_list()
