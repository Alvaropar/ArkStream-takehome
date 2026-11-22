"""Address-wide target projection and exposure reservations for ADR-0085."""

import heapq
import math
from datetime import timedelta

import numpy as np
import polars as pl

from arkstream.prices import manifest_files
from arkstream.replay_market import ms

C = pl.col
MINUTE = 60_000
BAR = 240 * MINUTE


class MinuteMarks:
    """Observed approved minute closes indexed by close time. NaN represents an absent bar."""

    def __init__(self, first, last, coins):
        self.first = first // MINUTE
        self.values = {c: np.full(last // MINUTE - self.first + 1, np.nan) for c in coins}

    @classmethod
    def load(cls, path, start, end, coins):
        marks = cls(ms(start) - MINUTE, ms(end), coins)
        for file in manifest_files(path):
            rows = (
                pl.scan_parquet(file)
                .filter((C("ts") >= start - pl.duration(minutes=1)) & (C("ts") < end) & C("coin").is_in(coins))
                .select("coin", "price", minute=C("ts").dt.epoch("ms") // MINUTE)
                .collect()
            )
            for (coin,), group in rows.partition_by("coin", as_dict=True).items():
                marks.values[coin][group["minute"].to_numpy() - marks.first] = group["price"].to_numpy()
        return marks

    def at(self, coin, t):
        values = self.values.get(coin)
        minute = t // MINUTE - self.first
        if values is None or not 0 <= minute < len(values):
            return None
        price = values[minute]
        if not math.isfinite(price) and t % MINUTE == 0 and minute:
            price = values[minute - 1]
        return float(price) if math.isfinite(price) and price > 0 else None

    def source_ms(self, coin, t, price):
        if price is None:
            return None
        minute = t // MINUTE
        if not math.isfinite(self.values[coin][minute - self.first]):
            minute -= 1
        return minute * MINUTE


def impact_bars(candles, end, n):
    """One row per completed candle. Gaps invalidate each window that spans them."""
    b = (
        candles.filter((C("ts") <= end) & (C("n_trades") > 0))
        .sort("coin", "ts")
        .select(
            "coin",
            bar_ms=C("ts").dt.epoch("ms"),
            bar_volume_usdc=C("volume") * C("price"),
            close="price",
            volume_file="src_file",
        )
    )
    b = b.with_columns(
        ret=pl.when(
            (C("bar_ms").diff().over("coin") == BAR) & (C("close") > 0) & (C("close").shift().over("coin") > 0)
        ).then(C("close").log().diff().over("coin"))
    )
    return b.with_columns(
        volume_daily=pl.when(C("bar_ms") - C("bar_ms").shift(5).over("coin") == 5 * BAR).then(
            C("bar_volume_usdc").rolling_sum(6).over("coin")
        ),
        sigma_daily=C("ret").rolling_std(n, ddof=1).over("coin") * math.sqrt(6),
        volatility_start_ms=C("bar_ms").shift(n).over("coin"),
    ).drop("ret", "close")


def review_times(start, end, days):
    """ADR-0116: reviews at the window start (UTC midnight) and every `days` after it, before the window end."""
    out, r = [], start
    while r < end:
        out.append(ms(r))
        r += timedelta(days=days)
    return out


def reference_equity(snaps, traders, start, end, days):
    """ADR-0116: the frozen reference equity of each address between reviews, in the shape of `snaps`.

    At each review the latest snapshot with timestamp <= the review sets `E_ref` if usable (equity > 0, not frozen).
    An unusable one makes the address reduce-only until the next usable review; its targets keep the window's last
    usable `E_ref` (null before the first one, when there is nothing to reduce). Rows: trader, eq_ms (= review time),
    equity (sizing equity), frozen (False), equity_row (the snapshot behind the sizing equity), and the review's
    audit fields review_status, review_row, review_reduce_only and review_kind.

    ADR-0119: an address whose window-start review has no usable equity gets an extra first review at its first usable
    snapshot inside the window (at that snapshot's timestamp, when it is known); the 14-day schedule continues."""
    usable = (C("equity") > 0) & ~C("frozen").fill_null(False)
    ordered = snaps.sort("eq_ms", "equity_row")
    who = pl.DataFrame({"trader": sorted(set(traders))}, schema={"trader": pl.String})

    def at(reviews: pl.DataFrame) -> pl.DataFrame:
        return reviews.sort("review_ms").join_asof(ordered, left_on="review_ms", right_on="eq_ms", by="trader",
                                                   check_sortedness=False)

    schedule = who.join(pl.DataFrame({"review_ms": review_times(start, end, days)}, schema={"review_ms": pl.Int64}),
                        how="cross").with_columns(review_kind=pl.lit("schedule"))
    opening = at(schedule.filter(C("review_ms") == ms(start)))
    missing = opening.filter(~usable.fill_null(False)).select("trader")
    first = (snaps.join(missing, on="trader", how="semi")
             .filter((C("eq_ms") > ms(start)) & (C("eq_ms") < ms(end)) & usable.fill_null(False))
             .group_by("trader").agg(review_ms=C("eq_ms").min())
             .with_columns(review_kind=pl.lit("first_usable_snapshot")))
    reviews = pl.concat([schedule, first.select(schedule.columns)]).unique(["trader", "review_ms"], keep="first")
    grid = at(reviews).sort("trader", "review_ms")
    status = (pl.when(C("eq_ms").is_null()).then(pl.lit("missing")).when(C("frozen").fill_null(False))
              .then(pl.lit("frozen")).when(C("equity") <= 0).then(pl.lit("nonpositive")).otherwise(pl.lit("ok")))
    x = grid.with_columns(review_status=status, ok=usable.fill_null(False)).with_columns(
        ref=pl.when("ok").then("equity"), ref_row=pl.when("ok").then("equity_row"))
    x = x.with_columns(C("ref", "ref_row").forward_fill().over("trader"))
    return x.select(
        "trader", eq_ms="review_ms", equity="ref", frozen=pl.lit(False), equity_row="ref_row",
        review_status="review_status", review_row="equity_row", review_reduce_only=~C("ok"),
        review_kind="review_kind",
    ).sort("trader", "eq_ms")


def cap_legs(batch, events, snaps, marks, passing, allocation, limit, receive_ms, start, end, no_scale_up=False):
    """Expand each signal to the common scaled basket using only fills visible by its decision.

    `snaps` is the sizing equity: the latest usable snapshot (dynamic, ADR-0081) or the frozen reference table
    (`reference_equity`, ADR-0116), whose `review_reduce_only` flag marks every leg of a signal reduce-only."""
    b = (
        batch.sort("trader", "decision_ms", "coin", "batch", "oid")
        .with_row_index("signal")
        .sort("decision_ms")
        .join_asof(
            snaps.sort("eq_ms", "equity_row"),
            left_on="decision_ms",
            right_on="eq_ms",
            by="trader",
            check_sortedness=False,
        )
        .sort("signal")
    )
    if "review_reduce_only" not in b.columns:
        b = b.with_columns(review_reduce_only=pl.lit(False))
    part = (
        events.filter(C("event_ms").is_between(ms(start), ms(end), closed="left") & C("coin").is_in(sorted(passing)))
        .sort("trader", "event_ms", "coin", "seq")
        .select("trader", "event_ms", "coin", "pos_after", "src_row")
    )
    groups = part.partition_by("trader", as_dict=True)
    rows = []
    last = None
    for sig, tr, decision, c, equity, frozen, own_pos, trow, tvis, reduce_only in b.select(
        "signal", "trader", "decision_ms", "coin", "equity", "frozen", "pos_after", "target_row", "visible_ms",
        C("review_reduce_only").fill_null(False),
    ).iter_rows():
        if tr != last:
            book = {}
            previously_bound = False
            group = groups.get((tr,))
            it = (
                iter(group.select("event_ms", "coin", "pos_after", "src_row").iter_rows())
                if group is not None
                else iter(())
            )
            update = next(it, None)
            last = tr
        while update is not None and update[0] + receive_ms <= decision:
            t, symbol, pos, row = update
            book[symbol] = (pos, row, t + receive_ms)
            update = next(it, None)
        eq = equity if equity and equity > 0 and not frozen else None
        gross = 0.0
        mark_values = {}
        for symbol, (pos, _, _) in book.items():
            if pos:
                mark_values[symbol] = marks.at(symbol, decision)
                if mark_values[symbol] is None:
                    gross = None
                    break
                gross += abs(pos) * mark_values[symbol]
        capital = min(allocation, eq) if eq and no_scale_up else allocation
        multiplier = capital / eq if eq else None
        gross_usdc = gross * multiplier if gross is not None and multiplier is not None else None
        scale = min(1.0, limit / gross_usdc) if gross_usdc else (1.0 if gross_usdc == 0 else None)
        # Include prior zero targets during a basket resize: a rejected close may still be held.
        resize = scale is not None and (scale < 1 or previously_bound)
        coins = sorted(set(book) | {c}) if resize else [c]
        for symbol in coins:
            pos, row, vis = book.get(symbol, (own_pos, trow, tvis))
            mark = mark_values.get(symbol) or marks.at(symbol, decision)
            target = pos * multiplier if multiplier is not None else None
            rows.append(
                (
                    sig,
                    symbol,
                    row,
                    vis,
                    pos,
                    mark,
                    marks.source_ms(symbol, decision, mark),
                    gross_usdc,
                    scale,
                    target,
                    target * scale if target is not None and scale is not None else None,
                    symbol != c,
                    eq,
                    multiplier,
                    bool(reduce_only),
                )
            )
        if scale is not None:
            previously_bound = scale < 1
    schema = {
        "signal": pl.UInt32,
        "coin": pl.String,
        "target_row": pl.Int64,
        "visible_ms": pl.Int64,
        "pos_after": pl.Float64,
        "decision_mark": pl.Float64,
        "mark_ms": pl.Int64,
        "uncapped_gross_usdc": pl.Float64,
        "cap_scale": pl.Float64,
        "uncapped_target": pl.Float64,
        "capped_target": pl.Float64,
        "resize_leg": pl.Boolean,
        "sizing_equity": pl.Float64,
        "copy_multiplier": pl.Float64,
        "reduce_only": pl.Boolean,
    }
    plan = pl.DataFrame(rows, schema=schema, orient="row")
    parent = (
        batch.sort("trader", "decision_ms", "coin", "batch", "oid")
        .with_row_index("signal")
        .rename({"coin": "trigger_coin", "batch": "trigger_batch"})
        .drop("target_row", "visible_ms", "pos_after")
    )
    return (
        plan.join(parent, on="signal")
        .sort("signal", "coin")
        .with_row_index("batch")
        .with_columns(
            C("batch").cast(pl.Int64), anchor_px=pl.when("resize_leg").then("decision_mark").otherwise("anchor_px")
        )
    )


class CapBook:
    """Worst reachable gross across outstanding buys/sells, valued at this decision's marks."""

    def __init__(self, marks, limit):
        self.marks, self.limit = marks, limit
        self.states = {}  # actual signed size, reserved buys, reserved sells
        self.pending = []
        self.t = None
        self.prices = {}
        self.gross = 0.0
        self.missing = 0

    @staticmethod
    def envelope(state):
        held, buy, sell = state
        return max(abs(held + buy), abs(held + sell))

    def advance(self, t):
        if t == self.t:
            return
        while self.pending and self.pending[0][0] <= t:
            _, _, c, q, filled = heapq.heappop(self.pending)
            state = self.states[c]
            state[1 if q > 0 else 2] -= q
            state[0] += filled
            if max(map(abs, state)) < 1e-12:
                del self.states[c]
        self.t = t
        self.prices = {c: self.marks.at(c, t) for c in self.states}
        self.gross = sum(
            self.envelope(s) * self.prices[c] for c, s in self.states.items() if self.prices[c] is not None
        )
        self.missing = sum(self.prices[c] is None and self.envelope(s) > 1e-12 for c, s in self.states.items())

    def size(self, c, target):
        return target - sum(self.states.get(c, (0.0, 0.0, 0.0))) if target is not None else None

    def reservation(self, c, q, mark):
        if self.missing or mark is None:
            return None
        held, buy, sell = self.states.get(c, (0.0, 0.0, 0.0))
        before = self.envelope((held, buy, sell))
        after = self.envelope((held, buy + max(q, 0.0), sell + min(q, 0.0)))
        return self.gross + (after - before) * mark

    def submit(self, c, q, ack, serial, filled, gross, mark, executed=None):
        self.states.setdefault(c, [0.0, 0.0, 0.0])[1 if q > 0 else 2] += q
        self.prices[c] = mark
        self.gross = gross
        posted = (q if executed is None else executed) if filled else 0.0
        heapq.heappush(self.pending, (ack, serial, c, q, posted))
