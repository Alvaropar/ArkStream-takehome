"""The cost rebuild of runs B and C (ADR-0098 item 2; pinned in ADR-0099 items 1-7). It is not a run.

Each order the frozen model prices is re-priced from the market records at that order's time:

* **delay**: one draw per order from the per-draw delay distribution (`research/latency/total_delay.csv`), fixed seed;
* **drift**: the Binance tape over the drawn delay as a ratio applied to the order's anchor (the venue basis cancels),
  on BTC, ETH, HYPE, SOL and, for the rebuild only, BNB, AAVE, EIGEN; else the frozen model's drift (flagged);
* **spread**: the ADR-0031 estimator on the decision's UTC day of Hyperliquid prints, no floor, raw Corwin-Schultz;
  fewer than 20 pairs: the frozen half-spread (flagged);
* **impact**: the square-root form with `y` fitted on the same day's taker orders (cost against the basis-corrected
  tape); fewer than 30 orders or no tape: the frozen `y` (flagged);
* **fill completeness**: no fill when the rebuilt shortfall exceeds the frozen O2 bound of the order's liquidity
  bucket (binary; the engine's failure path);
* **fee**: 4.5 bps.

Nothing here is read by run A. Files dated at or after `stop` are never opened (the holdout start before the freeze).
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from arkstream.portfolio_engine import BPS, DAY, Costs, exit_bps

C = pl.col
REBUILD_SYMBOLS = {"BNB": "BNBUSDT", "AAVE": "AAVEUSDT", "EIGEN": "EIGENUSDT"}  # ADR-0099 item 2, rebuild only
DELAY_P = (0.10, 0.50, 0.90, 0.99)
SEED = 20251203
CONFIG_CODE = {"S": 1, "U": 2, "G": 3}
MIN_PAIRS = 20  # ADR-0031 min_pairs (execution.yaml replay.spreads)
MIN_TAKER_ORDERS = 30  # the drift cell minimum (ADR-0099 item 12)


def midnight(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time(), UTC)


def ms(t: datetime) -> int:
    return int(round(t.timestamp() * 1000))


def day_of(t_ms: int) -> date:
    return date(1970, 1, 1) + timedelta(days=t_ms // DAY)


# ---------------------------------------------------------------------------------------------- 1. the delay
def delay_quantiles(path: Path) -> tuple[float, ...]:
    """The four `per_draw` totals (p10, p50, p90, p99, ms) of `research/latency/total_delay.csv`."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = {r["quantile"]: float(r["total_ms"]) for r in csv.DictReader(fh) if r["method"] == "per_draw"}
    return tuple(rows[q] for q in ("p10", "p50", "p90", "p99"))


class DelaySampler:
    """ADR-0099 item 1: linear through the four quantiles, flat outside them, whole ms; one uniform per order."""

    def __init__(self, quantiles: tuple[float, ...], seed: list[int]):
        self.q = quantiles
        self.rng = np.random.default_rng(seed)

    def at(self, u: float) -> int:
        return int(round(float(np.interp(u, DELAY_P, self.q))))

    def draw(self) -> int:
        return self.at(float(self.rng.random()))


def delay_seed(origin: date, config: str) -> list[int]:
    return [SEED, origin.toordinal(), CONFIG_CODE[config]]


# ---------------------------------------------------------------------------------------------- 2. the tape
def tape_symbols(ctx) -> dict[str, str]:
    """Rule 4's tape coins (config) plus the rebuild's own (ADR-0099 item 2)."""
    return {**dict(ctx.raw["drift"]["aggtrades_symbols"]), **REBUILD_SYMBOLS}


