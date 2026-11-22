"""Position reconstruction per (trader, symbol) from fills, point in time.

`start_position` is the signed position *before* the fill; the fill's signed delta is +size (buy) or
-size (sell). Fills sharing a millisecond have no reliable order, so within each (trader, symbol, ms)
group we choose an order that forms a continuous chain:

* single-sided groups (all buys or all sells): order by signed start_position (ascending for buys,
  descending for sells);
* mixed groups: depth-first search for a feasible chain where each fill starts where the previous
  one ended (e.g. buy 2.1, buy 0.4372, then sell 2.5372 in one ms).

Continuity then checks start_position[i] == start_position[i-1] + delta[i-1] across the whole series.
Continuity shows the observed sequence is internally consistent; it cannot detect a round trip that
opens and closes between observed fills, activity before the first fill, or non-fill position changes.

Round trips run flat -> flat per coin. A fill that crosses zero closes one trip and opens the next.
A series whose first observed start_position is non-zero is left-censored (A06): its first trip has an
unknown entry, and its realized PnL cannot be rebuilt until the position is next flat.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

ABS_TOL = 1e-9
REL_TOL = 1e-9
MAX_DFS_STEPS = 200_000
SERIES = ["trader", "symbol"]


def close(a: float, b: float) -> bool:
    return abs(a - b) <= ABS_TOL + REL_TOL * max(abs(a), abs(b))


def is_flat(x: float) -> bool:
    return abs(x) <= ABS_TOL


def pit(df: pl.DataFrame, asof: datetime, col: str = "ts") -> pl.DataFrame:
    """Point-in-time filter: only rows with timestamp <= asof."""
    return df.filter(pl.col(col) <= asof)


# ---------------------------------------------------------------- ordering within a millisecond
def chain_order(starts: list[float], deltas: list[float], entry: float | None = None,
                exit_: float | None = None) -> list[int] | None:
    """Return an order (indices) forming a continuous chain, or None if none exists.

    `entry` is the position the group must start from (end of the previous fill in the series) and
    `exit_` the position it must end at (start of the next fill). A chain consistent with both is
    preferred; without hints, heads whose start is not another fill's end are tried first.
    """
    n = len(starts)
    ends = [s + d for s, d in zip(starts, deltas, strict=True)]

    def head_rank(i: int) -> tuple[int, int, int]:
        fits_entry = 0 if entry is None or close(starts[i], entry) else 1
        internal = int(any(close(starts[i], ends[j]) for j in range(n) if j != i))
        return (fits_entry, internal, i)

    heads = sorted(range(n), key=head_rank)
    if entry is not None:
        heads = [h for h in heads if close(starts[h], entry)] or heads
    fallback: list[int] | None = None
    steps = 0
    for h in heads:
        path, used = [h], [False] * n
        used[h] = True
        stack = [iter([j for j in range(n) if j != h and close(starts[j], ends[h])])]
        while stack:
            steps += 1
            if steps > MAX_DFS_STEPS:
                return fallback
            if len(path) == n:
                if exit_ is None or close(ends[path[-1]], exit_):
                    return list(path)
                fallback = fallback or list(path)
                stack.pop()
                used[path.pop()] = False
                continue
            nxt = next(stack[-1], None)
            if nxt is None:
                stack.pop()
                used[path.pop()] = False
                continue
            if used[nxt]:
                continue
            used[nxt] = True
            path.append(nxt)
            cur = ends[nxt]
            stack.append(iter([j for j in range(n) if not used[j] and close(starts[j], cur)]))
    return fallback


def order_fills(perp: pl.DataFrame) -> pl.DataFrame:
    """Add `group_kind`, `chain_resolved` and `seq` (order within series); sort by series, ts, seq."""
    df = perp.sort([*SERIES, "ts", "src_row"]).with_columns(
        g_n=pl.len().over([*SERIES, "ts"]),
        g_buys=(pl.col("side") == "buy").sum().over([*SERIES, "ts"]),
    ).with_columns(
        group_kind=pl.when(pl.col("g_n") == 1).then(pl.lit("single"))
        .when((pl.col("g_buys") == 0) | (pl.col("g_buys") == pl.col("g_n"))).then(pl.lit("one_sided"))
        .otherwise(pl.lit("mixed")),
        # one-sided key: buys ascending start, sells descending start
        okey=pl.when(pl.col("side") == "buy").then(pl.col("start_position")).otherwise(-pl.col("start_position")),
    )
    # Entry hint for mixed groups: end position of the previous fill in the same series.
    df = df.sort([*SERIES, "ts", "okey", "src_row"]).with_columns(
        _prev_end=(pl.col("start_position") + pl.col("delta")).shift().over(SERIES),
        _first=pl.int_range(pl.len()).over([*SERIES, "ts"]) == 0,
    )
    mixed = df.filter(pl.col("group_kind") == "mixed")
    rank_rows: list[tuple[int, int, bool]] = []
    if mixed.height:
        for _, g in mixed.group_by([*SERIES, "ts"], maintain_order=True):
            entry = g.filter(pl.col("_first"))["_prev_end"][0]
            # No exit hint: it would read the next fill, which may lie after asof (point in time).
            order = chain_order(g["start_position"].to_list(), g["delta"].to_list(), entry, None)
            rows = g["src_row"].to_list()
            if order is None:
                rank_rows += [(r, i, False) for i, r in enumerate(rows)]
            else:
                rank_rows += [(rows[k], pos, True) for pos, k in enumerate(order)]
    ranks = pl.DataFrame(rank_rows, schema={"src_row": pl.Int64, "mixed_rank": pl.Int64,
                                            "chain_resolved": pl.Boolean}, orient="row")
    df = df.join(ranks, on="src_row", how="left").with_columns(
        chain_resolved=pl.col("chain_resolved").fill_null(True),
        okey=pl.when(pl.col("group_kind") == "mixed").then(pl.col("mixed_rank").cast(pl.Float64))
        .otherwise(pl.col("okey")),
    )
    df = df.sort([*SERIES, "ts", "okey", "src_row"]).with_columns(
        seq=pl.int_range(pl.len()).over(SERIES).cast(pl.Int64)
    )
    return df.drop("g_n", "g_buys", "okey", "mixed_rank", "_prev_end", "_first")


def continuity(ordered: pl.DataFrame) -> pl.DataFrame:
    """Flag breaks: start_position differs from the previous fill's end position in the same series."""
    prev_end = (pl.col("start_position") + pl.col("delta")).shift().over(SERIES)
    gap = (pl.col("start_position") - prev_end).abs()
    tol = ABS_TOL + REL_TOL * pl.max_horizontal(pl.col("start_position").abs(), prev_end.abs())
    return ordered.with_columns(
        prev_end=prev_end,
        continuity_break=prev_end.is_not_null() & (gap > tol),
    )


