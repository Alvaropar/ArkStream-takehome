from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from arkstream.config import ROOT, load_context, load_instruments
from arkstream.instruments import annotate_fills

RAW = ROOT / "data" / "raw"


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def make_fills(rows: list[dict]) -> pl.DataFrame:
    """Synthetic annotated fills. Required per row: ts, trader, symbol, side, size, start_position."""
    base = {"dir": "Open Long", "price": 100.0, "fee": 0.0, "fee_token": "USDC", "closed_pnl": 0.0,
            "is_maker": False, "tid": 0, "oid": 0}
    out = []
    for i, r in enumerate(rows):
        d = {**base, **r}
        d["src_row"] = d.get("src_row", i + 2)
        d["tid"] = d["tid"] or 1000 + i
        d["oid"] = d["oid"] or 5000 + i
        d["ts"] = ts(d["ts"]) if isinstance(d["ts"], str) else d["ts"]
        d["notional"] = d["price"] * d["size"]
        out.append(d)
    df = pl.DataFrame(out).with_columns(pl.col("ts").dt.cast_time_unit("ms"), date=pl.col("ts").dt.date())
    return annotate_fills(df, load_instruments())


def need(path: Path, how: str) -> None:
    """Skip a data test when a regenerated (not shipped) input is absent: a clean copy runs it after VERIFY.md."""
    if not path.exists() or (path.is_dir() and not any(path.rglob("*.parquet"))):
        pytest.skip(f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path} not present: {how}")


@pytest.fixture(scope="session")
def ctx():
    return load_context()


@pytest.fixture(scope="session")
def inputs(ctx):
    if not (RAW / "fills.csv").exists():
        pytest.skip("raw inputs not present (make data)")
    from arkstream.pipeline import load_inputs
    return load_inputs(ctx)


@pytest.fixture(scope="session")
def full_build(ctx, inputs):
    from arkstream.pipeline import build
    return build(ctx, inputs)
