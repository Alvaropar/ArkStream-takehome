"""Record Hyperliquid's public WebSocket, read-only, to measure the receive delay (ADR-0044 item 1, ADR-0100..0104).

    python -m arkstream_fetch.hl_ws_latency --dry-run                     # leaders, coins, plan; no network
    python -m arkstream_fetch.hl_ws_latency --clock-only                  # NTP offset only
    python -m arkstream_fetch.hl_ws_latency --probe-leaders               # pick currently active leaders
    python -m arkstream_fetch.hl_ws_latency --duration-min 90 --network "home fibre, Wi-Fi 5 GHz, Spain"

Connects only to `wss://api.hyperliquid.xyz/ws` and subscribes to `userFills` for the leaders with the most fills
in the last 14 days of `data/raw/fills.csv` (at most 10: the venue's limit on users per connection) and to
`trades` for BTC, ETH, HYPE, SOL and four thinner coins. For every message it keeps the local wall time
(`time.time_ns()`) and monotonic time taken right after the socket read that completed the frame, before any
parsing. Output, one folder per run, `data/reference/latency/hyperliquid/<run_id>/`:

* `raw.jsonl`: each text frame's payload, byte for byte, one per line (a payload containing a newline, which the
  venue never sends, goes to `raw_extra/<seq>.json` with a placeholder line);
* `arrivals.csv`: seq (= raw line), conn, chunk (socket read), recv_ns, mono_ns, bytes, channel, n_events;
* `events.csv`: seq, channel, coin, user, id, event_ms, is_snapshot (extracted after the time was taken);
* `gaps.csv`: every disconnection, its reason, and the wall times down / back up;
* `run.json`: run id, times, subscriptions, machine and network description (no IP address), NTP offsets
  before and after, counts; `MANIFEST.csv`: bytes and SHA-256 of every file above.

Rules:

* **Read-only.** The only data frames ever sent are subscribe messages for `userFills` and `trades`
  (`_guard_outgoing` refuses anything else). The only other frames are the protocol's own pong (echoing a
  server ping, required by RFC 6455) and close. No application ping, no `exchange` endpoint, no signing, no keys.
* **One host.** `wss://api.hyperliquid.xyz/ws` only (`_check_ws_url`); NTP only to `NTP_SERVERS`.
* NTP offset before and after the run, and every 5 minutes during it on a background thread (`--ntp-every-min`),
  so drift is measured rather than interpolated (ADR-0105).
* Reconnects with bounded exponential backoff (1 s doubling to 60 s), logs every gap, stops after the set
  duration or Ctrl-C, and always measures the clock afterwards and writes the manifest.
* Leaders: `--probe-leaders` subscribes (only) to the userFills of the top 30 package addresses, keeps those
  with a fill in the last 7 days, selects the 10 with the most fills in the last 24 h, and writes `leaders.csv`;
  runs use its selected rows (ADR-0102).
* Standard library only (no new dependency, ADR-0100); the analysis is `python -m arkstream latency`.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import platform
import re
import socket
import ssl
import statistics
import struct
import subprocess
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any, Protocol

from arkstream.latency import InitialTrades, extract_events

ALLOWED_HOST = "api.hyperliquid.xyz"
WS_URL = "wss://api.hyperliquid.xyz/ws"
WS_PATH = "/ws"
NTP_SERVERS = ("time.windows.com", "time.google.com", "time.cloudflare.com", "pool.ntp.org", "time.apple.com")
ROOT = Path(__file__).resolve().parents[2]
FILLS = ROOT / "data" / "raw" / "fills.csv"
DEFAULT_OUT = ROOT / "data" / "reference" / "latency" / "hyperliquid"
LEADERS_FILE = DEFAULT_OUT / "leaders.csv"
MAJORS = ("BTC", "ETH", "HYPE", "SOL")
THIN = ("ZEC", "PENDLE", "AIXBT", "TRX")  # ADR-0102: traded by the leaders, $0.3-2.8M notional in the last 14 days
MAX_USERS = 10
LOOKBACK_DAYS = 14
PROBE_CANDIDATES = 30   # ADR-0102: top package addresses probed for current activity
ACTIVE_DAYS = 7
BACKOFF_START_S, BACKOFF_MAX_S = 1.0, 60.0
STALE_S = 90.0     # no byte for this long: treat the connection as dead and reconnect
READ_TIMEOUT_S = 1.0
NTP_EVERY_S = 300.0  # ADR-0105: NTP reading during the run every 5 minutes, so drift is measured
MID_NTP_SAMPLES = 4  # per server during the run (8 before and after)
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_USER_RE = re.compile(r"^0x[0-9a-f]{40}$")
_COIN_RE = re.compile(r"^[A-Za-z0-9]{1,20}$")
OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


# ------------------------------------------------------------------------------------------------ safety

def _check_ws_url(url: str) -> None:
    if url != WS_URL:
        raise ValueError(f"refusing to connect to {url}: only {WS_URL} is allowed")


def subscribe_message(sub: dict[str, str]) -> bytes:
    payload = json.dumps({"method": "subscribe", "subscription": sub}, separators=(",", ":")).encode("utf-8")
    _guard_outgoing(payload)
    return payload


def _guard_outgoing(payload: bytes) -> None:
    """The only data this program may send: a subscribe to userFills (one address) or trades (one coin)."""
    try:
        msg = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as e:
        raise PermissionError(f"refusing to send a non-JSON frame: {payload[:80]!r}") from e
    if not isinstance(msg, dict) or set(msg) != {"method", "subscription"} or msg["method"] != "subscribe":
        raise PermissionError(f"refusing to send anything but a subscribe message: {payload[:120]!r}")
    sub = msg["subscription"]
    ok = isinstance(sub, dict) and (
        (set(sub) == {"type", "user"} and sub["type"] == "userFills" and isinstance(sub["user"], str)
         and bool(_USER_RE.match(sub["user"])))
        or (set(sub) == {"type", "coin"} and sub["type"] == "trades" and isinstance(sub["coin"], str)
            and bool(_COIN_RE.match(sub["coin"]))))
    if not ok:
        raise PermissionError(f"refusing to send subscription {sub!r}: only userFills(user) and trades(coin)")


# ------------------------------------------------------------------------------------------------ frames

def encode_frame(opcode: int, payload: bytes, mask: bytes | None = None) -> bytes:
    """One masked client frame (RFC 6455 5.2). Only text (guarded), pong and close are ever built."""
    if opcode == OP_TEXT:
        _guard_outgoing(payload)
    elif opcode not in (OP_PONG, OP_CLOSE):
        raise PermissionError(f"refusing to build a frame with opcode {opcode:#x}")
    if opcode != OP_TEXT and len(payload) > 125:
        raise ValueError("control frame payload over 125 bytes")
    mask = os.urandom(4) if mask is None else mask
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 1 << 16:
        head += bytes([0x80 | 126]) + struct.pack("!H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack("!Q", n)
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


@dataclass
class FrameDecoder:
    """Incremental server-frame parser. feed() returns complete (opcode, payload) messages; fragments joined."""
    buf: bytearray = field(default_factory=bytearray)
    frag_op: int | None = None
    frag: bytearray = field(default_factory=bytearray)

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        self.buf += data
        out: list[tuple[int, bytes]] = []
        while True:
            if len(self.buf) < 2:
                return out
            b0, b1 = self.buf[0], self.buf[1]
            fin, op, masked, n, i = b0 & 0x80, b0 & 0x0F, b1 & 0x80, b1 & 0x7F, 2
            if n == 126:
                if len(self.buf) < 4:
                    return out
                n, i = struct.unpack("!H", self.buf[2:4])[0], 4
            elif n == 127:
                if len(self.buf) < 10:
                    return out
                n, i = struct.unpack("!Q", self.buf[2:10])[0], 10
            key = b""
            if masked:
                if len(self.buf) < i + 4:
                    return out
                key, i = bytes(self.buf[i:i + 4]), i + 4
            if len(self.buf) < i + n:
                return out
            payload = bytes(self.buf[i:i + n])
            del self.buf[:i + n]
            if key:
                payload = bytes(b ^ key[j % 4] for j, b in enumerate(payload))
            if op >= 0x8:                      # control frames are never fragmented
                out.append((op, payload))
            elif op == OP_CONT:
                if self.frag_op is None:
                    raise ConnectionError("continuation frame without a start")
                self.frag += payload
                if fin:
                    out.append((self.frag_op, bytes(self.frag)))
                    self.frag_op, self.frag = None, bytearray()
            elif fin:
                out.append((op, payload))
            else:
                self.frag_op, self.frag = op, bytearray(payload)


# ------------------------------------------------------------------------------------------------ connection

class Transport(Protocol):
    def sendall(self, data: bytes) -> None: ...
    def recv(self, n: int) -> bytes: ...
    def settimeout(self, t: float | None) -> None: ...
    def close(self) -> None: ...


def _open_tls(host: str, port: int, timeout: float) -> Transport:
    raw = socket.create_connection((host, port), timeout=timeout)
    raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return ssl.create_default_context().wrap_socket(raw, server_hostname=host)


@dataclass
class Frame:
    opcode: int
    payload: bytes
    recv_ns: int
    mono_ns: int
    chunk: int


class WsConnection:
    """Minimal read-only client: handshake, guarded subscribe, read frames with arrival times."""

    def __init__(self, url: str = WS_URL, opener: Callable[[str, int, float], Transport] = _open_tls,
                 timeout_s: float = 10.0, clock: Callable[[], int] = time.time_ns,
                 mono: Callable[[], int] = time.perf_counter_ns):  # QPC; monotonic_ns ticks 15.6 ms on Windows
        _check_ws_url(url)
        self.clock, self.mono = clock, mono
        self.sock = opener(ALLOWED_HOST, 443, timeout_s)
        self.decoder = FrameDecoder()
        self.chunk = 0
        self.closed = False
        self._handshake()

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        self.sock.sendall(encode_frame(opcode, payload))  # the only send of frames; encode_frame guards

    def _handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {WS_PATH} HTTP/1.1\r\nHost: {ALLOWED_HOST}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nUser-Agent: arkstream-fetch/1\r\n\r\n")
        self.sock.sendall(req.encode("ascii"))
        buf = b""
        while b"\r\n\r\n" not in buf:
            b = self.sock.recv(4096)
            if not b:
                raise ConnectionError("connection closed during handshake")
            buf += b
            if len(buf) > 65536:
                raise ConnectionError("handshake response too long")
        head, rest = buf.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        if not re.match(r"HTTP/1\.1 101\b", lines[0]):
            raise ConnectionError(f"handshake refused: {lines[0]}")
        hdr = {k.strip().lower(): v.strip() for k, v in (ln.split(":", 1) for ln in lines[1:] if ":" in ln)}
        want = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()  # noqa: S324 (RFC 6455)
        if hdr.get("sec-websocket-accept") != want:
            raise ConnectionError("bad Sec-WebSocket-Accept")
        if hdr.get("sec-websocket-extensions"):
            raise ConnectionError(f"unrequested extension {hdr['sec-websocket-extensions']}")
        self._pending_t = (self.clock(), self.mono()) if rest else (0, 0)  # frames read with the upgrade
        self._pending = self.decoder.feed(rest) if rest else []

    def subscribe(self, sub: dict[str, str]) -> None:
        self._send_frame(OP_TEXT, subscribe_message(sub))

    def frames(self, stop: Callable[[], bool], stale_s: float = STALE_S) -> Iterator[Frame]:
        """Yield text frames until stop() or the connection ends (ConnectionError)."""
        self.sock.settimeout(READ_TIMEOUT_S)
        for op, p in self._pending:
            yield from self._handle(op, p, *self._pending_t, 0)
        self._pending = []
        last = time.monotonic()
        while not stop():
            try:
                data = self.sock.recv(1 << 16)
                t, m = self.clock(), self.mono()      # arrival time first, before any parsing
            except (TimeoutError, ssl.SSLWantReadError):  # a TLS read can time out mid-record: not a disconnect
                if time.monotonic() - last > stale_s:
                    raise ConnectionError(f"no data for {stale_s:.0f} s") from None
                continue
            if not data:
                raise ConnectionError("server closed the TCP connection")
            last = time.monotonic()
            self.chunk += 1
            for op, p in self.decoder.feed(data):
                yield from self._handle(op, p, t, m, self.chunk)
            if self.closed:
                raise ConnectionError("server sent close")

    def _handle(self, op: int, p: bytes, t: int, m: int, chunk: int) -> Iterator[Frame]:
        if op == OP_PING:
            self._send_frame(OP_PONG, p)       # RFC 6455 5.5.2: must answer; echoes the server's payload
        elif op == OP_CLOSE:
            if not self.closed:
                self.closed = True
                try:
                    self._send_frame(OP_CLOSE, p[:2])
                except OSError:
                    pass
        elif op in (OP_TEXT, OP_BIN):
            yield Frame(op, p, t, m, chunk)

    def close(self) -> None:
        try:
            if not self.closed:
                self.closed = True
                self._send_frame(OP_CLOSE, struct.pack("!H", 1000))
        except OSError:
            pass
        finally:
            self.sock.close()


# ------------------------------------------------------------------------------------------------ clock

NTP_EPOCH = 2208988800  # seconds from 1900-01-01 to 1970-01-01


def _ntp_ts(b: bytes) -> int:
    sec, frac = struct.unpack("!II", b)
    return (sec - NTP_EPOCH) * 1_000_000_000 + (frac * 1_000_000_000 >> 32)


def sntp_offset(response: bytes, t1_ns: int, t4_ns: int) -> tuple[int, int]:
    """(offset, round-trip delay) in ns from one SNTP reply (RFC 4330): offset = server - local."""
    if len(response) < 48:
        raise ValueError("short NTP reply")
    stratum = response[1]
    if stratum == 0 or stratum > 15:
        raise ValueError(f"NTP reply stratum {stratum} (kiss-of-death or unsynchronised)")
    t2, t3 = _ntp_ts(response[32:40]), _ntp_ts(response[40:48])
    return ((t2 - t1_ns) + (t3 - t4_ns)) // 2, (t4_ns - t1_ns) - (t3 - t2)


def query_ntp(server: str, samples: int = 8, timeout_s: float = 2.0, pause_s: float = 0.25) -> dict[str, Any]:
    """Offset to one server: the sample with the smallest round trip (least asymmetric error)."""
    if server not in NTP_SERVERS:
        raise ValueError(f"refusing NTP server {server}: only {NTP_SERVERS}")
    got: list[tuple[int, int]] = []
    errors: list[str] = []
    for _ in range(samples):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(timeout_s)
                s.connect((server, 123))
                t1 = time.time_ns()
                s.send(b"\x23" + 47 * b"\0")        # LI 0, version 4, mode 3 (client); nothing else
                r = s.recv(512)
                t4 = time.time_ns()
            got.append(sntp_offset(r, t1, t4))
        except (OSError, ValueError) as e:
            errors.append(f"{type(e).__name__}: {e}")
        time.sleep(pause_s)
    if not got:
        return {"server": server, "offset_ns": None, "delay_ns": None, "samples": 0, "errors": errors[:3]}
    off, dly = min(got, key=lambda x: x[1])
    return {"server": server, "offset_ns": off, "delay_ns": dly, "samples": len(got),
            "offset_spread_ns": max(o for o, _ in got) - min(o for o, _ in got), "errors": errors[:3]}


def parse_w32tm(text: str) -> list[float]:
    """Offsets in seconds from `w32tm /stripchart /dataonly` lines like '12:00:01, +00.0012345s'."""
    return [float(m.group(1)) for m in re.finditer(r",\s*([+-]\d+\.\d+)s", text)]


def w32tm_check(samples: int = 5) -> dict[str, Any]:
    """Windows' own NTP probe against time.windows.com, kept as a cross-check of the SNTP offset."""
    if platform.system() != "Windows":
        return {}
    try:
        out = subprocess.run(["w32tm", "/stripchart", "/computer:time.windows.com", f"/samples:{samples}",
                              "/dataonly"], capture_output=True, text=True, timeout=60, check=False).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": str(e)}
    v = parse_w32tm(out)
    return {"offsets_s": v, "median_offset_ns": int(statistics.median(v) * 1e9) if v else None}


