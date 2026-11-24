"""Bounded replay inputs and backwards aggTrade lookups at both endpoints (ADR-0029)."""

import csv
import io
import zipfile
from datetime import UTC, date, datetime, timedelta

import polars as pl

from arkstream import drift, positions
from arkstream.config import load_instruments, load_yaml
from arkstream.instruments import annotate_fills, forced_fill
from arkstream.pipeline import Inputs, processed_dir
from arkstream.prices import scan_reference
from arkstream.provenance import sha256_file

C = pl.col
DAY = 86_400_000
DIRECT = ("BTC", "ETH", "HYPE", "SOL")
LONG_MS = 300_000  # the approximate method's (and the stress buckets') horizon, ms


def midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), UTC)


def ms(t: datetime) -> int:
    return int(round(t.timestamp() * 1000))


def bounded_inputs(ctx, stop):
    def read(kind):
        paths = [
            p
            for p in sorted((processed_dir(ctx) / kind).glob("date=*/*.parquet"))
            if date.fromisoformat(p.parent.name[5:]) < stop.date()
        ]
        return pl.scan_parquet(paths, hive_partitioning=True).filter(C("ts") < stop).collect().sort("src_row")

    return Inputs(read("traders"), annotate_fills(read("fills"), load_instruments(ctx.root / "config")))


def tape_day(directory, row):
    if row is None or not (directory / row["file"]).is_file():
        return None
    path = directory / row["file"]
    if sha256_file(path) != row["published_sha256"]:
        raise ValueError(f"aggTrades checksum mismatch: {path}")
    with zipfile.ZipFile(path) as z:
        raw = z.read(z.namelist()[0])
    header = raw[:12].lower().startswith(b"agg_trade_id")
    names = ["agg_trade_id", "price", "transact_time"]
    trades = pl.read_csv(
        io.BytesIO(raw),
        has_header=header,
        columns=names if header else [0, 1, 5],
        new_columns=None if header else names,
        schema_overrides=None if not header else {"price": pl.Float64},
    )
    trades = trades.select("agg_trade_id", C("price").cast(pl.Float64), "transact_time").sort(
        "transact_time", "agg_trade_id"
    )
    return trades


