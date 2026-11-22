from datetime import timedelta

import polars as pl
import pytest
from conftest import make_fills, ts

from arkstream.prices import (
    MANIFEST_NAME,
    ReferenceManifestError,
    compare_to_prints,
    coverage,
    load_reference,
    manifest_files,
    price_asof,
    write_manifest,
)

T0 = ts("2025-12-01 00:00:00")


def _ref_dir(tmp_path, rows: dict | None = None):
    d = tmp_path / "prices"
    d.mkdir()
    rows = rows or {"timestamp": ["2025-12-01 00:01:00", "2025-12-01 00:02:00", "2025-12-01 00:03:00"],
                    "coin": ["BTC", "BTC", "BTC"], "price": [100.0, 150.0, 100.0]}
    pl.DataFrame(rows).write_csv(d / "btc.csv")
    write_manifest(d, [d / "btc.csv"], {"source": "synthetic"})
    return d


def test_no_reference_files_flags_every_coin(tmp_path, ctx):
    ref = load_reference(tmp_path / "missing")
    cov = coverage(ref, ["ETH", "BTC"], ctx.cutoff, ctx.cutoff)
    assert cov["coin"].to_list() == ["BTC", "ETH"]
    assert cov["ref_flag"].unique().to_list() == ["no_reference_coverage"]


def test_manifest_lists_and_verifies_files(tmp_path):
    d = _ref_dir(tmp_path)
    assert [p.name for p in manifest_files(d)] == ["btc.csv"]
    assert load_reference(d).height == 3


def test_manifest_refuses_unexpected_file(tmp_path):
    d = _ref_dir(tmp_path)
    (d / "hl_binance_map.csv").write_text("hl,binance\nBTC,BTCUSDT\n", encoding="utf-8")  # the M1 build breaker
    with pytest.raises(ReferenceManifestError, match=r"unexpected file.*hl_binance_map\.csv"):
        load_reference(d)


def test_manifest_refuses_changed_or_missing_file(tmp_path):
    d = _ref_dir(tmp_path)
    (d / "btc.csv").write_text("timestamp,coin,price\n2025-12-01 00:01:00,BTC,1.0\n", encoding="utf-8")
    with pytest.raises(ReferenceManifestError, match="(sha256|size)"):
        load_reference(d)
    (d / "btc.csv").unlink()
    with pytest.raises(ReferenceManifestError, match="missing"):
        load_reference(d)


def test_files_without_manifest_are_refused(tmp_path):
    d = _ref_dir(tmp_path)
    (d / MANIFEST_NAME).unlink()
    with pytest.raises(ReferenceManifestError, match="no MANIFEST"):
        load_reference(d)


def test_reference_compared_point_in_time_and_never_imputed(tmp_path, ctx):
    ref = load_reference(_ref_dir(tmp_path))
    fills = make_fills([dict(ts="2025-12-01 00:01:50", trader="0xa", symbol="BTC", side="buy", size=1.0,
                             start_position=0.0, price=100.0),
                        dict(ts="2025-12-01 00:02:55", trader="0xa", symbol="BTC", side="sell", size=1.0,
                             start_position=1.0, price=100.0),
                        dict(ts="2025-12-01 00:00:30", trader="0xa", symbol="BTC", side="buy", size=1.0,
                             start_position=0.0, price=100.0)])
    cmp = compare_to_prints(ref, fills, T0 + timedelta(hours=1), tolerance_bps=50, window_s=60)
    # 00:00:30: no reference known yet; 00:01:50: bar known 00:01 agrees; 00:02:55: bar known 00:02 is 150
    assert cmp["cmp_flag"].to_list() == ["no_reference_in_window", "ok", "disagree"]
    assert cmp["ref_px"].to_list()[0] is None  # flagged, not filled
    cov = coverage(ref, ["BTC", "ETH"], ts("2025-12-01 00:03:00"), ctx.cutoff)
    assert dict(zip(cov["coin"], cov["ref_flag"], strict=True)) == {"BTC": "ok", "ETH": "no_reference_coverage"}


def test_price_asof_reference_then_print_then_unpriced(tmp_path):
    # Bars known at 00:01 and 00:02; the 00:03 bar had zero volume, so it is not in the reference at all.
    ref = load_reference(_ref_dir(tmp_path, {"timestamp": ["2025-12-01 00:01:00", "2025-12-01 00:02:00"],
                                             "coin": ["ETH", "ETH"], "price": [10.0, 11.0]}))
    fills = make_fills([dict(ts="2025-12-01 00:03:40", trader="0xa", symbol="ETH", side="buy", size=1.0,
                             start_position=0.0, price=12.5)])
    q = pl.DataFrame({"coin": ["ETH", "ETH", "ETH", "ETH"],
                      "t": [ts("2025-12-01 00:01:30"), ts("2025-12-01 00:03:00"), ts("2025-12-01 00:04:10"),
                            ts("2025-12-01 00:06:00")]})
    out = price_asof(q, ref, fills, ts("2025-12-01 00:10:00"), max_age_s=60, print_window_s=60)
    assert out["price_source"].to_list() == ["reference", "reference", "package_print", "unpriced"]
    assert out["price"].to_list() == [10.0, 11.0, 12.5, None]  # never carried past 60 s
    assert out["price_src_row"].to_list()[2] == fills["src_row"][0]
    assert out["unpriced_reason"].to_list()[3].startswith("no reference price within 60s")


def test_price_asof_rejects_query_after_asof(tmp_path):
    ref = load_reference(_ref_dir(tmp_path))
    q = pl.DataFrame({"coin": ["BTC"], "t": [ts("2025-12-01 00:05:00")]})
    with pytest.raises(ValueError, match="after asof"):
        price_asof(q, ref, _empty_fills(), ts("2025-12-01 00:04:00"), 60, 60)


def _empty_fills():
    f = make_fills([dict(ts="2025-12-01 00:00:00", trader="0xa", symbol="BTC", side="buy", size=1.0,
                         start_position=0.0)])
    return f.head(0)
