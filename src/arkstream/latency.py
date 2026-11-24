"""Hyperliquid receive delay from recorded stream runs (ADR-0038 item 1, ADRs 0040..0043, 0056). No network.

    python -m arkstream latency            # every run under data/reference/latency/hyperliquid/

Input: the run folders written by `arkstream_fetch.hl_ws_latency` (`raw.jsonl`, `arrivals.csv`, `run.json`,
`MANIFEST.csv`). Every file is checked against the run's SHA-256 manifest before it is read; events are
re-extracted from the raw lines (the raw file is the record, `events.csv` is a convenience copy).

Delay per event = corrected receive time - event time, where

* receive time = `recv_ns` (wall clock, `time.time_ns()` taken right after the socket read that completed the
  frame, before any parsing);
* corrected = `recv_ns` + clock offset to NTP, linearly interpolated in wall time between the NTP readings
  (before, any periodic readings during the run, after; ADR-0041, ADR-0057);
* event time = the `time` field (ms) of each fill or trade in the message.

Snapshot messages (`isSnapshot: true`, sent on every (re)subscribe) are history, not live, and are excluded, as
is the first `trades` message per coin on each connection (the backlog of recent trades it sends on subscribe).

A run is usable (ADR-0057, which replaces ADR-0041 item 4) if it has NTP readings before and after, no lasting
clock step over 20 ms (jumps of wall minus the high-resolution counter, after removing the linear drift, on a
5-message rolling median). Steady drift between NTP readings is corrected, not a reason to exclude. The
correction is cross-checked on the high-resolution counter; a run where the two differ by more than 5 ms at
p10/p50/p90/p99, or whose NTP uncertainty exceeds 50 ms, is kept and labelled. Every per-run number carries the
run's NTP uncertainty.

Outputs (deterministic; same files give the same bytes):

* `research/latency/hl_receive_delay.csv`: per run (and `ALL` usable runs), channel and coin (and `ALL`):
  n events, n messages, mean, p10, p50, p90, p99, max delay in ms, share of messages that arrived in a batch
  (more than one message completed by the same socket read), mean events per message, and the run's offsets.
* `research/latency/hl_receive_delay_by_size.csv`: delay against message size (bytes quintiles per channel).
* `research/latency/hl_receive_delay.md`: short summary, `userFills` first.
"""

from __future__ import annotations

import bisect
import csv
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "data" / "reference" / "latency" / "hyperliquid"
OUT_DIR = ROOT / "research" / "latency"
MAX_CLOCK_STEP_MS = 20.0       # ADR-0057: lasting steps only, after the linear drift correction
MAX_QPC_DISAGREEMENT_MS = 5.0  # ADR-0057: counter-based vs wall-time correction, at p10/p50/p90/p99
WIDE_NTP_BOUND_MS = 50.0       # ADR-0057: label, not an exclusion
QPC_CHECK_PCTS = (10, 50, 90, 99)
CHANNELS = ("userFills", "trades")
SUMMARY_FIELDS = ["run", "usable", "channel", "coin", "n_events", "n_messages", "mean_ms", "p10_ms", "p50_ms",
                  "p90_ms", "p99_ms", "max_ms", "min_ms", "batched_share", "events_per_message",
                  "offset_before_ms", "offset_after_ms", "offset_change_ms", "offset_uncertainty_ms",
                  "ntp_mid_readings", "drift_residual_ms", "clock_step_ms", "qpc_check_ms", "clock_label",
                  "excluded_reason"]
BINANCE_STUDY = ROOT / "data" / "reference" / "latency" / "binance" / "latency_study.csv"
DEBOUNCE_MS = 250.0   # ADR-0030 (config replay.debounce_ms)
COMPUTE_MS = 120.0    # Binance study, single-asset decision compute median 115 (USD-M) - 128 (spot); ADR-0038
TOTAL_PCTS = (10, 50, 90, 99)
ACK_GRID = 1000       # evenly spaced probabilities for the per-draw combination
TOTAL_FIELDS = ["method", "quantile", "receive_ms", "debounce_ms", "compute_ms", "ack_ms", "total_ms",
                "receive_n_fills", "receive_n_messages", "receive_ntp_uncertainty_ms", "receive_source", "ack_source",
                "compute_source", "label"]
