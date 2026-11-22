"""Drift during the follower's delay, measured for the cost scenarios (follower replay, A13, A16).

drift(h) for a leader order = side x (P(t + h) / P(t) - 1) in bps, where t is the leader's first fill of the
order (event time), h the follower's delay and side +1 for a buy. Positive drift is a cost to a follower
that copies late. Horizons are whole milliseconds end to end (`horizon_ms`, ADR-0150): the config lists them in
seconds (`horizons_s`, 1.2 allowed) and `seconds_to_ms` converts them exactly or refuses; outputs also carry a
readable `horizon_s` float.

Sources, in order of preference:

1. **Binance aggTrades** (the daily zips under data/reference/binance/aggtrades, listed in its MANIFEST.csv;
   never the lake's aggTrades copy, which drops whole minutes). P(x) = the last Binance trade at or before
   x, used only if it is at most `max_staleness_s` old, at both ends. Coins: BTC, ETH, HYPE, SOL.
2. **Approximate**, for coins without aggTrades: P(t) = the leader's own fill price, P(t + h) = the
   reference price (1m kline close known by t + h, else the package's own print, see prices.price_asof).
   Only for h >= 300 s and labelled approximate: 1m klines correlate only 0-0.35 with trade-level drift
   at 10-60 s, and their close comes before the leader's entry. A shorter horizon on klines raises.
   The fill is a Hyperliquid price and the reference a Binance one, so the coin's venue basis (median of
   fill / reference(t) - 1 over the trailing `basis_window_days`, see `venue_basis`) is added back with the
   order's sign; without enough basis observations the drift is unmeasured, not left uncorrected.

Rules for the holdout (written into config/decision_context.yaml):

* Point in time per origin: the parameters used for the test window starting at origin o (8 Oct, 22 Oct,
  5 Nov, 19 Nov, and 3 Dec for the holdout) come only from orders whose t + h is before o, over the
  history 2025-09-08..o - 1 (expanding). Stress dates are excluded from the development estimate.
  No price after 2025-12-02 is read: the reader refuses any aggTrades file dated after the estimation
  end, and an order whose t + h passes an origin loses its drift at that origin.
* 10-11 Oct is estimated separately and feeds the stress scenario; it exists only at origins after it
  (22 Oct onward). The 8 Oct origin has no stress estimate, and none is borrowed from later.
* Pooled by coin and the leader's holding-time band (median hold of round trips closed before the
  origin), never per leader: per-leader standard errors are 5-25 bps.
* Holdout prices (2025-12-03..2026-01-04) are used only for the frozen follower's holdout results.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl

from arkstream.instruments import forced_fill
from arkstream.positions import continuity, order_fills, rebuild

MS = 1000
AGG_COLS = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time", "is_buyer_maker"]
BAND_EDGES_S = [60, 900, 3600, 21600, 86400, 604800]
BAND_LABELS = ["<1m", "1-15m", "15m-1h", "1-6h", "6-24h", "1-7d", ">7d"]


class HoldoutLeak(ValueError):
    """A drift estimate tried to read prices outside its estimation window."""


def seconds_to_ms(x: Any) -> int:
    """A configured duration in seconds as a positive whole number of milliseconds (ADR-0150). Exact: 1.2 s is
    1,200 ms, never truncated to 1 s; a value finer than 1 ms or not positive is refused."""
    if isinstance(x, bool):
        raise ValueError(f"{x!r} is not a duration")
    v = Decimal(str(x)) * 1000
    if v != v.to_integral_value() or v <= 0:
        raise ValueError(f"{x!r} s is not a positive whole number of milliseconds")
    return int(v)


@dataclass(frozen=True)
class DriftRules:
    est_start: date
    est_end: date
    exclude: frozenset[date]
    stress: frozenset[date]
    holdout_start: date
    horizons_ms: tuple[int, ...]           # aggTrades horizons and the replay's delay grid (ADR-0150)
    approx_horizons_ms: tuple[int, ...]
    approx_min_horizon_ms: int
    max_staleness_s: float
    min_orders_per_cell: int
    aggtrades_symbols: dict[str, str]
    origins: tuple[date, ...] = ()        # test dates; () = one origin, the day after est_end
    basis_window_days: int = 7            # approximate drift: trailing window for the coin's venue basis
    min_basis_obs: int = 10               # fewer basis observations in that window -> drift unmeasured
    max_abs_basis_bps: float = 100.0      # a larger basis is a mapping question, not a correction -> unmeasured

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> DriftRules:
        d, sp = cfg["drift"], cfg["splits"]
        r = cls(est_start=_date(d["estimate_window"]["start"]), est_end=_date(d["estimate_window"]["end"]),
                exclude=frozenset(_date(x) for x in d["exclude_dates"]),
                stress=frozenset(_date(x) for x in d["stress_dates"]),
                holdout_start=_date(sp["holdout"]["start"]),
                horizons_ms=tuple(seconds_to_ms(h) for h in d["horizons_s"]),
                approx_horizons_ms=tuple(seconds_to_ms(h) for h in d["approx"]["horizons_s"]),
                approx_min_horizon_ms=seconds_to_ms(d["approx"]["min_horizon_s"]),
                max_staleness_s=float(d["max_staleness_s"]),
                min_orders_per_cell=int(d["min_orders_per_cell"]), aggtrades_symbols=dict(d["aggtrades_symbols"]),
                origins=tuple(sorted(_date(x) for x in d["origins"])),
                basis_window_days=int(d["approx"]["basis_window_days"]),
                min_basis_obs=int(d["approx"]["min_basis_obs"]),
                max_abs_basis_bps=float(d["approx"]["max_abs_basis_bps"]))
        r.check()
        return r

    def check(self) -> None:
        if self.est_end >= self.holdout_start:
            raise HoldoutLeak(f"drift estimation window ends {self.est_end}, on or after the holdout start "
                              f"{self.holdout_start}")
        if not self.stress <= self.exclude:
            raise ValueError("stress dates must be excluded from the development estimate")
        for hs in (self.horizons_ms, self.approx_horizons_ms):
            if list(hs) != sorted(set(hs)) or not all(isinstance(h, int) and h > 0 for h in hs):
                raise ValueError(f"horizons must be distinct positive whole milliseconds, ascending: {hs}")
        if min(self.approx_horizons_ms) < self.approx_min_horizon_ms:
            raise ValueError(f"approximate (kline) drift needs horizons >= {self.approx_min_horizon_ms / MS:g} s")
        for o in self.origin_dates:
            if o > self.est_end + timedelta(days=1):
                raise HoldoutLeak(f"origin {o}: its estimate would need prices after {self.est_end}")
            if o <= self.est_start:
                raise ValueError(f"origin {o}: no history before it (estimation starts {self.est_start})")

    @property
    def origin_dates(self) -> tuple[date, ...]:
        return self.origins or (self.est_end + timedelta(days=1),)

    @property
    def est_end_ts(self) -> datetime:
        return _day_end(self.est_end)


def _day_end(d: date) -> datetime:
    return datetime.combine(d + timedelta(days=1), datetime.min.time(), UTC) - timedelta(milliseconds=1)


def _date(x: Any) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x))


# ------------------------------------------------------------------------------------------------ inputs

def leader_orders(fills: pl.DataFrame, start: datetime, end: datetime) -> pl.DataFrame:
    """Core-perp trade orders: (trader, oid) timed at the first fill, with its side and price. Forced fills
    (ADL, liquidation, settlement; ADR-0112) are not the leader's choice and are left out."""
    f = (fills.filter(pl.col("eligible") & (pl.col("event_kind") == "trade") & (pl.col("ts") >= start)
                      & (pl.col("ts") <= end) & ~forced_fill()).sort("ts", "src_row"))
    return (f.group_by("trader", "oid").agg(
        t=pl.col("ts").first(), coin=pl.col("symbol").first(), side=pl.col("side").first(),
        fill_px=pl.col("price").first(), src_row=pl.col("src_row").first(), n_fills=pl.len())
        .with_columns(sign=pl.when(pl.col("side") == "buy").then(1).otherwise(-1), day=pl.col("t").dt.date())
        .sort("t", "trader", "oid"))