class Tape:
    """Binance aggTrades of the given days, checksum-verified against `MANIFEST.csv`; as-of price lookups."""

    def __init__(self, directory: Path, symbols: dict[str, str], days: list[date], stop: datetime,
                 staleness_ms: int):
        from arkstream.replay_market import tape_day

        if any(midnight(d) >= stop for d in days):
            raise ValueError(f"tape day at or after {stop}: refused (the holdout needs the freeze)")
        self.staleness_ms = staleness_ms
        with (directory / "MANIFEST.csv").open(encoding="utf8", newline="") as f:
            files = {(r["symbol"], r["date"]): r for r in csv.DictReader(f)}
        self.times: dict[str, np.ndarray] = {}
        self.prices: dict[str, np.ndarray] = {}
        self.missing: list[tuple[str, date]] = []
        for coin, symbol in sorted(symbols.items()):
            ts, ps = [], []
            for d in sorted(days):
                tr = tape_day(directory, files.get((symbol, d.isoformat())))
                if tr is None:
                    self.missing.append((coin, d))
                    continue
                ts.append(tr["transact_time"].to_numpy().astype(np.int64))
                ps.append(tr["price"].to_numpy().astype(np.float64))
            if ts:
                t = np.concatenate(ts)
                order = np.argsort(t, kind="stable")
                self.times[coin], self.prices[coin] = t[order], np.concatenate(ps)[order]

    def has(self, coin: str) -> bool:
        return coin in self.times

    def price(self, coin: str, t: int) -> float | None:
        """The last aggTrade at or before t, at most `staleness_ms` old."""
        times = self.times.get(coin)
        if times is None:
            return None
        i = int(np.searchsorted(times, t, side="right")) - 1
        if i < 0 or t - int(times[i]) > self.staleness_ms:
            return None
        return float(self.prices[coin][i])

    def prices_at(self, coin: str, t: np.ndarray) -> np.ndarray:
        """Vectorised `price` (NaN where none)."""
        times = self.times.get(coin)
        out = np.full(len(t), np.nan)
        if times is None or not len(t):
            return out
        i = np.searchsorted(times, t, side="right") - 1
        ok = (i >= 0)
        ok[ok] &= (t[ok] - times[i[ok]]) <= self.staleness_ms
        out[ok] = self.prices[coin][i[ok]]
        return out


# ---------------------------------------------------------------------------------------------- 3. the spread
def daily_spreads(fills: pl.DataFrame, coins: list[str], days: list[date], spread_rules: dict, base_half: dict,
                  lookback_days: int = 1) -> pl.DataFrame:
    """`fit_spreads` per day d on [d - lookback, d + 1 - lookback ... ) prints: lookback 1 is the day itself (the
    rebuild, ADR-0099 item 3); C's refit uses the trailing 14 days before d (item 8)."""
    from arkstream.replay_spreads import fit_spreads

    rows = []
    for d in sorted(days):
        if lookback_days == 1:
            lo, hi = midnight(d), midnight(d + timedelta(days=1))
        else:
            lo, hi = midnight(d - timedelta(days=lookback_days)), midnight(d)
        f = fit_spreads(fills, coins, lo, hi, spread_rules, base_half).with_columns(day=pl.lit(d))
        rows.append(f.select("day", "coin", "pairs", "cs_half_bps", "ar_half_bps", "simulated_bias_bps",
                             "downward_bias"))
    return pl.concat(rows, how="vertical_relaxed") if rows else pl.DataFrame()


def spread_lookup(table: pl.DataFrame) -> dict[tuple[str, date], float]:
    """(coin, day) -> raw CS half-spread where the day has at least 20 pairs (ADR-0099 items 3, 12)."""
    if table.height == 0:
        return {}
    ok = table.filter((C("pairs") >= MIN_PAIRS) & C("cs_half_bps").is_not_null())
    return {(c, d): float(v) for d, c, v in ok.select("day", "coin", "cs_half_bps").rows()}


# ---------------------------------------------------------------------------------------------- 4. the impact
def taker_orders(fills: pl.DataFrame, coins: list[str], lo: datetime, hi: datetime) -> pl.DataFrame:
    """The package's taker orders: one (trader, oid), every fill `is_maker` false, eligible core-perp trades, forced
    fills excluded, every address (ADR-0099 item 4)."""
    from arkstream.instruments import forced_fill

    f = fills.filter(C("eligible") & (C("event_kind") == "trade") & C("symbol").is_in(coins) & (C("ts") >= lo)
                     & (C("ts") < hi) & ~forced_fill()).sort("ts", "src_row")
    g = f.group_by("trader", "oid", maintain_order=True).agg(
        coin=C("symbol").first(), t=C("ts").first(), side=C("side").first(), taker=(~C("is_maker")).all(),
        notional=(C("size").abs() * C("price")).sum(), qty=C("size").abs().sum())
    return g.filter("taker").with_columns(
        vwap=C("notional") / C("qty"), sign=pl.when(C("side") == "buy").then(1.0).otherwise(-1.0),
        t_ms=C("t").dt.epoch("ms"), day=C("t").dt.date()).drop("taker")


