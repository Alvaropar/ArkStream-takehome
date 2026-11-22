"""Reference coin prices (external, A13) and the package's own trade-print panel.

Reference price files live in data/reference/prices/ and are read **only through its manifest**,
`data/reference/prices/MANIFEST.yaml`, which lists every file with its SHA-256 and byte size. The loader
refuses to run when

* a file in the folder is not listed in the manifest (an unexpected file never enters the build by
  accident: it fails with a message naming it);
* a listed file is missing or its hash or size differs from the manifest.

Each file is Parquet or CSV with columns `ts` (or `timestamp`), `coin` (Hyperliquid name), `price` (in
Hyperliquid units). `ts` is the time the price became **known** (for Binance 1m klines: the bar close).
Files are produced by `arkstream.refprices` from Binance USD-M 1m klines; source, resolution and
retrieval date are recorded in the manifest and in config/decision_context.yaml.

Nothing is imputed and no price is carried forward. A price for (coin, t) is the latest reference price
known at or before t and at most `max_age_s` old. Zero-volume Binance bars are never written to the
reference, so a coin that did not trade on Binance in the last minute has no reference price; it falls
back to the package's own latest print within `print_window_s`, or stays unpriced with a reason (A13).
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
import yaml

from arkstream.positions import pit
from arkstream.provenance import sha256_file
from arkstream.timeparse import parse_ts_column

MANIFEST_NAME = "MANIFEST.yaml"
REF_COLS = {"coin", "price"}
REF_SCHEMA = pl.Schema([("ts", pl.Datetime("ms", "UTC")), ("coin", pl.String()), ("price", pl.Float64()),
                        ("ref_file", pl.String())])
IGNORED_NAMES = {".gitkeep", "README.md"}


class ReferenceManifestError(ValueError):
    """The reference price folder does not match its manifest."""


# ---------------------------------------------------------------------------------------------- manifest

def read_manifest(prices_dir: Path) -> dict[str, Any] | None:
    p = prices_dir / MANIFEST_NAME
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as fh:
        m = yaml.safe_load(fh) or {}
    if not isinstance(m.get("files", []), list):
        raise ReferenceManifestError(f"{p}: 'files' must be a list")
    return m


def write_manifest(prices_dir: Path, files: list[Path], meta: dict[str, Any] | None = None) -> Path:
    """Write MANIFEST.yaml listing exactly `files` (paths inside prices_dir) with SHA-256, bytes and rows."""
    entries = []
    for f in sorted(files, key=lambda x: x.relative_to(prices_dir).as_posix()):
        rows = (pl.scan_parquet(f).select(pl.len()).collect().item() if f.suffix.lower() == ".parquet"
                else pl.scan_csv(f, infer_schema=False).select(pl.len()).collect().item())
        entries.append({"path": f.relative_to(prices_dir).as_posix(), "sha256": sha256_file(f),
                        "bytes": f.stat().st_size, "rows": int(rows)})
    doc = {**(meta or {}), "files": entries}
    out = prices_dir / MANIFEST_NAME
    header = ("# Reference price manifest. The loader reads exactly these files and refuses any other file in\n"
              "# this folder, or a listed file whose sha256/bytes differ. Regenerate: python -m arkstream refprices\n")
    out.write_text(header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return out


_HASH_CACHE: dict[tuple[str, int, int], str] = {}


def _sha_cached(p: Path) -> str:
    st = p.stat()
    key = (str(p.resolve()), st.st_size, st.st_mtime_ns)
    if key not in _HASH_CACHE:
        _HASH_CACHE[key] = sha256_file(p)
    return _HASH_CACHE[key]


def manifest_files(prices_dir: Path) -> list[Path]:
    """The verified list of reference files. [] if the folder is absent or holds nothing.

    Raises ReferenceManifestError on any file not in the manifest, a missing listed file, or a hash/size
    mismatch. The message names the file and says how to fix it.
    """
    if not prices_dir.exists():
        return []
    present = sorted(p for p in prices_dir.rglob("*") if p.is_file() and p.name != MANIFEST_NAME
                     and p.name not in IGNORED_NAMES)
    m = read_manifest(prices_dir)
    if m is None:
        if present:
            raise ReferenceManifestError(
                f"{prices_dir}: no {MANIFEST_NAME}, but the folder holds {len(present)} file(s), e.g. "
                f"{present[0].name}. Reference prices are read only through the manifest; regenerate it with "
                f"`python -m arkstream refprices` or remove the files.")
        return []
    listed = {e["path"]: e for e in m.get("files", [])}
    unexpected = [p.relative_to(prices_dir).as_posix() for p in present
                  if p.relative_to(prices_dir).as_posix() not in listed]
    if unexpected:
        raise ReferenceManifestError(
            f"{prices_dir}: unexpected file(s) not listed in {MANIFEST_NAME}: {', '.join(unexpected)}. "
            f"Move them out of the folder, or regenerate the manifest if they are meant to be reference prices.")
    out = []
    for rel, e in listed.items():
        p = prices_dir / rel
        if not p.exists():
            raise ReferenceManifestError(f"{prices_dir}: {rel} is listed in {MANIFEST_NAME} but missing")
        if "bytes" in e and p.stat().st_size != int(e["bytes"]):
            raise ReferenceManifestError(f"{p}: size {p.stat().st_size} != manifest {e['bytes']}")
        got = _sha_cached(p)
        if got != e.get("sha256"):
            raise ReferenceManifestError(f"{p}: sha256 {got} != manifest {e.get('sha256')}")
        out.append(p)
    return out


# ---------------------------------------------------------------------------------------------- loading

def _scan_one(p: Path) -> pl.LazyFrame:
    if p.suffix.lower() == ".parquet":
        lf = pl.scan_parquet(p)
        cols = lf.collect_schema()
        if not REF_COLS <= set(cols.names()) or not ({"ts", "timestamp"} & set(cols.names())):
            raise ReferenceManifestError(f"{p}: needs columns ts|timestamp, coin, price; has {cols.names()}")
        tcol = "ts" if "ts" in cols.names() else "timestamp"
        dtype = cols[tcol]
        if isinstance(dtype, pl.Datetime):
            ts = (pl.col(tcol).dt.convert_time_zone("UTC").dt.cast_time_unit("ms") if dtype.time_zone
                  else pl.col(tcol).dt.cast_time_unit("ms").dt.replace_time_zone("UTC"))
            lf = lf.with_columns(ts=ts)
        else:
            lf = parse_ts_column(lf.collect().with_columns(pl.col(tcol).cast(pl.String).alias("timestamp"))).lazy()
    elif p.suffix.lower() == ".csv":
        raw = pl.read_csv(p, infer_schema=False)
        if not REF_COLS <= set(raw.columns) or not ({"ts", "timestamp"} & set(raw.columns)):
            raise ReferenceManifestError(f"{p}: needs columns ts|timestamp, coin, price; has {raw.columns}")
        tcol = "timestamp" if "timestamp" in raw.columns else "ts"
        lf = parse_ts_column(raw.with_columns(pl.col(tcol).alias("timestamp"))).lazy()
    else:
        raise ReferenceManifestError(f"{p}: reference files must be .parquet or .csv")
    return lf.select("ts", pl.col("coin").cast(pl.String), pl.col("price").cast(pl.Float64, strict=True),
                     pl.lit(p.name).alias("ref_file"))


def scan_reference(prices_dir: Path) -> pl.LazyFrame:
    """Lazy reference prices (ts, coin, price, ref_file) from the manifest's files only."""
    files = manifest_files(prices_dir)
    if not files:
        return pl.DataFrame(schema=REF_SCHEMA).lazy()
    return pl.concat([_scan_one(p) for p in files], how="vertical")


