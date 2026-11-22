"""Rule 1: an output computed at asof=T must not change when rows after T are appended or removed."""

from datetime import timedelta

import pytest
from conftest import ts
from pit_check import pit_violations

from arkstream.pipeline import build

T = ts("2025-10-15 15:39:40.221")  # deliberately inside a busy millisecond


@pytest.mark.data
def test_outputs_invariant_to_rows_after_asof(ctx, inputs):
    assert pit_violations(ctx, inputs, T) == []


@pytest.mark.data
def test_no_row_after_asof_used(ctx, inputs):
    import polars as pl
    res = build(ctx, inputs, T)
    for name, df in res.tables.items():
        for col, dtype in df.schema.items():
            if isinstance(dtype, pl.Datetime) and col not in ("asof",) and df[col].drop_nulls().len():
                assert df[col].drop_nulls().max() <= T, f"{name}.{col} has a timestamp after asof"


def test_asof_capped_at_cutoff(ctx):
    from arkstream.pipeline import effective_asof
    assert effective_asof(ctx, ctx.cutoff + timedelta(days=30)) == ctx.cutoff
    assert effective_asof(ctx, None) == ctx.cutoff
