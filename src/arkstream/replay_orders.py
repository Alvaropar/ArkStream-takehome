"""Follower decisions, batched visible fills and acknowledgement-time cash entries.

Delays and drift horizons are whole milliseconds end to end (ADR-0150): `delay_ms` on every order, drift cells keyed
by `horizon_ms`; `delay_s` is a readable float copy.
"""

import heapq
import json
import math

import polars as pl

from arkstream.instruments import forced_fill
from arkstream.replay_cap import CapBook
from arkstream.replay_market import DAY, DIRECT, LONG_MS, SPLIT_PREFIX, liquidity_bucket, ms

C = pl.col
KEY = ["trader", "coin"]
BPS = 10_000
VOL_NOTE = "Mean shortfall on parameterised orders understates copy-series volatility and can distort Sharpe."
# Coins the price check (as of the window's origin, ADR-0110) does not let the follower copy, and coins the selection
# rule's coin filter leaves out (ADR-0140: outcome `coin_filter` in the window's check table; never traded, also not
# by the benchmark).
EXCLUDED = ("failed_price_check", "no_binance_mapping", "insufficient_price_check", "coin_filter_excluded")
# Statuses that never reach a fill and are not submitted (no reservation).
NOT_SUBMITTED = ("below_minimum", "at_target", *EXCLUDED, "missing_cap_mark", "cap_headroom",
                 "missing_participation_volume", "missing_order_budget", "reduce_only")
COST_FIELDS = ("fee_bps", "half_spread_bps", "impact")
REGIMES = ("optimistic", "base", "stress")  # the cost rules the code knows (ADR-0080, 0088, 0114, 0115, 0120, 0122)


def resolve_scenarios(raw):
    """execution.yaml `scenarios` -> settings per scenario with integer millisecond delays (ADR-0150).

    Each scenario has `delay_ms` (and optionally `delay_thin_ms` for coins whose latest completed 4h bar is thin),
    its cost fields, `costs` (the regime whose cost and stress rules it uses: its own name, or `costs_of`) and a
    `label`. A `costs_of` scenario (severe) takes every cost field of the named one and only its own delays; it may
    not restate a cost field, so the two can never drift apart. Second-based keys are refused (they were truncated
    to whole seconds before ADR-0150)."""
    out = {}
    for name, s in raw.items():
        old = sorted(k for k in s if k in ("delay_s", "delay_thin_s"))
        if old:
            raise ValueError(f"scenario {name}: {old} are seconds; delays are configured as delay_ms (ADR-0150)")
        regime = s.get("costs_of", name)
        if regime not in REGIMES:
            raise ValueError(f"scenario {name}: unknown cost regime {regime!r}")
        if "costs_of" in s:
            src = raw[regime]
            if "costs_of" in src:
                raise ValueError(f"scenario {name}: {regime} itself borrows its costs")
            extra = sorted(set(s) - {"costs_of", "delay_ms", "delay_thin_ms", "label"})
            if extra:
                raise ValueError(f"scenario {name} takes its costs from {regime}; it may not set {extra}")
            costs = {k: src[k] for k in COST_FIELDS}
        else:
            costs = {k: s[k] for k in COST_FIELDS}
        delay, thin = s["delay_ms"], s.get("delay_thin_ms")
        for v in (delay, thin):
            if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v <= 0):
                raise ValueError(f"scenario {name}: delays are positive whole milliseconds (got {v!r})")
        if thin is not None and thin < delay:
            raise ValueError(f"scenario {name}: the thin-coin delay is shorter than the normal one")
        out[name] = {**costs, "delay_ms": delay, "delay_thin_ms": thin, "costs": regime,
                     "label": s.get("label", "measured")}
    return out


def main_delay(settings):
    """The delay key of a scenario's main run: an int (ms, every coin) or (normal_ms, thin_ms)."""
    thin = settings.get("delay_thin_ms")
    return settings["delay_ms"] if thin is None else (settings["delay_ms"], thin)


