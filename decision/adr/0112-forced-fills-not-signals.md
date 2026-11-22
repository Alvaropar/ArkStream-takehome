# ADR-0112: Forced fills are position changes, not signals

- Status: Accepted
- Date: 2026-11-20
- Phase: pre-Phase 4 fixes (brief item 3)
- Amends: ADR-0004 (drift sample), ADR-0088 (sweep anchor and size study)

## Context
The package marks forced fills in `dir`: `Auto-Deleveraging` (654 core-perp fills, $70.5M), `Settlement` (37) and
`Liquidated Isolated Long`, `Liquidated Isolated Short`, `Liquidated Cross Long` (34). Each forced fill has its own
order id (no oid mixes forced and voluntary fills). They were counted as leader orders in the drift estimate and
in the leader-size study, and the taker ones (ADL and settlement) were re-anchored at their sweep VWAP or deepest
fill under ADR-0088. The leader did not choose them, so their prices say nothing about the move after a signal.

## Decision
1. Forced = `dir` in {`Auto-Deleveraging`, `Settlement`} or starting with `Liquidated` (`instruments.forced_fill`).
2. Excluded from: drift estimation (`drift.leader_orders`, used by `drift.estimate` and the replay's warm-up
   vintages); the ADR-0088 sweep anchor (a forced batch keeps the first-fill anchor, `anchor_rule = first_fill`,
   and carries `forced = true`); the ADR-0088 leader-size study.
3. Kept everywhere else: the replay still mirrors a forced fill as the leader's position change (the follower
   reduces with it), and leader positions, round trips, books, liquidation gates and holding bands still include
   them.

## Consequences
The counts excluded (fills and orders by kind, per estimation window and replay window) are reported in
`decision/pre-phase-4-results.md`. Drift cells, the warm-up vintages and the size study are rerun. Tests:
`tests/test_pre_phase4.py` (drift sample, anchor, and the replay mirror).
