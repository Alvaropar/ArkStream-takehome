"""Hyperliquid hourly funding rates (ADR-0011), parsed from the saved fundingHistory responses. No network.

Input: `data/reference/hyperliquid/funding/` (written by `arkstream_fetch.fetch_hyperliquid`), read **only**
through its `MANIFEST.csv`: every listed file must exist with its bytes and SHA-256, and any `.json` not in the
manifest stops the load with its name.

Table (one row per coin and funding hour, sorted coin, ts_hour):

* `ts_hour`  - the accrual hour: the raw time floored to the hour. The rate applies to the position held
  at that hour.
* `known_at` - the raw `time` of the response, a few ms after the hour. A rate may be used only at
  `asof >= known_at` (point in time).
* `coin, funding_rate, premium` - as published (hourly rate, a fraction, not annualised).
* `src_file` - the raw response file the row came from.

Nothing is filled in. A missing hour is reported in `gaps()` with a reason and stays missing.

Convention for Phase 3 (payments are not computed here): payment to the account at hour h =
-sign(position) x |size| x price x rate = -position x price x rate, where position is the signed size held
at h. Longs pay when the rate is positive. Hyperliquid uses its oracle price, which has no history here; the
Binance reference price at h stands in for it, labelled `oracle_proxy=binance_reference` (an approximation).
Checked against actual payments of a few leaders in `user_funding_check()`.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from arkstream.provenance import sha256_file

START = datetime(2025, 7, 27, tzinfo=UTC)
MANIFEST = "MANIFEST.csv"
FUNDING_SCHEMA = pl.Schema([("ts_hour", pl.Datetime("ms", "UTC")), ("known_at", pl.Datetime("ms", "UTC")),
                            ("coin", pl.String()), ("funding_rate", pl.Float64()), ("premium", pl.Float64()),
                            ("src_file", pl.String())])
KNOWN_LAG = timedelta(minutes=5)  # observed: up to 0.11 s, except one hour (2025-07-27 12:00) at 111 s


class HyperliquidManifestError(ValueError):
    """A Hyperliquid reference folder does not match its manifest."""


def manifest_files(kind_dir: Path) -> list[tuple[Path, dict[str, str]]]:
    """Verified (path, manifest row) pairs for one kind folder, sorted by manifest key."""
    man = kind_dir / MANIFEST
    if not man.exists():
        raise HyperliquidManifestError(f"{man}: missing")
    with open(man, newline="", encoding="utf-8") as fh:
        rows = sorted(csv.DictReader(fh), key=lambda r: (r["coin"], int(r["start_ms"])))
    root = kind_dir.parent
    listed = {(root / r["file"]).resolve() for r in rows}
    for p in sorted(kind_dir.rglob("*.json")):
        if p.resolve() not in listed:
            raise HyperliquidManifestError(f"{p}: not listed in {man}")
    out = []
    for r in rows:
        p = root / r["file"]
        if not p.exists():
            raise HyperliquidManifestError(f"{p}: listed in {man} but missing")
        if p.stat().st_size != int(r["bytes"]) or sha256_file(p) != r["sha256"]:
            raise HyperliquidManifestError(f"{p}: bytes or sha256 differ from {man}")
        out.append((p, r))
    return out


def _ts(col: str) -> pl.Expr:
    return pl.from_epoch(pl.col(col), time_unit="ms").dt.replace_time_zone("UTC")


def parse_funding_file(path: Path, rel: str) -> pl.DataFrame:
    rows = json.loads(path.read_bytes())
    if not rows:
        return pl.DataFrame(schema=FUNDING_SCHEMA)
    df = pl.DataFrame({"time": [int(r["time"]) for r in rows], "coin": [str(r["coin"]) for r in rows],
                       "funding_rate": [float(r["fundingRate"]) for r in rows],
                       "premium": [float(r["premium"]) for r in rows]})
    return df.select(ts_hour=_ts("time").dt.truncate("1h"), known_at=_ts("time"), coin="coin",
                     funding_rate="funding_rate", premium="premium", src_file=pl.lit(rel))


def load_funding(hl_dir: Path, cutoff: datetime) -> pl.DataFrame:
    """All funding rows known at or before the cutoff. Duplicate (coin, ts_hour) with different values raise."""
    kd = hl_dir / "funding"
    parts = [parse_funding_file(p, r["file"]) for p, r in manifest_files(kd)]
    df = pl.concat(parts) if parts else pl.DataFrame(schema=FUNDING_SCHEMA)
    df = df.filter(pl.col("known_at") <= cutoff).unique(maintain_order=False).sort("coin", "ts_hour", "known_at")
    dup = df.filter(pl.len().over("coin", "ts_hour") > 1)
    if dup.height:
        raise HyperliquidManifestError(f"conflicting funding rows for the same hour: {dup.head(4).rows()}")
    return df


def funding_asof(table: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    """Point in time: only rates whose known_at <= asof (a rate at ts_hour is not yet known at ts_hour)."""
    return table.filter(pl.col("known_at") <= asof)


def last_expected_hour(asof: datetime) -> datetime:
    """Latest funding hour whose rate should be known by asof: the hour of asof, unless asof is within
    KNOWN_LAG of it (rates are published a few ms after the hour), then the hour before."""
    h = asof.replace(minute=0, second=0, microsecond=0)
    return h if asof - h >= KNOWN_LAG else h - timedelta(hours=1)


def _hours(a: datetime, b: datetime) -> int:
    return int((b - a) / timedelta(hours=1))


def gaps(table: pl.DataFrame, coins: pl.DataFrame, asof: datetime, start: datetime = START) -> pl.DataFrame:
    """Every missing funding hour range per coin in [start, last hour known by asof], with a reason.

    `coins` has `coin` and optionally `first_fill`, `last_fill` (strings or datetimes) for context.
    Reasons: no_funding_rows | before_first_rate | internal_gap | after_last_rate.
    """
    t = funding_asof(table, asof)
    last_hour = last_expected_hour(asof)
    out: list[tuple[str, datetime, datetime, int, str]] = []
    have = {c: g["ts_hour"].to_list() for (c,), g in t.group_by("coin")}
    for c in sorted(coins["coin"].to_list()):
        hs = have.get(c, [])
        if not hs:
            out.append((c, start, last_hour, _hours(start, last_hour) + 1, "no_funding_rows"))
            continue
        if hs[0] > start:
            out.append((c, start, hs[0] - timedelta(hours=1), _hours(start, hs[0]), "before_first_rate"))
        for a, b in zip(hs, hs[1:], strict=False):
            if b - a > timedelta(hours=1):
                out.append((c, a + timedelta(hours=1), b - timedelta(hours=1), _hours(a, b) - 1, "internal_gap"))
        if hs[-1] < last_hour:
            out.append((c, hs[-1] + timedelta(hours=1), last_hour, _hours(hs[-1], last_hour), "after_last_rate"))
    return pl.DataFrame(out, orient="row", schema={
        "coin": pl.String, "gap_start": pl.Datetime("ms", "UTC"), "gap_end": pl.Datetime("ms", "UTC"),
        "hours": pl.Int64, "reason": pl.String}).sort("coin", "gap_start")


def coverage(table: pl.DataFrame, coins: pl.DataFrame, asof: datetime, start: datetime = START) -> pl.DataFrame:
    """One row per eligible coin: rows, first/last hour, expected hours, missing hours by reason, flag."""
    t = funding_asof(table, asof).filter(pl.col("ts_hour") >= start)
    g = gaps(table, coins, asof, start)
    last_hour = last_expected_hour(asof)
    expected = _hours(start, last_hour) + 1
    agg = t.group_by("coin").agg(rows=pl.len(), first_hour=pl.col("ts_hour").min(), last_hour=pl.col("ts_hour").max())
    miss = g.pivot(on="reason", index="coin", values="hours", aggregate_function="sum") if g.height else \
        pl.DataFrame(schema={"coin": pl.String})
    for r in ("no_funding_rows", "before_first_rate", "internal_gap", "after_last_rate"):
        if r not in miss.columns:
            miss = miss.with_columns(pl.lit(None, pl.Int64).alias(r))
    keep = [c for c in ("coin", "eligible_fills", "notional", "first_fill", "last_fill") if c in coins.columns]
    out = (coins.select(keep).join(agg, on="coin", how="left").join(miss, on="coin", how="left")
           .with_columns(rows=pl.col("rows").fill_null(0), expected_hours=pl.lit(expected),
                         **{r: pl.col(r).fill_null(0) for r in ("no_funding_rows", "before_first_rate",
                                                                 "internal_gap", "after_last_rate")}))
    return out.with_columns(flag=pl.when(pl.col("rows") == 0).then(pl.lit("no_funding"))
                            .when(pl.col("internal_gap") > 0).then(pl.lit("internal_gap"))
                            .when((pl.col("before_first_rate") > 0) | (pl.col("after_last_rate") > 0))
                            .then(pl.lit("partial_listing")).otherwise(pl.lit("complete"))).sort("coin")


def eligible_coins(fills: pl.DataFrame, asof: datetime) -> pl.DataFrame:
    """Core perps traded in eligible fills up to asof: the coin list the fetcher reads (coins.csv)."""
    f = fills.filter(pl.col("eligible") & (pl.col("ts") <= asof))
    fmt = "%Y-%m-%dT%H:%M:%S%.3fZ"
    return (f.group_by(coin="symbol").agg(eligible_fills=pl.len(), notional=pl.col("notional").sum().round(2),
                                          first_fill=pl.col("ts").min().dt.strftime(fmt),
                                          last_fill=pl.col("ts").max().dt.strftime(fmt)).sort("coin"))


# ------------------------------------------------------------------------------- userFunding check

def load_user_funding(hl_dir: Path, cutoff: datetime) -> pl.DataFrame:
    """Actual funding payments of the checked leaders (a check, never an input)."""
    recs: list[dict] = []
    for p, r in manifest_files(hl_dir / "user_funding"):
        for x in json.loads(p.read_bytes()):
            d = x["delta"]
            if d.get("type") != "funding":
                continue
            recs.append({"trader": r["coin"], "time": int(x["time"]), "coin": d["coin"], "usdc": float(d["usdc"]),
                         "szi": float(d["szi"]), "rate": float(d["fundingRate"]),
                         "n_samples": d.get("nSamples"), "src_file": r["file"]})
    if not recs:
        return pl.DataFrame()
    df = pl.DataFrame(recs).with_columns(ts=_ts("time")).filter(pl.col("ts") <= cutoff)
    return df.with_columns(ts_hour=pl.col("ts").dt.truncate("1h")).unique().sort("trader", "coin", "ts", "usdc")


def user_funding_check(uf: pl.DataFrame, ledger: pl.DataFrame, rates: pl.DataFrame, prices: pl.DataFrame,
                       rel_tol: float = 0.01) -> pl.DataFrame:
    """One row per userFunding record, checked against rate x rebuilt position x Binance proxy price.

    userFunding history is a **daily rollup** (ADR-0014): a record stamped D 00:00 UTC sums the hourly payments
    of hours D 00:00 .. D 23:00, `nSamples` is the number of those hours with a position, `fundingRate` their
    mean rate and `szi` a position. So each record is expanded to its 24 hours; per hour the position is the
    pos_after of the leader's last fill strictly before the hour (null before the series' first fill), and
    calc = -position x price x rate (longs pay a positive rate). Hours with a zero position pay nothing.

    ledger: positions.rebuild ledger (trader, symbol, ts, pos_after, src_row).
    prices: (coin, ts_hour, price), the Binance reference at the hour (oracle proxy); may be missing.
    Output flags: sign_ok, samples_ok (hours with a position == nSamples), rate_ok (mean of our rates over those
    hours == fundingRate), amount_ok (|sum calc / usdc - 1| <= rel_tol, only when every hour is priced and every
    position is known). A check only, never an input.
    """
    ms = pl.Datetime("ms", "UTC")
    led = ledger.select("trader", coin="symbol", fill_ts=pl.col("ts").cast(ms), pos="pos_after").sort("fill_ts")
    rec = uf.with_columns(pl.col("ts_hour").cast(ms), _rid=pl.int_range(pl.len()))
    hrs = (rec.select("_rid", "trader", "coin", day=pl.col("ts_hour"), k=pl.int_ranges(0, 24)).explode("k")
           .with_columns(ts_hour=(pl.col("day") + pl.duration(hours=pl.col("k"))).cast(ms))
           .with_columns(_h=(pl.col("ts_hour") - pl.duration(milliseconds=1)).cast(ms)).sort("_h"))
    hrs = hrs.join_asof(led, left_on="_h", right_on="fill_ts", by=["trader", "coin"], strategy="backward",
                        check_sortedness=False)
    hrs = hrs.join(rates.select("coin", pl.col("ts_hour").cast(ms), r="funding_rate"), on=["coin", "ts_hour"],
                   how="left")
    hrs = hrs.join(prices.select("coin", pl.col("ts_hour").cast(ms), px="price"), on=["coin", "ts_hour"], how="left")
    held = pl.col("pos").is_not_null() & (pl.col("pos").abs() > 1e-12)
    agg = hrs.group_by("_rid").agg(
        pos_unknown_hours=pl.col("pos").is_null().sum(), held_hours=held.sum(),
        mean_rate_held=pl.col("r").filter(held).mean(),
        unpriced_held_hours=(held & pl.col("px").is_null()).sum(),
        calc_usdc=(-pl.col("pos") * pl.col("px") * pl.col("r")).filter(held).sum())
    j = rec.join(agg, on="_rid", how="left")
    complete = (pl.col("pos_unknown_hours") == 0) & (pl.col("unpriced_held_hours") == 0)
    return j.with_columns(
        sign_ok=(pl.col("usdc").sign() == (-pl.col("szi") * pl.col("rate")).sign()) | (pl.col("usdc") == 0),
        samples_ok=pl.col("held_hours") == pl.col("n_samples"),
        rate_ok=(pl.col("mean_rate_held") - pl.col("rate")).abs() <= 1e-10 + 1e-6 * pl.col("rate").abs(),
        amount_known=complete,
        amount_rel_err=pl.when(complete).then(pl.col("calc_usdc") / pl.col("usdc") - 1),
    ).with_columns(amount_ok=pl.col("amount_rel_err").abs() <= rel_tol).drop("_rid").sort(
        "trader", "coin", "ts_hour", "usdc")
