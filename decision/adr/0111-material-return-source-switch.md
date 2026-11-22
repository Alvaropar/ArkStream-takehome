# ADR-0111: Switch to the rebuilt book only on material, persistent PnL identity breaches

- Status: Accepted (thresholds PLACEHOLDER)
- Date: 2026-11-20
- Phase: pre-Phase 4 fixes (brief item 2)
- Amends: ADR-0065 (the switching rule; the book series itself is unchanged)

## Context
ADR-0065 moves an address's whole return series to the rebuilt core-perp book after a single snapshot with
abs(pnl - (equity - net_deposit)) > 0.01 USDC (`leader_assets.primary_source`, `pnl_rows_gt_tight > 0`). One
cent of rounding or one isolated transfer is enough to replace a cross-margin series by a reconstruction. The
thresholds below are the brief's defaults, fixed here before any return, gate or source count under them was
computed.

## Decision
1. **Breach.** A snapshot breaches when abs(pnl - (equity - net_deposit)) > max(10 USDC, 0.5% of its equity)
   (`leader.return_source.breach_abs_usdc: 10`, `breach_rel_equity: 0.005`; PLACEHOLDER). A nonpositive equity
   leaves the 10 USDC floor.
2. **Switch.** At each origin, over the address's snapshots with timestamp <= origin: the rebuilt book is the
   primary series when at least 5% of them breach (`book_min_breach_share: 0.05`) or at least 3 consecutive ones
   do (`book_min_breach_run: 3`; PLACEHOLDER). The choice is recomputed independently at every origin.
3. **Otherwise the snapshot series stays primary** and every interval whose opening or closing snapshot breaches
   is excluded from it with `exclude_reason = pnl_identity_breach` (an unexplained flow moves the residual, so
   both sides of a breach are contaminated). The exclusion applies wherever that series is the address's return:
   Phase 2 `daily_twr` and everything built on it, and the replay's test-window leader return. Coverage, fit and
   book-versus-account diagnostics keep all intervals, so they still show the disagreement.
4. **Both series are reported for every address.** `evidence` keeps `snapshot_twr_check` and adds
   `book_twr_check` / `book_days_check` (the funded book compounded over its usable days, ADR-0065 exclusions),
   plus `pnl_breaches`, `pnl_breach_share`, `pnl_breach_max_run` and `return_source_adr0065` (the old rule) so the
   switch can be audited.

## Consequences
Isolated or sub-10-USDC differences no longer replace a cross-margin series. Addresses with persistent breaches
(transfers between cross margin and other accounts) still use the book. The number of book-primary addresses
under the old and the new rule is reported per origin in `decision/pre-phase-4-results.md`. The ADR-0065 tight
tolerance still governs data grades (99% match share). Tests: `tests/test_pre_phase4.py` (isolated small and
material breaches, the share and run triggers, interval exclusion, point in time).
