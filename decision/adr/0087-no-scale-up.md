# ADR-0087: Never copy a leader at more than their own size

- Status: Accepted; promoted to the sizing rule by ADR-0043
- Date: 2026-11-20
- Phase: Phase 3, cost sensitivities

## Context
Proportional copying scales by allocation / leader equity, so a 10,000 USDC allocation copies a 2,000 USDC leader
at 5x its own size. The largest impact charges came from exactly these cases (for example a 39,000 USDC ETC order
copying a leader with 1,958 USDC of equity, at 180% of the 4h bar).

## Decision
- Variant `part_ns` = `part` (ADR-0086) + this rule.
- Copy multiplier = min(allocation / latest usable leader equity, 1) for every target position, before the common
  1.5x gross-exposure projection (`replay_cap.cap_legs(no_scale_up=True)`).
- Each order's USDC budget is also capped at the triggering leader batch's own notional (sum of |size| x fill
  price), including the cross-coin resize legs that batch triggers; the tighter of this and the participation
  budget applies at decision and at fill. A batch without a leader notional skips the order (`missing_order_budget`).
- Inherited, skipped or pending positions can still leave a catch-up target; partial fills leave residual targets.

## Consequences
An address whose equity exceeds the allocation is unaffected by the multiplier; small leaders are copied 1:1, so
part of the allocation can stay idle and their copy return is measured on the full allocation. Results and counts
in `decision/phase-3-sensitivity-results.md`.