def measure_clock(query: Callable[[str], dict[str, Any]] = query_ntp, w32tm: bool = True) -> dict[str, Any]:
    """Offset = the best (lowest round trip) sample over all servers; its error is at most half that round trip
    (ADR-0101). The median over servers and their spread are kept as a check against a bad server. `perf_ns`
    (the high-resolution counter at the same moment as `local_ns`) anchors the counter cross-check (ADR-0105)."""
    per = [query(s) for s in NTP_SERVERS]
    ok = [p for p in per if p.get("offset_ns") is not None]
    best = min(ok, key=lambda p: (p["delay_ns"], p["server"])) if ok else None
    offs = sorted(p["offset_ns"] for p in ok)
    return {"local_ns": time.time_ns(), "perf_ns": time.perf_counter_ns(), "utc": _utc_now(),
            "offset_ns": best["offset_ns"] if best else None,
            "uncertainty_ns": max(0, best["delay_ns"]) // 2 if best else None,
            "server": best["server"] if best else None,
            "median_offset_ns": int(statistics.median(offs)) if offs else None,
            "server_spread_ns": offs[-1] - offs[0] if offs else None,
            "servers": per, "w32tm": w32tm_check() if w32tm else {}}


def mid_run_clock() -> dict[str, Any]:
    """The reading taken during a run: fewer samples per server, no w32tm."""
    return measure_clock(query=partial(query_ntp, samples=MID_NTP_SAMPLES), w32tm=False)


