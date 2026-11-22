"""Kline reference prices: validity windows, zero-volume bars, price factor, bar-close timing, manifest."""

from datetime import date

import polars as pl
import pytest
from conftest import ts

from arkstream import refprices as rf
from arkstream.prices import ReferenceManifestError, load_reference, price_asof

NS = 1_000_000_000
CUT = ts("2025-10-03 23:59:59")


def _ns(s: str) -> int:
    return int(ts(s).timestamp()) * NS


def _lake(tmp_path, bars: dict[str, list[tuple[str, float, float]]]):
    """bars: symbol -> [(bar close 'YYYY-MM-DD HH:MM:SS', close, volume)], partitioned like the real lake
    (date = the bar's open date)."""
    lake = tmp_path / "lake"
    for sym, rows in bars.items():
        df = pl.DataFrame({"symbol": sym, "ts_known": [_ns(r[0]) for r in rows],
                           "close": [r[1] for r in rows], "volume": [r[2] for r in rows]})
        df = df.with_columns(ts_event=pl.col("ts_known"), open_date=pl.from_epoch(pl.col("ts_known") - 60 * NS, "ns")
                             .dt.strftime("%Y-%m-%d"))
        for (d,), part in df.group_by("open_date"):
            p = lake / rf.KLINES_SUBDIR / f"symbol={sym}" / f"date={d}"
            p.mkdir(parents=True, exist_ok=True)
            part.drop("open_date").write_parquet(p / "part-0.parquet")
    return lake


def _map(rows: list[dict]) -> pl.DataFrame:
    base = {"price_factor_hl_per_binance": 1.0, "binance_listed": None, "hl_first_fill": "2025-10-01",
            "hl_last_fill": "2025-10-03", "fills": 1, "notional_usd": 1, "notional_pct": 0.0}
    df = pl.DataFrame([{**base, **r} for r in rows])
    return df.with_columns([pl.col(c).cast(pl.String).str.to_date() for c in ("binance_listed", "hl_first_fill",
                                                                                "hl_last_fill")])


@pytest.fixture
def lake(tmp_path):
    return _lake(tmp_path, {
        # live throughout; a zero-volume bar at 10-02 00:03 must vanish, not be carried forward
        "AAAUSDT": [("2025-10-01 00:01:00", 10.0, 5.0), ("2025-10-02 00:02:00", 11.0, 5.0),
                    ("2025-10-02 00:03:00", 11.0, 0.0), ("2025-10-03 12:00:00", 12.0, 1.0),
                    ("2025-10-04 00:00:00", 13.0, 1.0)],  # 23:59 bar of 10-03, known after the cutoff
        # an old token with the same ticker before 10-02, then the real listing
        "BBBUSDT": [("2025-10-01 06:00:00", 0.59, 7.0), ("2025-10-02 06:00:00", 3.90, 7.0),
                    ("2025-10-03 06:00:00", 3.95, 7.0)],
        # quoted per 1000 tokens on Binance
        "KCCCUSDT": [("2025-10-01 06:00:00", 0.002, 1.0), ("2025-10-02 06:00:00", 0.003, 1.0)],
        # frozen contract: only zero-volume bars
        "DDDUSDT": [("2025-10-01 06:00:00", 1.59, 0.0), ("2025-10-02 06:00:00", 1.59, 0.0)],
        # delisted: trades until 09:01 on 10-02, flat zero-volume bars after
        "EEEUSDT": [("2025-10-01 06:00:00", 4.0, 2.0), ("2025-10-02 09:01:00", 4.2, 2.0),
                    ("2025-10-02 12:00:00", 4.2, 0.0), ("2025-10-03 06:00:00", 4.2, 0.0)],
    })


@pytest.fixture
def mapping(lake):
    m = _map([dict(hl="AAA", binance="AAAUSDT"), dict(hl="BBB", binance="BBBUSDT"),
              dict(hl="kCCC", binance="KCCCUSDT", price_factor_hl_per_binance=1000.0),
              dict(hl="DDD", binance="DDDUSDT"), dict(hl="EEE", binance="EEEUSDT"), dict(hl="ZZZ", binance=None)])
    ov = {"BBB": {"kind": "different_asset", "valid_from": "2025-10-02"},
          "EEE": {"kind": "delisting", "valid_to": "2025-10-01"}}
    ev = rf.window_evidence(rf.scan_klines(lake), CUT)
    return rf.apply_windows(m, ev, ov, CUT)


