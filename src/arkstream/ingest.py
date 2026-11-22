"""Raw CSV -> typed, date-partitioned Parquet. Raw files are opened read-only and never modified.

Every row keeps `src_row`: its 1-based line number in the raw file (header = line 1), so any derived
value can be traced back with e.g. `sed -n '<src_row>p' data/raw/fills.csv`.
"""

from __future__ import annotations

import gzip
import io
import shutil
from pathlib import Path

import polars as pl

from arkstream.timeparse import parse_ts_column

TRADER_COLS = ["timestamp", "user", "cross_margin_summary_account_value", "net_deposit", "pnl", "trader",
               "date", "equity"]
FILL_COLS = ["timestamp", "trader", "symbol", "side", "dir", "price", "size", "notional", "fee", "fee_token",
             "closed_pnl", "start_position", "is_maker", "tid", "oid"]
TRADER_FLOATS = ["cross_margin_summary_account_value", "net_deposit", "pnl", "equity"]
FILL_FLOATS = ["price", "size", "notional", "fee", "closed_pnl", "start_position"]


class SchemaError(ValueError):
    pass


def read_raw_csv(path: Path) -> pl.DataFrame:
    """Read every column as a string; sniff gzip from magic bytes, not from the file name."""
    with open(path, "rb") as fh:
        magic = fh.read(2)
    if magic == b"\x1f\x8b":
        with gzip.open(path, "rb") as gz:
            data = gz.read()
        return pl.read_csv(io.BytesIO(data), infer_schema=False)
    return pl.read_csv(path, infer_schema=False)


def _with_src_row(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_row_index("src_row", offset=2).with_columns(pl.col("src_row").cast(pl.Int64))


def _strict_cast(df: pl.DataFrame, cols: list[str], dtype: type[pl.DataType] | pl.DataType) -> pl.DataFrame:
    for c in cols:
        casted = df[c].cast(dtype, strict=False)
        bad = casted.is_null() & df[c].is_not_null()
        if bad.any():
            raise SchemaError(f"{c}: {int(bad.sum())} values fail cast to {dtype}")
        df = df.with_columns(casted.alias(c))
    return df


def type_traders(raw: pl.DataFrame) -> pl.DataFrame:
    if raw.columns != TRADER_COLS:
        raise SchemaError(f"traders columns {raw.columns} != {TRADER_COLS}")
    df = parse_ts_column(_with_src_row(raw))
    df = _strict_cast(df, TRADER_FLOATS, pl.Float64)
    df = df.with_columns(pl.col("date").str.to_date("%Y-%m-%d", strict=True))
    return df.select("src_row", "ts", "trader", "user", "date", "equity", "cross_margin_summary_account_value",
                     "net_deposit", "pnl", pl.col("timestamp").alias("raw_timestamp"))


def type_fills(raw: pl.DataFrame) -> pl.DataFrame:
    if raw.columns != FILL_COLS:
        raise SchemaError(f"fills columns {raw.columns} != {FILL_COLS}")
    df = parse_ts_column(_with_src_row(raw))
    df = _strict_cast(df, FILL_FLOATS, pl.Float64)
    df = _strict_cast(df, ["tid", "oid"], pl.Int64)
    if not df["is_maker"].is_in(["true", "false"]).all():
        raise SchemaError("is_maker not in {true,false}")
    if not df["side"].is_in(["buy", "sell"]).all():
        raise SchemaError("side not in {buy,sell}")
    df = df.with_columns(pl.col("is_maker") == "true", date=pl.col("ts").dt.date())
    return df.select("src_row", "ts", "date", "trader", "symbol", "side", "dir", "price", "size", "notional",
                     "fee", "fee_token", "closed_pnl", "start_position", "is_maker", "tid", "oid",
                     pl.col("timestamp").alias("raw_timestamp"))


def write_partitioned(df: pl.DataFrame, dest: Path, sort_by: list[str]) -> list[Path]:
    """One deterministic file per date: date=YYYY-MM-DD/part-0.parquet, rows sorted by `sort_by`."""
    if dest.exists():
        shutil.rmtree(dest)
    written = []
    df = df.sort(sort_by, maintain_order=True)
    for (d,), part in df.group_by(["date"], maintain_order=True):
        p = dest / f"date={d.isoformat()}" / "part-0.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        part.drop("date").write_parquet(p, compression="zstd", statistics=True, row_group_size=1 << 20)
        written.append(p)
    return sorted(written)


def load_processed(dest: Path) -> pl.DataFrame:
    return pl.read_parquet(dest / "**" / "*.parquet", hive_partitioning=True).sort("src_row")


def ingest_all(traders_csv: Path, fills_csv: Path, processed: Path) -> dict[str, list[Path]]:
    traders = type_traders(read_raw_csv(traders_csv))
    fills = type_fills(read_raw_csv(fills_csv))
    return {
        "traders": write_partitioned(traders, processed / "traders", ["date", "src_row"]),
        "fills": write_partitioned(fills, processed / "fills", ["date", "src_row"]),
    }
