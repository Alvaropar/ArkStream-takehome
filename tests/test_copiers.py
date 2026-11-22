from datetime import timedelta

import polars as pl
import pytest
from conftest import make_fills, ts

from arkstream import copiers


def _orders_frame():
    rows = []
    t0 = ts("2025-10-01 00:00:00")
    for i in range(60):
        t = t0 + timedelta(minutes=37 * i)
        coin, side = ("BTC", "ETH")[i % 2], ("buy", "sell")[(i // 2) % 2]
        rows.append(dict(ts=t, trader="0xaaaa0000", symbol=coin, side=side, size=1.0, start_position=0.0, oid=1 + i))
        rows.append(dict(ts=t + timedelta(seconds=3), trader="0xbbbb0000", symbol=coin, side=side, size=0.5,
                         start_position=0.0, oid=1000 + i))
        rows.append(dict(ts=t + timedelta(minutes=11), trader="0xcccc0000", symbol=coin, side=side, size=2.0,
                         start_position=0.0, oid=2000 + i))
    return make_fills(rows)


def test_copier_detected_with_placebo_size_ratio_and_lag():
    f = _orders_frame()
    cfg = dict(window_s=30, min_orders_leader=30, min_match_share=0.25, placebo_multiple=3, placebo_shifts=10,
               placebo_max_shift_s=86400, seed=1)
    r = copiers.screen(f, ts("2026-01-01 00:00:00"), cfg)
    fl = r["flagged"].filter(pl.col("confirmed"))
    assert fl.select("leader", "follower").rows() == [("0xaaaa0000", "0xbbbb0000")]
    row = fl.row(0, named=True)
    assert row["match_share"] == 1.0 and row["placebo_p95"] < 0.2
    assert row["lag_p50"] == pytest.approx(3.0)
    assert row["log_size_ratio_median"] == pytest.approx(-0.6931, abs=1e-3) and row["log_size_ratio_iqr"] == 0
    cl = r["clusters"]
    assert cl.filter("is_original")["trader"].to_list() == ["0xaaaa0000"]


@pytest.mark.data
def test_real_cluster_0x890e(full_build):
    cl = full_build.tables["copier_clusters"]
    cid = cl.filter(pl.col("trader").str.starts_with("0x890e"))["cluster_id"][0]
    members = {t[:6] for t in cl.filter(pl.col("cluster_id") == cid)["trader"]}
    assert {"0x890e", "0xd9ea", "0xa112", "0x8f30"} <= members
