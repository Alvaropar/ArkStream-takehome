# ADR-0103: Receive-delay definition, snapshot exclusion, batching and outputs

- Status: Accepted
- Date: 2026-11-20
- Phase: Phase 3 / Phase 6 (latency measurement, ADR-0044 item 1)

## Context
Each stream message can carry several fills or trades, each with its own `time` (ms). On every subscribe the
venue first sends history. `userFills` marks it `isSnapshot: true`. The first `trades` message per coin is also
a backlog, of the last 30 trades, but carries no flag: in the first smoke run those trades were 0.7 s to 21 min
old and set the maximum delay to 1,258 s.

## Decision
1. **Delay per event** = corrected receive time (ADR-0101) - the event's `time`, in ms. Every fill or trade in a
   message gets that message's receive time.
2. **Excluded as history:** `userFills` with `isSnapshot: true`, and the first `trades` message per coin on each
   connection (`arkstream.latency.InitialTrades`; the recorder's `events.csv` marks it the same way).
3. **Batching.** A message arrived in a batch when the socket read that completed it also completed another
   message. `batched_share` is the share of live messages in a group that arrived that way. `events_per_message`
   is the mean number of fills or trades per message.
4. **Size.** For each run and channel, each live message's median event delay, binned into quintiles of message bytes:
   `research/latency/hl_receive_delay_by_size.csv`.
5. **Outputs** (`python -m arkstream latency`, no network, byte-identical on rerun):
   - `research/latency/hl_receive_delay.csv`: per run, channel and coin, plus `coin = ALL` and `run = ALL`
     (usable runs only). Columns: n events and messages, mean, p10, p50, p90, p99, max, min, batched share,
     events per message, the offsets, change, uncertainty, clock step, and the reason a run is excluded;
   - `research/latency/hl_receive_delay.md`.
   Events come from `raw.jsonl` after the manifest check. `events.csv` is a convenience copy.
6. **Feeding ADR-0044:** d_receive is the `userFills` empirical distribution from `run = ALL`, drawn per copy
   event. The `trades` distribution is reported beside it as a cross-check with more events. This is the leg a copy
   engine needs, because it learns of a leader's fill from `userFills`, not from `trades`.

## Consequences
Second smoke run (4 min, not a measurement): trades p50 331 ms, p90 439 ms, p99 666 ms, max 1.4 s; 49% of
messages batched; no live `userFills` yet. A negative delay of a few ms is possible within the clock uncertainty
and is kept, not clipped. Tests cover the delay with correction, snapshot and backlog exclusion, batching, the
moving-offset exclusion, manifest tampering and deterministic output.
