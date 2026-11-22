"""Funding table: parsing, two times (accrual hour vs known_at), point in time, cutoff, gaps never filled."""

import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from arkstream import funding as fu

H = 3_600_000
S = int(fu.START.timestamp() * 1000)


def _write(tmp_path, pages: dict[str, list[dict]]):
    d = tmp_path / "funding"
    rows = []
    for coin, recs in pages.items():
        rel = f"funding/{coin}/{coin}-{S}.json"
        raw = json.dumps(recs).encode()
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(raw)
        rows.append({"coin": coin, "start_ms": S, "file": rel, "bytes": len(raw),
                     "sha256": hashlib.sha256(raw).hexdigest()})
    with open(d / "MANIFEST.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return tmp_path


def _rec(coin, i, rate=1e-5, jitter=31):
    return {"coin": coin, "fundingRate": str(rate), "premium": "0.0002", "time": S + i * H + jitter}


def test_parse_two_times_and_point_in_time(tmp_path):
    d = _write(tmp_path, {"BTC": [_rec("BTC", i) for i in range(3)]})
    t = fu.load_funding(d, datetime(2026, 1, 4, tzinfo=UTC))
    assert t.columns == ["ts_hour", "known_at", "coin", "funding_rate", "premium", "src_file"]
    r = t.row(0, named=True)
    assert r["ts_hour"] == fu.START and r["known_at"] == fu.START + timedelta(milliseconds=31)
    assert r["src_file"] == f"funding/BTC/BTC-{S}.json"
    # asof between the accrual hour and the raw time: the hour-0 rate is not yet known
    between = fu.START + timedelta(milliseconds=10)
    assert fu.funding_asof(t, between).height == 0
    assert fu.funding_asof(t, fu.START + timedelta(milliseconds=31)).height == 1


def test_cutoff_filters_rows(tmp_path):
    d = _write(tmp_path, {"BTC": [_rec("BTC", i) for i in range(5)]})
    cut = fu.START + timedelta(hours=2, milliseconds=30)  # hour-2 rate published at +31 ms: after the cutoff
    t = fu.load_funding(d, cut)
    assert t["ts_hour"].max() == fu.START + timedelta(hours=1)


def test_gaps_flagged_never_filled(tmp_path):
    d = _write(tmp_path, {"BTC": [_rec("BTC", i) for i in (0, 1, 4, 5)], "PURR": [_rec("PURR", i) for i in (2, 3)]})
    asof = fu.START + timedelta(hours=5, minutes=30)
    t = fu.load_funding(d, asof)
    assert t.height == 6  # nothing added
    coins = pl.DataFrame({"coin": ["BTC", "PURR", "NEW"]})
    g = fu.gaps(t, coins, asof)
    got = {(r["coin"], r["reason"]): r["hours"] for r in g.iter_rows(named=True)}
    assert got == {("BTC", "internal_gap"): 2, ("PURR", "before_first_rate"): 2,
                   ("PURR", "after_last_rate"): 2, ("NEW", "no_funding_rows"): 6}
    cov = fu.coverage(t, coins, asof).sort("coin")
    assert cov["flag"].to_list() == ["internal_gap", "no_funding", "partial_listing"]
    assert cov["expected_hours"].unique().to_list() == [6]


def test_last_expected_hour_respects_publication_lag():
    h = fu.START + timedelta(hours=3)
    assert fu.last_expected_hour(h + timedelta(milliseconds=5)) == h - timedelta(hours=1)
    assert fu.last_expected_hour(h + timedelta(minutes=5)) == h
    assert fu.last_expected_hour(h + timedelta(minutes=4)) == h - timedelta(hours=1)


def test_manifest_enforced(tmp_path):
    d = _write(tmp_path, {"BTC": [_rec("BTC", 0)]})
    (d / "funding" / "BTC" / "stray.json").write_text("[]")
    with pytest.raises(fu.HyperliquidManifestError, match="not listed"):
        fu.load_funding(d, datetime(2026, 1, 4, tzinfo=UTC))
    (d / "funding" / "BTC" / "stray.json").unlink()
    (d / "funding" / "BTC" / f"BTC-{S}.json").write_text("[ ]")
    with pytest.raises(fu.HyperliquidManifestError, match="differ"):
        fu.load_funding(d, datetime(2026, 1, 4, tzinfo=UTC))


def test_conflicting_duplicate_hour_raises(tmp_path):
    d = _write(tmp_path, {"BTC": [_rec("BTC", 0, 1e-5), _rec("BTC", 0, 2e-5, jitter=40)]})
    with pytest.raises(fu.HyperliquidManifestError, match="conflicting"):
        fu.load_funding(d, datetime(2026, 1, 4, tzinfo=UTC))


def test_user_funding_check_convention():
    """A daily record (stamped D 00:00) sums -position x price x rate over the hours of D with a position."""
    day = fu.START + timedelta(days=1)
    hours = [day + timedelta(hours=k) for k in range(24)]
    # long 0.1 from before the day until a sell at 10:30 to flat: held hours 00:00 .. 10:00 = 11 samples
    ledger = pl.DataFrame({"trader": ["a", "a"], "symbol": ["BTC", "BTC"],
                           "ts": [fu.START, day + timedelta(hours=10, minutes=30)], "pos_after": [0.1, 0.0],
                           "src_row": [1, 2]}).with_columns(pl.col("ts").dt.cast_time_unit("ms"))
    rates = pl.DataFrame({"coin": "BTC", "ts_hour": hours, "funding_rate": 1e-4}).with_columns(
        pl.col("ts_hour").dt.cast_time_unit("ms"))
    prices = rates.select("coin", "ts_hour", price=pl.lit(100_000.0))
    actual = -0.1 * 100_000.0 * 1e-4 * 11  # longs pay a positive rate
    uf = pl.DataFrame({"trader": ["a"], "coin": ["BTC"], "ts_hour": [day], "usdc": [actual], "szi": [0.1],
                       "rate": [1e-4], "n_samples": [11]}).with_columns(pl.col("ts_hour").dt.cast_time_unit("ms"))
    c = fu.user_funding_check(uf, ledger, rates, prices).row(0, named=True)
    assert c["held_hours"] == 11 and c["samples_ok"] and c["sign_ok"] and c["rate_ok"]
    assert c["amount_known"] and c["amount_ok"] and c["calc_usdc"] == pytest.approx(actual)
    # a missing proxy price in a held hour makes the amount unknown, never filled
    c2 = fu.user_funding_check(uf, ledger, rates, prices.filter(pl.col("ts_hour") != hours[3])).row(0, named=True)
    assert not c2["amount_known"] and c2["amount_rel_err"] is None


def _candles(tmp_path, bars):
    d = tmp_path / "candles_4h"
    rel = "candles_4h/BTC/BTC-0.json"
    raw = json.dumps(bars).encode()
    (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / rel).write_bytes(raw)
    with open(d / "MANIFEST.csv", "w", newline="", encoding="utf-8") as fh:
        fh.write("coin,start_ms,file,bytes,sha256\n"
                 f"BTC,0,{rel},{len(raw)},{hashlib.sha256(raw).hexdigest()}\n")
    return tmp_path


def _bar(t_ms, c, n=10):
    return {"t": t_ms, "T": t_ms + 4 * H - 1, "s": "BTC", "i": "4h", "o": "1", "c": str(c), "h": "1", "l": "1",
            "v": "1", "n": n}


def test_candles_known_at_close_and_drops(tmp_path):
    from arkstream import hlprices as hp
    d = _candles(tmp_path, [_bar(S, 100), _bar(S + 4 * H, 101, n=0), _bar(S + 8 * H, 102)])
    cut = fu.START + timedelta(hours=11)  # the third bar closes at +12 h: after the cutoff
    c, dropped = hp.load_candles(d, cut)
    assert c["ts"].to_list() == [fu.START + timedelta(hours=4)]  # known at open + 4 h, not at the open
    assert c["source"].to_list() == ["hyperliquid_4h"]
    assert sorted(dropped["drop_reason"].to_list()) == ["close_after_cutoff", "no_trades_in_bar"]


def test_compare_bars_uses_reference_at_close(tmp_path):
    from arkstream import hlprices as hp
    d = _candles(tmp_path, [_bar(S, 100.1)])
    c, _ = hp.load_candles(d, datetime(2026, 1, 4, tzinfo=UTC))
    close = fu.START + timedelta(hours=4)
    ref = pl.DataFrame({"ts": [fu.START + timedelta(minutes=1), close], "coin": ["BTC", "BTC"], "price": [90.0, 100.0],
                        "ref_file": ["x", "x"]}).with_columns(pl.col("ts").dt.cast_time_unit("ms"))
    fills = pl.DataFrame(schema={"symbol": pl.String, "ts": pl.Datetime("ms", "UTC"), "price": pl.Float64,
                                 "src_row": pl.Int64, "eligible": pl.Boolean, "event_kind": pl.String})
    b = hp.compare_bars(c, ref, fills, datetime(2026, 1, 4, tzinfo=UTC), 60).row(0, named=True)
    assert b["ref_px"] == 100.0 and b["gap_bps"] == pytest.approx(10.0)
    res = hp.price_check(hp.compare_bars(c, ref, fills, datetime(2026, 1, 4, tzinfo=UTC), 60), ["BTC", "PURR"],
                         {"PURR"}, min_n=1)
    assert res["outcome"].to_list() == ["pass", "no_binance"]