SIZE_FIELDS = ["run", "channel", "size_bin", "bytes_min", "bytes_max", "n_messages", "p50_ms", "p90_ms", "mean_ms"]


# ------------------------------------------------------------------------------------------------ parsing

@dataclass(frozen=True)
class Event:
    channel: str
    coin: str
    user: str          # userFills: the subscribed address; trades: ""
    event_id: str      # fill / trade id (`tid`)
    event_ms: int      # `time` in the message, ms since epoch
    is_snapshot: bool


def extract_events(text: str) -> list[Event]:
    """Fills and trades in one stream message. Other channels (subscriptionResponse, pong, error) give []."""
    try:
        msg = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(msg, dict):
        return []
    ch, data = msg.get("channel"), msg.get("data")
    if ch == "trades" and isinstance(data, list):
        return [Event("trades", str(t.get("coin", "")), "", str(t.get("tid", "")), int(t["time"]), False)
                for t in data if isinstance(t, dict) and "time" in t]
    if ch == "userFills" and isinstance(data, dict):
        snap, user = bool(data.get("isSnapshot", False)), str(data.get("user", "")).lower()
        return [Event("userFills", str(f.get("coin", "")), user, str(f.get("tid", "")), int(f["time"]), snap)
                for f in data.get("fills", []) if isinstance(f, dict) and "time" in f]
    return []


class InitialTrades:
    """The first `trades` message per coin on each connection is the venue's backlog of recent trades (it carries
    no isSnapshot flag): mark its events as snapshot so they are not counted as live (ADR-0043)."""

    def __init__(self) -> None:
        self.seen: set[tuple[int, str]] = set()

    def mark(self, conn: int, events: list[Event]) -> list[Event]:
        if not events or events[0].channel != "trades":
            return events
        key = (conn, events[0].coin)
        if key in self.seen:
            return events
        self.seen.add(key)
        return [replace(e, is_snapshot=True) for e in events]


def channel_of(text: str) -> str:
    try:
        msg = json.loads(text)
    except json.JSONDecodeError:
        return ""
    return str(msg.get("channel", "")) if isinstance(msg, dict) else ""


# ------------------------------------------------------------------------------------------------ clock

@dataclass(frozen=True)
class ClockFit:
    """NTP offset (server - local, ns) at local wall times: before, optional readings during the run (`mid`,
    (wall_ns, offset_ns) pairs), after. Piecewise linear in wall time in between, flat outside."""
    t_before_ns: int
    offset_before_ns: int
    t_after_ns: int
    offset_after_ns: int
    mid: tuple[tuple[int, int], ...] = ()

    @property
    def points(self) -> list[tuple[int, int]]:
        inner = [p for p in self.mid if self.t_before_ns < p[0] < self.t_after_ns]
        return sorted([(self.t_before_ns, self.offset_before_ns), *inner, (self.t_after_ns, self.offset_after_ns)])

    def offset_ns(self, wall_ns: int) -> int:
        pts = self.points
        if self.t_after_ns <= self.t_before_ns or wall_ns <= pts[0][0]:
            return pts[0][1]
        if wall_ns >= pts[-1][0]:
            return pts[-1][1]
        i = bisect.bisect_right([t for t, _ in pts], wall_ns)
        (t0, o0), (t1, o1) = pts[i - 1], pts[i]
        return int(round(o0 + (wall_ns - t0) / (t1 - t0) * (o1 - o0)))

    def correct(self, wall_ns: int) -> int:
        return wall_ns + self.offset_ns(wall_ns)

    @property
    def change_ms(self) -> float:
        return (self.offset_after_ns - self.offset_before_ns) / 1e6

    @property
    def drift_residual_ms(self) -> float | None:
        """Largest distance of a reading during the run from the before-after line: how far the drift was
        from linear (ADR-0057). None without readings during the run."""
        if not self.mid:
            return None
        line = ClockFit(self.t_before_ns, self.offset_before_ns, self.t_after_ns, self.offset_after_ns)
        return max(abs(o - line.offset_ns(t)) for t, o in self.mid) / 1e6


