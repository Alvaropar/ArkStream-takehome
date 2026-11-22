"""Drift: aggTrades source, development/stress split, holdout guard, approximate drift limits, pooling."""

import io
import zipfile
from datetime import date, timedelta

import polars as pl
import pytest
from conftest import make_fills, ts

from arkstream import drift
from arkstream.config import load_context


def _rules(**kw):
    base = dict(est_start=date(2025, 10, 9), est_end=date(2025, 10, 11), exclude=frozenset({date(2025, 10, 10)}),
                stress=frozenset({date(2025, 10, 10)}), holdout_start=date(2025, 10, 12), horizons_ms=(1000, 10_000),
                approx_horizons_ms=(300_000,), approx_min_horizon_ms=300_000, max_staleness_s=1.0,
                min_orders_per_cell=1, aggtrades_symbols={"BTC": "BTCUSDT"})
    r = drift.DriftRules(**{**base, **kw})
    r.check()
    return r


def _zip(root, sym, day, rows, header=True):
    p = root / sym / f"{sym}-aggTrades-{day}.zip"
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(drift.AGG_COLS)] if header else []
    lines += [f"{i},{px},1,{i},{i},{int(ts(t).timestamp() * 1000)},false" for i, (t, px) in enumerate(rows)]
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr(f"{sym}-aggTrades-{day}.csv", "\n".join(lines) + "\n")
    return p


def _fills():
    return make_fills([
        dict(ts="2025-10-09 00:00:10", trader="0xa", symbol="BTC", side="buy", size=1.0, start_position=0.0,
             price=100.0, oid=1),
        dict(ts="2025-10-09 00:00:40", trader="0xa", symbol="BTC", side="sell", size=1.0, start_position=1.0,
             price=101.0, oid=2, dir="Close Long"),
        dict(ts="2025-10-10 12:00:00", trader="0xa", symbol="BTC", side="buy", size=1.0, start_position=0.0,
             price=100.0, oid=3),
        dict(ts="2025-10-11 23:59:55", trader="0xa", symbol="BTC", side="sell", size=1.0, start_position=1.0,
             price=100.0, oid=4, dir="Close Long"),
    ])


@pytest.fixture
def src(tmp_path):
    root = tmp_path / "agg"
    _zip(root, "BTCUSDT", "2025-10-09", [("2025-10-09 00:00:09.500", 100.0), ("2025-10-09 00:00:10.500", 101.0),
                                         ("2025-10-09 00:00:19.800", 102.0), ("2025-10-09 00:00:40", 101.0)])
    _zip(root, "BTCUSDT", "2025-10-10", [("2025-10-10 11:59:59.900", 100.0), ("2025-10-10 12:00:00.900", 99.0),
                                         ("2025-10-10 12:00:09.500", 98.0)], header=False)
    _zip(root, "BTCUSDT", "2025-10-11", [("2025-10-11 23:59:54.500", 100.0), ("2025-10-11 23:59:55.500", 100.5)])
    _zip(root, "BTCUSDT", "2025-10-12", [("2025-10-12 00:00:01", 200.0)])  # holdout: must never be read
    return drift.AggTradesSource(root, _rules(), require_manifest=False)


def test_drift_sign_staleness_and_horizon_end(src):
    r = _rules()
    orders = drift.leader_orders(_fills(), ts("2025-10-09 00:00:00"), r.est_end_ts)
    m = drift.aggtrades_drift(orders, src, r).sort("t", "horizon_ms")
    d9 = m.filter(pl.col("oid") == 1)
    assert d9["drift_bps"].to_list() == pytest.approx([100.0, 200.0])      # buy into a rising price costs
    d10 = m.filter(pl.col("oid") == 3)                                     # 12:00:10 -> last trade 09.5 is fresh
    assert d10["drift_bps"].to_list() == pytest.approx([-100.0, -200.0])
    late = m.filter(pl.col("oid") == 4)                                    # t + 10 s passes the window end
    assert late.filter(pl.col("horizon_ms") == 10_000)["reason"].to_list() == ["horizon_past_estimation_end"]
    assert late.filter(pl.col("horizon_ms") == 10_000)["drift_bps"].to_list() == [None]
    # a sell copied 1 s late at a higher price is a gain to the follower: negative drift (cost)
    assert late.filter(pl.col("horizon_ms") == 1000)["drift_bps"].to_list() == pytest.approx([-50.0])


