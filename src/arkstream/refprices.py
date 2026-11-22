"""Reference prices from Binance USD-M 1m klines (A13): validity windows, filtering, files and manifest.

Input: the Hive-style Parquet lake of Binance 1m klines (`data/lake/venue=binance/dataset=binance.um.klines/
interval=1m/symbol=<SYM>/date=<YYYY-MM-DD>/part-*.parquet`, columns `ts_known` = bar close in ns, `close`,
`volume`), and the coin mapping `data/reference/binance/hl_binance_map.csv`. Reading Parquet needs nothing
but polars; no other repository is imported.

Rules (each is tested in tests/test_refprices.py):

* **Known time = bar close.** Binance stamps a 1m bar at its open; its close is known one minute later.
  The lake's `ts_known` is open + 60 s, and that is the reference `ts`. A bar known after CUTOFF is dropped
  (so the 23:59 bar of 4 Jan 2026, known at 00:00:00 on 5 Jan, is not used).
* **Validity window.** A coin's bar is kept only if the date of its known time is inside
  [valid_from, valid_to] (UTC dates, inclusive) from the mapping. Outside it the Binance contract is a
  different asset, not listed, or delisted.
* **Zero-volume bars are dropped**, never carried forward. Binance's archive prints flat bars at the last
  price for contracts that are not trading; such a bar is not a price observation.
* **Price factor.** price (Hyperliquid units) = close x price_factor_hl_per_binance.

Windows are derived from the data (first and last bar with volume > 0) plus the overrides in
`data/reference/binance/window_overrides.yaml`, each with a kind that says whether data may correct it.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import yaml

from arkstream.prices import write_manifest
from arkstream.provenance import sha256_file

NS = 1_000_000_000
KLINES_SUBDIR = Path("venue=binance") / "dataset=binance.um.klines" / "interval=1m"
MAP_COLUMNS = ["hl", "binance", "price_factor_hl_per_binance", "binance_listed", "valid_from", "valid_to",
               "status", "window_rule", "hl_first_fill", "hl_last_fill", "fills", "notional_usd", "notional_pct"]
STATUSES = ("full", "partial", "never_valid", "unmapped")


# ------------------------------------------------------------------------------------------------ inputs

def load_map(path: Path) -> pl.DataFrame:
    """The Hyperliquid -> Binance mapping, dates parsed. Works with or without the window columns."""
    m = pl.read_csv(path, infer_schema=False)
    dates = [c for c in ("binance_listed", "valid_from", "valid_to", "hl_first_fill", "hl_last_fill") if c in m.columns]
    m = m.with_columns([pl.col(c).str.to_date("%Y-%m-%d", strict=True) for c in dates])
    m = m.with_columns(price_factor_hl_per_binance=pl.col("price_factor_hl_per_binance").cast(pl.Float64))
    for c in ("fills", "notional_usd"):
        if c in m.columns:
            m = m.with_columns(pl.col(c).cast(pl.Int64))
    if "notional_pct" in m.columns:
        m = m.with_columns(pl.col("notional_pct").cast(pl.Float64))
    return m


def scan_klines(lake_dir: Path, month: str | None = None) -> pl.LazyFrame:
    """Lake 1m klines: symbol, ts_known (ns), close, volume. `month` = 'YYYY-MM' limits the scan."""
    base = lake_dir / KLINES_SUBDIR
    pat = f"symbol=*/date={month}-*/*.parquet" if month else "symbol=*/date=*/*.parquet"
    return (pl.scan_parquet(str(base / pat), hive_partitioning=False)
            .select("symbol", "ts_known", "close", "volume"))


def kline_months(lake_dir: Path) -> list[str]:
    base = lake_dir / KLINES_SUBDIR
    return sorted({p.name.removeprefix("date=")[:7] for p in base.glob("symbol=*/date=*") if p.is_dir()})


def _cut_ns(cutoff: datetime) -> int:
    return int(cutoff.timestamp()) * NS + cutoff.microsecond * 1000


def window_evidence(klines: pl.LazyFrame, cutoff: datetime) -> pl.DataFrame:
    """Per Binance symbol, bars known by CUTOFF: first/last bar, first/last bar with volume > 0, zero-volume
    count, the close of the last bar and the median close of zero-volume bars (frozen contracts)."""
    k = klines.filter(pl.col("ts_known") <= _cut_ns(cutoff))
    live = pl.col("volume") > 0
    ev = (k.group_by("symbol").agg(
        bars=pl.len(), zero_volume_bars=(~live).sum(),
        first_bar=pl.col("ts_known").min(), last_bar=pl.col("ts_known").max(),
        first_live=pl.col("ts_known").filter(live).min(), last_live=pl.col("ts_known").filter(live).max(),
        last_close=pl.col("close").sort_by("ts_known").last(),
        zero_volume_close_median=pl.col("close").filter(~live).median(),
    ).collect(engine="streaming"))
    ts = ["first_bar", "last_bar", "first_live", "last_live"]
    return ev.with_columns([pl.from_epoch(c, "ns").dt.cast_time_unit("ms").dt.replace_time_zone("UTC") for c in ts]
                           ).sort("symbol")


def load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return doc.get("overrides", {})


# ------------------------------------------------------------------------------------------------ windows

@dataclass(frozen=True)
class Window:
    valid_from: date | None
    valid_to: date | None
    rule: str


def _d(x: Any) -> date | None:
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return date.fromisoformat(str(x))


def derive_window(ev: dict[str, Any] | None, ov: dict[str, Any] | None, cutoff: datetime) -> Window:
    """One coin's validity window from data evidence and an optional override.

    Default: from the date of the first bar with volume > 0 to the cutoff date, or to the date of the last
    such bar when trading stopped more than a day before the cutoff (a delisting).

    Override kinds:
      never            - never valid (a different asset or a frozen contract), whatever the data shows;
      different_asset  - valid_from / valid_to are semantic limits; data can only narrow them;
      listing          - valid_from is checked against the data; the data date wins;
      delisting        - valid_to is checked against the data; the data date wins.
    """
    cut = cutoff.date()
    first_live = _d(ev.get("first_live")) if ev else None
    last_live = _d(ev.get("last_live")) if ev else None
    if ov and ov.get("kind") == "never":
        return Window(None, None, f"never: {ov.get('reason', '')}".strip())
    if first_live is None or last_live is None:
        why = "no Binance bars before the cutoff" if not ev or not ev.get("bars") else "no bar with volume > 0"
        return Window(None, None, f"data: {why}")
    vf, vt = first_live, (last_live if last_live < cut - timedelta(days=1) else cut)
    notes = ["data: first/last bar with volume > 0"]
    if ov:
        kind = ov.get("kind")
        rf, rt = _d(ov.get("valid_from")), _d(ov.get("valid_to"))
        if kind == "different_asset":
            if rf and rf > vf:
                vf = rf
            if rt and rt < vt:
                vt = rt
            notes.append(f"different_asset override {rf or ''}..{rt or ''}")
        elif kind in ("listing", "delisting"):
            if kind == "delisting":
                vt = last_live  # the data's last traded date, however close to the cutoff
            req = rf if kind == "listing" else rt
            got = vf if kind == "listing" else vt
            notes.append(f"{kind}: requested {req}, data {got}" + ("" if req == got else " (corrected to data)"))
        else:
            raise ValueError(f"unknown override kind {kind!r}")
    if vf > vt:
        return Window(None, None, "; ".join(notes + ["empty window"]))
    return Window(vf, vt, "; ".join(notes))


def status_expr() -> pl.Expr:
    """Status computed from the window and the Hyperliquid fill span (no listing-date guesswork)."""
    return (pl.when(pl.col("binance").is_null()).then(pl.lit("unmapped"))
            .when(pl.col("valid_from").is_null()).then(pl.lit("never_valid"))
            .when((pl.col("valid_from") <= pl.col("hl_first_fill")) & (pl.col("valid_to") >= pl.col("hl_last_fill")))
            .then(pl.lit("full"))
            .otherwise(pl.lit("partial")))


def apply_windows(mapping: pl.DataFrame, evidence: pl.DataFrame, overrides: dict[str, dict[str, Any]],
                  cutoff: datetime) -> pl.DataFrame:
    """Mapping with valid_from, valid_to, window_rule and a computed status (replacing the old one)."""
    ev = {r["symbol"]: r for r in evidence.iter_rows(named=True)}
    unknown = set(overrides) - set(mapping["hl"].to_list())
    if unknown:
        raise ValueError(f"window overrides for coins not in the mapping: {sorted(unknown)}")
    vf, vt, rule = [], [], []
    for hl, bn in mapping.select("hl", "binance").iter_rows():
        if bn is None:
            w = Window(None, None, "no Binance USD-M contract")
        else:
            w = derive_window(ev.get(bn), overrides.get(hl), cutoff)
        vf.append(w.valid_from)
        vt.append(w.valid_to)
        rule.append(w.rule)
    out = mapping.drop([c for c in ("valid_from", "valid_to", "status", "window_rule") if c in mapping.columns])
    out = out.with_columns(valid_from=pl.Series(vf, dtype=pl.Date), valid_to=pl.Series(vt, dtype=pl.Date),
                           window_rule=pl.Series(rule, dtype=pl.String))
    out = out.with_columns(status=status_expr())
    return out.select([c for c in MAP_COLUMNS if c in out.columns])


def write_map(mapping: pl.DataFrame, path: Path) -> None:
    mapping.with_columns([pl.col(c).dt.strftime("%Y-%m-%d") for c, t in mapping.schema.items() if t == pl.Date]
                         ).write_csv(path)


# ------------------------------------------------------------------------------------------------ prices

def reference_from_klines(klines: pl.LazyFrame, mapping: pl.DataFrame, cutoff: datetime) -> pl.LazyFrame:
    """The A13 rules: known at bar close, inside the coin's window, volume > 0, times the price factor."""
    m = (mapping.filter(pl.col("valid_from").is_not_null() & pl.col("binance").is_not_null())
         .select(pl.col("binance").alias("symbol"), pl.col("hl").alias("coin"), "price_factor_hl_per_binance",
                 "valid_from", "valid_to"))
    ts = pl.from_epoch("ts_known", "ns").dt.cast_time_unit("ms").dt.replace_time_zone("UTC")
    return (klines.filter((pl.col("ts_known") <= _cut_ns(cutoff)) & (pl.col("volume") > 0))
            .join(m.lazy(), on="symbol", how="inner")
            .with_columns(ts=ts)
            .filter(pl.col("ts").dt.date().is_between(pl.col("valid_from"), pl.col("valid_to"), closed="both"))
            .select("ts", "coin", price=pl.col("close") * pl.col("price_factor_hl_per_binance"),
                    source_symbol=pl.col("symbol")))


