# ADR-0055: Count only pricing failures as unpriced in the stress coverage measure

- Status: Accepted. **Decided after the results under ADR-0049 and ADR-0053 were seen** (threshold 0.80 unchanged,
  PLACEHOLDER)
- Date: 2026-11-21
- Phase: pre-Phase 4 fixes (the user's decision after item 10)
- Amends: ADR-0049 (which intents count as unpriced), ADR-0032 (stress reporting in the economic screen)

## Context
This rule was chosen after seeing the frozen stress results of `decision/pre-phase-4-results.md` (item 10): under
ADR-0049 and the ADR-0053 fallback, 49 of the 56 gate-passing test address-windows were measured (10, 11, 15 and 13
of 16, 12, 15 and 13), 6 of the 8 Oct ones below 80% priced intents. ADR-0049 counted as unpriced every intent that
was neither filled, below the minimum size, nor unsized, so it also counted the strategy's own outcomes: deferrals
at the 1.5x address cap (26,131 frozen stress intents over the four tests, the largest group), orders in coins that
fail or lack the point-in-time price check (not copied under ADR-0044) and reduce-only blocks. The replay values
those correctly: the strategy did not trade, and its cash and positions show that. Only intents the strategy wanted
to trade but the replay could not price leave a gap in the measurement.

Because the change was made after seeing the outcome, and it turns more windows into measured ones, it comes with
three safeguards (point 3), fixed here before any result under this measure was computed.

## Decision
1. **Classes.** Intents are as before (orders not already at target). Each intent's status falls in one class:
   - **Pricing failure (unpriced):** the replay lacked a price or cost input: `no_drift_cell`,
     `stress_sample_unavailable`, `no_eligible_aggtrade`, `outside_mapping_window`, `missing_sqrt_inputs`,
     `missing_impact_volume`, `missing_participation_volume`, `missing_order_budget` (no completed 4h volume for
     the budget), `missing_cap_mark` (no minute mark to project the cap) and `invalid_scenario_price`.
   - **Measured outcome:** `filled`, and the strategy's policy outcomes `below_minimum`, `below_minimum_at_ack`,
     `cap_headroom`, `failed_price_check`, `insufficient_price_check`, `no_binance_mapping`, `reduce_only` and
     `unusable_equity`.
   - Any other status stops the run: a new status must be classified here first.
2. **Measure.** `priced_share` = 1 - pricing failures / intents (1 with no intents); `unpriced` and `unpriced_share`
   count pricing failures only. The ADR-0049 measure stays in every summary as `priced_share_broad`,
   `unpriced_broad` and `unpriced_share_broad`. A stress result (main run and every delay-grid point) with
   `priced_share` below 0.80 is `unmeasured_low_coverage` with null return fields, as in ADR-0049.
3. **Safeguards** (frozen policy, gate-passing test address-windows, per test origin and pooled):
   1. *Both measures side by side*: windows measured, mean stress return over the measured windows and positive
      count, under ADR-0049 and under this ADR.
   2. *Stress check in the economic gate.* An address-window passes the plan's stress check ("the stress loss stays
      within the -10% step of the drawdown ladder") only when its stress result is measured, the account is not
      exhausted and the stress maximum drawdown (daily closes, from the higher of the allocation and the running
      peak) is no worse than -10% (`risk.yaml` `drawdown_ladder.reduce_only`). That bound also keeps the window's
      return at or above -10%. **An unmeasured window fails the check**: it stays in the denominator and is never
      dropped. Reported: passes, fails on loss, fails as unmeasured.
   3. *Worst-measured sensitivity.* Each unmeasured stress window takes the worst measured stress return (this
      measure) among the gate-passers of the same test origin; the mean and positive count with that value are
      reported next to the measured-only figures. A test with no measured window gets no imputed value and is
      reported as such. The imputed value never turns a stress check into a pass.
4. Base and optimistic are unchanged (always measured).

## Consequences
ADR-0053's coverage target (no gate-passing test window below 80% priced) is read on this measure, with the broad
measure beside it. Output: `research/replay_frozen/stress_coverage.csv` (ADR-0052: frozen only). Expected hashes:
`provenance/PRE_PHASE4_OUTPUT_CHECKSUMS.txt` now lists the frozen tree; the archived comparison, produced before this
ADR, is in `provenance/SIZING_ARCHIVE_CHECKSUMS.txt`. Code:
`replay_book.PRICING_FAILURES`, `replay_book.summaries`, `replay_frozen.stress_coverage`. Tests:
`tests/test_pre_phase4.py`.