def test_stale_binance_trade_not_used(tmp_path):
    root = tmp_path / "agg"
    _zip(root, "BTCUSDT", "2025-10-09", [("2025-10-09 00:00:05", 100.0), ("2025-10-09 00:00:10.500", 101.0)])
    s = drift.AggTradesSource(root, _rules(), require_manifest=False)
    orders = drift.leader_orders(_fills(), ts("2025-10-09 00:00:00"), ts("2025-10-09 00:00:11"))
    m = drift.aggtrades_drift(orders, s, _rules()).filter(pl.col("horizon_ms") == 1000)
    assert m["reason"].to_list() == ["stale_binance_trade"] and m["drift_bps"].to_list() == [None]


def test_holdout_files_are_refused(src):
    with pytest.raises(drift.HoldoutLeak):
        src.day("BTCUSDT", date(2025, 10, 12))
    with pytest.raises(drift.HoldoutLeak):
        _rules(est_end=date(2025, 10, 12))                                 # window touching the holdout


def _empty_ref():
    return pl.DataFrame(schema={"ts": pl.Datetime("ms", "UTC"), "coin": pl.String, "price": pl.Float64}).lazy()


def test_development_excludes_stress_days_and_stress_reported_apart(src):
    r = _rules()
    out = drift.estimate(_fills(), _empty_ref(), src, r, 60, 60)
    dev, st = out["development"], out["stress"]
    assert dev["origin"].unique().to_list() == [date(2025, 10, 12)]       # default: the day after est_end
    dev_all = dev.filter((pl.col("band") == "all") & (pl.col("horizon_ms") == 1000))
    st_all = st.filter((pl.col("band") == "all") & (pl.col("horizon_ms") == 1000))
    assert dev_all["orders"].to_list() == [3] and st_all["orders"].to_list() == [1]   # 10-09 x2, 10-11; 10-10
    assert st_all["mean_bps"].to_list() == pytest.approx([-100.0])
    assert set(dev["band"]) == {"6-24h", "all"}  # median of a 30 s and a 36 h trip; pooled by band, not leader
    assert "trader" not in dev.columns


def test_each_origin_uses_only_data_before_it(src):
    """Origin 10-10 sees only 10-09 orders; origin 10-12 sees all. Stress (10-10) exists only after 10-10."""
    r = _rules(origins=(date(2025, 10, 10), date(2025, 10, 12)))
    out = drift.estimate(_fills(), _empty_ref(), src, r, 60, 60)
    dev = out["development"].filter((pl.col("band") == "all") & (pl.col("horizon_ms") == 1000)).sort("origin")
    assert dev["origin"].to_list() == [date(2025, 10, 10), date(2025, 10, 12)]
    assert dev["orders"].to_list() == [2, 3] and dev["last_day"].to_list() == [date(2025, 10, 9), date(2025, 10, 11)]
    assert dev["window_end"].to_list() == [date(2025, 10, 9), date(2025, 10, 11)]
    assert out["stress"]["origin"].unique().to_list() == [date(2025, 10, 12)]   # nothing borrowed for 10-10
    # holding bands are recomputed per origin: at 10-10 only the 30 s round trip has closed
    b = out["bands"].sort("origin")
    assert b["band"].to_list() == ["<1m", "6-24h"]


