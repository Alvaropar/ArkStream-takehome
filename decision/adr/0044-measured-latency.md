# ADR-0044: Replace the assumed copy delay with measured latency

- Status: Accepted (method); both measurements in: Binance legs (2026-11-20), Hyperliquid receive (ADR-0104); item 3
  (scenarios) amended by ADR-0150: optimistic 1 s, base 1.2 s, stress 5 s, severe 60 s / 300 s
- Date: 2026-11-20
- Phase: Phase 3 (follower replay) and Phase 6 (operations)
- Amends: ADR-0081 (event model delays)

## Context
The replay's total delay per scenario (optimistic 1 s, base 10 s, stress 60 s, 300 s for thin coins) is assumed:
the package records when each leader fill happened, not when a follower could have received it, and there is no
copy engine to time. The delay has three legs:

1. **Receive:** leader fill on Hyperliquid -> our process receives it.
2. **Decide:** our process groups visible fills (debounce, 250 ms in ADR-0081) and computes the order.
3. **Acknowledge:** order sent -> exchange accepts and fills it.

## Decision
1. **Receive (d_receive): measured on Hyperliquid, read-only.** A small recorder subscribes to Hyperliquid's public
   WebSocket (`wss://api.hyperliquid.xyz/ws`): `userFills` for a few active leader addresses from the package
   (the path a copy engine would use) and `trades` for BTC, ETH, HYPE, SOL and a few thinner coins (volume). For
   each message: local receive time (clock offset to NTP measured and recorded) minus the event time in the message.
   No order is ever sent; the existing rule that only market-data code may touch the network stays. Brief:
   `decision/briefs/latency-hl-receive.md`.
2. **Decide and acknowledge (d_decide compute, d_ack): taken from the user's separate Binance trading repository**,
   where order submission and acknowledgement have been measured. Brief: `decision/briefs/latency-binance-results.md`.
   They are used as stated by that study, with its source (repository, commit, period, environment) recorded here
   when they arrive, and labelled `transferred_from_binance`: Hyperliquid's own order acknowledgement cannot be
   measured without sending orders, which this project forbids.
3. **Scenarios from the measurements.** Once both arrive, total delay = d_receive + debounce + compute + d_ack per
   draw; optimistic = the 10th percentile of the total, base = the median, stress = the 99th percentile (thin
   coins: the stress value or 300 s, whichever is larger). The replay is rerun with these, and the current 1 / 10 /
   60 s scenarios are kept as labelled sensitivities. Every number carries its source and date.

## Binance study received (2026-11-20)
Files: `data/reference/latency/binance/latency_study.csv` and `.md` (SHA-256 in `CHECKSUMS.txt` beside them;
originals delivered to `decision/`). Source: the user's quant-ai-harness repository (order journals
`r4b-demo-journals-4`, measurement at commit `42466a1`; market-data recorder report SHA-256 `0819ec97…2296`).
Environment: GCE europe-west4 (Netherlands), not co-located; Binance **Demo** for orders (MARKET, 0.0002-0.002 BTC,
n = 30 per venue), Binance mainnet public streams for market data. What is usable here, labelled
`transferred_from_binance`:

| Leg | USD-M figure (ms) | Use in the replay |
| --- | --- | --- |
| order submit -> ack (POST answer) | p10 322, p50 354, p90 574, p99 = max 2,767 (n = 30) | d_ack |
| decision compute | 115-128 median for a single-asset decision; 5,268 for a cross-sectional basket | d_decide compute: the copy engine's decision is a netting step, closer to the single-asset figure |
| gateway pre-send reconciliation | p50 4,178 | **not used**: a property of that harness (it reconciles synchronously before every send); the copy engine reconciles asynchronously (plan, Live operating model) |

Not used: the market-data receive legs (Binance kline closes, not Hyperliquid fills) and the user-stream legs
(waits on that harness's lock). Caveats carried with the numbers: Demo is not mainnet; n = 30 makes p99 a single
order; the network path (Netherlands to Binance) is not the path to Hyperliquid. Scenarios are set only after the
Hyperliquid receive delay (item 1) is measured.

## Hyperliquid receive delay measured (2026-11-21)
ADR-0104: `userFills` pooled over three runs, 284 fills: p10 265, p50 392, p90 793, p99 1,218 ms (run medians
339-738 ms; home Wi-Fi laptop; NTP bound up to +/-83 ms). Total = receive + debounce 250 + compute ~120 + ack
(Binance USD-M Demo): about 1.1 s at the median and 4.4 s at p99 (sum of quantiles), partly transferred from Binance.
Item 3 was not carried out: the 1 / 10 / 60 s scenarios are unchanged. The 10 s base and 60 s stress are
conservative against the measured total, and the existing 1 s point is the closest case consistent with it.

## Consequences
Until both measurements land, the assumed scenarios remain in force and are labelled assumptions. The Binance
figures include network and engine time measured on a different venue; the gap is stated, not corrected. The
recorder adds a read-only WebSocket dependency to `src/arkstream_fetch` only, with a host allowlist and a test that
it cannot reach any order endpoint.