def load_reference(prices_dir: Path) -> pl.DataFrame:
    """Eager version of scan_reference (small folders and tests). Empty frame with schema if none."""
    return scan_reference(prices_dir).collect().sort("coin", "ts")


def _lazy(ref: pl.DataFrame | pl.LazyFrame) -> pl.LazyFrame:
    lf = ref.lazy() if isinstance(ref, pl.DataFrame) else ref
    if "ref_file" not in lf.collect_schema().names():
        lf = lf.with_columns(ref_file=pl.lit(None, pl.String))
    return lf


def reference_rows(ref: pl.DataFrame | pl.LazyFrame, asof: datetime) -> int:
    return int(_lazy(ref).filter(pl.col("ts") <= asof).select(pl.len()).collect(engine="streaming").item())


def infer_resolution_s(ref: pl.DataFrame) -> float | None:
    if ref.height < 2:
        return None
    steps = ref.sort("coin", "ts").select(
        (pl.col("ts").diff().over("coin").dt.total_milliseconds() / 1000).alias("s")
    )["s"].drop_nulls()
    med = steps.median()
    return float(med) if isinstance(med, (int, float)) else None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------------- lookups

def _candidates(ref: pl.DataFrame | pl.LazyFrame, keys: pl.DataFrame, asof: datetime, max_age_s: float
                ) -> pl.DataFrame:
    """Reference rows that can answer queries `keys` (coin, t): ts in [t - max_age_s, t] and ts <= asof.

    Pre-filters the (large, lazy) reference by minute buckets before any as-of join, so the full
    reference is never materialised.
    """
    k = max(1, math.ceil(max_age_s / 60))
    buckets = (keys.select("coin", m=pl.col("t").dt.truncate("1m"))
               .with_columns(off=pl.lit(list(range(k + 1)))).explode("off")
               .select("coin", m=(pl.col("m") - pl.duration(minutes=pl.col("off"))).dt.cast_time_unit("ms"))
               .unique())
    return (_lazy(ref).filter(pl.col("ts") <= asof)
            .with_columns(m=pl.col("ts").dt.truncate("1m").dt.cast_time_unit("ms"))
            .join(buckets.lazy(), on=["coin", "m"], how="semi")
            .drop("m").collect(engine="streaming").sort("ts"))


