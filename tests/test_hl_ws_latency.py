"""Recorder (offline, fake transport) and receive-delay analysis (ADR-0100..0104)."""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import re
import struct

import pytest

from arkstream import latency as L
from arkstream_fetch import hl_ws_latency as W

USER = "0x" + "ab" * 20


def server_frame(opcode: int, payload: bytes, fin: bool = True) -> bytes:
    n = len(payload)
    head = bytes([(0x80 if fin else 0) | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 1 << 16:
        head += bytes([126]) + struct.pack("!H", n)
    else:
        head += bytes([127]) + struct.pack("!Q", n)
    return head + payload


def unmask(frame: bytes) -> tuple[int, bytes]:
    op, n, i = frame[0] & 0x0F, frame[1] & 0x7F, 2
    assert frame[1] & 0x80, "client frames must be masked"
    if n == 126:
        n, i = struct.unpack("!H", frame[2:4])[0], 4
    key = frame[i:i + 4]
    return op, bytes(b ^ key[j % 4] for j, b in enumerate(frame[i + 4:i + 4 + n]))


class FakeTransport:
    """Answers the upgrade, then hands out scripted chunks; records everything sent."""

    def __init__(self, chunks: list[bytes], extensions: str = ""):
        self.chunks, self.sent, self.extensions, self.timeout = list(chunks), [], extensions, None

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)
        if data.startswith(b"GET "):
            key = re.search(rb"Sec-WebSocket-Key: (\S+)", data).group(1).decode()
            acc = base64.b64encode(hashlib.sha1((key + W.GUID).encode()).digest()).decode()
            ext = f"Sec-WebSocket-Extensions: {self.extensions}\r\n" if self.extensions else ""
            self.chunks.insert(0, (f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                                   f"Connection: Upgrade\r\nSec-WebSocket-Accept: {acc}\r\n{ext}\r\n").encode())

    def recv(self, n: int) -> bytes:
        if not self.chunks:
            return b""
        c = self.chunks.pop(0)
        if isinstance(c, Exception):
            raise c
        return c

    def settimeout(self, t):
        self.timeout = t

    def close(self):
        pass


def text(obj) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode()


def trades_msg(coin: str, *ts: int) -> bytes:
    return text({"channel": "trades", "data": [{"coin": coin, "side": "B", "px": "1", "sz": "1", "hash": "0x0",
                                                "time": t, "tid": 100 + i, "users": [USER, USER]}
                                               for i, t in enumerate(ts)]})


def fills_msg(snapshot: bool, *ts: int) -> bytes:
    return text({"channel": "userFills", "data": {"isSnapshot": snapshot, "user": USER, "fills": [
        {"coin": "BTC", "px": "1", "sz": "1", "side": "B", "time": t, "tid": 900 + i, "oid": 1}
        for i, t in enumerate(ts)]}})


# ------------------------------------------------------------------------------------------------ frames

def test_frame_roundtrip_lengths_and_fragments():
    d = W.FrameDecoder()
    for n in (0, 5, 125, 126, 70_000):
        p = b"x" * n
        assert d.feed(server_frame(W.OP_TEXT, p)) == [(W.OP_TEXT, p)]
    f = server_frame(W.OP_TEXT, b"abc", fin=False) + server_frame(W.OP_PING, b"p") + server_frame(W.OP_CONT, b"def")
    out = []
    for i in range(len(f)):            # byte by byte: partial headers and payloads
        out += d.feed(f[i:i + 1])
    assert out == [(W.OP_PING, b"p"), (W.OP_TEXT, b"abcdef")]
    sub = W.subscribe_message({"type": "trades", "coin": "BTC"})
    assert unmask(W.encode_frame(W.OP_TEXT, sub)) == (W.OP_TEXT, sub)
    long_sub = W.encode_frame(W.OP_TEXT, W.subscribe_message({"type": "userFills", "user": USER}))
    assert unmask(long_sub)[0] == W.OP_TEXT


def test_connection_sends_only_upgrade_subscribes_and_pong():
    chunks = [server_frame(W.OP_TEXT, trades_msg("BTC", 1)) + server_frame(W.OP_PING, b"hb")
              + server_frame(W.OP_TEXT, trades_msg("ETH", 2)), TimeoutError(), server_frame(W.OP_CLOSE, b"\x03\xe8")]
    tr = FakeTransport(chunks)
    clock = iter(range(1_000, 10_000, 10))
    c = W.WsConnection(opener=lambda h, p, t: tr, clock=lambda: next(clock), mono=lambda: 7)
    c.subscribe({"type": "trades", "coin": "BTC"})
    got = []
    with pytest.raises(ConnectionError, match="close"):
        for f in c.frames(lambda: False):
            got.append(f)
    c.close()
    assert [json.loads(f.payload)["data"][0]["coin"] for f in got] == ["BTC", "ETH"]
    assert got[0].chunk == got[1].chunk and got[0].recv_ns == got[1].recv_ns   # same socket read: a batch
    assert tr.sent[0].startswith(b"GET /ws HTTP/1.1\r\nHost: api.hyperliquid.xyz\r\n")
    ops = [unmask(s) for s in tr.sent[1:]]
    assert ops[0] == (W.OP_TEXT, W.subscribe_message({"type": "trades", "coin": "BTC"}))
    assert ops[1] == (W.OP_PONG, b"hb")
    assert ops[2] == (W.OP_CLOSE, b"\x03\xe8")
    assert len(ops) == 3              # close() after the server's close sends nothing more


def test_connection_refuses_extensions_and_bad_status():
    with pytest.raises(ConnectionError, match="extension"):
        W.WsConnection(opener=lambda h, p, t: FakeTransport([], extensions="permessage-deflate"))

    class Refuse(FakeTransport):
        def sendall(self, data):
            self.sent.append(data)
            self.chunks.insert(0, b"HTTP/1.1 403 Forbidden\r\n\r\n")

    with pytest.raises(ConnectionError, match="refused"):
        W.WsConnection(opener=lambda h, p, t: Refuse([]))


def test_tls_want_read_is_a_timeout_not_a_disconnect():
    import ssl

    tr = FakeTransport([ssl.SSLWantReadError(), server_frame(W.OP_TEXT, trades_msg("BTC", 1)),
                        server_frame(W.OP_CLOSE, b"")])
    c = W.WsConnection(opener=lambda h, p, t: tr)
    got = []
    with pytest.raises(ConnectionError, match="close"):
        for f in c.frames(lambda: False):
            got.append(f)
    assert len(got) == 1


def test_stale_connection_raises():
    tr = FakeTransport([TimeoutError()] * 5)
    c = W.WsConnection(opener=lambda h, p, t: tr)
    with pytest.raises(ConnectionError, match="no data"):
        list(c.frames(lambda: False, stale_s=-1))


# ------------------------------------------------------------------------------------------------ clock

def ntp_reply(t2_ns: int, t3_ns: int, stratum: int = 2) -> bytes:
    def ts(ns):
        sec, rem = divmod(ns, 1_000_000_000)
        return struct.pack("!II", sec + W.NTP_EPOCH, (rem << 32) // 1_000_000_000)
    return bytes([0x24, stratum]) + b"\0" * 30 + ts(t2_ns) + ts(t3_ns)


def test_sntp_offset_and_delay():
    s = 1_700_000_000 * 10**9
    # local clock 30 ms behind the server; 10 ms each way; server holds it 1 ms
    t1, t2, t3, t4 = s, s + 40_000_000, s + 41_000_000, s + 21_000_000
    off, dly = W.sntp_offset(ntp_reply(t2, t3), t1, t4)
    assert abs(off - 30_000_000) < 2 and abs(dly - 20_000_000) < 2
    with pytest.raises(ValueError, match="stratum"):
        W.sntp_offset(ntp_reply(t2, t3, stratum=0), t1, t4)


def test_measure_clock_best_sample_and_w32tm_parse():
    vals = {"time.windows.com": (5_000_000, 60_000_000), "time.google.com": (7_000_000, 20_000_000),
            "time.cloudflare.com": (None, None), "pool.ntp.org": (9_000_000, 40_000_000),
            "time.apple.com": (None, None)}
    m = W.measure_clock(lambda s: {"server": s, "offset_ns": vals[s][0], "delay_ns": vals[s][1]}, w32tm=False)
    assert m["offset_ns"] == 7_000_000 and m["server"] == "time.google.com"      # lowest round trip wins
    assert m["uncertainty_ns"] == 10_000_000 and m["median_offset_ns"] == 7_000_000
    assert m["server_spread_ns"] == 4_000_000
    none = W.measure_clock(lambda s: {"server": s, "offset_ns": None}, w32tm=False)
    assert none["offset_ns"] is None and none["uncertainty_ns"] is None
    assert W.parse_w32tm("Tracking time.windows.com.\n12:00:01, +00.0012345s\n12:00:03, -00.0020000s\n") == \
        [0.0012345, -0.002]


def test_clock_fit_interpolates_and_corrects():
    f = L.ClockFit(t_before_ns=0, offset_before_ns=10_000_000, t_after_ns=100, offset_after_ns=20_000_000)
    assert f.offset_ns(-5) == 10_000_000 and f.offset_ns(50) == 15_000_000 and f.offset_ns(500) == 20_000_000
    assert f.correct(50) == 50 + 15_000_000 and f.change_ms == 10.0
    assert L.usability(f, 0.0) == ""
    assert L.usability(L.ClockFit(0, 0, 100, 90_000_000), 0.0) == ""     # steady drift is corrected (ADR-0105)
    assert "step" in L.usability(f, 25.0)
    assert L.usability(None, 0.0).startswith("no NTP")


def test_clock_step_ignores_drift_and_spikes_but_not_steps():
    mono = list(range(0, 101_000, 1000))
    drift = [m + i * 1_000_000 for i, m in enumerate(mono)]                      # 100 ms of steady drift
    spike = [m + (-95_000_000 if i == 40 else 0) for i, m in enumerate(mono)]    # one message paused
    step = [m + (8_000_000 if i >= 50 else 0) for i, m in enumerate(mono)]       # lasting shift
    assert L.clock_step_ms(drift, mono) == pytest.approx(0.0, abs=1e-6)
    assert L.clock_step_ms(spike, mono) == pytest.approx(0.0, abs=0.2)
    assert L.clock_step_ms(step, mono) == pytest.approx(8.0, abs=0.5)   # detrending takes a little off it


def test_clock_fit_follows_readings_during_the_run():
    f = L.ClockFit(0, 0, 100, 0, mid=((50, 10_000_000), (500, 99)))   # a reading outside the run is ignored
    assert f.offset_ns(25) == 5_000_000 and f.offset_ns(50) == 10_000_000 and f.offset_ns(75) == 5_000_000
    assert f.drift_residual_ms == pytest.approx(10.0)
    assert L.ClockFit(0, 0, 100, 0).drift_residual_ms is None
    meta = {"clock": {"before": {"local_ns": 0, "offset_ns": 0}, "after": {"local_ns": 100, "offset_ns": 0},
                      "mid": [{"local_ns": 50, "offset_ns": 10_000_000}, {"local_ns": 60, "offset_ns": None}]}}
    assert L.clock_fit(meta).mid == ((50, 10_000_000),)


def test_counter_fit_and_labels():
    # wall runs 1:1 with the counter, offset grows 0 -> 20 ms: both corrections agree
    meta = {"clock": {"before": {"local_ns": 1_000, "offset_ns": 0, "uncertainty_ns": 30_000_000},
                      "after": {"local_ns": 1_000 + 10**12, "offset_ns": 20_000_000, "uncertainty_ns": 60_000_000}}}
    wall = [1_000 + k * 10**11 for k in range(11)]
    mono = [5 + k * 10**11 for k in range(11)]
    cf = L.counter_fit(meta, wall, mono)
    fit = L.clock_fit(meta)
    for w, q in zip(wall, mono, strict=True):
        assert abs(cf.true_ns(q) - fit.correct(w)) <= 1
    meta_p = {"clock": {"before": {**meta["clock"]["before"], "perf_ns": 5},
                        "after": {**meta["clock"]["after"], "perf_ns": 5 + 10**12}}}
    assert L.counter_fit(meta_p, wall, mono).anchors == cf.anchors        # recorded counter used directly
    assert L.clock_label(meta) == "wide NTP bound (+/-60 ms)"
    assert L.clock_label(meta, 6.0) == "wide NTP bound (+/-60 ms); counter check 6.0 ms (> 5)"
    assert L.clock_label({"clock": {}}, 1.0) == ""


# ------------------------------------------------------------------------------------------------ record + analyse

def fake_record(tmp_path, chunks_per_conn, offsets=(10_000_000, 12_000_000), recv_times=None, **kw):
    """Run record() against fake connections; recv clock is scripted so delays are exact."""
    conns = iter(chunks_per_conn)
    times = iter(recv_times or range(10**18, 10**18 + 10**12, 10**9))
    mono = iter(range(0, 10**15, 10**9))
    clocks = iter([{"local_ns": 10**18 - 1, "offset_ns": offsets[0]},
                   {"local_ns": 10**18 + 10**12, "offset_ns": offsets[1]}])

    def connect():
        try:
            ch = next(conns)
        except StopIteration:
            raise ConnectionError("no more") from None
        return W.WsConnection(opener=lambda h, p, t: FakeTransport(ch), clock=lambda: next(times),
                              mono=lambda: next(mono))

    subs = W.subscriptions([USER], ["BTC"])
    state = {"n": 0}

    def sleep(s):
        state["n"] += 1
        if state["n"] > len(chunks_per_conn):
            raise KeyboardInterrupt  # end the run once the scripted connections are used up

    kw.setdefault("ntp_every_s", None)
    return W.record(3600, tmp_path, subs, "test network", connect=connect, clock=lambda: next(clocks),
                    log=lambda s: None, sleep=kw.pop("sleep", sleep), **kw)


def test_record_writes_raw_unchanged_with_manifest_and_gaps(tmp_path):
    m1 = trades_msg("BTC", 10**12 + 5)
    m2 = fills_msg(True, 1, 2)
    m3 = fills_msg(False, 10**12 + 1_000)
    run = fake_record(tmp_path, [[server_frame(W.OP_TEXT, m1)],
                                 [server_frame(W.OP_TEXT, m2) + server_frame(W.OP_TEXT, m3)]])
    raw = (run / "raw.jsonl").read_bytes().split(b"\n")
    assert raw[:3] == [m1, m2, m3] and raw[3] == b""
    L.verify_manifest(run)
    meta = json.loads((run / "run.json").read_text())
    assert meta["n_messages"] == 3 and meta["interrupted"] is True and meta["connections"] >= 2
    assert meta["gaps"][0]["conn"] == 2 and meta["gaps"][0]["up_ns"] is not None
    assert "Address" not in json.dumps(meta["machine"])
    with open(run / "events.csv", newline="") as fh:
        ev = list(csv.DictReader(fh))
    assert [(e["channel"], e["is_snapshot"]) for e in ev] == [("trades", "1"), ("userFills", "1"),
                                                             ("userFills", "1"), ("userFills", "0")]
    (run / "raw.jsonl").write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="MANIFEST"):
        L.verify_manifest(run)


def test_delay_corrected_snapshot_excluded_and_deterministic(tmp_path):
    base = 10**18                           # recv clock: first read at base, then +1 s per read
    e1 = (base + 10**9) // 10**6 - 50       # trade 50 ms before the second read
    e2 = (base + 2 * 10**9) // 10**6 - 300  # fill 300 ms before the third read
    run = fake_record(tmp_path / "runs", [[server_frame(W.OP_TEXT, trades_msg("BTC", 1)),   # backlog
                                           server_frame(W.OP_TEXT, trades_msg("BTC", e1)),
                                           server_frame(W.OP_TEXT, fills_msg(True, 1) ) + server_frame(
                                               W.OP_TEXT, fills_msg(False, e2))]],
                      offsets=(10_000_000, 10_000_000))
    r = L.load_run(run)
    assert r.usable
    d = {(e.channel, round(ms)) for _, e, ms in L.delays_ms(r)}
    assert d == {("trades", 60), ("userFills", 310)}      # +10 ms: local clock is 10 ms behind NTP
    out1, out2 = tmp_path / "o1", tmp_path / "o2"
    assert L.main(tmp_path / "runs", out1, log=lambda s: None) == 0
    assert L.main(tmp_path / "runs", out2, log=lambda s: None) == 0
    for name in ("hl_receive_delay.csv", "hl_receive_delay_by_size.csv", "hl_receive_delay.md", "total_delay.csv"):
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes()
    with open(out1 / "hl_receive_delay.csv", newline="") as fh:
        rows = {(x["run"], x["channel"], x["coin"]): x for x in csv.DictReader(fh)}
    uf = rows[("ALL", "userFills", "ALL")]
    assert uf["n_events"] == "1" and float(uf["p50_ms"]) == pytest.approx(310.0)
    assert rows[("ALL", "trades", "ALL")]["n_events"] == "1"                 # the backlog is not live
    assert rows[(r.run_id, "userFills", "BTC")]["batched_share"] == "1.000"   # arrived with the snapshot frame
    assert rows[(r.run_id, "trades", "BTC")]["batched_share"] == "0.000"


def test_moving_offset_is_corrected_and_used(tmp_path):
    e = (10**18 + 10**9) // 10**6 - 100
    run = fake_record(tmp_path / "runs", [[server_frame(W.OP_TEXT, trades_msg("BTC", 1)),
                                           server_frame(W.OP_TEXT, trades_msg("BTC", e))]],
                      offsets=(0, 25_000_000))
    r = L.load_run(run)
    assert r.usable and r.qpc_check_ms == pytest.approx(0.0, abs=1e-3)
    rows, _ = L.summarise([r])
    assert any(x["run"] == "ALL" for x in rows)
    assert rows[0]["usable"] == "true" and rows[0]["offset_change_ms"] == pytest.approx(25.0)


def test_clock_sampler_takes_readings_and_record_keeps_them(tmp_path):
    import time

    n = {"k": 0}

    def fake_mid():
        n["k"] += 1
        if n["k"] == 2:
            raise OSError("ntp down")
        return {"local_ns": 10**18 + n["k"], "perf_ns": n["k"], "offset_ns": 1_000_000}

    smp = W.ClockSampler(0.001, fake_mid, log=lambda s: None).start()
    time.sleep(0.2)
    got = smp.stop()
    assert len(got) >= 3 and got[1]["offset_ns"] is None and "ntp down" in got[1]["error"]

    def slow_sleep(s):
        time.sleep(0.1)
        raise KeyboardInterrupt

    run = fake_record(tmp_path, [[server_frame(W.OP_TEXT, trades_msg("BTC", 1))]], ntp_every_s=0.001,
                      mid_clock=lambda: {"local_ns": 10**18 + 5, "perf_ns": 5, "offset_ns": 11_000_000},
                      sleep=slow_sleep)
    meta = json.loads((run / "run.json").read_text())
    assert meta["clock"]["ntp_every_s"] == 0.001 and len(meta["clock"]["mid"]) >= 1


def test_total_delay_sums_legs_and_reads_binance_ack(tmp_path):
    ack = {"p10": 300.0, "p50": 350.0, "p90": 600.0, "p99": 3000.0, "n": 30.0}
    rows = L.total_delay([400.0] * 99 + [1400.0], 60, 34.0, ack)
    by = {(r["method"], r["quantile"]): r for r in rows}
    assert by[("sum_of_quantiles", "p50")]["total_ms"] == pytest.approx(400 + 250 + 120 + 350)
    assert by[("sum_of_quantiles", "p99")]["ack_ms"] == 3000.0
    assert by[("per_draw", "p50")]["total_ms"] == pytest.approx(400 + 250 + 120 + 350, abs=5)
    assert by[("per_draw", "p99")]["total_ms"] <= by[("sum_of_quantiles", "p99")]["total_ms"]
    assert all(r["label"] == "partly transferred from Binance" for r in rows)
    assert L.total_delay([], 0, None, ack) == []
    study = tmp_path / "latency_study.csv"
    study.write_text("leg,product,n,p10_ms,p50_ms,p90_ms,p99_ms\n"
                     "order_submit_to_ack,USD-M futures,30,321.8,353.5,573.9,2766.8\n", encoding="utf-8")
    (tmp_path / "CHECKSUMS.txt").write_text(f"{L.sha256_file(study)} *latency_study.csv\n", encoding="utf-8")
    assert L.binance_ack(study)["p99"] == 2766.8
    (tmp_path / "CHECKSUMS.txt").write_text("0" * 64 + " *latency_study.csv\n", encoding="utf-8")
    with pytest.raises(ValueError, match="CHECKSUMS"):
        L.binance_ack(study)


def test_extract_events_ignores_other_channels():
    assert L.extract_events('{"channel":"subscriptionResponse","data":{"method":"subscribe"}}') == []
    assert L.extract_events('{"channel":"pong"}') == [] and L.extract_events("nope") == []
    ev = L.extract_events(fills_msg(False, 5, 6).decode())
    assert [(e.channel, e.user, e.event_id, e.event_ms) for e in ev] == [("userFills", USER, "900", 5),
                                                                        ("userFills", USER, "901", 6)]


def test_select_leaders_last_14_days(tmp_path):
    p = tmp_path / "fills.csv"
    rows = ["timestamp,trader\n"]
    a, b, c = ("0x" + ch * 40 for ch in "abc")
    rows += [f"2026-01-04 10:00:00.000+00,{a}\n"] * 3 + [f"2026-01-01 10:00:00.000+00,{b}\n"] * 3
    rows += [f"2025-12-01 10:00:00.000+00,{c}\n"] * 9      # outside the window
    p.write_text("".join(rows))
    assert W.select_leaders(p, n=5) == [(a, 3), (b, 3)]
    with pytest.raises(ValueError):
        W.select_leaders(p, n=11)


def test_initial_trades_per_coin_and_connection_are_snapshot():
    it = L.InitialTrades()
    ev = lambda coin: L.extract_events(trades_msg(coin, 5).decode())  # noqa: E731
    assert it.mark(1, ev("BTC"))[0].is_snapshot and not it.mark(1, ev("BTC"))[0].is_snapshot
    assert it.mark(1, ev("ETH"))[0].is_snapshot and it.mark(2, ev("BTC"))[0].is_snapshot   # new coin / new conn
    fills = L.extract_events(fills_msg(False, 5).decode())
    assert it.mark(3, fills) == fills


def test_probe_and_choose_active_leaders(tmp_path):
    now = 1_800_000_000_000
    users = ["0x" + c * 40 for c in "abcdef"]
    snap = lambda u, *t: server_frame(W.OP_TEXT, text({"channel": "userFills", "data": {  # noqa: E731
        "isSnapshot": True, "user": u, "fills": [{"coin": "BTC", "time": x, "tid": 1} for x in t]}}))
    chunks = [snap(users[0], now - 1000, now - 2 * 86_400_000), snap(users[1], now - 30 * 86_400_000),
              snap(users[2]), snap(users[3], now - 3_600_000)]
    tr = FakeTransport(chunks)
    probe = W.probe_leaders(users[:4], connect=lambda: W.WsConnection(opener=lambda h, p, t: tr), listen_s=5,
                            log=lambda s: None)
    sent = [unmask(x) for x in tr.sent[1:]]
    assert all(op == W.OP_TEXT and json.loads(p)["method"] == "subscribe" for op, p in sent[:4])
    assert [op for op, _ in sent[4:]] == [W.OP_CLOSE]
    rows = W.choose_active([(u, 10 - i) for i, u in enumerate(users[:4])], probe, now, n=1)
    assert [(r["active"], r["selected"]) for r in rows] == [(True, True), (False, False), (False, False),
                                                            (True, False)]     # 24h tie (1 each): package order
    assert rows[0]["snapshot_fills_24h"] == 1
    probe[users[3]]["times"] = [now - 10, now - 20]
    rows2 = W.choose_active([(u, 10 - i) for i, u in enumerate(users[:4])], probe, now, n=1)
    assert [r["selected"] for r in rows2] == [False, False, False, True]      # more fills in the last 24 h
    W.write_leaders(rows, tmp_path / "leaders.csv", "2026-11-20T00:00:00Z")
    assert W.read_leaders(tmp_path / "leaders.csv") == [(users[0], 10)]
