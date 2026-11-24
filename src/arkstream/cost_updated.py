"""Run C's cost model: the frozen market view with the half-spread, the drift table and the impact `y` refitted daily
at 00:00 UTC on data before that time (ADR-0098 item 4; pinned in ADR-0099 items 8-9).

* **spread**: the ADR-0031 estimator on the trailing 14 days of prints, the scenario floor kept;
* **drift table**: `drift.estimate` at daily vintages (rules 4 and 5 on the expanding history), with the ADR-0053
  bucket cells, the ADR-0061 split-order cells and each leader's hold band at the same vintages;
* **impact `y`**: the rebuild's taker-order fit pooled over the trailing 14 days, plus C's own past fills.

Fixed: the delays, the fee, the half-spread floors, the 3x stress impact multiple, the C1 and O2 benchmarks. Marks,
bars, funding, shocks and betas are the frozen view's. The view feeds the stress limits and the gray loss cap of C
only; C1 and O2 keep the frozen model (the engine's `market`).
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta

import polars as pl

from arkstream.cost_rebuild import MIN_PAIRS, MIN_TAKER_ORDERS, day_of, midnight
from arkstream.portfolio_engine import MAJORS

C = pl.col
TRAILING_DAYS = 14  # the length of the original spread fit (ADR-0098 item 4)
CELL_COLS = ["origin", "period", "source", "coin", "band", "horizon_ms", "measured", "mean_bps"]


def daily_cells(ctx, inputs, days: list[date], stop: datetime) -> tuple[pl.DataFrame, pl.DataFrame]:
    """The drift table at each day of `days` from data before it: the development estimation rules (`drift.estimate`,
    rules 4 and 5, 10-11 Oct excluded from development and used as the stress sample once known), restricted to the
    coins passing the price check at that day (ADR-0044), with the ADR-0053 bucket cells and the ADR-0061 split-order
    cells at the same vintages, as `replay_market.vintages` builds them at the origins. Returns (cells, bands)."""
    from arkstream import drift
    from arkstream.config import load_yaml
    from arkstream.hlprices import PointInTimeCheck
    from arkstream.prices import scan_reference
    from arkstream.replay_market import short_floor_cells, stress_bucket_cells

    if any(midnight(d) >= stop for d in days):
        raise ValueError(f"a daily vintage at or after {stop}")
    rules = drift.DriftRules.from_config(ctx.raw)
    days = sorted(days)
    rd = dataclasses.replace(rules, est_end=days[-1] - timedelta(days=1), origins=tuple(days))
    src = drift.AggTradesSource(ctx.path("aggtrades_dir"), rd)
    rp = ctx.raw["reference_prices"]
    ref = scan_reference(ctx.path("reference_prices_dir"))
    fills = inputs.fills.filter(C("ts") < stop)
    res = drift.estimate(fills, ref, src, rd, rp["max_age_s"], rp["fallback_print_window_s"])
    cells = pl.concat([res["development"].select(CELL_COLS), res["stress"].select(CELL_COLS)],
                      how="vertical_relaxed")
    checker = PointInTimeCheck.load(ctx)
    allowed = pl.concat([
        pl.DataFrame({"origin": [v] * len(p), "coin": p}, schema={"origin": pl.Date, "coin": pl.String})
        for v in days for p in [checker.passing(midnight(v))]])
    cells = cells.join(allowed, on=["origin", "coin"], how="semi")
    replay_cfg = load_yaml("execution.yaml", ctx.root / "config")["replay"]
    fallback = replay_cfg["stress_fallback"]
    inp = type(inputs)(inputs.traders.filter(C("ts") < stop), fills)
    buckets = stress_bucket_cells(ctx, inp, rd, checker, ref, stop, fallback)
    split = short_floor_cells(ctx, inp, rd, checker, days, stop, replay_cfg.get("alt_short_floor") or {},
                              fallback["bucket_edges_usdc"])
    out = pl.concat([cells, buckets.select(CELL_COLS), split.select(CELL_COLS)], how="vertical_relaxed")
    return out.sort(CELL_COLS[:6]), res["bands"].sort("origin", "trader")


def origin_check(daily: pl.DataFrame, tree_cells: pl.DataFrame, origins: list[date]) -> pl.DataFrame:
    """ADR-0099 item 8: on an origin day the daily cells equal the origin's frozen cells (values to 1e-9)."""
    rows = []
    key = CELL_COLS[:6]
    for o in origins:
        a = daily.filter(C("origin") == o).select(*key, "mean_bps", "measured")
        b = tree_cells.filter(C("origin") == o).select(*key, "mean_bps", "measured")
        j = a.join(b, on=key, how="full", coalesce=True, suffix="_frozen")
        both = j.filter(C("mean_bps").is_not_null() & C("mean_bps_frozen").is_not_null())
        diff = both.filter((C("mean_bps") - C("mean_bps_frozen")).abs() > 1e-9 * (1 + C("mean_bps_frozen").abs()))
        rows.append({"origin": o, "daily_cells": a.height, "frozen_cells": b.height,
                     "only_daily": j.filter(C("mean_bps_frozen").is_null() & C("mean_bps").is_not_null()).height,
                     "only_frozen": j.filter(C("mean_bps").is_null() & C("mean_bps_frozen").is_not_null()).height,
                     "values_differ": diff.height,
                     "measured_differ": both.filter(C("measured") != C("measured_frozen")).height})
    return pl.DataFrame(rows)