def _ok(m: dict[str, Any] | None) -> bool:
    return bool(m) and m.get("offset_ns") is not None and m.get("local_ns") is not None  # type: ignore[union-attr]


def clock_fit(meta: dict[str, Any]) -> ClockFit | None:
    c = meta.get("clock") or {}
    b, a = c.get("before"), c.get("after")
    if not _ok(b) or not _ok(a):
        return None
    assert b is not None and a is not None
    mid = tuple(sorted((int(m["local_ns"]), int(m["offset_ns"])) for m in c.get("mid", []) if _ok(m)))
    return ClockFit(int(b["local_ns"]), int(b["offset_ns"]), int(a["local_ns"]), int(a["offset_ns"]), mid)


def _detrended(wall_ns: Sequence[int], mono_ns: Sequence[int]) -> np.ndarray:
    """(wall - counter) minus its straight line from the first to the last message, in ns."""
    d = (np.asarray(wall_ns, dtype=np.int64) - np.asarray(mono_ns, dtype=np.int64)).astype(np.float64)
    d -= d[0]
    m = np.asarray(mono_ns, dtype=np.int64)
    span = float(m[-1] - m[0])
    return d - (d[-1] * (m - m[0]) / span if span > 0 else 0.0)


def clock_step_ms(wall_ns: Sequence[int], mono_ns: Sequence[int]) -> float:
    """Largest lasting jump of (wall - high-resolution counter) between consecutive messages, in ms, after the
    linear drift is removed: a wall-clock step (ADR-0057). Taken on a 5-message rolling median, so a one- or
    two-message spike (the process paused between the two stamps) is not a step."""
    if len(wall_ns) < 2:
        return 0.0
    d = _detrended(wall_ns, mono_ns)
    if len(d) >= 5:
        d = np.median(np.lib.stride_tricks.sliding_window_view(d, 5), axis=1)
    return float(np.abs(np.diff(d)).max()) / 1e6


@dataclass(frozen=True)
class CounterFit:
    """The cross-check correction: true time as a piecewise-linear function of the high-resolution counter,
    through the NTP readings (true = wall + offset at each reading). The counter is not adjusted by the
    operating system's time service, so steps and slews of the wall clock do not enter it (ADR-0057)."""
    anchors: tuple[tuple[int, int], ...]   # (counter_ns, true_ns), sorted by counter

    def true_ns(self, counter_ns: int) -> int:
        a = self.anchors
        if len(a) == 1:
            return a[0][1] + (counter_ns - a[0][0])
        i = min(max(bisect.bisect_right([q for q, _ in a], counter_ns), 1), len(a) - 1)
        (q0, t0), (q1, t1) = a[i - 1], a[i]
        return int(round(t0 + (counter_ns - q0) * (t1 - t0) / (q1 - q0)))


def counter_fit(meta: dict[str, Any], wall_ns: Sequence[int], mono_ns: Sequence[int]) -> CounterFit | None:
    """Anchors from the NTP readings. A reading that recorded the counter (`perf_ns`) uses it; an older one is
    mapped through the nearest message's wall-counter relation (the first message for `before`, the last for
    `after`, both within seconds of the reading)."""
    c = meta.get("clock") or {}
    b, a = c.get("before"), c.get("after")
    if not _ok(b) or not _ok(a) or not wall_ns:
        return None
    assert b is not None and a is not None
    w, q = np.asarray(wall_ns, dtype=np.int64), np.asarray(mono_ns, dtype=np.int64)

    def counter_at(m: dict[str, Any]) -> int:
        if m.get("perf_ns") is not None:
            return int(m["perf_ns"])
        i = int(np.clip(np.searchsorted(w, int(m["local_ns"])), 0, len(w) - 1))
        return int(m["local_ns"]) - int(w[i] - q[i])

    pts = [b, *[m for m in c.get("mid", []) if _ok(m)], a]
    anchors = sorted({counter_at(m): int(m["local_ns"]) + int(m["offset_ns"]) for m in pts}.items())
    return CounterFit(tuple(anchors))


