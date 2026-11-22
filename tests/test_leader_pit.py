"""Phase 2 point in time on real data: leader tables are invariant to rows after asof, and a seeded leak
(a round trip closed after asof counted as closed) is caught."""

from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import need, ts
from pit_check import leader_subset, leader_violations

from arkstream import leader
from arkstream.pipeline import positions_asof

T = ts("2025-10-22 00:00:00")  # a development origin


@pytest.fixture(scope="module")
def small(ctx, inputs):
    from arkstream.refprices import KLINES_SUBDIR

    need(ctx.path("binance_lake") / KLINES_SUBDIR, "build it with `refprices --from-zips` (VERIFY.md)")
    return leader_subset(inputs, ctx, T)


@pytest.mark.data
def test_leader_tables_invariant_to_rows_after_asof(ctx, small):
    assert leader_violations(ctx, small, T) == []


@pytest.mark.data
def test_no_leader_timestamp_after_asof(ctx, small):
    import polars as pl
    tabs = leader.compute(ctx, small, T)
    allowed = {"asof", "eq_ts"}
    for name, df in tabs.items():
        for col, dtype in df.schema.items():
            if isinstance(dtype, pl.Datetime) and col not in allowed and df[col].drop_nulls().len():
                assert df[col].drop_nulls().max() <= T, f"{name}.{col} has a timestamp after asof"


@pytest.mark.data
def test_seeded_leak_trip_closed_after_asof_is_caught(ctx, small, monkeypatch):
    week = timedelta(days=7)

    def leaky_pit(df, asof, col="ts"):  # the leak: fills read a week past asof (snapshots stay clean)
        return df.filter(df[col] <= asof + (week if "tid" in df.columns else timedelta(0)))

    def leaky_positions(fills, asof):  # ... and round trips closed in that week counted as closed
        return positions_asof(fills, asof + week)
    monkeypatch.setattr(leader, "pit", leaky_pit)
    monkeypatch.setattr(leader, "positions_asof", leaky_positions)
    caught = leader_violations(ctx, small, T, adversarial=False)
    assert "leader.round_trips" in caught and "leader.trip_summary" in caught, caught

@pytest.mark.data
def test_seeded_hour_before_publication_is_caught(ctx, small, monkeypatch):
    from arkstream import funding
    monkeypatch.setattr(funding, "funding_asof", lambda rates, asof: rates.filter(rates["ts_hour"] <= asof))
    caught = leader_violations(ctx, small, T, adversarial=False)
    assert "leader.funding_payments" in caught