def print_basis(fills: pl.DataFrame, tape: Tape, coins: list[str], lo: datetime, hi: datetime) -> dict:
    """(coin, day) -> median over the day's deduplicated prints of print / tape price (ADR-0099 item 4)."""
    p = (fills.filter((C("ts") >= lo) & (C("ts") < hi) & C("eligible") & (C("event_kind") == "trade")
                      & C("symbol").is_in(coins))
         .sort("ts", "src_row").unique(["symbol", "ts", "tid", "price", "size"], maintain_order=True)
         .select(coin="symbol", t_ms=C("ts").dt.epoch("ms"), day=C("ts").dt.date(), price="price"))
    out: dict[tuple[str, date], float] = {}
    for (coin,), g in p.group_by("coin"):
        if not tape.has(str(coin)):
            continue
        b = tape.prices_at(str(coin), g["t_ms"].to_numpy())
        r = g.with_columns(ratio=pl.Series(g["price"].to_numpy() / b)).filter(C("ratio").is_finite())
        for d, v in r.group_by("day").agg(C("ratio").median()).rows():
            out[(str(coin), d)] = float(v)
    return out


def bar_inputs(orders: pl.DataFrame, bars: pl.DataFrame) -> pl.DataFrame:
    """The latest completed 4h bar at each order (the engine's `bar`): volume_daily, sigma_daily."""
    b = bars.select("coin", "bar_ms", "volume_daily", "sigma_daily").sort("bar_ms")
    return orders.sort("coin", "t_ms").join_asof(b.sort("coin", "bar_ms"), left_on="t_ms", right_on="bar_ms",
                                                 by="coin", strategy="backward", tolerance=4 * 3_600_000 - 1,
                                                 check_sortedness=False)


def impact_observations(fills: pl.DataFrame, tape: Tape, bars: pl.DataFrame, half: dict, frozen_half,
                        coins: list[str], lo: datetime, hi: datetime) -> pl.DataFrame:
    """Per taker order on a tape coin: x = σ √(N / V) × 10⁴ and z = sign (VWAP / reference - 1) × 10⁴ - half-spread,
    reference = tape(first fill - 1 ms) × the day's print basis (ADR-0099 item 4)."""
    tc = [c for c in coins if tape.has(c)]
    o = taker_orders(fills, tc, lo, hi)
    if o.height == 0:
        return pl.DataFrame(schema={"coin": pl.String, "day": pl.Date, "x": pl.Float64, "z": pl.Float64})
    basis = print_basis(fills, tape, tc, lo, hi)
    parts = []
    for (coin,), g in o.group_by("coin"):
        p0 = tape.prices_at(str(coin), g["t_ms"].to_numpy() - 1)
        parts.append(g.with_columns(p0=pl.Series(p0)))
    o = pl.concat(parts)
    o = bar_inputs(o, bars)
    rows = []
    for r in o.iter_rows(named=True):
        b = basis.get((r["coin"], r["day"]))
        if b is None or not math.isfinite(r["p0"]) or not r["volume_daily"] or r["volume_daily"] <= 0 or (
                r["sigma_daily"] is None):
            continue
        ref = r["p0"] * b
        h = half.get((r["coin"], r["day"]))
        h = frozen_half(r["coin"], r["t_ms"]) if h is None else h
        x = r["sigma_daily"] * math.sqrt(r["notional"] / r["volume_daily"]) * BPS
        if x <= 0:
            continue
        z = r["sign"] * (r["vwap"] / ref - 1) * BPS - h
        rows.append((r["coin"], r["day"], x, z))
    return pl.DataFrame(rows, schema={"coin": pl.String, "day": pl.Date, "x": pl.Float64, "z": pl.Float64},
                        orient="row")


def fit_y(obs: pl.DataFrame) -> dict[tuple[str, date], tuple[float, int]]:
    """(coin, day) -> (max(Σxz / Σx², 0), n) where n >= 30 (ADR-0099 item 4)."""
    if obs.height == 0:
        return {}
    g = obs.group_by("coin", "day").agg(n=pl.len(), sxz=(C("x") * C("z")).sum(), sxx=(C("x") ** 2).sum())
    return {(c, d): (max(sxz / sxx, 0.0), int(n)) for c, d, n, sxz, sxx in g.select(
        "coin", "day", "n", "sxz", "sxx").rows() if n >= MIN_TAKER_ORDERS and sxx > 0}