def delay_plan(scenarios, grid_ms):
    """The delays a window simulates, in order, each with the runs it serves: (delay, [(name, on_grid, main)]).

    Every grid point runs each scenario that owns a delay grid (its own cost regime); a scenario that borrows its
    costs (severe) shares that scenario's grid, so it runs only at its main delay. A main delay that is not a grid
    point (a thin-coin rule) gets its own frame after the grid. Every configured delay must be a grid point, so the
    aggTrades tape holds both endpoints of every order."""
    grid = [int(h) for h in grid_ms]
    for name, st in scenarios.items():
        for v in (st["delay_ms"], st.get("delay_thin_ms")):
            if v is not None and v not in grid:
                raise ValueError(f"scenario {name}: delay {v} ms is not a point of the delay grid {grid}")
    keys = [*grid, *dict.fromkeys(main_delay(st) for st in scenarios.values() if main_delay(st) not in grid)]
    plan = []
    for key in keys:
        runs = [(name, isinstance(key, int) and st["costs"] == name, main_delay(st) == key)
                for name, st in scenarios.items()]
        plan.append((key, [r for r in runs if r[1] or r[2]]))
    return plan


def grid_owner(name, settings):
    """The scenario whose delay grid `name` reports (its own, or its cost regime's)."""
    return settings.get("costs", name)


def regime(scenario, settings=None):
    """The cost regime a scenario prices with (severe -> stress); the ideal benchmarks keep their own names."""
    return (settings or {}).get("costs", scenario)


