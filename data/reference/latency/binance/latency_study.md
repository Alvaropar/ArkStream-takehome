# Binance latency study, from existing measurements

**Written 2026-11-20 from the quant-ai-harness repository's existing evidence.** No new orders
were sent, and nothing was run against a venue. The only computation added is a read-only leg
breakdown over the order journals that the harness had already copied to the laptop. It reads
the same records and the same 30 counted fills per venue as the harness's own measurement. Its
combined dispatch-to-fill p99 reproduces the pinned values exactly: spot 1,620.79 ms, USD-M
4,049.57 ms.

The numbers are in `latency_study.csv`, one row per leg and setup. That file adds a
`definition` column to the requested columns, giving each row's exact start and end points.
This file says how each leg was measured, and what does not transfer to another exchange.

No API keys, account identifiers, balances, order ids or trade ids appear in either file.

## The three bodies of evidence

| Evidence | What it measures | Where, when | Produced by |
|---|---|---|---|
| A. Arrival delays | Market data: closing klines over public mainnet WebSockets | `qh-recorder-1`: GCE e2-small, europe-west4-a. Run began 2026-11-10 06:24 UTC, ran 100 h. Report days 2026-11-11 to 11-13 UTC. | `qh paper delays` (`services/qh-paper/src/qh_paper/live/delays.py`, commit `f8ebd54`), analysis base `50147b7c`. Report `arrival-delays-report.json`, SHA-256 `0819ec97…2296`. |
| B. Demo order journals | Order legs: Binance **Demo** (not testnet, not mainnet), MARKET orders on BTCUSDT through the harness's risk gateway | `qh-soak-2`, GCE europe-west4-a. Spot 2026-11-18 05:29 to 11-19 05:13 UTC. USD-M 2026-11-19 07:01 to 08:06 UTC. | Evidence-archive `order` records, copied as `r4b-demo-journals-4.tar.gz` (SHA-256 `696fd2ca…b021`, 95 files, 0 manifest mismatches). The pinned measurement is `qh_compute.delayed_decision.execution_latency` at commit `42466a1` (branch `remediate/r4b`), giving `demo-latency-e.json`. |
| C. Replay evaluation time | Strategy compute per decision | The user's Windows laptop, research-period replays, in a guarded child (3 GB cap, 2 Polars threads) | `qh paper replay` (`qh_paper.live.replay` / `evaluate.py`), reported in `docs/phases/phase7/7c1/phase7-7c1-live-signals.md` (doc commit `6e5d134`). |

The order rounds ran on four releases of the paper service:
- spot rounds 13–14 on `87fd9dd`, 16–20 and 22–23 on `ae53659`, 26–31 on `5cc2c5b`;
- USD-M rounds 1–3 on `5cc2c5b`, 5–16 on `44d1b1b`.

None of these releases contains the later gateway lock fix (`5db253a`), which matters for USD-M's
tail (see Biases).

## How each leg was measured

All order-leg times are nanosecond wall-clock stamps (`time.time_ns()`) on the soak VM. The order
manager and the risk gateway run as two processes on that one VM, so legs between their stamps
share one clock. "Cross-clock" legs subtract a VM stamp from a Binance millisecond timestamp,
with no correction.

### market_data_receive (evidence A)

- **Start:** the kline's nominal close time (end of the bar), on Binance's clock.
- **End:** `ts_received`, the recorder's wall clock when it received the stream message carrying
  the closed bar, plus the measured clock offset.
- **Formula:** `ts_received + offset − close_time`.
- **Endpoints:**
  - spot: `wss://data-stream.binance.vision/stream`;
  - USD-M: `wss://fstream.binance.com/market/stream`.

  These are mainnet public streams, not Demo.
- **Samples:** spot 1m (4,320), spot 15m (288), spot 1d (3); USD-M 1m (4,320) and USD-M 1d for 522
  symbols (1,566), all closing at 00:00 UTC at once.
- **The summary gives quantiles p50, p90, p99, p99.9 and max** (nearest rank). It does not give
  the mean or p10, so those cells are empty rather than estimated. The 7 GB raw tar is on the
  laptop, and `qh paper delays` could recompute them, but it wasn't rerun because the summary
  exists.
