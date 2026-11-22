"""Hyperliquid 4h candle closes: a second reference source, kept apart from Binance (ADR-0012, ADR-0013).

Read only through `data/reference/hyperliquid/candles_4h/MANIFEST.csv` (same checks as funding). A candle's `t`
is its open; its close `c` is known at `t + 4h` (`ts` below). Candles with no trades (`n == 0`) are dropped:
their close is a carried price. Rows whose close is not known by the cutoff are dropped. Never mixed into the
Binance rows: the table carries `source = hyperliquid_4h` and its own `src_file`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from arkstream.funding import manifest_files
from arkstream.prices import price_asof

BAR = timedelta(hours=4)
SOURCE = "hyperliquid_4h"
STRESS = (datetime.fromisoformat("2025-10-10T00:00:00+00:00"), datetime.fromisoformat("2025-10-12T00:00:00+00:00"))
CANDLE_SCHEMA = pl.Schema([("ts", pl.Datetime("ms", "UTC")), ("open_ts", pl.Datetime("ms", "UTC")),
                           ("coin", pl.String()), ("price", pl.Float64()), ("n_trades", pl.Int64()),
                           ("volume", pl.Float64()), ("source", pl.String()), ("src_file", pl.String())])


def load_candles(hl_dir: Path, cutoff: datetime) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(candles known by the cutoff with trades, dropped rows with a reason)."""
    recs = []
    for p, r in manifest_files(hl_dir / "candles_4h"):
        for x in json.loads(p.read_bytes()):
            recs.append({"t": int(x["t"]), "coin": str(x["s"]), "c": float(x["c"]), "n": int(x["n"]),
                         "v": float(x["v"]), "interval": x["i"], "src_file": r["file"]})
    if not recs:
        return pl.DataFrame(schema=CANDLE_SCHEMA), pl.DataFrame()
    df = pl.DataFrame(recs)
    if set(df["interval"].unique()) != {"4h"}:
        raise ValueError("candles_4h holds a non-4h candle")
    df = df.with_columns(open_ts=pl.from_epoch("t", time_unit="ms").dt.replace_time_zone("UTC")).with_columns(
        ts=pl.col("open_ts") + BAR)
    df = df.with_columns(drop_reason=pl.when(pl.col("ts") > cutoff).then(pl.lit("close_after_cutoff"))
                         .when(pl.col("n") == 0).then(pl.lit("no_trades_in_bar")))
    keep = df.filter(pl.col("drop_reason").is_null()).select(
        "ts", "open_ts", "coin", price="c", n_trades="n", volume="v", source=pl.lit(SOURCE), src_file="src_file")
    dup = keep.filter(pl.len().over("coin", "ts") > 1)
    if dup.height:
        raise ValueError(f"duplicate 4h candles: {dup.head(3).rows()}")
    dropped = df.filter(pl.col("drop_reason").is_not_null()).select("coin", "open_ts", "drop_reason", "src_file")
    return keep.sort("coin", "ts"), dropped.sort("coin", "open_ts")


OHLC_SCHEMA = pl.Schema([("ts", pl.Datetime("ms", "UTC")), ("open_ts", pl.Datetime("ms", "UTC")),
                         ("coin", pl.String()), ("o", pl.Float64()), ("h", pl.Float64()), ("l", pl.Float64()),
                         ("c", pl.Float64()), ("n_trades", pl.Int64()), ("src_file", pl.String())])


def load_candles_ohlc(hl_dir: Path, cutoff: datetime) -> pl.DataFrame:
    """Full Hyperliquid 4h OHLC for the worst-case drawdown (ADR-0045). Same rules as `load_candles`: a bar is
    known at its close (`ts` = open + 4h), bars after the cutoff and bars with no trades are dropped."""
    recs = []
    for p, r in manifest_files(hl_dir / "candles_4h"):
        for x in json.loads(p.read_bytes()):
            recs.append({"t": int(x["t"]), "coin": str(x["s"]), "o": float(x["o"]), "h": float(x["h"]),
                         "l": float(x["l"]), "c": float(x["c"]), "n": int(x["n"]), "src_file": r["file"]})
    if not recs:
        return pl.DataFrame(schema=OHLC_SCHEMA)
    df = pl.DataFrame(recs).with_columns(
        open_ts=pl.from_epoch("t", time_unit="ms").dt.replace_time_zone("UTC")).with_columns(
        ts=pl.col("open_ts") + BAR)
    df = df.filter((pl.col("ts") <= cutoff) & (pl.col("n") > 0))
    return df.select("ts", "open_ts", "coin", "o", "h", "l", "c", n_trades="n", src_file="src_file").sort("coin", "ts")