def usability(fit: ClockFit | None, step_ms: float) -> str:
    """'' if usable, else the reason the run is reported and not used (ADR-0057). The counter cross-check and a
    wide NTP bound are labels (`clock_label`), not exclusions."""
    if fit is None:
        return "no NTP offset before and after"
    if step_ms > MAX_CLOCK_STEP_MS:
        return f"clock step {step_ms:.1f} ms after drift correction (> {MAX_CLOCK_STEP_MS:.0f})"
    return ""


# ------------------------------------------------------------------------------------------------ runs

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while b := fh.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def verify_manifest(run_dir: Path) -> None:
    with open(run_dir / "MANIFEST.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{run_dir}: empty MANIFEST.csv")
    for r in rows:
        p = run_dir / r["file"]
        if not p.exists() or p.stat().st_size != int(r["bytes"]) or sha256_file(p) != r["sha256"]:
            raise ValueError(f"{p}: does not match MANIFEST.csv")


@dataclass
class Message:
    seq: int
    chunk: tuple[int, int]   # (conn, chunk): frames completed by the same socket read
    recv_ns: int
    nbytes: int
    channel: str
    events: list[Event]


@dataclass
class Run:
    run_id: str
    meta: dict[str, Any]
    fit: ClockFit | None
    step_ms: float
    reason: str
    messages: list[Message]
    counter: CounterFit | None = None
    mono_ns: dict[int, int] | None = None    # seq -> high-resolution counter stamp
    qpc_check_ms: float | None = None

    @property
    def usable(self) -> bool:
        return self.reason == ""


def _raw_lines(run_dir: Path) -> list[str]:
    with open(run_dir / "raw.jsonl", "rb") as fh:
        lines = fh.read().split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    out = []
    for i, ln in enumerate(lines, 1):
        extra = run_dir / "raw_extra" / f"{i}.json"
        out.append(extra.read_bytes().decode("utf-8") if extra.exists() else ln.decode("utf-8"))
    return out


