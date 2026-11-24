"""ADR-A0140: the coin filter executed inside the frozen replay, and the single-window (holdout) path."""

from __future__ import annotations

import hashlib
from datetime import date

import polars as pl
import pytest
from conftest import need
from test_replay import BASE, END, RULES, START, T

from arkstream.config import ROOT, load_context
from arkstream.replay_book import MEASURED_OUTCOMES
from arkstream.replay_cap import MinuteMarks, cap_legs
from arkstream.replay_capture import CATEGORY
from arkstream.replay_orders import EXCLUDED, NOT_SUBMITTED, batches, execute
from arkstream.replay_sensitivity import filter_checks

C = pl.col
TREE = ROOT / "research/replay_coinfilter"
SUFFIX = "_sqrt_cap_part_ns_sweep_frozen"


def test_filter_checks_marks_only_passing_unkept_coins():
    checks = pl.DataFrame({"coin": ["BTC", "ZEC", "AAA", "BBB"], "outcome": ["pass", "pass", "fail", "pass"]})
    got = {c: (o, p) for c, o, p in filter_checks(checks, ["BTC", "BBB"]).rows()}
    assert got == {"BTC": ("pass", "pass"), "ZEC": ("coin_filter", "pass"), "AAA": ("coin_filter", "fail"),
                   "BBB": ("pass", "pass")}


def test_status_is_excluded_measured_and_uncopyable():
    assert "coin_filter_excluded" in EXCLUDED and "coin_filter_excluded" in NOT_SUBMITTED
    assert "coin_filter_excluded" in MEASURED_OUTCOMES
    assert CATEGORY["coin_filter_excluded"] == "uncopyable_coin"


def two_coin_setup():
    marks = MinuteMarks(T, T + 24 * 3600000, ["A", "B"])
    marks.values["A"][:] = 100.0
    marks.values["B"][:] = 100.0
    rows = [
        ("w", "A", 1, 1, T + 1000, 1, 11, 100.0, "buy", False, 300.0),
        ("w", "B", 2, 2, T + 2000, 2, 12, 100.0, "buy", False, 50.0),
    ]
    ev = pl.DataFrame(
        rows,
        schema=["trader", "coin", "seq", "oid", "event_ms", "src_row", "tid", "price", "side", "is_maker", "pos_after"],
        orient="row",
    )
    snaps = pl.DataFrame({"trader": ["w"], "equity": [10000.0], "frozen": [False], "eq_ms": [T], "equity_row": [22]})
    return marks, ev, snaps, batches(ev, 250, 250, START, END)


def test_cap_and_resize_legs_on_kept_coins_only():
    marks, ev, snaps, b = two_coin_setup()
    # unfiltered: A (30,000) + B (5,000) breach the 15,000 cap, so B's decision resizes A too
    both = cap_legs(b, ev, snaps, marks, {"A", "B"}, 10000, 15000, 250, START, END).filter(C("signal") == 1)
    assert both["cap_scale"][0] == pytest.approx(15000 / 35000) and sorted(both["coin"]) == ["A", "B"]
    # A filtered out: the cap book holds B alone (5,000 < 15,000): no scaling and no resize leg on A
    kept = cap_legs(b, ev, snaps, marks, {"B"}, 10000, 15000, 250, START, END).filter(C("signal") == 1)
    assert kept["coin"].to_list() == ["B"] and kept["cap_scale"][0] == 1.0
    assert kept["capped_target"][0] == pytest.approx(50.0)


def test_excluded_leg_never_reserved_or_filled():
    marks, ev, snaps, b = two_coin_setup()
    legs = cap_legs(b, ev, snaps, marks, {"B"}, 10000, 15000, 250, START, END).sort("signal")
    frame = legs.with_columns(
        equity=pl.lit(10000.0), frozen=pl.lit(False), ack_ms=C("decision_ms") + 500, ref_px=pl.lit(100.0),
        price_reason=pl.when(C("coin") == "A").then(pl.lit("coin_filter_excluded")).otherwise(pl.lit("")),
        half_bps=pl.lit(1.0), bar_volume_usdc=pl.lit(1e6), mean_bps=pl.lit(None, pl.Float64), mid_L=pl.lit(100.0),
    )
    got = execute(frame, BASE, dict(RULES, cap_usdc=15000), cap_marks=marks).sort("coin")
    a = got.filter(C("coin") == "A")
    assert (a["status"] == "coin_filter_excluded").all() and a["fill_px"].null_count() == a.height
    bfill = got.filter(C("coin") == "B").row(0, named=True)
    assert bfill["status"] == "filled"
    # the excluded A leg left nothing in the reservation book: B's reservation sees only B
    assert bfill["reserved_gross_before"] == pytest.approx(0.0)


def published(window: str, scenario: str) -> pl.DataFrame:
    path = TREE / f"origin=2025-11-19/window={window}"
    path = path / ("benchmark=unattainable_frozen" if scenario == "benchmark" else f"scenario={scenario}{SUFFIX}")
    return pl.read_parquet(path / "follower_orders.parquet", columns=["coin", "status", "resize_leg", "trader"])


@pytest.mark.data
def test_published_filter_never_trades_excluded_coins():
    need(TREE / "origin=2025-11-19", "uv run python -m arkstream replay --coin-filter")
    sets = pl.read_csv(TREE / "coin_sets.csv", try_parse_dates=True)
    kept = set(sets.filter(C("origin") == date(2025, 11, 19))["coin"])
    for window in ("training", "test"):
        for sc in ("base", "stress", "benchmark"):
            o = published(window, sc)
            filled = set(o.filter(C("status") == "filled")["coin"])
            assert filled <= kept, (window, sc, sorted(filled - kept)[:5])
            assert set(o.filter(C("resize_leg"))["coin"]) <= kept
            excl = o.filter(C("status") == "coin_filter_excluded")
            assert excl.height > 0 and not set(excl["coin"]) & kept


def tree_hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*.parquet"))}


@pytest.mark.data
def test_single_window_branch_reproduces_development_window(tmp_path):
    """The holdout's code path (one window, inputs bounded at its end) on the 19 Nov test window, whose end is the
    full run's bound, gives the same files byte for byte. No holdout data is read."""
    need(TREE / "origin=2025-11-19/window=test", "uv run python -m arkstream replay --coin-filter")
    from arkstream import replay_coinfilter

    ctx = load_context()
    replay_coinfilter.run_window(ctx, date(2025, 11, 19), date(2025, 11, 19), date(2025, 12, 3), tmp_path)
    rel = "origin=2025-11-19/window=test"
    mine = tree_hashes(tmp_path / rel)
    ref = {k: v for k, v in tree_hashes(TREE / rel).items() if not k.startswith(("universe", "leader_series"))}
    assert mine == ref


def test_holdout_path_refused_without_matching_freeze(tmp_path):
    from test_selection import frozen_copy

    from arkstream import freeze, replay_coinfilter

    ctx = frozen_copy(tmp_path)  # frozen: true, no freeze file
    with pytest.raises(freeze.FreezeError):
        replay_coinfilter.run_holdout(ctx, tmp_path / "out")
    assert not (tmp_path / "out").exists()
