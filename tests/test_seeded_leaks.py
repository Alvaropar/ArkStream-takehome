"""Seeded leak tests: plant a known leak and check that the point-in-time tests catch it.

A guard that has never been seen to fail proves nothing. Each test here introduces one realistic
look-ahead bug and asserts that the invariance check (`pit_check.pit_violations`) or the cutoff
check reports it. The third planned leak (pricing at event time instead of event time + d) belongs
to the follower replay and is added with it.
"""

from __future__ import annotations

from datetime import timedelta

import polars as pl
import pytest
from conftest import ts
from pit_check import pit_violations

from arkstream import pipeline, positions, quality, reconcile
from arkstream.config import CONFIG_DIR, ROOT, load_context
from arkstream.pipeline import Inputs, build

T = ts("2025-10-15 15:39:40.221")


def _snapshot_known_a_day_early(df: pl.DataFrame, asof, col: str = "ts") -> pl.DataFrame:
    """The leak: an account snapshot is treated as known one day before its own timestamp."""
    if "equity" in df.columns:
        return df.with_columns(pl.col(col) - pl.duration(days=1)).filter(pl.col(col) <= asof)
    return positions.pit(df, asof, col)


@pytest.mark.data
def test_leak_snapshot_used_before_its_timestamp_is_caught(ctx, inputs, monkeypatch):
    for mod in (pipeline, quality, reconcile):  # every module that filters snapshots by time
        monkeypatch.setattr(mod, "pit", _snapshot_known_a_day_early)
    caught = pit_violations(ctx, inputs, T, adversarial=False)
    assert "recon_snapshots" in caught and "quality_report" in caught, caught


def _one_trader(inputs: Inputs) -> Inputs:
    """A small real slice (one address with fills and snapshots) so a full-cutoff build stays fast."""
    tr = (inputs.fills.select("trader").unique().join(inputs.traders.select("trader").unique(), on="trader")
          .sort("trader")["trader"][0])
    return Inputs(traders=inputs.traders.filter(pl.col("trader") == tr),
                  fills=inputs.fills.filter(pl.col("trader") == tr))


def _with_markers(inputs: Inputs, at) -> Inputs:
    """One fill and one snapshot copied from the last real rows and moved to `at`."""
    def move(df: pl.DataFrame) -> pl.DataFrame:
        last = df.sort("ts", "src_row").tail(1)
        moved = last.with_columns(ts=pl.lit(at).dt.cast_time_unit("ms"), src_row=pl.col("src_row") + 30_000_000)
        return moved.with_columns(date=pl.col("ts").dt.date()) if "date" in df.columns else moved
    return Inputs(traders=pl.concat([inputs.traders, move(inputs.traders)]),
                  fills=pl.concat([inputs.fills, move(inputs.fills)]))


@pytest.mark.data
def test_leak_cutoff_moved_one_day_is_caught(ctx, inputs, tmp_path):
    base = _one_trader(inputs)
    marked = _with_markers(base, ctx.cutoff + timedelta(hours=12))

    # Under the real cutoff the marker rows are invisible: identical outputs with or without them.
    assert build(ctx, marked).headline == build(ctx, base).headline

    # Move CUTOFF one day later in a copy of the config file itself (not in code).
    cfg = tmp_path / "config"
    cfg.mkdir()
    for p in CONFIG_DIR.glob("*.yaml"):
        (cfg / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    text = (cfg / "decision_context.yaml").read_text(encoding="utf-8")
    old = ctx.raw["cutoff"]
    new = (ctx.cutoff + timedelta(days=1)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    assert text.count(f'"{old}"') == 1
    (cfg / "decision_context.yaml").write_text(text.replace(f'"{old}"', f'"{new}"'), encoding="utf-8")
    moved = load_context(cfg, ROOT)
    assert moved.cutoff == ctx.cutoff + timedelta(days=1)  # CUTOFF really comes from the YAML

    # Under the moved cutoff the same marker rows are used: the move is visible in the outputs.
    h0, h1 = build(moved, base).headline, build(moved, marked).headline
    assert h1["fills_rows"] == h0["fills_rows"] + 1
    assert h1["traders_rows"] == h0["traders_rows"] + 1
    assert h1["asof"] != build(ctx, base).headline["asof"]