def load_run(run_dir: Path) -> Run:
    verify_manifest(run_dir)
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    raw = _raw_lines(run_dir)
    msgs: list[Message] = []
    wall, mono = [], []
    initial = InitialTrades()
    with open(run_dir / "arrivals.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            seq = int(r["seq"])
            text = raw[seq - 1]
            conn = int(r["conn"])
            msgs.append(Message(seq, (conn, int(r["chunk"])), int(r["recv_ns"]), int(r["bytes"]),
                                channel_of(text), initial.mark(conn, extract_events(text))))
            wall.append(int(r["recv_ns"]))
            mono.append(int(r["mono_ns"]))
    if len(msgs) != len(raw):
        raise ValueError(f"{run_dir}: {len(msgs)} arrivals but {len(raw)} raw lines")
    fit = clock_fit(meta)
    step = clock_step_ms(wall, mono)
    run = Run(str(meta.get("run_id", run_dir.name)), meta, fit, step, "", msgs, counter_fit(meta, wall, mono),
              {m.seq: q for m, q in zip(msgs, mono, strict=True)})
    run.qpc_check_ms = qpc_check(run)
    run.reason = usability(fit, step)
    return run


def find_runs(runs_dir: Path = RUNS_DIR) -> list[Path]:
    return sorted(p for p in runs_dir.glob("*") if (p / "run.json").exists() and (p / "MANIFEST.csv").exists())


# ------------------------------------------------------------------------------------------------ stats

def delays_ms(run: Run) -> list[tuple[Message, Event, float]]:
    """(message, event, delay ms) for live fills and trades; needs a clock fit (else uncorrected)."""
    out = []
    for m in run.messages:
        corr = run.fit.correct(m.recv_ns) if run.fit else m.recv_ns
        for e in m.events:
            if not e.is_snapshot:
                out.append((m, e, corr / 1e6 - e.event_ms))
    return out


def counter_delays_ms(run: Run) -> list[tuple[Message, Event, float]]:
    """The same delays, corrected on the high-resolution counter instead of wall time (cross-check)."""
    if run.counter is None or run.mono_ns is None:
        return []
    return [(m, e, run.counter.true_ns(run.mono_ns[m.seq]) / 1e6 - e.event_ms)
            for m in run.messages for e in m.events if not e.is_snapshot]


def qpc_check(run: Run) -> float | None:
    """Largest |difference| of p10/p50/p90/p99 between the two corrections, over channels with live events."""
    a, b = delays_ms(run), counter_delays_ms(run)
    if not a or not b:
        return None
    worst = 0.0
    for ch in CHANNELS:
        x = [ms for _, e, ms in a if e.channel == ch]
        y = [ms for _, e, ms in b if e.channel == ch]
        if x and y:
            worst = max(worst, float(np.abs(np.percentile(x, QPC_CHECK_PCTS) - np.percentile(y, QPC_CHECK_PCTS)).max()))
    return worst


def clock_label(meta: dict[str, Any], qpc_check_ms: float | None = None) -> str:
    """Labels a usable run carries (ADR-0057): a wide NTP bound, and a counter cross-check above 5 ms."""
    u = _uncertainty_ms(meta)
    out = [f"wide NTP bound (+/-{u:.0f} ms)"] if u is not None and u > WIDE_NTP_BOUND_MS else []
    if qpc_check_ms is not None and qpc_check_ms > MAX_QPC_DISAGREEMENT_MS:
        out.append(f"counter check {qpc_check_ms:.1f} ms (> {MAX_QPC_DISAGREEMENT_MS:.0f})")
    return "; ".join(out)


def _stats(x: Iterable[float]) -> dict[str, float | int]:
    a = np.asarray(sorted(x), dtype=np.float64)
    if a.size == 0:
        return {"n_events": 0}
    p = np.percentile(a, [10, 50, 90, 99])
    return {"n_events": int(a.size), "mean_ms": float(a.mean()), "p10_ms": float(p[0]), "p50_ms": float(p[1]),
            "p90_ms": float(p[2]), "p99_ms": float(p[3]), "max_ms": float(a.max()), "min_ms": float(a.min())}


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return "" if math.isnan(v) else f"{v:.3f}"
    return "" if v is None else str(v)


def summarise(runs: list[Run]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    size_rows: list[dict[str, Any]] = []
    groups: dict[tuple[str, str, str], list[tuple[str, Message, float]]] = defaultdict(list)
    for run in runs:
        d = delays_ms(run)
        keys = [run.run_id] + (["ALL"] if run.usable else [])
        for m, e, ms in d:
            for k in keys:
                groups[(k, e.channel, e.coin)].append((run.run_id, m, ms))
                groups[(k, e.channel, "ALL")].append((run.run_id, m, ms))
    # batch share: per run, the share of live fill/trade messages whose socket read completed > 1 message
    chunk_sizes: dict[tuple[str, tuple[int, int]], int] = defaultdict(int)
    for run in runs:
        for m in run.messages:
            chunk_sizes[(run.run_id, m.chunk)] += 1
    by_id = {r.run_id: r for r in runs}
    for (rid, ch, coin), items in sorted(groups.items(), key=lambda kv: (kv[0][0] == "ALL", kv[0])):
        uniq = {(owner, m.seq): m for owner, m, _ in items}
        batched = sum(1 for (owner, _), m in uniq.items() if chunk_sizes[(owner, m.chunk)] > 1)
        row: dict[str, Any] = {"run": rid, "channel": ch, "coin": coin, **_stats(ms for _, _, ms in items),
                               "n_messages": len(uniq), "batched_share": batched / len(uniq) if uniq else float("nan"),
                               "events_per_message": len(items) / len(uniq) if uniq else float("nan")}
        if rid == "ALL":
            owners = sorted({owner for owner, _, _ in items})
            us = [u for u in (_uncertainty_ms(by_id[o].meta) for o in owners) if u is not None]
            labels = [lb for lb in (clock_label(by_id[o].meta, by_id[o].qpc_check_ms) for o in owners) if lb]
            row.update(usable="true", excluded_reason="", offset_uncertainty_ms=max(us) if us else None,
                       clock_label=(f"includes {len(labels)} labelled run(s); uncertainty is the "
                                    f"largest of the runs") if labels else "uncertainty is the largest of the runs")
        else:
            r = by_id[rid]
            drift = r.fit.drift_residual_ms if r.fit else None
            row.update(usable=str(r.usable).lower(), excluded_reason=r.reason, clock_step_ms=r.step_ms,
                       **_offsets(r.fit), offset_uncertainty_ms=_uncertainty_ms(r.meta),
                       ntp_mid_readings=len(r.fit.mid) if r.fit else 0, drift_residual_ms=drift,
                       qpc_check_ms=r.qpc_check_ms, clock_label=clock_label(r.meta, r.qpc_check_ms))
        rows.append(row)
    # delay against message size: quintiles of message bytes per run and channel (live messages only)
    for run in runs:
        for ch in CHANNELS:
            per_msg: dict[int, tuple[int, list[float]]] = {}
            for m, e, ms in delays_ms(run):
                if e.channel == ch:
                    per_msg.setdefault(m.seq, (m.nbytes, []))[1].append(ms)
            if not per_msg:
                continue
            pairs = sorted((nb, float(np.median(v))) for nb, v in per_msg.values())
            edges = np.unique(np.percentile([nb for nb, _ in pairs], [0, 20, 40, 60, 80, 100]))
            for i in range(len(edges) - 1):
                lo, hi = edges[i], edges[i + 1]
                sel = [d for nb, d in pairs if (lo <= nb < hi) or (i == len(edges) - 2 and nb == hi)]
                if sel:
                    a = np.asarray(sel)
                    size_rows.append({"run": run.run_id, "channel": ch, "size_bin": i + 1, "bytes_min": int(lo),
                                      "bytes_max": int(hi), "n_messages": len(sel),
                                      "p50_ms": float(np.median(a)), "p90_ms": float(np.percentile(a, 90)),
                                      "mean_ms": float(a.mean())})
    return rows, size_rows


def _uncertainty_ms(meta: dict[str, Any]) -> float | None:
    """Half the round trip of the NTP samples used, before or after, whichever is larger."""
    u = [c.get("uncertainty_ns") for c in ((meta.get("clock") or {}).get(k) or {} for k in ("before", "after"))]
    vals = [int(x) for x in u if x is not None]
    return max(vals) / 1e6 if len(vals) == 2 else None


def _offsets(fit: ClockFit | None) -> dict[str, float]:
    if fit is None:
        return {}
    return {"offset_before_ms": fit.offset_before_ns / 1e6, "offset_after_ms": fit.offset_after_ns / 1e6,
            "offset_change_ms": fit.change_ms}


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({f: _fmt(r.get(f)) for f in fields})


def summary_markdown(runs: list[Run], rows: list[dict[str, Any]]) -> str:
    lines = ["# Hyperliquid receive delay (stream, read-only)", "",
             "Delay = NTP-corrected local receive time - event time in the message "
             "(ADR-0038 item 1, ADRs 0040..0043, 0056).",
             "Snapshots excluded. Generated by `python -m arkstream latency`; do not edit by hand.", "",
             "## Runs", "",
             "| run | start (UTC) | minutes | usable | offset before / after (ms) | NTP +/- (ms) | clock step (ms) |"
             " counter check (ms) | messages | gaps | note |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        o = _offsets(r.fit)
        off = f"{o['offset_before_ms']:+.1f} / {o['offset_after_ms']:+.1f}" if o else "n/a"
        u = _uncertainty_ms(r.meta)
        lines.append(f"| {r.run_id} | {r.meta.get('start_utc', '')} | {r.meta.get('duration_s', 0) / 60:.0f} | "
                     f"{'yes' if r.usable else 'no'} | {off} | {'n/a' if u is None else f'{u:.1f}'} | "
                     f"{r.step_ms:.1f} | {'n/a' if r.qpc_check_ms is None else f'{r.qpc_check_ms:.1f}'} | "
                     f"{len(r.messages)} | {len(r.meta.get('gaps', []))} | "
                     f"{'; '.join(x for x in (r.reason, clock_label(r.meta, r.qpc_check_ms)) if x)} |")
    for ch in CHANNELS:
        sel = [x for x in rows if x["channel"] == ch and x["coin"] == "ALL" and x.get("n_events")]
        lines += ["", f"## {ch}" + (" (primary: the leg a copy engine needs)" if ch == "userFills" else ""), "",
                  "| run | usable | events | messages | p10 | p50 | p90 | p99 | max | NTP +/- | batched |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for x in sel:
            u = x.get("offset_uncertainty_ms")
            lines.append(f"| {x['run']} | {x['usable']} | {x['n_events']} | {x['n_messages']} | "
                         f"{x['p10_ms']:.0f} | {x['p50_ms']:.0f} | {x['p90_ms']:.0f} | {x['p99_ms']:.0f} | "
                         f"{x['max_ms']:.0f} | {'n/a' if u is None else f'{u:.0f}'} | {x['batched_share']:.0%} |")
        if not sel:
            lines.append("| (no live events) | | | | | | | | | | |")
    lines += ["", "Delays in ms. NTP +/- is the bound on each run's clock offset (half the best NTP round trip, the "
              "larger of the readings); for `ALL` it is the largest of the runs pooled. Per-coin rows and size bins: "
              "`hl_receive_delay.csv`, `hl_receive_delay_by_size.csv`.", ""]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ total delay

def binance_ack(study: Path = BINANCE_STUDY) -> dict[str, float]:
    """USD-M order submit -> ack quantiles (ms) from the Binance study (ADR-0038), checked against CHECKSUMS.txt."""
    sums = (study.parent / "CHECKSUMS.txt").read_text(encoding="utf-8")
    if sha256_file(study) not in sums:
        raise ValueError(f"{study}: does not match CHECKSUMS.txt")
    with open(study, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["leg"] == "order_submit_to_ack" and r["product"] == "USD-M futures":
                return {"p10": float(r["p10_ms"]), "p50": float(r["p50_ms"]), "p90": float(r["p90_ms"]),
                        "p99": float(r["p99_ms"]), "n": float(r["n"])}
    raise ValueError(f"{study}: no USD-M order_submit_to_ack row")


def ack_quantile(ack: dict[str, float], p: np.ndarray) -> np.ndarray:
    """Ack quantile function through the four published quantiles, flat below p10 and above p99 (= max)."""
    return np.interp(p, [0.10, 0.50, 0.90, 0.99], [ack["p10"], ack["p50"], ack["p90"], ack["p99"]])


def total_delay(receive: Sequence[float], n_messages: int, uncertainty_ms: float | None,
                ack: dict[str, float]) -> list[dict[str, Any]]:
    """ADR-0038 total = receive + debounce + compute + ack. Two ways: the sum of each leg's quantile (headline;
    for the tail an upper bound, as if the legs' tails coincided), and a per-draw combination of every pooled
    receive sample with the ack quantile function at ACK_GRID probabilities (legs independent)."""
    r = np.asarray(sorted(receive), dtype=np.float64)
    if r.size == 0:
        return []
    rq = np.percentile(r, TOTAL_PCTS)
    aq = ack_quantile(ack, np.asarray(TOTAL_PCTS) / 100)
    a = ack_quantile(ack, (np.arange(ACK_GRID) + 0.5) / ACK_GRID)
    draws = (r[:, None] + a[None, :]).ravel() + DEBOUNCE_MS + COMPUTE_MS
    dq = np.percentile(draws, TOTAL_PCTS)
    base = {"debounce_ms": DEBOUNCE_MS, "compute_ms": COMPUTE_MS, "receive_n_fills": int(r.size),
            "receive_n_messages": n_messages, "receive_ntp_uncertainty_ms": uncertainty_ms,
            "receive_source": "measured: Hyperliquid userFills, pooled usable runs (ADR-0056)",
            "ack_source": f"transferred_from_binance: USD-M Demo order submit -> ack, n = {ack['n']:.0f}",
            "compute_source": "transferred_from_binance: single-asset decision compute median, ~120 ms",
            "label": "partly transferred from Binance"}
    rows = []
    for i, q in enumerate(TOTAL_PCTS):
        rows.append({**base, "method": "sum_of_quantiles", "quantile": f"p{q}", "receive_ms": float(rq[i]),
                     "ack_ms": float(aq[i]), "total_ms": float(rq[i] + DEBOUNCE_MS + COMPUTE_MS + aq[i])})
    for i, q in enumerate(TOTAL_PCTS):
        rows.append({**base, "method": "per_draw", "quantile": f"p{q}", "receive_ms": None, "ack_ms": None,
                     "total_ms": float(dq[i])})
    return rows


def total_markdown(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    u = rows[0]["receive_ntp_uncertainty_ms"]
    out = ["", "## Total copy delay (ADR-0038), partly transferred from Binance", "",
           f"receive (measured, {rows[0]['receive_n_fills']} fills, NTP +/- "
           f"{'n/a' if u is None else f'{u:.0f}'} ms) + debounce "
           f"{DEBOUNCE_MS:.0f} + compute {COMPUTE_MS:.0f} (Binance) + acknowledgement (Binance USD-M Demo).", "",
           "| quantile | receive | ack | total, sum of quantiles | total, per draw |",
           "| --- | --- | --- | --- | --- |"]
    per = {x["quantile"]: x["total_ms"] for x in rows if x["method"] == "per_draw"}
    for x in rows:
        if x["method"] == "sum_of_quantiles":
            out.append(f"| {x['quantile']} | {x['receive_ms']:.0f} | {x['ack_ms']:.0f} | {x['total_ms']:.0f} | "
                       f"{per[x['quantile']]:.0f} |")
    return out


def main(runs_dir: Path = RUNS_DIR, out_dir: Path = OUT_DIR, log=print, study: Path = BINANCE_STUDY) -> int:
    paths = find_runs(runs_dir)
    if not paths:
        log(f"no runs under {runs_dir}")
        return 1
    runs = [load_run(p) for p in paths]
    rows, size_rows = summarise(runs)
    write_csv(out_dir / "hl_receive_delay.csv", SUMMARY_FIELDS, rows)
    write_csv(out_dir / "hl_receive_delay_by_size.csv", SIZE_FIELDS, size_rows)
    md = summary_markdown(runs, rows)
    if study.exists():
        pooled = [(r.run_id, m.seq, ms) for r in runs if r.usable for m, e, ms in delays_ms(r)
                  if e.channel == "userFills"]
        allrow = next((x for x in rows if x["run"] == "ALL" and x["channel"] == "userFills" and x["coin"] == "ALL"),
                      {})
        tot = total_delay([ms for _, _, ms in pooled], len({(a, b) for a, b, _ in pooled}),
                          allrow.get("offset_uncertainty_ms"), binance_ack(study))
        write_csv(out_dir / "total_delay.csv", TOTAL_FIELDS, tot)
        md = md.rstrip("\n") + "\n" + "\n".join(total_markdown(tot)) + "\n"
    (out_dir / "hl_receive_delay.md").write_text(md, encoding="utf-8", newline="\n")
    for r in runs:
        log(f"{r.run_id}: {len(r.messages)} messages, usable={r.usable} {r.reason}")
    log(f"wrote {out_dir / 'hl_receive_delay.csv'}")
    return 0