class ClockSampler:
    """Takes an NTP reading every `interval_s` on a background thread while a run records (ADR-0105). The thread
    only waits on UDP sockets; the recording thread keeps stamping arrivals."""

    def __init__(self, interval_s: float, measure: Callable[[], dict[str, Any]] = mid_run_clock,
                 log: Callable[[str], None] = print):
        self.interval_s, self.measure, self.log = interval_s, measure, log
        self.readings: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="ntp-sampler", daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                m = self.measure()
            except Exception as e:  # noqa: BLE001 - a failed reading is recorded, never fatal to the run
                m = {"local_ns": time.time_ns(), "perf_ns": time.perf_counter_ns(), "offset_ns": None,
                     "error": f"{type(e).__name__}: {e}"[:200]}
            self.readings.append(m)
            self.log(f"  NTP during run: {_ms(m.get('offset_ns'))}")

    def start(self) -> ClockSampler:
        self._thread.start()
        return self

    def stop(self, timeout_s: float = 60.0) -> list[dict[str, Any]]:
        self._stop.set()
        self._thread.join(timeout_s)
        return list(self.readings)


# ------------------------------------------------------------------------------------------------ selection

def select_leaders(fills: Path = FILLS, n: int = MAX_USERS, days: int = LOOKBACK_DAYS,
                   limit: bool = True) -> list[tuple[str, int]]:
    """Addresses with the most fills in the last `days` of the package data (ties: address order)."""
    if limit and n > MAX_USERS:
        raise ValueError(f"at most {MAX_USERS} users per connection")
    rows: list[tuple[str, str]] = []
    with open(fills, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append((r["timestamp"][:19], r["trader"].lower()))
    end = max(t for t, _ in rows)
    start = (datetime.fromisoformat(end) - timedelta(days=days)).isoformat(sep=" ")
    c = Counter(a for t, a in rows if t > start)
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def probe_leaders(candidates: list[str], connect: Callable[[], WsConnection] = WsConnection,
                  listen_s: float = 10.0, log: Callable[[str], None] = print) -> dict[str, dict[str, Any]]:
    """Each candidate's most recent fills from its userFills snapshot, 10 addresses per connection. Sends
    subscribe messages only, like the recorder; nothing is saved but the summary."""
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(candidates), MAX_USERS):
        batch = candidates[i:i + MAX_USERS]
        got: dict[str, dict[str, Any]] = {}
        t_end = time.monotonic() + listen_s
        c = connect()
        try:
            for u in batch:
                c.subscribe({"type": "userFills", "user": u})
            def done(t_end: float = t_end, got: dict = got, k: int = len(batch)) -> bool:
                return time.monotonic() >= t_end or len(got) == k

            for f in c.frames(done):
                try:
                    msg = json.loads(f.payload)
                except ValueError:
                    continue
                d = msg.get("data") if isinstance(msg, dict) else None
                if msg.get("channel") == "userFills" and isinstance(d, dict) and d.get("isSnapshot"):
                    times = [int(x["time"]) for x in d.get("fills", []) if "time" in x]
                    got[str(d.get("user", "")).lower()] = {"last_fill_ms": max(times) if times else None,
                                                           "snapshot_fills": len(times), "times": times}
        except ConnectionError as e:
            log(f"  probe batch {i // MAX_USERS + 1}: {e}")
        finally:
            c.close()
        out.update(got)
    return out


