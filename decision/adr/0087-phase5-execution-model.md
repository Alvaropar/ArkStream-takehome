# ADR-0087: Phase 5 execution model: sleeve targets, netting in the physical order, shared participation, stale signals and the flatten sweep

- Status: Accepted (the user approved ADRs 0086-0095 on 2026-11-24); thresholds PLACEHOLDER; details pinned in ADR-0096
- Date: 2026-11-23
- Phase: Phase 5 (revision 4), the portfolio replay (simulated; the live engine is out of scope, ADR-0064)
- Amends: ADR-0035 for the Phase 5 engine only (the participation budget becomes per coin per 4h bar, summed over
  sleeves; the single-sleeve replays keep the per-order budget)
- Source: `decision/phase-5-methodology-1.md` section 3 (revision 4)

## Context
The Phase 3 and Phase 4 replays copy one address at a time. A scheme of two or more sleeves needs:
- one aggregate target per coin;
- netting between sleeves;
- one participation budget shared by the sleeves;
- rules for stale signals and for residuals left when a leader is flat.

Whole-sleeve scaling (ADR-0088) is the user's decision 2: a limit never cuts a single leg.

## Decision
1. **Leader state.**
   - Fills update a virtual book per leader at the measured 392 ms receive delay (ADR-0062).
   - Snapshots update equity, the `E_ref` reviews (ADR-0052) and resync.
2. **Sleeve target** per coin: `T_{i,c} = s_i · k_i · q_{i,c}`.
   - `q` is the leader's net position, `k_i` the frozen multiplier (ADR-0052) and `s_i` the risk-state scalar
     (ADR-0089).
   - Coins outside the wallet's tradable set have target 0 (`not_tradable`, ADR-0073).
3. **Aggregate target** per coin: `T_c = Σ_i λ_i · T_{i,c}`. `λ_i ∈ [0, 1]` is the sleeve's limit scale (ADR-0088).
4. **Netting and attribution** (pinned here; the methodology states the principle only):
   - Each sleeve's virtual delta is `Δ_{i,c} = λ_i T_{i,c} − held_{i,c} − pending_{i,c}`. The physical order is
     `Δ_c = Σ_i Δ_{i,c}`.
   - Where sleeve deltas have opposite signs, the offsetting part is **crossed internally at the decision mark**,
     with no fee, spread or impact. That is the netting saving, reported per coin.
   - The net part is executed physically and allocated to the sleeves on its side pro rata to their `|Δ_{i,c}|`,
     at the physical fill price and costs.
   - Each sleeve's PnL, NAV, drawdown and state use its virtual positions only.
5. **Order rules.**
   - **Deadband:** no order while `|Δ_c| < max(10 USDC, 2% of |T_c|)`. An internal cross needs no physical order.
   - **Timing:** after a 250 ms debounce, plus a 15-minute sweep.
   - **Type:** an IOC with a deterministic client id, at a price bounded by O2 (ADR-0088).
   - **Failures:** a partial fill, rejection or timeout recomputes `Δ` from state. The original size is never resent.
6. **Participation (O1).**
   - The budget is per coin and per 4h bar: the summed `|notional|` of our physical orders on coin `c` submitted
     during the bar in progress is at most 0.5% (PLACEHOLDER) of the volume of the latest completed Hyperliquid 4h
     bar.
   - An order is clipped to the budget left, and the remainder waits for the next bar, whose budget uses the bar that
     has just closed.
   - Being on physical orders, the budget is shared by both sleeves.
   - **Amends ADR-0035 for this engine only.** ADR-0035 gave each order its own budget. The single-sleeve replays
     (Phase 3, Phase 4 and the P5-1 sizing replays) keep the per-order rule, so they stay comparable with the 10k
     trees.
7. **Flatten sweep.** When a leader is flat in a coin and its sleeve still holds it, the residual is closed
   reduce-only at the next 15-minute sweep, within O1 (pre-holdout Check 5).
8. **Stale signals.**
   - A leader event whose age at the decision (decision time minus the leader fill time) exceeds 30 s (PLACEHOLDER)
     is not executed.
   - The sleeve is resynced to the leader's state at its next decision.
9. **Funding** is booked as cash in the copy's PnL and reported separately from α (ADR-0084).
10. **Delays and costs:** the four scenarios of ADR-0058 and ADR-0060 (optimistic, base, stress, severe 60 s /
    300 s), with the frozen tradable stack's cost model, unchanged: half-spread, fee, square-root impact, delay drift
    and the sweep anchor.
11. **Shape and tracking.** Each difference from the scaled target is logged with its cause and reported as tracking
    error:
    - execution effects on single legs: participation clips (O1), sub-minimum skips and the deadband (O3), stale
      signals (item 8);
    - one risk state: REDUCE_ONLY does not open legs that the leader opens during the state (ADR-0089).

    No limit changes the book's shape.
12. **Determinism.**
    - The ADR-0034 tie rules hold within a sleeve.
    - Across sleeves, events at the same time are processed in address order.
    - Internal crosses are settled before the physical order.

## Consequences
- **Code:** `src/arkstream/portfolio_replay.py` (P5-3), one event loop for S\*, U\* and G\* from the same leader
  events. The parameters are in the `engine` block of `config/risk.yaml` v3; delays and costs stay in
  `config/execution.yaml`.
- **Tests (F1, ADR-0095):**
  - participation is shared within a bar;
  - a stale signal is dropped and resynced;
  - the flatten sweep closes a residual;
  - a partial fill is never resent at its original size;
  - an internal cross books no cost.
- **Netting** is measured, not assumed: savings per coin (BTC is shared by the two books) are reported.
