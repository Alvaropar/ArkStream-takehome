# ADR-0037: No scale-up is the copy sizing rule

- Status: Accepted (frozen); denominator amended by ADR-0052 (frozen reference equity instead of the latest usable equity)
- Date: 2026-11-20
- Phase: Phase 3 onward
- Promotes: ADR-A0087 from a sensitivity variant to the sizing rule

## Context
Proportional copying scales a leader's positions by allocation / leader equity, so a small leader is copied at
several times their own size. In the Phase 3 sensitivities, capping that multiplier at 1 was the change that moved
the mean funded base return across gate-passers from about zero to +0.63% (ADR-A0087;
`decision/phase-3-sensitivity-results.md`). Copying above the leader's size also means trading orders the leader
never traded, so their record says nothing about how those orders would have filled.

## Decision
Frozen by the user on 2026-11-20. Every follower replay, selection and portfolio step uses: copy multiplier =
min(allocation / latest usable leader equity, 1), and each follower order at most the triggering leader batch's own
notional (details below). It applies whatever allocation per address Phase 5 chooses.

### Carried over from ADR-A0087 (archived): how the rule is applied
- The multiplier is applied to every target position **before** the common 1.5x gross-exposure projection
  (`replay_cap.cap_legs(no_scale_up=True)`).
- Each order's USDC budget is capped at the triggering leader batch's own notional (sum of |size| x fill price),
  including the cross-coin resize legs that batch triggers. The tighter of this and the participation budget
  (ADR-0035) applies at decision and at fill. A batch without a leader notional skips the order
  (`missing_order_budget`).
- Inherited, skipped or pending positions can still leave a catch-up target; partial fills leave residual targets.

## Consequences
For leaders smaller than their allocation, part of it stays idle; returns are still measured on the full
allocation, which is the conservative reading. Phase 4 ranks on copy series produced with this rule (the
`*_sqrt_cap_part_ns*` variants). The other thresholds (impact coefficient, participation 0.5%, 1.5x cap) remain
placeholders.
