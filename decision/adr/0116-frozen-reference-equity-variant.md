# ADR-0116: Frozen reference equity between reviews, as a sizing variant to compare

- Status: Accepted as a research variant; the sizing policy is chosen by the user (a later ADR in 0110-0129); promoted to the sizing rule and amended by ADR-0119
- Date: 2026-11-20
- Phase: pre-Phase 4 fixes (brief item 7)
- Relates to: the plan's "Sizing and portfolio construction" (E_ref frozen between reviewed rebalances),
  ADR-0081 and ADR-0043 (the dynamic rule now in use)

## Context
The plan sizes each leader on a reference equity `E_ref` that is fixed between reviewed rebalances, so that a
change in the leader's equity alone cannot change our exposure. The replay divides by the latest snapshot equity
at every decision (`replay_orders.py:342`, `replay_cap.py:136,144`, ADR-0081): a deposit shrinks our copy, a
withdrawal or a loss enlarges it. Both are implemented on the same stack and compared before a policy is chosen.

## Decision
**Frozen variant** (`*_sqrt_cap_part_ns_sweep_frozen`):
1. Reviews at the start of every replay window (UTC midnight) and every 14 days after it, while before the
   window end. Training windows start on 27 Jul 2025 (first fill day); each test window is 14 days, so it has
   one review, at its origin.
2. `E_ref` at a review = the equity of the leader's latest cross-margin snapshot with timestamp <= the review,
   if usable (equity > 0 and not frozen under ADR-0060, as for the dynamic rule). It is fixed until the next
   review.
3. Copy multiplier = min(allocation / `E_ref`, 1) (no scale-up, ADR-0043); targets = leader position x
   multiplier, then the common 1.5x projection.
4. An unusable equity at a review makes the address reduce-only until the next review with usable equity: targets
   use the last usable `E_ref` of the window, and an order may only move the follower's position (held plus
   pending) toward zero, never increase or flip it (blocked orders: `status = reduce_only`). Before any usable
   review in a window there is no reference and nothing to reduce (`unusable_equity`).
5. Everything else is the dynamic full stack: square-root impact (Y = 1), the 1.5x address cap, 0.5%
   participation, the leader-batch order budget, the leader-sweep anchor, the conservative alt drift
   (ADR-0114), the point-in-time price check (ADR-0110), forced fills off the anchor (ADR-0112) and the stress
   coverage rule (ADR-0115).

**Dynamic variant** (`*_sqrt_cap_part_ns_sweep`): the same stack with the ADR-0081 denominator, the latest usable
snapshot at each decision.

Both run on the nine Phase 3 windows (five training, four test; the holdout is never computed) into
`research/replay_sizing/`, next to the original-model replay that supplies their shared inputs. Orders record
`sizing_equity`, `copy_multiplier`, `reduce_only` and, for the frozen variant, the review (`review_ms`,
`review_row`, `review_status`).

## Consequences
The comparison (per address and pooled: target exposure, gross and leverage, turnover, orders and skips, copy
return, drawdown, stress, and the address-windows where the variants differ most) is in
`decision/pre-phase-4-sizing-comparison.md`. Tests (`tests/test_pre_phase4.py`): the review schedule, the plan's
invariant (with positions and prices fixed, a change in leader equity between reviews leaves the target
unchanged), the multiplier bound and reduce-only after an unusable review.