def compare_bars(candles: pl.DataFrame, ref: pl.DataFrame | pl.LazyFrame, fills: pl.DataFrame, asof: datetime,
                 max_age_s: float) -> pl.DataFrame:
    """Each Hyperliquid 4h close vs the Binance reference known at the same instant (close time t + 4h)."""
    c = candles.filter(pl.col("ts") <= asof)
    q = price_asof(c.select("coin", t="ts"), ref, fills.clear(), asof, max_age_s, 0)
    j = c.with_columns(ref_px=q["price"], ref_ts=q["price_ts"], ref_file=q["price_ref_file"],
                       ref_source=q["price_source"])
    return j.with_columns(
        gap_bps=pl.when(pl.col("ref_source") == "reference").then((pl.col("price") / pl.col("ref_px") - 1) * 1e4),
        stress=(pl.col("ts") >= STRESS[0]) & (pl.col("ts") < STRESS[1]),
    ).sort("coin", "ts")


def _stats(df: pl.DataFrame, prefix: str) -> list[pl.Expr]:
    a = pl.col("gap_bps").abs()
    return [pl.len().alias(f"{prefix}n"), a.median().alias(f"{prefix}median_abs_bps"),
            a.quantile(0.95, "linear").alias(f"{prefix}p95_abs_bps"),
            pl.col("gap_bps").median().alias(f"{prefix}median_bps")]


def price_check(bars: pl.DataFrame, coins: list[str], no_binance: set[str], min_n: int = 30,
                max_median: float = 10.0, max_p95: float = 30.0) -> pl.DataFrame:
    """Outcome per coin under the pre-registered rule (ADR-0012)."""
    ok = bars.filter(pl.col("gap_bps").is_not_null())
    main = ok.filter(~pl.col("stress")).group_by("coin").agg(_stats(ok, ""))
    st = ok.filter(pl.col("stress")).group_by("coin").agg(_stats(ok, "stress_"))
    nref = bars.filter(pl.col("gap_bps").is_null()).group_by("coin").agg(bars_without_ref=pl.len())
    base = pl.DataFrame({"coin": sorted(coins)}, schema={"coin": pl.String})
    out = base.join(main, on="coin", how="left").join(st, on="coin", how="left").join(nref, on="coin", how="left") \
        .with_columns(n=pl.col("n").fill_null(0), bars_without_ref=pl.col("bars_without_ref").fill_null(0))
    return out.with_columns(outcome=pl.when(pl.col("coin").is_in(sorted(no_binance))).then(pl.lit("no_binance"))
                            .when(pl.col("n") < min_n).then(pl.lit("insufficient"))
                            .when((pl.col("median_abs_bps") <= max_median) & (pl.col("p95_abs_bps") <= max_p95))
                            .then(pl.lit("pass")).otherwise(pl.lit("fail"))).sort("coin")


# ------------------------------------------------------------------------------- point in time (ADR-0110)
BARS_FILE = "research/hyperliquid/price_check_bars.parquet"
COINS_FILE = "research/hyperliquid/price_check.csv"   # ADR-0013 record: only its coin list is read
BY_ORIGIN_FILE = "research/hyperliquid/price_check_by_origin.csv"


def price_check_asof(bars: pl.DataFrame, coins: list[str], no_binance: set[str], asof: datetime,
                     rule: dict) -> pl.DataFrame:
    """The unchanged ADR-0012 rule on the compared bars whose close is at or before `asof` (ADR-0110).

    Each bar row compares a Hyperliquid close with the Binance price known at that same close, so the filtered
    sample holds only what was known at `asof`."""
    known = bars.filter(pl.col("ts") <= asof)
    return price_check(known, coins, no_binance, int(rule["min_bars"]), float(rule["max_median_abs_bps"]),
                       float(rule["max_p95_abs_bps"]))


def no_binance_coins(map_path: Path) -> set[str]:
    """Coins whose Binance mapping is never valid (ADR-0012 `no_binance`)."""
    m = pl.read_csv(map_path, infer_schema=False)
    return set(m.filter(~pl.col("status").is_in(["full", "partial"]))["hl"].to_list())