- **p99.9 (corrected):**

  | Stream | p99.9 |
  |---|---|
  | spot 1m | 347.6 ms |
  | spot 15m | 559.5 ms |
  | USD-M 1m | 2,494.1 ms |
  | USD-M 1d | 3,213.1 ms |
- **Counts:** zero missing bars, zero conflicts, zero uncorrected and zero negative corrected
  latencies.
- **What the recorder's run is established by:** its existence and its 100 hours are attested by
  the user, and its counts match three full days. The archive's continuity and seals were not
  verified locally.
- **The 00:00 UTC burst is real:** USD-M 1d's p90 is 3.14 s, because 522 symbols close at once.
  USD-M 1m's tail, p99 1.55 s, is also much heavier than spot's, 250 ms.

### decision_compute (evidence C)

- **What it is:** wall-clock duration of one decision evaluated alone (spec plus point-in-time
  state, giving target weights), in a replay of the research period.
- **Measured on the laptop, not a VM.** No live-VM evaluation latency was ever recorded.
- **Reported figures:** median, p99 and max only. Mean and p90 were not reported.
- **Varies by strategy and state size:**
  - daily single-asset strategies: 0.12–0.13 s median;
  - a 15-minute EMA: 0.78 s median, growing with history;
  - a daily cross-sectional basket of USD-M perpetuals: 5.3 s median, up to 15.1 s at its
    largest state.
- **Measurement dates** were not recorded beyond the document's commit, 2026-11-07, so
  `period_start` and `period_end` say "not recorded".

### gateway_admission (evidence B; harness-specific)

- **Start:** the intent's `decision_time`, stamped by the order manager when the latency round
  created the order intent.
- **End:** `ts_sent`, the gateway's dispatch stamp, taken just before the HTTP POST.
- **What it covers:**
  - the risk gateway's admission checks;
  - a fresh reconciliation of signed REST reads against the venue (open orders, trades,
    account; about 1 s each on USD-M Demo);
  - the request's signing.
- **Not a strategy-compute leg:** the latency rounds' intents are fixed, not computed by a
  strategy.
- **Shown separately** because it dominates the decision-to-fill total: spot median 1.96 s,
  USD-M 4.18 s.

### order_submit_to_ack (evidence B)

- **Start:** `ts_sent` on the `submit_sent` record, the gateway's dispatch stamp just before
  `POST /api/v3/order` (spot) or `POST /fapi/v1/order` (USD-M).
  - It is the same stamp that the pinned measurement uses.
  - The gateway's separate `dispatch_time` record is 2.5–14 ms later.
- **End:** `ts_received` on the `submit_ack` record. That is the order manager's receipt of the
  POST answer, relayed from the gateway over a local Unix-socket RPC.
- **Includes:**
  - the network round trip from europe-west4 to Binance Demo;
  - Binance's matching;
  - the gateway's relay;
  - any wait for the gateway's lock.
- **Response types:** spot asks for `newOrderRespType=FULL`, so the answer carries the fills;
  USD-M asks for `RESULT`.
- **Counted orders:** MARKET, 0.0002 BTC on spot and 0.002 BTC on USD-M.
- **The 15 rounds per venue counted** are those whose buy and sell both filled.

### ack_to_fill (evidence B)

- **Start:** the POST answer's receipt.
- **End:** the first `fill` record's `ts_received`, when the order manager holds the fill's
  price and quantity.
- **Spot: 0.** The FULL answer already carries the fills.
- **USD-M:** the answer already has status `FILLED`, but price and quantity come from a follow-up
  REST lookup, `GET /fapi/v1/userTrades`.

  So the measured 289 ms median is "fill details known". If your system acts on status alone, a
  USD-M MARKET fill is known at the ack.
- **The private stream** also reports fills (see `user_stream_delivery`). In every counted order
  REST got there first, so the first fill record is from REST for all 60.

### round_trip_total (evidence B)

There are two rows per venue:
- **Dispatch to fill known.** This is order_submit_to_ack plus ack_to_fill, the harness's frozen
  `e`, and its p99 is the pinned value.
- **Intent decision time to fill known.** This adds gateway_admission.

