"""Monthly kline fetcher (offline) and the zip -> lake -> reference price path (item 9 of the pre-Phase 4 brief)."""

import hashlib
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from test_fetch_aggtrades import FakeHttp

from arkstream import refprices as rf
from arkstream_fetch import fetch_klines as fk

C = pl.col


def _todo():
    return fk.items(["BTCUSDT", "NEWUSDT"], "2025-11", "2025-12")


def test_months_items_and_cutoff():
    assert fk.months("2025-11", "2026-01") == ["2025-11", "2025-12", "2026-01"]
    with pytest.raises(ValueError):
        fk.months("2025-12", "2026-02")  # after the cutoff month
    it = _todo()[0]
    assert it.url == "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2025-11.zip"


def test_download_verify_resume_and_not_published(tmp_path):
    files = {it.name: f"zip-{it.name}".encode() for it in _todo() if it.name != "NEWUSDT-1m-2025-11.zip"}
    res = fk.run(_todo(), tmp_path, None, FakeHttp(files), log=lambda s: None)
    assert len(res["downloaded"]) == 3 and res["not_published"] == ["NEWUSDT-1m-2025-11.zip"] and not res["failed"]
    man = fk.read_manifest(tmp_path)
    row = man[("BTCUSDT", "2025-12")]
    assert row["sha256"] == row["published_sha256"] == hashlib.sha256(files["BTCUSDT-1m-2025-12.zip"]).hexdigest()
    again = FakeHttp(files)
    res = fk.run(_todo()[:2], tmp_path, None, again, log=lambda s: None)
    assert len(res["reused"]) == 2 and again.calls == []  # resume: no network for verified files
    bad = FakeHttp(files, wrong_checksum={"BTCUSDT-1m-2025-11.zip"})
    first = tmp_path / "BTCUSDT" / "BTCUSDT-1m-2025-11.zip"
    first.unlink()
    res = fk.run(_todo()[:1], tmp_path, None, bad, log=lambda s: None)
    assert res["failed"] == ["BTCUSDT-1m-2025-11.zip"] and not first.exists()  # a mismatch is never kept


def test_seed_is_verified_then_copied(tmp_path):
    seed = tmp_path / "seed"
    it = _todo()[0]
    (seed / it.symbol / "1m").mkdir(parents=True)
    it.seed(seed).write_bytes(b"seed-bytes")
    out = tmp_path / "out"
    res = fk.run([it], out, seed, FakeHttp({it.name: b"seed-bytes"}), log=lambda s: None)
    assert res["seeded"] == [it.name] and fk.read_manifest(out)[(it.symbol, it.month)]["source"] == "seed"
    assert fk.main(["--out", str(out), "--no-seed", "--dry-run", "--offline", "--symbols", "BTCUSDT",
                    "--start", "2025-11", "--end", "2025-11"]) == 0


def _zip(path: Path, rows: list[tuple[int, float, float]], header: bool = True) -> None:
    lines = ["open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,"
             "taker_buy_quote_volume,ignore"] if header else []
    for t, close, vol in rows:
        lines.append(f"{t},{close},{close + 1},{close - 1},{close},{vol},{t + 59_999},0,1,0,0,0")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(path.name.replace(".zip", ".csv"), "\n".join(lines) + "\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())


def test_zips_rebuild_the_lake_and_the_reference_prices(tmp_path):
    nov_last = int(datetime(2025, 11, 30, 23, 59, tzinfo=UTC).timestamp() * 1000)
    dec_first = int(datetime(2025, 12, 1, 0, 0, tzinfo=UTC).timestamp() * 1000)
    root = tmp_path / "zips"
    _zip(root / "AAAUSDT" / "AAAUSDT-1m-2025-11.zip", [(nov_last - 60_000, 10.0, 1.0), (nov_last, 11.0, 2.0)])
    _zip(root / "AAAUSDT" / "AAAUSDT-1m-2025-12.zip", [(dec_first, 12.0, 0.0), (dec_first + 60_000, 13.0, 3.0)],
         header=False)  # older archive layout, and a zero-volume bar
    hashes = {p.name: rf.sha256_file(p) for p in root.rglob("*.zip")}
    zips = rf.verified_kline_zips(root, hashes)
    with pytest.raises(ValueError):
        rf.verified_kline_zips(root, {**hashes, "AAAUSDT-1m-2025-12.zip": "0" * 64})  # a changed zip stops it
    with pytest.raises(ValueError):
        rf.verified_kline_zips(root, {"AAAUSDT-1m-2025-11.zip": hashes["AAAUSDT-1m-2025-11.zip"]})  # unverified
    lake = tmp_path / "lake"
    rf.lake_from_zips(zips, lake)
    k = rf.scan_klines(lake).collect().sort("ts_known")
    assert k["ts_known"].to_list() == [(t + 60_000) * 1_000_000 for t in (nov_last - 60_000, nov_last, dec_first,
                                                                        dec_first + 60_000)]
    assert rf.kline_months(lake) == ["2025-11", "2025-12"]  # the 23:59 bar of 30 Nov is known on 1 Dec
    mapping = pl.DataFrame({"hl": ["AAA"], "binance": ["AAAUSDT"], "price_factor_hl_per_binance": [1.0],
                            "valid_from": [datetime(2025, 11, 1).date()], "valid_to": [datetime(2025, 12, 31).date()]})
    files = rf.build_reference_files(lake, mapping, datetime(2025, 12, 31, tzinfo=UTC), tmp_path / "prices",
                                     {"dataset": "test"})
    got = {p.name: pl.read_parquet(p)["price"].to_list() for p in files}
    assert got == {"binance_um_1m_2025-11.parquet": [10.0], "binance_um_1m_2025-12.parquet": [11.0, 13.0]}
    with pytest.raises(FileExistsError):
        rf.lake_from_zips(zips, lake)  # never mixed into an existing lake


def test_zip_hash_sources(tmp_path):
    csv_path = tmp_path / "MANIFEST.csv"
    csv_path.write_text("symbol,month,file,bytes,sha256,published_sha256,source,retrieved_on,verified_on\n"
                        f"A,2025-11,A/A-1m-2025-11.zip,1,{'a' * 64},{'a' * 64},seed,,2026-11-21\n"
                        f"B,2025-11,B/B-1m-2025-11.zip,1,{'b' * 64},{'c' * 64},seed,,2026-11-21\n", encoding="utf-8")
    assert rf.load_zip_hashes(csv_path) == {"A-1m-2025-11.zip": "a" * 64}  # a row that did not verify is ignored
    txt = tmp_path / "CHECKSUMS.txt"
    txt.write_text("# header\n" + f"{'d' * 64}  10  data/futures/um/monthly/klines/D/1m/D-1m-2025-11.zip  verified\n"
                   + f"{'e' * 64}  10  data/futures/um/monthly/klines/E/1m/E-1m-2025-11.zip  unverified\n",
                   encoding="utf-8")
    assert rf.load_zip_hashes(txt) == {"D-1m-2025-11.zip": "d" * 64}