def choose_active(ranked: list[tuple[str, int]], probe: dict[str, dict[str, Any]], now_ms: int,
                  n: int = MAX_USERS, active_days: int = ACTIVE_DAYS) -> list[dict[str, Any]]:
    """Candidates in package order (fills in the last 14 days of the data). Active = latest fill within
    `active_days` of the probe. Selected = the n active ones with the most snapshot fills in the last 24 h
    (ties: package order), to get as many live fills as the 10-address limit allows (ADR-0102)."""
    rows: list[dict[str, Any]] = []
    for u, nf in ranked:
        p = probe.get(u, {})
        last = p.get("last_fill_ms")
        recent = sum(1 for t in p.get("times", []) if t >= now_ms - 86_400_000)
        active = last is not None and last >= now_ms - active_days * 86_400_000
        rows.append({"user": u, "package_fills_14d": nf, "probed": u in probe,
                     "last_fill_utc": "" if last is None else datetime.fromtimestamp(last / 1e3, UTC).isoformat(),
                     "snapshot_fills_24h": recent, "active": active, "selected": False})
    order = sorted((i for i, r in enumerate(rows) if r["active"]),
                   key=lambda i: (-int(rows[i]["snapshot_fills_24h"]), i))
    for i in order[:n]:
        rows[i]["selected"] = True
    return rows