### submit_to_venue_match and user_stream_delivery (evidence B; cross-clock)

- **submit_to_venue_match** runs from `ts_sent` to Binance's transaction or update time in the
  order answer. It covers the one-way trip plus matching: medians are 193 ms on spot and 153 ms on
  USD-M.
- **user_stream_delivery** runs from Binance's event time `E` in the first execution report to the
  gateway's recorded receipt.
  - Spot uses the WebSocket API user-data subscription.
  - USD-M uses the listenKey stream.
  - USD-M's 595 ms median and 3.9 s maximum are mostly waiting for the gateway's lock (see
    Biases), not the network. The report shows Binance publishing the event 188–239 ms after
    dispatch even in the tail orders.
- **Both legs are uncorrected for clock offset.** See Clock synchronisation.

### network_rtt

- **No ping-style RTT to the order endpoints was measured.** WebSocket ping and pong were logged
  as liveness events, without send times.
- **What exists:**
  - **The recorder's clock samples to `GET /fapi/v1/time`** (mainnet). Each measurement takes
    several samples and keeps the lowest round trip. The summary gives only that best sample's
    uncertainty range, 110.6–136.7 ms, so the best RTT was between 221 and 273 ms. That's the
    only network RTT figure, and it is a minimum per measurement, not a distribution. The CSV row
    has `max_ms` 273.4 and the minimum, 221.2, in `definition`.
  - **The gateway's REST order-book snapshots** (`GET depth`, `limit=1000`) on Demo: 9 spot,
    10 USD-M. These are heavy requests and include server work and payload, so they are an upper
    bound, not an RTT.
  - **The gateway's own server-time probe.** Only its last value survives, and it implies a 1.0 s
    spot round trip and a 1.5 s USD-M round trip. That isn't plausible as a network RTT, since the
    probe runs on a worker thread beside the reconciliation, so it is not in the CSV.

## Clock synchronisation

- **Same-clock legs** (gateway_admission, order_submit_to_ack, ack_to_fill, round_trip_total, the
  depth snapshots) take both stamps on one VM's wall clock, so the VM's absolute offset cancels.
  - What remains is wall-clock stepping during a leg. The harness detects jumps of the wall clock
    against the monotonic clock in the recorder (ADR-0018 D11), not in these legs.
  - The soak VM's clock is disciplined by chrony; its offset was not stored per sample.
- **Market data (A):**
  - **The offset is measured, not assumed.** It is `server_time − midpoint(send, receive)` from
    the lowest-RTT of several `GET /fapi/v1/time` calls, and is re-measured periodically. A bar
    received before the first measurement, or after a detected wall-clock jump, is left out:
    zero were.
  - **Its uncertainty is half the RTT, 110.6–136.7 ms.**
  - **Corrected and raw latencies differ by under 1 ms at p50.** So the recorder's GCE clock and
    Binance's agreed to about a millisecond at the midpoint, within ±111–137 ms.
- **Cross-clock order legs (B):**
  - **Uncorrected.** If the soak VM's offset is near zero, like the recorder's in the same zone a
    week earlier, they are about right, but that is an inference, not a measurement.
  - **The gateway's own offset values are unreliable.** It probes server time every 10 s, with
    uncertainty `|offset| + RTT/2 + 1 ms`. Its last values were +350 ms ±828 ms (spot, 2026-11-19
    05:30 UTC) and +70 ms ±831 ms (USD-M, 08:08 UTC), which are not usable for correction. Taken
    at face value, spot's +350 ms would make spot's submit_to_venue_match negative, so it reflects
    an asymmetric, slow probe, not the clock.

## Known biases and exclusions

- **Exclusions.** Rounds whose orders did not both fill are left out. Nothing was dropped as an
  outlier.

  | Venue | Excluded rounds | Why |
  |---|---|---|
  | Spot | 15 | buy ambiguous, halted |
  | Spot | 21, 24 | refused before sending |
  | Spot | 25 | gateway crash |
  | USD-M | 4 | the sell was refused with `-1021` (timestamp outside `recvWindow`), because the request's timestamp was stamped before a slow pre-send reconciliation; fixed in `44d1b1b` by stamping at dispatch |
