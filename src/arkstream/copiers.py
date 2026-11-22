"""Copier / duplicate-operator screen, point in time.

An *order* is one (trader, oid) over perp trade fills, timed at its first fill. For an ordered pair
(leader L, follower F), a leader order is *matched* when F places an order in the same coin and side
strictly after it and within `window_s` seconds. match_share = matched leader orders / leader orders.

Confirmation evidence for a flagged pair:
* placebo: F's timestamps shifted by random constant offsets give the chance match rate;
* size ratio: F size / L size across matched orders (a copier has a stable ratio);
* lag distribution of matched orders.
A confirmed cluster is one bet: keep at most one member, preferably the original (the leader).
"""

from __future__ import annotations

from datetime import datetime

import duckdb
import numpy as np
import polars as pl

from arkstream.positions import pit


def orders(fills: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    f = pit(fills, asof).filter(pl.col("is_perp") & (pl.col("event_kind") == "trade"))
    return (f.sort("ts", "src_row").group_by("trader", "oid", maintain_order=True)
            .agg(ts=pl.col("ts").first(), coin=pl.col("symbol").first(), side=pl.col("side").first(),
                 size=pl.col("size").sum(), notional=pl.col("notional").sum(), n_fills=pl.len(),
                 first_src_row=pl.col("src_row").first())
            .sort("trader", "ts", "oid"))


def pair_matches(orders_df: pl.DataFrame, window_s: int) -> pl.DataFrame:
    """All (leader order, follower) matches, earliest follower order per (leader order, follower)."""
    con = duckdb.connect()
    con.register("o", orders_df.select("trader", "oid", "ts", "coin", "side", "size").to_arrow())
    q = f"""
        SELECT l.trader AS leader, f.trader AS follower, l.oid AS leader_oid,
               arg_min(f.oid, f.ts) AS follower_oid,
               min(f.ts) AS follower_ts, any_value(l.ts) AS leader_ts,
               any_value(l.coin) AS coin, any_value(l.side) AS side,
               any_value(l.size) AS leader_size, arg_min(f.size, f.ts) AS follower_size
        FROM o l JOIN o f
          ON l.coin = f.coin AND l.side = f.side AND l.trader <> f.trader
         AND f.ts > l.ts AND f.ts <= l.ts + INTERVAL {int(window_s)} SECOND
        GROUP BY 1, 2, 3
    """
    out = con.sql(q).pl()
    con.close()
    return out.with_columns(
        pl.col("leader_ts").dt.cast_time_unit("ms").dt.replace_time_zone("UTC"),
        pl.col("follower_ts").dt.cast_time_unit("ms").dt.replace_time_zone("UTC"),
    ).with_columns(lag_s=(pl.col("follower_ts") - pl.col("leader_ts")).dt.total_milliseconds() / 1000
    ).sort("leader", "follower", "leader_ts", "leader_oid")


def follower_spans(orders_df: pl.DataFrame, window_s: int) -> pl.DataFrame:
    """Window in which a follower could match: [first order - window_s, last order]."""
    return orders_df.group_by("trader").agg(
        f_first=pl.col("ts").min().dt.offset_by(f"-{int(window_s)}s"), f_last=pl.col("ts").max())


def pair_table(orders_df: pl.DataFrame, matches: pl.DataFrame, window_s: int) -> pl.DataFrame:
    """Per ordered pair: matched leader orders, share over the leader's full history, and share over the
    window where both are active (leader orders inside [follower first order - window, follower last order])."""
    n_orders = orders_df.group_by("trader").agg(leader_orders=pl.len())
    span = follower_spans(orders_df, window_s)
    ratio = (pl.col("follower_size") / pl.col("leader_size")).log()
    p = matches.group_by("leader", "follower").agg(
        matched=pl.len(),
        lag_p10=pl.col("lag_s").quantile(0.1), lag_p50=pl.col("lag_s").median(),
        lag_p90=pl.col("lag_s").quantile(0.9),
        log_size_ratio_median=ratio.median(),
        log_size_ratio_iqr=ratio.quantile(0.75) - ratio.quantile(0.25),
        first_leader_oid=pl.col("leader_oid").first(), first_follower_oid=pl.col("follower_oid").first(),
    ).join(span.rename({"trader": "follower"}), on="follower")
    # leader orders inside the follower's active span, via sorted search per leader
    ts_by_trader = {t: g["ts"].dt.epoch("ms").sort().to_numpy()
                    for (t,), g in orders_df.select("trader", "ts").group_by(["trader"])}
    overlap = []
    for leader, f_first, f_last in p.select("leader", "f_first", "f_last").iter_rows():
        arr = ts_by_trader[leader]
        lo = np.searchsorted(arr, int(f_first.timestamp() * 1000), side="left")
        hi = np.searchsorted(arr, int(f_last.timestamp() * 1000), side="right")
        overlap.append(int(hi - lo))
    p = p.with_columns(leader_orders_overlap=pl.Series(overlap, dtype=pl.Int64))
    return (p.join(n_orders.rename({"trader": "leader"}), on="leader")
            .with_columns(match_share_full=pl.col("matched") / pl.col("leader_orders"),
                          match_share=pl.col("matched") / pl.col("leader_orders_overlap"))
            .sort("match_share", "leader", "follower", descending=[True, False, False]))


def clusters(confirmed: pl.DataFrame) -> pl.DataFrame:
    """Connected components over confirmed pairs (undirected). The proposed 'original' is the member
    whose orders are most matched by others (ties: lexicographic address)."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a_, b_ in confirmed.select("leader", "follower").iter_rows():
        ra, rb = find(a_), find(b_)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    members = sorted(parent)
    if not members:
        return pl.DataFrame(schema={"trader": pl.String, "cluster_id": pl.String, "cluster_size": pl.Int64,
                                    "times_followed": pl.Int64, "is_original": pl.Boolean})
    df = pl.DataFrame({"trader": members, "root": [find(m) for m in members]})
    led = confirmed.group_by("leader").agg(times_followed=pl.col("matched").sum()).rename({"leader": "trader"})
    df = df.join(led, on="trader", how="left").with_columns(pl.col("times_followed").fill_null(0))
    df = df.with_columns(cluster_id=pl.col("root"), cluster_size=pl.len().over("root").cast(pl.Int64))
    df = df.sort(["cluster_id", "times_followed", "trader"], descending=[False, True, False]).with_columns(
        is_original=pl.int_range(pl.len()).over("cluster_id") == 0)
    return df.select("trader", "cluster_id", "cluster_size", "times_followed", "is_original")


def match_share_shifted(leader_o: pl.DataFrame, follower_o: pl.DataFrame, window_s: int, shift_ms: int) -> float:
    """Share of leader orders matched when the follower's timestamps are shifted by shift_ms."""
    lo = leader_o.select("ts", "coin", "side").sort("ts")
    fo = follower_o.select(pl.col("ts").dt.offset_by(f"{shift_ms}ms").alias("f_ts"), "coin", "side").sort("f_ts")
    j = lo.join_asof(fo, left_on="ts", right_on="f_ts", by=["coin", "side"], strategy="forward",
                     tolerance=f"{window_s}s", allow_exact_matches=False, check_sortedness=False)
    return float(j["f_ts"].is_not_null().sum()) / lo.height if lo.height else 0.0


def placebo(orders_df: pl.DataFrame, pairs: pl.DataFrame, window_s: int, n_shifts: int, max_shift_s: int,
            seed: int) -> pl.DataFrame:
    """Chance match rate for each pair from random constant shifts (|shift| >= 10 * window), measured on
    leader orders inside the follower's active span (same base as match_share). Seeded per pair, so
    the result does not depend on which other pairs are screened."""
    rows = []
    for leader, follower, f_first, f_last in pairs.select("leader", "follower", "f_first", "f_last").iter_rows():
        rng = np.random.default_rng([seed, int(leader[2:10], 16), int(follower[2:10], 16)])
        lo = orders_df.filter((pl.col("trader") == leader) & pl.col("ts").is_between(f_first, f_last))
        fo = orders_df.filter(pl.col("trader") == follower)
        mags = rng.integers(10 * window_s * 1000, max_shift_s * 1000, size=n_shifts)
        signs = rng.choice([-1, 1], size=n_shifts)
        shares = [match_share_shifted(lo, fo, window_s, int(m * s)) for m, s in zip(mags, signs, strict=True)]
        rows.append({"leader": leader, "follower": follower, "placebo_mean": float(np.mean(shares)),
                     "placebo_p95": float(np.quantile(shares, 0.95)), "placebo_max": float(np.max(shares))})
    return pl.DataFrame(rows, schema={"leader": pl.String, "follower": pl.String, "placebo_mean": pl.Float64,
                                      "placebo_p95": pl.Float64, "placebo_max": pl.Float64})


def screen(fills: pl.DataFrame, asof: datetime, cfg: dict) -> dict[str, pl.DataFrame]:
    o = orders(fills, asof)
    m = pair_matches(o, cfg["window_s"])
    pairs = pair_table(o, m, cfg["window_s"])
    cand = pairs.filter((pl.col("leader_orders_overlap") >= cfg["min_orders_leader"])
                        & (pl.col("match_share") >= cfg["min_match_share"]))
    pl_df = placebo(o, cand, cfg["window_s"], cfg["placebo_shifts"], cfg["placebo_max_shift_s"], cfg["seed"])
    flagged = cand.join(pl_df, on=["leader", "follower"], how="left").with_columns(
        excess_over_placebo=pl.col("match_share") - pl.col("placebo_p95"),
        confirmed=(pl.col("match_share") > cfg["placebo_multiple"] * pl.col("placebo_p95"))
        & (pl.col("match_share") >= cfg["min_match_share"]),
    ).sort("match_share", "leader", "follower", descending=[True, False, False])
    cl = clusters(flagged.filter(pl.col("confirmed")))
    return {"orders": o, "matches": m, "pairs": pairs, "flagged": flagged, "clusters": cl}