def _ref(lake, mapping):
    return rf.reference_from_klines(rf.scan_klines(lake), mapping, CUT).collect().sort("coin", "ts")


def test_windows_and_computed_status(mapping):
    w = {r["hl"]: (r["valid_from"], r["valid_to"], r["status"]) for r in mapping.iter_rows(named=True)}
    assert w["AAA"] == (date(2025, 10, 1), date(2025, 10, 3), "full")
    assert w["BBB"] == (date(2025, 10, 2), date(2025, 10, 3), "partial")    # semantic override kept
    assert w["DDD"] == (None, None, "never_valid")                          # no live bar at all
    assert w["EEE"][:2] == (date(2025, 10, 1), date(2025, 10, 2))           # requested 10-01, data says 10-02
    assert "corrected to data" in mapping.filter(pl.col("hl") == "EEE")["window_rule"][0]
    assert w["ZZZ"] == (None, None, "unmapped")
    assert set(mapping["status"]) <= set(rf.STATUSES)


def test_never_override_beats_live_data():
    ev = {"bars": 10, "first_live": ts("2025-10-01 00:01:00"), "last_live": ts("2025-10-03 00:00:00")}
    w = rf.derive_window(ev, {"kind": "never", "reason": "frozen"}, CUT)
    assert (w.valid_from, w.valid_to) == (None, None)


def test_bars_outside_window_dropped(lake, mapping):
    r = _ref(lake, mapping)
    bbb = r.filter(pl.col("coin") == "BBB")
    assert bbb["price"].to_list() == [3.90, 3.95]                           # old-token 0.59 bar dropped
    assert r.filter(pl.col("coin") == "DDD").height == 0
    assert r.filter(pl.col("coin") == "EEE")["price"].to_list() == [4.0, 4.2]


def test_zero_volume_bars_dropped_never_carried(lake, mapping):
    r = _ref(lake, mapping)
    aaa = r.filter(pl.col("coin") == "AAA")
    assert aaa["ts"].to_list() == [ts("2025-10-01 00:01:00"), ts("2025-10-02 00:02:00"), ts("2025-10-03 12:00:00")]
    from conftest import make_fills
    no_prints = make_fills([dict(ts="2025-10-01 00:00:00", trader="0xa", symbol="AAA", side="buy", size=1.0,
                                 start_position=0.0)]).head(0)
    q = pl.DataFrame({"coin": ["AAA", "AAA"], "t": [ts("2025-10-02 00:02:30"), ts("2025-10-02 00:03:30")]})
    out = price_asof(q, r.lazy(), no_prints, CUT, max_age_s=60, print_window_s=60)
    assert out["price_source"].to_list() == ["reference", "unpriced"]       # 00:03 bar was zero-volume


def test_price_factor_applied(lake, mapping):
    r = _ref(lake, mapping)
    assert r.filter(pl.col("coin") == "kCCC")["price"].to_list() == pytest.approx([2.0, 3.0])
    assert r.filter(pl.col("coin") == "kCCC")["source_symbol"].unique().to_list() == ["KCCCUSDT"]


def test_known_at_bar_close_and_cutoff(lake, mapping):
    r = _ref(lake, mapping)
    assert r["ts"].max() <= CUT
    assert 13.0 not in r.filter(pl.col("coin") == "AAA")["price"].to_list()  # known 00:00 on 10-04
    assert r["ts"].dt.second().unique().to_list() == [0]                       # bar close, on the minute


def test_files_manifest_and_unexpected_file(lake, mapping, tmp_path):
    out = tmp_path / "prices"
    files = rf.build_reference_files(lake, mapping, CUT, out, {"source": "synthetic"})
    assert [f.name for f in files] == ["binance_um_1m_2025-10.parquet"]
    loaded = load_reference(out)
    assert loaded.height == _ref(lake, mapping).height
    again = tmp_path / "prices2"
    rf.build_reference_files(lake, mapping, CUT, again, {"source": "synthetic"})
    assert (again / files[0].name).read_bytes() == files[0].read_bytes()       # deterministic
    (out / "notes.csv").write_text("x\n", encoding="utf-8")
    with pytest.raises(ReferenceManifestError, match="unexpected file"):
        load_reference(out)


def test_map_roundtrip(mapping, tmp_path):
    p = tmp_path / "map.csv"
    rf.write_map(mapping, p)
    back = rf.load_map(p)
    assert back.columns == rf.MAP_COLUMNS
    assert back.filter(pl.col("hl") == "BBB")["valid_from"][0] == date(2025, 10, 2)