def test_horizon_crossing_the_origin_loses_its_drift():
    per = pl.DataFrame({"t": [ts("2025-10-09 23:59:58"), ts("2025-10-09 23:59:58")], "horizon_ms": [1000, 10_000],
                        "drift_bps": [5.0, 7.0], "reason": ["", ""],
                        "day": [date(2025, 10, 9)] * 2}).with_columns(pl.col("t").dt.cast_time_unit("ms"))
    x = drift.at_origin(per, date(2025, 10, 10))
    assert x["drift_bps"].to_list() == [5.0, None] and x["reason"].to_list() == ["", "horizon_past_origin"]
    assert drift.at_origin(per, date(2025, 10, 9)).height == 0


def test_origin_after_the_estimation_window_is_refused():
    with pytest.raises(drift.HoldoutLeak):
        _rules(origins=(date(2025, 10, 13),))
    with pytest.raises(ValueError, match="no history"):
        _rules(origins=(date(2025, 10, 9),))


def test_pool_leaves_small_cells_empty():
    per = pl.DataFrame({"trader": ["0xa", "0xa"], "oid": [1, 2], "coin": ["BTC", "BTC"],
                        "t": [ts("2025-10-09 00:00:00")] * 2, "day": [date(2025, 10, 9)] * 2, "sign": [1, 1],
                        "src_row": [2, 3], "horizon_ms": [1000, 1000], "drift_bps": [1.0, 3.0], "reason": ["", ""],
                        "source": ["aggtrades"] * 2, "price_source": ["x"] * 2})
    bands = pl.DataFrame({"trader": ["0xa"], "band": ["<1m"]})
    p = drift.pool(per, bands, _rules(min_orders_per_cell=3), "development")
    assert p["estimate"].unique().to_list() == ["too_few_orders"] and p["mean_bps"].null_count() == p.height
    p = drift.pool(per, bands, _rules(min_orders_per_cell=2), "development")
    assert p["mean_bps"].to_list() == [2.0, 2.0]


def test_klines_never_measure_drift_under_five_minutes():
    with pytest.raises(ValueError, match="300"):
        _rules(approx_horizons_ms=(60_000,))
    r = _rules()
    orders = drift.leader_orders(_fills(), ts("2025-10-09 00:00:00"), r.est_end_ts)
    with pytest.raises(ValueError, match="under 300"):
        drift.approx_drift(orders, pl.DataFrame().lazy(), _fills(), r, [10_000], 60, 60)


def _apx(ref_rows, min_basis_obs=1):
    r = _rules(aggtrades_symbols={}, min_basis_obs=min_basis_obs)
    ref = pl.DataFrame(ref_rows, schema={"ts": pl.Datetime("us", "UTC"), "coin": pl.String, "price": pl.Float64},
                       orient="row").with_columns(pl.col("ts").dt.cast_time_unit("ms"))
    orders = drift.leader_orders(_fills(), ts("2025-10-09 00:00:00"), ts("2025-10-09 00:00:20"))
    return drift.approx_drift(orders, ref.lazy(), _fills(), r, [300_000], 60, 60)


def test_approx_drift_from_fill_price_labelled():
    m = _apx([(ts("2025-10-09 00:00:00"), "BTC", 100.0), (ts("2025-10-09 00:05:00"), "BTC", 102.0)])
    assert m["source"].to_list() == ["approx_fill_to_reference"] and m["reason"].to_list() == [""]
    assert m["drift_bps"].to_list() == pytest.approx([200.0])             # no basis: fill 100 -> reference 102


def test_approx_drift_adds_back_the_venue_basis():
    """Hyperliquid fill 100 when Binance is at 99.5 (basis +50 bps); Binance then 102: drift on Binance is
    102 / 99.5 - 1, not 102 / 100 - 1."""
    m = _apx([(ts("2025-10-09 00:00:00"), "BTC", 99.5), (ts("2025-10-09 00:05:00"), "BTC", 102.0)])
    assert m["drift_bps"].to_list() == pytest.approx([(102 / 99.5 - 1) * 1e4])