# ---------------------------------------------------------------------------------------------- 5. O2
def o2_bounds(tree: Path, origins: list[date], scenario_dir: str = "scenario=stress_sqrt_cap_part_ns_sweep_frozen"
              ) -> pl.DataFrame:
    """ADR-0099 item 5: per ADR-0053 bucket, the p99 of the stress price shortfall without the fee over the filled
    trigger-leg orders of the four development test windows."""
    parts = []
    for o in origins:
        path = tree / f"origin={o}" / "window=test" / scenario_dir / "follower_orders.parquet"
        parts.append(pl.read_parquet(path, columns=["status", "resize_leg", "quantity", "fill_px", "mid_L",
                                                    "liq_bucket"]).with_columns(origin=pl.lit(o)))
    d = pl.concat(parts).filter((C("status") == "filled") & ~C("resize_leg") & (C("mid_L") > 0))
    d = d.with_columns(shortfall_bps=C("quantity").sign() * (C("fill_px") / C("mid_L") - 1) * BPS)
    return d.group_by("liq_bucket").agg(orders=pl.len(), p99_bps=C("shortfall_bps").quantile(0.99, "linear"),
                                        median_bps=C("shortfall_bps").median()).sort("liq_bucket")


# ---------------------------------------------------------------------------------------------- the pricer
@dataclass
class RebuildInputs:
    tape: Tape
    spread_day: dict[tuple[str, date], float]
    y_day: dict[tuple[str, date], tuple[float, int]]
    o2: dict[str, float]
    quantiles: tuple[float, ...]
    receive_ms: int
    debounce_ms: int
    fee_bps: float
    frozen_y: float
    spread_table: pl.DataFrame | None = None


