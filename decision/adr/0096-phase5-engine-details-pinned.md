# ADR-0096: Phase 5 engine details pinned while building P5-3 and P5-4

- Status: Accepted (pinned on development data on 2026-11-24, before any P5-4 or P5-5 result; recorded in
  `provenance/trial_log.md`, "Phase 5 P5-3 engine")
- Date: 2026-11-24
- Phase: Phase 5 (revision 4), steps P5-3 and P5-4
- Refines: ADR-0087 (pricing, the sweep, the participation budget), ADR-0088 item 4 (hourly checks), ADR-0089
  (triggers, reviews, resume), ADR-0095 items 1-2 (the population runs, the `E_ref` variant)
- Source: `src/arkstream/portfolio_engine.py`, `src/arkstream/portfolio_replay.py`,
  `src/arkstream/phase5_population.py`

## Context
ADRs 0087-0089 and 0095 state the engine's rules. Building it needed some details the methodology does not give.
Three of them (items 3-5) were fixed after a smoke run on the pair's development windows showed a trigger firing
for a reason that is not what it measures. Each fix applies at every origin, and no result is reverted on what it
produces.

## Decision
1. **Pricing (ADR-0087 item 10).**
   - The trigger leg of a leader batch takes the frozen tree's reference price at acknowledgement: tape or
     parameterised drift, with the sweep anchor.
   - Every other leg (resizes after a `λ` change, sweeps, state actions) is priced at the decision mark. It uses the
     same signal's tape factor (b1 / b0) when the tree has one, and otherwise the ADR-0029 parameterised drift for
     the scenario's delay.
   - Half-spread, square-root impact and fee are those of `replay_orders.execute`. FLATTEN orders use stress costs.
   - A trigger leg without a tree price falls back to the leg rule.
2. **When `λ` moves (ADR-0088 items 3-4).**
   - `λ` is re-solved from 1, with every limit, only at a leader-driven target update.
   - Hourly checks can only lower it: S2 and P5 for S\*, and the cap for G\*. They set the passive P4 flag, which
     blocks increases.
   - The 15-minute sweep executes toward the current targets. It never sells because of a P4 breach caused by marks
     alone.
3. **C1 (ADR-0089).**
   - The realised cost per side of each fill is measured against the order's own anchor: the tree's mid at the
     leader fill for a trigger leg, the decision mark otherwise. It includes the fee.
   - It is compared with the stress model's cost for the same order: half-spread, fee, stress drift and three times
     the impact.
   - The trigger compares the medians over the trailing 14 days and needs at least 5 fills. Model against model.
4. **L6** is measured only once the run holds 7 full days of the leader book. Before that the trailing window is a
   sample of hours, not 7 days.
5. **L7** uses the leader's last fill from before the window only when it is known at the window start. A training
   window starts before the origin, so the origin's own "last fill" is in its future.
6. **Reviews and resume (ADR-0089 items 4-5).**
   - Reviews fall at each window start and every 14 days after it.
   - A firing is a trigger's condition turning on, counted whatever the sleeve's state.
   - Resume is modelled as "yes" at the first review at which the trigger has cleared, and labelled so. For S3, the
     drawdown must be back above -10%; for the scheme's HALVED and REDUCE_ONLY, above -5% and -10%.
7. **C3** has no data source in the replay. It is exercised by fault injection only: a feed outage of more than
   60 s while holding freezes increases.
8. **The ADR-A0087 per-order leader-notional budget** is not applied in the portfolio engine. `k ≤ 1` and `λ ≤ 1`
   already bound each sleeve's change by the leader's own change.
9. **Population copies (ADR-0095 items 1-2).** Every A/B address is copied as a one-sleeve basket at 10,000 USDC with
   S1, S3, the states and the triggers, plus the execution model. The scheme limits (S2, P1-P5, P6) are defined on
   the two-sleeve `D` and are off. The forward 14-day return and drawdown after a firing come from the same copy's
   U twin.
10. **The `E_ref` high-water variant:** `E_ref,prev` is the leader's latest usable snapshot equity at or before the
    previous review (window start minus 14 days), from the origin's Phase 2 table.
11. **Exposure-weighted `λ` is reported beside the time-weighted mean.** Flat hours have `λ = 1` trivially, so the
    time-weighted mean overstates how much of the leader-shaped book a sleeve keeps. The exposure weight is the U\*
    twin's target gross.

## Consequences
- **Tests:** `tests/test_phase5_engine.py` (F1, F5, F6 and the P5-2 leak test).
- **The C1 model-against-model label** carries into the memo with D3's.
- **Item 6's modelled resume** can occur only in a run longer than 14 days: the training windows, and the holdout
  (reviews on 3, 17 and 31 Dec).