# ---------------------------------------------------------------- positions, round trips, realized PnL
def rebuild(ordered: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Walk each series once. Returns (per-fill ledger, round trips).

    Per fill: pos_before, pos_after, trip_id (trip the fill's PnL belongs to), opens_trip, rebuilt_realized
    (average-cost realized PnL, null when the entry is unknown because of left-censoring).
    """
    cols = ordered.select("trader", "symbol", "ts", "src_row", "tid", "oid", "start_position", "delta", "price",
                          "closed_pnl", "fee", "notional")
    tr, sy, ts, sr = (cols[c].to_list() for c in ("trader", "symbol", "ts", "src_row"))
    tid, oid = cols["tid"].to_list(), cols["oid"].to_list()
    sp, de, px = cols["start_position"].to_list(), cols["delta"].to_list(), cols["price"].to_list()
    cp, fee, notional = cols["closed_pnl"].to_list(), cols["fee"].to_list(), cols["notional"].to_list()

    n = len(tr)
    pos_after = [0.0] * n
    trip_of = [0] * n
    realized: list[float | None] = [None] * n
    avg_before: list[float | None] = [None] * n
    trips: list[dict] = []

    cur_key: tuple[str, str] | None = None
    avg: float | None = None
    trip: dict | None = None
    counter = [0]

    def new_trip(i: int, sign: float, censored: bool) -> dict:
        no = counter[0]
        counter[0] += 1
        return {"trader": tr[i], "symbol": sy[i], "trip_no": no, "side": "long" if sign > 0 else "short",
                "open_ts": ts[i], "entry_src_row": sr[i], "entry_tid": tid[i], "entry_oid": oid[i],
                "left_censored": censored, "close_ts": None, "exit_src_row": None, "exit_tid": None,
                "exit_oid": None, "n_fills": 0, "max_abs_pos": 0.0, "closed_pnl": 0.0, "fees": 0.0,
                "rebuilt_realized": 0.0, "rebuilt_known": not censored, "notional": 0.0}

    for i in range(n):
        key = (tr[i], sy[i])
        pb, d = sp[i], de[i]
        pa = pb + d
        if key != cur_key:
            if trip is not None:
                trips.append(trip)
            cur_key, avg, counter[0] = key, None, 0
            trip = None if is_flat(pb) else new_trip(i, pb, censored=True)
        if trip is None and not is_flat(pb):  # position appeared without an observed open (break)
            trip, avg = new_trip(i, pb, censored=True), None
        avg_before[i] = avg
        r: float | None
        if is_flat(pb):  # open from flat
            trip = new_trip(i, d, censored=False)
            avg, r = px[i], 0.0
        elif (d > 0) == (pb > 0):  # increase
            avg = None if avg is None else (avg * abs(pb) + px[i] * abs(d)) / abs(pa)
            r = 0.0
        else:  # reduce, close or flip
            q = min(abs(d), abs(pb))
            r = None if avg is None else q * (px[i] - avg) * (1.0 if pb > 0 else -1.0)
        assert trip is not None
        trip["n_fills"] += 1
        trip["max_abs_pos"] = max(trip["max_abs_pos"], abs(pa) if not (pb * pa < 0) else abs(pb))
        trip["closed_pnl"] += cp[i]
        trip["fees"] += fee[i]
        trip["notional"] += notional[i]
        if r is None:
            trip["rebuilt_known"] = False
        else:
            trip["rebuilt_realized"] += r
        realized[i], trip_of[i], pos_after[i] = r, trip["trip_no"], pa
        crossed = (not is_flat(pb)) and (pb * pa < 0) and not is_flat(pa)
        if (not is_flat(pb)) and (is_flat(pa) or crossed):
            trip.update(close_ts=ts[i], exit_src_row=sr[i], exit_tid=tid[i], exit_oid=oid[i])
            trips.append(trip)
            trip, avg = None, None
            if crossed:
                trip = new_trip(i, pa, censored=False)
                avg = px[i]
        elif is_flat(pb) and is_flat(pa):
            trip = None  # zero-size fill from flat (should not occur)
    if trip is not None:
        trips.append(trip)

    ledger = ordered.with_columns(
        pos_before=pl.col("start_position"),
        pos_after=pl.Series(pos_after, dtype=pl.Float64),
        trip_no=pl.Series(trip_of, dtype=pl.Int64),
        avg_entry_before=pl.Series(avg_before, dtype=pl.Float64),
        rebuilt_realized=pl.Series(realized, dtype=pl.Float64),
    )
    trips_df = pl.DataFrame(trips, schema={
        "trader": pl.String, "symbol": pl.String, "trip_no": pl.Int64, "side": pl.String,
        "open_ts": pl.Datetime("ms", "UTC"), "entry_src_row": pl.Int64, "entry_tid": pl.Int64,
        "entry_oid": pl.Int64, "left_censored": pl.Boolean, "close_ts": pl.Datetime("ms", "UTC"),
        "exit_src_row": pl.Int64, "exit_tid": pl.Int64, "exit_oid": pl.Int64, "n_fills": pl.Int64,
        "max_abs_pos": pl.Float64, "closed_pnl": pl.Float64, "fees": pl.Float64, "rebuilt_realized": pl.Float64,
        "rebuilt_known": pl.Boolean, "notional": pl.Float64,
    })
    return ledger, trips_df
