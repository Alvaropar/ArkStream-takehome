# ADR-0058: Set the replay's delay scenarios from the measured copy delay

- Status: Accepted (the user's decision, 2026-11-21, made from the measurement and before any Phase 4 selection
  result)
- Date: 2026-11-21
- Phase: Phase 3 (follower replay), rerun before Phase 4
- Amends: ADR-0038 item 3 (scenarios from the measurements), ADR-0056 decision 4 ("replay scenarios are not
  changed"), the delay values of ADR-0030's event model, and the scenario table of the plan's "Follower replay"
  section. Mechanics: ADR-0059 (milliseconds, horizons, delay grid) and ADR-0060 (the severe scenario).

## Context
The replay's delays were assumptions: optimistic 1 s, base 10 s, stress 60 s (300 s for thin coins). The copy delay
is now measured (ADR-0038, ADR-0056): Hyperliquid `userFills` receive delay (pooled 284 fills: p10 265, p50 392,
p99 1,218 ms) + the 250 ms debounce + about 120 ms decision compute + the Binance USD-M Demo acknowledgement (p50 354,
p99 2,767 ms; `transferred_from_binance`). The total is about 1.1-1.2 s at the median (1,116 ms summing quantiles,
1,225 ms per draw) and 3.5-4.4 s at the 99th percentile (3,540 ms per draw, 4,354 ms summing quantiles). Against
that, the 10 s base was about 9 times the measured median and the 60 s stress about 14 times the measured p99.

The recordings also show disconnects of 2.2-17 s (ADR-0056: three gaps over about 4.5 hours, from a recorder defect
since fixed). Fills during a gap arrive in the next snapshot, so they are excluded from the delay sample: the p99
of delivered messages does not capture an outage.

## Decision
1. **Scenarios** (`config/execution.yaml`, in whole milliseconds, ADR-0059):

   | Scenario | Delay | Was | Basis |
   | --- | --- | --- | --- |
   | optimistic | 1 s (unchanged) | 1 s | about the measured 10th percentile total (957-994 ms) |
   | **base** | **1.2 s** | 10 s | the measured median total, from a home laptop on Wi-Fi (a professional setup would be faster) |
   | **stress** | **5 s, every coin** | 60 s; 300 s for thin coins | the measured 99th percentile total (4,354 ms summing quantiles), rounded up |
   | severe (new, labelled sensitivity) | 60 s; 300 s for thin coins | (the old stress) | kept because the recordings show 2-17 s disconnects that the p99 of delivered messages does not capture |

2. **Costs other than the delay are unchanged**: fees, half-spreads, impact, the stress multipliers, the stress
   fallback (ADR-0053), the coverage rule (ADR-0049, ADR-0055). Stress keeps its 3 / 15 bps half-spreads, triple
   impact, stress-period drift and deepest sweep anchor; severe uses the same stress costs with the old delays
   (ADR-0060).
3. **Departures from ADR-0038 item 3**, chosen by the user: the stress delay has no thin-coin override (ADR-0038 had
   "the stress value or 300 s, whichever is larger" for thin coins); the 300 s thin-coin delay lives on only in
   severe. The old 10 s point is no longer a scenario; it stays on the delay grid (1, 1.2, 5, 10, 60, 300 s) with
   60 s and 300 s, so the old base and stress delays are still reported (ADR-0059).
4. **What is not changed.** The decision time inside the delay stays at event + `receive_ms` 250 + `debounce_ms`
   250 (ADR-0030, placeholders); the acknowledgement is at event + the scenario delay. The measured receive median
   (392 ms) is above the 250 ms placeholder, so the replay's decision sees fills slightly earlier than the
   measurement implies; that affects which fills are batched together, not the acknowledgement time or the drift.
   It is left open, not corrected here.
5. **Where the economic gate reads stress.** The plan's stress check (ADR-0055: measured, not exhausted, drawdown
   within -10%) is read on `stress` (5 s). `severe` is reported beside it with the same rule as a labelled
   sensitivity.
6. **Scope of the rerun.** Drift (new 1.2 s and 5 s cells), the frozen replay (ADR-0052: frozen `E_ref` only, all
   nine windows), the stress coverage table, the cost surface (ADR-0050) on the new base. Phase 2 does not depend
   on the copy delay and is not rerun. The holdout test window (2025-12-03..2026-01-04) is never computed;
   selection does not start.

## Consequences
The replay's main results now rest on the measured delay, with three labelled caveats carried from ADR-0056: the
acknowledgement leg is Binance Demo (Hyperliquid's own cannot be measured without sending orders), the receive leg is
from one home laptop on Wi-Fi (run medians 339-738 ms), and the p99 rests on few messages. Severe and the 10/60/300 s
grid points bound what a slower setup or an outage would cost. Results before and after:
`decision/measured-latency-results.md`. The plan's scenario table carries the new rows with this ADR's number.
Every delay used by a scenario must be a point of the drift grid, or the replay stops before any work (ADR-0059).
