"""The point-in-time invariance check, shared by the invariance tests and the seeded leak tests.

An output computed at asof=T must not change when rows after T are removed (truncated inputs) or
replaced by adversarial rows. `pit_violations` returns what differs, so a leak test can assert that
a planted leak is caught.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl
from polars.testing import assert_frame_equal

from arkstream.config import Context
from arkstream.pipeline import Inputs, build


def future_garbage(inputs: Inputs, after: datetime) -> Inputs:
    """Append adversarial rows after T: reversed positions, zero equity, a copier echo of every order."""
    past = inputs.fills.filter(pl.col("ts") <= after).sort("ts", "src_row")
    later = (pl.lit(after).dt.cast_time_unit("ms") + pl.duration(milliseconds=pl.int_range(1, pl.len() + 1))
             ).dt.cast_time_unit("ms")
    f = past.tail(5000).with_columns(ts=later, start_position=-pl.col("start_position") * 3 + 7,
                                     src_row=pl.col("src_row") + 10_000_000)
    echo = past.tail(2000).with_columns(
        trader=pl.lit("0xfeedfacefeedfacefeedfacefeedfacefeedface"),
        ts=(later + pl.duration(seconds=1)).dt.cast_time_unit("ms"),
        src_row=pl.col("src_row") + 20_000_000)
    t = inputs.traders.filter(pl.col("ts") <= after).sort("ts").tail(500).with_columns(
        ts=(later + pl.duration(days=2)).dt.cast_time_unit("ms"), equity=pl.lit(0.0),
        src_row=pl.col("src_row") + 10_000_000,
    ).with_columns(date=pl.col("ts").dt.date())
    assert all(df.select((pl.col("ts") > after).all()).item() for df in (f, echo, t))
    return Inputs(traders=pl.concat([inputs.traders, t]), fills=pl.concat([inputs.fills, f, echo]))


def truncate(inputs: Inputs, t: datetime) -> Inputs:
    return Inputs(traders=inputs.traders.filter(pl.col("ts") <= t), fills=inputs.fills.filter(pl.col("ts") <= t))


def _differs(a: pl.DataFrame, b: pl.DataFrame) -> bool:
    try:
        assert_frame_equal(a, b, check_row_order=True)
    except AssertionError:
        return True
    return False


def pit_violations(ctx: Context, inputs: Inputs, t: datetime, adversarial: bool = True) -> list[str]:
    """Names of outputs at t that change between truncated, full and (optionally) adversarial inputs."""
    a = build(ctx, truncate(inputs, t), t)
    others = [build(ctx, inputs, t)]
    if adversarial:
        others.append(build(ctx, future_garbage(inputs, t), t))
    bad: set[str] = set()
    for o in others:
        bad |= {f"headline.{k}" for k in a.headline if a.headline[k] != o.headline.get(k)}
        bad |= {name for name in a.tables if _differs(a.tables[name], o.tables[name])}
    return sorted(bad)


def replay_event_violations(orders: pl.DataFrame, end_ms: int, receive_ms: int) -> list[str]:
    """Check the normal delayed order ledger against individual source events and both market clocks."""
    failures = set()
    for r in orders.iter_rows(named=True):
        if any(t + receive_ms > r["decision_ms"] for t in r["source_event_ms"]):
            failures.add("unseen_source")
        if r["visible_ms"] > r["decision_ms"] or (r["eq_ms"] is not None and r["eq_ms"] > r["decision_ms"]):
            failures.add("future_decision_input")
        if not r["decision_ms"] < r["ack_ms"] < end_ms:
            failures.add("ack_clock")
        if r["status"] == "filled" and r["price_source"] == "binance_aggtrade":
            if not (0 <= r["event_ms"] - r["b0_ms"] <= 1000 and 0 <= r["ack_ms"] - r["b1_ms"] <= 1000
                    and r["b1_ms"] > max(r["last_visible_ms"], r["visible_ms"])):
                failures.add("execution_print_clock")
    return sorted(failures)


# ---------------------------------------------------------------- Phase 2: leader evidence (leader*.py)
def leader_subset(inputs: Inputs, ctx: Context, t: datetime, n: int = 12) -> Inputs:
    """A small real slice: the first n addresses graded A/B at t, so three leader runs stay fast."""
    rep = build(ctx, truncate(inputs, t), t).tables["quality_report"]
    keep = rep.filter(pl.col("grade").is_in(["A", "B"]) & (pl.col("n_fills") > 50)).sort("trader")["trader"].head(n)
    f = pl.col("trader").is_in(keep.implode())
    return Inputs(traders=inputs.traders.filter(f), fills=inputs.fills.filter(f))


def leader_violations(ctx: Context, inputs: Inputs, t: datetime, adversarial: bool = True) -> list[str]:
    """Names of leader tables at t that change between truncated, full and (optionally) adversarial inputs."""
    from arkstream import leader

    # The same truncation must hold for publication times and candle closes as for the package rows.
    later = t + timedelta(days=1)
    rates = leader.load_funding(ctx, later)
    candles, _ = leader.hlprices.load_candles(ctx.path("hyperliquid_dir"), later)
    early = {"funding": rates.filter(pl.col("known_at") <= t), "candles": candles.filter(pl.col("ts") <= t)}
    full = {"funding": rates, "candles": candles}
    a = leader.compute(ctx, truncate(inputs, t), t, **early)
    assert set(a) == set(leader.TABLES)
    others = [leader.compute(ctx, inputs, t, **full)]
    if adversarial:
        rates = rates.with_columns(funding_rate=pl.when(pl.col("known_at") > t).then(9.).otherwise("funding_rate"))
        candles = candles.with_columns(price=pl.when(pl.col("ts") > t).then(1e9).otherwise("price"))
        others.append(leader.compute(ctx, future_garbage(inputs, t), t, funding=rates, candles=candles))
    bad: set[str] = set()
    for o in others:
        bad |= {f"leader.{name}" for name in a if _differs(a[name], o[name])}
    return sorted(bad)