class UpdatedMarket:
    """C's view (ADR-0099 item 8). Implements the engine's `Market` protocol, plus `impact_y`."""

    def __init__(self, frozen, params, bands: pl.DataFrame, spreads14: dict[tuple[str, date], float],
                 taker: pl.DataFrame, pricer, frozen_y: float):
        self.frozen, self.params, self.pricer, self.frozen_y = frozen, params, pricer, frozen_y
        self.band = {(d, tr): b for d, tr, b in bands.select("origin", "trader", "band").rows()}
        self.spreads = spreads14
        self.sums: dict[tuple[str, date], tuple[int, float, float]] = {}
        if taker.height:
            g = taker.group_by("coin", "day").agg(n=pl.len(), sxz=(C("x") * C("z")).sum(), sxx=(C("x") ** 2).sum())
            self.sums = {(c, d): (int(n), float(a), float(b)) for c, d, n, a, b in g.select(
                "coin", "day", "n", "sxz", "sxx").rows()}
        self.cache: dict[tuple, float | None] = {}
        self.ycache: dict[tuple[str, date], float] = {}

    # frozen parts
    def mark(self, coin: str, t: int):
        return self.frozen.mark(coin, t)

    def bar(self, coin: str, t: int):
        return self.frozen.bar(coin, t)

    def funding(self, coin: str, hour: int):
        return self.frozen.funding(coin, hour)

    def shock(self, coin: str, long: bool) -> float:
        return self.frozen.shock(coin, long)

    def beta(self, coin: str) -> float:
        return self.frozen.beta(coin)

    def bucket(self, volume):
        return self.frozen.bucket(volume)

    # refitted parts
    def half_spread(self, coin: str, t: int, regime: str) -> float:
        c = self.frozen.costs[regime]
        configured = c.half_majors if coin in MAJORS else c.half_other
        cs = self.spreads.get((coin, day_of(t)))
        return max(configured, cs) if cs is not None else self.frozen.half_spread(coin, t, regime)

    def drift(self, coin: str, t: int, trader: str, regime: str, delay_ms: int, bucket: str) -> float | None:
        d = day_of(t)
        band = self.band.get((d, trader), "no_closed_trip")
        key = (d, coin, regime, band, delay_ms, bucket)
        if key not in self.cache:
            period = "stress" if regime == "stress" else "development"
            v, _, _, _ = self.params.lookup(d, period, coin, band, delay_ms, conservative=regime == "base",
                                            bucket=bucket)
            self.cache[key] = v
        return self.cache[key]

    def impact_y(self, coin: str, t: int) -> float:
        d = day_of(t)
        key = (coin, d)
        if key not in self.ycache:
            n, sxz, sxx = 0, 0.0, 0.0
            for k in range(1, TRAILING_DAYS + 1):
                s = self.sums.get((coin, d - timedelta(days=k)))
                if s:
                    n, sxz, sxx = n + s[0], sxz + s[1], sxx + s[2]
            for day, c, x, z in self.pricer.own:
                if c == coin and day < d:
                    n, sxz, sxx = n + 1, sxz + x * z, sxx + x * x
            self.ycache[key] = max(sxz / sxx, 0.0) if n >= MIN_TAKER_ORDERS and sxx > 0 else self.frozen_y
        return self.ycache[key]


def trailing_spreads(table: pl.DataFrame) -> dict[tuple[str, date], float]:
    """(coin, day) -> CS half-spread of the trailing 14 days where at least 20 pairs (ADR-0099 item 8)."""
    if table.height == 0:
        return {}
    ok = table.filter((C("pairs") >= MIN_PAIRS) & C("cs_half_bps").is_not_null())
    return {(c, d): float(v) for d, c, v in ok.select("day", "coin", "cs_half_bps").rows()}