@dataclass
class Rebuild:
    """The engine's `pricer` in runs B and C (ADR-0099 items 1-7, 9-10)."""

    inp: RebuildInputs
    delays: DelaySampler
    base: Costs
    stress: Costs
    updated: Any = None  # C: the updated view (its base cost per order is recorded)
    own: list[tuple[date, str, float, float]] = field(default_factory=list)  # C's filled orders: day, coin, x, z

    def price(self, eng, coin: str, t: int, q: float, trader: str, sig, flatten: bool, px_f: float,
              impact_f: float, half_f: float, ack_f: int, source_f: str, anchor: float) -> dict:
        sign = math.copysign(1.0, q)
        costs_f = self.stress if flatten else self.base
        leg = next((g for g in sig.legs if g.coin == coin), None) if sig is not None else None
        trigger = source_f == "tree_trigger"
        draw = self.delays.draw()
        if trigger and sig is not None:
            t0 = sig.event_ms
            ack = max(t0 + draw, t)
        else:
            t0 = t
            ack = t + max(draw - self.inp.receive_ms - self.inp.debounce_ms, 0)
        ref_f = px_f / (1 + sign * (half_f + impact_f) / BPS)
        drift_f = sign * (ref_f / anchor - 1) * BPS
        # drift (item 2)
        tape = self.inp.tape
        p0, p1 = tape.price(coin, t0), tape.price(coin, ack)
        if tape.has(coin) and p0 and p1:
            ref, drift_flag = anchor * p1 / p0, "tape"
        else:
            ref, drift_flag = ref_f, ("frozen_no_print" if tape.has(coin) else "frozen_no_tape")
        drift_r = sign * (ref / anchor - 1) * BPS
        # spread (item 3)
        day = day_of(t)
        cs = self.inp.spread_day.get((coin, day))
        half, half_flag = (cs, "day") if cs is not None else (half_f, "frozen")
        # impact (item 4)
        _, bar_vol, vol_daily, sigma = eng.market.bar(coin, t)
        fit = self.inp.y_day.get((coin, day)) if tape.has(coin) else None
        y, y_flag = (fit[0], "day") if fit is not None else (self.inp.frozen_y, "frozen")
        x = (BPS * sigma * math.sqrt(abs(q) * ref / vol_daily)
             if vol_daily and vol_daily > 0 and sigma is not None else 0.0)
        impact = y * x
        px = ref * (1 + sign * (half + impact) / BPS)
        shortfall = sign * (px / anchor - 1) * BPS
        bucket = eng.market.bucket(bar_vol)
        bound = self.inp.o2.get(bucket, max(self.inp.o2.values()) if self.inp.o2 else math.inf)
        status = "rejected_o2" if shortfall > bound else "filled"
        fee = abs(q) * px * self.inp.fee_bps / BPS
        rec = {
            "px": px if status == "filled" else None, "fee": fee if status == "filled" else 0.0,
            "impact_bps": impact, "half_bps": half, "ack_ms": ack, "status": status,
            "trader": trader, "trigger_leg": trigger, "t0_ms": t0, "anchor_px": anchor, "bucket": bucket,
            "o2_bound_bps": bound, "shortfall_bps": shortfall, "x_bps": x,
            # frozen model (the cost A charges for this order)
            "frozen_delay_ms": (ack_f - t0) if trigger else (ack_f - t + self.inp.receive_ms + self.inp.debounce_ms),
            "frozen_drift_bps": drift_f, "frozen_half_bps": half_f, "frozen_impact_bps": impact_f,
            "frozen_fee_bps": costs_f.fee_bps, "frozen_shortfall_bps": sign * (px_f / anchor - 1) * BPS,
            "frozen_status": "filled", "frozen_source": source_f,
            # the rebuild
            "rebuilt_delay_ms": draw, "rebuilt_drift_bps": drift_r, "rebuilt_half_bps": half,
            "rebuilt_impact_bps": impact, "rebuilt_fee_bps": self.inp.fee_bps, "rebuilt_shortfall_bps": shortfall,
            "rebuilt_status": status, "drift_flag": drift_flag, "half_flag": half_flag, "impact_flag": y_flag,
            "rebuilt_y": y,
        }
        if self.updated is not None:
            rec.update(self.updated_parts(eng, coin, t, q, trader, leg, flatten, trigger, source_f, drift_f, ref_f,
                                          bar_vol, vol_daily, sigma, costs_f))
            sb = exit_bps(self.updated, self.stress, coin, t, trader, abs(q) * (eng.mark(coin, t) or anchor))
            rec["shadow_o2_bound_bps"] = (sb - self.stress.fee_bps) if sb is not None else None
            rec["shadow_o2_reject"] = bool(sb is not None and shortfall > sb - self.stress.fee_bps)
        return rec

    def updated_parts(self, eng, coin, t, q, trader, leg, flatten, trigger, source_f, drift_f, ref_f, bar_vol,
                      vol_daily, sigma, costs_f: Costs) -> dict:
        """C's model (ADR-0099 items 8, 10): the same order priced with the refitted spread, drift cell and `y`."""
        u = self.updated
        assert u is not None
        tape_based = (trigger and leg is not None and leg.tape_factor is not None) or source_f == "tape_factor"
        drift_u = drift_f
        if not tape_based:
            thin = costs_f.delay_thin_ms is not None and (bar_vol is None or bar_vol < costs_f.thin_volume_usdc)
            delay = costs_f.delay_thin_ms if thin and costs_f.delay_thin_ms is not None else costs_f.delay_ms
            bucket = eng.market.bucket(bar_vol)
            d_f = eng.market.drift(coin, t, trader, costs_f.regime, delay, bucket)
            d_u = u.drift(coin, t, trader, costs_f.regime, delay, bucket)
            if d_f is not None and d_u is not None:
                drift_u = drift_f + (d_u - d_f)
        half_u = u.half_spread(coin, t, costs_f.regime)
        y_u = u.impact_y(coin, t)
        impact_u = (costs_f.impact_mult * BPS * y_u * sigma * math.sqrt(abs(q) * ref_f / vol_daily)
                    if costs_f.impact_mult and vol_daily and vol_daily > 0 and sigma is not None else 0.0)
        return {"updated_delay_ms": costs_f.delay_ms, "updated_drift_bps": drift_u, "updated_half_bps": half_u,
                "updated_impact_bps": impact_u, "updated_fee_bps": costs_f.fee_bps,
                "updated_shortfall_bps": drift_u + half_u + impact_u, "updated_status": "filled", "updated_y": y_u}

    def filled(self, rec: dict) -> None:
        """C learns from its own fill after the fill's rebuild window closes (ADR-0099 items 7-8)."""
        if rec.get("x_bps"):
            self.own.append((day_of(int(rec["decision_ms"])), rec["coin"], float(rec["x_bps"]),
                             float(rec["rebuilt_impact_bps"])))