class PointInTimeCheck:
    """ADR-0110: the price-check outcome of every coin as of any time, computed from the compared bars."""

    def __init__(self, bars: pl.DataFrame, coins: list[str], no_binance: set[str], rule: dict):
        self.bars = bars.select("ts", "coin", "gap_bps", "stress").sort("coin", "ts")
        self.coins, self.no_binance, self.rule = sorted(coins), set(no_binance), rule
        self._cache: dict[datetime, pl.DataFrame] = {}

    @classmethod
    def load(cls, ctx) -> PointInTimeCheck:
        path = ctx.root / BARS_FILE
        if not path.is_file():
            raise FileNotFoundError(f"{path} missing: run `python -m arkstream funding --step price-check` first")
        coins = pl.read_csv(ctx.root / COINS_FILE)["coin"].to_list()
        return cls(pl.read_parquet(path, columns=["ts", "coin", "gap_bps", "stress"]), coins,
                   no_binance_coins(ctx.path("binance_map")), ctx.raw["funding"]["price_check"])

    def outcomes(self, asof: datetime) -> pl.DataFrame:
        if asof not in self._cache:
            self._cache[asof] = price_check_asof(self.bars, self.coins, self.no_binance, asof, self.rule)
        return self._cache[asof]

    def checks(self, asof: datetime) -> pl.DataFrame:
        """(coin, outcome) as of `asof`, the shape every consumer joins."""
        return self.outcomes(asof).select("coin", "outcome")

    def passing(self, asof: datetime) -> list[str]:
        return self.outcomes(asof).filter(pl.col("outcome") == "pass")["coin"].to_list()

    def by_origin(self, origins: list[datetime]) -> pl.DataFrame:
        return pl.concat([self.outcomes(o).select(pl.lit(o.date()).alias("origin"), pl.all()) for o in origins])


def origin_changes(pit: PointInTimeCheck, origins: list[datetime], cutoff: datetime, fills: pl.DataFrame,
                   holdout_start: datetime) -> pl.DataFrame:
    """Coins whose outcome as of each origin differs from the CUTOFF outcome (ADR-0013), with the eligible leader
    orders (trader, oid) and notional on them before the origin and in the following window [origin, next origin).
    The window after the last development origin is the holdout and is never counted."""
    cut = pit.checks(cutoff).rename({"outcome": "cutoff_outcome"})
    f = fills.filter(pl.col("eligible") & (pl.col("event_kind") == "trade")).select(
        "trader", "oid", coin="symbol", ts="ts", notional="notional")
    first = f["ts"].min()
    rows = []
    for i, o in enumerate(origins):
        nxt = origins[i + 1] if i + 1 < len(origins) and o < holdout_start else None
        x = (pit.outcomes(o).select("coin", "outcome", "n", "median_abs_bps", "p95_abs_bps")
             .join(cut, on="coin").filter(pl.col("outcome") != pl.col("cutoff_outcome")))
        x = x.with_columns(origin=pl.lit(o.date()), copy_effect=pl.when(pl.col("cutoff_outcome") == "pass")
                           .then(pl.lit("now_excluded")).when(pl.col("outcome") == "pass").then(pl.lit("now_copied"))
                           .otherwise(pl.lit("none")))
        for tag, lo, hi in (("before", first, o), ("next_window", o, nxt)):
            if hi is None:
                x = x.with_columns(pl.lit(None, pl.UInt32).alias(f"{tag}_orders"),
                                   pl.lit(None, pl.Float64).alias(f"{tag}_notional"),
                                   pl.lit(None, pl.Float64).alias(f"{tag}_notional_share"))
                continue
            w = f.filter((pl.col("ts") >= lo) & (pl.col("ts") < hi))
            total = w["notional"].sum()
            per = w.group_by("coin").agg(pl.struct("trader", "oid").n_unique().alias(f"{tag}_orders"),
                                         pl.col("notional").sum().alias(f"{tag}_notional"))
            x = x.join(per, on="coin", how="left").with_columns(
                pl.col(f"{tag}_orders").fill_null(0), pl.col(f"{tag}_notional").fill_null(0.0)).with_columns(
                (pl.col(f"{tag}_notional") / total if total else pl.lit(None, pl.Float64)).alias(
                    f"{tag}_notional_share"))
        rows.append(x.select("origin", "coin", "cutoff_outcome", "outcome", "copy_effect", "n", "median_abs_bps",
                             "p95_abs_bps", "before_orders", "before_notional", "before_notional_share",
                             "next_window_orders", "next_window_notional", "next_window_notional_share"))
    return pl.concat(rows).sort("origin", "coin")