class Parameters:
    """Drift cells by (vintage, period, coin, band, horizon_ms). ADR-0120 stress fallback: `multiple` and the
    liquidity `edges` (completed 4h USDC volume) for parameterised stress orders without their own crash-sample
    cell."""

    def __init__(self, cells, multiple=3.0, edges=(250_000, 1_000_000, 5_000_000), short_bins=()):
        self.cells = {
            (v, p, c, b, h): (d, n)
            for v, p, c, b, h, d, n in cells.select(
                "origin", "period", "coin", "band", "horizon_ms", "mean_bps", "measured"
            ).iter_rows()
            if d is not None and math.isfinite(d)
        }
        self.stress_dates = set(cells.filter(C("period") == "stress")["origin"])
        self.multiple, self.edges = float(multiple), tuple(float(e) for e in edges)
        # ADR-0160: elapsed-time bins (upper edges, ms) of the split-order estimate; () = the ADR-0114 floor only
        self.short_bins = tuple(int(b) for b in short_bins)
        self.split_buckets = {(v, h) for v, p, c, b, h in self.cells
                              if c.startswith(SPLIT_PREFIX) and c != SPLIT_PREFIX + "all"}

    @classmethod
    def from_rules(cls, cells, rules):
        f = rules.get("stress_fallback") or {}
        s = rules.get("alt_short_floor") or {}
        bins = s.get("bins_ms", ()) if s.get("rule", "own_300s") == "hl_split_orders" else ()
        return cls(cells, f.get("multiple", 3.0), f.get("bucket_edges_usdc", (250_000, 1_000_000, 5_000_000)), bins)

    def short_bin(self, horizon):
        """ADR-0160: the right-closed bin (lo, hi] holding a delay, by its upper edge; None above the last bin."""
        lo = 0
        for hi in self.short_bins:
            if lo < horizon <= hi:
                return hi
            lo = hi
        return None

    def split_estimate(self, vintage, horizon, bucket, used):
        """ADR-0160 estimate for a base parameterised order: the order's bucket cell where the vintage has bucket cells
        for the bin, else the pooled cell; None (-> the ADR-0114 floor) without a bin or a cell."""
        hi = self.short_bin(horizon)
        if hi is None:
            return None
        coin = SPLIT_PREFIX + (bucket if (vintage, hi) in self.split_buckets else "all")
        found = self.cells.get((vintage, "development", coin, "all", hi))
        if found is None:
            return None
        used.append(["development", coin, "all", hi, found[0], found[1]])
        return found[0]

    def lookup(self, vintage, period, coin, band, horizon, conservative=False, bucket=None):
        """ADR-0080 parameter for one parameterised order; `horizon` in ms. `conservative` (the base scenario)
        bounds the sub-300 s four-coin proxy from below: by the ADR-0160 split-order estimate of the delay's bin and
        by zero where that estimate exists, else (ADR-0114) by the coin's own 300 s estimate and by zero, both
        required.
        Stress (ADR-0120): a missing own 300 s crash-sample cell becomes max(liquidity-bucket estimate,
        multiple x max(own 300 s development estimate, 0)); before any crash sample exists the four-coin stress proxy
        becomes multiple x max(development proxy, 0)."""
        used = []

        def cell(c, h, p=period):
            for b in (band, "all"):
                found = self.cells.get((vintage, p, c, b, h))
                if found is not None:
                    mean, n = found
                    used.append([p, c, b, h, mean, n])
                    return found
            return None

        def proxy(p=period):
            donors = [cell(c, horizon, p) for c in DIRECT]
            if all(x is not None for x in donors):
                return sum(d * n for d, n in donors) / sum(n for _, n in donors)
            return None

        def own_fallback():
            b = self.cells.get((vintage, "stress", f"bucket:{bucket}", "all", LONG_MS)) if bucket else None
            if b is not None:
                used.append(["stress", f"bucket:{bucket}", "all", LONG_MS, b[0], b[1]])
            dev = cell(coin, LONG_MS, "development")
            options = ([b[0]] if b is not None else []) + ([self.multiple * max(dev[0], 0.0)] if dev else [])
            return max([*options, 0.0]) if options else None  # an assumption, never a favourable drift

        method = "coin_approximate"
        value = None
        if horizon >= LONG_MS:
            own = cell(coin, horizon)
            if own:
                value = own[0]
            elif period == "stress":
                value, method = own_fallback(), "coin_fallback_max_bucket_3x_dev"
        else:
            value = proxy()
            method = "four_coin_proxy"
            if period == "stress":
                method = "stress_max_proxy_coin_300s"
                if value is None and vintage not in self.stress_dates:
                    dev = proxy("development")
                    value = self.multiple * max(dev, 0.0) if dev is not None else None
                    method += "|proxy=3x_dev"
                own = cell(coin, LONG_MS)
                own_value = own[0] if own else None
                if own_value is None:
                    own_value = own_fallback()
                    method += "|own=max_bucket_3x_dev"
                value = max(value, own_value) if value is not None and own_value is not None else None
            elif conservative:
                split = self.split_estimate(vintage, horizon, bucket, used)
                if split is not None:  # ADR-0160: the venue's own short-delay price, never favourable
                    method = "base_max_proxy_hlsplit_zero"
                    value = max(value, split, 0.0) if value is not None else None
                else:  # ADR-0114
                    own = cell(coin, LONG_MS)
                    method = "base_max_proxy_coin_300s_zero"
                    value = max(value, own[0], 0.0) if value is not None and own else None
        reason = (
            "stress_sample_unavailable" if period == "stress" and vintage not in self.stress_dates else "no_drift_cell"
        )
        return value, method, json.dumps(used, separators=(",", ":")), "" if value is not None else reason