def write_leaders(rows: list[dict[str, Any]], path: Path = LEADERS_FILE, probed_utc: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["user", "package_fills_14d", "probed", "last_fill_utc", "snapshot_fills_24h", "active", "selected",
              "probed_utc"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "probed_utc": probed_utc})


def read_leaders(path: Path = LEADERS_FILE) -> list[tuple[str, int]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [(r["user"], int(r["package_fills_14d"])) for r in csv.DictReader(fh) if r["selected"] == "True"]


def subscriptions(users: list[str], coins: list[str]) -> list[dict[str, str]]:
    subs = [{"type": "userFills", "user": u} for u in users] + [{"type": "trades", "coin": c} for c in coins]
    for s in subs:
        subscribe_message(s)  # validates every subscription before any connection is opened
    return subs


# ------------------------------------------------------------------------------------------------ recording

def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while b := fh.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def machine() -> dict[str, Any]:
    """Machine description without addresses or host names."""
    return {"os": platform.platform(), "python": platform.python_version(), "cpu": platform.processor(),
            "cpus": os.cpu_count()}


class RunWriter:
    ARRIVALS = ["seq", "conn", "chunk", "recv_ns", "mono_ns", "bytes", "channel", "n_events"]
    EVENTS = ["seq", "channel", "coin", "user", "id", "event_ms", "is_snapshot"]
    GAPS = ["conn", "reason", "down_ns", "up_ns", "gap_ms"]

    def __init__(self, run_dir: Path):
        run_dir.mkdir(parents=True, exist_ok=False)
        self.dir = run_dir
        self.raw = open(run_dir / "raw.jsonl", "wb")
        self._fa = open(run_dir / "arrivals.csv", "w", newline="", encoding="utf-8")
        self._fe = open(run_dir / "events.csv", "w", newline="", encoding="utf-8")
        self._fg = open(run_dir / "gaps.csv", "w", newline="", encoding="utf-8")
        self.arr, self.ev, self.gap = (csv.writer(f, lineterminator="\n") for f in (self._fa, self._fe, self._fg))
        self.arr.writerow(self.ARRIVALS)
        self.ev.writerow(self.EVENTS)
        self.gap.writerow(self.GAPS)
        self.seq = 0
        self.counts: Counter[str] = Counter()
        self.live_events: Counter[str] = Counter()
        self.initial = InitialTrades()

    def message(self, conn: int, f: Frame) -> None:
        self.seq += 1
        if b"\n" in f.payload or b"\r" in f.payload:
            (self.dir / "raw_extra").mkdir(exist_ok=True)
            (self.dir / "raw_extra" / f"{self.seq}.json").write_bytes(f.payload)
            self.raw.write(json.dumps({"_arkstream_raw_extra": self.seq}).encode() + b"\n")
        else:
            self.raw.write(f.payload + b"\n")
        text = f.payload.decode("utf-8", errors="replace")
        evs = self.initial.mark(conn, extract_events(text))
        ch = evs[0].channel if evs else _channel(text)
        self.arr.writerow([self.seq, conn, f.chunk, f.recv_ns, f.mono_ns, len(f.payload), ch, len(evs)])
        for e in evs:
            self.ev.writerow([self.seq, e.channel, e.coin, e.user, e.event_id, e.event_ms, int(e.is_snapshot)])
            if not e.is_snapshot:
                self.live_events[e.channel] += 1
        self.counts[ch] += 1

    def gap_row(self, conn: int, reason: str, down_ns: int, up_ns: int | None) -> None:
        self.gap.writerow([conn, reason, down_ns, up_ns if up_ns is not None else "",
                           f"{(up_ns - down_ns) / 1e6:.1f}" if up_ns is not None else ""])

    def flush(self) -> None:
        for f in (self.raw, self._fa, self._fe, self._fg):
            f.flush()

    def finish(self, meta: dict[str, Any]) -> None:
        for f in (self.raw, self._fa, self._fe, self._fg):
            f.close()
        (self.dir / "run.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        files = sorted(p for p in self.dir.rglob("*") if p.is_file() and p.name != "MANIFEST.csv")
        with open(self.dir / "MANIFEST.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["file", "bytes", "sha256"])
            for p in files:
                w.writerow([p.relative_to(self.dir).as_posix(), p.stat().st_size, sha256_file(p)])


def _channel(text: str) -> str:
    m = re.match(r'\s*\{\s*"channel"\s*:\s*"([^"]*)"', text)
    return m.group(1) if m else ""


def record(duration_s: float, out: Path, subs: list[dict[str, str]], network: str, *,
           connect: Callable[[], WsConnection] = WsConnection, clock: Callable[[], dict[str, Any]] = measure_clock,
           log: Callable[[str], None] = print, sleep: Callable[[float], None] = time.sleep,
           extra_meta: dict[str, Any] | None = None, ntp_every_s: float | None = NTP_EVERY_S,
           mid_clock: Callable[[], dict[str, Any]] = mid_run_clock) -> Path:
    """One run: clock, connect + subscribe (reconnect with backoff), read until the duration ends, clock. With
    `ntp_every_s`, an NTP reading is also taken every that many seconds during the run (`clock.mid`)."""
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    w = RunWriter(out / run_id)
    meta: dict[str, Any] = {"run_id": run_id, "start_utc": _utc_now(), "url": WS_URL, "subscriptions": subs,
                            "planned_duration_s": duration_s, "machine": machine(), "network": network,
                            "recorder": "arkstream_fetch.hl_ws_latency", "recorder_sha256": sha256_file(Path(__file__)),
                            **(extra_meta or {})}
    log(f"run {run_id}: measuring clock offset before")
    meta["clock"] = {"before": clock()}
    log(f"  offset before: {_ms(meta['clock']['before'].get('offset_ns'))}")
    sampler = ClockSampler(ntp_every_s, mid_clock, log).start() if ntp_every_s else None
    t_end = time.monotonic() + duration_s
    stop = lambda: time.monotonic() >= t_end  # noqa: E731
    gaps: list[dict[str, Any]] = []
    conn, backoff, interrupted = 0, BACKOFF_START_S, False
    down: tuple[int, str] | None = None
    next_report = time.monotonic() + 300
    try:
        while not stop():
            conn += 1
            c: WsConnection | None = None
            t_conn = time.monotonic()
            try:
                c = connect()
                for s in subs:
                    c.subscribe(s)
                log(f"  conn {conn}: subscribed to {len(subs)} streams")
                for f in c.frames(stop):
                    if down is not None:
                        gaps.append({"conn": conn, "reason": down[1], "down_ns": down[0], "up_ns": f.recv_ns})
                        w.gap_row(conn, down[1], down[0], f.recv_ns)
                        down = None
                    w.message(conn, f)
                    if time.monotonic() >= next_report:
                        w.flush()
                        next_report = time.monotonic() + 300
                        log(f"  {_utc_now()[:19]} messages {dict(w.counts)} live events {dict(w.live_events)}")
            except (OSError, ConnectionError, ssl.SSLError) as e:
                if down is None:
                    down = (time.time_ns(), f"{type(e).__name__}: {e}"[:200])
                log(f"  conn {conn}: {type(e).__name__}: {e}")
            finally:
                if c is not None:
                    c.close()
            if stop():
                break
            backoff = BACKOFF_START_S if time.monotonic() - t_conn > 60 else min(backoff * 2, BACKOFF_MAX_S)
            log(f"  reconnecting in {backoff:.0f} s")
            sleep(min(backoff, max(0.0, t_end - time.monotonic())))
    except KeyboardInterrupt:
        interrupted = True
        log("  interrupted; measuring clock and writing the manifest")
    if down is not None:
        gaps.append({"conn": conn, "reason": down[1], "down_ns": down[0], "up_ns": None})
        w.gap_row(conn, down[1], down[0], None)
    meta.update(end_utc=_utc_now(), duration_s=round((datetime.now(UTC) - started).total_seconds(), 3),
                connections=conn, gaps=gaps, interrupted=interrupted, messages=dict(sorted(w.counts.items())),
                live_events=dict(sorted(w.live_events.items())), n_messages=w.seq)
    meta["clock"]["mid"] = sampler.stop() if sampler else []
    meta["clock"]["ntp_every_s"] = ntp_every_s
    log("  measuring clock offset after")
    meta["clock"]["after"] = clock()
    b, a = meta["clock"]["before"].get("offset_ns"), meta["clock"]["after"].get("offset_ns")
    log(f"  offset after: {_ms(a)}" + (f"; change {(a - b) / 1e6:+.1f} ms" if a is not None and b is not None else ""))
    w.finish(meta)
    log(f"wrote {w.dir} ({w.seq} messages, {len(gaps)} gaps)")
    return w.dir


def _ms(ns: int | None) -> str:
    return "n/a" if ns is None else f"{ns / 1e6:+.2f} ms"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hl_ws_latency", description=__doc__.split("\n\n")[0])
    ap.add_argument("--duration-min", type=float, default=90.0)
    ap.add_argument("--leaders", type=int, default=MAX_USERS, help=f"how many leaders (<= {MAX_USERS})")
    ap.add_argument("--coins", nargs="+", default=list(MAJORS + THIN))
    ap.add_argument("--ntp-every-min", type=float, default=NTP_EVERY_S / 60,
                    help="NTP reading during the run every N minutes (0: before and after only)")
    ap.add_argument("--network", default="", help="network description (connection type, ISP class, region)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dry-run", action="store_true", help="print leaders and subscriptions; no network")
    ap.add_argument("--clock-only", action="store_true", help="measure the NTP offset and exit")
    ap.add_argument("--probe-leaders", action="store_true",
                    help=f"subscribe to the top {PROBE_CANDIDATES} package addresses' userFills, keep those active "
                         f"in the last {ACTIVE_DAYS} days, write {LEADERS_FILE.name}")
    a = ap.parse_args(argv)
    if a.clock_only:
        print(json.dumps(measure_clock(), indent=2))
        return 0
    if a.probe_leaders:
        ranked = select_leaders(n=PROBE_CANDIDATES, limit=False)
        probed_utc = _utc_now()
        rows = choose_active(ranked, probe_leaders([u for u, _ in ranked]), time.time_ns() // 1_000_000, a.leaders)
        write_leaders(rows, a.out / LEADERS_FILE.name, probed_utc)
        for r in rows:
            print(f"  {'*' if r['selected'] else ' '} {r['user']} {r['package_fills_14d']:5d} last fill "
                  f"{r['last_fill_utc'][:19] or 'none':19s} fills in last 24h (of snapshot) {r['snapshot_fills_24h']}")
        print(f"wrote {a.out / LEADERS_FILE.name}: {sum(r['selected'] for r in rows)} selected")
        return 0
    lf = a.out / LEADERS_FILE.name
    leaders = read_leaders(lf)[:a.leaders] if lf.exists() else select_leaders(n=a.leaders)
    subs = subscriptions([u for u, _ in leaders], a.coins)
    print(f"leaders ({lf.name if lf.exists() else 'package top, not probed'}; fills in the last {LOOKBACK_DAYS} "
          f"days of {FILLS.name}):")
    for u, n in leaders:
        print(f"  {u} {n}")
    print(f"coins: {', '.join(a.coins)}; {len(subs)} subscriptions to {WS_URL}; out: {a.out}")
    if a.dry_run:
        return 0
    if not a.network:
        print("pass --network \"<connection, ISP class, region>\" (no IP address) to describe the run",
              file=sys.stderr)
        return 2
    record(a.duration_min * 60, a.out, subs, a.network, ntp_every_s=a.ntp_every_min * 60 or None,
           extra_meta={"leaders": [{"user": u, "fills_last_14d": n} for u, n in leaders], "coins": a.coins})
    return 0


if __name__ == "__main__":
    sys.exit(main())