def test_approx_drift_without_a_basis_is_unmeasured():
    m = _apx([(ts("2025-10-09 00:00:00"), "BTC", 99.5), (ts("2025-10-09 00:05:00"), "BTC", 102.0)], min_basis_obs=2)
    assert m["drift_bps"].to_list() == [None] and m["reason"].to_list() == ["no_basis_estimate"]


def test_approx_drift_with_a_huge_basis_is_unmeasured():
    """Fill 100 against Binance 80 (+2,500 bps): not the same asset, so no drift rather than a big correction."""
    m = _apx([(ts("2025-10-09 00:00:00"), "BTC", 80.0), (ts("2025-10-09 00:05:00"), "BTC", 82.0)])
    assert m["drift_bps"].to_list() == [None] and m["reason"].to_list() == ["basis_too_large"]


def test_approx_drift_to_a_package_print_is_not_corrected():
    """No reference at t + 5 min: the package's own (Hyperliquid) print is used, same venue as the fill."""
    m = _apx([(ts("2025-10-09 00:00:00"), "BTC", 99.0)])
    assert m["price_source"].to_list() == ["unpriced"]                    # no print within 60 s of 00:05:10
    f = make_fills([dict(ts="2025-10-09 00:00:10", trader="0xa", symbol="BTC", side="buy", size=1.0,
                         start_position=0.0, price=100.0, oid=1),
                    dict(ts="2025-10-09 00:05:05", trader="0xb", symbol="BTC", side="sell", size=1.0,
                         start_position=0.0, price=103.0, oid=9)])
    r = _rules(aggtrades_symbols={}, min_basis_obs=1)
    ref = pl.DataFrame({"ts": [ts("2025-10-09 00:00:00")], "coin": ["BTC"], "price": [99.0]}).with_columns(
        pl.col("ts").dt.cast_time_unit("ms"))
    orders = drift.leader_orders(f, ts("2025-10-09 00:00:00"), ts("2025-10-09 00:00:20"))
    m = drift.approx_drift(orders, ref.lazy(), f, r, [300_000], 60, 60)
    assert m["price_source"].to_list() == ["package_print"]
    assert m["drift_bps"].to_list() == pytest.approx([300.0])            # 100 -> 103, both Hyperliquid


def test_lake_aggtrades_copy_refused(tmp_path):
    with pytest.raises(ValueError, match="incomplete"):
        drift.AggTradesSource(tmp_path / "venue=binance" / "dataset=binance.um.agg_trades", _rules(), False)
    with pytest.raises(FileNotFoundError, match="MANIFEST"):
        drift.AggTradesSource(tmp_path, _rules(), require_manifest=True)


def test_config_rules_keep_holdout_out():
    r = drift.DriftRules.from_config(load_context().raw)
    assert r.est_end == date(2025, 12, 2) and r.holdout_start == date(2025, 12, 3)
    assert r.origin_dates == (date(2025, 10, 8), date(2025, 10, 22), date(2025, 11, 5), date(2025, 11, 19),
                              date(2025, 12, 3))
    assert r.est_start <= date(2025, 10, 8) - timedelta(days=30)        # history before the first origin
    assert r.exclude == r.stress == frozenset({date(2025, 10, 10), date(2025, 10, 11)})
    assert r.approx_min_horizon_ms == 300_000 and min(r.approx_horizons_ms) >= 300_000


def test_header_and_headerless_zips_read_alike(tmp_path):
    a = _zip(tmp_path / "a", "X", "2025-10-09", [("2025-10-09 00:00:01", 1.0)], header=True)
    b = _zip(tmp_path / "b", "X", "2025-10-09", [("2025-10-09 00:00:01", 1.0)], header=False)
    assert drift.read_aggtrades_zip(a).equals(drift.read_aggtrades_zip(b))
    assert io  # noqa: B018 (imported for symmetry with the writer)
