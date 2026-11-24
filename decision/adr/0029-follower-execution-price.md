# ADR-0029: Price follower orders at acknowledgement

- Status: Accepted; amended by ADR-0044 (copied coins as of each origin) and ADR-0048 (base drift below 300 s); and ADR-0053 (stress fallback)
- Date: 2026-11-20
- Phase: Phase 3, follower replay
- Resolves: the execution-price choice in the Phase 3 brief, including ADR-0020 item 5

## Context

The follower trades on Hyperliquid. The package records leader fills, and the available
trade-level reference is on Binance. BTC, ETH, HYPE and SOL have verified aggTrades
archives. Of the 195 core perps, a further 159 pass the Binance price check but lack those
archives. For them the shortest coin-specific drift estimate is 300 seconds. The remaining
22 failed the check and 10 have no mapping. Use the existing source assignments as research
configuration at each origin, as in ADR-0024. The 10–60 s kline comparison and the venue-basis
trials are recorded in the [trial log](../../provenance/trial_log.md).

## Decision

Price each nonzero follower order once, at simulated acknowledgement. A decision can consume
only leader fills received by its decision time. Acknowledgement must fall strictly after
the latest visibility time among its source fills and within the replay window. Define
`L` as the first visible leader fill price in this debounce batch, using chain order for
same-time fills. This matches the first-fill anchor in the drift estimator and avoids
using later fragments of the parent order. Keep every contributing fill key.

| Core-perp group | Reference price at acknowledgement, before spread, impact and fees |
| --- | --- |
| BTC, ETH, HYPE, SOL | Use B(ack) / B(t_leader), the ratio of the last eligible Binance aggTrade at each endpoint. Each trade must be at most 1 s old. The acknowledgement print must also follow the batch's latest visibility time. Break a millisecond tie by greatest aggregate trade ID. Read the manifest-listed zip inside the symbol's valid mapping interval and convert with its price factor. Label `binance_aggtrade`. A missing file, stale print or empty interval leaves the order unpriced. |
| Other passing coin, delay of 300 s or longer | Use the coin's ADR-0005 approximate mean for the exact delay and leader holding-time band. Apply the published signed mean once to `mid_L`. Label `parameterised` with method `coin_approximate`. The estimate already includes the applicable venue-basis correction. |
| Other passing coin, delay below 300 s | Use the four aggTrades coins as donors at the exact horizon and band. Compute the mean of their signed means weighted by their measured order counts. Label `parameterised` with method `four_coin_proxy`. For stress take the larger signed cost of this proxy and the coin’s own stress-period 300 s estimate using the same band lookup. Both estimates are required. Transferring liquid-coin drift to another coin is a scenario assumption. This path uses no one-minute bar to measure the short move. |
| Failed or unmapped coin | Skip copying. Record `failed_price_check` or `no_binance_mapping` for each affected order. Keep the address and its leader evidence. A Hyperliquid 4h close can value a daily holding but cannot establish a seconds-later fill. |

**Parameter lookup.** Read the drift vintage's holding band from `drift_hold_bands`, including
`no_closed_trip` when applicable. For a missing or undersized coin-band cell, try that
coin's `all` row at the same horizon, vintage, period and source. For the donor proxy,
apply this lookup separately to each of the four coins, then combine one usable row per
coin. Require `estimate = ok` and a finite mean for each required row. The existing minimum
of 30 measured orders per cell is a PLACEHOLDER. Missing donors, an unsupported horizon,
an invalid mapping interval or an unavailable coin estimate leave the order unpriced.
Preserve the reason. Keep a genuine negative signed mean as measured.

Optimistic and base use the development pool, which excludes 10–11 October. Stress uses
the stress pool on parameterised orders. On 8 October that pool does not yet exist. Mark the
affected orders `stress_sample_unavailable` and report stress coverage alongside returns.
The four direct-price coins use the order-specific observed Binance move in all three scenarios.

**Point in time.** For a development test window, freeze the calibration at its opening
origin. Each contributing drift observation must finish strictly before that origin.
For training orders use the latest vintage available by the decision, never the later
training endpoint's fit or band. Before the first published origin, construct the same
expanding estimate and bands through the previous UTC day, starting with the configured
8 September history. Where there is insufficient history, retain the coverage gap. Apply
the same time discipline to fitted spread inputs. End the final development test at
2025-12-03 00:00 UTC, exclusive. The 3 December origin supplies training only.

**From reference price to cash.** Let `s` be +1 for a follower buy and −1 for a sell.
Let `a` be the anchor side and `m` be +1 for a taker anchor and −1 for a maker anchor,
from `is_maker`. Apply the effective scenario half-spread once to recover the mid estimate
`mid_L = L × (1 − a × m × w / 10,000)`. Save m, the adjustment and mid_L.
Multiply mid_L by B(ack) / B(t_leader) on the direct path, or by (1 + a × d / 10,000)
for signed parameter d in bps. Record the removed Binance level basis as
10,000 × (B(t_leader) / L − 1), with both underlying prices. A16 estimates that Binance leads BTC, ETH and SOL by 1–1.5 s and lags HYPE by
about 0.25 s. Use the recorded timestamps. The optimistic 1 s case lies within venue-lag
precision.

Apply scenario costs from `config/execution.yaml`. For half-spread `w` and assumed
impact `i`, both in bps, `P_fill = P_ref × (1 + s × (w + i) / 10,000)`.
Debit the taker fee once on absolute executed notional, `abs(quantity) × P_fill × 4.5 / 10,000`.
BTC and ETH receive the majors spread. Apply any increase from the development-only,
bias-checked half-spread estimate in the spread study. Keep funding as its own cash flow
on the follower's held position under ADRs 0009 and 0024. The zero-delay, zero-cost
leader-fill benchmark is labelled **unattainable**.

## Consequences and checks

Parameterised orders receive mean shortfall. This understates copy-series volatility for those coins and can distort Sharpe. Include this caveat wherever follower volatility or Sharpe is reported.

- Preserve trader, coin, tid, oid, source row and event time for every leader fill in the
  batch, plus visibility, decision and acknowledgement times. Record the archive file,
  trade ID and print time, or the anchor and all parameter keys, weights and vintage.
  Store reference price, fill price, signed shortfall, spread, impact, fee and skip reason
  separately so the cash entry can be reproduced.
- Report the 32-coin exclusion by origin, window and scenario. Count affected follower
  order intents and their share of all intents before the source filter. Report intended
  notional at the visible leader anchor wherever sizing is known. To put a USDC value on
  the omission, compare the same fixed-allocation, zero-delay, zero-cost benchmark with
  and without those coins. Use identical sizing on common legs, Hyperliquid daily marks
  and separately identified funding. Report the signed PnL difference and coverage.
  This measures the omitted contribution at leader prices. Actual delayed PnL for those
  legs is unobservable. Missing marks or funding leave the affected comparison incomplete.
- The event-time test must reject a direct print at leader fill time, a print at visibility,
  a print after acknowledgement, or a batch containing a fill received after the decision.
  Test the staleness boundary, timestamp ties, buy and sell costs, missing parameter cells,
  and the absent 8 October stress sample. Changing later observations must leave earlier
  orders unchanged. The 2025-12-03 through 2026-01-04 holdout test window is excluded
  from all Phase 3 scenarios, benchmarks and diagnostics.