def trade_queries(ctx, fills, rules, stop, basket=False, holdout=False):
    """Materialize only requested timestamps, retaining source IDs. Never open a holdout zip unless `holdout` and the
    freeze holds (ADR-A0139/A0141: `freeze.guard`). Queries are each leader event and event + every drift horizon, in
    whole ms (ADR-0058: 1.2 s is +1,200 ms)."""
    if stop > midnight(rules.holdout_start):
        if not holdout:
            raise drift.HoldoutLeak("replay ends at the holdout boundary")
        from arkstream.freeze import guard

        guard(ctx, stop)
    directory = ctx.path("aggtrades_dir")
    with (directory / "MANIFEST.csv").open(encoding="utf8", newline="") as f:
        files = {(r["symbol"], r["date"]): r for r in csv.DictReader(f)}
    frames = []
    for coin, symbol in sorted(rules.aggtrades_symbols.items()):
        own = fills.filter(C("symbol") == coin)
        signals = fills.join(own.select("trader").unique(), on="trader", how="semi") if basket else own
        events = signals.select(query=C("ts").dt.epoch("ms")).unique()
        queries = (
            pl.concat([events + offset for offset in sorted({0, *rules.horizons_ms})])
            .unique()
            .filter(C("query").is_between(ms(midnight(rules.est_start)), ms(stop), closed="left"))
            .sort("query")
        )
        tail = None
        prev_day = None
        for (day_no,), q in queries.group_by(C("query") // DAY, maintain_order=True):
            day = date.fromordinal(date(1970, 1, 1).toordinal() + day_no)
            trades = tape_day(directory, files.get((symbol, day.isoformat())))
            if trades is None:
                tail = None
                continue
            # A query in the first second may need yesterday's last print even if
            # yesterday itself contained no leader signals.
            if (
                prev_day != day_no - 1
                and day > rules.est_start
                and q["query"][0] - day_no * DAY <= rules.max_staleness_s * 1000
            ):
                prior = tape_day(directory, files.get((symbol, (day - timedelta(days=1)).isoformat())))
                tail = prior.tail(1) if prior is not None else None
                prev_day = day_no - 1
            if tail is not None and prev_day == day_no - 1:
                trades = pl.concat([tail, trades])
            tail, prev_day = trades.tail(1), day_no
            found = q.join_asof(
                trades, left_on="query", right_on="transact_time", tolerance=int(rules.max_staleness_s * 1000)
            ).drop_nulls()
            print_day = pl.from_epoch(C("transact_time"), time_unit="ms").dt.strftime("%Y-%m-%d")
            frames.append(
                found.with_columns(
                    coin=pl.lit(coin),
                    archive=pl.concat_str(pl.lit(f"{symbol}/{symbol}-aggTrades-"), print_day, pl.lit(".zip")),
                )
            )
    if not frames:
        return pl.DataFrame(
            schema={
                "query": pl.Int64,
                "agg_trade_id": pl.Int64,
                "price": pl.Float64,
                "transact_time": pl.Int64,
                "coin": pl.String,
                "archive": pl.String,
            }
        )
    return pl.concat(frames).sort("coin", "query")


def vintages(ctx, inputs, rules, tape, asof):
    """Daily, strictly earlier calibration during warm-up, then published origin tables. ADR-0044: a coin's cells
    exist at a vintage only if the coin passes the price check as of that vintage (its 00:00 UTC)."""
    from arkstream.config import research_dir
    from arkstream.hlprices import PointInTimeCheck

    root = research_dir(ctx, "drift")
    hist = pl.concat([pl.read_csv(root / f"drift_{p}.csv", try_parse_dates=True) for p in ("development", "stress")])
    bands = pl.read_csv(root / "drift_hold_bands.csv", try_parse_dates=True)
    end = midnight(rules.origin_dates[0])
    early = inputs.fills.filter(C("ts") < min(end, asof))
    orders = drift.leader_orders(early, midnight(rules.est_start), end - timedelta(milliseconds=1))
    other = orders.filter(~C("coin").is_in(DIRECT))
    checker = PointInTimeCheck.load(ctx)
    warm = []
    day = rules.est_start + timedelta(days=1)
    while day < end.date() and midnight(day) <= asof:
        warm.append(day)
        day += timedelta(days=1)
    vintage_days = sorted({*warm, *(o for o in rules.origin_dates if midnight(o) <= asof)})
    allowed = pl.concat([
        pl.DataFrame({"origin": [v] * len(p), "coin": p}, schema={"origin": pl.Date, "coin": pl.String})
        for v in vintage_days for p in [checker.passing(midnight(v))]
    ])
    passing = allowed.select("coin").unique().sort("coin")
    ref = scan_reference(ctx.path("reference_prices_dir"))
    apx = drift.approx_drift(
        other.join(passing, on="coin"),
        ref,
        early,
        rules,
        [LONG_MS],
        ctx.raw["reference_prices"]["max_age_s"],
        ctx.raw["reference_prices"]["fallback_print_window_s"],
    )
    direct = orders.filter(C("coin").is_in(DIRECT)).with_columns(query=C("t").dt.epoch("ms"))
    px = tape.select("coin", "query", "price")
    direct = direct.join(px, on=["coin", "query"]).rename({"price": "b0"})
    pieces = [apx.select("trader", "coin", "t", "day", "horizon_ms", "drift_bps", "source", "reason")]
    for h in rules.horizons_ms:
        j = direct.with_columns(query=C("query") + h).join(px, on=["coin", "query"])
        pieces.append(
            j.select(
                "trader",
                "coin",
                "t",
                "day",
                horizon_ms=pl.lit(h, pl.Int64),
                drift_bps=C("sign") * (C("price") / C("b0") - 1) * 1e4,
                source=pl.lit("aggtrades"),
                reason=pl.lit(""),
            )
        )
    per = pl.concat(pieces, how="vertical_relaxed")
    perp = early.filter(C("is_perp") & (C("event_kind") == "trade"))
    _, trips = positions.rebuild(positions.continuity(positions.order_fills(perp)))
    trips = trips.with_columns(hold_s=(C("close_ts") - C("open_ts")).dt.total_milliseconds() / 1000)
    cols = ["origin", "period", "source", "coin", "band", "horizon_ms", "measured", "mean_bps"]
    tables, band_tables = [hist.select(cols)], [bands]
    for day in warm:
        band = (
            trips.filter(C("close_ts") < midnight(day))
            .group_by("trader")
            .agg(median_hold_s=C("hold_s").median(), closed_trips=pl.len())
            .with_columns(band=drift.band_expr("median_hold_s"), origin=pl.lit(day))
        )
        cell = drift.pool(drift.at_origin(per, day), band, rules, "development").with_columns(origin=pl.lit(day))
        tables.append(cell.select(cols))
        band_tables.append(band.select(bands.columns))
    cells = pl.concat(tables, how="vertical_relaxed").filter(C("origin") <= asof.date())
    cells = cells.join(allowed, on=["origin", "coin"], how="semi")
    replay_cfg = load_yaml("execution.yaml", ctx.root / "config")["replay"]
    fallback = replay_cfg["stress_fallback"]
    buckets = stress_bucket_cells(ctx, inputs, rules, checker, ref, asof, fallback)
    split = short_floor_cells(ctx, inputs, rules, checker, vintage_days, asof, replay_cfg.get("alt_short_floor") or {},
                              fallback["bucket_edges_usdc"])
    return (
        pl.concat([cells, buckets.select(cols), split.select(cols)], how="vertical_relaxed").sort(cols[:6]),
        pl.concat(band_tables, how="vertical_relaxed").filter(C("origin") <= asof.date()).sort("origin", "trader"),
    )


def _usd(v: float) -> str:
    return f"{v / 1e6:g}M" if v >= 1e6 else f"{v / 1e3:g}k"


def bucket_labels(edges) -> list[str]:
    e = [float(x) for x in edges]
    return [f"<{_usd(e[0])}", *[f"{_usd(a)}-{_usd(b)}" for a, b in zip(e, e[1:], strict=False)], f">={_usd(e[-1])}"]


def liquidity_bucket(volume: pl.Expr, edges) -> pl.Expr:
    """ADR-0053: the USDC volume bucket of the latest completed Hyperliquid 4h bar; `unknown` when there is none."""
    labels = bucket_labels(edges)
    e: pl.Expr = pl.lit(labels[-1])
    for edge, label in reversed(list(zip(edges, labels[:-1], strict=True))):
        e = pl.when(volume < float(edge)).then(pl.lit(label)).otherwise(e)
    return pl.when(volume.is_not_null()).then(e).otherwise(pl.lit("unknown"))


def pool_buckets(obs: pl.DataFrame, passing_by_vintage: dict, edges, min_orders: int) -> pl.DataFrame:
    """Per vintage and liquidity bucket: the mean signed 300 s drift of crash-sample observations on coins passing
    at that vintage and ending before it. Buckets with fewer than `min_orders` measured orders get no row."""
    rows = []
    o = obs.filter(C("drift_bps").is_not_null()).with_columns(bucket=liquidity_bucket(C("bar_volume_usdc"), edges))
    o = o.filter(C("bucket") != "unknown").sort("t", "trader", "coin")
    for vintage, passing in sorted(passing_by_vintage.items()):
        end = midnight(vintage)
        use = o.filter(C("coin").is_in(sorted(passing)) & ((C("t") + pl.duration(milliseconds=LONG_MS)) < end))
        g = use.group_by("bucket", maintain_order=True).agg(measured=pl.len(), mean_bps=C("drift_bps").mean())
        g = g.filter(C("measured") >= min_orders)
        rows.append(g.select(origin=pl.lit(vintage), period=pl.lit("stress"), source=pl.lit("bucket"),
                             coin=pl.lit("bucket:") + C("bucket"), band=pl.lit("all"), horizon_ms=pl.lit(LONG_MS),
                             measured="measured", mean_bps="mean_bps"))
    schema = pl.Schema([("origin", pl.Date()), ("period", pl.String()), ("source", pl.String()),
                        ("coin", pl.String()), ("band", pl.String()), ("horizon_ms", pl.Int64()),
                        ("measured", pl.UInt32()), ("mean_bps", pl.Float64())])
    return pl.concat(rows, how="vertical_relaxed").cast(schema) if rows else pl.DataFrame(schema=schema)


SPLIT_SOURCE = "hl_split_orders"
CELL_SCHEMA = pl.Schema([("origin", pl.Date()), ("period", pl.String()), ("source", pl.String()),
                         ("coin", pl.String()), ("band", pl.String()), ("horizon_ms", pl.Int64()),
                         ("measured", pl.UInt32()), ("mean_bps", pl.Float64())])
SPLIT_PREFIX = "hlsplit:"


def split_order_observations(fills: pl.DataFrame, gap_ms: int, start: datetime, exclude) -> pl.DataFrame:
    """ADR-0061 evidence: one row per later child of a split leader trade on Hyperliquid (taker orders of the same
    trader, coin and side, each at most `gap_ms` after the previous one; forced fills excluded). `move_bps`: the
    child's best (first) fill vs the first order's VWAP, signed (positive = worse for a copier on the leader's side).
    An observation whose first order or own order falls on an `exclude` day (the stress days) is left out; orders
    before `start` are not read."""
    f = fills.filter(C("eligible") & (C("event_kind") == "trade") & ~C("is_maker") & ~forced_fill()
                     & (C("ts") >= start))
    o = (
        f.sort("ts", "src_row")
        .group_by("trader", "oid")
        .agg(
            coin=C("symbol").first(), side=C("side").first(), t_ms=C("ts").min().dt.epoch("ms"),
            notional=(C("size").abs() * C("price")).sum(), qty=C("size").abs().sum(),
            best=pl.when(C("side").first() == "buy").then(C("price").min()).otherwise(C("price").max()),
            src_row=C("src_row").min(),
        )
        .with_columns(vwap=C("notional") / C("qty"), sign=pl.when(C("side") == "buy").then(1).otherwise(-1),
                      day=pl.from_epoch("t_ms", time_unit="ms").dt.date())
        .sort("trader", "coin", "t_ms", "src_row")
    )
    o = o.with_columns(prev_t=C("t_ms").shift().over("trader", "coin"),
                       prev_side=C("side").shift().over("trader", "coin"))
    o = o.with_columns(new=(C("prev_t").is_null() | (C("t_ms") - C("prev_t") > gap_ms)
                            | (C("side") != C("prev_side"))).fill_null(True))
    o = o.with_columns(seq=C("new").cast(pl.Int64).cum_sum().over("trader", "coin"))
    o = o.with_columns(k=pl.int_range(pl.len()).over("trader", "coin", "seq"))
    first = o.filter(C("k") == 0).select("trader", "coin", "seq", t0_ms="t_ms", vwap0="vwap", day0="day")
    off = sorted(exclude)
    later = o.filter(C("k") > 0).join(first, on=["trader", "coin", "seq"]).filter(
        ~C("day").is_in(off) & ~C("day0").is_in(off))
    return later.select(
        "trader", "coin", "seq", "k", "oid", "src_row", "t0_ms", "t_ms",
        elapsed_ms=C("t_ms") - C("t0_ms"),
        move_bps=C("sign") * (C("best") / C("vwap0") - 1) * 1e4,
    ).sort("t_ms", "trader", "coin", "k")


def split_order_cells(obs: pl.DataFrame, passing_by_vintage: dict, bins_ms, edges, min_orders: int) -> pl.DataFrame:
    """ADR-0061: per vintage and elapsed-time bin (right-closed, keyed by its upper edge in ms), the mean move of
    later child orders on parameterised coins passing at that vintage, both orders strictly before it. By liquidity
    bucket (of the first order) only if every bucket has `min_orders` observations in the bin; else pooled
    (`hlsplit:all`); a cell below `min_orders` gets no row."""
    labels = bucket_labels(edges)
    lows = [0, *bins_ms[:-1]]
    o = obs.filter(~C("coin").is_in(DIRECT)).with_columns(bucket=liquidity_bucket(C("bar_volume_usdc"), edges))
    binned = pl.lit(None, pl.Int64)
    for lo, hi in reversed(list(zip(lows, bins_ms, strict=True))):
        binned = pl.when((C("elapsed_ms") > lo) & (C("elapsed_ms") <= hi)).then(pl.lit(hi, pl.Int64)).otherwise(binned)
    o = o.with_columns(horizon_ms=binned).filter(C("horizon_ms").is_not_null())
    rows = []
    for vintage, passing in sorted(passing_by_vintage.items()):
        end = ms(midnight(vintage))
        use = o.filter(C("coin").is_in(sorted(passing)) & (C("t_ms") < end))
        for hi in bins_ms:
            b = use.filter(C("horizon_ms") == hi)
            per = b.group_by("bucket").agg(measured=pl.len(), mean_bps=C("move_bps").mean())
            counts = dict(per.select("bucket", "measured").iter_rows())
            if all(counts.get(lab, 0) >= min_orders for lab in labels):
                for lab in labels:
                    m = per.filter(C("bucket") == lab).row(0, named=True)
                    rows.append((vintage, SPLIT_PREFIX + lab, hi, m["measured"], m["mean_bps"]))
            elif b.height >= min_orders:
                rows.append((vintage, SPLIT_PREFIX + "all", hi, b.height, b["move_bps"].mean()))
    if not rows:
        return pl.DataFrame(schema=CELL_SCHEMA)
    df = pl.DataFrame(rows, schema=["origin", "coin", "horizon_ms", "measured", "mean_bps"], orient="row")
    return df.select(
        "origin", period=pl.lit("development"), source=pl.lit(SPLIT_SOURCE), coin="coin", band=pl.lit("all"),
        horizon_ms="horizon_ms", measured="measured", mean_bps="mean_bps",
    ).cast(CELL_SCHEMA)


def hl_bars(ctx, asof) -> pl.DataFrame:
    """Completed Hyperliquid 4h bars with USDC volume, as ADR-0053 reads them."""
    from arkstream import hlprices

    candles, _ = hlprices.load_candles(ctx.path("hyperliquid_dir"), min(asof, ctx.cutoff))
    return candles.filter(C("n_trades") > 0).select("coin", bar_ms=C("ts").dt.epoch("ms"),
                                                    bar_volume_usdc=C("volume") * C("price")).sort("bar_ms")


def with_bar(obs: pl.DataFrame, bars: pl.DataFrame, at: str) -> pl.DataFrame:
    return obs.sort(at).join_asof(bars, left_on=at, right_on="bar_ms", by="coin", tolerance=4 * 3600 * 1000 - 1,
                                  check_sortedness=False)


def short_floor_cells(ctx, inputs, rules, checker, vintage_days, asof, cfg, edges) -> pl.DataFrame:
    """ADR-0061 cells for every vintage (`replay.alt_short_floor`); none when the rule is the ADR-0048 one."""
    if cfg.get("rule", "own_300s") != "hl_split_orders":
        return pl.DataFrame(schema=CELL_SCHEMA)
    obs = split_order_observations(inputs.fills.filter(C("ts") < asof), int(cfg["sequence_gap_ms"]),
                                   midnight(rules.est_start), rules.exclude)
    obs = with_bar(obs, hl_bars(ctx, asof), "t0_ms")
    passing_by = {v: set(checker.passing(midnight(v))) for v in vintage_days}
    return split_order_cells(obs, passing_by, [int(b) for b in cfg["bins_ms"]], edges, int(cfg["min_orders"]))


def stress_bucket_cells(ctx, inputs, rules, checker, ref, asof, fallback) -> pl.DataFrame:
    """ADR-0053: liquidity-bucket stress cells from the 10-11 Oct sample (forced fills excluded, approximate 300 s
    drift on parameterised coins, bucket by the coin's latest completed Hyperliquid 4h bar at the order)."""
    from arkstream import hlprices

    days = sorted(rules.stress)
    vintages_after = [o for o in rules.origin_dates if o > days[-1] and midnight(o) <= asof]
    passing_by = {o: set(checker.passing(midnight(o))) for o in vintages_after}
    if not passing_by:
        return pool_buckets(pl.DataFrame(schema={"t": pl.Datetime("ms", "UTC")}), {}, fallback["bucket_edges_usdc"],
                            fallback["min_orders"])
    lo = midnight(days[0]) - timedelta(days=rules.basis_window_days - 1)  # the venue basis needs its trailing days
    hi = midnight(days[-1] + timedelta(days=1)) - timedelta(milliseconds=1)
    orders = drift.leader_orders(inputs.fills, lo, hi)
    union = sorted(set().union(*passing_by.values()) - set(DIRECT))
    orders = orders.filter(C("coin").is_in(union))
    apx = drift.approx_drift(orders, ref, inputs.fills.filter(C("ts") <= hi + timedelta(minutes=10)), rules, [LONG_MS],
                             ctx.raw["reference_prices"]["max_age_s"],
                             ctx.raw["reference_prices"]["fallback_print_window_s"])
    obs = apx.filter(C("day").is_in(days) & (C("reason") == "")).select("trader", "coin", "t", "drift_bps")
    candles, _ = hlprices.load_candles(ctx.path("hyperliquid_dir"), min(asof, ctx.cutoff))
    bars = candles.filter(C("n_trades") > 0).select("coin", bar_ms=C("ts").dt.epoch("ms"),
                                                    bar_volume_usdc=C("volume") * C("price")).sort("bar_ms")
    obs = (obs.with_columns(t_ms=C("t").dt.epoch("ms")).sort("t_ms")
           .join_asof(bars, left_on="t_ms", right_on="bar_ms", by="coin", tolerance=4 * 3600 * 1000 - 1,
                      check_sortedness=False))
    return pool_buckets(obs, passing_by, fallback["bucket_edges_usdc"], int(fallback["min_orders"]))