def batches(fills, receive, debounce, start, end, ideal=False):
    """Non-sliding batch anchored at first reception. Source arrays follow the chain order."""
    f = fills.filter(C("event_ms").is_between(ms(start), ms(end), closed="left")).sort(*KEY, "oid", "event_ms", "seq")
    groups, last_key, anchor = [], None, 0
    for trader, coin, oid, t, seq in f.select(*KEY, "oid", "event_ms", "seq").iter_rows():
        key = (trader, coin, oid)
        if ideal or key != last_key or t > anchor + debounce:
            anchor, last_key, first_seq = t, key, seq
        groups.append(first_seq)
    f = f.with_columns(batch=pl.Series(groups, dtype=pl.Int64))
    out = (
        f.group_by(*KEY, "oid", "batch", maintain_order=True)
        .agg(
            C("event_ms").first().alias("event_ms"),
            C("event_ms").alias("source_event_ms"),
            C("src_row").alias("source_rows"),
            C("tid").alias("source_tids"),
            C("event_ms").last().alias("last_event_ms"),
            C("price").first().alias("anchor_px"),
            *([
                (C("size").abs()*C("price")).sum().alias("leader_notional"),
                ((C("size").abs()*C("price")).sum()/C("size").abs().sum()).alias("leader_vwap"),
                pl.when(C("side").first()=="buy").then(C("price").max()).otherwise(C("price").min()).alias("leader_deepest"),
            ] if "size" in f else []),
            # ADR-0112: forced fills have their own order ids, so a batch is either all forced or not at all.
            *([forced_fill().any().alias("forced")] if "dir" in f else []),
            C("side").first(),
            C("is_maker").first(),
            C("pos_after").last(),
            C("src_row").last().alias("target_row"),
        )
        .with_columns(last_visible_ms=C("last_event_ms") + receive, decision_ms=C("event_ms") + receive + debounce)
    )
    if ideal:
        return out.with_columns(visible_ms=C("last_visible_ms"))
    visible = fills.select(*KEY, "seq", "pos_after", visible_ms=C("event_ms") + receive, target_row="src_row").sort(
        "visible_ms", "seq"
    )
    return (
        out.drop("pos_after", "target_row")
        .sort("decision_ms")
        .join_asof(visible, on=None, left_on="decision_ms", right_on="visible_ms", by=KEY, check_sortedness=False)
    )


