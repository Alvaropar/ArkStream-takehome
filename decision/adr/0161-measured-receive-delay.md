# ADR-0161: Set the replay's receive delay to the measured 392 ms

- Status: Accepted. Decided after seeing results (ADR-0150 item 4 left the placeholder open); fixed here before any
  replay result under it was computed.
- Date: 2026-11-21
- Phase: Phase 3 (follower replay), rerun before Phase 4
- Amends: ADR-0081 (the 250 ms receive PLACEHOLDER), ADR-0104 (now used by the replay), ADR-0150 item 4.

## Context
The replay's decision time is event + `receive_ms` + `debounce_ms` (ADR-0081): 250 + 250 ms, both placeholders. The
Hyperliquid `userFills` receive delay is measured (ADR-0104: pooled 284 fills, p10 265, **p50 392**, p90 793,
p99 1,218 ms; run medians 339-738 ms; home laptop on Wi-Fi). The acknowledgement is event + the scenario delay
(ADR-0150) and does not depend on `receive_ms`.

## Decision
1. `config/execution.yaml: replay.receive_ms: 392` (the pooled median, ADR-0104). The debounce stays 250 ms
   (PLACEHOLDER, ADR-0081); every scenario delay is unchanged.
2. What it moves: each fill becomes visible at event + 392 ms and a batch decides at its first fill + 642 ms. The
   batch rule (a fill joins the open batch of its trader, coin and order id if received by the deadline) shifts
   receive and deadline by the same amount, so **which fills form one batch does not change**; what can change is
   anything read at the decision time against data on its own clock: the leader's latest cross-margin snapshot
   (equity, first-usable-snapshot reviews, ADR-0119), the latest completed Hyperliquid 4h bar (thin-coin delay of
   severe, liquidity bucket, impact volume), the spread estimate's `known_at`, the drift vintage at a UTC midnight,
   and the cap's view of other coins' leader positions (visible at event + receive). The count of decisions whose
   grouping or inputs change is reported in `decision/alt-floor-receive-results.md`.
3. Ordering checks stay: the acknowledgement must fall strictly after the batch's latest visibility. With the
   shortest delay (optimistic 1 s) the latest visibility is at most first fill + 250 + 392 = 642 ms, so the check
   still holds for every batch; the direct-coin acknowledgement print must follow it (ADR-0080).

## Consequences
The replay's decision timing now rests on the measurement, with ADR-0104's caveats (one home laptop, run medians
339-738 ms). The latency session's own outputs (`src/arkstream/latency.py` keeps its 250 ms debounce constant) are
not touched. Tests: `tests/test_alt_floor_receive.py` (batch grouping unchanged by a uniform receive shift; decision
time event + receive + debounce from the config).