- **Retries.** Every counted order was sent once (`attempt` 0). No rate-limit (429/418) answers
  appear in the order or gateway archives (searched for 429, 418, -1003).
- **Sample size.** n = 30 per venue, so the nearest-rank p99 is the maximum: one order.
  - **Spot's p99 of 1,620.8 ms is a single sell (round 30).** Every other spot sample is under
    353 ms, so without it the p99 would be 352 ms. Its cause was not diagnosed.
    Binance's own update time puts the delay after matching, between the venue and the
    manager's receipt (1.43 s cross-clock).
  - **USD-M has a tail of five samples between 3.0 and 4.05 s** (rounds 6, 9, 10, 12 and 13).
    Every other USD-M sample is under 1.3 s.
- **USD-M's tail is the harness's own lock, not Binance.**
  - **What holds it:** the risk gateway's 10-second reconciliation held a single lock across all
    its signed REST reads, about 1 s each on USD-M Demo. Recording a stream report and every
    manager call, the fill lookup included, waited on that lock.
  - **Two shapes:**
    - In the tail orders, Binance traded 167–215 ms after dispatch, but the fill was known
      3.1–4.2 s later.
    - In rounds 12 and 13, the POST answer itself was held for about 2.7 s.
  - **The fix and the frozen figure:** fixed after these rounds in `5db253a` (the reconciliation
    now reads the venue outside the lock), but not re-measured. So the USD-M figures here are an
    upper bound for the harness as it is now.
- **Demo is not mainnet.**
  - Demo matching, its liquidity and its endpoints' location and load can differ from
    production.
  - Fills of 0.0002 BTC (spot) and 0.002 BTC (USD-M) say nothing about slippage or partial fills at size.
- **Uneven coverage.**
  - **Spot rounds spread over two days** and three releases. **USD-M ran in one hour** on one
    morning, 2026-11-19 07:01–08:06 UTC, so time-of-day effects aren't sampled.
  - **Market data and orders were measured on different VMs, a week apart.** Both are in
    europe-west4-a.
  - **decision_compute was measured on a laptop,** not either VM.
- **What a closing kline measures.** It counts from the bar's nominal close, so it includes
  Binance's own kline aggregation and publishing delay, not only network transit.

## What does not transfer to another exchange

- **The location.** Every figure is from GCE europe-west4 (Netherlands) to Binance, so it
  includes a long-haul path. Binance's matching is generally reported to be in AWS Tokyo; the
  repository does not record this. A venue elsewhere, or a co-located or same-region host, would
  have very different network legs. Nothing here is co-located.
- **The harness's own stack.**
  - **gateway_admission** (the pre-send reconciliation and risk checks) and the lock effects on
    USD-M are properties of this harness. They are not exchange latency.
  - **ack_to_fill** depends on Binance's response types (FULL for spot, RESULT for USD-M) and on
    the harness's choice to wait for a trade lookup.
  - **A venue that returns fills in the order answer,** or only over a stream, has a different
    shape.
- **Binance's market-data cadence.** The 00:00 UTC burst, when every daily kline closes at once,
  and the USD-M 1m tail are specific to Binance's kline publishing.
- **Clock handling.** The offset method uses Binance's `/time` endpoint. Another venue needs its
  own time source and recvWindow-style rule; the `-1021` failure is Binance-specific.
- **Demo versus production:** see above.

## Reproducing

- **The pinned `e`:**

  ```
  uv run --no-sync python scripts/r4b_delayed_plan.py --journal-latency <r4b-demo-journals-4>
  ```

  Run it with `--round-logs` and `--count spot=13,14,16-20,22,23,26-31 --count usdm=1-3,5-16`,
  on branch `remediate/r4b`.
- **The per-leg split** reads the same archive's `order` records (`submit_sent.ts_sent`,
  `submit_ack.ts_received`, the first `fill.ts_received`, `exchange_update_time`, the
  user-stream `reconcile` records' `ts_exchange` and `ts_received`) and the gateway's
  `gateway_decision.decision_time`.
- **Market data:** `qh paper delays` over the recorder archive, for 2026-11-11 to 11-13.