def order_inputs(batch, snaps, bars, checks, mapping, tape, bands, origins, spread, rules, start, end, delay):
    """All joins that drive a decision use decision time or earlier. Prints only drive the later fill.

    `delay` in whole ms (ADR-0150): 0 = the ideal benchmark, an int = every coin, (normal_ms, thin_ms) = the
    thin-coin rule on the latest completed 4h bar at decision. The acknowledgement is event_ms + delay_ms exactly."""
    if isinstance(delay, tuple):
        normal, thin = delay
    else:
        normal = thin = delay
    for v in (normal, thin):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"delays are whole milliseconds (got {delay!r})")
    ideal = delay == 0
    x = batch.sort("decision_ms").join_asof(
        snaps.sort("eq_ms", "equity_row"), left_on="decision_ms", right_on="eq_ms", by="trader", check_sortedness=False
    )
    x = x.join_asof(
        bars.sort("bar_ms"),
        left_on="decision_ms",
        right_on="bar_ms",
        by="coin",
        tolerance=4 * 3600 * 1000 - 1,
        check_sortedness=False,
    )
    # Thinness uses the last completed bar available at decision.
    h = (
        pl.when(C("bar_volume_usdc").is_null() | (C("bar_volume_usdc") < rules["thin_volume_usdc"]))
        .then(pl.lit(thin, pl.Int64))
        .otherwise(pl.lit(normal, pl.Int64))
        if thin != normal
        else pl.lit(normal, pl.Int64)
    )
    x = (
        x.with_columns(h.alias("delay_ms"))
        .with_columns(delay_s=C("delay_ms") / 1000, ack_ms=C("event_ms") + C("delay_ms"))
        .filter(C("ack_ms") < ms(end))
    )
    days = (C("decision_ms") // DAY).cast(pl.Date)
    vintage = days
    for origin in origins:
        vintage = pl.when(days >= origin).then(pl.lit(origin)).otherwise(vintage)
    x = (
        x.with_columns(
            vintage=vintage,
            a=pl.when(C("side") == "buy").then(1).otherwise(-1),
            m=pl.when("is_maker").then(-1).otherwise(1),
        )
        .join(
            bands.select("origin", "trader", "band").rename({"origin": "vintage"}), on=["vintage", "trader"], how="left"
        )
        .with_columns(C("band").fill_null("no_closed_trip"))
        .join(checks, on="coin", how="left")
        .join(mapping, on="coin", how="left")
        .join(spread.select("coin", "known_at", "cs_half_bps"), on="coin", how="left")
        .with_columns(cs_half_bps=pl.when(C("decision_ms") >= C("known_at").dt.epoch("ms")).then("cs_half_bps"))
    )
    for endpoint, tm in (("b0", "event_ms"), ("b1", "ack_ms")):
        p = tape.select(
            "coin",
            C("query").alias(tm),
            C("agg_trade_id").alias(endpoint + "_id"),
            C("transact_time").alias(endpoint + "_ms"),
            C("price").alias(endpoint),
            C("archive").alias(endpoint + "_file"),
        )
        x = x.join(p, on=["coin", tm], how="left")
    if ideal:
        x = x.with_columns(vintage=pl.lit(None, pl.Date))
    return x.sort(*KEY, "decision_ms", "batch", "oid")


SWEEP_ANCHOR = {"optimistic": None, "base": "leader_vwap", "stress": "leader_deepest"}


def sweep_anchor(frame, scenario):
    """ADR-0088: anchor a native taker batch at the book its own sweep left behind.

    Optimistic keeps the first fill (book refilled before the copy arrives); base uses the batch VWAP; stress
    uses the deepest fill (book not refilled). Makers and basket-only resize legs keep their anchor. The first
    fill, VWAP, deepest fill and signed first-to-deepest bps are recorded with the batch's source keys. A forced
    batch (ADL, liquidation, settlement; ADR-0112) is not the leader's sweep and keeps the first fill."""
    native = ~C("is_maker").fill_null(True)
    if "resize_leg" in frame:
        native = native & ~C("resize_leg")
    if "forced" in frame:
        native = native & ~C("forced").fill_null(False)
    a = pl.when(C("side") == "buy").then(1).otherwise(-1)
    x = frame.with_columns(
        leader_first_px=C("anchor_px"),
        sweep_bps=pl.when(native).then(a * (C("leader_deepest") / C("anchor_px") - 1) * BPS),
    )
    col = SWEEP_ANCHOR.get(scenario)
    if col is None:
        return x.with_columns(anchor_rule=pl.lit("first_fill"))
    use = native & C(col).is_not_null() & (C(col) > 0)
    return x.with_columns(
        anchor_px=pl.when(use).then(C(col)).otherwise("anchor_px"),
        anchor_rule=pl.when(use).then(pl.lit(col.removeprefix("leader_"))).otherwise(pl.lit("first_fill")),
    )


def quotes(frame, scenario, settings, params, sweep=False):
    """Reference prices at acknowledgement. The cost rules follow the scenario's regime (`settings["costs"]`): severe
    prices exactly as stress (stress-period drift and fallback, deepest sweep anchor), at its own delays."""
    ideal = scenario.startswith("unattainable")
    scenario = regime(scenario, settings)
    period = "stress" if scenario == "stress" else "development"
    major = C("coin").is_in(["BTC", "ETH"])
    w = settings["half_spread_bps"]
    configured = pl.when(major).then(w["majors"]).otherwise(w["other"])
    if sweep and not ideal:
        frame = sweep_anchor(frame, scenario)
    x = frame.with_columns(
        configured_half_bps=configured, half_bps=pl.lit(0.0) if ideal else pl.max_horizontal(configured, "cs_half_bps")
    )
    if "resize_leg" in frame:
        x = x.with_columns(
            m=pl.when("resize_leg").then(0).otherwise("m"), is_maker=pl.when(~C("resize_leg")).then("is_maker")
        )
    x = x.with_columns(mid_adjust_bps=-C("a") * C("m") * C("half_bps")).with_columns(
        mid_L=C("anchor_px") * (1 + C("mid_adjust_bps") / BPS)
    )
    # ADR-0120: the liquidity bucket of the latest completed 4h bar at the decision (used by the stress fallback).
    x = x.with_columns(liq_bucket=liquidity_bucket(C("bar_volume_usdc"), params.edges))
    keys = ["coin", "vintage", "band", "delay_ms", "liq_bucket"]
    values = []
    if not ideal:
        for coin, vintage, band, h, bucket in (
            x.filter((C("outcome") == "pass") & ~C("coin").is_in(DIRECT)).select(keys).unique().sort(keys).rows()
        ):
            found = params.lookup(vintage, period, coin, band, h, conservative=scenario == "base", bucket=bucket)
            values.append((coin, vintage, band, h, bucket, *found))
    schema = {
        **{k: x.schema[k] for k in keys},
        "mean_bps": pl.Float64,
        "method": pl.String,
        "parameter_cells": pl.String,
        "param_reason": pl.String,
    }
    x = x.join(pl.DataFrame(values, schema=schema, orient="row"), on=keys, how="left")
    direct = C("coin").is_in(DIRECT)
    valid = ((C("event_ms") // DAY).cast(pl.Date) >= C("valid_from")) & (
        (C("ack_ms") // DAY).cast(pl.Date) <= C("valid_to")
    )
    # ADR-0140: under the coin filter `outcome` is `coin_filter` for every coin outside the set and the price check's
    # own outcome is in `price_check_outcome`; without the filter both are the price check's.
    check = C("price_check_outcome") if "price_check_outcome" in x.columns else C("outcome")
    filtered = C("outcome") == "coin_filter"
    reason = (
        pl.when(filtered & (pl.lit(scenario == "unattainable_all") | (check == "pass")))
        .then(pl.lit("coin_filter_excluded"))
        .when((check.fill_null("unclassified") != "pass") & pl.lit(scenario != "unattainable_all"))
        .then(
            pl.when(check == "no_binance")
            .then(pl.lit("no_binance_mapping"))
            .when(check == "insufficient")
            .then(pl.lit("insufficient_price_check"))
            .otherwise(pl.lit("failed_price_check"))
        )
        .when(~valid.fill_null(False) & pl.lit(not ideal))
        .then(pl.lit("outside_mapping_window"))
        .when(
            pl.lit(not ideal)
            & direct
            & (
                C("b0").is_null()
                | C("b1").is_null()
                | (C("b1_ms") <= pl.max_horizontal("last_visible_ms", "visible_ms"))
            )
        )
        .then(pl.lit("no_eligible_aggtrade"))
        .when(pl.lit(not ideal) & ~direct & C("mean_bps").is_null())
        .then(C("param_reason"))
        .otherwise(pl.lit(""))
    )
    factor = pl.when(direct).then(C("b1") / C("b0")).otherwise(1 + C("a") * C("mean_bps") / BPS)
    return x.with_columns(
        price_reason=reason,
        period=pl.lit(period),
        price_source=pl.lit("leader_fill")
        if ideal
        else pl.when(direct).then(pl.lit("binance_aggtrade")).otherwise(pl.lit("parameterised")),
        ref_px=pl.when(reason == "").then(C("anchor_px") if ideal else C("mid_L") * factor),
        removed_basis_bps=pl.when(direct & pl.lit(not ideal)).then(
            (C("b0") * C("price_factor_hl_per_binance") / C("anchor_px") - 1) * BPS
        ),
    ).sort(*KEY, "decision_ms", "batch", "oid")


def square_root_bps(q, volume_daily, sigma_daily, y):
    if not volume_daily or volume_daily <= 0 or sigma_daily is None:
        return None
    return BPS * y * sigma_daily * math.sqrt(q / volume_daily)


def execute(frame, settings, rules, ideal=False, cap_marks=None):
    """Reserve submitted size until ack. A rejected fill releases its reservation only then.

    On the cap path a leg flagged `reduce_only` (ADR-0116: unusable equity at the latest review) may only move the
    follower's held-plus-pending position toward zero; an order that would add or flip risk is `reduce_only`."""
    cols = [
        "trader",
        "coin",
        "decision_ms",
        "ack_ms",
        "equity",
        "pos_after",
        "anchor_px",
        "ref_px",
        "price_reason",
        "half_bps",
        "bar_volume_usdc",
        "frozen",
    ]
    results = []
    previous = None
    pending: list[tuple[int, int, float]] = []
    cap = cap_marks is not None
    sqrt = "sqrt_y" in settings
    if cap:
        frame = frame.sort("trader", "decision_ms", "signal", "resize_leg", "coin", "batch")
        if "reduce_only" not in frame:
            frame = frame.with_columns(reduce_only=pl.lit(False))
        cols += ["capped_target", "decision_mark", "resize_leg", "mean_bps", "mid_L", "reduce_only"]
    constrained = "participation" in settings
    clips = []
    if constrained:
        cols.append("leader_notional")
    if sqrt:
        cols += ["volume_daily", "sigma_daily"]
    cap_audit = []
    retained = []
    for idx, row in enumerate(frame.select(cols).iter_rows()):
        tr, c, decision, ack, eq, pos, anchor, ref, reason, w, volume, frozen = row[:12]
        blocked = False
        if cap:
            if tr != previous:
                book = CapBook(cap_marks, rules["cap_usdc"])
                previous = tr
            book.advance(decision)
            target, mark, resize, d, mid, reduce_only = row[12:18]
            qty = book.size(c, target)
            if reduce_only and qty is not None:
                current = sum(book.states.get(c, (0.0, 0.0, 0.0)))
                if abs(current) < 1e-12 or qty * current > 0:
                    qty, blocked = 0.0, abs(qty) >= 1e-12
                elif abs(qty) > abs(current):
                    qty = -current  # close at most to flat, never flip
            if resize and (qty is None or abs(qty) < 1e-12):
                continue
            if resize and not reason and d is not None and qty and mid is not None:
                ref = mid * (1 + math.copysign(1, qty) * d / BPS)
            if constrained:
                # ADR-0086 participation budget on the latest completed 4h bar; ADR-0087 caps it at the
                # triggering leader batch's own notional. Both are USDC limits checked at decision and fill.
                requested = qty
                part = settings["participation"]
                if part is None:  # ADR-0117 surface point "none": no volume budget, the leader budget still applies
                    budget = math.inf
                else:
                    budget = volume * part if volume and volume > 0 else None
                leader_usdc = row[18]
                if budget is not None and settings["no_scale_up"]:
                    budget = min(budget, leader_usdc) if leader_usdc and leader_usdc > 0 else None
                if qty and budget is not None and mark:
                    qty = math.copysign(min(abs(qty), budget / mark), qty)
                submitted = qty
                if budget is None and not reason:
                    reason = "missing_order_budget" if settings["no_scale_up"] else "missing_participation_volume"
                clips.append((budget, requested, submitted))
            gross_before = None if book.missing else book.gross
            projected = book.reservation(c, qty, mark) if qty is not None else None
            retained.append(idx)
        else:
            if (tr, c) != previous:
                previous, committed, pending = (tr, c), 0.0, []
            while pending and pending[0][0] <= decision:
                committed -= heapq.heappop(pending)[2]
            qty = pos * rules["allocation_usdc"] / eq - committed if eq and eq > 0 and not frozen else None
        intended = abs(qty) * anchor if qty is not None and anchor is not None else None
        px, fee, impact = None, None, None
        if qty is None:
            reason = "missing_cap_mark" if cap and eq and eq > 0 and not frozen else "unusable_equity"
        elif abs(qty) < 1e-12:
            reason = "reduce_only" if blocked else "at_target"
        elif (
            reason not in EXCLUDED
            and intended is not None
            and intended < rules["min_notional_usdc"]
            and not ideal
        ):
            reason = "below_minimum"
        elif cap and reason not in EXCLUDED and projected is None:
            reason = "missing_cap_mark"
        elif (
            cap
            and reason not in EXCLUDED
            and projected > max(book.limit, book.gross) + 1e-8
        ):
            reason = "cap_headroom"
        elif not reason and not ideal and settings["impact"] != "none" and not volume and not sqrt:
            reason = "missing_impact_volume"
        if not reason:
            mult = {"none": 0, "linear": 1, "3x_base": 3}[settings["impact"]]
            if sqrt and mult:
                bps = square_root_bps(abs(qty) * ref, *row[-2:], settings["sqrt_y"])
                impact = None if bps is None else mult * bps
            else:
                impact = 0.0 if not mult else mult * BPS * abs(qty) * ref / volume
            if impact is None:
                reason = "missing_sqrt_inputs"
        if not reason:
            px = ref * (1 + math.copysign(1, qty) * (w + impact) / BPS)
            if constrained and budget is not None and abs(qty) * px > budget:
                # A quote-currency limit at fill. Shrink the order and reprice it with its own (square-root) impact.
                lo, hi = 0.0, 1.0
                for _ in range(45):
                    frac = (lo + hi) / 2
                    trial = ref * (1 + math.copysign(1, qty) * (w + impact * math.sqrt(frac)) / BPS)
                    if abs(qty) * frac * trial <= budget:
                        lo = frac
                    else:
                        hi = frac
                qty *= lo
                impact *= math.sqrt(lo)
                px = ref * (1 + math.copysign(1, qty) * (w + impact) / BPS)
            if px <= 0 or not math.isfinite(px):
                px, reason = None, "invalid_scenario_price"
            elif not ideal and abs(qty) * px < rules["min_notional_usdc"]:
                px, reason = None, "below_minimum_at_ack"
            else:
                fee = abs(qty) * px * settings["fee_bps"] / BPS
        if qty is not None and reason not in NOT_SUBMITTED:
            if cap:
                book.submit(c, submitted if constrained else qty, ack, idx, not reason, projected, mark, executed=qty)
            else:
                committed += qty
                if reason:
                    heapq.heappush(pending, (ack, idx, qty))
        if cap:
            cap_audit.append((gross_before, projected, None if book.missing else book.gross, ref))
        results.append((qty, intended, impact, px, fee, reason or "filled"))
    schema = {
        "quantity": pl.Float64,
        "intended_notional": pl.Float64,
        "impact_bps": pl.Float64,
        "fill_px": pl.Float64,
        "fee": pl.Float64,
        "status": pl.String,
    }
    if cap:
        frame = (
            frame[retained]
            .drop("ref_px")
            .hstack(
                pl.DataFrame(
                    cap_audit,
                    orient="row",
                    schema=dict.fromkeys(
                        ["reserved_gross_before", "proposed_gross", "reserved_gross_after", "ref_px"], pl.Float64
                    ),
                )
            )
        )
    if constrained:
        clip_schema = dict.fromkeys(["order_budget_usdc", "requested_qty", "submitted_qty"], pl.Float64)
        frame = frame.hstack(pl.DataFrame(clips, schema=clip_schema, orient="row"))
    return (
        frame.hstack(pl.DataFrame(results, schema=schema, orient="row"))
        .with_columns(shortfall_bps=(C("ref_px") / C("mid_L") - 1) * C("quantity").sign() * BPS)
        .sort(*KEY, "ack_ms", "decision_ms", "batch", "oid")
    )