def hold_bands(fills: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    """Each leader's median holding time over round trips closed by asof, and its band (point in time)."""
    perp = fills.filter(pl.col("is_perp") & (pl.col("event_kind") == "trade") & (pl.col("ts") <= asof))
    _, trips = rebuild(continuity(order_fills(perp)))
    closed = trips.filter(pl.col("close_ts").is_not_null() & (pl.col("close_ts") <= asof)).with_columns(
        hold_s=(pl.col("close_ts") - pl.col("open_ts")).dt.total_milliseconds() / 1000)
    med = closed.group_by("trader").agg(median_hold_s=pl.col("hold_s").median(), closed_trips=pl.len())
    return med.with_columns(band=band_expr("median_hold_s")).sort("trader")  # stable order: byte-identical output


def band_expr(col: str) -> pl.Expr:
    e: Any = pl.when(pl.col(col) < BAND_EDGES_S[0]).then(pl.lit(BAND_LABELS[0]))
    for edge, lab in zip(BAND_EDGES_S[1:], BAND_LABELS[1:-1], strict=True):
        e = e.when(pl.col(col) < edge).then(pl.lit(lab))
    return e.otherwise(pl.lit(BAND_LABELS[-1]))


def read_aggtrades_zip(p: Path) -> pl.DataFrame:
    """One Binance daily aggTrades zip -> (bt: ms epoch, bp: price), sorted. Handles files with or without
    a header row."""
    with zipfile.ZipFile(p) as zf:
        raw = zf.read(zf.namelist()[0])
    has_header = raw[:12].lower().startswith(b"agg_trade_id")
    if has_header:
        df = pl.read_csv(io.BytesIO(raw), columns=["price", "transact_time"],
                         schema_overrides={"price": pl.Float64, "transact_time": pl.Int64})
    else:  # older archive files: same column order, no header row
        df = pl.read_csv(io.BytesIO(raw), has_header=False, new_columns=AGG_COLS,
                         schema_overrides={"price": pl.Float64, "transact_time": pl.Int64}
                         ).select("price", "transact_time")
    return df.select(bt=pl.col("transact_time"), bp=pl.col("price")).sort("bt")


class AggTradesSource:
    """Verified daily zips for one folder. With a MANIFEST.csv (fetch_aggtrades) only listed files whose
    size matches are read. `require_manifest=False` reads a folder of zips verified elsewhere (labelled)."""

    def __init__(self, root: Path, rules: DriftRules, require_manifest: bool = True):
        if "dataset=binance.um.agg_trades" in root.as_posix():
            raise ValueError("the lake's aggTrades copy is incomplete; read the Binance zips instead")
        self.root, self.rules = root, rules
        self.listed: dict[tuple[str, str], int] | None = None
        man = root / "MANIFEST.csv"
        if man.exists():
            with open(man, newline="", encoding="utf-8") as fh:
                self.listed = {(r["symbol"], r["date"]): int(r["bytes"]) for r in csv.DictReader(fh)}
        elif require_manifest:
            raise FileNotFoundError(f"{man} missing: run python -m arkstream_fetch.fetch_aggtrades first")
        self.label = "manifest" if self.listed is not None else "unlisted"
        self._cache: dict[tuple[str, date], pl.DataFrame | None] = {}

    def path(self, symbol: str, d: date) -> Path:
        return self.root / symbol / f"{symbol}-aggTrades-{d.isoformat()}.zip"

    def day(self, symbol: str, d: date) -> pl.DataFrame | None:
        if d > self.rules.est_end or d < self.rules.est_start:
            raise HoldoutLeak(f"refusing to read {symbol} aggTrades for {d}: outside the estimation window "
                              f"{self.rules.est_start}..{self.rules.est_end}")
        key = (symbol, d)
        if key not in self._cache:
            p = self.path(symbol, d)
            ok = p.exists()
            if ok and self.listed is not None:
                ok = self.listed.get((symbol, d.isoformat())) == p.stat().st_size
            if len(self._cache) > 3:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = read_aggtrades_zip(p) if ok else None
        return self._cache[key]


# ------------------------------------------------------------------------------------------------ measure

def _asof(left: pl.DataFrame, trades: pl.DataFrame, lcol: str, tag: str, staleness_ms: int) -> pl.DataFrame:
    r = trades.rename({"bt": f"{tag}_t", "bp": f"{tag}_p"})
    return left.sort(lcol).join_asof(r, left_on=lcol, right_on=f"{tag}_t", strategy="backward",
                                     tolerance=staleness_ms, check_sortedness=False)


def aggtrades_drift(orders: pl.DataFrame, src: AggTradesSource, rules: DriftRules) -> pl.DataFrame:
    """Per order and horizon: drift_bps from Binance trades, or null with a reason. One row per (order, h)."""
    stale = int(rules.max_staleness_s * MS)
    end_ms = int(rules.est_end_ts.timestamp() * MS)
    out = []
    for coin, sym in sorted(rules.aggtrades_symbols.items()):
        od = orders.filter(pl.col("coin") == coin).with_columns(tm=pl.col("t").dt.epoch("ms"))
        for (d,), part in sorted(od.group_by("day"), key=lambda x: x[0][0]):
            days = [x for x in (d - timedelta(days=1), d, d + timedelta(days=1))
                    if rules.est_start <= x <= rules.est_end]
            frames = [f for f in (src.day(sym, x) for x in days) if f is not None]
            have_day = src.day(sym, d) is not None
            tr = (pl.concat(frames).sort("bt") if frames
                  else pl.DataFrame(schema=pl.Schema([("bt", pl.Int64()), ("bp", pl.Float64())])))
            x0 = _asof(part, tr, "tm", "b0", stale)
            for h in rules.horizons_ms:
                x = x0.with_columns(t1=pl.col("tm") + h)
                x = _asof(x, tr, "t1", "b1", stale)
                ok = (pl.col("t1") <= end_ms) & pl.col("b0_p").is_not_null() & pl.col("b1_p").is_not_null()
                x = x.with_columns(
                    drift_bps=pl.when(ok).then(pl.col("sign") * (pl.col("b1_p") / pl.col("b0_p") - 1) * 1e4),
                    reason=pl.when(pl.lit(not have_day)).then(pl.lit("no_aggtrades_file"))
                    .when(pl.col("t1") > end_ms).then(pl.lit("horizon_past_estimation_end"))
                    .when(pl.col("b0_p").is_null() | pl.col("b1_p").is_null()).then(pl.lit("stale_binance_trade"))
                    .otherwise(pl.lit("")),
                    horizon_ms=pl.lit(h, pl.Int64), source=pl.lit("aggtrades"), price_source=pl.lit(src.label))
                out.append(x.select(_KEEP))
    return pl.concat(out) if out else pl.DataFrame(schema=_SCHEMA)


_KEEP = ["trader", "oid", "coin", "t", "day", "sign", "src_row", "horizon_ms", "drift_bps", "reason", "source",
         "price_source"]
_SCHEMA = pl.Schema([
    ("trader", pl.String()), ("oid", pl.Int64()), ("coin", pl.String()), ("t", pl.Datetime("ms", "UTC")),
    ("day", pl.Date()), ("sign", pl.Int32()), ("src_row", pl.Int64()), ("horizon_ms", pl.Int64()),
    ("drift_bps", pl.Float64()), ("reason", pl.String()), ("source", pl.String()), ("price_source", pl.String())])


def approx_drift(orders: pl.DataFrame, ref: pl.LazyFrame, fills: pl.DataFrame, rules: DriftRules,
                 horizons_ms: Iterable[int], max_age_s: float, print_window_s: float) -> pl.DataFrame:
    """Leader's fill price to the reference price at t + h, for h >= approx_min_horizon_ms only (h in ms)."""
    from arkstream.prices import price_asof

    hs = list(horizons_ms)
    if min(hs) < rules.approx_min_horizon_ms:
        raise ValueError(f"1m klines may not measure drift under {rules.approx_min_horizon_ms / MS:g} s "
                         f"(got {min(hs) / MS:g} s)")
    end = rules.est_end_ts
    orders = orders.join(venue_basis(orders, ref, fills, rules, max_age_s), on=["coin", "day"], how="left")
    out = []
    for h in hs:
        q = orders.with_columns(t1=pl.col("t") + pl.duration(milliseconds=h))
        inside = q.filter(pl.col("t1") <= end)
        priced = price_asof(inside.select("coin", t="t1"), ref, fills, end, max_age_s, print_window_s)
        inside = inside.with_columns(p1=priced["price"], p1_source=priced["price_source"])
        past = q.filter(pl.col("t1") > end).with_columns(p1=pl.lit(None, pl.Float64),
                                                          p1_source=pl.lit("horizon_past_estimation_end"))
        # The fill is a Hyperliquid price; a reference p1 is a Binance price. fill = B_t (1 + b), so the drift on
        # Binance is sign x (p1 (1 + b) / fill - 1). A package-print p1 is Hyperliquid: no correction.
        cross = pl.col("p1_source") == "reference"
        raw = pl.col("sign") * (pl.col("p1") / pl.col("fill_px") - 1) * 1e4
        adj = pl.col("sign") * (pl.col("p1") * (1 + pl.col("basis_bps") / 1e4) / pl.col("fill_px") - 1) * 1e4
        x = pl.concat([inside, past]).with_columns(
            drift_bps=pl.when(cross).then(adj).otherwise(raw),
            reason=pl.when(pl.col("p1").is_null()).then(
                pl.when(pl.col("p1_source") == "horizon_past_estimation_end").then(pl.col("p1_source"))
                .otherwise(pl.lit("unpriced")))
            .when(cross & pl.col("basis_bps").is_null() & pl.col("basis_too_large")).then(pl.lit("basis_too_large"))
            .when(cross & pl.col("basis_bps").is_null()).then(pl.lit("no_basis_estimate"))
            .otherwise(pl.lit("")),
            horizon_ms=pl.lit(h, pl.Int64), source=pl.lit("approx_fill_to_reference"),
            price_source=pl.col("p1_source"))
        out.append(x.select(_KEEP))
    return pl.concat(out) if out else pl.DataFrame(schema=_SCHEMA)


def venue_basis(orders: pl.DataFrame, ref: pl.DataFrame | pl.LazyFrame, fills: pl.DataFrame, rules: DriftRules,
                max_age_s: float) -> pl.DataFrame:
    """Per (coin, day): the median Hyperliquid/Binance basis in bps, fill_px / reference(t) - 1, over the coin's
    orders in the trailing `basis_window_days` days ending that day (point in time: only days <= that day).
    Unsigned on purpose: a side-signed basis also holds the move between the stale bar close and the fill
    (makers are filled after the price moves against them) and makes the approximation worse. Null when fewer
    than `min_basis_obs` observations, or when |basis| > `max_abs_basis_bps` (flagged `basis_too_large`: a gap that
    size means the two contracts may not be the same asset at that time): the drift is then unmeasured, never
    corrected with a made-up or doubtful basis."""
    from arkstream.prices import price_asof

    schema = pl.Schema([("coin", pl.String()), ("day", pl.Date()), ("basis_bps", pl.Float64()),
                        ("basis_obs", pl.UInt32()), ("basis_too_large", pl.Boolean())])
    if orders.height == 0:
        return pl.DataFrame(schema=schema)
    p0 = price_asof(orders.select("coin", "t"), ref, fills, rules.est_end_ts, max_age_s, 0.0)
    obs = (orders.select("coin", "day").with_columns(
        b=pl.when(p0["price_source"] == "reference").then((orders["fill_px"] / p0["price"] - 1) * 1e4))
        .drop_nulls("b"))
    days = orders.select("coin", "day").unique()
    w = rules.basis_window_days - 1
    j = (days.join(obs.rename({"day": "obs_day"}), on="coin", how="inner")
         .filter((pl.col("obs_day") <= pl.col("day")) & (pl.col("obs_day") >= pl.col("day") - timedelta(days=w))))
    g = j.group_by("coin", "day").agg(basis_bps=pl.col("b").median(), basis_obs=pl.len().cast(pl.UInt32))
    big = pl.col("basis_bps").abs() > rules.max_abs_basis_bps
    g = g.with_columns(basis_too_large=big.fill_null(False)).with_columns(
        basis_bps=pl.when((pl.col("basis_obs") >= rules.min_basis_obs) & ~big).then("basis_bps"))
    return days.join(g, on=["coin", "day"], how="left").select(schema.names()).cast(schema)


def pool(per_order: pl.DataFrame, bands: pl.DataFrame, rules: DriftRules, period: str) -> pl.DataFrame:
    """Pool by coin x holding-time band x horizon (plus an all-bands row per coin). Cells with fewer than
    min_orders_per_cell measured orders get no estimate (null), never a filled-in value."""
    x = (per_order.join(bands.select("trader", "band"), on="trader", how="left")
         .with_columns(band=pl.col("band").fill_null("no_closed_trip")))
    allb = x.with_columns(band=pl.lit("all"))
    g = pl.concat([x, allb]).group_by("source", "coin", "band", "horizon_ms").agg(
        orders=pl.len(), measured=pl.col("drift_bps").is_not_null().sum(),
        leaders=pl.col("trader").filter(pl.col("drift_bps").is_not_null()).n_unique(),
        days=pl.col("day").filter(pl.col("drift_bps").is_not_null()).n_unique(),
        mean_bps=pl.col("drift_bps").mean(), median_bps=pl.col("drift_bps").median(),
        sd_bps=pl.col("drift_bps").std(),
        first_day=pl.col("day").min(), last_day=pl.col("day").max(),
        main_unmeasured_reason=pl.col("reason").filter(pl.col("reason") != "").mode().sort().first(),
    ).with_columns(se_bps=pl.col("sd_bps") / pl.col("measured").sqrt())
    small = pl.col("measured") < rules.min_orders_per_cell
    g = g.with_columns([pl.when(small).then(None).otherwise(pl.col(c)).alias(c)
                        for c in ("mean_bps", "median_bps", "sd_bps", "se_bps")])
    return (g.with_columns(period=pl.lit(period), estimate=pl.when(small).then(pl.lit("too_few_orders"))
                           .otherwise(pl.lit("ok")), horizon_s=pl.col("horizon_ms") / MS,
                           label=pl.when(pl.col("source") == "aggtrades").then(pl.lit("measured"))
                           .otherwise(pl.lit("approximate")))
            .select("period", "source", "label", "coin", "band", "horizon_ms", "horizon_s", "orders", "measured",
                    "leaders", "days", "mean_bps", "se_bps", "sd_bps", "median_bps", "estimate", "first_day",
                    "last_day", "main_unmeasured_reason")
            .sort("period", "source", "coin", "band", "horizon_ms"))


def at_origin(per_order: pl.DataFrame, origin: date) -> pl.DataFrame:
    """The per-order rows an estimate made at `origin` may use: orders before the origin whose t + h is also
    before it. Rows whose horizon crosses the origin stay as orders but lose their drift (reason given)."""
    end = _day_end(origin - timedelta(days=1))
    x = per_order.filter(pl.col("t") <= end)
    crosses = (pl.col("t") + pl.duration(milliseconds=pl.col("horizon_ms"))) > end
    return x.with_columns(
        drift_bps=pl.when(crosses).then(None).otherwise(pl.col("drift_bps")),
        reason=pl.when(crosses & (pl.col("reason") == "")).then(pl.lit("horizon_past_origin"))
        .otherwise(pl.col("reason")))


def estimate(fills: pl.DataFrame, ref: pl.LazyFrame, src: AggTradesSource, rules: DriftRules,
             max_age_s: float, print_window_s: float) -> dict[str, pl.DataFrame]:
    """Drift parameters at every origin (test date), each from data before that origin only.

    Per-order drift depends only on prices in [t - staleness, t + h] (and, for the approximate method, the
    basis over the trailing days up to t's day), so it is measured once over the whole estimation window and
    each origin keeps the orders whose t + h is before it (`at_origin`). Holding bands are recomputed as of
    each origin. Development rows exclude the stress dates; stress rows are the stress dates before the origin
    (none for an origin before 10 Oct, which is reported as such, never borrowed from later)."""
    start = datetime.combine(rules.est_start, datetime.min.time(), UTC)
    orders = leader_orders(fills, start, rules.est_end_ts)
    agg_coins = set(rules.aggtrades_symbols)
    m_agg = aggtrades_drift(orders.filter(pl.col("coin").is_in(agg_coins)), src, rules)
    m_apx = approx_drift(orders.filter(~pl.col("coin").is_in(agg_coins)), ref, fills, rules,
                         rules.approx_horizons_ms, max_age_s, print_window_s)
    per = pl.concat([m_agg, m_apx])
    if per.height and per["t"].max() > rules.est_end_ts:  # type: ignore[operator]
        raise HoldoutLeak("an order after the estimation window entered the drift estimate")
    dev_t, st_t, band_t = [], [], []
    for o in rules.origin_dates:
        end = _day_end(o - timedelta(days=1))
        bands = hold_bands(fills, end)
        p = at_origin(per, o)
        tag = [pl.lit(o).alias("origin"), pl.lit(rules.est_start).alias("window_start"),
               pl.lit(o - timedelta(days=1)).alias("window_end")]
        dev_t.append(pool(p.filter(~pl.col("day").is_in(sorted(rules.exclude))), bands, rules, "development")
                     .select(*tag, pl.all()))
        st = p.filter(pl.col("day").is_in(sorted(rules.stress)))
        if st.height:
            st_t.append(pool(st, bands, rules, "stress").select(*tag, pl.all()))
        band_t.append(bands.select(pl.lit(o).alias("origin"), pl.all()))
    return {"development": pl.concat(dev_t),
            "stress": pl.concat(st_t) if st_t else dev_t[0].clear(),
            "per_order": per, "bands": pl.concat(band_t)}


def coverage_report(src: AggTradesSource, rules: DriftRules) -> pl.DataFrame:
    """Which estimation days have a usable aggTrades file per symbol (missing days are listed, not filled)."""
    days = [rules.est_start + timedelta(days=i) for i in range((rules.est_end - rules.est_start).days + 1)]
    rows = []
    for sym in sorted(rules.aggtrades_symbols.values()):
        for d in days:
            p = src.path(sym, d)
            ok = p.exists() and (src.listed is None or src.listed.get((sym, d.isoformat())) == p.stat().st_size)
            rows.append({"symbol": sym, "day": d, "available": ok})
    return pl.DataFrame(rows)