def build_reference_files(lake_dir: Path, mapping: pl.DataFrame, cutoff: datetime, out_dir: Path,
                          meta: dict[str, Any]) -> list[Path]:
    """One Parquet file per month (known-time month), sorted by coin and ts, then MANIFEST.yaml.

    Any stale reference file in out_dir is removed first (out_dir holds only generated files).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("binance_um_1m_*.parquet"):
        old.unlink()
    written = []
    for month in kline_months(lake_dir):
        df = reference_from_klines(scan_klines(lake_dir, month), mapping, cutoff).collect(engine="streaming")
        # A bar opened on the last minute of a month is known at 00:00 of the next: keep it in the file of
        # its known time, so each file holds exactly one calendar month of known times.
        if df.height == 0:
            continue
        for (mkey,), part in df.group_by(pl.col("ts").dt.strftime("%Y-%m").alias("mkey")):
            p = out_dir / f"binance_um_1m_{mkey}.parquet"
            prev = pl.read_parquet(p) if p in written else None
            part = part.drop("mkey") if "mkey" in part.columns else part
            full = pl.concat([prev, part]) if prev is not None else part
            full.sort("coin", "ts").write_parquet(p, compression="zstd", statistics=True, row_group_size=1_000_000)
            if p not in written:
                written.append(p)
    write_manifest(out_dir, written, meta)
    return sorted(written)


# ------------------------------------------------------------------------------------------------ zips
# Rebuild the kline lake from Binance's own monthly 1m zips (fetch_klines.py), without the external lake tool.
ZIP_NAME = re.compile(r"^(?P<symbol>[A-Z0-9]+)-1m-(?P<month>\d{4}-\d{2})\.zip$")
ZIP_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count",
            "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def load_zip_hashes(path: Path) -> dict[str, str]:
    """File name -> SHA-256 verified against Binance's published .CHECKSUM: either the fetcher's MANIFEST.csv
    (`file`, `sha256`, `published_sha256`) or data/reference/binance/CHECKSUMS.txt (`sha256  bytes  path  status`,
    only rows marked verified)."""
    out: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".csv":
        for r in csv.DictReader(io.StringIO(text)):
            if r["sha256"] == r["published_sha256"]:
                out[Path(r["file"]).name] = r["sha256"]
        return out
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 4 and not line.startswith("#") and parts[3] == "verified":
            out[Path(parts[2]).name] = parts[0]
    return out


def verified_kline_zips(root: Path, hashes: dict[str, str]) -> list[Path]:
    """Every monthly 1m kline zip under root, each checked against its verified SHA-256. A zip without a
    verified hash, or with a different one, stops the build with its name (nothing unverified is read)."""
    zips = sorted(p for p in root.rglob("*.zip") if ZIP_NAME.match(p.name))
    unknown = [p.name for p in zips if p.name not in hashes]
    if unknown:
        raise ValueError(f"kline zips without a verified checksum: {unknown[:5]} ({len(unknown)} in all)")
    bad = [p.name for p in zips if sha256_file(p) != hashes[p.name]]
    if bad:
        raise ValueError(f"kline zips whose sha256 differs from the verified one: {bad[:5]} ({len(bad)} in all)")
    return zips


def read_kline_zip(p: Path) -> pl.DataFrame:
    """One Binance monthly 1m kline zip -> the lake columns. Known time = bar close = open_time + 60 s (ns);
    `ts_event` is the same instant (the lake's convention)."""
    m = ZIP_NAME.match(p.name)
    if m is None:
        raise ValueError(f"{p.name}: not a monthly 1m kline zip")
    with zipfile.ZipFile(p) as z:
        raw = z.read(z.namelist()[0])
    header = raw[:9].lower().startswith(b"open_time")
    names = ZIP_COLS[:6]
    if header:
        df = pl.read_csv(io.BytesIO(raw), columns=names, infer_schema=False)
    else:  # older archive files: same column order, no header row
        df = pl.read_csv(io.BytesIO(raw), has_header=False, new_columns=ZIP_COLS, infer_schema=False)
    df = df.select(pl.col("open_time").cast(pl.Int64), *[pl.col(c).cast(pl.Float64) for c in names[1:]])
    if df.height and df["open_time"].max() > 10**14:  # type: ignore[operator]
        raise ValueError(f"{p.name}: open_time is not in milliseconds")
    known = (pl.col("open_time") + 60_000) * 1_000_000
    return df.select(symbol=pl.lit(m["symbol"]), ts_event=known, ts_known=known, open="open", high="high", low="low",
                     close="close", volume="volume").sort("ts_known")


def lake_from_zips(zips: list[Path], lake_dir: Path) -> list[Path]:
    """Write the Hive kline lake from verified zips: one Parquet file per symbol and month of known time
    (`symbol=<SYM>/date=<YYYY-MM>-01/part-0.parquet`). The target must not already hold kline files."""
    base = lake_dir / KLINES_SUBDIR
    if base.exists() and any(base.rglob("*.parquet")):
        raise FileExistsError(f"{base} already holds kline files; build into an empty folder")
    by_symbol: dict[str, list[Path]] = {}
    for p in zips:
        by_symbol.setdefault(ZIP_NAME.match(p.name)["symbol"], []).append(p)  # type: ignore[index]
    written = []
    for sym, files in sorted(by_symbol.items()):
        df = pl.concat([read_kline_zip(p) for p in sorted(files)]).sort("ts_known")
        if df["ts_known"].is_duplicated().any():
            raise ValueError(f"{sym}: duplicate bars across its monthly zips")
        df = df.with_columns(m=pl.from_epoch("ts_known", "ns").dt.strftime("%Y-%m"))
        for (mkey,), part in sorted(df.group_by("m"), key=lambda x: x[0]):
            d = base / f"symbol={sym}" / f"date={mkey}-01"
            d.mkdir(parents=True, exist_ok=True)
            p = d / "part-0.parquet"
            part.drop("m").write_parquet(p, compression="zstd", statistics=True)
            written.append(p)
    return written


def write_raw_checksums(raw_dir: Path, dest: Path, verified_db: Path | None = None) -> list[str]:
    """SHA-256 of every original Binance zip under raw_dir, cross-checked against the fetcher's record of
    hashes verified against Binance's published .CHECKSUM files (when that record exists)."""
    import sqlite3

    known: dict[str, str] = {}
    if verified_db and verified_db.exists():
        with sqlite3.connect(verified_db) as c:
            known = dict(c.execute("select key, sha256 from verified").fetchall())
    lines, mismatches = [], []
    for p in sorted(raw_dir.rglob("*.zip")):
        rel = p.relative_to(raw_dir).as_posix()
        h = sha256_file(p)
        ok = known.get(rel)
        if ok is not None and ok != h:
            mismatches.append(rel)
        lines.append(f"{h}  {p.stat().st_size:>12d}  {rel}  {'verified' if ok == h else 'unverified'}")
    if mismatches:
        raise ValueError(f"raw Binance zips differ from their verified hashes: {mismatches[:5]}")
    dest.write_text("# Original Binance zips (data.binance.vision), relative to data/lake/_raw/.\n"
                    "# 'verified' = this sha256 equals the hash checked against Binance's published .CHECKSUM\n"
                    "# sha256  bytes  path  status\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return lines
