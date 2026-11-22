# Brief: measure Hyperliquid receive delay from the public WebSocket

Written 2026-11-20. Project: `C:\Projects\quant-task-arkstream` (ArkStream Hyperliquid copy pilot). ADR numbers
reserved for this session: **0100-0109**. Decision this implements: ADR-0044 item 1.

## Why

The follower replay assumes how long it takes a copy engine to learn about a leader's fill. That leg can be measured
on Hyperliquid without trading: subscribe to the public WebSocket and compare when each message arrives with the
event time it carries.

## Scope

1. **Recorder** `src/arkstream_fetch/hl_ws_latency.py`, read-only:
   - connects only to `wss://api.hyperliquid.xyz/ws` (host allowlist), subscribes to `userFills` for 5-10 active
     leader addresses taken from `data/raw/fills.csv` (most fills in the last 14 days of the data) and to `trades`
     for BTC, ETH, HYPE, SOL and 3-4 thinner coins;
   - for every message records the local receive time (`time.time_ns()` taken on arrival, before parsing), the event
     time in the message, the channel, coin, and the fill or trade id; appends raw messages unchanged to a JSONL file
     with a SHA-256 manifest;
   - reconnects with bounded backoff, logs gaps, and runs for a set duration;
   - never sends anything except subscribe messages. No `exchange` endpoint, no signing, no keys.
2. **Clock.** Measure the local clock's offset to NTP before and after each run (for example `w32tm /stripchart
   /computer:time.windows.com /samples:5`), record it, and correct receive times by it. A run whose offset moves by
   more than 20 ms is reported and not used.
3. **Runs.** At least three runs of 1-2 hours at different times of day (including a busy US session), recorded in
   `data/reference/latency/hyperliquid/` with the machine and network described (no IP addresses).
4. **Analysis** `src/arkstream/latency.py` (no network): delay = corrected receive time - event time, per channel,
   coin and run: n, mean, p10, p50, p90, p99, max; the share of messages that arrive in batches; delay against
   message size. `userFills` is the primary result: it is the leg the copy engine needs. Output
   `research/latency/hl_receive_delay.csv` and a short markdown summary.
5. **Safety test.** `tests/test_audit_and_safety.py` currently forbids the word `websocket` in `src/arkstream_fetch`.
   Allow it only in `hl_ws_latency.py`, only for the allowlisted host, and keep forbidding `/exchange`, order
   placement and signing everywhere. Add tests for the delay computation, the clock correction and the allowlist.

## Rules

- No order-sending code, now or later ("No code path that sends real orders ... unless explicitly enabled").
- Network code only in `src/arkstream_fetch`; any new dependency (a WebSocket client) is added for that package
  only and recorded in an ADR.
- Raw messages kept unchanged with checksums; analysis deterministic (same files, same output).
- Record decisions as ADRs in `decision/adr/` (numbers 0100-0109; update the index rows for yours).

## Done when

The recorder and analysis exist with tests; ruff, mypy, pytest and the audit pass; three usable runs are on disk;
`research/latency/hl_receive_delay.csv` gives the `userFills` delay distribution, with clock offsets stated; and an
ADR records the result and how it feeds ADR-0044.

---

## Prompt to start the session

> Read `decision/briefs/latency-hl-receive.md` in `C:\Projects\quant-task-arkstream` and carry it out: build a
> read-only recorder for Hyperliquid's public WebSocket (`userFills` for a few active leader addresses and `trades`
> for a few coins) and measure the receive delay, local arrival time minus event time, with the clock offset to NTP
> measured and corrected. Read `decision/adr/README.md`, ADR-0044 and `src/arkstream_fetch/fetch_aggtrades.py`
> first. Never send anything but subscribe messages, and keep the host allowlist and the no-order tests. Build and
> test the recorder, then stop and tell me before the long recording runs so I can choose when to run them.
> Record decisions as ADRs numbered 0100-0109.