def price_asof(queries: pl.DataFrame, ref: pl.DataFrame | pl.LazyFrame, fills: pl.DataFrame, asof: datetime,
               max_age_s: float, print_window_s: float, coin_col: str = "coin", ts_col: str = "t") -> pl.DataFrame:
    """Price each (coin, t) query point in time: reference first, then package prints, else unpriced.

    Adds price, price_ts, price_source (reference | package_print | unpriced), price_ref_file,
    price_src_row (raw fills line of the print used), unpriced_reason. Never interpolates or carries a
    price beyond its tolerance. Queries after asof are rejected.
    """
    q = queries.rename({coin_col: "coin", ts_col: "t"}) if (coin_col, ts_col) != ("coin", "t") else queries
    q = q.with_columns(pl.col("t").dt.cast_time_unit("ms"), _qid=pl.int_range(pl.len()))
    if q.height and q["t"].max() > asof:  # type: ignore[operator]
        raise ValueError("price_asof: a query time is after asof")
    cand = _candidates(ref, q.select("coin", "t"), asof, max_age_s) if q.height else pl.DataFrame(schema=REF_SCHEMA)
    j = q.sort("t").join_asof(cand.select("coin", ref_ts="ts", ref_px="price", ref_file="ref_file").sort("ref_ts"),
                              left_on="t", right_on="ref_ts", by="coin", strategy="backward",
                              tolerance=f"{int(max_age_s * 1000)}ms", check_sortedness=False)
    prints = (pit(fills, asof).filter(pl.col("eligible") & (pl.col("event_kind") == "trade"))
              .select(pl.col("symbol").alias("coin"), pl.col("ts").alias("print_ts"), pl.col("price").alias("print_px"),
                      pl.col("src_row").alias("print_src_row")).sort("print_ts", "print_src_row"))
    j = j.sort("t").join_asof(prints, left_on="t", right_on="print_ts", by="coin", strategy="backward",
                              tolerance=f"{int(print_window_s * 1000)}ms", check_sortedness=False)
    use_ref = pl.col("ref_px").is_not_null()
    use_pr = ~use_ref & pl.col("print_px").is_not_null()
    out = j.with_columns(
        price=pl.when(use_ref).then("ref_px").when(use_pr).then("print_px"),
        price_ts=pl.when(use_ref).then("ref_ts").when(use_pr).then("print_ts"),
        price_source=pl.when(use_ref).then(pl.lit("reference")).when(use_pr).then(pl.lit("package_print"))
        .otherwise(pl.lit("unpriced")),
        price_ref_file=pl.when(use_ref).then("ref_file"),
        price_src_row=pl.when(use_pr).then("print_src_row"),
        unpriced_reason=pl.when(use_ref | use_pr).then(pl.lit("")).otherwise(pl.lit(
            f"no reference price within {max_age_s:g}s and no package print within {print_window_s:g}s")),
    ).sort("_qid").drop("_qid", "ref_ts", "ref_px", "ref_file", "print_ts", "print_px", "print_src_row")
    return out.rename({"coin": coin_col, "t": ts_col}) if (coin_col, ts_col) != ("coin", "t") else out


