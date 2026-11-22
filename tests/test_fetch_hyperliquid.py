"""Hyperliquid fetcher: pagination, raw files + manifest, resume without network, host allowlist, names."""

import json

import pytest

from arkstream_fetch import fetch_hyperliquid as fh

H = 3_600_000
S = fh.ms(fh.START)


class FakeHttp:
    """Serves fundingHistory for one coin with n hourly rows (+31 ms jitter), 500 per page; counts calls."""

    def __init__(self, n: int):
        self.rows = [{"coin": "BTC", "fundingRate": "0.0000125", "premium": "0.0001", "time": S + i * H + 31}
                     for i in range(n)]
        self.calls: list[dict] = []

    def post(self, url, body):
        fh._check_url(url)
        self.calls.append(body)
        sel = [r for r in self.rows if body["startTime"] <= r["time"] <= body["endTime"]][:500]
        return json.dumps(sel).encode()


def test_paginates_saves_raw_and_resumes_offline(tmp_path):
    http = FakeHttp(1200)
    end = fh.read_cutoff()
    res = fh.run("funding", ["BTC"], tmp_path, http, end, log=lambda s: None)
    assert res == {"done": ["BTC"], "failed": []}
    assert len(http.calls) == 3 and http.calls[1]["startTime"] == http.rows[499]["time"] + 1
    man = fh.read_manifest(tmp_path, "funding")
    assert sorted(int(r["rows"]) for r in man.values()) == [200, 500, 500]
    for r in man.values():  # raw bytes saved unchanged, hash recorded
        raw = (tmp_path / r["file"]).read_bytes()
        assert fh._sha(raw) == r["sha256"] and json.loads(raw)
    # resume: no network at all
    res2 = fh.run("funding", ["BTC"], tmp_path, None, end, log=lambda s: None)
    assert res2["done"] == ["BTC"]


def test_tampered_page_is_refetched(tmp_path):
    http = FakeHttp(10)
    end = fh.read_cutoff()
    fh.run("funding", ["BTC"], tmp_path, http, end, log=lambda s: None)
    (tmp_path / next(iter(fh.read_manifest(tmp_path, "funding").values()))["file"]).write_bytes(b"[]")
    assert fh.run("funding", ["BTC"], tmp_path, None, end, log=lambda s: None)["failed"] == ["BTC"]
    fh.run("funding", ["BTC"], tmp_path, http, end, log=lambda s: None)
    assert len(http.calls) == 2


def test_only_info_endpoint_allowed():
    for bad in ("https://api.hyperliquid.xyz/exchange", "https://evil.example/info", "http://api.hyperliquid.xyz/info"):
        with pytest.raises(ValueError):
            fh._check_url(bad)
    fh._check_url("https://api.hyperliquid.xyz/info")


def test_names_and_cutoff_refused(tmp_path):
    with pytest.raises(ValueError):
        fh.request_body("funding", "xyz:AAPL", 0, 1)  # HIP-3 out of scope
    with pytest.raises(ValueError):
        fh.request_body("funding", "../BTC", 0, 1)
    with pytest.raises(ValueError):
        fh.request_body("user_funding", "0xABC", 0, 1)
    from datetime import timedelta
    with pytest.raises(ValueError):
        fh.run("funding", ["BTC"], tmp_path, FakeHttp(1), fh.read_cutoff() + timedelta(seconds=1), log=lambda s: None)


def test_rate_limiter_spaces_requests():
    t = [0.0]
    slept: list[float] = []

    def sleep(s):
        slept.append(s)
        t[0] += s
    h = fh.UrllibHttp(interval_s=1.2, sleep=sleep, clock=lambda: t[0])
    h._wait()
    h._wait()
    assert slept == [pytest.approx(1.2)]
