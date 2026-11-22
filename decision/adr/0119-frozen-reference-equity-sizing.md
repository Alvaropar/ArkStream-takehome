# ADR-0119: Size every copy on the frozen reference equity

- Status: Accepted (sizing policy chosen by the user on 2026-11-21; the only policy from 2026-11-21, section 5)
- Date: 2026-11-21
- Phase: pre-Phase 4 fixes (brief item 7, the user's choice); applies to Phase 4 onward
- Promotes: ADR-0116 (frozen variant) to the sizing rule, with its review schedule amended below
- Replaces: the ADR-0081 denominator (the latest usable snapshot at each decision) for selection, the portfolio
  replay and operations. ADR-0043 (no scale-up) is unchanged.

## Context
Frozen and dynamic sizing were compared on the full stack (`decision/pre-phase-4-sizing-comparison.md`). Frozen
earned slightly less (+0.47% vs +0.55% mean funded base return over 56 gate-passing test address-windows; cost
surface lower bound -0.06% vs +0.11%) with a much lower worst follower leverage (1.58x vs 2.72x), and it satisfies
the plan's invariant: with positions and prices fixed, a change in the leader's equity cannot change our exposure.
Its training windows lost 0.84 pp on average against dynamic, mostly because 304 addresses had no snapshot at the
27 Jul window-start review and stayed flat until the 10 Aug review.

## Decision
1. **Sizing.** Copy multiplier = min(allocation / `E_ref`, 1). `E_ref` is the equity of the leader's latest
   cross-margin snapshot at a review, if usable (equity > 0, not frozen under ADR-0060); it is fixed until the next
   review. An unusable equity at a review makes the address reduce-only until the next usable review (ADR-0116).
2. **Reviews.** At the window start (UTC midnight) and every 14 days after it. **Amended here:** an address with no
   usable equity at the window-start review gets its first review at its first usable snapshot in the window, at that
   snapshot's timestamp (point in time: the snapshot is known then); the 14-day schedule from the window start then
   continues unchanged. Before that first review the address has no reference and sends no orders.
3. **Plain.** No review is triggered by a fall in the leader's equity, and no signal-copy variant (copying individual
   fills or orders) is added.
4. **Copy model.** The task asks for a portfolio of addresses, so target-position mirroring with netting stays the
   copy model: the leader's visible position times the multiplier, projected onto the common 1.5x address cap,
   netted against acknowledged holdings and pending orders (ADRs 0081, 0085-0088).

5. **Frozen only (the user's instruction, 2026-11-21).** Frozen `E_ref` is the only sizing policy from here: no
   further dynamic runs or comparisons. The dynamic denominator was rejected because it adds an implicit
   mean-reversion overlay: with the leader's positions unchanged, a fall in their equity raises allocation / equity
   and so enlarges our copy, and a rise shrinks it. That is a bet that the leader's losses revert and their gains do
   not last, which nobody chose and which the plan's invariant rules out (in the comparison, a leader whose equity
   fell 58% had the multiplier raised from 0.56 to 0.91 as they lost, and a leader whose equity rose 54% had theirs
   cut). The dynamic results stay only as the archived record behind ADR-0116 and this ADR, in
   `research/replay_sizing/` and `decision/pre-phase-4-sizing-comparison.md`; they are not rerun or updated.

## Consequences
Phase 4 ranks on the frozen copy series (`*_sqrt_cap_part_ns_sweep_frozen`), and the portfolio replay and operations
size on `E_ref`. The replay runs the frozen variant alone (`arkstream replay --frozen`, `research/replay_frozen/`):
the shared inputs (universe, drift cells, bands, spreads) are prepared without simulating the dynamically sized
original model, and the cost surface covers frozen only. `research/replay_sizing/` is the archived comparison. Orders record `review_kind` (`schedule` or `first_usable_snapshot`). Tests:
`tests/test_pre_phase4.py` (the first-usable-snapshot review, the schedule after it, the invariant).