# ---------------------------------------------------------------------------------------------- checks

def print_panel(fills: pl.DataFrame, asof: datetime, every: str = "1m") -> pl.DataFrame:
    """Package trade prints (core perps, trades only), last print and VWAP per coin per bucket."""
    f = pit(fills, asof).filter(pl.col("eligible") & (pl.col("event_kind") == "trade"))
    return (f.sort("ts").group_by_dynamic("ts", every=every, group_by="symbol", label="right", closed="right")
            .agg(last_print=pl.col("price").last(), vwap=(pl.col("notional").sum() / pl.col("size").sum()),
                 n_prints=pl.len(), last_print_src_row=pl.col("src_row").last())
            .rename({"symbol": "coin"}).sort("coin", "ts"))


def coverage(ref: pl.DataFrame | pl.LazyFrame, coins: list[str], asof: datetime, cutoff: datetime) -> pl.DataFrame:
    """One row per coin that is traded in eligible fills: does the reference cover it up to the cutoff?"""
    r = (_lazy(ref).filter(pl.col("ts") <= asof).group_by("coin")
         .agg(ref_first=pl.col("ts").min(), ref_last=pl.col("ts").max(), ref_rows=pl.len())
         .collect(engine="streaming"))
    any_ref = r.height > 0
    base = pl.DataFrame({"coin": sorted(coins)}, schema={"coin": pl.String})
    out = base.join(r, on="coin", how="left").with_columns(ref_rows=pl.col("ref_rows").fill_null(0))
    end = min(asof, cutoff)
    return out.with_columns(
        ref_flag=pl.when(pl.col("ref_rows") == 0).then(pl.lit("no_reference_coverage"))
        .when(pl.col("ref_last") < pl.lit(end).dt.offset_by("-1d")).then(pl.lit("reference_ends_early"))
        .otherwise(pl.lit("ok")),
        ref_reason=pl.when(pl.col("ref_rows") == 0).then(
            pl.lit("no reference rows for coin" if any_ref else "no reference files in data/reference/prices"))
        .when(pl.col("ref_last") < pl.lit(end).dt.offset_by("-1d")).then(pl.lit("last reference > 1 day before asof"))
        .otherwise(pl.lit("")),
    ).sort("coin")


def compare_to_prints(ref: pl.DataFrame | pl.LazyFrame, fills: pl.DataFrame, asof: datetime, tolerance_bps: float,
                      window_s: int) -> pl.DataFrame:
    """For every package trade print, the latest reference price known at or before it, at most window_s old.

    cmp_flag: ok | disagree (|print/ref - 1| beyond tolerance_bps) | no_reference_in_window. Point in time:
    only reference prices known by the print's own timestamp are used.
    """
    p = (pit(fills, asof).filter(pl.col("eligible") & (pl.col("event_kind") == "trade"))
         .select(pl.col("symbol").alias("coin"), pl.col("ts").alias("print_ts"), pl.col("price").alias("print_px"),
                 pl.col("src_row").alias("print_src_row")).sort("print_ts", "print_src_row"))
    cand = _candidates(ref, p.select("coin", t="print_ts"), asof, window_s) if p.height else \
        pl.DataFrame(schema=REF_SCHEMA)
    j = p.join_asof(cand.select("coin", ref_ts="ts", ref_px="price", ref_file="ref_file").sort("ref_ts"),
                    left_on="print_ts", right_on="ref_ts", by="coin", strategy="backward",
                    tolerance=f"{int(window_s * 1000)}ms", check_sortedness=False)
    return j.with_columns(diff_bps=(pl.col("print_px") / pl.col("ref_px") - 1) * 1e4).with_columns(
        cmp_flag=pl.when(pl.col("ref_px").is_null()).then(pl.lit("no_reference_in_window"))
        .when(pl.col("diff_bps").abs() > tolerance_bps).then(pl.lit("disagree"))
        .otherwise(pl.lit("ok"))
    ).sort("coin", "print_ts", "print_src_row")
